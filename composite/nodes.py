# FallingTS 多图合成节点。
#
# 参考本插件带 total 的节点 (switch/route/fanout/selector):
# 后端声明 MAX_TOTAL 组 (image_i / label_i), 前端按 total 动态增删,
# 未启用的端口不进 prompt。
#
# 行为:
# - total = 图片张数 (最少 1, 最多 MAX_TOTAL=8);
# - 输入 total 张图 image1..image_total (optional) + total 个标注 label1..label_total;
# - 网格列数 = ceil(sqrt(total)): total=4 时 2x2 (与原四图合成一致),
#   total=6 时 3 列 x 2 行; total=8 时 3 列 x 3 行 (最后一格留空);
# - 统一尺寸 (取非空图最大高宽), 每张子图左上角 CJK 白字黑描边标注, 拼成单图输出。

from __future__ import annotations

import math
import os

import numpy as np
import torch
from PIL import Image, ImageColor, ImageDraw, ImageFont

_FONT_REL = os.path.join("..", "fonts", "Alibaba-PuHuiTi-Heavy.ttf")

# 最多图片张数 (= 前端动态端口上限, 与其它 total 节点一致)
MAX_TOTAL = 64

# total 非法时的默认张数
DEFAULT_TOTAL = 4

# 默认标注 (按图序): 前 4 图为方位, 后 4 图为补充
_DEFAULT_LABELS = ("前面", "右面", "后面", "左面", "上面", "下面", "近处", "远处")

# 最近一次合成结果缓存: 键 = 节点唯一 ID (字符串), 值 = 合成输出张量
_last_output: dict[str, torch.Tensor] = {}


def _grid_dims(total: int) -> tuple[int, int]:
    """网格维度: cols = ceil(sqrt(total)), rows = ceil(total / cols)。

    参数:
        total (int): 已钳位的张数 (>= 1)。

    返回:
        tuple[int, int]: (cols, rows)。
    """
    n = max(1, int(total))
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


def _load_font(size: int) -> ImageFont.ImageFont:
    """CJK 字体 (随包); 缺失时回退 PIL 默认字体 (不崩溃)。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _FONT_REL)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _bg_rgb(color) -> tuple[int, int, int]:
    """底色转 RGB; None/非法色值回退黑色 (不崩溃)。"""
    try:
        return ImageColor.getrgb("#000000" if color is None else str(color))
    except (ValueError, TypeError):
        return (0, 0, 0)


def _first_frame(img) -> "torch.Tensor | None":
    """取输入的第一帧, 归一化为 HxWxC 0..1 张量; 无值输入一律 None。

    参数:
        img: IMAGE 输入 (任意形态: 单帧/批次/list/tuple/非张量)。

    返回:
        torch.Tensor | None: HxWxC 0..1; None = 无值 (None/空 tuple/list/零批/非张量)。
    """
    if img is None or (isinstance(img, (tuple, list)) and len(img) == 0):
        return None
    if not isinstance(img, torch.Tensor) or img.dim() < 2:
        return None
    if img.dim() == 4 and img.shape[0] == 0:
        return None
    return img[0] if img.dim() == 4 else img


def _to_pil(img_hwc: torch.Tensor, width: int, height: int) -> Image.Image:
    """单帧 HxWxC 0..1 转 PIL 图, 缩放到 (width, height)。"""
    arr = img_hwc.float().clamp(0.0, 1.0).cpu().numpy()
    im = Image.fromarray((arr * 255).astype(np.uint8))
    if im.size != (width, height):
        im = im.resize((width, height), Image.Resampling.LANCZOS)
    return im


class FallingTSImageCompositeNode:
    """N 图网格合成 单张图 (total 决定张数, 默认标注见 _DEFAULT_LABELS)。"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".total: 图片张数 (1~MAX_TOTAL, 前端据此动态增删端口);
            - "required".font_size/padding/background_color;
            - "optional".image1..imageMAX: 各图 (未连接 = 该格底色空格占位);
            - "optional".label1..labelMAX: 各图标注 (可与 image_i 交错排列; 未连接 = 默认标注 _DEFAULT_LABELS, 空串 = 不画);
            - "hidden"."id": 节点唯一 ID (合成结果缓存键)。
        """
        required: dict = {
            "total": (
                "INT",
                {
                    "default": DEFAULT_TOTAL,
                    "min": 1,
                    
                    "step": 1,
                    "tooltip": f"图片张数 (最少 1, 不设上限; 超过 {MAX_TOTAL} 张按 {MAX_TOTAL} 合成), 前端按此动态增删 image_i/label_i 端口",
                },
            ),
        }
        required["font_size"] = (
            "FLOAT",
            {"default": 8.0, "min": 2.0, "max": 30.0, "step": 0.5, "tooltip": "字号 (子图宽百分比, 8.0 = 8%)"},
        )
        required["padding"] = (
            "INT",
            {"default": 6, "min": 0, "max": 60, "step": 1, "tooltip": "格子间距 (像素)"},
        )
        required["background_color"] = (
            "STRING",
            {"default": "#000000", "multiline": False, "tooltip": "间距底色 (十六进制, 如 #000000)"},
        )
        optional = {}
        for i in range(1, MAX_TOTAL + 1):
            optional[f"image{i}"] = ("IMAGE", {"tooltip": f"图 {i} (未连接 = 该格底色空格占位)"})
            optional[f"label{i}"] = (
                "STRING",
                {"tooltip": f"标注 {i} (可连线; 未连接 = 默认标注, 空串 = 不画)"},
            )
        return {"required": required, "optional": optional, "hidden": {"id": "UNIQUE_ID"}}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "composite"
    CATEGORY = "FallingTS/工具"

    @staticmethod
    def _clamp_total(total) -> int:
        """张数钳位到 [1, MAX_TOTAL]; None/非法值回退默认 4。"""
        try:
            t = int(total)
        except (TypeError, ValueError):
            return DEFAULT_TOTAL
        return min(MAX_TOTAL, max(1, t))

    def composite(self, total=DEFAULT_TOTAL, font_size=8.0, padding=6, background_color="#000000", id=None, **kwargs):
        """统一尺寸 + 左上角标注, N 图网格合成为单张图。

        None 容忍 (输入一律安全降级, 不崩溃):
        - 某图 None/空 tuple/非张量 -> 该格渲染为底色空格 (不画标注), 布局不变;
        - 全部图 None/空 -> 本节点曾合成过则输出最近一次结果 (sticky, 让下游不丢数据),
          从未合成过则透传 (None,);
        - total None -> DEFAULT_TOTAL; 各 label None -> 默认标注 (图 1~4 为 前面/右面/
          后面/左面, 图 5~8 为 上面/下面/近处/远处), 空串 = 不画;
        - font_size None -> 8.0; padding None -> 6; background_color None -> #000000。

        参数 id: 节点唯一 ID (隐藏参数 UNIQUE_ID), 用作本节点合成结果缓存键。
        """
        n = self._clamp_total(total)
        # 逐格归一化 (无值输入 -> None, 该格占位)
        frames = [_first_frame(kwargs.get(f"image{i}")) for i in range(1, n + 1)]
        labels = []
        for i in range(1, n + 1):
            raw = kwargs.get(f"label{i}")
            if raw is None:
                labels.append(_DEFAULT_LABELS[i - 1] if i <= len(_DEFAULT_LABELS) else "")
            else:
                labels.append(raw)
        present = [f for f in frames if f is not None]
        if not present:
            # 全部无值 (未连接/上游无值/扇出未选中分支): 曾合成过 -> 回放最近一次结果;
            # 从未合成过 -> 透传 None
            if id is not None and str(id) in _last_output:
                return (_last_output[str(id)],)
            return (None,)
        # 统一尺寸: 取非空图最大高/宽 (单帧 = [H,W,C])
        height = max(f.shape[0] for f in present)
        width = max(f.shape[1] for f in present)
        try:
            gap = int(padding)
        except (TypeError, ValueError):
            gap = 6
        try:
            font_ratio = float(font_size)
        except (TypeError, ValueError):
            font_ratio = 8.0
        bg = _bg_rgb(background_color)
        margin = max(8, int(width * 0.02))
        # 逐格贴图: 有图画图+标注, 无图底色占位 (布局不变)
        tiles = []
        for frame, label in zip(frames, labels):
            if frame is None:
                tiles.append(Image.new("RGB", (width, height), bg))
                continue
            tile = _to_pil(frame, width, height)
            text = (label or "").strip()
            if text:
                size = max(14, int(width * font_ratio / 100.0))
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
        # 网格排列: cols = ceil(sqrt(total)), 行优先填充
        cols, rows = _grid_dims(n)
        canvas = Image.new("RGB", (width * cols + gap * (cols + 1), height * rows + gap * (rows + 1)), bg)
        for idx, tile in enumerate(tiles):
            row, col = divmod(idx, cols)
            canvas.paste(tile, (gap * (col + 1) + col * width, gap * (row + 1) + row * height))
        arr = np.asarray(canvas).astype(np.float32) / 255.0
        out = torch.from_numpy(arr[np.newaxis, ...])
        if id is not None:
            _last_output[str(id)] = out
        return (out,)


NODE_CLASS_MAPPINGS = {
    "FallingTSImageComposite": FallingTSImageCompositeNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSImageComposite": "FallingTS 多图合成 (total 网格带标注)",
}
