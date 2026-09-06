# cgroup 内存钳制
#
# ComfyUI 用 psutil.virtual_memory() 读系统内存(宿主全量)计算 RAM 压力缓存阈值,
# 容器里 cgroup memory.max 常远低于宿主(如宿主 503GB、cgroup 62GB),
# ComfyUI 按宿主内存规划缓存, 进程会被 cgroup OOM kill。
#
# 插件加载时机(main.py init_extra_nodes)早于 prompt_worker 线程计算缓存阈值,
# 此时接管 psutil.virtual_memory, 把 total/available 钳到 cgroup 上限,
# 并同步 comfy.model_management.total_ram, 全链路生效。
# available 口径: 当前用量扣除 memory.stat 的 file 页缓存(内存紧张时内核自动回收,
# 不算真实压力), 避免把加载模型攒下的缓存误判为内存不足。
# 无 cgroup 限制(裸机/虚拟机/Windows)时行为不变。

from __future__ import annotations

import logging

import psutil

logger = logging.getLogger(__name__)

_host_virtual_memory = psutil.virtual_memory


def _cgroup_memory() -> tuple[int, int, int] | None:
    """返回 (cgroup 内存上限, 当前用量, 可回收 file 页缓存), 单位字节; 无限制返回 None"""
    for max_path, current_path, stat_path in (
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.stat"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory/memory.stat"),
    ):
        try:
            with open(max_path) as f:
                limit = f.read().strip()
            if limit == "max":
                break
            limit = int(limit)
            with open(current_path) as f:
                current = int(f.read().strip())
        except (OSError, ValueError):
            continue
        return limit, current, _cgroup_file_cache(stat_path)
    return None


def _cgroup_file_cache(stat_path: str) -> int:
    """cgroup 的 file 页缓存(可回收), 单位字节; 读不到返回 0(保守口径)"""
    try:
        with open(stat_path) as f:
            for line in f:
                if line.startswith("file "):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return 0


def _cgroup_virtual_memory():
    """psutil.virtual_memory 替代实现: total 钳到 cgroup 上限, available 扣除可回收缓存后的真实用量"""
    mem = _host_virtual_memory()
    cgroup = _cgroup_memory()
    if cgroup is None:
        return mem
    limit, current, reclaimable = cgroup
    total = min(mem.total, limit)
    used = max(0, current - reclaimable)
    available = min(mem.available, max(0, limit - used))
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
    limit = cgroup[0]
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
