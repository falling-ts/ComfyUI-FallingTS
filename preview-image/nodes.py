# preview-image/nodes.py
"""PreviewImageSave 节点: 始终预览(temp), 点「保存」才写 output(同名覆盖, 无序号)。

实现参考 ComfyUI 内置:
- 预览部分照 PreviewImage(nodes.py:1713): 写 temp 目录 + 随机前缀 + 低压缩 PNG, 前端 /view?type=temp 显示;
- 保存部分照 SaveImageAdvanced(comfy_extras/nodes_images.py:1155): _encode_image 按 格式/位深/色彩空间
  编码 + 注入 prompt 元数据;
- 差异: 保存用 {filename_prefix}.{format} 直接写 output, 同名覆盖, 不带 _序号 后缀
  (不走 get_save_image_path 的 counter), 且仅当前端点「保存」按钮(POST /preview-image/save/{id})才写。
"""

from __future__ import annotations

import os
import random
import string

from PIL import Image
import numpy as np

from aiohttp import web
from server import PromptServer
import folder_paths
from comfy.cli_args import args
from comfy_extras.nodes_images import _encode_image, inject_png_metadata, inject_exr_metadata


# 已请求保存的节点 id 集合: 点「保存」后前端 POST 标记, 下一次 execute 写 output 并清除
_save_requested: set[str] = set()


class PreviewImageSaveNode:
    """始终预览 + 点「保存」才写 output(同名覆盖, 无序号)。"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".images: 要预览/保存的图片;
            - "required".filename_prefix: 保存文件名(不含扩展名, 同名覆盖);
            - "required".format: png/exr;
            - "required".bit_depth: 位深(png→8/16bit, exr→32bit float);
            - "required".input_color_space: 输入色彩空间(png→sRGB, exr→sRGB/HDR/linear);
            - "hidden".prompt/extra_pnginfo/id: 元数据与节点 id。
        """
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "要预览/保存的图片。"}),
                "filename_prefix": (
                    "STRING",
                    {
                        "default": "preview",
                        "multiline": False,
                        "tooltip": "保存到 output 的文件名(不含扩展名); 同名文件直接覆盖, 无序号",
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

    @classmethod
    def IS_CHANGED(cls, id: str | None = None, **kwargs):
        """缓存失效签名: 保存请求参与缓存键, 点「保存」后该节点判定已变化而重新执行(从而写 output)。

        参数:
            id (str | None): 节点唯一 ID, 与 hidden.id 对应;
            **kwargs: 其余输入(images 等), 本方法不读取。

        返回:
            tuple[bool]: (id 是否已在 _save_requested 中,) 作为缓存键的一部分。
        """
        return (id in _save_requested,)

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

    def execute(
        self,
        images,
        filename_prefix: str = "preview",
        format: str = "png",
        bit_depth: str = "8-bit",
        input_color_space: str = "sRGB",
        prompt=None,
        extra_pnginfo=None,
        id: str | None = None,
    ):
        """节点执行入口: 始终生成 temp 预览; 若已点「保存」则按控件配置写 output 并清除标记。

        逻辑: 先逐张生成 temp PNG 预览返回 UI; 若 id 在 _save_requested(点过「保存」),
        则按 filename_prefix/format/bit_depth/input_color_space 编码写 output(覆盖、无序号),
        然后清除保存标记。

        参数:
            images (torch.Tensor): BxHxWxC 图片批;
            filename_prefix (str, 默认 "preview"): 输出文件名前缀;
            format (str, 默认 "png"): png/exr;
            bit_depth (str, 默认 "8-bit"): 位深;
            input_color_space (str, 默认 "sRGB"): 输入色彩空间;
            prompt (dict|None): 工作流 prompt;
            extra_pnginfo (dict|None): 额外元数据;
            id (str | None, 默认 None): 节点唯一 ID, 用于查保存请求。

        返回:
            dict: {"ui": {"images": [temp 预览记录...]}, "result": (images,)}。
        """
        results = []
        for image in images:
            file, subfolder = self._make_temp_preview(image)
            results.append({"filename": file, "subfolder": subfolder, "type": "temp"})

        if id in _save_requested:
            _save_requested.discard(id)
            self._save_batch_to_output(
                images, filename_prefix, format, bit_depth, input_color_space, prompt, extra_pnginfo
            )

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
    """HTTP 路由: 标记该节点"已请求保存"(点「保存」按钮时前端调用)。

    流程: 把 node_id 加入 _save_requested, 前端随后触发本节点 partial 重跑,
    该节点 execute 检测到标记即写 output 并清除标记。

    参数:
        request (web.Request): POST /preview-image/save/{node_id} 请求, node_id 取自路径。

    返回:
        web.Response: {"status": "ok"}。
    """
    nid = _node_id(request)
    _save_requested.add(nid)
    return web.json_response({"status": "ok"})


NODE_CLASS_MAPPINGS = {
    "PreviewImageSave": PreviewImageSaveNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PreviewImageSave": "Preview Image (保存)",
}
