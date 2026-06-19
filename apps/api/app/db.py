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

from .config import Config
from .utils.logger import get_logger

logger = get_logger("superfish.db")


class Base(DeclarativeBase):
    """ORM 基类。"""


# 连接池 + pre_ping（自动剔除失效连接，避免长时间空闲后报错）
engine = create_engine(
    Config.DATABASE_URL,
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
    logger.info("数据库表已就绪（Postgres）")
