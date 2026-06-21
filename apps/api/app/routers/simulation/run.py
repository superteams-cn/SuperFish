"""模拟子路由：启动/停止/批量停止等运行控制接口。

拆分自 routers/simulation.py。共享件见 _shared.py。
"""

import traceback

from fastapi import APIRouter, Depends

from ...core.deps import get_current_admin, get_current_user, require_verified_user
from ...core.errors import error_response as _error
from ...core.redis_lock import LockBusy, redis_lock
from ...core.settings import settings
from ...jobqueue import enqueue
from ...models.project import ProjectManager
from ...schemas.simulation import StartSimulationRequest, StopSimulationRequest
from ...services.simulation_manager import SimulationManager, SimulationStatus
from ...services.simulation_runner import SimulationRunner
from ...utils.locale import get_locale, t
from ._shared import _check_simulation_prepared, _owned_simulation, logger

router = APIRouter()


@router.post("/start")
def start_simulation(req: StartSimulationRequest, current=Depends(require_verified_user)):
    """
    开始运行模拟

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",          // 必填，模拟ID
            "platform": "parallel",                // 可选: twitter / reddit / parallel (默认)
            "max_rounds": 100,                     // 可选: 最大模拟轮数，用于截断过长的模拟
            "enable_graph_memory_update": false,   // 可选: 是否将 Agent 活动动态更新到 图谱记忆
            "force": false                         // 可选: 强制重新开始（会停止运行中的模拟并清理日志）
        }
    """
    _start_lock = None
    try:
        simulation_id = req.simulation_id
        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if _owned_simulation(simulation_id, current) is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        # per-sim 互斥锁：把「查是否在跑 → 写 STARTING → 入队」临界区在多 API 副本间串行化，
        # 避免两个副本并发 /start 同一模拟各自入队、两个 worker 各拉起一个子进程。
        try:
            _start_lock = redis_lock(f"sim:start:{simulation_id}", ttl=60)
            _start_lock.__enter__()
        except LockBusy:
            _start_lock = None
            return _error("模拟正在启动中，请稍候重试", 409)

        # 配额：同时运行中的模拟数上限（重启自身不计入）
        running = [
            s
            for s in SimulationManager().list_simulations(user_id=current["user_id"])
            if s.status == SimulationStatus.RUNNING and s.simulation_id != simulation_id
        ]
        if len(running) >= settings.max_concurrent_simulations:
            return _error(
                t("api.concurrentSimQuota", limit=settings.max_concurrent_simulations), 403
            )

        platform = req.platform
        max_rounds = req.max_rounds  # 可选：最大模拟轮数
        enable_graph_memory_update = req.enable_graph_memory_update  # 可选：是否启用图谱记忆更新
        force = req.force  # 可选：强制重新开始

        # 验证 max_rounds 参数
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return _error(t("api.maxRoundsPositive"), 400)
            except (ValueError, TypeError):
                return _error(t("api.maxRoundsInvalid"), 400)

        if platform not in ["twitter", "reddit", "parallel"]:
            return _error(t("api.invalidPlatform", platform=platform), 400)

        # 检查模拟是否已准备好
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        force_restarted = False

        # 智能处理状态：如果准备工作已完成，允许重新启动
        if state.status != SimulationStatus.READY:
            # 检查准备工作是否已完成
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # 准备工作已完成，检查是否有正在运行的进程
                if state.status == SimulationStatus.RUNNING:
                    # 检查模拟进程是否真的在运行
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # 进程确实在运行
                        if force:
                            # 强制模式：停止运行中的模拟
                            logger.info(f"强制模式：停止运行中的模拟 {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"停止模拟时出现警告: {str(e)}")
                        else:
                            return _error(t("api.simRunningForceHint"), 400)

                # 如果是强制模式，清理运行日志
                if force:
                    logger.info(f"强制模式：清理模拟日志 {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"清理日志时出现警告: {cleanup_result.get('errors')}")
                    force_restarted = True

                # 进程不存在或已结束，重置状态为 ready
                logger.info(
                    f"模拟 {simulation_id} 准备工作已完成，重置状态为 ready（原状态: {state.status.value}）"
                )
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # 准备工作未完成
                return _error(t("api.simNotReady", status=state.status.value), 400)

        # 获取图谱ID（用于图谱记忆更新）
        graph_id = None
        if enable_graph_memory_update:
            # 从模拟状态或项目中获取 graph_id
            graph_id = state.graph_id
            if not graph_id:
                # 尝试从项目中获取
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id

            if not graph_id:
                return _error(t("api.graphIdRequiredForMemory"), 400)

            logger.info(f"启用图谱记忆更新: simulation_id={simulation_id}, graph_id={graph_id}")

        # 初始化 STARTING 运行态（快速、可立即返回前端），实际拉起子进程入队给 worker。
        # 控制面（stop/interview/IPC）走 Redis 总线，故子进程可由独立 worker 持有、横向扩展。
        # 队列不可用时回退本地线程执行（等价早期 API 进程内 Popen 的单机行为）。
        run_state = SimulationRunner._init_run_state(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id,
        )
        job_id = enqueue(
            "simulation_run",
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id,
            locale=get_locale(),
        )
        logger.info(f"模拟拉起已入队: simulation_id={simulation_id}, job_id={job_id}")

        # 更新模拟状态（乐观置 RUNNING，供配额/列表语义；worker 失败时回写 FAILED）
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)

        response_data = run_state.to_dict()
        if max_rounds:
            response_data["max_rounds_applied"] = max_rounds
        response_data["graph_memory_update_enabled"] = enable_graph_memory_update
        response_data["force_restarted"] = force_restarted
        if enable_graph_memory_update:
            response_data["graph_id"] = graph_id

        return {"success": True, "data": response_data}

    except Exception as e:
        logger.error(f"启动模拟失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())

    finally:
        if _start_lock is not None:
            _start_lock.__exit__(None, None, None)


@router.post("/stop")
def stop_simulation(req: StopSimulationRequest, current=Depends(get_current_user)):
    """
    停止模拟

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx"  // 必填，模拟ID
        }
    """
    try:
        simulation_id = req.simulation_id
        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if _owned_simulation(simulation_id, current) is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        run_state = SimulationRunner.stop_simulation(simulation_id)

        # 更新模拟状态
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)

        return {"success": True, "data": run_state.to_dict()}

    except Exception as e:
        logger.error(f"停止模拟失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/admin/stop-all")
def stop_all_simulations(current=Depends(get_current_admin)):
    """运维入口：终止所有正在运行的模拟（含服务重启后接管的孤儿）。

    配合「进程退出时松手不杀子进程」的策略——真正想全停时调用此接口。
    仅 admin 白名单邮箱可调用（settings.admin_emails）。
    """
    try:
        result = SimulationRunner.cleanup_all_simulations()
        # 同步把这些模拟的元数据状态置为 paused
        manager = SimulationManager()
        for sid in result.get("stopped", []):
            try:
                state = manager.get_simulation(sid)
                if state:
                    state.status = SimulationStatus.PAUSED
                    manager._save_simulation_state(state)
            except Exception as e:
                logger.warning(f"更新模拟元数据状态失败: {sid}, error={e}")
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"全部停止失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== Interview 采访接口 ==============
