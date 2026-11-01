"""缓存层。

失效用「数据指纹 + 显式 epoch」两重保险：

- 数据指纹：主题数、条目数与最近一次改动时间拼成短串，数据一变指纹就变，
  不依赖每个写入口都记得调用失效；
- epoch：写操作主动自增，用于数据没变但派生结果变了的情况（比如标签重命名）。

两种方式都不需要扫 key，Redis 和进程内缓存都能用。

缓存是可选项。Redis 不可用时 Django 会静默跳过缓存，
业务逻辑照常跑，只是慢一点。
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import wraps

from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300
HIT_COUNTER = "zhiji:stat:cache:hit"
MISS_COUNTER = "zhiji:stat:cache:miss"


def _epoch_key(user_id) -> str:
    return f"zhiji:epoch:{user_id}"


def epoch(user_id) -> int:
    value = cache.get(_epoch_key(user_id))
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def fingerprint(user_id) -> str:
    """用户数据的轻量指纹：主题数、条目数、最近改动时间。"""
    from django.db.models import Count, Max

    from ..models import Entry, Topic

    try:
        topics = Topic.objects.filter(owner_id=user_id).count()
        agg = Entry.objects.filter(topic__owner_id=user_id).aggregate(
            count=Count("id"), last=Max("date_added")
        )
    except Exception:  # pragma: no cover - 表还没建好时忽略
        return "0-0-none"
    last = agg["last"].isoformat() if agg["last"] else "none"
    return f"{topics}-{agg['count'] or 0}-{last}"


def version(user_id) -> str:
    """缓存键里的版本串：epoch 与数据指纹拼在一起。"""
    return f"e{epoch(user_id)}-{hashlib.sha1(fingerprint(user_id).encode()).hexdigest()[:10]}"


def invalidate(user_id) -> None:
    """显式作废某个用户的缓存。"""
    try:
        cache.incr(_epoch_key(user_id))
    except ValueError:
        cache.set(_epoch_key(user_id), 1, None)
    except Exception:  # pragma: no cover - 缓存不可用时不影响主流程
        logger.warning("缓存 epoch 自增失败", exc_info=True)


def token_of(*parts) -> str:
    """把参数变成稳定的短键。

    参数用 JSON 序列化而不是 str()：不同对象的 str() 可能撞成同一串
    （比如 Django 模型的默认 __str__ 都长这样），缓存就会串号。
    """
    raw = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def make_key(namespace: str, user_id, *parts) -> str:
    return f"zhiji:{namespace}:{user_id}:{version(user_id)}:{token_of(*parts)}"


def cached(namespace: str, ttl: int = DEFAULT_TTL, user_arg: str = "user"):
    """给服务函数加缓存。

    被装饰的函数需要有一个用户参数（默认名为 ``user``），
    缓存键会带上用户 id 与版本，不同人之间不会串。
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            bound = dict(zip(func.__code__.co_varnames, args))
            bound.update(kwargs)
            owner = bound.get(user_arg)
            owner_id = getattr(owner, "id", owner)
            if owner_id is None:
                return func(*args, **kwargs)

            extra = {k: v for k, v in bound.items() if k != user_arg}
            token = token_of(extra)
            key = make_key(namespace, owner_id, token)
            try:
                cached_value = cache.get(key)
            except Exception:  # pragma: no cover
                cached_value = None
                logger.warning("读取缓存失败，直接计算", exc_info=True)

            if cached_value is not None:
                _count(HIT_COUNTER)
                return cached_value

            _count(MISS_COUNTER)
            value = func(*args, **kwargs)
            try:
                cache.set(key, value, ttl)
            except Exception:  # pragma: no cover
                logger.warning("写入缓存失败", exc_info=True)
            return value

        wrapper.cache_namespace = namespace
        wrapper.cache_ttl = ttl
        return wrapper

    return decorator


def _count(key: str) -> None:
    """累加计数器。计数键不存在时先建一个，否则 incr 会报错。"""
    try:
        cache.add(key, 0, None)
        cache.incr(key)
    except Exception:  # pragma: no cover
        pass


def stats() -> dict:
    """命中率统计，给运维和调试用。"""
    try:
        hit = int(cache.get(HIT_COUNTER) or 0)
        miss = int(cache.get(MISS_COUNTER) or 0)
    except Exception:  # pragma: no cover
        return {"hit": 0, "miss": 0, "rate": 0}
    total = hit + miss
    return {
        "hit": hit,
        "miss": miss,
        "rate": round(hit / total * 100) if total else 0,
    }


def reset_stats() -> None:
    try:
        cache.delete(HIT_COUNTER, MISS_COUNTER)
    except Exception:  # pragma: no cover
        pass
