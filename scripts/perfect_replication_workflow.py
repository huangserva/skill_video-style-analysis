#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段1自动化脚本（步骤1-3，含步骤1.5角色检测）
由 Skill 调度，执行关键帧提取、角色检测、色彩分析、ASR 语音识别
后续步骤（3.5-11）由 Claude 根据 SKILL.md 调度执行
"""

import os
import sys
import json
import re
import shutil
import argparse
import subprocess
from pathlib import Path


def derive_project_name(reference_video_path: str) -> str:
    """根据输入视频文件名生成稳定的项目目录名"""
    stem = Path(reference_video_path).stem or "project"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return safe_name or "project"


class WorkflowCoordinator:
    """工作流协调器 - 执行步骤1-3的自动化脚本（含步骤1.5角色检测）"""

    def __init__(self, reference_video_path, output_dir="output", dry_run=False, project_name=None):
        """
        初始化协调器

        参数:
            reference_video_path: 原视频路径
            output_dir: 输出根目录
            dry_run: 演练模式，跳过真实执行，生成占位文件
        """
        self.reference_video_path = reference_video_path
        self.project_name = project_name or derive_project_name(reference_video_path)
        self.output_root = Path(output_dir)
        if self.output_root.name == self.project_name:
            self.output_dir = self.output_root
        else:
            self.output_dir = self.output_root / self.project_name
        self.dry_run = dry_run
        self.python_executable = sys.executable or "python3"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 输出路径
        self.keyframes_dir = self.output_dir / "keyframes"
        self.analysis_dir = self.output_dir / "analysis"
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

        self.color_analysis_path = self.analysis_dir / "color_analysis.json"
        self.asr_result_path = self.analysis_dir / "asr_result.json"
        self.character_detection_path = self.analysis_dir / "character_detection.json"

    def preflight_check(self):
        """环境预检：在开始任何步骤前验证依赖完整性"""
        print("[预检] 检查环境依赖...")
        errors = []

        # 检查 ffmpeg
        if shutil.which("ffmpeg") is None:
            errors.append(
                "ffmpeg 未找到。请安装：\n"
                "    macOS: brew install ffmpeg\n"
                "    Ubuntu: sudo apt-get install ffmpeg\n"
                "    Windows: https://ffmpeg.org/download.html"
            )

        # 检查必需 Python 包
        required = {"cv2": "opencv-python", "numpy": "numpy", "yaml": "pyyaml"}
        for mod, pkg in required.items():
            try:
                __import__(mod)
            except ImportError:
                errors.append(f"缺少必需 Python 包: {pkg}（pip install {pkg}）")

        # 检查可选 Python 包
        optional = {
            "insightface": "步骤1.5（角色检测）将跳过",
            "whisper": "步骤3（ASR）将尝试 sub-agent",
            "edge_tts": "步骤10（TTS）将降级为正弦波",
        }
        for mod, fallback in optional.items():
            try:
                __import__(mod)
            except ImportError:
                print(f"  ⚠️  可选包 '{mod}' 未安装 — {fallback}")

        if errors:
            print("\n[预检失败] 以下依赖缺失：")
            for e in errors:
                print(f"  ❌ {e}")
            sys.exit(1)

        print("  ✓ 环境预检通过")

    def _dry_run_result(self, step_name, output_path=None, placeholder_data=None):
        """dry-run 模式返回占位结果"""
        print(f"  [DRY-RUN] 跳过 {step_name}，生成占位数据")
        data = placeholder_data or {}
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        return {"success": True, "data": data, "dry_run": True}

    def step1_extract_keyframes(self):
        """
        步骤1: 智能关键帧提取
        """
        print("\n[步骤1] 智能关键帧提取...")
        print("=" * 70)

        if self.dry_run:
            self.keyframes_dir.mkdir(parents=True, exist_ok=True)
            # 生成占位帧文件
            (self.keyframes_dir / "frame_0000.jpg").touch()
            placeholder = {
                "video_info": {"path": self.reference_video_path, "duration": 30.0, "fps": 30, "resolution": "1280x720"},
                "scenes": [{"scene_id": 0, "start_time": 0.0, "end_time": 30.0}],
                "keyframes": [{"frame_index": 0, "timestamp": 0.0, "frame_path": str(self.keyframes_dir / "frame_0000.jpg"), "frame_type": "uniform", "scene_id": 0}]
            }
            return self._dry_run_result("关键帧提取", str(self.keyframes_dir / "extraction_result.json"), placeholder)

        cmd = [
            self.python_executable, "scripts/smart_keyframe_extractor.py",
            "--video_path", self.reference_video_path,
            "--output_dir", str(self.keyframes_dir),
            "--min_fps", "2.0"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                print(f"  ✓ 关键帧提取完成")
                print(f"  输出目录: {self.keyframes_dir}")

                # 读取提取结果
                extraction_result_path = self.keyframes_dir / "extraction_result.json"
                if extraction_result_path.exists():
                    with open(extraction_result_path, 'r', encoding='utf-8') as f:
                        extraction_result = json.load(f)
                    print(f"  关键帧数量: {len(extraction_result.get('keyframes', []))}")
                    print(f"  场景数量: {len(extraction_result.get('scenes', []))}")
                    return {"success": True, "data": extraction_result}
                else:
                    return {"success": True, "data": {}}
            else:
                print(f"  ❌ 关键帧提取失败")
                print(f"  错误信息: {result.stderr}")
                return {"success": False, "error": result.stderr}

        except subprocess.TimeoutExpired:
            print(f"  ❌ 关键帧提取超时（>300秒）")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            print(f"  ❌ 关键帧提取异常: {str(e)}")
            return {"success": False, "error": str(e)}

    def step1_5_detect_characters(self):
        """
        步骤1.5: 角色检测与跨帧聚类（InsightFace）
        """
        print("\n[步骤1.5] 角色检测与跨帧聚类...")
        print("=" * 70)

        if self.dry_run:
            placeholder = {
                "unique_characters": 2,
                "total_faces_detected": 5,
                "visible_people_stats": {
                    "stable_visible_people_estimate": 2,
                    "max_visible_people": 2,
                },
                "characters": [
                    {"character_id": 0, "label": "char_0", "appearance_count": 3},
                    {"character_id": 1, "label": "char_1", "appearance_count": 2},
                ],
            }
            return self._dry_run_result("角色检测", str(self.character_detection_path), placeholder)

        cmd = [
            self.python_executable, "scripts/character_detector.py",
            "--keyframes_dir", str(self.keyframes_dir),
            "--output_path", str(self.character_detection_path),
        ]

        # 如果有 extraction_result.json，传入
        extraction_result_path = self.keyframes_dir / "extraction_result.json"
        if extraction_result_path.exists():
            cmd.extend(["--extraction_result", str(extraction_result_path)])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                print(f"  ✓ 角色检测完成")
                print(f"  输出文件: {self.character_detection_path}")

                with open(self.character_detection_path, 'r', encoding='utf-8') as f:
                    char_result = json.load(f)

                unique_chars = char_result.get('unique_characters', 0)
                total_faces = char_result.get('total_faces_detected', 0)
                stable_visible = (
                    char_result.get('visible_people_stats', {}) or {}
                ).get('stable_visible_people_estimate', 0)
                print(f"  检测到人脸: {total_faces}")
                print(f"  跨帧人脸聚类数: {unique_chars}")
                if stable_visible:
                    print(f"  稳定可见人数估计: {stable_visible}")

                return {"success": True, "data": char_result}
            else:
                print(f"  ⚠️  角色检测失败（可能未安装InsightFace）")
                print(f"  错误信息: {result.stderr[-500:] if result.stderr else 'N/A'}")
                return {"success": False, "error": result.stderr, "optional": True}

        except subprocess.TimeoutExpired:
            print(f"  ⚠️  角色检测超时（>300秒）")
            return {"success": False, "error": "Timeout", "optional": True}
        except Exception as e:
            print(f"  ⚠️  角色检测异常: {str(e)}")
            return {"success": False, "error": str(e), "optional": True}

    def step2_analyze_color(self):
        """
        步骤2: 色彩与运动分析
        """
        print("\n[步骤2] 色彩与运动分析...")
        print("=" * 70)

        if self.dry_run:
            placeholder = {"visual_style": {"color_distribution": {"color_tone": "warm_yellow"}, "motion_characteristics": {"motion_type": "slow_movement"}}}
            return self._dry_run_result("色彩分析", str(self.color_analysis_path), placeholder)

        cmd = [
            self.python_executable, "scripts/video_analyzer.py",
            "--video_path", self.reference_video_path,
            "--output_path", str(self.color_analysis_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                print(f"  ✓ 色彩分析完成")
                print(f"  输出文件: {self.color_analysis_path}")

                # 读取分析结果
                with open(self.color_analysis_path, 'r', encoding='utf-8') as f:
                    color_analysis = json.load(f)

                color_tone = color_analysis.get('visual_style', {}).get('color_distribution', {}).get('color_tone', '未知')
                motion_type = color_analysis.get('visual_style', {}).get('motion_characteristics', {}).get('motion_type', '未知')

                print(f"  色调类型: {color_tone}")
                print(f"  运动类型: {motion_type}")

                return {"success": True, "data": color_analysis}
            else:
                print(f"  ❌ 色彩分析失败")
                print(f"  错误信息: {result.stderr}")
                return {"success": False, "error": result.stderr}

        except subprocess.TimeoutExpired:
            print(f"  ❌ 色彩分析超时（>120秒）")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            print(f"  ❌ 色彩分析异常: {str(e)}")
            return {"success": False, "error": str(e)}

    def step3_asr_transcribe(self, model_size="base", language="zh", word_level=True):
        """
        步骤3: ASR语音识别与风格分析
        """
        print("\n[步骤3] ASR语音识别与风格分析...")
        print("=" * 70)

        if self.dry_run:
            placeholder = {"full_text": "（dry-run 占位文本）", "duration": 30.0, "segments": [], "voice_style": {"speed": {"level": "中等"}}}
            return self._dry_run_result("ASR语音识别", str(self.asr_result_path), placeholder)

        cmd = [
            self.python_executable, "scripts/asr_transcriber.py",
            "--video_path", self.reference_video_path,
            "--output_path", str(self.asr_result_path),
            "--model_size", model_size,
            "--language", language
        ]

        if word_level:
            cmd.append("--word_level")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode == 0:
                print(f"  ✓ ASR语音识别完成")
                print(f"  输出文件: {self.asr_result_path}")

                # 读取识别结果
                with open(self.asr_result_path, 'r', encoding='utf-8') as f:
                    asr_result = json.load(f)

                full_text = asr_result.get('full_text', '')
                duration = asr_result.get('duration', 0)
                segments_count = len(asr_result.get('segments', []))
                voice_style = asr_result.get('voice_style', {})

                print(f"  文本长度: {len(full_text)} 字符")
                print(f"  音频时长: {duration:.2f} 秒")
                print(f"  段落数量: {segments_count}")
                if voice_style:
                    print(f"  语速: {voice_style.get('speed', {}).get('level', '未知')}")

                return {"success": True, "data": asr_result}
            else:
                print(f"  ⚠️  ASR语音识别失败（可能未安装Whisper或视频无音频）")
                print(f"  错误信息: {result.stderr}")
                return {"success": False, "error": result.stderr, "optional": True}

        except subprocess.TimeoutExpired:
            print(f"  ⚠️  ASR语音识别超时（>600秒）")
            return {"success": False, "error": "Timeout", "optional": True}
        except Exception as e:
            print(f"  ⚠️  ASR语音识别异常: {str(e)}")
            return {"success": False, "error": str(e), "optional": True}

    def run_stage1(self):
        """
        执行阶段1（步骤1-3）
        """
        print("=" * 70)
        print("阶段1：深度视频与音频分析")
        print("=" * 70)
        print(f"项目目录: {self.output_dir}")

        # 环境预检
        self.preflight_check()

        # 执行步骤（步骤1.5依赖步骤1的关键帧，其余可并行）
        result_step1 = self.step1_extract_keyframes()
        result_step1_5 = self.step1_5_detect_characters()  # 依赖步骤1的关键帧
        result_step2 = self.step2_analyze_color()
        result_step3 = self.step3_asr_transcribe()

        # 汇总结果
        success = result_step1["success"] and result_step2["success"]
        # 角色检测和ASR是可选的，失败不影响整体流程

        workflow_state = {
            "stage": 1,
            "success": success,
            "steps": {
                "step1_keyframes": result_step1,
                "step1_5_characters": result_step1_5,
                "step2_color_analysis": result_step2,
                "step3_asr": result_step3
            },
            "output_paths": {
                "keyframes_dir": str(self.keyframes_dir),
                "character_detection": str(self.character_detection_path),
                "color_analysis": str(self.color_analysis_path),
                "asr_result": str(self.asr_result_path)
            }
        }

        # 保存状态
        state_path = self.output_dir / "workflow_state.json"
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(workflow_state, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 70)
        if success:
            print("✓ 阶段1完成！")

            # 自动生成步骤3.5-7（含3.6六棱镜语义骨架）的JSON初稿
            print("\n[初稿生成] 自动生成步骤3.5-7（含3.6六棱镜语义骨架）的JSON初稿...")
            draft_cmd = [
                self.python_executable, "scripts/draft_generator.py",
                "--input_dir", str(self.output_dir),
                "--output_dir", str(self.output_dir),
            ]
            try:
                draft_result = subprocess.run(draft_cmd, capture_output=True, text=True, timeout=30)
                if draft_result.returncode == 0:
                    print("  ✓ 初稿生成完成")
                else:
                    print(f"  ⚠️  初稿生成失败: {draft_result.stderr[-300:]}")
            except Exception as e:
                print(f"  ⚠️  初稿生成异常: {e}")

            print("\n后续步骤由 Claude 根据 SKILL.md 调度：")
            print("  步骤3.5-7（含3.6）: 审核并补充初稿中的 [TODO] 字段")
            print("  步骤8:   python scripts/image_generator.py ...")
            print("  步骤9:   python scripts/video_generator.py ...")
            print("  步骤10:  python scripts/tts_generator.py ...")
            print("  步骤11:  python scripts/scene_concat.py + audio_video_mixer.py")

            if result_step1_5["success"]:
                char_data = result_step1_5.get("data", {})
                chars = char_data.get("unique_characters", 0)
                stable_visible = (
                    char_data.get("visible_people_stats", {}) or {}
                ).get("stable_visible_people_estimate", 0)
                if stable_visible:
                    print(
                        f"\n  步骤1.5结果：跨帧人脸聚类数 {chars}，"
                        f"稳定可见人数估计 {stable_visible}"
                    )
                else:
                    print(f"\n  步骤1.5已识别 {chars} 个视觉角色（可在步骤4中使用）")

            if not result_step3["success"]:
                if result_step1_5["success"]:
                    print("\n⚠️  注意：ASR失败，但角色检测成功，将使用视觉角色数据辅助分析")
                else:
                    print("\n⚠️  注意：ASR和角色检测均失败，将进入纯视觉分析模式")
        else:
            print("⚠️ 阶段1部分失败，请检查错误信息")
        print("=" * 70)

        return workflow_state


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='阶段1自动化（步骤1-3）')
    parser.add_argument('--reference_video', type=str, required=True, help='原视频路径')
    parser.add_argument('--output_dir', type=str, default='output', help='输出根目录（会自动创建视频同名子目录）')
    parser.add_argument('--project_name', type=str, default=None, help='可选，自定义项目子目录名')
    parser.add_argument('--whisper_model', type=str, default='base',
                        choices=['tiny', 'base', 'small', 'medium', 'large'],
                        help='Whisper模型大小')
    parser.add_argument('--language', type=str, default='zh', help='语音识别语言')
    parser.add_argument('--dry-run', action='store_true',
                        help='演练模式：跳过真实执行，生成占位文件，验证管线通路')

    args = parser.parse_args()

    # dry-run 模式跳过文件存在检查
    if not args.dry_run and not os.path.exists(args.reference_video):
        print(f"❌ 错误：原视频文件不存在: {args.reference_video}")
        return 1

    # 创建协调器
    coordinator = WorkflowCoordinator(
        reference_video_path=args.reference_video,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        project_name=args.project_name,
    )

    # 执行阶段1
    result = coordinator.run_stage1()

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
