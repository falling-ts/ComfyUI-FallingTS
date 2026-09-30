"""四方差: 图内母版 / 脚本基线504 / 脚本精修504 / 504+尺度过滤 —— 同一相机严格对比。

必须在隔离环境(hywm2-nodes)里跑, cwd = 插件目录。

动机: 图内 `save_gs_ply` 会按最大尺度 98% 分位砍掉最大的 2%; 母版(eff406)被砍后 scale_max=0.0098,
而脚本那条 eff504 路径 scale_max=0.3008 —— 差 30 倍的巨型雾团还在。本脚本量化这件事:
"远机位更雾"到底是【精修】造成的, 还是【分辨率上去了但没做尺度过滤】造成的。

远机位用标准 look-at 搭(COLMAP/OpenCV 约定: x 右 / y 下 / z 朝前), 先把 A 渲出来确认看得见场景。
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import os, sys
import numpy as np
import torch

PLUGIN = str(_COMFY / "custom_nodes" / "ComfyUI-HYWM2")
COMFYUI = str(_COMFY / "ComfyUI")
if COMFYUI not in sys.path:
    sys.path.append(COMFYUI)
if PLUGIN not in sys.path:
    sys.path.insert(0, PLUGIN)

C0 = 0.28209479177387814
CACHE = str(_COMFY / "scripts" / "_cache-0034-preds.pt")
OUTDIR = str(_COMFY / "scripts" / "_out-0034-refine")
PLY_A = str(_COMFY / "media" / "七纹刻印" / "0034_世界模型" / "0034_世界模型_世界3DGS.ply")
PLY_B = os.path.join(OUTDIR, "baseline_eff504.ply")
PLY_C = str(_COMFY / "media" / "七纹刻印" / "0034_世界模型" / "0034_世界模型_世界3DGS_精修.ply")
SCALE = 2

sys.stdout.reconfigure(encoding="utf-8")
dev = torch.device("cuda")
from gsplat import rasterization  # noqa: E402


def load_ply(path):
    from plyfile import PlyData
    v = PlyData.read(path)["vertex"].data
    g = lambda *ks: np.stack([np.asarray(v[k], dtype=np.float32) for k in ks], axis=1)  # noqa: E731
    means = torch.from_numpy(g("x", "y", "z")).to(dev)
    scales = torch.from_numpy(np.exp(g("scale_0", "scale_1", "scale_2"))).to(dev)
    quats = torch.from_numpy(g("rot_0", "rot_1", "rot_2", "rot_3")).to(dev)
    quats = quats / quats.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    opac = torch.sigmoid(torch.from_numpy(np.asarray(v["opacity"], dtype=np.float32)).to(dev))
    rgb = (torch.from_numpy(g("f_dc_0", "f_dc_1", "f_dc_2")).to(dev) * C0 + 0.5).clamp(0, 1)
    return means, quats, scales, opac, rgb


def scale_filter(m, q, s, o, rgb, qth=0.98):
    """复刻 save_gs_ply 的尺度过滤(最大尺度 qth 分位以上砍掉)。"""
    thr = torch.quantile(s.max(dim=-1)[0], qth, dim=0)
    keep = s.max(dim=-1)[0] <= thr
    return m[keep], q[keep], s[keep], o[keep], rgb[keep], int(keep.sum()), int((~keep).sum())


cache = torch.load(CACHE, weights_only=False)
c2w = cache["camera_poses"][0].to(dev)
Ks = cache["camera_intrs"][0].to(dev)
_, _, _, H0, W0 = cache["imgs"].shape
W, H = W0 * SCALE, H0 * SCALE
Ks = Ks.clone() * SCALE
Ks[:, 2, 2] = 1.0

# ---- 远机位: 标准 look-at (COLMAP 约定: x 右 / y 下 / z 朝前) ----
allm = cache["splats"]["means"].reshape(-1, 3).to(dev)
lo, hi = allm.min(0).values, allm.max(0).values
ctr = (lo + hi) / 2
r = float((hi - lo).norm() / 2)
eye = ctr + torch.tensor([1.0, 0.55, 1.0], device=dev) * (2.2 * r)
z = (ctr - eye)
z = z / z.norm()
up = torch.tensor([0.0, 1.0, 0.0], device=dev)
x = torch.cross(up, z, dim=0)
x = x / x.norm()
y = torch.cross(z, x, dim=0)
far = torch.eye(4, device=dev)
far[:3, 0], far[:3, 1], far[:3, 2], far[:3, 3] = x, y, z, eye
print(f"包围盒 center={ctr.cpu().numpy().round(3)} 半径 r={r:.3f}  远机位 eye={eye.cpu().numpy().round(3)}")


def shoot(m, q, s, o, rgb, vm):
    with torch.no_grad():
        out = rasterization(m, q, s, o, rgb, vm, Ks[0][None], W, H, sh_degree=None,
                            render_mode="RGB")
    img, alpha = out[0], out[1]
    if isinstance(img, list):
        img, alpha = img[0], alpha[0]
    if img.dim() == 4:
        img, alpha = img[0], alpha[0]
    if alpha.dim() == 3:
        alpha = alpha[..., 0]
    return img, alpha


def to_uint8(t):
    return (t.detach().float().cpu().clamp(0, 1).numpy() * 255.0 + 0.5).astype(np.uint8)


views = [("训练机位0", torch.linalg.inv(c2w[0])[None]), ("远机位(look-at)", torch.linalg.inv(far)[None])]

sets = [
    ("A 图内母版 eff406(已过滤)", PLY_A),
    ("B 脚本基线 eff504(已过滤)", PLY_B),
    ("C 旧精修 eff504(未过滤,反面教材)",
     str(_COMFY / "backups" / "backup-0034-旧未过滤精修-20260927" / "0034_世界模型_世界3DGS_精修-未过滤版.ply")),
    ("E 精修 eff504(已过滤+加固)", PLY_C),
]

rows, report = [], []
for tag, path in sets:
    if not os.path.isfile(path):
        report.append(f"{tag}: 缺文件 {os.path.basename(path)}")
        continue
    m, q, s, o, rgb = load_ply(path)
    report.append(f"{tag}: 高斯 {m.shape[0]:,}  scale_max={float(s.max()):.4f}  "
                  f"opac_med={float(o.median()):.4f}")
    rows.append([to_uint8(shoot(m, q, s, o, rgb, vm)[0]) for _, vm in views])
    del m, q, s, o, rgb
    torch.cuda.empty_cache()

print("\n".join(report))
from PIL import Image  # noqa: E402
arr = np.concatenate([np.concatenate(r, axis=1) for r in rows], axis=0)
p = os.path.join(OUTDIR, "four_way.png")
Image.fromarray(arr).save(p)
print(f"\n-> {p}")
print("   行序: " + " | ".join(t for t, _ in sets)[:200])
print("   列序: " + " | ".join(t for t, _ in views))
