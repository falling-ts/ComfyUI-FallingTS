# -*- coding: utf-8 -*-
"""为 workflows/00200_场景首帧_QI2.1.json 移植「优化二次采样」段(参考 00110_万物建模_QI2.1)。

链路(与 00110 的二次采样段同构):
  #42 主结果 保存/预览 → #85 FallingTSContinue
  #85 ─┬→ #87 VAEEncode(编辑底图) ──→ #102 KSampler.latent_image
       ├→ #88 编辑正词编码.image1
       ├→ #89 编辑负词编码.image1
       └→ #90 ImageCompare.image_a
  #91 Qwen-Edit 2511 基座 → #92 采样平移 → #93 CFGNorm
       ├ 真(加速) #94 Lightning LoRA → #95 3D国漫 LoRA → #96 Sage → #97.true_1
       └ 假(标准) ─────────────────────────────────────────→ #97.false_1
  #98 步数40 / #99 步数4 / #100 denoise / #101 denoise / #107 CFG3 / #108 CFG1 → #97
  #97 → #102 KSampler → #103 VAEDecode ─┬→ #104 编辑结果 保存/预览
                                        └→ #90.image_b
  #105 CLIP(1.x) / #106 VAE(1.x) 供编辑编码与解码
  #10 MD 表 ID → #104.filename_prefix

幂等: 先删除本段既有节点与连线(含 #42/#10 输出端口上的残留引用), 再按定义重建;
      不触碰主链与 MD 表数据(选中行/表路径)。
自检: 布局六规范(可机检部分) + 连线回填一致性; 第 2 条端口顺序只提示不拦
      (该拓扑下 switch 同时供 model 与 steps/cfg/denoise, 端口序在数学上无解 —— 与 00110/0020 同)。
"""
import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
REF = os.path.join(ROOT, "workflows", "00110_万物建模_QI2.1.json")
TGT = os.path.join(ROOT, "workflows", "00200_场景首帧_QI2.1.json")

# 本段节点 id(85..108); 107/108 是「编辑 CFG」primitive(00110 复用主链 35/36,
# 这里独立出来, 才能让 switch 的 8 个输入端口按 y 序排列)
STAGE_IDS = [85, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99,
             100, 101, 102, 103, 104, 105, 106, 107, 108]
# 新建节点无同名模板时, 从 00110 的哪个节点取结构
TEMPLATE = {107: 35, 108: 36}

# (link_id, src_node, src_slot, dst_node, dst_slot, type)
LINKS = [
    (75, 42, 0, 85, 0, "IMAGE"),
    (76, 85, 0, 87, 0, "IMAGE"),
    (77, 85, 0, 88, 2, "IMAGE"),
    (78, 85, 0, 89, 2, "IMAGE"),
    (79, 85, 0, 90, 0, "IMAGE"),
    (80, 106, 0, 87, 1, "VAE"),
    (81, 105, 0, 88, 0, "CLIP"),
    (82, 106, 0, 88, 1, "VAE"),
    (83, 105, 0, 89, 0, "CLIP"),
    (84, 106, 0, 89, 1, "VAE"),
    (85, 91, 0, 92, 0, "MODEL"),
    (86, 92, 0, 93, 0, "MODEL"),
    (87, 93, 0, 94, 0, "MODEL"),
    (88, 93, 0, 97, 0, "MODEL"),
    (89, 94, 0, 95, 0, "MODEL"),
    (90, 95, 0, 96, 0, "MODEL"),
    (91, 96, 0, 97, 1, "MODEL"),
    (92, 98, 0, 97, 2, "INT"),
    (93, 99, 0, 97, 3, "INT"),
    (94, 100, 0, 97, 4, "FLOAT"),
    (95, 101, 0, 97, 5, "FLOAT"),
    (96, 107, 0, 97, 6, "FLOAT"),
    (97, 108, 0, 97, 7, "FLOAT"),
    (98, 97, 0, 102, 0, "MODEL"),
    (99, 97, 1, 102, 5, "INT"),
    (100, 97, 2, 102, 9, "FLOAT"),
    (101, 97, 3, 102, 6, "FLOAT"),
    (102, 88, 0, 102, 1, "CONDITIONING"),
    (103, 89, 0, 102, 2, "CONDITIONING"),
    (104, 87, 0, 102, 3, "LATENT"),
    (105, 102, 0, 103, 0, "LATENT"),
    (106, 106, 0, 103, 1, "VAE"),
    (107, 103, 0, 90, 1, "IMAGE"),
    (108, 103, 0, 104, 0, "IMAGE"),
    (109, 10, 0, 104, 1, "STRING"),
]
STAGE_LINK_IDS = set(l[0] for l in LINKS)

# 布局: 从起点逐个向右下推进后锁定; 列距 60 / 行距 60, 落在 (50,100)
POS = {
    85:  (4780, 400),   # 继续
    105: (4780, 0),     # 编辑 CLIP 编码器 (1.x)
    106: (4780, 230),   # 编辑 VAE (1.x)
    88:  (5150, 120),   # 编辑正词 编码
    89:  (5150, 480),   # 编辑负词 编码
    87:  (5150, 840),   # 编辑图像 编码
    91:  (5610, 0),     # Qwen-Edit 模型
    92:  (5940, 0),     # 编辑 采样平移
    93:  (6270, 0),     # 编辑 CFG 归一
    94:  (6600, 0),     # 编辑 Lightning LoRA
    95:  (6930, 0),     # 编辑 3D国漫 LoRA
    96:  (7260, 140),   # 编辑 Sage 加速
    98:  (7260, 340),   # 编辑 步数 40
    99:  (7260, 490),   # 编辑 步数 4
    100: (7260, 640),   # 编辑 denoise 标准
    101: (7260, 790),   # 编辑 denoise 加速
    107: (7260, 940),   # 编辑 CFG 标准
    108: (7260, 1090),  # 编辑 CFG 加速
    97:  (7565, 0),     # 编辑 4步/40步 切换
    102: (7920, 0),     # 编辑 采样
    103: (8230, 520),   # 编辑结果 解码
    104: (8530, 300),   # 编辑结果 保存/预览
    90:  (9840, 520),   # 前后对比
}
SIZE = {
    85:  [230, 120], 105: [310, 170], 106: [310, 110],
    88:  [400, 300], 89:  [400, 300], 87:  [230, 80],
    91:  [270, 140], 92:  [270, 120], 93:  [270, 120],
    94:  [270, 120], 95:  [270, 120], 96:  [250, 120],
    98:  [230, 90], 99:  [230, 90], 100: [230, 90], 101: [230, 90],
    107: [230, 90], 108: [230, 90],
    97:  [300, 340], 102: [250, 540], 103: [230, 80],
    104: [1230, 1010], 90: [1620, 1010],
}
TITLE = {
    85: "", 87: "编辑图像 编码", 88: "编辑提示词 编码 (正)",
    89: "优化负面提示词 编码 (带图)", 90: "前后对比", 91: "Qwen-Edit 模型",
    92: "编辑 采样平移", 93: "编辑 CFG 归一", 94: "编辑 Lightning LoRA",
    95: "编辑 3D国漫 LoRA", 96: "编辑 Sage 加速", 97: "编辑 4步/40步 切换",
    98: "编辑 步数 40 (标准)", 99: "编辑 步数 4 (加速)",
    100: "编辑 denoise 0.5 (标准)", 101: "编辑 denoise 0.5 (加速)",
    102: "编辑 采样", 103: "编辑结果 解码", 104: "编辑结果 保存/预览",
    105: "编辑 CLIP 编码器 (1.x)", 106: "编辑 VAE (1.x, 16通道)",
    107: "编辑 CFG 3.0 (标准)", 108: "编辑 CFG 1.0 (加速)",
}
NEG = ("worst quality, low quality, normal quality, lowres, bad anatomy, bad hands, "
       "missing fingers, extra fingers, too many fingers, mutated hands, poorly drawn hands, "
       "poorly drawn face, mutation, deformed, ugly, blurry, out of focus, bad proportions, "
       "bad body, extra limbs, cloned face, disfigured, malformed limbs, missing arms, "
       "missing legs, extra arms, extra legs, fused fingers, long neck, cross-eyed, "
       "floating limbs, disconnected limbs, watermark, signature, text, username, logo, "
       "cropped, duplicate, error, jpeg artifacts, oversaturated, grainy")
WV = {
    87: [None],
    88: ["依据图1 参考, 提升图片整体画质和像素。"],
    89: [NEG],
    90: [],
    91: ["qwen_image_edit_2511_fp8mixed.safetensors", "default"],
    92: [3.1, "flow"],
    93: [1, False],
    94: ["Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors", 1],
    95: ["[Qwen-Edit]3DChineseStyle_25.safetensors", 0.8],
    96: ["sageattn_qk_int8_pv_fp16_cuda", True],
    97: [True, 4],
    98: [40, "fixed"],
    99: [4, "fixed"],
    100: [0.5],
    101: [0.5],
    102: [0, "fixed", 4, 1, "euler", "simple", 1],
    103: [None],
    104: ["preview", "", "png", "8-bit", "sRGB", None, ""],
    105: ["qwen_2.5_vl_7b_fp8_scaled.safetensors", "qwen_image", "default"],
    106: ["qwen_image_vae.safetensors"],
    107: [3],
    108: [1],
}
WVN = {
    88: {"prompt": WV[88][0]},
    89: {"prompt": WV[89][0]},
    91: {"unet_name": WV[91][0], "weight_dtype": WV[91][1]},
    92: {"shift": 3.1, "sampling": "flow"},
    93: {"strength": 1, "pre_cfg": False},
    94: {"lora_name": WV[94][0], "strength_model": 1},
    95: {"lora_name": WV[95][0], "strength_model": 0.8},
    96: {"sage_attention": WV[96][0], "allow_compile": True},
    97: {"switch": True, "total": 4},
    98: {"value": 40, "fixed": "fixed"},
    99: {"value": 4, "fixed": "fixed"},
    100: {"value": 0.5},
    101: {"value": 0.5},
    102: {"seed": 0, "control_after_generate": "fixed", "steps": 4, "cfg": 1,
          "sampler_name": "euler", "scheduler": "simple", "denoise": 1},
    104: {"filename_prefix": "preview", "filename_suffix": "", "format": "png",
          "bit_depth": "8-bit", "input_color_space": "sRGB"},
    105: {"clip_name": WV[105][0], "type": "qwen_image", "device": "default"},
    106: {"vae_name": WV[106][0]},
    107: {"value": 3},
    108: {"value": 1},
}

NOTE = """## 场景首帧 2.1 (场景首帧生成 · Qwen-Image 2.1)

场景首帧管线(《七纹刻印》场景首帧生成),两阶段链路:

1. **主生成(文生图)**: Qwen-Image 2.1 按表格「主-正词」生成场景首帧
2. **优化二次采样(图生图)**: 主结果交给 `FallingTSContinue` 放行, 再以 **Qwen-Image-Edit 2511**(1.x 编辑基座)
   作图生图提升细节; 底图 = 主结果, 参考图 image1 = 主结果
3. **场景库**: `FallingTSMarkDownTable` 读取 `stories/七纹刻印/0020_场景首帧.md`(与 1.x 版共用表), 一次选中一个场景行
4. **前后对比**: `ImageCompare` 左 = 主结果, 右 = 二次采样结果

### 主生成链(2.1)
- 基座 **Qwen-Image 2.1**(7B 统一生成+编辑模型), 文本编码器 **Qwen3-VL 8B**, VAE 为 **64 通道 RGBA**
- 不加载任何 LoRA; 步数按 2.1 官方域: 标准 40 步 / 加速 20 步, cfg 固定 1.0
- 新增 **Qwen Image 2.1 Cache** 节点复用 KV 前缀

### 优化二次采样链(移植自 00110_万物建模_QI2.1)
- 该段用 **1.x 专属** 的 CLIP(`qwen_2.5_vl_7b_fp8_scaled`)与 VAE(`qwen_image_vae`), 与 2.1 主链**互不共用**
- 基座 `qwen_image_edit_2511_fp8mixed`, 加速档叠 **Lightning 4step LoRA + 3D国漫 LoRA**
- 提示词写死在节点上: 正词 `依据图1 参考, 提升图片整体画质和像素。`, 负词为通用清单
  (cfg=1.0 时负词不生效, 仅作保留; 需要按行定制时把表格加回 TEXT 列并接回端口)
- 步数/denoise/cfg 由「编辑 4步/40步 切换」按连线取值(加速档 4步 / denoise 0.5 / cfg 1.0)
- ⚠️ **二次采样段的图必须从 `FallingTSContinue` 的输出接**(不能直连主结果保存节点),
  否则「继续」分段执行时会把主生成段整条拉回来重跑

### 场景库(MD 数据表)
- 数据源: `stories/七纹刻印/0020_场景首帧.md`(md 为唯一数据源, 「刷新」按 ID 重新查询)
- 5 列: `ID | 主-正词 | 主-负词 | 宽度 | 高度`(与 `0011_万物建模` 同构)
- 连线: ID → 两个保存节点的 filename_prefix; 主-正词/主-负词 → 主链 `TextEncodeQwenImage21`; 宽度/高度 → `EmptyLatentImage`
"""


def topo_order(nodes, links):
    """计算拓扑序(只依赖连线, 与存档里的 order 无关)。"""
    ids = [n["id"] for n in nodes]
    deps = {i: set() for i in ids}
    for _lid, a, _ao, b, _bo, _t in links:
        if a in deps and b in deps:
            deps[b].add(a)
    order, done = {}, set()
    remaining = set(ids)
    rank = 0
    while remaining:
        ready = [i for i in sorted(remaining) if deps[i] <= done]
        if not ready:
            ready = sorted(remaining)
        for i in ready:
            order[i] = rank
            rank += 1
            done.add(i)
            remaining.discard(i)
    return order


def build():
    with open(REF, encoding="utf-8") as f:
        ref = json.load(f)
    with open(TGT, encoding="utf-8") as f:
        tgt = json.load(f)

    refnodes = {n["id"]: n for n in ref["nodes"]}

    # ── 1. 幂等: 先摘掉本段既有节点与连线, 并清掉落在端口上的残留引用 ──────
    tgt["nodes"] = [n for n in tgt["nodes"] if n["id"] not in STAGE_IDS]
    tgt["links"] = [l for l in tgt["links"]
                    if l[0] not in STAGE_LINK_IDS
                    and l[1] not in STAGE_IDS and l[3] not in STAGE_IDS]
    for n in tgt["nodes"]:
        for o in n.get("outputs") or []:
            if o.get("links"):
                o["links"] = [l for l in o["links"] if l not in STAGE_LINK_IDS]
        for i in n.get("inputs") or []:
            if i.get("link") in STAGE_LINK_IDS:
                i["link"] = None

    # ── 2. 造本段节点(结构照抄 00110, 连线/坐标/标题/参数覆盖) ───────────
    in_link, out_link = {}, {}
    for lid, a, ao, b, bo, _t in LINKS:
        in_link[(b, bo)] = lid
        out_link.setdefault((a, ao), []).append(lid)

    made = []
    for nid in STAGE_IDS:
        tmpl = refnodes.get(TEMPLATE.get(nid, nid))
        if tmpl is None:
            raise SystemExit("00110 里找不到模板节点 %d" % nid)
        n = copy.deepcopy(tmpl)
        n["id"] = nid
        n["pos"] = list(POS[nid])
        n["size"] = list(SIZE[nid])
        n["title"] = TITLE[nid]
        n["mode"] = 0
        n["flags"] = {}
        for idx, inp in enumerate(n.get("inputs") or []):
            inp["link"] = in_link.get((nid, idx))
        for idx, out in enumerate(n.get("outputs") or []):
            out["links"] = sorted(out_link.get((nid, idx), []))
        if nid in WV:
            n["widgets_values"] = copy.deepcopy(WV[nid])
        if nid in WVN:
            n["widgets_values_named"] = copy.deepcopy(WVN[nid])
        made.append(n)

    tgt["nodes"].extend(made)
    tgt["links"].extend([list(l) for l in LINKS])

    # ── 3. 端点回填: #42(继续的上游) 与 #10(MD 表 ID) 的输出端口 ─────────
    by_id = {n["id"]: n for n in tgt["nodes"]}
    for lid, a, ao, b, bo, _t in LINKS:
        outs = by_id[a]["outputs"][ao]
        outs.setdefault("links", [])
        if lid not in outs["links"]:
            outs["links"].append(lid)
            outs["links"].sort()
        by_id[b]["inputs"][bo]["link"] = lid

    # ── 4. 说明文档 ──────────────────────────────────────────────────
    note = by_id[1]
    note["widgets_values"] = [NOTE]
    note["widgets_values_named"] = {"text": NOTE}

    # ── 5. 元数据 ────────────────────────────────────────────────────
    tgt["nodes"].sort(key=lambda n: n["id"])
    tgt["last_node_id"] = max(tgt["last_node_id"], max(STAGE_IDS))
    tgt["last_link_id"] = max(tgt["last_link_id"], max(STAGE_LINK_IDS))
    order = topo_order(tgt["nodes"], tgt["links"])
    for n in tgt["nodes"]:
        n["order"] = order[n["id"]]
    return tgt


def check(wf):
    """布局六规范(可机检部分) + 连线回填自检, 返回 (错误, 提示)。"""
    err, info = [], []
    nodes = {n["id"]: n for n in wf["nodes"]}
    box = {}
    for i, n in nodes.items():
        x, y = n["pos"]
        box[i] = (x, y, x + n["size"][0], y + n["size"][1])

    # 第 1 条: 每条连线 A→B 必须 A 右缘 <= B 左缘
    for lid, a, _ao, b, _bo, _t in wf["links"]:
        if box[a][2] > box[b][0]:
            err.append("[1] 连线 %d: %d(%s) 右缘 %d > %d(%s) 左缘 %d"
                       % (lid, a, nodes[a]["type"], box[a][2],
                          b, nodes[b]["type"], box[b][0]))

    # 第 2 条: 端口上下顺序(只提示)
    for nid in STAGE_IDS:
        if nid not in nodes:
            continue
        ups = {}
        for _lid, a, _ao, b, bo, _t in wf["links"]:
            if b == nid:
                ups[bo] = a
        ports = sorted(ups)
        for x in range(len(ports)):
            for y in range(x + 1, len(ports)):
                p, q = ports[x], ports[y]
                if ups[p] == ups[q]:
                    continue
                cp = (box[ups[p]][1] + box[ups[p]][3]) / 2.0
                cq = (box[ups[q]][1] + box[ups[q]][3]) / 2.0
                if cp > cq:
                    info.append("[2] 节点 %d(%s) 输入端口 %d/%d 序与上游 y 序相反"
                                % (nid, nodes[nid]["type"], p, q))

    # 第 3 条: 不重叠 + 相邻净距 (50,100) —— 只判「最近的同列/同行邻居」,
    # 远距节点之间不判上限(规范只约束相邻者)。
    ids = sorted(nodes)
    for x in range(len(ids)):
        for y in range(x + 1, len(ids)):
            a, b = ids[x], ids[y]
            ax0, ay0, ax1, ay1 = box[a]
            bx0, by0, bx1, by1 = box[b]
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                err.append("[3] 节点重叠: %d(%s) / %d(%s)"
                           % (a, nodes[a]["type"], b, nodes[b]["type"]))

    # 相邻净距 (50,100): 取「最近邻」口径 —— 对每个节点, 在与其 y 区间重叠的节点里
    # 找紧邻右侧(无第三个节点挡在中间)的那个, 量其 x 净距; 纵向同理。只作提示:
    # 第 2 条端口顺序在数学上可能要求拉大间距, 规范也把上限降级为紧凑性要求。
    def ovl_y(i, j):
        return box[i][1] < box[j][3] and box[j][1] < box[i][3]

    def ovl_x(i, j):
        return box[i][0] < box[j][2] and box[j][0] < box[i][2]

    for i in ids:
        rights = [j for j in ids if j != i and ovl_y(i, j) and box[j][0] >= box[i][2]]
        rights.sort(key=lambda j: box[j][0])
        if not rights:
            continue
        # 跳过中间还挡着别的节点的
        first = rights[0]
        gap = box[first][0] - box[i][2]
        if not (50 < gap < 100):
            info.append("[3] 横向最近邻净距 %d: %d(%s)→%d(%s)"
                        % (gap, i, nodes[i]["type"], first, nodes[first]["type"]))
    for i in ids:
        belows = [j for j in ids if j != i and ovl_x(i, j) and box[j][1] >= box[i][3]]
        belows.sort(key=lambda j: box[j][1])
        if not belows:
            continue
        first = belows[0]
        gap = box[first][1] - box[i][3]
        if not (50 < gap < 100):
            info.append("[3] 纵向最近邻净距 %d: %d(%s)↓%d(%s)"
                        % (gap, i, nodes[i]["type"], first, nodes[first]["type"]))

    # MD 表独占一列(正下方无限延伸, 同列任何位置都不许放节点)
    for m in [n for n in wf["nodes"] if n["type"] == "FallingTSMarkDownTable"]:
        mx0, my0, mx1, _my1 = box[m["id"]]
        for i in ids:
            if i == m["id"]:
                continue
            x0, y0, x1, _y1 = box[i]
            if x0 < mx1 and mx0 < x1 and y0 > my0:
                err.append("[3] MD 表同列下方有节点: %d(%s)"
                           % (i, nodes[i]["type"]))

    # 连线回填一致性
    for lid, a, ao, b, bo, _t in wf["links"]:
        if lid not in (nodes[a]["outputs"][ao].get("links") or []):
            err.append("[回填] 连线 %d 未写进 %d.outputs[%d].links" % (lid, a, ao))
        if nodes[b]["inputs"][bo].get("link") != lid:
            err.append("[回填] 连线 %d 未写进 %d.inputs[%d].link" % (lid, b, bo))
    return err, info


def main():
    wf = build()
    err, info = check(wf)
    if err:
        print("布局/结构自检: 有问题")
        for e in err:
            print("  ERR", e)
        return 1
    with open(TGT, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("已写入 %s: %d 节点 / %d 连线"
          % (os.path.basename(TGT), len(wf["nodes"]), len(wf["links"])))
    print("布局自检: 无误")
    for t in info:
        print("  提示", t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
