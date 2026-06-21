"""ReportManager：报告持久化与生成产物的服务层门面。

分层：
- reports 表的数据访问下沉到 ``repositories.report_repo.ReportRepository``；
- 本类保留：生成期本地日志（agent_log.jsonl / console_log.txt）读取、
  Markdown 内容后处理（标题清理/组装）、删除时的本地目录清理等编排。
对外 classmethod 接口与签名保持不变，调用方无需改动。
"""

import json
import os
from datetime import datetime
from typing import Any

from ...core.logger import get_logger
from ...core.settings import settings
from ...domain.report import Report, ReportOutline, ReportSection
from ...repositories.report_repo import ReportRepository
from ...utils.locale import t

logger = get_logger("superfish.report_agent")


class ReportManager:
    """报告管理器：元数据/大纲/进度/章节/markdown 经 ReportRepository 持久化，
    生成期 append 日志（agent_log.jsonl / console_log.txt）落运行节点本地。
    """

    # 报告本地目录（仅承载生成期 append 日志）
    REPORTS_DIR = os.path.join(settings.upload_folder, "reports")

    # ============== 本地日志目录 ==============

    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        return os.path.join(cls.REPORTS_DIR, report_id)

    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder

    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")

    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")

    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> dict[str, Any]:
        """获取控制台日志内容（INFO/WARNING 等纯文本），支持增量读取。"""
        log_path = cls._get_console_log_path(report_id)
        if not os.path.exists(log_path):
            return {"logs": [], "total_lines": 0, "from_line": 0, "has_more": False}

        logs = []
        total_lines = 0
        with open(log_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    logs.append(line.rstrip("\n\r"))
        return {"logs": logs, "total_lines": total_lines, "from_line": from_line, "has_more": False}

    @classmethod
    def get_console_log_stream(cls, report_id: str) -> list[str]:
        """一次性获取完整控制台日志。"""
        return cls.get_console_log(report_id, from_line=0)["logs"]

    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> dict[str, Any]:
        """获取结构化 Agent 日志（jsonl），支持增量读取。"""
        log_path = cls._get_agent_log_path(report_id)
        if not os.path.exists(log_path):
            return {"logs": [], "total_lines": 0, "from_line": 0, "has_more": False}

        logs = []
        total_lines = 0
        with open(log_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        logs.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        return {"logs": logs, "total_lines": total_lines, "from_line": from_line, "has_more": False}

    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> list[dict[str, Any]]:
        """一次性获取完整 Agent 日志。"""
        return cls.get_agent_log(report_id, from_line=0)["logs"]

    # ============== 元数据 / 大纲 / 进度 / 章节（委托 ReportRepository）==============

    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """保存报告大纲（规划阶段完成后调用）。"""
        ReportRepository.save_outline(report_id, outline)
        logger.info(t("report.outlineSaved", reportId=report_id))

    @classmethod
    def save_section(cls, report_id: str, section_index: int, section: ReportSection) -> str:
        """保存单个章节（清理重复标题后落库）。返回章节文件名标识。"""
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        file_suffix = f"section_{section_index:02d}.md"
        ReportRepository.upsert_section(
            report_id,
            {"filename": file_suffix, "section_index": section_index, "content": md_content},
        )
        logger.info(t("report.sectionFileSaved", reportId=report_id, fileSuffix=file_suffix))
        return file_suffix

    @classmethod
    def update_progress(
        cls,
        report_id: str,
        status: str,
        progress: int,
        message: str,
        current_section: str = None,
        completed_sections: list[str] = None,
    ) -> None:
        """更新报告生成进度。"""
        cls._ensure_report_folder(report_id)
        ReportRepository.set_progress(
            report_id,
            {
                "status": status,
                "progress": progress,
                "message": message,
                "current_section": current_section,
                "completed_sections": completed_sections or [],
                "updated_at": datetime.now().isoformat(),
            },
        )

    @classmethod
    def get_progress(cls, report_id: str) -> dict[str, Any] | None:
        """获取报告生成进度。"""
        return ReportRepository.get_progress(report_id)

    @classmethod
    def get_generated_sections(cls, report_id: str) -> list[dict[str, Any]]:
        """获取已生成的章节列表（按章节序号排序）。"""
        return ReportRepository.get_sections(report_id)

    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """从已保存章节组装完整报告，做标题后处理并落库。"""
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += "---\n\n"
        for section_info in cls.get_generated_sections(report_id):
            md_content += section_info["content"]

        md_content = cls._post_process_report(md_content, outline)
        ReportRepository.set_markdown(report_id, md_content)
        logger.info(t("report.fullReportAssembled", reportId=report_id))
        return md_content

    @classmethod
    def save_report(cls, report: Report) -> None:
        """保存报告元信息与完整 markdown。"""
        ReportRepository.save_report(report)
        logger.info(t("report.reportSaved", reportId=report.report_id))

    @classmethod
    def get_report(cls, report_id: str) -> Report | None:
        return ReportRepository.get_report(report_id)

    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Report | None:
        return ReportRepository.get_report_by_simulation(simulation_id)

    @classmethod
    def latest_report_ids_for_simulations(cls, simulation_ids: list[str]) -> dict[str, str]:
        return ReportRepository.latest_report_ids_for_simulations(simulation_ids)

    @classmethod
    def list_reports(
        cls, simulation_id: str | None = None, limit: int = 50, user_id: str | None = None
    ) -> list[Report]:
        return ReportRepository.list_reports(
            simulation_id=simulation_id, limit=limit, user_id=user_id
        )

    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """删除报告记录并清理本地日志文件夹。"""
        if not ReportRepository.delete_row(report_id):
            return False
        try:
            import shutil

            folder_path = cls._get_report_folder(report_id)
            if os.path.isdir(folder_path):
                shutil.rmtree(folder_path)
        except Exception:
            pass
        logger.info(t("report.reportFolderDeleted", reportId=report_id))
        return True

    # ============== 内容后处理（纯函数，无 IO）==============

    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """清理章节内容：移除与章节标题重复的标题行，并把 ### 及以下标题转为粗体。"""
        import re

        if not content:
            return content

        content = content.strip()
        lines = content.split("\n")
        cleaned_lines = []
        skip_next_empty = False

        for i, line in enumerate(lines):
            stripped = line.strip()
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)

            if heading_match:
                len(heading_match.group(1))
                title_text = heading_match.group(2).strip()

                # 跳过前5行内与章节标题重复的标题
                if i < 5:
                    if title_text == section_title or title_text.replace(
                        " ", ""
                    ) == section_title.replace(" ", ""):
                        skip_next_empty = True
                        continue

                # 内容中不应有任何标题：统一转粗体
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")
                continue

            if skip_next_empty and stripped == "":
                skip_next_empty = False
                continue

            skip_next_empty = False
            cleaned_lines.append(line)

        # 移除开头的空行
        while cleaned_lines and cleaned_lines[0].strip() == "":
            cleaned_lines.pop(0)

        # 移除开头的分隔线及其后空行
        while cleaned_lines and cleaned_lines[0].strip() in ["---", "***", "___"]:
            cleaned_lines.pop(0)
            while cleaned_lines and cleaned_lines[0].strip() == "":
                cleaned_lines.pop(0)

        return "\n".join(cleaned_lines)

    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """后处理整篇报告：去重复标题；保留主标题(#)与章节标题(##)，其余转粗体；清理空行。"""
        import re

        lines = content.split("\n")
        processed_lines = []
        prev_was_heading = False

        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)

            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                # 连续5行内相同标题视为重复
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r"^(#{1,6})\s+(.+)$", prev_line)
                    if prev_match and prev_match.group(2).strip() == title:
                        is_duplicate = True
                        break

                if is_duplicate:
                    i += 1
                    while i < len(lines) and lines[i].strip() == "":
                        i += 1
                    continue

                if level == 1:
                    if title == outline.title:
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False

                i += 1
                continue

            elif stripped == "---" and prev_was_heading:
                i += 1
                continue

            elif stripped == "" and prev_was_heading:
                if processed_lines and processed_lines[-1].strip() != "":
                    processed_lines.append(line)
                prev_was_heading = False

            else:
                processed_lines.append(line)
                prev_was_heading = False

            i += 1

        # 连续空行最多保留 2 个
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == "":
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)

        return "\n".join(result_lines)
