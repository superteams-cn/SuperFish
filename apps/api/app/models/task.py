"""
任务状态管理
用于跟踪长时间运行的任务（如图谱构建）。

存储采用「内存为主 + Redis 镜像」双层策略：
- 内存：保证单进程内读写一致与线程安全（沿用原有语义）；
- Redis：持久化镜像，使任务状态在服务重启 / 跨进程后仍可恢复。
当 Redis 不可用时自动回退为纯内存模式，不影响源码部署的开箱即用。
"""

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from ..utils.locale import t
from ..utils.logger import get_logger

logger = get_logger("superfish.task")

# Redis key 前缀与过期时间（与内存清理周期保持一致，避免无限堆积）
_TASK_KEY_PREFIX = "superfish:task:"
_TASK_TTL_SECONDS = 24 * 3600


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """从字典（Redis JSON）还原任务对象"""
        return cls(
            task_id=data["task_id"],
            task_type=data.get("task_type", ""),
            status=TaskStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            progress=data.get("progress", 0),
            message=data.get("message", ""),
            result=data.get("result"),
            error=data.get("error"),
            metadata=data.get("metadata") or {},
            progress_detail=data.get("progress_detail") or {},
        )


class TaskManager:
    """
    任务管理器
    线程安全的任务状态管理（内存 + 可选 Redis 持久化）。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_backend()
        return cls._instance

    def _init_backend(self) -> None:
        """初始化存储后端：内存兜底 + 尝试连接 Redis。"""
        self._task_lock = threading.Lock()
        self._tasks: dict[str, Task] = {}  # 进程内缓存 / Redis 不可用时的兜底
        self._redis = None
        try:
            import redis

            from ..config import Config

            client = redis.Redis.from_url(
                Config.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            self._redis = client
            logger.info(f"TaskManager 启用 Redis 持久化: {Config.REDIS_URL}")
        except Exception as exc:
            logger.warning(f"Redis 不可用，TaskManager 回退为纯内存存储: {exc}")
            self._redis = None

    # ============== Redis 持久化辅助 ==============

    @staticmethod
    def _key(task_id: str) -> str:
        return f"{_TASK_KEY_PREFIX}{task_id}"

    def _save(self, task: Task) -> None:
        """内存写入 + Redis 镜像（Redis 失败不影响内存写入）。"""
        self._tasks[task.task_id] = task
        if self._redis is not None:
            try:
                self._redis.set(
                    self._key(task.task_id),
                    json.dumps(task.to_dict(), ensure_ascii=False),
                    ex=_TASK_TTL_SECONDS,
                )
            except Exception as exc:
                logger.warning(f"任务写入 Redis 失败（内存仍保留）: {exc}")

    def _load(self, task_id: str) -> Task | None:
        """优先读内存；未命中则从 Redis 回填（支持重启后恢复）。"""
        task = self._tasks.get(task_id)
        if task is not None:
            return task
        if self._redis is not None:
            try:
                raw = self._redis.get(self._key(task_id))
                if raw:
                    task = Task.from_dict(json.loads(raw))
                    self._tasks[task_id] = task  # 回填内存缓存
                    return task
            except Exception as exc:
                logger.warning(f"任务从 Redis 读取失败: {exc}")
        return None

    # ============== 任务操作 ==============

    def create_task(self, task_type: str, metadata: dict | None = None) -> str:
        """
        创建新任务

        Args:
            task_type: 任务类型
            metadata: 额外元数据

        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())
        now = datetime.now()

        task = Task(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        with self._task_lock:
            self._save(task)

        return task_id

    def get_task(self, task_id: str) -> Task | None:
        """获取任务"""
        with self._task_lock:
            return self._load(task_id)

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
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态
            progress: 进度
            message: 消息
            result: 结果
            error: 错误信息
            progress_detail: 详细进度信息
        """
        with self._task_lock:
            task = self._load(task_id)
            if task:
                task.updated_at = datetime.now()
                if status is not None:
                    task.status = status
                if progress is not None:
                    task.progress = progress
                if message is not None:
                    task.message = message
                if result is not None:
                    task.result = result
                if error is not None:
                    task.error = error
                if progress_detail is not None:
                    task.progress_detail = progress_detail
                self._save(task)

    def complete_task(self, task_id: str, result: dict):
        """标记任务完成"""
        self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=t("progress.taskComplete"),
            result=result,
        )

    def fail_task(self, task_id: str, error: str):
        """标记任务失败"""
        self.update_task(
            task_id, status=TaskStatus.FAILED, message=t("progress.taskFailed"), error=error
        )

    def list_tasks(self, task_type: str | None = None) -> list:
        """列出任务（合并内存与 Redis 中的任务）"""
        with self._task_lock:
            tasks_by_id: dict[str, Task] = dict(self._tasks)
            if self._redis is not None:
                try:
                    for key in self._redis.scan_iter(f"{_TASK_KEY_PREFIX}*"):
                        tid = key[len(_TASK_KEY_PREFIX) :]
                        if tid in tasks_by_id:
                            continue
                        raw = self._redis.get(key)
                        if raw:
                            tasks_by_id[tid] = Task.from_dict(json.loads(raw))
                except Exception as exc:
                    logger.warning(f"列举 Redis 任务失败: {exc}")

            tasks = list(tasks_by_id.values())
            if task_type:
                tasks = [tk for tk in tasks if tk.task_type == task_type]
            return [tk.to_dict() for tk in sorted(tasks, key=lambda x: x.created_at, reverse=True)]

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理旧任务（内存 + Redis）"""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        with self._task_lock:
            old_ids = [
                tid
                for tid, task in self._tasks.items()
                if task.created_at < cutoff
                and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
            ]
            for tid in old_ids:
                del self._tasks[tid]
                if self._redis is not None:
                    try:
                        self._redis.delete(self._key(tid))
                    except Exception as exc:
                        logger.warning(f"删除 Redis 任务失败: {exc}")
