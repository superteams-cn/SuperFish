"""叙事引擎（P1 单场景 MVP）。

职责：在一个场景内，由导演（Director）选择下一个发声角色、角色（Character）依据
动机 / 目标 / 场景冲突 / 自建轻量记忆产出 beat，追加进事件流，直至导演判定收场。

只依赖 LLMClient 与领域纯函数（fold / recent_beats_for）。文件 IO 由 ``BeatLog`` 收口，
便于单测替换。运行时编排（子进程 / 监控 / 续跑）在 run_narrative_simulation.py。
详见 docs/narrative-engine-design.md。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from ...domain.narrative import (
    DIRECTOR_ACTOR,
    Beat,
    BeatType,
    Character,
    NarrativeMode,
    NarrativeSeed,
    WorldState,
    fold,
    recent_beats_for,
)
from ...utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class BeatLog:
    """事件流的只追加存储（``beats.jsonl``）。读：重放；写：追加。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read_all(self) -> list[Beat]:
        if not self.path.exists():
            return []
        beats: list[Beat] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    beats.append(Beat.from_dict(json.loads(line)))
        return beats

    def append(self, beat: Beat) -> Beat:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(beat.to_dict(), ensure_ascii=False) + "\n")
        return beat


def _mode_directive(mode: str) -> str:
    if mode == NarrativeMode.FAITHFUL.value:
        return (
            "推演模式=忠实复演：角色应贴合原剧本的性格与已知走向；"
            "当角色行为明显偏离其设定时，应校准回轨。目的是验证拆解是否站得住。"
        )
    return (
        "推演模式=自由推演：只锚定角色的初始动机与核心冲突，允许角色依据处境自由发挥，"
        "可以偏离原剧本，探索新的走向。目的是推演不同可能的结局。"
    )


def _fmt_beat(world: WorldState, beat: Beat) -> str:
    name = world.characters[beat.actor].name if beat.actor in world.characters else beat.actor
    if beat.type == BeatType.SPEAK.value:
        to_names = "、".join(
            world.characters[t].name if t in world.characters else t for t in beat.to
        )
        head = f"{name}（对{to_names}）" if to_names else name
        line = f"{head}：{beat.content}"
        if beat.subtext:
            line += f"  〔潜台词：{beat.subtext}〕"
        return line
    if beat.type == BeatType.ASIDE.value:
        return f"{name}〔内心〕：{beat.content}"
    if beat.type == BeatType.DIRECT.value:
        return f"〔导演〕{beat.content}"
    return f"{name}：{beat.content}"


def _roster(world: WorldState) -> str:
    lines = []
    for c in world.present_characters():
        lines.append(
            f"- {c.name}（{c.role}）动机：{c.motivation}；目标：{c.goal}；"
            f"当前状态：{c.mental_state or '（初始）'}"
        )
    return "\n".join(lines)


class NarrativeEngine:
    """单场景推演引擎。"""

    def __init__(
        self,
        seed: NarrativeSeed,
        beat_log: BeatLog,
        llm_client: LLMClient | None = None,
        on_beat: Callable[[Beat, WorldState], None] | None = None,
    ):
        self.seed = seed
        self.log = beat_log
        self.llm = llm_client or LLMClient()
        self.on_beat = on_beat

    # ---- LLM 决策 ----

    def _safe_chat_json(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> dict:
        """带一次重试的 JSON 调用：偶发空返回 / 解析失败不应中断整场推演。"""
        for attempt in range(2):
            try:
                out = self.llm.chat_json(messages, temperature=temperature, max_tokens=max_tokens)
                if isinstance(out, dict) and out:
                    return out
            except Exception as e:  # 解析失败 / 网络抖动
                logger.warning("narrative LLM call failed (attempt %d): %s", attempt + 1, e)
        return {}

    def _director_decide(self, world: WorldState) -> dict:
        """导演决定：下一个发声角色，或收场。"""
        scene = world.scene
        recent = "\n".join(_fmt_beat(world, b) for b in world.transcript[-10:]) or "（尚未开始）"
        present = "、".join(c.name for c in world.present_characters())
        system = (
            "你是一位戏剧导演，负责推进一个场景的节奏。"
            f"{_mode_directive(world.mode)}\n"
            "你要决定：让哪个在场角色接下来发声/行动，以制造或推进戏剧冲突；"
            "或在冲突已充分展开、场景目标达成或僵局时收场。"
            '只输出 JSON：{"action":"next"|"end","actor":"角色名","reason":"简述","beat_hint":"给该角色的一句情境提示"}。'
            "action=end 时 actor 可省略。"
        )
        user = (
            f"## 主题\n{self.seed.theme}\n\n"
            f"## 推演需求\n{self.seed.requirement}\n\n"
            f"## 当前场景\n{scene.location if scene else ''}（{scene.time if scene else ''}）"
            f" 目标/冲突：{scene.goal if scene else ''}\n在场：{present}\n\n"
            f"## 在场角色\n{_roster(world)}\n\n"
            f"## 最近发生\n{recent}\n\n"
            "请决定下一步。"
        )
        out = self._safe_chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.6,
            max_tokens=1500,
        )
        return out or {"action": "end"}

    def _character_act(self, world: WorldState, char: Character, hint: str) -> dict:
        """某角色产出一个 beat：台词 + 潜台词 + 可选内心独白。"""
        memory = recent_beats_for(world.transcript, char.char_id, limit=12)
        mem_txt = "\n".join(_fmt_beat(world, b) for b in memory) or "（这是你登场后的第一句）"
        others = "、".join(c.name for c in world.present_characters() if c.char_id != char.char_id)
        rel = "；".join(
            f"对{world.characters[cid].name if cid in world.characters else cid}：{desc}"
            for cid, desc in char.relationships.items()
        )
        system = (
            f"你现在扮演「{char.name}」（{char.role}）。\n"
            f"你的人设：{char.persona}\n"
            f"核心动机：{char.motivation}\n目标：{char.goal}\n"
            f"当前心理状态：{char.mental_state or '（初始）'}\n"
            f"你对其他人的态度：{rel or '（未明确）'}\n"
            f"{_mode_directive(world.mode)}\n"
            "请以这个角色的身份，针对当前处境说一句话并行动。"
            '只输出 JSON：{"to":["对话对象姓名"],"content":"你说的话","subtext":"这句话背后真实的潜台词","aside":"你此刻的内心独白（别人听不到，暴露你的真实动机；没有可留空）"}。'
            "台词要符合人物身份与情绪，推进冲突，不要复述旁白。"
        )
        user = (
            f"## 场景\n{world.scene.goal if world.scene else ''}\n"
            f"## 在场其他人\n{others}\n"
            f"## 你能回忆起的最近对话\n{mem_txt}\n\n"
            f"## 导演给你的情境提示\n{hint}\n\n"
            "现在轮到你。"
        )
        out = self._safe_chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.85,
            max_tokens=1500,
        )
        return out

    # ---- 主循环 ----

    def _name_to_id(self, world: WorldState, name: str) -> str | None:
        if not name:
            return None
        for c in world.characters.values():
            if c.name == name or c.char_id == name:
                return c.char_id
        # 容错：部分匹配
        for c in world.characters.values():
            if name in c.name or c.name in name:
                return c.char_id
        return None

    def _next_seq(self, world: WorldState) -> int:
        return world.last_seq + 1

    def _emit(self, beat: Beat) -> None:
        self.log.append(beat)
        if self.on_beat:
            try:
                self.on_beat(beat, fold(self.seed, self.log.read_all()))
            except Exception:  # 回调失败不应中断推演
                logger.exception("on_beat callback failed")

    def play(self, max_beats: int = 30) -> WorldState:
        """推进当前场景，直至导演收场或达到 beat 预算。返回最终 WorldState。"""
        for _ in range(max_beats):
            world = fold(self.seed, self.log.read_all())
            decision = self._director_decide(world)
            if decision.get("action") == "end":
                reason = decision.get("reason", "场景收束")
                self._emit(
                    Beat(
                        seq=self._next_seq(world),
                        type=BeatType.DIRECT.value,
                        actor=DIRECTOR_ACTOR,
                        scene_id=world.scene.scene_id if world.scene else "",
                        content=f"（场景结束：{reason}）",
                        meta={"kind": "end_scene"},
                    )
                )
                break

            actor_id = self._name_to_id(world, decision.get("actor", ""))
            if actor_id is None:
                # 导演没给有效角色：兜底选第一个在场角色，避免空转
                present = world.present_characters()
                if not present:
                    break
                actor_id = present[0].char_id
            char = world.characters[actor_id]
            hint = decision.get("beat_hint", "")

            act = self._character_act(world, char, hint)
            content = (act.get("content") or "").strip()
            if not content and not (act.get("aside") or "").strip():
                continue  # 角色没产出有效内容，跳过这一拍

            to_ids = [tid for tid in (self._name_to_id(world, n) for n in act.get("to", [])) if tid]
            if content:
                self._emit(
                    Beat(
                        seq=self._next_seq(fold(self.seed, self.log.read_all())),
                        type=BeatType.SPEAK.value,
                        actor=actor_id,
                        scene_id=world.scene.scene_id if world.scene else "",
                        to=to_ids,
                        content=content,
                        subtext=(act.get("subtext") or "").strip(),
                    )
                )
            aside = (act.get("aside") or "").strip()
            if aside:
                self._emit(
                    Beat(
                        seq=self._next_seq(fold(self.seed, self.log.read_all())),
                        type=BeatType.ASIDE.value,
                        actor=actor_id,
                        scene_id=world.scene.scene_id if world.scene else "",
                        content=aside,
                    )
                )

        return fold(self.seed, self.log.read_all())
