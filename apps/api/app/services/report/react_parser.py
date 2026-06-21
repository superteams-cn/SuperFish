"""ReACT 工具调用解析：从 LLM 自由文本响应中抽取工具调用 JSON。

从 ReportAgent 抽出为纯函数（输入响应文本 + 合法工具名集合，输出工具调用列表），
便于独立测试这套对 LLM 输出格式敏感、易随模型漂移的启发式解析。ReportAgent 以薄委托调用。

解析按优先级容三种格式：
1. ``<tool_call>{...}</tool_call>`` XML 标签（标准）；
2. 整体就是一个裸 JSON 对象（无标签）；
3. 思考文字 + 末尾裸 JSON（提取最后一个 ``{"name"|"tool": ...}``）。
"""

import json
import re
from typing import Any

_XML_PATTERN = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
_TRAILING_JSON_PATTERN = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'


def is_valid_tool_call(data: dict, valid_tool_names: set[str]) -> bool:
    """校验解析出的 JSON 是否是合法工具调用，并就地规范化键名。

    支持 ``{"name", "parameters"}`` 与 ``{"tool", "params"}`` 两种键名；命中合法工具名时
    把 tool→name、params→parameters 统一（就地修改 data），返回 True。
    """
    tool_name = data.get("name") or data.get("tool")
    if tool_name and tool_name in valid_tool_names:
        # 统一键名为 name / parameters
        if "tool" in data:
            data["name"] = data.pop("tool")
        if "params" in data and "parameters" not in data:
            data["parameters"] = data.pop("params")
        return True
    return False


def parse_tool_calls(response: str, valid_tool_names: set[str]) -> list[dict[str, Any]]:
    """从 LLM 响应中解析工具调用列表（容三种格式，见模块 docstring）。"""
    tool_calls = []

    # 格式1: XML风格（标准格式）
    for match in re.finditer(_XML_PATTERN, response, re.DOTALL):
        try:
            call_data = json.loads(match.group(1))
            tool_calls.append(call_data)
        except json.JSONDecodeError:
            pass

    if tool_calls:
        return tool_calls

    # 格式2: 兜底 - LLM 直接输出裸 JSON（没包 <tool_call> 标签）
    # 只在格式1未匹配时尝试，避免误匹配正文中的 JSON
    stripped = response.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            call_data = json.loads(stripped)
            if is_valid_tool_call(call_data, valid_tool_names):
                tool_calls.append(call_data)
                return tool_calls
        except json.JSONDecodeError:
            pass

    # 响应可能包含思考文字 + 裸 JSON，尝试提取最后一个 JSON 对象
    match = re.search(_TRAILING_JSON_PATTERN, stripped, re.DOTALL)
    if match:
        try:
            call_data = json.loads(match.group(1))
            if is_valid_tool_call(call_data, valid_tool_names):
                tool_calls.append(call_data)
        except json.JSONDecodeError:
            pass

    return tool_calls
