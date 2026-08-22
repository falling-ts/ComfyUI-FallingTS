# route/nodes.py
"""FallingTS 路由节点: total 组路由 (参考分组开关, total 组范式)。

参考 FallingTSSwitch: 一个 switch 布尔同时路由 total 组:
- 每组 = 为假时_i (ANY) / 为真时_i (ANY) 两个输入 + output_i (ANY) 一个输出;
- switch 为真 -> 各组输出 true_i, 为假 -> 各组输出 false_i;
- total 为组数 (最少 1, 最多 MAX_GROUPS), 前端 (web/js/route.js) 按 total 动态增删输入输出端口;
- 前端另保留分段执行增强: partial 提交时把 switch=false 路由节点各组输出下游的输出节点并入 targets,
  让"false=保存本段并停止"真正执行。
"""

from __future__ import annotations

from typing import Any


MAX_GROUPS = 50


class FallingTSRouteNode:
    """total 组路由: 一个 switch 同时路由 total 组 为假时/为真时。

    后端声明 MAX_GROUPS 组 (false_i/true_i 输入 + output_i 输出),
    前端 (web/js/route.js) 按 total 动态增删, 未使用的端口不进入 prompt。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".switch: 布尔开关, true 时各组输出 true_i, false 时各组输出 false_i;
            - "required".total: 组数(1~MAX_GROUPS), 前端按此动态增删端口;
            - "optional".false_i / true_i: 第 i 组的两个输入(ANY), 共 MAX_GROUPS 组。
        """
        required = {
            "switch": (
                "BOOLEAN",
                {"default": True, "tooltip": "为真时各组输出 为真时_i, 为假时各组输出 为假时_i"},
            ),
            "total": (
                "INT",
                {
                    "default": 2,
                    "min": 1,
                    "max": MAX_GROUPS,
                    "tooltip": f"组数 (最少 1, 最多 {MAX_GROUPS}), 每组 = 为假时/为真时/输出",
                },
            ),
        }
        optional = {}
        for i in range(1, MAX_GROUPS + 1):
            optional[f"false_{i}"] = ("*", {"tooltip": f"第 {i} 组: switch 为假时输出此项"})
            optional[f"true_{i}"] = ("*", {"tooltip": f"第 {i} 组: switch 为真时输出此项"})
        return {"required": required, "optional": optional}

    RETURN_TYPES = ("*",) * MAX_GROUPS
    RETURN_NAMES = tuple(f"output_{i}" for i in range(1, MAX_GROUPS + 1))
    OUTPUT_TOOLTIPS = tuple(f"第 {i} 组输出: switch 为真取 true_{i}, 为假取 false_{i}" for i in range(1, MAX_GROUPS + 1))
    FUNCTION = "execute"
    CATEGORY = "FallingTS/控制"
    DESCRIPTION = (
        "total 组路由 (参考分组开关): 一个 switch 布尔同时路由 total 组, "
        "每组 = 为假时/为真时/输出 (ANY), total 最少 1; "
        "partial 提交时 switch=false 的各组输出下游输出节点真正执行 (前端增强)。"
    )
    SEARCH_ALIASES = ["route", "路由", "分组", "多路", "多组", "分支", "分段", "switch"]

    def execute(self, switch: bool, total: int, **kwargs):
        """节点执行入口: 按 switch 与 total 从各组取对应输入。

        逻辑: total 裁到 [1, MAX_GROUPS]; 对每组 i, i<=total 时取 switch 对应的输入
        (true → true_i, false → false_i), 超出 total 的组输出 None(端口未启用)。

        参数:
            switch (bool): true → 各输出取 true_i, false → 取 false_i;
            total (int): 启用组数(1~MAX_GROUPS, 非法值回退 1);
            **kwargs: 各组输入 false_i / true_i(引擎按名字传入)。

        返回:
            tuple[Any, ...]: 长度 MAX_GROUPS, 前 total 个为对应输入, 其余为 None。
        """
        try:
            total = max(1, min(MAX_GROUPS, int(total)))
        except (TypeError, ValueError):
            total = 1
        out = []
        for i in range(1, MAX_GROUPS + 1):
            if i <= total:
                out.append(kwargs.get(f"true_{i}") if switch else kwargs.get(f"false_{i}"))
            else:
                out.append(None)
        return tuple(out)


NODE_CLASS_MAPPINGS = {
    "FallingTSRoute": FallingTSRouteNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSRoute": "FallingTS 路由节点 (total组)",
}
