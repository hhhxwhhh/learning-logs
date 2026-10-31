"""学习分析：把学习行为整理成可读的图表与洞察。"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from learning_logs.models import Entry, LearningGoal, StudySession, Topic
from learning_logs.services import stats

from .models import AnalyticsPreferences, LearningInsight, TopicAnalytics


def _preferences(user):
    preferences, _ = AnalyticsPreferences.objects.get_or_create(user=user)
    return preferences


def _insights(user, overview):
    """基于真实数据即时生成洞察，而不是写死文案。"""
    items = []
    week = overview["week_minutes"]
    last_week = stats.range_minutes(user, 14) - week

    if week == 0:
        items.append(
            {
                "type": "recommendation",
                "title": "这周还没有开始",
                "message": "从一条 3 分钟的笔记开始，比重读旧笔记有效得多。",
            }
        )
    elif last_week and week > last_week:
        items.append(
            {
                "type": "productivity",
                "title": f"本周比上周多投入 {round((week - last_week) / last_week * 100)}%",
                "message": f"本周 {stats.format_minutes(week)}，上周 {stats.format_minutes(last_week)}，保持节奏。",
            }
        )
    elif last_week:
        items.append(
            {
                "type": "productivity",
                "title": "本周投入低于上周",
                "message": f"本周 {stats.format_minutes(week)}，上周 {stats.format_minutes(last_week)}，可以安排一次 25 分钟专注。",
            }
        )

    if overview["streak"] >= 3:
        items.append(
            {
                "type": "streak",
                "title": f"已经连续 {overview['streak']} 天",
                "message": "连续记录正在形成习惯，今天再写一条就能延续。",
            }
        )

    hours = [row for row in stats.hour_distribution(user) if row["minutes"] > 0]
    if hours:
        best = max(hours, key=lambda row: row["minutes"])
        items.append(
            {
                "type": "pattern",
                "title": f"你最高效的时段是 {best['hour']}:00 - {best['hour'] + 1}:00",
                "message": f"这个时段累计投入 {stats.format_minutes(best['minutes'])}，可以把最难的内容安排在这里。",
            }
        )

    pending_goals = LearningGoal.objects.filter(user=user, completed=False)
    overdue = [g for g in pending_goals if g.is_overdue()]
    if overdue:
        items.append(
            {
                "type": "achievement",
                "title": f"有 {len(overdue)} 个目标已过期",
                "message": "要么重新设定日期，要么把它拆成更小的第一步。",
            }
        )

    return items


@login_required
def dashboard(request):
    """分析总览页。"""
    overview = stats.overview(request.user)
    weekly = stats.weekly_totals(request.user, weeks=12)

    hourly = stats.hour_distribution(request.user)
    hour_peak = max([row["minutes"] for row in hourly] + [1])
    for row in hourly:
        row["pct"] = round(row["minutes"] / hour_peak * 100) if row["minutes"] else 0

    context = {
        "overview": overview,
        "weekly": weekly,
        "hourly": hourly,
        "topic_ranking": stats.topic_ranking(request.user, limit=8),
        "insights": _insights(request.user, overview),
        "saved_insights": LearningInsight.objects.filter(user=request.user)[:3],
        "preferences": _preferences(request.user),
        "recent_sessions": StudySession.objects.filter(user=request.user).select_related("topic")[:6],
    }
    return render(request, "analytics/dashboard.html", context)


@login_required
def study_statistics(request):
    """学习时间统计。"""
    overview = stats.overview(request.user)
    weekly = stats.weekly_totals(request.user, weeks=12)

    hourly = stats.hour_distribution(request.user)
    hour_peak = max([row["minutes"] for row in hourly] + [1])
    for row in hourly:
        row["pct"] = round(row["minutes"] / hour_peak * 100) if row["minutes"] else 0

    sessions = StudySession.objects.filter(user=request.user).select_related("topic")
    finished = [s for s in sessions if s.duration]
    avg_minutes = (
        round(sum(s.duration.total_seconds() for s in finished) / len(finished) / 60)
        if finished
        else 0
    )

    context = {
        "overview": overview,
        "weekly": weekly,
        "hourly": hourly,
        "avg_minutes": avg_minutes,
        "recent_sessions": sessions[:12],
        "heatmap": stats.heatmap_weeks(request.user),
    }
    return render(request, "analytics/study_statistics.html", context)


@login_required
def progress_report(request):
    """进度报告：主题完成度与目标达成。"""
    topics = (
        Topic.objects.filter(owner=request.user)
        .annotate(entry_count=Count("entry"))
        .order_by("-date_added")
    )
    topics_data = [
        {"topic": topic, "progress": topic.progress_percentage(), "entry_count": topic.entry_count}
        for topic in topics
    ]

    goals = LearningGoal.objects.filter(user=request.user)
    total_goals = goals.count()
    completed = goals.filter(completed=True).count()

    month_start = timezone.localdate() - timedelta(days=30)
    entries_recent = Entry.objects.filter(
        topic__owner=request.user, date_added__date__gte=month_start
    ).count()

    context = {
        "overview": stats.overview(request.user),
        "topics_data": topics_data,
        "goals": goals,
        "total_goals": total_goals,
        "completed_goals": completed,
        "goal_rate": round(completed / total_goals * 100) if total_goals else 0,
        "entries_recent": entries_recent,
    }
    return render(request, "analytics/progress_report.html", context)


@login_required
def topic_analysis(request, topic_id):
    """单个主题的学习分析。"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    analytics, _ = TopicAnalytics.objects.get_or_create(topic=topic)

    sessions = StudySession.objects.filter(user=request.user, topic=topic)
    entries = Entry.objects.filter(topic=topic).order_by("-date_added")

    minutes_by_day = stats.daily_minutes(request.user, days=56)
    series = []
    today = timezone.localdate()
    for offset in range(55, -1, -1):
        day = today - timedelta(days=offset)
        series.append({"date": day, "minutes": minutes_by_day.get(day, 0)})
    peak = max([row["minutes"] for row in series] + [1])
    for row in series:
        row["pct"] = max(4, round(row["minutes"] / peak * 100)) if row["minutes"] else 4

    topic_minutes = sum(
        int(s.duration.total_seconds() // 60) for s in sessions if s.duration
    )

    context = {
        "topic": topic,
        "analytics": analytics,
        "sessions": sessions[:10],
        "entries": entries,
        "series": series,
        "topic_minutes": topic_minutes,
        "session_count": sessions.count(),
        "entry_count": entries.count(),
        "completed_entries": entries.filter(completed=True).count(),
    }
    return render(request, "analytics/topic_analysis.html", context)


@login_required
@require_POST
def update_preferences(request):
    """保存分析页偏好。"""
    preferences = _preferences(request.user)
    preferences.show_study_time = request.POST.get("show_study_time") == "on"
    preferences.show_topic_progress = request.POST.get("show_topic_progress") == "on"
    preferences.show_goal_progress = request.POST.get("show_goal_progress") == "on"
    preferences.chart_color_theme = request.POST.get("chart_color_theme", "default")
    preferences.dashboard_layout = request.POST.get("dashboard_layout", "grid")
    preferences.save()
    messages.success(request, "分析偏好已更新。")
    return redirect("analytics:dashboard")
