# -*- coding: utf-8 -*-
"""
生成 workflows/0017_建模细节.json —— 结构照 0022_场景推镜.json 克隆。

用途: 建模拆图(0016)的局部细节放大精修 —— MD 表(原图 + 正/负词) → 框选细节区域
→ 放大到工作分辨率 → Qwen-Image-Edit 一次优化采样 → PreviewImageSave 保存/预览 → 对比。

相对 0022 的改动:
  1. MD 表换成本表 0017_建模细节.md, 字段 原场景 → 原图;
  2. 节点标题改成「建模细节」口径;
  3. 修 0022 里两处真缺陷: 连线 58/59 没回填到 12/5 的输出端口; 29/30 两个
     PrimitiveFloat 摆在 switch 的同一列里(右缘 3700 越过 switch 左缘 3470, 违反布局第 1 条);
  4. 补 0022 里三处 <50px 的纵向边距(6/13、13/12、3/27);
  5. MD 节点独占一列, 尺寸收到 460x700。

幂等: 重复运行结果不变。自检: 布局六规范(第 2 条只提示不拦) + 连线回填一致性。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
SRC = os.path.join(ROOT, "workflows", "0022_场景推镜.json")
DST = os.path.join(ROOT, "workflows", "0017_建模细节.json")
TABLE_REL = "stories/七纹刻印/0017_建模细节.md"

MD_TITLE = "MD 数据表 (建模细节)"

FIELDS = [
    {"name": "ID", "type": "STRING"},
    {"name": "原图", "type": "IMAGE"},
    {"name": "主-正词", "type": "TEXT"},
    {"name": "主-负词", "type": "TEXT"},
]
SEL_ID = "00001_陈落_面部细节"
SEL = {
    "ID": SEL_ID,
    "原图": "@{0016_建模拆图/00001_陈落_左上}",
    "主-正词": "整体提升画质",
    "主-负词": "模糊",
}

NOTE = """## 建模细节 (局部放大精修)

**用法**
1. 「MD 数据表」选当前要处理的**那一行**(原图引用 + 细节提示词 + 输出文件名)
2. 「框选细节区域」填 x/y/width/height 框选要放大的细节(或在画布上拖框)
3. 「细节放大」把框选区域放大到工作分辨率(默认长边 1024)
4. 运行 → 一遍**优化采样** → 「结果 保存/预览」点底部「保存」

**要点**
- 原图来自 MD 表「原图」字段(@{表名/ID} 引用, 运行时按 output/input 目录解析)
- 「4步/20步」: true=加速(4步快看), false=标准(20步成图); cfg 固定 1, 负面已清零
- 框选无预览时可直接填数值; 预览在「细节放大 预览」节点看
- 链路: 0011 万物建模 → 0016 建模拆图 → **0017 建模细节**(本表, 逐块精修)
"""

RETITLE = {
    3: "框选细节区域",
    4: "细节放大 (长边1024)",
    5: "细节放大 预览",
    25: "使用说明",
}

# 布局: 从起点逐个向右下推进后锁定(布局第 6 条)。
# 横向相邻净间距一律 80px, 纵向相邻净间距一律 60px, 都落在 (50,100) 区间内。
POS = {
    25: (40, 10),        # 使用说明
    1:  (760, 10),       # MD 数据表 (独占一列)
    6:  (1290, 0),       # UNETLoader
    13: (1290, 200),     # CLIPLoader
    12: (1290, 430),     # VAELoader
    3:  (1290, 600),     # ImageCropV2
    27: (1290, 1170),    # GetImageSize
    7:  (1610, 0),       # ModelSamplingAuraFlow
    8:  (1930, 0),       # CFGNorm
    4:  (1870, 560),     # 细节放大
    10: (2250, 0),       # LoraLoaderModelOnly 3D国漫
    11: (2570, 0),       # PathchSageAttentionKJ
    5:  (2290, 560),     # 细节放大 预览
    9:  (2870, 0),       # LoraLoaderModelOnly Lightning
    15: (2940, 560),     # TextEncodeQwenImageEditPlus 正
    14: (2940, 1280),    # VAEEncode
    28: (2940, 920),     # TextEncodeQwenImageEditPlus 负
    21: (3420, 200),     # PrimitiveInt 步数 20
    22: (3420, 350),     # PrimitiveInt 步数 4
    23: (3420, 500),     # PrimitiveFloat denoise 0.6 标准
    24: (3420, 650),     # PrimitiveFloat denoise 0.9 加速
    29: (3420, 800),     # PrimitiveFloat cfg 3.0 标准
    30: (3420, 950),     # PrimitiveFloat cfg 1.0 加速
    20: (3730, 200),     # 4步/20步 切换
    17: (4110, 560),     # KSampler
    18: (4440, 800),     # VAEDecode
    19: (4750, 560),     # PreviewImageSave
    26: (5790, 620),     # ImageCompare
}
SIZE_OVERRIDE = {1: [460, 700]}


def build():
    with open(SRC, encoding="utf-8") as f:
        wf = json.load(f)

    nodes = {n["id"]: n for n in wf["nodes"]}

    # MD 数据表节点: 换表路径 / 字段 / 选中行 / 输出端口名
    md = nodes[1]
    md["title"] = MD_TITLE
    data = {
        "md_path": TABLE_REL,
        "fields": FIELDS,
        "selected": {"id": SEL_ID, "values": dict(SEL)},
    }
    md["widgets_values"] = [data]
    md["widgets_values_named"] = {"data": data}
    for o in md["outputs"]:
        if o["name"] == "原场景":
            o["name"] = "原图"

    for nid, title in RETITLE.items():
        nodes[nid]["title"] = title
    nodes[25]["widgets_values"] = [NOTE]

    # 布局回填
    for nid, (x, y) in POS.items():
        nodes[nid]["pos"] = [x, y]
    for nid, size in SIZE_OVERRIDE.items():
        nodes[nid]["size"] = list(size)

    # 修 0022 的连线回填缺陷: 连线 58(VAELoader→负编码)与 59(预览→负编码)
    # 没写进源节点的 outputs[].links, 前端会认不出这两条线的来处。
    links = wf["links"]
    for lid, a, ao, b, bo, _t in links:
        ls = nodes[a]["outputs"][ao].setdefault("links", [])
        if lid not in ls:
            ls.append(lid)
            ls.sort()
        nodes[b]["inputs"][bo]["link"] = lid

    return {
        "id": "00170000-0000-4000-8000-000000000017",
        "revision": 0,
        "last_node_id": wf["last_node_id"],
        "last_link_id": wf["last_link_id"],
        "nodes": sorted(wf["nodes"], key=lambda n: n["id"]),
        "links": links,
        "groups": [],
        "config": wf.get("config", {}),
        "extra": {"ds": {"scale": 0.22, "offset": [40.0, 260.0]},
                  "ue_links": [], "links_added_by_ue": []},
        "version": wf.get("version", 0.4),
    }


def check(wf):
    """布局六规范 + 连线回填自检, 返回 (错误, 提示)。"""
    err, info = [], []
    nodes = {n["id"]: n for n in wf["nodes"]}
    box = {}
    for i, n in nodes.items():
        x, y = n["pos"]
        box[i] = (x, y, x + n["size"][0], y + n["size"][1])

    # 第 1 条 左右方向: 每条连线 A → B 必须 A 右缘 ≤ B 左缘
    for lid, a, _ao, b, _bo, _t in wf["links"]:
        if box[a][2] > box[b][0]:
            err.append("[1] 连线 %d: 上游 %d(%s) 右缘 %d 越过下游 %d 左缘 %d"
                       % (lid, a, nodes[a]["type"], box[a][2], b, box[b][0]))

    # 第 2 条 端口上下顺序 —— 只提示: ComfyUI 图里「一个加载器扇出给多个不同节点」
    # 是常态(VAELoader/CLIPLoader/MD 表都会如此), 不作为拦路条件。
    def port_order(tag, owner_idx, slot_idx, other_idx):
        m = {}
        for lk in wf["links"]:
            m.setdefault(lk[owner_idx], []).append((lk[slot_idx], lk[other_idx]))
        for owner, items in m.items():
            items.sort()
            seen = []
            for slot, other in items:
                if any(slot == ps for ps, _ in seen):
                    continue          # 同一端口扇出多路, 无顺序约束
                c = (box[other][1] + box[other][3]) / 2.0
                for _ps, pother in seen:
                    if pother == other:
                        continue
                    if c <= (box[pother][1] + box[pother][3]) / 2.0:
                        info.append("[2] 节点 %d(%s) %s端口序与对侧 y 序不同向(%d / %d)"
                                    % (owner, nodes[owner]["type"], tag, pother, other))
                        break
                seen.append((slot, other))
    port_order("输入", 3, 4, 1)
    port_order("输出", 1, 2, 3)

    # 第 3 条 不重叠 + 相邻边距 50~100 + MD 独占列
    ids = sorted(nodes)
    for x in range(len(ids)):
        for y in range(x + 1, len(ids)):
            a, b = ids[x], ids[y]
            ax0, ay0, ax1, ay1 = box[a]
            bx0, by0, bx1, by1 = box[b]
            ox = min(ax1, bx1) - max(ax0, bx0)
            oy = min(ay1, by1) - max(ay0, by0)
            if ox > 0 and oy > 0:
                err.append("[3] 节点 %d(%s) 与 %d(%s) 重叠 %dx%d"
                           % (a, nodes[a]["type"], b, nodes[b]["type"], ox, oy))
            hp = oy > 0        # 纵向有投影 → 谈横向净间距
            vp = ox > 0        # 横向有投影 → 谈纵向净间距
            # 上限 <100px 只对「真正的相邻节点」有意义: 即在该方向上没有第三个节点
            # 插在两者之间, 故只统计最近的一对。
            for gap, proj, tag, mid in ((bx0 - ax1, hp, "横向", (ax0 + ax1 + bx0 + bx1) / 4.0),
                                        (by0 - ay1, vp, "纵向", (ay0 + ay1 + by0 + by1) / 4.0)):
                if not proj:
                    continue
                dist = abs(gap)
                if dist < 50:
                    err.append("[3] 节点 %d(%s) 与 %d(%s) %s净间距 %dpx < 50px"
                               % (a, nodes[a]["type"], b, nodes[b]["type"], tag, dist))
                elif dist > 100:
                    info.append("[3] 相邻 %d(%s)↔%d(%s) %s净间距 %dpx > 100px"
                                % (a, nodes[a]["type"], b, nodes[b]["type"], tag, dist))
    for m in [i for i, n in nodes.items() if n["type"] == "FallingTSMarkDownTable"]:
        mx0, my0, mx1, my1 = box[m]
        for i in ids:
            if i == m:
                continue
            ix0, iy0, ix1, iy1 = box[i]
            if ix0 >= mx0 and ix1 <= mx1:
                err.append("[3] 节点 %d(%s) 与 MD 节点 %d 同列" % (i, nodes[i]["type"], m))
            elif ix0 < mx1 and ix1 > mx0 and iy1 > my0:
                err.append("[3] 节点 %d 侵入 MD 节点 %d 所在列的垂直范围" % (i, m))

    # 连线回填一致性(两个方向都查)
    lset = dict((l[0], l) for l in wf["links"])
    for n in wf["nodes"]:
        for oi, o in enumerate(n.get("outputs", [])):
            for lid in (o.get("links") or []):
                l = lset.get(lid)
                if not l or l[1] != n["id"] or l[2] != oi:
                    err.append("[连线] 节点 %d 输出 %d 的 link %d 与 links 表不符" % (n["id"], oi, lid))
        for ii, inp in enumerate(n.get("inputs", [])):
            lid = inp.get("link")
            if lid is None:
                continue
            l = lset.get(lid)
            if not l or l[3] != n["id"] or l[4] != ii:
                err.append("[连线] 节点 %d 输入 %d 的 link %d 与 links 表不符" % (n["id"], ii, lid))

    info.append("节点 %d / 连线 %d" % (len(nodes), len(wf["links"])))
    return err, info


def main():
    wf = build()
    err, info = check(wf)
    for s in info:
        print("INFO:", s)
    if err:
        for e in err:
            print("ERROR:", e)
        sys.exit(1)
    text = json.dumps(wf, ensure_ascii=False, separators=(",", ":"))
    with open(DST, "w", encoding="utf-8") as f:
        f.write(text)
    again = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    print("OK ", os.path.relpath(DST, ROOT))
    print("幂等:", "OK" if text == again else "不一致")


if __name__ == "__main__":
    main()
