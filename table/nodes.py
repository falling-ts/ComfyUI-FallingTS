# table/nodes.py
"""FallingTS 通用表格节点 (Excel 式, 数据内嵌工作流, 不读外部文件)。

设计:
- 最左侧固定「索引」列 (从 0 开始, 与 index 输入严格对应), 其后依次为
  A、B、C ... (Excel 列名规则, 支持到 AZ, 共 MAX_COLS=52 列);
- 输入只有 index (行索引); 输出按列数动态生成 A/B/C..., 全部为 STRING;
- 行数/列数由前端表格控件底部输入 (最少 1), 修改列数时右侧输出端口随之增减;
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
    "data": [["", "", ""], ["", "", ""], ["", "", ""]],
}


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
    return {"row_count": row_count, "col_count": col_count, "data": data}


class FallingTSTableNode:
    """通用 Excel 式表格: 输入行索引, 输出该行 A/B/C... 各列字符串。

    前端用 DOM 表格控件 (web/js/table_lookup.js) 编辑: 最左索引列固定,
    其后 A/B/C... 列; 底部「行数/列数」输入 (最少 1); 修改列数时右侧
    输出端口随之增减。数据内嵌工作流 JSON, 不读外部文件; 类型转换由
    下游节点自行完成。
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "index": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFF,
                        "tooltip": "行索引 (从 0 开始), 输出该行 A/B/C... 各列字符串",
                    },
                ),
                "rows": (
                    "FALLINGTS_TABLE",
                    {
                        "default": DEFAULT_TABLE,
                        "tooltip": "通用表格: 最左索引列固定, 其后 A/B/C... 列 (行数/列数可调, 最少 1)",
                    },
                ),
            },
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
        "通用 Excel 式表格 (数据内嵌工作流): 输入行索引, 输出该行 A/B/C... "
        "各列字符串; 行数/列数可调 (最少 1), 输出端口随列数增减。"
    )
    SEARCH_ALIASES = ["表格", "表", "table", "excel", "行", "列", "查表", "数据表", "sheet"]

    def execute(self, index: int, rows):
        state = normalize_table(rows)
        row_count = state["row_count"]
        col_count = state["col_count"]
        data = state["data"]
        if index < 0 or index >= row_count:
            raise ValueError(
                f"FallingTSTable: 索引 {index} 超出范围 "
                f"(表格共 {row_count} 行, 索引从 0 开始)"
            )
        row = data[index]
        cells = [""] * MAX_COLS
        for i in range(min(col_count, MAX_COLS)):
            cells[i] = row[i]
        return tuple(cells)


NODE_CLASS_MAPPINGS = {
    "FallingTSTable": FallingTSTableNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSTable": "FallingTS 通用表格 (Excel 式)",
}
