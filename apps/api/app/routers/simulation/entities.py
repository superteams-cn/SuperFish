"""模拟子路由：图谱实体读取与过滤接口。

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

# ============== 实体读取接口 ==============


@router.get("/entities/{graph_id}")
def get_graph_entities(
    graph_id: str, entity_types: str = "", enrich: str = "true", current=Depends(get_current_user)
):
    """
    获取图谱中的所有实体（已过滤，仅限属主）

    只返回符合预定义实体类型的节点（Labels 不只是 Entity 的节点）

    Query 参数：
        entity_types: 逗号分隔的实体类型列表（可选，用于进一步过滤）
        enrich: 是否获取相关边信息（默认 true）
    """
    try:
        if not settings.neo4j_uri:
            return _error(t("api.neo4jConfigMissing"), 500)

        if not ProjectManager.user_owns_graph(graph_id, current["user_id"]):
            return _error(t("api.projectNotFound", id=graph_id), 404)

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
def get_entities_by_type(
    graph_id: str, entity_type: str, enrich: str = "true", current=Depends(get_current_user)
):
    """获取指定类型的所有实体（仅限属主）"""
    try:
        if not settings.neo4j_uri:
            return _error(t("api.neo4jConfigMissing"), 500)

        if not ProjectManager.user_owns_graph(graph_id, current["user_id"]):
            return _error(t("api.projectNotFound", id=graph_id), 404)

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
def get_entity_detail(graph_id: str, entity_uuid: str, current=Depends(get_current_user)):
    """获取单个实体的详细信息（仅限属主）"""
    try:
        if not settings.neo4j_uri:
            return _error(t("api.neo4jConfigMissing"), 500)

        if not ProjectManager.user_owns_graph(graph_id, current["user_id"]):
            return _error(t("api.projectNotFound", id=graph_id), 404)

        reader = Neo4jEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)

        if not entity:
            return _error(t("api.entityNotFound", id=entity_uuid), 404)

        return {"success": True, "data": entity.to_dict()}

    except Exception as e:
        logger.error(f"获取实体详情失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 模拟管理接口 ==============
