"""先搞清事实: 0031 的「旋镜视频」到底转了多少度? 是不是真 360° 环绕?

方法: 每 5 帧(≈0.208s)取一帧, 用 ORB 特征匹配 + 水平位移中位数累加, 估算总转角;
另出 4x4 联络表供肉眼核对首帧与末帧是不是同一堵墙。
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
FR = os.path.join(OUT, "probe")


def frames():
    os.makedirs(FR, exist_ok=True)
    for f in glob.glob(os.path.join(FR, "*.png")):
        os.remove(f)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", VID, "-vf", "select='not(mod(n\\,5))'",
                    "-fps_mode", "passthrough", os.path.join(FR, "%03d.png")], check=True)
    return sorted(glob.glob(os.path.join(FR, "*.png")))


def orb_du(a, b):
    """a→b 的水平位移中位数(px)。"""
    g1 = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(4000, scaleFactor=1.2, nlevels=8, fastThreshold=10)
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, None)
    if d1 is None or d2 is None or len(k1) < 8 or len(k2) < 8:
        return None, 0, 0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    m = bf.match(d1, d2)
    if len(m) < 8:
        return None, len(m), 0
    dx = np.array([k2[x.trainIdx].pt[0] - k1[x.queryIdx].pt[0] for x in m])
    dy = np.array([k2[x.trainIdx].pt[1] - k1[x.queryIdx].pt[1] for x in m])
    keep = np.abs(dx - np.median(dx)) < 40
    return float(np.median(dx[keep])), len(m), float(np.median(dy[keep]))


fs = frames()
print(f"抽帧 {len(fs)} 张")
imgs = [cv2.imread(p) for p in fs]
h, w = imgs[0].shape[:2]
# 水平 FOV 估计: 用内参未知, 先按常见 60° 记; 同时给出"总位移/画面宽"的屏幕数
f = (w / 2) / np.tan(np.radians(30))
total = 0.0
print("相邻位移:")
for i, (a, b) in enumerate(zip(imgs, imgs[1:])):
    dx, n, dy = orb_du(a, b)
    if dx is None:
        print(f"  {i:2d}->{i+1:2d}: 匹配不足({n})")
        continue
    total += dx
    print(f"  {i:2d}->{i+1:2d}: dx={dx:+7.1f}px (≈{np.degrees(np.arctan(dx/f)):+6.2f}° 若 hfov=60°) 匹配 {n} 对 dy={dy:+.1f}")
print(f"\n累计水平位移 {total:+.1f}px = {abs(total)/w:.2f} 个画面宽")
print(f"若按 hfov=60° 折算转角 ≈ {np.degrees(np.arctan(total/f)):+.1f}°")
print("首末帧 ORB 匹配:", orb_du(imgs[0], imgs[-1]))

# 4x4 联络表
sel = np.linspace(0, len(imgs) - 1, 16).astype(int)
th = [cv2.resize(imgs[i], (320, 185)) for i in sel]
rows = [np.hstack(th[r * 4:r * 4 + 4]) for r in range(4)]
grid = np.vstack(rows)
cv2.putText(grid, f"frames {sel[0]}..{sel[-1]} of {len(imgs)} (every 5th)", (8, 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
cv2.imwrite(os.path.join(OUT, "probe-grid.png"), grid)
print("联络表: probe-grid.png", grid.shape)