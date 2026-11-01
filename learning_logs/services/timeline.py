"""学习时间线：把笔记、闪卡与专注记录按月聚成一条可回看的河流。"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from learning_logs.models import Entry, Flashcard, StudySession

from .cache import cached


def month_key(value) -> str:
    local = timezone.localtime(value)
    return f"{local:%Y-%m}"


@cached("timeline", ttl=600)
def build(user, months: int = 12) -> dict:
    """生成按月分组的时间线数据。"""
    today = timezone.localdate()
    start = timezone.make_aware(
        timezone.datetime.combine(today.replace(day=1), timezone.datetime.min.time())
    ) - timedelta(days=31 * (months - 1))

    entries = (
        Entry.objects.filter(topic__owner=user, date_added__gte=start)
        .select_related("topic")
        .order_by("-date_added")
    )
    cards = Flashcard.objects.filter(user=user, created_at__gte=start).select_related(
        "topic"
    )
    sessions = StudySession.objects.filter(
        user=user, start_time__gte=start, duration__isnull=False
    ).select_related("topic")

    buckets: dict[str, dict] = {}
    for entry in entries:
        key = month_key(entry.date_added)
        bucket = buckets.setdefault(
            key, {"key": key, "entries": [], "cards": 0, "minutes": 0, "topics": set()}
        )
        bucket["entries"].append(entry)
        bucket["topics"].add(entry.topic.text)

    for card in cards:
        key = month_key(card.created_at)
        bucket = buckets.setdefault(
            key, {"key": key, "entries": [], "cards": 0, "minutes": 0, "topics": set()}
        )
        bucket["cards"] += 1

    for session in sessions:
        key = month_key(session.start_time)
        bucket = buckets.setdefault(
            key, {"key": key, "entries": [], "cards": 0, "minutes": 0, "topics": set()}
        )
        bucket["minutes"] += session.duration_minutes()

    months_rows = []
    for key in sorted(buckets.keys(), reverse=True):
        bucket = buckets[key]
        months_rows.append(
            {
                "key": key,
                "label": key.replace("-", " 年 ") + " 月",
                "entry_count": len(bucket["entries"]),
                "card_count": bucket["cards"],
                "minutes": bucket["minutes"],
                "topics": sorted(bucket["topics"]),
                "entries": bucket["entries"][:8],
            }
        )

    total_entries = sum(row["entry_count"] for row in months_rows)
    total_minutes = sum(row["minutes"] for row in months_rows)
    peak = max(months_rows, key=lambda row: row["entry_count"], default=None)

    return {
        "months": months_rows,
        "total_entries": total_entries,
        "total_minutes": total_minutes,
        "total_cards": sum(row["card_count"] for row in months_rows),
        "peak": peak,
        "max_entry_count": max((row["entry_count"] for row in months_rows), default=0) or 1,
        "range_months": months,
    }
