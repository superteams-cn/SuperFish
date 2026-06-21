"""叙事推演运行器（P1）。

与 OASIS 的子进程/双平台机器解耦：叙事引擎是仓内纯 Python，直接在后台守护线程里
跑 ``NarrativeEngine.play()``，把 beat 追加进 ``beats.jsonl``，运行态写 ``narrative_run.json``。

约定：**``narrative_seed.json`` 在 sim_dir 存在 == 这是一次叙事推演**。start / run-status
等路径据此分派，无需给 Simulation 加 DB 列。

P1 局限（已知）：在进程内线程，未接入 OASIS 那套 owner 锁 / detach / reconcile；
进程重启后可调用 start 续跑（beats.jsonl 为事实来源），但分布式接管留作后续硬化。
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from ...domain.narrative import Beat, NarrativeSeed, fold
from .engine import BeatLog, NarrativeEngine

logger = logging.getLogger(__name__)

SEED_FILENAME = "narrative_seed.json"
BEATS_FILENAME = "beats.jsonl"
RUN_FILENAME = "narrative_run.json"

DEFAULT_MAX_BEATS = 40


def seed_path(sim_dir: str | Path) -> Path:
    return Path(sim_dir) / SEED_FILENAME


def is_narrative(sim_dir: str | Path) -> bool:
    """sim_dir 是否为一次叙事推演（以种子文件存在为准）。"""
    return seed_path(sim_dir).exists()


def save_seed(sim_dir: str | Path, seed: NarrativeSeed) -> Path:
    p = seed_path(sim_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(seed.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_seed(sim_dir: str | Path) -> NarrativeSeed | None:
    p = seed_path(sim_dir)
    if not p.exists():
        return None
    return NarrativeSeed.from_dict(json.loads(p.read_text(encoding="utf-8")))


class NarrativeRunner:
    """单进程内的叙事推演调度。"""

    _threads: dict[str, threading.Thread] = {}
    _lock = threading.Lock()

    # ---- 运行态文件 ----

    @staticmethod
    def _run_state_path(sim_dir: str | Path) -> Path:
        return Path(sim_dir) / RUN_FILENAME

    @classmethod
    def _write_run_state(cls, sim_dir: str | Path, **fields: Any) -> None:
        p = cls._run_state_path(sim_dir)
        cur: dict[str, Any] = {}
        if p.exists():
            try:
                cur = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                cur = {}
        cur.update(fields)
        p.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def _beats(cls, sim_dir: str | Path) -> list[Beat]:
        return BeatLog(Path(sim_dir) / BEATS_FILENAME).read_all()

    # ---- 控制 ----

    @classmethod
    def is_running(cls, simulation_id: str) -> bool:
        with cls._lock:
            t = cls._threads.get(simulation_id)
            return bool(t and t.is_alive())

    @classmethod
    def start(
        cls,
        simulation_id: str,
        sim_dir: str | Path,
        max_beats: int = DEFAULT_MAX_BEATS,
        force: bool = False,
    ) -> dict[str, Any]:
        """启动（或续跑）一次叙事推演。返回 {started, status}。"""
        if cls.is_running(simulation_id) and not force:
            return {"started": False, "status": "running", "message": "已在推演中"}

        seed = load_seed(sim_dir)
        if seed is None:
            raise FileNotFoundError(f"未找到叙事种子: {seed_path(sim_dir)}")

        cls._write_run_state(sim_dir, status="running", error="", max_beats=max_beats)

        def _run() -> None:
            try:
                log = BeatLog(Path(sim_dir) / BEATS_FILENAME)

                def _on_beat(_beat: Beat, world) -> None:
                    cls._write_run_state(
                        sim_dir,
                        status="running",
                        beats_count=world.last_seq + 1,
                    )

                engine = NarrativeEngine(seed, log, on_beat=_on_beat)
                engine.play(max_beats=max_beats)
                final = fold(seed, log.read_all())
                cls._write_run_state(sim_dir, status="completed", beats_count=final.last_seq + 1)
                logger.info(
                    "narrative run completed: sim=%s beats=%d",
                    simulation_id,
                    final.last_seq + 1,
                )
            except Exception as e:  # noqa: BLE001 - 运行线程兜底
                logger.exception("narrative run failed: sim=%s", simulation_id)
                cls._write_run_state(sim_dir, status="failed", error=str(e))
            finally:
                with cls._lock:
                    cls._threads.pop(simulation_id, None)

        thread = threading.Thread(target=_run, name=f"narrative-{simulation_id}", daemon=True)
        with cls._lock:
            cls._threads[simulation_id] = thread
        thread.start()
        return {"started": True, "status": "running"}

    @classmethod
    def get_run_status(cls, simulation_id: str, sim_dir: str | Path) -> dict[str, Any]:
        """聚合运行态：状态 + 已产 beat 数 + 进度。供 run-status 接口。"""
        beats = cls._beats(sim_dir)
        beats_count = len(beats)
        run_state: dict[str, Any] = {}
        p = cls._run_state_path(sim_dir)
        if p.exists():
            try:
                run_state = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                run_state = {}

        status = run_state.get("status", "idle")
        # 线程已死但状态仍 running（如进程重启）→ 视为可续跑的中断态
        if status == "running" and not cls.is_running(simulation_id):
            status = "interrupted"
        max_beats = int(run_state.get("max_beats", DEFAULT_MAX_BEATS) or DEFAULT_MAX_BEATS)
        progress = (
            100.0 if status == "completed" else min(99.0, beats_count / max(1, max_beats) * 100)
        )

        return {
            "kind": "narrative",
            "runner_status": status,
            "beats_count": beats_count,
            "max_beats": max_beats,
            "progress_percent": round(progress, 1),
            "error": run_state.get("error", ""),
        }

    @classmethod
    def get_beats(cls, sim_dir: str | Path) -> list[dict[str, Any]]:
        """事件流（含角色名解析），供 run-status/detail 渲染。"""
        seed = load_seed(sim_dir)
        name_by_id = {c.char_id: c.name for c in seed.characters} if seed else {}
        out: list[dict[str, Any]] = []
        for b in cls._beats(sim_dir):
            d = b.to_dict()
            d["actor_name"] = name_by_id.get(b.actor, b.actor)
            d["to_names"] = [name_by_id.get(t, t) for t in b.to]
            out.append(d)
        return out
