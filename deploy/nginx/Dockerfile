# nginx 镜像：多阶段构建 —— 先构建前端静态产物，再由 nginx 托管 + 反代 /api。
# 构建上下文为仓库根（见 docker-compose.scale.yml 的 build.context: .）。

# ---- 阶段1：构建前端 ----
# VITE_API_BASE_URL 指向 nginx 对外地址：前端所有 /api 请求打到 nginx，由其反代到 API 副本。
FROM node:20-slim AS web-build
ARG VITE_API_BASE_URL=http://localhost:8080
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN corepack enable
WORKDIR /repo

# 先装依赖（利用缓存）：复制各 workspace 的 package.json + lock
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY apps/web/package.json ./apps/web/
COPY apps/api/package.json ./apps/api/
COPY packages/shared/package.json ./packages/shared/
RUN pnpm install --frozen-lockfile

# 复制源码并构建（产物在 apps/web/dist）
COPY packages/shared ./packages/shared
COPY apps/web ./apps/web
RUN pnpm --filter web build

# ---- 阶段2：nginx 托管 ----
FROM nginx:1.27-alpine
COPY deploy/nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
