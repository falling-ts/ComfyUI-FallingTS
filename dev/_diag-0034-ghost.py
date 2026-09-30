"""0034 重叠诊断: 透明度 vs 几何重复。

对同一份 PLY / 同一批机位渲三个变体, 看"重叠"是否随不透明度改变:
  A 原样      = sigmoid(field)            (浏览器视口/核心渲染的口径)
  B 强制不透明 = 0.99                     几何重复会在这里暴露得更清楚
  C 半透明     = A * 0.35                 透明层叠会变淡, 几何鬼影不会消失

用法(隔离环境解释器, gsplat 在那; cwd 必须是插件目录):
  <pixi env>\python.exe custom_nodes\ComfyUI-FallingTS\dev\_diag-0034-ghost.py <ply> [<preds.pt>] [<out.png>]
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

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
PLY = sys.argv[1] if len(sys.argv) > 1 else (
    str(_COMFY / "media" / "七纹刻印" / "0034_世界模型" / "0034_世界模型_世界3DGS.ply"))
PREDS = sys.argv[2] if len(sys.argv) > 2 else (
    str(_COMFY / "ComfyUI" / "temp" / "worldrefine" / "8723b9869474bd13" / "preds.pt"))
OUT = sys.argv[3] if len(sys.argv) > 3 else str(_COMFY / "scripts" / "_out-0034-refine" / "ghost_test.png")

from gsplat import rasterization  # noqa: E402


def log(*m):
    print(*m, flush=True)


raw = open(PLY, "rb").read()
end = raw.index(b"end_header\n") + len(b"end_header\n")
names, count = [], 0
for line in raw[:end].decode("ascii", "replace").splitlines():
    p = line.split()
    if p[:2] == ["element", "vertex"]:
        count = int(p[2])
    elif p[:1] == ["property"]:
        names.append(p[-1])
buf = np.frombuffer(raw[end:end + count * 4 * len(names)], dtype="<f4").reshape(count, len(names))
f = {n: buf[:, i].copy() for i, n in enumerate(names)}

dev = torch.device("cuda")
means = torch.tensor(np.stack([f["x"], f["y"], f["z"]], 1), device=dev)
scales = torch.exp(torch.tensor(np.stack([f["scale_0"], f["scale_1"], f["scale_2"]], 1), device=dev))
quats = torch.tensor(np.stack([f["rot_0"], f["rot_1"], f["rot_2"], f["rot_3"]], 1), device=dev)
quats = quats / quats.norm(dim=-1, keepdim=True).clamp_min(1e-8)
op0 = torch.sigmoid(torch.tensor(f["opacity"], device=dev))
dc = torch.tensor(np.stack([f["f_dc_0"], f["f_dc_1"], f["f_dc_2"]], 1), device=dev)
colors = (dc * C0 + 0.5).clamp(0, 1)
log(f"[PLY] {count:,} 高斯; op0 med={float(op0.median()):.3f} "
    f"p05={float(op0.quantile(0.05)):.3f} p95={float(op0.quantile(0.95)):.3f}")

cache = torch.load(PREDS, weights_only=False, map_location="cpu")
imgs = cache["imgs"][0].to(dev)
c2w = cache["camera_poses"][0].to(dev)
Ks = cache["camera_intrs"][0].to(dev)
viewmats = torch.linalg.inv(c2w)
S, _, H, W = imgs.shape
log(f"[cam] {PREDS}  GT {S} 视图 {W}x{H}")

VARIANTS = {
    "A 原样": op0,
    "B op=0.99": torch.full_like(op0, 0.99),
    "C op=0.35x": op0 * 0.35,
    "D 只留 op>=0.5": None,
}
KEEP = op0 >= 0.5
log(f"[PLY] op>=0.5 的高斯 {int(KEEP.sum()):,} / {count:,} ({float(KEEP.float().mean()) * 100:.1f}%)")


def render(view_idx, op, keep=None):
    m, q, s, c = means, quats, scales, colors
    if keep is not None:
        m, q, s, c, o = m[keep], q[keep], s[keep], c[keep], op[keep]
    else:
        o = op
    out = rasterization(m, q, s, o, c, viewmats[view_idx][None], Ks[view_idx][None], W, H,
                        sh_degree=None, render_mode="RGB")
    rgb = out[0]
    if isinstance(rgb, list):
        rgb = rgb[0]
    if rgb.dim() == 4:
        rgb = rgb[0]
    return rgb.clamp(0, 1)


PICK = [0, 1, 4, 5]
gt = imgs.permute(0, 2, 3, 1)
rows = [[(gt[i].cpu().numpy() * 255 + 0.5).astype(np.uint8) for i in PICK]]
log("[PSNR] 相对参考图:")
with torch.no_grad():
    for name, op in VARIANTS.items():
        ps, row = [], []
        for i in PICK:
            keep = KEEP if name.startswith("D") else None
            r = render(i, op if op is not None else op0, keep)
            mse = float(((r - gt[i]) ** 2).mean())
            ps.append(10.0 * math.log10(1.0 / max(mse, 1e-12)))
            row.append((r.cpu().numpy() * 255 + 0.5).astype(np.uint8))
        rows.append(row)
        log(f"  {name:<14} " + " ".join(f"{p:.2f}" for p in ps) + f"   均值 {sum(ps) / len(ps):.2f} dB")

from PIL import Image  # noqa: E402

grid = np.concatenate([np.concatenate(r, axis=1) for r in rows], axis=0)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
Image.fromarray(grid).save(OUT)
log(f"  -> {OUT}   (行: GT / " + " / ".join(VARIANTS) + ")")
