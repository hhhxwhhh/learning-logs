"""标签、知识图谱与标签建议。"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from ..ai.providers import AIError
from ..ai.service import suggest_tags as suggest_tags_service
from ..models import Entry, Tag, TaggedItem, Topic
from ..services import graph as graph_service
from ..services import tags as tags_service

logger = logging.getLogger(__name__)

@login_required
def tags(request):
    """标签总览：标签云 + 最近打过标签的对象。"""
    return render(
        request,
        "learning_logs/tags.html",
        {
            "cloud": tags_service.cloud(request.user),
            "tag_count": Tag.objects.filter(user=request.user).count(),
            "tagged_topics": TaggedItem.objects.filter(
                tag__user=request.user,
                content_type=ContentType.objects.get_for_model(Topic),
            ).count(),
            "tagged_entries": TaggedItem.objects.filter(
                tag__user=request.user,
                content_type=ContentType.objects.get_for_model(Entry),
            ).count(),
        },
    )


@login_required
def tag_detail(request, tag_id):
    """单个标签下的主题与笔记。"""
    data = tags_service.objects_of(request.user, tag_id)
    if data["tag"] is None:
        raise Http404("标签不存在")
    return render(request, "learning_logs/tag_detail.html", data)


@login_required
def graph(request):
    """知识图谱：主题之间的关联网络。"""
    return render(request, "learning_logs/graph.html", graph_service.build(request.user))


@login_required
@require_POST
def suggest_tags(request, topic_id):
    """让 AI 为主题建议标签，直接写入标签并返回建议结果。"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    try:
        names = suggest_tags_service(topic)
    except AIError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception:  # noqa: BLE001
        logger.exception("AI 标签建议失败")
        return JsonResponse({"ok": False, "error": "AI 服务暂时不可用，请稍后再试。"}, status=502)

    current = [tag.name for tag in tags_service.tags_of(topic)]
    merged = list(dict.fromkeys(current + [name for name in names if name not in current]))
    tags_service.sync_tags(request.user, topic, ", ".join(merged[:8]))

    return JsonResponse(
        {
            "ok": True,
            "suggested": names,
            "applied": tags_service.tags_input_of(topic),
            "message": f"已补充 {len(names)} 个 AI 建议标签。",
        }
    )
