"""模拟子进程侧的 Redis IPC 传输（命令收取 / 响应回写 / 存活心跳）。

把原先基于本地文件目录（ipc_commands/ipc_responses/env_status.json）的进程间
通信搬到 Redis，使「发命令的 API 副本」与「跑模拟的 worker 进程」不再需要共享
本地文件系统 —— 这是模拟从 API 进程拆到独立 worker / 多副本横向扩展的前置条件。

键协议（必须与后端 app/services/simulation_ipc.py 完全一致）：
  命令队列 (LIST)  : sim:ipc:cmd:{sid}        生产者 RPUSH / 消费者 LPOP（FIFO）
  响应信箱 (LIST)  : sim:ipc:resp:{sid}:{cid} 服务端 RPUSH(带TTL) / 客户端 BLPOP
  存活心跳 (STRING): sim:ipc:alive:{sid}      服务端 SET ... EX，客户端 GET/EXISTS

模拟脚本以独立进程运行（cwd=模拟目录），故本模块零依赖 app 包，仅用同步 redis。
"""

import json
import os
from datetime import datetime

# ---- 键协议（与 app/services/simulation_ipc.py 保持字节级一致）----
CMD_KEY = "sim:ipc:cmd:{sid}"
RESP_KEY = "sim:ipc:resp:{sid}:{cid}"
ALIVE_KEY = "sim:ipc:alive:{sid}"

ALIVE_TTL = 30  # 存活心跳 TTL（秒）；服务端每轮循环刷新，进程死后自动过期
RESP_TTL = 300  # 响应信箱兜底 TTL（秒），防客户端超时/掉线后残留
CMD_TTL = 120  # 命令队列兜底 TTL（秒），防孤儿命令长期残留


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class RedisIPCServer:
    """模拟子进程侧：从 Redis 收命令、回响应、刷存活心跳（同步客户端，懒连接）。"""

    def __init__(self, simulation_id: str):
        self.sid = simulation_id
        self._r = None

    def _redis(self):
        if self._r is None:
            import redis

            self._r = redis.Redis.from_url(
                _redis_url(), encoding="utf-8", decode_responses=True
            )
        return self._r

    def poll_command(self) -> dict | None:
        """非阻塞取一条命令（FIFO）。无命令或连接异常返回 None。"""
        try:
            raw = self._redis().lpop(CMD_KEY.format(sid=self.sid))
        except Exception:
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def send_response(
        self, command_id: str, status: str, result: dict | None = None, error: str | None = None
    ) -> None:
        """把响应写入对应命令的信箱（带 TTL 兜底）。"""
        payload = {
            "command_id": command_id,
            "status": status,
            "result": result,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }
        key = RESP_KEY.format(sid=self.sid, cid=command_id)
        try:
            r = self._redis()
            r.rpush(key, json.dumps(payload, ensure_ascii=False))
            r.expire(key, RESP_TTL)
        except Exception as exc:  # 响应回写失败不应中断模拟
            print(f"[ipc-redis] send_response 失败: {exc}")

    def touch_alive(self, payload: dict) -> None:
        """刷新存活心跳（SET + EX）。每轮命令循环调用，使其在进程存活期间不过期。"""
        try:
            self._redis().set(
                ALIVE_KEY.format(sid=self.sid),
                json.dumps(payload, ensure_ascii=False),
                ex=ALIVE_TTL,
            )
        except Exception as exc:
            print(f"[ipc-redis] touch_alive 失败: {exc}")

    def mark_stopped(self, payload: dict) -> None:
        """标记环境停止：写一个短 TTL 标记后让其自然过期。"""
        try:
            self._redis().set(
                ALIVE_KEY.format(sid=self.sid),
                json.dumps(payload, ensure_ascii=False),
                ex=5,
            )
        except Exception as exc:
            print(f"[ipc-redis] mark_stopped 失败: {exc}")
