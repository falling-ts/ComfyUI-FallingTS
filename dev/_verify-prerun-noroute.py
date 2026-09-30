"""验证「前端已更新、后端未重启」时的降级行为(无头 Edge + CDP 真跑, 打未重启的实例)。

前端 js 经 /extensions 从磁盘即时加载, 而后端路由要重启才注册 ⇒ 页面一刷新就是
"新前端 + 旧后端", 此时 POST /fallingts_prerun/run 会 405。本脚本断言:
  ① 命令确实被请求过(reqs=1);
  ② **不拦截**提交(promptQueueing 事件照常触发);
  ③ 后端没执行命令(无标记文件);
  ④ 只提示一次(console.warn 与 toast 各 1 次)。

用法: .venv\\Scripts\\python.exe custom_nodes\\ComfyUI-FallingTS\\dev\\_verify-prerun-noroute.py [BASE_URL]
"""

from __future__ import annotations

import json
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
MARK = ROOT / "scripts" / "_prerun-noroute.txt"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8188"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(f"   {'PASS' if ok else 'FAIL'}  {name}   {detail}")
    if not ok:
        FAILURES.append(name)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class CDP:
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

    def js(self, expression: str):
        res = self.call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
        )
        if res.get("exceptionDetails"):
            detail = res["exceptionDetails"]
            raise RuntimeError(f"JS 异常: {(detail.get('exception') or {}).get('description') or detail.get('text')}")
        return (res.get("result") or {}).get("value")

    def wait_ready(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.call("Runtime.evaluate", {"expression": "1"})
                return
            except RuntimeError:
                time.sleep(0.5)
        raise TimeoutError("页面执行上下文一直不可用")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    MARK.unlink(missing_ok=True)
    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="prerun-noroute-"))
    print(f"目标: {BASE}  (CDP {port})")

    proc = subprocess.Popen(  # noqa: S603
        [
            EDGE,
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            BASE + "/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    cdp: CDP | None = None
    try:
        def page_target():
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
                    targets = json.loads(r.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                return None
            return next(
                (t for t in targets if t.get("type") == "page" and t.get("url", "").startswith(BASE)),
                None,
            )

        deadline = time.monotonic() + 60
        target = None
        while target is None and time.monotonic() < deadline:
            target = page_target()
            time.sleep(1)
        if target is None:
            raise TimeoutError("找不到浏览器页面目标")

        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.wait_ready()

        ready = cdp.js(
            """
            (async () => {
              const t0 = Date.now();
              while (Date.now() - t0 < 60000) {
                const s = window.app?.ui?.settings;
                if (s?.settingsLookup?.["FallingTS.PreRun.Command"]) return true;
                await new Promise(r => setTimeout(r, 500));
              }
              return false;
            })()
            """
        )
        check("页面加载了新前端(设置项已注册)", ready is True, ready)
        if not ready:
            return 1

        out = cdp.js(
            f"""
            (async () => {{
              const s = window.app.ui.settings;
              if (s.setSettingValueAsync) await s.setSettingValueAsync("FallingTS.PreRun.Command", {json.dumps(f"echo noroute > {MARK.as_posix()}")});
              else s.setSettingValue("FallingTS.PreRun.Command", {json.dumps(f"echo noroute > {MARK.as_posix()}")});

              window.__prc = {{ fired: 0, reqs: 0, warns: [], toasts: [] }};
              window.app.api.addEventListener("promptQueueing", () => {{ window.__prc.fired++; }});
              const of = window.fetch.bind(window);
              window.fetch = (...a) => {{
                try {{ const u = String((a[0] && a[0].url) || a[0]); if (u.includes("/fallingts_prerun/run")) window.__prc.reqs++; }} catch (e) {{}}
                return of(...a);
              }};
              const ow = console.warn.bind(console);
              console.warn = (...a) => {{ window.__prc.warns.push(a.map(String).join(" ")); ow(...a); }};
              const toast = window.app.extensionManager?.toast;
              if (toast) {{ const oa = toast.add.bind(toast);
                toast.add = (o) => {{ window.__prc.toasts.push(o?.summary || ""); return oa(o); }}; }}
              await new Promise(r => setTimeout(r, 200));

              const before = {{ ...window.__prc }};
              let err = null;
              try {{ await window.app.queuePrompt(0, 1, {{ intent: "noroute" }}); }} catch (e) {{ err = String((e && e.message) || e); }}
              const first = {{ fired: window.__prc.fired - before.fired, reqs: window.__prc.reqs - before.reqs,
                               warns: window.__prc.warns.length, toasts: window.__prc.toasts.length, err }};

              // 第二次提交: 一次性提示不应重复
              await window.app.queuePrompt(0, 1, {{ intent: "noroute" }});
              const second = {{ warns: window.__prc.warns.length, toasts: window.__prc.toasts.length }};

              const s2 = window.app.ui.settings;
              if (s2.setSettingValueAsync) await s2.setSettingValueAsync("FallingTS.PreRun.Command", "");
              else s2.setSettingValue("FallingTS.PreRun.Command", "");

              return {{ first, second, warnText: window.__prc.warns[0] || "", toastText: window.__prc.toasts[0] || "" }};
            }})()
            """
        )
        print(f"   {out}")
        first = out["first"]
        check("命令被请求过后端(405)", first["reqs"] == 1, first)
        check("提交未被拦截(新前端不因旧后端卡住运行)", first["fired"] == 1, first)
        time.sleep(1.5)
        check("后端未执行命令(无标记文件)", not MARK.exists())
        check("有一次性 console.warn", first["warns"] == 1 and "404/405" in out["warnText"], out["warnText"][:80])
        check("有一次性 toast 提示", first["toasts"] == 1 and "重启" in out["toastText"], out["toastText"])
        check("第二次提交不再重复提示", out["second"]["warns"] == 1 and out["second"]["toasts"] == 1, out["second"])
    finally:
        if cdp:
            cdp.close()
        proc.terminate()
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        # Edge 会自我重启/派生, 再按**本次专属的 profile 目录**兜底杀一次。
        # ⚠️ 匹配串必须只出现在 chrome 命令行里: 早先用 '*prerun-noroute-*' 会连**本脚本所在的
        #    调用方 shell**(其命令行含脚本名)一起杀掉, 把 dsh 的作业进程也带走。
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$p = (Get-CimInstance Win32_Process | Where-Object {{ $_.Name -eq 'msedge.exe' -and "
                f"$_.CommandLine -like '*{profile}*' }}); "
                f"if ($p) {{ $p | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }} }}",
            ],
            capture_output=True,
            check=False,
        )
        time.sleep(1)
        shutil.rmtree(profile, ignore_errors=True)
        MARK.unlink(missing_ok=True)

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项: {FAILURES}")
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
