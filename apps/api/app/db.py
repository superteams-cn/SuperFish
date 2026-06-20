"""
数据库层（Postgres + SQLAlchemy 2.0 同步引擎）。

设计要点：
- 同步引擎 + 连接池，可在 FastAPI 同步路由及后台线程中安全使用；
- 通过 ``session_scope()`` 上下文管理器提供「每操作一会话」的事务边界；
- ``init_db()`` 在应用启动时建表（幂等）。
"""

import contextlib
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import settings
from .utils.logger import get_logger

logger = get_logger("superfish.db")


class Base(DeclarativeBase):
    """ORM 基类。"""


# 连接池 + pre_ping（自动剔除失效连接，避免长时间空闲后报错）
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextlib.contextmanager
def session_scope() -> Iterator[Session]:
    """提供一个带自动提交/回滚的事务性会话。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """建表（幂等）。在应用启动时调用。"""
    # 导入以注册 ORM 模型到 Base.metadata
    from . import db_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_add_user_id()
    logger.info("数据库表已就绪（Postgres）")


def _migrate_add_user_id() -> None:
    """补列迁移：create_all 不会给「已存在的表」加列，故对三张业务表
    幂等地补 user_id 列与索引（Postgres 支持 IF NOT EXISTS）。"""
    from sqlalchemy import text

    stmts = []
    for table in ("projects", "simulations", "reports"):
        stmts.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) NOT NULL DEFAULT ''"
        )
        stmts.append(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON {table} (user_id)"
        )
    with engine.begin() as conn:
        for s in stmts:
            conn.execute(text(s))
