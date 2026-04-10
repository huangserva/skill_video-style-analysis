#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色参考图生成器（步骤8）
读取 scene_prompts.json 中的角色参考图提示词，调用 Seedream API 生成插画风格半身像
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
from schema_validator import validate_scene_prompts, print_validation_result

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


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
                    f"插画风格，半身像，干净背景，"
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
    results = []
    manifest = {"characters": {}}

    for item in character_prompts:
        char_id = item.get("character_id", item.get("id", "unknown"))
        prompt = item.get("prompt", "")

        if not prompt:
            logger.warning(f"跳过空提示词: {char_id}")
            continue

        output_path = output_dir / f"{char_id}.jpg"
        if output_path.exists():
            logger.info(f"跳过已存在: {output_path}")
            manifest["characters"][char_id] = {
                "path": str(output_path),
                "prompt": prompt,
                "status": "skipped",
            }
            results.append({"character_id": char_id, "status": "skipped", "path": str(output_path)})
            continue

        logger.info(f"生成角色参考图: {char_id}")
        logger.info(f"  提示词: {prompt[:80]}...")

        success = await generate_seedream_image(
            prompt=prompt,
            output_path=output_path,
            config=config,
            api_key_override=api_key,
        )

        status = "success" if success else "failed"
        manifest["characters"][char_id] = {
            "path": str(output_path),
            "prompt": prompt,
            "status": status,
        }
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
