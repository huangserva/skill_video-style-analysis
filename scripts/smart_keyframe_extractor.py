#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能关键帧提取器

功能：
1. 场景变化检测 - 使用帧差分析检测场景切换
2. 动作密度分析 - 分析帧间差异，识别动作密集区域
3. 智能帧提取 - 动作密集区域多提取，静态区域少提取
"""

import os
import sys
import json
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class KeyframeInfo:
    """关键帧信息"""
    frame_index: int
    timestamp: float
    frame_path: str
    frame_type: str  # 'scene_start', 'scene_end', 'action_key', 'regular'
    scene_id: int
    action_density: float  # 0.0 - 1.0


@dataclass
class SceneInfo:
    """场景信息"""
    scene_id: int
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    avg_action_density: float


class SmartKeyframeExtractor:
    """智能关键帧提取器"""
    
    def __init__(
        self,
        video_path: str,
        output_dir: str,
        min_fps: float = 2.0,  # v2改进：从1.0提高到2.0，确保不遗漏重要镜头
        max_fps: float = 5.0,
        scene_threshold: float = 0.3,
        action_threshold: float = 0.15,
        uniform_fallback: bool = True  # v2新增：均匀提取兜底模式
    ):
        """
        初始化
        
        Args:
            video_path: 视频文件路径
            output_dir: 输出目录
            min_fps: 最小提取帧率（静态区域）
            max_fps: 最大提取帧率（动作密集区域）
            scene_threshold: 场景切换阈值（0-1）
            action_threshold: 动作检测阈值（0-1）
        """
        self.video_path = video_path
        self.output_dir = Path(output_dir)
        self.min_fps = min_fps
        self.max_fps = max_fps
        self.scene_threshold = scene_threshold
        self.action_threshold = action_threshold
        self.uniform_fallback = uniform_fallback  # v2新增
        
        # 打开视频
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise ValueError(f"无法打开视频: {video_path}")
        
        # 获取视频信息
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.duration = self.total_frames / self.fps
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"视频信息: {self.total_frames}帧, {self.fps}fps, {self.duration:.2f}秒")
    
    def compute_frame_difference(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """
        计算两帧之间的差异度
        
        Args:
            frame1: 第一帧
            frame2: 第二帧
            
        Returns:
            差异度 (0-1)
        """
        # 转灰度
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        
        # 计算差异
        diff = cv2.absdiff(gray1, gray2)
        
        # 计算差异比例
        diff_ratio = np.sum(diff > 30) / diff.size
        
        return diff_ratio
    
    def detect_scenes(self) -> List[SceneInfo]:
        """
        检测场景切换
        
        Returns:
            场景列表
        """
        print("检测场景切换...")
        
        scenes = []
        current_scene_start = 0
        current_scene_id = 0
        
        # 重置视频
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        ret, prev_frame = self.cap.read()
        if not ret:
            return scenes
        
        frame_idx = 1
        scene_changes = []  # 记录场景变化帧
        
        while True:
            ret, curr_frame = self.cap.read()
            if not ret:
                break
            
            # 计算差异
            diff = self.compute_frame_difference(prev_frame, curr_frame)
            
            # 检测场景切换
            if diff > self.scene_threshold:
                scene_changes.append(frame_idx)
                print(f"  检测到场景切换: 第{frame_idx}帧 (差异度: {diff:.3f})")
            
            prev_frame = curr_frame
            frame_idx += 1
        
        # 构建场景列表
        if not scene_changes:
            # 没有场景切换，整个视频是一个场景
            scenes.append(SceneInfo(
                scene_id=0,
                start_frame=0,
                end_frame=self.total_frames - 1,
                start_time=0.0,
                end_time=self.duration,
                avg_action_density=0.0
            ))
        else:
            # 有场景切换
            prev_change = 0
            for i, change in enumerate(scene_changes):
                scenes.append(SceneInfo(
                    scene_id=i,
                    start_frame=prev_change,
                    end_frame=change - 1,
                    start_time=prev_change / self.fps,
                    end_time=(change - 1) / self.fps,
                    avg_action_density=0.0
                ))
                prev_change = change
            
            # 最后一个场景
            scenes.append(SceneInfo(
                scene_id=len(scene_changes),
                start_frame=prev_change,
                end_frame=self.total_frames - 1,
                start_time=prev_change / self.fps,
                end_time=self.duration,
                avg_action_density=0.0
            ))
        
        print(f"检测到 {len(scenes)} 个场景")
        return scenes
    
    def analyze_action_density(self, scenes: List[SceneInfo]) -> List[SceneInfo]:
        """
        分析每个场景的动作密度
        
        Args:
            scenes: 场景列表
            
        Returns:
            更新后的场景列表（包含动作密度）
        """
        print("分析动作密度...")
        
        for scene in scenes:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, scene.start_frame)
            
            ret, prev_frame = self.cap.read()
            if not ret:
                continue
            
            total_diff = 0.0
            frame_count = 0
            
            for frame_idx in range(scene.start_frame + 1, scene.end_frame + 1):
                ret, curr_frame = self.cap.read()
                if not ret:
                    break
                
                diff = self.compute_frame_difference(prev_frame, curr_frame)
                total_diff += diff
                frame_count += 1
                prev_frame = curr_frame
            
            scene.avg_action_density = total_diff / max(frame_count, 1)
            print(f"  场景{scene.scene_id}: 动作密度 {scene.avg_action_density:.3f}")
        
        return scenes
    
    def extract_keyframes(self, scenes: List[SceneInfo]) -> List[KeyframeInfo]:
        """
        提取关键帧
        
        Args:
            scenes: 场景列表
            
        Returns:
            关键帧列表
        """
        print("提取关键帧...")
        
        keyframes = []
        frame_counter = 0
        
        for scene in scenes:
            # 根据动作密度决定提取帧率
            if scene.avg_action_density > 0.2:
                extract_fps = self.max_fps
            elif scene.avg_action_density > 0.1:
                extract_fps = (self.min_fps + self.max_fps) / 2
            else:
                extract_fps = self.min_fps
            
            frame_interval = int(self.fps / extract_fps)
            
            print(f"  场景{scene.scene_id}: 提取帧率 {extract_fps}fps (间隔{frame_interval}帧)")
            
            # 提取场景开始帧（必须）
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, scene.start_frame)
            ret, frame = self.cap.read()
            if ret:
                frame_path = self.output_dir / f"frame_{frame_counter:04d}.jpg"
                cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                keyframes.append(KeyframeInfo(
                    frame_index=scene.start_frame,
                    timestamp=scene.start_frame / self.fps,
                    frame_path=str(frame_path),
                    frame_type='scene_start',
                    scene_id=scene.scene_id,
                    action_density=scene.avg_action_density
                ))
                frame_counter += 1
            
            # 提取中间帧
            for frame_idx in range(scene.start_frame + frame_interval, scene.end_frame, frame_interval):
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = self.cap.read()
                if ret:
                    frame_path = self.output_dir / f"frame_{frame_counter:04d}.jpg"
                    cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    keyframes.append(KeyframeInfo(
                        frame_index=frame_idx,
                        timestamp=frame_idx / self.fps,
                        frame_path=str(frame_path),
                        frame_type='regular',
                        scene_id=scene.scene_id,
                        action_density=scene.avg_action_density
                    ))
                    frame_counter += 1
            
            # 提取场景结束帧（必须，如果和开始帧不同）
            if scene.end_frame > scene.start_frame:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, scene.end_frame)
                ret, frame = self.cap.read()
                if ret:
                    frame_path = self.output_dir / f"frame_{frame_counter:04d}.jpg"
                    cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    keyframes.append(KeyframeInfo(
                        frame_index=scene.end_frame,
                        timestamp=scene.end_frame / self.fps,
                        frame_path=str(frame_path),
                        frame_type='scene_end',
                        scene_id=scene.scene_id,
                        action_density=scene.avg_action_density
                    ))
                    frame_counter += 1
        
        print(f"共提取 {len(keyframes)} 个关键帧")
        return keyframes
    
    def run(self) -> Dict:
        """
        执行完整的提取流程
        
        v2改进：加入均匀提取兜底模式，确保不遗漏重要镜头
        
        Returns:
            分析结果
        """
        # v2新增：均匀提取兜底模式
        if self.uniform_fallback:
            print("使用均匀提取兜底模式（每秒2帧）...")
            uniform_frames = self._uniform_extract(fps=2.0)
            print(f"均匀提取: {len(uniform_frames)} 帧")
        else:
            uniform_frames = []
        
        # 1. 检测场景
        scenes = self.detect_scenes()
        
        # 2. 分析动作密度
        scenes = self.analyze_action_density(scenes)
        
        # 3. 提取关键帧
        keyframes = self.extract_keyframes(scenes)
        
        # 4. v2新增：合并均匀提取和场景提取，去重
        if self.uniform_fallback:
            keyframes = self._merge_keyframes(uniform_frames, keyframes)
            print(f"合并后关键帧数: {len(keyframes)}")
        
        # 5. 保存结果
        result = {
            "video_info": {
                "path": self.video_path,
                "total_frames": self.total_frames,
                "fps": self.fps,
                "duration": self.duration,
                "resolution": f"{self.width}x{self.height}"
            },
            "scenes": [asdict(s) for s in scenes],
            "keyframes": [asdict(k) for k in keyframes],
            "extraction_config": {
                "min_fps": self.min_fps,
                "max_fps": self.max_fps,
                "scene_threshold": self.scene_threshold,
                "action_threshold": self.action_threshold,
                "uniform_fallback": self.uniform_fallback  # v2新增
            }
        }
        
        # 保存JSON
        result_path = self.output_dir / "extraction_result.json"
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"结果已保存到: {result_path}")
        
        return result
    
    def _uniform_extract(self, fps: float = 2.0) -> List[KeyframeInfo]:
        """
        v2新增：均匀提取关键帧
        
        Args:
            fps: 提取帧率（每秒提取帧数）
            
        Returns:
            关键帧列表
        """
        keyframes = []
        frame_interval = int(self.fps / fps)
        frame_counter = 0
        
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        for frame_idx in range(0, self.total_frames, frame_interval):
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = self.cap.read()
            if ret:
                frame_path = self.output_dir / f"frame_{frame_counter:04d}.jpg"
                cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                keyframes.append(KeyframeInfo(
                    frame_index=frame_idx,
                    timestamp=frame_idx / self.fps,
                    frame_path=str(frame_path),
                    frame_type='uniform',  # 标记为均匀提取
                    scene_id=-1,  # 未分配场景
                    action_density=0.0
                ))
                frame_counter += 1
        
        return keyframes
    
    def _merge_keyframes(self, uniform_frames: List[KeyframeInfo], scene_frames: List[KeyframeInfo]) -> List[KeyframeInfo]:
        """
        v2新增：合并均匀提取和场景提取的关键帧，去重
        
        Args:
            uniform_frames: 均匀提取的关键帧
            scene_frames: 场景提取的关键帧
            
        Returns:
            合并后的关键帧列表
        """
        # 使用帧索引去重（允许±5帧的容差）
        frame_indices = set()
        merged = []
        
        # 先添加均匀提取的帧
        for kf in uniform_frames:
            if kf.frame_index not in frame_indices:
                frame_indices.add(kf.frame_index)
                merged.append(kf)
        
        # 再添加场景提取的帧（如果不在均匀提取范围内）
        for kf in scene_frames:
            # 检查是否已有相近的帧
            has_nearby = any(abs(kf.frame_index - idx) <= 5 for idx in frame_indices)
            if not has_nearby:
                frame_indices.add(kf.frame_index)
                merged.append(kf)
        
        # 按帧索引排序
        merged.sort(key=lambda x: x.frame_index)
        
        # 重新编号文件名
        for i, kf in enumerate(merged):
            old_path = Path(kf.frame_path)
            new_path = self.output_dir / f"frame_{i:04d}.jpg"
            if old_path.exists() and old_path != new_path:
                old_path.rename(new_path)
            kf.frame_path = str(new_path)
        
        return merged
    
    def __del__(self):
        if hasattr(self, 'cap'):
            self.cap.release()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='智能关键帧提取器 v2（均匀提取兜底模式）')
    parser.add_argument('--video_path', required=True, help='视频文件路径')
    parser.add_argument('--output_dir', required=True, help='输出目录')
    parser.add_argument('--min_fps', type=float, default=2.0, help='最小提取帧率（v2默认2.0）')
    parser.add_argument('--max_fps', type=float, default=5.0, help='最大提取帧率')
    parser.add_argument('--scene_threshold', type=float, default=0.3, help='场景切换阈值')
    parser.add_argument('--action_threshold', type=float, default=0.15, help='动作检测阈值')
    parser.add_argument('--no_uniform_fallback', action='store_true', help='禁用均匀提取兜底模式')
    
    args = parser.parse_args()
    
    extractor = SmartKeyframeExtractor(
        video_path=args.video_path,
        output_dir=args.output_dir,
        min_fps=args.min_fps,
        max_fps=args.max_fps,
        scene_threshold=args.scene_threshold,
        action_threshold=args.action_threshold,
        uniform_fallback=not args.no_uniform_fallback  # v2新增
    )
    
    result = extractor.run()
    
    print("\n提取完成!")
    print(f"场景数: {len(result['scenes'])}")
    print(f"关键帧数: {len(result['keyframes'])}")


if __name__ == '__main__':
    main()
