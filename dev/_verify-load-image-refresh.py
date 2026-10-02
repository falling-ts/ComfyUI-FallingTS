
"""验证「加载图像」(FallingTSLoadImage) 下拉: 打开工作流与点刷新都不再改写已选值。

背景(2026-10-02): 上游 remote 组件的 onFirstLoad 在节点首次加载时无条件把 widget.value
设成候选首项, 而候选按 mtime 倒序 ⇒ 最近改动的产物夺走选中权; 内置 LoadImageOutput 的
control_after_refresh="first" 让每次刷新也这样。本节点已去掉该项, 并由 web/js/load_image.js
做短守护拦 onFirstLoad。

用法: .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-load-image-refresh.py [BASE_URL]
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
WORKFLOW = ROOT / "workflows" / "0010_灰度遮罩.json"
STAMPED = "0011_万物建模/00001_陈落.png"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

FAILURES: list[str] = []


def check(label: str, ok: bool, detail=None) -> None:
    print(f"{'PASS' if ok else 'FAIL'}: {label}")
    if detail is not None:
        print(f"      {json.dumps(detail, ensure_ascii=False)}")
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
    for node in wf["nodes"]:
        if node.get("type") == "FallingTSLoadImage":
            node["widgets_values"][1] = STAMPED
            if isinstance(node.get("widgets_values_named"), dict):
                node["widgets_values_named"]["image"] = STAMPED
    wf_literal = json.dumps(json.dumps(wf, ensure_ascii=False))
    print(f"目标: {base}\n工作流: {WORKFLOW.name} (image 注入为 {STAMPED})\n")

    edge = next((p for p in EDGE_CANDIDATES if pathlib.Path(p).is_file()), None)
    if edge is None:
        print("找不到 Edge/Chrome")
        return 2

    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="loadimg-refresh-"))
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
                       "if(window.app?.graph&&window.app.graph._nodes&&window.LiteGraph?.registered_node_types?.FallingTSLoadImage)return true;"
                       "await new Promise(r=>setTimeout(r,300))}return false})()")
        check("前端与 FallingTSLoadImage 就绪", ready is True)

        cdp.js(f"(async()=>{{ await app.loadGraphData(JSON.parse({wf_literal})); return true }})()")
        time.sleep(5)
        after_load = cdp.js("""
        (() => {
          const n = app.graph._nodes.find(x => x.type === 'FallingTSLoadImage');
          const img = n.widgets.find(w => w.name === 'image');
          return { value: img.value, widgetsValues: n.widgets_values, values: (img.options?.values || []).slice(0, 6) };
        })()
        """)
        values = (after_load or {}).get("values") or []
        first = values[0] if values else None
        check("候选已灌入且含子目录资源", any("/" in v for v in values), values)
        if first == STAMPED:
            print("      (候选首项恰等于存档值, 本用例无法区分是否被改写 — 换一个文件再跑)")
        else:
            check("打开工作流后 image 值仍是存档值(未被换成候选首项)",
                  (after_load or {}).get("value") == STAMPED, after_load)

        after_refresh = cdp.js("""
        (async () => {
          const n = app.graph._nodes.find(x => x.type === 'FallingTSLoadImage');
          const img = n.widgets.find(w => w.name === 'image');
          const rb = n.widgets.find(w => w.name === 'refresh');
          if (!rb || typeof rb.callback !== 'function') return { error: '没有刷新按钮 widget' };
          const before = img.value;
          rb.callback();
          await new Promise(r => setTimeout(r, 3500));
          return { before, after: img.value, values: (img.options?.values || []).slice(0, 4) };
        })()
        """)
        check("存在刷新按钮", isinstance(after_refresh, dict) and "before" in after_refresh, after_refresh)
        if isinstance(after_refresh, dict) and "before" in after_refresh:
            check("点刷新后 image 值不变", after_refresh["before"] == after_refresh["after"] == STAMPED)
            check("刷新后候选仍含子目录资源",
                  any("/" in v for v in (after_refresh.get("values") or [])))

        spec = cdp.js("""
        (() => {
          const t = LiteGraph.registered_node_types.FallingTSLoadImage;
          const spec = t?.nodeData?.input?.required?.image?.[1];
          return { remote: spec?.remote ?? null };
        })()
        """)
        remote = (spec or {}).get("remote") or {}
        check("remote 保留 refresh_button", remote.get("refresh_button") is True, remote)
        check("remote 不再带 control_after_refresh", "control_after_refresh" not in remote, remote)
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
