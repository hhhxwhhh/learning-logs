"""Kafka 生产者。

连接是懒建立的，而且失败一次就不再重试：broker 不可达时事件走本地通道，
不该让每次写笔记都等一次网络超时。
"""

from __future__ import annotations

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class KafkaProducer:
    """薄薄一层 kafka-python 封装，失败就返回 False。"""

    def __init__(self):
        self._producer = None
        self._disabled = False

    @property
    def disabled(self) -> bool:
        return self._disabled

    def _connect(self):
        if self._producer is not None or self._disabled:
            return self._producer

        try:
            from kafka import KafkaProducer
        except ImportError:  # pragma: no cover - 没装 kafka-python 时降级
            logger.warning("未安装 kafka-python，事件改走其他通道")
            self._disabled = True
            return None

        base = {
            "bootstrap_servers": list(settings.KAFKA_BOOTSTRAP_SERVERS),
            "client_id": settings.KAFKA_CLIENT_ID,
            "value_serializer": lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            "key_serializer": lambda key: str(key).encode("utf-8") if key else None,
            "acks": 1,
            "linger_ms": 50,
            "request_timeout_ms": int(settings.KAFKA_PRODUCER_TIMEOUT * 1000),
            "max_block_ms": int(settings.KAFKA_PRODUCER_TIMEOUT * 1000),
        }
        # 不同版本 kafka-python 的可用参数不一样，先用新参数，不支持就退回老参数
        attempts = [dict(base, api_version_auto_timeout_ms=2000), dict(base)]

        for options in attempts:
            try:
                self._producer = KafkaProducer(**options)
                return self._producer
            except (ValueError, TypeError):
                continue
            except Exception:
                logger.warning("Kafka 连接失败，事件改走其他通道", exc_info=True)
                self._disabled = True
                return None

        logger.warning("当前 kafka-python 不支持所选参数，事件改走其他通道")
        self._disabled = True
        return None

    def publish(self, event: dict) -> bool:
        """投递成功返回 True，失败返回 False（调用方决定降级路径）。"""
        producer = self._connect()
        if producer is None:
            return False
        try:
            producer.send(settings.KAFKA_TOPIC, key=event.get("user_id"), value=event)
            return True
        except Exception:
            logger.warning("Kafka 投递失败", exc_info=True)
            self._disabled = True
            self._producer = None
            return False

    def close(self) -> None:
        if self._producer is not None:
            try:
                self._producer.flush(timeout=2)
                self._producer.close(timeout=2)
            except Exception:  # pragma: no cover
                pass
            self._producer = None


producer = KafkaProducer()
