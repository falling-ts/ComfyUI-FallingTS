"""画质探针: 只导出 3DGS 之后, 深度/法线/点云三个 head 的结果没人用, 却仍要占显存。

本脚本提交一个**变体**(关掉这三个 head), 对照检查 WorldMirror 内部按空闲显存
自适应的有效分辨率(`[Inference] ... shape=[1,8,3,H,W]`)是否因此抬高 ——
若抬高, 说明这是不花钱的画质杠杆, 应固化进生成器。

变体输出写到 `..._probe_heads.ply`(不覆盖正式产物), 跑完自行删除。

用法: python custom_nodes\\ComfyUI-FallingTS\\dev\\_probe-0034-heads.py
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import json, os, sys, time, urllib.request, uuid

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8188"
API = str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "dev" / "0034_api_prompt.json")
LOG = str(_COMFY / "ComfyUI" / "user" / "comfyui_8188.log")
PROBE_NAME = "0034_世界模型_世界3DGS_probe_heads"
ASSET_DIR = str(_COMFY / "media" / "七纹刻印" / "0034_世界模型")


def log_tail():
    if not os.path.isfile(LOG):
        return []
    return [ln.rstrip("\n") for ln in open(LOG, encoding="utf-8", errors="replace")
            if "Inference" in ln or "Export" in ln]


prompt = json.load(open(API, encoding="utf-8"))
# 关掉本图用不到的三个 head(相机与高斯保留)
for k in ("predict_depth", "predict_normals", "predict_points"):
    prompt["2"]["inputs"][k] = False
prompt["6"]["inputs"]["filename"] = PROBE_NAME
print("变体: predict_depth/normals/points = False")
print("  LoadHYWM2Model:", json.dumps(prompt["2"]["inputs"], ensure_ascii=False))
print("  导出文件名:", prompt["6"]["inputs"]["filename"])

before = log_tail()
t0 = time.time()
body = json.dumps({"prompt": prompt, "client_id": str(uuid.uuid4())}).encode()
try:
    with urllib.request.urlopen(urllib.request.Request(
            BASE + "/prompt", data=body, headers={"Content-Type": "application/json"}), timeout=120) as r:
        res = json.load(r)
except urllib.error.HTTPError as e:
    print("提交被拒:", e.code, e.read().decode("utf-8", "replace")[:4000])
    sys.exit(1)
pid = res.get("prompt_id")
print("prompt_id:", pid, "node_errors:", json.dumps(res.get("node_errors"), ensure_ascii=False)[:1500])
while True:
    time.sleep(3)
    with urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=60) as r:
        h = json.load(r)
    if pid in h:
        st = h[pid].get("status", {}) or {}
        print(f"[{time.time() - t0:.0f}s] status={st.get('status_str')} completed={st.get('completed')}")
        break

print("\n--- 本次新增日志 ---")
new = log_tail()[len(before):]
for ln in new:
    print("  " + ln.strip())

out = os.path.join(ASSET_DIR, PROBE_NAME + ".ply")
if os.path.isfile(out):
    sz = os.path.getsize(out)
    # 68 B/顶点 + header: 反推过滤后的高斯数
    print(f"\n探针产物: {out}  {sz:,} B  ≈ {sz // 68:,} 高斯")
    os.remove(out)
    print("(已删除探针产物)")
else:
    print("\n没用探针产物生成(可能失败)")
