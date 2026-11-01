"""消息总线：Kafka 优先，没有 Kafka 时退回 Redis Stream。

选这个顺序是因为 Kafka 更适合多消费方与长期回放，Redis Stream 部署成本低，
本地开发一条命令就能跑起来。两者都没有时事件只留在库里。
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def deliver(event: dict) -> str:
    """投递一条事件，返回实际使用的通道名。"""
    if settings.KAFKA_ENABLED and settings.KAFKA_BOOTSTRAP_SERVERS:
        from .kafka_producer import producer

        if producer.publish(event):
            return "kafka"

    from .stream import publish_stream

    if publish_stream(event):
        return "redis-stream"

    return "local"
