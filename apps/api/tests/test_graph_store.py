"""图谱 Postgres 存储后端测试：写整张图 → 读/搜/单点 → 删 的往返。

需要 Postgres（conftest 已建表）。验证 write_graph 的规范化与边名富集、各读取函数形状、
应用层搜索打分、删除。
"""

import uuid

import pytest

from app.repositories.graph_repo import GraphRepository
from app.utils.graph_store import (
    GraphStore,
    delete_group,
    fetch_all_edges,
    fetch_all_nodes,
    fetch_node,
    fetch_node_edges,
    run_async,
)


@pytest.fixture
def graph(tmp_path):
    gid = f"g_test_{uuid.uuid4().hex[:10]}"
    nodes = [
        {"uuid": "n1", "name": "周瑜", "summary": "东吴大都督", "type": "PERSON", "attributes": {"k": 1}},
        {"uuid": "n2", "name": "诸葛亮", "summary": "蜀汉丞相", "labels": ["Entity", "PERSON"]},
        {"uuid": "n3", "name": "赤壁", "summary": "古战场"},
    ]
    edges = [
        {"uuid": "e1", "name": "对战", "fact": "周瑜与诸葛亮联手", "source_node_uuid": "n1", "target_node_uuid": "n2"},
        {"uuid": "e2", "name": "发生地", "fact": "战于赤壁", "source_node_uuid": "n1", "target_node_uuid": "n3"},
    ]
    GraphStore().write_graph(gid, nodes, edges, user_id="u_test")
    yield gid
    GraphRepository.delete(gid)


def test_write_normalizes_and_enriches(graph):
    nodes = fetch_all_nodes(None, graph)
    edges = fetch_all_edges(None, graph)
    assert len(nodes) == 3 and len(edges) == 2

    # 节点形状 + 标签规范化（Entity + 类型）
    n1 = next(n for n in nodes if n["uuid"] == "n1")
    assert n1["name"] == "周瑜"
    assert n1["labels"] == ["Entity", "PERSON"]
    assert n1["attributes"] == {"k": 1}

    # 边富集了 source/target 名（读取期无需再 join）
    e1 = next(e for e in edges if e["uuid"] == "e1")
    assert e1["source_node_name"] == "周瑜"
    assert e1["target_node_name"] == "诸葛亮"


def test_fetch_node_and_node_edges(graph):
    assert fetch_node(graph, "n1")["name"] == "周瑜"
    assert fetch_node(graph, "nope") is None
    # n1 关联 e1、e2
    assert {e["uuid"] for e in fetch_node_edges(graph, "n1")} == {"e1", "e2"}
    # n2 只在 e1 中
    assert {e["uuid"] for e in fetch_node_edges(graph, "n2")} == {"e1"}


def test_search_scores_within_graph(graph):
    res = run_async(GraphStore().search("赤壁", group_ids=[graph], num_results=10))
    assert any(r.fact and "赤壁" in r.fact for r in res)
    # 空 group_ids 不跨租户全表扫，直接空
    assert run_async(GraphStore().search("赤壁", group_ids=[])) == []


def test_write_replaces_whole_graph(graph):
    # 再写一次（更小的集）应整张替换，而非累加
    GraphStore().write_graph(
        graph,
        [{"uuid": "n9", "name": "鲁肃", "summary": "", "type": "PERSON"}],
        [],
    )
    nodes = fetch_all_nodes(None, graph)
    assert [n["uuid"] for n in nodes] == ["n9"]


def test_delete_group(graph):
    delete_group(None, graph)
    assert fetch_all_nodes(None, graph) == []
    assert not GraphRepository.exists(graph)
