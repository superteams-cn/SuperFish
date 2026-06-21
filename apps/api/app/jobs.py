"""
后台作业的「业务逻辑」层（同步实现）。

这些函数自包含（仅靠 id/参数即可运行，内部从 Postgres/对象存储取数），
既可被 arq worker 调用，也可在队列不可用时由 inline 兜底线程直接执行。
所有持久状态写 Postgres，因此任意副本都能观测进度。
"""

import traceback

from .core.logger import get_logger
from .core.settings import settings
from .models.project import ProjectManager, ProjectStatus
from .models.task import TaskManager, TaskStatus
from .utils.locale import set_locale, t

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


def run_simulation_launch(
    *,
    simulation_id: str,
    platform: str = "parallel",
    max_rounds: int | None = None,
    enable_graph_memory_update: bool = False,
    graph_id: str | None = None,
    locale: str = "zh",
) -> None:
    """在 worker 进程拉起 OASIS 模拟子进程（原 API 进程内 Popen，迁移为可入队作业）。

    前置：API 已调 SimulationRunner._init_run_state 持久化 STARTING 运行态。本作业
    调 _spawn_process 真正 Popen + 启动监控线程，worker 进程据此成为该模拟监控 owner。
    成功后把所属模拟状态置 RUNNING；失败置 FAILED（运行态由 _spawn_process 兜底回写）。
    """
    from .domain.simulation import SimulationStatus
    from .services.simulation_manager import SimulationManager
    from .services.simulation_runner import SimulationRunner

    set_locale(locale)
    try:
        SimulationRunner._spawn_process(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id,
        )
        try:
            manager = SimulationManager()
            sim = manager.get_simulation(simulation_id)
            if sim and sim.status != SimulationStatus.RUNNING:
                sim.status = SimulationStatus.RUNNING
                manager._save_simulation_state(sim)
        except Exception as exc:
            logger.warning(f"[{simulation_id}] 置模拟状态 RUNNING 失败（忽略）: {exc}")
        logger.info(f"[{simulation_id}] 模拟子进程已在 worker 拉起")
    except Exception as e:
        logger.error(f"[{simulation_id}] 拉起模拟子进程失败: {e}")
        logger.debug(traceback.format_exc())
        try:
            manager = SimulationManager()
            sim = manager.get_simulation(simulation_id)
            if sim:
                sim.status = SimulationStatus.FAILED
                sim.error = str(e)
                manager._save_simulation_state(sim)
        except Exception as exc:
            logger.warning(f"[{simulation_id}] 置模拟状态 FAILED 失败（忽略）: {exc}")


def run_reconcile(*, locale: str = "zh") -> None:
    """周期对账：接管本机仍在跑的孤儿、终结真正已死的运行。

    由 worker cron 周期调用。使「持有某模拟的 worker 崩溃/重启」后，该模拟能被及时
    终结（其 Redis 心跳随进程消失而过期）或在本机重启场景被重新接管 —— 实现任意
    worker 经 DB 状态对账接管，而非依赖单一进程存活。reset_detach=False 不打断优雅退出。
    """
    from .services.simulation_runner import SimulationRunner

    set_locale(locale)
    try:
        result = SimulationRunner.reconcile_running_simulations(locale=locale, reset_detach=False)
        if result.get("adopted") or result.get("finalized"):
            logger.info(f"周期对账: 接管={result['adopted']}, 终结={result['finalized']}")
    except Exception as e:
        logger.error(f"周期对账失败: {e}")
        logger.debug(traceback.format_exc())


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
    from .services.report import ReportAgent, ReportManager, ReportStatus

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
