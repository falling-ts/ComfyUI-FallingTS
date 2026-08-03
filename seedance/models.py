# 模型配置与定价数据

from __future__ import annotations

from typing import Any


# ─── 模型配置 ──────────────────────────────────────────────

# 模型 ID 映射
# 注意: 国内端点 (ark.cn-beijing.volces.com) 用 doubao- 前缀
#       国际端点 (ark.ap-southeast.bytepluses.com) 用 dreamina- 前缀
# 版本号 260615 = 2026-06-15 发布
SEEDANCE_MODELS: dict[str, str] = {
    "Seedance 2.0": "doubao-seedance-2-0-260128",
    "Seedance 2.0 Fast": "doubao-seedance-2-0-fast-260128",
    "Seedance 2.0 Mini": "doubao-seedance-2-0-mini-260615",
}

# 每个模型的可用分辨率和参考视频像素限制
MODEL_RESOLUTIONS: dict[str, list[str]] = {
    "Seedance 2.0": ["480p", "720p", "1080p", "4k"],
    "Seedance 2.0 Fast": ["480p", "720p"],
    "Seedance 2.0 Mini": ["480p", "720p"],
}

MODEL_PIXEL_LIMITS: dict[str, dict[str, dict[str, int]]] = {
    "doubao-seedance-2-0-260128": {
        "480p": {"min": 409_600, "max": 927_408},
        "720p": {"min": 409_600, "max": 927_408},
        "1080p": {"min": 409_600, "max": 2_073_600},
    },
    "doubao-seedance-2-0-fast-260128": {
        "480p": {"min": 409_600, "max": 927_408},
        "720p": {"min": 409_600, "max": 927_408},
    },
    "doubao-seedance-2-0-mini-260615": {
        "480p": {"min": 409_600, "max": 927_408},
        "720p": {"min": 409_600, "max": 927_408},
    },
}

SEEDANCE2_PRICE_PER_1K_TOKENS: dict[tuple[str, bool, str], float] = {
    ("doubao-seedance-2-0-260128", False, "480p"): 0.0070,
    ("doubao-seedance-2-0-260128", True, "480p"): 0.0043,
    ("doubao-seedance-2-0-260128", False, "720p"): 0.0070,
    ("doubao-seedance-2-0-260128", True, "720p"): 0.0043,
    ("doubao-seedance-2-0-260128", False, "1080p"): 0.0077,
    ("doubao-seedance-2-0-260128", True, "1080p"): 0.0047,
    ("doubao-seedance-2-0-260128", False, "4k"): 0.0040,
    ("doubao-seedance-2-0-260128", True, "4k"): 0.0024,
    ("doubao-seedance-2-0-fast-260128", False, "480p"): 0.0056,
    ("doubao-seedance-2-0-fast-260128", True, "480p"): 0.0033,
    ("doubao-seedance-2-0-fast-260128", False, "720p"): 0.0056,
    ("doubao-seedance-2-0-fast-260128", True, "720p"): 0.0033,
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
