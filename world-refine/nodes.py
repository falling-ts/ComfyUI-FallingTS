# world-refine/nodes.py
"""FallingTS 世界重建精修节点 (多视图 → 504 前馈 + 3DGS 全参数精修 → PLY)。

为什么是"编排"而不是"在节点里算": 精修要 gsplat, 而 gsplat 只存在于 HYWM2 插件的隔离
环境 (`hywm2-nodes`, cu128) 里 —— 主 venv 是 torch 2.13+cu130, 装不了它。本节点因此在
主进程 (主 venv) 里只做三件事, 真算交给隔离解释器跑同目录的 `refine_0034_gs.py`:

  ① 把上游来的 IMAGE 批落成临时 PNG (并可选地把 EXTRINSICS/INTRINSICS 先验落成相机 JSON);
  ② 用隔离解释器的 python 跑精修脚本 (它自己做 504 前馈 + 2% 尺度过滤 + 外观精修);
  ③ 从脚本 stdout 的 `[OUT] ` 行取回 PLY 路径, 交给下游 PLY 视口。

两种上游接法:
  - **8 视图 (md 数据表)**: 批序 前面/前右/右面/右后/后面/后左/左面/左前, 位姿由模型自己预测;
  - **全景视角批 (WorldPanoramaViews)**: 任意 N 个视角 + 每个视角的**精确** w2c 外参与内参,
    脚本会带 `cond_flags=[cam,0,intr]` 注入相机先验, 位姿不再靠猜 —— 上游推理
    `rasterization.py` 在 `is_inference` 直接 return、不做跨视图融合, 每个视角按**自己预测的**
    位姿/深度反投影(`position_from="gsdepth+predcamera"`) ⇒ 同一表面两层壳 = 视口里的重影;
    给了精确位姿, 壳从源头就少一层。

缓存是两层的: ComfyUI 自己的节点缓存 + 本节点按**图像内容哈希**建的目录 (目录名即哈希, 相机
先验也一起入哈希)。换图/换先验必然换目录, 脚本那份同样按内容校验的 `preds.pt` 缓存随之失效。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess

import folder_paths
import numpy as np
from PIL import Image

from comfy_api.latest import io

PIXI_PY = r"C:\Users\zghyu\AppData\Local\Programs\comfy-env\.pixi\envs\hywm2-nodes\python.exe"
# 项目根由本文件位置反推 (realpath 会解开 `ComfyUI\custom_nodes` 那层目录软链),
# 于是 HYWM2 根目录跟着项目走 —— 项目整体搬家后不必再改这里。
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
# 精修脚本与本文件同目录: 它是本节点的运行期硬依赖, 而根仓库 `scripts\` 只放临时文件
# (2026-09-30 由那里搬进来, 免得哪天清理临时文件把它一起清掉)。
SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "refine_0034_gs.py")
PLUGIN_CWD = os.path.join(_ROOT, "custom_nodes", "ComfyUI-HYWM2")   # 脚本要的相对 import 根
TEMP_ROOT = os.path.join(folder_paths.get_temp_directory(), "worldrefine")
OUT_SUBDIR = "0034_世界模型"
OUT_NAME = "0034_世界模型_世界3DGS"
LEGACY_N_VIEWS = 8
SLOTS = "前面/前右/右面/右后/后面/后左/左面/左前"

logger = logging.getLogger(__name__)

# images=None (上游未接/扇出未选中) 时回放本节点最近一次产出的 PLY, 键 = UNIQUE_ID
_last_output: dict[str, str] = {}


def _to_u8(t):
    """IMAGE float 0..1 → uint8 HWC, 与 ComfyUI 存图口径一致 (±0.5 四舍五入)。"""
    return (t.detach().cpu().numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)


def _dump_batch(images, key):
    """把 IMAGE 批落成 temp\\worldrefine\\<内容哈希>\\NN.png, 返回按批序的路径列表。"""
    d = os.path.join(TEMP_ROOT, key)
    os.makedirs(d, exist_ok=True)
    paths = []
    for i in range(images.shape[0]):
        p = os.path.join(d, f"{i:02d}.png")
        Image.fromarray(_to_u8(images[i])).save(p)
        paths.append(p)
    return paths


def _as_np(t):
    """torch.Tensor → float64 numpy (先 detach/cpu); 已经不是张量就原样转。"""
    if hasattr(t, "detach"):
        return t.detach().float().cpu().numpy().astype(np.float64)
    return np.asarray(t, dtype=np.float64)


def _dump_prior(extrinsics, intrinsics, n_views, key):
    """EXTRINSICS(w2c [N,4,4] 或 [4,4]) + INTRINSICS([N,3,3] 或 [3,3]) → 相机先验 JSON。

    格式与上游 `load_prior_camera` 一致 (它按 PNG 文件名去扩展名匹配 camera_id):
        {"extrinsics": [{"camera_id": "00", "matrix": [[...]]}, ...],
         "intrinsics": [...]}
    注意上游要的是 **c2w**, 而 EXTRINSICS 输入是 w2c ⇒ 这里逐视角取逆
    (口径与 HYWM2Reconstruct._dump_camera_priors_json 相同)。

    参数:
        extrinsics: w2c 张量 [N,4,4] / [1,N,4,4] / [4,4]; None 表示不注入。
        intrinsics: 内参 [N,3,3] / [3,3] / [1,N,3,3]; None 表示不注入。
        n_views (int): 本批视图数 (校验先验数量必须对得上)。
        key (str): 本批内容哈希 (JSON 就写在该哈希目录里)。

    返回:
        str | None: 写出的 JSON 路径; 两个先验都没给时 None。
    """
    if extrinsics is None and intrinsics is None:
        return None
    d = os.path.join(TEMP_ROOT, key)
    os.makedirs(d, exist_ok=True)
    out: dict = {}

    if extrinsics is not None:
        ext = _as_np(extrinsics)
        if ext.ndim == 4 and ext.shape[0] == 1:
            ext = ext[0]
        if ext.ndim == 2 and ext.shape == (4, 4):
            ext = ext[None, ...]
        if ext.ndim == 3 and ext.shape[1:] == (3, 4):
            pad = np.tile(np.array([0, 0, 0, 1.0]), (ext.shape[0], 1, 1))
            ext = np.concatenate([ext, pad], axis=1)
        if ext.ndim != 3 or ext.shape[1:] != (4, 4):
            raise ValueError(f"WorldRefinePLY: extrinsics 形状应为 [N,4,4], 实为 {ext.shape}")
        if ext.shape[0] != n_views:
            raise ValueError(
                f"WorldRefinePLY: extrinsics 数量 {ext.shape[0]} != 视图数 {n_views}")
        c2w = np.linalg.inv(ext)
        out["extrinsics"] = [{"camera_id": f"{i:02d}", "matrix": c2w[i].tolist()}
                             for i in range(n_views)]

    if intrinsics is not None:
        intr = _as_np(intrinsics)
        if intr.ndim == 4 and intr.shape[0] == 1:
            intr = intr[0]
        if intr.ndim == 2 and intr.shape == (3, 3):
            intr = np.tile(intr[None, ...], (n_views, 1, 1))
        elif intr.ndim == 3 and intr.shape[0] == 1 and n_views > 1:
            intr = np.tile(intr, (n_views, 1, 1))
        if intr.ndim == 3 and intr.shape[1:] == (4, 4):
            intr = intr[:, :3, :3]
        if intr.ndim != 3 or intr.shape[1:] != (3, 3):
            raise ValueError(f"WorldRefinePLY: intrinsics 形状应为 [N,3,3] 或 [3,3], 实为 {intr.shape}")
        if intr.shape[0] != n_views:
            raise ValueError(
                f"WorldRefinePLY: intrinsics 数量 {intr.shape[0]} != 视图数 {n_views}")
        out["intrinsics"] = [{"camera_id": f"{i:02d}", "matrix": intr[i].tolist()}
                             for i in range(n_views)]

    path = os.path.join(d, "prior_camera.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    logger.info("[FallingTSWorldRefinePLY] 相机先验 → %s (外参 %s, 内参 %s)",
                path, "有" if "extrinsics" in out else "无",
                "有" if "intrinsics" in out else "无")
    return path


class FallingTSWorldRefinePLYNode(io.ComfyNode):
    """多视图 → 504 前馈 + 3DGS 全参数精修 → 输出最高质量 PLY 路径。"""

    @classmethod
    def define_schema(cls):
        """声明节点输入/输出。不带先验时 images 的批序必须是 前面/前右/右面/右后/后面/后左/左面/左前。"""
        return io.Schema(
            node_id="WorldRefinePLY",
            display_name="FallingTS 世界重建精修 PLY (504)",
            category="FallingTS/3D",
            description=(
                f"多视图世界重建 (504) + 3DGS 外观精修, 输出一个标准 3DGS PLY 路径。"
                f"两种用法: ① 无先验时按 {SLOTS} 批序喂 8 图; ② 接 WorldPanoramaViews 时喂任意 "
                f"N 个视角 + extrinsics/intrinsics, 位姿先验会注入前馈(从源头消重影)。"
                f"精修在 HYWM2 的隔离环境里跑 (gsplat 在那), 本节点只负责落临时图与转发路径。"
            ),
            inputs=[
                io.Image.Input(
                    "images",
                    tooltip=f"视图批: {SLOTS} (md 数据表, 8 图) 或 WorldPanoramaViews 的任意 N 视角。",
                ),
                io.Int.Input(
                    "steps",
                    default=800,
                    min=0,
                    max=5000,
                    step=50,
                    tooltip="外观精修步数; 0 = 只做前馈与尺度过滤, 不精修。",
                ),
                io.Combo.Input(
                    "mode",
                    options=["appearance", "all"],
                    default="all",
                    tooltip=(
                        "appearance = 只优化不透明度与 SH (means/四元数/log 尺度冻结, 视图各自铺的"
                        "壳动不了 ⇒ 双重曝光去不掉); all = 全参数, 会把壳收拢(去鬼影), 代价是深度不"
                        "连续处可能出'焦边'暗斑 —— 用 reg 压住。"
                    ),
                ),
                io.Float.Input(
                    "reg",
                    default=3.0,
                    min=0.0,
                    max=10.0,
                    step=0.1,
                    tooltip=(
                        "几何信任域(mode=all 时生效): 越大越贴着前馈初值。0=不管(伪影最重), 10=最干净"
                        "但收敛力度最小; 实测 3.0 能在收掉鬼影的同时把'焦边'压到轻微。"
                    ),
                ),
                io.Float.Input(
                    "reg_opac",
                    default=0.5,
                    min=0.0,
                    max=10.0,
                    step=0.1,
                    tooltip="不透明度信任域: 越大越贴着前馈初始值, 抑制精修把透明度整体推高。",
                ),
                io.Float.Input(
                    "reg_color",
                    default=0.5,
                    min=0.0,
                    max=10.0,
                    step=0.1,
                    tooltip=(
                        "颜色信任域: 每步只监督 1 个视角, 少数高斯会被撑成彩虹色去凑那一个视角, "
                        "单色(DC-only)渲染里就是墙角上的粉/绿噪点; 越大越贴着前馈的初始颜色。"
                    ),
                ),
                io.Int.Input(
                    "target",
                    default=952,
                    min=256,
                    max=2048,
                    step=8,
                    tooltip="前馈长边(几何/布局细节上限)。实际会按空闲显存自适应压低, 8GB 实测落在 504。",
                ),
                io.Int.Input(
                    "gt",
                    default=826,
                    min=0,
                    max=2048,
                    step=2,
                    tooltip="颜色精修监督用的长边(0 = 跟随前馈分辨率); 8 图路径是 826(原生), 全景视角填视角边长。",
                ),
                io.Float.Input(
                    "prune_opac",
                    default=0.0,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    tooltip="落盘前剪掉不透明度低于该值的高斯(减高斯数=减远看雾气); 0 = 不剪。",
                ),
                io.Boolean.Input(
                    "refresh",
                    default=False,
                    tooltip="忽略前馈缓存 (preds.pt) 重新前馈; 换图/换先验时内容哈希已变, 无需勾选。",
                ),
                io.Custom("EXTRINSICS").Input(
                    "extrinsics",
                    optional=True,
                    tooltip="可选的 w2c 外参 [N,4,4] (如 WorldPanoramaViews 的输出)。接了就把位姿"
                            "作为先验注入前馈, 位姿不再由模型预测 —— 消重影的关键入口。",
                ),
                io.Custom("INTRINSICS").Input(
                    "intrinsics",
                    optional=True,
                    tooltip="可选的内参 [3,3] (广播到所有视角) 或 [N,3,3]; 与 extrinsics 一起用。",
                ),
            ],
            outputs=[io.String.Output(display_name="ply_path")],
            hidden=[io.Hidden.unique_id],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, images, steps, mode, reg, reg_opac, reg_color, target, gt, prune_opac,
                refresh, extrinsics=None, intrinsics=None) -> io.NodeOutput:
        """落临时图(+相机先验) → 调隔离解释器 → 回传 PLY 路径。

        参数:
            images (IMAGE): 视图批, 无先验时批序 前面…左前 (8 张)。
            steps (int): 精修步数。
            mode (str): "all"(默认, 连几何一起修, 去多视图双重曝光) | "appearance"(只修颜色+透明度)。
            reg (float): 几何信任域强度(mode=all 时生效)。
            reg_opac (float): 不透明度信任域强度。
            reg_color (float): 颜色(DC)信任域强度。
            target (int): 前馈长边(实际按空闲显存自适应压低)。
            gt (int): 颜色精修监督长边(0 = 跟随前馈)。
            prune_opac (float): 落盘前剪掉不透明度低于该值的高斯。
            refresh (bool): 是否忽略前馈缓存。
            extrinsics: 可选 w2c 外参 [N,4,4] (相机先验)。
            intrinsics: 可选内参 [3,3] 或 [N,3,3]。

        返回:
            io.NodeOutput: 单元素 (PLY 绝对路径,); images 为空时回放上次路径, 从未产出则空串。
        """
        uid = str(cls.hidden.unique_id or "")
        if images is None:
            # None 只表示"本次没有数据", 不等于"清空": 回放上次产出的 PLY, 否则交给下游视口报错
            cached = _last_output.get(uid, "")
            if cached and os.path.isfile(cached):
                logger.info("[FallingTSWorldRefinePLY] images 为空, 回放上次 PLY: %s", cached)
                return io.NodeOutput(cached)
            logger.warning("[FallingTSWorldRefinePLY] images 为空且从无产出, 输出空路径")
            return io.NodeOutput("")

        n_views = int(images.shape[0])
        if n_views < 2:
            raise ValueError(f"WorldRefinePLY: 至少要 2 个视图, 实际 {n_views}")
        if extrinsics is None and intrinsics is None and n_views != LEGACY_N_VIEWS:
            logger.warning("[FallingTSWorldRefinePLY] 无相机先验且视图数 %d != %d, 位姿全靠模型预测",
                           n_views, LEGACY_N_VIEWS)

        h = hashlib.sha1()
        for i in range(n_views):
            h.update(_to_u8(images[i]).tobytes())
        for t in (extrinsics, intrinsics):
            if t is not None:                                  # 先验也入哈希: 换位姿必须换缓存
                h.update(_as_np(t).tobytes())
        key = h.hexdigest()[:16]
        paths = _dump_batch(images, key)
        prior = _dump_prior(extrinsics, intrinsics, n_views, key)

        out_dir = os.path.join(folder_paths.get_output_directory(), OUT_SUBDIR)
        expected = os.path.join(out_dir, OUT_NAME + ".ply")
        cmd = [PIXI_PY, SCRIPT,
               "--views", ";".join(paths),
               "--cache", os.path.join(TEMP_ROOT, key, "preds.pt"),
               "--asset-dir", out_dir,
               "--out-name", OUT_NAME,
               "--steps", str(int(steps)),
               "--mode", mode,
               "--reg", str(float(reg)),
               "--reg-opac", str(float(reg_opac)),
               "--reg-color", str(float(reg_color)),
               "--target", str(int(target)),
               "--gt", str(int(gt)),
               "--prune-opac", str(float(prune_opac))]
        if refresh:
            cmd.append("--refresh")
        if prior:
            cmd += ["--prior-camera", prior]

        logger.info(
            "[FallingTSWorldRefinePLY] %d 视图%s → 前馈长边 %s + 精修 %s 步 "
            "(%s, reg=%s, reg_opac=%s, reg_color=%s) + 颜色监督 %s + 剪枝 %s, 哈希 %s",
            n_views, "(含相机先验)" if prior else "", target, steps, mode, reg, reg_opac,
            reg_color, gt, prune_opac, key)
        # 子进程输出一律 UTF-8: Windows 下管道 stdout 默认退回 GBK, 而含中文的产物路径
        # (output\0034_世界模型\...) 按 UTF-8 解出来是 \ufffd ⇒ 路径失效、日志也写不进 GBK 控制台。
        # 环境与解码两端都钉死, 不依赖启动 ComfyUI 时带没带 PYTHONUTF8。
        child_env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        r = subprocess.run(cmd, cwd=PLUGIN_CWD, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=child_env)
        for line in (r.stdout or "").splitlines():
            logger.info("  [refine] %s", line.replace("\ufffd", "?"))
        if r.returncode != 0:
            raise RuntimeError(
                f"WorldRefinePLY: 精修脚本退出码 {r.returncode}\n"
                f"--- stdout 末尾 ---\n{(r.stdout or '')[-2000:]}\n"
                f"--- stderr 末尾 ---\n{(r.stderr or '')[-2000:]}")

        out = next((ln[6:].strip() for ln in (r.stdout or "").splitlines() if ln.startswith("[OUT] ")), "")
        if out and not os.path.isfile(out):
            logger.warning("[FallingTSWorldRefinePLY] stdout 报出的路径不存在(疑管道编码), 丢弃: %r", out)
            out = ""
        if not out and os.path.isfile(expected):
            # 兜底: 路径本来就是本节点用 --asset-dir/--out-name 约定的, 不看 stdout 也知道。
            logger.warning("[FallingTSWorldRefinePLY] stdout 没给出 PLY 路径, 回退约定路径: %s", expected)
            out = expected
        if not out:
            raise RuntimeError(f"WorldRefinePLY: 脚本没报出 PLY 路径\n{(r.stdout or '')[-2000:]}")

        _last_output[uid] = out
        return io.NodeOutput(out)


NODE_CLASS_MAPPINGS = {
    "WorldRefinePLY": FallingTSWorldRefinePLYNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WorldRefinePLY": "FallingTS 世界重建精修 PLY (504)",
}
