# AGENTS.md — SuperFish 项目协作规范

本文件面向所有参与本仓库开发的 AI 代理与人类开发者，定义统一的工程约定。**首要原则：对中文程序员友好。**

## 0. 语言约定（最高优先级）

- **界面文案**：所有面向用户的 UI 文本以中文为第一语言，通过 `packages/shared/locales` 多语言机制提供。新增文案必须同时补齐 `zh.json`，英文等其他语言可后续跟进。
- **代码注释**：一律使用**简体中文**编写注释，解释「为什么」而非「做了什么」。复杂逻辑、业务规则、临时取舍必须有中文注释。
- **提交信息 / PR 描述**：使用中文。但须遵循**约定式提交**格式（commitlint 强制）：`type(scope): 中文主题`，type 用英文关键字（`feat`/`fix`/`refactor`/`chore`/`docs`/`test`/`perf`/`build`/`ci`/`style`），scope 与主题用中文。例：`refactor(web): 拆分报告组件`。
- **标识符命名**：变量、函数、类型等标识符仍用英文（保证生态兼容），但命名要语义清晰，便于中文开发者理解。
- **文档**：README、设计文档、错误提示尽量提供中文版本。

> 目标：一名只读中文的工程师，能仅凭注释和文档理解全部代码意图。

## 1. 仓库架构（Monorepo）

```
superfish/
├─ apps/
│  ├─ web/      # 前端：Vite + React 18 + TypeScript + TailwindCSS + shadcn/ui + Radix
│  └─ api/      # 后端：FastAPI + Python + Pydantic + uv（分层架构，见 §4）
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
| 仅启动前端 / 后端 | `pnpm dev:web` / `pnpm dev:api` |
| 单独启动任务 worker | `pnpm dev:worker` |
| 构建 | `pnpm build` |
| Lint（eslint + ruff） | `pnpm lint` |
| 类型检查（tsc） | `pnpm typecheck` |
| 测试（vitest + pytest） | `pnpm test` |
| 前端格式化 | `pnpm format` |

> 上述 `lint`/`typecheck`/`test` 经 turbo 编排，会下发到对应子包（前端 eslint/tsc/vitest，后端 ruff/pytest）。
> Python 依赖通过 `pnpm setup:api`（即在 `apps/api` 内 `uv sync`）安装；后端单测可在 `apps/api` 内 `uv run pytest` 单独跑。

## 3. 前端约定（apps/web）

- 技术栈：**React + TypeScript + Vite + TailwindCSS + shadcn/ui（基于 Radix）**。
- 多语言用 `react-i18next`，文案来自 `@superfish/shared` 的 locales（用 `useTranslation` 的 `t`）。

### 3.1 优先使用 shadcn/Radix 原生组件（强制）
- **禁止手写**已有原生组件能覆盖的交互元素。一律使用 `src/components/ui/` 下的 shadcn 封装（底层 Radix）：
  - 按钮 → `Button`（不要写 `<button className="...">`）；图标按钮用 `size="icon"`。
  - 弹窗/模态 → `Dialog`（不要手写 `fixed inset-0` 遮罩）。
  - 复选 → `Checkbox`；滑块 → `Slider`；分隔线 → `Separator`；下拉 → `DropdownMenu`/`Select`；
    标签页 → `Tabs`；分段切换 → `ToggleGroup`；头像 → `Avatar`；提示 → `Tooltip`；
    输入 → `Input`/`Textarea`；进度 → `Progress`；徽标 → `Badge`；卡片 → `Card`。
- 缺少的 shadcn 组件：按官方实现新增到 `src/components/ui/`（已装好对应 `@radix-ui/*` 依赖），再使用。
- **设计系统：苹果玻璃质感（Liquid Glass）**，令牌驱动、亮/暗双主题。表面统一用 `src/index.css` 的 `.glass` / `.glass-subtle` 工具类（内置 `backdrop-blur`），不要逐处手写半透明背景与模糊。
- 颜色用语义化 token（`bg-background`/`text-muted-foreground`/`border` 等），避免硬编码灰阶与具体色值（旧的单一橙 `#FF5722` 主色已废弃）。

### 3.2 组件化与可维护性
- **小而专、可复用**：组件单一职责；页面级文件只做编排（数据/轮询/路由），UI 细节下沉到子组件。
- 目录约定：
  - `src/pages/`：路由页面（编排器），通过 `router.tsx` **懒加载**（`React.lazy` + `Suspense`）。
  - `src/components/ui/`：shadcn 原生封装（不写业务逻辑）。
  - `src/components/common/`：跨页复用的业务无关小件（如 `Brand`、`StatusDot`）。
  - `src/components/<viewname>/`（如 `step1/`…`step5/`）：某视图专属的聚焦子组件。
  - `src/components/*.tsx`：跨视图复用的较大业务组件（如 `WorkflowLayout`、`GraphPanel`、`Markdown`）。
  - `src/lib/api/`：接口封装；`src/lib/*-types.ts`：领域类型。
- 重复出现 3 次以上的 UI 片段必须抽成组件；公共外壳（如工作流头部）用 `WorkflowLayout` 复用。
- 控制单文件体量（经验值 < ~300 行）；超出优先按子组件拆分而非堆叠。

## 4. 后端约定（apps/api）

- 技术栈：**FastAPI + Pydantic + uv**，钉死版本的重依赖（`camel-oasis`、`camel-ai`）**不得擅自升级**。
- 请求体（JSON/Form）用 Pydantic 模型（置于 `app/schemas/`）。注意：必填项手动在处理器内校验并返回本地化 400，模型字段设为可选，避免 FastAPI 默认的 422 破坏前端契约。

### 4.1 分层架构（单向依赖，自上而下）
后端按职责分层，依赖方向**严格单向**：`routers → services → repositories → domain`，`core` 为横切层、可被任意层引用。入口在 `app/main.py`（含 lifespan）。

| 层 | 目录 | 职责 |
|----|------|------|
| 路由层 | `app/routers/`（`simulation/` 已拆为子包） | HTTP 编排、参数校验、组装响应信封。**不得出现 `session_scope`**——DB 访问一律下沉到 repository。 |
| 服务层 | `app/services/`、`app/models/`（如 `ProjectManager`） | 业务编排：图谱构建、模拟、报告、本体生成、对象存储、删除级联等跨资源逻辑。 |
| 仓储层 | `app/repositories/`（`*_repo.py`，按实体一文件） | 唯一封装 `session_scope` + SQLAlchemy ORM（`app/db_models.py`）的地方；对上只暴露领域对象/字典。 |
| 领域层 | `app/domain/`（`*.py`，纯 `dataclass`） | 纯数据/状态机，**无 IO、无 DB 依赖**。 |
| 横切层 | `app/core/` | `settings.py`（配置，旧 `config.py` 已废弃）、`db.py`（`session_scope`/`Base`）、`errors.py`（错误信封）、`deps.py`、`security.py`（JWT/密码）、`redis_lock.py`、`logger.py`。 |

> 历史导入路径（如 `from ..models.project import Project`）通过 `models/` 内的 re-export 保持兼容，新代码请直接从 `domain/` / `repositories/` 引用。

### 4.2 通用约定
- 响应统一信封 `{"success": bool, "data"/"error": ...}`；错误用 `app/core/errors.py` 的辅助函数（`_error(msg, status, **extra)`）。
- 路由声明顺序敏感：字面量路径必须在动态段 `/{id}` 之前声明。
- i18n：请求级语言由 `app/core/deps.py:use_locale` 依赖从 `Accept-Language` 设置；后台线程入口处需 `set_locale(get_locale())` 继承。
- 涉及 OASIS 模拟的进程/生命周期由 FastAPI `lifespan` 统一管理。
- **鉴权**：邮箱密码 + JWT（见 `app/core/security.py`、`app/routers/auth.py`、`app/schemas/auth.py`）。`JWT_SECRET` 上线务必用强随机串覆盖；`ADMIN_EMAILS` 白名单命中者可调用 `/admin/*`。三表（project/task/simulation 等）按 `user_id` 做数据隔离。
- **无状态化约定**：元数据/记录落 Postgres（经 repository 层的 `session_scope` + `*Row` 模型），产物落 S3(RustFS)，跨进程状态不放内存。重活（图谱构建、报告生成）经 `app/jobqueue.py:enqueue` 投递到 **arq** 队列，由独立 worker 进程执行（`app/jobs.py` / `app/worker.py`）；队列不可用时兜底本地线程。
- **异步任务必须先写占位记录**：凡是「立即返回 id + 入队 worker 异步落库」的接口，必须在入队**前**就向 Postgres 写一条状态为 `pending` 的占位行，否则调用方在 worker 落库前 `GET /{id}` 会 404。占位行须带齐下游读取路径所需字段（如 `simulation_id`/`graph_id`），worker 完成时按同一 id upsert 覆盖。参见 `app/routers/report.py` 的 `POST /generate`。

## 5. 协作纪律

- 重依赖（OASIS / camel-ai 版本）改动前必须与维护者确认。
- 不提交 `.env`、密钥、上传文件、日志等（见 `.gitignore`）。
- 改动公共契约（API schema、locales key）时，前后端要同步更新。

## 6. 质量与测试

- **提交钩子（husky + lint-staged，自动执行）**：`pre-commit` 对暂存文件跑前端 `eslint --fix` + `prettier`、后端 `ruff check --fix` + `ruff format`；`commit-msg` 用 commitlint 强制约定式提交格式。本地绕过仅限隔离他人 WIP 时用 `--no-verify`。
- **测试**：前端 **vitest**（`apps/web`，`pnpm --filter @superfish/web test`），后端 **pytest**（`apps/api/tests/`，`uv run pytest`）。改动核心逻辑（实体消解、模拟 runner、图谱存储、Redis 锁/IPC 等）须同步补/改测试。
- 合并前自检顺序：`pnpm lint` → `pnpm typecheck` → `pnpm test`。

## 7. 部署形态

- **单机**：根目录 `docker-compose.yml`（`superfish` 应用 + `worker` + Postgres/Redis/RustFS），见 README「Docker 部署」。
- **可水平扩展**：`docker-compose.scale.yml`（nginx 反代 + 静态前端 + 3 API 副本 + 5 worker，独立 project `sf-scale`），用 `--scale worker=N` 扩缩。新增需跨进程共享的状态时，务必落 Postgres/Redis/S3，不得放进程内存（否则多副本下不一致）。
