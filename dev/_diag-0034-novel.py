"""在相邻训练机位之间插值出"没见过的角度", 对比多份 PLY 是否真收敛还是过拟合。

用法(隔离环境解释器, cwd = 插件目录):
  <pixi env>\python.exe custom_nodes\ComfyUI-FallingTS\dev\_diag-0034-novel.py <label=path> [<label=path> ...]
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import os
import sys

import numpy as np
import torch

PLUGIN = str(_COMFY / "custom_nodes" / "ComfyUI-HYWM2")
COMFYUI = str(_COMFY / "ComfyUI")
for p in (COMFYUI, PLUGIN):
    if p not in sys.path:
        sys.path.append(p)

C0 = 0.28209479177387814
PREDS = str(_COMFY / "ComfyUI" / "temp" / "worldrefine" / "8723b9869474bd13" / "preds.pt")
OUT = str(_COMFY / "scripts" / "_out-0034-refine" / "novel_cmp.png")
PAIRS = [x.split("=", 1) for x in sys.argv[1:]]
if not PAIRS:
    raise SystemExit("用法: _diag-0034-novel.py <label=ply> ...")

from gsplat import rasterization  # noqa: E402


def log(*m):
    print(*m, flush=True)


def read_ply(path):
    raw = open(path, "rb").read()
    end = raw.index(b"end_header\n") + len(b"end_header\n")
    names, count = [], 0
    for line in raw[:end].decode("ascii", "replace").splitlines():
        p = line.split()
        if p[:2] == ["element", "vertex"]:
            count = int(p[2])
        elif p[:1] == ["property"]:
            names.append(p[-1])
    buf = np.frombuffer(raw[end:end + count * 4 * len(names)], dtype="<f4").reshape(count, len(names))
    return {n: buf[:, i].copy() for i, n in enumerate(names)}


cache = torch.load(PREDS, weights_only=False, map_location="cpu")
dev = torch.device("cuda")
c2w = cache["camera_poses"][0].to(dev)
Ks = cache["camera_intrs"][0].to(dev)
S, _, H, W = cache["imgs"][0].shape


def novel_cams():
    out = []
    for i in range(0, S, 2):
        j = (i + 1) % S
        Ra, Rb = c2w[i][:3, :3], c2w[j][:3, :3]
        U, _, Vt = torch.linalg.svd(Ra + Rb)
        Rm = U @ Vt
        if torch.linalg.det(Rm) < 0:
            Vt[-1] *= -1
            Rm = U @ Vt
        c = torch.eye(4, device=dev)
        c[:3, :3] = Rm
        c[:3, 3] = (c2w[i][:3, 3] + c2w[j][:3, 3]) / 2
        out.append(torch.linalg.inv(c)[None])
    return out


CAMS = novel_cams()
log(f"[cam] 插值出 {len(CAMS)} 个新机位 (训练机位之间的中间偏航角)")


def render(f, vm):
    means = torch.tensor(np.stack([f["x"], f["y"], f["z"]], 1), device=dev)
    scales = torch.exp(torch.tensor(np.stack([f["scale_0"], f["scale_1"], f["scale_2"]], 1), device=dev))
    quats = torch.tensor(np.stack([f["rot_0"], f["rot_1"], f["rot_2"], f["rot_3"]], 1), device=dev)
    quats = quats / quats.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    alpha = torch.sigmoid(torch.tensor(f["opacity"], device=dev))
    dc = torch.tensor(np.stack([f["f_dc_0"], f["f_dc_1"], f["f_dc_2"]], 1), device=dev)
    colors = (dc * C0 + 0.5).clamp(0, 1)
    out = rasterization(means, quats, scales, alpha, colors, vm, Ks[0][None], W, H,
                        sh_degree=None, render_mode="RGB")
    rgb = out[0]
    if isinstance(rgb, list):
        rgb = rgb[0]
    if rgb.dim() == 4:
        rgb = rgb[0]
    return (rgb.clamp(0, 1).cpu().numpy() * 255 + 0.5).astype(np.uint8)


rows, labels = [], []
with torch.no_grad():
    for label, path in PAIRS:
        f = read_ply(path)
        rows.append([render(f, vm) for vm in CAMS])
        labels.append(label)
        log(f"  {label:<22} {len(f['x']):>9,} 点  新视角 {len(CAMS)} 张")

from PIL import Image  # noqa: E402

Image.fromarray(np.concatenate([np.concatenate(r, axis=1) for r in rows], axis=0)).save(OUT)
log(f"  -> {OUT}   (自上而下: {' / '.join(labels)})")
