"""
SuperFish Backend —— FastAPI 应用入口

graph / report / simulation 三大业务路由均为原生 FastAPI 实现。
"""

import os
import warnings

# 抑制 multiprocessing resource_tracker 的警告（来自第三方库如 transformers）
# 需要在所有其他导入之前设置
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Config
from .utils.logger import setup_logger, get_logger
from .routers import graph as graph_router
from .routers import report as report_router
from .routers import simulation as simulation_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理模拟进程。"""
    logger = setup_logger('superfish')
    logger.info("=" * 50)
    logger.info("SuperFish Backend 启动中...")
    logger.info("=" * 50)

    # 注册模拟进程清理函数（确保服务器关闭时终止所有模拟进程）
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    logger.info("已注册模拟进程清理函数")

    logger.info("SuperFish Backend 启动完成")
    yield
    # 关闭阶段：SimulationRunner 通过 atexit 清理，无需额外操作


def create_app() -> FastAPI:
    """构建 FastAPI 应用。"""
    app = FastAPI(title="SuperFish Backend", lifespan=lifespan)

    # 启用 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 健康检查
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "SuperFish Backend"}

    # 业务路由（全部已迁移为原生 FastAPI）
    app.include_router(graph_router.router, prefix="/api/graph", tags=["graph"])
    app.include_router(report_router.router, prefix="/api/report", tags=["report"])
    app.include_router(simulation_router.router, prefix="/api/simulation", tags=["simulation"])

    return app


app = create_app()
