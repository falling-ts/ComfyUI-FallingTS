# mask-rename/nodes.py
"""遮罩编辑器文件整理: 让 clipspace 遮罩文件保存到 clipspace 子目录, 并复制成品到 output 根。

背景:
- input/ 与 output/ 均软链到同一物理目录(media)。
- 内置遮罩编辑器通过 /upload/image 上传, 前端硬编码 type=input、不带 subfolder → 默认落 input 根。

本模块做两件事:
1. 【包装 /upload/image 路由】(aiohttp 路由替换, 不改打包前端/ComfyUI 核心):
   对文件名以 clipspace- 开头的上传, 直接保存到 input/clipspace/(= output/clipspace),
   返回 subfolder='clipspace' —— 节点引用自动带 subfolder, 重新打开遮罩编辑器可完整恢复
   -mask/-paint 层继续编辑。
2. 【POST /fallingts_mask/rename】: 复制 input/clipspace 里的 clipspace-painted-masked-{ts}.png
   到 output/{base}.png(按 ID 命名成品, 同名覆盖)。

目录结构:
  - input/output 根: 只有成品 {base}.png
  - input/clipspace/: 遮罩编辑文件(clipspace-*, 可重新编辑)

base 名 = 预览节点 execute 时缓存的 filename_prefix(即 MD 行 ID)。
"""

from __future__ import annotations

import importlib
import logging
import os
import re
import shutil
import time

from aiohttp import web
from server import PromptServer
import folder_paths

logger = logging.getLogger(__name__)

# preview-image 目录名含连字符, 经 importlib 按名加载, 取 _last_output 缓存的 filename_prefix
_preview_image = importlib.import_module("preview-image.nodes")
_last_output = _preview_image._last_output

_CLIPSPACE_PREFIX = "clipspace-painted-masked-"
# 只允许处理「近期」生成的遮罩文件(防误动历史文件); 传 force=true 可绕过
_RECENT_MS = 10 * 60 * 1000


def _sanitize_base(name: str) -> str:
    """清洗 base 名: 去扩展名、路径分隔、非法字符, 返回安全的纯文件名(不含扩展名)。"""
    if not name:
        return ""
    name = os.path.splitext(str(name))[0]
    name = re.sub(r'[\\/:*?"<>|\r\n\t ]+', "-", name.strip())
    name = name.strip(" .-")
    return name[:120] or ""


# ─── 1) 包装 /upload/image: clipspace-* 上传直接保存到 input/clipspace ──────────────


def _save_clipspace_upload(image, filename: str) -> web.Response:
    """把 clipspace-* 上传文件保存到 input/clipspace/, 返回 subfolder='clipspace' 引用。"""
    input_dir = folder_paths.get_input_directory()
    clip_dir = os.path.join(input_dir, "clipspace")
    os.makedirs(clip_dir, exist_ok=True)
    safe = os.path.basename(filename)
    filepath = os.path.join(clip_dir, safe)
    try:
        with open(filepath, "wb") as f:
            f.write(image.file.read())
    except OSError as e:
        logger.warning("保存遮罩文件失败 %s: %s", filepath, e)
        return web.Response(status=500)
    return web.json_response({"name": safe, "subfolder": "clipspace", "type": "input"})


def _install_upload_hook() -> bool:
    """替换 /upload/image 路由 handler: 对 clipspace-* 上传走 clipspace 子目录, 其余交还原 handler。"""
    try:
        app = PromptServer.instance.app
    except Exception:
        return False
    for route in list(app.router.routes()):
        if getattr(route, "method", None) != "POST":
            continue
        # ComfyUI 1.48.7+ 给 API 路由加了 /api 前缀重新注册; 两个路径都要包装
        canonical = getattr(getattr(route, "resource", None), "canonical", "")
        if canonical not in ("/upload/image", "/api/upload/image"):
            continue
        # 防重复包装(立即尝试 + on_startup 都可能走到)
        if getattr(route, "_handler", None) and getattr(route._handler, "_ft_clipspace_hook", False):
            return True
        orig = route._handler

        async def wrapped(request: web.Request, _orig=orig) -> web.Response:
            # 预读 multipart(aiohttp 会缓存 post, 原 handler 再取不重复解析)
            try:
                post = await request.post()
            except Exception:
                post = {}
            image = post.get("image")
            filename = getattr(image, "filename", None) if image else None
            if filename and filename.startswith("clipspace-"):
                return _save_clipspace_upload(image, filename)
            return await _orig(request)

        wrapped._ft_clipspace_hook = True
        route._handler = wrapped
        return True
    return False


async def _on_startup(app) -> None:
    """app 启动时(add_routes 已执行后)再包装 /upload/image。"""
    if _install_upload_hook():
        logger.info("遮罩文件将保存到 input/clipspace 子目录(/upload/image 已包装)")
    else:
        logger.warning("未能包装 /upload/image 路由, 遮罩文件将落 input 根目录")


# 插件加载时 server.py 的 routes 尚未 add(init_extra_nodes 早于 add_routes),
# 立即尝试一次(手动注入等场景), 失败则注册 on_startup 兜底
if not _install_upload_hook():
    try:
        PromptServer.instance.app.on_startup.append(_on_startup)
    except Exception:
        pass


# ─── 2) 复制成品到 output 根 ─────────────────────────────────────────────────────


@PromptServer.instance.routes.post("/fallingts_mask/rename")
async def _rename_mask(request: web.Request) -> web.Response:
    """复制 input/clipspace 里的 clipspace-painted-masked-{ts}.png -> output/{base}.png(成品)。

    body: {"node_id": "前端节点 id", "image_ref": "clipspace-painted-masked-1754976000123.png", "base": "可选覆盖"}
    返回: {"ok": true,
           "edit_ref": {"filename": "clipspace-painted-masked-{ts}.png", "subfolder": "clipspace", "type": "input"},
           "out_ref": {"filename": "{base}.png", "subfolder": "", "type": "output"},
           "copied": bool}
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    node_id = str(data.get("node_id", ""))
    image_ref = str(data.get("image_ref", "")).strip()

    if not image_ref.startswith(_CLIPSPACE_PREFIX):
        return web.json_response({"ok": False, "error": "非 clipspace 遮罩文件"}, status=400)
    ts = image_ref[len(_CLIPSPACE_PREFIX):].split(".")[0]
    if not ts.isdigit():
        return web.json_response({"ok": False, "error": "无法解析时间戳"}, status=400)

    # 只允许处理近期文件; force=true 可绕过
    age_ms = int(time.time() * 1000) - int(ts)
    if age_ms > _RECENT_MS and not data.get("force"):
        return web.json_response(
            {"ok": False, "error": f"文件生成于 {age_ms // 1000}s 前, 已超出近期窗口, 跳过(防误动历史文件)"},
            status=400,
        )

    # base 名: 前端传入 > 预览节点缓存 filename_prefix > 兜底 mask-{ts}
    base = _sanitize_base(str(data.get("base") or ""))
    if not base:
        cached = _last_output.get(node_id) if node_id else None
        if cached:
            base = _sanitize_base(str(cached.get("filename_prefix") or ""))
    base = base or f"mask-{ts}"

    input_dir = folder_paths.get_input_directory()
    output_dir = folder_paths.get_output_directory()

    # 源: input/clipspace/ 优先, 兼容旧路径 input 根
    src = os.path.join(input_dir, "clipspace", f"clipspace-painted-masked-{ts}.png")
    if not os.path.isfile(src):
        src = os.path.join(input_dir, f"clipspace-painted-masked-{ts}.png")
    if not os.path.isfile(src):
        return web.json_response({"ok": False, "error": "找不到对应遮罩文件"}, status=400)

    copied = False
    out_file = os.path.join(output_dir, f"{base}.png")
    try:
        shutil.copyfile(src, out_file)
        copied = True
    except OSError as e:
        logger.warning("复制成品失败 %s: %s", out_file, e)

    edit_ref = {
        "filename": f"clipspace-painted-masked-{ts}.png",
        "subfolder": "clipspace",
        "type": "input",
    }
    out_ref = {"filename": f"{base}.png", "subfolder": "", "type": "output"}
    return web.json_response(
        {"ok": True, "edit_ref": edit_ref, "out_ref": out_ref, "copied": copied}
    )
