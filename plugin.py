# comfy-desktop-plugins 入口
# 支持两种加载方式:
#   1. 通过 custom_nodes/ 自动加载 (检测 NODE_CLASS_MAPPINGS)
#   2. 通过 main.py 一行 import 手动注入

from __future__ import annotations

import logging

import cgroup_memory
import numbered_subdirs

from comfy_api.latest import IO
from comfy_api.latest import ComfyExtension
from importlib import import_module

from proceed.nodes import FallingTSContinueNode
from selector.nodes import FallingTSSelectorNode
from table.nodes import FallingTSTableNode
from switch.nodes import FallingTSSwitchNode
from route.nodes import FallingTSRouteNode
from fanout.nodes import FallingTSFanoutNode
from mdtable.nodes import FallingTSMarkDownTableNode
from fps.nodes import FallingTSFrameRateConvertNode
from composite.nodes import FallingTSImageCompositeNode

# preview-video 目录名含连字符, 不能写 `from preview-video.nodes import`, 需经 importlib 按名加载
PreviewVideoNode = import_module("preview-video.nodes").PreviewVideoNode
# preview-image 目录名同样含连字符, 需经 importlib 按名加载
PreviewImageSaveNode = import_module("preview-image.nodes").PreviewImageSaveNode
# preview-audio 目录名同样含连字符, 需经 importlib 按名加载
PreviewAudioSaveNode = import_module("preview-audio.nodes").PreviewAudioSaveNode
# audio-trim 目录名同样含连字符, 需经 importlib 按名加载(音频截段: 波形选区切多段输出)
AudioTrimNode = import_module("audio-trim.nodes").FallingTSAudioTrimNode
# video-components 目录名同样含连字符, 需经 importlib 按名加载
VideoComponentsNode = import_module("video-components.nodes").FallingTSVideoComponentsNode
# h3-guide 目录名同样含连字符, 需经 importlib 按名加载
H3AddGuideNode = import_module("h3-guide.nodes").FallingTSH3AddGuideNode

logger = logging.getLogger(__name__)

# 容器里 ComfyUI 按宿主全量内存规划缓存会被 cgroup OOM kill, 钳制到 cgroup 上限 (须早于 prompt_worker 算阈值)
cgroup_memory.apply()

# 前端文件列表默认不进子目录, 保存到 output/<工作流名>/ 的产物看不到; 挂 middleware 补上
numbered_subdirs.apply()

# ─── V1 节点注册表 (支持 custom_nodes/ 自动加载) ──────

NODE_CLASS_MAPPINGS: dict[str, type[IO.ComfyNode]] = {
    "FallingTSContinue": FallingTSContinueNode,
    "FallingTSRoute": FallingTSRouteNode,
    "FallingTSFanout": FallingTSFanoutNode,
    "FallingTSSelector": FallingTSSelectorNode,
    "FallingTSTable": FallingTSTableNode,
    "FallingTSSwitch": FallingTSSwitchNode,
    "FallingTSMarkDownTable": FallingTSMarkDownTableNode,
    "FallingTSFrameRateConvert": FallingTSFrameRateConvertNode,
    "FallingTSImageComposite": FallingTSImageCompositeNode,
    "FallingTSVideoComponents": VideoComponentsNode,
    "FallingTSH3AddGuide": H3AddGuideNode,
    "PreviewVideo": PreviewVideoNode,
    "PreviewImageSave": PreviewImageSaveNode,
    "PreviewAudioSave": PreviewAudioSaveNode,
    "FallingTSAudioTrim": AudioTrimNode,
}

NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {
    "FallingTSSelector": "FallingTS 多对一选择",
    "FallingTSTable": "FallingTS 通用表格 (Excel 式)",
    "FallingTSSwitch": "FallingTS 分组开关 (total组)",
    "FallingTSContinue": "FallingTS 继续节点",
    "FallingTSRoute": "FallingTS 路由节点 (total组)",
    "FallingTSFanout": "FallingTS 扇出选择 (total组)",
    "FallingTSMarkDownTable": "FallingTS MarkDown 数据表",
    "FallingTSFrameRateConvert": "FallingTS 帧率转换 (抽帧)",
    "FallingTSImageComposite": "FallingTS 四图合成 (2×2 带标注)",
    "FallingTSVideoComponents": "FallingTS 视频拆解 (拆帧/拆音)",
    "FallingTSH3AddGuide": "FallingTS H3 引导锚定 (None 安全)",
    "PreviewVideo": "Preview Video (保存)",
    "PreviewImageSave": "Preview Image (保存)",
    "PreviewAudioSave": "Preview Audio (保存)",
    "FallingTSAudioTrim": "FallingTS 音频截段 (波形切段)",
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
