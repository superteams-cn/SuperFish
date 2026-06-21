"""
OASIS模拟运行器
在后台运行模拟并记录每个Agent的动作，支持实时状态监控
"""

import atexit
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from queue import Queue
from typing import Any

from ..core.errors import AppError
from ..core.logger import get_logger
from ..domain.run_state import AgentAction, RoundSummary, RunnerStatus, SimulationRunState
from ..repositories.interview_trace_repo import InterviewTraceRepository
from ..repositories.run_state_repo import RunStateRepository
from ..utils.locale import get_locale, set_locale
from .graph_memory_updater import GraphMemoryManager
from .simulation import log_reader
from .simulation import process_control as pc
from .simulation_ipc import CommandType, SimulationIPCClient

logger = get_logger("superfish.simulation_runner")

# re-export 运行态领域类型，保持 `from ..services.simulation_runner import ...` 导入面
__all__ = [
    "SimulationRunner",
    "SimulationRunState",
    "RunnerStatus",
    "AgentAction",
    "RoundSummary",
]

# 标记是否已注册清理函数
_cleanup_registered = False

# 平台检测
IS_WINDOWS = sys.platform == "win32"


class SimulationRunner:
    """
    模拟运行器

    负责：
    1. 在后台进程中运行OASIS模拟
    2. 解析运行日志，记录每个Agent的动作
    3. 提供实时状态查询接口
    4. 支持暂停/停止/恢复操作
    """

    # 运行状态存储目录
    RUN_STATE_DIR = os.path.join(os.path.dirname(__file__), "../../uploads/simulations")

    # 脚本目录
    SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "../../scripts")

    # 内存中的运行状态
    _run_states: dict[str, SimulationRunState] = {}
    _processes: dict[str, subprocess.Popen] = {}
    _action_queues: dict[str, Queue] = {}
    _monitor_threads: dict[str, threading.Thread] = {}
    _stdout_files: dict[str, Any] = {}  # 存储 stdout 文件句柄
    _stderr_files: dict[str, Any] = {}  # 存储 stderr 文件句柄

    # 图谱记忆更新配置
    _graph_memory_enabled: dict[str, bool] = {}  # simulation_id -> enabled

    # ===== 无状态可恢复（档位 A）相关 =====
    # 本进程实例唯一标识（hostname:pid），用于监控所有权归属
    _instance_id: str | None = None
    # owner 心跳超时（秒）：超过则视为旧 owner 已失联，可被接管
    OWNER_TTL = 15.0
    # 启动宽限期（秒）：STARTING 但尚无 PID（已入队待 worker 拉起）的容忍窗口，超期判失败
    LAUNCH_GRACE = 120.0
    # 退出/热重载时「松手」标志，让监控线程尽快退出（不杀子进程）
    _detaching: bool = False
    _detached: bool = False

    @classmethod
    def _inst_id(cls) -> str:
        """本进程实例标识（懒初始化）。"""
        if cls._instance_id is None:
            try:
                host = socket.gethostname()
            except Exception:
                host = "host"
            cls._instance_id = f"{host}:{os.getpid()}"
        return cls._instance_id

    # 进程探活/终止等无状态工具委托 process_control（保留旧方法名，调用方与集成测试不变）
    @staticmethod
    def _parse_etime(s: str) -> int | None:
        return pc.parse_etime(s)

    @staticmethod
    def _read_process_start_time(pid: int) -> float | None:
        return pc.read_process_start_time(pid)

    @staticmethod
    def _pid_alive(pid: int | None, expected_start: float | None = None) -> bool:
        return pc.pid_alive(pid, expected_start)

    @staticmethod
    def _has_simulation_end(sim_dir: str) -> bool:
        return pc.has_simulation_end(sim_dir)

    # 监控所有权 CAS：DB 原子读改写下沉到 RunStateRepository；本层只提供实例 id/TTL 与降级语义
    @classmethod
    def _try_claim_ownership(cls, simulation_id: str) -> bool:
        """抢占监控所有权；DB 异常时降级为 False。"""
        try:
            return RunStateRepository.try_claim_owner(simulation_id, cls._inst_id(), cls.OWNER_TTL)
        except Exception as e:
            logger.warning(f"抢占监控所有权失败: {simulation_id}, error={e}")
            return False

    @classmethod
    def _still_owner(cls, simulation_id: str) -> bool:
        """确认本进程仍是 owner；读失败时保守返回 True，避免误退出监控。"""
        try:
            return RunStateRepository.is_owner(simulation_id, cls._inst_id())
        except Exception:
            return True

    @classmethod
    def _release_ownership(cls, simulation_id: str) -> None:
        """释放所有权（仅当 owner 是自己时清空）。"""
        try:
            RunStateRepository.release_owner(simulation_id, cls._inst_id())
        except Exception as e:
            logger.warning(f"释放监控所有权失败: {simulation_id}, error={e}")

    @classmethod
    def _owns_locally(cls, simulation_id: str) -> bool:
        """本进程是否确实在监控该模拟（持有监控线程或子进程句柄）。

        用于判定内存缓存 `_run_states` 是否可信：仅 owner（拉起或接管者）的缓存是实时的，
        非 owner（如 API 入队后）的缓存是过期快照，必须改读 DB。
        """
        return simulation_id in cls._monitor_threads or simulation_id in cls._processes

    @classmethod
    def get_run_state(cls, simulation_id: str) -> SimulationRunState | None:
        """获取运行状态。

        拥有子进程的进程（worker/本进程）持有 `_run_states` 里的实时对象；
        其他副本（如 API 入队后并不监控的进程）则从 Postgres 读取最新快照（保证新鲜）。

        关键：仅当本进程【确实在监控】该模拟（有监控线程或子进程句柄）时才信任内存缓存。
        否则（如 API 调 _init_run_state 入队后缓存了 STARTING 快照、但拉起在 worker）必须读
        DB —— 不然 API 会一直返回自己缓存的 STARTING，看不到 worker 写入的 running/completed。

        返回前做实时校正：若标记 running/starting 但进程已死，则据 actions.jsonl
        终态回写 completed/interrupted，消除「进程已退出但快照仍 running」的脏状态。
        """
        if cls._owns_locally(simulation_id):
            return cls._run_states[simulation_id]
        state = cls._load_run_state(simulation_id)
        if state is None:
            return None
        return cls._reconcile_state(state)

    @classmethod
    def _reconcile_state(cls, state: SimulationRunState) -> SimulationRunState:
        """对从 PG 读出的快照做实时校正：running/starting 但进程已死 → 据日志判终态回写。

        仅校正非本进程拥有的快照（本进程拥有的对象由其监控线程实时维护）。
        """
        if state.runner_status not in (RunnerStatus.RUNNING, RunnerStatus.STARTING):
            return state
        # 存活性优先以 host-independent 信号为准（模拟可能跑在另一台 worker，本机 PID 探活
        # 对异机进程无意义，会把存活的远端模拟误判为已死）：
        #  1) owner 心跳新鲜 → 其监控线程在整个运行期（含活跃轮次）每 2s 刷新，最可靠；
        #  2) Redis IPC 心跳在 → 子进程存活（活跃轮次中可能因 TTL 短暂缺失，故配合 owner 心跳）。
        if cls._owner_fresh(state):
            return state
        if cls._env_alive(state.simulation_id):
            return state
        if cls._pid_alive(state.process_pid, state.process_start_time):
            return state  # 进程在本机仍活（owner 视角；心跳偶发缺失时的兜底）

        # 尚未拿到 PID 的 STARTING：已入队但 worker 还没真正 Popen（跨进程/副本的排队窗口）。
        # 在宽限期内视为「启动中」保持原样，避免被误判为 INTERRUPTED；超期才判失败。
        if state.process_pid is None and state.runner_status == RunnerStatus.STARTING:
            if cls._within_launch_grace(state):
                return state
            state.runner_status = RunnerStatus.FAILED
            state.error = state.error or "启动超时：worker 未在宽限期内拉起模拟进程"
            state.twitter_running = False
            state.reddit_running = False
            try:
                cls._save_run_state(state)
            except Exception as e:
                logger.warning(f"回写启动超时状态失败: {state.simulation_id}, error={e}")
            return state

        # 进程已死但快照仍 running → 据 actions.jsonl 判终态
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        if cls._has_simulation_end(sim_dir):
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
            cls._save_run_state(state)
        except Exception as e:
            logger.warning(f"回写校正后的运行状态失败: {state.simulation_id}, error={e}")
        return state

    @classmethod
    def _env_alive(cls, simulation_id: str) -> bool:
        """模拟是否存活（以 Redis IPC 心跳为准，host-independent）。

        模拟子进程每轮循环刷新 sim:ipc:alive:{sid}（TTL 过期即失效），故无论模拟跑在
        哪台 worker，任意副本都能据此判活 —— 取代「本机 PID 探活」对异机进程的无效判断。
        """
        try:
            from .simulation_ipc import read_env_status

            return read_env_status(simulation_id).get("status") == "alive"
        except Exception:
            return False

    @classmethod
    def _owner_fresh(cls, state: SimulationRunState) -> bool:
        """是否有新鲜 owner 正在监控（owner 心跳在 OWNER_TTL 内）。"""
        if not state.owner_id or not state.owner_heartbeat:
            return False
        return (time.time() - state.owner_heartbeat) < cls.OWNER_TTL

    @classmethod
    def _within_launch_grace(cls, state: SimulationRunState) -> bool:
        """STARTING 但尚无 PID 的状态是否仍在启动宽限期内（据 started_at 判断）。

        解析失败时保守返回 True（视为刚入队），避免把正常排队的模拟误杀。
        """
        if not state.started_at:
            return True
        try:
            started = datetime.fromisoformat(state.started_at)
        except (ValueError, TypeError):
            return True
        return (datetime.now() - started).total_seconds() < cls.LAUNCH_GRACE

    @classmethod
    def _load_run_state(cls, simulation_id: str) -> SimulationRunState | None:
        """从 Postgres 加载运行状态快照（委托 RunStateRepository）。"""
        data = RunStateRepository.load_raw(simulation_id)
        if not data:
            return None
        return cls._state_from_data(simulation_id, data)

    @classmethod
    def get_run_states_bulk(cls, simulation_ids: list[str]) -> dict[str, SimulationRunState]:
        """批量获取运行状态（首页历史用）：单次查询加载全部快照，避免逐条 N+1。

        - 本进程拥有的活动对象优先用内存实时态；
        - 仅对标记 running/starting 的快照做存活校正（绝大多数历史项为终态，无需触碰文件系统）。
        返回 {simulation_id: SimulationRunState}；无快照的模拟不在结果中。
        """
        if not simulation_ids:
            return {}
        result: dict[str, SimulationRunState] = {}
        to_load: list[str] = []
        for sid in simulation_ids:
            # 仅信任本进程确实在监控的内存态；非 owner 缓存可能过期，改读 DB（见 get_run_state）
            if cls._owns_locally(sid):
                result[sid] = cls._run_states[sid]
            else:
                to_load.append(sid)

        if to_load:
            raw = RunStateRepository.load_raw_bulk(to_load)
            for sid, data in raw.items():
                state = cls._state_from_data(sid, data)
                if state is None:
                    continue
                # 仅对仍标记运行中的快照做存活校正（其余直接用快照，零文件系统访问）
                if state.runner_status in (RunnerStatus.RUNNING, RunnerStatus.STARTING):
                    state = cls._reconcile_state(state)
                result[sid] = state
        return result

    @classmethod
    def _state_from_data(cls, simulation_id: str, data: dict) -> SimulationRunState | None:
        """从持久化 data dict 重建 SimulationRunState（委托领域类 from_data）。"""
        try:
            return SimulationRunState.from_data(simulation_id, data)
        except Exception as e:
            logger.error(f"加载运行状态失败: {str(e)}")
            return None

    @classmethod
    def _save_run_state(cls, state: SimulationRunState):
        """保存运行状态到 Postgres（upsert，委托 RunStateRepository）并更新本进程实时缓存。"""
        RunStateRepository.save_raw(state.simulation_id, state.to_detail_dict())
        cls._run_states[state.simulation_id] = state

    @classmethod
    def _materialize_sim_dir(cls, simulation_id: str) -> str:
        """确保模拟目录与配置在本机存在：本地缺失时从对象存储物化准备阶段产物。

        支持 prepare / start / 运行进程分处不同节点（API 副本入队、worker 拉起）。
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            try:
                from ..utils import object_store

                os.makedirs(sim_dir, exist_ok=True)
                n = object_store.download_prefix_to_dir(f"simulations/{simulation_id}/", sim_dir)
                if n:
                    logger.info(f"已从对象存储物化模拟文件: {simulation_id}（{n} 个）")
            except Exception as exc:
                logger.warning(f"从对象存储物化模拟文件失败: {exc}")
        return sim_dir

    @classmethod
    def _init_run_state(
        cls,
        simulation_id: str,
        platform: str = "parallel",
        max_rounds: int | None = None,
        enable_graph_memory_update: bool = False,
        graph_id: str | None = None,
    ) -> SimulationRunState:
        """初始化并持久化 STARTING 运行态（不拉起进程）。

        API 路由调用本方法拿到可立即返回前端的 STARTING 快照，再把实际拉起入队给
        worker（由 _spawn_process 续接）—— 从而把计算（OASIS 子进程）从 API 进程
        移到可横向扩展的 worker 进程。
        """
        # 检查是否已在运行
        existing = cls.get_run_state(simulation_id)
        if existing and existing.runner_status in [RunnerStatus.RUNNING, RunnerStatus.STARTING]:
            raise AppError(f"模拟已在运行中: {simulation_id}", status=409)

        sim_dir = cls._materialize_sim_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            raise AppError("模拟配置不存在，请先调用 /prepare 接口", status=404)

        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        # 初始化运行状态
        time_config = config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = int(total_hours * 60 / minutes_per_round)

        # 如果指定了最大轮数，则截断
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                logger.info(
                    f"轮数已截断: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})"
                )

        state = SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.STARTING,
            total_rounds=total_rounds,
            total_simulation_hours=total_hours,
            started_at=datetime.now().isoformat(),
        )
        # 平台运行标记（让 STARTING 快照即带正确平台，前端立即正确显示）
        if platform == "twitter":
            state.twitter_running = True
        elif platform == "reddit":
            state.reddit_running = True
        else:
            state.twitter_running = True
            state.reddit_running = True

        cls._save_run_state(state)
        return state

    @classmethod
    def start_simulation(
        cls,
        simulation_id: str,
        platform: str = "parallel",  # twitter / reddit / parallel
        max_rounds: int | None = None,  # 最大模拟轮数（可选，用于截断过长的模拟）
        enable_graph_memory_update: bool = False,  # 是否将活动更新到图谱
        graph_id: str | None = None,  # 图谱ID（启用图谱更新时必需）
    ) -> SimulationRunState:
        """启动模拟（同步整链路：初始化 STARTING + 本进程拉起子进程）。

        保留给内联兜底（队列不可用时）与集成测试；常规路径由 API 调 _init_run_state
        入队、worker 调 _spawn_process。Returns: SimulationRunState。
        """
        cls._init_run_state(
            simulation_id, platform, max_rounds, enable_graph_memory_update, graph_id
        )
        return cls._spawn_process(
            simulation_id, platform, max_rounds, enable_graph_memory_update, graph_id
        )

    @classmethod
    def _spawn_process(
        cls,
        simulation_id: str,
        platform: str = "parallel",
        max_rounds: int | None = None,
        enable_graph_memory_update: bool = False,
        graph_id: str | None = None,
    ) -> SimulationRunState:
        """在本进程拉起 OASIS 子进程并启动监控线程（假设 STARTING 运行态已存在）。

        由 worker 作业（jobs.run_simulation_launch）或 start_simulation 调用；本进程
        据此成为该模拟的监控 owner。
        """
        state = cls.get_run_state(simulation_id)
        if state is None:
            raise AppError(f"运行态不存在，无法拉起进程: {simulation_id}", status=404)

        sim_dir = cls._materialize_sim_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            raise AppError("模拟配置不存在，请先调用 /prepare 接口", status=404)

        # 如果启用图谱记忆更新，创建更新器
        if enable_graph_memory_update:
            if not graph_id:
                raise AppError("启用图谱记忆更新时必须提供 graph_id", status=400)

            try:
                GraphMemoryManager.create_updater(simulation_id, graph_id)
                cls._graph_memory_enabled[simulation_id] = True
                logger.info(
                    f"已启用图谱记忆更新: simulation_id={simulation_id}, graph_id={graph_id}"
                )
            except Exception as e:
                logger.error(f"创建图谱记忆更新器失败: {e}")
                cls._graph_memory_enabled[simulation_id] = False
        else:
            cls._graph_memory_enabled[simulation_id] = False

        # 确定运行哪个脚本（脚本位于 backend/scripts/ 目录）
        if platform == "twitter":
            script_name = "run_twitter_simulation.py"
            state.twitter_running = True
        elif platform == "reddit":
            script_name = "run_reddit_simulation.py"
            state.reddit_running = True
        else:
            script_name = "run_parallel_simulation.py"
            state.twitter_running = True
            state.reddit_running = True

        script_path = os.path.join(cls.SCRIPTS_DIR, script_name)

        if not os.path.exists(script_path):
            raise AppError(f"脚本不存在: {script_path}", status=404)

        # 创建动作队列
        action_queue = Queue()
        cls._action_queues[simulation_id] = action_queue

        # 启动模拟进程
        try:
            # 构建运行命令，使用完整路径
            # 新的日志结构：
            #   twitter/actions.jsonl - Twitter 动作日志
            #   reddit/actions.jsonl  - Reddit 动作日志
            #   simulation.log        - 主进程日志

            cmd = [
                sys.executable,  # Python解释器
                script_path,
                "--config",
                config_path,  # 使用完整配置文件路径
            ]

            # 如果指定了最大轮数，添加到命令行参数
            if max_rounds is not None and max_rounds > 0:
                cmd.extend(["--max-rounds", str(max_rounds)])

            # 创建主日志文件，避免 stdout/stderr 管道缓冲区满导致进程阻塞
            main_log_path = os.path.join(sim_dir, "simulation.log")
            main_log_file = open(main_log_path, "w", encoding="utf-8")

            # 设置子进程环境变量，确保 Windows 上使用 UTF-8 编码
            # 这可以修复第三方库（如 OASIS）读取文件时未指定编码的问题
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"  # Python 3.7+ 支持，让所有 open() 默认使用 UTF-8
            env["PYTHONIOENCODING"] = "utf-8"  # 确保 stdout/stderr 使用 UTF-8

            # 设置工作目录为模拟目录（数据库等文件会生成在此）
            # 使用 start_new_session=True 创建新的进程组，确保可以通过 os.killpg 终止所有子进程
            process = subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=main_log_file,
                stderr=subprocess.STDOUT,  # stderr 也写入同一个文件
                text=True,
                encoding="utf-8",  # 显式指定编码
                bufsize=1,
                env=env,  # 传递带有 UTF-8 设置的环境变量
                start_new_session=True,  # 创建新进程组，确保服务器关闭时能终止所有相关进程
            )

            # 保存文件句柄以便后续关闭
            cls._stdout_files[simulation_id] = main_log_file
            cls._stderr_files[simulation_id] = None  # 不再需要单独的 stderr

            state.process_pid = process.pid
            state.process_start_time = cls._read_process_start_time(process.pid)
            state.runner_status = RunnerStatus.RUNNING
            # 持久化图谱记忆配置 + 抢占监控所有权（便于其他进程接管时重建）
            state.graph_id = graph_id
            state.graph_memory_enabled = bool(enable_graph_memory_update)
            state.owner_id = cls._inst_id()
            state.owner_heartbeat = time.time()
            cls._processes[simulation_id] = process
            cls._save_run_state(state)

            # Capture locale before spawning monitor thread
            current_locale = get_locale()

            # 启动监控线程
            monitor_thread = threading.Thread(
                target=cls._monitor_simulation, args=(simulation_id, current_locale), daemon=True
            )
            monitor_thread.start()
            cls._monitor_threads[simulation_id] = monitor_thread

            logger.info(f"模拟启动成功: {simulation_id}, pid={process.pid}, platform={platform}")

        except Exception as e:
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
            raise

        return state

    @classmethod
    def _monitor_simulation(cls, simulation_id: str, locale: str = "zh"):
        """监控模拟进程，解析动作日志。

        可监控两类进程：
        - 本进程亲自 Popen 的（`_processes` 有句柄）：用 process.poll() 判存活，退出码判终态。
        - 接管的孤儿（无句柄）：用 PID 探活，据 actions.jsonl 有无 simulation_end 判 completed/interrupted。

        关键：日志读取偏移从持久化的 `*_log_offset` 续读、每 tick 落库，接管时不重读 → 不重复推图谱记忆。
        若本进程被「松手」（_detaching）或所有权被他人接管，则直接退出而不改终态。
        """
        set_locale(locale)
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)

        # 新的日志结构：分平台的动作日志
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")

        process = cls._processes.get(simulation_id)  # 孤儿接管时为 None
        state = cls._run_states.get(simulation_id) or cls._load_run_state(simulation_id)

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
            return cls._pid_alive(pid, start_time)

        try:
            tick = 0
            while _alive():
                if cls._detaching:
                    # 进程退出/热重载：松手退出，不改终态，交给下次 reconcile 接管
                    logger.info(f"监控松手退出（进程将退出）: {simulation_id}")
                    return

                if os.path.exists(twitter_actions_log):
                    twitter_position = cls._read_action_log(
                        twitter_actions_log, twitter_position, state, "twitter"
                    )
                    state.twitter_log_offset = twitter_position
                if os.path.exists(reddit_actions_log):
                    reddit_position = cls._read_action_log(
                        reddit_actions_log, reddit_position, state, "reddit"
                    )
                    state.reddit_log_offset = reddit_position

                # 刷新所有权心跳后落库
                state.owner_id = cls._inst_id()
                state.owner_heartbeat = time.time()
                cls._save_run_state(state)

                tick += 1
                # 周期性确认仍是 owner，否则让位退出（避免多进程重复监控/重复推图谱记忆）
                if tick % 5 == 0 and not cls._still_owner(simulation_id):
                    logger.info(f"监控所有权已被接管，让位退出: {simulation_id}")
                    return

                time.sleep(2)

            # 进程已结束：最后读取一次日志（续偏移）
            if os.path.exists(twitter_actions_log):
                twitter_position = cls._read_action_log(
                    twitter_actions_log, twitter_position, state, "twitter"
                )
                state.twitter_log_offset = twitter_position
            if os.path.exists(reddit_actions_log):
                reddit_position = cls._read_action_log(
                    reddit_actions_log, reddit_position, state, "reddit"
                )
                state.reddit_log_offset = reddit_position

            # 终态判定
            if state.runner_status == RunnerStatus.COMPLETED:
                # _read_action_log 已据 simulation_end 置为 completed
                if not state.completed_at:
                    state.completed_at = datetime.now().isoformat()
                logger.info(f"模拟完成: {simulation_id}")
            elif process is not None:
                # 本进程亲自启动：用退出码判定
                exit_code = process.returncode
                if exit_code == 0 or cls._has_simulation_end(sim_dir):
                    state.runner_status = RunnerStatus.COMPLETED
                    state.completed_at = datetime.now().isoformat()
                    logger.info(f"模拟完成: {simulation_id}")
                else:
                    state.runner_status = RunnerStatus.FAILED
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
            else:
                # 接管的孤儿无退出码：据 simulation_end 判定 completed / interrupted
                if cls._has_simulation_end(sim_dir):
                    state.runner_status = RunnerStatus.COMPLETED
                    state.completed_at = datetime.now().isoformat()
                    logger.info(f"接管的模拟自然完成: {simulation_id}")
                else:
                    state.runner_status = RunnerStatus.INTERRUPTED
                    logger.warning(f"接管的模拟进程已消失且未跑完，标记中断: {simulation_id}")

            # 任意终态都上传 agent 记忆快照到 S3：强停/中断的模拟同样已周期性落盘，
            # 用户多半正是对"提前结束"的推演发起采访（无 agent_memory 时该调用是空操作）。
            cls._upload_run_artifacts(simulation_id, sim_dir)

            state.twitter_running = False
            state.reddit_running = False
            state.owner_id = None
            state.owner_heartbeat = None
            cls._save_run_state(state)

        except Exception as e:
            logger.error(f"监控线程异常: {simulation_id}, error={str(e)}")
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)

        finally:
            # 停止图谱记忆更新器
            if cls._graph_memory_enabled.get(simulation_id, False):
                try:
                    GraphMemoryManager.stop_updater(simulation_id)
                    logger.info(f"已停止图谱记忆更新: simulation_id={simulation_id}")
                except Exception as e:
                    logger.error(f"停止图谱记忆更新器失败: {e}")
                cls._graph_memory_enabled.pop(simulation_id, None)

            # 清理进程资源（本进程不再监控此模拟）
            cls._processes.pop(simulation_id, None)
            cls._action_queues.pop(simulation_id, None)
            cls._monitor_threads.pop(simulation_id, None)

            # 关闭日志文件句柄
            if simulation_id in cls._stdout_files:
                try:
                    cls._stdout_files[simulation_id].close()
                except Exception:
                    pass
                cls._stdout_files.pop(simulation_id, None)
            if simulation_id in cls._stderr_files and cls._stderr_files[simulation_id]:
                try:
                    cls._stderr_files[simulation_id].close()
                except Exception:
                    pass
                cls._stderr_files.pop(simulation_id, None)

    @classmethod
    def _read_action_log(
        cls, log_path: str, position: int, state: SimulationRunState, platform: str
    ) -> int:
        """
        读取动作日志文件

        Args:
            log_path: 日志文件路径
            position: 上次读取位置
            state: 运行状态对象
            platform: 平台名称 (twitter/reddit)

        Returns:
            新的读取位置
        """
        # 检查是否启用了图谱记忆更新
        graph_memory_enabled = cls._graph_memory_enabled.get(state.simulation_id, False)
        graph_updater = None
        if graph_memory_enabled:
            graph_updater = GraphMemoryManager.get_updater(state.simulation_id)

        try:
            with open(log_path, encoding="utf-8") as f:
                f.seek(position)
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            action_data = json.loads(line)

                            # 处理事件类型的条目
                            if "event_type" in action_data:
                                event_type = action_data.get("event_type")

                                # 检测 simulation_end 事件，标记平台已完成
                                if event_type == "simulation_end":
                                    if platform == "twitter":
                                        state.twitter_completed = True
                                        state.twitter_running = False
                                        logger.info(
                                            f"Twitter 模拟已完成: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}"
                                        )
                                    elif platform == "reddit":
                                        state.reddit_completed = True
                                        state.reddit_running = False
                                        logger.info(
                                            f"Reddit 模拟已完成: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}"
                                        )

                                    # 检查是否所有启用的平台都已完成
                                    # 如果只运行了一个平台，只检查那个平台
                                    # 如果运行了两个平台，需要两个都完成
                                    all_completed = cls._check_all_platforms_completed(state)
                                    if all_completed:
                                        state.runner_status = RunnerStatus.COMPLETED
                                        state.completed_at = datetime.now().isoformat()
                                        logger.info(f"所有平台模拟已完成: {state.simulation_id}")

                                # 更新轮次信息（从 round_end 事件）
                                elif event_type == "round_end":
                                    round_num = action_data.get("round", 0)
                                    simulated_hours = action_data.get("simulated_hours", 0)

                                    # 更新各平台独立的轮次和时间
                                    if platform == "twitter":
                                        if round_num > state.twitter_current_round:
                                            state.twitter_current_round = round_num
                                        state.twitter_simulated_hours = simulated_hours
                                    elif platform == "reddit":
                                        if round_num > state.reddit_current_round:
                                            state.reddit_current_round = round_num
                                        state.reddit_simulated_hours = simulated_hours

                                    # 总体轮次取两个平台的最大值
                                    if round_num > state.current_round:
                                        state.current_round = round_num
                                    # 总体时间取两个平台的最大值
                                    state.simulated_hours = max(
                                        state.twitter_simulated_hours, state.reddit_simulated_hours
                                    )

                                continue

                            action = AgentAction(
                                round_num=action_data.get("round", 0),
                                timestamp=action_data.get("timestamp", datetime.now().isoformat()),
                                platform=platform,
                                agent_id=action_data.get("agent_id", 0),
                                agent_name=action_data.get("agent_name", ""),
                                action_type=action_data.get("action_type", ""),
                                action_args=action_data.get("action_args", {}),
                                result=action_data.get("result"),
                                success=action_data.get("success", True),
                            )
                            state.add_action(action)

                            # 更新轮次
                            if action.round_num and action.round_num > state.current_round:
                                state.current_round = action.round_num

                            # 如果启用了图谱记忆更新，将活动发送到图谱
                            if graph_updater:
                                graph_updater.add_activity_from_dict(action_data, platform)

                        except json.JSONDecodeError:
                            pass
                return f.tell()
        except Exception as e:
            logger.warning(f"读取动作日志失败: {log_path}, error={e}")
            return position

    @classmethod
    def _check_all_platforms_completed(cls, state: SimulationRunState) -> bool:
        """
        检查所有启用的平台是否都已完成模拟

        通过检查对应的 actions.jsonl 文件是否存在来判断平台是否被启用

        Returns:
            True 如果所有启用的平台都已完成
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        twitter_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_log = os.path.join(sim_dir, "reddit", "actions.jsonl")

        # 检查哪些平台被启用（通过文件是否存在判断）
        twitter_enabled = os.path.exists(twitter_log)
        reddit_enabled = os.path.exists(reddit_log)

        # 如果平台被启用但未完成，则返回 False
        if twitter_enabled and not state.twitter_completed:
            return False
        if reddit_enabled and not state.reddit_completed:
            return False

        # 至少有一个平台被启用且已完成
        return twitter_enabled or reddit_enabled

    @classmethod
    def reconcile_running_simulations(
        cls, locale: str = "zh", reset_detach: bool = True
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
            cls._detaching = False
            cls._detached = False

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
            state = cls._load_run_state(sid)
            if not state:
                continue

            local_alive = cls._pid_alive(state.process_pid, state.process_start_time)
            env_alive = cls._env_alive(sid)

            if env_alive or local_alive:
                # 仍在运行（本机或他机）。仅当进程在【本机】存活且无人监控时由本进程接管监控；
                # 进程在异机时不跨机抢监控（无法 poll 异机 PID / tail 其本地日志），交给运行它的
                # worker 自行监控 —— 但绝不在此把存活的远端模拟误判为已死。
                if (
                    local_alive
                    and sid not in cls._monitor_threads
                    and cls._try_claim_ownership(sid)
                ):
                    cls._run_states[sid] = state
                    cls._graph_memory_enabled[sid] = bool(state.graph_memory_enabled)
                    if state.graph_memory_enabled and state.graph_id:
                        try:
                            GraphMemoryManager.create_updater(sid, state.graph_id)
                        except Exception as e:
                            logger.error(f"接管时重建图谱记忆更新器失败: {sid}, error={e}")
                    th = threading.Thread(
                        target=cls._monitor_simulation, args=(sid, locale), daemon=True
                    )
                    th.start()
                    cls._monitor_threads[sid] = th
                    adopted.append(sid)
                    logger.info(f"已接管运行中的模拟: {sid}, pid={state.process_pid}")
                continue

            # 既无 Redis 心跳、本机也无存活 PID。若仍有新鲜 owner（其 worker 暂时探测不到但
            # 心跳未过期），让它自己终结，避免争用；否则视为真正已死，据 actions.jsonl 终结。
            if cls._owner_fresh(state):
                continue

            sim_dir = os.path.join(cls.RUN_STATE_DIR, sid)
            if cls._has_simulation_end(sim_dir):
                state.runner_status = RunnerStatus.COMPLETED
                if not state.completed_at:
                    state.completed_at = datetime.now().isoformat()
            else:
                state.runner_status = RunnerStatus.INTERRUPTED
            state.twitter_running = False
            state.reddit_running = False
            state.owner_id = None
            state.owner_heartbeat = None
            cls._save_run_state(state)
            finalized.append(sid)
            logger.info(f"终结已死的模拟: {sid} -> {state.runner_status.value}")

        if adopted or finalized:
            logger.info(f"模拟对账完成: 接管={adopted}, 终结={finalized}")
        return {"adopted": adopted, "finalized": finalized}

    @staticmethod
    def _kill_pid_group(pid: int, timeout: int = 45) -> None:
        """按 PID 杀进程组（委托 process_control）。"""
        pc.kill_pid_group(pid, timeout)

    @classmethod
    def _terminate_process(cls, process: subprocess.Popen, simulation_id: str, timeout: int = 45):
        """
        跨平台终止进程及其子进程

        Args:
            process: 要终止的进程
            simulation_id: 模拟ID（用于日志）
            timeout: 等待进程退出的超时时间（秒）。SIGTERM 后给模拟留出收尾时间，让其
                优雅跳出当前轮、落盘 agent 记忆快照（供唤醒采访）后再退出；进程一旦完成
                收尾即刻退出，wait 随之返回，故放宽上限对正常停止无额外延迟。
        """
        if IS_WINDOWS:
            # Windows: 使用 taskkill 命令终止进程树
            # /F = 强制终止, /T = 终止进程树（包括子进程）
            logger.info(f"终止进程树 (Windows): simulation={simulation_id}, pid={process.pid}")
            try:
                # 先尝试优雅终止
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T"], capture_output=True, timeout=5
                )
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # 强制终止
                    logger.warning(f"进程未响应，强制终止: {simulation_id}")
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(process.pid), "/T"],
                        capture_output=True,
                        timeout=5,
                    )
                    process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"taskkill 失败，尝试 terminate: {e}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        else:
            # Unix: 使用进程组终止
            # 由于使用了 start_new_session=True，进程组 ID 等于主进程 PID
            pgid = os.getpgid(process.pid)
            logger.info(f"终止进程组 (Unix): simulation={simulation_id}, pgid={pgid}")

            # 先发送 SIGTERM 给整个进程组
            os.killpg(pgid, signal.SIGTERM)

            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # 如果超时后还没结束，强制发送 SIGKILL
                logger.warning(f"进程组未响应 SIGTERM，强制终止: {simulation_id}")
                os.killpg(pgid, signal.SIGKILL)
                process.wait(timeout=5)

    @classmethod
    def stop_simulation(cls, simulation_id: str) -> SimulationRunState:
        """停止模拟"""
        state = cls.get_run_state(simulation_id)
        if not state:
            raise AppError(f"模拟不存在: {simulation_id}", status=404)

        if state.runner_status not in [RunnerStatus.RUNNING, RunnerStatus.PAUSED]:
            raise AppError(
                f"模拟未在运行: {simulation_id}, status={state.runner_status}", status=409
            )

        state.runner_status = RunnerStatus.STOPPING
        cls._save_run_state(state)

        # 终止进程
        process = cls._processes.get(simulation_id)
        if process and process.poll() is None:
            # 本进程亲自启动的：用 Popen 句柄终止进程组
            try:
                cls._terminate_process(process, simulation_id)
            except ProcessLookupError:
                # 进程已经不存在
                pass
            except Exception as e:
                logger.error(f"终止进程组失败: {simulation_id}, error={e}")
                # 回退到直接终止进程
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
        elif cls._pid_alive(state.process_pid, state.process_start_time):
            # 孤儿（无本进程句柄，如重启后接管的）：按 PID 杀进程组
            logger.info(f"按 PID 终止孤儿模拟: {simulation_id}, pid={state.process_pid}")
            try:
                cls._kill_pid_group(state.process_pid)
            except Exception as e:
                logger.error(f"按 PID 终止失败: {simulation_id}, error={e}")
        else:
            # 既无本机句柄、PID 也不在本机存活：子进程可能跑在另一台 worker 上。
            # 经 Redis IPC 投递 close_env，让其优雅自关（位置无关，不阻塞等响应）。
            try:
                sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
                SimulationIPCClient(sim_dir).post_command(CommandType.CLOSE_ENV, {})
                logger.info(f"已经 Redis 投递 close_env 停止远端模拟: {simulation_id}")
            except Exception as e:
                logger.warning(f"投递 close_env 失败: {simulation_id}, error={e}")

        state.runner_status = RunnerStatus.STOPPED
        state.twitter_running = False
        state.reddit_running = False
        state.completed_at = datetime.now().isoformat()
        state.owner_id = None
        state.owner_heartbeat = None
        cls._save_run_state(state)

        # 进程已优雅退出并落盘 agent 记忆，主动同步一次到 S3（与 monitor 上传幂等），
        # 确保用户对"提前结束"的推演也能按需唤醒采访。
        cls._upload_run_artifacts(simulation_id, os.path.join(cls.RUN_STATE_DIR, simulation_id))

        # 停止图谱记忆更新器
        if cls._graph_memory_enabled.get(simulation_id, False):
            try:
                GraphMemoryManager.stop_updater(simulation_id)
                logger.info(f"已停止图谱记忆更新: simulation_id={simulation_id}")
            except Exception as e:
                logger.error(f"停止图谱记忆更新器失败: {e}")
            cls._graph_memory_enabled.pop(simulation_id, None)

        logger.info(f"模拟已停止: {simulation_id}")
        return state

    # 动作日志读取委托 log_reader（保留旧方法名/签名，路由与调用方不变）
    @classmethod
    def _read_actions_from_file(
        cls,
        file_path: str,
        default_platform: str | None = None,
        platform_filter: str | None = None,
        agent_id: int | None = None,
        round_num: int | None = None,
    ) -> list[AgentAction]:
        return log_reader.read_actions_from_file(
            file_path, default_platform, platform_filter, agent_id, round_num
        )

    @classmethod
    def get_all_actions(
        cls,
        simulation_id: str,
        platform: str | None = None,
        agent_id: int | None = None,
        round_num: int | None = None,
    ) -> list[AgentAction]:
        """获取所有平台的完整动作历史（按时间戳倒序，无分页）。"""
        return log_reader.get_all_actions(
            cls.RUN_STATE_DIR,
            simulation_id,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num,
        )

    @classmethod
    def get_actions(
        cls,
        simulation_id: str,
        limit: int = 100,
        offset: int = 0,
        platform: str | None = None,
        agent_id: int | None = None,
        round_num: int | None = None,
    ) -> list[AgentAction]:
        """获取动作历史（带分页）。"""
        return log_reader.get_actions(
            cls.RUN_STATE_DIR,
            simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num,
        )

    @classmethod
    def get_timeline(
        cls, simulation_id: str, start_round: int = 0, end_round: int | None = None
    ) -> list[dict[str, Any]]:
        """获取模拟时间线（按轮次汇总）。"""
        return log_reader.get_timeline(cls.RUN_STATE_DIR, simulation_id, start_round, end_round)

    @classmethod
    def get_agent_stats(cls, simulation_id: str) -> list[dict[str, Any]]:
        """获取每个 Agent 的统计信息。"""
        return log_reader.get_agent_stats(cls.RUN_STATE_DIR, simulation_id)

    @classmethod
    def cleanup_simulation_logs(cls, simulation_id: str) -> dict[str, Any]:
        """
        清理模拟的运行日志（用于强制重新开始模拟）

        会删除以下文件/记录：
        - 运行状态快照（Postgres）
        - twitter/actions.jsonl
        - reddit/actions.jsonl
        - simulation.log
        - stdout.log / stderr.log
        - twitter_simulation.db（模拟数据库）
        - reddit_simulation.db（模拟数据库）
        - env_status.json（环境状态）

        注意：不会删除配置文件（simulation_config.json）和 profile 文件

        Args:
            simulation_id: 模拟ID

        Returns:
            清理结果信息
        """

        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return {"success": True, "message": "模拟目录不存在，无需清理"}

        cleaned_files = []
        errors = []

        # 要删除的文件列表（包括数据库文件）
        files_to_delete = [
            "simulation.log",
            "stdout.log",
            "stderr.log",
            "twitter_simulation.db",  # Twitter 平台数据库
            "reddit_simulation.db",  # Reddit 平台数据库
            "env_status.json",  # 环境状态文件
        ]

        # 要删除的目录列表（包含动作日志）
        dirs_to_clean = ["twitter", "reddit"]

        # 删除文件
        for filename in files_to_delete:
            file_path = os.path.join(sim_dir, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    cleaned_files.append(filename)
                except Exception as e:
                    errors.append(f"删除 {filename} 失败: {str(e)}")

        # 清理平台目录中的动作日志
        for dir_name in dirs_to_clean:
            dir_path = os.path.join(sim_dir, dir_name)
            if os.path.exists(dir_path):
                actions_file = os.path.join(dir_path, "actions.jsonl")
                if os.path.exists(actions_file):
                    try:
                        os.remove(actions_file)
                        cleaned_files.append(f"{dir_name}/actions.jsonl")
                    except Exception as e:
                        errors.append(f"删除 {dir_name}/actions.jsonl 失败: {str(e)}")

        # 清理内存中的运行状态
        if simulation_id in cls._run_states:
            del cls._run_states[simulation_id]

        # 清理 Postgres 中的运行状态快照
        try:
            RunStateRepository.delete(simulation_id)
        except Exception as e:
            errors.append(f"清理运行状态(PG)失败: {str(e)}")

        logger.info(f"清理模拟日志完成: {simulation_id}, 删除文件: {cleaned_files}")

        return {
            "success": len(errors) == 0,
            "cleaned_files": cleaned_files,
            "errors": errors if errors else None,
        }

    @classmethod
    def detach_all_simulations(cls):
        """进程退出 / 热重载时调用：「松手」而非「杀掉」。

        档位 A 语义：让 OASIS 子进程作为受控孤儿继续跑完，由下次启动的 reconcile 接管。
        因此这里只：置松手标志让监控线程尽快退出、释放监控所有权、停本进程的图谱 updater
        线程、关文件句柄、清本进程内存引用——**不 killpg、不改 runner_status、不动元数据**。
        """
        if cls._detached:
            return
        cls._detached = True
        cls._detaching = True

        if not cls._processes and not cls._monitor_threads and not cls._graph_memory_enabled:
            return  # 本进程没在监控任何模拟，静默返回

        logger.info("正在松手退出（保留运行中的模拟子进程，待下次启动接管）...")

        # 释放本进程持有的监控所有权，便于新进程立即接管
        for sim_id in list(cls._monitor_threads.keys()):
            try:
                cls._release_ownership(sim_id)
            except Exception:
                pass

        # 停止本进程的图谱记忆 updater 线程（不影响子进程；接管进程会重建）
        try:
            GraphMemoryManager.stop_all()
        except Exception as e:
            logger.error(f"停止图谱记忆更新器失败: {e}")
        cls._graph_memory_enabled.clear()

        # 关闭文件句柄
        for file_handle in list(cls._stdout_files.values()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stdout_files.clear()
        cls._stderr_files.clear()

        # 丢弃本进程的句柄/引用，但**不终止子进程**
        cls._processes.clear()
        cls._monitor_threads.clear()
        cls._action_queues.clear()

        logger.info("已松手退出")

    @classmethod
    def cleanup_all_simulations(cls):
        """运维「全部停止」：真正终止所有正在运行的模拟（含孤儿）并置 stopped。

        与 detach 不同，这里会杀子进程。仅由显式运维入口（如 /admin/stop-all）调用，
        **不再注册到进程退出钩子**（退出走 detach「松手」）。
        """
        # 收集所有运行中的模拟：本进程内存中的 + PG 标记 running/starting 的
        ids = set(cls._processes.keys())
        try:
            for sid, data in RunStateRepository.load_all_raw().items():
                if (data or {}).get("runner_status") in ("running", "starting"):
                    ids.add(sid)
        except Exception as e:
            logger.error(f"读取运行中模拟列表失败: {e}")

        stopped = []
        for simulation_id in ids:
            try:
                state = cls.get_run_state(simulation_id)
                if state and state.runner_status in (RunnerStatus.RUNNING, RunnerStatus.PAUSED):
                    cls.stop_simulation(simulation_id)
                    stopped.append(simulation_id)
            except Exception as e:
                logger.error(f"停止模拟失败: {simulation_id}, error={e}")

        logger.info(f"运维全停完成: stopped={stopped}")
        return {"stopped": stopped}

    @classmethod
    def register_cleanup(cls):
        """注册进程退出钩子：退出/热重载时「松手」（detach），不杀子进程、不误置 stopped。

        在 FastAPI lifespan startup 调用。退出动作为「松手」而非「杀掉」。
        """
        global _cleanup_registered

        if _cleanup_registered:
            return

        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sighup = None
        has_sighup = hasattr(signal, "SIGHUP")
        if has_sighup:
            original_sighup = signal.getsignal(signal.SIGHUP)

        def detach_handler(signum=None, frame=None):
            """信号处理器：松手后调用原处理器，让服务正常退出。"""
            if cls._processes or cls._monitor_threads:
                logger.info(f"收到信号 {signum}，松手退出（保留子进程）...")
            cls.detach_all_simulations()

            if signum == signal.SIGINT and callable(original_sigint):
                original_sigint(signum, frame)
            elif signum == signal.SIGTERM and callable(original_sigterm):
                original_sigterm(signum, frame)
            elif has_sighup and signum == signal.SIGHUP:
                if callable(original_sighup):
                    original_sighup(signum, frame)
                else:
                    sys.exit(0)
            else:
                raise KeyboardInterrupt

        # atexit 兜底
        atexit.register(cls.detach_all_simulations)

        try:
            signal.signal(signal.SIGTERM, detach_handler)
            signal.signal(signal.SIGINT, detach_handler)
            if has_sighup:
                signal.signal(signal.SIGHUP, detach_handler)
        except ValueError:
            logger.warning("无法注册信号处理器（不在主线程），仅使用 atexit")

        _cleanup_registered = True

    @classmethod
    def get_running_simulations(cls) -> list[str]:
        """
        获取所有正在运行的模拟ID列表
        """
        running = []
        for sim_id, process in cls._processes.items():
            if process.poll() is None:
                running.append(sim_id)
        return running

    # ============== Interview 功能 ==============

    @classmethod
    def _upload_run_artifacts(cls, simulation_id: str, sim_dir: str) -> None:
        """模拟完成后把 agent 记忆快照上传 S3，供后续按需唤醒环境采访时取回（失败不阻断）。"""
        try:
            from ..utils import object_store

            mem_dir = os.path.join(sim_dir, "agent_memory")
            if not os.path.isdir(mem_dir):
                return
            uploaded = 0
            for fn in os.listdir(mem_dir):
                if fn.endswith(".json"):
                    object_store.upload_file(
                        f"simulations/{simulation_id}/agent_memory/{fn}",
                        os.path.join(mem_dir, fn),
                        "application/json",
                    )
                    uploaded += 1
            if uploaded:
                logger.info(f"已上传 {uploaded} 份 agent 记忆到 S3: {simulation_id}")
        except Exception as e:
            logger.warning(f"上传 agent 记忆到 S3 失败（不影响）: {simulation_id}, {e}")

    @classmethod
    def wake_env(cls, simulation_id: str) -> dict[str, Any]:
        """
        按需唤醒模拟环境：环境已活则直接返回；否则从 S3 物化 sim_dir（配置/profiles/记忆快照），
        以 --resume-env 重建环境并进入等待命令模式（不跑模拟循环），供采访使用。
        起进程后立即返回 status=waking，由调用方轮询 check_env_alive 至 alive。
        """
        if cls.check_env_alive(simulation_id):
            return {"success": True, "status": "alive"}

        # 60s 内已发起过唤醒则不重复起进程（前端轮询期间防重）
        if not hasattr(cls, "_waking_at"):
            cls._waking_at = {}
        now = time.monotonic()
        last = cls._waking_at.get(simulation_id)
        if last is not None and (now - last) < 60:
            return {"success": True, "status": "waking"}

        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        mem_dir = os.path.join(sim_dir, "agent_memory")

        # 从 S3 物化缺失的输入（配置/profiles/记忆快照）
        if not os.path.exists(config_path) or not os.path.isdir(mem_dir):
            try:
                from ..utils import object_store

                object_store.download_prefix_to_dir(f"simulations/{simulation_id}/", sim_dir)
            except Exception as e:
                logger.warning(f"唤醒前从 S3 物化失败: {simulation_id}, {e}")

        if not os.path.exists(config_path):
            return {"success": False, "error": "缺少模拟配置，无法唤醒环境"}
        if not os.path.isdir(mem_dir):
            return {
                "success": False,
                "error": "缺少 agent 记忆快照，无法唤醒（该模拟可能在记忆持久化前就已结束）",
            }

        script_path = os.path.join(cls.SCRIPTS_DIR, "run_parallel_simulation.py")
        cmd = [sys.executable, script_path, "--config", config_path, "--resume-env"]
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            log_file = open(os.path.join(sim_dir, "resume.log"), "w", encoding="utf-8")
            subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=env,
                start_new_session=True,
            )
        except Exception as e:
            return {"success": False, "error": f"启动恢复进程失败: {e}"}

        cls._waking_at[simulation_id] = now
        logger.info(f"已发起环境唤醒（恢复模式）: {simulation_id}")
        return {"success": True, "status": "waking"}

    @classmethod
    def check_env_alive(cls, simulation_id: str) -> bool:
        """
        检查模拟环境是否存活（可以接收Interview命令）

        Args:
            simulation_id: 模拟ID

        Returns:
            True 表示环境存活，False 表示环境已关闭
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return False

        ipc_client = SimulationIPCClient(sim_dir)
        return ipc_client.check_env_alive()

    @classmethod
    def get_env_status_detail(cls, simulation_id: str) -> dict[str, Any]:
        """
        获取模拟环境的详细状态信息

        Args:
            simulation_id: 模拟ID

        Returns:
            状态详情字典，包含 status, twitter_available, reddit_available, timestamp
        """
        from .simulation_ipc import read_env_status

        return read_env_status(simulation_id)

    @classmethod
    def interview_agent(
        cls,
        simulation_id: str,
        agent_id: int,
        prompt: str,
        platform: str | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """
        采访单个Agent

        Args:
            simulation_id: 模拟ID
            agent_id: Agent ID
            prompt: 采访问题
            platform: 指定平台（可选）
                - "twitter": 只采访Twitter平台
                - "reddit": 只采访Reddit平台
                - None: 双平台模拟时同时采访两个平台，返回整合结果
            timeout: 超时时间（秒）

        Returns:
            采访结果字典

        Raises:
            ValueError: 模拟不存在或环境未运行
            TimeoutError: 等待响应超时
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise AppError(f"模拟不存在: {simulation_id}", status=404)

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise AppError(
                f"模拟环境未运行或已关闭，无法执行Interview: {simulation_id}", status=409
            )

        logger.info(
            f"发送Interview命令: simulation_id={simulation_id}, agent_id={agent_id}, platform={platform}"
        )

        response = ipc_client.send_interview(
            agent_id=agent_id, prompt=prompt, platform=platform, timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "agent_id": agent_id,
                "prompt": prompt,
                "result": response.result,
                "timestamp": response.timestamp,
            }
        else:
            return {
                "success": False,
                "agent_id": agent_id,
                "prompt": prompt,
                "error": response.error,
                "timestamp": response.timestamp,
            }

    @classmethod
    def interview_agents_batch(
        cls,
        simulation_id: str,
        interviews: list[dict[str, Any]],
        platform: str | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        批量采访多个Agent

        Args:
            simulation_id: 模拟ID
            interviews: 采访列表，每个元素包含 {"agent_id": int, "prompt": str, "platform": str(可选)}
            platform: 默认平台（可选，会被每个采访项的platform覆盖）
                - "twitter": 默认只采访Twitter平台
                - "reddit": 默认只采访Reddit平台
                - None: 双平台模拟时每个Agent同时采访两个平台
            timeout: 超时时间（秒）

        Returns:
            批量采访结果字典

        Raises:
            ValueError: 模拟不存在或环境未运行
            TimeoutError: 等待响应超时
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise AppError(f"模拟不存在: {simulation_id}", status=404)

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise AppError(
                f"模拟环境未运行或已关闭，无法执行Interview: {simulation_id}", status=409
            )

        logger.info(
            f"发送批量Interview命令: simulation_id={simulation_id}, count={len(interviews)}, platform={platform}"
        )

        response = ipc_client.send_batch_interview(
            interviews=interviews, platform=platform, timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "interviews_count": len(interviews),
                "result": response.result,
                "timestamp": response.timestamp,
            }
        else:
            return {
                "success": False,
                "interviews_count": len(interviews),
                "error": response.error,
                "timestamp": response.timestamp,
            }

    @classmethod
    def interview_all_agents(
        cls, simulation_id: str, prompt: str, platform: str | None = None, timeout: float = 180.0
    ) -> dict[str, Any]:
        """
        采访所有Agent（全局采访）

        使用相同的问题采访模拟中的所有Agent

        Args:
            simulation_id: 模拟ID
            prompt: 采访问题（所有Agent使用相同问题）
            platform: 指定平台（可选）
                - "twitter": 只采访Twitter平台
                - "reddit": 只采访Reddit平台
                - None: 双平台模拟时每个Agent同时采访两个平台
            timeout: 超时时间（秒）

        Returns:
            全局采访结果字典
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise AppError(f"模拟不存在: {simulation_id}", status=404)

        # 从配置文件获取所有Agent信息
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            raise AppError(f"模拟配置不存在: {simulation_id}", status=404)

        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        agent_configs = config.get("agent_configs", [])
        if not agent_configs:
            raise AppError(f"模拟配置中没有Agent: {simulation_id}", status=404)

        # 构建批量采访列表
        interviews = []
        for agent_config in agent_configs:
            agent_id = agent_config.get("agent_id")
            if agent_id is not None:
                interviews.append({"agent_id": agent_id, "prompt": prompt})

        logger.info(
            f"发送全局Interview命令: simulation_id={simulation_id}, agent_count={len(interviews)}, platform={platform}"
        )

        return cls.interview_agents_batch(
            simulation_id=simulation_id, interviews=interviews, platform=platform, timeout=timeout
        )

    @classmethod
    def close_simulation_env(cls, simulation_id: str, timeout: float = 30.0) -> dict[str, Any]:
        """
        关闭模拟环境（而不是停止模拟进程）

        向模拟发送关闭环境命令，使其优雅退出等待命令模式

        Args:
            simulation_id: 模拟ID
            timeout: 超时时间（秒）

        Returns:
            操作结果字典
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise AppError(f"模拟不存在: {simulation_id}", status=404)

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            return {"success": True, "message": "环境已经关闭"}

        logger.info(f"发送关闭环境命令: simulation_id={simulation_id}")

        try:
            response = ipc_client.send_close_env(timeout=timeout)

            return {
                "success": response.status.value == "completed",
                "message": "环境关闭命令已发送",
                "result": response.result,
                "timestamp": response.timestamp,
            }
        except TimeoutError:
            # 超时可能是因为环境正在关闭
            return {
                "success": True,
                "message": "环境关闭命令已发送（等待响应超时，环境可能正在关闭）",
            }

    @classmethod
    def get_interview_history(
        cls,
        simulation_id: str,
        platform: str | None = None,
        agent_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        获取Interview历史记录（从数据库读取）

        Args:
            simulation_id: 模拟ID
            platform: 平台类型（reddit/twitter/None）
                - "reddit": 只获取Reddit平台的历史
                - "twitter": 只获取Twitter平台的历史
                - None: 获取两个平台的所有历史
            agent_id: 指定Agent ID（可选，只获取该Agent的历史）
            limit: 每个平台返回数量限制

        Returns:
            Interview历史记录列表
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)

        results = []

        # 确定要查询的平台
        if platform in ("reddit", "twitter"):
            platforms = [platform]
        else:
            # 不指定platform时，查询两个平台
            platforms = ["twitter", "reddit"]

        for p in platforms:
            db_path = os.path.join(sim_dir, f"{p}_simulation.db")
            platform_results = InterviewTraceRepository.list_interviews(
                db_path=db_path, platform_name=p, agent_id=agent_id, limit=limit
            )
            results.extend(platform_results)

        # 按时间降序排序
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # 如果查询了多个平台，限制总数
        if len(platforms) > 1 and len(results) > limit:
            results = results[:limit]

        return results
