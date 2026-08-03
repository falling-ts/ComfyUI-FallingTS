# 环境配置管理
# 支持 .env 文件 和 环境变量 两种方式

from __future__ import annotations

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 插件根目录 (.env 文件所在位置)
PLUGIN_ROOT = Path(__file__).resolve().parent

# 环境变量键名
ENV_API_KEY = "SEEDANCE_API_KEY"
ENV_MODEL_ID = "SEEDANCE_MODEL_ID"  # 可选: 覆盖默认模型
ENV_MODEL_NAME = "SEEDANCE_MODEL_NAME"  # 可选: 覆盖默认模型显示名


def _load_dotenv() -> None:
    """加载 .env 文件到环境变量 (如果存在)。

    纯 Python 实现, 无额外依赖。只处理 VAR=value 格式。
    """
    dotenv_path = PLUGIN_ROOT / ".env"
    if not dotenv_path.exists():
        return

    loaded = 0
    with open(dotenv_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value
                loaded += 1

    if loaded:
        logger.info("Loaded %d variables from .env", loaded)


# 模块加载时自动尝试加载 .env
_load_dotenv()


def get_api_key() -> str | None:
    """获取 Volcengine API Key。

    优先级: 环境变量 > .env 文件
    """
    return os.environ.get(ENV_API_KEY)


def get_model_override() -> tuple[str, str] | None:
    """获取模型覆盖配置 (显示名, 模型ID)。

    返回 None 表示使用默认配置。
    """
    model_id = os.environ.get(ENV_MODEL_ID)
    model_name = os.environ.get(ENV_MODEL_NAME)
    if model_id and model_name:
        return model_name, model_id
    if model_id:
        return model_id, model_id
    return None
