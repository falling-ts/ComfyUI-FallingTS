"""对拍: 自研 WorldPanoramaViews 的切图/位姿 与 上游 HYWM2SamplePanorama 是否完全一致。

口径必须逐像素一致, 否则下游 WorldRefinePLY 拿到的位姿就是错的。
做法: 直接按文件路径加载上游 `sample_panorama.py`(不经 `nodes.` 包名, 避免与 ComfyUI 自己的
`nodes.py` 撞名), 用同一张假全景、同一组 (yaw, pitch) 调两边的**单视角采样原语**比对。

用法: python custom_nodes/ComfyUI-FallingTS/dev/_verify-panorama-views.py
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import importlib.util
import math
import sys

import numpy as np
import torch

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS"))
sys.path.append(str(_COMFY / "ComfyUI"))          # comfy_api 是 ComfyUI 根下的顶层包

UPSTREAM = str(_COMFY / "custom_nodes" / "ComfyUI-HYWM2" / "nodes" / "sample_panorama.py")


def load_upstream():
    spec = importlib.util.spec_from_file_location("hywm2_sample_panorama_ref", UPSTREAM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ref = load_upstream()
    from importlib import import_module
    mine = import_module("world-panorama.nodes")          # 目录名含连字符, 按名加载

    torch.manual_seed(0)
    H, W = 256, 512
    yy = torch.linspace(0, 1, H).view(H, 1).expand(H, W)
    xx = torch.linspace(0, 1, W).view(1, W).expand(H, W)
    pano = torch.stack([xx, yy, (xx * yy) ** 0.5], dim=-1).unsqueeze(0)   # [1,H,W,3]

    worst = {"img": 0.0, "ext": 0.0, "intr": 0.0}
    for fov, size in ((80.0, 256), (65.0, 238)):
        for yaw_d, pitch_d in ((0, 0), (37, 22), (-125, -40), (180, 75), (13.7, 58)):
            yaw, pitch = math.radians(yaw_d), math.radians(pitch_d)
            a_img, a_ext, a_int = mine.FallingTSWorldPanoramaViewsNode._sample(
                pano[0], yaw, pitch, math.radians(fov), size)
            b_img, b_ext, b_int = ref._sample_perspective_from_equirectangular(
                pano[0], yaw, pitch, math.radians(fov), size)
            di = float((a_img - b_img).abs().max())
            de = float((a_ext - b_ext).abs().max())
            dk = float((a_int - b_int).abs().max())
            worst["img"] = max(worst["img"], di)
            worst["ext"] = max(worst["ext"], de)
            worst["intr"] = max(worst["intr"], dk)
            print(f"fov={fov:5.1f} size={size} yaw={yaw_d:6.1f} pitch={pitch_d:5.1f}  "
                  f"图像最大差={di:.3e}  外参最大差={de:.3e}  内参最大差={dk:.3e}")

    ok = worst["img"] < 1e-5 and worst["ext"] < 1e-6 and worst["intr"] < 1e-6
    print(f"\n最坏差: 图像 {worst['img']:.3e} / 外参 {worst['ext']:.3e} / 内参 {worst['intr']:.3e}")
    print("结论:", "与上游完全一致 ✔" if ok else "**不一致 ✘**")

    # 顺带核对网格口径 (v_range 与上游 skip_poles 的 150° 同量级)
    img = pano[0]
    out = mine.FallingTSWorldPanoramaViewsNode.execute(
        pano, fov_degrees=80.0, overlap_percent=10.0, output_size=224,
        v_range=70.0, v_center=0.0)
    images, extr, intr2, nh, nv = out
    print(f"\n网格自检: v_range=70 fov=80 → {nh}×{nv} = {images.shape[0]} 视角, "
          f"图像 {tuple(images.shape)}, 外参 {tuple(extr.shape)}, 内参 {tuple(intr2.shape)}")
    print("外参正交性 |RᵀR-I| =",
          float((extr[:, :3, :3].transpose(1, 2) @ extr[:, :3, :3]
                 - torch.eye(3)).abs().max()))
    print("相机平移 |t| 最大值 =", float(extr[:, :3, 3].abs().max()), "(纯旋转 ⇒ 应为 0)")
    # 各视角光轴方向 (R@(0,0,1) 的逆 = 世界朝向) 的俯仰角
    for i in range(images.shape[0]):
        R = extr[i, :3, :3]
        fwd = R.T @ torch.tensor([0.0, 0.0, 1.0])
        print(f"  view{i}: yaw={math.degrees(math.atan2(float(fwd[0]), float(fwd[2]))):7.2f}° "
              f"pitch={math.degrees(math.asin(float(fwd[1]))):7.2f}°")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())