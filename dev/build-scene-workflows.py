# -*- coding: utf-8 -*-
"""生场景工作流的「预览视频 → 0035 后续链」拼接: 0030 / 0031 / 0032。

## 做什么

把 0035_场景截帧 那条**截帧后续链**(8 个单向保存 + 2 个合成 + 2 个合成保存, 共 12 个
AutoSaveImage 与 FallingTSImageComposite)整条复制到每个生场景工作流的 PreviewVideo 之后,
端口按 0035 的口径对齐:

    PreviewVideo.video(0)   ... 原样, 不影响
    PreviewVideo.prefix(2)  → 每个保存节点的 filename_prefix(一条线分发 12 个)
    PreviewVideo.image_1..N(3 起) → 8 个单向保存 + 2 个合成的对应格

## 为什么用脚本而不是手改

四个工作流的改法**完全一致**, 且必须幂等 —— 手工改 4 份 JSON 既容易漏、也无法复核。
本脚本可反复跑: 第二次跑会先撤掉上次插入的尾部节点(按类型+标题识别)再重建, 不叠加。

## 与 0035 的关系

0035 的链由 build-decompose-workflows.py 的 fix_0035() 维护; 本脚本**从 0035 现读模板**
(json 里的节点定义), 于是 0035 那边的后缀/标题变化能自动带过来, 不必两处同步。
唯一的例外是「前缀来源」: 0035 接的是 FallingTSLoadVideo 的 prefix 输出, 这里改接
PreviewVideo 的 prefix 输出(二者同名同类型, 只需改链路两端)。

## 产物目录

不额外设置: 四个生场景工作流都带 md 数据表, output_subdir.resolve_subdir 会优先取表名,
所以截帧产物落 output/<表名>/(与资源表 @{} 引用口径一致)。

跑法(工作区根): python custom_nodes/ComfyUI-FallingTS/dev/build-scene-workflows.py
"""

from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent.parent
WF_DIR = ROOT / "workflows"

PREVIEW_VIDEO = "PreviewVideo"
COMPOSITE = "FallingTSImageComposite"
AUTO_SAVE_IMAGE = "AutoSaveImage"

# 要拼接的目标工作流(按用户确认的范围: 三个「生场景」流)
TARGETS = ["0030_文生场景", "0031_首帧场景", "0032_参考场景"]

# 0035 的链: 8 个单向保存(后缀 → 标题), 顺序即 image_1..image_8 的分配顺序
SINGLE_SAVES = [
    ("_前面", "单图 前面"),
    ("_前右", "单图 前右"),
    ("_右面", "单图 右面"),
    ("_右后", "单图 右后"),
    ("_后面", "单图 后面"),
    ("_后左", "单图 后左"),
    ("_左面", "单图 左面"),
    ("_左前", "单图 左前"),
]

# 尾部节点的全部标题, 用于幂等识别与清理。
# ⚠️ 不能只用一个前缀: 链里除「截帧合成…」「八向合成…」外还有 8 个「单图 XX」,
# 漏掉它们会在第二次跑时把上一批节点留在工作流里, 与新节点重号。
TAIL_TITLES = {title for _suffix, title in SINGLE_SAVES} | {
    "截帧合成 一张图",
    "截帧合成 预览/保存",
    "八向合成 一张图",
    "八向合成 预览/保存",
}

# PreviewVideo 固定端口: video(0) / audio(1) / prefix(2), 选中帧自 3 起
PV_PREFIX_SLOT = 2
PV_FRAME_START = 3


def load(name: str) -> dict:
    return json.loads((WF_DIR / (name + ".json")).read_text(encoding="utf-8"))


def save(name: str, wf: dict) -> None:
    text = json.dumps(wf, ensure_ascii=False, separators=(",", ":"))
    (WF_DIR / (name + ".json")).write_text(text, encoding="utf-8")


def node_by_type(wf: dict, node_type: str) -> list:
    return [n for n in wf["nodes"] if n["type"] == node_type]


def next_id(wf: dict) -> int:
    """下一个可用节点 id(实际最大值 + 1)。

    ⚠️ **只看节点列表, 不看 last_node_id**: 本脚本会先 strip_tail 删掉上次插入的一批,
    而 last_node_id 记录的是历史最大值 —— 掺进来会让第二次跑的 id 从上次的最大值继续
    涨(实测: 重跑一次 last_node_id 从 142 涨到 166), 脚本就不幂等了。
    """
    return max(n["id"] for n in wf["nodes"]) + 1


def next_link_id(wf: dict) -> int:
    """下一个可用连线 id(实际最大值 + 1); 不掺 last_link_id, 理由同 next_id。"""
    return max(l[0] for l in wf["links"]) + 1


# ─── 从 0035 取模板 ─────────────────────────────────────────────────────────


def tail_templates() -> dict:
    """从 0035_场景截帧 读出后续链的节点模板(去掉 id/pos/order/连线, 只留结构与控件值)。

    返回 {"singles": {标题: 节点}, "comp4": ..., "comp8": ..., "save4": ..., "save8": ...}。
    节点里带链接的输入槽会被调用方重指向, 故这里把 link 一律清成 None。
    """
    src = load("0035_场景截帧")
    by_type_title = {}
    for n in src["nodes"]:
        by_type_title[(n["type"], n.get("title"))] = n

    def take(node_type: str, title: str) -> dict:
        tpl = json.loads(json.dumps(by_type_title[(node_type, title)]))  # 深拷贝
        tpl["id"] = 0
        tpl["pos"] = [0, 0]
        tpl["order"] = 0
        tpl["mode"] = 0
        for inp in tpl.get("inputs") or []:
            inp["link"] = None
        for out in tpl.get("outputs") or []:
            out["links"] = []
        return tpl

    singles = {title: take(AUTO_SAVE_IMAGE, title) for _suffix, title in SINGLE_SAVES}
    return {
        "singles": singles,
        "comp4": take(COMPOSITE, "截帧合成 一张图"),
        "comp8": take(COMPOSITE, "八向合成 一张图"),
        "save4": take(AUTO_SAVE_IMAGE, "截帧合成 预览/保存"),
        "save8": take(AUTO_SAVE_IMAGE, "八向合成 预览/保存"),
    }


# ─── 幂等: 先撤掉上次插入的尾部 ─────────────────────────────────────────────


def strip_tail(wf: dict) -> int:
    """删掉本脚本上次插入的尾部节点及其连线。

    只认 TAIL_TITLES 里那几个精确标题, 不误删工作流原有节点(0030~0032 原本没有这些标题)。
    返回删掉的节点数。
    """
    doomed = {
        n["id"]
        for n in wf["nodes"]
        if n["type"] in (COMPOSITE, AUTO_SAVE_IMAGE) and (n.get("title") or "") in TAIL_TITLES
    }
    if not doomed:
        return 0
    wf["links"] = [l for l in wf["links"] if l[1] not in doomed and l[3] not in doomed]
    wf["nodes"] = [n for n in wf["nodes"] if n["id"] not in doomed]
    return len(doomed)


# ─── 重连 ──────────────────────────────────────────────────────────────────


def relink(wf: dict) -> None:
    """按 links 表重建每个节点的输入/输出槽指向(与 build-decompose-workflows.py 同款)。

    前端序列化格式里, 连线同时记在三处: 全局 links 表、目标节点的 inputs[].link、
    源节点的 outputs[].links。改完 links 表后必须把后两者重建, 否则前端加载时端口是空的。
    """
    by_id = {n["id"]: n for n in wf["nodes"]}
    for n in wf["nodes"]:
        for inp in n.get("inputs") or []:
            inp["link"] = None
        for out in n.get("outputs") or []:
            out["links"] = []
    for link in wf["links"]:
        _lid, src, src_slot, dst, dst_slot = link[0], link[1], link[2], link[3], link[4]
        s = by_id.get(src)
        d = by_id.get(dst)
        if s is None or d is None:
            continue
        if src_slot < len(s.get("outputs") or []):
            s["outputs"][src_slot].setdefault("links", []).append(_lid)
        if dst_slot < len(d.get("inputs") or []):
            d["inputs"][dst_slot]["link"] = _lid


# ─── 布局: 四列网格(与 0035 的 layout_0035 同口径) ─────────────────────────

GAP_X = 80
GAP_Y = 60


def layout(wf: dict, pv: dict, singles: list, comp4: dict, comp8: dict, save4: dict, save8: dict) -> None:
    """四列网格: 预览视频(源) → 8 单图保存 → 2 合成 → 2 合成保存。

    直接**平移复刻 0035 的实测布局**, 而不是另算一套: 0035 里这条链的列距正好是
    「前一列右缘 + 80」(loadvideo 右缘 970 → 单图 1050 → 合成 1660 → 合成保存 2040),
    行距 60(单图 550 高 + 60 = 610), 完全落在布局规范的 (50,100) 内。
    只需把 0035 的 (1050, 40) 锚点平移到本工作流的 (单图列 x, pv_y) 即可 —— 这样
    两个合成相对单图列的高度关系(comp8 落在单图列中段, 而不是紧贴 comp4)也一并继承。

    **不动 PreviewVideo 的位置**: 它是链的源头, 四个目标工作流里它右侧都是空的(改前已核)。
    """
    pv_x, pv_y = pv["pos"]
    x1 = pv_x + pv["size"][0] + GAP_X

    # 0035 的锚点与各列 x
    REF_X, REF_Y = 1050, 40
    dx, dy = x1 - REF_X, pv_y - REF_Y

    def moved(ref_pos):
        return [ref_pos[0] + dx, ref_pos[1] + dy]

    # 列 1: 8 个单图保存(统一成 0035 的 530x550, 行距 60)
    single_w, single_h = 530, 550
    for i, n in enumerate(singles):
        n["size"] = [single_w, single_h]
        n["pos"] = [x1, pv_y + i * (single_h + GAP_Y)]

    comp4["pos"] = moved([1660, 40])
    comp8["pos"] = moved([1660, 1410])
    save4["pos"] = moved([2040, 40])
    save8["pos"] = moved([2040, 880])


# ─── 主流程 ────────────────────────────────────────────────────────────────


def build(name: str) -> dict:
    wf = load(name)
    removed = strip_tail(wf)
    if removed:
        print(f"  {name}: 撤掉上次插入的 {removed} 个尾部节点")

    pv = node_by_type(wf, PREVIEW_VIDEO)[0]
    tpl = tail_templates()

    # ① 预览视频: 补齐 audio/prefix + 选中帧端口(0030~0032 原本只有 video 一个输出)
    old_out = pv.get("outputs") or []
    # 保留原有 video 端口的连线(它就是 CreateVideo 的结果), 其余重建
    new_outputs = [
        {"localized_name": "video", "name": "video", "type": "VIDEO", "links": []},
        {"localized_name": "audio", "name": "audio", "type": "AUDIO", "links": []},
        {
            "localized_name": "prefix",
            "label": "文件名前缀",
            "name": "prefix",
            "type": "STRING",
            "links": [],
        },
    ]
    # 从原输出里搬回 video 端口上的连线(按名字匹配, 保证幂等: 第二次跑时 video 已在 slot 0)
    old_by_name = {o.get("name"): o for o in old_out}
    video_links = list((old_by_name.get("video") or {}).get("links") or [])
    new_outputs[0]["links"] = video_links
    frames = 8
    for i in range(1, frames + 1):
        new_outputs.append(
            {
                "label": "选中帧 " + str(i),
                "localized_name": "选中帧 " + str(i),
                "name": "image_" + str(i),
                "type": "IMAGE",
                "links": [],
            }
        )
    for slot, o in enumerate(new_outputs):
        o["slot_index"] = slot
    pv["outputs"] = new_outputs

    # 控件槽序必须与前端 onNodeCreated 的注册顺序一致(否则存档加载后整体错位):
    #   [前缀, 后缀, 保存, 截帧, 完成, 输出帧数, frame_list, video_fallback]
    # 依据: 老存档 PreviewVideo 是 4 槽 [前缀, 后缀, 保存=None, video_fallback],
    # 与本节点「每个 widget 在 widgets_values 占一槽、按钮占 None」的口径吻合;
    # 「加载视频」的 12 槽存档同样是 12 个 named 键一一对应。⇒「输出帧数」在下标 5,
    # 前端 onConfigure 的 `_wv[5]` 兜底正是指它。
    named = pv.get("widgets_values_named") or {}
    prefix_value = named.get("filename_prefix", "")
    suffix_value = named.get("filename_suffix", "")
    pv["widgets_values"] = [prefix_value, suffix_value, None, None, None, frames, {"frames": []}, ""]
    pv["widgets_values_named"] = {
        "filename_prefix": prefix_value,
        "filename_suffix": suffix_value,
        "保存": None,
        "截帧": None,
        "完成": None,
        "输出帧数": frames,
        "frame_list": {"frames": []},
        "video_fallback": "",
    }
    props = pv.setdefault("properties", {}).setdefault("ue_properties", {})
    props["widget_ue_connectable"] = {"filename_prefix": True, "filename_suffix": True}

    all_singles_needed = [title for _s, title in SINGLE_SAVES]
    singles = [json.loads(json.dumps(tpl["singles"][t])) for t in all_singles_needed]
    comp4 = json.loads(json.dumps(tpl["comp4"]))
    comp8 = json.loads(json.dumps(tpl["comp8"]))
    save4 = json.loads(json.dumps(tpl["save4"]))
    save8 = json.loads(json.dumps(tpl["save8"]))

    # ② 分配 id / link id
    nid = next_id(wf)
    lid = next_link_id(wf)
    for n in singles + [comp4, comp8, save4, save8]:
        n["id"] = nid
        nid += 1
    nid_single = [n["id"] for n in singles]
    nid_comp4, nid_comp8, nid_save4, nid_save8 = comp4["id"], comp8["id"], save4["id"], save8["id"]

    new_links = []

    def add_link(src, src_slot, dst, dst_slot, kind):
        nonlocal lid
        new_links.append([lid, src, src_slot, dst, dst_slot, kind])
        lid += 1

    # ③ 前缀: PreviewVideo.prefix 一条线分发到 12 个保存节点
    for n in singles + [save4, save8]:
        add_link(pv["id"], PV_PREFIX_SLOT, n["id"], 1, "STRING")

    # ④ 单向保存: PreviewVideo.image_1..8 → 8 个单图保存的 images(slot 0)
    for i, n in enumerate(singles):
        add_link(pv["id"], PV_FRAME_START + i, n["id"], 0, "IMAGE")

    # ⑤ 四图/八图合成: 直接吃单图保存的 images 输出(与 0035 同款: 不重复接预览视频)
    for slot, n in enumerate(singles[:4]):
        add_link(n["id"], 0, comp4["id"], slot, "IMAGE")
    for slot, n in enumerate(singles):
        # 八图合成的 image5..8 在端口表里排在 label* 之后(与 0035 的序列化一致)
        dst_slot = slot if slot < 4 else _comp8_slot(comp8, "image" + str(slot + 1))
        add_link(n["id"], 0, comp8["id"], dst_slot, "IMAGE")

    # ⑥ 合成 → 合成保存
    add_link(comp4["id"], 0, save4["id"], 0, "IMAGE")
    add_link(comp8["id"], 0, save8["id"], 0, "IMAGE")

    wf["nodes"] = [n for n in wf["nodes"] if n["id"] != pv["id"]] + [pv]
    wf["nodes"] += singles + [comp4, comp8, save4, save8]
    wf["links"] += new_links
    wf["last_node_id"] = max(n["id"] for n in wf["nodes"])
    wf["last_link_id"] = max(l[0] for l in wf["links"])

    layout(wf, pv, singles, comp4, comp8, save4, save8)
    relink(wf)
    return wf


def _comp8_slot(comp8: dict, port_name: str) -> int:
    """八图合成里 image5..8 的实际输入槽下标(它们在 label* 之后, 不能按 0..7 直接数)。"""
    for idx, inp in enumerate(comp8["inputs"]):
        if inp.get("name") == port_name:
            return idx
    raise KeyError(port_name)


def main() -> None:
    for name in TARGETS:
        print(f"{name}:")
        wf = build(name)
        save(name, wf)
        print(f"  完成: {len(wf['nodes'])} 个节点, {len(wf['links'])} 条连线")


if __name__ == "__main__":
    main()
