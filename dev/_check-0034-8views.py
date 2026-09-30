"""量化 0034 的 8 张参考图到底有多大重叠/重复 —— 直接回答「是不是重复像素导致重影」。

指标:
  MAE     相邻两张的平均绝对差(0~255), 越大越不一样
  corr    去均值后的皮尔逊相关, 越接近 1 越像
  收益    «把两张当作同一内容» 的像素占比估算: 1 - MAE/255 只是粗指标, 另给出
          用 64x64 缩略图做的最近邻重复率(每张图的像素在另一张里 15 灰阶内可找到的比例)
另外报 ROI: 每张图中心的水平梯度, 用来判断是"同内容平移"还是"不同内容"。
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import glob
import os
import sys

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
D = str(_COMFY / "ComfyUI" / "temp" / "worldrefine" / "8723b9869474bd13")
ps = sorted(glob.glob(os.path.join(D, "0*.png")))
print("输入张数:", len(ps))
arrs = []
for p in ps:
    im = Image.open(p).convert("RGB")
    arrs.append((os.path.basename(p), im.size, np.asarray(im, dtype=np.float32)))
for n, size, a in arrs:
    print(f"  {n} {size} 均值={a.mean():.1f} 标准差={a.std():.1f}")


def gray(a):
    return a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def dup_rate(g1, g2, tol=15.0):
    """缩略图最近邻重复率: g1 的像素在 g2 中 8 邻域内能找到 |差|<tol 的比例。"""
    h1 = np.asarray(Image.fromarray(g1.astype(np.uint8)).resize((64, 64)), dtype=np.float32)
    h2 = np.asarray(Image.fromarray(g2.astype(np.uint8)).resize((64, 64)), dtype=np.float32)
    pad = np.pad(h2, 1, mode="edge")
    best = np.full(h1.shape, 1e9, dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            d = np.abs(h1 - pad[dy:dy + 64, dx:dx + 64])
            best = np.minimum(best, d)
    return float((best < tol).mean())


print("\n相邻对(01-02, 02-03, …)与对角对:")
n = len(arrs)
grays = [gray(a) for _, _, a in arrs]
rows = []
for i in range(n):
    j = (i + 1) % n
    g1, g2 = grays[i], grays[j]
    mae = float(np.abs(arrs[i][2] - arrs[j][2]).mean())
    c1, c2 = g1.ravel() - g1.mean(), g2.ravel() - g2.mean()
    corr = float((c1 @ c2) / (np.linalg.norm(c1) * np.linalg.norm(c2) + 1e-9))
    rows.append((f"{arrs[i][0]}↔{arrs[j][0]}", mae, corr, dup_rate(g1, g2)))
for name, mae, corr, dup in rows:
    print(f"  {name}: MAE={mae:6.1f}  corr={corr:+.3f}  缩略图最近邻重复率={dup*100:5.1f}%")

print("\n判定: MAE 越小/corr 越高/重复率越高 = 越像同一内容")
print("平均 MAE=%.1f, 平均 corr=%+.3f, 平均重复率=%.1f%%" % (
    np.mean([r[1] for r in rows]), np.mean([r[2] for r in rows]), np.mean([r[3] for r in rows]) * 100))
