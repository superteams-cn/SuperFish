"""
图谱相关接口的 Pydantic 模型
"""

from typing import Optional

from pydantic import BaseModel, Field


class BuildGraphRequest(BaseModel):
    """构建图谱请求体（接口2）"""

    project_id: str = Field(..., description="项目ID，来自本体生成接口")
    graph_name: Optional[str] = Field(default=None, description="图谱名称，缺省用项目名")
    chunk_size: Optional[int] = Field(default=None, description="文本分块大小")
    chunk_overlap: Optional[int] = Field(default=None, description="分块重叠长度")
    force: bool = Field(default=False, description="是否强制重新构建")
