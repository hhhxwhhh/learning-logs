"""项目级运维视图：健康检查。"""

from django.db import connection
from django.http import JsonResponse


def healthz(request):
    """给容器/监控用的探活接口，顺带探一下数据库连接。"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database_ok = True
    except Exception:  # pragma: no cover - 仅在数据库不可用时触发
        database_ok = False

    payload = {
        "status": "ok" if database_ok else "degraded",
        "database": "up" if database_ok else "down",
    }
    return JsonResponse(payload, status=200 if database_ok else 503)
