#!/usr/bin/env python3
"""
视频风格化渲染脚本

功能：
1. 基于参考视频分析结果应用风格特征
2. 调用外部视频API或本地处理生成风格化视频
3. 支持多种风格复刻方案

使用方法：
    python video_renderer.py --reference_analysis <参考分析报告JSON路径> \
                             --source_video <素材视频路径> \
                             --style_prompts <风格提示词> \
                             --content_prompts <内容提示词> \
                             --output_path <输出视频路径>

参数说明：
    reference_analysis: 参考视频的分析报告（JSON格式）
    source_video: 待处理的素材视频路径
    style_prompts: 风格描述提示词（字符串或JSON文件路径）
    content_prompts: 内容描述提示词（字符串或JSON文件路径）
    output_path: 输出视频路径
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List
import cv2
import numpy as np
from moviepy import VideoFileClip


class VideoRenderer:
    """视频风格化渲染器"""

    def __init__(self, reference_analysis: Dict[str, Any], source_video: str):
        """
        初始化渲染器

        参数:
            reference_analysis: 参考视频分析报告
            source_video: 素材视频路径
        """
        self.reference_analysis = reference_analysis
        self.source_video = source_video
        self.source_clip = None
        self.output_clip = None

    def load_source_video(self) -> bool:
        """
        加载素材视频

        返回:
            成功返回True，失败返回False
        """
        if not os.path.exists(self.source_video):
            print(f"错误：素材视频不存在: {self.source_video}")
            return False

        try:
            self.source_clip = VideoFileClip(self.source_video)
            return True
        except Exception as e:
            print(f"错误：无法加载视频文件: {str(e)}")
            return False

    def parse_prompts(self, style_prompts: str, content_prompts: str) -> Dict[str, Any]:
        """
        解析提示词

        参数:
            style_prompts: 风格提示词（字符串或JSON文件路径）
            content_prompts: 内容提示词（字符串或JSON文件路径）

        返回:
            解析后的提示词字典
        """
        # 解析风格提示词
        if os.path.exists(style_prompts):
            with open(style_prompts, 'r', encoding='utf-8') as f:
                style_data = json.load(f)
        else:
            # 将字符串提示词转换为结构化格式
            style_data = {
                "description": style_prompts,
                "keywords": self._extract_keywords(style_prompts),
                "color_adjustment": True,
                "motion_adjustment": True
            }

        # 解析内容提示词
        if os.path.exists(content_prompts):
            with open(content_prompts, 'r', encoding='utf-8') as f:
                content_data = json.load(f)
        else:
            content_data = {
                "description": content_prompts,
                "keywords": self._extract_keywords(content_prompts)
            }

        return {
            "style": style_data,
            "content": content_data
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """
        从文本中提取关键词

        参数:
            text: 输入文本

        返回:
            关键词列表
        """
        # 简单的关键词提取逻辑
        common_keywords = [
            "warm", "cool", "bright", "dark", "cinematic", "documentary",
            "vlog", "commercial", "slow", "fast", "dynamic", "static",
            "high contrast", "low contrast", "vibrant", "muted", "natural",
            "dramatic", "romantic", "mysterious", "energetic"
        ]

        text_lower = text.lower()
        keywords = []

        for keyword in common_keywords:
            if keyword in text_lower:
                keywords.append(keyword)

        return keywords

    def apply_color_adjustment(self, prompts: Dict[str, Any]) -> VideoFileClip:
        """
        应用色彩调整

        参数:
            prompts: 解析后的提示词

        返回:
            调整后的视频片段
        """
        clip = self.source_clip

        # 从参考分析中获取色彩特征
        ref_color = self.reference_analysis.get("visual_style", {}).get("color_distribution", {})
        ref_tone = ref_color.get("color_tone", "")

        # 基于风格提示词调整色彩
        style_keywords = prompts.get("style", {}).get("keywords", [])

        # 应用色调调整
        if "warm" in style_keywords or "warm_red_orange" in ref_tone:
            # 暖色调调整
            clip = clip.fx(lambda v: self._apply_warm_tone(v, intensity=0.2))

        elif "cool" in style_keywords or "blue" in ref_tone or "cyan" in ref_tone:
            # 冷色调调整
            clip = clip.fx(lambda v: self._apply_cool_tone(v, intensity=0.2))

        # 应用饱和度调整
        if "vibrant" in style_keywords:
            clip = clip.fx(lambda v: self._adjust_saturation(v, factor=1.3))

        elif "muted" in style_keywords or "low_saturation" in ref_tone:
            clip = clip.fx(lambda v: self._adjust_saturation(v, factor=0.7))

        # 应用亮度调整
        if "bright" in style_keywords:
            clip = clip.fx(lambda v: self._adjust_brightness(v, factor=1.2))

        elif "dark" in style_keywords:
            clip = clip.fx(lambda v: self._adjust_brightness(v, factor=0.8))

        # 应用对比度调整
        if "high contrast" in style_keywords:
            clip = clip.fx(lambda v: self._adjust_contrast(v, factor=1.3))

        return clip

    def _apply_warm_tone(self, frame: np.ndarray, intensity: float = 0.2) -> np.ndarray:
        """
        应用暖色调

        参数:
            frame: 输入帧
            intensity: 强度

        返回:
            调整后的帧
        """
        frame = frame.astype(float)
        frame[:, :, 2] = np.clip(frame[:, :, 2] * (1 + intensity), 0, 255)  # 增加红色
        frame[:, :, 1] = np.clip(frame[:, :, 1] * (1 + intensity * 0.5), 0, 255)  # 增加绿色
        return frame.astype(np.uint8)

    def _apply_cool_tone(self, frame: np.ndarray, intensity: float = 0.2) -> np.ndarray:
        """
        应用冷色调

        参数:
            frame: 输入帧
            intensity: 强度

        返回:
            调整后的帧
        """
        frame = frame.astype(float)
        frame[:, :, 0] = np.clip(frame[:, :, 0] * (1 + intensity), 0, 255)  # 增加蓝色
        return frame.astype(np.uint8)

    def _adjust_saturation(self, frame: np.ndarray, factor: float = 1.0) -> np.ndarray:
        """
        调整饱和度

        参数:
            frame: 输入帧
            factor: 饱和度因子

        返回:
            调整后的帧
        """
        frame = frame.astype(float)
        gray = np.mean(frame, axis=2)
        frame = gray[:, :, np.newaxis] * (1 - factor) + frame * factor
        return np.clip(frame, 0, 255).astype(np.uint8)

    def _adjust_brightness(self, frame: np.ndarray, factor: float = 1.0) -> np.ndarray:
        """
        调整亮度

        参数:
            frame: 输入帧
            factor: 亮度因子

        返回:
            调整后的帧
        """
        frame = frame.astype(float)
        frame = frame * factor
        return np.clip(frame, 0, 255).astype(np.uint8)

    def _adjust_contrast(self, frame: np.ndarray, factor: float = 1.0) -> np.ndarray:
        """
        调整对比度

        参数:
            frame: 输入帧
            factor: 对比度因子

        返回:
            调整后的帧
        """
        frame = frame.astype(float)
        mean = np.mean(frame)
        frame = (frame - mean) * factor + mean
        return np.clip(frame, 0, 255).astype(np.uint8)

    def apply_motion_effects(self, prompts: Dict[str, Any]) -> VideoFileClip:
        """
        应用运动效果

        参数:
            prompts: 解析后的提示词

        返回:
            调整后的视频片段
        """
        clip = self.source_clip

        # 从参考分析中获取运动特征
        ref_motion = self.reference_analysis.get("visual_style", {}).get("motion_characteristics", {})
        ref_motion_type = ref_motion.get("motion_type", "")

        # 基于风格提示词调整速度
        style_keywords = prompts.get("style", {}).get("keywords", [])

        if "slow" in style_keywords or "slow_movement" in ref_motion_type:
            # 慢动作效果
            clip = clip.fx(lambda v: v.speedx(0.7))

        elif "fast" in style_keywords or "fast_movement" in ref_motion_type:
            # 快速效果
            clip = clip.fx(lambda v: v.speedx(1.3))

        return clip

    def render(self, style_prompts: str, content_prompts: str, output_path: str) -> bool:
        """
        执行渲染

        参数:
            style_prompts: 风格提示词
            content_prompts: 内容提示词
            output_path: 输出路径

        返回:
            成功返回True，失败返回False
        """
        if not self.load_source_video():
            return False

        # 解析提示词
        prompts = self.parse_prompts(style_prompts, content_prompts)

        try:
            # 应用色彩调整
            self.output_clip = self.apply_color_adjustment(prompts)

            # 应用运动效果
            self.output_clip = self.apply_motion_effects(prompts)

            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # 写入输出文件
            self.output_clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=self.source_clip.fps,
                threads=4
            )

            print(f"风格化视频已生成: {output_path}")
            return True

        except Exception as e:
            print(f"渲染失败: {str(e)}")
            return False

        finally:
            if self.source_clip:
                self.source_clip.close()
            if self.output_clip:
                self.output_clip.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='视频风格化渲染')
    parser.add_argument('--reference_analysis', type=str, required=True, help='参考分析报告JSON路径')
    parser.add_argument('--source_video', type=str, required=True, help='素材视频路径')
    parser.add_argument('--style_prompts', type=str, required=True, help='风格提示词')
    parser.add_argument('--content_prompts', type=str, required=True, help='内容提示词')
    parser.add_argument('--output_path', type=str, required=True, help='输出视频路径')

    args = parser.parse_args()

    # 读取参考分析报告
    if not os.path.exists(args.reference_analysis):
        print(f"错误：参考分析报告不存在: {args.reference_analysis}")
        sys.exit(1)

    with open(args.reference_analysis, 'r', encoding='utf-8') as f:
        reference_analysis = json.load(f)

    # 创建渲染器
    renderer = VideoRenderer(reference_analysis, args.source_video)

    # 执行渲染
    success = renderer.render(
        style_prompts=args.style_prompts,
        content_prompts=args.content_prompts,
        output_path=args.output_path
    )

    if not success:
        sys.exit(1)

    print("渲染完成！")


if __name__ == "__main__":
    main()
