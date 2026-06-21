"""模拟路由子包的共享件：统一导入面 + 路由级归属守卫 + 跨处理器复用的小工具。

拆分自原 routers/simulation.py（2104 行）。各子路由模块统一 ``from ._shared import ...``，
以此作为本子包的单一导入来源；业务处理器按概念分布在
entities/lifecycle/run/interview/env/results 等模块。

``__all__`` 显式声明再导出面，避免 lint 误删「本文件未直接使用、但供子模块导入」的符号。
"""

import csv
import json
import os
import threading
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from ...core.deps import get_current_admin, get_current_user, require_verified_user, use_locale
from ...core.errors import error_response as _error  # 统一错误信封
from ...core.logger import get_logger
from ...core.settings import settings
from ...models.project import ProjectManager
from ...schemas.simulation import (
    CloseEnvRequest,
    CreateSimulationRequest,
    EnvStatusRequest,
    GenerateProfilesRequest,
    InterviewAgentRequest,
    InterviewAllRequest,
    InterviewBatchRequest,
    InterviewHistoryRequest,
    PrepareSimulationRequest,
    PrepareStatusRequest,
    StartSimulationRequest,
    StopSimulationRequest,
)
from ...services.neo4j_entity_reader import Neo4jEntityReader
from ...services.oasis_profile_generator import OasisProfileGenerator
from ...services.simulation_manager import SimulationManager, SimulationStatus
from ...services.simulation_runner import SimulationRunner
from ...utils.locale import get_locale, set_locale, t

__all__ = [
    # stdlib / fastapi
    "csv",
    "json",
    "os",
    "threading",
    "traceback",
    "datetime",
    "APIRouter",
    "Depends",
    "HTTPException",
    "Request",
    "FileResponse",
    "StreamingResponse",
    # deps / infra
    "get_current_admin",
    "get_current_user",
    "require_verified_user",
    "use_locale",
    "_error",
    "settings",
    "ProjectManager",
    # schemas
    "CloseEnvRequest",
    "CreateSimulationRequest",
    "EnvStatusRequest",
    "GenerateProfilesRequest",
    "InterviewAgentRequest",
    "InterviewAllRequest",
    "InterviewBatchRequest",
    "InterviewHistoryRequest",
    "PrepareSimulationRequest",
    "PrepareStatusRequest",
    "StartSimulationRequest",
    "StopSimulationRequest",
    # services
    "Neo4jEntityReader",
    "OasisProfileGenerator",
    "SimulationManager",
    "SimulationStatus",
    "SimulationRunner",
    # locale
    "get_locale",
    "set_locale",
    "t",
    # 本子包共享 helper
    "logger",
    "_enforce_sim_ownership",
    "_owned_simulation",
    "INTERVIEW_PROMPT_PREFIX",
    "optimize_interview_prompt",
    "_check_simulation_prepared",
]

logger = get_logger("superfish.api.simulation")


def _enforce_sim_ownership(request: Request, current=Depends(get_current_user)):
    """路由级守卫：整个模拟路由需登录；凡 path 含 simulation_id 的，校验归属。

    覆盖所有 GET /{simulation_id}/* 详情接口；以 body 传 simulation_id 的
    变更类接口（prepare/start/stop/interview/*-env 等）在各自处理器内单独校验。
    """
    sid = request.path_params.get("simulation_id")
    if sid:
        state = SimulationManager().get_simulation(sid)
        if not state or state.user_id != current["user_id"]:
            raise HTTPException(status_code=404, detail=t("api.simulationNotFound", id=sid))


def _owned_simulation(simulation_id: str, current: dict):
    """返回属于当前用户的模拟 state；不存在或非属主返回 None（调用方据此回 404）。"""
    state = SimulationManager().get_simulation(simulation_id)
    if not state or state.user_id != current["user_id"]:
        return None
    return state


# Interview prompt 优化前缀：添加后可避免 Agent 调用工具，直接用文本回复
INTERVIEW_PROMPT_PREFIX = "结合你的人设、所有的过往记忆与行动，不调用任何工具直接用文本回复我："


def optimize_interview_prompt(prompt: str) -> str:
    """优化 Interview 提问，添加前缀避免 Agent 调用工具。"""
    if not prompt:
        return prompt
    # 避免重复添加前缀
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """检查模拟是否已准备完成（基于 Postgres 状态 + 对象存储中的配置）。

    判定：模拟存在、config_generated=True，且配置可获取（本地或对象存储）。
    返回 (is_prepared: bool, info: dict)。
    """
    simulation_manager = SimulationManager()

    state = simulation_manager.get_simulation(simulation_id)
    if state is None:
        return False, {"reason": "模拟不存在"}

    status = state.status.value
    config_generated = state.config_generated
    logger.debug(
        f"检测模拟准备状态: {simulation_id}, status={status}, config_generated={config_generated}"
    )

    prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
    if not (status in prepared_statuses and config_generated):
        logger.warning(
            f"模拟 {simulation_id} 检测结果: 未准备完成 "
            f"(status={status}, config_generated={config_generated})"
        )
        return False, {
            "reason": f"状态未就绪或配置未生成: status={status}, config_generated={config_generated}",
            "status": status,
            "config_generated": config_generated,
        }

    # 校验配置确实可获取（本地缺失时回退对象存储）
    if simulation_manager.get_simulation_config(simulation_id) is None:
        return False, {"reason": "缺少模拟配置 simulation_config.json", "status": status}

    # preparing 但配置已生成 → 自动置为 ready
    if status == "preparing":
        try:
            state.status = SimulationStatus.READY
            simulation_manager._save_simulation_state(state)
            status = "ready"
            logger.info(f"自动更新模拟状态: {simulation_id} preparing -> ready")
        except Exception as e:
            logger.warning(f"自动更新状态失败: {e}")

    logger.info(f"模拟 {simulation_id} 检测结果: 已准备完成 (status={status})")
    return True, {
        "status": status,
        "entities_count": state.entities_count,
        "profiles_count": state.profiles_count,
        "entity_types": state.entity_types,
        "config_generated": config_generated,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }
