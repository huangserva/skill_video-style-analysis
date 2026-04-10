# ASR 输出格式说明

## 目录
1. [格式概述](#格式概述)
2. [字段说明](#字段说明)
3. [示例输出](#示例输出)
4. [使用场景](#使用场景)

## 格式概述

ASR（Automatic Speech Recognition）输出使用 JSON 格式，包含原视频的完整语音文本和精确的时间戳信息。

**JSON 结构**：
```json
{
  "video_path": "原视频路径",
  "language": "语言代码",
  "full_text": "完整文本",
  "duration": 总时长,
  "segments": [段落数组]
}
```

## 字段说明

### 顶层字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `video_path` | string | 原视频文件路径 | `/path/to/video.mp4` |
| `language` | string | 语言代码 | `zh`（中文）、`en`（英文） |
| `full_text` | string | 完整的语音文本 | `"大家好，今天要分享的是..."` |
| `duration` | float | 音频总时长（秒） | `30.5` |
| `segments` | array | 段落数组 | 见下方 |

### 段落（Segment）字段

每个段落包含一段连续的语音，字段如下：

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `id` | int | 段落ID | `0` |
| `start` | float | 段落开始时间（秒） | `0.0` |
| `end` | float | 段落结束时间（秒） | `2.5` |
| `text` | string | 段落文本 | `"大家好，今天要分享的是"` |
| `words` | array | 词级时间戳数组 | 见下方 |

### 词（Word）字段

每个词包含精确的时间戳信息：

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `word` | string | 词文本 | `"大家好"` |
| `start` | float | 词开始时间（秒） | `0.0` |
| `end` | float | 词结束时间（秒） | `0.8` |
| `confidence` | float | 识别置信度（0-1） | `0.95` |

## 示例输出

### 完整示例

```json
{
  "video_path": "/workspace/input/reference_video.mp4",
  "language": "zh",
  "full_text": "大家好，今天要分享的是关于AI视频生成技术的一些心得体会。在这个过程中，我们会探讨...",
  "duration": 45.2,
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 3.5,
      "text": "大家好，今天要分享的是关于AI视频生成技术的一些心得体会。",
      "words": [
        {"word": "大家好", "start": 0.0, "end": 0.8, "confidence": 0.95},
        {"word": "今天", "start": 0.9, "end": 1.2, "confidence": 0.92},
        {"word": "要", "start": 1.3, "end": 1.5, "confidence": 0.90},
        {"word": "分享", "start": 1.6, "end": 2.0, "confidence": 0.94},
        {"word": "的", "start": 2.1, "end": 2.3, "confidence": 0.88},
        {"word": "是", "start": 2.4, "end": 2.6, "confidence": 0.91},
        {"word": "关于", "start": 2.7, "end": 2.9, "confidence": 0.93},
        {"word": "AI", "start": 3.0, "end": 3.2, "confidence": 0.96},
        {"word": "视频", "start": 3.3, "end": 3.5, "confidence": 0.94}
      ]
    },
    {
      "id": 1,
      "start": 4.0,
      "end": 8.5,
      "text": "在这个过程中，我们会探讨如何使用AI工具来创作高质量的视频内容。",
      "words": [
        {"word": "在这个过程中", "start": 4.0, "end": 5.2, "confidence": 0.91},
        {"word": "我们", "start": 5.3, "end": 5.6, "confidence": 0.93},
        {"word": "会", "start": 5.7, "end": 5.9, "confidence": 0.89},
        {"word": "探讨", "start": 6.0, "end": 6.5, "confidence": 0.95},
        {"word": "如何", "start": 6.6, "end": 6.9, "confidence": 0.92},
        {"word": "使用", "start": 7.0, "end": 7.4, "confidence": 0.94},
        {"word": "AI", "start": 7.5, "end": 7.7, "confidence": 0.96},
        {"word": "工具", "start": 7.8, "end": 8.1, "confidence": 0.93},
        {"word": "来", "start": 8.2, "end": 8.4, "confidence": 0.90},
        {"word": "创作", "start": 8.5, "end": 9.0, "confidence": 0.95}
      ]
    }
  ]
}
```

### 简化示例（无词级时间戳）

如果未启用 `--word_level` 参数，输出将不包含 `words` 字段：

```json
{
  "video_path": "/workspace/input/video.mp4",
  "language": "zh",
  "full_text": "大家好，今天要分享的是...",
  "duration": 30.5,
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 3.5,
      "text": "大家好，今天要分享的是"
    }
  ]
}
```

## 使用场景

### 1. TTS语音克隆

ASR 输出作为 TTS 模块的输入：

```python
import json

# 读取ASR结果
with open('asr_result.json', 'r', encoding='utf-8') as f:
    asr_data = json.load(f)

# 提取完整文本
text_to_speak = asr_data['full_text']

# 提取时间戳（用于对齐）
timestamps = asr_data['segments']

# 调用TTS克隆
tts_generator.generate_cloned_tts(asr_data, output_path='cloned_speech.wav')
```

### 2. 音视频精确对齐

使用时间戳将TTS音频与视频精确对齐：

```python
# 读取ASR时间戳
with open('asr_result.json', 'r', encoding='utf-8') as f:
    asr_data = json.load(f)

# 读取TTS结果
with open('tts_result.json', 'r', encoding='utf-8') as f:
    tts_result = json.load(f)

# 使用时间戳对齐
audio_video_mixer.align_audio_to_video_with_timestamps(
    video_path='new_video.mp4',
    tts_audio_path='cloned_speech.wav',
    output_path='final_video.mp4',
    asr_json_path='asr_result.json',
    tts_result_json_path='tts_result.json'
)
```

### 3. 文本分析和翻译

提取文本进行进一步处理：

```python
import json

with open('asr_result.json', 'r', encoding='utf-8') as f:
    asr_data = json.load(f)

# 提取完整文本
full_text = asr_data['full_text']

# 翻译（智能体完成）
translated_text = translate_to_english(full_text)

# 提取词级时间戳（用于字幕生成）
subtitles = []
for seg in asr_data['segments']:
    for word in seg['words']:
        subtitles.append({
            'text': word['word'],
            'start': word['start'],
            'end': word['end']
        })
```

## 注意事项

1. **时间戳精度**：词级时间戳精度约为 0.1 秒，段落级时间戳精度约为 0.5 秒
2. **置信度阈值**：建议过滤置信度低于 0.8 的词
3. **语言支持**：Whisper 支持多种语言，详见 [Whisper 官方文档](https://github.com/openai/whisper)
4. **模型选择**：
   - `tiny`: 最快，准确率最低
   - `base`: 平衡速度和准确率（推荐）
   - `small`: 较慢，准确率较高
   - `medium/large`: 最慢，准确率最高
