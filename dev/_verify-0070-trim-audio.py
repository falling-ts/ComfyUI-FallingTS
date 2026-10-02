# -*- coding: utf-8 -*-
"""验收: 0070_截取声音(加载音频 + 截取音频 → 多个截取音频预览) + FallingTSLoadAudio 的 audio_in。

前提: 临时实例跑在 8189(读同一份插件代码), 且 media 根目录有探针音频 _probe_audio_in.wav。
用法(工作区根): .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-0070-trim-audio.py
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from websockets.sync.client import connect

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
BASE = "http://127.0.0.1:8189"
PROBE = "_probe_audio_in.wav"

FAILURES = []


def check(label, ok, detail=None):
    print(("PASS" if ok else "FAIL") + ": " + label, "" if detail is None else str(detail)[:300])
    if not ok:
        FAILURES.append(label)


class CDP:
    def __init__(self, ws_url):
        self.ws = connect(ws_url, max_size=None, open_timeout=30)
        self.seq = 0

    def call(self, method, params=None):
        self.seq += 1
        mid = self.seq
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        for _ in range(30):
            try:
                res = self.call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
            except RuntimeError as exc:
                if "Execution context was destroyed" in str(exc):
                    time.sleep(1.2)
                    continue
                raise
            if res.get("exceptionDetails"):
                d = res["exceptionDetails"]
                raise RuntimeError("JS 异常: " + str((d.get("exception") or {}).get("description") or d.get("text")))
            return (res.get("result") or {}).get("value")
        raise RuntimeError("JS 求值失败")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


def main():
    # ── 后端: audio_in 路径端到端(核心 LoadAudio → 我们的加载音频 → 预览音频) ──
    info = None
    for _ in range(60):
        try:
            info = get("/object_info/FallingTSLoadAudio")
            if info:
                break
        except Exception:
            time.sleep(3)
    if not info:
        print("FAIL: 8189 未就绪")
        sys.exit(1)
    node = info["FallingTSLoadAudio"]
    check("加载音频声明 audio_in(AUDIO, optional)",
          node["input_order"].get("optional") == ["audioUI", "audio_in"]
          and node["input"]["optional"]["audio_in"][0] == "AUDIO",
          node["input_order"])

    if not (ROOT / "media" / "七纹刻印" / PROBE).is_file():
        print("SKIP 后端 audio_in 用例: 探针音频不存在", PROBE)
    else:
        prompt = {
            "1": {"class_type": "LoadAudio", "inputs": {"audio": PROBE}},
            "2": {"class_type": "FallingTSLoadAudio",
                  "inputs": {"audio_in": ["1", 0], "audio": "", "name": "探针", "sequence": "00000"}},
            "3": {"class_type": "PreviewAudioSave",
                  "inputs": {"audio": ["2", 0], "filename_prefix": "probe", "filename_suffix": "",
                             "format": "flac", "quality": "128k"}},
        }
        res = post("/prompt", {"prompt": prompt, "client_id": "verify-0070"})
        pid = res.get("prompt_id")
        check("audio_in 图提交", bool(pid), res)
        if pid:
            hist = None
            for _ in range(60):
                time.sleep(2)
                h = get("/history/" + pid)
                if pid in h:
                    hist = h[pid]
                    break
            outs = (hist or {}).get("outputs") or {}
            check("audio_in 直通: 下游拿到音频",
                  (hist or {}).get("status", {}).get("status_str") == "success" and bool(outs.get("3", {}).get("audio")),
                  {"status": (hist or {}).get("status", {}).get("status_str"), "node3": outs.get("3")})
            check("audio_in 直通: 本节点发 UI.PreviewAudio", bool(outs.get("2", {}).get("audio")), outs.get("2"))

    # ── 前端: 0070 工作流加载后的连线与控件值 ──
    edge = next((p for p in EDGE if pathlib.Path(p).is_file()), None)
    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="verify0070-"))
    proc = subprocess.Popen([edge, "--headless=new", f"--remote-debugging-port={port}",
                             f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                             "--disable-gpu", "--window-size=1800,1100", BASE + "/"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(150):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as r:
                    for t in json.loads(r.read().decode()):
                        if t.get("type") == "page" and t.get("url", "").startswith(BASE):
                            ws_url = t["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(1)
        cdp = CDP(ws_url)
        cdp.call("Runtime.enable")
        cdp.js("(async()=>{const t0=Date.now();while(Date.now()-t0<180000){"
               "if(window.app?.graph&&window.app.graph._nodes)return true;"
               "await new Promise(r=>setTimeout(r,300))}return false})()")
        cdp.js("window.__errs=[];window.addEventListener('error',e=>window.__errs.push(String(e.message)))")
        wf = json.loads((ROOT / "workflows" / "0070_截取声音.json").read_text(encoding="utf-8"))
        lit = json.dumps(json.dumps(wf, ensure_ascii=False))
        dump = cdp.js("""
        (async () => {
          app.graph.clear();
          await app.loadGraphData(JSON.parse(%s));
          await new Promise(r => setTimeout(r, 1000));
          // Vue 节点按视口渲染: 先把视角对准加载音频节点, 否则它的 DOM 还没挂出来
          const target = (app.graph._nodes || []).find(n => n.type === 'FallingTSLoadAudio');
          if (target && app.canvas?.centerOnNode) app.canvas.centerOnNode(target);
          await new Promise(r => setTimeout(r, 800));
          const g = app.graph;
          const nm = n => (n.title || n.type);
          const byType = t => (g._nodes || []).filter(n => n.type === t);
          const links = Object.values(g.links || {}).map(l => {
            const a = g.getNodeById(l.origin_id), b = g.getNodeById(l.target_id);
            return { from: a ? nm(a) + '.' + (a.outputs?.[l.origin_slot]?.name ?? '') : '?',
                     to: b ? nm(b) + '.' + (b.inputs?.[l.target_slot]?.name ?? '') : '?' };
          });
          const lv = byType('FallingTSLoadAudio')[0];
          return {
            count: (g._nodes || []).length,
            links: links,
            titles: (g._nodes || []).map(nm),
            lvWidgets: lv ? Object.fromEntries((lv.widgets || []).map(w => [w.name, w.value])) : null,
            trimOuts: byType('FallingTSAudioTrim').map(n => (n.outputs || []).map(o => o.name)),
            // 节点内播放器: 前端 AUDIO_UI 工厂把 <audio> 当 DOM widget 挂在节点上;
            // 直接查 widget.element(不依赖 Vue 是否已按视口把 DOM 渲染出来)
            hasPlayer: (() => {
              const w = lv && (lv.widgets || []).find(x => x.name === 'audioUI');
              return !!(w && w.element && String(w.element.tagName).toLowerCase() === 'audio');
            })(),
            playerTag: (() => {
              const w = lv && (lv.widgets || []).find(x => x.name === 'audioUI');
              return w && w.element ? String(w.element.tagName) : null;
            })(),
          };
        })()
        """ % lit)
        check("0070 节点集 = MD/加载音频/截取音频/3×预览/说明", dump["count"] == 8
              and sorted(dump["titles"]) == sorted(["MD 数据表 (截取声音)", "Reroute", "音频 加载/试听",
                                                    "截取音频", "截取音频预览-1", "截取音频预览-2", "截取音频预览-3", "使用说明"]),
              dump["titles"])
        want = {"MD 数据表 (截取声音).原声音": "音频 加载/试听.audio_in",
                "MD 数据表 (截取声音).ID": "Reroute.",
                "音频 加载/试听.audio": "截取音频.audio",
                "截取音频.audio_1": "截取音频预览-1.audio",
                "截取音频.audio_2": "截取音频预览-2.audio",
                "截取音频.audio_3": "截取音频预览-3.audio",
                "Reroute.": "截取音频.filename_prefix",
                }
        got = {(l["from"], l["to"]) for l in dump["links"]}
        missing = [k for k, v in want.items() if (k, v) not in got]
        check("0070 关键连线正确", not missing, {"missing": missing, "all": sorted(got)})
        check("0070 Reroute 分发 4 个 filename_prefix",
              len([l for l in dump["links"] if l["from"] == "Reroute." and l["to"].endswith("filename_prefix")]) == 4,
              [l for l in dump["links"] if l["to"].endswith("filename_prefix")])
        check("加载音频控件值 = 空音频/序列号 00000",
              (dump["lvWidgets"] or {}).get("audio") == "" and (dump["lvWidgets"] or {}).get("sequence") == "00000",
              dump["lvWidgets"])
        check("加载音频节点内播放器已挂载(原生 AUDIO_UI <audio>)", dump["hasPlayer"], dump.get("playerTag"))
        check("截取音频输出 = audio + 截段 1..3",
              dump["trimOuts"] == [["audio", "audio_1", "audio_2", "audio_3"]], dump["trimOuts"])
        errs = cdp.js("window.__errs")
        check("无前端 JS 报错", not errs, errs)
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
                        f"Where-Object {{ $_.CommandLine -like '*{profile}*' }} | "
                        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                       capture_output=True)

    print()
    print("FAILURES: " + (", ".join(FAILURES) if FAILURES else "无"))
    sys.exit(1 if FAILURES else 0)


main()
