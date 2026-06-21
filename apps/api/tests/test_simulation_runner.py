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
import time
import uuid

import pytest

from app.core.errors import AppError
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
        SimulationRunner._run_states.pop(sid, None)
        SimulationRunner._graph_memory_enabled.pop(sid, None)


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
    SimulationRunner._run_states.pop(sid, None)
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
    SimulationRunner._monitor_threads[sid] = object()  # type: ignore[assignment]
    try:
        assert SimulationRunner.get_run_state(sid) is state
    finally:
        SimulationRunner._monitor_threads.pop(sid, None)


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
    SimulationRunner._run_states.pop(sid, None)

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
    SimulationRunner._run_states.pop(sid, None)

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
    SimulationRunner._run_states.pop(sid, None)

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
    SimulationRunner._run_states.pop(sid, None)
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
    SimulationRunner._run_states.pop(sid, None)
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
    SimulationRunner._run_states.pop(sid, None)

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
    SimulationRunner._run_states.pop(sid, None)

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
    SimulationRunner._run_states.pop(sid, None)

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
    SimulationRunner._run_states.pop(sid, None)

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
    SimulationRunner._run_states.pop(sid, None)

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
