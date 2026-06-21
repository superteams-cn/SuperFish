"""叙事引擎纯数据层测试：fold 重放 / 轻量记忆可见性 / BeatLog 往返。

不触 LLM、不触 DB，确定性。守住 event-sourcing 地基（resume/fork 都靠它）。
"""

from app.domain.narrative import (
    DIRECTOR_ACTOR,
    Beat,
    BeatType,
    Character,
    NarrativeMode,
    NarrativeSeed,
    Scene,
    fold,
    recent_beats_for,
)
from app.services.narrative.engine import BeatLog


def _seed() -> NarrativeSeed:
    return NarrativeSeed(
        simulation_id="t",
        mode=NarrativeMode.FREE.value,
        requirement="r",
        theme="主题",
        characters=[
            Character(char_id="a", name="甲", mental_state="平静"),
            Character(char_id="b", name="乙"),
        ],
        opening_scene=Scene(scene_id="sc1", goal="冲突", present=["a", "b"]),
    )


def test_fold_empty_stream():
    w = fold(_seed(), [])
    assert w.last_seq == -1
    assert w.scene.scene_id == "sc1"
    assert set(w.characters) == {"a", "b"}
    assert w.transcript == []


def test_fold_is_pure_and_replayable():
    seed = _seed()
    beats = [
        Beat(seq=0, type=BeatType.SPEAK.value, actor="a", to=["b"], content="hi"),
        Beat(seq=1, type=BeatType.SPEAK.value, actor="b", to=["a"], content="yo"),
    ]
    w1 = fold(seed, beats)
    w2 = fold(seed, beats)
    assert w1.last_seq == w2.last_seq == 1
    assert len(w1.transcript) == 2
    # 乱序输入按 seq 归位
    w3 = fold(seed, list(reversed(beats)))
    assert [b.seq for b in w3.transcript] == [0, 1]


def test_fold_direct_switches_scene_and_patches_mental_state():
    seed = _seed()
    direct = Beat(
        seq=0,
        type=BeatType.DIRECT.value,
        actor=DIRECTOR_ACTOR,
        content="切场",
        meta={
            "scene": {"scene_id": "sc2", "goal": "新冲突", "present": ["a"]},
            "mental_state_patch": {"a": "崩溃"},
        },
    )
    w = fold(seed, [direct])
    assert w.scene.scene_id == "sc2"
    assert w.characters["a"].mental_state == "崩溃"
    # 折叠不污染 seed 原对象
    assert seed.characters[0].mental_state == "平静"


def test_recent_beats_hides_others_aside():
    transcript = [
        Beat(seq=0, type=BeatType.SPEAK.value, actor="a", to=["b"], content="公开"),
        Beat(seq=1, type=BeatType.ASIDE.value, actor="a", content="甲的内心"),
        Beat(seq=2, type=BeatType.ASIDE.value, actor="b", content="乙的内心"),
    ]
    seen_by_b = recent_beats_for(transcript, "b")
    contents = [b.content for b in seen_by_b]
    assert "甲的内心" not in contents  # 看不到别人的内心独白
    assert "乙的内心" in contents  # 看得到自己的
    assert "公开" in contents


def test_beatlog_roundtrip(tmp_path):
    log = BeatLog(tmp_path / "beats.jsonl")
    assert log.read_all() == []
    log.append(Beat(seq=0, type=BeatType.SPEAK.value, actor="a", content="x"))
    log.append(Beat(seq=1, type=BeatType.ASIDE.value, actor="a", content="y"))
    back = log.read_all()
    assert [b.seq for b in back] == [0, 1]
    assert back[0].content == "x"
    assert back[1].type == BeatType.ASIDE.value
