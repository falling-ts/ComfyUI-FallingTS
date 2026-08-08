# route/nodes.py
"""FallingTS 路由节点: 1 进 2 出。

一个值按布尔开关路由到两路输出之一:
- switch=true  → value 走 output_true, output_false 输出阻断(下游跳过);
- switch=false → value 走 output_false, output_true 输出阻断(下游跳过)。
适合"false=保存本段并停止, true=继续下一段"的分支场景。
"""

from __future__ import annotations

from typing import Any

from comfy_execution.graph_utils import ExecutionBlocker


class FallingTSRouteNode:
    """1 进 2 出路由节点: 一个值按布尔开关路由到两路输出之一。"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "switch": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "true → value 走 output_true; false → value 走 output_false; 未选输出为阻断",
                    },
                ),
                "value": ("*", {"tooltip": "要路由的值(通常是本段结果图像)"}),
            },
        }

    RETURN_TYPES = ("*", "*")
    RETURN_NAMES = ("output_false", "output_true")
    OUTPUT_TOOLTIPS = (
        "switch=false 时输出 value, switch=true 时为阻断",
        "switch=true 时输出 value, switch=false 时为阻断",
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/控制"
    DESCRIPTION = "一路输入按布尔路由到两路输出之一; 未选输出为阻断(ExecutionBlocker), 下游不执行。"

    def execute(self, switch: bool, value: Any = None):
        # 未选中输出为无消息阻断: 下游跳过但不报错
        if switch:
            return (ExecutionBlocker(None), value)
        return (value, ExecutionBlocker(None))


NODE_CLASS_MAPPINGS = {
    "FallingTSRoute": FallingTSRouteNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSRoute": "FallingTS 路由节点 (1进2出)",
}
