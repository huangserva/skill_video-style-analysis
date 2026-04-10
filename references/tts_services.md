# TTS 服务配置指南

## 目录
1. [服务概述](#服务概述)
2. [Coze 语音克隆](#coze-语音克隆)
3. [ElevenLabs Voice Cloning](#elevenlabs-voice-cloning)
4. [Azure Custom Voice](#azure-custom-voice)
5. [选择建议](#选择建议)

## 服务概述

本 Skill 支持多种 TTS 语音克隆服务，用于模仿原视频说话人的音色、语调和节奏。

| 服务 | 推荐度 | 成本 | 音质 | 配置难度 |
|------|--------|------|------|----------|
| **Coze 语音克隆** | ⭐⭐⭐⭐⭐ | 免费 | 高 | 低 |
| **ElevenLabs** | ⭐⭐⭐⭐ | 按量付费 | 极高 | 中 |
| **Azure Custom Voice** | ⭐⭐⭐ | 按量付费 | 高 | 高 |

## Coze 语音克隆

### 概述

Coze 平台内置语音克隆功能，无需额外配置，推荐优先使用。

### 配置步骤

1. **在 Coze 平台创建语音克隆**
   - 登录 Coze 平台
   - 进入"语音克隆"功能
   - 上传原视频的音频片段作为参考
   - 创建语音克隆模型

2. **在 Skill 中使用**
   ```bash
   python scripts/tts_generator.py \
     --asr_json asr_result.json \
     --output_audio cloned_speech.wav \
     --service coze
   ```

### 优势

- ✅ 无需额外 API 密钥
- ✅ 与 Coze 平台深度集成
- ✅ 免费使用
- ✅ 高质量语音克隆

### 注意事项

- 需要先在 Coze 平台创建语音克隆模型
- 首次使用可能需要上传参考音频

## ElevenLabs Voice Cloning

### 概述

ElevenLabs 提供业界领先的语音克隆技术，支持高度自然的语音合成。

### 配置步骤

1. **获取 API 密钥**
   - 访问 [ElevenLabs 官网](https://elevenlabs.io/)
   - 注册账号并创建 API 密钥

2. **设置环境变量**
   ```bash
   export ELEVENLABS_API_KEY="your_api_key_here"
   ```

3. **在 Skill 中使用**
   ```bash
   python scripts/tts_generator.py \
     --asr_json asr_result.json \
     --output_audio cloned_speech.wav \
     --service elevenlabs
   ```

### API 参数

```python
payload = {
    "text": "要合成的文本",
    "model_id": "eleven_multilingual_v2",  # 模型ID
    "voice_settings": {
        "stability": 0.5,        # 稳定性（0-1）
        "similarity_boost": 0.75,  # 相似度提升（0-1）
        "style": 0.0,            # 风格增强（0-1）
        "use_speaker_boost": true  # 说话人增强
    }
}
```

### 优势

- ✅ 极高音质
- ✅ 支持多种语言
- ✅ 高度自然的语音
- ✅ 丰富的参数可调

### 注意事项

- 需要付费订阅
- 需要先创建 Voice ID（上传参考音频）

### 创建 Voice ID

```python
import requests

api_key = "your_api_key"
url = "https://api.elevenlabs.io/v1/voices/add"

# 上传参考音频
with open("reference_audio.wav", "rb") as f:
    files = {"files": ("reference_audio.wav", f)}
    headers = {"xi-api-key": api_key}
    response = requests.post(url, files=files, headers=headers)

voice_id = response.json()["voice_id"]
print(f"Voice ID: {voice_id}")
```

## Azure Custom Voice

### 概述

微软 Azure 提供企业级语音克隆服务，适合大规模部署。

### 配置步骤

1. **创建 Azure 语音服务**
   - 访问 [Azure 门户](https://portal.azure.com/)
   - 创建"语音服务"资源
   - 获取 API 密钥和区域

2. **创建自定义语音**
   - 上传参考音频（至少 1 分钟）
   - 训练语音模型
   - 获取端点 ID

3. **设置环境变量**
   ```bash
   export AZURE_SPEECH_KEY="your_speech_key"
   export AZURE_SPEECH_REGION="your_region"
   export AZURE_VOICE_ID="your_voice_id"
   ```

4. **在 Skill 中使用**
   ```bash
   python scripts/tts_generator.py \
     --asr_json asr_result.json \
     --output_audio cloned_speech.wav \
     --service azure
   ```

### 优势

- ✅ 企业级稳定性
- ✅ 支持大规模部署
- ✅ 高安全性
- ✅ 丰富的语音定制选项

### 注意事项

- 配置较复杂
- 需要付费订阅
- 首次训练需要较长时间

## 选择建议

### 场景1：快速原型开发

**推荐服务**：Coze 语音克隆

**理由**：
- 无需额外配置
- 免费使用
- 与 Coze 平台深度集成

### 场景2：高质量生产环境

**推荐服务**：ElevenLabs

**理由**：
- 极高音质
- 参数可调
- 支持多语言

### 场景3：企业级部署

**推荐服务**：Azure Custom Voice

**理由**：
- 企业级稳定性
- 高安全性
- 支持大规模部署

## 代码示例

### 检查服务可用性

```python
import os

def check_service_availability(service):
    if service == "coze":
        # Coze 无需额外配置
        return True
    elif service == "elevenlabs":
        # 检查 ElevenLabs API 密钥
        return "ELEVENLABS_API_KEY" in os.environ
    elif service == "azure":
        # 检查 Azure 配置
        return all(key in os.environ for key in [
            "AZURE_SPEECH_KEY",
            "AZURE_SPEECH_REGION",
            "AZURE_VOICE_ID"
        ])
    return False

# 使用
if check_service_availability("elevenlabs"):
    print("ElevenLabs 服务可用")
else:
    print("请配置 ELEVENLABS_API_KEY 环境变量")
```

### 自动选择最佳服务

```python
def auto_select_service():
    # 优先级：Coze > ElevenLabs > Azure
    services = ["coze", "elevenlabs", "azure"]
    for service in services:
        if check_service_availability(service):
            return service
    return None

# 使用
best_service = auto_select_service()
if best_service:
    print(f"自动选择服务: {best_service}")
else:
    print("未找到可用的 TTS 服务，请先配置")
```

## 常见问题

### Q1: Coze 语音克隆需要上传参考音频吗？

**A**: 是的，首次使用需要上传原视频的音频片段（建议至少 30 秒）作为参考。

### Q2: ElevenLabs 的 API 配额是多少？

**A**: 免费套餐每月 10,000 字符，付费套餐根据订阅等级不同。

### Q3: 如何提高语音克隆的相似度？

**A**:
- 使用高质量参考音频（无噪音、清晰）
- 参考音频时长至少 1 分钟
- 包含多种语调和情感的表达

### Q4: 可以同时使用多个语音克隆服务吗？

**A**: 可以，但建议优先使用一个服务，避免混淆。

## 更新日志

- **2024-01-15**: 添加 Coze 语音克隆支持
- **2024-01-10**: 更新 ElevenLabs API 参数
- **2024-01-05**: 初始版本，支持 ElevenLabs 和 Azure
