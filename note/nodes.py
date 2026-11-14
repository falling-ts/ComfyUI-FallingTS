# note/nodes.py
"""FallingTS 笔记节点: 官方 Markdown Note 的可复制版。

与官方 `MarkdownNote` 相比只多做一件事 —— 节点右上角有一个复制按钮
(前端 `web/js/note.js` 注入), 点一下把整段 markdown 源码写进
**浏览器所在那台电脑**的剪贴板, 也就是"访问服务的电脑",
而不是跑 ComfyUI 的服务器。

## 为什么官方 Note 在后端查不到

官方 `Note` / `MarkdownNote` 是**纯前端虚拟节点**: 前端 core 里直接
`LiteGraph.registerNodeType('MarkdownNote', ...)`, 不进 `/object_info`。
它们带有 `isVirtualNode = true`, 于是 `graphToPrompt()` 构建 prompt 时
`if (e.isVirtualNode) continue` 直接跳过 —— 不进 prompt、不参与执行、
不占校验。

## 本节点为什么"后端也注册一份"

纯前端注册的节点不在 `/object_info` 里, 新版前端的节点库面板/搜索
拿不到它, 只能在画布上右键的 LiteGraph 搜索里找到; 工作流传给别人
时也更容易被判成"缺失节点"。所以这里反过来做:

- **后端注册** ⇒ `/object_info` 有定义、节点面板能搜到、存档不报缺失;
- **前端标记虚拟** ⇒ `onNodeCreated` 里设 `isVirtualNode = true`,
  行为与官方完全一致, 不进 prompt、不执行。

节点的文本控件不在这里声明, 由前端用 `ComfyWidgets.MARKDOWN` 现场添加
(与官方 `MarkdownNoteNode` 同一套渲染), 因此本类只有 execute 空壳,
供"万一进了 prompt"时兜底 —— 正常情况下它永远不会被调用。
"""

from __future__ import annotations


class FallingTSNoteNode:
    """Markdown 笔记: 画布上贴说明文字, 右上角可一键复制。

    无输入无输出。文本控件由前端 `ComfyWidgets.MARKDOWN` 添加(官方同款
    tiptap 渲染, 支持标题/表格/代码块), 前端同时把节点标记为虚拟节点,
    使它不进 prompt、不参与执行。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入: 空。

        文本控件**故意不由后端声明** —— 后端只能声明普通 `STRING`(单行或
        multiline 纯文本框), 而官方的 markdown 渲染是前端 widget 构造器
        (`ComfyWidgets.MARKDOWN`) 提供的。改成前端添加才能拿到同款渲染。

        返回:
            dict: 空的 "required"/"optional", 表示本节点没有执行期输入。
        """
        return {"required": {}, "optional": {}}

    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "execute"
    CATEGORY = "FallingTS"
    DESCRIPTION = (
        "在画布上贴一段 Markdown 说明(支持标题/表格/代码块), "
        "节点右上角的复制按钮可把原文一键复制到浏览器所在电脑的剪贴板。"
    )
    SEARCH_ALIASES = ["note", "笔记", "注释", "说明", "markdown", "备注", "文本"]

    def execute(self) -> dict:
        """执行入口: 什么都不做。

        本节点被前端标记为虚拟节点(`isVirtualNode`), `graphToPrompt()` 不会把
        它放进 prompt, 所以正常情况下永远不会被调用。这里返回空 dict 只是
        兜底: 万一前端扩展没加载(例如手写 API 提交), 节点进了 prompt 也能
        照常通过校验与执行, 不让整张图失败。

        返回:
            dict: 空字典(无输出)。
        """
        return {}


NODE_CLASS_MAPPINGS = {
    "FallingTSNote": FallingTSNoteNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSNote": "FallingTS 笔记 (Markdown 可复制)",
}
