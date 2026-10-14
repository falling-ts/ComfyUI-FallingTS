#!/usr/bin/env python3
"""容器内存清理: 丢弃文件页缓存 (posix_fadvise DONTNEED)

容器内 cgroup 限额常远小于宿主内存, 进程读过的文件页缓存 (file cache)
全部计入容器限额并堆积到顶; 宿主内存充裕时内核不会主动回收,
表现为 memory.current 逼近 memory.max、分配被限流 (memory.events max 计数增长)。

本脚本对目录下的文件执行 posix_fadvise(DONTNEED), 精确丢弃干净的页缓存:
- 对 mmap 中的进程 (如 llama-server -mm) 无害, 下次访问自动重读磁盘;
- 脏页先 sync 落盘再丢弃, 不丢数据;
- 对 anon (进程真实内存) 无效, 只回收文件页缓存。

本文件放在 auto-unload/ 内、由 nodes.py 调用, 不依赖工作区外的任何路径 ——
插件被单独安装时也不会缺文件。

用法:
  python3 clear_page_cache.py                 # 清理默认目录 (ComfyUI 模型目录 + 当前解释器目录)
  python3 clear_page_cache.py /path/a /path/b # 清理指定目录
  python3 clear_page_cache.py --min-size 512M # 只处理大于阈值的文件 (默认 20M)

阈值默认 20M 而非更大: 实测解释器 site-packages 里 ≥20M 的动态库合计 5.4GiB,
若按 ≥512M 只覆盖到 1 个文件(0.5GiB) —— 大文件阈值会让第二大缓存来源整片漏掉。
文件数增加有限(本机 2202 → 3151 个, 扫描耗时基本不变), 远低于调用方 120s 超时。

无 cgroup 限制 (裸机) 或无权限时安全退出, 退出码 0。
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time

POSIX_FADV_DONTNEED = 4


def comfy_model_dirs() -> list[str]:
    """ComfyUI 的模型目录. 优先问 folder_paths(尊重 extra_model_paths.yaml 等额外路径),
    拿不到再按插件位置回退到 <工作区根>/models 与 <ComfyUI>/models。"""
    dirs: list[str] = []
    try:  # 作为插件运行时 ComfyUI 已在 sys.path 上
        import folder_paths  # type: ignore

        for _name, (paths, _exts) in folder_paths.folder_names_and_paths.items():
            dirs.extend(paths)
        if getattr(folder_paths, "models_dir", None):
            dirs.append(folder_paths.models_dir)
    except Exception:
        pass

    if not dirs:  # 独立运行(离线自检/手动)时的回退: 从本文件位置反推
        here = os.path.dirname(os.path.abspath(__file__))       # …/ComfyUI-FallingTS/auto-unload
        plugin = os.path.dirname(here)                          # …/ComfyUI-FallingTS
        custom_nodes = os.path.dirname(plugin)                  # …/custom_nodes
        comfy_root = os.path.dirname(os.path.realpath(custom_nodes)) if os.path.islink(custom_nodes) \
            else os.path.dirname(custom_nodes)
        dirs.extend([os.path.join(comfy_root, "models"),
                     os.path.join(os.path.dirname(comfy_root), "models")])
    return dirs


def default_dirs() -> list[str]:
    """默认目录 = ComfyUI 模型目录 + 当前解释器目录(动态库). 只依赖运行时探测, 不写死路径。"""
    dirs = comfy_model_dirs()

    root = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
    for sub in ("lib",):  # 类 Unix: <env>/lib; Windows 无此目录, 自然跳过
        lib = os.path.join(root, sub)
        if os.path.isdir(lib):
            dirs.append(lib)

    # 去重 + 父子剪枝: folder_paths 会把 models/ 下的每个子槽位各列一条(30+ 条),
    # 它们全被父目录 models/ 覆盖 ⇒ 只保留父目录, 否则同一批文件被重复 walk 多遍。
    uniq: list[str] = []
    seen: set[str] = set()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        key = os.path.realpath(d)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(key)

    out: list[str] = []
    for key in sorted(uniq, key=lambda p: p.count(os.sep)):  # 浅的在前 ⇒ 父目录先入列
        # 已有更浅的父目录覆盖它 ⇒ 跳过
        if any(key == p or key.startswith(p + os.sep) for p in out):
            continue
        out.append(key)
    return out


def parse_size(text: str) -> int:
    """'512M' / '2G' / '1073741824' → 字节数"""
    text = text.strip().upper()
    mult = 1
    for suffix, m in (("KIB", 1024), ("MIB", 1024**2), ("GIB", 1024**3),
                      ("K", 1024), ("M", 1024**2), ("G", 1024**3)):
        if text.endswith(suffix):
            mult = m
            text = text[: -len(suffix)]
            break
    return int(float(text) * mult)


def cgroup_memory() -> tuple[int, int] | None:
    """返回 (memory.current, memory.max); 无 cgroup 限制返回 None"""
    for cur, mx in (("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
                    ("/sys/fs/cgroup/memory/memory.usage_in_bytes",
                     "/sys/fs/cgroup/memory/memory.limit_in_bytes")):
        try:
            with open(cur) as f:
                current = int(f.read().strip())
            with open(mx) as f:
                raw = f.read().strip()
            if raw == "max":
                return None
            return current, int(raw)
        except (OSError, ValueError):
            continue
    return None


def drop_file_cache(path: str, libc: ctypes.CDLL) -> None:
    """对单个文件执行 fadvise(DONTNEED), 丢弃干净页缓存"""
    fd = os.open(path, os.O_RDONLY)
    try:
        libc.posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED)
    finally:
        os.close(fd)


def collect_files(dirs: list[str], min_size: int) -> list[str]:
    files: set[str] = set()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, names in os.walk(d, followlinks=False):
            for name in names:
                p = os.path.join(root, name)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if not os.path.isfile(p):  # 排除软链目标重复统计
                    continue
                if st.st_size >= min_size:
                    files.add(os.path.realpath(p))
    return sorted(files, key=lambda p: os.path.getsize(p), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="丢弃容器内文件页缓存 (fadvise DONTNEED)")
    parser.add_argument("dirs", nargs="*", default=None,
                        help="要清理的目录 (默认: ComfyUI 模型目录 + 当前解释器目录)")
    parser.add_argument("--min-size", default="20M",
                        help="只处理大于该大小的文件, 如 20M / 512M / 1G (默认 20M)")
    args = parser.parse_args()

    mem = cgroup_memory()
    if mem is None:
        print("[clear_page_cache] 无 cgroup 内存限制, 无需清理")
        return 0

    dirs = args.dirs if args.dirs else default_dirs()
    min_size = parse_size(args.min_size)

    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    os.sync()

    before = mem[0]
    files = collect_files(dirs, min_size)
    total = sum(os.path.getsize(f) for f in files)
    print(f"[clear_page_cache] 处理 {len(files)} 个文件 (≥{args.min_size}, 合计 {total/1024**3:.0f}GiB) …")
    dropped = 0
    for f in files:
        try:
            drop_file_cache(f, libc)
            dropped += 1
        except OSError:
            pass
    time.sleep(1)
    os.sync()

    after = cgroup_memory()
    if after is None:
        print("[clear_page_cache] 清理后无法读取 cgroup 状态")
        return 0
    freed = before - after[0]
    print(f"[clear_page_cache] 完成: 丢弃 {dropped}/{len(files)} 个文件, "
          f"memory.current {before/1024**3:.1f}GiB → {after[0]/1024**3:.1f}GiB "
          f"(释放 {freed/1024**3:.1f}GiB, 限额 {after[1]/1024**3:.1f}GiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
