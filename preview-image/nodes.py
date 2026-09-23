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
from urllib.parse import quote

from PIL import Image
import numpy as np
import torch

from aiohttp import web
from server import PromptServer
import folder_paths
from comfy.cli_args import args
from comfy_extras.nodes_images import _encode_image, inject_png_metadata, inject_exr_metadata

from output_subdir import resolve_subdir, safe_dir_name


# 最近一次预览的图片数据缓存: 缓存键 -> {"images": [张量...], "prompt": ..., "extra_pnginfo": ...}
# 点「保存」时前端把控件配置 POST 过来, 后端直接用这里的缓存写 output(无需重跑工作流)
_last_output: dict[str, dict] = {}

# 最近一次预览的 UI 记录缓存: 缓存键 -> ui["images"] 列表(指向 temp 目录文件)
# 输入为 None (如扇出未选中分支) 时回放此列表, 保持原有预览不被清空
_last_ui: dict[str, list] = {}


def _workflow_scope(extra_pnginfo) -> str:
    """从 extra_pnginfo 取当前工作流的根 id, 作为缓存键的工作流作用域。

    该 id 就是工作流 JSON 的根 `id`(前端 `graph.serialize().id`; 前端的
    `graphToPrompt()` 把 `graph.serialize()` 整个塞进 `extra_pnginfo.workflow`, 所以这里
    取到的和前端 `app.graph.id` 是同一个值)。

    **为什么必须带工作流作用域**: 只按节点 id 缓存会跨工作流串图 —— 节点 id 在各工作流之间
    大量重复(实测 `18` 撞 6 个工作流、`62` 撞 4 个、`901`~`908` 各撞 3~4 个), 打开工作流 B 时
    会把之前跑过的 A 的同 id 节点预览当成 B 的预览显示出来(遗留预览)。

    参数:
        extra_pnginfo (dict|None): execute 收到的额外元数据。

    返回:
        str: 工作流根 id; 取不到(如无头 API 直接提交、未带 extra_pnginfo)时返回空串。
    """
    if not isinstance(extra_pnginfo, dict):
        return ""
    workflow = extra_pnginfo.get("workflow")
    if not isinstance(workflow, dict):
        return ""
    return str(workflow.get("id") or "").strip()


def _scoped_key(node_id, workflow_id=None) -> str:
    """把 (工作流 id, 节点 id) 拼成缓存键; 工作流 id 缺失时退回纯节点 id。

    参数:
        node_id (str|int|None): 节点唯一 ID。
        workflow_id (str|None): 工作流根 id(见 _workflow_scope)。

    返回:
        str: 缓存键 "<工作流 id>::<节点 id>", 或纯 "<节点 id>"。
    """
    nid = str(node_id or "")
    wid = str(workflow_id or "").strip()
    return f"{wid}::{nid}" if wid and nid else nid


def _cache_get(cache: dict, node_id, workflow_id=None):
    """按 (工作流, 节点) 读缓存: 优先带工作流标识的键, 再退回纯节点 id。

    退回纯节点 id 是为了兼容「那次执行没带工作流标识」的写入(无头 API 提交时
    extra_pnginfo 为空), 否则页面刷新后这类预览就再也读不回来了。

    参数:
        cache (dict): _last_output 或 _last_ui。
        node_id (str|int|None): 节点唯一 ID。
        workflow_id (str|None): 调用方声明的当前工作流根 id。

    返回:
        *: 命中的缓存值; 未命中返回 None。
    """
    keys = [str(node_id or "")]
    if workflow_id:
        keys.insert(0, _scoped_key(node_id, workflow_id))
    for key in keys:
        if key in cache:
            return cache[key]
    return None


def _safe_dir_name(name) -> str:
    """把工作流名清洗成可安全用作单层目录名的字符串(实现见 output_subdir.safe_dir_name)。

    参数:
        name (str|None): 前端传来的工作流名(可能含 .json 后缀或完整路径)。

    返回:
        str: 清洗后的目录名; 空串表示不该建子目录(退回 output 根)。
    """
    return safe_dir_name(name)


def _workflow_output_dir(workflow_name, prompt=None) -> str:
    """取保存目录: output 下按子目录名建目录, 不存在则创建; 名字非法时退回 output 根。

    子目录名由 output_subdir.resolve_subdir 解析 —— 工作流里有 md 数据表节点时用它的
    表文件名, 没有 md 表节点才用工作流名(理由见该模块头部说明)。

    参数:
        workflow_name (str|None): 前端传来的当前工作流名。
        prompt (dict|None): 该节点 execute 时缓存的 API prompt(用于找 md 表节点)。

    返回:
        str: 可直接拼接文件名的目录绝对路径(保证存在)。
    """
    base = folder_paths.get_output_directory()
    sub = resolve_subdir(workflow_name, prompt)
    if not sub:
        return base
    target = os.path.join(base, sub)
    os.makedirs(target, exist_ok=True)
    return target



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
        workflow_name=None,
    ) -> None:
        """按格式编码并写 output: 文件名 {prefix}.{format}, 同名直接覆盖, 无 _序号 后缀。

        参数:
            images (torch.Tensor): BxHxWxC 批张量;
            filename_prefix (str): 文件名前缀(可含 %batch_num% 按批号区分);
            file_format (str): png/exr;
            bit_depth (str): 位深(8-bit/16-bit/32-bit float);
            colorspace (str): 输入色彩空间(sRGB/HDR/linear);
            prompt (dict|None): 工作流 prompt(注入元数据; 同时用于解析产物子目录名);
            extra_pnginfo (dict|None): 额外元数据;
            workflow_name (str|None): 当前工作流名; 非空时在 output 下建同名子目录再写
                (工作流里有 md 数据表节点时改用表文件名, 见 _workflow_output_dir)。

        返回:
            None: 直接写文件到 output(或其子目录)目录。
        """
        output_dir = _workflow_output_dir(workflow_name, prompt)

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
    def _last_images(id, workflow_id=None) -> "torch.Tensor | None":
        """取该节点最近一次预览的图片, 重组为 BxHxWxC 批张量 (来自 _last_output 缓存); 无缓存返回 None。

        用于 None 透传: 本节点本次没有新图 (如扇出未选中分支) 时, 把该节点上一次预览的图透传给下游
        (如四图合成), 让下游能拿到该面「之前预览过」的图进入合成, 而非黑空格。

        参数:
            id (str | None): 节点唯一 ID, 用作缓存键的一部分。
            workflow_id (str | None): 当前工作流根 id(缓存作用域, 见 _workflow_scope)。

        返回:
            torch.Tensor | None: BxHxWxC 批张量; 无缓存 (从未预览过) 或形状不一致无法堆叠时 None (下游按无值处理)。
        """
        cache = _cache_get(_last_output, id, workflow_id)
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

        逻辑: 逐张生成 temp PNG 预览返回 UI; 把 images/prompt/extra_pnginfo 存进 _last_output[工作流 id::节点 id]
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
            id (str | None, 默认 None): 节点唯一 ID, 用作缓存键的一部分(另一半是工作流作用域, 见 _workflow_scope)。

        返回:
            dict: {"ui": {"images": [temp 预览记录...]}, "result": (images,)}。
        """
        # 缓存键带工作流作用域: 只按节点 id 缓存会跨工作流串图(见 _workflow_scope)
        scope = _workflow_scope(extra_pnginfo)

        # None (如扇出节点未选中分支输出 = 无值): 不动原来的数据 —— 回放上一次预览记录
        # (temp 文件仍在, 原预览保持显示); 透传本节点【最近一次预览的图】(下游如四图合成能拿到该面
        # 之前预览过的图进入合成, 未选中的面不再是黑空格); 从未预览过则透传 None (下游按无值处理);
        # 不更新「保存」缓存, 不崩溃
        if images is None:
            return {
                "ui": {"images": _cache_get(_last_ui, id, scope) or []},
                "result": (self._last_images(id, scope),),
            }

        # 缓存最近一次预览的图片数据(供「保存」直接写 output, 无需重跑)
        # filename_prefix/filename_suffix 一并缓存: 这些输入可能被上游连线(如 MDTable 的 ID 列),
        # 此时 widget 里只是占位符, 实际值在 execute 收到的入参里 —— 保存用它而非占位符。
        _last_output[_scoped_key(id, scope)] = {
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
        _last_ui[_scoped_key(id, scope)] = results
        return {"ui": {"images": results}, "result": (images,)}


def _node_id(request: web.Request) -> str:
    """从 aiohttp 请求路径参数中取出 node_id 并去首尾空白。

    参数:
        request (web.Request): 已匹配路由的 aiohttp 请求。

    返回:
        str: 去空白后的节点 ID 字符串。
    """
    return request.match_info["node_id"].strip()


def _temp_file_exists(item: dict) -> bool:
    """判断一条 temp 预览记录指向的文件是否还在。

    缓存是纯内存的, 而 temp 文件会被清理(重启/手工清 temp), 留下指不到文件的死条目 ——
    这种条目不该再返回给前端, 否则节点上会挂一张加载失败的图。

    参数:
        item (dict): _last_ui 里的一条 {"filename", "subfolder", "type"} 记录。

    返回:
        bool: 文件存在返回 True。
    """
    name = item.get("filename")
    if not name:
        return False
    path = os.path.join(folder_paths.get_temp_directory(), item.get("subfolder") or "", name)
    return os.path.isfile(path)


@PromptServer.instance.routes.get("/preview-image/image-url/{node_id}")
async def _handle_image_url(request: web.Request) -> web.Response:
    """HTTP 路由: 返回该节点最近一次预览图的 URL 列表, 供前端在刷新后重建预览。

    原生 UI.PreviewImage 是一次性 WebSocket 事件, 页面刷新后不会重发, 图片预览就空了。
    execute 时已把 temp 预览记录存进 _last_ui[工作流 id::节点 id](filename/subfolder/type), 这里直接
    转成 /view URL 返回 —— 与 preview-audio 的 /audio-url 同构, 后端是唯一事实来源。
    不重新编码图片, 只复用已有的 temp 文件; 指向的文件已被清理的条目会被过滤掉。

    缓存按 (工作流根 id, 节点 id) 取: 前端必须带 `?workflow_id=<app.graph.id>`。不带就只按节点 id 查,
    那时会命中「那次执行没带工作流标识」写下的条目 —— 跨工作流串图的旧毛病正是这么来的, 所以前端
    一律要带。

    参数:
        request (web.Request): GET /preview-image/image-url/{node_id}?workflow_id=<工作流根 id>。

    返回:
        web.Response: 200 {"status":"ok","urls":[...]}; 无缓存时 400。
    """
    items = _cache_get(_last_ui, _node_id(request), request.query.get("workflow_id")) or []
    items = [it for it in items if _temp_file_exists(it)]
    if not items:
        return web.json_response({"status": "error", "message": "没有可预览的图片, 请先运行到该节点"}, status=400)
    urls = [
        f"/view?filename={quote(it['filename'])}&subfolder={quote(it.get('subfolder') or '')}&type=temp"
        for it in items
        if it.get("filename")
    ]
    return web.json_response({"status": "ok", "urls": urls})


@PromptServer.instance.routes.post("/preview-image/save/{node_id}")
async def _handle_save(request: web.Request) -> web.Response:
    """HTTP 路由: 用缓存数据把该节点最近预览的图片写入 output(同名覆盖, 无序号)。

    流程: 前端点「保存」按钮时把 文件名/格式/位深/色彩空间 POST 过来;
    后端查 _last_output[工作流 id::节点 id](execute 时缓存的图片), 有则按配置编码写 output, 无则 400。
    全程不触发任何工作流重跑。子目录名优先取该次执行缓存的 md 数据表文件名(见 output_subdir),
    工作流里没有 md 表节点时才用 body 里的 workflow_name。

    缓存按 (工作流根 id, 节点 id) 取 —— 前端必须带 body 字段 workflow_id(=`app.graph.id`)。
    不带就只按节点 id 查, 会命中别的工作流留下的同 id 节点数据(跨工作流串图), 所以前端一律要带。

    参数:
        request (web.Request): POST /preview-image/save/{node_id}, body 为 JSON
            {filename_prefix, filename_suffix, filename_prefix_linked, filename_suffix_linked,
             format, bit_depth, input_color_space, workflow_name, workflow_id}。

    返回:
        web.Response:
        - 成功: 200, {"status": "ok", "message": "已保存 N 张: <文件名>.<格式>"};
        - 失败: 400, {"status": "error", "message": "没有预览数据, 请先运行到该节点"}。
    """
    nid = _node_id(request)

    try:
        data = await request.json()
    except Exception:
        data = {}

    cache = _cache_get(_last_output, nid, data.get("workflow_id"))
    if not cache or not cache.get("images"):
        return web.json_response(
            {"status": "error", "message": "没有预览数据, 请先运行到该节点"}, status=400
        )

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
        data.get("workflow_name"),
    )
    saved_dir = resolve_subdir(data.get("workflow_name"), cache.get("prompt"))
    where = f"{saved_dir}/" if saved_dir else ""
    return web.json_response(
        {
            "status": "ok",
            "message": f"已保存 {len(cache['images'])} 张: {where}{name}.{file_format}",
        }
    )


NODE_CLASS_MAPPINGS = {
    "PreviewImageSave": PreviewImageSaveNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PreviewImageSave": "Preview Image (保存)",
}
