"""
模拟相关 API 路由（FastAPI 版）

Step2: Neo4j 实体读取与过滤、OASIS 模拟准备与运行（全程自动化）。
响应沿用 {"success": ..., "data"/"error": ...} 信封，保持与前端契约一致。

注意路由声明顺序：FastAPI 按声明顺序匹配，所有字面量路径
（/create、/prepare、/list、/history、/start 等）以及多段动态路径
必须声明在单段动态路径 /{simulation_id} 之前，否则会被其捕获。
"""

import csv
import json
import os
import threading
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..deps import use_locale
from ..models.project import ProjectManager
from ..schemas.simulation import (
    CloseEnvRequest,
    CreateSimulationRequest,
    EnvStatusRequest,
    GenerateProfilesRequest,
    InterviewAgentRequest,
    InterviewAllRequest,
    InterviewBatchRequest,
    InterviewHistoryRequest,
    PrepareSimulationRequest,
    PrepareStatusRequest,
    StartSimulationRequest,
    StopSimulationRequest,
)
from ..services.neo4j_entity_reader import Neo4jEntityReader
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..settings import settings
from ..utils.locale import get_locale, set_locale, t
from ..utils.logger import get_logger

# 整个模拟路由统一在请求开始时解析语言
router = APIRouter(dependencies=[Depends(use_locale)])

logger = get_logger("superfish.api.simulation")


def _error(message: str, status: int, **extra) -> JSONResponse:
    """构造错误响应，保持统一信封。"""
    body = {"success": False, "error": message}
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


# Interview prompt 优化前缀
# 添加此前缀可以避免 Agent 调用工具，直接用文本回复
INTERVIEW_PROMPT_PREFIX = "结合你的人设、所有的过往记忆与行动，不调用任何工具直接用文本回复我："


def optimize_interview_prompt(prompt: str) -> str:
    """
    优化 Interview 提问，添加前缀避免 Agent 调用工具

    Args:
        prompt: 原始提问

    Returns:
        优化后的提问
    """
    if not prompt:
        return prompt
    # 避免重复添加前缀
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    检查模拟是否已经准备完成（基于 Postgres 状态 + 对象存储中的配置）。

    判定条件：模拟存在、config_generated=True，且配置可获取（本地或对象存储）。

    Args:
        simulation_id: 模拟ID

    Returns:
        (is_prepared: bool, info: dict)
    """
    simulation_manager = SimulationManager()

    state = simulation_manager.get_simulation(simulation_id)
    if state is None:
        return False, {"reason": "模拟不存在"}

    status = state.status.value
    config_generated = state.config_generated
    logger.debug(
        f"检测模拟准备状态: {simulation_id}, status={status}, config_generated={config_generated}"
    )

    prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
    if not (status in prepared_statuses and config_generated):
        logger.warning(
            f"模拟 {simulation_id} 检测结果: 未准备完成 "
            f"(status={status}, config_generated={config_generated})"
        )
        return False, {
            "reason": f"状态未就绪或配置未生成: status={status}, config_generated={config_generated}",
            "status": status,
            "config_generated": config_generated,
        }

    # 校验配置确实可获取（本地缺失时回退对象存储）
    if simulation_manager.get_simulation_config(simulation_id) is None:
        return False, {"reason": "缺少模拟配置 simulation_config.json", "status": status}

    # preparing 但配置已生成 → 自动置为 ready
    if status == "preparing":
        try:
            state.status = SimulationStatus.READY
            simulation_manager._save_simulation_state(state)
            status = "ready"
            logger.info(f"自动更新模拟状态: {simulation_id} preparing -> ready")
        except Exception as e:
            logger.warning(f"自动更新状态失败: {e}")

    logger.info(f"模拟 {simulation_id} 检测结果: 已准备完成 (status={status})")
    return True, {
        "status": status,
        "entities_count": state.entities_count,
        "profiles_count": state.profiles_count,
        "entity_types": state.entity_types,
        "config_generated": config_generated,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def _get_report_id_for_simulation(simulation_id: str) -> str | None:
    """获取 simulation 对应的最新 report_id（Postgres）。"""
    try:
        from ..services.report_agent import ReportManager

        report = ReportManager.get_report_by_simulation(simulation_id)
        return report.report_id if report else None
    except Exception as e:
        logger.warning(f"查找 simulation {simulation_id} 的 report 失败: {e}")
        return None


# ============== 实体读取接口 ==============


@router.get("/entities/{graph_id}")
def get_graph_entities(graph_id: str, entity_types: str = "", enrich: str = "true"):
    """
    获取图谱中的所有实体（已过滤）

    只返回符合预定义实体类型的节点（Labels 不只是 Entity 的节点）

    Query 参数：
        entity_types: 逗号分隔的实体类型列表（可选，用于进一步过滤）
        enrich: 是否获取相关边信息（默认 true）
    """
    try:
        if not settings.neo4j_uri:
            return _error(t("api.neo4jConfigMissing"), 500)

        entity_types_str = entity_types
        # 注意：循环变量改名为 et，避免遮蔽翻译函数 t
        entity_types_list = (
            [et.strip() for et in entity_types_str.split(",") if et.strip()]
            if entity_types_str
            else None
        )
        enrich_bool = enrich.lower() == "true"

        logger.info(
            f"获取图谱实体: graph_id={graph_id}, entity_types={entity_types_list}, enrich={enrich_bool}"
        )

        reader = Neo4jEntityReader()
        result = reader.filter_defined_entities(
            graph_id=graph_id, defined_entity_types=entity_types_list, enrich_with_edges=enrich_bool
        )

        return {"success": True, "data": result.to_dict()}

    except Exception as e:
        logger.error(f"获取图谱实体失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/entities/{graph_id}/by-type/{entity_type}")
def get_entities_by_type(graph_id: str, entity_type: str, enrich: str = "true"):
    """获取指定类型的所有实体"""
    try:
        if not settings.neo4j_uri:
            return _error(t("api.neo4jConfigMissing"), 500)

        enrich_bool = enrich.lower() == "true"

        reader = Neo4jEntityReader()
        entities = reader.get_entities_by_type(
            graph_id=graph_id, entity_type=entity_type, enrich_with_edges=enrich_bool
        )

        return {
            "success": True,
            "data": {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": [e.to_dict() for e in entities],
            },
        }

    except Exception as e:
        logger.error(f"获取实体失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/entities/{graph_id}/{entity_uuid}")
def get_entity_detail(graph_id: str, entity_uuid: str):
    """获取单个实体的详细信息"""
    try:
        if not settings.neo4j_uri:
            return _error(t("api.neo4jConfigMissing"), 500)

        reader = Neo4jEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)

        if not entity:
            return _error(t("api.entityNotFound", id=entity_uuid), 404)

        return {"success": True, "data": entity.to_dict()}

    except Exception as e:
        logger.error(f"获取实体详情失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 模拟管理接口 ==============


@router.post("/create")
def create_simulation(req: CreateSimulationRequest):
    """
    创建新的模拟

    注意：max_rounds 等参数由 LLM 智能生成，无需手动设置

    请求（JSON）：
        {
            "project_id": "proj_xxxx",      // 必填
            "graph_id": "superfish_xxxx",    // 可选，如不提供则从 project 获取
            "enable_twitter": true,          // 可选，默认 true
            "enable_reddit": true            // 可选，默认 true
        }
    """
    try:
        project_id = req.project_id
        if not project_id:
            return _error(t("api.requireProjectId"), 400)

        project = ProjectManager.get_project(project_id)
        if not project:
            return _error(t("api.projectNotFound", id=project_id), 404)

        graph_id = req.graph_id or project.graph_id
        if not graph_id:
            return _error(t("api.graphNotBuilt"), 400)

        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=req.enable_twitter,
            enable_reddit=req.enable_reddit,
        )

        return {"success": True, "data": state.to_dict()}

    except Exception as e:
        logger.error(f"创建模拟失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/prepare")
def prepare_simulation(req: PrepareSimulationRequest):
    """
    准备模拟环境（异步任务，LLM 智能生成所有参数）

    这是一个耗时操作，接口会立即返回 task_id，
    使用 POST /api/simulation/prepare/status 查询进度

    特性：
    - 自动检测已完成的准备工作，避免重复生成
    - 如果已准备完成，直接返回已有结果
    - 支持强制重新生成（force_regenerate=true）
    """
    from ..models.task import TaskManager, TaskStatus

    try:
        simulation_id = req.simulation_id
        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        # 检查是否强制重新生成
        force_regenerate = req.force_regenerate
        logger.info(
            f"开始处理 /prepare 请求: simulation_id={simulation_id}, force_regenerate={force_regenerate}"
        )

        # 检查是否已经准备完成（避免重复生成）
        if not force_regenerate:
            logger.debug(f"检查模拟 {simulation_id} 是否已准备完成...")
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            logger.debug(f"检查结果: is_prepared={is_prepared}, prepare_info={prepare_info}")
            if is_prepared:
                logger.info(f"模拟 {simulation_id} 已准备完成，跳过重复生成")
                return {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "message": t("api.alreadyPrepared"),
                        "already_prepared": True,
                        "prepare_info": prepare_info,
                    },
                }
            else:
                logger.info(f"模拟 {simulation_id} 未准备完成，将启动准备任务")

        # 从项目获取必要信息
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return _error(t("api.projectNotFound", id=state.project_id), 404)

        # 获取模拟需求
        simulation_requirement = project.simulation_requirement or ""
        if not simulation_requirement:
            return _error(t("api.projectMissingRequirement"), 400)

        # 获取文档文本
        document_text = ProjectManager.get_extracted_text(state.project_id) or ""

        entity_types_list = req.entity_types
        use_llm_for_profiles = req.use_llm_for_profiles
        parallel_profile_count = req.parallel_profile_count

        # ========== 同步获取实体数量（在后台任务启动前） ==========
        # 这样前端在调用 prepare 后立即就能获取到预期 Agent 总数
        try:
            logger.info(f"同步获取实体数量: graph_id={state.graph_id}")
            reader = Neo4jEntityReader()
            # 快速读取实体（不需要边信息，只统计数量）
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False,  # 不获取边信息，加快速度
            )
            # 保存实体数量到状态（供前端立即获取）
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(
                f"预期实体数量: {filtered_preview.filtered_count}, 类型: {filtered_preview.entity_types}"
            )
        except Exception as e:
            logger.warning(f"同步获取实体数量失败（将在后台任务中重试）: {e}")
            # 失败不影响后续流程，后台任务会重新获取

        # 创建异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={"simulation_id": simulation_id, "project_id": state.project_id},
        )

        # 更新模拟状态（包含预先获取的实体数量）
        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)

        # 在派生后台线程前捕获当前语言
        current_locale = get_locale()

        # 定义后台任务
        def run_prepare():
            set_locale(current_locale)
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message=t("progress.startPreparingEnv"),
                )

                # 准备模拟（带进度回调）
                # 存储阶段进度详情
                stage_details = {}

                def progress_callback(stage, progress, message, **kwargs):
                    # 计算总进度
                    stage_weights = {
                        "reading": (0, 20),  # 0-20%
                        "generating_profiles": (20, 70),  # 20-70%
                        "generating_config": (70, 90),  # 70-90%
                        "copying_scripts": (90, 100),  # 90-100%
                    }

                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)

                    # 构建详细进度信息
                    stage_names = {
                        "reading": t("progress.readingGraphEntities"),
                        "generating_profiles": t("progress.generatingProfiles"),
                        "generating_config": t("progress.generatingSimConfig"),
                        "copying_scripts": t("progress.preparingScripts"),
                    }

                    stage_index = (
                        list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    )
                    total_stages = len(stage_weights)

                    # 更新阶段详情
                    stage_details[stage] = {
                        "stage_name": stage_names.get(stage, stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                        "item_name": kwargs.get("item_name", ""),
                    }

                    # 构建详细进度信息
                    detail = stage_details[stage]
                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": stage_names.get(stage, stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message,
                    }

                    # 构建简洁消息
                    if detail["total"] > 0:
                        detailed_message = (
                            f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                            f"{detail['current']}/{detail['total']} - {message}"
                        )
                    else:
                        detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"

                    task_manager.update_task(
                        task_id,
                        progress=current_progress,
                        message=detailed_message,
                        progress_detail=progress_detail_data,
                    )

                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count,
                )

                # 任务完成
                task_manager.complete_task(task_id, result=result_state.to_simple_dict())

            except Exception as e:
                logger.error(f"准备模拟失败: {str(e)}")
                task_manager.fail_task(task_id, str(e))

                # 更新模拟状态为失败
                state = manager.get_simulation(simulation_id)
                if state:
                    state.status = SimulationStatus.FAILED
                    state.error = str(e)
                    manager._save_simulation_state(state)

        # 启动后台线程
        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()

        return {
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "status": "preparing",
                "message": t("api.prepareStarted"),
                "already_prepared": False,
                "expected_entities_count": state.entities_count,  # 预期的 Agent 总数
                "entity_types": state.entity_types,  # 实体类型列表
            },
        }

    except ValueError as e:
        return _error(str(e), 404)

    except Exception as e:
        logger.error(f"启动准备任务失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/prepare/status")
def get_prepare_status(req: PrepareStatusRequest):
    """
    查询准备任务进度

    支持两种查询方式：
    1. 通过 task_id 查询正在进行的任务进度
    2. 通过 simulation_id 检查是否已有完成的准备工作
    """
    from ..models.task import TaskManager

    try:
        task_id = req.task_id
        simulation_id = req.simulation_id

        # 如果提供了 simulation_id，先检查是否已准备完成
        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "progress": 100,
                        "message": t("api.alreadyPrepared"),
                        "already_prepared": True,
                        "prepare_info": prepare_info,
                    },
                }

        # 如果没有 task_id，返回错误
        if not task_id:
            if simulation_id:
                # 有 simulation_id 但未准备完成
                return {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "not_started",
                        "progress": 0,
                        "message": t("api.notStartedPrepare"),
                        "already_prepared": False,
                    },
                }
            return _error(t("api.requireTaskOrSimId"), 400)

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)

        if not task:
            # 任务不存在，但如果有 simulation_id，检查是否已准备完成
            if simulation_id:
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    return {
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": task_id,
                            "status": "ready",
                            "progress": 100,
                            "message": t("api.taskCompletedPrepared"),
                            "already_prepared": True,
                            "prepare_info": prepare_info,
                        },
                    }

            return _error(t("api.taskNotFound", id=task_id), 404)

        task_dict = task.to_dict()
        task_dict["already_prepared"] = False

        return {"success": True, "data": task_dict}

    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        return _error(str(e), 500)


@router.get("/list")
def list_simulations(project_id: str | None = None):
    """
    列出所有模拟

    Query 参数：
        project_id: 按项目ID过滤（可选）
    """
    try:
        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)

        return {
            "success": True,
            "data": [s.to_dict() for s in simulations],
            "count": len(simulations),
        }

    except Exception as e:
        logger.error(f"列出模拟失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/history")
def get_simulation_history(limit: int = 20):
    """
    获取历史模拟列表（带项目详情）

    用于首页历史项目展示，返回包含项目名称、描述等丰富信息的模拟列表

    Query 参数：
        limit: 返回数量限制（默认 20）
    """
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as _FutureTimeout

    def _build():
        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]

        # 增强模拟数据，只从 Simulation 文件读取
        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()

            # 获取模拟配置信息（从 simulation_config.json 读取 simulation_requirement）
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                # 推荐轮数（后备值）
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0)
                    * 60
                    / max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0

            # 获取运行状态（从 Postgres 读取用户设置的实际轮数）
            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                # 使用用户设置的 total_rounds，若无则使用推荐轮数
                sim_dict["total_rounds"] = (
                    run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
                )
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds

            # 获取关联项目的文件列表（最多3个）
            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, "files") and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", "未知文件")} for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []

            # 获取关联的 report_id（查找该 simulation 最新的 report）
            sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)

            # 添加版本号
            sim_dict["version"] = "v1.0.2"

            # 格式化日期
            try:
                created_date = sim_dict.get("created_at", "")[:10]
                sim_dict["created_date"] = created_date
            except Exception:
                sim_dict["created_date"] = ""

            enriched_simulations.append(sim_dict)

        # 合并「已建图谱但尚无模拟」的项目，使首页历史也能看到并续做这类项目
        sim_project_ids = {s.project_id for s in simulations if s.project_id}
        for project in ProjectManager.list_projects(limit=limit):
            if project.project_id in sim_project_ids:
                continue
            files = getattr(project, "files", None) or []
            created_at = getattr(project, "created_at", "") or ""
            enriched_simulations.append(
                {
                    "project_id": project.project_id,
                    "simulation_id": None,
                    "report_id": None,
                    "graph_id": project.graph_id,
                    "name": project.name,
                    "status": project.status,
                    "simulation_requirement": project.simulation_requirement or "",
                    "files": [{"filename": f.get("filename", "未知文件")} for f in files[:3]],
                    "created_at": created_at,
                    "created_date": created_at[:10],
                    "current_round": 0,
                    "total_rounds": 0,
                    "total_simulation_hours": 0,
                    "runner_status": "idle",
                    "version": "v1.0.2",
                }
            )

        # 按创建时间倒序，统一截断到 limit
        enriched_simulations.sort(key=lambda x: x.get("created_at", "") or "", reverse=True)
        return enriched_simulations[:limit]

    # 止血：整页查询设 30s 墙钟超时，避免单条 S3 回源卡死时首页 spinner 永久转圈。
    # 配合 object_store 的 read_timeout，卡住的工作线程也会在 ~30s 内自行释放，不会越积越多。
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_build)
    try:
        data = future.result(timeout=30)
        pool.shutdown(wait=False)
        return {"success": True, "data": data, "count": len(data)}
    except _FutureTimeout:
        pool.shutdown(wait=False, cancel_futures=True)
        logger.error("获取历史模拟超时（>30s）")
        return _error(t("api.historyTimeout"), 504)
    except Exception as e:
        pool.shutdown(wait=False)
        logger.error(f"获取历史模拟失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== Profile 生成接口（独立使用） ==============


@router.post("/generate-profiles")
def generate_profiles(req: GenerateProfilesRequest):
    """
    直接从图谱生成 OASIS Agent Profile（不创建模拟）

    请求（JSON）：
        {
            "graph_id": "superfish_xxxx",     // 必填
            "entity_types": ["Student"],      // 可选
            "use_llm": true,                  // 可选
            "platform": "reddit"              // 可选
        }
    """
    try:
        graph_id = req.graph_id
        if not graph_id:
            return _error(t("api.requireGraphId"), 400)

        entity_types = req.entity_types
        use_llm = req.use_llm
        platform = req.platform

        reader = Neo4jEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id, defined_entity_types=entity_types, enrich_with_edges=True
        )

        if filtered.filtered_count == 0:
            return _error(t("api.noMatchingEntities"), 400)

        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities, use_llm=use_llm
        )

        if platform == "reddit":
            profiles_data = [p.to_reddit_format() for p in profiles]
        elif platform == "twitter":
            profiles_data = [p.to_twitter_format() for p in profiles]
        else:
            profiles_data = [p.to_dict() for p in profiles]

        return {
            "success": True,
            "data": {
                "platform": platform,
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data,
            },
        }

    except Exception as e:
        logger.error(f"生成Profile失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 模拟运行控制接口 ==============


@router.post("/start")
def start_simulation(req: StartSimulationRequest):
    """
    开始运行模拟

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",          // 必填，模拟ID
            "platform": "parallel",                // 可选: twitter / reddit / parallel (默认)
            "max_rounds": 100,                     // 可选: 最大模拟轮数，用于截断过长的模拟
            "enable_graph_memory_update": false,   // 可选: 是否将 Agent 活动动态更新到 Neo4j 图谱记忆
            "force": false                         // 可选: 强制重新开始（会停止运行中的模拟并清理日志）
        }
    """
    try:
        simulation_id = req.simulation_id
        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        platform = req.platform
        max_rounds = req.max_rounds  # 可选：最大模拟轮数
        enable_graph_memory_update = req.enable_graph_memory_update  # 可选：是否启用图谱记忆更新
        force = req.force  # 可选：强制重新开始

        # 验证 max_rounds 参数
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return _error(t("api.maxRoundsPositive"), 400)
            except (ValueError, TypeError):
                return _error(t("api.maxRoundsInvalid"), 400)

        if platform not in ["twitter", "reddit", "parallel"]:
            return _error(t("api.invalidPlatform", platform=platform), 400)

        # 检查模拟是否已准备好
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        force_restarted = False

        # 智能处理状态：如果准备工作已完成，允许重新启动
        if state.status != SimulationStatus.READY:
            # 检查准备工作是否已完成
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # 准备工作已完成，检查是否有正在运行的进程
                if state.status == SimulationStatus.RUNNING:
                    # 检查模拟进程是否真的在运行
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # 进程确实在运行
                        if force:
                            # 强制模式：停止运行中的模拟
                            logger.info(f"强制模式：停止运行中的模拟 {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"停止模拟时出现警告: {str(e)}")
                        else:
                            return _error(t("api.simRunningForceHint"), 400)

                # 如果是强制模式，清理运行日志
                if force:
                    logger.info(f"强制模式：清理模拟日志 {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"清理日志时出现警告: {cleanup_result.get('errors')}")
                    force_restarted = True

                # 进程不存在或已结束，重置状态为 ready
                logger.info(
                    f"模拟 {simulation_id} 准备工作已完成，重置状态为 ready（原状态: {state.status.value}）"
                )
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # 准备工作未完成
                return _error(t("api.simNotReady", status=state.status.value), 400)

        # 获取图谱ID（用于图谱记忆更新）
        graph_id = None
        if enable_graph_memory_update:
            # 从模拟状态或项目中获取 graph_id
            graph_id = state.graph_id
            if not graph_id:
                # 尝试从项目中获取
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id

            if not graph_id:
                return _error(t("api.graphIdRequiredForMemory"), 400)

            logger.info(f"启用图谱记忆更新: simulation_id={simulation_id}, graph_id={graph_id}")

        # 启动模拟
        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id,
        )

        # 更新模拟状态
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)

        response_data = run_state.to_dict()
        if max_rounds:
            response_data["max_rounds_applied"] = max_rounds
        response_data["graph_memory_update_enabled"] = enable_graph_memory_update
        response_data["force_restarted"] = force_restarted
        if enable_graph_memory_update:
            response_data["graph_id"] = graph_id

        return {"success": True, "data": response_data}

    except ValueError as e:
        return _error(str(e), 400)

    except Exception as e:
        logger.error(f"启动模拟失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/stop")
def stop_simulation(req: StopSimulationRequest):
    """
    停止模拟

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx"  // 必填，模拟ID
        }
    """
    try:
        simulation_id = req.simulation_id
        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        run_state = SimulationRunner.stop_simulation(simulation_id)

        # 更新模拟状态
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)

        return {"success": True, "data": run_state.to_dict()}

    except ValueError as e:
        return _error(str(e), 400)

    except Exception as e:
        logger.error(f"停止模拟失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/admin/stop-all")
def stop_all_simulations():
    """运维入口：终止所有正在运行的模拟（含服务重启后接管的孤儿）。

    配合「进程退出时松手不杀子进程」的策略——真正想全停时调用此接口。
    """
    try:
        result = SimulationRunner.cleanup_all_simulations()
        # 同步把这些模拟的元数据状态置为 paused
        manager = SimulationManager()
        for sid in result.get("stopped", []):
            try:
                state = manager.get_simulation(sid)
                if state:
                    state.status = SimulationStatus.PAUSED
                    manager._save_simulation_state(state)
            except Exception as e:
                logger.warning(f"更新模拟元数据状态失败: {sid}, error={e}")
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"全部停止失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== Interview 采访接口 ==============


@router.post("/interview")
def interview_agent(req: InterviewAgentRequest):
    """
    采访单个 Agent

    注意：此功能需要模拟环境处于运行状态（完成模拟循环后进入等待命令模式）

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",       // 必填，模拟ID
            "agent_id": 0,                     // 必填，Agent ID
            "prompt": "你对这件事有什么看法？",  // 必填，采访问题
            "platform": "twitter",             // 可选，指定平台（twitter/reddit）
            "timeout": 60                      // 可选，超时时间（秒），默认 60
        }
    """
    try:
        simulation_id = req.simulation_id
        agent_id = req.agent_id
        prompt = req.prompt
        platform = req.platform  # 可选：twitter/reddit/None
        timeout = req.timeout

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        if agent_id is None:
            return _error(t("api.requireAgentId"), 400)

        if not prompt:
            return _error(t("api.requirePrompt"), 400)

        # 验证 platform 参数
        if platform and platform not in ("twitter", "reddit"):
            return _error(t("api.invalidInterviewPlatform"), 400)

        # 检查环境状态
        if not SimulationRunner.check_env_alive(simulation_id):
            return _error(t("api.envNotRunning"), 400)

        # 优化 prompt，添加前缀避免 Agent 调用工具
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout,
        )

        return {"success": result.get("success", False), "data": result}

    except ValueError as e:
        return _error(str(e), 400)

    except TimeoutError as e:
        return _error(t("api.interviewTimeout", error=str(e)), 504)

    except Exception as e:
        logger.error(f"Interview失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/interview/batch")
def interview_agents_batch(req: InterviewBatchRequest):
    """
    批量采访多个 Agent

    注意：此功能需要模拟环境处于运行状态
    """
    try:
        simulation_id = req.simulation_id
        interviews = req.interviews
        platform = req.platform  # 可选：twitter/reddit/None
        timeout = req.timeout

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        if not interviews or not isinstance(interviews, list):
            return _error(t("api.requireInterviews"), 400)

        # 验证 platform 参数
        if platform and platform not in ("twitter", "reddit"):
            return _error(t("api.invalidInterviewPlatform"), 400)

        # 验证每个采访项
        for i, interview in enumerate(interviews):
            if "agent_id" not in interview:
                return _error(t("api.interviewListMissingAgentId", index=i + 1), 400)
            if "prompt" not in interview:
                return _error(t("api.interviewListMissingPrompt", index=i + 1), 400)
            # 验证每项的 platform（如果有）
            item_platform = interview.get("platform")
            if item_platform and item_platform not in ("twitter", "reddit"):
                return _error(t("api.interviewListInvalidPlatform", index=i + 1), 400)

        # 检查环境状态
        if not SimulationRunner.check_env_alive(simulation_id):
            return _error(t("api.envNotRunning"), 400)

        # 优化每个采访项的 prompt，添加前缀避免 Agent 调用工具
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview["prompt"] = optimize_interview_prompt(interview.get("prompt", ""))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout,
        )

        return {"success": result.get("success", False), "data": result}

    except ValueError as e:
        return _error(str(e), 400)

    except TimeoutError as e:
        return _error(t("api.batchInterviewTimeout", error=str(e)), 504)

    except Exception as e:
        logger.error(f"批量Interview失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _interview_stream_response(simulation_id: str, poster) -> StreamingResponse:
    """采访流式 SSE 通用管道：订阅 Redis 频道 → 投递命令 → 逐块下发，直到 done/error/超时。

    poster: 回调 (ipc, command_id) -> None，负责投递对应的（单/批量）流式采访命令。
    子进程把 token 逐条发布到 interview:stream:{command_id}，本端点订阅并转成 text/event-stream。
    """
    import asyncio
    import uuid

    import redis.asyncio as aioredis

    from ..services.simulation_ipc import SimulationIPCClient

    async def event_gen():
        sim_dir = os.path.join(SimulationRunner.RUN_STATE_DIR, simulation_id)
        if not os.path.isdir(sim_dir):
            yield _sse_event({"type": "error", "error": "simulation-not-found"})
            return
        ipc = SimulationIPCClient(sim_dir)
        if not ipc.check_env_alive():
            # 环境已回收：前端应先调 ensure-env 唤醒后再发起；这里直接报错让其走兜底
            yield _sse_event({"type": "error", "error": "env-not-alive"})
            return

        command_id = str(uuid.uuid4())
        channel = f"interview:stream:{command_id}"
        r = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        try:
            # 先订阅再投递命令，避免漏掉首批 token
            poster(ipc, command_id)
            loop = asyncio.get_event_loop()
            overall_deadline = loop.time() + 200.0  # 整体上限
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=20.0)
                if msg is None:
                    # 无消息：首 token 前可能在唤醒/排队，发心跳保活并检查总超时
                    if loop.time() > overall_deadline:
                        yield _sse_event({"type": "error", "error": "timeout"})
                        break
                    yield ": keep-alive\n\n"
                    continue
                try:
                    payload = json.loads(msg["data"])
                except (ValueError, TypeError):
                    continue
                yield _sse_event(payload)
                if payload.get("type") in ("done", "error"):
                    break
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
                await r.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用反向代理缓冲，确保逐块下发
        },
    )


@router.post("/interview/stream")
def interview_stream(req: InterviewAgentRequest):
    """单 Agent 流式采访（SSE）。事件：`data:{"type":"chunk"|"done"|"error",...}`。"""
    if not req.simulation_id or req.agent_id is None or not req.prompt:
        return _error(t("api.requireSimulationId"), 400)
    agent_id = int(req.agent_id)
    prompt = req.prompt
    platform = req.platform
    return _interview_stream_response(
        req.simulation_id,
        lambda ipc, cid: ipc.post_stream_interview(agent_id, prompt, platform, command_id=cid),
    )


@router.post("/interview/stream-batch")
def interview_stream_batch(req: InterviewBatchRequest):
    """多 Agent 并发流式群访（SSE）。

    事件：chunk/agent_done/agent_error 均带 agent_id，全部完成发 done；前端按 agent_id 分别填充。
    """
    if not req.simulation_id or not req.interviews:
        return _error(t("api.requireSimulationId"), 400)
    interviews = req.interviews
    platform = req.platform
    return _interview_stream_response(
        req.simulation_id,
        lambda ipc, cid: ipc.post_stream_batch_interview(interviews, platform, command_id=cid),
    )


@router.post("/interview/all")
def interview_all_agents(req: InterviewAllRequest):
    """
    全局采访 - 使用相同问题采访所有 Agent

    注意：此功能需要模拟环境处于运行状态
    """
    try:
        simulation_id = req.simulation_id
        prompt = req.prompt
        platform = req.platform  # 可选：twitter/reddit/None
        timeout = req.timeout

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        if not prompt:
            return _error(t("api.requirePrompt"), 400)

        # 验证 platform 参数
        if platform and platform not in ("twitter", "reddit"):
            return _error(t("api.invalidInterviewPlatform"), 400)

        # 检查环境状态
        if not SimulationRunner.check_env_alive(simulation_id):
            return _error(t("api.envNotRunning"), 400)

        # 优化 prompt，添加前缀避免 Agent 调用工具
        optimized_prompt = optimize_interview_prompt(prompt)

        # platform 为可选；SimulationRunner 运行期接受 None（其签名标注偏紧，故定向忽略）
        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,  # type: ignore[arg-type]
            timeout=timeout,
        )

        return {"success": result.get("success", False), "data": result}

    except ValueError as e:
        return _error(str(e), 400)

    except TimeoutError as e:
        return _error(t("api.globalInterviewTimeout", error=str(e)), 504)

    except Exception as e:
        logger.error(f"全局Interview失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/interview/history")
def get_interview_history(req: InterviewHistoryRequest):
    """
    获取 Interview 历史记录

    从模拟数据库中读取所有 Interview 记录
    """
    try:
        simulation_id = req.simulation_id
        platform = req.platform  # 不指定则返回两个平台的历史
        agent_id = req.agent_id
        limit = req.limit

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        # platform/agent_id 为可选；运行期接受 None（service 签名偏紧，定向忽略）
        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,  # type: ignore[arg-type]
            agent_id=agent_id,
            limit=limit,
        )

        return {"success": True, "data": {"count": len(history), "history": history}}

    except Exception as e:
        logger.error(f"获取Interview历史失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/env-status")
def get_env_status(req: EnvStatusRequest):
    """
    获取模拟环境状态

    检查模拟环境是否存活（可以接收 Interview 命令）
    """
    try:
        simulation_id = req.simulation_id

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        env_alive = SimulationRunner.check_env_alive(simulation_id)

        # 获取更详细的状态信息
        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = t("api.envRunning")
        else:
            message = t("api.envNotRunningShort")

        return {
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "env_alive": env_alive,
                "twitter_available": env_status.get("twitter_available", False),
                "reddit_available": env_status.get("reddit_available", False),
                "message": message,
            },
        }

    except Exception as e:
        logger.error(f"获取环境状态失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/ensure-env")
def ensure_env(req: EnvStatusRequest):
    """
    确保模拟环境存活（采访前唤醒）。

    环境已活则返回 status=alive；否则按需唤醒（恢复模式重建环境 + 灌回 agent 记忆，
    不重跑模拟），返回 status=waking，由前端轮询 /env-status 至 env_alive 后再发起采访。
    """
    try:
        simulation_id = req.simulation_id
        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        result = SimulationRunner.wake_env(simulation_id)
        if result.get("success"):
            return {"success": True, "data": {"status": result.get("status", "waking")}}
        return _error(result.get("error") or t("api.envNotRunningShort"), 400)

    except Exception as e:
        logger.error(f"唤醒环境失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/close-env")
def close_simulation_env(req: CloseEnvRequest):
    """
    关闭模拟环境

    向模拟发送关闭环境命令，使其优雅退出等待命令模式。

    注意：这不同于 /stop 接口，/stop 会强制终止进程，
    而此接口会让模拟优雅地关闭环境并退出。
    """
    try:
        simulation_id = req.simulation_id
        timeout = req.timeout

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        result = SimulationRunner.close_simulation_env(simulation_id=simulation_id, timeout=timeout)

        # 更新模拟状态
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)

        return {"success": result.get("success", False), "data": result}

    except ValueError as e:
        return _error(str(e), 400)

    except Exception as e:
        logger.error(f"关闭环境失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 配置 / 脚本下载接口（带 send_file → FileResponse） ==============


@router.get("/script/{script_name}/download")
def download_simulation_script(script_name: str):
    """
    下载模拟运行脚本文件（通用脚本，位于 backend/scripts/）

    script_name 可选值：
        - run_twitter_simulation.py
        - run_reddit_simulation.py
        - run_parallel_simulation.py
        - action_logger.py
    """
    try:
        # 脚本位于 backend/scripts/ 目录
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts"))

        # 验证脚本名称
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py",
            "run_parallel_simulation.py",
            "action_logger.py",
        ]

        if script_name not in allowed_scripts:
            return _error(t("api.unknownScript", name=script_name, allowed=allowed_scripts), 400)

        script_path = os.path.join(scripts_dir, script_name)

        if not os.path.exists(script_path):
            return _error(t("api.scriptFileNotFound", name=script_name), 404)

        return FileResponse(script_path, filename=script_name, media_type="text/x-python")

    except Exception as e:
        logger.error(f"下载脚本失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 带 /{simulation_id}/... 子路径的接口（多段，不会与单段冲突） ==============


@router.get("/{simulation_id}/profiles")
def get_simulation_profiles(simulation_id: str, platform: str = "reddit"):
    """
    获取模拟的 Agent Profile

    Query 参数：
        platform: 平台类型（reddit/twitter，默认 reddit）
    """
    try:
        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)

        return {
            "success": True,
            "data": {"platform": platform, "count": len(profiles), "profiles": profiles},
        }

    except ValueError as e:
        return _error(str(e), 404)

    except Exception as e:
        logger.error(f"获取Profile失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/profiles/realtime")
def get_simulation_profiles_realtime(simulation_id: str, platform: str = "reddit"):
    """
    实时获取模拟的 Agent Profile（用于在生成过程中实时查看进度）

    与 /profiles 接口的区别：
    - 直接读取文件，不经过 SimulationManager
    - 适用于生成过程中的实时查看
    - 返回额外的元数据（如文件修改时间、是否正在生成等）

    Query 参数：
        platform: 平台类型（reddit/twitter，默认 reddit）
    """
    from datetime import datetime

    try:
        # 模拟存在性以 Postgres 为准（本地目录可能不在当前节点）
        sim_state = SimulationManager().get_simulation(simulation_id)
        if sim_state is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        sim_dir = os.path.join(settings.oasis_simulation_data_dir, simulation_id)

        # 确定文件路径
        if platform == "reddit":
            profiles_file = os.path.join(sim_dir, "reddit_profiles.json")
        else:
            profiles_file = os.path.join(sim_dir, "twitter_profiles.csv")

        # 检查文件是否存在
        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None

        if file_exists:
            # 获取文件修改时间
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()

            try:
                if platform == "reddit":
                    with open(profiles_file, encoding="utf-8") as f:
                        profiles = json.load(f)
                else:
                    with open(profiles_file, encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        profiles = list(reader)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"读取 profiles 文件失败（可能正在写入中）: {e}")
                profiles = []

        # 是否正在生成（以 Postgres 状态为准）
        is_generating = sim_state.status.value == "preparing"
        total_expected = sim_state.entities_count or None

        return {
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "platform": platform,
                "count": len(profiles),
                "total_expected": total_expected,
                "is_generating": is_generating,
                "file_exists": file_exists,
                "file_modified_at": file_modified_at,
                "profiles": profiles,
            },
        }

    except Exception as e:
        logger.error(f"实时获取Profile失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/config/realtime")
def get_simulation_config_realtime(simulation_id: str):
    """
    实时获取模拟配置（用于在生成过程中实时查看进度）

    与 /config 接口的区别：
    - 直接读取文件，不经过 SimulationManager
    - 适用于生成过程中的实时查看
    - 返回额外的元数据（如文件修改时间、是否正在生成等）
    - 即使配置还没生成完也能返回部分信息
    """

    try:
        # 模拟存在性以 Postgres 为准
        sim_state = SimulationManager().get_simulation(simulation_id)
        if sim_state is None:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        sim_dir = os.path.join(settings.oasis_simulation_data_dir, simulation_id)

        # 配置文件路径
        config_file = os.path.join(sim_dir, "simulation_config.json")

        # 检查文件是否存在
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None

        if file_exists:
            # 获取文件修改时间
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()

            try:
                with open(config_file, encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"读取 config 文件失败（可能正在写入中）: {e}")
                config = None

        # 生成状态以 Postgres 为准
        status = sim_state.status.value
        is_generating = status == "preparing"
        config_generated = sim_state.config_generated

        generation_stage = None
        if is_generating:
            generation_stage = "generating_config" if config_generated else "generating_profiles"
        elif status == "ready":
            generation_stage = "completed"

        # 构建返回数据
        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "config": config,
        }

        # 如果配置存在，提取一些关键统计信息
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model"),
            }

        return {"success": True, "data": response_data}

    except Exception as e:
        logger.error(f"实时获取Config失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/config/download")
def download_simulation_config(simulation_id: str):
    """下载模拟配置文件"""
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")

        # 本地缺失则从对象存储物化后再下载
        if not os.path.exists(config_path):
            from ..utils import object_store

            raw = object_store.get_bytes(f"simulations/{simulation_id}/simulation_config.json")
            if raw is None:
                return _error(t("api.configFileNotFound"), 404)
            with open(config_path, "wb") as f:
                f.write(raw)

        return FileResponse(
            config_path, filename="simulation_config.json", media_type="application/json"
        )

    except Exception as e:
        logger.error(f"下载配置失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/config")
def get_simulation_config(simulation_id: str):
    """
    获取模拟配置（LLM 智能生成的完整配置）

    返回包含：
        - time_config: 时间配置（模拟时长、轮次、高峰/低谷时段）
        - agent_configs: 每个 Agent 的活动配置（活跃度、发言频率、立场等）
        - event_config: 事件配置（初始帖子、热点话题）
        - platform_configs: 平台配置
        - generation_reasoning: LLM 的配置推理说明
    """
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)

        if not config:
            return _error(t("api.configNotFound"), 404)

        return {"success": True, "data": config}

    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/run-status/detail")
def get_run_status_detail(simulation_id: str, platform: str | None = None):
    """
    获取模拟运行详细状态（包含所有动作）

    用于前端展示实时动态

    Query 参数：
        platform: 过滤平台（twitter/reddit，可选）
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = platform

        if not run_state:
            return {
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "all_actions": [],
                    "twitter_actions": [],
                    "reddit_actions": [],
                },
            }

        # 获取完整的动作列表
        all_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id, platform=platform_filter
        )

        # 分平台获取动作
        twitter_actions = (
            SimulationRunner.get_all_actions(simulation_id=simulation_id, platform="twitter")
            if not platform_filter or platform_filter == "twitter"
            else []
        )

        reddit_actions = (
            SimulationRunner.get_all_actions(simulation_id=simulation_id, platform="reddit")
            if not platform_filter or platform_filter == "reddit"
            else []
        )

        # 获取当前轮次的动作（recent_actions 只展示最新一轮）
        current_round = run_state.current_round
        recent_actions = (
            SimulationRunner.get_all_actions(
                simulation_id=simulation_id, platform=platform_filter, round_num=current_round
            )
            if current_round > 0
            else []
        )

        # 获取基础状态信息
        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["twitter_actions"] = [a.to_dict() for a in twitter_actions]
        result["reddit_actions"] = [a.to_dict() for a in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        # recent_actions 只展示当前最新一轮两个平台的内容
        result["recent_actions"] = [a.to_dict() for a in recent_actions]

        return {"success": True, "data": result}

    except Exception as e:
        logger.error(f"获取详细状态失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/run-status")
def get_run_status(simulation_id: str):
    """
    获取模拟运行实时状态（用于前端轮询）
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)

        if not run_state:
            return {
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percent": 0,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                },
            }

        return {"success": True, "data": run_state.to_dict()}

    except Exception as e:
        logger.error(f"获取运行状态失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/actions")
def get_simulation_actions(
    simulation_id: str,
    limit: int = 100,
    offset: int = 0,
    platform: str | None = None,
    agent_id: int | None = None,
    round_num: int | None = None,
):
    """
    获取模拟中的 Agent 动作历史

    Query 参数：
        limit: 返回数量（默认 100）
        offset: 偏移量（默认 0）
        platform: 过滤平台（twitter/reddit）
        agent_id: 过滤 Agent ID
        round_num: 过滤轮次
    """
    try:
        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num,
        )

        return {
            "success": True,
            "data": {"count": len(actions), "actions": [a.to_dict() for a in actions]},
        }

    except Exception as e:
        logger.error(f"获取动作历史失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/timeline")
def get_simulation_timeline(simulation_id: str, start_round: int = 0, end_round: int | None = None):
    """
    获取模拟时间线（按轮次汇总）

    用于前端展示进度条和时间线视图

    Query 参数：
        start_round: 起始轮次（默认 0）
        end_round: 结束轮次（默认全部）
    """
    try:
        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id, start_round=start_round, end_round=end_round
        )

        return {"success": True, "data": {"rounds_count": len(timeline), "timeline": timeline}}

    except Exception as e:
        logger.error(f"获取时间线失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/agent-stats")
def get_agent_stats(simulation_id: str):
    """
    获取每个 Agent 的统计信息

    用于前端展示 Agent 活跃度排行、动作分布等
    """
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)

        return {"success": True, "data": {"agents_count": len(stats), "stats": stats}}

    except Exception as e:
        logger.error(f"获取Agent统计失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 数据库查询接口 ==============


@router.get("/{simulation_id}/posts")
def get_simulation_posts(
    simulation_id: str, platform: str = "reddit", limit: int = 50, offset: int = 0
):
    """
    获取模拟中的帖子

    Query 参数：
        platform: 平台类型（twitter/reddit）
        limit: 返回数量（默认 50）
        offset: 偏移量

    返回帖子列表（从 SQLite 数据库读取）
    """
    try:
        sim_dir = os.path.join(
            os.path.dirname(__file__), f"../../uploads/simulations/{simulation_id}"
        )

        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)

        if not os.path.exists(db_path):
            return {
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": t("api.dbNotExist"),
                },
            }

        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT * FROM post
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """,
                (limit, offset),
            )

            posts = [dict(row) for row in cursor.fetchall()]

            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]

        except sqlite3.OperationalError:
            posts = []
            total = 0

        conn.close()

        return {
            "success": True,
            "data": {"platform": platform, "total": total, "count": len(posts), "posts": posts},
        }

    except Exception as e:
        logger.error(f"获取帖子失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{simulation_id}/comments")
def get_simulation_comments(
    simulation_id: str, post_id: str | None = None, limit: int = 50, offset: int = 0
):
    """
    获取模拟中的评论（仅 Reddit）

    Query 参数：
        post_id: 过滤帖子ID（可选）
        limit: 返回数量
        offset: 偏移量
    """
    try:
        sim_dir = os.path.join(
            os.path.dirname(__file__), f"../../uploads/simulations/{simulation_id}"
        )

        db_path = os.path.join(sim_dir, "reddit_simulation.db")

        if not os.path.exists(db_path):
            return {"success": True, "data": {"count": 0, "comments": []}}

        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if post_id:
                cursor.execute(
                    """
                    SELECT * FROM comment
                    WHERE post_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """,
                    (post_id, limit, offset),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM comment
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """,
                    (limit, offset),
                )

            comments = [dict(row) for row in cursor.fetchall()]

        except sqlite3.OperationalError:
            comments = []

        conn.close()

        return {"success": True, "data": {"count": len(comments), "comments": comments}}

    except Exception as e:
        logger.error(f"获取评论失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 模拟状态（单段 /{simulation_id}，须放在最后） ==============


@router.get("/{simulation_id}")
def get_simulation(simulation_id: str):
    """获取模拟状态"""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        result = state.to_dict()

        # 如果模拟已准备好，附加运行说明
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)

        return {"success": True, "data": result}

    except Exception as e:
        logger.error(f"获取模拟状态失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())
