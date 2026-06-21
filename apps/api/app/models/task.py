"""任务状态管理（服务层）。

分层：领域模型 ``Task`` / ``TaskStatus`` 在 ``app.domain.task``（此处 re-export）；
Postgres 数据访问下沉到 ``app.repositories.task_repo.TaskRepository``；
``TaskManager`` 仅保留服务级语义（生成 ID、本地化完成/失败消息）。
"""

import uuid

# re-export 领域模型，保持对外导入路径不变
from ..domain.task import Task, TaskStatus
from ..repositories.task_repo import TaskRepository
from ..utils.locale import t

__all__ = ["Task", "TaskStatus", "TaskManager"]


class TaskManager:
    """任务服务：状态经 TaskRepository 持久化（Postgres）。"""

    def create_task(self, task_type: str, metadata: dict | None = None) -> str:
        """创建新任务，返回任务ID。"""
        task_id = str(uuid.uuid4())
        TaskRepository.create(task_id, task_type, metadata)
        return task_id

    def get_task(self, task_id: str) -> Task | None:
        """获取任务。"""
        return TaskRepository.get(task_id)

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
        """更新任务状态。"""
        TaskRepository.update(
            task_id,
            status=status,
            progress=progress,
            message=message,
            result=result,
            error=error,
            progress_detail=progress_detail,
        )

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
        """列出任务，按创建时间倒序（返回 dict 列表，保持原接口）。"""
        return [task.to_dict() for task in TaskRepository.list(task_type)]

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理已完成/失败的旧任务。"""
        TaskRepository.delete_old(max_age_hours)
