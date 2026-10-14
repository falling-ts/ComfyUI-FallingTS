# auto-unload/nodes.py
r"""跑完自动卸载模型: 每次工作流跑完(成功)且队列为空时, 自动卸载全部已加载模型, 释放显存。

本文件**不注册任何节点**, 只注册路由(与 mask-rename / pre-run 同款: 由包 __init__.py import 即生效):

    POST /fallingts_auto_unload/unload   (空 body)
      → {"ok", "skipped", "remaining", "freed_mb", "free_mb", "ms"}

语义(与内置「卸载模型」按钮等效, 但可立即触发):

- 内置按钮走 `POST /free` 只是**置旗**(`unload_models`), 旗标在 prompt 主循环里
  **下一次 prompt 执行完之后**才被消费 ⇒ 单次"跑完"永远不会生效。
  所以这里直接调旗标最终调用的核心函数:
  `comfy.model_management.unload_all_models()`(对每个设备 `free_memory(1e30)` 强逐全部已加载模型)
  → `gc.collect()` → `soft_empty_cache()`(sync + empty_cache + ipc_collect);
- **队列非空则跳过**(返回 `skipped: true`): 多任务连跑时只有最后一个真正卸载,
  避免中途把模型逐掉导致下一个任务被迫重新加载;
- 卸载放在线程池 executor 里跑(逐大模型 + empty_cache 可能耗时数秒, 不能阻塞 aiohttp 事件循环);
- 卸载完再追加一步**容器内存清理**(通用, 非显存): 子进程跑同目录的 `clear_page_cache.py`,
  对模型与解释器的大文件执行 posix_fadvise(DONTNEED) 丢弃文件页缓存 —— 页缓存堆积会把
  cgroup 内存限额吃满导致分配被限流; 无 cgroup 限制(裸机)时脚本自己安全退出; 脚本缺失或
  清理失败不报错, 不影响卸载结果;
  ⚠️ 脚本**必须随本节点一起放**(同目录), 不依赖工作区根的 `scripts/` —— 插件被单独安装时
  那里没有这个文件, 清理会静默失效; 缺失时记 info 而非 debug, 便于发现;
- 前端在 `execution_success` 事件后触发(见 web/js/auto_unload.js): 此时该 prompt 已被
  `task_done` 从队列 pop、`queue_updated` 已推送, 与执行线程无竞态; 唯一竞态是"跑完立刻又提交
  新任务", 最坏情况 = 新任务的模型多加载一次(与内置按钮在运行中被点击等效), 不崩溃。

日志: 每次卸载的结果(释放显存、耗时)记入 `logging`(落 `ComfyUI\user\comfyui.log`)。
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import subprocess
import sys
import time

from aiohttp import web
from server import PromptServer

from comfy import model_management

logger = logging.getLogger(__name__)

_MB = 1024 * 1024


def _clear_page_cache() -> None:
    """追加的容器内存清理: 丢弃模型与解释器大文件的页缓存, 释放 cgroup 内存压力。

    页缓存堆积会把 cgroup 限额吃满(分配被限流/OOM), 而宿主内存充裕时内核不主动
    回收; 对模型目录跑 fadvise(DONTNEED) 精确丢弃干净页缓存即可。无 cgroup 限制
    (裸机/Windows)时脚本自己退出; 脚本缺失记 info、执行失败记 warning, 均不影响卸载。
    """
    # 脚本与本文件同目录(随插件分发), 不依赖工作区根的 scripts/ —— 插件被单独安装时
    # 那里没有这个文件。用 realpath: 经 custom_nodes 软链加载时 __file__ 是软链路径。
    script = os.path.join(os.path.dirname(os.path.realpath(__file__)), "clear_page_cache.py")
    if not os.path.isfile(script):
        logger.info("[FallingTS.AutoUnload] 页缓存清理脚本不存在, 跳过: %s", script)
        return
    try:
        proc = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            logger.warning(
                "[FallingTS.AutoUnload] 页缓存清理脚本退出码 %d: %s",
                proc.returncode, (proc.stderr or "").strip()[:200],
            )
        elif proc.stdout.strip():
            for line in proc.stdout.strip().splitlines():
                logger.info("[FallingTS.AutoUnload] %s", line)
    except Exception:  # 清理失败绝不影响卸载主流程
        logger.exception("[FallingTS.AutoUnload] 页缓存清理异常, 已忽略")


def _do_unload() -> dict:
    """逐出全部已加载模型 + 释放 CUDA 缓存分配器, 返回前后空闲显存差(单位 MB)。"""
    devices = model_management.get_all_torch_devices()
    before = {str(dev): model_management.get_free_memory(dev) for dev in devices}

    t0 = time.monotonic()
    model_management.unload_all_models()
    gc.collect()
    model_management.soft_empty_cache()
    ms = int((time.monotonic() - t0) * 1000)

    freed_mb = 0
    free_mb = 0
    for dev in devices:
        after = model_management.get_free_memory(dev)
        freed_mb += max(0, int(after - before[str(dev)]) // _MB)
        free_mb += int(after // _MB)

    logger.info(
        "[FallingTS.AutoUnload] 已卸载全部模型: 释放 %d MB, 当前空闲 %d MB, %d ms",
        freed_mb,
        free_mb,
        ms,
    )
    _clear_page_cache()
    return {"freed_mb": freed_mb, "free_mb": free_mb, "ms": ms}


@PromptServer.instance.routes.post("/fallingts_auto_unload/unload")
async def _auto_unload(request: web.Request) -> web.Response:
    """自动卸载入口: 队列非空则跳过, 否则工作线程里卸载并返回结果。"""
    remaining = PromptServer.instance.prompt_queue.get_tasks_remaining()
    if remaining > 0:
        return web.json_response({"ok": True, "skipped": True, "remaining": remaining})

    result = await asyncio.get_running_loop().run_in_executor(None, _do_unload)
    return web.json_response({"ok": True, "skipped": False, "remaining": 0, **result})
