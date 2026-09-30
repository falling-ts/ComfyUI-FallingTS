"""真实视频 v2 展开 + 视角对拍验证 (2026-09-28)。

1) 用新算法展开 0031 旋镜视频 → scripts\_out-pano\v2-long.png(横向长图, 上行=天)
2) 打印 report(焦距/角速率/接缝/对齐残差/空白)
3) 目视素材: 顶部/底部条带 + 两个 1:1 细节块(与 v1 老图同角度区并排), 用 read_image 看
4) **关键**: 从新长图按 yaw=0 采样一个视角, 与源视频第 0 帧对拍 —— 正放必须赢过上下翻转,
   证明"长图改成正立"之后切出来的视角画面**仍然正确**(外参口径不变 ⇒ PLY 不受影响)

用法: .venv\\Scripts\\python.exe custom_nodes\\ComfyUI-FallingTS\\dev\\_test-pano-v2.py
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import importlib.util
import math
import os
import sys

import cv2
import numpy as np
import torch
import torch.nn.functional as F

sys.path.append(str(_COMFY / "ComfyUI"))
sys.path.append(str(_COMFY))

NODE_PATH = os.environ.get("WSRP_NODES",
                           str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "world-panorama" / "nodes.py"))
spec = importlib.util.spec_from_file_location("wpn2", NODE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

VID = str(_COMFY / "media" / "七纹刻印" / "0031_首帧场景" / "00001_书房旋镜视频.mp4")
OUT = str(_COMFY / "scripts" / "_out-pano")
OLD = os.path.join(OUT, "0034-360长图-预览.png")
os.makedirs(OUT, exist_ok=True)


def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    ext = os.path.splitext(p)[1]
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(p)


def ncc(a, b):
    a = a.astype(np.float32) - a.mean()
    b = b.astype(np.float32) - b.mean()
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float((a * b).sum() / d) if d > 0 else 0.0


# ── 读帧 ──
cap = cv2.VideoCapture(VID)
frames = []
while True:
    ok, f = cap.read()
    if not ok:
        break
    frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
cap.release()
print(f"视频帧数 {len(frames)}  尺寸 {frames[0].shape}")
batch = torch.from_numpy(np.stack(frames).astype(np.float32) / 255.0)

out = mod.FallingTSWorldSurroundPanoramaNode.execute(
    images=batch, mode="unfold", max_frames=240, target_shift_percent=12.0,
    supersample=1.5, seam_feather=int(sys.argv[1]) if len(sys.argv) > 1 else 7)
pano_t, band, vc, report = getattr(out, "result", None) or tuple(out)
print("report:", report)
p = (pano_t[0].numpy() * 255.0 + 0.5).astype(np.uint8)
ph, pw = p.shape[:2]
print(f"新长图 {pw}x{ph}  band={band:.1f}°  v_center={vc:+.2f}°")
imwrite_u(os.path.join(OUT, "v2-long.png"), cv2.cvtColor(p, cv2.COLOR_RGB2BGR))

# ── 上下朝向自检: 与源帧同角度区比(正放 vs 上下翻转) ──
# ⚠️ h_fov 不能从 pw 直接反推 —— pw 里含 supersample 倍率; 从 report 里取解出的 h_fov。
import re
m = re.search(r"h_fov≈([\d.]+)°", report)
hfov = float(m.group(1)) if m else 2 * math.degrees(math.atan((832 / 2) / (pw / (2 * math.pi * 1.5))))
print(f"采用 h_fov={hfov:.1f}°")
half = int(round(hfov / 360.0 * pw / 2))
c0, c1 = pw // 2 - half, pw // 2 + half
patch = p[:, max(0, c0):min(pw, c1)]
ref = cv2.resize(frames[0], (patch.shape[1], patch.shape[0]), interpolation=cv2.INTER_AREA)
print("同角度区 正放 NCC = %+.3f / 上下翻转 NCC = %+.3f"
      % (ncc(patch, ref), ncc(patch, ref[::-1])))
assert ncc(patch, ref) > ncc(patch, ref[::-1]) + 0.2, "长图仍然是倒立的!"

# ── 视角对拍: 新长图(yaw=0) vs 源帧 0 ──
VIEW = mod.FallingTSWorldPanoramaViewsNode


def view_from(pano_t, yaw, pitch, fov_deg, size, center=0.0, rng=None):
    img, ext, K = VIEW._sample(pano_t[0], math.radians(yaw), math.radians(pitch),
                               math.radians(fov_deg), size, center,
                               rng if rng is not None else band)
    return (img.numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)


size = frames[0].shape[1]                    # 832: 与源帧同宽 ⇒ 视角 f_px 恰好等于源帧 f_px
v_new_full = view_from(pano_t, 0.0, 0.0, hfov, size)
r0 = (size - frames[0].shape[0]) // 2        # 方视角的中央 band == 源帧的视场
v_new = v_new_full[r0:r0 + frames[0].shape[0]]
src = frames[0]
res_new = {"正放": ncc(v_new, src), "上下翻转": ncc(v_new, src[::-1]),
           "左右镜像": ncc(v_new, src[:, ::-1])}
print(f"新长图→视角(yaw=0, {size}x{size} 取中带) vs 源帧0:", {k: round(v, 3) for k, v in res_new.items()})
# 真实视频(含平移/生成漂移)跨 106° 的视角由 7 帧拼成, 对单帧的相关很难到 0.9;
# 判据放宽到 0.65, 关键是与上下翻转/镜像**拉开差距**(朝向正确)。
assert res_new["正放"] > 0.65 and res_new["正放"] > res_new["上下翻转"] + 0.3, res_new

# ── 老长图 + 老公式(上下颠倒的那套)是否也给出同样正确的视角 ──
if os.path.isfile(OLD):
    old = imread_u(OLD)
    old_rgb = cv2.cvtColor(old, cv2.COLOR_BGR2RGB)
    oh, ow = old_rgb.shape[:2]
    old_t = torch.from_numpy(old_rgb.astype(np.float32) / 255.0)

    def sample_old(pano, yaw, pitch, fov_rad, size_):
        h, w, _ = pano.shape
        f_px = (size_ / 2.0) / math.tan(fov_rad / 2.0)
        c = (size_ - 1) / 2.0
        u = torch.arange(size_, dtype=torch.float32)
        uu, vv = torch.meshgrid(u, u, indexing="xy")
        dx, dy = (uu - c) / f_px, (vv - c) / f_px
        rc = F.normalize(torch.stack([dx, dy, torch.ones_like(dx)], dim=-1), dim=-1)
        cy_, sy_ = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        R = torch.tensor([[cy_, 0, sy_], [0, 1, 0], [-sy_, 0, cy_]]) @ \
            torch.tensor([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        rw = torch.einsum("ij,hwj->hwi", R, rc)
        eq_x = (torch.atan2(rw[..., 0], rw[..., 2]) / math.pi + 1.0) * (w - 1) / 2.0
        eq_y = (0.5 - torch.asin(torch.clamp(rw[..., 1], -1, 1)) / math.pi) * (h - 1)
        g = torch.stack([eq_x / (w - 1) * 2 - 1, eq_y / (h - 1) * 2 - 1], dim=-1).unsqueeze(0)
        s = F.grid_sample(pano.permute(2, 0, 1).unsqueeze(0), g, mode="bilinear",
                          padding_mode="border", align_corners=True)
        return (s[0].permute(1, 2, 0).numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)

    v_old = sample_old(old_t, 0.0, 0.0, math.radians(hfov), size)[r0:r0 + src.shape[0]]
    res_old = {"正放": ncc(v_old, src), "上下翻转": ncc(v_old, src[::-1])}
    print("老长图+老公式→视角 vs 源帧0:", {k: round(v, 3) for k, v in res_old.items()})
    np.save(os.path.join(OUT, "v2-oldview.npy"), v_old)

# ── 目视素材: 顶/底条带 + 细节块 ──
top = p[:max(24, ph // 12)]
bot = p[-max(24, ph // 12):]
imwrite_u(os.path.join(OUT, "v2-top-band.png"),
          cv2.resize(cv2.cvtColor(top, cv2.COLOR_RGB2BGR), (1400, None if False else max(8, 1400 * top.shape[0] // top.shape[1]))))
imwrite_u(os.path.join(OUT, "v2-bottom-band.png"),
          cv2.resize(cv2.cvtColor(bot, cv2.COLOR_RGB2BGR), (1400, max(8, 1400 * bot.shape[0] // bot.shape[1]))))
# 细节块: 取一个方位角区(与帧 0 的右半区对应), 1:1
d0, d1 = pw // 2 + 40, pw // 2 + 40 + 620
det = p[:, d0:d1]
imwrite_u(os.path.join(OUT, "v2-detail.png"), cv2.cvtColor(det, cv2.COLOR_RGB2BGR))
if os.path.isfile(OLD):
    old_band_g = cv2.cvtColor(old_rgb, cv2.COLOR_RGB2GRAY)
    rr = np.flatnonzero(old_band_g.max(axis=1) > 6)
    ob = old_rgb[rr[0]:rr[-1] + 1]
    scale = ob.shape[0] / max(1, ph)
    oc0, oc1 = int(d0 * ob.shape[1] / pw), int(d1 * ob.shape[1] / pw)
    olddet = ob[:, oc0:oc1]
    olddet = cv2.resize(olddet, (det.shape[1], det.shape[0]))
    cmp_img = np.concatenate([cv2.cvtColor(olddet, cv2.COLOR_RGB2BGR),
                              cv2.cvtColor(det, cv2.COLOR_RGB2BGR)], axis=1)
    cv2.putText(cmp_img, "v1 (blended)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
    cv2.putText(cmp_img, "v2 (winner-take-all)", (det.shape[1] + 10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3)
    imwrite_u(os.path.join(OUT, "v2-cmp-detail.png"), cmp_img)
    print(f"并排对比: v2-cmp-detail.png (左=v1 混合, 右=v2 唯一帧) {cmp_img.shape}")
print("输出:", os.listdir(OUT)[:20])
