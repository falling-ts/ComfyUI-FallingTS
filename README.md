# comfy-desktop-plugins

ComfyUI Desktop 插件扩展项目。提供自定义视频生成节点, 通过 Volcengine API 接入 Seedance 2.0 模型。

## 节点列表

| 节点 | Node ID | 功能 |
|------|---------|------|
| Seedance 2.0 Text to Video | `Seedance2TextToVideo` | 文生视频 |
| Seedance 2.0 Image to Video | `Seedance2ImageToVideo` | 图生视频(首帧) |
| Seedance 2.0 First-Last-Frame to Video | `Seedance2FirstLastFrame` | 首尾帧生视频 |
| Seedance 2.0 Reference to Video | `Seedance2Reference` | 多模态参考生视频 |

## 安装方式

### 方式 A: custom_nodes/ 自动加载 (推荐, 0 行修改)

```bash
# 在 ComfyUI custom_nodes 目录下创建符号链接
cd D:/Comfy-Desktop/ComfyUI-Installs/Default/ComfyUI/custom_nodes
mklink /D comfy-desktop-plugins D:/Comfy-Desktop/ComfyUI-Installs/comfy-desktop-plugins
```

### 方式 B: 一行代码注入 main.py

在 `Default/ComfyUI/main.py` 中, 在 `start_comfyui()` 调用前添加:

```python
# 推荐插入位置: main.py ~line 487, 在 def start_comfyui() 之前
import comfy_desktop_plugins.plugin
comfy_desktop_plugins.plugin.inject()
```

### 方式 C: 直接复制

```bash
copy D:\Comfy-Desktop\ComfyUI-Installs\comfy-desktop-plugins D:\Comfy-Desktop\ComfyUI-Installs\Default\ComfyUI\custom_nodes\comfy_desktop_plugins
```

## 前置条件

1. **开通 Seedance 2.0 服务**: https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement
2. **获取 API Key**: https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey
3. **账户余额 > 200 元** 或已购买资源包

## 使用

1. 在 ComfyUI 节点列表中搜索 "Seedance"
2. 拖入节点, 填入 Volcengine API Key
3. 选择模型、分辨率、时长等参数
4. 连接输入/输出, 运行工作流

## 架构

```
comfy-desktop-plugins/
├── __init__.py          # 入口, 导出 NODE_CLASS_MAPPINGS
├── plugin.py            # 节点注册逻辑
├── config.py            # .env 配置管理 (根级别, 到处可用)
├── seedance/            # 📹 Seedance 视频生成节点
│   ├── seedance.py      #   4 个节点定义
│   ├── api.py           #   Volcengine HTTP 客户端
│   └── models.py        #   请求/响应数据模型 + 定价
├── mcp/                 # MCP 服务器文档
└── .env.example         # 环境配置模板
```

## 依赖

- 运行在 ComfyUI 环境中
- 复用 `comfy_api_nodes.util` 中的工具 (client/upload/download/conversion/validation)
- 无额外依赖
