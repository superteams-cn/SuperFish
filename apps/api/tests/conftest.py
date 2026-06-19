"""测试全局夹具：确保 Postgres 表已建好（不触碰对象存储）。

API 冒烟测试通过 TestClient 直接调用，不经过应用 lifespan，因此在这里
显式建表。需要本地/CI 提供 Postgres（CI 已配置 postgres service）。
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _init_database() -> None:
    from app.db import init_db

    init_db()
