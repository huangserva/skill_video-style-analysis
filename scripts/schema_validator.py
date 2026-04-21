#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON Schema 校验器

校验管线中间 JSON 文件的字段完整性，
在下游脚本消费前提前发现缺失字段，避免静默失败。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

TARGET_VISUAL_MODE_VALUES = {
    "live_action",
    "stylized_live_action",
    "anime",
}
CHARACTER_REFERENCE_MODE_VALUES = {
    "live_action",
    "stylized_live_action",
    "anime",
    "pseudo_realistic_human_illustration",
    "safe_stylized_human",
}
SCENE_GENERATION_MODE_VALUES = {
    "live_action",
    "stylized_live_action",
    "anime",
}
LIVE_SOURCE_MODES = {
    "live_action",
    "stylized_live_action",
}
VISUAL_MODE_VALUES = TARGET_VISUAL_MODE_VALUES | CHARACTER_REFERENCE_MODE_VALUES
GENERATION_CONTRACT_REQUIRED_FIELDS = [
    "source_visual_mode",
    "target_visual_mode",
    "mode_lock_reason",
    "fallback_policy",
    "character_reference_mode",
    "scene_generation_mode",
    "required_keywords",
    "forbidden_keywords",
    "consistency_rules",
]

MODE_KEYWORDS = {
    "live_action": {
        "required": ["live action", "realistic photo style", "真人", "实拍", "photographic"],
        "forbidden": ["anime", "插画", "illustration", "角色设定图", "赛璐璐", "cartoon"],
    },
    "stylized_live_action": {
        "required": ["stylized", "仿真人", "写实人物", "真人质感", "真实人类比例"],
        "forbidden": ["anime", "插画", "illustration", "角色设定图", "赛璐璐", "cartoon"],
    },
    "anime": {
        "required": ["anime", "插画", "illustration", "动画", "角色设定图", "动漫"],
        "forbidden": ["live action", "realistic photo style", "真人", "实拍", "photographic"],
    },
    "pseudo_realistic_human_illustration": {
        "required": [
            "realistic character illustration",
            "pseudo realistic human illustration",
            "pseudo_realistic_human_illustration",
            "写实人物插画",
            "写实人物插画参考图",
            "仿真人插画",
            "写实插画",
            "非照片",
            "真实人类比例",
        ],
        "forbidden": [
            "anime",
            "二次元",
            "漫画",
            "赛璐璐",
            "cartoon",
            "真人照片",
            "实拍",
        ],
    },
    "safe_stylized_human": {
        "required": [
            "realistic character illustration",
            "safe stylized human",
            "pseudo realistic human illustration",
            "pseudo_realistic_human_illustration",
            "写实人物插画",
            "写实人物插画参考图",
            "半写实",
            "参考插画人",
            "仿真人插画",
            "写实插画",
            "非照片",
            "真实人类比例",
            "illustrated human",
        ],
        "forbidden": [
            "anime",
            "二次元",
            "漫画",
            "赛璐璐",
            "cartoon",
            "真人照片",
            "实拍",
        ],
    },
}


# ============================================================
# Schema 定义
# ============================================================

SCENE_PROMPTS_SCHEMA = {
    "description": "步骤6输出 - 场景提示词 + 角色定义",
    "required_keys": ["scenes", "style_consistency", "generation_contract"],
    "optional_keys": ["characters", "character_ref_prompts", "visual_style_prompt", "video_generation"],
    "generation_contract_required": GENERATION_CONTRACT_REQUIRED_FIELDS,
    "style_consistency_required": [
        "style_family",
        "character_render_mode",
        "scene_render_mode",
        "lighting_rule",
        "palette_rule",
        "background_rule",
        "framing_rule",
        "costume_rule",
        "character_prompt_block",
        "scene_prompt_block",
        "must_keep",
        "negative_constraints",
    ],
    "scenes_item_required": ["scene_id", "prompt", "duration"],
    "scenes_item_optional": ["main_character", "visible_characters", "extra_refs", "semantic_anchor"],
    "scene_semantic_anchor_required": [
        "content_type",
        "subtype_judgment",
        "behavior_summary",
        "evidence_to_preserve",
        "negative_constraints",
    ],
    "characters_item_required": ["id", "gender", "appearance"],
    "characters_item_optional": ["age", "clothing", "name"],
    "character_ref_prompts_item_required": ["character_id", "prompt"],
    "character_ref_prompts_item_optional": ["reference_type", "priority", "notes"],
}

NARRATIVE_ANALYSIS_SCHEMA = {
    "description": "步骤3.5输出 - 叙事线分析",
    "required_keys": ["narrative_theme", "characters_from_text"],
    "optional_keys": ["narrator", "narrative_arc", "analysis_level", "confidence_warning"],
    "characters_from_text_item_required": ["name", "role"],
    "characters_from_text_item_optional": ["identity"],
}

TTS_GUIDE_SCHEMA = {
    "description": "步骤7输出 - TTS复刻指导",
    "required_keys": ["tts_parameters", "reference_text"],
    "optional_keys": ["duration_target", "_skipped", "skip_reason"],
    "tts_parameters_required": ["tone", "speed", "emotion"],
    "tts_parameters_optional": ["gender", "rhythm", "voice"],
}

COHERENCE_ANALYSIS_SCHEMA = {
    "description": "步骤4输出 - 深度视觉分析",
    "required_keys": ["characters"],
    "optional_keys": ["scene_analysis", "analysis_level"],
    "characters_item_required": ["character_id", "visual_description"],
    "characters_item_optional": [
        "name_from_text", "age_range", "appearance",
        "clothing_changes", "scenes_appearance", "confidence",
    ],
}

AUDIO_VISUAL_CORRELATION_SCHEMA = {
    "description": "步骤5输出 - 音画关联分析",
    "required_keys": ["timeline_mapping"],
    "optional_keys": [
        "semantic_match_score", "emotion_consistency",
        "overall_correlation", "analysis_level",
    ],
}

SEMANTIC_ANALYSIS_SCHEMA = {
    "description": "步骤3.6输出 - 6棱镜语义分析骨架",
    "required_keys": ["media_baseline", "global_summary", "generation_contract", "style_consistency", "scene_prisms"],
    "optional_keys": ["analysis_level", "inference_notes"],
    "media_baseline_required": [
        "source_resolution", "source_aspect_ratio", "orientation",
        "duration", "scene_count", "keyframe_count",
        "audio_mode", "understanding_mode",
    ],
    "global_summary_required": [
        "content_mode", "visual_style", "open_world_status", "summary_note",
    ],
    "generation_contract_required": GENERATION_CONTRACT_REQUIRED_FIELDS,
    "style_consistency_required": [
        "style_family",
        "character_render_mode",
        "scene_render_mode",
        "lighting_rule",
        "palette_rule",
        "background_rule",
        "framing_rule",
        "costume_rule",
        "character_prompt_block",
        "scene_prompt_block",
        "must_keep",
        "negative_constraints",
    ],
    "scene_prisms_item_required": [
        "scene_id", "time_range",
        "narrative_prism", "subject_prism", "action_prism",
        "scene_prism", "camera_prism", "constraint_prism",
    ],
}


# ============================================================
# 校验函数
# ============================================================

def _check_required_keys(data: dict, required: List[str], path: str = "root") -> List[str]:
    """检查必需字段"""
    errors = []
    for key in required:
        if key not in data:
            errors.append(f"[{path}] 缺少必需字段: '{key}'")
    return errors


def _check_array_items(
    data: dict,
    array_key: str,
    required_fields: List[str],
    path: str = "root",
    max_check: int = 3,
) -> List[str]:
    """检查数组项的字段"""
    errors = []
    items = data.get(array_key, [])

    if not isinstance(items, list):
        errors.append(f"[{path}] '{array_key}' 应为数组，实际为 {type(items).__name__}")
        return errors

    if not items:
        errors.append(f"[{path}] '{array_key}' 数组为空")
        return errors

    for i, item in enumerate(items[:max_check]):
        if not isinstance(item, dict):
            errors.append(f"[{path}.{array_key}[{i}]] 应为对象，实际为 {type(item).__name__}")
            continue
        for field in required_fields:
            if field not in item:
                errors.append(f"[{path}.{array_key}[{i}]] 缺少必需字段: '{field}'")

    return errors


def validate(data: dict, schema: dict, file_desc: str = "") -> Tuple[bool, List[str], List[str]]:
    """
    通用校验函数

    Returns:
        (is_valid, errors, warnings)
    """
    errors = []
    warnings = []
    desc = file_desc or schema.get("description", "")

    # 检查顶级必需字段
    errors.extend(_check_required_keys(data, schema.get("required_keys", []), desc))

    # 检查数组项字段
    for key in schema:
        if key.endswith("_item_required"):
            array_key = key.replace("_item_required", "")
            if array_key in data:
                errors.extend(_check_array_items(
                    data, array_key,
                    schema[key], desc,
                ))

    # 检查嵌套对象字段
    for key in schema:
        if key.endswith("_required") and not key.endswith("_item_required"):
            obj_key = key.replace("_required", "")
            if obj_key in data:
                obj = data[obj_key]
                if isinstance(obj, dict):
                    errors.extend(_check_required_keys(obj, schema[key], f"{desc}.{obj_key}"))

    # 检查可选但推荐的字段
    for key in schema.get("optional_keys", []):
        if key not in data:
            warnings.append(f"[{desc}] 可选字段 '{key}' 未提供")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def _validate_style_consistency(data: dict, desc: str) -> List[str]:
    """校验统一风格约束块"""
    errors = []
    style = data.get("style_consistency")
    if not isinstance(style, dict):
        errors.append(f"[{desc}.style_consistency] 应为对象，实际为 {type(style).__name__}")
        return errors

    for field in ["must_keep", "negative_constraints"]:
        value = style.get(field)
        if not isinstance(value, list):
            errors.append(
                f"[{desc}.style_consistency.{field}] 应为数组，实际为 {type(value).__name__}"
            )

    return errors


def _is_todo_value(value) -> bool:
    """判断字段是否还是占位符"""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped.startswith("[TODO") or stripped.startswith("TODO")
    if isinstance(value, list):
        return any(_is_todo_value(item) for item in value)
    return False


def _validate_generation_contract(data: dict, desc: str) -> List[str]:
    """校验统一生成契约块"""
    errors = []
    contract = data.get("generation_contract")
    if not isinstance(contract, dict):
        errors.append(f"[{desc}.generation_contract] 应为对象，实际为 {type(contract).__name__}")
        return errors

    for field in GENERATION_CONTRACT_REQUIRED_FIELDS:
        if field not in contract:
            errors.append(f"[{desc}.generation_contract] 缺少必需字段: '{field}'")

    for field in ["required_keywords", "forbidden_keywords", "consistency_rules"]:
        value = contract.get(field)
        if field in contract and not isinstance(value, list):
            errors.append(
                f"[{desc}.generation_contract.{field}] 应为数组，实际为 {type(value).__name__}"
            )

    return errors


def _check_mode_text_alignment(
    text: str,
    mode: str,
    path: str,
    warnings: List[str],
) -> List[str]:
    """检查文本内容是否和目标视觉形态冲突"""
    errors = []
    if not isinstance(text, str) or not text.strip():
        return errors

    mode_key = (mode or "").strip().lower()
    if mode_key not in MODE_KEYWORDS:
        return errors

    lowered = text.lower()
    rules = MODE_KEYWORDS[mode_key]

    for keyword in rules["forbidden"]:
        if keyword.lower() in lowered:
            errors.append(f"[{path}] 出现了与 {mode_key} 冲突的关键词: '{keyword}'")

    if not any(keyword.lower() in lowered for keyword in rules["required"]):
        warnings.append(f"[{path}] 没有明显体现 {mode_key} 的固定关键词")

    return errors


def validate_generation_contract_runtime(data: dict, desc: str) -> Tuple[bool, List[str]]:
    """给步骤8/9用的运行时强校验：生成契约必须已锁定且不得自相矛盾"""
    errors = _validate_generation_contract(data, desc)
    contract = data.get("generation_contract", {})
    if errors:
        return False, errors

    field_allowed_values = {
        "source_visual_mode": TARGET_VISUAL_MODE_VALUES,
        "target_visual_mode": TARGET_VISUAL_MODE_VALUES,
        "character_reference_mode": CHARACTER_REFERENCE_MODE_VALUES,
        "scene_generation_mode": SCENE_GENERATION_MODE_VALUES,
    }

    for field in ["source_visual_mode", "target_visual_mode", "character_reference_mode", "scene_generation_mode"]:
        value = contract.get(field, "")
        if _is_todo_value(value):
            errors.append(f"[{desc}.generation_contract.{field}] 仍是占位符，生成前必须先锁定")
        elif value not in field_allowed_values[field]:
            errors.append(
                f"[{desc}.generation_contract.{field}] 必须是 {sorted(field_allowed_values[field])} 之一，"
                f"当前为 '{value}'"
            )

    target_mode = contract.get("target_visual_mode", "")
    source_mode = contract.get("source_visual_mode", "")
    char_mode = contract.get("character_reference_mode", "")
    if target_mode in TARGET_VISUAL_MODE_VALUES:
        scene_mode = contract.get("scene_generation_mode")
        if scene_mode != target_mode:
            errors.append(
                f"[{desc}.generation_contract.scene_generation_mode] 必须与 target_visual_mode 保持一致，"
                f"当前 target_visual_mode='{target_mode}'，但 scene_generation_mode='{scene_mode}'"
            )

    if char_mode in {"pseudo_realistic_human_illustration", "safe_stylized_human"} and source_mode not in LIVE_SOURCE_MODES:
        errors.append(
            f"[{desc}.generation_contract.character_reference_mode] 只有真人源视频才能使用写实人物插画桥接，"
            f"当前 source_visual_mode='{source_mode}'，但 character_reference_mode='{char_mode}'"
        )

    if _is_todo_value(contract.get("mode_lock_reason", "")):
        errors.append(f"[{desc}.generation_contract.mode_lock_reason] 仍是占位符，生成前必须说明锁定原因")

    return len(errors) == 0, errors


def validate_scene_prompts(path: str) -> Tuple[bool, List[str], List[str]]:
    """校验 scene_prompts.json"""
    data = _load_json(path)
    if data is None:
        return False, [f"无法读取文件: {path}"], []

    is_valid, errors, warnings = validate(data, SCENE_PROMPTS_SCHEMA, "scene_prompts.json")
    errors.extend(_validate_generation_contract(data, "scene_prompts.json"))
    errors.extend(_validate_style_consistency(data, "scene_prompts.json"))

    # 额外检查：必须有 characters 或 character_ref_prompts
    has_chars = bool(data.get("characters"))
    has_ref_prompts = bool(data.get("character_ref_prompts"))
    if not has_chars and not has_ref_prompts:
        errors.append("[scene_prompts.json] 必须包含 'characters' 或 'character_ref_prompts' 之一")
        is_valid = False

    contract = data.get("generation_contract", {})
    target_mode = contract.get("target_visual_mode", "")
    char_mode = contract.get("character_reference_mode", target_mode)
    scene_mode = contract.get("scene_generation_mode", target_mode)

    if target_mode in TARGET_VISUAL_MODE_VALUES:
        style = data.get("style_consistency", {})
        errors.extend(_check_mode_text_alignment(
            " ".join([
                str(style.get("character_render_mode", "")),
                str(style.get("character_prompt_block", "")),
            ]),
            char_mode,
            "scene_prompts.json.style_consistency(character)",
            warnings,
        ))
        errors.extend(_check_mode_text_alignment(
            " ".join([
                str(style.get("scene_render_mode", "")),
                str(style.get("scene_prompt_block", "")),
            ]),
            scene_mode,
            "scene_prompts.json.style_consistency(scene)",
            warnings,
        ))

    # 检查提示词是否和 generation_contract 对齐
    for i, scene in enumerate(data.get("scenes", [])):
        prompt = scene.get("prompt", "")
        if target_mode in TARGET_VISUAL_MODE_VALUES:
            errors.extend(_check_mode_text_alignment(
                prompt,
                scene_mode,
                f"scene_prompts.json.scenes[{i}].prompt",
                warnings,
            ))

        semantic_anchor = scene.get("semantic_anchor")
        if semantic_anchor is None:
            warnings.append(
                f"[scene_prompts.json.scenes[{i}]] 缺少 semantic_anchor；"
                "建议把内容类型 / 子类判断 / 行为摘要 / 关键证据 / 负约束显式结构化，"
                "避免分析结论在生成阶段丢失。"
            )
        elif not isinstance(semantic_anchor, dict):
            errors.append(
                f"[scene_prompts.json.scenes[{i}].semantic_anchor] "
                f"应为对象，实际为 {type(semantic_anchor).__name__}"
            )
        else:
            errors.extend(
                _check_required_keys(
                    semantic_anchor,
                    SCENE_PROMPTS_SCHEMA.get("scene_semantic_anchor_required", []),
                    f"scene_prompts.json.scenes[{i}].semantic_anchor",
                )
            )
            for field in ("evidence_to_preserve", "negative_constraints"):
                value = semantic_anchor.get(field)
                if field in semantic_anchor and not isinstance(value, list):
                    errors.append(
                        f"[scene_prompts.json.scenes[{i}].semantic_anchor.{field}] "
                        f"应为数组，实际为 {type(value).__name__}"
                    )

    # 跨引用检查：scenes[].main_character 必须存在于 characters[].id
    char_ids = set()
    for c in data.get("characters", []):
        cid = c.get("id")
        if cid:
            char_ids.add(cid)
    for c in data.get("character_ref_prompts", []):
        cid = c.get("character_id")
        if cid:
            char_ids.add(cid)

    if char_ids:
        for i, scene in enumerate(data.get("scenes", [])):
            mc = scene.get("main_character")
            if mc and mc not in char_ids:
                errors.append(
                    f"[scenes[{i}]] main_character='{mc}' 在 characters 列表中找不到对应 id，"
                    f"可用的 id 为：{sorted(char_ids)}"
                )
                is_valid = False

            visible_chars = scene.get("visible_characters", [])
            if visible_chars and not isinstance(visible_chars, list):
                errors.append(
                    f"[scenes[{i}]] visible_characters 应为数组，实际为 {type(visible_chars).__name__}"
                )
                is_valid = False
            elif isinstance(visible_chars, list):
                for visible_char in visible_chars:
                    if visible_char not in char_ids:
                        errors.append(
                            f"[scenes[{i}]] visible_characters 包含未知角色 id '{visible_char}'，"
                            f"可用的 id 为：{sorted(char_ids)}"
                        )
                        is_valid = False

            visible_people_estimate = scene.get("visible_people_estimate")
            if (
                isinstance(visible_people_estimate, (int, float))
                and visible_people_estimate >= 4
                and not scene.get("visible_characters")
            ):
                warnings.append(
                    f"[scenes[{i}]] visible_people_estimate={visible_people_estimate}，"
                    "但没有提供 visible_characters，多人场景容易出现同脸。"
                )

    for i, item in enumerate(data.get("character_ref_prompts", [])):
        prompt = item.get("prompt", "")
        if target_mode in TARGET_VISUAL_MODE_VALUES:
            errors.extend(_check_mode_text_alignment(
                prompt,
                char_mode,
                f"scene_prompts.json.character_ref_prompts[{i}].prompt",
                warnings,
            ))

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def validate_narrative_analysis(path: str) -> Tuple[bool, List[str], List[str]]:
    """校验 narrative_analysis.json"""
    data = _load_json(path)
    if data is None:
        return False, [f"无法读取文件: {path}"], []
    return validate(data, NARRATIVE_ANALYSIS_SCHEMA, "narrative_analysis.json")


def validate_tts_guide(path: str) -> Tuple[bool, List[str], List[str]]:
    """校验 tts_guide.json"""
    data = _load_json(path)
    if data is None:
        return False, [f"无法读取文件: {path}"], []

    is_valid, errors, warnings = validate(data, TTS_GUIDE_SCHEMA, "tts_guide.json")

    if data.get("_skipped"):
        warnings.append("[tts_guide.json] 标记为跳过：当前项目应跳过 TTS 复刻链路")
        return is_valid, errors, warnings

    # 检查文本不为空
    text = data.get("reference_text", "")
    if not text or not text.strip():
        errors.append("[tts_guide.json] 'reference_text' 为空")
        is_valid = False

    return is_valid, errors, warnings


def validate_coherence_analysis(path: str) -> Tuple[bool, List[str], List[str]]:
    """校验 coherence_analysis.json"""
    data = _load_json(path)
    if data is None:
        return False, [f"无法读取文件: {path}"], []
    return validate(data, COHERENCE_ANALYSIS_SCHEMA, "coherence_analysis.json")


def validate_audio_visual_correlation(path: str) -> Tuple[bool, List[str], List[str]]:
    """校验 audio_visual_correlation.json"""
    data = _load_json(path)
    if data is None:
        return False, [f"无法读取文件: {path}"], []
    return validate(data, AUDIO_VISUAL_CORRELATION_SCHEMA, "audio_visual_correlation.json")


def validate_semantic_analysis(path: str) -> Tuple[bool, List[str], List[str]]:
    """校验 semantic_analysis.json"""
    data = _load_json(path)
    if data is None:
        return False, [f"无法读取文件: {path}"], []

    is_valid, errors, warnings = validate(data, SEMANTIC_ANALYSIS_SCHEMA, "semantic_analysis.json")
    errors.extend(_validate_generation_contract(data, "semantic_analysis.json"))
    errors.extend(_validate_style_consistency(data, "semantic_analysis.json"))

    contract = data.get("generation_contract", {})
    target_mode = contract.get("target_visual_mode", "")
    char_mode = contract.get("character_reference_mode", target_mode)
    scene_mode = contract.get("scene_generation_mode", target_mode)

    if target_mode in TARGET_VISUAL_MODE_VALUES:
        style = data.get("style_consistency", {})
        errors.extend(_check_mode_text_alignment(
            " ".join([
                str(style.get("character_render_mode", "")),
                str(style.get("character_prompt_block", "")),
            ]),
            char_mode,
            "semantic_analysis.json.style_consistency(character)",
            warnings,
        ))
        errors.extend(_check_mode_text_alignment(
            " ".join([
                str(style.get("scene_render_mode", "")),
                str(style.get("scene_prompt_block", "")),
            ]),
            scene_mode,
            "semantic_analysis.json.style_consistency(scene)",
            warnings,
        ))

    scene_prisms = data.get("scene_prisms", [])
    prism_required = {
        "narrative_prism": [
            "dramatic_purpose", "coarse_category",
            "candidate_labels", "final_label", "label_status",
        ],
        "subject_prism": [
            "primary_subjects", "subject_scale",
            "organization", "role_relationship", "identity_clues",
        ],
        "action_prism": [
            "primary_action", "action_pattern", "movement_intensity",
            "tempo_rhythm", "interaction_mode", "stage_beats",
        ],
        "scene_prism": ["location_space", "lighting", "props", "evidence"],
        "camera_prism": [
            "shot_type", "framing", "camera_angle",
            "camera_movement", "camera_focus",
        ],
        "constraint_prism": [
            "must_keep", "should_keep", "must_not_change",
            "must_not_generate", "continuity_focus",
        ],
    }
    required_evidence_keys = ["clothing", "footwear", "props_equipment", "text_signals", "environment_clues"]
    subtype_required = [
        "domain",
        "subtype_candidates",
        "final_subtype",
        "confidence",
        "decision_reason",
    ]
    behavior_required = [
        "behavior_label",
        "behavior_summary",
        "behavior_evidence",
        "distinguishing_features",
    ]
    evidence_chain_required = [
        "direct_evidence",
        "supporting_evidence",
        "counter_hypotheses",
        "unresolved_points",
    ]

    for i, scene in enumerate(scene_prisms[:5]):
        if not isinstance(scene, dict):
            errors.append(
                f"[semantic_analysis.json.scene_prisms[{i}]] 应为对象，实际为 {type(scene).__name__}"
            )
            continue

        for prism_key, fields in prism_required.items():
            prism_value = scene.get(prism_key)
            if not isinstance(prism_value, dict):
                errors.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].{prism_key}] "
                    f"应为对象，实际为 {type(prism_value).__name__}"
                )
                continue
            errors.extend(
                _check_required_keys(
                    prism_value,
                    fields,
                    f"semantic_analysis.json.scene_prisms[{i}].{prism_key}",
                )
            )

        narrative = scene.get("narrative_prism", {})
        if isinstance(narrative, dict):
            candidates = narrative.get("candidate_labels", [])
            if not isinstance(candidates, list):
                errors.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].narrative_prism.candidate_labels] "
                    f"应为数组，实际为 {type(candidates).__name__}"
                )
            subtype = narrative.get("subtype_judgment")
            if subtype is None:
                warnings.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].narrative_prism] "
                    "缺少 subtype_judgment；建议把更细的内容子类与判断理由显式结构化。"
                )
            elif not isinstance(subtype, dict):
                errors.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].narrative_prism.subtype_judgment] "
                    f"应为对象，实际为 {type(subtype).__name__}"
                )
            else:
                errors.extend(
                    _check_required_keys(
                        subtype,
                        subtype_required,
                        f"semantic_analysis.json.scene_prisms[{i}].narrative_prism.subtype_judgment",
                    )
                )
                subtype_candidates = subtype.get("subtype_candidates")
                if "subtype_candidates" in subtype and not isinstance(subtype_candidates, list):
                    errors.append(
                        f"[semantic_analysis.json.scene_prisms[{i}].narrative_prism.subtype_judgment.subtype_candidates] "
                        f"应为数组，实际为 {type(subtype_candidates).__name__}"
                    )

        for prism_key, list_fields in {
            "subject_prism": ["primary_subjects", "identity_clues"],
            "action_prism": ["stage_beats"],
            "scene_prism": ["props"],
            "constraint_prism": [
                "must_keep", "should_keep", "must_not_change",
                "must_not_generate", "continuity_focus",
            ],
        }.items():
            prism_value = scene.get(prism_key, {})
            if not isinstance(prism_value, dict):
                continue
            for field in list_fields:
                value = prism_value.get(field)
                if not isinstance(value, list):
                    errors.append(
                        f"[semantic_analysis.json.scene_prisms[{i}].{prism_key}.{field}] "
                        f"应为数组，实际为 {type(value).__name__}"
                    )

        action_prism = scene.get("action_prism", {})
        if isinstance(action_prism, dict):
            behavior = action_prism.get("behavior_judgment")
            if behavior is None:
                warnings.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].action_prism] "
                    "缺少 behavior_judgment；建议把行为判断与动作证据单独结构化。"
                )
            elif not isinstance(behavior, dict):
                errors.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].action_prism.behavior_judgment] "
                    f"应为对象，实际为 {type(behavior).__name__}"
                )
            else:
                errors.extend(
                    _check_required_keys(
                        behavior,
                        behavior_required,
                        f"semantic_analysis.json.scene_prisms[{i}].action_prism.behavior_judgment",
                    )
                )
                for field in ("behavior_evidence", "distinguishing_features"):
                    value = behavior.get(field)
                    if field in behavior and not isinstance(value, list):
                        errors.append(
                            f"[semantic_analysis.json.scene_prisms[{i}].action_prism.behavior_judgment.{field}] "
                            f"应为数组，实际为 {type(value).__name__}"
                        )

        scene_prism = scene.get("scene_prism", {})
        if isinstance(scene_prism, dict):
            evidence = scene_prism.get("evidence")
            if not isinstance(evidence, dict):
                errors.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].scene_prism.evidence] "
                    f"应为对象，实际为 {type(evidence).__name__}"
                )
            else:
                for key in required_evidence_keys:
                    if key not in evidence:
                        errors.append(
                            f"[semantic_analysis.json.scene_prisms[{i}].scene_prism.evidence] "
                            f"缺少必需字段: '{key}'"
                        )
                    elif not isinstance(evidence[key], list):
                        errors.append(
                            f"[semantic_analysis.json.scene_prisms[{i}].scene_prism.evidence.{key}] "
                            f"应为数组，实际为 {type(evidence[key]).__name__}"
                        )
            evidence_chain = scene_prism.get("evidence_chain")
            if evidence_chain is None:
                warnings.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].scene_prism] "
                    "缺少 evidence_chain；建议把直接证据、辅助证据和反例假设分开记录。"
                )
            elif not isinstance(evidence_chain, dict):
                errors.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].scene_prism.evidence_chain] "
                    f"应为对象，实际为 {type(evidence_chain).__name__}"
                )
            else:
                errors.extend(
                    _check_required_keys(
                        evidence_chain,
                        evidence_chain_required,
                        f"semantic_analysis.json.scene_prisms[{i}].scene_prism.evidence_chain",
                    )
                )
                for field in evidence_chain_required:
                    value = evidence_chain.get(field)
                    if field in evidence_chain and not isinstance(value, list):
                        errors.append(
                            f"[semantic_analysis.json.scene_prisms[{i}].scene_prism.evidence_chain.{field}] "
                            f"应为数组，实际为 {type(value).__name__}"
                        )

        constraint_prism = scene.get("constraint_prism", {})
        if isinstance(constraint_prism, dict):
            negative_constraints = constraint_prism.get("negative_constraints")
            if negative_constraints is None:
                warnings.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].constraint_prism] "
                    "缺少 negative_constraints；建议把最容易生成错的高风险点单独列出来。"
                )
            elif not isinstance(negative_constraints, list):
                errors.append(
                    f"[semantic_analysis.json.scene_prisms[{i}].constraint_prism.negative_constraints] "
                    f"应为数组，实际为 {type(negative_constraints).__name__}"
                )

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


# ============================================================
# 工具函数
# ============================================================

def _load_json(path: str) -> dict | None:
    """安全加载 JSON"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [校验] 无法读取 JSON: {path} ({e})")
        return None


def print_validation_result(
    name: str,
    is_valid: bool,
    errors: List[str],
    warnings: List[str],
):
    """打印校验结果"""
    if is_valid:
        print(f"  ✓ {name} 校验通过")
    else:
        print(f"  ✗ {name} 校验失败:")
        for e in errors:
            print(f"    ✗ {e}")

    for w in warnings:
        print(f"    ⚠ {w}")


def validate_and_exit_if_invalid(
    path: str,
    validator_func,
    name: str = "",
):
    """校验并在失败时退出（供其他脚本调用）"""
    is_valid, errors, warnings = validator_func(path)
    print_validation_result(name or path, is_valid, errors, warnings)

    if not is_valid:
        print(f"\n请根据模板修正 {path}，模板位于 assets/schema_templates/")
        sys.exit(1)

    return True


# ============================================================
# CLI 入口
# ============================================================

def main():
    """命令行校验工具"""
    import argparse

    parser = argparse.ArgumentParser(description="JSON Schema 校验器")
    parser.add_argument("--file", required=True, help="要校验的 JSON 文件路径")
    parser.add_argument(
        "--type",
        required=True,
        choices=[
            "scene_prompts",
            "narrative",
            "semantic",
            "tts_guide",
            "coherence",
            "audio_visual",
        ],
        help="文件类型",
    )

    args = parser.parse_args()

    validators = {
        "scene_prompts": validate_scene_prompts,
        "narrative": validate_narrative_analysis,
        "semantic": validate_semantic_analysis,
        "tts_guide": validate_tts_guide,
        "coherence": validate_coherence_analysis,
        "audio_visual": validate_audio_visual_correlation,
    }

    print(f"校验 {args.file} (类型: {args.type})")
    is_valid, errors, warnings = validators[args.type](args.file)
    print_validation_result(args.file, is_valid, errors, warnings)

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
