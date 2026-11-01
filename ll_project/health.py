"""依赖探针：数据库、Redis、Celery broker、Kafka、通道层。

每个探针都返回 (状态, 详情) 且不抛异常——探活接口要在依赖挂掉时也给出结果。
"""

from __future__ import annotations

import time

from django.conf import settings
from django.core.cache import cache
from django.db import connection

OK = "up"
DEGRADED = "degraded"
DOWN = "down"


def _timed(func):
    started = time.perf_counter()
    try:
        detail = func()
        status = OK
    except Exception as exc:  # pragma: no cover - 依赖异常时才触发
        detail = f"{exc.__class__.__name__}: {exc}"
        status = DOWN
    return status, detail, round((time.perf_counter() - started) * 1000, 1)


def probe_database() -> tuple[str, str, float]:
    def check():
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return connection.vendor

    return _timed(check)


def probe_cache() -> tuple[str, str, float]:
    def check():
        cache.set("__probe__", "1", 10)
        return cache.get("__probe__")

    return _timed(check)


def probe_celery() -> tuple[str, str, float]:
    def check():
        broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
        if not broker:
            return "未配置 broker，任务同步执行"
        from learning_logs.celery_app import app as celery_app

        # 只探 broker 连通性：ping worker 要等心跳，超时会把探活接口拖慢
        with celery_app.connection_for_write() as connection:
            connection.ensure_connection(max_retries=0, timeout=1.0)
        return f"broker {celery_app.conf.broker_url}"

    return _timed(check)


def probe_kafka() -> tuple[str, str, float]:
    def check():
        servers = getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", []) or []
        if not servers:
            return "未配置 Kafka，事件走 Redis Stream"
        from learning_logs.messaging.kafka_producer import producer

        if producer.disabled:
            raise RuntimeError("Kafka 连接已禁用")
        if producer._connect() is None:  # noqa: SLF001 - 探针需要触发一次连接
            raise RuntimeError("Kafka 不可达")
        return f"broker {', '.join(servers)}"

    return _timed(check)


def probe_channel_layer() -> tuple[str, str, float]:
    def check():
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        return type(layer).__name__

    return _timed(check)


PROBES = {
    "database": probe_database,
    "cache": probe_cache,
    "celery": probe_celery,
    "kafka": probe_kafka,
    "channel_layer": probe_channel_layer,
}

# 这些依赖缺失属于可降级情形，不影响整体就绪判断
OPTIONAL = {"celery", "kafka"}


def collect(use_cache: bool = True) -> dict:
    """跑一遍全部探针，汇总成报告。

    结果缓存几秒：探针里有网络往返，监控每次拉取都全量探测会拖慢响应。
    """
    if use_cache:
        cached = cache.get("zhiji:readyz")
        if cached is not None:
            return cached

    results = {}
    for name, probe in PROBES.items():
        status, detail, elapsed = probe()
        results[name] = {"status": status, "detail": detail, "ms": elapsed}

    required_down = [
        name
        for name, item in results.items()
        if item["status"] == DOWN and name not in OPTIONAL
    ]
    optional_down = [
        name
        for name, item in results.items()
        if item["status"] == DOWN and name in OPTIONAL
    ]
    if required_down:
        overall = DOWN
    elif optional_down:
        overall = DEGRADED
    else:
        overall = OK
    report = {"status": overall, "checks": results}
    if use_cache:
        cache.set("zhiji:readyz", report, 10)
    return report
