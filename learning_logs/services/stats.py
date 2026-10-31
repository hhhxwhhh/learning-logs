"""学习统计服务：把散落在会话、条目里的数据整理成可直接渲染的结构。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from learning_logs.models import (
    Entry,
    Flashcard,
    LearningGoal,
    LearningPath,
    StudySession,
    Topic,
)


def _local_date(value):
    """把 aware datetime 转成当前时区下的日期。"""
    return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()


def daily_minutes(user, days: int = 119) -> dict[date, int]:
    """返回「日期 → 学习分钟数」，包含条目创建日（按 5 分钟折算）与会话时长。"""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    totals: dict[date, int] = defaultdict(int)

    sessions = StudySession.objects.filter(
        user=user,
        start_time__date__gte=start,
    ).values_list("start_time", "duration")
    for start_time, duration in sessions:
        if duration:
            totals[_local_date(start_time)] += int(duration.total_seconds() // 60)

    # 写笔记也是学习行为：每条按 5 分钟计，避免「只记笔记不计时」的空白
    entry_days = (
        Entry.objects.filter(topic__owner=user, date_added__date__gte=start)
        .values_list("date_added", flat=True)
    )
    for created_at in entry_days:
        totals[_local_date(created_at)] += 5

    return dict(totals)


def _level(minutes: int) -> int:
    if minutes <= 0:
        return 0
    if minutes < 20:
        return 1
    if minutes < 45:
        return 2
    if minutes < 90:
        return 3
    return 4


def heatmap_weeks(user, weeks: int = 17) -> list[list[dict]]:
    """生成 GitHub 风格热力图数据：固定 weeks 列，每列周一到周日。"""
    weeks = max(1, weeks)
    today = timezone.localdate()
    end = today + timedelta(days=6 - today.weekday())  # 本周周日
    start = end - timedelta(days=weeks * 7 - 1)
    totals = daily_minutes(user, days=(today - start).days + 1)

    result: list[list[dict]] = []
    cursor = start
    for _ in range(weeks):
        week = []
        for _ in range(7):
            if cursor > today:
                week.append({"date": cursor, "level": -1, "minutes": 0})
            else:
                minutes = totals.get(cursor, 0)
                week.append({"date": cursor, "level": _level(minutes), "minutes": minutes})
            cursor += timedelta(days=1)
        result.append(week)
    return result


def current_streak(user) -> int:
    """当前连续学习天数（今天没学则从昨天起算，仍算连续）。"""
    totals = daily_minutes(user, days=400)
    if not totals:
        return 0

    today = timezone.localdate()
    cursor = today if totals.get(today) else today - timedelta(days=1)
    streak = 0
    while totals.get(cursor):
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def range_minutes(user, days: int) -> int:
    """最近 N 天学习分钟数。"""
    return sum(daily_minutes(user, days=days).values())


def weekly_series(user, weeks: int = 8) -> list[dict]:
    """最近 N 周的每日分钟数与周汇总，用于纯 CSS 柱状图。"""
    today = timezone.localdate()
    start = today - timedelta(days=weeks * 7 - 1)
    totals = daily_minutes(user, days=(today - start).days + 1)

    series = []
    for offset in range(weeks * 7):
        day = start + timedelta(days=offset)
        series.append({"date": day, "minutes": totals.get(day, 0)})
    return series


def weekly_totals(user, weeks: int = 8) -> list[dict]:
    """按周聚合学习分钟数，用于柱状图（每周一根柱子，避免空白天数干扰）。"""
    weeks = max(1, weeks)
    today = timezone.localdate()
    end = today + timedelta(days=6 - today.weekday())
    start = end - timedelta(days=weeks * 7 - 1)
    totals = daily_minutes(user, days=(today - start).days + 1)

    rows = []
    cursor = start
    for _ in range(weeks):
        minutes = sum(totals.get(cursor + timedelta(days=i), 0) for i in range(7))
        rows.append(
            {
                "start": cursor,
                "end": cursor + timedelta(days=6),
                "minutes": minutes,
            }
        )
        cursor += timedelta(days=7)

    peak = max([row["minutes"] for row in rows] + [1])
    for row in rows:
        row["pct"] = max(6, round(row["minutes"] / peak * 100)) if row["minutes"] else 6
    return rows


def hour_distribution(user) -> list[dict]:
    """一天 24 小时的学习时长分布（分钟）。"""
    buckets = defaultdict(int)
    for start_time, duration in StudySession.objects.filter(user=user).values_list(
        "start_time", "duration"
    ):
        if duration:
            hour = timezone.localtime(start_time).hour
            buckets[hour] += int(duration.total_seconds() // 60)
    return [{"hour": hour, "minutes": buckets.get(hour, 0)} for hour in range(24)]


def overview(user) -> dict:
    """仪表盘顶部指标。"""
    topics = Topic.objects.filter(owner=user)
    entries = Entry.objects.filter(topic__owner=user)
    total_minutes = sum(daily_minutes(user, days=3650).values())

    return {
        "topic_count": topics.count(),
        "entry_count": entries.count(),
        "completed_entries": entries.filter(completed=True).count(),
        "total_minutes": total_minutes,
        "week_minutes": range_minutes(user, 7),
        "month_minutes": range_minutes(user, 30),
        "streak": current_streak(user),
        "active_goals": LearningGoal.objects.filter(user=user, completed=False).count(),
        "active_paths": LearningPath.objects.filter(user=user, is_completed=False).count(),
        "due_cards": Flashcard.objects.filter(
            user=user, due_date__lte=timezone.localdate()
        ).count(),
    }


def topic_ranking(user, limit: int = 6) -> list[dict]:
    """按学习记录数量给主题排序，附带完成度。"""
    topics = (
        Topic.objects.filter(owner=user)
        .annotate(entry_count=Count("entry"))
        .order_by("-entry_count", "-date_added")[:limit]
    )
    return [
        {
            "topic": topic,
            "entry_count": topic.entry_count,
            "progress": topic.progress_percentage(),
        }
        for topic in topics
    ]


def upcoming_goals(user, limit: int = 4):
    today = timezone.localdate()
    return LearningGoal.objects.filter(
        user=user, completed=False, target_date__gte=today
    ).order_by("target_date")[:limit]


def format_minutes(minutes: int) -> str:
    """分钟数转「X 小时 Y 分」。"""
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours} 小时 {mins} 分"
    if hours:
        return f"{hours} 小时"
    return f"{mins} 分钟"


def parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def ensure_day_bounds(day: date) -> tuple[datetime, datetime]:
    """把本地日期转成带时区的起止时间。"""
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)
