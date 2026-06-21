"""模拟子路由：创建/准备/列表/历史/生成人设等生命周期前段接口。

拆分自 routers/simulation.py。共享件见 _shared.py。
"""

from ._shared import (  # noqa: F401  (统一从共享件导入，未用项由 ruff 裁剪)
    INTERVIEW_PROMPT_PREFIX,
    APIRouter,
    CloseEnvRequest,
    CreateSimulationRequest,
    Depends,
    EnvStatusRequest,
    FileResponse,
    GenerateProfilesRequest,
    HTTPException,
    InterviewAgentRequest,
    InterviewAllRequest,
    InterviewBatchRequest,
    InterviewHistoryRequest,
    GraphEntityReader,
    OasisProfileGenerator,
    PrepareSimulationRequest,
    PrepareStatusRequest,
    ProjectManager,
    Request,
    SimulationManager,
    SimulationRunner,
    SimulationStatus,
    StartSimulationRequest,
    StopSimulationRequest,
    StreamingResponse,
    _check_simulation_prepared,
    _error,
    _owned_simulation,
    csv,
    datetime,
    get_current_admin,
    get_current_user,
    get_locale,
    json,
    logger,
    optimize_interview_prompt,
    os,
    require_verified_user,
    set_locale,
    settings,
    t,
    threading,
    traceback,
)

router = APIRouter()


@router.post("/create")
def create_simulation(req: CreateSimulationRequest, current=Depends(require_verified_user)):
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
        if not project or project.user_id != current["user_id"]:
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
            user_id=project.user_id,
        )

        return {"success": True, "data": state.to_dict()}

    except Exception as e:
        logger.error(f"创建模拟失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/prepare")
def prepare_simulation(req: PrepareSimulationRequest, current=Depends(require_verified_user)):
    """
    准备模拟环境（异步任务，LLM 智能生成所有参数）

    这是一个耗时操作，接口会立即返回 task_id，
    使用 POST /api/simulation/prepare/status 查询进度

    特性：
    - 自动检测已完成的准备工作，避免重复生成
    - 如果已准备完成，直接返回已有结果
    - 支持强制重新生成（force_regenerate=true）
    """
    from ...models.task import TaskManager, TaskStatus

    try:
        simulation_id = req.simulation_id
        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state or state.user_id != current["user_id"]:
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
            reader = GraphEntityReader()
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
def get_prepare_status(req: PrepareStatusRequest, current=Depends(get_current_user)):
    """
    查询准备任务进度

    支持两种查询方式：
    1. 通过 task_id 查询正在进行的任务进度
    2. 通过 simulation_id 检查是否已有完成的准备工作
    """
    from ...models.task import TaskManager

    try:
        task_id = req.task_id
        simulation_id = req.simulation_id

        # 如果提供了 simulation_id，先检查是否已准备完成
        if simulation_id:
            if _owned_simulation(simulation_id, current) is None:
                return _error(t("api.simulationNotFound", id=simulation_id), 404)
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
def list_simulations(project_id: str | None = None, current=Depends(get_current_user)):
    """
    列出当前用户的模拟

    Query 参数：
        project_id: 按项目ID过滤（可选）
    """
    try:
        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id, user_id=current["user_id"])

        return {
            "success": True,
            "data": [s.to_dict() for s in simulations],
            "count": len(simulations),
        }

    except Exception as e:
        logger.error(f"列出模拟失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/history")
def get_simulation_history(limit: int = 20, current=Depends(get_current_user)):
    """
    获取当前用户的历史模拟列表（带项目详情）

    用于首页历史项目展示，返回包含项目名称、描述等丰富信息的模拟列表

    Query 参数：
        limit: 返回数量限制（默认 20）
    """
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as _FutureTimeout

    user_id = current["user_id"]

    def _build():
        from ...services.report import ReportManager

        manager = SimulationManager()
        # 按用户过滤：既隔离数据，也限定批量增强的范围在「当前用户的少量模拟」内
        simulations = manager.list_simulations(user_id=user_id)[:limit]

        # P2.1 根治 N+1：三次批量查询替代逐条增强，且摘要字段直接来自 simulations 冗余列，
        # 不再逐条回源 S3 的 simulation_config.json（原首页历史卡顿的主因）。
        sim_ids = [s.simulation_id for s in simulations]
        proj_ids = list({s.project_id for s in simulations if s.project_id})
        run_states = SimulationRunner.get_run_states_bulk(sim_ids)
        projects_map = ProjectManager.get_projects_bulk(proj_ids)
        report_ids = ReportManager.latest_report_ids_for_simulations(sim_ids)

        enriched_simulations = []
        for sim in simulations:
            sim_dict = (
                sim.to_dict()
            )  # 已含 simulation_requirement/total_simulation_hours/minutes_per_round

            # 推荐轮数（后备值）由冗余的时间配置算出
            recommended_rounds = int(
                sim.total_simulation_hours * 60 / max(sim.minutes_per_round, 1)
            )

            # 运行状态（批量结果中取，用户设置的实际轮数优先）
            run_state = run_states.get(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                sim_dict["total_rounds"] = (
                    run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
                )
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds

            # 关联项目的文件列表（最多3个，来自批量结果）
            project = projects_map.get(sim.project_id)
            if project and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", "未知文件")} for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []

            # 冗余列为空的存量模拟，用所属项目的需求兜底（项目已批量取出，零额外查询）
            if not sim_dict.get("simulation_requirement") and project:
                sim_dict["simulation_requirement"] = project.simulation_requirement or ""

            # 关联的最新 report_id（来自批量结果）
            sim_dict["report_id"] = report_ids.get(sim.simulation_id)

            # 添加版本号
            sim_dict["version"] = "v1.0.2"

            # 格式化日期
            try:
                sim_dict["created_date"] = (sim_dict.get("created_at", "") or "")[:10]
            except Exception:
                sim_dict["created_date"] = ""

            enriched_simulations.append(sim_dict)

        # 合并「已建图谱但尚无模拟」的项目，使首页历史也能看到并续做这类项目
        sim_project_ids = {s.project_id for s in simulations if s.project_id}
        for project in ProjectManager.list_projects(limit=limit, user_id=user_id):
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
def generate_profiles(req: GenerateProfilesRequest, current=Depends(get_current_user)):
    """
    直接从图谱生成 OASIS Agent Profile（不创建模拟，仅限属主）

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
        if not ProjectManager.user_owns_graph(graph_id, current["user_id"]):
            return _error(t("api.projectNotFound", id=graph_id), 404)

        entity_types = req.entity_types
        use_llm = req.use_llm
        platform = req.platform

        reader = GraphEntityReader()
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
