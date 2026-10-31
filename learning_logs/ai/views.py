"""AI 助教页面与接口。"""

from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from learning_logs.models import ChatSession, Topic

from . import prompts, service
from .providers import AIError, available_models

logger = logging.getLogger(__name__)

# 快捷动作：系统提示词 + 发送给模型的指令
QUICK_ACTIONS = {
    "summary": ("整理成摘要", prompts.SUMMARY_SYSTEM, prompts.summary_prompt),
    "quiz": ("生成自测题", prompts.QUIZ_SYSTEM, prompts.quiz_prompt),
    "recommend": ("下一步建议", prompts.RECOMMEND_SYSTEM, prompts.recommend_prompt),
}


@login_required
def assistant(request, topic_id):
    """AI 助教工作台。"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)

    session_id = request.GET.get("session")
    if session_id:
        session = get_object_or_404(ChatSession, id=session_id, user=request.user, topic=topic)
    else:
        session = service.get_or_create_session(request.user, topic)

    sessions = (
        ChatSession.objects.filter(user=request.user, topic=topic)
        .annotate(message_count=Count("messages"))
        .order_by("-updated_at")[:30]
    )

    context = {
        "topic": topic,
        "session": session,
        "sessions": sessions,
        "messages": session.messages.all(),
        "models": available_models(),
        "selected_model": session.model_name,
        "quick_actions": [
            {"key": key, "label": value[0]} for key, value in QUICK_ACTIONS.items()
        ],
        "entry_count": topic.entry_set.count(),
    }
    return render(request, "learning_logs/ai_assistant.html", context)


@login_required
@require_POST
def new_session(request, topic_id):
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    session = service.create_session(request.user, topic)
    return redirect(f"{request.POST.get('next') or '/topics/%d/ai-assistant/' % topic.id}?session={session.id}")


@login_required
@require_POST
def delete_session(request, session_id):
    session = get_object_or_404(ChatSession, id=session_id, user=request.user)
    topic_id = session.topic_id
    session.delete()
    messages.success(request, "会话已删除。")
    if topic_id:
        return redirect("learning_logs:ai_assistant", topic_id=topic_id)
    return redirect("learning_logs:topics")


@login_required
@require_POST
def stream(request, session_id):
    """SSE 流式回答。请求体：{"message": "...", "model": "...", "action": "summary"}"""
    session = get_object_or_404(ChatSession, id=session_id, user=request.user)

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "请求体不是合法 JSON"}, status=400)

    question = (payload.get("message") or "").strip()
    action = payload.get("action")
    model = payload.get("model")

    max_length = 4000
    if len(question) > max_length:
        return JsonResponse({"error": f"问题过长，请控制在 {max_length} 字以内"}, status=400)

    context_text = prompts.build_context(session.topic) if session.topic else ""

    if action in QUICK_ACTIONS:
        _, system_prompt, builder = QUICK_ACTIONS[action]
        question = question or QUICK_ACTIONS[action][0]
        prompt = builder(context_text)
    else:
        if not question:
            return JsonResponse({"error": "请输入问题"}, status=400)
        system_prompt = prompts.TUTOR_SYSTEM
        prompt = prompts.tutor_prompt(question, context_text)

    def event_stream():
        try:
            for item in service.stream_reply(
                session,
                question,
                model=model,
                system_prompt=system_prompt,
                prompt=prompt,
            ):
                data = json.dumps(item["data"], ensure_ascii=False)
                yield f"event: {item['event']}\ndata: {data}\n\n"
        except Exception as exc:  # noqa: BLE001 - 保证连接一定能正常结束
            logger.exception("SSE 流异常")
            data = json.dumps({"message": f"服务异常：{exc}"}, ensure_ascii=False)
            yield f"event: error\ndata: {data}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    response["Connection"] = "keep-alive"
    return response


@login_required
@require_POST
def generate_path(request):
    """让 AI 把学习目标拆成可执行的学习路径。"""
    goal = (request.POST.get("goal") or "").strip()
    topic_id = request.POST.get("topic_id")

    if not goal:
        messages.error(request, "请先描述你的学习目标。")
        return redirect("learning_logs:learning_paths")

    topic = None
    if topic_id:
        topic = Topic.objects.filter(id=topic_id, owner=request.user).first()

    try:
        path = service.generate_learning_path(
            request.user, goal, topic=topic, model=request.POST.get("model")
        )
    except AIError as exc:
        messages.error(request, str(exc))
        return redirect("learning_logs:learning_paths")

    messages.success(request, f"已生成学习路径「{path.title}」，共 {path.pathstep_set.count()} 个步骤。")
    return redirect("learning_logs:learning_path_detail", path_id=path.id)
