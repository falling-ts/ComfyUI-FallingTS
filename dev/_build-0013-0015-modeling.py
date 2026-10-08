# -*- coding: utf-8 -*-
"""0013_首图建模 / 0014_参考建模 / 0015_建模截帧 三件套的幂等生成器.

每个工作流复制既有模板后只改「身份 + 数据表 + 说明 + 前缀」, 不动拓扑:
  0013_首图建模 <- 0031_首帧场景 (I2VA, MiniMaxH3ImageToVideo)
  0014_参考建模 <- 0032_参考场景 (REF2VA, MiniMaxH3ReferenceToVideo)
  0015_建模截帧 <- 0035_场景截帧 (FallingTSLoadVideo 截帧 + AutoSaveImage)

0013 / 0014 另建小说数据表, 并在 stories/template 放同名空表.
"""
import json
import os

ROOT = "D:\\AI\\Comfy"
WF_DIR = os.path.join(ROOT, "workflows")
STORY = os.path.join(ROOT, "stories", "七纹刻印")
TPL = os.path.join(ROOT, "stories", "template")

def _write(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        if isinstance(obj, str):
            f.write(obj)
        else:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    print("wrote", path)
I2VA_13 = (
    "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
    "<br><br>integrated_multimodal_description: [Shot 1] "
    "本段是一段为锁定人物脸部一致性而设计的建模视频, 整部画面只出现 <Picture 1> 里这同一个人、这一套造型、这一张脸。"
    "<br>人物锁定: 二十多岁的中国男性青年, 黑色短发, 清秀干净的脸, 气质沉静内敛。黑色短发的发型、颜色、脸型、五官比例与 <Picture 1> 严格一致, 不变脸、不变年龄、不变发型。"
    "<br>镜头规则: 相机自全程固定在人物正前方、与眼高平行, 不推拉、不升降、不移动、不变焦; 全程一个连续镜头, 无剪辑、无跳切、无叠化、无淡入淡出。人物全程稳定站立不动, 只有头部与肩部随拍摄式需要作最小幅度转动。"
    "<br>参考图边界不入画: <Picture 1> 只是人物资产参考图, 它里面的分栏、黑色实线、边框、拼贴接缝、白边、标注文字与任何版面元素只存在于参考图内部, 目标视频中绝不出现分栏线、黑色实线、边框、拼贴缝、水印、字幕、字母、标注、数字与界面元素, 全程画面完全无字。"
    "<br>景别链: 视频按特写、近景、中景、全景的顺序逐段拉远, 同一张脸在四种景别下的五官比例、光阴、细节形状始终保持一致, 只有因为镜头拉远而越来越小、越来越模。"
    "<br><br>[Shot 1] 0.00-6.00 秒, 特写: 画面被头部和肩部填满, 正面朝向镜头, 双眼平视前方, 双唇闭合, 表情平静自然。颜色、肤色、发型与 <Picture 1> 逐处一致, 皮肤保留真实毛孔、下皮层散射的通透感与黑色双瞳。"
    "<br>[Shot 2] 6.00-10.00 秒, 近景: 镜头缓缓拉远, 画面中心从头部下移到上肩与肩部, 肩部与肩部的轮廓线走线, 脸部不再占满画面。"
    "<br>[Shot 3] 10.00-14.00 秒, 中景: 继续拉远, 画面中心下移到腰际, 人物上半身轮廓完整可辨, 手臂自然垂放、不挥手。"
    "<br>[Shot 4] 14.00-18.00 秒, 全景: 镜头保持正面自然站立, 人物全身完整入画并在画面中央留出完整空白边距, 头顶与脚底都不被裁掉, 软缎等功率在全景里仍然可辨。"
    "<br>[Shot 5] 18.00-20.00 秒, 回收: 镜头缓缓推回特写景别, 最终回到与开场完全一致的正脸特写构图, 作为该人物的最终锁脸参考。"
    "<br><br>overall_soundscape: 室内很静, 只有人物穿着软底鞋在地面上的极轻脚步声与一次性的空气微动, 没有对话, 没有音乐, 没有环境杂气。"
    "<br><br>non_diegestic_music: 无背景音乐。"
)

I2VA_13_TABLE = (
    "| ID          | <Picture 1>(IMAGE) | 建模提示词(TEXT) | 宽度(INT) | 高度(INT) | 视频秒数(INT) |"
    "\n| :---------- | :----------------- | :---------------------- | :------ | :------ | :-------- |"
    "\n| 00001_陈落_四景别 | @{0011_万物建模/00001_陈落} | " + I2VA_13 + " | 832 | 480 | 8 |"
    "\n"
)
NOTE_13 = (
    "## 0013_首图建模 (I2VA 8秒/24fps, 4步/20步 可切)\n"
    "\n"
    "- 模型: minimax_h3_fl2va_pruned_int8_convrot.safetensors\n"
    "- 用途: 把 0011 的人物资产图当首帧, 让 H3 在一段里串走\n"
    "  特写→近景→中景→全景→回特写, 在视频内部锁住脸部一致性。\n"
    "- 产物: media\\七纹刻印\\0013_首图建模\\, 文件名前缀取表里 ID。\n"
    "- 提示词必须否定参考图的分栏与黑色实线（reference leakage）。\n"
    "- 切换: FallingTSSwitch — True=4步 (turbo LoRA + euler + shift 6/3)\n"
    "                          False=20步 (无 LoRA + res_multistep + simple)\n"
    "- 缓存: EasyCache (0.2/0.15/0.7) 仅挂 20步分支\n"
    "- 帧数 = 秒数x24 对齐 17k+5 网格; 输出 24fps\n"
)

def build_0013():
    with open(os.path.join(WF_DIR, "0031_首帧场景.json"), encoding="utf-8") as f:
        wf = json.load(f)
    wf["id"] = "gen-0013_首图建模"
    for n in wf["nodes"]:
        if n["type"] == "FallingTSMarkDownTable":
            n["widgets_values"][0]["md_path"] = "stories/七纹刻印/0013_首图建模.md"
            n["widgets_values"][0]["fields"] = [
                {"name": "ID", "type": "STRING"},
                {"name": "<Picture 1>", "type": "IMAGE"},
                {"name": "建模提示词", "type": "TEXT"},
                {"name": "宽度", "type": "INT"},
                {"name": "高度", "type": "INT"},
                {"name": "视频秒数", "type": "INT"},
            ]
            n["widgets_values"][0]["selected"] = None
        elif n["type"] == "PreviewVideo":
            n["widgets_values"][0] = "model_video"
        elif n["type"] == "MarkdownNote":
            n["widgets_values"][0] = NOTE_13
    _write(os.path.join(WF_DIR, "0013_首图建模.json"), wf)
REF_14 = (
    "subject_definitions:\n"
    "<Subject 1> 是 <Picture 1> 里的那个人: 二十多岁的中国男性青年, 黑色短发, "
    "清秀干净的脸, 气质沉静内敛, 脸部五官结构清晰, 皮肤保留真实毛孔与黑色双瞳。<Subject 1> "
    "是全部参考资产中锁定的同一个人。\n"
    "<Subject 2> 是这个人要穿的这一身衣服: 一件宽松的纯白色圆领短袖T恤与一条灰色针织运动短裤。\n"
    "<Picture 1> 是该人的资产参考图: 左侧是他的正脸特写, 右侧是这一身衣服的参考。\n"
    "这些参考图只是身份与布料的依据: 它们自身绝不会出现在画面里, "
    "它们的分栏线、黑色实线、边框、拼贴接缝、白边与标注文字也都不出现在画面里; "
    "目标视频中完全不得出现任何文字、字幕、说明文字、水印或界面元素。\n"
    "\n"
    "summary:\n"
    "[reference generation] 目标视频是一段不拆切的单镜头: "
    "镜头固定在 <Subject 1> 正前方的平行视点上, 只做一次平缓的从特写拉远到全景的拉镜。"
    "全程 <Subject 1> 的脸、发型与 <Subject 2> 的衣服始终是同一套, "
    "随着镜头拉远只有顶点变小, 不发生身份漂移。\n"
    "\n"
    "retention_analysis:\n"
    "<Subject 1>(出现在 [Shot 1] 中): fully_preserved - 脸型、颜色、发型、年龄感、皮肤质感"
    "与穿着状态全程按 <Picture 1> 保留。\n"
    "<Subject 2>(出现在 [Shot 1] 中): fully_preserved - 衣服款式、颜色与材质全程不变。\n"
    "<Picture 1>(布局与身份参考): fully_preserved - 只用于校正人物身份与布料, "
    "图上的版面元素算作不参与复现的注释。\n"
    "\n"
    "detailed_description:\n"
    "目标视频具有实拍电影质感, 光线柔和、背景是纯白色, 深度梯度很浅、脸部始终清晰。"
    "[Shot 1] 一个连续、eye level 的单镜头从 <Subject 1> 的特写开场: "
    "正面朝向镜头, 双眼平视, 双唇闭合, 表情平静。"
    "随后镜头从特写平缓拉远到近景, 再继续拉到中景, 最后缩到全景; "
    "每一段拉镜中 <Subject 1> 的身体姿态不变, 只有颈肩关节随镜头进度可能有极小幅度变化。"
    "全程镜头只做一次平缓拉镜, 无 push in、无滚动、无升降、无沿墙、无快门。\n"
    "\n"
    "overall_soundscape:\n"
    "室内很静, 只有软底鞋踩地面的极轻声音与一次性的空气微动。\n"
    "\n"
    "non_diegetic_music:\n"
    "无背景音乐。"
)
# 表头/分隔行直接派生 0032_参考场景.md, 只把列名「场景提示词」换成「建模提示词」,
# 保证列序与管道数(22)与 REF2VA 节点端口一一对应, 绝不手写分隔行。
with open(os.path.join(STORY, "0032_参考场景.md"), encoding="utf-8") as f:
    _ref_lines = f.read().split("\n")
REF_14_HEADER = _ref_lines[0].replace("场景提示词", "建模提示词").rstrip()
REF_14_SEP = _ref_lines[1].rstrip()

# 数据行: ID + 提示词 + 9 图 + 3 视频 + 3 音频 + 宽 + 高 + 秒 = 20 列, 空单元留空字符串
def _blank_row(pic1="", pic2="", pic3=""):
    cells = ["00001_陈落_参考建模", REF_14.replace("\n", "<br>")]
    cells += [pic1, pic2, pic3] + [""] * 6          # <Picture 4..9>
    cells += [""] * 3 + [""] * 3                     # <Video 1..3> + <Audio 1..3>
    cells += ["832", "480", "8"]
    return "| " + " | ".join(cells) + " |"


# 一般情况只有一张参考图(0011 资产图); <Picture 2>/<Picture 3> 留空, 需要时再手工填帧图。
REF_14_ROW = _blank_row("@{0011_万物建模/00001_陈落}")

NOTE_14 = (
    "## 0014_参考建模 (REF2VA 8秒/24fps, 4步/20步 可切)\n"
    "\n"
    "- 模型: minimax_h3_ref2va_pruned_int8_convrot.safetensors\n"
    "- 用途: 把 0011 资产图 + 0015 截帧一起作参考, 让 H3 在多参考下\n"
    "  给出与资产一致的正面人物视频, 用作 0015 的新输入。\n"
    "- ref_image_size: max (参考图短边不超 2048, never upscaled;\n"
    "  脸必须来自高分辨率独立生成)\n"
    "- 参考图最多 9 张 (前缀 ref_image_0..8), 视频 3 条 (内部走 FallingTSVideoComponents 拆帧)。\n"
    "- 提示词必须否定参考图的分栏与黑色实线（reference leakage）。\n"
    "- 切换: FallingTSSwitch — True=4步 (稀疏注意力 + turbo LoRA)\n"
    "                          False=20步 (无 LoRA + res_multistep + simple + EasyCache)\n"
    "- 帧数 = 秒数x24 对齐 17k+5 网格; 输出 24fps\n"
)
def build_0014():
    with open(os.path.join(WF_DIR, "0032_参考场景.json"), encoding="utf-8") as f:
        wf = json.load(f)
    wf["id"] = "gen-0014_参考建模"
    for n in wf["nodes"]:
        if n["type"] == "FallingTSMarkDownTable":
            n["widgets_values"][0]["md_path"] = "stories/七纹刻印/0014_参考建模.md"
            n["widgets_values"][0]["selected"] = None
        elif n["type"] == "MiniMaxH3ReferenceToVideo":
            n["widgets_values"][4] = "max"
        elif n["type"] == "MarkdownNote":
            n["widgets_values"][0] = NOTE_14
    _write(os.path.join(WF_DIR, "0014_参考建模.json"), wf)
FRAMES = [
    ("特写",), ("近景",), ("中景",), ("全景",),
    ("侧脸",), ("半身",), ("背后",), ("回收特写",),
]

def build_0015():
    with open(os.path.join(WF_DIR, "0035_场景截帧.json"), encoding="utf-8") as f:
        wf = json.load(f)
    wf["id"] = "gen-0015_建模截帧"
    nodes = {n["id"]: n for n in wf["nodes"]}

    load = nodes[18]
    load["title"] = "建模视频 加载/截帧"
    for out in load["outputs"]:
        if out["name"].startswith("选中帧"):
            out["label"] = "选中帧 " + FRAMES[int(out["slot_index"]) - 3][0]
    load["widgets_values"] = ["", "", None, "", True, None, None, None, None, 8, {"frames": []}, ""]
    load["widgets_values_named"] = {
        "name": "", "sequence": "", "刷新序列号": None, "video": "",
        "Auto-refresh after generation": True, "refresh": None, "upload": None,
        "截帧": None, "完成": None, "输出帧数": 8,
        "frame_list": {"frames": []}, "video_fallback": "",
    }

    for nid, (label,) in zip(range(118, 126), FRAMES):
        n = nodes[nid]
        n["title"] = "单图 " + label
        n["widgets_values"] = ["", "_" + label, "png", "8-bit", "sRGB", ""]
        n["widgets_values_named"] = {
            "filename_prefix": "", "filename_suffix": "_" + label, "format": "png",
            "bit_depth": "8-bit", "input_color_space": "sRGB", "image_fallback": "",
        }

    quad = nodes[116]
    quad["title"] = "建模四图合成"
    quad["widgets_values"] = [4, 8, 6, "#000000"] + [""] * 8
    oct_ = nodes[126]
    oct_["title"] = "建模八图合成"
    oct_["widgets_values"] = [8, 8, 6, "#000000"] + [""] * 12

    nodes[117]["title"] = "建模四图合成 预览/保存"
    nodes[117]["widgets_values"] = ["", "_四图", "png", "8-bit", "sRGB", ""]
    nodes[117]["widgets_values_named"] = {
        "filename_prefix": "", "filename_suffix": "_四图", "format": "png",
        "bit_depth": "8-bit", "input_color_space": "sRGB", "image_fallback": "",
    }
    nodes[127]["title"] = "建模八图合成 预览/保存"
    nodes[127]["widgets_values"] = ["", "_八图", "png", "8-bit", "sRGB", ""]
    nodes[127]["widgets_values_named"] = {
        "filename_prefix": "", "filename_suffix": "_八图", "format": "png",
        "bit_depth": "8-bit", "input_color_space": "sRGB", "image_fallback": "",
    }

    wf["groups"] = []
    _write(os.path.join(WF_DIR, "0015_建模截帧.json"), wf)
def write_tables():
    _write(os.path.join(STORY, "0013_首图建模.md"), I2VA_13_TABLE)
    _write(os.path.join(TPL, "0013_首图建模.md"), "\n".join(I2VA_13_TABLE.split("\n")[:2]) + "\n")
    body = REF_14_HEADER + "\n" + REF_14_SEP + "\n" + REF_14_ROW + "\n"
    _write(os.path.join(STORY, "0014_参考建模.md"), body)
    _write(os.path.join(TPL, "0014_参考建模.md"), REF_14_HEADER + "\n" + REF_14_SEP + "\n")


def verify():
    ok = True
    for name, base in (("0013_首图建模", "0031_首帧场景"), ("0014_参考建模", "0032_参考场景"), ("0015_建模截帧", "0035_场景截帧")):
        with open(os.path.join(WF_DIR, name + ".json"), encoding="utf-8") as f:
            wf = json.load(f)
        pos = {n["id"]: n["pos"][0] for n in wf["nodes"]}
        size = {n["id"]: (n["size"][0] if n.get("size") else 0) for n in wf["nodes"]}
        bad = []
        for link in wf["links"]:
            src, dst = link[1], link[3]
            if src not in pos or dst not in pos:
                continue
            if pos[src] + size[src] > pos[dst]:
                bad.append("%s->%s" % (src, dst))
        with open(os.path.join(WF_DIR, base + ".json"), encoding="utf-8") as f:
            bwf = json.load(f)
        bpos = {n["id"]: n["pos"][0] for n in bwf["nodes"]}
        bsize = {n["id"]: (n["size"][0] if n.get("size") else 0) for n in bwf["nodes"]}
        bbad = sorted("%s->%s" % (l[1], l[3]) for l in bwf["links"]
                      if bpos.get(l[1]) is not None and bpos.get(l[3]) is not None
                      and bpos[l[1]] + bsize[l[1]] > bpos[l[3]])
        same = sorted(bad) == bbad
        print("[%s] nodes=%d links=%d 同模板基线=%s (本表 %d 条/基线 %d 条)" % (name, len(wf["nodes"]), len(wf["links"]), same, len(bad), len(bbad)))
        ok = ok and same
    for p, pipes in ((os.path.join(STORY, "0013_首图建模.md"), 8),
                     (os.path.join(STORY, "0014_参考建模.md"), 22),
                     (os.path.join(TPL, "0013_首图建模.md"), 8),
                     (os.path.join(TPL, "0014_参考建模.md"), 22)):
        with open(p, encoding="utf-8") as f:
            lines = f.read().split("\n")
        got = [len(l.split("|")) for l in lines if l.strip()]
        print("[%s] 行=%d 管道=%s 期望=%d" % (os.path.basename(p), len(lines), got, pipes))
        ok = ok and all(g == pipes for g in got)
    print("VERIFY", "OK" if ok else "FAIL")


if __name__ == "__main__":
    build_0013()
    build_0014()
    build_0015()
    write_tables()
    verify()