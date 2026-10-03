"""诊断: 产出的世界模型 PLY 到底带没带参考图的颜色。

对照三份数据:
  1. 导出 PLY 的 f_dc(DC 色, 就是视口/核心 RenderSplat 能看到的那份颜色);
  2. 8 张参考视图的像素均值/中位(参考图真正的颜色);
  3. 若缓存里有前馈的完整 SH, 顺带算一遍"8 视角平均色", 看丢掉的 band>=1 有多少能量。

用途: 判断"参考图颜色没进世界模型"是【导出丢 SH】还是【渲染器问题】。
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image


def read_ply_vertex(path):
    """极简 3DGS PLY 读取(主 venv 没有 plyfile): 只认 binary_little_endian + f4 属性。"""
    with open(path, "rb") as f:
        raw = f.read()
    end = raw.index(b"end_header\n") + len(b"end_header\n")
    header = raw[:end].decode("ascii", "replace")
    names, count = [], 0
    for line in header.splitlines():
        parts = line.split()
        if parts[:2] == ["element", "vertex"]:
            count = int(parts[2])
        elif parts[:3] == ["property", "float", "x"] or (len(parts) == 3 and parts[0] == "property"):
            names.append(parts[-1])
    stride = 4 * len(names)
    buf = np.frombuffer(raw[end:end + count * stride], dtype="<f4").reshape(count, len(names))
    return {n: buf[:, i] for i, n in enumerate(names)}


C0 = 0.28209479177387814
PLY = str(_COMFY / "media" / "七纹刻印" / "0034_世界模型" / "0034_世界模型_世界3DGS.ply")
MEDIA = str(_COMFY / "media" / "七纹刻印" / "0031_首帧场景")
SLOTS = ["前面", "前右", "右面", "后右", "后面", "后左", "左面", "前左"]

v = read_ply_vertex(PLY)
n = len(v["x"])
names = list(v.keys())
print("PLY 属性:", ", ".join(names))
print(f"高斯数 {n:,}")

dc = np.stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]], 1).astype(np.float32)
rgb = np.clip(0.5 + C0 * dc, 0, 1)
op = 1.0 / (1.0 + np.exp(-v["opacity"].astype(np.float32)))
sc = np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], 1).astype(np.float32)

print(f"\n[PLY] DC 色 均值 {rgb.mean(0).round(3)}  中位 {np.median(rgb, 0).round(3)}")
print(f"[PLY] 亮度 p05/p50/p95 = {np.percentile(rgb.mean(1), [5, 50, 95]).round(3)}")
print(f"[PLY] 饱和度 (max-min) 中位 = {float(np.median(rgb.max(1) - rgb.min(1))):.4f}")
print(f"[PLY] 不透明度 中位 {float(np.median(op)):.3f}  <0.05 占比 {float((op < 0.05).mean()):.3f}")
print(f"[PLY] scale 中位 {float(np.median(sc)):.4f} max {float(sc.max()):.4f}")

print("\n[参考图]")
acc = []
for name in SLOTS:
    p = os.path.join(MEDIA, f"00001_书房旋镜{name}.png")
    im = np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0
    pix = im.reshape(-1, 3)
    acc.append(pix)
    print(f"  {name} {im.shape[1]}x{im.shape[0]} 均值 {pix.mean(0).round(3)} "
          f"中位 {np.median(pix, 0).round(3)}")
allv = np.concatenate(acc, 0)
gt = allv.mean(0)
print(f"[参考图] 总均值 {gt.round(3)} 中位 {np.median(allv, 0).round(3)} "
      f"亮度 p05/p50/p95 {np.percentile(allv.mean(1), [5, 50, 95]).round(3)}")
print(f"[参考图] 饱和度 中位 {float(np.median(allv.max(1) - allv.min(1))):.4f}")

print("\n=== 结论口径 ===")
d = rgb.mean(0) - gt
print(f"DC 色 与 参考图 的通道差 (PLY-GT) = {d.round(3)}  L1={float(np.abs(d).mean()):.3f}")
print(f"亮度差 中位 = {float(np.median(rgb.mean(1)) - np.median(allv.mean(1))):+.3f}")

# ---- 若缓存里还有完整 SH, 量化 band>=1 的能量(即导出被丢掉的部分) ----
CACHE = str(_COMFY / "scripts" / "_cache-0034-preds.pt")
if os.path.isfile(CACHE):
    import torch

    c = torch.load(CACHE, weights_only=False, map_location="cpu")
    print(f"\n[cache] {CACHE}  eff={c.get('eff')}  views_key={c.get('views_key')}")
    sh = c["splats"].get("sh")
    if sh is not None:
        sh = sh.reshape(-1, sh.shape[-1] // 3, 3).float()
        K = sh.shape[1]
        deg = int(round(np.sqrt(K))) - 1
        dc_part = np.clip((sh[:, 0, :] * C0 + 0.5).numpy(), 0, 1)
        rest = sh[:, 1:, :].abs().mean().item()
        print(f"[cache] sh K={K} deg={deg}  band>=1 |系数| 均值 = {rest:.5f}")
        print(f"[cache] SH-DC 色 均值 = {dc_part.mean(0).round(3)} 中位 = {np.median(dc_part, 0).round(3)}")
