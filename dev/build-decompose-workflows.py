# -*- coding: utf-8 -*-
"""拆解类工作流的生成: 0050_视频拆帧 / 0051_视频拆音 / 0070_截取声音 + 0040..0044 尾部清空。

四件事(幂等, 可反复跑):

1. 0050_视频拆帧: 用 FallingTSLoadVideo(加载视频) 取代核心 GetVideoComponents,
   并照搬「0044_参考视频」PreviewVideo 之后的三个 PreviewImageSave(首帧/关键帧/尾帧)。
2. 0051_视频拆音: 加载视频的 audio 输出 → FallingTSAudioTrim(波形截段) →
   三个 PreviewAudioSave(音频处理链同样来自「0044_参考视频」尾部)。
3. 0070_截取声音: 用 FallingTSLoadAudio(加载音频) 取音频 → 同一条截取链
   (FallingTSAudioTrim → 多个 PreviewAudioSave, 即「截取音频预览」)。
4. 0035_场景截帧: 补齐 video/audio/prefix 输出端口(+ 老存档的选中帧端口整体后移), 并把
   文件名前缀接到十个保存节点上、后缀补下划线。0035 的结构自 2026-10-02 起由本函数维护 ——
   原来"从 0030 的 PreviewVideo 尾部搬运"的 make-0035-scene.py 已退休(0030 尾部已清空)。

**这三个工作流不要 md 数据表节点**(2026-10-02): 源文件由加载节点自身的下拉给出(节点本身
就是"起始的加载"), 文件名前缀 = 加载节点的 prefix 输出「序列号_名称」(见
output_subdir.sequence_prefix), 一条线分发给本图所有预览/保存节点 —— 前缀不再来自 MD 表的 ID 列。
故成品目录退回工作流名(0050_视频拆帧/ 等), 与「没有 md 表就退回工作流名」的既有口径一致。

5. 0040..0044: 删掉 PreviewVideo 之后的截帧链(首帧/关键帧/尾帧保存)与整条截音链
   (截段 + 三个音频保存) + 分发文件名前缀的 Reroute; 预览视频节点只留 video 输出,
   文件名前缀改为 MD 表 ID 直连(与 0030/0031/0032 已完成的清理同口径)。

跑法(工作区根): .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/build-decompose-workflows.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent.parent
WF_DIR = ROOT / "workflows"

MD_TABLE = "FallingTSMarkDownTable"
LOAD_VIDEO = "FallingTSLoadVideo"
LOAD_AUDIO = "FallingTSLoadAudio"
AUDIO_TRIM = "FallingTSAudioTrim"


# ─── 读写 ──────────────────────────────────────────────────────────────────


def load(name: str) -> dict:
    return json.loads((WF_DIR / (name + ".json")).read_text(encoding="utf-8"))


def save(name: str, wf: dict) -> None:
    text = json.dumps(wf, ensure_ascii=False, separators=(",", ":"))
    (WF_DIR / (name + ".json")).write_text(text, encoding="utf-8")


def node_of(wf: dict, node_id: int) -> dict:
    return next(n for n in wf["nodes"] if n["id"] == node_id)


def node_by_type(wf: dict, node_type: str) -> list:
    return [n for n in wf["nodes"] if n["type"] == node_type]


def relink(wf: dict) -> None:
    """按 wf["links"] 重建所有 inputs.link / outputs.links(保证引用一致)。

    顺带丢掉历史残留连线: 目标输入槽的 link 字段才是权威, 指向别的连线的条目是旧改线残留
    (0043 的 link 132 就是这种 —— EasyCache → LoRA 的老连线, 输入槽其实早已指向 254)。
    """
    by_id = {n["id"]: n for n in wf["nodes"]}
    keep = []
    for link in wf["links"]:
        existing = by_id[link[3]]["inputs"][link[4]].get("link")
        if existing is None or existing == link[0]:
            keep.append(link)
    wf["links"] = keep
    for n in wf["nodes"]:
        for i in n.get("inputs") or []:
            i["link"] = None
        for o in n.get("outputs") or []:
            o["links"] = []
    for lid, sid, sslot, tid, tslot, _t in wf["links"]:
        by_id[sid]["outputs"][sslot]["links"].append(lid)
        by_id[tid]["inputs"][tslot]["link"] = lid


# ─── 节点模板(手写内联, 字段格式与前端序列化一致 ⇒ 脚本可脱离备份复跑) ──


KEEP = object()


def place(n: dict, node_id: int, pos, size, title=KEEP, order=0) -> dict:
    """摆位并改 id/order; title 不给就保留原值(模板里已带标题)。"""
    n["id"] = node_id
    n["pos"] = list(pos)
    n["size"] = list(size)
    n["order"] = order
    n["mode"] = 0
    if title is not KEEP:
        if title is None:
            n.pop("title", None)
        else:
            n["title"] = title
    return n


def io(name, kind, link=None, widget=True) -> dict:
    """一个输入槽(前端序列化格式)。"""
    item = {"localized_name": name, "name": name, "type": kind}
    if widget:
        item["widget"] = {"name": name}
    if widget:
        item["link"] = link
    return item


def md_note(node_id: int, text: str, pos, size, order) -> dict:
    return {
        "id": node_id,
        "type": "MarkdownNote",
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "title": "使用说明",
        "properties": {
            "Node name for S&R": "MarkdownNote",
            "ue_properties": {"widget_ue_connectable": {}, "version": "7.8", "input_ue_unconnectable": {}},
        },
        "widgets_values": [text],
        "widgets_values_named": {"text": text},
        "color": "#222",
        "bgcolor": "#000",
    }


def load_video_node(pos, size, order, frames: int) -> dict:
    """加载视频节点: 输入端插 video_in(VIDEO), 输出端 video + audio + prefix + image_1..N。

    输入顺序按运行时实测顺序 —— 可选输入 video_in 排在 required 之前:
    video_in / name / sequence / video / upload;
    输出顺序 video(0) / audio(1) / prefix(2) / image_1..(3 起) —— 前端的 syncFrameState
    按 startIdx=3 增删选中帧端口, prefix 必须排在选中帧之前, 否则会被它裁掉。
    """
    n = {
        "id": 0,
        "type": LOAD_VIDEO,
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [io("video_in", "VIDEO", widget=False)],
        "outputs": [
            {"localized_name": "video", "name": "video", "type": "VIDEO", "slot_index": 0, "links": []},
            {"localized_name": "audio", "name": "audio", "type": "AUDIO", "slot_index": 1, "links": []},
            {
                "localized_name": "prefix",
                "label": "文件名前缀",
                "name": "prefix",
                "type": "STRING",
                "slot_index": 2,
                "links": [],
            },
        ],
        "title": "视频 加载/截帧",
        "properties": {
            "Node name for S&R": LOAD_VIDEO,
            "ue_properties": {"widget_ue_connectable": {}, "version": "7.8", "input_ue_unconnectable": {}},
        },
        "widgets_values": ["", "00000", None, "", None, None, None, None, {"frames": []}, "", frames, {"frames": []}, ""],
        "widgets_values_named": {
            "name": "",
            "sequence": "00000",
            "刷新序列号": None,
            "video": "",
            "Auto-refresh after generation": None,
            "refresh": None,
            "upload": None,
            "截帧": None,
            "完成": {"frames": []},
            "保存帧": "",
            "输出帧数": frames,
            "frame_list": {"frames": []},
            "video_fallback": "",
        },
    }
    n["inputs"] += [
        io("name", "STRING"),
        io("sequence", "STRING"),
        io("video", "COMBO"),
        io("upload", "IMAGEUPLOAD"),
    ]
    for i in range(1, frames + 1):
        n["outputs"].append(
            {"label": "选中帧 " + str(i), "localized_name": "选中帧 " + str(i), "name": "image_" + str(i), "type": "IMAGE", "links": []}
        )
    for slot, o in enumerate(n["outputs"]):
        o["slot_index"] = slot
    return n


def widget_input(name: str, kind: str) -> dict:
    return {"localized_name": name, "name": name, "type": kind, "widget": {"name": name}, "link": None}


def preview_image_save(suffix: str, title: str) -> dict:
    return {
        "id": 0,
        "type": "PreviewImageSave",
        "pos": [0, 0],
        "size": [640, 760],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "images", "name": "images", "type": "IMAGE", "link": None},
            widget_input("filename_prefix", "STRING"),
            widget_input("filename_suffix", "STRING"),
            widget_input("format", "COMBO"),
            widget_input("bit_depth", "COMBO"),
            widget_input("input_color_space", "COMBO"),
        ],
        "outputs": [{"localized_name": "images", "name": "images", "type": "IMAGE", "slot_index": 0, "links": []}],
        "title": title,
        "properties": {
            "Node name for S&R": "PreviewImageSave",
            "ue_properties": {
                "widget_ue_connectable": {"filename_prefix": True, "filename_suffix": True, "format": True, "bit_depth": True, "input_color_space": True},
                "version": "7.8",
                "input_ue_unconnectable": {},
            },
        },
        "widgets_values": ["", suffix, "png", "8-bit", "sRGB", None, ""],
        "widgets_values_named": {
            "filename_prefix": "",
            "filename_suffix": suffix,
            "format": "png",
            "bit_depth": "8-bit",
            "input_color_space": "sRGB",
            "保存": None,
            "image_fallback": "",
        },
    }


def preview_audio_save(title: str) -> dict:
    return {
        "id": 0,
        "type": "PreviewAudioSave",
        "pos": [0, 0],
        "size": [660, 660],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "audio", "name": "audio", "type": "AUDIO", "link": None},
            widget_input("filename_prefix", "STRING"),
            widget_input("filename_suffix", "STRING"),
            widget_input("format", "COMBO"),
            widget_input("quality", "COMBO"),
        ],
        "outputs": [{"localized_name": "audio", "name": "audio", "type": "AUDIO", "slot_index": 0, "links": []}],
        "title": title,
        "properties": {
            "Node name for S&R": "PreviewAudioSave",
            "ue_properties": {
                "widget_ue_connectable": {"filename_prefix": True, "filename_suffix": True, "format": True, "quality": True},
                "version": "7.8",
                "input_ue_unconnectable": {},
            },
        },
        "widgets_values": ["", "", "mp3", "320k", None, ""],
        "widgets_values_named": {
            "filename_prefix": "",
            "filename_suffix": "",
            "format": "mp3",
            "quality": "320k",
            "保存": None,
            "player": "",
        },
    }


def audio_trim() -> dict:
    return {
        "id": 0,
        "type": AUDIO_TRIM,
        "pos": [0, 0],
        "size": [660, 660],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "audio", "name": "audio", "type": "AUDIO", "link": None},
            widget_input("filename_prefix", "STRING"),
            widget_input("filename_suffix", "STRING"),
            widget_input("format", "COMBO"),
            widget_input("quality", "COMBO"),
        ],
        "outputs": [
            {"localized_name": "audio", "name": "audio", "type": "AUDIO", "slot_index": 0, "links": []},
            {"label": "截段 1", "localized_name": "截段 1", "name": "audio_1", "type": "AUDIO", "slot_index": 1, "links": []},
            {"label": "截段 2", "localized_name": "截段 2", "name": "audio_2", "type": "AUDIO", "slot_index": 2, "links": []},
            {"label": "截段 3", "localized_name": "截段 3", "name": "audio_3", "type": "AUDIO", "slot_index": 3, "links": []},
        ],
        "properties": {
            "Node name for S&R": AUDIO_TRIM,
            "ue_properties": {
                "widget_ue_connectable": {"filename_prefix": True, "filename_suffix": True, "format": True, "quality": True},
                "version": "7.8",
                "input_ue_unconnectable": {},
            },
        },
        "widgets_values": ["", "", "mp3", "320k", None, "", None, None, 3, ""],
        "widgets_values_named": {
            "filename_prefix": "",
            "filename_suffix": "",
            "format": "mp3",
            "quality": "320k",
            "保存": None,
            "waveform": "",
            "截段": None,
            "完成": None,
            "输出段数": 3,
            "segment_list": "",
        },
    }


# ─── 0050 / 0051 ───────────────────────────────────────────────────────────


def build_0050() -> dict:
    wf = load("0050_视频拆帧")
    nodes = [
        place(load_video_node((0, 0), (930, 1300), 0, 3), 1, (0, 0), (930, 1300), order=0),
        place(preview_image_save("_首帧", "预览保存-首帧"), 2, (1010, 0), (640, 760), order=1),
        place(preview_image_save("_关键帧", "预览保存-关键帧"), 3, (1010, 820), (640, 760), order=2),
        place(preview_image_save("_尾帧", "预览保存-尾帧"), 4, (1010, 1640), (640, 760), order=3),
        md_note(5,
            "## 视频拆帧\n\n"
            "- 「加载视频」(FallingTSLoadVideo) 自己就是起点: 在它的下拉里选 output 里的原视频(点「刷新」重扫候选)\n"
            "- 点「截帧」在播放位置取帧(可删/可多次), 点「完成」把选中帧输出到下游\n"
            "- 选中帧 1/2/3 → 首帧/关键帧/尾帧 三个「预览保存」; 单帧也能用节点自带的「保存帧」直接存\n"
            "- 文件名前缀 = 加载视频的「文件名前缀」输出(序列号_名称, 一条线分发给三个保存节点); 后缀区分首帧/关键帧/尾帧\n"
            "- 本工作流不读数据表; 拆音见 0051_视频拆音",
            (-600, 0), (520, 760), 4,
        ),
    ]
    links = [
        [1, 1, 3, 2, 0, "IMAGE"],
        [2, 1, 4, 3, 0, "IMAGE"],
        [3, 1, 5, 4, 0, "IMAGE"],
        [4, 1, 2, 2, 1, "STRING"],
        [5, 1, 2, 3, 1, "STRING"],
        [6, 1, 2, 4, 1, "STRING"],
    ]
    wf["nodes"] = nodes
    wf["links"] = links
    wf["groups"] = []
    wf["last_node_id"] = 5
    wf["last_link_id"] = 6
    wf["extra"] = {"ds": {"scale": 0.55, "offset": [1000, 700]}, "ue_links": []}
    relink(wf)
    return wf


def build_0051() -> dict:
    wf = load("0051_视频拆音")
    nodes = [
        place(load_video_node((0, 0), (930, 1300), 0, 1), 1, (0, 0), (930, 1300), order=0),
        place(audio_trim(), 2, (1010, 0), (660, 660), order=1),
        place(preview_audio_save("预览音频-1"), 3, (1750, 0), (660, 660), order=2),
        place(preview_audio_save("预览音频-2"), 4, (1750, 720), (660, 660), order=3),
        place(preview_audio_save("预览音频-3"), 5, (1750, 1440), (660, 660), order=4),
        md_note(6,
            "## 视频拆音\n\n"
            "- 「加载视频」(FallingTSLoadVideo) 自己就是起点: 在它的下拉里选 output 里的原视频(点「刷新」重扫候选)\n"
            "- 加载视频直接输出 audio 音轨(拆音不需要截帧, 不受「完成」门控)\n"
            "- 音轨进「音频截段」: 波形上拖两侧把手选区 → 点「截段」累积(可多段) → 点「完成」输出 截段 1/2/3\n"
            "- 三段各接一个「预览音频」, 可试听并点「保存」落盘\n"
            "- 文件名前缀 = 加载视频的「文件名前缀」输出(序列号_名称, 一条线分发给截段与三个预览)\n"
            "- 本工作流不读数据表",
            (-600, 0), (520, 760), 5,
        ),
    ]
    links = [
        [1, 1, 1, 2, 0, "AUDIO"],
        [2, 1, 2, 2, 1, "STRING"],
        [3, 1, 2, 3, 1, "STRING"],
        [4, 1, 2, 4, 1, "STRING"],
        [5, 1, 2, 5, 1, "STRING"],
        [6, 2, 1, 3, 0, "AUDIO"],
        [7, 2, 2, 4, 0, "AUDIO"],
        [8, 2, 3, 5, 0, "AUDIO"],
    ]
    wf["nodes"] = nodes
    wf["links"] = links
    wf["groups"] = []
    wf["last_node_id"] = 6
    wf["last_link_id"] = 8
    wf["extra"] = {"ds": {"scale": 0.55, "offset": [1100, 700]}, "ue_links": []}
    relink(wf)
    return wf


# ─── 0035: 补 audio 端口并把选中帧槽整体后移一位 ──────────────────────────


def fix_0035() -> dict:
    """0035: 端口规范化(video/audio/prefix + 选中帧) + 文件名前缀接到每个保存节点。

    ① 节点 18 的输入/输出按当前 schema 重写 —— video(0) / audio(1) / prefix(2) /
       image_1..N(3 起): 老存档里没有音频/前缀口、选中帧从端口 1 起, 这里按**输出名**
       把连线搬到新槽位(重跑不叠加);
    ② 每个 PreviewImageSave 的 filename_prefix 改接加载视频的 prefix 输出(「序列号_名称」),
       后缀补一个下划线(前缀与后缀之间也要有分隔: 00001_陈落_前面.png);
    ③ 「输出帧数」控件对齐到实际选中帧端口数(前端 syncFrameState 按 3 + total 增删端口)。
    """
    wf = load("0035_场景截帧")
    n = node_of(wf, 18)
    n["inputs"] = [
        io("video_in", "VIDEO", widget=False),
        io("name", "STRING"),
        io("sequence", "STRING"),
        io("video", "COMBO"),
        io("upload", "IMAGEUPLOAD"),
    ]
    frames = [o for o in n["outputs"] if str(o.get("name", "")).startswith("image_")]
    outs = [
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
    for o in frames:
        outs.append(
            {
                "label": o.get("label") or o["name"],
                "localized_name": o.get("localized_name") or o["name"],
                "name": o["name"],
                "type": "IMAGE",
                "links": [],
            }
        )
    for slot, o in enumerate(outs):
        o["slot_index"] = slot
    # 按输出名把连线搬到新槽位(audio/prefix 插在前面 ⇒ 选中帧整体后移; 重跑不叠加)
    new_slot = {o["name"]: slot for slot, o in enumerate(outs)}
    old_names = {slot: o.get("name") for slot, o in enumerate(n["outputs"])}
    for link in wf["links"]:
        if link[1] == 18 and link[2] in old_names:
            link[2] = new_slot.get(old_names[link[2]], link[2])
    n["outputs"] = outs

    # 「输出帧数」= 选中帧端口数
    values = n.get("widgets_values") or []
    named = n.get("widgets_values_named")
    if isinstance(named, dict):
        named["输出帧数"] = len(frames)
    if len(values) > 10:
        values[10] = len(frames)
    n["widgets_values"] = values

    # 每个保存节点: filename_prefix 改接 prefix 输出; 后缀补下划线
    saves = node_by_type(wf, "PreviewImageSave")
    save_ids = {s["id"] for s in saves}
    wf["links"] = [
        l for l in wf["links"] if not (l[3] in save_ids and l[4] == 1)
    ]
    next_link = max((l[0] for l in wf["links"]), default=0) + 1
    for s in saves:
        wf["links"].append([next_link, 18, 2, s["id"], 1, "STRING"])
        next_link += 1
        named_s = s.get("widgets_values_named")
        if not isinstance(named_s, dict):
            continue
        suffix = str(named_s.get("filename_suffix") or "")
        if suffix and not suffix.startswith("_"):
            suffix = "_" + suffix
        named_s["filename_suffix"] = suffix
        vals = s.get("widgets_values") or []
        if len(vals) > 1:
            vals[0] = ""  # 前缀已改连线, 控件值不再参与提交
            vals[1] = suffix
        s["widgets_values"] = vals

    wf["last_link_id"] = max((l[0] for l in wf["links"]), default=wf.get("last_link_id", 0))
    relink(wf)
    return wf


# ─── 清空 0040..0044 的 PreviewVideo 尾部 ───────────────────────────────────


def clean_tail(name: str) -> dict:
    wf = load(name)
    nodes = wf["nodes"]
    md_ids = [n["id"] for n in nodes if n["type"] == MD_TABLE]
    pv = node_by_type(wf, "PreviewVideo")[0]

    doomed = set()
    queue = [pv["id"]]
    while queue:
        nid = queue.pop()
        for link in wf["links"]:
            if link[1] == nid and link[3] not in doomed:
                doomed.add(link[3])
                queue.append(link[3])
    doomed.discard(pv["id"])
    for n in nodes:
        if n["type"] in (AUDIO_TRIM, "PreviewAudioSave"):
            doomed.add(n["id"])
    for n in nodes:
        if n["type"] != "Reroute" or not n.get("inputs"):
            continue
        lid = n["inputs"][0].get("link")
        src = next((l for l in wf["links"] if l[0] == lid), None)
        if src and src[1] in md_ids and src[2] == 0:
            doomed.add(n["id"])

    # 预览视频的文件名前缀原本来自将被删掉的 Reroute ⇒ 改成 MD 的 ID 直连
    for inp in pv["inputs"]:
        if inp["name"] != "filename_prefix":
            continue
        lid = inp.get("link")
        link = next((l for l in wf["links"] if l[0] == lid), None)
        if link and link[1] in doomed:
            link[1], link[2] = md_ids[0], 0

    wf["links"] = [l for l in wf["links"] if l[1] not in doomed and l[3] not in doomed]
    wf["nodes"] = [n for n in nodes if n["id"] not in doomed]

    named = pv.get("widgets_values_named") or {}
    pv["outputs"] = [{"localized_name": "video", "name": "video", "type": "VIDEO", "slot_index": 0, "links": []}]
    pv["widgets_values"] = [named.get("filename_prefix", ""), named.get("filename_suffix", ""), None, ""]
    pv["widgets_values_named"] = {
        "filename_prefix": named.get("filename_prefix", ""),
        "filename_suffix": named.get("filename_suffix", ""),
        "保存": None,
        "video_fallback": "",
    }
    pv["size"] = [pv["size"][0], 800]
    pv["properties"]["ue_properties"]["widget_ue_connectable"] = {"filename_prefix": True, "filename_suffix": True}
    relink(wf)
    return wf


# ─── 自检(AGENTS.md「工作流布局规范」) ─────────────────────────────────────


def overlap(a: dict, b: dict) -> bool:
    ax, ay = a["pos"]
    aw, ah = a["size"]
    bx, by = b["pos"]
    bw, bh = b["size"]
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def band_gaps(nodes: list, vertical: bool) -> list:
    """同一列(vertical)/同一排 的**相邻**节点净间距必须落在 (50, 100)。

    只比较该列/该排里紧邻的一对 —— 远距离节点(如 MD 表与它右侧的下游)不受上限约束。
    """
    errs = []
    done = set()
    for a in nodes:
        band = []
        for b in nodes:
            if b is a:
                continue
            if vertical:
                same = a["pos"][0] < b["pos"][0] + b["size"][0] and b["pos"][0] < a["pos"][0] + a["size"][0]
            else:
                same = a["pos"][1] < b["pos"][1] + b["size"][1] and b["pos"][1] < a["pos"][1] + a["size"][1]
            if same:
                band.append(b)
        band.sort(key=lambda n: n["pos"][1] if vertical else n["pos"][0])
        order = band + [a]
        order.sort(key=lambda n: n["pos"][1] if vertical else n["pos"][0])
        idx = order.index(a)
        for other in (order[idx - 1] if idx > 0 else None, order[idx + 1] if idx + 1 < len(order) else None):
            if other is None:
                continue
            key = tuple(sorted((a["id"], other["id"])))
            if key in done:
                continue
            done.add(key)
            # 两者之间若还夹着别的节点(哪怕不同排), 就不算"相邻", 不受上限约束
            lo, hi = sorted((a, other), key=lambda n: n["pos"][0 if not vertical else 1])
            if vertical:
                band0, band1 = lo["pos"][1] + lo["size"][1], hi["pos"][1]
                between = [n for n in nodes if n not in (a, other) and band0 < n["pos"][1] and n["pos"][1] + n["size"][1] < band1]
            else:
                band0, band1 = lo["pos"][0] + lo["size"][0], hi["pos"][0]
                between = [n for n in nodes if n not in (a, other) and band0 < n["pos"][0] < band1 and n["pos"][0] + n["size"][0] > band0]
            if between:
                continue
            p, q = (a, other) if (a["pos"][1 if vertical else 0] <= other["pos"][1 if vertical else 0]) else (other, a)
            gap = q["pos"][1 if vertical else 0] - (p["pos"][1 if vertical else 0] + p["size"][1 if vertical else 0])
            if gap <= 50 or gap >= 100:
                errs.append("%s间距 %dpx: #%s 与 #%s" % ("同列" if vertical else "同排", gap, p["id"], q["id"]))
    return errs


def gap_errors(nodes: list) -> list:
    return band_gaps(nodes, True) + band_gaps(nodes, False)


def integrity(name: str, wf: dict) -> list:
    """引用完整性: 连线端点/槽位/links 互指一致(任何工作流都该满足)。"""
    nodes = wf["nodes"]
    by_id = {n["id"]: n for n in nodes}
    errs = []
    seen = set()
    for link in wf["links"]:
        lid, sid, sslot, tid, tslot = link[0], link[1], link[2], link[3], link[4]
        if lid in seen:
            errs.append("连线 id 重复: %s" % lid)
        seen.add(lid)
        src, dst = by_id.get(sid), by_id.get(tid)
        if src is None or dst is None:
            errs.append("连线 %s 端点缺失: #%s → #%s" % (lid, sid, tid))
            continue
        if sslot >= len(src.get("outputs") or []):
            errs.append("连线 %s 源槽越界: #%s[%s]" % (lid, sid, sslot))
            continue
        if tslot >= len(dst.get("inputs") or []):
            errs.append("连线 %s 目标槽越界: #%s[%s]" % (lid, tid, tslot))
            continue
        if lid not in (src["outputs"][sslot].get("links") or []):
            errs.append("连线 %s 未登记在 #%s 输出槽 %s" % (lid, sid, sslot))
        if dst["inputs"][tslot].get("link") != lid:
            errs.append("连线 %s 未落到 #%s 输入槽 %s" % (lid, tid, tslot))
    return [name + ": " + e for e in errs]


def check(name: str, wf: dict) -> list:
    nodes = wf["nodes"]
    by_id = {n["id"]: n for n in nodes}
    errs = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if overlap(a, b):
                errs.append("节点重叠: #%s 与 #%s" % (a["id"], b["id"]))
    for lid, sid, sslot, tid, tslot, _t in wf["links"]:
        src, dst = by_id.get(sid), by_id.get(tid)
        if src is None or dst is None:
            errs.append("连线 %s 端点缺失" % lid)
            continue
        if src["pos"][0] + src["size"][0] > dst["pos"][0]:
            errs.append("连线 %s 逆向左/同列: #%s → #%s" % (lid, sid, tid))
        if dst["inputs"][tslot].get("link") != lid:
            errs.append("连线 %s 未落到 #%s 输入槽 %s" % (lid, tid, tslot))
    for n in nodes:
        ins = [i for i in n.get("inputs") or [] if i.get("link") is not None]
        for x in range(len(ins)):
            for y in range(x + 1, len(ins)):
                pa, pb = ins[x], ins[y]
                ia = next(l for l in wf["links"] if l[0] == pa["link"])
                ib = next(l for l in wf["links"] if l[0] == pb["link"])
                if by_id[ia[1]]["pos"][1] > by_id[ib[1]]["pos"][1]:
                    errs.append("#%s 输入端口顺序与上游上下顺序相反: %s / %s" % (n["id"], pa["name"], pb["name"]))
        outs = [o for o in n.get("outputs") or [] if o.get("links")]
        for x in range(len(outs)):
            for y in range(x + 1, len(outs)):
                oa, ob = outs[x], outs[y]
                ya = min(by_id[l[3]]["pos"][1] for l in wf["links"] if l[0] in oa["links"])
                yb = min(by_id[l[3]]["pos"][1] for l in wf["links"] if l[0] in ob["links"])
                if ya > yb:
                    errs.append("#%s 输出端口顺序与下游上下顺序相反: %s / %s" % (n["id"], oa["name"], ob["name"]))
    for n in nodes:
        if n["type"] != MD_TABLE:
            continue
        x, w = n["pos"][0], n["size"][0]
        for m in nodes:
            if m is n or m["type"] == MD_TABLE:
                continue
            if x <= m["pos"][0] < x + w:
                errs.append("MD 表 #%s 同列有节点 #%s" % (n["id"], m["id"]))
    errs += gap_errors(nodes)
    return [name + ": " + e for e in errs]


def load_audio_node(pos, size, order, title: str) -> dict:
    """加载音频节点: 输入端 audio_in(AUDIO) + name/sequence/audio/audioUI/upload, 输出 audio + prefix。

    输入顺序按运行时实测顺序 —— 可选输入排在 required 之前:
    audio_in / name / sequence / audio / audioUI / upload;
    输出 audio(0) / prefix(1) —— prefix = 「序列号_名称」, 接各预览保存节点的 filename_prefix。
    """
    n = {
        "id": 0,
        "type": LOAD_AUDIO,
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": [
            io("audio_in", "AUDIO", widget=False),
            io("name", "STRING"),
            io("sequence", "STRING"),
            io("audio", "COMBO"),
            io("audioUI", "AUDIO_UI", widget=False),
            io("upload", "IMAGEUPLOAD"),
        ],
        "outputs": [
            {"localized_name": "audio", "name": "audio", "type": "AUDIO", "slot_index": 0, "links": []},
            {
                "localized_name": "prefix",
                "label": "文件名前缀",
                "name": "prefix",
                "type": "STRING",
                "slot_index": 1,
                "links": [],
            },
        ],
        "title": title,
        "properties": {
            "Node name for S&R": LOAD_AUDIO,
            "ue_properties": {"widget_ue_connectable": {}, "version": "7.8", "input_ue_unconnectable": {}},
        },
        "widgets_values": ["", "00000", None, "", None, None, None, None],
        "widgets_values_named": {
            "name": "",
            "sequence": "00000",
            "刷新序列号": None,
            "audio": "",
            "Auto-refresh after generation": None,
            "refresh": None,
            "audioUI": None,
            "upload": None,
        },
    }
    return n


def build_0070() -> dict:
    """0070_截取声音: MD 表(原声音) → 加载音频 → 截取音频(截段) → 多个截取音频预览。"""
    wf = load("0070_截取声音")
    nodes = [
        place(load_audio_node((0, 0), (930, 640), 0, "音频 加载/试听"), 1, (0, 0), (930, 640), order=0),
        place(audio_trim(), 2, (1010, 0), (660, 660), order=1),
        place(preview_audio_save("截取音频预览-1"), 3, (1750, 0), (660, 660), order=2),
        place(preview_audio_save("截取音频预览-2"), 4, (1750, 720), (660, 660), order=3),
        place(preview_audio_save("截取音频预览-3"), 5, (1750, 1440), (660, 660), order=4),
        md_note(
            6,
            "## 截取声音\n\n"
            "- 「加载音频」(FallingTSLoadAudio) 自己就是起点: 在它的下拉里选 output 里的音频(点「刷新」重扫候选)\n"
            "- 加载音频直接输出 audio(节点内可试听)\n"
            "- 音频进「截取音频」: 波形上拖两侧把手选区 → 点「截段」累积(可多段) → 点「完成」输出 截段 1/2/3\n"
            "- 每段各接一个「截取音频预览」, 可试听并点「保存」落盘; 段数不够时把该节点的「输出段数」调大即可\n"
            "- 文件名前缀 = 加载音频的「文件名前缀」输出(序列号_名称, 一条线分发给截取音频与三个预览)\n"
            "- 本工作流不读数据表",
            (-600, 0), (520, 760), 5,
        ),
    ]
    nodes[1]["title"] = "截取音频"
    links = [
        [1, 1, 0, 2, 0, "AUDIO"],
        [2, 1, 1, 2, 1, "STRING"],
        [3, 1, 1, 3, 1, "STRING"],
        [4, 1, 1, 4, 1, "STRING"],
        [5, 1, 1, 5, 1, "STRING"],
        [6, 2, 1, 3, 0, "AUDIO"],
        [7, 2, 2, 4, 0, "AUDIO"],
        [8, 2, 3, 5, 0, "AUDIO"],
    ]
    wf["nodes"] = nodes
    wf["links"] = links
    wf["groups"] = []
    wf["last_node_id"] = 6
    wf["last_link_id"] = 8
    wf["extra"] = {"ds": {"scale": 0.55, "offset": [1100, 700]}, "ue_links": []}
    relink(wf)
    return wf


def main() -> None:
    results = {
        "0050_视频拆帧": build_0050(),
        "0051_视频拆音": build_0051(),
        "0070_截取声音": build_0070(),
        "0035_场景截帧": fix_0035(),
    }
    for name in ("0040_文生视频", "0041_首帧视频", "0042_首尾视频", "0043_关键帧视频", "0044_参考视频"):
        results[name] = clean_tail(name)

    problems = []
    for name, wf in results.items():
        problems += integrity(name, wf)
        if name in ("0050_视频拆帧", "0051_视频拆音", "0070_截取声音"):
            problems += check(name, wf)
        save(name, wf)
        types = {}
        for n in wf["nodes"]:
            types[n["type"]] = types.get(n["type"], 0) + 1
        print("%s: 节点 %d / 连线 %d | %s" % (name, len(wf["nodes"]), len(wf["links"]),
              ", ".join("%s×%d" % (k, v) for k, v in sorted(types.items()))))

    print()
    if problems:
        print("布局/结构自检问题:")
        for p in problems:
            print("  -", p)
    else:
        print("布局/结构自检: 无问题")


if __name__ == "__main__":
    main()
