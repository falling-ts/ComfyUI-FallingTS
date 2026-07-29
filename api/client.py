# Volcengine API 客户端 - 直接调用 Seedance 2.0 接口

from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import Any, Callable

import torch
from aiohttp import ClientError
from PIL import Image

from comfy_api.latest import IO, InputImpl
from comfy_api_nodes.util.client import (
    ApiEndpoint,
    poll_op_raw,
    sync_op_raw,
)
from comfy_api_nodes.util.conversions import (
    bytesio_to_image_tensor,
    tensor_to_bytesio,
)
from comfy_api_nodes.util.download_helpers import download_url_to_video_output
from comfy_api_nodes.util.upload_helpers import (
    upload_images_to_comfyapi,
    upload_video_to_comfyapi,
)

from .config import get_api_key
from .models import (
    TaskCreationRequest,
    TaskCreationResponse,
    TaskStatusResponse,
    TaskTextContent,
    TaskImageContent,
    TaskImageContentUrl,
    TaskVideoContent,
    TaskVideoContentUrl,
    TaskAudioContent,
    TaskAudioContentUrl,
    price_extractor_fn,
)

logger = logging.getLogger(__name__)

# Volcengine Seedance 2.0 API 端点
VOLC_API_BASE = "https://ark.cn-beijing.volces.com"
TASK_ENDPOINT = f"{VOLC_API_BASE}/api/v3/contents/generations/tasks"


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _image_to_base64(image: torch.Tensor, fmt: str = "png") -> str:
    """将图像张量转为 base64 字符串。"""
    buf = BytesIO()
    pil_img = tensor_to_pil(image)
    pil_img.save(buf, format=fmt.upper())
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/{fmt};base64,{b64}"


def tensor_to_pil(image: torch.Tensor) -> Image.Image:
    """将 [B, H, W, C] 张量转为 PIL Image。"""
    if image.dim() == 4:
        image = image[0]
    img_np = (image.cpu().numpy() * 255).clip(0, 255).astype("uint8")
    return Image.fromarray(img_np)


async def upload_images_as_base64(
    cls: type[IO.ComfyNode],
    images: dict[str, torch.Tensor],
) -> dict[str, str]:
    """将多张图像转为 base64 URL。"""
    urls: dict[str, str] = {}
    for key, img in images.items():
        urls[key] = _image_to_base64(img)
    return urls


async def upload_images_to_urls(
    cls: type[IO.ComfyNode],
    images: dict[str, torch.Tensor],
) -> dict[str, str]:
    """将多张图像上传到 Comfy 托管服务, 返回 URL。"""
    urls: dict[str, str] = {}
    for key, img in images.items():
        uploaded = await upload_images_to_comfyapi(cls, img, max_images=1, wait_label=f"Uploading image")
        if uploaded:
            urls[key] = uploaded[0]
    return urls


async def upload_videos_to_urls(
    cls: type[IO.ComfyNode],
    videos: dict[str, InputImpl.VideoFromFile],
) -> dict[str, str]:
    """将多个视频上传到 Comfy 托管服务, 返回 URL。"""
    urls: dict[str, str] = {}
    for key, video in videos.items():
        url = await upload_video_to_comfyapi(cls, video, wait_label=f"Uploading video")
        urls[key] = url
    return urls


def _resolve_api_key(api_key: str) -> str:
    """解析 API Key: 优先用传入值, 否则从环境变量读取。"""
    if api_key:
        return api_key
    env_key = get_api_key()
    if env_key:
        return env_key
    raise ValueError(
        "Volcengine API Key 未配置。请在节点中输入, "
        "或在 .env 文件中设置 VOLC_ENGINE_API_KEY=your_key"
    )


async def create_seedance_task(
    cls: type[IO.ComfyNode],
    api_key: str,
    model_id: str,
    *,
    prompt: str | None = None,
    resolution: str = "720p",
    ratio: str = "16:9",
    duration: int = 7,
    generate_audio: bool = True,
    seed: int = 0,
    watermark: bool = False,
    image_base64s: dict[str, str] | None = None,
    image_roles: dict[str, str] | None = None,
    video_urls: dict[str, str] | None = None,
    audio_urls: dict[str, str] | None = None,
) -> str:
    """创建 Seedance 2.0 视频生成任务, 返回 task_id。"""
    content: list[dict] = []

    if prompt:
        content.append({"type": "text", "text": prompt})

    if image_base64s:
        for key, b64_url in image_base64s.items():
            role = (image_roles or {}).get(key, "reference_image")
            content.append({
                "type": "image_url",
                "image_url": {"url": b64_url},
                "role": role,
            })

    if video_urls:
        for key, url in video_urls.items():
            content.append({
                "type": "video_url",
                "video_url": {"url": url},
                "role": "reference_video",
            })

    if audio_urls:
        for key, url in audio_urls.items():
            content.append({
                "type": "audio_url",
                "audio_url": {"url": url},
                "role": "reference_audio",
            })

    payload = {
        "model": model_id,
        "content": content,
        "resolution": resolution,
        "ratio": ratio,
        "duration": duration,
        "seed": seed,
    }
    if generate_audio is not None:
        payload["generate_audio"] = generate_audio
    if watermark:
        payload["watermark"] = watermark

    resolved_key = _resolve_api_key(api_key)
    logger.debug("Creating Seedance task: model=%s, resolution=%s, duration=%ds", model_id, resolution, duration)

    resp = await sync_op_raw(
        cls,
        ApiEndpoint(
            path=TASK_ENDPOINT,
            method="POST",
            headers=_auth_headers(resolved_key),
        ),
        data=payload,
        timeout=120,
        max_retries=3,
        wait_label="Creating task",
    )

    if not isinstance(resp, dict):
        raise RuntimeError(f"Unexpected response from task creation: {resp}")

    if "id" not in resp:
        error_msg = resp.get("error", {}).get("message", str(resp))
        raise RuntimeError(f"Failed to create task: {error_msg}")

    task_id: str = resp["id"]
    logger.info("Task created: %s", task_id)
    return task_id


async def poll_seedance_task(
    cls: type[IO.ComfyNode],
    api_key: str,
    task_id: str,
    *,
    model_id: str = "",
    has_video_input: bool = False,
    resolution: str = "720p",
    poll_interval: float = 9.0,
) -> str:
    """轮询 Seedance 2.0 任务直到完成, 返回结果视频 URL。"""
    resolved_key = _resolve_api_key(api_key)
    price_fn = price_extractor_fn(model_id, has_video_input, resolution)

    resp = await poll_op_raw(
        cls,
        poll_endpoint=ApiEndpoint(
            path=f"{TASK_ENDPOINT}/{task_id}",
            method="GET",
            headers=_auth_headers(resolved_key),
        ),
        status_extractor=lambda r: r.get("status") if isinstance(r, dict) else None,
        progress_extractor=lambda r: None,
        price_extractor=price_fn,
        completed_statuses=["succeeded", "succeed", "success", "completed"],
        failed_statuses=["failed", "cancelled", "canceled", "error"],
        queued_statuses=["created", "queued", "queueing", "submitted", "initializing", "wait", "in_queue"],
        poll_interval=poll_interval,
        max_poll_attempts=480,
        timeout_per_poll=120,
        extra_text=model_id,
    )

    if not isinstance(resp, dict):
        raise RuntimeError(f"Unexpected poll response: {resp}")

    status = resp.get("status")
    if status in ("failed", "cancelled", "canceled", "error"):
        error = resp.get("error", {})
        code = error.get("code", "") if isinstance(error, dict) else ""
        msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        raise RuntimeError(f"Task failed (status={status}, code={code}): {msg}")

    content = resp.get("content")
    if not content or not isinstance(content, dict):
        raise RuntimeError(f"Task completed but no content: {resp}")

    video_url = content.get("video_url")
    if not video_url:
        raise RuntimeError(f"Task completed but no video_url in content: {content}")

    logger.info("Task completed: %s, video_url: %s", task_id, video_url)
    return video_url


async def download_video(url: str, cls: type[IO.ComfyNode]) -> InputImpl.VideoFromFile:
    """下载视频并返回 VideoFromFile。"""
    return await download_url_to_video_output(url, cls=cls)
