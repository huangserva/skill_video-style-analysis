#!/usr/bin/env python3
import cv2
import numpy as np
import glob

# 读取所有帧
frame_files = sorted(glob.glob('/workspace/projects/video-style-analysis/frames_*.jpg'))
print(f"找到 {len(frame_files)} 帧")

# 分析第一帧作为示例
first_frame = cv2.imread(frame_files[0])
print(f"第一帧尺寸: {first_frame.shape}")

# 转换为HSV色彩空间分析色调
hsv = cv2.cvtColor(first_frame, cv2.COLOR_BGR2HSV)

# 分析色调分布
h_hist = cv2.calcHist([hsv], [0], None, [180], [0, 180])
s_hist = cv2.calcHist([hsv], [1], None, [256], [0, 256])
v_hist = cv2.calcHist([hsv], [2], None, [256], [0, 256])

# 找出主要色调
dominant_hue = np.argmax(h_hist)
dominant_sat = np.argmax(s_hist)
dominant_val = np.argmax(v_hist)

print(f"\n色彩分析:")
print(f"  主要色调(H): {dominant_hue}° (0=红, 60=黄, 120=绿, 180=青, 240=蓝, 300=洋红)")
print(f"  主要饱和度(S): {dominant_sat}/255")
print(f"  主要亮度(V): {dominant_val}/255")

# 分析RGB平均色
mean_rgb = np.mean(first_frame, axis=(0, 1))
print(f"\n  平均RGB: R={int(mean_rgb[2])}, G={int(mean_rgb[1])}, B={int(mean_rgb[0])}")

# 判断色温
r, g, b = mean_rgb[2], mean_rgb[1], mean_rgb[0]
if r > b and g > b:
    color_tone = "暖色调"
else:
    color_tone = "冷色调"
print(f"  色调倾向: {color_tone}")

# 分析多帧的平均色彩
all_rgbs = []
for frame_file in frame_files[:5]:  # 分析前5帧
    frame = cv2.imread(frame_file)
    rgb = np.mean(frame, axis=(0, 1))
    all_rgbs.append(rgb)

avg_rgb = np.mean(all_rgbs, axis=0)
print(f"\n前5帧平均RGB: R={int(avg_rgb[2])}, G={int(avg_rgb[1])}, B={int(avg_rgb[0])}")
