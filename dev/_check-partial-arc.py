"""窄弧段展开的几何正确性复核 (2026-09-28)。

转速谱系扫描里两个窄弧用例(30°/200°)的"分块局部 NCC"只有 0.6~0.72, 而漂移只有 0.2~0.6°。
怀疑是**合成真值的逐像素噪声**: 窄弧长图把远场(|a|→62°)抻长 4~5 倍 = 强低通, 而参考图
仍是带噪声的原图 ⇒ 相关被噪声拉低, 与几何无关。

做法: 用**无噪声** GT 重建同样两个用例 + 一个整圈对照, 比几何指标与相关。
若无噪声下相关回到 0.9+, 则谱系扫描里那两个 FAIL 判的是噪声, 不是展开。

用法: .venv\\Scripts\\python.exe custom_nodes\\ComfyUI-FallingTS\\dev\\_check-partial-arc.py
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import importlib.util
import math
import sys

import cv2
import numpy as np
import torch

NODE_PATH = str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "world-panorama" / "nodes.py")
sys.path.append(str(_COMFY / "ComfyUI"))
sys.path.append(str(_COMFY))
spec = importlib.util.spec_from_file_location("wpn3", NODE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
NODE = mod.FallingTSWorldSurroundPanoramaNode

sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

harness = import_module("_verify-unfold-rate")
GT_W, GT_H, SRC_W, SRC_H, F_TRUE = harness.GT_W, harness.GT_H, harness.SRC_W, harness.SRC_H, harness.F_TRUE
render_yaw, roll_ncc, block_drift, band_of = harness.render_yaw, harness.roll_ncc, harness.block_drift, harness.band_of
H_FOV_TRUE = harness.H_FOV_TRUE


def make_gt_clean(seed=7):
    """与 make_gt 同构但**不加逐像素噪声**(斑块/网格/文字都保留)。"""
    x = np.linspace(0, 1, GT_W)[None, :]
    y = np.linspace(0, 1, GT_H)[:, None]
    img = np.zeros((GT_H, GT_W, 3), np.uint8)
    img[..., 0] = (60 + 180 * y)
    img[..., 1] = (180 - 120 * y + 30 * np.cos(2 * np.pi * x))
    img[..., 2] = (200 - 160 * y)
    rng = np.random.default_rng(seed)
    for _ in range(400):
        cx, cy = int(rng.integers(0, GT_W)), int(rng.integers(0, GT_H))
        w, h = int(rng.integers(8, 40)), int(rng.integers(8, 40))
        img[max(0, cy - h):cy + h, max(0, cx - w):cx + w] = rng.integers(0, 255, 3)
    for i in range(0, GT_W, GT_W // 12):
        img[:, max(0, i - 2):i + 2] = 255
    for j in range(0, GT_H, GT_H // 6):
        img[max(0, j - 2):j + 2, :] = 255
    for txt, org in ((b"UP", (GT_W // 2 - 60, 80)), (b"DOWN", (GT_W // 2 - 110, GT_H - 40)),
                     (b"LEFT", (40, GT_H // 2)), (b"RIGHT", (GT_W - 260, GT_H // 2))):
        cv2.putText(img, txt.decode(), org, cv2.FONT_HERSHEY_SIMPLEX, 3.0, (0, 0, 0), 9)
        cv2.putText(img, txt.decode(), org, cv2.FONT_HERSHEY_SIMPLEX, 3.0, (255, 255, 255), 4)
    return img


def run(name, yaws_deg, gt):
    imgs = np.stack([render_yaw(gt, math.radians(a)) for a in yaws_deg]).astype(np.float32) / 255.0
    out = NODE.execute(images=torch.from_numpy(imgs), mode="unfold", max_frames=240,
                       target_shift_percent=12.0, supersample=1.5, seam_feather=3)
    pano, band, vc, report = getattr(out, "result", None) or tuple(out)
    p = (pano[0].numpy() * 255.0 + 0.5).astype(np.uint8)
    ph, pw = p.shape[:2]
    empty = p.astype(np.int32).sum(axis=2).mean(axis=0) < 12.0
    col_ok = ~empty
    if not col_ok.any():
        col_ok = np.ones(pw, dtype=bool)
    ref = cv2.resize(band_of(gt, band), (pw, ph), interpolation=cv2.INTER_AREA)
    s, n_roll = roll_ncc(p, ref)
    al = np.roll(ref, s, axis=1)
    drift_px, n_raw, n_b = block_drift(p, ref, col_ok)
    hf = float(report.split("h_fov≈")[1].split("°")[0]) if "h_fov≈" in report else None
    print("=== %s ===" % name)
    print("  report: %s" % report)
    print("  内容列 %.0f%% | 滚动NCC %.3f(列移 %+dpx) | 分块漂移 %.1fpx=%.2f° | 分块NCC %.3f (低通 %.3f)"
          % (col_ok.mean() * 100, n_roll, s, drift_px, drift_px / pw * 360.0, n_raw, n_b))
    print("  h_fov %s (真值 %.1f°) | 全局对齐后 NCC %.3f" %
          (("%.2f°" % hf) if hf is not None else "未解出", H_FOV_TRUE,
           harness.ncc(p[:, col_ok], al[:, col_ok])))
    return n_roll, n_b, drift_px / pw * 360.0


gt = make_gt_clean()
print("无噪声真值(对照: 同一用例在带噪真值下 分块NCC ≈0.5~0.7)")
run("整圈 48 帧 (对照)", np.linspace(0, -360, 48), gt)
run("部分弧 200° / 28 帧", np.linspace(0, -200, 28), gt)
run("窄弧 30° / 30 帧", np.linspace(0, -30, 30), gt)
