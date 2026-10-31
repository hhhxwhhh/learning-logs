"""搜索服务：多关键词匹配、相关度排序与摘要高亮。

没有引入外部搜索引擎，直接用 SQLite + Python 打分：
- 主题命中权重高于笔记正文；
- 命中关键词越多、出现次数越多，排名越靠前；
- 返回片段时转义 HTML，再用 <mark> 标出关键词（前端用 v-html 之外的 innerHTML 渲染）。
"""

from __future__ import annotations

import html
import re

from django.db.models import Q

from learning_logs.models import Entry, Topic

_SPLIT = re.compile(r"[\s,，。;；、/|]+")


def tokenize(query: str) -> list[str]:
    return [part for part in _SPLIT.split((query or "").strip()) if part][:6]


def plain_text(text: str) -> str:
    """去掉 Markdown 标记，得到用于摘要的纯文本。"""
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"[*_>#~]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def score(text: str, terms: list[str], weight: int = 1) -> int:
    low = (text or "").lower()
    total = 0
    for term in terms:
        low_term = term.lower()
        if low_term in low:
            total += weight * (1 + low.count(low_term))
    return total


def make_snippet(text: str, terms: list[str], width: int = 90) -> str:
    """截取关键词附近的片段并高亮，返回已转义的 HTML。"""
    plain = plain_text(text)
    if not plain:
        return ""

    lower = plain.lower()
    position = min(
        (lower.find(term.lower()) for term in terms if lower.find(term.lower()) >= 0),
        default=0,
    )
    start = max(0, position - width // 3)
    end = min(len(plain), start + width)
    snippet = plain[start:end]

    escaped = html.escape(snippet)
    for term in sorted({t for t in terms if t}, key=len, reverse=True):
        escaped = re.sub(
            f"({re.escape(html.escape(term))})",
            r"<mark>\1</mark>",
            escaped,
            flags=re.IGNORECASE,
        )

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(plain) else ""
    return f"{prefix}{escaped}{suffix}"


def search_all(user, query: str, limit: int = 6) -> dict:
    """返回主题与笔记的搜索结果，按相关度排序。"""
    terms = tokenize(query)
    if not terms:
        return {"query": query, "terms": [], "topics": [], "entries": [], "total": 0}

    topic_q = Q()
    entry_q = Q()
    for term in terms:
        topic_q |= Q(text__icontains=term)
        entry_q |= Q(text__icontains=term)

    topic_rows = []
    for topic in Topic.objects.filter(owner=user).filter(topic_q)[:30]:
        topic_rows.append(
            {
                "id": topic.id,
                "title": topic.text,
                "meta": f"{topic.total_items} 条记录 · 完成 {topic.progress_percentage()}%",
                "snippet": make_snippet(topic.text, terms),
                "score": score(topic.text, terms, weight=3),
                "url": f"/topic/{topic.id}",
            }
        )
    topic_rows.sort(key=lambda row: row["score"], reverse=True)

    entry_rows = []
    entries = (
        Entry.objects.filter(topic__owner=user)
        .filter(entry_q)
        .select_related("topic")
        .order_by("-date_added")[:80]
    )
    for entry in entries:
        entry_rows.append(
            {
                "id": entry.id,
                "title": entry.topic.text,
                "meta": entry.date_added.strftime("%Y-%m-%d"),
                "snippet": make_snippet(entry.text, terms),
                "score": score(entry.text, terms),
                "url": f"/entry/{entry.id}/comments/",
            }
        )
    entry_rows.sort(key=lambda row: (row["score"], row["meta"]), reverse=True)

    return {
        "query": query,
        "terms": terms,
        "topics": topic_rows[:limit],
        "entries": entry_rows[:limit],
        "total": len(topic_rows) + len(entry_rows),
    }
