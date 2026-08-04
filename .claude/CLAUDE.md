# comfy-desktop-plugins

本项目是 ComfyUI Desktop 的插件扩展项目, 毗邻 ComfyUI 核心项目运行。

## ComfyUI 项目概况

| 属性 | 值 |
|------|-----|
| 位置 | `D:\Comfy-Desktop\ComfyUI-Installs\Default\ComfyUI\` |
| 版本 | **0.29.0** (2025-07-29, 提交 `a8c44f9b`) |
| 语言 | Python >=3.10 |
| 许可证 | GPL-3.0 |
| 包名 | `ComfyUI` |
| 上游 | https://github.com/comfyanonymous/ComfyUI |
| 文档 | https://docs.comfy.org/ |

### 核心依赖

- PyTorch (torch, torchvision, torchaudio, torchsde)
- transformers>=4.50.3, tokenizers>=0.13.3, safetensors>=0.4.2
- numpy>=1.25.0, einops, scipy, Pillow
- aiohost>=3.11.8 (HTTP/WebSocket 服务器), yarl>=1.18.0
- alembic + SQLAlchemy>=2.0.0 (数据库)
- pydantic~2.0, pydantic-settings~2.0
- av>=16.0.0 (音视频处理)
- **comfyui-frontend-package==1.47.10** (前端)
- **comfy-kitchen==0.2.22** (优化算子库: RMS RoPE, fp8 等)
- **comfy-aimdo==0.4.10** (Dynamic VRAM 管理)
- filelock, blake3, psutil, PyOpenGL, spandrel, kornia

---

## 项目目录结构

### ComfyUI 核心 (`Default/ComfyUI/`)

```
Default/ComfyUI/
├── main.py                     # 入口: 参数解析 → 初始化 → 事件循环启动
├── server.py                   # WebSocket + HTTP 服务器 (aiohttp), prompt 队列管理
├── execution.py                # 节点图执行引擎 (61K, 异步队列/缓存策略/进度钩子)
├── nodes.py                    # 核心内置节点 (107K, ~3500+ 行)
├── folder_paths.py             # 路径管理: models/input/output/temp/custom_nodes
├── node_helpers.py             # 节点辅助工具
├── protocol.py                 # BinaryEventTypes (WebSocket 二进制协议)
├── hook_breaker_ac10a0.py      # 钩子恢复机制 (自定义节点 import 后恢复被覆盖的钩子)
├── comfyui_version.py          # __version__ = "0.29.0"
├── execution.py                # PromptExecutor, CAcheType, PromptQueue
│
├── comfy/                      # ★ 核心引擎层 (50+ 模块)
│   ├── cli_args.py             # CLI 参数解析 (~220 行), 含 --listen/--port/--gpu/--cache 等
│   ├── options.py              # args_parsing 开关
│   ├── model_management.py     # GPU/CPU VRAM 状态管理, 模型卸载/加载策略
│   ├── memory_management.py    # 张量内存分配器, aimdo 集成
│   ├── model_base.py           # 模型基类, 集成所有 LDM 架构 (flux/hunyuan/wan/cosmos...)
│   ├── model_patcher.py        # 模型补丁机制 (支持 ModelPatcherDynamic DynamicVRAM)
│   ├── model_detection.py      # 模型自动检测/分类
│   ├── model_prefetch.py       # 模型预取优化
│   ├── model_sampling.py       # 采样调度器 (噪声调度)
│   ├── sample.py               # 核心采样循环
│   ├── samplers.py             # 采样器实现 (DDIM/DDPM/DPM++/Euler/...)
│   ├── sampler_helpers.py      # 采样辅助工具
│   ├── sd.py                   # SD 模型加载/管理
│   ├── sd1_clip.py             # SD1.x CLIP 文本编码器
│   ├── sdxl_clip.py            # SDXL CLIP 文本编码器
│   ├── clip_model.py           # CLIP 模型抽象
│   ├── clip_vision.py          # CLIP Vision 模型 (含 siglip2)
│   ├── controlnet.py           # ControlNet 模型
│   ├── lora.py                 # LoRA 加载/合并
│   ├── lora_convert.py         # LoRA 格式转换
│   ├── conds.py                # Conditioning 编码/加权
│   ├── latent_formats.py       # 潜在空间格式定义
│   ├── hooks.py                # 模型钩子机制
│   ├── patcher_extension.py    # Patcher 扩展接口
│   ├── ops.py                  # 自定义算子/操作 (RMS RoPE, fp8 等)
│   ├── quant_ops.py            # 量化算子
│   ├── float.py                # 浮点精度工具
│   ├── rmsnorm.py              # RMSNorm 实现
│   ├── nested_tensor.py        # 嵌套张量支持
│   ├── multigpu.py             # 多 GPU 支持
│   ├── pinned_memory.py        # 固定内存分配
│   ├── pixel_space_convert.py  # 像素空间 ⇄ 潜在空间转换
│   ├── comfy_api_env.py        # API 环境覆盖 (云/本地环境)
│   ├── deploy_environment.py   # 部署环境检测
│   ├── supported_models.py     # 支持的模型列表 (检测/分类)
│   ├── supported_models_base.py # 模型基类定义
│   ├── context_windows.py      # 上下文窗口管理 (视频模型)
│   ├── bg_removal_model.py     # 背景移除模型
│   ├── diffusers_convert.py    # Diffusers 格式转换
│   ├── diffusers_load.py       # Diffusers 加载
│   ├── gligen.py               # GLIGEN 接地
│   ├── utils.py                # 通用工具 (图像/张量操作)
│   │
│   ├── comfy_types/            # 类型定义
│   │   ├── __init__.py         # UnetApplyFunction, UnetParams 等协议
│   │   ├── node_typing.py      # IO, InputTypeDict, ComfyNodeABC
│   │   └── examples/           # 类型使用示例
│   │
│   ├── ldm/                    # ★ 具体 LDM 架构实现 (30+ 模型家族)
│   │   ├── flux/               # Flux.1 模型
│   │   ├── hunyuan_video/      # Hunyuan 视频
│   │   ├── hunyuan3d/          # Hunyuan 3D
│   │   ├── hunyuan3dv2_1/      # Hunyuan 3D v2.1
│   │   ├── wan/                # Wan 视频/图像
│   │   ├── cosmos/             # Cosmos 世界模型
│   │   ├── lumina/             # Lumina 模型
│   │   ├── lightricks/         # Lightricks (LTXV) 视频
│   │   ├── pixart/             # PixArt-α
│   │   ├── cascade/            # Stable Cascade
│   │   ├── audio/              # 音频扩散模型
│   │   ├── mmaudio/            # MM Audio
│   │   ├── hidream/            # HiDream
│   │   ├── hidream_o1/         # HiDream O1
│   │   ├── ace/                # ACE 模型
│   │   ├── omnigen/            # OmniGen
│   │   ├── chroma/             # Chroma
│   │   ├── chroma_radiance/    # Chroma Radiance
│   │   ├── seedvr/             # Seed VR
│   │   ├── boogu/              # BooGu
│   │   ├── mage_flow/          # MageFlow
│   │   ├── cogvideo/           # CogVideo
│   │   ├── pixeldit/           # PixelDIT
│   │   ├── qwen_image/         # Qwen 图像
│   │   ├── sam3/               # SAM3 分割
│   │   ├── depth_anything_3/   # Depth Anything v3
│   │   ├── rt_detr/            # RT-DETR 检测
│   │   ├── ernie/              # Ernie 模型
│   │   ├── anima/              # Anima
│   │   ├── joyimage/           # JoyImage
│   │   ├── krea2/              # KREA 2
│   │   ├── kolors/             # Kolors
│   │   ├── ideogram4/          # Ideogram 4
│   │   ├── kandinsky5/         # Kandinsky 5
│   │   ├── suir/               # SUPIR 超分
│   │   ├── lens/               # Lens 模型
│   │   ├── triposplat/         # TripoSplat 3D
│   │   ├── modules/            # 共享模块 (diffusionmodules/attention/etc.)
│   │   ├── models/             # 模型基类
│   │   └── util.py             # LDM 工具函数
│   │
│   ├── k_diffusion/            # Karras diffusion 采样器
│   ├── extra_samplers/         # 额外采样器
│   ├── text_encoders/          # 各类文本编码器
│   ├── image_encoders/         # 图像编码器 (DINOv2, etc.)
│   ├── audio_encoders/         # 音频编码器
│   ├── t2i_adapter/            # T2I-Adapter
│   ├── cldm/                   # 可控 LDM
│   ├── taesd/                  # Tiny AE (快速预览)
│   ├── weight_adapter/         # 权重适配器
│   ├── sdxl_clip/              # SDXL CLIP
│   └── sd1_tokenizer/          # SD1.x tokenizer
│
├── comfy_execution/            # ★ 执行引擎
│   ├── graph.py                # DynamicPrompt, ExecutionBlocker, ExecutionList, get_input_info
│   ├── graph_utils.py          # GraphBuilder, is_link
│   ├── caching.py              # 缓存策略: Basic/Null/LRU/Hierarchical/RAMPressure
│   ├── cache_provider.py       # 缓存提供者抽象
│   ├── jobs.py                 # 作业状态管理 (JobStatus PENDING/RUNNING/COMPLETED/FAILED/CANCELLED)
│   ├── validation.py           # 节点输入验证
│   ├── progress.py             # 进度管理, 预览图像
│   ├── utils.py                # CurrentNodeContext, get_executing_context
│   └── asset_enrichment.py     # 输出资产富化
│
├── comfy_extras/               # ★ 额外节点 (90+ 文件, 各类模型/功能节点)
│   ├── nodes_flux.py           # Flux 模型节点
│   ├── nodes_hunyuan.py        # Hunyuan 视频节点
│   ├── nodes_wan.py            # Wan 视频/图像节点
│   ├── nodes_video.py          # 通用视频处理
│   ├── nodes_audio.py          # 音频处理
│   ├── nodes_controlnet.py     # ControlNet 节点
│   ├── nodes_advanced_samplers.py # 高级采样器
│   ├── nodes_edit_model.py     # 模型编辑
│   ├── nodes_model_merging.py  # 模型合并
│   ├── nodes_latent.py         # 潜在空间操作
│   ├── nodes_mask.py           # 遮罩处理
│   ├── nodes_text.py           # 文本处理
│   ├── nodes_primitive.py      # 原始类型节点
│   ├── nodes_logic.py          # 逻辑控制
│   ├── nodes_math.py           # 数学运算
│   ├── nodes_seed.py           # 种子控制
│   ├── nodes_image.py          # 图像处理
│   ├── nodes_color.py          # 色彩处理
│   ├── nodes_cond.py           # Conditioning 操作
│   ├── nodes_custom_sampler.py # 自定义采样器
│   ├── nodes_post_processing.py # 后处理
│   ├── nodes_upscale_model.py  # 放大模型
│   ├── nodes_video_model.py    # 视频模型
│   └── ... (90+ 文件)
│
├── comfy_api/                  # ★ 版本化 API 层 (供自定义节点/插件使用)
│   ├── version_list.py         # [latest, v0.0.2, v0.0.1]
│   ├── feature_flags.py        # WebSocket 协议特性标志, CLI 可配置
│   ├── generate_api_stubs.py   # API 存根生成
│   │
│   ├── internal/               # API 内部基础设施
│   │   ├── api_registry.py     # ComfyAPIBase, register_versions, version 解析
│   │   ├── singleton.py        # ProxiedSingleton 基类
│   │   ├── async_to_sync.py    # 异步→同步包装器
│   │   └── __init__.py         # _ComfyNodeInternal, _NodeOutputInternal, as_pruned_dict
│   │
│   ├── latest/                 # latest API (当前开发版本, 不稳定)
│   │   ├── __init__.py         # ComfyAPI_latest: NodeReplacement / Execution / Caching
│   │   ├── _io_public.py       # IO 类型导出
│   │   ├── _ui_public.py       # UI 类型导出
│   │   ├── _input/             # ImageInput, AudioInput, MaskInput, LatentInput, VideoInput
│   │   ├── _input_impl/        # VideoFromFile, VideoFromComponents
│   │   ├── _io.py              # IO 基础设施
│   │   ├── _ui.py              # UI 基础设施
│   │   ├── _caching.py         # 缓存 API
│   │   └── _util/              # VideoCodec, VideoContainer, VideoComponents, 3D 文件类型
│   │
│   ├── v0_0_2/                 # v0.0.2 稳定 API
│   │   ├── generated/          # 生成的存根
│   │   └── __init__.py         # ComfyAPIAdapter_v0_0_2
│   │
│   ├── v0_0_1/                 # v0.0.1 API (仅作模板, 不应使用)
│   │
│   ├── input/                  # 输入辅助
│   ├── input_impl/             # 输入实现 (basic/curve/range/video)
│   └── util/                   # API 工具
│
├── comfy_api_nodes/            # ★ Partner API 节点 (30+ 第三方服务)
│   ├── apis/                   # API 客户端实现
│   │   ├── anthropic.py        # Anthropic Claude
│   │   ├── openai.py           # OpenAI
│   │   ├── gemini.py           # Google Gemini
│   │   ├── grok.py             # xAI Grok
│   │   ├── bytedance.py        # ByteDance
│   │   ├── bytedance_llm.py    # ByteDance LLM
│   │   ├── recraft.py          # Recraft V4.1
│   │   ├── bfl.py              # BFL (Black Forest Labs)
│   │   ├── bria.py             # Bria AI
│   │   ├── kling.py            # Kling (快手)
│   │   ├── luma.py             # Luma AI
│   │   ├── runway.py           # Runway
│   │   ├── minimax.py          # MiniMax
│   │   ├── elevenlabs.py       # ElevenLabs 语音
│   │   ├── heygen.py           # HeyGen 数字人
│   │   ├── topaz.py            # Topaz 放大
│   │   ├── vidu.py             # Vidu 视频
│   │   ├── veo.py              # Google Veo 2
│   │   ├── wan.py              # Wan 视频
│   │   ├── pixverse.py         # PixVerse
│   │   ├── sora.py             # OpenAI Sora
│   │   ├── meshy.py            # Meshy 3D
│   │   ├── tripo.py            # Tripo 3D
│   │   ├── rodin.py            # Rodin 3D
│   │   ├── hunyuan3d.py        # Hunyuan 3D
│   │   ├── magnificent.py      # Magnific
│   │   ├── ideogram.py         # Ideogram
│   │   ├── krea.py             # KREA
│   │   ├── beeble.py           # Beeble
│   │   ├── reve.py             # Reve
│   │   ├── sonilo.py           # Sonilo
│   │   ├── hitpaw.py           # HitPaw
│   │   ├── quiver.py           # Quiver
│   │   ├── sync_so.py          # Sync.so
│   │   ├── wavespeed.py        # WaveSpeed
│   │   └── openrouter.py       # OpenRouter
│   │
│   ├── util/                   # API 工具
│   │   ├── client.py           # HTTP 客户端基类
│   │   ├── _helpers.py         # 辅助函数
│   │   ├── upload_helpers.py   # 上传辅助
│   │   ├── download_helpers.py # 下载辅助
│   │   ├── validation_utils.py # 输入验证
│   │   ├── conversions.py      # 格式转换
│   │   ├── common_exceptions.py # 异常定义
│   │   └── request_logger.py   # 请求日志
│   │
│   └── nodes_*.py              # 前端节点定义
│       ├── nodes_anthropic.py  (12K)
│       ├── nodes_gemini.py     (70K)
│       ├── nodes_bytedance.py  (118K, 最大)
│       ├── nodes_kling.py      (143K)
│       ├── nodes_openai.py     (52K)
│       ├── nodes_recraft.py    (54K)
│       └── ... (共 38 个文件)
│
├── api_server/                 # HTTP API 服务器
│   ├── routes/
│   │   └── internal/           # /internal/* 路由 (仅供前端, 不保证稳定)
│   │       └── internal_routes.py  # 日志 / 文件夹路径 / 文件列表 / 文件操作
│   └── services/
│       └── terminal_service.py # 终端/日志 WebSocket 推送
│
├── app/                        # ★ 应用管理层
│   ├── __init__.py
│   ├── logger.py               # 日志系统 (环形缓冲区, 颜色输出)
│   ├── frontend_management.py  # 前端版本管理/下载
│   ├── custom_node_manager.py  # 自定义节点翻译加载 (locales/)
│   ├── user_manager.py         # 用户管理/认证
│   ├── model_manager.py        # 模型文件管理
│   ├── subgraph_manager.py     # 子图管理器
│   ├── node_replace_manager.py # 节点替换管理
│   ├── app_settings.py         # 应用设置 REST API
│   │
│   ├── assets/                 # ★ 资产管理 (数据库驱动)
│   │   ├── seeder.py           # 资产扫描器 (models/input/output)
│   │   ├── scanner.py          # 文件扫描
│   │   ├── helpers.py          # 辅助函数
│   │   ├── api/                # REST API
│   │   │   ├── routes.py       # /assets/* 路由
│   │   │   ├── upload.py       # 文件上传
│   │   │   ├── schemas_in.py   # 请求 Schema
│   │   │   └── schemas_out.py  # 响应 Schema
│   │   ├── database/           # 数据库模型
│   │   │   ├── models.py       # Asset, AssetReference, AssetFolder 等 ORM
│   │   │   └── queries/        # 数据库查询
│   │   └── services/           # 业务逻辑
│   │       ├── asset_management.py  # 资产管理
│   │       ├── ingest.py       # 文件导入
│   │       ├── bulk_ingest.py  # 批量导入
│   │       ├── cursor.py       # 游标分页
│   │       ├── file_utils.py   # 文件工具
│   │       ├── hashing.py      # 哈希计算
│   │       ├── image_dimensions.py # 图像尺寸
│   │       ├── metadata_extract.py # 元数据提取
│   │       ├── path_utils.py   # 路径工具
│   │       ├── schemas.py      # Service Schema
│   │       └── tagging.py      # 标签系统
│   │
│   └── database/               # 数据库层
│       ├── db.py               # SQLAlchemy + alembic 初始化
│       └── models.py           # ORM 基类 (Base, to_dict)
│
├── middleware/                  # aiohttp 中间件
│   └── cache_middleware.py     # 缓存控制
│
├── utils/                      # 通用工具
│   ├── extra_config.py         # extra_model_paths.yaml 加载
│   ├── mime_types.py           # MIME 类型初始化
│   ├── json_util.py            # JSON 合并工具
│   └── install_util.py         # 安装/包版本检查
│
├── alembic_db/                 # 数据库迁移脚本
├── alembic.ini                 # Alembic 配置
├── comfy_config/               # 配置解析
│   ├── config_parser.py        # 配置解析器
│   └── types.py                # 配置类型
│
├── custom_nodes/               # 自定义节点目录
├── models/                     # 模型存储目录
├── input/                      # 输入文件目录
├── output/                     # 输出文件目录
├── temp/                       # 临时文件目录
├── user/                       # 用户数据目录
│
├── tests/                      # 单元测试
├── tests-unit/                 # 单元测试 (新)
├── blueprints/                 # App Mode 蓝图
├── script_examples/            # 脚本示例
├── .ci/                        # CI 配置
├── .github/                    # GitHub Actions
│
├── AGENTS.md                   # AI 编码指南 (保持改动小/删除死代码/架构分层)
├── .coderabbit.yaml            # CodeRabbit 配置
├── .spectral.yaml              # Spectral lint 配置
│
├── requirements.txt            # pip 依赖
├── pyproject.toml              # 项目配置 (ruff + pylint)
└── openapi.yaml                # OpenAPI 规范 (217K)
```

---

## 架构分层

```
┌─────────────────────────────────────────────────┐
│              app/ (应用管理层)                    │
│  logger / user_manager / model_manager / assets  │
│  app_settings / subgraph / node_replace          │
│  database (SQLAlchemy + alembic)                  │
└───────────────────────┬─────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────┐
│         api_server/ (HTTP API 服务层)            │
│     internal_routes (/internal/*)               │
│     terminal_service (WS 日志推送)               │
│     + app_settings (/settings/*)                │
│     + assets (/assets/*)                        │
└───────────────────────┬─────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────┐
│          server.py (WebSocket 核心层)            │
│  客户端连接管理 / prompt 队列 / 任务分发 /       │
│  消息推送 / 中间件 (CORS/压缩/废弃路径警告)      │
│  BinaryEventTypes 二进制协议                     │
└───────────────────────┬─────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────┐
│       execution.py (执行引擎层)                  │
│ 图遍历 / 异步执行 / 缓存策略 / 进度钩子          │
│ PromptExecutor / CacheType / JobStatus           │
│ hook_breaker / asset_enrichment                  │
└───────────┬───────────────────────┬─────────────┘
            │                       │
┌───────────▼──────────┐ ┌─────────▼─────────────┐
│   nodes.py +         │ │  comfy_extras/ (90+)   │
│   comfy_api_nodes/   │ │  + comfy_api_nodes/    │
│   核心节点 + Partner │ │  (38 Partner 节点)     │
│   API 节点           │ │                        │
└───────────┬──────────┘ └─────────┬──────────────┘
            │                      │
┌───────────▼──────────────────────▼──────────────┐
│         comfy/ (核心引擎层)                      │
│   模型加载 / 推理 / 采样 / 内存管理 / 算子      │
│   ┌──────────────────────────────────────────┐  │
│   │  ldm/ (30+ 模型架构实现)                 │  │
│   │  flux, hunyuan, wan, cosmos,            │  │
│   │  cascade, pixart, audio, lightricks...  │  │
│   └──────────────────────────────────────────┘  │
│   VRAM 状态: DISABLED → SHARED                  │
│   DynamicVRAM: ModelPatcherDynamic              │
└─────────────────────────────────────────────────┘
```

---

## 关键架构模式

### 1. 版本化 API (`comfy_api/`)

ComfyUI 为插件提供**版本化适配器模式** API:

```
comfy_api/
├── internal/api_registry.py   ComfyAPIBase + register_versions()
├── version_list.py            [latest, v0.0.2, v0.0.1]
├── latest/                    当前开发版本 (不稳定, STABLE=False)
├── v0_0_2/                    稳定版本 (STABLE=True)
└── v0_0_1/                    模板 (不应使用)
```

- 每个版本定义 `VERSION` + `STABLE` 属性, 使用适配器模式继承
- 同步/异步双模式: `ComfyAPISync = create_sync_class(ComfyAPIAdapter)`
- 插件应使用 `from comfy_api.v0_0_2 import ...` (稳定) 而非 `latest`

### 2. 节点图执行引擎 (`comfy_execution/`)

- **图结构**: `graph.py` — DynamicPrompt / ExecutionBlocker / ExecutionList / 基于链接的图遍历
- **缓存策略**: `caching.py` — BasicCache / NullCache / LRUCache / HierarchicalCache / RAMPressureCache
- **缓存键**: `CacheKeySetID` (按节点ID) / `CacheKeySetInputSignature` (按输入签名)
- **作业管理**: `jobs.py` — JobStatus (PENDING/RUNNING/COMPLETED/FAILED/CANCELLED)
- **验证**: `validation.py` — 节点输入类型/形状验证

### 3. 模型与内存管理 (`comfy/`)

- **VRAM 状态机**: `DISABLED → NO_VRAM → LOW_VRAM → NORMAL_VRAM → HIGH_VRAM → SHARED`
- **DynamicVRAM**: `comfy-aimdo==0.4.10 + ModelPatcherDynamic` (PyTorch>=2.8 自动启用)
- **模型检测**: 自动识别模型架构并分配正确加载器
- **模型补丁**: ModelPatcher 支持 LoRA/ControlNet 注入式修改
- **优化算子**: `comfy-kitchen==0.2.22` 提供 RMS RoPE, fp8 等优化

### 4. CLI 参数体系 (`comfy/cli_args.py`)

| 类别 | 关键参数 |
|------|---------|
| 网络 | `--listen` / `--port` / `--tls-keyfile` / `--cors` / `--max-upload-size` |
| 精度 | `--force-fp32/fp16` / `--fp8_e4m3fn/fp8_e5m2-unet` / `--bf16-unet` |
| 内存 | `--gpu-only/highvram/lowvram/novram/cpu` / `--reserve-vram` / `--vram-headroom` |
| 缓存 | `--cache-ram` / `--cache-classic` / `--cache-lru` / `--cache-none` |
| 注意力 | `--use-split/quad/pytorch/sage/flash-cross-attention` |
| 功能 | `--enable-manager` / `--multi-user` / `--fast` / `--deterministic` |

### 5. Feature Flags (`comfy_api/feature_flags.py`)

- WebSocket 协议版本协商: 前端/后端能力发现
- CLI 可配置: `--feature show_signin_button=true`
- 注册表驱动: `CLI_FEATURE_FLAG_REGISTRY`

### 6. 资产管理 (`app/assets/`)

- 数据库驱动 (SQLAlchemy + alembic)
- 自动扫描: `models/`, `input/`, `output/` 目录
- 功能: 哈希计算 / 元数据提取 / 图像尺寸检测 / 标签系统 / 批量导入
- Asset ORM 模型: `Asset` / `AssetReference` / `AssetFolder`

### 7. 自定义节点系统

- 位于 `custom_nodes/` 目录, 每个子目录是一个独立 Python 包
- 可禁用: `--disable-all-custom-nodes` + `--whitelist-custom-nodes`
- 支持 prestartup 脚本: `prestartup_script.py` (在 import 前执行)
- 翻译系统: `locales/` → `custom_node_manager.py` 加载
- 钩子恢复: `hook_breaker_ac10a0.py` 在自定义节点 import 后恢复被覆盖的 Python 钩子
- 可禁用 API 节点: `--disable-api-nodes` (阻止前端访问互联网)

### 8. 数据库

- **引擎**: SQLAlchemy 2.0+ ORM + alembic 迁移
- **默认**: SQLite (可配置 `--database-url`)
- **模型**: `app/database/models.py` (基类) + `app/assets/database/models.py` (资产)
- **初始化**: `app/database/db.py` — 依赖可选, 降级兼容

---

## 插件开发接口

本插件项目应通过 `comfy_api` 的版本化 API 与 ComfyUI 交互, 避免直接导入内部模块。

### 推荐 API 入口

```python
# 稳定 API (推荐)
from comfy_api.v0_0_2 import ComfyAPI, Input, Types

# 最新 API (可能有破坏性变更)
from comfy_api.latest import io, ui
from comfy_api.latest import ImageInput, AudioInput, VideoInput

# 节点类型定义
from comfy.comfy_types import IO, ComfyNodeABC, InputTypeDict
```

### 插件可扩展的点

| 扩展点 | 方式 |
|--------|------|
| 自定义节点 | `custom_nodes/` 下注册 `NODE_CLASS_MAPPINGS` |
| 节点替换 | `ComfyAPI.NodeReplacement().register(...)` |
| 执行进度 | `ComfyAPI.Execution().set_progress(...)` |
| 模型补丁 | `patcher_extension.py` / `model_patcher` |
| 资产服务 | `app/assets/services/` 注册自定义处理 |

---

## AGENTS.md 工程风格要点

```text
- 保持改动小且直接, 最窄代码路径修复问题
- 宁删功能路径也不要保留复杂的局部修复
- 删除死代码、废弃 fallback、未使用的选项
- 保持各层聚焦: 不把 UI/API/持久化泄露到无关层
- 传递最窄的数据跨边界, 避免宽泛的 context 对象
- 代码必须看起来像手写, 拒绝 AI 生成的通用风格
```

---

## 开发注意事项

1. **许可证**: GPL-3.0, 衍生代码需兼容
2. **API 稳定性**: `comfy_api/latest` 不稳定, 生产插件应锁定到 `v0_0_2`
3. **内部模块**: `comfy/` 内部 API 无版本保证, 避免直接依赖
4. **节点注册**: 全局变量 `NODE_CLASS_MAPPINGS` + `NODE_DISPLAY_NAME_MAPPINGS`
5. **WebSocket**: 协议通过 `server.py` + `feature_flags.py` 管理
6. **prestartup 脚本**: 自定义节点可在 import 前执行, 但需注意钩子恢复
7. **数据库**: 可选依赖, 需处理降级场景 (`dependencies_available()`)

---

## 参考

- 官方文档: https://docs.comfy.org/
- 仓库: https://github.com/comfyanonymous/ComfyUI
- API 定义: `Default/ComfyUI/openapi.yaml`
- 节点示例: `Default/ComfyUI/comfy_extras/nodes_*.py`
- Partner 节点: `Default/ComfyUI/comfy_api_nodes/nodes_*.py`
- 前端包: `comfyui-frontend-package==1.47.10`
- 开发指南: `Default/ComfyUI/AGENTS.md`

---

## 项目规则 (`.claude/rules/`)

| 规则文件 | 说明 |
|---------|------|
| [rules/project.md](rules/project.md) | 项目开发规范: API 使用, 节点开发, 错误处理, 异步执行 |
| [rules/seedance-video.md](rules/seedance-video.md) | Seedance 2.0 视频生成: 模型版本, 节点参数, 定价, 预处理约束 |
