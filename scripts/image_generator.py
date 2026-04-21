#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色参考图生成器（步骤8）
读取 scene_prompts.json 中的角色参考图提示词，按 generation_contract 生成统一形态的角色参考图
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# 添加脚本目录到 path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from api_client import load_config, generate_seedream_image, get_model_config
from schema_validator import (
    validate_scene_prompts,
    print_validation_result,
    validate_generation_contract_runtime,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BRIDGE_REFERENCE_MODES = {
    "pseudo_realistic_human_illustration",
    "safe_stylized_human",
}
LIVE_SOURCE_MODES = {
    "live_action",
    "stylized_live_action",
}

MODE_HARD_RULES = {
    "live_action": (
        "最终只输出一张单人真人角色参考照；真实人类比例、真实皮肤材质、真实服装褶皱；"
        "纯净背景，禁止插画、动漫、卡通、角色设定图质感。"
    ),
    "stylized_live_action": (
        "最终只输出一张单人仿真人角色参考照；保持真实人类比例和真人皮肤、服装材质，"
        "允许轻微风格化，但绝不能变成动漫插画或卡通。"
    ),
    "anime": (
        "最终只输出一张单人动漫角色参考图；统一二次元插画语言，禁止真人照片质感。"
    ),
    "pseudo_realistic_human_illustration": (
        "最终只输出一张单人写实人物插画参考图；非照片、真实人类比例、"
        "保留真实皮肤明暗层次、鼻梁唇部结构和布料褶皱；干净浅色背景；"
        "禁止漫画脸、二次元大眼、赛璐璐阴影、卡通线稿。"
    ),
    # 兼容旧项目里的历史命名；新文件统一改用 pseudo_realistic_human_illustration
    "safe_stylized_human": (
        "最终只输出一张单人写实人物插画参考图；非照片、真实人类比例、"
        "保留真实皮肤明暗层次、鼻梁唇部结构和布料褶皱；干净浅色背景；"
        "禁止漫画脸、二次元大眼、赛璐璐阴影、卡通线稿。"
    ),
}

MODE_AUTO_PROMPT = {
    "live_action": "真人角色参考照，单人，头肩像到胸像，纯净背景，",
    "stylized_live_action": "仿真人角色参考照，单人，头肩像到胸像，纯净背景，真实人类比例，",
    "anime": "动漫角色设定图，单人，头肩像到胸像，纯净背景，",
    "pseudo_realistic_human_illustration": (
        "realistic character illustration，写实人物插画参考图，单人，头肩像到胸像，"
        "纯净背景，非照片，realistic illustration，真实人类比例，真实皮肤明暗和布料褶皱，"
    ),
    "safe_stylized_human": (
        "realistic character illustration，写实人物插画参考图，单人，头肩像到胸像，"
        "纯净背景，非照片，realistic illustration，真实人类比例，真实皮肤明暗和布料褶皱，"
    ),
}

REFERENCE_TYPE_DEFAULT = "identity_portrait"
REFERENCE_FILENAME_SUFFIX = {
    REFERENCE_TYPE_DEFAULT: "",
    "full_body_outfit": "__full_body_outfit",
}


def _load_existing_manifest(output_dir: Path) -> dict:
    manifest_path = output_dir / "refs_manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _normalize_reference_type(reference_type: str | None) -> str:
    if not reference_type:
        return REFERENCE_TYPE_DEFAULT
    return str(reference_type).strip() or REFERENCE_TYPE_DEFAULT


def _build_output_path(output_dir: Path, char_id: str, reference_type: str) -> Path:
    suffix = REFERENCE_FILENAME_SUFFIX.get(reference_type, f"__{reference_type}")
    return output_dir / f"{char_id}{suffix}.jpg"


def _find_existing_ref_entry(existing_manifest: dict, char_id: str, reference_type: str) -> dict:
    if not existing_manifest:
        return {}

    char_info = existing_manifest.get("characters", {}).get(char_id, {})
    if not isinstance(char_info, dict):
        return {}

    for item in char_info.get("reference_images", []):
        if not isinstance(item, dict):
            continue
        item_type = _normalize_reference_type(item.get("reference_type"))
        if item_type == reference_type:
            return item

    if reference_type == REFERENCE_TYPE_DEFAULT and char_info.get("path"):
        return char_info

    return {}


def _can_skip_existing_ref(
    existing_manifest: dict,
    char_id: str,
    expected_mode: str,
    reference_type: str,
) -> bool:
    if not existing_manifest:
        return False

    manifest_contract = existing_manifest.get("generation_contract", {})
    manifest_mode = ""
    if isinstance(manifest_contract, dict):
        manifest_mode = str(manifest_contract.get("character_reference_mode", ""))

    ref_info = _find_existing_ref_entry(existing_manifest, char_id, reference_type)
    if not ref_info:
        return False

    char_mode = str(ref_info.get("generation_mode", manifest_mode))
    return bool(expected_mode and char_mode == expected_mode and ref_info.get("status") in {"success", "skipped"})


def _build_style_consistency_block(style_consistency: dict | None, mode: str) -> str:
    """把统一风格约束整理成可直接拼到 prompt 里的文本块"""
    if not isinstance(style_consistency, dict) or not style_consistency:
        return ""

    mode_field = "character_prompt_block" if mode == "character" else "scene_prompt_block"
    lines = ["【统一风格模板】"]

    if style_consistency.get("style_family"):
        lines.append(f"项目风格：{style_consistency['style_family']}")
    if style_consistency.get(mode_field):
        lines.append(style_consistency[mode_field])

    field_pairs = [
        ("character_render_mode", "角色图画法"),
        ("lighting_rule", "光线规则"),
        ("palette_rule", "配色规则"),
        ("background_rule", "背景规则"),
        ("framing_rule", "构图规则"),
        ("costume_rule", "服装规则"),
    ]
    if mode != "character":
        field_pairs = [
            ("scene_render_mode", "场景画法"),
            ("lighting_rule", "光线规则"),
            ("palette_rule", "配色规则"),
            ("framing_rule", "构图规则"),
            ("costume_rule", "服装规则"),
        ]

    for key, label in field_pairs:
        value = style_consistency.get(key)
        if value:
            lines.append(f"{label}：{value}")

    must_keep = style_consistency.get("must_keep", [])
    if must_keep:
        lines.append("必须保持：" + "；".join(str(item) for item in must_keep))

    negative_constraints = style_consistency.get("negative_constraints", [])
    if negative_constraints:
        lines.append("禁止偏离：" + "；".join(str(item) for item in negative_constraints))

    return "\n".join(lines)


def _build_character_reference_template_block(
    generation_contract: dict | None,
    reference_type: str,
) -> str:
    """为步骤8生成专用模板，避免把步骤9的场景/视频约束污染到角色参考图。"""
    contract = generation_contract or {}
    source_mode = str(contract.get("source_visual_mode", "")).strip()
    char_mode = str(contract.get("character_reference_mode", "")).strip()

    lines = ["【角色参考图模板】"]

    if char_mode in BRIDGE_REFERENCE_MODES:
        lines.append(
            "当前任务只生成单人写实人物插画桥接参考图，用来锁定身份或服装；"
            "这不是场景图，也不是最终视频画面。"
        )
        lines.append(
            "介质：写实人物插画，非照片，真实人类比例，真实面部结构，"
            "柔和皮肤明暗层次，自然发丝细节，真实布料褶皱。"
        )
        lines.append(
            "背景：纯白或极浅灰无纹理背景；不要灯具、墙角、地板、训练馆、文字、道具、第二个人。"
        )
        if reference_type == "full_body_outfit":
            lines.append(
                "构图：单人全身直立，头到脚完整入镜，完整露出长裤和鞋子；"
                "不要裁切腿部，不要半身，不要多人。"
            )
        else:
            lines.append(
                "构图：单人胸像到半身，只锁定脸型、五官、发型、肩线和上衣领口；"
                "不要腰部以下，不要鞋子，不要复杂场景。"
            )
        lines.append(
            "禁止：不要动漫立绘感，不要漫画脸，不要夸张大眼，不要赛璐璐平涂，"
            "不要卡通线稿，不要真人照片感。"
        )
        if source_mode not in LIVE_SOURCE_MODES:
            lines.append(
                "注意：写实人物插画桥接只适用于真人源视频；当前 source_visual_mode 看起来不匹配。"
            )
    elif char_mode == "anime":
        lines.append("当前任务只生成单人动漫角色参考图，用于锁定角色身份或全身服装。")
        lines.append("介质：统一动漫角色设定图语言，轮廓清晰，禁止真人照片质感。")
        lines.append("背景：纯净单色或极简背景，不要第二个人，不要复杂场景。")
        if reference_type == "full_body_outfit":
            lines.append("构图：单人全身站姿，完整露出服装与鞋子。")
        else:
            lines.append("构图：单人胸像到半身，优先锁定脸型与发型。")
    else:
        lines.append(
            "当前任务只生成单人角色参考图，不承担场景描述和视频生成任务；"
            "请只锁定人物身份、发型和服装。"
        )
        if reference_type == "full_body_outfit":
            lines.append("构图：单人全身站姿，完整露出服装和鞋子。")
        else:
            lines.append("构图：单人胸像到半身，锁定脸型和发型。")

    return "\n".join(lines)


def _build_character_prompt(
    style_consistency: dict | None,
    generation_contract: dict | None,
    role_prompt: str,
    reference_type: str = REFERENCE_TYPE_DEFAULT,
) -> str:
    """组装最终角色参考图 prompt"""
    parts = []
    mode = ""
    if isinstance(generation_contract, dict):
        mode = generation_contract.get("character_reference_mode", "")
    template_block = _build_character_reference_template_block(
        generation_contract,
        reference_type=reference_type,
    )
    if template_block:
        parts.append(template_block)
    parts.append("【硬性输出要求】")
    parts.append(MODE_HARD_RULES.get(mode, "生成前必须先锁定 generation_contract.character_reference_mode。"))
    if reference_type == "full_body_outfit":
        parts.append("【镜头要求】")
        parts.append(
            "必须输出单人全身参考图，完整露出发型、上衣、长裤和鞋子；"
            "人物占画面85%以上，姿态自然直立，不能裁掉腿部和鞋子。"
        )
    else:
        parts.append("【镜头要求】")
        parts.append(
            "默认输出单人身份参考图，优先锁定脸型、发型、上衣领口和肩部结构；"
            "不需要展示复杂背景。"
        )
    costume_rule = ""
    if isinstance(style_consistency, dict):
        costume_rule = str(style_consistency.get("costume_rule", "")).strip()
    if costume_rule:
        parts.append("【服装提醒】")
        parts.append(costume_rule)
    parts.append("【当前角色差异】")
    parts.append(role_prompt)
    return "\n".join(parts)


async def generate_character_refs(
    prompts_path: Path,
    output_dir: Path,
    config_path: Path | None = None,
    api_key: str | None = None,
) -> dict:
    """为所有角色生成参考图"""
    config = load_config(config_path) if config_path else None

    # 读取并校验提示词
    if not prompts_path.exists():
        logger.error(f"提示词文件不存在: {prompts_path}")
        return {"success": False, "error": f"文件不存在: {prompts_path}"}

    # Schema 校验
    is_valid, errors, warnings = validate_scene_prompts(str(prompts_path))
    print_validation_result("scene_prompts.json", is_valid, errors, warnings)
    if not is_valid:
        logger.error("scene_prompts.json 校验失败，请根据模板修正: assets/schema_templates/scene_prompts_template.json")
        return {"success": False, "error": f"Schema 校验失败: {'; '.join(errors)}"}

    with open(prompts_path, "r", encoding="utf-8") as f:
        prompts_data = json.load(f)
    contract_valid, contract_errors = validate_generation_contract_runtime(
        prompts_data, "scene_prompts.json"
    )
    if not contract_valid:
        for error in contract_errors:
            logger.error(error)
        return {"success": False, "error": "generation_contract 未锁定或存在跨形态冲突"}

    generation_contract = prompts_data.get("generation_contract", {})
    style_consistency = prompts_data.get("style_consistency", {})
    char_mode = generation_contract.get("character_reference_mode", "")

    # 提取角色参考图提示词
    character_prompts = prompts_data.get("character_ref_prompts", [])
    if not character_prompts:
        # 尝试从角色定义自动生成提示词
        characters = prompts_data.get("characters", [])
        if characters:
            character_prompts = []
            for char in characters:
                char_id = char.get("id", char.get("name", "unknown"))
                prompt = (
                    f"{MODE_AUTO_PROMPT.get(char_mode, '')}"
                    f"{char.get('gender', '')}，{char.get('age', '')}，"
                    f"{char.get('appearance', '')}，"
                    f"穿着{char.get('clothing', '').split('→')[0] if '→' in char.get('clothing', '') else char.get('clothing', '')}"
                )
                character_prompts.append({
                    "character_id": char_id,
                    "prompt": prompt,
                })

    if not character_prompts:
        logger.error("未找到角色参考图提示词（character_ref_prompts 或 characters）")
        return {"success": False, "error": "未找到角色提示词"}

    output_dir.mkdir(parents=True, exist_ok=True)
    existing_manifest = _load_existing_manifest(output_dir)
    results = []
    manifest = {
        "generation_contract": generation_contract,
        "characters": {},
    }

    for item in character_prompts:
        char_id = item.get("character_id", item.get("id", "unknown"))
        prompt = item.get("prompt", "")
        reference_type = _normalize_reference_type(item.get("reference_type"))
        final_prompt = _build_character_prompt(
            style_consistency,
            generation_contract,
            prompt,
            reference_type=reference_type,
        )

        if not prompt:
            logger.warning(f"跳过空提示词: {char_id}")
            continue

        output_path = _build_output_path(output_dir, char_id, reference_type)
        if output_path.exists():
            if _can_skip_existing_ref(existing_manifest, char_id, char_mode, reference_type):
                logger.info(f"跳过已存在且形态一致: {output_path}")
                char_manifest = manifest["characters"].setdefault(char_id, {"reference_images": []})
                ref_item = {
                    "path": str(output_path),
                    "prompt": prompt,
                    "final_prompt": final_prompt,
                    "reference_type": reference_type,
                    "generation_mode": char_mode,
                    "status": "skipped",
                }
                char_manifest.setdefault("reference_images", []).append(ref_item)
                if reference_type == REFERENCE_TYPE_DEFAULT:
                    char_manifest.update(ref_item)
                results.append({"character_id": char_id, "status": "skipped", "path": str(output_path)})
                continue
            logger.info(f"发现旧参考图但形态契约不明或不一致，将重新生成: {output_path}")

        logger.info(f"生成角色参考图: {char_id}")
        logger.info(f"  最终提示词: {final_prompt[:120]}...")

        success = await generate_seedream_image(
            prompt=final_prompt,
            output_path=output_path,
            config=config,
            api_key_override=api_key,
        )

        status = "success" if success else "failed"
        char_manifest = manifest["characters"].setdefault(char_id, {"reference_images": []})
        ref_item = {
            "path": str(output_path),
            "prompt": prompt,
            "final_prompt": final_prompt,
            "reference_type": reference_type,
            "generation_mode": char_mode,
            "status": status,
        }
        char_manifest.setdefault("reference_images", []).append(ref_item)
        if reference_type == REFERENCE_TYPE_DEFAULT or "path" not in char_manifest:
            char_manifest.update(ref_item)
        results.append({"character_id": char_id, "status": status, "path": str(output_path)})

        if success:
            logger.info(f"  ✓ 生成成功: {output_path}")
        else:
            logger.error(f"  ✗ 生成失败: {char_id}")

    # 保存 manifest
    manifest_path = output_dir / "refs_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info(f"参考图 manifest 已保存: {manifest_path}")

    success_count = sum(1 for r in results if r["status"] == "success")
    logger.info(f"完成: {success_count}/{len(results)} 角色参考图生成成功")

    return {
        "success": success_count > 0,
        "results": results,
        "manifest_path": str(manifest_path),
    }


def main():
    parser = argparse.ArgumentParser(description="角色参考图生成器（步骤8）")
    parser.add_argument("--prompts_json", type=str, required=True, help="scene_prompts.json 路径")
    parser.add_argument("--output_dir", type=str, default="output/角色参考图", help="输出目录")
    parser.add_argument("--config", type=str, default=None, help="api_config.yaml 路径")
    parser.add_argument("--api_key", type=str, default=None, help="API 密钥（覆盖配置文件）")

    args = parser.parse_args()

    result = asyncio.run(generate_character_refs(
        prompts_path=Path(args.prompts_json),
        output_dir=Path(args.output_dir),
        config_path=Path(args.config) if args.config else None,
        api_key=args.api_key,
    ))

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
