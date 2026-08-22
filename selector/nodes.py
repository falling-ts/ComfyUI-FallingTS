# selector/nodes.py
"""FallingTS 多对一选择 (多组切换, 参考分组开关的 total 范式):
items 文本框(英文逗号分隔组名) + total 组数(最少 1) + selection 下拉选组;
每组 = input_i 输入 + output_i 输出, 前端 (web/js/selector.js) 按 total 动态增删输入输出端口。

行为:
- total 为组数 (最少 1, 最多 MAX_GROUPS); 第 i 组 = input_i (ANY) 输入 + output_i (ANY) 输出;
- 下拉 (selection) 选中的第 k 组导通: output_k = input_k, 其余组输出 None;
- 只拉取选中组的输入 (check_lazy_status), 未选中的分支不会加入执行列表 —— "没有选择的不输出/不执行";
- 组名 (items 逗号分隔) 是各组的端口标签与下拉选项 (前端联动);
- 附带三个输出: selected_value(选中组输入值, ANY) / selected(选中组选项文本, STRING) / index(选中组索引, 从 0 起, INT);
- 选中组未连线时输出 None (不报错); selection 失配(旧工作流/手动改动)回退第一组。
"""

from __future__ import annotations


def _split_items(items: str) -> list[str]:
    """按英文逗号拆分并去除首尾空白, 忽略空项。

    参数:
        items (str): 逗号分隔的组名文本, 可为空字符串或 None。

    返回:
        list[str]: 去空白后的非空组名列表。
    """
    return [s.strip() for s in (items or "").split(",") if s.strip()]


# 最多组数 (与分组开关同一范式, 前端按 total 增删端口)
MAX_GROUPS = 50

# 哨兵: 区分"该输入根本没连线"与"连了线但上游未求值"
MISSING = object()


class FallingTSSelectorNode:
    """多对一选择节点: total 组数(最少 1)动态展开 input1..inputN 输入端口与 output1..outputN 输出端口,
    下拉选第 k 组, 该组 input_k 导通到 output_k (其余组输出 None), 并附带选中组的选项文本 (selected) 与索引 (index); 未选中的输入标记 lazy, 上游不执行。

    行为:
    - total 变化时前端 (web/js/selector.js) 按分组开关范式动态增删输入/输出端口;
    - items (英文逗号分隔组名) 提供各组端口标签与下拉选项 (如 "右侧提示词,后面提示词,左侧提示词"),
      端口内部名称仍为 inputN / outputN 用于定位;
    - 下拉 (selection) 选中第 k 组 -> 只拉取 input(k) 并导通到 output(k), 其余组输出 None,
      未选中的分支不会加入执行列表 —— "没有选择的不输出/不执行";
    - 选中组未连线时 output_k / selected_value 为 None (不报错); selection 失配(旧工作流/手动改动)回退第一组。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".items: 逗号分隔的组名列表, 每组名作为对应组输入/输出端口标签与下拉选项 (前端联动);
            - "required".total: 组数 (INT, 最少 1, 最多 MAX_GROUPS), 前端按此动态增删输入/输出端口;
            - "required".selection: 下拉选组, 选项为动态列表(前端 selector.js 联动), 默认空;
            - "optional".input1..inputMAX_GROUPS: 各组数据端口 (ANY), 全部标记 lazy=True,
              只有选中的那一组会被 check_lazy_status 拉取执行。
        """
        optional = {}
        for i in range(1, MAX_GROUPS + 1):
            optional[f"input{i}"] = (
                "*",
                {
                    "lazy": True,
                    "tooltip": f"第 {i} 组输入 (ANY), 选中该组时导通到第 {i} 组输出",
                },
            )
        return {
            "required": {
                "items": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "用英文逗号分隔的组名列表 (如: 右侧提示词,后面提示词,左侧提示词); 组名作为各组输入/输出端口标签与下拉选项",
                    },
                ),
                "total": (
                    "INT",
                    {
                        "default": 2,
                        "min": 1,
                        "max": MAX_GROUPS,
                        "tooltip": f"组数 (最少 1, 最多 {MAX_GROUPS}), 每组 = 输入 + 输出, 前端按此动态增删端口",
                    },
                ),
                "selection": (
                    [],
                    {
                        "default": "",
                        "tooltip": "下拉选择第几组导通 (选项由 items 文本框实时生成)",
                    },
                ),
            },
            "optional": optional,
        }

    # 输出槽位: 前 3 个固定 (selected_value/selected/index, 与旧版槽位一致, 旧工作流连线不漂移),
    # 其后 output1..outputN 按 total 追加 (组输出), 前端增删只动尾部, 槽位稳定。
    RETURN_TYPES = ("*", "STRING", "INT") + ("*",) * MAX_GROUPS
    RETURN_NAMES = ("selected_value", "selected", "index") + tuple(f"output_{i}" for i in range(1, MAX_GROUPS + 1))
    OUTPUT_TOOLTIPS = (
        (
            "选中组输入的值 (ANY, 通常是 STRING), 与选中组的输出一致",
            "选中组的组名文本 (STRING, 来自 items 列表, 与下拉框显示一致)",
            "选中组在 items 列表中的索引, 从 0 开始 (INT)",
        )
        + tuple(f"第 {i} 组输出 (ANY): 选中第 {i} 组时导通其输入, 未选中为 None" for i in range(1, MAX_GROUPS + 1))
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"
    DESCRIPTION = (
        "多对一选择 (多组切换, 参考分组开关): items 逗号分隔组名, total 组数(最少 1)动态增删输入输出端口, "
        "下拉选第几组, 该组输入导通到该组输出, 未选中的组为 None 且 lazy 不执行。"
    )
    SEARCH_ALIASES = ["多对一", "多选一", "选择", "切换", "switch", "路由", "items", "下拉", "组数", "多组"]

    @classmethod
    def IS_CHANGED(cls, items: str = "", total: int = 2, selection: str = "", **kwargs):
        """缓存失效签名: 组名列表、组数或选中组变化时重新执行 (动态输入值变化由引擎依赖机制处理)。"""
        return (items, total, selection)

    @classmethod
    def VALIDATE_INPUTS(cls, items: str = "", total: int = 2, selection: str = "", input_types=None, **kwargs) -> bool:
        """输入校验: 动态下拉选项由 items 实时生成, 后端静态选项表为空, 恒通过 (execute 内有失配回退)。"""
        return True

    @staticmethod
    def _resolve_index(options: list[str], selection: str) -> int:
        """选中组 -> 索引: 按选中项匹配, 失配(旧工作流/手动改动)回退 0。

        参数:
            options (list[str]): 组名列表(调用方已保证非空);
            selection (str): 下拉选中的组名。

        返回:
            int: 0 ~ len(options)-1 的组索引。
        """
        if selection in options:
            return options.index(selection)
        return 0

    def check_lazy_status(self, items: str = "", total: int = 2, selection: str = "", **kwargs) -> list[str]:
        """lazy 输入门控: 只请求选中组的输入, 未选中的分支不执行。

        机制 (ComfyUI 执行引擎):
        1. 所有 inputN 声明 lazy=True, 构建执行列表时不会沿这些边向上游遍历;
        2. 节点执行前引擎调本方法, 返回的输入名若尚未求值才会 make_input_strong_link 拉上游;
        3. 只返回选中组 -> 只有选中分支被求值, 其余分支 (即使连了线) 不执行。

        参数:
            items (str): 逗号分隔的组名列表;
            total (int): 组数 (仅前端端口增删用, 不影响选中组定位);
            selection (str): 下拉选中的组名;
            **kwargs: 各 inputN 输入值 (未连线的键不存在)。

        返回:
            list[str]: 需要拉取上游的输入名, 只能是 [f"input{k}"] 或 []。
        """
        options = _split_items(items)
        if not options:
            return []
        idx = self._resolve_index(options, selection)
        input_name = f"input{idx + 1}"
        if kwargs.get(input_name, MISSING) is MISSING:
            return []  # 选中组没连线: 无上游可拉
        return [input_name]

    def execute(self, items: str = "", total: int = 2, selection: str = "", **kwargs):
        """节点执行入口: 选中组导通 (input_k -> output_k), 其余组输出 None, 附选中组文本与索引。

        参数:
            items (str): 逗号分隔的组名列表;
            total (int): 组数 (仅前端端口增删用, 不影响选中组定位);
            selection (str): 下拉选中的组名;
            **kwargs: 各 inputN 输入值 (未连线/未求值时键不存在或为 None)。

        返回:
            tuple: 前 3 个固定为 (selected_value 选中组输入值, selected 选中组组名文本, index 选中组索引, 从 0 起),
            其后 MAX_GROUPS 个为各组输出 (选中组 = 其输入值, 其余 None);
            选中组未连线时值为 None; 列表空/失配时回退第一组。
        """
        options = _split_items(items)
        idx = self._resolve_index(options, selection)
        input_name = f"input{idx + 1}"
        value = kwargs.get(input_name, MISSING)
        if value is MISSING:
            value = None  # 选中组未连线: 输出 None, 不报错
        selected_text = options[idx] if idx < len(options) else ""
        out = [None] * MAX_GROUPS
        if idx < MAX_GROUPS:
            out[idx] = value
        return (value, selected_text, idx, *out)


NODE_CLASS_MAPPINGS = {
    "FallingTSSelector": FallingTSSelectorNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSSelector": "FallingTS 多对一选择",
}
