# load-video/nodes.py
r"""FallingTS 加载视频 (来自输出 + 截帧)。

参考内置 LoadVideo(ComfyUI/comfy_extras/nodes_video.py), 保留它的加载口径:
- 下拉从 output 目录取视频(remote 路由 + 刷新按钮 + 上传按钮);
- 值经 folder_paths.get_annotated_filepath(..., default_dir=output) 解析, 带 " [output]"
  标注的值仍按标注走。

本模块另加四件事:

1. **下拉候选由自身路由 GET /fallingts_load_video/files 提供**(与「加载图像」同一口径):
   内置 /internal/files/output 只列 output 根目录一层, 而本工作区产物全落在数字目录
   (0035_场景截帧/、0010_灰度遮罩/ …) 里 ⇒ 内置节点的下拉在本机基本是空的。本路由扫
   output 根视频 + 数字目录(正则 ^\d+_)内部整棵子树的视频, 按 mtime 倒序, 值形如
   0035_场景截帧/00001_陈落.mp4(不带 " [output]" 标注, 见「加载图像」模块的同一条说明)。
   remote **不设 control_after_refresh** —— 刷新只重新拉候选列表, 不改写已选值。

2. **「序列号」+「名称」**: 截帧保存的命名。序列号 = output/<工作流产物目录>/ 里已有
   编号的最大值 + 1(目录不存在或没有 "数字_" 命名的文件时为 0), 显示为 5 位; 前端在
   节点创建/打开工作流时自动拉取一次, 刷新按钮可随时重算, 保存帧后自动续到下一个可用号。

3. **「保存帧」**: 把选中帧逐张写成 output/<目录>/<序列号>_<名称>.png。

4. **截帧/完成/选中帧输出**(自 PreviewVideo 迁移; 预览视频节点只保留「保存」):
   - 执行时把视频编码到 temp 并 UI.PreviewVideo 让前端播放, 同时 get_components() 拆出
     帧集合缓存; 前端「截帧」按钮按播放时间取帧, 「完成」后输出 image_1..image_N;
   - 未「完成」时输出全部 ExecutionBlocker(None) 阻断下游(到本节点停下, 等截帧);
   - fingerprint_inputs 纳入选中帧/完成状态/重置代际, 使 partial 提交时本节点必然重跑;
     已完成且已有缓存时 execute 直接取缓存输出, 不重新解码视频。
"""

from __future__ import annotations

import io as _io
import os
import random
import re
import string
from urllib.parse import quote

import numpy as np
from PIL import Image
from aiohttp import web
from server import PromptServer

import folder_paths
from comfy_api.latest import IO, Types, UI, InputImpl
from comfy_execution.graph_utils import ExecutionBlocker

from output_subdir import next_sequence, safe_dir_name, sequence_dir

_NODE_NAME = "FallingTSLoadVideo"

# 截帧输出上限(与 composite 的 MAX_TOTAL=64 一致; 后端声明定长槽, 前端按需增删端口)
MAX_FRAMES = 64

# 资源表目录口径: 数字开头 + 下划线(0035_场景截帧 / 0010_灰度遮罩 …)
_NUMERIC_DIR_RE = re.compile(r"^\d+_")

# 目录名/文件名里不允许出现的字符(Windows 非法字符 + 路径分隔符)
_UNSAFE_CHARS = '<>:"/\\|?*'

# 最近一次加载/预览的缓存: node_id -> {"video","images","fps","file","selected_frames",...}
_last_output: dict[str, dict] = {}

# 已「完成」截帧的节点: set[node_id] —— 完成前下游输出被阻断, 完成后输出选中帧
_done: set[str] = set()

# 重置代际: /fallingts_load_video/reset 时递增, 纳入 fingerprint_inputs
_reset_generation: int = 0


# ─── 下拉列表: output 根 + 数字目录内部的视频 ────────────────────────────────


def _is_video_file(name: str) -> bool:
    """按扩展名判视频(复用核心的 MIME 缓存, 与内置 LoadVideo.define_schema 同口径)。"""
    return bool(folder_paths.filter_files_content_types([name], ["video"]))


def _collect_output_items(directory: str, prefix: str = "") -> list[tuple[float, str]]:
    """递归收集 (mtime, "sub/name.ext") 项。

    - prefix 为空(output 根): 只递归**数字目录** —— output 里还有 clipspace 这类
      非资源目录, 不把它们的内容混进下拉;
    - prefix 非空(已在数字目录内): 整棵子树都收(资源目录内部允许再分层)。
    """
    items: list[tuple[float, str]] = []
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return items

    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                if prefix or _NUMERIC_DIR_RE.match(entry.name):
                    items.extend(_collect_output_items(entry.path, prefix + entry.name + "/"))
                continue
            if not entry.is_file() or not _is_video_file(entry.name):
                continue
            items.append((entry.stat().st_mtime, prefix + entry.name))
        except OSError:
            continue
    return items


def _list_relative(directory: str) -> list[str]:
    """按相对路径列出目录里的视频(供 define_schema 的初始候选)。"""
    return sorted(name for _, name in _collect_output_items(directory))


@PromptServer.instance.routes.get("/fallingts_load_video/files")
async def _list_output_files(request: web.Request) -> web.Response:
    """给节点的下拉喂候选值: output 根 + 数字目录内部的视频, 按 mtime 倒序。"""
    items = _collect_output_items(folder_paths.get_output_directory())
    items.sort(key=lambda item: -item[0])
    return web.json_response([value for _, value in items])


# ─── 序列号: 产物目录里已有的编号 + 1 ────────────────────────────────────────


# 编号与产物目录解析都放在 output_subdir 里共用(「加载图像」的序列号用同一套口径):
# next_sequence(目录) -> 下一个可用编号, sequence_dir(工作流名, prompt) -> 产物目录绝对路径。


@PromptServer.instance.routes.get("/fallingts_load_video/next_sequence")
async def _handlenext_sequence(request: web.Request) -> web.Response:
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


def _sanitize_name(name) -> str:
    """清洗「名称」: 去扩展名、路径分隔与非法字符, 返回安全的纯文件名(不含扩展名)。"""
    text = os.path.splitext(str(name or ""))[0]
    text = text.replace("/", "-").replace("\\", "-")
    for ch in _UNSAFE_CHARS:
        text = text.replace(ch, "-")
    text = re.sub(r"[\r\n\t ]+", "-", text.strip())
    return text.strip(" .-")[:120]


# ─── 帧工具(与 preview-video 同实现) ───────────────────────────────────────


def _frames_from_cache(cached: dict, selected: list[int]) -> list:
    """按选中帧号列表从缓存的帧集合取图(1-based → 张量索引), 未选中槽 None。"""
    images = cached.get("images")
    total = len(images) if images is not None else 0
    out: list = [None] * MAX_FRAMES
    for i, fno in enumerate(selected[:MAX_FRAMES]):
        idx = fno - 1
        if images is not None and 0 <= idx < total:
            frame = images[idx]
            out[i] = frame.unsqueeze(0) if frame.dim() == 3 else frame[:1]
    return out


def _png_bytes(frame) -> bytes:
    """把单帧张量编码为 PNG 字节(低压缩)。兼容 [H,W,C] 与 [1,H,W,C]。"""
    if frame.dim() == 4:
        frame = frame[0]
    arr = (frame.float().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
    buf = _io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


# ─── 节点 ──────────────────────────────────────────────────────────────────


class FallingTSLoadVideoNode(IO.ComfyNode):
    """加载视频 (来自输出 + 截帧): 内置 LoadVideo 的超集。"""

    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: node_id/display_name/category/description, 输入 name + sequence + video,
            输出 video + image_1..image_MAX_FRAMES, hidden 含 prompt+extra_pnginfo+unique_id,
            标记 is_output_node=True(有 UI 预览, 且是截帧后 partial 提交的锚点)。
        """
        files = _list_relative(folder_paths.get_output_directory())
        outputs = [IO.Video.Output("video", tooltip="加载的视频(原样透传, 供下游拆解/编辑)。")]
        outputs += [
            IO.Image.Output(
                f"image_{i}",
                display_name=f"选中帧 {i}",
                tooltip=f"第 {i} 个截帧(前端点「截帧」累积, 未选中为 None)。",
            )
            for i in range(1, MAX_FRAMES + 1)
        ]
        return IO.Schema(
            node_id=_NODE_NAME,
            display_name="FallingTS 加载视频 (来自输出 + 截帧)",
            category="FallingTS",
            description=(
                "Load a video from the output directory (including videos inside numbered subdirectories); "
                "capture frames from it and save them as <sequence>_<name>.png into the workflow's output subdirectory. "
                "「序列号」是保存帧的编号(自动取目录里最大编号 + 1, 可改, 右侧刷新按钮重算), 「名称」是保存帧的文件名。"
            ),
            inputs=[
                IO.String.Input(
                    "name",
                    default="",
                    multiline=False,
                    tooltip="保存帧的文件名(不含扩展名): output/<产物目录>/<序列号>_<名称>.png",
                ),
                # 字符串而非 INT: 编号按 5 位书写(00000), 前端补零显示, 保存时按整数解析
                IO.String.Input(
                    "sequence",
                    default="",
                    multiline=False,
                    tooltip="保存帧的编号: 自动取产物目录里已有编号的最大值 + 1(目录为空时为 00000), 可手动改",
                ),
                IO.Combo.Input(
                    "video",
                    options=files,
                    upload=IO.UploadType.video,
                    image_folder=IO.FolderType.output,
                    remote=IO.RemoteOptions(
                        route="/fallingts_load_video/files",
                        refresh_button=True,
                        # 不设 control_after_refresh: 刷新/跑完自动刷新只重新拉候选, 不改写已选值
                        control_after_refresh=None,
                    ),
                    tooltip="要加载的视频(下拉来自 output 目录, 含数字目录内部的资源; 也可直接上传)",
                ),
            ],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo, IO.Hidden.unique_id],
            is_output_node=True,
            outputs=outputs,
        )

    @classmethod
    def execute(cls, video, name: str = "", sequence: str = "") -> IO.NodeOutput:
        """节点执行入口: 加载视频 → 编码 temp 供预览 → 拆帧缓存 → 按「完成」输出选中帧。

        逻辑:
        - 已「完成」且已有帧缓存: 直接取缓存输出(partial 提交时本节点会再次执行, 走这条
          路径不重新解码视频), 不重新编码 temp;
        - 未「完成」: 解码视频并编码到 temp 预览, 拆帧缓存, 输出全部 ExecutionBlocker(None)
          阻断下游(合成/保存都不跑, "到本节点就停下, 等截帧"), 但 UI.PreviewVideo 照常发出;
        - 「完成」: 输出视频 + 选中帧 image_1..image_MAX_FRAMES(未选中槽 None)。

        参数:
            video (str): 视频文件名(相对 output, 形如 0035_场景截帧/00001_陈落.mp4)。
            name (str, 默认 ""): 保存帧的文件名。
            sequence (str, 默认 ""): 保存帧的编号(5 位文本, 如 "00005"; 缓存起来供「保存帧」兜底)。

        返回:
            IO.NodeOutput: 视频 + 64 个选中帧槽(未选中/未完成时按上述语义填)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        # V3 节点的 hidden 不进 execute 实参(execution.py 的 get_finalized_class_inputs 单独摘出),
        # prompt 只能经 cls.hidden 取, 缓存下来供「保存帧」解析产物子目录名。
        prompt = getattr(cls.hidden, "prompt", None)

        cached = _last_output.get(nid_str)
        if nid_str in _done and cached and cached.get("file"):
            return IO.NodeOutput(
                cached.get("video"),
                *_frames_from_cache(cached, cached.get("selected_frames") or []),
                ui=UI.PreviewVideo([UI.SavedResult(cached["file"], cached.get("subfolder") or "", IO.FolderType.temp)]),
            )

        video_path = folder_paths.get_annotated_filepath(
            video, default_dir=folder_paths.get_output_directory()
        )
        loaded = InputImpl.VideoFromFile(video_path)

        width, height = loaded.get_dimensions()
        prefix = "ComfyUI_temp_" + "".join(random.choice(string.ascii_lowercase) for _ in range(5))
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            prefix,
            folder_paths.get_temp_directory(),
            width,
            height,
        )
        ext = Types.VideoContainer.get_extension("mp4")
        file = f"{filename}_{counter:05}_.{ext}"
        loaded.save_to(
            os.path.join(full_output_folder, file),
            format=Types.VideoContainer.MP4,
            codec=Types.VideoCodec.AUTO,
        )

        # 拆出帧集合缓存(截帧数据源): images = [N,H,W,C] 张量
        try:
            components = loaded.get_components()
            images = components.images
            fps = float(components.frame_rate) if components.frame_rate else 0.0
        except Exception:
            images = None
            fps = 0.0

        try:
            sequence_value = int(str(sequence).strip() or 0)
        except ValueError:
            sequence_value = 0

        selected_frames = (cached or {}).get("selected_frames") or []
        _last_output[nid_str] = {
            "video": loaded,
            "name": name,
            "sequence": max(0, sequence_value),
            "prompt": prompt,
            "path": video_path,
            "file": file,
            "subfolder": subfolder,
            "images": images,
            "fps": fps,
            "selected_frames": selected_frames,
        }

        ui = UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)])
        if nid_str not in _done:
            # 未「完成」: 阻断下游, 但预览照发(视频照常出现在节点上供播放/截帧)
            return IO.NodeOutput(*([ExecutionBlocker(None)] * (1 + MAX_FRAMES)), ui=ui)
        return IO.NodeOutput(loaded, *_frames_from_cache(_last_output[nid_str], selected_frames), ui=ui)

    @classmethod
    def fingerprint_inputs(cls, video=None, **kwargs):
        """缓存失效签名: 文件名 + 文件 mtime + 选中帧 + 是否完成 + 重置代际。

        截帧/删帧/完成都改变缓存里的 selected_frames/_done, 「重置」递增 _reset_generation;
        指纹随之变化 → 本节点在重提交时必然重新执行(否则会被 ComfyUI 全局执行缓存跳过,
        下游拿到旧的选中帧)。文件本身用 mtime 而不是内容哈希 —— 视频文件可能很大。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        cached = _last_output.get(nid_str) or {}

        stamp = video
        try:
            path = folder_paths.get_annotated_filepath(
                video, default_dir=folder_paths.get_output_directory()
            )
            stamp = (video, os.path.getmtime(path))
        except Exception:
            pass

        return (
            stamp,
            _reset_generation,
            nid_str,
            tuple(cached.get("selected_frames") or ()),
            nid_str in _done,
        )

    @classmethod
    def validate_inputs(cls, video, **kwargs) -> bool | str:
        """文件不存在时给出明确提示(内置 LoadVideo 同口径; 值默认按 output 解析)。"""
        try:
            path = folder_paths.get_annotated_filepath(
                video, default_dir=folder_paths.get_output_directory()
            )
        except ValueError:
            return "Invalid video file: {}".format(video)
        if not os.path.isfile(path):
            return "Invalid video file: {}".format(video)
        return True


# ─── 截帧 / 完成 / 重置 / 预览 路由 ─────────────────────────────────────────


async def _handle_frame(request: web.Request) -> web.Response:
    """按前端播放时间/帧号从缓存帧集合取该帧, 编码 PNG 返回并追加到选中帧列表。"""
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache or cache.get("images") is None:
        return web.json_response(
            {"status": "error", "message": "没有可截帧的视频数据, 请先运行到该节点"}, status=400
        )
    images = cache["images"]
    total = len(images)

    try:
        data = await request.json()
    except Exception:
        data = {}

    mode = str(data.get("mode", "time"))
    append = bool(data.get("append", True))
    fps = float(cache.get("fps") or 0.0)
    if mode == "frame":
        try:
            fno = int(data.get("frame_index") or 0)
        except (TypeError, ValueError):
            return web.json_response({"status": "error", "message": "frame_index 非法"}, status=400)
    else:
        try:
            pos = float(data.get("position_seconds") or 0.0)
        except (TypeError, ValueError):
            pos = 0.0
        # 播放时间 → 1-based 帧号 (浏览器 video.currentTime 是浮点秒)
        fno = int(round(pos * fps)) + 1 if fps > 0.0 and total > 1 else 1
    fno = max(1, min(int(fno), total))

    if append:
        selected = cache.get("selected_frames") or []
        if fno in selected:
            return web.json_response(
                {"status": "error", "message": f"帧 {fno} 已在选中列表中 (可删除后重新截帧)"}, status=400
            )
        if len(selected) >= MAX_FRAMES:
            return web.json_response(
                {"status": "error", "message": f"已达截帧上限 {MAX_FRAMES} 张"}, status=400
            )
        selected.append(fno)
        cache["selected_frames"] = selected

    try:
        png = _png_bytes(images[fno - 1])
    except Exception as e:
        return web.json_response({"status": "error", "message": f"帧编码失败: {e}"}, status=400)

    response = web.Response(body=png, content_type="image/png")
    response.headers["X-Frame-Index"] = str(fno)
    response.headers["X-Selected-Count"] = str(len(cache.get("selected_frames") or []))
    return response


async def _handle_frame_remove(request: web.Request) -> web.Response:
    """从缓存 selected_frames 移除指定帧号(或清空)。"""
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache:
        return web.json_response({"status": "error", "message": "没有缓存数据"}, status=400)

    try:
        data = await request.json()
    except Exception:
        data = {}

    selected = cache.get("selected_frames") or []
    if data.get("clear"):
        selected = []
    else:
        try:
            fno = int(data.get("frame_index") or 0)
        except (TypeError, ValueError):
            return web.json_response({"status": "error", "message": "frame_index 非法"}, status=400)
        selected = [f for f in selected if f != fno]
    cache["selected_frames"] = selected
    return web.json_response({"status": "ok", "frames": selected})


async def _handle_done(request: web.Request) -> web.Response:
    """标记该节点「完成截帧」: 下一次执行输出选中帧并放行下游。"""
    nid = request.match_info["node_id"].strip()
    cache = _last_output.setdefault(nid, {"selected_frames": [], "video": None})
    try:
        data = await request.json()
    except Exception:
        data = None
    if data and isinstance(data.get("frames"), list):
        try:
            cache["selected_frames"] = [int(f) for f in data["frames"] if f is not None]
        except (TypeError, ValueError):
            pass
    # 仅当已有选中帧才置完成(没帧的"完成"= 预加载上游, 走 reset + 全量提交)
    if cache.get("selected_frames"):
        _done.add(nid)
    return web.json_response({"status": "ok", "done": nid in _done})


async def _handle_reset(request: web.Request) -> web.Response:
    """重置所有加载视频节点为未完成(默认 Run 时调用), 并递增代际强制重跑。"""
    global _reset_generation
    _done.clear()
    _reset_generation += 1
    return web.json_response({"status": "ok"})


async def _handle_state(request: web.Request) -> web.Response:
    """返回该节点当前的截帧状态, 供前端在页面刷新后重建帧列表。"""
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid) or {}
    images = cache.get("images")
    return web.json_response(
        {
            "status": "ok",
            "selected_frames": [int(f) for f in (cache.get("selected_frames") or [])],
            "done": nid in _done,
            "total_frames": len(images) if images is not None else 0,
            "has_video": cache.get("video") is not None,
        }
    )


async def _handle_preview_url(request: web.Request) -> web.Response:
    """返回该节点当前缓存视频的可播放 URL, 供前端在刷新后重建预览。"""
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid) or {}
    file = cache.get("file")
    if not file:
        return web.json_response({"status": "error", "message": "没有可预览的视频, 请先运行到该节点"}, status=400)
    subfolder = cache.get("subfolder") or ""
    return web.json_response(
        {"status": "ok", "url": f"/view?filename={quote(file)}&subfolder={quote(subfolder)}&type=temp"}
    )


async def _handle_save_frames(request: web.Request) -> web.Response:
    """把选中的帧逐张写成 output/<产物目录>/<序列号>_<名称>.png。

    body: {"frames": [帧号...](缺省用缓存里已选的), "sequence": int(缺省用缓存值或自动重算),
           "name": "名称", "workflow_name": 当前工作流名(据此解析产物子目录), "dir": 直接指定目录名}
    返回: {"status":"ok","message":...,"saved":[...],"next_sequence":int}。
    编号撞上已存在的文件时顺延到下一个空号, 不覆盖已有产物。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache or cache.get("images") is None:
        return web.json_response(
            {"status": "error", "message": "没有可保存的帧, 请先运行到该节点再截帧"}, status=400
        )

    try:
        data = await request.json()
    except Exception:
        data = {}

    images = cache["images"]
    total = len(images)
    raw_frames = data.get("frames") or cache.get("selected_frames") or []
    frames: list[int] = []
    for item in raw_frames:
        try:
            fno = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= fno <= total and fno not in frames:
            frames.append(fno)
    if not frames:
        return web.json_response({"status": "error", "message": "还没有截帧, 请先点「截帧」"}, status=400)

    sub = safe_dir_name(data.get("dir")) or sequence_dir(data.get("workflow_name"), cache.get("prompt"))
    base = folder_paths.get_output_directory()
    out_dir = os.path.join(base, sub) if sub else base
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        return web.json_response({"status": "error", "message": f"无法创建产物目录: {e}"}, status=500)

    seq = data.get("sequence")
    if seq is None:
        seq = cache.get("sequence")
    try:
        seq = int(seq)
    except (TypeError, ValueError):
        seq = next_sequence(out_dir)
    seq = max(0, seq)

    name = _sanitize_name(data.get("name") if data.get("name") is not None else cache.get("name")) or "frame"

    saved: list[str] = []
    for fno in frames:
        # 撞号顺延, 绝不覆盖已有产物
        while os.path.exists(os.path.join(out_dir, f"{seq:05d}_{name}.png")):
            seq += 1
        target = os.path.join(out_dir, f"{seq:05d}_{name}.png")
        try:
            with open(target, "wb") as f:
                f.write(_png_bytes(images[fno - 1]))
        except OSError as e:
            return web.json_response(
                {"status": "error", "message": f"写入 {os.path.basename(target)} 失败: {e}"}, status=500
            )
        saved.append(f"{seq:05d}_{name}.png")
        seq += 1

    cache["sequence"] = seq
    where = f"{sub}/" if sub else ""
    return web.json_response(
        {
            "status": "ok",
            "message": f"已保存 {len(saved)} 帧: {where}{saved[0]}" + (" …" if len(saved) > 1 else ""),
            "saved": saved,
            "next_sequence": next_sequence(out_dir),
        }
    )


PromptServer.instance.routes.post("/fallingts_load_video/frame/{node_id}")(_handle_frame)
PromptServer.instance.routes.post("/fallingts_load_video/frame-remove/{node_id}")(_handle_frame_remove)
PromptServer.instance.routes.post("/fallingts_load_video/done/{node_id}")(_handle_done)
PromptServer.instance.routes.post("/fallingts_load_video/reset")(_handle_reset)
PromptServer.instance.routes.post("/fallingts_load_video/save_frames/{node_id}")(_handle_save_frames)
PromptServer.instance.routes.get("/fallingts_load_video/state/{node_id}")(_handle_state)
PromptServer.instance.routes.get("/fallingts_load_video/preview-url/{node_id}")(_handle_preview_url)
