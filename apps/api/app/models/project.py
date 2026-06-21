"""项目上下文管理（服务层）。

分层：
- 领域模型 ``Project`` / ``ProjectStatus`` 定义在 ``app.domain.project``（此处 re-export，
  保持 ``from ..models.project import Project, ProjectStatus`` 的历史导入不变）；
- Postgres 数据访问下沉到 ``app.repositories.project_repo.ProjectRepository``；
- ``ProjectManager`` 仅保留服务级编排：对象存储（文件/文本）、删除级联的非 SQL 善后。
"""

import uuid
from datetime import datetime
from typing import Any

# re-export 领域模型，保持对外导入路径不变
from ..domain.project import Project, ProjectStatus
from ..repositories.project_repo import ProjectRepository
from ..utils import object_store

__all__ = ["Project", "ProjectStatus", "ProjectManager"]


class ProjectManager:
    """项目服务：元数据经 ProjectRepository 持久化，文件/文本走对象存储。"""

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

    # ============== 元数据 CRUD（委托 ProjectRepository）==============

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
        ProjectRepository.save(project)

    @classmethod
    def get_project(cls, project_id: str) -> Project | None:
        """获取项目，不存在返回 None。"""
        return ProjectRepository.get(project_id)

    @classmethod
    def list_projects(cls, limit: int = 50, user_id: str | None = None) -> list[Project]:
        """列出项目，按创建时间倒序；传 user_id 时只返回该用户的项目。"""
        return ProjectRepository.list(limit=limit, user_id=user_id)

    @classmethod
    def get_projects_bulk(cls, project_ids: list[str]) -> dict[str, Project]:
        """批量获取项目（单次查询），返回 {project_id: Project}，用于首页历史避免 N+1。"""
        return ProjectRepository.get_bulk(project_ids)

    @classmethod
    def count_projects(cls, user_id: str) -> int:
        """统计某用户名下项目数（用于配额校验）。"""
        return ProjectRepository.count(user_id)

    @classmethod
    def user_owns_graph(cls, graph_id: str, user_id: str) -> bool:
        """判断某 graph_id 是否属于该用户（其名下的项目或模拟引用了它）。"""
        return ProjectRepository.user_owns_graph(graph_id, user_id)

    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        """删除项目及其级联数据：模拟、运行态、报告（SQL 由 repo 事务完成），
        以及知识图谱与对象存储文件（事务外善后，单点失败不影响元数据删除）。
        """
        existed, graph_ids, sim_ids = ProjectRepository.delete_cascade(project_id)
        if not existed:
            return False

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
