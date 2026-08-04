# comfy-desktop-plugins
# 自定义视频生成节点插件 - 通过 Volcengine API 接入 Seedance 2.0
#
# 加载方式:
#   1. 目录链接到 custom_nodes/comfy_desktop_plugins/
#   2. 在 main.py 中: import comfy_desktop_plugins.plugin; plugin.inject()

import os
import sys

# 前端扩展目录:web/ 下的 JS 会被 ComfyUI 前端自动加载(通过 /extensions 接口)
WEB_DIRECTORY = "./web"

# 将插件目录加入 Python 路径, 确保绝对导入可工作
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from plugin import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, inject, comfy_entrypoint
from seedance.nodes import (
    Seedance2FirstLastFrameNode,
    Seedance2ReferenceNode,
)
from proceed.nodes import FallingTSContinueNode
from selector.nodes import FallingTSSelectorNode, FallingTSLatentRouterNode

__all__ = [
    "WEB_DIRECTORY",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "inject",
    "comfy_entrypoint",
    "Seedance2FirstLastFrameNode",
    "Seedance2ReferenceNode",
    "FallingTSContinueNode",
    "FallingTSSelectorNode",
    "FallingTSLatentRouterNode",
]
