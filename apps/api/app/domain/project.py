"""项目领域模型（纯数据类，无 IO / 无 DB 依赖）。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..core.settings import settings


class ProjectStatus(StrEnum):
    """项目状态"""

    CREATED = "created"  # 刚创建，文件已上传
    ONTOLOGY_GENERATED = "ontology_generated"  # 本体已生成
    GRAPH_BUILDING = "graph_building"  # 图谱构建中
    GRAPH_COMPLETED = "graph_completed"  # 图谱构建完成
    FAILED = "failed"  # 失败


class ProjectKind(StrEnum):
    """推演类型：决定本体/报告走哪套模板，以及中段引擎如何分派。

    新增类型时只追加枚举值；存量数据缺该字段时一律回落 SOCIAL_OPINION，旧流程零改动。
    """

    SOCIAL_OPINION = "social_opinion"  # 社交媒体舆论模拟（原有默认流程）
    NARRATIVE = "narrative"  # 剧本/小说剧情拆解 + 推演


@dataclass
class Project:
    """项目数据模型"""

    project_id: str
    name: str
    status: ProjectStatus
    created_at: str
    updated_at: str

    # 推演类型（决定本体/报告模板与引擎分派）；存量数据回落社媒舆论模拟
    kind: str = ProjectKind.SOCIAL_OPINION.value

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
            "kind": self.kind,
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
            kind=data.get("kind") or ProjectKind.SOCIAL_OPINION.value,
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
