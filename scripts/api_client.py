#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共用 API 客户端
提供凭证加载、图片编码、Seedance/Seedream API 调用封装
"""

import asyncio
import base64
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

import aiohttp
import yaml

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """加载 api_config.yaml 配置"""
    if config_path is None:
        config_path = PROJECT_DIR / "config" / "api_config.yaml"
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_credentials(
    provider: str,
    config: dict[str, Any] | None = None,
    api_key_override: str | None = None,
) -> dict[str, str]:
    """获取 API 凭证，优先级：参数 > 环境变量 > api_keys.yaml"""
    if config is None:
        config = load_config()

    result: dict[str, str] = {}

    # 从 api_config.yaml 获取 api_base
    providers = config.get("providers", {})
    provider_cfg = providers.get(provider, {})
    if isinstance(provider_cfg, dict):
        result["api_base"] = provider_cfg.get("api_base", "")

    # 1. 参数覆盖
    if api_key_override:
        result["api_key"] = api_key_override
        return result

    # 2. 环境变量
    env_key_map = {
        "volcengine": "VOLCENGINE_API_KEY",
        "byteplus": "BYTEPLUS_API_KEY",
        "apimart": "APIMART_API_KEY",
        "fal": "FAL_KEY",
    }
    env_base_map = {
        "volcengine": "VOLCENGINE_API_BASE",
        "byteplus": "BYTEPLUS_API_BASE",
        "apimart": "APIMART_API_BASE",
        "fal": "FAL_API_BASE",
    }

    env_key = env_key_map.get(provider, f"{provider.upper()}_API_KEY")
    env_val = os.environ.get(env_key)
    if env_val:
        result["api_key"] = env_val
    env_base = env_base_map.get(provider, f"{provider.upper()}_API_BASE")
    env_base_val = os.environ.get(env_base)
    if env_base_val:
        result["api_base"] = env_base_val

    if result.get("api_key"):
        return result

    # 3. api_keys.yaml 文件
    keys_path = PROJECT_DIR / "config" / "api_keys.yaml"
    if keys_path.exists():
        try:
            with open(keys_path, "r", encoding="utf-8") as f:
                keys_data = yaml.safe_load(f) or {}
            # 支持多种 key 格式：volcengine.api_key / Volcengine.api_key
            for key_name in [provider, provider.lower(), provider.capitalize()]:
                section = keys_data.get(key_name, {})
                if isinstance(section, dict):
                    if section.get("api_key"):
                        result["api_key"] = section["api_key"]
                    if section.get("api_base"):
                        result["api_base"] = section["api_base"]
                    break
        except Exception as e:
            logger.warning(f"读取 api_keys.yaml 失败: {e}")

    return result


def get_model_config(module: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """获取指定模块的模型配置"""
    if config is None:
        config = load_config()
    return dict(config.get("models", {}).get(module, {}))


def encode_image_base64(path: Path) -> str:
    """将图片文件编码为 data URL"""
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


async def download_file(session: aiohttp.ClientSession, url: str, output: Path) -> bool:
    """下载文件到本地"""
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(await resp.read())
                logger.info(f"已下载: {output}")
                return True
            logger.warning(f"下载失败 ({resp.status}): {url[:100]}")
            return False
    except Exception as e:
        logger.warning(f"下载异常: {e}")
        return False


# ---------------------------------------------------------------------------
# Seedream 图像生成
# ---------------------------------------------------------------------------

async def generate_seedream_image(
    prompt: str,
    output_path: Path,
    config: dict[str, Any] | None = None,
    api_key_override: str | None = None,
    image_urls: list[str] | None = None,
) -> bool:
    """调用 Seedream API 生成图片"""
    if config is None:
        config = load_config()
    img_cfg = get_model_config("image", config)
    provider = img_cfg.get("provider", "volcengine")
    creds = get_credentials(provider, config, api_key_override)

    if not creds.get("api_key"):
        logger.error(f"{provider} api_key 未配置")
        return False

    payload = {
        "model": img_cfg.get("model", "doubao-seedream-4-0-250828"),
        "prompt": prompt,
        "size": img_cfg.get("size", "2K"),
        "response_format": img_cfg.get("response_format", "url"),
        "watermark": img_cfg.get("watermark", False),
    }
    if image_urls:
        payload["image_urls"] = image_urls

    timeout = img_cfg.get("timeout", 120)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(
                f"{creds['api_base']}/images/generations",
                headers={
                    "Authorization": f"Bearer {creds['api_key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Seedream 请求失败 ({resp.status}): {body[:200]}")
                    return False
                data = await resp.json()
                url = data.get("data", [{}])[0].get("url")
                if url:
                    return await download_file(session, url, output_path)
                logger.error(f"Seedream 返回无 URL: {data}")
                return False
    except Exception as e:
        logger.error(f"Seedream 异常: {e}")
        return False


# ---------------------------------------------------------------------------
# Seedance 视频生成
# ---------------------------------------------------------------------------

async def submit_seedance_task(
    prompt: str,
    reference_images: list[Path],
    duration: int = 10,
    config: dict[str, Any] | None = None,
    api_key_override: str | None = None,
) -> str | None:
    """提交 Seedance 视频生成任务，返回 task_id"""
    if config is None:
        config = load_config()
    video_cfg = get_model_config("video", config)
    provider = video_cfg.get("provider", "volcengine")
    creds = get_credentials(provider, config, api_key_override)

    if not creds.get("api_key"):
        logger.error(f"{provider} api_key 未配置")
        return None

    # 构建 content 数组
    content: list[dict[str, Any]] = []

    # 构建提示词中的 @图片N 调用语句
    ref_callouts: list[str] = []
    for idx, ref_path in enumerate(reference_images, start=1):
        if not ref_path.exists():
            continue
        data_url = encode_image_base64(ref_path)
        content.append({
            "type": "image_url",
            "image_url": {"url": data_url},
            "role": "reference_image",
        })
        ref_callouts.append(f"@图片{idx} 作为参考。")

    # 拼接参考图调用 + 提示词
    final_prompt = prompt
    if ref_callouts:
        parts = ["【参考素材调用】", *ref_callouts, "", "【生成要求】", prompt]
        final_prompt = "\n".join(parts)

    content.insert(0, {"type": "text", "text": final_prompt})

    payload = {
        "model": video_cfg.get("model", "doubao-seedance-2-0-fast-260128"),
        "content": content,
        "duration": duration,
        "ratio": video_cfg.get("ratio", "16:9"),
        "resolution": video_cfg.get("resolution", "720p"),
        "generate_audio": video_cfg.get("generate_audio", True),
        "watermark": video_cfg.get("watermark", False),
    }

    submit_timeout = video_cfg.get("submit_timeout", 30)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=submit_timeout)) as session:
            async with session.post(
                f"{creds['api_base']}/contents/generations/tasks",
                headers={
                    "Authorization": f"Bearer {creds['api_key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Seedance 提交失败 ({resp.status}): {body[:200]}")
                    return None
                data = await resp.json()
                task_id = data.get("id")
                if task_id:
                    logger.info(f"Seedance 任务已提交: {task_id} ({len(reference_images)} 张参考图)")
                else:
                    logger.error(f"Seedance 返回无 task_id: {data}")
                return task_id
    except Exception as e:
        logger.error(f"Seedance 提交异常: {e}")
        return None


async def poll_seedance_task(
    task_id: str,
    output_path: Path,
    config: dict[str, Any] | None = None,
    api_key_override: str | None = None,
) -> bool:
    """轮询 Seedance 任务直到完成，下载视频"""
    if config is None:
        config = load_config()
    video_cfg = get_model_config("video", config)
    provider = video_cfg.get("provider", "volcengine")
    creds = get_credentials(provider, config, api_key_override)

    poll_interval = video_cfg.get("poll_interval", 5)
    poll_max = video_cfg.get("poll_max_attempts", 120)
    poll_timeout = video_cfg.get("poll_timeout", 15)

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=poll_timeout)) as session:
            for attempt in range(poll_max):
                await asyncio.sleep(poll_interval)
                async with session.get(
                    f"{creds['api_base']}/contents/generations/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {creds['api_key']}"},
                ) as resp:
                    if resp.status != 200:
                        continue
                    result = await resp.json()
                    status = result.get("status", "")

                    if status == "succeeded":
                        video_url = (result.get("content") or {}).get("video_url")
                        if video_url:
                            logger.info("Seedance 生成成功，下载视频...")
                            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as dl_session:
                                return await download_file(dl_session, video_url, output_path)
                        logger.error("Seedance 成功但无 video_url")
                        return False

                    if status in ("failed", "cancelled"):
                        error = result.get("error")
                        logger.error(f"Seedance 任务 {status}: {error}")
                        return False

                    # running / pending
                    if attempt % 6 == 0:
                        elapsed = attempt * poll_interval
                        logger.info(f"Seedance 生成中... ({elapsed}s)")

        logger.error(f"Seedance 超时（{poll_max * poll_interval}s）")
        return False
    except Exception as e:
        logger.error(f"Seedance 轮询异常: {e}")
        return False


async def generate_seedance_video(
    prompt: str,
    reference_images: list[Path],
    output_path: Path,
    duration: int = 10,
    config: dict[str, Any] | None = None,
    api_key_override: str | None = None,
) -> bool:
    """一步到位：提交 + 轮询 + 下载"""
    task_id = await submit_seedance_task(
        prompt, reference_images, duration, config, api_key_override
    )
    if not task_id:
        return False
    return await poll_seedance_task(task_id, output_path, config, api_key_override)
