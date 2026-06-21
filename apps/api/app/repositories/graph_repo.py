"""知识图谱仓储：graphs 表（整张图以 JSONB 存放）的数据访问。

图谱存储后端（Postgres）。访问模式为「按 graph_id 取整张图」，故只需简单 KV 式读写。
"""

from __future__ import annotations

from datetime import datetime

from ..core.db import session_scope
from ..db_models import GraphRow


class GraphRepository:
    """graphs 表读写（nodes/edges 全量替换 upsert）。"""

    @staticmethod
    def save(graph_id: str, nodes: list[dict], edges: list[dict], user_id: str = "") -> None:
        """整张图全量 upsert（替换 nodes/edges）。user_id 为空时不覆盖既有归属。"""
        now = datetime.now().isoformat()
        with session_scope() as session:
            row = session.get(GraphRow, graph_id)
            if row is None:
                row = GraphRow(
                    graph_id=graph_id,
                    user_id=user_id,
                    nodes=nodes,
                    edges=edges,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.nodes = nodes
                row.edges = edges
                if user_id:
                    row.user_id = user_id
                row.updated_at = now

    @staticmethod
    def load(graph_id: str) -> tuple[list[dict], list[dict]]:
        """读取整张图，返回 (nodes, edges)；不存在返回 ([], [])。"""
        with session_scope() as session:
            row = session.get(GraphRow, graph_id)
            if row is None:
                return [], []
            return list(row.nodes or []), list(row.edges or [])

    @staticmethod
    def delete(graph_id: str) -> None:
        with session_scope() as session:
            row = session.get(GraphRow, graph_id)
            if row is not None:
                session.delete(row)

    @staticmethod
    def exists(graph_id: str) -> bool:
        with session_scope() as session:
            return session.get(GraphRow, graph_id) is not None
