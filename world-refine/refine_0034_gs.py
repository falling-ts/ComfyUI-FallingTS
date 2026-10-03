"""0034 世界模型质量诊断 + 光度精修原型。

在隔离环境 (hywm2-nodes) 里跑:
  C:\\Users\\zghyu\\AppData\\Local\\Programs\\comfy-env\\.pixi\\envs\\hywm2-nodes\\python.exe
  cwd = D:\\AI\\Comfy\\custom_nodes\\ComfyUI-HYWM2

阶段:
  A. 跑 WorldMirror 前馈, 缓存预测到 .pt  (--steps 0 只做 A)
  B. 用【模型自己预测的相机】渲染, 对 8 张预处理 GT 算 PSNR  -> 客观基线
  C. 以 8 视图光度监督做 Adam 精修, 再算 PSNR -> 提升量
"""
import pathlib as _pathlib
# 项目根 = 往上 4 层 (world-refine → ComfyUI-FallingTS → custom_nodes → 工作区根);
# realpath 会解开 `ComfyUI\custom_nodes` 那层目录软链, 项目整体搬家后自动跟随。
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent

import argparse, os, sys, time, math, json
import numpy as np
import torch

# stdout 接到管道时 Windows 上 Python 会退回 GBK 输出(节点按 UTF-8 解码 ⇒ 含中文的
# output 路径变成 \ufffd, isfile 为假, 节点误报"脚本没报出 PLY 路径")。
# 这里自己钉死 UTF-8, 不依赖父进程的 PYTHONUTF8 / PYTHONIOENCODING。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PLUGIN = str(_COMFY / "custom_nodes" / "ComfyUI-HYWM2")
COMFYUI = str(_COMFY / "ComfyUI")
# 正式 worker 的 sys_path 就是这两条 + site-packages。
# 顺序要紧: 插件目录必须先于 ComfyUI —— 插件顶层包就叫 `nodes`,
# 否则 `nodes.hyworld2...` 会解析到 ComfyUI 的 nodes.py 并拉进 torchsde。
if COMFYUI not in sys.path:
    sys.path.append(COMFYUI)
if PLUGIN not in sys.path:
    sys.path.insert(0, PLUGIN)

MODEL_DIR = str(_COMFY / "models" / "hywm2")
MEDIA = str(_COMFY / "media" / "七纹刻印")
SLOTS = ["前面", "前右", "右面", "后右", "后面", "后左", "左面", "前左"]
DEFAULT_VIEWS = [os.path.join(MEDIA, "0031_首帧场景", f"00001_书房旋镜{v}.png") for v in SLOTS]
CACHE = str(_COMFY / "scripts" / "_cache-0034-preds.pt")
OUTDIR = str(_COMFY / "scripts" / "_out-0034-refine")
ASSET_DIR = str(_COMFY / "media" / "七纹刻印" / "0034_世界模型")
OUT_NAME = "0034_世界模型_世界3DGS_精修"
C0 = 0.28209479177387814

ap = argparse.ArgumentParser()
# --views: 由 ComfyUI 节点(脚本阶段则用默认的 8 张 0031 帧)按**批序**传进来的图片路径,
#          顺序必须是 前面/前右/右面/后右/后面/后左/左面/前左。
ap.add_argument("--views", type=str, default="",
                help="8 张视图路径, 用 ; 分隔(批序); 空=用 0031_首帧场景 的默认八面")
ap.add_argument("--cache", type=str, default=CACHE, help="前馈预测缓存路径(按图片内容哈希校验)")
ap.add_argument("--asset-dir", type=str, default=ASSET_DIR, help="PLY 落盘目录")
ap.add_argument("--out-name", type=str, default=OUT_NAME, help="PLY 文件名(不含扩展名)")
ap.add_argument("--steps", type=int, default=800)
ap.add_argument("--target", type=int, default=952)
ap.add_argument("--eff", type=int, default=0, help="强制 ViT 分辨率(0=复刻节点的自动预算)")
ap.add_argument("--lr", type=float, default=1.6e-3)
ap.add_argument("--gt", type=int, default=826,
                help="精修监督用的长边像素(0=沿用 ViT 的 eff); 826 = 输入原生长边")
ap.add_argument("--mode", choices=["all", "appearance"], default="appearance",
                help="all=连几何一起修(易在新视角出伪影); appearance=只修颜色+透明度")
ap.add_argument("--reg", type=float, default=3.0,
                help="对几何施加信任域惩罚的权重(mode=all 时用, 0=关)。mode=all 会真的把 8 个视图"
                     "各自铺的壳收拢(去双重曝光), 但几何动得越多, 门框/墙角这类深度不连续处越容易"
                     "冒出'烧焦'暗斑; 800 步实测扫描: reg=0 训练视角 PSNR 最高但伪影最重, reg=10 "
                     "最干净且鬼影照样收掉, 默认 3.0 取中间。0=不设信任域(会拿到最脏的一档)")
ap.add_argument("--reg-opac", type=float, default=0.5,
                help="对【不透明度】施加信任域惩罚的权重(默认 0.5: 防止把软高斯'画实'导致远看发灰发雾; 0=关)")
ap.add_argument("--reg-color", type=float, default=0.0,
                help="对【SH DC 颜色】施加信任域惩罚的权重(0=关)。每步只监督 1 个视角, "
                     "少数高斯会被撑成彩虹色去凑那一个视角, 单色(DC-only)渲染里就是墙角的粉/绿噪点; "
                     "这一项把 DC 拉回前馈解附近")
ap.add_argument("--prune-opac", type=float, default=0.0,
                help="落盘前剪掉不透明度低于该阈值的高斯(减高斯数=减远看雾气, 0=不剪)")
ap.add_argument("--prior-camera", type=str, default="",
                help="相机先验 JSON (upstream `load_prior_camera` 口径: extrinsics = 每视角 4x4 "
                     "**c2w**, intrinsics = 3x3)。给了它前馈就带上 cond_flags=[cam,0,intr], 位姿不再"
                     "由模型瞎猜 —— 这是从源头消重影的唯一入口; 空=沿用模型自己预测的位姿")
ap.add_argument("--dump-baseline", action="store_true",
                help="把前馈(未精修)的同一份高斯另存一个 PLY, 用于把【分辨率】与【精修】两个变量拆开")
ap.add_argument("--refresh", action="store_true", help="忽略缓存, 重跑前馈")
a = ap.parse_args()
VIEWS = [p for p in a.views.split(";") if p] or DEFAULT_VIEWS
PRIOR = a.prior_camera if a.prior_camera and os.path.isfile(a.prior_camera) else ""
if a.prior_camera and not PRIOR:
    raise SystemExit(f"--prior-camera 指的文件不存在: {a.prior_camera}")
os.makedirs(OUTDIR, exist_ok=True)
CACHE = a.cache


def log(*m):
    print(*m, flush=True)


def views_key():
    """输入的**内容**哈希 —— 缓存必须按内容校验, 否则换了输入会静默复用旧前馈。

    相机先验 JSON 也一起入哈希: 同一批图换个位姿先验, 前馈结果完全不同。
    """
    import hashlib
    h = hashlib.sha1()
    for p in VIEWS:
        with open(p, "rb") as f:
            h.update(hashlib.sha1(f.read()).digest())
    if PRIOR:
        with open(PRIOR, "rb") as f:
            h.update(hashlib.sha1(f.read()).digest())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------- A. 前馈
def prior_deviation(preds):
    """量化「相机先验到底有没有生效」: 模型预测位姿 vs 注入先验的偏差。

    口径与 pipeline 完全一致 (`_run_inference` 注入时按第一台相机归一化:
    `P' = inv(P[0]) @ P`), 先验 JSON 里是 **c2w**。偏差越小说明模型的位姿头被先验拉得越紧,
    每个视角的反投影就越可能落在同一张表面上 —— 这正是重影的对症指标。
    """
    import json as _json
    try:
        data = _json.load(open(PRIOR, encoding="utf-8"))
        entries = {str(e["camera_id"]): np.array(e["matrix"], dtype=np.float64)
                   for e in data.get("extrinsics", [])}
        order = [os.path.splitext(os.path.basename(p))[0] for p in VIEWS]
        P = np.stack([entries[s] for s in order])                  # [S,4,4] c2w
        P = np.linalg.inv(P[0]) @ P                                # 第一台相机为世界原点
        pred = preds["camera_poses"][0].detach().float().cpu().numpy()
        S = min(len(P), len(pred))
        ang, tr = [], []
        for i in range(S):
            R = P[i][:3, :3].T @ pred[i][:3, :3]
            cos = (np.trace(R) - 1.0) / 2.0
            ang.append(math.degrees(math.acos(min(1.0, max(-1.0, cos)))))
            tr.append(float(np.linalg.norm(P[i][:3, 3] - pred[i][:3, 3])))
        log(f"[A] 先验生效度: 预测位姿 vs 注入先验 —— 旋转偏差 中位 {np.median(ang):.2f}° "
            f"最大 {max(ang):.2f}°, 平移偏差 最大 {max(tr):.4f} (纯旋转场景应≈0)")
    except Exception as exc:  # noqa: BLE001
        log(f"[A] 先验偏差统计失败(不影响重建): {exc}")


def run_forward():
    from nodes.hyworld2.worldrecon.pipeline import WorldMirrorPipeline
    from nodes.hyworld2.worldrecon.hyworldmirror.utils.inference_utils import (
        compute_adaptive_target_size,
    )
    missing = [p for p in VIEWS if not os.path.isfile(p)]
    if missing:
        raise SystemExit("缺输入图:\n  " + "\n  ".join(missing))

    eff = compute_adaptive_target_size(VIEWS, a.target)
    if a.eff > 0:
        log(f"[A] {len(VIEWS)} 视图, requested={a.target} adaptive={eff} -> 强制 eff={a.eff}")
        eff = a.eff
    else:
        from nodes.reconstruct import _auto_target_size
        free_gb = torch.cuda.mem_get_info()[0] / (1024 ** 3)
        auto = _auto_target_size(len(VIEWS), eff, free_gb)
        log(f"[A] {len(VIEWS)} 视图, requested={a.target} adaptive={eff} "
            f"free={free_gb:.2f}GB -> _auto_target_size={auto}  (节点实际口径)")
        eff = auto

    dev = torch.device("cuda")
    pipe = WorldMirrorPipeline.from_pretrained(
        pretrained_model_name_or_path=MODEL_DIR, subfolder="", enable_bf16=True,
        disable_heads=None,
    )
    pipe.model.to(dev)
    pipe.device = dev
    log(f"[A] pipeline ready, device={pipe.device}")

    t0 = time.perf_counter()
    # 必须 no_grad: 节点的 execute 外层有 @torch.no_grad(), 直接调会保留 24 层激活而 OOM
    with torch.no_grad():
        preds, imgs, infer_time = pipe._run_inference(
            img_paths=VIEWS, target_size=eff, prior_cam_path=PRIOR or None, prior_depth_path=None)
    log(f"[A] 前馈完成 {infer_time:.2f}s (墙钟 {time.perf_counter()-t0:.2f}s) "
        + (f"[相机先验 {os.path.basename(PRIOR)} 已注入 cond_flags=[cam,0,intr]]"
           if PRIOR else "[无相机先验: 每个视角按自己预测的位姿反投影 = 双重曝光源头]"))
    if PRIOR:
        prior_deviation(preds)
    log(f"[A] imgs(GT) shape = {tuple(imgs.shape)}  dtype={imgs.dtype}")

    sp = preds["splats"]
    log("[A] splats keys: " + ", ".join(sorted(sp.keys())))
    for k in sorted(sp.keys()):
        v = sp[k]
        if torch.is_tensor(v):
            log(f"      {k:12s} {tuple(v.shape)} {v.dtype}")
    for k in ("camera_poses", "camera_intrs", "pts3d", "depth", "normals", "conf"):
        if k in preds and torch.is_tensor(preds[k]):
            log(f"      preds[{k}] {tuple(preds[k].shape)} {preds[k].dtype}")

    cache = {
        "imgs": imgs.detach().float().cpu(),
        "camera_poses": preds["camera_poses"].detach().float().cpu(),
        "camera_intrs": preds["camera_intrs"].detach().float().cpu(),
        "splats": {k: v.detach().float().cpu() for k, v in sp.items()
                   if torch.is_tensor(v) and k in ("means", "quats", "scales", "opacities", "sh", "weights")},
        "eff": eff,
        "views_key": VK,
    }
    torch.save(cache, CACHE)
    log(f"[A] 缓存 -> {CACHE} ({os.path.getsize(CACHE)/1e6:.1f} MB)")
    return cache


VK = views_key()
if a.refresh or not os.path.isfile(CACHE):
    cache = run_forward()
else:
    cache = torch.load(CACHE, weights_only=False)
    if cache.get("views_key") != VK:
        log(f"[A] 缓存的内容哈希 {cache.get('views_key')} != 当前输入 {VK}, 重跑前馈")
        cache = run_forward()
    elif a.eff and cache.get("eff") != a.eff:
        log(f"[A] 缓存 eff={cache.get('eff')} != 要求 {a.eff}, 重跑")
        cache = run_forward()
    else:
        log(f"[A] 用缓存 {CACHE}  (eff={cache['eff']}, views_key={VK})")


# ---------------------------------------------------------------- 参数打包
def unpack(splats, G, dev):
    """splats(模型原始量) -> 可优化张量 (gsplat 约定)."""
    means = splats["means"].reshape(-1, 3).to(dev)
    quats = splats["quats"].reshape(-1, 4).to(dev)
    quats = quats / quats.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    scales = splats["scales"].reshape(-1, 3).to(dev)          # 已是线性(exp 过)
    opac = splats["opacities"].reshape(-1).to(dev)            # 已是 sigmoid 过
    sh = splats.get("sh")
    if sh is None:
        raise SystemExit("splats 里没有 sh")
    sh = sh.reshape(-1, sh.shape[-1] // 3, 3).to(dev) if sh.dim() >= 3 else sh.reshape(-1, 1, 3).to(dev)
    K = sh.shape[1]
    sh_deg = int(round(math.sqrt(K))) - 1
    log(f"[P] means={tuple(means.shape)} sh={tuple(sh.shape)} -> sh_degree={sh_deg}")
    log(f"[P] scales  min/med/max = {scales.min():.5f}/{scales.median():.5f}/{scales.max():.5f}")
    log(f"[P] opacity min/med/max = {opac.min():.4f}/{opac.median():.4f}/{opac.max():.4f}")
    return means, quats, scales, opac, sh, sh_deg


from gsplat import rasterization  # noqa: E402


def render(means, quats, scales, opac, sh, sh_deg, viewmats, Ks, W, H):
    colors = sh if sh_deg > 0 else (sh[:, 0, :] * C0 + 0.5).clamp(0, 1)
    use_sh = sh_deg if sh_deg > 0 else None
    out = rasterization(
        means, quats, scales, opac, colors,
        viewmats, Ks, W, H, sh_degree=use_sh, render_mode="RGB",
    )
    rgb = out[0]
    if isinstance(rgb, list):
        rgb = rgb[0]
    if rgb.dim() == 4:
        rgb = rgb[0]                       # [C,H,W,3] -> [H,W,3]
    return rgb


def to_uint8(t):
    t = t.detach().float().cpu()
    if t.dim() == 3 and t.shape[0] == 3:      # CHW -> HWC
        t = t.permute(1, 2, 0)
    return (t.clamp(0, 1).numpy() * 255.0 + 0.5).astype(np.uint8)


def psnr(a_, b_):
    mse = float(((a_ - b_) ** 2).mean())
    return 99.0 if mse <= 1e-12 else 10.0 * math.log10(1.0 / mse)


dev = torch.device("cuda")
imgs = cache["imgs"][0].to(dev)                    # [S,3,H,W]  GT(预处理后)
c2w = cache["camera_poses"][0].to(dev)             # [S,4,4]
Ks = cache["camera_intrs"][0].to(dev)              # [S,3,3]
S, _, H, W = imgs.shape
viewmats = torch.linalg.inv(c2w)
log(f"[B] GT {S} 视图 {W}x{H};  相机 K[0]=\n{Ks[0].cpu().numpy().round(1)}")

# ViT 只用了 eff(=504) 长边, 而输入原生长边是 826 —— 精修可以按原生分辨率监督。
# 同一套 crop 预处理下变换近似纯缩放, 故按 sx/sy 同比缩放 K。
if a.gt and a.gt != W:
    from nodes.hyworld2.worldrecon.hyworldmirror.utils.inference_utils import (
        prepare_images_to_tensor,
    )
    hi = prepare_images_to_tensor(VIEWS, target_size=a.gt, resize_strategy="crop").to(dev)[0]
    H2, W2 = hi.shape[-2:]
    sx, sy = W2 / W, H2 / H
    Ks = Ks.clone()
    Ks[:, 0, 0] *= sx
    Ks[:, 0, 2] *= sx
    Ks[:, 1, 1] *= sy
    Ks[:, 1, 2] *= sy
    imgs = hi
    H, W = H2, W2
    log(f"[B] 监督分辨率提到 {W}x{H}  (sx={sx:.4f} sy={sy:.4f}, K 同比缩放)")

means, quats, scales, opac, sh, sh_deg = unpack(cache["splats"], None, dev)


@torch.no_grad()
def eval_all(tag):
    ps = []
    outs = []
    for i in range(S):
        rgb = render(means, quats, scales, opac, sh, sh_deg,
                     viewmats[i][None], Ks[i][None], W, H).clamp(0, 1)
        ps.append(psnr(rgb.permute(2, 0, 1), imgs[i]))
        outs.append(rgb)
    log(f"[{tag}] PSNR 逐视图: " + " ".join(f"{p:.2f}" for p in ps))
    log(f"[{tag}] PSNR 均值 = {sum(ps)/len(ps):.2f} dB")
    return ps, outs


ps0, out0 = eval_all("B-baseline")


def dump_ply(path, m, q, s, o, s_):
    """用与节点完全相同的 save_gs_ply 落盘, 保证与图内产物可直接对比。

    ⚠️ 两个坑都踩过, 都是"静默"的 —— 产物照样生成, 只是颜色/尺度不对:

    ① **必须传非批次的** [N,3] / [N,4] / [N]。`save_gs_ply` 内部按
    `quantile(scales.max(-1), 0.98, dim=0)` 算尺度阈值, 只在 unbatched
    时得到一个标量; 传 [1,N,3] 时 dim=0 是 batch 维, 会逐元素返回自身 ⇒ 掩码恒 True ⇒
    **那个"砍掉最大 2% 大高斯"的过滤会静默失效**。失效的后果肉眼可见: scale_max 从 0.0098
    涨到 0.3008, 房间外一看就是一圈大雾(四个变体对照见 _compare-0034-ply.py)。

    ② **rgbs 参数必须是 SH 的 DC 系数本身, 不能传已经 `*C0+0.5` 过的 RGB**。第四个参数
    被 `_build_gs_ply_data` **原样**写进 `f_dc_*`, 而 3DGS PLY 的 `f_dc_*` 定义就是 DC 系数,
    读取端一律再算一次 `0.5 + C0*f_dc` —— 本插件自己的 `process_ply_to_splat` 就是这么读的
    (`0.5 + SH_C0 * v["f_dc_0"]`), 浏览器视口(mkkellogg, 见
    `web/ply_advanced_gaussian/viewer.html` 的字段解读表)也一样。传 RGB 进去 = 变换做两遍:
    实测整间书房被抬到 DC 均值 [0.556, 0.546, 0.535](参考图是 [0.165, 0.136, 0.101]),
    亮度 +0.41、饱和度只剩 1/3.5 —— 视口和核心渲染里就是"参考图的颜色没进世界模型",
    一片中灰发白。正确值: 前馈/精修出来的 `sh[:, 0, :]`(均值约 -1.14)。
    """
    from nodes.hyworld2.worldrecon.hyworldmirror.utils.save_utils import save_gs_ply as _save
    from pathlib import Path as _P
    # s_ 形状 [N, K, 3], 第 0 个 SH 系数就是 DC; 这里**不做** C0 变换(见上 ②)
    _save(_P(path), m, s, q, s_[:, 0, :], o)
    log(f"  -> {path} ({os.path.getsize(path)/1e6:.1f} MB, {m.shape[0]:,} 高斯)")


# 拆变量: 节点被 token 预算压到 eff=406, 而本脚本用 mem_get_info 自己算到 eff=504 ——
# 所以精修版 118.5 万高斯 vs 图内 75.8 万, 差的是【分辨率】不是精修。
# 把前馈(未精修)的同一份也存成 PLY, 才能把这两个变量拆开。
if a.dump_baseline:
    dump_ply(os.path.join(OUTDIR, f"baseline_eff{cache['eff']}.ply"), means, quats, scales, opac, sh)

# 存 对拍图: 第一行 GT / 第二行 baseline
def tile(rows, path):
    from PIL import Image
    arr = np.concatenate([np.concatenate(r, axis=1) for r in rows], axis=0)
    Image.fromarray(arr).save(path)
    log(f"  -> {path}")


tile([[to_uint8(imgs[0]), to_uint8(imgs[1]), to_uint8(imgs[4])],
      [to_uint8(out0[0]), to_uint8(out0[1]), to_uint8(out0[4])]],
     os.path.join(OUTDIR, "cmp_baseline.png"))

if a.steps <= 0:
    log("[B] --steps 0, 只做基线; 加 --steps 300 做精修")
    raise SystemExit(0)

# ---------------------------------------------------------------- C. 光度精修
# 起点 = 前馈输出; 目标 = 8 张原生视图; 变量 = 高斯的 位置/旋转/尺度/透明度/颜色。
# 渲染走光栅化, 不受 ViT 的 token 预算限制 —— 这是绕开 504px 瓶颈的唯一通道。
import torch.nn as nn  # noqa: E402
from torch.optim import Adam  # noqa: E402

base_params = (means.clone(), quats.clone(), scales.clone(), opac.clone(), sh.clone())

geo = a.mode == "all"
means_p = nn.Parameter(means.clone(), requires_grad=geo)
quats_p = nn.Parameter(quats.clone(), requires_grad=geo)
logsc_p = nn.Parameter(torch.log(scales.clamp_min(1e-8)), requires_grad=geo)
opac_p = nn.Parameter(torch.logit(opac.clamp(1e-4, 1 - 1e-4)))
sh_p = nn.Parameter(sh.clone())

means0, logsc0, quats0 = means.clone(), torch.log(scales.clamp_min(1e-8)), quats.clone()
opac0 = opac.clone()
sh0 = sh.clone()

groups = [
    {"params": [opac_p], "lr": a.lr * 30.0},
    {"params": [sh_p], "lr": a.lr * 1.50},
]
if geo:
    groups = [
        {"params": [means_p], "lr": a.lr * 0.10},   # 3DGS 标准比例
        {"params": [quats_p], "lr": a.lr * 0.60},
        {"params": [logsc_p], "lr": a.lr * 3.00},
    ] + groups
opt = Adam(groups, eps=1e-15)


def current():
    q = quats_p / quats_p.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    return means_p, q, torch.exp(logsc_p), torch.sigmoid(opac_p), sh_p


log(f"[C] 精修 {a.steps} 步, mode={a.mode}, lr={a.lr}, reg={a.reg}, reg_opac={a.reg_opac}, "
    f"reg_color={a.reg_color}, prune_opac={a.prune_opac}, 每步监督 1 个视图")
t0 = time.perf_counter()
for step in range(a.steps):
    i = step % S
    m, q, sc, op, sh_ = current()
    rgb = render(m, q, sc, op, sh_, sh_deg, viewmats[i][None], Ks[i][None], W, H)
    gt = imgs[i].permute(1, 2, 0)
    loss = (rgb - gt).abs().mean()
    if a.reg and geo:
        # 信任域: 允许几何微调, 但不许偏离前馈解太远(否则新视角出伪影)
        loss = loss + a.reg * (
            (means_p - means0).pow(2).mean() * 1e3
            + (logsc_p - logsc0).pow(2).mean() * 1e-1
            + (1.0 - (quats_p * quats0).sum(-1)).pow(2).mean() * 1e-1
        )
    if a.reg_opac:
        # appearance 模式里 means/scales/quats 是冻结的, 唯一能"跑飞"的自由度就是不透明度:
        # 它一中位数往上飘, 软高斯就被"画实", 远看整体发灰发雾。给个信任域压住。
        loss = loss + a.reg_opac * (torch.sigmoid(opac_p) - opac0).pow(2).mean()
    if a.reg_color:
        # 同理压住颜色: 每步只看 1 个视角, 只在少数视角可见的高斯会被撑成极值(彩虹色),
        # DC-only 渲染(浏览器视口 / 核心 RenderSplat 都是)里就是墙角上的彩色噪点。
        loss = loss + a.reg_color * (sh_p[:, 0, :] - sh0[:, 0, :]).pow(2).mean()
    opt.zero_grad(set_to_none=True)
    loss.backward()
    opt.step()
    if (step + 1) % 50 == 0 or step == 0:
        log(f"[C] step {step+1}/{a.steps}  L1={loss.item():.4f}  {time.perf_counter()-t0:.0f}s")

means, quats, scales, opac, sh = [t.detach() for t in current()]
ps1, out1 = eval_all("C-refined")

if a.prune_opac > 0:
    keep = opac >= a.prune_opac
    log(f"[C] 剪枝 opac < {a.prune_opac}: 剪掉 {int((~keep).sum()):,} 个 "
        f"({100 * float((~keep).float().mean()):.1f}%), 剩 {int(keep.sum()):,}")
    means, quats, scales, opac, sh = means[keep], quats[keep], scales[keep], opac[keep], sh[keep]
    eval_all("D-pruned")

log(f"[C] 尺度 精修前 med/max = {base_params[2].median():.4f}/{base_params[2].max():.4f}"
    f"  -> 精修后 {scales.median():.4f}/{scales.max():.4f}")
log(f"[C] 透明度 精修前 med = {base_params[3].median():.4f} -> 精修后 {opac.median():.4f}")

# 新视角体检: 8 个训练视角 PSNR 高 ≠ 3D 资产好。在相邻训练机位之间插值出"没见过的角度",
# 若精修只是把高斯撑成对准训练机位的广告牌, 这里会明显崩。
def novel_cams():
    out = []
    for i in range(0, S, 2):
        j = (i + 1) % S
        Ra, Rb = c2w[i][:3, :3], c2w[j][:3, :3]
        U, _, Vt = torch.linalg.svd(Ra + Rb)      # 旋转矩阵的正交化平均 = 中间偏航角
        Rm = U @ Vt
        if torch.linalg.det(Rm) < 0:
            Vt[-1] *= -1
            Rm = U @ Vt
        c = torch.eye(4, device=dev)
        c[:3, :3] = Rm
        c[:3, 3] = (c2w[i][:3, 3] + c2w[j][:3, 3]) / 2
        out.append(torch.linalg.inv(c)[None])
    return out


def novel_row(params, tag):
    m, q, sc, op, s_ = params
    row = []
    with torch.no_grad():
        for v in novel_cams():
            row.append(to_uint8(render(m, q, sc, op, s_, sh_deg, v, Ks[0][None], W, H).clamp(0, 1)))
    log(f"[V] {tag} 新视角 {len(row)} 张")
    return row


nov_base = novel_row(base_params, "baseline")
nov_ref = novel_row((means, quats, scales, opac, sh), "refined")
tile([nov_base, nov_ref], os.path.join(OUTDIR, "novel_views.png"))

tile([[to_uint8(imgs[0]), to_uint8(imgs[1]), to_uint8(imgs[4])],
      [to_uint8(out0[0]), to_uint8(out0[1]), to_uint8(out0[4])],
      [to_uint8(out1[0]), to_uint8(out1[1]), to_uint8(out1[4])]],
     os.path.join(OUTDIR, "cmp_refined.png"))
log(f"[C] 提升 {sum(ps0)/len(ps0):.2f} -> {sum(ps1)/len(ps1):.2f} dB")

# 存精修后的 PLY 供 0034 使用 (只把这个 3D 资产写进产物目录, 对拍图留在 scripts\)
os.makedirs(a.asset_dir, exist_ok=True)
gs_ply = os.path.join(a.asset_dir, f"{a.out_name}.ply")
dump_ply(gs_ply, means, quats, scales, opac, sh)
log(f"[OUT] {gs_ply}")
