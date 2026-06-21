"""任务仓储：tasks 表的全部数据访问（session_scope + 行<->领域映射）。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete

from ..core.db import session_scope
from ..db_models import TaskRow
from ..domain.task import Task, TaskStatus


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


class TaskRepository:
    """tasks 表数据访问。"""

    @staticmethod
    def create(task_id: str, task_type: str, metadata: dict | None = None) -> None:
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

    @staticmethod
    def get(task_id: str) -> Task | None:
        with session_scope() as session:
            row = session.get(TaskRow, task_id)
            return _row_to_task(row) if row else None

    @staticmethod
    def update(
        task_id: str,
        status: TaskStatus | str | None = None,
        progress: int | None = None,
        message: str | None = None,
        result: dict | None = None,
        error: str | None = None,
        progress_detail: dict | None = None,
    ) -> None:
        """读-改-写在单事务内完成；任务不存在则静默返回。"""
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

    @staticmethod
    def list(task_type: str | None = None) -> list[Task]:
        with session_scope() as session:
            query = session.query(TaskRow)
            if task_type:
                query = query.filter(TaskRow.task_type == task_type)
            rows = query.order_by(TaskRow.created_at.desc()).all()
            return [_row_to_task(r) for r in rows]

    @staticmethod
    def delete_old(max_age_hours: int = 24) -> None:
        """清理已完成/失败的旧任务。"""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        with session_scope() as session:
            session.execute(
                delete(TaskRow)
                .where(TaskRow.created_at < cutoff)
                .where(TaskRow.status.in_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]))
            )
