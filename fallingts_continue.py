# fallingts_continue.py
"""FallingTS 继续节点: 工作流分段执行控制。

行为:
- 执行到本节点时暂停, 前端节点上显示「▶ 继续」和「↻ 重跑」按钮;
- 「继续」: 放行当前运行, 继续往后执行;
- 「重跑」: 先中断当前(下游)运行, 再从本节点重新执行下游;
- 支持反复继续: 每次执行到本节点都会再次暂停;
- run_token 每次重跑递增, 用于破除 ComfyUI 缓存, 强制下游重新执行。
"""

from __future__ import annotations

import time
from typing import Any

from aiohttp import web
from comfy.model_management import InterruptProcessingException
from server import PromptServer


class AnyType(str):
    def __ne__(self, _: object) -> bool:
        return False


ANY = AnyType("*")


class FallingTSContinueNode:
    """分段执行控制节点: 数据透传 + 暂停/继续/重跑。"""

    # 暂停状态: node_id -> "paused" | "continue" | "cancelled"
    _status: dict[str, str] = {}
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
            return data

        self._count[node_id] = self._count.get(node_id, 0) + 1
        self._status[node_id] = "paused"
        PromptServer.instance.send_sync("fallingts_continue_paused", {"node_id": node_id})

        try:
            while self._status.get(node_id) == "paused":
                time.sleep(0.1)

            action = self._status.get(node_id)
            if action == "cancelled":
                raise InterruptProcessingException("FallingTS Continue: 已取消")
            return data
        finally:
            self._status.pop(node_id, None)


def _node_id(request: web.Request) -> str:
    return request.match_info["node_id"].strip()


@PromptServer.instance.routes.post("/fallingts_continue/continue/{node_id}")
async def _handle_continue(request: web.Request) -> web.Response:
    """继续: 放行当前暂停的节点。"""
    FallingTSContinueNode._status[_node_id(request)] = "continue"
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/fallingts_continue/cancel/{node_id}")
async def _handle_cancel(request: web.Request) -> web.Response:
    """取消: 中断当前暂停的节点(整次运行终止)。"""
    FallingTSContinueNode._status[_node_id(request)] = "cancelled"
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/fallingts_continue/restart/{node_id}")
async def _handle_restart(request: web.Request) -> web.Response:
    """重跑: 若节点正暂停则先中断当前运行, 并标记下次执行直接放行。"""
    nid = _node_id(request)
    if FallingTSContinueNode._status.get(nid) == "paused":
        FallingTSContinueNode._status[nid] = "cancelled"
    FallingTSContinueNode._restart_pending[nid] = time.time()
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/fallingts_continue/cancel_all")
async def _handle_cancel_all(_request: web.Request) -> web.Response:
    for nid in FallingTSContinueNode._status:
        FallingTSContinueNode._status[nid] = "cancelled"
    return web.json_response({"status": "ok"})


NODE_CLASS_MAPPINGS = {"FallingTSContinue": FallingTSContinueNode}
NODE_DISPLAY_NAME_MAPPINGS = {"FallingTSContinue": "FallingTS 继续节点"}
