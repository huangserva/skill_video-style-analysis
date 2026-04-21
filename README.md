# video-style-analysis

视频完美复刻 Claude Code Skill — 通过智能体分析原视频的视觉风格和音频特征，生成风格提示词，使用 TTS 复刻配音，基于原画面重新生成相似视频并合成。

## 功能

- 智能关键帧提取（场景切换检测 + 动作密度自适应）
- InsightFace 人脸检测与跨帧角色聚类（换装也能识别同一人）
- 色彩/运动风格分析（RGB/HSV + Farneback 光流法）
- ASR 语音识别与叙事线分析（Whisper + 三级容错）
- AI 内容生成（Seedream 角色参考图 + Seedance 场景视频）
- 项目级统一风格约束（`style_consistency`）前置分析，并强制贯穿角色图与场景视频生成
- TTS 配音克隆（edge_tts，带时间戳估算）
- 音视频精确对齐合成

## 管线流程

```
原视频
  ├─ [步骤1]   智能关键帧提取
  ├─ [步骤1.5] 角色检测与跨帧聚类 (InsightFace)
  ├─ [步骤2]   色彩与运动分析
  ├─ [步骤3]   ASR 语音识别 (Whisper)
  ├─ [自动]    生成步骤3.5-7（含3.6）JSON 初稿
  │
  ├─ [步骤3.5] 审核 narrative_analysis.json 初稿 (Claude)
  ├─ [步骤3.6] 审核 semantic_analysis.json 初稿 (Claude)
  ├─ [步骤4]   审核 coherence_analysis.json 初稿 (Claude)
  ├─ [步骤5]   审核 audio_visual_correlation.json 初稿 (Claude)
  ├─ [步骤6]   审核 scene_prompts.json 初稿 (Claude)
  ├─ [步骤7]   审核 tts_guide.json 初稿 (Claude)
  │
  ├─ [步骤8]   角色参考图生成 (Seedream API)
  ├─ [步骤9]   场景视频生成 (Seedance API)
  ├─ [步骤10]  TTS 配音生成 (edge_tts)
  └─ [步骤11]  音视频合成 (ffmpeg + moviepy)
       └─ 复刻视频.mp4
```

## 快速开始

### 安装依赖

#### 系统依赖

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt-get install ffmpeg

# Windows — 从 https://ffmpeg.org/download.html 下载并加入 PATH
```

#### Python 依赖

```bash
pip install opencv-python numpy moviepy Pillow openai-whisper edge-tts aiohttp pyyaml insightface onnxruntime
```

### 配置 API 密钥

```bash
cp config/api_keys.yaml.example config/api_keys.yaml
# 编辑 api_keys.yaml，填入 VolcEngine API Key
```

### 运行阶段1（自动化分析）

```bash
python scripts/perfect_replication_workflow.py \
  --reference_video 原视频.mp4 \
  --output_dir output
```

后续步骤 3.5-11 由 Claude 根据 `SKILL.md` 调度执行。
阶段 1 结束后会自动生成 `output/analysis/` 和 `output/prompts/` 下的 6 个 JSON 初稿，Claude 主要负责先完善 `semantic_analysis.json` 的 6 棱镜结构（叙事 / 主体 / 动作 / 场景 / 镜头 / 约束）以及项目级 `style_consistency`，再补齐其余语义字段并修正 `[TODO]` 占位符。

## 项目结构

```
scripts/
  smart_keyframe_extractor.py  # 步骤1: 智能关键帧提取
  character_detector.py        # 步骤1.5: 角色检测 (InsightFace)
  video_analyzer.py            # 步骤2: 色彩与运动分析
  asr_transcriber.py           # 步骤3: ASR 语音识别
  draft_generator.py           # 自动生成步骤3.5-7（含3.6）JSON 初稿
  image_generator.py           # 步骤8: 角色参考图 (Seedream)
  video_generator.py           # 步骤9: 场景视频 (Seedance)
  tts_generator.py             # 步骤10: TTS 配音
  scene_concat.py              # 步骤11a: 视频拼接
  audio_video_mixer.py         # 步骤11b: 音视频合成
  schema_validator.py          # JSON Schema 校验器
  perfect_replication_workflow.py  # 阶段1编排
  api_client.py                # API 客户端

config/
  api_config.yaml              # API 配置
  api_keys.yaml.example        # API 密钥模板

assets/
  schema_templates/            # 步骤3.5-7（含3.6）的 JSON 标准模板

references/                    # 参考文档
```

## 核心设计

**ASR 优先原则** — 先从语音识别文本中理解叙事和角色，再用视觉验证，而非从图像猜测。

**三级容错** — ASR 清晰时全流程分析；ASR 模糊时降级到视觉辅助；ASR 失败时用 InsightFace 人脸聚类做纯视觉角色识别。

**风格先锁定** — 风格一致性不是步骤 8 临时补救，而是在步骤 3.6 先沉淀成 `style_consistency`，后续角色图和场景视频都强制继承。

**Schema 校验** — 步骤 6-7 生成的中间 JSON 在步骤 8-9 入口自动校验，缺字段时报明确错误而非静默失败。

## 详细文档

完整的步骤说明、字段规范和注意事项见 [SKILL.md](SKILL.md)。
