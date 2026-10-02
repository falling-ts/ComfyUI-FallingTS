"""验证「加载视频」截帧的懒解码兜底: 没跑过节点也能按前端播放位置截帧。

背景(2026-10-02): 用户点「截帧」报「没有可截帧的视频数据, 请先运行到该节点」——
帧缓存只在进程内存里(重启 ComfyUI / 刚选好或上传视频还没执行时为空), 而前端播放器
已经能播放。修复后截帧路由按请求带来的 video 值现场拆帧(懒解码)再取帧。

做法: 起一个临时实例(随机端口 + 独立数据库, 不影响 8188), 只发 HTTP 验证:
  ① 无缓存 + 带 video → 200, 帧号 = round(秒数 x fps) + 1
  ② 同位置重复截 → 400「已在选中列表中」(追加语义仍在)
  ③ 带不存在的 video → 400 且提示具体
  ④ 无 video 且无缓存 → 400 且提示「请在节点里选择或上传视频」
  ⑤ mode=frame 直接按帧号取 → 200 且帧号一致
  ⑥ /state 反映懒解码建好的缓存(total_frames / selected_frames)
  ⑦ save_frames 懒解码兜底 → 产物落临时子目录(测完删除)

用法: .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-load-video-lazy-frame.py
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
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
VIDEO = "0031_首帧场景/00001_书房旋镜视频.mp4"
EXPECT_FPS = 24
TMP_DIR_NAME = "_verify_lazy_frame_tmp"

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


def post(url: str, payload: dict) -> tuple[int, dict, dict]:
    """POST JSON, 返回 (状态码, 响应头, 解析后的 JSON 或 {})。"""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            body = r.read()
            try:
                parsed = json.loads(body.decode("utf-8"))
            except Exception:
                parsed = {}
            return r.status, dict(r.headers), parsed
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:
            parsed = {}
        return e.code, dict(e.headers), parsed


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


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


def main() -> int:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    db = pathlib.Path(tempfile.gettempdir()) / f"fallingts-lazy-{port}.db"
    log = pathlib.Path(tempfile.gettempdir()) / f"fallingts-lazy-{port}.log"
    out_dir = ROOT / "media" / "七纹刻印" / TMP_DIR_NAME

    env_log = open(log, "wb")
    proc = subprocess.Popen(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), "main.py",
         "--cpu", "--port", str(port), "--disable-pinned-memory",
         "--database-url", f"sqlite:///{db.as_posix()}"],
        cwd=str(ROOT / "ComfyUI"), stdout=env_log, stderr=subprocess.STDOUT,
    )
    print(f"临时实例: pid={proc.pid} port={port} 日志={log}")
    try:
        if not wait_http(base + "/system_stats", 300):
            print("临时实例未就绪; 日志尾部:")
            print(log.read_text(encoding="utf-8", errors="replace")[-3000:])
            return 2

        url = base + "/fallingts_load_video/frame/18"

        # ① 无缓存 + 带 video → 懒解码取帧
        status, headers, body = post(url, {
            "position_seconds": 5.0, "video": VIDEO, "name": "懒解码", "sequence": "00007",
        })
        fno = headers.get("X-Frame-Index")
        check("① 无缓存 + video → 200", status == 200, {"status": status, "body": body})
        check("① 帧号 = round(5s x 24fps) + 1 = 121", str(fno) == "121", {"X-Frame-Index": fno})

        # ② 同位置重复截 → 400 已在列表
        status2, _, body2 = post(url, {"position_seconds": 5.0, "video": VIDEO})
        check("② 重复截同帧 → 400 已在选中列表", status2 == 400 and "已在选中列表" in str(body2.get("message", "")),
              {"status": status2, "message": body2.get("message")})

        # ③ 不存在的 video → 400 且提示具体
        status3, _, body3 = post(base + "/fallingts_load_video/frame/17", {"position_seconds": 1.0, "video": "不存在/没有这个.mp4"})
        check("③ 不存在的 video → 400 找不到文件", status3 == 400 and "找不到视频文件" in str(body3.get("message", "")),
              {"status": status3, "message": body3.get("message")})

        # ④ 无 video 且无缓存 → 400 提示选择/上传
        status4, _, body4 = post(base + "/fallingts_load_video/frame/16", {"position_seconds": 1.0})
        check("④ 无 video 无缓存 → 400 提示选择或上传", status4 == 400 and "选择或上传视频" in str(body4.get("message", "")),
              {"status": status4, "message": body4.get("message")})

        # ⑤ mode=frame 按帧号取
        status5, headers5, _ = post(url, {"mode": "frame", "frame_index": 10, "append": False, "video": VIDEO})
        check("⑤ mode=frame 取第 10 帧", status5 == 200 and headers5.get("X-Frame-Index") == "10",
              {"status": status5, "X-Frame-Index": headers5.get("X-Frame-Index")})

        # ⑥ /state 反映懒解码缓存
        st = get_json(base + "/fallingts_load_video/state/18")
        check("⑥ /state: 243 帧 + 已选 [121]", st.get("total_frames") == 243 and st.get("selected_frames") == [121],
              st)

        # ⑥b 懒解码同时编码了 temp 预览 → preview-url 可用(页面刷新后播放器能重建)
        pv = get_json(base + "/fallingts_load_video/preview-url/18")
        url_path = pv.get("url") or ""
        status_pv, ctype = 0, ""
        if pv.get("status") == "ok" and url_path:
            with urllib.request.urlopen(base + url_path, timeout=60) as pr:
                status_pv = pr.status
                ctype = pr.headers.get("Content-Type", "")
                pr.read(64)
        check("⑥b 懒解码后有可播放预览 URL", status_pv == 200 and "video" in ctype,
              {"preview": pv, "status": status_pv, "content_type": ctype})

        # ⑥c 「完成」能置位(懒解码已建好 selected_frames, 后端据此放行下游)
        s6, _, b6 = post(base + "/fallingts_load_video/done/18", {"frames": [121]})
        check("⑥c 懒解码后「完成」置位", s6 == 200 and b6.get("done") is True,
              {"status": s6, "done": b6.get("done")})

        # ⑦ save_frames 懒解码兜底(写进临时子目录, 测完删)
        status7, _, body7 = post(base + "/fallingts_load_video/save_frames/18", {
            "frames": [121], "sequence": 0, "name": "懒解码", "dir": TMP_DIR_NAME,
        })
        saved_ok = status7 == 200 and (out_dir / "00000_懒解码.png").is_file()
        check("⑦ save_frames 懒解码 → 产物落临时目录", saved_ok,
              {"status": status7, "message": body7.get("message"), "saved": body7.get("saved")})

        size = (out_dir / "00000_懒解码.png").stat().st_size if saved_ok else 0
        check("⑦ 产物是有效 PNG(>10KB)", size > 10_000, {"bytes": size})
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        env_log.close()
        if out_dir.is_dir():
            shutil.rmtree(out_dir, ignore_errors=True)
        for p in (db, log):
            try:
                p.unlink()
            except OSError:
                pass

    print(f"\n{'全部通过' if not FAILURES else '失败 ' + str(len(FAILURES)) + ' 项: ' + ', '.join(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
