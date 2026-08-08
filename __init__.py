# comfy-desktop-plugins
# 自定义节点插件:通用工具节点 + 前端增强
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

from importlib import import_module
from plugin import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, inject, comfy_entrypoint
from proceed.nodes import FallingTSContinueNode
from selector.nodes import FallingTSSelectorNode
from table.nodes import FallingTSTableNode
from switch.nodes import FallingTSSwitchNode
from route.nodes import FallingTSRouteNode

# preview-video 目录名含连字符, 不能写 `from preview-video.nodes import`, 需经 importlib 按名加载
PreviewVideoNode = import_module("preview-video.nodes").PreviewVideoNode

__all__ = [
    "WEB_DIRECTORY",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "inject",
    "comfy_entrypoint",
    "FallingTSContinueNode",
    "FallingTSRouteNode",
    "FallingTSSelectorNode",
    "FallingTSTableNode",
    "FallingTSSwitchNode",
    "PreviewVideoNode",
]
