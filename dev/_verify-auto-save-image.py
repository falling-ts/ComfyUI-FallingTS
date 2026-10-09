"""AutoSaveImage 离线验收: 不起服务、不动 8188 主实例, 只验节点本体。

验四件事:
1. 节点是从「预览图片」继承来的(输入/输出/落盘实现复用同一个父类);
2. workflow_name_from_extra 的两条通道 —— 顶层 workflow_name 优先于 workflow.extra 注入键;
3. 子目录口径: 有 md 数据表节点 → 表文件名; 没有 md 表 → 工作流名; 都没有 → output 根;
4. execute 真的落盘(前缀 + 后缀拼接、同名覆盖无序号), 且 images=None 时不写盘、按 sticky 回放。

跑法(工作区根): .venv/Scripts/python.exe custom_nodes/ComfyUI-FallingTS/dev/_verify-auto-save-image.py
"""

from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent  # 工作区根
PLUGIN = ROOT / "custom_nodes" / "ComfyUI-FallingTS"
sys.path.insert(0, str(ROOT / "ComfyUI"))
sys.path.insert(0, str(PLUGIN))

FAILED: list[str] = []


def check(cond, label: str, extra: str = "") -> None:
    """记一条验收结果, 失败单独记名以便汇总。"""
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra else ""))
    if not cond:
        FAILED.append(label)


# 插件的节点模块在 import 时就给 PromptServer 挂路由(要求 instance 非空); 离线跑没有 main.py,
# 自造一个只带 routes 的壳, 让 @PromptServer.instance.routes.get(...) 正常执行
from aiohttp import web  # noqa: E402

import server  # noqa: E402

if getattr(server.PromptServer, "instance", None) is None:

    class _FakeServer:
        def __init__(self):
            self.routes = web.RouteTableDef()

    server.PromptServer.instance = _FakeServer()

import folder_paths  # noqa: E402
import torch  # noqa: E402

preview = importlib.import_module("preview-image.nodes")
autosave = importlib.import_module("auto-save-image.nodes")

# ── 1. 继承与声明 ─────────────────────────────────────────
node_cls = autosave.AutoSaveImageNode
check(issubclass(node_cls, preview.PreviewImageSaveNode), "继承 PreviewImageSaveNode(复用预览/落盘实现)")
check(node_cls.FUNCTION == "execute" and node_cls.OUTPUT_NODE is True, "FUNCTION/OUTPUT_NODE 与父类一致")
check(node_cls.CATEGORY == "FallingTS", "CATEGORY=FallingTS", node_cls.CATEGORY)
check(node_cls.INPUT_TYPES() == preview.PreviewImageSaveNode.INPUT_TYPES(), "输入声明与父类完全相同(含 hidden)")
check(node_cls.DESCRIPTION != preview.PreviewImageSaveNode.DESCRIPTION, "DESCRIPTION 独立(写明自动保存)")
check(autosave.NODE_CLASS_MAPPINGS == {"AutoSaveImage": node_cls}, "模块注册表 NODE_CLASS_MAPPINGS")

# ── 1b. 缓存失效签名(自动保存必须每次执行都落盘) ───────────
check(
    "IS_CHANGED" not in vars(preview.PreviewImageSaveNode),
    "父类未定义 IS_CHANGED(没有为自动保存改过 preview-image)",
)
check(
    node_cls.IS_CHANGED() != node_cls.IS_CHANGED(),
    "IS_CHANGED 每次签名都不同(否则重跑时 ComfyUI 命中 output 缓存、根本不调 execute)",
    str(node_cls.IS_CHANGED()),
)

# ── 2. 工作流名的两条通道 ─────────────────────────────────
wne = autosave.workflow_name_from_extra
check(wne(None) == "" and wne({}) == "", "无 extra_pnginfo → 空串")
check(wne({"workflow_name": "0044_参考视频"}) == "0044_参考视频", "顶层 workflow_name 通道")
check(
    wne({"workflow": {"extra": {autosave.WORKFLOW_NAME_EXTRA_KEY: "0050_视频截帧"}}}) == "0050_视频截帧",
    "workflow.extra 注入通道",
)
check(
    wne({"workflow_name": "  ", "workflow": {"extra": {autosave.WORKFLOW_NAME_EXTRA_KEY: "0051_视频拆音"}}})
    == "0051_视频拆音",
    "顶层为空时退回注入通道",
)
check(
    wne({"workflow_name": "0044_参考视频", "workflow": {"extra": {autosave.WORKFLOW_NAME_EXTRA_KEY: "0050_视频截帧"}}})
    == "0044_参考视频",
    "顶层优先于注入通道",
)
check(wne({"workflow": {"id": "gen-x"}}) == "" and wne([1, 2]) == "", "形状不对/无名字 → 空串")

# ── 3./4. 真落盘(把 output/temp 换到临时目录) ─────────────
out_root = Path(tempfile.mkdtemp(prefix="fallingts-autosave-out-"))
temp_root = Path(tempfile.mkdtemp(prefix="fallingts-autosave-temp-"))
folder_paths.get_output_directory = lambda: str(out_root)
folder_paths.get_temp_directory = lambda: str(temp_root)

images = torch.zeros((1, 16, 16, 3))
prompt_md = {
    "1": {"class_type": "EmptyImage", "inputs": {}},
    "9": {
        "class_type": "FallingTSMarkDownTable",
        "inputs": {"data": {"md_path": "stories/七纹刻印/0044_参考视频.md"}},
    },
}


def run(prefix, suffix, prompt, extra, node_id="7"):
    """跑一次 execute, 返回落盘文件名(相对 output 根)与返回的 UI 记录。"""
    node = node_cls()
    out = node.execute(
        images,
        filename_prefix=prefix,
        filename_suffix=suffix,
        format="png",
        bit_depth="8-bit",
        input_color_space="sRGB",
        prompt=prompt,
        extra_pnginfo=extra,
        id=node_id,
    )
    return out


def files_under(root: Path) -> list[str]:
    """列出 root 下所有文件(相对路径, 正斜杠)。"""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ① 有 md 表 → 子目录 = 表文件名(即使工作流名是别的)
run("00001_书房旋镜视频", "_首帧", prompt_md, {"workflow_name": "0044_参考视频"})
check(
    "0044_参考视频/00001_书房旋镜视频_首帧.png" in files_under(out_root),
    "md 表文件名优先作子目录",
    ", ".join(files_under(out_root)),
)

# ② 没有 md 表 → 子目录 = 工作流名(经 workflow.extra 注入通道)
run("00002_书房旋镜视频", "_关键帧", {"1": {"class_type": "EmptyImage", "inputs": {}}},
    {"workflow": {"extra": {autosave.WORKFLOW_NAME_EXTRA_KEY: "0050_视频截帧"}}})
check(
    "0050_视频截帧/00002_书房旋镜视频_关键帧.png" in files_under(out_root),
    "无 md 表 → 工作流名作子目录(注入通道)",
    ", ".join(files_under(out_root)),
)

# ③ 都没有 → output 根
run("裸前缀", "_后缀", {"1": {"class_type": "EmptyImage", "inputs": {}}}, {})
check("裸前缀_后缀.png" in files_under(out_root), "无子目录信息 → output 根", ", ".join(files_under(out_root)))

# ④ 同名覆盖无序号: 再跑一次, 文件数不变
before = files_under(out_root)
run("00001_书房旋镜视频", "_首帧", prompt_md, {"workflow_name": "0044_参考视频"})
check(files_under(out_root) == before, "同参数重跑同名覆盖(无 _序号 副本)", ", ".join(files_under(out_root)))

# ⑤ %batch_num% 按批号区分(父类口径)
run("batch_%batch_num%", "", prompt_md, {"workflow_name": "0044_参考视频"})
check("0044_参考视频/batch_0.png" in files_under(out_root), "%batch_num% 替换", ", ".join(files_under(out_root)))

# ⑥ 预览记录 = temp 目录里的文件且确实存在
out = run("00003_预览", "", prompt_md, {"workflow_name": "0044_参考视频"})
ui_items = out.get("ui", {}).get("images", [])
check(
    bool(ui_items) and all(it.get("type") == "temp" for it in ui_items),
    "返回 temp 预览记录(前端 /view?type=temp 显示)",
    str(ui_items[:1]),
)
check(
    all((temp_root / (it.get("subfolder") or "") / it["filename"]).is_file() for it in ui_items),
    "temp 预览文件真实存在",
)
check(out.get("result", (None,))[0] is not None and tuple(out["result"][0].shape) == (1, 16, 16, 3), "result 透传图片批")

# ⑦ images=None: 不写盘 + 按 sticky 回放(用有缓存的 node_id="7")
before_none = files_under(out_root)
last = node_cls()
res = last.execute(None, prompt=prompt_md, extra_pnginfo={"workflow_name": "0044_参考视频"}, id="7")
check(files_under(out_root) == before_none, "images=None 不落盘")
check(res["result"][0] is not None and tuple(res["result"][0].shape) == (1, 16, 16, 3), "images=None 透传最近一次预览的图")
fresh = node_cls()
res2 = fresh.execute(None, prompt=None, extra_pnginfo={}, id="99")
check(res2["result"][0] is None and res2["ui"]["images"] == [], "从未预览过 → images=None 下透传 None、预览为空")

print()
if FAILED:
    print(f"FAILED {len(FAILED)}: " + "; ".join(FAILED))
    sys.exit(1)
print(f"ALL PASS  (output 临时目录: {out_root})")
