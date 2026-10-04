
"""验证「加载视频」(FallingTSLoadVideo) 前端: 控件齐全 / 序列号 / 端口对齐 / remote 配置。

背景(2026-10-02): 截帧/完成/选中帧输出自 PreviewVideo 迁移到新节点, 并新增
「序列号(自动取产物目录最大编号 + 1)」「名称」「刷新序列号」。
本脚本用无头 Edge + CDP 真开前端, 加载 0035_场景截帧 工作流后逐项检查。

用法: .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-0035-load-video.py [BASE_URL]
默认 BASE_URL = http://127.0.0.1:8188
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

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
WORKFLOW = ROOT / "workflows" / "0035_场景截帧.json"
VIDEO = "0031_首帧场景/00001_书房旋镜视频.mp4"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

FAILURES: list[str] = []


def check(label: str, ok: bool, detail=None) -> None:
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    if detail is not None:
        print(f"      {json.dumps(detail, ensure_ascii=False)[:400]}")
    if not ok:
        FAILURES.append(label)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_http(url: str, seconds: int) -> bool:
    for _ in range(seconds):
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


class CDP:
    def __init__(self, ws_url: str):
        self.ws = connect(ws_url, max_size=None, open_timeout=30)
        self.seq = 0

    def call(self, method: str, params=None):
        self.seq += 1
        mid = self.seq
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expression: str):
        for _ in range(25):
            try:
                res = self.call("Runtime.evaluate", {
                    "expression": expression, "awaitPromise": True,
                    "returnByValue": True, "allowUnsafeEvalBlockedByCSP": True,
                })
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

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def kill_browser(proc: subprocess.Popen, profile: pathlib.Path) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    # 只匹配 msedge/chrome: 匹配串写宽了会把调用方 shell 一起杀掉
    subprocess.run([
        "powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{profile}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
    ], capture_output=True)


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8188").rstrip("/")
    if not wait_http(base + "/system_stats", 30):
        print(f"目标 {base} 未就绪")
        return 2

    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    wf_literal = json.dumps(json.dumps(wf, ensure_ascii=False))
    print(f"目标: {base}\n工作流: {WORKFLOW.name}\n")

    edge = next((p for p in EDGE_CANDIDATES if pathlib.Path(p).is_file()), None)
    if edge is None:
        print("找不到 Edge/Chrome")
        return 2

    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="loadvideo-"))
    proc = subprocess.Popen(
        [edge, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--window-size=1600,1000",
         base + "/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    cdp: CDP | None = None
    try:
        ws_url = None
        for _ in range(120):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as r:
                    for t in json.loads(r.read().decode()):
                        if t.get("type") == "page" and t.get("url", "").startswith(base):
                            ws_url = t["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(1)
        if not ws_url:
            print("拿不到 CDP page target")
            return 2
        cdp = CDP(ws_url)
        cdp.call("Runtime.enable")
        ready = cdp.js("(async()=>{const t0=Date.now();while(Date.now()-t0<120000){"
                       "if(window.app?.graph&&window.app.graph._nodes&&window.LiteGraph?.registered_node_types?.FallingTSLoadVideo)return true;"
                       "await new Promise(r=>setTimeout(r,300))}return false})()")
        check("前端与 FallingTSLoadVideo 就绪", ready is True)

        cdp.js(f"(async()=>{{ await app.loadGraphData(JSON.parse({wf_literal})); return true }})()")
        time.sleep(5)

        info = cdp.js("""
        (() => {
          const n = app.graph._nodes.find(x => x.type === 'FallingTSLoadVideo');
          if (!n) return { error: '节点不存在' };
          const names = n.widgets.map(w => w.name);
          const seq = n.widgets.find(w => w.name === 'sequence');
          const vid = n.widgets.find(w => w.name === 'video');
          return {
            names,
            sequence: seq?.value,
            video: vid?.value,
            values: (vid?.options?.values || []).slice(0, 5),
            outputs: (n.outputs || []).map(o => o.name),
            labels: (n.outputs || []).map(o => o.label),
            size: n.size,
            pos: n.pos,
          };
        })()
        """)
        if info and info.get("error"):
            check("工作流里找到 FallingTSLoadVideo 节点", False, info)
        else:
            check("工作流里找到 FallingTSLoadVideo 节点", True)
            names = info.get("names") or []
            for want in ("name", "sequence", "刷新序列号", "video", "截帧", "完成", "输出帧数", "frame_list", "video_fallback"):
                check(f"控件存在: {want}", want in names, names)
            check("序列号自动填成 5 位 00001", info.get("sequence") == "00001", info.get("sequence"))
            check("视频下拉值 = 工作流存档视频", info.get("video") == VIDEO, info.get("video"))
            check("下拉候选含子目录视频", any("/" in v for v in (info.get("values") or [])), info.get("values"))
            outputs = info.get("outputs") or []
            check("输出端口 = 1(video) + 8(选中帧)", len(outputs) == 9, outputs)
            check("视频端口在最上", outputs[:1] == ["video"], outputs[:2])
            check("端口标签为选中帧 N", info.get("labels")[1:3] == ["选中帧 1", "选中帧 2"], info.get("labels")[:4])

        after = cdp.js("""
        (async () => {
          const n = app.graph._nodes.find(x => x.type === 'FallingTSLoadVideo');
          const seq = n.widgets.find(w => w.name === 'sequence');
          const rb = n.widgets.find(w => w.name === '刷新序列号');
          if (!rb || typeof rb.callback !== 'function') return { error: '没有刷新序列号按钮 widget' };
          const before = seq.value;
          rb.callback();
          await new Promise(r => setTimeout(r, 2500));
          return { before, after: seq.value };
        })()
        """)
        check("存在「刷新序列号」按钮", isinstance(after, dict) and "before" in after, after)
        if isinstance(after, dict) and "before" in after:
            check("刷新后序列号 = 00001(0035_场景截帧 目录尚无产物)",
                  after.get("before") == "00001" and after.get("after") == "00001", after)

        spec = cdp.js("""
        (() => {
          const t = LiteGraph.registered_node_types.FallingTSLoadVideo;
          const req = t?.nodeData?.input?.required || {};
          const video = req.video?.[1] || {};
          return {
            remote: video.remote ?? null,
            upload: Object.keys(video).filter(k => k.endsWith('_upload')),
            imageFolder: video.image_folder ?? null,
            hasFingerprint: typeof t?.prototype?.constructor?.fingerprint_inputs === 'function'
              || typeof t?.fingerprint_inputs === 'function',
          };
        })()
        """)
        remote = (spec or {}).get("remote") or {}
        check("remote 保留 refresh_button", remote.get("refresh_button") is True, remote)
        check("remote 不带 control_after_refresh", "control_after_refresh" not in remote, remote)
        check("带 video_upload", (spec or {}).get("upload") == ["video_upload"], spec)

        pv = cdp.js("""
        (async () => {
          const wf = await fetch('/userdata?dir=workflows&full_info=true').then(r => r.json()).catch(() => null);
          const t = LiteGraph.registered_node_types.PreviewVideo;
          return { outputs: (t?.nodeData?.output || []).length, hasWorkflows: !!wf };
        })()
        """)
        check("精简后 PreviewVideo 只有 1 个输出", (pv or {}).get("outputs") == 1, pv)
    finally:
        if cdp is not None:
            cdp.close()
        kill_browser(proc, profile)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} 项 -> {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
