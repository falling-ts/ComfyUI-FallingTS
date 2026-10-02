# -*- coding: utf-8 -*-
"""浏览器验收: FallingTSLoadAudio 前端(控件顺序 / 试听播放器 / 序列号 / 已选值不被顶掉)。

前提: 另起一个临时实例(带新代码)在 8189:
  cd ComfyUI && D:/AI/Comfy/.venv/Scripts/python.exe main.py --cpu --port 8189 --disable-pinned-memory
用法(工作区根): .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-load-audio-ui.py
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
BASE = "http://127.0.0.1:8189"
AUDIO = "0060_背景音乐/_probe_tmp_audio.mp3"

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


def main():
    edge = next((p for p in EDGE if pathlib.Path(p).is_file()), None)
    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="verify-loadaudio-"))
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

        # 扩展脚本已加载(否则不会挂播放器/序列号按钮)
        loaded = cdp.js("(app.extensions||[]).map(e => e.name).filter(n => n && n.includes('FallingTS.LoadAudio')).join(',')")
        check("load_audio.js 已注册", "FallingTS.LoadAudio" in str(loaded), loaded)

        # 拖一个节点出来
        info = cdp.js("""
        (async () => {
          app.graph.clear();
          const n = LiteGraph.createNode("FallingTSLoadAudio");
          app.graph.add(n);
          await new Promise(r => setTimeout(r, 600));
          window.__node = n;
          const prompt = await app.graphToPrompt();
          return {
            sent: prompt.output[String(n.id)] ? prompt.output[String(n.id)].inputs : null,
            widgets: (n.widgets || []).map(w => w.name),
            inputs: (n.inputs || []).map(i => i.name + ':' + i.type),
            outputs: (n.outputs || []).map(o => o.name + ':' + o.type),
          };
        })()
        """)
        check("控件顺序 = name/sequence/刷新序列号/audio",
              info["widgets"][:4] == ["name", "sequence", "刷新序列号", "audio"], info["widgets"])
        check("提交载荷不带 audioUI(故后端声明为 optional)", "audioUI" not in (info["sent"] or {}), info["sent"])
        check("带 audioUI 播放器 + 上传按钮",
              "audioUI" in info["widgets"] and "upload" in info["widgets"], info["widgets"])
        check("输入 = audio_in/name/sequence/audio/audioUI/upload",
              info["inputs"] == ["audio_in:AUDIO", "name:STRING", "sequence:STRING", "audio:COMBO",
                                 "audioUI:AUDIO_UI", "upload:AUDIOUPLOAD"], info["inputs"])
        check("输出 = audio:AUDIO + prefix:STRING(文件名前缀)", info["outputs"] == ["audio:AUDIO", "prefix:STRING"], info["outputs"])

        # 序列号: 新节点会自动向后端取一次
        seq = cdp.js("(window.__node.widgets.find(w => w.name === 'sequence') || {}).value")
        check("序列号已按 5 位填充", isinstance(seq, str) and len(seq) == 5 and seq.isdigit(), seq)

        # 选中探针音频 → 前端原生 audioUI 播放器按已选值重建播放源
        played = cdp.js("""
        (async () => {
          const n = window.__node;
          const w = n.widgets.find(x => x.name === 'audio');
          w.value = %s;
          w.callback && w.callback(w.value);
          await new Promise(r => setTimeout(r, 900));
          const host = document.querySelector('[data-node-id="' + n.id + '"]');
          const el = host ? host.querySelector('audio') : null;
          return { inDom: !!el, src: el ? (el.getAttribute('src') || '') : '' };
        })()
        """ % json.dumps(AUDIO))
        check("节点内 <audio> 播放器已渲染", played["inDom"], played)
        check("播放源指向所选的音频文件", "_probe_tmp_audio.mp3" in urllib.request.unquote(played["src"]), played["src"])

        # 打开一个带存档值的工作流: 已选音频不能被候选首项顶掉
        wf = {"id": "verify-load-audio", "last_node_id": 1, "last_link_id": 0, "nodes": [
            {"id": 1, "type": "FallingTSLoadAudio", "pos": [40, 40], "size": [420, 220], "flags": {}, "order": 0,
             "mode": 0, "inputs": [{"name": "name", "type": "STRING", "widget": {"name": "name"}, "link": None},
                                   {"name": "sequence", "type": "STRING", "widget": {"name": "sequence"}, "link": None},
                                   {"name": "audio", "type": "COMBO", "widget": {"name": "audio"}, "link": None},
                                   {"name": "upload", "type": "IMAGEUPLOAD", "widget": {"name": "upload"}, "link": None}],
             "outputs": [{"name": "audio", "type": "AUDIO", "slot_index": 0, "links": []},
                         {"name": "prefix", "type": "STRING", "slot_index": 1, "links": []}],
             "properties": {"Node name for S&R": "FallingTSLoadAudio"},
             "widgets_values": ["name-a", "00007", "0060_背景音乐/_probe_tmp_audio.mp3", None, None, None, None],
             "widgets_values_named": {"name": "name-a", "sequence": "00007",
                                      "audio": "0060_背景音乐/_probe_tmp_audio.mp3"}},
        ], "links": [], "groups": [], "config": {}, "extra": {}, "version": 0.4}
        lit = json.dumps(json.dumps(wf, ensure_ascii=False))
        kept = cdp.js("""
        (async () => {
          app.graph.clear();
          await app.loadGraphData(JSON.parse(%s));
          await new Promise(r => setTimeout(r, 4200));
          const n = app.graph._nodes[0];
          const get = name => (n.widgets.find(w => w.name === name) || {}).value;
          return { audio: get('audio'), sequence: get('sequence'), name: get('name'),
                   values: (n.widgets.find(w => w.name === 'audio') || {}).options?.values?.slice(0, 4) };
        })()
        """ % lit)
        check("打开工作流后已选音频不被顶掉", kept["audio"] == AUDIO, kept)
        check("打开工作流后序列号保留存档值", kept["sequence"] == "00007", kept)
        check("打开工作流后名称保留存档值", kept["name"] == "name-a", kept)

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
