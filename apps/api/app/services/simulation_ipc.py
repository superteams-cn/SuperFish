"""
模拟IPC通信模块
用于后端（FastAPI）和模拟脚本之间的进程间通信

通过 Redis 实现命令/响应模式（不再依赖共享本地文件系统，故发命令的 API 副本与
跑模拟的 worker 进程可分处不同主机）：
1. 后端把命令 RPUSH 到 sim:ipc:cmd:{sid} 队列
2. 模拟脚本 LPOP 取命令、执行，并把响应 RPUSH 到 sim:ipc:resp:{sid}:{cid} 信箱
3. 后端 BLPOP 信箱获取结果；存活性由 sim:ipc:alive:{sid} 心跳键判定

键协议与 scripts/_ipc_redis.py（模拟脚本侧）保持字节级一致。
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import redis

from ..core.logger import get_logger
from ..core.settings import settings

logger = get_logger("superfish.simulation_ipc")

# ---- 键协议（与 scripts/_ipc_redis.py 保持字节级一致）----
CMD_KEY = "sim:ipc:cmd:{sid}"
RESP_KEY = "sim:ipc:resp:{sid}:{cid}"
ALIVE_KEY = "sim:ipc:alive:{sid}"
CMD_TTL = 120  # 命令队列兜底 TTL（秒），防孤儿命令长期残留


_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    """进程内复用一个同步 Redis 连接（连接池）。"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
    return _redis_client


class CommandType(StrEnum):
    """命令类型"""

    INTERVIEW = "interview"  # 单个Agent采访
    BATCH_INTERVIEW = "batch_interview"  # 批量采访
    STREAM_INTERVIEW = "stream_interview"  # 单 agent 流式采访（响应经 Redis，不走文件轮询）
    STREAM_BATCH_INTERVIEW = "stream_batch_interview"  # 多 agent 并发流式群访（响应经 Redis）
    CLOSE_ENV = "close_env"  # 关闭环境


class CommandStatus(StrEnum):
    """命令状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """IPC命令"""

    command_id: str
    command_type: CommandType
    args: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IPCCommand":
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class IPCResponse:
    """IPC响应"""

    command_id: str
    status: CommandStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IPCResponse":
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


class SimulationIPCClient:
    """
    模拟IPC客户端（后端使用）

    用于向模拟进程发送命令并等待响应
    """

    def __init__(self, simulation_dir: str):
        """
        初始化IPC客户端

        Args:
            simulation_dir: 模拟数据目录（其 basename 即 simulation_id，用作 Redis 键前缀）
        """
        self.simulation_dir = simulation_dir
        self.simulation_id = os.path.basename(os.path.normpath(simulation_dir))

    def _post(self, command: IPCCommand) -> None:
        """把命令 RPUSH 到该模拟的命令队列（FIFO），并刷新队列兜底 TTL。"""
        r = _get_redis()
        cmd_key = CMD_KEY.format(sid=self.simulation_id)
        r.rpush(cmd_key, json.dumps(command.to_dict(), ensure_ascii=False))
        r.expire(cmd_key, CMD_TTL)

    def send_command(
        self,
        command_type: CommandType,
        args: dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5,  # 保留以兼容旧签名；Redis BLPOP 为阻塞等待，不再轮询
    ) -> IPCResponse:
        """
        发送命令并等待响应（命令入 Redis 队列，响应经 Redis 信箱阻塞等待）

        Args:
            command_type: 命令类型
            args: 命令参数
            timeout: 超时时间（秒）
            poll_interval: 兼容旧签名的占位参数（Redis BLPOP 阻塞等待，无需轮询）

        Returns:
            IPCResponse

        Raises:
            TimeoutError: 等待响应超时
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(command_id=command_id, command_type=command_type, args=args)

        r = _get_redis()
        resp_key = RESP_KEY.format(sid=self.simulation_id, cid=command_id)
        self._post(command)
        logger.info(f"发送IPC命令: {command_type.value}, command_id={command_id}")

        # BLPOP 阻塞等待响应（timeout 取整秒，至少 1s）
        item = r.blpop(resp_key, timeout=max(1, int(timeout)))
        if item is None:
            logger.error(f"等待IPC响应超时: command_id={command_id}")
            raise TimeoutError(f"等待命令响应超时 ({timeout}秒)")

        _, raw = item
        try:
            response = IPCResponse.from_dict(json.loads(raw))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"解析响应失败: {e}")
            raise TimeoutError(f"响应解析失败: {e}") from e

        logger.info(f"收到IPC响应: command_id={command_id}, status={response.status.value}")
        return response

    def send_interview(
        self, agent_id: int, prompt: str, platform: str | None = None, timeout: float = 60.0
    ) -> IPCResponse:
        """
        发送单个Agent采访命令

        Args:
            agent_id: Agent ID
            prompt: 采访问题
            platform: 指定平台（可选）
                - "twitter": 只采访Twitter平台
                - "reddit": 只采访Reddit平台
                - None: 双平台模拟时同时采访两个平台，单平台模拟时采访该平台
            timeout: 超时时间

        Returns:
            IPCResponse，result字段包含采访结果
        """
        args = {"agent_id": agent_id, "prompt": prompt}
        if platform:
            args["platform"] = platform

        return self.send_command(command_type=CommandType.INTERVIEW, args=args, timeout=timeout)

    def post_command(
        self, command_type: CommandType, args: dict[str, Any], command_id: str | None = None
    ) -> str:
        """只写命令文件、不等响应，返回 command_id。

        用于流式采访：子进程把结果逐 token 发布到 Redis，由 SSE 端点消费，无需文件轮询。
        允许调用方预先指定 command_id，以便先订阅 Redis 频道再投递命令、避免漏掉首批 token。
        """
        command_id = command_id or str(uuid.uuid4())
        command = IPCCommand(command_id=command_id, command_type=command_type, args=args)
        self._post(command)
        logger.info(f"投递IPC命令(不等待): {command_type.value}, command_id={command_id}")
        return command_id

    def post_stream_interview(
        self, agent_id: int, prompt: str, platform: str | None = None, command_id: str | None = None
    ) -> str:
        """投递单 agent 流式采访命令，返回 command_id（响应经 Redis 频道）。"""
        args: dict[str, Any] = {"agent_id": agent_id, "prompt": prompt}
        if platform:
            args["platform"] = platform
        return self.post_command(CommandType.STREAM_INTERVIEW, args, command_id=command_id)

    def post_stream_batch_interview(
        self,
        interviews: list[dict[str, Any]],
        platform: str | None = None,
        command_id: str | None = None,
    ) -> str:
        """投递多 agent 并发流式群访命令，返回 command_id（响应经 Redis 频道）。"""
        args: dict[str, Any] = {"interviews": interviews}
        if platform:
            args["platform"] = platform
        return self.post_command(CommandType.STREAM_BATCH_INTERVIEW, args, command_id=command_id)

    def send_batch_interview(
        self, interviews: list[dict[str, Any]], platform: str | None = None, timeout: float = 120.0
    ) -> IPCResponse:
        """
        发送批量采访命令

        Args:
            interviews: 采访列表，每个元素包含 {"agent_id": int, "prompt": str, "platform": str(可选)}
            platform: 默认平台（可选，会被每个采访项的platform覆盖）
                - "twitter": 默认只采访Twitter平台
                - "reddit": 默认只采访Reddit平台
                - None: 双平台模拟时每个Agent同时采访两个平台
            timeout: 超时时间

        Returns:
            IPCResponse，result字段包含所有采访结果
        """
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform

        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW, args=args, timeout=timeout
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """
        发送关闭环境命令

        Args:
            timeout: 超时时间

        Returns:
            IPCResponse
        """
        return self.send_command(command_type=CommandType.CLOSE_ENV, args={}, timeout=timeout)

    def check_env_alive(self) -> bool:
        """
        检查模拟环境是否存活

        通过 Redis 心跳键 sim:ipc:alive:{sid} 判断（模拟进程每轮循环刷新，进程死后 TTL 过期）。
        """
        return read_env_status(self.simulation_id).get("status") == "alive"


def read_env_status(simulation_id: str) -> dict[str, Any]:
    """读取模拟环境的存活/可用性状态（来自 Redis 心跳键）。

    返回 {status, twitter_available, reddit_available, timestamp}；
    键不存在（未启动 / 已回收）时返回 status=stopped。
    """
    default = {
        "status": "stopped",
        "twitter_available": False,
        "reddit_available": False,
        "timestamp": None,
    }
    try:
        raw = _get_redis().get(ALIVE_KEY.format(sid=simulation_id))
    except Exception:
        return default
    if not raw:
        return default
    try:
        status = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
    return {
        "status": status.get("status", "stopped"),
        "twitter_available": status.get("twitter_available", False),
        "reddit_available": status.get("reddit_available", False),
        "timestamp": status.get("timestamp"),
    }


class SimulationIPCServer:
    """
    模拟IPC服务器（模拟脚本端可用的参考实现，基于 Redis）

    从 Redis 命令队列取命令、执行并把响应写回信箱。运行中的模拟脚本各自内置了等价的
    轻量实现（见 scripts/_ipc_redis.py），本类作为同协议的库级参考实现保留。
    """

    def __init__(self, simulation_dir: str):
        """
        初始化IPC服务器

        Args:
            simulation_dir: 模拟数据目录（其 basename 即 simulation_id）
        """
        self.simulation_dir = simulation_dir
        self.simulation_id = os.path.basename(os.path.normpath(simulation_dir))
        self._running = False

    def start(self):
        """标记服务器为运行状态，写存活心跳"""
        self._running = True
        self._update_env_status("alive")

    def stop(self):
        """标记服务器为停止状态"""
        self._running = False
        self._update_env_status("stopped")

    def _update_env_status(self, status: str):
        """更新环境存活心跳键"""
        ttl = 30 if status == "alive" else 5
        _get_redis().set(
            ALIVE_KEY.format(sid=self.simulation_id),
            json.dumps({"status": status, "timestamp": datetime.now().isoformat()}),
            ex=ttl,
        )

    def poll_commands(self) -> IPCCommand | None:
        """非阻塞取一条待处理命令（FIFO）。无命令返回 None。"""
        raw = _get_redis().lpop(CMD_KEY.format(sid=self.simulation_id))
        if not raw:
            return None
        try:
            return IPCCommand.from_dict(json.loads(raw))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"解析命令失败: {e}")
            return None

    def send_response(self, response: IPCResponse):
        """把响应写入 Redis 信箱（带 TTL 兜底）。"""
        key = RESP_KEY.format(sid=self.simulation_id, cid=response.command_id)
        r = _get_redis()
        r.rpush(key, json.dumps(response.to_dict(), ensure_ascii=False))
        r.expire(key, 300)

    def send_success(self, command_id: str, result: dict[str, Any]):
        """发送成功响应"""
        self.send_response(
            IPCResponse(command_id=command_id, status=CommandStatus.COMPLETED, result=result)
        )

    def send_error(self, command_id: str, error: str):
        """发送错误响应"""
        self.send_response(
            IPCResponse(command_id=command_id, status=CommandStatus.FAILED, error=error)
        )
