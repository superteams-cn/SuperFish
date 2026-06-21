"""图谱存储工具（模块名沿用 graph_store 以兼容既有导入）。

后端为 Postgres JSONB（见 repositories/graph_repo.py）：图谱访问全是
「取整张图 + 应用层朴素打分」，无多跳遍历，且单图极小（百级节点），故 KV 式 JSONB 存储
足矣，并没有独立图数据库的在线单点。公开的类/函数名保持不变，调用方无需改动。
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from types import SimpleNamespace
from typing import Any

from ..core.logger import get_logger

logger = get_logger("superfish.graph_utils")

_DEFAULT_MAX_NODES = 2000
_graph_client = None
_graph_client_lock = threading.Lock()


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
    chinese_chunks = re.findall(r"[一-鿿]+", query)
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


class GraphStore:
    """图谱存储客户端（历史名保留以兼容导入）。后端为 Postgres JSONB（GraphRepository）。

    仅承载实际被使用的子集：写整张图（write_graph）、应用层搜索（search）。
    历史的 read/write 裸 Cypher 接口已移除——其调用方改用 fetch_node_edges/fetch_node 等。
    """

    def __init__(self, uri: str | None = None):
        # 后端为 Postgres，无需驱动连接；uri 仅为兼容旧签名而保留。
        pass

    def close(self):  # 兼容旧调用，无操作
        pass

    def build_indices_and_constraints(self):  # 表/索引由建表负责，无操作
        pass

    async def search(
        self,
        query: str,
        group_ids: list[str] | None = None,
        num_results: int = 10,
        **_: Any,
    ) -> list[Any]:
        """在指定图谱内按朴素文本打分检索关系（不跨租户全表扫；group_ids 为空直接返回）。"""
        from ..repositories.graph_repo import GraphRepository

        group_ids = [g for g in (group_ids or []) if g]
        if not group_ids:
            return []
        query_lower = (query or "").lower()
        terms = _search_terms(query) or ([query_lower] if query_lower else [])

        scored: list[tuple[int, dict, dict, dict, str]] = []
        for gid in group_ids:
            nodes, edges = GraphRepository.load(gid)
            nmap = {n.get("uuid"): n for n in nodes}
            for r in edges:
                s = nmap.get(r.get("source_node_uuid"), {})
                t = nmap.get(r.get("target_node_uuid"), {})
                searchable = " ".join(
                    str(x or "")
                    for x in (
                        r.get("name"),
                        r.get("fact"),
                        s.get("name"),
                        s.get("summary"),
                        t.get("name"),
                        t.get("summary"),
                    )
                )
                score = _score_text(query_lower, terms, searchable)
                if score > 0:
                    scored.append((score, r, s, t, gid))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            SimpleNamespace(
                uuid=r.get("uuid") or "",
                name=r.get("name") or "",
                fact=r.get("fact") or "",
                group_id=gid,
                source_node_uuid=r.get("source_node_uuid") or "",
                target_node_uuid=r.get("target_node_uuid") or "",
                source_node_name=s.get("name") or "",
                target_node_name=t.get("name") or "",
            )
            for _, r, s, t, gid in scored[:num_results]
        ]

    def write_graph(
        self,
        graph_id: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        user_id: str = "",
    ) -> None:
        """整张图全量写入（替换语义，与建图流式累积写一致）。

        规范化为读取期一致的形状，并在写入时富集边的 source/target 名（读取期无需再 join）。
        """
        from ..repositories.graph_repo import GraphRepository

        name_map: dict[str, str] = {}
        norm_nodes: list[dict[str, Any]] = []
        for node in nodes:
            labels = [
                label
                for label in node.get("labels", [])
                if label and label not in ("Entity", "Node")
            ]
            node_type = labels[0] if labels else node.get("type", "Entity")
            uuid = node["uuid"]
            name = node.get("name", "")
            name_map[uuid] = name
            norm_nodes.append(
                {
                    "uuid": uuid,
                    "name": name,
                    "summary": node.get("summary", ""),
                    "labels": ["Entity", _safe_label(node_type)],
                    "attributes": node.get("attributes", {}) or {},
                }
            )

        norm_edges: list[dict[str, Any]] = []
        for edge in edges:
            su = edge.get("source_node_uuid", "")
            tu = edge.get("target_node_uuid", "")
            norm_edges.append(
                {
                    "uuid": edge["uuid"],
                    "name": edge.get("name", ""),
                    "fact": edge.get("fact", ""),
                    "source_node_uuid": su,
                    "target_node_uuid": tu,
                    "source_node_name": name_map.get(su, ""),
                    "target_node_name": name_map.get(tu, ""),
                    "attributes": edge.get("attributes", {}) or {},
                }
            )

        GraphRepository.save(graph_id, norm_nodes, norm_edges, user_id=user_id)


def get_graph_store(routing_key: str | None = None) -> GraphStore:
    """返回图谱存储客户端（进程内单例）。routing_key 仅为兼容签名而保留，无实际作用。"""
    global _graph_client
    if _graph_client is None:
        with _graph_client_lock:
            if _graph_client is None:
                _graph_client = GraphStore()
                logger.info("图谱存储客户端已初始化（Postgres 后端）")
    return _graph_client


get_graph_store = get_graph_store


def fetch_all_nodes(
    client: GraphStore | None,
    group_id: str,
    max_items: int = _DEFAULT_MAX_NODES,
) -> list[dict[str, Any]]:
    """取整张图的节点（已是读取期形状）。"""
    from ..repositories.graph_repo import GraphRepository

    nodes, _ = GraphRepository.load(group_id)
    return nodes[:max_items]


def fetch_all_edges(
    client: GraphStore | None,
    group_id: str,
) -> list[dict[str, Any]]:
    """取整张图的边（已富集 source/target 名）。"""
    from ..repositories.graph_repo import GraphRepository

    _, edges = GraphRepository.load(group_id)
    return edges


def fetch_node_edges(group_id: str, node_uuid: str) -> list[dict[str, Any]]:
    """取某节点相关的边（源或目标为该节点）。"""
    from ..repositories.graph_repo import GraphRepository

    _, edges = GraphRepository.load(group_id)
    return [
        e
        for e in edges
        if e.get("source_node_uuid") == node_uuid or e.get("target_node_uuid") == node_uuid
    ]


def fetch_node(group_id: str, node_uuid: str) -> dict[str, Any] | None:
    """取某节点（按 uuid）。"""
    from ..repositories.graph_repo import GraphRepository

    nodes, _ = GraphRepository.load(group_id)
    return next((n for n in nodes if n.get("uuid") == node_uuid), None)


def delete_group(client: GraphStore | None, group_id: str) -> None:
    """删除整张图。"""
    from ..repositories.graph_repo import GraphRepository

    GraphRepository.delete(group_id)
    logger.info(f"已删除图谱数据: group_id={group_id}")
