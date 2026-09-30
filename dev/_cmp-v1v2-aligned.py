"""公平 A/B: 在 v1/v2 两张长图里各自扫出「同一帧内容」所在的偏航角, 再同角度切视角并排。

这样左右两半显示的是**同一块场景**, 比的是清晰度/重影, 而不是"各切了一块"。
用法: .venv\\Scripts\\python.exe custom_nodes\\ComfyUI-FallingTS\\dev\\_cmp-v1v2-aligned.py [帧号, 默认121]
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import importlib.util
import math
import sys

import cv2
import numpy as np
import torch
import torch.nn.functional as F

sys.path.append(str(_COMFY / "ComfyUI"))
sys.path.append(str(_COMFY))
spec = importlib.util.spec_from_file_location(
    "wpn5", str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "world-panorama" / "nodes.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

VID = str(_COMFY / "media" / "七纹刻印" / "0031_首帧场景" / "00001_书房旋镜视频.mp4")
OUT = str(_COMFY / "scripts" / "_out-pano")
HFOV = 106.3
IFRAME = int(sys.argv[1]) if len(sys.argv) > 1 else 121


def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(p)


cap = cv2.VideoCapture(VID)
frames = []
while True:
    ok, f = cap.read()
    if not ok:
        break
    frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
cap.release()
n = len(frames)
size = frames[0].shape[1]
r0 = (size - frames[0].shape[0]) // 2
target = frames[IFRAME]

v2 = torch.from_numpy(cv2.cvtColor(imread_u(OUT + r"\v2-long.png"), cv2.COLOR_BGR2RGB)
                      .astype(np.float32) / 255.0)
v1b = imread_u(OUT + r"\0034-360长图-预览.png")
g = cv2.cvtColor(v1b, cv2.COLOR_BGR2GRAY)
rr = np.flatnonzero(g.max(axis=1) > 6)
v1b = cv2.cvtColor(v1b[rr[0]:rr[-1] + 1], cv2.COLOR_BGR2RGB)
v1 = torch.from_numpy(v1b.astype(np.float32) / 255.0)


def sample_new(yaw_deg):
    img, _, _ = mod.FallingTSWorldPanoramaViewsNode._sample(
        v2, math.radians(yaw_deg), 0.0, math.radians(HFOV), size, 0.0, 72.6)
    v = (img.numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)
    return v[r0:r0 + frames[0].shape[0]]


def sample_v1(yaw_deg):
    """v1 的原始口径: 2:1 等距圆柱 + 上行=地的旧映射。"""
    h, w, _ = v1.shape
    f_px = (size / 2.0) / math.tan(math.radians(HFOV) / 2)
    c = (size - 1) / 2.0
    u = torch.arange(size, dtype=torch.float32)
    uu, vv = torch.meshgrid(u, u, indexing="xy")
    dx, dy = (uu - c) / f_px, (vv - c) / f_px
    rc = F.normalize(torch.stack([dx, dy, torch.ones_like(dx)], dim=-1), dim=-1)
    yaw = math.radians(yaw_deg)
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    R = torch.tensor([[cy_, 0, sy_], [0, 1, 0], [-sy_, 0, cy_]])
    rw = torch.einsum("ij,hwj->hwi", R, rc)
    eq_x = (torch.atan2(rw[..., 0], rw[..., 2]) / math.pi + 1.0) * (w - 1) / 2.0
    eq_y = (0.5 - torch.asin(torch.clamp(rw[..., 1], -1, 1)) / math.pi) * (h - 1)
    gr = torch.stack([eq_x / (w - 1) * 2 - 1, eq_y / (h - 1) * 2 - 1], dim=-1).unsqueeze(0)
    s = F.grid_sample(v1.permute(2, 0, 1).unsqueeze(0), gr, mode="bilinear",
                      padding_mode="border", align_corners=True)
    v = (s[0].permute(1, 2, 0).numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)
    return v[r0:r0 + frames[0].shape[0]]


def ncc(a, b):
    a = a.astype(np.float32) - a.mean()
    b = b.astype(np.float32) - b.mean()
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float((a * b).sum() / d) if d > 0 else 0.0


def scan(fn, label):
    best = (-9, None)
    for cand in np.arange(-380.0, 20.0, 2.0):
        v = ncc(fn(cand), target)
        if v > best[0]:
            best = (v, cand)
    c0 = best[1]
    for cand in np.arange(c0 - 2.5, c0 + 2.51, 0.25):
        v = ncc(fn(cand), target)
        if v > best[0]:
            best = (v, cand)
    print(f"{label}: 该帧内容位于 yaw={best[1]:+.2f}°, NCC={best[0]:.3f}")
    return best[1], best[0]


y2, n2 = scan(sample_new, "v2 (winner-take-all)")
y1, n1 = scan(sample_v1, "v1 (混合)")
va, vb = sample_v1(y1), sample_new(y2)
lap = []
for tag, im in (("v1", va), ("v2", vb)):
    lg = cv2.Laplacian(cv2.cvtColor(im, cv2.COLOR_RGB2GRAY), cv2.CV_32F).var()
    lap.append(lg)
    print(f"{tag} 锐度(拉普拉斯方差) = {lg:.1f}")
print(f"锐度比 v2/v1 = {lap[1] / max(lap[0], 1e-6):.2f}")

h = va.shape[0]
cmp_img = np.concatenate([cv2.cvtColor(va, cv2.COLOR_RGB2BGR),
                          np.full((h, 6, 3), 60, np.uint8),
                          cv2.cvtColor(vb, cv2.COLOR_RGB2BGR)], axis=1)
cv2.putText(cmp_img, f"v1 blend (NCC {n1:.2f}, blur {lap[0]:.0f})", (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
cv2.putText(cmp_img, f"v2 winner-take-all (NCC {n2:.2f}, blur {lap[1]:.0f})",
            (va.shape[1] + 16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
imwrite_u(OUT + r"\v2-cmp-aligned.png", cmp_img)
print("输出:", OUT + r"\v2-cmp-aligned.png", cmp_img.shape)
