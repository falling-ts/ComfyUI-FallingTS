# PreviewVideo 节点: 预览视频 + 点「保存」才写入 output 目录 + 截帧输出选中帧 IMAGE。
# 参照 PreviewImageSave(preview-image/nodes.py) 的「始终预览(temp)+ 保存按钮写 output」模式。
# 原理: VIDEO 是惰性内存对象, 核心 WebSocket 协议只有图片预览事件;
#       本节点把 VIDEO 编码成 mp4 写到【临时目录】(temp, 非 output),
#       再通过 UI.PreviewVideo 让前端播放临时文件 —— "不满意就不保存"。
#       点「保存」按钮时, 后端用 execute 缓存的视频按 {filename_prefix}{filename_suffix}.mp4
#       直接写 output(同名覆盖, 不带 _序号 后缀), 不重跑工作流。
#       filename_suffix 默认空串, 可手动输入或上游连线, 保存时拼接在前缀之后。
#
# 截帧(2026-09-04 新增): 收到视频即用 get_components() 转内部帧集合 images 缓存到节点,
#       前端点「截帧」按钮把当前播放时间 POST 到 /preview-video/frame/{id},
#       后端按 fps 折算帧号从缓存 images 取该帧转 PNG 返回, 前端累积渲染 selected_images 列表;
#       点「完成」后 execute 按前端写回的 selected_frames 帧号列表输出 image_1..image_MAX_FRAMES (IMAGE),
#       未选中的槽为 None(与 mdtable/table 的动态端口同套模式: 后端定长槽 + 前端按 total 增删端口,
#       前端输出端口数量按「输出帧数」total 展示, 而非一次性显示全部 64 槽)。
#
# 刷新即清空(2026-09-04 补): 前端页面加载(setup)时调 /preview-video/clear 同步清空所有节点
#       的 selected_frames + _done, 且 configure 不再还原序列化的帧列表 —— 浏览器刷新 = 截帧
#       状态回未截帧初始态(前端缩略图与后端帧号都不保留); 视频/帧张量缓存不清(「保存」按钮
#       刷新后仍可用)。
#
# 「完成」= 继续节点语义(V3 lazy + partial execution, 与 proceed 同套机制):
#       - video 输入声明 lazy: 构建执行列表时不沿这条边向上游遍历, 是否拉上游由 check_lazy_status 决定
#         (未完成 -> 返回 ["video"] 拉上游生成视频填缓存; 已完成且有选中帧 -> 返回 [] 不拉, 用缓存);
#       - 未完成: execute 返回 ExecutionBlocker(None) 但 ui 预览照发 —— 上游全部执行、到此断开,
#         预览节点之后的合成/预览/保存节点不执行(运行时到预览就停);
#       - 点「完成」(无选中帧): 前端调 /preview-video/reset 清 done 再全量提交 = 预加载上游;
#       - 点「完成」(有选中帧): 前端调 /preview-video/done 置 done, 再以 partial_execution_targets
#         只提交预览节点之后的下游输出节点 —— 上游因 lazy 边不进子图, 运行时看不到预览前面的节点。

from __future__ import annotations

import io as _io
import os
import random
import string
from typing import Any

import numpy as np
from PIL import Image
import torch

from aiohttp import web
from server import PromptServer

from comfy_api.latest import IO, Types, UI
from comfy_execution.graph_utils import ExecutionBlocker
import folder_paths

_NODE_NAME = "PreviewVideo"

# 截帧输出上限(与 composite 的 MAX_TOTAL=64 一致; 后端声明定长槽, 前端按需增删端口)
MAX_FRAMES = 64

# 哨兵: 区分"该输入根本没连线"(MISSING)与"连了线但上游未求值"(None)。
# check_lazy_status 里只有真正连了线才能去拉上游 —— 若对不存在的输入调用
# make_input_strong_link 会抛 NodeInputError (comfy_execution/graph.py:122)。
MISSING = object()

# 最近一次预览的视频缓存: node_id -> {"video", "filename_prefix", "images", "fps", "selected_frames", ...}
# 点「保存」/「截帧」时前端把数据 POST 过来, 后端直接用缓存处理(无需重跑工作流)
_last_output: dict[str, dict] = {}

# 已「完成」截帧的节点: set[node_id] —— 完成前下游 image 输出为 None(阻塞语义),
# 前端点「完成」按钮置入本集合使 execute 输出选中帧(完成后即终态, 无重新截帧)。
# 点「完成」(无选中帧) / 默认 Run 时经 /preview-video/reset 清空 -> 重新拉上游生成。
_done: set[str] = set()
# 重置代际: /preview-video/reset 时递增, 纳入 fingerprint_inputs -> 每次 Run 后指纹必变,
# 强制 PreviewVideo 重新执行(重新拉上游填缓存), 不被 ComfyUI 全局执行缓存跳过。
_reset_generation: int = 0


class PreviewVideoNode(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: 节点元数据, 含 node_id/display_name/category/description,
            输入 video + filename_prefix + filename_suffix, 输出 video + image_1..image_MAX_FRAMES,
            hidden 含 prompt+extra_pnginfo+unique_id, 标记 is_output_node=True。
        """
        outputs = [IO.Video.Output("video", tooltip="预览/保存的视频。")]
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
            category="video",
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
                    tooltip="保存到 output 的文件名(不含扩展名); 同名直接覆盖, 无序号",
                ),
                # 紧随 filename_prefix(控件紧挨前缀显示); 旧工作流 widgets_values 按位置对齐,
                # 插入槽位由前端 onConfigure 按旧形状检测并自动迁移, 见 web/js/preview-video.js
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
    def execute(cls, video, filename_prefix: str = "video", filename_suffix: str = "", prompt=None, extra_pnginfo=None) -> IO.NodeOutput:
        """节点执行入口: 把视频编码为 mp4 写入临时目录并在前端播放, 缓存帧集合, 按选中帧输出 IMAGE。

        逻辑:
        - video 为 None (lazy 未拉上游 / 扇出未选中分支): 回放上次预览;
          已完成 -> 输出缓存的视频 + 选中帧(partial 只跑下游); 未完成 -> block 阻断下游;
        - 否则: 取尺寸生成随机前缀文件名写 temp 临时文件, 返回 UI.PreviewVideo 让前端播放;
          同时 video.get_components() 拆出全部帧缓存进 _last_output[unique_id]["images"] (截帧数据源);
          未「完成」: 输出全部 ExecutionBlocker(None) 阻断下游节点本身不执行
          (合成/预览/保存都不跑, "到预览节点就停止断掉"), 但 UI.PreviewVideo 预览事件照常发出
          (V3 的 NodeOutput(block_execution=..., ui=...) 可共存) —— 视频正常预览供播放/截帧;
          已「完成」: 输出缓存的 selected_frames 对应的帧序列 image_1..image_MAX_FRAMES(未选中槽 None)。

        参数:
            video (Video|None): 要预览的视频对象(惰性内存对象); None (lazy 未拉上游 / 扇出未选中分支) 跳过预览/缓存, 输出本节点最近一次预览的视频(从未预览过则 None)。
            filename_prefix (str, 默认 "video"): 保存文件名前缀(控件; 若被上游连线, widget 只是占位符, 本参数为实际接收值, 保存时以此为准)。
            filename_suffix (str, 默认 ""): 文件名后缀(控件, 保存时拼接在前缀之后; 连线时本参数为实际接收值)。
            prompt (dict|None): 工作流 prompt(预留元数据)。
            extra_pnginfo (dict|None): 额外元数据(预留)。

        返回:
            IO.NodeOutput:
            - 未完成: 全部输出槽 ExecutionBlocker(None)(阻断下游) + UI.PreviewVideo 预览事件;
            - 已完成: 视频 + image_1..image_MAX_FRAMES 选中帧 + UI.PreviewVideo 预览事件;
            - video 为 None 时回放上一次预览事件(count 已完成)或同样 block(未完成)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""

        # None (lazy 未拉上游 / 扇出未选中分支): 回放上一次预览事件。
        # 已完成 -> 输出缓存的视频+选中帧(partial 只跑下游); 未完成 -> block 阻断下游。
        if video is None:
            cached = _last_output.get(nid_str)
            if cached and cached.get("file"):
                selected = cached.get("selected_frames") or []
                if nid_str not in _done:
                    # 未完成: 预览仍发出, 但输出全部 block(下游节点不执行)
                    return IO.NodeOutput(
                        *([ExecutionBlocker(None)] * (1 + MAX_FRAMES)),
                        ui=UI.PreviewVideo([UI.SavedResult(cached["file"], cached["subfolder"], IO.FolderType.temp)]),
                    )
                frames_out = _frames_from_cache(cached, selected)
                return IO.NodeOutput(
                    cached.get("video"),
                    *frames_out,
                    ui=UI.PreviewVideo([UI.SavedResult(cached["file"], cached["subfolder"], IO.FolderType.temp)]),
                )
            return IO.NodeOutput(*([ExecutionBlocker(None)] * (1 + MAX_FRAMES)))

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

        # 拆出帧集合缓存(截帧数据源): images = [N,H,W,C] 张量, frame_rate
        try:
            components = video.get_components()
            images = components.images
            fps = float(components.frame_rate) if components.frame_rate else 0.0
        except Exception:
            images = None
            fps = 0.0

        # 保留既有选中帧号(前端经路由维护, 跨次执行不丢); 首次则空列表
        cached = _last_output.get(nid_str) or {}
        selected_frames = cached.get("selected_frames") or []

        _last_output[nid_str] = {
            "video": video,
            "filename_prefix": filename_prefix,
            "filename_suffix": filename_suffix,
            "prompt": prompt,
            "file": file,
            "subfolder": subfolder,
            "images": images,
            "fps": fps,
            "selected_frames": selected_frames,
        }

        frames_out = _frames_from_cache(_last_output[nid_str], selected_frames)
        done = nid_str in _done
        # 未「完成」(continue 语义): 用 block_execution 阻断下游节点本身不执行
        # (合成/预览/保存都不跑, "到预览节点就停止断掉"), 但 UI.PreviewVideo 预览事件
        # 仍照常发出 —— V3 的 NodeOutput(block_execution=..., ui=...) 两者可共存,
        # 视频照常出现在节点上供播放/截帧。首次 Run 即此态: 上游全部执行, 到此断开。
        if not done:
            return IO.NodeOutput(
                *([ExecutionBlocker(None)] * (1 + MAX_FRAMES)),
                ui=UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)]),
            )
        return IO.NodeOutput(
            video,
            *frames_out,
            ui=UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)]),
        )

    @classmethod
    def check_lazy_status(cls, video=MISSING, filename_prefix: str = "video", filename_suffix: str = "", prompt=None, extra_pnginfo=None) -> list[str]:  # noqa: A002
        """lazy 输入门控: 决定本次执行要不要拉取上游的 video —— "完成只跑下游"的关键。

        机制(ComfyUI 执行引擎, 与继续节点同套):
        1. 构建执行列表时, lazy 输入不会让 add_node 向上游遍历 —— 上游不因这条边被加入执行;
        2. 节点真正执行前, 引擎调本方法, 返回"缺失且需要拉取的输入名";
        3. 返回的输入名若在 missing_keys(连了线但未求值)里, 引擎才 make_input_strong_link 拉上游
           并返回 PENDING, 上游执行完重新调度本节点; 返回空则直接用 get_input_data 给的值(未拉取时是 None)。

        完成语义:
        - 已「完成」且已有选中帧: 上游不应重跑, 数据来自节点缓存 (_last_output) -> 返回 [] 不拉;
        - 未完成(首次 Run / reset 后 / 刚截完帧未点完成): 上游必须执行以产生视频 -> 返回 ["video"] 拉上游;
        - 没连线: 根本没有上游可拉, 返回 [] —— 避免对不存在的输入 make_input_strong_link 抛 NodeInputError。

        参数:
            video (Any, 默认 MISSING): 上游视频, 由引擎按输入名注入:
                - MISSING: 该输入没连线(不在 prompt 的 inputs 里, kwargs 无此键 -> 走默认值);
                - None: 连了线但上游未求值(lazy 输入未被拉取, 已完成时即此处);
                - 其他: 已求值的上游视频(此时已不在 missing_keys, 本方法的返回值会被过滤, 不触发拉取)。
            filename_prefix (str, 默认 "video"): 文件名前缀(本方法不读取, 仅保持签名兼容)。
            filename_suffix (str, 默认 ""): 文件名后缀(本方法不读取, 仅保持签名兼容)。
            prompt (dict|None): 工作流 prompt(预留, 不读取)。
            extra_pnginfo (dict|None): 额外元数据(预留, 不读取)。

        返回:
            list[str]: 本次需要拉取的上游输入名列表, 只能是 ["video"] 或 []。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        if video is MISSING:
            return []          # 没连线: 无上游可拉
        cached = _last_output.get(nid_str) or {}
        selected = cached.get("selected_frames") or []
        if nid_str in _done and selected:
            return []          # 已「完成」且有选中帧: 不拉上游, execute 从 _last_output 取缓存
        return ["video"]       # 未完成: 拉上游, 生成/更新缓存的视频

    @classmethod
    def fingerprint_inputs(cls, **kwargs) -> Any:
        """缓存失效签名: 把该节点当前的"选中帧列表 + 是否完成 + 重置代际"纳入指纹。

        截帧路由每追加/删除一帧都更新 _last_output[nid]["selected_frames"],
        「完成」置入 _done, 「重置」递增 _reset_generation; 指纹随之变化 -> PreviewVideo
        在重提交时必然重新执行, 使新截帧值/完成状态输出到下游(不被 ComfyUI 全局执行缓存跳过)。

        参数:
            **kwargs: 输入参数(不读取具体值), 仅保持签名兼容。

        返回:
            tuple: (重置代际, unique_id, 选中帧列表元组, 是否完成), 作为缓存指纹。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        cached = _last_output.get(nid_str) or {}
        return (_reset_generation, nid_str, tuple(cached.get("selected_frames") or ()), nid_str in _done)


def _frames_from_cache(cached: dict, selected: list[int]) -> list:
    """按选中帧号列表从缓存的帧集合取图(1-based → 张量索引), 未选中槽 None。

    返回的单帧形状为 [1, H, W, C] (带 batch 维, IMAGE 张量约定), 供下游直接预览/合成。

    参数:
        cached (dict): _last_output 中该节点的缓存(含 images 张量)。
        selected (list[int]): 选中帧号(1-based)。

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


def _png_bytes(frame: torch.Tensor) -> bytes:
    """把单帧张量编码为 PNG 字节(低压缩)。兼容 [H,W,C] 与 [1,H,W,C]。

    参数:
        frame (torch.Tensor): 单帧 [H,W,C] 或 [1,H,W,C] 张量。

    返回:
        bytes: PNG 编码字节。
    """
    if frame is None:
        raise ValueError("帧为空")
    if frame.dim() == 4:
        frame = frame[0]
    arr = (frame.float().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    buf = _io.BytesIO()
    img.save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


async def _handle_frame(request: web.Request) -> web.Response:
    """HTTP 路由: 按前端播放时间/帧号从缓存帧集合取该帧, 编码 PNG 返回并追加到选中帧列表。

    前端点「截帧」按钮时 POST 当前播放时间(秒)或帧号(1-based), 后端用 execute 时缓存的
    images 张量定位该帧, 转 PNG 返回; 同时把该帧号追加进缓存 selected_frames(去重, 上限
    MAX_FRAMES), 供下一次 execute 输出. 前端显示在截帧列表并记录帧号。

    请求体: {"position_seconds": float, "frame_index": int, "mode": "time"|"frame", "append": bool}
    - mode=time (默认): position_seconds × fps 折算帧号;
    - mode=frame: frame_index 直接用(1-based);
    - append=true (默认): 追加帧号到缓存 selected_frames; false 仅取帧不追加(预览用)。

    返回:
        web.Response:
        - 200: 直接把 PNG 字节返回 (Content-Type: image/png), 附加头 X-Frame-Index = 帧号(1-based);
        - 400: {"status": "error", "message": ...} 无缓存/帧号越界/帧为空/已满。
    """
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
        if fps > 0.0 and total > 1:
            fno = int(round(pos * fps)) + 1
        else:
            fno = 1
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

    frame = images[fno - 1]
    try:
        png = _png_bytes(frame)
    except Exception as e:
        return web.json_response({"status": "error", "message": f"帧编码失败: {e}"}, status=400)

    response = web.Response(body=png, content_type="image/png")
    response.headers["X-Frame-Index"] = str(fno)
    response.headers["X-Selected-Count"] = str(len(cache.get("selected_frames") or []))
    return response


async def _handle_frame_remove(request: web.Request) -> web.Response:
    """HTTP 路由: 从缓存 selected_frames 移除指定帧号(或清空)。

    前端点选中帧列表中的「✕」时调用。

    请求体: {"frame_index": int} 或 {"clear": true}。

    返回:
        web.Response: 200, {"status": "ok", "frames": [剩余帧号]}。
    """
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
    """HTTP 路由: 标记该节点「完成截帧」(置入 _done), 使下一次执行只跑下游。

    前端点红色「完成」按钮时调用(且已至少截了一帧): 完成后 video 输入被 lazy 门控
    跳过拉取(不重跑上游生成), PreviewVideo 用缓存的视频+选中帧输出给下游;
    前端随后以 partial_execution_targets 只提交下游输出节点 —— 运行时看不到前面的节点。

    请求体(可选): {"frames": [帧号...]} —— 从工作流恢复的帧(前端 DOM state, 后端缓存可能
    为空)时, 用前端帧号列表填充 _last_output[nid]["selected_frames"], 使完成可基于前端帧生效。

    参数:
        request (web.Request): POST /preview-video/done/{node_id}。

    返回:
        web.Response: 200, {"status": "ok", "done": bool}。
    """
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
            cache["selected_frames"] = cache.get("selected_frames") or []
    # 仅当节点已有选中帧才置完成(没帧的"完成"= 预加载上游, 走 reset+全量提交)
    if cache.get("selected_frames"):
        _done.add(nid)
    return web.json_response({"status": "ok", "done": nid in _done})


async def _handle_reset(request: web.Request) -> web.Response:
    """HTTP 路由: 重置所有 PreviewVideo 为未完成(前端默认 Run / 无帧点「完成」时调用)。

    清空 _done(全部回到阻塞态 = 未完成, 下次执行拉上游重新生成)并递增 _reset_generation
    (强制 PreviewVideo 重新执行, 见 fingerprint_inputs), 使下一次全量提交从开头执行。

    参数:
        request (web.Request): POST /preview-video/reset 请求, 不读取 body。

    返回:
        web.Response: 200, {"status": "ok"}。
    """
    global _reset_generation
    _done.clear()
    _reset_generation += 1
    return web.json_response({"status": "ok"})


async def _handle_clear(request: web.Request) -> web.Response:
    """HTTP 路由: 清空所有 PreviewVideo 的截帧状态(前端页面加载/刷新时调一次)。

    前端刷新后不再还原序列化的帧列表(缩略图回空), 后端须同步清掉内存帧号, 避免
    "前端列表已空但后端还留着旧帧号" —— 否则下次截帧会把新帧追加到旧帧号后面。
    清空各节点缓存的 selected_frames 并清 _done(全部回阻塞态); 视频/帧张量缓存
    不清(「保存」按钮刷新后仍可用)。selected_frames 变化本身会改变
    fingerprint_inputs, 无需再递增 _reset_generation。

    参数:
        request (web.Request): POST /preview-video/clear 请求, 不读取 body。

    返回:
        web.Response: 200, {"status": "ok"}。
    """
    for cache in _last_output.values():
        if isinstance(cache, dict):
            cache["selected_frames"] = []
    _done.clear()
    return web.json_response({"status": "ok"})


async def _handle_save(request: web.Request) -> web.Response:
    """HTTP 路由: 用缓存视频把该节点最近预览的视频写入 output(同名覆盖, 无序号)。

    流程: 前端点「保存」按钮时把文件名前缀+后缀 POST 过来;
    后端查 _last_output[node_id](execute 时缓存的视频), 有则编码写 output, 无则 400。
    全程不触发任何工作流重跑。文件名 = {filename_prefix}{filename_suffix}.mp4, 不带 _0001 序列后缀。

    参数:
        request (web.Request): POST /preview-video/save/{node_id}, body 为 JSON
            {filename_prefix, filename_suffix, filename_prefix_linked, filename_suffix_linked}。

    返回:
        web.Response:
        - 成功: 200, {"status": "ok", "message": "已保存: <文件名>.mp4"};
        - 失败: 400, {"status": "error", "message": "没有预览数据, 请先运行到该节点"}。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache or not cache.get("video"):
        return web.json_response(
            {"status": "error", "message": "没有预览数据, 请先运行到该节点"}, status=400
        )

    try:
        data = await request.json()
    except Exception:
        data = {}

    filename_prefix = str(data.get("filename_prefix", "video"))
    # 若 filename_prefix 输入被上游连线, widget 值是占位符:
    # 用 execute 时实际接收到的值 (前端已标记 filename_prefix_linked)
    if data.get("filename_prefix_linked") and cache.get("filename_prefix"):
        filename_prefix = str(cache["filename_prefix"])
    # 后缀同前缀: 手动输入或上游连线(连线时用 execute 实际接收值); 空串 = 不拼后缀
    # (旧工作流 widgets_values 按位置对齐, 尾部 null 落到 suffix 槽, 此处 or "" 兜底)
    filename_suffix = str(data.get("filename_suffix") or "")
    if data.get("filename_suffix_linked") and cache.get("filename_suffix") is not None:
        filename_suffix = str(cache["filename_suffix"])
    # 文件名 = 前缀 + 后缀
    name = filename_prefix + filename_suffix

    video = cache["video"]
    output_dir = folder_paths.get_output_directory()
    ext = Types.VideoContainer.get_extension("mp4")
    file_path = os.path.join(output_dir, f"{name}.{ext}")
    video.save_to(
        file_path,
        format=Types.VideoContainer.MP4,
        codec=Types.VideoCodec.AUTO,
    )
    return web.json_response(
        {"status": "ok", "message": f"已保存: {name}.{ext}"}
    )


PromptServer.instance.routes.post("/preview-video/save/{node_id}")(_handle_save)
PromptServer.instance.routes.post("/preview-video/frame/{node_id}")(_handle_frame)
PromptServer.instance.routes.post("/preview-video/frame-remove/{node_id}")(_handle_frame_remove)
PromptServer.instance.routes.post("/preview-video/done/{node_id}")(_handle_done)
PromptServer.instance.routes.post("/preview-video/reset")(_handle_reset)
PromptServer.instance.routes.post("/preview-video/clear")(_handle_clear)