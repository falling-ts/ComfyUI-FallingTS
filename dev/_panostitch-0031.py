"""有界实测: 把 0031 的 360° 旋镜视频缝成「球面四周展开的长图」(圆柱/球面全景)。

做法: ffmpeg 等间隔抽 N 帧 → OpenCV Stitcher(球面 + 圆柱两种 warper) 拼图。
产物落 scripts\\_out-pano\\ (临时目录, 不是 media 真实数据)。
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import glob
import os
import subprocess
import sys

import cv2
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
VID = str(_COMFY / "media" / "七纹刻印" / "0031_首帧场景" / "00001_书房旋镜视频.mp4")
OUT = str(_COMFY / "scripts" / "_out-pano")
FR = os.path.join(OUT, "frames")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
ONLY = sys.argv[2] if len(sys.argv) > 2 else ""   # 只跑指定 warper, 空=全跑


def probe():
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate,nb_frames,duration",
                        "-of", "default=nw=1", VID], capture_output=True, text=True)
    print("=== 视频 ===")
    print(r.stdout.strip())


def extract():
    os.makedirs(FR, exist_ok=True)
    for f in glob.glob(os.path.join(FR, "*.png")):
        os.remove(f)
    # fps = N / 时长 → 等间隔抽 N 帧
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", VID], capture_output=True, text=True)
    dur = float(r.stdout.strip())
    fps = N / dur
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", VID, "-vf", f"fps={fps:.6f}", "-frames:v", str(N),
           os.path.join(FR, "%02d.png")]
    subprocess.run(cmd, check=True)
    fs = sorted(glob.glob(os.path.join(FR, "*.png")))
    print(f"时长 {dur:.2f}s → 抽帧 fps={fps:.3f}, 实得 {len(fs)} 帧, 尺寸 {cv2.imread(fs[0]).shape[1]}x{cv2.imread(fs[0]).shape[0]}")
    return fs


def stitch(fs, warper_name, tag):
    import time
    t0 = time.time()
    st = cv2.Stitcher.create(cv2.Stitcher_PANORAMA)
    if warper_name:
        st.setWarper(cv2.PyRotationWarper(warper_name, 1.0))
    try:
        st.setPanoConfidenceThresh(0.5)      # 默认值; 置 0 会让匹配图爆炸(实测 36 帧跑 900s+ CPU)
        st.setRegistrationResol(0.6)
        st.setSeamEstimationResol(0.1)
        st.setCompositingResol(cv2.Stitcher_ORIG_RESOL)
    except Exception as e:
        print("  调参失败(不影响):", e)
    imgs = [cv2.imread(p) for p in fs]
    status, pano = st.stitch(imgs)
    names = {0: "OK", 1: "ERR_NEED_MORE_IMGS", 2: "ERR_HOMOGRAPHY_EST_FAIL", 3: "ERR_CAMERA_PARAMS_ADJUST_FAIL"}
    print(f"  warper={warper_name or 'default(spherical)'}: status={status} {names.get(status, '?')} 用时 {time.time()-t0:.0f}s", end="")
    if pano is not None and pano.size:
        p = os.path.join(OUT, f"pano-{tag}.png")
        cv2.imwrite(p, pano)
        h, w = pano.shape[:2]
        print(f" → {w}x{h} 宽高比 {w/h:.2f}  已存 {os.path.basename(p)}")
    else:
        print(" → 无输出")


probe()
frames = extract()
os.makedirs(OUT, exist_ok=True)
print("=== 拼接 ===")
for warper, tag in ((None, "spherical"), ("cylindrical", "cylindrical"), ("equirectangular", "equirect")):
    if ONLY and ONLY not in tag:
        continue
    try:
        stitch(frames, warper, tag)
    except Exception as e:
        print(f"  warper={warper}: 异常 {type(e).__name__}: {e}")
