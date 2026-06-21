"""SimulationRunner 集成测试（不起真实子进程）。

聚焦深拆 SimulationRunner（→ ProcessController/OwnershipLock/RunStateStore/...）前
最易回归的「编排逻辑」：
- 运行态持久化往返（RunStateStore 边界）；
- 进程探活与「死进程→终态」对账（ProcessController + 对账边界）；
- 监控所有权 CAS：抢占/确认/释放/TTL 过期接管（OwnershipLock 边界）；
- 启动对账 reconcile 终结已死运行。

需要 Postgres（conftest 已建表）。通过伪造 PID 与受控 sim 目录达成确定性，无需 OASIS。
"""

import os
import sqlite3
import time
import uuid
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.repositories.interview_trace_repo import InterviewTraceRepository
from app.repositories.run_state_repo import RunStateRepository
from app.services.simulation_runner import RunnerStatus, SimulationRunner, SimulationRunState


@pytest.fixture
def runner_cleanup():
    """记录用过的 simulation_id，测试后清理 DB 行与进程内缓存，避免跨用例污染。"""
    created: list[str] = []
    yield created
    for sid in created:
        try:
            RunStateRepository.delete(sid)
        except Exception:
            pass
        SimulationRunner._store.run_states.pop(sid, None)
        SimulationRunner._store.graph_memory_enabled.pop(sid, None)


def _new_sid(created: list[str]) -> str:
    sid = f"sim_test_{uuid.uuid4().hex[:12]}"
    created.append(sid)
    return sid


# ───────────────────────── 纯工具：解析 / 探活 ─────────────────────────


def test_parse_etime_formats():
    assert SimulationRunner._parse_etime("05") is None  # 单段非法
    assert SimulationRunner._parse_etime("01:02") == 62  # mm:ss
    assert SimulationRunner._parse_etime("01:02:03") == 3723  # hh:mm:ss
    assert SimulationRunner._parse_etime("2-00:00:00") == 172800  # dd-hh:mm:ss
    assert SimulationRunner._parse_etime("") is None


def test_decide_terminal_status():
    from app.services.simulation import process_control as pc

    # already_completed 优先（_read_action_log 已据 simulation_end 置 completed）
    assert (
        pc.decide_terminal_status(
            already_completed=True, is_own_process=True, exit_code=1, has_sim_end=False
        )
        == RunnerStatus.COMPLETED
    )
    # 本进程：退出码 0 → COMPLETED
    assert (
        pc.decide_terminal_status(
            already_completed=False, is_own_process=True, exit_code=0, has_sim_end=False
        )
        == RunnerStatus.COMPLETED
    )
    # 本进程：非 0 退出码但已见 simulation_end → COMPLETED
    assert (
        pc.decide_terminal_status(
            already_completed=False, is_own_process=True, exit_code=137, has_sim_end=True
        )
        == RunnerStatus.COMPLETED
    )
    # 本进程：非 0 退出码且未跑完 → FAILED
    assert (
        pc.decide_terminal_status(
            already_completed=False, is_own_process=True, exit_code=1, has_sim_end=False
        )
        == RunnerStatus.FAILED
    )
    # 接管孤儿（无退出码）：见 simulation_end → COMPLETED
    assert (
        pc.decide_terminal_status(
            already_completed=False, is_own_process=False, exit_code=None, has_sim_end=True
        )
        == RunnerStatus.COMPLETED
    )
    # 接管孤儿：进程消失且未跑完 → INTERRUPTED
    assert (
        pc.decide_terminal_status(
            already_completed=False, is_own_process=False, exit_code=None, has_sim_end=False
        )
        == RunnerStatus.INTERRUPTED
    )


def test_pid_alive_basic():
    assert SimulationRunner._pid_alive(os.getpid()) is True
    assert SimulationRunner._pid_alive(None) is False
    # 999999 几乎不可能存在 → ProcessLookupError → 判死
    assert SimulationRunner._pid_alive(999999) is False


def test_has_simulation_end(tmp_path):
    sim_dir = tmp_path / "sim_x"
    (sim_dir / "reddit").mkdir(parents=True)
    log = sim_dir / "reddit" / "actions.jsonl"
    log.write_text('{"event":"step"}\n', encoding="utf-8")
    assert SimulationRunner._has_simulation_end(str(sim_dir)) is False
    log.write_text('{"event":"step"}\n{"event":"simulation_end"}\n', encoding="utf-8")
    assert SimulationRunner._has_simulation_end(str(sim_dir)) is True


# ───────────────────────── 监控循环：终态落地 + 资源清理 ─────────────────────────


class _DeadProc:
    """已退出的假进程：poll() 返回非 None（returncode），使监控循环体直接跳到终态处理。"""

    def __init__(self, returncode: int):
        self.returncode = returncode

    def poll(self):
        return self.returncode


class _FakeFile:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_monitor_own_process_completed_finalizes_and_cleans_up(
    runner_cleanup, tmp_path, monkeypatch
):
    """本进程亲自启动、退出码 0：落 COMPLETED + completed_at，置 running=False、owner 清空，
    并清理 store 中的进程/线程/文件句柄。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        SimulationRunner, "_upload_run_artifacts", classmethod(lambda c, s, d: None)
    )
    sid = _new_sid(runner_cleanup)
    (tmp_path / sid).mkdir(parents=True, exist_ok=True)
    SimulationRunner._save_run_state(
        SimulationRunState(
            simulation_id=sid,
            runner_status=RunnerStatus.RUNNING,
            twitter_running=True,
            reddit_running=True,
        )
    )
    SimulationRunner._store.processes[sid] = _DeadProc(0)  # type: ignore[assignment]
    SimulationRunner._store.monitor_threads[sid] = object()  # type: ignore[assignment]
    fout = _FakeFile()
    SimulationRunner._store.stdout_files[sid] = fout

    SimulationRunner._monitor_simulation(sid)

    got = SimulationRunner._load_run_state(sid)
    assert got.runner_status == RunnerStatus.COMPLETED
    assert got.completed_at
    assert got.twitter_running is False
    assert got.reddit_running is False
    assert got.owner_id is None
    # 资源清理
    assert sid not in SimulationRunner._store.processes
    assert sid not in SimulationRunner._store.monitor_threads
    assert sid not in SimulationRunner._store.stdout_files
    assert fout.closed is True


def test_monitor_own_process_nonzero_exit_marks_failed_with_log_tail(
    runner_cleanup, tmp_path, monkeypatch
):
    """本进程退出码非 0 且未见 simulation_end：落 FAILED，error 含退出码与日志尾部。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        SimulationRunner, "_upload_run_artifacts", classmethod(lambda c, s, d: None)
    )
    sid = _new_sid(runner_cleanup)
    sim_dir = tmp_path / sid
    sim_dir.mkdir(parents=True, exist_ok=True)
    (sim_dir / "simulation.log").write_text("boom traceback here", encoding="utf-8")
    SimulationRunner._save_run_state(
        SimulationRunState(simulation_id=sid, runner_status=RunnerStatus.RUNNING)
    )
    SimulationRunner._store.processes[sid] = _DeadProc(1)  # type: ignore[assignment]

    SimulationRunner._monitor_simulation(sid)

    got = SimulationRunner._load_run_state(sid)
    assert got.runner_status == RunnerStatus.FAILED
    assert "进程退出码: 1" in (got.error or "")
    assert "boom traceback here" in (got.error or "")


def test_monitor_orphan_dead_without_sim_end_marks_interrupted(
    runner_cleanup, tmp_path, monkeypatch
):
    """接管的孤儿（无本机句柄）：PID 已死且未见 simulation_end → INTERRUPTED。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        SimulationRunner, "_upload_run_artifacts", classmethod(lambda c, s, d: None)
    )
    monkeypatch.setattr(SimulationRunner, "_pid_alive", classmethod(lambda c, p, s=None: False))
    sid = _new_sid(runner_cleanup)
    (tmp_path / sid).mkdir(parents=True, exist_ok=True)
    SimulationRunner._save_run_state(
        SimulationRunState(
            simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
        )
    )
    # store.processes 无此 sid → process=None → 走孤儿分支

    SimulationRunner._monitor_simulation(sid)

    got = SimulationRunner._load_run_state(sid)
    assert got.runner_status == RunnerStatus.INTERRUPTED
    assert got.owner_id is None


# ───────────────────────── 运行态持久化往返 ─────────────────────────


def test_run_state_persistence_roundtrip(runner_cleanup):
    sid = _new_sid(runner_cleanup)
    state = SimulationRunState(
        simulation_id=sid,
        runner_status=RunnerStatus.RUNNING,
        current_round=3,
        total_rounds=10,
        process_pid=4242,
        graph_id="graph_abc",
        graph_memory_enabled=True,
    )
    SimulationRunner._save_run_state(state)

    # 清掉进程内缓存，强制走 DB 重建路径
    SimulationRunner._store.run_states.pop(sid, None)
    loaded = SimulationRunner._load_run_state(sid)
    assert loaded is not None
    assert loaded.simulation_id == sid
    assert loaded.runner_status == RunnerStatus.RUNNING
    assert loaded.current_round == 3
    assert loaded.total_rounds == 10
    assert loaded.process_pid == 4242
    assert loaded.graph_id == "graph_abc"
    assert loaded.graph_memory_enabled is True


def test_get_run_state_serves_inmemory_only_when_owner(runner_cleanup):
    """内存缓存仅在本进程确实监控（owner）时可信；非 owner 必须改读 DB 取新鲜快照。

    复现并守护 e2e 暴露的 bug：API 入队后缓存 STARTING，但拉起在 worker；若无脑信任缓存，
    API 会一直返回 STARTING，看不到 worker 写入的 running/completed。
    """
    sid = _new_sid(runner_cleanup)
    state = SimulationRunState(simulation_id=sid, runner_status=RunnerStatus.STOPPED)
    SimulationRunner._save_run_state(state)  # 缓存进 _run_states，但本进程并不监控它

    # 非 owner：不得返回缓存对象，应读 DB 重建（值相等、对象不同）
    got = SimulationRunner.get_run_state(sid)
    assert got is not state
    assert got.runner_status == RunnerStatus.STOPPED

    # owner（有监控线程登记）：信任内存实时对象，原样返回
    SimulationRunner._store.monitor_threads[sid] = object()  # type: ignore[assignment]
    try:
        assert SimulationRunner.get_run_state(sid) is state
    finally:
        SimulationRunner._store.monitor_threads.pop(sid, None)


# ───────────────────────── 监控所有权 CAS ─────────────────────────


def test_ownership_claim_still_release(runner_cleanup):
    sid = _new_sid(runner_cleanup)
    SimulationRunner._save_run_state(
        SimulationRunState(simulation_id=sid, runner_status=RunnerStatus.RUNNING)
    )

    assert SimulationRunner._try_claim_ownership(sid) is True
    assert SimulationRunner._still_owner(sid) is True

    SimulationRunner._release_ownership(sid)
    assert SimulationRunner._still_owner(sid) is False


def test_ownership_blocked_by_live_other_but_takeover_on_expiry(runner_cleanup):
    sid = _new_sid(runner_cleanup)
    SimulationRunner._save_run_state(
        SimulationRunState(simulation_id=sid, runner_status=RunnerStatus.RUNNING)
    )

    data = RunStateRepository.load_raw(sid)
    # 另一实例持有且心跳新鲜 → 不可抢占
    data["owner_id"] = "other-host:123"
    data["owner_heartbeat"] = time.time()
    RunStateRepository.save_raw(sid, data)
    assert SimulationRunner._try_claim_ownership(sid) is False

    # 心跳过期（> OWNER_TTL）→ 可接管
    data["owner_heartbeat"] = time.time() - (SimulationRunner.OWNER_TTL + 60)
    RunStateRepository.save_raw(sid, data)
    assert SimulationRunner._try_claim_ownership(sid) is True
    assert SimulationRunner._still_owner(sid) is True


def test_claim_ownership_missing_row_returns_false(runner_cleanup):
    sid = _new_sid(runner_cleanup)  # 未落库
    assert SimulationRunner._try_claim_ownership(sid) is False


# ───────────────────────── 死进程 → 终态对账 ─────────────────────────


def test_reconcile_state_dead_running_to_interrupted(runner_cleanup, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)
    state = SimulationRunState(
        simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
    )
    SimulationRunner._save_run_state(state)
    SimulationRunner._store.run_states.pop(sid, None)

    reconciled = SimulationRunner._reconcile_state(SimulationRunner._load_run_state(sid))
    # 进程已死、无 simulation_end → INTERRUPTED
    assert reconciled.runner_status == RunnerStatus.INTERRUPTED
    assert reconciled.twitter_running is False
    assert reconciled.reddit_running is False
    assert reconciled.owner_id is None


def test_reconcile_state_dead_with_simulation_end_to_completed(
    runner_cleanup, tmp_path, monkeypatch
):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)
    sim_dir = tmp_path / sid / "reddit"
    sim_dir.mkdir(parents=True)
    (sim_dir / "actions.jsonl").write_text('{"event":"simulation_end"}\n', encoding="utf-8")

    state = SimulationRunState(
        simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
    )
    SimulationRunner._save_run_state(state)
    SimulationRunner._store.run_states.pop(sid, None)

    reconciled = SimulationRunner._reconcile_state(SimulationRunner._load_run_state(sid))
    assert reconciled.runner_status == RunnerStatus.COMPLETED
    assert reconciled.completed_at  # 终结时间已写


def test_reconcile_running_simulations_finalizes_dead(runner_cleanup, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)
    SimulationRunner._save_run_state(
        SimulationRunState(
            simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
        )
    )
    SimulationRunner._store.run_states.pop(sid, None)

    result = SimulationRunner.reconcile_running_simulations()
    assert sid in result["finalized"]
    assert SimulationRunner._load_run_state(sid).runner_status == RunnerStatus.INTERRUPTED


# ───── 提交2：模拟入队 / 计算面拆出 API（_init_run_state + 启动宽限 + 队列注册）─────


def _write_config(tmp_path, sid, *, hours=10, minutes_per_round=30):
    """写一份最小 simulation_config.json，供 _init_run_state 读取轮数。"""
    import json

    sim_dir = tmp_path / sid
    sim_dir.mkdir(parents=True, exist_ok=True)
    (sim_dir / "simulation_config.json").write_text(
        json.dumps(
            {
                "time_config": {
                    "total_simulation_hours": hours,
                    "minutes_per_round": minutes_per_round,
                }
            }
        ),
        encoding="utf-8",
    )
    return sim_dir


def test_init_run_state_creates_starting_without_process(runner_cleanup, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)
    _write_config(tmp_path, sid, hours=10, minutes_per_round=30)

    state = SimulationRunner._init_run_state(sid, platform="reddit")

    # STARTING、无 PID（进程交由 worker 拉起）、平台标记正确、轮数据配置算出
    assert state.runner_status == RunnerStatus.STARTING
    assert state.process_pid is None
    assert state.reddit_running is True
    assert state.twitter_running is False
    assert state.total_rounds == 20  # 10h * 60 / 30min
    # 已持久化，重载可见
    assert SimulationRunner._load_run_state(sid).runner_status == RunnerStatus.STARTING


def test_init_run_state_rejects_when_already_running(runner_cleanup, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)
    _write_config(tmp_path, sid)
    # 伪造一个「运行中」快照（带活 PID = 本进程）
    SimulationRunner._save_run_state(
        SimulationRunState(
            simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=os.getpid()
        )
    )
    with pytest.raises(AppError) as exc_info:
        SimulationRunner._init_run_state(sid, platform="reddit")
    # 状态冲突：当前状态不允许该操作 → 409 Conflict（迁移自原 ValueError/400）
    assert exc_info.value.status == 409


def test_reconcile_starting_no_pid_within_grace_stays_starting(
    runner_cleanup, tmp_path, monkeypatch
):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)
    from datetime import datetime

    # STARTING、无 PID、刚入队（started_at=now）→ 宽限期内不应被判失败
    SimulationRunner._save_run_state(
        SimulationRunState(
            simulation_id=sid,
            runner_status=RunnerStatus.STARTING,
            process_pid=None,
            started_at=datetime.now().isoformat(),
        )
    )
    SimulationRunner._store.run_states.pop(sid, None)
    reconciled = SimulationRunner._reconcile_state(SimulationRunner._load_run_state(sid))
    assert reconciled.runner_status == RunnerStatus.STARTING


def test_reconcile_starting_no_pid_past_grace_fails(runner_cleanup, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "LAUNCH_GRACE", 0.0)  # 立即超期
    sid = _new_sid(runner_cleanup)
    from datetime import datetime

    SimulationRunner._save_run_state(
        SimulationRunState(
            simulation_id=sid,
            runner_status=RunnerStatus.STARTING,
            process_pid=None,
            started_at=datetime.now().isoformat(),
        )
    )
    SimulationRunner._store.run_states.pop(sid, None)
    reconciled = SimulationRunner._reconcile_state(SimulationRunner._load_run_state(sid))
    assert reconciled.runner_status == RunnerStatus.FAILED
    assert reconciled.error


def test_jobqueue_registers_simulation_run():
    """模拟拉起作业已注册到队列分发表，且映射到 worker 协程与同步业务函数。"""
    from app import jobqueue, jobs

    entry = jobqueue._JOBS.get("simulation_run")
    assert entry is not None
    arq_func_name, sync_fn = entry
    assert arq_func_name == "simulation_run_job"
    assert sync_fn is jobs.run_simulation_launch


# ───── 提交3：跨主机存活以 Redis 心跳为准 / 周期对账接管收尾 ─────


def test_reconcile_state_env_alive_keeps_running_despite_dead_local_pid(
    runner_cleanup, tmp_path, monkeypatch
):
    """模拟跑在另一台 worker（本机 PID 探不到）但 Redis 心跳在 → 不得误判为 INTERRUPTED。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "_env_alive", classmethod(lambda cls, sid: True))
    sid = _new_sid(runner_cleanup)
    SimulationRunner._save_run_state(
        SimulationRunState(
            simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
        )
    )
    SimulationRunner._store.run_states.pop(sid, None)

    reconciled = SimulationRunner._reconcile_state(SimulationRunner._load_run_state(sid))
    assert reconciled.runner_status == RunnerStatus.RUNNING  # 心跳在 → 保持运行


def test_reconcile_state_fresh_owner_keeps_running_during_active_rounds(
    runner_cleanup, tmp_path, monkeypatch
):
    """活跃轮次中 Redis 心跳可能因 TTL 短暂缺失，但 owner 监控线程每 2s 刷 owner 心跳；
    非 owner（API）reconcile 应据新鲜 owner 心跳判活，不得误判 INTERRUPTED。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "_env_alive", classmethod(lambda cls, sid: False))
    sid = _new_sid(runner_cleanup)
    state = SimulationRunState(
        simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
    )
    state.owner_id = "worker-host:7"
    state.owner_heartbeat = time.time()  # 监控线程刚刷新
    SimulationRunner._save_run_state(state)
    SimulationRunner._store.run_states.pop(sid, None)

    reconciled = SimulationRunner._reconcile_state(SimulationRunner._load_run_state(sid))
    assert reconciled.runner_status == RunnerStatus.RUNNING


def test_reconcile_running_skips_remote_alive_sim(runner_cleanup, tmp_path, monkeypatch):
    """对账：异机存活模拟（心跳在、本机 PID 不在）既不接管也不终结。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "_env_alive", classmethod(lambda cls, sid: True))
    sid = _new_sid(runner_cleanup)
    SimulationRunner._save_run_state(
        SimulationRunState(
            simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
        )
    )
    SimulationRunner._store.run_states.pop(sid, None)

    result = SimulationRunner.reconcile_running_simulations(reset_detach=False)
    assert sid not in result["finalized"]
    assert sid not in result["adopted"]
    # 状态保持 RUNNING（未被终结）
    assert SimulationRunner._load_run_state(sid).runner_status == RunnerStatus.RUNNING


def test_reconcile_running_finalizes_when_no_heartbeat_no_owner(
    runner_cleanup, tmp_path, monkeypatch
):
    """对账：无心跳、本机 PID 死、无新鲜 owner → 据日志终结（此处无 simulation_end → INTERRUPTED）。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "_env_alive", classmethod(lambda cls, sid: False))
    sid = _new_sid(runner_cleanup)
    SimulationRunner._save_run_state(
        SimulationRunState(
            simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
        )
    )
    SimulationRunner._store.run_states.pop(sid, None)

    result = SimulationRunner.reconcile_running_simulations(reset_detach=False)
    assert sid in result["finalized"]
    assert SimulationRunner._load_run_state(sid).runner_status == RunnerStatus.INTERRUPTED


def test_reconcile_running_skips_when_owner_fresh(runner_cleanup, tmp_path, monkeypatch):
    """对账：无心跳/本机 PID 死，但 owner 心跳新鲜 → 让其 owner 自己终结，不在此争用。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "_env_alive", classmethod(lambda cls, sid: False))
    sid = _new_sid(runner_cleanup)
    state = SimulationRunState(
        simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
    )
    state.owner_id = "other-worker:42"
    state.owner_heartbeat = time.time()  # 新鲜
    SimulationRunner._save_run_state(state)
    SimulationRunner._store.run_states.pop(sid, None)

    result = SimulationRunner.reconcile_running_simulations(reset_detach=False)
    assert sid not in result["finalized"]
    assert SimulationRunner._load_run_state(sid).runner_status == RunnerStatus.RUNNING


def test_owner_fresh_and_periodic_reconcile_does_not_reset_detach(monkeypatch):
    """_owner_fresh 阈值正确；周期对账（reset_detach=False）不复位松手标志。"""
    s_fresh = SimulationRunState(simulation_id="x", owner_id="w:1", owner_heartbeat=time.time())
    s_stale = SimulationRunState(
        simulation_id="x", owner_id="w:1", owner_heartbeat=time.time() - 999
    )
    s_none = SimulationRunState(simulation_id="x")
    assert SimulationRunner._owner_fresh(s_fresh) is True
    assert SimulationRunner._owner_fresh(s_stale) is False
    assert SimulationRunner._owner_fresh(s_none) is False

    # 周期对账不得复位 _detaching（避免打断正在进行的优雅退出）
    monkeypatch.setattr(SimulationRunner, "_env_alive", classmethod(lambda cls, sid: False))
    SimulationRunner._detaching = True
    try:
        SimulationRunner.reconcile_running_simulations(reset_detach=False)
        assert SimulationRunner._detaching is True
    finally:
        SimulationRunner._detaching = False


def test_worker_registers_reconcile_cron():
    """worker 配置含周期对账 cron，且 reconcile 作业映射到 SimulationRunner 对账。"""
    from app import jobs
    from app.worker import WorkerSettings

    assert any(cj.name == "cron:reconcile_job" for cj in WorkerSettings.cron_jobs)
    assert callable(jobs.run_reconcile)


# ════════════════════════════════════════════════════════════════════════════
# 采访子系统（下轮抽 InterviewService 的接缝）
#
# 锁定当前可观察行为为基线：mock 掉 IPC/子进程/Redis/文件系统，断言三类路径：
#   - 模拟不存在 → AppError(404)
#   - 环境未运行（心跳不在）→ AppError(409)
#   - 正常路径的编排顺序（check_env_alive → send_*）与返回结构。
# 错误一律为 AppError，断言 .status。
# ════════════════════════════════════════════════════════════════════════════


class _FakeIPCClient:
    """SimulationIPCClient 的测试替身：记录调用、按脚本返回伪响应。

    通过 monkeypatch 替换 simulation_runner 命名空间中的 SimulationIPCClient，
    从而完全隔离 Redis；不起任何进程、不连任何外部服务。
    """

    instances: list["_FakeIPCClient"] = []

    def __init__(self, sim_dir: str):
        self.sim_dir = sim_dir
        self.alive = True
        self.calls: list[tuple[str, dict]] = []
        # 默认完成态响应；用例可改写
        self.interview_response = SimpleNamespace(
            status=SimpleNamespace(value="completed"),
            result={"answer": "ok"},
            error=None,
            timestamp="2026-06-21T00:00:00",
        )
        self.batch_response = SimpleNamespace(
            status=SimpleNamespace(value="completed"),
            result={"items": []},
            error=None,
            timestamp="2026-06-21T00:00:00",
        )
        _FakeIPCClient.instances.append(self)

    def check_env_alive(self) -> bool:
        self.calls.append(("check_env_alive", {}))
        return self.alive

    def send_interview(self, **kwargs):
        self.calls.append(("send_interview", kwargs))
        return self.interview_response

    def send_batch_interview(self, **kwargs):
        self.calls.append(("send_batch_interview", kwargs))
        return self.batch_response


@pytest.fixture
def fake_ipc(monkeypatch):
    """替换 interview_service 内引用的 SimulationIPCClient 为测试替身（采访已从 runner 抽出）。"""
    _FakeIPCClient.instances.clear()
    monkeypatch.setattr(
        "app.services.simulation.interview_service.SimulationIPCClient", _FakeIPCClient
    )
    return _FakeIPCClient


def _make_sim_dir(tmp_path, monkeypatch, sid: str):
    """在受控 RUN_STATE_DIR 下建一个空的模拟目录，使 os.path.exists(sim_dir) 为真。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sim_dir = tmp_path / sid
    sim_dir.mkdir(parents=True, exist_ok=True)
    return sim_dir


# ───────────────────────── interview_agent ─────────────────────────


def test_interview_agent_missing_simulation_raises_404(tmp_path, monkeypatch, fake_ipc):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    with pytest.raises(AppError) as exc:
        SimulationRunner.interview_agent("sim_does_not_exist", agent_id=1, prompt="hi")
    assert exc.value.status == 404


def test_interview_agent_env_not_running_raises_409(tmp_path, monkeypatch, fake_ipc):
    _make_sim_dir(tmp_path, monkeypatch, "sim_alive_false")
    # 让替身上报「环境未存活」
    monkeypatch.setattr(_FakeIPCClient, "check_env_alive", lambda self: False)
    with pytest.raises(AppError) as exc:
        SimulationRunner.interview_agent("sim_alive_false", agent_id=1, prompt="hi")
    assert exc.value.status == 409


def test_interview_agent_happy_path_orchestration_and_shape(tmp_path, monkeypatch, fake_ipc):
    _make_sim_dir(tmp_path, monkeypatch, "sim_ok")
    result = SimulationRunner.interview_agent(
        "sim_ok", agent_id=7, prompt="问题", platform="reddit", timeout=12.0
    )

    # 返回结构（completed → success=True，回填 agent_id/prompt/result/timestamp）
    assert result == {
        "success": True,
        "agent_id": 7,
        "prompt": "问题",
        "result": {"answer": "ok"},
        "timestamp": "2026-06-21T00:00:00",
    }
    # 编排顺序：先探活，再发采访；且采访参数被透传
    client = fake_ipc.instances[-1]
    assert [name for name, _ in client.calls] == ["check_env_alive", "send_interview"]
    _, kw = client.calls[-1]
    assert kw == {"agent_id": 7, "prompt": "问题", "platform": "reddit", "timeout": 12.0}


def test_interview_agent_failed_response_maps_to_success_false(tmp_path, monkeypatch, fake_ipc):
    _make_sim_dir(tmp_path, monkeypatch, "sim_fail")
    monkeypatch.setattr(
        _FakeIPCClient,
        "send_interview",
        lambda self, **kw: SimpleNamespace(
            status=SimpleNamespace(value="failed"),
            result=None,
            error="boom",
            timestamp="t1",
        ),
    )
    result = SimulationRunner.interview_agent("sim_fail", agent_id=3, prompt="q")
    assert result["success"] is False
    assert result["error"] == "boom"
    assert result["agent_id"] == 3
    assert "result" not in result  # 失败分支不带 result


# ───────────────────────── interview_agents_batch ─────────────────────────


def test_interview_batch_missing_simulation_raises_404(tmp_path, monkeypatch, fake_ipc):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    with pytest.raises(AppError) as exc:
        SimulationRunner.interview_agents_batch("nope", interviews=[{"agent_id": 1, "prompt": "x"}])
    assert exc.value.status == 404


def test_interview_batch_env_not_running_raises_409(tmp_path, monkeypatch, fake_ipc):
    _make_sim_dir(tmp_path, monkeypatch, "sim_b_dead")
    monkeypatch.setattr(_FakeIPCClient, "check_env_alive", lambda self: False)
    with pytest.raises(AppError) as exc:
        SimulationRunner.interview_agents_batch(
            "sim_b_dead", interviews=[{"agent_id": 1, "prompt": "x"}]
        )
    assert exc.value.status == 409


def test_interview_batch_happy_path_shape_and_count(tmp_path, monkeypatch, fake_ipc):
    _make_sim_dir(tmp_path, monkeypatch, "sim_b_ok")
    interviews = [{"agent_id": 1, "prompt": "a"}, {"agent_id": 2, "prompt": "b"}]
    result = SimulationRunner.interview_agents_batch(
        "sim_b_ok", interviews=interviews, platform="twitter", timeout=99.0
    )
    assert result["success"] is True
    assert result["interviews_count"] == 2
    assert result["result"] == {"items": []}
    client = fake_ipc.instances[-1]
    assert [name for name, _ in client.calls] == ["check_env_alive", "send_batch_interview"]
    _, kw = client.calls[-1]
    assert kw == {"interviews": interviews, "platform": "twitter", "timeout": 99.0}


# ───────────────────────── interview_all_agents ─────────────────────────


def test_interview_all_agents_missing_simulation_raises_404(tmp_path, monkeypatch, fake_ipc):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    with pytest.raises(AppError) as exc:
        SimulationRunner.interview_all_agents("nope", prompt="q")
    assert exc.value.status == 404


def test_interview_all_agents_missing_config_raises_404(tmp_path, monkeypatch, fake_ipc):
    _make_sim_dir(tmp_path, monkeypatch, "sim_all_nocfg")
    with pytest.raises(AppError) as exc:
        SimulationRunner.interview_all_agents("sim_all_nocfg", prompt="q")
    assert exc.value.status == 404


def test_interview_all_agents_empty_agent_configs_raises_404(tmp_path, monkeypatch, fake_ipc):
    import json

    sim_dir = _make_sim_dir(tmp_path, monkeypatch, "sim_all_empty")
    (sim_dir / "simulation_config.json").write_text(
        json.dumps({"agent_configs": []}), encoding="utf-8"
    )
    with pytest.raises(AppError) as exc:
        SimulationRunner.interview_all_agents("sim_all_empty", prompt="q")
    assert exc.value.status == 404


def test_interview_all_agents_builds_batch_from_config(tmp_path, monkeypatch, fake_ipc):
    """从配置抽出 agent_id 列表（跳过缺 agent_id 的项）后委托批量采访。"""
    import json

    sim_dir = _make_sim_dir(tmp_path, monkeypatch, "sim_all_ok")
    (sim_dir / "simulation_config.json").write_text(
        json.dumps({"agent_configs": [{"agent_id": 10}, {"agent_id": 11}, {"name": "no_id"}]}),
        encoding="utf-8",
    )
    result = SimulationRunner.interview_all_agents(
        "sim_all_ok", prompt="统一问题", platform="reddit", timeout=200.0
    )
    assert result["success"] is True
    client = fake_ipc.instances[-1]
    _, kw = client.calls[-1]
    # 仅含两个有 agent_id 的项，prompt 统一，platform/timeout 透传
    assert kw["interviews"] == [
        {"agent_id": 10, "prompt": "统一问题"},
        {"agent_id": 11, "prompt": "统一问题"},
    ]
    assert kw["platform"] == "reddit"
    assert kw["timeout"] == 200.0


# ───────────────────────── get_interview_history（编排 + repo 委托）─────────────────────────


def test_get_interview_history_single_platform_queries_only_that_db(tmp_path, monkeypatch):
    """指定 platform 时只查该平台的 sqlite，路径与参数透传正确。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    (tmp_path / "sim_hist").mkdir(parents=True)
    captured: list[dict] = []

    def _fake_list(db_path, platform_name, agent_id, limit):
        captured.append(
            {
                "db_path": db_path,
                "platform_name": platform_name,
                "agent_id": agent_id,
                "limit": limit,
            }
        )
        return [{"agent_id": 1, "timestamp": "t1", "platform": platform_name}]

    monkeypatch.setattr(InterviewTraceRepository, "list_interviews", staticmethod(_fake_list))

    out = SimulationRunner.get_interview_history(
        "sim_hist", platform="reddit", agent_id=5, limit=50
    )
    assert len(captured) == 1
    assert captured[0]["platform_name"] == "reddit"
    assert captured[0]["agent_id"] == 5
    assert captured[0]["limit"] == 50
    assert captured[0]["db_path"].endswith("reddit_simulation.db")
    assert len(out) == 1


def test_get_interview_history_both_platforms_merged_sorted_and_capped(tmp_path, monkeypatch):
    """不指定 platform 时查两平台，按 timestamp 倒序合并并按 limit 截断总数。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    (tmp_path / "sim_merge").mkdir(parents=True)

    def _fake_list(db_path, platform_name, agent_id, limit):
        if platform_name == "twitter":
            return [{"timestamp": "2026-01-01", "platform": "twitter"}]
        return [
            {"timestamp": "2026-03-01", "platform": "reddit"},
            {"timestamp": "2026-02-01", "platform": "reddit"},
        ]

    monkeypatch.setattr(InterviewTraceRepository, "list_interviews", staticmethod(_fake_list))

    out = SimulationRunner.get_interview_history("sim_merge", platform=None, limit=2)
    # 合并 3 条 → 截到 limit=2，且整体按 timestamp 倒序
    assert len(out) == 2
    assert [r["timestamp"] for r in out] == ["2026-03-01", "2026-02-01"]


# ════════════════════════════════════════════════════════════════════════════
# InterviewTraceRepository：每模拟独立 sqlite 的只读访问
# ════════════════════════════════════════════════════════════════════════════


def _make_trace_db(path, rows):
    """建一个含 OASIS `trace` 表的 sqlite 文件并塞入若干行。

    rows: list[(user_id, action, info_json, created_at)]
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE trace (user_id INTEGER, action TEXT, info TEXT, created_at TEXT)"
        )
        conn.executemany(
            "INSERT INTO trace (user_id, action, info, created_at) VALUES (?, ?, ?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()


def test_trace_repo_returns_empty_when_file_missing(tmp_path):
    out = InterviewTraceRepository.list_interviews(
        str(tmp_path / "nope.db"), platform_name="reddit"
    )
    assert out == []


def test_trace_repo_filters_interview_action_and_parses_info(tmp_path):
    import json

    db = tmp_path / "reddit_simulation.db"
    _make_trace_db(
        db,
        [
            (1, "interview", json.dumps({"prompt": "Q1", "response": "A1"}), "2026-01-02"),
            (1, "post", json.dumps({"x": 1}), "2026-01-03"),  # 非 interview → 应被过滤
            (2, "interview", json.dumps({"prompt": "Q2", "response": "A2"}), "2026-01-01"),
        ],
    )
    out = InterviewTraceRepository.list_interviews(str(db), platform_name="reddit")
    # 仅 2 条 interview，按 created_at 倒序
    assert [r["agent_id"] for r in out] == [1, 2]
    assert out[0] == {
        "agent_id": 1,
        "response": "A1",
        "prompt": "Q1",
        "timestamp": "2026-01-02",
        "platform": "reddit",
    }


def test_trace_repo_filters_by_agent_id(tmp_path):
    import json

    db = tmp_path / "reddit_simulation.db"
    _make_trace_db(
        db,
        [
            (1, "interview", json.dumps({"prompt": "Q1", "response": "A1"}), "2026-01-02"),
            (2, "interview", json.dumps({"prompt": "Q2", "response": "A2"}), "2026-01-01"),
        ],
    )
    out = InterviewTraceRepository.list_interviews(str(db), platform_name="reddit", agent_id=2)
    assert len(out) == 1
    assert out[0]["agent_id"] == 2


def test_trace_repo_respects_limit(tmp_path):
    import json

    db = tmp_path / "reddit_simulation.db"
    rows = [
        (i, "interview", json.dumps({"prompt": f"Q{i}", "response": f"A{i}"}), f"2026-01-{i:02d}")
        for i in range(1, 6)
    ]
    _make_trace_db(db, rows)
    out = InterviewTraceRepository.list_interviews(str(db), platform_name="reddit", limit=2)
    assert len(out) == 2


def test_trace_repo_falls_back_on_invalid_info_json(tmp_path):
    """info 非合法 JSON 时不崩，response 回退为整段 info、prompt 为空。"""
    db = tmp_path / "reddit_simulation.db"
    _make_trace_db(db, [(1, "interview", "not-json{", "2026-01-01")])
    out = InterviewTraceRepository.list_interviews(str(db), platform_name="reddit")
    assert len(out) == 1
    # info 解析失败 → info = {"raw": "not-json{"}；response 取整个 info（无 "response" 键）
    assert out[0]["response"] == {"raw": "not-json{"}
    assert out[0]["prompt"] == ""


def test_trace_repo_returns_empty_when_no_trace_table(tmp_path):
    """库存在但无 trace 表（读失败）→ 记录日志并返回已得（空）列表，不抛。"""
    db = tmp_path / "empty.db"
    sqlite3.connect(str(db)).close()  # 建空库，无 trace 表
    out = InterviewTraceRepository.list_interviews(str(db), platform_name="reddit")
    assert out == []


# ════════════════════════════════════════════════════════════════════════════
# 生命周期状态机：stop_simulation 三态
# ════════════════════════════════════════════════════════════════════════════


def test_stop_simulation_missing_raises_404(runner_cleanup, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)  # 未落库
    with pytest.raises(AppError) as exc:
        SimulationRunner.stop_simulation(sid)
    assert exc.value.status == 404


def test_stop_simulation_not_running_raises_409(runner_cleanup, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)
    SimulationRunner._save_run_state(
        SimulationRunState(simulation_id=sid, runner_status=RunnerStatus.COMPLETED)
    )
    SimulationRunner._store.run_states.pop(sid, None)
    with pytest.raises(AppError) as exc:
        SimulationRunner.stop_simulation(sid)
    assert exc.value.status == 409


def test_stop_simulation_running_remote_posts_close_env_and_finalizes(
    runner_cleanup, tmp_path, monkeypatch
):
    """正常停止一个「无本机句柄、本机 PID 不在」的运行：
    走 Redis close_env 投递分支（不杀本机进程），并落终态 STOPPED。
    通过替身隔离 IPC 与 S3 上传，无任何真实 IO。
    """
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    # 隔离 S3 上传（停止流程末尾会调用）
    monkeypatch.setattr(
        SimulationRunner, "_upload_run_artifacts", classmethod(lambda c, s, d: None)
    )

    posted: list[tuple] = []

    class _IPC:
        def __init__(self, sim_dir):
            self.sim_dir = sim_dir

        def post_command(self, cmd_type, args):
            posted.append((cmd_type, args))

    monkeypatch.setattr("app.services.simulation_runner.SimulationIPCClient", _IPC)

    sid = _new_sid(runner_cleanup)
    # 新鲜 owner 心跳 → get_run_state 的 reconcile 视其为存活，保持 RUNNING（不被校正为终态），
    # 从而让 stop_simulation 走真正的停止路径（而非 409）。
    st = SimulationRunState(
        simulation_id=sid, runner_status=RunnerStatus.RUNNING, process_pid=999999
    )
    st.owner_id = "remote-worker:1"
    st.owner_heartbeat = time.time()
    SimulationRunner._save_run_state(st)

    state = SimulationRunner.stop_simulation(sid)

    assert state.runner_status == RunnerStatus.STOPPED
    assert state.twitter_running is False
    assert state.reddit_running is False
    assert state.completed_at
    assert state.owner_id is None
    # 远端停止：经 Redis 投递了一条 close_env 命令
    assert len(posted) == 1


# ════════════════════════════════════════════════════════════════════════════
# 进程拉起：_spawn_process（mock subprocess.Popen，不起真实进程）
# ════════════════════════════════════════════════════════════════════════════


def test_spawn_process_missing_run_state_raises_404(runner_cleanup, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)  # 无运行态
    with pytest.raises(AppError) as exc:
        SimulationRunner._spawn_process(sid, platform="reddit")
    assert exc.value.status == 404


def test_spawn_process_missing_config_raises_404(runner_cleanup, tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)
    (tmp_path / sid).mkdir(parents=True)  # 目录在但无 simulation_config.json
    SimulationRunner._save_run_state(
        SimulationRunState(simulation_id=sid, runner_status=RunnerStatus.STARTING)
    )
    with pytest.raises(AppError) as exc:
        SimulationRunner._spawn_process(sid, platform="reddit")
    assert exc.value.status == 404


def test_spawn_process_missing_script_raises_404(runner_cleanup, tmp_path, monkeypatch):
    """脚本不存在（指向空目录）→ AppError(404)。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(tmp_path / "no_scripts"))
    sid = _new_sid(runner_cleanup)
    _write_config(tmp_path, sid)
    SimulationRunner._save_run_state(
        SimulationRunState(simulation_id=sid, runner_status=RunnerStatus.STARTING)
    )
    with pytest.raises(AppError) as exc:
        SimulationRunner._spawn_process(sid, platform="reddit")
    assert exc.value.status == 404


def test_spawn_process_assembles_command_and_env_and_runs(runner_cleanup, tmp_path, monkeypatch):
    """正常拉起（mock Popen）：装配命令行/env、置 RUNNING、记录 PID、抢占 owner。

    断言不起真实进程的前提下的可观察编排：命令含解释器+脚本+--config，
    可选 --max-rounds 透传；env 带 UTF-8 设置；cwd=sim_dir；状态转 RUNNING。
    """
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    # 避免真起监控线程（其会读文件/落库）；只验证拉起编排
    monkeypatch.setattr(
        SimulationRunner, "_monitor_simulation", classmethod(lambda c, *a, **k: None)
    )
    # PID 起始时间读取在某些平台依赖 ps，固定为常量隔离
    monkeypatch.setattr(
        SimulationRunner, "_read_process_start_time", classmethod(lambda c, pid: 1.0)
    )

    captured = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            self.pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr("app.services.simulation_runner.subprocess.Popen", _FakePopen)

    sid = _new_sid(runner_cleanup)
    _write_config(tmp_path, sid)
    SimulationRunner._save_run_state(
        SimulationRunState(simulation_id=sid, runner_status=RunnerStatus.STARTING)
    )

    try:
        state = SimulationRunner._spawn_process(sid, platform="reddit", max_rounds=5)

        assert state.runner_status == RunnerStatus.RUNNING
        assert state.process_pid == 4321
        assert state.owner_id  # 已抢占监控所有权
        # 命令行装配
        cmd = captured["cmd"]
        assert cmd[1].endswith("run_reddit_simulation.py")
        assert "--config" in cmd
        assert "--max-rounds" in cmd and "5" in cmd
        # 环境变量与工作目录
        kwargs = captured["kwargs"]
        assert kwargs["env"]["PYTHONUTF8"] == "1"
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        assert kwargs["cwd"] == str(tmp_path / sid)
    finally:
        # 清理本用例在内存里登记的句柄，避免污染其它用例
        SimulationRunner._store.processes.pop(sid, None)
        SimulationRunner._store.monitor_threads.pop(sid, None)
        SimulationRunner._store.action_queues.pop(sid, None)
        sf = SimulationRunner._store.stdout_files.pop(sid, None)
        if sf:
            try:
                sf.close()
            except Exception:
                pass
        SimulationRunner._store.stderr_files.pop(sid, None)


def test_spawn_process_graph_memory_requires_graph_id(runner_cleanup, tmp_path, monkeypatch):
    """启用图谱记忆但未给 graph_id → AppError(400)。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = _new_sid(runner_cleanup)
    _write_config(tmp_path, sid)
    SimulationRunner._save_run_state(
        SimulationRunState(simulation_id=sid, runner_status=RunnerStatus.STARTING)
    )
    with pytest.raises(AppError) as exc:
        SimulationRunner._spawn_process(
            sid, platform="reddit", enable_graph_memory_update=True, graph_id=None
        )
    assert exc.value.status == 400


# ════════════════════════════════════════════════════════════════════════════
# 纯工具 / 小编排补漏
# ════════════════════════════════════════════════════════════════════════════


def test_owner_fresh_boundaries():
    """owner 心跳新鲜度边界：刚过 TTL 视为过期。"""
    s_at_ttl = SimulationRunState(
        simulation_id="x",
        owner_id="w:1",
        owner_heartbeat=time.time() - SimulationRunner.OWNER_TTL - 1,
    )
    assert SimulationRunner._owner_fresh(s_at_ttl) is False


def test_within_launch_grace_handles_bad_started_at():
    """started_at 缺失或不可解析时保守返回 True（视为刚入队，不误杀）。"""
    s_none = SimulationRunState(simulation_id="x", started_at=None)
    s_bad = SimulationRunState(simulation_id="x", started_at="not-a-date")
    assert SimulationRunner._within_launch_grace(s_none) is True
    assert SimulationRunner._within_launch_grace(s_bad) is True


def test_check_all_platforms_completed_single_platform(tmp_path, monkeypatch):
    """仅 reddit 启用（仅 reddit 日志存在）且已完成 → all_completed=True。"""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    sid = "sim_platcheck"
    (tmp_path / sid / "reddit").mkdir(parents=True)
    (tmp_path / sid / "reddit" / "actions.jsonl").write_text("{}\n", encoding="utf-8")
    state = SimulationRunState(simulation_id=sid)
    state.reddit_completed = True
    assert SimulationRunner._check_all_platforms_completed(state) is True
    # reddit 未完成 → False
    state.reddit_completed = False
    assert SimulationRunner._check_all_platforms_completed(state) is False
