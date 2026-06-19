"""
任务状态管理
用于跟踪长时间运行的任务（如图谱构建）。

存储后端：Postgres（tasks 表）。任务状态在服务重启 / 跨进程 / 多副本间共享，
不再依赖进程内存。对外保持原有接口，调用方无需改动。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import delete

from ..db import session_scope
from ..db_models import TaskRow
from ..utils.locale import t


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


def _row_to_task(row: TaskRow) -> Task:
    return Task(
        task_id=row.task_id,
        task_type=row.task_type,
        status=TaskStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        progress=row.progress,
        message=row.message,
        result=row.result,
        error=row.error,
        metadata=row.task_metadata or {},
        progress_detail=row.progress_detail or {},
    )


class TaskManager:
    """任务管理器（Postgres 持久化）。"""

    def create_task(self, task_type: str, metadata: dict | None = None) -> str:
        """创建新任务，返回任务ID。"""
        task_id = str(uuid.uuid4())
        now = datetime.now()
        with session_scope() as session:
            session.add(
                TaskRow(
                    task_id=task_id,
                    task_type=task_type,
                    status=TaskStatus.PENDING.value,
                    created_at=now,
                    updated_at=now,
                    progress=0,
                    message="",
                    task_metadata=metadata or {},
                    progress_detail={},
                )
            )
        return task_id

    def get_task(self, task_id: str) -> Task | None:
        """获取任务。"""
        with session_scope() as session:
            row = session.get(TaskRow, task_id)
            return _row_to_task(row) if row else None

    def update_task(
        self,
        task_id: str,
        status: TaskStatus | None = None,
        progress: int | None = None,
        message: str | None = None,
        result: dict | None = None,
        error: str | None = None,
        progress_detail: dict | None = None,
    ):
        """更新任务状态（读-改-写在单事务内完成）。"""
        with session_scope() as session:
            row = session.get(TaskRow, task_id)
            if row is None:
                return
            row.updated_at = datetime.now()
            if status is not None:
                row.status = status.value if isinstance(status, TaskStatus) else status
            if progress is not None:
                row.progress = progress
            if message is not None:
                row.message = message
            if result is not None:
                row.result = result
            if error is not None:
                row.error = error
            if progress_detail is not None:
                row.progress_detail = progress_detail

    def complete_task(self, task_id: str, result: dict):
        """标记任务完成。"""
        self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=t("progress.taskComplete"),
            result=result,
        )

    def fail_task(self, task_id: str, error: str):
        """标记任务失败。"""
        self.update_task(
            task_id, status=TaskStatus.FAILED, message=t("progress.taskFailed"), error=error
        )

    def list_tasks(self, task_type: str | None = None) -> list:
        """列出任务，按创建时间倒序。"""
        with session_scope() as session:
            query = session.query(TaskRow)
            if task_type:
                query = query.filter(TaskRow.task_type == task_type)
            rows = query.order_by(TaskRow.created_at.desc()).all()
            return [_row_to_task(r).to_dict() for r in rows]

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理已完成/失败的旧任务。"""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        with session_scope() as session:
            session.execute(
                delete(TaskRow)
                .where(TaskRow.created_at < cutoff)
                .where(TaskRow.status.in_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]))
            )
