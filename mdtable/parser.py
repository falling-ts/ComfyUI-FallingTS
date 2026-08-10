# mdtable/parser.py
"""FallingTSMarkDownTable 的 md 数据表解析与值类型转换(纯函数, 不依赖 ComfyUI, 可单测)。

md 数据表约定:
- 文件含一张 GFM 表格(表头 + --- 分隔行 + 数据行), 取第一张;
- **第一列永远是 ID 列**: str 中文字符串, 可能用 `-` 连接多段信息; 解析时强制该列 type=STRING;
- 表头格式 `标题(类型)`, 未标类型默认 `STRING`; 支持类型(大小写不敏感, 别名归一):
  IMAGE / VIDEO / AUDIO / STRING / INT / FLOAT / BOOLEAN / TEXT;
- 单元格值按列类型在 execute 时转换 (coerce_value): INT/FLOAT/BOOLEAN -> 原生数值/布尔,
  STRING/TEXT/IMAGE/VIDEO/AUDIO -> 原字符串 (TEXT 输出同为 STRING, 仅前端渲染为多行文本框)。
"""

from __future__ import annotations

import json
import os
import re

# ─── 常量 ────────────────────────────────────────────────────────────

# 非 ID 字段数量上限 (输出端口 = 1[ID] + MAX_FIELDS 字段 + 1[data JSON])
MAX_FIELDS = 40
MAX_OUTPUTS = MAX_FIELDS + 2

DEFAULT_STATE = {
    "md_path": "",
    "fields": [],
    "selected": {"id": "", "values": {}},
}

# 类型别名归一表: 统一到大写 ComfyUI 风格类型; 显式写了类型但不在表里 -> 回退 STRING
# 核心类型: IMAGE / VIDEO / AUDIO / STRING / INT / FLOAT / BOOLEAN / TEXT
#   - STRING: 单行文本; TEXT: 多行文本 (输出同为 STRING, 前端渲染差异);
#   - IMAGE/VIDEO/AUDIO: 文件路径 (带预览); INT/FLOAT/BOOLEAN: 数值/布尔。
_TYPE_ALIASES = {
    "str": "STRING", "string": "STRING",
    "text": "TEXT", "txt": "TEXT",
    "int": "INT", "integer": "INT", "long": "INT",
    "float": "FLOAT", "double": "FLOAT", "real": "FLOAT", "number": "FLOAT", "num": "FLOAT",
    "bool": "BOOLEAN", "boolean": "BOOLEAN", "flag": "BOOLEAN",
    "image": "IMAGE", "img": "IMAGE", "png": "IMAGE", "jpg": "IMAGE", "jpeg": "IMAGE", "photo": "IMAGE",
    "video": "VIDEO", "mp4": "VIDEO", "webm": "VIDEO", "movie": "VIDEO",
    "audio": "AUDIO", "sound": "AUDIO", "mp3": "AUDIO", "wav": "AUDIO", "voice": "AUDIO",
    # 旧版 list/set/dict 类型已并入 STRING (不再特殊解析集合)
    "list": "STRING", "array": "STRING", "set": "STRING", "dict": "STRING", "json": "STRING",
}

_HEADER_RE = re.compile(r"^(.*?)\s*[\(\[](.*?)[\)\]]\s*$")
# 说明: md 表格表头里 `[]` 是特殊语法(链接/脚注), 类型一律写 `标题(类型)`;
#       同时兼容旧式 `标题[类型]`。无括号时整格作为字段名, 类型默认 STRING。
# GFM 分隔行: | :--- | ---: | 等
_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
# 单元格内的 markdown 修饰: [文本](链接) -> 文本
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")

_TRUE_VALUES = {"true", "1", "yes", "y", "on", "是", "真", "开", "对", "t"}

# ─── 类型处理 ────────────────────────────────────────────────────────


def normalize_type(raw: str) -> str:
    """把表头里写的类型归一化为大写 ComfyUI 类型; 未知类型回退 STRING。

    参数:
        raw (str): 表头类型原文。

    返回:
        str: 归一化类型 (IMAGE/VIDEO/AUDIO/STRING/INT/FLOAT/BOOLEAN/TEXT)。
    """
    key = (raw or "").strip().lower()
    return _TYPE_ALIASES.get(key, "STRING")


def parse_header(cell: str) -> tuple[str, str]:
    """解析单个表头 `标题(类型)`; 无 (类型) 时默认 STRING。

    参数:
        cell (str): 表头单元格文本。

    返回:
        tuple[str, str]: (标题, 归一化类型)。
    """
    text = (cell or "").strip()
    m = _HEADER_RE.match(text)
    if not m:
        return (text or "字段", "STRING")
    name = m.group(1).strip()
    ftype = normalize_type(m.group(2).strip())
    return (name or "字段", ftype)


# ─── md 表格解析 ─────────────────────────────────────────────────────


def _split_md_row(line: str) -> list[str]:
    r"""按未转义的 `|` 切分一行表格; 处理 `\|` 转义并去首尾空白。

    参数:
        line (str): 一行表格文本(可能含前导/尾随 |)。

    返回:
        list[str]: 各单元格去空白后的字符串。
    """
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells: list[str] = []
    cur = ""
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n and s[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if ch == "|":
            cells.append(cur.strip())
            cur = ""
            i += 1
            continue
        cur += ch
        i += 1
    cells.append(cur.strip())
    return cells


def _is_separator(line: str) -> bool:
    """判断一行是否为 GFM 表格分隔行 (| --- | --- | 等)。

    参数:
        line (str): 去空白后的一行。

    返回:
        bool: 是分隔行返回 True。
    """
    return bool(_SEP_RE.match(line.strip()))


def _clean_cell(value: str) -> str:
    """去掉单元格内的常见 markdown 修饰, 还原纯文本值。

    参数:
        value (str): 原始单元格文本。

    返回:
        str: 清洗后的值。
    """
    v = (value or "").strip()
    v = _LINK_RE.sub(r"\1", v)       # [文本](url) -> 文本
    v = v.replace("**", "").replace("__", "")  # 粗体
    v = v.strip("`").strip()         # 行内代码反引号
    return v.strip()


def _read_text(path: str) -> str:
    """按 utf-8(-sig)/gb18030 顺序读取文本文件(Windows 常见 gbk 兜底)。

    参数:
        path (str): 文件绝对路径。

    返回:
        str: 文件文本。

    异常:
        OSError: 文件不存在/不可读时按最后一个编码策略抛出。
    """
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_md_file(path: str) -> tuple[list[dict], list[dict]]:
    """从 md 文件解析出第一张 GFM 表格: 字段定义 + 数据行。

    参数:
        path (str): md 文件绝对路径。

    返回:
        tuple[list[dict], list[dict]]:
        - fields: [{name, type}, ...], 第 0 个恒为 ID 列 (type=str);
        - rows: [{id, values:{字段名: 值字符串}}, ...], 按出现顺序, 去重空行/重复 ID。

    异常:
        ValueError: 文件里没有表格 / 没有数据行。
    """
    text = _read_text(path)
    lines = text.splitlines()
    n = len(lines)
    found = None
    for i in range(n - 1):
        if "|" not in lines[i]:
            continue
        if not _is_separator(lines[i + 1]):
            continue
        header = _split_md_row(lines[i])
        if not header:
            continue
        rows_raw: list[list[str]] = []
        j = i + 2
        while j < n:
            line = lines[j].strip()
            if not line or "|" not in line or _is_separator(line):
                break
            rows_raw.append(_split_md_row(lines[j]))
            j += 1
        found = (header, rows_raw)
        break
    if found is None:
        raise ValueError("文件中未找到 Markdown 表格 (需要表头 + --- 分隔行)")
    header, rows_raw = found

    fields = [{"name": name, "type": ftype} for name, ftype in (parse_header(c) for c in header)]
    if not fields:
        raise ValueError("表格表头为空")
    # 第一列永远是 ID 列: 类型强制 STRING (名称保留 md 里写的, 常为 ID)
    fields[0]["type"] = "STRING"

    rows: list[dict] = []
    seen: set[str] = set()
    for cells in rows_raw:
        if not cells or not cells[0].strip():
            continue
        rid = cells[0].strip()
        if rid in seen:
            continue
        seen.add(rid)
        values: dict[str, str] = {}
        for fi, f in enumerate(fields):
            cell = cells[fi] if fi < len(cells) else ""
            values[f["name"]] = _clean_cell(cell)
        rows.append({"id": rid, "values": values})

    if not rows:
        raise ValueError("表格中没有数据行")
    return fields, rows


# ─── 值类型转换 (execute 输出用) ─────────────────────────────────────


def _to_bool(raw) -> bool:
    """把表单/md 里的 bool 值字符串解析为布尔 (兼容中文/英文/数字)。

    参数:
        raw (str|bool): 原始值。

    返回:
        bool: 解析结果, 无法识别按 False。
    """
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in _TRUE_VALUES


def coerce_value(raw, ftype: str):
    """按字段类型把表单/md 的原始值转换为 execute 输出值。

    参数:
        raw (str|bool|None): 表单里存的原始值。
        ftype (str): 归一化类型 (IMAGE/VIDEO/AUDIO/STRING/INT/FLOAT/BOOLEAN/TEXT)。

    返回:
        int|float|bool|str: 转换后的值; 解析失败回退默认 (0/0.0/False/原字符串)。
    """
    if ftype == "INT":
        try:
            return int(float(str(raw).strip()))
        except (TypeError, ValueError):
            return 0
    if ftype == "FLOAT":
        try:
            return float(str(raw).strip())
        except (TypeError, ValueError):
            return 0.0
    if ftype == "BOOLEAN":
        return _to_bool(raw)
    # STRING / TEXT / IMAGE / VIDEO / AUDIO / 未知 -> 原字符串 (TEXT 输出同为 STRING), 前后 trim
    raw = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
    return raw.strip()


# ─── 状态规范化 (兼容旧工作流/缺省值) ────────────────────────────────


def normalize_state(value) -> dict:
    """把前端传回的控件值规范化为 {md_path, fields, selected}。

    兼容: 空值/结构缺字段/字段类型非预期时回退到安全默认, 不抛错。

    参数:
        value (dict|None): 前端控件 getValue 序列化的状态对象。

    返回:
        dict: 规范化状态 {md_path: str, fields: [{name,type}], selected: {id, values}}。
    """
    if not isinstance(value, dict):
        value = {}
    raw_fields = value.get("fields")
    if not isinstance(raw_fields, list):
        raw_fields = []
    fields: list[dict] = []
    seen: set[str] = set()
    for f in raw_fields:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name", "") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        fields.append({"name": name, "type": normalize_type(str(f.get("type", "str")))})
    if not fields:
        fields = [{"name": "ID", "type": "STRING"}]
    fields[0]["type"] = "STRING"  # 首列永远是 ID

    sel = value.get("selected")
    if not isinstance(sel, dict):
        sel = {}
    vals = sel.get("values")
    if not isinstance(vals, dict):
        vals = {}
    # 匹配后统一做前后 trim: ID 与各字段字符串值去首尾空白 (execute 输出 / data JSON 均干净)
    values = {str(k): (str(v).strip() if isinstance(v, str) else v) for k, v in vals.items()}
    return {
        "md_path": str(value.get("md_path", "") or ""),
        "fields": fields,
        "selected": {"id": str(sel.get("id", "") or "").strip(), "values": values},
    }


def build_outputs(state: dict) -> tuple:
    """由规范化状态构建 execute 返回值 (长度恒为 MAX_OUTPUTS, 未用槽为 None)。

    参数:
        state (dict): normalize_state 的输出。

    返回:
        tuple: 长度 MAX_OUTPUTS; [0]=ID, [1..MAX_FIELDS]=非 ID 字段值, [MAX_OUTPUTS-1]=data JSON。
    """
    fields = state["fields"]
    sid = state["selected"]["id"]
    values = state["selected"]["values"]
    out: list = [None] * MAX_OUTPUTS
    out[0] = sid
    for i, f in enumerate(fields[1:MAX_FIELDS], start=1):
        out[i] = coerce_value(values.get(f["name"], ""), f["type"])
    out[MAX_OUTPUTS - 1] = json.dumps({"id": sid, "values": values}, ensure_ascii=False)
    return tuple(out)


def path_basename(path: str) -> str:
    """取绝对路径的文件名 (展示用); 空路径返回空串。

    参数:
        path (str): 绝对路径。

    返回:
        str: basename。
    """
    if not path:
        return ""
    return os.path.basename(path.rstrip("/\\"))
