"""
图谱构建服务
使用严格本体约束的 LLM 抽取 + Neo4j 存储。
"""

import asyncio
import json
import re
import threading
import time
import uuid
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY
from llama_index.core.indices.property_graph import SchemaLLMPathExtractor
from llama_index.core.schema import TextNode
from llama_index.llms.openai_like import OpenAILike
from pydantic import PrivateAttr

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.llm_client import LLMClient
from ..utils.locale import get_locale, set_locale, t
from ..utils.logger import get_logger
from ..utils.neo4j_graph_utils import (
    delete_group,
    fetch_all_edges,
    fetch_all_nodes,
    get_neo4j_graph_client,
)
from .text_processor import TextProcessor

logger = get_logger("superfish.graph_builder")

_RESERVED_ATTRS = {"uuid", "name", "group_id", "name_embedding", "summary", "created_at"}


@dataclass
class GraphInfo:
    """图谱信息"""

    graph_id: str
    node_count: int
    edge_count: int
    entity_types: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


def _clean_attr_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", name or "").strip("_").lower()
    if not cleaned:
        cleaned = "value"
    if cleaned in _RESERVED_ATTRS:
        cleaned = f"entity_{cleaned}"
    return cleaned


def _normalize_entity_key(entity_type: str, name: str) -> str:
    return f"{entity_type}:{(name or '').strip().lower()}"


def _schema_label(name: str) -> str:
    """Normalize ontology names for LlamaIndex strict enum validation."""
    label = re.sub(r"[^\w]+", "_", name or "", flags=re.UNICODE).strip("_").upper()
    return label or "ENTITY"


def _schema_value(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").upper()


def _enum_member_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", value or "").strip("_").upper()
    if not name:
        checksum = zlib.crc32((value or "").encode("utf-8")) & 0xFFFFFFFF
        name = f"VALUE_{checksum:08X}"
    if name[0].isdigit():
        name = f"V_{name}"
    return name


def _enum_mapping(values: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for value in values:
        member = _enum_member_name(value)
        if member in used:
            checksum = zlib.crc32(value.encode("utf-8")) & 0xFFFFFFFF
            member = f"{member}_{checksum:08X}"
        mapping[member] = value
        used.add(member)
    return mapping


class SuperFishStructuredLLM(OpenAILike):
    """OpenAI-compatible LLM wrapper that returns Pydantic objects via JSON mode."""

    _json_client: LLMClient = PrivateAttr()

    def __init__(self):
        super().__init__(
            model=Config.LLM_MODEL_NAME,
            api_base=Config.LLM_BASE_URL,
            api_key=Config.LLM_API_KEY,
            temperature=0.1,
            max_tokens=Config.GRAPH_EXTRACT_MAX_TOKENS,
            is_chat_model=True,
            is_function_calling_model=False,
            timeout=120,
        )
        self._json_client = LLMClient()

    def structured_predict(
        self,
        output_cls: Any,
        prompt: Any,
        llm_kwargs: dict[str, Any] | None = None,
        **prompt_args: Any,
    ) -> Any:
        prompt_text = prompt.format(**prompt_args) if hasattr(prompt, "format") else str(prompt)
        output_schema = output_cls.model_json_schema()
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract knowledge graph triplets from Chinese text. "
                    "Return only a valid JSON object matching the provided JSON schema. "
                    "Do not include markdown, explanations, or fields outside the schema."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt_text}\n\n"
                    "JSON schema to follow exactly:\n"
                    f"{json.dumps(output_schema, ensure_ascii=False)}\n\n"
                    "Important rules:\n"
                    "- Use the enum values exactly as written.\n"
                    "- Each triplet must contain subject, relation, and object.\n"
                    "- Put a concise Chinese evidence sentence in relation.properties.fact when possible.\n"
                    "- Put a concise Chinese summary in entity.properties.summary when useful.\n"
                    "- Keep the JSON compact and complete.\n"
                    '- If no valid triplet is present, return {"triplets": []}.'
                ),
            },
        ]
        last_error = None
        for attempt in range(2):
            try:
                data = self._json_client.chat_json(
                    messages,
                    temperature=0.1,
                    max_tokens=Config.GRAPH_EXTRACT_MAX_TOKENS,
                )
                return output_cls.model_validate(data)
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning(
                        "LlamaIndex schema extraction returned invalid JSON; retrying once"
                    )
                    continue
                message = str(exc)
                logger.warning(
                    "LlamaIndex schema extraction JSON validation failed after retry: "
                    f"{type(exc).__name__}: {message[:500]}"
                )
        raise last_error

    async def astructured_predict(
        self,
        output_cls: Any,
        prompt: Any,
        llm_kwargs: dict[str, Any] | None = None,
        **prompt_args: Any,
    ) -> Any:
        return await asyncio.to_thread(
            self.structured_predict,
            output_cls,
            prompt,
            llm_kwargs,
            **prompt_args,
        )


class GraphBuilderService:
    """
    图谱构建服务。

    该实现不依赖开放式图谱抽取，而是在每个文本块上用项目生成的
    ontology 作为严格 schema，让 LLM 只返回允许的实体类型、关系类型和
    source/target 组合，再写入 Neo4j。
    """

    def __init__(self, api_key: str | None = None, llm_client: Any | None = None):
        # api_key 参数保留以兼容现有调用；Neo4j 配置从 Config 读取。
        self.task_manager = TaskManager()
        self.llm = llm_client or self._make_llamaindex_llm()
        self.client = get_neo4j_graph_client()

    def _make_llamaindex_llm(self) -> OpenAILike:
        return SuperFishStructuredLLM()

    def build_graph_async(
        self,
        text: str,
        ontology: dict[str, Any],
        graph_name: str = "SuperFish Graph",
        chunk_size: int = 5000,
        chunk_overlap: int = 200,
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
            args=(
                task_id,
                text,
                ontology,
                graph_name,
                chunk_size,
                chunk_overlap,
                batch_size,
                current_locale,
            ),
            daemon=True,
        )
        thread.start()
        return task_id

    def build_graph(
        self,
        task_id: str,
        text: str,
        ontology: dict[str, Any],
        graph_name: str = "SuperFish Graph",
        chunk_size: int = 5000,
        chunk_overlap: int = 200,
        batch_size: int = 3,
        locale: str = "zh",
        graph_id: str | None = None,
    ):
        """使用已有任务ID同步构建图谱，供 API 层托管项目状态。

        若传入 ``graph_id``，则复用该 ID（API 层会提前写入项目以支持构建期间实时轮询）。
        """
        self._build_graph_worker(
            task_id,
            text,
            ontology,
            graph_name,
            chunk_size,
            chunk_overlap,
            batch_size,
            locale,
            graph_id,
        )

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        locale: str = "zh",
        graph_id: str | None = None,
    ):
        set_locale(locale)

        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message=t("progress.startBuildingGraph"),
            )

            self.client.build_indices_and_constraints()
            graph_id = graph_id or self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=t("progress.graphCreated", graphId=graph_id),
            )

            schema = self._build_schema(ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message=t("progress.ontologySet"),
            )

            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=t("progress.textSplit", count=total_chunks),
            )

            # 每抽取一个文本块就把已累积的节点/边增量写入 Neo4j，
            # 让前端轮询 /api/graph/data 时能实时看到图谱逐步生长。
            nodes, edges = self._extract_chunks(
                chunks=chunks,
                schema=schema,
                progress_callback=lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.65),
                    message=msg,
                ),
                write_callback=lambda n, e: self.client.write_graph(graph_id, n, e),
            )

            # 实体消解：合并同一实体的不同称谓(全称/简称、别名/别称等)
            self.task_manager.update_task(
                task_id,
                progress=86,
                message=t("progress.resolvingEntities"),
            )
            raw_count = len(nodes)
            nodes, edges = self._resolve_entities(nodes, edges)

            self.task_manager.update_task(
                task_id,
                progress=88,
                message=t("progress.fetchingGraphInfo"),
            )
            # 若发生过合并,增量写入的别名节点仍在库中,需先清空再写规范集；
            # 未合并则直接幂等全量写入(保留增量结果)。
            if len(nodes) != raw_count:
                delete_group(self.client, graph_id)
            self.client.write_graph(graph_id, nodes, edges)
            graph_info = self._get_graph_info(graph_id)

            self.task_manager.complete_task(
                task_id,
                {
                    "graph_id": graph_id,
                    "graph_info": graph_info.to_dict(),
                    "node_count": graph_info.node_count,
                    "edge_count": graph_info.edge_count,
                    "chunks_processed": total_chunks,
                },
            )

        except Exception as e:
            import traceback

            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            logger.error(f"图谱构建失败: {error_msg}")
            self.task_manager.fail_task(task_id, error_msg)

    @staticmethod
    def create_graph(name: str) -> str:
        """生成图谱 group_id。"""
        return f"superfish_{uuid.uuid4().hex[:16]}"

    def _build_schema(self, ontology: dict[str, Any]) -> dict[str, Any]:
        entity_types = {}
        entity_label_by_name = {}
        for entity in ontology.get("entity_types", []):
            name = entity.get("name")
            if not name:
                continue
            label = _schema_label(name)
            attrs = [
                _clean_attr_name(attr.get("name", "")) for attr in entity.get("attributes", [])
            ]
            entity_label_by_name[name] = label
            entity_types[label] = {
                "name": name,
                "label": label,
                "description": entity.get("description", ""),
                "attributes": sorted({attr for attr in attrs if attr} | {"summary"}),
            }

        edge_types = {}
        allowed_triples = set()
        for edge in ontology.get("edge_types", []):
            name = _schema_label(edge.get("name") or "")
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
                    "description": edge.get("description", ""),
                    "source_targets": source_targets,
                    "attributes": sorted(
                        {
                            _clean_attr_name(attr.get("name", ""))
                            for attr in edge.get("attributes", [])
                            if attr.get("name")
                        }
                        | {"fact"}
                    ),
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
        chunks: list[str],
        schema: dict[str, Any],
        progress_callback: Callable[[str, float], None] | None = None,
        write_callback: Callable[[list[dict[str, Any]], list[dict[str, Any]]], None] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        nodes_by_key: dict[str, dict[str, Any]] = {}
        edges_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        total = len(chunks)

        for idx, chunk in enumerate(chunks):
            if progress_callback:
                progress_callback(
                    t("progress.sendingBatch", current=idx + 1, total=total, chunks=1),
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
                    if node.get("summary") and node["summary"] not in nodes_by_key[node_key].get(
                        "summary", ""
                    ):
                        summary = nodes_by_key[node_key].get("summary", "")
                        nodes_by_key[node_key]["summary"] = (
                            summary + "\n" + node["summary"]
                        ).strip()[:2000]
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
                        "fact": edge.get("fact")
                        or f"{edge['source']} {edge['type']} {edge['target']}",
                        "source_node_uuid": source_uuid,
                        "target_node_uuid": target_uuid,
                        "attributes": edge.get("attributes", {}),
                    }

            # 增量落库：写入当前已累积的全量节点/边（MERGE 幂等），
            # 使前端轮询能实时看到本块新增的实体与关系。
            if write_callback and (valid_nodes or valid_edges):
                try:
                    write_callback(
                        list(nodes_by_key.values()),
                        list(edges_by_key.values()),
                    )
                except Exception as exc:  # 增量写失败不应中断整体抽取
                    logger.warning(f"增量写入 Neo4j 失败（块 {idx + 1}/{total}）: {exc}")

            if idx < total - 1:
                time.sleep(0.2)

        if progress_callback:
            progress_callback(t("progress.processingComplete", completed=total, total=total), 1.0)

        return list(nodes_by_key.values()), list(edges_by_key.values())

    def _resolve_entities(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """实体消解：用 LLM 把同一现实实体的不同称谓(本名/字/号/简称/全称)聚类合并。

        分块独立抽取 + 仅字面去重会把同一实体的不同称谓(全称/简称、别名/别称等)拆成多个节点。
        本步在全部抽完后,让 LLM 判定别名分组,选规范节点,合并摘要/属性并把边重指向
        规范 uuid,再交由调用方清空旧图并写入规范集。

        失败或无可合并时原样返回(调用方据节点数变化决定是否需要清库重写)。
        """
        # 仅对实体类型节点消解，规模过大时跳过(单次 LLM 调用上限)
        if len(nodes) < 2 or len(nodes) > 400:
            return nodes, edges

        listing = []
        for i, n in enumerate(nodes):
            labels = n.get("labels") or []
            ntype = next((label for label in labels if label != "Entity"), "Entity")
            summary = (n.get("summary") or "").replace("\n", " ")[:50]
            listing.append(f"{i}. {n.get('name', '')} [{ntype}] — {summary}")

        prompt = (
            "你在做知识图谱的实体消解。下面是从同一篇文档抽取的实体列表(序号. 名称 [类型] — 简介)。\n"
            "请把指向【同一个现实实体】的不同称谓归为一组。常见的同一实体不同写法包括:"
            "全称与简称/缩写、正式名与别名/别称/俗称、同一实体在文中出现的不同表述。\n"
            "规则:\n"
            "- 仅在确信是同一实体时才合并;不确定就保持独立。\n"
            "- 名称相近但实为不同实体的不要合并;优先依据简介与类型等上下文判断,而非仅看字面。\n"
            "- 每组选一个最完整、最规范的作为 canonical_index。\n"
            '仅返回 JSON:{"groups":[{"canonical_index":int,"member_indices":[int,...]}]},'
            '只包含成员数 ≥2 的组,没有可合并时返回 {"groups":[]}。\n\n'
            "实体列表:\n" + "\n".join(listing)
        )

        try:
            result = LLMClient().chat_json(
                [{"role": "user", "content": prompt}], temperature=0.1, max_tokens=4096
            )
        except Exception as exc:
            logger.warning(f"实体消解 LLM 调用失败,跳过: {exc}")
            return nodes, edges

        groups = result.get("groups") if isinstance(result, dict) else None
        if not groups:
            return nodes, edges

        n_total = len(nodes)
        remap: dict[str, str] = {}  # 别名 uuid -> 规范 uuid
        merged_away: set[int] = set()  # 被合并掉的节点下标

        for g in groups:
            members = [
                i for i in g.get("member_indices", []) if isinstance(i, int) and 0 <= i < n_total
            ]
            members = list(dict.fromkeys(members))  # 去重保序
            if len(members) < 2:
                continue
            canon = g.get("canonical_index")
            if not isinstance(canon, int) or canon not in members:
                canon = max(members, key=lambda i: len(nodes[i].get("name", "")))  # 退化:取最长名
            canon_node = nodes[canon]
            aliases = set(canon_node.get("attributes", {}).get("aliases", []) or [])
            for i in members:
                if i == canon:
                    continue
                src = nodes[i]
                remap[src["uuid"]] = canon_node["uuid"]
                merged_away.add(i)
                aliases.add(src.get("name", ""))
                # 合并摘要与属性
                if src.get("summary") and src["summary"] not in (canon_node.get("summary") or ""):
                    canon_node["summary"] = (
                        canon_node.get("summary", "") + "\n" + src["summary"]
                    ).strip()[:2000]
                for k, v in (src.get("attributes") or {}).items():
                    canon_node.setdefault("attributes", {}).setdefault(k, v)
            if aliases:
                canon_node.setdefault("attributes", {})["aliases"] = sorted(a for a in aliases if a)

        if not merged_away:
            return nodes, edges

        new_nodes = [n for i, n in enumerate(nodes) if i not in merged_away]

        # 边重指向规范 uuid，丢弃因合并产生的自环，按 (源,类型,目标) 再去重
        new_edges: list[dict[str, Any]] = []
        seen_edge: set[tuple[str, str, str]] = set()
        for e in edges:
            s = remap.get(e["source_node_uuid"], e["source_node_uuid"])
            tgt = remap.get(e["target_node_uuid"], e["target_node_uuid"])
            if s == tgt:
                continue  # 合并后自指,丢弃
            key = (s, e.get("name", ""), tgt)
            if key in seen_edge:
                continue
            seen_edge.add(key)
            new_edges.append({**e, "source_node_uuid": s, "target_node_uuid": tgt})

        logger.info(f"实体消解:{n_total} → {len(new_nodes)} 个实体(合并 {len(merged_away)} 个别名)")
        return new_nodes, new_edges

    def _extract_chunk_with_llamaindex(
        self,
        chunk: str,
        schema: dict[str, Any],
        chunk_idx: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        # 三元组上限随块长等比例放大,保持抽取密度不随 chunk_size 变化而漏抽
        max_triplets = max(Config.GRAPH_EXTRACT_MAX_TRIPLETS, len(chunk) // 70)
        extractor = self._make_schema_extractor(schema, max_triplets)
        text_node = TextNode(text=chunk, id_=f"chunk_{chunk_idx:04d}")
        extracted_node = extractor([text_node])[0]

        kg_nodes = extracted_node.metadata.get(KG_NODES_KEY, [])
        kg_relations = extracted_node.metadata.get(KG_RELATIONS_KEY, [])

        nodes_by_name = {}
        valid_nodes = []
        for node in kg_nodes:
            entity_type = _schema_value(getattr(node, "label", ""))
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
                },
            }
            nodes_by_name[name] = record
            valid_nodes.append(record)

        valid_edges = []
        for rel in kg_relations:
            source_id = str(getattr(rel, "source_id", "") or "")
            target_id = str(getattr(rel, "target_id", "") or "")
            rel_type = _schema_value(getattr(rel, "label", ""))
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
            valid_edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "type": rel_type,
                    "fact": str(properties.get("fact") or "")[:1000],
                    "attributes": attrs,
                }
            )

        return valid_nodes, valid_edges

    def _make_schema_extractor(
        self, schema: dict[str, Any], max_triplets: int | None = None
    ) -> SchemaLLMPathExtractor:
        entity_members = _enum_mapping(
            [entity["label"] for entity in schema["entity_types"].values()]
        )
        relation_members = _enum_mapping(list(schema["edge_types"]))
        entity_member_by_label = {label: member for member, label in entity_members.items()}
        relation_member_by_label = {label: member for member, label in relation_members.items()}
        entity_enum = Enum("SuperFishEntityType", entity_members)
        relation_enum = Enum("SuperFishRelationType", relation_members)
        validation_schema = [
            (
                entity_enum[entity_member_by_label[source]],
                relation_enum[relation_member_by_label[relation]],
                entity_enum[entity_member_by_label[target]],
            )
            for source, relation, target in schema["allowed_triples"]
        ]
        entity_props = sorted(
            {
                attr
                for entity in schema["entity_types"].values()
                for attr in entity.get("attributes", [])
            }
        )
        relation_props = sorted(
            {attr for edge in schema["edge_types"].values() for attr in edge.get("attributes", [])}
        )
        allowed_triples_text = "\n".join(
            f"- {source} --{relation}--> {target}"
            for source, relation, target in sorted(schema["allowed_triples"])
        )
        extract_prompt = (
            "Given the following Chinese text, extract a knowledge graph according to "
            "the project ontology. Return at most {max_triplets_per_chunk} paths.\n"
            "Only use these source-relation-target combinations:\n"
            f"{allowed_triples_text}\n"
            "Use specific named entities from the text as subject/object names.\n"
            "-------\n"
            "{text}\n"
            "-------\n"
        )
        return SchemaLLMPathExtractor(
            llm=self.llm,
            extract_prompt=extract_prompt,
            possible_entities=entity_enum,
            possible_entity_props=entity_props,
            possible_relations=relation_enum,
            possible_relation_props=relation_props,
            kg_validation_schema=validation_schema,
            strict=True,
            max_triplets_per_chunk=max_triplets or Config.GRAPH_EXTRACT_MAX_TRIPLETS,
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

    def get_graph_data(self, graph_id: str) -> dict[str, Any]:
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
