"""重建 0034_世界模型 工作流: 输入改为「一条 360° 环绕视频」→ 全景长图 → 带精确位姿的视角 → 精修 PLY。

节点:
  #1  FallingTSMarkDownTable    md 表(360环绕视频 列) → VIDEO
  #2  WorldSurroundPanorama     视频 → 等距圆柱长图 (unfold/equirect) + valid_band
  #3  PreviewImageSave          长图预览/保存支路 (与 #4 同列, 二者是兄弟)
  #4  WorldPanoramaViews        长图 → 视角批 + EXTRINSICS/INTRINSICS (v_range = valid_band)
  #5  WorldRefinePLY            视角批 + 位姿先验 → 504 前馈 + 3DGS 精修 → 一个 PLY
  #6  HYWM2PLYAdvancedGaussianViewer
布局遵守六条规范 (左右严格推进 / 端口上下顺序 / 间隙 50~100px / MD 表独占一列)。

用法: python custom_nodes/ComfyUI-FallingTS/dev/_build-0034-world360.py [--dry]
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import json
import sys

SRC = str(_COMFY / "workflows" / "0034_世界模型.json")
OUT = SRC
MD = str(_COMFY / "stories" / "七纹刻印" / "0034_世界模型.md")

DRY = "--dry" in sys.argv
old = json.load(open(SRC, encoding="utf-8"))
old_nodes = {n["id"]: n for n in old["nodes"]}


def find_node(nid, typ):
    """幂等: 老工作流的 id 找不到时按类型找当前节点(重复跑本脚本不会 KeyError)。"""
    if nid in old_nodes:
        return old_nodes[nid]
    for n in old["nodes"]:
        if n["type"] == typ:
            return n
    raise SystemExit(f"重建失败: 既没有 id={nid} 也没有 type={typ} 的节点")

SCENE = ("一处平面轮廓近似正方形的紧凑家庭书房，约十平方米，四面墙长度相近且两两以直角相接，"
         "深蓝灰色墙面、浅色木质地板，四面墙脚一圈深棕色踢脚线；前面墙偏左是一扇黑框大窗，"
         "窗外是夜雨中亮着灯的高楼城市，窗左端垂一幅深色窗帘，窗前偏左一张深色木书桌，桌面上"
         "一盏黑罩暖光台灯、一个笔筒、一台亮着冷白文档的银色笔记本电脑与一小摞立着的书，桌前"
         "一把黑色转椅，转椅左前方地板上铺一块浅灰色小地毯；左墙靠前段挂一块浅木色边框黑板、"
         "黑板下深色木矮几上放两盆盆栽与一小摞书，左墙靠后段墙脚放一盆白盆绿植；右墙靠前段一只"
         "深红棕色木质抽屉柜、柜顶一盆白盆绿植，右墙靠后段墙脚一座木质矮书架、层板上十几本书；"
         "后墙中部偏右一扇关着的深色木门，门框右侧墙面一个白色开关面板，门左侧墙脚一只矮边柜、"
         "柜面一小摞书，门右侧墙面一只圆形白色挂钟；本行唯一输入是一条以房间中央为圆心、视线保持"
         "水平、顺时针转满一整圈的旋镜视频，视频里所有画面出自同一次连续拍摄，不存在多张图之间"
         "的位姿/内容不一致；重建时由工作流先把这条 360° 视频展开成一张等距圆柱全景长图，再按解析"
         "解位姿切成互相重叠的透视视角，一次送入多视角重建。")

NOTE = """## 0034_世界模型 · 360° 视频 → 一个最高质量 3DGS PLY

输入 = md 表(节点 1)的 `360环绕视频` 列；改表 → 点「刷新」→ Run。细节见
`docs\\360视频横向展开长图-v2实现-2026-09-28.md`。

**链路**：表 → `WorldSurroundPanorama`(视频 → 横向展开长图：等距圆柱条带、上行=天、无黑边、无重影，
另出 `valid_band`/`v_center`) → `PreviewImageSave`(目视) ＋ `WorldPanoramaViews`(长图 → 重叠视角批
＋ 每视角解析 w2c 外参/内参) → `WorldRefinePLY`(＋相机先验 → 504 前馈 → 3DGS 全参数精修 1500 步)
→ PLY 视口。产物 `output\\0034_世界模型\\0034_世界模型_世界3DGS.ply`。

**必接**：`valid_band→v_range`、`v_center→v_center`(否则切出黑边视角)；视角 72°/重叠 10% ⇒ 6 视角；
`target`/`gt`=952、`reg`=3.0。

**四个坑**：① 重影根源是上游自猜位姿 —— 本链把解析位姿当先验注入(`cond_flags=[cam,0,intr]`)；
② 子进程 stdout 钉 UTF-8(否则中文路径乱码)；③ `f_dc_*` 落盘写原始 `sh[:,0]`(否则颜色做两遍变中灰)；
④ 验收看 `/history` 的 `status_str`，不看退出码。
"""


def widget_inputs(pairs):
    """[(name, type, localized)] → ComfyUI 序列化的 widget 型输入槽。"""
    return [{"localized_name": loc, "name": name, "type": typ,
             "widget": {"name": name}, "link": None} for name, typ, loc in pairs]


def link_input(name, typ, link_id, loc=None, optional=False):
    d = {"localized_name": loc or name, "name": name, "type": typ, "link": link_id}
    if optional:
        d["shape"] = 7
    return d


nodes = []

# ── #1 md 数据表 ──────────────────────────────────────────────
old_md = old_nodes[1]
nodes.append({
    "id": 1, "type": "FallingTSMarkDownTable", "pos": [420, 40], "size": [480, 1010],
    "flags": {}, "order": 0, "mode": 0,
    "inputs": [{"localized_name": "data", "name": "data", "type": "FALLINGTS_MD_TABLE",
                "widget": {"name": "data"}, "link": None}],
    "outputs": [
        {"name": "ID", "type": "STRING", "slot_index": 0, "links": []},
        {"name": "场景描述", "type": "STRING", "slot_index": 1, "links": []},
        {"name": "360环绕视频", "type": "VIDEO", "slot_index": 2, "links": [1]},
        {"name": "整行数据", "type": "STRING", "slot_index": 3, "links": []},
    ],
    "properties": old_md["properties"],
    "widgets_values": [{
        "md_path": MD,
        "fields": [{"name": "ID", "type": "STRING"},
                   {"name": "场景描述", "type": "TEXT"},
                   {"name": "360环绕视频", "type": "VIDEO"}],
        "selected": {"id": "00001_书房",
                     "values": {"ID": "00001_书房", "场景描述": SCENE,
                                "360环绕视频": "@{0031_首帧场景/00001_书房旋镜视频}"}},
    }],
    "widgets_values_named": {
        "md_path": MD,
        "fields": [{"name": "ID", "type": "STRING"},
                   {"name": "场景描述", "type": "TEXT"},
                   {"name": "360环绕视频", "type": "VIDEO"}],
        "selected": {"id": "00001_书房",
                     "values": {"ID": "00001_书房", "场景描述": SCENE,
                                "360环绕视频": "@{0031_首帧场景/00001_书房旋镜视频}"}},
    },
})

# ── #2 视频 → 长图 ────────────────────────────────────────────
nodes.append({
    "id": 2, "type": "WorldSurroundPanorama", "pos": [980, 40], "size": [360, 340],
    "flags": {}, "order": 1, "mode": 0,
    "inputs": [
        link_input("video", "VIDEO", 1, "360 环绕视频", optional=True),
        link_input("images", "IMAGE", None, "帧序列(备用)", optional=True),
    ] + widget_inputs([("mode", "COMBO", "展开模式"), ("frame_index", "INT", "抽帧序号"),
                       ("max_frames", "INT", "最大抽帧数"), ("target_shift_percent", "FLOAT", "帧间位移%"),
                       ("h_fov", "FLOAT", "水平FOV(0=自动)"), ("out_width", "INT", "长图宽度(0=自动)"),
                       ("supersample", "FLOAT", "超采样倍率"), ("seam_feather", "INT", "接缝羽化px")]),
    "outputs": [
        {"name": "panorama", "type": "IMAGE", "slot_index": 0, "links": [2, 3]},
        {"name": "valid_band", "type": "FLOAT", "slot_index": 1, "links": [4]},
        {"name": "v_center", "type": "FLOAT", "slot_index": 2, "links": [9]},
        {"name": "report", "type": "STRING", "slot_index": 3, "links": []},
    ],
    "properties": {"Node name for S&R": "WorldSurroundPanorama",
                   "ue_properties": {"widget_ue_connectable": {}, "version": "7.8",
                                     "input_ue_unconnectable": {}}},
    "widgets_values": ["auto", -1, 240, 12.0, 0.0, 0, 1.5, 7],
    "widgets_values_named": {"mode": "auto", "frame_index": -1, "max_frames": 240,
                             "target_shift_percent": 12, "h_fov": 0, "out_width": 0,
                             "supersample": 1.5, "seam_feather": 7},
})

# ── #3 长图预览支路 ───────────────────────────────────────────
nodes.append({
    "id": 3, "type": "PreviewImageSave", "pos": [1420, 40], "size": [620, 600],
    "flags": {}, "order": 3, "mode": 0,
    "inputs": [
        link_input("images", "IMAGE", 2, "panorama"),
    ] + widget_inputs([("filename_prefix", "STRING", ""), ("filename_suffix", "STRING", ""),
                       ("format", "COMBO", ""), ("bit_depth", "COMBO", ""),
                       ("input_color_space", "COMBO", "")]),
    "outputs": [{"localized_name": "images", "name": "images", "type": "IMAGE",
                 "slot_index": 0, "links": []}],
    "properties": {"Node name for S&R": "PreviewImageSave",
                   "ue_properties": {"widget_ue_connectable": {}, "version": "7.8",
                                     "input_ue_unconnectable": {}}},
    "widgets_values": ["0034_世界模型_360长图", "", "png", "8-bit", "sRGB", None, ""],
    "widgets_values_named": {"filename_prefix": "0034_世界模型_360长图", "filename_suffix": "",
                             "format": "png", "bit_depth": "8-bit", "input_color_space": "sRGB",
                             "保存": None, "image_fallback": ""},
})

# ── #4 长图 → 视角 + 位姿 ─────────────────────────────────────
nodes.append({
    "id": 4, "type": "WorldPanoramaViews", "pos": [1420, 700], "size": [400, 280],
    "flags": {}, "order": 2, "mode": 0,
    "inputs": [
        link_input("panorama", "IMAGE", 3, "panorama"),
    ] + widget_inputs([("fov_degrees", "FLOAT", "视场角"), ("overlap_percent", "FLOAT", "重叠%"),
                       ("output_size", "INT", "视角边长"), ("v_range", "FLOAT", "竖向跨度(接valid_band)"),
                       ("v_center", "FLOAT", "竖向中心")]),
    "outputs": [
        {"name": "images", "type": "IMAGE", "slot_index": 0, "links": [5]},
        {"name": "extrinsics", "type": "EXTRINSICS", "slot_index": 1, "links": [6]},
        {"name": "intrinsics", "type": "INTRINSICS", "slot_index": 2, "links": [7]},
        {"name": "num_horizontal", "type": "INT", "slot_index": 3, "links": []},
        {"name": "num_vertical", "type": "INT", "slot_index": 4, "links": []},
    ],
    "properties": {"Node name for S&R": "WorldPanoramaViews",
                   "ue_properties": {"widget_ue_connectable": {}, "version": "7.8",
                                     "input_ue_unconnectable": {}}},
    "widgets_values": [72.0, 10.0, 952, 70.0, 0.0],
    "widgets_values_named": {"fov_degrees": 72, "overlap_percent": 10, "output_size": 952,
                             "v_range": 70, "v_center": 0},
})
# v_range / v_center 由 #2 的长图元信息链接驱动(接上后前端显示为连线端口)
nodes[-1]["inputs"][4]["link"] = 4      # v_range  ← valid_band
nodes[-1]["inputs"][5]["link"] = 9      # v_center ← v_center

# ── #5 重建 + 精修 (带相机先验) ───────────────────────────────
old_ref = find_node(20, "WorldRefinePLY")
nodes.append({
    "id": 5, "type": "WorldRefinePLY", "pos": [1910, 700], "size": [420, 400],
    "flags": {}, "order": 4, "mode": 0, "title": "世界重建精修 PLY (接相机先验)",
    "inputs": [
        link_input("images", "IMAGE", 5, "视角批"),
    ] + widget_inputs([("steps", "INT", "精修步数"), ("mode", "COMBO", "精修模式"),
                       ("reg", "FLOAT", "几何信任域"), ("reg_opac", "FLOAT", "透明度信任域"),
                       ("reg_color", "FLOAT", "颜色信任域"), ("target", "INT", "前馈长边"),
                       ("gt", "INT", "颜色监督长边"), ("prune_opac", "FLOAT", "剪枝阈值"),
                       ("refresh", "BOOLEAN", "重算前馈")]) + [
        link_input("extrinsics", "EXTRINSICS", 6, "相机先验(w2c)", optional=True),
        link_input("intrinsics", "INTRINSICS", 7, "相机内参", optional=True),
    ],
    "outputs": [{"name": "ply_path", "type": "STRING", "slot_index": 0, "links": [8]}],
    "properties": old_ref["properties"],
    "widgets_values": [1500, "all", 3, 0.5, 0.5, 952, 952, 0, False],
    "widgets_values_named": {"steps": 1500, "mode": "all", "reg": 3, "reg_opac": 0.5,
                             "reg_color": 0.5, "target": 952, "gt": 952, "prune_opac": 0,
                             "refresh": False},
})

# ── #6 PLY 视口 ───────────────────────────────────────────────
viewer = dict(find_node(19, "HYWM2PLYAdvancedGaussianViewer"))
viewer["id"] = 6
viewer["pos"] = [2410, 700]
viewer["order"] = 5
viewer["inputs"] = [link_input("ply_path", "STRING", 8, "ply_path")]
nodes.append(viewer)

# ── #15 说明 ──────────────────────────────────────────────────
note = dict(find_node(15, "MarkdownNote"))
note["pos"] = [0, 40]
note["size"] = [340, 980]
note["widgets_values"] = [NOTE]
note["widgets_values_named"] = [NOTE]
nodes.append(note)

links = [
    [1, 1, 2, 2, 0, "VIDEO"],
    [2, 2, 0, 3, 0, "IMAGE"],
    [3, 2, 0, 4, 0, "IMAGE"],
    [4, 2, 1, 4, 4, "FLOAT"],
    [5, 4, 0, 5, 0, "IMAGE"],
    [6, 4, 1, 5, 10, "EXTRINSICS"],
    [7, 4, 2, 5, 11, "INTRINSICS"],
    [8, 5, 0, 6, 0, "STRING"],
    [9, 2, 2, 4, 5, "FLOAT"],
]

wf = {
    "id": "0034-world-model",
    "revision": 0,
    "last_node_id": 15,
    "last_link_id": 9,
    "nodes": nodes,
    "links": links,
    "groups": [],
    "config": old.get("config", {}),
    "extra": old.get("extra", {}),
    "version": old.get("version", 0.4),
}

# ── 自检: 六条布局规范里可机检的几条 ──────────────────────────
def edges(n):
    x, y = n["pos"]
    return x, y, x + n["size"][0], y + n["size"][1]

by_id = {n["id"]: n for n in nodes}
problems = []

# ── 0) 声明尺寸必须是"真实渲染尺寸的上界", 否则画布上会长出声明框去压别人 ──────
# ComfyUI 前端载入时会按内容把节点撑大(存盘的 size 只是提示), 实测踩坑: PreviewImageSave
# 存 300x300 时真实渲染 ~760x690, 直接把同列的 #4 盖住。行数口径取自 /object_info(2026-09-28):
#   WorldSurroundPanorama 10 输入/4 输出, WorldPanoramaViews 6/5, WorldRefinePLY 12/1,
#   FallingTSMarkDownTable 1/42, PreviewImageSave 6/1(另有图像预览区), 视口 3290x2130(前端实测)。
MIN_SIZE = {1: (480, 1010), 2: (360, 300), 3: (620, 600), 4: (400, 260),
            5: (420, 360), 6: (3290, 2130), 15: (340, 700)}
for n in nodes:
    mw, mh = MIN_SIZE.get(n["id"], (0, 0))
    if n["size"][0] < mw or n["size"][1] < mh:
        problems.append(f"#{n['id']} 声明 {n['size']} 小于真实下界 [{mw},{mh}] (会被前端撑大 ⇒ 视觉重叠)")

# ── 1) 任意两节点不得重叠(全局两两检查) ──────────────────────────
for i, a in enumerate(nodes):
    ax0, ay0, ax1, ay1 = edges(a)
    for b in nodes[i + 1:]:
        bx0, by0, bx1, by1 = edges(b)
        if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
            problems.append(f"节点重叠: #{a['id']} [{ax0},{ay0}..{ax1},{ay1}] ∩ "
                            f"#{b['id']} [{bx0},{by0}..{bx1},{by1}]")

# ── 2) 连线严格左→右 ──────────────────────────────────────────
for l in links:
    o, t = by_id[l[1]], by_id[l[3]]
    ox0, oy0, ox1, oy1 = edges(o)
    tx0, ty0, tx1, ty1 = edges(t)
    if not ox1 <= tx0:
        problems.append(f"连线 {l[1]}:{l[3]} 上游右缘 {ox1} > 下游左缘 {tx0} (必须严格左→右)")
# 同列兄弟的纵向净间距
sib = sorted([by_id[3], by_id[4]], key=lambda n: n["pos"][1])
gap = sib[1]["pos"][1] - (sib[0]["pos"][1] + sib[0]["size"][1])
if not 50 < gap < 100:
    problems.append(f"同列兄弟 #3/#4 纵向净间距 {gap} 不在 (50,100)")
# 横向链上的净间距
order = [by_id[i] for i in (1, 2, 4, 5, 6)]
for a, b in zip(order, order[1:]):
    if a["pos"][1] == b["pos"][1] or b["id"] in (4, 5, 6):
        g = b["pos"][0] - (a["pos"][0] + a["size"][0])
        if not 50 < g < 100:
            problems.append(f"#{a['id']}→#{b['id']} 横向净间距 {g} 不在 (50,100)")
# 预览支路 #2 → #3 的横向净间距(不在主链上, 单独查)
g23 = by_id[3]["pos"][0] - (by_id[2]["pos"][0] + by_id[2]["size"][0])
if not 50 < g23 < 100:
    problems.append(f"#2→#3 横向净间距 {g23} 不在 (50,100)")
# MD 表独占一列
md_x0, md_x1 = by_id[1]["pos"][0], by_id[1]["pos"][0] + by_id[1]["size"][0]
for n in nodes:
    if n["id"] == 1:
        continue
    x0, x1 = n["pos"][0], n["pos"][0] + n["size"][0]
    if not (x1 <= md_x0 or x0 >= md_x1):
        problems.append(f"#{n['id']} 与 MD 表同列 (x {x0}..{x1} 与 {md_x0}..{md_x1} 重叠)")

# 说明节点必须"压缩": 文本长度与声明尺寸都要收住(前端 MarkdownNote 高 ≈ 文本行数 × 22)
if by_id[15]["size"][0] > 340:
    problems.append(f"说明节点宽度 {by_id[15]['size'][0]} > 340 (会挤进 MD 表那一列)")
if not 700 <= by_id[15]["size"][1] <= 1050:
    problems.append(f"说明节点高度 {by_id[15]['size'][1]} 超出压缩目标 700~1050")
if len(NOTE) > 700:
    problems.append(f"说明文本 {len(NOTE)} 字, 超过压缩目标 700 字")

print("节点:", [(n["id"], n["type"]) for n in nodes])
print("说明文本:", len(NOTE), "字 | 说明框:", by_id[15]["size"])
print("连线:", len(links))
print("布局自检:", "全部通过 ✔" if not problems else problems)
if DRY:
    raise SystemExit(0)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, separators=(",", ":"))
print("已写入:", OUT)