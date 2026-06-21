"""模拟子路由：模拟环境状态/唤醒/关闭接口。

拆分自 routers/simulation.py。共享件见 _shared.py。
"""

from ._shared import (  # noqa: F401  (统一从共享件导入，未用项由 ruff 裁剪)
    INTERVIEW_PROMPT_PREFIX,
    APIRouter,
    CloseEnvRequest,
    CreateSimulationRequest,
    Depends,
    EnvStatusRequest,
    FileResponse,
    GenerateProfilesRequest,
    HTTPException,
    InterviewAgentRequest,
    InterviewAllRequest,
    InterviewBatchRequest,
    InterviewHistoryRequest,
    GraphEntityReader,
    OasisProfileGenerator,
    PrepareSimulationRequest,
    PrepareStatusRequest,
    ProjectManager,
    Request,
    SimulationManager,
    SimulationRunner,
    SimulationStatus,
    StartSimulationRequest,
    StopSimulationRequest,
    StreamingResponse,
    _check_simulation_prepared,
    _error,
    _owned_simulation,
    csv,
    datetime,
    get_current_admin,
    get_current_user,
    get_locale,
    json,
    logger,
    optimize_interview_prompt,
    os,
    require_verified_user,
    set_locale,
    settings,
    t,
    threading,
    traceback,
)

router = APIRouter()


@router.post("/env-status")
def get_env_status(req: EnvStatusRequest, current=Depends(get_current_user)):
    """
    获取模拟环境状态

    检查模拟环境是否存活（可以接收 Interview 命令）
    """
    try:
        simulation_id = req.simulation_id

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if _owned_simulation(simulation_id, current) is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        env_alive = SimulationRunner.check_env_alive(simulation_id)

        # 获取更详细的状态信息
        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = t("api.envRunning")
        else:
            message = t("api.envNotRunningShort")

        return {
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "env_alive": env_alive,
                "twitter_available": env_status.get("twitter_available", False),
                "reddit_available": env_status.get("reddit_available", False),
                "message": message,
            },
        }

    except Exception as e:
        logger.error(f"获取环境状态失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/ensure-env")
def ensure_env(req: EnvStatusRequest, current=Depends(get_current_user)):
    """
    确保模拟环境存活（采访前唤醒）。

    环境已活则返回 status=alive；否则按需唤醒（恢复模式重建环境 + 灌回 agent 记忆，
    不重跑模拟），返回 status=waking，由前端轮询 /env-status 至 env_alive 后再发起采访。
    """
    try:
        simulation_id = req.simulation_id
        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if _owned_simulation(simulation_id, current) is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        result = SimulationRunner.wake_env(simulation_id)
        if result.get("success"):
            return {"success": True, "data": {"status": result.get("status", "waking")}}
        return _error(result.get("error") or t("api.envNotRunningShort"), 400)

    except Exception as e:
        logger.error(f"唤醒环境失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/close-env")
def close_simulation_env(req: CloseEnvRequest, current=Depends(get_current_user)):
    """
    关闭模拟环境

    向模拟发送关闭环境命令，使其优雅退出等待命令模式。

    注意：这不同于 /stop 接口，/stop 会强制终止进程，
    而此接口会让模拟优雅地关闭环境并退出。
    """
    try:
        simulation_id = req.simulation_id
        timeout = req.timeout

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if _owned_simulation(simulation_id, current) is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        result = SimulationRunner.close_simulation_env(simulation_id=simulation_id, timeout=timeout)

        # 更新模拟状态
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)

        return {"success": result.get("success", False), "data": result}

    except ValueError as e:
        return _error(str(e), 400)

    except Exception as e:
        logger.error(f"关闭环境失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 配置 / 脚本下载接口（带 send_file → FileResponse） ==============
