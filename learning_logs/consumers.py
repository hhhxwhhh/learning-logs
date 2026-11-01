"""WebSocket 消费者：把学习事件实时推给看板。

每个登录用户一个 group（live-<user_id>），事件发生时被调用方投递进来，
消费者只负责转成 JSON 发给浏览器。
"""

from __future__ import annotations

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class LiveConsumer(AsyncJsonWebsocketConsumer):
    """实时看板连接。"""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.group_name = f"live-{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "ready"})

    async def disconnect(self, code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """客户端目前只会发心跳。"""
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def live_event(self, message):
        """事件总线投递过来的学习事件。

        channel layer 传进来的是整条消息（含 type 字段），真正的业务数据在
        消息的 event 键里。这里统一拆出来，保证前端拿到的结构与接口一致。
        """
        if isinstance(message, dict):
            event = message.get("event")
            if event is None:
                event = {k: v for k, v in message.items() if k != "type"}
        else:  # pragma: no cover - 理论上不会走到
            event = message
        await self.send_json({"type": "event", "event": event})
