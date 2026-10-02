# -*- coding: utf-8 -*-
"""离线单测: 加载音频/加载视频的 validate_inputs 对"连线"入参的容错。"""
import sys, os, importlib.util
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath("ComfyUI"))
sys.path.insert(0, os.path.abspath("custom_nodes/ComfyUI-FallingTS"))
os.chdir("ComfyUI")

# 独立导入时 PromptServer 未就绪: 塞个假的(路由装饰器变空操作)
import types
fake = types.ModuleType("server")
class _Routes:
    @staticmethod
    def get(path):
        return lambda fn: fn
    @staticmethod
    def post(path):
        return lambda fn: fn
class _PromptServer:
    routes = _Routes()
    instance = None
_PromptServer.instance = _PromptServer()
fake.PromptServer = _PromptServer
sys.modules.setdefault("server", fake)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

audio = load("../custom_nodes/ComfyUI-FallingTS/load-audio/nodes.py", "load_audio_nodes")
video = load("../custom_nodes/ComfyUI-FallingTS/load-video/nodes.py", "load_video_nodes")

fails = 0
def check(label, ok, detail=None):
    global fails
    print(("PASS" if ok else "FAIL") + ": " + label, "" if detail is None else detail)
    if not ok:
        fails += 1

# 已连线(input_types 里有该输入) → 放过; 未连线且没选文件 → 明确提示
check("加载音频: 已连线 audio_in 放过", audio.FallingTSLoadAudioNode.validate_inputs(audio="", input_types={"audio_in": "AUDIO"}) is True)
check("加载音频: 未连线未选择 → 提示", isinstance(audio.FallingTSLoadAudioNode.validate_inputs(audio="", input_types={}), str))
check("加载视频: 已连线 video_in 放过", video.FallingTSLoadVideoNode.validate_inputs(video="", input_types={"video_in": "VIDEO"}) is True)
check("加载视频: 未连线未选择 → 提示", isinstance(video.FallingTSLoadVideoNode.validate_inputs(video="", input_types={}), str))
sys.exit(1 if fails else 0)
