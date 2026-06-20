"""通用实体消解算法（与领域、语言、抽取框架无关）。

输入一组节点与边，把指向同一现实实体、却被拆成多个节点的实体合并为规范节点，
并把边重指向规范节点。算法不含任何领域词表或硬编码实体名，仅依据：

1. **确定性归并**：名称做 Unicode 归一(NFKC + 去空白 + casefold)后相同即视为同一实体。
   分块抽取常把同一名称在不同文本块里判成不同类型(例：主角时而被判成 A 类、时而 B 类)，
   旧逻辑以「类型:名称」为去重键会把它们拆开；本步只看归一名称，跨类型也能合并。
2. **可选别名归并**：调用方可传入额外的别名分组(例如 LLM 判定的 全称/简称/别号 同指)，
   与确定性结果一起用并查集(union-find)合并，两种信号叠加而不冲突。

合并时规范节点的选取与类型裁决均按**关系度数**加权(度数高者更可能是规范主体)，
因此对任意题材的图谱都成立，无需调参或词表。
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from typing import Any

NodeList = list[dict[str, Any]]
EdgeList = list[dict[str, Any]]


def _char_bigrams(text: str) -> set[str]:
    text = normalize_name(text).replace(" ", "")
    if len(text) < 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def unambiguous_containment_groups(nodes: NodeList) -> list[list[int]]:
    """**确定性**安全归并：仅当一个名字是**恰好一个**其它名字的子串时，判为同指并合并。

    这是稳定可复现的「主干」，即便 LLM 不可用也始终生效，且**绝不误并**：
    - 安全：敖广 ⊂ 东海龙王敖广（仅一个容器）→ 合并；
    - 不碰歧义：妖王 ⊂ 七十二洞妖王/乌鸡国妖王/通天河妖王（多个不同容器，多半是通用称谓
      被不同实体共享）→ 不动，留给 LLM 逐一判定，宁可不合并也不误并。

    无领域词表：靠「容器唯一性」而非具体词识别安全场景。较短名长度需 ≥2。
    """
    n = len(nodes)
    if n < 2:
        return []
    norm = [normalize_name(node.get("name")) for node in nodes]

    uf = _UnionFind(n)
    for i in range(n):
        ni = norm[i]
        if len(ni) < 2:
            continue
        # 包含 ni 且名称不同的「容器」们；按归一名去重统计是否唯一
        containers = {norm[j]: j for j in range(n) if j != i and norm[j] != ni and ni in norm[j]}
        if len(containers) == 1:
            uf.union(i, next(iter(containers.values())))

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    return [sorted(m) for m in groups.values() if len(m) >= 2]


def candidate_clusters(
    nodes: NodeList,
    *,
    bigram_min: float = 0.7,
    df_max: int = 4,
    max_cluster: int = 12,
) -> list[list[int]]:
    """按**名称**生成「疑似同指」候选簇（blocking，纯字符串，无领域词表）。

    候选信号（任一成立即入簇，**偏召回**，精度由下游 LLM 裁决——这点很关键：像「妖王」
    这种被多个不同妖怪名共享的子串，确定性合并会把不同实体并错，必须让 LLM 拆分）：
    - **包含**：一名是另一名子串，较短名长度 ≥2，且其「文档频率」≤ df_max
      （过高频的子串多是通用称谓，按频率自动剔除，不靠词表）；
    - **字符二元组 Jaccard** ≥ bigram_min（共享字根/换序/个别字差异，如 托塔李天王/托搭李天王）。

    不用图结构：稠密图里「共享邻居」会把众多中心实体连成巨簇、淹没真正别名
    （昵称型别名改由 LLM 全局判定，见 graph_builder）。返回候选簇（每簇 2..max_cluster）。
    """
    n = len(nodes)
    if n < 2:
        return []

    norm = [normalize_name(node.get("name")) for node in nodes]
    bigrams = [_char_bigrams(node.get("name", "")) for node in nodes]
    df: Counter[str] = Counter()
    for a in set(filter(None, norm)):
        df[a] = sum(1 for b in norm if a in b)

    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            ni, nj = norm[i], norm[j]
            if not ni or not nj or ni == nj:
                continue
            linked = False
            if len(ni) >= 2 and ni in nj and df[ni] <= df_max:
                linked = True
            elif len(nj) >= 2 and nj in ni and df[nj] <= df_max:
                linked = True
            elif bigrams[i] and bigrams[j]:
                inter = len(bigrams[i] & bigrams[j])
                union = len(bigrams[i] | bigrams[j])
                if union and inter / union >= bigram_min:
                    linked = True
            if linked:
                uf.union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(uf.find(i), []).append(i)

    return [sorted(m) for m in clusters.values() if 2 <= len(m) <= max_cluster]


def normalize_name(name: str | None) -> str:
    """归一实体名用于确定性匹配：NFKC(全角/半角、兼容字符统一) + 折叠空白 + casefold。"""
    text = unicodedata.normalize("NFKC", str(name or ""))
    text = " ".join(text.split())  # 折叠所有内部/首尾空白
    return text.casefold()


def _node_type(node: dict[str, Any]) -> str:
    """取节点的本体类型：优先 attributes.ontology_type，回退首个非 Entity 标签。"""
    attr_type = (node.get("attributes") or {}).get("ontology_type")
    if attr_type:
        return str(attr_type)
    for label in node.get("labels") or []:
        if label and label not in ("Entity", "Node"):
            return str(label)
    return "Entity"


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, i: int) -> int:
        root = i
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[i] != root:  # 路径压缩
            self._parent[i], i = root, self._parent[i]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)  # 取较小下标为根，结果稳定可预测


def resolve_entities(
    nodes: NodeList,
    edges: EdgeList,
    alias_groups: list[list[int]] | None = None,
) -> tuple[NodeList, EdgeList, dict[str, Any]]:
    """合并同指实体并重指向边，返回 (规范节点, 规范边, 统计信息)。

    Args:
        nodes: 节点列表，每个含 uuid/name/labels/summary/attributes。
        edges: 边列表，每个含 uuid/name/source_node_uuid/target_node_uuid/...。
        alias_groups: 可选。额外的同指分组，元素为 nodes 下标的列表(LLM 等外部信号)。

    算法对输入顺序稳定：同一输入恒得到同一规范集（便于测试与幂等重算）。
    """
    n = len(nodes)
    stats: dict[str, Any] = {"raw_nodes": n, "raw_edges": len(edges)}
    if n < 2:
        stats.update(merged_nodes=0, canonical_nodes=n, dropped_edges=0)
        return nodes, edges, stats

    uuid_to_index = {node["uuid"]: i for i, node in enumerate(nodes)}

    # 各节点的关系度数（用于规范节点与类型裁决的加权）
    degree = [0] * n
    for edge in edges:
        for end in ("source_node_uuid", "target_node_uuid"):
            idx = uuid_to_index.get(edge.get(end))
            if idx is not None:
                degree[idx] += 1

    uf = _UnionFind(n)

    # (1) 确定性：归一名称相同则合并（跨类型）
    by_norm: dict[str, int] = {}
    for i, node in enumerate(nodes):
        key = normalize_name(node.get("name"))
        if not key:
            continue
        if key in by_norm:
            uf.union(by_norm[key], i)
        else:
            by_norm[key] = i

    # (2) 可选别名分组（外部信号，如 LLM）
    for group in alias_groups or []:
        valid = [i for i in group if isinstance(i, int) and 0 <= i < n]
        for j in valid[1:]:
            uf.union(valid[0], j)

    # 收集簇
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(uf.find(i), []).append(i)

    canonical_nodes: NodeList = []
    remap: dict[str, str] = {}  # 别名 uuid -> 规范 uuid
    merged_count = 0

    for members in clusters.values():
        if len(members) == 1:
            canonical_nodes.append(nodes[members[0]])
            continue

        # 规范节点：度数最高 → 名称最长 → 下标最小（稳定）
        canon_i = max(members, key=lambda i: (degree[i], len(nodes[i].get("name") or ""), -i))
        canon = dict(nodes[canon_i])
        canon["attributes"] = dict(canon.get("attributes") or {})

        # 类型裁决：按各成员度数汇总，取度数最高的本体类型（度数全 0 时取出现最多）
        type_weight: Counter[str] = Counter()
        for i in members:
            type_weight[_node_type(nodes[i])] += degree[i]
        chosen_type = (
            type_weight.most_common(1)[0][0]
            if any(type_weight.values())
            else Counter(_node_type(nodes[i]) for i in members).most_common(1)[0][0]
        )
        canon["labels"] = ["Entity", chosen_type]
        canon["attributes"]["ontology_type"] = chosen_type

        aliases = set(canon["attributes"].get("aliases") or [])
        summary_parts = [canon.get("summary") or ""]

        for i in members:
            if i == canon_i:
                continue
            other = nodes[i]
            remap[other["uuid"]] = canon["uuid"]
            merged_count += 1
            name = other.get("name")
            if name:
                aliases.add(name)
            # 别名节点已有的别名也并入
            aliases.update((other.get("attributes") or {}).get("aliases") or [])
            if other.get("summary"):
                summary_parts.append(other["summary"])
            # 属性填空：规范节点缺失的字段用别名补齐，不覆盖已有值
            for k, v in (other.get("attributes") or {}).items():
                if k == "aliases":
                    continue
                canon["attributes"].setdefault(k, v)

        # 合并摘要（去重保序，截断）
        seen_lines: set[str] = set()
        merged_summary: list[str] = []
        for part in summary_parts:
            for line in str(part).split("\n"):
                line = line.strip()
                if line and line not in seen_lines:
                    seen_lines.add(line)
                    merged_summary.append(line)
        canon["summary"] = "\n".join(merged_summary)[:2000]

        alias_list = sorted(a for a in aliases if a and a != canon.get("name"))
        if alias_list:
            canon["attributes"]["aliases"] = alias_list
        canonical_nodes.append(canon)

    # 边重指向规范 uuid，丢弃合并产生的自环，按 (源, 类型, 目标) 去重
    new_edges: EdgeList = []
    seen_edges: set[tuple[str, str, str]] = set()
    dropped = 0
    for edge in edges:
        src = remap.get(edge["source_node_uuid"], edge["source_node_uuid"])
        tgt = remap.get(edge["target_node_uuid"], edge["target_node_uuid"])
        if src == tgt:
            dropped += 1
            continue
        key = (src, edge.get("name", ""), tgt)
        if key in seen_edges:
            dropped += 1
            continue
        seen_edges.add(key)
        new_edges.append({**edge, "source_node_uuid": src, "target_node_uuid": tgt})

    stats.update(
        merged_nodes=merged_count,
        canonical_nodes=len(canonical_nodes),
        dropped_edges=dropped,
    )
    return canonical_nodes, new_edges, stats
