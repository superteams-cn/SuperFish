"""报告服务包（拆分自 2481 行 report_agent.py）。

分层：domain/report（领域）← repositories/report_repo（数据访问）← manager（持久化门面）
← agent（ReACT 报告生成）。此处 re-export 历史符号，保持导入面稳定。
"""

from ...domain.report import Report, ReportOutline, ReportSection, ReportStatus
from .agent import ReportAgent
from .logs import ReportConsoleLogger, ReportLogger
from .manager import ReportManager

__all__ = [
    "Report",
    "ReportOutline",
    "ReportSection",
    "ReportStatus",
    "ReportAgent",
    "ReportManager",
    "ReportLogger",
    "ReportConsoleLogger",
]
