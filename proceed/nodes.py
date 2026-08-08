# proceed/nodes.py
"""FallingTS 继续节点: 分段执行控制 (节点缓存 + partial execution)。

行为:
- 继续节点把收到的 any 缓存到节点上(新数据覆盖), 未放行时返回 ExecutionBlocker 阻塞下游;
- Run(默认): 前端先调 /proceed/reset 清空 released+缓存, 再全量提交 -> 生成段, 第一个继续缓存+阻塞;
- 点「继续」: 前端校验节点有缓存(否则 400"没有上游数据")并放行 -> 断开该节点 any 输入
  (节点用自身缓存), partial_execution_targets 取"下一个继续之后"的输出节点 ->
  执行子图穿过并到达下一个继续, 它缓存本段预览输出并阻塞。于是从当前继续开始往下跑, 不从开头。
"""

from __future__ import annotations

from typing import Any

from aiohttp import web
from server import PromptServer
from comfy_execution.graph_utils import ExecutionBlocker


class AnyType(str):
    def __ne__(self, _: object) -> bool:
        return False


ANY = AnyType("*")


class FallingTSContinueNode:
    """分段执行控制节点: 默认阻塞下游, 点「继续」放行一段。"""

    # 已放行的节点: set[node_id]
    _released: set[str] = set()
    # 节点缓存的上游数据: node_id -> any (Run/上一段到达时收到的新数据覆盖; 点「继续」从这里取)
    _data_cache: dict[str, Any] = {}

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "optional": {
                "any": (
                    ANY,
                    {
                        "tooltip": "透传数据, 通常接上一节点的图像/任意输出; 点「继续」时由节点缓存提供, 可从上游断开",
                    },
                ),
            },
            "hidden": {"id": "UNIQUE_ID"},
        }

    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("any",)
    FUNCTION = "execute"
    CATEGORY = "FallingTS/控制"

    @classmethod
    def IS_CHANGED(cls, id: str | None = None, **kwargs):
        """释放状态参与缓存签名: 放行会促使该节点重新执行 (从而从节点缓存取数据)。"""
        return (id in cls._released,)

    def execute(self, any: Any = None, id: str | None = None):  # noqa: A002
        # 新数据进来就覆盖节点缓存 (点「继续」后仍以节点缓存为准发往下游)
        if any is not None:
            self._data_cache[id] = any
        if id in self._released:
            # 已放行: 从节点缓存取数据发往下一个流
            return (self._data_cache.get(id, any),)
        # 未放行: 阻断下游 (不带消息, 不触发 execution_error 弹窗)
        return ExecutionBlocker(None)


def _node_id(request: web.Request) -> str:
    return request.match_info["node_id"].strip()


@PromptServer.instance.routes.post("/proceed/continue/{node_id}")
async def _handle_continue(request: web.Request) -> web.Response:
    """放行该继续节点: 有节点缓存(收到过上游数据)才放行, 否则报"没有上游数据"。"""
    nid = _node_id(request)
    if nid not in FallingTSContinueNode._data_cache:
        return web.json_response(
            {"status": "error", "message": "没有上游数据, 请先运行到该节点"},
            status=400,
        )
    FallingTSContinueNode._released.add(nid)
    return web.json_response({"status": "ok"})


@PromptServer.instance.routes.post("/proceed/reset")
async def _handle_reset(request: web.Request) -> web.Response:
    """重置所有继续节点为阻塞并清空缓存 (前端 Run 时调用)。"""
    FallingTSContinueNode._released.clear()
    FallingTSContinueNode._data_cache.clear()
    return web.json_response({"status": "ok"})


NODE_CLASS_MAPPINGS = {
    "FallingTSContinue": FallingTSContinueNode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSContinue": "FallingTS 继续节点",
}
