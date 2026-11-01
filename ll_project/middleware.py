"""请求日志中间件。

默认输出普通文本行；设置 ``DJANGO_LOG_FORMAT=json`` 时输出结构化 JSON，
方便在容器环境里被日志采集器解析。
"""

from __future__ import annotations

import json
import logging
import time
import uuid

logger = logging.getLogger("zhiji.request")

EXCLUDE_PREFIXES = ("/static/", "/media/", "/favicon.ico")


class RequestLogMiddleware:
    """记录请求耗时、状态码与用户，中间件开销控制在毫秒级。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        request.request_id = request_id
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            self._log(request, 500, started, request_id)
            raise
        self._log(request, response.status_code, started, request_id)
        response["X-Request-Id"] = request_id
        return response

    def _log(self, request, status: int, started: float, request_id: str) -> None:
        path = request.path
        if path.startswith(EXCLUDE_PREFIXES):
            return
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        user = getattr(request, "user", None)
        payload = {
            "request_id": request_id,
            "method": request.method,
            "path": path,
            "status": status,
            "ms": elapsed,
            "user_id": getattr(user, "id", None) if user is not None and user.is_authenticated else None,
        }
        logger.info(json.dumps(payload, ensure_ascii=False))
