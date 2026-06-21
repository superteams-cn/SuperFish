"""ReACT 工具调用解析的特征测试（守护对 LLM 输出格式敏感的启发式解析）。

覆盖 react_parser.parse_tool_calls / is_valid_tool_call 的全部分支：XML 标签 /
裸 JSON / 思考文字+末尾 JSON / 键名规范化 / 非法工具名 / 坏 JSON。
"""

from app.services.report import react_parser

VALID = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}


def test_parse_xml_tagged_single():
    resp = '前缀思考<tool_call>{"name": "quick_search", "parameters": {"q": "x"}}</tool_call>'
    calls = react_parser.parse_tool_calls(resp, VALID)
    assert calls == [{"name": "quick_search", "parameters": {"q": "x"}}]


def test_parse_xml_tagged_multiple():
    resp = (
        '<tool_call>{"name": "quick_search", "parameters": {}}</tool_call>'
        '<tool_call>{"name": "panorama_search", "parameters": {}}</tool_call>'
    )
    calls = react_parser.parse_tool_calls(resp, VALID)
    assert [c["name"] for c in calls] == ["quick_search", "panorama_search"]


def test_xml_takes_priority_and_skips_bad_json_entries():
    # 第一个 JSON 坏掉被跳过，第二个有效仍被收集
    resp = (
        "<tool_call>{bad json}</tool_call>"
        '<tool_call>{"name": "insight_forge", "parameters": {}}</tool_call>'
    )
    calls = react_parser.parse_tool_calls(resp, VALID)
    assert calls == [{"name": "insight_forge", "parameters": {}}]


def test_parse_bare_json_whole_response():
    resp = '{"name": "insight_forge", "parameters": {"topic": "t"}}'
    calls = react_parser.parse_tool_calls(resp, VALID)
    assert calls == [{"name": "insight_forge", "parameters": {"topic": "t"}}]


def test_bare_json_invalid_tool_name_rejected():
    resp = '{"name": "not_a_tool", "parameters": {}}'
    assert react_parser.parse_tool_calls(resp, VALID) == []


def test_parse_trailing_json_after_thinking_text():
    resp = '我需要先搜索一下相关信息。\n{"name": "quick_search", "parameters": {"q": "y"}}'
    calls = react_parser.parse_tool_calls(resp, VALID)
    assert calls == [{"name": "quick_search", "parameters": {"q": "y"}}]


def test_key_normalization_tool_and_params():
    # {"tool", "params"} 应被规范化为 {"name", "parameters"}
    resp = '{"tool": "panorama_search", "params": {"k": 1}}'
    calls = react_parser.parse_tool_calls(resp, VALID)
    assert calls == [{"name": "panorama_search", "parameters": {"k": 1}}]


def test_final_answer_text_yields_no_tool_calls():
    resp = "Final Answer: 这是最终的章节正文，不包含任何工具调用。"
    assert react_parser.parse_tool_calls(resp, VALID) == []


def test_malformed_trailing_json_returns_empty():
    resp = '思考中……{"name": "quick_search", "parameters": {'  # 截断的 JSON
    assert react_parser.parse_tool_calls(resp, VALID) == []


def test_is_valid_tool_call_normalizes_in_place():
    data = {"tool": "quick_search", "params": {"q": "z"}}
    assert react_parser.is_valid_tool_call(data, VALID) is True
    assert data["name"] == "quick_search"
    assert data["parameters"] == {"q": "z"}
    assert "tool" not in data and "params" not in data


def test_is_valid_tool_call_rejects_unknown():
    assert react_parser.is_valid_tool_call({"name": "bogus"}, VALID) is False
    assert react_parser.is_valid_tool_call({}, VALID) is False
