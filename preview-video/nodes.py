# PreviewVideo 节点: 预览视频 + 点「保存」才写入 output 目录。
# 参照 PreviewImageSave(preview-image/nodes.py) 的「始终预览(temp)+ 保存按钮写 output」模式。
# 原理: VIDEO 是惰性内存对象, 核心 WebSocket 协议只有图片预览事件;
#       本节点把 VIDEO 编码成 mp4 写到【临时目录】(temp, 非 output),
#       再通过 UI.PreviewVideo 让前端播放临时文件 —— "不满意就不保存"。
#       点「保存」按钮时, 后端用 execute 缓存的视频按 {filename_prefix}{filename_suffix}.mp4
#       直接写 output(同名覆盖, 不带 _序号 后缀), 不重跑工作流。
#       filename_suffix 默认空串, 可手动输入或上游连线, 保存时拼接在前缀之后。
#
# 截帧/完成/选中帧输出已迁至 load-video 的 FallingTSLoadVideo 节点(2026-10-02):
# 本节点此后只保留「预览 + 保存」两件事, 与核心 SaveVideo 的分工一致(不落盘, 点保存才写);
# 输出只剩 video(原样透传), 不再有 image_1..image_64 的截帧槽。

from __future__ import annotations

import os
import random
import string
from urllib.parse import quote

from aiohttp import web
from server import PromptServer

from comfy_api.latest import IO, Types, UI
import folder_paths

from output_subdir import resolve_subdir, safe_dir_name

_NODE_NAME = "PreviewVideo"

# 最近一次预览的视频缓存: node_id -> {"video", "filename_prefix", "filename_suffix", "file", "subfolder", "prompt"}
# 点「保存」时前端把文件名 POST 过来, 后端直接用缓存处理(无需重跑工作流)
_last_output: dict[str, dict] = {}

# 重置代际: /preview-video/reset 时递增, 纳入 fingerprint_inputs -> 每次 Run 后指纹必变,
# 强制本节点重新执行(不被 ComfyUI 全局执行缓存跳过, 否则预览停在旧 temp 文件上)。
_reset_generation: int = 0


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


class PreviewVideoNode(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: 节点元数据, 含 node_id/display_name/category/description,
            输入 video + filename_prefix + filename_suffix, 输出 video,
            hidden 含 prompt+extra_pnginfo+unique_id, 标记 is_output_node=True。
        """
        return IO.Schema(
            node_id=_NODE_NAME,
            display_name="Preview Video (保存)",
            category="FallingTS",
            description=(
                "Preview the video without saving it to the ComfyUI output directory; "
                "click 保存 to write it to output as {filename_prefix}{filename_suffix}.mp4 (no sequence suffix). "
                "Encodes to the temp folder for preview."
            ),
            inputs=[
                IO.Video.Input(
                    "video",
                    tooltip="要预览的视频(None = 无值, 如扇出未选中分支, 跳过预览, 输出该节点最近一次预览的视频供下游)。",
                ),
                IO.String.Input(
                    "filename_prefix",
                    default="video",
                    multiline=False,
                    tooltip="保存到 output 的文件名(不含扩展名); 同名直接覆盖, 无序号",
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
            outputs=[IO.Video.Output("video", tooltip="预览/保存的视频。")],
        )

    @classmethod
    def execute(cls, video, filename_prefix: str = "video", filename_suffix: str = "") -> IO.NodeOutput:
        """节点执行入口: 把视频编码为 mp4 写入临时目录并在前端播放, 输出该视频(原样透传)。

        video 为 None (扇出未选中分支 / 上游无值)时回放上次预览事件并输出缓存视频,
        从未预览过则输出 None(下游按无值处理), 绝不抛异常。

        参数:
            video (Video|None): 要预览的视频对象(惰性内存对象)。
            filename_prefix (str, 默认 "video"): 保存文件名前缀(控件; 被上游连线时本参数为实际接收值)。
            filename_suffix (str, 默认 ""): 文件名后缀(控件, 保存时拼接在前缀之后)。

        返回:
            IO.NodeOutput: 视频 + UI.PreviewVideo 预览事件(temp 文件)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        # 工作流 prompt 只能从 hidden 取 —— V3 节点的 hidden 不进 execute 实参。
        prompt = getattr(cls.hidden, "prompt", None)

        if video is None:
            cached = _last_output.get(nid_str)
            if cached and cached.get("file"):
                return IO.NodeOutput(
                    cached.get("video"),
                    ui=UI.PreviewVideo([UI.SavedResult(cached["file"], cached["subfolder"], IO.FolderType.temp)]),
                )
            return IO.NodeOutput(None)

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

        _last_output[nid_str] = {
            "video": video,
            "filename_prefix": filename_prefix,
            "filename_suffix": filename_suffix,
            "prompt": prompt,
            "file": file,
            "subfolder": subfolder,
        }
        return IO.NodeOutput(
            video,
            ui=UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)]),
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        """缓存失效签名: 重置代际 + 节点 id。

        /preview-video/reset 递增 _reset_generation, 使每次默认 Run 后本节点必然重新执行
        (重新编码 temp 并发出预览事件), 不被 ComfyUI 全局执行缓存跳过 —— 否则预览会停在
        上一次的 temp 文件上(该文件一旦被清理, 播放就报「视频加载失败」)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        return (_reset_generation, str(nid) if nid else "")


async def _handle_reset(request: web.Request) -> web.Response:
    """重置所有 PreviewVideo(前端默认 Run / 无帧点「完成」时调用): 递增代际强制重跑。"""
    global _reset_generation
    _reset_generation += 1
    return web.json_response({"status": "ok"})


async def _handle_clear(request: web.Request) -> web.Response:
    """保留端点但**不清任何状态**(后端是唯一事实来源, 刷新后由前端读回重建)。"""
    return web.json_response({"status": "ok"})


async def _handle_video_url(request: web.Request) -> web.Response:
    """HTTP 路由: 返回该节点当前缓存视频的可播放 URL, 供前端在刷新后重建预览。

    节点原生的 UI.PreviewVideo 是一次性 WebSocket 事件, 页面刷新后不会重发, 视频预览
    就空了。前端因此在节点上备一个 <video>, 页面加载/刷新时调本路由拿 URL 填上。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid) or {}
    file = cache.get("file")
    if not file:
        return web.json_response({"status": "error", "message": "没有可预览的视频, 请先运行到该节点"}, status=400)
    subfolder = cache.get("subfolder") or ""
    return web.json_response(
        {"status": "ok", "url": f"/view?filename={quote(file)}&subfolder={quote(subfolder)}&type=temp"}
    )


async def _handle_save(request: web.Request) -> web.Response:
    """HTTP 路由: 用缓存视频把该节点最近预览的视频写入 output(同名覆盖, 无序号)。

    流程: 前端点「保存」按钮时把文件名前缀+后缀 POST 过来;
    后端查 _last_output[node_id](execute 时缓存的视频), 有则编码写 output, 无则 400。
    全程不触发任何工作流重跑。文件名 = {filename_prefix}{filename_suffix}.mp4, 不带 _0001 序列后缀。
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


PromptServer.instance.routes.post("/preview-video/save/{node_id}")(_handle_save)
PromptServer.instance.routes.post("/preview-video/reset")(_handle_reset)
PromptServer.instance.routes.get("/preview-video/video-url/{node_id}")(_handle_video_url)
PromptServer.instance.routes.post("/preview-video/clear")(_handle_clear)
