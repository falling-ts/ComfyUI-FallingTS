# dev/_verify-load-image.py
"""离线自检: 加载图像节点的下拉扫描 + 遮罩成品自增编号命名。

用法(工作区根):
    .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-load-image.py

覆盖:
1. _collect_output_items: output 根图片 + 数字目录内部图片(含嵌套), 排除非数字目录
   (clipspace)与非图片; 按 mtime 倒序;
2. _next_numbered_base: 已有 00001_/00003_ → 下一个 00004_;
3. /fallingts_mask/rename 带 name: 成品写成 0010_灰度遮罩/00004_名称.png;
   不带 name 时保持旧口径(仍按传入 base 命名)。
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
PLUGIN_DIR = Path(__file__).resolve().parent.parent
# ComfyUI 根(folder_paths / comfy / torch 等核心包都在这里)
sys.path.insert(0, str(ROOT / "ComfyUI"))
sys.path.insert(0, str(PLUGIN_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ─── 桩掉 server(模块导入期会取 PromptServer.instance.routes) ───────────────────


class _Routes:
    def get(self, _path):
        return lambda fn: fn

    def post(self, _path):
        return lambda fn: fn


class _Router:
    def routes(self):
        return []


class _App:
    def __init__(self):
        self.router = _Router()
        self.on_startup = []

    def add_routes(self, _routes):
        pass


class _PromptServer:
    instance = None

    def __init__(self):
        self.routes = _Routes()
        self.app = _App()


_PromptServer.instance = _PromptServer()
_server = types.ModuleType("server")
_server.PromptServer = _PromptServer
sys.modules["server"] = _server

import folder_paths  # noqa: E402  (必须在桩之后)

from importlib import import_module  # noqa: E402

load_image = import_module("load-image.nodes")
mask_rename = import_module("mask-rename.nodes")

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def _touch(path: Path, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    import os

    os.utime(path, (mtime, mtime))


# ─── 1) 下拉扫描 ─────────────────────────────────────────────────────────────

# ⚠️ 临时目录不能落系统 %TEMP%(DSH 沙箱下 mkdir 会被拒), 用工作区内的临时目录
(ROOT / "scripts").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=str(ROOT / "scripts")) as tmp:
    out_dir = Path(tmp) / "output"
    now = time.time()
    _touch(out_dir / "封面.png", now - 100)
    _touch(out_dir / "clipspace" / "clipspace-painted-masked-1.png", now)   # 非数字目录: 排除
    _touch(out_dir / "0010_灰度遮罩" / "00001_手部.png", now - 10)
    _touch(out_dir / "0010_灰度遮罩" / "旧文件.txt", now - 20)                # 非图片: 排除
    _touch(out_dir / "0010_灰度遮罩" / "子层" / "00002_脚部.png", now - 5)     # 数字目录内部可再分层
    _touch(out_dir / "0011_万物建模" / "00001_陈落.png", now - 30)
    _touch(out_dir / ".隐藏.png", now - 1)                                    # 隐藏: 排除

    items = load_image._collect_output_items(str(out_dir))
    items.sort(key=lambda item: -item[0])
    names = [value for _, value in items]
    print("扫描结果:", names)

    check("根目录图片被收录", "封面.png" in names)
    check("数字目录图片带子目录前缀", "0010_灰度遮罩/00001_手部.png" in names)
    check("数字目录内部可再分层", "0010_灰度遮罩/子层/00002_脚部.png" in names)
    check("多数字目录都能收录", "0011_万物建模/00001_陈落.png" in names)
    check("非数字目录被排除", not any("clipspace" in n for n in names))
    check("非图片被排除", not any(n.endswith(".txt") for n in names))
    check("隐藏文件被排除", not any(".隐藏" in n for n in names))
    check("按 mtime 倒序", names[0] == "0010_灰度遮罩/子层/00002_脚部.png", names[0] if names else "(空)")

    # ─── 2) 自增编号 ─────────────────────────────────────────────────────────
    numbered_dir = out_dir / "0010_灰度遮罩"
    (numbered_dir / "00003_旧名.png").write_bytes(b"x")
    check("编号 = 已有最大值 + 1", mask_rename._next_numbered_base(str(numbered_dir), "手部") == "00004_手部")
    check("空目录从 00001 开始", mask_rename._next_numbered_base(str(out_dir / "不存在"), "甲") == "00001_甲")
    check("撞号顺延", mask_rename._next_numbered_base(str(numbered_dir), "00004_手部".split("_", 1)[1]) == "00004_手部")

    # ─── 3) 改名路由 ─────────────────────────────────────────────────────────
    old_input, old_output = folder_paths.get_input_directory, folder_paths.get_output_directory
    folder_paths.get_input_directory = lambda: str(out_dir)
    folder_paths.get_output_directory = lambda: str(out_dir)
    try:
        ts = int(time.time() * 1000)
        src = out_dir / "clipspace" / f"clipspace-painted-masked-{ts}.png"
        _touch(src, time.time())

        class _Req:
            def __init__(self, data):
                self._data = data

            async def json(self):
                return self._data

        resp = asyncio.run(mask_rename._rename_mask(_Req({
            "node_id": "1", "image_ref": src.name, "name": "手部",
        })))
        body = json.loads(resp.body.decode("utf-8"))
        out_name = body.get("out_ref", {}).get("filename", "")
        check("带名称的成品按 0000N_名称 命名", body.get("ok") and out_name == "00004_手部.png", str(body))
        check("成品确实落盘", (numbered_dir / "00004_手部.png").is_file())

        resp2 = asyncio.run(mask_rename._rename_mask(_Req({
            "node_id": "1", "image_ref": src.name, "base": "直传名",
        })))
        body2 = json.loads(resp2.body.decode("utf-8"))
        check("不带名称时保持旧口径", body2.get("ok") and body2.get("out_ref", {}).get("filename") == "直传名.png", str(body2))
    finally:
        folder_paths.get_input_directory = old_input
        folder_paths.get_output_directory = old_output

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} 项 -> {FAILURES}")
    sys.exit(1)
print("ALL PASS")
