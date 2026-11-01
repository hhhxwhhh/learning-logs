"""DRF 异常处理：把错误收敛成统一结构。

所有接口报错都返回 ``{"error": {"code": 400, "message": "..."}}``，
客户端只需要读 ``error.message``。
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from learning_logs.services import api_access


def api_exception_handler(exc, context):
    if isinstance(exc, api_access.ApiError):
        return Response(
            {"error": {"code": exc.status, "message": exc.message}},
            status=exc.status,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail:
        message = str(detail["detail"])
    else:
        message = str(detail)
    response.data = {"error": {"code": response.status_code, "message": message}}
    return response
