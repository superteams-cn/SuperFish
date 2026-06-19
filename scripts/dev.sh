#!/usr/bin/env bash
# 一键管理本地开发进程：API(FastAPI) + worker(arq) + web(vite)
# 用法: bash scripts/dev.sh {start|stop|restart|status}
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/.dev-logs"
mkdir -p "$LOG_DIR"

API_PORT=5001
WEB_PORT=3000

# 各进程的唯一匹配特征（用于 pkill -f / 状态检查）
API_PAT="uvicorn app.main:app|apps/api/.venv/bin/python3 run.py| run.py"
WORKER_PAT="arq app.worker.WorkerSettings"
WEB_PAT="apps/web/node_modules/.bin/.*vite|vite --host"

stop() {
  echo "停止开发进程..."
  # 用 SIGKILL：arq worker 收到 SIGTERM 会先跑完手上的任务才退出，导致残留
  pkill -9 -f "$WORKER_PAT" 2>/dev/null && echo "  ✓ worker 已停" || echo "  · worker 未在运行"
  pkill -9 -f "uvicorn app.main:app" 2>/dev/null && echo "  ✓ API(uvicorn) 已停" || true
  pkill -9 -f "run.py" 2>/dev/null && echo "  ✓ API(run.py) 已停" || true
  pkill -9 -f "$WEB_PAT" 2>/dev/null && echo "  ✓ web(vite) 已停" || echo "  · web 未在运行"
  # 端口兜底（排除浏览器等非服务进程的占用由调用者自理）
  for p in "$API_PORT" "$WEB_PORT"; do
    pids="$(lsof -ti:"$p" 2>/dev/null || true)"
    [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null || true
  done
  echo "完成。"
}

start() {
  # 先停掉已有的同名进程，保证幂等：重复 start 不会累积多份
  stop >/dev/null 2>&1
  sleep 1
  echo "启动开发进程(后台,日志在 .dev-logs/)..."
  cd "$ROOT"
  nohup pnpm --filter @superfish/api dev    >"$LOG_DIR/api.log"    2>&1 &
  echo "  ▶ API    :$API_PORT   → .dev-logs/api.log"
  nohup pnpm --filter @superfish/api worker >"$LOG_DIR/worker.log" 2>&1 &
  echo "  ▶ worker (arq)        → .dev-logs/worker.log"
  nohup pnpm --filter @superfish/web dev    >"$LOG_DIR/web.log"    2>&1 &
  echo "  ▶ web    :$WEB_PORT   → .dev-logs/web.log"
  echo "完成。用 'pnpm stop' 关闭,日志: tail -f .dev-logs/*.log"
}

status() {
  check() { pgrep -fl "$1" >/dev/null 2>&1 && echo "  ✓ $2 运行中" || echo "  ✗ $2 未运行"; }
  check "$WORKER_PAT" "worker"
  (pgrep -fl "uvicorn app.main:app" >/dev/null 2>&1 || pgrep -fl "run.py" >/dev/null 2>&1) \
    && echo "  ✓ API 运行中" || echo "  ✗ API 未运行"
  check "$WEB_PAT" "web"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  status) status ;;
  *) echo "用法: bash scripts/dev.sh {start|stop|restart|status}"; exit 1 ;;
esac
