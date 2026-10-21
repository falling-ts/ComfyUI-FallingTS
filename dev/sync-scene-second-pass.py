"""把《0031_首帧场景》的二采(二段采样)整条链原样同步给其它生场景工作流。

用户要求:「完全参考首帧场景工作流, 改其它生场景的二采」。0031 的二采是 **LTX-2.5 潜空间
放大二采**(latent upscale + ICLoRA guide), 而 0030/0032 原本是 **H3 高清重绘**(EmptyLTXV +
双 ImgToVideoInplace + 15 步 denoise 0.4)。两者形态完全不同, 不是改几个参数能对齐的,
所以本脚本的做法是:**把 0031 的二采链整条摘下, 原样移植到目标工作流**。

做四件事(幂等, 可反复跑):
  ① 删除目标工作流原有二采 —— 判据是「挂在二采继续节点下游」的整片节点, 不是标题/类型白名单,
     这样 0030/0032 那套 H3 重绘专属的 PrimitiveFloat 二采倍数、DisableNoise、BasicGuider、
     MiniMaxH3ShiftSigmas、EmptyLTXVLatentVideo、LTXAddVideoICLoRAGuide 等一次性全清掉。
  ② 从 0031 现读二采链(22 个节点 + 节点内部连线), 重新编号贴进去 —— 模板**从 0031 现读**,
     以后 0031 的二采调了 sigmas/prompt/LoRA, 重跑本脚本就会跟过去。
  ③ 只保留两处外部依赖: 继续节点(VIDEO 输入)与 MD 数据表(预览节点的 filename_prefix)。
     ⚠️ 0031 的预览节点 prefix 接的是 MD 表 out[0], 而 0030/0032 一直是 out[2] —— 保留目标
     工作流自己的接法, 不把 0031 的端口号搬过来。
  ④ 布局按 0031 的相对坐标整体平移(生成区在左、二采在右), 避免和目标工作流左侧节点重叠。

⚠️ 本脚本只做结构搬运, **不做布局重排**; 跑完请再跑 `scripts/wf_layout_all.py <关键字>`。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

WF_DIR = Path(__file__).resolve().parents[3] / "workflows"

BASE = "0031_首帧场景.json"
# 全部生场景 + 生视频: 二采流程一律照搬 0031 的 LTX-2.5 潜空间放大链。
# ⚠️ 「照搬」= 连**整条流程结构**一起搬(单段采样 / VAEEncode 起链 / LTXVCropGuides 出正负条件 /
# 无 EmptyLTXVLatentVideo / 无 LTXAddVideoICLoRAGuide), 不是只改采样器与 sigmas 参数 ——
# 用户 2026-10-21 明确选的就是这个方案。
TARGETS = [
    "0030_文生场景.json",
    "0032_参考场景.json",
    "0040_文生视频.json",
    "0041_首帧视频.json",
    "0042_首尾视频.json",
    "0043_关键帧视频.json",
    "0044_参考视频.json",
]

# 「生视频」目标: 视频本身就是最终结果, 二采预览之后**不挂截帧后续段**
# (8 张分向单图 / 四图合成 / 八图合成都不挂) —— 用户明确要求「不要后面的八图、合成」。
# 生场景则相反: 场景的交付物就是那张四图/八图合成。
VIDEO_TARGETS = {
    "0040_文生视频.json",
    "0041_首帧视频.json",
    "0042_首尾视频.json",
    "0043_关键帧视频.json",
    "0044_参考视频.json",
}

# 二采预览节点 filename_prefix 接 MD 表的哪个输出。
# ⚠️ 0031 接 out[0], 而 0030/0032 一直是 out[2] —— 端口号是**目标工作流自己的约定**,
# 不能跟着 0031 搬, 否则文件名前缀会落到别的列。原样保留 out[2]。
MD_PREFIX_SLOT = 2

# 二采链里允许接到「链外」的两类节点 —— 其余外部连线一律丢弃, 由目标工作流自己的节点补上
LINK_CONTINUE = "continue"
LINK_PREFIX = "prefix"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _downstream(nodes: dict[int, dict], links: dict[int, list], start: int) -> set[int]:
    """从 start 出发沿连线向下游走, 返回可达的全部节点 id(不含 start)。"""
    kids: dict[int, list[int]] = {}
    for L in links.values():
        kids.setdefault(L[1], []).append(L[3])
    seen: set[int] = set()
    stack = list(kids.get(start, []))
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in nodes:
            continue
        seen.add(cur)
        stack.extend(kids.get(cur, []))
    return seen


def _upstream(nodes: dict[int, dict], links: dict[int, list], start: int,
              stop_types: set[str]) -> set[int]:
    """从 start 向上游溯源, 遇到 stop_types 里的类型**不并入、也不再往它上面走**。

    二采的准备链(UNETLoader/VAELoader/CLIPLoader/LoRA/两个 CLIPTextEncode 等)全都是
    「喂给二采采样器」的, 只沿下游是走不到的 —— 必须从下游的采样器再往前溯源。
    """
    parents: dict[int, list[int]] = {}
    for L in links.values():
        parents.setdefault(L[3], []).append(L[1])
    seen: set[int] = set()
    stack = list(parents.get(start, []))
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in nodes:
            continue
        if nodes[cur]["type"] in stop_types:
            continue
        seen.add(cur)
        stack.extend(parents.get(cur, []))
    return seen


def _find_continue(nodes: dict[int, dict]) -> int:
    hits = [i for i, n in nodes.items() if n["type"] == "FallingTSContinue"]
    if not hits:
        raise SystemExit("✗ 找不到 FallingTSContinue")
    return hits[0]


def is_frame_tail(n: dict) -> bool:
    """截帧后续段: 单图保存(标题「单图 xx」) / 多图合成 / 合成结果保存(标题含「合成」)。"""
    t = n.get("title") or ""
    return n["type"] == "FallingTSImageComposite" or (
        n["type"] == "AutoSaveImage" and (t.startswith("单图 ") or "合成" in t)
    )


def extract_frame_tail(base: dict) -> tuple[list[dict], list[list]]:
    """从 0031 里摘出「二采预览之后的截帧后续段」: 8 个单图保存 + 四图合成 + 八图合成 + 2 个合成保存, 共 12 节点。

    这一段的数据全部来自二采 PreviewVideo 的截帧输出(image_1..image_8)与它的 prefix,
    所以必须在二采贴好之后再搬 —— 靠标题认, 不靠节点 id。
    """
    nodes = {int(n["id"]): n for n in base["nodes"]}
    links = {int(l[0]): l for l in base["links"]}
    tail = {i for i, n in nodes.items() if is_frame_tail(n)}
    if not tail:
        raise SystemExit("✗ 0031 里找不到截帧后续段(单图/合成), 无法移植")
    sub_nodes = [json.loads(json.dumps(nodes[i])) for i in sorted(tail)]
    sub_links = [list(l) for l in links.values() if int(l[1]) in tail and int(l[3]) in tail]
    return sub_nodes, sub_links


def extract_chain(base: dict) -> tuple[list[dict], list[list], int, dict]:
    """从 0031 里摘出二采链, 返回(节点副本, 内部连线, 继续节点id, 外部依赖信息)。"""
    nodes = {int(n["id"]): n for n in base["nodes"]}
    links = {int(l[0]): l for l in base["links"]}
    cont = _find_continue(nodes)
    chain_ids = _downstream(nodes, links, cont)
    # 二采链 = 继续节点下游 ∩ 不是「截帧后续段」(单图/合成保存) 的部分 —— 后者由
    # extract_frame_tail() 单独搬, 因为它挂在二采 PreviewVideo 的截帧输出上, 得等二采到位再贴。
    chain_ids = {i for i in chain_ids if not is_frame_tail(nodes[i])}
    # 再往下游的每个采样器往前溯源, 把二采的准备链(UNET/VAE/CLIP/LoRA/文本编码/潜空间准备)
    # 一并收进来 —— 只沿下游走是够不着它们的。遇到截帧段与继续节点就停。
    prep = _upstream(nodes, links, sorted(chain_ids)[0] if chain_ids else cont,
                     {"FallingTSContinue", "FallingTSImageComposite", "AutoSaveImage"})
    chain_ids |= prep
    # 溯源会顺带捞到「挂在链里但输出全空」的孤儿节点(0031 的 #200 GetImageSize 就是 ——
    # 它读二段帧只为算尺寸, 换了二采结构后再没人吃它的输出), 剔掉: 判据是「有链内出线」,
    # 只有入线没有出线的节点搬过去就是死节点。继续节点与链尾预览节点不受此限。
    sink_types = {"PreviewVideo"}
    has_out = {L[1] for L in links.values() if L[1] in chain_ids and L[3] in chain_ids}
    chain_ids = {i for i in chain_ids
                 if i in has_out or i == cont or nodes[i]["type"] in sink_types}
    chain = chain_ids | {cont}

    sub_links = [
        list(l) for l in links.values()
        if int(l[1]) in chain and int(l[3]) in chain
    ]
    # 外部依赖: 继续节点的 VIDEO 输入(来自一段 CreateVideo) + 预览的 prefix(来自 MD 表)
    prefix_src = None
    for n in base["nodes"]:
        if int(n["id"]) not in chain:
            continue
        for x in n.get("inputs") or []:
            lid = x.get("link")
            if lid is None:
                continue
            L = links.get(int(lid))
            if not L:
                continue
            if int(L[1]) in chain:
                continue
            src = nodes[int(L[1])]
            if n["type"] == "PreviewVideo" and x["name"] == "filename_prefix":
                prefix_src = {"node_type": src["type"], "slot": int(L[2])}
    sub_nodes = [json.loads(json.dumps(nodes[i])) for i in sorted(chain)]
    pv_id = next(i for i, n in nodes.items()
                 if n["type"] == "PreviewVideo" and "二采" in (n.get("title") or ""))
    tail_nodes, tail_links = extract_frame_tail(base)
    return sub_nodes, sub_links, cont, {
        "prefix": prefix_src,
        "tail_nodes": tail_nodes,
        "tail_links": tail_links,
        "links": links,
        "pv_id": pv_id,
    }


def rebuild(target_path: Path, chain_nodes, chain_links, cont_base_id, ext) -> str:
    doc = _load(target_path)
    nodes = {int(n["id"]): n for n in doc["nodes"]}
    links = {int(l[0]): l for l in doc["links"]}
    rep: list[str] = []

    # ---------- ① 删除目标工作流原有二采 ----------
    cont_old = _find_continue(nodes)
    # 二采预览的 prefix 原来接谁 —— **必须在删旧二采之前记下来**: 那条连线马上会被清掉,
    # 之后再问「接没接」永远是空, 于是所有目标都会掉进「退回 MD 表」的兜底分支。
    # 生场景(0030/0032)接 MD 表 out[2], 生视频(0040..0044)接一段预览节点的 prefix out[2],
    # 两种都是各自正确的约定, 一律原样保留。
    keep_prefix = None
    keep_suffix = ""
    for i, n in nodes.items():
        if n["type"] == "PreviewVideo" and "二采" in (n.get("title") or ""):
            wv = n.get("widgets_values")
            if isinstance(wv, list) and len(wv) > 1 and isinstance(wv[1], str):
                keep_suffix = wv[1]
            for k, x in enumerate(n.get("inputs") or []):
                if x["name"] == "filename_prefix" and x.get("link") is not None:
                    L = links.get(x["link"])
                    if L and int(L[1]) in nodes:
                        keep_prefix = {"src": int(L[1]), "slot": int(L[2]), "dst": i, "k": k}
            break
    # 判据 = 继续节点下游可达 + 标题带二采前缀。
    # ⚠️ 两轮都清不干净过一次: 旧二采有几个节点(RandomNoise/VAEDecode/MiniMaxH3ShiftSigmas)
    # 输出根本没接线, 从继续节点走不到; 而 LTXVConditioning / LatentUpscaleModelLoader 这类
    # 「有出线但出线全指向已删节点」的, 只看 any(o.links) 也会被误判成还活着。
    # 所以这里坚持按标题前缀删, 并且反复扫到不再变为止。
    # 现在的二采标题前缀是 `LTX二采 · `(这条链本身就是 LTX-2.5 潜空间放大, 早期误标成「H3高阶」),
    # 两份旧前缀都算 —— 目标工作流可能是历史存档。
    OLD_PREFIXES = ("LTX二采 · ", "H3高阶 · 二采")
    old_chain = _downstream(nodes, links, cont_old)
    removed_ids = (old_chain | {i for i, n in nodes.items()
                                if (n.get("title") or "").startswith(OLD_PREFIXES)}) - {cont_old}
    removed = 0
    for i in sorted(removed_ids):
        if i in nodes:
            del nodes[i]
            removed += 1
    # 清掉与已删节点相关的全部连线
    for lid in [lid for lid, L in links.items() if L[1] not in nodes or L[3] not in nodes]:
        del links[lid]
    # 再收口一遍端口上的 link 登记 —— 删连线不会自动抹掉端口里记住的 link id,
    # 留着的话前端会画出指向空处的线头, 打开工作流就看到一堆断线。
    for n in nodes.values():
        for o in n.get("outputs") or []:
            if o.get("links"):
                o["links"] = [v for v in o["links"] if v in links]
        for x in n.get("inputs") or []:
            if x.get("link") is not None and x["link"] not in links:
                x["link"] = None
    # 收口后输出全空的旧二采节点一并清掉, 直到不再变化。
    # ⚠️ 不能只看标题前缀: 旧二采里 LTXVConditioning / LatentUpscaleModelLoader / ManualSigmas /
    # RandomNoise / KSamplerSelect 这些节点**没有标题**(标题是给「LTX二采 · xx」那几个起的),
    # 靠前缀根本捞不到, 会整批留成输出全空的死节点。改用「连一根出线都没有」判定 ——
    # 工作流里真正有意义的节点(输出节点除外)必然有出线, 没有出线的就是被摘空的壳。
    KEEP_SINK = {"PreviewVideo", "PreviewImageSave", "PreviewAudioSave", "AutoSaveImage",
                 "SaveImage", "MarkdownNote", "Note", "FallingTSMarkDownTable",
                 "FallingTSContinue"}  # 继续节点的出线要到第 ③ 步才接上, 这里必须豁免
    while True:
        dead = {i for i, n in nodes.items()
                if n["type"] not in KEEP_SINK
                and not any(o.get("links") for o in (n.get("outputs") or []))}
        if not dead:
            break
        for i in dead:
            del nodes[i]
        removed += len(dead)
        for lid in [lid for lid, L in links.items() if L[1] not in nodes or L[3] not in nodes]:
            del links[lid]
        for n in nodes.values():
            for o in n.get("outputs") or []:
                if o.get("links"):
                    o["links"] = [v for v in o["links"] if v in links]
            for x in n.get("inputs") or []:
                if x.get("link") is not None and x["link"] not in links:
                    x["link"] = None
    # 顺手清掉继续节点上挂着的旧上游(它要改接到新二采的二段视频)
    for x in nodes[cont_old].get("inputs") or []:
        if x.get("link") is not None:
            old = links.pop(x["link"], None)
            if old:
                src = nodes.get(old[1])
                for o in src.get("outputs") or []:
                    if o.get("links"):
                        o["links"] = [v for v in o["links"] if v != x["link"]]
            x["link"] = None
    rep.append(f"删除原二采 {removed} 节点")

    # 目标工作流的 MD 表节点(预览 prefix 的数据源) —— 沿用目标自己的, 不搬 0031 的
    md_nodes = [i for i, n in nodes.items() if n["type"] == "FallingTSMarkDownTable"]
    if not md_nodes:
        raise SystemExit(f"✗ {target_path.name} 找不到 FallingTSMarkDownTable")
    md_id = md_nodes[0]
    prefix_slot = MD_PREFIX_SLOT

    # ---------- ② 贴入 0031 的二采链 ----------
    next_id = max([*nodes, *links]) + 1
    id_map: dict[int, int] = {}
    for n in chain_nodes:
        id_map[int(n["id"])] = next_id
        next_id += 1
    lid_map: dict[int, int] = {}
    for L in chain_links:
        lid_map[int(L[0])] = next_id
        next_id += 1

    # 布局: 整体平移到目标工作流右侧空白区
    xs = [n["pos"][0] for n in chain_nodes]
    ys = [n["pos"][1] for n in chain_nodes]
    min_x, min_y = min(xs), min(ys)
    tgt_xs = [(n.get("pos") or [0, 0])[0] + (n.get("size") or [0, 0])[0] for n in nodes.values() if n.get("pos")]
    tgt_ys = [(n.get("pos") or [0, 0])[1] for n in nodes.values() if n.get("pos")]
    anchor_x = max(tgt_xs) + 400 if tgt_xs else 0
    anchor_y = min(tgt_ys) if tgt_ys else 0

    # 继续节点在目标里已存在, 不重复贴 —— 把模板里的继续节点记为「复用」
    new_nodes = []
    for n in chain_nodes:
        old_id = int(n["id"])
        if old_id == cont_base_id:
            id_map[old_id] = cont_old
            continue
        n = json.loads(json.dumps(n))
        n["id"] = id_map[old_id]
        n["pos"] = [anchor_x + (n["pos"][0] - min_x), anchor_y + (n["pos"][1] - min_y)]
        n.pop("order", None)
        # 节点内部 input.link / output.links 先清空, 稍后按新连线回填
        for x in n.get("inputs") or []:
            x["link"] = None
        for o in n.get("outputs") or []:
            o["links"] = []
        new_nodes.append(n)

    # 连线重映射
    new_links = []
    for L in chain_links:
        src_old, dst_old = int(L[1]), int(L[3])
        if src_old not in id_map or dst_old not in id_map:
            continue
        new_links.append([lid_map[int(L[0])], id_map[src_old], int(L[2]), id_map[dst_old], int(L[4]), L[5]])
    # 回填节点端口引用
    bylid = {l[0]: l for l in new_links}
    all_new = {n["id"]: n for n in new_nodes}
    all_new[cont_old] = nodes[cont_old]
    for lid, L in bylid.items():
        s, d = L[1], L[3]
        if s in all_new:
            outs = all_new[s].get("outputs") or []
            if L[2] < len(outs):
                outs[L[2]].setdefault("links", [])
                if outs[L[2]]["links"] is None:
                    outs[L[2]]["links"] = []
                outs[L[2]]["links"].append(lid)
        if d in all_new:
            ins = all_new[d].get("inputs") or []
            if L[4] < len(ins):
                ins[L[4]]["link"] = lid

    for n in new_nodes:
        nodes[n["id"]] = n
    for l in new_links:
        links[l[0]] = l

    # ---------- ③ 两处外部依赖 ----------
    # (a) 继续节点 ← 一段的 CreateVideo(VIDEO)
    cv1 = [i for i, n in nodes.items()
           if n["type"] == "CreateVideo" and "二采" not in (n.get("title") or "")]
    cont_in = nodes[cont_old]["inputs"][0]
    if cv1:
        cv = cv1[0]
        lid = max(links) + 1
        links[lid] = [lid, cv, 0, cont_old, 0, "VIDEO"]
        nodes[cv]["outputs"][0].setdefault("links", [])
        if nodes[cv]["outputs"][0]["links"] is None:
            nodes[cv]["outputs"][0]["links"] = []
        nodes[cv]["outputs"][0]["links"].append(lid)
        cont_in["link"] = lid
        cont_in["type"] = "VIDEO"
        rep.append(f"继续节点 ← #{cv}(CreateVideo).VIDEO")
    else:
        rep.append("⚠ 找不到一段 CreateVideo, 继续节点留空")
    # (b) 二采预览 prefix ← 目标自己的数据源
    # ⚠️ 两种接法都不能硬搬:
    #   · 生场景(0030/0032): 接自己的 MD 表, 端口号是目标约定(0031 是 out[0], 它们一直是 out[2])
    #   · 生视频(0040..0044): 接**一段预览节点的 prefix 输出**(out[2]) —— 它们的产物命名走
    #     「加载/预览节点的序列号前缀」那套, 根本没有 MD 表参与, 改成 MD 表会落错目录
    # 所以判据是「原来接谁就还接谁」: 保留目标自己的连线, 只在完全没接时才退回 MD 表。
    pv = [i for i, n in nodes.items() if n["type"] == "PreviewVideo" and "二采" in (n.get("title") or "")]
    if pv:
        p = pv[0]
        slot = next(i for i, x in enumerate(nodes[p]["inputs"]) if x["name"] == "filename_prefix")
        src = None if keep_prefix is None else keep_prefix["src"]
        if src is not None and src in nodes:
            lid = max(links) + 1
            sslot = keep_prefix["slot"]
            links[lid] = [lid, src, sslot, p, slot, "STRING"]
            so = nodes[src].get("outputs") or []
            if sslot < len(so):
                if so[sslot].get("links") is None:
                    so[sslot]["links"] = []
                so[sslot]["links"].append(lid)
            nodes[p]["inputs"][slot]["link"] = lid
            rep.append(f"二采预览 prefix ← #{src}({nodes[src]['type']}).out[{sslot}]")
        else:
            lid = max(links) + 1
            links[lid] = [lid, md_id, prefix_slot, p, slot, "STRING"]
            nodes[md_id]["outputs"][prefix_slot].setdefault("links", [])
            if nodes[md_id]["outputs"][prefix_slot]["links"] is None:
                nodes[md_id]["outputs"][prefix_slot]["links"] = []
            nodes[md_id]["outputs"][prefix_slot]["links"].append(lid)
            nodes[p]["inputs"][slot]["link"] = lid
            rep.append(f"二采预览 prefix ← #{md_id}(MD 表).out[{prefix_slot}]")

    # ---------- ④ 贴入截帧后续段(8 单图 + 四图/八图合成 + 2 合成保存) ----------
    # ⚠️ 只有**生场景**要这段(场景的交付物就是那张四图/八图合成)。
    # 生视频的产物是一段视频, 二采预览之后什么都不挂 —— 用户明确要求「不要后面的八图、合成」。
    drop_tail = target_path.name in VIDEO_TARGETS
    tail_nodes, tail_links = ext["tail_nodes"], ext["tail_links"]
    links_src = ext["links"]      # 0031 自己的连线表, 用来查尾段的外部引用指向谁
    pv_base_id = ext["pv_id"]      # 0031 的二采预览节点 id
    old_tail = {i for i, n in nodes.items() if is_frame_tail(n)}
    if old_tail:
        for i in old_tail:
            del nodes[i]
        for lid in [lid for lid, L in links.items() if L[1] not in nodes or L[3] not in nodes]:
            del links[lid]
        for n in nodes.values():
            for o in n.get("outputs") or []:
                if o.get("links"):
                    o["links"] = [v for v in o["links"] if v in links]
            for x in n.get("inputs") or []:
                if x.get("link") is not None and x["link"] not in links:
                    x["link"] = None
    if drop_tail:
        # 生视频: 只把二采预览本身留成一个 3 槽节点(video/audio/prefix), 不补 image_* 槽。
        pvn = nodes[[i for i, n in nodes.items()
                     if n["type"] == "PreviewVideo" and "二采" in (n.get("title") or "")][0]]
        while len(pvn.get("outputs") or []) > 3:
            pvn["outputs"].pop()
        # ⚠️ 模板是从 0031 整条摘的, 预览节点带着**0031 的截帧列表与 _1080p 后缀**。
        # 生视频不挂截帧段 ⇒ 那些 frame blob 指向 8189 的临时会话, 留着只会是死数据;
        # 后缀也不该跟 0031 走, 保留目标原有的一段约定(生视频一直是空串或 _1088p)。
        pv_wv = pvn.get("widgets_values")
        if isinstance(pv_wv, list) and len(pv_wv) >= 7:
            pv_wv[1] = keep_suffix
            pv_wv[2] = pv_wv[3] = pv_wv[4] = None
            pv_wv[5] = 1
            pv_wv[6] = {"frames": []}
            while len(pv_wv) > 7:
                pv_wv.pop()
        named = pvn.get("widgets_values_named")
        if isinstance(named, dict):
            named["filename_suffix"] = keep_suffix
            named["保存"] = None
            named["截帧"] = None
            named["完成"] = None
            named["输出帧数"] = 1
            named["frame_list"] = {"frames": []}
        doc["nodes"] = [nodes[i] for i in sorted(nodes)]
        doc["links"] = [links[i] for i in sorted(links)]
        for idx, n in enumerate(sorted(doc["nodes"], key=lambda x: (x["pos"][1], x["pos"][0]))):
            n["order"] = idx
        doc["last_node_id"] = max(nodes)
        doc["last_link_id"] = max(links)
        target_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        rep.append(f"生视频: 不挂截帧后续段, 预览后缀={keep_suffix!r}  写回 {target_path.name}: {len(nodes)} 节点 / {len(links)} 连线")
        return "  ".join(rep)

    pv_old = [i for i, n in nodes.items()
              if n["type"] == "PreviewVideo" and "二采" in (n.get("title") or "")][0]
    # 二采预览必须备齐 image_1..image_8 输出槽 —— 尾段 8 个单图保存就是挂在它们上面的。
    # 生场景(0030/0032)存档里本来就有 11 槽, 生视频(0040..0044)只有 video/audio/prefix 三槽,
    # 不补的话 image_* 连线无处可挂。
    # ⚠️ 槽数由前端的「输出帧数」控件(3 + total)决定, 该控件在 widgets_values **下标 5**
    # (槽序: 前缀/后缀/保存/截帧/完成/输出帧数/frame_list/video_fallback)。存档里若没写
    # total, 前端按默认 1 重建 ⇒ 只剩 4 槽、image_2..8 被裁掉。所以这里连 total 一起写足。
    pvn = nodes[pv_old]
    # 尾段有 8 个单图保存, 每个吃一个 image_* 槽 ⇒ 至少要 8 个
    pv_total = 8
    while len(pvn.get("outputs") or []) < 3 + pv_total:
        outs = pvn.setdefault("outputs", [])
        outs.append({"name": f"image_{len(outs) - 2}", "type": "IMAGE", "slot_index": len(outs) - 3,
                     "links": []})
    pv_wv = pvn.get("widgets_values")
    if isinstance(pv_wv, list):
        while len(pv_wv) < 6:
            pv_wv.append(None)
        pv_wv[0] = pv_wv[0] or ""
        pv_wv[5] = pv_total
    named = pvn.get("widgets_values_named")
    if isinstance(named, dict):
        named["输出帧数"] = pv_total
    rep.append(f"二采预览补至 {len(pvn['outputs'])} 输出槽(输出帧数={pv_total})")
    # 尾段里对「二采预览」的外部引用: images ← image_1..image_8, filename_prefix ← prefix
    tail_ids = {int(n["id"]) for n in tail_nodes}
    t_map: dict[int, int] = {}
    tid = max([*nodes, *links]) + 1
    for i in sorted(tail_ids):
        t_map[i] = tid
        tid += 1
    l_map: dict[int, int] = {}
    for L in tail_links:
        l_map[int(L[0])] = tid
        tid += 1

    # 布局: 尾段整体挪到二采预览右侧(它自己按 0031 的相对位置平移)
    txs = [n["pos"][0] for n in tail_nodes]
    tys = [n["pos"][1] for n in tail_nodes]
    t_min_x, t_min_y = min(txs), min(tys)
    pvw = nodes[pv_old]
    t_anchor_x = (pvw.get("pos") or [0, 0])[0] + (pvw.get("size") or [0, 0])[0] + 120
    t_anchor_y = (pvw.get("pos") or [0, 0])[1]

    for n in tail_nodes:
        n = dict(n)
        n["id"] = t_map[int(n["id"])]
        n["pos"] = [t_anchor_x + (n["pos"][0] - t_min_x), t_anchor_y + (n["pos"][1] - t_min_y)]
        n.pop("order", None)
        for x in n.get("inputs") or []:
            x["link"] = None
        for o in n.get("outputs") or []:
            o["links"] = []
        nodes[n["id"]] = n

    # 尾段内部连线 + 指向二采预览的外部连线
    new_tail_links = []
    for L in tail_links:
        s, d = int(L[1]), int(L[3])
        if s not in t_map or d not in t_map:
            continue
        new_tail_links.append([l_map[int(L[0])], t_map[s], int(L[2]), t_map[d], int(L[4]), L[5]])
    # 外部: 尾段里凡是原来接 0031 二采预览的, 改接目标里的二采预览。
    # ⚠️ 必须拿 links_src 反查 —— 上面贴节点时已把副本的 input.link 清成 None。
    cnt_ext = 0
    nl_next = max([*nodes, *l_map.values()]) + 1
    for lid, L in links_src.items():
        s, d = int(L[1]), int(L[3])
        if d not in t_map or s != pv_base_id:
            continue
        nid = t_map[d]
        ins = nodes[nid].get("inputs") or []
        nxt = [l for l in new_tail_links if l[3] == nid and l[4] == int(L[4])]
        if nxt:
            continue
        new_tail_links.append([nl_next, pv_old, int(L[2]), nid, int(L[4]), L[5]])
        nl_next += 1
        cnt_ext += 1
    for l in new_tail_links:
        links[l[0]] = l
    for l in new_tail_links:
        s, d = l[1], l[3]
        if s in nodes:
            outs = nodes[s].get("outputs") or []
            if l[2] < len(outs):
                if outs[l[2]].get("links") is None:
                    outs[l[2]]["links"] = []
                outs[l[2]]["links"].append(l[0])
        if d in nodes:
            ins = nodes[d].get("inputs") or []
            if l[4] < len(ins):
                ins[l[4]]["link"] = l[0]
    rep.append(f"截帧后续段 {len(t_map)} 节点({cnt_ext} 处接二采预览)")

    # ---------- ⑤ 写回 ----------
    doc["nodes"] = [nodes[i] for i in sorted(nodes)]
    doc["links"] = [links[i] for i in sorted(links)]
    for idx, n in enumerate(sorted(doc["nodes"], key=lambda x: (x["pos"][1], x["pos"][0]))):
        n["order"] = idx
    doc["last_node_id"] = max(nodes)
    doc["last_link_id"] = max(links)
    target_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    rep.append(f"写回 {target_path.name}: {len(nodes)} 节点 / {len(links)} 连线")
    return "  ".join(rep)


def main() -> int:
    base = _load(WF_DIR / BASE)
    chain_nodes, chain_links, cont_base_id, ext = extract_chain(base)
    print(f"模板 {BASE}: 二采链 {len(chain_nodes)} 节点 / {len(chain_links)} 内部连线")
    rc = 0
    for name in TARGETS:
        p = WF_DIR / name
        if not p.is_file():
            print(f"✗ 找不到 {p}")
            rc = 2
            continue
        print(f"\n{'=' * 70}\n{name}\n  " + rebuild(p, chain_nodes, chain_links, cont_base_id, ext))
    return rc


if __name__ == "__main__":
    sys.exit(main())
