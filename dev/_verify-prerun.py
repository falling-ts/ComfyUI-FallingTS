"""离线验证 pre-run 路由: 空命令跳过 / 成功 / 失败 / 超时杀进程树 / 编码。

不启动 ComfyUI: 用 types.SimpleNamespace 桩掉 server.PromptServer(与 _0044-verify-row2.py 同款做法),
直接 import 模块并把注册到 routes 上的 handler 拿出来调用。
"""

from __future__ import annotations

import asyncio
import importlib
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
PLUGIN = ROOT / "custom_nodes" / "ComfyUI-FallingTS"


class _Routes:
    def __init__(self) -> None:
        self.posts: dict[str, object] = {}

    def post(self, path: str):
        def deco(fn):
            self.posts[path] = fn
            return fn

        return deco


routes = _Routes()
srv = types.ModuleType("server")
srv.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes))
sys.modules["server"] = srv
sys.path.insert(0, str(PLUGIN))

mod = importlib.import_module("pre-run.nodes")


class _Req:
    def __init__(self, payload) -> None:
        self._p = payload

    async def json(self):
        if isinstance(self._p, Exception):
            raise self._p
        return self._p


async def call(payload):
    """调用 handler, 回传 (status, dict)。"""
    handler = routes.posts["/fallingts_prerun/run"]
    resp = await handler(_Req(payload))
    return resp.status, resp.text


async def main() -> int:
    print(f"路由注册: {list(routes.posts)}")
    print(f"工作区根: {mod._WORKSPACE_ROOT}")
    assert mod._WORKSPACE_ROOT == ROOT, f"工作区根反推错误: {mod._WORKSPACE_ROOT} != {ROOT}"
    assert list(routes.posts) == ["/fallingts_prerun/run"]

    print("\n== 1. 空命令 / 纯空白 / 非 JSON body: 必须 skipped 且不执行 ==")
    for payload in ({}, {"command": ""}, {"command": "   \t "}, {"command": None}, ValueError("bad json")):
        status, body = await call(payload)
        data = __import__("json").loads(body)
        print(f"   {payload!r:38s} → {status} ok={data.get('ok')} skipped={data.get('skipped')}")
        assert status == 200 and data["ok"] is True and data["skipped"] is True

    print("\n== 2. 成功 + 中文输出 + 相对路径(cwd 生效) ==")
    cmd = 'python -c "import os,sys;print(os.getcwd());print(\'中文输出 OK\');print(sys.stdout.encoding)"'
    status, body = await call({"command": cmd})
    data = __import__("json").loads(body)
    print(f"   ok={data['ok']} code={data['code']} {data['ms']}ms cwd={data['cwd']}")
    for line in (data["output"] or "").splitlines():
        print(f"      | {line}")
    assert data["ok"] is True and data["code"] == 0
    assert str(ROOT) in (data["output"] or ""), "cwd 没生效(相对路径会在错误目录执行)"
    assert "中文输出 OK" in (data["output"] or ""), "中文输出解码失败"

    print("\n== 3. 非 0 退出码: ok=false + 退出码透传 ==")
    status, body = await call({"command": "echo 出错了 1>&2 & exit /b 7"})
    data = __import__("json").loads(body)
    print(f"   ok={data['ok']} code={data['code']} output={data['output']!r}")
    assert data["ok"] is False and data["code"] == 7

    print("\n== 4. 超时: 强杀进程树, ok=false, timeout=true ==")
    mod._TIMEOUT_S = 2
    status, body = await call({"command": "ping -n 30 127.0.0.1 >nul"})
    data = __import__("json").loads(body)
    print(f"   ok={data['ok']} timeout={data.get('timeout')} {data['ms']}ms output={data['output']!r}")
    assert data["ok"] is False and data.get("timeout") is True and data["ms"] < 15000

    print("\n== 5. 编码兜底: GBK 字节也能解出来 ==")
    gbk = "中文 GBK 输出".encode("gbk")
    assert mod._decode(gbk) == "中文 GBK 输出", mod._decode(gbk)
    print(f"   GBK 解码 → {mod._decode(gbk)!r}")
    print(f"   UTF-8 优先 → {mod._decode('中文 UTF-8'.encode('utf-8'))!r}")

    print("\n全部通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
