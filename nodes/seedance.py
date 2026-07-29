# Seedance 2.0 视频生成节点 (V3 API 模式)

from __future__ import annotations

import logging

from comfy_api.latest import IO
from comfy_api_nodes.util.validation_utils import validate_string

from ..api.client import (
    create_seedance_task,
    poll_seedance_task,
    download_video,
    upload_images_to_urls,
    upload_videos_to_urls,
)
from ..api.models import (
    SEEDANCE_MODELS,
    MODEL_RESOLUTIONS,
    seedance2_price,
)

logger = logging.getLogger(__name__)


def _text_inputs(resolutions: list[str], default_ratio: str = "16:9"):
    """纯文本输入模式 (Text/Image-to-Video 共享)。"""
    return [
        IO.String.Input(
            "prompt",
            multiline=True,
            default="",
            tooltip="视频生成提示词。支持中文(≤500字)、英文(≤1000词)等多语言。",
        ),
        IO.Combo.Input(
            "resolution",
            options=resolutions,
            tooltip="输出视频分辨率。",
        ),
        IO.Combo.Input(
            "ratio",
            options=["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
            default=default_ratio,
            tooltip="输出视频宽高比。",
        ),
        IO.Int.Input(
            "duration",
            default=7,
            min=4,
            max=15,
            step=1,
            tooltip="视频时长(秒), 4-15 秒。",
            display_mode=IO.NumberDisplay.slider,
        ),
        IO.Boolean.Input(
            "generate_audio",
            default=True,
            tooltip="是否生成背景音频。",
        ),
    ]


def _image_to_video_inputs(resolutions: list[str]):
    """图生视频输入 (首帧/参考图)。"""
    return [
        IO.String.Input(
            "prompt",
            multiline=True,
            default="",
            optional=True,
            tooltip="视频生成提示词(可选)。",
        ),
        IO.Combo.Input(
            "resolution",
            options=resolutions,
            tooltip="输出视频分辨率。",
        ),
        IO.Combo.Input(
            "ratio",
            options=["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
            default="adaptive",
            tooltip="输出视频宽高比。",
        ),
        IO.Int.Input(
            "duration",
            default=7,
            min=4,
            max=15,
            step=1,
            tooltip="视频时长(秒), 4-15 秒。",
            display_mode=IO.NumberDisplay.slider,
        ),
        IO.Boolean.Input(
            "generate_audio",
            default=True,
            tooltip="是否生成背景音频。",
        ),
    ]


def _price_badge(model_key: str = "model"):
    """构建定价显示 badge。"""
    return IO.PriceBadge(
        depends_on=IO.PriceBadgeDepends(
            widgets=[model_key, f"{model_key}.resolution", f"{model_key}.duration"],
            input_groups=[f"{model_key}.reference_videos"],
        ),
        expr="""
        (
          $rate480 := 10044;
          $rate720 := 21600;
          $rate1080 := 48800;
          $rate4k := 195200;
          $m := widgets.model;
          $hasVideo := $lookup(inputGroups, "model.reference_videos") > 0;
          $res := $lookup(widgets, "model.resolution");
          $dur := $lookup(widgets, "model.duration");
          $noVideoPricePer1K := $res = "4k"    ? 0.00572 :
                                $res = "1080p" ? 0.011011 :
                                $contains($m, "mini") ? 0.005005 :
                                $contains($m, "fast") ? 0.008008 : 0.01001;
          $videoPricePer1K := $res = "4k"    ? 0.003432 :
                              $res = "1080p" ? 0.006721 :
                              $contains($m, "mini") ? 0.003003 :
                              $contains($m, "fast") ? 0.004719 : 0.006149;
          $rate := $res = "4k"    ? $rate4k :
                   $res = "1080p" ? $rate1080 :
                   $res = "720p"  ? $rate720 :
                                    $rate480;
          $pricePer1K := $hasVideo ? $videoPricePer1K : $noVideoPricePer1K;
          $cost := $dur * $rate * $pricePer1K / 1000;
          {"type": "usd", "usd": $cost, "format": {"approximate": true}}
        )
        """,
    )


# ─── Text to Video ────────────────────────────────────────

class Seedance2TextToVideoNode(IO.ComfyNode):

    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="Seedance2TextToVideo",
            display_name="Seedance 2.0 Text to Video",
            category="video/ByteDance",
            description="使用 Seedance 2.0 模型通过文本提示词生成视频。",
            inputs=[
                IO.DynamicCombo.Input(
                    "model",
                    options=[
                        IO.DynamicCombo.Option(
                            "Seedance 2.0",
                            _text_inputs(MODEL_RESOLUTIONS["Seedance 2.0"]),
                        ),
                        IO.DynamicCombo.Option(
                            "Seedance 2.0 Fast",
                            _text_inputs(MODEL_RESOLUTIONS["Seedance 2.0 Fast"]),
                        ),
                        IO.DynamicCombo.Option(
                            "Seedance 2.0 Mini",
                            _text_inputs(MODEL_RESOLUTIONS["Seedance 2.0 Mini"]),
                        ),
                    ],
                    tooltip="选择模型: Seedance 2.0(最高质量) / Fast(速度优化) / Mini(最快最省)",
                ),
                IO.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=2147483647,
                    step=1,
                    display_mode=IO.NumberDisplay.number,
                    control_after_generate=True,
                    tooltip="随机种子(仅控制重跑, 结果非确定性)。",
                ),
                IO.Boolean.Input(
                    "watermark",
                    default=False,
                    tooltip="是否添加水印。",
                    advanced=True,
                ),
                IO.String.Input(
                    "volcengine_api_key",
                    default="",
                    placeholder="可选: 或在 .env 中设置 VOLC_ENGINE_API_KEY",
                    tooltip="Volcengine API Key。可为空, 将自动读取 VOLC_ENGINE_API_KEY 环境变量或 .env 文件配置。",
                    optional=True,
                    advanced=True,
                ),
            ],
            outputs=[
                IO.Video.Output(),
            ],
            hidden=[],
            is_api_node=True,
            price_badge=_price_badge(),
        )

    @classmethod
    async def execute(
        cls,
        model: dict,
        seed: int,
        watermark: bool,
        volcengine_api_key: str = "",
    ) -> IO.NodeOutput:
        # 验证提示词
        prompt = model.get("prompt", "")
        validate_string(prompt, strip_whitespace=True, min_length=1)

        model_name = model["model"]
        model_id = SEEDANCE_MODELS.get(model_name)
        if not model_id:
            raise ValueError(f"未知模型: {model_name}")

        # 创建任务
        task_id = await create_seedance_task(
            cls, volcengine_api_key, model_id,
            prompt=prompt,
            resolution=model["resolution"],
            ratio=model["ratio"],
            duration=model["duration"],
            generate_audio=model["generate_audio"],
            seed=seed,
            watermark=watermark,
        )

        # 轮询结果
        video_url = await poll_seedance_task(
            cls, volcengine_api_key, task_id,
            model_id=model_id,
            has_video_input=False,
            resolution=model["resolution"],
        )

        # 下载视频
        video = await download_video(video_url, cls)
        return IO.NodeOutput(video)


# ─── Image to Video (首帧) ────────────────────────────────

class Seedance2ImageToVideoNode(IO.ComfyNode):

    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="Seedance2ImageToVideo",
            display_name="Seedance 2.0 Image to Video",
            category="video/ByteDance",
            description="使用 Seedance 2.0 通过首帧图片生成视频。",
            inputs=[
                IO.DynamicCombo.Input(
                    "model",
                    options=[
                        IO.DynamicCombo.Option(
                            "Seedance 2.0",
                            _image_to_video_inputs(MODEL_RESOLUTIONS["Seedance 2.0"]),
                        ),
                        IO.DynamicCombo.Option(
                            "Seedance 2.0 Fast",
                            _image_to_video_inputs(MODEL_RESOLUTIONS["Seedance 2.0 Fast"]),
                        ),
                        IO.DynamicCombo.Option(
                            "Seedance 2.0 Mini",
                            _image_to_video_inputs(MODEL_RESOLUTIONS["Seedance 2.0 Mini"]),
                        ),
                    ],
                    tooltip="选择模型: Seedance 2.0(最高质量) / Fast(速度优化) / Mini(最快最省)",
                ),
                IO.Image.Input(
                    "first_frame",
                    tooltip="首帧图片。宽高比 0.4-2.5, 宽高 300-6000px。",
                ),
                IO.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=2147483647,
                    step=1,
                    display_mode=IO.NumberDisplay.number,
                    control_after_generate=True,
                    tooltip="随机种子(仅控制重跑, 结果非确定性)。",
                ),
                IO.Boolean.Input(
                    "watermark",
                    default=False,
                    tooltip="是否添加水印。",
                    advanced=True,
                ),
                IO.String.Input(
                    "volcengine_api_key",
                    default="",
                    placeholder="请输入 Volcengine API Key",
                    tooltip="Volcengine API Key (必填)。",
                    advanced=True,
                ),
            ],
            outputs=[
                IO.Video.Output(),
            ],
            hidden=[],
            is_api_node=True,
            price_badge=_price_badge(),
        )

    @classmethod
    async def execute(
        cls,
        model: dict,
        first_frame: IO.Image.Type,
        seed: int,
        watermark: bool,
        volcengine_api_key: str = "",
    ) -> IO.NodeOutput:
        model_name = model["model"]
        model_id = SEEDANCE_MODELS.get(model_name)
        if not model_id:
            raise ValueError(f"未知模型: {model_name}")

        prompt = model.get("prompt", "")

        # 上传首帧图片为 base64
        image_urls = await upload_images_to_urls(cls, {"first_frame": first_frame})
        image_roles = {"first_frame": "first_frame"}

        # 创建任务
        task_id = await create_seedance_task(
            cls, volcengine_api_key, model_id,
            prompt=prompt or None,
            resolution=model["resolution"],
            ratio=model["ratio"],
            duration=model["duration"],
            generate_audio=model["generate_audio"],
            seed=seed,
            watermark=watermark,
            image_base64s=image_urls,
            image_roles=image_roles,
        )

        # 轮询结果
        video_url = await poll_seedance_task(
            cls, volcengine_api_key, task_id,
            model_id=model_id,
            has_video_input=False,
            resolution=model["resolution"],
        )

        video = await download_video(video_url, cls)
        return IO.NodeOutput(video)


# ─── Reference to Video (多模态参考) ──────────────────────

class Seedance2ReferenceNode(IO.ComfyNode):

    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="Seedance2Reference",
            display_name="Seedance 2.0 Reference to Video",
            category="video/ByteDance",
            description="使用 Seedance 2.0 通过多模态参考(图片/视频/音频)生成、编辑或延展视频。",
            inputs=[
                IO.DynamicCombo.Input(
                    "model",
                    options=[
                        IO.DynamicCombo.Option(
                            "Seedance 2.0",
                            _image_to_video_inputs(MODEL_RESOLUTIONS["Seedance 2.0"]),
                        ),
                        IO.DynamicCombo.Option(
                            "Seedance 2.0 Fast",
                            _image_to_video_inputs(MODEL_RESOLUTIONS["Seedance 2.0 Fast"]),
                        ),
                        IO.DynamicCombo.Option(
                            "Seedance 2.0 Mini",
                            _image_to_video_inputs(MODEL_RESOLUTIONS["Seedance 2.0 Mini"]),
                        ),
                    ],
                    tooltip="选择模型: Seedance 2.0(最高质量) / Fast(速度优化) / Mini(最快最省)",
                ),
                # 多模态参考输入
                IO.Image.Input(
                    "reference_images",
                    tooltip="参考图片(1-9张)。宽高比 0.4-2.5, 宽高 300-6000px。",
                    optional=True,
                ),
                IO.Video.Input(
                    "reference_videos",
                    tooltip="参考视频(0-3个)。时长 2-15s, 总时长≤15s。",
                    optional=True,
                ),
                IO.Audio.Input(
                    "reference_audios",
                    tooltip="参考音频(0-3段)。时长 2-15s, 总时长≤15s。",
                    optional=True,
                ),
                IO.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=2147483647,
                    step=1,
                    display_mode=IO.NumberDisplay.number,
                    control_after_generate=True,
                    tooltip="随机种子(仅控制重跑, 结果非确定性)。",
                ),
                IO.Boolean.Input(
                    "watermark",
                    default=False,
                    tooltip="是否添加水印。",
                    advanced=True,
                ),
                IO.String.Input(
                    "volcengine_api_key",
                    default="",
                    placeholder="请输入 Volcengine API Key",
                    tooltip="Volcengine API Key (必填)。",
                    advanced=True,
                ),
            ],
            outputs=[
                IO.Video.Output(),
            ],
            hidden=[],
            is_api_node=True,
            price_badge=_price_badge(),
        )

    @classmethod
    async def execute(
        cls,
        model: dict,
        seed: int,
        watermark: bool,
        volcengine_api_key: str = "",
        reference_images: IO.Image.Type | None = None,
        reference_videos: IO.Video.Type | None = None,
        reference_audios: IO.Audio.Type | None = None,
    ) -> IO.NodeOutput:
        model_name = model["model"]
        model_id = SEEDANCE_MODELS.get(model_name)
        if not model_id:
            raise ValueError(f"未知模型: {model_name}")

        # 至少需要一个参考图片或视频
        has_images = reference_images is not None
        has_videos = reference_videos is not None
        if not has_images and not has_videos:
            raise ValueError("至少需要 1 张参考图片或 1 个参考视频。")

        prompt = model.get("prompt", "")

        # 上传媒体文件
        image_urls: dict[str, str] = {}
        if has_images:
            image_urls = await upload_images_to_urls(cls, {"ref_img": reference_images})

        video_urls: dict[str, str] = {}
        if has_videos:
            video_urls = await upload_videos_to_urls(cls, {"ref_video": reference_videos})

        # 创建任务
        task_id = await create_seedance_task(
            cls, volcengine_api_key, model_id,
            prompt=prompt or None,
            resolution=model["resolution"],
            ratio=model["ratio"],
            duration=model["duration"],
            generate_audio=model["generate_audio"],
            seed=seed,
            watermark=watermark,
            image_base64s=image_urls if image_urls else None,
            image_roles={"ref_img": "reference_image"} if image_urls else None,
            video_urls=video_urls if video_urls else None,
        )

        # 轮询结果
        video_url = await poll_seedance_task(
            cls, volcengine_api_key, task_id,
            model_id=model_id,
            has_video_input=has_videos,
            resolution=model["resolution"],
        )

        video = await download_video(video_url, cls)
        return IO.NodeOutput(video)


# ─── First-Last-Frame to Video ────────────────────────────

class Seedance2FirstLastFrameNode(IO.ComfyNode):

    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="Seedance2FirstLastFrame",
            display_name="Seedance 2.0 First-Last-Frame to Video",
            category="video/ByteDance",
            description="使用 Seedance 2.0 通过首帧和尾帧图片生成视频。",
            inputs=[
                IO.DynamicCombo.Input(
                    "model",
                    options=[
                        IO.DynamicCombo.Option(
                            "Seedance 2.0",
                            _image_to_video_inputs(MODEL_RESOLUTIONS["Seedance 2.0"]),
                        ),
                        IO.DynamicCombo.Option(
                            "Seedance 2.0 Fast",
                            _image_to_video_inputs(MODEL_RESOLUTIONS["Seedance 2.0 Fast"]),
                        ),
                        IO.DynamicCombo.Option(
                            "Seedance 2.0 Mini",
                            _image_to_video_inputs(MODEL_RESOLUTIONS["Seedance 2.0 Mini"]),
                        ),
                    ],
                    tooltip="选择模型: Seedance 2.0(最高质量) / Fast(速度优化) / Mini(最快最省)",
                ),
                IO.Image.Input(
                    "first_frame",
                    tooltip="首帧图片。",
                ),
                IO.Image.Input(
                    "last_frame",
                    tooltip="尾帧图片(可选)。不提供则为首帧生成。",
                    optional=True,
                ),
                IO.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=2147483647,
                    step=1,
                    display_mode=IO.NumberDisplay.number,
                    control_after_generate=True,
                    tooltip="随机种子(仅控制重跑, 结果非确定性)。",
                ),
                IO.Boolean.Input(
                    "watermark",
                    default=False,
                    tooltip="是否添加水印。",
                    advanced=True,
                ),
                IO.String.Input(
                    "volcengine_api_key",
                    default="",
                    placeholder="请输入 Volcengine API Key",
                    tooltip="Volcengine API Key (必填)。",
                    advanced=True,
                ),
            ],
            outputs=[
                IO.Video.Output(),
            ],
            hidden=[],
            is_api_node=True,
            price_badge=_price_badge(),
        )

    @classmethod
    async def execute(
        cls,
        model: dict,
        first_frame: IO.Image.Type,
        seed: int,
        watermark: bool,
        volcengine_api_key: str = "",
        last_frame: IO.Image.Type | None = None,
    ) -> IO.NodeOutput:
        model_name = model["model"]
        model_id = SEEDANCE_MODELS.get(model_name)
        if not model_id:
            raise ValueError(f"未知模型: {model_name}")

        prompt = model.get("prompt", "")

        # 上传图片
        images_to_upload: dict[str, IO.Image.Type] = {"first_frame": first_frame}
        image_roles: dict[str, str] = {"first_frame": "first_frame"}
        if last_frame is not None:
            images_to_upload["last_frame"] = last_frame
            image_roles["last_frame"] = "last_frame"

        image_urls = await upload_images_to_urls(cls, images_to_upload)

        # 创建任务
        task_id = await create_seedance_task(
            cls, volcengine_api_key, model_id,
            prompt=prompt or None,
            resolution=model["resolution"],
            ratio=model["ratio"],
            duration=model["duration"],
            generate_audio=model["generate_audio"],
            seed=seed,
            watermark=watermark,
            image_base64s=image_urls,
            image_roles=image_roles,
        )

        # 轮询结果
        video_url = await poll_seedance_task(
            cls, volcengine_api_key, task_id,
            model_id=model_id,
            has_video_input=False,
            resolution=model["resolution"],
        )

        video = await download_video(video_url, cls)
        return IO.NodeOutput(video)
