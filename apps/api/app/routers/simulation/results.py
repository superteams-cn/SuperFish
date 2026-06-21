"""模拟子路由：脚本下载、人设/配置读取、运行状态、行动/时间线/统计、帖子/评论及单模拟详情。

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
    Neo4jEntityReader,
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
            from ...utils import object_store

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
