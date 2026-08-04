# proceed/nodes.py
"""FallingTS 继续节点: 工作流分段执行控制。

行为:
- 执行到本节点时暂停, 前端节点上显示「▶ 继续」和「↻ 重跑」按钮;
- 「继续」: 放行当前运行, 继续往后执行 (多次排队时一次放行一个运行);
- 「重跑」: 先中断当前(下游)运行, 再从本节点重新执行下游;
- 支持反复继续: 每次执行到本节点都会再次暂停;
- IS_CHANGED 保证本节点每次必执行, 并带动整条下游重跑;
- run_token 每次重跑递增, 破除 ComfyUI 缓存。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from aiohttp import web
from comfy.model_management import (
    InterruptProcessingException,
    interrupt_current_processing,
    throw_exception_if_processing_interrupted,
)
from server import PromptServer


class AnyType(str):
    def __ne__(self, _: object) -> bool:
        return False


ANY = AnyType("*")


# Qwen-Image-2512 官方支持的比例与分辨率 (与 note 中表格一致)
RATIOS: dict[str, tuple[int, int]] = {
    "9:16 (928×1664)": (928, 1664),
    "16:9 (1664×928)": (1664, 928),
    "1:1 (1328×1328)": (1328, 1328),
    "4:3 (1472×1104)": (1472, 1104),
    "3:4 (1104×1472)": (1104, 1472),
    "3:2 (1584×1056)": (1584, 1056),
    "2:3 (1056×1584)": (1056, 1584),
}


class FallingTSResolutionNode:
    """分辨率/宽高比选择器: 下拉选择比例, 输出 width/height 供空 Latent 使用。"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "ratio": (list(RATIOS.keys()), {"default": "9:16 (928×1664)", "tooltip": "Qwen-Image-2512 官方支持的比例"}),
            },
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"

    def execute(self, ratio: str):
        w, h = RATIOS[ratio]
        return (w, h)


class FallingTSContinueNode:
    """分段执行控制节点: 通用数据透传 + 暂停/继续/重跑。"""

    # 每个等待中的运行一个 Event: node_id -> deque[threading.Event]
    _waiters: dict[str, deque[threading.Event]] = {}
    # Event -> "continue" | "cancelled" (用 Event 对象自身做键, 避免与 execute 的 id 参数冲突)
    _wait_actions: dict[threading.Event, str] = {}
    # 重跑标记: node_id -> 时间戳 (下一次执行直接放行, 不暂停; 带过期防残留)
    _restart_pending: dict[str, float] = {}
    _RESTART_TTL = 60.0
    # 放行次数统计
    _count: dict[str, int] = {}

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "data": (ANY, {"tooltip": "透传数据, 通常接上一节点的图像/任意输出"}),
                "run_token": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF, "step": 1, "tooltip": "重跑序号, 每次重跑自动+1 用于破除缓存"}),
            },
            "hidden": {"id": "UNIQUE_ID"},
        }

    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("data",)
    FUNCTION = "execute"
    CATEGORY = "FallingTS/控制"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """返回变化值: 使本节点每次必执行, 并因祖先签名变化带动整条下游重跑。"""
        return time.time()

    def execute(self, data: Any = None, run_token: int = 0, id: str | None = None):  # noqa: A002
        node_id = id or "?"

        # 重跑放行: 上一次点了「重跑」, 本次执行直接通过, 不暂停 (60s 内有效)
        ts = self._restart_pending.pop(node_id, None)
        if ts is not None and time.time() - ts < self._RESTART_TTL:
            return (data,)

        self._count[node_id] = self._count.get(node_id, 0) + 1
        ev = threading.Event()
        self._waiters.setdefault(node_id, deque()).append(ev)
        self._wait_actions[ev] = "paused"
        PromptServer.instance.send_sync("proceed_paused", {"node_id": node_id})

        try:
            # 等待继续/重跑/取消; 同时轮询全局中断标志, API 层中断也能唤醒
            while not ev.is_set():
                throw_exception_if_processing_interrupted()
                ev.wait(0.2)
            action = self._wait_actions.pop(ev, "cancelled")
            if action == "cancelled":
                # 取消路径是直接抛异常(不经过 throw_exception), 需显式消费全局中断标志,
                # 防止残留标志把下一次运行在第一个节点就中断掉。
                interrupt_current_processing(False)
                raise InterruptProcessingException("FallingTS Continue: 已取消")
            return (data,)
        finally:
            # 清理本事件 (若路由尚未消费)
            dq = self._waiters.get(node_id)
            if dq is not None:
                try:
                    dq.remove(ev)
                except ValueError:
                    pass
                if not dq:
                    self._waiters.pop(node_id, None)
            self._wait_actions.pop(ev, None)


def _node_id(request: web.Request) -> str:
    return request.match_info["node_id"].strip()


def _cancel_waiters(nid: str) -> None:
    dq = FallingTSContinueNode._waiters.get(nid)
    if not dq:
        return
    for ev in list(dq):
        FallingTSContinueNode._wait_actions[ev] = "cancelled"
        ev.set()
    dq.clear()


@PromptServer.instance.routes.post("/proceed/continue/{node_id}")
async def _handle_continue(request: web.Request) -> web.Response:
    """继续: 放行最早一个暂停的运行。"""
    nid = _node_id(request)
    dq = FallingTSContinueNode._waiters.get(nid)
    if dq:
        ev = dq.popleft()
        FallingTSContinueNode._wait_actions[ev] = "continue"
        ev.set()
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/proceed/cancel/{node_id}")
async def _handle_cancel(request: web.Request) -> web.Response:
    """取消: 中断该节点所有暂停的运行。"""
    _cancel_waiters(_node_id(request))
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/proceed/restart/{node_id}")
async def _handle_restart(request: web.Request) -> web.Response:
    """重跑: 取消该节点暂停中的运行, 并标记下次执行直接放行。"""
    nid = _node_id(request)
    _cancel_waiters(nid)
    FallingTSContinueNode._restart_pending[nid] = time.time()
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/proceed/cancel_all")
async def _handle_cancel_all(_request: web.Request) -> web.Response:
    for nid in list(FallingTSContinueNode._waiters):
        _cancel_waiters(nid)
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/proceed/reset_interrupt")
async def _handle_reset_interrupt(_request: web.Request) -> web.Response:
    """清除全局中断标志 (重启流程: 旧运行结束后、重新入队前调用, 防止残留标志误杀新运行)。"""
    interrupt_current_processing(False)
    return web.json_response({"status": "ok"})


NODE_CLASS_MAPPINGS = {
    "FallingTSContinue": FallingTSContinueNode,
    "FallingTSResolution": FallingTSResolutionNode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSContinue": "FallingTS 继续节点",
    "FallingTSResolution": "FallingTS 分辨率选择",
}
