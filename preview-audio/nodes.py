# preview-audio/nodes.py
"""PreviewAudioSave 节点: 始终预览(temp), 可在节点上按波形截段(多段), 点「保存」写 output。

参照:
- 预览部分照原生 PreviewAudio(nodes_audio.py): UI.PreviewAudio → 写 temp 音频;
- 截段照 PreviewVideo 的截帧机制: 前端把段列表写回后端缓存, 「完成」后 execute 按段
  输出 audio_1..audio_MAX_SEGMENTS(未截段的槽为 None), 未「完成」时用 ExecutionBlocker
  阻断下游("到预览节点就停止"), 只发预览事件供试听与截段;
- 每段的切片逻辑照原生 TrimAudioDuration.execute: start 支持负数(从尾部计), 帧级
  clamp, start >= end 时该段为空;
- 保存部分照原生 SaveAudioAdvanced: 支持 flac/mp3/opus(+quality) 编码, 写
  {filename_prefix}{filename_suffix}.{format}, 同名覆盖无序号; 点「保存」不重跑工作流。
"""

from __future__ import annotations

import os
from io import BytesIO
from typing import Any

import av
import torch

from aiohttp import web
from server import PromptServer

from comfy_api.latest import IO, UI
from comfy_execution.graph_utils import ExecutionBlocker
import folder_paths

try:
    import torchaudio

    TORCH_AUDIO_AVAILABLE = True
except ImportError:
    TORCH_AUDIO_AVAILABLE = False

_OPUS_RATES = [8000, 12000, 16000, 24000, 48000]
_FORMATS = {"flac", "mp3", "opus"}

# 截段上限(输出槽数量 = 1 个透传 audio + MAX_SEGMENTS 个段)
MAX_SEGMENTS = 64

# 哨兵: 区分"该输入根本没连线"(MISSING)与"连了线但上游未求值"(None)
MISSING = object()

# 最近一次预览的音频缓存: node_id -> {"audio", "filename_prefix", "filename_suffix",
# "format", "segments": [{"start","duration"}...]}
_last_output: dict[str, dict] = {}
# 已点「完成」的节点(完成后 execute 按段输出, 并不再拉上游)
_done: set[str] = set()
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


def _trim_audio(audio: dict, start: float, duration: float) -> dict | None:
    """按时间区间截取音频(与原生 TrimAudioDuration.execute 同一套切片逻辑)。

    参数:
        audio (dict): 音频对象 {"waveform": Tensor[C, N], "sample_rate": int};
        start (float): 起始秒; 负数表示从尾部倒计;
        duration (float): 时长秒(must >= 0)。

    返回:
        dict | None: 截取后的音频对象; 区间为空(起点 >= 终点)时 None。
    """
    waveform = audio.get("waveform")
    sample_rate = audio.get("sample_rate")
    if waveform is None or not sample_rate:
        return None
    audio_length = waveform.shape[-1]
    if audio_length == 0:
        return None

    if start < 0:
        start_frame = audio_length + int(round(start * sample_rate))
    else:
        start_frame = int(round(start * sample_rate))
    start_frame = max(0, min(start_frame, audio_length))

    end_frame = start_frame + int(round(duration * sample_rate))
    end_frame = max(0, min(end_frame, audio_length))
    if start_frame >= end_frame:
        return None

    return {"waveform": waveform[..., start_frame:end_frame], "sample_rate": sample_rate}


def _segments_from_cache(audio: dict, segments: list) -> list:
    """按段列表截取音频, 返回长度 MAX_SEGMENTS 的槽位列表(未截到的槽 None)。

    参数:
        audio (dict): 源音频;
        segments (list): [{"start": float, "duration": float}, ...]。

    返回:
        list: 前 len(segments) 个为截取后的音频(越界/空段为 None), 其余 None。
    """
    out: list = [None] * MAX_SEGMENTS
    for i, seg in enumerate(segments[:MAX_SEGMENTS]):
        if not isinstance(seg, dict):
            continue
        try:
            start = float(seg.get("start", 0.0))
            duration = float(seg.get("duration", 0.0))
        except (TypeError, ValueError):
            continue
        out[i] = _trim_audio(audio, start, duration)
    return out


def _waveform_peaks(audio: dict, buckets: int = 1200) -> list[float]:
    """把波形降采样成 buckets 个峰值(供前端画波形与拖动选区)。

    参数:
        audio (dict): 音频对象;
        buckets (int): 目标点数。

    返回:
        list[float]: 各桶的绝对值峰值(0..1 量级)。
    """
    waveform = audio.get("waveform")
    if waveform is None:
        return []
    mono = waveform.abs().amax(dim=0) if waveform.dim() > 1 else waveform.abs()
    total = int(mono.shape[0])
    if total == 0:
        return []
    if total <= buckets:
        return [float(v) for v in mono.tolist()]

    step = total / buckets
    peaks: list[float] = []
    for i in range(buckets):
        lo = int(i * step)
        hi = max(lo + 1, int((i + 1) * step))
        peaks.append(float(mono[lo:hi].max()))
    return peaks


def _audio_duration(audio: dict) -> float:
    """音频总时长(秒); 无有效数据返回 0.0。"""
    waveform = audio.get("waveform")
    sample_rate = audio.get("sample_rate")
    if waveform is None or not sample_rate:
        return 0.0
    return float(waveform.shape[-1]) / float(sample_rate)


class PreviewAudioSaveNode(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        """定义节点 schema(V3 规范)。

        返回:
            IO.Schema: 输入 audio + filename_prefix + filename_suffix + format;
            输出 audio(透传) + audio_1..audio_MAX_SEGMENTS(按截段输出);
            hidden 含 prompt/extra_pnginfo/unique_id, is_output_node=True。
        """
        outputs = [IO.Audio.Output("audio", tooltip="预览/保存的音频(整段透传)。")]
        outputs += [
            IO.Audio.Output(
                f"audio_{i}",
                display_name=f"截段 {i}",
                tooltip=f"第 {i} 个截段(前端拖动选区后点「截段」累积, 未截到为 None)。",
            )
            for i in range(1, MAX_SEGMENTS + 1)
        ]
        return IO.Schema(
            node_id="PreviewAudioSave",
            search_aliases=["preview audio", "保存音频", "音频预览", "输出音频", "截取音频", "音频截段"],
            display_name="Preview Audio (保存+截段)",
            category="audio",
            description=(
                "Preview the audio (temp folder), drag on the waveform to pick a time range and click 截段 "
                "to add it, then click 完成 to output each segment on audio_1..audio_N. "
                "click 保存 to write it to output as {filename_prefix}{filename_suffix}.{format} "
                "(no sequence suffix, overwrites same name)."
            ),
            inputs=[
                IO.Audio.Input("audio", tooltip="要预览/截段/保存的音频 (None = 无值, 如扇出未选中分支, 跳过预览, 输出该节点最近一次预览的音频供下游)。"),
                IO.String.Input(
                    "filename_prefix",
                    default="audio",
                    multiline=False,
                    tooltip="保存到 output 的文件名(不含扩展名); 同名直接覆盖, 无序号",
                ),
                # 紧随 filename_prefix(控件紧挨前缀显示); 无旧工作流引用本节点, 无兼容约束
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
            outputs=outputs,
        )

    @classmethod
    def check_lazy_status(cls, audio=MISSING, filename_prefix: str = "audio", filename_suffix: str = "", format: str = "flac", quality: str = "128k", **kwargs) -> list[str]:
        """懒加载门控: 已「完成」且有截段时不拉上游(用缓存), 否则拉取音频。

        参数:
            audio (Any, 默认 MISSING): 上游音频:
                - MISSING: 该输入没连线;
                - None: 连了线但上游未求值(已完成时即此处);
                - 其他: 已求值(此时不在 missing_keys, 返回值会被过滤)。
            filename_prefix / filename_suffix / format / quality: 不读取, 保持签名兼容。
            **kwargs: 吸收其余隐藏输入。

        返回:
            list[str]: 需要拉取的上游输入名, 只能是 ["audio"] 或 []。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        if audio is MISSING:
            return []
        cached = _last_output.get(nid_str) or {}
        if nid_str in _done and (cached.get("segments") or []):
            return []
        return ["audio"]

    @classmethod
    def fingerprint_inputs(cls, **kwargs) -> Any:
        """缓存失效签名: 把 截段列表 + 是否完成 + 重置代际 纳入指纹。

        截段路由每追加/删除一段都更新 _last_output[nid]["segments"], 「完成」置入 _done,
        「重置」递增 _reset_generation; 指纹随之变化 -> 本节点重提交时必然重新执行,
        使新的截段结果输出到下游(不被 ComfyUI 全局执行缓存跳过)。

        参数:
            **kwargs: 输入参数(不读取具体值), 仅保持签名兼容。

        返回:
            tuple: (重置代际, unique_id, 段参数元组, 是否完成)。
        """
        nid = getattr(cls.hidden, "unique_id", None)
        nid_str = str(nid) if nid else ""
        cached = _last_output.get(nid_str) or {}
        seg_key = tuple(
            (round(float(s.get("start", 0.0)), 6), round(float(s.get("duration", 0.0)), 6))
            for s in (cached.get("segments") or [])
            if isinstance(s, dict)
        )
        return (_reset_generation, nid_str, seg_key, nid_str in _done)

    @classmethod
    def execute(cls, audio, filename_prefix: str = "audio", filename_suffix: str = "", format: str = "flac", quality: str = "128k") -> IO.NodeOutput:
        """节点执行入口: 预览音频; 已「完成」则按截段输出 audio_1..audio_N。

        逻辑:
        - audio 为 None (扇出未选中分支 / 已完成时 lazy 未拉上游): 用缓存音频继续,
          已完成则按缓存段输出, 否则重发预览事件;
        - audio 有值: 更新缓存; 未「完成」→ 输出全部 ExecutionBlocker(None) 阻断下游
          (合成/保存不跑, "到预览节点就停止断掉"), 但 UI.PreviewAudio 预览照常发出,
          音频正常试听与截段;
        - 已「完成」: 输出整段 audio + 各截段(audio_1..audio_MAX_SEGMENTS)。

        参数:
            audio (dict|None): 音频对象, 含 waveform 与 sample_rate。
            filename_prefix (str, 默认 "audio"): 输出文件名前缀(控件; 连线时以实际接收值为准)。
            filename_suffix (str, 默认 ""): 文件名后缀(控件, 保存时拼接在前缀之后)。
            format (dict|None): {format, quality}(控件)。

        返回:
            IO.NodeOutput: 整段音频 + 各截段 + UI.PreviewAudio 预览事件。
        """
        nid = str(getattr(cls.hidden, "unique_id", "") or "")
        cached = _last_output.get(nid) or {}
        done = nid in _done
        segments = cached.get("segments") or []
        blocked = [ExecutionBlocker(None)] * (1 + MAX_SEGMENTS)

        if audio is None:
            last_audio = cached.get("audio")
            if last_audio is None:
                return IO.NodeOutput(*([None] * (1 + MAX_SEGMENTS)))
            if not done:
                return IO.NodeOutput(*blocked, ui=UI.PreviewAudio(last_audio, cls=cls))
            return IO.NodeOutput(
                last_audio, *_segments_from_cache(last_audio, segments), ui=UI.PreviewAudio(last_audio, cls=cls)
            )

        if nid:
            _last_output[nid] = {
                "audio": audio,
                "filename_prefix": filename_prefix,
                "filename_suffix": filename_suffix,
                "format": format,
                "quality": quality,
                "segments": segments,
            }

        # 未「完成」: 阻断下游节点本身不执行, 但预览事件照发(可试听/截段)
        if not done:
            return IO.NodeOutput(*blocked, ui=UI.PreviewAudio(audio, cls=cls))

        return IO.NodeOutput(audio, *_segments_from_cache(audio, segments), ui=UI.PreviewAudio(audio, cls=cls))


async def _handle_segment(request: web.Request) -> web.Response:
    """HTTP 路由: 追加一个截段到该节点的段列表。

    前端在波形上拖动确定起止后点「截段」, 把 {start, duration} POST 过来; 后端做区间
    合法性检查(与 TrimAudioDuration 一致: start>=0 或负数倒计, duration>0, 且落在音频
    时长内)后追加进 _last_output[nid]["segments"](上限 MAX_SEGMENTS), 供下次 execute 输出。

    请求体: {"start": float, "duration": float}

    返回:
        web.Response: 200 {"status": "ok", "index": 段序号(1-based), "total": 段数, "duration": 音频总时长};
        400 {"status": "error", "message": ...} 无缓存/参数非法/越界/已满。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache or not cache.get("audio"):
        return web.json_response(
            {"status": "error", "message": "没有可截段的音频数据, 请先运行到该节点"}, status=400
        )

    try:
        data = await request.json()
    except Exception:
        data = {}

    try:
        start = float(data.get("start", 0.0))
        duration = float(data.get("duration", 0.0))
    except (TypeError, ValueError):
        return web.json_response({"status": "error", "message": "start/duration 非法"}, status=400)

    if duration <= 0:
        return web.json_response({"status": "error", "message": "截段时长必须大于 0"}, status=400)

    total_duration = _audio_duration(cache["audio"])
    if _trim_audio(cache["audio"], start, duration) is None:
        return web.json_response(
            {"status": "error", "message": f"截段区间无效(音频总长 {total_duration:.2f}s)"}, status=400
        )

    segments = cache.get("segments") or []
    if len(segments) >= MAX_SEGMENTS:
        return web.json_response(
            {"status": "error", "message": f"已达截段上限 {MAX_SEGMENTS} 段"}, status=400
        )
    segments.append({"start": round(start, 4), "duration": round(duration, 4)})
    cache["segments"] = segments

    return web.json_response(
        {
            "status": "ok",
            "index": len(segments),
            "total": len(segments),
            "duration": total_duration,
        }
    )


async def _handle_segment_remove(request: web.Request) -> web.Response:
    """HTTP 路由: 从段列表里删除指定序号的截段(1-based)。

    请求体: {"index": int} —— 1-based 段序号。

    返回:
        web.Response: 200 {"status": "ok", "total": 剩余段数}; 400 序号非法/无缓存。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache:
        return web.json_response({"status": "error", "message": "没有该节点的缓存"}, status=400)

    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        index = int(data.get("index", 0))
    except (TypeError, ValueError):
        return web.json_response({"status": "error", "message": "index 非法"}, status=400)

    segments = cache.get("segments") or []
    if index < 1 or index > len(segments):
        return web.json_response({"status": "error", "message": f"段序号越界(当前 {len(segments)} 段)"}, status=400)

    segments.pop(index - 1)
    cache["segments"] = segments
    return web.json_response({"status": "ok", "total": len(segments)})


async def _handle_done(request: web.Request) -> web.Response:
    """HTTP 路由: 标记该节点「完成截段」, 使下一次执行按段输出且不重跑上游。

    请求体(可选): {"segments": [{"start","duration"}...]} —— 从工作流恢复的段列表
    (前端 DOM state, 后端缓存可能为空)时, 用它填充后端缓存, 使完成可基于前端段生效。

    返回:
        web.Response: 200 {"status": "ok", "done": bool, "total": 段数}。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.setdefault(nid, {"segments": []})
    try:
        data = await request.json()
    except Exception:
        data = None

    if data and isinstance(data.get("segments"), list):
        cleaned = []
        for seg in data["segments"]:
            if not isinstance(seg, dict):
                continue
            try:
                cleaned.append({"start": float(seg.get("start", 0.0)), "duration": float(seg.get("duration", 0.0))})
            except (TypeError, ValueError):
                continue
        cache["segments"] = cleaned[:MAX_SEGMENTS]

    segments = cache.get("segments") or []
    # 仅当已有截段才置完成(无段的「完成」= 预加载上游, 走 reset + 全量提交)
    if segments:
        _done.add(nid)
    return web.json_response({"status": "ok", "done": nid in _done, "total": len(segments)})


async def _handle_reset(request: web.Request) -> web.Response:
    """HTTP 路由: 重置所有 PreviewAudioSave 为未完成(前端默认 Run / 无段点「完成」时调用)。

    清空 _done(全部回阻塞态 = 未完成, 下次执行重新拉上游)并递增 _reset_generation,
    使 fingerprint_inputs 变化从而强制重新执行。

    返回:
        web.Response: 200 {"status": "ok"}。
    """
    global _reset_generation
    _done.clear()
    _reset_generation += 1
    return web.json_response({"status": "ok"})


async def _handle_clear(request: web.Request) -> web.Response:
    """HTTP 路由: 清空所有节点的截段状态(前端页面加载/刷新时调一次)。

    前端刷新后不再还原序列化的段列表, 后端须同步清掉内存段列表, 避免"前端已空但后端
    还留着旧段" —— 否则下次截段会追加到旧段后面。音频缓存不清(「保存」刷新后仍可用)。

    返回:
        web.Response: 200 {"status": "ok"}。
    """
    for cache in _last_output.values():
        if isinstance(cache, dict):
            cache["segments"] = []
    _done.clear()
    return web.json_response({"status": "ok"})


async def _handle_waveform(request: web.Request) -> web.Response:
    """HTTP 路由: 返回该节点缓存音频的降采样峰值(供前端画波形与拖动选区)。

    返回:
        web.Response: 200 {"status": "ok", "peaks": [...], "duration": float, "sample_rate": int};
        400 {"status": "error", "message": ...} 无缓存。
    """
    nid = request.match_info["node_id"].strip()
    cache = _last_output.get(nid)
    if not cache or not cache.get("audio"):
        return web.json_response(
            {"status": "error", "message": "没有可绘制的音频数据, 请先运行到该节点"}, status=400
        )
    audio = cache["audio"]
    return web.json_response(
        {
            "status": "ok",
            "peaks": _waveform_peaks(audio),
            "duration": _audio_duration(audio),
            "sample_rate": int(audio.get("sample_rate") or 0),
            "segments": cache.get("segments") or [],
        }
    )


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

    # 指定段号(1-based)时只存该段; 省略/0 = 存整段
    try:
        segment_index = int(data.get("segment_index") or 0)
    except (TypeError, ValueError):
        segment_index = 0

    audio = cache["audio"]
    name = filename_prefix + filename_suffix
    if segment_index > 0:
        segments = cache.get("segments") or []
        if segment_index > len(segments):
            return web.json_response(
                {"status": "error", "message": f"段序号越界(当前 {len(segments)} 段)"}, status=400
            )
        seg = segments[segment_index - 1]
        audio = _trim_audio(audio, float(seg.get("start", 0.0)), float(seg.get("duration", 0.0)))
        if audio is None:
            return web.json_response({"status": "error", "message": "该段区间无效"}, status=400)
        name = f"{name}_{segment_index}"

    try:
        saved = _save_audio_no_counter(audio, name, file_format, quality)
    except ValueError as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)

    return web.json_response(
        {"status": "ok", "message": f"已保存 {len(saved)} 段: {', '.join(saved)}"}
    )


PromptServer.instance.routes.post("/preview-audio/save/{node_id}")(_handle_save)
PromptServer.instance.routes.post("/preview-audio/segment/{node_id}")(_handle_segment)
PromptServer.instance.routes.post("/preview-audio/segment-remove/{node_id}")(_handle_segment_remove)
PromptServer.instance.routes.post("/preview-audio/done/{node_id}")(_handle_done)
PromptServer.instance.routes.post("/preview-audio/reset")(_handle_reset)
PromptServer.instance.routes.post("/preview-audio/clear")(_handle_clear)
PromptServer.instance.routes.get("/preview-audio/waveform/{node_id}")(_handle_waveform)
