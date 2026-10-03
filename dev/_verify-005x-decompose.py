# -*- coding: utf-8 -*-
"""验收: 0050/0051 重构 + 0035 端口迁移 + 0040..0044 尾部清空(真实前端 + 8189 新节点代码)。

用法(工作区根): .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-005x-decompose.py
前提: 另起一个临时实例(带新代码)在 8189:
  cd ComfyUI && D:/AI/Comfy/.venv/Scripts/python.exe main.py --cpu --port 8189 --disable-pinned-memory
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

FAILURES = []


def check(label, ok, detail=None):
    print(("PASS" if ok else "FAIL") + ": " + label, "" if detail is None else str(detail)[:200])
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


LOADER_JS = """
window.__loadWf = async (wf) => {
  app.graph.clear();
  await app.loadGraphData(wf);
  await new Promise(r => setTimeout(r, 900));
  const g = app.graph;
  const nodes = g._nodes || [];
  const nm = n => (n.title || n.type);
  const links = Object.values(g.links || {}).map(l => {
    const a = g.getNodeById(l.origin_id), b = g.getNodeById(l.target_id);
    return {
      fromType: a ? a.type : "?", fromTitle: a ? nm(a) : "?",
      fromOut: a ? (a.outputs?.[l.origin_slot]?.name ?? "") : "",
      toType: b ? b.type : "?", toTitle: b ? nm(b) : "?",
      toIn: b ? (b.inputs?.[l.target_slot]?.name ?? "") : "",
    };
  });
  return {
    nodes: nodes.length,
    links: links,
    nodeList: nodes.map(n => ({
      id: n.id, type: n.type, title: nm(n),
      outputs: (n.outputs || []).map(o => o.name),
      inputs: (n.inputs || []).map(i => i.name),
      widgets: Object.fromEntries((n.widgets || []).map(w => [w.name, w.value])),
    })),
  };
};
"""


def load(cdp, wf_name):
    wf = json.loads((ROOT / "workflows" / (wf_name + ".json")).read_text(encoding="utf-8"))
    lit = json.dumps(json.dumps(wf, ensure_ascii=False))
    return cdp.js("(async()=>{ return await window.__loadWf(JSON.parse(" + lit + ")); })()")


def nodes_of(dump, node_type):
    return [n for n in dump["nodeList"] if n["type"] == node_type]


def link(dump, **kw):
    found = [l for l in dump["links"] if all(l.get(k) == v for k, v in kw.items())]
    return found


def post(path, payload):
    """POST JSON 到 8189(400 时把 body 回给调用方看)。"""
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode()[:600]}


def get(path):
    """GET JSON。"""
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode())


def check_video_in_end_to_end():
    """后端: video_in 连线时提交不该被误判成「Invalid video file」(0050/0051 走的就是这条路)。

    校验阶段连线的输入拿不到值, 若只判断 video_in 是否为 None, "下拉为空 + video_in 接线"
    的图会被整次拦掉 —— 这里用核心 LoadVideo 造一个 VIDEO 源接进 video_in, 验证提交被接受、
    且本节点正常执行(未「完成」→ 阻断下游但预览照发)。
    """
    probe = ROOT / "media" / "七纹刻印" / "_probe_video_in.mp4"
    source = ROOT / "media" / "七纹刻印" / "0031_首帧场景" / "00001_书房旋镜视频.mp4"
    if not source.is_file():
        print("SKIP video_in 用例: 找不到源视频", source)
        return
    probe.write_bytes(source.read_bytes())
    try:
        prompt = {
            "1": {"class_type": "LoadVideo", "inputs": {"file": probe.name}},
            "2": {"class_type": "FallingTSLoadVideo",
                  "inputs": {"video_in": ["1", 0], "video": "", "name": "拆帧探针", "sequence": "7"}},
            # 3: 核心 PreviewAny 把 prefix 回显到 history 的 ui.text(端到端验证「序列号_名称」)
            "3": {"class_type": "PreviewAny", "inputs": {"source": ["2", 2]}},
        }
        res = post("/prompt", {"prompt": prompt, "client_id": "verify-005x"})
        body = str(res.get("_body") or "")
        check("video_in 图提交未被「Invalid video file」拦掉",
              bool(res.get("prompt_id")) and "Invalid video file" not in body, res)
        pid = res.get("prompt_id")
        if pid:
            hist = None
            for _ in range(60):
                time.sleep(2)
                h = get("/history/" + pid)
                if pid in h:
                    hist = h[pid]
                    break
            outs = (hist or {}).get("outputs") or {}
            check("video_in 图执行成功(未完成 → 预览照发)",
                  (hist or {}).get("status", {}).get("status_str") == "success"
                  and bool(outs.get("2", {}).get("images")),
                  {"status": (hist or {}).get("status", {}).get("status_str"), "node2": outs.get("2")})
            text = ((outs.get("3") or {}).get("text") or [None])[0]
            check("加载视频的 prefix 输出 = 序列号_名称", text == "00007_拆帧探针", text)
    finally:
        probe.unlink(missing_ok=True)


def check_prefix_save_end_to_end():
    """后端: 连线来的「序列号_名称」前缀真的进了保存文件名。

    前缀链路 = 加载节点 prefix 输出 → 保存节点 filename_prefix 输入 → execute 时收到该值 →
    点「保存」时前端带 filename_prefix_linked=true, 后端改用 execute 时缓存的值(忽略控件值)。
    这里模拟前端: body 里的 filename_prefix 故意写错, 断言落盘文件名是 <序列号>_<名称><后缀>.png。
    """
    from PIL import Image as _Image

    png = ROOT / "media" / "七纹刻印" / "_probe_prefix.png"
    wav = ROOT / "media" / "七纹刻印" / "_probe_audio_in.wav"
    if not wav.is_file():
        print("SKIP 前缀落盘用例: 缺探针音频", wav)
        return
    _Image.new("RGB", (8, 8), (10, 20, 30)).save(png)
    out_dir = ROOT / "media" / "七纹刻印" / "0050_视频拆帧"
    target = out_dir / "00007_前缀探针_首帧.png"
    target.unlink(missing_ok=True)
    try:
        prompt = {
            "1": {"class_type": "LoadAudio", "inputs": {"audio": wav.name}},
            "2": {"class_type": "FallingTSLoadAudio",
                  "inputs": {"audio_in": ["1", 0], "audio": "", "name": "前缀探针", "sequence": "7"}},
            "3": {"class_type": "LoadImage", "inputs": {"image": png.name}},
            # filename_prefix 由「加载音频」的 prefix 输出连线供给(控件值只剩占位)
            "4": {"class_type": "PreviewImageSave",
                  "inputs": {"images": ["3", 0], "filename_prefix": ["2", 1], "filename_suffix": "_首帧",
                             "format": "png", "bit_depth": "8-bit", "input_color_space": "sRGB"}},
        }
        res = post("/prompt", {"prompt": prompt, "client_id": "verify-005x"})
        pid = res.get("prompt_id")
        check("前缀落盘: 图提交", bool(pid), res)
        if not pid:
            return
        for _ in range(60):
            time.sleep(2)
            if pid in get("/history/" + pid):
                break
        body = {"filename_prefix": "控件值应被忽略", "filename_suffix": "_首帧",
                "filename_prefix_linked": True, "filename_suffix_linked": False,
                "workflow_name": "0050_视频拆帧", "format": "png", "bit_depth": "8-bit",
                "input_color_space": "sRGB"}
        saved = post("/preview-image/save/4", body)
        check("前缀落盘: 文件名 = 00007_前缀探针_首帧.png",
              saved.get("status") == "ok" and target.is_file(),
              {"resp": str(saved)[:180], "file": target.is_file()})
    finally:
        png.unlink(missing_ok=True)
        target.unlink(missing_ok=True)


def main():
    check_video_in_end_to_end()
    check_prefix_save_end_to_end()
    edge = next((p for p in EDGE if pathlib.Path(p).is_file()), None)
    port = free_port()
    profile = pathlib.Path(tempfile.mkdtemp(prefix="verify005x-"))
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
        cdp.js(LOADER_JS)
        cdp.js("window.__errs=[];window.addEventListener('error',e=>window.__errs.push(String(e.message)))")

        # ── 0050_视频拆帧 ──────────────────────────────────────────────
        d = load(cdp, "0050_视频拆帧")
        check("0050 节点构成 = 加载视频 + 3 预览保存 + 说明(无数据表)",
              len(nodes_of(d, "FallingTSLoadVideo")) == 1 and len(nodes_of(d, "PreviewImageSave")) == 3
              and not nodes_of(d, "FallingTSMarkDownTable") and not nodes_of(d, "Reroute"),
              "%d 节点 / %d 连线" % (d["nodes"], len(d["links"])))
        lv = nodes_of(d, "FallingTSLoadVideo")[0]
        check("0050 加载视频输出 = video/audio/prefix/选中帧1..3",
              lv["outputs"] == ["video", "audio", "prefix", "image_1", "image_2", "image_3"], lv["outputs"])
        check("0050 输出帧数 = 3", lv["widgets"].get("输出帧数") == 3, lv["widgets"].get("输出帧数"))
        ok = all(len(link(d, fromType="FallingTSLoadVideo", fromOut="image_%d" % i, toType="PreviewImageSave", toIn="images")) == 1
                 for i in (1, 2, 3))
        check("0050 选中帧 1..3 → 三个预览保存", ok)
        check("0050 加载视频 prefix → 三个 filename_prefix",
              len(link(d, fromType="FallingTSLoadVideo", fromOut="prefix", toType="PreviewImageSave", toIn="filename_prefix")) == 3)
        check("0050 保存节点标题", sorted(n["title"] for n in nodes_of(d, "PreviewImageSave")) == ["预览保存-关键帧", "预览保存-尾帧", "预览保存-首帧"])

        # ── 0051_视频拆音 ──────────────────────────────────────────────
        d = load(cdp, "0051_视频拆音")
        check("0051 节点构成 = 加载视频 + 截段 + 3 预览音频 + 说明(无数据表)",
              len(nodes_of(d, "FallingTSLoadVideo")) == 1 and len(nodes_of(d, "FallingTSAudioTrim")) == 1
              and len(nodes_of(d, "PreviewAudioSave")) == 3 and not nodes_of(d, "FallingTSMarkDownTable"),
              "%d 节点 / %d 连线" % (d["nodes"], len(d["links"])))
        check("0051 加载视频 audio → 音频截段",
              len(link(d, fromType="FallingTSLoadVideo", fromOut="audio", toType="FallingTSAudioTrim", toIn="audio")) == 1)
        check("0051 截段 1..3 → 三个预览音频",
              all(len(link(d, fromType="FallingTSAudioTrim", fromOut="audio_%d" % i, toType="PreviewAudioSave", toIn="audio")) == 1 for i in (1, 2, 3)))
        check("0051 加载视频 prefix → 截段 + 三个预览音频的 filename_prefix",
              len(link(d, fromType="FallingTSLoadVideo", fromOut="prefix", toIn="filename_prefix")) == 4,
              [l["toType"] for l in link(d, fromType="FallingTSLoadVideo", fromOut="prefix", toIn="filename_prefix")])
        tr = nodes_of(d, "FallingTSAudioTrim")[0]
        check("0051 音频截段输出段数 = 3", tr["widgets"].get("输出段数") == 3, tr["widgets"].get("输出段数"))

        # ── 0035_场景截帧(端口从 slot1 起后移一位) ─────────────────────
        d = load(cdp, "0035_场景截帧")
        lv = nodes_of(d, "FallingTSLoadVideo")[0]
        check("0035 加载视频输出 = video/audio/prefix/选中帧1..8",
              lv["outputs"] == ["video", "audio", "prefix"] + ["image_%d" % i for i in range(1, 9)], lv["outputs"])
        want = ["单图 前面", "单图 前右", "单图 右面", "单图 后右", "单图 后面", "单图 后左", "单图 左面", "单图 前左"]
        got = []
        for i in range(1, 9):
            hit = link(d, fromType="FallingTSLoadVideo", fromOut="image_%d" % i, toType="PreviewImageSave", toIn="images")
            got.append(hit[0]["toTitle"] if hit else "(无)")
        check("0035 八个选中帧仍落在八个单图保存", got == want, got)
        pref = link(d, fromType="FallingTSLoadVideo", fromOut="prefix", toType="PreviewImageSave", toIn="filename_prefix")
        check("0035 加载视频 prefix → 十个保存节点", len(pref) == 10, [l["toTitle"] for l in pref])

        # ── 0040..0044 尾部清空 ────────────────────────────────────────
        expect_counts = {"0040_文生视频": 27, "0041_首帧视频": 26, "0042_首尾视频": 26,
                         "0043_关键帧视频": 42, "0044_参考视频": 30}
        for wf_name, want_nodes in expect_counts.items():
            d = load(cdp, wf_name)
            tail_types = [n["type"] for n in d["nodeList"] if n["type"] in ("FallingTSAudioTrim", "PreviewAudioSave", "PreviewImageSave")]
            check("%s 截帧/截音尾部已清空" % wf_name, not tail_types, tail_types)
            pv = nodes_of(d, "PreviewVideo")
            check("%s 预览视频只剩 video 输出" % wf_name, len(pv) == 1 and pv[0]["outputs"] == ["video"],
                  pv[0]["outputs"] if pv else "无 PreviewVideo")
            got = link(d, toType="PreviewVideo", toIn="filename_prefix")
            check("%s 预览视频文件名前缀 ← MD 表 ID" % wf_name,
                  len(got) == 1 and got[0]["fromType"] == "FallingTSMarkDownTable" and got[0]["fromOut"] == "ID",
                  got)
            check("%s 节点数不变(仅删尾部)" % wf_name, d["nodes"] == want_nodes, d["nodes"])

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
