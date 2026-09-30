# pre-run/nodes.py
"""运行前命令: 每次「运行 / Ctrl+Enter」提交之前, 在宿主上执行一条用户在系统设置里配置的命令。

本文件**不注册任何节点**, 只注册路由(与 mask-rename 同款: 由包 __init__.py import 即生效):

    POST /fallingts_prerun/run   {"command": "<命令>"}
      → {"ok", "skipped", "code", "output", "cwd", "ms", "timeout"}

语义(照 git 的 pre-commit 钩子来, 前端据此决定要不要真的提交):

- **命令为空/全是空白 → 直接跳过**(skipped=true), 不执行任何东西;
- 命令在**「Comfy 工作区根目录」下执行** —— 即 `custom_nodes` 的上一级(本机 `D:\\AI\\Comfy`),
  通常也正是 `.venv` 与 `scripts\\` 所在处, 所以 `scripts\\xxx.py` 这类相对路径可以直接写。
  该目录由本文件 realpath 反推得到(`ComfyUI\\custom_nodes` 是目录级软链, realpath 会解开),
  项目整体搬家后自动跟随, 不写死盘符;
- **非 0 退出码 → ok=false, 前端不提交本次运行**(命令没成功就不要拿旧输入去跑生成);
- **超时 → 杀掉整个进程树**(cmd.exe 会派生子进程, 只杀 shell 会留下孤儿进程), 同样 ok=false;
- 成功时也只把**输出尾部**回传(见 _MAX_OUTPUT), 免得一条话多的命令把响应撑爆。

日志: 命令原文、退出码、耗时与输出都进 `logging`(落 `ComfyUI\\user\\comfyui.log`), 便于事后追溯。

⚠️ 安全性: 本路由会在宿主上执行任意命令, 与 ComfyUI 自身的节点执行能力同级(ComfyUI 默认只听 127.0.0.1)。
"""

from __future__ import annotations

import asyncio
import locale
import logging
import os
import pathlib
import time

from aiohttp import web
from server import PromptServer

logger = logging.getLogger(__name__)

# 工作目录 = Comfy 工作区根 = custom_nodes 的上一级。
# __file__ = <root>/custom_nodes/ComfyUI-FallingTS/pre-run/nodes.py
_PLUGIN_DIR = pathlib.Path(__file__).resolve().parent
_WORKSPACE_ROOT = _PLUGIN_DIR.parent.parent.parent

# 反推失败(布局被改)时退回进程工作目录, 保证路由仍可用
if not (_WORKSPACE_ROOT / "custom_nodes").is_dir():
    logger.warning(
        "[FallingTS.PreRun] 工作区根反推异常(%s), 回退进程工作目录", _WORKSPACE_ROOT
    )
    _WORKSPACE_ROOT = pathlib.Path(os.getcwd())

# 输出只回传尾部; 一次运行最长 10 分钟
_MAX_OUTPUT = 8000
_TIMEOUT_S = 600

# 串行化: 连点两次 Run 时不要并发跑两条前置命令
_run_lock = asyncio.Lock()


def _child_env() -> dict[str, str]:
    """子进程环境: 追加 UTF-8 钉定(Windows 上 stdout 接管道会退回 GBK, 中文产物路径会变乱码)。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _fallback_encodings() -> tuple[str, ...]:
    """候选编码: UTF-8 → 系统本地编码 → Windows 控制台 OEM/ANSI 代码页。

    ⚠️ 不能只用 `locale.getpreferredencoding()`: 它受 `PYTHONUTF8=1` 影响会变成 utf-8,
    而 cmd 的**内建命令**(echo/dir/copy)把输出写进管道时用的是控制台代码页(简中 = GBK),
    于是中文提示语会解成 `\\ufffd`。故额外带上 Windows 专用的 `oem`(输出代码页)与 `mbcs`(ANSI)。
    """
    candidates = ["utf-8", locale.getpreferredencoding(False)]
    if os.name == "nt":
        candidates += ["oem", "mbcs"]
    seen: list[str] = []
    for enc in candidates:
        if enc and enc.lower() not in [s.lower() for s in seen]:
            seen.append(enc)
    return tuple(seen)


def _decode(raw: bytes) -> str:
    """解码子进程输出: 逐个候选编码严格试解, 全失败才按 UTF-8 替换字符兜底。"""
    if not raw:
        return ""
    for enc in _fallback_encodings():
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


async def _kill_tree(pid: int) -> None:
    """结束整个进程树(Windows 用 taskkill /T, POSIX 杀进程组)。"""
    try:
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/F",
                "/T",
                "/PID",
                str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
            return
        os.killpg(os.getpgid(pid), 9)
    except (OSError, ProcessLookupError) as exc:
        logger.warning("[FallingTS.PreRun] 终止进程树失败(pid=%s): %s", pid, exc)


async def _run_command(command: str) -> dict:
    """执行一条命令并收集结果(不抛异常, 一切失败都转成 ok=false)。"""
    cwd = str(_WORKSPACE_ROOT)
    logger.info("[FallingTS.PreRun] 执行: %s   (cwd=%s)", command, cwd)
    t0 = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            env=_child_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )
    except OSError as exc:
        logger.error("[FallingTS.PreRun] 无法启动命令: %s", exc)
        return {
            "ok": False,
            "skipped": False,
            "code": None,
            "output": f"无法启动命令: {exc}",
            "cwd": cwd,
            "ms": 0,
        }

    timed_out = False
    raw = b""
    try:
        raw, _ = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_S)
    except asyncio.TimeoutError:
        timed_out = True
        logger.error("[FallingTS.PreRun] 命令超时 %ss, 强制终止 pid=%s", _TIMEOUT_S, proc.pid)
        await _kill_tree(proc.pid)
        try:
            raw, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        except (asyncio.TimeoutError, ValueError, ProcessLookupError):
            raw = b""

    ms = int((time.monotonic() - t0) * 1000)
    output = _decode(raw)
    if timed_out:
        output = f"{output}\n[FallingTS.PreRun] 超时 {_TIMEOUT_S}s, 已强制终止".strip()
    code = None if timed_out else proc.returncode
    ok = not timed_out and proc.returncode == 0

    logger.info(
        "[FallingTS.PreRun] 结束: ok=%s exit=%s %dms%s",
        ok,
        code,
        ms,
        f"\n{output}" if output else "  (无输出)",
    )
    return {
        "ok": ok,
        "skipped": False,
        "code": code,
        "output": output[-_MAX_OUTPUT:],
        "cwd": cwd,
        "ms": ms,
        "timeout": timed_out,
    }


@PromptServer.instance.routes.post("/fallingts_prerun/run")
async def _prerun(request: web.Request) -> web.Response:
    """运行前命令入口: 空命令跳过, 否则串行执行并回传结果。"""
    try:
        data = await request.json()
    except (ValueError, TypeError):
        data = {}

    command = str((data or {}).get("command") or "").strip()
    if not command:
        return web.json_response({"ok": True, "skipped": True, "cwd": str(_WORKSPACE_ROOT)})

    async with _run_lock:
        return web.json_response(await _run_command(command))
