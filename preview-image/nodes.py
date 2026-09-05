# preview-image/nodes.py
"""PreviewImageSave 节点: 始终预览(temp), 点「保存」才写 output(同名覆盖, 无序号)。

实现参考 ComfyUI 内置:
- 预览部分照 PreviewImage(nodes.py:1713): 写 temp 目录 + 随机前缀 + 低压缩 PNG, 前端 /view?type=temp 显示;
- 保存部分照 SaveImageAdvanced(comfy_extras/nodes_images.py:1155): _encode_image 按 格式/位深/色彩空间
  编码 + 注入 prompt 元数据;
- 差异: 保存用 {filename_prefix}{filename_suffix}.{format} 直接写 output, 同名覆盖, 不带 _序号 后缀
  (不走 get_save_image_path 的 counter); filename_suffix 默认空串, 可手动输入或上游连线。
- 关键: 点「保存」【不重跑工作流】—— execute 时把最近一次预览的图片数据缓存到后端,
  点按钮时前端把 文件名/格式/位深/色彩空间 POST 到 /preview-image/save/{id}, 后端直接用缓存写 output。
"""

from __future__ import annotations

import os
import random
import string

from PIL import Image
import numpy as np
import torch

from aiohttp import web
from server import PromptServer
import folder_paths
from comfy.cli_args import args
from comfy_extras.nodes_images import _encode_image, inject_png_metadata, inject_exr_metadata


# 最近一次预览的图片数据缓存: node_id -> {"images": [张量...], "prompt": ..., "extra_pnginfo": ...}
# 点「保存」时前端把控件配置 POST 过来, 后端直接用这里的缓存写 output(无需重跑工作流)
_last_output: dict[str, dict] = {}

# 最近一次预览的 UI 记录缓存: node_id -> ui["images"] 列表(指向 temp 目录文件)
# 输入为 None (如扇出未选中分支) 时回放此列表, 保持原有预览不被清空
_last_ui: dict[str, list] = {}


class PreviewImageSaveNode:
    """始终预览 + 点「保存」才写 output(同名覆盖, 无序号)。"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".images: 要预览/保存的图片;
            - "required".filename_prefix: 保存文件名(不含扩展名, 同名覆盖);
            - "required".filename_suffix: 文件名后缀(紧跟 filename_prefix; 不含扩展名, 默认空, 拼接在 filename_prefix 之后);
            - "required".format: png/exr;
            - "required".bit_depth: 位深(png→8/16bit, exr→32bit float);
            - "required".input_color_space: 输入色彩空间(png→sRGB, exr→sRGB/HDR/linear);
            - "hidden".prompt/extra_pnginfo/id: 元数据与节点 id。
        """
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "要预览/保存的图片 (None = 无值, 如扇出未选中分支, 跳过预览, 透传该节点最近一次预览的图供下游合成)。"}),
                "filename_prefix": (
                    "STRING",
                    {
                        "default": "preview",
                        "multiline": False,
                        "tooltip": "保存到 output 的文件名(不含扩展名); 同名文件直接覆盖, 无序号",
                    },
                ),
                # 紧随 filename_prefix(控件紧挨前缀显示); 旧工作流 widgets_values 按位置对齐,
                # 插入槽位由前端 onConfigure 按旧形状(5 槽)检测并自动迁移, 见 web/js/preview-image.js
                "filename_suffix": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "文件名后缀(不含扩展名, 默认空); 保存时拼接在 filename_prefix 之后: {filename_prefix}{filename_suffix}.{format}",
                    },
                ),
                "format": (
                    ["png", "exr"],
                    {
                        "default": "png",
                        "tooltip": "保存的文件格式: png(8/16-bit, sRGB) 或 exr(32-bit float)",
                    },
                ),
                "bit_depth": (
                    ["8-bit", "16-bit", "32-bit float"],
                    {
                        "default": "8-bit",
                        "tooltip": "位深: png → 8-bit/16-bit; exr → 32-bit float",
                    },
                ),
                "input_color_space": (
                    ["sRGB", "HDR", "linear"],
                    {
                        "default": "sRGB",
                        "tooltip": "输入色彩空间: png → sRGB; exr → sRGB/HDR/linear",
                    },
                ),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "始终预览图片(写 temp 不写 output); 点「保存」才按 文件名/格式/位深/色彩空间 "
        "写入 output, 同名直接覆盖、无序号。"
    )
    SEARCH_ALIASES = ["preview", "预览", "保存", "save image", "输出图片"]

    def _make_temp_preview(self, image) -> tuple[str, str]:
        """把单张图片编码为 PNG 写 temp 目录(低压缩), 供前端 /view?type=temp 显示。

        参数:
            image (torch.Tensor): HxWxC 张量。

        返回:
            tuple[str, str]: (temp 文件名, 子目录)。
        """
        i = 255.0 * image.cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        prefix = "ComfyUI_temp_" + "".join(random.choice(string.ascii_lowercase) for _ in range(5))
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            prefix, folder_paths.get_temp_directory(), image.shape[1], image.shape[0]
        )
        file = f"{filename}_{counter:05}_.png"
        img.save(os.path.join(full_output_folder, file), compress_level=1)
        return file, subfolder

    def _save_batch_to_output(
        self,
        images,
        filename_prefix: str,
        file_format: str,
        bit_depth: str,
        colorspace: str,
        prompt,
        extra_pnginfo,
    ) -> None:
        """按格式编码并写 output: 文件名 {prefix}.{format}, 同名直接覆盖, 无 _序号 后缀。

        参数:
            images (torch.Tensor): BxHxWxC 批张量;
            filename_prefix (str): 文件名前缀(可含 %batch_num% 按批号区分);
            file_format (str): png/exr;
            bit_depth (str): 位深(8-bit/16-bit/32-bit float);
            colorspace (str): 输入色彩空间(sRGB/HDR/linear);
            prompt (dict|None): 工作流 prompt(注入元数据);
            extra_pnginfo (dict|None): 额外元数据。

        返回:
            None: 直接写文件到 output 目录。
        """
        output_dir = folder_paths.get_output_directory()
        for batch_number, image in enumerate(images):
            encoded = _encode_image(image, file_format, bit_depth, colorspace)
            if not args.disable_metadata:
                if file_format == "png":
                    encoded = inject_png_metadata(encoded, prompt, extra_pnginfo)
                elif file_format == "exr":
                    encoded = inject_exr_metadata(encoded, prompt, extra_pnginfo, colorspace)
            name = filename_prefix.replace("%batch_num%", str(batch_number))
            full_path = os.path.join(output_dir, f"{name}.{file_format}")
            with open(full_path, "wb") as f:
                f.write(encoded)

    @staticmethod
    def _last_images(id) -> "torch.Tensor | None":
        """取该节点最近一次预览的图片, 重组为 BxHxWxC 批张量 (来自 _last_output 缓存); 无缓存返回 None。

        用于 None 透传: 本节点本次没有新图 (如扇出未选中分支) 时, 把该节点上一次预览的图透传给下游
        (如四图合成), 让下游能拿到该面「之前预览过」的图进入合成, 而非黑空格。

        参数:
            id (str | None): 节点唯一 ID, 用作缓存键。

        返回:
            torch.Tensor | None: BxHxWxC 批张量; 无缓存 (从未预览过) 或形状不一致无法堆叠时 None (下游按无值处理)。
        """
        cache = _last_output.get(id)
        imgs = cache.get("images") if cache else None
        if not imgs or not all(isinstance(x, torch.Tensor) for x in imgs):
            return None
        try:
            return torch.stack(imgs)
        except RuntimeError:
            return None

    def execute(
        self,
        images,
        filename_prefix: str = "preview",
        filename_suffix: str = "",
        format: str = "png",
        bit_depth: str = "8-bit",
        input_color_space: str = "sRGB",
        prompt=None,
        extra_pnginfo=None,
        id: str | None = None,
    ):
        """节点执行入口: 生成 temp 预览, 并把最近一次图片数据缓存到后端供「保存」直接写 output。

        逻辑: 逐张生成 temp PNG 预览返回 UI; 把 images/prompt/extra_pnginfo 存进 _last_output[id]
        —— 之后点「保存」按钮, 前端把 文件名/格式/位深/色彩空间 POST 过来, 后端直接用这份缓存写 output,
        【不重跑工作流】。filename_prefix/filename_suffix/format/bit_depth/input_color_space 这些输入
        只作为控件显示(按钮读取它们), 本方法不用于保存。

        参数:
            images (torch.Tensor|None): BxHxWxC 图片批; None (如扇出节点未选中分支输出 = 无值) 回放上一次预览(保持原预览不清空), 并透传本节点最近一次预览的图(下游可拿到该面之前预览的图进入合成; 从未预览过则透传 None, 下游按无值处理);
            filename_prefix (str, 默认 "preview"): 输出文件名前缀(控件, 保存时以按钮 POST 的为准);
            filename_suffix (str, 默认 ""): 文件名后缀(控件, 紧跟前缀, 保存时以按钮 POST 的为准);
            format (str, 默认 "png"): png/exr(控件);
            bit_depth (str, 默认 "8-bit"): 位深(控件);
            input_color_space (str, 默认 "sRGB"): 输入色彩空间(控件);
            prompt (dict|None): 工作流 prompt(缓存, 供保存时注入元数据);
            extra_pnginfo (dict|None): 额外元数据(同上);
            id (str | None, 默认 None): 节点唯一 ID, 用作缓存键。

        返回:
            dict: {"ui": {"images": [temp 预览记录...]}, "result": (images,)}。
        """
        # None (如扇出节点未选中分支输出 = 无值): 不动原来的数据 —— 回放上一次预览记录
        # (temp 文件仍在, 原预览保持显示); 透传本节点【最近一次预览的图】(下游如四图合成能拿到该面
        # 之前预览过的图进入合成, 未选中的面不再是黑空格); 从未预览过则透传 None (下游按无值处理);
        # 不更新「保存」缓存, 不崩溃
        if images is None:
            return {"ui": {"images": _last_ui.get(id, [])}, "result": (self._last_images(id),)}

        # 缓存最近一次预览的图片数据(供「保存」直接写 output, 无需重跑)
        # filename_prefix/filename_suffix 一并缓存: 这些输入可能被上游连线(如 MDTable 的 ID 列),
        # 此时 widget 里只是占位符, 实际值在 execute 收到的入参里 —— 保存用它而非占位符。
        _last_output[id] = {
            "images": list(images),
            "prompt": prompt,
            "extra_pnginfo": extra_pnginfo,
            "filename_prefix": filename_prefix,
            "filename_suffix": filename_suffix,
        }

        results = []
        for image in images:
            file, subfolder = self._make_temp_preview(image)
            results.append({"filename": file, "subfolder": subfolder, "type": "temp"})
        _last_ui[id] = results
        return {"ui": {"images": results}, "result": (images,)}


def _node_id(request: web.Request) -> str:
    """从 aiohttp 请求路径参数中取出 node_id 并去首尾空白。

    参数:
        request (web.Request): 已匹配路由的 aiohttp 请求。

    返回:
        str: 去空白后的节点 ID 字符串。
    """
    return request.match_info["node_id"].strip()


@PromptServer.instance.routes.post("/preview-image/save/{node_id}")
async def _handle_save(request: web.Request) -> web.Response:
    """HTTP 路由: 用缓存数据把该节点最近预览的图片写入 output(同名覆盖, 无序号)。

    流程: 前端点「保存」按钮时把 文件名/格式/位深/色彩空间 POST 过来;
    后端查 _last_output[node_id](execute 时缓存的图片), 有则按配置编码写 output, 无则 400。
    全程不触发任何工作流重跑。

    参数:
        request (web.Request): POST /preview-image/save/{node_id}, body 为 JSON
            {filename_prefix, filename_suffix, filename_prefix_linked, filename_suffix_linked,
             format, bit_depth, input_color_space}。

    返回:
        web.Response:
        - 成功: 200, {"status": "ok", "message": "已保存 N 张: <文件名>.<格式>"};
        - 失败: 400, {"status": "error", "message": "没有预览数据, 请先运行到该节点"}。
    """
    nid = _node_id(request)
    cache = _last_output.get(nid)
    if not cache or not cache.get("images"):
        return web.json_response(
            {"status": "error", "message": "没有预览数据, 请先运行到该节点"}, status=400
        )

    try:
        data = await request.json()
    except Exception:
        data = {}

    filename_prefix = str(data.get("filename_prefix", "preview"))
    # 若 filename_prefix 输入被上游连线(如 MDTable 的 ID), widget 值是占位符:
    # 用 execute 时实际接收到的值 (前端已标记 filename_prefix_linked)
    if data.get("filename_prefix_linked") and cache.get("filename_prefix") is not None:
        filename_prefix = str(cache["filename_prefix"])
    # 后缀同前缀: 手动输入或上游连线(连线时用 execute 实际接收值); 空串 = 不拼后缀
    # (旧工作流 widgets_values 按位置对齐, 尾部 null 落到 suffix 槽, 此处 or "" 兜底)
    filename_suffix = str(data.get("filename_suffix") or "")
    if data.get("filename_suffix_linked") and cache.get("filename_suffix") is not None:
        filename_suffix = str(cache["filename_suffix"])
    # 文件名 = 前缀 + 后缀 (拼接后整体可含 %batch_num%)
    name = filename_prefix + filename_suffix
    file_format = str(data.get("format", "png"))
    bit_depth = str(data.get("bit_depth", "8-bit"))
    colorspace = str(data.get("input_color_space", "sRGB"))

    node = PreviewImageSaveNode()
    node._save_batch_to_output(
        cache["images"],
        name,
        file_format,
        bit_depth,
        colorspace,
        cache.get("prompt"),
        cache.get("extra_pnginfo"),
    )
    return web.json_response(
        {
            "status": "ok",
            "message": f"已保存 {len(cache['images'])} 张: {name}.{file_format}",
        }
    )


NODE_CLASS_MAPPINGS = {
    "PreviewImageSave": PreviewImageSaveNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PreviewImageSave": "Preview Image (保存)",
}
