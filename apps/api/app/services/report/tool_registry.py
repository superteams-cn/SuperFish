"""报告 Agent 的工具注册与分派。

从 ReportAgent 抽出：工具定义（define_tools）、描述文本（tools_description）、合法工具名
集合（VALID_TOOL_NAMES）、以及把工具调用分派到 GraphToolsService 的执行器（execute_tool）。
execute_tool 以显式参数接收依赖（graph_tools + 三个运行上下文）而非 self，便于独立测试。
ReportAgent 以薄委托调用本模块。
"""

import json
from typing import Any

from ...core.logger import get_logger
from ...utils.locale import t
from ..graph_tools import GraphToolsService
from .prompts import (
    TOOL_DESC_INSIGHT_FORGE,
    TOOL_DESC_INTERVIEW_AGENTS,
    TOOL_DESC_PANORAMA_SEARCH,
    TOOL_DESC_QUICK_SEARCH,
)

logger = get_logger("superfish.report.tools")

# 合法的工具名称集合，用于裸 JSON 兜底解析时校验
VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}


def define_tools() -> dict[str, dict[str, Any]]:
    """定义可用工具（名称 → {name, description, parameters}）。"""
    return {
        "insight_forge": {
            "name": "insight_forge",
            "description": TOOL_DESC_INSIGHT_FORGE,
            "parameters": {
                "query": "你想深入分析的问题或话题",
                "report_context": "当前报告章节的上下文（可选，有助于生成更精准的子问题）",
            },
        },
        "panorama_search": {
            "name": "panorama_search",
            "description": TOOL_DESC_PANORAMA_SEARCH,
            "parameters": {
                "query": "搜索查询，用于相关性排序",
                "include_expired": "是否包含过期/历史内容（默认True）",
            },
        },
        "quick_search": {
            "name": "quick_search",
            "description": TOOL_DESC_QUICK_SEARCH,
            "parameters": {"query": "搜索查询字符串", "limit": "返回结果数量（可选，默认10）"},
        },
        "interview_agents": {
            "name": "interview_agents",
            "description": TOOL_DESC_INTERVIEW_AGENTS,
            "parameters": {
                "interview_topic": "采访主题或需求描述（如：'了解学生对宿舍甲醛事件的看法'）",
                "max_agents": "最多采访的Agent数量（可选，默认5，最大10）",
            },
        },
    }


def tools_description(tools: dict[str, dict[str, Any]]) -> str:
    """生成工具描述文本。"""
    desc_parts = ["可用工具："]
    for name, tool in tools.items():
        params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
        desc_parts.append(f"- {name}: {tool['description']}")
        if params_desc:
            desc_parts.append(f"  参数: {params_desc}")
    return "\n".join(desc_parts)


def execute_tool(
    graph_tools: GraphToolsService,
    *,
    graph_id: str,
    simulation_id: str,
    simulation_requirement: str,
    tool_name: str,
    parameters: dict[str, Any],
    report_context: str = "",
) -> str:
    """执行一次工具调用，返回文本结果。

    把 tool_name 分派到 GraphToolsService 的对应方法；含若干向后兼容旧工具名的内部重定向。
    任何异常都被吞为「工具执行失败: ...」文本（ReACT 循环据此自愈）。
    """
    logger.info(t("report.executingTool", toolName=tool_name, params=parameters))

    def _redirect(new_name: str, params: dict[str, Any]) -> str:
        return execute_tool(
            graph_tools,
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement,
            tool_name=new_name,
            parameters=params,
            report_context=report_context,
        )

    try:
        if tool_name == "insight_forge":
            query = parameters.get("query", "")
            ctx = parameters.get("report_context", "") or report_context
            result = graph_tools.insight_forge(
                graph_id=graph_id,
                query=query,
                simulation_requirement=simulation_requirement,
                report_context=ctx,
            )
            return result.to_text()

        elif tool_name == "panorama_search":
            # 广度搜索 - 获取全貌
            query = parameters.get("query", "")
            include_expired = parameters.get("include_expired", True)
            if isinstance(include_expired, str):
                include_expired = include_expired.lower() in ["true", "1", "yes"]
            result = graph_tools.panorama_search(
                graph_id=graph_id, query=query, include_expired=include_expired
            )
            return result.to_text()

        elif tool_name == "quick_search":
            # 简单搜索 - 快速检索
            query = parameters.get("query", "")
            limit = parameters.get("limit", 10)
            if isinstance(limit, str):
                limit = int(limit)
            result = graph_tools.quick_search(graph_id=graph_id, query=query, limit=limit)
            return result.to_text()

        elif tool_name == "interview_agents":
            # 深度采访 - 调用真实的OASIS采访API获取模拟Agent的回答（双平台）
            interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
            max_agents = parameters.get("max_agents", 5)
            if isinstance(max_agents, str):
                max_agents = int(max_agents)
            max_agents = min(max_agents, 10)
            result = graph_tools.interview_agents(
                simulation_id=simulation_id,
                interview_requirement=interview_topic,
                simulation_requirement=simulation_requirement,
                max_agents=max_agents,
            )
            return result.to_text()

        # ========== 向后兼容的旧工具（内部重定向到新工具） ==========

        elif tool_name == "search_graph":
            # 重定向到 quick_search
            logger.info(t("report.redirectToQuickSearch"))
            return _redirect("quick_search", parameters)

        elif tool_name == "get_graph_statistics":
            result = graph_tools.get_graph_statistics(graph_id)
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "get_entity_summary":
            entity_name = parameters.get("entity_name", "")
            result = graph_tools.get_entity_summary(graph_id=graph_id, entity_name=entity_name)
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "get_simulation_context":
            # 重定向到 insight_forge，因为它更强大
            logger.info(t("report.redirectToInsightForge"))
            query = parameters.get("query", simulation_requirement)
            return _redirect("insight_forge", {"query": query})

        elif tool_name == "get_entities_by_type":
            entity_type = parameters.get("entity_type", "")
            nodes = graph_tools.get_entities_by_type(graph_id=graph_id, entity_type=entity_type)
            result = [n.to_dict() for n in nodes]
            return json.dumps(result, ensure_ascii=False, indent=2)

        else:
            return f"未知工具: {tool_name}。请使用以下工具之一: insight_forge, panorama_search, quick_search"

    except Exception as e:
        logger.error(t("report.toolExecFailed", toolName=tool_name, error=str(e)))
        return f"工具执行失败: {str(e)}"
