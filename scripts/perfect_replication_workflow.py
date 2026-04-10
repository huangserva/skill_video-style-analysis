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
import argparse
import subprocess
from pathlib import Path


class WorkflowCoordinator:
    """工作流协调器 - 执行步骤1-3的自动化脚本（含步骤1.5角色检测）"""

    def __init__(self, reference_video_path, output_dir="output"):
        """
        初始化协调器

        参数:
            reference_video_path: 原视频路径
            output_dir: 输出目录
        """
        self.reference_video_path = reference_video_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 输出路径
        self.keyframes_dir = self.output_dir / "keyframes"
        self.analysis_dir = self.output_dir / "analysis"
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

        self.color_analysis_path = self.analysis_dir / "color_analysis.json"
        self.asr_result_path = self.analysis_dir / "asr_result.json"
        self.character_detection_path = self.analysis_dir / "character_detection.json"

    def step1_extract_keyframes(self):
        """
        步骤1: 智能关键帧提取
        """
        print("\n[步骤1] 智能关键帧提取...")
        print("=" * 70)

        cmd = [
            "python", "scripts/smart_keyframe_extractor.py",
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

        cmd = [
            "python", "scripts/character_detector.py",
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
                print(f"  检测到人脸: {total_faces}")
                print(f"  识别角色数: {unique_chars}")

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

        cmd = [
            "python", "scripts/video_analyzer.py",
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

        cmd = [
            "python", "scripts/asr_transcriber.py",
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
            print("\n后续步骤由 Claude 根据 SKILL.md 调度：")
            print("  步骤3.5: 分析 ASR 文本 → narrative_analysis.json")
            print("  步骤4:   查看关键帧 + 叙事线 → coherence_analysis.json")
            print("  步骤5:   音画关联分析 → audio_visual_correlation.json")
            print("  步骤6-7: 生成提示词 → scene_prompts.json + tts_guide.json")
            print("  步骤8:   python scripts/image_generator.py ...")
            print("  步骤9:   python scripts/video_generator.py ...")
            print("  步骤10:  python scripts/tts_generator.py ...")
            print("  步骤11:  python scripts/scene_concat.py + audio_video_mixer.py")

            if result_step1_5["success"]:
                chars = result_step1_5.get("data", {}).get("unique_characters", 0)
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
    parser.add_argument('--output_dir', type=str, default='output', help='输出目录')
    parser.add_argument('--whisper_model', type=str, default='base',
                        choices=['tiny', 'base', 'small', 'medium', 'large'],
                        help='Whisper模型大小')
    parser.add_argument('--language', type=str, default='zh', help='语音识别语言')

    args = parser.parse_args()

    # 验证输入文件
    if not os.path.exists(args.reference_video):
        print(f"❌ 错误：原视频文件不存在: {args.reference_video}")
        return 1

    # 创建协调器
    coordinator = WorkflowCoordinator(
        reference_video_path=args.reference_video,
        output_dir=args.output_dir
    )

    # 执行阶段1
    result = coordinator.run_stage1()

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
