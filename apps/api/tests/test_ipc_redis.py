"""提交1 验证：Redis IPC 总线的客户端↔服务端往返与存活心跳。

覆盖位置无关控制面的核心契约：
- 客户端 send_command 投递命令 → 服务端 poll 取到 → 服务端回响应 → 客户端阻塞拿到；
- post_command（流式，不等待）只入队；
- 存活心跳 touch_alive/mark_stopped 与 read_env_status/check_env_alive 一致；
- 键协议两侧字节级一致。

需要本地 Redis；不可用时整文件 skip（与 CI 无 redis 环境兼容）。
"""

import sys
import threading
import uuid
from pathlib import Path

import pytest

# 让 scripts/_ipc_redis 可导入（模拟脚本侧的服务端实现）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.services.simulation_ipc import (  # noqa: E402
    ALIVE_KEY,
    CMD_KEY,
    CommandType,
    SimulationIPCClient,
    read_env_status,
)


def _redis_available() -> bool:
    try:
        import redis

        from app.core.settings import settings

        redis.Redis.from_url(settings.redis_url).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="本地 Redis 不可用")


@pytest.fixture
def server_and_client(tmp_path):
    """构造一对 (服务端总线, 客户端)，共用一个随机 simulation_id；用例结束清理键。"""
    from _ipc_redis import RedisIPCServer

    sid = f"test-{uuid.uuid4().hex[:8]}"
    sim_dir = tmp_path / sid
    sim_dir.mkdir()
    bus = RedisIPCServer(sid)
    client = SimulationIPCClient(str(sim_dir))
    assert client.simulation_id == sid  # basename 即 sid
    yield sid, bus, client
    r = bus._redis()
    r.delete(CMD_KEY.format(sid=sid), ALIVE_KEY.format(sid=sid))


def test_command_response_roundtrip(server_and_client):
    sid, bus, client = server_and_client

    # 服务端在后台等命令并回响应（模拟脚本的 process_commands 循环）
    def serve():
        for _ in range(200):  # 最多轮询 ~2s
            cmd = bus.poll_command()
            if cmd:
                assert cmd["command_type"] == CommandType.INTERVIEW.value
                bus.send_response(
                    cmd["command_id"], "completed", result={"echo": cmd["args"]["prompt"]}
                )
                return
            import time

            time.sleep(0.01)

    t = threading.Thread(target=serve)
    t.start()

    resp = client.send_command(
        CommandType.INTERVIEW, {"agent_id": 1, "prompt": "你好"}, timeout=5
    )
    t.join()

    assert resp.status.value == "completed"
    assert resp.result == {"echo": "你好"}


def test_post_command_enqueues_only(server_and_client):
    sid, bus, client = server_and_client

    cid = client.post_command(CommandType.STREAM_INTERVIEW, {"agent_id": 2, "prompt": "hi"})
    # 不等待响应，命令应已入队，可被服务端取到
    cmd = bus.poll_command()
    assert cmd is not None
    assert cmd["command_id"] == cid
    assert cmd["command_type"] == CommandType.STREAM_INTERVIEW.value


def test_alive_heartbeat(server_and_client):
    sid, bus, client = server_and_client

    # 未心跳前：stopped
    assert read_env_status(sid)["status"] == "stopped"
    assert client.check_env_alive() is False

    # 心跳后：alive，且带可用性
    bus.touch_alive(
        {"status": "alive", "twitter_available": True, "reddit_available": False, "timestamp": "t"}
    )
    status = read_env_status(sid)
    assert status["status"] == "alive"
    assert status["twitter_available"] is True
    assert status["reddit_available"] is False
    assert client.check_env_alive() is True

    # 标记停止后回到 stopped
    bus.mark_stopped({"status": "stopped", "timestamp": "t"})
    assert read_env_status(sid)["status"] == "stopped"


def test_send_command_timeout(server_and_client):
    sid, bus, client = server_and_client
    # 无服务端应答 → 超时
    with pytest.raises(TimeoutError):
        client.send_command(CommandType.INTERVIEW, {"agent_id": 9, "prompt": "x"}, timeout=1)
