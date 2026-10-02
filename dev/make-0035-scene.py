# make-0035-scene.py
r"""生成 0035_场景截帧 工作流(幂等)。

内容 = 0030_文生场景 的「预览视频往后的所有节点」, 只把那个 PreviewVideo 换成
FallingTSLoadVideo(加载视频: 来自输出 + 截帧):

    加载视频(截帧) → 8 个 PreviewImageSave(单图 前面/前右/…/左前)
                   → 截帧合成(4 图) → 截帧合成 预览/保存
                   → 八向合成(8 图) → 八向合成 预览/保存

- 节点相对布局与 0030 完全一致(整条链左移到 x=0 起);
- 各保存节点的 filename_prefix 直接写字面值(0030 里由 MD 数据表的 ID 列经 Reroute 供给,
  本工作流不读数据表 —— 产物目录由工作流名 0035_场景截帧 决定, 见 output_subdir.py);
- 加载视频节点的视频默认指向 output 里已有的第一个视频(没有则留空, 由用户在下拉里选)。

用法: .venv\Scripts\python.exe custom_nodes\ComfyUI-FallingTS\dev\make-0035-scene.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SRC = ROOT / "workflows" / "0030_文生场景.json"
DST = ROOT / "workflows" / "0035_场景截帧.json"

# 要搬运的下游节点(0030 里 PreviewVideo 之后的全部)
KEEP = set(range(116, 128))
# 整条链左移, 使加载视频节点落在 x=0(相对布局与 0030 一致)
SHIFT_X = -4710
# 各保存节点的文件名前缀(0030 由 MD 表的 ID 列供给)
PREFIX = {
    117: "截帧合成",
    118: "前面",
    119: "前右",
    120: "右面",
    121: "右后",
    122: "后面",
    123: "后左",
    124: "左面",
    125: "左前",
    127: "八向合成",
}
# 加载视频节点的输出帧数(1 video + N image; 8 = 覆盖 8 个单图与八向合成)
TOTAL_FRAMES = 8

_NUMERIC_DIR = re.compile(r"^\d+_")


def first_existing_video() -> str:
    """output 根 + 数字目录里的第一个视频(相对路径), 找不到返回空串。"""
    base = ROOT / "media" / "七纹刻印"
    if not base.is_dir():
        return ""
    found: list[str] = []
    for entry in sorted(base.iterdir()):
        if entry.is_file() and entry.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv"):
            found.append(entry.name)
        elif entry.is_dir() and _NUMERIC_DIR.match(entry.name):
            for sub in sorted(entry.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv"):
                    found.append(f"{entry.name}/{sub.relative_to(entry).as_posix()}")
    return found[0] if found else ""


def new_load_video_node(video: str) -> dict:
    """构造 FallingTSLoadVideo 节点(控件顺序: 名称/序列号/刷新序列号/视频/截帧/完成/保存帧/输出帧数/帧列表)。"""
    outputs = [{"localized_name": "video", "name": "video", "type": "VIDEO", "slot_index": 0, "links": []}]
    for i in range(1, TOTAL_FRAMES + 1):
        outputs.append(
            {"label": f"选中帧 {i}", "localized_name": f"选中帧 {i}", "name": f"image_{i}", "type": "IMAGE", "links": []}
        )
    return {
        "id": 18,
        "type": "FallingTSLoadVideo",
        "pos": [0, -390],
        "size": [930, 1780],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"localized_name": "名称", "name": "name", "type": "STRING", "widget": {"name": "name"}, "link": None},
            {"localized_name": "序列号", "name": "sequence", "type": "STRING", "widget": {"name": "sequence"}, "link": None},
            {"localized_name": "video", "name": "video", "type": "COMBO", "widget": {"name": "video"}, "link": None},
        ],
        "outputs": outputs,
        "title": "场景视频 加载/截帧",
        "properties": {
            "Node name for S&R": "FallingTSLoadVideo",
            "ue_properties": {"widget_ue_connectable": {}, "version": "7.8", "input_ue_unconnectable": {}},
        },
        "widgets_values": ["", "00000", None, video, None, None, None, TOTAL_FRAMES, {"frames": []}, ""],
        "widgets_values_named": {
            "name": "",
            "sequence": "00000",
            "刷新序列号": None,
            "video": video,
            "截帧": None,
            "完成": None,
            "保存帧": None,
            "输出帧数": TOTAL_FRAMES,
            "frame_list": {"frames": []},
            "video_fallback": "",
        },
    }


def main() -> int:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    node_ids = KEEP | {18}
    kept_links = [l for l in src["links"] if l[1] in node_ids and l[3] in node_ids]
    link_ids = {l[0] for l in kept_links}

    nodes: list[dict] = [new_load_video_node(first_existing_video())]
    for node in src["nodes"]:
        if node["id"] not in KEEP:
            continue
        node = json.loads(json.dumps(node))  # 深拷贝
        node["pos"] = [node["pos"][0] + SHIFT_X, node["pos"][1]]
        for item in node.get("inputs") or []:
            if item.get("link") not in link_ids:
                item["link"] = None
        for item in node.get("outputs") or []:
            item["links"] = [lid for lid in (item.get("links") or []) if lid in link_ids]
        if node["id"] in PREFIX:
            values = node.get("widgets_values") or []
            while len(values) < 2:
                values.append("")
            values[0] = PREFIX[node["id"]]
            node["widgets_values"] = values
            named = node.get("widgets_values_named")
            if isinstance(named, dict):
                named["filename_prefix"] = PREFIX[node["id"]]
        nodes.append(node)

    # 加载视频节点的输出 links: 从保留下来的连线里回填
    load_node = nodes[0]
    for link in kept_links:
        if link[1] != 18:
            continue
        slot = link[2]
        if 0 <= slot < len(load_node["outputs"]):
            load_node["outputs"][slot]["links"].append(link[0])

    nodes.sort(key=lambda n: n["id"])
    result = {
        "id": "gen-0035_场景截帧",
        "revision": 0,
        "last_node_id": max(n["id"] for n in nodes),
        "last_link_id": max((l[0] for l in kept_links), default=0),
        "nodes": nodes,
        "links": kept_links,
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.2, "offset": [-60, 320]}, "ue_links": [], "links_added_by_ue": []},
        "version": 0.4,
    }

    # 自检: 连线两端存在 + 上游完全在左(布局规范第 1 条)
    by_id = {n["id"]: n for n in nodes}
    problems: list[str] = []
    for link in kept_links:
        lid, origin, oslot, target, tslot, _type = link
        if origin not in by_id or target not in by_id:
            problems.append(f"link {lid}: 端点缺失 {origin}->{target}")
            continue
        right = by_id[origin]["pos"][0] + by_id[origin]["size"][0]
        if right > by_id[target]["pos"][0]:
            problems.append(f"link {lid}: {origin} 右缘 {right} 越过 {target} 左缘 {by_id[target]['pos'][0]}")
    if len({n["id"] for n in nodes}) != len(nodes):
        problems.append("节点 id 重复")

    DST.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入 {DST.relative_to(ROOT)}")
    print(f"节点 {len(nodes)} 个, 连线 {len(kept_links)} 条, 视频默认值 = {nodes[0]['widgets_values'][3]!r}")
    if problems:
        print("自检问题:")
        for p in problems:
            print("  -", p)
        return 1
    print("自检通过: 连线两端齐全, 上游全部在左")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
