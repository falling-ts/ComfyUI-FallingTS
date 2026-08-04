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


class AnyType(str):
    """ComfyUI 通配类型: 与任何类型都相等, 用于任意数据透传 (同 proceed 节点)。"""

    def __ne__(self, _: object) -> bool:
        return False


ANY = AnyType("*")


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


class _FlexibleInputs(dict):
    """接受前端按 input_count 动态添加的任意输入。

    any_1..any_N 视为任意类型 (ANY), enable_1..enable_N 视为 BOOLEAN;
    ComfyUI 校验/执行时通过 __contains__/__getitem__ 接受这些动态输入。
    """

    def __getitem__(self, key):
        if str(key).startswith("enable_"):
            return ("BOOLEAN",)
        return (ANY,)

    def __contains__(self, key):
        return True


class FallingTSLatentRouterNode:
    """通用多路路由: 平级输入对 (enable_i, any_i), 只有 enable=true 的那组数据输出。

    设计目的: 替代嵌套 Switch。any_i 为任意类型 (参考 proceed 的 AnyType),
    可以路由 Latent / 模型 / 条件 / 图像 / 字符串等任何数据, 输出类型同样是任意。
    加 items 只需增加输入对 (前端 input_count 控制), 不需要改动连接结构。
    约定: 全局有且仅有一组 enable=true; 若没有则抛错提示。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "input_count": (
                    "INT",
                    {
                        "default": 2,
                        "min": 1,
                        "max": 100,
                        "step": 1,
                        "tooltip": "输入对数量 (每对 = enable_i + latent_i), 前端会自动增删输入槽",
                    },
                ),
            },
            "optional": _FlexibleInputs(),
        }

    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("any",)
    FUNCTION = "route"
    CATEGORY = "FallingTS/工具"

    def route(self, input_count: int, **kwargs):
        for i in range(1, int(input_count) + 1):
            enable = kwargs.get(f"enable_{i}")
            data = kwargs.get(f"any_{i}")
            if enable is True and data is not None:
                return (data,)
        raise ValueError(
            "FallingTS 通用路由: 没有任何一组输入满足 enable=true 且提供了数据, "
            "请检查下拉选择是否生效、比较节点是否连接正确。"
        )


NODE_CLASS_MAPPINGS = {
    "FallingTSSelector": FallingTSSelectorNode,
    "FallingTSLatentRouter": FallingTSLatentRouterNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSSelector": "FallingTS 下拉选择器",
    "FallingTSLatentRouter": "下拉选择路由",
}
