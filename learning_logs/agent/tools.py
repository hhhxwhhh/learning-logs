"""Agent 工具集。

每个工具是一段受控的代码：只能读写当前用户自己的数据，
参数用 JSON Schema 描述，模型只能按 schema 调用。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable

from django.db.models import Count
from django.utils import timezone

from learning_logs.models import Entry, Flashcard, Topic

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable

    def spec(self) -> dict:
        """转成 OpenAI 兼容的 function 定义。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


REGISTRY: dict[str, Tool] = {}


def register(name: str, description: str, parameters: dict):
    """把一个函数登记成 Agent 可调用的工具。"""

    def decorator(func):
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=func,
        )
        return func

    return decorator


def specs() -> list[dict]:
    return [tool.spec() for tool in REGISTRY.values()]


def run(user, name: str, arguments: dict | None = None) -> dict:
    """执行一次工具调用。出错时返回错误信息而不是抛出，方便模型自我修正。"""
    tool = REGISTRY.get(name)
    if tool is None:
        return {"ok": False, "error": f"未知工具：{name}"}
    try:
        result = tool.handler(user, **(arguments or {}))
    except TypeError as exc:
        return {"ok": False, "error": f"参数不匹配：{exc}"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("工具 %s 执行失败", name, exc_info=True)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, dict):
        return result
    return {"ok": True, "result": result}


# ---------------------------------------------------------------------------
# 只读工具
# ---------------------------------------------------------------------------


@register(
    "list_topics",
    "列出当前用户的主题，包含条目数与进度。",
    {"type": "object", "properties": {}},
)
def list_topics(user) -> dict:
    rows = (
        Topic.objects.filter(owner=user)
        .annotate(entry_count=Count("entry"))
        .order_by("-date_added")[:30]
    )
    return {
        "ok": True,
        "topics": [
            {
                "id": topic.id,
                "text": topic.text,
                "entries": topic.entry_count,
                "progress": topic.progress_percentage(),
            }
            for topic in rows
        ],
    }


@register(
    "search_entries",
    "按关键词搜索当前用户的笔记，返回命中片段。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "最多返回几条，默认 5"},
        },
        "required": ["query"],
    },
)
def search_entries(user, query: str = "", limit: int = 5) -> dict:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "query 不能为空"}
    limit = max(1, min(int(limit or 5), 20))
    rows = (
        Entry.objects.filter(topic__owner=user, text__icontains=query)
        .select_related("topic")
        .order_by("-date_added")[:limit]
    )
    return {
        "ok": True,
        "query": query,
        "results": [
            {
                "id": entry.id,
                "topic": entry.topic.text,
                "text": entry.text[:300],
                "date": entry.date_added.strftime("%Y-%m-%d"),
            }
            for entry in rows
        ],
    }


@register(
    "get_topic_notes",
    "读取某个主题下的笔记。主题名可以模糊匹配。",
    {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "主题名"},
            "limit": {"type": "integer", "description": "最多返回几条，默认 10"},
        },
        "required": ["topic"],
    },
)
def get_topic_notes(user, topic: str = "", limit: int = 10) -> dict:
    topic = (topic or "").strip()
    if not topic:
        return {"ok": False, "error": "topic 不能为空"}
    limit = max(1, min(int(limit or 10), 30))
    record = Topic.objects.filter(owner=user, text__icontains=topic).first()
    if record is None:
        return {"ok": False, "error": f"没有找到主题：{topic}"}
    rows = record.entry_set.order_by("-date_added")[:limit]
    return {
        "ok": True,
        "topic": {"id": record.id, "text": record.text},
        "entries": [
            {
                "id": entry.id,
                "text": entry.text[:300],
                "date": entry.date_added.strftime("%Y-%m-%d"),
            }
            for entry in rows
        ],
    }


@register(
    "get_stats",
    "读取最近的学习统计：条目数、学习时长、连续天数、待复习卡片。",
    {"type": "object", "properties": {}},
)
def get_stats(user) -> dict:
    from learning_logs.services import stats

    overview = stats.overview(user)
    return {
        "ok": True,
        "overview": overview,
        "streak": stats.current_streak(user),
        "week_minutes": stats.range_minutes(user, 7),
        "due_cards": Flashcard.objects.filter(
            user=user, due_date__lte=timezone.localdate()
        ).count(),
    }


@register(
    "list_due_cards",
    "列出今天到期的闪卡。",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "最多返回几张，默认 5"}
        },
    },
)
def list_due_cards(user, limit: int = 5) -> dict:
    limit = max(1, min(int(limit or 5), 20))
    rows = Flashcard.objects.filter(
        user=user, due_date__lte=timezone.localdate()
    ).select_related("topic")[:limit]
    return {
        "ok": True,
        "cards": [
            {"id": card.id, "topic": card.topic.text, "front": card.front}
            for card in rows
        ],
    }


# ---------------------------------------------------------------------------
# 写入工具
# ---------------------------------------------------------------------------


@register(
    "create_entry",
    "在指定主题下写一条笔记。主题不存在时会新建同名主题。",
    {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "主题名"},
            "text": {"type": "string", "description": "笔记内容"},
        },
        "required": ["topic", "text"],
    },
)
def create_entry(user, topic: str = "", text: str = "") -> dict:
    from learning_logs import events
    from learning_logs.services import cache as cache_service

    topic = (topic or "").strip()
    text = (text or "").strip()
    if not topic or not text:
        return {"ok": False, "error": "topic 与 text 都不能为空"}

    record, created = Topic.objects.get_or_create(text=topic[:200], owner=user)
    entry = Entry.objects.create(topic=record, text=text)
    events.publish(
        "entry_created",
        user,
        f"在「{record.text}」写了一条笔记",
        topic=record,
        payload={"entry_id": entry.id, "via": "agent"},
    )
    cache_service.invalidate(user.id)
    return {
        "ok": True,
        "entry_id": entry.id,
        "topic": record.text,
        "topic_created": created,
    }


@register(
    "create_flashcard",
    "为指定主题新增一张闪卡。",
    {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "主题名"},
            "front": {"type": "string", "description": "正面问题"},
            "back": {"type": "string", "description": "背面答案"},
        },
        "required": ["topic", "front", "back"],
    },
)
def create_flashcard(user, topic: str = "", front: str = "", back: str = "") -> dict:
    from learning_logs import events

    topic = (topic or "").strip()
    front = (front or "").strip()
    back = (back or "").strip()
    if not topic or not front or not back:
        return {"ok": False, "error": "topic、front、back 都不能为空"}

    record = Topic.objects.filter(owner=user, text__icontains=topic).first()
    if record is None:
        record = Topic.objects.create(text=topic[:200], owner=user)

    card = Flashcard.objects.create(user=user, topic=record, front=front, back=back)
    events.publish(
        "card_created",
        user,
        f"为「{record.text}」新增了一张闪卡",
        topic=record,
        payload={"card_id": card.id, "via": "agent"},
    )
    return {"ok": True, "card_id": card.id, "topic": record.text}


@register(
    "create_todo",
    "往指定主题的最新一条笔记里追加一条待办（- [ ] 格式）。",
    {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "主题名"},
            "text": {"type": "string", "description": "待办内容"},
        },
        "required": ["topic", "text"],
    },
)
def create_todo(user, topic: str = "", text: str = "") -> dict:
    from learning_logs import events

    topic = (topic or "").strip()
    text = (text or "").strip()
    if not topic or not text:
        return {"ok": False, "error": "topic 与 text 都不能为空"}

    record = Topic.objects.filter(owner=user, text__icontains=topic).first()
    if record is None:
        return {"ok": False, "error": f"没有找到主题：{topic}"}

    entry = record.entry_set.order_by("-date_added").first()
    if entry is None:
        return {"ok": False, "error": "这个主题下还没有笔记，先写一条再看待办"}

    entry.text = (entry.text or "").rstrip() + f"\n- [ ] {text}"
    entry.save()
    events.publish(
        "todo_toggled",
        user,
        f"新增了一条待办：{text}",
        topic=record,
        payload={"entry_id": entry.id, "via": "agent"},
    )
    return {"ok": True, "entry_id": entry.id, "todo": text}
