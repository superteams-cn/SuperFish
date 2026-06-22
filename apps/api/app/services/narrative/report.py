"""剧本推演报告生成器（P1/P3）。

与 OASIS 的 ReportAgent（ReACT + 社媒数据工具）解耦：叙事报告的数据源是 beats.jsonl +
narrative_seed.json，一次结构化 LLM 合成即可产出"拆解 + 推演结论"报告，复用 Report 存储
与 Step4 渲染（outline / sections / progress / markdown）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from ...domain.narrative import BeatType
from ...domain.report import Report, ReportOutline, ReportSection, ReportStatus
from ...utils.llm_client import LLMClient
from ...utils.locale import get_language_instruction
from ..report import ReportManager
from .engine import BeatLog, _fmt_beat
from .runner import BEATS_FILENAME, load_seed

logger = logging.getLogger(__name__)


_SYSTEM = """你是一位资深的剧本/叙事分析师。给你一段"剧情推演"的完整过程（角色在场景里的对白、潜台词、内心独白，以及导演的场景调度），请产出一份结构化的「剧本拆解 + 推演结论」报告。

报告要回答：人物动机是否成立、冲突如何展开与升级、关键转折、推演出的走向/结局相对原设定的差异、以及对创作或决策有用的拆解结论。

**只输出 JSON**，结构：
{
  "title": "报告标题",
  "summary": "一段话总览（80字内）",
  "sections": [
    {"title": "章节标题", "content": "章节正文（markdown，可用列表/小标题）"}
  ]
}
建议章节：推演概览、人物动机与弧光、冲突的展开与升级、关键转折点、结局推演与原设定对照、拆解结论与启示。正文要引用推演中的具体台词/内心独白作为证据。"""


_SCREENWRITING_SYSTEM = """你是一位资深的影视编剧指导（script doctor）。给你一段"剧情推演"的完整过程（角色对白、潜台词、内心独白、导演场景调度），请用专业编剧框架产出一份「剧本拆解 + 改稿建议」报告。

**只输出 JSON**，结构：
{
  "title": "报告标题",
  "summary": "一段话总览（80字内）",
  "sections": [
    {"title": "章节标题", "content": "章节正文（markdown，可用列表/小标题/表格）"}
  ]
}
请采用编剧专业维度，建议章节：
- 三幕结构：按建置/对抗/结局划分，标出各幕的功能与转折
- 节拍表（Beat Sheet）：参照 Save the Cat，列出可识别的关键节拍（如催化事件、中点、低谷、高潮）及其出现处
- 人物弧光：主要人物的起点状态→转变→终点状态，弧光是否完整
- 场次与冲突梳理：核心场景的戏剧目标与冲突强度
- 主题与潜文本
- 改稿建议：动机漏洞、节奏问题、弧光断裂处的具体修改方向
正文要引用推演中的具体台词/内心独白作为证据。"""


class NarrativeReportGenerator:
    """从 beats + seed 合成叙事拆解报告。style: narrative(通用) / screenwriting(编剧专业)。"""

    def __init__(self, sim_dir: str, llm_client: LLMClient | None = None, style: str = "narrative"):
        self.sim_dir = sim_dir
        self.llm = llm_client or LLMClient()
        self.style = style

    def _transcript(self) -> str:
        seed = load_seed(self.sim_dir)
        beats = BeatLog(f"{self.sim_dir}/{BEATS_FILENAME}").read_all()
        if not seed:
            return ""
        # 复用 fold 构造 world 以便 _fmt_beat 解析角色名
        from ...domain.narrative import fold

        world = fold(seed, beats)
        lines = [_fmt_beat(world, b) for b in beats if b.type != BeatType.DIRECT.value or b.content]
        return "\n".join(lines)

    def _roster(self) -> str:
        seed = load_seed(self.sim_dir)
        if not seed:
            return ""
        return "\n".join(
            f"- {c.name}（{c.role}）动机：{c.motivation}；目标：{c.goal}" for c in seed.characters
        )

    def generate(self, report_id: str, progress_callback: Callable | None = None) -> Report:
        seed = load_seed(self.sim_dir)
        sim_id = seed.simulation_id if seed else ""
        theme = seed.theme if seed else ""
        requirement = seed.requirement if seed else ""

        if progress_callback:
            progress_callback("planning", 10, "读取推演记录")
        ReportManager.update_progress(report_id, "generating", 20, "正在分析推演过程")

        transcript = self._transcript()
        if not transcript.strip():
            raise ValueError("没有可分析的推演记录（beats 为空）")

        user = (
            f"## 主题\n{theme}\n\n## 推演需求（含 what-if）\n{requirement}\n\n"
            f"## 角色\n{self._roster()}\n\n## 推演全过程\n{transcript}\n"
        )
        if progress_callback:
            progress_callback("generating", 40, "正在撰写拆解报告")

        system = _SCREENWRITING_SYSTEM if self.style == "screenwriting" else _SYSTEM
        out = self.llm.chat_json(
            [
                {"role": "system", "content": system + "\n\n" + get_language_instruction()},
                {"role": "user", "content": user},
            ],
            temperature=0.5,
            max_tokens=4096,
        )

        title = (out.get("title") or "剧本推演拆解报告").strip()
        summary = (out.get("summary") or "").strip()
        raw_sections = out.get("sections") or []
        sections = [
            ReportSection(
                title=str(s.get("title", f"章节{i + 1}")), content=str(s.get("content", ""))
            )
            for i, s in enumerate(raw_sections)
            if isinstance(s, dict)
        ]
        if not sections:
            sections = [ReportSection(title="推演分析", content=summary or transcript[:500])]

        outline = ReportOutline(title=title, summary=summary, sections=sections)
        ReportManager.save_outline(report_id, outline)

        completed: list[str] = []
        for i, section in enumerate(sections):
            ReportManager.save_section(report_id, i, section)
            completed.append(section.title)
            prog = 50 + int((i + 1) / len(sections) * 45)
            ReportManager.update_progress(
                report_id,
                "generating",
                prog,
                f"已完成：{section.title}",
                completed_sections=completed,
            )
            if progress_callback:
                progress_callback("generating", prog, section.title)

        markdown = ReportManager.assemble_full_report(report_id, outline)
        ReportManager.update_progress(
            report_id, "completed", 100, "报告生成完成", completed_sections=completed
        )

        report = ReportManager.get_report(report_id)
        if report is None:
            report = Report(
                report_id=report_id,
                simulation_id=sim_id,
                graph_id="",
                simulation_requirement=requirement,
                status=ReportStatus.COMPLETED,
            )
        report.outline = outline
        report.markdown_content = markdown
        report.status = ReportStatus.COMPLETED
        report.completed_at = datetime.now().isoformat()
        logger.info("narrative report generated: %s (%d sections)", report_id, len(sections))
        return report
