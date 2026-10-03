# load-video/nodes.py
r"""FallingTS 加载视频 (来自输出 + 截帧)。

参考内置 LoadVideo(ComfyUI/comfy_extras/nodes_video.py), 保留它的加载口径:
- 下拉从 output 目录取视频(remote 路由 + 刷新按钮 + 上传按钮);
- 值经 folder_paths.get_annotated_filepath(..., default_dir=output) 解析, 带 " [output]"
  标注的值仍按标注走。

本模块在原加载口径之外另加这些能力:

1. **下拉候选由自身路由 GET /fallingts_load_video/files 提供**(与「加载图像」同一口径):
   内置 /internal/files/output 只列 output 根目录一层, 而本工作区产物全落在数字目录
   (0035_场景截帧/、0010_灰度遮罩/ …) 里 ⇒ 内置节点的下拉在本机基本是空的。本路由扫
   output 根视频 + 数字目录(正则 ^\d+_)内部整棵子树的视频, 按 mtime 倒序, 值形如
   0035_场景截帧/00001_陈落.mp4(不带 " [output]" 标注, 见「加载图像」模块的同一条说明)。
   remote **不设 control_after_refresh** —— 刷新只重新拉候选列表, 不改写已选值。

2. **「序列号」+「名称」**: 产物文件名前缀的命名。序列号 = output/<工作流产物目录>/ 里已有
   编号的最大值 + 1(目录不存在或没有 "数字_" 命名的文件时为 0), 显示为 5 位; 前端在
   节点创建/打开工作流时自动拉取一次, 刷新按钮可随时重算。

3. **音频输出**: 执行时 get_components() 的音轨直接给 `audio` 输出 —— 拆音不需要截帧,
    该输出**不受「完成」门控**(只有 image_1..N 被门控), 于是「加载视频 → 音频后处理」这条链
    在未点「完成」时就能跑通。

4. **「序列号_名称」前缀输出**: `prefix`(STRING) = `<序列号>_<名称>`(口径见
    output_subdir.sequence_prefix), 接各预览保存节点的 `filename_prefix` —— 拆帧/拆音/截取
    这类"表驱动"工作流不再需要 md 数据表提供文件名前缀。与 `audio` 一样**不受「完成」门控**
    (拆音链在未截帧时也要能落盘)。

5. **「原视频」可外部传入**: 可选 VIDEO 输入 `video_in`(数据表「原视频」列等)—— 连上就用它,
    不连则用自身下拉(下拉是 COMBO, 前端不允许把 VIDEO/STRING 连进 COMBO, 故另开这一个口)。

6. **截帧/完成/选中帧输出**(自 PreviewVideo 迁移; 预览视频节点只保留「保存」):
   - 执行时把视频编码到 temp 并 UI.PreviewVideo 让前端播放, 同时 get_components() 拆出
     帧集合缓存; 前端「截帧」按钮按播放时间取帧, 「完成」后输出 image_1..image_N;
   - ⚠️ **截帧不要求先跑过本节点**: 帧缓存只在进程内存里, 缓存为空时(重启 ComfyUI /
     刚选好或上传视频还没执行)截帧路由会按请求带来的 video 值**现场拆帧**(懒解码)建好
     缓存 —— 用户既然能在节点上播放视频, 就该能直接截帧(旧行为报「请先运行到该节点」);
   - 未「完成」时输出全部 ExecutionBlocker(None) 阻断下游(到本节点停下, 等截帧);
   - fingerprint_inputs 纳入选中帧/完成状态/重置代际, 使 partial 提交时本节点必然重跑;
     已完成且已有缓存时 execute 直接取缓存输出, 不重新解码视频。
"""

from __future__ import annotations

import io as _io
import logging
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

from output_subdir import next_sequence, safe_dir_name, sequence_dir, sequence_prefix

_NODE_NAME = "FallingTSLoadVideo"

# 截帧输出上限(与 composite 的 MAX_TOTAL=64 一致; 后端声明定长槽, 前端按需增删端口)
MAX_FRAMES = 64

# 资源表目录口径: 数字开头 + 下划线(0035_场景截帧 / 0010_灰度遮罩 …)
_NUMERIC_DIR_RE = re.compile(r"^\d+_")

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


def _resolve_video_path(value) -> str | None:
    """把节点上的视频值解析成绝对路径(纯文件名 / 相对 output 的子目录 / 上传到 input 的文件)。

    值默认按 output 解析(与 execute 口径一致); output 里找不到再退回 input —— 上传按钮把
    文件写进 input 目录, 而未跑过本节点时缓存里没有解析好的路径。
    """
    text = str(value or "").strip()
    if not text:
        return None
    bases = (folder_paths.get_output_directory(), folder_paths.get_input_directory())
    for base in bases:
        try:
            path = folder_paths.get_annotated_filepath(text, default_dir=base)
        except Exception:
            continue
        if os.path.isfile(path):
            return path
    for base in bases:
        path = os.path.join(base, text)
        if os.path.isfile(path):
            return path
    return None


def _decode_frames(loaded) -> dict:
    """拆出视频的帧集合/音轨/帧率, 失败只记日志并三项置空(不抛)。

    核心 get_components() 一次性解出帧与音轨: 拆不出帧时音轨同样没有, 故这里三项一起兜底;
    调用方(截帧 vs 普通执行)各自决定拿不到帧时是报错还是照常输出。
    """
    try:
        components = loaded.get_components()
        return {
            "images": components.images,
            "audio": components.audio,
            "fps": float(components.frame_rate) if components.frame_rate else 0.0,
        }
    except Exception as e:
        logging.warning("[FallingTS] 视频拆帧失败: %s", e)
        return {"images": None, "audio": None, "fps": 0.0}


def _encode_temp_preview(loaded) -> tuple[str, str]:
    """把视频编码成一份 temp 预览, 返回 (file, subfolder); 编不出时抛异常由调用方兜底。

    与 execute 同口径(随机前缀 + 5 位计数 + mp4), 供「页面刷新后重建播放器」使用。
    """
    width, height = loaded.get_dimensions()
    temp_prefix = "ComfyUI_temp_" + "".join(random.choice(string.ascii_lowercase) for _ in range(5))
    full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
        temp_prefix,
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
    return file, subfolder


def _temp_preview_exists(cache: dict) -> bool:
    """缓存里的 temp 预览文件是否还在(ComfyUI 清理 temp 后就不在了)。"""
    file = str(cache.get("file") or "")
    if not file:
        return False
    path = os.path.join(folder_paths.get_temp_directory(), str(cache.get("subfolder") or ""), file)
    return os.path.isfile(path)


def _ensure_temp_preview(cache: dict) -> bool:
    """确保缓存里有真实存在的 temp 预览: 不在就现场重编码一份(懒编码兜底)。

    为什么需要: temp 目录随时会被 ComfyUI 清理, 而预览 URL 是页面刷新后重建播放器的唯一
    来源 —— 沿用旧文件名直接返回, 就是给节点挂一个「视频加载失败 / Invalid URL」(实测
    /view 返回 404)。重编码成功后把新文件名写回缓存, 前端按新 URL 重新加载。
    """
    if _temp_preview_exists(cache):
        return True
    loaded = cache.get("video")
    if loaded is None and cache.get("path"):
        try:
            loaded = InputImpl.VideoFromFile(cache["path"])
        except Exception as e:
            logging.warning("[FallingTS] 重建预览时打开视频失败: %s", e)
            return False
    if loaded is None:
        return False
    try:
        file, subfolder = _encode_temp_preview(loaded)
    except Exception as e:
        logging.warning("[FallingTS] 重建 temp 预览失败: %s", e)
        return False
    cache["video"] = loaded
    cache["file"], cache["subfolder"] = file, subfolder
    return True


def _source_video_url(path) -> str:
    """源文件本身的 /view URL(temp 预览重建失败时的兜底; 源文件在磁盘上不会消失)。"""
    if not path:
        return ""
    for kind, base in (("output", folder_paths.get_output_directory()), ("input", folder_paths.get_input_directory())):
        try:
            rel = os.path.relpath(str(path), base)
        except ValueError:
            continue
        if rel.startswith(".."):
            continue
        rel = rel.replace("\\", "/")
        subfolder, _, name = rel.rpartition("/")
        return f"/view?filename={quote(name)}&subfolder={quote(subfolder)}&type={kind}"
    return ""


def _preview_url(cache: dict) -> str:
    """取该节点可播放的预览 URL: 优先 temp 预览(必要时现场重建), 退而用源文件。"""
    if _ensure_temp_preview(cache):
        file = str(cache.get("file") or "")
        subfolder = str(cache.get("subfolder") or "")
        return f"/view?filename={quote(file)}&subfolder={quote(subfolder)}&type=temp"
    return _source_video_url(cache.get("path"))


def _build_cache_from_file(nid: str, video_value, name: str = "", sequence: str = "") -> tuple[dict | None, str]:
    """按节点上选中的视频现场拆帧并建缓存(截帧路由的「懒解码」兜底)。

    为什么需要: execute 的帧缓存只在进程内存里 —— 重启 ComfyUI、或用户刚在节点上选好/
    上传视频还没跑过本节点时缓存是空的, 而此时前端播放器已经就绪、播放位置也读得到, 却点
    不了「截帧」(旧行为报「请先运行到该节点」)。这里按请求带来的视频值当场解码一次。

    顺手把视频编码一份到 temp(与 execute 同口径): 页面刷新后 `restoreVideo` 能重建播放器,
    「完成」时的 partial 提交也能直接命中 execute 的缓存快速路径(不必再解码一遍)。

    返回 (缓存, 错误信息); 成功时错误信息为空串。
    """
    path = _resolve_video_path(video_value)
    if not path:
        return None, f"找不到视频文件 {video_value!r}"
    try:
        loaded = InputImpl.VideoFromFile(path)
    except Exception as e:
        return None, f"打开视频失败: {e}"
    parts = _decode_frames(loaded)
    if parts["images"] is None:
        return None, "视频拆帧失败(帧集合为空)"

    try:
        sequence_value = int(str(sequence).strip() or 0)
    except ValueError:
        sequence_value = 0

    # 顺手编码一份预览到 temp(与 execute 同口径): ① 页面刷新后 restoreVideo 能重建播放器;
    # ② 「完成」时 partial 提交可直接命中 execute 的缓存快速路径, 不必再解码一遍。
    # 编码失败不影响截帧(只是没有预览), 故单独兜底。
    try:
        file, subfolder = _encode_temp_preview(loaded)
    except Exception as e:
        logging.warning("[FallingTS] 懒解码时编码预览失败(不影响截帧): %s", e)
        file, subfolder = "", ""

    cache = {
        "video": loaded,
        "name": name,
        "sequence": max(0, sequence_value),
        "path": path,
        "file": file,
        "subfolder": subfolder,
        "images": parts["images"],
        "audio": parts["audio"],
        "fps": parts["fps"],
        "selected_frames": [],
    }
    _last_output[nid] = cache
    return cache, ""


# ─── 节点 ──────────────────────────────────────────────────────────────────


class FallingTSLoadVideoNode(IO.ComfyNode):
    """加载视频 (来自输出 + 截帧): 内置 LoadVideo 的超集。"""

    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: node_id/display_name/category/description, 输入 name + sequence + video +
            video_in(可选), 输出 video + audio + prefix(序列号_名称) + image_1..image_MAX_FRAMES,
            hidden 含 prompt+extra_pnginfo+unique_id,
            标记 is_output_node=True(有 UI 预览, 且是截帧后 partial 提交的锚点)。
        """
        files = _list_relative(folder_paths.get_output_directory())
        outputs = [
            IO.Video.Output("video", tooltip="加载的视频(原样透传, 供下游拆解/编辑)。"),
            IO.Audio.Output("audio", tooltip="视频的音轨(拆音用; 不受「完成」门控)。"),
            # 端口名保持 ASCII(前端 load_video.js 给它挂中文 label「文件名前缀」); 不设 display_name,
            # 否则 object_info 的 output_name 与前端端口名都会变成中文, 与「加载音频」的同一端口不一致
            IO.String.Output(
                "prefix",
                tooltip="「序列号_名称」: 接各预览保存节点的 filename_prefix(不受「完成」门控)。",
            ),
        ]
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
                "capture frames from it and output them downstream. "
                "「序列号」+「名称」组成 prefix 文件名前缀(自动取目录里最大编号 + 1, 可改, 右侧刷新按钮重算)。"
            ),
            inputs=[
                IO.String.Input(
                    "name",
                    default="",
                    multiline=False,
                    tooltip="文件名前缀的名称部分: prefix = <序列号>_<名称>, 接预览保存节点的 filename_prefix",
                ),
                # 字符串而非 INT: 编号按 5 位书写(00000), 前端补零显示, 保存时按整数解析
                IO.String.Input(
                    "sequence",
                    default="",
                    multiline=False,
                    tooltip="文件名前缀的编号: 自动取产物目录里已有编号的最大值 + 1(目录为空时为 00000), 可手动改",
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
                # 下拉是 COMBO, 前端不允许把 VIDEO/STRING 连进 COMBO(实测 isValidConnection 为假),
                # 故另开一个 VIDEO 口给「数据表原视频列」这类外部来源
                IO.Video.Input(
                    "video_in",
                    optional=True,
                    tooltip="可选: 外部传入的视频(如数据表「原视频」列); 连上就用它, 不连则用上面的下拉",
                ),
            ],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo, IO.Hidden.unique_id],
            is_output_node=True,
            outputs=outputs,
        )

    @classmethod
    def execute(cls, video=None, video_in=None, name: str = "", sequence: str = "") -> IO.NodeOutput:
        """节点执行入口: 加载视频 → 编码 temp 供预览 → 拆帧缓存 → 按「完成」输出选中帧。

        逻辑:
        - 已「完成」且已有帧缓存: 直接取缓存输出(partial 提交时本节点会再次执行, 走这条
          路径不重新解码视频), 不重新编码 temp;
        - 未「完成」: 解码视频并编码到 temp 预览, 拆帧缓存, 音轨照常输出, 但视频与选中帧
          输出 ExecutionBlocker(None) 阻断下游(合成/保存都不跑, "到本节点就停下, 等截帧"),
          UI.PreviewVideo 照常发出 —— 拆音不需要截帧, 故音频不受「完成」门控;
        - 「完成」: 输出视频 + 音轨 + 前缀 + 选中帧 image_1..image_MAX_FRAMES(未选中槽 None)。

        无论走哪条路径都输出 `prefix` =「序列号_名称」: 它只是文件名, 与截帧无关 —— 拆音链
        (加载视频 → 音频截段 → 预览音频) 在未点「完成」时也要能拿到前缀落盘。

        参数:
            video (str | None): 视频文件名(相对 output, 形如 0035_场景截帧/00001_陈落.mp4)。
            video_in (Video | None): 外部传入的视频(数据表「原视频」列等), 有值时优先于 video。
            name (str, 默认 ""): 「名称」: 文件名前缀的名称部分。
            sequence (str, 默认 ""): 「序列号」(5 位文本, 如 "00005"), 与 name 一起组成 prefix。

        返回:
            IO.NodeOutput: 视频 + 音轨 + 前缀 + 64 个选中帧槽(未选中/未完成时按上述语义填)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        # V3 节点的 hidden 不进 execute 实参(execution.py 的 get_finalized_class_inputs 单独摘出),
        # prompt 只能经 cls.hidden 取(hidden 不进 execute 实参), 缓存下来备用。
        prompt = getattr(cls.hidden, "prompt", None)
        # 「序列号_名称」文件名前缀(独立于视频, 任何分支都照常输出)
        prefix = sequence_prefix(sequence, name)

        cached = _last_output.get(nid_str)
        # temp 预览可能已被 ComfyUI 清理: 先现场补编码, 否则 UI.PreviewVideo 指向死文件,
        # 补不出来就落到下面的完整路径重新解码
        if nid_str in _done and cached and _ensure_temp_preview(cached):
            return IO.NodeOutput(
                cached.get("video"),
                cached.get("audio"),
                prefix,
                *_frames_from_cache(cached, cached.get("selected_frames") or []),
                ui=UI.PreviewVideo([UI.SavedResult(cached["file"], cached.get("subfolder") or "", IO.FolderType.temp)]),
            )

        if video_in is None and not video:
            raise ValueError("FallingTS 加载视频: 没有选择视频(下拉), 也没有连接 video_in")

        if video_in is not None:
            loaded = video_in
            source = video_in.get_stream_source()
            video_path = source if isinstance(source, str) else ""
        else:
            video_path = folder_paths.get_annotated_filepath(
                video, default_dir=folder_paths.get_output_directory()
            )
            loaded = InputImpl.VideoFromFile(video_path)

        file, subfolder = _encode_temp_preview(loaded)

        # 拆出帧集合缓存(截帧数据源): images = [N,H,W,C] 张量
        parts = _decode_frames(loaded)
        images, audio, fps = parts["images"], parts["audio"], parts["fps"]

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
            "audio": audio,
            "fps": fps,
            "selected_frames": selected_frames,
        }

        ui = UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)])
        if nid_str not in _done:
            # 未「完成」: 视频与选中帧阻断下游, 音轨与前缀照常输出(拆音不需要截帧), 预览照发
            return IO.NodeOutput(
                ExecutionBlocker(None),
                audio,
                prefix,
                *([ExecutionBlocker(None)] * MAX_FRAMES),
                ui=ui,
            )
        return IO.NodeOutput(
            loaded,
            audio,
            prefix,
            *_frames_from_cache(_last_output[nid_str], selected_frames),
            ui=ui,
        )

    @classmethod
    def fingerprint_inputs(cls, video=None, video_in=None, **kwargs):
        """缓存失效签名: 文件名 + 文件 mtime + 选中帧 + 是否完成 + 重置代际。

        截帧/删帧/完成都改变缓存里的 selected_frames/_done, 「重置」递增 _reset_generation;
        指纹随之变化 → 本节点在重提交时必然重新执行(否则会被 ComfyUI 全局执行缓存跳过,
        下游拿到旧的选中帧)。文件本身用 mtime 而不是内容哈希 —— 视频文件可能很大。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        cached = _last_output.get(nid_str) or {}

        stamp = video
        if video_in is not None:
            source = video_in.get_stream_source()
            stamp = (str(source), os.path.getmtime(source) if isinstance(source, str) else None)
        else:
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
    def validate_inputs(cls, video=None, video_in=None, input_types=None, **kwargs) -> bool | str:
        """文件不存在时给出明确提示(内置 LoadVideo 同口径; 值默认按 output 解析)。

        ⚠️ 校验阶段**连线的输入拿不到值**(execution.py 的 get_input_data 在 execution_list
        为空时把 linked 输入标成 missing), 所以「视频是从 video_in 连进来的」不能靠
        video_in is None 判断 —— 否则 0050/0051 这种"下拉为空 + video_in 接线"的图会在
        提交时被误判成「Invalid video file: 」而整次被拦掉。判定见 input_types 形参
        (ComfyUI 会把各连线输入的上游类型传进来)。
        """
        if "video_in" in (input_types or {}) or video_in is not None:
            return True
        if not video:
            return "请选择视频文件(下拉)或把视频连到 video_in"
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
    """按前端播放时间/帧号从缓存帧集合取该帧, 编码 PNG 返回并追加到选中帧列表。

    缓存缺失时先按请求带来的视频值现场拆帧(懒解码)再取帧 —— 不必先运行到本节点:
    用户刚选好/上传视频、或 ComfyUI 重启后缓存为空时, 前端播放器仍在播放, 截帧应照常可用。
    """
    nid = request.match_info["node_id"].strip()
    try:
        data = await request.json()
    except Exception:
        data = {}

    cache = _last_output.get(nid)
    if not cache or cache.get("images") is None:
        cache, err = _build_cache_from_file(
            nid, data.get("video"), str(data.get("name") or ""), str(data.get("sequence") or "")
        )
        if cache is None:
            return web.json_response(
                {
                    "status": "error",
                    "message": f"没有可截帧的视频数据({err}); 请在节点里选择或上传视频",
                },
                status=400,
            )
    images = cache["images"]
    total = len(images)

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
    """返回该节点当前缓存视频的可播放 URL, 供前端在刷新后重建预览。

    temp 预览被清理时现场重编码(懒编码兜底), 再不行退回源文件本身的 URL —— 绝不能把
    已被清理的 temp 文件名直接返给前端: 前端把播放器指过去就是 404, 节点上显示
    「视频加载失败 / Invalid URL」(实测复现)。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache:
        return web.json_response({"status": "error", "message": "没有可预览的视频, 请先运行到该节点"}, status=400)
    url = _preview_url(cache)
    if not url:
        return web.json_response({"status": "error", "message": "视频预览已失效, 请重新运行到该节点"}, status=400)
    return web.json_response({"status": "ok", "url": url})


PromptServer.instance.routes.post("/fallingts_load_video/frame/{node_id}")(_handle_frame)
PromptServer.instance.routes.post("/fallingts_load_video/frame-remove/{node_id}")(_handle_frame_remove)
PromptServer.instance.routes.post("/fallingts_load_video/done/{node_id}")(_handle_done)
PromptServer.instance.routes.post("/fallingts_load_video/reset")(_handle_reset)
PromptServer.instance.routes.get("/fallingts_load_video/state/{node_id}")(_handle_state)
PromptServer.instance.routes.get("/fallingts_load_video/preview-url/{node_id}")(_handle_preview_url)
