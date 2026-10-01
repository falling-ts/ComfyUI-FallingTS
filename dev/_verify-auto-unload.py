"""离线验证 auto-unload 路由: 队列非空跳过 / 队列为空卸载 + 显存差值计算 + 调用顺序。

不启动 ComfyUI: 用 types 桩掉 server.PromptServer 与 comfy.model_management
(与 _verify-prerun.py 同款做法), 直接 import 模块并把注册到 routes 上的 handler 拿出来调用。

用法: .venv/bin/python custom_nodes/ComfyUI-FallingTS/dev/_verify-auto-unload.py
"""

from __future__ import annotations

import importlib
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
PLUGIN = ROOT / "custom_nodes" / "ComfyUI-FallingTS"
_MB = 1024 * 1024


class _Routes:
    def __init__(self) -> None:
        self.posts: dict[str, object] = {}

    def post(self, path: str):
        def deco(fn):
            self.posts[path] = fn
            return fn

        return deco


routes = _Routes()


class _Queue:
    def __init__(self) -> None:
        self.remaining = 0

    def get_tasks_remaining(self) -> int:
        return self.remaining


queue = _Queue()
srv = types.ModuleType("server")
srv.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes, prompt_queue=queue))
sys.modules["server"] = srv


class _MM:
    """桩 comfy.model_management: 记录调用序列, unload 后把空闲显存抬高 25 GB。"""

    def __init__(self) -> None:
        self.free = 8 * _MB * 1024  # 8 GB 空闲
        self.calls: list[str] = []

    def get_all_torch_devices(self):
        return ["cuda:0"]

    def get_free_memory(self, dev):
        return self.free

    def unload_all_models(self):
        self.calls.append("unload")
        self.free += 25 * _MB * 1024  # 模拟逐出大模型: 空闲 +25 GB

    def soft_empty_cache(self):
        self.calls.append("soft_empty_cache")


mm = _MM()
comfy = types.ModuleType("comfy")
mm_mod = types.ModuleType("comfy.model_management")
mm_mod.get_all_torch_devices = mm.get_all_torch_devices
mm_mod.get_free_memory = mm.get_free_memory
mm_mod.unload_all_models = mm.unload_all_models
mm_mod.soft_empty_cache = mm.soft_empty_cache
comfy.model_management = mm_mod
sys.modules["comfy"] = comfy
sys.modules["comfy.model_management"] = mm_mod
sys.path.insert(0, str(PLUGIN))

mod = importlib.import_module("auto-unload.nodes")


class _Req:
    async def json(self):
        return {}


async def call():
    handler = routes.posts["/fallingts_auto_unload/unload"]
    resp = await handler(_Req())
    return resp.status, json.loads(resp.text)


def main() -> int:
    print(f"路由注册: {list(routes.posts)}")
    assert list(routes.posts) == ["/fallingts_auto_unload/unload"], "路由路径不对"

    print("\n== 1. 队列非空(3 个任务): 必须 skipped 且完全不调用卸载 ==")
    queue.remaining = 3
    status, data = call_sync()
    print(f"   → {status} {data}")
    assert status == 200 and data["ok"] is True and data["skipped"] is True and data["remaining"] == 3
    assert mm.calls == [], f"队列非空却调了卸载: {mm.calls}"

    print("\n== 2. 队列为空: 卸载 + 显存差值 + 调用顺序 ==")
    queue.remaining = 0
    mm.free = 8 * _MB * 1024
    mm.calls.clear()
    status, data = call_sync()
    print(f"   → {status} {data}")
    print(f"   调用序列: {mm.calls}")
    assert status == 200 and data["ok"] is True and data["skipped"] is False and data["remaining"] == 0
    assert data["freed_mb"] == 25 * 1024, f"freed_mb 算错: {data['freed_mb']}"
    assert data["free_mb"] == 33 * 1024, f"free_mb 算错: {data['free_mb']}"
    assert mm.calls == ["unload", "soft_empty_cache"], f"调用顺序不对: {mm.calls}"

    print("\n== 3. 空闲显存不涨(逐不动)时 freed_mb 不为负 ==")
    mm.free = 8 * _MB * 1024
    mm.calls.clear()
    mm.unload_all_models = lambda: mm.calls.append("unload")  # 这次不涨
    mm_mod.unload_all_models = mm.unload_all_models  # 同步到模块桩(模块持有的是 mm_mod 上的引用)
    status, data = call_sync()
    print(f"   → {status} {data}")
    assert data["ok"] is True and data["freed_mb"] == 0 and data["free_mb"] == 8 * 1024

    print("\nPASS: auto-unload 路由离线自检全部通过")
    return 0


def call_sync():
    import asyncio

    return asyncio.run(call())


if __name__ == "__main__":
    raise SystemExit(main())
