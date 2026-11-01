"""开放接口的令牌管理与文档页。"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from ..models import ApiToken

logger = logging.getLogger(__name__)

API_ENDPOINTS = [
    {
        "method": "GET",
        "path": "/api/v1/me/",
        "desc": "账号信息与学习概览",
        "params": "无",
    },
    {
        "method": "GET",
        "path": "/api/v1/topics/",
        "desc": "全部主题及进度、标签",
        "params": "无",
    },
    {
        "method": "GET",
        "path": "/api/v1/entries/",
        "desc": "笔记列表，支持关键词与主题过滤",
        "params": "q=关键词&topic=主题ID&limit=50",
    },
    {
        "method": "GET",
        "path": "/api/v1/cards/due/",
        "desc": "今日到期与逾期的闪卡",
        "params": "无",
    },
    {
        "method": "GET",
        "path": "/api/v1/sessions/",
        "desc": "学习计时记录",
        "params": "limit=30",
    },
    {
        "method": "GET",
        "path": "/api/v1/stats/",
        "desc": "连续天数、时长、主题排行等统计",
        "params": "无",
    },
    {
        "method": "POST",
        "path": "/api/v1/entries/create/",
        "desc": "快速写入一条笔记（可自动建主题）",
        "params": "text=内容&topic=主题ID 或 topic_name=主题名",
    },
]


API_ENDPOINTS_V2 = [
    {
        "method": "GET",
        "path": "/api/v2/topics/",
        "desc": "主题列表，分页 + 搜索 + 排序",
        "params": "search=&ordering=-date_added&page=1",
    },
    {
        "method": "GET",
        "path": "/api/v2/entries/",
        "desc": "笔记列表，支持主题与关键词过滤",
        "params": "topic=主题ID&q=关键词&page=1",
    },
    {
        "method": "POST",
        "path": "/api/v2/entries/",
        "desc": "新建笔记，需要 topic 或 topic_name",
        "params": "JSON: {text, topic}",
    },
    {
        "method": "GET",
        "path": "/api/v2/cards/",
        "desc": "闪卡列表，due=1 只看到期",
        "params": "due=1",
    },
    {
        "method": "GET",
        "path": "/api/v2/sessions/",
        "desc": "学习会话列表",
        "params": "page=1",
    },
    {
        "method": "GET",
        "path": "/api/v2/events/",
        "desc": "学习事件流",
        "params": "ordering=-created_at",
    },
    {
        "method": "GET",
        "path": "/api/v2/stats/",
        "desc": "统计概览与主题排行",
        "params": "无",
    },
    {
        "method": "GET",
        "path": "/api/v2/schema/",
        "desc": "OpenAPI 3 文档",
        "params": "无",
    },
]


@login_required
def api_tokens(request):
    """个人 API 令牌管理：签发、吊销与用法示例。"""
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "revoke":
            token_id = request.POST.get("token_id")
            updated = ApiToken.objects.filter(id=token_id, user=request.user).update(
                revoked=True
            )
            messages.success(request, "令牌已吊销。" if updated else "令牌不存在。")
        else:
            name = (request.POST.get("name") or "默认令牌").strip()[:60]
            record = ApiToken.issue(request.user, name)
            request.session["new_api_token"] = record.token
            messages.success(request, f"已签发令牌「{record.name}」，请立即复制保存。")
        return redirect("learning_logs:api_tokens")

    new_token = request.session.pop("new_api_token", None)
    return render(
        request,
        "learning_logs/api_tokens.html",
        {
            "tokens": ApiToken.objects.filter(user=request.user),
            "new_token": new_token,
            "endpoints": API_ENDPOINTS,
            "endpoints_v2": API_ENDPOINTS_V2,
        },
    )


@login_required
def api_docs(request):
    """开放 API 文档页。"""
    return render(
        request,
        "learning_logs/api_docs.html",
        {"endpoints": API_ENDPOINTS, "token_count": ApiToken.objects.filter(user=request.user, revoked=False).count()},
    )
