#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补生成脚本 - 用于视频生成失败后的补救
功能：
1. 检查已完成的中间结果（ASR、TTS、分析、提示词）
2. 仅重新生成视频（调用智能体）
3. 等待视频生成完成
4. 执行音视频合成
"""

import os
import json
import argparse
import time


def check_intermediate_files(reference_video_path):
    """
    检查中间文件是否存在

    参数:
        reference_video_path: 参考视频路径

    返回:
        dict: 中间文件状态
    """
    asr_json_path = f"{reference_video_path}_asr.json"
    tts_audio_path = f"{reference_video_path}_cloned_tts.wav"
    analysis_json_path = f"{reference_video_path}_analysis.json"
    prompts_json_path = f"{reference_video_path}_prompts.json"
    state_json_path = f"{reference_video_path}_workflow_state.json"

    files_status = {
        "asr_json": {
            "path": asr_json_path,
            "exists": os.path.exists(asr_json_path),
            "required": True
        },
        "tts_audio": {
            "path": tts_audio_path,
            "exists": os.path.exists(tts_audio_path),
            "required": True
        },
        "analysis_json": {
            "path": analysis_json_path,
            "exists": os.path.exists(analysis_json_path),
            "required": True
        },
        "prompts_json": {
            "path": prompts_json_path,
            "exists": os.path.exists(prompts_json_path),
            "required": True
        },
        "state_json": {
            "path": state_json_path,
            "exists": os.path.exists(state_json_path),
            "required": False
        }
    }

    return files_status


def regenerate_video(reference_video_path, output_video_path, max_wait_time=600):
    """
    补生成视频

    参数:
        reference_video_path: 参考视频路径
        output_video_path: 输出视频路径
        max_wait_time: 最大等待时间（秒）

    返回:
        dict: 补生成结果
    """
    print("=" * 70)
    print("视频补生成")
    print("=" * 70)

    # 检查中间文件
    print("\n[第一步] 检查中间文件...")
    files_status = check_intermediate_files(reference_video_path)

    all_required_exist = True
    for file_name, file_info in files_status.items():
        if file_info["required"]:
            status = "✓" if file_info["exists"] else "❌"
            print(f"  {status} {file_name}: {file_info['path']}")
            if not file_info["exists"]:
                all_required_exist = False
        else:
            if file_info["exists"]:
                print(f"  ✓ {file_name}: {file_info['path']}")

    if not all_required_exist:
        print("\n❌ 错误：缺少必需的中间文件，无法补生成视频")
        print("   请先运行完整工作流生成中间文件")
        return {
            "success": False,
            "error": "缺少必需的中间文件"
        }

    print("\n✓ 所有必需的中间文件都存在，可以补生成视频")

    # 读取风格提示词
    print("\n[第二步] 读取风格提示词...")
    prompts_json_path = files_status["prompts_json"]["path"]
    with open(prompts_json_path, 'r', encoding='utf-8') as f:
        style_prompts = json.load(f)

    print(f"  视觉风格: {style_prompts.get('visual_style_prompt', '未知')}")
    print(f"  时长: {style_prompts.get('duration', 0)} 秒")
    print(f"  分辨率: {style_prompts.get('resolution', '未知')}")

    # 提交给智能体生成视频
    print("\n[第三步] 提交视频生成任务...")
    print(f"  输出路径: {output_video_path}")

    print(f"\n[智能体任务]")
    print(f"  任务: 基于风格提示词生成视频")
    print(f"  视觉风格: {style_prompts['visual_style_prompt']}")
    print(f"  时长: {style_prompts['duration']} 秒")
    print(f"  分辨率: {style_prompts['resolution']}")

    print(f"\n[重要] 视频生成任务已提交给智能体")
    print(f"  - 智能体将调用 seedance2.0 等工具生成视频")
    print(f"  - 预计排队时间：可能需要等待几分钟")

    # 等待视频生成
    print(f"\n[第四步] 等待视频生成...")
    print(f"  最大等待时间: {max_wait_time} 秒 ({max_wait_time//60} 分钟)")

    waited = 0
    interval = 10
    video_generated = False

    while waited < max_wait_time:
        if os.path.exists(output_video_path) and os.path.getsize(output_video_path) > 1000:
            print(f"  ✓ 视频已生成！")
            print(f"    文件大小: {os.path.getsize(output_video_path) / (1024*1024):.2f} MB")
            video_generated = True
            break

        print(f"  等待中... ({waited}/{max_wait_time} 秒)")
        time.sleep(interval)
        waited += interval

    if not video_generated:
        print(f"  ❌ 等待超时，视频未在 {max_wait_time} 秒内生成")
        return {
            "success": False,
            "error": f"视频生成超时（{max_wait_time} 秒）"
        }

    # 执行音视频合成
    print("\n[第五步] 音视频对齐合成...")

    tts_audio_path = files_status["tts_audio"]["path"]
    final_output_path = output_video_path.replace('.mp4', '_final.mp4')

    import subprocess
    try:
        result = subprocess.run(
            ['python', 'scripts/audio_video_mixer.py',
             '--video_path', output_video_path,
             '--audio_path', tts_audio_path,
             '--output_path', final_output_path,
             '--asr_json', files_status["asr_json"]["path"]],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            print(f"  ⚠️  音视频合成失败")
            print(f"  错误信息: {result.stderr}")
            return {
                "success": True,
                "video_generated": True,
                "audio_alignment": False,
                "output_path": output_video_path,
                "error": "音视频合成失败"
            }

        print(f"  ✓ 音视频合成完成")
        print(f"    最终输出: {final_output_path}")

        return {
            "success": True,
            "video_generated": True,
            "audio_alignment": True,
            "output_path": final_output_path
        }

    except Exception as e:
        print(f"  ❌ 音视频合成异常: {str(e)}")
        return {
            "success": True,
            "video_generated": True,
            "audio_alignment": False,
            "output_path": output_video_path,
            "error": str(e)
        }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='视频补生成（视频生成失败后补救）')
    parser.add_argument('--reference_video', type=str, required=True, help='原视频路径')
    parser.add_argument('--output_video', type=str, required=True, help='输出视频路径')
    parser.add_argument('--max_wait', type=int, default=600, help='最大等待时间（秒），默认600秒（10分钟）')

    args = parser.parse_args()

    # 执行补生成
    result = regenerate_video(
        reference_video_path=args.reference_video,
        output_video_path=args.output_video,
        max_wait_time=args.max_wait
    )

    # 显示结果
    print("\n" + "=" * 70)
    if result["success"]:
        print("✓ 补生成完成！")
        print("=" * 70)
        print(f"\n输出文件: {result.get('output_path')}")

        if result.get("audio_alignment"):
            print(f"✓ 音视频合成: 完成")
        else:
            print(f"⚠️  音视频合成: 失败")
            print(f"  视频文件: {result.get('output_path')}")
    else:
        print("❌ 补生成失败")
        print("=" * 70)
        print(f"\n错误: {result.get('error')}")


if __name__ == "__main__":
    main()
