"""SQLAlchemy ORM 模型（Postgres）。

仅承载「关系型元数据」；大文本与二进制文件存放于对象存储（见 utils/object_store.py）。
嵌套结构（files / ontology / result 等）以 JSONB 列存放。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ProjectRow(Base):
    """项目元数据表。"""

    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="Unnamed Project")
    status: Mapped[str] = mapped_column(String(32), index=True, default="created")
    # created_at/updated_at 沿用 ISO 字符串语义（与既有 to_dict 契约一致，便于字符串排序）
    created_at: Mapped[str] = mapped_column(String(40), default="", index=True)
    updated_at: Mapped[str] = mapped_column(String(40), default="")

    files: Mapped[list] = mapped_column(JSONB, default=list)
    total_text_length: Mapped[int] = mapped_column(Integer, default=0)

    ontology: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    graph_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    graph_build_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    simulation_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_size: Mapped[int] = mapped_column(Integer, default=500)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=50)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskRow(Base):
    """异步任务状态表。"""

    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(255), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    progress_detail: Mapped[dict] = mapped_column(JSONB, default=dict)
