# -*- coding: utf-8 -*-
"""生成 workflows/0016_建模拆图.json (幂等, 无 md 数据表)。

工作流是**两套完全独立的节点流**, 各自一个加载图片节点(源图、序列号、名称、
文件名前缀全部互不相干):

    流一(四宫)  拼板图加载(序列号 00001) → 等分网格 2×2 → 取第 1..4 块
              → 4 个自动保存, 后缀 左上/右上/左下/右下
    流二(九宫)  拼板图加载(序列号 00002) → 等分网格 3×3 → 取第 1..9 块
              → 9 个自动保存, 后缀 左上/上边/右上/左边/中间/右边/左下/下边/右下

两套流的两条竖向带上下排开(四宫带在上、九宫带在下), 不共用任何节点 ——
因此四宫的 `_左上.png` 与九宫的 `_左上.png` 前缀不同(各自的序列号_名称),
即便落到同一目录也不会互相覆盖。

两处口径说明:
- **网格拆分 = `easy imageSplitGrid`**(ComfyUI-Easy-Use, 已装): 输入 images + row/column
  两个**格数**整数, 内部 `width // column` 等分后沿批维拼接, 不重叠。它与易混淆的
  同名易错点: 官方 `SplitImageToTileList` 是按**像素**步长滑窗(块数由图长算出、边缘补齐),
  不是等分宫格; `ImageGridtoBatch`(KJNodes) 是反方向(拼网格 → 批)。
- **取批次 = `ImageFromBatch`**(核心 image/batch): batch_index=i, length=1 取第 i 张。
  不用 `ImageBatchSplitter //Inspire`: 它的输出端口由前端按 split_count 动态增删
  (末位还会多一个 'remained'), 存档 JSON 里的端口与连线对不上, 每次加载都要等前端重排。
- **落盘前缀**取自**本流自己**的加载图像节点 prefix 输出(与 0050/0051/0070/0035 同一口径),
  保存节点只用自己的 filename_suffix 区分方位 ⇒ 如 `00001_陈落_左上.png`。

无 md 数据表节点(与 0050/0051/0070 同口径), 故产物目录退回工作流名 `0016_建模拆图`。
⚠️ 两个加载节点因此落在**同一目录**,「刷新序列号」取的都是该目录里已有编号的最大值 + 1 ——
即两个流默认会拿到**同一个**序列号(不会出现互相撞号的续号)。要真正错开请手改其中一个的
「序列号」, 或把两条流分到两个工作流里。

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
# 每条流内部的纵向次序, 由「端口顺序规范」倒推(做法同 0035 把加载节点压到同一水平带):
#
#   ① 保存节点输入 0 = images(上游 取批次)、输入 1 = filename_prefix(上游 加载图像)
#      ⇒ 本流的加载图像必须**低于本流每一个取批次节点**, prefix 线才都是从下往右上、不交叉;
#   ② 加载图像输出 0 = IMAGE(下游 网格节点)、输出 2 = prefix(下游 保存节点)
#      ⇒ 本流的网格节点必须**高于本流每一个保存节点**。
#
# 自上而下: 取批次(本流块数) → 网格 → 加载图像 → 自动保存(本流块数)。
# 加载图像只在第 0 列, 它的 prefix 线走**本流下方空白带**绕到第 3 列, 不穿过任何节点。
Y_PICK_STEP = PICK_H + 80               # 220
Y_SAVE_STEP = SAVE_H + 80               # 480


def band_y(base, n_pick, n_save):
    """给定一条流的起始 y, 返回该流六个关键 y(取批次/网格/加载/保存)。"""
    y_pick = base
    y_load = base + n_pick * Y_PICK_STEP + 80
    y_save = y_load + 100
    y_split = y_load - SPLIT_H - 80
    return y_pick, y_split, y_load, y_save

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

    def build_flow(base, load_id, split_id, rows, cols, suffixes, titles,
                   name_widget, sequence_widget, title_tag):
        """铺一套**完全独立**的流: 自己的加载图片节点 + 网格 + 逐块自动保存。"""
        nonlocal order
        n = cols * rows
        y_pick, y_split, y_load, y_save = band_y(base, n, n)

        # 本流的加载图片节点(源图/序列号/名称/前缀全归本流)
        load_prefix_links = []
        load = _node(
            load_id,
            "FallingTSLoadImage",
            (X_LOAD, y_load),
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
            title=f"拼板图 加载 · {title_tag}",
            widgets=[name_widget, "", False, None, "image", sequence_widget, None],
            order=order,
        )
        nodes.append(load)
        node_by_id[load_id] = load
        order += 1

        split_links = []
        split = _node(
            split_id,
            "easy imageSplitGrid",
            (X_SPLIT, y_split),
            (SPLIT_W, SPLIT_H),
            [_in("images", "IMAGE")],
            [_out("images", "IMAGE", split_links)],
            title=f"等分网格 {cols}×{rows} · {title_tag}",
            widgets=[rows, cols],
            order=order,
        )
        nodes.append(split)
        node_by_id[split_id] = split
        order += 1
        add_link(load_id, 0, split_id, 0, "IMAGE")

        for i, (suffix, cell) in enumerate(zip(suffixes, titles)):
            pick_id = split_id + 1 + i
            save_id = pick_id + 1000

            pick_links = []
            pick = _node(
                pick_id,
                "ImageFromBatch",
                (X_PICK, y_pick + i * Y_PICK_STEP),
                (PICK_W, PICK_H),
                [_in("image", "IMAGE"), _in("batch_index", "INT"), _in("length", "INT")],
                [_out("IMAGE", "IMAGE", pick_links)],
                title=f"取第 {i + 1} 块 · {title_tag}",
                widgets=[i, 1],
                order=order,
            )
            nodes.append(pick)
            node_by_id[pick_id] = pick
            order += 1
            add_link(split_id, 0, pick_id, 0, "IMAGE")

            save_links = []
            save = _node(
                save_id,
                "AutoSaveImage",
                (X_SAVE, y_save + i * Y_SAVE_STEP),
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
                title=f"保存 {cell} · {title_tag}",
                widgets=["", suffix, "png", "8-bit", "sRGB", ""],
                order=order,
            )
            nodes.append(save)
            node_by_id[save_id] = save
            order += 1
            add_link(pick_id, 0, save_id, 0, "IMAGE")
            add_link(load_id, 2, save_id, 1, "STRING")

        # 本流最低点(供下一条流从下方起带, 保证两带不重叠)
        return max(y_load + LOAD_H, y_split + SPLIT_H,
                   y_pick + (n - 1) * Y_PICK_STEP + PICK_H,
                   y_save + (n - 1) * Y_SAVE_STEP + SAVE_H)

    # 流一: 四宫(上带)。流二: 九宫(下带)。
    BAND_GAP = 300
    bottom4 = build_flow(0, 1, 10, 2, 2, SUFFIX4, SUFFIX4_TITLES,
                         "建模拆图", "00001", "四宫")
    build_flow(bottom4 + BAND_GAP, 2, 30, 3, 3, SUFFIX9, SUFFIX9_TITLES,
               "建模拆图", "00002", "九宫")

    workflow = {
        "id": None,
        "revision": 0,
        "last_node_id": max(x["id"] for x in nodes),
        "last_link_id": next_link - 1,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.35, "offset": [120, 120]},
                  "ue_links": [], "links_added_by_ue": []},
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
                    if nodes[a[0]]["pos"][1] > nodes[b[0]]["pos"][1]:
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

    # 3 不重叠(全对判定)
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

    # 3b 纵向边距: 只判**同列内按 y 排序真正相邻**的一对。>300 视为「两条流之间的
    # 刻意留白/远距节点」(规范第 3 条: 远距节点之间不判上限), 仍然如实报出。
    FAR = 300
    by_col: dict[int, list[int]] = {}
    for nid in nodes:
        by_col.setdefault(nodes[nid]["pos"][0], []).append(nid)
    for x, group in by_col.items():
        group.sort(key=lambda nid: nodes[nid]["pos"][1])
        for a, b in zip(group, group[1:]):
            gap = nodes[b]["pos"][1] - (nodes[a]["pos"][1] + nodes[a]["size"][1])
            if gap <= 50:
                problems.append(f"{nodes[a]['type']}#{a} 与 {nodes[b]['type']}#{b} 同列纵向净距 {gap} 太挤")
            elif 100 <= gap < FAR:
                problems.append(f"{nodes[a]['type']}#{a} 与 {nodes[b]['type']}#{b} 同列纵向净距 {gap} 超出 (50,100)")

    # 3c 横向边距: 逐列看**下一列里 y 区间与之相交**的节点(同排横向相邻)。
    cols = sorted(by_col)
    for ci, x in enumerate(cols):
        if ci + 1 >= len(cols):
            continue
        nx = cols[ci + 1]
        for a in by_col[x]:
            na = nodes[a]
            for b in by_col[nx]:
                nb = nodes[b]
                if not (na["pos"][1] < nb["pos"][1] + nb["size"][1]
                        and nb["pos"][1] < na["pos"][1] + na["size"][1]):
                    continue
                gap = nb["pos"][0] - (na["pos"][0] + na["size"][0])
                if not 50 < gap < 100:
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
