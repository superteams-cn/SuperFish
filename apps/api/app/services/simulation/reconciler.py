"""模拟对账：把 PG 快照校正为实时终态，并接管/终结进程已死的运行。

从 SimulationRunner 抽出为独立模块。对账需编排 runner 的多项行为（探活 / 所有权 CAS /
图谱 updater 重建 / 监控线程重起 / 状态持久化），故以 ``runner`` 作为协作者回调，
SimulationRunner 以薄委托调用本模块。存活性一律以 host-independent 信号（owner 心跳 /
Redis IPC 心跳）优先，避免把存活的异机模拟按本机 PID 误判为已死。

集成测试 tests/test_simulation_runner.py 覆盖：死进程→INTERRUPTED/COMPLETED、STARTING 无
PID 超宽限期判失败、不抢异机存活模拟、新鲜 owner 不被打断等分支。
"""

import os
import threading
from datetime import datetime
from typing import Any

from ...core.logger import get_logger
from ...domain.run_state import RunnerStatus, SimulationRunState
from ...repositories.run_state_repo import RunStateRepository
from ..graph_memory_updater import GraphMemoryManager

logger = get_logger("superfish.simulation.reconciler")


def _sync_sim_terminal(simulation_id: str, runner_status: Any) -> None:
    """对账落 runner 终态后，把 sim 级 SimulationStatus 同步到一致，避免僵尸泄漏配额。"""
    from ..simulation_manager import SimulationManager

    SimulationManager().sync_terminal_status(simulation_id, runner_status)


def reconcile_state(runner: Any, state: SimulationRunState) -> SimulationRunState:
    """对从 PG 读出的快照做实时校正：running/starting 但进程已死 → 据日志判终态回写。

    仅校正非本进程拥有的快照（本进程拥有的对象由其监控线程实时维护）。
    """
    if state.runner_status not in (RunnerStatus.RUNNING, RunnerStatus.STARTING):
        return state
    # 存活性优先以 host-independent 信号为准（模拟可能跑在另一台 worker，本机 PID 探活
    # 对异机进程无意义，会把存活的远端模拟误判为已死）：
    #  1) owner 心跳新鲜 → 其监控线程在整个运行期（含活跃轮次）每 2s 刷新，最可靠；
    #  2) Redis IPC 心跳在 → 子进程存活（活跃轮次中可能因 TTL 短暂缺失，故配合 owner 心跳）。
    if runner._owner_fresh(state):
        return state
    if runner._env_alive(state.simulation_id):
        return state
    if runner._pid_alive(state.process_pid, state.process_start_time):
        return state  # 进程在本机仍活（owner 视角；心跳偶发缺失时的兜底）

    # 尚未拿到 PID 的 STARTING：已入队但 worker 还没真正 Popen（跨进程/副本的排队窗口）。
    # 在宽限期内视为「启动中」保持原样，避免被误判为 INTERRUPTED；超期才判失败。
    if state.process_pid is None and state.runner_status == RunnerStatus.STARTING:
        if runner._within_launch_grace(state):
            return state
        state.runner_status = RunnerStatus.FAILED
        state.error = state.error or "启动超时：worker 未在宽限期内拉起模拟进程"
        state.twitter_running = False
        state.reddit_running = False
        try:
            runner._save_run_state(state)
        except Exception as e:
            logger.warning(f"回写启动超时状态失败: {state.simulation_id}, error={e}")
        _sync_sim_terminal(state.simulation_id, state.runner_status)
        return state

    # 进程已死但快照仍 running → 据 actions.jsonl 判终态
    sim_dir = os.path.join(runner.RUN_STATE_DIR, state.simulation_id)
    if runner._has_simulation_end(sim_dir):
        state.runner_status = RunnerStatus.COMPLETED
        if not state.completed_at:
            state.completed_at = datetime.now().isoformat()
    else:
        state.runner_status = RunnerStatus.INTERRUPTED
    state.twitter_running = False
    state.reddit_running = False
    state.owner_id = None
    state.owner_heartbeat = None
    try:
        runner._save_run_state(state)
    except Exception as e:
        logger.warning(f"回写校正后的运行状态失败: {state.simulation_id}, error={e}")
    _sync_sim_terminal(state.simulation_id, state.runner_status)
    return state


def reconcile_running_simulations(
    runner: Any, locale: str = "zh", reset_detach: bool = True
) -> dict[str, Any]:
    """对账：接管本机仍在跑的孤儿、终结真正已死的运行（存活性以 Redis 心跳为准）。

    扫描 PG 中标记 running/starting 的模拟：
    - Redis 心跳在或本机 PID 存活 → 仍在运行；本机存活且无人监控时抢占所有权 + 重建
      图谱 updater + 重起监控线程续读（异机运行则交给其 worker，不跨机抢监控、不误判）。
    - 心跳与本机 PID 皆无、且无新鲜 owner → 据 actions.jsonl 判 completed/interrupted 回写。

    两处调用：FastAPI/worker 启动时（reset_detach=True，复位松手标志使重启后自动恢复），
    以及 worker 周期 cron（reset_detach=False，使任一 worker 死亡后其在跑模拟被及时终结/接管）。
    """
    # 新进程生命周期开始：复位松手标志（周期对账不复位，避免打断正在进行的优雅退出）
    if reset_detach:
        runner._detaching = False
        runner._detached = False

    adopted, finalized = [], []
    try:
        ids = [
            sid
            for sid, data in RunStateRepository.load_all_raw().items()
            if (data or {}).get("runner_status") in ("running", "starting")
        ]
    except Exception as e:
        logger.error(f"对账运行中模拟失败（读取列表）: {e}")
        return {"adopted": [], "finalized": []}

    for sid in ids:
        state = runner._load_run_state(sid)
        if not state:
            continue

        local_alive = runner._pid_alive(state.process_pid, state.process_start_time)
        env_alive = runner._env_alive(sid)

        if env_alive or local_alive:
            # 仍在运行（本机或他机）。仅当进程在【本机】存活且无人监控时由本进程接管监控；
            # 进程在异机时不跨机抢监控（无法 poll 异机 PID / tail 其本地日志），交给运行它的
            # worker 自行监控 —— 但绝不在此把存活的远端模拟误判为已死。
            if (
                local_alive
                and sid not in runner._store.monitor_threads
                and runner._try_claim_ownership(sid)
            ):
                runner._store.run_states[sid] = state
                runner._store.graph_memory_enabled[sid] = bool(state.graph_memory_enabled)
                if state.graph_memory_enabled and state.graph_id:
                    try:
                        GraphMemoryManager.create_updater(sid, state.graph_id)
                    except Exception as e:
                        logger.error(f"接管时重建图谱记忆更新器失败: {sid}, error={e}")
                th = threading.Thread(
                    target=runner._monitor_simulation, args=(sid, locale), daemon=True
                )
                th.start()
                runner._store.monitor_threads[sid] = th
                adopted.append(sid)
                logger.info(f"已接管运行中的模拟: {sid}, pid={state.process_pid}")
            continue

        # 既无 Redis 心跳、本机也无存活 PID。若仍有新鲜 owner（其 worker 暂时探测不到但
        # 心跳未过期），让它自己终结，避免争用；否则视为真正已死，据 actions.jsonl 终结。
        if runner._owner_fresh(state):
            continue

        sim_dir = os.path.join(runner.RUN_STATE_DIR, sid)
        if runner._has_simulation_end(sim_dir):
            state.runner_status = RunnerStatus.COMPLETED
            if not state.completed_at:
                state.completed_at = datetime.now().isoformat()
        else:
            state.runner_status = RunnerStatus.INTERRUPTED
        state.twitter_running = False
        state.reddit_running = False
        state.owner_id = None
        state.owner_heartbeat = None
        runner._save_run_state(state)
        _sync_sim_terminal(sid, state.runner_status)
        finalized.append(sid)
        logger.info(f"终结已死的模拟: {sid} -> {state.runner_status.value}")

    if adopted or finalized:
        logger.info(f"模拟对账完成: 接管={adopted}, 终结={finalized}")
    return {"adopted": adopted, "finalized": finalized}
