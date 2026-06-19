"""
作业入队封装。

API（同步路由）调用 ``enqueue(job_name, **kwargs)`` 把长任务投递到 arq(Redis)
队列，由独立 worker 进程消费 —— 从而 API 无后台线程、可水平扩展，作业可跨副本执行。

兜底：当队列不可用（Redis 未启动 / 未部署 worker）时，回退到本地后台线程直接
运行同一份同步业务逻辑，保证单机开发与测试不受影响。
"""

import asyncio
import threading

from arq import create_pool
from arq.connections import RedisSettings

from . import jobs
from .config import Config
from .utils.logger import get_logger

logger = get_logger("superfish.jobqueue")

# 作业名 → (arq worker 函数名, 同步业务函数)
# arq 函数名与 worker.py 中注册的协程名一致。
# 注：模拟启动未入队 —— 其控制面(stop/interview/IPC)与子进程同进程绑定，
# 拆到独立 worker 需要跨进程命令路由层，故模拟仍在拥有子进程的进程内执行。
_JOBS = {
    "graph_build": ("graph_build_job", jobs.run_graph_build),
    "report_generate": ("report_generate_job", jobs.run_report_generate),
}


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(Config.REDIS_URL)


def _run_inline(sync_fn, kwargs: dict) -> None:
    """队列不可用时的兜底：本地后台线程执行同步业务逻辑。"""
    thread = threading.Thread(target=lambda: sync_fn(**kwargs), daemon=True)
    thread.start()


def enqueue(job_name: str, **kwargs) -> str | None:
    """把作业投递到 arq 队列；失败则回退本地线程。

    Returns:
        arq job_id；走兜底线程时返回 None。
    """
    entry = _JOBS.get(job_name)
    if entry is None:
        raise ValueError(f"unknown job: {job_name}")
    arq_func_name, sync_fn = entry

    try:

        async def _do() -> str | None:
            redis = await create_pool(_redis_settings())
            try:
                job = await redis.enqueue_job(arq_func_name, **kwargs)
                return job.job_id if job else None
            finally:
                await redis.close()

        job_id = asyncio.run(_do())
        logger.info(f"作业已入队: {job_name} -> job_id={job_id}")
        return job_id
    except Exception as exc:
        logger.warning(f"入队失败，回退本地线程执行 {job_name}: {exc}")
        if sync_fn is None:
            raise
        _run_inline(sync_fn, kwargs)
        return None
