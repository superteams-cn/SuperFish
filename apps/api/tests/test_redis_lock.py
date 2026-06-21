"""跨副本互斥锁测试（/start 并发去重的底座）。需本地 Redis，缺失则整文件 skip。"""

import pytest

from app.core.redis_lock import LockBusy, redis_lock


def _redis_available() -> bool:
    try:
        import redis

        from app.core.settings import settings

        redis.Redis.from_url(settings.redis_url).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="本地 Redis 不可用")


def _del(key):
    import redis

    from app.core.settings import settings

    redis.Redis.from_url(settings.redis_url, decode_responses=True).delete(key)


def test_lock_is_mutually_exclusive_and_releases():
    key = "test:lock:mutex"
    _del(key)
    with redis_lock(key, ttl=30):
        # 临界区内：第二次获取应抛 LockBusy
        with pytest.raises(LockBusy):
            with redis_lock(key, ttl=30):
                pass
    # 退出临界区后可再次获取（已释放）
    with redis_lock(key, ttl=30):
        pass
    _del(key)


def test_lock_busy_carries_key():
    key = "test:lock:key"
    _del(key)
    with redis_lock(key, ttl=30):
        try:
            with redis_lock(key, ttl=30):
                pass
            raise AssertionError("应抛 LockBusy")
        except LockBusy as e:
            assert e.key == key
    _del(key)


def test_release_only_deletes_own_token(monkeypatch):
    """CAS 释放：TTL 过期后他人重新持有，原持有者退出不得误删他人锁。"""
    import redis

    from app.core.settings import settings

    key = "test:lock:cas"
    r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    _del(key)

    cm = redis_lock(key, ttl=30)
    cm.__enter__()
    # 模拟锁过期后被他人重新持有：直接覆盖为他人 token
    r.set(key, "other-holder-token")
    cm.__exit__(None, None, None)  # 原持有者释放 —— 不应删掉他人的锁
    assert r.get(key) == "other-holder-token"
    _del(key)
