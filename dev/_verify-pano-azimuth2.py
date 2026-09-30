"""长图方位标定 v2: 不再假设匀速旋转。

1) 用 ORB 位移从第 0 帧逐段累加, 独立测出**每个测试帧的真实转角**(位移法, 与长图无关);
2) 在长图上把该帧扫一遍偏航角, 找 NCC 峰值所在 yaw;
3) 两者若一致(±3°) ⇒ 长图的方位映射正确; 顺带把旋转曲线打出来看是否匀速。
用法: .venv\\Scripts\\python.exe custom_nodes\\ComfyUI-FallingTS\\dev\\_verify-pano-azimuth2.py
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import importlib.util
import math
import sys

import cv2
import numpy as np
import torch

sys.path.append(str(_COMFY / "ComfyUI"))
sys.path.append(str(_COMFY))
spec = importlib.util.spec_from_file_location(
    "wpn4", str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "world-panorama" / "nodes.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

VID = str(_COMFY / "media" / "七纹刻印" / "0031_首帧场景" / "00001_书房旋镜视频.mp4")
PANO = str(_COMFY / "scripts" / "_out-pano" / "v2-long.png")
HFOV, BAND = 106.3, 72.6

pano = torch.from_numpy(cv2.cvtColor(
    cv2.imdecode(np.fromfile(PANO, dtype=np.uint8), cv2.IMREAD_COLOR),
    cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0)

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

# ── 1) 位移法独立测转角(每 2 帧一步, ORB 中位位移) ──
orb = cv2.ORB_create(3000, scaleFactor=1.2, nlevels=8, fastThreshold=10)
step, prev = 2, None
dxs = []
for k in range(0, n, step):
    k2, d2 = orb.detectAndCompute(cv2.cvtColor(frames[k], cv2.COLOR_RGB2GRAY), None)
    if prev is not None:
        dxs.append(mod._match_dx(prev[0], prev[1], k2, d2))
    prev = (k2, d2)
adx = np.abs([x for x in dxs if x is not None])
W = frames[0].shape[1]
lo, hi = 20.0, 1e5
for _ in range(80):                                  # 闭环: Σ atan(|dx|/f) = 2π
    mid = (lo + hi) / 2
    if float(np.sum(np.arctan(adx / mid))) > 2 * math.pi:
        lo = mid
    else:
        hi = mid
f_ref = (lo + hi) / 2
print(f"位移法闭环: f_ref={f_ref:.1f}px (h_fov={2*math.degrees(math.atan(W/2/f_ref)):.1f}°)")
yaw_orb = {}
acc = 0.0
for idx, x in enumerate(dxs):
    if x is not None:
        acc += -math.atan(x / f_ref)
    yaw_orb[(idx + 1) * step] = acc
yaw_orb[min(yaw_orb.keys(), key=lambda z: abs(z))] = 0.0
yaw_orb[0] = 0.0

VIEW = mod.FallingTSWorldPanoramaViewsNode


def view(yaw_deg):
    img, _, _ = VIEW._sample(pano, math.radians(yaw_deg), 0.0, math.radians(HFOV), size, 0.0, BAND)
    v = (img.numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)
    return v[r0:r0 + frames[0].shape[0]]


def ncc(a, b):
    a = a.astype(np.float32) - a.mean()
    b = b.astype(np.float32) - b.mean()
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float((a * b).sum() / d) if d > 0 else 0.0


print("\n帧号   位移法yaw   长图扫出的yaw   峰值NCC   yaw差")
diffs = []
for i in (0, 30, 61, 91, 121, 152, 182, 212, 242):
    y0 = yaw_orb.get(i, -360.0 * i / (n - 1))
    best = (-9, None)
    for cand in np.arange(-380.0, 20.0, 2.0):        # 粗扫
        v = ncc(view(cand), frames[i])
        if v > best[0]:
            best = (v, cand)
    coarse = best[1]
    for cand in np.arange(coarse - 2.5, coarse + 2.51, 0.25):   # 细扫
        v = ncc(view(cand), frames[i])
        if v > best[0]:
            best = (v, cand)
    d = best[1] - y0
    diffs.append(d)
    print(f"{i:4d}  {y0:9.2f}  {best[1]:+13.2f}   {best[0]:.3f}   {d:+7.2f}")
diffs = np.array(diffs)
print(f"\nyaw 差: 中位 {np.median(diffs):+.2f}°, 最大 |{np.abs(diffs).max():.2f}|°")
print("判据: 中位 |差| ≤ 3° ⇒ 长图方位映射正确(与位移法一致)")
print("\n位移法旋转曲线(每 24 帧):",
      [f"{i}:{math.degrees(yaw_orb.get(i, 0)):.0f}°" for i in range(0, n - 1, 24)])
