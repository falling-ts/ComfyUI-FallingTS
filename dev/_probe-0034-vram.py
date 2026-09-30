"""画质探针 2: WorldMirror 的有效分辨率是不是按"当时空闲显存"自适应?

若是, 那么"先 /free 卸载其它模型腾出显存再跑 0034"就是一条不花钱的画质杠杆
(PLY 更清晰), 该写进工作流说明。

做法: 同一份 canonical prompt 跑两次 —— A 直接跑, B 先 POST /free {"unload_models":true}
卸干净再跑; 对照 `[Inference] ... shape=[1,8,3,H,W]` 与产物高斯数。
两次都用探针文件名, 不覆盖正式产物。

用法: python custom_nodes\\ComfyUI-FallingTS\\dev\\_probe-0034-vram.py
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import json, os, subprocess, sys, time, urllib.request, uuid

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8188"
API = str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "dev" / "0034_api_prompt.json")
LOG = str(_COMFY / "ComfyUI" / "user" / "comfyui_8188.log")
PROBE_NAME = "0034_世界模型_世界3DGS_probe_vram"
ASSET_DIR = str(_COMFY / "media" / "七纹刻印" / "0034_世界模型")


def gpu_free_mib():
    """nvidia-smi 报的显存空闲量(MiB)。"""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True,
                             timeout=20).stdout.strip()
        used, total = (int(v) for v in out.split(","))
        return total - used, used, total
    except Exception as e:      # noqa: BLE001
        return None, None, str(e)


def log_shape_lines():
    if not os.path.isfile(LOG):
        return []
    return [ln.rstrip("\n") for ln in open(LOG, encoding="utf-8", errors="replace")
            if "shape=torch.Size" in ln or "Export Gaussians PLY" in ln]


def run(tag):
    prompt = json.load(open(API, encoding="utf-8"))
    prompt["6"]["inputs"]["filename"] = PROBE_NAME
    before = len(log_shape_lines())
    free, used, total = gpu_free_mib()
    print(f"\n=== {tag} === 显存: 空闲 {free} MiB / 已用 {used} MiB (总 {total} MiB)")
    body = json.dumps({"prompt": prompt, "client_id": str(uuid.uuid4())}).encode()
    with urllib.request.urlopen(urllib.request.Request(
            BASE + "/prompt", data=body, headers={"Content-Type": "application/json"}), timeout=120) as r:
        pid = json.load(r).get("prompt_id")
    t0 = time.time()
    while True:
        time.sleep(3)
        with urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=60) as r:
            h = json.load(r)
        if pid in h:
            st = h[pid].get("status", {}) or {}
            print(f"[{time.time() - t0:.0f}s] {st.get('status_str')} completed={st.get('completed')}")
            break
    for ln in log_shape_lines()[before:]:
        print("   " + ln.strip())
    out = os.path.join(ASSET_DIR, PROBE_NAME + ".ply")
    if os.path.isfile(out):
        print(f"   产物 {os.path.getsize(out):,} B")
        os.remove(out)


print("run A: 直接跑(其它模型可能仍占显存)")
run("A 直接跑")
print("\nPOST /free {'unload_models': true, 'free_memory': true} …")
req = urllib.request.Request(BASE + "/free", data=json.dumps(
    {"unload_models": True, "free_memory": True}).encode(), headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=120) as r:
    print("  ->", r.status)
time.sleep(3)
print("run B: 卸载后再跑")
run("B 卸载后")
