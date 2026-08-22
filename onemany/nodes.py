# onemany/nodes.py
"""FallingTS 一对多下拉选择 (total 组, 参考多对一选择/路由节点的 total 组范式):
一个 value 输入 (ANY) 按 selection 多选下拉广播到 total 组中的若干输出:
- total 为输出组数 (最少 1, 最多 MAX_GROUPS), 前端 (web/js/onemany.js) 按 total 动态增删输出端口;
- selection 为多选下拉 (选项 = 输出组号 1..total, 可多选), 值存为逗号分隔的组号文本 (如 "1,3");
- 被选中的第 i 组输出 output_i = value 输入值, 未选中的组输出 None;
- 未连线时 value 为 None, 各组输出均为 None。
"""

from __future__ import annotations

from typing import Any


# 最多组数 (组数 total 的上限, 与多对一选择/路由/分组开关同一范式)
MAX_GROUPS = 50


def _parse_selection(selection: Any) -> set[int]:
    """把多选下拉的逗号分隔组号文本解析为去重组号集合 (1 起, 裁到 [1, MAX_GROUPS])。

    参数:
        selection (Any): 逗号分隔的组号文本 (如 "1,3"), 可为空字符串/None/数字。

    返回:
        set[int]: 有效的选中组号集合, 非法项忽略; 无有效项时为空集。
    """
    if selection is None:
        return set()
    items = selection if isinstance(selection, (list, tuple, set)) else str(selection).split(",")
    out: set[int] = set()
    for s in items:
        try:
            n = int(str(s).strip())
        except (TypeError, ValueError):
            continue
        if 1 <= n <= MAX_GROUPS:
            out.add(n)
    return out


def _clamp_total(total: Any) -> int:
    """组数钳位到 [1, MAX_GROUPS], 非法值回退默认 2 (与路由/分组开关一致)。

    参数:
        total (Any): 组数 (int 或可转 int 的文本)。

    返回:
        int: 1 ~ MAX_GROUPS 的有效组数。
    """
    try:
        t = int(total)
    except (TypeError, ValueError):
        t = 2
    return min(MAX_GROUPS, max(1, t))


class FallingTSOneToManyNode:
    """一对多下拉选择: total 组输出, 一个 value 输入按 selection 多选下拉广播到选中的若干输出。

    后端声明 MAX_GROUPS 个输出 (output_1..output_50), 前端 (web/js/onemany.js)
    按 total 动态增删; selection 多选下拉选项 = 输出组号 1..total (前端联动),
    值存为逗号分隔组号文本 (如 "1,3"), 被选中组的输出 = value, 其余为 None。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".total: 输出组数 (INT, 最少 1, 最多 MAX_GROUPS), 前端按此动态增删输出端口;
            - "required".selection: 多选下拉组号 (STRING, 逗号分隔, 如 "1,3"),
              选项为 1..total (前端 onemany.js 联动), 被选中组的输出 = value;
            - "optional".value: 单一数据输入 (ANY), 广播到所有被选中组的输出, 未连线时为 None。
        """
        return {
            "required": {
                "total": (
                    "INT",
                    {
                        "default": 2,
                        "min": 1,
                        "max": MAX_GROUPS,
                        "tooltip": f"输出组数 (最少 1, 最多 {MAX_GROUPS}), 输出端口 output_1..output_total",
                    },
                ),
                "selection": (
                    "FALLINGTS_ONEMANY_SELECT",
                    {
                        "default": "1",
                        "tooltip": "多选下拉: 选中哪些输出组 (选项 = 组号 1..total, 可多选), 值存为逗号分隔组号 (如 1,3); 选中组的输出 = value, 未选中组为 None",
                    },
                ),
            },
            "optional": {
                "value": (
                    "*",
                    {"tooltip": "单一输入 (ANY): 广播到所有被选中组的输出, 未连线时各组输出 None"},
                ),
            },
        }

    # 输出槽位: output_1..output_MAX_GROUPS, 前端按 total 显隐; 增删只动尾部, 已有连线的槽位永不漂移
    RETURN_TYPES = ("*",) * MAX_GROUPS
    RETURN_NAMES = tuple(f"output_{i}" for i in range(1, MAX_GROUPS + 1))
    OUTPUT_TOOLTIPS = tuple(
        f"第 {i} 组输出 (ANY): selection 含组号 {i} 时为 value 输入值, 否则 None"
        for i in range(1, MAX_GROUPS + 1)
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"
    DESCRIPTION = (
        "一对多下拉选择 (total组): 一个 value 输入按 selection 多选下拉 (选项 = 组号 1..total, 可多选) "
        "广播到选中的若干输出 output_i, 未选中组输出 None; 未连线时各组输出 None。"
    )
    SEARCH_ALIASES = ["一对多", "下拉", "多选", "扇出", "广播", "one-to-many", "fanout", "group", "组数", "多组", "total"]

    @classmethod
    def IS_CHANGED(cls, total: int = 2, selection: str = "1", **kwargs):
        """缓存失效签名: 组数或选中组号变化时重新执行 (value 为动态输入, 变化由引擎依赖机制处理)。"""
        return (total, selection)

    def execute(self, total: int = 2, selection: str = "1", **kwargs):
        """节点执行入口: value 广播到所有被选中组的输出, 其余组输出 None。

        参数:
            total (int): 输出组数 (1~MAX_GROUPS, 非法值回退 2);
            selection (str): 多选下拉值, 逗号分隔的选中组号 (如 "1,3");
            **kwargs: value 单一输入 (未连线时键不存在, 取 None)。

        返回:
            tuple[Any, ...]: 长度 MAX_GROUPS, 第 i 个 = i<=total 且 i 在选中集合时的 value, 否则 None。
        """
        total = _clamp_total(total)
        selected = _parse_selection(selection)
        value = kwargs.get("value")
        out = []
        for i in range(1, MAX_GROUPS + 1):
            out.append(value if i <= total and i in selected else None)
        return tuple(out)


NODE_CLASS_MAPPINGS = {
    "FallingTSOneToMany": FallingTSOneToManyNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSOneToMany": "FallingTS 一对多下拉选择 (total组)",
}
