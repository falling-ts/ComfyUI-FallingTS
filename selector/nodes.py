# selector/nodes.py
"""FallingTS 下拉选择器: 文本输入框(英文逗号分隔选项) + 下拉框选择, 输出选中项在选项列表中的索引。

行为:
- items 文本框里用英文逗号写选项列表, 例如 "4步加速,20步标准,30步精修";
- 下拉框 (selection) 会跟随 items 内容实时更新选项 (前端 web/js/selector.js 联动);
- 下拉选择哪个 item, 节点就输出该 item 在列表中的索引 (从 0 开始), 供下游按索引路由/查表;
- selection 值不在 items 列表时 (旧工作流/手动改动), 回退到第一项, 不报错。
"""

from __future__ import annotations

DEFAULT_ITEMS = ""


def _split_items(items: str) -> list[str]:
    """按英文逗号拆分并去除首尾空白, 忽略空项。

    参数:
        items (str): 逗号分隔的选项文本, 可为空字符串或 None。

    返回:
        list[str]: 去空白后的非空选项列表。
    """
    return [s.strip() for s in (items or "").split(",") if s.strip()]


class FallingTSSelectorNode:
    """文本+下拉选择器: 逗号分隔选项写在文本框, 下拉选哪个, 就输出它在列表中的索引。

    items 默认空, selection 默认空下拉; 前端在 items 变化时实时同步下拉选项。
    输出: index: 选中项在 items 列表中的索引, 从 0 开始 (INT)。
    设计说明: 文本本身仅供人查看 (下拉框内显示), 机器侧用索引标识最精确;
    映射表 (索引 -> 名称/提示词/比例) 集中放在下游加载器中, 避免字符串比较路由。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".items: 选项列表文本框(英文逗号分隔), 下拉选项由此实时生成;
            - "required".selection: 下拉选择项, 类型为动态列表(前端 selector.js 联动), 默认空。
        """
        return {
            "required": {
                "items": (
                    "STRING",
                    {
                        "default": DEFAULT_ITEMS,
                        "multiline": False,
                        "tooltip": "用英文逗号分隔的选项列表 (如: 9:16,16:9), 下拉框会跟随此内容更新",
                    },
                ),
                "selection": (
                    [],
                    {
                        "default": "",
                        "tooltip": "下拉选择项 (选项由上方 items 文本框实时生成)",
                    },
                ),
            },
        }

    RETURN_TYPES = ("INT", "STRING")
    RETURN_NAMES = ("index", "selected")
    OUTPUT_TOOLTIPS = (
        "选中项在 items 列表中的索引, 从 0 开始 (INT)",
        "选中项的选项文本 (STRING), 与下拉框当前显示一致, 可用于后续保存/记录",
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"

    @classmethod
    def IS_CHANGED(cls, items: str, selection: str):
        """缓存失效签名: 选项列表或选中项变化时该节点判定为已变化而重新执行。

        参数:
            items (str): 选项列表文本;
            selection (str): 当前选中项。

        返回:
            tuple[str, str]: (items, selection) 作为 ComfyUI 缓存键的一部分。
        """
        return (items, selection)

    @classmethod
    def VALIDATE_INPUTS(cls, items: str, selection: str, input_types) -> bool:
        """输入校验: 动态下拉的选项由 items 实时生成, 后端静态选项表为空,
        跳过默认 value_not_in_list 校验(execute 内已有失配回退逻辑)。

        参数:
            items (str): 选项列表文本;
            selection (str): 当前选中项;
            input_types (dict): 节点输入类型表(引擎传入)。

        返回:
            bool: 恒为 True(校验始终通过, 实际校验在 execute 内做)。
        """
        return True

    def execute(self, items: str, selection: str):
        """节点执行入口: 输出选中项在选项列表中的索引与文本。

        逻辑: selection 在选项列表里 → 输出其索引与文本; 失配(旧工作流/手动改动/列表空)
        则回退到第 0 项(索引 0, 文本为首项或空)。

        参数:
            items (str): 逗号分隔的选项列表文本;
            selection (str): 下拉框选中的选项文本。

        返回:
            tuple[int, str]: (选中项索引, 选中项文本); 失配时回退 (0, 首项或 "")。
        """
        options = _split_items(items)
        if selection in options:
            return (options.index(selection), selection)
        # 旧工作流或手动改动导致 selection 不在列表里 / 列表为空: 回退索引 0
        return (0, options[0] if options else "")


# 多对一选择: 最多同时展开的输入端口数 (与 switch 的 MAX_GROUPS 同一范式, 前端按 items 增删)
MAX_INPUTS = 50

# 哨兵: 区分"该输入根本没连线"与"连了线但上游未求值"
MISSING = object()


class FallingTSSelectOneNode:
    """多对一选择节点: items 文本框(英文逗号分隔)实时展开左侧 input1..inputN 输入端口,
    下拉选择哪一项, 就从右侧 selected_value 输出哪一路, 并附带选中项的选项文本 (selected) 与列表索引 (index); 未选中的输入标记 lazy, 上游不执行。

    行为:
    - items 里每写一个选项(逗号分隔), 前端 (web/js/select_one.js) 就展开一个输入端口,
      端口标签显示该项的实际内容 (如 "右侧提示词"), 内部名称仍为 inputN 用于定位;
    - 下拉 (selection) 选中第 k 项 -> 只拉取并输出 input(k+1) 的值 (check_lazy_status 只请求选中项),
      未选中的分支不会加入执行列表 —— "没有选择的不输出/不执行";
    - 三个输出: selected_value(选中的那一项输入值, ANY) / selected(选中项的选项文本, STRING) / index(选中项在 items 列表中的索引, 从 0 起, INT);
    - 选中项未连线时输出 None (不报错); selection 失配(旧工作流/手动改动)回退第一项, 与下拉选择器一致。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".items: 逗号分隔的输入项列表, 每项展开为一个输入端口 (前端联动);
            - "required".selection: 下拉选择项, 类型为动态列表(前端 select_one.js 联动), 默认空;
            - "optional".input1..inputMAX_INPUTS: 各输入项数据端口 (ANY), 全部标记 lazy=True,
              只有选中的那一项会被 check_lazy_status 拉取执行。
        """
        optional = {}
        for i in range(1, MAX_INPUTS + 1):
            optional[f"input{i}"] = (
                "*",
                {
                    "lazy": True,
                    "tooltip": f"第 {i} 项输入 (由 items 展开, 只执行下拉选中的那一项)",
                },
            )
        return {
            "required": {
                "items": (
                    "STRING",
                    {
                        "default": DEFAULT_ITEMS,
                        "multiline": False,
                        "tooltip": "用英文逗号分隔的输入项列表 (如: 右侧提示词,后面提示词,左侧提示词,相机交互); 每项在节点左侧展开为一个输入端口",
                    },
                ),
                "selection": (
                    [],
                    {
                        "default": "",
                        "tooltip": "下拉选择要输出的那一项 (选项由 items 文本框实时生成)",
                    },
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("*", "STRING", "INT")
    RETURN_NAMES = ("selected_value", "selected", "index")
    OUTPUT_TOOLTIPS = (
        "选中的那一项输入的值 (ANY, 通常是 STRING); 未选中的项不输出",
        "选中项的选项文本 (STRING, 来自 items 列表, 与下拉框显示一致)",
        "选中项在 items 列表中的索引, 从 0 开始 (INT)",
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"
    DESCRIPTION = (
        "多对一选择 (参考下拉选择器 + ImpactSwitch): items 逗号分隔展开输入端口, "
        "下拉选哪项就从右侧输出哪项(含选中项文本与索引), 未选中的分支 lazy 不执行。"
    )
    SEARCH_ALIASES = ["多对一", "多选一", "选择", "切换", "switch", "路由", "items", "下拉"]

    @classmethod
    def IS_CHANGED(cls, items: str = "", selection: str = "", **kwargs):
        """缓存失效签名: 选项列表或选中项变化时重新执行 (动态输入值变化由引擎依赖机制处理)。"""
        return (items, selection)

    @classmethod
    def VALIDATE_INPUTS(cls, items: str = "", selection: str = "", input_types=None, **kwargs) -> bool:
        """输入校验: 动态下拉选项由 items 实时生成, 后端静态选项表为空, 恒通过 (execute 内有失配回退)。"""
        return True

    @staticmethod
    def _resolve_index(options: list[str], selection: str) -> int:
        """选中项 -> 索引; 失配回退 0 (与 FallingTSSelector 一致)。"""
        if selection in options:
            return options.index(selection)
        return 0

    def check_lazy_status(self, items: str = "", selection: str = "", **kwargs) -> list[str]:
        """lazy 输入门控: 只请求选中项对应的输入, 未选中的分支不执行。

        机制 (ComfyUI 执行引擎):
        1. 所有 inputN 声明 lazy=True, 构建执行列表时不会沿这些边向上游遍历;
        2. 节点执行前引擎调本方法, 返回的输入名若尚未求值才会 make_input_strong_link 拉上游;
        3. 只返回选中项 -> 只有选中分支被求值, 其余分支 (即使连了线) 不执行。

        参数:
            items (str): 逗号分隔的输入项列表;
            selection (str): 下拉选中的项;
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
            return []  # 选中项没连线: 无上游可拉
        return [input_name]

    def execute(self, items: str = "", selection: str = "", **kwargs):
        """节点执行入口: 输出选中项对应的输入值、选项文本与索引。

        参数:
            items (str): 逗号分隔的输入项列表;
            selection (str): 下拉选中的项;
            **kwargs: 各 inputN 输入值 (未连线/未求值时键不存在或为 None)。

        返回:
            tuple[Any, str, int]: (选中项输入值, 选中项选项文本, 选中项索引);
            选中项未连线时输入值为 None; 列表空/失配时回退第一项。
        """
        options = _split_items(items)
        idx = self._resolve_index(options, selection)
        input_name = f"input{idx + 1}"
        value = kwargs.get(input_name, MISSING)
        if value is MISSING:
            value = None  # 选中项未连线: 输出 None, 不报错
        selected_text = options[idx] if options else ""  # 选项文本(与下拉框一致)
        return (value, selected_text, idx)


NODE_CLASS_MAPPINGS = {
    "FallingTSSelector": FallingTSSelectorNode,
    "FallingTSSelectOne": FallingTSSelectOneNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSSelector": "FallingTS 下拉选择器",
    "FallingTSSelectOne": "FallingTS 多对一选择",
}
