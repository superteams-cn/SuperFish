"""报告仓储：reports 表的全部数据访问（session_scope + 行<->领域映射）。

只负责 Postgres 读写并收发 ``Report`` 领域对象。生成期本地日志（agent_log/console_log）
与内容后处理留在 ``ReportManager`` 服务层。
"""

from __future__ import annotations

from datetime import datetime

from ..core.db import session_scope
from ..db_models import ReportRow
from ..domain.report import Report, ReportOutline, ReportSection, ReportStatus


def _row_to_report(row: ReportRow) -> Report:
    outline = None
    if row.outline:
        sections = [
            ReportSection(title=s["title"], content=s.get("content", ""))
            for s in row.outline.get("sections", [])
        ]
        outline = ReportOutline(
            title=row.outline["title"], summary=row.outline["summary"], sections=sections
        )
    return Report(
        report_id=row.report_id,
        simulation_id=row.simulation_id,
        user_id=row.user_id or "",
        graph_id=row.graph_id,
        simulation_requirement=row.simulation_requirement,
        status=ReportStatus(row.status),
        outline=outline,
        markdown_content=row.markdown_content or "",
        created_at=row.created_at or "",
        completed_at=row.completed_at or "",
        error=row.error,
    )


def _load_row(session, report_id: str, create: bool = False) -> ReportRow | None:
    """加载报告行；create=True 时不存在则新建并 add。"""
    row = session.get(ReportRow, report_id)
    if row is None and create:
        row = ReportRow(report_id=report_id, created_at=datetime.now().isoformat())
        session.add(row)
    return row


class ReportRepository:
    """reports 表数据访问。"""

    @staticmethod
    def save_report(report: Report) -> None:
        """保存报告元信息与完整 markdown（章节/进度等其他字段保留）。"""
        with session_scope() as session:
            row = _load_row(session, report.report_id, create=True)
            row.simulation_id = report.simulation_id
            # 只在有值时写入，避免后续进度保存把已继承的归属清空
            if report.user_id:
                row.user_id = report.user_id
            row.graph_id = report.graph_id
            row.simulation_requirement = report.simulation_requirement
            row.status = (
                report.status.value if isinstance(report.status, ReportStatus) else report.status
            )
            if report.outline:
                row.outline = report.outline.to_dict()
            if report.markdown_content:
                row.markdown_content = report.markdown_content
            if report.created_at:
                row.created_at = report.created_at
            row.completed_at = report.completed_at
            row.error = report.error

    @staticmethod
    def save_outline(report_id: str, outline: ReportOutline) -> None:
        with session_scope() as session:
            row = _load_row(session, report_id, create=True)
            row.outline = outline.to_dict()

    @staticmethod
    def upsert_section(report_id: str, entry: dict) -> None:
        """按 section_index 幂等地写入/替换单个章节条目。"""
        section_index = entry.get("section_index")
        with session_scope() as session:
            row = _load_row(session, report_id, create=True)
            sections = [s for s in (row.sections or []) if s.get("section_index") != section_index]
            sections.append(entry)
            sections.sort(key=lambda s: s.get("section_index", 0))
            row.sections = sections

    @staticmethod
    def get_sections(report_id: str) -> list[dict]:
        """按章节序号排序返回已生成章节。"""
        with session_scope() as session:
            row = session.get(ReportRow, report_id)
            sections = list(row.sections or []) if row else []
        sections.sort(key=lambda s: s.get("section_index", 0))
        return sections

    @staticmethod
    def set_progress(report_id: str, progress_data: dict) -> None:
        with session_scope() as session:
            row = _load_row(session, report_id, create=True)
            row.progress = progress_data

    @staticmethod
    def get_progress(report_id: str) -> dict | None:
        with session_scope() as session:
            row = session.get(ReportRow, report_id)
            return row.progress if row else None

    @staticmethod
    def set_markdown(report_id: str, markdown_content: str) -> None:
        with session_scope() as session:
            row = _load_row(session, report_id, create=True)
            row.markdown_content = markdown_content

    @staticmethod
    def get_report(report_id: str) -> Report | None:
        with session_scope() as session:
            row = session.get(ReportRow, report_id)
            return _row_to_report(row) if row else None

    @staticmethod
    def get_report_by_simulation(simulation_id: str) -> Report | None:
        """取该模拟最新一条报告。"""
        with session_scope() as session:
            row = (
                session.query(ReportRow)
                .filter(ReportRow.simulation_id == simulation_id)
                .order_by(ReportRow.created_at.desc())
                .first()
            )
            return _row_to_report(row) if row else None

    @staticmethod
    def latest_report_ids_for_simulations(simulation_ids: list[str]) -> dict[str, str]:
        """批量取每个模拟的最新 report_id（单次查询），首页历史避免 N+1。"""
        if not simulation_ids:
            return {}
        with session_scope() as session:
            rows = (
                session.query(ReportRow.simulation_id, ReportRow.report_id, ReportRow.created_at)
                .filter(ReportRow.simulation_id.in_(simulation_ids))
                .order_by(ReportRow.created_at.desc())
                .all()
            )
        latest: dict[str, str] = {}
        # 已按 created_at 倒序，遇到的第一条即该模拟最新报告
        for sim_id, report_id, _created in rows:
            if sim_id not in latest:
                latest[sim_id] = report_id
        return latest

    @staticmethod
    def list_reports(
        simulation_id: str | None = None, limit: int = 50, user_id: str | None = None
    ) -> list[Report]:
        """按创建时间倒序；可按 user_id / simulation_id 过滤。"""
        with session_scope() as session:
            query = session.query(ReportRow)
            if user_id is not None:
                query = query.filter(ReportRow.user_id == user_id)
            if simulation_id is not None:
                query = query.filter(ReportRow.simulation_id == simulation_id)
            rows = query.order_by(ReportRow.created_at.desc()).limit(limit).all()
            return [_row_to_report(r) for r in rows]

    @staticmethod
    def delete_row(report_id: str) -> bool:
        """删除报告行；不存在返回 False。"""
        with session_scope() as session:
            row = session.get(ReportRow, report_id)
            if row is None:
                return False
            session.delete(row)
        return True
