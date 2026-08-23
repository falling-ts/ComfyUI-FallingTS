# PreviewVideo 节点: 预览视频 + 点「保存」才写入 output 目录。
# 参照 PreviewImageSave(preview-image/nodes.py) 的「始终预览(temp)+ 保存按钮写 output」模式。
# 原理: VIDEO 是惰性内存对象, 核心 WebSocket 协议只有图片预览事件;
#       本节点把 VIDEO 编码成 mp4 写到【临时目录】(temp, 非 output),
#       再通过 UI.PreviewVideo 让前端播放临时文件 —— "不满意就不保存"。
#       点「保存」按钮时, 后端用 execute 缓存的视频按 {filename_prefix}.mp4
#       直接写 output(同名覆盖, 不带 _序号 后缀), 不重跑工作流。

from __future__ import annotations

import os
import random
import string

from aiohttp import web
from server import PromptServer

from comfy_api.latest import IO, Types, UI
import folder_paths

_NODE_NAME = "PreviewVideo"

# 最近一次预览的视频缓存: node_id -> {"video": Video, "filename_prefix": str}
# 点「保存」时前端把文件名 POST 过来, 后端直接用缓存写 output(无需重跑工作流)
_last_output: dict[str, dict] = {}


class PreviewVideoNode(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: 节点元数据, 含 node_id/display_name/category/description,
            输入 video + filename_prefix, 输出 video, hidden 含 prompt+extra_pnginfo+unique_id,
            标记 is_output_node=True。
        """
        return IO.Schema(
            node_id=_NODE_NAME,
            display_name="Preview Video (保存)",
            category="video",
            description=(
                "Preview the video without saving it to the ComfyUI output directory; "
                "click 保存 to write it to output as {filename_prefix}.mp4 (no sequence suffix). "
                "Encodes to the temp folder for preview."
            ),
            inputs=[
                IO.Video.Input("video", tooltip="要预览的视频 (None = 无值, 如扇出未选中分支, 跳过预览, 输出该节点最近一次预览的视频供下游)。"),
                IO.String.Input(
                    "filename_prefix",
                    default="video",
                    multiline=False,
                    tooltip="保存到 output 的文件名(不含扩展名); 同名直接覆盖, 无序号",
                ),
            ],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo, IO.Hidden.unique_id],
            is_output_node=True,
            outputs=[IO.Video.Output("video")],
        )

    @classmethod
    def execute(cls, video, filename_prefix: str = "video", prompt=None, extra_pnginfo=None) -> IO.NodeOutput:
        """节点执行入口: 把视频编码为 mp4 写入临时目录并在前端播放, 同时缓存供「保存」直接写 output。

        逻辑: 视频为 None (如扇出节点未选中分支输出 = 无值) 跳过预览/缓存, 输出本节点最近一次预览的视频(从未预览过则 None);
        否则取尺寸生成随机前缀文件名, 经 folder_paths 得到临时目录保存路径,
        以 MP4 + AUTO 编码保存, 返回 UI.PreviewVideo 让前端播放临时文件。
        同时把 video/filename_prefix 缓存进 _last_output[unique_id] —— 点「保存」按钮,
        前端 POST 到 /preview-video/save/{node_id}, 后端直接用这份缓存写 output, 【不重跑工作流】。

        参数:
            video (Video|None): 要预览的视频对象(惰性内存对象); None (如扇出未选中分支) 跳过预览/缓存, 输出本节点最近一次预览的视频(从未预览过则 None)。
            filename_prefix (str, 默认 "video"): 保存文件名前缀(控件; 若被上游连线,
                widget 只是占位符, 本参数为实际接收值, 保存时以此为准)。
            prompt (dict|None): 工作流 prompt(预留元数据)。
            extra_pnginfo (dict|None): 额外元数据(预留)。

        返回:
            IO.NodeOutput: 视频输出 + UI.PreviewVideo 预览事件(指向 temp 目录文件);
            video 为 None 时回放上一次预览事件(保持原预览不清空) 并输出本节点最近一次预览的视频(从未预览过则 None)。
        """
        # None (如扇出节点未选中分支输出 = 无值): 不动原来的数据 —— 回放上一次预览事件
        # (temp 文件仍在, 原预览保持), 输出本节点【最近一次预览的视频】(下游可拿到该分支之前预览的
        # 视频, 而非 None); 从未预览过则输出 None, 不更新「保存」缓存
        if video is None:
            nid = getattr(cls.hidden, "unique_id", None)
            cached = _last_output.get(str(nid)) if nid else None
            last_video = cached.get("video") if cached else None
            if cached and cached.get("file"):
                return IO.NodeOutput(
                    last_video,
                    ui=UI.PreviewVideo([UI.SavedResult(cached["file"], cached["subfolder"], IO.FolderType.temp)]),
                )
            return IO.NodeOutput(last_video)

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

        # 缓存最近一次预览的视频(供「保存」直接写 output, 无需重跑)
        nid = getattr(cls.hidden, "unique_id", None)
        if nid:
            _last_output[str(nid)] = {
                "video": video,
                "filename_prefix": filename_prefix,
                "prompt": prompt,
                "file": file,
                "subfolder": subfolder,
            }

        return IO.NodeOutput(video, ui=UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)]))


async def _handle_save(request: web.Request) -> web.Response:
    """HTTP 路由: 用缓存视频把该节点最近预览的视频写入 output(同名覆盖, 无序号)。

    流程: 前端点「保存」按钮时把文件名前缀 POST 过来;
    后端查 _last_output[node_id](execute 时缓存的视频), 有则编码写 output, 无则 400。
    全程不触发任何工作流重跑。文件名 = {filename_prefix}.mp4, 不带 _0001 序列后缀。

    参数:
        request (web.Request): POST /preview-video/save/{node_id}, body 为 JSON
            {filename_prefix, filename_prefix_linked}。

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

    video = cache["video"]
    output_dir = folder_paths.get_output_directory()
    ext = Types.VideoContainer.get_extension("mp4")
    file_path = os.path.join(output_dir, f"{filename_prefix}.{ext}")
    video.save_to(
        file_path,
        format=Types.VideoContainer.MP4,
        codec=Types.VideoCodec.AUTO,
    )
    return web.json_response(
        {"status": "ok", "message": f"已保存: {filename_prefix}.{ext}"}
    )


PromptServer.instance.routes.post("/preview-video/save/{node_id}")(_handle_save)
