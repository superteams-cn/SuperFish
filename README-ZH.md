<div align="center">

<img src="./static/image/SuperFish_logo_compressed.jpeg" alt="SuperFish Logo" width="75%"/>

<a href="https://trendshift.io/repositories/16144" target="_blank"><img src="https://trendshift.io/api/badge/repositories/16144" alt="superteams-cn%2FSuperFish | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

简洁通用的群体智能引擎，预测万物
</br>
<em>A Simple and Universal Swarm Intelligence Engine, Predicting Anything</em>

<a href="https://www.shanda.com/" target="_blank"><img src="./static/image/shanda_logo.png" alt="superteams-cn%2FSuperFish | Shanda" height="40"/></a>

[![GitHub Stars](https://img.shields.io/github/stars/superteams-cn/SuperFish?style=flat-square&color=DAA520)](https://github.com/superteams-cn/SuperFish/stargazers)
[![GitHub Watchers](https://img.shields.io/github/watchers/superteams-cn/SuperFish?style=flat-square)](https://github.com/superteams-cn/SuperFish/watchers)
[![GitHub Forks](https://img.shields.io/github/forks/superteams-cn/SuperFish?style=flat-square)](https://github.com/superteams-cn/SuperFish/network)
[![Docker](https://img.shields.io/badge/Docker-Build-2496ED?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/superteams-cn/SuperFish)

[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=flat-square&logo=discord&logoColor=white)](http://discord.gg/ePf5aPaHnA)
[![X](https://img.shields.io/badge/X-Follow-000000?style=flat-square&logo=x&logoColor=white)](https://x.com/superfish_ai)
[![Instagram](https://img.shields.io/badge/Instagram-Follow-E4405F?style=flat-square&logo=instagram&logoColor=white)](https://www.instagram.com/superfish_ai/)

[English](./README.md) | [中文文档](./README-ZH.md)

</div>

## ⚡ 项目概述

**SuperFish** 是一款基于多智能体技术的新一代 AI 预测引擎。通过提取现实世界的种子信息（如突发新闻、政策草案、金融信号），自动构建出高保真的平行数字世界。在此空间内，成千上万个具备独立人格、长期记忆与行为逻辑的智能体进行自由交互与社会演化。你可透过「上帝视角」动态注入变量，精准推演未来走向——**让未来在数字沙盘中预演，助决策在百战模拟后胜出**。

> 你只需：上传种子材料（数据分析报告或者有趣的小说故事），并用自然语言描述预测需求</br>
> SuperFish 将返回：一份详尽的预测报告，以及一个可深度交互的高保真数字世界

### 我们的愿景

SuperFish 致力于打造映射现实的群体智能镜像，通过捕捉个体互动引发的群体涌现，突破传统预测的局限：

- **于宏观**：我们是决策者的预演实验室，让政策与公关在零风险中试错
- **于微观**：我们是个人用户的创意沙盘，无论是推演小说结局还是探索脑洞，皆可有趣、好玩、触手可及

从严肃预测到趣味仿真，我们让每一个如果都能看见结果，让预测万物成为可能。

## 🌐 在线体验

欢迎访问在线 Demo 演示环境，体验我们为你准备的一次关于热点舆情事件的推演预测：[superfish-live-demo](https://666ghj.github.io/superfish-demo/)

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

## 🎬 演示视频

### 1. 武汉大学舆情推演预测 + SuperFish项目讲解

<div align="center">
<a href="https://www.bilibili.com/video/BV1VYBsBHEMY/" target="_blank"><img src="./static/image/武大模拟演示封面.png" alt="SuperFish Demo Video" width="75%"/></a>

点击图片查看使用微舆BettaFish生成的《武大舆情报告》进行预测的完整演示视频
</div>

### 2. 《红楼梦》失传结局推演预测

<div align="center">
<a href="https://www.bilibili.com/video/BV1cPk3BBExq" target="_blank"><img src="./static/image/红楼梦模拟推演封面.jpg" alt="SuperFish Demo Video" width="75%"/></a>

点击图片查看基于《红楼梦》前80回数十万字，SuperFish深度预测失传结局
</div>

> **金融方向推演预测**、**时政要闻推演预测**等示例陆续更新中...

## 🔄 工作流程

1. **本体与图谱构建**：LLM 生成本体，LlamaIndex 严格抽取实体/关系，并写入 Neo4j property graph
2. **环境搭建**：读取 Neo4j 图谱实体，生成人设，并注入 Agent 仿真参数
3. **开始模拟**：双平台并行模拟，自动解析预测需求，并动态更新图谱记忆
4. **报告生成**：ReportAgent 通过 Neo4j 图谱搜索、全景检索、深度洞察与采访工具生成报告
5. **深度互动**：与模拟世界中的任意一位进行对话 & 与ReportAgent进行对话

## 🧠 知识图谱后端

SuperFish 现在使用自托管 Neo4j property graph 作为 GraphRAG 后端：

- 本体生成阶段会按用户选择的界面语言直接生成实体类型和关系类型；中文项目使用中文 schema 名，英文项目使用英文 schema 名。
- 图谱构建使用 `LlamaIndex SchemaLLMPathExtractor(strict=True)`，只抽取符合项目本体的实体和关系。
- 抽取出的节点与边写入 Neo4j，并通过 `group_id` 按项目隔离。
- 环境搭建、模拟记忆更新和 ReportAgent 检索都读取同一份 Neo4j 图谱。

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

后端已做到**无状态、可水平扩展**：元数据存于 **PostgreSQL**，上传文件/提取文本存于 **S3 兼容对象存储（RustFS）**，Neo4j property graph 作为 GraphRAG 后端。重活（图谱构建、报告生成）经 **Redis 支撑的 [arq](https://arq-docs.helpmanual.io/) 队列** 投递，由**独立 worker 进程**执行（`apps/api/app/worker.py`）。若 Redis 不可达，`enqueue` 会自动回退到进程内线程执行——因此开发时**独立 worker 可选**，但生产与扩缩容场景推荐单独运行。

## 🚀 快速开始

### 一、源码部署（推荐）

#### 前置要求

| 工具 | 版本要求 | 说明 | 安装检查 |
|------|---------|------|---------|
| **Node.js** | 18+ | 前端运行环境 | `node -v` |
| **pnpm** | 9+ | monorepo 包管理器 | `pnpm -v` |
| **Python** | ≥3.11, ≤3.12 | 后端运行环境 | `python --version` |
| **uv** | 最新版 | Python 包管理器 | `uv --version` |
| **Docker** | 最新版 | 运行内置中间件（Neo4j / PostgreSQL / Redis / RustFS） | `docker -v` |

> 没有 pnpm？用 `npm install -g pnpm` 或 `corepack enable` 安装。
> 四个中间件（Neo4j 5.x、PostgreSQL 16、Redis 7、RustFS）均已内置在 `docker-compose.yml`，无需手动安装；也可把环境变量指向你自己的实例。

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
GRAPH_EXTRACT_MAX_TOKENS=8192
GRAPH_EXTRACT_MAX_TRIPLETS=20

# ── Neo4j（知识图谱）──
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

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
```

> 上面的 `localhost` 取值用于源码部署。完整 Docker Compose 部署时改用服务名（`bolt://neo4j:7687`、`postgres`、`redis://redis:6379/0`、`http://rustfs:9000`）——`worker` 与 `superfish` 服务已内置这些覆盖值。

可选加速模型配置：`LLM_BOOST_API_KEY`、`LLM_BOOST_BASE_URL`、`LLM_BOOST_MODEL_NAME`。（不使用时请整行删除，不要留占位值。）

#### 2. 安装依赖

```bash
# 一键安装全部依赖：Node 工作区依赖（根 + web）与 Python 依赖（api，走 uv sync）
pnpm setup
```

`pnpm setup` 会先执行 `pnpm install`，再执行 `pnpm setup:api`（即在 `apps/api` 内 `uv sync`，自动创建虚拟环境）。

#### 3. 启动中间件

拉起四个后端依赖服务（应用本身从源码运行，不在 Docker 内）：

```bash
docker compose up -d neo4j postgres redis rustfs
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
# （neo4j / postgres / redis / rustfs），无需改 localhost。

# 2. 拉取镜像并启动整套（应用 + worker + 全部中间件）
docker compose up -d
```

会一次性启动全部：`superfish`（web + api）、`worker`（arq），以及 Neo4j / PostgreSQL / Redis / RustFS。默认读取根目录 `.env`，映射端口 `3000（前端）/5001（后端）`。

> 在 `docker-compose.yml` 中已通过注释提供加速镜像地址，可按需替换。

## 📬 更多交流

<div align="center">
<img src="./static/image/QQ群.png" alt="QQ交流群" width="60%"/>
</div>

&nbsp;

SuperFish团队长期招募全职/实习，如果你对多Agent应用感兴趣，欢迎投递简历至：**superfish@shanda.com**

## 📄 致谢

**SuperFish 得到了盛大集团的战略支持和孵化！**

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
