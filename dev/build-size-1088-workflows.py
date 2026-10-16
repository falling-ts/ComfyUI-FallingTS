#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给「带尺寸下拉」的工作流插入 横1088 / 竖1088 两个档位。

背景
----
0040~0044 走 H3 一采 + LTX-2.5 二采放大到 1088p, **一采档** = 960x544(二采 2x 后成品 1920x1088)。
所以 H3 系工作流(0013 / 0014 / 0030~0033 / 0040~0044, 共 11 个)的

    横1088 = 960x544, 竖1088 = 544x960

与既有的 横544/竖544 **数值相同** —— 是同一对常量节点的「别名档位」;
而 Qwen-Image 系(00110 / 00200)的尺寸直接喂 EmptyLatentImage, 不受 H3 的
MAX_PIXELS = 768x1344 与「短边 <= 768」约束, 取真值

    横1088 = 1920x1088, 竖1088 = 1088x1920。

档位顺序(用户指定)
------------------
    默认 -> 横1088 -> 竖1088 -> 横768 -> 竖768 -> 横544 -> 竖544 -> 横480 -> 竖480

为什么必须整体重建接线
--------------------
FallingTSSelector 的左侧输入端口数 = total(组数) x M(组名数), 后端按

    input{(i-1)*M + k + 1}

取值 —— **M 是除数**: 在中间插入档位会移动其后所有端口的含义。本脚本以
「档位名 -> (组1 宽, 组2 高)」为唯一真相源**重建** inputs 与连线, 而不是就地插值。

幂等
----
以档位名为键重建(而非增量追加): 已合规的工作流重建结果与现状逐字节一致,
逐字节比较后**内容相同就不写盘**。缩进式(indent=2)与压缩式两种存档格式各按原格式 dump。

用法
----
    python custom_nodes/ComfyUI-FallingTS/dev/build-size-1088-workflows.py --check   # 只报告
    python custom_nodes/ComfyUI-FallingTS/dev/build-size-1088-workflows.py           # 写盘
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WF_DIR = ROOT / "workflows"

SELECTOR = "FallingTSSelector"
ITEMS_OLD = "默认,横768,竖768,横544,竖544,横480,竖480"
ITEMS_NEW = "默认,横1088,竖1088,横768,竖768,横544,竖544,横480,竖480"
SLOTS = ITEMS_NEW.split(",")  # 9 个组名 -> 后端取值公式的 M = 9
NEW_SLOTS = ("横1088", "竖1088")
SLOT_H = 20     # 每个动态端口行的渲染高度(实测: 14 端口 366px, 9 端口 266px -> 20px/行)

# 档位 -> (组1 宽, 组2 高); "默认" 取 md 表列(保留原连线), 不在表内
H3_VALUES = {
    "横1088": (960, 544),
    "竖1088": (544, 960),
    "横768": (1344, 768),
    "竖768": (768, 1344),
    "横544": (960, 544),
    "竖544": (544, 960),
    "横480": (832, 480),
    "竖480": (480, 832),
}
QWEN_VALUES = dict(H3_VALUES)
QWEN_VALUES.update({
    "横1088": (1920, 1088),
    "竖1088": (1088, 1920),
})


def _dump(wf: dict, fmt: str) -> str:
    """按原存档格式序列化(两种格式的 json.dumps 参数各自与原文逐字节对齐)。"""
    if fmt == "indent2":
        return json.dumps(wf, ensure_ascii=False, indent=2)
    return json.dumps(wf, ensure_ascii=False, separators=(",", ":"))


def _read(path: Path):
    """读工作流并识别其存档格式(indent2 / compact)。"""
    raw = path.read_text(encoding="utf-8")
    fmt = "indent2" if raw.startswith('{\n  "') else "compact"
    return json.loads(raw), fmt


def _selector(wf: dict):
    """取出尺寸下拉节点(按 items 精确匹配, 兼容已加档与未加档两种状态)。"""
    for n in wf.get("nodes", []):
        if n.get("type") != SELECTOR:
            continue
        vals = n.get("widgets_values") or [None]
        if vals[0] in (ITEMS_OLD, ITEMS_NEW):
            return n
    return None


def _is_qwen(wf: dict) -> bool:
    """是否 Qwen-Image 系(不含任何 MiniMaxH3 节点) —— 决定 1088 档取真值还是一采档。"""
    return not any(str(n.get("type", "")).startswith("MiniMaxH3") for n in wf.get("nodes", []))


def _prim_col(wf: dict):
    """常量节点所在列(x 的众数)与该列最大 y, 供新建 PrimitiveInt 落位。"""
    prims = [n for n in wf.get("nodes", []) if n.get("type") == "PrimitiveInt"]
    if not prims:
        return None, None
    colx = Counter(n["pos"][0] for n in prims).most_common(1)[0][0]
    maxy = max(n["pos"][1] for n in prims if n["pos"][0] == colx)
    return colx, maxy


def _make_int(value: int, nid: int, x: int, y: int, order: int) -> dict:
    """照抄既有 PrimitiveInt 的结构造一个新常量节点。"""
    return {
        "id": nid,
        "type": "PrimitiveInt",
        "pos": [x, y],
        "size": [270, 150],
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [
            {"localized_name": "数值", "name": "value", "type": "INT", "widget": {"name": "value"}, "link": None}
        ],
        "outputs": [{"localized_name": "整数", "name": "INT", "type": "INT", "links": []}],
        "properties": {
            "Node name for S&R": "PrimitiveInt",
            "ue_properties": {"widget_ue_connectable": {}, "input_ue_unconnectable": {}, "version": "7.8"},
        },
        "widgets_values": [value, "fixed"],
        "widgets_values_named": {"value": value, "fixed": "fixed"},
    }


def _process(wf: dict, sel: dict) -> str:
    """就地重建某个 selector 的档位与接线; 返回一句改动摘要。"""
    sid = sel["id"]
    links = wf["links"]
    nodes = wf["nodes"]
    first = (sel.get("widgets_values") or [None])[0] == ITEMS_OLD
    values = QWEN_VALUES if _is_qwen(wf) else H3_VALUES

    # ---- 1) 旧端口: 索引 -> (档位名, 组号), 并记下各档位原连线 ----
    old_key_by_idx: dict[int, tuple[str, int]] = {}
    old_link: dict[tuple[str, int], int | None] = {}
    seen: dict[str, int] = {}
    for i, p in enumerate(sel.get("inputs", [])):
        if p.get("widget"):
            continue
        name = p.get("localized_name")
        g = seen.get(name, 0)
        seen[name] = g + 1
        old_key_by_idx[i] = (name, g)
        old_link[(name, g)] = p.get("link")

    # ---- 2) 新顺序: 组1 九档在前, 组2 九档在后(前 3 个槽是 items/total/selection 控件) ----
    order = [(s, g) for g in (0, 1) for s in SLOTS]
    idx_of = {k: 3 + j for j, k in enumerate(order)}

    # ---- 3) 旧连线重映射 dst_slot ----
    for l in links:
        if l[3] == sid:
            l[4] = idx_of[old_key_by_idx[l[4]]]

    # ---- 4) 补齐新档位的连线(指向 960/544 或 1920/1088 常量) ----
    colx, maxy = _prim_col(wf)
    next_lid = max([l[0] for l in links] + [0])
    next_nid = max([n["id"] for n in nodes] + [0])
    next_order = max([n.get("order", 0) for n in nodes] + [0])
    made_nodes = 0

    def ensure_int(value: int) -> dict:
        """取值为 value 的 PrimitiveInt 节点; 没有就新建一个(落常量列底部)。"""
        nonlocal next_nid, made_nodes
        for n in nodes:
            if n.get("type") == "PrimitiveInt" and (n.get("widgets_values") or [None])[0] == value:
                return n
        next_nid += 1
        made_nodes += 1
        node = _make_int(value, next_nid, colx, maxy + 210 * made_nodes, next_order + made_nodes)
        nodes.append(node)
        return node

    def add_link(src: dict, dst_slot: int) -> int:
        """建一条 src.out0 -> selector.dst_slot 的 INT 连线并双向登记。"""
        nonlocal next_lid
        next_lid += 1
        out = src["outputs"][0]
        if out.get("links") is None:
            out["links"] = []
        out["links"].append(next_lid)
        links.append([next_lid, src["id"], 0, sid, dst_slot, "INT"])
        return next_lid

    added = 0
    for slot in NEW_SLOTS:
        for g in (0, 1):
            key = (slot, g)
            if old_link.get(key) is not None:
                continue
            if colx is None:
                raise RuntimeError(f"{slot} 组{g + 1}: 找不到常量列, 无法新建 PrimitiveInt")
            src = ensure_int(values[slot][g])
            add_link(src, idx_of[key])
            added += 1

    # ---- 5) 重建 inputs 数组 ----
    widget_slots = [p for p in sel.get("inputs", []) if p.get("widget")]
    new_dyn = []
    for slot, g in order:
        new_dyn.append({
            "localized_name": slot,
            "name": f"input{len(new_dyn) + 1}",
            "type": "*",
            "link": old_link.get((slot, g)) if (slot, g) in old_link else None,
        })
    # 新档位的连线已在第 4 步写入 links, 这里按 links 回填端口上的 link
    link_at_slot = {l[4]: l[0] for l in links if l[3] == sid}
    for j, p in enumerate(new_dyn):
        p["link"] = link_at_slot.get(3 + j)
    sel["inputs"] = widget_slots + new_dyn

    # ---- 6) 档位文本 ----
    sel["widgets_values"][0] = ITEMS_NEW
    if isinstance(sel.get("widgets_values_named"), dict) and "items" in sel["widgets_values_named"]:
        sel["widgets_values_named"]["items"] = ITEMS_NEW

    # ---- 7) 首次执行: 节点加高 4 行, 并把它正下方被压到的节点让开 ----
    if first:
        x, y = sel["pos"]
        old_bot = y + sel["size"][1]
        sel["size"][1] += len(NEW_SLOTS) * 2 * SLOT_H
        new_bot = y + sel["size"][1]
        w = sel["size"][0]
        for n in nodes:
            if n["id"] == sid:
                continue
            nx, ny = n["pos"]
            nw = n["size"][0]
            if nx + nw <= x or nx >= x + w:
                continue
            if old_bot <= ny < new_bot:
                n["pos"][1] = new_bot + 60

    wf["last_node_id"] = max(n["id"] for n in nodes)
    wf["last_link_id"] = max(l[0] for l in links)

    return (f"selector #{sid} 档位 {len(SLOTS)} 个 / 动态端口 {len(new_dyn)} 个, "
            f"新增连线 {added} 条, 新建常量 {made_nodes} 个")


def main() -> int:
    ap = argparse.ArgumentParser(description="给尺寸下拉插入 横1088 / 竖1088 档位")
    ap.add_argument("--check", action="store_true", help="只报告差异, 不写盘")
    args = ap.parse_args()

    written = 0
    for path in sorted(WF_DIR.glob("*.json")):
        wf, fmt = _read(path)
        sel = _selector(wf)
        if sel is None:
            continue
        note = _process(wf, sel)
        out = _dump(wf, fmt)
        before = _dump(json.loads(path.read_text(encoding="utf-8")), fmt)
        if out == before:
            print(f"  同 {path.name}: {note}")
            continue
        if not args.check:
            path.write_text(out, encoding="utf-8")
        print(f"{'检查' if args.check else '  写'} {path.name}: {note}")
        written += 1

    print(f"\n{'待修改' if args.check else '已修改'} {written} 个工作流")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
