"""知识图谱服务：把主题之间的关联算成一张可画的图。

边的来源按优先级：
1. 共享标签（最常见也最有语义）：共享几个标签权重就是几；
2. 退化情况（没有任何标签）用「同一周有记录」建立弱连接，避免图谱变成一堆孤点。

布局用简化力导向（Fruchterman-Reingold）：斥力把节点推开、弹簧把有边的节点拉近，
迭代固定次数后归一化到画布内。所有坐标都在服务端算好，模板只负责画 SVG。
"""

from __future__ import annotations

import math
import random

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count

from learning_logs.models import Entry, TaggedItem, Topic

WIDTH = 880
HEIGHT = 520
PADDING = 58


def _shared_tag_pairs(user) -> dict[tuple[int, int], int]:
    """统计共享标签的主题对及权重。"""
    pairs: dict[tuple[int, int], int] = {}
    items = (
        TaggedItem.objects.filter(tag__user=user)
        .select_related("tag")
        .values_list("tag_id", "content_type_id", "object_id")
    )
    topic_ct = ContentType.objects.get_for_model(Topic).id
    by_tag: dict[int, list[int]] = {}
    for tag_id, content_type_id, object_id in items:
        if content_type_id != topic_ct:
            continue
        by_tag.setdefault(tag_id, []).append(object_id)

    for object_ids in by_tag.values():
        unique = sorted(set(object_ids))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                key = (unique[i], unique[j])
                pairs[key] = pairs.get(key, 0) + 1
    return pairs


def _week_pairs(topics) -> dict[tuple[int, int], int]:
    """无标签时的兜底：同一 ISO 周内都写过笔记的主题之间连弱边。"""
    entries = (
        Entry.objects.filter(topic__in=topics)
        .values_list("topic_id", "date_added")
    )
    weeks: dict[tuple[int, int, int], set[int]] = {}
    for topic_id, date_added in entries:
        local = date_added
        key = local.isocalendar()[:3]
        weeks.setdefault(key, set()).add(topic_id)

    pairs: dict[tuple[int, int], int] = {}
    for topic_ids in weeks.values():
        ordered = sorted(topic_ids)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                key = (ordered[i], ordered[j])
                pairs[key] = pairs.get(key, 0) + 1
    return pairs


def _layout(nodes: list[dict], edges: list[dict], seed: int = 7) -> None:
    """力导向布局，直接把 x/y 写回 nodes。"""
    count = len(nodes)
    if count == 0:
        return
    rng = random.Random(seed)

    for index, node in enumerate(nodes):
        angle = 2 * math.pi * index / max(count, 1)
        radius = min(WIDTH, HEIGHT) * 0.32
        node["x"] = WIDTH / 2 + math.cos(angle) * radius + rng.uniform(-8, 8)
        node["y"] = HEIGHT / 2 + math.sin(angle) * radius + rng.uniform(-8, 8)

    index_of = {node["id"]: index for index, node in enumerate(nodes)}
    springs = [
        (index_of[edge["source"]], index_of[edge["target"]], edge["weight"])
        for edge in edges
        if edge["source"] in index_of and edge["target"] in index_of
    ]
    k = math.sqrt((WIDTH * HEIGHT) / max(count, 1)) * 0.55
    iterations = 160

    for step in range(iterations):
        cooling = (1 - step / iterations) ** 2 + 0.05
        fx = [0.0] * count
        fy = [0.0] * count

        for i in range(count):
            for j in range(i + 1, count):
                dx = nodes[i]["x"] - nodes[j]["x"]
                dy = nodes[i]["y"] - nodes[j]["y"]
                dist = math.hypot(dx, dy) or 0.01
                force = (k * k) / dist
                ux, uy = dx / dist, dy / dist
                fx[i] += ux * force
                fy[i] += uy * force
                fx[j] -= ux * force
                fy[j] -= uy * force

        for i, j, weight in springs:
            dx = nodes[i]["x"] - nodes[j]["x"]
            dy = nodes[i]["y"] - nodes[j]["y"]
            dist = math.hypot(dx, dy) or 0.01
            force = (dist * dist) / k * (0.6 + 0.4 * weight)
            ux, uy = dx / dist, dy / dist
            fx[i] -= ux * force
            fy[i] -= uy * force
            fx[j] += ux * force
            fy[j] += uy * force

        for i, node in enumerate(nodes):
            cx, cy = WIDTH / 2, HEIGHT / 2
            fx[i] += (cx - node["x"]) * 0.012
            fy[i] += (cy - node["y"]) * 0.012
            limit = k * 1.6
            step_x = max(-limit, min(limit, fx[i] * cooling * 0.06))
            step_y = max(-limit, min(limit, fy[i] * cooling * 0.06))
            node["x"] += step_x
            node["y"] += step_y

    xs = [node["x"] for node in nodes]
    ys = [node["y"] for node in nodes]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1)
    span_y = max(max_y - min_y, 1)

    for node in nodes:
        node["x"] = round(
            PADDING + (node["x"] - min_x) / span_x * (WIDTH - 2 * PADDING), 1
        )
        node["y"] = round(
            PADDING + (node["y"] - min_y) / span_y * (HEIGHT - 2 * PADDING), 1
        )


def build(user) -> dict:
    """生成知识图谱的 nodes / edges 与关联推荐。"""
    topics = (
        Topic.objects.filter(owner=user)
        .annotate(entry_count=Count("entry"))
        .order_by("-entry_count", "text")
    )
    visible = list(topics[:26])
    if not visible:
        return {
            "nodes": [],
            "edges": [],
            "width": WIDTH,
            "height": HEIGHT,
            "topics": [],
            "related": [],
            "linked": 0,
            "isolated": [],
        }

    max_entries = max(topic.entry_count for topic in visible) or 1
    nodes = [
        {
            "id": topic.id,
            "name": topic.text,
            "entries": topic.entry_count,
            "progress": topic.progress_percentage(),
            "url": f"/topic/{topic.id}",
            "r": round(14 + 20 * (topic.entry_count / max_entries), 1),
        }
        for topic in visible
    ]

    pairs = _shared_tag_pairs(user)
    if not pairs:
        pairs = _week_pairs(visible)

    id_set = {node["id"] for node in nodes}
    edges = []
    for (a, b), weight in pairs.items():
        if a in id_set and b in id_set:
            edges.append(
                {"source": a, "target": b, "weight": weight, "width": min(1 + weight, 5)}
            )
    edges.sort(key=lambda edge: -edge["weight"])

    _layout(nodes, edges)
    position = {node["id"]: node for node in nodes}
    for edge in edges:
        source = position.get(edge["source"])
        target = position.get(edge["target"])
        if source and target:
            edge["x1"] = source["x"]
            edge["y1"] = source["y"]
            edge["x2"] = target["x"]
            edge["y2"] = target["y"]
            edge["mid_x"] = round((source["x"] + target["x"]) / 2, 1)
            edge["mid_y"] = round((source["y"] + target["y"]) / 2, 1)

    linked_ids = set()
    for edge in edges:
        linked_ids.add(edge["source"])
        linked_ids.add(edge["target"])

    related = [
        {
            "source": position[edge["source"]]["name"],
            "target": position[edge["target"]]["name"],
            "weight": edge["weight"],
            "source_url": position[edge["source"]]["url"],
            "target_url": position[edge["target"]]["url"],
        }
        for edge in edges[:8]
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "width": WIDTH,
        "height": HEIGHT,
        "topics": visible,
        "related": related,
        "linked": len(linked_ids),
        "isolated": [node["name"] for node in nodes if node["id"] not in linked_ids],
    }
