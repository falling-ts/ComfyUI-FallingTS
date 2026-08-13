# 项目开发规范

## 项目定位

本项目是 ComfyUI 的插件扩展项目, 毗邻 `ComfyUI\` 核心项目运行。所有插件代码应通过 ComfyUI 的版本化 API (`comfy_api/`) 交互。

## 核心原则

### 1. 通过版本化 API 集成

```python
# ✅ 正确: 使用稳定 API
from comfy_api.v0_0_2 import ComfyAPI, Input, Types

# ✅ 正确: 使用 latest API (开发中)
from comfy_api.latest import io, ui
from comfy_api.latest import ImageInput, AudioInput, VideoInput

# ❌ 错误: 直接导入内部模块
from comfy.sd import ...         # 不稳定的内部 API
from execution import ...        # 不稳定的内部 API
from comfy_execution import ...  # 不稳定的内部 API
```

### 2. 节点开发规范

- 节点类继承 `IO.ComfyNode`
- 使用 `define_schema(cls)` 定义输入/输出/分类
- 使用 `execute(cls, ...)` 实现执行逻辑
- 节点注册到全局 `NODE_CLASS_MAPPINGS` + `NODE_DISPLAY_NAME_MAPPINGS`
- api 节点需标记 `is_api_node=True`

```python
class MyCustomNode(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="MyCustomNode",
            display_name="My Custom Node",
            category="my/category",
            description="Description",
            inputs=[...],
            outputs=[...],
            hidden=[IO.Hidden.auth_token_comfy_org],
            is_api_node=True,
        )

    @classmethod
    async def execute(cls, ...) -> IO.NodeOutput:
        ...
```

### 3. API 节点输入类型

| 输入类型 | 使用场景 |
|---------|---------|
| `IO.String.Input` | 文本输入 |
| `IO.Combo.Input` | 单选下拉 |
| `IO.DynamicCombo.Input` | 模型关联的动态选项 |
| `IO.Image.Input` | 图像输入 |
| `IO.Video.Input` | 视频输入 |
| `IO.Int.Input` | 整数输入 (支持 `control_after_generate`) |
| `IO.Float.Input` | 浮点数输入 |
| `IO.Boolean.Input` | 布尔开关 |
| `IO.Hidden.*` | 隐藏参数 (auth token, api key 等) |

### 4. 错误处理

- 使用 `validate_string()` / `validate_image_dimensions()` / `validate_image_aspect_ratio()` 进行输入验证
- 所有验证失败直接 `raise ValueError(...)` 或 `raise RuntimeError(...)`
- 避免静默吞异常

### 5. 异步执行

- `execute` 方法必须声明为 `async def`
- 使用 `sync_op()` 发起 API 请求
- 使用 `poll_op()` 轮询异步任务状态
- 使用 `upload_images_to_comfyapi()` 上传图像资产
