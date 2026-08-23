# fps/nodes.py
"""FallingTS 帧率转换节点: 按目标帧率对图像序列抽帧。

把模型生成的 24fps 帧序列按目标帧率抽帧输出 (例如 24fps → 8fps 保留每第 3 帧),
音频不动 (H3 原生 24fps 同步音轨在抽帧后仍与视频总时长一致), 配合 CreateVideo 的
fps 参数输出指定帧率的视频。
"""

from __future__ import annotations


class FallingTSFrameRateConvertNode:
    """按目标帧率抽帧: 输入 images (源帧率 source_fps) 输出 target_fps 对应的抽帧序列。

    抽帧步长 = max(1, round(source_fps / target_fps)), 每 stride 帧保留 1 帧;
    stride == 1 (目标帧率 >= 源帧率) 时原样透传。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入: images 图像序列 + 源帧率 + 目标帧率。"""
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "源帧率下的图像序列 (如 H3 生成的 24fps 帧)"}),
                "source_fps": (
                    "FLOAT",
                    {
                        "default": 24.0,
                        "min": 1.0,
                        "max": 120.0,
                        "step": 1.0,
                        "tooltip": "输入图像序列的帧率 (H3 原生 24)",
                    },
                ),
                "target_fps": (
                    "FLOAT",
                    {
                        "default": 8.0,
                        "min": 1.0,
                        "max": 120.0,
                        "step": 1.0,
                        "tooltip": "目标输出帧率 (抽帧后 CreateVideo 用此帧率输出)",
                    },
                ),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    OUTPUT_TOOLTIPS = ("抽帧后的图像序列 (每 round(source/target) 帧保留 1 帧)",)
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"
    DESCRIPTION = "按目标帧率抽帧: 24fps → 8fps 保留每第 3 帧; 音频不动, 视频总时长不变, 播放速率正常。"

    def execute(self, images, source_fps: float, target_fps: float):
        """节点执行入口: 按帧率比抽帧。

        抽帧步长 = max(1, round(source_fps / target_fps)); stride == 1 时原样返回。
        images 为 None (未连接/上游失败) 时透传 None;
        source_fps/target_fps 任一为 None (未连接) 时无法计算帧率比, 按原样透传 (stride=1)。

        参数:
            images (torch.Tensor | None): [B,H,W,3] 图像序列;
            source_fps (float | None): 源帧率 (None 视为未连接, 原样透传);
            target_fps (float | None): 目标帧率 (None 视为未连接, 原样透传)。

        返回:
            tuple[torch.Tensor | None]: 抽帧后的图像序列。
        """
        if images is None:
            return (None,)
        try:
            stride = max(1, round(source_fps / target_fps))
        except (TypeError, ZeroDivisionError):
            # source_fps / target_fps 任一为 None (未连接) 或非法 → 无法算帧率比, 原样透传
            return (images,)
        if stride == 1 or images.shape[0] <= 1:
            return (images,)
        return (images[::stride],)


NODE_CLASS_MAPPINGS = {
    "FallingTSFrameRateConvert": FallingTSFrameRateConvertNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSFrameRateConvert": "FallingTS 帧率转换 (抽帧)",
}
