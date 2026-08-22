# selector/nodes.py
"""FallingTS 多对一选择 (多组切换, 参考分组开关的 total 范式):
items 组名列表(英文逗号分隔) + total 组数(最少 1) + selection 下拉选组名;
左侧输入端口 = 组数 × 组名数量 (第 1 组的组名输入在前, 第 2 组在后, 依此类推),
下拉选一个组名, 右侧每组的 选中值 输出各自该组名的输入值。

行为:
- total 为组数 (最少 1, 最多 MAX_GROUPS); 组名列表有 M 个组名时,
  左侧共 total × M 个输入端口 (最多 MAX_INPUTS): 第 i 组 = 每个组名一个输入, 端口标签为组名;
- selection 下拉选中第 k 个组名 (索引 0 起): 第 i 组的 selected_value_i 输出第 i 组中
  该组名对应的输入值, 未连线时 None; 未选中的输入标记 lazy, 上游不执行;
- 右侧顶部固定 2 个输出: selected (选中项, 选中组名的文本) + index (选中组名的索引, 从 0 起),
  其后每组的 选中值 selected_value_i (ANY) 依次堆叠, 前端按 total 显隐;
- selection 失配(旧工作流/手动改动)回退第一组。
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


# 最多组数 (组数 total 的上限)
MAX_GROUPS = 50

# 最多输入端口数 (组数 × 组名数量 的上限, 与分组开关同一范式)
MAX_INPUTS = 50

# 哨兵: 区分"该输入根本没连线"与"连了线但上游未求值"
MISSING = object()


class FallingTSSelectorNode:
    """多对一选择节点: total 组数(最少 1) × items 组名数量 动态展开左侧 input1..inputN 输入端口
    (第 1 组的组名输入在前, 第 2 组在后), 下拉选一个组名, 右侧各组 选中值 输出各自该组名的输入值,
    顶部固定输出 选中项 (选中组名文本) 与 索引 (选中组名索引, 从 0 起); 未选中的输入标记 lazy, 上游不执行。

    行为:
    - items (英文逗号分隔组名) 提供各输入端口标签与下拉选项 (如 "右侧提示词,后面提示词,左侧提示词"),
      端口内部名称仍为 inputN 用于定位;
    - 左侧第 i 组 = input[(i-1)×M+1 .. i×M] (M = 组名数量), 端口标签循环为组名列表内容;
    - selection 选中第 k 个组名 -> 第 i 组的 selected_value_i = 第 i 组中该组名的输入值,
      未连线时 None, 未选中的分支不会加入执行列表 —— "没有选择的不输出/不执行";
    - 右侧: selected (选中项, STRING) / index (索引, INT) 固定在最上方,
      其后 selected_value_1..selected_value_N (每组的 选中值, ANY) 依次堆叠。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".items: 逗号分隔的组名列表, 每个组名在每组各展开一个输入端口 (前端联动);
            - "required".total: 组数 (INT, 最少 1, 最多 MAX_GROUPS),
              左侧输入端口数 = 组数 × 组名数量, 前端按此动态增删端口;
            - "required".selection: 下拉选组名, 选项为动态列表(前端 selector.js 联动), 默认空;
            - "optional".input1..inputMAX_INPUTS: 组名数据端口 (ANY), 全部标记 lazy=True,
              只有选中组名对应的各组输入会被 check_lazy_status 拉取执行。
        """
        optional = {}
        for i in range(1, MAX_INPUTS + 1):
            optional[f"input{i}"] = (
                "*",
                {
                    "lazy": True,
                    "tooltip": f"组名输入 {i} (组数 × 组名数量, 第 1 组在前第 2 组在后), 选中组名对应的那几个被执行",
                },
            )
        return {
            "required": {
                "items": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "用英文逗号分隔的组名列表 (如: 右侧提示词,后面提示词,左侧提示词); 每个组名在每组各展开一个输入端口, 端口标签为组名",
                    },
                ),
                "total": (
                    "INT",
                    {
                        "default": 2,
                        "min": 1,
                        "max": MAX_GROUPS,
                        "tooltip": f"组数 (最少 1, 最多 {MAX_GROUPS}), 每组 = 每个组名一个输入 + 一个 选中值 输出, 左侧输入 = 组数 × 组名数量",
                    },
                ),
                "selection": (
                    [],
                    {
                        "default": "",
                        "tooltip": "下拉选择哪个组名 (选项由组名列表实时生成), 各组 选中值 输出各自该组名的输入值",
                    },
                ),
            },
            "optional": optional,
        }

    # 输出槽位: 前 2 个固定 selected(选中项)/index(索引), 其后 selected_value_1..selected_value_N
    # (每组的 选中值) 按 total 追加; 前端增删只动尾部, 已有连线的槽位永不漂移。
    RETURN_TYPES = ("STRING", "INT") + ("*",) * MAX_GROUPS
    RETURN_NAMES = ("selected", "index") + tuple(f"selected_value_{i}" for i in range(1, MAX_GROUPS + 1))
    OUTPUT_TOOLTIPS = (
        (
            "选中项: 选中组名的文本 (STRING, 与下拉框显示一致)",
            "索引: 选中组名在组名列表中的索引, 从 0 开始 (INT)",
        )
        + tuple(f"第 {i} 组 选中值 (ANY): 第 {i} 组中选中组名对应的输入值, 未连线为 None" for i in range(1, MAX_GROUPS + 1))
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"
    DESCRIPTION = (
        "多对一选择 (多组切换, 参考分组开关): items 逗号分隔组名, total 组数(最少 1), "
        "左侧输入 = 组数 × 组名数量 (第1组在前第2组在后), 下拉选一个组名, "
        "右侧各组 选中值 输出各自该组名的输入值, 顶部固定 选中项/索引, 未选中的分支 lazy 不执行。"
    )
    SEARCH_ALIASES = ["多对一", "多选一", "选择", "切换", "switch", "路由", "items", "下拉", "组数", "多组"]

    @classmethod
    def IS_CHANGED(cls, items: str = "", total: int = 2, selection: str = "", **kwargs):
        """缓存失效签名: 组名列表、组数或选中组名变化时重新执行 (动态输入值变化由引擎依赖机制处理)。"""
        return (items, total, selection)

    @classmethod
    def VALIDATE_INPUTS(cls, items: str = "", total: int = 2, selection: str = "", input_types=None, **kwargs) -> bool:
        """输入校验: 动态下拉选项由 items 实时生成, 后端静态选项表为空, 恒通过 (execute 内有失配回退)。"""
        return True

    @staticmethod
    def _resolve_index(options: list[str], selection: str) -> int:
        """选中组名 -> 索引: 按选中项匹配, 失配(旧工作流/手动改动)回退 0。

        参数:
            options (list[str]): 组名列表(调用方已保证非空);
            selection (str): 下拉选中的组名。

        返回:
            int: 0 ~ len(options)-1 的组名索引。
        """
        if selection in options:
            return options.index(selection)
        return 0

    @staticmethod
    def _clamp_total(total) -> int:
        """组数钳位到 [1, MAX_GROUPS], 非法值回退默认 2。"""
        try:
            t = int(total)
        except (TypeError, ValueError):
            t = 2
        return min(MAX_GROUPS, max(1, t))

    def check_lazy_status(self, items: str = "", total: int = 2, selection: str = "", **kwargs) -> list[str]:
        """lazy 输入门控: 只请求选中组名在各组对应的输入, 未选中的分支不执行。

        机制 (ComfyUI 执行引擎):
        1. 所有 inputN 声明 lazy=True, 构建执行列表时不会沿这些边向上游遍历;
        2. 节点执行前引擎调本方法, 返回的输入名若尚未求值才会 make_input_strong_link 拉上游;
        3. 只返回选中组名对应的各组输入 -> 只有这些分支被求值, 其余分支 (即使连了线) 不执行。

        参数:
            items (str): 逗号分隔的组名列表;
            total (int): 组数;
            selection (str): 下拉选中的组名;
            **kwargs: 各 inputN 输入值 (未连线的键不存在)。

        返回:
            list[str]: 需要拉取上游的输入名, 为各组中选中组名对应的 [inputN...] 或 []。
        """
        options = _split_items(items)
        if not options:
            return []
        total = self._clamp_total(total)
        k = self._resolve_index(options, selection)
        need = []
        for i in range(1, total + 1):
            name = f"input{(i - 1) * len(options) + k + 1}"
            if kwargs.get(name, MISSING) is not MISSING:
                need.append(name)
        return need

    def execute(self, items: str = "", total: int = 2, selection: str = "", **kwargs):
        """节点执行入口: 各组 选中值 = 各组中选中组名的输入值, 附选中项文本与索引。

        参数:
            items (str): 逗号分隔的组名列表;
            total (int): 组数;
            selection (str): 下拉选中的组名;
            **kwargs: 各 inputN 输入值 (未连线/未求值时键不存在或为 None)。

        返回:
            tuple: 前 2 个为 (selected 选中组名文本, index 选中组名索引, 从 0 起),
            其后 MAX_GROUPS 个为各组 选中值 selected_value_i (第 i 组中选中组名的输入值,
            组数之外的组为 None); 未连线时值为 None; 列表空/失配时回退第一组名。
        """
        options = _split_items(items)
        total = self._clamp_total(total)
        k = self._resolve_index(options, selection)
        vals = []
        for i in range(1, MAX_GROUPS + 1):
            if i > total or not options:
                vals.append(None)
                continue
            v = kwargs.get(f"input{(i - 1) * len(options) + k + 1}", MISSING)
            vals.append(None if v is MISSING else v)
        selected_text = options[k] if k < len(options) else ""
        return (selected_text, k, *vals)


NODE_CLASS_MAPPINGS = {
    "FallingTSSelector": FallingTSSelectorNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSSelector": "FallingTS 多对一选择",
}
