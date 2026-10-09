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
    "<br><br>integrated_multimodal_description: 这是一段为锁定人物身份而设计的建模视频, 整部画面只出现 <Picture 1> 里这同一个人、这一张脸、这一套造型。"
    "<br>人物锁定: 二十多岁的中国男性青年, 黑色短发、发丝蓬松自然、刘海细碎垂落在额前, 清瘦的脸型与清晰的下颌线, 眉形平直, 双眼细长、上眼睑略垂, 鼻梁高挺, 双唇偏薄, 气质沉静内敛。脸型、五官比例、发型与肤色自始至终与 <Picture 1> 严格一致, 不变脸、不变年龄、不变发型。"
    "<br>身体与着装(严格照抄 <Picture 1> 三视图里这一身衣着与体型, 本段只是复述并要求全程保持不变, 不得另起一套): 身高约一米七五, 真人解剖比例, 肩宽腰窄、四肢长度符合真实人体结构, 体态匀称偏瘦。"
    "上身是一件宽松的纯白色圆领短袖T恤, 棉质面料, 领口、袖口与下摆自然, 版型宽松落肩, 衣服上没有任何图案与文字。"
    "下身是一条灰色针织运动短裤, 柔软针织面料的织纹与绒感可辨, 腰头与裤脚边缘干净。"
    "脚上是一双低调的浅色夹脚拖鞋, 一字宽带横跨脚背、鞋面大面积镂空只由这一条带子固定、鞋头圆润开放、鞋帮低矮、鞋底是平整的软质橡胶底。这身衣着全程不变, 不换装、不变形、不增减任何衣物。"
    "<br>镜头规则: [Shot 1] 相机从特写缓缓拉远到人物正面全身站立; 从 [Shot 2] 起相机完全固定在人物正前方、与眼高平行, 不推拉、不升降、不移动、不变焦。全程一个连续镜头, 无剪辑、无跳切、无叠化、无淡入淡出。"
    "人物双脚并拢、与肩同宽, 双手自然垂在身侧, 全程稳定站立、不移动脚步、不挥手, 只有头部与肩部有极小幅度的自然变化。"
    "<br>旋转规则: [Shot 2] 起, 人物自己站在原地以垂直轴为轴心匀速逆时针转过一整整圈, 共转满三百六十度。"
    "转动方向以正上方俯视为准: 从俯视看是逆时针, 也就是人物先转向画面左边, 他的右侧一点一点转到画面背面去, 他的左侧一点一点从画面左边转出来。"
    "每段各转四十五度, [Shot 2] 到 [Shot 9] 共八段, 合计三百六十度, 转完刚好回到正面。"
    "转动的过程中脸部五官、发型、身体比例与这身衣着全程不变形, 只有水平方向的朝向在改变, 不出现拉伸、扭曲、拖影与残影。"
    "<br>环境与背景: 全程是纯净的纯白色背景, 无地面景物、无环境、无道具、无文字, 柔和均匀的影棚布光, 人物不向背景投射阴影, 旋转全程没有投影的移动与变化。"
    "<br>参考图边界不入画: <Picture 1> 是这个人的三视图资产图(横向并排左正、中侧、右后三个视角), 它自身绝不会出现在画面里, 目标视频中完全不得出现它的白边、边框、拼贴缝、水印、字幕、字母、标注、数字与任何界面元素, 更不得并排出现多个视角或多个身影: 全程画面里始终只有一个完整人物, 全程画面完全无字。"
    "<br><br>[Shot 1] 0.00-3.00 秒, 拉镜: 起幅是 <Picture 1> 中那个人的正面全身像(左边那个正面视角), 头部与肩部填满画面、正面朝向镜头、双眼平视前方、双唇闭合、表情平静自然。"
    "相机缓缓向后拉远并同步下移, 画面中心从头部一路下移到胸腹之间, 最终人物正面笔直站立、头顶到脚底的全身完整入画并居于画面正中, 四周留出完整空白边距, 头顶与浅色夹脚拖鞋都不被裁掉。"
    "拉镜过程中肤色、发型与五官比例与 <Picture 1> 逐处一致, 皮肤保留真实毛孔、次表面散射的通透感与黑色双瞳; 白色T恤、灰色针织短裤与浅色夹脚拖鞋的带子结构、鞋底与颜色依次清晰可辨。"
    "<br>[Shot 2] 3.00-4.50 秒, 四十五度: 人物由正面开始原地逆时针转过四十五度, 画面转到他的右前方侧身。"
    "<br>[Shot 3] 4.50-6.00 秒, 九十度: 继续逆时针, 画面转到他的正右侧侧面。"
    "<br>[Shot 4] 6.00-7.50 秒, 一百三十五度: 继续逆时针, 越过侧面转入他的右后方。"
    "<br>[Shot 5] 7.50-9.00 秒, 一百八十度: 继续逆时针, 画面正好是他的正背面, 背部正面朝向镜头。"
    "<br>[Shot 6] 9.00-10.50 秒, 二百二十五度: 继续逆时针, 画面转到他的左后方。"
    "<br>[Shot 7] 10.50-12.00 秒, 二百七十度: 继续逆时针, 画面转到他的正左侧侧面。"
    "<br>[Shot 8] 12.00-13.50 秒, 三百一十五度: 继续逆时针, 越过侧面转入他的左前方。"
    "<br>[Shot 9] 13.50-15.00 秒, 三百六十度: 继续逆时针转完最后一小段, 人物转回正面笔直站立, 与 [Shot 1] 拉镜结束时的构图完全一致, 作为该人物的最终锁脸参考。"
    "<br><br>overall_soundscape: 室内很静, 只有人物穿着拖鞋在地面上的极轻脚步声与一次性的空气微动, 没有对话, 没有音乐, 没有环境杂声。"
    "<br><br>non_diegestic_music: 无背景音乐。"
)
I2VA_13_TABLE = (
    "| ID          | <Picture 1>(IMAGE) | 建模提示词(TEXT) | 宽度(INT) | 高度(INT) | 视频秒数(INT) |"
    "\n| :---------- | :----------------- | :---------------------- | :------ | :------ | :-------- |"
    "\n| 00001_陈落 | @{0011_万物建模/00001_陈落} | " + I2VA_13 + " | 832 | 480 | 15 |"
    "\n"
)
NOTE_13 = (
    "## 0013_首图建模 (I2VA, 24fps, 4步/20步 可切)\n"
    "\n"
    "- 模型: minimax_h3_fl2va_pruned_int8_convrot.safetensors\n"
    "- 用途: 把 0011 的人物三视图(左正/中侧/右后)当首帧参考, 让 H3 原地逆时针转满一整圈, 锁住身份一致性。\n"    "- ⚠️ 0011 人物行已改回三视图(2026-10-07): 参考图自带并排的三个视角与拼版结构, H3 复刻白边/边框/\n"    "  并排多身影的风险显著更高, 提示词必须显式否定版面元素, 并写明「全程画面里始终只有一个完整人物」。\n"    "- 服装与体型以 0011 三视图为准, 本表提示词只做复述, 不要另起一套(两处打架会让视频里的衣服对不上三视图)。\n"
    "- 产物: media\\七纹刻印\\0013_首图建模\\, 文件名前缀取表里 ID。\n"
    "- 提示词先看首图再写: 首图是三视图 → 15 秒, [Shot 1] 3 秒拉镜(正面半身→正面全身站立),\n"
    "  [Shot 2]~[Shot 9] 共 8 段各 1.5 秒, 每段逆时针 45 度, 合计 360 度。\n"
    "  若换一张本身就是全身的首图, 改成 12 秒, [Shot 1]~[Shot 8] 共 8 段各 1.5 秒、\n"
    "  段段都是 45 度, 没有拉镜段。\n"
    "- 旋转方向: 以正上方俯视为准的逆时针; 人物的右侧转到画面背面, 左侧从画面左边转出来。\n"
    "- 提示词必须否定参考图的白边/边框/拼贴缝等 reference leakage。\n"
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
    "是全部参考资产中锁定的同一个人, 在 [Shot 1] 到 [Shot 9] 的全程都是这同一个人。\n"
    "<Subject 2> 是这个人要穿的这一身衣服: 一件宽松的纯白色圆领短袖T恤与一条灰色针织运动短裤, "
    "全程不变。\n"
    "<Picture 1> 是这个人的三视图身份参考图: 画面里从左到右并排三个视角, 左边是正面、中间是侧面、右边是后面, 三个视角是同一个人、同一套衣着, 造型与尺寸完全一致。\n"
    "这些参考图只是身份与布料的依据: 它们自身绝不会出现在画面里, "
    "它的白边、边框、拼贴接缝与标注文字也都不出现在画面里; "
    "目标视频中完全不得出现任何文字、字幕、说明文字、水印或界面元素。\n"
    "\n"
    "summary:\n"
    "[reference generation] 目标视频是一段不拆切的单镜头, 完整走 [Shot 1] 到 [Shot 9] 共九个连续段落, "
    "没有任何剪切: [Shot 1] 里镜头从 <Subject 1> 的正面特写平缓拉远到他的正面全身站立; "
    "[Shot 2] 起镜头完全固定不动, 由 <Subject 1> 自己站在原地匀速转过一整圈, "
    "转动方向以垂直俯视为准是逆时针, 也就是他的右肩背逐渐转向画面深处、"
    "左肩逐渐转向镜头, 到 [Shot 9] 末尾正好转回正面, 与 [Shot 1] 结束时的姿态一致。"
    "全程 <Subject 1> 的脸、发型与 <Subject 2> 的衣服始终是同一套, 变的只有身体朝向, "
    "不发生身份漂移, 背景也始终是同一片纯白。\n"
    "\n"
    "retention_analysis:\n"
    "<Subject 1>(出现在 [Shot 1] 到 [Shot 9] 全程): fully_preserved - 脸型、颜色、发型、年龄感、"
    "皮肤质感、身体比例与穿着状态全程按 <Picture 1> 保留, 只允许整体朝向随转体变化。\n"
    "<Subject 2>(出现在 [Shot 1] 到 [Shot 9] 全程): fully_preserved - 衣服款式、颜色与材质全程不变, "
    "下摆与袖口只随转动做轻微的自然甩动。\n"
    "<Picture 1>(布局与身份参考): fully_preserved - 只用于校正人物身份与布料, "
    "图上的版面元素算作不参与复现的注释。\n"
    "\n"
    "detailed_description:\n"
    "目标视频具有实拍电影质感, 光线柔和均匀、背景是纯白色、深度梯度很浅, 脸部在任何朝向都清晰。"
    "全片只使用一个 eye level 的固定视点, 不切镜头、不换机位、不推拉摇移。"
    "[Shot 1] 从 0.00 秒到 3.00 秒: 连续单镜头从 <Subject 1> 的正面特写开场, "
    "他正面朝向镜头、双眼平视、双唇闭合、表情平静。"
    "镜头持续平缓地向后拉远, 景别依次经过特写、近景、中景, 到本段末尾落到全身, "
    "此时 <Subject 1> 完整入画、正面笔直站立、双脚与肩同宽、双手自然垂在身侧, "
    "人物高度约占画面的七成, 脚下与背景都是同一种纯白。"
    "[Shot 2] 从 3.00 秒到 4.50 秒: 镜头在这里停住并从此固定不动。"
    "<Subject 1> 保持原地站立不动, 从正面开始以俯视逆时针方向匀速转过 45 度, "
    "右肩背逐渐转向画面深处、左肩逐渐转向镜头; 本段末尾是正面偏左的四分之三侧面。"
    "[Shot 3] 从 4.50 秒到 6.00 秒: 转速保持不变, 再逆时针转过 45 度, 累计 90 度, "
    "本段末尾是 <Subject 1> 的正左侧全侧身, 左肩正对镜头、脸转成侧脸。"
    "[Shot 4] 从 6.00 秒到 7.50 秒: 继续同样转速再转 45 度, 累计 135 度, "
    "本段末尾是左后方的四分之三背面。"
    "[Shot 5] 从 7.50 秒到 9.00 秒: 继续再转 45 度, 累计 180 度, "
    "本段末尾 <Subject 1> 完全背对镜头。"
    "[Shot 6] 从 9.00 秒到 10.50 秒: 继续再转 45 度, 累计 225 度, "
    "本段末尾是右后方的四分之三背面。"
    "[Shot 7] 从 10.50 秒到 12.00 秒: 继续再转 45 度, 累计 270 度, "
    "本段末尾是 <Subject 1> 的正右侧全侧身, 右肩正对镜头、脸转成侧脸。"
    "[Shot 8] 从 12.00 秒到 13.50 秒: 继续再转 45 度, 累计 315 度, "
    "本段末尾是右前方的四分之三正面。"
    "[Shot 9] 从 13.50 秒到 15.00 秒: 继续再转 45 度, 累计 360 度, "
    "<Subject 1> 转回正面, 姿态与 [Shot 1] 末尾的正面全身站立完全一致。"
    "转体全程由腰部带动、头部与双肩自然跟随, 转速均匀不变、不忽快忽慢, 重心原地微调、双脚基本不移动。"
    "[Shot 2] 到 [Shot 9] 的镜头完全静止, 只有 <Subject 1> 的朝向在变。"
    "\n"
    "overall_soundscape:\n"
    "室内很静, 只有转体时拖鞋鞋底与地面轻微的摩擦声与衣料摩擦的细碎声, "
    "人物没有说话, 没有其它环境音。\n"
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
    cells += ["832", "480", "15"]
    return "| " + " | ".join(cells) + " |"


# 一般情况只有一张参考图(0011 资产图); <Picture 2>/<Picture 3> 留空, 需要时再手工填帧图。
REF_14_ROW = _blank_row("@{0011_万物建模/00001_陈落}")

NOTE_14 = (
    "## 0014_参考建模 (REF2VA 15秒/24fps, 4步/20步 可切)\n"
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