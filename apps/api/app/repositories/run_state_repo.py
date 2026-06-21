"""运行态仓储：simulation_run_states 表的全部数据访问（session_scope）。

收编 SimulationRunner 中所有触碰该表的 DB 代码：常规读写（load/save/bulk/all/delete）
以及监控所有权的 CAS（``with_for_update`` 行锁 + 实例/TTL 判定）。
实例标识与 TTL 策略由调用方（SimulationRunner）传入，本层只负责原子读改写。
"""

from __future__ import annotations

import time
from datetime import datetime

from ..core.db import session_scope
from ..db_models import SimulationRunStateRow


class RunStateRepository:
    """simulation_run_states 表的常规读写（收发持久化 data dict）。"""

    @staticmethod
    def load_raw(simulation_id: str) -> dict | None:
        """读取单个运行态快照的 data dict；不存在返回 None。"""
        with session_scope() as session:
            row = session.get(SimulationRunStateRow, simulation_id)
            return dict(row.data) if row and row.data else None

    @staticmethod
    def load_raw_bulk(simulation_ids: list[str]) -> dict[str, dict]:
        """批量读取多个运行态快照（单次查询），返回 {simulation_id: data}。"""
        if not simulation_ids:
            return {}
        with session_scope() as session:
            rows = (
                session.query(SimulationRunStateRow)
                .filter(SimulationRunStateRow.simulation_id.in_(simulation_ids))
                .all()
            )
            return {r.simulation_id: dict(r.data) for r in rows if r.data}

    @staticmethod
    def load_all_raw() -> dict[str, dict]:
        """读取全部运行态快照，返回 {simulation_id: data}（用于对账/退出收集）。"""
        with session_scope() as session:
            rows = session.query(SimulationRunStateRow).all()
            return {r.simulation_id: dict(r.data) for r in rows if r.data}

    @staticmethod
    def save_raw(simulation_id: str, data: dict) -> None:
        """保存运行态快照 data dict（upsert）。"""
        with session_scope() as session:
            row = session.get(SimulationRunStateRow, simulation_id)
            if row is None:
                row = SimulationRunStateRow(simulation_id=simulation_id)
                session.add(row)
            row.data = data
            row.updated_at = datetime.now().isoformat()

    @staticmethod
    def delete(simulation_id: str) -> None:
        """删除运行态快照（不存在则忽略）。"""
        with session_scope() as session:
            row = session.get(SimulationRunStateRow, simulation_id)
            if row is not None:
                session.delete(row)

    # ───────────────────────── 监控所有权 CAS（行锁原子读改写）─────────────────────────

    @staticmethod
    def try_claim_owner(simulation_id: str, inst_id: str, ttl: float) -> bool:
        """原子抢占监控所有权（行锁 CAS）。无 owner / owner 是自己 / 心跳超 ttl 时可抢占。"""
        now = time.time()
        with session_scope() as session:
            row = session.get(SimulationRunStateRow, simulation_id, with_for_update=True)
            if row is None:
                return False
            data = dict(row.data)
            owner = data.get("owner_id")
            hb = data.get("owner_heartbeat") or 0
            if owner and owner != inst_id and (now - hb) < ttl:
                return False
            data["owner_id"] = inst_id
            data["owner_heartbeat"] = now
            row.data = data
            return True

    @staticmethod
    def is_owner(simulation_id: str, inst_id: str) -> bool:
        """确认 inst_id 是否为当前 owner。"""
        with session_scope() as session:
            row = session.get(SimulationRunStateRow, simulation_id)
            return row is not None and (row.data or {}).get("owner_id") == inst_id

    @staticmethod
    def release_owner(simulation_id: str, inst_id: str) -> None:
        """释放所有权（仅当 owner 是 inst_id 时清空）。"""
        with session_scope() as session:
            row = session.get(SimulationRunStateRow, simulation_id, with_for_update=True)
            if row and (row.data or {}).get("owner_id") == inst_id:
                data = dict(row.data)
                data["owner_id"] = None
                data["owner_heartbeat"] = None
                row.data = data
