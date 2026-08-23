# onemany/nodes.py
"""FallingTS 一对多选择 (多对一选择的镜像, 参考多对一选择的 total 组范式):
items 组名列表(英文逗号分隔) + total 组数(最少 1) + selection 选中项(下拉框, 选项 = 组名, 可连线接多对一 选中项/索引);
左侧输入端口 = 组数 (每组一个 input_i, 第 1 组在前第 2 组在后),
右侧输出端口 = 组数 × 组名数量 (第 i 组 = 每个组名一个输出, 端口标签循环为组名)。

行为 (多对一的镜像):
- total 为组数 (最少 1, 最多 MAX_GROUPS), 左侧 total 个输入端口 input_1..input_total, 每组一个;
- items 组名列表有 M 个组名时, 右侧共 total × M 个输出端口 (最多 MAX_OUTPUTS):
  第 i 组 = 每个组名一个输出, 端口标签循环为组名列表内容;
- selection 选中项 = 下拉框选中的组名 (选项 = 所有组名), 可连线接多对一 选中项 (组名文本) 或 索引 (0 起,
  传入索引直接选中所属索引的组名), 选中第 k 个组名:
  第 i 组的输入值 input_i 路由到第 i 组中该组名对应的输出, 第 i 组其余输出 None;
- selection 失配/索引越界(旧工作流/手动改动)回退第一组名;
- 未连线时各组输入为 None, 各组输出均为 None。
"""

from __future__ import annotations


def _split_items(items: str) -> list[str]:
    """按英文逗号拆分并去除首尾空白, 忽略空项。

    参数:
        items (str): 逗号分隔的组名文本, 可为空字符串或 None。

    返回:
        list[str]: 去空白后的非空组名列表。
    """
    return [s.strip() for s in (items or "").split(",") if s.strip()]


# 最多组数 (组数 total 的上限, = 左侧输入端口数, 与多对一选择同一范式)
MAX_GROUPS = 50

# 最多输出端口数 (组数 × 组名数量 的上限, 与多对一选择的 MAX_INPUTS 同一范式)
MAX_OUTPUTS = 50

# 哨兵: 区分"该输入根本没连线"与"连了线但上游未求值"
MISSING = object()


class FallingTSOneToManyNode:
    """一对多选择节点 (多对一的镜像): total 组数(最少 1) 动态展开左侧 input_1..input_total 输入端口
    (每组一个), 右侧 total × 组名数量 动态展开 output_1..outputN 输出端口 (第 i 组 = 每个组名一个输出,
    端口标签循环为组名), selection 选中项 (下拉框, 选项 = 组名, 可连线接多对一 选中项/索引) 选中第 k 个组名 ->
    第 i 组 input_i 路由到第 i 组该组名对应的输出, 第 i 组其余输出 None。

    行为:
    - items (英文逗号分隔组名) 提供各输出端口标签与下拉选项 (如 "右面,后面,左面"),
      端口内部名称仍为 outputN 用于定位;
    - 左侧第 i 组 = input_i (1 个输入, 每组一个, 第 1 组在前第 2 组在后);
    - selection 选中第 k 个组名 -> 第 i 组 output[(i-1)×M+k+1] = input_i 的值, 第 i 组其余输出 None;
    - 右侧: output_1..outputN (N = total × M) 按 total/M 追加, 前端按 total×M 显隐, 按 items 组名标注;
    - 未连线时各组输入为 None, 各组输出均为 None。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".items: 逗号分隔的组名列表, 每个组名在每组各展开一个输出端口 (前端联动);
            - "required".total: 组数 (INT, 最少 1, 最多 MAX_GROUPS), 左侧 total 个输入端口 (每组一个),
              右侧输出 = 组数 × 组名数量, 前端按此动态增删端口;
            - "required".selection: 选中项 下拉框 (选项 = 组名, 可连线接多对一 选中项/索引),
              传入组名按名匹配, 传入索引直接选中所属索引的组名, 决定每组 input_i 路由到哪个输出;
            - "optional".input1..inputMAX_GROUPS: 组数据端口 (ANY, 每组一个), 全部标记 lazy=True,
              各组输入值路由到该组选中组名对应的输出。
        """
        optional = {}
        for i in range(1, MAX_GROUPS + 1):
            optional[f"input{i}"] = (
                "*",
                {
                    "lazy": True,
                    "tooltip": f"第 {i} 组 输入 (ANY): 该组 input_i, 选中组名对应的输出 = 此输入值",
                },
            )
        return {
            "required": {
                "items": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "用英文逗号分隔的组名列表 (如: 右面,后面,左面); 每个组名在每组各展开一个输出端口, 端口标签为组名",
                    },
                ),
                "total": (
                    "INT",
                    {
                        "default": 2,
                        "min": 1,
                        "max": MAX_GROUPS,
                        "tooltip": f"组数 (最少 1, 最多 {MAX_GROUPS}), 每组一个输入 + 每个组名一个输出, 输出 = 组数 × 组名数量",
                    },
                ),
                "selection": (
                    [],
                    {
                        "default": "",
                        "tooltip": "选中项 下拉框 (选项 = 组名, 可连线接多对一 选中项/索引): 传组名按名匹配, 传索引 (0 起) 直接选中所属索引的组名",
                    },
                ),
            },
            "optional": optional,
        }

    # 输出槽位: output_1..output_MAX_OUTPUTS (total × M, 前端按 total×M 显隐, 按 items 组名标注);
    # 增删只动尾部, 已有连线的槽位永不漂移。
    RETURN_TYPES = ("*",) * MAX_OUTPUTS
    RETURN_NAMES = tuple(f"output_{i}" for i in range(1, MAX_OUTPUTS + 1))
    OUTPUT_TOOLTIPS = tuple(
        f"第 i 组 第 j 个组名 输出 (ANY): 该组选中组名对应时 = 该组 input 值, 否则 None"
        for i in range(1, MAX_OUTPUTS + 1)
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"
    DESCRIPTION = (
        "一对多选择 (多对一的镜像): items 逗号分隔组名, total 组数(最少 1, = 左侧输入端口数, 每组一个 input_i), "
        "右侧 total × 组名数量 个输出 (每组每个组名一个, 标签 = 组名), "
        "selection 选中项 (下拉框, 可连线接多对一 选中项/索引, 传索引直接选中所属索引的组名), 每组 input_i 路由到该组名对应的输出, 其余 None, 未连线为 None。"
    )
    SEARCH_ALIASES = [
        "一对多", "多选多", "扇出", "广播", "路由", "one-to-many", "fanout", "group", "组名", "多组", "total", "items", "选中项",
    ]

    @classmethod
    def IS_CHANGED(cls, items: str = "", total: int = 2, selection = "", **kwargs):
        """缓存失效签名: 组名列表、组数或选中项变化时重新执行 (动态输入值变化由引擎依赖机制处理)。"""
        return (items, total, selection)

    @classmethod
    def VALIDATE_INPUTS(cls, items: str = "", total: int = 2, selection = "", input_types=None, **kwargs) -> bool:
        """输入校验: 动态下拉选项由 items 实时生成, 后端静态选项表为空, 恒通过 (execute 内有失配回退)。"""
        return True

    @staticmethod
    def _resolve_index(options: list[str], selection) -> int:
        """选中项 -> 索引: 传入索引 (INT, 0 起) 直接取该索引的组名; 传入组名 (STRING) 按名匹配;
        失配/越界/非法值(旧工作流/手动改动)回退 0。

        参数:
            options (list[str]): 组名列表(调用方已保证非空);
            selection: 选中项 (下拉选中的组名文本, 或连线传入的索引, 0 起)。

        返回:
            int: 0 ~ len(options)-1 的组名索引。
        """
        if isinstance(selection, bool) or not isinstance(selection, (int, str)):
            return 0
        if isinstance(selection, int):
            return selection if 0 <= selection < len(options) else 0
        if selection in options:
            return options.index(selection)
        return 0

    @staticmethod
    def _clamp_total(total) -> int:
        """组数钳位到 [1, MAX_GROUPS], 非法值回退默认 2。"""
        try:
            t = int(total)
        except (TypeError, ValueError):
            t = 2
        return min(MAX_GROUPS, max(1, t))

    def check_lazy_status(self, items: str = "", total: int = 2, selection: str = "", **kwargs) -> list[str]:
        """lazy 输入门控: 各组输入都要拉取 (每组 input_i 路由到该组选中组名对应的输出, 无单一假分支)。

        机制 (ComfyUI 执行引擎):
        1. 所有 inputN 声明 lazy=True, 构建执行列表时不会沿这些边向上游遍历;
        2. 节点执行前引擎调本方法, 返回的输入名若尚未求值才会 make_input_strong_link 拉上游;
        3. 返回各组 input_1..input_total (连线的) -> 各组分支都被求值 (每个组的输入都要路由到输出)。

        参数:
            items (str): 逗号分隔的组名列表;
            total (int): 组数;
            selection: 选中项 (下拉选中的组名, 或连线传入的索引, 0 起);
            **kwargs: 各 inputN 输入值 (未连线的键不存在)。

        返回:
            list[str]: 需要拉取上游的输入名 (连线的各组 inputN)。
        """
        total = self._clamp_total(total)
        need = []
        for i in range(1, total + 1):
            name = f"input{i}"
            if kwargs.get(name, MISSING) is not MISSING:
                need.append(name)
        return need

    def execute(self, items: str = "", total: int = 2, selection = "", **kwargs):
        """节点执行入口: 各组 input_i 路由到该组选中组名对应的输出, 第 i 组其余输出 None。

        参数:
            items (str): 组名列表 (逗号分隔), 提供各输出端口标签 (M 个组名);
            total (int): 组数 (1~MAX_GROUPS, 非法值回退 2), = 左侧输入端口数 (每组一个 input_i);
            selection: 选中项 (下拉选中的组名, 或连线传入的索引, 0 起), 决定每组 input_i 路由到哪个输出;
            **kwargs: 各 inputN 输入值 (未连线/未求值时键不存在或为 None)。

        返回:
            tuple: 长度 MAX_OUTPUTS, 第 i 组 (i=1..total) 的 M 个输出中,
            选中组名 (selection 对应索引 k) 对应的输出 = 该组 input_i 的值, 其余 None;
            组数之外的组与组名数量不足 MAX_OUTPUTS 的尾部为 None。
        """
        options = _split_items(items)
        total = self._clamp_total(total)
        M = len(options)
        k = self._resolve_index(options, selection) if options else 0
        out: list = []
        for i in range(1, total + 1):
            v = kwargs.get(f"input{i}", MISSING)
            v = None if v is MISSING else v
            for j in range(M):
                out.append(v if j == k else None)
        while len(out) < MAX_OUTPUTS:
            out.append(None)
        return tuple(out[:MAX_OUTPUTS])


NODE_CLASS_MAPPINGS = {
    "FallingTSOneToMany": FallingTSOneToManyNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSOneToMany": "FallingTS 一对多选择 (total组)",
}
