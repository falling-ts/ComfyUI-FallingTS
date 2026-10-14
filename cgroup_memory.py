# 容器内存视图 (psutil 兜底钳制)
#
# 新版 ComfyUI (>= 0.39) 自带 comfy/system_memory.py, 已按 cgroup 层级钳制
# total_ram / virtual_memory_available, ComfyUI 自身的缓存阈值与 /system_stats
# 不再经过 psutil, 无需干预。
#
# 但第三方插件 (Crystools 监视器、Easy-Use、MultiGPU 等) 仍直接调用
# psutil.virtual_memory(), 拿到的是宿主全量内存 (如宿主 1TB、cgroup 80GB),
# 仪表显示与它们的内存判断全部失真。本模块在插件加载时接管
# psutil.virtual_memory, 把 total/available/used/percent 钳到 cgroup 上限:
#   total     = min(宿主 total, cgroup memory.max)   → 只显示容器能用的内存
#   used      = cgroup memory.current - inactive_file → 容器内真实占用
#               (inactive_file 页缓存内存紧张时内核自动回收, 不算真实压力)
#   available = min(宿主 available, cgroup 剩余)
# 无 cgroup 限制 (裸机/虚拟机/Windows) 时原样透传, 行为不变。

from __future__ import annotations

import logging
import os

import psutil

logger = logging.getLogger(__name__)

_host_virtual_memory = psutil.virtual_memory

_CGROUP_V2_ROOT = "/sys/fs/cgroup"
_CGROUP_V1_ROOT = "/sys/fs/cgroup/memory"


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path: str) -> int | None:
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _stat_key(stat_path: str, key: str) -> int:
    raw = _read_text(stat_path)
    if raw:
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == key:
                try:
                    return int(parts[1])
                except ValueError:
                    break
    return 0


def _own_cgroup_roots() -> list[str]:
    """本进程所属的 cgroup 链 (v2 一条, v1 memory 一条), 自底向上 (最具体的层级优先)"""
    raw = _read_text("/proc/self/cgroup")
    if raw is None:
        return []
    roots: list[str] = []
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        controllers, path = parts[1], parts[2]
        if controllers == "":
            root = _CGROUP_V2_ROOT
        elif "memory" in controllers.split(","):
            root = _CGROUP_V1_ROOT
        else:
            continue
        dirs = [root]
        for part in path.split("/"):
            if part:
                dirs.append(os.path.join(dirs[-1], part))
        dirs.reverse()
        for d in dirs:
            if d not in roots:
                roots.append(d)
    return roots


def _cgroup_memory() -> tuple[int, int, int] | None:
    """返回 (最紧的 cgroup 内存上限, 容器内真实用量 = current - inactive_file,
    inactive_file 可回收缓存), 单位字节; 无限制返回 None"""
    host_total = _host_virtual_memory().total
    best: tuple[int, int, int] | None = None
    for root in _own_cgroup_roots():
        v2 = root != _CGROUP_V1_ROOT and root.startswith(_CGROUP_V2_ROOT)
        max_name = "memory.max" if v2 else "memory.limit_in_bytes"
        limit = _read_int(os.path.join(root, max_name))
        if limit is None or limit <= 0 or limit >= host_total:
            continue
        usage_name = "memory.current" if v2 else "memory.usage_in_bytes"
        current = _read_int(os.path.join(root, usage_name))
        if current is None:
            continue
        stat = os.path.join(root, "memory.stat")
        inactive = _stat_key(stat, "inactive_file" if v2 else "total_inactive_file")
        candidate = (limit, max(0, current - inactive), inactive)
        if best is None or candidate[0] < best[0]:
            best = candidate
    return best


def _cgroup_virtual_memory():
    """psutil.virtual_memory 替代实现: 只显示容器能用的内存与容器内使用情况"""
    mem = _host_virtual_memory()
    cgroup = _cgroup_memory()
    if cgroup is None:
        return mem
    limit, used, _reclaimable = cgroup
    total = min(mem.total, limit)
    available = min(mem.available, max(0, limit - used))
    return mem._replace(
        total=total,
        available=available,
        used=used,
        percent=round(100.0 * used / total, 1) if total else 0.0,
    )


def apply() -> None:
    """安装钳制: psutil 看到容器内存视图 (ComfyUI 自身走 comfy.system_memory, 不受影响)"""
    if psutil.virtual_memory is not _cgroup_virtual_memory:
        psutil.virtual_memory = _cgroup_virtual_memory
    cgroup = _cgroup_memory()
    if cgroup is not None:
        logger.info(
            "FallingTS: container memory view installed, cgroup cap %.1f GiB (host sees %.1f GiB)",
            cgroup[0] / 1024**3, _host_virtual_memory().total / 1024**3,
        )
