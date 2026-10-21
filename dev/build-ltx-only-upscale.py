#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 11 个 H3 工作流统一成「一采 960×544 → 只保留 LTX-2.5 二采 ×2 = 1920×1088」。

## 做什么

用户决策(2026-10-17):

1. **删掉 H3 高阶二采**(`MiniMaxH3LatentUpscale` / `MiniMaxH3ConditioningUpscale` /
   `MiniMaxH3AddNoise` / `MiniMaxH3ShiftSigmas` / `LTXVSeparateAVLatent` / `LTXVConcatAVLatent`
   那一整组), 二采只走 LTX-2.5。
2. **一采必须 960×544**, 二采 LTX latent 固定 ×2 ⇒ 成品 1920×1088。
   LTX 链的宽高/帧数由 `GetImageSize` 从 H3 帧批自动取, 因此**无需写死**:
   只要一采是 960×544, 二采必然 1920×1088。
3. **尺寸选择器本身不动**(档位名与各档数值保持原样, 由用户自己选)。
   但二采倍数那一组(第 3 组 input19~27)随 H3 二采一起消失, 故 `total` 3 → 2。

## 两个附带修复

- **0044 的去油开关断链**: 工作树里 `#965`(H3高阶 · 去油开关) 的 `false_1`/`true_1` 两个输入
  都是 `null`, 而它的 out0 是 `#37 MiniMaxLowVRAMAttention.model` 的唯一来源 ⇒
  `FallingTSSwitch.execute` 走 `kwargs.get("true_1")` 拿到 `None`, 主模型链断在这里。
  本脚本按 HEAD 语义接回: `#6 Sage → #965.false_1`, `#967 电影质感 → #965.true_1`。
- **5 个建模/场景工作流没有 LTX 二采**(0013/0014/0030/0031/0032) —— 原本只有 H3 高阶二采。
  删掉 H3 二采后它们就**完全没有二采**了, 故用 `build-ltx-upscale-workflows.py` 的
  `build_chain()` 补上同一条 LTX 链(该模块已跑通 0040~0044)。

## 幂等

两步都按**标志**识别, 不依赖计数:

- H3 二采节点按标题前缀 `H3高阶 · 二采` 与类型白名单双重识别;
- LTX 链按标题前缀 `LTX二采 · ` 识别, 已存在则整段撤掉重建(复用上游模块的 `strip_tail`);
- 尺寸选择器的第 3 组按「`input19` 端口是否存在」判断, 已清过则跳过。

因此重跑任意多次, 结果逐字节一致。

## 跑法(工作区根)

    python custom_nodes/ComfyUI-FallingTS/dev/build-ltx-only-upscale.py --check   # 只报告
    python custom_nodes/ComfyUI-FallingTS/dev/build-ltx-only-upscale.py           # 写盘
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
WF_DIR = ROOT / "workflows"


def _load_ltx_module():
    """按路径加载带连字符的兄弟模块 `build-ltx-upscale-workflows.py`。

    复用它的 `Builder` / `build_chain` / `layout` / `relink` / `ensure_outputs` ——
    那条 LTX 链已经在 0040~0044 上实测跑通, 不必在这里再抄一遍(抄一份就是第二份会漂移的真相)。
    """
    path = Path(__file__).with_name("build-ltx-upscale-workflows.py")
    spec = importlib.util.spec_from_file_location("_ltx_build", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LTX = _load_ltx_module()

# ─── 目标工作流 ─────────────────────────────────────────────────────────────

TARGETS = [
    "0013_首图建模",
    "0014_参考建模",
    "0030_文生场景",
    "0031_首帧场景",
    "0032_参考场景",
    "0040_文生视频",
    "0041_首帧视频",
    "0042_首尾视频",
    "0043_关键帧视频",
    "0044_参考视频",
]

# H3 高阶二采的全部节点类型(标题前缀之外的第二道保险)
H3_PASS2_TYPES = {
    "MiniMaxH3LatentUpscale",
    "MiniMaxH3ConditioningUpscale",
    "MiniMaxH3AddNoise",
    "MiniMaxH3ShiftSigmas",
    "LTXVSeparateAVLatent",
    "LTXVConcatAVLatent",
}

H3_PASS2_TITLE_PREFIX = "H3高阶 · 二采"
FACTOR_TITLE_TOKEN = "二采倍数"

# 尺寸选择器: 9 个档名 × 3 组 -> 27 个 input 端口。第 3 组是「二采倍数」, 随 H3 二采一起删。
SIZE_SELECTOR_INPUTS_KEEP = 18   # input1..input18 = 宽度 9 + 高度 9


# ─── 读写 ───────────────────────────────────────────────────────────────────


def load(name: str) -> dict:
    return json.loads((WF_DIR / (name + ".json")).read_text(encoding="utf-8"))


def save(name: str, wf: dict) -> None:
    text = json.dumps(wf, ensure_ascii=False, separators=(",", ":"))
    (WF_DIR / (name + ".json")).write_text(text, encoding="utf-8")


# ─── 步骤 1: 删 H3 高阶二采 ─────────────────────────────────────────────────


def strip_h3_pass2(wf: dict) -> list[str]:
    """删掉 H3 高阶二采整组与它的 9 个「二采倍数」PrimitiveFloat。返回删除说明。"""
    doomed: set[int] = set()
    for n in wf["nodes"]:
        title = n.get("title") or ""
        if title.startswith(H3_PASS2_TITLE_PREFIX) or FACTOR_TITLE_TOKEN in title:
            doomed.add(n["id"])
        elif n["type"] in H3_PASS2_TYPES:
            doomed.add(n["id"])

    if not doomed:
        return []

    notes = []
    by_id = {n["id"]: n for n in wf["nodes"]}
    # 记录被删节点曾有过的、指向组外的连线 —— 这些是「删了会断链」的嫌疑点, 必须报出来
    for lid, src, _ss, dst, _ds, _t in wf["links"]:
        if (src in doomed) != (dst in doomed):
            outside = dst if src in doomed else src
            notes.append(f"跨组连线 {lid}: {by_id[src]['type']} -> {by_id[dst]['type']}"
                         f"(外部端 {outside})")

    wf["links"] = [l for l in wf["links"] if l[1] not in doomed and l[3] not in doomed]
    wf["nodes"] = [n for n in wf["nodes"] if n["id"] not in doomed]
    return notes


# ─── 步骤 2: 尺寸选择器去掉第 3 组(二采倍数) ────────────────────────────────


def trim_size_selector(wf: dict) -> list[str]:
    """把尺寸选择器的第 3 组输入(二采倍数)摘掉, `total` 3 -> 2。

    ⚠️ **不动档位名与各档数值**: 用户要自己选档。这里只摘掉「二采倍数」这一组 ——
    它的 9 个 PrimitiveFloat 已被 `strip_h3_pass2` 删掉, 留着就是 9 个永空的输入端口。
    后端 `FallingTSSelector.check_lazy_status` 取 `input19..27` 时键不存在会跳过(不报错),
    但端口留着会让「组数 × 档名数」的公式与实际端口数对不上, 故一并清掉。
    """
    notes = []
    for n in wf["nodes"]:
        if n["type"] != "FallingTSSelector":
            continue
        ins = n.get("inputs") or []
        if len(ins) <= SIZE_SELECTOR_INPUTS_KEEP + 3:
            continue
        # 前 3 个是 items / total / selection, 其后才是 input1..inputN
        keep = ins[: 3 + SIZE_SELECTOR_INPUTS_KEEP]
        dropped = ins[3 + SIZE_SELECTOR_INPUTS_KEEP:]
        if not any(d.get("name", "").startswith("input") for d in dropped):
            continue
        n["inputs"] = keep
        w = list(n.get("widgets_values") or [])
        if len(w) >= 2 and isinstance(w[1], int) and w[1] > 2:
            old = w[1]
            w[1] = 2
            n["widgets_values"] = w
            if isinstance(n.get("widgets_values_named"), dict):
                n["widgets_values_named"]["total"] = 2
            notes.append(f"选择器 #{n['id']} total {old} -> 2, 摘掉 {len(dropped)} 个端口")
    return notes


# ─── 步骤 3: 修复去油开关断链(0044) ─────────────────────────────────────────


def fix_deoil_switch(wf: dict) -> list[str]:
    """去油开关的 `false_1`/`true_1` 悬空时, 按 HEAD 语义接回 Sage 与去油 LoRA 末级。"""
    by_id = {n["id"]: n for n in wf["nodes"]}
    notes = []

    sage = next((n for n in wf["nodes"]
                 if n["type"] == "MiniMaxH3MemoryEfficientSageAttentionPatch"), None)
    if sage is None:
        return notes

    # 去油两条 LoRA 的末级: 从 Sage 出发沿 LoraLoaderModelOnly 链一直走到底
    lora_tail = None
    cur = sage
    for _ in range(8):
        nxt = None
        for l in wf["links"]:
            if l[1] == cur["id"] and l[2] == 0:
                cand = by_id.get(l[3])
                if cand is not None and cand["type"] == "LoraLoaderModelOnly" \
                        and (cand.get("title") or "").startswith("H3高阶 · 去油 ·"):
                    nxt = cand
        if nxt is None:
            break
        lora_tail = cur = nxt

    for n in wf["nodes"]:
        if n["type"] != "FallingTSSwitch" or "去油开关" not in (n.get("title") or ""):
            continue
        ins = n.get("inputs") or []
        # 端口顺序: switch / total / false_1 / true_1 —— 但 0044 存的是精简版(只有两个输入)
        slots = {i["name"]: idx for idx, i in enumerate(ins)}
        for name, src in (("false_1", sage), ("true_1", lora_tail)):
            if name not in slots:
                continue
            idx = slots[name]
            if ins[idx].get("link") is not None:
                continue
            if src is None:
                continue
            lid = LTX.next_link_id(wf)
            wf["links"].append([lid, src["id"], 0, n["id"], idx, "MODEL"])
            notes.append(f"接回 #{src['id']} {src.get('title') or src['type']} -> "
                         f"#{n['id']}.{name}")
    return notes


# ─── 步骤 4: 确保有 LTX 二采链 ──────────────────────────────────────────────


def ensure_ltx(wf: dict) -> tuple[int, list[str]]:
    """已存在则撤掉重建(幂等), 返回新增节点数与说明。"""
    removed = LTX.strip_tail(wf)
    pv = next((n for n in wf["nodes"]
               if n["type"] == "PreviewVideo"
               and not (n.get("title") or "").startswith(LTX.TITLE_PREFIX)), None)
    if pv is None:
        return 0, ["找不到原 PreviewVideo, 未建 LTX 二采"]

    start_x = pv["pos"][0] + pv.get("size", [1300, 800])[0] + 80
    start_y = pv["pos"][1]
    added = LTX.build_chain(wf, pv)
    LTX.layout(wf, added, start_x, start_y)
    notes = [f"撤掉旧 LTX 链 {removed} 个节点"] if removed else []
    return len(added), notes


# ─── 校验 ───────────────────────────────────────────────────────────────────


def validate(name: str, wf: dict) -> list[str]:
    errs: list[str] = []
    ids = [n["id"] for n in wf["nodes"]]
    if len(ids) != len(set(ids)):
        errs.append("节点 id 重复")
    by_id = {n["id"]: n for n in wf["nodes"]}
    lids = [l[0] for l in wf["links"]]
    if len(lids) != len(set(lids)):
        errs.append("连线 id 重复")

    for lid, src, sslot, dst, dslot, _t in wf["links"]:
        s, d = by_id.get(src), by_id.get(dst)
        if s is None or d is None:
            errs.append(f"连线 {lid} 端点不存在 {src}->{dst}")
            continue
        if sslot >= len(s.get("outputs") or []):
            errs.append(f"连线 {lid} 源端口越界 [{src}]{s['type']} slot {sslot}")
        elif lid not in (s["outputs"][sslot].get("links") or []):
            errs.append(f"连线 {lid} 未记在源 [{src}].outputs[{sslot}]")
        if dslot >= len(d.get("inputs") or []):
            errs.append(f"连线 {lid} 目标端口越界 [{dst}]{d['type']} slot {dslot}")
        elif d["inputs"][dslot].get("link") != lid:
            errs.append(f"连线 {lid} 未记在目标 [{dst}].inputs[{dslot}]")

    # 残留检查
    left = [n["id"] for n in wf["nodes"]
            if n["type"] in H3_PASS2_TYPES or FACTOR_TITLE_TOKEN in (n.get("title") or "")]
    if left:
        errs.append(f"仍有 H3 二采残留节点: {left}")

    # 必需节点存在
    for t in ("LTXAddVideoICLoRAGuide", "LTXVLatentUpsampler", "GetVideoComponents",
              "EmptyLTXVLatentVideo"):
        if not any(n["type"] == t for n in wf["nodes"]):
            errs.append(f"缺少 LTX 二采必需节点 {t}")

    # 开关悬空
    for n in wf["nodes"]:
        if n["type"] == "FallingTSSwitch":
            hung = [i["name"] for i in (n.get("inputs") or [])
                    if not i.get("name") in ("switch", "total") and i.get("link") is None]
            if hung:
                errs.append(f"开关 #{n['id']} {n.get('title', '')} 悬空输入 {hung}")
    return errs


def geometry(wf: dict) -> str:
    """报告一采/二采的实际像素尺寸(一采取 H3 节点与 md 表驱动的档位, 二采按 ×2 推算)。"""
    def lat_out(w: int, h: int) -> tuple[int, int]:
        # LTX latent: /32, 再 ×2, 再 ×32
        return ((w // 32) * 2 * 32, (h // 32) * 2 * 32)

    for n in wf["nodes"]:
        if n["type"] in ("MiniMaxH3ReferenceToVideo", "MiniMaxH3ImageToVideo",
                         "MiniMaxH3FirstLastToVideo", "MiniMaxH3TextToVideo"):
            w = n.get("widgets_values") or []
            # 宽高通常已被连线覆盖, widget 只是占位 —— 取「横544 / 横1088」档对应的常量
            break
    sel = next((n for n in wf["nodes"] if n["type"] == "FallingTSSelector"
                and "横544" in str(n.get("widgets_values"))), None)
    detail = ""
    if sel is not None:
        detail = f" 档位={sel['widgets_values'][2]!r} total={sel['widgets_values'][1]}"
    return detail


# ─── 主流程 ─────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只报告, 不写盘")
    args = ap.parse_args()

    rc = 0
    for name in TARGETS:
        wf = load(name)
        notes: list[str] = []

        cross = strip_h3_pass2(wf)
        notes += [f"删 H3 二采 → {c}" for c in cross]
        notes += trim_size_selector(wf)
        notes += fix_deoil_switch(wf)
        n_added, ltx_notes = ensure_ltx(wf)
        notes += ltx_notes

        LTX.relink(wf)
        wf["last_node_id"] = max(n["id"] for n in wf["nodes"])
        wf["last_link_id"] = max([l[0] for l in wf["links"]], default=0)

        errs = validate(name, wf)
        if errs:
            rc = 1
            print(f"[X] {name}: 校验未通过(未写盘)")
            for e in errs:
                print("     -", e)
            continue

        if not args.check:
            save(name, wf)
        tag = "检查" if args.check else "写盘"
        print(f"[ok] {name}: {tag} 完成, {len(wf['nodes'])} 节点 / {len(wf['links'])} 连线"
              f", LTX 链 {n_added} 节点{geometry(wf)}")
        for x in notes:
            print(f"       · {x}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
