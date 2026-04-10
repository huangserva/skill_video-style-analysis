#!/usr/bin/env python3
"""
视频分析与风格提取脚本

功能：
1. 提取视频技术规格（分辨率、帧率、时长、编码格式）
2. 分析视觉风格（色彩分布、调色特征、光影效果）
3. 生成结构化分析报告（JSON格式）

使用方法：
    python video_analyzer.py --video_path <视频文件路径> --output_path <输出JSON路径>

输出格式：
    详见 ../assets/report_template.json
"""

import os
import sys
import json
import argparse
from typing import Dict, Any
import cv2
import numpy as np


class VideoAnalyzer:
    """视频分析器"""

    def __init__(self, video_path: str):
        """
        初始化视频分析器

        参数:
            video_path: 视频文件路径
        """
        self.video_path = video_path
        self.cap = None
        self.fps = 0
        self.frame_count = 0
        self.width = 0
        self.height = 0
        self.duration = 0

    def open_video(self) -> bool:
        """
        打开视频文件

        返回:
            成功返回True，失败返回False
        """
        if not os.path.exists(self.video_path):
            print(f"错误：视频文件不存在: {self.video_path}")
            return False

        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            print(f"错误：无法打开视频文件: {self.video_path}")
            return False

        # 获取视频基本信息
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if self.fps > 0:
            self.duration = self.frame_count / self.fps

        return True

    def extract_tech_specs(self) -> Dict[str, Any]:
        """
        提取技术规格

        返回:
            技术规格字典
        """
        return {
            "resolution": f"{self.width}x{self.height}",
            "frame_rate": round(self.fps, 2),
            "duration": round(self.duration, 2),
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": f"{self.width/self.height:.2f}",
            "video_format": os.path.splitext(self.video_path)[1].replace(".", "").upper()
        }

    def analyze_color_distribution(self, num_frames: int = 30) -> Dict[str, Any]:
        """
        分析色彩分布

        参数:
            num_frames: 采样的帧数

        返回:
            色彩分析结果
        """
        # 采样帧
        sample_indices = np.linspace(0, self.frame_count - 1, num_frames, dtype=int)
        frames = []

        for idx in sample_indices:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = self.cap.read()
            if ret:
                frames.append(frame)

        if not frames:
            return {"error": "无法读取视频帧"}

        # 转换为BGR到RGB
        frames_rgb = [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames]
        frames_array = np.array(frames_rgb)

        # 分析RGB通道分布
        mean_rgb = frames_array.mean(axis=(0, 1, 2))

        # 计算HSV特征
        frames_hsv = [cv2.cvtColor(f, cv2.COLOR_BGR2HSV) for f in frames]
        frames_hsv_array = np.array(frames_hsv)

        mean_hsv = frames_hsv_array.mean(axis=(0, 1, 2))

        # 计算亮度和对比度
        gray_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
        gray_array = np.array(gray_frames)

        mean_brightness = gray_array.mean()
        std_brightness = gray_array.std()

        return {
            "dominant_colors": {
                "red": round(mean_rgb[0], 2),
                "green": round(mean_rgb[1], 2),
                "blue": round(mean_rgb[2], 2)
            },
            "color_features": {
                "mean_hue": round(mean_hsv[0], 2),
                "mean_saturation": round(mean_hsv[1], 2),
                "mean_value": round(mean_hsv[2], 2)
            },
            "brightness": round(mean_brightness, 2),
            "contrast": round(std_brightness, 2),
            "color_tone": self._identify_color_tone(mean_rgb, mean_hsv)
        }

    def _identify_color_tone(self, mean_rgb: np.ndarray, mean_hsv: np.ndarray) -> str:
        """
        识别色调类型

        参数:
            mean_rgb: 平均RGB值
            mean_hsv: 平均HSV值

        返回:
            色调描述
        """
        hue = mean_hsv[0]
        saturation = mean_hsv[1]
        value = mean_hsv[2]

        if saturation < 50:
            return "low_saturation_gray"
        elif value < 50:
            return "dark"
        elif hue < 10 or hue > 170:
            return "warm_red_orange"
        elif hue < 25:
            return "warm_yellow"
        elif hue < 85:
            return "green"
        elif hue < 125:
            return "cyan"
        elif hue < 155:
            return "blue"
        else:
            return "purple"

    def analyze_motion_characteristics(self, num_frames: int = 30) -> Dict[str, Any]:
        """
        分析运动特征

        参数:
            num_frames: 采样的帧数

        返回:
            运动特征分析结果
        """
        if self.frame_count < 2:
            return {"error": "视频帧数不足，无法分析运动特征"}

        # 采样连续帧对
        sample_indices = np.linspace(0, self.frame_count - 2, min(num_frames, self.frame_count - 1), dtype=int)
        motion_scores = []

        for idx in sample_indices:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret1, frame1 = self.cap.read()
            ret2, frame2 = self.cap.read()

            if ret1 and ret2:
                # 计算帧间差分
                gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

                # 使用光流法计算运动
                flow = cv2.calcOpticalFlowFarneback(gray1, gray2, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                mag = np.sqrt(flow[:, :, 0]**2 + flow[:, :, 1]**2)
                motion_score = mag.mean()
                motion_scores.append(motion_score)

        if not motion_scores:
            return {"error": "无法计算运动特征"}

        avg_motion = np.mean(motion_scores)
        motion_variance = np.var(motion_scores)

        return {
            "average_motion": round(avg_motion, 4),
            "motion_stability": round(motion_variance, 4),
            "motion_type": self._classify_motion(avg_motion, motion_variance)
        }

    def _classify_motion(self, avg_motion: float, motion_variance: float) -> str:
        """
        分类运动类型

        参数:
            avg_motion: 平均运动量
            motion_variance: 运动方差

        返回:
            运动类型描述
        """
        if avg_motion < 0.5:
            return "static"
        elif avg_motion < 2.0:
            return "slow_movement"
        elif avg_motion < 5.0:
            return "normal_movement"
        elif motion_variance > 10:
            return "dynamic_fast"
        else:
            return "fast_movement"

    def generate_report(self) -> Dict[str, Any]:
        """
        生成完整的分析报告

        返回:
            分析报告字典
        """
        if not self.open_video():
            return {"error": "无法打开视频文件"}

        try:
            # 提取技术规格
            tech_specs = self.extract_tech_specs()

            # 分析色彩分布
            color_analysis = self.analyze_color_distribution()

            # 分析运动特征
            motion_analysis = self.analyze_motion_characteristics()

            # 组合报告
            report = {
                "video_path": self.video_path,
                "technical_specs": tech_specs,
                "visual_style": {
                    "color_distribution": color_analysis,
                    "motion_characteristics": motion_analysis
                },
                "metadata": {
                    "analysis_timestamp": __import__('datetime').datetime.now().isoformat(),
                    "analyzer_version": "1.0.0"
                }
            }

            return report

        finally:
            if self.cap:
                self.cap.release()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='视频分析与风格提取')
    parser.add_argument('--video_path', type=str, required=True, help='视频文件路径')
    parser.add_argument('--output_path', type=str, required=True, help='输出JSON文件路径')

    args = parser.parse_args()

    # 创建分析器
    analyzer = VideoAnalyzer(args.video_path)

    # 生成报告
    # 将 numpy 类型转换为 Python 原生类型
    def convert_to_json_serializable(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: convert_to_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_json_serializable(item) for item in obj]
        else:
            return obj

    report = convert_to_json_serializable(analyzer.generate_report())

    if "error" in report:
        print(f"分析失败: {report['error']}")
        sys.exit(1)

    # 保存报告
    output_dir = os.path.dirname(args.output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(args.output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"分析报告已生成: {args.output_path}")
    print(f"视频时长: {report['technical_specs']['duration']} 秒")
    print(f"分辨率: {report['technical_specs']['resolution']}")
    print(f"色调类型: {report['visual_style']['color_distribution'].get('color_tone', 'unknown')}")
    print(f"运动类型: {report['visual_style']['motion_characteristics'].get('motion_type', 'unknown')}")


if __name__ == "__main__":
    main()
