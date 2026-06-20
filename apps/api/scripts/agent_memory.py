"""
Agent 记忆持久化 / 恢复工具。

OASIS 的 SocialAgent 继承自 camel 的 ChatAgent，其全程对话记忆存在
`agent.memory`（ChatHistoryMemory）底层的 KV storage 里。采访（perform_interview）
靠这块记忆回答。但该记忆只在进程内存，进程退出即丢——为支持"模拟跑完后按需唤醒
环境再采访"，需要把它落盘、唤醒时灌回。

关键点：
- dump 走 `storage.load()` 拿**全量** record（已是 MemoryRecord.to_dict() 的 dict），
  不能用 `memory.retrieve()`（会被 window_size 截断，丢早期记忆）。
- restore 用 `memory.write_records([MemoryRecord.from_dict(d) ...])` 灌回。
- 文件落在 `{simulation_dir}/agent_memory/{platform}.json`，随 simulations/{sid}/
  前缀同步到 S3、唤醒时随 download_prefix_to_dir 一起取回。
"""

import json
import os
from typing import Any, Dict, Optional

MEMORY_DIRNAME = "agent_memory"


def memory_path(simulation_dir: str, platform: str) -> str:
    return os.path.join(simulation_dir, MEMORY_DIRNAME, f"{platform}.json")


def _agent_records(agent) -> Optional[list]:
    """取单个 agent 的全量记忆 record（dict 列表），失败返回 None。"""
    try:
        return agent.memory._chat_history_block.storage.load()
    except Exception as e:  # noqa: BLE001 — 单个 agent 失败不应影响整体
        print(f"[memory] 读取 agent 记忆失败: {e}")
        return None


def dump_memories(simulation_dir: str, platform: str, agent_graph) -> int:
    """
    把某平台所有 agent 的全量记忆 dump 到 {simulation_dir}/agent_memory/{platform}.json。
    返回成功导出的 agent 数。agent_graph 为 None 时跳过。
    """
    if agent_graph is None:
        return 0
    data: Dict[str, Any] = {}
    try:
        for agent_id, agent in agent_graph.get_agents():
            records = _agent_records(agent)
            if records is not None:
                data[str(agent_id)] = records
    except Exception as e:  # noqa: BLE001
        print(f"[memory] 遍历 {platform} agent_graph 失败: {e}")
        return 0

    path = memory_path(simulation_dir, platform)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"[memory] 已导出 {platform} 记忆: {len(data)} 个 agent → {path}")
    return len(data)


def restore_memories(simulation_dir: str, platform: str, agent_graph) -> int:
    """
    从 {simulation_dir}/agent_memory/{platform}.json 把记忆灌回 agent_graph 各 agent。
    返回成功恢复的 agent 数。文件缺失或 agent_graph 为 None 时返回 0。
    """
    if agent_graph is None:
        return 0
    path = memory_path(simulation_dir, platform)
    if not os.path.exists(path):
        print(f"[memory] 未找到 {platform} 记忆快照（{path}），跳过恢复")
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"[memory] 解析 {platform} 记忆快照失败: {e}")
        return 0

    # 延迟导入，避免非恢复路径强依赖 camel 细节
    from camel.memories import MemoryRecord

    restored = 0
    for agent_id, agent in agent_graph.get_agents():
        records = data.get(str(agent_id))
        if not records:
            continue
        try:
            agent.memory.clear()
            agent.memory.write_records([MemoryRecord.from_dict(r) for r in records])
            restored += 1
        except Exception as e:  # noqa: BLE001
            print(f"[memory] 恢复 agent {agent_id} 记忆失败: {e}")
    print(f"[memory] 已恢复 {platform} 记忆: {restored} 个 agent")
    return restored
