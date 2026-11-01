"""ASGI 入口：HTTP 走 Django，WebSocket 走 Channels。

部署时用 uvicorn 起这个应用：
    uvicorn ll_project.asgi:application --host 0.0.0.0 --port 8000
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ll_project.settings")

django_asgi_app = get_asgi_application()

try:  # 没装 channels 时退回纯 Django 应用
    from channels.auth import AuthMiddlewareStack
    from channels.routing import ProtocolTypeRouter, URLRouter

    from learning_logs.routing import websocket_urlpatterns

    application = ProtocolTypeRouter(
        {
            "http": django_asgi_app,
            "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
        }
    )
except ImportError:  # pragma: no cover
    application = django_asgi_app
