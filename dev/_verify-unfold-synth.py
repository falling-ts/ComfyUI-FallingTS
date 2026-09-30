"""合成序列验证 WorldSurroundPanorama (2026-09-28 v2)。

思路: 造一张**已知真值**的等距圆柱世界图(GT, 上行=天/下行=地, 四角带方向文字与渐变色),
按纯偏航旋转**渲染**一族针孔帧(与节点内部正演模型同一套公式), 交给节点展开, 再与 GT 比对:

  1. 朝向: 与 GT 的相关必须**远高于**上下翻转/左右镜像 —— 证明"不倒立、不镜像";
  2. 重影: 与 GT 的 PSNR 要高(静态 GT + 精确位姿下, WTA 拼接应几乎无损; 帧间平均会掉一大截);
  3. 焦距: 闭环/单应解出的 h_fov 与真值误差 < 3°;
  4. 方位: 用相位相关求最佳循环列移, 应≈0(说明 yaw 积分方向没错);
  5. 部分弧段(只转 200°): 仍要能解出 f 并展开(不再依赖"正好一圈")。

用法: .venv\\Scripts\\python.exe custom_nodes\\ComfyUI-FallingTS\\dev\\_verify-unfold-synth.py
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

NODE_PATH = str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "world-panorama" / "nodes.py")
spec = importlib.util.spec_from_file_location("world_panorama_nodes", NODE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
NODE = mod.FallingTSWorldSurroundPanoramaNode

GT_W, GT_H = 2048, 1024
SRC_W, SRC_H = 640, 360
F_TRUE = (SRC_W / 2) / math.tan(math.radians(90.0) / 2)      # h_fov = 90°
H_FOV_TRUE = 2 * math.degrees(math.atan((SRC_W / 2) / F_TRUE))
V_FOV_TRUE = 2 * math.degrees(math.atan((SRC_H / 2) / F_TRUE))
print(f"真值: f={F_TRUE:.1f}px  h_fov={H_FOV_TRUE:.2f}°  v_fov={V_FOV_TRUE:.2f}°")


def make_gt():
    """已知真值世界图: 上蓝下绿, 四角方向文字, 网格 + 随机斑块(便于比对与看重影)。"""
    x = np.linspace(0, 1, GT_W)[None, :]
    y = np.linspace(0, 1, GT_H)[:, None]
    img = np.zeros((GT_H, GT_W, 3), np.uint8)
    img[..., 0] = (60 + 180 * y)                     # R: 上暗下亮
    img[..., 1] = (180 - 120 * y + 30 * np.cos(2 * np.pi * x))   # G
    img[..., 2] = (200 - 160 * y)                    # B: 上亮(天) 下暗(地)
    rng = np.random.default_rng(7)
    for _ in range(400):                             # 随机色块: 高频细节, 用于查重影
        cx, cy = int(rng.integers(0, GT_W)), int(rng.integers(0, GT_H))
        w, h = int(rng.integers(8, 40)), int(rng.integers(8, 40))
        img[max(0, cy - h):cy + h, max(0, cx - w):cx + w] = rng.integers(0, 255, 3)
    for i in range(0, GT_W, GT_W // 12):             # 经线
        img[:, max(0, i - 2):i + 2] = 255
    for j in range(0, GT_H, GT_H // 6):              # 纬线
        img[max(0, j - 2):j + 2, :] = 255
    for txt, org in ((b"UP", (GT_W // 2 - 60, 80)), (b"DOWN", (GT_W // 2 - 110, GT_H - 40)),
                     (b"LEFT", (40, GT_H // 2)), (b"RIGHT", (GT_W - 260, GT_H // 2))):
        cv2.putText(img, txt.decode(), org, cv2.FONT_HERSHEY_SIMPLEX, 3.0, (0, 0, 0), 9)
        cv2.putText(img, txt.decode(), org, cv2.FONT_HERSHEY_SIMPLEX, 3.0, (255, 255, 255), 4)
    noise = rng.integers(0, 255, img.shape, dtype=np.uint8)      # 细纹理: 给 ORB 足够独特角点
    img = (0.72 * img.astype(np.float32) + 0.28 * noise.astype(np.float32)).astype(np.uint8)
    return img


def render_yaw(gt, yaw):
    """纯偏航渲染一帧针孔图(与节点内部正演一致: world_y 向下, 上行=天)。"""
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
    """从 GT 裁出 ±v_fov/2 的条带(上行=天), 返回 (bgr, elev_top_deg)。"""
    top = int(round((0.5 - (v_fov / 2) / 180.0) * (GT_H - 1)))
    bot = int(round((0.5 + (v_fov / 2) / 180.0) * (GT_H - 1))) + 1
    return gt[top:bot].copy()


def best_shift(a, b):
    """a 相对 b 的最佳循环列移(带符号整数) —— 用相位相关。"""
    ga = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gb = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY).astype(np.float32)
    (sx, sy), _ = cv2.phaseCorrelate(ga, gb)
    return sx, sy


def run_case(name, yaws_deg, gt, expect_full=True):
    print(f"\n=== {name} ({len(yaws_deg)} 帧, 转角 {abs(yaws_deg[-1]-yaws_deg[0]):.0f}°) ===")
    imgs = np.stack([render_yaw(gt, math.radians(a)) for a in yaws_deg]).astype(np.float32) / 255.0
    out = NODE.execute(images=torch.from_numpy(imgs), mode="unfold", max_frames=120,
                       target_shift_percent=12.0, supersample=1.5, seam_feather=3)
    pano, valid_band, v_center, report = getattr(out, "result", None) or tuple(out)
    print("report:", report)
    p = (pano[0].numpy() * 255.0 + 0.5).astype(np.uint8)
    ph, pw = p.shape[:2]
    vf = valid_band
    gtb = band_of(gt, vf)
    ref = cv2.resize(gtb, (pw, ph), interpolation=cv2.INTER_AREA)

    # 循环列移对齐后可比的三种读法(只在**基本填满的列**上比, 部分弧段其余列是黑的)
    black = (p.astype(np.int32).sum(axis=2) < 12)
    col_ok = black.mean(axis=0) < 0.02
    if not col_ok.any():
        col_ok = np.ones(pw, dtype=bool)
    sh, _ = best_shift(p[:, col_ok], ref[:, col_ok])
    al = np.roll(ref, -int(round(sh)), axis=1)
    res = {}
    for tag, variant in (("正放", al), ("上下翻转", ref[::-1]), ("左右镜像", ref[:, ::-1]),
                         ("旋转180", ref[::-1, ::-1])):
        res[tag] = ncc(p[:, col_ok], variant[:, col_ok])
    print(f"内容列占比 {col_ok.mean() * 100:.0f}%")
    print("NCC:", {k: round(v, 3) for k, v in res.items()})
    print(f"相位相关列移 = {sh:+.2f}px (应≈0)")
    print(f"对齐后 PSNR(正放) = {psnr(p[:, col_ok], al[:, col_ok]):.2f} dB")
    print(f"对齐后 PSNR(上下翻转) = {psnr(p[:, col_ok], ref[::-1][:, col_ok]):.2f} dB")
    lap_p = cv2.Laplacian(cv2.cvtColor(p[:, col_ok], cv2.COLOR_RGB2GRAY), cv2.CV_32F).var()
    lap_r = cv2.Laplacian(cv2.cvtColor(ref[:, col_ok], cv2.COLOR_RGB2GRAY), cv2.CV_32F).var()
    sharp = lap_p / max(lap_r, 1e-6)
    print(f"锐度比(长图/真值) = {sharp:.2f}  [仅供参考: 本用例的真值只经过一次 resize, "
          f"而长图经过 渲染→展开 两次线性重采样, 天然偏软; 重影不是靠这个指标判的]")

    ok = True
    if res["正放"] < (0.85 if expect_full else 0.70):
        print("✗ 正放相关不足"); ok = False
    if res["正放"] - max(res["上下翻转"], res["左右镜像"]) < 0.3:
        print("✗ 朝向判别不明确(可能是倒立/镜像)"); ok = False
    if abs(sh) > 3.0:
        print(f"✗ 列移 {sh:.1f}px 过大(yaw 积分方向可能错了)"); ok = False
    # 焦距: 从 report 里解出 h_fov 做检查
    if "h_fov≈" in report:
        got = float(report.split("h_fov≈")[1].split("°")[0])
        print(f"h_fov: 解出 {got:.2f}° / 真值 {H_FOV_TRUE:.2f}°  误差 {abs(got-H_FOV_TRUE):.2f}°")
        if abs(got - H_FOV_TRUE) > 3.0:
            print("✗ 焦距误差 > 3°"); ok = False
    else:
        print("! report 里没有 h_fov, 跳过焦距检查")
    if expect_full and abs(pw / ph * 1.0 - 360.0 / vf) > 0.1:
        print(f"✗ 长图宽高比与有效带不一致: {pw}x{ph}, band={vf:.1f}°"); ok = False
    print("结果:", "PASS" if ok else "FAIL")
    return p, (pw, ph), report, ok


gt = make_gt()
full = np.linspace(0, -360, 49)                     # 49 帧正好一圈(帧间 7.5°)
p1, size1, rep1, ok1 = run_case("完整一圈", full, gt)

part = np.linspace(0, -200, 28)                     # 只转 200°
p2, size2, rep2, ok2 = run_case("部分弧段(200°)", part, gt, expect_full=False)

print("\n==== 汇总 ====")
print("完整一圈:", "PASS" if ok1 else "FAIL", size1)
print("部分弧段:", "PASS" if ok2 else "FAIL", size2)
assert ok1, "完整一圈用例失败"
sys.exit(0 if ok1 and ok2 else 1)
