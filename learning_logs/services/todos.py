"""待办服务：从 Markdown 笔记里抽出 `- [ ]` 待办项，并支持勾选回写。

待办不单独建表，而是寄生在笔记正文里：
- 好处是待办和它所依赖的上下文永远在一起，导出 Markdown 也不丢；
- 代价是需要解析与回写文本，所以这里把「解析」和「改写」都收敛到一个模块，
  只暴露 extract / scan / toggle 三个动作给视图。
"""

from __future__ import annotations

import re

from learning_logs.models import Entry

# 支持 `- [ ]`、`* [x]`、`1. [ ]`，允许行首缩进
TODO_RE = re.compile(
    r"^(?P<indent>\s*)(?:[-*+]|\d+[.)])\s+\[(?P<mark>[ xX])\]\s*(?P<body>.*)$"
)
_MARK_RE = re.compile(r"\[([ xX])\]")


def extract(text: str) -> list[dict]:
    """抽出一段 Markdown 里的所有待办项，按出现顺序编号。"""
    items: list[dict] = []
    for number, line in enumerate((text or "").splitlines()):
        match = TODO_RE.match(line)
        if not match:
            continue
        items.append(
            {
                "index": len(items),
                "line": number,
                "done": match.group("mark").lower() == "x",
                "text": match.group("body").strip(),
            }
        )
    return items


def scan(user, *, only_open: bool = False, topic=None) -> list[dict]:
    """扫描用户所有笔记里的待办项，带上所属主题与笔记信息。"""
    entries = (
        Entry.objects.filter(topic__owner=user)
        .select_related("topic")
        .order_by("-date_added")
    )
    if topic is not None:
        entries = entries.filter(topic=topic)

    rows: list[dict] = []
    for entry in entries:
        for item in extract(entry.text):
            if only_open and item["done"]:
                continue
            rows.append(
                {
                    "index": item["index"],
                    "done": item["done"],
                    "text": item["text"],
                    "entry": entry,
                    "entry_id": entry.id,
                    "topic": entry.topic,
                    "topic_text": entry.topic.text,
                    "topic_id": entry.topic_id,
                    "date_added": entry.date_added,
                }
            )
    return rows


def summarize(rows: list[dict]) -> dict:
    """统计完成率，顺带算出还有多少条没做。"""
    total = len(rows)
    done = sum(1 for row in rows if row["done"])
    open_count = total - done
    return {
        "total": total,
        "done": done,
        "open": open_count,
        "rate": round(done / total * 100) if total else 0,
    }


def group_by_topic(rows: list[dict]) -> list[dict]:
    """按主题分组，组内保持笔记时间倒序带来的原始顺序。"""
    groups: dict[int, dict] = {}
    for row in rows:
        group = groups.get(row["topic_id"])
        if group is None:
            group = {
                "topic_id": row["topic_id"],
                "topic_text": row["topic_text"],
                "items": [],
            }
            groups[row["topic_id"]] = group
        group["items"].append(row)
    for group in groups.values():
        group["done"] = sum(1 for item in group["items"] if item["done"])
        group["total"] = len(group["items"])
    return list(groups.values())


def toggle(entry: Entry, index: int) -> dict | None:
    """切换某条笔记里第 index 个待办的勾选状态，返回新状态。

    只改内存中 entry.text，是否留痕与保存交给调用方决定。
    """
    items = extract(entry.text)
    target = next((item for item in items if item["index"] == index), None)
    if target is None:
        return None

    lines = (entry.text or "").splitlines()
    if target["line"] >= len(lines):
        return None

    mark = " " if target["done"] else "x"
    lines[target["line"]] = _MARK_RE.sub(f"[{mark}]", lines[target["line"]], count=1)
    entry.text = "\n".join(lines)
    return {"done": not target["done"], "text": target["text"]}
