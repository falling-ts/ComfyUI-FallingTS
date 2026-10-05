"""AutoSaveImage 端到端验收(纯 HTTP): 需要临时实例跑在 8189。

以工作区根跑:
    .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-auto-save-image-e2e.py

前置: 临时实例(与 8188 主实例隔离, 代码经同一软链接生效)
    cd ComfyUI && ../.venv/Scripts/python.exe main.py --cpu --port 8189 --disable-pinned-memory --output-directory <临时输出目录>
(它可能打印 "Database is locked", 只读验证可忽略)

验证口径:
1. /object_info 里已注册 AutoSaveImage(显示名 + 6 个控件 + 3 个 hidden 齐备);
2. POST /prompt(带 extra_pnginfo.workflow.extra.fallingts_workflow_name, 图里另有一个**没人消费的
   md 数据表节点**) → 产物落进 output/<md 表文件名>/, 而不是工作流名目录;
3. 抽掉 md 表节点再跑 → 落进 output/<工作流名>/;
4. 同参数重跑 → 同名覆盖, 不出现 _序号 副本。

环境变量:
    FALLINGTS_BASE  实例地址(默认 http://127.0.0.1:8189)
    FALLINGTS_OUT   实例的 output 根目录(默认取脚本同目录下 .e2e-out, 需与 --output-directory 一致)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("FALLINGTS_BASE", "http://127.0.0.1:8189").rstrip("/")
OUT = Path(os.environ.get("FALLINGTS_OUT", str(Path(__file__).resolve().parent / ".e2e-out"))).resolve()

FAILED: list[str] = []


def check(cond, label: str, extra: str = "") -> None:
    """记一条验收结果。"""
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra else ""))
    if not cond:
        FAILED.append(label)


def req(method: str, path: str, body=None, timeout=30):
    """发一个请求, 返回 (status, 解析后的 JSON 或原始文本)。"""
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", "replace")
        status = err.code
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def files_under(root: Path) -> list[str]:
    """列出 root 下所有文件(相对路径, 正斜杠)。"""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def submit(prompt: dict, client_id: str) -> str:
    """提交 prompt 并等它跑完, 返回 prompt_id。"""
    body = {
        "prompt": prompt,
        "client_id": client_id,
        "extra_data": {
            "extra_pnginfo": {
                "workflow": {
                    "id": "e2e-auto-save",
                    "extra": {"fallingts_workflow_name": WORKFLOW_NAME},
                }
            }
        },
    }
    status, data = req("POST", "/prompt", body)
    if status != 200:
        check(False, "POST /prompt 被接受", f"{status} {data}")
        return ""
    pid = data.get("prompt_id")
    for _ in range(120):
        st, hist = req("GET", f"/history/{pid}")
        if st == 200 and hist.get(pid):
            entry = hist[pid]
            state = (entry.get("status") or {}).get("status_str")
            if state == "success":
                return pid
            if state == "error":
                check(False, "工作流执行成功", json.dumps(entry.get("status"))[:400])
                return pid
        time.sleep(0.5)
    check(False, "工作流执行成功", "超时")
    return pid


WORKFLOW_NAME = "e2e_工作流名"
PREFIX = "e2e_前缀"
SUFFIX = "_自动保存"
TABLE_DIR = "0044_参考视频"
IMAGE_NODE = {
    "1": {"class_type": "EmptyImage", "inputs": {"width": 64, "height": 48, "batch_size": 1, "color": 0}},
    "2": {
        "class_type": "AutoSaveImage",
        "inputs": {
            "images": ["1", 0],
            "filename_prefix": PREFIX,
            "filename_suffix": SUFFIX,
            "format": "png",
            "bit_depth": "8-bit",
            "input_color_space": "sRGB",
        },
    },
}
MD_NODE = {
    "9": {
        "class_type": "FallingTSMarkDownTable",
        "inputs": {"data": {"md_path": f"stories/七纹刻印/{TABLE_DIR}.md"}},
    },
}

# ── 1. 节点注册 ───────────────────────────────────────────
status, info = req("GET", "/object_info/AutoSaveImage")
check(status == 200 and isinstance(info, dict) and "AutoSaveImage" in info, "节点已注册(/object_info)")
spec = (info or {}).get("AutoSaveImage", {}) if isinstance(info, dict) else {}
check(spec.get("display_name") == "Auto Save Image (自动保存)", "显示名", str(spec.get("display_name")))
required = (spec.get("input") or {}).get("required") or {}
names = list(required)
check(
    names == ["images", "filename_prefix", "filename_suffix", "format", "bit_depth", "input_color_space"],
    "输入齐备且顺序与「预览图片」一致",
    str(names),
)
check(spec.get("output_node") is True and spec.get("output") == ["IMAGE"], "OUTPUT_NODE + IMAGE 输出")
check(
    (spec.get("input") or {}).get("hidden", {}).keys() == {"prompt", "extra_pnginfo", "id"},
    "hidden = prompt/extra_pnginfo/id",
)

# ── 2. 有 md 表 → 子目录 = 表文件名 ───────────────────────
if OUT.exists():
    # 只清上一次的残留(临时目录, 安全性由 FALLINGTS_OUT 指向保证)
    for p in sorted(OUT.rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
OUT.mkdir(parents=True, exist_ok=True)

pid = submit(IMAGE_NODE | MD_NODE, "e2e-auto-save")
target = f"{TABLE_DIR}/{PREFIX}{SUFFIX}.png"
check(target in files_under(OUT), "有 md 表 → 产物进表文件名目录", ", ".join(files_under(OUT)))

# ── 3. 没有 md 表 → 子目录 = 工作流名(注入通道) ──────────
before = files_under(OUT)
submit(IMAGE_NODE, "e2e-auto-save")
check(
    f"{WORKFLOW_NAME}/{PREFIX}{SUFFIX}.png" in files_under(OUT) and len(files_under(OUT)) == len(before) + 1,
    "无 md 表 → 产物进工作流名目录(extra 注入通道)",
    ", ".join(files_under(OUT)),
)

# ── 4. 同参数重跑 → 同名覆盖, 无 _序号 副本; 且确实重新落盘 ─
before = files_under(OUT)
target_path = OUT / TABLE_DIR / f"{PREFIX}{SUFFIX}.png"
mtime_before = target_path.stat().st_mtime_ns if target_path.exists() else 0
time.sleep(1.1)  # 让 mtime 可分辨
submit(IMAGE_NODE | MD_NODE, "e2e-auto-save")
check(files_under(OUT) == before, "同参数重跑同名覆盖(不出现 _序号 副本)", ", ".join(files_under(OUT)))
check(
    target_path.exists() and target_path.stat().st_mtime_ns > mtime_before,
    "同参数重跑确实重新落盘(IS_CHANGED 让本节点不被 output 缓存跳过)",
    f"mtime {mtime_before} -> {target_path.stat().st_mtime_ns if target_path.exists() else 'missing'}",
)

print()
if FAILED:
    print(f"FAILED {len(FAILED)}: " + "; ".join(FAILED))
    sys.exit(1)
print(f"ALL PASS  (output 根: {OUT})")
