# -*- coding: utf-8 -*-
"""验收: FallingTSLoadAudio(后端) —— 注册/路由/执行。

前提: 临时实例跑在 8189(读的是同一份插件代码)。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8189"
FAILURES = []


def check(label, ok, detail=None):
    print(("PASS" if ok else "FAIL") + ": " + label, "" if detail is None else str(detail)[:300])
    if not ok:
        FAILURES.append(label)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode())


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode()[:600]}


# 等实例就绪
info = None
for _ in range(200):
    try:
        info = get("/object_info/FallingTSLoadAudio")
        if info:
            break
    except Exception:
        time.sleep(3)
if not info:
    print("FAIL: 8189 未就绪或节点未注册")
    sys.exit(1)

node = info.get("FallingTSLoadAudio") or {}
check("节点已注册", bool(node), list(info.keys()))
check("输入顺序 = name/sequence/audio(+optional audioUI)",
      node.get("input_order", {}).get("required") == ["name", "sequence", "audio"]
      and node.get("input_order", {}).get("optional") == ["audioUI"],
      node.get("input_order"))
ui = (node.get("input") or {}).get("optional", {}).get("audioUI")
check("声明了 audioUI(AUDIO_UI) 播放器输入(optional)", isinstance(ui, list) and ui[0] == "AUDIO_UI", ui)
check("输出 = audio", node.get("output_name") == ["audio"], node.get("output_name"))
combo = (node.get("input") or {}).get("required", {}).get("audio")
check("audio 是 COMBO 且带上传/远端", isinstance(combo, list) and isinstance(combo[1], dict)
      and combo[1].get("audio_upload") is True and (combo[1].get("remote") or {}).get("route") == "/fallingts_load_audio/files",
      combo[1] if isinstance(combo, list) and len(combo) > 1 else combo)

# 路由: 候选列表(含数字目录内部 + output 根)
files = get("/fallingts_load_audio/files")
check("候选含数字目录内部音频", "0060_背景音乐/_probe_tmp_audio.mp3" in files, files[:6])
check("候选含 output 根音频", "_probe_root_audio.wav" in files, files[:6])

# 路由: 序列号
seq = get("/fallingts_load_audio/next_sequence?workflow_name=" + urllib.parse.quote("0060_背景音乐"))
check("序列号路由可用", seq.get("status") == "ok" and "sequence" in seq, seq)

# 路由: 可播放 URL
# execute 会发 UI.PreviewAudio: history 里该节点应有 audio 输出

# 执行: 加载音频 → PreviewAudioSave(用它读出 AUDIO 是否真有值)
prompt = {
    "1": {"class_type": "FallingTSLoadAudio",
          "inputs": {"audio": "0060_背景音乐/_probe_tmp_audio.mp3", "name": "探针", "sequence": "00000"}},
    "2": {"class_type": "PreviewAudioSave",
          "inputs": {"audio": ["1", 0], "filename_prefix": "probe", "filename_suffix": "",
                     "format": "flac", "quality": "128k"}},
}
res = post("/prompt", {"prompt": prompt, "client_id": "verify-load-audio"})
pid = res.get("prompt_id")
check("提交执行", bool(pid), res)
if pid:
    hist = None
    for _ in range(60):
        time.sleep(2)
        h = get("/history/" + pid)
        if pid in h:
            hist = h[pid]
            break
    status = (hist or {}).get("status", {}).get("status_str")
    outs = (hist or {}).get("outputs") or {}
    check("执行成功且下游拿到音频", status == "success" and bool(outs.get("2", {}).get("audio")),
          {"status": status, "node2": outs.get("2")})
    check("本节点发 UI.PreviewAudio(节点内播放器用)", bool(outs.get("1", {}).get("audio")),
          outs.get("1"))

print()
print("FAILURES: " + (", ".join(FAILURES) if FAILURES else "无"))
sys.exit(1 if FAILURES else 0)
