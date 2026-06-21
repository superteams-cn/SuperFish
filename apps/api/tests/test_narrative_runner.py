"""叙事 runner 非 LLM 面测试：种子 IO / narrative 判别 / 运行态聚合 / beat 解析。

完整推演（LLM）路径由引擎烟测覆盖，这里只守住文件契约与状态推导。
"""

import json

from app.domain.narrative import Beat, BeatType, Character, NarrativeSeed, Scene
from app.services.narrative.runner import (
    BEATS_FILENAME,
    RUN_FILENAME,
    NarrativeRunner,
    is_narrative,
    load_seed,
    save_seed,
)


def _seed() -> NarrativeSeed:
    return NarrativeSeed(
        simulation_id="sim_x",
        mode="free",
        requirement="推演",
        theme="主题",
        characters=[Character(char_id="u1", name="甲"), Character(char_id="u2", name="乙")],
        opening_scene=Scene(scene_id="s1", present=["u1", "u2"]),
    )


def test_seed_roundtrip_and_is_narrative(tmp_path):
    assert is_narrative(tmp_path) is False
    save_seed(tmp_path, _seed())
    assert is_narrative(tmp_path) is True
    back = load_seed(tmp_path)
    assert back is not None
    assert [c.name for c in back.characters] == ["甲", "乙"]
    assert back.opening_scene.present == ["u1", "u2"]


def test_run_status_idle(tmp_path):
    save_seed(tmp_path, _seed())
    st = NarrativeRunner.get_run_status("sim_x", tmp_path)
    assert st["kind"] == "narrative"
    assert st["runner_status"] == "idle"
    assert st["beats_count"] == 0


def test_run_status_counts_beats_and_progress(tmp_path):
    save_seed(tmp_path, _seed())
    beats = [
        Beat(seq=0, type=BeatType.SPEAK.value, actor="u1", to=["u2"], content="hi"),
        Beat(seq=1, type=BeatType.ASIDE.value, actor="u2", content="心声"),
    ]
    (tmp_path / BEATS_FILENAME).write_text(
        "\n".join(json.dumps(b.to_dict(), ensure_ascii=False) for b in beats) + "\n",
        encoding="utf-8",
    )
    (tmp_path / RUN_FILENAME).write_text(
        json.dumps({"status": "completed", "max_beats": 40}), encoding="utf-8"
    )
    st = NarrativeRunner.get_run_status("sim_x", tmp_path)
    assert st["beats_count"] == 2
    assert st["runner_status"] == "completed"
    assert st["progress_percent"] == 100.0


def test_run_status_running_but_dead_thread_is_interrupted(tmp_path):
    save_seed(tmp_path, _seed())
    (tmp_path / RUN_FILENAME).write_text(
        json.dumps({"status": "running", "max_beats": 40}), encoding="utf-8"
    )
    # 没有活线程 → 视为可续跑的中断态
    st = NarrativeRunner.get_run_status("sim_x", tmp_path)
    assert st["runner_status"] == "interrupted"


def test_get_beats_resolves_names(tmp_path):
    save_seed(tmp_path, _seed())
    beats = [Beat(seq=0, type=BeatType.SPEAK.value, actor="u1", to=["u2"], content="hi")]
    (tmp_path / BEATS_FILENAME).write_text(
        json.dumps(beats[0].to_dict(), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    out = NarrativeRunner.get_beats(tmp_path)
    assert out[0]["actor_name"] == "甲"
    assert out[0]["to_names"] == ["乙"]
