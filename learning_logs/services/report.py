"""学习周报：统计本周数据，并可让 AI 写一段复盘。"""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Count
from django.utils import timezone

from learning_logs.ai.providers import AIError, Message, get_provider, resolve_model
from learning_logs.models import (
    Entry,
    Flashcard,
    LearningGoal,
    StudySession,
    Topic,
    WeeklyReport,
)
from learning_logs.services import stats

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

REPORT_SYSTEM = (
    "你是一位务实的学习教练。根据用户这一周的真实数据写一份简短周报，"
    "用中文 Markdown，分为三节：\\n"
    "## 本周回顾（2-3 句，基于数据，不要空泛鼓励）\\n"
    "## 值得注意（指出停滞的主题、被忽略的目标或过度分散的迹象）\\n"
    "## 下周建议（3 条具体、可执行的小行动）\\n"
    "总字数控制在 300 字以内，不要编造数据之外的信息。"
)


def week_start_of(day: date | None = None) -> date:
    day = day or timezone.localdate()
    return day - timedelta(days=day.weekday())


def collect(user, start: date) -> dict:
    """收集某一周的学习数据（JSON 可序列化）。"""
    end = start + timedelta(days=6)
    today = timezone.localdate()

    daily = stats.daily_minutes(user, days=max((today - start).days + 1, 7))
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        days.append(
            {
                "date": day.isoformat(),
                "label": WEEKDAY_NAMES[offset],
                "minutes": daily.get(day, 0),
                "is_future": day > today,
            }
        )

    week_minutes = sum(item["minutes"] for item in days)
    prev_minutes = sum(
        daily.get(start - timedelta(days=offset), 0) for offset in range(1, 8)
    )

    entries = Entry.objects.filter(
        topic__owner=user, date_added__date__range=(start, end)
    )
    sessions = StudySession.objects.filter(
        user=user, start_time__date__range=(start, end)
    )
    reviewed = Flashcard.objects.filter(
        user=user, last_reviewed_at__date__range=(start, end)
    ).count()
    new_topics = Topic.objects.filter(
        owner=user, date_added__date__range=(start, end)
    )

    topic_rows = (
        entries.values("topic__id", "topic__text")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    overdue = [
        goal.title
        for goal in LearningGoal.objects.filter(user=user, completed=False)
        if goal.is_overdue()
    ]

    peak = max([item["minutes"] for item in days] + [1])
    for item in days:
        item["pct"] = max(4, round(item["minutes"] / peak * 100)) if item["minutes"] else 4

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "week_minutes": week_minutes,
        "prev_minutes": prev_minutes,
        "delta": week_minutes - prev_minutes,
        "entry_count": entries.count(),
        "completed_entries": entries.filter(completed=True).count(),
        "session_count": sessions.count(),
        "reviewed_cards": reviewed,
        "new_topics": [topic.text for topic in new_topics],
        "top_topics": [
            {"id": row["topic__id"], "text": row["topic__text"], "count": row["count"]}
            for row in topic_rows
        ],
        "overdue_goals": overdue,
        "days": days,
    }


def build_prompt(data: dict) -> str:
    topics = "、".join(f"{row['text']}（{row['count']} 条）" for row in data["top_topics"]) or "无"
    return (
        f"周期：{data['week_start']} 至 {data['week_end']}\n"
        f"学习时长：本周 {data['week_minutes']} 分钟，上周 {data['prev_minutes']} 分钟\n"
        f"新增笔记：{data['entry_count']} 条（已完成 {data['completed_entries']} 条）\n"
        f"计时会话：{data['session_count']} 次；复习闪卡：{data['reviewed_cards']} 张\n"
        f"涉及主题：{topics}\n"
        f"逾期目标：{'、'.join(data['overdue_goals']) or '无'}\n"
        "请据此写周报。"
    )


def generate(user, start: date, model: str | None = None) -> WeeklyReport:
    """调用模型生成周报并保存（同一周重复生成会覆盖）。"""
    data = collect(user, start)
    provider = get_provider()
    model_name = resolve_model(model)

    summary = provider.complete(
        [
            Message(role="system", content=REPORT_SYSTEM),
            Message(role="user", content=build_prompt(data)),
        ],
        model=model_name,
    )
    if not (summary or "").strip():
        raise AIError("模型没有返回内容，请稍后重试。")

    report, _ = WeeklyReport.objects.update_or_create(
        user=user,
        week_start=start,
        defaults={
            "summary": summary.strip(),
            "stats": data,
            "model_name": model_name,
        },
    )
    return report


def suggestions(data: dict) -> list[str]:
    """不依赖模型也能给出的规则建议。"""
    items = []
    if data["week_minutes"] == 0:
        items.append("这周还没有记录，先写一条 3 分钟的笔记恢复节奏。")
    elif data["delta"] < 0:
        items.append(
            f"本周比上周少投入 {abs(data['delta'])} 分钟，下周固定一个 25 分钟的专注时段。"
        )
    else:
        items.append(f"本周比上周多投入 {data['delta']} 分钟，保持同样的节奏即可。")

    if data["overdue_goals"]:
        items.append(f"有 {len(data['overdue_goals'])} 个目标已逾期，重新设定日期或拆小第一步。")
    if data["reviewed_cards"] == 0:
        items.append("这周没有复习闪卡，安排一次 10 分钟复习能显著降低遗忘。")
    if data["entry_count"] == 0:
        items.append("尝试把本周读到的一段话，用自己的话写成一条笔记。")
    return items[:4]
