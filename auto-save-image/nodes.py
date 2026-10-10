# auto-save-image/nodes.py
"""AutoSaveImage 节点: 预览 + 【执行即自动保存】。

保存口径与「预览图片」(preview-image 的 PreviewImageSave)点「保存」**完全一致** ——
本节点不另写一套落盘逻辑, 而是直接继承 PreviewImageSaveNode 复用它的实现:

- 输入控件、temp 预览编码、`_last_ui` 预览缓存、images=None 的 sticky 回放: 全部沿用父类;
- 落盘: 直接调父类的 `_save_batch_to_output(前缀 + 后缀, 格式, 位深, 色彩空间, ...)`,
  所以文件名是 `{前缀}{后缀}.{格式}`、同名覆盖无序号、元数据注入与格式/位深/色彩空间口径
  与点「保存」逐字节相同。

与 PreviewImageSave 的差别只有两点:

1. **没有「保存」按钮** —— execute 里就把本批图片写进 output, 不必点按钮、不重跑工作流;
2. 工作流名不再由前端在点按钮时 POST, 而是**随 prompt 带进来**: 前端 `web/js/auto_save_image.js`
   包装 `POST /prompt`, 把当前工作流名写进 `extra_pnginfo.workflow.extra.fallingts_workflow_name`;
   无头提交也可以直接在 `extra_pnginfo` 顶层写 `workflow_name` (优先取它)。子目录名仍走
   `output_subdir.resolve_subdir`: **优先 md 数据表文件名, 没有 md 表才用工作流名**, 都没有则
   output 根 —— 与插件其余保存节点同一口径。

预览回填复用 preview-image 的 `GET /preview-image/image-url/{id}`: 两者共用同一份 `_last_ui` 缓存
(键口径也相同: `<工作流根 id>::<节点 id>`), 因此本节点**不需要任何自己的路由**,
preview-image 的代码一行未改。
"""

from __future__ import annotations

import importlib
import logging

# preview-image 目录名含连字符, 只能经 importlib 按名加载 —— 这里拿到的是 ComfyUI 进程里
# 同一个模块对象, 所以 _last_ui / _last_output / _scoped_key 等都是与它共享的那一份缓存
_PI = importlib.import_module("preview-image.nodes")
PreviewImageSaveNode = _PI.PreviewImageSaveNode

logger = logging.getLogger(__name__)

# extra_pnginfo 顶层键: 无头 API 提交时直接写这个名字(优先取)
WORKFLOW_NAME_TOP_KEY = "workflow_name"
# workflow.extra 下的键: 前端包装 POST /prompt 时注入(见 web/js/auto_save_image.js)
WORKFLOW_NAME_EXTRA_KEY = "fallingts_workflow_name"


def workflow_name_from_extra(extra_pnginfo) -> str:
    """从 extra_pnginfo 里取「当前工作流名」, 供产物子目录解析使用。

    两条通道, 顶层优先:

    - `extra_pnginfo["workflow_name"]`: 无头/脚本提交自己写的;
    - `extra_pnginfo["workflow"]["extra"]["fallingts_workflow_name"]`: 前端注入的
      (前端拿不到 execute 时机, 只能跟着 prompt 一起送进来)。

    参数:
        extra_pnginfo (dict|None): execute 收到的额外元数据。

    返回:
        str: 工作流名(已去首尾空白); 取不到返回空串 —— 调用方据此退回 output 根。
    """
    if not isinstance(extra_pnginfo, dict):
        return ""

    top = extra_pnginfo.get(WORKFLOW_NAME_TOP_KEY)
    if isinstance(top, str) and top.strip():
        return top.strip()

    workflow = extra_pnginfo.get("workflow")
    if not isinstance(workflow, dict):
        return ""
    extra = workflow.get("extra")
    if not isinstance(extra, dict):
        return ""
    name = extra.get(WORKFLOW_NAME_EXTRA_KEY)
    return name.strip() if isinstance(name, str) and name.strip() else ""


class AutoSaveImageNode(PreviewImageSaveNode):
    """预览图片 + 执行即自动保存(同名覆盖、无序号); 没有「保存」按钮。"""

    DESCRIPTION = (
        "预览图片, 并在执行到本节点时【自动保存】: 按 {前缀}{后缀}.{格式} 写入 output"
        "(同名覆盖, 无序号), 不必点「保存」; 保存口径与「预览图片」一致, 子目录优先用"
        "工作流的 md 数据表文件名, 没有 md 表才用工作流名。"
    )
    SEARCH_ALIASES = ["auto save", "自动保存", "保存图片", "save image", "预览图片"]

    @classmethod
    def IS_CHANGED(cls, **kwargs) -> float:
        """永不复用执行缓存 —— 自动保存必须在**每次执行**时落盘。

        证据(2026-10-05 端到端实测): 同一张图连跑两次, 第二次 ComfyUI 直接命中 output 缓存
        (`execution.py:446` 的 `caches.outputs.get(unique_id)`, 输出节点也照样跳过), execute 根本
        没被调用 —— 产物文件时间戳不变, 换个工作流名重跑还会沿用旧子目录(名字不在缓存键里)。
        预览保存类节点中只有本节点依赖 execute 落盘(「预览图片」是点按钮走 HTTP 路由, 不受缓存
        影响), 故显式让签名每次都不同; 返回 `float("NaN")`(任何比较都不相等; `execution.py:102`
        给动态 prompt 节点也是这么置的)比自增计数器更直白。
        """
        return float("NaN")

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
        """节点执行入口: 先把本批图片写 output(自动保存), 再生成 temp 预览返回 UI。

        保存参数一律取 execute 的实参(而不是 widget 里的占位值) —— filename_prefix /
        filename_suffix 常被上游连线(如「加载视频」的 prefix 输出), 连线时 widget 只是占位符。

        参数:
            images (torch.Tensor|None): BxHxWxC 图片批; None(如扇出未选中分支 = 无值)时
                不落盘、不动原数据, 回放上一次预览记录并把本节点最近一次预览的图透传给下游;
            filename_prefix (str, 默认 "preview"): 文件名前缀(默认值同父类, 便于手输);
            filename_suffix (str, 默认 ""): 文件名后缀(紧跟前缀, 拼接后整体可含 %batch_num%);
            format (str, 默认 "png"): png/exr;
            bit_depth (str, 默认 "8-bit"): 位深(png→8/16-bit, exr→16/32-bit float);
            input_color_space (str, 默认 "sRGB"): 输入色彩空间(png→sRGB, exr→sRGB/HDR/HDR PQ/linear/HDR LogC3/HDR ACEScct);
            prompt (dict|None): 工作流 prompt(注入元数据 + 解析 md 表子目录);
            extra_pnginfo (dict|None): 额外元数据(兼取当前工作流名, 见 workflow_name_from_extra);
            id (str|None): 节点唯一 ID, 用作预览缓存键的一部分(另一半是工作流作用域)。

        返回:
            dict: {"ui": {"images": [temp 预览记录...]}, "result": (images,)}。
        """
        # 缓存键带工作流作用域: 只按节点 id 缓存会跨工作流串图(父类 _workflow_scope)
        scope = _PI._workflow_scope(extra_pnginfo)

        # None(扇出未选中分支): 不落盘、不更新保存缓存, 回放预览 + 透传最近一次预览的图
        if images is None:
            return {
                "ui": {"images": _PI._cache_get(_PI._last_ui, id, scope) or []},
                "result": (self._last_images(id, scope),),
            }

        filename_prefix = str(filename_prefix if filename_prefix is not None else "preview")
        filename_suffix = str(filename_suffix or "")
        file_format = str(format or "png")
        bit_depth = str(bit_depth or "8-bit")
        colorspace = str(input_color_space or "sRGB")

        # 与 PreviewImageSave 一致地留一份「最近一次图片」缓存: images=None 时透传给下游
        _PI._last_output[_PI._scoped_key(id, scope)] = {
            "images": list(images),
            "prompt": prompt,
            "extra_pnginfo": extra_pnginfo,
            "filename_prefix": filename_prefix,
            "filename_suffix": filename_suffix,
        }

        # 自动保存: 前缀 + 后缀拼接后整体作文件名(同名覆盖, 无 _序号); 子目录优先 md 表文件名
        workflow_name = workflow_name_from_extra(extra_pnginfo)
        name = filename_prefix + filename_suffix
        self._save_batch_to_output(
            images,
            name,
            file_format,
            bit_depth,
            colorspace,
            prompt,
            extra_pnginfo,
            workflow_name,
        )
        where = _PI.resolve_subdir(workflow_name, prompt)
        logger.info(
            "[FallingTS] 自动保存图片 %d 张: %s%s.%s",
            len(images),
            f"{where}/" if where else "",
            name,
            file_format,
        )

        results = []
        for image in images:
            file, subfolder = self._make_temp_preview(image)
            results.append({"filename": file, "subfolder": subfolder, "type": "temp"})
        _PI._last_ui[_PI._scoped_key(id, scope)] = results
        return {"ui": {"images": results}, "result": (images,)}


NODE_CLASS_MAPPINGS = {
    "AutoSaveImage": AutoSaveImageNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AutoSaveImage": "Auto Save Image (自动保存)",
}
