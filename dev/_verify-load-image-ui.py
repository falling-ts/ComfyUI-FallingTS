"""端到端验证「加载图像 (来自输出)」节点前端(无头 Edge + CDP 真跑)。

覆盖:
  T1 节点类型已注册到前端
  T2 「名称」输入框排在 image 下拉的刷新按钮**之前**(用户要求: 输入框在刷新按钮上方)
  T3 image 下拉的候选值由 /fallingts_load_image/files 提供(含数字目录内的资源)
  T4 弹窗的分类文案: 「已导入」已被改成「已保存」(与左侧媒体资产面板同一 i18n key)

用法: .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-load-image-ui.py [BASE_URL]
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8189"
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(f"   {'PASS' if ok else 'FAIL'}  {name}   {detail}")
    if not ok:
        FAILURES.append(name)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def find_edge() -> str:
    for path in EDGE_CANDIDATES:
        if pathlib.Path(path).is_file():
            return path
    raise SystemExit("找不到 Edge/Chrome 可执行文件")


class CDP:
    """极简 CDP 客户端: 只用到 Runtime.evaluate。"""

    def __init__(self, ws_url: str) -> None:
        self.ws = connect(ws_url, max_size=None, open_timeout=20)
        self.seq = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.seq += 1
        mid = self.seq
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method} 失败: {msg['error']}")
                return msg.get("result", {})

    def wait_ready(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.call("Runtime.evaluate", {"expression": "1", "returnByValue": True})
                return
            except RuntimeError:
                time.sleep(0.5)
        raise TimeoutError("页面执行上下文一直不可用")

    def js(self, expression: str, await_promise: bool = True, retries: int = 15):
        """求值; 页面导航把执行上下文销毁时重试(连接时页面往往还在加载/跳转)。"""
        last: Exception | None = None
        for _ in range(retries):
            try:
                res = self.call("Runtime.evaluate", {
                    "expression": expression,
                    "awaitPromise": await_promise,
                    "returnByValue": True,
                    "allowUnsafeEvalBlockedByCSP": True,
                })
            except RuntimeError as err:
                if "Execution context was destroyed" not in str(err):
                    raise
                last = err
                time.sleep(1.0)
                continue
            if res.get("exceptionDetails"):
                detail = res["exceptionDetails"]
                text = (detail.get("exception") or {}).get("description") or detail.get("text")
                raise RuntimeError(f"JS 异常: {text}")
            return (res.get("result") or {}).get("value")
        raise last if last else RuntimeError("JS 求值失败")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


def wait_for(predicate, timeout: float, interval: float = 0.5, what: str = ""):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise TimeoutError(f"等待超时: {what}")


def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def kill_browser(proc, profile: pathlib.Path) -> None:
    """先按 pid 树杀, 再按 --user-data-dir 兜底(只匹配 msedge/chrome, 绝不误伤调用方 shell)。"""
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
         f"Where-Object {{ $_.CommandLine -like '*{profile}*' }} | "
         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        capture_output=True,
    )


def main() -> int:
    edge = find_edge()
    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="loadimage-cdp-"))
    print(f"Edge: {edge}\nCDP 端口: {port}\n目标: {BASE}\n")

    proc = subprocess.Popen(
        [edge, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--window-size=1600,1000", BASE + "/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    cdp: CDP | None = None
    try:
        def page_target():
            try:
                targets = fetch_json(f"http://127.0.0.1:{port}/json/list")
            except Exception:  # noqa: BLE001
                return None
            for t in targets:
                if t.get("type") == "page" and t.get("url", "").startswith(BASE):
                    return t
            return None

        target = wait_for(page_target, 60, 1.0, "浏览器页面目标")
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.wait_ready()

        print("== T1. 前端与节点类型就绪 ==")
        ready = cdp.js("""
            (async () => {
              const t0 = Date.now();
              while (Date.now() - t0 < 60000) {
                if (window.LiteGraph?.registered_node_types?.FallingTSLoadImage && window.app?.graph) return true;
                await new Promise(r => setTimeout(r, 300));
              }
              return false;
            })()
        """)
        check("节点类型 FallingTSLoadImage 已注册到前端", ready is True)

        print("\n== T2. 名称输入框在刷新按钮上方 ==")
        order = cdp.js("""
            (() => {
              const node = window.LiteGraph.createNode("FallingTSLoadImage");
              if (!node) return null;
              window.app.graph.add(node);
              node.__ftProbe = true;
              window.app.graph.setDirtyCanvas(true, true);
              return node.widgets.map(w => w.name);
            })()
        """)
        ok_order = (isinstance(order, list) and "name" in order and "refresh" in order
                    and order.index("name") < order.index("refresh"))
        check("widget 顺序: name 在 refresh 之前", ok_order, order)

        print("\n== T3. 下拉候选来自 /fallingts_load_image/files ==")
        dropdown = cdp.js("""
            (async () => {
              const node = window.app.graph._nodes.find(n => n.type === "FallingTSLoadImage");
              const w = node?.widgets?.find(x => x.name === "image");
              if (!w) return { error: "no image widget" };
              const t0 = Date.now();
              while (Date.now() - t0 < 8000 && !(Array.isArray(w.options?.values) && w.options.values.length)) {
                await new Promise(r => setTimeout(r, 300));
              }
              const values = w.options?.values ?? [];
              return { count: values.length, sample: values.slice(0, 3), value: w.value };
            })()
        """)
        check("远端候选已灌进 widget.options.values", isinstance(dropdown, dict) and dropdown.get("count", 0) > 0, dropdown)
        sample = (dropdown or {}).get("sample") or []
        check("候选含数字目录内的资源", any("/" in v for v in sample) or any("/" in v for v in ((dropdown or {}).get("values_all") or [])), sample)

        print("\n== T4. 弹窗分类文案 ==")
        labels = cdp.js("""
            (() => {
              const gp = document.getElementById('vue-app')?.__vue_app__?.config?.globalProperties;
              const i18n = gp?.$i18n;
              const composer = i18n?.global ?? i18n;
              const t = (k) => (typeof gp?.$t === 'function' ? gp.$t(k) : null);
              return {
                imported: t('sideToolbar.labels.imported'),
                generated: t('sideToolbar.labels.generated'),
                all: t('g.all'),
                composerImported: (typeof composer?.t === 'function') ? composer.t('sideToolbar.labels.imported') : null,
                savedInBody: ((document.body.innerText || '').match(/已保存/g) || []).length
              };
            })()
        """)
        check("「已导入」已改成「已保存」(i18n)", isinstance(labels, dict) and labels.get("imported") == "已保存", labels)

        cleanup = cdp.js("""
            (() => {
              const n = window.app.graph._nodes.find(n => n.__ftProbe);
              if (n) window.app.graph.remove(n);
              return true;
            })()
        """)
        check("测试节点已移除", cleanup is True)
    finally:
        if cdp:
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
