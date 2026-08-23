# proceed/nodes.py
"""FallingTS 继续节点: 分段执行控制 (节点缓存 + lazy 输入 + partial execution)。

行为:
- 继续节点把收到的 any 缓存到节点上(新数据覆盖), 未放行时返回 ExecutionBlocker 阻塞下游;
- any 输入声明为 lazy, 由 check_lazy_status 决定是否拉取上游: 未放行 -> 拉上游产生数据; 已放行 -> 不拉、用节点缓存;
- Run(默认): 前端先调 /proceed/reset 清空 released+缓存, 再全量提交 -> 生成段, 第一个继续缓存+阻塞;
- 点「继续」: 前端校验节点有缓存(否则 400"没有上游数据")并放行; 无需断开连线 ——
  any 输入 lazy, check_lazy_status 按放行状态决定不拉上游(节点用自身缓存),
  partial_execution_targets 取"下一个继续之后"的输出节点 ->
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

# 哨兵: 区分"该输入根本没连线"(MISSING)与"连了线但上游未求值"(None)。
# check_lazy_status 里只有真正连了线才能去拉上游 —— 若对不存在的输入调用
# make_input_strong_link 会抛 NodeInputError (comfy_execution/graph.py:122)。
MISSING = object()


class FallingTSContinueNode:
    """分段执行控制节点: 默认阻塞下游, 点「继续」放行一段。

    any 输入 lazy + check_lazy_status: 未放行时拉上游产生数据并缓存, 放行后不拉上游、
    用节点缓存发往下游 —— 连线无需断开, 上游也不会被重新执行。
    """

    # 已放行的节点: set[node_id]
    _released: set[str] = set()
    # 节点缓存的上游数据: node_id -> any (Run/上一段到达时收到的新数据覆盖; 点「继续」从这里取)
    _data_cache: dict[str, Any] = {}
    # 重置代际: /proceed/reset 时递增, 纳入 IS_CHANGED -> 每次 Run 后缓存键必变,
    # 强制继续节点重新执行(重新拉上游填 _data_cache), 不被 ComfyUI 全局执行缓存跳过
    # (否则同进程内重跑同图时, 继续节点被缓存命中 -> execute 不执行 -> _data_cache 不填 -> 「继续」400)
    _reset_generation: int = 0

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "optional".any: 透传数据端口, 类型为 ANY 通配符(*), 可接任意上游输出(图像/文本/数值...);
              标记 lazy=True: 构建执行列表时不沿这条边向上游遍历(add_node 对 lazy 输入跳过),
              是否拉取上游由 check_lazy_status 按放行状态决定(首次 Run 拉上游填缓存, 点「继续」后不拉、用节点缓存);
            - "hidden".id: 隐藏参数, 由前端注入当前节点的 UNIQUE_ID, 用作本节点的缓存键与释放状态键。
        """
        return {
            "optional": {
                "any": (
                    ANY,
                    {
                        "lazy": True,
                        "tooltip": "透传数据, 通常接上一节点的图像/任意输出; 点「继续」时由节点缓存提供, 上游不重新执行",
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
        """缓存失效签名: 把"重置代际 + 是否已放行"纳入缓存键, 代际变化或放行状态变化 ->
        该节点被判定已变化 -> 强制重新执行(全量 Run 拉上游填缓存; 放行后从节点缓存取数据发往下游)。

        参数:
            id (str | None): 节点唯一 ID, 与 INPUT_TYPES 的 hidden.id 对应;
            **kwargs: 其余输入(any 等), 本方法不读取, 仅保持签名兼容。

        返回:
            tuple: (_reset_generation, id 是否已在 _released 中) 作为 ComfyUI 缓存键的一部分。
            _reset_generation 每次 /proceed/reset 递增 -> 每次 Run 后缓存键必变, 强制重新执行;
            是否已放行区分全量 Run(阻塞)与 partial(放行)两种上下文, 避免互相命中缓存。
        """
        return (cls._reset_generation, id in cls._released)

    def check_lazy_status(self, any: Any = MISSING, id: str | None = None) -> list[str]:  # noqa: A002
        """lazy 输入门控: 决定本次执行要不要拉取上游的 any 数据 —— 这是"不断开连线也能从节点往下跑"的关键。

        机制(ComfyUI 执行引擎):
        1. 构建执行列表时, lazy 输入不会让 add_node 向上游遍历(execution.py 调 add_node 未带
           include_lazy, graph.py 的 add_node 对 lazy 输入直接跳过) —— 上游不因这条边被加入执行;
        2. 节点真正执行前, 引擎调本方法(execution.py:507-520), 返回"缺失且需要的输入名";
        3. 返回的输入名若在 missing_keys(连了线但未求值)里, 引擎才 make_input_strong_link 拉上游
           并返回 PENDING, 上游执行完重新调度本节点; 返回空则直接用 get_input_data 给的值(未拉取时是 None)。

        放行语义:
        - 未放行(首次 Run / 上一段刚放行到本节点): 上游必须执行以产生数据 -> 返回 ["any"] 拉上游, 填缓存;
        - 已放行(点过「继续」): 上游不应重跑, 数据来自节点缓存 -> 返回 [] 不拉, 引擎给 any=None,
          execute 里 None 不会覆盖缓存;
        - 没连线: 根本没有上游可拉, 返回 [] —— 避免对不存在的输入 make_input_strong_link 抛 NodeInputError。

        参数:
            any (Any, 默认 MISSING): 上游数据, 由引擎按输入名注入:
                - MISSING: 该输入没连线(不在 prompt 的 inputs 里, kwargs 无此键 -> 走默认值);
                - None: 连了线但上游未求值(lazy 输入未被拉取);
                - 其他: 已求值的上游值(此时已不在 missing_keys, 本方法的返回值会被过滤, 不触发拉取)。
            id (str | None): 当前节点唯一 ID, 与 execute 一致, 用于查释放状态 _released。

        返回:
            list[str]: 本次需要拉取的上游输入名列表, 只能是 ["any"] 或 []。
        """
        if any is MISSING:
            return []          # 没连线: 无上游可拉
        if id in self._released:
            return []          # 已放行: 不拉上游, execute 从 _data_cache 取缓存
        return ["any"]         # 未放行: 拉上游, 填缓存后再阻塞

    def execute(self, any: Any = None, id: str | None = None):  # noqa: A002
        """节点执行入口(分段执行的核心逻辑)。

        流程:
        1. 收到新数据(any 非 None)就写入节点缓存 _data_cache 覆盖旧值 —— 点「继续」后上游不重跑, 下游仍以节点缓存为准;
        2. 若本节点已放行(id 在 _released), 从缓存取数据包成单元素元组返回, 放行到下一段;
        3. 未放行则返回 ExecutionBlocker(None) 阻断下游 —— 不带消息, 不触发 execution_error 弹窗。

        参数:
            any (Any, 默认 None): 透传数据, 通常接上一节点的图像/任意输出; 点「继续」后由于
                check_lazy_status 返回 [] 不拉上游, 引擎给 None —— 节点用 _data_cache 的缓存, None 不覆盖;
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
    并递增 _reset_generation(强制继续节点重新执行, 见 IS_CHANGED),
    使下一次全量提交从开头执行、在第一个继续节点重新停住。

    参数:
        request (web.Request): POST /proceed/reset 请求, 不读取 body。

    返回:
        web.Response: 200, {"status": "ok"}。
    """
    FallingTSContinueNode._released.clear()
    FallingTSContinueNode._data_cache.clear()
    # 递增重置代际: 强制继续节点重新执行(见 IS_CHANGED), 避免同进程重跑时被全局执行缓存跳过
    FallingTSContinueNode._reset_generation += 1
    return web.json_response({"status": "ok"})


NODE_CLASS_MAPPINGS = {
    "FallingTSContinue": FallingTSContinueNode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSContinue": "FallingTS 继续节点",
}
