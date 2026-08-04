# selector/nodes.py
"""FallingTS 档位选择器: 一个下拉档位统一控制生成参数 (steps / cfg / seed)。

背景: ComfyUI 核心只有 Not/And/Or/If-Else Switch 等二选一逻辑节点,
没有"一个下拉档位同时控制流程中多个参数"的组件。本节点用下拉预设
替代工作流里 Primitive + Switch 组成的参数联动链。

行为:
- 下拉选择一个档位 (如 4步加速 / 20步标准), 一次输出 steps/cfg/seed;
- seed_mode 为 "random" 时, 每次执行自动生成新随机种子, 且 IS_CHANGED
  返回变化值, 强制带动下游 KSampler 重新采样 (等价于 KSampler 的
  control_after_generate=randomize);
- seed_mode 为 "fixed" 时输出固定种子, 结果可复现, 且可正常命中缓存。
"""

from __future__ import annotations

import random
import time
from typing import Any

# 档位预设: 每档定义生成参数
# seed_mode: "random" = 每次执行随机种子; "fixed" = 固定使用 fixed_seed 输入
PRESETS: dict[str, dict[str, Any]] = {
    "4步加速": {
        "steps": 4,
        "cfg": 1.0,
        "seed_mode": "random",
        "tooltip": "极速出图, 细节较少, 种子自动随机",
    },
    "20步标准": {
        "steps": 20,
        "cfg": 2.5,
        "seed_mode": "fixed",
        "tooltip": "标准质量, 种子固定可复现",
    },
    "30步精修": {
        "steps": 30,
        "cfg": 3.0,
        "seed_mode": "fixed",
        "tooltip": "更高质量, 耗时更长, 种子固定可复现",
    },
}

# 模块加载时校验档位结构, 避免手改 PRESETS 时字段缺失到运行时才炸
for _name, _cfg in PRESETS.items():
    for _field in ("steps", "cfg", "seed_mode"):
        if _field not in _cfg:
            raise ValueError(f"FallingTSSelector: 档位 '{_name}' 缺少字段 '{_field}'")


def _resolve_preset(mode: str) -> tuple[str, dict[str, Any]]:
    """按档位名取预设; 档位名无效(保存的旧工作流引用已删除/改名的档位)时回退到第一个档位。"""
    if mode in PRESETS:
        return mode, PRESETS[mode]
    fallback = next(iter(PRESETS))
    return fallback, PRESETS[fallback]


class FallingTSSelectorNode:
    """下拉档位选择器: 一个下拉同时控制 steps / cfg / seed 模式与种子值。"""

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "mode": (
                    list(PRESETS.keys()),
                    {
                        "default": "20步标准",
                        "tooltip": "选择生成档位, 一次性设置 steps/cfg/seed",
                    },
                ),
                "fixed_seed": (
                    "INT",
                    {
                        "default": 189167814536999,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "step": 1,
                        "tooltip": "固定模式 (20步标准/30步精修) 使用的种子值",
                    },
                ),
            },
        }

    RETURN_TYPES = ("INT", "FLOAT", "INT", "BOOLEAN", "STRING")
    RETURN_NAMES = ("steps", "cfg", "seed", "random_seed", "mode")
    FUNCTION = "execute"
    CATEGORY = "FallingTS/工具"

    @classmethod
    def IS_CHANGED(cls, mode: str, fixed_seed: int, **kwargs) -> Any:
        _, preset = _resolve_preset(mode)
        if preset["seed_mode"] == "random":
            # 随机档位: 每次执行都变化, 带动下游 KSampler 重新采样
            return time.time()
        resolved, _ = _resolve_preset(mode)
        return (resolved, fixed_seed)

    def execute(self, mode: str, fixed_seed: int):
        resolved, preset = _resolve_preset(mode)
        steps = int(preset["steps"])
        cfg = float(preset["cfg"])
        if preset["seed_mode"] == "random":
            seed = random.randrange(0, 0xFFFFFFFFFFFFFFFF)
            random_seed = True
        else:
            seed = int(fixed_seed)
            random_seed = False
        return (steps, cfg, seed, random_seed, resolved)


NODE_CLASS_MAPPINGS = {
    "FallingTSSelector": FallingTSSelectorNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FallingTSSelector": "FallingTS 档位选择器",
}
