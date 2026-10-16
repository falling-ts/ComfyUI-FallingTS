# -*- coding: utf-8 -*-
"""H3 工作流「高阶技能」改造脚本(幂等)。

## 做什么

给 11 个 H3 工作流接上三类高阶技能, 每一项都可切换/可旁路:

### 技能一: 去油(塑料感)

在 MODEL 链的**公共分叉点** `MiniMaxH3MemoryEfficientSageAttentionPatch` 之后插入两个
LoRA 与一个开关:

    Sage 注意力补丁 ─┬─→ FallingTSSwitch(去油开关) ─┬─(关)→ 原样透传 ─┐
                     │                              └─(开)→ 去油LoRA ─┤
                     │                                                ├→ (原有全部 MODEL 消费者:
                     └────────────────────────────────────────────────┘   LowVRAMAttention / EasyCache /
                                                                          turbo 4step / turbo 8step …)

- `h3-realism-people-t2v-i2v-r2v` @0.8 —— 真实感, 触发词 `r34l1sm`
- `Minimax-H3真实电影质感V0.1-解决张量报错` @0.3 —— 电影质感
- 触发词由 `StringConcatenate` 拼在 prompt 最前面。

⚠️ **为什么分叉点取 Sage 而不是 `MiniMaxLowVRAMAttention`**: 各工作流的 MODEL 链形状不同 ——
0013/0014/0031/…/0044 是 `Sage → LowVRAMAttention → {turbo 4step, turbo 8step}`; 而
**0030/0043 根本没有 LowVRAMAttention**, 是 `Sage → {EasyCache(20步档), turbo 4step, turbo 8step}`。
唯一对所有工作流都成立的公共分叉点就是 Sage 补丁(注意力补丁必须贴在最原始权重上, 必然
在 turbo LoRA 之前)。把 Sage 的**全部** MODEL 消费者改接到开关, 于是无论下游是什么都统一生效。

⚠️ **触发词只与 LoRA 同时有意义**: 脚本让两者随去油开关一起默认启用; 若把开关关掉, 建议
同时清空「H3高阶 · 触发词 r34l1sm」节点的值(残留时只是多一个无意义 token, 不会出错)。

### 技能二: 完美中文

脚本能做的只有一件事: 把 `r34l1sm` 触发词拼进 prompt(见上)。

> ⚠️ **中文规范的绝大部分无法由脚本代劳** —— 六段段名/`<Subject N>`/`[Shot N]`/时间戳/
> 枚举值必须英文、中文只允许出现在 `<d>…</d>` 与画面可见文字, 这些都写在 md 数据表的
> 提示词正文里, 需要人按契约写提示词。
> 详见 `docs/MiniMax-H3-高阶技能改造方案-2026-10-16.md` §3。
> (`MarkdownNote` 类节点在本机 2979 个节点里**未注册**, 故脚本不往图里塞提示牌。)

### 技能三: 远景小人物崩脸(H3 latent 二采提 token)

在**一采采样器之后**接一条 H3 原生两段式链(照官方 `example_workflows/minimax_h3_*_two_pass_upscale.json`)。

⚠️ **各工作流分两条路径**(实测发现的关键差异, 见 `has_audio()`):

**带音频**(0040–0044, 有 `VAEDecodeAudio` + audio VAE):

    一采 SamplerCustomAdvanced → LTXVSeparateAVLatent ─┬─ video → MiniMaxH3LatentUpscale ─┐
                                                        └─ audio ──────────────────────┐ │
    一采 conditioning → MiniMaxH3ConditioningUpscale(同 scale) → BasicGuider(二采)      │ │
    ManualSigmas(二采) → MiniMaxH3AddNoise(video) ←───────────────────────────────────────┘ │
                       └→ MiniMaxH3ShiftSigmas → MiniMaxH3AddNoise(audio) ←─────────────────┘
                                                        ↓
                                        LTXVConcatAVLatent → SamplerCustomAdvanced(二采)
                                                        ↓
                                        独立的 VAEDecode / VAEDecodeAudio → CreateVideo → 二采预览

**纯视频**(0013/0014/0030/0031/0032/0033, 无 audio VAE):

    一采 SamplerCustomAdvanced → MiniMaxH3LatentUpscale → MiniMaxH3AddNoise(video)
       → SamplerCustomAdvanced(二采) → 独立的 VAEDecode → CreateVideo → 二采预览

纯视频工作流的 latent 里没有音频分量, **不能**接 `LTXVSeparateAVLatent`(那条路要求联合
AV latent)。

**二采自己解码、自己出一个预览节点, 一采的 PreviewVideo 原样保留** —— 画布上同时有两个
产物可直接对比; 而且**不切断**原有下游(0030/0033 的截帧链仍吃一采的帧, 行为完全不变)。

**scale_by 随尺寸档位联动**: `FallingTSSelector` 的 `total` 从 2 扩到 3, 新增一组
`scale_by`。480p→1.6、544p→1.4、768p→1.0, 三个值都精确落在 H3 原生 1344×768
(= `MAX_PIXELS`)。前端增删只动尾部 ⇒ 已有连线槽位不漂移。

## 三个源码级坑(必须遵守, 否则静默坏掉)

1. **必须用 `MiniMaxH3AddNoise`**, 不能用原生 `AddNoise`: H3 是 CONST flow 模型,
   标准 AddNoise 的输出会在二采内部再被 `(1-sigma)` 缩放一次 ⇒ 输出近纯噪声。
2. **音频支路必须走 `MiniMaxH3ShiftSigmas`**: DiT 内部音频跑自己的 shift(3.0),
   用原始视频 sigma 给音频加噪 = 音频失真。shift 值**从工作流现读**, 不硬编码。
3. **`MiniMaxH3ConditioningUpscale` 的 scale 必须与 `MiniMaxH3LatentUpscale` 完全相同**:
   不同 ⇒ `minimax_refs`/`minimax_keyframes` 的 token 尺度与 RoPE 行布局错位, 不报错但画面错。

## 幂等

⚠️ **本脚本不是「改当前文件」而是「从基线重建」** —— 每次运行都从 `backups/` 里那份
`backup-<工作流>-<日期>-H3高阶技能改造前.json` 基线读入, 重新拼装后覆盖 `workflows/`。

为什么必须这样: 技能一是把 **Sage 注意力补丁原有的 MODEL 消费者改接到开关** —— 一改,
原有连线就从 `links` 表里消失了。按标题前缀 strip 掉新增节点**恢复不了那条连线**
(它是原地改接, 不是尾部追加)。于是第二次跑会看到一棵「半改造」的图, 结果不幂等。

所以设计上只认一个输入源(基线), 输出完全确定 —— 重跑任意多次结果逐字节一致,
也不需要在重跑时先手工还原。基线缺失时脚本直接报错退出, 绝不静默就地改造。

跑法(工作区根): python custom_nodes/ComfyUI-FallingTS/dev/build-h3-advanced-workflows.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent.parent
WF_DIR = ROOT / "workflows"
BACKUP_DIR = ROOT / "backups"
BASELINE_DATE = "20261016"

# ─── 要改造的目标工作流 ─────────────────────────────────────────────────────

TARGETS = [
    "0013_首图建模",
    "0014_参考建模",
    "0030_文生场景",
    "0031_首帧场景",
    "0032_参考场景",
    "0033_OrbitSheets场景",
    "0040_文生视频",
    "0041_首帧视频",
    "0042_首尾视频",
    "0043_关键帧视频",
    "0044_参考视频",
]

TAG = "H3高阶"
TITLE_PREFIX = TAG + " · "

# ─── 去油 LoRA(本机已验证存在) ──────────────────────────────────────────────
#
# ⚠️ 触发词 `r34l1sm` 由 h3-realism-people 官方模型卡规定, 必须放在提示词最前面。
#    它与 LoRA 由**同一个 switch** 驱动, 关掉 LoRA 时触发词也一并撤掉 —— 否则触发词会
#    变成无意义的 prompt token(它只在 LoRA 激活时有语义)。
LORA_REALISM = "h3-realism-people-t2v-i2v-r2v.safetensors"
LORA_REALISM_STRENGTH = 0.8          # 官方推荐 1.0; 本机主流 0.75-0.9, 取 0.8 兼顾动态
LORA_CINEMA = "Minimax-H3真实电影质感V0.1-解决张量报错.safetensors"
LORA_CINEMA_STRENGTH = 0.3           # 本机 17 个工作流主力 0.2/0.5, 取 0.3 偏保守
TRIGGER = "r34l1sm"

# ─── 二采尺寸联动 ───────────────────────────────────────────────────────────
#
# scale_by 随尺寸档位选择器的第三组给出。三个值都精确落在 H3 原生 1344x768:
#   832x480 → latent 52x30 → x1.6 = 83.2x48 → snap(2的倍数) 84x48 → 1344x768 ✓
#   960x544 → latent 60x34 → x1.4 = 84x47.6 → snap 84x48      → 1344x768 ✓
#   1344x768→ latent 84x48 → x1.0                              → 1344x768 ✓
SIZE_ITEMS = "默认,横1088,竖1088,横768,竖768,横544,竖544,横480,竖480"
SCALE_BY_SIZE = {
    "默认": 1.4,      # 随 md 表, 保守值(多数行的宽度/高度落在 544p 档)
    "横1088": 1.4,
    "竖1088": 1.4,
    "横768": 1.0,     # 已在最高档, 不提 token
    "竖768": 1.0,
    "横544": 1.4,
    "竖544": 1.4,
    "横480": 1.6,
    "竖480": 1.6,
}

# 二采 sigmas: 4 步、起点 0.55(本机共识 denoise 0.35 附近的中等强度)
SIGMAS_PASS2 = "0.55, 0.4000, 0.2200, 0.0000"

# H3 原生分辨率上限(与 ComfyUI nodes_minimax_h3.py 的 MAX_PIXELS 一致)
MAX_PIXELS = 768 * 1344


# ─── 基础工具 ───────────────────────────────────────────────────────────────


def baseline_path(name: str) -> Path:
    """改造前基线文件路径(幂等的唯一输入源)。"""
    return BACKUP_DIR / f"backup-{name}-{BASELINE_DATE}-H3高阶技能改造前.json"


def load(name: str) -> dict:
    """从**基线**读入, 而非从 `workflows/` 读当前文件 —— 见模块文档「幂等」一节。

    原地改接原有连线是擦除性的, 按标题 strip 掉新增节点恢复不了它, 所以重跑必须有一次
    干净的起点。基线由 `backup-workflows.py` 思路手工前置生成(已就位 11 份)。
    """
    p = baseline_path(name)
    if not p.is_file():
        raise FileNotFoundError(
            f"缺少改造前基线 {p.name} —— 本脚本从基线重建以保证幂等, 不会就地改造当前文件"
        )
    return json.loads(p.read_text(encoding="utf-8"))


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
    """删掉本脚本上次插入的节点与其连线。返回删除数。

    只作**兜底清理**用: 正常路径下 `load()` 已从基线读入, 图上不可能有上次的残留。
    保留它是为了万一有人拿一份改造过的图直接喂进来时能自愈 —— 但它**恢复不了**被
    `build_deoil` 原地改接掉的 Sage → 消费者的 MODEL 连线(见模块文档「幂等」)。

    识别靠**标题前缀** —— 本脚本新建的每个节点标题都带它, 而工作流原有节点都不会以它为
    前缀, 因此不会误删; 也无需在增删节点时同步维护任何白名单。
    """
    doomed = {
        n["id"]
        for n in wf["nodes"]
        if (n.get("title") or "").startswith(TITLE_PREFIX)
    }
    if not doomed:
        return 0
    wf["links"] = [l for l in wf["links"] if l[1] not in doomed and l[3] not in doomed]
    wf["nodes"] = [n for n in wf["nodes"] if n["id"] not in doomed]
    return len(doomed)


def in_slot(name, dtype, widget=None, localized=None):
    """构造输入端口。

    ⚠️ `name` 必须是**节点定义里的英文原名**(引擎按 name 传 kwargs), `localized_name`
    才是前端显示的中文。写反了引擎取不到值 —— 而且**不会报错**。
    """
    s = {"name": name, "type": dtype, "link": None}
    if localized:
        s["localized_name"] = localized
    if widget:
        s["widget"] = {"name": widget}
    return s


def out_slot(name, dtype, slot_index=None, localized=None):
    """构造输出端口。

    ⚠️ `slot_index` 必须存在且与顺序一致: 前端 `relink`/加载时按它定位槽位, 缺了会让
    连到后面的槽位错位(实测 `MiniMaxH3ReferenceToVideo` 的 ref_images 就是这样)。
    """
    s = {"name": name, "type": dtype, "links": []}
    if localized:
        s["localized_name"] = localized
    if slot_index is not None:
        s["slot_index"] = slot_index
    return s


class Builder:
    """按顺序分配 id 与 link, 并维护 nodes/links。"""

    def __init__(self, wf: dict):
        self.wf = wf
        self.nid = next_id(wf)
        self.lid = next_link_id(wf)
        self.added: list = []

    def node(self, ntype: str, title: str, widgets=None, inputs=None, outputs=None,
             size=(330, 100)) -> dict:
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
        self.nid += 1
        self.wf["nodes"].append(n)
        self.added.append(n)
        return n

    def link(self, src: dict, src_slot: int, dst: dict, dst_slot: int, dtype: str) -> int:
        lid = self.lid
        self.lid += 1
        self.wf["links"].append([lid, src["id"], src_slot, dst["id"], dst_slot, dtype])
        return lid


def note(self_wf: dict, builder: Builder, title: str, text: str) -> dict:
    """加一块只读提示牌(Note)。前端按 `type: "Note"` 渲染成文本块, 不参与执行。"""
    n = builder.node("Note", title, widgets=[text], size=(520, 300))
    return n


# ─── 定位现有节点 ───────────────────────────────────────────────────────────


def find_first(wf: dict, ntype: str, pred=None) -> dict | None:
    for n in wf["nodes"]:
        if n["type"] == ntype and (pred is None or pred(n)):
            return n
    return None


def src_of(wf: dict, node: dict, slot_name: str):
    """返回 (源节点, 源端口号) 或 None。"""
    by = {n["id"]: n for n in wf["nodes"]}
    for inp in node.get("inputs") or []:
        if inp["name"] == slot_name and inp.get("link"):
            for l in wf["links"]:
                if l[0] == inp["link"]:
                    return by.get(l[1]), l[2], l[0]
    return None


def is_ltx(n: dict) -> bool:
    return (n.get("title") or "").startswith("LTX二采")


def find_pass1_sampler(wf: dict) -> dict | None:
    """一采采样器 = 标题不带 LTX二采 的 SamplerCustomAdvanced。"""
    return find_first(wf, "SamplerCustomAdvanced", lambda n: not is_ltx(n))


def find_size_selector(wf: dict) -> dict | None:
    """尺寸档位选择器 = 第一组输入端口有 9 个(9 个尺寸档)的 FallingTSSelector。

    ⚠️ **不能只认「widgets[0] 以 `默认,` 开头」**: 步数选择器的 items 是 `默认,8步,4步`,
    同样以「默认,」开头 ⇒ 0030/0031/0032/0033 都会误抓到步数选择器, 于是脚本去扩它的
    total, 把步数档扩成尺寸档(0031 因此报「Sage 没有 MODEL 消费者」这类看似无关的错)。
    可靠的判据是**第一组端口数 == len(SIZE_ITEMS 的档位数)**: 尺寸选择器固定 9 档 18 端口,
    步数选择器只有 3 档 6 端口。
    """
    want = len(SIZE_ITEMS.split(","))
    for n in wf["nodes"]:
        if n["type"] != "FallingTSSelector":
            continue
        inputs = n.get("inputs") or []
        named = [i for i in inputs if str(i.get("name", "")).startswith("input")]
        total = (n.get("widgets_values") or [None, None])[1]
        # 第一组端口数 = 总端口数 / 组数; 必须整除且等于档位数
        if not isinstance(total, int) or total < 1 or not named:
            continue
        if len(named) % total == 0 and len(named) // total == want:
            return n
    return None


def find_step_selector(wf: dict) -> dict | None:
    """步数档选择器 = widgets = ['默认,8步,4步', ...]。"""
    for n in wf["nodes"]:
        if n["type"] == "FallingTSSelector":
            w = n.get("widgets_values") or []
            if w and str(w[0]).startswith("默认,8步"):
                return n
    return None


def find_h3_node(wf: dict) -> dict | None:
    """一采的 H3 生成节点(ImageToVideo / ReferenceToVideo)。"""
    return (find_first(wf, "MiniMaxH3ImageToVideo")
            or find_first(wf, "MiniMaxH3ReferenceToVideo"))


def fork_point(wf: dict) -> dict | None:
    """4 步链 / 8 步链 / 20 步官方档三条支路的**公共分叉点**。

    ⚠️ 实测各工作流的 MODEL 链形状不同:
      - 0013/0014/0031/0032/0033/0040/0041/0042/0044: Sage → LowVRAMAttention → {4step, 8step, …}
      - 0030/0043:                                    Sage → {EasyCache(20步档), 4step, 8step}
    所以**不能**统一取 LowVRAMAttention(0030/0043 根本没有这个节点)。
    唯一对所有工作流都成立的公共分叉点就是 `MiniMaxH3MemoryEfficientSageAttentionPatch`:
    它一定在 turbo LoRA 之前(注意力补丁必须贴在最原始权重上)。
    """
    return find_first(wf, "MiniMaxH3MemoryEfficientSageAttentionPatch")


def shift_values(wf: dict) -> tuple[float, float]:
    """从工作流现读一采的 shift(video/audio), 不硬编码 —— 这是 LoRA 的训练配方。"""
    n = find_first(wf, "MiniMaxH3SigmaShift")
    if n and n.get("widgets_values"):
        w = n["widgets_values"]
        return float(w[0]), float(w[1])
    return 12.0, 3.0


# ─── 改造 1: 去油 LoRA + 触发词 ─────────────────────────────────────────────


def build_deoil(wf: dict, b: Builder) -> dict:
    """在公共分叉点(Sage 注意力补丁)之后插入去油链与开关。

    把 Sage 的**全部 MODEL 消费者**改接到开关输出 —— 于是无论下游是
    LowVRAMAttention、EasyCache 还是直接接 turbo LoRA, 去油都统一生效。
    """
    fork = fork_point(wf)
    if fork is None:
        raise RuntimeError("找不到 MODEL 链公共分叉点(MiniMaxH3MemoryEfficientSageAttentionPatch)")

    by = {n["id"]: n for n in wf["nodes"]}
    consumers = []
    for l in wf["links"]:
        if l[1] == fork["id"] and l[2] == 0 and l[5] == "MODEL":
            consumers.append((by.get(l[3]), l[4], l[0]))
    if not consumers:
        raise RuntimeError("Sage 注意力补丁没有 MODEL 消费者")

    # ── 开关: 关 = 原样透传, 开 = 经去油 LoRA ──
    # ⚠️ 端口名必须是 `false_1` / `true_1`(节点定义的英文原名), 不是中文 ——
    #    引擎按 name 传 kwargs, 写中文会让开关永远取到 None(且不报错)。
    sw = b.node(
        "FallingTSSwitch", f"{TITLE_PREFIX}去油开关",
        widgets=[True, 1],   # switch=True(默认开启去油)
        inputs=[in_slot("switch", "BOOLEAN", "switch", "开关"),
                in_slot("total", "INT", "total", "组数"),
                in_slot("false_1", "*", None, "为假时 1"),
                in_slot("true_1", "*", None, "为真时 1")],
        outputs=[out_slot("output_1", "*", 0, "输出 1")],
        size=(320, 150),
    )
    b.link(fork, 0, sw, 2, "MODEL")      # false_1 = 原样

    # ── 去油 LoRA 两级 ──
    lr = b.node(
        "LoraLoaderModelOnly", f"{TITLE_PREFIX}去油 · 真实感 {LORA_REALISM_STRENGTH}",
        widgets=[LORA_REALISM, LORA_REALISM_STRENGTH],
        inputs=[in_slot("model", "MODEL", None, "模型"),
                in_slot("lora_name", "COMBO", "lora_name", "LoRA 名称"),
                in_slot("strength_model", "FLOAT", "strength_model", "强度")],
        outputs=[out_slot("MODEL", "MODEL", 0, "模型")],
        size=(360, 100),
    )
    b.link(fork, 0, lr, 0, "MODEL")

    lc = b.node(
        "LoraLoaderModelOnly", f"{TITLE_PREFIX}去油 · 电影质感 {LORA_CINEMA_STRENGTH}",
        widgets=[LORA_CINEMA, LORA_CINEMA_STRENGTH],
        inputs=[in_slot("model", "MODEL", None, "模型"),
                in_slot("lora_name", "COMBO", "lora_name", "LoRA 名称"),
                in_slot("strength_model", "FLOAT", "strength_model", "强度")],
        outputs=[out_slot("MODEL", "MODEL", 0, "模型")],
        size=(360, 100),
    )
    b.link(lr, 0, lc, 0, "MODEL")
    b.link(lc, 0, sw, 3, "MODEL")        # true_1 = 去油后

    # ── 把 Sage 原本的 MODEL 消费者全部改接到开关输出 ──
    for cons, cons_slot, old_lid in consumers:
        if cons is None:
            continue
        wf["links"] = [l for l in wf["links"] if l[0] != old_lid]
        b.link(sw, 0, cons, cons_slot, "MODEL")

    return {"model_out": sw, "switch": sw, "fork": fork}


def prompt_injection_point(wf: dict) -> tuple[dict, int, dict, int, int] | None:
    """找到「提示词进入 H3」的注入点。

    返回 `(目标节点, prompt槽下标, 原来源节点, 原来源槽, 原linkId)`, 找不到返回 None。

    ⚠️ 各工作流的提示词入口不同:
      - 0013/0014/0030/0031/0032/0041/0042/0043/0044: H3 生成节点的 `prompt` 输入
      - 0033: `OrbitSheetsLocationPrompt` 喂 H3 的 `prompt`
      - 0040: 没有 H3 生成节点, 走 `CLIPTextEncode#20` 的 `text` 输入
    统一做法: 找「有 prompt/text 输入且已连线」的节点, 在其上游插拼接。
    """
    h3 = find_h3_node(wf)
    targets = []
    if h3 is not None:
        targets.append((h3, "prompt"))
    # 兜底: 找第一个 text 有连线的非 LTX CLIPTextEncode
    for n in wf["nodes"]:
        if n["type"] == "CLIPTextEncode" and not is_ltx(n):
            targets.append((n, "text"))

    for node, slot_name in targets:
        for idx, inp in enumerate(node.get("inputs") or []):
            if inp["name"] == slot_name and inp.get("link"):
                src = src_of(wf, node, slot_name)
                if src is None:
                    continue
                return (node, idx, src[0], src[1], src[2])
    return None


def build_trigger_word(wf: dict, b: Builder) -> dict | None:
    """把触发词 `r34l1sm` 拼进 H3 的提示词。

    ⚠️ 触发词的语义**只在去油 LoRA 激活时存在**。本脚本让它随去油 LoRA 一起默认启用;
    若把「去油开关」关掉, 建议同时把触发词常量节点的值清空(标题带 `H3高阶 ·` 前缀,
    在画布上直接改即可) —— 残留时只是多一个无意义 token, 不会出错。
    """
    spot = prompt_injection_point(wf)
    if spot is None:
        return None
    node, idx, orig, orig_slot, old_lid = spot

    trig = b.node(
        "PrimitiveString", f"{TITLE_PREFIX}触发词 {TRIGGER}",
        widgets=[TRIGGER + ", "],
        inputs=[in_slot("value", "STRING", "value", "文本")],
        outputs=[out_slot("STRING", "STRING", 0, "字符串")],
        size=(300, 90),
    )

    cat = b.node(
        "StringConcatenate", f"{TITLE_PREFIX}提示词 · 前置触发词",
        widgets=["", "", ""],
        inputs=[in_slot("string_a", "STRING", "string_a", "字符串 A"),
                in_slot("string_b", "STRING", "string_b", "字符串 B"),
                in_slot("delimiter", "STRING", "delimiter", "分隔符")],
        outputs=[out_slot("STRING", "STRING", 0, "字符串")],
        size=(340, 130),
    )
    b.link(trig, 0, cat, 0, "STRING")
    b.link(orig, orig_slot, cat, 1, "STRING")

    # 断开原连线, 改接拼接结果
    wf["links"] = [l for l in wf["links"] if l[0] != old_lid]
    b.link(cat, 0, node, idx, "STRING")

    return {"trigger": trig, "concat": cat}


# ─── 改造 2: H3 latent 二采(提 token) ───────────────────────────────────────


def build_pass2(wf: dict, b: Builder, size_sel: dict) -> dict | None:
    """在一采采样器之后接 H3 原生两段式链(提 token, 治远景崩脸)。

    设计取舍: **二采自己解码、自己出一个预览节点**, 一采的 PreviewVideo 原样保留。
    于是画布上同时有两个产物 —— 一采(原始)与二采(提 token 后), 可直接对比;
    而且**不切断**原有下游(0030/0033 的截帧链仍吃一采的帧, 行为完全不变)。
    """
    p1 = find_pass1_sampler(wf)
    if p1 is None:
        return None

    # 一采的 conditioning 与 model: 从 BasicGuider 的输入取
    gi = None
    for inp in p1.get("inputs") or []:
        if inp["name"] == "guider" and inp.get("link"):
            by = {n["id"]: n for n in wf["nodes"]}
            for l in wf["links"]:
                if l[0] == inp["link"]:
                    gi = by.get(l[1])
    if gi is None:
        return None
    cond_src = src_of(wf, gi, "conditioning")
    model_src = src_of(wf, gi, "model")
    if cond_src is None or model_src is None:
        return None

    sv, sa = shift_values(wf)

    # ── 扩展尺寸选择器: total 2 → 3, 新增 scale_by 组(只在尾部追加端口) ──
    items = SIZE_ITEMS.split(",")
    old_total = int(size_sel["widgets_values"][1])
    if old_total != 2:
        return None
    inputs = size_sel.setdefault("inputs", [])
    named = [i for i in inputs if str(i.get("name", "")).startswith("input")]
    if len(named) != len(items) * old_total:
        return None
    # ⚠️ 追加位置是**端口列表的实际长度**, 不是 inputN 的个数: `inputs` 前面还有
    #    `items`/`total`/`selection` 三个 widget 端口(共 3 个), 拿 inputN 计数当索引用
    #    会把新端口接到第 2 组末尾那 3 个已有端口上 —— 表现为原有连线被挤掉、新连线错位
    #    (实测 0030: in[18..20] 从第 2 组的 `竖544/横480/竖480` 被夺走)。
    append_at = len(inputs)

    scale_consts = {}
    for nm in items:
        c = b.node(
            "PrimitiveFloat",
            f"{TITLE_PREFIX}二采倍数 {nm} = {SCALE_BY_SIZE[nm]}",
            widgets=[SCALE_BY_SIZE[nm]],
            inputs=[in_slot("value", "FLOAT", "value", "数值")],
            outputs=[out_slot("FLOAT", "FLOAT", 0, "浮点数")],
            size=(340, 100),
        )
        scale_consts[nm] = c

    inputs.extend([in_slot(f"input{len(named) + i + 1}", "*", None, nm)
                   for i, nm in enumerate(items)])
    size_sel["widgets_values"] = [SIZE_ITEMS, old_total + 1, size_sel["widgets_values"][2]]
    for i, nm in enumerate(items):
        b.link(scale_consts[nm], 0, size_sel, append_at + i, "FLOAT")

    # ⚠️ selector 的输出端口也要从 2 组扩到 3 组: 缺 selected_value_3 时前端加载会把
    #    连到它的连线**静默丢掉**(端口不存在), 于是 scale_by 恒为 None。
    #    输出端口总数 = 2 个固定项(selected/index) + 组数
    outs = size_sel.setdefault("outputs", [])
    while len(outs) < 2 + old_total + 1:
        idx = len(outs)
        nm_out = ("selected", "index")[idx] if idx < 2 else f"selected_value_{idx - 1}"
        loc = "选中项" if idx == 0 else ("索引" if idx == 1 else f"选中值 {idx - 1}")
        outs.append(out_slot(nm_out, "STRING" if idx == 0 else ("INT" if idx == 1 else "*"),
                             idx, loc))

    # scale_by = 第 3 组输出 = selected_value_3 = 输出端口下标 4
    SCALE_OUT_SLOT = 4

    # ── 分离 AV latent(仅带音频的工作流) ──
    #
    # ⚠️ 纯视频工作流(0013/0014/0030/0031/0032/0033)的一采 latent **没有音频分量**,
    #    不能走 LTXVSeparateAVLatent —— 那条路要求联合 AV latent。这些直接对 latent
    #    做纯视频放大 + 纯视频加噪, 二采后仍用同一个 VAEDecode。
    audio = has_audio(wf)

    if audio:
        sep = b.node(
            "LTXVSeparateAVLatent", f"{TITLE_PREFIX}二采 · 分离AV latent",
            inputs=[in_slot("av_latent", "LATENT", None, "AV latent")],
            outputs=[out_slot("video_latent", "LATENT", 0, "视频 latent"),
                     out_slot("audio_latent", "LATENT", 1, "音频 latent")],
            size=(320, 100),
        )
        b.link(p1, 0, sep, 0, "LATENT")
        vid_latent_src = (sep, 0)
    else:
        vid_latent_src = (p1, 0)

    # ── video latent 放大 ──
    up = b.node(
        "MiniMaxH3LatentUpscale", f"{TITLE_PREFIX}二采 · video latent ×scale",
        widgets=[1.4, "bilinear"],
        inputs=[in_slot("samples", "LATENT", None, "latent"),
                in_slot("scale_by", "FLOAT", "scale_by", "放大倍数"),
                in_slot("upscale_method", "COMBO", "upscale_method", "插值方法")],
        outputs=[out_slot("LATENT", "LATENT", 0, "LATENT")],
        size=(340, 120),
    )
    b.link(vid_latent_src[0], vid_latent_src[1], up, 0, "LATENT")
    b.link(size_sel, SCALE_OUT_SLOT, up, 1, "FLOAT")

    # ── conditioning 同步放大(必须与 latent 同 scale) ──
    csrc, cslot, _cl = cond_src
    cup = b.node(
        "MiniMaxH3ConditioningUpscale", f"{TITLE_PREFIX}二采 · conditioning ×scale",
        widgets=[1.4, "bilinear"],
        inputs=[in_slot("conditioning", "CONDITIONING", None, "CONDITIONING"),
                in_slot("scale_by", "FLOAT", "scale_by", "放大倍数"),
                in_slot("upscale_method", "COMBO", "upscale_method", "插值方法")],
        outputs=[out_slot("CONDITIONING", "CONDITIONING", 0, "CONDITIONING")],
        size=(360, 120),
    )
    b.link(csrc, cslot, cup, 0, "CONDITIONING")
    b.link(size_sel, SCALE_OUT_SLOT, cup, 1, "FLOAT")

    msrc, mslot, _ml = model_src

    # ── sigmas ──
    sg = b.node(
        "ManualSigmas", f"{TITLE_PREFIX}二采 · sigmas (4步)",
        widgets=[SIGMAS_PASS2],
        inputs=[in_slot("sigmas", "STRING", "sigmas", "sigmas")],
        outputs=[out_slot("SIGMAS", "SIGMAS", 0, "SIGMAS")],
        size=(360, 90),
    )

    nz = b.node(
        "RandomNoise", f"{TITLE_PREFIX}二采 · 噪声",
        widgets=[12345, "fixed"],
        outputs=[out_slot("NOISE", "NOISE", 0, "NOISE")],
        size=(300, 80),
    )

    # ── video 支路加噪(必须用 MiniMaxH3AddNoise) ──
    nz_v = b.node(
        "MiniMaxH3AddNoise", f"{TITLE_PREFIX}二采 · 加噪 video",
        inputs=[in_slot("model", "MODEL", None, "模型"),
                in_slot("noise", "NOISE", None, "噪声"),
                in_slot("sigmas", "SIGMAS", None, "sigmas"),
                in_slot("latent_image", "LATENT", None, "latent")],
        outputs=[out_slot("LATENT", "LATENT", 0, "LATENT")],
        size=(340, 130),
    )
    b.link(msrc, mslot, nz_v, 0, "MODEL")
    b.link(nz, 0, nz_v, 1, "NOISE")
    b.link(sg, 0, nz_v, 2, "SIGMAS")
    b.link(up, 0, nz_v, 3, "LATENT")

    # ── 音频支路: sigmas 必须过 ShiftSigmas(否则音频失真) ──
    #
    # 仅带音频的工作流需要: 音频 latent 单独加噪、单独对齐 shift, 再与视频 latent 合并。
    if audio:
        sh = b.node(
            "MiniMaxH3ShiftSigmas", f"{TITLE_PREFIX}二采 · 音频sigma对齐 ({sv:g}/{sa:g})",
            widgets=[sv, sa],
            inputs=[in_slot("sigmas", "SIGMAS", None, "sigmas"),
                    in_slot("shift_video", "FLOAT", "shift_video", "视频 shift"),
                    in_slot("shift_audio", "FLOAT", "shift_audio", "音频 shift")],
            outputs=[out_slot("SIGMAS", "SIGMAS", 0, "SIGMAS")],
            size=(380, 120),
        )
        b.link(sg, 0, sh, 0, "SIGMAS")

        nz_a = b.node(
            "MiniMaxH3AddNoise", f"{TITLE_PREFIX}二采 · 加噪 audio",
            inputs=[in_slot("model", "MODEL", None, "模型"),
                    in_slot("noise", "NOISE", None, "噪声"),
                    in_slot("sigmas", "SIGMAS", None, "sigmas"),
                    in_slot("latent_image", "LATENT", None, "latent")],
            outputs=[out_slot("LATENT", "LATENT", 0, "LATENT")],
            size=(340, 130),
        )
        b.link(msrc, mslot, nz_a, 0, "MODEL")
        b.link(nz, 0, nz_a, 1, "NOISE")
        b.link(sh, 0, nz_a, 2, "SIGMAS")
        b.link(sep, 1, nz_a, 3, "LATENT")

        cat = b.node(
            "LTXVConcatAVLatent", f"{TITLE_PREFIX}二采 · 合并AV latent",
            inputs=[in_slot("video_latent", "LATENT", None, "视频 latent"),
                    in_slot("audio_latent", "LATENT", None, "音频 latent")],
            outputs=[out_slot("LATENT", "LATENT", 0, "LATENT")],
            size=(320, 100),
        )
        b.link(nz_v, 0, cat, 0, "LATENT")
        b.link(nz_a, 0, cat, 1, "LATENT")
        latent_in = cat
    else:
        # 纯视频: 加噪后的 latent 直接进二采采样器, 不经 AV 合并。
        latent_in = nz_v

    g2 = b.node(
        "BasicGuider", f"{TITLE_PREFIX}二采 · guider",
        inputs=[in_slot("model", "MODEL", None, "模型"),
                in_slot("conditioning", "CONDITIONING", None, "条件")],
        outputs=[out_slot("GUIDER", "GUIDER", 0, "引导")],
        size=(320, 100),
    )
    b.link(msrc, mslot, g2, 0, "MODEL")
    b.link(cup, 0, g2, 1, "CONDITIONING")

    k2 = b.node(
        "KSamplerSelect", f"{TITLE_PREFIX}二采 · 采样器",
        widgets=["euler"],
        outputs=[out_slot("SAMPLER", "SAMPLER", 0, "采样器")],
        size=(300, 60),
    )
    dn = b.node("DisableNoise", f"{TITLE_PREFIX}二采 · 禁用噪声",
                outputs=[out_slot("NOISE", "NOISE", 0, "NOISE")], size=(300, 60))

    sm2 = b.node(
        "SamplerCustomAdvanced", f"{TITLE_PREFIX}二采 · 采样",
        inputs=[in_slot("noise", "NOISE", None, "噪声"),
                in_slot("guider", "GUIDER", None, "引导"),
                in_slot("sampler", "SAMPLER", None, "采样器"),
                in_slot("sigmas", "SIGMAS", None, "sigmas"),
                in_slot("latent_image", "LATENT", None, "latent")],
        outputs=[out_slot("output", "LATENT", 0, "输出"),
                 out_slot("denoised_output", "LATENT", 1, "去噪输出")],
        size=(340, 150),
    )
    b.link(dn, 0, sm2, 0, "NOISE")
    b.link(g2, 0, sm2, 1, "GUIDER")
    b.link(k2, 0, sm2, 2, "SAMPLER")
    b.link(sg, 0, sm2, 3, "SIGMAS")
    b.link(latent_in, 0, sm2, 4, "LATENT")

    # ── 二采自己解码 ──
    src_dec_v = _find_decode(wf, "VAEDecode")
    vae_v = src_of(wf, src_dec_v, "vae") if src_dec_v else None
    if vae_v is None:
        return None
    if audio:
        src_dec_a = _find_decode(wf, "VAEDecodeAudio")
        vae_a = src_of(wf, src_dec_a, "vae") if src_dec_a else None
        if vae_a is None:
            return None

    dec = b.node(
        "VAEDecode", f"{TITLE_PREFIX}二采 · 解码(视频)",
        inputs=[in_slot("samples", "LATENT", None, "samples"),
                in_slot("vae", "VAE", None, "vae")],
        outputs=[out_slot("IMAGE", "IMAGE", 0, "图像")],
        size=(320, 100),
    )
    b.link(sm2, 0, dec, 0, "LATENT")
    b.link(vae_v[0], vae_v[1], dec, 1, "VAE")

    if audio:
        deca = b.node(
            "VAEDecodeAudio", f"{TITLE_PREFIX}二采 · 解码(音频)",
            inputs=[in_slot("samples", "LATENT", None, "samples"),
                    in_slot("vae", "VAE", None, "vae")],
            outputs=[out_slot("AUDIO", "AUDIO", 0, "音频")],
            size=(320, 100),
        )
        b.link(sm2, 0, deca, 0, "LATENT")
        b.link(vae_a[0], vae_a[1], deca, 1, "VAE")

    # ── 合成视频 + 预览(与一采并列, 便于对比) ──
    pv1 = find_first(wf, "PreviewVideo", lambda n: not is_ltx(n))
    fps = 24
    if pv1 is not None:
        w = pv1.get("widgets_values") or []
        for v in w:
            if isinstance(v, (int, float)) and 1 <= v <= 120:
                fps = int(v)
                break

    mk = b.node(
        "CreateVideo", f"{TITLE_PREFIX}二采 · 合成视频",
        # 纯视频流没有音轨 ⇒ codec 相应退到 h264(带音轨时上游用 none = 不重编码)
        widgets=[fps, 8, "sRGB", "none" if audio else "h264"],
        inputs=[in_slot("images", "IMAGE", None, "图像"),
                in_slot("audio", "AUDIO", None, "音频"),
                in_slot("fps", "FLOAT", "fps", "帧率"),
                in_slot("bit_depth", "COMBO", "bit_depth", "位深"),
                in_slot("color_space", "COMBO", "color_space", "色彩空间"),
                in_slot("codec", "COMBO", "codec", "编码")],
        outputs=[out_slot("VIDEO", "VIDEO", 0, "视频")],
        size=(320, 130),
    )
    b.link(dec, 0, mk, 0, "IMAGE")
    if audio:
        b.link(deca, 0, mk, 1, "AUDIO")

    pv2 = b.node(
        "PreviewVideo", f"{TITLE_PREFIX}二采 · 预览/保存",
        widgets=["", "_768p", None, ""],
        inputs=[in_slot("video", "VIDEO", None, "视频"),
                in_slot("filename_prefix", "STRING", "filename_prefix", "文件名前缀"),
                in_slot("filename_suffix", "STRING", "filename_suffix", "文件名后缀")],
        outputs=[out_slot("video", "VIDEO", 0, "视频"),
                 out_slot("audio", "AUDIO", 1, "音频"),
                 out_slot("prefix", "STRING", 2, "前缀")],
        size=(1200, 700),
    )
    b.link(mk, 0, pv2, 0, "VIDEO")
    if pv1 is not None and len(pv1.get("outputs") or []) > 2:
        b.link(pv1, 2, pv2, 1, "STRING")   # 复用一采 prefix, 文件名同源

    return {"sampler": sm2, "preview": pv2, "upscale": up, "cond_upscale": cup}


def _find_decode(wf: dict, ntype: str) -> dict | None:
    """找一采的解码节点(标题不带 LTX二采 / H3高阶 前缀)。"""
    for n in wf["nodes"]:
        if n["type"] == ntype:
            t = n.get("title") or ""
            if not t.startswith("H3高阶") and not is_ltx(n):
                return n
    return None


def has_audio(wf: dict) -> bool:
    """该工作流是否带音频分支。

    ⚠️ 实测本机 11 个工作流分两类:
      - **带音频**(0040/0041/0042/0043/0044): 有 `VAEDecodeAudio` 与 audio VAE,
        一采 latent 是**联合 AV latent**, 二采必须走 `LTXVSeparateAVLatent` /
        `MiniMaxH3ShiftSigmas` / `LTXVConcatAVLatent` 那条 AV 路径。
      - **纯视频**(0013/0014/0030/0031/0032/0033): 只有 `VAEDecode`, 没有 audio VAE,
        latent 里没有音频分量 —— 二采**不能**去接音频支路, 否则 `LTXVSeparateAVLatent`
        会拿不到音频而报错 / 产出坏数据。这些走纯视频路径。
    """
    return _find_decode(wf, "VAEDecodeAudio") is not None


# ─── 布局 ───────────────────────────────────────────────────────────────────


def layout(wf: dict, added: list, start_x: float, start_y: float) -> None:
    """按反向拓扑深度把新增节点分层。

    反向深度让每个节点贴近它的消费者(参数节点恰好落在消费者左边一列), 列内右对齐 +
    纵向间距 60, 满足「输出在左、输入在右, 相邻边距落在 (50,100)px」。
    """
    ids = {n["id"] for n in added}
    downs: dict = {n["id"]: set() for n in added}
    for _lid, src, _ss, dst, _ds, _t in wf["links"]:
        if src in ids and dst in ids:
            downs[src].add(dst)

    depth: dict = {}

    def rd(nid: int, seen: frozenset = frozenset()) -> int:
        if nid in depth:
            return depth[nid]
        if nid in seen:
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
        max_w = max(n.get("size", [330, 100])[0] for n in group)
        y = start_y
        for n in group:
            w = n.get("size", [330, 100])[0]
            n["pos"] = [x + (max_w - w), y]
            y += n.get("size", [330, 100])[1] + 60
        x += max_w + 80


# ─── 主流程 ─────────────────────────────────────────────────────────────────


def process(name: str) -> tuple[int, list]:
    wf = load(name)
    strip_tail(wf)
    b = Builder(wf)

    problems = []
    size_sel = find_size_selector(wf)
    if size_sel is None:
        problems.append("找不到尺寸档位选择器")
    if find_pass1_sampler(wf) is None:
        problems.append("找不到一采采样器")
    if fork_point(wf) is None:
        problems.append("找不到 MODEL 链公共分叉点(SageAttentionPatch)")
    if problems:
        return 0, problems

    # ── 技能一 + 技能二: 去油 LoRA 与前置触发词 ──
    try:
        build_deoil(wf, b)
    except RuntimeError as e:
        return 0, [f"去油链构建失败: {e}"]
    build_trigger_word(wf, b)

    # ── 技能三: H3 latent 二采提 token ──
    p2 = build_pass2(wf, b, size_sel)
    if p2 is None:
        return 0, ["二采构建失败(缺少 conditioning / model / 解码节点来源)"]

    relink(wf)
    # 新增节点整块摆到**所有原有节点的右侧**, 不写死 12000 —— 0040/0041/0042/0043/0044
    # 里已经有 LTX 二采链占据 12000 往右的一大片, 写死会与它成片重叠。
    old_right = max(
        (n["pos"][0] + n.get("size", [330, 100])[0]
         for n in wf["nodes"] if n["id"] not in {a["id"] for a in b.added}),
        default=0,
    )
    layout(wf, b.added, start_x=old_right + 200, start_y=40)

    # ── 校验: 每个档位的二采目标尺寸都不超 MAX_PIXELS ──
    BASE = {"横480": (832, 480), "竖480": (480, 832), "横544": (960, 544),
            "竖544": (544, 960), "横768": (1344, 768), "竖768": (768, 1344),
            "横1088": (960, 544), "竖1088": (544, 960)}
    for nm, sc in SCALE_BY_SIZE.items():
        base = BASE.get(nm)
        if not base:
            continue
        lat_h, lat_w = base[1] // 16, base[0] // 16
        th = max(2, ((int(round(lat_h * sc)) + 1) // 2) * 2)
        tw = max(2, ((int(round(lat_w * sc)) + 1) // 2) * 2)
        out_h, out_w = th * 16, tw * 16
        if out_h * out_w > MAX_PIXELS:
            problems.append(f"{nm} × {sc} → {out_w}x{out_h} 超 MAX_PIXELS({MAX_PIXELS})")

    wf["last_node_id"] = max(n["id"] for n in wf["nodes"])
    wf["last_link_id"] = max([l[0] for l in wf["links"]], default=0)
    save(name, wf)
    return len(b.added), problems


def main() -> int:
    total = 0
    bad = 0
    for name in TARGETS:
        n, problems = process(name)
        total += n
        if problems:
            bad += 1
            print(f"[!] {name}: 新增 {n} 节点, 问题: {problems}")
        else:
            print(f"[ok] {name}: 新增 {n} 节点")
    print(f"\n合计新增 {total} 节点; {bad} 个工作流有问题")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
