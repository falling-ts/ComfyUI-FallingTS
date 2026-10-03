"""核对 WorldRefinePLY 落给脚本的 8 张临时 PNG 是否就是 md 表原本那 8 张(逐像素)。

用法: python custom_nodes\\ComfyUI-FallingTS\\dev\\_check-worldrefine-inputs.py
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import glob
import os
import sys

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
SLOTS = ["前面", "前右", "右面", "后右", "后面", "后左", "左面", "前左"]
TEMP = str(_COMFY / "ComfyUI" / "temp" / "worldrefine")
ORIG = str(_COMFY / "media" / "七纹刻印" / "0031_首帧场景" / "00001_书房旋镜{}.png")

dirs = [d for d in sorted(glob.glob(os.path.join(TEMP, "*"))) if glob.glob(os.path.join(d, "*.png"))]
print("临时目录:", [os.path.basename(d) for d in dirs])
if not dirs:
    raise SystemExit("没有临时图片")
d = dirs[-1]
print("最新:", d)
bad = 0
for i, s in enumerate(SLOTS):
    a = np.asarray(Image.open(os.path.join(d, f"{i:02d}.png")).convert("RGB")).astype(int)
    b = np.asarray(Image.open(ORIG.format(s)).convert("RGB")).astype(int)
    if a.shape != b.shape:
        print(f"  {i} {s}: 尺寸不同 {a.shape} vs {b.shape}")
        bad += 1
        continue
    diff = int(np.abs(a - b).max())
    same = diff == 0
    bad += 0 if same else 1
    print(f"  {i} {s:4s} {a.shape}  逐像素相同={same}  最大差={diff}")
print("结论:", "8 张全部与原图一致" if bad == 0 else f"{bad} 张不一致")
