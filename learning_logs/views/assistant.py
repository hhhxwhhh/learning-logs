"""学习助手对话页。"""

from __future__ import annotations

import logging

import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from ..ai.providers import AIError, available_models, resolve_model
from ..agent import runtime as agent_runtime
from ..agent import tools as agent_tools

logger = logging.getLogger(__name__)

@login_required
def agent(request):
    """Agent 对话页：模型按需调用工具，读写自己的学习数据。"""
    history = list(request.session.get("agent_history") or [])
    result = None
    error = ""

    if request.method == "POST":
        # 页面本身只负责渲染；实际问答走 /agent/stream/ 的 SSE 接口。
        # 这里保留同步分支，方便没有 JS 时直接提交表单。
        prompt = (request.POST.get("prompt") or "").strip()
        model = request.POST.get("model") or None
        if not prompt:
            error = "先描述一下你想做的事。"
        else:
            try:
                result = agent_runtime.run(
                    request.user, prompt, model=resolve_model(model) if model else None
                )
            except AIError as exc:
                error = str(exc)
            else:
                error = result.get("error", "")
                history.append({"prompt": prompt, "answer": result.get("answer", "")})
                request.session["agent_history"] = history[-6:]

    return render(
        request,
        "learning_logs/agent.html",
        {
            "history": history,
            "result": result,
            "error": error,
            "tools": list(agent_tools.REGISTRY.values()),
            "models": available_models(),
        },
    )


@login_required
@require_POST
def agent_stream(request):
    """Agent 的流式接口：SSE 逐步返回文本与工具调用。"""
    prompt = (request.POST.get("prompt") or "").strip()
    model = request.POST.get("model") or None
    if not prompt:
        return JsonResponse({"error": "先描述一下你想做的事。"}, status=400)

    def stream_events():
        try:
            for event in agent_runtime.run_stream(
                request.user, prompt, model=resolve_model(model) if model else None
            ):
                yield f"event: {event.get('type', 'message')}\n"
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except AIError as exc:
            payload = {"type": "error", "message": str(exc)}
            yield "event: error\n"
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    response = StreamingHttpResponse(stream_events(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
