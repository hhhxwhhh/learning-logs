"""学习事件：写库 + 投递。

publish() 做两件事：

1. 把事件写进 EventLog，页面马上能看见；
2. 投递到消息总线，让外部系统拿到同一份事件流。

投递失败只记日志，不影响业务操作本身。
"""

from __future__ import annotations

import logging
import uuid

from .models import EventLog

logger = logging.getLogger(__name__)


def publish(kind: str, user, summary: str, *, topic=None, payload: dict | None = None) -> EventLog:
    """记录并投递一条学习事件。"""
    event_id = uuid.uuid4().hex
    record, _ = EventLog.objects.get_or_create(
        event_id=event_id,
        defaults={
            "user": user,
            "kind": kind,
            "summary": (summary or "")[:200],
            "payload": payload or {},
            "topic": topic,
        },
    )
    deliver(to_dict(record))
    broadcast(record.user_id, to_dict(record))
    return record


def to_dict(record: EventLog) -> dict:
    """事件在总线上的标准格式。"""
    return {
        "event_id": record.event_id,
        "kind": record.kind,
        "summary": record.summary,
        "payload": record.payload or {},
        "user_id": record.user_id,
        "topic_id": record.topic_id,
        "created_at": record.created_at.isoformat(),
    }


def deliver(event: dict) -> str:
    """投递到消息总线，返回实际使用的通道。"""
    from .messaging import bus

    try:
        return bus.deliver(event)
    except Exception:  # pragma: no cover - 投递失败不影响业务
        logger.warning("事件投递失败", exc_info=True)
        return "local"


def broadcast(user_id, event: dict) -> None:
    """推给该用户的实时看板连接。

    看板是可选功能：没装 channels、没有连接、通道层不可用时都直接跳过。
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"live-{user_id}", {"type": "live.event", "event": event}
        )
    except Exception:  # pragma: no cover - 推送失败不影响业务
        logger.debug("实时推送失败", exc_info=True)


def store(event: dict) -> bool:
    """把总线上的事件写回库里，按 event_id 去重。"""
    user_id = event.get("user_id")
    if not user_id:
        return False
    _, created = EventLog.objects.get_or_create(
        event_id=event.get("event_id") or uuid.uuid4().hex,
        defaults={
            "user_id": user_id,
            "kind": event.get("kind", "entry_created"),
            "summary": (event.get("summary") or "")[:200],
            "payload": event.get("payload") or {},
            "topic_id": event.get("topic_id"),
        },
    )
    return created
