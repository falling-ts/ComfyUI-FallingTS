"""验收: 产出的世界模型 PLY 里到底有没有"参考图的颜色与布局"。

口径 = **读者的口径**: 从 PLY 的字段还原高斯(scale=exp/logit/sigmoid、rot 归一化、
f_dc 再算 `0.5 + C0*f_dc`), 用前馈预测出来的 8 个机位(DC 单色渲染, 等价于浏览器视口
`sphericalHarmonicsDegree=0`)渲一遍, 和 8 张参考图并排落成一张对拍图。

用法(必须用隔离环境解释器, gsplat 在那):
  C:\\Users\\zghyu\\AppData\\Local\\Programs\\comfy-env\\.pixi\\envs\\hywm2-nodes\\python.exe
  custom_nodes\\ComfyUI-FallingTS\\dev\\_verify-0034-color.py <ply> [<preds.pt>] [<out.png>]
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import argparse
import math
import os
import sys

import numpy as np
import torch

PLUGIN = str(_COMFY / "custom_nodes" / "ComfyUI-HYWM2")
COMFYUI = str(_COMFY / "ComfyUI")
if COMFYUI not in sys.path:
    sys.path.append(COMFYUI)
if PLUGIN not in sys.path:
    sys.path.insert(0, PLUGIN)

C0 = 0.28209479177387814
SLOTS = ["前面", "前右", "右面", "后右", "后面", "后左", "左面", "前左"]
AP = argparse.ArgumentParser()
AP.add_argument("ply")
AP.add_argument("preds", nargs="?", default=str(_COMFY / "scripts" / "_cache-0034-preds.pt"))
AP.add_argument("out", nargs="?", default=str(_COMFY / "scripts" / "_out-0034-refine" / "dc_verify.png"))
a = AP.parse_args()

from gsplat import rasterization  # noqa: E402


def log(*m):
    print(*m, flush=True)


def read_ply(path):
    """极简 3DGS PLY 读取: binary_little_endian + f4 属性。"""
    raw = open(path, "rb").read()
    end = raw.index(b"end_header\n") + len(b"end_header\n")
    names, count = [], 0
    for line in raw[:end].decode("ascii", "replace").splitlines():
        p = line.split()
        if p[:2] == ["element", "vertex"]:
            count = int(p[2])
        elif p[:1] == ["property"]:
            names.append(p[-1])
    buf = np.frombuffer(raw[end:end + count * 4 * len(names)],
                        dtype="<f4").reshape(count, len(names))
    return {n: buf[:, i].copy() for i, n in enumerate(names)}, names


f, names = read_ply(a.ply)
has_rest = any(n.startswith("f_rest_") for n in names)
log(f"[PLY] {a.ply}")
log(f"[PLY] {len(f['x']):,} 高斯, 属性 {len(names)} 个, f_rest: {'有' if has_rest else '无(DC-only)'}")

dev = torch.device("cuda")
means = torch.tensor(np.stack([f["x"], f["y"], f["z"]], 1), device=dev)
scales = torch.exp(torch.tensor(np.stack([f["scale_0"], f["scale_1"], f["scale_2"]], 1), device=dev))
quats = torch.tensor(np.stack([f["rot_0"], f["rot_1"], f["rot_2"], f["rot_3"]], 1), device=dev)
quats = quats / quats.norm(dim=-1, keepdim=True).clamp_min(1e-8)
opac = torch.sigmoid(torch.tensor(f["opacity"], device=dev))
dc = torch.tensor(np.stack([f["f_dc_0"], f["f_dc_1"], f["f_dc_2"]], 1), device=dev)
colors = (dc * C0 + 0.5).clamp(0, 1)          # ← 与所有读取端一致的那一步

log(f"[PLY] f_dc 均值 {dc.mean(0).cpu().numpy().round(4)}")
log(f"[PLY] 解码后 DC 色均值 {colors.mean(0).cpu().numpy().round(3)} "
    f"中位 {colors.median(0).values.cpu().numpy().round(3)}")
log(f"[PLY] 解码后亮度 p05/p50/p95 = "
    f"{np.percentile(colors.mean(1).cpu().numpy(), [5, 50, 95]).round(3)} "
    f"饱和度中位 {float(colors.max(1).values.sub(colors.min(1).values).median()):.4f}")
log(f"[PLY] 不透明度中位 {float(opac.median()):.3f}  scale 中位 {float(scales.median()):.4f}")

cache = torch.load(a.preds, weights_only=False, map_location="cpu")
imgs = cache["imgs"][0].to(dev)
c2w = cache["camera_poses"][0].to(dev)
Ks = cache["camera_intrs"][0].to(dev)
viewmats = torch.linalg.inv(c2w)
S, _, H, W = imgs.shape
log(f"[cam] 缓存 {a.preds}  eff={cache.get('eff')}  GT {S} 视图 {W}x{H}")


def render(i):
    out = rasterization(means, quats, scales, opac, colors,
                        viewmats[i][None], Ks[i][None], W, H,
                        sh_degree=None, render_mode="RGB")
    rgb = out[0]
    if isinstance(rgb, list):
        rgb = rgb[0]
    if rgb.dim() == 4:
        rgb = rgb[0]
    return rgb.clamp(0, 1)


gt_rgb = imgs.permute(0, 2, 3, 1)
ps = []
rows_gt, rows_r = [], []
with torch.no_grad():
    for i in range(S):
        r = render(i)
        mse = float(((r - gt_rgb[i]) ** 2).mean())
        ps.append(99.0 if mse <= 1e-12 else 10.0 * math.log10(1.0 / mse))
        rows_gt.append((gt_rgb[i].cpu().numpy() * 255 + 0.5).astype(np.uint8))
        rows_r.append((r.cpu().numpy() * 255 + 0.5).astype(np.uint8))
log("[PSNR] 参考口径(DC 单色, 视口同款) 逐视图: " + " ".join(f"{p:.2f}" for p in ps))
log(f"[PSNR] 均值 {sum(ps)/len(ps):.2f} dB  (修复前那份定格在 ~24 dB 上下)")

gt_mean = np.concatenate([x.reshape(-1, 3) for x in rows_gt], 0).mean(0) / 255.0
r_mean = np.concatenate([x.reshape(-1, 3) for x in rows_r], 0).mean(0) / 255.0
log(f"[色差] 渲染均值 {r_mean.round(3)}  vs  参考图均值 {gt_mean.round(3)}  "
    f"L1={float(np.abs(r_mean - gt_mean).mean()):.3f}")


def tile(rows, path, cols=4):
    from PIL import Image
    lines = []
    for i in range(0, len(rows), cols):
        chunk = rows[i:i + cols]
        while len(chunk) < cols:
            chunk.append(np.zeros_like(chunk[0]))
        lines.append(np.concatenate(chunk, axis=1))
    Image.fromarray(np.concatenate(lines, axis=0)).save(path)
    log(f"  -> {path}")


os.makedirs(os.path.dirname(a.out), exist_ok=True)
tile(rows_gt + rows_r, a.out)              # 上半 = 参考图, 下半 = 世界模型渲染
log("[图] 上四张 = 参考图 前面/前右/右面/后右; 下四张 = 世界模型同机位渲染")
