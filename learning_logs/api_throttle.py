"""DRF 层的限流与审计。

限流按令牌维度计数（未带令牌的请求按 IP 计），用 Django 缓存实现；
没有配置 Redis 时缓存退化为进程内计数，多进程部署下会各自计数，
这是有意的降级：宁可限得不准，也不要因为限流器不可用而拒绝请求。
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


class ApiRateThrottle(SimpleRateThrottle):
    """按令牌限流；没有令牌时退回按 IP 限流。"""

    scope = "api"

    def get_rate(self):
        return getattr(settings, "API_THROTTLE_RATE", "240/min")

    def get_cache_key(self, request, view):
        token = getattr(request, "api_token", None)
        if token is not None:
            return self.cache_format % {"scope": self.scope, "ident": f"token-{token.id}"}
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class ApiAuditMiddleware:
    """记录 v2 API 的调用：谁、什么时候、调用了哪个接口、结果如何。"""

    PREFIX = "/api/v2/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.PREFIX):
            self._record(request, response)
        return response

    def _record(self, request, response) -> None:
        # DRF 会把 request 包一层，认证属性挂在 DRF Request 上
        token = getattr(request, "api_token", None)
        if token is None:
            inner = getattr(request, "_request", None)
            token = getattr(inner, "api_token", None)
        inner = getattr(request, "_request", request)
        user = getattr(inner, "user", None)
        payload = {
            "path": request.path,
            "method": request.method,
            "status": response.status_code,
            "token_id": getattr(token, "id", None),
            "user_id": getattr(user, "id", None) if getattr(user, "is_authenticated", False) else None,
        }
        try:
            from learning_logs.models import ApiAccessLog

            ApiAccessLog.objects.create(**payload)
        except Exception:  # pragma: no cover - 审计失败不能影响主流程
            logger.warning("API 审计写入失败", exc_info=True)
            return
        logger.info("api %s", json.dumps(payload, ensure_ascii=False))


class ApiAccessLogMiddleware(ApiAuditMiddleware):
    """兼容命名。"""
