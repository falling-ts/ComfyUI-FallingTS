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
