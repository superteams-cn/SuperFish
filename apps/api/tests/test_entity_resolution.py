"""通用实体消解算法的单元测试（不依赖 图谱存储 / LLM，名称为抽象占位符）。"""

from app.services.entity_resolution import (
    candidate_clusters,
    normalize_name,
    resolve_entities,
    unambiguous_containment_groups,
)


def _node(uuid, name, type_, summary="", attrs=None):
    a = {"ontology_type": type_}
    a.update(attrs or {})
    return {
        "uuid": uuid,
        "name": name,
        "labels": ["Entity", type_],
        "summary": summary,
        "attributes": a,
    }


def _edge(uuid, name, src, tgt):
    return {
        "uuid": uuid,
        "name": name,
        "fact": f"{src}-{name}-{tgt}",
        "source_node_uuid": src,
        "target_node_uuid": tgt,
        "attributes": {},
    }


def test_normalize_name_handles_width_case_and_space():
    # 全角/半角、大小写、首尾与内部空白都应归一到同一键
    assert normalize_name("  Ｈｅｌｌｏ  World ") == normalize_name("hello world")
    assert normalize_name("ABC") == normalize_name("abc")


def test_merges_same_name_across_different_types():
    """同名但被抽成不同类型的节点应跨类型合并（核心场景）。"""
    nodes = [
        _node("a", "X", "TypeA", summary="s1"),
        _node("b", "X", "TypeB", summary="s2"),
        _node("c", "X", "TypeC"),
        _node("d", "Y", "TypeA"),
    ]
    edges = [
        _edge("e1", "rel", "a", "d"),
        _edge("e2", "rel", "b", "d"),  # 指向别名 b → 应重指向规范节点
        _edge("e3", "rel", "c", "d"),
    ]
    new_nodes, new_edges, stats = resolve_entities(nodes, edges)

    assert stats["merged_nodes"] == 2
    assert stats["canonical_nodes"] == 2  # 合并后的 X + 独立的 Y
    names = sorted(n["name"] for n in new_nodes)
    assert names == ["X", "Y"]

    x = next(n for n in new_nodes if n["name"] == "X")
    # 类型按度数裁决：a/b/c 各 1 度 → 取出现最多/稳定者，且为单一类型
    assert x["attributes"]["ontology_type"] == x["labels"][1]
    # 摘要合并保留两段
    assert "s1" in x["summary"] and "s2" in x["summary"]

    # 三条边都应指向同一个规范 X，且去重后保留（同 rel 但被去重为 1 条）
    x_uuid = x["uuid"]
    assert all(e["source_node_uuid"] == x_uuid for e in new_edges)
    assert len(new_edges) == 1  # 三条 (X)-rel->(Y) 去重为一条


def test_alias_groups_merge_distinct_names():
    """字面不同的别名靠外部 alias_groups（如 LLM）合并。"""
    nodes = [
        _node("a", "Full Name", "T", summary="canon"),
        _node("b", "Nick", "T"),
        _node("c", "Other", "T"),
    ]
    edges = [_edge("e1", "rel", "b", "c")]
    # 下标 0 与 1 是同一实体
    new_nodes, new_edges, stats = resolve_entities(nodes, edges, alias_groups=[[0, 1]])

    assert stats["canonical_nodes"] == 2
    assert stats["merged_nodes"] == 1
    # 规范节点取度数更高的 "Nick"，"Full Name" 进入别名
    merged = next(n for n in new_nodes if n["name"] == "Nick")
    assert "Full Name" in (merged["attributes"].get("aliases") or [])
    # 边 b->c 重指向后仍存在且非自环
    assert len(new_edges) == 1


def test_canonical_prefers_higher_degree_node():
    """规范节点优先取关系度数更高者。"""
    nodes = [
        _node("low", "Z", "T"),
        _node("high", "Z", "T"),
    ]
    # high 有 2 条边，low 有 0 条
    edges = [
        _edge("e1", "rel", "high", "low"),  # 合并后自环 → 丢弃
        _edge("e2", "rel2", "high", "high"),
    ]
    new_nodes, new_edges, stats = resolve_entities(nodes, edges)
    assert stats["canonical_nodes"] == 1
    assert new_nodes[0]["uuid"] == "high"


def test_drops_self_loops_and_duplicate_edges():
    nodes = [_node("a", "X", "T"), _node("b", "X", "T"), _node("c", "Y", "T")]
    edges = [
        _edge("e1", "rel", "a", "b"),  # 合并后 a,b 同体 → 自环丢弃
        _edge("e2", "rel", "a", "c"),
        _edge("e3", "rel", "b", "c"),  # 与 e2 合并后重复 → 去重
    ]
    new_nodes, new_edges, stats = resolve_entities(nodes, edges)
    assert stats["canonical_nodes"] == 2
    assert len(new_edges) == 1
    assert stats["dropped_edges"] == 2


def test_candidate_clusters_links_substring_aliases():
    """子串型别名进入同一候选簇（供 LLM 裁决），无关实体不入簇；结果确定可复现。"""
    nodes = [
        _node("a", "Wukong", "T"),
        _node("a2", "SunWukong", "T"),  # 包含 "wukong"
        _node("z", "Unrelated", "T"),
    ]
    clusters = candidate_clusters(nodes)
    assert any({nodes[i]["name"] for i in cl} == {"Wukong", "SunWukong"} for cl in clusters)
    assert all("Unrelated" not in {nodes[i]["name"] for i in cl} for cl in clusters)
    assert candidate_clusters(nodes) == clusters  # 纯函数，稳定


def test_candidate_clusters_prunes_generic_substring_by_frequency():
    """高频子串(通用称谓)按频率剔除，不把众多实体卷进一个巨簇。"""
    nodes = [_node(f"n{i}", f"Aldr{i}Lord", "T") for i in range(8)]
    nodes.append(_node("bare", "Lord", "T"))
    clusters = candidate_clusters(nodes, df_max=4)
    # "Lord" 的 df 很高 → 不因它而把所有 *Lord 互联
    assert all(len(cl) < len(nodes) for cl in clusters)


def test_unambiguous_containment_merges_single_container_only():
    """唯一容器子串确定性合并；被多个不同名共享的子串(歧义)不动，绝不误并。"""
    nodes = [
        _node("a", "Aoguang", "T"),  # 仅被 DragonAoguang 包含 → 合并
        _node("b", "DragonAoguang", "T"),
        _node("k", "King", "T"),  # 被三个不同名包含 → 歧义，不合并
        _node("k1", "FireKing", "T"),
        _node("k2", "WaterKing", "T"),
        _node("k3", "WindKing", "T"),
    ]
    groups = unambiguous_containment_groups(nodes)
    merged = {frozenset(nodes[i]["name"] for i in g) for g in groups}
    assert frozenset({"Aoguang", "DragonAoguang"}) in merged
    # King 不应把三个不同的 *King 合并
    assert all("King" not in {nodes[i]["name"] for i in g} for g in groups)
    # 确定性：可复现
    assert unambiguous_containment_groups(nodes) == groups


def test_candidate_clusters_groups_fuzzy_bigram_variants():
    """字根高度重叠的写法差异进入候选簇（供 LLM 裁决），无关实体不入簇。"""
    nodes = [
        _node("a", "Heavenking", "T"),
        _node("b", "Heavenkingg", "T"),  # 与 Heavenking 高度重叠的写法变体
        _node("z", "Totallyother", "T"),
    ]
    clusters = candidate_clusters(nodes)
    assert any({nodes[i]["name"] for i in cl} == {"Heavenking", "Heavenkingg"} for cl in clusters)
    assert all("Totallyother" not in {nodes[i]["name"] for i in cl} for cl in clusters)


def test_noop_when_nothing_to_merge():
    nodes = [_node("a", "A", "T"), _node("b", "B", "T")]
    edges = [_edge("e1", "rel", "a", "b")]
    new_nodes, new_edges, stats = resolve_entities(nodes, edges)
    assert stats["merged_nodes"] == 0
    assert len(new_nodes) == 2
    assert len(new_edges) == 1
