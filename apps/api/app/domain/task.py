"""任务领域模型（纯数据类，无 IO / 无 DB 依赖）。"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    """任务状态枚举"""

    PENDING = "pending"  # 等待中
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


@dataclass
class Task:
    """任务数据类"""

    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: int = 0  # 总进度百分比 0-100
    message: str = ""  # 状态消息
    result: dict | None = None  # 任务结果
    error: str | None = None  # 错误信息
    metadata: dict = field(default_factory=dict)  # 额外元数据
    progress_detail: dict = field(default_factory=dict)  # 详细进度信息

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": self.progress,
            "message": self.message,
            "progress_detail": self.progress_detail,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }
