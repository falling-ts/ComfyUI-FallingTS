# run-group/nodes.py
"""FallingTS 分组运行节点: 把一组输出节点聚合成「一个可单独执行的锚点」。

用途(0016 建模拆图这类「一套工作流里并列多条独立流」的场景):
原来靠「继续」节点在每条流入口把关, 点「继续」才放行那一条流; 现在改成在每条流的
**所有自动保存节点之后**各汇聚一个本节点, 点它浮窗上的「运行本组」按钮即可只跑这一条流,
不再需要「继续」。

实现要点:
- 左侧 input1..inputN(N = total)是 **ANY 且非 lazy** 输入, 用以接收本组各输出节点
  (如 AutoSaveImage)的输出。**必须非 lazy**: 执行引擎构建执行列表时对 lazy 输入会
  跳过向上游遍历(见 proceed/nodes.py), 而本节点的作用恰恰是"从本节点向上游拉整条流";
- **无任何输出**(RETURN_TYPES = ()): 本节点不产出数据, execute 只作占位;
- 声明 OUTPUT_NODE = True: ComfyUI 的 partial_execution_targets 只接受输出节点
  (execution.py 的 validate_prompt: 仅当 class 的 OUTPUT_NODE 为 True 且在本轮
  partial 列表里才加入 outputs)。前端点按钮即提交 partial_execution_targets=[本节点 id],
  执行引擎于是从本节点沿非 lazy 输入向上游遍历 -> 只执行本组那一条流, 另一组不受影响。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 最多输入端口数 (total 的上限, 与多对一选择/分组开关同一范式)
MAX_INPUTS = 50


class AnyType(str):
    """任意类型通配符: 继承 str 并让 __ne__ 恒返回 False —— 在 ComfyUI 类型校验里
    与任何类型都"不相异", 即类型与任意输入/输出兼容, 从而实现 ANY 通配端口自由连线。
    """

    def __ne__(self, _: object) -> bool:
        # 恒返回 False: "ANY != 任何值"永远为假, 即 ANY 与任何类型都判为相等
        return False


# 通配端口常量: 类型为 * 的输入, 可连接任意类型的数据
ANY = AnyType("*")


class FallingTSRunGroupNode:
    """分组运行节点: total 个 ANY 输入(聚合本组各输出节点), 无输出, 点浮窗按钮只跑本组。

    行为:
    - total (INT) 决定左侧输入端口个数, 前端按此动态增删 input1..inputN;
    - 每个输入接本组一个输出节点(如自动保存图片)的输出 —— 连线只是"声明归属",
      真正让它只跑本组的是前端提交时的 partial_execution_targets=[本节点 id];
    - 本节点无输出、不产出任何数据, 仅作执行锚点。

    为什么需要"非 lazy": 执行引擎构建执行列表时, 对 lazy 输入不沿该边向上游遍历
    (这正是「继续」节点用缓存跳过上游的机制)。本节点要的恰好相反 —— 让引擎从本节点
    向上游把整条流拉起来执行, 所以输入**不能**声明 lazy。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".total: 本组输出节点个数 (INT, 最少 1, 最多 MAX_INPUTS),
              左侧输入端口数 = total, 前端按此动态增删;
            - "optional".input1..inputMAX_INPUTS: 组内各输出节点的输出 (ANY 通配, 非 lazy),
              超出 total 的端口由前端删除、不进入 prompt。
        """
        optional = {}
        for i in range(1, MAX_INPUTS + 1):
            optional[f"input{i}"] = (
                "*",
                {
                    "tooltip": f"本组第 {i} 个输出节点的输出 (ANY), 仅声明归属; 点「运行本组」只执行本组",
                },
            )
        return {
            "required": {
                "total": (
                    "INT",
                    {
                        "default": 2,
                        "min": 1,
                        "max": MAX_INPUTS,
                        "tooltip": f"本组输出节点个数 (最少 1, 最多 {MAX_INPUTS}), 决定左侧输入端口数",
                    },
                ),
            },
            "optional": optional,
        }

    # 无任何输出: 本节点不产出数据(RETURN_TYPES 为空 -> 前端不显示输出端口)
    RETURN_TYPES = ()
    FUNCTION = "execute"
    # 必须是输出节点: partial_execution_targets 只接受 OUTPUT_NODE(见模块 docstring)
    OUTPUT_NODE = True
    CATEGORY = "FallingTS"
    DESCRIPTION = (
        "分组运行: total 个 ANY 输入聚合本组各输出节点, 无输出; "
        "点节点浮窗上的「运行本组」只执行本组那一条流(partial execution), 不影响其它组。"
    )
    SEARCH_ALIASES = ["分组运行", "运行本组", "分组", "运行", "run group", "锚点", "流"]

    @classmethod
    def IS_CHANGED(cls, **kwargs) -> float:
        """永不复用执行缓存 —— 每次点「运行本组」都必须真正重跑本组。

        返回 float("NaN")(任何比较都不相等, execution.py 给动态 prompt 节点也是这么置的),
        避免同进程内重复点按钮时本节点被全局执行缓存命中而跳过。
        """
        return float("NaN")

    def execute(self, total: int = 2, **kwargs):
        """节点执行入口: 不产出任何数据, 仅作为「本组唯一执行锚点」。

        参数:
            total (int, 默认 2): 本组输出节点个数(仅用于日志, 不影响执行);
            **kwargs: 各 inputN 输入值(本组各输出节点的输出), 本方法不读取。

        返回:
            dict: 空字典 —— 本节点无输出(RETURN_TYPES 为空), 与内置 SaveCheckpoint 同款。
        """
        got = sum(1 for k in kwargs if k.startswith("input") and kwargs.get(k) is not None)
        logger.info("[FallingTS.RunGroup] 运行本组: total=%s, 收到 %d 个输入", total, got)
        return {}


NODE_CLASS_MAPPINGS = {
    "FallingTSRunGroup": FallingTSRunGroupNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSRunGroup": "FallingTS 分组运行",
}
