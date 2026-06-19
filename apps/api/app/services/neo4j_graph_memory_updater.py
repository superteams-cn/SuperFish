"""
Neo4j 图谱记忆更新服务
将模拟中的 Agent 活动动态更新到当前项目图谱中。
"""

import json
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import Any

from ..utils.locale import get_locale, set_locale
from ..utils.logger import get_logger
from ..utils.neo4j_graph_utils import get_neo4j_graph_client

logger = get_logger("superfish.neo4j_graph_memory_updater")


@dataclass
class AgentActivity:
    """Agent 活动记录"""

    platform: str
    agent_id: int
    agent_name: str
    action_type: str
    action_args: dict[str, Any]
    round_num: int
    timestamp: str

    def to_episode_text(self) -> str:
        """将活动转换为自然语言描述"""
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        return f"{self.agent_name}: {describe_func()}"

    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        return f"发布了一条帖子：「{content}」" if content else "发布了一条帖子"

    def _describe_like_post(self) -> str:
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        if post_content and post_author:
            return f"点赞了{post_author}的帖子：「{post_content}」"
        elif post_content:
            return f"点赞了一条帖子：「{post_content}」"
        elif post_author:
            return f"点赞了{post_author}的一条帖子"
        return "点赞了一条帖子"

    def _describe_dislike_post(self) -> str:
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        if post_content and post_author:
            return f"踩了{post_author}的帖子：「{post_content}」"
        elif post_content:
            return f"踩了一条帖子：「{post_content}」"
        elif post_author:
            return f"踩了{post_author}的一条帖子"
        return "踩了一条帖子"

    def _describe_repost(self) -> str:
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        if original_content and original_author:
            return f"转发了{original_author}的帖子：「{original_content}」"
        elif original_content:
            return f"转发了一条帖子：「{original_content}」"
        elif original_author:
            return f"转发了{original_author}的一条帖子"
        return "转发了一条帖子"

    def _describe_quote_post(self) -> str:
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get(
            "content", ""
        )
        if original_content and original_author:
            base = f"引用了{original_author}的帖子「{original_content}」"
        elif original_content:
            base = f"引用了一条帖子「{original_content}」"
        elif original_author:
            base = f"引用了{original_author}的一条帖子"
        else:
            base = "引用了一条帖子"
        return base + (f"，并评论道：「{quote_content}」" if quote_content else "")

    def _describe_follow(self) -> str:
        target = self.action_args.get("target_user_name", "")
        return f"关注了用户「{target}」" if target else "关注了一个用户"

    def _describe_create_comment(self) -> str:
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        if content:
            if post_content and post_author:
                return f"在{post_author}的帖子「{post_content}」下评论道：「{content}」"
            elif post_content:
                return f"在帖子「{post_content}」下评论道：「{content}」"
            elif post_author:
                return f"在{post_author}的帖子下评论道：「{content}」"
            return f"评论道：「{content}」"
        return "发表了评论"

    def _describe_like_comment(self) -> str:
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        if comment_content and comment_author:
            return f"点赞了{comment_author}的评论：「{comment_content}」"
        elif comment_content:
            return f"点赞了一条评论：「{comment_content}」"
        elif comment_author:
            return f"点赞了{comment_author}的一条评论"
        return "点赞了一条评论"

    def _describe_dislike_comment(self) -> str:
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        if comment_content and comment_author:
            return f"踩了{comment_author}的评论：「{comment_content}」"
        elif comment_content:
            return f"踩了一条评论：「{comment_content}」"
        elif comment_author:
            return f"踩了{comment_author}的一条评论"
        return "踩了一条评论"

    def _describe_search(self) -> str:
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"搜索了「{query}」" if query else "进行了搜索"

    def _describe_search_user(self) -> str:
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"搜索了用户「{query}」" if query else "搜索了用户"

    def _describe_mute(self) -> str:
        target = self.action_args.get("target_user_name", "")
        return f"屏蔽了用户「{target}」" if target else "屏蔽了一个用户"

    def _describe_generic(self) -> str:
        return f"执行了{self.action_type}操作"


class Neo4jGraphMemoryUpdater:
    """
    Neo4j 图谱记忆更新器

    监控模拟的 actions 日志，将新的 Agent 活动实时写入 Neo4j 图谱。
    按平台分组，每累积 BATCH_SIZE 条活动后批量合并为一个 episode 写入。
    """

    BATCH_SIZE = 5
    PLATFORM_LABELS = {"twitter": "世界1", "reddit": "世界2"}
    SEND_INTERVAL = 0.5
    MAX_RETRIES = 3
    RETRY_DELAY = 2

    def __init__(self, graph_id: str, api_key: str | None = None):
        # api_key 参数保留以兼容现有调用
        self.graph_id = graph_id
        self._client = get_neo4j_graph_client()

        self._activity_queue: Queue = Queue()
        self._platform_buffers: dict[str, list[AgentActivity]] = {
            "twitter": [],
            "reddit": [],
        }
        self._buffer_lock = threading.Lock()
        self._running = False
        self._worker_thread: threading.Thread | None = None

        self._total_activities = 0
        self._total_sent = 0
        self._total_items_sent = 0
        self._failed_count = 0
        self._skipped_count = 0

        logger.info(
            f"GraphMemoryUpdater 初始化完成: graph_id={graph_id}, batch_size={self.BATCH_SIZE}"
        )

    def _get_platform_label(self, platform: str) -> str:
        return self.PLATFORM_LABELS.get(platform.lower(), platform)

    def start(self):
        if self._running:
            return
        current_locale = get_locale()
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(current_locale,),
            daemon=True,
            name=f"GraphMemoryUpdater-{self.graph_id[:8]}",
        )
        self._worker_thread.start()
        logger.info(f"GraphMemoryUpdater 已启动: graph_id={self.graph_id}")

    def stop(self):
        self._running = False
        self._flush_remaining()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        logger.info(
            f"GraphMemoryUpdater 已停止: graph_id={self.graph_id}, "
            f"total={self._total_activities}, sent={self._total_items_sent}, "
            f"failed={self._failed_count}, skipped={self._skipped_count}"
        )

    def add_activity(self, activity: AgentActivity):
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"添加活动到队列: {activity.agent_name} - {activity.action_type}")

    def add_activity_from_dict(self, data: dict[str, Any], platform: str):
        if "event_type" in data:
            return
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        self.add_activity(activity)

    def _worker_loop(self, locale: str = "zh"):
        set_locale(locale)
        while self._running or not self._activity_queue.empty():
            try:
                try:
                    activity = self._activity_queue.get(timeout=1)
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][: self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][
                                self.BATCH_SIZE :
                            ]
                            self._send_batch_activities(batch, platform)
                            time.sleep(self.SEND_INTERVAL)
                except Empty:
                    pass
            except Exception as e:
                logger.error(f"工作循环异常: {e}")
                time.sleep(1)

    def _send_batch_activities(self, activities: list[AgentActivity], platform: str):
        if not activities:
            return

        combined_text = "\n".join(a.to_episode_text() for a in activities)
        platform_label = self._get_platform_label(platform)

        for attempt in range(self.MAX_RETRIES):
            try:
                activity_uuid = (
                    f"activity_{platform}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
                )
                with self._client.driver.session() as session:
                    session.run(
                        """
                        MERGE (a:Entity:SimulationActivity {uuid: $uuid})
                        SET a.name = $name,
                            a.summary = $summary,
                            a.group_id = $group_id,
                            a.attributes_json = $attributes_json,
                            a.created_at = $created_at
                        WITH a
                        UNWIND $agent_names AS agent_name
                        MATCH (agent:Entity {group_id: $group_id})
                        WHERE agent.name = agent_name
                        MERGE (agent)-[r:RELATES_TO {uuid: $uuid + '_' + agent.uuid}]->(a)
                        SET r.name = 'POSTED_ACTIVITY',
                            r.fact = $summary,
                            r.group_id = $group_id,
                            r.attributes_json = '{}',
                            r.created_at = $created_at
                        """,
                        {
                            "uuid": activity_uuid,
                            "name": f"{platform_label}模拟活动",
                            "summary": combined_text,
                            "group_id": self.graph_id,
                            "attributes_json": json.dumps(
                                {
                                    "platform": platform,
                                    "activity_count": len(activities),
                                },
                                ensure_ascii=False,
                            ),
                            "created_at": datetime.now(UTC).isoformat(),
                            "agent_names": list({a.agent_name for a in activities if a.agent_name}),
                        },
                    )
                self._total_sent += 1
                self._total_items_sent += len(activities)
                logger.info(
                    f"成功写入 {len(activities)} 条{platform_label}活动到图谱 {self.graph_id}"
                )
                return

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"写入失败 (尝试 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"写入失败，已重试 {self.MAX_RETRIES} 次: {e}")
                    self._failed_count += 1

    def _flush_remaining(self):
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    self._platform_buffers.setdefault(platform, []).append(activity)
            except Empty:
                break

        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    logger.info(
                        f"发送{self._get_platform_label(platform)}平台剩余的 {len(buffer)} 条活动"
                    )
                    self._send_batch_activities(buffer, platform)
            for p in self._platform_buffers:
                self._platform_buffers[p] = []

    def get_stats(self) -> dict[str, Any]:
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,
            "batches_sent": self._total_sent,
            "items_sent": self._total_items_sent,
            "failed_count": self._failed_count,
            "skipped_count": self._skipped_count,
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,
            "running": self._running,
        }


class Neo4jGraphMemoryManager:
    """管理多个模拟的图谱记忆更新器（接口与原版完全兼容）"""

    _updaters: dict[str, Neo4jGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    _stop_all_done = False

    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> Neo4jGraphMemoryUpdater:
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            updater = Neo4jGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            logger.info(f"创建图谱记忆更新器: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater

    @classmethod
    def get_updater(cls, simulation_id: str) -> Neo4jGraphMemoryUpdater | None:
        return cls._updaters.get(simulation_id)

    @classmethod
    def stop_updater(cls, simulation_id: str):
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"已停止图谱记忆更新器: simulation_id={simulation_id}")

    @classmethod
    def stop_all(cls):
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        with cls._lock:
            for simulation_id, updater in list(cls._updaters.items()):
                try:
                    updater.stop()
                except Exception as e:
                    logger.error(f"停止更新器失败: simulation_id={simulation_id}, error={e}")
            cls._updaters.clear()
            logger.info("已停止所有图谱记忆更新器")

    @classmethod
    def get_all_stats(cls) -> dict[str, dict[str, Any]]:
        return {sid: u.get_stats() for sid, u in cls._updaters.items()}
