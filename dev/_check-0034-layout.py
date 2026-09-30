"""独立校验 0034_世界模型 的节点布局(不依赖生成脚本的自检), 并输出一张布局示意图。

判据(与 AGENTS.md 六条规范对应):
  0) 声明尺寸 ≥ 真实渲染下界 —— 前端载入时会按内容撑大节点, 存盘 size 只是提示;
     实测坑: PreviewImageSave 存 300x300 时真实渲染 ~760x690, 会盖住同列的下一节点
  1) 任意两节点不重叠(全局两两)
  2) 每条连线严格左→右(上游右缘 ≤ 下游左缘)
  3) 相邻节点净间距落在 (50,100)
  4) FallingTSMarkDownTable 独占一列(其所在 x 区间整条垂直方向不得有别的节点)
  5) 说明节点已压缩(宽度 ≤340, 文本 ≤700 字)
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import json
import os
import sys

WF = str(_COMFY / "workflows" / "0034_世界模型.json")
PNG = str(_COMFY / "scripts" / "_out-pano" / "0034-layout.png")
MIN_SIZE = {1: (480, 566), 2: (360, 250), 3: (510, 540), 4: (400, 200),
            5: (420, 300), 6: (3290, 2130), 15: (340, 700)}

d = json.load(open(WF, encoding="utf-8"))
nodes = {n["id"]: n for n in d["nodes"]}
box = {i: (n["pos"][0], n["pos"][1], n["pos"][0] + n["size"][0], n["pos"][1] + n["size"][1])
       for i, n in nodes.items()}
bad = []

# 0) 声明 ≥ 真实下界
for i, n in nodes.items():
    mw, mh = MIN_SIZE.get(i, (0, 0))
    if n["size"][0] < mw or n["size"][1] < mh:
        bad.append(f"#{i} 声明 {n['size']} < 下界 [{mw},{mh}]")

# 1) 全局不重叠
ids = sorted(nodes)
for k, a in enumerate(ids):
    ax0, ay0, ax1, ay1 = box[a]
    for b in ids[k + 1:]:
        bx0, by0, bx1, by1 = box[b]
        if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
            bad.append(f"重叠: #{a} 与 #{b}")

# 2) 连线左→右
for l in d["links"]:
    _, o, _, t = l[0], l[1], l[2], l[3]
    if not box[o][2] <= box[t][0]:
        bad.append(f"连线 {o}→{t}: 上游右缘 {box[o][2]} > 下游左缘 {box[t][0]}")

# 3) 相邻净间距 (50,100)
pairs = [(1, 2), (2, 3), (4, 5), (5, 6), (3, 4)]
for a, b in pairs:
    ax0, ay0, ax1, ay1 = box[a]
    bx0, by0, bx1, by1 = box[b]
    if ax1 <= bx0 and not (ay1 <= by0 or by1 <= ay0):          # 横向相邻
        g = bx0 - ax1
    elif ay1 <= by0 and not (ax1 <= bx0 or bx1 <= ax0):        # 纵向相邻
        g = by0 - ay1
    else:
        continue
    flag = "" if 50 < g < 100 else "  ← 违规"
    print(f"相邻 #{a}→#{b}: 净间距 {g}px{flag}")
    if flag:
        bad.append(f"#{a}→#{b} 净间距 {g} 不在 (50,100)")

# 4) MD 表独占一列
md = nodes[1]
mx0, mx1 = md["pos"][0], md["pos"][0] + md["size"][0]
for i, n in nodes.items():
    if i == 1:
        continue
    x0, x1 = n["pos"][0], n["pos"][0] + n["size"][0]
    if not (x1 <= mx0 or x0 >= mx1):
        bad.append(f"#{i} 与 MD 表同列")

# 5) 说明压缩
note = nodes[15]
txt = note["widgets_values"][0]
print(f"说明节点: 框 {note['size']} | 文本 {len(txt)} 字")
if note["size"][0] > 340 or len(txt) > 700:
    bad.append("说明节点未压缩")

print("\n各节点框(x0,y0..x1,y1):")
for i in ids:
    n = nodes[i]
    x0, y0, x1, y1 = box[i]
    print(f"  #{i:<3} {n['type']:<32} [{x0:>5},{y0:>4}..{x1:>5},{y1:>5}]  {n['size'][0]}x{n['size'][1]}")
print("\n布局校验:", "PASS ✔" if not bad else f"FAIL {bad}")

# ── 示意图 ────────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont
    S = 0.16
    W = int((max(b[2] for b in box.values()) + 260) * S)
    H = int((max(b[3] for b in box.values()) + 160) * S)
    img = Image.new("RGB", (W, H), (245, 246, 248))
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 12)
        small = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 10)
    except OSError:
        font = small = ImageFont.load_default()
    for i in ids:
        x0, y0, x1, y1 = [v * S for v in box[i]]
        color = (255, 236, 204) if i == 15 else (214, 232, 255)
        dr.rectangle([x0, y0, x1, y1], fill=color, outline=(60, 90, 140), width=1)
        # 标签只写在框内, 按框宽截断(窄框把标签挪到框上方, 免得压到邻居)
        name = f"#{i} {nodes[i]['type']}"
        maxc = max(4, int((x1 - x0) / 6.2))
        if x1 - x0 >= 74:
            dr.text((x0 + 3, y0 + 3), name[:maxc], fill=(20, 30, 50), font=font)
            dr.text((x0 + 3, y0 + 17), f"{nodes[i]['size'][0]}x{nodes[i]['size'][1]}",
                    fill=(90, 100, 120), font=small)
        else:
            dr.text((x0, y0 - 13), name[:maxc], fill=(20, 30, 50), font=small)
    for l in d["links"]:
        ax, ay = box[l[1]][2], (box[l[1]][1] + box[l[1]][3]) / 2
        bx, by = box[l[3]][0], (box[l[3]][1] + box[l[3]][3]) / 2
        dr.line([ax * S, ay * S, bx * S, by * S], fill=(210, 110, 80), width=1)
    img.save(PNG)
    print("示意图:", PNG, img.size)
except Exception as e:                                   # 图画不出来不影响校验结论
    print("示意图跳过:", e)

raise SystemExit(0 if not bad else 1)
