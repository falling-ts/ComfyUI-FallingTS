# table/nodes.py
"""FallingTS 通用表格节点 (Excel 式, 数据内嵌工作流, 不读外部文件)。

设计:
- 最左侧固定「索引」列 (从 0 开始), 其后依次为 A、B、C ... (Excel 列名规则, 支持到 AZ, 共 MAX_COLS=52 列);
- 行选择由前端「选择」下拉驱动 (值存 selected_index), 输出按列数动态生成 A/B/C..., 全部为 STRING;
- 行数/列数/首列ID 由前端控件顶部输入 (最少 1), 修改列数时右侧输出端口随之增减;
- 需要数值/其他类型时, 由用户在其后自行添加类型转换节点。
"""

from __future__ import annotations


MAX_COLS = 52


def excel_col_name(i: int) -> str:
    """Excel 风格列名: 0->A ... 25->Z, 26->AA ... 51->AZ。"""
    s = ""
    n = i + 1
    while n > 0:
        n -= 1
        s = chr(65 + (n % 26)) + s
        n //= 26
    return s


DEFAULT_TABLE = {
    "row_count": 3,
    "col_count": 3,
    "first_col_is_id": False,
    "selected_index": 0,
    "data": [["", "", ""], ["", "", ""], ["", "", ""]],
}

# 最近一次输出缓存: node_id -> 选中行各列字符串元组 (长度 MAX_COLS)
# rows 为 None (未连接/上游无值) 时输出本节点最近一次输出行 (sticky), 让下游不丢数据; 从未输出则回退默认表
_last_output: dict = {}


def normalize_table(value) -> dict:
    """把前端表格控件值规范化为 {row_count, col_count, data}。

    兼容旧版: 传入行对象数组 (正|负|宽|高|批次) 时转换为 A..E 五列网格。
    """
    if isinstance(value, list):
        rows = [
            [
                str(r.get("pos", "")),
                str(r.get("neg", "")),
                str(r.get("w", 928)),
                str(r.get("h", 1664)),
                str(r.get("batch", 1)),
            ]
            for r in value
        ]
        if rows:
            cc = max(len(r) for r in rows)
            return {
                "row_count": max(1, len(rows)),
                "col_count": max(1, min(MAX_COLS, cc)),
                "first_col_is_id": False,
                "selected_index": 0,
                "data": rows,
            }
        return dict(DEFAULT_TABLE)

    if not isinstance(value, dict):
        value = {}
    try:
        row_count = max(1, int(value.get("row_count", 1)))
        col_count = max(1, min(MAX_COLS, int(value.get("col_count", 1))))
    except (TypeError, ValueError):
        row_count, col_count = 1, 1
    try:
        selected_index = max(0, int(value.get("selected_index", 0)))
    except (TypeError, ValueError):
        selected_index = 0
    src = value.get("data")
    if not isinstance(src, list):
        src = []
    data = []
    for r in range(row_count):
        src_row = src[r] if r < len(src) and isinstance(src[r], list) else []
        data.append(
            [
                str(src_row[c]) if c < len(src_row) and src_row[c] is not None else ""
                for c in range(col_count)
            ]
        )
    return {
        "row_count": row_count,
        "col_count": col_count,
        "first_col_is_id": value.get("first_col_is_id") is True,
        "selected_index": min(selected_index, row_count - 1),
        "data": data,
    }


class FallingTSTableNode:
    """通用 Excel 式表格: 顶部「选择」下拉选行, 输出该行 A/B/C... 各列字符串。

    前端用 DOM 表格控件 (web/js/table_lookup.js) 编辑: 最左索引列固定,
    其后 A/B/C... 列; 顶部「选择/行数/列数/首列ID」控件 (最少 1); 修改
    列数时右侧输出端口随之增减。数据内嵌工作流 JSON, 不读外部文件; 类型
    转换由下游节点自行完成。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        """声明节点输入。

        返回:
            dict:
            - "required".rows: FALLINGTS_TABLE 表格控件(前端 table_lookup.js 渲染),
              值是 {row_count, col_count, first_col_is_id, selected_index, data} 表格状态对象。
        """
        return {
            "required": {
                "rows": (
                    "FALLINGTS_TABLE",
                    {
                        "default": DEFAULT_TABLE,
                        "tooltip": "通用表格: 顶部「选择」下拉选行, 最左索引列固定, 其后 A/B/C... 列 (行数/列数/首列ID可调, 最少 1)",
                    },
                ),
            },
            "hidden": {"id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING",) * MAX_COLS
    RETURN_NAMES = tuple(excel_col_name(i) for i in range(MAX_COLS))
    OUTPUT_TOOLTIPS = tuple(
        f"{excel_col_name(i)} 列: 选中行第 {i + 1} 列单元格字符串"
        for i in range(MAX_COLS)
    )
    FUNCTION = "execute"
    CATEGORY = "FallingTS/表格"
    DESCRIPTION = (
        "通用 Excel 式表格 (数据内嵌工作流): 顶部「选择」下拉选行, 输出该行 "
        "A/B/C... 各列字符串; 行数/列数可调 (最少 1), 输出端口随列数增减。"
    )
    SEARCH_ALIASES = ["表格", "表", "table", "excel", "行", "列", "查表", "数据表", "sheet", "选择", "下拉"]

    def execute(self, rows, id=None):
        """节点执行入口: 输出选中行的各列单元格字符串。

        逻辑: 规范化 rows 为表格状态, 取 selected_index 选中行,
        把该行各列填进 A/B/C... 输出槽(未用的槽输出空串)。
        rows 为 None (未连接/上游无值): 不报错 —— 若本节点曾输出过数据, 输出最近一次输出行 (sticky, 下游不丢数据);
        从未输出过则回退默认表 (空表)。

        参数:
            rows (dict|list|None): 表格控件值(前端序列化的表格状态对象, 或旧版行对象数组); None (未连接/上游无值)。
            id (str | None): 节点唯一 ID (隐藏参数 UNIQUE_ID), 用作本节点输出缓存键。

        返回:
            tuple[str, ...]: 长度 MAX_COLS, 前 col_count 个为选中行各列字符串, 其余为空串。
        """
        # rows 为 None (未连接/上游无值) 且本节点曾输出过数据 → 输出最近一次输出行 (sticky)
        if rows is None and id is not None and str(id) in _last_output:
            return _last_output[str(id)]
        state = normalize_table(rows)
        row_count = state["row_count"]
        col_count = state["col_count"]
        data = state["data"]
        index = state["selected_index"]
        row = data[index]
        cells = [""] * MAX_COLS
        for i in range(min(col_count, MAX_COLS)):
            cells[i] = row[i]
        result = tuple(cells)
        if id is not None:
            _last_output[str(id)] = result
        return result


NODE_CLASS_MAPPINGS = {
    "FallingTSTable": FallingTSTableNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSTable": "FallingTS 通用表格 (Excel 式)",
}
