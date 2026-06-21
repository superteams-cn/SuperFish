"""report/tool_registry 的测试：工具定义、描述文本、以及到 GraphToolsService 的分派。

execute_tool 用记录调用的假 graph_tools 隔离真实检索，验证路由/参数透传/类型强转/
旧工具重定向/未知工具/异常吞没。
"""

from app.services.report import tool_registry


class _Result:
    def __init__(self, text: str):
        self._text = text

    def to_text(self) -> str:
        return self._text


class _FakeGraphTools:
    """记录每次调用的工具替身。"""

    def __init__(self):
        self.calls: list[tuple] = []

    def insight_forge(self, **kw):
        self.calls.append(("insight_forge", kw))
        return _Result("insight-result")

    def panorama_search(self, **kw):
        self.calls.append(("panorama_search", kw))
        return _Result("panorama-result")

    def quick_search(self, **kw):
        self.calls.append(("quick_search", kw))
        return _Result("quick-result")

    def interview_agents(self, **kw):
        self.calls.append(("interview_agents", kw))
        return _Result("interview-result")

    def get_graph_statistics(self, graph_id):
        self.calls.append(("get_graph_statistics", graph_id))
        return {"total_nodes": 1}


def _exec(gt, tool_name, parameters, **ctx):
    base = dict(
        graph_id="g1",
        simulation_id="s1",
        simulation_requirement="预测舆情",
    )
    base.update(ctx)
    return tool_registry.execute_tool(gt, tool_name=tool_name, parameters=parameters, **base)


def test_define_tools_shape():
    tools = tool_registry.define_tools()
    assert set(tools) == tool_registry.VALID_TOOL_NAMES
    for name, spec in tools.items():
        assert spec["name"] == name
        assert spec["description"]
        assert isinstance(spec["parameters"], dict)


def test_tools_description_lists_every_tool():
    desc = tool_registry.tools_description(tool_registry.define_tools())
    assert desc.startswith("可用工具：")
    for name in tool_registry.VALID_TOOL_NAMES:
        assert name in desc


def test_execute_insight_forge_passes_context():
    gt = _FakeGraphTools()
    out = _exec(gt, "insight_forge", {"query": "q"}, report_context="ctx")
    assert out == "insight-result"
    name, kw = gt.calls[-1]
    assert name == "insight_forge"
    assert kw["graph_id"] == "g1"
    assert kw["query"] == "q"
    assert kw["report_context"] == "ctx"


def test_execute_quick_search_coerces_str_limit():
    gt = _FakeGraphTools()
    _exec(gt, "quick_search", {"query": "q", "limit": "3"})
    assert gt.calls[-1][1]["limit"] == 3


def test_execute_panorama_coerces_str_include_expired():
    gt = _FakeGraphTools()
    _exec(gt, "panorama_search", {"query": "q", "include_expired": "false"})
    assert gt.calls[-1][1]["include_expired"] is False


def test_execute_interview_caps_max_agents_at_10():
    gt = _FakeGraphTools()
    _exec(gt, "interview_agents", {"interview_topic": "t", "max_agents": "50"})
    assert gt.calls[-1][1]["max_agents"] == 10


def test_search_graph_redirects_to_quick_search():
    gt = _FakeGraphTools()
    out = _exec(gt, "search_graph", {"query": "q"})
    assert out == "quick-result"
    assert gt.calls[-1][0] == "quick_search"


def test_unknown_tool_returns_message():
    gt = _FakeGraphTools()
    out = _exec(gt, "no_such_tool", {})
    assert "未知工具" in out


def test_exception_is_swallowed_to_failure_text():
    class _Boom:
        def quick_search(self, **kw):
            raise RuntimeError("db down")

    out = _exec(_Boom(), "quick_search", {"query": "q"})
    assert out.startswith("工具执行失败")
    assert "db down" in out
