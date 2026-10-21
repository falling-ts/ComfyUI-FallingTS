"""把《0031_首帧场景》的二段采样与音频嫁接同步给 0030/0032, 并删除截帧后续段。

做三件事(幂等, 可反复跑):
  ① 音频嫁接: 二段 GetVideoComponents.audio → 二采 CreateVideo.audio
     —— H3 一段生成的视频自带音轨, LTX 二采只吃画面不产出声音, 不接则成片无声。
  ② 删除截帧后续段(「重点生视频的最后八图截取这块不要」):
     8 个「单图 *」AutoSaveImage + 2 个 FallingTSImageComposite + 2 个「*合成*」AutoSaveImage,
     连同它们的连线一并清掉。0031 保留该段, 本脚本不碰 0031。
  ③ 清理悬空的 links(两端节点已不存在的), 让存档自洽。

判据统一按 **标题 + 类型**, 不按节点 id —— 三份工作流的 id 各不相同。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

WF_DIR = Path(__file__).resolve().parents[3] / "workflows"

TARGETS = [
    "0030_文生场景.json",
    "0032_参考场景.json",
    # 0031 是基准, 截帧段保留, 只补音频嫁接
    "0031_首帧场景.json",
]

# 截帧后续段保留的工作流(0031 是基准, 「单图 前面」等要留着)
KEEP_TAIL = {"0031_首帧场景.json"}


def is_tail_node(n: dict) -> bool:
    """截帧后续段: 单图保存 / 两张合成 / 合成的保存。"""
    title = n.get("title") or ""
    if n["type"] == "FallingTSImageComposite":
        return True
    if n["type"] == "AutoSaveImage":
        return title.startswith("单图 ") or "合成" in title
    return False


def find_one(nodes: dict[int, dict], cls: str, *, video_src: str) -> int | None:
    """按类型找唯一节点; video_src 用于区分一段/二段的 GetVideoComponents。"""
    hits = [i for i, n in nodes.items() if n["type"] == cls]
    return hits[0] if hits else None


def sync(path: Path) -> str:
    doc = json.loads(path.read_text(encoding="utf-8"))
    nodes = {int(n["id"]): n for n in doc["nodes"]}
    links: dict[int, list] = {int(l[0]): l for l in doc["links"]}

    report = []

    # ---------- ② 删除截帧后续段 ----------
    if path.name in KEEP_TAIL:
        report.append("截帧段按基准保留(0031)")
    else:
        tail_ids = {i for i, n in nodes.items() if is_tail_node(n)}
        if tail_ids:
            report.append(f"删除截帧段 {len(tail_ids)} 节点: {sorted(tail_ids)}")
            for i in tail_ids:
                del nodes[i]
        else:
            report.append("截帧段已不存在")

    # ---------- ③ 清理悬空 links ----------
    dropped = 0
    for lid in list(links):
        src_id, dst_id = links[lid][1], links[lid][3]
        if src_id not in nodes or dst_id not in nodes:
            del links[lid]
            dropped += 1
    if dropped:
        report.append(f"清理悬空连线 {dropped} 条")

    # 节点上登记的 links 引用同步收口, 否则前端会留下指向已删连线的悬空线头
    pruned = 0
    for n in nodes.values():
        for o in n.get("outputs") or []:
            if o.get("links"):
                kept = [lid for lid in o["links"] if lid in links]
                pruned += len(o["links"]) - len(kept)
                o["links"] = kept
        for x in n.get("inputs") or []:
            if x.get("link") is not None and x["link"] not in links:
                x["link"] = None
                pruned += 1
    if pruned:
        report.append(f"清理节点上的悬空引用 {pruned} 处")

    # 输入槽只容一条线, 但存档里可能残留多条 —— 只保留输入上登记的那条。
    # 实测 0030/0032 的继续节点都多挂了一条从一段采样器来的 LATENT(link 表里有、
    # 输入槽不认), 与 0031 的「继续只接视频」不一致, 留着会误导连线走向。
    dups = 0
    for n in nodes.values():
        for slot, x in enumerate(n.get("inputs") or []):
            keep = x.get("link")
            for lid in [lid for lid, L in links.items() if L[3] == n["id"] and L[4] == slot and lid != keep]:
                del links[lid]
                dups += 1
    if dups:
        # 再收口一次: 上一步删掉的连线可能还登记在源节点的 outputs 里
        for n in nodes.values():
            for o in n.get("outputs") or []:
                if o.get("links"):
                    o["links"] = [lid for lid in o["links"] if lid in links]
        report.append(f"清理抢占同一输入槽的冗余连线 {dups} 条")

    # ---------- ①b 去掉 SaveVideo: 生场景的工作流一律不自动落盘视频 ----------
    # 0031 的二采链是 CreateVideo → SaveVideo → PreviewVideo, SaveVideo 顺带当预览的视频来源,
    # 直接删会把预览断链 ⇒ 先把吃它输出的下游改接到它的上游, 再摘掉节点。
    removed_sv = 0
    for sv in [i for i, n in nodes.items() if n["type"] == "SaveVideo"]:
        src_lid = next((x.get("link") for x in nodes[sv].get("inputs") or [] if x["name"] == "video"), None)
        src = links.get(src_lid) if src_lid else None
        if not src:
            continue  # 没有上游可改接, 留给后面的悬空清理
        sid, sslot = src[1], src[2]
        for lid in [lid for lid, L in links.items() if L[1] == sv]:
            target_id, target_slot = links[lid][3], links[lid][4]
            new_lid = max(links) + 1
            links[new_lid] = [new_lid, sid, sslot, target_id, target_slot, src[5]]
            nodes[target_id]["inputs"][target_slot]["link"] = new_lid
            nodes[sid]["outputs"][sslot].setdefault("links", [])
            if nodes[sid]["outputs"][sslot]["links"] is None:
                nodes[sid]["outputs"][sslot]["links"] = []
            nodes[sid]["outputs"][sslot]["links"].append(new_lid)
            report.append(f"  改接: #{target_id}.{nodes[target_id]['inputs'][target_slot]['name']} 改由 #{sid} 供 VIDEO")
        del nodes[sv]
        removed_sv += 1
    if removed_sv:
        # 摘掉节点后, 把它占用的连线与各处登记一并收口
        for lid in [lid for lid, L in links.items() if L[1] not in nodes or L[3] not in nodes]:
            del links[lid]
        for n in nodes.values():
            for o in n.get("outputs") or []:
                if o.get("links"):
                    o["links"] = [lid for lid in o["links"] if lid in links]
            for x in n.get("inputs") or []:
                if x.get("link") is not None and x["link"] not in links:
                    x["link"] = None
        report.append(f"移除 SaveVideo {removed_sv} 个(视频不自动落盘)")

    # ---------- ① 音频嫁接 ----------
    # 找二段的 CreateVideo: 沿 VIDEO 输出向下游走(最多 3 跳)看是否到达标题含「二采」的预览节点。
    # 0030/0032 是 CreateVideo → PreviewVideo 直连; 0031 中间多一个 SaveVideo(落盘), 故不能只看一跳。
    def reaches_tail_preview(start: int) -> bool:
        seen, frontier = {start}, [start]
        for _ in range(3):
            nxt = []
            for cur in frontier:
                for o in nodes[cur].get("outputs") or []:
                    for lid in o.get("links") or []:
                        L = links.get(lid)
                        if not L or L[3] in seen:
                            continue
                        dst = nodes.get(L[3])
                        if not dst:
                            continue
                        if dst["type"] == "PreviewVideo" and "二采" in (dst.get("title") or ""):
                            return True
                        seen.add(L[3])
                        nxt.append(L[3])
            frontier = nxt
        return False

    create2 = None
    for i, n in nodes.items():
        if n["type"] == "CreateVideo" and reaches_tail_preview(i):
            create2 = i
    if create2 is None:
        report.append("⚠ 未找到二采 CreateVideo, 音频嫁接跳过")
    else:
        # 二段 GetVideoComponents: 输入 video 来自继续节点
        gvc2 = None
        for i, n in nodes.items():
            if n["type"] != "GetVideoComponents":
                continue
            for x in n.get("inputs") or []:
                if x["name"] != "video" or x.get("link") is None:
                    continue
                L = links.get(x["link"])
                if L and nodes.get(L[1], {}).get("type") == "FallingTSContinue":
                    gvc2 = i
        if gvc2 is None:
            report.append("⚠ 未找到二段 GetVideoComponents, 音频嫁接跳过")
        else:
            audio_out = None
            for idx, o in enumerate(nodes[gvc2].get("outputs") or []):
                if o["name"] == "audio":
                    audio_out = (idx, o)
            audio_in = None
            for idx, x in enumerate(nodes[create2].get("inputs") or []):
                if x["name"] == "audio":
                    audio_in = (idx, x)

            if audio_out is None or audio_in is None:
                report.append("⚠ 音频端口不存在, 嫁接跳过")
            elif audio_in[1].get("link") is not None:
                L = links.get(audio_in[1]["link"])
                if L and L[1] == gvc2 and L[2] == audio_out[0]:
                    report.append(f"音频嫁接已存在: #{gvc2}.audio → #{create2}.audio")
                else:
                    report.append(f"⚠ #{create2}.audio 已被占用(来源 #{L[1] if L else '?'}), 不覆盖")
            else:
                new_lid = max(links) + 1 if links else 1
                isrc, osrc = audio_out
                idst, odst = audio_in
                links[new_lid] = [new_lid, gvc2, isrc, create2, idst, "AUDIO"]
                nodes[gvc2]["outputs"][isrc].setdefault("links", [])
                if nodes[gvc2]["outputs"][isrc]["links"] is None:
                    nodes[gvc2]["outputs"][isrc]["links"] = []
                nodes[gvc2]["outputs"][isrc]["links"].append(new_lid)
                nodes[create2]["inputs"][idst]["link"] = new_lid
                report.append(
                    f"音频嫁接: #{gvc2}(GetVideoComponents).audio → #{create2}(CreateVideo).audio  [link {new_lid}]"
                )

    # ---------- 写回 ----------
    doc["nodes"] = [nodes[i] for i in sorted(nodes)]
    doc["links"] = [links[i] for i in sorted(links)]
    if doc.get("last_node_id") is None or doc["last_node_id"] < max(nodes):
        doc["last_node_id"] = max(nodes)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    report.append(f"写回 {path.name}: {len(nodes)} 节点 / {len(links)} 连线")
    return "\n  ".join(report)


def main() -> int:
    rc = 0
    for name in TARGETS:
        p = WF_DIR / name
        if not p.is_file():
            print(f"✗ 找不到 {p}")
            rc = 2
            continue
        print(f"\n{'=' * 70}\n{name}\n  " + sync(p))
    return rc


if __name__ == "__main__":
    sys.exit(main())
