# 让前端文件列表看到"编号子目录"里的文件
#
# 背景: 保存类节点 (PreviewImageSave / PreviewVideo / PreviewAudioSave / 遮罩编辑器)
# 会把产物写进 output/<工作流名>/ 这样的子目录, 而 ComfyUI 的
# GET /internal/files/{directory_type} 是这样列的:
#
#     sorted((entry for entry in os.scandir(directory) if is_visible_file(entry)), ...)
#
# os.scandir 不递归, is_visible_file 又要求 entry.is_file(), 于是子目录被整个跳过 ——
# 前端「已保存 / 已生成」下拉里因此看不到保存进去的文件。
#
# 本模块给 /internal 子应用挂一个 middleware, 接管该路由: 顶层文件照旧, 额外进入
# **"编号+分隔符+名称"形式的子目录**(如 0010_灰度遮罩 —— 保存类节点按工作流名建的那层) 把里面的
# 文件一并列出。判据是 "数字 + 连字符或下划线"(`-` 为早期命名, `_` 为现行命名),
# 这样 ComfyUI 自建的 3d 目录不会被卷进来。
#
# 返回格式与核心保持一致: "<相对路径> [<directory_type>]", 相对路径用 '/' 分隔。
# LoadImage 等节点用 folder_paths.get_annotated_filepath 解析该值, 它走
# os.path.join(base_dir, name) 且带 is_within_directory 防穿越校验, 因此子路径可直接用。

from __future__ import annotations

import logging
import os
import re

from aiohttp import web

import nodes as comfy_nodes
from folder_paths import filter_files_content_types, get_directory_by_type, get_input_directory
from api_server.routes.internal.internal_routes import InternalRoutes

logger = logging.getLogger(__name__)

# 与核心 get_files 接受的口径一致
_DIRECTORY_TYPES = ("output", "input", "temp")

# 只认 "编号+分隔符+名称" 形式的子目录 (0010_灰度遮罩 / 0040-文生视频); ComfyUI 自建的 3d 不符合, 不扫
_NUMBERED_DIR = re.compile(r"^\d+[-_]")


def _iter_files(directory: str, prefix: str = ""):
    """产出 (相对路径, mtime): 本层文件 + 编号子目录里的文件。

    参数:
        directory (str): 当前目录绝对路径。
        prefix (str): 相对最外层目录的前缀, 末尾带 '/'。

    返回:
        Iterator[tuple[str, float]]
    """
    try:
        entries = list(os.scandir(directory))
    except OSError as exc:
        logger.warning("numbered_subdirs: 无法读取 %s: %s", directory, exc)
        return

    for entry in entries:
        name = entry.name
        if name.startswith("."):
            continue
        if entry.is_file():
            yield prefix + name, entry.stat().st_mtime
        elif entry.is_dir() and _NUMBERED_DIR.match(name):
            yield from _iter_files(entry.path, f"{prefix}{name}/")


@web.middleware
async def _files_middleware(request: web.Request, handler):
    """接管 GET /internal/files/{type}, 额外列出编号子目录里的文件。"""
    if request.method != "GET":
        return await handler(request)

    parts = request.path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "internal" or parts[1] != "files":
        return await handler(request)

    directory_type = parts[2]
    if directory_type not in _DIRECTORY_TYPES:
        return await handler(request)

    items = sorted(_iter_files(get_directory_by_type(directory_type)), key=lambda it: -it[1])
    return web.json_response([f"{name} [{directory_type}]" for name, _ in items], status=200)


def _resolve_under(base_dir: str, relative: str) -> str | None:
    """把相对路径解析到 base_dir 内; 越界返回 None。"""
    base = os.path.abspath(base_dir)
    full = os.path.abspath(os.path.join(base, relative))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full


@web.middleware
async def _view_middleware(request: web.Request, handler):
    """让 /view 认识带子目录的 filename。

    核心 /view 结尾会做 `filename = os.path.basename(filename)`, 于是
    "0040-文生视频/a.png" 被截成 "a.png" 而 404; 它认识的子目录写法是独立的
    subfolder 查询参数。前端只传 filename, 所以在这里替它拆开。
    """
    if request.method != "GET" or request.path.rstrip("/") not in ("/view", "/api/view"):
        return await handler(request)

    query = request.rel_url.query
    filename = query.get("filename") or ""
    if filename.startswith("blake3:") or query.get("subfolder"):
        return await handler(request)

    parts = filename.replace("\\", "/").rsplit("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return await handler(request)

    subfolder, name = parts
    base_dir = get_directory_by_type(query.get("type", "output"))
    if base_dir is None:
        return await handler(request)

    full = _resolve_under(base_dir, f"{subfolder}/{name}")
    if full is None:
        return web.Response(status=403)
    if not os.path.isfile(full):
        return web.Response(status=404)
    return web.FileResponse(full)


def _patch_view_route() -> None:
    """给主 app 挂上 _view_middleware (/view 在主 app, 不在 /internal 子应用)。"""
    from server import PromptServer

    server = PromptServer.instance
    if server is None or server.app is None:
        logger.warning("numbered_subdirs: PromptServer 未就绪, /view 未补子目录支持")
        return
    if _view_middleware not in server.app.middlewares:
        server.app.middlewares.append(_view_middleware)


def apply() -> None:
    """挂 middleware 并 patch LoadImage (须在 app 启动前生效)。"""
    original_get_app = InternalRoutes.get_app

    def get_app(self):
        app = original_get_app(self)
        if _files_middleware not in app.middlewares:
            app.middlewares.append(_files_middleware)
        return app

    InternalRoutes.get_app = get_app
    _patch_load_image()
    _patch_view_route()
    logger.info("numbered_subdirs: 文件列表/Loader 下拉/预览 支持编号子目录")


def _list_relative(directory: str) -> list[str]:
    """按相对路径列出目录: 本层文件 + 编号子目录里的文件。"""
    return sorted(name for name, _ in _iter_files(directory))


def _patch_load_image() -> None:
    """让 LoadImage 的下拉也含编号子目录里的图。

    LoadImage.INPUT_TYPES 是静态生成的 (核心用 os.listdir 只列顶层), 不经过
    /internal/files, 所以要在同一处一起补上。
    """
    original_input_types = comfy_nodes.LoadImage.INPUT_TYPES.__func__

    @classmethod
    def INPUT_TYPES(cls):
        data = original_input_types(cls)
        files = filter_files_content_types(_list_relative(get_input_directory()), ["image"])
        data["required"]["image"] = (files, {"image_upload": True})
        return data

    comfy_nodes.LoadImage.INPUT_TYPES = INPUT_TYPES
