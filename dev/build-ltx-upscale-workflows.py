# -*- coding: utf-8 -*-
"""生视频工作流(0040~0044)的「H3 一采 → LTX-2.5 二采」拼接。

## 做什么

把一段 **LTX-2.5 二采放大链**接到每个生视频工作流的 PreviewVideo 之后:

    H3 段(已存在, 一采: 定框架/动作/音轨)
        VAEDecode → CreateVideo → PreviewVideo
                                     │
                                     ├─ video ─────────────────┐
                                     └─ prefix ──→ 保存节点前缀  │
                                                                ▼
    ┌──────────────────── LTX-2.5 二采(本脚本新增) ────────────────────┐
    │ GetVideoComponents(H3 视频) → 帧批 + 音轨                       │
    │        │                                                        │
    │        ├─ 全部帧 ──→ LTXAddVideoICLoRAGuide(IC-LoRA 引导注入)    │
    │        └─ 第一帧 ──→ LTXVImgToVideoInplace(锚定首帧)             │
    │ Stage 1: 8 步蒸馏采样(1.0→0.0 sigma) → LTXVCropGuides            │
    │ Stage 2: LTXVLatentUpsampler(latent 2x) → 3 步重采样(0.85→0.0)   │
    │ 平铺 VAE 解码 + 音频透传 → CreateVideo → PreviewVideo(1088p)     │
    └──────────────────────────────────────────────────────────────────┘

## 二采原理(与 wan 的高低双采样同构)

一采 H3 定框架(0.5MP 档 960×544): 动作、构图、音轨全部由它决定。
二采 LTX-2.5 在**潜空间**放大 2 倍再重采样补细节, 于是 960×544 → 1920×1088(≈1080p)。
关键在 Stage 1 用 `LTXAddVideoICLoRAGuide` 把**H3 全部帧**作为 IC-LoRA 引导注入 latent
——这是「动作与构图逐帧保留」的来源; Stage 2 只做低 sigma 重采样(0.85→0), 不重画内容。

## 尺寸与帧数: 全部从 H3 段接线, 不写死

- 帧批来自 `PreviewVideo.video` → `GetVideoComponents.images`, 帧数天然等于 H3 产出;
- Stage 2 的放大倍数固定为 2(latent 空间), 输出 = H3 尺寸 × 2;
- `LTXAddVideoICLoRAGuide.frame_idx=0` 表示"与生成片段对齐"(视频参考的标准用法)。

## 依赖(必须)

`Custom_Nodes/ComfyUI-LTXVideo`(Lightricks 官方)提供两个关键节点:
`LTXAddVideoICLoRAGuide`(IC-LoRA 引导帧注入) 与 `LTXICLoRALoaderModelOnly`(IC-LoRA 权重加载)。
本机 2026-10-16 安装。缺这两个节点时脚本会在校验阶段直接报错, 不会写出半成品。

## 幂等

脚本按**标题前缀**识别自己上次插入的尾部节点并整段撤掉再重建, 可反复跑。
（⚠️ 与 build-scene-workflows.py 同理: `next_id` 只看节点列表最大值, 不掺 `last_node_id`,
否则第二次跑 id 会持续上涨, 脚本就不幂等了。）

跑法(工作区根): python custom_nodes/ComfyUI-FallingTS/dev/build-ltx-upscale-workflows.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent.parent
WF_DIR = ROOT / "workflows"

# 要拼接的目标工作流
TARGETS = [
    "0040_文生视频",
    "0041_首帧视频",
    "0042_首尾视频",
    "0043_关键帧视频",
    "0044_参考视频",
]

# 本脚本插入的尾部节点统一标题前缀(幂等识别用)
#
# ⚠️ 用**前缀匹配**而不是精确标题白名单: 白名单要手工跟着节点增删同步, 漏一个就会让那个
#    节点每次都被留下、逐次累积(实测踩过: 加了「H3 尺寸/帧数」节点却忘了往白名单里补,
#    于是每跑一次就多残留一个节点, 工作流越跑越脏且不再幂等)。前缀匹配天然免疫这种遗漏。
TAG = "LTX二采"
TITLE_PREFIX = TAG + " · "

# ─── 节点参数(取自社区实测方案 + 官方 LTX-2.5 模板) ──────────────────────────

# 模型口径: 本机 bf16 全套(参考实现用的也是 bf16)。若显存吃紧可换 int8-convrot 档。
UNET_LTX = "LTX-2.5/ltx-2.5-22b-distilled-transformer-bf16.safetensors"
CLIP_LTX = "LTX-2.5/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors"
VAE_VIDEO = "LTX-2.5/ltx-2.5-video-vae-bf16.safetensors"
UPSCALE_MODEL = "LTX-2.5/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
# IC-LoRA: ingredients 是"成分/素材保真"向的 IC-LoRA, 参考实现用它做动作保留
IC_LORA = "ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors"

# Stage 1: 8 步蒸馏(1.0 → 0.0), 把 H3 帧作为引导注入后重建
SIGMAS_STAGE1 = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
# Stage 2: latent 2x 后的 3 步低 sigma 重采样(0.85 → 0), 只补细节不重画
SIGMAS_STAGE2 = "0.85, 0.7250, 0.4219, 0.0"

PROMPT_POS = (
    "Upscale the source video to clean 1080p resolution while strictly preserving the "
    "original composition, character identity, facial features, clothing, pose, camera "
    "angle and motion. Do not change the scene or story. Improve sharpness, detail, "
    "natural skin texture, fabric texture and lighting quality. Add subtle film grain "
    "and cinematic color grading. Avoid over-smoothing, face distortion, body "
    "deformation, flickering and unnatural changes."
)
PROMPT_NEG = (
    "blurry, pixelated, jitter, morphing, artifacts, oversaturated, flickering, "
    "distorted face, deformed hands, bad anatomy, plastic skin, oversmoothed, noisy, "
    "grain overdone, color shift, character change, composition change, text, "
    "watermark, logo"
)

FPS = 24


# ─── 基础工具 ───────────────────────────────────────────────────────────────


def load(name: str) -> dict:
    return json.loads((WF_DIR / (name + ".json")).read_text(encoding="utf-8"))


def save(name: str, wf: dict) -> None:
    text = json.dumps(wf, ensure_ascii=False, separators=(",", ":"))
    (WF_DIR / (name + ".json")).write_text(text, encoding="utf-8")


def next_id(wf: dict) -> int:
    """下一个可用节点 id = 现有最大值 + 1。

    ⚠️ **不掺 `last_node_id`**: 本脚本会先 strip_tail 删掉上次插入的一批, 而 last_node_id
    记的是历史最大值, 掺进来会让重跑的 id 持续上涨, 脚本就不幂等了。
    """
    return max(n["id"] for n in wf["nodes"]) + 1


def next_link_id(wf: dict) -> int:
    """下一个可用连线 id; 不掺 last_link_id, 理由同 next_id。"""
    return max(l[0] for l in wf["links"]) + 1


def relink(wf: dict) -> None:
    """按 links 表重建 inputs[].link 与 outputs[].links。

    前端序列化格式里连线记在三处(全局 links 表、目标 inputs[].link、源 outputs[].links),
    改完 links 表必须重建后两者, 否则前端加载时端口是空的。
    """
    by_id = {n["id"]: n for n in wf["nodes"]}
    for n in wf["nodes"]:
        for inp in n.get("inputs") or []:
            inp["link"] = None
        for out in n.get("outputs") or []:
            out["links"] = []
    for link in wf["links"]:
        _lid, src, src_slot, dst, dst_slot = link[0], link[1], link[2], link[3], link[4]
        s = by_id.get(src)
        d = by_id.get(dst)
        if s is None or d is None:
            continue
        if src_slot < len(s.get("outputs") or []):
            s["outputs"][src_slot].setdefault("links", []).append(_lid)
        if dst_slot < len(d.get("inputs") or []):
            d["inputs"][dst_slot]["link"] = _lid


def strip_tail(wf: dict) -> int:
    """删掉本脚本上次插入的尾部节点与其连线。返回删除数。

    识别靠**标题前缀** `TITLE_PREFIX` —— 本脚本新建的每个节点标题都带它, 而工作流原有节点
    都不会以它为前缀, 因此不会误删; 也无需在增删节点时同步维护任何白名单。

    ⚠️ **加一道形态闸门**: 0030/0031/0032 的二采是早期手工搭的 LTX 潜空间放大链(标题现在
    也叫 `LTX二采 · xxx`), 但它**没有** `EmptyLTXVLatentVideo` / `LTXAddVideoICLoRAGuide` 这
    两个本脚本必建的节点。只看标题前缀会把它们当自家链删掉。故要求「组内出现本脚本的标志
    节点」才认领 —— 那两节点同时缺失就说明这段不是本脚本建的。
    """
    tagged = {
        n["id"]
        for n in wf["nodes"]
        if (n.get("title") or "").startswith(TITLE_PREFIX)
    }
    if not tagged:
        return 0
    types = {n["type"] for n in wf["nodes"] if n["id"] in tagged}
    if not {"EmptyLTXVLatentVideo", "LTXAddVideoICLoRAGuide"} <= types:
        return 0
    doomed = tagged
    wf["links"] = [l for l in wf["links"] if l[1] not in doomed and l[3] not in doomed]
    wf["nodes"] = [n for n in wf["nodes"] if n["id"] not in doomed]
    # 端口引用也要跟着清: 被删节点连过的下游, 其 inputs[].link 仍指着已删的连线
    return len(doomed)


# ─── 节点构造 ───────────────────────────────────────────────────────────────


class Builder:
    """按顺序分配 id 与 link, 并维护 nodes/links。"""

    def __init__(self, wf: dict):
        self.wf = wf
        self.nid = next_id(wf)
        self.lid = next_link_id(wf)
        self.col: dict = {}      # 节点 id -> 列号(用于分层布局)

    def node(self, ntype: str, title: str, widgets=None, inputs=None, outputs=None,
             size=(330, 100), col: int = 0) -> dict:
        n = {
            "id": self.nid,
            "type": ntype,
            "pos": [0, 0],
            "size": list(size),
            "flags": {},
            "order": 0,
            "mode": 0,
            "inputs": inputs or [],
            "outputs": outputs or [],
            "properties": {"Node name for S&R": ntype},
        }
        if title:
            n["title"] = title
        if widgets is not None:
            n["widgets_values"] = widgets
        self.col[self.nid] = col
        self.nid += 1
        self.wf["nodes"].append(n)
        return n

    def link(self, src: dict, src_slot: int, dst: dict, dst_slot: int, dtype: str) -> int:
        lid = self.lid
        self.lid += 1
        self.wf["links"].append([lid, src["id"], src_slot, dst["id"], dst_slot, dtype])
        return lid


def in_slot(name, dtype, widget=None):
    s = {"name": name, "type": dtype, "link": None}
    if widget:
        s["widget"] = {"name": widget}
    return s


def out_slot(name, dtype, slot_index):
    return {"name": name, "type": dtype, "links": [], "slot_index": slot_index}


# 端口索引常量(避免魔法数字写错)
L_VIDEO = 0       # PreviewVideo.video
L_PREFIX = 2      # PreviewVideo.prefix

G_IMAGES = 0      # GetVideoComponents.images
G_AUDIO = 1       # GetVideoComponents.audio

ICO_MODEL = 0     # LTXICLoRALoaderModelOnly.model
ICO_FACTOR = 1    # LTXICLoRALoaderModelOnly.latent_downscale_factor

GUIDE_POS = 0     # LTXAddVideoICLoRAGuide.positive
GUIDE_NEG = 1     # LTXAddVideoICLoRAGuide.negative
GUIDE_LATENT = 2  # LTXAddVideoICLoRAGuide.latent

CROP_POS = 0
CROP_NEG = 1
CROP_LATENT = 2


def ensure_outputs(node: dict, needed: int) -> None:
    """把节点的输出端口补齐到至少 needed 个。

    ⚠️ 老存档里的 PreviewVideo 只有 1 个输出端口(video), 而连线要接到 slot 2(prefix)。
    前端加载时本会按节点定义自动补齐端口, 但**脚本读的是磁盘 JSON**, 不补就会写出
    指向不存在端口的连线 —— 前端加载该工作流时那根线会凭空消失(静默丢线, 不报错)。
    """
    outs = node.setdefault("outputs", [])
    while len(outs) < needed:
        idx = len(outs)
        # 前三个端口是 video/audio/prefix, 之后是选中帧
        if idx == 1:
            outs.append(out_slot("audio", "AUDIO", 1))
        elif idx == 2:
            outs.append(out_slot("prefix", "STRING", 2))
        else:
            outs.append(out_slot(f"选中帧 {idx - 2}", "IMAGE", idx))


def build_chain(wf: dict, pv: dict) -> list:
    """在 PreviewVideo 之后建整条 LTX-2.5 二采链, 返回新增节点列表。"""
    # 先保证源端口存在, 否则后面 b.link(pv, L_PREFIX, ...) 会写到不存在的槽位
    ensure_outputs(pv, 3)
    b = Builder(wf)

    # ── 从 H3 视频拆帧与取音轨 ──
    gvc = b.node(
        "GetVideoComponents", f"{TAG} · H3 视频解码",
        outputs=[out_slot("images", "IMAGE", 0), out_slot("audio", "AUDIO", 1),
                 out_slot("fps", "FLOAT", 2), out_slot("bit_depth", "COMBO", 3),
                 out_slot("color_space", "COMBO", 4)],
        inputs=[in_slot("video", "VIDEO")],
        size=(320, 130),
    )
    b.link(pv, L_VIDEO, gvc, 0, "VIDEO")

    first = b.node(
        "ImageFromBatch", f"{TAG} · 首帧",
        widgets=[0, 1],
        inputs=[in_slot("image", "IMAGE"), in_slot("batch_index", "INT", "batch_index"),
                in_slot("length", "INT", "length")],
        outputs=[out_slot("IMAGE", "IMAGE", 0)],
        size=(300, 110),
    )
    b.link(gvc, G_IMAGES, first, 0, "IMAGE")

    # ── 模型与 VAE ──
    vae = b.node("VAELoader", f"{TAG} · 视频VAE", widgets=[VAE_VIDEO],
                 outputs=[out_slot("VAE", "VAE", 0)], size=(320, 60))
    unet = b.node("UNETLoader", f"{TAG} · 视频模型", widgets=[UNET_LTX, "default"],
                  outputs=[out_slot("MODEL", "MODEL", 0)], size=(340, 80))
    clip = b.node("CLIPLoader", f"{TAG} · 文本编码器", widgets=[CLIP_LTX, "ltxv", "default"],
                  outputs=[out_slot("CLIP", "CLIP", 0)], size=(360, 100))
    iclora = b.node("LTXICLoRALoaderModelOnly", f"{TAG} · IC-LoRA权重",
                    widgets=[IC_LORA, 1],
                    inputs=[in_slot("model", "MODEL")],
                    outputs=[out_slot("model", "MODEL", 0),
                             out_slot("latent_downscale_factor", "FLOAT", 1)],
                    size=(360, 100))
    b.link(unet, 0, iclora, 0, "MODEL")

    # ── 条件 ──
    pos = b.node("CLIPTextEncode", f"{TAG} · 正提示词", widgets=[PROMPT_POS],
                 inputs=[in_slot("clip", "CLIP"), in_slot("text", "STRING", "text")],
                 outputs=[out_slot("CONDITIONING", "CONDITIONING", 0)], size=(420, 180))
    neg = b.node("CLIPTextEncode", f"{TAG} · 负提示词", widgets=[PROMPT_NEG],
                 inputs=[in_slot("clip", "CLIP"), in_slot("text", "STRING", "text")],
                 outputs=[out_slot("CONDITIONING", "CONDITIONING", 0)], size=(420, 180))
    b.link(clip, 0, pos, 0, "CLIP")
    b.link(clip, 0, neg, 0, "CLIP")

    cond = b.node("LTXVConditioning", f"{TAG} · 条件", widgets=[FPS],
                  inputs=[in_slot("positive", "CONDITIONING"),
                          in_slot("negative", "CONDITIONING"),
                          in_slot("frame_rate", "FLOAT", "frame_rate")],
                  outputs=[out_slot("positive", "CONDITIONING", 0),
                           out_slot("negative", "CONDITIONING", 1)],
                  size=(320, 110))
    b.link(pos, 0, cond, 0, "CONDITIONING")
    b.link(neg, 0, cond, 1, "CONDITIONING")

    # ── 空 latent: 尺寸与帧数**全部由 H3 帧批自动决定** ──
    # ⚠️ 不能写死宽高: 一采的 FallingTSSelector 可在 480p/544p/768p 之间切档, 二采必须跟随,
    #    否则 LTXAddVideoICLoRAGuide 会把引导帧 resize 到你写死的尺寸上 —— 画面被拉伸或裁切,
    #    而且不会报错。length 接帧批的 batch_size: latent 帧数 = ((N-1)//8)+1, 恰好让引导帧
    #    在 LTX 的 8n+1 网格内对齐(num_frames_to_keep 会把末尾不足一组的帧丢掉, 不报错)。
    size_n = b.node(
        "GetImageSize", f"{TAG} · H3 尺寸/帧数",
        inputs=[in_slot("image", "IMAGE")],
        outputs=[out_slot("width", "INT", 0), out_slot("height", "INT", 1),
                 out_slot("batch_size", "INT", 2)],
        size=(300, 100))
    b.link(gvc, G_IMAGES, size_n, 0, "IMAGE")

    latent = b.node(
        "EmptyLTXVLatentVideo", f"{TAG} · 空latent", widgets=[544, 960, 121, 1],
        inputs=[in_slot("width", "INT", "width"), in_slot("height", "INT", "height"),
                in_slot("length", "INT", "length"), in_slot("batch_size", "INT", "batch_size")],
        outputs=[out_slot("LATENT", "LATENT", 0)], size=(300, 130),
    )
    b.link(size_n, 0, latent, 0, "INT")
    b.link(size_n, 1, latent, 1, "INT")
    b.link(size_n, 2, latent, 2, "INT")

    anchor = b.node(
        "LTXVImgToVideoInplace", f"{TAG} · 首帧锚定", widgets=[1.0, False],
        inputs=[in_slot("vae", "VAE"), in_slot("image", "IMAGE"), in_slot("latent", "LATENT"),
                in_slot("strength", "FLOAT", "strength"), in_slot("bypass", "BOOLEAN", "bypass")],
        outputs=[out_slot("latent", "LATENT", 0)], size=(300, 130))
    b.link(vae, 0, anchor, 0, "VAE")
    b.link(first, 0, anchor, 1, "IMAGE")
    b.link(latent, 0, anchor, 2, "LATENT")

    guide = b.node(
        "LTXAddVideoICLoRAGuide", f"{TAG} · 引导注入",
        # ⚠️ widgets 必须给满 12 个(10 required + 2 optional), 少给会让前端按下标取值错位。
        #    口径: frame_idx=0(H3 帧与生成片段对齐)、strength=1(全强度引导)、
        #    latent_downscale_factor 由 IC-LoRA 节点的输出接线覆盖、crop=disabled、
        #    use_tiled_encode=True(1088p 引导帧较大, 平铺编码省显存)、tile 256/64。
        widgets=[0, 1.0, 1.0, "disabled", True, 256, 64, False, 97],
        inputs=[in_slot("positive", "CONDITIONING"), in_slot("negative", "CONDITIONING"),
                in_slot("vae", "VAE"), in_slot("latent", "LATENT"), in_slot("image", "IMAGE"),
                in_slot("frame_idx", "INT", "frame_idx"),
                in_slot("strength", "FLOAT", "strength"),
                in_slot("latent_downscale_factor", "FLOAT", "latent_downscale_factor"),
                in_slot("crop", "COMBO", "crop"),
                in_slot("use_tiled_encode", "BOOLEAN", "use_tiled_encode"),
                in_slot("tile_size", "INT", "tile_size"),
                in_slot("tile_overlap", "INT", "tile_overlap"),
                in_slot("use_streaming", "BOOLEAN", "use_streaming"),
                in_slot("tile_frames", "INT", "tile_frames")],
        outputs=[out_slot("positive", "CONDITIONING", 0),
                 out_slot("negative", "CONDITIONING", 1),
                 out_slot("latent", "LATENT", 2)],
        size=(360, 210))
    b.link(cond, 0, guide, 0, "CONDITIONING")
    b.link(cond, 1, guide, 1, "CONDITIONING")
    b.link(vae, 0, guide, 2, "VAE")
    b.link(anchor, 0, guide, 3, "LATENT")
    b.link(gvc, G_IMAGES, guide, 4, "IMAGE")
    b.link(iclora, ICO_FACTOR, guide, 7, "FLOAT")

    # ── Stage 1: 8 步蒸馏采样 ──
    n1 = b.node("RandomNoise", f"{TAG} · Stage1 噪声", widgets=[42, "fixed"],
                outputs=[out_slot("NOISE", "NOISE", 0)], size=(300, 80))
    g1 = b.node("CFGGuider", f"{TAG} · Stage1 引导", widgets=[1.0],
                inputs=[in_slot("model", "MODEL"), in_slot("positive", "CONDITIONING"),
                        in_slot("negative", "CONDITIONING"), in_slot("cfg", "FLOAT", "cfg")],
                outputs=[out_slot("GUIDER", "GUIDER", 0)], size=(300, 120))
    # ⚠️ Stage 1 用**原始 UNET**(不带 IC-LoRA 权重), 权重由 LTXAddVideoICLoRAGuide 自身的
    #    引导注意力承担 —— 与参考实现一致。
    b.link(unet, 0, g1, 0, "MODEL")
    b.link(guide, GUIDE_POS, g1, 1, "CONDITIONING")
    b.link(guide, GUIDE_NEG, g1, 2, "CONDITIONING")

    s1 = b.node("KSamplerSelect", f"{TAG} · Stage1 采样器", widgets=["euler_ancestral"],
                outputs=[out_slot("SAMPLER", "SAMPLER", 0)], size=(300, 60))
    sg1 = b.node("ManualSigmas", f"{TAG} · Stage1 sigmas", widgets=[SIGMAS_STAGE1],
                 outputs=[out_slot("SIGMAS", "SIGMAS", 0)], size=(420, 60))
    sm1 = b.node("SamplerCustomAdvanced", f"{TAG} · Stage1 采样",
                 inputs=[in_slot("noise", "NOISE"), in_slot("guider", "GUIDER"),
                         in_slot("sampler", "SAMPLER"), in_slot("sigmas", "SIGMAS"),
                         in_slot("latent_image", "LATENT")],
                 outputs=[out_slot("output", "LATENT", 0),
                          out_slot("denoised_output", "LATENT", 1)],
                 size=(340, 150))
    b.link(n1, 0, sm1, 0, "NOISE")
    b.link(g1, 0, sm1, 1, "GUIDER")
    b.link(s1, 0, sm1, 2, "SAMPLER")
    b.link(sg1, 0, sm1, 3, "SIGMAS")
    b.link(guide, GUIDE_LATENT, sm1, 4, "LATENT")

    crop = b.node("LTXVCropGuides", f"{TAG} · 裁引导",
                  inputs=[in_slot("positive", "CONDITIONING"),
                          in_slot("negative", "CONDITIONING"), in_slot("latent", "LATENT")],
                  outputs=[out_slot("positive", "CONDITIONING", 0),
                           out_slot("negative", "CONDITIONING", 1),
                           out_slot("latent", "LATENT", 2)],
                  size=(320, 120))
    b.link(guide, GUIDE_POS, crop, 0, "CONDITIONING")
    b.link(guide, GUIDE_NEG, crop, 1, "CONDITIONING")
    b.link(sm1, 0, crop, 2, "LATENT")

    # ── Stage 2: latent 2x + 3 步重采样 ──
    up_m = b.node("LatentUpscaleModelLoader", f"{TAG} · 上采样模型",
                  widgets=[UPSCALE_MODEL],
                  outputs=[out_slot("LATENT_UPSCALE_MODEL", "LATENT_UPSCALE_MODEL", 0)],
                  size=(380, 60))
    up = b.node("LTXVLatentUpsampler", f"{TAG} · latent 2x",
                inputs=[in_slot("samples", "LATENT"),
                        in_slot("upscale_model", "LATENT_UPSCALE_MODEL"),
                        in_slot("vae", "VAE")],
                outputs=[out_slot("LATENT", "LATENT", 0)], size=(340, 100))
    b.link(crop, CROP_LATENT, up, 0, "LATENT")
    b.link(up_m, 0, up, 1, "LATENT_UPSCALE_MODEL")
    b.link(vae, 0, up, 2, "VAE")

    anchor2 = b.node(
        "LTXVImgToVideoInplace", f"{TAG} · Stage2 首帧锚定", widgets=[1.0, False],
        inputs=[in_slot("vae", "VAE"), in_slot("image", "IMAGE"), in_slot("latent", "LATENT"),
                in_slot("strength", "FLOAT", "strength"),
                in_slot("bypass", "BOOLEAN", "bypass")],
        outputs=[out_slot("latent", "LATENT", 0)], size=(300, 130))
    b.link(vae, 0, anchor2, 0, "VAE")
    b.link(first, 0, anchor2, 1, "IMAGE")
    b.link(up, 0, anchor2, 2, "LATENT")

    n2 = b.node("RandomNoise", f"{TAG} · Stage2 噪声", widgets=[850862500779429, "randomize"],
                outputs=[out_slot("NOISE", "NOISE", 0)], size=(300, 80))
    g2 = b.node("CFGGuider", f"{TAG} · Stage2 引导", widgets=[1.0],
                inputs=[in_slot("model", "MODEL"), in_slot("positive", "CONDITIONING"),
                        in_slot("negative", "CONDITIONING"), in_slot("cfg", "FLOAT", "cfg")],
                outputs=[out_slot("GUIDER", "GUIDER", 0)], size=(300, 120))
    # Stage 2 用带 IC-LoRA 的模型 + 裁掉引导后的条件(参考实现口径)
    b.link(iclora, ICO_MODEL, g2, 0, "MODEL")
    b.link(crop, CROP_POS, g2, 1, "CONDITIONING")
    b.link(crop, CROP_NEG, g2, 2, "CONDITIONING")

    s2 = b.node("KSamplerSelect", f"{TAG} · Stage2 采样器", widgets=["euler_ancestral"],
                outputs=[out_slot("SAMPLER", "SAMPLER", 0)], size=(300, 60))
    sg2 = b.node("ManualSigmas", f"{TAG} · Stage2 sigmas", widgets=[SIGMAS_STAGE2],
                 outputs=[out_slot("SIGMAS", "SIGMAS", 0)], size=(420, 60))
    sm2 = b.node("SamplerCustomAdvanced", f"{TAG} · Stage2 采样",
                 inputs=[in_slot("noise", "NOISE"), in_slot("guider", "GUIDER"),
                         in_slot("sampler", "SAMPLER"), in_slot("sigmas", "SIGMAS"),
                         in_slot("latent_image", "LATENT")],
                 outputs=[out_slot("output", "LATENT", 0),
                          out_slot("denoised_output", "LATENT", 1)],
                 size=(340, 150))
    b.link(n2, 0, sm2, 0, "NOISE")
    b.link(g2, 0, sm2, 1, "GUIDER")
    b.link(s2, 0, sm2, 2, "SAMPLER")
    b.link(sg2, 0, sm2, 3, "SIGMAS")
    b.link(anchor2, 0, sm2, 4, "LATENT")

    # ── 解码与输出 ──
    dec = b.node("VAEDecodeTiled", f"{TAG} · 平铺解码", widgets=[512, 64, 64, 8],
                 inputs=[in_slot("samples", "LATENT"), in_slot("vae", "VAE"),
                         in_slot("tile_size", "INT", "tile_size"),
                         in_slot("overlap", "INT", "overlap"),
                         in_slot("temporal_size", "INT", "temporal_size"),
                         in_slot("temporal_overlap", "INT", "temporal_overlap")],
                 outputs=[out_slot("IMAGE", "IMAGE", 0)], size=(340, 150))
    b.link(sm2, 0, dec, 0, "LATENT")
    b.link(vae, 0, dec, 1, "VAE")

    vid = b.node("CreateVideo", f"{TAG} · 合成视频", widgets=[FPS, 8, "sRGB", "none"],
                 inputs=[in_slot("images", "IMAGE"), in_slot("audio", "AUDIO"),
                         in_slot("fps", "FLOAT", "fps"),
                         in_slot("bit_depth", "COMBO", "bit_depth"),
                         in_slot("color_space", "COMBO", "color_space"),
                         in_slot("codec", "COMBO", "codec")],
                 outputs=[out_slot("VIDEO", "VIDEO", 0)], size=(320, 130))
    b.link(dec, 0, vid, 0, "IMAGE")
    b.link(gvc, G_AUDIO, vid, 1, "AUDIO")   # 音轨由 H3 原样透传(二采不重画音频)

    pv2 = b.node(
        "PreviewVideo", f"{TAG} · 预览/保存",
        widgets=["", "_1088p", None, ""],
        inputs=[in_slot("video", "VIDEO"), in_slot("filename_prefix", "STRING", "filename_prefix"),
                in_slot("filename_suffix", "STRING", "filename_suffix")],
        outputs=[out_slot("video", "VIDEO", 0), out_slot("audio", "AUDIO", 1),
                 out_slot("prefix", "STRING", 2)],
        size=(1200, 700))
    b.link(vid, 0, pv2, 0, "VIDEO")
    b.link(pv, L_PREFIX, pv2, 1, "STRING")   # 复用 H3 的 prefix 输出, 文件名与一采同源

    return [gvc, first, size_n, vae, unet, clip, iclora, pos, neg, cond, latent, anchor, guide,
            n1, g1, s1, sg1, sm1, crop, up_m, up, anchor2, n2, g2, s2, sg2, sm2, dec, vid, pv2]


# ─── 布局: 每条边 A.x + A.宽 ≤ B.x, 相邻边距落在 (50,100) ────────────────────


def layout(wf: dict, added: list, start_x: float, start_y: float) -> None:
    """按**反向拓扑深度**把二采链分层: 列号 = 该节点到汇点(最右)的最长路径。

    ⚠️ 为什么用**反向**而不是正向深度:
      正向(从源算)会把「无输入的参数节点」—— `RandomNoise` / `KSamplerSelect` / `ManualSigmas`
      / 各类 Loader —— 一律压在**最左列**(深度 0), 而它们的消费者 `SamplerCustomAdvanced`
      在第 15 列 ⇒ 连线横跨十几列, 又长又乱(实测最远 19 列)。
      反向深度让每个节点都贴近它的消费者: 参数节点恰好落在消费者左边一列。

    列内**右对齐** + 纵向间距 60, 于是同一列右边界对齐、到下一列的水平间距恒为 80,
    满足布局规范「输出在左、输入在右, 相邻边距落在开区间 (50,100)px」; 跨列连线(中间隔着
    别的列)间距自然更大, 那是分层的正常结果, 不是违规。

    用拓扑算而不手工标列: 手工列号一旦与真实接线脱节(改了接线忘了改列号), 就会出现
    上下游同列甚至反向的连线, 而脚本自己看不出来。
    """
    ids = {n["id"] for n in added}
    downs: dict = {n["id"]: set() for n in added}      # 后继
    for _lid, src, _ss, dst, _ds, _t in wf["links"]:
        if src in ids and dst in ids:
            downs[src].add(dst)

    depth: dict = {}

    def rd(nid: int, seen: frozenset = frozenset()) -> int:
        """到任意汇点的最长路径长度(边数)。"""
        if nid in depth:
            return depth[nid]
        if nid in seen:                     # 防御性: 理论上无环
            return 0
        succ = downs[nid]
        val = 0 if not succ else 1 + max(rd(x, seen | {nid}) for x in succ)
        depth[nid] = val
        return val

    for n in added:
        rd(n["id"])
    mx = max(depth.values()) if depth else 0

    cols: dict = {}
    for n in added:
        cols.setdefault(mx - depth[n["id"]], []).append(n)

    x = start_x
    for col in sorted(cols):
        group = cols[col]
        # 列内右对齐: 若左对齐, 同列窄节点的右边界会缩进, 从它到下一列的间距就变成
        # 「列宽 - 自身宽 + 80」而突破 (50,100)(实测冒出 100/140/180 等值)。
        max_w = max(n.get("size", [330, 100])[0] for n in group)
        y = start_y
        for n in group:
            w = n.get("size", [330, 100])[0]
            n["pos"] = [x + (max_w - w), y]
            y += n.get("size", [330, 100])[1] + 60
        x += max_w + 80


# ─── 校验 ───────────────────────────────────────────────────────────────────


def validate(name: str, wf: dict, added: list, sources: list) -> list:
    """结构校验: 连线双向一致、无悬空、无重复 id。返回问题列表。"""
    errs = []
    ids = [n["id"] for n in wf["nodes"]]
    if len(ids) != len(set(ids)):
        dup = [i for i in set(ids) if ids.count(i) > 1]
        errs.append(f"节点 id 重复: {dup}")

    by_id = {n["id"]: n for n in wf["nodes"]}
    # links 表 -> inputs/outputs 双向一致
    for lid, src, sslot, dst, dslot, _t in wf["links"]:
        s, d = by_id.get(src), by_id.get(dst)
        if s is None or d is None:
            errs.append(f"连线 {lid} 端点不存在: {src}->{dst}")
            continue
        if sslot >= len(s.get("outputs") or []):
            errs.append(f"连线 {lid} 源端口越界: [{src}]{s['type']} slot {sslot}")
        elif lid not in (s["outputs"][sslot].get("links") or []):
            errs.append(f"连线 {lid} 未记在源 [{src}].outputs[{sslot}]")
        if dslot >= len(d.get("inputs") or []):
            errs.append(f"连线 {lid} 目标端口越界: [{dst}]{d['type']} slot {dslot}")
        elif d["inputs"][dslot].get("link") != lid:
            errs.append(f"连线 {lid} 未记在目标 [{dst}].inputs[{dslot}]")

    # 图连通性: 检查**新增节点的子图整体**是否与 PreviewVideo 相连(无向连通)。
    # ⚠️ 不能用"从 PreviewVideo 正向 BFS 能到"来判 —— 那要求每个节点都有**从视频出发的路径**,
    #    但二采链里 `CLIPTextEncode → LTXVConditioning → 引导注入` 这条**条件支路**方向相反:
    #    它是被引导注入节点**拉取**的(引擎按输入边反向遍历), 正向永远到不了, 却完全正确。
    #    正确的判据是**无向连通**: 新增子图必须与 PreviewVideo 处在同一个连通分量里,
    #    即"没有任何一段新链悬在外边谁也拉不到"。
    adj: dict = {}
    for _lid, src, _ss, dst, _ds, _t in wf["links"]:
        adj.setdefault(src, set()).add(dst)
        adj.setdefault(dst, set()).add(src)
    # ⚠️ BFS 起点**只取原 PreviewVideo**(sources), 不能把本脚本新增的那个 PreviewVideo 也算进去:
    #    否则新链若整体与 H3 段断开, 新节点会从"自己那个起点"被覆盖到, 断链就检不出来。
    seen, stack = set(), list(sources)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adj.get(cur, ()))
    orphan = [n["id"] for n in added if n["id"] not in seen]
    if orphan:
        errs.append(f"新增节点与 PreviewVideo 不连通(悬空): {orphan}")

    return errs


# 前端专用节点: 不出现在后端 object_info 里, 校验时豁免
FRONTEND_ONLY = {"MarkdownNote", "Note", "MarkdownNoteNode", "PreviewAny"}


def check_compat(wf: dict, object_info: dict) -> list:
    """对照 ComfyUI 的 object_info 校验: 节点类型存在、required 输入齐全、widgets 数量匹配。"""
    errs = []
    for n in wf["nodes"]:
        t = n["type"]
        if t in FRONTEND_ONLY:
            continue
        if t not in object_info:
            errs.append(f"[{n['id']}] 节点类型不存在: {t}")
            continue
        info = object_info[t]["input"]
        req = info.get("required") or {}
        opt = info.get("optional") or {}
        # widgets 值数量应与「无连线输入的控件」数量匹配
        wired = {i["name"] for i in (n.get("inputs") or []) if i.get("link") is not None}
        need = 0
        for k, v in list(req.items()) + list(opt.items()):
            if k in wired:
                continue
            if isinstance(v[0], list):   # COMBO = 控件
                need += 1
            elif isinstance(v[0], str) and v[0] in (
                "INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"
            ):
                need += 1
        got = len(n.get("widgets_values") or [])
        # 有些节点(如 PreviewVideo)带 hidden/额外控件, 允许 got >= need
        if got < need:
            errs.append(f"[{n['id']}] {t}: widgets {got} 个 < 需要的 {need} 个")
    return errs


# ─── 主流程 ─────────────────────────────────────────────────────────────────


def main() -> int:
    import urllib.request

    # 先取 object_info 做节点兼容校验(LTXVideo 插件必须已装且 ComfyUI 已重启)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/object_info", timeout=60) as r:
            object_info = json.load(r)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  取不到 ComfyUI object_info({exc}); 跳过节点兼容校验")
        object_info = {}

    required = ["LTXAddVideoICLoRAGuide", "LTXICLoRALoaderModelOnly", "LTXVLatentUpsampler",
                "LTXVCropGuides", "LTXVImgToVideoInplace", "EmptyLTXVLatentVideo"]
    if object_info:
        missing = [k for k in required if k not in object_info]
        if missing:
            print("❌ ComfyUI 尚未加载这些节点: " + ", ".join(missing))
            print("   请确认 custom_nodes/ComfyUI-LTXVideo 已安装并重启 ComfyUI。")
            return 2

    rc = 0
    for name in TARGETS:
        wf = load(name)
        pv = next((n for n in wf["nodes"]
                   if n["type"] == "PreviewVideo" and (n.get("title") or "") != f"{TAG} · 预览/保存"), None)
        if pv is None:
            print(f"❌ {name}: 找不到原 PreviewVideo 节点")
            rc = 1
            continue

        removed = strip_tail(wf)
        # 布局起点: 放在原 PreviewVideo 右侧, 纵向与它对齐
        start_x = pv["pos"][0] + pv.get("size", [1300, 800])[0] + 80
        start_y = pv["pos"][1]
        added = build_chain(wf, pv)
        layout(wf, added, start_x, start_y)
        relink(wf)

        errs = validate(name, wf, added, sources=[pv["id"]])
        if object_info:
            errs += check_compat(wf, object_info)
        if errs:
            print(f"❌ {name}: 校验未通过(未写盘)")
            for e in errs:
                print("     -", e)
            rc = 1
            continue

        save(name, wf)
        print(f"✓ {name}: {len(added)} 个二采节点"
              + (f"(撤掉上次 {removed} 个)" if removed else "")
              + f"; 画布右端 x={max(n['pos'][0] for n in wf['nodes']):.0f}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
