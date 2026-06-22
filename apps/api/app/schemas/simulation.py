"""
模拟相关接口的 Pydantic 模型

说明：必填字段在迁移前的实现中是手动校验并返回本地化的 400 错误，
为保持前端契约一致，这里字段统一设为可选、在处理器内手动校验，
避免 FastAPI 默认抛出 422（结构不同的错误体）。
"""

from typing import Any

from pydantic import BaseModel, Field


class CreateSimulationRequest(BaseModel):
    """创建模拟请求体"""

    project_id: str | None = Field(default=None, description="项目ID，必填")
    graph_id: str | None = Field(default=None, description="图谱ID，可选，缺省从项目获取")
    enable_twitter: bool = Field(default=True, description="是否启用 Twitter")
    enable_reddit: bool = Field(default=True, description="是否启用 Reddit")


class PrepareSimulationRequest(BaseModel):
    """准备模拟环境请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID，必填")
    entity_types: list[str] | None = Field(default=None, description="指定实体类型，可选")
    use_llm_for_profiles: bool = Field(default=True, description="是否用 LLM 生成人设")
    parallel_profile_count: int = Field(default=5, description="并行生成人设数量")
    force_regenerate: bool = Field(default=False, description="是否强制重新生成")


class PrepareStatusRequest(BaseModel):
    """查询准备任务进度请求体"""

    task_id: str | None = Field(default=None, description="准备返回的任务ID，可选")
    simulation_id: str | None = Field(default=None, description="模拟ID，可选")


class GenerateProfilesRequest(BaseModel):
    """直接从图谱生成 Agent Profile 请求体（不创建模拟）"""

    graph_id: str | None = Field(default=None, description="图谱ID，必填")
    entity_types: list[str] | None = Field(default=None, description="指定实体类型，可选")
    use_llm: bool = Field(default=True, description="是否用 LLM 生成人设")
    platform: str = Field(default="reddit", description="平台类型")


class StartSimulationRequest(BaseModel):
    """开始运行模拟请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID，必填")
    platform: str = Field(default="parallel", description="平台: twitter / reddit / parallel")
    max_rounds: Any | None = Field(default=None, description="最大模拟轮数，可选")
    enable_graph_memory_update: bool = Field(
        default=False, description="是否将 Agent 活动更新到 图谱记忆"
    )
    force: bool = Field(default=False, description="是否强制重新开始")


class StopSimulationRequest(BaseModel):
    """停止模拟请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID，必填")


class BranchSimulationRequest(BaseModel):
    """剧本推演分支请求体（从某个节拍处分叉 + 上帝视角注入变量）。"""

    simulation_id: str | None = Field(default=None, description="父推演ID，必填")
    from_seq: int = Field(default=-1, description="分支点 beat seq（含），-1 表示从末尾分叉")
    injection: str = Field(default="", description="上帝视角注入的变量/事件，可选")
    label: str = Field(default="", description="分支备注，可选")


class InterviewAgentRequest(BaseModel):
    """采访单个 Agent 请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID，必填")
    agent_id: Any | None = Field(default=None, description="Agent ID，必填")
    prompt: str | None = Field(default=None, description="采访问题，必填")
    platform: str | None = Field(default=None, description="指定平台（twitter/reddit），可选")
    timeout: int = Field(default=60, description="超时时间（秒）")


class InterviewBatchRequest(BaseModel):
    """批量采访多个 Agent 请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID，必填")
    interviews: list[dict[str, Any]] | None = Field(default=None, description="采访列表，必填")
    platform: str | None = Field(default=None, description="默认平台（twitter/reddit），可选")
    timeout: int = Field(default=120, description="超时时间（秒）")


class InterviewAllRequest(BaseModel):
    """全局采访所有 Agent 请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID，必填")
    prompt: str | None = Field(default=None, description="采访问题，必填")
    platform: str | None = Field(default=None, description="指定平台（twitter/reddit），可选")
    timeout: int = Field(default=180, description="超时时间（秒）")


class InterviewHistoryRequest(BaseModel):
    """获取 Interview 历史记录请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID，必填")
    platform: str | None = Field(default=None, description="平台类型（reddit/twitter），可选")
    agent_id: Any | None = Field(default=None, description="只获取该 Agent 的采访历史，可选")
    limit: int = Field(default=100, description="返回数量")


class EnvStatusRequest(BaseModel):
    """获取模拟环境状态请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID，必填")


class CloseEnvRequest(BaseModel):
    """关闭模拟环境请求体"""

    simulation_id: str | None = Field(default=None, description="模拟ID，必填")
    timeout: int = Field(default=30, description="超时时间（秒）")
