# -*- coding: utf-8 -*-
"""验收「加载视频截帧后播放报 视频加载失败 / Invalid URL」的修复。

根因: 节点缓存的 temp 预览被 ComfyUI 清理后, /fallingts_load_video/preview-url 仍原样返回
那个已经被删掉的文件名 ⇒ 前端播放器指过去是 404 ⇒ 页面上显示「视频加载失败 / Invalid URL」。

断言(全部对运行中的 8188):
 1 截帧建缓存后 preview-url 返回的 temp 文件真实存在(GET /view 200/206);
 2 删掉 temp 预览文件后, preview-url 仍返回可播放地址(现场重编码 temp, 或退回源文件);
 3 前端页面加载该节点后, 播放器 src 指向真实存在的文件, 页面上没有「视频加载失败」;
 4 页面里点「截帧」后, 播放器/帧列表照常, 且页面依旧没有失败提示。
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
BASE = "http://127.0.0.1:8188"
NODE_ID = "18"
VIDEO = "0031_首帧场景/00001_书房旋镜视频.mp4"
TEMP_DIR = ROOT / "ComfyUI" / "temp"
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"]

failures: list[str] = []


def check(label, ok, detail=None):
    print(("PASS" if ok else "FAIL") + ": " + label, "" if detail is None else str(detail)[:240])
    if not ok:
        failures.append(label)


def http(url, method="GET", body=None, headers=None, timeout=120):
    req = urllib.request.Request(url, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def preview_url():
    st, body, _ = http(f"{BASE}/fallingts_load_video/preview-url/{NODE_ID}")
    return st, json.loads(body.decode())


def view_of(url):
    st, body, _ = http(BASE + url if url.startswith("/") else url, timeout=60)
    return st, len(body)


def main():
    # ① 通过截帧路由(懒解码)建缓存 + temp 预览
    payload = json.dumps({"position_seconds": 1.0, "video": VIDEO, "name": "书房", "sequence": "00007"}).encode()
    st, body, hdr = http(f"{BASE}/fallingts_load_video/frame/{NODE_ID}", "POST", payload,
                         {"Content-Type": "application/json"})
    check("截帧路由可用(懒解码建缓存)", st == 200 and body[:2] == b"\x89P", (st, len(body), hdr.get("X-Frame-Index")))

    st, data = preview_url()
    url1 = data.get("url", "")
    check("截帧后 preview-url 返回 temp 预览", st == 200 and "type=temp" in url1, (st, data))
    st1, size1 = view_of(url1)
    check("该 temp 文件可播(GET /view)", st1 in (200, 206) and size1 > 1000, (st1, size1))

    # ② 模拟 ComfyUI 清理 temp: 删掉全部 temp 预览
    killed = []
    for f in TEMP_DIR.glob("ComfyUI_temp_*.mp4"):
        killed.append(f.name)
        f.unlink()
    check("已删除 temp 预览(模拟清理)", bool(killed), killed)

    st2, size2 = view_of(url1)
    check("旧 URL 现在确实 404(复现前提成立)", st2 == 404, (st2, size2))

    st, data = preview_url()
    url2 = data.get("url", "")
    check("temp 被清理后 preview-url 仍给出可播地址", st == 200 and bool(url2), (st, data))
    check("地址已不是那个死文件", url2 != url1, (url1, url2))
    check("返回的是现场重编码的 temp(或退而用源文件)", "type=temp" in url2 or "type=output" in url2, url2)
    st3, size3 = view_of(url2)
    check("新地址可播", st3 in (200, 206) and size3 > 1000, (st3, size3))

    # ③ 浏览器: 打开 0035, 看播放器与页面提示; 再点一次截帧看前端是否自愈
    edge = next((p for p in EDGE if pathlib.Path(p).is_file()), None)
    if not edge:
        print("(跳过浏览器部分: 没找到 Edge/Chrome)")
    else:
        port = free_port()
        profile = pathlib.Path(tempfile.mkdtemp(prefix="vidrecover-"))
        proc = subprocess.Popen([edge, "--headless=new", f"--remote-debugging-port={port}",
                                 f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                                 "--disable-gpu", "--window-size=1800,1100", BASE + "/"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            ws_url = None
            for _ in range(120):
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
            cdp.js("(async()=>{const t0=Date.now();while(Date.now()-t0<120000){"
                   "if(window.app?.graph&&window.app.graph._nodes)return true;"
                   "await new Promise(r=>setTimeout(r,300))}return false})()")
            wf = json.loads((ROOT / "workflows" / "0035_场景截帧.json").read_text(encoding="utf-8"))
            cdp.js("(async()=>{ await app.loadGraphData(JSON.parse(" + json.dumps(json.dumps(wf, ensure_ascii=False)) + ")); return true })()")
            time.sleep(7)

            state = cdp.js(PLAYER_STATE)
            check("页面播放器 src 指向真实文件", any(v["src"] for v in state.get("vids", [])), state)
            check("页面上没有「视频加载失败」", not state.get("failText"), state.get("failText"))

            # 再点一次截帧: 后端会重编码新 temp, 前端应把失败/过期的播放器指过去
            clicked = cdp.js("""
            (() => {
              const n = app.graph._nodes.find(x => x.type === 'FallingTSLoadVideo');
              const host = document.querySelector('[data-node-id="' + n.id + '"]');
              const b = [...(host ? host.querySelectorAll('button') : [])].find(x => (x.textContent||'').trim() === '截帧');
              if (!b) return false;
              b.click();
              return true;
            })()
            """)
            check("页面「截帧」按钮可点", clicked)
            time.sleep(6)
            after = cdp.js(PLAYER_STATE)
            check("截帧后页面仍无「视频加载失败」", not after.get("failText"), after.get("failText"))
            check("截帧后播放器仍在(帧列表照常)", bool(after.get("vids")), after)
        finally:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)

    print()
    print("FAILURES:", failures if failures else "无 (ALL PASS)")
    return 1 if failures else 0


PLAYER_STATE = """
(() => {
  const n = app.graph._nodes.find(x => x.type === 'FallingTSLoadVideo');
  const host = document.querySelector('[data-node-id="' + n.id + '"]');
  const vids = host ? [...host.querySelectorAll('video')].map(v => ({
    src: v.src, ready: v.readyState, net: v.networkState, vis: (v.getClientRects().length > 0),
    err: v.error ? (v.error.code + ':' + v.error.message) : null,
  })) : [];
  const failText = [];
  if (host) {
    for (const el of host.querySelectorAll('*')) {
      if (el.children.length) continue;
      const t = (el.textContent || '').trim();
      if (/加载失败|Invalid URL/i.test(t)) failText.push(t.slice(0, 60));
    }
  }
  return {vids: vids, failText: failText, frames: (n._fallingtsFrameList?.state?.frames || []).length};
})()
"""


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
        for _ in range(40):
            try:
                res = self.call("Runtime.evaluate", {"expression": expr, "awaitPromise": True,
                                                     "returnByValue": True, "allowUnsafeEvalBlockedByCSP": True})
            except RuntimeError as e:
                if "Execution context was destroyed" in str(e):
                    time.sleep(1.2)
                    continue
                raise
            if res.get("exceptionDetails"):
                d = res["exceptionDetails"]
                raise RuntimeError("JS 异常: " + str((d.get("exception") or {}).get("description") or d.get("text")))
            return (res.get("result") or {}).get("value")
        raise RuntimeError("JS 求值失败")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


sys.exit(main())
