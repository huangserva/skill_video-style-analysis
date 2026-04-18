#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初稿生成器

读取步骤1-3的分析结果，自动生成步骤3.5-7的中间JSON初稿。
能从数据推导的字段自动填充，需要语义理解的留 [TODO] 占位符让 Claude 补充。

输入：output/keyframes/extraction_result.json
      output/analysis/character_detection.json
      output/analysis/color_analysis.json
      output/analysis/asr_result.json

输出：output/analysis/narrative_analysis.json      (步骤3.5初稿)
      output/analysis/coherence_analysis.json      (步骤4初稿)
      output/analysis/audio_visual_correlation.json (步骤5初稿)
      output/prompts/scene_prompts.json             (步骤6初稿)
      output/prompts/tts_guide.json                 (步骤7初稿)
"""

import json
import re
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional


# ============================================================
# 映射表
# ============================================================

COLOR_TONE_MAP = {
    "warm_red_orange": "暖红橙色调",
    "warm_yellow": "暖黄色调",
    "green": "绿色调",
    "cyan": "青色调",
    "blue": "蓝色调",
    "purple": "紫色调",
    "low_saturation_gray": "低饱和灰色调",
    "dark": "暗色调",
}

MOTION_TYPE_MAP = {
    "static": "静态镜头",
    "slow_movement": "缓慢镜头运动",
    "normal_movement": "中等镜头运动",
    "dynamic_fast": "快速动态镜头",
    "fast_movement": "快速镜头运动",
}


# ============================================================
# 数据加载
# ============================================================

def load_json(path: Path) -> Optional[dict]:
    """安全加载 JSON 文件"""
    if not path.exists():
        print(f"  [跳过] 文件不存在: {path}")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict, path: Path):
    """保存 JSON"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 已生成: {path}")


# ============================================================
# 辅助函数
# ============================================================

def extract_names_from_text(text: str) -> List[str]:
    """从中文文本中提取可能的人名（简易启发式）"""
    names = []
    # 匹配"叫XX"、"是XX"、"XX说" 等模式
    patterns = [
        r'叫[「「]?(\w{2,4})[」」]?',
        r'名叫(\w{2,4})',
        r'(\w{2,4})先生',
        r'(\w{2,4})女士',
        r'(\w{2,4})小姐',
    ]
    for p in patterns:
        for match in re.finditer(p, text):
            name = match.group(1)
            if name not in names and len(name) >= 2:
                names.append(name)
    return names


def find_dominant_character(
    scene_start: float,
    scene_end: float,
    characters: List[dict],
    keyframes: List[dict],
) -> str:
    """找出某时间段内出现次数最多的角色"""
    char_counts = {}

    for char in characters:
        label = char.get("label", "")
        indices = char.get("keyframe_indices", [])
        count = 0
        for idx in indices:
            if idx < len(keyframes):
                kf = keyframes[idx]
                ts = kf.get("timestamp", 0)
                if scene_start <= ts <= scene_end:
                    count += 1
        if count > 0:
            char_counts[label] = count

    if not char_counts:
        return ""
    return max(char_counts, key=char_counts.get)


def map_asr_to_scene(
    segments: List[dict],
    scene_start: float,
    scene_end: float,
) -> str:
    """提取某时间段内的 ASR 文本"""
    texts = []
    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        # 有重叠就算
        if seg_start < scene_end and seg_end > scene_start:
            texts.append(seg.get("text", ""))
    return "".join(texts)


# ============================================================
# 初稿生成
# ============================================================

def generate_narrative_draft(asr_data: dict) -> dict:
    """生成 narrative_analysis.json 初稿"""
    full_text = asr_data.get("full_text", "")
    duration = asr_data.get("duration", 0)
    segments = asr_data.get("segments", [])

    # 提取人名
    names = extract_names_from_text(full_text)

    # 构建角色列表
    characters_from_text = []
    for name in names:
        characters_from_text.append({
            "name": name,
            "role": "[TODO: Claude 补充角色在故事中的身份]",
            "identity": "[TODO: Claude 补充角色真实身份]",
        })

    # 如果文本有第一人称"我"，加一个叙述者角色
    if "我" in full_text and not any(c["name"] == "我" for c in characters_from_text):
        characters_from_text.insert(0, {
            "name": "叙述者（我）",
            "role": "[TODO: Claude 补充叙述者身份]",
            "identity": "[TODO: Claude 补充]",
        })

    # 按时间三等分构建叙事弧线
    third = duration / 3 if duration > 0 else 10
    narrative_arc = {
        "act_1": {
            "name": "[TODO: Claude 补充阶段名称]",
            "time_range": f"0-{third:.1f}s",
            "description": "[TODO: Claude 补充阶段描述]",
        },
        "act_2": {
            "name": "[TODO: Claude 补充]",
            "time_range": f"{third:.1f}-{third*2:.1f}s",
            "description": "[TODO: Claude 补充]",
        },
        "act_3": {
            "name": "[TODO: Claude 补充]",
            "time_range": f"{third*2:.1f}-{duration:.1f}s",
            "description": "[TODO: Claude 补充]",
        },
    }

    has_asr = bool(full_text.strip())
    return {
        "analysis_level": "level_1" if has_asr else "level_3",
        "narrative_theme": "[TODO: Claude 补充叙事主题，如：富豪伪装穷人的爱情故事]",
        "narrator": "[TODO: Claude 补充叙述者，如：女主（女性）/ 旁白]",
        "characters_from_text": characters_from_text,
        "narrative_arc": narrative_arc,
        "_auto_generated": True,
        "_asr_text_preview": full_text[:200] + ("..." if len(full_text) > 200 else ""),
    }


def generate_coherence_draft(
    char_detection: dict,
    narrative: dict,
) -> dict:
    """生成 coherence_analysis.json 初稿"""
    characters = []
    detected = char_detection.get("characters", [])
    text_chars = narrative.get("characters_from_text", [])

    for i, det in enumerate(detected):
        # 尝试匹配文本角色名
        matched_name = None
        if i < len(text_chars):
            matched_name = text_chars[i].get("name")

        characters.append({
            "character_id": det.get("label", f"char_{i}"),
            "name_from_text": matched_name or "[TODO: Claude 从叙事线匹配角色名]",
            "visual_description": "[TODO: Claude 用 read_image 查看关键帧后填写]",
            "age_range": "[TODO: Claude 补充]",
            "appearance": {
                "hair": "[TODO]",
                "face": "[TODO]",
                "distinctive_marks": "[TODO]",
            },
            "clothing_changes": ["[TODO: Claude 查看关键帧后填写]"],
            "scenes_appearance": det.get("scene_ids", []) or det.get("keyframe_indices", []),
            "confidence": det.get("avg_det_score", 0),
        })

    return {
        "analysis_level": narrative.get("analysis_level", "level_1"),
        "characters": characters,
        "scene_analysis": [{"scene_id": 0, "description": "[TODO: Claude 补充]", "characters_present": [], "mood": "[TODO]"}],
        "_auto_generated": True,
    }


def generate_correlation_draft(
    asr_data: dict,
    scenes: List[dict],
) -> dict:
    """生成 audio_visual_correlation.json 初稿"""
    segments = asr_data.get("segments", [])
    timeline = []

    for scene in scenes:
        start = scene.get("start_time", 0)
        end = scene.get("end_time", 0)
        asr_text = map_asr_to_scene(segments, start, end)

        timeline.append({
            "time_range": f"{start:.1f}-{end:.1f}s",
            "asr_text": asr_text if asr_text else "[该时间段无 ASR 文本]",
            "visual_content": "[TODO: Claude 查看对应关键帧后描述画面内容]",
            "semantic_match": "[TODO: high/medium/low]",
            "emotion_match": "[TODO: high/medium/low]",
        })

    return {
        "analysis_level": "level_1" if segments else "level_3",
        "timeline_mapping": timeline,
        "semantic_match_score": "[TODO: Claude 评分 0-1]",
        "emotion_consistency": "[TODO: Claude 评分 0-1]",
        "overall_correlation": "[TODO: Claude 总结音画关联程度]",
        "_auto_generated": True,
    }


def generate_scene_prompts_draft(
    scenes: List[dict],
    keyframes: List[dict],
    char_detection: dict,
    color_data: dict,
) -> dict:
    """生成 scene_prompts.json 初稿"""
    # 视觉风格提示词（自动从色彩分析推导）
    color_dist = color_data.get("visual_style", {}).get("color_distribution", {})
    motion = color_data.get("visual_style", {}).get("motion_characteristics", {})
    color_tone = color_dist.get("color_tone", "")
    motion_type = motion.get("motion_type", "")

    style_parts = []
    if color_tone:
        style_parts.append(COLOR_TONE_MAP.get(color_tone, color_tone))
    if motion_type:
        style_parts.append(MOTION_TYPE_MAP.get(motion_type, motion_type))
    style_parts.append("电影感")
    visual_style_prompt = "，".join(style_parts)

    # 角色列表（从 character_detection 映射）
    detected_chars = char_detection.get("characters", [])
    characters = []
    for det in detected_chars:
        characters.append({
            "id": det.get("label", "unknown"),
            "name": "[TODO: Claude 填写角色名]",
            "gender": "[TODO: 男性/女性]",
            "age": "[TODO: 如 25-35岁]",
            "appearance": "[TODO: Claude 用 read_image 查看代表面部后描述]",
            "clothing": "[TODO: Claude 查看关键帧后描述]",
        })

    # character_ref_prompts（结构骨架）
    character_ref_prompts = []
    for det in detected_chars:
        character_ref_prompts.append({
            "character_id": det.get("label", "unknown"),
            "prompt": f"插画风格，半身像，干净背景，[TODO: Claude 补充角色外貌描述]",
        })

    # 场景列表
    scene_list = []
    for scene in scenes:
        sid = scene.get("scene_id", 0)
        start = scene.get("start_time", 0)
        end = scene.get("end_time", 0)
        duration = round(end - start, 1)
        duration = max(4, min(15, duration))  # clamp 到 Seedance 限制

        # 找该场景的主角色
        main_char = find_dominant_character(start, end, detected_chars, keyframes)

        scene_list.append({
            "scene_id": sid,
            "prompt": f"realistic photo style, live action, 16:9 widescreen, 1280x720, [TODO: Claude 补充场景描述和角色动作]",
            "duration": duration,
            "main_character": main_char,
            "time_range": f"{start:.1f}-{end:.1f}s",
        })

    return {
        "visual_style_prompt": visual_style_prompt,
        "characters": characters,
        "character_ref_prompts": character_ref_prompts,
        "scenes": scene_list,
        "_auto_generated": True,
    }


def generate_tts_guide_draft(asr_data: dict) -> dict:
    """生成 tts_guide.json 初稿"""
    voice_style = asr_data.get("voice_style", {})
    full_text = asr_data.get("full_text", "")
    duration = asr_data.get("duration", 0)

    return {
        "tts_parameters": {
            "gender": "[TODO: 男性/女性，根据叙述者判断]",
            "tone": voice_style.get("estimated_tone", "温暖"),
            "speed": voice_style.get("speed", {}).get("level", "中等"),
            "emotion": voice_style.get("estimated_emotion", "温暖"),
            "rhythm": "平稳节奏",
        },
        "reference_text": full_text,
        "duration_target": round(duration, 2),
        "_auto_generated": True,
    }


# ============================================================
# 主流程
# ============================================================

def run(input_dir: str, output_dir: str):
    """执行初稿生成"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    print("=" * 70)
    print("初稿生成器：自动生成步骤3.5-7的JSON初稿")
    print("=" * 70)

    # 加载输入数据
    print("\n[加载] 读取步骤1-3的分析结果...")

    extraction = load_json(input_path / "keyframes" / "extraction_result.json")
    char_detection = load_json(input_path / "analysis" / "character_detection.json")
    color_data = load_json(input_path / "analysis" / "color_analysis.json")
    asr_data = load_json(input_path / "analysis" / "asr_result.json")

    # 提供空数据兜底
    if extraction is None:
        extraction = {"scenes": [], "keyframes": []}
    if char_detection is None:
        char_detection = {"characters": []}
    if color_data is None:
        color_data = {"visual_style": {"color_distribution": {}, "motion_characteristics": {}}}
    if asr_data is None:
        asr_data = {"full_text": "", "duration": 0, "segments": [], "voice_style": {}}

    scenes = extraction.get("scenes", [])
    keyframes = extraction.get("keyframes", [])

    # 如果没有场景数据，构造一个默认场景
    if not scenes:
        duration = asr_data.get("duration", 30)
        scenes = [{"scene_id": 0, "start_time": 0, "end_time": duration}]

    # 生成初稿
    print("\n[生成] 生成5个JSON初稿...")

    # 步骤3.5: narrative_analysis
    narrative = generate_narrative_draft(asr_data)
    save_json(narrative, output_path / "analysis" / "narrative_analysis.json")

    # 步骤4: coherence_analysis
    coherence = generate_coherence_draft(char_detection, narrative)
    save_json(coherence, output_path / "analysis" / "coherence_analysis.json")

    # 步骤5: audio_visual_correlation
    correlation = generate_correlation_draft(asr_data, scenes)
    save_json(correlation, output_path / "analysis" / "audio_visual_correlation.json")

    # 步骤6: scene_prompts
    scene_prompts = generate_scene_prompts_draft(scenes, keyframes, char_detection, color_data)
    save_json(scene_prompts, output_path / "prompts" / "scene_prompts.json")

    # 步骤7: tts_guide
    tts_guide = generate_tts_guide_draft(asr_data)
    save_json(tts_guide, output_path / "prompts" / "tts_guide.json")

    # 统计
    todo_count = _count_todos(narrative, coherence, correlation, scene_prompts, tts_guide)
    print(f"\n[完成] 5个初稿已生成")
    print(f"  待 Claude 补充的 [TODO] 字段: {todo_count} 处")
    print(f"  Claude 接下来需要：")
    print(f"    1. 阅读 ASR 文本和关键帧图片")
    print(f"    2. 用 read_image 查看角色代表面部")
    print(f"    3. 填写所有 [TODO] 占位符")
    print(f"    4. 运行 schema_validator.py 校验后保存")
    print("=" * 70)


def _count_todos(*dicts) -> int:
    """递归统计所有 [TODO] 占位符"""
    count = 0
    for d in dicts:
        text = json.dumps(d, ensure_ascii=False)
        count += text.count("[TODO")
    return count


def main():
    parser = argparse.ArgumentParser(description="初稿生成器：自动生成步骤3.5-7的JSON初稿")
    parser.add_argument("--input_dir", default="output", help="输入目录（含 keyframes/ 和 analysis/）")
    parser.add_argument("--output_dir", default="output", help="输出目录")

    args = parser.parse_args()
    run(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
