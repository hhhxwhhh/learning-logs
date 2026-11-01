"""闪卡的创建、复习与统计。"""

from __future__ import annotations

import logging

from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from ..ai.providers import AIError
from ..ai.service import generate_flashcards
from ..models import Flashcard, Topic
from .. import events
from ..services import cache as cache_service
from ..services import export as export_service

logger = logging.getLogger(__name__)

@login_required
def flashcards(request):
    """闪卡总览：今日待复习、卡片列表与 AI 生成入口。"""
    today = timezone.localdate()
    cards = Flashcard.objects.filter(user=request.user).select_related("topic")
    due_cards = cards.filter(due_date__lte=today)

    if request.method == "POST":
        front = (request.POST.get("front") or "").strip()
        back = (request.POST.get("back") or "").strip()
        topic_id = request.POST.get("topic")
        topic = Topic.objects.filter(id=topic_id, owner=request.user).first()
        if not front or not back or topic is None:
            messages.error(request, "请填写问题、答案并选择一个主题。")
        else:
            Flashcard.objects.create(
                user=request.user, topic=topic, front=front[:300], back=back
            )
            messages.success(request, "闪卡已添加。")
            return redirect("learning_logs:flashcards")

    context = {
        "cards": cards[:60],
        "total": cards.count(),
        "due_count": due_cards.count(),
        "learned": cards.filter(repetitions__gte=3).count(),
        "topics": Topic.objects.filter(owner=request.user).annotate(
            card_count=Count("flashcards")
        ),
        "today": today,
    }
    return render(request, "learning_logs/flashcards.html", context)


@login_required
def review(request):
    """今日复习队列，一次只显示一张卡。"""
    cards = (
        Flashcard.objects.filter(user=request.user, due_date__lte=timezone.localdate())
        .select_related("topic")
        .order_by("due_date", "id")
    )
    total = cards.count()
    card = cards.first()

    return render(
        request,
        "learning_logs/review.html",
        {"card": card, "remaining": total, "total": total},
    )


@login_required
@require_POST
def review_answer(request, card_id):
    card = get_object_or_404(Flashcard, id=card_id, user=request.user)
    try:
        quality = int(request.POST.get("quality", 3))
    except (TypeError, ValueError):
        quality = 3
    card.review(quality)
    events.publish(
        "card_reviewed",
        request.user,
        f"复习了「{card.topic.text}」的卡片",
        topic=card.topic,
        payload={"card_id": card.id, "quality": quality},
    )
    cache_service.invalidate(request.user.id)
    return redirect("learning_logs:review")


@login_required
@require_POST
def delete_flashcard(request, card_id):
    card = get_object_or_404(Flashcard, id=card_id, user=request.user)
    card.delete()
    messages.success(request, "闪卡已删除。")
    return redirect("learning_logs:flashcards")


@login_required
@require_POST
def generate_cards(request, topic_id):
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    try:
        count = int(request.POST.get("count", 8))
    except (TypeError, ValueError):
        count = 8
    count = max(1, min(count, 15))

    try:
        created = generate_flashcards(topic, count=count)
    except AIError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"已为「{topic.text}」生成 {created} 张闪卡。")
    return redirect("learning_logs:flashcards")


@login_required
def card_stats(request):
    """闪卡复习统计：掌握度分布、按主题分布与最近复习节奏。"""
    cards = Flashcard.objects.filter(user=request.user).select_related("topic")
    today = timezone.localdate()

    buckets = {"未开始": 0, "学习中": 0, "已掌握": 0}
    for card in cards:
        if card.repetitions == 0:
            buckets["未开始"] += 1
        elif card.repetitions >= 3:
            buckets["已掌握"] += 1
        else:
            buckets["学习中"] += 1

    by_topic = (
        cards.values("topic__text")
        .annotate(total=Count("id"), mastered=Count("id", filter=Q(repetitions__gte=3)))
        .order_by("-total")[:8]
    )

    daily = []
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        count = cards.filter(last_reviewed_at__date=day).count()
        daily.append({"date": day.strftime("%m-%d"), "count": count})

    reviewed = cards.filter(last_reviewed_at__isnull=False).count()
    context = {
        "total": cards.count(),
        "buckets": buckets,
        "by_topic": by_topic,
        "daily": daily,
        "reviewed": reviewed,
        "due_count": cards.filter(due_date__lte=today).count(),
        "max_daily": max((row["count"] for row in daily), default=0) or 1,
    }
    return render(request, "learning_logs/card_stats.html", context)


@login_required
@require_POST
def import_cards_view(request):
    """批量建卡：支持粘贴文本与上传 Anki CSV。"""
    topic_id = request.POST.get("topic")
    topic = Topic.objects.filter(id=topic_id, owner=request.user).first()
    if topic is None:
        messages.error(request, "请先选择一个属于自己的主题。")
        return redirect("learning_logs:import_center")

    text = (request.POST.get("cards") or "").strip()
    upload = request.FILES.get("file")

    if upload is not None:
        if upload.size > 1024 * 1024:
            messages.error(request, "文件超过 1MB，请拆分后再导入。")
            return redirect("learning_logs:import_center")
        content = upload.read().decode("utf-8-sig", errors="ignore")
        result = export_service.import_cards_csv(request.user, topic, content)
        source = upload.name
    elif text:
        result = export_service.import_cards(request.user, topic, text)
        source = "粘贴的文本"
    else:
        messages.error(request, "请粘贴卡片内容或上传 CSV 文件。")
        return redirect("learning_logs:import_center")

    if not result["created"]:
        messages.info(request, "没有新增卡片，可能是内容为空或正面重复。")
    else:
        messages.success(
            request,
            f"已从{source}导入 {result['created']} 张卡片"
            + (f"，跳过 {result['skipped']} 张重复卡。" if result["skipped"] else "。"),
        )
    return redirect("learning_logs:flashcards")
