"""Neo4j graph utilities.

The module name is kept for compatibility with existing imports. The
implementation is now a lightweight Neo4j property-graph layer used by the
schema-constrained graph builder.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from neo4j import GraphDatabase

from .logger import get_logger

logger = get_logger("superfish.graph_utils")

_DEFAULT_MAX_NODES = 2000
_neo4j_client = None
_neo4j_client_lock = threading.Lock()


def run_async(coro) -> Any:
    """Compatibility wrapper for older call sites that still pass coroutines."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result = None
    error = None

    def _runner():
        nonlocal result, error
        try:
            result = asyncio.run(coro)
        except Exception as exc:
            error = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error
    return result


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _json_loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _safe_label(label: str) -> str:
    cleaned = "".join(ch for ch in (label or "") if ch.isalnum() or ch == "_")
    return cleaned or "Entity"


def _search_terms(query: str) -> list[str]:
    query = (query or "").lower()
    terms = [
        part
        for part in re.split(r"[\s,，。；;：:、/\\|（）()《》<>\"'“”‘’！？!?]+", query)
        if len(part) > 1
    ]
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]+", query)
    for chunk in chinese_chunks:
        for size in (2, 3, 4):
            terms.extend(chunk[idx : idx + size] for idx in range(0, max(len(chunk) - size + 1, 0)))
    terms.extend(re.findall(r"[a-zA-Z0-9_]{2,}", query))
    seen = set()
    return [term for term in terms if not (term in seen or seen.add(term))]


def _score_text(query: str, terms: list[str], text: str) -> int:
    if not text:
        return 0
    haystack = text.lower()
    score = 100 if query and query in haystack else 0
    for term in terms:
        if term in haystack:
            score += 10 + min(len(term), 8)
    return score


class Neo4jGraphClient:
    """Small synchronous Neo4j client with the subset used by SuperFish."""

    def __init__(self):
        from ..config import Config

        self.driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
        )

    def close(self):
        self.driver.close()

    async def search(
        self,
        query: str,
        group_ids: list[str] | None = None,
        num_results: int = 10,
        **_: Any,
    ) -> list[Any]:
        group_ids = group_ids or []
        query_lower = (query or "").lower()
        terms = _search_terms(query)
        if not terms and query_lower:
            terms = [query_lower]

        with self.driver.session() as session:
            records = list(
                session.run(
                    """
                MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity)
                WHERE size($group_ids) = 0 OR r.group_id IN $group_ids
                RETURN r.uuid AS uuid,
                       r.name AS name,
                       r.fact AS fact,
                       r.group_id AS group_id,
                       s.uuid AS source_node_uuid,
                       s.name AS source_node_name,
                       s.summary AS source_summary,
                       t.uuid AS target_node_uuid,
                       t.name AS target_node_name,
                       t.summary AS target_summary
                """,
                    {"group_ids": group_ids},
                )
            )

        scored = []
        for record in records:
            searchable = " ".join(
                str(record.get(key) or "")
                for key in (
                    "name",
                    "fact",
                    "source_node_name",
                    "source_summary",
                    "target_node_name",
                    "target_summary",
                )
            )
            score = _score_text(query_lower, terms, searchable)
            if score <= 0:
                continue
            scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            SimpleNamespace(
                uuid=record.get("uuid") or "",
                name=record.get("name") or "",
                fact=record.get("fact") or "",
                group_id=record.get("group_id") or "",
                source_node_uuid=record.get("source_node_uuid") or "",
                target_node_uuid=record.get("target_node_uuid") or "",
                source_node_name=record.get("source_node_name") or "",
                target_node_name=record.get("target_node_name") or "",
            )
            for _, record in scored[:num_results]
        ]

    def build_indices_and_constraints(self):
        with self.driver.session() as session:
            session.run(
                "CREATE CONSTRAINT entity_uuid IF NOT EXISTS FOR (n:Entity) REQUIRE n.uuid IS UNIQUE"
            )
            session.run("CREATE INDEX entity_group IF NOT EXISTS FOR (n:Entity) ON (n.group_id)")
            session.run("CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)")
            session.run(
                "CREATE INDEX relates_group IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.group_id)"
            )

    def write_graph(
        self,
        graph_id: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.driver.session() as session:
            for node in nodes:
                labels = [
                    label
                    for label in node.get("labels", [])
                    if label and label not in ("Entity", "Node")
                ]
                node_type = labels[0] if labels else node.get("type", "Entity")
                node_label = _safe_label(node_type)
                session.run(
                    f"""
                    MERGE (n:Entity:`{node_label}` {{uuid: $uuid}})
                    SET n.name = $name,
                        n.summary = $summary,
                        n.group_id = $group_id,
                        n.attributes_json = $attributes_json,
                        n.created_at = coalesce(n.created_at, $created_at)
                    """,
                    {
                        "uuid": node["uuid"],
                        "name": node.get("name", ""),
                        "summary": node.get("summary", ""),
                        "group_id": graph_id,
                        "attributes_json": _json_dumps(node.get("attributes", {})),
                        "created_at": now,
                    },
                )

            for edge in edges:
                session.run(
                    """
                    MATCH (s:Entity {uuid: $source_uuid}), (t:Entity {uuid: $target_uuid})
                    MERGE (s)-[r:RELATES_TO {uuid: $uuid}]->(t)
                    SET r.name = $name,
                        r.fact = $fact,
                        r.group_id = $group_id,
                        r.attributes_json = $attributes_json,
                        r.created_at = coalesce(r.created_at, $created_at)
                    """,
                    {
                        "uuid": edge["uuid"],
                        "source_uuid": edge["source_node_uuid"],
                        "target_uuid": edge["target_node_uuid"],
                        "name": edge.get("name", ""),
                        "fact": edge.get("fact", ""),
                        "group_id": graph_id,
                        "attributes_json": _json_dumps(edge.get("attributes", {})),
                        "created_at": now,
                    },
                )


def get_neo4j_graph_client() -> Neo4jGraphClient:
    """Return the shared Neo4j graph client."""
    global _neo4j_client
    if _neo4j_client is None:
        with _neo4j_client_lock:
            if _neo4j_client is None:
                _neo4j_client = Neo4jGraphClient()
                _neo4j_client.build_indices_and_constraints()
                logger.info("Neo4j graph client initialized")
    return _neo4j_client


get_neo4j_client = get_neo4j_graph_client


def fetch_all_nodes(
    client: Neo4jGraphClient | None,
    group_id: str,
    max_items: int = _DEFAULT_MAX_NODES,
) -> list[dict[str, Any]]:
    client = client or get_neo4j_graph_client()
    with client.driver.session() as session:
        result = session.run(
            """
            MATCH (n:Entity)
            WHERE n.group_id = $group_id
            RETURN n.uuid AS uuid,
                   n.name AS name,
                   n.summary AS summary,
                   labels(n) AS labels,
                   n.attributes_json AS attributes_json
            LIMIT $limit
            """,
            {"group_id": group_id, "limit": max_items},
        )
        nodes = [
            {
                "uuid": record.get("uuid") or "",
                "name": record.get("name") or "",
                "summary": record.get("summary") or "",
                "labels": list(record.get("labels") or []),
                "attributes": _json_loads(record.get("attributes_json")),
            }
            for record in result
        ]
    if len(nodes) >= max_items:
        logger.warning(f"节点数达到上限 {max_items}，graph={group_id}，可能存在截断")
    return nodes


def fetch_all_edges(
    client: Neo4jGraphClient | None,
    group_id: str,
) -> list[dict[str, Any]]:
    client = client or get_neo4j_graph_client()
    with client.driver.session() as session:
        result = session.run(
            """
            MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity)
            WHERE r.group_id = $group_id
            RETURN r.uuid AS uuid,
                   r.name AS name,
                   r.fact AS fact,
                   s.uuid AS source_node_uuid,
                   t.uuid AS target_node_uuid,
                   r.created_at AS created_at,
                   r.valid_at AS valid_at,
                   r.invalid_at AS invalid_at,
                   r.expired_at AS expired_at,
                   r.attributes_json AS attributes_json,
                   s.name AS source_node_name,
                   t.name AS target_node_name
            """,
            {"group_id": group_id},
        )
        return [
            {
                "uuid": record.get("uuid") or "",
                "name": record.get("name") or "",
                "fact": record.get("fact") or "",
                "source_node_uuid": record.get("source_node_uuid") or "",
                "target_node_uuid": record.get("target_node_uuid") or "",
                "source_node_name": record.get("source_node_name") or "",
                "target_node_name": record.get("target_node_name") or "",
                "created_at": record.get("created_at"),
                "valid_at": record.get("valid_at"),
                "invalid_at": record.get("invalid_at"),
                "expired_at": record.get("expired_at"),
                "attributes": _json_loads(record.get("attributes_json")),
            }
            for record in result
        ]


def delete_group(client: Neo4jGraphClient | None, group_id: str) -> None:
    client = client or get_neo4j_graph_client()
    with client.driver.session() as session:
        session.run(
            "MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity) WHERE r.group_id = $gid DELETE r",
            {"gid": group_id},
        )
        session.run("MATCH (n:Entity) WHERE n.group_id = $gid DETACH DELETE n", {"gid": group_id})
    logger.info(f"已删除图谱数据: group_id={group_id}")
