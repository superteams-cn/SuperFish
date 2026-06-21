"""
配置管理（pydantic-settings）

- 统一从仓库根目录的 .env 加载；真实环境变量优先级高于 .env（docker compose 注入的变量会生效）。
- 通过模块级单例 `settings` 访问，字段为小写蛇形，例如 settings.llm_api_key。
"""

from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 本文件位于 apps/api/app/core/settings.py。
# _API_DIR=apps/api（uploads 等运行期目录的基准），_REPO_ROOT=仓库根（.env 所在）。
_CORE_DIR = Path(__file__).resolve().parent  # apps/api/app/core
_APP_DIR = _CORE_DIR.parent  # apps/api/app（保留语义：app 目录）
_API_DIR = _CORE_DIR.parents[1]  # apps/api
_REPO_ROOT = _CORE_DIR.parents[3]  # 仓库根（SuperFish）


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 服务运行 =====
    debug: bool = Field(default=True, validation_alias="APP_DEBUG")
    host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    port: int = Field(default=5001, validation_alias="API_PORT")

    # ===== LLM（统一 OpenAI 格式）=====
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model_name: str = "gpt-4o-mini"
    llm_request_timeout: float = 120.0

    # ===== 本体生成 =====
    # 最大输出 token：推理类模型的思考过程也计入此预算，设小会截断 JSON 致解析失败。
    ontology_max_tokens: int = 16384
    # 实体类型总数（含「个人/组织」2 个兜底类型）；同时作为后处理硬上限。最小 3。
    ontology_entity_types: int = 10
    # 关系类型数量范围（提示词建议区间）；上限同时作为后处理硬截断。
    ontology_edge_types_min: int = 6
    ontology_edge_types_max: int = 10

    # ===== 图谱抽取 =====
    # 每个文本块的最大输出 token；块更大、三元组更多时需更高，避免 JSON 截断。
    graph_extract_max_tokens: int = 16384
    # LlamaIndex SchemaLLMPathExtractor 每个文本块最多抽取的三元组数量。
    graph_extract_max_triplets: int = 20

    # ===== 知识图谱 =====
    # 图谱存于 Postgres（见 graphs 表 / repositories/graph_repo.py），无需独立图数据库配置。

    # ===== 用户体系 / 鉴权（JWT）=====
    # 上线前务必通过环境变量 JWT_SECRET 覆盖为高强度随机值；默认值仅供本地开发。
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 30
    jwt_refresh_ttl_days: int = 14
    jwt_reset_ttl_min: int = 30
    # 邮箱验证令牌有效期（默认 24h）
    jwt_verify_ttl_min: int = 60 * 24

    # ===== P3 开放注册护栏 =====
    # admin 邮箱白名单（逗号分隔），命中者拥有运维接口权限（如 /admin/stop-all）
    admin_emails: str = ""
    # 单用户配额：项目总数 + 同时运行中的模拟数
    max_projects_per_user: int = 10
    max_concurrent_simulations: int = 2
    # 限流（Redis 滑动窗口）。注册/登录/找回密码/重发验证按 IP 与邮箱双维度限流
    rate_limit_enabled: bool = True
    rate_limit_register_per_hour: int = 10
    rate_limit_login_per_min: int = 10
    rate_limit_forgot_per_hour: int = 5
    rate_limit_resend_per_hour: int = 5

    # ===== 邮件发送（找回密码/邮箱验证）=====
    # 未配置 smtp_host 时走「开发桩」：邮件内容打印到后端日志，便于本地联调；
    # 上线只需配置 SMTP（或换第三方），业务代码无需改动。
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    # 直连 SSL（端口 465）还是 STARTTLS（端口 587）。留空时按端口自动判定（465→SSL）。
    smtp_use_ssl: bool | None = None
    # 是否启用 STARTTLS（仅在非 SSL 时有意义；个别内网无 TLS 的 SMTP 可置 false）
    smtp_use_tls: bool = True
    email_from: str = "SuperFish <no-reply@superfish.local>"
    # 用于拼接邮件里的重置链接（指向前端路由 /reset-password）
    web_base_url: str = "http://localhost:3000"

    # ===== Redis（缓存/队列）=====
    # 源码部署默认 localhost；docker compose 中由 compose 注入 redis://redis:6379/0
    redis_url: str = "redis://localhost:6379/0"

    # ===== Postgres（项目/任务等关系型元数据）=====
    database_url: str = "postgresql+psycopg://superfish:superfish_pg@localhost:5432/superfish"

    # ===== S3 兼容对象存储（RustFS）=====
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "superfish"
    s3_secret_key: str = "superfish_secret"
    s3_bucket: str = "superfish"
    s3_region: str = "us-east-1"

    # ===== 文件上传 =====
    max_content_length: int = 50 * 1024 * 1024  # 50MB
    upload_folder: str = str(_APP_DIR.parent / "uploads")
    allowed_extensions: set[str] = {"pdf", "md", "txt", "markdown"}

    # ===== 文本分块（大上下文模型可调大以减少分块数与跨块实体分裂）=====
    default_chunk_size: int = 5000
    default_chunk_overlap: int = 200

    # ===== OASIS 模拟 =====
    oasis_default_max_rounds: int = 10
    oasis_simulation_data_dir: str = str(_APP_DIR.parent / "uploads" / "simulations")
    oasis_twitter_actions: list[str] = [
        "CREATE_POST",
        "LIKE_POST",
        "REPOST",
        "FOLLOW",
        "DO_NOTHING",
        "QUOTE_POST",
    ]
    oasis_reddit_actions: list[str] = [
        "LIKE_POST",
        "DISLIKE_POST",
        "CREATE_POST",
        "CREATE_COMMENT",
        "LIKE_COMMENT",
        "DISLIKE_COMMENT",
        "SEARCH_POSTS",
        "SEARCH_USER",
        "TREND",
        "REFRESH",
        "DO_NOTHING",
        "FOLLOW",
        "MUTE",
    ]

    # ===== Report Agent =====
    report_agent_max_tool_calls: int = 5
    # 报告章节生成的最大输出 token；推理类模型思考过程亦计入，设小会截断正文。
    report_agent_max_tokens: int = 8192
    report_agent_max_reflection_rounds: int = 2
    report_agent_temperature: float = 0.5

    @field_validator("ontology_entity_types")
    @classmethod
    def _clamp_entity_types(cls, v: int) -> int:
        # 至少 1 个具体类型 + 2 个兜底类型
        return max(3, v)

    @field_validator("ontology_edge_types_min")
    @classmethod
    def _clamp_edge_min(cls, v: int) -> int:
        return max(1, v)

    @model_validator(mode="after")
    def _clamp_edge_max(self) -> "Settings":
        if self.ontology_edge_types_max < self.ontology_edge_types_min:
            self.ontology_edge_types_max = self.ontology_edge_types_min
        return self

    @property
    def admin_email_set(self) -> set[str]:
        """解析 admin_emails 为规范化（小写去空）邮箱集合。"""
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    def validate_required(self) -> list[str]:
        """验证必要配置，返回错误信息列表（空列表表示通过）。"""
        errors: list[str] = []
        if not self.llm_api_key:
            errors.append("LLM_API_KEY 未配置")
        return errors


# 模块级单例：全项目统一通过 `from .settings import settings` 访问
settings = Settings()
