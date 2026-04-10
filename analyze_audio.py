#!/usr/bin/env python3
import numpy as np
import wave

# 读取音频文件
with wave.open('/workspace/projects/video-style-analysis/original_audio.wav', 'rb') as wav_file:
    # 获取音频参数
    sample_rate = wav_file.getframerate()
    n_frames = wav_file.getnframes()
    n_channels = wav_file.getnchannels()
    sample_width = wav_file.getsampwidth()

    # 读取音频数据
    audio_data = wav_file.readframes(n_frames)

print(f"采样率: {sample_rate} Hz")
print(f"帧数: {n_frames}")
print(f"声道数: {n_channels}")
print(f"采样位数: {sample_width}")
print(f"时长: {n_frames / sample_rate:.2f} 秒")

# 转换为numpy数组
audio_array = np.frombuffer(audio_data, dtype=np.int16)

# 分析音频特征
print(f"\n音频分析:")
print(f"  最大振幅: {np.max(np.abs(audio_array))}")
print(f"  平均振幅: {np.mean(np.abs(audio_array)):.2f}")
print(f"  标准差: {np.std(audio_array):.2f}")

# 检测静音部分
silence_threshold = 500
is_speech = np.abs(audio_array) > silence_threshold
speech_ratio = np.sum(is_speech) / len(is_speech)
print(f"  语音占比: {speech_ratio * 100:.1f}%")

# 分析能量分布
energy = audio_array ** 2
print(f"  总能量: {np.sum(energy):.2f}")
print(f"  平均能量: {np.mean(energy):.2f}")

# 分段分析（每5秒）
segment_length = sample_rate * 5
num_segments = n_frames // segment_length

print(f"\n分段分析（每5秒）:")
for i in range(min(num_segments, 10)):  # 最多显示前10段
    start = i * segment_length
    end = start + segment_length
    segment = audio_array[start:end]

    if len(segment) > 0:
        avg_energy = np.mean(np.abs(segment))
        max_energy = np.max(np.abs(segment))
        print(f"  [{i*5:2d}-{(i+1)*5:2d}s] 平均能量: {avg_energy:8.2f}, 最大能量: {max_energy:8.2f}")
