"""成就系统：根据学习数据计算徽章解锁状态。

不建额外数据表：所有成就都由现有数据推导，改规则不需要迁移。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db.models import Count, Max
from django.utils import timezone

from learning_logs.models import Entry, Flashcard, LearningPath, StudySession, Topic

from . import stats


@dataclass
class Badge:
    key: str
    name: str
    description: str
    icon: str
    target: int
    current: int
    unit: str
    achieved_at: datetime | None = None

    @property
    def unlocked(self) -> bool:
        return self.current >= self.target

    @property
    def progress(self) -> int:
        if self.target <= 0:
            return 100
        return min(100, round(self.current / self.target * 100))


def _nth_entry(entries, index: int):
    row = entries.order_by("date_added").values_list("date_added", flat=True)[index - 1 : index]
    return row[0] if row else None


def collect(user) -> dict:
    entries = Entry.objects.filter(topic__owner=user)
    total = entries.count()
    completed = entries.filter(completed=True).count()

    topic_max = (
        Topic.objects.filter(owner=user)
        .annotate(count=Count("entry"))
        .aggregate(value=Max("count"))["value"]
        or 0
    )
    deep_topic = (
        Topic.objects.filter(owner=user)
        .annotate(count=Count("entry"))
        .order_by("-count")
        .first()
    )

    streak = stats.current_streak(user)
    night_sessions = sum(
        1
        for start_time in StudySession.objects.filter(user=user).values_list(
            "start_time", flat=True
        )
        if timezone.localtime(start_time).hour >= 22
    )
    reviews = sum(
        Flashcard.objects.filter(user=user).values_list("repetitions", flat=True)
    )
    paths_done = LearningPath.objects.filter(user=user, is_completed=True).count()
    forest_entries = total

    deep_achieved = None
    if deep_topic and deep_topic.count >= 20:
        deep_achieved = _nth_entry(deep_topic.entry_set, 20)

    badges = [
        Badge("first_entry", "第一片叶子", "写下第一条学习笔记", "i-sprout", 1, total, "条",
              _nth_entry(entries, 1)),
        Badge("entries_10", "十步有痕", "累计写下 10 条笔记", "i-doc", 10, total, "条",
              _nth_entry(entries, 10)),
        Badge("entries_50", "半百积累", "累计写下 50 条笔记", "i-layers", 50, total, "条",
              _nth_entry(entries, 50)),
        Badge("entries_100", "百篇笔记", "累计写下 100 条笔记", "i-book", 100, total, "条",
              _nth_entry(entries, 100)),
        Badge("deep_topic", "深耕一处", "单个主题累计 20 条笔记", "i-target", 20, topic_max, "条",
              deep_achieved),
        Badge("completed_20", "收口能力", "标记 20 条笔记为已掌握", "i-check", 20, completed, "条",
              None),
        Badge("streak_7", "七日之约", "连续学习 7 天", "i-flame", 7, streak, "天", None),
        Badge("streak_30", "月不辍", "连续学习 30 天", "i-flame", 30, streak, "天", None),
        Badge("path_done", "路径行者", "完成一条学习路径", "i-route", 1, paths_done, "条", None),
        Badge("review_50", "记忆工匠", "累计复习闪卡 50 次", "i-cards", 50, reviews, "次", None),
        Badge("forest", "长成森林", "笔记达到 45 条，进入森林阶段", "i-sprout", 45, forest_entries, "条",
              _nth_entry(entries, 45)),
        Badge("night_owl", "深夜书桌", "在 22 点后开始学习 5 次", "i-clock", 5,
              night_sessions, "次", None),
    ]

    unlocked = [badge for badge in badges if badge.unlocked]
    locked = [badge for badge in badges if not badge.unlocked]
    # 未解锁的按完成度倒序，让"差一点"的排在前面
    locked.sort(key=lambda badge: badge.progress, reverse=True)

    return {
        "badges": unlocked + locked,
        "unlocked_count": len(unlocked),
        "total_count": len(badges),
        "completion": round(len(unlocked) / len(badges) * 100),
        "next_up": locked[:3],
    }
