# proceed/nodes.py
"""FallingTS 继续节点: 工作流分段执行控制。

行为 (2026-08-04 重构, 配合前端 proceed.js):
- 继续节点只做通用数据透传 (any -> any), 不在后端阻塞;
- 分段由前端控制: Run 只提交"第一个继续节点之前"的部分执行,
  点「继续」提交"本节点往后到下一个继续节点之前"的部分执行
  (partial_execution_targets, 前半段命中缓存不重跑), 每次执行都是正常完成;
- 点「重跑」: 后端内部 run_token +1, IS_CHANGED 变化带动整条下游缓存失效重跑;
- run_token 是内部参数, 不再作为前端可见的 widget。
"""

from __future__ import annotations

from typing import Any

from aiohttp import web
from server import PromptServer


class AnyType(str):
    def __ne__(self, _: object) -> bool:
        return False


ANY = AnyType("*")


class FallingTSContinueNode:
    """分段执行控制节点: 通用数据透传, 分段/继续/重跑由前端 partial execution 控制。"""

    # 内部重跑序号: node_id -> int (前端「重跑」时 +1, 破除下游缓存, 不在前端显示)
    _tokens: dict[str, int] = {}

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "any": (ANY, {"tooltip": "透传数据, 通常接上一节点的图像/任意输出"}),
            },
            "hidden": {"id": "UNIQUE_ID"},
        }

    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("any",)
    FUNCTION = "execute"
    CATEGORY = "FallingTS/控制"

    @classmethod
    def IS_CHANGED(cls, id: str | None = None, **kwargs):
        """返回内部重跑序号; 「重跑」时 +1, 因缓存签名含祖先 IS_CHANGED, 带动整条下游重跑。"""
        return cls._tokens.get(id or "?", 0)

    def execute(self, any: Any = None, id: str | None = None):  # noqa: A002
        # 纯透传: 数据一模一样进入、一模一样出去
        return (any,)


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
    """继续 (兼容保留): 分段执行由前端 partial execution 控制, 后端仅确认。"""
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/proceed/restart/{node_id}")
async def _handle_restart(request: web.Request) -> web.Response:
    """重跑: 内部 run_token +1, 使该节点及整条下游缓存失效。"""
    nid = _node_id(request)
    FallingTSContinueNode._tokens[nid] = FallingTSContinueNode._tokens.get(nid, 0) + 1
    return web.json_response({"status": "ok"})


NODE_CLASS_MAPPINGS = {
    "FallingTSContinue": FallingTSContinueNode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSContinue": "FallingTS 继续节点",
}
