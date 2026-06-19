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

## ⚡ Overview

**SuperFish** is a next-generation AI prediction engine powered by multi-agent technology. By extracting seed information from the real world (such as breaking news, policy drafts, or financial signals), it automatically constructs a high-fidelity parallel digital world. Within this space, thousands of intelligent agents with independent personalities, long-term memory, and behavioral logic freely interact and undergo social evolution. You can inject variables dynamically from a "God's-eye view" to precisely deduce future trajectories — **rehearse the future in a digital sandbox, and win decisions after countless simulations**.

> You only need to: Upload seed materials (data analysis reports or interesting novel stories) and describe your prediction requirements in natural language</br>
> SuperFish will return: A detailed prediction report and a deeply interactive high-fidelity digital world

### Our Vision

SuperFish is dedicated to creating a swarm intelligence mirror that maps reality. By capturing the collective emergence triggered by individual interactions, we break through the limitations of traditional prediction:

- **At the Macro Level**: We are a rehearsal laboratory for decision-makers, allowing policies and public relations to be tested at zero risk
- **At the Micro Level**: We are a creative sandbox for individual users — whether deducing novel endings or exploring imaginative scenarios, everything can be fun, playful, and accessible

From serious predictions to playful simulations, we let every "what if" see its outcome, making it possible to predict anything.

## 🌐 Live Demo

Welcome to visit our online demo environment and experience a prediction simulation on trending public opinion events we've prepared for you: [superfish-live-demo](https://666ghj.github.io/superfish-demo/)

## 📸 Screenshots

<div align="center">
<table>
<tr>
<td><img src="./static/image/Screenshot/运行截图1.png" alt="Screenshot 1" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图2.png" alt="Screenshot 2" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图3.png" alt="Screenshot 3" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图4.png" alt="Screenshot 4" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图5.png" alt="Screenshot 5" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图6.png" alt="Screenshot 6" width="100%"/></td>
</tr>
</table>
</div>

## 🎬 Demo Videos

### 1. Wuhan University Public Opinion Simulation + SuperFish Project Introduction

<div align="center">
<a href="https://www.bilibili.com/video/BV1VYBsBHEMY/" target="_blank"><img src="./static/image/武大模拟演示封面.png" alt="SuperFish Demo Video" width="75%"/></a>

Click the image to watch the complete demo video for prediction using BettaFish-generated "Wuhan University Public Opinion Report"
</div>

### 2. Dream of the Red Chamber Lost Ending Simulation

<div align="center">
<a href="https://www.bilibili.com/video/BV1cPk3BBExq" target="_blank"><img src="./static/image/红楼梦模拟推演封面.jpg" alt="SuperFish Demo Video" width="75%"/></a>

Click the image to watch SuperFish's deep prediction of the lost ending based on hundreds of thousands of words from the first 80 chapters of "Dream of the Red Chamber"
</div>

> **Financial Prediction**, **Political News Prediction** and more examples coming soon...

## 🔄 Workflow

1. **Ontology & Graph Building**: LLM-generated ontology, strict LlamaIndex path extraction, and Neo4j property-graph storage
2. **Environment Setup**: Neo4j entity reading, persona generation, and agent configuration injection
3. **Simulation**: Dual-platform parallel simulation, automatic requirement parsing, and dynamic graph memory updates
4. **Report Generation**: ReportAgent with Neo4j graph search, panorama search, insight retrieval, and interview tools
5. **Deep Interaction**: Chat with any agent in the simulated world & Interact with ReportAgent

## 🧠 Knowledge Graph Backend

SuperFish now uses a self-hosted Neo4j property graph as the GraphRAG backend:

- The ontology generator creates entity and relationship type names directly in the selected UI language; Chinese projects use Chinese schema names, English projects use English schema names.
- Graph building uses `LlamaIndex SchemaLLMPathExtractor(strict=True)` to extract only ontology-valid entities and relations.
- Extracted nodes and edges are stored in Neo4j with `group_id` isolation per project.
- ReportAgent and simulation setup read/search the same Neo4j graph through local graph search tools.

## 🏗️ Architecture

SuperFish is a **pnpm + turbo monorepo**:

```
SuperFish/
├── apps/
│   ├── web/        # Frontend — React 18 + Vite + TypeScript + TailwindCSS + shadcn/ui (port 3000)
│   └── api/        # Backend  — FastAPI + Pydantic, managed by uv (port 5001)
├── packages/
│   └── shared/     # Shared assets (i18n locales, etc.)
└── docker-compose.yml
```

The backend is **stateless and horizontally scalable**: metadata lives in **PostgreSQL**, uploaded files / extracted text live in an **S3-compatible store (RustFS)**, and the Neo4j property graph is the GraphRAG backend. Long-running jobs (graph building, report generation) are pushed onto a **Redis-backed [arq](https://arq-docs.helpmanual.io/) queue** and executed by a **separate worker process** (`apps/api/app/worker.py`). If Redis is unreachable, `enqueue` transparently falls back to an in-process thread, so a dedicated worker is **optional in development** but recommended for production and scaling.

## 🚀 Quick Start

### Option 1: Source Code Deployment (Recommended)

#### Prerequisites

| Tool | Version | Description | Check Installation |
|------|---------|-------------|-------------------|
| **Node.js** | 18+ | Frontend runtime | `node -v` |
| **pnpm** | 9+ | Monorepo package manager | `pnpm -v` |
| **Python** | ≥3.11, ≤3.12 | Backend runtime | `python --version` |
| **uv** | Latest | Python package manager | `uv --version` |
| **Docker** | Latest | Runs bundled infra (Neo4j / PostgreSQL / Redis / RustFS) | `docker -v` |

> Don't have pnpm? Install with `npm install -g pnpm` or `corepack enable`.
> The four infra services (Neo4j 5.x, PostgreSQL 16, Redis 7, RustFS) are all bundled in `docker-compose.yml` — no manual install needed. You may also point the env vars at your own instances.

#### 1. Configure Environment Variables

```bash
# Copy the example configuration file
cp .env.example .env

# Edit the .env file and fill in the required API keys
```

**Required Environment Variables:**

```env
# ── LLM API (supports any LLM API with OpenAI SDK format) ──
# Recommended: Alibaba Qwen-plus model via Bailian Platform: https://bailian.console.aliyun.com/
# High consumption — try simulations with fewer than 40 rounds first.
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
LLM_REQUEST_TIMEOUT=120
GRAPH_EXTRACT_MAX_TOKENS=8192
GRAPH_EXTRACT_MAX_TRIPLETS=20

# ── Neo4j (knowledge graph) ──
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

# ── PostgreSQL (project/task/report metadata) ──
DATABASE_URL=postgresql+psycopg://superfish:superfish_pg@localhost:5432/superfish

# ── Redis (arq job queue) ──
REDIS_URL=redis://localhost:6379/0

# ── S3-compatible object storage (RustFS) — uploads & extracted text ──
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=superfish
S3_SECRET_KEY=superfish_secret
S3_BUCKET=superfish
S3_REGION=us-east-1
```

> The `localhost` values above are for source deployment. For full Docker Compose deployment, use the service names instead (`bolt://neo4j:7687`, `postgres`, `redis://redis:6379/0`, `http://rustfs:9000`) — the `worker` and `superfish` services already set these.

Optional acceleration LLM variables are also supported: `LLM_BOOST_API_KEY`, `LLM_BOOST_BASE_URL`, and `LLM_BOOST_MODEL_NAME`. (If you don't use them, omit these lines entirely rather than leaving placeholders.)

#### 2. Install Dependencies

```bash
# Install everything: Node workspace deps (root + web) and Python deps (api, via uv sync)
pnpm setup
```

`pnpm setup` runs `pnpm install` followed by `pnpm setup:api` (which is `uv sync` inside `apps/api`, auto-creating the virtual environment).

#### 3. Start Infrastructure

Bring up the four backing services (the app itself runs from source, not in Docker):

```bash
docker compose up -d neo4j postgres redis rustfs
```

#### 4. Start the App

```bash
# Start frontend + backend together (from project root, via turbo)
pnpm dev
```

**Service URLs:**
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

**Start individually:**

```bash
pnpm dev:web   # Frontend only
pnpm dev:api   # Backend only
```

#### 5. (Optional) Start the Job Worker

Graph building and report generation are queued to arq. In dev they fall back to an in-process thread if no worker is running, so this step is optional. To run a real, separate worker (recommended, mirrors production):

```bash
cd apps/api && uv run arq app.worker.WorkerSettings
```

### Option 2: Docker Deployment

```bash
# 1. Configure environment variables (same as source deployment)
cp .env.example .env
# For full Docker Compose deployment, the bundled services already use container names
# (neo4j / postgres / redis / rustfs) — no localhost overrides needed.

# 2. Pull images and start the entire stack (app + worker + all infra)
docker compose up -d
```

This starts everything: `superfish` (web + api), `worker` (arq), plus Neo4j / PostgreSQL / Redis / RustFS. Reads `.env` from the root by default and maps ports `3000 (frontend) / 5001 (backend)`.

> A faster mirror address is provided as comments in `docker-compose.yml` — replace if needed.

## 📬 Join the Conversation

<div align="center">
<img src="./static/image/QQ群.png" alt="QQ Group" width="60%"/>
</div>

&nbsp;

The SuperFish team is recruiting full-time/internship positions. If you're interested in multi-agent simulation and LLM applications, feel free to send your resume to: **superfish@shanda.com**

## 📄 Acknowledgments

**SuperFish has received strategic support and incubation from Shanda Group!**

SuperFish's simulation engine is powered by **[OASIS (Open Agent Social Interaction Simulations)](https://github.com/camel-ai/oasis)**, We sincerely thank the CAMEL-AI team for their open-source contributions!

We also gratefully acknowledge the original repository **[MiroFish](https://github.com/666ghj/MiroFish)** and its author **[666ghj](https://github.com/666ghj)** for the foundational inspiration and open-source work that helped shape this project.

## 📈 Project Statistics

<a href="https://www.star-history.com/#superteams-cn/SuperFish&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=superteams-cn/SuperFish&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=superteams-cn/SuperFish&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=superteams-cn/SuperFish&type=date&legend=top-left" />
 </picture>
</a>
