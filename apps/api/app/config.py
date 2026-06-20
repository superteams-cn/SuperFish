"""
配置管理
统一从项目根目录的 .env 文件加载配置
"""

import os

from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
# 路径: SuperFish/.env (相对于 apps/api/app/config.py，需上溯三级到仓库根)
project_root_env = os.path.join(os.path.dirname(__file__), "../../../.env")

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv(override=True)


class Config:
    """Flask配置类"""

    # Flask配置
    SECRET_KEY = os.environ.get("SECRET_KEY", "superfish-secret-key")
    DEBUG = os.environ.get("FLASK_DEBUG", "True").lower() == "true"

    # JSON配置 - 禁用ASCII转义，让中文直接显示（而不是 \uXXXX 格式）
    JSON_AS_ASCII = False

    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get("LLM_API_KEY")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")
    LLM_REQUEST_TIMEOUT = float(os.environ.get("LLM_REQUEST_TIMEOUT", "120"))

    # 本体生成的最大输出token。推理类模型（如 deepseek-v4-pro）的思考过程也计入此预算，
    # 设得过小会导致 JSON 输出被截断、解析失败。默认 16384 留足余量。
    ONTOLOGY_MAX_TOKENS = int(os.environ.get("ONTOLOGY_MAX_TOKENS", "16384"))
    # 本体生成的实体类型总数（含「个人/组织」2 个兜底类型，故具体类型数 = 总数 - 2）。
    # 同时作为后处理硬上限：LLM 多给会从末尾截断，缺兜底会补齐。最小 3（至少 1 具体 + 2 兜底）。
    ONTOLOGY_ENTITY_TYPES = max(3, int(os.environ.get("ONTOLOGY_ENTITY_TYPES", "10")))
    # 本体生成的关系类型数量范围（提示词建议区间）；上限同时作为后处理硬截断。
    ONTOLOGY_EDGE_TYPES_MIN = max(1, int(os.environ.get("ONTOLOGY_EDGE_TYPES_MIN", "6")))
    ONTOLOGY_EDGE_TYPES_MAX = max(
        ONTOLOGY_EDGE_TYPES_MIN, int(os.environ.get("ONTOLOGY_EDGE_TYPES_MAX", "10"))
    )
    # 图谱抽取每个文本块的最大输出token。块更大、三元组更多时需更高,避免 JSON 被截断。
    GRAPH_EXTRACT_MAX_TOKENS = int(os.environ.get("GRAPH_EXTRACT_MAX_TOKENS", "16384"))
    # LlamaIndex SchemaLLMPathExtractor 每个文本块最多抽取的三元组数量。
    GRAPH_EXTRACT_MAX_TRIPLETS = int(os.environ.get("GRAPH_EXTRACT_MAX_TRIPLETS", "20"))

    # Neo4j 配置（schema 约束知识图谱）
    NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "superfish_neo4j")

    # Redis 配置（缓存/队列等，可选）
    # 源码部署默认 localhost；docker compose 中由 compose 注入 redis://redis:6379/0
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Postgres 配置（项目/任务等关系型元数据持久化，跨进程/重启/多副本共享）
    # 源码部署默认 localhost；docker compose 中由 compose 注入 postgres 服务名
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://superfish:superfish_pg@localhost:5432/superfish",
    )

    # S3 兼容对象存储（RustFS）配置（上传文件、提取文本等二进制/大文本持久化）
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "superfish")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "superfish_secret")
    S3_BUCKET = os.environ.get("S3_BUCKET", "superfish")
    S3_REGION = os.environ.get("S3_REGION", "us-east-1")

    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "../uploads")
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}

    # 文本处理配置（按大上下文模型调大，减少分块数与跨块实体分裂）
    # 默认切块大小（字符）。大上下文模型(deepseek 32k+)可调大以减少分块数。
    DEFAULT_CHUNK_SIZE = int(os.environ.get("DEFAULT_CHUNK_SIZE", "5000"))
    # 默认重叠大小（字符）。
    DEFAULT_CHUNK_OVERLAP = int(os.environ.get("DEFAULT_CHUNK_OVERLAP", "200"))

    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get("OASIS_DEFAULT_MAX_ROUNDS", "10"))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), "../uploads/simulations")

    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        "CREATE_POST",
        "LIKE_POST",
        "REPOST",
        "FOLLOW",
        "DO_NOTHING",
        "QUOTE_POST",
    ]
    OASIS_REDDIT_ACTIONS = [
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

    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get("REPORT_AGENT_MAX_TOOL_CALLS", "5"))
    # 报告章节生成的最大输出token。推理类模型的思考过程也计入此预算，
    # 设得过小会导致正文被截断。默认 8192。
    REPORT_AGENT_MAX_TOKENS = int(os.environ.get("REPORT_AGENT_MAX_TOKENS", "8192"))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(
        os.environ.get("REPORT_AGENT_MAX_REFLECTION_ROUNDS", "2")
    )
    REPORT_AGENT_TEMPERATURE = float(os.environ.get("REPORT_AGENT_TEMPERATURE", "0.5"))

    @classmethod
    def validate(cls) -> list[str]:
        """验证必要配置"""
        errors: list[str] = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        if not cls.NEO4J_URI:
            errors.append("NEO4J_URI 未配置")
        return errors
