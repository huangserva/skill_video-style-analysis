#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASR语音识别脚本
使用Whisper模型提取视频中的语音文本和时间戳
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path


def extract_audio_from_video(video_path, audio_output_path):
    """
    从视频中提取音频轨道
    
    参数:
        video_path: 视频文件路径
        audio_output_path: 音频输出路径
        
    返回:
        bool: 是否成功
    """
    print(f"  正在提取音频轨道...")
    
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn",  # 不包含视频
        "-acodec", "pcm_s16le",  # 16位PCM编码
        "-ar", "16000",  # 采样率16kHz
        "-ac", "1",  # 单声道
        "-y",  # 覆盖输出文件
        audio_output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print(f"  ✓ 音频提取完成: {audio_output_path}")
            return True
        else:
            print(f"  ❌ 音频提取失败: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ❌ 音频提取异常: {str(e)}")
        return False


def transcribe_with_whisper(audio_path, output_json_path, model_size="base", language="zh", word_level=True):
    """
    使用Whisper进行语音识别
    
    参数:
        audio_path: 音频文件路径
        output_json_path: 输出JSON路径
        model_size: Whisper模型大小 (tiny/base/small/medium/large)
        language: 语言代码 (zh/en等)
        word_level: 是否提取词级时间戳
        
    返回:
        dict: 识别结果
    """
    print(f"  正在使用Whisper进行语音识别...")
    print(f"  模型: {model_size}")
    print(f"  语言: {language}")
    
    try:
        import whisper
        
        # 加载模型
        print(f"  正在加载Whisper模型...")
        model = whisper.load_model(model_size)
        
        # 转录
        print(f"  正在进行语音转录...")
        result = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=word_level
        )
        
        # 构建输出格式
        output = {
            "video_path": audio_path.replace("_extracted_audio.wav", ""),
            "language": language,
            "full_text": result["text"].strip(),
            "duration": result.get("segments", [{}])[-1].get("end", 0) if result.get("segments") else 0,
            "segments": []
        }
        
        # 提取段落
        for i, segment in enumerate(result.get("segments", [])):
            seg_data = {
                "id": i,
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip()
            }
            
            # 提取词级时间戳
            if word_level and "words" in segment:
                seg_data["words"] = []
                for word_info in segment["words"]:
                    seg_data["words"].append({
                        "word": word_info["word"].strip(),
                        "start": word_info["start"],
                        "end": word_info["end"],
                        "confidence": word_info.get("probability", 0.9)
                    })
            
            output["segments"].append(seg_data)
        
        # 保存JSON
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"  ✓ 语音识别完成")
        print(f"  文本长度: {len(output['full_text'])} 字符")
        print(f"  音频时长: {output['duration']:.2f} 秒")
        print(f"  段落数量: {len(output['segments'])}")
        
        return output
        
    except ImportError:
        print(f"  ❌ 未安装Whisper，请先安装: pip install openai-whisper")
        return None
    except Exception as e:
        print(f"  ❌ 语音识别异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def analyze_voice_style(asr_data):
    """
    分析语音风格
    
    参数:
        asr_data: ASR识别结果
        
    返回:
        dict: 语音风格分析结果
    """
    print(f"  正在分析语音风格...")
    
    if not asr_data or "segments" not in asr_data:
        return None
    
    segments = asr_data["segments"]
    
    # 计算平均语速（字符/秒）
    total_chars = sum(len(seg["text"]) for seg in segments)
    total_duration = segments[-1]["end"] if segments else 0
    
    if total_duration > 0:
        chars_per_second = total_chars / total_duration
    else:
        chars_per_second = 3.0  # 默认中等语速
    
    # 分类语速
    if chars_per_second < 2.5:
        speed_level = "慢速"
    elif chars_per_second < 3.5:
        speed_level = "中等"
    elif chars_per_second < 4.5:
        speed_level = "较快"
    else:
        speed_level = "快速"
    
    # 计算停顿频率
    pause_count = 0
    for i in range(len(segments) - 1):
        gap = segments[i+1]["start"] - segments[i]["end"]
        if gap > 0.5:  # 超过0.5秒算停顿
            pause_count += 1
    
    # 分析语音风格
    voice_style = {
        "speed": {
            "chars_per_second": round(chars_per_second, 2),
            "level": speed_level
        },
        "pause": {
            "count": pause_count,
            "frequency": round(pause_count / max(total_duration / 10, 1), 2)  # 每10秒停顿次数
        },
        "estimated_tone": "温柔",  # 需要更复杂的音频分析才能准确识别
        "estimated_emotion": "温暖"  # 需要更复杂的音频分析才能准确识别
    }
    
    print(f"  ✓ 语音风格分析完成")
    print(f"  语速: {speed_level} ({chars_per_second:.2f} 字符/秒)")
    print(f"  停顿次数: {pause_count}")
    
    return voice_style


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='ASR语音识别与风格分析')
    parser.add_argument('--video_path', type=str, required=True, help='视频文件路径')
    parser.add_argument('--output_path', type=str, required=True, help='输出JSON路径')
    parser.add_argument('--model_size', type=str, default='base', 
                        choices=['tiny', 'base', 'small', 'medium', 'large'],
                        help='Whisper模型大小')
    parser.add_argument('--language', type=str, default='zh', help='语言代码')
    parser.add_argument('--word_level', action='store_true', help='是否提取词级时间戳')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("ASR语音识别与风格分析")
    print("=" * 70)
    
    # 验证输入文件
    if not os.path.exists(args.video_path):
        print(f"❌ 错误：视频文件不存在: {args.video_path}")
        return 1
    
    # 创建临时音频文件
    temp_audio_path = args.video_path.replace('.mp4', '_extracted_audio.wav')
    if args.video_path.endswith('.mov'):
        temp_audio_path = args.video_path.replace('.mov', '_extracted_audio.wav')
    
    # 步骤1：提取音频
    print(f"\n[步骤1] 提取音频轨道...")
    if not extract_audio_from_video(args.video_path, temp_audio_path):
        print(f"❌ 音频提取失败")
        return 1
    
    # 步骤2：语音识别
    print(f"\n[步骤2] 语音识别...")
    asr_result = transcribe_with_whisper(
        audio_path=temp_audio_path,
        output_json_path=args.output_path,
        model_size=args.model_size,
        language=args.language,
        word_level=args.word_level
    )
    
    if not asr_result:
        print(f"❌ 语音识别失败")
        return 1
    
    # 步骤3：语音风格分析
    print(f"\n[步骤3] 语音风格分析...")
    voice_style = analyze_voice_style(asr_result)
    
    # 合并结果
    final_result = {
        **asr_result,
        "voice_style": voice_style
    }
    
    # 保存最终结果
    with open(args.output_path, 'w', encoding='utf-8') as f:
        json.dump(final_result, f, ensure_ascii=False, indent=2)
    
    # 清理临时文件
    if os.path.exists(temp_audio_path):
        os.remove(temp_audio_path)
        print(f"  已清理临时文件: {temp_audio_path}")
    
    print("\n" + "=" * 70)
    print("✓ ASR语音识别与风格分析完成！")
    print("=" * 70)
    print(f"输出文件: {args.output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
