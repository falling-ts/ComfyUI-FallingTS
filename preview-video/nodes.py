# PreviewVideo 节点: 预览视频 + 点「保存」才写入 output 目录。
# 参照 PreviewImageSave(preview-image/nodes.py) 的「始终预览(temp)+ 保存按钮写 output」模式。
# 原理: VIDEO 是惰性内存对象, 核心 WebSocket 协议只有图片预览事件;
#       本节点把 VIDEO 编码成 mp4 写到【临时目录】(temp, 非 output),
#       再通过 UI.PreviewVideo 让前端播放临时文件 —— "不满意就不保存"。
#       点「保存」按钮时, 后端用 execute 缓存的视频按 {filename_prefix}{filename_suffix}.mp4
#       直接写 output(同名覆盖, 不带 _序号 后缀), 不重跑工作流。
#       filename_suffix 默认空串, 可手动输入或上游连线, 保存时拼接在前缀之后。
#
# 截帧/完成/选中帧输出已迁至 load-video 的 FallingTSLoadVideo 节点(2026-10-02):
# 本节点此后只保留「预览 + 保存」两件事, 与核心 SaveVideo 的分工一致(不落盘, 点保存才写);
# 输出只剩 video(原样透传), 不再有 image_1..image_64 的截帧槽。

from __future__ import annotations

import logging
import os
import random
import string
from urllib.parse import quote

from aiohttp import web
from server import PromptServer

from comfy_api.latest import IO, Types, UI
import folder_paths

from output_subdir import resolve_subdir, safe_dir_name

_NODE_NAME = "PreviewVideo"

# 最近一次预览的视频缓存: 缓存键 -> 视频数据
# 点「保存」时前端把文件名 POST 过来, 后端直接用缓存处理(无需重跑工作流)
# 缓存键 = "<工作流根 id>::<节点 id>"(见 _scoped_key), 只按节点 id 会跨工作流串片
_last_output: dict[str, dict] = {}

# 重置代际: /preview-video/reset 时递增, 纳入 fingerprint_inputs -> 每次 Run 后指纹必变,
# 强制本节点重新执行(不被 ComfyUI 全局执行缓存跳过, 否则预览停在旧 temp 文件上)。
_reset_generation: int = 0


def _workflow_scope(extra_pnginfo) -> str:
    """从 extra_pnginfo 取当前工作流的根 id, 作为缓存键的工作流作用域。

    与 preview-image 同口径: 该 id 就是工作流 JSON 的根 id(前端 graph.serialize().id;
    graphToPrompt() 把 graph.serialize() 整个塞进 extra_pnginfo.workflow, 所以这里取到的
    和前端 app.rootGraph.id 是同一个值)。

    **为什么必须带工作流作用域**: 只按节点 id 缓存会跨工作流串片 —— 节点 id 在各工作流之间
    大量重复, 打开工作流 B 时会把之前跑过的 A 的同 id 节点预览当成 B 的预览播放出来。

    参数:
        extra_pnginfo (dict|None): hidden 里的额外元数据。

    返回:
        str: 工作流根 id; 取不到(如无头 API 直接提交)时返回空串。
    """
    if not isinstance(extra_pnginfo, dict):
        return ""
    workflow = extra_pnginfo.get("workflow")
    if not isinstance(workflow, dict):
        return ""
    return str(workflow.get("id") or "").strip()


def _scoped_key(node_id, workflow_id=None) -> str:
    """把 (工作流 id, 节点 id) 拼成缓存键; 工作流 id 缺失时退回纯节点 id。

    参数:
        node_id (str|int|None): 节点唯一 ID。
        workflow_id (str|None): 工作流根 id(见 _workflow_scope)。

    返回:
        str: 缓存键 "<工作流 id>::<节点 id>", 或纯 "<节点 id>"。
    """
    nid = str(node_id or "")
    wid = str(workflow_id or "").strip()
    return f"{wid}::{nid}" if wid and nid else nid


def _cache_get(cache: dict, node_id, workflow_id=None):
    """按 (工作流, 节点) 读缓存: 优先带工作流标识的键, 再退回纯节点 id。

    退回纯节点 id 是为了兼容「那次执行没带工作流标识」的写入(无头 API 提交时
    extra_pnginfo 为空), 否则页面刷新后这类预览就再也读不回来了。

    参数:
        cache (dict): 缓存字典(本模块即 _last_output)。
        node_id (str|int|None): 节点唯一 ID。
        workflow_id (str|None): 调用方声明的当前工作流根 id。

    返回:
        dict|None: 命中的缓存; 未命中返回 None。
    """
    keys = [str(node_id or "")]
    if workflow_id:
        keys.insert(0, _scoped_key(node_id, workflow_id))
    for key in keys:
        if key in cache:
            return cache[key]
    return None


def _safe_dir_name(name) -> str:
    """把工作流名清洗成可安全用作单层目录名的字符串(实现见 output_subdir.safe_dir_name)。"""
    return safe_dir_name(name)


def _workflow_output_dir(workflow_name, prompt=None) -> str:
    """取保存目录: output 下按子目录名建目录, 不存在则创建; 名字非法时退回 output 根。

    子目录名由 output_subdir.resolve_subdir 解析 —— 工作流里有 md 数据表节点时用它的
    表文件名, 没有 md 表节点才用工作流名(理由见该模块头部说明)。
    """
    base = folder_paths.get_output_directory()
    sub = resolve_subdir(workflow_name, prompt)
    if not sub:
        return base
    target = os.path.join(base, sub)
    os.makedirs(target, exist_ok=True)
    return target


def _encode_temp_preview(video):
    """把视频编码成一份 temp 预览 mp4, 返回 (文件名, 子目录)。

    口径与 execute 完全一致(随机前缀 + 5 位计数 + mp4), 供「temp 被清理后现场重建」复用,
    使重建出来的文件名与首次预览同形, 前端无需区分。

    参数:
        video: 视频对象(惰性内存对象)。

    返回:
        tuple[str, str]|None: (文件名, 子目录); 编码失败返回 None。
    """
    width, height = video.get_dimensions()
    prefix = "ComfyUI_temp_" + "".join(random.choice(string.ascii_lowercase) for _ in range(5))
    full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
        prefix,
        folder_paths.get_temp_directory(),
        width,
        height,
    )
    ext = Types.VideoContainer.get_extension("mp4")
    file = f"{filename}_{counter:05}_.{ext}"
    video.save_to(
        os.path.join(full_output_folder, file),
        format=Types.VideoContainer.MP4,
        codec=Types.VideoCodec.AUTO,
    )
    return file, subfolder


def _temp_preview_exists(cache: dict) -> bool:
    """校验缓存里那份 temp 预览文件是否还在磁盘上。

    temp 目录随时会被 ComfyUI 清理, 文件不在时绝不能把它的文件名返给前端 —— 前端播放器
    指过去就是 404, 实测表现是节点上「视频加载失败 / Invalid URL」。

    参数:
        cache (dict): 预览缓存(含 file / subfolder)。

    返回:
        bool: 文件存在为 True。
    """
    file = cache.get("file")
    if not file:
        return False
    path = os.path.join(folder_paths.get_temp_directory(), cache.get("subfolder") or "", file)
    return os.path.isfile(path)


def _ensure_temp_preview(cache: dict):
    """保证缓存里有一份**真实存在**的 temp 预览文件, 没有就现场重编码一份。

    与 load-video 的 _ensure_temp_preview 同口径: temp 被清理时用缓存的视频对象重编码,
    并把新文件名写回缓存; 编不出来(视频对象已失效)返回 None, 由调用方决定兜底。

    参数:
        cache (dict): 预览缓存(含 video / file / subfolder)。

    返回:
        tuple[str, str]|None: (文件名, 子目录); 无法提供时返回 None。
    """
    if _temp_preview_exists(cache):
        return cache.get("file"), cache.get("subfolder") or ""
    video = cache.get("video")
    if video is None:
        return None
    try:
        encoded = _encode_temp_preview(video)
    except Exception:  # noqa: BLE001 - 重编码失败只告警, 不让整次请求 500
        logging.exception("[FallingTS] 重建视频 temp 预览失败")
        return None
    if not encoded:
        return None
    cache["file"], cache["subfolder"] = encoded
    return encoded


def _temp_url(file: str, subfolder: str = "") -> str:
    """拼 temp 文件的 /view URL。

    参数:
        file (str): 文件名。
        subfolder (str): 子目录(可空)。

    返回:
        str: 可播放的 /view URL。
    """
    return f"/view?filename={quote(file)}&subfolder={quote(subfolder)}&type=temp"


class PreviewVideoNode(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: 节点元数据, 含 node_id/display_name/category/description,
            输入 video + filename_prefix + filename_suffix, 输出 video,
            hidden 含 prompt+extra_pnginfo+unique_id, 标记 is_output_node=True。
        """
        return IO.Schema(
            node_id=_NODE_NAME,
            display_name="Preview Video (保存)",
            category="FallingTS",
            description=(
                "Preview the video without saving it to the ComfyUI output directory; "
                "click 保存 to write it to output as {filename_prefix}{filename_suffix}.mp4 (no sequence suffix). "
                "Encodes to the temp folder for preview."
            ),
            inputs=[
                IO.Video.Input(
                    "video",
                    tooltip="要预览的视频(None = 无值, 如扇出未选中分支, 跳过预览, 输出该节点最近一次预览的视频供下游)。",
                ),
                IO.String.Input(
                    "filename_prefix",
                    default="video",
                    multiline=False,
                    tooltip="保存到 output 的文件名(不含扩展名); 同名直接覆盖, 无序号",
                ),
                IO.String.Input(
                    "filename_suffix",
                    default="",
                    multiline=False,
                    tooltip="文件名后缀(不含扩展名, 默认空); 保存时拼接在 filename_prefix 之后: {filename_prefix}{filename_suffix}.mp4",
                ),
            ],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo, IO.Hidden.unique_id],
            is_output_node=True,
            outputs=[IO.Video.Output("video", tooltip="预览/保存的视频。")],
        )

    @classmethod
    def execute(cls, video, filename_prefix: str = "video", filename_suffix: str = "") -> IO.NodeOutput:
        """节点执行入口: 把视频编码为 mp4 写入临时目录并在前端播放, 输出该视频(原样透传)。

        video 为 None (扇出未选中分支 / 上游无值)时回放上次预览事件并输出缓存视频,
        从未预览过则输出 None(下游按无值处理), 绝不抛异常。

        参数:
            video (Video|None): 要预览的视频对象(惰性内存对象)。
            filename_prefix (str, 默认 "video"): 保存文件名前缀(控件; 被上游连线时本参数为实际接收值)。
            filename_suffix (str, 默认 ""): 文件名后缀(控件, 保存时拼接在前缀之后)。

        返回:
            IO.NodeOutput: 视频 + UI.PreviewVideo 预览事件(temp 文件)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        # 工作流 prompt / extra_pnginfo 只能从 hidden 取 —— V3 节点的 hidden 不进 execute 实参。
        prompt = getattr(cls.hidden, "prompt", None)
        # 工作流根 id: 给预览缓存加作用域, 只按节点 id 缓存会跨工作流串片
        wid = _workflow_scope(getattr(cls.hidden, "extra_pnginfo", None))
        key = _scoped_key(nid_str, wid)

        if video is None:
            cached = _cache_get(_last_output, nid_str, wid)
            # 回放同样要保证 temp 文件真的还在: 不在就现场重编码一份, 编不出才不发预览事件
            got = _ensure_temp_preview(cached) if cached else None
            if got:
                file, subfolder = got
                return IO.NodeOutput(
                    cached.get("video"),
                    ui=UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)]),
                )
            return IO.NodeOutput(cached.get("video") if cached else None)

        encoded = _encode_temp_preview(video)
        if encoded is None:
            # 编码失败不中断工作流: 只告警, 照常把视频透传给下游
            logging.warning("[FallingTS] PreviewVideo 编码 temp 预览失败, 本次不刷新预览")
            if nid_str:
                _last_output[key] = {
                    "video": video,
                    "filename_prefix": filename_prefix,
                    "filename_suffix": filename_suffix,
                    "prompt": prompt,
                    "file": None,
                    "subfolder": "",
                }
            return IO.NodeOutput(video)

        file, subfolder = encoded
        if nid_str:
            _last_output[key] = {
                "video": video,
                "filename_prefix": filename_prefix,
                "filename_suffix": filename_suffix,
                "prompt": prompt,
                "file": file,
                "subfolder": subfolder,
            }
        return IO.NodeOutput(
            video,
            ui=UI.PreviewVideo([UI.SavedResult(file, subfolder, IO.FolderType.temp)]),
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        """缓存失效签名: 重置代际 + 节点 id。

        /preview-video/reset 递增 _reset_generation, 使每次默认 Run 后本节点必然重新执行
        (重新编码 temp 并发出预览事件), 不被 ComfyUI 全局执行缓存跳过 —— 否则预览会停在
        上一次的 temp 文件上(该文件一旦被清理, 播放就报「视频加载失败」)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        return (_reset_generation, str(nid) if nid else "")


async def _handle_reset(request: web.Request) -> web.Response:
    """重置所有 PreviewVideo(前端默认 Run / 无帧点「完成」时调用): 递增代际强制重跑。"""
    global _reset_generation
    _reset_generation += 1
    return web.json_response({"status": "ok"})


async def _handle_clear(request: web.Request) -> web.Response:
    """保留端点但**不清任何状态**(后端是唯一事实来源, 刷新后由前端读回重建)。"""
    return web.json_response({"status": "ok"})


async def _handle_video_url(request: web.Request) -> web.Response:
    """HTTP 路由: 返回该节点当前缓存视频的可播放 URL, 供前端在刷新后重建预览。

    节点原生的 UI.PreviewVideo 是一次性 WebSocket 事件, 页面刷新后不会重发, 视频预览
    就空了。前端因此在节点上备一个 <video>, 页面加载/刷新时调本路由拿 URL 填上。
    """
    nid = request.match_info["node_id"].strip()
    wid = (request.query.get("workflow_id") or "").strip()
    cache = _cache_get(_last_output, nid, wid)
    if not cache or not cache.get("video"):
        return web.json_response({"status": "error", "message": "没有可预览的视频, 请先运行到该节点"}, status=400)
    # temp 目录随时被清理: 文件不在就现场重编码一份, 绝不把已删除的文件名返给前端
    # (实测表现 = 节点上「视频加载失败 / Invalid URL」)
    got = _ensure_temp_preview(cache)
    if not got:
        return web.json_response(
            {"status": "error", "message": "预览文件已被清理且无法重建, 请重新运行到该节点"}, status=400
        )
    file, subfolder = got
    return web.json_response({"status": "ok", "url": _temp_url(file, subfolder)})


async def _handle_save(request: web.Request) -> web.Response:
    """HTTP 路由: 用缓存视频把该节点最近预览的视频写入 output(同名覆盖, 无序号)。

    流程: 前端点「保存」按钮时把文件名前缀+后缀 POST 过来;
    后端查 _last_output[node_id](execute 时缓存的视频), 有则编码写 output, 无则 400。
    全程不触发任何工作流重跑。文件名 = {filename_prefix}{filename_suffix}.mp4, 不带 _0001 序列后缀。
    """
    nid = request.match_info["node_id"].strip()
    # workflow_id 由前端带过来(app.rootGraph.id): 保存必须用**当前工作流**的预览缓存,
    # 只按节点 id 查会把别的工作流同 id 节点的预览存进来(跨工作流串片)
    wid = None
    try:
        _body = await request.json()
    except Exception:
        _body = {}
    if isinstance(_body, dict):
        wid = str(_body.get("workflow_id") or "").strip() or None
    data = _body if isinstance(_body, dict) else {}
    cache = _cache_get(_last_output, nid, wid)
    if not cache or not cache.get("video"):
        return web.json_response(
            {"status": "error", "message": "没有预览数据, 请先运行到该节点"}, status=400
        )

    filename_prefix = str(data.get("filename_prefix", "video"))
    # 若 filename_prefix 输入被上游连线, widget 值是占位符: 用 execute 时实际接收到的值
    if data.get("filename_prefix_linked") and cache.get("filename_prefix"):
        filename_prefix = str(cache["filename_prefix"])
    # 后缀同前缀: 连线时用 execute 实际接收值; 空串 = 不拼后缀
    filename_suffix = str(data.get("filename_suffix") or "")
    if data.get("filename_suffix_linked") and cache.get("filename_suffix") is not None:
        filename_suffix = str(cache["filename_suffix"])
    name = filename_prefix + filename_suffix

    video = cache["video"]
    output_dir = _workflow_output_dir(data.get("workflow_name"), cache.get("prompt"))
    ext = Types.VideoContainer.get_extension("mp4")
    file_path = os.path.join(output_dir, f"{name}.{ext}")
    video.save_to(
        file_path,
        format=Types.VideoContainer.MP4,
        codec=Types.VideoCodec.AUTO,
    )
    saved_dir = resolve_subdir(data.get("workflow_name"), cache.get("prompt"))
    where = f"{saved_dir}/" if saved_dir else ""
    return web.json_response(
        {"status": "ok", "message": f"已保存: {where}{name}.{ext}"}
    )


PromptServer.instance.routes.post("/preview-video/save/{node_id}")(_handle_save)
PromptServer.instance.routes.post("/preview-video/reset")(_handle_reset)
PromptServer.instance.routes.get("/preview-video/video-url/{node_id}")(_handle_video_url)
PromptServer.instance.routes.post("/preview-video/clear")(_handle_clear)
