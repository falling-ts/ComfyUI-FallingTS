# -*- coding: utf-8 -*-
"""生成 workflows/0016_建模拆图.json (幂等, 无 md 数据表)。

工作流结构(两套并行节点流, 共用同一个「加载图像」节点):

    加载图像(FallingTSLoadImage)
      ├─ prefix 输出(序列号_名称) ──→ 13 个 AutoSaveImage 的 filename_prefix
      ├─ IMAGE → 网格拆分 2×2 ──→ 取批次 1..4 ──→ 4 个自动保存(左上/右上/左下/右下)
      └─ IMAGE → 网格拆分 3×3 ──→ 取批次 1..9 ──→ 9 个自动保存(左上/上边/右上/左边/中间/
                                                右边/左下/下边/右下)

两处口径说明:
- **网格拆分 = `easy imageSplitGrid`**(ComfyUI-Easy-Use, 已装): 输入 images + row/column
  两个**格数**整数, 内部 `width // column` 等分后沿批维拼接, 不重叠。它与易混淆的
  同名易错点: 官方 `SplitImageToTileList` 是按**像素**步长滑窗(块数由图长算出、边缘补齐),
  不是等分宫格; `ImageGridtoBatch`(KJNodes) 是反方向(拼网格 → 批)。
- **取批次 = `ImageFromBatch`**(核心 image/batch): batch_index=i, length=1 取第 i 张。
  不用 `ImageBatchSplitter //Inspire`: 它的输出端口由前端按 split_count 动态增删
  (末位还会多一个 'remained'), 存档 JSON 里的端口与连线对不上, 每次加载都要等前端重排。
- **落盘前缀**取自加载图像节点的 prefix 输出(与 0050/0051/0070/0035 同一口径), 保存节点
  只用自己的 filename_suffix 区分方位 ⇒ 如 `00001_陈落_左上.png`。

无 md 数据表节点(与 0050/0051/0070 同口径), 故产物目录退回工作流名 `0016_建模拆图`。

布局遵循工作区六规范: 输出在左输入在右、同列无上下游、端口顺序不交叉、纵距 60 横距 80、
功能群聚拢、从起点向右下逐个锁定。本脚本末尾自带六条规范自检。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "workflows" / "0016_建模拆图.json"

# ── 尺寸 ──────────────────────────────────────────────────────────────────
LOAD_W, LOAD_H = 420, 560
SPLIT_W, SPLIT_H = 300, 150
PICK_W, PICK_H = 280, 140
SAVE_W, SAVE_H = 320, 400

# ── 列 x(横距一律 80, 落在 (50,100) 中部) ────────────────────────────────
X_LOAD = 0
X_SPLIT = X_LOAD + LOAD_W + 80          # 500
X_PICK = X_SPLIT + SPLIT_W + 80         # 880
X_SAVE = X_PICK + PICK_W + 80           # 1240

# ── 行 y ──────────────────────────────────────────────────────────────────
# 纵向次序完全由「端口顺序规范」倒推(做法同 0035 把加载节点压到同一水平带):
#
#   ① 保存节点输入 0 = images(上游 取批次)、输入 1 = filename_prefix(上游 加载图像)
#      ⇒ 加载图像必须**低于每一个取批次节点**, 13 条 prefix 线才都是从下往右上、不交叉;
#   ② 加载图像输出 0 = IMAGE(下游 两个网格节点)、输出 2 = prefix(下游 保存节点)
#      ⇒ 两个网格节点必须**高于每一个保存节点**。
#
# 自上而下: 13 个取批次 → 网格 3×3 → 网格 2×2 → 加载图像 → 13 个保存节点。
# 加载图像只在第 0 列, 它的 prefix 线走**下方空白带**绕到第 3 列, 不穿过任何节点。
Y_PICK = 0
Y_PICK_STEP = PICK_H + 80               # 220
Y_LOAD = 13 * Y_PICK_STEP + 80          # 2940
Y_SPLIT9 = Y_LOAD - SPLIT_H - 80        # 2710
Y_SPLIT4 = Y_SPLIT9 - SPLIT_H - 80      # 2480
Y_SAVE = Y_LOAD + 100                   # 3040
Y_SAVE_STEP = SAVE_H + 80               # 480

SUFFIX4 = ("_左上", "_右上", "_左下", "_右下")
SUFFIX9 = ("_左上", "_上边", "_右上", "_左边", "_中间", "_右边", "_左下", "_下边", "_右下")
# 保存节点的标题/后缀**严格按格位**: 网格节点 row-major 顺序 i*cols + j ⇒
#   2×2 → 0 左上 / 1 右上 / 2 左下 / 3 右下
#   3×3 → 0 左上 / 1 上边 / 2 右上 / 3 左边 / 4 中间 / 5 右边 / 6 左下 / 7 下边 / 8 右下
SUFFIX4_TITLES = ("左上", "右上", "左下", "右下")
SUFFIX9_TITLES = ("左上", "上边", "右上", "左边", "中间", "右边", "左下", "下边", "右下")


def _node(nid, ntype, pos, size, inputs, outputs, title=None, widgets=None, order=0):
    """构造一个节点字典(字段顺序与前端存盘一致)。"""
    node = {
        "id": nid,
        "type": ntype,
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "properties": {
            "Node name for S&R": ntype,
            "ue_properties": {
                "widget_ue_connectable": {},
                "input_ue_unconnectable": {},
                "version": "7.8",
            },
        },
        "widgets_values": list(widgets or []),
    }
    if title:
        node["title"] = title
    return node


def _in(name, itype, link=None, localized=None, widget=None):
    slot = {"localized_name": localized or name, "name": name, "type": itype}
    if widget is not False:
        slot["widget"] = {"name": name}
    slot["link"] = link
    return slot


def _out(name, itype, links=None, slot_index=0, localized=None, label=None):
    slot = {"localized_name": localized or name, "name": name, "type": itype}
    if label:
        slot["label"] = label
    slot["links"] = links if links is not None else []
    if slot_index:
        slot["slot_index"] = slot_index
    return slot


def build() -> dict:
    nodes = []
    links = []
    node_by_id: dict[int, dict] = {}
    next_link = 1
    order = 0

    def add_link(origin, origin_slot, target, target_slot, ltype):
        """登记一条连线: 同时把 link id 回填进两端端口的 links 列表。"""
        nonlocal next_link
        lid = next_link
        next_link += 1
        links.append([lid, origin, origin_slot, target, target_slot, ltype])
        src = node_by_id[origin]["outputs"][origin_slot]
        dst = node_by_id[target]["inputs"][target_slot]
        if src["links"] is not None:
            src["links"].append(lid)
        dst["link"] = lid
        return lid

    # ── 加载图像 ──────────────────────────────────────────────────────────
    load_id = 1
    load_prefix_links = []
    load = _node(
        load_id,
        "FallingTSLoadImage",
        (X_LOAD, Y_LOAD),
        (LOAD_W, LOAD_H),
        [
            _in("name", "STRING", None, "名称"),
            _in("image", "COMBO", None),
            _in("sequence", "STRING", None, "序列号"),
            _in("upload", "IMAGEUPLOAD", None),
        ],
        [
            _out("IMAGE", "IMAGE", []),
            _out("MASK", "MASK", []),
            _out("prefix", "STRING", load_prefix_links, slot_index=2, label="文件名前缀"),
        ],
        title="拼板图 加载",
        widgets=["建模拆图", "", False, None, "image", "00001", None],
        order=order,
    )
    nodes.append(load)
    node_by_id[load_id] = load
    order += 1

    def build_chain(rows, cols, suffixes, titles, split_id, split_y, pick_y0, save_y0):
        """铺一套「等分网格 → 逐块自动保存」的链, 返回 (split_y, save_y)。"""
        nonlocal order
        split_links = []
        split_id_local = split_id
        split = _node(
            split_id_local,
            "easy imageSplitGrid",
            (X_SPLIT, split_y),
            (SPLIT_W, SPLIT_H),
            [_in("images", "IMAGE")],
            [_out("images", "IMAGE", split_links)],
            title=f"等分网格 {cols}×{rows}",
            widgets=[rows, cols],
            order=order,
        )
        nodes.append(split)
        node_by_id[split_id_local] = split
        order += 1
        add_link(load_id, 0, split_id_local, 0, "IMAGE")

        for i, (suffix, title) in enumerate(zip(suffixes, titles)):
            pick_id = split_id_local + 1 + i
            save_id = pick_id + 1000

            pick_links = []
            pick = _node(
                pick_id,
                "ImageFromBatch",
                (X_PICK, pick_y0 + i * Y_PICK_STEP),
                (PICK_W, PICK_H),
                [_in("image", "IMAGE"), _in("batch_index", "INT"), _in("length", "INT")],
                [_out("IMAGE", "IMAGE", pick_links)],
                title=f"取第 {i + 1} 块",
                widgets=[i, 1],
                order=order,
            )
            nodes.append(pick)
            node_by_id[pick_id] = pick
            order += 1
            add_link(split_id_local, 0, pick_id, 0, "IMAGE")

            save_links = []
            save_y = save_y0 + i * Y_SAVE_STEP
            save = _node(
                save_id,
                "AutoSaveImage",
                (X_SAVE, save_y),
                (SAVE_W, SAVE_H),
                [
                    _in("images", "IMAGE"),
                    _in("filename_prefix", "STRING"),
                    _in("filename_suffix", "STRING"),
                    _in("format", "COMBO"),
                    _in("bit_depth", "COMBO"),
                    _in("input_color_space", "COMBO"),
                ],
                [_out("images", "IMAGE", save_links)],
                title=f"保存 {title}",
                widgets=["", suffix, "png", "8-bit", "sRGB", ""],
                order=order,
            )
            nodes.append(save)
            node_by_id[save_id] = save
            order += 1
            add_link(pick_id, 0, save_id, 0, "IMAGE")
            add_link(load_id, 2, save_id, 1, "STRING")

        return

    # 两套链: 4 图链占上方 4 个取批次/保存槽, 9 图链占下方 9 个
    build_chain(2, 2, SUFFIX4, SUFFIX4_TITLES, 10, Y_SPLIT4, Y_PICK, Y_SAVE)
    build_chain(3, 3, SUFFIX9, SUFFIX9_TITLES, 30, Y_SPLIT9, Y_PICK + 4 * Y_PICK_STEP,
                Y_SAVE + 4 * Y_SAVE_STEP)

    load["widgets_values"] = ["建模拆图", "", False, None, "image", "00001", None]

    workflow = {
        "id": None,
        "revision": 0,
        "last_node_id": max(n["id"] for n in nodes),
        "last_link_id": next_link - 1,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.4, "offset": [120, 120]}, "ue_links": [], "links_added_by_ue": []},
        "version": 0.4,
    }
    return workflow


# ── 六规范自检 ────────────────────────────────────────────────────────────

def check(wf: dict) -> list[str]:
    problems = []
    nodes = {n["id"]: n for n in wf["nodes"]}

    def right(nid):
        n = nodes[nid]
        return n["pos"][0] + n["size"][0]

    def bottom(nid):
        n = nodes[nid]
        return n["pos"][1] + n["size"][1]

    # 1 方向: 上游右缘 <= 下游左缘
    for link in wf["links"]:
        lid, src, _oslot, dst, _tslot, _t = link
        if right(src) > nodes[dst]["pos"][0]:
            problems.append(f"连线 {lid}: 上游 {nodes[src]['type']} 右缘越过下游 {nodes[dst]['type']}")

    # 1b 连线两端端口回填自检(存档 JSON 里 link id 必须落在端口上, 否则前端加载后连线全丢)
    port_link = {}
    for link in wf["links"]:
        lid, src, oslot, dst, tslot, _t = link
        port_link.setdefault((src, oslot, "out"), []).append(lid)
        port_link.setdefault((dst, tslot, "in"), []).append(lid)
    for nid, n in nodes.items():
        for i, o in enumerate(n["outputs"]):
            for lid in o["links"] or []:
                if lid not in port_link.get((nid, i, "out"), []):
                    problems.append(f"{n['type']}#{nid} 输出 {i} 挂了不存在的连线 {lid}")
        for j, inp in enumerate(n["inputs"]):
            lid = inp["link"]
            if lid is not None and lid not in port_link.get((nid, j, "in"), []):
                problems.append(f"{n['type']}#{nid} 输入 {j} 挂了不存在的连线 {lid}")

    # 2 端口顺序: 同一节点多输入/多输出, 上下游纵向顺序必须一致
    by_target = {}
    by_origin = {}
    for link in wf["links"]:
        lid, src, oslot, dst, tslot, _t = link
        by_target.setdefault((dst, tslot), (src, oslot))
        by_origin.setdefault((src, oslot), []).append((dst, tslot))
    for nid in nodes:
        n = nodes[nid]
        for i in range(len(n["inputs"])):
            for j in range(i + 1, len(n["inputs"])):
                a = by_target.get((nid, i))
                b = by_target.get((nid, j))
                if a and b and a[0] != b[0]:
                    y0 = nodes[a[0]]["pos"][1]
                    y1 = nodes[b[0]]["pos"][1]
                    if y0 > y1:
                        problems.append(f"{n['type']}#{nid} 输入 {i}/{j} 上游顺序倒置")
        for i in range(len(n["outputs"])):
            for j in range(i + 1, len(n["outputs"])):
                a = by_origin.get((nid, i))
                b = by_origin.get((nid, j))
                if not a or not b:
                    continue
                da = sorted(nodes[d]["pos"][1] for d, _s in a)
                db = sorted(nodes[d]["pos"][1] for d, _s in b)
                if any(da[k] > db[k] for k in range(min(len(da), len(db)))):
                    problems.append(f"{n['type']}#{nid} 输出 {i}/{j} 下游顺序倒置")

    # 3 不重叠 + 相邻边距 (50,100)
    # 边距只对**同一列内纵向相邻**、或**同一行内横向相邻**的节点判定(不同列之间隔着别的列,
    # 远距节点之间不判上限 —— 见工作区布局规范第 3 条)。
    ids = sorted(nodes)
    for i, a in enumerate(ids):
        na = nodes[a]
        ax0, ay0 = na["pos"]
        ax1, ay1 = ax0 + na["size"][0], ay0 + na["size"][1]
        for b in ids[i + 1:]:
            nb = nodes[b]
            bx0, by0 = nb["pos"]
            bx1, by1 = bx0 + nb["size"][0], by0 + nb["size"][1]
            if ax1 > bx0 and bx1 > ax0 and ay1 > by0 and by1 > ay0:
                problems.append(
                    f"{na['type']}#{a} 与 {nb['type']}#{b} 重叠 "
                    f"(x {max(ax0, bx0)}..{min(ax1, bx1)}, y {max(ay0, by0)}..{min(ay1, by1)})"
                )
                continue
    # 边距只对**同列内真正相邻的一对**(按 y 排序的相邻两个)判定; 同列远距节点之间
    # 不判上限 —— 见工作区布局规范第 3 条(「远距节点之间不判上限」)。
    by_col: dict[int, list[int]] = {}
    for nid in nodes:
        by_col.setdefault(nodes[nid]["pos"][0], []).append(nid)
    for x, group in by_col.items():
        group.sort(key=lambda nid: nodes[nid]["pos"][1])
        for a, b in zip(group, group[1:]):
            gap = nodes[b]["pos"][1] - (nodes[a]["pos"][1] + nodes[a]["size"][1])
            if not 50 < gap < 100:
                problems.append(
                    f"{nodes[a]['type']}#{a} 与 {nodes[b]['type']}#{b} 同列纵向净距 {gap} 不在 (50,100)"
                )

    # 横向: 按 x 排序, 只看 y 区间相接且 x 相邻的一对
    ids2 = sorted(nodes)
    for a, b in zip(ids2, ids2[1:]):
        na, nb = nodes[a], nodes[b]
        gap = nb["pos"][0] - (na["pos"][0] + na["size"][0])
        overlap_y = (
            na["pos"][1] < nb["pos"][1] + nb["size"][1]
            and nb["pos"][1] < na["pos"][1] + na["size"][1]
        )
        if 0 < gap and overlap_y and not 50 < gap < 100:
            problems.append(
                f"{na['type']}#{a} 与 {nb['type']}#{b} 横向净距 {gap} 不在 (50,100)"
            )

    return problems


def main() -> None:
    wf = build()
    problems = check(wf)
    OUT.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"写入 {OUT}")
    print(f"节点 {len(wf['nodes'])} / 连线 {len(wf['links'])}")
    if problems:
        print("布局/结构自检: 有问题")
        for p in problems:
            print("  -", p)
    else:
        print("布局/结构自检: 无问题")


if __name__ == "__main__":
    main()
