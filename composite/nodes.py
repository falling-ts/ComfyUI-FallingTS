# composite/nodes.py
"""FallingTS 四图合成 (2×2 带标注, Z 字排列):

4 个 IMAGE 输入 (image1..image4) + 4 个 STRING 标注 (label1..label4, 可连线, 默认 前面/右面/后面/左面)。
行为:
- 统一尺寸: 取 4 图最大高/最大宽, 较小的图 Lanczos 放大对齐 (三张生成图通常同尺寸, 原图尺寸不同时对齐到最大);
- 每张子图左上角标注文字: CJK 字体 (随包 fonts/Alibaba-PuHuiTi-Heavy.ttf), 白字黑描边, 字号 = 子图宽 × font_size%;
  标注为空则不画;
- Z 字排列 2×2: 上排 image1(默认 前面)/image2(默认 右面), 下排 image3(默认 后面)/image4(默认 左面)
  (前面→右面→后面→左面 的阅读顺序即 Z 形);
- 输出 1 张 IMAGE (2×2 + 间距, 间距与外边距 = padding 像素, 底色 = background_color)。

典型用法: 场景旋镜 原图 (前面) + 右面/后面/左面 生成图 (LoadImage 载入 output 已存文件) → 单张四向标注图。
"""

from __future__ import annotations

import os

import numpy as np
import torch
from PIL import Image, ImageColor, ImageDraw, ImageFont

# 随包 CJK 字体 (相对本文件): 标注渲染用
_FONT_REL = os.path.join("..", "fonts", "Alibaba-PuHuiTi-Heavy.ttf")


def _load_font(size: int) -> ImageFont.ImageFont:
    """加载随包 CJK 字体; 缺失时退回 PIL 默认字体 (非 CJK 字符会缺字)。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _FONT_REL)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _to_pil(img, width: int, height: int) -> Image.Image:
    """IMAGE 张量 [B,H,W,C] 0..1 → PIL RGB (取首帧, 必要时 Lanczos 缩放到 width×height)。"""
    arr = img[0].float().clamp(0.0, 1.0).cpu().numpy()
    im = Image.fromarray((arr * 255).astype(np.uint8))
    if im.size != (width, height):
        im = im.resize((width, height), Image.Resampling.LANCZOS)
    return im


class FallingTSImageCompositeNode:
    """四图 2×2 Z 字合成为单张带标注图: 4 图 + 4 标注 → 统一尺寸 → 左上角标注 → 2×2 排列输出。"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".image1..image4: 四个子图 (IMAGE);
            - "required".label1..label4: 四个标注文字 (STRING, 可连线, 默认 前面/右面/后面/左面, 空 = 不画);
            - "required".font_size: 字号 (子图宽百分比, 默认 8.0);
            - "required".padding: 图间距与外边距 (像素, 默认 6);
            - "required".background_color: 间距底色 (十六进制, 默认 #000000)。
        """
        return {
            "required": {
                "image1": ("IMAGE", {"tooltip": "左上 (默认标注 前面, 通常接原图)"}),
                "image2": ("IMAGE", {"tooltip": "右上 (默认标注 右面)"}),
                "image3": ("IMAGE", {"tooltip": "左下 (默认标注 后面)"}),
                "image4": ("IMAGE", {"tooltip": "右下 (默认标注 左面)"}),
                "label1": ("STRING", {"default": "前面", "multiline": False, "tooltip": "左上标注 (空 = 不画)"}),
                "label2": ("STRING", {"default": "右面", "multiline": False, "tooltip": "右上标注 (空 = 不画)"}),
                "label3": ("STRING", {"default": "后面", "multiline": False, "tooltip": "左下标注 (空 = 不画)"}),
                "label4": ("STRING", {"default": "左面", "multiline": False, "tooltip": "右下标注 (空 = 不画)"}),
                "font_size": ("FLOAT", {"default": 8.0, "min": 2.0, "max": 30.0, "step": 0.5, "tooltip": "字号 (子图宽百分比, 8.0 = 8%)"}),
                "padding": ("INT", {"default": 6, "min": 0, "max": 60, "step": 1, "tooltip": "图间距与外边距 (像素)"}),
                "background_color": ("STRING", {"default": "#000000", "multiline": False, "tooltip": "间距底色 (十六进制, 如 #000000)"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "composite"
    CATEGORY = "FallingTS/工具"

    def composite(self, image1, image2, image3, image4, label1, label2, label3, label4,
                  font_size, padding, background_color):
        """统一尺寸 + 左上角标注 → 2×2 Z 字合成为单张图。"""
        images = (image1, image2, image3, image4)
        labels = (label1, label2, label3, label4)
        # 统一尺寸: 取最大高/宽 (生成三图同尺寸, 原图不同时对齐到最大; IMAGE 张量 = [B,H,W,C])
        width = max(img.shape[2] for img in images)
        height = max(img.shape[1] for img in images)
        gap = int(padding)
        margin = max(8, int(width * 0.02))
        tiles = []
        for img, label in zip(images, labels):
            tile = _to_pil(img, width, height)
            text = (label or "").strip()
            if text:
                size = max(14, int(width * font_size / 100.0))
                draw = ImageDraw.Draw(tile)
                draw.text(
                    (margin, margin),
                    text,
                    font=_load_font(size),
                    fill=(255, 255, 255, 255),
                    stroke_width=max(1, size // 10),
                    stroke_fill=(0, 0, 0, 255),
                )
            tiles.append(tile)
        # Z 字排列: 上排 image1(前面)/image2(右面), 下排 image3(后面)/image4(左面)
        canvas = Image.new("RGB", (width * 2 + gap * 3, height * 2 + gap * 3), ImageColor.getrgb(background_color))
        canvas.paste(tiles[0], (gap, gap))
        canvas.paste(tiles[1], (gap * 2 + width, gap))
        canvas.paste(tiles[2], (gap, gap * 2 + height))
        canvas.paste(tiles[3], (gap * 2 + width, gap * 2 + height))
        arr = np.asarray(canvas).astype(np.float32) / 255.0
        return (torch.from_numpy(arr[np.newaxis, ...]),)


NODE_CLASS_MAPPINGS = {
    "FallingTSImageComposite": FallingTSImageCompositeNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSImageComposite": "FallingTS 四图合成 (2×2 带标注)",
}
