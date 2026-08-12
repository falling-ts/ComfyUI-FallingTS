# mdtable/nodes.py
"""FallingTSMarkDownTable 节点: 从 md 文件解析数据表, 弹窗选行, 节点内按字段类型渲染可编辑表单。

数据流:
- 「选择md文件」: 后端 tkinter 弹**系统文件选择器**, 记录绝对路径 (headless 时前端可直接在路径框粘贴);
- 「打开数据」: 前端内嵌 HTML 弹窗 (各字段模糊搜索 + 分页 + 首列单选), 选一行;
- 「确定」: 关闭弹窗, 节点把选中行的数据载入表单 (竖向排列, 按类型渲染控件), 可编辑;
- 「刷新」: 按 ID 重新查询 md 文件, 用磁盘最新值更新表单 (md 文件是唯一数据源, 节点只存路径+字段+选中行值)。

后端职责:
- 注册 3 条路由: select_file (系统选择器) / read (解析 md) / preview (本地 image/video/audio 预览);
- execute 读控件状态 (FALLINGTS_MD_TABLE) 输出: 0=ID, 1..N=各字段值 (按类型转换), 末位=data JSON;
- 输出端口声明为通配 `*` 定长槽, 前端按字段裁剪/重命名/定显示类型 (沿用 FallingTSTable 动态端口模式)。
"""

from __future__ import annotations

import asyncio
import os

from aiohttp import web
from server import PromptServer

from mdtable.parser import (
    DEFAULT_STATE,
    MAX_FIELDS,
    MAX_OUTPUTS,
    build_outputs,
    media_ref_id,
    normalize_state,
    parse_md_file,
)

# ─── IMAGE/VIDEO/AUDIO 字段资源解析 ──────────────────────────────────

# 各类型在 output/input 目录匹配的扩展名; _KIND_EXTS 供 execute 按字段类型过滤
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v")
_AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac", ".flac")
_MEDIA_EXTS = _IMAGE_EXTS + _VIDEO_EXTS + _AUDIO_EXTS
_KIND_EXTS = {"IMAGE": _IMAGE_EXTS, "VIDEO": _VIDEO_EXTS, "AUDIO": _AUDIO_EXTS}


def _media_dirs() -> tuple[str, ...]:
    """返回资源搜索目录 (output 优先, 其次 input)。

    目录全部由 folder_paths 按**当前安装位置**动态解析 (跟随 --output/--input-directory
    启动参数与 base_path), 项目整体搬走/换机器后自动跟随, 绝不写死绝对路径。
    """
    try:
        from folder_paths import get_input_directory, get_output_directory, base_path
    except Exception:
        return ()
    dirs = [get_output_directory(), get_input_directory()]
    try:
        if base_path and base_path not in dirs:
            dirs.append(base_path)  # 相对路径兜底 (如 output/foo.png)
    except Exception:
        pass
    # 去重 (output/input 可能软链同一目录), 保留顺序
    seen = set()
    out = []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return tuple(out)


def resolve_media_path(raw, exts=None) -> str | None:
    """把 IMAGE/VIDEO/AUDIO 字段值解析为真实文件路径 (全部动态解析, 不写死)。

    规则:
    - `@{ID}` 引用: 在 output/input 目录找 basename(去扩展) == ID 的媒体文件
      (兼容 `ID_00001_` 计数器命名); 按 exts 过滤类型;
    - 绝对路径: 存在则原样返回;
    - 相对路径: 依次相对 output/input/base 解析 (不依赖进程 CWD);
    - 其余: 返回 None (调用方按原字符串回退)。

    参数:
        raw: 字段原始值。
        exts: 允许匹配的扩展名元组; None 表示全部媒体类型 (预览用)。

    返回:
        str | None: 解析到的绝对路径, 未找到为 None。
    """
    exts = exts or _MEDIA_EXTS
    ref = media_ref_id(raw)
    if ref:
        for base in _media_dirs():
            if not base or not os.path.isdir(base):
                continue
            try:
                for fn in os.listdir(base):
                    if not os.path.isfile(os.path.join(base, fn)):
                        continue
                    stem, ext = os.path.splitext(fn)
                    if ext.lower() in exts and (stem == ref or stem.startswith(ref + "_")):
                        return os.path.join(base, fn)
            except OSError:
                continue
        return None
    p = os.path.normpath(str(raw or "").strip())
    if os.path.isabs(p):
        return p if os.path.isfile(p) else None
    # 相对路径: 相对各搜索根解析, 避免依赖进程 CWD
    for base in _media_dirs():
        cand = os.path.normpath(os.path.join(base, p))
        if os.path.isfile(cand):
            return cand
    return None


def load_image_tensor(path):
    """读图片为 ComfyUI IMAGE 张量 [B,H,W,3] float32 0~1。"""
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    arr = np.asarray(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def load_video_obj(path):
    """读视频为 ComfyUI VIDEO 对象 (惰性流式, 不预读帧)。"""
    from comfy_api.latest._input_impl import VideoFromFile

    return VideoFromFile(path)


def load_audio_obj(path):
    """读音频为 ComfyUI AUDIO 字典 {waveform, sample_rate}。"""
    from comfy_extras.nodes_audio import load as _load_audio

    waveform, sample_rate = _load_audio(path)
    return {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}


# 字段类型 -> 加载函数
_KIND_LOADERS = {
    "IMAGE": load_image_tensor,
    "VIDEO": load_video_obj,
    "AUDIO": load_audio_obj,
}


# ─── 系统文件选择器 ──────────────────────────────────────────────────


def _pick_file_dialog():
    """弹系统原生文件选择器 (tkinter), 返回选中文件的绝对路径; 失败/取消返回 None。

    tkinter 需要本机桌面会话; 在非主线程建 Tk 在 Windows 上可行。
    headless / 失败时前端会回退到手动粘贴路径。

    返回:
        str | None: 选中文件的绝对路径, 未选或异常为 None。
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    try:
        root = tk.Tk()
    except Exception:
        return None
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        return filedialog.askopenfilename(
            title="选择 Markdown 数据文件",
            filetypes=[("Markdown 文件", "*.md;*.markdown"), ("所有文件", "*.*")],
        )
    except Exception:
        return None
    finally:
        try:
            root.destroy()
        except Exception:
            pass


@PromptServer.instance.routes.post("/fallingts_mdtable/select_file")
async def _select_file(request: web.Request) -> web.Response:
    """HTTP 路由: 弹系统文件选择器并返回选中的 md 绝对路径。

    返回:
        web.Response:
        - 成功: 200, {"ok": true, "path": "绝对路径"};
        - 未选/失败: 200, {"ok": false, "error": "..."} (前端回退手动粘贴)。
    """
    loop = asyncio.get_running_loop()
    path = await loop.run_in_executor(None, _pick_file_dialog)
    if not path:
        return web.json_response(
            {"ok": False, "error": "未选择文件 (或无法弹出系统选择器, 可直接在节点路径框粘贴)"}
        )
    return web.json_response({"ok": True, "path": os.path.normpath(path)})


# ─── 读取 / 解析 md ──────────────────────────────────────────────────


@PromptServer.instance.routes.get("/fallingts_mdtable/read")
async def _read_md(request: web.Request) -> web.Response:
    """HTTP 路由: 读取并解析 md 文件, 返回字段定义 + 全部数据行。

    返回:
        web.Response:
        - 成功: 200, {"ok": true, "path", "fields": [{name,type}], "rows": [{id, values}], "total"};
        - 失败: 400, {"ok": false, "error": "..."}。
    """
    path = request.query.get("path", "").strip()
    if not path or not os.path.isfile(path):
        return web.json_response({"ok": False, "error": f"文件不存在: {path}"}, status=400)
    try:
        fields, rows = parse_md_file(path)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(
        {
            "ok": True,
            "path": os.path.normpath(path),
            "fields": fields,
            "rows": rows,
            "total": len(rows),
        }
    )


# ─── 本地文件预览 (image/video/audio 字段) ──────────────────────────

_PREVIEW_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}


@PromptServer.instance.routes.get("/fallingts_mdtable/preview")
async def _preview(request: web.Request) -> web.Response:
    """HTTP 路由: 提供本地 image/video/audio 文件 (供表单内嵌预览)。

    支持 `@{ID}` 引用: 先解析为实际文件路径再提供。

    返回:
        web.Response:
        - 200: 文件内容 (FileResponse, 支持 Range);
        - 404: 路径不存在或非可预览扩展名。
    """
    raw = request.query.get("path", "").strip()
    path = resolve_media_path(raw) if raw else None
    if not path or not os.path.isfile(path):
        return web.Response(status=404)
    ext = os.path.splitext(path)[1].lower()
    if ext not in _PREVIEW_MIME:
        return web.Response(status=404)
    return web.FileResponse(path, headers={"Content-Type": _PREVIEW_MIME[ext]})


@PromptServer.instance.routes.get("/fallingts_mdtable/resolve")
async def _resolve(request: web.Request) -> web.Response:
    """HTTP 路由: 把 IMAGE/VIDEO/AUDIO 字段值解析为实际文件绝对路径 (供节点展示)。

    支持 `@{ID}` 引用 (按 output/input 目录去扩展名匹配) 与直接路径; 按 kind 过滤类型。

    返回:
        web.Response:
        - 成功: 200, {"ok": true, "path": "绝对路径", "ref": "ID 或 null"};
        - 未找到: 200, {"ok": false, "path": null}。
    """
    raw = request.query.get("path", "").strip()
    kind = request.query.get("kind", "").upper()
    exts = _KIND_EXTS.get(kind) if kind in _KIND_EXTS else None
    path = resolve_media_path(raw, exts) if raw else None
    if path and os.path.isfile(path):
        return web.json_response({"ok": True, "path": os.path.normpath(path), "ref": media_ref_id(raw)})
    return web.json_response({"ok": False, "path": None})


# ─── 节点 ────────────────────────────────────────────────────────────


class FallingTSMarkDownTableNode:
    """md 数据表超级节点: 系统选择器选文件 -> 弹窗选行 -> 按类型渲染可编辑表单 -> 输出选中行各字段。

    输入: data (FALLINGTS_MD_TABLE DOM 控件), 值即状态 {md_path, fields, selected};
    输出: 动态端口 —— [0] ID, [1..] 各非 ID 字段 (按类型: int/float/bool 原生,
        list/set/dict 原生集合对象, image/video/audio/str 字符串), 末位 data (整行 JSON 字符串)。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入: 唯一自定义控件 FALLINGTS_MD_TABLE (前端 md_table.js 渲染)。"""
        return {
            "required": {
                "data": (
                    "FALLINGTS_MD_TABLE",
                    {
                        "default": DEFAULT_STATE,
                        "tooltip": (
                            "md 数据表: 选择md文件(系统选择器) → 打开数据弹窗选行 → "
                            "节点内按字段类型渲染可编辑表单; 刷新按 ID 重新查询 md 文件"
                        ),
                    },
                ),
            },
        }

    RETURN_TYPES = ("*",) * MAX_OUTPUTS
    RETURN_NAMES = tuple(f"out{i}" for i in range(MAX_OUTPUTS))
    OUTPUT_TOOLTIPS = tuple(
        "ID (STRING)" if i == 0
        else ("整行数据 JSON (STRING)" if i == MAX_OUTPUTS - 1 else f"字段 {i} (按类型)")
        for i in range(MAX_OUTPUTS)
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/表格"
    DESCRIPTION = (
        "从 md 文件解析数据表: 系统选择器选文件 → 弹窗按字段搜索+分页单选一行 → "
        "节点内按「标题(类型)」渲染可编辑表单 (IMAGE/VIDEO/AUDIO/STRING/INT/FLOAT/BOOLEAN/TEXT, "
        "TEXT 为多行文本框且输出同为 STRING), "
        "刷新按 ID 重查 md 文件; 输出选中行各字段 (按类型) + data JSON。"
    )
    SEARCH_ALIASES = [
        "md", "markdown", "表格", "数据表", "表单", "数据库", "角色库", "词条",
        "table", "read", "load", "挑选", "选行", "刷新",
    ]

    @classmethod
    def IS_CHANGED(cls, data) -> str:
        """缓存失效签名: 状态 (路径/字段/选中行/表单值) + IMAGE 字段源文件 mtime。"""
        import json

        sig = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
        # IMAGE/VIDEO/AUDIO 字段解析到的源文件变化 -> 本节点重跑 (避免缓存旧资源)
        try:
            state = normalize_state(data)
            for f in state["fields"][1:MAX_FIELDS]:
                if f["type"] in _KIND_LOADERS:
                    path = resolve_media_path(
                        state["selected"]["values"].get(f["name"], ""), _KIND_EXTS[f["type"]]
                    )
                    if path:
                        sig += "|" + str(os.path.getmtime(path))
        except Exception:
            pass
        return sig

    def execute(self, data):
        """节点执行入口: 由控件状态构建各字段输出值; IMAGE 字段解析为真实图片张量。

        参数:
            data (dict|None): FALLINGTS_MD_TABLE 控件值 ({md_path, fields, selected}),
                由前端 getValue 序列化进工作流并作为输入传入。

        返回:
            tuple: 长度 MAX_OUTPUTS; [0]=选中行 ID, [1..]=各非 ID 字段值 (按类型转换),
                IMAGE/VIDEO/AUDIO 字段解析成功为对应类型, 解析失败输出 None (可选输入惯例),
                未用槽 None, [MAX_OUTPUTS-1]=整行 {id, values} 的 JSON 字符串。
        """
        state = normalize_state(data)
        out = list(build_outputs(state))
        # IMAGE/VIDEO/AUDIO 字段 -> 解析 @{ID}/路径 并加载为对应类型; 解析失败输出 None
        for i, f in enumerate(state["fields"][1:MAX_FIELDS], start=1):
            loader = _KIND_LOADERS.get(f["type"])
            if loader:
                path = resolve_media_path(
                    state["selected"]["values"].get(f["name"], ""), _KIND_EXTS[f["type"]]
                )
                out[i] = loader(path) if path else None
        return tuple(out)


NODE_CLASS_MAPPINGS = {
    "FallingTSMarkDownTable": FallingTSMarkDownTableNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSMarkDownTable": "FallingTS MarkDown 数据表",
}
