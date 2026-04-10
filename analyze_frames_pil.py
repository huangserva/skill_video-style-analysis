#!/usr/bin/env python3
from PIL import Image
import glob
import numpy as np

# 读取所有帧
frame_files = sorted(glob.glob('/workspace/projects/video-style-analysis/frames_*.jpg'))
print(f"找到 {len(frame_files)} 帧")

# 分析第一帧
first_frame = Image.open(frame_files[0])
print(f"第一帧尺寸: {first_frame.size}")

# 转换为numpy数组
img_array = np.array(first_frame)

# 分析RGB平均色
mean_rgb = np.mean(img_array, axis=(0, 1))
print(f"\n色彩分析:")
print(f"  平均RGB: R={int(mean_rgb[0])}, G={int(mean_rgb[1])}, B={int(mean_rgb[2])}")

# 判断色温
r, g, b = mean_rgb[0], mean_rgb[1], mean_rgb[2]
if r > b and g > b:
    color_tone = "暖色调"
    color_brightness = "明亮"
else:
    color_tone = "冷色调"
    color_brightness = "偏暗"
print(f"  色调倾向: {color_tone}")
print(f"  亮度倾向: {color_brightness}")

# 分析多帧的平均色彩
all_rgbs = []
for frame_file in frame_files[:5]:  # 分析前5帧
    frame = Image.open(frame_file)
    img_array = np.array(frame)
    rgb = np.mean(img_array, axis=(0, 1))
    all_rgbs.append(rgb)

avg_rgb = np.mean(all_rgbs, axis=0)
print(f"\n前5帧平均RGB: R={int(avg_rgb[0])}, G={int(avg_rgb[1])}, B={int(avg_rgb[2])}")

# 分析对比度
contrast = np.std(img_array)
print(f"\n画面对比度: {contrast:.2f}")
if contrast > 50:
    contrast_level = "高对比度"
elif contrast > 30:
    contrast_level = "中等对比度"
else:
    contrast_level = "低对比度"
print(f"  对比度水平: {contrast_level}")
