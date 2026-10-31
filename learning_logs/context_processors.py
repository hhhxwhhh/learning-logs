"""全局模板上下文：把未读提醒数量带进每一个页面。"""

from __future__ import annotations

from django.core.cache import cache

from .services import notifications as notification_service

# 同一个用户最多每 30 分钟真正扫描一次学习状态
THROTTLE_SECONDS = 1800


def notifications(request):
    """登录用户才有提醒；未登录或异常时一律返回空值，不影响渲染。"""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"unread_count": 0, "unread_items": []}

    try:
        throttle_key = f"zhiji:notify-scan:{user.id}"
        if cache.add(throttle_key, "1", timeout=THROTTLE_SECONDS):
            notification_service.generate(user)
        count = notification_service.unread_count(user)
    except Exception:  # 数据库未就绪时不阻断渲染
        return {"unread_count": 0, "unread_items": []}

    items = []
    if count:
        items = list(notification_service.recent(user, limit=5))
        items = [item for item in items if item.is_unread][:5]
    return {"unread_count": count, "unread_items": items}
