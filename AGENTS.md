# AGENTS.md — SuperFish 项目协作规范

本文件面向所有参与本仓库开发的 AI 代理与人类开发者，定义统一的工程约定。**首要原则：对中文程序员友好。**

## 0. 语言约定（最高优先级）

- **界面文案**：所有面向用户的 UI 文本以中文为第一语言，通过 `packages/shared/locales` 多语言机制提供。新增文案必须同时补齐 `zh.json`，英文等其他语言可后续跟进。
- **代码注释**：一律使用**简体中文**编写注释，解释「为什么」而非「做了什么」。复杂逻辑、业务规则、临时取舍必须有中文注释。
- **提交信息 / PR 描述**：使用中文。
- **标识符命名**：变量、函数、类型等标识符仍用英文（保证生态兼容），但命名要语义清晰，便于中文开发者理解。
- **文档**：README、设计文档、错误提示尽量提供中文版本。

> 目标：一名只读中文的工程师，能仅凭注释和文档理解全部代码意图。

## 1. 仓库架构（Monorepo）

```
superfish/
├─ apps/
│  ├─ web/      # 前端：Vite + React + TailwindCSS + shadcn/ui + Radix（迁移中）
│  └─ api/      # 后端：FastAPI + Python + Pydantic + uv（迁移中）
└─ packages/
   └─ shared/   # 前后端共享资源（locales 多语言文案等）
```

- **包管理**：根目录用 **pnpm** 工作区；Python 端用 **uv**。
- **任务编排**：根目录用 **turbo**（`turbo run dev` / `turbo run build`）。
- 子包命名统一为 `@superfish/<name>`。

## 2. 常用命令

| 目的 | 命令 |
|------|------|
| 安装全部依赖 | `pnpm setup` |
| 同时启动前后端 | `pnpm dev` |
| 仅启动前端 | `pnpm dev:web` |
| 仅启动后端 | `pnpm dev:api` |
| 构建 | `pnpm build` |

> Python 依赖通过 `pnpm --filter @superfish/api setup`（即 `uv sync`）安装。

## 3. 前端约定（apps/web）

- 技术栈：**React + TypeScript + Vite + TailwindCSS + shadcn/ui（基于 Radix）**。
- UI 组件优先使用 shadcn/ui，采用其默认主题 + 单一品牌主色，不再维护多套自定义主题。
- 多语言用 `react-i18next`，文案来自 `@superfish/shared` 的 locales。
- 组件按功能域组织于 `src/features/`，通用 UI 放 `src/components/ui/`。

## 4. 后端约定（apps/api）

- 技术栈：**FastAPI + Pydantic + uv**，钉死版本的重依赖（`camel-oasis`、`camel-ai`）**不得擅自升级**。
- 请求体（JSON/Form）用 Pydantic 模型（置于 `app/schemas/`）。注意：必填项手动在处理器内校验并返回本地化 400，模型字段设为可选，避免 FastAPI 默认的 422 破坏前端契约。
- 路由置于 `app/routers/`，业务逻辑置于 `app/services/`，配置在 `app/config.py`，入口在 `app/main.py`（含 lifespan）。
- 响应统一信封 `{"success": bool, "data"/"error": ...}`；错误用 `_error(msg, status, **extra)` 辅助函数。
- 路由声明顺序敏感：字面量路径必须在动态段 `/{id}` 之前声明。
- i18n：请求级语言由 `app/deps.py:use_locale` 依赖从 `Accept-Language` 设置；后台线程入口处需 `set_locale(get_locale())` 继承。
- 涉及 OASIS 模拟的进程/生命周期由 FastAPI `lifespan` 统一管理。

## 5. 协作纪律

- 重依赖（OASIS / camel-ai / neo4j 版本）改动前必须与维护者确认。
- 不提交 `.env`、密钥、上传文件、日志等（见 `.gitignore`）。
- 改动公共契约（API schema、locales key）时，前后端要同步更新。
