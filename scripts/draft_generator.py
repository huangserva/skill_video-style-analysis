#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初稿生成器

读取步骤1-3的分析结果，自动生成步骤3.5-7（含步骤3.6语义骨架）的中间JSON初稿。
能从数据推导的字段自动填充，需要语义理解的留 [TODO] 占位符让 Claude 补充。

输入：output/keyframes/extraction_result.json
      output/analysis/character_detection.json
      output/analysis/color_analysis.json
      output/analysis/asr_result.json

输出：output/analysis/narrative_analysis.json      (步骤3.5初稿)
      output/analysis/semantic_analysis.json       (步骤3.6初稿)
      output/analysis/coherence_analysis.json      (步骤4初稿)
      output/analysis/audio_visual_correlation.json (步骤5初稿)
      output/prompts/scene_prompts.json             (步骤6初稿)
      output/prompts/tts_guide.json                 (步骤7初稿)
"""

import json
import re
import argparse
from math import gcd
from pathlib import Path
from typing import List, Optional


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

SUBJECT_SCALE_LABELS = {
    "single": "单人",
    "duo": "双人",
    "small_group": "小群体",
    "medium_group": "中等群体",
    "crowd": "大型群像",
    "unknown": "未知规模",
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


def parse_resolution(resolution: str) -> tuple[int, int]:
    """解析 WxH 分辨率字符串"""
    match = re.match(r"^\s*(\d+)\s*x\s*(\d+)\s*$", resolution or "")
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def build_video_generation_profile(extraction: dict) -> dict:
    """根据源视频信息生成尺寸/比例配置"""
    video_info = extraction.get("video_info", {}) if extraction else {}
    resolution = video_info.get("resolution", "")
    width, height = parse_resolution(resolution)

    if width <= 0 or height <= 0:
        width, height = 1280, 720
        resolution = "1280x720"
    else:
        resolution = f"{width}x{height}"

    ratio_gcd = gcd(width, height) if width and height else 1
    aspect_ratio = f"{width // ratio_gcd}:{height // ratio_gcd}" if ratio_gcd else "16:9"

    if height > width:
        orientation_label = "vertical"
        prompt_aspect = f"{aspect_ratio} vertical"
    elif width > height:
        orientation_label = "horizontal"
        prompt_aspect = f"{aspect_ratio} widescreen"
    else:
        orientation_label = "square"
        prompt_aspect = f"{aspect_ratio} square frame"

    provider_ratio = aspect_ratio if aspect_ratio in {"16:9", "9:16", "1:1"} else ("9:16" if height > width else "16:9")
    provider_resolution = "1080p" if max(width, height) >= 1080 else "720p"

    return {
        "source_resolution": resolution,
        "source_width": width,
        "source_height": height,
        "source_aspect_ratio": aspect_ratio,
        "orientation": orientation_label,
        "provider_ratio": provider_ratio,
        "provider_resolution": provider_resolution,
        "target_resolution": resolution,
        "prompt_prefix": f"[TODO: 按 target_visual_mode 填写统一前缀], {prompt_aspect}, {resolution}",
    }


def build_visual_style_prompt(color_data: dict) -> str:
    """根据色彩分析生成视觉风格摘要"""
    color_dist = color_data.get("visual_style", {}).get("color_distribution", {})
    motion = color_data.get("visual_style", {}).get("motion_characteristics", {})
    color_tone = color_dist.get("color_tone", "")
    motion_type = motion.get("motion_type", "")

    style_parts = []
    if color_tone:
        style_parts.append(COLOR_TONE_MAP.get(color_tone, color_tone))
    if motion_type:
        style_parts.append(MOTION_TYPE_MAP.get(motion_type, motion_type))
    style_parts.append("写实影像风格")
    return "，".join(style_parts)


def build_generation_contract(video_generation: dict) -> dict:
    """生成复刻主脑中的统一生成契约草稿"""
    resolution = video_generation.get("source_resolution", "1280x720")
    aspect_ratio = video_generation.get("source_aspect_ratio", "16:9")
    orientation = video_generation.get("orientation", "horizontal")

    return {
        "source_visual_mode": "[TODO: Claude 根据关键帧判断源视频形态：live_action / stylized_live_action / anime]",
        "target_visual_mode": "[TODO: Claude 锁定整项目唯一目标形态：live_action / stylized_live_action / anime]",
        "mode_lock_reason": (
            f"[TODO: 说明为什么整项目锁定成这一种形态；原视频尺寸 {resolution}，"
            f"比例 {aspect_ratio}，画幅 {orientation}。如因模型限制降级，必须写明统一降级原因]"
        ),
        "fallback_policy": "如果模型能力不足，只允许整项目统一降级，不允许某一段单独换成别的形态。",
        "character_reference_mode": (
            "[TODO: 角色参考图形态；通常与 target_visual_mode 一致，"
            "如真人项目受平台限制不能直接用真人参考图，也可统一锁定为 pseudo_realistic_human_illustration]"
        ),
        "scene_generation_mode": "[TODO: 必须与 target_visual_mode 完全一致]",
        "required_keywords": [
            "[TODO: 按 target_visual_mode 固定必须出现的关键词]",
        ],
        "forbidden_keywords": [
            "[TODO: 按 target_visual_mode 固定禁止出现的关键词]",
        ],
        "consistency_rules": [
            "步骤8和步骤9都必须服从同一份 generation_contract",
            "scene_generation_mode 必须与 target_visual_mode 完全一致",
            "如果 character_reference_mode 与 target_visual_mode 不同，只允许整项目统一采用写实人物插画桥接方案",
            "如果从 live_action 统一降级到 stylized_live_action 或 anime，必须整项目一起降级",
        ],
    }


def build_style_consistency(
    color_data: dict,
    video_generation: dict,
    generation_contract: dict,
) -> dict:
    """生成项目级统一风格约束模板"""
    color_dist = color_data.get("visual_style", {}).get("color_distribution", {})
    motion = color_data.get("visual_style", {}).get("motion_characteristics", {})
    color_tone = color_dist.get("color_tone", "")
    motion_type = motion.get("motion_type", "")

    tone_label = COLOR_TONE_MAP.get(color_tone, "原视频综合色调")
    motion_label = MOTION_TYPE_MAP.get(motion_type, "原视频镜头运动节奏")
    resolution = video_generation.get("source_resolution", "1280x720")
    aspect_ratio = video_generation.get("source_aspect_ratio", "16:9")
    orientation = video_generation.get("orientation", "horizontal")
    orientation_label = {
        "vertical": "竖屏",
        "horizontal": "横屏",
        "square": "方形画幅",
    }.get(orientation, "原视频画幅")
    target_mode = generation_contract.get("target_visual_mode", "[TODO]")

    return {
        "style_family": "[TODO: Claude 确认统一项目风格名称，必须与 target_visual_mode 保持一致]",
        "character_render_mode": (
            "角色参考图的统一表现形态必须服从 generation_contract.character_reference_mode。"
            f"当前目标形态占位为：{target_mode}。如真人项目使用桥接参考图，"
            "桥接图也必须保持真人比例、真实皮肤明暗和真实布料褶皱。"
        ),
        "scene_render_mode": (
            "场景视频的统一表现形态必须完全服从 generation_contract.scene_generation_mode。"
            "如果角色参考图使用桥接方案，也只能锁身份、发型、服装和鞋子，"
            "不能反向把最终视频带偏成插画或卡通。"
            f"最终输出需保持 {orientation_label} {aspect_ratio}、{resolution} 的原视频记录关系。"
        ),
        "lighting_rule": f"整体延续 {tone_label} 与原视频照明逻辑，避免戏剧化补光和跳色",
        "palette_rule": f"整体保持 {tone_label}，服装和主体配色统一，不要出现无关强跳色",
        "background_rule": "角色参考图必须单人、纯白或极浅灰无纹理背景，不带训练馆、不带地面、不带第二个人，也不要灯、窗、栏杆、墙角等场景痕迹",
        "framing_rule": "角色参考图默认平视、头肩像到胸像、单人居中；核心角色还要补全身服装锚点图，完整露出长裤和鞋子；场景保持原视频记录式构图",
        "costume_rule": "服装材质、颜色、版型统一沿用原视频，不要时装化，不要演出化",
        "character_prompt_block": (
            "步骤8每次生成角色参考图前，都必须先读取 generation_contract.character_reference_mode。"
            "角色参考图只允许单人、纯净背景、统一构图距离。"
            "真人项目如果要绕开真人参考限制，桥接图只能走写实人物插画参考图。"
            "至少为核心角色生成 identity_portrait；多人场景还要给主角色和关键服装角色补 full_body_outfit。"
        ),
        "scene_prompt_block": (
            "步骤9每次生成场景前，都必须先读取 generation_contract.scene_generation_mode，"
            "并消费同一份 style_consistency。"
            f"所有场景都要保持 {orientation_label} {aspect_ratio}、{resolution}、{tone_label}、"
            f"{motion_label} 与同一项目的统一输出，不允许局部换形态。多人场景至少给 main_character + visible_characters 提供多张角色参考图，避免整队同脸。"
        ),
        "must_keep": [
            "同一项目只能有一种目标形态",
            "scene_generation_mode 必须与 target_visual_mode 一致",
            "角色参考图和场景视频都必须服从同一份 generation_contract",
            "人物脸部与材质表达方式一致",
            "服装材质表达一致",
            "多人场景的人脸和发型必须分开，不要整队同脸",
            "核心角色的裤型和鞋型必须稳定",
        ],
        "negative_constraints": [
            "不要跳过 visible_characters，导致多人场景只喂一张参考图",
            "不要某一段单独降级成别的风格",
            "不要把 live_action、stylized_live_action、anime 的关键词混在同一个项目里",
            "不要把群像做成一张脸复制",
            "不要让主角色或关键服装角色在不同片段突然换裤子或换鞋",
            "角色参考图不要画成漫画脸、二次元大眼或赛璐璐阴影",
            "不要训练馆和地面进入身份参考图",
        ],
    }


def infer_audio_mode(asr_data: dict) -> str:
    """根据 ASR 结果推断音频模式"""
    full_text = (asr_data.get("full_text") or "").strip()
    segments = asr_data.get("segments", []) or []

    if full_text and segments:
        return "narration_or_dialogue"
    if asr_data.get("duration", 0) > 0:
        return "music_or_nonverbal_audio"
    return "silent_or_unavailable"


def get_scene_character_labels(
    scene_start: float,
    scene_end: float,
    characters: List[dict],
    keyframes: List[dict],
) -> List[str]:
    """获取某个场景时间段内出现过的角色 id 列表"""
    labels = []
    for char in characters:
        label = char.get("label", "")
        indices = char.get("keyframe_indices", [])
        for idx in indices:
            if idx < len(keyframes):
                ts = keyframes[idx].get("timestamp", 0)
                if scene_start <= ts <= scene_end:
                    labels.append(label)
                    break
    return labels


def get_scene_visible_characters(
    scene_start: float,
    scene_end: float,
    characters: List[dict],
    keyframes: List[dict],
    max_count: int = 5,
) -> List[str]:
    """按场景时间段挑出真正可见的核心角色，用于步骤9多人参考图"""
    char_counts = []
    for char in characters:
        label = char.get("label", "")
        indices = char.get("keyframe_indices", [])
        count = 0
        for idx in indices:
            if idx < len(keyframes):
                ts = keyframes[idx].get("timestamp", 0)
                if scene_start <= ts <= scene_end:
                    count += 1
        if count > 0:
            char_counts.append((label, count))

    char_counts.sort(key=lambda item: (-item[1], item[0]))
    visible = [label for label, _ in char_counts[:max_count]]
    return visible


def infer_subject_scale(count: int) -> str:
    """根据主体数量推断规模"""
    if count <= 0:
        return "unknown"
    if count == 1:
        return "single"
    if count == 2:
        return "duo"
    if count <= 5:
        return "small_group"
    if count <= 10:
        return "medium_group"
    return "crowd"


def infer_camera_movement_label(motion_type: str) -> str:
    """将运动类型映射为镜头运动提示"""
    if motion_type in {"static", ""}:
        return "static"
    if motion_type == "slow_movement":
        return "slow_follow"
    if motion_type in {"normal_movement", "fast_movement", "dynamic_fast"}:
        return "dynamic_tracking"
    return "mixed"


def get_visible_people_stats(char_detection: dict) -> dict:
    """读取角色检测中的可见人数统计，缺失时给出兜底"""
    stats = char_detection.get("visible_people_stats", {}) or {}
    detected_chars = char_detection.get("characters", []) or []

    stable_visible = int(stats.get("stable_visible_people_estimate", 0) or 0)
    if stable_visible <= 0:
        stable_visible = min(
            len(detected_chars),
            int(char_detection.get("unique_characters", len(detected_chars)) or 0),
        )

    frames_with_faces = int(stats.get("frames_with_faces", 0) or 0)
    sampled_keyframes = int(stats.get("sampled_keyframes", 0) or 0)

    return {
        "counting_basis": char_detection.get("counting_basis", "cluster_fallback"),
        "sampled_keyframes": sampled_keyframes,
        "frames_with_faces": frames_with_faces,
        "min_visible_people": int(stats.get("min_visible_people", stable_visible) or 0),
        "median_visible_people": stats.get("median_visible_people", stable_visible),
        "max_visible_people": int(stats.get("max_visible_people", stable_visible) or 0),
        "avg_visible_people": stats.get("avg_visible_people", float(stable_visible)),
        "stable_visible_people_estimate": stable_visible,
        "raw_face_cluster_count": int(
            char_detection.get("unique_characters", len(detected_chars)) or len(detected_chars)
        ),
    }


def get_scene_visible_people_stats_map(char_detection: dict) -> dict:
    """按 scene_id 建立场景人数统计索引"""
    mapping = {}
    for item in char_detection.get("scene_visible_people_stats", []) or []:
        if not isinstance(item, dict):
            continue
        scene_id = item.get("scene_id")
        if scene_id is None:
            continue
        mapping[int(scene_id)] = item
    return mapping


def get_scene_visible_people_estimate(scene: dict, scene_stats_map: dict) -> int:
    """获取某场景的稳定可见人数估计"""
    scene_id_raw = scene.get("scene_id", -1)
    scene_id = int(-1 if scene_id_raw is None else scene_id_raw)
    scene_stat = scene_stats_map.get(scene_id, {})
    estimate = int(scene_stat.get("stable_visible_people_estimate", 0) or 0)
    if estimate > 0:
        return estimate
    return 0


def select_generation_characters(char_detection: dict) -> tuple[list[dict], dict]:
    """选择真正进入复刻链路的主体角色集合"""
    detected_chars = char_detection.get("characters", []) or []
    people_stats = get_visible_people_stats(char_detection)
    stable_visible = int(people_stats.get("stable_visible_people_estimate", 0) or 0)

    if not detected_chars:
        return [], {
            "mode": "no_character_detection",
            "selected_count": 0,
            "stable_visible_people_estimate": stable_visible,
            "raw_face_cluster_count": people_stats.get("raw_face_cluster_count", 0),
        }

    if stable_visible > 10:
        selected_count = 1
        mode = "crowd_mode"
    else:
        selected_count = max(1, min(len(detected_chars), stable_visible or len(detected_chars)))
        mode = "role_mode"

    return detected_chars[:selected_count], {
        "mode": mode,
        "selected_count": selected_count,
        "stable_visible_people_estimate": stable_visible,
        "raw_face_cluster_count": people_stats.get("raw_face_cluster_count", 0),
    }


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

    # 纯视觉模式下仍保留一个角色骨架，避免后续 schema 校验失败
    if not characters_from_text:
        characters_from_text.append({
            "name": "[TODO: Claude 从视觉中命名主体]",
            "role": "[TODO: Claude 根据纯视觉叙事判断主体角色]",
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
        "confidence_warning": (
            "" if has_asr else "ASR 文本为空，当前叙事线主要基于视觉推断，仅作语义骨架使用"
        ),
        "_auto_generated": True,
        "_asr_text_preview": full_text[:200] + ("..." if len(full_text) > 200 else ""),
    }


def generate_semantic_draft(
    extraction: dict,
    char_detection: dict,
    color_data: dict,
    asr_data: dict,
    video_generation: dict,
) -> dict:
    """生成 semantic_analysis.json 初稿"""
    scenes = extraction.get("scenes", []) or []
    keyframes = extraction.get("keyframes", []) or []
    detected_chars = char_detection.get("characters", []) or []
    duration = extraction.get("video_info", {}).get("duration", asr_data.get("duration", 0))
    audio_mode = infer_audio_mode(asr_data)
    understanding_mode = "asr_plus_visual" if (asr_data.get("full_text") or "").strip() else "visual_only"
    people_stats = get_visible_people_stats(char_detection)
    scene_stats_map = get_scene_visible_people_stats_map(char_detection)
    stable_visible = int(people_stats.get("stable_visible_people_estimate", 0) or 0)
    global_scale = infer_subject_scale(stable_visible or len(detected_chars))
    visual_style = build_visual_style_prompt(color_data)
    generation_contract = build_generation_contract(video_generation)
    style_consistency = build_style_consistency(color_data, video_generation, generation_contract)
    motion_type = (
        color_data.get("visual_style", {})
        .get("motion_characteristics", {})
        .get("motion_type", "")
    )
    global_camera_movement = infer_camera_movement_label(motion_type)

    scene_prisms = []
    for scene in scenes:
        sid = scene.get("scene_id", 0)
        start = scene.get("start_time", 0)
        end = scene.get("end_time", 0)
        char_labels = get_scene_character_labels(start, end, detected_chars, keyframes)
        scene_visible_estimate = get_scene_visible_people_estimate(scene, scene_stats_map)
        if scene_visible_estimate > 0 and len(char_labels) > scene_visible_estimate:
            char_labels = char_labels[:scene_visible_estimate]
        scene_scale = infer_subject_scale(scene_visible_estimate or len(char_labels))
        scene_scale_zh = SUBJECT_SCALE_LABELS.get(scene_scale, "未知规模")
        action_hint = "存在持续动作" if motion_type and motion_type != "static" else "动作较弱或偏静态"
        stage_beats = [
            "[TODO: Claude 补充起始状态]",
            "[TODO: Claude 补充中段推进]",
            "[TODO: Claude 补充结果落点]",
        ]
        scene_stat = scene_stats_map.get(int(sid), {})

        scene_prisms.append({
            "scene_id": sid,
            "time_range": f"{start:.1f}-{end:.1f}s",
            "narrative_prism": {
                "dramatic_purpose": f"{scene_scale_zh}画面，{action_hint}，[TODO: Claude 补充这段只完成什么]",
                "coarse_category": "[TODO: Claude 补充粗分类，如 indoor_group_activity / dialogue / tutorial]",
                "candidate_labels": [
                    "[TODO: 候选标签1]",
                    "[TODO: 候选标签2]",
                ],
                "final_label": "[TODO: Claude 补充最终标签；若无法确认可写 unknown]",
                "label_status": "[TODO: identified / partial / unknown]",
                "subtype_judgment": {
                    "domain": "[TODO: 训练 / 表演 / 仪式 / 课堂 / 比赛 / 商品展示 / 剧情 / 口播 / unknown]",
                    "subtype_candidates": [
                        "[TODO: 更细子类候选1]",
                        "[TODO: 更细子类候选2]",
                    ],
                    "final_subtype": "[TODO: Claude 补充更细子类；若无法确认可写 unknown]",
                    "confidence": "[TODO: high / medium / low]",
                    "decision_reason": "[TODO: 用一句话说明为什么是这个子类，而不是相似类别]",
                },
            },
            "subject_prism": {
                "primary_subjects": char_labels,
                "subject_scale": scene_scale,
                "visible_people_estimate": scene_visible_estimate,
                "visible_people_range": {
                    "min": int(scene_stat.get("min_visible_people", scene_visible_estimate or 0) or 0),
                    "max": int(scene_stat.get("max_visible_people", scene_visible_estimate or 0) or 0),
                },
                "organization": "[TODO: Claude 判断：rows / dialogue / collaboration / performance / crowd]",
                "role_relationship": "[TODO: Claude 判断主体关系，如 教学 / 协作 / 围观 / 对抗 / 表演]",
                "identity_clues": [
                    "[TODO: Claude 补充主体身份线索，如统一服装/年龄层/位置分工]",
                ],
            },
            "action_prism": {
                "primary_action": f"{action_hint}，[TODO: Claude 判断主体具体在做什么]",
                "action_pattern": "[TODO: static / repetitive / synchronized / chained / explosive]",
                "movement_intensity": "[TODO: low / medium / high]",
                "tempo_rhythm": "[TODO: steady / pulsed / accelerating / irregular]",
                "interaction_mode": "[TODO: solo / group_sync / collaboration / confrontation / observation]",
                "stage_beats": stage_beats,
                "behavior_judgment": {
                    "behavior_label": "[TODO: 主体行为标签，如 基础步法训练 / 示范带练 / 列队推进]",
                    "behavior_summary": "[TODO: 用一句话说明主体到底在做什么，不能只写抽象词]",
                    "behavior_evidence": [
                        "[TODO: 支撑该行为判断的动作证据]",
                    ],
                    "distinguishing_features": [
                        "[TODO: 能把它与相似行为区分开的动作特征]",
                    ],
                },
            },
            "scene_prism": {
                "location_space": "[TODO: Claude 判断空间类型与用途，如室内训练馆/教室/街道]",
                "lighting": "[TODO: Claude 判断光线，如暖黄顶灯/自然日光/冷色漫射]",
                "props": ["[TODO: Claude 补充关键道具或器材；无则留空列表]"],
                "evidence": {
                    "clothing": ["[TODO: Claude 检查服装是否统一、颜色和功能性]"],
                    "footwear": ["[TODO: Claude 检查鞋型，如运动鞋/舞鞋/工鞋]"],
                    "props_equipment": ["[TODO: Claude 检查是否存在关键道具或器材]"],
                    "text_signals": ["[TODO: Claude 检查墙面/衣物/字幕/OCR文字]"],
                    "environment_clues": ["[TODO: Claude 检查地板材质、布局、空间用途]"],
                },
                "evidence_chain": {
                    "direct_evidence": ["[TODO: 最直接支撑判断的证据，如鞋型 / 文字 / 关键动作]"],
                    "supporting_evidence": ["[TODO: 辅助支撑的证据，如队形 / 服装 / 场地]"],
                    "counter_hypotheses": ["[TODO: 容易混淆的解释，如健身操 / 演出 / 普通活动]"],
                    "unresolved_points": ["[TODO: 当前还不能完全确认的点；若无可留空列表]"],
                },
            },
            "camera_prism": {
                "shot_type": "[TODO: visible_subject / offscreen_reaction / transition_reveal / free_atmosphere]",
                "framing": "[TODO: wide / medium / close]",
                "camera_angle": "[TODO: eye_level / low_angle / high_angle]",
                "camera_movement": global_camera_movement,
                "camera_focus": "[TODO: Claude 补充镜头关注点，如队列整体/主角前排/局部动作]",
            },
            "constraint_prism": {
                "must_keep": ["[TODO: Claude 补充该场景必须保留的视觉事实]"],
                "should_keep": ["[TODO: Claude 补充建议保留但允许近似的事实]"],
                "must_not_change": ["[TODO: Claude 补充不能改掉的识别点]"],
                "must_not_generate": ["[TODO: Claude 补充不能生成错的方向]"],
                "continuity_focus": ["[TODO: Claude 补充需要持续稳定的空间/动作/主体关系]"],
                "negative_constraints": ["[TODO: Claude 单列最容易生成错的高风险点]"],
            },
        })

    return {
        "analysis_level": "level_1" if (asr_data.get("full_text") or "").strip() else "level_3",
        "media_baseline": {
            "source_resolution": video_generation.get("source_resolution", "1280x720"),
            "source_aspect_ratio": video_generation.get("source_aspect_ratio", "16:9"),
            "orientation": video_generation.get("orientation", "horizontal"),
            "duration": round(duration or 0, 2),
            "scene_count": len(scenes),
            "keyframe_count": len(keyframes),
            "audio_mode": audio_mode,
            "understanding_mode": understanding_mode,
        },
        "global_summary": {
            "content_mode": "[TODO: Claude 判断：剧情 / 口播 / 纪录 / 教程 / 表演 / 训练 / 商品展示 / 纯氛围]",
            "visual_style": visual_style,
            "stable_visible_people_estimate": stable_visible,
            "raw_face_cluster_count": people_stats.get("raw_face_cluster_count", 0),
            "open_world_status": "[TODO: identified / partial / unknown]",
            "summary_note": (
                f"整体主体规模倾向为 {global_scale}，稳定可见人数估计约 {stable_visible or 'unknown'} 人，"
                f"跨帧人脸聚类数为 {people_stats.get('raw_face_cluster_count', 0)}（仅作底层检测参考），"
                f"镜头运动倾向为 {global_camera_movement}。"
                "[TODO: Claude 补充总体判断与不确定性]"
            ),
        },
        "generation_contract": generation_contract,
        "style_consistency": style_consistency,
        "scene_prisms": scene_prisms,
        "inference_notes": "[TODO: Claude 说明不确定点、候选判断与缺失证据]",
        "_auto_generated": True,
    }


def generate_coherence_draft(
    char_detection: dict,
    narrative: dict,
) -> dict:
    """生成 coherence_analysis.json 初稿"""
    characters = []
    detected, selection_meta = select_generation_characters(char_detection)
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
        "_analysis_note": {
            "character_selection_mode": selection_meta.get("mode"),
            "stable_visible_people_estimate": selection_meta.get("stable_visible_people_estimate", 0),
            "raw_face_cluster_count": selection_meta.get("raw_face_cluster_count", 0),
            "selected_character_count": selection_meta.get("selected_count", len(characters)),
        },
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
    video_generation: dict,
    generation_contract: dict,
    style_consistency: dict,
    semantic_scene_prisms: List[dict] | None = None,
) -> dict:
    """生成 scene_prompts.json 初稿"""
    visual_style_prompt = build_visual_style_prompt(color_data).replace("写实影像风格", "电影感")
    prompt_prefix = video_generation.get(
        "prompt_prefix",
        "[TODO: 按 target_visual_mode 填写统一前缀], 16:9 widescreen, 1280x720",
    )
    scene_stats_map = get_scene_visible_people_stats_map(char_detection)
    selected_chars, selection_meta = select_generation_characters(char_detection)
    semantic_map = {
        int(item.get("scene_id", 0)): item
        for item in (semantic_scene_prisms or [])
        if isinstance(item, dict)
    }

    # 角色列表（从 character_detection 映射）
    detected_chars = selected_chars
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
    core_outfit_anchor_ids = [det.get("label", "unknown") for det in detected_chars[: min(3, len(detected_chars))]]
    for det in detected_chars:
        char_id = det.get("label", "unknown")
        character_ref_prompts.append({
            "character_id": char_id,
            "reference_type": "identity_portrait",
            "prompt": (
                "[TODO: 先读取 generation_contract.character_reference_mode，"
                "写 identity_portrait 单人身份参考图提示词；锁定脸型、发型、上衣领口，禁止跨形态关键词]"
            ),
        })
        if char_id in core_outfit_anchor_ids:
            character_ref_prompts.append({
                "character_id": char_id,
                "reference_type": "full_body_outfit",
                "prompt": (
                    "[TODO: 先读取 generation_contract.character_reference_mode，"
                    "写 full_body_outfit 单人全身服装锚点提示词；必须完整露出长裤和鞋子，用于避免步骤9换衣和换鞋]"
                ),
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
        scene_visible_estimate = get_scene_visible_people_estimate(scene, scene_stats_map)
        visible_characters = get_scene_visible_characters(start, end, detected_chars, keyframes)
        semantic = semantic_map.get(int(sid), {})
        narrative_prism = semantic.get("narrative_prism", {}) if isinstance(semantic, dict) else {}
        action_prism = semantic.get("action_prism", {}) if isinstance(semantic, dict) else {}
        scene_prism = semantic.get("scene_prism", {}) if isinstance(semantic, dict) else {}
        constraint_prism = semantic.get("constraint_prism", {}) if isinstance(semantic, dict) else {}
        subtype_judgment = narrative_prism.get("subtype_judgment", {}) if isinstance(narrative_prism, dict) else {}
        behavior_judgment = action_prism.get("behavior_judgment", {}) if isinstance(action_prism, dict) else {}
        scene_evidence = scene_prism.get("evidence", {}) if isinstance(scene_prism, dict) else {}
        evidence_to_preserve = []
        if isinstance(scene_evidence, dict):
            for key in ("footwear", "text_signals", "props_equipment", "environment_clues", "clothing"):
                value = scene_evidence.get(key, [])
                if isinstance(value, list):
                    evidence_to_preserve.extend(value[:2])
        if not evidence_to_preserve:
            evidence_to_preserve = ["[TODO: 从 semantic_analysis.scene_prism.evidence 提取必须保留的证据]"]
        negative_constraints = (
            constraint_prism.get("negative_constraints")
            if isinstance(constraint_prism, dict)
            else None
        )
        if not isinstance(negative_constraints, list) or not negative_constraints:
            negative_constraints = ["[TODO: 从 semantic_analysis.constraint_prism 提取最容易生成错的点]"]

        scene_list.append({
            "scene_id": sid,
            "prompt": (
                f"{prompt_prefix}, [TODO: 先读取 generation_contract.scene_generation_mode，"
                "再把 semantic_anchor.content_type / subtype_judgment / behavior_summary / evidence_to_preserve / "
                "negative_constraints 明确写进 prompt；多人场景要明确不同角色的脸型/发型差异，"
                "并写清所有可见成员都穿什么长裤和鞋子，避免同脸与换衣]"
            ),
            "duration": duration,
            "main_character": main_char,
            "visible_characters": visible_characters,
            "time_range": f"{start:.1f}-{end:.1f}s",
            "visible_people_estimate": scene_visible_estimate,
            "semantic_anchor": {
                "content_type": subtype_judgment.get(
                    "domain",
                    "[TODO: 从 semantic_analysis.narrative_prism.subtype_judgment.domain 继承]",
                ),
                "subtype_judgment": subtype_judgment.get(
                    "final_subtype",
                    "[TODO: 从 semantic_analysis.narrative_prism.subtype_judgment.final_subtype 继承]",
                ),
                "behavior_summary": behavior_judgment.get(
                    "behavior_summary",
                    "[TODO: 从 semantic_analysis.action_prism.behavior_judgment.behavior_summary 继承]",
                ),
                "evidence_to_preserve": evidence_to_preserve,
                "negative_constraints": negative_constraints,
            },
        })

    return {
        "visual_style_prompt": visual_style_prompt,
        "generation_contract": generation_contract,
        "style_consistency": style_consistency,
        "video_generation": video_generation,
        "characters": characters,
        "character_ref_prompts": character_ref_prompts,
        "scenes": scene_list,
        "_analysis_note": {
            "character_selection_mode": selection_meta.get("mode"),
            "stable_visible_people_estimate": selection_meta.get("stable_visible_people_estimate", 0),
            "raw_face_cluster_count": selection_meta.get("raw_face_cluster_count", 0),
            "selected_character_count": selection_meta.get("selected_count", len(characters)),
            "core_outfit_anchor_ids": core_outfit_anchor_ids,
        },
        "_auto_generated": True,
    }


def generate_tts_guide_draft(asr_data: dict) -> dict:
    """生成 tts_guide.json 初稿"""
    voice_style = asr_data.get("voice_style", {})
    full_text = asr_data.get("full_text", "")
    duration = asr_data.get("duration", 0)

    if not full_text.strip():
        return {
            "_skipped": True,
            "skip_reason": "ASR 文本为空，当前项目应跳过 TTS 复刻链路",
            "tts_parameters": {
                "gender": "[SKIPPED_NO_ASR]",
                "tone": "平稳",
                "speed": "中等",
                "emotion": "中性",
                "rhythm": "平稳节奏",
            },
            "reference_text": "[SKIPPED_NO_ASR]",
            "duration_target": 0,
            "_auto_generated": True,
        }

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
    print("初稿生成器：自动生成步骤3.5-7（含3.6六棱镜语义骨架）的JSON初稿")
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
    video_generation = build_video_generation_profile(extraction)

    # 如果没有场景数据，构造一个默认场景
    if not scenes:
        duration = asr_data.get("duration", 30)
        scenes = [{"scene_id": 0, "start_time": 0, "end_time": duration}]

    # 生成初稿
    print("\n[生成] 生成6个JSON初稿...")

    # 步骤3.5: narrative_analysis
    narrative = generate_narrative_draft(asr_data)
    save_json(narrative, output_path / "analysis" / "narrative_analysis.json")

    # 步骤3.6: semantic_analysis
    semantic = generate_semantic_draft(
        extraction,
        char_detection,
        color_data,
        asr_data,
        video_generation,
    )
    save_json(semantic, output_path / "analysis" / "semantic_analysis.json")

    # 步骤4: coherence_analysis
    coherence = generate_coherence_draft(char_detection, narrative)
    save_json(coherence, output_path / "analysis" / "coherence_analysis.json")

    # 步骤5: audio_visual_correlation
    correlation = generate_correlation_draft(asr_data, scenes)
    save_json(correlation, output_path / "analysis" / "audio_visual_correlation.json")

    # 步骤6: scene_prompts
    scene_prompts = generate_scene_prompts_draft(
        scenes,
        keyframes,
        char_detection,
        color_data,
        video_generation,
        semantic.get("generation_contract", {}),
        semantic.get("style_consistency", {}),
        semantic.get("scene_prisms", []),
    )
    save_json(scene_prompts, output_path / "prompts" / "scene_prompts.json")

    # 步骤7: tts_guide
    tts_guide = generate_tts_guide_draft(asr_data)
    save_json(tts_guide, output_path / "prompts" / "tts_guide.json")

    # 统计
    todo_count = _count_todos(narrative, semantic, coherence, correlation, scene_prompts, tts_guide)
    print(f"\n[完成] 6个初稿已生成")
    print(f"  待 Claude 补充的 [TODO] 字段: {todo_count} 处")
    print(f"  Claude 接下来需要：")
    print(f"    1. 阅读 ASR 文本和关键帧图片")
    print(f"    2. 先完善 semantic_analysis.json 中的 6 棱镜结构")
    print(f"    3. 用 read_image 查看角色代表面部")
    print(f"    4. 填写所有 [TODO] 占位符")
    print(f"    5. 运行 schema_validator.py 校验后保存")
    print("=" * 70)


def _count_todos(*dicts) -> int:
    """递归统计所有 [TODO] 占位符"""
    count = 0
    for d in dicts:
        text = json.dumps(d, ensure_ascii=False)
        count += text.count("[TODO")
    return count


def main():
    parser = argparse.ArgumentParser(
        description="初稿生成器：自动生成步骤3.5-7（含3.6六棱镜语义骨架）的JSON初稿"
    )
    parser.add_argument("--input_dir", default="output", help="输入目录（含 keyframes/ 和 analysis/）")
    parser.add_argument("--output_dir", default="output", help="输出目录")

    args = parser.parse_args()
    run(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
