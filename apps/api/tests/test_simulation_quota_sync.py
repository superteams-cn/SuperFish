"""SimulationManager.sync_terminal_status 单元测试（不触 DB）。

守护「配额泄漏」修复的核心：监控线程/对账器把运行态判成终态时，须把 sim 级
SimulationStatus 一并同步到终态，否则异常结束的模拟会永远停留 RUNNING 而占满并发配额。

通过 monkeypatch 掉 _load/_save_simulation_state，聚焦纯映射与「仅从活跃态降级」的守卫，
无需 Postgres。
"""

from types import SimpleNamespace

import pytest

from app.domain.run_state import RunnerStatus
from app.services.simulation_manager import SimulationManager, SimulationStatus


def _mgr_with(state, saved: list):
    """构造一个 _load 固定返回 state、_save 记录入参的 manager。"""
    mgr = SimulationManager()
    mgr._load_simulation_state = lambda sid: state  # type: ignore[method-assign]
    mgr._save_simulation_state = lambda s: saved.append(s.status)  # type: ignore[method-assign]
    return mgr


@pytest.mark.parametrize(
    "runner_status,expected",
    [
        (RunnerStatus.COMPLETED, SimulationStatus.COMPLETED),
        (RunnerStatus.FAILED, SimulationStatus.FAILED),
        (RunnerStatus.INTERRUPTED, SimulationStatus.STOPPED),
        (RunnerStatus.STOPPED, SimulationStatus.STOPPED),
    ],
)
def test_running_synced_to_terminal(runner_status, expected):
    state = SimpleNamespace(status=SimulationStatus.RUNNING)
    saved: list = []
    _mgr_with(state, saved).sync_terminal_status("sim_x", runner_status)
    assert state.status == expected
    assert saved == [expected]


def test_preparing_also_demoted():
    # 启动超时（STARTING→FAILED）时 sim 级可能仍在 PREPARING，应允许降级。
    state = SimpleNamespace(status=SimulationStatus.PREPARING)
    saved: list = []
    _mgr_with(state, saved).sync_terminal_status("sim_x", RunnerStatus.FAILED)
    assert state.status == SimulationStatus.FAILED
    assert saved == [SimulationStatus.FAILED]


def test_paused_not_overridden():
    # PAUSED 是用户显式态，不在「活跃可降级」之列，须保持不动。
    state = SimpleNamespace(status=SimulationStatus.PAUSED)
    saved: list = []
    _mgr_with(state, saved).sync_terminal_status("sim_x", RunnerStatus.INTERRUPTED)
    assert state.status == SimulationStatus.PAUSED
    assert saved == []


def test_already_terminal_is_noop():
    # 已是终态：幂等，不重复落库（COMPLETED 不应被 INTERRUPTED 覆盖成 STOPPED）。
    state = SimpleNamespace(status=SimulationStatus.COMPLETED)
    saved: list = []
    _mgr_with(state, saved).sync_terminal_status("sim_x", RunnerStatus.INTERRUPTED)
    assert state.status == SimulationStatus.COMPLETED
    assert saved == []


def test_non_terminal_runner_status_ignored():
    # RUNNING/STARTING 等非终态不触发任何同步。
    state = SimpleNamespace(status=SimulationStatus.RUNNING)
    saved: list = []
    _mgr_with(state, saved).sync_terminal_status("sim_x", RunnerStatus.RUNNING)
    assert state.status == SimulationStatus.RUNNING
    assert saved == []


def test_missing_state_is_safe():
    mgr = SimulationManager()
    mgr._load_simulation_state = lambda sid: None  # type: ignore[method-assign]
    # 不抛即可（无可同步对象）。
    mgr.sync_terminal_status("sim_x", RunnerStatus.COMPLETED)
