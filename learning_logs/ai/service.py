"""AI 业务编排：会话上下文、流式回答、结构化生成学习路径。"""

from __future__ import annotations

import json
import re
from typing import Iterator

from django.conf import settings
from django.db import transaction

from learning_logs.models import (
    ChatMessage,
    ChatSession,
    Flashcard,
    LearningPath,
    PathStep,
    StepResource,
    Tag,
    Topic,
)
from learning_logs.services import tags as tags_service
from learning_logs.utils.markdown import render_markdown

from . import prompts
from .providers import AIError, Message, get_provider, resolve_model


def create_session(user, topic: Topic | None = None) -> ChatSession:
    return ChatSession.objects.create(
        user=user,
        topic=topic,
        title="新的对话",
        model_name=settings.AI_MODEL,
    )


def get_or_create_session(user, topic: Topic) -> ChatSession:
    session = ChatSession.objects.filter(user=user, topic=topic).first()
    return session or create_session(user, topic)


def history_messages(session: ChatSession) -> list[Message]:
    """取最近若干条消息作为上下文，避免超出模型窗口。"""
    limit = getattr(settings, "AI_MAX_CONTEXT_MESSAGES", 16)
    recent = list(session.messages.order_by("-created_at", "-id")[:limit])
    recent.reverse()
    return [
        Message(role=item.role, content=item.content)
        for item in recent
        if item.role in ("user", "assistant")
    ]


def stream_reply(
    session: ChatSession,
    question: str,
    *,
    model: str | None = None,
    system_prompt: str = prompts.TUTOR_SYSTEM,
    prompt: str | None = None,
) -> Iterator[dict]:
    """以事件流的形式返回回答：delta / done / error。"""
    model_name = resolve_model(model)
    history = history_messages(session)

    user_message = ChatMessage.objects.create(
        session=session, role="user", content=question, model_name=model_name
    )
    if session.title in ("", "新的对话"):
        first_line = question.strip().splitlines()[0] if question.strip() else "新的对话"
        session.title = first_line[:40]
    session.model_name = model_name
    session.save(update_fields=["title", "model_name", "updated_at"])

    messages = [Message(role="system", content=system_prompt), *history]
    messages.append(Message(role="user", content=prompt or question))

    provider = get_provider()
    buffer: list[str] = []
    try:
        for delta in provider.stream(messages, model=model_name):
            buffer.append(delta)
            yield {"event": "delta", "data": {"text": delta}}
    except AIError as exc:
        # 保留用户提问，方便重试
        yield {"event": "error", "data": {"message": str(exc)}}
        return
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "data": {"message": f"生成失败：{exc}"}}
        return

    answer = "".join(buffer).strip()
    if not answer:
        yield {"event": "error", "data": {"message": "模型返回了空内容，请稍后重试。"}}
        return

    assistant_message = ChatMessage.objects.create(
        session=session, role="assistant", content=answer, model_name=model_name
    )
    session.touch()
    yield {
        "event": "done",
        "data": {
            "id": assistant_message.id,
            "user_message_id": user_message.id,
            "html": render_markdown(answer),
            "title": session.title,
        },
    }


def rewrite_title(session: ChatSession) -> str:
    """用首条提问生成更短的会话标题（不额外调用模型，节省额度）。"""
    first = session.messages.filter(role="user").first()
    if first:
        session.title = first.content.strip().splitlines()[0][:30]
        session.save(update_fields=["title"])
    return session.title


def _extract_json(raw: str) -> dict:
    """从模型输出中提取 JSON，兼容 ```json 代码块与前后废话。"""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise AIError("模型没有返回合法 JSON，请重试或换一个模型。")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AIError("模型返回的 JSON 无法解析。") from exc


@transaction.atomic
def generate_learning_path(
    user,
    goal: str,
    *,
    topic: Topic | None = None,
    model: str | None = None,
) -> LearningPath:
    """让模型输出结构化计划，并落库为学习路径 + 主题 + 步骤。"""
    context = prompts.build_context(topic) if topic else ""
    provider = get_provider()
    raw = provider.complete(
        [
            Message(role="system", content=prompts.PLAN_SYSTEM),
            Message(role="user", content=prompts.plan_prompt(goal, context)),
        ],
        model=resolve_model(model),
    )
    data = _extract_json(raw)

    steps = data.get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise AIError("模型没有生成任何步骤，请把目标描述得更具体一些。")

    path = LearningPath.objects.create(
        user=user,
        title=(data.get("title") or goal)[:200],
        description=(data.get("description") or "")[:2000],
        estimated_hours=max(1, min(int(data.get("estimated_hours") or 10), 999)),
    )

    for index, item in enumerate(steps[:8], start=1):
        if isinstance(item, str):
            item = {"topic": item}
        if not isinstance(item, dict) or not item.get("topic"):
            continue
        topic_obj, _ = Topic.objects.get_or_create(
            owner=user, text=str(item["topic"])[:200]
        )
        step = PathStep.objects.create(
            path=path,
            topic=topic_obj,
            order=index,
            description=str(item.get("description") or "")[:2000],
            estimated_hours=max(1, min(int(item.get("estimated_hours") or 2), 99)),
        )
        for resource in (item.get("resources") or [])[:5]:
            if isinstance(resource, str) and resource.strip():
                StepResource.objects.create(step=step, title=resource.strip()[:200])

    return path


def generate_flashcards(topic: Topic, count: int = 8, model: str | None = None) -> int:
    """让模型从笔记生成闪卡，返回新增数量（相同正面自动去重）。"""
    context = prompts.build_context(topic, limit=4000)
    provider = get_provider()
    raw = provider.complete(
        [
            Message(role="system", content=prompts.FLASHCARD_SYSTEM),
            Message(role="user", content=prompts.flashcard_prompt(context, count)),
        ],
        model=resolve_model(model),
    )
    data = _extract_json(raw)

    cards = data.get("cards") or data.get("items") or []
    if not isinstance(cards, list):
        raise AIError("模型没有返回合法的闪卡列表。")

    existing = {
        front.lower()
        for front in Flashcard.objects.filter(user=topic.owner, topic=topic).values_list(
            "front", flat=True
        )
    }

    created = 0
    for item in cards[:count]:
        if not isinstance(item, dict):
            continue
        front = str(item.get("front") or "").strip()[:300]
        back = str(item.get("back") or "").strip()
        if not front or not back or front.lower() in existing:
            continue
        Flashcard.objects.create(user=topic.owner, topic=topic, front=front, back=back)
        existing.add(front.lower())
        created += 1

    if created == 0:
        raise AIError("没有生成新卡片（可能模型返回的内容与已有卡片重复）。")
    return created


def suggest_tags(topic: Topic, count: int = 5, model: str | None = None) -> list[str]:
    """让模型为主题建议标签，返回清洗后的标签名列表。"""
    context = prompts.build_context(topic, limit=3000)
    existing = [tag.name for tag in Tag.objects.filter(user=topic.owner)[:20]]

    provider = get_provider()
    raw = provider.complete(
        [
            Message(role="system", content=prompts.TAGGING_SYSTEM),
            Message(role="user", content=prompts.tagging_prompt(context, existing)),
        ],
        model=resolve_model(model),
    )
    data = _extract_json(raw)

    raw_tags = data.get("tags") or []
    if not isinstance(raw_tags, list):
        raise AIError("模型没有返回合法的标签列表。")

    names: list[str] = []
    for item in raw_tags[:count]:
        name = tags_service.normalize(str(item))
        if name and name not in names:
            names.append(name)

    if not names:
        raise AIError("模型没有给出可用标签，可以手动打几个关键词。")
    return names
