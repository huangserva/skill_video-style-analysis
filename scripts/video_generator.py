#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场景视频生成器（步骤9）
读取 scene_prompts.json 和角色参考图，调用 Seedance 2.0 API 生成场景视频
"""

import argparse
import asyncio
import copy
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from api_client import load_config, generate_seedance_video, get_model_config
from schema_validator import (
    validate_scene_prompts,
    print_validation_result,
    validate_generation_contract_runtime,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCENE_MODE_HARD_RULES = {
    "live_action": (
        "最终必须输出真人出镜视频；真实皮肤、真实布料、真实手机实拍感；"
        "不要插画脸、不要动漫材质、不要卡通渲染、不要塑料感人物。"
    ),
    "stylized_live_action": (
        "最终必须输出仿真人视频；保持真实人类比例和真实布料材质；"
        "允许轻微风格化，但不要跑成动漫或卡通。"
    ),
    "anime": (
        "最终必须输出动漫视频；统一动画角色脸和动画材质；"
        "不要真人照片感和真人皮肤质感。"
    ),
}

SCENE_PROMPT_BRIDGE_TERMS = (
    "pseudo realistic human illustration",
    "pseudo_realistic_human_illustration",
    "仿真人插画参考图",
    "仿真人插画",
    "safe stylized human",
    "safe_stylized_human",
    "安全参考插画人",
    "参考插画人",
    "identity_portrait",
    "full_body_outfit",
)


def _is_scene_safe_text(text: str) -> bool:
    lowered = (text or "").lower()
    return not any(term.lower() in lowered for term in SCENE_PROMPT_BRIDGE_TERMS)


def _to_scene_only_text(text: str) -> str:
    """把混合了参考图描述的规则裁成只给步骤9看的场景版本"""
    raw = str(text or "").strip()
    if not raw:
        return ""

    if "；场景" in raw:
        return "场景" + raw.split("；场景", 1)[1]

    if "参考图做成真人照片" in raw:
        return ""

    if raw.startswith("角色参考图") or raw.startswith("参考图"):
        return ""

    return raw


def build_generation_contract_block(
    generation_contract: dict | None,
    mode: str = "scene",
) -> str:
    """把统一生成契约整理成 prompt 里的固定文本块"""
    if not isinstance(generation_contract, dict) or not generation_contract:
        return ""

    lines = ["【统一生成契约】"]
    field_pairs = [
        ("source_visual_mode", "源视频形态"),
        ("target_visual_mode", "目标形态"),
        ("character_reference_mode", "参考图形态"),
        ("scene_generation_mode", "视频输出形态"),
        ("mode_lock_reason", "锁定原因"),
        ("fallback_policy", "降级规则"),
    ]
    if mode == "scene":
        field_pairs = [
            ("source_visual_mode", "源视频形态"),
            ("target_visual_mode", "目标形态"),
            ("scene_generation_mode", "视频输出形态"),
        ]

    for key, label in field_pairs:
        value = generation_contract.get(key)
        if value:
            lines.append(f"{label}：{value}")

    list_pairs = [
        ("required_keywords", "必须出现"),
        ("forbidden_keywords", "禁止出现"),
        ("consistency_rules", "一致性规则"),
    ]
    for key, label in list_pairs:
        value = generation_contract.get(key)
        if isinstance(value, list) and value:
            filtered_items = [str(item) for item in value]
            if mode == "scene":
                filtered_items = [item for item in filtered_items if _is_scene_safe_text(item)]
            if filtered_items:
                lines.append(f"{label}：" + "；".join(filtered_items))

    if mode == "scene":
        final_mode = str(
            generation_contract.get("scene_generation_mode")
            or generation_contract.get("target_visual_mode")
            or ""
        )
        hard_rule = SCENE_MODE_HARD_RULES.get(final_mode)
        if hard_rule:
            lines.append(f"最终输出要求：{hard_rule}")

    return "\n".join(lines)


def build_style_consistency_block(
    style_consistency: dict | None,
    mode: str = "scene",
    generation_contract: dict | None = None,
) -> str:
    """把统一风格约束整理成 prompt 里的文本块"""
    if not isinstance(style_consistency, dict) or not style_consistency:
        return ""

    mode_field = "scene_prompt_block" if mode == "scene" else "character_prompt_block"
    lines = ["【统一风格模板】"]

    if mode != "scene" and style_consistency.get("style_family"):
        lines.append(f"项目风格：{style_consistency['style_family']}")
    if style_consistency.get(mode_field):
        mode_text = str(style_consistency[mode_field])
        if mode == "scene":
            if _is_scene_safe_text(mode_text):
                lines.append(mode_text)
            else:
                scene_mode = ""
                if isinstance(generation_contract, dict):
                    scene_mode = str(
                        generation_contract.get("scene_generation_mode")
                        or generation_contract.get("target_visual_mode")
                        or ""
                    )
                if scene_mode == "live_action":
                    lines.append(
                        "输入参考图只用于锁定人物身份、发型、服装、裤型和鞋子，"
                        "不代表最终画面介质；最终必须是真人出镜、真实皮肤、真实布料、手机实拍感。"
                    )
                elif scene_mode:
                    lines.append(
                        "输入参考图只用于锁定人物身份和服装连续性，不代表最终画面介质；"
                        "最终必须严格服从 scene_generation_mode。"
                    )
        else:
            lines.append(mode_text)

    field_pairs = [
        ("scene_render_mode", "场景画法"),
        ("lighting_rule", "光线规则"),
        ("palette_rule", "配色规则"),
        ("framing_rule", "构图规则"),
        ("costume_rule", "服装规则"),
    ]
    if mode != "scene":
        field_pairs = [
            ("character_render_mode", "角色图画法"),
            ("lighting_rule", "光线规则"),
            ("palette_rule", "配色规则"),
            ("background_rule", "背景规则"),
            ("framing_rule", "构图规则"),
            ("costume_rule", "服装规则"),
        ]

    for key, label in field_pairs:
        value = style_consistency.get(key)
        if value:
            text_value = str(value)
            if mode == "scene":
                text_value = _to_scene_only_text(text_value)
                if not text_value or not _is_scene_safe_text(text_value):
                    continue
            lines.append(f"{label}：{text_value}")

    must_keep = style_consistency.get("must_keep", [])
    if must_keep:
        filtered = [str(item) for item in must_keep]
        if mode == "scene":
            filtered = [
                scene_item
                for item in filtered
                for scene_item in [_to_scene_only_text(item)]
                if scene_item and _is_scene_safe_text(scene_item)
            ]
        if filtered:
            lines.append("必须保持：" + "；".join(filtered))

    negative_constraints = style_consistency.get("negative_constraints", [])
    if negative_constraints:
        filtered = [str(item) for item in negative_constraints]
        if mode == "scene":
            filtered = [
                scene_item
                for item in filtered
                for scene_item in [_to_scene_only_text(item)]
                if scene_item and _is_scene_safe_text(scene_item)
            ]
        if filtered:
            lines.append("禁止偏离：" + "；".join(filtered))

    return "\n".join(lines)


def build_scene_prompt(
    generation_contract: dict | None,
    style_consistency: dict | None,
    scene_prompt: str,
) -> str:
    """组装最终场景 prompt"""
    contract_block = build_generation_contract_block(generation_contract, mode="scene")
    style_block = build_style_consistency_block(
        style_consistency,
        "scene",
        generation_contract=generation_contract,
    )
    blocks = [block for block in [contract_block, style_block] if block]
    if not blocks:
        return scene_prompt
    return "\n".join([*blocks, "【当前场景要求】", scene_prompt])


def parse_resolution(resolution: str) -> tuple[int, int]:
    """解析 WxH 分辨率字符串"""
    if not resolution or "x" not in resolution:
        return 0, 0
    width_text, height_text = resolution.lower().split("x", 1)
    try:
        return int(width_text.strip()), int(height_text.strip())
    except ValueError:
        return 0, 0


def get_video_dimensions(path: Path) -> tuple[int, int]:
    """读取视频首个视频流的宽高"""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0, 0
    return parse_resolution(result.stdout.strip())


def normalize_video_size(video_path: Path, target_width: int, target_height: int) -> bool:
    """将生成视频缩放/补边到目标尺寸，确保最终成片与源视频一致"""
    if target_width <= 0 or target_height <= 0 or not video_path.exists():
        return True

    current_width, current_height = get_video_dimensions(video_path)
    if (current_width, current_height) == (target_width, target_height):
        return True

    fd, temp_path_str = tempfile.mkstemp(prefix=f"{video_path.stem}_norm_", suffix=".mp4", dir=video_path.parent)
    os.close(fd)
    temp_path = Path(temp_path_str)
    vf = (
        f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
        f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(temp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"视频尺寸归一化失败: {result.stderr[-500:]}")
        temp_path.unlink(missing_ok=True)
        return False

    temp_path.replace(video_path)
    logger.info(f"场景尺寸已统一到源视频大小: {target_width}x{target_height}")
    return True


def load_refs_manifest(refs_dir: Path) -> dict:
    """读取角色参考图 manifest"""
    manifest_path = refs_dir / "refs_manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _normalize_reference_type(reference_type: str | None) -> str:
    if not reference_type:
        return "identity_portrait"
    return str(reference_type).strip() or "identity_portrait"


def _manifest_generation_mode(manifest: dict) -> str:
    """读取角色参考图 manifest 中记录的生成形态"""
    contract = manifest.get("generation_contract", {})
    if isinstance(contract, dict) and contract.get("character_reference_mode"):
        return str(contract.get("character_reference_mode"))

    for char_info in manifest.get("characters", {}).values():
        if isinstance(char_info, dict) and char_info.get("generation_mode"):
            return str(char_info.get("generation_mode"))

    return ""


def validate_refs_manifest_runtime(refs_dir: Path, generation_contract: dict) -> tuple[bool, list[str]]:
    """运行时校验：角色参考图 manifest 必须和当前项目的统一生成形态一致"""
    errors = []
    manifest = load_refs_manifest(refs_dir)
    if not manifest:
        errors.append(
            f"[video_generator] 参考图目录缺少 refs_manifest.json：{refs_dir}。"
            "请先用步骤8在当前 generation_contract 下重新生成参考图。"
        )
        return False, errors

    expected_mode = generation_contract.get("character_reference_mode", "")
    actual_mode = _manifest_generation_mode(manifest)

    if expected_mode and actual_mode and expected_mode != actual_mode:
        errors.append(
            f"[video_generator] 当前项目要求的角色参考图形态是 '{expected_mode}'，"
            f"但 refs_manifest.json 记录的是 '{actual_mode}'。"
            "这说明参考图是旧形态产物，不能继续拿来生成视频。"
        )

    if expected_mode and not actual_mode:
        errors.append(
            "[video_generator] refs_manifest.json 没有记录 generation_mode，"
            "无法确认角色参考图是否和当前项目一致，请重新跑步骤8。"
        )

    return len(errors) == 0, errors


def load_existing_videos_manifest(output_dir: Path) -> dict:
    """读取历史视频 manifest，用于判断旧视频是否还能复用"""
    manifest_path = output_dir / "videos_manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def can_skip_existing_video(existing_manifest: dict, expected_mode: str) -> bool:
    """只有当旧视频和当前统一生成形态一致时，才允许跳过"""
    if not existing_manifest:
        return False

    contract = existing_manifest.get("generation_contract", {})
    if not isinstance(contract, dict):
        return False

    return str(contract.get("scene_generation_mode", "")) == expected_mode


def find_character_ref_variants(refs_dir: Path, character_id: str) -> list[dict]:
    """查找角色参考图的所有变体"""
    manifest = load_refs_manifest(refs_dir)
    char_info = manifest.get("characters", {}).get(character_id, {})
    variants: list[dict] = []

    if isinstance(char_info, dict):
        for item in char_info.get("reference_images", []):
            if not isinstance(item, dict):
                continue
            path_text = item.get("path")
            if not path_text:
                continue
            ref_path = Path(path_text)
            if ref_path.exists():
                variants.append({
                    "path": ref_path,
                    "reference_type": _normalize_reference_type(item.get("reference_type")),
                })

        if not variants and char_info.get("path"):
            ref_path = Path(char_info["path"])
            if ref_path.exists():
                variants.append({
                    "path": ref_path,
                    "reference_type": _normalize_reference_type(char_info.get("reference_type")),
                })

    if variants:
        return variants

    # 兜底：按文件名查找
    for ext in ["jpg", "jpeg", "png"]:
        primary = refs_dir / f"{character_id}.{ext}"
        if primary.exists():
            variants.append({"path": primary, "reference_type": "identity_portrait"})
        full_body = refs_dir / f"{character_id}__full_body_outfit.{ext}"
        if full_body.exists():
            variants.append({"path": full_body, "reference_type": "full_body_outfit"})
    return variants


def _append_unique_ref(ref_images: list[Path], seen_paths: set[str], ref_path: Path) -> None:
    key = str(ref_path.resolve()) if ref_path.exists() else str(ref_path)
    if key in seen_paths:
        return
    ref_images.append(ref_path)
    seen_paths.add(key)


def build_scene_reference_images(
    refs_dir: Path,
    scene: dict,
    max_reference_images: int,
) -> list[Path]:
    """按角色重要性组合多人参考图，避免多人场景同脸和服装漂移"""
    ref_images: list[Path] = []
    seen_paths: set[str] = set()

    main_character = scene.get("main_character", "")
    visible_characters = scene.get("visible_characters", [])
    ordered_characters: list[str] = []
    for char_id in [main_character, *visible_characters]:
        if char_id and char_id not in ordered_characters:
            ordered_characters.append(char_id)

    if not ordered_characters:
        return ref_images

    # 主角色优先同时给全身服装锚点和身份图
    main_variants = find_character_ref_variants(refs_dir, ordered_characters[0])
    by_type = {item.get("reference_type"): item.get("path") for item in main_variants}
    for ref_type in ["full_body_outfit", "identity_portrait"]:
        ref_path = by_type.get(ref_type)
        if isinstance(ref_path, Path):
            _append_unique_ref(ref_images, seen_paths, ref_path)
            if len(ref_images) >= max_reference_images:
                return ref_images

    # 其他可见角色优先给身份图，确保多人不要往主角一张脸收敛
    for char_id in ordered_characters[1:]:
        variants = find_character_ref_variants(refs_dir, char_id)
        preferred = None
        fallback = None
        for item in variants:
            ref_path = item.get("path")
            ref_type = item.get("reference_type")
            if not isinstance(ref_path, Path):
                continue
            if ref_type == "identity_portrait" and preferred is None:
                preferred = ref_path
            elif fallback is None:
                fallback = ref_path
        selected = preferred or fallback
        if isinstance(selected, Path):
            _append_unique_ref(ref_images, seen_paths, selected)
            if len(ref_images) >= max_reference_images:
                return ref_images

    # 如果还有空间，再补一个主角色身份图或其他全身锚点
    for char_id in ordered_characters[1:]:
        variants = find_character_ref_variants(refs_dir, char_id)
        for item in variants:
            ref_path = item.get("path")
            ref_type = item.get("reference_type")
            if ref_type != "full_body_outfit" or not isinstance(ref_path, Path):
                continue
            _append_unique_ref(ref_images, seen_paths, ref_path)
            if len(ref_images) >= max_reference_images:
                return ref_images

    return ref_images


async def generate_scene_videos(
    prompts_path: Path,
    refs_dir: Path,
    output_dir: Path,
    config_path: Path | None = None,
    api_key: str | None = None,
    parallel: int = 1,
) -> dict:
    """为所有场景生成视频"""
    config = load_config(config_path) if config_path else load_config()

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

    refs_valid, refs_errors = validate_refs_manifest_runtime(refs_dir, generation_contract)
    if not refs_valid:
        for error in refs_errors:
            logger.error(error)
        return {"success": False, "error": "角色参考图和当前 generation_contract 不一致"}

    runtime_config = copy.deepcopy(config)
    video_generation = prompts_data.get("video_generation", {})
    target_width, target_height = parse_resolution(video_generation.get("target_resolution", ""))

    if video_generation:
        runtime_video_cfg = runtime_config.setdefault("models", {}).setdefault("video", {})
        if video_generation.get("provider_ratio"):
            runtime_video_cfg["ratio"] = video_generation["provider_ratio"]
        if video_generation.get("provider_resolution"):
            runtime_video_cfg["resolution"] = video_generation["provider_resolution"]

    scenes = prompts_data.get("scenes", [])
    if not scenes:
        logger.error("未找到场景列表（scenes）")
        return {"success": False, "error": "未找到场景列表"}

    output_dir.mkdir(parents=True, exist_ok=True)
    existing_videos_manifest = load_existing_videos_manifest(output_dir)
    video_cfg = get_model_config("video", runtime_config)
    min_dur = video_cfg.get("min_duration", 4)
    max_dur = video_cfg.get("max_duration", 15)
    max_reference_images = int(video_cfg.get("max_reference_images", 4) or 4)

    results = []
    manifest = {
        "generation_contract": generation_contract,
        "scenes": {},
    }
    sem = asyncio.Semaphore(parallel)

    async def generate_one(scene: dict) -> dict:
        scene_id = scene.get("scene_id", 0)
        prompt = scene.get("prompt", "")
        final_prompt = build_scene_prompt(generation_contract, style_consistency, prompt)
        raw_duration = scene.get("duration", 10)
        main_character = scene.get("main_character", "")

        # 时长限制
        duration = max(min_dur, min(max_dur, int(raw_duration)))

        output_path = output_dir / f"scene_{scene_id:03d}.mp4"

        # 断点续传
        if output_path.exists() and output_path.stat().st_size > 1000:
            expected_scene_mode = generation_contract.get("scene_generation_mode", "")
            if can_skip_existing_video(existing_videos_manifest, expected_scene_mode):
                logger.info(f"跳过已存在且形态一致: scene_{scene_id:03d}")
                normalize_video_size(output_path, target_width, target_height)
                return {"scene_id": scene_id, "status": "skipped", "path": str(output_path)}
            logger.info(f"发现旧视频但形态契约不明或不一致，将重新生成: scene_{scene_id:03d}")

        visible_characters = scene.get("visible_characters", [])

        # 收集参考图：主角色 + 可见角色，防止多人同脸
        ref_images = build_scene_reference_images(refs_dir, scene, max_reference_images)
        if main_character and not ref_images:
            logger.warning(
                f"场景{scene_id}: 未找到角色参考图 '{main_character}'。"
                f"请确认 main_character 值与 characters[].id 以及参考图文件名一致。"
                f"参考图目录: {refs_dir}"
            )

        # 额外参考图
        for extra in scene.get("extra_refs", []):
            p = Path(extra)
            if p.exists():
                ref_images.append(p)
        logger.info(f"场景{scene_id}: 生成视频 ({duration}s, {len(ref_images)} 张参考图)")
        logger.info(f"  最终提示词: {final_prompt[:120]}...")

        async with sem:
            success = await generate_seedance_video(
                prompt=final_prompt,
                reference_images=ref_images,
                output_path=output_path,
                duration=duration,
                config=runtime_config,
                api_key_override=api_key,
            )

        status = "success" if success else "failed"
        if success:
            success = normalize_video_size(output_path, target_width, target_height)
            status = "success" if success else "failed"
        manifest["scenes"][str(scene_id)] = {
            "path": str(output_path),
            "duration": duration,
            "main_character": main_character,
            "visible_characters": visible_characters,
            "used_reference_images": [str(path) for path in ref_images],
            "final_prompt": final_prompt,
            "status": status,
        }
        return {"scene_id": scene_id, "status": status, "path": str(output_path)}

    # 并行生成
    tasks = [generate_one(scene) for scene in scenes]
    results = await asyncio.gather(*tasks)

    # 保存 manifest
    manifest_path = output_dir / "videos_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info(f"视频 manifest 已保存: {manifest_path}")

    success_count = sum(1 for r in results if r["status"] in ("success", "skipped"))
    logger.info(f"完成: {success_count}/{len(results)} 场景视频生成成功")

    return {
        "success": success_count > 0,
        "results": results,
        "manifest_path": str(manifest_path),
    }


def main():
    parser = argparse.ArgumentParser(description="场景视频生成器（步骤9）")
    parser.add_argument("--prompts_json", type=str, required=True, help="scene_prompts.json 路径")
    parser.add_argument("--refs_dir", type=str, required=True, help="角色参考图目录")
    parser.add_argument("--output_dir", type=str, default="output/videos", help="输出目录")
    parser.add_argument("--config", type=str, default=None, help="api_config.yaml 路径")
    parser.add_argument("--api_key", type=str, default=None, help="API 密钥")
    parser.add_argument("--parallel", type=int, default=1, help="并行数")

    args = parser.parse_args()

    result = asyncio.run(generate_scene_videos(
        prompts_path=Path(args.prompts_json),
        refs_dir=Path(args.refs_dir),
        output_dir=Path(args.output_dir),
        config_path=Path(args.config) if args.config else None,
        api_key=args.api_key,
        parallel=args.parallel,
    ))

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
