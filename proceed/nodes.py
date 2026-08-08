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
    """任意类型通配符: 继承 str 并让 __ne__ 恒返回 False —— 在 ComfyUI 类型校验里
    与任何类型都"不相异", 即类型与任意输入/输出兼容, 从而实现 ANY 通配端口自由连线。
    """

    def __ne__(self, _: object) -> bool:
        # 恒返回 False: "ANY != 任何值"永远为假, 即 ANY 与任何类型都判为相等
        return False


# 通配端口常量: 类型为 * 的输入/输出, 可连接任意类型的数据
ANY = AnyType("*")


class FallingTSContinueNode:
    """分段执行控制节点: 默认阻塞下游, 点「继续」放行一段。"""

    # 已放行的节点: set[node_id]
    _released: set[str] = set()
    # 节点缓存的上游数据: node_id -> any (Run/上一段到达时收到的新数据覆盖; 点「继续」从这里取)
    _data_cache: dict[str, Any] = {}

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "optional".any: 透传数据端口, 类型为 ANY 通配符(*), 可接任意上游输出(图像/文本/数值...);
            - "hidden".id: 隐藏参数, 由前端注入当前节点的 UNIQUE_ID, 用作本节点的缓存键与释放状态键。
        """
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
        """缓存失效签名: 把"是否已放行"纳入缓存键, 放行前后返回值不同 -> 该节点被判定已变化
        -> 强制重新执行(从而从节点缓存取数据发往下游)。

        参数:
            id (str | None): 节点唯一 ID, 与 INPUT_TYPES 的 hidden.id 对应;
            **kwargs: 其余输入(any 等), 本方法不读取, 仅保持签名兼容。

        返回:
            tuple[bool]: (id 是否已在 _released 中,) 作为 ComfyUI 缓存键的一部分。
        """
        return (id in cls._released,)

    def execute(self, any: Any = None, id: str | None = None):  # noqa: A002
        """节点执行入口(分段执行的核心逻辑)。

        流程:
        1. 收到新数据(any 非 None)就写入节点缓存 _data_cache 覆盖旧值 —— 点「继续」后即使上游断开, 下游仍以节点缓存为准;
        2. 若本节点已放行(id 在 _released), 从缓存取数据包成单元素元组返回, 放行到下一段;
        3. 未放行则返回 ExecutionBlocker(None) 阻断下游 —— 不带消息, 不触发 execution_error 弹窗。

        参数:
            any (Any, 默认 None): 透传数据, 通常接上一节点的图像/任意输出; None 表示上游未提供(点「继续」时上游输入已被前端断开);
            id (str | None, 默认 None): 当前节点唯一 ID, 同时用作缓存键与释放状态键。

        返回:
            tuple[Any] | ExecutionBlocker:
            - (缓存值,): 放行时返回, 单元素元组, 数据透传给下游;
            - ExecutionBlocker(None): 未放行时返回, 阻断下游执行。
        """
        # 新数据进来就覆盖节点缓存 (点「继续」后仍以节点缓存为准发往下游)
        if any is not None:
            self._data_cache[id] = any
        if id in self._released:
            # 已放行: 从节点缓存取数据发往下一个流
            return (self._data_cache.get(id, any),)
        # 未放行: 阻断下游 (不带消息, 不触发 execution_error 弹窗)
        return ExecutionBlocker(None)


def _node_id(request: web.Request) -> str:
    """从 aiohttp 请求路径参数中取出 node_id 并去首尾空白。

    参数:
        request (web.Request): 已匹配路由 "/proceed/continue/{node_id}" 的 aiohttp 请求, node_id 取自 match_info["node_id"]。

    返回:
        str: 去空白后的节点 ID 字符串。
    """
    return request.match_info["node_id"].strip()


@PromptServer.instance.routes.post("/proceed/continue/{node_id}")
async def _handle_continue(request: web.Request) -> web.Response:
    """HTTP 路由: 放行一个继续节点(前端点「▶ 继续」时调用)。

    流程: 仅当节点在 _data_cache 中有缓存(说明之前确实跑到过该节点、收到过上游数据)才放行;
    否则返回 400 "没有上游数据", 前端据此 alert 提示。

    参数:
        request (web.Request): POST /proceed/continue/{node_id} 请求, node_id 取自路径参数。

    返回:
        web.Response (JSON):
        - 成功: 200, {"status": "ok"};
        - 失败: 400, {"status": "error", "message": "没有上游数据, 请先运行到该节点"}。
    """
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
    """HTTP 路由: 重置所有继续节点为阻塞并清空缓存(前端默认 Run 时调用)。

    清空 _released(全部回到未放行 = 阻塞)与 _data_cache(丢弃已缓存的上游数据),
    使下一次全量提交从开头执行、在第一个继续节点重新停住。

    参数:
        request (web.Request): POST /proceed/reset 请求, 不读取 body。

    返回:
        web.Response: 200, {"status": "ok"}。
    """
    FallingTSContinueNode._released.clear()
    FallingTSContinueNode._data_cache.clear()
    return web.json_response({"status": "ok"})


NODE_CLASS_MAPPINGS = {
    "FallingTSContinue": FallingTSContinueNode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSContinue": "FallingTS 继续节点",
}
