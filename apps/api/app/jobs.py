"""
后台作业的「业务逻辑」层（同步实现）。

这些函数自包含（仅靠 id/参数即可运行，内部从 Postgres/对象存储取数），
既可被 arq worker 调用，也可在队列不可用时由 inline 兜底线程直接执行。
所有持久状态写 Postgres，因此任意副本都能观测进度。
"""

import traceback

from .models.project import ProjectManager, ProjectStatus
from .models.task import TaskManager, TaskStatus
from .settings import settings
from .utils.locale import set_locale, t
from .utils.logger import get_logger

logger = get_logger("superfish.jobs")


def run_graph_build(
    *,
    project_id: str,
    task_id: str,
    graph_id: str,
    graph_name: str,
    chunk_size: int,
    chunk_overlap: int,
    locale: str = "zh",
) -> None:
    """构建图谱（原 graph.py 后台线程逻辑，迁移为可入队作业）。"""
    from .services.graph_builder import GraphBuilderService

    set_locale(locale)
    task_manager = TaskManager()
    try:
        logger.info(f"[{task_id}] 开始构建图谱...")
        project = ProjectManager.get_project(project_id)
        if not project:
            task_manager.update_task(
                task_id, status=TaskStatus.FAILED, error=f"project not found: {project_id}"
            )
            return

        text = ProjectManager.get_extracted_text(project_id)
        ontology = project.ontology
        if not text or not ontology:
            task_manager.update_task(
                task_id, status=TaskStatus.FAILED, error="missing text or ontology"
            )
            project.status = ProjectStatus.FAILED
            project.error = "missing text or ontology"
            ProjectManager.save_project(project)
            return

        builder = GraphBuilderService(api_key=settings.neo4j_uri)
        builder.build_graph(
            task_id=task_id,
            text=text,
            ontology=ontology,
            graph_name=graph_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            batch_size=3,
            locale=locale,
            graph_id=graph_id,
        )

        task = task_manager.get_task(task_id)
        if task and task.status == TaskStatus.COMPLETED:
            result = task.result or {}
            graph_info = result.get("graph_info", {})
            project.graph_id = result.get("graph_id") or graph_id
            project.status = ProjectStatus.GRAPH_COMPLETED
            project.error = None
            ProjectManager.save_project(project)
            logger.info(
                f"[{task_id}] 图谱构建完成: graph_id={project.graph_id}, "
                f"节点={graph_info.get('node_count', 0)}, 边={graph_info.get('edge_count', 0)}"
            )
        elif task and task.status == TaskStatus.FAILED:
            project.status = ProjectStatus.FAILED
            project.error = task.error
            ProjectManager.save_project(project)

    except Exception as e:
        logger.error(f"[{task_id}] 图谱构建失败: {e}")
        logger.debug(traceback.format_exc())
        project = ProjectManager.get_project(project_id)
        if project:
            project.status = ProjectStatus.FAILED
            project.error = str(e)
            ProjectManager.save_project(project)
        task_manager.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message=t("progress.buildFailed", error=str(e)),
            error=traceback.format_exc(),
        )


def run_report_generate(
    *,
    simulation_id: str,
    task_id: str,
    report_id: str,
    graph_id: str,
    simulation_requirement: str,
    locale: str = "zh",
) -> None:
    """生成模拟分析报告（原 report.py 后台线程逻辑，迁移为可入队作业）。

    报告章节已逐章写入 Postgres，因此重跑时 ReportAgent 可从已完成章节续跑。
    """
    from .services.report_agent import ReportAgent, ReportManager, ReportStatus

    set_locale(locale)
    task_manager = TaskManager()
    try:
        task_manager.update_task(
            task_id,
            status=TaskStatus.PROCESSING,
            progress=0,
            message=t("api.initReportAgent"),
        )

        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement,
        )

        def progress_callback(stage, progress, message):
            task_manager.update_task(task_id, progress=progress, message=f"[{stage}] {message}")

        report = agent.generate_report(progress_callback=progress_callback, report_id=report_id)
        # worker 无请求上下文：从所属模拟继承数据归属，确保报告带上 user_id
        try:
            from .services.simulation_manager import SimulationManager

            sim = SimulationManager().get_simulation(simulation_id)
            if sim and sim.user_id:
                report.user_id = sim.user_id
        except Exception:
            pass
        ReportManager.save_report(report)

        if report.status == ReportStatus.COMPLETED:
            task_manager.complete_task(
                task_id,
                result={
                    "report_id": report.report_id,
                    "simulation_id": simulation_id,
                    "status": "completed",
                },
            )
        else:
            task_manager.fail_task(task_id, report.error or t("api.reportGenerateFailed"))

    except Exception as e:
        logger.error(f"报告生成失败: {e}")
        task_manager.fail_task(task_id, str(e))
