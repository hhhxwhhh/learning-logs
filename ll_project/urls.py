"""urls.py — 项目级路由。

约定：业务路由全部挂在应用自己的 urls.py 里，这里只做拼装。
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from .views import healthz, manifest, offline, service_worker

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("sw.js", service_worker, name="service_worker"),
    path("manifest.webmanifest", manifest, name="manifest"),
    path("offline/", offline, name="offline"),
    path("", include("learning_logs.urls", namespace="learning_logs")),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("analytics/", include("analytics.urls")),
    path(
        "favicon.ico",
        RedirectView.as_view(url="/static/images/favicon.png", permanent=True),
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
