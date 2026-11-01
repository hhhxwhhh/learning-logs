"""学习花园：把学习数据长成一棵可视化的树。"""

from __future__ import annotations

import calendar
import math

from django.db.models import Count
from django.utils import timezone

from learning_logs.models import Entry, Topic
from learning_logs.services import stats

# (所需笔记数, 阶段名, 描述)
STAGES = [
    (0, "种子", "还没有记录，先种下一颗种子。"),
    (1, "嫩芽", "第一片叶子长出来了。"),
    (6, "小树", "枝干开始分叉，保持每周记录。"),
    (18, "大树", "知识开始互相连接，试着做总结。"),
    (45, "森林", "你已经拥有自己的知识体系。"),
]

VIEWBOX = {"width": 900, "height": 560}
TRUNK_X = 450
GROUND_Y = 520


def stage_of(total_entries: int) -> dict:
    """根据笔记数计算成长阶段与到下一阶段的进度。"""
    current_index = 0
    for index, (threshold, _, _) in enumerate(STAGES):
        if total_entries >= threshold:
            current_index = index

    name = STAGES[current_index][1]
    description = STAGES[current_index][2]

    if current_index + 1 < len(STAGES):
        next_threshold = STAGES[current_index + 1][0]
        current_threshold = STAGES[current_index][0]
        span = max(next_threshold - current_threshold, 1)
        progress = round((total_entries - current_threshold) / span * 100)
        next_name = STAGES[current_index + 1][1]
        remaining = next_threshold - total_entries
    else:
        progress = 100
        next_name = None
        remaining = 0

    return {
        "index": current_index,
        "name": name,
        "description": description,
        "progress": max(0, min(progress, 100)),
        "next_name": next_name,
        "remaining": remaining,
    }


def tree_data(user, max_branches: int = 7) -> dict:
    """计算树枝与叶片的坐标，返回可直接渲染的 SVG 数据。"""
    topics = list(
        Topic.objects.filter(owner=user)
        .annotate(entry_count=Count("entry"))
        .order_by("-entry_count", "date_added")[:max_branches]
    )
    count = len(topics)
    branches = []

    for index, topic in enumerate(topics):
        side = -1 if index % 2 == 0 else 1
        ratio = 0.6 if count == 1 else index / (count - 1)  # 0 = 最下部，1 = 顶部
        size = topic.entry_count
        size_factor = 0.72 + min(size, 14) / 22

        attach_y = 480 - ratio * 270
        angle = math.radians(side * (74 - 30 * ratio))
        length = (190 - 80 * ratio) * size_factor

        x1 = TRUNK_X + math.sin(angle) * length
        y1 = attach_y - math.cos(angle) * length
        control_x = TRUNK_X + math.sin(angle) * length * 0.55
        control_y = attach_y - math.cos(angle) * length * 0.42

        leaves = []
        canopy = []
        twigs = []
        leaf_total = max(1, min(size, 12))
        positions = (0.55, 0.78, 0.97)
        offsets = ((0, -11, 7), (-11, 1, 6), (10, 2, 5), (-4, -16, 5), (6, -14, 5))

        for cluster_index, position in enumerate(positions):
            cx = TRUNK_X + (x1 - TRUNK_X) * position
            cy = attach_y + (y1 - attach_y) * position
            canopy.append({"x": round(cx, 1), "y": round(cy, 1), "r": 19 - cluster_index * 2})

            # 笔记越多，这一簇叶子越密
            cluster_leaves = leaf_total // len(positions) + (
                1 if cluster_index < leaf_total % len(positions) else 0
            )
            for leaf_index in range(max(1, cluster_leaves)):
                dx, dy, radius = offsets[leaf_index % len(offsets)]
                leaves.append(
                    {
                        "x": round(cx + dx * side, 1),
                        "y": round(cy + dy + (leaf_index // len(offsets)) * 6, 1),
                        "r": radius,
                        "tone": index % 4,
                    }
                )

            # 末梢小枝，让轮廓更接近真实树冠
            twigs.append(
                f"M{cx:.0f},{cy:.0f} l{12 * side},{-14}"
            )
            twigs.append(f"M{cx:.0f},{cy:.0f} l{-9 * side},{-17}")

        branches.append(
            {
                "topic": topic,
                "path": f"M{TRUNK_X},{attach_y:.0f} Q{control_x:.0f},{control_y:.0f} {x1:.0f},{y1:.0f}",
                "width": round(4 + min(size, 10) * 1.25, 1),
                "leaves": leaves,
                "canopy": canopy,
                "twigs": twigs,
                "tone": index % 4,
                "entry_count": size,
                "progress": topic.progress_percentage(),
            }
        )

    x = TRUNK_X
    seed = {
        "cx": x,
        "cy": 492,
        "stem": f"M{x},492 C{x},470 {x},458 {x},446",
        "leaf_left": f"M{x},458 C{x - 18},452 {x - 22},438 {x - 22},432 C{x - 10},432 {x - 2},444 {x},456",
        "leaf_right": f"M{x},470 C{x + 16},466 {x + 22},452 {x + 22},446 C{x + 10},446 {x + 2},458 {x},468",
    }

    return {
        "seed": seed,
        "branches": branches,
        "trunk": (
            f"M{TRUNK_X - 21},{GROUND_Y} "
            f"C{TRUNK_X - 14},420 {TRUNK_X - 9},300 {TRUNK_X - 6},196 "
            f"C{TRUNK_X - 4},176 {TRUNK_X + 4},176 {TRUNK_X + 6},196 "
            f"C{TRUNK_X + 9},300 {TRUNK_X + 14},420 {TRUNK_X + 21},{GROUND_Y} Z"
        ),
        "viewbox": VIEWBOX,
        "trunk_x": TRUNK_X,
        "ground_y": GROUND_Y,
    }


def _matches_today(local_date, today) -> bool:
    """判断是否是「去年的今天」：允许 29-31 号回退到短月份的最后一天。"""
    if local_date == today:
        return False
    if local_date.day == today.day:
        return True
    last_day = calendar.monthrange(local_date.year, local_date.month)[1]
    return today.day > local_date.day and local_date.day == last_day


def on_this_day(user, limit: int = 4):
    """往年/往月的今天写下的笔记，用于「今日回顾」。"""
    today = timezone.localdate()
    candidates = (
        Entry.objects.filter(topic__owner=user)
        .exclude(date_added__date=today)
        .select_related("topic")
        .order_by("-date_added")[:200]
    )
    picked = []
    for entry in candidates:
        local_date = timezone.localtime(entry.date_added).date()
        if _matches_today(local_date, today):
            picked.append(entry)
        if len(picked) >= limit:
            break
    return picked


def garden_context(user) -> dict:
    overview = stats.overview(user)
    stage = stage_of(overview["entry_count"])
    tree = tree_data(user)

    week_minutes = overview["week_minutes"]
    growth_note = (
        "本周还没有新的生长，写一条笔记就能看到叶子。"
        if week_minutes == 0
        else f"本周生长了 {stats.format_minutes(week_minutes)}，继续保持。"
    )

    first_day = (
        Entry.objects.filter(topic__owner=user)
        .order_by("date_added")
        .values_list("date_added", flat=True)
        .first()
    )
    days = (timezone.localdate() - timezone.localtime(first_day).date()).days + 1 if first_day else 0

    return {
        "overview": overview,
        "stage": stage,
        "tree": tree,
        "growth_note": growth_note,
        "days": days,
        "review_entries": on_this_day(user),
        "today": timezone.localdate(),
    }
