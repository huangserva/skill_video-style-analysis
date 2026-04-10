---
name: video-style-analysis
description: 完美复刻原视频的完整内容（画面+声音），通过智能体分析原视频的视觉风格和音频特征，生成风格提示词，使用TTS复刻配音，基于原画面重新生成相似视频并合成；当用户需要完美复刻视频内容、语音克隆、视频风格迁移时使用
dependency:
  python:
    - opencv-python
    - numpy
    - moviepy
    - Pillow
    - openai-whisper
    - edge-tts
    - aiohttp
    - pyyaml
    - insightface
    - onnxruntime
---

# 视频完美复刻（智能体分析+TTS配音+音视频合成）

## 任务目标
- 本 Skill 用于：完美复刻原视频的完整内容，包括重新生成画面（保持高相似度）和克隆原视频的配音风格（音色、语调、节奏），并合成最终视频
- 能力包含：智能体视频分析（视觉+音频）、风格提示词生成、TTS配音生成、音视频合成
- 触发条件：用户需要完美复刻视频内容、克隆原视频配音风格、保持原故事情节和画面风格时使用

## 前置准备
- 依赖说明：确保已安装以下Python包
  ```
  opencv-python
  numpy
  moviepy
  Pillow
  openai-whisper
  ```

---

## 核心理念

### ⭐ ASR优先 + 分级容错机制

**关键洞察**：ASR语音识别不仅仅是"语音转文字"，更是**理解视频叙事的关键步骤**。

**对比**：
| 方法 | 只看图像 | 图像+ASR |
|------|----------|----------|
| 角色数量 | 可能误判（如数出7个） | 准确（如实际2个） |
| 主角识别 | 不确定 | 立刻知道 |
| 叙事线 | 需要猜测 | 文本直接说明 |
| 角色关系 | 不清楚 | 明确 |

**因此**：ASR结果**指导**角色识别，而非角色识别后再分析文本。

**执行方式**：ASR步骤如主session环境无法安装Whisper，会自动启动sub-agent session执行。

---

### ⚠️ 分级容错机制

**问题**：不是所有视频都有音频，也不是所有音频都能提取到有效的叙事线。

**解决方案**：三级容错机制，自动降级处理。

#### Level 1：ASR成功 + 叙事线清晰（最佳）✅

**触发条件**：
- 视频有音频轨道
- ASR成功提取文本
- 文本包含明确的角色信息和叙事线

**处理方式**：
- 按标准流程：ASR → 叙事线分析 → 角色识别 → 视觉验证
- 输出高质量叙事分析

**示例**：当前案例（富豪伪装穷人爱情故事）

---

#### Level 2：ASR成功但叙事线不清晰（次佳）⚠️

**触发条件**：
- 视频有音频轨道
- ASR成功提取文本
- 文本缺少明确角色信息或叙事线（如：环境音、音乐、片段式对话）

**处理方式**：
- **ASR辅助模式**：使用ASR时间戳作为场景边界
- **文本辅助**：提取关键词作为风格提示
- **降级到视觉分析**：主要依靠关键帧视觉分析
- **角色识别**：纯视觉推断 + ASR关键词辅助

**示例场景**：
- 旅游纪录片：ASR可能只有环境音，但时间戳可用于场景分割
- 美食视频：ASR可能只有烹饪声音，但可以提取场景节奏

---

#### Level 3：无ASR或ASR失败（兜底）🛡️

**触发条件**：
- 视频无音频轨道
- ASR完全失败（音频损坏、格式不支持等）
- 纯视觉视频

**处理方式**：
- **纯视觉分析模式**
- **场景分割**：完全依赖关键帧视觉差异
- **角色识别**：使用步骤1.5的 `character_detection.json`（InsightFace人脸嵌入聚类，即使换装也能匹配同一角色）
- **叙事线推断**：基于场景变化和动作序列推断

**风险提示**：
- 角色数量可能误判（如之前的7个 vs 实际2个）
- 叙事线可能不准确
- 需要用户确认角色识别结果

**示例场景**：
- 无声视频、动画视频、纯画面展示视频

---

### 自动降级流程

```python
def analyze_with_fallback(video_path):
    """
    带容错的视频分析流程
    """
    # 尝试提取音频
    audio = extract_audio(video_path)
    
    if audio is None:
        # Level 3: 无音频
        return pure_visual_analysis(video_path)
    
    # 尝试ASR
    asr_result = perform_asr(audio)
    
    if asr_result is None or not asr_result["full_text"]:
        # Level 3: ASR失败
        return pure_visual_analysis(video_path)
    
    # 尝试叙事线分析
    narrative = analyze_narrative(asr_result["full_text"])
    
    if narrative["clarity_score"] < 0.5:
        # Level 2: 叙事线不清晰
        return hybrid_analysis(video_path, asr_result, narrative)
    
    # Level 1: 完整流程
    return full_analysis_with_narrative(video_path, asr_result, narrative)
```

**输出标识**：
- 每个分析结果需包含 `analysis_level` 字段（"level_1" / "level_2" / "level_3"）
- Level 2/3 需增加 `confidence_warning` 字段，提示用户验证

---

## 操作步骤

### 阶段1：叙事理解（ASR优先）

#### 步骤1：智能关键帧提取

**执行方式：调用Python脚本**

```bash
python scripts/smart_keyframe_extractor.py \
  --video_path <原视频路径> \
  --output_dir output/keyframes/ \
  --min_fps 2.0
```

**核心功能**：
- **场景切换检测**：识别场景边界（帧间像素差异阈值15%）
- **动作密度分析**：动作密集区域多提取，静态区域适度提取
- **均匀提取兜底**：每秒至少2帧，确保不遗漏重要镜头

**输出**：
- `output/keyframes/*.jpg` - 关键帧图像
- `output/keyframes/extraction_result.json` - 提取结果（场景列表、关键帧列表、视频信息）

---

#### 步骤1.5：角色检测与跨帧聚类

**执行方式：调用Python脚本（InsightFace）**

```bash
python scripts/character_detector.py \
  --keyframes_dir output/keyframes/ \
  --output_path output/analysis/character_detection.json \
  --extraction_result output/keyframes/extraction_result.json \
  --similarity_threshold 0.4
```

**核心功能**：
- **人脸检测**：使用InsightFace (buffalo_l) 检测每帧中的人脸及位置
- **特征提取**：提取512维人脸嵌入向量（ArcFace）
- **跨帧聚类**：余弦相似度贪心聚类（默认阈值0.4），即使换装也能通过人脸特征匹配同一角色
- **角色档案**：生成每个角色的出现帧列表、人脸/身体区域bbox、代表性面部裁切图
- **ASR整合**（可选）：步骤3.5完成后，可带 `--narrative_path` 重新运行以将视觉角色与文本角色名关联

**为什么需要这一步**：
- 纯图像分析中，同一角色换装后会被误判为不同人
- ASR失败时，没有角色检测就只能靠Claude看图猜测
- 人脸嵌入在换装、换场景时仍然稳定，是最可靠的跨帧角色匹配方式

**输出**：
- `output/analysis/character_detection.json` - 角色检测与聚类结果
- `output/analysis/characters/char_N_face.jpg` - 每个角色的代表性面部裁切

**输出示例**：
```json
{
  "total_keyframes_analyzed": 10,
  "total_faces_detected": 15,
  "unique_characters": 2,
  "characters": [
    {
      "character_id": 0,
      "label": "char_0",
      "matched_name": null,
      "appearance_count": 7,
      "keyframe_indices": [0, 2, 3, 5, 6, 8, 9],
      "scene_ids": [0, 1, 2, 3],
      "face_bboxes": {"frame_0000.jpg": [120, 50, 220, 180]},
      "body_bboxes": {"frame_0000.jpg": [80, 50, 260, 440]},
      "representative_face_path": "output/analysis/characters/char_0_face.jpg",
      "avg_det_score": 0.92
    }
  ]
}
```

---

#### 步骤2：色彩与运动分析

**执行方式：调用Python脚本**

```bash
python scripts/video_analyzer.py \
  --video_path <原视频路径> \
  --output_path output/analysis/color_analysis.json
```

**分析内容**：
- **技术规格**：分辨率、帧率、时长、编码格式
- **色彩分布**：RGB均值、HSV特征、亮度、对比度
- **色调识别**：warm_red_orange, warm_yellow, green, cyan, blue, purple等
- **运动特征**：static, slow_movement, normal_movement, dynamic_fast等

**输出**：
- `output/analysis/color_analysis.json` - 色彩分析结果

---

#### 步骤3：ASR语音识别 ⭐ 核心步骤

**执行方式：调用Python脚本（自动提取音频+语音识别）**

```bash
python scripts/asr_transcriber.py \
  --video_path <原视频路径> \
  --output_path output/analysis/asr_result.json \
  --model_size base \
  --language zh \
  --word_level
```

**自动执行流程**：
1. **音频提取**：使用ffmpeg从视频中提取音频轨道（16kHz, mono, WAV格式）
2. **语音识别**：使用Whisper模型将音频转为文本
3. **时间戳提取**：生成段落级和词级时间戳

**⚠️ 重要说明**：
- 如果主session环境无法安装Whisper库，会**自动启动sub-agent session执行**
- sub-agent session有独立环境，可以安装依赖并执行完整流程
- ASR结果返回后，主session继续后续步骤

**分析内容**：
- **语音转文本**：提取完整解说文本
- **时间戳提取**：段落级和词级时间戳（用于音画对齐）
- **叙事内容**：文本中包含的角色、身份、关系、叙事主题

**输出**：
- `output/audio/extracted_audio.wav` - 提取的音频文件
- `output/analysis/asr_result.json` - ASR识别结果

**输出示例**：
```json
{
  "video_path": "原视频.mp4",
  "language": "zh",
  "full_text": "大家好，今天要分享的是...",
  "duration": 45.2,
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 3.5,
      "text": "大家好，今天要分享的是",
      "words": [
        {"word": "大家好", "start": 0.0, "end": 0.8, "confidence": 0.95}
      ]
    }
  ],
  "voice_style": {
    "speed": {"chars_per_second": 3.2, "level": "中等"},
    "pause": {"count": 5, "frequency": 1.1},
    "estimated_tone": "温柔",
    "estimated_emotion": "温暖"
  }
}
```

---

#### 步骤3.5：叙事线分析（基于ASR文本）⭐ 关键步骤

**执行方式：智能体分析ASR文本**

**核心理念**：用ASR文本识别的角色，指导后续的图像验证

**分析内容**：

##### 3.5.1 叙事主题识别
- 从文本识别故事类型（爱情/励志/纪录片/广告等）
- 识别叙事视角（第一人称"我"/第三人称）
- 识别情感基调（温暖/紧张/幽默/治愈等）

##### 3.5.2 角色识别（从文本）
- **主角识别**：文本中明确提到的主角是谁？
- **角色关系**：角色之间是什么关系？（情侣/朋友/家人等）
- **角色身份**：角色的真实身份是什么？（富豪/普通人/企业家等）

##### 3.5.3 叙事弧线
- **起**：故事的开端（0-?秒）
- **承**：故事的发展（?-?秒）
- **转**：故事的转折（?-?秒）
- **合**：故事的结局（?-?秒）

**输出**：
- `output/analysis/narrative_analysis.json` - 叙事线分析结果

**示例输出**：
```json
{
  "narrative_theme": "富豪伪装穷人的爱情故事 + 女主逆袭",
  "narrator": "女主（女性）",
  "characters_from_text": [
    {
      "name": "顧杰森",
      "role": "男主，千亿财团继承人，伪装成普通人",
      "identity": "千亿财团唯一继承人"
    },
    {
      "name": "女主（'我'）",
      "role": "女主，从普通人到女首富",
      "identity": "最终成为女首富"
    }
  ],
  "narrative_arc": {
    "act_1": {"name": "伪装", "time_range": "0-15s"},
    "act_2": {"name": "平凡", "time_range": "15-35s"},
    "act_3": {"name": "逆袭", "time_range": "35-49.5s"}
  }
}
```

**重要**：此步骤完成后，才能进行步骤4的角色视觉验证。

---

#### 步骤4：深度视觉分析（基于叙事线）

**执行方式：智能体调用read_image工具**

**⚠️ 核心要求**：
1. **必须先完成步骤3.5叙事线分析**
2. **必须使用read_image工具检查关键帧内容**
3. **角色识别必须基于叙事线**，而非从头猜测
4. **优先使用步骤1.5的 `character_detection.json`**：该文件包含InsightFace检测到的角色聚类结果（跨帧同一人识别），即使ASR失败也能提供可靠的角色数量和出现帧信息

##### 步骤4.1：基于叙事线分配关键帧

```python
# 读取叙事线分析
with open("output/analysis/narrative_analysis.json") as f:
    narrative = json.load(f)

# 读取ASR时间戳
with open("output/analysis/asr_result.json") as f:
    asr_data = json.load(f)
    segments = asr_data["segments"]

# 根据ASR时间戳和叙事弧线，分配关键帧到对应角色
for segment in segments:
    start_time = segment["start"]
    end_time = segment["end"]
    text = segment["text"]
    
    # 根据文本内容判断这段属于哪个角色
    # 例如："我的男友叫顧杰森" → 男主顧杰森
    #       "我后来成了女首富" → 女主
    
    # 找到对应时间的关键帧
    keyframes_in_range = [kf for kf in keyframes 
                          if start_time <= kf["time"] <= end_time]
```

##### 步骤4.2：用read_image验证角色外貌

```python
# 选择要检查的帧（每个角色的代表性帧）
frames_to_check = []

# 对于每个角色，选择其出现的关键帧
for char in narrative["characters_from_text"]:
    char_frames = get_keyframes_for_character(char, segments, keyframes)
    frames_to_check.extend(char_frames[:5])  # 每个角色最多5帧

# 用read_image检查
result = read_image(frames_to_check)

# 从read_image结果提取角色外貌特征
# 注意：要和叙事线中的角色对应
```

##### 步骤4.3：角色定义表（基于叙事线+视觉验证）

**必须基于叙事线 + read_image结果**

**示例角色定义表：**

| 角色 | 文本识别（叙事线） | 关键帧验证 | 年龄 | 外貌 | 服装 | 出现场景 |
|------|-------------------|-----------|------|------|------|----------|
| 顧杰森 | "我的男友叫顧杰森" | frame_005,010,015 | 25-35岁 | 东亚男性，黑色短发，剑眉星目 | 浅粉衬衫→灰色T恤 | 1-5 |
| 女主 | "我后来成了女首富" | frame_050,070,080 | 25-30岁 | 东亚女性，黑色短发 | 白色T恤→金色礼服 | 5-7 |

**对比：错误做法 vs 正确做法**

| 错误做法 | 正确做法 |
|---------|---------|
| 从图像识别出7个角色 | 从ASR文本识别出2个主角 |
| 每个场景独立分析 | 用ASR时间戳分配场景到角色 |
| 猜测叙事线 | 文本直接说明叙事线 |
| 不知道主角是谁 | 文本明确说明主角 |

**输出**：
- `output/analysis/coherence_analysis.json` - 场景分析 + 角色定义

---

#### 步骤5：音画关联分析（智能体）

**执行方式：智能体基于ASR和视觉分析结果进行分析**

**分析内容**：
- **时间轴映射**：建立音频文本与视频分镜的时间对应关系
- **语义匹配度**：分析解说文本与画面内容的关联性
- **情感一致性**：评估语音情感与画面氛围的一致性

**输出**：
- `output/analysis/audio_visual_correlation.json` - 音画关联分析结果

---

### 阶段2：智能多维提示词生成

#### 步骤6：生成视觉风格提示词

**执行方式：智能体基于步骤1-5的数据生成**

**数据来源**：
- 色彩数据：`output/analysis/color_analysis.json`
- 角色定义：`output/analysis/coherence_analysis.json`

**示例输出**：
```
视觉风格提示词：
电影感，warm_yellow色调，缓慢推拉镜头，流畅转场

场景1提示词：
realistic photo style, live action, 16:9 widescreen, 哈佛校门前，阳光明媚，角色A_哈佛青年（东亚男性，25岁，黑色卷发，粉色衬衫）

场景4提示词：
realistic photo style, live action, 16:9 widescreen, 餐桌旁，角色B_餐桌男性（东亚男性，35岁，短发，米白衬衫）
```

**输出**：
- `output/prompts/visual_style_prompt.txt` - 视觉风格提示词
- `output/prompts/scene_prompts.json` - 每个场景的提示词

**⚠️ `scene_prompts.json` 必须严格遵守以下 JSON schema，步骤8-9的脚本依赖这些字段**：

```json
{
  "global_style": "电影感，warm_yellow色调，缓慢推拉镜头",
  "characters": [
    {
      "id": "char_A",
      "name": "顧杰森",
      "gender": "男性",
      "age": "25-35岁",
      "appearance": "东亚男性，黑色短发，剑眉星目",
      "clothing": "浅粉衬衫→灰色T恤"
    }
  ],
  "character_ref_prompts": [
    {
      "character_id": "char_A",
      "prompt": "插画风格，半身像，干净背景，男性，25-35岁，东亚男性，黑色短发，剑眉星目，穿着浅粉衬衫"
    }
  ],
  "scenes": [
    {
      "scene_id": 1,
      "prompt": "realistic photo style, live action, 16:9 widescreen, 1280x720, 哈佛校门前，阳光明媚，char_A（东亚男性，25岁，黑色短发，浅粉衬衫），自信微笑",
      "duration": 5.2,
      "main_character": "char_A",
      "time_range": "0-5.2s"
    }
  ]
}
```

**字段说明**：
- `characters`：角色定义列表（`id`, `gender`, `age`, `appearance`, `clothing`），用于步骤8自动生成角色参考图
- `character_ref_prompts`：角色参考图的提示词（`character_id` 对应 `characters[].id`，`prompt` 为生成提示词）
- `scenes`：场景列表（`scene_id`, `prompt`, `duration`, `main_character`），用于步骤9生成视频
- `main_character`：值必须对应 `characters[].id`，用于查找角色参考图

---

#### 步骤7：生成TTS复刻指导

**执行方式：智能体基于ASR结果生成**

**数据来源**：
- ASR结果：`output/analysis/asr_result.json`

**TTS复刻参数**：
```json
{
  "tts_parameters": {
    "gender": "女性",
    "tone": "温柔亲切",
    "speed": "中等",
    "emotion": "温暖鼓励",
    "rhythm": "平稳节奏"
  },
  "reference_text": "大家好，今天要分享的是...",
  "duration_target": 45.2
}
```

**输出**：
- `output/prompts/tts_guide.json` - TTS复刻指导

**⚠️ `tts_guide.json` 必须严格遵守以下 JSON schema，步骤10的脚本依赖这些字段**：

```json
{
  "tts_parameters": {
    "gender": "女性",
    "tone": "温柔亲切",
    "speed": "中等",
    "emotion": "温暖鼓励",
    "rhythm": "平稳节奏"
  },
  "reference_text": "大家好，今天要分享的是...",
  "duration_target": 45.2
}
```

**字段说明**：
- `tts_parameters.gender`：性别（男/女），用于 voice 映射
- `tts_parameters.tone`：语调（温柔/激昂/平静），用于 voice 映射
- `tts_parameters.speed`：语速（慢/较慢/中等/较快/快速），用于 rate 调整
- `tts_parameters.emotion`：情感（温暖/严肃/轻松），用于 voice 映射
- `reference_text`：完整解说文本，用于 TTS 输入

---

### 阶段3：风格精准复刻与音画一体化生成

#### 步骤8：生成插画风格角色参考图

**执行方式：调用Python脚本（Seedream API）**

```bash
python scripts/image_generator.py \
  --prompts_json output/prompts/scene_prompts.json \
  --output_dir output/角色参考图/ \
  --config config/api_config.yaml
```

**脚本读取 `scene_prompts.json` 中的 `character_ref_prompts` 或 `characters` 列表，调用 volcengine Seedream API 生成插画风格半身像。**

**配置要求**：
- `config/api_config.yaml` 中配置 `models.image`（provider: volcengine）
- API 密钥通过 `config/api_keys.yaml` 或环境变量 `VOLCENGINE_API_KEY` 设置

**输出**：
- `output/角色参考图/*.jpg` - 每个角色的插画风格半身像
- `output/角色参考图/refs_manifest.json` - 参考图清单

---

#### 步骤9：生成视频片段

**执行方式：调用Python脚本（Seedance 2.0 API）**

```bash
python scripts/video_generator.py \
  --prompts_json output/prompts/scene_prompts.json \
  --refs_dir output/角色参考图/ \
  --output_dir output/videos/ \
  --config config/api_config.yaml \
  --parallel 1
```

**脚本为每个场景：**
1. 查找该场景主角的参考图（从 refs_manifest.json）
2. 构建带 `@图片N` 调用语句的提示词
3. 调用 Seedance 2.0 API 提交任务 → 轮询 → 下载视频
4. 支持最多 9 张参考图（角色+构图+风格等）

**强制参数**（由 config 控制）：
- **ratio**: 16:9
- **resolution**: 720p
- **duration**: 4-15秒（与原视频场景时长一致，自动 clamp）
- **max_reference_images**: 9

**断点续传**：已存在的 scene_*.mp4 自动跳过。

**输出**：
- `output/videos/scene_*.mp4` - 每个场景的视频片段
- `output/videos/videos_manifest.json` - 视频清单

---

#### 步骤10：生成TTS配音

**执行方式：调用Python脚本（edge_tts）**

```bash
python scripts/tts_generator.py \
  --text "<解说文本>" \
  --output_path output/audio/tts_narration.wav \
  --tone "温柔" \
  --speed "中等" \
  --emotion "温暖" \
  --service edge_tts
```

**支持的服务**：
- **edge_tts**（默认，免费）：微软 Edge TTS，支持中文多音色
- **custom**：自定义 TTS API（通过 `--custom_api_url` 指定）
- **sine**：正弦波兜底（仅调试用）

**Voice 映射**（tone + emotion → voice）：
| 语调+情感 | edge_tts voice |
|-----------|---------------|
| 温暖/女性 | zh-CN-XiaoxiaoNeural |
| 平静/中性 | zh-CN-XiaoyiNeural |
| 激昂/男性 | zh-CN-YunxiNeural |

可通过 `--voice` 直接指定 voice 名称覆盖自动映射。

**输出**：
- `output/audio/tts_narration.wav` - TTS配音音频
- `output/audio/tts_narration_tts_result.json` - TTS参数记录

---

#### 步骤11：音视频合成

**执行方式：调用Python脚本**

```bash
# 11a 拼接场景视频
python scripts/scene_concat.py \
  --video_dir output/videos/ \
  --output_path output/videos/merged_video.mp4 \
  --order_json output/prompts/scene_prompts.json

# 11b 合成音视频（使用ASR时间戳精确对齐）
python scripts/audio_video_mixer.py \
  --video_path output/videos/merged_video.mp4 \
  --audio_path output/audio/tts_narration.wav \
  --output_path output/复刻视频.mp4 \
  --asr_json output/analysis/asr_result.json
```

**输出**：
- `output/复刻视频.mp4` - 最终视频

---

## 📋 完整步骤总结

| 阶段 | 步骤 | 内容 | 执行方式 | 输出 |
|------|------|------|----------|------|
| 阶段1 | 步骤1 | 智能关键帧提取 | Python脚本 | keyframes/ |
| 阶段1 | 步骤1.5 | 角色检测与跨帧聚类 | Python脚本（InsightFace） | character_detection.json |
| 阶段1 | 步骤2 | 色彩与运动分析 | Python脚本 | color_analysis.json |
| 阶段1 | 步骤3 | ASR语音识别 ⭐ | Python脚本 | asr_result.json |
| 阶段2 | 步骤3.5 | 叙事线分析 ⭐ | Claude分析 | narrative_analysis.json |
| 阶段2 | 步骤4 | 深度视觉分析（基于叙事线）⭐ | Claude+Read工具 | coherence_analysis.json |
| 阶段2 | 步骤5 | 音画关联分析 | Claude分析 | audio_visual_correlation.json |
| 阶段2 | 步骤6 | 生成视觉提示词 | Claude生成 | scene_prompts.json |
| 阶段2 | 步骤7 | 生成TTS指导 | Claude生成 | tts_guide.json |
| 阶段3 | 步骤8 | 生成角色参考图 | Python脚本（Seedream API） | 角色参考图/ |
| 阶段3 | 步骤9 | 生成视频片段 | Python脚本（Seedance 2.0 API） | videos/scene_*.mp4 |
| 阶段3 | 步骤10 | 生成TTS配音 | Python脚本（edge_tts） | tts_narration.wav |
| 阶段3 | 步骤11 | 音视频合成 | Python脚本 | 复刻视频.mp4 |

---

## 数据流完整链路

```
原视频.mp4
    │
    ├─→ [步骤1] smart_keyframe_extractor.py → keyframes/*.jpg
    ├─→ [步骤1.5] character_detector.py → character_detection.json + characters/*.jpg
    ├─→ [步骤2] video_analyzer.py → color_analysis.json
    └─→ [步骤3] asr_transcriber.py
            ├─→ extracted_audio.wav
            └─→ asr_result.json
                    │
                    ↓
            [步骤3.5] Claude分析 → narrative_analysis.json
                    │
                    ↓
    [步骤4] Claude Read(keyframes) + 叙事线 → coherence_analysis.json

    ↓

[步骤5] Claude分析 → audio_visual_correlation.json

    ↓

[步骤6-7] Claude生成提示词
    ├─→ scene_prompts.json（视觉风格+场景提示词+角色参考图提示词）
    └─→ tts_guide.json（TTS参数+文本）

    ↓

[步骤8] image_generator.py（Seedream API）→ 角色参考图/*.jpg

    ↓

[步骤9] video_generator.py（Seedance 2.0 API + 角色参考图）→ videos/scene_*.mp4

    ↓

[步骤10] tts_generator.py（edge_tts）→ tts_narration.wav

    ↓

[步骤11a] scene_concat.py → merged_video.mp4
[步骤11b] audio_video_mixer.py → 复刻视频.mp4
```

---

## 注意事项

### 1. ASR优先原则 ⭐ 最重要
- **永远先执行ASR**，再进行角色识别
- **文本理解 > 图像理解**
- ASR结果**指导**整个后续流程（叙事线、角色识别、音画对齐）
- 不要跳过ASR直接分析图像，会导致角色识别错误

### 2. 调度模式
- **本 Skill 是调度核心**：Claude 读取 SKILL.md 后按步骤执行全部流程
- **步骤1-3**：Claude 调用 Python 脚本（`perfect_replication_workflow.py` 或单独脚本）
- **步骤3.5-7**：Claude 直接执行（分析 ASR 文本、查看关键帧、生成提示词）
- **步骤8-9**：Claude 调用 Python 脚本（`image_generator.py`、`video_generator.py`，通过 API 生成）
- **步骤10-11**：Claude 调用 Python 脚本（`tts_generator.py`、`scene_concat.py`、`audio_video_mixer.py`）
- **API 配置**：`config/api_config.yaml` 定义 provider，`config/api_keys.yaml` 存放密钥（或用环境变量）

### 3. 角色识别流程
1. 步骤1.5自动检测人脸并聚类（`character_detection.json`）
2. 从ASR文本识别角色（名字、身份、关系）
3. 从ASR时间戳分配关键帧到角色
4. 用read_image验证角色外貌
5. 生成最终角色定义表

### 4. 角色 ID 命名规范 ⭐ 重要
- 步骤1.5输出的角色 label（如 `char_0`, `char_1`）是**全管线统一的角色 ID**
- 步骤6生成 `scene_prompts.json` 时，`characters[].id` 和 `scenes[].main_character` **必须使用相同的 ID**
- 步骤8生成参考图时，文件名为 `{character_id}.jpg`
- 步骤9查找参考图时，用 `main_character` 值匹配参考图文件名
- **如果 ID 不一致，步骤9将找不到参考图，生成的视频质量会严重下降**

### 5. 步骤依赖关系
- 步骤1-3可并行执行（或调用 `perfect_replication_workflow.py` 一次性完成，含步骤1.5）
- **步骤3.5必须在步骤4之前**（叙事线指导角色识别）
- 步骤4必须用 Read 工具查看关键帧图片
- 步骤6生成提示词时必须引用步骤2的色彩分析和步骤3.5的叙事线
- **步骤6-7生成的 JSON 必须通过 Schema 校验**（`scripts/schema_validator.py`），步骤8-9入口会自动校验
- 步骤8-11依赖步骤6-7生成的提示词文件
- 步骤8-9需要 API 密钥已配置（`config/api_keys.yaml` 或环境变量 `VOLCENGINE_API_KEY`）

### 6. JSON 模板与 Schema 校验
- 步骤3.5-7的每个 JSON 输出都有标准模板，位于 `assets/schema_templates/`
- 生成 JSON 时应参考模板中的字段定义，确保不遗漏必需字段
- `scripts/schema_validator.py` 可独立运行校验任意中间文件：
  ```bash
  python scripts/schema_validator.py --file output/prompts/scene_prompts.json --type scene_prompts
  ```
- 步骤8（`image_generator.py`）和步骤9（`video_generator.py`）入口已集成自动校验，缺字段时会报明确错误

### 7. 其他注意事项
- 角色定义必须一致：同一个角色在所有场景使用完全相同的描述
- 强制16:9比例：所有视频片段必须1280x720
- Whisper依赖：步骤3需要安装openai-whisper包（或使用sub-agent）

### 8. 真人出镜提示词 ⭐ 强制要求

**所有场景提示词必须以以下内容开头**：
```
realistic photo style, live action, 16:9 widescreen, 1280x720,
```

**关键词说明**：
- **`realistic photo style`**：确保真人实拍风格，避免动画化
- **`live action`**：明确真人实拍，非卡通/插画风格

**为什么必须**：
1. **风格统一**：确保所有场景保持一致的真人实拍风格
2. **避免误生成**：防止AI生成卡通、插画或动画风格视频
3. **电影质感**：保持写实电影感，提升视频质量

**错误示例**（❌ 不可省略）：
```
哈佛校门前，阳光明媚，角色A_哈佛青年...
```

**正确示例**（✅ 必须包含）：
```
realistic photo style, live action, 16:9 widescreen, 1280x720,
哈佛校门前，阳光明媚，角色A_哈佛青年...
```

**步骤6生成提示词时必须检查**：每个场景提示词是否以这两个关键词开头。

---

## 资源索引

### 核心脚本
- 智能关键帧提取: scripts/smart_keyframe_extractor.py
- 角色检测与聚类: scripts/character_detector.py（步骤1.5，InsightFace人脸嵌入聚类）
- 视频色彩分析: scripts/video_analyzer.py
- ASR语音识别: scripts/asr_transcriber.py
- API客户端: scripts/api_client.py（凭证加载、Seedance/Seedream封装）
- 角色参考图生成: scripts/image_generator.py（步骤8，Seedream API）
- 场景视频生成: scripts/video_generator.py（步骤9，Seedance 2.0 API）
- TTS生成: scripts/tts_generator.py（步骤10，edge_tts优先+可切换）
- 视频拼接: scripts/scene_concat.py（步骤11a，ffmpeg）
- 音视频合成: scripts/audio_video_mixer.py（步骤11b）
- JSON Schema 校验: scripts/schema_validator.py（校验步骤3.5-7的中间JSON）
- 完整工作流: scripts/perfect_replication_workflow.py（步骤1-11完整管线）

### JSON 模板（步骤3.5-7输出标准格式）
- 叙事线分析: assets/schema_templates/narrative_analysis_template.json
- 深度视觉分析: assets/schema_templates/coherence_analysis_template.json
- 音画关联分析: assets/schema_templates/audio_visual_correlation_template.json
- 场景提示词: assets/schema_templates/scene_prompts_template.json
- TTS复刻指导: assets/schema_templates/tts_guide_template.json

### 配置文件
- API配置: config/api_config.yaml
- API密钥示例: config/api_keys.yaml.example（复制为 api_keys.yaml 填入密钥）

### 参考资料
- ASR输出格式: references/asr_output_format.md
- 提示词模板: references/prompt_templates.md
- 风格分类: references/style_categories.md
