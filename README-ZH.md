<div align="center">

<img src="./static/image/SuperFish_logo_compressed.jpeg" alt="SuperFish Logo" width="75%"/>

简洁通用的群体智能引擎，预测万物
</br>
<em>A Simple and Universal Swarm Intelligence Engine, Predicting Anything</em>

[English](./README.md) | [中文文档](./README-ZH.md)

</div>

## ⚡ 项目概述

**SuperFish（超级章鱼）** 是一款基于多智能体技术的新一代 AI 预测引擎。通过提取现实世界的种子信息（如突发新闻、政策草案、金融信号），自动构建出高保真的平行数字世界。在此空间内，成千上万个具备独立人格、长期记忆与行为逻辑的智能体进行自由交互与社会演化。你可透过「上帝视角」动态注入变量，精准推演未来走向——**让未来在数字沙盘中预演，助决策在百战模拟后胜出**。

> 你只需：上传种子材料（数据分析报告或者有趣的小说故事），并用自然语言描述预测需求</br>
> SuperFish 将返回：一份详尽的预测报告，以及一个可深度交互的高保真数字世界

### 我们的愿景

SuperFish 致力于打造映射现实的群体智能镜像，通过捕捉个体互动引发的群体涌现，突破传统预测的局限：

- **于宏观**：我们是决策者的预演实验室，让政策与公关在零风险中试错
- **于微观**：我们是个人用户的创意沙盘，无论是推演小说结局还是探索脑洞，皆可有趣、好玩、触手可及

从严肃预测到趣味仿真，我们让每一个如果都能看见结果，让预测万物成为可能。

## 📸 系统截图

<div align="center">
<table>
<tr>
<td><img src="./static/image/Screenshot/运行截图1.png" alt="截图1" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图2.png" alt="截图2" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图3.png" alt="截图3" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图4.png" alt="截图4" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图5.png" alt="截图5" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图6.png" alt="截图6" width="100%"/></td>
</tr>
</table>
</div>

## 🔄 工作流程

1. **本体与图谱构建**：LLM 生成本体，LlamaIndex 严格抽取实体/关系，并将图谱存入 Postgres
2. **环境搭建**：读取图谱实体，生成人设，并注入 Agent 仿真参数
3. **开始模拟**：双平台并行模拟，自动解析预测需求，并动态更新图谱记忆
4. **报告生成**：ReportAgent 通过图谱搜索、全景检索、深度洞察与采访工具生成报告
5. **深度互动**：与模拟世界中的任意一位进行对话 & 与ReportAgent进行对话

## 🧠 知识图谱后端

SuperFish 将每个项目的知识图谱以 JSONB 存于 Postgres（无需独立图数据库）：

- 本体生成阶段会按用户选择的界面语言直接生成实体类型和关系类型；中文项目使用中文 schema 名，英文项目使用英文 schema 名。
- 图谱构建使用 `LlamaIndex SchemaLLMPathExtractor(strict=True)`，只抽取符合项目本体的实体和关系。
- 抽取出的节点与边写入 `graphs` 表（每张图一行 JSONB），按 `graph_id` 隔离。
- 环境搭建、模拟记忆更新和 ReportAgent 检索都读取同一份图谱。访问模式是「取整张图 + 应用层打分」、无多跳遍历，故 JSONB 即可，也没有在线图数据库单点。

## 🏗️ 架构总览

SuperFish 是一个 **pnpm + turbo monorepo**：

```
SuperFish/
├── apps/
│   ├── web/        # 前端 —— React 18 + Vite + TypeScript + TailwindCSS + shadcn/ui（端口 3000）
│   └── api/        # 后端 —— FastAPI + Pydantic，由 uv 管理（端口 5001）
├── packages/
│   └── shared/     # 共享资源（i18n 文案等）
└── docker-compose.yml
```

后端已做到**无状态、可水平扩展**：元数据与知识图谱存于 **PostgreSQL**，上传文件/提取文本存于 **S3 兼容对象存储（RustFS）**。重活（图谱构建、报告生成）经 **Redis 支撑的 [arq](https://arq-docs.helpmanual.io/) 队列** 投递，由**独立 worker 进程**执行（`apps/api/app/worker.py`）。若 Redis 不可达，`enqueue` 会自动回退到进程内线程执行——因此开发时**独立 worker 可选**，但生产与扩缩容场景推荐单独运行。

## 🚀 快速开始

### 一、源码部署（推荐）

#### 前置要求

| 工具 | 版本要求 | 说明 | 安装检查 |
|------|---------|------|---------|
| **Node.js** | 18+ | 前端运行环境 | `node -v` |
| **pnpm** | 9+ | monorepo 包管理器 | `pnpm -v` |
| **Python** | ≥3.11, ≤3.12 | 后端运行环境 | `python --version` |
| **uv** | 最新版 | Python 包管理器 | `uv --version` |
| **Docker** | 最新版 | 运行内置中间件（PostgreSQL / Redis / RustFS） | `docker -v` |

> 没有 pnpm？用 `npm install -g pnpm` 或 `corepack enable` 安装。
> 三个中间件（PostgreSQL 16、Redis 7、RustFS）均已内置在 `docker-compose.yml`，无需手动安装；也可把环境变量指向你自己的实例。

#### 1. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env 文件，填入必要的 API 密钥
```

**必需的环境变量：**

```env
# ── LLM API（支持 OpenAI SDK 格式的任意 LLM API）──
# 推荐使用阿里百炼平台 qwen-plus 模型：https://bailian.console.aliyun.com/
# 注意消耗较大，可先进行小于 40 轮的模拟尝试。
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
LLM_REQUEST_TIMEOUT=120

# ── PostgreSQL（项目/任务/报告等元数据）──
DATABASE_URL=postgresql+psycopg://superfish:superfish_pg@localhost:5432/superfish

# ── Redis（arq 任务队列）──
REDIS_URL=redis://localhost:6379/0

# ── S3 兼容对象存储 RustFS（上传文件/提取文本）──
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=superfish
S3_SECRET_KEY=superfish_secret
S3_BUCKET=superfish
S3_REGION=us-east-1

# ── 鉴权（邮箱密码 / JWT）──
# 有 dev 默认值保证可启动，但生产环境务必覆盖（如 `openssl rand -hex 32`）。
JWT_SECRET=dev-insecure-change-me
```

> 上面的 `localhost` 取值用于源码部署。完整 Docker Compose 部署时改用服务名（`postgres`、`redis://redis:6379/0`、`http://rustfs:9000`）——`worker` 与 `superfish` 服务已内置这些覆盖值。

`.env.example` 是配置的唯一权威来源，完整记录了所有可选项，包括：
- **图谱调参**——`GRAPH_EXTRACT_MAX_TOKENS`、`GRAPH_EXTRACT_MAX_TRIPLETS`、`DEFAULT_CHUNK_SIZE`、本体类型数量（均已内置合理默认值）。
- **鉴权护栏**——令牌有效期、`ADMIN_EMAILS` 白名单、单用户配额、限流开关。
- **邮件（SMTP）**——找回密码 / 邮箱验证；不配 `SMTP_HOST` 时走开发桩，邮件内容打印到后端日志。
- **加速 LLM（可选）**——`LLM_BOOST_API_KEY`、`LLM_BOOST_BASE_URL`、`LLM_BOOST_MODEL_NAME`。（不使用时请整行删除，不要留占位值。）

#### 2. 安装依赖

```bash
# 一键安装全部依赖：Node 工作区依赖（根 + web）与 Python 依赖（api，走 uv sync）
pnpm setup
```

`pnpm setup` 会先执行 `pnpm install`，再执行 `pnpm setup:api`（即在 `apps/api` 内 `uv sync`，自动创建虚拟环境）。

#### 3. 启动中间件

拉起三个后端依赖服务（应用本身从源码运行，不在 Docker 内）：

```bash
docker compose up -d postgres redis rustfs
```

#### 4. 启动应用

```bash
# 同时启动前后端（在项目根目录执行，经 turbo 编排）
pnpm dev
```

**服务地址：**
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:5001`

**单独启动：**

```bash
pnpm dev:web   # 仅启动前端
pnpm dev:api   # 仅启动后端
```

#### 5.（可选）启动任务 worker

图谱构建与报告生成会投递到 arq 队列。开发时若没有 worker 在跑，会回退到进程内线程执行，故此步可选。要运行真正独立的 worker（推荐，与生产一致）：

```bash
cd apps/api && uv run arq app.worker.WorkerSettings
```

### 二、Docker 部署

```bash
# 1. 配置环境变量（同源码部署）
cp .env.example .env
# 完整 Docker Compose 部署时，内置服务已使用容器名
# （postgres / redis / rustfs），无需改 localhost。

# 2. 拉取镜像并启动整套（应用 + worker + 全部中间件）
docker compose up -d
```

会一次性启动全部：`superfish`（web + api）、`worker`（arq），以及 PostgreSQL / Redis / RustFS。默认读取根目录 `.env`，映射端口 `3000（前端）/5001（后端）`。

> 在 `docker-compose.yml` 中已通过注释提供加速镜像地址，可按需替换。

#### 水平扩展（生产）

后端无状态，可在负载均衡后运行多个 API 与 worker 副本。`docker-compose.scale.yml` 已内置一套现成拓扑——**nginx（静态前端 + 反向代理）+ 3 个 API 副本 + 5 个 worker**，使用独立的 Compose project：

```bash
# 启动可扩展栈（独立 project 名，避免与基础 compose 的服务定义冲突）
docker compose -p sf-scale -f docker-compose.scale.yml up -d

# 按需对某一层扩缩
docker compose -p sf-scale -f docker-compose.scale.yml up -d --scale worker=8
```

nginx 在请求时动态解析 API 上游，因此增删副本无需改配置。

## 📄 致谢

SuperFish 的仿真引擎由 **[OASIS](https://github.com/camel-ai/oasis)** 驱动，我们衷心感谢 CAMEL-AI 团队的开源贡献！

我们同时诚挚感谢原始仓库 **[MiroFish](https://github.com/666ghj/MiroFish)** 及其作者 **[666ghj](https://github.com/666ghj)** 的基础启发与开源贡献，为本项目的发展提供了重要参考。

## 📈 项目统计

<a href="https://www.star-history.com/#superteams-cn/SuperFish&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=superteams-cn/SuperFish&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=superteams-cn/SuperFish&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=superteams-cn/SuperFish&type=date&legend=top-left" />
 </picture>
</a>
