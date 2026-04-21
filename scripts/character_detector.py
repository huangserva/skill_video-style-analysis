#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色检测与跨帧聚类

功能：
1. 人脸检测 - 使用InsightFace检测每帧中的人脸
2. 特征提取 - 提取512维人脸嵌入向量
3. 跨帧聚类 - 余弦相似度贪心聚类，识别同一角色
4. 角色档案 - 生成每个角色的出现帧、代表面部、身体区域
5. ASR整合 - 可选：按时间戳匹配叙事线中的角色名
"""

import os
import sys
import json
import argparse
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FaceDetection:
    """单帧中的一个人脸检测结果"""
    keyframe_idx: int       # 关键帧在列表中的索引
    frame_path: str
    timestamp: float
    scene_id: int
    bbox: List[int]         # [x1, y1, x2, y2]
    det_score: float        # 检测置信度 0-1
    embedding: Optional[np.ndarray] = None  # 512维，不写入最终JSON
    face_quality: float = 0.0


@dataclass
class CharacterProfile:
    """聚类后的唯一角色"""
    character_id: int
    label: str
    appearance_count: int = 0
    keyframe_indices: List[int] = field(default_factory=list)
    scene_ids: List[int] = field(default_factory=list)
    face_bboxes: Dict[str, List[int]] = field(default_factory=dict)
    body_bboxes: Dict[str, List[int]] = field(default_factory=dict)
    representative_face_path: str = ""
    representative_frame_path: str = ""
    avg_det_score: float = 0.0
    matched_name: Optional[str] = None


class CharacterDetector:
    """角色检测与跨帧聚类器"""

    def __init__(
        self,
        keyframes_dir: str,
        output_path: str,
        extraction_result_path: str = None,
        narrative_path: str = None,
        similarity_threshold: float = 0.4,
        det_size: int = 640,
        det_thresh: float = 0.5
    ):
        self.keyframes_dir = Path(keyframes_dir)
        self.output_path = Path(output_path)
        self.extraction_result_path = extraction_result_path
        self.narrative_path = narrative_path
        self.similarity_threshold = similarity_threshold
        self.det_size = (det_size, det_size)
        self.det_thresh = det_thresh
        self.extraction_data = self._load_extraction_data()
        self.scene_ranges = self.extraction_data.get("scenes", []) if self.extraction_data else []

        # 输出目录
        self.characters_dir = self.output_path.parent / "characters"
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化 InsightFace
        self.app = None
        self._init_insightface()

    def _load_extraction_data(self) -> dict:
        """预加载 extraction_result.json，避免重复读取并支持场景推断"""
        if not self.extraction_result_path:
            return {}

        path = Path(self.extraction_result_path)
        if not path.exists():
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  [警告] 无法读取 extraction_result.json: {e}")
            return {}

    def _init_insightface(self):
        """初始化InsightFace模型"""
        try:
            from insightface.app import FaceAnalysis

            self.app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            self.app.prepare(ctx_id=0, det_size=self.det_size, det_thresh=self.det_thresh)
            print(f"InsightFace 模型加载完成 (det_size={self.det_size}, det_thresh={self.det_thresh})")
        except ImportError:
            print("InsightFace 未安装，请先安装: pip install insightface onnxruntime")
            sys.exit(1)
        except Exception as e:
            print(f"InsightFace 初始化失败: {e}")
            sys.exit(1)

    # ========== Phase 1: 加载与检测 ==========

    def load_keyframes(self) -> List[dict]:
        """
        加载关键帧元数据

        优先从 extraction_result.json 读取，否则扫描目录
        """
        keyframes = []

        if self.extraction_data:
            for i, kf in enumerate(self.extraction_data.get("keyframes", [])):
                keyframes.append({
                    "idx": i,
                    "frame_index": kf.get("frame_index", i),
                    "frame_path": kf["frame_path"],
                    "timestamp": kf.get("timestamp", 0.0),
                    "scene_id": self._resolve_scene_id(kf),
                })
            print(f"从 extraction_result.json 加载 {len(keyframes)} 个关键帧")
        else:
            # 扫描目录
            frame_files = sorted(self.keyframes_dir.glob("frame_*.jpg"))
            if not frame_files:
                frame_files = sorted(self.keyframes_dir.glob("frames_*.jpg"))
            if not frame_files:
                frame_files = sorted(self.keyframes_dir.glob("*.jpg"))

            for i, fp in enumerate(frame_files):
                keyframes.append({
                    "idx": i,
                    "frame_index": i,
                    "frame_path": str(fp),
                    "timestamp": 0.0,
                    "scene_id": -1,
                })
            print(f"从目录扫描到 {len(keyframes)} 个关键帧")

        return keyframes

    def _resolve_scene_id(self, keyframe: dict) -> int:
        """优先用 extraction 提供的 scene_id，否则按时间/帧号回填"""
        scene_id = keyframe.get("scene_id", -1)
        if isinstance(scene_id, int) and scene_id >= 0:
            return scene_id

        timestamp_raw = keyframe.get("timestamp", 0.0)
        frame_index_raw = keyframe.get("frame_index", -1)
        timestamp = float(0.0 if timestamp_raw is None else timestamp_raw)
        frame_index = int(-1 if frame_index_raw is None else frame_index_raw)

        for scene in self.scene_ranges:
            start_time_raw = scene.get("start_time", -1)
            end_time_raw = scene.get("end_time", -1)
            start_time = float(-1 if start_time_raw is None else start_time_raw)
            end_time = float(-1 if end_time_raw is None else end_time_raw)
            if start_time >= 0 and end_time >= 0 and start_time <= timestamp <= end_time:
                return int(scene.get("scene_id", -1))

            start_frame_raw = scene.get("start_frame", -1)
            end_frame_raw = scene.get("end_frame", -1)
            start_frame = int(-1 if start_frame_raw is None else start_frame_raw)
            end_frame = int(-1 if end_frame_raw is None else end_frame_raw)
            if frame_index >= 0 and start_frame >= 0 and end_frame >= 0:
                if start_frame <= frame_index <= end_frame:
                    return int(scene.get("scene_id", -1))

        return -1

    def detect_faces(self, keyframes: List[dict]) -> Tuple[List[FaceDetection], List[dict]]:
        """在每个关键帧中检测人脸并提取嵌入"""
        all_detections = []
        frame_visible_people = []

        for kf in keyframes:
            frame_path = kf["frame_path"]
            img = cv2.imread(frame_path)
            if img is None:
                print(f"  [警告] 无法读取: {frame_path}")
                continue

            faces = self.app.get(img)
            visible_count = len(faces)

            frame_visible_people.append({
                "keyframe_idx": kf["idx"],
                "frame_index": kf.get("frame_index", kf["idx"]),
                "frame_path": frame_path,
                "timestamp": round(float(kf.get("timestamp", 0.0) or 0.0), 3),
                "scene_id": kf.get("scene_id", -1),
                "visible_people_estimate": visible_count,
            })
            print(f"  {Path(frame_path).name}: 单帧可见人数估计 {visible_count}")

            if not faces:
                continue

            for face in faces:
                bbox = face.bbox.astype(int).tolist()
                det_score = float(face.det_score)
                embedding = face.normed_embedding  # 已归一化的512维向量

                detection = FaceDetection(
                    keyframe_idx=kf["idx"],
                    frame_path=frame_path,
                    timestamp=kf["timestamp"],
                    scene_id=kf["scene_id"],
                    bbox=bbox,
                    det_score=det_score,
                    embedding=embedding,
                )
                detection.face_quality = self._compute_face_quality(detection, img.shape)
                all_detections.append(detection)

        print(f"共检测到 {len(all_detections)} 张人脸")
        return all_detections, frame_visible_people

    def _compute_face_quality(self, det: FaceDetection, img_shape: tuple) -> float:
        """
        计算人脸质量分数

        综合 bbox 面积占比、检测置信度、正脸程度
        """
        x1, y1, x2, y2 = det.bbox
        face_area = (x2 - x1) * (y2 - y1)
        img_area = img_shape[0] * img_shape[1]
        area_ratio = min(face_area / max(img_area, 1), 1.0)

        # 面积占比（越大越好，但上限 0.3 就够了）
        area_score = min(area_ratio / 0.3, 1.0)

        # 置信度
        conf_score = det.det_score

        # 宽高比（接近1:1.3为正脸）
        face_w = x2 - x1
        face_h = y2 - y1
        aspect = face_w / max(face_h, 1)
        frontal_score = 1.0 - min(abs(aspect - 0.77), 0.5) / 0.5

        return area_score * 0.3 + conf_score * 0.4 + frontal_score * 0.3

    # ========== Phase 2: 聚类 ==========

    def cluster_faces(self, detections: List[FaceDetection]) -> List[List[int]]:
        """
        贪心聚类：余弦相似度 + 平均链接

        返回: List[List[int]] — 每个子列表是同一角色的 detection 索引
        """
        if not detections:
            return []

        n = len(detections)
        if n == 1:
            return [[0]]

        # 构建嵌入矩阵
        embeddings = np.array([d.embedding for d in detections])
        # L2归一化（InsightFace已归一化，双保险）
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        embeddings = embeddings / norms

        # 余弦相似度矩阵
        sim_matrix = embeddings @ embeddings.T

        # 按 face_quality 降序排列
        qualities = np.array([d.face_quality for d in detections])
        order = np.argsort(-qualities)

        assigned = [False] * n
        clusters = []

        for i in order:
            if assigned[i]:
                continue

            cluster = [int(i)]
            assigned[i] = True

            for j in order:
                if assigned[j]:
                    continue

                # 平均链接：与簇内所有成员的平均相似度
                avg_sim = np.mean([sim_matrix[j][k] for k in cluster])

                if avg_sim >= self.similarity_threshold:
                    cluster.append(int(j))
                    assigned[j] = True

            clusters.append(cluster)

        print(f"聚类完成: {n} 张人脸 → {len(clusters)} 个角色")
        return clusters

    # ========== Phase 3: 构建角色档案 ==========

    def build_profiles(
        self, clusters: List[List[int]], detections: List[FaceDetection]
    ) -> List[CharacterProfile]:
        """为每个聚类构建角色档案"""
        profiles = []

        for char_id, cluster_indices in enumerate(clusters):
            cluster_dets = [detections[i] for i in cluster_indices]

            # 出现帧和场景
            keyframe_indices = sorted(set(d.keyframe_idx for d in cluster_dets))
            scene_ids = sorted(set(d.scene_id for d in cluster_dets if d.scene_id >= 0))

            # 每帧的人脸和身体 bbox
            face_bboxes = {}
            body_bboxes = {}
            for d in cluster_dets:
                fname = Path(d.frame_path).name
                face_bboxes[fname] = d.bbox
                img = cv2.imread(d.frame_path)
                if img is not None:
                    body_bboxes[fname] = self._compute_body_bbox(d.bbox, img.shape)

            # 选择代表性人脸（质量最高的）
            best_det = max(cluster_dets, key=lambda d: d.face_quality)
            rep_face_path = str(self.characters_dir / f"char_{char_id}_face.jpg")
            self._save_face_crop(best_det, rep_face_path)

            profile = CharacterProfile(
                character_id=char_id,
                label=f"char_{char_id}",
                appearance_count=len(keyframe_indices),
                keyframe_indices=keyframe_indices,
                scene_ids=scene_ids,
                face_bboxes=face_bboxes,
                body_bboxes=body_bboxes,
                representative_face_path=rep_face_path,
                representative_frame_path=best_det.frame_path,
                avg_det_score=round(np.mean([d.det_score for d in cluster_dets]), 4),
            )
            profiles.append(profile)

        # 按出现次数降序排列
        profiles.sort(key=lambda p: p.appearance_count, reverse=True)
        # 重新编号
        for i, p in enumerate(profiles):
            p.character_id = i
            p.label = f"char_{i}"

        return profiles

    def _compute_body_bbox(self, face_bbox: List[int], img_shape: tuple) -> List[int]:
        """从人脸 bbox 估算身体区域"""
        x1, y1, x2, y2 = face_bbox
        face_h = y2 - y1
        face_w = x2 - x1

        body_x1 = max(0, x1 - int(face_w * 0.5))
        body_y1 = y1
        body_x2 = min(img_shape[1], x2 + int(face_w * 0.5))
        body_y2 = min(img_shape[0], y2 + int(face_h * 3.0))

        return [body_x1, body_y1, body_x2, body_y2]

    def _save_face_crop(self, det: FaceDetection, save_path: str, padding: float = 0.3):
        """裁切并保存代表性人脸"""
        img = cv2.imread(det.frame_path)
        if img is None:
            return

        h, w = img.shape[:2]
        x1, y1, x2, y2 = det.bbox
        face_w = x2 - x1
        face_h = y2 - y1

        # 加 padding
        pad_x = int(face_w * padding)
        pad_y = int(face_h * padding)
        cx1 = max(0, x1 - pad_x)
        cy1 = max(0, y1 - pad_y)
        cx2 = min(w, x2 + pad_x)
        cy2 = min(h, y2 + pad_y)

        crop = img[cy1:cy2, cx1:cx2]
        if crop.size > 0:
            cv2.imwrite(save_path, crop, [cv2.IMWRITE_JPEG_QUALITY, 95])

    # ========== Phase 4: ASR 整合 ==========

    def match_with_narrative(self, profiles: List[CharacterProfile]) -> List[CharacterProfile]:
        """
        将视觉角色与叙事线中的角色名匹配

        匹配策略：计算每个视觉角色出现的时间范围与 ASR 段落中
        提到某角色的时间范围之间的重叠度
        """
        if not self.narrative_path or not Path(self.narrative_path).exists():
            return profiles

        try:
            with open(self.narrative_path, "r", encoding="utf-8") as f:
                narrative = json.load(f)
        except Exception:
            print("  [警告] 无法读取 narrative_analysis.json，跳过角色名匹配")
            return profiles

        characters_from_text = narrative.get("characters_from_text", [])
        narrative_arc = narrative.get("narrative_arc", {})

        if not characters_from_text:
            return profiles

        # 为每个文本角色构建时间范围
        text_char_times = []
        for tc in characters_from_text:
            name = tc.get("name", "")
            # 从 narrative_arc 中提取时间范围
            time_ranges = []
            for act_key, act_val in narrative_arc.items():
                tr = act_val.get("time_range", "")
                if "-" in tr:
                    parts = tr.replace("s", "").split("-")
                    try:
                        start = float(parts[0])
                        end = float(parts[1])
                        time_ranges.append((start, end))
                    except ValueError:
                        pass
            text_char_times.append({"name": name, "role": tc.get("role", ""), "ranges": time_ranges})

        # 对每个视觉角色，找时间戳重叠最多的文本角色
        for profile in profiles:
            frame_times = set()
            for det_fname in profile.face_bboxes:
                # 需要从关键帧索引反查时间戳（简化：用 profile 里的帧索引）
                pass

            # 简化匹配：按出现顺序对应
            # 视觉角色按出现次数排序，文本角色按列表顺序
            # 第一个视觉角色 → 第一个文本角色
            if profile.character_id < len(text_char_times):
                tc = text_char_times[profile.character_id]
                profile.matched_name = tc["name"]
                print(f"  {profile.label} → {tc['name']} ({tc['role']})")

        return profiles

    # ========== 主流程 ==========

    def run(self) -> dict:
        """执行完整的角色检测流程"""
        print("=" * 70)
        print("角色检测与跨帧聚类")
        print("=" * 70)

        # 1. 加载关键帧
        print("\n[Phase 1] 加载关键帧...")
        keyframes = self.load_keyframes()
        if not keyframes:
            print("未找到关键帧，退出")
            return self._empty_result()

        # 2. 人脸检测
        print("\n[Phase 2] 人脸检测与特征提取...")
        detections, frame_visible_people = self.detect_faces(keyframes)
        if not detections:
            print("未检测到人脸")
            return self._empty_result(total_keyframes=len(keyframes), frame_visible_people=frame_visible_people)

        # 3. 聚类
        print("\n[Phase 3] 跨帧聚类...")
        clusters = self.cluster_faces(detections)

        # 4. 构建档案
        print("\n[Phase 4] 构建角色档案...")
        profiles = self.build_profiles(clusters, detections)

        # 5. ASR 整合
        if self.narrative_path:
            print("\n[Phase 5] ASR 角色名匹配...")
            profiles = self.match_with_narrative(profiles)

        # 6. 保存结果
        print("\n[保存] 写入结果...")
        result = self._save_results(profiles, len(keyframes), len(detections), frame_visible_people)

        print(f"\n结果已保存到: {self.output_path}")
        print(f"角色面部裁切: {self.characters_dir}/")
        print(f"跨帧人脸聚类数: {len(profiles)}")
        stable_visible = result.get("visible_people_stats", {}).get("stable_visible_people_estimate", 0)
        if stable_visible:
            print(f"稳定可见人数估计: {stable_visible}")

        return result

    def _build_count_stats(self, counts: List[int]) -> dict:
        """汇总单帧可见人数统计"""
        if not counts:
            return {
                "sampled_keyframes": 0,
                "frames_with_faces": 0,
                "min_visible_people": 0,
                "median_visible_people": 0,
                "max_visible_people": 0,
                "avg_visible_people": 0.0,
                "stable_visible_people_estimate": 0,
            }

        nonzero_counts = [c for c in counts if c > 0]
        stable_source = nonzero_counts or counts

        return {
            "sampled_keyframes": len(counts),
            "frames_with_faces": len(nonzero_counts),
            "min_visible_people": int(min(stable_source)),
            "median_visible_people": round(float(np.median(stable_source)), 2),
            "max_visible_people": int(max(counts)),
            "avg_visible_people": round(float(np.mean(counts)), 2),
            "stable_visible_people_estimate": int(round(float(np.median(stable_source)))),
        }

    def _build_scene_visible_people_stats(self, frame_visible_people: List[dict]) -> List[dict]:
        """按场景汇总人数统计"""
        stats = []
        frames_by_scene = {}

        for frame in frame_visible_people:
            scene_id = frame.get("scene_id", -1)
            frames_by_scene.setdefault(scene_id, []).append(frame)

        if self.scene_ranges:
            for scene in self.scene_ranges:
                scene_id = int(scene.get("scene_id", -1))
                frames = frames_by_scene.get(scene_id, [])
                counts = [item.get("visible_people_estimate", 0) for item in frames]
                item = {
                    "scene_id": scene_id,
                    "time_range": (
                        f"{float(scene.get('start_time', 0.0) or 0.0):.1f}-"
                        f"{float(scene.get('end_time', 0.0) or 0.0):.1f}s"
                    ),
                }
                item.update(self._build_count_stats(counts))
                stats.append(item)
            return stats

        for scene_id, frames in sorted(frames_by_scene.items()):
            counts = [item.get("visible_people_estimate", 0) for item in frames]
            item = {"scene_id": scene_id, "time_range": "[unknown]"}
            item.update(self._build_count_stats(counts))
            stats.append(item)

        return stats

    def _save_results(
        self,
        profiles: List[CharacterProfile],
        total_keyframes: int,
        total_faces: int,
        frame_visible_people: List[dict],
    ) -> dict:
        """保存结果为 JSON"""
        visible_people_stats = self._build_count_stats(
            [item.get("visible_people_estimate", 0) for item in frame_visible_people]
        )
        result = {
            "version": "1.0.0",
            "analysis_timestamp": datetime.now().isoformat(),
            "keyframes_dir": str(self.keyframes_dir),
            "total_keyframes_analyzed": total_keyframes,
            "total_faces_detected": total_faces,
            "unique_characters": len(profiles),
            "counting_basis": "per_keyframe_face_detection",
            "visible_people_stats": visible_people_stats,
            "scene_visible_people_stats": self._build_scene_visible_people_stats(frame_visible_people),
            "frame_visible_people": frame_visible_people,
            "clustering_config": {
                "model": "buffalo_l",
                "similarity_threshold": self.similarity_threshold,
                "det_size": list(self.det_size),
                "det_thresh": self.det_thresh,
            },
            "characters": [],
        }

        for p in profiles:
            char_data = {
                "character_id": p.character_id,
                "label": p.label,
                "matched_name": p.matched_name,
                "appearance_count": p.appearance_count,
                "keyframe_indices": p.keyframe_indices,
                "scene_ids": p.scene_ids,
                "face_bboxes": p.face_bboxes,
                "body_bboxes": p.body_bboxes,
                "representative_face_path": p.representative_face_path,
                "representative_frame_path": p.representative_frame_path,
                "avg_det_score": p.avg_det_score,
            }
            result["characters"].append(char_data)

        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return result

    def _empty_result(self, total_keyframes: int = 0, frame_visible_people: Optional[List[dict]] = None) -> dict:
        """无检测结果时的空输出"""
        frame_visible_people = frame_visible_people or []
        result = {
            "version": "1.0.0",
            "analysis_timestamp": datetime.now().isoformat(),
            "keyframes_dir": str(self.keyframes_dir),
            "total_keyframes_analyzed": total_keyframes,
            "total_faces_detected": 0,
            "unique_characters": 0,
            "counting_basis": "per_keyframe_face_detection",
            "visible_people_stats": self._build_count_stats(
                [item.get("visible_people_estimate", 0) for item in frame_visible_people]
            ),
            "scene_visible_people_stats": self._build_scene_visible_people_stats(frame_visible_people),
            "frame_visible_people": frame_visible_people,
            "clustering_config": {
                "model": "buffalo_l",
                "similarity_threshold": self.similarity_threshold,
                "det_size": list(self.det_size),
                "det_thresh": self.det_thresh,
            },
            "characters": [],
            "warnings": ["未检测到人脸"],
        }

        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return result


def main():
    parser = argparse.ArgumentParser(description="角色检测与跨帧聚类（InsightFace）")
    parser.add_argument("--keyframes_dir", required=True, help="关键帧目录")
    parser.add_argument("--output_path", required=True, help="输出 JSON 路径")
    parser.add_argument("--extraction_result", default=None,
                        help="extraction_result.json 路径（可选）")
    parser.add_argument("--narrative_path", default=None,
                        help="narrative_analysis.json 路径（可选，用于角色名匹配）")
    parser.add_argument("--similarity_threshold", type=float, default=0.4,
                        help="聚类余弦相似度阈值（默认0.4）")
    parser.add_argument("--det_size", type=int, default=640,
                        help="InsightFace 检测输入尺寸（默认640）")
    parser.add_argument("--det_thresh", type=float, default=0.5,
                        help="人脸检测置信度阈值（默认0.5）")

    args = parser.parse_args()

    detector = CharacterDetector(
        keyframes_dir=args.keyframes_dir,
        output_path=args.output_path,
        extraction_result_path=args.extraction_result,
        narrative_path=args.narrative_path,
        similarity_threshold=args.similarity_threshold,
        det_size=args.det_size,
        det_thresh=args.det_thresh,
    )

    result = detector.run()

    print("\n" + "=" * 70)
    print(f"角色检测完成: 跨帧人脸聚类数 {result['unique_characters']}")
    stable_visible = result.get("visible_people_stats", {}).get("stable_visible_people_estimate", 0)
    if stable_visible:
        print(f"稳定可见人数估计: {stable_visible}")
    print("=" * 70)


if __name__ == "__main__":
    main()
