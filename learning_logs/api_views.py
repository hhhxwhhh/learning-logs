"""开放 API 视图：只读为主，供脚本、笔记工具与自动化使用。

所有接口都要求 Bearer 令牌，且只返回令牌所属用户的数据。
"""

from __future__ import annotations

import logging

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Entry, Flashcard, StudySession, Topic
from .services import api_access, stats

logger = logging.getLogger(__name__)


def _json(payload: dict, status: int = 200) -> JsonResponse:
    response = JsonResponse(
        payload, status=status, json_dumps_params={"ensure_ascii": False}
    )
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _error(message: str, status: int) -> JsonResponse:
    return _json({"ok": False, "error": message}, status=status)


def _guard(request):
    """统一鉴权入口，返回 (token, error_response)。"""
    try:
        return api_access.authenticate(request), None
    except api_access.ApiError as exc:
        return None, _error(exc.message, exc.status)


@csrf_exempt
def options(request):
    return _json({"ok": True})


@require_GET
def me(request):
    """当前令牌对应的账号与概览。"""
    token, error = _guard(request)
    if error:
        return error
    user = token.user
    overview = stats.overview(user)
    return _json(
        {
            "ok": True,
            "user": {"username": user.username, "joined": user.date_joined.isoformat()},
            "overview": overview,
        }
    )


@require_GET
def topics(request):
    token, error = _guard(request)
    if error:
        return error
    rows = Topic.objects.filter(owner=token.user).prefetch_related("entry_set")
    return _json(
        {
            "ok": True,
            "count": rows.count(),
            "results": [api_access.serialize_topic(topic) for topic in rows],
        }
    )


@require_GET
def entries(request):
    token, error = _guard(request)
    if error:
        return error

    limit = _int_param(request, "limit", 50, minimum=1, maximum=200)
    query = (request.GET.get("q") or "").strip()
    rows = Entry.objects.filter(topic__owner=token.user).select_related("topic")
    topic_id = request.GET.get("topic")
    if str(topic_id or "").isdigit():
        rows = rows.filter(topic_id=int(topic_id))
    if query:
        rows = rows.filter(text__icontains=query)

    return _json(
        {
            "ok": True,
            "count": rows.count(),
            "results": [api_access.serialize_entry(entry) for entry in rows[:limit]],
        }
    )


@require_GET
def due_cards(request):
    """今日到期（含逾期）的闪卡，适合做每日推送。"""
    token, error = _guard(request)
    if error:
        return error
    rows = Flashcard.objects.filter(
        user=token.user, due_date__lte=timezone.localdate()
    ).select_related("topic")
    return _json(
        {
            "ok": True,
            "count": rows.count(),
            "results": [api_access.serialize_card(card) for card in rows],
        }
    )


@require_GET
def sessions(request):
    token, error = _guard(request)
    if error:
        return error
    limit = _int_param(request, "limit", 30, minimum=1, maximum=200)
    rows = StudySession.objects.filter(
        user=token.user, duration__isnull=False
    ).select_related("topic")
    return _json(
        {
            "ok": True,
            "count": rows.count(),
            "results": [api_access.serialize_session(s) for s in rows[:limit]],
        }
    )


@require_GET
def stats_view(request):
    token, error = _guard(request)
    if error:
        return error
    user = token.user
    ranking = [
        {
            "topic": row["topic"].text,
            "entry_count": row["entry_count"],
            "progress": row["progress"],
        }
        for row in stats.topic_ranking(user)
    ]
    return _json(
        {
            "ok": True,
            "overview": stats.overview(user),
            "streak": stats.current_streak(user),
            "week_minutes": stats.range_minutes(user, 7),
            "topic_ranking": ranking,
            "heatmap_weeks": len(stats.heatmap_weeks(user)),
        }
    )


@require_POST
@csrf_exempt
def quick_entry(request):
    """快速写一条笔记：POST /api/v1/entries/create/"""
    token, error = _guard(request)
    if error:
        return error

    text = (request.POST.get("text") or "").strip()
    topic_id = request.POST.get("topic")
    topic_name = (request.POST.get("topic_name") or "").strip()

    if not text:
        return _error("text 不能为空。", 400)

    topic = None
    if str(topic_id or "").isdigit():
        topic = Topic.objects.filter(id=int(topic_id), owner=token.user).first()
    if topic is None and topic_name:
        topic, _ = Topic.objects.get_or_create(text=topic_name[:200], owner=token.user)
    if topic is None:
        return _error("需要 topic 或 topic_name 指定归属主题。", 400)

    entry = Entry.objects.create(topic=topic, text=text)
    return _json({"ok": True, "entry": api_access.serialize_entry(entry)}, status=201)


def _int_param(request, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.GET.get(name)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))
