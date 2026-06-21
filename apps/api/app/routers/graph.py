"""
图谱相关 API 路由（FastAPI 版）

采用项目上下文机制，服务端持久化状态。
响应沿用 {"success": ..., "data"/"error": ...} 信封，保持与前端契约一致。
"""

import os
import traceback

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..core.deps import get_current_user, require_verified_user, use_locale
from ..core.errors import error_response as _error  # 统一错误信封
from ..core.logger import get_logger
from ..core.settings import settings
from ..jobqueue import enqueue
from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager
from ..schemas.graph import BuildGraphRequest
from ..services.graph_builder import GraphBuilderService
from ..services.ontology_generator import OntologyGenerator
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.locale import get_locale, t

# 整个图谱路由：解析语言 + 强制登录（具体的 graph_id/project_id 归属在各处理器内校验）
router = APIRouter(dependencies=[Depends(use_locale), Depends(get_current_user)])

# 获取日志器
logger = get_logger("superfish.api")


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    if not filename or "." not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in settings.allowed_extensions


# ============== 项目管理接口 ==============


# 注意：/project/list 必须声明在 /project/{project_id} 之前，
# 否则 "list" 会被当作 project_id 捕获。
@router.get("/project/list")
def list_projects(limit: int = 50, current=Depends(get_current_user)):
    """列出当前用户的项目"""
    projects = ProjectManager.list_projects(limit=limit, user_id=current["user_id"])
    return {
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects),
    }


@router.get("/project/{project_id}")
def get_project(project_id: str, current=Depends(get_current_user)):
    """获取项目详情（仅限属主）"""
    project = ProjectManager.get_project(project_id)
    # 非属主一律按「不存在」处理，避免泄露资源是否存在
    if not project or project.user_id != current["user_id"]:
        return _error(t("api.projectNotFound", id=project_id), 404)
    return {"success": True, "data": project.to_dict()}


@router.delete("/project/{project_id}")
def delete_project(project_id: str, current=Depends(get_current_user)):
    """删除项目（仅限属主）"""
    project = ProjectManager.get_project(project_id)
    if not project or project.user_id != current["user_id"]:
        return _error(t("api.projectDeleteFailed", id=project_id), 404)
    success = ProjectManager.delete_project(project_id)
    if not success:
        return _error(t("api.projectDeleteFailed", id=project_id), 404)
    return {"success": True, "message": t("api.projectDeleted", id=project_id)}


@router.post("/project/{project_id}/reset")
def reset_project(project_id: str, current=Depends(get_current_user)):
    """重置项目状态（用于重新构建图谱，仅限属主）"""
    project = ProjectManager.get_project(project_id)
    if not project or project.user_id != current["user_id"]:
        return _error(t("api.projectNotFound", id=project_id), 404)

    # 重置到本体已生成状态
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED

    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)

    return {
        "success": True,
        "message": t("api.projectReset", id=project_id),
        "data": project.to_dict(),
    }


# ============== 接口1：上传文件并生成本体 ==============


@router.post("/ontology/generate")
async def generate_ontology(
    files: list[UploadFile] = File(default=[]),
    simulation_requirement: str = Form(default=""),
    project_name: str = Form(default="Unnamed Project"),
    additional_context: str = Form(default=""),
    current=Depends(require_verified_user),
):
    """接口1：上传文件（PDF/MD/TXT），分析生成本体定义。

    请求方式：multipart/form-data
    """
    try:
        logger.info("=== 开始生成本体定义 ===")
        logger.debug(f"项目名称: {project_name}")
        logger.debug(f"模拟需求: {simulation_requirement[:100]}...")

        if not simulation_requirement:
            return _error(t("api.requireSimulationRequirement"), 400)

        # 校验上传文件
        if not files or all(not f.filename for f in files):
            return _error(t("api.requireFileUpload"), 400)

        # 配额：单用户项目总数上限
        if ProjectManager.count_projects(current["user_id"]) >= settings.max_projects_per_user:
            return _error(t("auth.projectQuotaExceeded", limit=settings.max_projects_per_user), 403)

        # 创建项目（盖章当前用户为属主）
        project = ProjectManager.create_project(name=project_name, user_id=current["user_id"])
        project.simulation_requirement = simulation_requirement
        logger.info(f"创建项目: {project.project_id}")

        # 保存文件并提取文本
        document_texts = []
        all_text = ""

        for file in files:
            if file and file.filename and allowed_file(file.filename):
                # 读出字节后保存到项目目录（框架无关）
                file_bytes = await file.read()
                file_info = ProjectManager.save_file_to_project(
                    project.project_id,
                    file_bytes,
                    file.filename,
                )
                project.files.append(
                    {
                        "filename": file_info["original_filename"],
                        "size": file_info["size"],
                        "s3_key": file_info["s3_key"],
                    }
                )

                # 直接从内存字节提取文本（文件本体已存入对象存储）
                text = FileParser.extract_text_from_bytes(file_bytes, file.filename)
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return _error(t("api.noDocProcessed"), 400)

        # 保存提取的文本
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"文本提取完成，共 {len(all_text)} 字符")

        # 生成本体
        logger.info("调用 LLM 生成本体定义...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None,
        )

        # 保存本体到项目
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"本体生成完成: {entity_count} 个实体类型, {edge_count} 个关系类型")

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== 本体生成完成 === 项目ID: {project.project_id}")

        return {
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length,
            },
        }

    except Exception as e:
        logger.error(f"本体生成失败: {e}", exc_info=True)
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 接口2：构建图谱 ==============


@router.post("/build")
def build_graph(req: BuildGraphRequest, current=Depends(require_verified_user)):
    """接口2：根据 project_id 构建图谱（后台异步执行，仅限属主）。"""
    try:
        logger.info("=== 开始构建图谱 ===")

        project_id = req.project_id
        logger.debug(f"请求参数: project_id={project_id}")

        if not project_id:
            return _error(t("api.requireProjectId"), 400)

        # 获取项目（校验归属）
        project = ProjectManager.get_project(project_id)
        if not project or project.user_id != current["user_id"]:
            return _error(t("api.projectNotFound", id=project_id), 404)

        # 检查项目状态
        force = req.force

        if project.status == ProjectStatus.CREATED:
            return _error(t("api.ontologyNotGenerated"), 400)

        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return _error(t("api.graphBuilding"), 400, task_id=project.graph_build_task_id)

        # 如果强制重建，重置状态
        if force and project.status in [
            ProjectStatus.GRAPH_BUILDING,
            ProjectStatus.FAILED,
            ProjectStatus.GRAPH_COMPLETED,
        ]:
            # 清理上一次（可能因中断而残留）的图谱数据，避免图谱累积孤儿节点
            if project.graph_id:
                try:
                    from ..utils.graph_store import (
                        delete_group,
                        get_graph_store,
                    )

                    delete_group(get_graph_store(), project.graph_id)
                    logger.info(f"强制重建：已清理旧图谱数据 graph_id={project.graph_id}")
                except Exception as exc:
                    logger.warning(f"清理旧图谱数据失败（忽略）: {exc}")
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None

        # 获取配置：优先显式入参，否则用当前默认(env 可配)。
        # 不再回退到 project 中创建时冻结的旧值，使改默认后重建即生效。
        graph_name = req.graph_name or project.name or "SuperFish Graph"
        chunk_size = req.chunk_size or settings.default_chunk_size
        chunk_overlap = req.chunk_overlap or settings.default_chunk_overlap

        # 更新项目配置
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap

        # 获取提取的文本
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return _error(t("api.textNotFound"), 400)

        # 获取本体
        ontology = project.ontology
        if not ontology:
            return _error(t("api.ontologyNotFound"), 400)

        # 创建异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"构建图谱: {graph_name}")
        logger.info(f"创建图谱构建任务: task_id={task_id}, project_id={project_id}")

        # 提前生成 graph_id 并落库：构建期间节点/边会增量写入该图谱，
        # 前端凭此 ID 轮询 /api/graph/data 即可实时展示图谱逐步生长。
        graph_id = GraphBuilderService.create_graph(graph_name)

        # 更新项目状态
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        project.graph_id = graph_id
        ProjectManager.save_project(project)

        # 捕获当前语言后投递到队列，由 worker 进程执行（队列不可用则兜底本地线程）
        current_locale = get_locale()
        enqueue(
            "graph_build",
            project_id=project_id,
            task_id=task_id,
            graph_id=graph_id,
            graph_name=graph_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            locale=current_locale,
        )

        return {
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": t("api.graphBuildStarted", taskId=task_id),
            },
        }

    except Exception as e:
        return _error(str(e), 500, traceback=traceback.format_exc())


# ============== 任务查询接口 ==============


@router.get("/task/{task_id}")
def get_task(task_id: str):
    """查询任务状态"""
    task = TaskManager().get_task(task_id)
    if not task:
        return _error(t("api.taskNotFound", id=task_id), 404)
    return {"success": True, "data": task.to_dict()}


@router.get("/tasks")
def list_tasks():
    """列出所有任务"""
    tasks = TaskManager().list_tasks()
    return {
        "success": True,
        "data": [tk.to_dict() for tk in tasks],
        "count": len(tasks),
    }


# ============== 图谱数据接口 ==============


@router.get("/data/{graph_id}")
def get_graph_data(graph_id: str, current=Depends(get_current_user)):
    """获取图谱数据（节点和边，仅限属主）"""
    try:
        if not ProjectManager.user_owns_graph(graph_id, current["user_id"]):
            return _error(t("api.projectNotFound", id=graph_id), 404)

        builder = GraphBuilderService()
        graph_data = builder.get_graph_data(graph_id)
        return {"success": True, "data": graph_data}

    except Exception as e:
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.post("/project/{project_id}/recanonicalize")
def recanonicalize_project_graph(
    project_id: str, dry_run: bool = False, current=Depends(get_current_user)
):
    """对项目已构建的图谱重跑实体消解，合并重复/别名实体（无需重新抽取，仅限属主）。

    dry_run=true 时只返回拟合并分组，不改动数据库（用于先复核再执行）。
    """
    try:
        project = ProjectManager.get_project(project_id)
        if not project or project.user_id != current["user_id"]:
            return _error(t("api.projectNotFound", id=project_id), 404)
        if not project.graph_id:
            return _error(t("api.graphNotBuilt"), 400)

        builder = GraphBuilderService()
        result = builder.recanonicalize_graph(project.graph_id, dry_run=dry_run)
        logger.info(f"图谱实体消解完成: {result}")
        return {"success": True, "data": result}

    except Exception as e:
        return _error(str(e), 500, traceback=traceback.format_exc())


@router.delete("/delete/{graph_id}")
def delete_graph(graph_id: str, current=Depends(get_current_user)):
    """删除 图谱（仅限属主）"""
    try:
        if not ProjectManager.user_owns_graph(graph_id, current["user_id"]):
            return _error(t("api.graphDeleted", id=graph_id), 404)

        builder = GraphBuilderService()
        builder.delete_graph(graph_id)
        return {"success": True, "message": t("api.graphDeleted", id=graph_id)}

    except Exception as e:
        return _error(str(e), 500, traceback=traceback.format_exc())
