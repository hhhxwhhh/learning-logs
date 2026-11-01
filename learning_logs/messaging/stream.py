"""Redis Stream 通道：没有 Kafka 时的替代方案。

用 Redis Stream 而不是普通 List，是因为它支持消费者组与断点续传，
多进程消费不会重复处理同一条消息。
"""

from __future__ import annotations

import json
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

STREAM_KEY = "zhiji:events"
GROUP = "zhiji-consumers"


def get_client():
    """拿到 Redis 客户端；配置里没启用 Redis 时返回 None。"""
    if not settings.REDIS_URL:
        return None
    try:
        from django_redis import get_redis_connection

        return get_redis_connection("default")
    except Exception:
        logger.debug("Redis 连接不可用", exc_info=True)
        return None


def publish_stream(event: dict) -> bool:
    """写一条事件到 Stream，成功返回 True。"""
    client = get_client()
    if client is None:
        return False
    try:
        client.xadd(
            STREAM_KEY,
            {"event": json.dumps(event, ensure_ascii=False)},
            maxlen=1000,
            approximate=True,
        )
        return True
    except Exception:
        logger.warning("Redis Stream 投递失败", exc_info=True)
        return False


def ensure_group(client) -> None:
    """建消费者组。

    组已经存在但底层 Stream 被删过时，组会指向一个不存在的流，
    这时读不到任何消息。这里检测到这种情况就把组重建。
    """
    try:
        client.xgroup_create(STREAM_KEY, GROUP, id="0", mkstream=True)
        return
    except Exception:
        pass

    try:
        groups = client.xinfo_groups(STREAM_KEY)
    except Exception:
        return

    for group in groups or []:
        name = group.get("name") if isinstance(group, dict) else None
        if name is None and isinstance(group, (list, tuple)):
            name = group[0]
        if isinstance(name, bytes):
            name = name.decode("utf-8", "ignore")
        if name == GROUP:
            try:
                client.xgroup_destroy(STREAM_KEY, GROUP)
                client.xgroup_create(STREAM_KEY, GROUP, id="0", mkstream=True)
            except Exception:
                logger.debug("重建消费者组失败", exc_info=True)
            return


def read_stream(limit: int = 100, consumer: str | None = None) -> list[dict]:
    """读取新事件并返回，确认后从 Stream 里删除。

    consumer 名默认按进程区分：同一个进程反复调用能看到自己的新消息，
    换进程则各自消费，不会互相抢消息。
    """
    client = get_client()
    if client is None:
        return []

    name = consumer or f"consumer-{os.getpid()}"
    events: list[dict] = []
    try:
        ensure_group(client)
        entries = client.xreadgroup(GROUP, name, {STREAM_KEY: ">"}, count=limit)
        for _stream, items in entries or []:
            for message_id, fields in items:
                # Redis 客户端可能不解码响应，字段名与值都可能是 bytes
                raw = fields.get("event")
                if raw is None:
                    raw = fields.get(b"event")
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "ignore")
                try:
                    events.append(json.loads(raw))
                except (TypeError, ValueError):
                    continue
                client.xack(STREAM_KEY, GROUP, message_id)
    except Exception:
        logger.warning("读取 Redis Stream 失败", exc_info=True)
    return events
