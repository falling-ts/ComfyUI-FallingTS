
"""验收: 两个加载节点的下拉候选「点开即最新」+ 加载图像的序列号。

背景(2026-10-02): 用户反馈"点开下拉不显示子目录资源 / 第一次不显示"。根因是候选只在
① NodeDef 注册 ② 点刷新按钮 ③ 跑完 Auto-refresh 三个时机拉, 而"点开下拉"那一下前端
不拉我们的 remote 候选(它只刷新「已保存」那份资产列表)。修法两半:
- 后端: 加载图像的 INPUT_TYPES 也现扫一份 options(与加载视频的 define_schema 同口径);
- 前端: web/js/load_combo_refresh.js 在 节点创建 / 按下鼠标 / 每 4 秒 三个时机拉 remote。

本脚本用无头 Edge + CDP 真跑前端逐项验收。用法:
    .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-load-dropdown.py [BASE_URL]
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
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8188").rstrip("/")
WF_IMAGE = ROOT / "workflows" / "0010_灰度遮罩.json"
WF_VIDEO = ROOT / "workflows" / "0035_场景截帧.json"

EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"]

FAILURES: list[str] = []


def check(label, ok, detail=None):
    print(("PASS" if ok else "FAIL") + ": " + label)
    if detail is not None:
        print("      " + json.dumps(detail, ensure_ascii=False)[:400])
    if not ok:
        FAILURES.append(label)


class CDP:
    def __init__(self, ws):
        self.ws = connect(ws, max_size=None, open_timeout=30)
        self.seq = 0

    def call(self, method, params=None):
        self.seq += 1
        mid = self.seq
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                return msg.get("result", {})

    def js(self, expr):
        for _ in range(25):
            try:
                res = self.call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
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

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def kill_browser(proc, profile):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | "
                    "Where-Object { $_.CommandLine -like '*" + str(profile) + "*' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                   capture_output=True)


def main():
    # 控制台按 UTF-8 输出: 标签里有中文, 默认 cp936 会 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8")
    exe = next((p for p in EDGE if pathlib.Path(p).is_file()), None)
    if exe is None:
        print("找不到 Edge/Chrome")
        return 2

    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="loaddrop-"))
    proc = subprocess.Popen([exe, "--headless=new", "--remote-debugging-port=" + str(port),
                             "--user-data-dir=" + str(profile), "--no-first-run", "--disable-gpu",
                             "--window-size=1600,1000", BASE + "/"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp = None
    try:
        ws = None
        for _ in range(120):
            try:
                with urllib.request.urlopen("http://127.0.0.1:" + str(port) + "/json/list", timeout=3) as r:
                    for t in json.loads(r.read().decode()):
                        if t.get("type") == "page" and t.get("url", "").startswith(BASE):
                            ws = t["webSocketDebuggerUrl"]
                            break
                if ws:
                    break
            except Exception:
                pass
            time.sleep(1)
        if not ws:
            print("拿不到 CDP page target")
            return 2
        cdp = CDP(ws)
        cdp.call("Runtime.enable")
        ready = cdp.js("(async()=>{const t0=Date.now();while(Date.now()-t0<120000){"
                       "if(window.app?.graph&&window.LiteGraph?.registered_node_types?.FallingTSLoadImage"
                       "&&window.LiteGraph?.registered_node_types?.FallingTSLoadVideo)return true;"
                       "await new Promise(r=>setTimeout(r,300))}return false})()")
        check("前端与两个加载节点就绪", ready is True)

        # 共用模块真的能被前端取到(它被两个 js 以相对路径 import)
        exts = cdp.js("(async()=>{"
                      "const r=await fetch('/extensions/ComfyUI-FallingTS/js/load_combo_refresh.js');"
                      "const t=await r.text();"
                      "return { status: r.status, hasExport: t.includes('export function armComboRefresh') }})()")
        check("load_combo_refresh.js 可访问且导出了 armComboRefresh",
              bool(exts) and exts.get("status") == 200 and exts.get("hasExport") is True, exts)

        for wf_path, ntype, combo_name in ((WF_IMAGE, "FallingTSLoadImage", "image"),
                                           (WF_VIDEO, "FallingTSLoadVideo", "video")):
            wf = json.loads(wf_path.read_text(encoding="utf-8"))
            cdp.js("(async()=>{await app.loadGraphData(JSON.parse(" + json.dumps(json.dumps(wf, ensure_ascii=False)) + "));return 1})()")
            time.sleep(5)
            info = cdp.js("""
            (() => {
              const n = app.graph._nodes.find(x => x.type === '%s');
              if (!n) return { error: '节点不存在' };
              const w = n.widgets.find(x => x.name === '%s');
              const seq = n.widgets.find(x => x.name === 'sequence');
              return {
                names: n.widgets.map(x => x.name),
                imageOptions: w?.options?.values ?? null,
                imageValue: w?.value ?? null,
                hasRefreshFn: typeof w?.refresh === 'function',
                armed: w?._fallingtsComboArmed === true,
                seqValue: seq?.value ?? null,
              };
            })()
            """ % (ntype, combo_name))
            if info and info.get("error"):
                check(wf_path.name + " 里找到 " + ntype, False, info)
                continue
            check(wf_path.name + " 里找到 " + ntype, True)
            opts = info.get("imageOptions") or []
            check(ntype + ": 候选非空且含子目录项", len(opts) > 0 and any("/" in str(v) for v in opts), opts)
            check(ntype + ": combo 已装上自动刷新(armed)", info.get("armed") is True, info)
            if ntype == "FallingTSLoadImage":
                check("加载图像: 有 sequence 控件", "sequence" in (info.get("names") or []), info.get("names"))
                check("加载图像: 有「刷新序列号」按钮", "刷新序列号" in (info.get("names") or []), info.get("names"))
                check("加载图像: 序列号自动填成 5 位文本",
                      isinstance(info.get("seqValue"), str) and len(info.get("seqValue")) == 5, info.get("seqValue"))

                # 用户口径: 序列号跟着「当前工作流名所在的目录」走。0010_灰度遮罩/ 里已有
                # 00001_陈落换衣服.png ⇒ 下一个可用号是 00002。
                # (无头 loadGraphData 注入的图没有工作流名, 故这里先尽力给活动工作流命名,
                #  命名失败时退回用路由的 dir 参数直接验证后端目录解析。)
                seqdir = cdp.js("""
                (async () => {
                  const wf = app.extensionManager?.workflow?.activeWorkflow;
                  const out = { before: wf?.name ?? null };
                  try { if (wf) wf.name = '0010_灰度遮罩'; } catch (err) { out.setError = String(err); }
                  out.after = wf?.name ?? null;
                  const n = app.graph._nodes.find(x => x.type === 'FallingTSLoadImage');
                  const btn = n?.widgets?.find(w => w.name === '刷新序列号');
                  if (btn?.callback) btn.callback();
                  await new Promise(r => setTimeout(r, 2500));
                  out.seq = n?.widgets?.find(w => w.name === 'sequence')?.value;
                  const r = await fetch('/fallingts_load_image/next_sequence?workflow_name=' +
                                        encodeURIComponent('0010_灰度遮罩'));
                  out.route = await r.json();
                  return out;
                })()
                """)
                named = isinstance(seqdir, dict) and seqdir.get("after") == "0010_灰度遮罩"
                if named:
                    check("序列号跟着当前工作流名的目录走(0010_灰度遮罩 -> 00002)",
                          seqdir.get("seq") == "00002", seqdir)
                else:
                    route = (seqdir or {}).get("route") or {}
                    print("[info] 无头环境改不动活动工作流名, 改用路由 dir 口径验证: "
                          + json.dumps(seqdir, ensure_ascii=False)[:200])
                    check("序列号目录解析: 0010_灰度遮罩 已有 00001 -> 2",
                          route.get("sequence") == 2, route)

        # 行为验证: 轮询真的在拉候选(给 refresh 打点, 等 6 秒)
        tick = cdp.js("""
        (async () => {
          const n = app.graph._nodes.find(x => x.type === 'FallingTSLoadVideo');
          const w = n.widgets.find(x => x.name === 'video');
          let cnt = 0;
          const orig = w.refresh.bind(w);
          w.refresh = function () { cnt += 1; return orig.apply(null, arguments); };
          await new Promise(r => setTimeout(r, 6500));
          w.refresh = orig;
          return cnt;
        })()
        """)
        check("兜底轮询在 6.5 秒内至少拉了一次候选", isinstance(tick, int) and tick >= 1, tick)

        # 行为验证: 新拖入的节点, 候选在创建后立刻就有(不是"第一次点开是空的")
        fresh = cdp.js("""
        (async () => {
          const n = LiteGraph.createNode('FallingTSLoadImage');
          app.graph.add(n);
          await new Promise(r => setTimeout(r, 1500));
          const w = n.widgets.find(x => x.name === 'image');
          const seq = n.widgets.find(x => x.name === 'sequence');
          const out = { values: (w?.options?.values || []).length, armed: w?._fallingtsComboArmed === true,
                        seq: seq?.value ?? null, widgets: n.widgets.map(x => x.name) };
          app.graph.remove(n);
          return out;
        })()
        """)
        check("新建的加载图像节点候选立刻非空(无需先点刷新)",
              isinstance(fresh, dict) and (fresh.get("values") or 0) > 0, fresh)
        check("新建的加载图像节点也装上了自动刷新", isinstance(fresh, dict) and fresh.get("armed") is True, fresh)
        check("新建的加载图像节点自动取了序列号", isinstance(fresh, dict) and isinstance(fresh.get("seq"), str), fresh)
    finally:
        if cdp is not None:
            cdp.close()
        kill_browser(proc, profile)

    print()
    if FAILURES:
        print("FAILED: " + str(len(FAILURES)) + " 项 -> " + str(FAILURES))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
