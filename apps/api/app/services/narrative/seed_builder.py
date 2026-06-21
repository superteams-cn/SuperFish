"""把 P0 抽取的图谱实体（角色）+ 关系 + 主题，组装成叙事引擎的 ``NarrativeSeed``。

输入来自现有抽取链：``GraphEntityReader.filter_defined_entities`` 产出的 ``EntityNode``
（属性里含 P0 叙事本体抽取的 role/motivation/goal/mental_state 等）+ 项目的
``analysis_summary``（主题/冲突主线）+ 推演需求。输出喂给 ``NarrativeEngine``。

纯组装逻辑，无 LLM、无图查询（实体已由调用方读好），便于单测。
"""

from __future__ import annotations

import logging
from typing import Any

from ...domain.narrative import Character, NarrativeMode, NarrativeSeed, Scene
from ..graph_entity_reader import EntityNode

logger = logging.getLogger(__name__)

# 出场角色上限：一个开场场景塞太多人会稀释冲突，按关系密度取前 N。
MAX_OPENING_CAST = 8

# 兜底类型名（与 ontology 叙事模板的兜底契约一致）：不作为戏剧功能 role 展示。
_FALLBACK_TYPES = {"个人", "Person", "组织", "Organization"}


def _attr(attrs: dict[str, Any], *keys: str) -> str:
    """按优先级取第一个非空属性值，转成字符串。"""
    for k in keys:
        v = attrs.get(k)
        if v:
            return str(v).strip()
    return ""


def _role_of(entity: EntityNode) -> str:
    """戏剧功能：优先属性里的 role，其次实体类型标签（排除兜底类型）。"""
    role = _attr(entity.attributes, "role", "dramatic_role")
    if role:
        return role
    etype = entity.get_entity_type()
    if etype and etype not in _FALLBACK_TYPES:
        return etype
    return ""


def _persona_of(entity: EntityNode) -> str:
    """人设描述：summary 为主，缀上 description/faction 等补充属性。"""
    parts = []
    if entity.summary:
        parts.append(entity.summary.strip())
    extra = _attr(entity.attributes, "description", "background")
    if extra and extra not in (entity.summary or ""):
        parts.append(extra)
    faction = _attr(entity.attributes, "faction")
    if faction:
        parts.append(f"所属：{faction}")
    return "；".join(parts)


def _relationships_of(entity: EntityNode, name_by_uuid: dict[str, str]) -> dict[str, str]:
    """从 related_edges 提取「对其他角色的关系认知」：char_id -> 描述。

    只保留指向 seed 内其他角色的边；用 edge_name + fact 作为可读描述。
    """
    rels: dict[str, str] = {}
    for edge in entity.related_edges:
        other = edge.get("target_node_uuid") or edge.get("source_node_uuid")
        if not other or other not in name_by_uuid:
            continue
        label = edge.get("edge_name", "") or ""
        fact = (edge.get("fact", "") or "").strip()
        desc = f"{label}：{fact}" if fact else label
        if not desc:
            continue
        # 同一对象多条边：拼接，避免覆盖
        rels[other] = f"{rels[other]}；{desc}" if other in rels else desc
    return rels


def _cast_priority(entity: EntityNode) -> int:
    """出场优先级：关系越多越可能是冲突核心。"""
    return len(entity.related_edges)


def build_seed(
    *,
    simulation_id: str,
    entities: list[EntityNode],
    requirement: str,
    theme: str = "",
    mode: str = NarrativeMode.FREE.value,
    location: str = "",
    time: str = "",
) -> NarrativeSeed:
    """组装 NarrativeSeed。

    Args:
        entities: 已读好的图谱实体（角色），属性含 P0 抽取的戏剧维度。
        requirement: 推演需求（含 what-if）。
        theme: 主题/冲突主线（一般传项目 analysis_summary）。
        mode: 推演模式，默认自由推演。
    """
    name_by_uuid = {e.uuid: e.name for e in entities}

    characters: list[Character] = []
    for e in entities:
        characters.append(
            Character(
                char_id=e.uuid,
                name=e.name,
                role=_role_of(e),
                motivation=_attr(e.attributes, "motivation", "desire", "want"),
                goal=_attr(e.attributes, "goal", "objective"),
                mental_state=_attr(e.attributes, "mental_state", "emotion", "state"),
                persona=_persona_of(e),
                relationships=_relationships_of(e, name_by_uuid),
            )
        )

    # 开场场景：取关系最密的前 N 个角色在场，目标即推演需求（退而求其次用主题）。
    ranked = sorted(entities, key=_cast_priority, reverse=True)
    present = [e.uuid for e in ranked[:MAX_OPENING_CAST]]
    scene_goal = requirement.strip() or theme.strip() or "角色在核心冲突中相遇"
    opening = Scene(
        scene_id="scene_1",
        location=location or "故事现场",
        time=time or "开场",
        goal=scene_goal,
        present=present,
    )

    seed = NarrativeSeed(
        simulation_id=simulation_id,
        mode=mode
        if mode in (NarrativeMode.FREE.value, NarrativeMode.FAITHFUL.value)
        else NarrativeMode.FREE.value,
        requirement=requirement,
        theme=theme,
        characters=characters,
        opening_scene=opening,
    )
    logger.info(
        "narrative seed built: sim=%s chars=%d cast=%d mode=%s",
        simulation_id,
        len(characters),
        len(present),
        seed.mode,
    )
    return seed
