"""数据的导出与导入。"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from ..models import Entry, Flashcard, LearningPath, Topic
from ..services import export as export_service

logger = logging.getLogger(__name__)

@login_required
def data_tools(request):
    """数据导出与导入入口。"""
    topics = Topic.objects.filter(owner=request.user).annotate(entry_count=Count("entry"))
    context = {
        "topics": topics,
        "entry_count": Entry.objects.filter(topic__owner=request.user).count(),
        "card_count": Flashcard.objects.filter(user=request.user).count(),
        "path_count": LearningPath.objects.filter(user=request.user).count(),
    }
    return render(request, "learning_logs/data.html", context)


@login_required
def export_notes(request):
    """导出全部笔记为 Markdown zip。"""
    content = export_service.all_topics_zip(request.user)
    response = HttpResponse(content, content_type="application/zip")
    response["Content-Disposition"] = (
        f'attachment; filename="zhiji-notes-{timezone.localdate():%Y%m%d}.zip"'
    )
    return response


@login_required
def export_topic(request, topic_id):
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    content = export_service.topic_markdown(topic)
    response = HttpResponse(content, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="topic-{topic.id}.md"'
    return response


@login_required
def export_cards(request):
    content = export_service.flashcards_csv(request.user)
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="zhiji-flashcards-{timezone.localdate():%Y%m%d}.csv"'
    )
    return response


@login_required
def export_backup(request):
    content = export_service.backup_json(request.user)
    response = HttpResponse(content, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="zhiji-backup-{timezone.localdate():%Y%m%d}.json"'
    )
    return response


@login_required
@require_POST
def import_notes(request):
    """从 Markdown 文件导入笔记。"""
    upload = request.FILES.get("file")
    if upload is None:
        messages.error(request, "请选择要导入的 Markdown 文件。")
        return redirect("learning_logs:data_tools")

    if upload.size > 1024 * 1024:
        messages.error(request, "文件超过 1MB，请拆分后再导入。")
        return redirect("learning_logs:data_tools")

    try:
        text = upload.read().decode("utf-8-sig", errors="ignore")
    except Exception:  # noqa: BLE001
        messages.error(request, "文件无法解析，请确认是 UTF-8 编码的 Markdown。")
        return redirect("learning_logs:data_tools")

    topic = None
    topic_id = request.POST.get("topic")
    if topic_id and topic_id != "new":
        topic = Topic.objects.filter(id=topic_id, owner=request.user).first()
        if topic is None:
            messages.error(request, "选择的主题不存在。")
            return redirect("learning_logs:data_tools")

    if topic is None:
        title = (request.POST.get("title") or "").strip()
        default_name = upload.name.rsplit(".", 1)[0][:200]
        topic_title = title or default_name or f"导入的笔记 {timezone.localdate():%Y-%m-%d}"
        result = export_service.import_markdown(request.user, text, title=topic_title)
    else:
        result = export_service.import_markdown(request.user, text, topic=topic)

    if result["created"] == 0:
        messages.warning(request, "文件里没有识别到可导入的内容（需要 Markdown 标题分段）。")
    else:
        messages.success(
            request,
            f"已导入 {result['created']} 条笔记到「{result['topic'].text}」。",
        )
        return redirect("learning_logs:topic", topic_id=result["topic"].id)
    return redirect("learning_logs:data_tools")


@login_required
def import_center(request):
    """导入中心：Markdown 笔记、批量文本建卡、Anki CSV 三种入口。"""
    topics = Topic.objects.filter(owner=request.user).annotate(
        card_count=Count("flashcards")
    )
    return render(
        request,
        "learning_logs/import.html",
        {
            "topics": topics,
            "entry_count": Entry.objects.filter(topic__owner=request.user).count(),
            "card_count": Flashcard.objects.filter(user=request.user).count(),
        },
    )
