# onemany/nodes.py
"""FallingTS 一对多选择 (total 组, 参考多对一选择/路由节点的 total 组范式):
一个 value 输入 (ANY) 按 selection 广播到 total 组中的若干输出:
- total 为输出组数 (最少 1, 最多 MAX_GROUPS), 前端 (web/js/onemany.js) 按 total 动态增删输出端口;
- items 为组名列表 (英文逗号分隔, 如 "右面,后面,左面"), 与多对一选择的 items 同源, 前端据此
  同步输出端口标签与 selection 下拉选项; 为空时按 组1,组2,... 补全;
- selection 为选中的组名 (英文逗号分隔, 如 "右面" 或 "右面,后面"), 是可连线输入
  (可接多对一选择的 选中项 STRING 输出), 也可在节点上手动多选 (前端下拉, 选项 = 组名);
- 被选中组名的输出 output_i = value 输入值, 未选中组输出 None;
- selection 为空 (未连线未设置) 时默认选中第一组;
- 未连线时 value 为 None, 各组输出均为 None。
"""

from __future__ import annotations

from typing import Any


# 最多组数 (组数 total 的上限, 与多对一选择/路由/分组开关同一范式)
MAX_GROUPS = 50


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


def _group_names(items: Any, total: int) -> list:
    """构建长度 total 的组名列表: 解析 items (逗号分隔), 不足按 组{i} 补全, 超出截断。

    参数:
        items (Any): 逗号分隔的组名文本 (如 "右面,后面,左面"), 可为空/None/列表。
        total (int): 组数 (1~MAX_GROUPS)。

    返回:
        list[str]: 长度 total 的组名列表 (不足补 组{i}, 超出截断)。
    """
    if items is None:
        raw: list = []
    elif isinstance(items, (list, tuple, set)):
        raw = [str(s).strip() for s in items]
    else:
        raw = [s.strip() for s in str(items).split(",")]
    names = [s for s in raw if s]
    for i in range(len(names), total):
        names.append("组" + str(i + 1))
    return names[:total]


def _parse_names(selection: Any) -> set:
    """把逗号分隔的组名文本解析为去重非空组名集合。

    参数:
        selection (Any): 逗号分隔的组名文本 (如 "右面" 或 "右面,后面"), 可为空/None/列表。

    返回:
        set[str]: 有效组名集合; 无有效项时为空集。
    """
    if selection is None:
        return set()
    items = selection if isinstance(selection, (list, tuple, set)) else str(selection).split(",")
    out: set = set()
    for s in items:
        name = str(s).strip()
        if name:
            out.add(name)
    return out


class FallingTSOneToManyNode:
    """一对多下拉选择: total 组输出, 一个 value 输入按 selection (组名, 可连线) 广播到选中组输出。

    后端声明 MAX_GROUPS 个输出 (output_1..output_50), 前端 (web/js/onemany.js)
    按 total 动态增删并按 items 组名标注; selection 为选中的组名 (逗号分隔, 可连线
    接多对一 选中项), 被选中组的输出 = value, 其余为 None。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".total: 输出组数 (INT, 最少 1, 最多 MAX_GROUPS), 前端按此动态增删输出端口;
            - "required".items: 组名列表 (STRING, 逗号分隔, 如 "右面,后面,左面"),
              与多对一选择的 items 同源; 为空时按 组1,组2,... 补全;
            - "required".selection: 选中的组名 (STRING, 逗号分隔, 如 "右面" 或 "右面,后面"),
              可连线输入 (可接多对一 选中项 STRING 输出), 也可节点上手动多选, 被选中组输出 = value;
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
                "items": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "组名列表 (逗号分隔, 如 右面,后面,左面), 与多对一选择 items 同源; 为空时按 组1,组2,... 补全",
                    },
                ),
                "selection": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "选中的组名 (逗号分隔, 如 右面 或 右面,后面), 可连线 (接多对一 选中项); 选中组的输出 = value, 未选中组 None; 为空默认第一组",
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

    # 输出槽位: output_1..output_MAX_GROUPS, 前端按 total 显隐, 按 items 组名标注; 增删只动尾部, 已有连线的槽位永不漂移
    RETURN_TYPES = ("*",) * MAX_GROUPS
    RETURN_NAMES = tuple(f"output_{i}" for i in range(1, MAX_GROUPS + 1))
    OUTPUT_TOOLTIPS = tuple(
        f"第 {i} 组输出 (ANY): 该组组名 (items 第 {i} 个) 在 selection 中时为 value 输入值, 否则 None"
        for i in range(1, MAX_GROUPS + 1)
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"
    DESCRIPTION = (
        "一对多下拉选择 (total组): 一个 value 输入按 selection (选中组名, 逗号分隔, 可连线接多对一 选中项) "
        "广播到选中的若干输出 output_i, 未选中组输出 None; items 组名列表与多对一选择同源; 未连线时各组输出 None。"
    )
    SEARCH_ALIASES = [
        "一对多", "下拉", "多选", "扇出", "广播", "one-to-many", "fanout", "group", "组名", "多组", "total", "items",
    ]

    @classmethod
    def IS_CHANGED(cls, total: int = 2, items: str = "", selection: str = "", **kwargs):
        """缓存失效签名: 组数/组名/选中组名变化时重新执行 (value 为动态输入, 变化由引擎依赖机制处理)。"""
        return (total, items, selection)

    def execute(self, total: int = 2, items: str = "", selection: str = "", **kwargs):
        """节点执行入口: value 广播到所有被选中组名的输出, 其余组输出 None。

        参数:
            total (int): 输出组数 (1~MAX_GROUPS, 非法值回退 2);
            items (str): 组名列表 (逗号分隔), 为空时按 组1,组2,... 补全;
            selection (str): 选中的组名 (逗号分隔, 可连线), 为空时默认选中第一组;
            **kwargs: value 单一输入 (未连线时键不存在, 取 None)。

        返回:
            tuple[Any, ...]: 长度 MAX_GROUPS, 第 i 个 = i<=total 且 items 第 i 个组名在选中集合时的 value, 否则 None。
        """
        total = _clamp_total(total)
        names = _group_names(items, total)
        selected = _parse_names(selection)
        if not selected:
            selected = {names[0]}
        value = kwargs.get("value")
        out = []
        for i in range(1, MAX_GROUPS + 1):
            active = i <= total and names[i - 1] in selected
            out.append(value if active else None)
        return tuple(out)


NODE_CLASS_MAPPINGS = {
    "FallingTSOneToMany": FallingTSOneToManyNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSOneToMany": "FallingTS 一对多选择 (total组)",
}
