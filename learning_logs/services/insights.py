"""学习洞察：用规则引擎把统计数据翻译成人话与下一步行动。

不依赖任何模型：全部由本地数据推导，AI 不可用也能给出有价值的建议。
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from learning_logs.models import Entry, Flashcard, StudySession, Topic

from .cache import cached

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _best_hour(user) -> dict | None:
    buckets = {}
    for start_time, duration in StudySession.objects.filter(
        user=user, duration__isnull=False
    ).values_list("start_time", "duration"):
        hour = timezone.localtime(start_time).hour
        buckets[hour] = buckets.get(hour, 0) + int(duration.total_seconds() // 60)
    if not buckets:
        return None
    hour = max(buckets.items(), key=lambda item: item[1])[0]
    return {"hour": hour, "minutes": buckets[hour]}


def _best_weekday(user) -> dict | None:
    buckets = {}
    for start_time, duration in StudySession.objects.filter(
        user=user, duration__isnull=False
    ).values_list("start_time", "duration"):
        weekday = timezone.localtime(start_time).weekday()
        buckets[weekday] = buckets.get(weekday, 0) + int(duration.total_seconds() // 60)
    if not buckets:
        return None
    weekday = max(buckets.items(), key=lambda item: item[1])[0]
    return {"weekday": weekday, "name": WEEKDAY_NAMES[weekday], "minutes": buckets[weekday]}


def _focus_ratio(user) -> dict:
    topics = (
        Topic.objects.filter(owner=user)
        .annotate(entry_count=Count("entry"))
        .order_by("-entry_count")
    )
    total = sum(topic.entry_count for topic in topics) or 1
    top = topics.first()
    if top is None:
        return {"name": "", "share": 0}
    return {"name": top.text, "share": round(top.entry_count / total * 100)}


def _idle_topics(user, days: int = 14) -> list[str]:
    today = timezone.localdate()
    threshold = today - timedelta(days=days)
    idle = []
    for topic in Topic.objects.filter(owner=user).annotate(entry_count=Count("entry")):
        if topic.entry_count == 0:
            continue
        latest = topic.entry_set.order_by("-date_added").first()
        last_day = timezone.localdate(latest.date_added) if latest else today
        if last_day < threshold:
            idle.append(topic.text)
    return idle[:5]


def _review_health(user) -> dict:
    cards = Flashcard.objects.filter(user=user)
    total = cards.count()
    due = cards.filter(due_date__lte=timezone.localdate()).count()
    mastered = cards.filter(repetitions__gte=3).count()
    return {
        "total": total,
        "due": due,
        "mastered": mastered,
        "mastered_share": round(mastered / total * 100) if total else 0,
    }


@cached("insights", ttl=600)
def build(user) -> dict:
    """生成洞察卡片与行动建议。"""
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    last_week_start = week_start - timedelta(days=7)

    entries_week = Entry.objects.filter(
        topic__owner=user, date_added__date__gte=week_start
    ).count()
    entries_last_week = Entry.objects.filter(
        topic__owner=user,
        date_added__date__gte=last_week_start,
        date_added__date__lt=week_start,
    ).count()

    delta = entries_week - entries_last_week
    best_hour = _best_hour(user)
    best_weekday = _best_weekday(user)
    focus = _focus_ratio(user)
    idle = _idle_topics(user)
    review = _review_health(user)

    cards = [
        {
            "title": "本周产出",
            "value": f"{entries_week} 条",
            "hint": (
                f"比上周{'多' if delta > 0 else '少'} {abs(delta)} 条"
                if delta
                else "与上周持平"
            ),
            "tone": "accent" if delta > 0 else "muted" if delta == 0 else "amber",
        },
        {
            "title": "黄金时段",
            "value": f"{best_hour['hour']}:00 前后" if best_hour else "暂无数据",
            "hint": f"这个时段累计投入 {best_hour['minutes']} 分钟" if best_hour else "做几次计时就能算出来",
            "tone": "teal",
        },
        {
            "title": "最活跃的一天",
            "value": best_weekday["name"] if best_weekday else "暂无数据",
            "hint": f"这天累计 {best_weekday['minutes']} 分钟" if best_weekday else "先积累一周的记录",
            "tone": "accent",
        },
        {
            "title": "投入集中度",
            "value": f"{focus['share']}%" if focus["name"] else "暂无数据",
            "hint": f"集中在「{focus['name']}」" if focus["name"] else "还没有主题",
            "tone": "teal" if focus["share"] < 60 else "amber",
        },
        {
            "title": "复习健康度",
            "value": f"{review['mastered_share']}%",
            "hint": (
                f"{review['due']} 张到期 · 共 {review['total']} 张"
                if review["total"]
                else "还没有闪卡"
            ),
            "tone": "rose" if review["due"] > 10 else "teal",
        },
    ]

    suggestions = []
    if best_hour:
        suggestions.append(
            f"把最难的任务放在 {best_hour['hour']}:00 前后，那是你历史投入最高的时段。"
        )
    if best_weekday:
        suggestions.append(f"{best_weekday['name']}是你学得最多的一天，可以安排复盘或攻坚。")
    if focus["name"] and focus["share"] >= 60:
        suggestions.append(
            f"「{focus['name']}」占了 {focus['share']}% 的笔记，考虑给其他方向也留一点时间。"
        )
    if idle:
        suggestions.append(f"已搁置两周以上的主题：{'、'.join(idle)}，回去补一条或归档。")
    if review["due"] > 10:
        suggestions.append(f"有 {review['due']} 张卡片到期，先清一波再记新内容。")
    elif review["total"] == 0:
        suggestions.append("还没有闪卡：挑一个主题让 AI 生成一批，记忆才会留下来。")
    if delta < 0:
        suggestions.append("本周笔记比上周少，写一条「今天学到什么」就能把节奏拉回来。")
    if not suggestions:
        suggestions.append("数据还在积累，保持每天写一条，洞察会越来越准。")

    return {
        "cards": cards,
        "suggestions": suggestions[:6],
        "entries_week": entries_week,
        "idle_topics": idle,
        "review": review,
    }
