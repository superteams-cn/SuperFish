"""模拟监控循环：跟踪进程存活、续读动作日志、刷新所有权心跳、落终态、清理资源。

从 SimulationRunner 抽出为独立模块。监控循环需编排 runner 的多项行为（日志解析 /
状态持久化 / 所有权确认 / 产物上传 / 探活），故以 ``runner`` 作为协作者回调（而非把
十余个依赖逐一注入），SimulationRunner 以薄委托 ``_monitor_simulation`` 调用本函数。

终态决策为纯函数 ``process_control.decide_terminal_status``；进程内运行时状态统一在
``runner._store``（RunnerRuntimeStore）。集成测试 tests/test_simulation_runner.py 通过
塞「已退出的假进程」驱动循环体直达终态，守护此处的终态落地与资源清理。
"""

import os
import time
from datetime import datetime
from typing import Any

from ...core.logger import get_logger
from ...domain.run_state import RunnerStatus
from ...utils.locale import set_locale
from ..graph_memory_updater import GraphMemoryManager
from . import process_control as pc

logger = get_logger("superfish.simulation.monitor")


def run_monitor_loop(runner: Any, simulation_id: str, locale: str = "zh") -> None:
    """监控一个模拟运行直至其进程结束，并落终态、清理资源。

    可监控两类进程：
    - 本进程亲自 Popen 的（``runner._store.processes`` 有句柄）：用 process.poll() 判存活，退出码判终态。
    - 接管的孤儿（无句柄）：用 PID 探活，据 actions.jsonl 有无 simulation_end 判 completed/interrupted。

    关键：日志读取偏移从持久化的 ``*_log_offset`` 续读、每 tick 落库，接管时不重读 →
    不重复推图谱记忆。若本进程被「松手」（``runner._detaching``）或所有权被他人接管，
    则直接退出而不改终态。
    """
    set_locale(locale)
    sim_dir = os.path.join(runner.RUN_STATE_DIR, simulation_id)

    # 新的日志结构：分平台的动作日志
    twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
    reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")

    process = runner._store.processes.get(simulation_id)  # 孤儿接管时为 None
    state = runner._store.run_states.get(simulation_id) or runner._load_run_state(simulation_id)

    if not state:
        return

    # 从持久化偏移续读（接管场景从断点继续；新启动时为 0）
    twitter_position = state.twitter_log_offset or 0
    reddit_position = state.reddit_log_offset or 0
    pid = state.process_pid
    start_time = state.process_start_time

    def _alive() -> bool:
        if process is not None:
            return process.poll() is None
        return runner._pid_alive(pid, start_time)

    try:
        tick = 0
        while _alive():
            if runner._detaching:
                # 进程退出/热重载：松手退出，不改终态，交给下次 reconcile 接管
                logger.info(f"监控松手退出（进程将退出）: {simulation_id}")
                return

            if os.path.exists(twitter_actions_log):
                twitter_position = runner._read_action_log(
                    twitter_actions_log, twitter_position, state, "twitter"
                )
                state.twitter_log_offset = twitter_position
            if os.path.exists(reddit_actions_log):
                reddit_position = runner._read_action_log(
                    reddit_actions_log, reddit_position, state, "reddit"
                )
                state.reddit_log_offset = reddit_position

            # 刷新所有权心跳后落库
            state.owner_id = runner._inst_id()
            state.owner_heartbeat = time.time()
            runner._save_run_state(state)

            tick += 1
            # 周期性确认仍是 owner，否则让位退出（避免多进程重复监控/重复推图谱记忆）
            if tick % 5 == 0 and not runner._still_owner(simulation_id):
                logger.info(f"监控所有权已被接管，让位退出: {simulation_id}")
                return

            time.sleep(2)

        # 进程已结束：最后读取一次日志（续偏移）
        if os.path.exists(twitter_actions_log):
            twitter_position = runner._read_action_log(
                twitter_actions_log, twitter_position, state, "twitter"
            )
            state.twitter_log_offset = twitter_position
        if os.path.exists(reddit_actions_log):
            reddit_position = runner._read_action_log(
                reddit_actions_log, reddit_position, state, "reddit"
            )
            state.reddit_log_offset = reddit_position

        # 终态判定（纯决策见 pc.decide_terminal_status；此处仅落副作用）
        exit_code = process.returncode if process is not None else None
        new_status = pc.decide_terminal_status(
            already_completed=state.runner_status == RunnerStatus.COMPLETED,
            is_own_process=process is not None,
            exit_code=exit_code,
            has_sim_end=runner._has_simulation_end(sim_dir),
        )
        state.runner_status = new_status
        if new_status == RunnerStatus.COMPLETED:
            if not state.completed_at:
                state.completed_at = datetime.now().isoformat()
            logger.info(f"模拟完成: {simulation_id}")
        elif new_status == RunnerStatus.FAILED:
            main_log_path = os.path.join(sim_dir, "simulation.log")
            error_info = ""
            try:
                if os.path.exists(main_log_path):
                    with open(main_log_path, encoding="utf-8") as f:
                        error_info = f.read()[-2000:]
            except Exception:
                pass
            state.error = f"进程退出码: {exit_code}, 错误: {error_info}"
            logger.error(f"模拟失败: {simulation_id}, error={state.error}")
        else:  # INTERRUPTED
            logger.warning(f"接管的模拟进程已消失且未跑完，标记中断: {simulation_id}")

        # 任意终态都上传 agent 记忆快照到 S3：强停/中断的模拟同样已周期性落盘，
        # 用户多半正是对"提前结束"的推演发起采访（无 agent_memory 时该调用是空操作）。
        runner._upload_run_artifacts(simulation_id, sim_dir)

        state.twitter_running = False
        state.reddit_running = False
        state.owner_id = None
        state.owner_heartbeat = None
        runner._save_run_state(state)

    except Exception as e:
        logger.error(f"监控线程异常: {simulation_id}, error={str(e)}")
        state.runner_status = RunnerStatus.FAILED
        state.error = str(e)
        runner._save_run_state(state)

    finally:
        # 停止图谱记忆更新器
        if runner._store.graph_memory_enabled.get(simulation_id, False):
            try:
                GraphMemoryManager.stop_updater(simulation_id)
                logger.info(f"已停止图谱记忆更新: simulation_id={simulation_id}")
            except Exception as e:
                logger.error(f"停止图谱记忆更新器失败: {e}")
            runner._store.graph_memory_enabled.pop(simulation_id, None)

        # 清理进程资源（本进程不再监控此模拟）
        runner._store.processes.pop(simulation_id, None)
        runner._store.action_queues.pop(simulation_id, None)
        runner._store.monitor_threads.pop(simulation_id, None)

        # 关闭日志文件句柄
        if simulation_id in runner._store.stdout_files:
            try:
                runner._store.stdout_files[simulation_id].close()
            except Exception:
                pass
            runner._store.stdout_files.pop(simulation_id, None)
        if (
            simulation_id in runner._store.stderr_files
            and runner._store.stderr_files[simulation_id]
        ):
            try:
                runner._store.stderr_files[simulation_id].close()
            except Exception:
                pass
            runner._store.stderr_files.pop(simulation_id, None)
