# comfy-desktop-plugins 入口
# 支持两种加载方式:
#   1. 通过 custom_nodes/ 自动加载 (检测 NODE_CLASS_MAPPINGS)
#   2. 通过 main.py 一行 import 手动注入

from __future__ import annotations

import logging

from comfy_api.latest import IO
from comfy_api.latest._io import ComfyExtension

from .nodes.seedance import (
    Seedance2TextToVideoNode,
    Seedance2ImageToVideoNode,
    Seedance2FirstLastFrameNode,
    Seedance2ReferenceNode,
)

logger = logging.getLogger(__name__)

# ─── V1 节点注册表 (支持 custom_nodes/ 自动加载) ──────

NODE_CLASS_MAPPINGS: dict[str, type[IO.ComfyNode]] = {
    "Seedance2TextToVideo": Seedance2TextToVideoNode,
    "Seedance2ImageToVideo": Seedance2ImageToVideoNode,
    "Seedance2FirstLastFrame": Seedance2FirstLastFrameNode,
    "Seedance2Reference": Seedance2ReferenceNode,
}

NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {
    "Seedance2TextToVideo": "Seedance 2.0 Text to Video",
    "Seedance2ImageToVideo": "Seedance 2.0 Image to Video",
    "Seedance2FirstLastFrame": "Seedance 2.0 First-Last-Frame to Video",
    "Seedance2Reference": "Seedance 2.0 Reference to Video",
}

# ─── V3 ComfyExtension (支持 comfy_entrypoint 注册) ─────

class DesktopPluginsExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[IO.ComfyNode]]:
        return list(NODE_CLASS_MAPPINGS.values())


async def comfy_entrypoint() -> DesktopPluginsExtension:
    """V3 扩展入口点, 被 load_custom_node 检测到后调用。"""
    return DesktopPluginsExtension()


def inject() -> None:
    """手动注入函数: 在 main.py 中调用 import plugin; plugin.inject()"""
    import nodes as comfy_nodes

    registered = 0
    for node_id, node_cls in NODE_CLASS_MAPPINGS.items():
        if node_id not in comfy_nodes.NODE_CLASS_MAPPINGS:
            comfy_nodes.NODE_CLASS_MAPPINGS[node_id] = node_cls
            node_cls.RELATIVE_PYTHON_MODULE = "comfy_desktop_plugins"
            registered += 1

    for node_id, display_name in NODE_DISPLAY_NAME_MAPPINGS.items():
        if node_id not in comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS:
            comfy_nodes.NODE_DISPLAY_NAME_MAPPINGS[node_id] = display_name

    logger.info("comfy-desktop-plugins injected: %d nodes registered", registered)
