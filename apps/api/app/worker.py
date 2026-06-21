"""
arq worker —— 独立进程消费 Redis 队列，执行长任务（图谱构建/报告生成/模拟）。

启动方式：``arq app.worker.WorkerSettings``（docker-compose 中为 worker 服务）。
每个 arq 协程把同步业务逻辑丢到线程池执行，避免阻塞事件循环。
"""

import asyncio

from arq import cron
from arq.connections import RedisSettings

from . import jobs
from .core.logger import get_logger, setup_logger
from .core.settings import settings

logger = get_logger("superfish.worker")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def graph_build_job(ctx, **kwargs) -> None:
    await asyncio.to_thread(jobs.run_graph_build, **kwargs)


async def report_generate_job(ctx, **kwargs) -> None:
    await asyncio.to_thread(jobs.run_report_generate, **kwargs)


async def simulation_run_job(ctx, **kwargs) -> None:
    # 拉起子进程 + 启动监控线程后即返回（监控线程为 worker 进程的 daemon，持续存活）
    await asyncio.to_thread(jobs.run_simulation_launch, **kwargs)


async def reconcile_job(ctx) -> None:
    # 周期对账：终结崩溃 worker 遗留的已死模拟、按需接管本机孤儿（存活性以 Redis 心跳为准）
    await asyncio.to_thread(jobs.run_reconcile)


async def startup(ctx) -> None:
    setup_logger("superfish")
    logger.info("worker 启动：初始化数据库与对象存储")
    from .core.db import init_db
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

    # 启动即对账一次：终结本 worker 上次崩溃/重启遗留的已死模拟，并接管本机仍在跑的孤儿
    try:
        await asyncio.to_thread(jobs.run_reconcile)
    except Exception as exc:
        logger.warning(f"worker 启动对账失败（忽略）: {exc}")


async def shutdown(ctx) -> None:
    logger.info("worker 关闭")


class WorkerSettings:
    """arq worker 配置。"""

    functions = [graph_build_job, report_generate_job, simulation_run_job]
    # 每 30s 周期对账：任一持有模拟的 worker 崩溃后，其在跑模拟由其他 worker 的对账及时
    # 终结（心跳过期）/接管。unique=True：每个 cron tick 仅一个 worker 执行，避免重复扫描。
    cron_jobs = [cron(reconcile_job, second={0, 30}, run_at_startup=False, unique=True)]
    redis_settings = _redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    # 单作业超时放宽以容纳长任务（报告/图谱/模拟拉起）
    job_timeout = 60 * 60 * 6
    keep_result = 60 * 30
