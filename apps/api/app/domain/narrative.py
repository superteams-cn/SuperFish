"""叙事引擎领域模型（纯数据类 + 纯函数，无 IO / 无 LLM 依赖）。

剧本拆解 P1 的地基：事件溯源（event sourcing）。
- ``NarrativeSeed``：不变的初始世界（角色 / 初始场景 / 模式 / 需求）。
- ``Beat``：只追加、不可变的最小事件单元，带单调递增 ``seq``。
- ``WorldState = fold(seed, beats)``：把种子与事件流折叠出的当前世界，纯函数、可重放。

续跑（resume）= 读快照后重放其余 beats；分支（fork，P2）= 截取 beats[0..K] 另起一支。
两者由同一 ``fold`` 机制掉出来，故 P1 必须把这层做对。详见 docs/narrative-engine-design.md。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NarrativeMode(StrEnum):
    """推演模式：决定导演的介入强度。"""

    FAITHFUL = "faithful"  # 忠实复演：偏离剧本时校准回轨，用于验证拆解
    FREE = "free"  # 自由推演：仅锚初始设定与冲突，放手发挥（默认，以推演为主）


class BeatType(StrEnum):
    """事件类型（动作空间）。P1 先实现 SPEAK / ASIDE / DIRECT。"""

    SPEAK = "SPEAK"  # 角色对在场对象说话
    ASIDE = "ASIDE"  # 内心独白 / 动机暴露（其他角色不可感知，供拆解）
    ACT = "ACT"  # 物理 / 情节行动（P1 暂不实现）
    MOVE = "MOVE"  # 角色进出场景（P1 暂不实现）
    DIRECT = "DIRECT"  # 导演事件：切场 / 引入冲突 / 收场


# 导演用于推进的内部演员标识（区别于真实角色）
DIRECTOR_ACTOR = "__director__"


@dataclass
class Character:
    """一个可决策角色。属性多来自 P0 叙事本体抽取（motivation/mental_state 等）。"""

    char_id: str
    name: str
    role: str = ""  # 戏剧功能（主角 / 对手 / 导师……）
    motivation: str = ""  # 核心动机
    goal: str = ""  # 目标诉求
    mental_state: str = ""  # 当前心理状态（fold 过程中可被 DIRECT 漂移）
    persona: str = ""  # 完整人设描述
    # 对其他角色的关系认知：char_id -> 描述
    relationships: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "char_id": self.char_id,
            "name": self.name,
            "role": self.role,
            "motivation": self.motivation,
            "goal": self.goal,
            "mental_state": self.mental_state,
            "persona": self.persona,
            "relationships": self.relationships,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Character:
        return cls(
            char_id=data["char_id"],
            name=data.get("name", data["char_id"]),
            role=data.get("role", ""),
            motivation=data.get("motivation", ""),
            goal=data.get("goal", ""),
            mental_state=data.get("mental_state", ""),
            persona=data.get("persona", ""),
            relationships=dict(data.get("relationships", {})),
        )


@dataclass
class Scene:
    """一幕：在场角色、地点、时刻、戏剧目标 / 冲突。"""

    scene_id: str
    location: str = ""
    time: str = ""
    goal: str = ""  # 场景的戏剧目标或核心冲突
    present: list[str] = field(default_factory=list)  # 在场角色 char_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "location": self.location,
            "time": self.time,
            "goal": self.goal,
            "present": list(self.present),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        return cls(
            scene_id=data["scene_id"],
            location=data.get("location", ""),
            time=data.get("time", ""),
            goal=data.get("goal", ""),
            present=list(data.get("present", [])),
        )


@dataclass
class Beat:
    """只追加、不可变的事件单元。"""

    seq: int
    type: str  # BeatType
    actor: str  # 触发者 char_id；导演事件为 DIRECTOR_ACTOR
    scene_id: str = ""
    to: list[str] = field(default_factory=list)  # SPEAK 的对象
    content: str = ""  # 台词 / 行动描述 / 内心独白 / 导演事件文本
    subtext: str = ""  # 潜台词（SPEAK 可选）
    meta: dict[str, Any] = field(default_factory=dict)  # 扩展位（如 DIRECT 的 kind）

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "type": self.type,
            "actor": self.actor,
            "scene_id": self.scene_id,
            "to": list(self.to),
            "content": self.content,
            "subtext": self.subtext,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Beat:
        return cls(
            seq=int(data["seq"]),
            type=data["type"],
            actor=data["actor"],
            scene_id=data.get("scene_id", ""),
            to=list(data.get("to", [])),
            content=data.get("content", ""),
            subtext=data.get("subtext", ""),
            meta=dict(data.get("meta", {})),
        )


@dataclass
class NarrativeSeed:
    """不变的初始世界。来自 P0 抽取的角色 + 关系 + 初始场景设定。"""

    simulation_id: str
    mode: str  # NarrativeMode
    requirement: str  # 推演需求（含 what-if）
    theme: str = ""  # 主题 / 冲突主线（来自 analysis_summary）
    characters: list[Character] = field(default_factory=list)
    opening_scene: Scene | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "mode": self.mode,
            "requirement": self.requirement,
            "theme": self.theme,
            "characters": [c.to_dict() for c in self.characters],
            "opening_scene": self.opening_scene.to_dict() if self.opening_scene else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NarrativeSeed:
        scene = data.get("opening_scene")
        return cls(
            simulation_id=data["simulation_id"],
            mode=data.get("mode", NarrativeMode.FREE.value),
            requirement=data.get("requirement", ""),
            theme=data.get("theme", ""),
            characters=[Character.from_dict(c) for c in data.get("characters", [])],
            opening_scene=Scene.from_dict(scene) if scene else None,
        )


@dataclass
class WorldState:
    """种子与事件流折叠出的当前世界。纯由 ``fold`` 产生，丢失可重建。"""

    simulation_id: str
    mode: str
    characters: dict[str, Character]  # char_id -> Character（mental_state 可能已漂移）
    scene: Scene | None  # 当前场景
    transcript: list[Beat]  # 已发生的全部 beat（按 seq）
    last_seq: int  # 最后一个 beat 的 seq；空流为 -1

    def present_characters(self) -> list[Character]:
        if self.scene is None:
            return list(self.characters.values())
        return [self.characters[cid] for cid in self.scene.present if cid in self.characters]


def fold(seed: NarrativeSeed, beats: list[Beat]) -> WorldState:
    """把种子 + 有序事件流折叠成当前世界。纯函数：相同输入恒等输出，可重放。

    P1 折叠规则（最小但真实）：
    - 角色集来自 seed；``DIRECT`` 的 ``meta.mental_state_patch`` 可漂移角色心理状态。
    - 当前场景从 seed.opening_scene 起步，被 ``DIRECT`` 的 ``meta.scene`` 切换。
    - transcript 累积全部 beat。
    后续阶段再补 MOVE 改 present、ACT 改世界事实等。
    """
    characters: dict[str, Character] = {
        c.char_id: Character.from_dict(c.to_dict()) for c in seed.characters
    }
    scene: Scene | None = (
        Scene.from_dict(seed.opening_scene.to_dict()) if seed.opening_scene else None
    )
    transcript: list[Beat] = []
    last_seq = -1

    for beat in sorted(beats, key=lambda b: b.seq):
        transcript.append(beat)
        last_seq = beat.seq
        if beat.type == BeatType.DIRECT.value:
            new_scene = beat.meta.get("scene")
            if isinstance(new_scene, dict):
                scene = Scene.from_dict(new_scene)
            patch = beat.meta.get("mental_state_patch")
            if isinstance(patch, dict):
                for cid, state in patch.items():
                    if cid in characters and isinstance(state, str):
                        characters[cid].mental_state = state

    return WorldState(
        simulation_id=seed.simulation_id,
        mode=seed.mode,
        characters=characters,
        scene=scene,
        transcript=transcript,
        last_seq=last_seq,
    )


def recent_beats_for(transcript: list[Beat], char_id: str, limit: int = 12) -> list[Beat]:
    """自建轻量记忆：取与某角色相关的最近 N 个 beat。

    相关 = 该角色是触发者、或是 SPEAK 的对象、或该 beat 是公开的（非他人 ASIDE）。
    角色看不到别人的内心独白（ASIDE）。
    """
    relevant: list[Beat] = []
    for beat in transcript:
        is_own = beat.actor == char_id
        if beat.type == BeatType.ASIDE.value and not is_own:
            continue  # 别人的内心独白不可见
        if (
            is_own
            or char_id in beat.to
            or beat.type in (BeatType.SPEAK.value, BeatType.DIRECT.value)
        ):
            relevant.append(beat)
    return relevant[-limit:]
