# preview-audio/nodes.py
"""PreviewAudioSave 节点: 始终预览(temp), 点「保存」才写 output(同名覆盖, 无序号)。

参照:
- 预览部分照原生 PreviewAudio(nodes_audio.py): UI.PreviewAudio → AudioSaveHelper.save_audio 写 temp flac;
- 保存部分照原生 SaveAudioAdvanced + AudioSaveHelper.save_audio: 支持 flac/mp3/opus(+quality) 编码;
- 差异: 保存用 {filename_prefix}.{format} 直接写 output, 同名覆盖, 不带 _序号 后缀
  (不走 get_save_image_path 的 counter);
- 关键: 点「保存」【不重跑工作流】—— execute 时把最近一次预览的音频数据缓存到后端,
  点按钮时前端把 文件名/格式/质量 POST 到 /preview-audio/save/{id}, 后端直接用缓存写 output。
"""

from __future__ import annotations

import os
from io import BytesIO

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

# 最近一次预览的音频缓存: node_id -> {"audio": dict, "filename_prefix": str, "format": dict}
_last_output: dict[str, dict] = {}


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


def _save_audio_no_counter(audio: dict, filename_prefix: str, file_format: str, quality: str) -> list[str]:
    """按 {filename_prefix}.{format} 把音频写 output(同名覆盖, 无 _序号 后缀)。

    参数:
        audio (dict): 音频对象, 含 "waveform"(BxCxN) 与 "sample_rate";
        filename_prefix (str): 文件名前缀(可含 %batch_num%);
        file_format (str): flac/mp3/opus;
        quality (str): 质量。

    返回:
        list[str]: 已保存的文件名列表(不含目录)。
    """
    if file_format not in _FORMATS:
        raise ValueError(f"Unsupported audio format: {file_format!r}")

    output_dir = folder_paths.get_output_directory()
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
    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: 输入 audio + filename_prefix + format(flac/mp3/opus 及质量),
            输出 audio, hidden 含 prompt/extra_pnginfo/unique_id, is_output_node=True。
        """
        return IO.Schema(
            node_id="PreviewAudioSave",
            search_aliases=["preview audio", "保存音频", "音频预览", "输出音频"],
            display_name="Preview Audio (保存)",
            category="audio",
            description=(
                "Preview the audio (temp folder) and click 保存 to write it to output "
                "as {filename_prefix}.{format} (no sequence suffix, overwrites same name)."
            ),
            inputs=[
                IO.Audio.Input("audio", tooltip="要预览/保存的音频 (None = 无值, 如扇出未选中分支, 跳过预览, 输出该节点最近一次预览的音频供下游)。"),
                IO.String.Input(
                    "filename_prefix",
                    default="audio",
                    multiline=False,
                    tooltip="保存到 output 的文件名(不含扩展名); 同名直接覆盖, 无序号",
                ),
                IO.DynamicCombo.Input(
                    "format",
                    options=[
                        IO.DynamicCombo.Option("flac", []),
                        IO.DynamicCombo.Option("mp3", [
                            IO.Combo.Input("quality", options=["V0", "128k", "320k"], default="V0"),
                        ]),
                        IO.DynamicCombo.Option("opus", [
                            IO.Combo.Input("quality", options=["64k", "96k", "128k", "192k", "320k"], default="128k"),
                        ]),
                    ],
                    tooltip="保存的文件格式与质量(flac / mp3 / opus)。",
                ),
            ],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo, IO.Hidden.unique_id],
            is_output_node=True,
            outputs=[IO.Audio.Output("audio")],
        )

    @classmethod
    def execute(cls, audio, filename_prefix: str = "audio", format: dict | None = None) -> IO.NodeOutput:
        """节点执行入口: 生成 temp 预览, 并把最近一次音频数据缓存到后端供「保存」直接写 output。

        逻辑: 音频为 None (如扇出节点未选中分支输出 = 无值) 跳过预览/缓存, 输出本节点最近一次预览的音频(从未预览过则 None);
        否则返回 UI.PreviewAudio 让前端播放 temp 文件;
        把 audio/filename_prefix/format 存进 _last_output[id] —— 之后点「保存」按钮,
        前端把 文件名/格式/质量 POST 过来, 后端直接用这份缓存写 output, 【不重跑工作流】。

        参数:
            audio (dict|None): 音频对象, 含 waveform 与 sample_rate; None (如扇出未选中分支) 跳过预览/缓存, 输出本节点最近一次预览的音频(从未预览过则 None)。
            filename_prefix (str, 默认 "audio"): 输出文件名前缀(控件; 若被上游连线,
                widget 只是占位符, 本参数为实际接收值, 保存时以此为准)。
            format (dict|None): {format, quality}(控件)。

        返回:
            IO.NodeOutput: 音频输出 + UI.PreviewAudio 预览事件(指向 temp 目录文件);
            audio 为 None 时回放上一次预览事件(保持原预览不清空) 并输出本节点最近一次预览的音频(从未预览过则 None)。
        """
        # None (如扇出节点未选中分支输出 = 无值): 不动原来的数据 —— 回放上一次预览事件
        # (保持原预览不清空), 输出本节点【最近一次预览的音频】(下游可拿到该分支之前预览的音频,
        # 而非 None); 从未预览过则输出 None, 不更新「保存」缓存
        if audio is None:
            nid = getattr(cls.hidden, "unique_id", None)
            cached = _last_output.get(str(nid)) if nid else None
            last_audio = cached.get("audio") if cached else None
            if last_audio is not None:
                return IO.NodeOutput(last_audio, ui=UI.PreviewAudio(last_audio, cls=cls))
            return IO.NodeOutput(None)

        # 缓存最近一次预览的音频(供「保存」直接写 output, 无需重跑)
        nid = getattr(cls.hidden, "unique_id", None)
        if nid:
            _last_output[str(nid)] = {
                "audio": audio,
                "filename_prefix": filename_prefix,
                "format": format,
            }

        return IO.NodeOutput(audio, ui=UI.PreviewAudio(audio, cls=cls))


async def _handle_save(request: web.Request) -> web.Response:
    """HTTP 路由: 用缓存音频把该节点最近预览的音频写入 output(同名覆盖, 无序号)。

    流程: 前端点「保存」按钮时把 文件名/格式/质量 POST 过来;
    后端查 _last_output[node_id](execute 时缓存的音频), 有则编码写 output, 无则 400。
    全程不触发任何工作流重跑。

    参数:
        request (web.Request): POST /preview-audio/save/{node_id}, body 为 JSON
            {filename_prefix, filename_prefix_linked, format, quality}。

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

    file_format = str(data.get("format") or "flac")
    quality = str(data.get("quality") or "128k")

    try:
        saved = _save_audio_no_counter(cache["audio"], filename_prefix, file_format, quality)
    except ValueError as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)

    return web.json_response(
        {"status": "ok", "message": f"已保存 {len(saved)} 段: {', '.join(saved)}"}
    )


PromptServer.instance.routes.post("/preview-audio/save/{node_id}")(_handle_save)
