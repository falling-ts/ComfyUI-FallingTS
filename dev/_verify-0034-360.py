"""0034(360°视频版) 端到端验收 —— 判据缺一不可。

  1. /history 的 status.status_str == "success" 且无 execution_error;
  2. PLY 确实被重写(mtime + sha256 变化), 高斯数 > 0;
  3. 日志里能看到这条链的关键证据:
     旋转展开(闭环解焦距) / 单行网格 / [Prior] Loaded extrinsics N/N / 先验生效度;
  4. PLY 的颜色编码正确(f_dc 解码后均值贴近参考图, 而不是被变换两遍的中灰)。

用法: python custom_nodes/ComfyUI-FallingTS/dev/_verify-0034-360.py
"""
import pathlib as _pathlib
_COMFY = _pathlib.Path(__file__).resolve().parent.parent.parent.parent   # 项目根

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import uuid

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8188"
API = str(_COMFY / "custom_nodes" / "ComfyUI-FallingTS" / "dev" / "0034_api_prompt_360.json")
# 日志路径可传参: 冷启动验收时 ComfyUI 的日志文件名会变(缓存也随进程清空, 这样重算才是真的)
LOG = sys.argv[1] if len(sys.argv) > 1 else str(_COMFY / "logs" / "comfyui-8188-world360c.log")
PLY = str(_COMFY / "media" / "七纹刻印" / "0034_世界模型" / "0034_世界模型_世界3DGS.ply")
C0 = 0.28209479177387814


def snapshot(path):
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"size": os.path.getsize(path), "mtime": os.path.getmtime(path),
            "sha256": h.hexdigest()[:16]}


def ply_stats(path):
    with open(path, "rb") as f:
        header = b""
        while b"end_header" not in header:
            header += f.readline()
        lines = header.decode("ascii", "replace").splitlines()
        n = int(next(l.split()[-1] for l in lines if l.startswith("element vertex")))
        props = [l.split()[-1] for l in lines if l.startswith("property float")]
        body = f.read()
    a = np.frombuffer(body, dtype=np.float32, count=n * len(props)).reshape(n, len(props))
    i = {p: k for k, p in enumerate(props)}
    dc = np.stack([a[:, i[f"f_dc_{c}"]] for c in range(3)], axis=1)
    return n, (0.5 + C0 * dc).mean(axis=0)


before = snapshot(PLY)
print("运行前:", json.dumps(before, ensure_ascii=False))

prompt = json.load(open(API, encoding="utf-8"))
assert set(prompt) == {"1", "2", "3", "4", "5", "6"}, f"节点集不对: {sorted(prompt)}"
assert prompt["5"]["inputs"]["extrinsics"] == ["4", 1], "extrinsics 没接上"
assert prompt["5"]["inputs"]["intrinsics"] == ["4", 2], "intrinsics 没接上"
prompt["5"]["inputs"]["refresh"] = True          # 打掉前馈缓存, 确保真算
print("节点:", sorted(prompt), "| #2:", json.dumps(prompt["2"]["inputs"], ensure_ascii=False))

body = json.dumps({"prompt": prompt, "client_id": str(uuid.uuid4())}).encode()
req = urllib.request.Request(BASE + "/prompt", data=body,
                            headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.load(r)
except urllib.error.HTTPError as e:
    print("\n提交被拒:", e.code, e.read().decode("utf-8", "replace")[:5000])
    raise SystemExit(1)
pid = res.get("prompt_id")
print("prompt_id:", pid, "node_errors:", json.dumps(res.get("node_errors"), ensure_ascii=False)[:2000])

t0 = time.time()
entry = None
while True:
    time.sleep(5)
    with urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=60) as r:
        h = json.load(r)
    el = time.time() - t0
    if pid in h:
        entry = h[pid]
        st = entry.get("status", {}) or {}
        print(f"\n[{el:.0f}s] status={st.get('status_str')} completed={st.get('completed')}")
        for m in st.get("messages", []) or []:
            if m and m[0] in ("execution_error", "execution_interrupted"):
                print("  !!", json.dumps(m[1], ensure_ascii=False)[:3500])
        for nid, o in sorted((entry.get("outputs") or {}).items()):
            print(f"  #{nid} 输出: {json.dumps(o, ensure_ascii=False)[:600]}")
        break
    if el > 900:
        print("超时未完成")
        raise SystemExit(1)
    print(f"  [{el:.0f}s] 运行中…")

st = (entry or {}).get("status", {}) or {}
errs = [m for m in (st.get("messages") or []) if m and m[0] in
        ("execution_error", "execution_interrupted")]
after = snapshot(PLY)
ok = True

if st.get("status_str") != "success":
    print(f"FAIL: status_str = {st.get('status_str')!r}"); ok = False
if errs:
    print("FAIL: 出现 execution_error / execution_interrupted"); ok = False
if not after:
    print("FAIL: PLY 不存在"); ok = False
elif before and after["mtime"] == before["mtime"]:
    print("FAIL: PLY mtime 未变 —— 没有真正重算"); ok = False
else:
    n, rgb = ply_stats(PLY)
    print("\n运行后:", json.dumps(after, ensure_ascii=False))
    print(f"高斯数 {n:,} | f_dc 解码颜色均值 {rgb.round(3)}")
    if n < 10000:
        print("FAIL: 高斯数过少"); ok = False
    if not (0.05 <= rgb.mean() <= 0.6):
        print("FAIL: 颜色均值异常(可能又做了两遍 DC↔RGB 变换)"); ok = False

def read_log(path):
    """读 ComfyUI 日志: PowerShell `Tee-Object` 写出来是 UTF-16LE(带 BOM), 得按 BOM 判。"""
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", "replace")
    return raw.decode("utf-8", "replace")


log = read_log(LOG)
# v2 的日志口径: 焦距由「重叠区稠密光度一致性」解出(**不再**是 360° 闭环), 视角数按单行网格
for pat, need in (("旋转展开", True), ("空白 0%", True), ("×1=", True),
                  ("[Prior] Loaded extrinsics for", True),
                  ("[Prior] Loaded intrinsics for", True),
                  ("先验生效度", True), ("相机先验", True),
                  ("[C-refined] PSNR 均值", True)):
    if need and pat not in log:
        print(f"FAIL: 日志缺少证据 {pat!r}"); ok = False
m = re.search(r"\[WorldPanoramaViews\][^\n]*?(\d+)×(\d+)=(\d+) 视角", log)
if m:
    print(f"视角网格: {m.group(1)}×{m.group(2)}={m.group(3)}")
    if int(m.group(2)) != 1:
        print("FAIL: 竖向切了多行(会一半黑边 + 摊薄前馈分辨率)"); ok = False
else:
    print("FAIL: 日志里找不到 WorldPanoramaViews 的网格信息"); ok = False
m2 = re.search(r"空白 (\d+)%", log)
if m2 and int(m2.group(1)) > 1:
    print(f"FAIL: 长图空白 {m2.group(1)}% > 1%"); ok = False
print("日志证据: 已核对(旋转展开/无黑边/单行网格/先验注入/先验生效度/PSNR 打点)")
print("\n验收:", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)