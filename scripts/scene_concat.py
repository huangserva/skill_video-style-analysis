#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场景视频拼接（步骤11a）
将多个场景视频按顺序拼接为一个完整视频
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def concat_videos(
    video_dir: Path,
    output_path: Path,
    order_json: Path | None = None,
) -> dict:
    """按顺序拼接场景视频"""
    # 收集场景视频
    if order_json and order_json.exists():
        with open(order_json, "r", encoding="utf-8") as f:
            prompts = json.load(f)
        scenes = prompts.get("scenes", [])
        video_files = []
        for scene in scenes:
            scene_id = scene.get("scene_id", 0)
            p = video_dir / f"scene_{scene_id:03d}.mp4"
            if p.exists():
                video_files.append(p)
            else:
                logger.warning(f"场景视频不存在: {p}")
    else:
        # 按文件名排序
        video_files = sorted(video_dir.glob("scene_*.mp4"))

    if not video_files:
        logger.error("未找到任何场景视频")
        return {"success": False, "error": "未找到场景视频"}

    logger.info(f"准备拼接 {len(video_files)} 个场景视频")

    # 生成 concat list
    concat_list = output_path.parent / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for vf in video_files:
            f.write(f"file '{vf.resolve()}'\n")

    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ffmpeg 拼接
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"ffmpeg 拼接失败: {result.stderr[:300]}")
            return {"success": False, "error": result.stderr[:300]}
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg 拼接超时")
        return {"success": False, "error": "超时"}
    except FileNotFoundError:
        logger.error("ffmpeg 未安装")
        return {"success": False, "error": "ffmpeg 未安装"}

    # 清理临时文件
    concat_list.unlink(missing_ok=True)

    size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info(f"拼接完成: {output_path} ({size_mb:.1f} MB)")

    return {
        "success": True,
        "output_path": str(output_path),
        "scene_count": len(video_files),
        "size_mb": round(size_mb, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="场景视频拼接（步骤11a）")
    parser.add_argument("--video_dir", type=str, required=True, help="场景视频目录")
    parser.add_argument("--output_path", type=str, default="output/videos/merged_video.mp4", help="输出文件路径")
    parser.add_argument("--order_json", type=str, default=None, help="scene_prompts.json（用于确定顺序）")

    args = parser.parse_args()

    result = concat_videos(
        video_dir=Path(args.video_dir),
        output_path=Path(args.output_path),
        order_json=Path(args.order_json) if args.order_json else None,
    )

    if result.get("success"):
        print(f"\n✓ 拼接完成: {result['output_path']} ({result.get('scene_count')} 个场景)")
        return 0
    else:
        print(f"\n✗ 拼接失败: {result.get('error')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
