"""
Report API 路由（FastAPI 版）

提供模拟报告生成、获取、对话等接口。
响应沿用 {"success": ..., "data"/"error": ...} 信封，保持与前端契约一致。

注意路由声明顺序：所有字面量路径（/list、/generate、/by-simulation 等）
必须声明在 /{report_id} 之前，否则会被动态段捕获。
"""

import traceback
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse

from ..deps import use_locale
from ..jobqueue import enqueue
from ..models.project import ProjectManager
from ..models.task import TaskManager
from ..schemas.report import (
    ChatRequest,
    GenerateReportRequest,
    GenerateStatusRequest,
    SearchToolRequest,
    StatisticsToolRequest,
)
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager
from ..utils.locale import get_locale, t
from ..utils.logger import get_logger

router = APIRouter(dependencies=[Depends(use_locale)])

logger = get_logger("superfish.api.report")


def _error(message: str, status: int, **extra) -> JSONResponse:
    """构造错误响应，保持统一信封。"""
    body = {"success": False, "error": message}
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


# ============== 报告生成接口 ==============


@router.post("/generate")
def generate_report(req: GenerateReportRequest):
    """生成模拟分析报告（异步任务）。立即返回 task_id，用 /generate/status 查询进度。"""
    try:
        simulation_id = req.simulation_id
        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)

        force_regenerate = req.force_regenerate

        # 获取模拟信息
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        # 检查是否已有报告
        if not force_regenerate:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "message": t("api.reportAlreadyExists"),
                        "already_generated": True,
                    },
                }

        # 获取项目信息
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return _error(t("api.projectNotFound", id=state.project_id), 404)

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return _error(t("api.missingGraphIdEnsure"), 400)

        simulation_requirement = project.simulation_requirement
        if not simulation_requirement:
            return _error(t("api.missingSimRequirement"), 400)

        # 提前生成 report_id，以便立即返回给前端
        report_id = f"report_{uuid.uuid4().hex[:12]}"

        # 创建异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="report_generate",
            metadata={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "report_id": report_id,
            },
        )

        # 捕获当前语言后投递到队列，由 worker 进程执行（队列不可用则兜底本地线程）
        current_locale = get_locale()
        enqueue(
            "report_generate",
            simulation_id=simulation_id,
            task_id=task_id,
            report_id=report_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            locale=current_locale,
        )

        return {
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "report_id": report_id,
                "task_id": task_id,
                "status": "generating",
                "message": t("api.reportGenerateStarted"),
                "already_generated": False,
            },
        }

    except Exception as e:
        logger.error(f"启动报告生成任务失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/generate/status")
def get_generate_status(req: GenerateStatusRequest):
    """查询报告生成任务进度。"""
    try:
        task_id = req.task_id
        simulation_id = req.simulation_id

        # 如果提供了 simulation_id，先检查是否已有完成的报告
        if simulation_id:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "progress": 100,
                        "message": t("api.reportGenerated"),
                        "already_completed": True,
                    },
                }

        if not task_id:
            return _error(t("api.requireTaskOrSimId"), 400)

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        if not task:
            return _error(t("api.taskNotFound", id=task_id), 404)

        return {"success": True, "data": task.to_dict()}

    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        return _error(str(e), 500)


# ============== 报告列表 / 按模拟查询（字面量路径，须在 /{report_id} 前）==============


@router.get("/list")
def list_reports(simulation_id: str | None = None, limit: int = 50):
    """列出所有报告，可按模拟ID过滤。"""
    try:
        reports = ReportManager.list_reports(simulation_id=simulation_id, limit=limit)
        return {
            "success": True,
            "data": [r.to_dict() for r in reports],
            "count": len(reports),
        }
    except Exception as e:
        logger.error(f"列出报告失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/by-simulation/{simulation_id}")
def get_report_by_simulation(simulation_id: str):
    """根据模拟ID获取报告。"""
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        if not report:
            return _error(t("api.noReportForSim", id=simulation_id), 404, has_report=False)
        return {"success": True, "data": report.to_dict(), "has_report": True}
    except Exception as e:
        logger.error(f"获取报告失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== Report Agent 对话接口 ==============


@router.post("/chat")
def chat_with_report_agent(req: ChatRequest):
    """与 Report Agent 对话，Agent 可自主调用检索工具回答问题。"""
    try:
        simulation_id = req.simulation_id
        message = req.message
        chat_history = req.chat_history

        if not simulation_id:
            return _error(t("api.requireSimulationId"), 400)
        if not message:
            return _error(t("api.requireMessage"), 400)

        # 获取模拟和项目信息
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return _error(t("api.simulationNotFound", id=simulation_id), 404)

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return _error(t("api.projectNotFound", id=state.project_id), 404)

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return _error(t("api.missingGraphId"), 400)

        simulation_requirement = project.simulation_requirement or ""

        # 创建 Agent 并进行对话
        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement,
        )
        result = agent.chat(message=message, chat_history=chat_history)

        return {"success": True, "data": result}

    except Exception as e:
        logger.error(f"对话失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 报告状态检查接口 ==============


@router.get("/check/{simulation_id}")
def check_report_status(simulation_id: str):
    """检查模拟是否有报告及其状态，用于前端判断是否解锁 Interview。"""
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)

        has_report = report is not None
        report_status = report.status.value if report else None
        report_id = report.report_id if report else None

        # 只有报告完成后才解锁 interview
        interview_unlocked = report is not None and report.status == ReportStatus.COMPLETED

        return {
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "has_report": has_report,
                "report_status": report_status,
                "report_id": report_id,
                "interview_unlocked": interview_unlocked,
            },
        }
    except Exception as e:
        logger.error(f"检查报告状态失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 工具调用接口（供调试使用）==============


@router.post("/tools/search")
def search_graph_tool(req: SearchToolRequest):
    """图谱搜索工具接口（调试用）。"""
    try:
        graph_id = req.graph_id
        query = req.query
        limit = req.limit

        if not graph_id or not query:
            return _error(t("api.requireGraphIdAndQuery"), 400)

        from ..services.neo4j_tools import Neo4jToolsService

        tools = Neo4jToolsService()
        result = tools.search_graph(graph_id=graph_id, query=query, limit=limit)
        return {"success": True, "data": result.to_dict()}

    except Exception as e:
        logger.error(f"图谱搜索失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/tools/statistics")
def get_graph_statistics_tool(req: StatisticsToolRequest):
    """图谱统计工具接口（调试用）。"""
    try:
        graph_id = req.graph_id
        if not graph_id:
            return _error(t("api.requireGraphId"), 400)

        from ..services.neo4j_tools import Neo4jToolsService

        tools = Neo4jToolsService()
        result = tools.get_graph_statistics(graph_id)
        return {"success": True, "data": result}

    except Exception as e:
        logger.error(f"获取图谱统计失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 报告下载 / 进度 / 章节 / 日志（带 report_id 前缀的子路径）==============


@router.get("/{report_id}/download")
def download_report(report_id: str):
    """下载报告（Markdown 格式）。"""
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return _error(t("api.reportNotFound", id=report_id), 404)

        # markdown 内容存于 Postgres，写入临时文件后下载
        markdown = report.markdown_content or ""
        if not markdown:
            assembled = ReportManager.get_generated_sections(report_id)
            markdown = "\n\n".join(s.get("content", "") for s in assembled)

        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(markdown)
            temp_path = f.name
        return FileResponse(temp_path, filename=f"{report_id}.md", media_type="text/markdown")

    except Exception as e:
        logger.error(f"下载报告失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{report_id}/progress")
def get_report_progress(report_id: str):
    """获取报告生成进度（实时）。"""
    try:
        progress = ReportManager.get_progress(report_id)
        if not progress:
            return _error(t("api.reportProgressNotAvail", id=report_id), 404)
        return {"success": True, "data": progress}
    except Exception as e:
        logger.error(f"获取报告进度失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{report_id}/sections")
def get_report_sections(report_id: str):
    """获取已生成的章节列表（分章节输出，前端可轮询）。"""
    try:
        sections = ReportManager.get_generated_sections(report_id)

        # 获取报告状态
        report = ReportManager.get_report(report_id)
        is_complete = report is not None and report.status == ReportStatus.COMPLETED

        return {
            "success": True,
            "data": {
                "report_id": report_id,
                "sections": sections,
                "total_sections": len(sections),
                "is_complete": is_complete,
            },
        }
    except Exception as e:
        logger.error(f"获取章节列表失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{report_id}/section/{section_index}")
def get_single_section(report_id: str, section_index: int):
    """获取单个章节内容。"""
    try:
        sections = ReportManager.get_generated_sections(report_id)
        match = next((s for s in sections if s.get("section_index") == section_index), None)

        if match is None:
            return _error(t("api.sectionNotFound", index=f"{section_index:02d}"), 404)

        return {
            "success": True,
            "data": {
                "filename": match.get("filename", f"section_{section_index:02d}.md"),
                "section_index": section_index,
                "content": match.get("content", ""),
            },
        }
    except Exception as e:
        logger.error(f"获取章节内容失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== Agent 日志接口 ==============


@router.get("/{report_id}/agent-log")
def get_agent_log(report_id: str, from_line: int = 0):
    """获取 Report Agent 的结构化执行日志（支持从指定行增量获取）。"""
    try:
        log_data = ReportManager.get_agent_log(report_id, from_line=from_line)
        return {"success": True, "data": log_data}
    except Exception as e:
        logger.error(f"获取Agent日志失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{report_id}/agent-log/stream")
def stream_agent_log(report_id: str):
    """一次性获取完整的 Agent 日志。"""
    try:
        logs = ReportManager.get_agent_log_stream(report_id)
        return {"success": True, "data": {"logs": logs, "count": len(logs)}}
    except Exception as e:
        logger.error(f"获取Agent日志失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 控制台日志接口 ==============


@router.get("/{report_id}/console-log")
def get_console_log(report_id: str, from_line: int = 0):
    """获取 Report Agent 的控制台输出日志（纯文本，支持增量获取）。"""
    try:
        log_data = ReportManager.get_console_log(report_id, from_line=from_line)
        return {"success": True, "data": log_data}
    except Exception as e:
        logger.error(f"获取控制台日志失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.get("/{report_id}/console-log/stream")
def stream_console_log(report_id: str):
    """一次性获取完整的控制台日志。"""
    try:
        logs = ReportManager.get_console_log_stream(report_id)
        return {"success": True, "data": {"logs": logs, "count": len(logs)}}
    except Exception as e:
        logger.error(f"获取控制台日志失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 报告详情 / 删除（单段 /{report_id}，须放在最后）==============


@router.get("/{report_id}")
def get_report(report_id: str):
    """获取报告详情。"""
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return _error(t("api.reportNotFound", id=report_id), 404)
        return {"success": True, "data": report.to_dict()}
    except Exception as e:
        logger.error(f"获取报告失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.delete("/{report_id}")
def delete_report(report_id: str):
    """删除报告。"""
    try:
        success = ReportManager.delete_report(report_id)
        if not success:
            return _error(t("api.reportNotFound", id=report_id), 404)
        return {"success": True, "message": t("api.reportDeleted", id=report_id)}
    except Exception as e:
        logger.error(f"删除报告失败: {str(e)}")
        return _error(str(e), 500, traceback=traceback.format_exc())
