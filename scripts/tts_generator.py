#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS音频生成模块
支持 edge_tts（免费）+ 可切换自定义 TTS 服务
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Voice 映射表：tone + emotion → edge_tts voice
# ---------------------------------------------------------------------------

VOICE_MAP = {
    # 女声
    ("温柔", "温暖"): "zh-CN-XiaoxiaoNeural",
    ("温柔", "亲切"): "zh-CN-XiaoxiaoNeural",
    ("温柔", "鼓励"): "zh-CN-XiaoxiaoNeural",
    ("平静", "中性"): "zh-CN-XiaoyiNeural",
    ("平静", "温暖"): "zh-CN-XiaoyiNeural",
    ("激昂", "温暖"): "zh-CN-XiaohanNeural",
    ("激昂", "鼓励"): "zh-CN-XiaohanNeural",
    # 男声
    ("激昂", "严肃"): "zh-CN-YunxiNeural",
    ("激昂", "热血"): "zh-CN-YunxiNeural",
    ("平静", "严肃"): "zh-CN-YunjianNeural",
    ("温柔", "中性"): "zh-CN-YunyangNeural",
}

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def map_voice(tone: str, emotion: str, gender: str = "") -> str:
    """根据语调+情感+性别映射到 edge_tts voice"""
    # 优先匹配精确的 (tone, emotion)
    voice = VOICE_MAP.get((tone, emotion))
    if voice:
        return voice

    # 如果指定了性别，用性别对应的默认
    if gender == "男性" or gender == "男":
        return "zh-CN-YunxiNeural"

    return DEFAULT_VOICE


# ---------------------------------------------------------------------------
# edge_tts 实现
# ---------------------------------------------------------------------------

async def generate_tts_edge(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "",
) -> dict:
    """使用 edge_tts 生成真实语音"""
    import edge_tts

    logger.info(f"edge_tts: voice={voice}, text={text[:50]}...")

    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(output_path))

    # 获取实际时长
    import wave
    try:
        with wave.open(output_path, "rb") as wf:
            frames = wf.getnframes()
            rate_val = wf.getframerate()
            duration = frames / rate_val if rate_val else 0
    except Exception:
        duration = len(text) / 3.0  # 估算

    return {
        "output_path": output_path,
        "duration": duration,
        "service": "edge_tts",
        "voice": voice,
    }


# ---------------------------------------------------------------------------
# 自定义 TTS 服务实现
# ---------------------------------------------------------------------------

async def generate_tts_custom(
    text: str,
    output_path: str,
    api_url: str,
    api_key: str = "",
) -> dict:
    """调用自定义 TTS API 生成语音"""
    import aiohttp

    logger.info(f"custom TTS: api_url={api_url}")

    payload = {
        "text": text,
        "output_path": output_path,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
        async with session.post(api_url, headers=headers, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                # 假设 API 返回音频 URL 或直接写入文件
                audio_url = data.get("audio_url") or data.get("url")
                if audio_url:
                    async with session.get(audio_url) as dl_resp:
                        if dl_resp.status == 200:
                            Path(output_path).write_bytes(await dl_resp.read())
            else:
                body = await resp.text()
                raise RuntimeError(f"自定义 TTS 失败 ({resp.status}): {body[:200]}")

    return {
        "output_path": output_path,
        "service": "custom",
        "api_url": api_url,
    }


# ---------------------------------------------------------------------------
# 正弦波兜底（调试用）
# ---------------------------------------------------------------------------

def generate_sine_wave(text: str, output_path: str, speed: str = "中等") -> dict:
    """生成正弦波音频（调试兜底）"""
    import numpy as np

    duration = estimate_audio_duration(text, speed)
    sample_rate = 44100
    num_samples = int(duration * sample_rate)

    t = np.linspace(0, duration, num_samples, False)
    audio_data = np.sin(2 * np.pi * 440 * t) * 0.3

    # 淡入淡出
    fade = int(sample_rate * 0.1)
    if len(audio_data) > fade * 2:
        audio_data[:fade] *= np.linspace(0, 1, fade)
        audio_data[-fade:] *= np.linspace(1, 0, fade)

    try:
        from scipy.io import wavfile
        wavfile.write(output_path, sample_rate, (audio_data * 32767).astype("int16"))
    except ImportError:
        import wave
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes((audio_data * 32767).astype("int16").tobytes())

    return {
        "output_path": output_path,
        "duration": duration,
        "service": "sine_wave_debug",
    }


def estimate_audio_duration(text: str, speed_level: str) -> float:
    """估算音频时长"""
    base_speed = 3.0
    adjustments = {"慢": 0.7, "较慢": 0.85, "中等": 1.0, "较快": 1.2, "快速": 1.4}
    return len(text) / (base_speed * adjustments.get(speed_level, 1.0))


# ---------------------------------------------------------------------------
# 时间戳估算（供 audio_video_mixer 使用）
# ---------------------------------------------------------------------------

def _estimate_timestamp_alignment(text: str, total_duration: float) -> dict:
    """
    基于字符均匀分布估算每个句子的时间戳。

    audio_video_mixer.py 期望 tts_result.json 包含 timestamp_alignment 字段，
    用于音画对齐。这里按句子切分文本，按字符比例分配时间。
    """
    import re

    # 按句号/问号/感叹号/换行切分
    sentences = [s.strip() for s in re.split(r'[。！？\n]+', text) if s.strip()]

    if not sentences:
        return {"method": "estimated", "total_duration": total_duration, "segments": []}

    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        return {"method": "estimated", "total_duration": total_duration, "segments": []}

    segments = []
    current_time = 0.0

    for sentence in sentences:
        char_ratio = len(sentence) / total_chars
        seg_duration = total_duration * char_ratio

        segments.append({
            "text": sentence,
            "start": round(current_time, 3),
            "end": round(current_time + seg_duration, 3),
        })
        current_time += seg_duration

    return {
        "method": "estimated",
        "total_duration": round(total_duration, 3),
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------

def generate_tts_audio(
    text: str,
    output_path: str,
    tone: str = "温暖",
    speed: str = "中等",
    emotion: str = "温暖",
    gender: str = "",
    service: str = "edge_tts",
    voice: str | None = None,
    custom_api_url: str = "",
    custom_api_key: str = "",
) -> dict:
    """统一 TTS 入口"""
    # 确保输出目录存在
    if os.path.dirname(output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    logger.info(f"TTS 生成: service={service}, tone={tone}, speed={speed}, emotion={emotion}")

    # 速率映射
    rate_map = {"慢": "-30%", "较慢": "-15%", "中等": "+0%", "较快": "+15%", "快速": "+30%"}
    rate = rate_map.get(speed, "+0%")

    if service == "edge_tts":
        selected_voice = voice or map_voice(tone, emotion, gender)
        result = asyncio.run(generate_tts_edge(text, output_path, voice=selected_voice, rate=rate))
    elif service == "custom" and custom_api_url:
        result = asyncio.run(generate_tts_custom(text, output_path, custom_api_url, custom_api_key))
    else:
        logger.warning(f"未知的 TTS 服务 '{service}'，使用正弦波兜底")
        result = generate_sine_wave(text, output_path, speed)

    # 补充元信息
    result["voice_params"] = {"tone": tone, "speed": speed, "emotion": emotion}
    result["narration_text"] = text

    # 生成 timestamp_alignment（基于字符均匀分布估算）
    result["timestamp_alignment"] = _estimate_timestamp_alignment(
        text, result.get("duration", estimate_audio_duration(text, speed))
    )

    # 保存结果 JSON
    result_json = output_path.replace(".wav", "_tts_result.json").replace(".mp3", "_tts_result.json")
    with open(result_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"TTS 完成: {output_path} ({result.get('duration', 0):.1f}s)")
    return result


def main():
    parser = argparse.ArgumentParser(description="TTS 音频生成")
    parser.add_argument("--text", type=str, required=True, help="解说文本")
    parser.add_argument("--output_path", type=str, required=True, help="输出音频路径")
    parser.add_argument("--tone", type=str, default="温暖", help="语调")
    parser.add_argument("--speed", type=str, default="中等", help="语速")
    parser.add_argument("--emotion", type=str, default="温暖", help="情感")
    parser.add_argument("--gender", type=str, default="", help="性别（男/女）")
    parser.add_argument("--service", type=str, default="edge_tts", choices=["edge_tts", "custom", "sine"], help="TTS 服务")
    parser.add_argument("--voice", type=str, default=None, help="直接指定 edge_tts voice 名称")
    parser.add_argument("--custom_api_url", type=str, default="", help="自定义 TTS API URL")
    parser.add_argument("--custom_api_key", type=str, default="", help="自定义 TTS API Key")

    args = parser.parse_args()

    result = generate_tts_audio(
        text=args.text,
        output_path=args.output_path,
        tone=args.tone,
        speed=args.speed,
        emotion=args.emotion,
        gender=args.gender,
        service=args.service,
        voice=args.voice,
        custom_api_url=args.custom_api_url,
        custom_api_key=args.custom_api_key,
    )
    return 0 if result.get("output_path") else 1


if __name__ == "__main__":
    sys.exit(main())
