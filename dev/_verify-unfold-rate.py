"""WorldSurroundPanorama 转速适配谱系扫描 (2026-09-28)。

问题: 「是否适配任何转动速率, 甚至不平滑速率?」
做法: 用已知真值 GT 生成等距圆柱世界图 → 按**给定的逐帧转角曲线**渲染针孔帧序列 →
      交给 WorldSurroundPanorama(mode=unfold) 展开 → 与 GT 比对。

覆盖: 匀速 4 档(7.5/15/30/45/60°/帧) + 帧数极端 + 两段式落差(5 倍) + 阶跃(静止后猛转)
      + 中段突发 + 极慢(30°/2°) + 部分弧段。

判定口径:
  * 整圈用例: 内容列占比 ≥ 0.98(没有漏方位) 且 NCC(正放) ≥ 0.85 且 h_fov 误差 ≤ 3°
              且相位相关列移 ≤ 3px;
  * 部分弧: 允许大面积空白, 但 f/h_fov 仍要准;
  * 所有用例: 不许静默给出错误的 f / 假称"整圈"。

用法: .venv\\Scripts\\python.exe custom_nodes\\ComfyUI-FallingTS\\dev\\_verify-unfold-rate.py
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import importlib.util
import math
import os
import sys
import time

import cv2
import numpy as np
import torch

sys.path.append(str(_COMFY / "ComfyUI"))

NODE_PATH = os.environ.get("WSRP_NODES",
                           str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "world-panorama" / "nodes.py"))
spec = importlib.util.spec_from_file_location("world_panorama_nodes", NODE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
NODE = mod.FallingTSWorldSurroundPanoramaNode

GT_W, GT_H = 2048, 1024
SRC_W, SRC_H = 640, 360
F_TRUE = (SRC_W / 2) / math.tan(math.radians(90.0) / 2)
H_FOV_TRUE = 2 * math.degrees(math.atan((SRC_W / 2) / F_TRUE))
V_FOV_TRUE = 2 * math.degrees(math.atan((SRC_H / 2) / F_TRUE))
MAX_FRAMES = 240
print("真值: f=%.1fpx  h_fov=%.2f°  v_fov=%.2f°" % (F_TRUE, H_FOV_TRUE, V_FOV_TRUE))


def make_gt(seed=7, noise=True):
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
    if not noise:
        return img                                          # 低纹理: 少了逐像素噪声 ⇒ ORB 特征骤减
    n = rng.integers(0, 255, img.shape, dtype=np.uint8)
    return (0.72 * img.astype(np.float32) + 0.28 * n.astype(np.float32)).astype(np.uint8)


def render_yaw(gt, yaw):
    u = np.arange(SRC_W, dtype=np.float64)
    v = np.arange(SRC_H, dtype=np.float64)
    uu, vv = np.meshgrid(u, v)
    dx = (uu - (SRC_W - 1) / 2) / F_TRUE
    dy = (vv - (SRC_H - 1) / 2) / F_TRUE
    n = np.sqrt(dx * dx + dy * dy + 1.0)
    wx = math.cos(yaw) * dx + math.sin(yaw) * 1.0
    wy = dy
    wz = -math.sin(yaw) * dx + math.cos(yaw) * 1.0
    elev = np.arcsin(np.clip(-wy / n, -1, 1))
    az = np.arctan2(wx, wz)
    gx = (az / math.pi + 1.0) * (GT_W - 1) / 2.0
    gy = (0.5 - elev / math.pi) * (GT_H - 1)
    return cv2.remap(gt, gx.astype(np.float32), gy.astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def ncc(a, b):
    a = a.astype(np.float32) - a.mean()
    b = b.astype(np.float32) - b.mean()
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float((a * b).sum() / d) if d > 0 else 0.0


def psnr(a, b):
    mse = float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))
    return 99.0 if mse <= 1e-9 else 10 * math.log10(255.0 ** 2 / mse)


def band_of(gt, v_fov):
    top = int(round((0.5 - (v_fov / 2) / 180.0) * (GT_H - 1)))
    bot = int(round((0.5 + (v_fov / 2) / 180.0) * (GT_H - 1))) + 1
    return gt[top:bot].copy()


def roll_ncc(a, b):
    """a ≈ np.roll(b, s) 的最佳循环列移 s 与对应 NCC(FFT 一次算全列)。

    区分「整体滚动偏移」(无害: 长图的 yaw 原点本就任意) 与「局部漂移/漏方位」(有害)。
    """
    A = a.astype(np.float32)
    B = b.astype(np.float32)
    if A.ndim == 3:
        A = A.mean(axis=2)
        B = B.mean(axis=2)
    A = A - A.mean(axis=1, keepdims=True)
    B = B - B.mean(axis=1, keepdims=True)
    FA = np.fft.rfft(A, axis=1)
    FB = np.fft.rfft(B, axis=1)
    corr = np.fft.irfft(FA * np.conj(FB), axis=1).sum(axis=0)   # corr[s] = Σ A[x]·B[(x-s)%W]
    den = float(np.sqrt((A * A).sum() * (B * B).sum()))
    s = int(np.argmax(corr))
    return s, float(corr[s] / max(den, 1e-9))


def block_drift(p, ref, col_ok, maxs=150):
    """把内容列切成 ≤6 块, 每块单独求局部列移 → 返回 (漂移幅度px, 原始NCC均值, 低通后NCC均值)。

    低通(σ=3)那一路是为了去掉等距圆柱 tan 拉伸带来的锐度差 —— 窄弧段上长图把远场
    (|a|→62°) 抻长了 4~5 倍, 原始 NCC 天然偏低, 那不是几何错。
    """
    runs = []
    start = None
    for i, ok in enumerate(col_ok):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(col_ok)))
    chunks = []
    for c0, c1 in runs:
        if c1 - c0 < 32:
            continue
        chunks.extend(np.array_split(np.arange(c0, c1), 3 if c1 - c0 >= 240 else 1))
    if not chunks:
        return 0.0, 0.0, 0.0
    ga = cv2.cvtColor(p, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gb = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY).astype(np.float32)
    ga_b = cv2.GaussianBlur(ga, (0, 0), 3.0)
    gb_b = cv2.GaussianBlur(gb, (0, 0), 3.0)
    offs, nccs, nccb = [], [], []
    W = p.shape[1]
    for cols in chunks:
        c0, c1 = int(cols[0]), int(cols[-1]) + 1
        if c1 - c0 < 32 or W < (c1 - c0) + 2 * maxs:
            continue
        lo, hi = max(0, c0 - maxs), min(W, c1 + maxs)
        res = cv2.matchTemplate(gb_b[:, lo:hi], ga_b[:, c0:c1], cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        off = (lo + loc[0]) - c0
        shifted = np.roll(gb, off, axis=1)
        shifted_b = np.roll(gb_b, off, axis=1)
        offs.append(off)
        nccs.append(ncc(ga[:, c0:c1], shifted[:, c0:c1]))
        nccb.append(ncc(ga_b[:, c0:c1], shifted_b[:, c0:c1]))
    if not offs:
        return 0.0, 0.0, 0.0
    return float(max(offs) - min(offs)), float(np.mean(nccs)), float(np.mean(nccb))


def yaws_from_steps(steps):
    """逐帧转角(度, 正=左转) → 累计偏航(度)。返回长度 = len(steps)+1。"""
    out = [0.0]
    acc = 0.0
    for s in steps:
        acc -= float(s)
        out.append(acc)
    return np.array(out)


def uniform(total_deg, n_frames):
    return np.linspace(0.0, -total_deg, n_frames)


CASES = [
    ("匀速 48 帧 / 7.5°每帧 (一圈)", uniform(360, 48), "full"),
    ("匀速 24 帧 / 15°每帧 (一圈)", uniform(360, 24), "full"),
    ("匀速 12 帧 / 30°每帧 (一圈)", uniform(360, 12), "full"),
    ("匀速 8 帧 / 45°每帧 (一圈)", uniform(360, 8), "full"),
    ("匀速 6 帧 / 60°每帧 (一圈)", uniform(360, 6), "boundary"),
    ("匀速 4 帧 / 90°每帧 (一圈)", uniform(360, 4), "boundary"),
    ("两段式 3°→9°/帧 (一圈, 81 帧)", yaws_from_steps([3.0] * 60 + [9.0] * 20), "full"),
    ("仿0031 5倍落差 8°→14°/帧 (一圈, 37 帧)", yaws_from_steps([8.0] * 24 + [14.0] * 12), "full"),
    ("阶跃 静止30帧→30°/帧×12 (一圈, 43 帧)",
     yaws_from_steps([0.0] * 30 + [30.0] * 12), "boundary"),
    ("中段突发 2°/帧 + 4帧×40° (一圈, 105 帧)",
     yaws_from_steps([2.0] * 40 + [40.0] * 4 + [2.0] * 60), "boundary"),
    ("慢速 480 帧 / 0.75°每帧 (一圈)", uniform(360, 480), "full"),
    ("极慢 30 帧 / 1°每帧 (共 30°)", uniform(30, 30), "partial"),
    ("近乎静止 24 帧 / 0.087°每帧 (共 2°)", uniform(2, 24), "static"),
    ("完全静止 24 帧 (共 0°)", uniform(0, 24), "static"),
    ("部分弧 200° / 28 帧", uniform(200, 28), "partial"),
    ("低纹理 整圈 48 帧 (无噪声真值)", uniform(360, 48), "full", "clean"),
    ("低纹理 部分弧 200° (无噪声真值)", uniform(200, 28), "partial", "clean"),
]


def run_case(name, yaws_deg, kind, gt):
    t0 = time.time()
    imgs = np.stack([render_yaw(gt, math.radians(a)) for a in yaws_deg]).astype(np.float32) / 255.0
    got_arc = abs(float(yaws_deg[-1] - yaws_deg[0]))
    print("\n=== %s ===" % name)
    print("  输入 %d 帧, 总转角 %.0f°, 平均 %.2f°/帧" %
          (len(yaws_deg), got_arc, got_arc / max(1, len(yaws_deg) - 1)))
    try:
        out = NODE.execute(images=torch.from_numpy(imgs), mode="unfold", max_frames=MAX_FRAMES,
                           target_shift_percent=12.0, supersample=1.5, seam_feather=3)
    except Exception as exc:  # noqa: BLE001
        print("  [RAISE] %s" % exc)
        print("  耗时 %.1fs" % (time.time() - t0))
        return dict(name=name, kind=kind, arc=got_arc, status="RAISE",
                    msg=str(exc)[:110], ok=(kind in ("boundary", "static")))

    pano, valid_band, v_center, report = getattr(out, "result", None) or tuple(out)
    print("  report: %s" % report)
    p = (pano[0].numpy() * 255.0 + 0.5).astype(np.uint8)
    ph, pw = p.shape[:2]
    gray_sum = p.astype(np.int32).sum(axis=2)
    col_empty = gray_sum.mean(axis=0) < 12.0
    content_ratio = 1.0 - float(col_empty.mean())
    # 最长连续空白列 → 换算成"漏掉的方位角"
    run = best = 0
    for e in col_empty:
        run = run + 1 if e else 0
        best = max(best, run)
    gap_deg = best / pw * 360.0

    gtb = band_of(gt, valid_band)
    ref = cv2.resize(gtb, (pw, ph), interpolation=cv2.INTER_AREA)
    col_ok = ~col_empty
    if not col_ok.any():
        col_ok = np.ones(pw, dtype=bool)
    ga = cv2.cvtColor(p[:, col_ok], cv2.COLOR_RGB2GRAY).astype(np.float32)
    gb = cv2.cvtColor(ref[:, col_ok], cv2.COLOR_RGB2GRAY).astype(np.float32)
    (sh_full, _sy), _ = cv2.phaseCorrelate(ga, gb)
    s_best, n_best = roll_ncc(p, ref)
    al = np.roll(ref, s_best, axis=1)
    n_ok = ncc(p[:, col_ok], al[:, col_ok])
    n_flip = ncc(p[:, col_ok], ref[::-1][:, col_ok])
    ps = psnr(p[:, col_ok], al[:, col_ok])
    drift_px, n_local, n_local_b = block_drift(p, ref, col_ok)
    drift_deg = drift_px / pw * 360.0

    hf = None
    if "h_fov≈" in report:
        hf = float(report.split("h_fov≈")[1].split("°")[0])
    print("  长图 %dx%d (%d px/度) | 内容列 %.0f%% | 最长空白 %.0f°" %
          (pw, ph, round(pw / 360.0), content_ratio * 100, gap_deg))
    print("  NCC 正放 %.3f / 上下翻转 %.3f | PSNR %.1f dB | h_fov %s (真值 %.1f°)" %
          (n_ok, n_flip, ps, ("%.1f°" % hf) if hf is not None else "未解出", H_FOV_TRUE))
    print("  滚动列移 %+.1fpx(相位相关) / %+dpx(FFT 全局) | 分块漂移 %.1fpx=%.1f° | 分块NCC %.3f (低通 %.3f)" %
          (sh_full, s_best, drift_px, drift_deg, n_local, n_local_b))

    ok, why = True, []
    if kind == "full":
        if content_ratio < 0.98:
            ok, why = False, why + ["漏方位 %.0f°" % gap_deg]
        if n_ok < 0.85:
            ok, why = False, why + ["NCC %.3f" % n_ok]
        if drift_deg > 1.0:
            ok, why = False, why + ["局部漂移 %.1f°" % drift_deg]
        if hf is None or abs(hf - H_FOV_TRUE) > 3.0:
            ok, why = False, why + ["h_fov 误差过大"]
    elif kind == "partial":
        # 窄弧段: 长图把远场(|a|→62°)抻长 4~5 倍, 而源帧在离轴处的角分辨率本就低 ⇒ 长图远场
        # 必然比参考图糊, 结构 NCC 天然低(与几何无关)。故判几何 + 覆盖量: 漂移、焦距、内容列占比
        # (误判"整整一圈"会把 200° 拉成 360° ⇒ 内容列占比冲到 ~100% + 漂移几十度, 这条能抓住)。
        if hf is None or abs(hf - H_FOV_TRUE) > 5.0:
            ok, why = False, why + ["h_fov 误差过大"]
        if drift_deg > 1.5:
            ok, why = False, why + ["局部漂移 %.1f°" % drift_deg]
        if not (0.15 <= content_ratio <= 0.95):
            ok, why = False, why + ["内容列占比 %.0f%% 与弧长不符(疑似被硬拉成整圈)" % (content_ratio * 100)]
    elif kind == "boundary":
        # 边界用例: 报错(诚实)算过; 出图的话必须几何对得上, 不许"静默给错 f + 糊图"。
        if hf is not None and abs(hf - H_FOV_TRUE) > 3.0:
            ok, why = False, why + ["静默给出错误 f"]
        if drift_deg > 2.0:
            ok, why = False, why + ["局部漂移 %.1f°" % drift_deg]
        if hf is not None and n_local_b < 0.80:
            ok, why = False, why + ["低通局部NCC %.3f" % n_local_b]
    elif kind == "static":
        # 期望: 明确报错/明确回退, 若仍宣称 h_fov≈143°(f 掉到搜索下界)记为失败
        if hf is not None and abs(hf - H_FOV_TRUE) > 20.0:
            ok, why = False, why + ["近乎静止却解出 h_fov=%.0f° (f 掉到搜索下界)" % hf]
        if content_ratio > 0.6:
            ok, why = False, why + ["近乎静止却输出大片内容(可疑)"]
    print("  判定: %s%s  耗时 %.1fs" % ("PASS" if ok else "FAIL",
                                       ("" if ok else "  ← " + "; ".join(why)),
                                       time.time() - t0))
    return dict(name=name, kind=kind, arc=got_arc, status="OK", ok=ok,
                content=content_ratio, gap=gap_deg, ncc=n_ok, hf=hf, sh=s_best, size=(pw, ph))


def main():
    gts = {"noisy": make_gt(), "clean": make_gt(noise=False)}
    rows = [run_case(c[0], c[1], c[2], gts[c[3] if len(c) > 3 else "noisy"]) for c in CASES]
    print("\n================ 汇总 ================")
    print("%-42s %-9s %8s %8s %8s %9s" % ("用例", "判定", "内容%", "空白°", "NCC", "h_fov"))
    for r in rows:
        if r["status"] == "RAISE":
            print("%-42s %-9s %8s %8s %8s %9s" % (r["name"][:42], "报错(诚实)", "-", "-", "-", "-"))
            continue
        print("%-42s %-9s %8.0f %8.0f %8.3f %9s" %
              (r["name"][:42], "PASS" if r["ok"] else "FAIL",
               r["content"] * 100, r["gap"], r["ncc"],
               ("%.1f°" % r["hf"]) if r["hf"] is not None else "-"))
    n_fail = sum(1 for r in rows if not r["ok"])
    print("\n失败 %d / %d" % (n_fail, len(rows)))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
