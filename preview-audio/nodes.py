# preview-audio/nodes.py
"""PreviewAudioSave 节点: 始终预览(temp), 点「保存」写 output —— 纯预览+保存, 不切段。

切段(波形选区 → 多段输出)已拆到独立节点 audio-trim(FallingTSAudioTrim)。

参照:
- 预览部分照原生 PreviewAudio(nodes_audio.py): UI.PreviewAudio → 写 temp 音频;
- 保存部分照原生 SaveAudioAdvanced: 支持 flac/mp3/opus(+quality) 编码, 写
  {filename_prefix}{filename_suffix}.{format}, 同名覆盖无序号; 点「保存」不重跑工作流。
- audio 为 None(扇出未选中分支)时回放上次预览并输出该节点最近一次预览的音频(sticky)。
"""

from __future__ import annotations

import logging
import os
from io import BytesIO
from typing import Any
from urllib.parse import quote

import av
import torch

from aiohttp import web
from server import PromptServer

from comfy_api.latest import IO, UI
import folder_paths

try:
    import torchaudio

    TORCH_AUDIO_AVAILABLE = True
except ImportError:
    TORCH_AUDIO_AVAILABLE = False

_OPUS_RATES = [8000, 12000, 16000, 24000, 48000]
_FORMATS = {"flac", "mp3", "opus"}

# 保存目标目录名里不允许出现的字符(Windows 非法字符 + 路径分隔符)
_UNSAFE_CHARS = '<>:"/\\|?*'


def _safe_dir_name(name) -> str:
    """把工作流名清洗成可安全用作单层目录名的字符串。

    参数:
        name (str|None): 前端传来的工作流名(可能含 .json 后缀或完整路径)。

    返回:
        str: 清洗后的目录名; 空串表示不该建子目录(退回 output 根)。
    """
    text = str(name or "").strip()
    if not text:
        return ""
    # 只取路径末段, 防 ../ 穿越
    text = text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if text.lower().endswith(".json"):
        text = text[:-5]
    for ch in _UNSAFE_CHARS:
        text = text.replace(ch, "_")
    text = text.strip().strip(".")
    return "" if text in ("", ".", "..") else text


def _workflow_output_dir(workflow_name) -> str:
    """取保存目录: output 下按当前工作流名建子目录, 不存在则创建; 名字非法时退回 output 根。

    参数:
        workflow_name (str|None): 前端传来的当前工作流名。

    返回:
        str: 可直接拼接文件名的目录绝对路径(保证存在)。
    """
    base = folder_paths.get_output_directory()
    sub = _safe_dir_name(workflow_name)
    if not sub:
        return base
    target = os.path.join(base, sub)
    os.makedirs(target, exist_ok=True)
    return target

# 最近一次预览缓存(键 = 节点 id 字符串), 供 sticky 回放与「保存」取数据
_last_output: dict[str, dict] = {}
# 重置代际: 「重置」时递增, 让 fingerprint_inputs 变化从而强制重新执行
_reset_generation = 0


def _encode_audio_waveform(waveform: torch.Tensor, sample_rate: int, file_format: str, quality: str) -> bytes:
    """把单段波形按 格式/质量 编码为字节流(参照 AudioSaveHelper.save_audio 的编码部分)。

    参数:
        waveform (torch.Tensor): 单段波形 [channels, samples];
        sample_rate (int): 采样率;
        file_format (str): flac/mp3/opus;
        quality (str): 质量(V0/128k/320k/64k/96k/192k)。

    返回:
        bytes: 编码后的音频字节。
    """
    out = BytesIO()
    container = av.open(out, mode="w", format=file_format)
    layout = "mono" if waveform.shape[0] == 1 else "stereo"
    if file_format == "opus":
        # Opus 仅支持固定采样率; 超标或不在表内时重采样(参照原生 AudioSaveHelper)
        original_rate = sample_rate
        if sample_rate > 48000:
            sample_rate = 48000
        elif sample_rate not in _OPUS_RATES:
            for rate in sorted(_OPUS_RATES):
                if rate > sample_rate:
                    sample_rate = rate
                    break
            if sample_rate not in _OPUS_RATES:
                sample_rate = 48000
        if sample_rate != original_rate:
            if not TORCH_AUDIO_AVAILABLE:
                raise RuntimeError("torchaudio 不可用, 无法将音频重采样到 Opus 支持采样率")
            waveform = torchaudio.functional.resample(waveform, original_rate, sample_rate)
        out_stream = container.add_stream("libopus", rate=sample_rate, layout=layout)
        if quality == "64k":
            out_stream.bit_rate = 64000
        elif quality == "96k":
            out_stream.bit_rate = 96000
        elif quality == "128k":
            out_stream.bit_rate = 128000
        elif quality == "192k":
            out_stream.bit_rate = 192000
        elif quality == "320k":
            out_stream.bit_rate = 320000
    elif file_format == "mp3":
        out_stream = container.add_stream("libmp3lame", rate=sample_rate, layout=layout)
        if quality == "V0":
            out_stream.codec_context.qscale = 1
        elif quality == "128k":
            out_stream.bit_rate = 128000
        elif quality == "320k":
            out_stream.bit_rate = 320000
    else:  # flac
        out_stream = container.add_stream("flac", rate=sample_rate, layout=layout)

    frame = av.AudioFrame.from_ndarray(
        waveform.movedim(0, 1).reshape(1, -1).float().numpy(),
        format="flt",
        layout=layout,
    )
    frame.sample_rate = sample_rate
    frame.pts = 0
    container.mux(out_stream.encode(frame))
    container.mux(out_stream.encode(None))
    container.close()
    out.seek(0)
    return out.getbuffer()




def _save_audio_no_counter(
    audio: dict,
    filename_prefix: str,
    file_format: str,
    quality: str,
    workflow_name=None,
) -> list[str]:
    """按 {filename_prefix}.{format} 把音频写 output(同名覆盖, 无 _序号 后缀)。

    参数:
        audio (dict): 音频对象, 含 "waveform"(BxCxN) 与 "sample_rate";
        filename_prefix (str): 文件名前缀(可含 %batch_num%);
        file_format (str): flac/mp3/opus;
        quality (str): 质量;
        workflow_name (str|None): 当前工作流名; 非空时在 output 下建同名子目录再写。

    返回:
        list[str]: 已保存的文件名列表(不含目录)。
    """
    if file_format not in _FORMATS:
        raise ValueError(f"Unsupported audio format: {file_format!r}")

    output_dir = _workflow_output_dir(workflow_name)
    sample_rate = audio["sample_rate"]
    results = []
    for batch_number, waveform in enumerate(audio["waveform"].cpu()):
        name = filename_prefix.replace("%batch_num%", str(batch_number))
        # 多段时用 {prefix}_{i}, 单段就是 {prefix} —— 均不带 5 位补零序号
        if batch_number > 0:
            name = f"{name}_{batch_number}"
        file_name = f"{name}.{file_format}"
        data = _encode_audio_waveform(waveform, sample_rate, file_format, quality)
        with open(os.path.join(output_dir, file_name), "wb") as f:
            f.write(data)
        results.append(file_name)
    return results




class PreviewAudioSaveNode(IO.ComfyNode):
    """音频预览保存节点: 预览(temp) + 「保存」写 output; 切段见 FallingTSAudioTrim。"""

    @classmethod
    def define_schema(cls) -> IO.Schema:
        """定义节点结构。

        返回:
            IO.Schema: 输入 audio + filename_prefix + filename_suffix + format + quality;
            输出 audio(透传/回放); hidden 含 prompt/extra_pnginfo/unique_id, is_output_node=True。
        """
        return IO.Schema(
            node_id="PreviewAudioSave",
            search_aliases=["preview audio", "保存音频", "音频预览", "输出音频"],
            display_name="Preview Audio (保存)",
            category="audio",
            description=(
                "Preview the audio (temp folder) and click 保存 to write it to output as "
                "{filename_prefix}{filename_suffix}.{format} (no sequence suffix, overwrites same name)."
            ),
            inputs=[
                IO.Audio.Input("audio", tooltip="要预览/保存的音频 (None = 无值, 如扇出未选中分支, 跳过预览, 输出该节点最近一次预览的音频供下游)。"),
                IO.String.Input(
                    "filename_prefix",
                    default="audio",
                    multiline=False,
                    tooltip="保存到 output 的文件名(不含扩展名); 同名直接覆盖, 无序号",
                ),
                IO.String.Input(
                    "filename_suffix",
                    default="",
                    multiline=False,
                    tooltip="文件名后缀(不含扩展名, 默认空); 保存时拼接在前缀之后: {filename_prefix}{filename_suffix}.{format}",
                ),
                IO.Combo.Input(
                    "format",
                    options=["flac", "mp3", "opus"],
                    default="flac",
                    tooltip="保存的文件格式。",
                ),
                IO.Combo.Input(
                    "quality",
                    options=["V0", "128k", "320k", "64k", "96k", "192k"],
                    default="128k",
                    tooltip="编码质量(mp3: V0/128k/320k; opus: 64k~320k; flac 忽略此项)。",
                ),
            ],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo, IO.Hidden.unique_id],
            is_output_node=True,
            outputs=[IO.Audio.Output("audio", tooltip="预览/保存的音频(透传或 sticky 回放)。")],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs) -> Any:
        """缓存失效签名: 把重置代际 + 节点 id 纳入指纹。

        「重置」递增 _reset_generation, 使指纹变化 -> 本节点重提交时必然重新执行,
        不被 ComfyUI 全局执行缓存跳过(否则同进程重跑同图会拿到旧预览)。

        参数:
            **kwargs: 输入参数(不读取具体值), 仅保持签名兼容。

        返回:
            tuple: (重置代际, 节点 id)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        return (_reset_generation, str(nid) if nid else "")

    @classmethod
    def execute(cls, audio, filename_prefix: str = "audio", filename_suffix: str = "", format: str = "flac", quality: str = "128k") -> IO.NodeOutput:
        """节点执行入口: 预览音频并把有效值输出给下游。

        逻辑:
        - audio 有值: 更新本节点缓存, 发 UI.PreviewAudio 预览事件, 输出该音频;
        - audio 为 None(扇出未选中分支 / 上游无值): 回放缓存并输出该节点最近一次
          预览的音频(sticky), 从未预览过则输出 None。

        参数:
            audio (dict|None): 音频对象, 含 waveform 与 sample_rate。
            filename_prefix (str, 默认 "audio"): 输出文件名前缀(控件; 连线时以实际接收值为准)。
            filename_suffix (str, 默认 ""): 文件名后缀(控件, 保存时拼接在前缀之后)。
            format (str, 默认 "flac"): 保存格式(控件)。
            quality (str, 默认 "128k"): 编码质量(控件)。

        返回:
            IO.NodeOutput: 音频 + UI.PreviewAudio 预览事件。
        """
        nid = str(getattr(cls.hidden, "unique_id", "") or "")
        cached = _last_output.get(nid) or {}

        if audio is None:
            last_audio = cached.get("audio")
            if last_audio is None:
                return IO.NodeOutput(None)
            return IO.NodeOutput(last_audio, ui=UI.PreviewAudio(last_audio, cls=cls))

        if nid:
            _last_output[nid] = {
                "audio": audio,
                "filename_prefix": filename_prefix,
                "filename_suffix": filename_suffix,
                "format": format,
                "quality": quality,
            }
        return IO.NodeOutput(audio, ui=UI.PreviewAudio(audio, cls=cls))


async def _handle_reset(request: web.Request) -> web.Response:
    """HTTP 路由: 重置所有 PreviewAudioSave(前端默认 Run 时调用)。

    递增 _reset_generation, 使 fingerprint_inputs 变化从而强制重新执行。

    返回:
        web.Response: 200 {"status": "ok"}。
    """
    global _reset_generation
    _reset_generation += 1
    return web.json_response({"status": "ok"})


async def _handle_clear(request: web.Request) -> web.Response:
    """HTTP 路由: 页面加载/刷新时的同步钩子(前端 setup 会调一次)。

    这里**故意不清音频缓存** —— 与 preview-video 只清 selected_frames 同理:
    清掉之后「保存」与节点内播放器在刷新后就拿不到数据, 必须重跑整条工作流才能用。
    本节点精简后已无段/帧列表这类纯界面态, 因此只回 ok。

    返回:
        web.Response: 200 {"status": "ok"}。
    """
    return web.json_response({"status": "ok"})




async def _handle_audio_url(request: web.Request) -> web.Response:
    """返回该节点当前缓存音频的可播放 URL(写 temp 一份, 供节点内 <audio> 试听)。

    节点自带 DOM widget(波形/段列表), 会占满内容区, 导致 ComfyUI 的 PreviewAudio
    播放器渲染不出来; 因此由后端直接给出可播放 URL, 前端自备 <audio controls>。

    参数:
        request: 路径参数 node_id。

    返回:
        web.Response: {"status":"ok","url":...} 或 400/500。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache or not cache.get("audio"):
        return web.json_response({"status": "error", "message": "没有可播放的音频数据"}, status=400)

    audio = cache["audio"]
    file_format = str(cache.get("format") or "flac")
    if file_format not in _FORMATS:
        file_format = "flac"
    try:
        waveform = audio["waveform"]
        first = waveform[0] if getattr(waveform, "dim", lambda: 0)() > 2 else waveform
        data = _encode_audio_waveform(first.cpu(), audio["sample_rate"], file_format, str(cache.get("quality") or "128k"))
        name = f"FallingTS_preview_audio_{nid}.{file_format}"
        with open(os.path.join(folder_paths.get_temp_directory(), name), "wb") as f:
            f.write(data)
    except Exception as e:  # noqa: BLE001 - 把真实原因回前端
        logging.exception("[FallingTS] 生成可播放音频失败")
        return web.json_response({"status": "error", "message": f"生成可播放音频失败: {e!r}"}, status=500)

    return web.json_response({"status": "ok", "url": f"/view?filename={quote(name)}&type=temp"})




async def _handle_save(request: web.Request) -> web.Response:
    """HTTP 路由: 用缓存音频把该节点最近预览的音频写入 output(同名覆盖, 无序号)。

    流程: 前端点「保存」按钮时把 文件名/格式/质量 POST 过来;
    后端查 _last_output[node_id](execute 时缓存的音频), 有则编码写 output, 无则 400。
    全程不触发任何工作流重跑。

    参数:
        request (web.Request): POST /preview-audio/save/{node_id}, body 为 JSON
            {filename_prefix, filename_suffix, filename_prefix_linked, filename_suffix_linked,
             format, quality, segment_index}。
            segment_index 省略或为 0 时保存整段; 指定 N 时只保存第 N 段。

    返回:
        web.Response:
        - 成功: 200, {"status": "ok", "message": "已保存 N 段: <文件名>.<格式>"};
        - 失败: 400, {"status": "error", "message": "没有预览数据, 请先运行到该节点"}。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache or not cache.get("audio"):
        return web.json_response(
            {"status": "error", "message": "没有预览数据, 请先运行到该节点"}, status=400
        )

    try:
        data = await request.json()
    except Exception:
        data = {}

    filename_prefix = str(data.get("filename_prefix", "audio"))
    # 若 filename_prefix 输入被上游连线, widget 值是占位符:
    # 用 execute 时实际接收到的值 (前端已标记 filename_prefix_linked)
    if data.get("filename_prefix_linked") and cache.get("filename_prefix"):
        filename_prefix = str(cache["filename_prefix"])
    # 后缀同前缀: 手动输入或上游连线(连线时用 execute 实际接收值); 空串 = 不拼后缀
    # (旧工作流 widgets_values 按位置对齐, 尾部 null 落到 suffix 槽, 此处 or "" 兜底)
    filename_suffix = str(data.get("filename_suffix") or "")
    if data.get("filename_suffix_linked") and cache.get("filename_suffix") is not None:
        filename_suffix = str(cache["filename_suffix"])

    file_format = str(data.get("format") or cache.get("format") or "flac")
    quality = str(data.get("quality") or cache.get("quality") or "128k")

    audio = cache["audio"]
    name = filename_prefix + filename_suffix

    try:
        saved = _save_audio_no_counter(
            audio, name, file_format, quality, data.get("workflow_name")
        )
    except ValueError as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)

    saved_dir = _safe_dir_name(data.get("workflow_name"))
    where = f"{saved_dir}/" if saved_dir else ""
    return web.json_response(
        {"status": "ok", "message": f"已保存 {len(saved)} 个文件: {where}{', '.join(saved)}"}
    )




PromptServer.instance.routes.post("/preview-audio/save/{node_id}")(_handle_save)
PromptServer.instance.routes.post("/preview-audio/reset")(_handle_reset)
PromptServer.instance.routes.post("/preview-audio/clear")(_handle_clear)
PromptServer.instance.routes.get("/preview-audio/audio-url/{node_id}")(_handle_audio_url)
