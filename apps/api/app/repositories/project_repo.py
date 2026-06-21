"""项目仓储：projects 表的全部数据访问（session_scope + 行<->领域映射）。

只负责 Postgres 读写并收发 ``Project`` 领域对象；对象存储 / 图谱 / 跨实体编排
留在 ``ProjectManager`` 服务层。
"""

from __future__ import annotations  # 延迟注解求值：避免 list() 方法遮蔽 list[str] 注解

from datetime import datetime

from ..core.db import session_scope
from ..db_models import ProjectRow
from ..domain.project import Project, ProjectStatus


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


class ProjectRepository:
    """projects 表数据访问。"""

    @staticmethod
    def save(project: Project) -> None:
        """保存项目元数据（upsert）。写入前刷新 updated_at。"""
        project.updated_at = datetime.now().isoformat()
        with session_scope() as session:
            row = session.get(ProjectRow, project.project_id)
            if row is None:
                row = ProjectRow(project_id=project.project_id)
                _apply_project_to_row(project, row)
                session.add(row)
            else:
                _apply_project_to_row(project, row)

    @staticmethod
    def get(project_id: str) -> Project | None:
        with session_scope() as session:
            row = session.get(ProjectRow, project_id)
            return _row_to_project(row) if row else None

    @staticmethod
    def list(limit: int = 50, user_id: str | None = None) -> list[Project]:
        with session_scope() as session:
            query = session.query(ProjectRow)
            if user_id is not None:
                query = query.filter(ProjectRow.user_id == user_id)
            rows = query.order_by(ProjectRow.created_at.desc()).limit(limit).all()
            return [_row_to_project(r) for r in rows]

    @staticmethod
    def get_bulk(project_ids: list[str]) -> dict[str, Project]:
        if not project_ids:
            return {}
        with session_scope() as session:
            rows = session.query(ProjectRow).filter(ProjectRow.project_id.in_(project_ids)).all()
            return {r.project_id: _row_to_project(r) for r in rows}

    @staticmethod
    def count(user_id: str) -> int:
        with session_scope() as session:
            return session.query(ProjectRow).filter(ProjectRow.user_id == user_id).count()

    @staticmethod
    def user_owns_graph(graph_id: str, user_id: str) -> bool:
        """该 graph_id 是否被此用户名下的项目或模拟引用。"""
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

    @staticmethod
    def delete_cascade(project_id: str) -> tuple[bool, set[str], list[str]]:
        """事务内级联删除 project 行及其 simulations/run_states/reports 行。

        返回 ``(existed, graph_ids, sim_ids)``：调用方据此在事务外清理对象存储与图谱。
        兼容「项目行已删但模拟/图谱成孤儿」——清理到任一关联即视为存在。
        """
        from ..db_models import ReportRow, SimulationRow, SimulationRunStateRow

        graph_ids: set[str] = set()
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

        return existed, graph_ids, sim_ids
