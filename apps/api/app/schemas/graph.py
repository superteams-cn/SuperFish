"""
图谱相关接口的 Pydantic 模型
"""

from pydantic import BaseModel, Field


class BuildGraphRequest(BaseModel):
    """构建图谱请求体（接口2）

    注意：project_id 设为可选，由处理器手动校验并返回本地化 400，
    与 report/simulation 的契约保持一致（避免 FastAPI 默认的 422）。
    """

    project_id: str | None = Field(default=None, description="项目ID，来自本体生成接口")
    graph_name: str | None = Field(default=None, description="图谱名称，缺省用项目名")
    chunk_size: int | None = Field(default=None, description="文本分块大小")
    chunk_overlap: int | None = Field(default=None, description="分块重叠长度")
    force: bool = Field(default=False, description="是否强制重新构建")
