r"""Generate workflows/0034_世界模型.json (frontend format) + its API prompt, then self-validate.

用户要求: 0034 的输入必须走 **md 数据表**(FallingTSMarkDownTable), 不许硬编码 8 个 LoadImage.
本版(= 2026-09-27 三改, 只出一个最高质量 PLY)**把重建从 HYWM2 原生节点挪进了脚本**。

    FallingTSMarkDownTable(md_path = stories\七纹刻印\0034_世界模型.md)
      ├ 前面/前右/右面/后右/后面/后左/左面/前左 八个 IMAGE 列 → ImageBatchMulti.image_1..8
      └ 宽度/高度 与 偏航角/俯仰角/距离/目标深度/视场角 → 预留元数据(本版不输出图片视频, 也不建网格)
    唯一支路: ImageBatchMulti → **WorldRefinePLY**(自有插件 `ComfyUI-FallingTS\world-refine`)
      → HYWM2PLYAdvancedGaussianViewer   **全图唯一产物: 一个 3DGS `.ply`**

为什么不再用 HYWM2 原生节点(读源码确认, 不是偷懒):
  · `HYWM2Reconstruct` 先 `mm.load_models_gpu(...)` 把模型装进显存, **然后**才
    `mm.get_free_memory()` 算 token 预算(reconstruct.py:248 → :263) ⇒ 只能拿到 406;
    而 `custom_nodes\ComfyUI-FallingTS\world-refine\refine_0034_gs.py` 在装模型**之前**测空闲显存 ⇒ 拿到 **504**(高斯多 53%)。
    想让图内节点也吃到 504, 必须改 HYWM2 插件代码, 那是第三方, 本仓不动。
  · 于是把整条重建+精修交给 WorldRefinePLY: 它在主进程(主 venv)只做"落临时 PNG + 调隔离解释器
    + 转发结果", 真正的 504 前馈与外观精修在 `hywm2-nodes` 环境里跑(gsplat 只在那里)。
    这样图里**只有一次前馈**, 不会出现两个进程各装一份 WorldMirror 抢 8GB 显存。
  · 唯一产物同时是**质量最高**的那个: 504 前馈 + 尺度过滤(砍最大 2% 大雾团)+ 外观精修(PSNR +5.02dB)。

- md 表节点规格(读 `custom_nodes\ComfyUI-FallingTS\mdtable\nodes.py` 确认):
   · 输入只有一个控件 `data`(FALLINGTS_MD_TABLE), 值 = {md_path, fields, selected};
     序列化 `widgets_values = [那个 dict]`, API prompt `inputs["data"] = 那个 dict`;
   · **输出槽位 = 列序**: 槽 0 = ID, 槽 i = 第 i 列(面/ID 字段), 末槽 = 整行 JSON;
     IMAGE 列执行时按 `@{表文件名/ID}` 解析真实文件并加载为 IMAGE 张量(解析失败输出 None);
   · `@{0031_首帧场景/00001_书房旋镜前面}` 走**严格命中**: `output|input/0031_首帧场景/00001_书房旋镜前面.*`;
   · 节点声明 42 个输出槽, 前端加载时按 fields 数裁前 —— 序列化侧照官方旧版写满 42 槽。
- 全图零 output 写入: 没有任何 `Save*`/网格/图片/视频节点; 唯一的 3D 资产由 WorldRefinePLY
  落到宿主 output 目录的 `0034_世界模型\` 子目录(供 viewer 的 /view URL 使用), 中间图只进 `temp\`。
- 布局: 说明卡片独占最左列, **md 表独占第二列**(规则 3), 之后是数据流各列。
修改历史: 旧版「单图 → TripoSplat 物体级 3DGS」、「单图 → DA3 网格」、「DA3 网格支路并存」、
  「HYWM2 三导出支路」、「HYWM2 只留 PLY 导出」的快照曾放在
  `backups\backup-make-0034-*-20260927-*.py` 与 `backups\backup-0034_世界模型.json-20260927-*.json`,
  「三改」前的快照在 `backups\backup-*-20260927-去非PLY导出前.*` —— **这些快照已于 2026-09-30 随
  `backups\` 整体清空删除**(该目录此后只作修改前的临时暂存, 不留档), 旧版实现只能查 git 历史。
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import json
import os
import urllib.request

ROOT = str(_COMFY)
OUT_JSON = os.path.join(ROOT, "workflows", "0034_世界模型.json")
API_JSON = os.path.join(ROOT, "custom_nodes", "ComfyUI-FallingTS", "dev", "0034_api_prompt.json")
MD_PATH = os.path.join(ROOT, "stories", "七纹刻印", "0034_世界模型.md")
MEDIA_DIR = os.path.join(ROOT, "media", "七纹刻印")
# ⚠️ 必须用**软链侧**路径 `ComfyUI\output\...`, 不能用真实路径 `media\七纹刻印\...`:
#    viewer 的 _build_view_url 拿真实路径对 folder_paths.get_output_directory()(=软链路径) 求
#    relpath, 会得到 `..\..\media\...` 开头而被判定"不在 output 内", 回落到 subfolder= 为空的 404 URL。
#    软链侧路径同时**跟随当前项目**(换项目不用改), 比硬编码 media\七纹刻印 更稳。
OUT_DIR = os.path.join(ROOT, "ComfyUI", "output", "0034_世界模型")
HYWM2_WEIGHT = os.path.join(ROOT, "models", "hywm2", "model.safetensors")
VIEWER_URL = "http://127.0.0.1:8188/extensions/ComfyUI-FallingTS/viewer/scene-walk.html"
BASE = "http://127.0.0.1:8188"
OI = json.load(urllib.request.urlopen(f"{BASE}/object_info", timeout=120))

WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COLOR", "COMFY_DYNAMICCOMBO_V3",
                "COMFY_AUTOGROW_V3", "COMFY_MULTISELECT_V3", "FALLINGTS_MD_TABLE", "LOAD_3D"}
# 官方模板里 ImageBatchMulti 的 inputs 只列 image_1..N 端口; inputcount 只出现在 widgets_values,
# 且节点定义只声明 image_1/image_2 —— image_3..N 必须由序列化侧自己补出来(见 build_io)。
SKIP_WIDGET_INPUTS = {"ImageBatchMulti": {"inputcount"}}
DROP_INPUTS = {"ImageBatchMulti": {"inputcount"}}
MD_SLOTS = 42                 # FallingTSMarkDownTable 声明的输出槽数(RETURN_TYPES)

# 八个水平方位, 顺时针 45° 一档: 前面(起始面) → 前右 → 右面 → 后右 → 后面 → 后左 → 左面 → 前左
VIEWS = ["前面", "前右", "右面", "后右", "后面", "后左", "左面", "前左"]
PLY_NAME = "0034_世界模型_世界3DGS"       # 全图唯一产物 → 0034_世界模型_世界3DGS.ply
REFINE_SCRIPT = str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "world-refine" / "refine_0034_gs.py")
REFINE_PY = r"C:\Users\zghyu\AppData\Local\Programs\comfy-env\.pixi\envs\hywm2-nodes\python.exe"
NODE_SRC = os.path.join(ROOT, "custom_nodes", "ComfyUI-FallingTS", "world-refine", "nodes.py")


# ---------------------------------------------------------------- md table payload
def parse_md(path):
    """读 md 数据表表头与首行: 表头 `标题(类型)` → fields, 首行 → {列名: 值}。"""
    lines = [ln.rstrip("\n") for ln in open(path, encoding="utf-8") if ln.strip()]
    header = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    row = [c.strip() for c in lines[2].strip().strip("|").split("|")]
    fields = []
    for c in header:
        if "(" in c and c.endswith(")"):
            name, t = c.rsplit("(", 1)
            fields.append({"name": name.strip(), "type": t[:-1]})
        else:
            fields.append({"name": c, "type": "STRING"})
    return fields, {f["name"]: v for f, v in zip(fields, row)}


FIELDS, VALUES = parse_md(MD_PATH)
MD_WIDGET = [{"md_path": MD_PATH, "fields": FIELDS, "selected": {"id": VALUES["ID"], "values": VALUES}}]
SLOT = {f["name"]: i for i, f in enumerate(FIELDS)}       # 槽位 = 列序


# ---------------------------------------------------------------- object_info helpers
def _items(node_type):
    out = []
    info = OI[node_type]
    for group in ("required", "optional"):
        for k, v in (info.get("input", {}).get(group) or {}).items():
            out.append((k, v))
    return out


def schema_inputs(node_type):
    out = []
    info = OI[node_type]
    for name, v in _items(node_type):
        spec = v[0] if isinstance(v, list) else v
        if isinstance(spec, list):
            spec = "COMBO"
        group = "optional" if name in (info.get("input", {}).get("optional") or {}) else "required"
        out.append((name, spec, group))
    return out


def force_inputs(node_type):
    names = set()
    for name, v in _items(node_type):
        opts = v[1] if isinstance(v, list) and len(v) > 1 and isinstance(v[1], dict) else {}
        if opts.get("forceInput"):
            names.add(name)
    return names


def combo_children(node_type, combo_name, selected_key):
    """动态下拉选中项的子控件名(API 侧按 "<父>.<子>" 传值)。"""
    for name, v in _items(node_type):
        if name != combo_name:
            continue
        opts = v[1] if len(v) > 1 and isinstance(v[1], dict) else {}
        for opt in opts.get("options") or []:
            if isinstance(opt, dict) and opt.get("key") == selected_key:
                kids = []
                for g2 in ("required", "optional"):
                    for ck, cv in (opt.get("inputs", {}).get(g2) or {}).items():
                        kids.append((f"{combo_name}.{ck}", cv[0] if isinstance(cv, list) else cv))
                return kids
    return []


def outputs_of(node):
    """序列化输出槽: md 表固定 42 槽(out0..out41/*), 其余按后端 output 声明。"""
    if node["type"] == "FallingTSMarkDownTable":
        return [(f"out{i}", "*") for i in range(MD_SLOTS)]
    if node["type"] == "MarkdownNote":
        return []
    info = OI[node["type"]]
    names = info.get("output_name") or []
    types = info.get("output") or []
    if isinstance(types, str):
        types = [types]
    if isinstance(names, str):
        names = [names]
    return [(names[i] if i < len(names) else f"out{i}", types[i] if i < len(types) else "*")
            for i in range(len(types))]


# ---------------------------------------------------------------- node specs
N = {}


def add(nid, ntype, col, y, widgets=None, links=None):
    N[nid] = {"id": nid, "type": ntype, "col": col, "y": y,
              "widgets": widgets or [], "links": links or {}}


# ── 输入: md 数据表 (列 前面/前右/右面/后右/后面/后左/左面/前左 → 八个 IMAGE 槽)
add(1, "FallingTSMarkDownTable", 1, 40, MD_WIDGET)

# ── 八个面合成一个 batch (一次拿到整组视图)
add(9, "ImageBatchMulti", 2, 40, [len(VIEWS), None],
    {f"image_{i + 1}": (1, SLOT[v]) for i, v in enumerate(VIEWS)})

# ── 唯一支路: 8 视图 → **504 世界重建 + 3DGS 外观精修** → 唯一一个 PLY
#    WorldRefinePLY 在主进程只做"落临时 PNG + 调隔离解释器", 真算在 hywm2-nodes 环境里(gsplat 在那)。
#    排在这里(图里第一次前馈也是唯一一次) ⇒ 不会和别的进程各装一份 WorldMirror 抢 8GB 显存。
#    控件顺序 = 节点 inputs 顺序去掉图端口: 步数 / 模式 / 透明度信任域 / 颜色信任域 / 前馈长边 / 颜色监督长边 / 剪枝 / 重算前馈
add(20, "WorldRefinePLY", 3, 40, [800, "all", 3.0, 0.5, 0.5, 952, 826, 0.0, False], {"images": (9, 0)})

#    查看器是 output 节点 + forceInput 端口, 既保活上游节点, 又是可交互 3D 视口(只读不写)。
add(19, "HYWM2PLYAdvancedGaussianViewer", 4, 40, [], {"ply_path": (20, 0)})

NOTE_ID = 15
NOTE_TEXT = f"""## 0034_世界模型 · md 数据表 → HY-World 2.0 世界重建 + 精修（**只出一个最高质量 PLY**）

**输入走 md 数据表**（`stories\\七纹刻印\\0034_世界模型.md`，本节点 1 就是那张表）：
表内 `前面 / 前右 / 右面 / 后右 / 后面 / 后左 / 左面 / 前左` 八个 IMAGE 列按槽位顺序
（槽 2..9 = 列序）接进 `Image Batch Multi`。
改表后在本节点上点「刷新」，再 Run 即可换场景 —— **工作流里没有任何硬编码图片路径**。

### 唯一支路

| 链路 | 产物 |
|------|------|
| `Image Batch Multi` → **`World Refine PLY`**（自有插件 `ComfyUI-FallingTS\world-refine`） | **一个 3DGS `.ply`（全图唯一产物）** |

8 张图**一次前馈**（WorldMirror-2，HY-World 2.0 重建段）→ 统一世界坐标里的 3DGS →
**全参数精修**（颜色+透明度+几何）→ 落 `ComfyUI\\output\\0034_世界模型\\0034_世界模型_世界3DGS.ply`
（即 `media\\<当前项目>\\0034_世界模型\\`）。深度 / 法线 / 点云**不落盘**（零图片零视频；
点云无高斯、`.splat` 是 8bit 量化且无 SH —— 都按"只要 ply、要最高质量的"抛弃了）。

### 为什么重建跑在脚本里，而不是图内的 `HYWM2 Reconstruct`

读源码确认过（不是偷懒）：图内那个节点先 `mm.load_models_gpu(...)` 把模型装进显存，
**然后**才 `mm.get_free_memory()` 算分辨率 token 预算（`reconstruct.py:248 → :263`）⇒ 只能给到 **406**；
而 `custom_nodes\ComfyUI-FallingTS\world-refine\\refine_0034_gs.py` 在装模型**之前**测空闲显存 ⇒ 拿到 **504**，高斯多 53%、细节明显更多。
想让图内节点也吃到 504 必须改 HYWM2 插件代码，那是第三方子模块，本仓不动。
所以 `World Refine PLY` 只做三件事：把 8 张图落成临时 PNG → 调隔离解释器
（`comfy-env` 的 `hywm2-nodes`，gsplat 只在那里）跑 `custom_nodes\ComfyUI-FallingTS\world-refine\\refine_0034_gs.py` → 转发 PLY 路径。
**图里只有一次前馈**，不会两个进程各装一份 WorldMirror 抢这 8GB 显存。

### 这一步顺带修掉的五个坑

1. **分辨率**：504 而不是 406（见上）。
2. **尺度过滤**：`save_gs_ply` 的"砍最大 2% 尺度"在**批次张量**上会静默失效
   （`quantile(..., dim=0)` 退化成逐元素自身）；脚本落盘传的是非批次张量，过滤真的生效，
   否则房间外看就是一圈大雾（`scale_max` 0.3008 vs 0.0087）。
3. **不透明度信任域**：`reg_opac=0.5`，把精修后的不透明度中位从 0.366 压回 0.218，
   远看不再发灰；代价是 PSNR 29.48 而非 30.48 dB —— 8 个训练视角的 PSNR 高 ≠ 3D 资产好。
4. **颜色编码（决定"参考图的颜色有没有进世界模型"）**：`f_dc_*` 是 SH 的 DC **系数**，
   读取端一律再算 `0.5 + C0*f_dc`（本插件 `process_ply_to_splat`、浏览器视口、核心渲染都如此）。
   脚本原先落盘时传的是已经 `*C0+0.5` 过的 RGB ⇒ 变换做两遍，整间书房被抬到 DC 均值
   `[0.556, 0.546, 0.535]`（参考图是 `[0.165, 0.136, 0.101]`），亮度 +0.41、饱和度只剩 1/3.5,
   视口里就是**一片中灰发白**。现在传原始 `sh[:,0,:]`（均值约 -1.14），参考图的配色与
   每面墙的颜色分布因此才真的落进 PLY。
5. **多视图双重曝光（"影像重叠"的真凶）**：HYWM2 的**推理路径不做跨视图融合** ——
   `rasterization.py:240` 在 `is_inference` 时直接 `return predictions`，把紧接着的
   `prune_gs(voxel_size=0.002)`（`:248`）与 `apply_confidence_filter`（`:295`）**短路掉**；
   每个视图按自己的深度 + 自己预测的位姿反投影（`position_from="gsdepth+predcamera"`，`:522`），
   输出就是 `视图数 × H × W` 的**直接拼接**（本次 1,164,128 ÷ 8 ≈ 14.5 万/视图）⇒ 每个可见表面
   都有 2 层以上、彼此差几厘米的壳，位姿误差还会让整张视图的壳整体平移，视口里就是门框/挂钟/
   墙角各有两个的**重影**。实测把它与"透明度"拆开：α 调到 0.20 / 0.56 / 0.99 三个口径渲染，
   重影**一模一样**（连全不透明也不消失）⇒ 与透明无关，是几何。**只修外观（`mode=appearance`）
   会冻结 means/四元数/log 尺度 ⇒ 去不掉**；`mode=all` + `几何信任域` 才会把两层壳收拢。

### 零 output 写入（硬规则）
本图**没有任何** `Save*` / `RenderSplat` / `RenderMesh` / `PreviewImage*` / `PreviewVideo` / `CreateVideo` 节点。
唯一产物由 `World Refine PLY` 写进 output 子目录（viewer 需要走 `/view` URL 才能加载），
中间图只进 `ComfyUI\\temp\\worldrefine\\<输入内容哈希>\\`。除这一个 `.ply` 外**不再产出任何其它文件**。

### 怎么操作生成出来的模型
- **图内可交互 3D 视口**：节点 19（3DGS `.ply`，还会列每个字段的 dtype/数量与
  渲染时的解释方式 —— 这是核对"高斯字段对不对"最快的办法）。
  ComfyUI 内置视口只有**拖动旋转 + 滚轮缩放**（three.js OrbitControls，实测前端无 WASD 键位处理）。
- **像游戏一样漫游**：打开 → **{VIEWER_URL}**
  点一下画面进入指针锁定：**W/A/S/D 前后左右、Q/E 上下、Shift 加速、鼠标转头、滚轮调速、ESC 退出**；
  它自动拉取最新的 3D 产物，Queue 完 0034 后按「载入最新」就能走。

### 节点参数与实测（RTX 4060 8GB）
- `World Refine PLY`：`步数 800` / `mode=all`（全参数：颜色 + 透明度 + **几何**）/
  `几何信任域 3.0` / `透明度信任域 0.5` / `颜色信任域 0.5` / `前馈长边 952`（自适应后实测 504）/
  `颜色监督长边 826`（= 输入原生长边）/ `剪枝阈值 0` / `重算前馈 False`。
  - `精修模式` + `几何信任域` 是去重影的一档：`appearance` 冻结几何 ⇒ 8 个视图各自铺的壳原地不动，
    门框/墙角永远是两层；`all` 让 means/四元数/log 尺度一起参与光度监督，两层壳会收拢。
    权重扫描（同一份缓存、800 步、视口口径 4 机位的 PSNR）：`reg=0` 27.50 dB 但门框/墙角出现
    明显"烧焦"暗斑，`reg=1` 26.48，`reg=3` 26.21，`reg=10` 25.99 且几乎无伪影 —— **连 reg=10
    都能把壳收掉**（两层壳间距本来就不大），默认 3.0 取"无焦边 + 已去重影"。8 视图 PSNR：
    前馈 24.46 → `reg=0` 33.94 / `reg=3` 31.35 / `reg=10` 30.63 dB。
    ⚠️ 训练视角 PSNR 高 ≠ 3D 资产好：`reg=0` 最高，但那是靠把高斯掰成对准这 8 个机位换来的。
  - `颜色信任域` 是关键的一档：每步只监督 1 个视角，个别高斯会被撑成彩虹色去凑那一个视角，
    单色（DC-only）渲染里就是墙角上的粉/绿噪点。0.5 把"饱和度 > 0.3 的高斯"从 3.07% 压到 1.58%，
    参考机位下的 DC 单色 PSNR 反而从 25.51 升到 **27.17 dB**、与参考图的色差 L1 从 0.019 降到 0.015
    （代价是 8 个训练视角的 PSNR 29.48 → 29.10 dB，同 `reg_opac` 一样的取舍）。
  - `前馈长边` 调高 = 几何/布局细节上限更高，但会被空闲显存自适应压低（8GB 实测 504）。
  - `颜色监督长边` 调低可省显存/时间；826 是精修对参考图做光度监督的分辨率。
  - `剪枝阈值` 会剪掉低不透明度高斯（减高斯数=减远看雾气），注意会改变高斯数。
  - `refresh=True` 忽略前馈缓存强制重算；缓存按**8 张图的内容哈希**校验，换图必然重算，不会串旧结果。
- 实测：504 前馈 + 800 步全参数精修 ≈ **1 分钟**；产物 **79.0MB / 1,161,699 个高斯**，
  8 视图 PSNR 24.46 → **31.35 dB**（`reg=3`），去除多视图双重曝光。
- 3DGS 头只输出 **SH degree 0（视图无关颜色）** ⇒ 颜色就是"参考图的平均配色"，
  没有视角依赖的高光；精修是绕开 ViT token 预算、把参考图颜色按原生分辨率压进 DC 的唯一通道。
- 3DGS `.ply` 的 17 个属性是标准布局（`x,y,z + nx,ny,nz + f_dc_0..2 + opacity + scale_0..2 + rot_0..3`），
  Blender / SuperSplat / 任何 3DGS 工具都能直接读；`scale_*` 是自然对数、`opacity` 按标准是 logit。
  ⚠️ 但上游与我们的落盘路径都把**已经 sigmoid 过的 α** 原样写进 `opacity` 字段，读取端按 logit
  再 sigmoid 一次 ⇒ **视口里每个高斯的 α 被抬到 0.50~0.69，没有一个是暗的**（模型本意约
  0.008~0.78、中位 0.19；视口口径 vs 真实 α 口径的 PSNR 差 1.5 dB）。2026-09-28 诊断确认，
  **尚未修**（去鬼影不靠它，见坑 5）。
- ⚠️ **表内当前这八张的素材不闭合**：它们是从 0031 的 H3 旋转视频里抽的帧，"原地旋转"实际把每面墙
  各渲染成一张**正面视角**，相邻面重叠不足 → 会拼出开口的墙皮扇面。
  换**真机环绕实拍八张**（或 Qwen 多视角 LoRA 出图、相邻面共享墙角）填进同一批列即可闭合，
  链路与参数都不用动。**8 张是下限而非目标**，相邻视角重叠 ≥60% 最稳。
- 视口里**巨小或看着不在房间里**：说明世界尺度变了，按 PLY 里 `x,y,z` 的包围盒重标机位。
"""
N[NOTE_ID] = {"id": NOTE_ID, "type": "MarkdownNote", "col": 0, "y": 40, "widgets": [NOTE_TEXT], "links": {}}


# ---------------------------------------------------------------- build serialized io
def build_io(node):
    t = node["type"]
    if t in ("FallingTSMarkDownTable", "MarkdownNote"):
        return []
    forced = force_inputs(t)
    drop = DROP_INPUTS.get(t, set())
    io = []
    for name, spec, group in schema_inputs(t):
        if name in drop:
            continue
        is_widget = (spec in WIDGET_TYPES) and name not in forced
        io.append({"name": name, "type": spec, "group": group, "is_widget": is_widget})
    count = node["widgets"][0] if t in ("ImageBatchMulti", "MaskBatchMulti") else 0
    have = {x["name"] for x in io}
    for i in range(2, int(count) + 1):
        nm = f"image_{i}"
        if nm not in have:
            io.append({"name": nm, "type": "IMAGE", "group": "optional", "is_widget": False})
    return io


for node in N.values():
    node["io"] = build_io(node)


# ---------------------------------------------------------------- links
links = []
link_id = 1
for node in sorted(N.values(), key=lambda x: x["id"]):
    node["_inputs"] = []
    for spec in node["io"]:
        name = spec["name"]
        src = None if spec["is_widget"] else node["links"].get(name)
        if src is None:
            entry = {"name": name, "type": spec["type"], "link": None}
            if spec["group"] == "optional":
                entry["shape"] = 7
            if spec["is_widget"]:
                entry["widget"] = {"name": name}
            node["_inputs"].append(entry)
            continue
        oid, oslot = src
        otype = outputs_of(N[oid])[oslot][1]
        ltype = otype if otype != "*" else spec["type"]
        links.append([link_id, oid, oslot, node["id"], len(node["_inputs"]), ltype])
        entry = {"name": name, "type": spec["type"], "link": link_id}
        if spec["group"] == "optional":
            entry["shape"] = 7
        node["_inputs"].append(entry)
        link_id += 1
    node["_socket_names"] = [s["name"] for s in node["io"] if not s["is_widget"]]


# ---------------------------------------------------------------- layout (hand placed)
GAP = 80
SIZES = {
    "FallingTSMarkDownTable": (480, 950),
    "ImageBatchMulti": (300, 294),
    "WorldRefinePLY": (300, 200),
    "HYWM2PLYAdvancedGaussianViewer": (300, 160),
    "MarkdownNote": (340, 940),
}
# 视口默认机位: 原 DA3 网格视口已删, 不再需要 VIEWPORT_PROPS

sizes = {}
for node in N.values():
    w, h = SIZES.get(node["type"], (300, 160))
    need = 60 + 26 * max(len(node["io"]), len(node["widgets"]) + 1)
    sizes[node["id"]] = (w, max(h, need))

cols = {}
for node in N.values():
    cols.setdefault(node["col"], []).append(node)
prev_x = prev_w = 0
for c in sorted(cols):
    width = max(sizes[n["id"]][0] for n in cols[c])
    x = 0 if c == 0 else prev_x + prev_w + GAP
    for n in cols[c]:
        n["_x"], n["_y"] = x, n["y"]
    prev_x, prev_w = x, width

# ---------------------------------------------------------------- emit
out_nodes = []
for node in sorted(N.values(), key=lambda z: z["id"]):
    t = node["type"]
    w, h = sizes[node["id"]]
    props = {"Node name for S&R": t}
    entry = {
        "id": node["id"], "type": t, "pos": [node["_x"], node["_y"]], "size": [w, h],
        "flags": {}, "order": node["id"], "mode": 0,
        "inputs": node["_inputs"],
        "outputs": [{"name": nm, "type": ty, "links": [], "slot_index": i}
                    for i, (nm, ty) in enumerate(outputs_of(node))],
        "properties": props,
        "widgets_values": node["widgets"],
    }
    if t == "MarkdownNote":
        entry["color"] = "#432"
        entry["bgcolor"] = "#653"
    out_nodes.append(entry)

by_id = {n["id"]: n for n in out_nodes}
for l in links:
    by_id[l[1]]["outputs"][l[2]]["links"].append(l[0])

wf = {
    "id": "0034-world-model", "revision": 0, "last_node_id": max(N), "last_link_id": link_id - 1,
    "nodes": out_nodes, "links": links, "groups": [], "config": {},
    "extra": {"ds": {"scale": 0.33, "offset": [40, 60]}}, "version": 0.4,
}
json.dump(wf, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"wrote {OUT_JSON}: {len(out_nodes)} nodes, {len(links)} links")

# ---------------------------------------------------------------- API prompt
CTRL_AFTER_SEED = {"seed", "noise_seed"}
api = {}
for node in N.values():
    if node["type"] == "MarkdownNote":
        continue
    t = node["type"]
    inputs = {}
    if t == "FallingTSMarkDownTable":
        inputs["data"] = node["widgets"][0]          # md 表节点只吃控件状态 data
    else:
        vals = list(node["widgets"])
        wi = 0
        for k, v in _items(t):
            spec = v[0] if isinstance(v, list) else v
            opts = v[1] if len(v) > 1 and isinstance(v[1], dict) else {}
            if isinstance(spec, list):
                spec = "COMBO"
            if spec == "COMFY_DYNAMICCOMBO_V3":
                key = vals[wi]
                inputs[k] = key
                wi += 1
                for ck, ct in combo_children(t, k, key):
                    inputs[ck] = vals[wi]
                    wi += 1
                continue
            if spec == "COMFY_AUTOGROW_V3":
                continue
            if (spec in WIDGET_TYPES or opts.get("socketless")) and k not in SKIP_WIDGET_INPUTS.get(t, set()):
                if wi < len(vals):
                    inputs[k] = vals[wi]
                    wi += 1
                    if k in CTRL_AFTER_SEED and wi < len(vals):
                        wi += 1
            elif k in SKIP_WIDGET_INPUTS.get(t, set()):
                inputs[k] = vals[wi]
                wi += 1
    for name in node["_socket_names"]:
        src = node["links"].get(name)
        if src:
            inputs[name] = [str(src[0]), src[1]]
    api[str(node["id"])] = {"class_type": t, "inputs": inputs}
json.dump(api, open(API_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"wrote {API_JSON}: {len(api)} nodes")

# ---------------------------------------------------------------- validation
problems = []

# 1) md 表本身: 列定义、八个面、引用可解析
hdr = [f["name"] for f in FIELDS]
if hdr[0] != "ID":
    problems.append(f"md 表第一列必须是 ID, 实际 {hdr[0]}")
for i, v in enumerate(VIEWS):
    if f"{v}(IMAGE)" not in [f"{f['name']}({f['type']})" for f in FIELDS]:
        problems.append(f"md 表缺少 IMAGE 列: {v}(IMAGE)")
    if hdr[2 + i] != v:
        problems.append(f"md 表图片列顺序不对: 槽 {2 + i} 应为 {v}, 实际 {hdr[2 + i]}")
for need in ("宽度(INT)", "高度(INT)", "场景描述(TEXT)"):
    if need not in [f"{f['name']}({f['type']})" for f in FIELDS]:
        problems.append(f"md 表缺少列: {need}")
for v in VIEWS:
    raw = VALUES[v]
    ref = raw[2:-1] if raw.startswith("@{") and raw.endswith("}") else ""
    subdir, _, stem = ref.rpartition("/")
    if not subdir:
        problems.append(f"md 表 {v} 不是 @{{表名/ID}} 引用: {raw}")
        continue
    exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
    hit = [e for e in exts if os.path.isfile(os.path.join(MEDIA_DIR, subdir, stem + e))]
    if not hit:
        problems.append(f"md 表 {v} 引用解析不到文件: {ref}（严格命中 media\\{subdir}\\{stem}.*）")
if len(FIELDS) > MD_SLOTS - 1:
    problems.append(f"md 表列数 {len(FIELDS)} 超过 md 表节点槽位上限 {MD_SLOTS}")

# 2) 工作流结构
node_types = [n["type"] for n in out_nodes]
if node_types.count("FallingTSMarkDownTable") != 1:
    problems.append(f"必须有且只有一个 md 数据表节点, 实际 {node_types.count('FallingTSMarkDownTable')}")
if "LoadImage" in node_types:
    problems.append("本版输入必须走 md 表, 不该再出现硬编码的 LoadImage")
if N[1]["widgets"] != MD_WIDGET:
    problems.append("md 表节点 widgets_values 结构不对")
mdw = N[1]["widgets"][0]
if set(mdw) != {"md_path", "fields", "selected"} or mdw["md_path"] != MD_PATH:
    problems.append(f"md 表节点状态不对: {mdw.keys()}")
if mdw["selected"]["id"] != VALUES["ID"] or mdw["selected"]["values"] != VALUES:
    problems.append("md 表节点选中行与 md 首行不一致")
if api["1"]["inputs"].get("data") != mdw:
    problems.append("API prompt 里 md 表节点没有把整份 state 传给 data")

# 3) 逐节点 / 逐连线检查
for node in out_nodes:
    t = node["type"]
    if t not in OI and t != "MarkdownNote":
        problems.append(f"node {node['id']} type not registered: {t}")
    for i, p in enumerate(node["inputs"]):
        if p["link"] is None:
            continue
        src = [l for l in links if l[0] == p["link"]]
        if not src:
            problems.append(f"node {node['id']} input {p['name']}: dangling link")
            continue
        if src[0][3] != node["id"] or src[0][4] != i:
            problems.append(f"link {src[0][0]} target mismatch")
    for l in links:
        if l[3] != node["id"]:
            continue
        o = by_id[l[1]]
        if o["pos"][0] + o["size"][0] > node["pos"][0]:
            problems.append(f"RULE1 violation link {l[0]}: {o['type']} -> {t}")
    info = OI.get(t, {})
    for name, specs in (info.get("input", {}).get("required") or {}).items():
        spec = specs[0] if isinstance(specs, list) else specs
        opts = specs[1] if isinstance(specs, list) and len(specs) > 1 and isinstance(specs[1], dict) else {}
        if isinstance(spec, list):
            spec = "COMBO"
        if spec in WIDGET_TYPES or opts.get("socketless") or name in SKIP_WIDGET_INPUTS.get(t, set()):
            continue
        if not any(p["name"] == name and p["link"] is not None for p in node["inputs"]):
            problems.append(f"node {node['id']} ({t}) required input {name} unconnected")

# 4) 八个面按槽位顺序接进 ImageBatchMulti(端口顺序 = 方位顺序)
for i in range(len(VIEWS)):
    p = next((e for e in by_id[9]["inputs"] if e["name"] == f"image_{i + 1}"), None)
    if not p or p.get("link") is None:
        problems.append(f"ImageBatchMulti.image_{i + 1} 没接")
        continue
    l = [x for x in links if x[0] == p["link"]][0]
    if (l[1], l[2]) != (1, SLOT[VIEWS[i]]):
        problems.append(f"image_{i + 1} 应来自 md 表槽 {SLOT[VIEWS[i]]}({VIEWS[i]}), 实际 {l[1]}:{l[2]}")
if N[9]["widgets"] != [8, None]:
    problems.append(f"ImageBatchMulti widgets_values 应为 [8, None], 实际 {N[9]['widgets']}")

# 5) 六条布局规范
#    规则 2 输入侧: 同一节点内, 端口 a<b ⇒ 上游 a 的 y < 上游 b 的 y
for node in out_nodes:
    ups = [([l for l in links if l[0] == p["link"]][0][1], i)
           for i, p in enumerate(node["inputs"]) if p["link"] is not None]
    for a in range(len(ups)):
        for b in range(a + 1, len(ups)):
            if ups[a][0] == ups[b][0]:
                continue
            if by_id[ups[a][0]]["pos"][1] >= by_id[ups[b][0]]["pos"][1]:
                problems.append(f"RULE2 in violation node {node['id']} ({node['type']}) 端口 "
                                f"{ups[a][1]}<{ups[b][1]} 上游 y 颠倒")
#    规则 2 输出侧: 同一节点内, 端口 a<b ⇒ 下游 a 的 y < 下游 b 的 y
for node in out_nodes:
    ports = {}
    for l in links:
        if l[1] != node["id"]:
            continue
        ports.setdefault(l[2], []).append(l[3])
    keys = sorted(ports)
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            for da in ports[keys[a]]:
                for db in ports[keys[b]]:
                    if da == db:
                        continue
                    if by_id[da]["pos"][1] >= by_id[db]["pos"][1]:
                        problems.append(f"RULE2 out violation node {node['id']} ({node['type']}) 端口 "
                                        f"{keys[a]}<{keys[b]} 下游 {da}/{db} y 颠倒")
for a in out_nodes:
    for b in out_nodes:
        if a["id"] >= b["id"]:
            continue
        ax, ay = a["pos"]; aw, ah = a["size"]; bx, by = b["pos"]; bw, bh = b["size"]
        if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
            problems.append(f"RULE3 overlap {a['id']}({a['type']}) / {b['id']}({b['type']})")
col_members = {}
for n in out_nodes:
    col_members.setdefault(n["pos"][0], []).append(n)
for x, members in col_members.items():
    members.sort(key=lambda m: m["pos"][1])
    for lower, upper in zip(members, members[1:]):
        gapv = upper["pos"][1] - (lower["pos"][1] + lower["size"][1])
        if gapv < 50 or gapv > 100:
            problems.append(f"RULE3 column gap {lower['id']}->{upper['id']} = {gapv}px")
md_cols = {n["pos"][0] for n in out_nodes if n["type"] == "FallingTSMarkDownTable"}
if len(md_cols) != 1:
    problems.append("md 表节点位置异常")
elif len(col_members[next(iter(md_cols))]) != 1:
    problems.append("RULE3: md 数据表节点必须独占整列")

# 6) 唯一链路完整性 + 关键参数 + 零图片视频输出(本图无网格、无第二份产物)
CHAIN = [(9, "image_1", 1), (20, "images", 9), (19, "ply_path", 20)]
for node_id, in_name, want in CHAIN:
    p = next((e for e in by_id[node_id]["inputs"] if e["name"] == in_name), None)
    if not p or p.get("link") is None:
        problems.append(f"[CHAIN] node {node_id}.{in_name} 没接")
        continue
    l = [x for x in links if x[0] == p["link"]][0]
    if l[1] != want:
        problems.append(f"[CHAIN] node {node_id}.{in_name} 应来自 {want}, 实际 {l[1]}")

#    ★ 唯一产物: 全图只允许 WorldRefinePLY 一个产出型节点, 且它写出的是 3DGS PLY
if [n["type"] for n in out_nodes if n["type"] == "WorldRefinePLY"] != ["WorldRefinePLY"]:
    problems.append("全图必须有且只有一个 WorldRefinePLY")
if [n["type"] for n in out_nodes if n["type"].startswith("HYWM2Export")]:
    problems.append("重建已交给 WorldRefinePLY, 图里不该再有 HYWM2Export* 节点")
#    WorldRefinePLY 的九个控件: 步数 / mode / reg / reg_opac / reg_color / target / gt / prune_opac / refresh
if N[20]["widgets"] != [800, "all", 3.0, 0.5, 0.5, 952, 826, 0.0, False]:
    problems.append(f"WorldRefinePLY 控件不对: {N[20]['widgets']}")
#    它依赖的三个文件必须在(节点本体 + 隔离解释器 + 精修脚本), 否则运行期才炸
for p in (NODE_SRC, REFINE_PY, REFINE_SCRIPT):
    if not os.path.isfile(p):
        problems.append(f"WorldRefinePLY 依赖缺失: {p}")
#    产物目录必须在**软链侧** output 目录内, 否则 viewer 拼不出 /view URL
out_root = os.path.join(ROOT, "ComfyUI", "output")
if os.path.normcase(os.path.commonpath([OUT_DIR, out_root])) != os.path.normcase(out_root):
    problems.append(f"PLY 落盘目录必须在 {out_root} 内(软链侧), 实际 {OUT_DIR}")
#    ★ 反向校验: 被抛弃的导出格式/视口/回显, 以及被挪走的重建节点不得回流
DISCARDED = ("HYWM2ExportGaussiansSplat", "HYWM2ExportPointsPLY", "HYWM2SplatAdvancedViewer",
             "HYWM2PreviewPointCloud", "PreviewAny", "LoadHYWM2Model", "HYWM2Reconstruct")
for t in node_types:
    if t in DISCARDED:
        problems.append(f"已抛弃/已挪走的节点不该回流: {t}")
#    零 output 写入: 不允许任何网格/图片/视频节点
FORBIDDEN = ("SaveImage", "SaveVideo", "SaveAnimatedWEBP", "SaveAudio", "SaveGLB",
             "PreviewImage", "PreviewImageSave", "PreviewVideo", "CreateVideo", "RenderSplat",
             "RenderMesh", "VHS_VideoCombine", "SaveGaussianSplat", "Save3D")
for t in node_types:
    if t.startswith("Save") or t in FORBIDDEN:
        problems.append(f"本图不输出图片/视频、零 output 写入, 不该出现 {t}")
#    PLY 视口必须是 output 节点(否则上游 WorldRefinePLY 会被剪枝)
for nid in (19,):
    if not OI.get(N[nid]["type"], {}).get("output_node"):
        problems.append(f"node {nid} ({N[nid]['type']}) 不是 output 节点, 其上游会被剪枝")
if not os.path.isfile(HYWM2_WEIGHT):
    problems.append(f"HYWM2 权重缺失: {HYWM2_WEIGHT}")
#    本图不应再出现任何网格节点(用户要求"不要网格, 只要世界模型")
for t in node_types:
    if t in ("LoadDA3Model", "DA3Inference", "DA3GeometryToMesh", "MeshToFile3D",
             "Preview3DAdvanced", "Load3D", "File3DToSplat", "SplatToMesh", "SaveGLB", "RenderMesh"):
        problems.append(f"本图只要世界模型, 不该出现网格节点 {t}")

print("\n--- validation ---")
for p in problems:
    print("  PROBLEM:", p)
if not problems:
    print("  all static checks passed")
print("md 表列:", ", ".join(f"{f['name']}({f['type']})" for f in FIELDS))
print("八个面槽位:", {v: SLOT[v] for v in VIEWS})
print("列 x:", sorted({n["pos"][0] for n in out_nodes}))
print("各列 y:", {x: [m["id"] for m in sorted(col_members[x], key=lambda m: m["pos"][1])]
                  for x in sorted(col_members)})
print("节点:", ", ".join(f"{n['id']}:{n['type']}" for n in out_nodes))
