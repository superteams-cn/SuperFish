"""
图谱构建服务
使用严格本体约束的 LLM 抽取 + Neo4j 存储。
"""

import re
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY
from llama_index.core.indices.property_graph import SchemaLLMPathExtractor
from llama_index.core.schema import TextNode
from llama_index.llms.openai_like import OpenAILike

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.neo4j_graph_utils import (
    delete_group,
    fetch_all_edges,
    fetch_all_nodes,
    get_neo4j_graph_client,
)
from ..utils.locale import get_locale, set_locale, t
from ..utils.logger import get_logger
from .text_processor import TextProcessor

logger = get_logger('mirofish.graph_builder')

_RESERVED_ATTRS = {'uuid', 'name', 'group_id', 'name_embedding', 'summary', 'created_at'}


@dataclass
class GraphInfo:
    """图谱信息"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


def _clean_attr_name(name: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_]+', '_', name or '').strip('_').lower()
    if not cleaned:
        cleaned = "value"
    if cleaned in _RESERVED_ATTRS:
        cleaned = f"entity_{cleaned}"
    return cleaned


def _normalize_entity_key(entity_type: str, name: str) -> str:
    return f"{entity_type}:{(name or '').strip().lower()}"


def _schema_label(name: str) -> str:
    """Normalize ontology names for LlamaIndex strict enum validation."""
    label = re.sub(r'[^a-zA-Z0-9_]+', '_', name or '').strip('_').upper()
    return label or "ENTITY"


def _enum_member_name(value: str) -> str:
    name = re.sub(r'[^a-zA-Z0-9_]+', '_', value or '').strip('_').upper()
    if not name:
        name = "VALUE"
    if name[0].isdigit():
        name = f"V_{name}"
    return name


class GraphBuilderService:
    """
    图谱构建服务。

    该实现不依赖开放式图谱抽取，而是在每个文本块上用项目生成的
    ontology 作为严格 schema，让 LLM 只返回允许的实体类型、关系类型和
    source/target 组合，再写入 Neo4j。
    """

    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[Any] = None):
        # api_key 参数保留以兼容现有调用；Neo4j 配置从 Config 读取。
        self.task_manager = TaskManager()
        self.llm = llm_client or self._make_llamaindex_llm()
        self.client = get_neo4j_graph_client()

    def _make_llamaindex_llm(self) -> OpenAILike:
        return OpenAILike(
            model=Config.LLM_MODEL_NAME,
            api_base=Config.LLM_BASE_URL,
            api_key=Config.LLM_API_KEY,
            temperature=0.1,
            max_tokens=Config.GRAPH_EXTRACT_MAX_TOKENS,
            is_chat_model=True,
            is_function_calling_model=False,
            timeout=120,
        )

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3,
    ) -> str:
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            },
        )
        current_locale = get_locale()
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, current_locale),
            daemon=True,
        )
        thread.start()
        return task_id

    def build_graph(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3,
        locale: str = 'zh',
    ):
        """使用已有任务ID同步构建图谱，供 API 层托管项目状态。"""
        self._build_graph_worker(
            task_id,
            text,
            ontology,
            graph_name,
            chunk_size,
            chunk_overlap,
            batch_size,
            locale,
        )

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        locale: str = 'zh',
    ):
        set_locale(locale)

        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message=t('progress.startBuildingGraph'),
            )

            self.client.build_indices_and_constraints()
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=t('progress.graphCreated', graphId=graph_id),
            )

            schema = self._build_schema(ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message=t('progress.ontologySet'),
            )

            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=t('progress.textSplit', count=total_chunks),
            )

            nodes, edges = self._extract_chunks(
                chunks=chunks,
                schema=schema,
                progress_callback=lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.65),
                    message=msg,
                ),
            )

            self.task_manager.update_task(
                task_id,
                progress=88,
                message=t('progress.fetchingGraphInfo'),
            )
            self.client.write_graph(graph_id, nodes, edges)
            graph_info = self._get_graph_info(graph_id)

            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "node_count": graph_info.node_count,
                "edge_count": graph_info.edge_count,
                "chunks_processed": total_chunks,
            })

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            logger.error(f"图谱构建失败: {error_msg}")
            self.task_manager.fail_task(task_id, error_msg)

    def create_graph(self, name: str) -> str:
        """生成图谱 group_id。"""
        return f"mirofish_{uuid.uuid4().hex[:16]}"

    def _build_schema(self, ontology: Dict[str, Any]) -> Dict[str, Any]:
        entity_types = {}
        entity_label_by_name = {}
        for entity in ontology.get("entity_types", []):
            name = entity.get("name")
            if not name:
                continue
            label = _schema_label(name)
            attrs = [_clean_attr_name(attr.get("name", "")) for attr in entity.get("attributes", [])]
            entity_label_by_name[name] = label
            entity_types[label] = {
                "name": name,
                "label": label,
                "display_name": entity.get("display_name") or name,
                "description": entity.get("description", ""),
                "attributes": sorted({attr for attr in attrs if attr} | {"summary"}),
            }

        edge_types = {}
        allowed_triples = set()
        for edge in ontology.get("edge_types", []):
            name = (edge.get("name") or "").upper()
            if not name:
                continue
            source_targets = []
            for st in edge.get("source_targets", []):
                source = entity_label_by_name.get(st.get("source"))
                target = entity_label_by_name.get(st.get("target"))
                if source in entity_types and target in entity_types:
                    source_targets.append({"source": source, "target": target})
                    allowed_triples.add((source, name, target))
            if source_targets:
                edge_types[name] = {
                    "name": name,
                    "display_name": edge.get("display_name") or name,
                    "description": edge.get("description", ""),
                    "source_targets": source_targets,
                    "attributes": sorted({
                        _clean_attr_name(attr.get("name", ""))
                        for attr in edge.get("attributes", [])
                        if attr.get("name")
                    } | {"fact"}),
                }

        if not entity_types:
            raise ValueError("本体缺少可用的 entity_types")
        if not edge_types:
            raise ValueError("本体缺少可用的 edge_types/source_targets")

        return {
            "entity_types": entity_types,
            "edge_types": edge_types,
            "allowed_triples": allowed_triples,
            "entity_label_by_name": entity_label_by_name,
        }

    def _extract_chunks(
        self,
        chunks: List[str],
        schema: Dict[str, Any],
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        nodes_by_key: Dict[str, Dict[str, Any]] = {}
        edges_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        total = len(chunks)

        for idx, chunk in enumerate(chunks):
            if progress_callback:
                progress_callback(
                    t('progress.sendingBatch', current=idx + 1, total=total, chunks=1),
                    idx / max(total, 1),
                )

            valid_nodes, valid_edges = self._extract_chunk_with_llamaindex(chunk, schema, idx)

            local_key_to_uuid = {}
            for node in valid_nodes:
                node_key = _normalize_entity_key(node["type"], node["name"])
                if node_key not in nodes_by_key:
                    nodes_by_key[node_key] = {
                        "uuid": str(uuid.uuid4()),
                        "name": node["name"],
                        "summary": node.get("summary") or "",
                        "labels": ["Entity", node["type"]],
                        "attributes": node.get("attributes", {}),
                    }
                else:
                    if node.get("summary") and node["summary"] not in nodes_by_key[node_key].get("summary", ""):
                        summary = nodes_by_key[node_key].get("summary", "")
                        nodes_by_key[node_key]["summary"] = (summary + "\n" + node["summary"]).strip()[:2000]
                    nodes_by_key[node_key]["attributes"].update(node.get("attributes", {}))
                local_key_to_uuid[node.get("id") or node["name"]] = nodes_by_key[node_key]["uuid"]
                local_key_to_uuid[node["name"]] = nodes_by_key[node_key]["uuid"]

            for edge in valid_edges:
                source_uuid = local_key_to_uuid.get(edge["source"])
                target_uuid = local_key_to_uuid.get(edge["target"])
                if not source_uuid or not target_uuid:
                    continue
                edge_key = (source_uuid, edge["type"], target_uuid)
                if edge_key not in edges_by_key:
                    edges_by_key[edge_key] = {
                        "uuid": str(uuid.uuid4()),
                        "name": edge["type"],
                        "fact": edge.get("fact") or f"{edge['source']} {edge['type']} {edge['target']}",
                        "source_node_uuid": source_uuid,
                        "target_node_uuid": target_uuid,
                        "attributes": edge.get("attributes", {}),
                    }

            if idx < total - 1:
                time.sleep(0.2)

        if progress_callback:
            progress_callback(t('progress.processingComplete', completed=total, total=total), 1.0)

        return list(nodes_by_key.values()), list(edges_by_key.values())

    def _extract_chunk_with_llamaindex(
        self,
        chunk: str,
        schema: Dict[str, Any],
        chunk_idx: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        extractor = self._make_schema_extractor(schema)
        text_node = TextNode(text=chunk, id_=f"chunk_{chunk_idx:04d}")
        extracted_node = extractor([text_node])[0]

        kg_nodes = extracted_node.metadata.get(KG_NODES_KEY, [])
        kg_relations = extracted_node.metadata.get(KG_RELATIONS_KEY, [])

        nodes_by_name = {}
        valid_nodes = []
        for node in kg_nodes:
            entity_type = str(getattr(node, "label", "") or "").upper()
            name = str(getattr(node, "name", "") or "").strip()
            if entity_type not in schema["entity_types"] or not name:
                continue
            properties = dict(getattr(node, "properties", {}) or {})
            allowed_attrs = set(schema["entity_types"][entity_type].get("attributes", []))
            attrs = {
                _clean_attr_name(k): v
                for k, v in properties.items()
                if _clean_attr_name(k) in allowed_attrs and k != "summary"
            }
            summary = str(properties.get("summary") or "")[:1000]
            record = {
                "id": name,
                "name": name,
                "type": entity_type,
                "summary": summary,
                "attributes": {
                    **attrs,
                    "ontology_type": schema["entity_types"][entity_type]["name"],
                    "display_type": schema["entity_types"][entity_type]["display_name"],
                },
            }
            nodes_by_name[name] = record
            valid_nodes.append(record)

        valid_edges = []
        for rel in kg_relations:
            source_id = str(getattr(rel, "source_id", "") or "")
            target_id = str(getattr(rel, "target_id", "") or "")
            rel_type = str(getattr(rel, "label", "") or "").upper()
            source = nodes_by_name.get(source_id)
            target = nodes_by_name.get(target_id)
            if not source or not target:
                continue
            if (source["type"], rel_type, target["type"]) not in schema["allowed_triples"]:
                continue
            properties = dict(getattr(rel, "properties", {}) or {})
            allowed_attrs = set(schema["edge_types"][rel_type].get("attributes", []))
            attrs = {
                _clean_attr_name(k): v
                for k, v in properties.items()
                if _clean_attr_name(k) in allowed_attrs and k != "fact"
            }
            valid_edges.append({
                "source": source_id,
                "target": target_id,
                "type": rel_type,
                "fact": str(properties.get("fact") or "")[:1000],
                "attributes": {
                    **attrs,
                    "display_type": schema["edge_types"][rel_type]["display_name"],
                },
            })

        return valid_nodes, valid_edges

    def _make_schema_extractor(self, schema: Dict[str, Any]) -> SchemaLLMPathExtractor:
        entity_enum = Enum(
            "MiroFishEntityType",
            {
                _enum_member_name(entity["label"]): entity["label"]
                for entity in schema["entity_types"].values()
            },
        )
        relation_enum = Enum(
            "MiroFishRelationType",
            {
                _enum_member_name(edge_name): edge_name
                for edge_name in schema["edge_types"]
            },
        )
        entity_props = sorted({
            attr
            for entity in schema["entity_types"].values()
            for attr in entity.get("attributes", [])
        })
        relation_props = sorted({
            attr
            for edge in schema["edge_types"].values()
            for attr in edge.get("attributes", [])
        })
        return SchemaLLMPathExtractor(
            llm=self.llm,
            possible_entities=entity_enum,
            possible_entity_props=entity_props,
            possible_relations=relation_enum,
            possible_relation_props=relation_props,
            kg_validation_schema=list(schema["allowed_triples"]),
            strict=True,
            max_triplets_per_chunk=Config.GRAPH_EXTRACT_MAX_TRIPLETS,
            num_workers=1,
            allow_additional_properties=False,
        )

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)
        entity_types = set()
        for node in nodes:
            for label in node.get("labels", []):
                if label not in ("Entity", "Node"):
                    entity_types.add(label)
        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types),
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)
        node_map = {n["uuid"]: n["name"] for n in nodes}

        nodes_data = [
            {
                "uuid": n["uuid"],
                "name": n["name"],
                "labels": n["labels"],
                "summary": n["summary"],
                "attributes": n["attributes"],
                "created_at": None,
            }
            for n in nodes
        ]

        edges_data = [
            {
                "uuid": e["uuid"],
                "name": e["name"],
                "fact": e["fact"],
                "fact_type": e["name"],
                "source_node_uuid": e["source_node_uuid"],
                "target_node_uuid": e["target_node_uuid"],
                "source_node_name": node_map.get(e["source_node_uuid"], ""),
                "target_node_name": node_map.get(e["target_node_uuid"], ""),
                "attributes": e["attributes"],
                "created_at": str(e["created_at"]) if e["created_at"] else None,
                "valid_at": str(e["valid_at"]) if e.get("valid_at") else None,
                "invalid_at": str(e["invalid_at"]) if e.get("invalid_at") else None,
                "expired_at": str(e["expired_at"]) if e.get("expired_at") else None,
                "episodes": [],
            }
            for e in edges
        ]

        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, graph_id: str):
        delete_group(self.client, graph_id)
