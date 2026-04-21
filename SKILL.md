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

### ⭐ 多层视频语义分析：先粗判，再抽丝剥茧

**这套 Skill 不应该一上来就把视频压缩成一句 prompt。**

无论有没有 ASR，都必须先完成一个**逐层收敛**的分析过程：先判断视频属于什么内容机制，再判断画面里发生了什么，再抽取能帮助进一步判定的证据，最后才生成复刻约束。

**强制顺序：**
1. **媒体基线**：分辨率、横竖屏、时长、帧率、是否有音轨、是否有 OCR/字幕
2. **内容粗分类**：剧情 / 口播 / 纪录 / 教程 / 表演 / 训练 / 商品展示 / 氛围片
3. **场景语义骨架**：地点类型、空间结构、人数规模、主体组织方式、光线与环境
4. **主体与行为分析**：谁在画面里、在做什么、动作是同步还是对抗、是训练还是表演
5. **判别性证据提取**：服装、鞋子、道具、器材、文字、标识、屏幕内容
6. **子类收敛与复刻约束**：把“像运动”继续收敛到“训练 / 表演 / 比赛 / 排练”等，再写 prompt 和负约束

**原则**：
- 不允许从“多人 + 室内”直接跳成“多人活动现场”
- 不允许从“像跳舞”直接停住，必须继续检查动作、队形、服装、鞋子、文字、道具
- 先写**事实层**，再写**解释层**，最后才写**生成层**
- 每一层都要回答：`我看到了什么`、`这说明什么`、`还缺什么证据`

### 语义分析 6 层 16 维（通用）

#### Layer 0：媒体基线
- `媒体规格`：分辨率、比例、横竖屏、时长、帧率、清晰度
- `音频角色`：无人声 / 解说 / 对话 / 环境音 / 音乐主导 / 混合

#### Layer 1：内容机制判断
- `内容类型`：剧情、纪实、教程、舞台、训练、广告、旅行、产品、纯氛围
- `叙事驱动力`：ASR 驱动、视觉驱动、字幕驱动、音乐驱动，或混合驱动

#### Layer 2：场景语义骨架
- `地点与空间`：室内/室外、建筑类型、空间用途、景深与站位关系
- `时间与光线`：白天/夜晚、自然光/人工光、冷暖、硬光/漫射
- `主体规模`：单人、双人、小群体、大型群像
- `主体组织关系`：对话、协作、对抗、列队、围观、表演、教学

#### Layer 3：主体与行为
- `核心行为`：走、跑、跳、练、演、讲、做、展示、互动、操作
- `动作结构`：静态、重复动作、连续动作链、强爆发动作、同步动作
- `外观线索`：年龄段、性别倾向、服装类别、制服程度、发型、妆造

#### Layer 4：判别性证据
- `道具/器材/鞋服细节`：最能帮助子类判断的具体物件或穿着细节
- `文字与符号线索`：字幕、招牌、屏幕 UI、墙面文字、衣物印字、徽标

#### Layer 5：生成约束
- `构图与摄影`：景别、机位、构图、运镜、节奏
- `风格与氛围`：色调、质感、真实度、年代感、文化风格、情绪气候
- `复刻硬约束`：哪些必须保留，哪些不能错，哪些允许近似

**示例（抽象方法，不是写死舞蹈模板）**：
- 粗分类：室内多人同步活动
- 行为判断：重复抬步、队列训练、节奏一致
- 证据提取：统一服装、分趾舞鞋、木地板、墙面文字
- 子类收敛：群体基础舞步训练 / 民俗舞排练，而不是泛化成“多人运动”

### ⭐ ASR优先 + 分级容错机制

**关键洞察**：ASR语音识别不仅仅是"语音转文字"，更是**理解视频叙事的关键步骤**。

**对比**：
| 方法 | 只看图像 | 图像+ASR |
|------|----------|----------|
| 角色数量 | 可能误判（如数出7个） | 准确（如实际2个） |
| 主角识别 | 不确定 | 立刻知道 |
| 叙事线 | 需要猜测 | 文本直接说明 |
| 角色关系 | 不清楚 | 明确 |

**因此**：当 ASR 有效时，ASR结果**指导**角色识别和叙事理解；但它不替代视觉语义分析，更不能跳过“粗分类 → 证据提取 → 子类收敛”。

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

**示例**：完整剧情类短视频（含明确角色关系与叙事线）

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
- **逐层视觉语义分析**：按“内容粗分类 → 主体行为 → 证据提取 → 子类判定 → 生成约束”执行
- **叙事线推断**：基于场景变化和动作序列推断，而不是直接猜主题

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

**人数字段的正确理解**：
- `unique_characters` = **跨帧人脸聚类数**，它表示底层检测里聚成了多少张“可能是不同人”的脸，**不能直接当成现场人数**
- `frame_visible_people` = 对步骤1提取出的每张关键帧做一次 `单帧可见人数估计`
- `visible_people_stats.stable_visible_people_estimate` = 复刻链路默认使用的 **稳定可见人数估计**
- `scene_visible_people_stats` = 每个场景的人数统计，后续判断主体规模、群像策略、prompt 人数关系时优先用它

**输出示例**：
```json
{
  "total_keyframes_analyzed": 10,
  "total_faces_detected": 15,
  "unique_characters": 2,
  "visible_people_stats": {
    "stable_visible_people_estimate": 2,
    "min_visible_people": 1,
    "max_visible_people": 2
  },
  "scene_visible_people_stats": [
    {
      "scene_id": 0,
      "time_range": "0.0-5.0s",
      "stable_visible_people_estimate": 2
    }
  ],
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

#### 步骤3.5：叙事线分析 + 内容粗分类 ⭐ 关键步骤

**执行方式：审核初稿 + 智能体补充**

> **初稿已自动生成**：`output/analysis/narrative_analysis.json` 由 `draft_generator.py` 在阶段1结束时自动生成，包含从ASR文本提取的人名和按时间三等分的叙事弧线骨架。Claude 只需阅读 ASR 文本后，补充所有 `[TODO]` 占位符。

**核心理念**：先判断这条视频是“什么类型的内容”，再用 ASR 文本识别角色和叙事线，指导后续图像验证。

**分析内容**：

##### 3.5.1 内容粗分类（必须先做）
- 判断视频属于：剧情 / 口播 / 纪录 / 教程 / 表演 / 训练 / 商品展示 / 纯氛围
- 判断当前视频的主导理解方式：ASR 驱动 / 视觉驱动 / 字幕驱动 / 音乐驱动
- 如果 ASR 文本很弱，只把它当辅助信号，不允许强行编造完整剧情

##### 3.5.2 叙事主题识别
- 从文本识别故事类型（爱情/励志/纪录片/广告等）
- 识别叙事视角（第一人称"我"/第三人称）
- 识别情感基调（温暖/紧张/幽默/治愈等）

##### 3.5.3 角色识别（从文本）
- **主角识别**：文本中明确提到的主角是谁？
- **角色关系**：角色之间是什么关系？（情侣/朋友/家人等）
- **角色身份**：角色的真实身份是什么？（富豪/普通人/企业家等）

##### 3.5.4 叙事弧线
- **起**：故事的开端（0-?秒）
- **承**：故事的发展（?-?秒）
- **转**：故事的转折（?-?秒）
- **合**：故事的结局（?-?秒）

**输出**：
- `output/analysis/narrative_analysis.json` - 叙事线分析结果

**示例输出**（中性占位示例，仅演示结构）：
```json
{
  "narrative_theme": "都市人物关系变化故事",
  "narrator": "第一人称主角（女性）",
  "characters_from_text": [
    {
      "name": "角色甲",
      "role": "主要对手戏角色，表面身份普通",
      "identity": "隐藏真实背景"
    },
    {
      "name": "叙述者（我）",
      "role": "第一人称主角",
      "identity": "故事推动者"
    }
  ],
  "narrative_arc": {
    "act_1": {"name": "建立关系", "time_range": "0-15s"},
    "act_2": {"name": "冲突发展", "time_range": "15-35s"},
    "act_3": {"name": "结果揭示", "time_range": "35-49.5s"}
  }
}
```

**重要**：此步骤完成后，应先完善步骤3.6的 `semantic_analysis.json`，再进行步骤4的角色视觉验证。

---

#### 步骤3.6：6棱镜语义分析骨架（逐层收敛）

**执行方式：审核初稿 + 智能体补全行为、证据、子类判断**

> **初稿已自动生成**：`output/analysis/semantic_analysis.json` 已自动写入媒体基线，并为每个场景生成 6 棱镜骨架。Claude 应优先完善这个文件，再进入步骤4-6。

**核心理念**：这一步不是单纯写分析报告，而是要产出**复刻主脑**。先用固定提问框架把视频看清楚，再把分析结论直接写成后续步骤必须继承的统一生成约束。

**6棱镜固定提问框架**：
- `narrative_prism`：这段在讲什么？这镜只完成什么？当前属于什么内容类型？允许 `unknown`
- `subject_prism`：谁是主体？人数规模如何？主体之间是什么关系？谁必须出现？
- `action_prism`：主体在做什么？动作是静态、重复、同步还是连续动作链？
- `scene_prism`：空间是什么？灯光如何？有哪些服装、鞋子、道具、文字、环境证据？
- `camera_prism`：这镜怎么拍？景别、角度、运镜、镜头关注点是什么？
- `constraint_prism`：哪些事实必须保留？哪些可以近似？哪些绝不能生成错？

**这一步还必须把 4 类高价值判断单独结构化**：
- **本体 / 子类判断**：不能只写“训练 / 表演 / 活动”这种大类，必须继续收敛到更细层；写进 `narrative_prism.subtype_judgment`
- **行为判断**：不能只写“在运动 / 在跳舞”，必须说明主体到底在做什么、凭什么这么判断；写进 `action_prism.behavior_judgment`
- **证据链**：不能只把鞋子、文字、道具零散记下来，必须组织成“直接证据 / 辅助证据 / 反例假设 / 未决点”；写进 `scene_prism.evidence_chain`
- **负约束**：不能只散落在描述里，必须把最容易生成错的高风险事实单列；写进 `constraint_prism.negative_constraints`

**必须完成的内容**：
- **媒体基线**：确认分辨率、比例、时长、音频模式、主导理解方式
- **6棱镜补全**：每个 scene 都必须补全 `narrative_prism / subject_prism / action_prism / scene_prism / camera_prism / constraint_prism`
- **统一生成契约 / `generation_contract`**：在步骤3.6就先锁定整项目最终视频形态与参考图策略。后面步骤8和步骤9只能继承，不能再各自决定
- **统一风格模板 / `style_consistency`**：它不是独立脑子，而是对 `generation_contract` 的展开描述。后面步骤8和步骤9必须直接继承，不允许各自发挥
- **开放世界判断**：如果不确定具体类别，允许 `label_status = unknown`，但不允许跳过行为、证据、约束
- **证据驱动复刻**：即使无法精确命名，也必须把服装、鞋子、道具、文字、环境、动作组织方式写清楚
- **负约束整理**：把“不能生成错”的点写进 `constraint_prism`
- **禁止只看见不穿透**：看到鞋子、文字、队形、动作还不够，必须把它们变成后续 prompt 会消费的结构化字段

**`generation_contract` + `style_consistency` 至少必须回答这些点**：
- 原视频本体是什么形态：`live_action / stylized_live_action / anime`
- 这个项目最终统一生成成什么形态：只能选一种
- 如果模型能力不足，是否允许整项目统一降级；如果允许，只能整项目一起降，不能局部乱降
- 角色参考图必须是什么形态：直接同形态，还是在 `source_visual_mode` 明确为真人时统一走 `pseudo_realistic_human_illustration` 这类写实人物插画桥接方案
- 场景视频必须是什么形态：它必须与 `target_visual_mode` 一致，不能被参考图介质带偏
- 角色参考图的背景规则和构图规则是什么
- 多人场景要给哪些 `visible_characters` 提供身份锚点，哪些核心角色还要补 `full_body_outfit`
- 服装材质和颜色语言如何统一
- 哪些一致性必须保持，哪些偏离明确禁止
- 哪些关键词必须出现，哪些关键词绝对不能混用

**原则**：
- 生成形态不是步骤8或步骤9临时决定，而是步骤3.6先锁定的项目级结论
- `generation_contract` 和 `style_consistency` 一起构成复刻主脑
- 后面每次生角色图、每次生场景，都必须携带同一份 `generation_contract` + `style_consistency`
- 角色之间只允许改“发型 / 脸型 / 灰裤黑裤 / 站位气质”这类差异点，不能改整体形态和项目统一画法
- 多人队列如果不补 `visible_characters` 和全身服装锚点，步骤9很容易出现整队同脸和主角换衣，这必须在步骤6先避免

**输出**：
- `output/analysis/semantic_analysis.json` - 6棱镜语义分析骨架

**重要**：
- 如果 `semantic_analysis.json` 还没补完整，不要急着写 `scene_prompts.json`
- 固定的是问题结构，不是分类答案
- `final_label` 可以是 `unknown`
- crowd mode 只影响参考图策略，不等于“活动现场”语义结论

---

#### 步骤4：深度视觉分析（主体行为 + 证据提取）

**执行方式：审核初稿 + 智能体用 read_image 验证**

> **初稿已自动生成**：`output/analysis/coherence_analysis.json` 包含从 character_detection.json 映射的角色骨架。Claude 需要用 read_image 查看关键帧和角色代表面部，填写外貌描述，并补充“主体在做什么、为什么这样判断、还有哪些证据支撑”。

**⚠️ 核心要求**：
1. **必须先完成步骤3.5叙事线分析**
2. **必须先完成步骤3.6语义骨架**
3. **必须使用read_image工具检查关键帧内容**
4. **角色识别必须基于叙事线**，而非从头猜测
5. **优先使用步骤1.5的 `character_detection.json`**：该文件包含跨帧角色聚类、单帧可见人数、场景人数统计。**人数判断先看 `visible_people_stats` / `scene_visible_people_stats`，不要直接拿 `unique_characters` 当现场人数**

##### 步骤4.1：基于叙事线与场景分配关键帧

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
    # 例如："我第一次见到角色甲" → 角色甲
    #       "那时我才明白真相" → 叙述者（我）
    
    # 找到对应时间的关键帧
    keyframes_in_range = [kf for kf in keyframes 
                          if start_time <= kf["time"] <= end_time]
```

##### 步骤4.2：用 read_image 做主体行为判断

除了看“是谁”，还必须回答：
- 画面主体是单人、双人、小群体还是大型群像
- 主体组织方式是什么：对话 / 围观 / 列队 / 协作 / 对抗 / 表演 / 教学
- 当前主行为是什么：走、讲、练、演、展示、操作、互动
- 动作结构是什么：静态、重复动作、同步动作、连续动作链、爆发动作

##### 步骤4.3：用 read_image 提取判别性证据

必须主动检查以下证据，而不是只写“看起来像”：
- 服装：是否统一、是否有制服特征、颜色层次、功能性
- 鞋子：运动鞋、皮鞋、舞鞋、工鞋、裸足等
- 道具/器材：球拍、乐器、厨具、工具、训练器材、交通工具等
- 文字与标识：墙面文字、屏幕 UI、标牌、衣服印字、字幕
- 环境细节：地板材质、舞台/教室/车间/球场/厨房等空间特征

##### 步骤4.4：用read_image验证角色外貌

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

##### 步骤4.5：角色定义表（基于叙事线+视觉验证）

**必须基于叙事线 + read_image结果**

**示例角色定义表（中性占位示例）**：

| 角色 | 文本识别（叙事线） | 关键帧验证 | 年龄 | 外貌 | 服装 | 出现场景 |
|------|-------------------|-----------|------|------|------|----------|
| 角色甲 | "我第一次见到角色甲" | frame_005,010,015 | 25-35岁 | 东亚男性，黑色短发，五官立体 | 浅色衬衫→深色外套 | 1-5 |
| 叙述者 | "那时我才明白真相" | frame_050,070,080 | 25-30岁 | 东亚女性，黑色短发 | 白色上衣→正式礼服 | 5-7 |

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

#### 步骤5：音画关联分析 + 子类判定（智能体）

**执行方式：审核初稿 + 智能体补充语义评分**

> **初稿已自动生成**：`output/analysis/audio_visual_correlation.json` 包含 ASR 文本与场景时间的自动映射。Claude 需要补充语义匹配、情感一致性评分，并完成“从粗分类到子类”的最终收敛判断。

**分析内容**：
- **时间轴映射**：建立音频文本与视频分镜的时间对应关系
- **语义匹配度**：分析解说文本与画面内容的关联性
- **情感一致性**：评估语音情感与画面氛围的一致性
- **子类判定**：例如把“运动”继续收敛到“训练 / 比赛 / 表演”，把“多人活动”继续收敛到“列队训练 / 课堂练习 / 舞台演出 / 现场活动”
- **负约束整理**：明确哪些内容不能被生成错，例如人数关系、队形、服装类型、关键道具、鞋型、文字信息

**输出**：
- `output/analysis/audio_visual_correlation.json` - 音画关联分析结果

---

### 阶段2：智能多维提示词生成

#### 步骤6：生成视觉风格提示词

**执行方式：审核初稿 + 智能体补充场景描述和角色外貌**

> **初稿已自动生成**：`output/prompts/scene_prompts.json` 包含从 character_detection 映射的角色列表、从场景数据推导的场景骨架（scene_id/duration/main_character 已填充）、从色彩分析推导的 visual_style_prompt、以及 `realistic photo style` 提示词前缀。Claude 需要把步骤3.5-5得到的“内容类型、行为、证据、子类判定、负约束”真正落实到 prompt，而不是只补几个形容词。

**数据来源**：
- 色彩数据：`output/analysis/color_analysis.json`
- 角色定义：`output/analysis/coherence_analysis.json`
- 内容粗分类 / 子类判定：步骤3.5、步骤3.6与步骤5的结论

**写 prompt 前必须先写清 4 件事**：
1. 这是什么类型的视频内容
2. 当前场景里主体在做什么
3. 哪些证据决定了这个判断
4. 哪些视觉事实绝不能生成错

**还必须继承步骤3.6的复刻主脑**：
- `scene_prompts.json` 必须同时携带 `generation_contract` 和 `style_consistency`
- 步骤8生成角色参考图时，先读 `generation_contract.character_reference_mode`，再套用 `style_consistency`
- 步骤9生成场景视频时，也必须先读同一份 `generation_contract.scene_generation_mode`，再套用 `style_consistency`
- 多人场景必须在 `scenes[]` 里补 `visible_characters`，不能只写 `main_character`
- 每个 `scene` 必须带 `semantic_anchor`，把步骤3.6的**内容类型 / 子类判断 / 行为摘要 / 关键证据 / 负约束**直接挂到生成层
- 核心角色的 `character_ref_prompts` 不能只有胸像身份图；至少主角色和关键服装角色要补 `full_body_outfit`
- 如果出现风格不一致，优先回头修步骤3.6，不要只在某一张图或某一段视频上临时打补丁

**Prompt 组成顺序建议**：
1. 与 `target_visual_mode` 一致的统一前缀 + 原视频尺寸比例
2. 场景与空间骨架
3. 主体规模与组织关系
4. 语义锚点（内容类型 + 子类判断 + 行为摘要）
5. 判别性证据（服装 / 鞋子 / 道具 / 文字 / 环境）
6. 光线与色调
7. 负约束（避免把训练生成成演出、避免把制服生成错、避免把群像生成成散乱路人）

**示例输出**（中性占位示例，仅演示结构）：
```
视觉风格提示词：
电影感，warm_yellow色调，缓慢推拉镜头，流畅转场

场景1提示词：
[按 target_visual_mode 填写统一前缀], 9:16 vertical, 540x960, 校园入口外景，日间自然光，角色甲（东亚男性，25岁，黑色短发，浅色衬衫）

场景4提示词：
[按 target_visual_mode 填写统一前缀], 9:16 vertical, 540x960, 室内餐桌场景，暖色灯光，角色乙（东亚男性，35岁，短发，米白衬衫）
```

**输出**：
- `output/prompts/visual_style_prompt.txt` - 视觉风格提示词
- `output/prompts/scene_prompts.json` - 每个场景的提示词

**⚠️ `scene_prompts.json` 必须严格遵守以下 JSON schema，步骤8-9的脚本依赖这些字段**：

```json
{
  "global_style": "电影感，warm_yellow色调，缓慢推拉镜头",
  "generation_contract": {
    "source_visual_mode": "live_action",
    "target_visual_mode": "live_action",
    "mode_lock_reason": "原视频是真人，最终视频仍统一保持真人出镜；但平台对真人参考图有限制，因此步骤8统一使用写实人物插画参考图桥接",
    "fallback_policy": "如果模型能力不足，只允许整项目统一降级，不允许局部混用",
    "character_reference_mode": "pseudo_realistic_human_illustration",
    "scene_generation_mode": "live_action",
    "required_keywords": ["live action", "realistic photo style", "真人出镜"],
    "forbidden_keywords": ["anime", "illustration", "角色设定图", "live action 与动漫词混用"],
    "consistency_rules": [
      "步骤8和步骤9都必须服从同一份 generation_contract",
      "scene_generation_mode 必须与 target_visual_mode 一致",
      "如果 character_reference_mode 与 target_visual_mode 不同，只允许整项目统一采用写实人物插画桥接方案，且 source_visual_mode 必须是真人"
    ]
  },
  "style_consistency": {
    "style_family": "统一项目风格名称",
    "character_render_mode": "角色参考图必须完全服从 character_reference_mode；真人项目走桥接时，也必须是写实人物插画参考图，并保持真人比例、真实皮肤明暗和布料褶皱",
    "scene_render_mode": "场景视频必须完全服从 scene_generation_mode，不能被参考图介质带偏",
    "lighting_rule": "统一光线逻辑",
    "palette_rule": "统一主色倾向和服装配色",
    "background_rule": "角色参考图必须单人、纯净浅色背景、不带第二个人",
    "framing_rule": "角色参考图默认平视胸像；核心角色还要补全身服装锚点图",
    "costume_rule": "服装材质、颜色、版型沿用原视频",
    "character_prompt_block": "步骤8每次生角色图都必须先读取 character_reference_mode；只有 source_visual_mode 为真人时，才能走写实人物插画桥接；多人场景至少给核心角色补 identity_portrait + full_body_outfit",
    "scene_prompt_block": "步骤9每次生场景都必须先读取 scene_generation_mode；输入参考图只锁定身份、发型、服装和鞋子，最终画面仍必须服从 scene_generation_mode；多人场景必须用 main_character + visible_characters 的多张参考图防止同脸",
    "must_keep": ["scene_generation_mode 与 target_visual_mode 一致", "多人场景的人脸和发型必须分开", "核心角色的裤型和鞋型必须稳定"],
    "negative_constraints": ["角色参考图不要画成漫画脸、二次元大眼或赛璐璐阴影", "不要只喂一张参考图去生成多人场景", "不要局部换风格"]
  },
  "video_generation": {
    "source_resolution": "540x960",
    "source_aspect_ratio": "9:16",
    "target_resolution": "540x960",
    "provider_ratio": "9:16",
    "provider_resolution": "720p",
    "prompt_prefix": "[按 target_visual_mode 填写统一前缀], 9:16 vertical, 540x960"
  },
  "characters": [
    {
      "id": "char_0",
      "name": "角色甲",
      "gender": "男性",
      "age": "25-35岁",
      "appearance": "东亚男性，黑色短发，五官立体",
      "clothing": "浅色衬衫→深色外套"
    }
  ],
  "character_ref_prompts": [
    {
      "character_id": "char_0",
      "reference_type": "identity_portrait",
      "prompt": "先读取 character_reference_mode，再按唯一目标形态写身份参考图提示词，锁定脸型和发型"
    },
    {
      "character_id": "char_0",
      "reference_type": "full_body_outfit",
      "prompt": "先读取 character_reference_mode，再按唯一目标形态写全身服装锚点提示词，锁定长裤和鞋子"
    }
  ],
  "scenes": [
    {
      "scene_id": 1,
      "prompt": "[按 target_visual_mode 填写统一前缀], 9:16 vertical, 540x960, 校园入口外景，日间自然光，char_0（东亚男性，25岁，黑色短发，浅色衬衫），自然站立",
      "duration": 5.2,
      "main_character": "char_0",
      "visible_characters": ["char_0", "char_1", "char_2"],
      "semantic_anchor": {
        "content_type": "训练 / 表演 / 仪式 / 课堂 / 比赛 / 商品展示 / 剧情 / unknown",
        "subtype_judgment": "更细的子类判断，如：女子舞踊基础练习 / 课堂示范 / 队列排练",
        "behavior_summary": "一句话说明主体到底在做什么，不能只写抽象词",
        "evidence_to_preserve": ["必须在生成中保留的证据，如鞋型 / 字样 / 道具 / 队形"],
        "negative_constraints": ["最容易生成错的点，如不要把训练生成成演出 / 不要把分趾鞋生成成运动鞋"]
      },
      "time_range": "0-5.2s"
    }
  ]
}
```

**字段说明**：
- `video_generation`：从原视频自动继承的尺寸与比例信息，步骤9必须优先遵循此配置
- `generation_contract`：步骤3.6锁定的统一生成形态，步骤8和步骤9都必须先消费它，不能绕过
- `style_consistency`：项目级统一风格模板，是 `generation_contract` 的展开描述，步骤8和步骤9必须强制消费
- `characters`：角色定义列表（`id`, `gender`, `age`, `appearance`, `clothing`），用于步骤8自动生成角色参考图
- `character_ref_prompts`：角色参考图的提示词；支持 `reference_type=identity_portrait/full_body_outfit`
- `scenes`：场景列表（`scene_id`, `prompt`, `duration`, `main_character`, `visible_characters`），用于步骤9生成视频
- `semantic_anchor`：场景级语义锚点，强制把步骤3.6的本体 / 子类 / 行为 / 证据 / 负约束穿透到生成层
- `main_character`：值必须对应 `characters[].id`，用于查找角色参考图
- `visible_characters`：多人场景里真正要喂给步骤9的人物锚点；如果缺失，极容易出现同脸

**大型现场模式（crowd mode）**：
- 当 `character_detection.json` 中的 `visible_people_stats.stable_visible_people_estimate > 10` 时，默认判定为**大型群像场景**
- **注意**：crowd mode 只是参考图生成策略，不是最终语义结论；不能因为人数多，就把内容草率写成“活动现场”
- 即使进入 crowd mode，也仍需继续判断它到底是训练、表演、比赛、课堂、仪式、集会还是其他多人组织活动
- `unique_characters` 仍然保留在分析结果里，作为底层聚类参考；但角色数量、队形关系、场景规模，必须优先使用 `单帧可见人数` 与 `稳定可见人数估计`
- crowd mode 下默认不为所有路人逐个建模，但仍要给前排主体和关键服装角色保留少量身份锚点
- 步骤9主要通过场景提示词 + `visible_characters` 复刻多人现场关系：前景主体、背景人群、站位层次、活动氛围，而不是给每个路人单独生成参考图
- 如用户明确要求逐角色建模，才从 crowd mode 切回逐角色参考图模式

---

#### 步骤7：生成TTS复刻指导

**执行方式：仅在 ASR 有有效文本时执行**

> **执行前检查**：如果 `output/analysis/asr_result.json` 的 `full_text` 为空，或 `segments` 为空，说明该视频没有可复刻的有效解说文本。此时**跳过步骤7和步骤10**，进入纯视觉复刻模式，不再生成或消费 `tts_guide.json`。

> **初稿已自动生成**：`output/prompts/tts_guide.json` 已从 ASR 结果自动填充 reference_text（完整解说文本）、duration_target、以及从 voice_style 映射的 TTS 参数。只有在 ASR 文本非空时，Claude 才需要审核这些字段。

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
- `output/prompts/tts_guide.json` - TTS复刻指导（仅在 ASR 有有效文本时生成并消费）

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

#### 步骤8：生成统一形态角色参考图

**执行方式：调用Python脚本（ApiMart Gemini 图片生成）**

```bash
python scripts/image_generator.py \
  --prompts_json output/prompts/scene_prompts.json \
  --output_dir output/角色参考图/ \
  --config config/api_config.yaml
```

**脚本读取 `scene_prompts.json` 中的 `generation_contract`、`style_consistency` 与 `character_ref_prompts` / `characters` 列表。先确认 `scene_generation_mode == target_visual_mode`，再按 `character_reference_mode` 生成角色参考图。只有当 `source_visual_mode` 明确为真人时，步骤8才允许统一改用 `pseudo_realistic_human_illustration` 作为写实人物插画桥接参考图。动漫源视频必须继续走动漫角色参考图模板。**

**强制规则**：
- 如果 `generation_contract` 还没锁定，步骤8必须直接报错停止
- 如果角色参考图的目标形态和步骤9的场景目标形态不一致，步骤8输出不能继续用于步骤9
- 当前项目生成完的 `refs_manifest.json` 必须记录本次 `generation_contract`，供步骤9核对
- 真人项目如果不能直接喂真人参考图，桥接图必须是**写实人物插画参考图**：非照片、真人比例、真实皮肤明暗、真实布料褶皱
- 动漫源视频不能走写实人物插画桥接，必须继续使用动漫角色参考图模板
- 只要桥接图出现**漫画脸 / 二次元大眼 / 赛璐璐阴影 / 卡通线稿**，就必须打回重生，不能流入步骤9

**角色参考图策略**：
- **常规模式**（`stable_visible_people_estimate <= 10`）：按稳定可见人数估计选择主要主体生成参考图
- 每个进入生成链路的关键角色，至少应有 `identity_portrait`
- 主角色和关键服装角色，还应补 `full_body_outfit`，专门锁定长裤、鞋子和服装版型
- **大型现场模式 / crowd mode**（`stable_visible_people_estimate > 10`）：默认不做“全员逐个建模”，但仍要保留少量前排主体锚点，不能只剩 1 张主角图去硬带全场
- crowd mode 的目的不是减少复刻对象，而是避免把大型群像视频错误降维成“29 个独立角色逐个建模”，从而破坏真实现场感
- crowd mode 下的多人信息应保留在 `scene_prompts.json` 的场景描述中，而不是依赖大量单角色参考图

**配置要求**：
- `config/api_config.yaml` 中配置 `models.image`（默认 provider: apimart）
- API 密钥通过 `config/api_keys.yaml` 或环境变量 `APIMART_API_KEY` / `VOLCENGINE_API_KEY` 设置

**输出**：
- `output/角色参考图/*.jpg` - 每个角色的统一形态参考图
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
1. 查找该场景主角 + `visible_characters` 的参考图（从 refs_manifest.json）
2. 先核对 `refs_manifest.json` 与当前 `generation_contract` 是否一致；不一致则直接停止
3. 构建带 `@图片N` 调用语句的提示词
4. 调用 Seedance 2.0 API 提交任务 → 轮询 → 下载视频
5. 每个 scene prompt 在提交前，都必须自动叠加同一份 `generation_contract` 和 `style_consistency`
6. 支持最多 9 张参考图（角色+构图+风格等）

**多人场景强制要求**：
- `main_character` 只能解决“主角是谁”，解决不了“整队不要同脸”
- `visible_characters` 必须列出真正需要喂给步骤9的人物锚点
- 如果多人场景只喂一张主角参考图，极容易出现“所有人长成同一张脸”
- 如果主角色没有 `full_body_outfit`，极容易出现“裤子、鞋子、下装版型漂移”

**强制参数**（优先由 `scene_prompts.json.video_generation` 决定，`config` 为兜底）：
- **ratio**: 继承原视频比例（如 9:16 / 16:9 / 1:1）
- **resolution**: API 生成档位（当前通常为 720p 或 1080p），生成后再归一到原视频精确尺寸
- **duration**: 4-15秒（与原视频场景时长一致，自动 clamp）
- **max_reference_images**: 9

**尺寸规则**：
- **最终输出尺寸必须与原视频一致**（例如原视频为 `540x960`，则生成后的场景视频也必须落盘为 `540x960`）
- 如果视频生成 API 只能按档位分辨率工作，允许先按最近档位生成，再在本地统一缩放/补边到原视频尺寸

**断点续传**：已存在的 scene_*.mp4 自动跳过。

**输出**：
- `output/videos/scene_*.mp4` - 每个场景的视频片段
- `output/videos/videos_manifest.json` - 视频清单

---

#### 步骤10：生成TTS配音

**执行方式：仅在步骤7已确认存在有效解说文本时执行**

> **跳过条件**：如果 `asr_result.json` 没有可用文本（`full_text == ""`），则该视频视为**无 TTS 复刻需求**。直接跳过步骤10，进入纯视觉复刻模式。

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

**执行方式：根据是否存在 TTS 分为两种模式**

##### 模式A：有 TTS 文本 → 执行 11a + 11b

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

##### 模式B：无 TTS 文本 → 仅执行 11a（纯视觉复刻）

> **默认规则**：当 ASR 为空时，最终交付物定义为**无复刻配音版本**。即只拼接视频片段，不执行 `audio_video_mixer.py`。

```bash
# 11a 拼接场景视频（此时 merged_video.mp4 即最终交付物）
python scripts/scene_concat.py \
  --video_dir output/videos/ \
  --output_path output/videos/merged_video.mp4 \
  --order_json output/prompts/scene_prompts.json
```

> **当前 Skill 的默认定义**：纯视觉复刻模式下，最终输出是 `merged_video.mp4`。  
> **不默认保留原视频音轨**；“保留原音轨”属于额外需求，需用户明确提出，并应通过单独的音频策略实现，而不是复用 TTS 替换链路。

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
- `output/复刻视频.mp4` - 最终视频（有 TTS 文本时）
- `output/videos/merged_video.mp4` - 纯视觉复刻的最终视频（无 TTS 文本时）

---

## 📋 完整步骤总结

| 阶段 | 步骤 | 内容 | 执行方式 | 输出 |
|------|------|------|----------|------|
| 阶段1 | 步骤1 | 智能关键帧提取 | Python脚本 | keyframes/ |
| 阶段1 | 步骤1.5 | 角色检测与跨帧聚类 | Python脚本（InsightFace） | character_detection.json |
| 阶段1 | 步骤2 | 色彩与运动分析 | Python脚本 | color_analysis.json |
| 阶段1 | 步骤3 | ASR语音识别 ⭐ | Python脚本 | asr_result.json |
| 阶段2 | 步骤3.5 | 叙事线分析 ⭐ | Claude分析 | narrative_analysis.json |
| 阶段2 | 步骤3.6 | 通用语义分析骨架 ⭐ | Claude分析 | semantic_analysis.json |
| 阶段2 | 步骤4 | 深度视觉分析（基于叙事线）⭐ | Claude+Read工具 | coherence_analysis.json |
| 阶段2 | 步骤5 | 音画关联分析 | Claude分析 | audio_visual_correlation.json |
| 阶段2 | 步骤6 | 生成视觉提示词 | Claude生成 | scene_prompts.json |
| 阶段2 | 步骤7 | 生成TTS指导（可选） | Claude生成 | tts_guide.json |
| 阶段3 | 步骤8 | 生成角色参考图 | Python脚本（ApiMart Gemini 图片生成） | 角色参考图/ |
| 阶段3 | 步骤9 | 生成视频片段 | Python脚本（Seedance 2.0 API） | videos/scene_*.mp4 |
| 阶段3 | 步骤10 | 生成TTS配音（可选） | Python脚本（edge_tts） | tts_narration.wav |
| 阶段3 | 步骤11 | 音视频合成 / 纯视觉交付 | Python脚本 | 复刻视频.mp4 / merged_video.mp4 |

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
            [步骤3.6] Claude分析 → semantic_analysis.json
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

[步骤8] image_generator.py（ApiMart Gemini 图片生成）→ 角色参考图/*.jpg

    ↓

[步骤9] video_generator.py（Seedance 2.0 API + 角色参考图）→ videos/scene_*.mp4

    ↓

[步骤10] tts_generator.py（edge_tts，可选）→ tts_narration.wav

    ↓

[步骤11a] scene_concat.py → merged_video.mp4
    ├─→ 若无有效 ASR / 无 TTS 需求：merged_video.mp4 即最终输出
    └─→ 若有有效 ASR / 需要 TTS：进入步骤11b

[步骤11b] audio_video_mixer.py → 复刻视频.mp4
```

---

## 注意事项

### 1. ASR优先，但允许纯视觉降级 ⭐ 最重要
- **优先尝试 ASR**，再判断是否进入文本驱动流程
- **有有效 ASR 文本时**：文本理解 > 图像理解，ASR结果指导叙事线、角色识别和音画对齐
- **无有效 ASR 文本时**：立即切换到纯视觉复刻模式，以关键帧、角色检测、场景叙事为主，不再强行走 TTS 链路
- **禁止跳过 ASR 探测**；但 ASR 为空不等于流程失败，而是代表该视频不适合做 TTS 复刻

### 2. 调度模式
- **本 Skill 是调度核心**：Claude 读取 SKILL.md 后按步骤执行全部流程
- **步骤1-3**：Claude 调用 Python 脚本（`perfect_replication_workflow.py` 或单独脚本）
- **步骤3.5-7（含步骤3.6）**：Claude 直接执行（分析 ASR 文本、补全语义骨架、查看关键帧、生成提示词）
- **步骤8-9**：Claude 调用 Python 脚本（`image_generator.py`、`video_generator.py`，通过 API 生成）
- **步骤10-11**：Claude 调用 Python 脚本；其中步骤10和步骤11b仅在存在有效 ASR 文本时执行
- **API 配置**：`config/api_config.yaml` 定义 provider，`config/api_keys.yaml` 存放密钥（或用环境变量）

### 3. 角色识别流程
1. 步骤1.5自动检测人脸并聚类（`character_detection.json`）
2. 从ASR文本识别角色（名字、身份、关系）
3. 完成 `semantic_analysis.json` 中的主体规模、行为、证据、子类判断
4. 从ASR时间戳分配关键帧到角色
5. 用read_image验证角色外貌
6. 生成最终角色定义表

### 4. 角色 ID 命名规范 ⭐ 重要
- 步骤1.5输出的角色 label（如 `char_0`, `char_1`）是**全管线统一的角色 ID**
- 步骤6生成 `scene_prompts.json` 时，`characters[].id`、`scenes[].main_character`、`scenes[].visible_characters[]` **必须使用相同的 ID**
- 步骤8生成参考图时，身份图默认文件名为 `{character_id}.jpg`，全身服装锚点图为 `{character_id}__full_body_outfit.jpg`
- 步骤9查找参考图时，会同时读取 `main_character` 和 `visible_characters`
- **如果 ID 不一致，步骤9将找不到参考图，生成的视频质量会严重下降**
- 若进入 crowd mode，未单独生成参考图的角色 ID 仍应保留在分析结果中，不得因为跳过参考图生成而删除角色记录
- 但 `scene_prompts.json` 中真正进入生成链路的 `characters` 列表，应按 `稳定可见人数估计` 做收敛，不能把 `unique_characters` 原样当成人数抄下去

### 5. 步骤依赖关系
- 步骤1-3可并行执行（或调用 `perfect_replication_workflow.py` 一次性完成，含步骤1.5）
- **步骤3.5必须在步骤3.6之前或同时完成**（叙事线提供文本语义）
- **步骤3.6必须在步骤4和步骤6之前完成**（行为、证据、子类判断先于角色细化和 prompt 编写）
- 步骤4必须用 Read 工具查看关键帧图片
- 步骤6生成提示词时必须引用步骤2的色彩分析、步骤3.5的叙事线和步骤3.6的语义骨架
- **步骤6生成的 JSON 必须通过 Schema 校验**（`scripts/schema_validator.py`），步骤8-9入口会自动校验
- 若 ASR 文本为空，则步骤7、步骤10、步骤11b默认跳过
- 步骤8-9依赖 `scene_prompts.json`；步骤10-11b仅在存在有效 `tts_guide.json` 时依赖 TTS 相关文件
- 步骤8-9需要 API 密钥已配置（`config/api_keys.yaml` 或环境变量 `VOLCENGINE_API_KEY`）

### 6. JSON 模板与 Schema 校验
- 步骤3.5-7（含步骤3.6）的每个 JSON 输出都有标准模板，位于 `assets/schema_templates/`
- 生成 JSON 时应参考模板中的字段定义，确保不遗漏必需字段
- `scripts/schema_validator.py` 可独立运行校验任意中间文件：
  ```bash
  python scripts/schema_validator.py --file output/analysis/semantic_analysis.json --type semantic
  ```
- 步骤8（`image_generator.py`）和步骤9（`video_generator.py`）入口已集成自动校验，缺字段时会报明确错误

### 7. 其他注意事项
- 角色定义必须一致：同一个角色在所有场景使用完全相同的描述
- 视频尺寸必须跟随原视频：不得在 Skill 层面写死为 16:9 / 1280x720
- 当 `asr_result.json` 中 `full_text` 为空时，应切换到**纯视觉复刻模式**，不再强行生成 TTS
- 纯视觉复刻模式下，默认最终输出为 `output/videos/merged_video.mp4`
- 当 `visible_people_stats.stable_visible_people_estimate > 10` 时，默认进入 **crowd mode**：保留全部角色检测结果，但步骤8不做全员逐个建模，只保留少量前排主体与关键服装锚点
- “保留原视频音轨”不是当前默认链路；只有用户明确要求时，才应作为单独音频策略处理
- Whisper依赖：步骤3需要安装openai-whisper包（或使用sub-agent）

### 8. 统一生成形态提示词 ⭐ 强制要求

**所有场景提示词和角色参考图提示词，都必须先服从 `generation_contract`。**

**允许的最终视频目标形态只有 3 种**：
- `live_action`
- `stylized_live_action`
- `anime`

**允许的桥接参考图形态**：
- `pseudo_realistic_human_illustration`

> 兼容说明：旧项目里的 `safe_stylized_human` 视为历史命名；新生成的文件统一不要再写这个值。

**规则**：
- 一个项目只能选 **1 种**
- `scene_generation_mode` 必须和 `target_visual_mode` 完全一致
- `character_reference_mode` 通常与 `target_visual_mode` 一致；如真人项目受平台限制不能直接使用真人参考图，可整项目统一改成 `pseudo_realistic_human_illustration`
- `pseudo_realistic_human_illustration` 的含义是：写实人物插画参考图，不是漫画，不是二次元，不是卡通脸
- 如果 `source_visual_mode = anime`，则 `character_reference_mode` 不得使用 `pseudo_realistic_human_illustration`
- 如果模型能力不足，只允许**整项目统一降级**
- 禁止出现“某一段角色参考图是桥接安全图，另一段又突然改成别的桥接方式”这种局部乱切
- 禁止出现“多人场景只喂一张主角图，结果整队同脸”这种结构性错误

**示例前缀**：

`live_action`
```text
realistic photo style, live action, 9:16 vertical, 540x960,
```

`stylized_live_action`
```text
stylized live action, realistic human proportions, 9:16 vertical, 540x960,
```

`anime`
```text
anime style, clean cel shading, 9:16 vertical, 540x960,
```

**步骤6生成提示词时必须检查**：
- 当前项目前缀是否和 `target_visual_mode` 一致
- 角色参考图提示词和场景提示词是否属于同一种形态
- 比例与分辨率是否与原视频一致
- 是否出现跨形态冲突词（如 `live action` 和 `插画角色设定图` 混在一起）

---

## 资源索引

### 核心脚本
- 智能关键帧提取: scripts/smart_keyframe_extractor.py
- 角色检测与聚类: scripts/character_detector.py（步骤1.5，InsightFace人脸嵌入聚类）
- 视频色彩分析: scripts/video_analyzer.py
- ASR语音识别: scripts/asr_transcriber.py
- API客户端: scripts/api_client.py（凭证加载、图像/视频 API 封装）
- 角色参考图生成: scripts/image_generator.py（步骤8，ApiMart Gemini 图片生成）
- 场景视频生成: scripts/video_generator.py（步骤9，Seedance 2.0 API）
- TTS生成: scripts/tts_generator.py（步骤10，edge_tts优先+可切换）
- 视频拼接: scripts/scene_concat.py（步骤11a，ffmpeg）
- 音视频合成: scripts/audio_video_mixer.py（步骤11b）
- JSON Schema 校验: scripts/schema_validator.py（校验步骤3.5-7含3.6的中间JSON）
- 初稿生成器: scripts/draft_generator.py（自动从步骤1-3的输出生成步骤3.5-7含3.6的JSON初稿）
- 完整工作流: scripts/perfect_replication_workflow.py（步骤1-11完整管线）

### JSON 模板（步骤3.5-7含3.6输出标准格式）
- 叙事线分析: assets/schema_templates/narrative_analysis_template.json
- 语义分析骨架: assets/schema_templates/semantic_analysis_template.json
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
