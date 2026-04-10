#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场景视频生成器（步骤9）
读取 scene_prompts.json 和角色参考图，调用 Seedance 2.0 API 生成场景视频
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from api_client import load_config, generate_seedance_video, get_model_config
from schema_validator import validate_scene_prompts, print_validation_result

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_refs_manifest(refs_dir: Path) -> dict:
    """读取角色参考图 manifest"""
    manifest_path = refs_dir / "refs_manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def find_character_ref(refs_dir: Path, character_id: str) -> Path | None:
    """查找角色参考图路径"""
    # 先查 manifest
    manifest = load_refs_manifest(refs_dir)
    char_info = manifest.get("characters", {}).get(character_id, {})
    if char_info.get("path"):
        p = Path(char_info["path"])
        if p.exists():
            return p

    # 兜底：按文件名查找
    for ext in ["jpg", "jpeg", "png"]:
        p = refs_dir / f"{character_id}.{ext}"
        if p.exists():
            return p
    return None


async def generate_scene_videos(
    prompts_path: Path,
    refs_dir: Path,
    output_dir: Path,
    config_path: Path | None = None,
    api_key: str | None = None,
    parallel: int = 1,
) -> dict:
    """为所有场景生成视频"""
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

    scenes = prompts_data.get("scenes", [])
    if not scenes:
        logger.error("未找到场景列表（scenes）")
        return {"success": False, "error": "未找到场景列表"}

    output_dir.mkdir(parents=True, exist_ok=True)
    video_cfg = get_model_config("video", config) if config else {}
    min_dur = video_cfg.get("min_duration", 4)
    max_dur = video_cfg.get("max_duration", 15)

    results = []
    manifest = {"scenes": {}}
    sem = asyncio.Semaphore(parallel)

    async def generate_one(scene: dict) -> dict:
        scene_id = scene.get("scene_id", 0)
        prompt = scene.get("prompt", "")
        raw_duration = scene.get("duration", 10)
        main_character = scene.get("main_character", "")

        # 时长限制
        duration = max(min_dur, min(max_dur, int(raw_duration)))

        output_path = output_dir / f"scene_{scene_id:03d}.mp4"

        # 断点续传
        if output_path.exists() and output_path.stat().st_size > 1000:
            logger.info(f"跳过已存在: scene_{scene_id:03d}")
            return {"scene_id": scene_id, "status": "skipped", "path": str(output_path)}

        # 收集参考图
        ref_images: list[Path] = []
        if main_character:
            ref_path = find_character_ref(refs_dir, main_character)
            if ref_path:
                ref_images.append(ref_path)
            else:
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
        logger.info(f"  提示词: {prompt[:80]}...")

        async with sem:
            success = await generate_seedance_video(
                prompt=prompt,
                reference_images=ref_images,
                output_path=output_path,
                duration=duration,
                config=config,
                api_key_override=api_key,
            )

        status = "success" if success else "failed"
        manifest["scenes"][str(scene_id)] = {
            "path": str(output_path),
            "duration": duration,
            "main_character": main_character,
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
