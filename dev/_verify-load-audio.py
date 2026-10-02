# -*- coding: utf-8 -*-
"""验收: FallingTSLoadAudio(后端) —— 注册/路由/执行/audio_in。

自建探针音频(标准库 wave, 不用 ffmpeg), 跑完自删 —— 可反复跑。
前提: 临时实例跑在 8189(读的是同一份插件代码):
  cd ComfyUI && D:/AI/Comfy/.venv/Scripts/python.exe main.py --cpu --port 8189 --disable-pinned-memory
用法(工作区根): .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-load-audio.py
"""
from __future__ import annotations

import json
import math
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent.parent.parent
BASE = "http://127.0.0.1:8189"

# 探针: output 根一个 + 数字目录内部一个(验证两处都进候选)
PROBE_ROOT = ROOT / "media" / "七纹刻印" / "_probe_root_audio.wav"
PROBE_SUB = ROOT / "media" / "七纹刻印" / "0060_背景音乐" / "_probe_tmp_audio.wav"
SUB_VALUE = "0060_背景音乐/_probe_tmp_audio.wav"

FAILURES = []


def check(label, ok, detail=None):
    print(("PASS" if ok else "FAIL") + ": " + label, "" if detail is None else str(detail)[:300])
    if not ok:
        FAILURES.append(label)


def write_wav(path: Path, freq: float, seconds: float = 1.0) -> None:
    """写一个 16bit 单声道正弦 wav(标准库, 不依赖 ffmpeg)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 16000
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * seconds))
        )
        w.writeframes(frames)


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


def run_prompt(prompt, want_node):
    """提交并等 history, 返回 (status, 该节点的 outputs)。"""
    res = post("/prompt", {"prompt": prompt, "client_id": "verify-load-audio"})
    pid = res.get("prompt_id")
    if not pid:
        return None, None, res
    for _ in range(60):
        time.sleep(2)
        h = get("/history/" + pid)
        if pid in h:
            hist = h[pid]
            return hist.get("status", {}).get("status_str"), (hist.get("outputs") or {}).get(want_node), None
    return None, None, {"_timeout": True}


def main() -> None:
    write_wav(PROBE_ROOT, 660)
    write_wav(PROBE_SUB, 440)
    try:
        info = None
        for _ in range(80):
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
        check("输入顺序 = name/sequence/audio(+optional audioUI/audio_in)",
              node.get("input_order", {}).get("required") == ["name", "sequence", "audio"]
              and node.get("input_order", {}).get("optional") == ["audioUI", "audio_in"],
              node.get("input_order"))
        ui = (node.get("input") or {}).get("optional", {}).get("audioUI")
        check("声明了 audioUI(AUDIO_UI) 播放器输入(optional)", isinstance(ui, list) and ui[0] == "AUDIO_UI", ui)
        combo = (node.get("input") or {}).get("required", {}).get("audio")
        check("audio 是 COMBO 且带上传/远端", isinstance(combo, list) and isinstance(combo[1], dict)
              and combo[1].get("audio_upload") is True
              and (combo[1].get("remote") or {}).get("route") == "/fallingts_load_audio/files",
              combo[1] if isinstance(combo, list) and len(combo) > 1 else combo)
        check("输出 = audio + prefix(文件名前缀)",
              node.get("output_name") == ["audio", "prefix"], node.get("output_name"))

        files = get("/fallingts_load_audio/files")
        check("候选含数字目录内部音频", SUB_VALUE in files, files[:6])
        check("候选含 output 根音频", "_probe_root_audio.wav" in files, files[:6])

        seq = get("/fallingts_load_audio/next_sequence?workflow_name=" + urllib.parse.quote("0060_背景音乐"))
        check("序列号路由可用", seq.get("status") == "ok" and "sequence" in seq, seq)

        # 执行(按文件名): 加载音频 → PreviewAudioSave
        status, out1, err = run_prompt({
            "1": {"class_type": "FallingTSLoadAudio",
                  "inputs": {"audio": SUB_VALUE, "name": "探针", "sequence": "00000"}},
            "2": {"class_type": "PreviewAudioSave",
                  "inputs": {"audio": ["1", 0], "filename_prefix": "probe", "filename_suffix": "",
                             "format": "flac", "quality": "128k"}},
        }, "1")
        check("提交执行(按文件名)", status is not None or err is None, err or status)
        check("执行成功且下游拿到音频", status == "success" and bool((out1 or {}).get("audio")),
              {"status": status, "node1": out1})

        # 执行(audio_in 连线): 核心 LoadAudio → 我们的加载音频(下拉留空)
        status2, out2, err2 = run_prompt({
            "1": {"class_type": "LoadAudio", "inputs": {"audio": PROBE_ROOT.name}},
            "2": {"class_type": "FallingTSLoadAudio",
                  "inputs": {"audio_in": ["1", 0], "audio": "", "name": "", "sequence": "00000"}},
            "3": {"class_type": "PreviewAudioSave",
                  "inputs": {"audio": ["2", 0], "filename_prefix": "probe", "filename_suffix": "",
                             "format": "flac", "quality": "128k"}},
        }, "3")
        check("提交执行(audio_in 连线, 下拉为空)", status2 is not None or err2 is None, err2 or status2)
        check("audio_in 直通: 下游拿到音频", status2 == "success" and bool((out2 or {}).get("audio")),
              {"status": status2, "node3": out2})
    finally:
        PROBE_ROOT.unlink(missing_ok=True)
        PROBE_SUB.unlink(missing_ok=True)
        if PROBE_SUB.parent.is_dir() and not any(PROBE_SUB.parent.iterdir()):
            PROBE_SUB.parent.rmdir()

    print()
    print("FAILURES: " + (", ".join(FAILURES) if FAILURES else "无"))
    sys.exit(1 if FAILURES else 0)


main()
