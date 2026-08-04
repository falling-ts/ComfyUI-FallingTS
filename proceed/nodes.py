# continue/nodes.py
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
from comfy.model_management import InterruptProcessingException
from server import PromptServer


class AnyType(str):
    def __ne__(self, _: object) -> bool:
        return False


ANY = AnyType("*")


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
        PromptServer.instance.send_sync("fallingts_continue_paused", {"node_id": node_id})

        try:
            ev.wait()
            action = self._wait_actions.pop(ev, "cancelled")
            if action == "cancelled":
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


@PromptServer.instance.routes.post("/fallingts_continue/continue/{node_id}")
async def _handle_continue(request: web.Request) -> web.Response:
    """继续: 放行最早一个暂停的运行。"""
    nid = _node_id(request)
    dq = FallingTSContinueNode._waiters.get(nid)
    if dq:
        ev = dq.popleft()
        FallingTSContinueNode._wait_actions[ev] = "continue"
        ev.set()
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/fallingts_continue/cancel/{node_id}")
async def _handle_cancel(request: web.Request) -> web.Response:
    """取消: 中断该节点所有暂停的运行。"""
    _cancel_waiters(_node_id(request))
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/fallingts_continue/restart/{node_id}")
async def _handle_restart(request: web.Request) -> web.Response:
    """重跑: 取消该节点暂停中的运行, 并标记下次执行直接放行。"""
    nid = _node_id(request)
    _cancel_waiters(nid)
    FallingTSContinueNode._restart_pending[nid] = time.time()
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/fallingts_continue/cancel_all")
async def _handle_cancel_all(_request: web.Request) -> web.Response:
    for nid in list(FallingTSContinueNode._waiters):
        _cancel_waiters(nid)
    return web.json_response({"status": "ok"})


NODE_CLASS_MAPPINGS = {"FallingTSContinue": FallingTSContinueNode}
NODE_DISPLAY_NAME_MAPPINGS = {"FallingTSContinue": "FallingTS 继续节点"}
