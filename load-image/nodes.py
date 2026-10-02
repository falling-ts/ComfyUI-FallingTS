# load-image/nodes.py
r"""FallingTS 加载图像 (来自输出)。

参考内置 LoadImageOutput(ComfyUI/nodes.py), 保留它的全部功能:
- 下拉从 output 目录取图(前端 remote 路由 + 刷新按钮 + 上传按钮 + 生成后自动刷新开关);
- 输出 IMAGE / MASK, load_image / IS_CHANGED / VALIDATE_INPUTS 与内置同口径。

本模块另加四件事:

1. **「名称」输入框**(排在 image 下拉之前 —— 内置刷新按钮由 remote 组件在 combo 之后
   addWidget('button', 'refresh', ...) 追加, 故输入框天然落在刷新按钮上方):
   遮罩编辑器保存时, 前端把它带给 POST /fallingts_mask/rename, 成品按
   0010_灰度遮罩/0000N_名称.png 落盘(N = 该目录里已有 5 位编号的最大值 + 1)。

2. **下拉列表由本模块的路由 GET /fallingts_load_image/files 提供**:
   内置 /internal/files/output 只列 output 根目录下的文件(os.scandir 一层),
   而本工作区的产物全落在数字目录里(0010_灰度遮罩/、0011_万物建模/ …),
   于是内置节点的下拉在本机基本是空的。本路由按「媒体资产」侧栏同一口径扫描:
   output 根目录的文件 + **数字目录(正则 ^\d+_)内部整棵子树的图片**,
   值形如 0010_灰度遮罩/00001_手部.png, 经
   folder_paths.get_annotated_filepath(..., default_dir=output) 定位到子目录内的文件。

⚠️ 值**不带 " [output]" 标注**(与内置 /internal/files/output 的线格式不同), 两条理由:
1. 前端给每个候选算预览图时一律拼 type=input 且不剥离标注(useWidgetSelectItems 的
   inputItems), 带标注的 filename 会让 /api/view 404 ⇒ 弹窗里每张卡片都是破图
   (内置 LoadImageOutput 的下拉就长这样);
2. 本节点的值默认属于 output, load_image 用 default_dir=output 解析, 不必靠后缀;
   写 " [output]"/" [input]" 标注的值依然按标注走(annotated_filepath 优先看后缀)。
本工作区 input/ 与 output/ 是同一物理目录的软链, 故 type=input 的预览图也读得到。

3. **下拉候选同时在 INPUT_TYPES 里给一份「现扫」的 options**(每次 /object_info 都重新扫
   目录, 故页面加载/新建节点时拿到的就已经是含子目录的完整列表) —— 只靠 remote 的话,
   节点刚建好时 widget.options.values 还是空的, 用户"第一次点开下拉"会看到空列表,
   必须点一下刷新按钮才出来。V3 的 define_schema 同样是每次现算(实测), 两个节点一致。
   remote 路由仍然是权威数据源: 点刷新按钮 / 跑完自动刷新都重新拉它。

4. **「序列号」+「刷新序列号」**: 与「加载视频」同一套 —— 输出目录里已有编号的最大值 + 1
   (目录不存在或没有 "数字_" 命名的文件时为 0, 显示成 5 位 00000), 可手改, 按钮随时重算。
   编号口径与目录解析都取自 output_subdir(有 md 数据表用表文件名, 没有才用工作流名)。
   ⚠️ 序列号排在 image **之后**: V1 节点按 widgets_values 数组的**下标**恢复旧工作流,
   插在中间会让老工作流的 image 值整体错位。

5. **remote 不设 control_after_refresh —— 刷新只更新候选, 不改写已选值**:
   内置 LoadImageOutput 设了 control_after_refresh="first", 前端 remote 组件因此在每次
   刷新(含跑完流程后的 Auto-refresh)后把 widget.value 换成候选首项; 候选按 mtime 倒序 ⇒
   刚保存的产物必然夺走选中权, 用户选的子目录资源被顶掉。本节点只保留 refresh_button,
   刷新与自动刷新都只重新拉候选列表。前端另配 web/js/load_image.js: 上游的 onFirstLoad
   (节点首次加载时无条件把值设成候选首项, 没有开关)由它做短守护恢复成工作流存的值。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re

import folder_paths
import numpy as np
import torch
from aiohttp import web
from PIL import Image, ImageOps, ImageSequence
from server import PromptServer

from output_subdir import next_sequence, safe_dir_name, sequence_dir

import comfy.model_management
import node_helpers
from comfy_api.latest import InputImpl

logger = logging.getLogger(__name__)

# 资源表目录口径: 数字开头 + 下划线(0010_灰度遮罩 / 0011_万物建模 …)
_NUMERIC_DIR_RE = re.compile(r"^\d+_")


# ─── 下拉列表: output 根 + 数字目录内部的图片 ─────────────────────────────────


def _is_image_file(name: str) -> bool:
    """按扩展名判图片(复用核心的 MIME 缓存, 与内置 LoadImage.INPUT_TYPES 同口径)。"""
    return bool(folder_paths.filter_files_content_types([name], ["image"]))


def _collect_output_items(directory: str, prefix: str = "") -> list[tuple[float, str]]:
    """递归收集 (mtime, "sub/name.ext") 项(值不带 " [output]" 标注, 见模块 docstring)。

    - prefix 为空(output 根): 只递归**数字目录** —— output 里还有 clipspace 这类
      非资源目录, 不把它们的内容混进下拉;
    - prefix 非空(已在数字目录内): 整棵子树都收(资源目录内部允许再分层)。
    """
    items: list[tuple[float, str]] = []
    try:
        entries = list(os.scandir(directory))
    except OSError as e:
        logger.warning("扫描 output 目录失败 %s: %s", directory, e)
        return items

    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                if prefix or _NUMERIC_DIR_RE.match(entry.name):
                    items.extend(_collect_output_items(entry.path, prefix + entry.name + "/"))
                continue
            if not entry.is_file() or not _is_image_file(entry.name):
                continue
            items.append((entry.stat().st_mtime, prefix + entry.name))
        except OSError:
            continue
    return items


def _list_relative(directory: str) -> list[str]:
    """按相对路径列出目录里的图片(供 INPUT_TYPES 的初始候选; 每次 /object_info 现扫)。"""
    return sorted(name for _, name in _collect_output_items(directory))


@PromptServer.instance.routes.get("/fallingts_load_image/files")
async def _list_output_files(request: web.Request) -> web.Response:
    """给节点的下拉喂候选值: output 根 + 数字目录内部的图片, 按 mtime 倒序。

    返回形如 ["0011_万物建模/00001_陈落.png", "封面.png"] 的数组(不带 " [output]" 标注,
    见模块 docstring), 前端 remote 组件直接把它当 widget.options.values 用。
    """
    items = _collect_output_items(folder_paths.get_output_directory())
    items.sort(key=lambda item: -item[0])
    return web.json_response([value for _, value in items])


@PromptServer.instance.routes.get("/fallingts_load_image/next_sequence")
async def _handle_next_sequence(request: web.Request) -> web.Response:
    """返回该工作流产物目录里的下一个可用编号(前端在节点创建/刷新时拉取)。

    query: workflow_name(当前工作流名) 或 dir(直接指定目录名, 优先)。
    返回: {"status":"ok","sequence":int,"directory":"<子目录名>","exists":bool}。
    目录不存在/没有编号文件时 sequence 为 0(前端显示成 00000)。
    """
    query = request.rel_url.query
    sub = safe_dir_name(query.get("dir")) or sequence_dir(query.get("workflow_name"))
    base = folder_paths.get_output_directory()
    directory = os.path.join(base, sub) if sub else base
    return web.json_response(
        {
            "status": "ok",
            "sequence": next_sequence(directory),
            "directory": sub,
            "exists": os.path.isdir(directory),
        }
    )


# ─── 节点 ──────────────────────────────────────────────────────────────────


class FallingTSLoadImageNode:
    """加载图像 (来自输出): 内置 LoadImageOutput 的超集(名称输入框 + 序列号 + 数字目录下拉)。"""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                # 排在最前 ⇒ 渲染在 image 下拉(及其刷新按钮)上方
                "name": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "display_name": "名称",
                    },
                ),
                "image": (
                    "COMBO",
                    {
                        "image_upload": True,
                        "image_folder": "output",
                        # 现扫一份候选: 前端页面加载 / 新建节点时即为完整列表(含子目录),
                        # 不必等 remote 拉取、也不必先点刷新按钮(见模块 docstring 第 3 条)
                        "options": _list_relative(folder_paths.get_output_directory()),
                        "remote": {
                            "route": "/fallingts_load_image/files",
                            "refresh_button": True,
                        },
                    },
                ),
            },
            # ⚠️ 序列号排在 image **之后**, 且放 optional:
            # - 排在 image 之后: V1 节点按 widgets_values 数组的**下标**恢复旧工作流,
            #   插在中间会让老工作流的 image 值整体错位;
            # - optional: 无头 API 提交(手工构造的 API prompt / 老工作流转出来的图)
            #   不带这个输入时也能跑, 不会报 "Required input is missing"。
            # required + optional 的拼接顺序仍是 name → image → sequence。
            "optional": {
                "sequence": (
                    "STRING",
                    {
                        "default": "00000",
                        "multiline": False,
                        "display_name": "序列号",
                    },
                ),
            },
        }

    CATEGORY = "FallingTS"
    DESCRIPTION = (
        "从 output 目录加载图片(含数字目录内部的资源); 「名称」供遮罩编辑器保存时"
        "按 0010_灰度遮罩 的自增编号命名成品; 「序列号」是该工作流产物目录里下一个可用编号。"
    )
    SEARCH_ALIASES = ["load image", "output image", "加载图像", "来自输出"]
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"

    def load_image(self, image, name=None, sequence=None):
        """与内置 LoadImage.load_image 同实现(视频/动图序列 + PIL 回退)。"""
        image_path = folder_paths.get_annotated_filepath(
            image, default_dir=folder_paths.get_output_directory()
        )

        dtype = comfy.model_management.intermediate_dtype()
        device = comfy.model_management.intermediate_device()

        components = InputImpl.VideoFromFile(image_path).get_components()
        if components.images.shape[0] > 0:
            mask = (
                (1.0 - components.alpha[..., -1]).to(device=device, dtype=dtype)
                if components.alpha is not None
                else torch.zeros((components.images.shape[0], 64, 64), dtype=dtype, device=device)
            )
            return (components.images.to(device=device, dtype=dtype), mask)

        # pyav 读不了的动图(如 animated webp)走 PIL
        img = node_helpers.pillow(Image.open, image_path)

        output_images: list[torch.Tensor] = []
        output_masks: list[torch.Tensor] = []
        w, h = None, None

        for frame in ImageSequence.Iterator(img):
            frame = node_helpers.pillow(ImageOps.exif_transpose, frame)
            frame = frame.convert("RGB")

            if len(output_images) == 0:
                w, h = frame.size[0], frame.size[1]
            if frame.size[0] != w or frame.size[1] != h:
                continue

            array = np.array(frame).astype(np.float32) / 255.0
            tensor = torch.from_numpy(array)[None,]
            if "A" in frame.getbands():
                alpha = np.array(frame.getchannel("A")).astype(np.float32) / 255.0
                mask_tensor = 1.0 - torch.from_numpy(alpha)
            else:
                mask_tensor = torch.zeros((64, 64), dtype=torch.float32, device="cpu")
            output_images.append(tensor.to(dtype=dtype))
            output_masks.append(mask_tensor.unsqueeze(0).to(dtype=dtype))

        output_image = torch.cat(output_images, dim=0)
        output_mask = torch.cat(output_masks, dim=0)
        return (
            output_image.to(device=device, dtype=dtype),
            output_mask.to(device=device, dtype=dtype),
        )

    @classmethod
    def IS_CHANGED(cls, image, **kwargs):
        """文件内容变了才算变化(内置口径)。**kwargs 吸收 name 等新增输入。"""
        image_path = folder_paths.get_annotated_filepath(
            image, default_dir=folder_paths.get_output_directory()
        )
        m = hashlib.sha256()
        with open(image_path, "rb") as f:
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(cls, image, **kwargs):
        """文件不存在时给出明确提示(内置口径; 值默认按 output 解析)。"""
        try:
            path = folder_paths.get_annotated_filepath(
                image, default_dir=folder_paths.get_output_directory()
            )
        except ValueError:
            return "Invalid image file: {}".format(image)
        if not os.path.isfile(path):
            return "Invalid image file: {}".format(image)

        return True
