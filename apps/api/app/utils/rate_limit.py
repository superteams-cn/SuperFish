"""
基于 Redis 的滑动窗口限流（跨进程精确，fail-open）。

设计：
- 用有序集合（ZSET）按时间戳记录每次命中，窗口外的旧记录在每次检查时清理；
- Redis 不可用时一律放行（fail-open），绝不因缓存故障阻塞登录等关键路径；
- 同步客户端（redis>=5 内置），与现有同步业务代码一致，连接带短超时。

调用方拿到 False 即应返回 429。键由调用方按「动作:维度」自行拼装，
例如 ``auth:login:ip:1.2.3.4`` / ``auth:login:email:a@b.com``。
"""

import time

import redis

from ..settings import settings
from .logger import get_logger

logger = get_logger("superfish.rate_limit")

_client: redis.Redis | None = None
_client_failed = False


def _get_client() -> redis.Redis | None:
    """惰性创建带超时的同步 Redis 客户端；创建失败后不再重试（fail-open）。"""
    global _client, _client_failed
    if _client is not None or _client_failed:
        return _client
    try:
        _client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        return _client
    except Exception as e:
        logger.warning(f"Redis 限流客户端初始化失败，限流降级为放行：{e}")
        _client_failed = True
        return None


def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """滑动窗口限流：window_seconds 内最多 limit 次。

    返回 True 放行、False 触发限流。Redis 异常时一律放行。
    """
    if not settings.rate_limit_enabled or limit <= 0:
        return True
    client = _get_client()
    if client is None:
        return True

    now = time.time()
    member = f"{now:.6f}"
    redis_key = f"ratelimit:{key}"
    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        pipe.zadd(redis_key, {member: now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, window_seconds + 1)
        _, _, count, _ = pipe.execute()
        return int(count) <= limit
    except Exception as e:
        # fail-open：缓存故障不阻塞业务
        logger.warning(f"限流检查异常，降级放行 key={key}: {e}")
        return True


def client_ip(request) -> str:
    """从请求解析客户端 IP，优先取反代透传的 X-Forwarded-For 首段。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
