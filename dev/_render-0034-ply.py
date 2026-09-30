"""产物真读: 用核心 Load3D → File3DToSplat → RenderSplat 把 PLY 渲成 PNG, 供 read_image 判读。

⚠️ 用**中性**渲染参数(splat_scale=1.0 / sharpen=1.0), 不用 1.6/4.0 那种放大纹理的激进设置 ——
那种会把高斯糊成的洞放大成"画质差"的假象。

用法: python custom_nodes\\ComfyUI-FallingTS\\dev\\_render-0034-ply.py            # 渲正式的母版与精修版各一张
      python custom_nodes\\ComfyUI-FallingTS\\dev\\_render-0034-ply.py <相对路径>  # 渲指定文件
产物: scripts\\_out-0034-render\\<tag>.png
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import json, os, shutil, sys, time, urllib.request, uuid

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8188"
TEMP = str(_COMFY / "ComfyUI" / "temp")
OUT = str(_COMFY / "scripts" / "_out-0034-render")
# ⚠️ Load3D.image 是 LOAD_3D 控件, API 里必须传 **dict**(不是路径字符串), 否则
#    node 内 `image['image']` 会报 TypeError: string indices must be integers
REF = {"image": "3d/_ref.png", "mask": "3d/_ref_mask.png",
       "normal": "3d/_ref_normal.png", "camera_info": {}, "recording": ""}
ASSETS = ["0034_世界模型/0034_世界模型_世界3DGS.ply",
          "0034_世界模型/0034_世界模型_世界3DGS_精修.ply"]
targets = sys.argv[1:] or ASSETS
os.makedirs(OUT, exist_ok=True)

for model in targets:
    tag = os.path.splitext(os.path.basename(model))[0]
    prompt = {
        "1": {"class_type": "Load3D", "inputs": {
            "model_file": model, "image": REF, "width": 768, "height": 768}},
        "2": {"class_type": "File3DToSplat", "inputs": {"model_3d": ["1", 6]}},
        "3": {"class_type": "RenderSplat", "inputs": {
            "splat": ["2", 0], "width": 768, "height": 768, "frames": 1,
            "splat_scale": 1.0, "sharpen": 1.0, "headlight_shading": 0.6,
            "opacity_threshold": 0.05, "render_style": "color", "background": "#202020"}},
        "4": {"class_type": "PreviewImage", "inputs": {"images": ["3", 0]}},
    }
    body = json.dumps({"prompt": prompt, "client_id": str(uuid.uuid4())}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + "/prompt", data=body, headers={"Content-Type": "application/json"}), timeout=120) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"{tag}: 提交被拒 {e.code} {e.read().decode('utf-8', 'replace')[:1500]}")
        continue
    pid = res.get("prompt_id")
    t0 = time.time()
    while True:
        time.sleep(3)
        with urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=60) as r:
            h = json.load(r)
        if pid in h:
            break
    e = h[pid]
    st = (e.get("status") or {}).get("status_str")
    imgs = (e.get("outputs") or {}).get("4", {}).get("images") or []
    print(f"{tag}: {st} ({time.time() - t0:.0f}s) -> {imgs}")
    for im in imgs:
        src = os.path.join(TEMP, im["filename"])
        if os.path.isfile(src):
            dst = os.path.join(OUT, f"{tag}.png")
            shutil.copyfile(src, dst)
            print(f"   {dst}  {os.path.getsize(dst):,} B")
