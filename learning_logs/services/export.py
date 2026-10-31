"""数据导出与导入。

- Markdown：按主题导出，可直接放进 Obsidian / Logseq 笔记库
- CSV：Anki 可导入的问答卡片格式
- JSON：完整备份，便于迁移或二次开发
- 导入：把外部 Markdown 按标题切成条目，归入指定主题
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile

from django.utils import timezone

from learning_logs.models import Entry, Flashcard, LearningGoal, LearningPath, Topic

_UNSAFE = re.compile(r'[\\/:*?"<>|\s]+')


def safe_filename(text: str, fallback: str = "topic") -> str:
    name = _UNSAFE.sub("-", (text or "").strip()).strip("-")
    return (name or fallback)[:60]


def topic_markdown(topic: Topic) -> str:
    """把一个主题导出为 Markdown，保留时间、状态与评论。"""
    lines = [f"# {topic.text}", ""]
    lines.append(
        f"> 导出时间：{timezone.localtime():%Y-%m-%d %H:%M} · "
        f"{topic.total_items} 条记录 · 完成 {topic.progress_percentage()}%"
    )
    lines.append("")

    for entry in topic.entry_set.order_by("date_added"):
        status = "已掌握" if entry.completed else "进行中"
        lines.append(f"## {timezone.localtime(entry.date_added):%Y-%m-%d %H:%M} · {status}")
        lines.append("")
        lines.append(entry.text.strip())
        lines.append("")

        comments = entry.comments.all()
        if comments:
            lines.append("### 评论")
            for comment in comments:
                lines.append(
                    f"- **{comment.user.username}**"
                    f"（{timezone.localtime(comment.created_at):%Y-%m-%d}）：{comment.text}"
                )
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def all_topics_zip(user) -> bytes:
    """全部笔记打包为 zip，每个主题一个 Markdown 文件。"""
    buffer = io.BytesIO()
    topics = Topic.objects.filter(owner=user).order_by("date_added")

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        index = ["# 知迹学习日志导出", "", f"主题数：{topics.count()}", ""]
        for topic in topics:
            filename = f"{safe_filename(topic.text, f'topic-{topic.id}')}.md"
            archive.writestr(filename, topic_markdown(topic))
            index.append(f"- [{topic.text}]({filename}) · {topic.total_items} 条记录")

        archive.writestr("README.md", "\n".join(index) + "\n")

    return buffer.getvalue()


def flashcards_csv(user) -> str:
    """Anki 可导入的 CSV（UTF-8 BOM，Excel 打开不乱码）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["front", "back", "tags"])
    for card in Flashcard.objects.filter(user=user).select_related("topic"):
        writer.writerow([card.front, card.back, f"知迹::{card.topic.text}"])
    return "\ufeff" + buffer.getvalue()


def backup_json(user) -> str:
    """完整数据备份，不含文件本体。"""
    topics = Topic.objects.filter(owner=user).order_by("date_added")
    payload = {
        "format": "zhiji-learning-log",
        "version": 2,
        "exported_at": timezone.localtime().isoformat(),
        "user": user.get_username(),
        "topics": [
            {
                "text": topic.text,
                "created_at": topic.date_added.isoformat(),
                "entries": [
                    {
                        "text": entry.text,
                        "completed": entry.completed,
                        "created_at": entry.date_added.isoformat(),
                        "comments": [
                            {
                                "user": comment.user.username,
                                "text": comment.text,
                                "created_at": comment.created_at.isoformat(),
                            }
                            for comment in entry.comments.all()
                        ],
                    }
                    for entry in topic.entry_set.order_by("date_added")
                ],
            }
            for topic in topics
        ],
        "flashcards": [
            {
                "front": card.front,
                "back": card.back,
                "topic": card.topic.text,
                "due_date": card.due_date.isoformat(),
                "interval_days": card.interval_days,
                "ease_factor": round(card.ease_factor, 3),
            }
            for card in Flashcard.objects.filter(user=user).select_related("topic")
        ],
        "paths": [
            {
                "title": path.title,
                "description": path.description,
                "estimated_hours": path.estimated_hours,
                "steps": [
                    {
                        "topic": step.topic.text,
                        "description": step.description,
                        "estimated_hours": step.estimated_hours,
                        "completed": step.is_completed,
                    }
                    for step in path.pathstep_set.order_by("order")
                ],
            }
            for path in LearningPath.objects.filter(user=user)
        ],
        "goals": [
            {
                "title": goal.title,
                "description": goal.description,
                "target_date": goal.target_date.isoformat(),
                "completed": goal.completed,
            }
            for goal in LearningGoal.objects.filter(user=user)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def split_markdown(text: str) -> list[str]:
    """把 Markdown 按标题切分成若干段；没有标题时按空行分段。"""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []

    h2 = re.split(r"^##\s+", text, flags=re.M)
    if len(h2) > 1:
        chunks = h2[1:]
    else:
        h1 = re.split(r"^#\s+", text, flags=re.M)
        chunks = h1[1:] if len(h1) > 1 else [text]

    cleaned = []
    for chunk in chunks:
        # 标题本身也保留，导入后仍能看出这段话讲的是什么
        body = (chunk or "").strip()
        if len(body) >= 2:
            cleaned.append(body)
    return cleaned


def import_markdown(user, text: str, *, topic: Topic | None = None, title: str = "") -> dict:
    """导入 Markdown 片段，返回 {created, topic}。"""
    chunks = split_markdown(text)
    if not chunks:
        return {"created": 0, "topic": topic}

    if topic is None:
        name = (title or "").strip() or f"导入的笔记 {timezone.localdate():%Y-%m-%d}"
        topic = Topic.objects.create(text=name[:200], owner=user)

    entries = [Entry(topic=topic, text=chunk) for chunk in chunks]
    Entry.objects.bulk_create(entries)
    topic.update_progress()
    return {"created": len(entries), "topic": topic}


def parse_card_lines(text: str) -> list[tuple[str, str]]:
    """解析批量建卡文本：每行一张卡，支持 |、Tab、;; 三种分隔。"""
    pairs: list[tuple[str, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        front, back = "", ""
        for separator in ("\t", ";;", "|", "｜", "——"):
            if separator in line:
                front, back = line.split(separator, 1)
                break
        if not back:
            continue

        front = front.strip()[:300]
        back = back.strip()
        if front and back:
            pairs.append((front, back))
    return pairs


def import_cards(user, topic: Topic, text: str) -> dict:
    """批量创建闪卡，返回 {created, skipped}。"""
    if topic is None or topic.owner_id != user.id:
        return {"created": 0, "skipped": 0}

    pairs = parse_card_lines(text)
    if not pairs:
        return {"created": 0, "skipped": 0}

    existing = set(
        Flashcard.objects.filter(user=user, topic=topic).values_list("front", flat=True)
    )
    cards = []
    skipped = 0
    for front, back in pairs:
        if front in existing:
            skipped += 1
            continue
        existing.add(front)
        cards.append(Flashcard(user=user, topic=topic, front=front, back=back))

    if cards:
        Flashcard.objects.bulk_create(cards)
    return {"created": len(cards), "skipped": skipped}


def import_cards_csv(user, topic: Topic, content: str) -> dict:
    """导入 Anki 导出的 CSV（前两列为正面/背面，可含表头）。"""
    if topic is None or topic.owner_id != user.id:
        return {"created": 0, "skipped": 0}

    reader = csv.reader(io.StringIO(content or ""))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return {"created": 0, "skipped": 0}

    first_cell = rows[0][0].strip().lower()
    if first_cell in {"front", "正面", "问题", "question"}:
        rows = rows[1:]

    lines = []
    for row in rows:
        front = row[0].strip() if row else ""
        back = row[1].strip() if len(row) > 1 else ""
        if front and back:
            lines.append(f"{front}\t{back}")
    return import_cards(user, topic, "\n".join(lines))
