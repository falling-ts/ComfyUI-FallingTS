"""端到端验证「运行前命令」前端(无头 Edge + CDP 真跑)。

覆盖:
  T1 设置项已注册(id/name/type/category/sortOrder/defaultValue)
  T2 提示音 sortOrder(20) 高于开始前命令(10) —— 决定右栏上下顺序
  T3 设置对话框「其它」分类里两项都在, 且提示音排在开始前命令**上面**
  T4 命令为空 → 不拦截(queuePrompt 正常往下走)
  T5 命令非 0 退出 → 取消本次运行(queuePrompt 返回 false), 且命令确实执行过
  T6 命令成功 → 先执行再提交(标记文件落盘, queuePrompt 未被拦截)
  T7 partial 提交(截帧/继续) → **不执行**前置命令

用法: .venv\\Scripts\\python.exe custom_nodes\\ComfyUI-FallingTS\\dev\\_verify-prerun-ui.py [BASE_URL]
"""

from __future__ import annotations

import json
import os
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
SCRIPTS = ROOT / "scripts"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8189"
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

MARK_BLOCK = SCRIPTS / "_prerun-ui-block.txt"
MARK_OK = SCRIPTS / "_prerun-ui-ok.txt"
MARK_PARTIAL = SCRIPTS / "_prerun-ui-partial.txt"

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
        """等页面执行上下文可用(连接时页面往往还在导航, 上下文会被销毁重建)。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.call("Runtime.evaluate", {"expression": "1", "returnByValue": True})
                return
            except RuntimeError:
                time.sleep(0.5)
        raise TimeoutError("页面执行上下文一直不可用")

    def js(self, expression: str, await_promise: bool = True):
        """求值一个 JS 表达式, 回传 returnByValue 的结果; JS 抛错则抛出。"""
        res = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
                "allowUnsafeEvalBlockedByCSP": True,
            },
        )
        if res.get("exceptionDetails"):
            detail = res["exceptionDetails"]
            text = (detail.get("exception") or {}).get("description") or detail.get("text")
            raise RuntimeError(f"JS 异常: {text}")
        return (res.get("result") or {}).get("value")

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


def wait_file(path: pathlib.Path, timeout: float = 15.0) -> bool:
    return bool(wait_for(lambda: path.exists() and path.stat().st_size > 0, timeout, what=str(path.name))) if path.exists() or True else False


def main() -> int:
    for mark in (MARK_BLOCK, MARK_OK, MARK_PARTIAL):
        mark.unlink(missing_ok=True)

    edge = find_edge()
    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="prerun-cdp-"))
    print(f"Edge: {edge}\nCDP 端口: {port}\nprofile: {profile}\n目标: {BASE}")

    proc = subprocess.Popen(  # noqa: S603
        [
            edge,
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--window-size=1600,1000",
            BASE + "/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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

        print("\n== 0. 等前端与扩展就绪 ==")
        ready = cdp.js(
            """
            (async () => {
              const t0 = Date.now();
              while (Date.now() - t0 < 60000) {
                const s = window.app?.ui?.settings;
                if (s?.settingsLookup && Object.keys(s.settingsLookup).length > 50
                    && s.settingsLookup["FallingTS.PreRun.Command"]) {
                  return true;
                }
                await new Promise(r => setTimeout(r, 500));
              }
              return false;
            })()
            """
        )
        check("前端加载 + pre_run_command.js 已注册设置", ready is True, ready)
        if not ready:
            return 1

        print("\n== 1. 设置项定义 ==")
        params = cdp.js(
            """
            (() => {
              const p = app.ui.settings.settingsLookup["FallingTS.PreRun.Command"];
              return p ? { id: p.id, name: p.name, type: p.type, category: p.category,
                           sortOrder: p.sortOrder, defaultValue: p.defaultValue,
                           hasTooltip: !!p.tooltip } : null;
            })()
            """
        )
        print(f"   {params}")
        check("id/name 正确", params.get("name") == "开始前命令", params.get("name"))
        check("type=text", params.get("type") == "text", params.get("type"))
        cat = params.get("category")
        cat_list = list(cat.values()) if isinstance(cat, dict) else list(cat or [])
        check("category=[开始前命令](单元素→浮到「其它」)", cat_list == ["开始前命令"], cat_list)
        check("defaultValue 空串(未配置即跳过)", params.get("defaultValue") == "", repr(params.get("defaultValue")))
        check("带 tooltip 说明", params.get("hasTooltip") is True)

        notify_order = cdp.js('(() => { const p = app.ui.settings.settingsLookup["FallingTS.Notify.Panel"]; return p ? p.sortOrder : null; })()')
        pre_order = params.get("sortOrder")
        print(f"   提示音 sortOrder={notify_order}  开始前命令 sortOrder={pre_order}")
        check("提示音 sortOrder > 开始前命令(右栏降序 ⇒ 提示音在上)", (notify_order or 0) > (pre_order or 0))

        print("\n== 2. 设置对话框: 「其它」分类里的排位 ==")
        opened = cdp.js(
            """
            (async () => {
              const em = window.app?.extensionManager;
              if (em?.command?.execute) {
                try { await em.command.execute("Comfy.ShowSettingsDialog"); } catch (e) {}
              }
              await new Promise(r => setTimeout(r, 1200));
              if (!document.querySelector('[data-nav-id="Other"]')) {
                const icon = [...document.querySelectorAll("i,span,div")]
                  .find(e => String(e.className || "").includes("lucide--settings"));
                (icon?.closest("button") || icon?.parentElement)?.click();
                await new Promise(r => setTimeout(r, 1500));
              }
              return !!document.querySelector('[data-nav-id="Other"]');
            })()
            """
        )
        check("设置对话框已打开且能找到「其它」导航", opened is True, opened)

        nav_label = cdp.js('(() => { const n = document.querySelector(\'[data-nav-id="Other"]\'); return n ? n.textContent.trim() : null; })()')
        print(f"   「其它」导航文案: {nav_label!r}")

        clicked = cdp.js(
            """
            (async () => {
              const el = document.querySelector('[data-nav-id="Other"]');
              if (!el) return false;
              el.click();
              await new Promise(r => setTimeout(r, 900));
              return true;
            })()
            """
        )
        check("点击「其它」分类", clicked is True)

        dom = cdp.js(
            """
            (() => {
              const sel = id => document.querySelector(`[data-setting-id="${id}"]`);
              const box = e => { if (!e) return null; const r = e.getBoundingClientRect();
                return { top: Math.round(r.top), height: Math.round(r.height), text: (e.textContent || "").trim().slice(0, 40) }; };
              const notify = sel("FallingTS.Notify.Panel");
              const prerun = sel("FallingTS.PreRun.Command");
              return {
                notify: box(notify),
                prerun: box(prerun),
                prerunInput: prerun ? prerun.querySelectorAll("input,textarea").length : 0,
                prerunPlaceholder: prerun ? (prerun.querySelector("input,textarea")?.placeholder || "") : "",
              };
            })()
            """
        )
        print(f"   提示音: {dom.get('notify')}")
        print(f"   开始前命令: {dom.get('prerun')} 输入框数={dom.get('prerunInput')} placeholder={dom.get('prerunPlaceholder')!r}")
        check("两项都在「其它」分类里", bool(dom.get("notify") and dom.get("prerun")))
        check("开始前命令渲染出输入框", (dom.get("prerunInput") or 0) >= 1, dom.get("prerunInput"))
        check("输入框有占位提示", bool(dom.get("prerunPlaceholder")))
        if dom.get("notify") and dom.get("prerun"):
            check(
                "提示音排在开始前命令上面(即开始前命令在提示音下面)",
                dom["notify"]["top"] < dom["prerun"]["top"],
                f"notify.top={dom['notify']['top']} prerun.top={dom['prerun']['top']}",
            )

        def queue_prompt(command: str, third: str) -> dict:
            return cdp.js(
                f"""
                (async () => {{
                  const s = window.app.ui.settings;
                  if (s.setSettingValueAsync) await s.setSettingValueAsync("FallingTS.PreRun.Command", {json.dumps(command)});
                  else {{ s.setSettingValue("FallingTS.PreRun.Command", {json.dumps(command)});
                         await new Promise(r => setTimeout(r, 200)); }}
                  await new Promise(r => setTimeout(r, 150));
                  let res, err = null;
                  const before = {{ ...window.__prc }};
                  try {{ res = await window.app.queuePrompt(0, 1, {third}); }}
                  catch (e) {{ err = String((e && e.message) || e); }}
                  return {{
                    blocked: res === false,
                    err,
                    fired: window.__prc.fired - before.fired,
                    reqs: window.__prc.reqs - before.reqs,
                  }};
                }})()
                """
            )

        # 探针: ① promptQueueing 事件 = 原生提交入口真的被走到了(包装没拦);
        #       ② /fallingts_prerun/run 请求数 = 前置命令有没有被请求执行。
        cdp.js(
            """
            (() => {
              window.__prc = window.__prc || { fired: 0, reqs: 0, hooked: false };
              if (!window.__prc.hooked) {
                window.__prc.hooked = true;
                window.app.api.addEventListener("promptQueueing", () => { window.__prc.fired++; });
                const of = window.fetch.bind(window);
                window.fetch = (...a) => {
                  try {
                    const u = String((a[0] && a[0].url) || a[0]);
                    if (u.includes("/fallingts_prerun/run")) window.__prc.reqs++;
                  } catch (e) {}
                  return of(...a);
                };
              }
              return window.__prc;
            })()
            """
        )

        print("\n== 3. 命令为空 → 跳过且不拦截 ==")
        out = queue_prompt("", '{intent:"verify"}')
        print(f"   {out}")
        check("空命令: 不请求后端(跳过)", out.get("reqs") == 0, out)
        check("空命令: 提交入口被正常走到(未拦截)", out.get("fired") == 1, out)

        print("\n== 4. 非 0 退出 → 取消本次运行 ==")
        out = queue_prompt(f"echo blocked > {MARK_BLOCK.as_posix()} & exit /b 7", '{intent:"verify"}')
        print(f"   {out}")
        check("失败命令: 请求过后端", out.get("reqs") == 1, out)
        check("失败命令: 确实执行过(标记落盘)", wait_file(MARK_BLOCK, 10))
        check("失败命令: 提交被拦下(原生入口未被走到)", out.get("fired") == 0, out)
        check("失败命令: 包装返回 false(等价取消本次运行)", out.get("blocked") is True, out)

        print("\n== 5. 命令成功 → 先执行后提交 ==")
        out = queue_prompt(f"echo ok > {MARK_OK.as_posix()}", '{intent:"verify"}')
        print(f"   {out}")
        check("成功命令: 请求过后端", out.get("reqs") == 1, out)
        check("成功命令: 执行成功(标记落盘)", wait_file(MARK_OK, 10))
        check("成功命令: 随后正常提交(未拦截)", out.get("fired") == 1, out)

        print("\n== 6. partial 提交(截帧/继续)→ 不执行前置命令 ==")
        out = queue_prompt(f"echo partial > {MARK_PARTIAL.as_posix()} & exit /b 7", "[42]")
        print(f"   {out}")
        time.sleep(1.5)
        check("partial: 不请求后端(跳过)", out.get("reqs") == 0, out)
        check("partial: 无标记落盘", not MARK_PARTIAL.exists())
        check("partial: 提交未被拦截", out.get("fired") == 1, out)

        print("\n== 7. 收尾: 清空配置 ==")
        cdp.js(
            """
            (async () => {
              const s = window.app.ui.settings;
              if (s.setSettingValueAsync) await s.setSettingValueAsync("FallingTS.PreRun.Command", "");
              else s.setSettingValue("FallingTS.PreRun.Command", "");
              return true;
            })()
            """
        )
        check("配置已复位为空串", cdp.js('(() => window.app.ui.settings.getSettingValue("FallingTS.PreRun.Command"))()') == "")

    finally:
        if cdp:
            cdp.close()
        proc.terminate()
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        # Edge 会自我重启/派生, 再按**本次专属的 profile 目录**兜底杀一次(只匹配 msedge 进程:
        # 泛匹配命令行会把调用方 shell 一起杀掉, 连带 dsh 的作业进程)。
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
        for mark in (MARK_BLOCK, MARK_OK, MARK_PARTIAL):
            mark.unlink(missing_ok=True)

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项: {FAILURES}")
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
