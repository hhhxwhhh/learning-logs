"""主题分享与公开主页。"""

from __future__ import annotations

import logging

import secrets
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from ..models import Entry, Topic
from ..services import tags as tags_service

logger = logging.getLogger(__name__)

@login_required
@require_POST
def toggle_share(request, topic_id):
    """开启 / 关闭主题的只读分享链接。"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)

    if topic.share_token:
        topic.share_token = ""
        topic.shared_at = None
        messages.success(request, "已关闭分享链接，之前的地址立即失效。")
    else:
        topic.share_token = secrets.token_urlsafe(16)
        topic.shared_at = timezone.now()
        messages.success(request, "分享链接已生成，任何拿到链接的人都能只读查看。")

    topic.save(update_fields=["share_token", "shared_at"])
    return redirect("learning_logs:topic", topic_id=topic.id)


def shared_topic(request, token):
    """公开只读页面：不需要登录，不带任何用户信息。"""
    topic = (
        Topic.objects.filter(share_token=token)
        .exclude(share_token="")
        .first()
        if token
        else None
    )
    if topic is None:
        raise Http404("分享链接不存在或已失效")

    context = {
        "topic": topic,
        "entries": topic.entry_set.order_by("-date_added"),
        "entry_count": topic.total_items,
    }
    return render(request, "learning_logs/shared.html", context)


def public_profile(request, username):
    """公开主页：只展示该用户主动开启分享的主题，不含任何私人信息。"""
    owner = get_object_or_404(get_user_model(), username=username)
    shared_topics = (
        Topic.objects.filter(owner=owner)
        .exclude(share_token="")
        .order_by("-date_added")
    )
    if not shared_topics.exists():
        raise Http404("这位用户还没有公开任何主题")

    entries = (
        Entry.objects.filter(topic__in=shared_topics)
        .select_related("topic")
        .order_by("-date_added")[:8]
    )
    tag_names = sorted(
        {tag.name for topic in shared_topics for tag in tags_service.tags_of(topic)}
    )

    return render(
        request,
        "learning_logs/public_profile.html",
        {
            "owner": owner,
            "topics": shared_topics,
            "entries": entries,
            "tag_names": tag_names,
            "topic_count": shared_topics.count(),
            "entry_count": Entry.objects.filter(topic__in=shared_topics).count(),
        },
    )
