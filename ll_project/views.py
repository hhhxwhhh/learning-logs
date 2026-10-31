"""项目级视图：健康检查、Service Worker、manifest 与离线页。"""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render


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


def service_worker(request):
    """从根路径提供 Service Worker，以便控制整个站点作用域。"""
    path = finders.find("js/sw.js")
    if not path:
        raise Http404("Service Worker 不存在")

    response = HttpResponse(
        Path(path).read_text(encoding="utf-8"),
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def manifest(request):
    """返回 PWA manifest，避免静态目录层级影响 scope。"""
    path = finders.find("manifest.webmanifest")
    if not path:
        raise Http404("manifest 不存在")
    return HttpResponse(
        Path(path).read_text(encoding="utf-8"),
        content_type="application/manifest+json; charset=utf-8",
    )


def offline(request):
    """Service Worker 在断网时回退到的页面。"""
    return render(request, "offline.html")
