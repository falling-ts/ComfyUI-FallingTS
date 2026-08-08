# PreviewVideo 节点: 预览视频但不写入 output 目录。
# 参考 PreviewImage / PreviewAudio / SaveVideo 的实现。
# 原理: VIDEO 是惰性内存对象, 核心 WebSocket 协议只有图片预览事件;
#       本节点把 VIDEO 编码成 mp4 写到【临时目录】(temp, 非 output),
#       再通过 UI.PreviewVideo 让前端播放临时文件 —— "不满意就不保存"。

from __future__ import annotations

import os
import random
import string

from comfy_api.latest import IO, Types, UI
import folder_paths

_NODE_NAME = "PreviewVideo"


class PreviewVideoNode(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: 节点元数据, 含 node_id/display_name/category/description,
            输入 video、输出 video, hidden 含 prompt+extra_pnginfo, 标记 is_output_node=True。
        """
        return IO.Schema(
            node_id=_NODE_NAME,
            display_name="Preview Video (不保存)",
            category="video",
            description=(
                "Preview the video without saving it to the ComfyUI output directory. "
                "Encodes to the temp folder and plays it in the browser."
            ),
            inputs=[
                IO.Video.Input("video", tooltip="要预览的视频。"),
            ],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo],
            is_output_node=True,
            outputs=[IO.Video.Output("video")],
        )

    @classmethod
    def execute(cls, video) -> IO.NodeOutput:
        """节点执行入口: 把视频编码为 mp4 写入临时目录并在前端播放(不保存到 output)。

        逻辑: 视频为空则报错; 取尺寸生成随机前缀文件名, 经 folder_paths 得到临时目录保存路径,
        以 MP4 + AUTO 编码保存, 返回 UI.PreviewVideo 让前端播放临时文件。

        参数:
            video (Video): 要预览的视频对象(惰性内存对象)。

        返回:
            IO.NodeOutput: 视频输出 + UI.PreviewVideo 预览事件(指向 temp 目录文件)。

        异常:
            ValueError: video 为 None 时抛出。
        """
        if video is None:
            raise ValueError("PreviewVideo: input video is None")

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
        return IO.NodeOutput(video, ui=UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)]))
