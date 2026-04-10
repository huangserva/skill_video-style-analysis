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


# ============================================================
# Schema 定义
# ============================================================

SCENE_PROMPTS_SCHEMA = {
    "description": "步骤6输出 - 场景提示词 + 角色定义",
    "required_keys": ["scenes"],
    "optional_keys": ["characters", "character_ref_prompts", "visual_style_prompt"],
    "scenes_item_required": ["scene_id", "prompt", "duration"],
    "scenes_item_optional": ["main_character", "extra_refs"],
    "characters_item_required": ["id", "gender", "appearance"],
    "characters_item_optional": ["age", "clothing", "name"],
    "character_ref_prompts_item_required": ["character_id", "prompt"],
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
    "optional_keys": ["duration_target"],
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


def validate_scene_prompts(path: str) -> Tuple[bool, List[str], List[str]]:
    """校验 scene_prompts.json"""
    data = _load_json(path)
    if data is None:
        return False, [f"无法读取文件: {path}"], []

    is_valid, errors, warnings = validate(data, SCENE_PROMPTS_SCHEMA, "scene_prompts.json")

    # 额外检查：必须有 characters 或 character_ref_prompts
    has_chars = bool(data.get("characters"))
    has_ref_prompts = bool(data.get("character_ref_prompts"))
    if not has_chars and not has_ref_prompts:
        errors.append("[scene_prompts.json] 必须包含 'characters' 或 'character_ref_prompts' 之一")
        is_valid = False

    # 检查提示词是否包含必需前缀
    for i, scene in enumerate(data.get("scenes", [])):
        prompt = scene.get("prompt", "")
        if prompt and "realistic photo style" not in prompt.lower():
            warnings.append(
                f"[scenes[{i}]] 提示词未包含 'realistic photo style' 前缀（SKILL.md 强制要求）"
            )

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
