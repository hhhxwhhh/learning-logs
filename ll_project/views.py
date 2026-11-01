"""项目级视图：健康检查、Service Worker、manifest 与离线页。"""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render

from .health import collect


def healthz(request):
    """存活探针：只看数据库能不能用，轻量。"""
    from .health import probe_database

    status, detail, elapsed = probe_database()
    payload = {
        "status": "ok" if status == "up" else "degraded",
        "database": "up" if status == "up" else "down",
        "ms": elapsed,
    }
    return JsonResponse(payload, status=200 if status == "up" else 503)


def readyz(request):
    """就绪探针：逐项检查依赖，可选依赖缺失只降级不算故障。"""
    report = collect()
    http_status = 200 if report["status"] != "down" else 503
    return JsonResponse(report, status=http_status)


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
