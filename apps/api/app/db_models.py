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


class SimulationRow(Base):
    """模拟元数据表（运行时产物仍在节点本地，详见 simulation_runner）。"""

    __tablename__ = "simulations"

    simulation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    graph_id: Mapped[str] = mapped_column(String(64), default="")

    enable_twitter: Mapped[bool] = mapped_column(default=True)
    enable_reddit: Mapped[bool] = mapped_column(default=True)

    status: Mapped[str] = mapped_column(String(32), index=True, default="created")

    entities_count: Mapped[int] = mapped_column(Integer, default=0)
    profiles_count: Mapped[int] = mapped_column(Integer, default=0)
    entity_types: Mapped[list] = mapped_column(JSONB, default=list)

    config_generated: Mapped[bool] = mapped_column(default=False)
    config_reasoning: Mapped[str] = mapped_column(Text, default="")

    current_round: Mapped[int] = mapped_column(Integer, default=0)
    twitter_status: Mapped[str] = mapped_column(String(32), default="not_started")
    reddit_status: Mapped[str] = mapped_column(String(32), default="not_started")

    created_at: Mapped[str] = mapped_column(String(40), default="", index=True)
    updated_at: Mapped[str] = mapped_column(String(40), default="")

    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReportRow(Base):
    """报告记录表（元数据 + 大纲 + 进度 + 章节 + 完整 markdown）。

    生成期的 append 日志（agent_log.jsonl / console_log.txt）仍属运行节点本地。
    """

    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    simulation_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    graph_id: Mapped[str] = mapped_column(String(64), default="")
    simulation_requirement: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")

    outline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sections: Mapped[list] = mapped_column(JSONB, default=list)
    progress: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    markdown_content: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[str] = mapped_column(String(40), default="", index=True)
    completed_at: Mapped[str] = mapped_column(String(40), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SimulationRunStateRow(Base):
    """模拟运行时状态（实时进度/动作计数等），存整份 detail dict 以便任意副本观测。

    运行中的子进程仍绑定在拥有它的进程/节点；本表仅用于跨副本「读」进度。
    """

    __tablename__ = "simulation_run_states"

    simulation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[str] = mapped_column(String(40), default="")
