"""双链笔记：用 [[主题名]] 把笔记互相连起来，并在主题页显示反向链接。

渲染策略：先把 [[名称]] 替换成 Markdown 链接语法，再交给 markdown 渲染，
这样既复用现有的安全渲染（禁用原始 HTML），也不用改动 Markdown 解析器。
"""

from __future__ import annotations

import re

from learning_logs.models import Entry, Topic

WIKI_LINK = re.compile(r"\[\[([^\[\]]{1,60})\]\]")


def extract(text: str) -> list[str]:
    """取出文本里所有 [[双链]] 的名称（去重、保序）。"""
    names: list[str] = []
    for name in WIKI_LINK.findall(text or ""):
        cleaned = name.strip()
        if cleaned and cleaned not in names:
            names.append(cleaned)
    return names


def resolve(user, names: list[str]) -> dict[str, int]:
    """把名称映射到主题 id，只认本人名下的主题。"""
    if not names:
        return {}
    topics = Topic.objects.filter(owner=user, text__in=names).values("id", "text")
    return {row["text"]: row["id"] for row in topics}


def render(text: str, user) -> str:
    """把 [[名称]] 渲染成指向主题的 Markdown 链接；未匹配的主题保留为普通文本。"""
    names = extract(text)
    if not names:
        return text or ""

    mapping = resolve(user, names)

    def replace(match: re.Match) -> str:
        name = match.group(1).strip()
        topic_id = mapping.get(name)
        if topic_id is None:
            return f"`[[{name}]]`"
        return f"[{name}](/topic/{topic_id})"

    return WIKI_LINK.sub(replace, text or "")


def backlinks(topic: Topic, limit: int = 10) -> list[Entry]:
    """找出引用了该主题名的笔记。"""
    owner = topic.owner
    needle = f"[[{topic.text}]]"
    siblings = (
        Entry.objects.filter(topic__owner=owner)
        .exclude(topic_id=topic.id)
        .select_related("topic")
        .order_by("-date_added")
    )
    # 用朴素包含判断，避免主题名里的方括号被当成正则语法
    return [entry for entry in siblings if needle in (entry.text or "")][:limit]


def outgoing(user, entry: Entry) -> list[Topic]:
    """某条笔记指向了哪些主题。"""
    names = extract(entry.text)
    if not names:
        return []
    return list(Topic.objects.filter(owner=user, text__in=names))
