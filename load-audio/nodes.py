# load-audio/nodes.py
r"""FallingTS 加载音频 (来自输出)。

参考内置 LoadAudio(ComfyUI/comfy_extras/nodes_audio.py) 与本插件的加载节点约定:

1. **下拉候选由自身路由 GET /fallingts_load_audio/files 提供**: 内置 LoadAudio 从
   **input** 目录取(input_directory 的一层), 而本工作区的音频产物落在 output 的数字目录里
   (0060_背景音乐/、0061_环境音效/ …)。本路由按「媒体资产」侧栏同一口径扫描:
   output 根目录的音频 + **数字目录(正则 ^\d+_)内部整棵子树的音频**, 按 mtime 倒序,
   值形如 0060_背景音乐/00001_夜雨.mp3(**不带 " [output]" 标注** —— 前端给候选算预览
   一律拼 type=input 且不剥离标注, 带标注会让 /api/view 404; 本节点的解码与「可播放 URL」
   都用 get_annotated_filepath(..., default_dir=output) 解析, 不必靠后缀)。

2. **「名称」+「序列号」+「刷新序列号」**: 与「加载图像 / 加载视频」同一套 ——
   序列号 = output/<产物目录>/ 里已有编号的最大值 + 1(目录不存在或没有 "数字_" 命名的文件时为
   0, 显示成 5 位 00000), 可手改, 按钮随时重算; 目录口径走共用的 output_subdir
   (有 md 数据表用表文件名, 没有才用工作流名)。

3. **remote 不设 control_after_refresh** —— 刷新按钮与跑完自动刷新只重新拉候选列表,
   不把已选值换成候选首项(候选按 mtime 倒序 ⇒ 刚产出的音频必然夺走选中权)。

4. **「序列号_名称」前缀输出**: `prefix`(STRING) = `<序列号>_<名称>`(口径见 output_subdir.sequence_prefix),
   接各预览保存节点的 `filename_prefix` —— 截取/拆音这类工作流不再需要 md 数据表提供文件名前缀。

5. **节点内试听**(与「预览音频」同一套"执行前后都能听"的体验, 但走前端原生音频控件):
   声明一个 AUDIO_UI 输入 ⇒ 前端 Comfy.AudioWidget 的 AUDIO_UI 工厂给节点挂上
   <audio controls> DOM 播放器(页面刷新后靠 onGraphConfigured 按已选值重建, 不依赖一次性事件);
   执行时再发 UI.PreviewAudio ⇒ 跑完播放器自动指向本次解码出来的音频。
   ⚠️ 这个输入**必须声明**: 前端 Comfy.UploadAudio 的上传按钮要求节点上存在名为 audioUI 的控件,
   否则**创建节点时直接抛 TypeError**(内置 LoadAudio 由前端按 comfyClass 白名单自动补, 自定义节点
   得自己写)。「保存」不复制: 写盘仍归 PreviewAudioSave。
"""

from __future__ import annotations

import logging
import os
import re

from aiohttp import web
from server import PromptServer

import folder_paths
from comfy_api.latest import IO, UI
from comfy_extras.nodes_audio import load

from output_subdir import next_sequence, sequence_dir, sequence_prefix

logger = logging.getLogger(__name__)

_NODE_NAME = "FallingTSLoadAudio"
_ROUTE = "/fallingts_load_audio"

# 资源表目录口径: 数字开头 + 下划线(0060_背景音乐 / 0061_环境音效 …)
_NUMERIC_DIR_RE = re.compile(r"^\d+_")


# ─── 下拉列表: output 根 + 数字目录内部的音频 ────────────────────────────────


def _is_audio_file(name: str) -> bool:
    """按扩展名判音频(复用核心的 MIME 缓存, 与内置 LoadAudio 同口径)。"""
    return bool(folder_paths.filter_files_content_types([name], ["audio"]))


def _collect_output_items(directory: str, prefix: str = "") -> list[tuple[float, str]]:
    """递归收集 (mtime, "sub/name.ext") 项(值不带 " [output]" 标注, 见模块 docstring)。

    - prefix 为空(output 根): 只递归**数字目录** —— output 里还有 clipspace 这类
      非资源目录, 不把它们的内容混进下拉;
    - prefix 非空(已在数字目录内): 整棵子树都收(资源目录内部允许再分层)。
    """
    items: list[tuple[float, str]] = []
    try:
        entries = list(os.scandir(directory))
    except OSError as e:
        logger.warning("扫描 output 目录失败 %s: %s", directory, e)
        return items

    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                if prefix or _NUMERIC_DIR_RE.match(entry.name):
                    items.extend(_collect_output_items(entry.path, prefix + entry.name + "/"))
                continue
            if not entry.is_file() or not _is_audio_file(entry.name):
                continue
            items.append((entry.stat().st_mtime, prefix + entry.name))
        except OSError:
            continue
    return items


def _list_relative(directory: str) -> list[str]:
    """按相对路径列出目录里的音频(供 define_schema 的初始候选; 每次 /object_info 现扫)。"""
    return sorted(name for _, name in _collect_output_items(directory))


# ─── 路由 ──────────────────────────────────────────────────────────────────


@PromptServer.instance.routes.get(_ROUTE + "/files")
async def _list_output_files(request: web.Request) -> web.Response:
    """给节点的下拉喂候选值: output 根 + 数字目录内部的音频, 按 mtime 倒序。

    返回形如 ["0060_背景音乐/00001_夜雨.mp3", "开场.wav"] 的数组(不带 " [output]" 标注,
    见模块 docstring), 前端 remote 组件直接把它当 widget.options.values 用。
    """
    items = _collect_output_items(folder_paths.get_output_directory())
    items.sort(key=lambda item: -item[0])
    return web.json_response([value for _, value in items])


@PromptServer.instance.routes.get(_ROUTE + "/next_sequence")
async def _handle_next_sequence(request: web.Request) -> web.Response:
    """返回该工作流产物目录里的下一个可用编号(前端在节点创建/刷新时拉取)。

    query: workflow_name(当前工作流名) 或 dir(直接指定目录名, 优先)。
    返回: {"status":"ok","sequence":int,"directory":"<子目录名>","exists":bool}。
    目录不存在/没有编号文件时 sequence 为 0(前端显示成 00000)。
    """
    query = request.rel_url.query
    directory = sequence_dir(query.get("workflow_name"), directory=query.get("dir"))
    return web.json_response(
        {
            "status": "ok",
            "sequence": next_sequence(directory),
            "directory": directory,
            "exists": os.path.isdir(directory),
        }
    )


# ─── 节点 ──────────────────────────────────────────────────────────────────


class FallingTSLoadAudioNode(IO.ComfyNode):
    """加载音频 (来自输出): 内置 LoadAudio 的超集(数字目录下拉 + 名称/序列号 + 节点内试听)。"""

    @classmethod
    def define_schema(cls) -> IO.Schema:
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: node_id/display_name/category/description, 输入 name + sequence + audio,
            输出 audio + prefix(序列号_名称), hidden 含 prompt+extra_pnginfo+unique_id,
            标记 is_output_node=True(节点自带试听播放器, 单独 Run 即可加载并播放)。
        """
        files = _list_relative(folder_paths.get_output_directory())
        return IO.Schema(
            node_id=_NODE_NAME,
            search_aliases=["load audio", "audio file", "加载音频", "来自输出"],
            display_name="FallingTS 加载音频 (来自输出)",
            category="FallingTS",
            description=(
                "Load an audio file from the output directory (including files inside numbered "
                "subdirectories) and play it inside the node; 「序列号」是该工作流产物目录里下一个可用编号, "
                "「名称」是配套的文件名(保存仍由 Preview Audio 节点负责)。"
            ),
            inputs=[
                IO.String.Input(
                    "name",
                    default="",
                    multiline=False,
                    tooltip="文件名(供下游/保存命名用); 本节点只负责加载与试听",
                ),
                IO.String.Input(
                    "sequence",
                    default="",
                    multiline=False,
                    tooltip="编号: 自动取产物目录里已有编号的最大值 + 1(目录为空时为 00000), 可手动改",
                ),
                IO.Combo.Input(
                    "audio",
                    options=files,
                    upload=IO.UploadType.audio,
                    image_folder=IO.FolderType.output,
                    remote=IO.RemoteOptions(
                        route=_ROUTE + "/files",
                        refresh_button=True,
                        # 不设 control_after_refresh: 刷新/跑完自动刷新只重新拉候选, 不改写已选值
                        control_after_refresh=None,
                    ),
                    tooltip="要加载的音频(下拉来自 output 目录, 含数字目录内部的资源; 也可直接上传)",
                ),
                # 前端按输入类型 AUDIO_UI 建节点内播放器(见模块 docstring 第 4 条); 后端不读它。
                # ⚠️ 必须 optional: 该 DOM 控件在前端是 serialize=false, 提交 prompt 时**不带**它
                # (实测 graphToPrompt 的 inputs 里没有 audioUI), 声明成 required 会让每次 Run 都
                # 报 "Required input is missing: audioUI"; 无头 API 提交同理。
                IO.Custom("AUDIO_UI").Input(
                    "audioUI",
                    optional=True,
                    tooltip="节点内试听播放器(前端原生音频控件, 后端不读)",
                ),
                # 下拉是 COMBO, 前端不允许把 AUDIO 连进 COMBO, 故另开一个 AUDIO 口给
                # 「数据表 原声音 列」这类外部来源(与加载视频的 video_in 同一套做法)
                IO.Audio.Input(
                    "audio_in",
                    optional=True,
                    tooltip="可选: 外部传入的音频(如数据表「原声音」列); 连上就用它, 不连则用上面的下拉",
                ),
            ],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo, IO.Hidden.unique_id],
            is_output_node=True,
            outputs=[
                IO.Audio.Output("audio", tooltip="加载的音频(供下游试听/截段/保存)。"),
                # 端口名保持 ASCII(前端 load_audio.js 给它挂中文 label「文件名前缀」);
                # 不设 display_name —— 设了 object_info 的 output_name 与前端端口名都会变成中文,
                # 与「加载视频」的同一端口不一致
                IO.String.Output(
                    "prefix",
                    tooltip="「序列号_名称」: 接各预览保存节点的 filename_prefix。",
                ),
            ],
        )

    @classmethod
    def execute(cls, audio=None, audio_in=None, name: str = "", sequence: str = "") -> IO.NodeOutput:
        """节点执行入口: 取音频(外部传入优先, 否则从 output 目录读文件) → 输出 AUDIO 对象。

        参数:
            audio (str | None): 音频文件名(相对 output, 形如 0060_背景音乐/00001_夜雨.mp3)。
            audio_in (dict | None): 上游直接给的 AUDIO(如数据表「原声音」列), 有值时优先于 audio。
            name (str, 默认 ""): 配套文件名(本节点不写盘, 仅记录给下游/前端)。
            sequence (str, 默认 ""): 配套编号(同上)。

        返回:
            IO.NodeOutput: 音频对象 {"waveform": BxCxN, "sample_rate": int} + 「序列号_名称」前缀 +
            UI.PreviewAudio。
        """
        prefix = sequence_prefix(sequence, name)
        if audio_in is not None:
            return IO.NodeOutput(audio_in, prefix, ui=UI.PreviewAudio(audio_in, cls=cls))
        if not audio:
            raise ValueError("FallingTS 加载音频: 没有选择音频(下拉), 也没有连接 audio_in")

        audio_path = folder_paths.get_annotated_filepath(
            audio, default_dir=folder_paths.get_output_directory()
        )
        waveform, sample_rate = load(audio_path)
        audio_obj = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}
        # 发预览事件: 前端 AUDIO_UI 播放器据此把播放源指向本次解码出来的音频
        return IO.NodeOutput(audio_obj, prefix, ui=UI.PreviewAudio(audio_obj, cls=cls))

    @classmethod
    def fingerprint_inputs(cls, audio=None, audio_in=None, **kwargs):
        """缓存失效签名: 文件 mtime + 大小(audio_in 分支只需一个稳定标记)。

        音频文件可能很大(整段 wav), 故不像内置 LoadAudio 那样对内容做 sha256, 用
        (mtime, size) 判定"文件换过了" —— 换文件/重新导出必然触发重跑。
        走 audio_in 时本节点只做透传, 签名含义由上游节点自己的 fingerprint/IS_CHANGED 决定
        (ComfyUI 的缓存签名串会带上全部祖先节点的签名), 这里给个稳定标记即可。
        """
        if audio_in is not None:
            return ("audio_in",)
        try:
            path = folder_paths.get_annotated_filepath(
                audio, default_dir=folder_paths.get_output_directory()
            )
            stat = os.stat(path)
            return (audio, stat.st_mtime, stat.st_size)
        except Exception:
            return (audio,)

    @classmethod
    def validate_inputs(cls, audio=None, audio_in=None, input_types=None, **kwargs) -> bool | str:
        """文件不存在时给出明确提示(内置口径; 值默认按 output 解析)。

        ⚠️ 校验阶段**连线的输入拿不到值** —— execution.py 的 get_input_data 在
        execution_list 为空时把 linked 输入标成 missing(实参为 None), 所以「音频是从 audio_in
        连进来的」这件事**不能靠 audio_in is None 判断**, 否则会把"下拉为空但已连线"误判成
        「Invalid audio file: 」而拦掉整次提交(实测 0070 的 audio_in 图即此症状)。
        判定办法: 声明 input_types 形参 —— ComfyUI 会把各连线输入的上游类型传进来
        (execution.py: `input_filtered['input_types'] = [received_types]`)。
        """
        if "audio_in" in (input_types or {}) or audio_in is not None:
            return True
        if not audio:
            return "请选择音频文件(下拉)或把音频连到 audio_in"
        try:
            path = folder_paths.get_annotated_filepath(
                audio, default_dir=folder_paths.get_output_directory()
            )
        except ValueError:
            return "Invalid audio file: {}".format(audio)
        if not os.path.isfile(path):
            return "Invalid audio file: {}".format(audio)
        return True
