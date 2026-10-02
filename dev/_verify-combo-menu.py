# -*- coding: utf-8 -*-
"""Vue 节点模式下打开 FallingTSLoadVideo 的 video 下拉, dump 弹窗结构。"""
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


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


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


def kill_browser(proc, profile):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
                    f"Where-Object {{ $_.CommandLine -like '*{profile}*' }} | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                   capture_output=True)


def main():
    base = "http://127.0.0.1:8188"
    edge = next((p for p in EDGE if pathlib.Path(p).is_file()), None)
    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="combo-"))
    proc = subprocess.Popen([edge, "--headless=new", f"--remote-debugging-port={port}",
                             f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                             "--disable-gpu", "--window-size=1800,1100", base + "/"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp = None
    failures = []
    probe_file = ROOT / "media" / "七纹刻印" / "0031_首帧场景" / "_probe_tmp_menu.mp4"

    def check(label, ok, detail=None):
        print(("PASS" if ok else "FAIL") + ": " + label, "" if detail is None else str(detail)[:220])
        if not ok:
            failures.append(label)

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
        cdp = CDP(ws_url)
        cdp.call("Runtime.enable")
        cdp.js("(async()=>{const t0=Date.now();while(Date.now()-t0<120000){"
               "if(window.app?.graph&&window.app.graph._nodes)return true;"
               "await new Promise(r=>setTimeout(r,300))}return false})()")
        wf = json.loads((ROOT / "workflows" / "0035_场景截帧.json").read_text(encoding="utf-8"))
        lit = json.dumps(json.dumps(wf, ensure_ascii=False))
        cdp.js(f"(async()=>{{ await app.loadGraphData(JSON.parse({lit})); return true }})()")
        time.sleep(5)

        cdp.js("window.__errs=[];window.addEventListener('error',e=>window.__errs.push(String(e.message)))")
        before = cdp.js("""
        (() => {
          const n = app.graph._nodes.find(x => x.type === 'FallingTSLoadVideo');
          const w = n.widgets.find(x => x.name === 'video');
          window.__pvNode = n; window.__pvWidget = w;
          w.refresh && w.refresh();
          return {values: (w.options?.values || []).slice(), count: (w.options?.values || []).length};
        })()
        """)
        time.sleep(1.2)
        print("刷新前候选数:", before.get("count"))

        # 造一个临时"视频"文件, 验证刷新按钮真的重新扫了目录
        src_video = ROOT / "media" / "七纹刻印" / "0031_首帧场景" / "00001_书房旋镜视频.mp4"
        probe_file.write_bytes(src_video.read_bytes())
        print("临时文件:", probe_file)

        # 采样: 打开下拉前后 options.values 长度与列表格子数
        cdp.js("""
        (() => {
          window.__samples = [];
          const t0 = Date.now();
          const timer = setInterval(() => {
            const w = window.__pvWidget;
            const menu = document.querySelector('[data-testid=form-dropdown-menu]');
            const cells = menu ? menu.querySelectorAll('[data-virtual-grid-item]').length : -1;
            window.__samples.push([Date.now() - t0, (w.options.values || []).length, cells]);
            if (Date.now() - t0 > 9000) clearInterval(timer);
          }, 250);
          return true;
        })()
        """)
        # 打开下拉
        opened = cdp.js("""
        (() => {
          const w = window.__pvWidget;
          const text = String(w.value || '').trim();
          const hit = [...document.querySelectorAll('*')].filter(el => el.children.length === 0 && (el.textContent||'').trim() === text);
          if (!hit.length) return {found: 0};
          const btn = hit[hit.length - 1].closest('button') || hit[hit.length - 1].parentElement;
          ['pointerdown','mousedown','pointerup','mouseup','click'].forEach((t, i) => setTimeout(() => {
            if (t === 'mousedown' || t === 'click') btn.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, button: 0}));
            else btn.dispatchEvent(new PointerEvent(t, {bubbles: true, cancelable: true, composed: true, pointerType: 'mouse', button: 0, buttons: t === 'pointerdown' ? 1 : 0}));
          }, i * 40));
          return {found: hit.length};
        })()
        """)
        check("combo 按钮可定位并点开", bool(opened.get("found")), opened)
        time.sleep(1.6)

        print("采样 [ms, values长度, 格子数]:", json.dumps(cdp.js("(window.__samples || [])"), ensure_ascii=False))
        state = cdp.js("""
        (() => {
          const pop = [...document.body.children].filter(e => e.className.toString().includes('absolute z-50')).pop();
          if (!pop) return {noPop: true};
          const menu = pop.querySelector('[data-testid=form-dropdown-menu]');
          if (!menu) return {noMenu: true};
          const refreshBtn = menu.querySelector('button.fallingts-combo-refresh');
          const sortBtn = [...menu.querySelectorAll('button')].find(b => /排序|sort/i.test((b.getAttribute('title')||'') + (b.getAttribute('aria-label')||'')));
          let order = 'n/a';
          if (refreshBtn && sortBtn) {
            order = (refreshBtn.compareDocumentPosition(sortBtn) & Node.DOCUMENT_POSITION_FOLLOWING) ? 'refresh-before-sort' : 'refresh-after-sort';
          }
          // 注入一个带 " [output]" 的假选项, 看是否被抹掉
          const list = menu.lastElementChild;
          const fake = document.createElement('div');
          fake.id = 'fallingts-fake-item';
          fake.textContent = '0035_场景截帧/00009_假资源.mp4 [output]';
          list.appendChild(fake);
          return {hasRefresh: !!refreshBtn, hasSort: !!sortBtn, order: order,
                  title: refreshBtn ? refreshBtn.getAttribute('title') : null};
        })()
        """)
        check("弹窗里有刷新按钮", state.get("hasRefresh"), state)
        check("刷新按钮在「排序方式」左侧", state.get("order") == "refresh-before-sort", state.get("order"))
        time.sleep(0.6)
        cleaned = cdp.js("(() => { const el = document.getElementById('fallingts-fake-item'); return el ? el.textContent : '(gone)'; })()")
        check("列表里的 ' [output]' 标注被抹掉", cleaned == "0035_场景截帧/00009_假资源.mp4", cleaned)

        # 点刷新按钮
        cdp.js("(() => { const b = document.querySelector('button.fallingts-combo-refresh'); if (b) b.click(); return !!b; })()")
        time.sleep(4.5)
        diag = cdp.js("""
        (() => {
          const w = window.__pvWidget;
          const text = String(w.value || '').trim();
          const btns = [...document.querySelectorAll('button')].filter(b => (b.textContent||'').trim() === text);
          const pop = [...document.body.children].filter(e => e.className.toString().includes('absolute z-50')).pop();
          return {popExists: !!pop, btnCount: btns.length, btnInDoc: btns.map(b => document.body.contains(b)),
                  openAttr: pop ? (pop.getAttribute('style')||'').slice(0,60) : null};
        })()
        """)
        print("诊断(刷新后):", json.dumps(diag, ensure_ascii=False))
        after = cdp.js("""
        (() => {
          const w = window.__pvWidget;
          const values = (w.options?.values || []);
          const pop = [...document.body.children].filter(e => e.className.toString().includes('absolute z-50')).pop();
          const menu = pop ? pop.querySelector('[data-testid=form-dropdown-menu]') : null;
          const listed = menu ? (menu.innerText || '').includes('_probe_tmp_menu.mp4') : null;
          return {count: values.length, hasProbe: values.includes('0031_首帧场景/_probe_tmp_menu.mp4'), listed: listed,
                  sample: values.slice(0, 4)};
        })()
        """)
        check("刷新后候选含新文件(重新扫了目录)", bool(after.get("hasProbe")), after)
        samples = cdp.js("(window.__samples || [])")
        closed_at = next((i for i, row in enumerate(samples) if row[2] == -1), -1)
        reopened = closed_at >= 0 and any(row[2] >= 0 for row in samples[closed_at:])
        check("刷新后弹窗被关闭又重新打开(让列表用新候选重算)", reopened, samples[-6:] if samples else samples)
        check("控件值仍无 [output] 标注", not any('[output]' in str(v) for v in (after.get("sample") or [])), after.get("sample"))

        # 老工作流里带标注的值应被清洗
        clean = cdp.js("""
        (() => {
          const w = window.__pvWidget;
          w.value = '0031_首帧场景/00001_书房旋镜视频.mp4 [output]';
          const now = w.value;
          w.value = '0031_首帧场景/00001_书房旋镜视频.mp4';
          return now;
        })()
        """)
        check("写进 widget 的值也被清洗", clean == "0031_首帧场景/00001_书房旋镜视频.mp4", clean)



        errs = cdp.js("(window.__errs || []).slice(-5)")
        check("无前端 JS 报错", not errs, errs)
    finally:
        try:
            cdp.close()
        except Exception:
            pass
        kill_browser(proc, profile)
        if probe_file.exists():
            probe_file.unlink()
            print("已删除临时文件")

    print()
    print("FAILURES:", failures if failures else "无 (ALL PASS)")
    return 1 if failures else 0


sys.exit(main())
