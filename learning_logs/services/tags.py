"""标签服务：解析输入、同步关联、生成标签云。

标签用 GenericForeignKey 挂在 Topic / Entry 上，这样一个标签体系可以覆盖
主题和笔记两种对象，而不需要维护两套中间表。
"""

from __future__ import annotations

import re

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count

from learning_logs.models import Entry, Tag, TaggedItem, Topic

_SPLIT = re.compile(r"[,\s，、;；/|]+")
MAX_TAGS = 8
MAX_LEN = 24


def normalize(name: str) -> str:
    """去掉 # 前缀与两侧空白，截断到合理长度。"""
    cleaned = (name or "").strip().lstrip("#").strip()
    return cleaned[:MAX_LEN]


def parse_tags(raw: str) -> list[str]:
    """把用户输入解析成去重、保序的标签名列表。"""
    names: list[str] = []
    for part in _SPLIT.split(raw or ""):
        name = normalize(part)
        if name and name not in names:
            names.append(name)
        if len(names) >= MAX_TAGS:
            break
    return names


def sync_tags(user, obj, raw: str) -> list[Tag]:
    """把某对象的标签整体替换成 raw 解析出的标签集合。"""
    names = parse_tags(raw)
    content_type = ContentType.objects.get_for_model(obj)
    TaggedItem.objects.filter(
        tag__user=user, content_type=content_type, object_id=obj.pk
    ).delete()
    if not names:
        prune(user)
        return []

    tags = []
    for name in names:
        tag, _ = Tag.objects.get_or_create(user=user, name=name)
        TaggedItem.objects.create(tag=tag, content_object=obj)
        tags.append(tag)
    prune(user)
    return tags


def tags_of(obj) -> list[Tag]:
    """读取对象的标签（按名字排序，保证展示稳定）。"""
    content_type = ContentType.objects.get_for_model(obj)
    return list(
        Tag.objects.filter(
            items__content_type=content_type, items__object_id=obj.pk
        ).order_by("name")
    )


def tags_input_of(obj) -> str:
    """把对象标签还原成输入框里的逗号分隔文本。"""
    return ", ".join(tag.name for tag in tags_of(obj))


def prune(user) -> int:
    """清理没有任何引用的空标签，避免标签云里出现僵尸项。"""
    orphan = Tag.objects.filter(user=user, items__isnull=True)
    count = orphan.count()
    orphan.delete()
    return count


def cloud(user, limit: int | None = None) -> list[dict]:
    """标签云数据：按使用次数降序，附带相对权重用于渲染字号。"""
    rows = []
    for tag in Tag.objects.filter(user=user).annotate(count=Count("items")):
        if tag.count == 0:
            continue
        rows.append(
            {
                "id": tag.id,
                "name": tag.name,
                "count": tag.count,
                "hue": tag.hue,
                "url": f"/tags/{tag.id}/",
            }
        )
    rows.sort(key=lambda row: (-row["count"], row["name"]))
    top = rows[0]["count"] if rows else 1
    for row in rows:
        row["weight"] = round(0.6 + 0.9 * (row["count"] / top), 2)
    return rows[:limit] if limit else rows


def objects_of(user, tag_id: int) -> dict:
    """取某个标签下的主题与笔记。"""
    tag = Tag.objects.filter(id=tag_id, user=user).first()
    if tag is None:
        return {"tag": None, "topics": [], "entries": []}

    topic_ct = ContentType.objects.get_for_model(Topic)
    entry_ct = ContentType.objects.get_for_model(Entry)
    topic_ids = TaggedItem.objects.filter(tag=tag, content_type=topic_ct).values_list(
        "object_id", flat=True
    )
    entry_ids = TaggedItem.objects.filter(tag=tag, content_type=entry_ct).values_list(
        "object_id", flat=True
    )
    return {
        "tag": tag,
        "topics": Topic.objects.filter(owner=user, id__in=list(topic_ids)),
        "entries": Entry.objects.filter(topic__owner=user, id__in=list(entry_ids))
        .select_related("topic")
        .order_by("-date_added"),
    }
