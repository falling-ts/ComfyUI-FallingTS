# cgroup 内存钳制
#
# ComfyUI 用 psutil.virtual_memory() 读系统内存(宿主全量)计算 RAM 压力缓存阈值,
# 容器里 cgroup memory.max 常远低于宿主(如宿主 503GB、cgroup 62GB),
# ComfyUI 按宿主内存规划缓存, 进程会被 cgroup OOM kill。
#
# 插件加载时机(main.py init_extra_nodes)早于 prompt_worker 线程计算缓存阈值,
# 此时接管 psutil.virtual_memory, 把 total/available 钳到 cgroup 上限,
# 并同步 comfy.model_management.total_ram, 全链路生效。
# 无 cgroup 限制(裸机/虚拟机/Windows)时行为不变。

from __future__ import annotations

import logging

import psutil

logger = logging.getLogger(__name__)

_host_virtual_memory = psutil.virtual_memory


def _cgroup_memory() -> tuple[int, int] | None:
    """返回 (cgroup 内存上限, 当前用量), 单位字节; 无限制返回 None"""
    for max_path, current_path in (
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
    ):
        try:
            with open(max_path) as f:
                limit = f.read().strip()
            if limit == "max":
                break
            limit = int(limit)
            with open(current_path) as f:
                current = int(f.read().strip())
            return limit, current
        except (OSError, ValueError):
            continue
    return None


def _cgroup_virtual_memory():
    """psutil.virtual_memory 替代实现: 按 cgroup 上限钳制 total/available"""
    mem = _host_virtual_memory()
    cgroup = _cgroup_memory()
    if cgroup is None:
        return mem
    limit, current = cgroup
    total = min(mem.total, limit)
    available = min(mem.available, max(0, limit - current))
    return mem._replace(
        total=total,
        available=available,
        used=total - available,
        percent=round(100.0 * (total - available) / total, 1),
    )


def apply() -> None:
    """安装钳制: psutil 看到 cgroup 内存视图, model_management.total_ram 同步钳制值"""
    psutil.virtual_memory = _cgroup_virtual_memory
    cgroup = _cgroup_memory()
    if cgroup is None:
        return
    limit, _ = cgroup
    try:
        import comfy.model_management as model_management
    except ImportError:
        return
    clamped_mb = limit / (1024 * 1024)
    if clamped_mb < model_management.total_ram:
        logger.info(
            "FallingTS: cgroup memory cap %.1f GiB (host sees %.1f GiB), clamping ComfyUI memory view",
            limit / 1024**3, model_management.total_ram / 1024,
        )
        model_management.total_ram = clamped_mb
