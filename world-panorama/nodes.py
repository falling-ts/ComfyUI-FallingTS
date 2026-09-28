# world-panorama/nodes.py
"""FallingTS 世界模型 · 360° 视频 → 横向展开长图(等距圆柱) → 带精确位姿的视角批。

链路位置 (0034):
    md 数据表(360 环绕视频) → WorldSurroundPanorama → 横向展开长图
    → WorldPanoramaViews → 视角批 + EXTRINSICS/INTRINSICS → WorldRefinePLY → PLY

为什么要有这两个节点 (对比原来的 8 图路径):
  0034 原来喂给重建的是 8 张**各自独立生成**的多视角图, 位姿由 WorldMirror 自己猜。上游推理
  不做跨视图融合(`rasterization.py` 在 `is_inference` 直接 return, 把体素合并/置信度过滤短路),
  每个视角按**自己预测的**位姿与深度反投影(`position_from="gsdepth+predcamera"`)⇒ 同一表面
  被铺两层壳, 就是视口里的"重影"。换成一条 360°(或真 equirect)视频后, 所有视角出自同一段
  画面; 再由本节点给出**解析解位姿**(纯旋转、相机在球心), 位姿不再靠猜。

## 长图的四条硬要求 (2026-09-28 v2 重做)

1. **不许有重影** —— v1 把每列按角距离最近的两帧**线性混合**, 只要位姿有 0.5° 误差(≈3px)
   或视频本身帧间内容在漂, 平均出来的就是双重曝光。v2 改成 **逐像素 winner-take-all**:
   每个输出像素只取**一帧**(光学轴夹角最小的那帧)的值 ⇒ 结构上不可能有重影; 帧间亮度差用
   「相邻帧曝光链」消掉, 接缝处只对**低频**做羽化(高频仍来自唯一的那一帧)。
2. **不许倒立** —— v1 的行映射是 `v = cy + f·tanφ/cos a`(`φ = π(0.5 - y/(H-1))`), 即长图
   第 0 行取到的是源图的**下方**(上/下颠倒); 实测把帧 0 缩到同角度区与长图比: 上下翻转
   NCC=0.52、正放只有 0.16 —— 确认倒立。v2 统一按 **上行 = 仰角 +band/2**(与世界地图/真
   equirect 一致: 上=天, 下=地), 视角采样同步改成同一套反变换, 画面内容**与 v1 完全相同**
   (两处一起翻, 互相抵消; 见 `scripts/_verify-unfold-synth.py` 的镜像等价断言)。
3. **不许有黑边** —— v1 输出固定 2:1 画布, 而旋转视频只有 ±36° 有数据 ⇒ 上下各 30% 是纯黑
   (实测 2074x1038, 内容只有 312..725 行)。v2 输出**紧贴有效带的横条**(H = W·band/2π),
   一行黑边都没有; 真 360 素材 band=180° 时自动退化成标准 2:1 等距圆柱。
4. **分辨率要吃满源素材** —— v1 的 W = 2πf(中心采样率), 只有 5.76 px/度, 而源帧中心就有
   8.07 px/度、边缘更高(tan 拉伸)。v2 默认 `supersample=1.5` ⇒ 8.6 px/度, 下游切出来的
   视角明显更锐。

## 「借助模型」与自动适配

- **位姿**: 相邻帧的 ORB 匹配 → `findHomography` + RANSAC(几何模型)拟合**纯偏航单应**, 从
  单应里闭式解出每对的转角与焦距(`f² = -H02/H20 - cx²`), 取**画面中心**的亚像素位移而不是
  关键点中位数(后者被 ORB 的整数像素坐标量化, 且易受误匹配影响); 焦距优先用「整段正好 360°」
  闭环约束反解, 部分弧段则用单对闭式解 —— 于是**没有转满一圈的视频也能展开**。
- **帧率自适应**: 先粗采样估出「每帧画面水平位移(px)」, 再按 `target_shift_percent`(目标位移
  占画面宽的比例)自动决定抽帧步长 —— 转得快就少抽、转得慢就多抽; 超过一圈自动截到一圈并
  把总转角吸附成 2π(消掉一圈后的接缝错位)。
- **俯仰漂移**: 手持旋转会有轻微抬头/低头, 会让长图地平线歪掉。用「相邻帧中心竖直位移」估每帧
  俯仰角, 写进映射(俯仰让映射不再可分离, 但仍只算 2W×H 个采样点, 3 秒级)。

输出 `panorama` / `valid_band`(有效竖向跨度, 接下游 v_range)/ `v_center`(竖向中心, 接 v_center) /
`report`(帧数·角速率·解出的 f 与 h_fov·接缝数·曝光匹配量等)。

坐标/参数口径: 外参 w2c 取 `R.T`、相机在球心(纯旋转 ⇒ 平移恒 0), 内参
`f_px = (size/2)/tan(fov/2)`、`cx=cy=(size-1)/2`, 与 `ComfyUI-HYWM2` 的 `HYWM2SamplePanorama`
一致(等距圆柱的**竖直朝向**按上面第 2 条修正, 上游原式的 up/down 与真 equirect 图相反)。
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from comfy_api.latest import io

logger = logging.getLogger(__name__)

DEFAULT_MAX_FRAMES = 240
DEFAULT_TARGET_SHIFT = 12.0        # 相邻采样帧的目标位移(占画面宽度 %)
DEFAULT_SUPERSAMPLE = 1.5
_ORB_FEATURES = 3000
_ORB_FAST_THRESHOLD = 10
_MIN_MATCHES = 12
_RANSAC_PX = 2.5
_MAX_ABS_A = math.radians(62.0)    # 只用光学轴 ±62° 以内的像素(更外面畸变/插值都差)
_MIN_COS_A = 0.15
_F_LO_FRAC, _F_HI_FRAC = 0.15, 2.0   # 焦距合理区间(相对源画面宽度, 即 h_fov 约 30°~147°)
_GAIN_CLAMP = (0.85, 1.18)


# ──────────────────────────────────────────────────────────────── 通用小工具


def _to_u8_rgb(frame: torch.Tensor) -> np.ndarray:
    """IMAGE 单帧 float 0..1 [H,W,3] → uint8 RGB (与 ComfyUI 存图口径一致)。"""
    a = (frame.detach().float().cpu().numpy() * 255.0 + 0.5).clip(0, 255)
    return a.astype(np.uint8)


def _wrap_pi(a: np.ndarray) -> np.ndarray:
    """把角度绕回 [-π, π)。"""
    return (a + np.pi) % (2 * np.pi) - np.pi


def _orb_gray(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def _detect(orb: cv2.ORB, rgb: np.ndarray):
    """单帧 ORB 特征点 + 描述子。"""
    return orb.detectAndCompute(_orb_gray(rgb), None)


def _match_pts(k1, d1, k2, d2):
    """两帧 ORB 匹配 → 匹配点坐标对 (p1, p2); 太少返回 None。"""
    if d1 is None or d2 is None or not k1 or not k2:
        return None
    m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    if len(m) < _MIN_MATCHES:
        return None
    p1 = np.array([k1[x.queryIdx].pt for x in m], dtype=np.float64)
    p2 = np.array([k2[x.trainIdx].pt for x in m], dtype=np.float64)
    return p1, p2


def _match_dx(k1, d1, k2, d2) -> float | None:
    """两帧 ORB 匹配 → 水平位移中位数 (px, 正=画面内容右移); 粗采样估速率用。"""
    got = _match_pts(k1, d1, k2, d2)
    if got is None:
        return None
    p1, p2 = got
    dx = p2[:, 0] - p1[:, 0]
    keep = np.abs(dx - np.median(dx)) < 40.0
    return float(np.median(dx[keep])) if keep.any() else None


def _pair_pose(p1: np.ndarray, p2: np.ndarray, cx: float, cy: float):
    """相邻帧匹配点 → 纯偏航单应, 返回 (dx, dy, n_in, f_est, sin_dt, cos_dt, inlier_mask)。

    纯偏航时 `H = λ·K·Ry(-Δ)·K⁻¹`(Δ = 后一帧偏航增量), 展开后:
        f² = -H[0,2]/H[2,0] - cx²          (焦距, 单位: 像素/弧度; λ 约掉)
        sinΔ = (H[2,0]/H[1,1])·f
        cosΔ = (H[2,2] + H[2,0]·cx)/H[1,1]      ← 注意 H[2,2] = c + s·cx/f, 不是 c
    中心位移 (dx, dy) 用整幅单应投影画面中心得到 —— 亚像素、且用上了全部内点, 比关键点
    位移中位数稳得多(v1 就是栽在"整数像素 + 误匹配"上)。

    参数:
        p1, p2: 前一帧/后一帧里的匹配点 (x,y) 像素坐标。
        cx, cy: 主点(取画面中心)。
    返回:
        tuple | None: (dx, dy, 内点数, f 估计或 None, u, cosΔ, 内点掩码);
                      其中 `sinΔ = u·f`(用最终选定的 f 换算), 便于闭环反解 f。
    """
    H, mask = cv2.findHomography(p1, p2, cv2.RANSAC, _RANSAC_PX, maxIters=5000, confidence=0.999)
    if H is None:
        return None
    inl = np.zeros(len(p1), dtype=bool) if mask is None else mask.ravel().astype(bool)
    n_in = int(inl.sum())
    if n_in < max(8, int(0.2 * len(p1))):
        return None
    q = H @ np.array([cx, cy, 1.0])
    if abs(q[2]) < 1e-9:
        return None
    dx = float(q[0] / q[2] - cx)
    dy = float(q[1] / q[2] - cy)
    f_est = u = cos_dt = dxm = None
    if inl.any():
        dxm = float(np.median(p2[inl, 0] - p1[inl, 0]))          # 平移污染下比单应中心更稳
    if abs(H[2, 0]) > 1e-9 and abs(H[1, 1]) > 1e-9:
        v = -H[0, 2] / H[2, 0] - cx * cx
        if v > 0:
            f_est = float(math.sqrt(v))
            lam = float(H[1, 1])
            u = float(H[2, 0] / lam)                              # sinΔ = u·f
            cos_dt = float((H[2, 2] + H[2, 0] * cx) / lam)        # cosΔ
            if abs(u * f_est) > 1.3 or abs(cos_dt) > 1.3:
                u = cos_dt = None
    return dx, dy, n_in, f_est, u, cos_dt, inl, dxm


def _median_patch(img: np.ndarray, pts: np.ndarray, half: int = 2) -> np.ndarray:
    """在 (x,y) 点上取 (2·half+1)² 局部中值颜色, 返回 [N,3] float。"""
    h, w = img.shape[:2]
    out = np.empty((len(pts), 3), dtype=np.float64)
    for i, (x, y) in enumerate(pts):
        x0, x1 = int(max(0, x - half)), int(min(w, x + half + 1))
        y0, y1 = int(max(0, y - half)), int(min(h, y + half + 1))
        out[i] = np.median(img[y0:y1, x0:x1], axis=(0, 1))
    return out


def _pair_gain(img_a: np.ndarray, img_b: np.ndarray, pa: np.ndarray, pb: np.ndarray):
    """相邻帧在**同一物理点**上的亮度关系: b ≈ s·a + t (每通道); 不可靠时返回 None。"""
    if len(pa) < 24:
        return None
    va, vb = _median_patch(img_a, pa), _median_patch(img_b, pb)
    scale = np.empty(3)
    bias = np.empty(3)
    for c in range(3):
        a, b = va[:, c], vb[:, c]
        denom = float(np.dot(a, a))
        if denom < 1e-6:
            return None
        s = float(np.dot(a, b) / denom)
        if not (_GAIN_CLAMP[0] <= s <= _GAIN_CLAMP[1]):
            return None
        scale[c] = s
        bias[c] = float(np.median(b - s * a))
    return scale, bias


def _f_from_correspondences(shots, cx: float, cy: float, f_lo: float, f_hi: float):
    """由**对应点**直接解焦距(纯旋转最小模型, 与 8 自由度单应无关, 因此不受平移污染)。

    纯偏航时, 同一物理点在两帧里的方位角差**必须等于两帧的转角** Δ:
        a1 = atan((u1-cx)/f),  a2 = atan((u2-cx)/f)   ⇒  Δ_i = a1 - a2
    以及竖直关系 `(v2-cy)·cos(a2) = (v1-cy)·cos(a1)`(对同一 f 精确成立)。
    代价必须**无量纲**, 否则 ΣΔ→0(f→∞) 会让它单调下降、退化成"f 越大越好":
        cost = MAD(Δ)/|median(Δ)|          相对离散度(真 f 处 → 0)
             + median|r| / median|v-cy|    竖直残差(真 f 处 → 0)
    一维搜索(粗网格 + 黄金分割)取最小者。

    参数:
        shots: [(p1, p2)] 每对的 RANSAC 内点坐标 [N,2]。
        cx, cy: 主点。
        f_lo, f_hi: 搜索区间(像素/弧度)。
    返回:
        (f, cost) 或 (0.0, inf)。
    """
    shots = [(a, b) for a, b in shots if len(a) >= 12]
    if not shots:
        return 0.0, float("inf")
    # 转角信号太弱(近乎静止)时, 代价里的 MAD(Δ)/|median Δ| 会退化成纯噪声比值 ⇒ 交回上层。
    f_ref = math.sqrt(max(f_lo, 1e-6) * max(f_hi, 1e-6))
    signal = max(abs(float(np.median(np.arctan((p1[:, 0] - cx) / f_ref)
                                   - np.arctan((p2[:, 0] - cx) / f_ref))))
                 for p1, p2 in shots)
    if signal < math.radians(1.0):
        return 0.0, float("inf")

    def cost(f):
        tot = 0.0
        for p1, p2 in shots:
            a1 = np.arctan((p1[:, 0] - cx) / f)
            a2 = np.arctan((p2[:, 0] - cx) / f)
            d = a1 - a2
            med = float(np.median(d))
            tot += float(np.median(np.abs(d - med))) / max(abs(med), 1e-6)
            r = (p2[:, 1] - cy) * np.cos(a2) - (p1[:, 1] - cy) * np.cos(a1)
            base = max(float(np.median(np.abs(p1[:, 1] - cy))), 1.0)
            tot += float(np.median(np.abs(r))) / base
        return tot / len(shots)

    grid = np.geomspace(max(4.0, f_lo), f_hi, 80)
    best = min(grid, key=cost)
    lo, hi = best / 1.4, best * 1.4
    for _ in range(30):                                                 # 黄金分割细化
        m1 = lo + (hi - lo) * 0.382
        m2 = lo + (hi - lo) * 0.618
        if cost(m1) < cost(m2):
            hi = m2
        else:
            lo = m1
    f = (lo + hi) / 2
    return float(f), float(cost(f))


def _f_from_overlap(rgbs, shots, pairs_shot_idx, cx: float, cy: float,
                    f_lo: float, f_hi: float, src_w: int, src_h: int):
    """用**相邻帧重叠区的稠密光度一致性**定焦距(最硬的判据, 不受平移污染)。

    对候选 f: 每对相邻帧的转角 Δ 由对应点给出(`median(a1-a2)`), 然后把两帧各自按
        u = cx + f·tan(a),   v = cy + f·tan(φ)/cos(a)
    重采样到同一组世界方向 (a, φ) 上 —— f 正确时两帧看到的是**同一个表面**, 逐像素差最小;
    f 偏大/偏小都会让重叠区张开或挤压 ⇒ 差值变大。这就是"展开是否自洽"的直接度量。

    参数:
        rgbs: 采样帧 uint8 列表。
        shots: 每对的 RANSAC 内点坐标对。
        pairs_shot_idx: 每个 shots 元素对应的 (前一帧下标, 后一帧下标)。
        cx, cy: 主点。
        f_lo, f_hi: 搜索区间。
        src_w, src_h: 源帧尺寸。
    返回:
        (f, cost)。shots 为空返回 (0.0, inf)。
    """
    if not shots:
        return 0.0, float("inf")
    A = None

    def cost(f):
        """返回 (平均绝对差, 有效对数)。

        有效对数为 0 **不能**视为"完美契合"(成本 0): 恒等/静止视频的 Δ≈0 会被下面 `|d|<1e-4`
        全部跳过, 于是每个候选 f 都拿到 0 分, 搜索就把 f 推到区间下界(实测 h_fov 假解成 143°)。
        上层据此判定"没有可用重叠"并回退到其它判据。
        """
        tot, cnt = 0.0, 0
        amax = max(2.0, math.degrees(math.atan(max(8.0, src_w / 2.0 - 8) / f)) * 0.85)
        vmax = max(2.0, math.degrees(math.atan(max(8.0, src_h / 2.0 - 8) / f)) * 0.85)
        grid = None
        for k, (q1, q2) in enumerate(shots):
            d = float(np.median(np.arctan((q1[:, 0] - cx) / f)
                                - np.arctan((q2[:, 0] - cx) / f)))
            if abs(d) < 1e-4:
                continue
            if grid is None:
                aa = np.radians(np.linspace(-amax, amax, 44))[None, :]
                pp = np.radians(np.linspace(-vmax, vmax, 34))[:, None]
                grid = (np.broadcast_to(aa, (pp.shape[0], aa.shape[1])).copy(),
                        np.broadcast_to(pp, (pp.shape[0], aa.shape[1])).copy())
            AA, PP = grid
            i, j = pairs_shot_idx[k]

            def sample(a_off):
                a = AA + a_off
                ca = np.cos(a)
                return (cx + f * np.tan(a)).astype(np.float32), \
                       (cy + f * np.tan(PP) / ca).astype(np.float32), a, ca

            ui, vi, _, cai = sample(0.0)
            uj, vj, _, caj = sample(-d)
            m = 4
            ok = ((ui >= m) & (ui <= src_w - 1 - m) & (vi >= m) & (vi <= src_h - 1 - m)
                  & (uj >= m) & (uj <= src_w - 1 - m) & (vj >= m) & (vj <= src_h - 1 - m)
                  & (np.abs(cai) > 0.2) & (np.abs(caj) > 0.2))
            if ok.sum() < 150:
                continue
            ri = cv2.remap(rgbs[i], ui, vi, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            rj = cv2.remap(rgbs[j], uj, vj, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            dif = ri[ok].astype(np.float32) - rj[ok].astype(np.float32)
            dif -= dif.mean(axis=0, keepdims=True)          # 去掉帧间整体亮度差, 只比结构
            tot += float(np.mean(np.abs(dif)))
            cnt += 1
        return tot / max(cnt, 1), cnt

    gg = np.geomspace(max(4.0, f_lo), f_hi, 26)
    vals = [cost(x) for x in gg]
    usable = [k for k, (_, c) in enumerate(vals) if c > 0]
    if not usable:                                          # 一对有效重叠都没有 ⇒ 交回上层
        return 0.0, float("inf")
    j = int(min(usable, key=lambda k: vals[k][0]))
    lo = gg[max(0, j - 1)]
    hi = gg[min(len(gg) - 1, j + 1)]
    for _ in range(18):                                     # 黄金分割细化
        m1 = lo + (hi - lo) * 0.382
        m2 = lo + (hi - lo) * 0.618
        if cost(m1)[0] < cost(m2)[0]:
            hi = m2
        else:
            lo = m1
    f = (lo + hi) / 2
    val, cnt = cost(f)
    return (float(f), float(val)) if cnt > 0 else (0.0, float("inf"))


def _sample_rows(img: np.ndarray, map_x: np.ndarray, map_y: np.ndarray):
    """按等距圆柱反投影采样一帧; map_x 可为 [W] 或 [H,W], map_y 为 [H,W]。"""
    if map_x.ndim == 1:
        map_x = np.broadcast_to(map_x[None, :], map_y.shape)
    warped = cv2.remap(img, map_x.astype(np.float32), map_y.astype(np.float32),
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return warped.astype(np.float32)


# ──────────────────────────────────────────────────────────────── 节点 1


class FallingTSWorldSurroundPanoramaNode(io.ComfyNode):
    """360° 视频 → 横向展开长图(等距圆柱条带) + 有效带信息。"""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="WorldSurroundPanorama",
            display_name="FallingTS 360°视频 → 横向展开长图",
            category="FallingTS/3D",
            description=(
                "把一段 360° 环绕视频展开成一张**横向长图**(等距圆柱): 上行=天, 下行=地, "
                "有效带紧贴内容(无黑边)。真 360 相机导出的 equirect 视频直接抽帧。"
                "普通镜头原地旋转拍的视频: ORB+RANSAC 纯偏航单应解出逐帧亚像素位姿与焦距, "
                "逐像素只取一帧(winner-take-all) ⇒ 无重影; 抽帧步长按画面位移自动适配转速。"
                "输出 panorama / valid_band(接下游 v_range)/ v_center / report。"
            ),
            inputs=[
                io.Video.Input(
                    "video",
                    optional=True,
                    tooltip="360° 环绕视频 (md 数据表 VIDEO 列); 与 images 二选一。",
                ),
                io.Image.Input(
                    "images",
                    optional=True,
                    tooltip="也可直接给帧序列 (IMAGE 批); video 与 images 都给时用 video。",
                ),
                io.Combo.Input(
                    "mode",
                    options=["auto", "equirect", "unfold"],
                    default="auto",
                    tooltip=(
                        "auto = 帧宽高比≈2:1 视为 equirect 直接抽帧, 否则走旋转展开; "
                        "equirect = 真 360 相机的等距圆柱视频; unfold = 强制按原地旋转展开。"
                    ),
                ),
                io.Int.Input(
                    "frame_index",
                    default=-1,
                    min=-1,
                    max=100000,
                    tooltip="equirect 模式抽第几帧 (-1 = 正中间那帧); unfold 模式忽略。",
                ),
                io.Int.Input(
                    "max_frames",
                    default=DEFAULT_MAX_FRAMES,
                    min=8,
                    max=600,
                    step=4,
                    tooltip="抽帧数上限(实际步长按画面位移自动定, 转得快就抽得少)。",
                ),
                io.Float.Input(
                    "target_shift_percent",
                    default=DEFAULT_TARGET_SHIFT,
                    min=4.0,
                    max=40.0,
                    step=1.0,
                    tooltip=(
                        "相邻采样帧之间允许的画面位移(占宽度%): 12 → 约 100px。越小抽得越密"
                        "(更稳更慢), 越大越稀疏(更快, 但重叠变少)。"
                    ),
                ),
                io.Float.Input(
                    "h_fov",
                    default=0.0,
                    min=0.0,
                    max=180.0,
                    step=1.0,
                    tooltip="水平 FOV: 0 = 自动(闭环/单应闭式解); >0 = 强制使用该值。",
                ),
                io.Int.Input(
                    "out_width",
                    default=0,
                    min=0,
                    max=8192,
                    step=2,
                    tooltip="长图宽度: 0 = 2πf·supersample (像素/弧度与源帧对齐)。",
                ),
                io.Float.Input(
                    "supersample",
                    default=DEFAULT_SUPERSAMPLE,
                    min=0.5,
                    max=4.0,
                    step=0.1,
                    tooltip=(
                        "长图相对「源帧中心采样率」的倍率: 1.0 = 与源帧中心同密度; "
                        "1.5 更锐(源帧边缘 tan 拉伸处本来就有更多像素), 代价是文件更大。"
                    ),
                ),
                io.Int.Input(
                    "seam_feather",
                    default=7,
                    min=0,
                    max=16,
                    step=1,
                    tooltip=(
                        "接缝羽化半宽(像素): 只在换帧处对**低频**做过渡(高频仍来自唯一一帧)"
                        " ⇒ 看不到亮度台阶, 也不会有重影。0 = 硬切。"
                    ),
                ),
            ],
            outputs=[
                io.Image.Output(display_name="panorama"),
                io.Float.Output(display_name="valid_band"),
                io.Float.Output(display_name="v_center"),
                io.String.Output(display_name="report"),
            ],
        )

    @classmethod
    def execute(cls, video=None, images=None, mode="auto", frame_index=-1,
                max_frames=DEFAULT_MAX_FRAMES, target_shift_percent=DEFAULT_TARGET_SHIFT,
                h_fov=0.0, out_width=0, supersample=DEFAULT_SUPERSAMPLE,
                seam_feather=3) -> io.NodeOutput:
        """视频 → 横向展开长图。

        参数:
            video: ComfyUI VIDEO 对象 (None 时改用 images)。
            images: IMAGE 批 [T,H,W,3]。
            mode: "auto" | "equirect" | "unfold"。
            frame_index: equirect 模式选帧 (-1 = 中间)。
            max_frames: 抽帧数上限。
            target_shift_percent: 相邻采样帧的目标位移(占宽度%)。
            h_fov: >0 时强制水平 FOV。
            out_width: >0 时强制输出宽度。
            supersample: 输出宽度相对源帧中心采样率的倍率。
            seam_feather: 接缝低频羽化半宽(px)。

        返回:
            io.NodeOutput: (panorama[1,H,W,3] float, valid_band 度, v_center 度, report);
                            无输入时 panorama=None 且不报错。
        """
        frames = cls._frames(video, images)
        if frames is None or frames.shape[0] == 0:
            logger.warning("[WorldSurroundPanorama] 没有视频/帧输入, 输出空")
            return io.NodeOutput(None, 0.0, 0.0, "无输入")

        total = int(frames.shape[0])
        src_h, src_w = int(frames.shape[1]), int(frames.shape[2])
        is_equirect = abs(src_w / src_h - 2.0) <= 0.1
        use_equirect = mode == "equirect" or (mode == "auto" and is_equirect)

        if use_equirect:
            idx = total // 2 if frame_index < 0 else max(0, min(frame_index, total - 1))
            pano = _to_u8_rgb(frames[idx])
            report = (f"equirect 直通: 抽第 {idx}/{total} 帧, {src_w}x{src_h}, "
                      f"有效竖向 180°(真全景), 上行=天")
            logger.info("[WorldSurroundPanorama] %s", report)
            return io.NodeOutput(cls._as_image(pano), 180.0, 0.0, report)

        if mode == "auto":
            logger.info("[WorldSurroundPanorama] 帧宽高比 %.2f ≠ 2:1, 走旋转展开", src_w / src_h)

        orb = cv2.ORB_create(_ORB_FEATURES, scaleFactor=1.2, nlevels=8,
                             fastThreshold=_ORB_FAST_THRESHOLD)

        # ── 1) 粗采样估「每帧画面位移(px)」→ 自动定抽帧步长(帧率/转速自适应) ──
        n0 = max(8, min(total, 48))
        idx0 = np.unique(np.linspace(0, total - 1, n0).round().astype(int))
        feats0 = [_detect(orb, _to_u8_rgb(frames[int(i)])) for i in idx0]
        d0 = [_match_dx(feats0[i][0], feats0[i][1], feats0[i + 1][0], feats0[i + 1][1])
              for i in range(len(feats0) - 1)]
        good0 = [abs(x) for x in d0 if x is not None]
        if len(good0) < max(4, len(d0) // 2):
            raise ValueError(
                f"WorldSurroundPanorama: 相邻帧匹配失败过多 ({len(good0)}/{len(d0)}) —— "
                f"这段视频不是「原地旋转」的镜头 (平移/大范围变焦/黑场会这样), "
                f"请改用 equirect 模式并喂真 360 相机导出的视频。"
            )
        step0 = float(np.median(np.diff(idx0))) if len(idx0) > 1 else 1.0
        px_per_frame = max(0.01, float(np.median(good0)) / max(step0, 1e-6))
        target_px = max(8.0, target_shift_percent / 100.0 * src_w)
        stride = max(1, int(round(target_px / px_per_frame)))
        if len(np.arange(0, total, stride)) < 12:            # 抽太少就加密
            stride = max(1, total // 12)
        if max_frames > 0:
            stride = max(stride, int(math.ceil((total - 1) / max_frames)))
        idxs = np.arange(0, total, stride, dtype=int)
        if idxs[-1] != total - 1:                            # 末帧必须采到: 否则"是否整整一圈"的
            idxs = np.append(idxs, total - 1)                # 闭环判定会漏掉尾巴(实测 48 帧素材
        idxs = np.unique(idxs)                               # 因丢了末帧, 采样弧少 7.7°)

        # ── 1b) 自适应补密: **一个全局步长追不上不均匀转速** ──────────────────
        #   · 长静止段会把「每帧画面位移的中位数」拉到 ~0 ⇒ 步长爆掉(实测 43 帧只抽到 15 帧,
        #     整段转角被低估成 10°, 焦距还被解到搜索下界 143°);
        #   · 甩镜/突发段每帧位移远超目标 ⇒ 相邻采样帧隔 40° 以上方位, 匹配失败或整段漏方位。
        #   做法: 反复找出「帧间位移超过上限」的相邻采样对, 一次给所有这样的对插一帧中间帧,
        #   直到全部回到上限内(或撞 max_frames / 帧间隔已到 1 —— 后者是源视频原生转速过快,
        #   属素材上限, 只在 report 里点出来)。
        walk_px = float(np.sum(good0))
        if walk_px < 0.06 * src_w:
            raise ValueError(
                f"WorldSurroundPanorama: 整段视频画面几乎没有横向移动(累计位移 {walk_px:.1f}px, "
                f"约 {math.degrees(math.atan(walk_px / max(src_w, 1))):.1f}° 量级) —— "
                f"这不是环绕/旋转镜头, 无法解焦距并展开。"
            )
        dens_limit = max(target_px * 3.0, 24.0)
        feat_cache: dict = {}

        def feat_of(i):
            if i not in feat_cache:
                feat_cache[i] = _detect(orb, _to_u8_rgb(frames[i]))
            return feat_cache[i]

        cap = max(1, int(max_frames)) if max_frames > 0 else 10 ** 9
        cx_r, cy_r = (src_w - 1) / 2.0, (src_h - 1) / 2.0
        idx_cur = [int(v) for v in idxs]
        added, rounds = 0, 0
        while rounds < 8 and len(idx_cur) < cap:
            mids = []
            for j in range(len(idx_cur) - 1):
                a, b = idx_cur[j], idx_cur[j + 1]
                if b - a <= 1:
                    continue
                ka, da = feat_of(a)
                kb, db = feat_of(b)
                # 判据 = **几何模型解不出来**(匹配不足 / RANSAC 失败) 或 **位移超上限**。
                # ⚠️ 不能用"单应内点比例低"当判据: 真实素材相邻帧本身有内容漂移/运动模糊, 内点比例
                # 常年 0.24~0.37 却完全解得出几何 —— 实测拿比例<0.40 触发会给 0031 视频平白补 11 帧,
                # 焦距被带偏 311.8→332.4px、长图与源帧相关 0.74→0.51。而合成甩镜段那两对是
                # RANSAC 直接失败(比例判据在这里同样会亮, 但位移中位数会骗人, 见上)。
                got = _match_pts(ka, da, kb, db)
                pose = _pair_pose(got[0], got[1], cx_r, cy_r) if got else None
                bad = pose is None or pose[7] is None or abs(pose[7]) > dens_limit
                if bad:
                    mid = (a + b) // 2
                    if mid not in idx_cur:
                        mids.append((j + 1, mid))
            if not mids:
                break
            for pos, mid in sorted(mids, reverse=True):
                if len(idx_cur) >= cap:
                    break
                idx_cur.insert(pos, mid)
                added += 1
            rounds += 1
        # 静止段会留下一串内容几乎相同的采样帧(赢家打分并列 ⇒ 接缝乱跳 + 白算), 保守抽稀:
        # 只丢「与上一保留帧位移 < 0.5px」的帧, 且至少留 8 帧。
        keep = [idx_cur[0]]
        for j in range(1, len(idx_cur)):
            a, b = keep[-1], idx_cur[j]
            ka, da = feat_of(a)
            kb, db = feat_of(b)
            dxm = _match_dx(ka, da, kb, db)
            if dxm is None or abs(dxm) >= 0.5 or len(idx_cur) - j + len(keep) <= 8:
                keep.append(b)
        dropped = len(idx_cur) - len(keep)
        if len(keep) >= 2:
            idx_cur = keep
        too_coarse = 0
        for j in range(len(idx_cur) - 1):
            if idx_cur[j + 1] - idx_cur[j] != 1:
                continue
            ka, da = feat_of(idx_cur[j])
            kb, db = feat_of(idx_cur[j + 1])
            dxm = _match_dx(ka, da, kb, db)
            if dxm is None or abs(dxm) > dens_limit:
                too_coarse += 1
        idxs = np.unique(np.array(sorted(idx_cur), dtype=int))
        dens = f"自适应补密 +{added}/抽稀 -{dropped}"
        if too_coarse:
            dens += f", ⚠ {too_coarse} 处帧间隔内位移仍超目标(源转速过快, 可能漏方位)"

        # ── 2) 采样帧特征 + 逐对位姿(单应 RANSAC → 亚像素) ──
        rgb_all = [_to_u8_rgb(frames[int(i)]) for i in idxs]
        f_lo, f_hi = _F_LO_FRAC * src_w, _F_HI_FRAC * src_w
        cx0, cy0 = (src_w - 1) / 2.0, (src_h - 1) / 2.0
        feats = [_detect(orb, rgb) for rgb in rgb_all]
        pairs, f_ests, gains_scale, gains_bias, shots, shot_idx = [], [], [], [], [], []
        prev_tf = (np.ones(3), np.zeros(3))
        for i in range(len(feats) - 1):
            k1, d1 = feats[i]
            k2, d2 = feats[i + 1]
            got = _match_pts(k1, d1, k2, d2)
            pose = _pair_pose(got[0], got[1], cx0, cy0) if got else None
            if pose is None:
                dxm = _match_dx(k1, d1, k2, d2)
                if dxm is None:
                    raise ValueError("WorldSurroundPanorama: 相邻采样帧匹配不足, 无法估位姿")
                pairs.append((float(dxm), 0.0, 0, None, None, None, None, float(dxm), -1))
            else:
                p1, p2 = got
                mask = pose[6]
                shots.append((p1[mask], p2[mask]))
                shot_idx.append((i, i + 1))
                pairs.append(pose + (len(shots) - 1,))
                g = _pair_gain(rgb_all[i], rgb_all[i + 1], p1[pose[6]], p2[pose[6]])
                gains_scale.append(g[0] if g else None)
                gains_bias.append(g[1] if g else None)
                if pose[3] is not None and f_lo <= pose[3] <= f_hi:
                    f_ests.append(pose[3])

        # ── 3) 焦距: ① 对应点纯旋转一致性(主) ② 360° 闭环 ③ 单对单应闭式解 ──
        f_pair = float(np.median(f_ests)) if f_ests else 0.0
        f_cons, _ = _f_from_correspondences(shots, cx0, cy0, f_lo, f_hi)
        dxs = np.array([p[7] if p[7] is not None else p[0] for p in pairs], dtype=np.float64)
        adx = np.abs(dxs)
        # 闭环: Σ atan(|dx|/f) = 2π(纯旋转转角可加)。Σ 随 f 单调下降 ⇒ 用 [小, 大] 夹住。
        f_closure = 0.0
        if adx.sum() > 0 and float(np.sum(np.arctan(adx / 20.0))) >= 2 * math.pi:
            lo, hi = 20.0, 1.0e5
            for _ in range(70):
                mid = (lo + hi) / 2
                if float(np.sum(np.arctan(adx / mid))) > 2 * math.pi:
                    lo = mid
                else:
                    hi = mid
            f_closure = (lo + hi) / 2
        span_h = float(sum(abs(math.atan2(p[4] * (f_pair or 1.0), p[5]))
                           for p in pairs if p[4] is not None)) if f_pair > 0 else 0.0
        cross = (f"闭环 {f_closure:.1f}px/对应点 {f_cons:.1f}px/单对 {f_pair:.1f}px"
                 f"(单对转角合计 {math.degrees(span_h):.0f}°)")
        # 「正好一圈」约束落在**对应点转角**上(而不是有偏的中位位移):
        #   Σ_pair median_i(a1-a2)(f) = 2π  ⇒ 几何与总转角同时自洽
        def span_shot(f_):
            return float(sum(float(np.median(np.arctan((q1[:, 0] - cx0) / f_)
                                             - np.arctan((q2[:, 0] - cx0) / f_)))
                             for q1, q2 in shots))

        f_full, span_full, arc_deg = 0.0, 0.0, 0.0
        if shots:
            gg = np.geomspace(max(4.0, f_lo), f_hi, 240)
            sp = np.array([span_shot(x) for x in gg])
            cand = np.flatnonzero(np.abs(sp - 2 * math.pi) < 0.25)
            if cand.size:
                j = int(cand[np.argmin(np.abs(np.log(gg[cand] / max(f_cons, 1e-6))))])
                f_full, span_full = float(gg[j]), float(sp[j])
            arc_deg = math.degrees(span_shot(f_cons)) if f_cons > 0 else 0.0

        f_photo, _ = _f_from_overlap(rgb_all, shots, shot_idx, cx0, cy0, f_lo, f_hi,
                                     src_w, src_h)

        if h_fov > 0:
            f = (src_w / 2) / math.tan(math.radians(h_fov) / 2)
            note = f"h_fov={h_fov:.1f}° (强制; {cross})"
        elif f_photo > 0:
            f = f_photo
            note = (f"焦距={f:.1f}px 由**相邻帧重叠区稠密光度一致性**解出 → h_fov≈"
                    f"{2 * math.degrees(math.atan((src_w / 2) / f)):.1f}° "
                    f"(闭环 {f_closure:.0f}px/对应点 {f_cons:.0f}px/单对 {f_pair:.0f}px 作交叉校验; "
                    f"该 f 下整段转角约 {math.degrees(span_shot(f)):.0f}°)")
        elif f_full > 0:
            f = f_full
            note = (f"焦距={f:.1f}px 由「对应点转角合计=360°」解出 → h_fov≈"
                    f"{2 * math.degrees(math.atan((src_w / 2) / f)):.1f}° "
                    f"(一致性最优值 {f_cons:.1f}px ⇒ 该视频转角合计约 {arc_deg:.0f}°, 一圈约束修正 "
                    f"{(f / max(f_cons, 1e-6) - 1) * 100:+.0f}%)")
        elif f_cons > 0:
            f = f_cons
            note = (f"焦距={f:.1f}px 由**对应点纯旋转一致性**解出 → h_fov≈"
                    f"{2 * math.degrees(math.atan((src_w / 2) / f)):.1f}° "
                    f"(整段约 {arc_deg:.0f}° < 360°, 长图会缺方位; {cross})")
        elif f_closure > 0:
            f = f_closure
            note = (f"焦距由 360° 闭环解出 f={f:.1f}px → h_fov≈"
                    f"{2 * math.degrees(math.atan((src_w / 2) / f)):.1f}° ({cross})")
        elif f_pair > 0:
            f = f_pair
            note = (f"焦距由单对纯偏航单应闭式解 f={f:.1f}px → h_fov≈"
                    f"{2 * math.degrees(math.atan((src_w / 2) / f)):.1f}° (整段不足一圈)")
        else:
            f = (src_w / 2) / math.tan(math.radians(90.0) / 2)
            note = "警告: 位姿估计失败, 已回退 h_fov=90° (长图会缺一部分方位)"

        # ── 4) 逐帧偏航: 由**对应点**在同一 f 下直接解(median(a1-a2), 纯旋转下 a1-a2=Δ),
        #      与 f 的估计同源 ⇒ 几何与转角自洽; 无单应的帧退水平位移近似。 ──
        d_theta = []
        for p in pairs:
            if p[8] >= 0:
                q1, q2 = shots[p[8]]
                d_theta.append(float(np.median(np.arctan((q1[:, 0] - cx0) / f)
                                               - np.arctan((q2[:, 0] - cx0) / f))))
            else:
                d_theta.append(-math.atan(p[7] / f))
        yaws = np.concatenate([[0.0], np.cumsum(d_theta)])
        cut = len(yaws)
        if abs(yaws[-1]) > 2 * math.pi + math.radians(3):
            beyond = np.flatnonzero(np.abs(yaws) > 2 * math.pi)
            cut = int(beyond[0]) if beyond.size else len(yaws)
            yaws = yaws[:cut]
        if cut < 8:
            raise ValueError("WorldSurroundPanorama: 有效采样帧太少(不足 8), 无法展开")
        span = float(abs(yaws[-1] - yaws[0]))
        # 闭环检测: 首末采样帧内容若几乎重合, 说明这段视频**确实转了整整一圈** —— 此时把总转角
        # 吸附成 2π 可以一次性消掉"逐帧位移累积的系统偏差"(实测量到 311° 而真值是 360°)。
        # ⚠️ 只比位移中位数会被**误匹配**骗过: 低纹理素材上首末两帧(可能相隔 200°)的 12~40 个
        # 随机匹配, 其中位数可能恰好很小 ⇒ 误判"整整一圈"、把 200° 硬拉成 360°(实测长图整幅
        # 错位、漂移 31.8° 且不报错)。判据必须带上**几何一致性**:
        #   · 匹配点足够多 (≥40) 且 RANSAC 内点比例 ≥0.3 (真重合是"同一个画面", 内点应占多数);
        #   · 单应中心位移与内点中位位移都要小;
        #   · 在已解出的 f 下、由对应点算出的转角也要小 (<5°) —— 三者同时成立才叫重合。
        loop = _match_pts(feats[0][0], feats[0][1], feats[-1][0], feats[-1][1])
        loop_pose = _pair_pose(loop[0], loop[1], cx0, cy0) if loop else None
        typ = float(np.median(np.abs(dxs))) if dxs.size else 0.0
        closed = False
        if loop_pose is not None and typ > 0 and len(loop[0]) >= 40:
            ratio = loop_pose[2] / max(1, len(loop[0]))
            dt = abs(float(np.median(np.arctan((loop[0][:, 0] - cx0) / f)
                                     - np.arctan((loop[1][:, 0] - cx0) / f))))
            dxm_loop = loop_pose[7]
            closed = (ratio >= 0.3 and dxm_loop is not None
                      and abs(dxm_loop) < 0.35 * typ and dt < math.radians(5.0))
        snapped = False
        # 闭环吸附**只在首末采样帧内容确实重合时**做: 否则"采样弧段恰好落在 360°±10° 内"会被
        # 强行拉成 360°, 引入全局尺度误差(实测 48 帧素材采样弧 352.4° 被拉成 360° ⇒ 尺度错
        # 2.15%, 长图中段漂移 3.3°、NCC 0.57; 而误差 0.3% 的 24 帧素材看不出来)。
        if span > 1e-6 and closed:
            yaws = yaws * (2 * math.pi / span)
            span, snapped = 2 * math.pi, True
        # 吸附后最后一帧与第一帧方位**重合**(同角度的两张图), 若不剔除, 两者得分相等会在
        # 换帧处来回翻转 ⇒ 接缝从 ~20 处暴涨到 100+ 处。直接丢掉重合的尾帧。
        dup = np.abs(np.abs(yaws) - 2 * math.pi) < 1e-6
        if dup.any():
            c_dup = int(np.flatnonzero(dup)[0])
            if c_dup >= 8:
                yaws, cut = yaws[:c_dup], c_dup
        tail = ("; 首末帧重合⇒判定整整一圈并把总转角吸附成 360°" if snapped
                else ("; 整段只转了 %.0f° < 360°, 长图会缺方位" % math.degrees(span)
                      if span < 2 * math.pi - math.radians(1) else ""))

        # ── 5) 拼接: 逐像素 WTA + 对齐细化(修俯仰/亚像素偏航) + 接缝低频羽化 + 自动裁黑边 ──
        band_rad = 2 * math.atan((src_h / 2) / f)
        w_out = int(out_width) if out_width > 0 else int(round(2 * math.pi * f * supersample))
        w_out = int(min(8192, max(64, w_out)))

        pano, stats = cls._unfold_strip(rgb_all[:cut], yaws, f, src_w, src_h, w_out,
                                        band_rad, np.zeros(cut), seam_feather,
                                        gains_scale[:cut - 1], gains_bias[:cut - 1])
        vfov = float(stats["band"])
        v_c = float(stats["center"])
        pxdeg = w_out / 360.0
        rate_deg = math.degrees(math.atan(px_per_frame / f))
        rb, ra = stats["residual"]
        fit = f"" if rb <= 0 else f", 对齐残差 {rb:.1f}→{ra:.1f}/255(修 {stats['aligned']} 帧)"
        report = (
            f"旋转展开: 抽帧 {len(idxs)}→{cut}/{total} (步长 {stride}, 约 {px_per_frame:.1f}px/帧"
            f"≈{rate_deg:.2f}°, {dens}), {note}{tail}; 长图 {pano.shape[1]}x{pano.shape[0]} "
            f"({pxdeg:.2f}px/度), 有效带 {vfov:.1f}°{'' if abs(v_c) < 0.05 else f'(中心 {v_c:+.1f}°)'}, "
            f"空白 {stats['gap']}%, 接缝 {stats['seams']} 处(羽化 {seam_feather}px), "
            f"曝光匹配 {stats['exposure']}{fit}"
        )
        logger.info("[WorldSurroundPanorama] %s", report)
        return io.NodeOutput(cls._as_image(pano), float(vfov), float(v_c), report)

    # ──────────────────────────────────────────────────────── 内部实现

    @staticmethod
    def _frames(video, images):
        """取帧序列: video 优先; 都没有时 None (None 容忍, 不崩)。"""
        if video is not None:
            try:
                return video.get_components().images
            except Exception as exc:                        # noqa: BLE001
                logger.warning("[WorldSurroundPanorama] 视频解码失败: %s", exc)
                return None
        return images

    @staticmethod
    def _as_image(arr: np.ndarray) -> torch.Tensor:
        """uint8 RGB [H,W,3] → IMAGE [1,H,W,3] float 0..1。"""
        return torch.from_numpy(arr.astype(np.float32) / 255.0).unsqueeze(0)

    @staticmethod
    def _exposure_chain(scales, biases, n):
        """把「相邻帧 b≈s·a+t」链成「各帧 → 第 0 帧」的线性变换 [(n,3)]。

        返回 (scale[n,3], bias[n,3]) 或 (None, None)(估计不足/离散太大则放弃)。
        """
        if len(scales) != n - 1 or any(s is None for s in scales):
            return None, None
        S = np.ones((n, 3))
        B = np.zeros((n, 3))
        for i in range(n - 2, -1, -1):
            S[i] = S[i + 1] * scales[i]
            B[i] = S[i + 1] * biases[i] + B[i + 1]
        # 逐对增益的噪声会沿链放大: 静态场景实测链到 20% 反而是伪影 ⇒ 只在"确有曝光漂移"
        # 且量级可信时才启用(2%~12%), 并夹到 ±8% 以内。
        dev = float(np.abs(S - 1.0).max())
        if not (0.02 <= dev <= 0.12):
            return None, None
        S = np.clip(S, 1.0 - 0.08, 1.0 + 0.08)
        return S, B

    @classmethod
    def _unfold_strip(cls, rgbs, yaws, f, src_w, src_h, w_out, band_rad, axis_e, feather,
                      scales, biases):
        """等距圆柱反投影成**横条**长图: 逐像素 winner-take-all(不混合 ⇒ 无重影)。

        约定(与世界地图/真 equirect 一致): 第 0 行 = 仰角 +band/2(天), 最后一行 = -band/2(地)。
        对源像素 (u,v)(v 向下):
            dir_cam = (dx, dy, 1), (dx,dy) = ((u-cx)/f, (v-cy)/f)
            world = Ry(yaw)·dir_cam                (y 向下为正, 与旧口径一致)
            elev  = asin(-world_y/|world|) = asin(-dy/|dir_cam|)     ← 抬头为 +, 于是上行=天
            a     = θ - yaw  (θ = 该像素的方位角)
        反解(对输出像素 (x,y)):
            e = band/2 - band·y/(H-1);  a = θ(x) - yaw
            u = cx + f·tan(a);   v = cy - f·tan(e - E_i)/cos(a)
        E_i 是该帧光轴的**仰角偏置**(俯仰漂移) —— 每帧内容因此落在正确的世界仰角上。

        去重影的三件事:
          ① **winner-take-all**: 每个输出像素只取光学轴夹角最小的那一帧, 从不做帧间平均
             (平均才会产生"双重曝光", 位姿再准也消不掉帧间内容漂移造成的鬼影);
          ② **对齐细化**: 逐帧与当前共识长图做相位相关, 拿到亚像素残差后**穷举 4 种符号组合**
             各测一次残差, 取最小者更新 (偏航, 仰角) —— 不用猜符号, 也顺带修掉手持俯仰漂移;
          ③ **接缝只羽化低频**: 换帧处把两帧的高斯低频做过渡, 高频仍来自唯一那一帧 ⇒
             看不到亮度/位置台阶, 也不会出现第二条边。

        参数:
            rgbs: 采样帧 uint8 列表。
            yaws: 每帧偏航角(弧度, 世界方位角)。
            f: 焦距(像素/弧度)。
            src_w, src_h: 源帧尺寸。
            w_out: 输出宽度。
            band_rad: 输出竖向跨度(弧度) = 源帧竖直 FOV。
            axis_e: 每帧光轴仰角初值(弧度; 由对齐细化再修)。
            feather: 接缝低频羽化半宽(px)。
            scales, biases: 相邻帧曝光关系(可为 None 列表)。

        返回:
            (pano uint8 [H,W,3], stats dict) —— stats 含 gap/seams/exposure/residual/band/center。
        """
        n = len(rgbs)
        h_out = max(2, int(round(w_out * band_rad / (2 * math.pi))))
        theta = math.pi * (2.0 * np.arange(w_out, dtype=np.float64) / (w_out - 1) - 1.0)
        elev = band_rad / 2.0 - band_rad * np.arange(h_out, dtype=np.float64) / (h_out - 1)
        cx, cy = (src_w - 1) / 2.0, (src_h - 1) / 2.0
        yaws = np.asarray(yaws, dtype=np.float64)
        axes = np.asarray(axis_e, dtype=np.float64) if axis_e is not None else np.zeros(n)

        S, B = cls._exposure_chain(scales, biases, n)
        exposure = "关" if S is None else f"开(最大偏差 {np.abs(S - 1).max() * 100:.1f}%)"

        def compose(yy, aa):
            """按当前位姿(偏航 / 光轴仰角)做逐像素 WTA 拼接, 返回 (canvas, best, who, frame_cols, warp)。"""
            amap = _wrap_pi(theta[None, :] - yy[:, None])
            ok = np.abs(amap) < _MAX_ABS_A
            dist = np.abs(amap)
            order = np.argsort(dist, axis=0)
            near1, near2 = order[0], order[1]
            best = np.full((h_out, w_out), -2.0, dtype=np.float32)
            who = np.full((h_out, w_out), -1, dtype=np.int32)
            canvas = np.zeros((h_out, w_out, 3), dtype=np.float32)
            frame_cols = []

            def warp(i, cols, axis):
                a = amap[i, cols]
                cosd = np.cos(a)
                ee = elev - axis
                map_x = cx + f * np.tan(a)
                map_y = cy - f * np.outer(np.tan(ee), 1.0 / cosd)
                out = _sample_rows(rgbs[i], map_x, map_y)
                if S is not None:
                    out = out * S[i].astype(np.float32)[None, None, :] \
                        + B[i].astype(np.float32)[None, None, :]
                valid = ((map_x >= 0) & (map_x <= src_w - 1))[None, :] \
                    & (map_y >= 0) & (map_y <= src_h - 1) & (cosd > _MIN_COS_A)[None, :]
                score = cosd[None, :] * np.cos(ee)[:, None]
                return out, valid, score

            for i in range(n):
                cols = np.flatnonzero(((near1 == i) | (near2 == i)) & ok[i])
                frame_cols.append(cols)
                if cols.size == 0:
                    continue
                out, valid, score = warp(i, cols, aa[i])
                cb, bb, wb = canvas[:, cols], best[:, cols], who[:, cols]
                better = valid & (score > bb)
                bb[better] = score[better]
                wb[better] = i
                cb[better] = out[better]
                canvas[:, cols], best[:, cols], who[:, cols] = cb, bb, wb
            return canvas, best, who, frame_cols, warp

        canvas, best, who, frame_cols, warp = compose(yaws, axes)

        # ── 对齐细化: 每帧与共识长图相位相关 → 4 种符号组合里挑残差最小的更新 ──
        r0, r1 = int(h_out * 0.15), int(h_out * 0.85) + 1
        res_before, res_after, fixed = [], [], 0
        for i in range(n):
            cols = frame_cols[i]
            if cols.size < 24:
                continue
            c0, c1 = int(cols[0]), int(cols[-1]) + 1
            mid = (c0 + c1) // 2
            half = max(8, int((c1 - c0) * 0.35))
            cols_w = np.arange(max(0, mid - half), min(w_out, mid + half + 1))
            out, valid, _ = warp(i, cols_w, axes[i])
            ref = canvas[:, cols_w]
            cov = best[:, cols_w] >= -1.5
            use = cov & valid
            use[:r0] = False
            use[r1:] = False
            if use.sum() < 400:
                continue
            ga = cv2.cvtColor(out.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
            gb = cv2.cvtColor(ref.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
            roi_a, roi_b = ga[r0:r1], gb[r0:r1]
            wy = np.hanning(roi_a.shape[0])[:, None]
            wx = np.hanning(roi_a.shape[1])[None, :]
            w2 = (wy * wx).astype(np.float32)
            (du, dv), _ = cv2.phaseCorrelate(roi_a * w2, roi_b * w2)
            base = float(np.abs(out[use] - ref[use]).mean())
            res_before.append(base)
            if abs(du) > 12.0 or abs(dv) > 12.0 or (abs(du) < 0.05 and abs(dv) < 0.05):
                res_after.append(base)
                continue
            cand = [(base, yaws[i], axes[i])]
            for sy in (1.0, -1.0):
                for sa in (1.0, -1.0):
                    o2, v2, _ = warp(i, cols_w, axes[i] + sa * dv / f)
                    use2 = (best[:, cols_w] >= -1.5) & v2
                    use2[:r0] = False
                    use2[r1:] = False
                    if use2.sum() < 400:
                        continue
                    r2 = float(np.abs(o2[use2] - ref[use2]).mean())
                    cand.append((r2, yaws[i] + sy * du / f, axes[i] + sa * dv / f))
            cand.sort(key=lambda z: z[0])
            if cand[0][0] < base * 0.98:
                _, yaws[i], axes[i] = cand[0]
                fixed += 1
            res_after.append(cand[0][0])
        if fixed:
            canvas, best, who, frame_cols, warp = compose(yaws, axes)
        resid = (float(np.mean(res_before)) if res_before else 0.0,
                 float(np.mean(res_after)) if res_after else 0.0)

        # ── 自动裁掉没被完全覆盖的行(保证一条黑边都没有) ──
        covered = (best >= -1.5)
        frac = covered.mean(axis=1)
        good = frac >= 0.995
        center = h_out // 2
        r_slice = slice(0, h_out)
        if not good.all() and good[center]:
            top = center
            while top > 0 and good[top - 1]:
                top -= 1
            bot = center
            while bot < h_out - 1 and good[bot + 1]:
                bot += 1
            elev_c = band_rad / 2.0 - band_rad * ((top + bot) / 2.0) / (h_out - 1)
            band_keep = band_rad * (bot - top + 1) / (h_out - 1)
            r_slice = slice(top, bot + 1)
            canvas, best, who = canvas[r_slice], best[r_slice], who[r_slice]
            h_out = canvas.shape[0]
            center = h_out // 2
        else:
            elev_c, band_keep = 0.0, band_rad

        # ── 接缝: 换帧处只对低频羽化(高频仍来自唯一赢家 ⇒ 不重影) ──
        row = who[center]
        seam = np.flatnonzero((row[1:] != row[:-1]) & (row[1:] >= 0) & (row[:-1] >= 0)) + 1
        if feather > 0:
            for c in seam:
                A, Bf = int(row[c - 1]), int(row[c])
                cols = np.arange(max(0, c - feather), min(w_out, c + feather + 1))
                if cols.size < 3:
                    continue
                outa, va, _ = warp(A, cols, axes[A])
                outb, vb, _ = warp(Bf, cols, axes[Bf])
                outa, outb = outa[r_slice], outb[r_slice]
                both = (va & vb)[r_slice]
                if not both.any():
                    continue
                t = (cols[-1] - cols).astype(np.float32) / float(cols[-1] - cols[0])
                lo = cv2.GaussianBlur(outa, (0, 0), 2.5) * t[None, :, None] \
                    + cv2.GaussianBlur(outb, (0, 0), 2.5) * (1.0 - t[None, :, None])
                cur = canvas[:, cols]
                hi = cur - cv2.GaussianBlur(cur, (0, 0), 2.5)
                canvas[:, cols] = np.where(both[..., None], lo + hi, cur)

        gap = float((best.max(axis=0) < -1.5).mean() * 100.0)
        pano = canvas.clip(0, 255).astype(np.uint8)
        pano[best < -1.5] = 0
        return pano, {
            "gap": int(round(gap)),
            "seams": int(seam.size),
            "exposure": exposure,
            "residual": resid,
            "aligned": fixed,
            "band": math.degrees(band_keep),
            "center": math.degrees(elev_c),
        }


# ──────────────────────────────────────────────────────────────── 节点 2


class FallingTSWorldPanoramaViewsNode(io.ComfyNode):
    """横向长图 → 一网格透视视角 + 每视角精确 w2c 外参 / 内参。"""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="WorldPanoramaViews",
            display_name="FallingTS 全景 → 视角批 + 位姿",
            category="FallingTS/3D",
            description=(
                "把横向展开长图切成互相重叠的透视视角, 并输出每个视角的 w2c 外参与内参 "
                "(相机都在球心, 纯旋转)。外参口径与 HYWM2SamplePanorama 一致; 竖向采样范围由 "
                "v_center/v_range 决定(接长图的 v_center / valid_band) —— 旋转视频只有一条带, "
                "用它避免切出黑边。"
            ),
            inputs=[
                io.Image.Input("panorama", tooltip="横向展开长图, 如 WorldSurroundPanorama 的输出。"),
                io.Float.Input("fov_degrees", default=80.0, min=30.0, max=120.0, step=1.0,
                               tooltip="每个透视视角的视场角。"),
                io.Float.Input("overlap_percent", default=10.0, min=0.0, max=50.0, step=1.0,
                               tooltip="相邻视角的重叠 (占 FOV 的百分比)。"),
                io.Int.Input("output_size", default=952, min=224, max=2048, step=14,
                             tooltip="方视角的边长; 952 对齐 WorldMirror 的 target_size。"),
                io.Float.Input("v_range", default=150.0, min=5.0, max=180.0, step=5.0,
                               tooltip="长图竖向跨度(度): 接 WorldSurroundPanorama 的 valid_band。"),
                io.Float.Input("v_center", default=0.0, min=-90.0, max=90.0, step=5.0,
                               tooltip="竖向中心(度): 接 WorldSurroundPanorama 的 v_center。"),
            ],
            outputs=[
                io.Image.Output(display_name="images"),
                io.Custom("EXTRINSICS").Output(display_name="extrinsics"),
                io.Custom("INTRINSICS").Output(display_name="intrinsics"),
                io.Int.Output(display_name="num_horizontal"),
                io.Int.Output(display_name="num_vertical"),
            ],
        )

    @classmethod
    def execute(cls, panorama, fov_degrees=80.0, overlap_percent=10.0, output_size=952,
                v_range=150.0, v_center=0.0) -> io.NodeOutput:
        """长图 → 视角批 + 位姿 (纯旋转, 相机在球心)。

        参数:
            panorama (IMAGE): 横向长图 [1,H,W,3]; 宽高比 0.5 时为整张等距圆柱(竖向 180°)。
            fov_degrees (float): 每个透视视角的视场角。
            overlap_percent (float): 相邻视角重叠比例。
            output_size (int): 方视角边长。
            v_range (float): 长图竖向跨度 (度)。
            v_center (float): 长图竖向中心 (度)。

        返回:
            io.NodeOutput: (images[N,S,S,3], extrinsics[N,4,4] w2c, intrinsics[3,3],
                            num_h, num_v); 长图为空时 images/extrinsics/intrinsics 全 None。
        """
        if panorama is None:
            logger.warning("[WorldPanoramaViews] 长图为空, 输出空")
            return io.NodeOutput(None, None, None, 0, 0)

        pano = panorama[0] if panorama.dim() == 4 else panorama
        h, w, _ = pano.shape
        if v_range <= 0:
            v_range = 180.0
        if abs(w / h - 2.0) < 0.06 and v_range < 175.0:
            logger.warning("[WorldPanoramaViews] 长图看起来是整张 2:1 等距圆柱(竖向 180°), "
                           "但 v_range=%.0f° —— 记得把 WorldSurroundPanorama 的 valid_band "
                           "接到本节点 v_range", v_range)
        if abs(v_center) + v_range / 2 > 90.5:
            logger.warning("[WorldPanoramaViews] v_center±v_range/2 超出 ±90°, 视角边缘会被拉伸")

        step = math.radians(fov_degrees) * (1.0 - overlap_percent / 100.0)
        num_h = max(1, math.ceil(2 * math.pi / step))
        # 竖向档数: 一个视角的竖直 FOV 就能盖住整条带时只切一行 —— 旋转视频的 valid_band
        # 就是这么来的(实测 72°), 若按 ceil(v_range/step) 会切出 2 行、每行一半是黑边,
        # 白白把 token 预算摊薄(12 视角时前馈只能到 406, 6 视图能到 500+)。
        # ⚠️ 留 8% 容差: 实测 v_range=73° 而 fov=72° 时硬比大小会翻成 2 行 ⇒ 12 视角、
        #    前馈分辨率掉到 406、PSNR 42.7→37.4dB; 超出的那 1° 用边缘复制补, 无害。
        num_v = 1 if math.radians(v_range) <= math.radians(fov_degrees) * 1.08 \
            else max(1, math.ceil(math.radians(v_range) / step))
        logger.info("[WorldPanoramaViews] FOV=%.1f° 重叠=%.1f%% 步进=%.1f° → %d×%d=%d 视角 "
                    "(v_range=%.0f°, v_center=%.0f°, 长图 %dx%d)",
                    fov_degrees, overlap_percent, math.degrees(step), num_h, num_v,
                    num_h * num_v, v_range, v_center, w, h)

        imgs, exts = [], []
        intr = None
        for j in range(num_v):
            pitch = math.radians(v_center) + (j - (num_v - 1) / 2.0) * step
            for i in range(num_h):
                yaw = -math.pi + (i + 0.5) * step
                img, ext, K = cls._sample(pano, yaw, pitch, math.radians(fov_degrees),
                                          output_size, v_center, v_range)
                imgs.append(img)
                exts.append(ext)
                intr = K if intr is None else intr
        return io.NodeOutput(torch.stack(imgs, 0), torch.stack(exts, 0), intr, num_h, num_v)

    @staticmethod
    def _sample(pano: torch.Tensor, yaw: float, pitch: float, fov_rad: float, size: int,
                v_center: float = 0.0, v_range: float = 180.0):
        """从横向长图采样一个透视视角 (外参口径与 HYWM2SamplePanorama 一致)。

        竖直朝向: 长图第 0 行 = 仰角 (v_center+v_range/2), 最后一行 = (v_center-v_range/2);
        像素 (u,v) 的视线方向 `rays_cam = (dx, dy, 1)`(y 向下), 经同款 `R = Ry(yaw)Rx(pitch)`
        旋转后取仰角 `elev = asin(-world_y)`, 于是 `eq_y = (elev_top - elev)/v_range·(H-1)`。
        (与 v1/上游的差别只有 up/down 的符号 —— 上游那套要求长图上行=地, 用真 equirect 图会
        上下颠倒; 本节点与 WorldSurroundPanorama 成对修正, 切出来的视角画面完全不变。)

        返回 (image[H,W,3], extrinsics_w2c[4,4], intrinsics[3,3])。
        """
        pano = pano.permute(2, 0, 1).unsqueeze(0)
        h, w = pano.shape[-2:]
        dev = pano.device
        f_px = (size / 2.0) / math.tan(fov_rad / 2.0)
        cx = cy = (size - 1) / 2.0

        u = torch.arange(size, dtype=torch.float32, device=dev)
        uu, vv = torch.meshgrid(u, u, indexing="xy")
        dx = (uu - cx) / f_px
        dy = (vv - cy) / f_px
        rays_cam = F.normalize(torch.stack([dx, dy, torch.ones_like(dx)], dim=-1), dim=-1)

        cy_, sy_ = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        R = torch.tensor([[cy_, 0, sy_], [0, 1, 0], [-sy_, 0, cy_]], dtype=torch.float32, device=dev) \
            @ torch.tensor([[1, 0, 0], [0, cp, -sp], [0, sp, cp]], dtype=torch.float32, device=dev)
        rays_world = torch.einsum("ij,hwj->hwi", R, rays_cam)

        rx, ry, rz = rays_world[..., 0], rays_world[..., 1], rays_world[..., 2]
        elev_top = math.radians(v_center) + math.radians(v_range) / 2.0
        eq_x = (torch.atan2(rx, rz) / math.pi + 1.0) * (w - 1) / 2.0
        elev = torch.asin(torch.clamp(-ry, -1, 1))          # 抬头为正 ⇒ 上行=天
        eq_y = (elev_top - elev) / math.radians(v_range) * (h - 1)
        grid = torch.stack([eq_x / (w - 1) * 2 - 1, eq_y / (h - 1) * 2 - 1], dim=-1).unsqueeze(0)
        sampled = F.grid_sample(pano, grid, mode="bilinear",
                                padding_mode="border", align_corners=True)
        image = sampled[0].permute(1, 2, 0)

        K = torch.tensor([[f_px, 0, cx], [0, f_px, cy], [0, 0, 1]],
                         dtype=torch.float32, device=dev)
        ext = torch.eye(4, dtype=torch.float32, device=dev)
        ext[:3, :3] = R.T
        return image, ext, K


NODE_CLASS_MAPPINGS = {
    "WorldSurroundPanorama": FallingTSWorldSurroundPanoramaNode,
    "WorldPanoramaViews": FallingTSWorldPanoramaViewsNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WorldSurroundPanorama": "FallingTS 360°视频 → 横向展开长图",
    "WorldPanoramaViews": "FallingTS 全景 → 视角批 + 位姿",
}
