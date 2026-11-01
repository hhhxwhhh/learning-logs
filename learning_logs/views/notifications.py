"""提醒中心。"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from ..models import Notification
from ..services import notifications as notifications_service

logger = logging.getLogger(__name__)

@login_required
def notifications_view(request):
    """提醒中心：查看全部提醒并标记已读。"""
    notifications_service.generate(request.user)
    items = Notification.objects.filter(user=request.user)
    return render(
        request,
        "learning_logs/notifications.html",
        {
            "items": items[:40],
            "unread": items.filter(read_at__isnull=True).count(),
            "total": items.count(),
        },
    )


@login_required
def mark_notification_read(request, notification_id):
    """把单条提醒标记为已读，然后跳到它指向的页面。

    只对本人提醒生效，标记已读没有副作用，因此允许 GET 直达。
    """
    item = Notification.objects.filter(id=notification_id, user=request.user).first()
    if item is None:
        raise Http404("提醒不存在")

    updated = 0
    if item.is_unread:
        item.mark_read()
        updated = 1

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": bool(updated)})
    if item.link:
        return redirect(item.link)
    if not updated:
        messages.info(request, "这条提醒已经是已读状态。")
    return redirect("learning_logs:notifications")


@login_required
@require_POST
def mark_all_read(request):
    """一键清空未读。"""
    count = notifications_service.mark_all_read(request.user)
    messages.success(request, f"已把 {count} 条提醒标记为已读。")
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "count": count})
    return redirect("learning_logs:notifications")
