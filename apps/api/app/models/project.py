"""
项目上下文管理
在服务端持久化项目状态，避免前端在接口间传递大量数据。

存储后端：
- 元数据 → Postgres（projects 表）；
- 上传文件与提取文本 → S3 兼容对象存储（RustFS）。
对外仍保持原有 classmethod 接口，调用方无需改动。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..db import session_scope
from ..db_models import ProjectRow
from ..settings import settings
from ..utils import object_store


class ProjectStatus(StrEnum):
    """项目状态"""

    CREATED = "created"  # 刚创建，文件已上传
    ONTOLOGY_GENERATED = "ontology_generated"  # 本体已生成
    GRAPH_BUILDING = "graph_building"  # 图谱构建中
    GRAPH_COMPLETED = "graph_completed"  # 图谱构建完成
    FAILED = "failed"  # 失败


@dataclass
class Project:
    """项目数据模型"""

    project_id: str
    name: str
    status: ProjectStatus
    created_at: str
    updated_at: str

    # 所属用户（数据隔离归属根）
    user_id: str = ""

    # 文件信息
    files: list[dict[str, Any]] = field(default_factory=list)  # [{filename, size, s3_key}]
    total_text_length: int = 0

    # 本体信息（接口1生成后填充）
    ontology: dict[str, Any] | None = None
    analysis_summary: str | None = None

    # 图谱信息（接口2完成后填充）
    graph_id: str | None = None
    graph_build_task_id: str | None = None

    # 配置
    simulation_requirement: str | None = None
    chunk_size: int = field(default_factory=lambda: settings.default_chunk_size)
    chunk_overlap: int = field(default_factory=lambda: settings.default_chunk_overlap)

    # 错误信息
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "project_id": self.project_id,
            "user_id": self.user_id,
            "name": self.name,
            "status": self.status.value if isinstance(self.status, ProjectStatus) else self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "files": self.files,
            "total_text_length": self.total_text_length,
            "ontology": self.ontology,
            "analysis_summary": self.analysis_summary,
            "graph_id": self.graph_id,
            "graph_build_task_id": self.graph_build_task_id,
            "simulation_requirement": self.simulation_requirement,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        """从字典创建"""
        status = data.get("status", "created")
        if isinstance(status, str):
            status = ProjectStatus(status)

        return cls(
            project_id=data["project_id"],
            user_id=data.get("user_id", ""),
            name=data.get("name", "Unnamed Project"),
            status=status,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            files=data.get("files", []),
            total_text_length=data.get("total_text_length", 0),
            ontology=data.get("ontology"),
            analysis_summary=data.get("analysis_summary"),
            graph_id=data.get("graph_id"),
            graph_build_task_id=data.get("graph_build_task_id"),
            simulation_requirement=data.get("simulation_requirement"),
            chunk_size=data.get("chunk_size", settings.default_chunk_size),
            chunk_overlap=data.get("chunk_overlap", settings.default_chunk_overlap),
            error=data.get("error"),
        )


def _row_to_project(row: ProjectRow) -> Project:
    return Project(
        project_id=row.project_id,
        user_id=row.user_id or "",
        name=row.name,
        status=ProjectStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        files=row.files or [],
        total_text_length=row.total_text_length,
        ontology=row.ontology,
        analysis_summary=row.analysis_summary,
        graph_id=row.graph_id,
        graph_build_task_id=row.graph_build_task_id,
        simulation_requirement=row.simulation_requirement,
        chunk_size=row.chunk_size,
        chunk_overlap=row.chunk_overlap,
        error=row.error,
    )


def _apply_project_to_row(project: Project, row: ProjectRow) -> None:
    status = project.status
    row.user_id = project.user_id
    row.name = project.name
    row.status = status.value if isinstance(status, ProjectStatus) else status
    row.created_at = project.created_at
    row.updated_at = project.updated_at
    row.files = project.files
    row.total_text_length = project.total_text_length
    row.ontology = project.ontology
    row.analysis_summary = project.analysis_summary
    row.graph_id = project.graph_id
    row.graph_build_task_id = project.graph_build_task_id
    row.simulation_requirement = project.simulation_requirement
    row.chunk_size = project.chunk_size
    row.chunk_overlap = project.chunk_overlap
    row.error = project.error


class ProjectManager:
    """项目管理器 - 负责项目的持久化存储和检索（Postgres + 对象存储）。"""

    # ============== 对象存储 key 规则 ==============

    @staticmethod
    def _files_key(project_id: str, saved_filename: str) -> str:
        return f"projects/{project_id}/files/{saved_filename}"

    @staticmethod
    def _text_key(project_id: str) -> str:
        return f"projects/{project_id}/extracted_text.txt"

    @staticmethod
    def _project_prefix(project_id: str) -> str:
        return f"projects/{project_id}/"

    # ============== 元数据 CRUD ==============

    @classmethod
    def create_project(cls, name: str = "Unnamed Project", user_id: str = "") -> Project:
        """创建新项目并落库。"""
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        project = Project(
            project_id=project_id,
            user_id=user_id,
            name=name,
            status=ProjectStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
        cls.save_project(project)
        return project

    @classmethod
    def save_project(cls, project: Project) -> None:
        """保存项目元数据（upsert）。"""
        project.updated_at = datetime.now().isoformat()
        with session_scope() as session:
            row = session.get(ProjectRow, project.project_id)
            if row is None:
                row = ProjectRow(project_id=project.project_id)
                _apply_project_to_row(project, row)
                session.add(row)
            else:
                _apply_project_to_row(project, row)

    @classmethod
    def get_project(cls, project_id: str) -> Project | None:
        """获取项目，不存在返回 None。"""
        with session_scope() as session:
            row = session.get(ProjectRow, project_id)
            return _row_to_project(row) if row else None

    @classmethod
    def list_projects(cls, limit: int = 50, user_id: str | None = None) -> list[Project]:
        """列出项目，按创建时间倒序；传 user_id 时只返回该用户的项目。"""
        with session_scope() as session:
            query = session.query(ProjectRow)
            if user_id is not None:
                query = query.filter(ProjectRow.user_id == user_id)
            rows = query.order_by(ProjectRow.created_at.desc()).limit(limit).all()
            return [_row_to_project(r) for r in rows]

    @classmethod
    def count_projects(cls, user_id: str) -> int:
        """统计某用户名下项目数（用于配额校验）。"""
        with session_scope() as session:
            return session.query(ProjectRow).filter(ProjectRow.user_id == user_id).count()

    @classmethod
    def user_owns_graph(cls, graph_id: str, user_id: str) -> bool:
        """判断某 graph_id 是否属于该用户（其名下的项目或模拟引用了它）。"""
        if not graph_id:
            return False
        from ..db_models import SimulationRow

        with session_scope() as session:
            owned = (
                session.query(ProjectRow.project_id)
                .filter(ProjectRow.graph_id == graph_id, ProjectRow.user_id == user_id)
                .first()
            )
            if owned:
                return True
            owned_sim = (
                session.query(SimulationRow.simulation_id)
                .filter(SimulationRow.graph_id == graph_id, SimulationRow.user_id == user_id)
                .first()
            )
            return owned_sim is not None

    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        """删除项目及其级联数据：模拟、运行态、报告、知识图谱与对象存储文件。

        兼容「项目行已被删除但模拟/图谱成为孤儿」的情形——只要清理到任一关联数据
        即视为成功，避免历史列表里残留无法删除的孤儿记录。
        """
        from ..db_models import ReportRow, SimulationRow, SimulationRunStateRow

        graph_ids: set[str] = set()
        sim_ids: list[str] = []
        with session_scope() as session:
            row = session.get(ProjectRow, project_id)
            if row is not None and row.graph_id:
                graph_ids.add(row.graph_id)

            sims = session.query(SimulationRow).filter(SimulationRow.project_id == project_id).all()
            sim_ids = [s.simulation_id for s in sims]
            for s in sims:
                if s.graph_id:
                    graph_ids.add(s.graph_id)

            if sim_ids:
                session.query(ReportRow).filter(ReportRow.simulation_id.in_(sim_ids)).delete(
                    synchronize_session=False
                )
                session.query(SimulationRunStateRow).filter(
                    SimulationRunStateRow.simulation_id.in_(sim_ids)
                ).delete(synchronize_session=False)
                session.query(SimulationRow).filter(
                    SimulationRow.simulation_id.in_(sim_ids)
                ).delete(synchronize_session=False)

            existed = row is not None or bool(sim_ids)
            if row is not None:
                session.delete(row)

        if not existed:
            return False

        # 以下均在事务外，单点失败不影响元数据删除
        for gid in graph_ids:
            try:
                from ..services.graph_builder import GraphBuilderService

                GraphBuilderService().delete_graph(gid)
            except Exception:
                pass
        try:
            object_store.delete_prefix(cls._project_prefix(project_id))
        except Exception:
            pass
        for sid in sim_ids:
            try:
                object_store.delete_prefix(f"simulations/{sid}/")
            except Exception:
                pass
        return True

    # ============== 文件 / 文本（对象存储） ==============

    @classmethod
    def save_file_to_project(
        cls, project_id: str, file_bytes: bytes, original_filename: str
    ) -> dict[str, Any]:
        """保存上传文件到对象存储，返回文件信息（含 s3_key）。"""
        import os

        ext = os.path.splitext(original_filename)[1].lower()
        saved_filename = f"{uuid.uuid4().hex[:8]}{ext}"
        key = cls._files_key(project_id, saved_filename)
        object_store.put_bytes(key, file_bytes)
        return {
            "original_filename": original_filename,
            "saved_filename": saved_filename,
            "s3_key": key,
            "size": len(file_bytes),
        }

    @classmethod
    def save_extracted_text(cls, project_id: str, text: str) -> None:
        """保存提取文本到对象存储。"""
        object_store.put_text(cls._text_key(project_id), text)

    @classmethod
    def get_extracted_text(cls, project_id: str) -> str | None:
        """从对象存储读取提取文本。"""
        return object_store.get_text(cls._text_key(project_id))

    @classmethod
    def get_project_files(cls, project_id: str) -> list[str]:
        """返回项目所有文件的对象存储 key。"""
        project = cls.get_project(project_id)
        if not project:
            return []
        return [f["s3_key"] for f in project.files if f.get("s3_key")]
