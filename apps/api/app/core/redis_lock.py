"""跨副本互斥锁（基于 Redis SET NX EX + token 校验释放）。

用于把「先查后改」的临界区在多 API 副本间串行化，例如 /start：避免两个副本同时
判定「未在运行」→ 各自入队 → 两个 worker 各拉起一个子进程。

Redis 不可用时退化为「无锁放行」（与 jobqueue 的内联兜底一致）：单机/降级场景不因
缺少 Redis 而拒绝请求；此时本就退回单进程，竞态窗口也不存在。
"""

import uuid
from contextlib import contextmanager

import redis

from .logger import get_logger
from .settings import settings

logger = get_logger("superfish.redis_lock")

# CAS 释放：仅当持有者仍是自己时删除，避免误删他人因 TTL 过期后重新获取的锁
_RELEASE_LUA = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"

_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


class LockBusy(Exception):
    """锁已被他人持有（临界区正被另一副本执行）。"""

    def __init__(self, key: str):
        super().__init__(f"resource busy: {key}")
        self.key = key


@contextmanager
def redis_lock(key: str, ttl: int = 60):
    """获取 per-key 互斥锁；获取失败抛 LockBusy。

    Args:
        key: 锁键（建议含业务前缀，如 sim:start:{sid}）
        ttl: 锁自动过期秒数（持有者崩溃时的兜底，应略大于临界区最坏耗时）
    """
    token = uuid.uuid4().hex
    try:
        acquired = _get_redis().set(key, token, nx=True, ex=ttl)
    except Exception as exc:
        # Redis 不可用：退化为无锁放行（不因缺锁而拒绝请求）
        logger.warning(f"获取锁失败，退化为无锁: {key}, error={exc}")
        yield
        return

    if not acquired:
        raise LockBusy(key)

    try:
        yield
    finally:
        try:
            _get_redis().eval(_RELEASE_LUA, 1, key, token)
        except Exception as exc:
            logger.warning(f"释放锁失败（将由 TTL 自动过期）: {key}, error={exc}")
