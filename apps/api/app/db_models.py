"""SQLAlchemy ORM 模型（Postgres）。

仅承载「关系型元数据」；大文本与二进制文件存放于对象存储（见 utils/object_store.py）。
嵌套结构（files / ontology / result 等）以 JSONB 列存放。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .core.db import Base
from .core.settings import settings


class GraphRow(Base):
    """知识图谱存储表：整张图以两段 JSONB 存放。

    访问模式全是「取整张图」+ 应用层朴素打分（无多跳遍历），且单图极小（百级节点），
    故 Postgres JSONB 一行存下即可，无需独立图数据库、无在线单点。
    nodes: [{uuid,name,summary,labels,attributes}]；edges: [{uuid,name,fact,
    source_node_uuid,target_node_uuid,source_node_name,target_node_name,attributes,...}]。
    """

    __tablename__ = "graphs"

    graph_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    nodes: Mapped[list] = mapped_column(JSONB, default=list)
    edges: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")


class UserRow(Base):
    """用户账户表（邮箱+密码，纯个人账户）。

    密码以 PBKDF2 哈希串存储（见 utils/security.py），绝不存明文。
    """

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    display_name: Mapped[str] = mapped_column(String(64), default="")
    # active / disabled
    status: Mapped[str] = mapped_column(String(16), index=True, default="active")
    email_verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(String(40), default="", index=True)
    updated_at: Mapped[str] = mapped_column(String(40), default="")


class ProjectRow(Base):
    """项目元数据表。"""

    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 所属用户（数据隔离的归属根）；存量数据为空串
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="")
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
    chunk_size: Mapped[int] = mapped_column(Integer, default=lambda: settings.default_chunk_size)
    chunk_overlap: Mapped[int] = mapped_column(
        Integer, default=lambda: settings.default_chunk_overlap
    )

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
    # 所属用户（从所属项目继承），历史列表主查询走它
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="")
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

    # 历史列表冗余字段：准备阶段从 simulation_config 落库一份，避免首页历史逐条回源 S3
    simulation_requirement: Mapped[str] = mapped_column(Text, default="")
    total_simulation_hours: Mapped[int] = mapped_column(Integer, default=0)
    minutes_per_round: Mapped[int] = mapped_column(Integer, default=0)

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
    # 所属用户（从所属模拟继承，在后台 worker 创建时回填）
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="")
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
