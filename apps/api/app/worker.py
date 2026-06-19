"""
arq worker —— 独立进程消费 Redis 队列，执行长任务（图谱构建/报告生成/模拟）。

启动方式：``arq app.worker.WorkerSettings``（docker-compose 中为 worker 服务）。
每个 arq 协程把同步业务逻辑丢到线程池执行，避免阻塞事件循环。
"""

import asyncio

from arq.connections import RedisSettings

from . import jobs
from .config import Config
from .utils.logger import get_logger, setup_logger

logger = get_logger("superfish.worker")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(Config.REDIS_URL)


async def graph_build_job(ctx, **kwargs) -> None:
    await asyncio.to_thread(jobs.run_graph_build, **kwargs)


async def report_generate_job(ctx, **kwargs) -> None:
    await asyncio.to_thread(jobs.run_report_generate, **kwargs)


async def startup(ctx) -> None:
    setup_logger("superfish")
    logger.info("worker 启动：初始化数据库与对象存储")
    from .db import init_db
    from .utils import object_store

    try:
        init_db()
    except Exception as exc:
        logger.error(f"worker 初始化数据库失败: {exc}")
        raise
    try:
        object_store.ensure_bucket()
    except Exception as exc:
        logger.warning(f"worker 初始化对象存储失败（忽略）: {exc}")


async def shutdown(ctx) -> None:
    logger.info("worker 关闭")


class WorkerSettings:
    """arq worker 配置。"""

    functions = [graph_build_job, report_generate_job]
    redis_settings = _redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    # 单作业超时放宽以容纳长任务（报告/图谱）；模拟类作业在 Commit B 处理
    job_timeout = 60 * 60 * 6
    keep_result = 60 * 30
