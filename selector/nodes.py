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
    """按英文逗号拆分并去空白, 忽略空项。"""
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
        return (items, selection)

    @classmethod
    def VALIDATE_INPUTS(cls, items: str, selection: str, input_types) -> bool:
        """动态下拉: 选项由 items 实时生成, 后端静态选项表为空,
        跳过默认 value_not_in_list 校验 (execute 内已有回退逻辑)。"""
        return True

    def execute(self, items: str, selection: str):
        options = _split_items(items)
        if selection in options:
            return (options.index(selection), selection)
        # 旧工作流或手动改动导致 selection 不在列表里 / 列表为空: 回退索引 0
        return (0, options[0] if options else "")


NODE_CLASS_MAPPINGS = {
    "FallingTSSelector": FallingTSSelectorNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSSelector": "FallingTS 下拉选择器",
}
