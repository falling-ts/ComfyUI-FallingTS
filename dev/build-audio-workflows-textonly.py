#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 0060~0064 五个音频工作流改造成「无 md 数据表、只用官方文本框」的版本。

参考来源: stories/workflows/ 下 0060~0064 的 md 表版本(节点结构、模型、采样参数
全部照搬, 只把 `FallingTSMarkDownTable` 换掉), 以及 0070_截取声音(它本来就没有 md 节点)。

替换规则:
  md 表的提示词类 STRING 输出 -> PrimitiveStringMultiline (官方多行文本框)
  md 表的 ID STRING 输出       -> PrimitiveString (官方单行文本框, 作文件名前缀)
  md 表的秒数 INT 输出         -> PrimitiveFloat (目标端口 duration/seconds 均为 FLOAT)
  0064 的「原人声」AUDIO 输出   -> 官方 LoadAudio (Load Audio)

产品写到根 `workflows/`(前端经 ComfyUI/user/default/workflows 软链接读取的就是这里)。
脚本幂等: 重复执行得到同样的 JSON。

用法: .venv\\Scripts\\python.exe custom_nodes\\ComfyUI-FallingTS\\dev\\build-audio-workflows-textonly.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT / "stories" / "workflows"
DST_DIR = ROOT / "workflows"

COL_GAP = 80   # 列间净距(规范要求落在 (50,100))
ROW_GAP = 60   # 列内净距
Y0 = 60        # 首行 y

TXT_W, TXT_H = 420, 240     # 多行文本框
STR_W, STR_H = 420, 106     # 单行文本框
NUM_W, NUM_H = 260, 106     # 数值节点
AUD_W, AUD_H = 360, 320     # 音频加载节点


# ---------------------------------------------------------------- 构造件

def _props(ntype, connectable=True):
    return {
        "Node name for S&R": ntype,
        "cnr_id": "comfy-core",
        "ue_properties": {
            "widget_ue_connectable": {"value": connectable},
            "version": "7.8",
            "input_ue_unconnectable": {},
        },
    }


def text_node(nid, title, value, order=0):
    """官方多行文本框 PrimitiveStringMultiline。"""
    return {
        "id": nid,
        "type": "PrimitiveStringMultiline",
        "pos": [0, 0],
        "size": [TXT_W, TXT_H],
        "flags": {},
        "order": order,
        "mode": 0,
        "title": title,
        "inputs": [{"localized_name": "数值", "name": "value", "type": "STRING",
                    "widget": {"name": "value"}, "link": None}],
        "outputs": [{"localized_name": "字符串", "name": "STRING", "type": "STRING",
                     "slot_index": 0, "links": []}],
        "properties": _props("PrimitiveStringMultiline"),
        "widgets_values": [value],
        "widgets_values_named": {"value": value},
    }


def str_node(nid, title, value, order=0):
    """官方单行文本框 PrimitiveString。"""
    return {
        "id": nid,
        "type": "PrimitiveString",
        "pos": [0, 0],
        "size": [STR_W, STR_H],
        "flags": {},
        "order": order,
        "mode": 0,
        "title": title,
        "inputs": [{"localized_name": "数值", "name": "value", "type": "STRING",
                    "widget": {"name": "value"}, "link": None}],
        "outputs": [{"localized_name": "字符串", "name": "STRING", "type": "STRING",
                     "slot_index": 0, "links": []}],
        "properties": _props("PrimitiveString"),
        "widgets_values": [value],
    }


def float_node(nid, title, value, order=0):
    """官方浮点数 PrimitiveFloat。"""
    return {
        "id": nid,
        "type": "PrimitiveFloat",
        "pos": [0, 0],
        "size": [NUM_W, NUM_H],
        "flags": {},
        "order": order,
        "mode": 0,
        "title": title,
        "inputs": [{"localized_name": "值", "name": "value", "type": "FLOAT",
                    "widget": {"name": "value"}, "link": None}],
        "outputs": [{"localized_name": "浮点", "name": "FLOAT", "type": "FLOAT",
                     "slot_index": 0, "links": []}],
        "properties": _props("PrimitiveFloat"),
        "widgets_values": [value],
        "widgets_values_named": {"value": value},
    }


def load_audio_node(nid, title, value="", order=0):
    """官方 Load Audio。"""
    return {
        "id": nid,
        "type": "LoadAudio",
        "pos": [0, 0],
        "size": [AUD_W, AUD_H],
        "flags": {},
        "order": order,
        "mode": 0,
        "title": title,
        "inputs": [{"localized_name": "audio", "name": "audio", "type": "COMBO",
                    "widget": {"name": "audio"}, "link": None}],
        "outputs": [{"localized_name": "AUDIO", "name": "AUDIO", "type": "AUDIO",
                     "slot_index": 0, "links": []}],
        "properties": _props("LoadAudio", connectable=False),
        "widgets_values": [value],
    }


# ---------------------------------------------------------------- 改造工具

def load_src(fname):
    return json.loads((SRC_DIR / fname).read_text(encoding="utf-8"))


def prepare(src):
    """剥离 md 表节点与说明节点。返回 (其余节点列表, 全部连线, md 节点 id, note 节点)。"""
    md_nodes = [n for n in src["nodes"] if n["type"] == "FallingTSMarkDownTable"]
    assert len(md_nodes) == 1, f"期望恰有 1 个 md 表节点, 实得 {len(md_nodes)}"
    md_id = md_nodes[0]["id"]
    notes = [n for n in src["nodes"] if n["type"] == "MarkdownNote"]
    assert len(notes) == 1, f"期望恰有 1 个说明节点, 实得 {len(notes)}"
    drop = {"FallingTSMarkDownTable", "MarkdownNote"}
    nodes = [n for n in src["nodes"] if n["type"] not in drop]
    links = [list(l) for l in src["links"]]
    return nodes, links, md_id, notes[0]


def remap_md(links, md_id, slotmap):
    """把以 md 表为源的连线改指向新节点。

    slotmap: {md 输出槽位: 新节点 id}; 新节点输出槽位一律是 0。
    """
    hit = set()
    for l in links:
        if l[1] == md_id:
            assert l[2] in slotmap, f"md 槽位 {l[2]} 未在 slotmap 中声明"
            new_id = slotmap[l[2]]
            l[1] = new_id
            l[2] = 0
            hit.add(new_id)
    missing = set(slotmap.values()) - hit
    assert not missing, f"有官方节点没有接上任何下游: {sorted(missing)}"
    return links


def drop_dangling(links, nodes):
    ids = {n["id"] for n in nodes}
    return [l for l in links if l[1] in ids and l[3] in ids]


def rebuild_io(nodes, links):
    """按 links 重建 outputs[].links 与 inputs[].link, 保证双向一致。"""
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        for o in n.get("outputs", []):
            o["links"] = []
        for i in n.get("inputs", []):
            i["link"] = None
    for lid, s, ss, t, ts, _typ in links:
        sn, tn = by_id.get(s), by_id.get(t)
        assert sn is not None, f"link{lid} 源节点 {s} 不存在"
        assert tn is not None, f"link{lid} 目标节点 {t} 不存在"
        assert ss < len(sn.get("outputs", [])), f"link{lid} 源槽位越界 {s}.{ss}"
        assert ts < len(tn.get("inputs", [])), f"link{lid} 目标槽位越界 {t}.{ts}"
        sn["outputs"][ss]["links"].append(lid)
        tn["inputs"][ts]["link"] = lid


def layout(nodes, col_of, note):
    """按列摆位: 列内紧凑堆叠(净距 60), 列间按本列实际最大宽度 + 80 推进。"""
    cols = {}
    for n in nodes:
        if n is note:
            continue
        cols.setdefault(col_of[n["id"]], []).append(n)

    note["pos"] = [40, Y0]
    note["order"] = 0
    x = 40 + note["size"][0] + COL_GAP

    order = 1
    for c in sorted(cols):
        group = sorted(cols[c], key=lambda n: (n["pos"][1], n["id"]))
        width = max(n["size"][0] for n in group)
        y = Y0
        for n in group:
            n["pos"] = [x, y]
            n["order"] = order
            order += 1
            y += n["size"][1] + ROW_GAP
        x += width + COL_GAP


def finalize(src, nodes, note, links, note_text):
    note["widgets_values"] = [note_text]
    if "widgets_values_named" in note:
        note["widgets_values_named"] = {"text": note_text}
    note["pos"] = [40, Y0]
    note["order"] = 0

    nodes = nodes + [note]
    rebuild_io(nodes, links)
    nodes.sort(key=lambda n: n["order"])

    wf = {
        "id": src["id"],
        "revision": 0,
        "last_node_id": max(n["id"] for n in nodes),
        "last_link_id": max((l[0] for l in links), default=0),
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": src.get("extra", {}),
        "version": 0.4,
    }
    validate(wf)
    return wf


# ---------------------------------------------------------------- 自检

MUST_FEED = {
    "TextEncodeAceStepAudio1.5": ["tags", "clip", "duration"],
    "EmptyAceStep1.5LatentAudio": ["seconds"],
    "HunyuanFoleySampler": ["hunyuan_model", "hunyuan_deps", "prompt", "duration"],
    "CLIPTextEncode": ["clip", "text"],
    "EmptyLatentAudio": ["seconds"],
    "KSampler": ["model", "positive", "negative", "latent_image"],
    "VAEDecodeAudio": ["samples", "vae"],
    "QwenEmotionNode": ["emotion_text"],
    "UnifiedTTSTextNode": ["TTS_engine", "text"],
    "SaveAudioAdvanced": ["audio", "filename_prefix"],
    "PreviewAudio": ["audio"],
    "FallingTSContinue": ["any"],
    "LoadAudio": [],
}


def validate(wf):
    nodes = wf["nodes"]
    by_id = {n["id"]: n for n in nodes}
    assert len(by_id) == len(nodes), "节点 id 重复"
    assert not any(n["type"] == "FallingTSMarkDownTable" for n in nodes), "仍残留 md 表节点"

    for l in wf["links"]:
        lid, s, ss, t, ts, typ = l
        sn, tn = by_id[s], by_id[t]
        styp, ttyp = sn["outputs"][ss]["type"], tn["inputs"][ts]["type"]
        assert styp == ttyp or "*" in (styp, ttyp), \
            f"link{lid} 类型不匹配 {sn['type']}.{styp} -> {tn['type']}.{ttyp}"
        assert lid in sn["outputs"][ss]["links"], f"link{lid} 未回填源节点"
        assert tn["inputs"][ts]["link"] == lid, f"link{lid} 未回填目标节点"

    for n in nodes:
        need = MUST_FEED.get(n["type"])
        if need is None:
            continue
        for i in n.get("inputs", []):
            if i["name"] in need:
                assert i["link"] is not None, f"{n['type']}#{n['id']}.{i['name']} 未接线"

    # 每个文本框/加载节点都必须有下游
    for n in nodes:
        if n["type"] in ("PrimitiveString", "PrimitiveStringMultiline",
                         "PrimitiveFloat", "PrimitiveInt", "LoadAudio"):
            assert n["outputs"][0]["links"], f"{n['type']}#{n['id']} 没有接到任何下游"

    # 布局: 任意两节点不得重叠
    for a in nodes:
        ax, ay = a["pos"]
        aw, ah = a["size"]
        for b in nodes:
            if a["id"] >= b["id"]:
                continue
            bx, by = b["pos"]
            bw, bh = b["size"]
            ox = min(ax + aw, bx + bw) - max(ax, bx)
            oy = min(ay + ah, by + bh) - max(ay, by)
            assert not (ox > 0 and oy > 0), \
                f"节点重叠: #{a['id']}({a['type']}) 与 #{b['id']}({b['type']})"


# ---------------------------------------------------------------- 0060 背景音乐

def build_0060():
    src = load_src("0060_背景音乐.json")
    nodes, links, md_id, note = prepare(src)

    PROMPT = ("深夜都市雨夜的极简氛围音乐，以低音钢琴单音为主，持续弦乐长音铺底，"
              "节奏极慢、力度极轻，克制而压抑，贴合凌晨三点三十三分失眠独处时的紧绷与空落。")
    PREFIX = "0060_背景音乐/00001_雨夜低缓钢琴"

    t_prompt = text_node(201, "音乐提示词 (tags)", PROMPT, order=0)
    t_seconds = float_node(202, "秒数", 180, order=1)
    t_prefix = str_node(203, "文件名前缀", PREFIX, order=2)
    nodes += [t_prompt, t_seconds, t_prefix]

    # md 槽位: 0=ID 1=音乐提示词 2=秒数
    remap_md(links, md_id, {0: 203, 1: 201, 2: 202})
    links = drop_dangling(links, nodes)

    NOTE = """## 背景音乐 · 无数据表版 (ACE-Step v1.5)

**引擎**: ACE-Step v1.5 Turbo (StepFun / ACE Studio)
**权重**: `checkpoints/ComfyUI-ACE-Step/ace_step_1.5_turbo_aio.safetensors`

### 这一版和 md 表版的区别
数据表节点已移除，改为三个官方文本框直接给值：

| 文本框 | 接到哪里 |
|--------|----------|
| **音乐提示词** | `TextEncodeAceStepAudio1.5` 的 `tags` |
| **秒数** | 该节点 `duration` + `EmptyAceStep1.5LatentAudio` 的 `seconds` |
| **文件名前缀** | `SaveAudioAdvanced` 的 `filename_prefix` |

要换一首曲子，直接在节点上改这三处，不用开数据表。

### 参数要点
- **纯音乐**：`lyrics` 留空即无人声；要带唱就把歌词填进该字段
- **步数 8 / cfg 1**：turbo 权重官方配方，不要按常规 20 步调
- **shift 3**（`ModelSamplingAuraFlow`）：官方模板值，改大更发散、改小更贴提示词
- **bpm 120 / C minor**：氛围乐默认，可按需改

### 链路
文本框 → ACE-Step 编码 → KSampler → VAE 解码 → 试听 → 继续闸门 → 保存

产物落在 `output/0060_背景音乐/` 下，文件名由「文件名前缀」决定。"""

    col = {
        201: 1, 202: 1, 203: 1,          # 三个文本框列为参数列
        5: 2,                            # EmptyAceStep1.5LatentAudio
        2: 2,                            # CheckpointLoaderSimple
        4: 3,                            # TextEncodeAceStepAudio1.5
        3: 3,                            # ModelSamplingAuraFlow
        6: 4,                            # ConditioningZeroOut
        7: 5,                            # KSampler
        8: 6,                            # VAEDecodeAudio
        9: 7,                            # PreviewAudio
        10: 8,                           # FallingTSContinue
        11: 9,                           # SaveAudioAdvanced
    }
    layout(nodes, col, note)
    return finalize(src, nodes, note, links, NOTE)


# ---------------------------------------------------------------- 0061 环境音效

def build_0061():
    src = load_src("0061_环境音效.json")
    nodes, links, md_id, note = prepare(src)

    PROMPT = ("连续三天的深夜细雨敲打窗户，雨点细密地落在玻璃上，"
              "玻璃表面蒙着水雾和雨痕，远处传来城市车流的低沉声与高楼之间的闷响，"
              "安静而持续的雨夜氛围。")
    PREFIX = "0061_环境音效/00001_窗外夜雨"

    t_prompt = text_node(201, "音效提示词", PROMPT, order=0)
    t_seconds = float_node(202, "秒数", 30, order=1)
    t_prefix = str_node(203, "文件名前缀", PREFIX, order=2)
    nodes += [t_prompt, t_seconds, t_prefix]

    # md 槽位: 0=ID 1=音效提示词 2=秒数
    remap_md(links, md_id, {0: 203, 1: 201, 2: 202})
    links = drop_dangling(links, nodes)

    NOTE = """## 环境音效 · 无数据表版 (Hunyuan Video Foley)

**引擎**: HunyuanVideo Foley
**权重**: `hunyuanvideo_foley.pth` + `vae_128d_48k_fp16.pth` / `synchformer_state_dict_fp16.pth`

### 这一版和 md 表版的区别
数据表节点已移除，改为三个官方文本框直接给值：

| 文本框 | 接到哪里 |
|--------|----------|
| **音效提示词** | `HunyuanFoleySampler` 的 `prompt` |
| **秒数** | 该节点 `duration`（上限 60 秒） |
| **文件名前缀** | `SaveAudioAdvanced` 的 `filename_prefix` |

### 参数要点
- **提示词写成一句英文或中文场景描述**：说清「什么东西、在什么表面、发出什么声」
- **秒数上限 60**：本节点 `duration` 最大 60，要更长就分几段生成再拼
- **cfg 4.5 / 步数 50 / euler**：官方默认，动之前先跑一遍基线
- **负向提示词**已固定为 `noisy, harsh`，用于压掉刺耳噪声

### 链路
文本框 → Hunyuan Foley 采样 → 试听 → 继续闸门 → 保存

产物落在 `output/0061_环境音效/` 下。"""

    col = {
        201: 1, 202: 1, 203: 1,
        2: 2,     # HunyuanModelLoader
        3: 2,     # HunyuanDependenciesLoader
        4: 3,     # HunyuanFoleySampler
        5: 4,     # PreviewAudio
        6: 5,     # FallingTSContinue
        7: 6,     # SaveAudioAdvanced
    }
    layout(nodes, col, note)
    return finalize(src, nodes, note, links, NOTE)


# ---------------------------------------------------------------- 0062 效果音效

def build_0062():
    src = load_src("0062_效果音效.json")
    nodes, links, md_id, note = prepare(src)

    PROMPT = "手机扣在桌面上震动了一下，沉闷而短促的一声嗡鸣，桌面随之微微共振。"
    PREFIX = "0062_效果音效/00001_手机震动"

    t_prompt = text_node(201, "音效提示词", PROMPT, order=0)
    t_neg = text_node(202, "负向提示词 (cfg=1 时不生效)", "", order=1)
    t_seconds = float_node(203, "秒数", 2, order=2)
    t_prefix = str_node(204, "文件名前缀", PREFIX, order=3)
    nodes += [t_prompt, t_neg, t_seconds, t_prefix]

    # 原 md 把「音效提示词」同时接到正向 #4 与负向 #5;
    # 这里拆成两个独立文本框: 正向用提示词, 负向单独给(默认空, cfg=1 时被忽略)。
    # md 槽位: 0=ID 1=音效提示词 2=秒数
    for l in links:
        if l[1] == md_id:
            if l[2] == 0:
                l[1], l[2] = 204, 0        # ID -> 文件名前缀
            elif l[2] == 2:
                l[1], l[2] = 203, 0        # 秒数 -> 秒数
            elif l[2] == 1:
                if l[3] == 4:              # 正向编码
                    l[1], l[2] = 201, 0
                elif l[3] == 5:            # 负向编码
                    l[1], l[2] = 202, 0
                else:
                    raise AssertionError(f"意外的提示词下游: {l}")
            else:
                raise AssertionError(f"意外的 md 槽位: {l}")
    links = drop_dangling(links, nodes)

    NOTE = """## 效果音效 · 无数据表版 (Stable Audio 3 small_sfx)

**引擎**: Stable Audio 3 small_sfx
**权重**: `stable_audio_3_small_sfx.safetensors` + `t5gemma_b_b_ul2.safetensors`（CLIP `stable_audio`）

### 这一版和 md 表版的区别
数据表节点已移除，改为四个官方文本框直接给值：

| 文本框 | 接到哪里 |
|--------|----------|
| **音效提示词** | 正向 `CLIPTextEncode` 的 `text` |
| **负向提示词** | 负向 `CLIPTextEncode` 的 `text`（**cfg=1 时实际不生效**，留空即可） |
| **秒数** | `EmptyLatentAudio` 的 `seconds` |
| **文件名前缀** | `SaveAudioAdvanced` 的 `filename_prefix` |

> md 表版把同一个提示词同时接到正负两端；本版拆成两个文本框，语义更清楚。

### 参数要点
- **提示词写「一次动作」**：一件物体、一次发声，别塞多个事件
- **秒数 2~10 秒**最稳；更长容易糊成环境音
- **步数 8 / cfg 1 / lcm**：small_sfx 的加速配方，改大反而变差
- **和 0060 的分工**：0062 只擅长短音效，成品音乐走 0060 的 ACE-Step

### 链路
文本框 → CLIP 编码 → KSampler → VAE 解码 → 试听 → 继续闸门 → 保存

产物落在 `output/0062_效果音效/` 下。"""

    col = {
        201: 1, 202: 1, 203: 1, 204: 1,
        6: 2,     # EmptyLatentAudio
        2: 2,     # CheckpointLoaderSimple
        3: 2,     # CLIPLoader
        4: 3,     # CLIPTextEncode 正向
        5: 3,     # CLIPTextEncode 负向
        7: 4,     # KSampler
        8: 5,     # VAEDecodeAudio
        9: 6,     # PreviewAudio
        10: 7,    # FallingTSContinue
        11: 8,    # SaveAudioAdvanced
    }
    layout(nodes, col, note)
    return finalize(src, nodes, note, links, NOTE)


# ---------------------------------------------------------------- 0063 文生人声

def build_0063():
    src = load_src("0063_文生人声.json")
    nodes, links, md_id, note = prepare(src)

    CONTENT = "今晚算是写不出来了。脑子里空荡荡的，最近怪事搞得我连一句像样的对白都挤不出来。"
    EMOTION = ("二十多岁男性，声音疲惫低沉，像自言自语，音量很低、语速偏慢，"
               "字与字之间留有明显停顿，透着压抑与沉重。")
    PREFIX = "0063_文生人声/00001_陈落卡稿独白"

    t_text = text_node(201, "内容 (要读的文字)", CONTENT, order=0)
    t_emotion = text_node(202, "情绪", EMOTION, order=1)
    t_prefix = str_node(203, "文件名前缀", PREFIX, order=2)
    nodes += [t_text, t_emotion, t_prefix]

    # md 槽位: 0=ID 1=内容 2=情绪
    remap_md(links, md_id, {0: 203, 1: 201, 2: 202})
    links = drop_dangling(links, nodes)

    NOTE = """## 文生人声 · 无数据表版 (IndexTTS-2.5 + Qwen 情绪)

**引擎**: IndexTTS-2.5
**情绪模型**: `qwen0.6bemo4-merge`（Qwen 情绪编码）

### 这一版和 md 表版的区别
数据表节点已移除，改为三个官方文本框直接给值：

| 文本框 | 接到哪里 |
|--------|----------|
| **内容** | `UnifiedTTSTextNode` 的 `text` |
| **情绪** | `QwenEmotionNode` 的 `emotion_text` |
| **文件名前缀** | `SaveAudioAdvanced` 的 `filename_prefix` |

### 参数要点
- **内容**：直接写要读出来的台词；用 `[角色名]` 可切换不同音色
- **情绪**：用自然语言描述音色与状态（年龄/性别/气息/语速/停顿），写得越具体越稳
- **音色**：`narrator_voice` 默认 `voices_examples/male/male_01.wav`，可从下拉换
- **长文本**：`enable_chunking` 已开，`max_chars_per_chunk` 400，过长会自动分段

### 链路
文本框 → Qwen 情绪编码 → IndexTTS 引擎 → TTS 合成 → 试听 → 继续闸门 → 保存

产物落在 `output/0063_文生人声/` 下。
要「用某个已有声音去念新台词」，请用 `0064_参考人声`。"""

    col = {
        201: 1, 202: 1, 203: 1,
        8: 2,     # QwenEmotionNode
        2: 3,     # IndexTTSEngineNode
        3: 4,     # UnifiedTTSTextNode
        4: 5,     # PreviewAudio
        5: 6,     # FallingTSContinue
        6: 7,     # SaveAudioAdvanced
    }
    layout(nodes, col, note)
    return finalize(src, nodes, note, links, NOTE)


# ---------------------------------------------------------------- 0064 参考人声

def build_0064():
    src = load_src("0064_参考人声.json")
    nodes, links, md_id, note = prepare(src)

    CONTENT = "又来，三个晚上了，连续三天同一个时间醒，是不是有点不正常？"
    EMOTION = "困惑不安，声音放低带点迟疑，像在自言自语，句尾微微上扬带疑问语气。"
    PREFIX = "0064_参考人声/00001_陈落台词"

    # 「原人声」原本来自 md 表的 AUDIO 列, 这里换成官方 Load Audio
    a_ref = load_audio_node(204, "参考人声 (原音频)", "", order=0)
    t_text = text_node(201, "内容 (要读的新台词)", CONTENT, order=1)
    t_emotion = text_node(202, "情绪", EMOTION, order=2)
    t_prefix = str_node(203, "文件名前缀", PREFIX, order=3)
    nodes += [a_ref, t_text, t_emotion, t_prefix]

    # md 槽位: 0=ID 1=原人声(AUDIO) 2=内容 3=情绪
    remap_md(links, md_id, {0: 203, 1: 204, 2: 201, 3: 202})
    links = drop_dangling(links, nodes)

    # opt_narrator 是 * 类型, 原连线类型记的是 '*', 与 LoadAudio 的 AUDIO 兼容
    for l in links:
        if l[1] == 204:
            l[5] = "*"

    NOTE = """## 参考人声 · 无数据表版 (IndexTTS-2.5 音色克隆 + Qwen 情绪)

**引擎**: IndexTTS-2.5 + `qwen0.6bemo4-merge`
**用途**: 拿一段**已有的声音**当音色参考，让它去念**新的台词**。

### 这一版和 md 表版的区别
数据表节点已移除，改为「一个官方音频加载节点 + 三个官方文本框」：

| 节点 | 接到哪里 |
|------|----------|
| **参考人声**（Load Audio） | `UnifiedTTSTextNode` 的 `opt_narrator`（音色参考） |
| **内容** | 该节点的 `text`（要念的新台词） |
| **情绪** | `QwenEmotionNode` 的 `emotion_text` |
| **文件名前缀** | `SaveAudioAdvanced` 的 `filename_prefix` |

> ⚠️ **参考人声要在节点上的下拉里手选**：官方 `Load Audio` 只从 `input` 目录一层列文件，
> 而本机产物都在 `output/` 各子目录。先把音频放到 `input/`（`ComfyUI/input` 已软链到
> `media/default`），再在节点下拉里选中即可。
> 若想直接指向 `output/` 里的历史产物，可把该节点换成自带的「加载音频（来自输出）」。

### 参数要点
- **参考音频越干净越好**：单人、无背景音乐、2~10 秒，能明显听出音色
- **内容**：写新台词，不要照抄参考音频里的原话
- **情绪**：仍然生效，用来在新台词上加重语气方向
- **`narrator_voice` 此时失效**：接了 `opt_narrator` 就以参考音频为准

### 链路
参考音频 ┐
　　　　 ├→ UnifiedTTSTextNode → 试听 → 继续闸门 → 保存
内容+情绪 ┘

产物落在 `output/0064_参考人声/` 下。"""

    col = {
        204: 1,   # 参考人声 Load Audio
        201: 1, 202: 1, 203: 1,
        8: 2,     # QwenEmotionNode
        2: 3,     # IndexTTSEngineNode
        3: 4,     # UnifiedTTSTextNode
        4: 5,     # PreviewAudio
        5: 6,     # FallingTSContinue
        6: 7,     # SaveAudioAdvanced
    }
    layout(nodes, col, note)
    return finalize(src, nodes, note, links, NOTE)


# ---------------------------------------------------------------- 入口

BUILDERS = [
    ("0060_背景音乐.json", build_0060),
    ("0061_环境音效.json", build_0061),
    ("0062_效果音效.json", build_0062),
    ("0063_文生人声.json", build_0063),
    ("0064_参考人声.json", build_0064),
]


def main():
    DST_DIR.mkdir(parents=True, exist_ok=True)
    for fname, fn in BUILDERS:
        wf = fn()
        out = DST_DIR / fname
        out.write_text(
            json.dumps(wf, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        kinds = {}
        for n in wf["nodes"]:
            kinds[n["type"]] = kinds.get(n["type"], 0) + 1
        prims = sum(v for k, v in kinds.items() if k.startswith("Primitive") or k == "LoadAudio")
        print(f"  {fname:<24} 节点 {len(wf['nodes']):>2}  连线 {len(wf['links']):>2}  "
              f"官方输入 {prims}  {out.stat().st_size:>6} B")

    print("\n自检: 全部通过(无 md 表节点 / 端口类型匹配 / 接线完整 / 无节点重叠)")


if __name__ == "__main__":
    main()
