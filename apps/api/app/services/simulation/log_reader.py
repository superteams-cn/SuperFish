"""动作日志读取：从模拟运行目录解析 actions.jsonl，汇总动作/时间线/Agent 统计。

从 SimulationRunner 抽出，全部为纯函数（按 ``run_state_dir`` + ``simulation_id`` 读文件，
不依赖类级状态）。SimulationRunner 以薄委托调用并传入 ``RUN_STATE_DIR``。
"""

import json
import os
from typing import Any

from ...domain.run_state import AgentAction


def read_actions_from_file(
    file_path: str,
    default_platform: str | None = None,
    platform_filter: str | None = None,
    agent_id: int | None = None,
    round_num: int | None = None,
) -> list[AgentAction]:
    """从单个动作文件读取动作（跳过事件记录与无 agent_id 的行，支持平台/Agent/轮次过滤）。"""
    if not os.path.exists(file_path):
        return []

    actions = []
    with open(file_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                # 跳过非动作记录（simulation_start/round_start/round_end 等事件）
                if "event_type" in data:
                    continue
                # 跳过没有 agent_id 的记录（非 Agent 动作）
                if "agent_id" not in data:
                    continue

                record_platform = data.get("platform") or default_platform or ""
                if platform_filter and record_platform != platform_filter:
                    continue
                if agent_id is not None and data.get("agent_id") != agent_id:
                    continue
                if round_num is not None and data.get("round") != round_num:
                    continue

                actions.append(
                    AgentAction(
                        round_num=data.get("round", 0),
                        timestamp=data.get("timestamp", ""),
                        platform=record_platform,
                        agent_id=data.get("agent_id", 0),
                        agent_name=data.get("agent_name", ""),
                        action_type=data.get("action_type", ""),
                        action_args=data.get("action_args", {}),
                        result=data.get("result"),
                        success=data.get("success", True),
                    )
                )
            except json.JSONDecodeError:
                continue
    return actions


def get_all_actions(
    run_state_dir: str,
    simulation_id: str,
    platform: str | None = None,
    agent_id: int | None = None,
    round_num: int | None = None,
) -> list[AgentAction]:
    """读取所有平台的完整动作历史（按时间戳倒序，无分页）。"""
    sim_dir = os.path.join(run_state_dir, simulation_id)
    actions: list[AgentAction] = []

    if not platform or platform == "twitter":
        actions.extend(
            read_actions_from_file(
                os.path.join(sim_dir, "twitter", "actions.jsonl"),
                default_platform="twitter",
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num,
            )
        )
    if not platform or platform == "reddit":
        actions.extend(
            read_actions_from_file(
                os.path.join(sim_dir, "reddit", "actions.jsonl"),
                default_platform="reddit",
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num,
            )
        )

    # 分平台文件不存在时回退旧的单一文件格式
    if not actions:
        actions = read_actions_from_file(
            os.path.join(sim_dir, "actions.jsonl"),
            default_platform=None,
            platform_filter=platform,
            agent_id=agent_id,
            round_num=round_num,
        )

    actions.sort(key=lambda x: x.timestamp, reverse=True)
    return actions


def get_actions(
    run_state_dir: str,
    simulation_id: str,
    limit: int = 100,
    offset: int = 0,
    platform: str | None = None,
    agent_id: int | None = None,
    round_num: int | None = None,
) -> list[AgentAction]:
    """获取动作历史（带分页）。"""
    actions = get_all_actions(
        run_state_dir, simulation_id, platform=platform, agent_id=agent_id, round_num=round_num
    )
    return actions[offset : offset + limit]


def get_timeline(
    run_state_dir: str, simulation_id: str, start_round: int = 0, end_round: int | None = None
) -> list[dict[str, Any]]:
    """按轮次汇总时间线。"""
    actions = get_actions(run_state_dir, simulation_id, limit=10000)
    rounds: dict[int, dict[str, Any]] = {}

    for action in actions:
        round_num = action.round_num
        if round_num < start_round:
            continue
        if end_round is not None and round_num > end_round:
            continue

        if round_num not in rounds:
            rounds[round_num] = {
                "round_num": round_num,
                "twitter_actions": 0,
                "reddit_actions": 0,
                "active_agents": set(),
                "action_types": {},
                "first_action_time": action.timestamp,
                "last_action_time": action.timestamp,
            }
        r = rounds[round_num]
        if action.platform == "twitter":
            r["twitter_actions"] += 1
        else:
            r["reddit_actions"] += 1
        r["active_agents"].add(action.agent_id)
        r["action_types"][action.action_type] = r["action_types"].get(action.action_type, 0) + 1
        r["last_action_time"] = action.timestamp

    result = []
    for round_num in sorted(rounds.keys()):
        r = rounds[round_num]
        result.append(
            {
                "round_num": round_num,
                "twitter_actions": r["twitter_actions"],
                "reddit_actions": r["reddit_actions"],
                "total_actions": r["twitter_actions"] + r["reddit_actions"],
                "active_agents_count": len(r["active_agents"]),
                "active_agents": list(r["active_agents"]),
                "action_types": r["action_types"],
                "first_action_time": r["first_action_time"],
                "last_action_time": r["last_action_time"],
            }
        )
    return result


def get_agent_stats(run_state_dir: str, simulation_id: str) -> list[dict[str, Any]]:
    """获取每个 Agent 的统计信息（按总动作数倒序）。"""
    actions = get_actions(run_state_dir, simulation_id, limit=10000)
    agent_stats: dict[int, dict[str, Any]] = {}

    for action in actions:
        agent_id = action.agent_id
        if agent_id not in agent_stats:
            agent_stats[agent_id] = {
                "agent_id": agent_id,
                "agent_name": action.agent_name,
                "total_actions": 0,
                "twitter_actions": 0,
                "reddit_actions": 0,
                "action_types": {},
                "first_action_time": action.timestamp,
                "last_action_time": action.timestamp,
            }
        stats = agent_stats[agent_id]
        stats["total_actions"] += 1
        if action.platform == "twitter":
            stats["twitter_actions"] += 1
        else:
            stats["reddit_actions"] += 1
        stats["action_types"][action.action_type] = (
            stats["action_types"].get(action.action_type, 0) + 1
        )
        stats["last_action_time"] = action.timestamp

    return sorted(agent_stats.values(), key=lambda x: x["total_actions"], reverse=True)
