# video-components/nodes.py
"""FallingTS 视频拆解节点 (None 安全的参考视频解码)。

核心 GetVideoComponents 的 `video` 是 required 输入, execute 内直接调 `video.get_components()`,
收到 None 会抛 AttributeError ('NoneType' object has no attribute 'get_components')。
H3 参考工作流 (3020-参考场景 / 4030-参考视频) 的 <Video N> 参考列允许留空, mdtable 对空字段按
"可选输入惯例"输出 None, 这个 None 在到达 MiniMaxH3ReferenceToVideo 之前就会撞上
GetVideoComponents 而整图失败。本节点是它的 None 安全替代。

None 语义: 输出全 None, **不做 sticky 回放** (与本插件其它数据类节点的约定不同) ——
video 为 None 表示"该行没有视频参考", 若回放上一次的视频会让生成张冠李戴;
下游 MiniMaxH3ReferenceToVideo 的 ref_video_N 是可选输入, None 会被它内部的
`if video_frames is None: continue` 安全跳过, 这正是期望行为。
"""

from __future__ import annotations


class FallingTSVideoComponentsNode:
    """拆解参考视频为帧序列/音频/帧率/位深/色彩空间; video 为 None 时全部输出 None。"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入: 仅一个可选的 video (未连接/None 均安全)。"""
        return {
            "required": {},
            "optional": {
                "video": (
                    "VIDEO",
                    {"tooltip": "参考视频 (None = 该行无视频参考, 全部输出 None, 不报错)"},
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "FLOAT", "INT", "STRING")
    RETURN_NAMES = ("images", "audio", "fps", "bit_depth", "color_space")
    OUTPUT_TOOLTIPS = (
        "视频帧序列 (IMAGE); video 为 None 时为 None",
        "视频音轨 (AUDIO); video 为 None 时为 None",
        "帧率 (FLOAT); video 为 None 时为 0.0",
        "位深 (INT); video 为 None 时为 0",
        "色彩空间 (STRING); video 为 None 时为空串",
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"
    DESCRIPTION = "拆解参考视频为帧/音频/帧率/位深/色彩空间; video 未连接或为 None 时全部输出 None, 不崩溃。"

    def execute(self, video=None):
        """节点执行入口: 拆解视频组件。

        video 为 None (未连接 / mdtable 空字段) 时全部输出 None, 不报错、不回放上次结果;
        否则返回该视频的帧序列、音轨、帧率、位深与色彩空间 (语义与核心 GetVideoComponents 一致)。

        参数:
            video (Video | None): 参考视频对象; None 视为"无视频参考"。

        返回:
            tuple: (images, audio, fps, bit_depth, color_space);
                   video 为 None 时为 (None, None, 0.0, 0, "")。
        """
        if video is None:
            return (None, None, 0.0, 0, "")
        components = video.get_components()
        return (
            components.images,
            components.audio,
            float(components.frame_rate),
            video.get_bit_depth(),
            video.get_color_space(),
        )


NODE_CLASS_MAPPINGS = {
    "FallingTSVideoComponents": FallingTSVideoComponentsNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSVideoComponents": "FallingTS 视频拆解 (拆帧/拆音)",
}
