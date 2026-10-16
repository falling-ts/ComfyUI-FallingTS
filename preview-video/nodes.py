# PreviewVideo 节点: 预览视频 + 点「保存」才写入 output 目录 + 截帧输出选中帧 IMAGE。
# 参照 PreviewImageSave(preview-image/nodes.py) 的「始终预览(temp)+ 保存按钮写 output」模式。
# 原理: VIDEO 是惰性内存对象, 核心 WebSocket 协议只有图片预览事件;
#       本节点把 VIDEO 编码成 mp4 写到【临时目录】(temp, 非 output),
#       再通过 UI.PreviewVideo 让前端播放临时文件 —— "不满意就不保存"。
#       点「保存」按钮时, 后端用 execute 缓存的视频按 {filename_prefix}{filename_suffix}.mp4
#       直接写 output(同名覆盖, 不带 _序号 后缀), 不重跑工作流。
#       filename_suffix 默认空串, 可手动输入或上游连线, 保存时拼接在前缀之后。
#
# 截帧(2026-10-16 自「加载视频」节点同套机制回迁):
#       收到视频即用 get_components() 拆出内部帧集合 images 缓存到本节点;
#       前端点「截帧」把当前播放时间 POST 到 /preview-video/frame/{id},
#       后端按 fps 折算帧号从缓存 images 取该帧转 PNG 返回, 前端累积渲染选中帧列表;
#       点「完成」后 execute 按选中帧号输出 image_1..image_MAX_FRAMES (IMAGE),
#       未选中的槽为 None(与 mdtable/composite 同套模式: 后端定长槽 + 前端按「输出帧数」增删端口)。
#
#       ⚠️ 与「加载视频」的区别: 本节点的视频是**输入**(上游 CreateVideo 连线), 不是下拉,
#       所以不存在"按节点上的视频值现场拆帧"那条懒解码兜底 —— 帧集合只在 execute 时拿得到,
#       截帧前必须先运行到本节点(否则报「请先运行到该节点」)。其余机制(选中帧列表、
#       完成门控、state 复原、动态端口)与加载视频完全一致。
#
# 「完成」= 继续节点语义(V3 lazy + partial execution):
#       - video 输入声明 lazy: 构建执行列表时不沿这条边向上游遍历, 是否拉上游由 check_lazy_status 决定
#         (未完成 -> 返回 ["video"] 拉上游生成视频填缓存; 已完成且有选中帧 -> 返回 [] 不拉, 用缓存);
#       - 未完成: execute 用 ExecutionBlocker(None) 阻断下游但 ui 预览照发 —— 上游全部执行、到此断开,
#         本节点之后的合成/保存节点不执行("到预览就停", 等用户截帧);
#       - 点「完成」(无选中帧): 前端调 /preview-video/reset 清 done 再全量提交 = 预加载上游;
#       - 点「完成」(有选中帧): 前端调 /preview-video/done 置 done, 再以 partial_execution_targets
#         只提交本节点之后的下游输出节点 —— 上游因 lazy 边不进子图, 运行时看不到本节点前面的节点。

from __future__ import annotations

import io as _io
import logging
import os
import random
import string
from urllib.parse import quote

import numpy as np
from PIL import Image
from aiohttp import web
from server import PromptServer

from comfy_api.latest import IO, Types, UI
from comfy_execution.graph_utils import ExecutionBlocker
import folder_paths

from output_subdir import resolve_subdir, safe_dir_name

_NODE_NAME = "PreviewVideo"

# 截帧输出上限(与 composite 的 MAX_TOTAL=64 一致; 后端声明定长槽, 前端按需增删端口)
MAX_FRAMES = 64

# 固定端口数: video(0) + audio(1) + prefix(2), 选中帧自端口 3 起(与「加载视频」同布局)
_FIXED_OUTPUTS = 3

# 哨兵: 区分"该输入根本没连线"(MISSING)与"连了线但上游未求值"(None)。
# check_lazy_status 里只有真正连了线才能去拉上游 —— 若对不存在的输入调用
# make_input_strong_link 会抛 NodeInputError (comfy_execution/graph.py:122)。
MISSING = object()

# 最近一次预览的视频缓存: 缓存键 -> {"video", "filename_prefix", "images", "fps", "selected_frames", ...}
# 点「保存」/「截帧」时前端把数据 POST 过来, 后端直接用缓存处理(无需重跑工作流)
# 缓存键 = "<工作流根 id>::<节点 id>"(见 _scoped_key), 只按节点 id 会跨工作流串片
_last_output: dict[str, dict] = {}

# 已「完成」截帧的节点(缓存键集合): 完成前下游被阻断, 完成后输出选中帧
# 前端点「完成」按钮置入本集合使 execute 输出选中帧; 点「完成」(无选中帧) / 默认 Run 时
# 经 /preview-video/reset 清空 -> 重新拉上游生成。
_done: set[str] = set()

# 重置代际: /preview-video/reset 时递增, 纳入 fingerprint_inputs -> 每次 Run 后指纹必变,
# 强制本节点重新执行(不被 ComfyUI 全局执行缓存跳过, 否则预览停在旧 temp 文件上)。
_reset_generation: int = 0


def _workflow_scope(extra_pnginfo) -> str:
    """从 extra_pnginfo 取当前工作流的根 id, 作为缓存键的工作流作用域。

    与 preview-image 同口径: 该 id 就是工作流 JSON 的根 id(前端 graph.serialize().id;
    graphToPrompt() 把 graph.serialize() 整个塞进 extra_pnginfo.workflow, 所以这里取到的
    和前端 app.rootGraph.id 是同一个值)。

    **为什么必须带工作流作用域**: 只按节点 id 缓存会跨工作流串片 —— 节点 id 在各工作流之间
    大量重复, 打开工作流 B 时会把之前跑过的 A 的同 id 节点预览当成 B 的预览播放出来。

    参数:
        extra_pnginfo (dict|None): hidden 里的额外元数据。

    返回:
        str: 工作流根 id; 取不到(如无头 API 直接提交)时返回空串。
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
        cache (dict): 缓存字典(本模块即 _last_output)。
        node_id (str|int|None): 节点唯一 ID。
        workflow_id (str|None): 调用方声明的当前工作流根 id。

    返回:
        dict|None: 命中的缓存; 未命中返回 None。
    """
    keys = [str(node_id or "")]
    if workflow_id:
        keys.insert(0, _scoped_key(node_id, workflow_id))
    for key in keys:
        if key in cache:
            return cache[key]
    return None


def _resolve_cache_key(node_id, workflow_id=None) -> str:
    """定位该节点的缓存键 —— 给**取不到 extra_pnginfo 的调用路径**用。

    execute 从 hidden 拿得到 extra_pnginfo, 写的键带工作流作用域("<工作流 id>::<节点 id>");
    但 fingerprint_inputs / check_lazy_status 是引擎在执行前后各调一次的钩子, 那里拿不到
    hidden(实测 extra_pnginfo 为空)⇒ 只能算出纯节点 id 的键, 与 execute 写的键对不上。

    **不兜这一下的后果(实测)**: 指纹恒等于初值 ⇒ 本节点被 ComfyUI 全局执行缓存命中,
    点「完成」后 partial 提交拿回的仍是上一轮那个「全阻断」结果, 下游一个都不跑;
    check_lazy_status 也会误判成未完成, 把已经不必重跑的整条上游重新拉起来。

    所以这里在拿不到工作流 id 时, 按节点 id **反查**已有缓存里的带作用域键; 查不到就退回纯键。

    参数:
        node_id (str|int|None): 节点唯一 ID。
        workflow_id (str|None): 调用方拿到的当前工作流根 id; 拿不到时传空。

    返回:
        str: 该节点应使用的缓存键(可能与传入的工作流 id 无关, 见上文)。
    """
    nid = str(node_id or "")
    if not nid:
        return ""
    if workflow_id:
        return _scoped_key(nid, workflow_id)
    # 无工作流 id: 先看纯键在不在, 再扫带作用域的键(取第一个匹配的节点)
    if nid in _last_output:
        return nid
    suffix = "::" + nid
    for existing in _last_output:
        if existing.endswith(suffix):
            return existing
    return nid


def _safe_dir_name(name) -> str:
    """把工作流名清洗成可安全用作单层目录名的字符串(实现见 output_subdir.safe_dir_name)。"""
    return safe_dir_name(name)


def _workflow_output_dir(workflow_name, prompt=None) -> str:
    """取保存目录: output 下按子目录名建目录, 不存在则创建; 名字非法时退回 output 根。

    子目录名由 output_subdir.resolve_subdir 解析 —— 工作流里有 md 数据表节点时用它的
    表文件名, 没有 md 表节点才用工作流名(理由见该模块头部说明)。
    """
    base = folder_paths.get_output_directory()
    sub = resolve_subdir(workflow_name, prompt)
    if not sub:
        return base
    target = os.path.join(base, sub)
    os.makedirs(target, exist_ok=True)
    return target


# ─── 帧工具(与「加载视频」同实现) ────────────────────────────────────────────


def _frames_from_cache(cached: dict, selected: list) -> list:
    """按选中帧号列表从缓存的帧集合取图(1-based → 张量索引), 未选中槽 None。

    返回的单帧形状为 [1, H, W, C](带 batch 维, IMAGE 张量约定), 供下游直接预览/合成。

    参数:
        cached (dict): 缓存(含 images 张量)。
        selected (list): 选中帧号(1-based)。

    返回:
        list: 长度 MAX_FRAMES, 前 len(selected) 个为对应帧张量([1,H,W,C]), 其余 None;
        缓存的 images 缺失/越界时对应槽 None。
    """
    images = cached.get("images")
    total = len(images) if images is not None else 0
    out: list = [None] * MAX_FRAMES
    for i, fno in enumerate(selected[:MAX_FRAMES]):
        idx = fno - 1
        if images is not None and 0 <= idx < total:
            frame = images[idx]
            # images 为 [N,H,W,C] 批次: 取单帧 [H,W,C] 后补 batch 维 -> [1,H,W,C]
            out[i] = frame.unsqueeze(0) if frame.dim() == 3 else frame[:1]
    return out


def _png_bytes(frame) -> bytes:
    """把单帧张量编码为 PNG 字节(低压缩)。兼容 [H,W,C] 与 [1,H,W,C]。

    参数:
        frame: 单帧 [H,W,C] 或 [1,H,W,C] 张量。

    返回:
        bytes: PNG 编码字节。
    """
    if frame is None:
        raise ValueError("帧为空")
    if frame.dim() == 4:
        frame = frame[0]
    arr = (frame.float().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
    buf = _io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


def _decode_frames(video) -> dict:
    """拆出视频的帧集合/音轨/帧率, 失败只记日志并三项置空(不抛)。

    核心 get_components() 一次性解出帧与音轨: 拆不出帧时音轨同样没有, 故这里三项一起兜底;
    拆帧失败不该中断整条工作流(预览与保存仍要可用), 所以异常在此吞掉、返回空帧集合。

    参数:
        video: 视频对象(惰性内存对象)。

    返回:
        dict: {"images", "audio", "fps"}; 拆不出时为 {None, None, 0.0}。
    """
    try:
        components = video.get_components()
        return {
            "images": components.images,
            "audio": components.audio,
            "fps": float(components.frame_rate) if components.frame_rate else 0.0,
        }
    except Exception as e:  # noqa: BLE001 - 拆帧失败只告警, 不让预览/保存整条链挂掉
        logging.warning("[FallingTS] PreviewVideo 视频截帧失败: %s", e)
        return {"images": None, "audio": None, "fps": 0.0}


def _encode_temp_preview(video):
    """把视频编码成一份 temp 预览 mp4, 返回 (文件名, 子目录)。

    口径与 execute 完全一致(随机前缀 + 5 位计数 + mp4), 供「temp 被清理后现场重建」复用,
    使重建出来的文件名与首次预览同形, 前端无需区分。

    参数:
        video: 视频对象(惰性内存对象)。

    返回:
        tuple[str, str]: (文件名, 子目录)。
    """
    width, height = video.get_dimensions()
    prefix = "ComfyUI_temp_" + "".join(random.choice(string.ascii_lowercase) for _ in range(5))
    full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
        prefix,
        folder_paths.get_temp_directory(),
        width,
        height,
    )
    ext = Types.VideoContainer.get_extension("mp4")
    file = f"{filename}_{counter:05}_.{ext}"
    video.save_to(
        os.path.join(full_output_folder, file),
        format=Types.VideoContainer.MP4,
        codec=Types.VideoCodec.AUTO,
    )
    return file, subfolder


def _temp_preview_exists(cache: dict) -> bool:
    """校验缓存里那份 temp 预览文件是否还在磁盘上。

    temp 目录随时会被 ComfyUI 清理, 文件不在时绝不能把它的文件名返给前端 —— 前端播放器
    指过去就是 404, 实测表现是节点上「视频加载失败 / Invalid URL」。

    参数:
        cache (dict): 预览缓存(含 file / subfolder)。

    返回:
        bool: 文件存在为 True。
    """
    file = cache.get("file")
    if not file:
        return False
    path = os.path.join(folder_paths.get_temp_directory(), cache.get("subfolder") or "", file)
    return os.path.isfile(path)


def _ensure_temp_preview(cache: dict):
    """保证缓存里有一份**真实存在**的 temp 预览文件, 没有就现场重编码一份。

    与 load-video 的 _ensure_temp_preview 同口径: temp 被清理时用缓存的视频对象重编码,
    并把新文件名写回缓存; 编不出来(视频对象已失效)返回 None, 由调用方决定兜底。

    参数:
        cache (dict): 预览缓存(含 video / file / subfolder)。

    返回:
        tuple[str, str]|None: (文件名, 子目录); 无法提供时返回 None。
    """
    if _temp_preview_exists(cache):
        return cache.get("file"), cache.get("subfolder") or ""
    video = cache.get("video")
    if video is None:
        return None
    try:
        encoded = _encode_temp_preview(video)
    except Exception:  # noqa: BLE001 - 重编码失败只告警, 不让整次请求 500
        logging.exception("[FallingTS] 重建视频 temp 预览失败")
        return None
    if not encoded:
        return None
    cache["file"], cache["subfolder"] = encoded
    return encoded


def _temp_url(file: str, subfolder: str = "") -> str:
    """拼 temp 文件的 /view URL。

    参数:
        file (str): 文件名。
        subfolder (str): 子目录(可空)。

    返回:
        str: 可播放的 /view URL。
    """
    return f"/view?filename={quote(file)}&subfolder={quote(subfolder)}&type=temp"


class PreviewVideoNode(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        输出布局与「加载视频」保持一致: video(0) / audio(1) / prefix(2) / image_1..image_MAX_FRAMES(3 起)
        —— 0035_场景截帧 那条后续链(单图保存 + 合成)因此可以原样接到本节点之后(见
        dev/build-scene-workflows.py 的 append 逻辑)。

        返回:
            IO.Schema: 节点元数据, 含 node_id/display_name/category/description,
            输入 video(lazy) + filename_prefix + filename_suffix, 输出 video/audio/prefix/选中帧,
            hidden 含 prompt+extra_pnginfo+unique_id, 标记 is_output_node=True。
        """
        outputs = [
            IO.Video.Output("video", tooltip="预览/保存的视频(原样透传)。"),
            IO.Audio.Output("audio", tooltip="视频的音轨(拆音用; 不受「完成」门控)。"),
            IO.String.Output(
                "prefix",
                tooltip="「文件名前缀」: 即 filename_prefix 的值, 接各预览保存节点的 filename_prefix。",
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
            display_name="Preview Video (保存+截帧)",
            category="FallingTS",
            description=(
                "Preview the video without saving it to the ComfyUI output directory; "
                "click 保存 to write it to output as {filename_prefix}{filename_suffix}.mp4 (no sequence suffix). "
                "Frame capture: 截帧 button reads the playing position, appends selected frames "
                "to image_1..image_N outputs (up to 64). Encodes to the temp folder for preview."
            ),
            inputs=[
                # video 输入 lazy: 构建执行列表时不沿这条边向上游遍历
                # (add_node 对 lazy 输入跳过), 是否拉取上游由 check_lazy_status 决定:
                # 未「完成」 -> 拉上游生成/缓存视频; 已「完成」(有选中帧) -> 不拉,
                # execute 用最近一次缓存的视频/帧输出 —— 这是"点完成只跑下游、运行时
                # 看不到预览节点前面的所有节点"的关键(lazy 门控 + partial execution targets)。
                IO.Video.Input(
                    "video",
                    tooltip="要预览的视频 (None = 无值, 如扇出未选中分支, 跳过预览, 输出该节点最近一次预览的视频供下游)。",
                    lazy=True,
                ),
                IO.String.Input(
                    "filename_prefix",
                    default="video",
                    multiline=False,
                    tooltip="保存到 output 的文件名(不含扩展名); 同名直接覆盖, 无序号; 同时经 prefix 输出透传给下游保存节点",
                ),
                IO.String.Input(
                    "filename_suffix",
                    default="",
                    multiline=False,
                    tooltip="文件名后缀(不含扩展名, 默认空); 保存时拼接在 filename_prefix 之后: {filename_prefix}{filename_suffix}.mp4",
                ),
            ],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo, IO.Hidden.unique_id],
            is_output_node=True,
            outputs=outputs,
        )

    @classmethod
    def execute(
        cls,
        video,
        filename_prefix: str = "video",
        filename_suffix: str = "",
    ) -> IO.NodeOutput:
        """节点执行入口: 编码 temp 预览 + 拆帧缓存, 按「完成」输出选中帧。

        逻辑:
        - video 为 None (lazy 未拉上游 / 扇出未选中分支): 回放上次预览;
          已有缓存且已完成 -> 输出缓存的视频+音轨+选中帧(partial 只跑下游);
          否则按未完成语义阻断下游;
        - 否则: 编码 temp 预览 + get_components() 拆帧缓存;
          未「完成」: 输出 3+MAX_FRAMES 个 ExecutionBlocker(None) 阻断下游节点不执行
          (合成/保存都不跑, "到预览节点就停止断掉"), 但 UI.PreviewVideo 预览事件照常发出
          —— 视频正常预览供播放/截帧;
          已「完成」: 输出视频 + 音轨 + 前缀 + 选中帧 image_1..image_MAX_FRAMES(未选中槽 None)。

        参数:
            video (Video|None): 要预览的视频对象(惰性内存对象)。
            filename_prefix (str, 默认 "video"): 保存文件名前缀(控件; 被上游连线时本参数为实际接收值)。
            filename_suffix (str, 默认 ""): 文件名后缀(控件, 保存时拼接在前缀之后)。

        返回:
            IO.NodeOutput: 视频/音轨/前缀/选中帧 + UI.PreviewVideo 预览事件(temp 文件)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        # 工作流 prompt / extra_pnginfo 只能从 hidden 取 —— V3 节点的 hidden 不进 execute 实参。
        prompt = getattr(cls.hidden, "prompt", None)
        # 工作流根 id: 给预览/截帧缓存加作用域, 只按节点 id 缓存会跨工作流串片。
        # ⚠️ 拿不到工作流 id 时要反查已有键(见 _resolve_cache_key): execute 与
        # fingerprint_inputs / check_lazy_status 必须落在同一个键上, 否则指纹查空、
        # 本节点被全局执行缓存命中, 点「完成」后下游一个都不跑。
        wid = _workflow_scope(getattr(cls.hidden, "extra_pnginfo", None))
        key = _resolve_cache_key(nid_str, wid)
        prefix = str(filename_prefix)
        blocked = [ExecutionBlocker(None)] * (_FIXED_OUTPUTS + MAX_FRAMES)

        if video is None:
            # 无值: lazy 未拉上游 / 扇出未选中分支 -> 回放上次预览。
            cached = _last_output.get(key)
            if not cached or not cached.get("video"):
                return IO.NodeOutput(*blocked)
            # 回放同样要保证 temp 文件真的还在: 不在就现场重编码一份; 编不出则不发预览事件,
            # 输出照旧(下游拿到的是缓存的视频/帧, 不依赖这份 temp)
            got = _ensure_temp_preview(cached)
            frames = _frames_from_cache(cached, cached.get("selected_frames") or [])
            if key not in _done:
                # 未完成: 预览仍发出, 但输出全部 block(下游节点不执行)
                if got:
                    return IO.NodeOutput(
                        *blocked,
                        ui=UI.PreviewVideo([UI.SavedResult(got[0], got[1], IO.FolderType.temp)]),
                    )
                return IO.NodeOutput(*blocked)
            if got:
                return IO.NodeOutput(
                    cached.get("video"),
                    cached.get("audio"),
                    prefix,
                    *frames,
                    ui=UI.PreviewVideo([UI.SavedResult(got[0], got[1], IO.FolderType.temp)]),
                )
            return IO.NodeOutput(cached.get("video"), cached.get("audio"), prefix, *frames)

        # 有值: 编码 temp 预览。编码失败不中断工作流 —— 拆帧缓存、「保存」都只用 video 对象,
        # 与 temp 文件无关, 故只告警、把 file/subfolder 留空(前端拿不到预览但流程照走)。
        try:
            file, subfolder = _encode_temp_preview(video)
        except Exception:  # noqa: BLE001 - 编码失败不中断工作流
            logging.exception("[FallingTS] PreviewVideo 编码 temp 预览失败, 本次不刷新预览")
            file, subfolder = None, ""

        # 拆出帧集合缓存(截帧数据源): images = [N,H,W,C] 张量, 同时拿到音轨与帧率
        parts = _decode_frames(video)

        # 保留既有选中帧号(前端经路由维护, 跨次执行不丢); 首次则空列表
        cached = _last_output.get(key) or {}
        selected_frames = cached.get("selected_frames") or []

        if key:
            _last_output[key] = {
                "video": video,
                "filename_prefix": filename_prefix,
                "filename_suffix": filename_suffix,
                "prompt": prompt,
                "file": file,
                "subfolder": subfolder,
                "images": parts["images"],
                "audio": parts["audio"],
                "fps": parts["fps"],
                "selected_frames": selected_frames,
            }

        # 只有真正编出了 temp 文件才发预览事件(编不出时发个空文件名, 前端会挂一个 404 播放器)
        ui = (
            UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)])
            if file
            else None
        )
        if key not in _done:
            # 未「完成」(继续语义): 阻断下游(合成/保存都不跑, "到预览节点就停止断掉"),
            # 但 UI.PreviewVideo 预览事件仍照常发出, 视频照常供播放/截帧。
            # 首次 Run 即此态: 上游全部执行, 到此断开。
            return IO.NodeOutput(*blocked, ui=ui) if ui else IO.NodeOutput(*blocked)
        if ui:
            return IO.NodeOutput(
                video,
                parts["audio"],
                prefix,
                *_frames_from_cache(_last_output[key], selected_frames),
                ui=ui,
            )
        return IO.NodeOutput(
            video,
            parts["audio"],
            prefix,
            *_frames_from_cache(_last_output[key], selected_frames),
        )

    @classmethod
    def check_lazy_status(cls, video=MISSING, filename_prefix: str = "video", **kwargs) -> list:  # noqa: A002
        """lazy 输入门控: 决定本次执行要不要拉取上游的 video —— "完成只跑下游"的关键。

        机制(ComfyUI 执行引擎, 与继续节点同套):
        1. 构建执行列表时, lazy 输入不会让 add_node 向上游遍历 —— 上游不因这条边被加入执行;
        2. 节点真正执行前, 引擎调本方法, 返回"缺失且需要拉取的输入名";
        3. 返回的输入名若在 missing_keys(连了线但未求值)里, 引擎才 make_input_strong_link 拉上游
           并返回 PENDING, 上游执行完重新调度本节点; 返回空则直接用 get_input_data 给的值。

        完成语义:
        - 已「完成」且已有选中帧: 上游不应重跑, 数据来自节点缓存 -> 返回 [] 不拉;
        - 未完成(首次 Run / reset 后 / 刚截完帧未点完成): 上游必须执行以产生视频 -> 返回 ["video"];
        - 没连线: 根本没有上游可拉, 返回 [] —— 避免对不存在的输入 make_input_strong_link 抛 NodeInputError。

        参数:
            video (Any, 默认 MISSING): 上游视频, 由引擎按输入名注入:
                - MISSING: 该输入没连线(不在 prompt 的 inputs 里, kwargs 无此键 -> 走默认值);
                - None: 连了线但上游未求值(lazy 输入未被拉取, 已完成时即此处);
                - 其他: 已求值的上游视频(此时已不在 missing_keys, 本方法的返回值会被过滤)。
            filename_prefix (str, 默认 "video"): 文件名前缀(本方法不读取, 仅保持签名兼容)。
            **kwargs: 吸收 hidden 与其余输入(本方法不读取)。

        返回:
            list: 本次需要拉取的上游输入名列表, 只能是 ["video"] 或 []。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        if video is MISSING:
            return []  # 没连线: 无上游可拉
        # ⚠️ 本钩子拿不到 extra_pnginfo(引擎调它时不传 extra_data) ⇒ 键要靠反查定位,
        # 否则 _done 里存的带作用域键查不到, 会把未完成误判成完成(或反之)
        key = _resolve_cache_key(nid_str, _workflow_scope(getattr(cls.hidden, "extra_pnginfo", None)))
        cached = _last_output.get(key) or {}
        if key in _done and (cached.get("selected_frames") or []):
            return []  # 已「完成」且有选中帧: 不拉上游, execute 从缓存取
        return ["video"]  # 未完成: 拉上游, 生成/更新缓存的视频

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        """缓存失效签名: 文件名 + 选中帧 + 是否完成 + 重置代际 + 节点 id。

        /preview-video/reset 递增 _reset_generation, 使每次默认 Run 后本节点必然重新执行
        (重新编码 temp 并发出预览事件), 不被 ComfyUI 全局执行缓存跳过 —— 否则预览会停在
        上一次的 temp 文件上(该文件一旦被清理, 播放就报「视频加载失败」)。
        截帧/删帧/完成都会改变缓存的 selected_frames / _done, 指纹随之变化 -> 本节点在重提交时
        必然重新执行, 使新截帧值与完成状态输出到下游。

        参数:
            **kwargs: 输入参数(不读取具体值), 仅保持签名兼容。

        返回:
            tuple: (重置代际, 节点 id, 选中帧列表元组, 是否完成), 作为缓存指纹。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        # ⚠️ 与 check_lazy_status 同理: 本钩子拿不到 extra_pnginfo, 键必须反查定位 ——
        # 否则指纹恒等于初值, 本节点被全局执行缓存命中, 点「完成」后下游一个都不跑。
        key = _resolve_cache_key(nid_str, _workflow_scope(getattr(cls.hidden, "extra_pnginfo", None)))
        cached = _last_output.get(key) or {}
        return (
            _reset_generation,
            nid_str,
            tuple(cached.get("selected_frames") or ()),
            key in _done,
        )


# ─── 截帧 / 完成 / 重置 / 状态 / 预览 路由 ──────────────────────────────────


def _request_wf_id(request, data=None) -> str:
    """从请求体或 query 取工作流根 id(前端带过来, 用于定位该工作流的缓存)。"""
    if isinstance(data, dict):
        wid = str(data.get("workflow_id") or "").strip()
        if wid:
            return wid
    return str(request.query.get("workflow_id") or "").strip()


async def _read_json(request) -> dict:
    """读请求体 JSON; 非对象/解析失败一律当空 dict(这些路由不因坏 body 报 500)。"""
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


async def _handle_frame(request: web.Request) -> web.Response:
    """HTTP 路由: 按前端播放时间/帧号从缓存帧集合取该帧, 编码 PNG 返回并追加到选中帧列表。

    前端点「截帧」按钮时 POST 当前播放时间(秒)或帧号(1-based), 后端用 execute 时缓存的
    images 张量定位该帧, 转 PNG 返回; 同时把该帧号追加进缓存 selected_frames(去重, 上限
    MAX_FRAMES), 供下一次 execute 输出。前端显示在截帧列表并记录帧号。

    ⚠️ 与「加载视频」不同: 本节点的视频是输入连线而不是下拉值, 缓存为空时**无法**现场拆帧
    (拿不到视频来源), 只能提示先运行到本节点。

    请求体: {"position_seconds": float, "frame_index": int, "mode": "time"|"frame",
             "append": bool, "workflow_id": str}
    - mode=time (默认): position_seconds × fps 折算帧号;
    - mode=frame: frame_index 直接用(1-based);
    - append=true (默认): 追加帧号到缓存 selected_frames; false 仅取帧不追加(复原列表用)。

    返回:
        web.Response:
        - 200: 直接把 PNG 字节返回 (Content-Type: image/png), 附 X-Frame-Index = 帧号(1-based);
        - 400: {"status": "error", "message": ...} 无缓存/帧号越界/帧为空/已满。
    """
    nid = request.match_info["node_id"].strip()
    data = await _read_json(request)
    cache = _cache_get(_last_output, nid, _request_wf_id(request, data))
    if not cache or cache.get("images") is None:
        return web.json_response(
            {"status": "error", "message": "没有可截帧的视频数据, 请先运行到该节点"}, status=400
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
    """HTTP 路由: 从缓存 selected_frames 移除指定帧号(或清空)。

    前端点选中帧列表中的「✕」时调用。

    请求体: {"frame_index": int, "workflow_id": str} 或 {"clear": true}。

    返回:
        web.Response: 200, {"status": "ok", "frames": [剩余帧号]}; 无缓存时 400。
    """
    nid = request.match_info["node_id"].strip()
    data = await _read_json(request)
    cache = _cache_get(_last_output, nid, _request_wf_id(request, data))
    if not cache:
        return web.json_response({"status": "error", "message": "没有缓存数据"}, status=400)

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
    """HTTP 路由: 标记该节点「完成截帧」(置入 _done), 使下一次执行只跑下游。

    前端点红色「完成」按钮时调用(且已至少截了一帧): 完成后 video 输入被 lazy 门控
    跳过拉取(不重跑上游生成), 本节点用缓存的视频+选中帧输出给下游;
    前端随后以 partial_execution_targets 只提交下游输出节点 —— 运行时看不到前面的节点。

    请求体(可选): {"frames": [帧号...], "workflow_id": str} —— 从工作流恢复的帧(前端 DOM
    state, 后端缓存可能为空)时, 用前端帧号列表填充缓存的 selected_frames, 使完成可基于前端帧生效。

    返回:
        web.Response: 200, {"status": "ok", "done": bool}。
    """
    nid = request.match_info["node_id"].strip()
    data = await _read_json(request)
    wid = _request_wf_id(request, data)
    # 键必须与 execute / fingerprint_inputs 用的是同一个: 带 workflow_id 就用作用域键,
    # 没带则反查已有缓存(而不是新起一个纯键 —— 那会让指纹与 execute 又分叉)
    key = _resolve_cache_key(nid, wid)
    cache = _last_output.get(key)
    if cache is None:
        cache = {"selected_frames": [], "video": None}
        _last_output[key] = cache
    if isinstance(data.get("frames"), list):
        try:
            cache["selected_frames"] = [int(f) for f in data["frames"] if f is not None]
        except (TypeError, ValueError):
            cache["selected_frames"] = cache.get("selected_frames") or []
    # 仅当节点已有选中帧才置完成(没帧的"完成"= 预加载上游, 走 reset+全量提交)
    if cache.get("selected_frames"):
        _done.add(key)
    return web.json_response({"status": "ok", "done": key in _done})


async def _handle_reset(request: web.Request) -> web.Response:
    """HTTP 路由: 重置所有 PreviewVideo 为未完成(前端默认 Run / 无帧点「完成」时调用)。

    清空 _done(全部回到阻塞态 = 未完成, 下次执行拉上游重新生成)并递增 _reset_generation
    (强制本节点重新执行, 见 fingerprint_inputs), 使下一次全量提交从开头执行。

    返回:
        web.Response: 200, {"status": "ok"}。
    """
    global _reset_generation
    _done.clear()
    _reset_generation += 1
    return web.json_response({"status": "ok"})


async def _handle_state(request: web.Request) -> web.Response:
    """HTTP 路由: 返回该节点当前的截帧状态, 供前端在页面刷新后重建帧列表。

    query: workflow_id(当前工作流根 id, 用于定位缓存)。

    返回:
        web.Response: 200, {"status", "selected_frames", "done", "total_frames", "has_video"}。
    """
    nid = request.match_info["node_id"].strip()
    wid = _request_wf_id(request)
    # 与 execute / fingerprint_inputs 同一套键解析: 状态查询要看到同一份 done 标记
    key = _resolve_cache_key(nid, wid)
    cache = _last_output.get(key) or {}
    images = cache.get("images")
    return web.json_response(
        {
            "status": "ok",
            "selected_frames": [int(f) for f in (cache.get("selected_frames") or [])],
            "done": key in _done,
            "total_frames": len(images) if images is not None else 0,
            "has_video": cache.get("video") is not None,
        }
    )


async def _handle_clear(request: web.Request) -> web.Response:
    """保留端点但**不清任何状态**(后端是唯一事实来源, 刷新后由前端读回重建)。"""
    return web.json_response({"status": "ok"})


async def _handle_video_url(request: web.Request) -> web.Response:
    """HTTP 路由: 返回该节点当前缓存视频的可播放 URL, 供前端在刷新后重建预览。

    节点原生的 UI.PreviewVideo 是一次性 WebSocket 事件, 页面刷新后不会重发, 视频预览
    就空了。前端因此在节点上备一个 <video>, 页面加载/刷新时调本路由拿 URL 填上。
    """
    nid = request.match_info["node_id"].strip()
    wid = _request_wf_id(request)
    cache = _cache_get(_last_output, nid, wid)
    if not cache or not cache.get("video"):
        return web.json_response({"status": "error", "message": "没有可预览的视频, 请先运行到该节点"}, status=400)
    # temp 目录随时被清理: 文件不在就现场重编码一份, 绝不把已删除的文件名返给前端
    # (实测表现 = 节点上「视频加载失败 / Invalid URL」)
    got = _ensure_temp_preview(cache)
    if not got:
        return web.json_response(
            {"status": "error", "message": "预览文件已被清理且无法重建, 请重新运行到该节点"}, status=400
        )
    file, subfolder = got
    return web.json_response({"status": "ok", "url": _temp_url(file, subfolder)})


async def _handle_save(request: web.Request) -> web.Response:
    """HTTP 路由: 用缓存视频把该节点最近预览的视频写入 output(同名覆盖, 无序号)。

    流程: 前端点「保存」按钮时把文件名前缀+后缀 POST 过来;
    后端查缓存(execute 时缓存的视频), 有则编码写 output, 无则 400。
    全程不触发任何工作流重跑。文件名 = {filename_prefix}{filename_suffix}.mp4, 不带 _0001 序列后缀。
    """
    nid = request.match_info["node_id"].strip()
    data = await _read_json(request)
    # workflow_id 由前端带过来(app.rootGraph.id): 保存必须用**当前工作流**的预览缓存,
    # 只按节点 id 查会把别的工作流同 id 节点的预览存进来(跨工作流串片)
    wid = _request_wf_id(request, data) or None
    cache = _cache_get(_last_output, nid, wid)
    if not cache or not cache.get("video"):
        return web.json_response(
            {"status": "error", "message": "没有预览数据, 请先运行到该节点"}, status=400
        )

    filename_prefix = str(data.get("filename_prefix", "video"))
    # 若 filename_prefix 输入被上游连线, widget 值是占位符: 用 execute 时实际接收到的值
    if data.get("filename_prefix_linked") and cache.get("filename_prefix"):
        filename_prefix = str(cache["filename_prefix"])
    # 后缀同前缀: 连线时用 execute 实际接收值; 空串 = 不拼后缀
    filename_suffix = str(data.get("filename_suffix") or "")
    if data.get("filename_suffix_linked") and cache.get("filename_suffix") is not None:
        filename_suffix = str(cache["filename_suffix"])
    name = filename_prefix + filename_suffix

    video = cache["video"]
    output_dir = _workflow_output_dir(data.get("workflow_name"), cache.get("prompt"))
    ext = Types.VideoContainer.get_extension("mp4")
    file_path = os.path.join(output_dir, f"{name}.{ext}")
    video.save_to(
        file_path,
        format=Types.VideoContainer.MP4,
        codec=Types.VideoCodec.AUTO,
    )
    saved_dir = resolve_subdir(data.get("workflow_name"), cache.get("prompt"))
    where = f"{saved_dir}/" if saved_dir else ""
    return web.json_response(
        {"status": "ok", "message": f"已保存: {where}{name}.{ext}"}
    )


PromptServer.instance.routes.post("/preview-video/frame/{node_id}")(_handle_frame)
PromptServer.instance.routes.post("/preview-video/frame-remove/{node_id}")(_handle_frame_remove)
PromptServer.instance.routes.post("/preview-video/done/{node_id}")(_handle_done)
PromptServer.instance.routes.post("/preview-video/save/{node_id}")(_handle_save)
PromptServer.instance.routes.post("/preview-video/reset")(_handle_reset)
PromptServer.instance.routes.post("/preview-video/clear")(_handle_clear)
PromptServer.instance.routes.get("/preview-video/state/{node_id}")(_handle_state)
PromptServer.instance.routes.get("/preview-video/video-url/{node_id}")(_handle_video_url)
