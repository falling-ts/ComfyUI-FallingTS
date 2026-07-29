# comfy-desktop-plugins
# 自定义视频生成节点插件 - 通过 Volcengine API 接入 Seedance 2.0
#
# 加载方式:
#   1. 自动: 符号链接到 Default/ComfyUI/custom_nodes/comfy-desktop-plugins/
#   2. 自动: 复制到 Default/ComfyUI/custom_nodes/comfy_desktop_plugins/
#   3. 手动: 在 main.py 中添加:
#        import comfy_desktop_plugins.plugin
#        comfy_desktop_plugins.plugin.inject()

from .plugin import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, inject, comfy_entrypoint
from .nodes.seedance import (
    Seedance2TextToVideoNode,
    Seedance2ImageToVideoNode,
    Seedance2FirstLastFrameNode,
    Seedance2ReferenceNode,
)

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "inject",
    "comfy_entrypoint",
    "Seedance2TextToVideoNode",
    "Seedance2ImageToVideoNode",
    "Seedance2FirstLastFrameNode",
    "Seedance2ReferenceNode",
]
