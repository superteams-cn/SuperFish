"""
报告相关接口的 Pydantic 模型

说明：必填字段在原 Flask 实现中是手动校验并返回本地化的 400 错误，
为保持前端契约一致，这里字段统一设为可选、在处理器内手动校验，
避免 FastAPI 默认抛出 422（结构不同的错误体）。
"""

from typing import Any

from pydantic import BaseModel, Field


class GenerateReportRequest(BaseModel):
    """生成报告请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID")
    force_regenerate: bool = Field(default=False, description="是否强制重新生成")


class GenerateStatusRequest(BaseModel):
    """查询报告生成进度请求体"""

    task_id: str | None = Field(default=None, description="任务ID")
    simulation_id: str | None = Field(default=None, description="模拟ID")


class ChatRequest(BaseModel):
    """与 Report Agent 对话请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID")
    message: str | None = Field(default=None, description="用户消息")
    chat_history: list[dict[str, Any]] = Field(default_factory=list, description="对话历史")


class SearchToolRequest(BaseModel):
    """图谱搜索工具请求体（调试用）"""

    graph_id: str | None = Field(default=None, description="图谱ID")
    query: str | None = Field(default=None, description="搜索查询")
    limit: int = Field(default=10, description="返回数量上限")


class StatisticsToolRequest(BaseModel):
    """图谱统计工具请求体（调试用）"""

    graph_id: str | None = Field(default=None, description="图谱ID")
