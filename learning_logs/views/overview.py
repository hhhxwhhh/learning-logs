"""活动流、学习洞察、实时看板、成就、花园与时间线。"""

from __future__ import annotations

import logging

from datetime import datetime, time, timedelta
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone
from ..models import Entry, EventLog, Flashcard, StudySession
from ..services import achievements as achievements_service
from ..services import garden as garden_service
from ..services import insights as insights_service
from ..services import timeline as timeline_service
from ..services import todos as todos_service

logger = logging.getLogger(__name__)

@login_required
def activity(request):
    """活动流：最近发生过哪些学习动作。"""
    kind = (request.GET.get("kind") or "").strip()
    queryset = EventLog.objects.filter(user=request.user).select_related("topic")
    if kind:
        queryset = queryset.filter(kind=kind)

    counts = {
        row["kind"]: row["total"]
        for row in queryset.values("kind").annotate(total=Count("id"))
    }
    size = getattr(settings, "ACTIVITY_FEED_SIZE", 60)
    items = list(queryset[:size])

    groups = []
    for item in items:
        day = timezone.localtime(item.created_at).date()
        if not groups or groups[-1]["day"] != day:
            groups.append({"day": day, "items": []})
        groups[-1]["items"].append(item)

    return render(
        request,
        "learning_logs/activity.html",
        {
            "groups": groups,
            "kind": kind,
            "counts": counts,
            "total": sum(counts.values()),
            "kinds": EventLog.KIND_CHOICES,
        },
    )


@login_required
def insights(request):
    """学习洞察：把统计数据翻译成结论与下一步行动。"""
    return render(
        request,
        "learning_logs/insights.html",
        insights_service.build(request.user),
    )


@login_required
def live_board(request):
    """实时看板：首屏数据由服务端给，之后走 WebSocket 增量更新。"""
    today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today, time.min))

    entries_today = Entry.objects.filter(
        topic__owner=request.user, date_added__gte=start
    ).count()
    sessions = StudySession.objects.filter(
        user=request.user, start_time__gte=start, duration__isnull=False
    )
    minutes = sum(session.duration_minutes() for session in sessions)
    due_cards = Flashcard.objects.filter(
        user=request.user, due_date__lte=today
    ).count()
    open_todos = todos_service.summarize(todos_service.scan(request.user))["open"]

    recent = EventLog.objects.filter(user=request.user).select_related("topic")[:20]

    # 近 7 天每日笔记数，用于看板上的迷你趋势图
    week_start = today - timedelta(days=6)
    day_counts = (
        Entry.objects.filter(
            topic__owner=request.user, date_added__gte=week_start
        )
        .values("date_added__date")
        .annotate(total=Count("id"))
        .order_by("date_added__date")
    )
    by_day = {row["date_added__date"]: row["total"] for row in day_counts}
    series = [
        {"date": (week_start + timedelta(days=offset)).isoformat(),
         "count": by_day.get(week_start + timedelta(days=offset), 0)}
        for offset in range(7)
    ]

    initial = {
        "metrics": {
            "entries": entries_today,
            "minutes": minutes,
            "cards": due_cards,
            "todos": open_todos,
        },
        "series": series,
        "events": [
            {
                "event_id": item.event_id,
                "kind": item.kind,
                "label": item.label,
                "summary": item.summary,
                "topic": item.topic.text if item.topic else "",
                "created_at": item.created_at.isoformat(),
            }
            for item in recent
        ],    }

    return render(
        request,
        "learning_logs/live.html",
        {"initial": initial, "ws_url": "/ws/live/"},
    )


@login_required
def achievements(request):
    """学习成就：徽章解锁情况。"""
    return render(
        request,
        "learning_logs/achievements.html",
        achievements_service.collect(request.user),
    )


@login_required
def garden(request):
    """学习花园：把主题与笔记可视化成一棵树。"""
    return render(request, "learning_logs/garden.html", garden_service.garden_context(request.user))


@login_required
def timeline(request):
    """学习时间线：按月回看自己的学习轨迹。"""
    try:
        months = max(3, min(36, int(request.GET.get("months", "12"))))
    except (TypeError, ValueError):
        months = 12
    return render(
        request,
        "learning_logs/timeline.html",
        timeline_service.build(request.user, months=months),
    )
