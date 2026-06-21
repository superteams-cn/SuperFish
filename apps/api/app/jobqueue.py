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
from .core.logger import get_logger
from .core.settings import settings

logger = get_logger("superfish.jobqueue")

# 作业名 → (arq worker 函数名, 同步业务函数)
# arq 函数名与 worker.py 中注册的协程名一致。
# 模拟启动已入队：控制面(stop/interview/IPC)走 Redis 总线（见 simulation_ipc），
# 故子进程可由独立 worker 持有，API 任意副本仍能控制 —— 实现计算面横向扩展。
# 队列不可用时回退本地线程（_run_inline），等价于早期 API 进程内 Popen 的单机行为。
_JOBS = {
    "graph_build": ("graph_build_job", jobs.run_graph_build),
    "report_generate": ("report_generate_job", jobs.run_report_generate),
    "simulation_run": ("simulation_run_job", jobs.run_simulation_launch),
}


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


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
