FROM python:3.11

# 安装 Node.js（满足 >=18）并通过 corepack 启用 pnpm
RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm \
  && rm -rf /var/lib/apt/lists/* \
  && corepack enable

# 从 uv 官方镜像复制 uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# 先复制依赖描述文件以利用构建缓存
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY apps/web/package.json ./apps/web/
COPY apps/api/package.json ./apps/api/
COPY packages/shared/package.json ./packages/shared/
COPY apps/api/pyproject.toml apps/api/uv.lock ./apps/api/

# 安装依赖（Node 端用 pnpm，Python 端用 uv）
RUN pnpm install --frozen-lockfile \
  && cd apps/api && uv sync --frozen

# 复制项目源码
COPY . .

EXPOSE 3000 5001

# 同时启动前后端（开发模式）
CMD ["pnpm", "dev"]
