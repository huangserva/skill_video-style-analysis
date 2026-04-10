# 视频分析报告格式规范

## 目录
- [概览](#概览)
- [报告结构](#报告结构)
- [字段说明](#字段说明)
- [示例](#示例)

## 概览
本文档定义了视频分析报告的标准化格式。报告采用JSON格式，包含技术规格、视觉风格分析、运动特征等信息。

## 报告结构

```json
{
  "video_path": "string",
  "technical_specs": {
    "resolution": "string",
    "frame_rate": "number",
    "duration": "number",
    "frame_count": "integer",
    "width": "integer",
    "height": "integer",
    "aspect_ratio": "string",
    "video_format": "string"
  },
  "visual_style": {
    "color_distribution": {
      "dominant_colors": {
        "red": "number",
        "green": "number",
        "blue": "number"
      },
      "color_features": {
        "mean_hue": "number",
        "mean_saturation": "number",
        "mean_value": "number"
      },
      "brightness": "number",
      "contrast": "number",
      "color_tone": "string"
    },
    "motion_characteristics": {
      "average_motion": "number",
      "motion_stability": "number",
      "motion_type": "string"
    }
  },
  "metadata": {
    "analysis_timestamp": "string (ISO 8601)",
    "analyzer_version": "string"
  }
}
```

## 字段说明

### video_path
- **类型**: string
- **说明**: 被分析视频的完整路径
- **示例**: `/path/to/video.mp4`

### technical_specs
- **类型**: object
- **说明**: 视频技术规格信息

#### resolution
- **类型**: string
- **格式**: `WIDTHxHEIGHT`
- **示例**: `1920x1080`

#### frame_rate
- **类型**: number
- **单位**: fps (帧/秒)
- **说明**: 视频的帧率，保留两位小数
- **示例**: `29.97`

#### duration
- **类型**: number
- **单位**: 秒
- **说明**: 视频总时长，保留两位小数
- **示例**: `120.5`

#### frame_count
- **类型**: integer
- **说明**: 视频总帧数
- **示例**: `3600`

#### width / height
- **类型**: integer
- **单位**: 像素
- **说明**: 视频的宽度和高度
- **示例**: `1920`, `1080`

#### aspect_ratio
- **类型**: string
- **格式**: 宽高比，保留两位小数
- **示例**: `1.78`

#### video_format
- **类型**: string
- **说明**: 视频格式
- **示例**: `MP4`, `AVI`, `MOV`

### visual_style
- **类型**: object
- **说明**: 视觉风格分析结果

#### color_distribution
- **类型**: object
- **说明**: 色彩分布分析

##### dominant_colors
- **类型**: object
- **说明**: 主色调RGB值，范围0-255
- **示例**: `{"red": 180.5, "green": 160.3, "blue": 140.2}`

##### color_features
- **类型**: object
- **说明**: HSV色彩空间特征

###### mean_hue
- **类型**: number
- **范围**: 0-180 (OpenCV HSV范围)
- **说明**: 平均色相值

###### mean_saturation
- **类型**: number
- **范围**: 0-255
- **说明**: 平均饱和度

###### mean_value
- **类型**: number
- **范围**: 0-255
- **说明**: 平均明度

##### brightness
- **类型**: number
- **范围**: 0-255
- **说明**: 平均亮度

##### contrast
- **类型**: number
- **说明**: 亮度标准差，表示对比度

##### color_tone
- **类型**: string
- **说明**: 色调类型分类
- **可选值**:
  - `low_saturation_gray` - 低饱和度灰调
  - `dark` - 暗调
  - `warm_red_orange` - 暖红色调
  - `warm_yellow` - 暖黄色调
  - `green` - 绿色调
  - `cyan` - 青色调
  - `blue` - 蓝色调
  - `purple` - 紫色调

#### motion_characteristics
- **类型**: object
- **说明**: 运动特征分析

##### average_motion
- **类型**: number
- **说明**: 平均运动量，基于光流法计算

##### motion_stability
- **类型**: number
- **说明**: 运动方差，表示运动稳定性

##### motion_type
- **类型**: string
- **说明**: 运动类型分类
- **可选值**:
  - `static` - 静态
  - `slow_movement` - 缓慢运动
  - `normal_movement` - 正常运动
  - `dynamic_fast` - 动态快速
  - `fast_movement` - 快速运动

### metadata
- **类型**: object
- **说明**: 分析元数据

#### analysis_timestamp
- **类型**: string
- **格式**: ISO 8601 日期时间
- **示例**: `2024-01-15T10:30:00.123456`

#### analyzer_version
- **类型**: string
- **说明**: 分析器版本号
- **示例**: `1.0.0`

## 验证规则

1. **必需字段**: 所有顶级字段（video_path, technical_specs, visual_style, metadata）均为必需
2. **数值范围**: 所有数值字段必须在指定范围内
3. **格式检查**: 日期时间必须符合ISO 8601格式
4. **枚举值**: color_tone 和 motion_type 必须在可选值范围内

## 使用建议

1. **文件命名**: 建议使用 `video_analysis_<timestamp>.json` 格式命名
2. **存储位置**: 存储在项目目录的 `analysis/` 子目录下
3. **版本控制**: 建议保留分析报告的版本历史
4. **共享使用**: 报告JSON文件可以直接在团队中共享和使用

## 示例

完整的报告示例请参考 `../assets/report_template.json`
