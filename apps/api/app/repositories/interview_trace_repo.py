"""Interview 轨迹仓储：读取 OASIS 模拟产生的独立 SQLite 库。

与其它 repo 不同：这里访问的不是应用主库（Postgres / ``session_scope``），
而是 OASIS 模拟在运行目录下落地的**每模拟独立 sqlite 文件**
（``{simulation_id}/{platform}_simulation.db``，含 OASIS 自有的 ``trace`` 表）。

因此本 repo 以**只读**方式按路径连接该 sqlite 文件，不接入 Postgres 的
``session_scope``；仅负责把内联在 SimulationRunner 里的 sqlite 访问收拢到数据层，
让 service 不再直连数据库。
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from ..core.logger import get_logger

logger = get_logger("superfish.api.repositories.interview_trace")


class InterviewTraceRepository:
    """OASIS ``{platform}_simulation.db`` 中 ``trace`` 表的只读访问。"""

    @staticmethod
    def list_interviews(
        db_path: str,
        platform_name: str,
        agent_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """读取单个 OASIS 模拟库中的 interview 轨迹。

        Args:
            db_path: OASIS 模拟产生的 sqlite 文件绝对路径；不存在时返回空列表。
            platform_name: 平台标识（reddit/twitter），用于回填到结果。
            agent_id: 指定 Agent（OASIS ``trace.user_id``）；None 表示不过滤。
            limit: 返回上限。

        Returns:
            interview 记录列表（已解析 info JSON）。读取失败时记录日志并返回已得部分。
        """
        if not os.path.exists(db_path):
            return []

        results: list[dict[str, Any]] = []
        try:
            # 只读连接：mode=ro 避免对模拟产物建库/加锁
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                cursor = conn.cursor()
                if agent_id is not None:
                    cursor.execute(
                        """
                        SELECT user_id, info, created_at
                        FROM trace
                        WHERE action = 'interview' AND user_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (agent_id, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT user_id, info, created_at
                        FROM trace
                        WHERE action = 'interview'
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )

                for user_id, info_json, created_at in cursor.fetchall():
                    try:
                        info = json.loads(info_json) if info_json else {}
                    except json.JSONDecodeError:
                        info = {"raw": info_json}

                    results.append(
                        {
                            "agent_id": user_id,
                            "response": info.get("response", info),
                            "prompt": info.get("prompt", ""),
                            "timestamp": created_at,
                            "platform": platform_name,
                        }
                    )
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"读取Interview历史失败 ({platform_name}): {e}")

        return results
