"""Redis Stream 通道：没有 Kafka 时的替代方案。

用 Redis Stream 而不是普通 List，是因为它支持消费者组与断点续传，
多进程消费不会重复处理同一条消息。
"""

from __future__ import annotations

import json
import logging

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
    """建消费者组，已经存在就忽略。"""
    try:
        client.xgroup_create(STREAM_KEY, GROUP, id="0", mkstream=True)
    except Exception:
        pass


def read_stream(limit: int = 100) -> list[dict]:
    """读取新事件并返回，同时从 Stream 里删除。"""
    client = get_client()
    if client is None:
        return []

    events: list[dict] = []
    try:
        ensure_group(client)
        entries = client.xreadgroup(GROUP, "consumer-1", {STREAM_KEY: ">"}, count=limit)
        for _stream, items in entries or []:
            for message_id, fields in items:
                raw = fields.get("event")
                if not raw:
                    continue
                try:
                    events.append(json.loads(raw))
                except (TypeError, ValueError):
                    continue
                client.xack(STREAM_KEY, GROUP, message_id)
    except Exception:
        logger.warning("读取 Redis Stream 失败", exc_info=True)
    return events
