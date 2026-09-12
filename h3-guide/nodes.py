# h3-guide/nodes.py
"""FallingTS H3 引导锚定节点 (None 安全的 Add Guide)。

关键帧列的留空能力依赖本节点。核心 `MiniMaxH3AddGuide` 在 image 与 audio 同为 None 时
直接抛 `ValueError("MiniMaxH3AddGuide needs an image or an audio to anchor")`; 而 mdtable
对空的 `<Picture N>` 列按"可选输入惯例"输出 None, `execution.py` 又把上游的 None 原样传给
下游 (`input_data_all[x] = obj`, 不走 `mark_missing`) —— 于是 N 路引导串联时, 只要有一列
留空就在那一环整图失败, "尾部可留空" 无法成立。

本节点是它的 None 安全替代: image 与 audio 同为 None 时**原样透传 positive**, 等价于
"这一列没有锚点", 链路继续往下走。有值时把工作整个交给核心 AddGuide (直接调用
`MiniMaxH3AddGuide.execute`, 不复制其实现), 因此锚定语义与官方完全一致。

4025-关键帧视频 用 9 路本节点串联: 表里填了几列就锚几个点, 尾部留空自动少锚点。
"""

from __future__ import annotations

from comfy_api.latest import io
from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide


class FallingTSH3AddGuideNode(io.ComfyNode):
    """把 1 张图 (或音频) 锚定到 MiniMax H3 视频的任意帧; 空输入时原样透传不报错。"""

    @classmethod
    def define_schema(cls):
        """声明节点输入/输出: 与核心 MiniMaxH3AddGuide 同形, 仅空值分支改为透传。"""
        return io.Schema(
            node_id="FallingTSH3AddGuide",
            display_name="FallingTS H3 引导锚定 (None 安全)",
            category="FallingTS/H3",
            description=(
                "把 1 张图 (或音频) 锚定到 MiniMax H3 视频的任意帧。image 与 audio 同为 None 时"
                "原样透传 positive (该列无锚点, 不报错), 因此关键帧列可以留空。"
                "有值时语义与核心 Add Guide 完全一致。"
            ),
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("latent"),
                io.Int.Input(
                    "frame_idx",
                    default=0,
                    min=-9999,
                    max=9999,
                    tooltip=(
                        "锚定帧索引 (24fps 像素帧)。秒数换算 frame_idx = round(秒 × 24); "
                        "负值从视频末尾起算, 尾帧一律用 -1。"
                    ),
                ),
                io.Vae.Input("vae", optional=True, tooltip="视频 VAE, 接图像时必填。"),
                io.Vae.Input("audio_vae", optional=True, tooltip="音频 VAE, 接音频时必填。"),
                io.Image.Input(
                    "image",
                    optional=True,
                    tooltip="要锚定的图。None (mdtable 空列) = 该列无锚点, 原样透传 positive。",
                ),
                io.Audio.Input("audio", optional=True, tooltip="与图同帧起锚定的音轨。"),
            ],
            outputs=[io.Conditioning.Output(display_name="positive")],
        )

    @classmethod
    def execute(cls, positive, latent, frame_idx, vae=None, audio_vae=None, image=None, audio=None) -> io.NodeOutput:
        """节点执行入口: 空输入透传, 有值委派核心 Add Guide。

        参数:
            positive (CONDITIONING): 上游条件 (基础条件或上一个引导节点的输出)。
            latent (LATENT): MiniMax H3 AV latent, 用于取目标时长/尺寸。
            frame_idx (int): 锚定帧索引; 负值从末尾起算。
            vae (VAE | None): 视频 VAE, 接图像时必填。
            audio_vae (VAE | None): 音频 VAE, 接音频时必填。
            image (IMAGE | None): 要锚定的图; None 表示该列留空。
            audio (AUDIO | None): 要锚定的音轨。

        返回:
            IO.NodeOutput: 单元素 (positive,); 空输入时即传入的 positive 本身。
        """
        if image is None and audio is None:
            return io.NodeOutput(positive)
        return MiniMaxH3AddGuide.execute(
            positive, latent, frame_idx, vae=vae, audio_vae=audio_vae, image=image, audio=audio
        )


NODE_CLASS_MAPPINGS = {
    "FallingTSH3AddGuide": FallingTSH3AddGuideNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSH3AddGuide": "FallingTS H3 引导锚定 (None 安全)",
}
