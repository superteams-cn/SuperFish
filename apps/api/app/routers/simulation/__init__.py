"""模拟路由聚合（拆分自 2104 行 God 路由 simulation.py）。

按声明顺序聚合子路由：所有字面量路径（/create、/list、/start…）与多段动态路径
均在前面的模块中，单段 catch-all ``GET /{simulation_id}``（位于 results 模块末尾）
随 results 最后纳入，确保不会吞掉前面的字面量路由。

对外仍暴露模块级 ``router``，main.py 的 include 方式无需改动。
"""

from fastapi import APIRouter, Depends

from ...core.deps import use_locale
from ._shared import _enforce_sim_ownership
from .entities import router as entities_router
from .env import router as env_router
from .interview import router as interview_router
from .lifecycle import router as lifecycle_router
from .results import router as results_router
from .run import router as run_router

# 整个模拟路由：解析语言 + 强制登录与 simulation_id 归属校验
router = APIRouter(dependencies=[Depends(use_locale), Depends(_enforce_sim_ownership)])

# 顺序关键：results 最后纳入（其末尾的 /{simulation_id} 是单段 catch-all）
for _sub in (
    entities_router,
    lifecycle_router,
    run_router,
    interview_router,
    env_router,
    results_router,
):
    router.include_router(_sub)
