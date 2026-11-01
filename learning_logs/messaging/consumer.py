"""事件消费者：从 Kafka 或 Redis Stream 读取事件并落库。

发布端已经同步写过一次库，这里的价值在于：
外部系统产生的事件也能进到库里，以及支持离线回放。
写入按 event_id 去重，重复消费不会写出第二条。
"""

from __future__ import annotations

import json
import logging

from django.conf import settings

from ..events import store

logger = logging.getLogger(__name__)


def consume_from_stream(limit: int = 100) -> int:
    """消费 Redis Stream，返回新写入的事件数。"""
    from .stream import read_stream

    created = 0
    for event in read_stream(limit=limit):
        if store(event):
            created += 1
    return created


def consume_from_kafka(timeout: float = 5.0, limit: int = 100) -> int:
    """消费 Kafka 指定 topic，返回新写入的事件数。"""
    if not settings.KAFKA_ENABLED or not settings.KAFKA_BOOTSTRAP_SERVERS:
        return 0

    try:
        from kafka import KafkaConsumer
    except ImportError:  # pragma: no cover
        logger.warning("未安装 kafka-python，无法消费 Kafka")
        return 0

    created = 0
    consumer = None
    try:
        consumer = KafkaConsumer(
            settings.KAFKA_TOPIC,
            bootstrap_servers=list(settings.KAFKA_BOOTSTRAP_SERVERS),
            group_id=settings.KAFKA_CONSUMER_GROUP,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            consumer_timeout_ms=int(timeout * 1000),
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        for message in consumer:
            if store(message.value):
                created += 1
            if created >= limit:
                break
    except Exception:
        logger.warning("消费 Kafka 失败", exc_info=True)
    finally:
        if consumer is not None:
            try:
                consumer.close()
            except Exception:  # pragma: no cover
                pass
    return created


def consume(source: str = "auto", limit: int = 100) -> int:
    """按指定来源消费事件。

    source 取值：kafka / redis / auto。
    auto 表示 Kafka 开着就用 Kafka，否则用 Redis Stream。
    """
    if source == "kafka":
        return consume_from_kafka(limit=limit)
    if source == "redis":
        return consume_from_stream(limit=limit)
    if settings.KAFKA_ENABLED and settings.KAFKA_BOOTSTRAP_SERVERS:
        return consume_from_kafka(limit=limit)
    return consume_from_stream(limit=limit)
