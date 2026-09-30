"""把 0031 的 360° 旋镜视频展成「球形四周长图」(圆柱展开)。

为什么能成立: 视频是绕光心的纯旋转 —— 相邻帧只差一个水平位移, 用 ORB 匹配求位移,
累加成每帧的偏航角 yaw_i; 焦距 f 由「整段正好 360°」这条约束用二分法解出来
(即 Σ atan(dx_i/f) = 2π)。再按圆柱投影把每帧重采样到同一张长图:
    对输出列 θ:  u = cx + f·tan(θ - yaw_i)
    对输出行 y:  v = cy + f·y   (可与列分离 ⇒ 一次 remap 即可)
帧间重叠区按到帧中心的角度做羽化混合。产物落 scripts\\_out-pano\\(临时目录)。
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import glob
import os
import subprocess
import sys

import cv2
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
VID = str(_COMFY / "media" / "七纹刻印" / "0031_首帧场景" / "00001_书房旋镜视频.mp4")
OUT = str(_COMFY / "scripts" / "_out-pano")
FR = os.path.join(OUT, "dense")
STEP = int(sys.argv[1]) if len(sys.argv) > 1 else 3      # 每 STEP 帧取一帧


def ensure_frames():
    os.makedirs(FR, exist_ok=True)
    for f in glob.glob(os.path.join(FR, "*.png")):
        os.remove(f)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", VID,
                    "-vf", f"select='not(mod(n\\,{STEP}))'", "-fps_mode", "passthrough",
                    os.path.join(FR, "%04d.png")], check=True)
    return sorted(glob.glob(os.path.join(FR, "*.png")))


def orb_dx(a, b):
    g1 = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(4000, scaleFactor=1.2, nlevels=8, fastThreshold=10)
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, None)
    if d1 is None or d2 is None or len(k1) < 8 or len(k2) < 8:
        return None
    m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    if len(m) < 8:
        return None
    dx = np.array([k2[x.trainIdx].pt[0] - k1[x.queryIdx].pt[0] for x in m])
    keep = np.abs(dx - np.median(dx)) < 40
    return float(np.median(dx[keep]))


fs = ensure_frames()
imgs = [cv2.imread(p) for p in fs]
h, w = imgs[0].shape[:2]
print(f"抽帧 {len(imgs)} 张(每 {STEP} 帧), 尺寸 {w}x{h}")

print("相邻帧 ORB 水平位移:", end=" ")
dxs = []
for a, b in zip(imgs, imgs[1:]):
    dx = orb_dx(a, b)
    dxs.append(dx)
print(f"{sum(1 for d in dxs if d is not None)}/{len(dxs)} 对匹配成功")
bad = [i for i, d in enumerate(dxs) if d is None]
if bad:
    print("  匹配失败的帧对(将按邻值插补):", bad)
    for i in bad:                                    # 用邻值插补, 尽量不留断点
        vals = [d for d in (dxs[i-1] if i else None, dxs[i+1] if i+1 < len(dxs) else None) if d is not None]
        dxs[i] = float(np.mean(vals)) if vals else 0.0
dxs = np.array(dxs, dtype=np.float64)
print(f"  平均 {dxs.mean():+.1f} px/步, 合计 {dxs.sum():+.1f} px; 若正好 360° 则 f = ?")

# 解 f: Σ atan(dx_i / f) = 2π  (dx 为负 = 画面右移; 取绝对值方向上无所谓, 统一符号)
sign = -1.0 if dxs.sum() < 0 else 1.0
adx = np.abs(dxs)


def total(f):
    return float(np.sum(np.arctan(adx / f)))


lo, hi = 20.0, 100000.0
if total(lo) < 2 * np.pi:
    print(f"警告: f={lo} 时总转角仍 {np.degrees(total(lo)):.1f}° < 360°, 该视频不是完整一圈")
f = None
for _ in range(80):
    mid = (lo + hi) / 2
    if total(mid) > 2 * np.pi:
        lo = mid
    else:
        hi = mid
f = (lo + hi) / 2
hfov = 2 * np.degrees(np.arctan((w / 2) / f))
print(f"解出焦距 f={f:.1f}px → 水平 FOV≈{hfov:.1f}°  (总转角 {np.degrees(total(f)):.2f}°)")

yaws = np.cumsum(np.concatenate([[0.0], sign * np.arctan(adx / f)]))     # 各帧偏航(弧度)
print(f"yaw 范围 {np.degrees(yaws.min()):+.1f}° .. {np.degrees(yaws.max()):+.1f}°")

# ---- 圆柱展开: 每个输出列取角度 θ, 每帧用一次 remap ----
W = int(round(2 * np.pi * f))
H = h
cx, cy = (w - 1) / 2, (h - 1) / 2
theta = (np.arange(W, dtype=np.float64) / W) * 2 * np.pi - np.pi
canvas = np.zeros((H, W, 3), np.float64)
wsum = np.zeros((H, W), np.float64)
rows = np.arange(H, dtype=np.float32)
map_y_base = (cy + f * (rows - cy) / f).astype(np.float32)               # 圆柱: v = cy + f·y ⇒ 恒等
# 每列只取最近的两帧: 全窗口羽化会把 ±60° 内的 ~27 帧平均在一起 ⇒ 糊成一片。
D = np.abs((theta[None, :] - yaws[:, None] + np.pi) % (2 * np.pi) - np.pi)     # (Nf, W)
near1 = np.argmin(D, axis=0)
d1 = D[near1, np.arange(W)]
order = np.argsort(D, axis=0)
near2 = order[1, np.arange(W)]
d2 = D[near2, np.arange(W)]
step = 2 * np.pi / len(yaws)
w1 = np.maximum(0.0, 1 - d1 / (d1 + d2 + 1e-9)) * (d1 < np.radians(60))
w2 = np.maximum(0.0, 1 - d2 / (d1 + d2 + 1e-9)) * (d2 < np.radians(60))
print(f"每列混合帧数: 1 帧 {int(((w2 <= 0)).sum())} 列, 2 帧 {int((w2 > 0).sum())} 列; 帧间距≈{np.degrees(step):.2f}°")

for i, (im, yaw) in enumerate(zip(imgs, yaws)):
    take = (near1 == i) | (near2 == i)
    if not take.any():
        continue
    wt = np.where(near1 == i, w1, w2) * take
    a = (theta - yaw + np.pi) % (2 * np.pi) - np.pi
    u = cx + f * np.tan(a)
    ok = (np.abs(a) < np.radians(60)) & (u >= 0) & (u <= w - 1)
    map_x = np.tile(u, (H, 1)).astype(np.float32)
    map_y = np.tile(map_y_base[:, None], (1, W))
    warped = cv2.remap(im, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    wt = wt * ok
    canvas += warped.astype(np.float64) * wt[None, :, None]
    wsum += wt[None, :]
pano = (canvas / np.maximum(wsum, 1e-9)[..., None]).clip(0, 255).astype(np.uint8)
empty = (wsum < 1e-6)
pano[empty] = 0
print(f"圆柱长图: {W}x{H} 宽高比 {W/H:.2f}, 未覆盖列 {int(empty.any(axis=0).sum())}/{W}")
p = os.path.join(OUT, "surround-cylindrical.png")
cv2.imwrite(p, pano)
cv2.imwrite(os.path.join(OUT, "surround-cylindrical-preview.png"),
            cv2.resize(pano, (1600, int(1600 * H / W)), interpolation=cv2.INTER_AREA))
print("已存:", p)

# ---- 2:1 equirect: 纵向按球面反投影重采样(逐像素), 上方/下方不足处留黑 ----
W2, H2 = W, W // 2
phi = (0.5 - (np.arange(H2, dtype=np.float64) + 0.5) / H2) * np.pi     # 俯仰 +π/2..-π/2
canvas2 = np.zeros((H2, W2, 3), np.float64)
wsum2 = np.zeros((H2, W2), np.float64)
for i, (im, yaw) in enumerate(zip(imgs, yaws)):
    take = (near1 == i) | (near2 == i)
    if not take.any():
        continue
    a = (theta - yaw + np.pi) % (2 * np.pi) - np.pi
    u = cx + f * np.tan(a)
    ok = (np.abs(a) < np.radians(60)) & (u >= 0) & (u <= w - 1)
    cosd = np.cos(a)
    # 反投影: 相机坐标 dx=tan(a), dy=tan(phi)/cos(a)
    map_x = (cx + f * np.tan(a))[None, :].repeat(H2, 0)
    map_y = cy + f * (np.tan(phi)[:, None] / cosd[None, :])
    warped = cv2.remap(im, map_x.astype(np.float32), map_y.astype(np.float32),
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    valid = (map_y >= 0) & (map_y < h) & ok[None, :] & np.isfinite(map_y)
    wt = np.where(near1 == i, w1, w2) * take * valid
    canvas2 += warped.astype(np.float64) * wt[..., None]
    wsum2 += wt
pano2 = (canvas2 / np.maximum(wsum2, 1e-9)[..., None]).clip(0, 255).astype(np.uint8)
pano2[wsum2 < 1e-6] = 0
cov = float((wsum2 >= 1e-6).mean())
print(f"equirect 2:1: {W2}x{H2}, 有效覆盖 {cov*100:.1f}% (旋转相机的竖直 FOV 有限, 上下极区必然缺)")
p2 = os.path.join(OUT, "surround-equirect.png")
cv2.imwrite(p2, pano2)
cv2.imwrite(os.path.join(OUT, "surround-equirect-preview.png"),
            cv2.resize(pano2, (1600, 800), interpolation=cv2.INTER_AREA))
print("已存:", p2)