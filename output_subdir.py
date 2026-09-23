# 产物子目录名解析: 工作流里有 md 数据表时用「表文件名」, 没有才用「工作流名」
#
# 背景: 保存类节点 (PreviewImageSave / PreviewVideo / PreviewAudioSave) 把产物写进
# output/<子目录>/<文件名> 这一层, 子目录名原先取前端点「保存」时传来的当前工作流名。
# 但产物的真正归属是工作流读取的那张 md 数据表 —— 资源表里的跨表引用一律写成
# `@{<表文件名>/<行 ID>}`, 而 mdtable 的解析器严格按 output/<表文件名>/ 找文件
# (命中不了才退回递归兜底)。两者不一致时 (如 QI2.1 变体工作流、表改名后), 产物就落在
# 引用解析找不到的目录里, 只能靠兜底命中 —— 表名与目录名一致才能走严格命中。
#
# 故本模块统一口径: 工作流里存在 FallingTSMarkDownTable 节点时, 用该节点 `data.md_path`
# 的文件名(去扩展名)作子目录名; 没有 md 表节点时才退回工作流名。这与
# `stories/AGENTS.md` 的「`@{...}` 斜杠前那段 = 表文件名 = 产物目录名」一致。
#
# 导入方式与 numbered_subdirs.py 相同: 插件根目录已被 __init__.py 加进 sys.path,
# 三个预览节点直接 `import output_subdir` 即可(它们的目录名含连字符, 只能按名加载)。

from __future__ import annotations

import os

# md 数据表节点的 class_type (与 mdtable/nodes.py 的注册名一致)
MD_TABLE_CLASS = "FallingTSMarkDownTable"

# 目录名里不允许出现的字符(Windows 非法字符 + 路径分隔符)
_UNSAFE_CHARS = '<>:"/\\|?*'


def safe_dir_name(name) -> str:
    """把工作流名/表文件名清洗成可安全用作单层目录名的字符串。

    参数:
        name (str|None): 原始名字(可能含 .json 后缀或完整路径)。

    返回:
        str: 清洗后的目录名; 空串表示不该建子目录(退回 output 根)。
    """
    text = str(name or "").strip()
    if not text:
        return ""
    # 只取路径末段, 防 ../ 穿越
    text = text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if text.lower().endswith(".json"):
        text = text[:-5]
    for ch in _UNSAFE_CHARS:
        text = text.replace(ch, "_")
    text = text.strip().strip(".")
    return "" if text in ("", ".", "..") else text


def _node_order(node_id) -> tuple:
    """排序键: 纯数字节点 id 按数值排, 其余按字符串排在后面。"""
    text = str(node_id)
    return (0, int(text), "") if text.isdigit() else (1, 0, text)


def md_table_name(prompt) -> str:
    """从 API prompt 里找 md 数据表节点, 取它 `data.md_path` 的文件名(去扩展名)作子目录名。

    同图出现多个 md 表节点时取节点 id 最小的那个 —— 一个工作流正常只读一张表,
    取固定顺序只为保证结果确定, 不随 dict 遍历顺序变化。

    参数:
        prompt (dict|None): 引擎注入的 API prompt {节点 id: {"class_type":..., "inputs": {...}}}。

    返回:
        str: 清洗后的表文件名(如 "0011_万物建模"); 空串表示工作流里没有可用的 md 表节点。
    """
    if not isinstance(prompt, dict):
        return ""
    for node_id in sorted(prompt, key=_node_order):
        node = prompt.get(node_id)
        if not isinstance(node, dict) or node.get("class_type") != MD_TABLE_CLASS:
            continue
        data = node.get("inputs", {}).get("data")
        raw = data.get("md_path") if isinstance(data, dict) else None
        # 先剥扩展名再清洗: md_path 形如 "stories/七纹刻印/0011_万物建模.md"
        name = safe_dir_name(os.path.splitext(str(raw or ""))[0])
        if name:
            return name
    return ""


def resolve_subdir(workflow_name, prompt=None) -> str:
    """解析产物子目录名: 优先 md 数据表的表文件名, 无 md 表才退回工作流名。

    参数:
        workflow_name (str|None): 前端点「保存」时传来的当前工作流名。
        prompt (dict|None): 该节点 execute 时缓存的 API prompt(用于找 md 表节点)。

    返回:
        str: 子目录名; 空串表示不建子目录(退回 output 根)。
    """
    return md_table_name(prompt) or safe_dir_name(workflow_name)
