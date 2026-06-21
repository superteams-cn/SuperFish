"""ReportAgent._generate_section_react（ReACT 章节生成循环）的特征测试。

用脚本化假 LLM + 假 graph_tools 驱动循环（report_logger 留 None），覆盖核心路径：
够量工具后正常收尾 / 过早 Final Answer 被拒后补足 / 达最大迭代强制收尾。
为后续把循环抽到独立模块建立行为等价基线。
"""

from app.domain.report import ReportOutline, ReportSection
from app.services.report.agent import ReportAgent


class _Result:
    def __init__(self, text="tool-data"):
        self._text = text

    def to_text(self):
        return self._text


class _FakeGraphTools:
    """所有检索方法都返回固定文本，并提供 get_simulation_context 供构造期/规划用。"""

    def insight_forge(self, **kw):
        return _Result()

    def panorama_search(self, **kw):
        return _Result()

    def quick_search(self, **kw):
        return _Result()

    def interview_agents(self, **kw):
        return _Result()


class _ScriptedLLM:
    """按预设脚本逐次返回 chat() 响应；脚本用尽后固定返回一个 Final Answer 兜底。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def chat(self, messages, temperature=0.5, max_tokens=None):
        self.calls += 1
        if self._responses:
            return self._responses.pop(0)
        return "Final Answer: 脚本兜底正文"


def _make_agent(llm):
    return ReportAgent(
        graph_id="g1",
        simulation_id="s1",
        simulation_requirement="预测舆情",
        llm_client=llm,
        graph_tools=_FakeGraphTools(),
    )


_SECTION = ReportSection(title="第一章")
_OUTLINE = ReportOutline(title="报告", summary="摘要", sections=[_SECTION])


def _tool(name):
    return f'<tool_call>{{"name": "{name}", "parameters": {{}}}}</tool_call>'


def test_section_react_happy_path_three_tools_then_final():
    # min_tool_calls=3：先调用三种工具，再 Final Answer 才被接受
    llm = _ScriptedLLM(
        [
            _tool("quick_search"),
            _tool("panorama_search"),
            _tool("insight_forge"),
            "Final Answer: 这是最终章节正文。",
        ]
    )
    agent = _make_agent(llm)
    out = agent._generate_section_react(_SECTION, _OUTLINE, previous_sections=[])
    assert out == "这是最终章节正文。"
    assert llm.calls == 4


def test_section_react_rejects_premature_final_then_accepts():
    # 第一次就 Final Answer（工具 0 次）→ 被拒；补足 3 次工具后再 Final Answer → 接受
    llm = _ScriptedLLM(
        [
            "Final Answer: 过早收尾",
            _tool("quick_search"),
            _tool("panorama_search"),
            _tool("insight_forge"),
            "Final Answer: 正式正文",
        ]
    )
    agent = _make_agent(llm)
    out = agent._generate_section_react(_SECTION, _OUTLINE, previous_sections=[])
    assert out == "正式正文"
    # 过早收尾不算工具调用，被拒后继续，故至少 5 次 chat
    assert llm.calls == 5


def test_section_react_force_final_after_max_iterations():
    # LLM 一直调用工具、从不收尾 → 5 轮迭代后进入强制收尾，强制收尾返回 Final Answer
    llm = _ScriptedLLM([_tool("quick_search")] * 5 + ["Final Answer: 强制收尾正文"])
    agent = _make_agent(llm)
    out = agent._generate_section_react(_SECTION, _OUTLINE, previous_sections=[])
    assert out == "强制收尾正文"
    # 5 轮循环 + 1 次强制收尾
    assert llm.calls == 6


def test_section_react_no_prefix_content_accepted_after_enough_tools():
    # 工具够量后，LLM 输出无 "Final Answer:" 前缀的正文 → 直接当最终答案
    llm = _ScriptedLLM(
        [
            _tool("quick_search"),
            _tool("panorama_search"),
            _tool("insight_forge"),
            "这是没有前缀的正文内容。",
        ]
    )
    agent = _make_agent(llm)
    out = agent._generate_section_react(_SECTION, _OUTLINE, previous_sections=[])
    assert out == "这是没有前缀的正文内容。"
