# comfy-desktop-plugins 入口
# 支持两种加载方式:
#   1. 通过 custom_nodes/ 自动加载 (检测 NODE_CLASS_MAPPINGS)
#   2. 通过 main.py 一行 import 手动注入

from __future__ import annotations

import logging

from comfy_api.latest import IO
from comfy_api.latest import ComfyExtension

from seedance.nodes import (
    Seedance2FirstLastFrameNode,
    Seedance2ReferenceNode,
)
from proceed.nodes import FallingTSContinueNode, FallingTSResolutionNode
from selector.nodes import FallingTSSelectorNode, FallingTSLatentRouterNode

logger = logging.getLogger(__name__)

# ─── V1 节点注册表 (支持 custom_nodes/ 自动加载) ──────

NODE_CLASS_MAPPINGS: dict[str, type[IO.ComfyNode]] = {
    "Seedance2FirstLastFrame": Seedance2FirstLastFrameNode,
    "Seedance2Reference": Seedance2ReferenceNode,
    "FallingTSContinue": FallingTSContinueNode,
    "FallingTSResolution": FallingTSResolutionNode,
    "FallingTSSelector": FallingTSSelectorNode,
    "FallingTSLatentRouter": FallingTSLatentRouterNode,
}

NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {
    "FallingTSSelector": "FallingTS 下拉选择器",
    "FallingTSLatentRouter": "FallingTS 通用路由",
    "FallingTSResolution": "FallingTS 分辨率选择",
    "Seedance2FirstLastFrame": "Seedance 2.0 首尾帧生视频",
    "Seedance2Reference": "Seedance 2.0 多模态参考生视频",
    "FallingTSContinue": "FallingTS 继续节点",
}

# ─── V3 ComfyExtension (支持 comfy_entrypoint 注册) ─────

class DesktopPluginsExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[IO.ComfyNode]]:
        # 仅 V3 IO.ComfyNode 走扩展注册; legacy 节点由 NODE_CLASS_MAPPINGS 直接加载
        return [
            cls
            for cls in NODE_CLASS_MAPPINGS.values()
            if isinstance(cls, type) and issubclass(cls, IO.ComfyNode)
        ]


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
