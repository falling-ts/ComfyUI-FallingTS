# Volcengine Seedance 2.0 API 请求/响应模型

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ─── 请求模型 ──────────────────────────────────────────────

class TaskTextContent(BaseModel):
    type: str = "text"
    text: str = Field(..., min_length=1)


class TaskImageContentUrl(BaseModel):
    url: str = Field(..., description="图片 URL、Base64 或 asset:// ID")


class TaskImageContent(BaseModel):
    type: str = "image_url"
    image_url: TaskImageContentUrl
    role: str | None = None  # first_frame / last_frame / reference_image


class TaskVideoContentUrl(BaseModel):
    url: str = Field(..., description="视频 URL 或 asset:// ID")


class TaskVideoContent(BaseModel):
    type: str = "video_url"
    video_url: TaskVideoContentUrl
    role: str | None = "reference_video"


class TaskAudioContentUrl(BaseModel):
    url: str = Field(..., description="音频 URL、Base64 或 asset:// ID")


class TaskAudioContent(BaseModel):
    type: str = "audio_url"
    audio_url: TaskAudioContentUrl
    role: str | None = "reference_audio"


class TaskCreationRequest(BaseModel):
    """创建视频生成任务的请求体。"""
    model: str = Field(..., description="模型 ID (如 doubao-seedance-2-0-260615)")
    content: list[TaskTextContent | TaskImageContent | TaskVideoContent | TaskAudioContent] = Field(
        ..., min_length=1, description="输入内容列表"
    )
    generate_audio: bool | None = Field(None, description="是否生成音频")
    resolution: str | None = Field(None, description="输出分辨率: 480p/720p/1080p/4k")
    ratio: str | None = Field(None, description="宽高比: 16:9/4:3/1:1/3:4/9:16/21:9/adaptive")
    duration: int | None = Field(None, ge=4, le=15, description="视频时长(秒)")
    seed: int | None = Field(None, ge=0, le=2147483647, description="随机种子")
    watermark: bool | None = Field(False, description="是否添加水印")


# ─── 响应模型 ──────────────────────────────────────────────

class TaskStatusError(BaseModel):
    code: int | None = None
    message: str | None = None


class TaskContentResponse(BaseModel):
    video_url: str | None = Field(None, description="生成视频的 URL")
    video_duration: float | None = None
    audio_url: str | None = None


class TaskCreationResponse(BaseModel):
    """创建任务后的响应。"""
    id: str = Field(..., description="任务 ID")
    model: str | None = None
    status: str | None = None
    content: TaskContentResponse | None = None
    error: TaskStatusError | None = None


class TaskStatusResponse(BaseModel):
    """查询任务状态的响应。"""
    id: str | None = None
    status: str = Field(..., description="任务状态: created/queued/processing/succeeded/failed")
    model: str | None = None
    content: TaskContentResponse | None = None
    error: TaskStatusError | None = None
    token_count: int | None = None
    seed: int | None = None


# ─── 模型配置 ──────────────────────────────────────────────

# 模型 ID 映射
# 注意: 国内端点 (ark.cn-beijing.volces.com) 用 doubao- 前缀
#       国际端点 (ark.ap-southeast.bytepluses.com) 用 dreamina- 前缀
# 版本号 260615 = 2026-06-15 发布
SEEDANCE_MODELS: dict[str, str] = {
    "Seedance 2.0": "doubao-seedance-2-0-260615",
    "Seedance 2.0 Fast": "doubao-seedance-2-0-fast-260615",
    "Seedance 2.0 Mini": "doubao-seedance-2-0-mini-260615",
}

# 每个模型的可用分辨率和参考视频像素限制
MODEL_RESOLUTIONS: dict[str, list[str]] = {
    "Seedance 2.0": ["480p", "720p", "1080p", "4k"],
    "Seedance 2.0 Fast": ["480p", "720p"],
    "Seedance 2.0 Mini": ["480p", "720p"],
}

MODEL_PIXEL_LIMITS: dict[str, dict[str, dict[str, int]]] = {
    "doubao-seedance-2-0-260615": {
        "480p": {"min": 409_600, "max": 927_408},
        "720p": {"min": 409_600, "max": 927_408},
        "1080p": {"min": 409_600, "max": 2_073_600},
    },
    "doubao-seedance-2-0-fast-260615": {
        "480p": {"min": 409_600, "max": 927_408},
        "720p": {"min": 409_600, "max": 927_408},
    },
    "doubao-seedance-2-0-mini-260615": {
        "480p": {"min": 409_600, "max": 927_408},
        "720p": {"min": 409_600, "max": 927_408},
    },
}

SEEDANCE2_PRICE_PER_1K_TOKENS: dict[tuple[str, bool, str], float] = {
    ("doubao-seedance-2-0-260615", False, "480p"): 0.0070,
    ("doubao-seedance-2-0-260615", True, "480p"): 0.0043,
    ("doubao-seedance-2-0-260615", False, "720p"): 0.0070,
    ("doubao-seedance-2-0-260615", True, "720p"): 0.0043,
    ("doubao-seedance-2-0-260615", False, "1080p"): 0.0077,
    ("doubao-seedance-2-0-260615", True, "1080p"): 0.0047,
    ("doubao-seedance-2-0-260615", False, "4k"): 0.0040,
    ("doubao-seedance-2-0-260615", True, "4k"): 0.0024,
    ("doubao-seedance-2-0-fast-260615", False, "480p"): 0.0056,
    ("doubao-seedance-2-0-fast-260615", True, "480p"): 0.0033,
    ("doubao-seedance-2-0-fast-260615", False, "720p"): 0.0056,
    ("doubao-seedance-2-0-fast-260615", True, "720p"): 0.0033,
    ("doubao-seedance-2-0-mini-260615", False, "480p"): 0.0035,
    ("doubao-seedance-2-0-mini-260615", True, "480p"): 0.0021,
    ("doubao-seedance-2-0-mini-260615", False, "720p"): 0.0035,
    ("doubao-seedance-2-0-mini-260615", True, "720p"): 0.0021,
}


def seedance2_price(model_id: str, has_video_input: bool, resolution: str) -> float | None:
    return SEEDANCE2_PRICE_PER_1K_TOKENS.get((model_id, has_video_input, resolution))


def price_extractor_fn(model_id: str, has_video_input: bool, resolution: str):
    """返回一个 price_extractor 闭包, 用于 poll_op。"""
    rate = seedance2_price(model_id, has_video_input, resolution)
    if rate is None:
        return None

    def extractor(resp: Any) -> float | None:
        if not isinstance(resp, dict):
            return None
        token_count = resp.get("token_count")
        if token_count is not None and isinstance(token_count, (int, float)):
            return token_count / 1000 * rate
        return None
    return extractor
