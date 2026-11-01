"""仪表盘、学习目标、会话计时、今日速览与专注。"""

from __future__ import annotations

import logging

import random
from datetime import datetime, time, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from ..models import Entry, Flashcard, LearningGoal, LearningPath, StudySession, Topic
from .. import events
from ..services import cache as cache_service
from ..services import stats
from ..services import todos as todos_service

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    """学习仪表盘：指标、热力图、趋势与待办。"""
    overview = stats.overview(request.user)

    weekly = stats.weekly_totals(request.user, weeks=8)

    context = {
        "overview": overview,
        "heatmap": stats.heatmap_weeks(request.user),
        "weekly": weekly,
        "topic_ranking": stats.topic_ranking(request.user),
        "recent_entries": Entry.objects.filter(topic__owner=request.user)
        .select_related("topic")
        .order_by("-date_added")[:5],
        "goals": stats.upcoming_goals(request.user),
        "paths": LearningPath.objects.filter(user=request.user).order_by("-updated_at")[:3],
        "format_minutes": stats.format_minutes,
    }
    return render(request, "learning_logs/dashboard.html", context)


@login_required
def goals(request):
    """管理学习目标"""
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        target_date = stats.parse_date(request.POST.get("target_date", ""))

        if not title:
            messages.error(request, "目标名称不能为空。")
        elif target_date is None:
            messages.error(request, "请选择合法的截止日期。")
        else:
            LearningGoal.objects.create(
                user=request.user,
                title=title,
                description=description,
                target_date=target_date,
            )
            messages.success(request, "目标已添加，记得给它留出时间。")
            return redirect("learning_logs:goals")

    return render(
        request,
        "learning_logs/goals.html",
        {"goals": LearningGoal.objects.filter(user=request.user).order_by("completed", "target_date")},
    )


@login_required
@require_POST
def toggle_goal(request, goal_id):
    """切换目标完成状态"""
    goal = get_object_or_404(LearningGoal, id=goal_id, user=request.user)
    goal.completed = not goal.completed
    goal.save()
    return redirect('learning_logs:goals')


@login_required
@require_POST
def start_session(request, topic_id):
    """开始一个学习会话"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    
    # 创建一个新会话
    session = StudySession.objects.create(
        user=request.user,
        topic=topic,
        start_time=timezone.now(),
        end_time=timezone.now()  # 将在结束时更新
    )
    
    request.session['active_session_id'] = session.id
    return redirect('learning_logs:topic', topic_id=topic.id)


@login_required
@require_POST
def end_session(request):
    """结束当前学习会话"""
    session_id = request.session.get('active_session_id')
    if session_id:
        try:
            session = StudySession.objects.get(id=session_id, user=request.user)
            session.end_time = timezone.now()
            session.save()  # 这将触发 save 方法计算 duration
            del request.session['active_session_id']
            
            # 提供反馈消息
            messages.success(request, f"学习会话已结束，持续了 {session.duration}")
        except StudySession.DoesNotExist:
            messages.error(request, "找不到活动的学习会话")
    
    return redirect('learning_logs:dashboard')


@login_required
def today(request):
    """今日速览：把今天该做的事和值得回看的旧笔记聚到一页。"""
    user = request.user
    today_date = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today_date, time.min))

    entries_today = Entry.objects.filter(topic__owner=user, date_added__gte=start)
    sessions_today = StudySession.objects.filter(
        user=user, start_time__gte=start, duration__isnull=False
    )
    minutes_today = sum(
        session.duration_minutes() for session in sessions_today
    )
    due_cards = Flashcard.objects.filter(user=user, due_date__lte=today_date)

    old_entries = list(
        Entry.objects.filter(topic__owner=user, date_added__lt=start - timedelta(days=30))
        .select_related("topic")
        .order_by("-date_added")[:60]
    )
    random.shuffle(old_entries)

    context = {
        "today": today_date,
        "entry_count_today": entries_today.count(),
        "minutes_today": minutes_today,
        "minutes_text": stats.format_minutes(minutes_today),
        "streak": stats.current_streak(user),
        "due_cards": due_cards[:5],
        "due_count": due_cards.count(),
        "flashbacks": old_entries[:3],
        "recent_topics": Topic.objects.filter(owner=user).order_by("-date_added")[:5],
        "goals": stats.upcoming_goals(user, limit=3),
        "week_minutes": stats.range_minutes(user, 7),
        "open_todos": todos_service.scan(user, only_open=True)[:5],
        "open_todo_count": todos_service.summarize(todos_service.scan(user))["open"],
    }
    return render(request, "learning_logs/today.html", context)


@login_required
def focus(request):
    """专注计时（番茄钟）页面。"""
    sessions = StudySession.objects.filter(
        user=request.user, duration__isnull=False
    ).select_related("topic")[:8]
    today_date = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today_date, time.min))
    return render(
        request,
        "learning_logs/focus.html",
        {
            "topics": Topic.objects.filter(owner=request.user),
            "sessions": sessions,
            "minutes_today": sum(
                s.duration_minutes()
                for s in StudySession.objects.filter(
                    user=request.user, start_time__gte=start, duration__isnull=False
                )
            ),
            "today": today_date,
        },
    )


@login_required
@require_POST
def focus_log(request):
    """专注结束后写入一次学习会话。"""
    minutes = request.POST.get("minutes") or "0"
    try:
        minutes = max(0, min(600, int(float(minutes))))
    except (TypeError, ValueError):
        minutes = 0
    topic_id = request.POST.get("topic")
    topic = Topic.objects.filter(id=topic_id, owner=request.user).first()

    if minutes <= 0:
        return JsonResponse({"ok": False, "error": "时长太短，未记录。"}, status=400)
    if topic is None:
        return JsonResponse({"ok": False, "error": "请先选择一个主题。"}, status=400)

    end = timezone.now()
    StudySession.objects.create(
        user=request.user, topic=topic, start_time=end - timedelta(minutes=minutes), end_time=end
    )
    events.publish(
        "session_ended",
        request.user,
        f"专注了 {minutes} 分钟：{topic.text}",
        topic=topic,
        payload={"minutes": minutes},
    )
    cache_service.invalidate(request.user.id)
    return JsonResponse(
        {
            "ok": True,
            "minutes": minutes,
            "topic": topic.text,
            "message": f"已记录 {minutes} 分钟专注：{topic.text}",
        }
    )
