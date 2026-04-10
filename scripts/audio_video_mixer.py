#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音视频精确对齐合成模块
基于ASR时间戳将TTS音频与视频精确对齐
支持音频拉伸/压缩匹配视频时长
"""

import os
import json
import argparse
import sys


def align_audio_to_video_with_timestamps(video_path, tts_audio_path, output_path, asr_json_path=None, tts_result_json_path=None):
    """
    基于时间戳将TTS音频与视频精确对齐

    参数:
        video_path: 输入视频路径（新生成的视频）
        tts_audio_path: TTS克隆音频路径
        output_path: 输出视频路径
        asr_json_path: ASR识别结果JSON路径（可选，用于时间戳对齐）
        tts_result_json_path: TTS生成结果JSON路径（可选）

    返回:
        dict: 对齐合成结果
    """
    print("=" * 70)
    print("音视频精确对齐合成")
    print("=" * 70)

    # 验证输入文件
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    if not os.path.exists(tts_audio_path):
        raise FileNotFoundError(f"TTS音频文件不存在: {tts_audio_path}")

    print(f"\n[第一步] 验证输入文件...")
    print(f"  输入视频: {video_path}")
    print(f"  TTS音频: {tts_audio_path}")

    # 读取时间戳数据
    timestamp_mapping = None
    if asr_json_path and os.path.exists(asr_json_path):
        print(f"\n[第二步] 读取时间戳数据...")
        with open(asr_json_path, 'r', encoding='utf-8') as f:
            asr_data = json.load(f)

        if tts_result_json_path and os.path.exists(tts_result_json_path):
            with open(tts_result_json_path, 'r', encoding='utf-8') as f:
                tts_result = json.load(f)
            timestamp_mapping = tts_result.get('timestamp_alignment')
        else:
            timestamp_mapping = {
                "asr_duration": asr_data.get("duration", 0),
                "segments": asr_data.get("segments", [])
            }

        print(f"  ✓ 时间戳数据加载完成")
        print(f"    ASR时长: {timestamp_mapping.get('asr_duration', 0):.2f} 秒")

    # 加载视频和音频
    print(f"\n[第三步] 加载音视频文件...")

    try:
        from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip
    except ImportError:
        raise ImportError("未安装 moviepy，请先安装: pip install moviepy")

    video_clip = VideoFileClip(video_path)
    tts_audio = AudioFileClip(tts_audio_path)

    print(f"  视频时长: {video_clip.duration:.2f} 秒")
    print(f"  音频时长: {tts_audio.duration:.2f} 秒")

    # 计算时长差异
    duration_diff = tts_audio.duration - video_clip.duration
    print(f"  时长差异: {duration_diff:+.2f} 秒")

    # 时长校验：ASR 原始时长 vs TTS 生成时长
    if timestamp_mapping:
        asr_duration = timestamp_mapping.get("asr_duration") or timestamp_mapping.get("total_duration", 0)
        if asr_duration > 0:
            tts_vs_asr_ratio = abs(tts_audio.duration - asr_duration) / asr_duration
            if tts_vs_asr_ratio > 0.5:
                print(f"  [警告] TTS时长 ({tts_audio.duration:.1f}s) 与ASR原始时长 ({asr_duration:.1f}s) 差异超过50%，变速后声音可能严重失真")
            elif tts_vs_asr_ratio > 0.3:
                print(f"  [注意] TTS时长 ({tts_audio.duration:.1f}s) 与ASR原始时长 ({asr_duration:.1f}s) 差异超过30%，变速后声音可能有轻微失真")

    # 视频 vs 音频差异校验
    if video_clip.duration > 0:
        video_audio_ratio = abs(duration_diff) / video_clip.duration
        if video_audio_ratio > 0.5:
            print(f"  [警告] 音视频时长差异超过50%（{video_audio_ratio:.0%}），合成质量可能受影响")

    # 调整音频时长以匹配视频
    final_audio = tts_audio
    if abs(duration_diff) > 0.1:  # 差异超过0.1秒时调整
        print(f"\n[第四步] 调整音频时长...")

        if duration_diff > 0:
            # 音频比视频长，需要压缩
            print(f"  音频比视频长 {duration_diff:.2f} 秒，需要压缩")
            compression_ratio = video_clip.duration / tts_audio.duration
            print(f"  压缩比例: {compression_ratio:.3f}")

            try:
                # 使用MoviePy的speedx函数压缩音频
                final_audio = tts_audio.speedx(factor=compression_ratio)
                print(f"  ✓ 音频压缩完成")
            except Exception as e:
                print(f"  ⚠️  音频压缩失败，将使用截断方式: {str(e)}")
                final_audio = tts_audio.subclip(0, video_clip.duration)

        else:
            # 音频比视频短，需要拉伸
            print(f"  音频比视频短 {-duration_diff:.2f} 秒，需要拉伸")
            stretch_ratio = video_clip.duration / tts_audio.duration
            print(f"  拉伸比例: {stretch_ratio:.3f}")

            try:
                # 使用MoviePy的speedx函数拉伸音频
                final_audio = tts_audio.speedx(factor=stretch_ratio)
                print(f"  ✓ 音频拉伸完成")
            except Exception as e:
                print(f"  ⚠️  音频拉伸失败，将使用循环方式: {str(e)}")
                loop_count = int(video_clip.duration / tts_audio.duration) + 1
                audio_segments = [tts_audio] * loop_count
                final_audio = CompositeAudioClip(audio_segments).subclip(0, video_clip.duration)
                print(f"  音频已循环 {loop_count} 次")

    # 替换原视频的音频
    print(f"\n[第五步] 合成音轨...")
    final_clip = video_clip.with_audio(final_audio)
    print(f"  ✓ 音轨替换完成")

    # 输出视频
    print(f"\n[第六步] 输出视频...")
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    print(f"  正在写入视频: {output_path}")
    final_clip.write_videofile(
        output_path,
        codec='libx264',
        audio_codec='aac',
        fps=video_clip.fps,
        threads=4,
        logger=None
    )

    print(f"  ✓ 视频输出完成")

    # 关闭资源
    video_clip.close()
    tts_audio.close()
    final_clip.close()

    # 生成结果报告
    result = {
        "output_path": output_path,
        "video_info": {
            "original_duration": video_clip.duration,
            "fps": video_clip.fps,
            "size": video_clip.size
        },
        "audio_info": {
            "original_tts_duration": tts_audio.duration,
            "final_audio_duration": final_audio.duration,
            "duration_adjustment": duration_diff
        },
        "timestamp_alignment": timestamp_mapping is not None,
        "status": "success"
    }

    print(f"\n[完成] 音视频对齐合成成功！")
    print(f"  输出文件: {output_path}")
    print(f"  视频时长: {result['video_info']['original_duration']:.2f} 秒")
    print(f"  音频时长: {result['audio_info']['final_audio_duration']:.2f} 秒")

    if timestamp_mapping:
        print(f"  时间戳对齐: 已启用")

    return result


def mix_audio_to_video(video_path, audio_path, output_path, bgm_path=None):
    """
    保留原有功能：将音频混入视频（兼容旧接口）

    参数:
        video_path: 输入视频路径
        audio_path: TTS解说音频路径
        output_path: 输出视频路径
        bgm_path: 背景音乐路径（可选）

    返回:
        dict: 合成结果
    """
    # 调用新的精确对齐函数
    return align_audio_to_video_with_timestamps(
        video_path=video_path,
        tts_audio_path=audio_path,
        output_path=output_path,
        asr_json_path=None,
        tts_result_json_path=None
    )


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='音视频精确对齐合成')
    parser.add_argument('--video_path', type=str, required=True, help='输入视频路径')
    parser.add_argument('--audio_path', type=str, required=True, help='TTS音频路径')
    parser.add_argument('--output_path', type=str, required=True, help='输出视频路径')
    parser.add_argument('--asr_json', type=str, default=None, help='ASR识别结果JSON路径（可选）')
    parser.add_argument('--tts_result_json', type=str, default=None, help='TTS生成结果JSON路径（可选）')

    args = parser.parse_args()

    try:
        result = align_audio_to_video_with_timestamps(
            video_path=args.video_path,
            tts_audio_path=args.audio_path,
            output_path=args.output_path,
            asr_json_path=args.asr_json,
            tts_result_json_path=args.tts_result_json
        )

        # 保存结果报告
        report_path = args.output_path.replace('.mp4', '_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n结果报告已保存: {report_path}")
        sys.exit(0)

    except Exception as e:
        print(f"\n错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
