"""模拟仓储：simulations 表的全部数据访问（session_scope + 行<->领域映射）。

只负责 Postgres 读写并收发 ``SimulationState``；profiles/config 等文件产物与运行编排
留在 ``SimulationManager`` 服务层。
"""

from __future__ import annotations

from datetime import datetime

from ..core.db import session_scope
from ..db_models import SimulationRow
from ..domain.simulation import SimulationState, SimulationStatus


def _row_to_state(row: SimulationRow) -> SimulationState:
    return SimulationState(
        simulation_id=row.simulation_id,
        project_id=row.project_id,
        user_id=row.user_id or "",
        graph_id=row.graph_id,
        enable_twitter=row.enable_twitter,
        enable_reddit=row.enable_reddit,
        status=SimulationStatus(row.status),
        entities_count=row.entities_count,
        profiles_count=row.profiles_count,
        entity_types=row.entity_types or [],
        config_generated=row.config_generated,
        config_reasoning=row.config_reasoning,
        simulation_requirement=row.simulation_requirement or "",
        total_simulation_hours=row.total_simulation_hours or 0,
        minutes_per_round=row.minutes_per_round or 0,
        current_round=row.current_round,
        twitter_status=row.twitter_status,
        reddit_status=row.reddit_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        error=row.error,
    )


def _apply_state_to_row(state: SimulationState, row: SimulationRow) -> None:
    row.project_id = state.project_id
    row.user_id = state.user_id
    row.graph_id = state.graph_id
    row.enable_twitter = state.enable_twitter
    row.enable_reddit = state.enable_reddit
    row.status = state.status.value if isinstance(state.status, SimulationStatus) else state.status
    row.entities_count = state.entities_count
    row.profiles_count = state.profiles_count
    row.entity_types = state.entity_types
    row.config_generated = state.config_generated
    row.config_reasoning = state.config_reasoning
    row.simulation_requirement = state.simulation_requirement
    row.total_simulation_hours = state.total_simulation_hours
    row.minutes_per_round = state.minutes_per_round
    row.current_round = state.current_round
    row.twitter_status = state.twitter_status
    row.reddit_status = state.reddit_status
    row.created_at = state.created_at
    row.updated_at = state.updated_at
    row.error = state.error


class SimulationRepository:
    """simulations 表数据访问。"""

    @staticmethod
    def save(state: SimulationState) -> None:
        """保存模拟状态（upsert）。写入前刷新 updated_at。"""
        state.updated_at = datetime.now().isoformat()
        with session_scope() as session:
            row = session.get(SimulationRow, state.simulation_id)
            if row is None:
                row = SimulationRow(simulation_id=state.simulation_id)
                _apply_state_to_row(state, row)
                session.add(row)
            else:
                _apply_state_to_row(state, row)

    @staticmethod
    def get(simulation_id: str) -> SimulationState | None:
        with session_scope() as session:
            row = session.get(SimulationRow, simulation_id)
            return _row_to_state(row) if row else None

    @staticmethod
    def list(project_id: str | None = None, user_id: str | None = None) -> list[SimulationState]:
        """按创建时间倒序；可按 user_id / project_id 过滤。"""
        with session_scope() as session:
            query = session.query(SimulationRow)
            if user_id is not None:
                query = query.filter(SimulationRow.user_id == user_id)
            if project_id is not None:
                query = query.filter(SimulationRow.project_id == project_id)
            rows = query.order_by(SimulationRow.created_at.desc()).all()
            return [_row_to_state(r) for r in rows]
