# selector/nodes.py
"""FallingTS 下拉选择器: 文本输入框(英文逗号分隔选项) + 下拉框选择, 输出选中的选项字符串。

行为:
- items 文本框里用英文逗号写选项列表, 例如 "4步加速,20步标准,30步精修";
- 下拉框 (selection) 会跟随 items 内容实时更新选项 (前端 web/js/selector.js 联动);
- 下拉选择哪个 item, 节点就输出哪个 item 字符串, 进入下一个节点;
- selection 值不在 items 列表时 (旧工作流/手动改动), 回退到第一项, 不报错。
"""

from __future__ import annotations

DEFAULT_ITEMS = ""


def _split_items(items: str) -> list[str]:
    """按英文逗号拆分并去空白, 忽略空项。"""
    return [s.strip() for s in (items or "").split(",") if s.strip()]


class FallingTSSelectorNode:
    """文本+下拉选择器: 逗号分隔选项写在文本框, 下拉选哪个就输出哪个。

    items 默认空, selection 默认空下拉; 前端在 items 变化时实时同步下拉选项。
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

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("selection",)
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"

    @classmethod
    def IS_CHANGED(cls, items: str, selection: str):
        return (items, selection)

    def execute(self, items: str, selection: str):
        options = _split_items(items)
        if selection in options:
            return (selection,)
        # 旧工作流或手动改动导致 selection 不在列表里: 回退第一项; 空列表返回空串
        return (options[0] if options else selection,)


NODE_CLASS_MAPPINGS = {
    "FallingTSSelector": FallingTSSelectorNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSSelector": "FallingTS 下拉选择器",
}
