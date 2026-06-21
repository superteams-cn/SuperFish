"""模拟领域模型（纯数据类，无 IO / 无 DB 依赖）。"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SimulationStatus(StrEnum):
    """模拟状态"""

    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"  # 模拟被手动停止
    COMPLETED = "completed"  # 模拟自然完成
    FAILED = "failed"


class PlatformType(StrEnum):
    """平台类型"""

    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    """模拟状态"""

    simulation_id: str
    project_id: str
    graph_id: str

    # 所属用户（从所属项目继承）
    user_id: str = ""

    # 平台启用状态
    enable_twitter: bool = True
    enable_reddit: bool = True

    # 状态
    status: SimulationStatus = SimulationStatus.CREATED

    # 准备阶段数据
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: list[str] = field(default_factory=list)

    # 配置生成信息
    config_generated: bool = False
    config_reasoning: str = ""

    # 历史列表冗余字段（准备阶段从 simulation_config 落库，供首页历史批量读取）
    simulation_requirement: str = ""
    total_simulation_hours: int = 0
    minutes_per_round: int = 0

    # 运行时数据
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"

    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 错误信息
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """完整状态字典（内部使用）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "simulation_requirement": self.simulation_requirement,
            "total_simulation_hours": self.total_simulation_hours,
            "minutes_per_round": self.minutes_per_round,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }

    def to_simple_dict(self) -> dict[str, Any]:
        """简化状态字典（API返回使用）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "error": self.error,
        }
