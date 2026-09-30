"""0034 去重叠实验: 把多视图各自铺的"壳"按体素合并, 看双重曝光能不能收敛。

口径: alpha = sigmoid(opacity 字段)(= 视口实际看到的 α), 颜色/尺度按 α 加权平均,
合并后 α 用 alpha 合成律 1-Π(1-α_i)(等价于"两层各 0.19 的壳 -> 0.34")。

用法(隔离环境解释器, cwd = 插件目录):
  <pixi env>\python.exe custom_nodes\ComfyUI-FallingTS\dev\_diag-0034-fuse.py
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
PLY = str(_COMFY / "media" / "七纹刻印" / "0034_世界模型" / "0034_世界模型_世界3DGS.ply")
PREDS = str(_COMFY / "ComfyUI" / "temp" / "worldrefine" / "8723b9869474bd13" / "preds.pt")
OUT = str(_COMFY / "scripts" / "_out-0034-refine" / "fuse_test.png")
VOXELS = [0.003, 0.006, 0.012, 0.025]

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
alpha = torch.sigmoid(torch.tensor(f["opacity"], device=dev))
dc = torch.tensor(np.stack([f["f_dc_0"], f["f_dc_1"], f["f_dc_2"]], 1), device=dev)
colors = (dc * C0 + 0.5).clamp(0, 1)

cache = torch.load(PREDS, weights_only=False, map_location="cpu")
imgs = cache["imgs"][0].to(dev)
viewmats = torch.linalg.inv(cache["camera_poses"][0].to(dev))
Ks = cache["camera_intrs"][0].to(dev)
S, _, H, W = imgs.shape
gt = imgs.permute(0, 2, 3, 1)
PICK = [0, 1, 4, 5]
log(f"[PLY] {count:,} 高斯, α med={float(alpha.median()):.3f}")


def voxel_merge(voxel):
    key = torch.floor(means / voxel).to(torch.int64)
    key = key - key.min(0).values
    dims = key.max(0).values + 1
    flat = (key[:, 0] * dims[1] + key[:, 1]) * dims[2] + key[:, 2]
    uniq, inv = torch.unique(flat, return_inverse=True)
    K = uniq.numel()
    w = alpha.clamp_min(1e-6)

    def wsum(t, extra=None):
        src = t if extra is None else t * extra
        out = torch.zeros((K, t.shape[1]), device=dev)
        out.index_add_(0, inv, src)
        ws = torch.zeros(K, device=dev).index_add_(0, inv, w)
        return out / ws.clamp_min(1e-12).unsqueeze(1)

    m2 = wsum(means)
    s2 = wsum(scales)
    c2 = wsum(colors)
    # 四元数必须先统一定向(q 与 -q 是同一个旋转, 直接加权平均会互相抵消)
    n = means.shape[0]
    first = torch.full((K,), n, dtype=torch.long, device=dev)
    first.scatter_reduce_(0, inv, torch.arange(n, device=dev), reduce="amin")
    qref = quats[first]
    sign = torch.where((quats * qref[inv]).sum(-1) < 0, -1.0, 1.0)
    q2 = wsum(quats * sign.unsqueeze(1))
    q2 = q2 / q2.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    # α 合成: 1 - Π(1-α_i)
    log1p = torch.zeros(K, device=dev).index_add_(0, inv, torch.log1p(-alpha.clamp(max=1 - 1e-6)))
    a2 = 1.0 - torch.exp(log1p)
    return m2, q2, s2, a2, c2, K


def render(m, q, s, a, c, i):
    out = rasterization(m, q, s, a, c, viewmats[i][None], Ks[i][None], W, H,
                        sh_degree=None, render_mode="RGB")
    rgb = out[0]
    if isinstance(rgb, list):
        rgb = rgb[0]
    if rgb.dim() == 4:
        rgb = rgb[0]
    return rgb.clamp(0, 1)


def psnr(row):
    ps = []
    for k, i in enumerate(PICK):
        mse = float(((row[k] - gt[i]) ** 2).mean())
        ps.append(10.0 * math.log10(1.0 / max(mse, 1e-12)))
    return ps


rows = [[(gt[i].cpu().numpy() * 255 + 0.5).astype(np.uint8) for i in PICK]]
labels = ["GT"]
with torch.no_grad():
    base = [render(means, quats, scales, alpha, colors, i) for i in PICK]
    rows.append([(r.cpu().numpy() * 255 + 0.5).astype(np.uint8) for r in base])
    labels.append("原样")
    log(f"  原样                    PSNR " + " ".join(f"{p:.2f}" for p in psnr(base))
        + f"  均值 {sum(psnr(base)) / 4:.2f}")
    for v in VOXELS:
        m2, q2, s2, a2, c2, K = voxel_merge(v)
        row = [render(m2, q2, s2, a2, c2, i) for i in PICK]
        p = psnr(row)
        rows.append([(r.cpu().numpy() * 255 + 0.5).astype(np.uint8) for r in row])
        labels.append(f"体素{v * 1000:.0f}mm")
        log(f"  体素合并 {v * 1000:4.0f}mm  {K:>8,} 点  PSNR "
            + " ".join(f"{x:.2f}" for x in p) + f"  均值 {sum(p) / 4:.2f}")

from PIL import Image  # noqa: E402

grid = np.concatenate([np.concatenate(r, axis=1) for r in rows], axis=0)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
Image.fromarray(grid).save(OUT)
log(f"  -> {OUT}   (行: {', '.join(labels)})")
