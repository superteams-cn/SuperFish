"""
OASIS模拟管理器
管理Twitter和Reddit双平台并行模拟
使用预设脚本 + LLM智能生成配置参数
"""

import json
import os
from collections.abc import Callable
from typing import Any

from ..core.errors import AppError
from ..core.logger import get_logger
from ..domain.simulation import PlatformType, SimulationState, SimulationStatus
from ..repositories.simulation_repo import SimulationRepository
from ..utils import object_store
from ..utils.locale import t
from .graph_entity_reader import GraphEntityReader
from .oasis_profile_generator import OasisProfileGenerator
from .simulation_config_generator import SimulationConfigGenerator

__all__ = [
    "SimulationManager",
    "SimulationState",
    "SimulationStatus",
    "PlatformType",
]

logger = get_logger("superfish.simulation")


class SimulationManager:
    """
    模拟管理器

    核心功能：
    1. 从图谱读取实体并过滤
    2. 生成OASIS Agent Profile
    3. 使用LLM智能生成模拟配置参数
    4. 准备预设脚本所需的所有文件
    """

    # 模拟数据存储目录
    SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), "../../uploads/simulations")

    def __init__(self):
        # 确保运行时本地目录存在（profiles/config/sqlite/日志等运行产物仍落本地）
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)

    def _get_simulation_dir(self, simulation_id: str) -> str:
        """获取模拟数据目录（运行时本地工作目录）"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir

    @staticmethod
    def _s3_key(simulation_id: str, name: str) -> str:
        """模拟相关文件在对象存储中的 key。"""
        return f"simulations/{simulation_id}/{name}"

    def _mirror_to_s3(self, simulation_id: str, filename: str) -> None:
        """把本地的模拟文件（config/profiles）镜像到对象存储，失败仅告警。"""
        local_path = os.path.join(self._get_simulation_dir(simulation_id), filename)
        if not os.path.exists(local_path):
            return
        try:
            object_store.upload_file(self._s3_key(simulation_id, filename), local_path)
        except Exception as exc:
            logger.warning(f"镜像模拟文件到对象存储失败 {filename}: {exc}")

    def _save_simulation_state(self, state: SimulationState):
        """保存模拟状态到 Postgres（upsert，委托 SimulationRepository）。"""
        SimulationRepository.save(state)

    def _load_simulation_state(self, simulation_id: str) -> SimulationState | None:
        """从 Postgres 读取模拟状态（委托 SimulationRepository）。"""
        return SimulationRepository.get(simulation_id)

    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        user_id: str = "",
    ) -> SimulationState:
        """
        创建新的模拟

        Args:
            project_id: 项目ID
            graph_id: 图谱ID
            enable_twitter: 是否启用Twitter模拟
            enable_reddit: 是否启用Reddit模拟
            user_id: 所属用户（从所属项目继承）

        Returns:
            SimulationState
        """
        import uuid

        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"

        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            user_id=user_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
        )

        self._save_simulation_state(state)
        logger.info(f"创建模拟: {simulation_id}, project={project_id}, graph={graph_id}")

        return state

    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: list[str] | None = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Callable | None = None,
        parallel_profile_count: int = 3,
    ) -> SimulationState:
        """
        准备模拟环境（全程自动化）

        步骤：
        1. 从图谱读取并过滤实体
        2. 为每个实体生成OASIS Agent Profile（可选LLM增强，支持并行）
        3. 使用LLM智能生成模拟配置参数（时间、活跃度、发言频率等）
        4. 保存配置文件和Profile文件
        5. 复制预设脚本到模拟目录

        Args:
            simulation_id: 模拟ID
            simulation_requirement: 模拟需求描述（用于LLM生成配置）
            document_text: 原始文档内容（用于LLM理解背景）
            defined_entity_types: 预定义的实体类型（可选）
            use_llm_for_profiles: 是否使用LLM生成详细人设
            progress_callback: 进度回调函数 (stage, progress, message)
            parallel_profile_count: 并行生成人设的数量，默认3

        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise AppError(f"模拟不存在: {simulation_id}", status=404)

        try:
            state.status = SimulationStatus.PREPARING
            self._save_simulation_state(state)

            sim_dir = self._get_simulation_dir(simulation_id)

            # ========== 阶段1: 读取并过滤实体 ==========
            if progress_callback:
                progress_callback("reading", 0, t("progress.connectingGraph"))

            reader = GraphEntityReader()

            if progress_callback:
                progress_callback("reading", 30, t("progress.readingNodeData"))

            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True,
            )

            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)

            if progress_callback:
                progress_callback(
                    "reading",
                    100,
                    t("progress.readingComplete", count=filtered.filtered_count),
                    current=filtered.filtered_count,
                    total=filtered.filtered_count,
                )

            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "没有找到符合条件的实体，请检查图谱是否正确构建"
                self._save_simulation_state(state)
                return state

            # ========== 阶段2: 生成Agent Profile ==========
            total_entities = len(filtered.entities)

            if progress_callback:
                progress_callback(
                    "generating_profiles",
                    0,
                    t("progress.startGenerating"),
                    current=0,
                    total=total_entities,
                )

            # 传入graph_id以启用图谱检索功能，获取更丰富的上下文
            generator = OasisProfileGenerator(graph_id=state.graph_id)

            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles",
                        int(current / total * 100),
                        msg,
                        current=current,
                        total=total,
                        item_name=msg,
                    )

            # 设置实时保存的文件路径（优先使用 Reddit JSON 格式）
            realtime_output_path = None
            realtime_platform = "reddit"
            if state.enable_reddit:
                realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                realtime_platform = "reddit"
            elif state.enable_twitter:
                realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                realtime_platform = "twitter"

            profiles = generator.generate_profiles_from_entities(
                entities=filtered.entities,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                graph_id=state.graph_id,  # 传入graph_id用于图谱检索
                parallel_count=parallel_profile_count,  # 并行生成数量
                realtime_output_path=realtime_output_path,  # 实时保存路径
                output_platform=realtime_platform,  # 输出格式
            )

            state.profiles_count = len(profiles)

            # 保存Profile文件（注意：Twitter使用CSV格式，Reddit使用JSON格式）
            # Reddit 已经在生成过程中实时保存了，这里再保存一次确保完整性
            if progress_callback:
                progress_callback(
                    "generating_profiles",
                    95,
                    t("progress.savingProfiles"),
                    current=total_entities,
                    total=total_entities,
                )

            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit",
                )

            if state.enable_twitter:
                # Twitter使用CSV格式！这是OASIS的要求
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter",
                )

            if progress_callback:
                progress_callback(
                    "generating_profiles",
                    100,
                    t("progress.profilesComplete", count=len(profiles)),
                    current=len(profiles),
                    total=len(profiles),
                )

            # ========== 阶段3: LLM智能生成模拟配置 ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0, t("progress.analyzingRequirements"), current=0, total=3
                )

            config_generator = SimulationConfigGenerator()

            if progress_callback:
                progress_callback(
                    "generating_config", 30, t("progress.callingLLMConfig"), current=1, total=3
                )

            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit,
            )

            if progress_callback:
                progress_callback(
                    "generating_config", 70, t("progress.savingConfigFiles"), current=2, total=3
                )

            # 保存配置文件
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(sim_params.to_json())

            # 把准备阶段产物镜像到对象存储，使 start 可在其他节点物化运行
            self._mirror_to_s3(simulation_id, "simulation_config.json")
            if state.enable_reddit:
                self._mirror_to_s3(simulation_id, "reddit_profiles.json")
            if state.enable_twitter:
                self._mirror_to_s3(simulation_id, "twitter_profiles.csv")

            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning
            # 冗余历史摘要字段：首页历史据此批量展示，免去逐条回源 config
            state.simulation_requirement = sim_params.simulation_requirement or ""
            state.total_simulation_hours = int(
                getattr(sim_params.time_config, "total_simulation_hours", 0) or 0
            )
            state.minutes_per_round = int(
                getattr(sim_params.time_config, "minutes_per_round", 0) or 0
            )

            if progress_callback:
                progress_callback(
                    "generating_config", 100, t("progress.configComplete"), current=3, total=3
                )

            # 注意：运行脚本保留在 backend/scripts/ 目录，不再复制到模拟目录
            # 启动模拟时，simulation_runner 会从 scripts/ 目录运行脚本

            # 更新状态
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)

            logger.info(
                f"模拟准备完成: {simulation_id}, "
                f"entities={state.entities_count}, profiles={state.profiles_count}"
            )

            return state

        except Exception as e:
            logger.error(f"模拟准备失败: {simulation_id}, error={str(e)}")
            import traceback

            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise

    def get_simulation(self, simulation_id: str) -> SimulationState | None:
        """获取模拟状态"""
        return self._load_simulation_state(simulation_id)

    # RunnerStatus(运行态) → SimulationStatus(sim 级) 的终态映射。
    # SimulationStatus 无 INTERRUPTED，被外部杀死/崩溃但可重启者归入 STOPPED。
    _RUNNER_TO_SIM_TERMINAL = {
        "completed": SimulationStatus.COMPLETED,
        "failed": SimulationStatus.FAILED,
        "interrupted": SimulationStatus.STOPPED,
        "stopped": SimulationStatus.STOPPED,
    }

    def sync_terminal_status(self, simulation_id: str, runner_status: Any) -> None:
        """把 sim 级 SimulationStatus 同步到与 runner 终态一致。

        监控线程/对账器把运行态判成终态(COMPLETED/INTERRUPTED/FAILED)时只回写 run_state，
        历史上不动 sim 级状态——导致异常结束的模拟在 Postgres 永远停留 RUNNING，配额闸门
        (run.py)把僵尸算作"在跑"而泄漏配额。此方法补上这一步，失败仅告警(非关键路径)。
        """
        target = self._RUNNER_TO_SIM_TERMINAL.get(
            str(getattr(runner_status, "value", runner_status))
        )
        if target is None:
            return
        try:
            state = self._load_simulation_state(simulation_id)
            if state is None or state.status == target:
                return
            # 仅从"活跃态"降级，避免覆盖用户显式置位(如 PAUSED 不在此列、已是终态则上面已返回)
            if state.status not in (SimulationStatus.RUNNING, SimulationStatus.PREPARING):
                return
            state.status = target
            self._save_simulation_state(state)
            logger.info(f"[{simulation_id}] sim 级状态同步终态: {target.value}")
        except Exception as exc:
            logger.warning(f"[{simulation_id}] 同步 sim 级终态失败(忽略): {exc}")

    def list_simulations(
        self, project_id: str | None = None, user_id: str | None = None
    ) -> list[SimulationState]:
        """列出所有模拟（Postgres，按创建时间倒序）；传 user_id 时只返回该用户的。"""
        return SimulationRepository.list(project_id=project_id, user_id=user_id)

    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> list[dict[str, Any]]:
        """获取模拟的Agent Profile"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise AppError(f"模拟不存在: {simulation_id}", status=404)

        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(sim_dir, f"{platform}_profiles.json")

        if os.path.exists(profile_path):
            with open(profile_path, encoding="utf-8") as f:
                return json.load(f)

        # 本地缺失则回退对象存储（如运行在 prepare 之外的节点）
        raw = object_store.get_text(self._s3_key(simulation_id, f"{platform}_profiles.json"))
        return json.loads(raw) if raw else []

    def get_simulation_config(self, simulation_id: str) -> dict[str, Any] | None:
        """获取模拟配置"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")

        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)

        # 本地缺失则回退对象存储
        raw = object_store.get_text(self._s3_key(simulation_id, "simulation_config.json"))
        return json.loads(raw) if raw else None

    def get_run_instructions(self, simulation_id: str) -> dict[str, str]:
        """获取运行说明"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts"))

        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. 激活conda环境: conda activate SuperFish\n"
                f"2. 运行模拟 (脚本位于 {scripts_dir}):\n"
                f"   - 单独运行Twitter: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - 单独运行Reddit: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - 并行运行双平台: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            ),
        }
