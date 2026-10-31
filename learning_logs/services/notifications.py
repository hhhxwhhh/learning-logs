"""站内提醒：按当前学习状态生成，同一条提醒不会重复堆积。

生成策略是「惰性 + 幂等」：每次访问时检查当天是否已经生成过同类提醒，
没有才写入，避免刷新页面导致提醒爆炸。
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from learning_logs.models import (
    Entry,
    Flashcard,
    LearningGoal,
    Notification,
    Topic,
    WeeklyReport,
)

MAX_KEEP = 40


def _exists_today(user, kind: str) -> bool:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return Notification.objects.filter(
        user=user, kind=kind, created_at__gte=start
    ).exists()


def _create(user, kind: str, title: str, body: str = "", link: str = "") -> bool:
    if _exists_today(user, kind):
        return False
    Notification.objects.create(user=user, kind=kind, title=title, body=body, link=link)
    return True


def generate(user) -> int:
    """扫描学习状态，写入需要的提醒，返回本次新增条数。"""
    today = timezone.localdate()
    created = 0

    due = Flashcard.objects.filter(user=user, due_date__lte=today).count()
    if due:
        created += _create(
            user,
            Notification.KIND_DUE,
            f"今天有 {due} 张闪卡到期",
            "间隔重复到期了，趁还记得先过一遍。",
            "/flashcards/review/",
        )

    has_history = Entry.objects.filter(topic__owner=user).exists()
    today_entry = Entry.objects.filter(
        topic__owner=user, date_added__date=today
    ).exists()
    if has_history and not today_entry:
        created += _create(
            user,
            Notification.KIND_STREAK,
            "今天还没有留下学习痕迹",
            "写一条笔记或开一次专注，连续天数就能延续。",
            "/today/",
        )

    week_start = today - timedelta(days=today.weekday())
    has_report = WeeklyReport.objects.filter(
        user=user, week_start__gte=week_start
    ).exists()
    if has_history and not has_report:
        created += _create(
            user,
            Notification.KIND_WEEKLY,
            "本周的学习周报还没生成",
            "花一分钟让 AI 帮你复盘这一周。",
            "/weekly/",
        )

    soon = LearningGoal.objects.filter(
        user=user,
        completed=False,
        target_date__gte=today,
        target_date__lte=today + timedelta(days=3),
    ).first()
    if soon:
        days = (soon.target_date - today).days
        created += _create(
            user,
            Notification.KIND_GOAL,
            f"目标「{soon.title}」还有 {days} 天到期",
            soon.description[:120],
            "/goals/",
        )

    idle_topic = (
        Topic.objects.filter(owner=user)
        .filter(Q(entry__isnull=False))
        .order_by("date_added")
        .first()
    )
    if idle_topic:
        last = idle_topic.entry_set.order_by("-date_added").first()
        if last and (today - timezone.localdate(last.date_added)).days >= 30:
            days = (today - timezone.localdate(last.date_added)).days
            created += _create(
                user,
                Notification.KIND_IDLE,
                f"主题「{idle_topic.text}」已搁置 {days} 天",
                "回去补一条笔记，或者干脆归档它。",
                f"/topic/{idle_topic.id}",
            )

    prune(user)
    return created


def prune(user, keep: int = MAX_KEEP) -> int:
    """只保留最近若干条提醒，避免表无限增长。"""
    stale = Notification.objects.filter(user=user).order_by("-created_at")[keep:]
    ids = [item.id for item in stale]
    if ids:
        Notification.objects.filter(id__in=ids).delete()
    return len(ids)


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def recent(user, limit: int = 8):
    return Notification.objects.filter(user=user).order_by("-created_at")[:limit]


def mark_all_read(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).update(
        read_at=timezone.now()
    )
