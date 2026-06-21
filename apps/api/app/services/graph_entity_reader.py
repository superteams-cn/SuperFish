"""
图谱实体读取与过滤服务
从 图谱中读取节点，筛选出符合预定义实体类型的节点
"""

import json
from dataclasses import dataclass, field
from typing import Any

from ..core.logger import get_logger
from ..utils.graph_store import (
    fetch_all_edges,
    fetch_all_nodes,
    fetch_node,
    fetch_node_edges,
    get_graph_store,
)

logger = get_logger("superfish.graph_entity_reader")


def _parse_attrs(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


@dataclass
class EntityNode:
    """实体节点数据结构"""

    uuid: str
    name: str
    labels: list[str]
    summary: str
    attributes: dict[str, Any]
    related_edges: list[dict[str, Any]] = field(default_factory=list)
    related_nodes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> str | None:
        for label in self.labels:
            if label not in ("Entity", "Node"):
                return label
        return None


@dataclass
class FilteredEntities:
    """过滤后的实体集合"""

    entities: list[EntityNode]
    entity_types: set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class GraphEntityReader:
    """
    图谱实体读取与过滤服务（Postgres 实现）

    公共接口与原 旧图谱 版本完全相同，调用方无需修改。
    """

    def __init__(self, api_key: str | None = None):
        # api_key 参数保留以兼容现有调用
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = get_graph_store()
        return self._client

    def get_all_nodes(self, graph_id: str) -> list[dict[str, Any]]:
        """获取图谱的所有节点"""
        logger.info(f"获取图谱 {graph_id} 的所有节点...")
        nodes = fetch_all_nodes(self._get_client(), graph_id)
        logger.info(f"共获取 {len(nodes)} 个节点")
        return nodes

    def get_all_edges(self, graph_id: str) -> list[dict[str, Any]]:
        """获取图谱的所有边"""
        logger.info(f"获取图谱 {graph_id} 的所有边...")
        edges = fetch_all_edges(self._get_client(), graph_id)
        logger.info(f"共获取 {len(edges)} 条边")
        return edges

    def get_node_edges(self, node_uuid: str, graph_id: str = "") -> list[dict[str, Any]]:
        """获取指定节点的所有相关边（按 graph_id 取图后在内存过滤）。"""
        if not graph_id:
            return []
        try:
            return fetch_node_edges(graph_id, node_uuid)
        except Exception as e:
            logger.warning(f"获取节点 {node_uuid} 的边失败: {str(e)}")
            return []

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: list[str] | None = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        """
        筛选出符合预定义实体类型的节点

        筛选逻辑：Labels 必须包含除 "Entity" 和 "Node" 之外的标签。
        """
        logger.info(f"开始筛选图谱 {graph_id} 的实体...")

        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)

        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        node_map = {n["uuid"]: n for n in all_nodes}

        filtered_entities: list[EntityNode] = []
        entity_types_found: set[str] = set()

        for node in all_nodes:
            labels = node.get("labels", [])
            custom_labels = [l for l in labels if l not in ("Entity", "Node")]

            if not custom_labels:
                continue

            if defined_entity_types:
                matching = [l for l in custom_labels if l in defined_entity_types]
                if not matching:
                    continue
                entity_type = matching[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )

            if enrich_with_edges:
                related_edges = []
                related_node_uuids: set[str] = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append(
                            {
                                "direction": "outgoing",
                                "edge_name": edge["name"],
                                "fact": edge["fact"],
                                "target_node_uuid": edge["target_node_uuid"],
                            }
                        )
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append(
                            {
                                "direction": "incoming",
                                "edge_name": edge["name"],
                                "fact": edge["fact"],
                                "source_node_uuid": edge["source_node_uuid"],
                            }
                        )
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges
                entity.related_nodes = [
                    {
                        "uuid": node_map[uid]["uuid"],
                        "name": node_map[uid]["name"],
                        "labels": node_map[uid]["labels"],
                        "summary": node_map[uid].get("summary", ""),
                    }
                    for uid in related_node_uuids
                    if uid in node_map
                ]

            filtered_entities.append(entity)

        logger.info(
            f"筛选完成: 总节点 {total_count}, 符合条件 {len(filtered_entities)}, "
            f"实体类型: {entity_types_found}"
        )
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str,
    ) -> EntityNode | None:
        """获取单个实体及其完整上下文"""
        try:
            r = fetch_node(graph_id, entity_uuid)
            if not r:
                return None

            edges = self.get_node_edges(entity_uuid, graph_id)
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}

            related_edges = []
            related_node_uuids: set[str] = set()
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append(
                        {
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        }
                    )
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append(
                        {
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        }
                    )
                    related_node_uuids.add(edge["source_node_uuid"])

            return EntityNode(
                uuid=r.get("uuid") or "",
                name=r.get("name") or "",
                labels=list(r.get("labels") or []),
                summary=r.get("summary") or "",
                attributes=r.get("attributes") or {},
                related_edges=related_edges,
                related_nodes=[
                    {
                        "uuid": node_map[uid]["uuid"],
                        "name": node_map[uid]["name"],
                        "labels": node_map[uid]["labels"],
                        "summary": node_map[uid].get("summary", ""),
                    }
                    for uid in related_node_uuids
                    if uid in node_map
                ],
            )

        except Exception as e:
            logger.error(f"获取实体 {entity_uuid} 失败: {str(e)}")
            return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> list[EntityNode]:
        """获取指定类型的所有实体"""
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities
