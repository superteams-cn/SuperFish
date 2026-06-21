"""一次性迁移：把既有 Neo4j 图谱数据回灌到 Postgres（graphs 表）。

图谱存储后端从 Neo4j 切换为 Postgres JSONB 后，用本脚本把历史图谱搬过去。
直接连 Neo4j 读取每个 group_id 的节点/边，按 build 输入形状交给 GraphRepository 落库。

用法（需能同时访问 Neo4j 与 Postgres）：
    uv run python scripts/backfill_graphs_to_postgres.py
迁移完成后即可下线 Neo4j。
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from neo4j import GraphDatabase  # noqa: E402

from app.core.db import init_db  # noqa: E402
from app.repositories.graph_repo import GraphRepository  # noqa: E402


def main() -> None:
    init_db()  # 确保 graphs 表存在
    # 旧 Neo4j 连接仅迁移用，从环境变量读取（运行时配置已无此项）
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "neo4j")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    migrated = 0
    with driver.session() as session:
        group_ids = [
            r["gid"]
            for r in session.run(
                "MATCH (n:Entity) WHERE n.group_id IS NOT NULL "
                "RETURN DISTINCT n.group_id AS gid"
            )
        ]
        print(f"发现 {len(group_ids)} 个图谱待迁移")

        for gid in group_ids:
            nodes = [
                {
                    "uuid": r["uuid"],
                    "name": r["name"] or "",
                    "summary": r["summary"] or "",
                    "labels": list(r["labels"] or []),
                    "attributes": _loads(r["attrs"]),
                }
                for r in session.run(
                    "MATCH (n:Entity) WHERE n.group_id = $gid "
                    "RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary, "
                    "labels(n) AS labels, n.attributes_json AS attrs",
                    {"gid": gid},
                )
            ]
            edges = [
                {
                    "uuid": r["uuid"],
                    "name": r["name"] or "",
                    "fact": r["fact"] or "",
                    "source_node_uuid": r["su"] or "",
                    "target_node_uuid": r["tu"] or "",
                    "attributes": _loads(r["attrs"]),
                }
                for r in session.run(
                    "MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity) WHERE r.group_id = $gid "
                    "RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, "
                    "s.uuid AS su, t.uuid AS tu, r.attributes_json AS attrs",
                    {"gid": gid},
                )
            ]
            # 复用 write_graph 的规范化（富集边名等）
            from app.utils.graph_store import GraphStore

            GraphStore().write_graph(gid, nodes, edges)
            migrated += 1
            print(f"  ✓ {gid}: {len(nodes)} 节点 / {len(edges)} 边")

    driver.close()
    print(f"完成：已迁移 {migrated} 个图谱到 Postgres")
    _ = GraphRepository  # 保活导入（落库经 write_graph→GraphRepository）


def _loads(value):
    import json

    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        out = json.loads(value)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


if __name__ == "__main__":
    main()
