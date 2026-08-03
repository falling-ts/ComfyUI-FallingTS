# Seedance 2.0 视频生成节点 (V3 API 模式)

from __future__ import annotations

import logging
from typing import Any

from comfy_api.latest import IO
from comfy_api_nodes.util.upload_helpers import upload_audio_to_comfyapi

from .api import (
    create_seedance_task,
    poll_seedance_task,
    download_video,
    upload_images_as_base64,
    upload_videos_to_urls,
)
from .models import SEEDANCE_MODELS, MODEL_RESOLUTIONS

logger = logging.getLogger(__name__)


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


# ─── Reference to Video (多模态参考) ──────────────────────

class Seedance2ReferenceNode(IO.ComfyNode):

    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="Seedance2Reference",
            display_name="Seedance 2.0 多模态参考生视频",
            category="自定义节点/字节跳动",
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
                # 多模态参考输入 (Autogrow: 可动态增减槽位)
                IO.Autogrow.Input(
                    "reference_images",
                    template=IO.Autogrow.TemplateNames(
                        IO.Image.Input("reference_image"),
                        names=["image_1", "image_2", "image_3", "image_4", "image_5",
                               "image_6", "image_7", "image_8", "image_9"],
                        min=0,
                    ),
                ),
                IO.Autogrow.Input(
                    "reference_asset_ids",
                    template=IO.Autogrow.TemplateNames(
                        IO.String.Input("asset_id"),
                        names=["asset_1", "asset_2", "asset_3", "asset_4", "asset_5",
                               "asset_6", "asset_7", "asset_8", "asset_9"],
                        min=0,
                    ),
                ),
                IO.Autogrow.Input(
                    "reference_videos",
                    template=IO.Autogrow.TemplateNames(
                        IO.Video.Input("reference_video"),
                        names=["video_1", "video_2", "video_3"],
                        min=0,
                    ),
                ),
                IO.Autogrow.Input(
                    "reference_audios",
                    template=IO.Autogrow.TemplateNames(
                        IO.Audio.Input("reference_audio"),
                        names=["audio_1", "audio_2", "audio_3"],
                        min=0,
                    ),
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
            ],
            outputs=[
                IO.Video.Output(),
            ],
            price_badge=_price_badge(),
        )

    @classmethod
    async def execute(
        cls,
        model: dict,
        seed: int,
        watermark: bool,
        reference_images: dict[str, Any] | None = None,
        reference_videos: dict[str, Any] | None = None,
        reference_audios: dict[str, Any] | None = None,
        reference_asset_ids: dict[str, Any] | None = None,
    ) -> IO.NodeOutput:
        model_name = model["model"]
        model_id = SEEDANCE_MODELS.get(model_name)
        if not model_id:
            raise ValueError(f"未知模型: {model_name}")

        # Autogrow 输入是 dict
        images = reference_images or {}
        videos = reference_videos or {}
        audios = reference_audios or {}
        asset_ids = reference_asset_ids or {}

        total_images = len(images) + len(asset_ids)
        has_images = total_images > 0
        has_videos = len(videos) > 0
        has_audios = len(audios) > 0
        if total_images > 9:
            raise ValueError(f"参考图片+资产库ID总数不能超过 9 (当前 {total_images})")
        if not has_images and not has_videos:
            raise ValueError("至少需要 1 张参考图片、资产库ID或 1 个参考视频。")

        prompt = model.get("prompt", "")

        # 上传/组装参考文件
        image_urls = upload_images_as_base64(images) if images else {}
        for slot, aid in (asset_ids or {}).items():
            aid = aid.strip()
            if aid and not aid.startswith("asset://"):
                aid = f"asset://{aid}"
            image_urls[slot] = aid
        image_roles = {k: "reference_image" for k in image_urls}

        video_urls = await upload_videos_to_urls(cls, videos) if videos else {}
        audio_urls: dict[str, str] = {}
        if has_audios:
            for slot in sorted(audios, key=lambda x: int(x.split("_")[-1]) if x.split("_")[-1].isdigit() else 0):
                audio_urls[slot] = await upload_audio_to_comfyapi(
                    cls, audios[slot], container_format="mp3", mime_type="audio/mpeg",
                )

        # 创建任务
        task_id = await create_seedance_task(
            cls, "", model_id,
            prompt=prompt or None,
            resolution=model["resolution"],
            ratio=model["ratio"],
            duration=model["duration"],
            generate_audio=model["generate_audio"],
            seed=seed,
            watermark=watermark,
            image_base64s=image_urls if image_urls else None,
            image_roles=image_roles if image_roles else None,
            video_urls=video_urls if video_urls else None,
            audio_urls=audio_urls if audio_urls else None,
        )

        # 轮询结果
        video_url = await poll_seedance_task(
            cls, "", task_id,
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
            display_name="Seedance 2.0 首尾帧生视频",
            category="自定义节点/字节跳动",
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
            ],
            outputs=[
                IO.Video.Output(),
            ],
            price_badge=_price_badge(),
        )

    @classmethod
    async def execute(
        cls,
        model: dict,
        first_frame: IO.Image.Type,
        seed: int,
        watermark: bool,
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

        image_urls = upload_images_as_base64(images_to_upload)

        # 创建任务
        task_id = await create_seedance_task(
            cls, "", model_id,
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
            cls, "", task_id,
            model_id=model_id,
            has_video_input=False,
            resolution=model["resolution"],
        )

        video = await download_video(video_url, cls)
        return IO.NodeOutput(video)
