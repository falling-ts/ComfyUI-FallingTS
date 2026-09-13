# ComfyUI-FallingTS

我的 ComfyUI 自定义节点插件:通用工具节点集(Continue/Route/Selector/Table/Switch/MarkDown 数据表/多图合成)+ 媒体预览保存节点(图片/视频/音频)+ 前端增强。位于 `custom_nodes\ComfyUI-FallingTS`,经根 `custom_nodes` 目录级软链接被 ComfyUI 加载。

## 项目目录结构

```
ComfyUI-FallingTS/
├── plugin.py                   # 插件入口:V1 节点注册表 (NODE_CLASS_MAPPINGS, 15 节点) + V3 ComfyExtension (DesktopPluginsExtension)
├── __init__.py                 # 包初始化
├── AGENTS.md                   # AI 编码指南(本文件)
├── CLAUDE.md                   # Claude Code 垫片,内容为 @AGENTS.md
├── README.md                   # 项目说明
├── LICENSE                     # 许可证
├── .gitignore                  # git 忽略规则
├── .env                        # 本地环境配置(含密钥,已忽略)
├── .agents/                    # 智能体配置目录
│   └── rules/
│       └── project.md          # 项目开发规范 (API 使用/节点开发/错误处理/异步执行)
├── .claude                     # 指向 .agents 的相对符号链接 (Claude Code 兼容垫片)
├── locales/
│   └── zh/
│       └── nodeDefs.json       # 中文节点定义/显示名
├── proceed/
│   └── nodes.py                # FallingTSContinueNode 继续节点
├── route/
│   └── nodes.py                # FallingTSRouteNode 路由节点 (total组路由, 参考分组开关)
├── fanout/
│   ├── __init__.py
│   └── nodes.py                # FallingTSFanoutNode 扇出选择 (多对一的镜像: total=组数=输入数, 每组一个 input_i, 输出=组数×组名数, 选中项下拉(可连线接多对一 选中项组名/索引, 索引直接选中所属索引组名), 每组 input_i 路由到选中组名对应输出)
├── selector/
│   └── nodes.py                # FallingTSSelectorNode 多对一选择 (下拉 + 组号, 通用 ANY)
├── table/
│   └── nodes.py                # FallingTSTableNode 通用表格 (Excel 式)
├── switch/
│   └── nodes.py                # FallingTSSwitchNode 分组开关 (total组)
├── mdtable/
│   ├── __init__.py
│   ├── nodes.py                # FallingTSMarkDownTableNode MarkDown 数据表
│   └── parser.py               # 表格解析
├── fps/
│   └── nodes.py                # FallingTSFrameRateConvertNode 帧率转换 (按目标帧率抽帧, 目标帧率未连接/None 原样透传)
├── composite/
│   ├── __init__.py
│   └── nodes.py                # FallingTSImageCompositeNode total 驱动 N 图合成 (total 最少 1 不设上限默认 4, 左侧 image1..imageN 图端口 + 节点内 label1..labelN 标注表单文本框; 列数 = ceil(sqrt(N)) 行优先填充, 统一尺寸, 每张子图左上角中文标注, 合成单张图)
├── video-components/
│   └── nodes.py                # FallingTSVideoComponentsNode 视频拆解 (参考视频 → 帧/音频/帧率/位深/色彩空间; None 安全替代核心 GetVideoComponents: video 可选, None 时全部输出 None 且**不 sticky 回放**)
├── h3-guide/
│   └── nodes.py                # FallingTSH3AddGuideNode H3 引导锚定 (None 安全替代核心 MiniMaxH3AddGuide: image 与 audio 同为 None 时**原样透传 positive**, 关键帧列因此可留空; 有值时直接委派 `MiniMaxH3AddGuide.execute`, 不复制其实现)
├── fonts/
│   └── Alibaba-PuHuiTi-Heavy.ttf  # CJK 字体 (随包, 合成节点标注渲染用)
├── preview-image/
│   ├── __init__.py
│   └── nodes.py                # PreviewImageSaveNode 图片预览保存
├── preview-video/
│   ├── __init__.py
│   └── nodes.py                # PreviewVideoNode 视频预览保存
├── preview-audio/
│   ├── __init__.py
│   └── nodes.py                # PreviewAudioSaveNode 音频预览保存 (纯预览 + 「保存」, 不切段)
├── audio-trim/
│   ├── __init__.py
│   └── nodes.py                # FallingTSAudioTrimNode 音频截段 (波形拖选区 → 多段输出 + 保存)
├── mask-rename/
│   └── nodes.py                # 遮罩编辑器文件整理:包装 /upload/image 路由 + POST /fallingts_mask/rename
└── web/
    └── js/                     # 前端扩展脚本 (经 GET /extensions 加载,不参与前端打包)
        ├── assets_tab_rename.js        # 媒体资产面板「已导入」→「已保存」
        ├── mask-rename.js              # PreviewImageSave 遮罩编辑器保存联动
        ├── md_table.js                 # MarkDown 数据表前端 (选文件/内嵌表格弹窗)
        ├── media_lightbox_zoom.js      # 全屏预览缩放 (滚轮/拖拽/双击/快捷键)
        ├── node_image_middleclick.js   # 节点中键 → 全屏大图预览
        ├── preview-image.js            # PreviewImageSave 底部控件 + 保存按钮
        ├── preview-video.js            # PreviewVideo 底部保存按钮 + 截帧/完成 + restoreFrames(刷新后从后端重建帧列表)
        ├── preview-audio.js            # PreviewAudioSave 底部保存按钮 + 内置播放器
        ├── audio-trim.js               # FallingTSAudioTrim 波形+播放器+截段/完成按钮+段列表(刷新后从后端重建)
        ├── proceed.js                  # 继续节点前端 (节点缓存 + partial execution)
        ├── route.js                    # total组路由节点: total 动态端口 + 假分支真正执行
        ├── fanout.js                  # 扇出选择(多对一镜像): total=组数=输入端口数(input_i 每组一个) + 输出=组数×组名数(标签=组名) + 选中项下拉选项联动(槽类型 STRING,INT: 可连线接多对一 选中项组名/索引, 索引直接选中所属索引组名) + 选中组分支真正执行 + 旧版 value 遗留输入槽加载时自动清理
        ├── selector.js                 # 多对一选择: items 展开输入端口 + 下拉联动
        ├── switch.js                   # 分组开关前端联动
        ├── composite.js                # 多图合成: total 决定左侧图端口 image1..imageN + 节点内 label1..labelN 标注表单文本框 (按 total 自动扩充) + 旧版 7 槽 / 中间版 12 槽 widgets_values 加载时自动迁移
        ├── table_lookup.js             # 通用表格 Excel 式控件
        └── workflow_reload_button.js   # 刷新工作流按钮
```

## 节点一览

| 包 | 节点 | 说明 |
|------|------|------|
| proceed | FallingTSContinue | 继续节点 (分段执行控制: any 输入 lazy + 节点缓存 + partial execution; 未放行时拉上游填缓存并阻塞下游, 点「继续」放行后上游不再重跑、用缓存继续下游。2030-场景旋镜 接在合成与合成预览之间: #1 原视角→73.image1, 58/59/60(右面/后面/左面 PreviewImageSave, 扇出三角度输出)→73.image2/3/4 实时直连(无需 LoadImage 加载已存图), 73→76.any→74(合成预览保存), 73/74 常开; 全量 Run 跑生成段+合成段(76 缓存合成结果+阻塞保存), 点 76「继续」只跑保存段, 不重跑生成与合成) |
| route | FallingTSRoute | 路由节点 (total组路由, 参考分组开关: 1个 switch + total 组数, 每组 = 为假时_i/为真时_i 输入 + 输出_i) |
| fanout | FallingTSFanout | 扇出选择 (多对一的镜像: items 逗号分隔组名(与多对一同源), total 组数(最少 1, 最多 50) = 左侧输入端口数(每组一个 input_i), 右侧输出 = 组数 × 组名数量(每组每个组名一个, 标签=组名), selection 选中项(下拉框, 选项=组名, 可连线直接接多对一 选中项组名/索引, 索引直接选中所属索引组名)选中第 k 个组名 → 每组 input_i 路由到该组该组名对应的输出, 第 i 组其余输出 None; partial 提交时每组选中组名输出下游输出节点真正执行; 提交时按 partial_execution_targets 拦截未选中分支: partial 提交剔除未选中组名槽位下游输出节点, 全量 Run(图无继续节点)显式列「全部输出节点-未选中分支下游输出节点」提交, 未选中分支下游根本不执行(selection 连线时值运行时才定, 不拦截, 靠下游 None 容忍兜底)) |
| selector | FallingTSSelector | 多对一选择 (多组切换, 通用 ANY: items 逗号分隔组名, total 组数(最少 1), 左侧输入 = 组数 × 组名数量(第1组在前第2组在后), 下拉选一个组名, 右侧各组 选中值 输出各自该组名的输入, 顶部固定 选中项/索引) |
| table | FallingTSTable | 通用表格 (Excel 式; rows=None 如未连接 → 输出本节点最近一次输出行(sticky), 从未输出则回退默认表) |
| switch | FallingTSSwitch | 分组开关 (total组) |
| mdtable | FallingTSMarkDownTable | MarkDown 数据表 (data=None 如未连接 → 输出本节点最近一次输出(sticky), 从未输出则回退默认状态) |
| fps | FallingTSFrameRateConvert | 帧率转换 (图像序列按目标帧率抽帧: 步长 = max(1, round(source_fps/target_fps)), 每 stride 帧保留 1 帧, stride=1 原样透传; 目标帧率未连接/None 时原样透传不抽帧; **images=None → 输出本节点最近一次抽帧结果(sticky), 从未处理则透传 None**; 音频不动, 配合 CreateVideo 的 fps 参数输出) |
| composite | FallingTSImageComposite | 多图合成 (total 驱动: total 最少 1 不设上限 默认 4 (端口口径 64), 左侧只有 image1..imageN 图端口, 标注是节点内 label1..labelN 表单文本框 (按 total 自动扩充), **前端按 total 动态增删 image_i 图端口、扩充 label_i 标注表单文本框 (未启用的图端口/文本框不进提交载荷)**, 与 switch/route/fanout/selector 同套机制; 图 image1..64 (optional, 未连接/None = 该格用底色空白占位, **total 图全空 → 输出本节点最近一次合成结果(sticky), 从未合成则输出 None**) + label1..64 (节点内表单文本框, widget 默认空串 = 不画, 值为 None 时才回退默认标注 前面/右面/后面/左面/上面/下面/近处/远处); 网格列数 = ceil(sqrt(total)) 行优先填充 (total=4 → 2×2, 与旧版布局一致), 统一尺寸 (取最大高宽), 每张子图左上角 CJK 白字黑描边标注, 合成单张图; 字号/间距/底色 None=默认 8/6/#000000, 底色非法值回退黑色) |
| preview-image | PreviewImageSave | 图片预览保存 (始终预览 temp, 点「保存」才写 output 同名覆盖无序号; images=None 如扇出未选中分支 → 回放上次预览 + **输出该节点最近一次预览的图**(sticky)供下游合成, 从未预览则输出 None) |
| preview-video | PreviewVideo | 视频预览保存 (video=None 如扇出未选中分支 → 回放上次预览 + **输出该节点最近一次预览的视频**(sticky), 从未预览则输出 None) |
| preview-audio | PreviewAudioSave | 音频预览保存 (纯预览与保存, 不切段; audio=None 如扇出未选中分支 → 回放上次预览 + **输出该节点最近一次预览的音频**(sticky), 从未预览则输出 None; 切段已拆到 audio-trim) |
| audio-trim | FallingTSAudioTrim | 音频截段 (节点内波形拖两侧把手选区 → 点「截段」累积多段 → 点「完成」按段输出 audio_1..audio_N; 未「完成」时用 ExecutionBlocker 阻断下游, 只发预览事件供试听与切段; 同样带「保存」与内置播放器; 输出 1 + 64 槽) |
| video-components | FallingTSVideoComponents | 视频拆解 (参考视频 → 帧序列/音频/帧率/位深/色彩空间, **None 安全替代核心 GetVideoComponents**: 核心节点的 `video` 是 required 且 execute 内直接调 `video.get_components()`, 收到 None 抛 `AttributeError: 'NoneType' object has no attribute 'get_components'`; 本节点 `video` 为 **optional**, None (mdtable 空 `<Video N>` 字段 / 上游无值) 时**全部输出 None 且不报错**, 下游 H3 Ref2VA 的 `ref_video_N` 是可选输入, None 被其内部 `if video_frames is None: continue` 安全跳过; **不做 sticky 回放** —— None 在此表示"该行没有视频参考", 回放上一次的视频会让生成张冠李戴。3020-参考场景 / 4030-参考视频 各 3 处已换用) |
| h3-guide | FallingTSH3AddGuide | H3 引导锚定 (**None 安全替代核心 MiniMaxH3AddGuide**: 核心节点在 image 与 audio 同为 None 时直接抛 `ValueError("MiniMaxH3AddGuide needs an image or an audio to anchor")`, 而 mdtable 空列按"可选输入惯例"输出 None、`execution.py` 又把上游 None 原样传给下游(`input_data_all[x] = obj`, 不走 `mark_missing`), 于是 N 路引导串联时只要有一列留空就整图失败; 本节点空输入时**原样透传 positive**(等价于该列无锚点), 有值时**直接委派 `MiniMaxH3AddGuide.execute`** 不复制其实现 —— 锚定语义与官方完全一致。4025-关键帧视频 的 9 路引导链已换用, 尾部关键帧列因此可留空; **并带同帧去重** —— 4025 的帧索引由每列右侧的 `关键帧n所在秒数` 逐列换算 (`max(0, min(round(秒数 x 24), length - 1))`), 两列秒数相同或换算后落在同一帧时会被夹到同一帧, 本节点发现本次图片锚点与上游某列撞帧时**撤掉本次图片锚点并告警**(仅撤图片 `latent`, 同帧音频锚点保留), 避免同一时刻钉上两个互相矛盾的画面致物件漂移) |

注:`preview-image` / `preview-video` / `preview-audio` / `audio-trim` 目录名含连字符,不能直接 `from xxx import`,入口经 `importlib` 按名加载。

### None 容忍约定(全部 15 节点)

所有节点的 `execute` 输入均为 **None 容忍**:可选输入未连接时 ComfyUI 引擎不传该参数(靠函数默认值兜底),传参为 None 时走安全回退,**绝不崩溃**。

**核心约定 —— 数据类节点「None → 回放 + 输出 last 数据」(sticky)**:数据类节点收到 None(未连接/上游无值/扇出未选中分支)时**不报错**,先查本节点是否缓存了 **last 数据**(最近一次处理/预览的有效输出):**有 → 输出该 last 数据**(下游不丢数据, 如四图合成未选中面拿到该面「之前预览过」的图);**无 → 透传 None**(或回退默认表/默认状态, 下游按无值处理)。实现:V1 节点声明 `"hidden": {"id": "UNIQUE_ID"}` + `execute(..., id=None)`, 用模块级 `_last_output: dict[str, ...]`(键 `str(id)`)缓存最近一次**有效输出**;V3 节点用 `cls.hidden.unique_id` + 已有 `_last_output` 缓存, 仅把 None 分支的返回值从 `None` 改为 last 数据。

要点:

- **控制/路由类**(route/switch/fanout/selector)——**保持纯路由, 不做 None→last**:`_split_items`/`_clamp_total`/`_resolve_index` 等助手对 None items/total/selection 回退默认(1 组、第 0 项);未选中分支**输出 None**(由下游数据类节点用 sticky 兜底),选中分支输出真实值。这是路由的语义(未选中 = 无值),不缓存、不透传 last;
- **数据类 —— 预览**(preview-image/preview-video/preview-audio):media 为 None → 回放 `_last_output` 上次预览事件(保持原预览不清空, 不更新「保存」缓存) + **输出该节点最近一次预览的媒体**(preview-image 重组为 BxHxWxC 批张量; video/audio 直接输出缓存对象),让下游(如四图合成)拿到该面「之前预览过」的媒体;从未预览过则输出 None。**绝不透传空 tuple `()`**(会被下游当合法值走 `.shape`/迭代而崩溃);
- **数据类 —— 音频截段**(audio-trim):`audio` 为 None → 若有缓存则按已缓存段输出, 否则输出全 None; 未点「完成」时用 `ExecutionBlocker` 阻断全部下游(切段节点自身仍执行并发预览事件), 点「完成」后输出整段 + 各段;
- **数据类 —— 帧率**(fps):images 为 None → 输出本节点最近一次抽帧结果(sticky),从未处理则透传 None;source_fps/target_fps 任一 None 时无法算帧率比,按原样透传(stride=1);
- **数据类 —— 视频拆解**(video-components):`video` 为 optional,None 时**全部输出 None**(images/audio/fps/bit_depth/color_space),不报错;此处**故意不做 sticky** —— 与其它数据类节点相反,因为 None 表示"该行没有视频参考"(mdtable 空 `<Video N>` 字段),回放上一次的视频会让生成的参考张冠李戴;下游 Ref2VA 的可选 `ref_video_N` 收到 None 即按无参考跳过, 输出 None 不构成"丢数据";
- **数据类 —— H3 引导锚定**(h3-guide):`image` 与 `audio` 同为 None 时**原样透传 `positive`**, 等价于"该列没有锚点";有值时直接委派核心 `MiniMaxH3AddGuide.execute`, 不复制其实现。此处**不能沿用 sticky 回放** —— 回放上一次的图会把该列的锚点钉到错误画面上;另有**同帧去重**:委派核心后比对本次新增图片锚点与上游各列的 `resolved_frame_index`(帧号取核心算好的值, 不重复其帧数换算), 撞帧则撤掉本次图片锚点(仅撤 `latent`, 同帧音频锚点保留)并 `logging.warning` 告警 —— 只有本节点能看到整条链累积的 `minimax_keyframes`, 故去重只能在这一层做;
- **数据类 —— 合成**(composite):total 驱动张数(None → 默认 4, clamp 1..64);image1..64 全部 optional,经 `_first_frame` 统一归一化:None / 空 tuple / list / 零批张量 / 非张量 一律按无值处理 → **该格用底色空白占位**(部分有值时正常合成, 缺格用底色占位);**total 张图全无值 → 输出本节点最近一次合成结果(sticky), 从未合成则输出 None**(绝不崩溃);label1..64 (节点内表单文本框, 空串 = 不画; None → 各自默认标注);font_size/padding/background_color None → 默认 8.0/6/#000000;
- **数据类 —— 表格**(table/mdtable):rows/data 为 None → 输出本节点最近一次输出(sticky),从未输出则回退默认表/默认状态;`normalize_table`/`normalize_state` 对 None 回退空表不报错。mdtable 有 `IS_CHANGED(cls, data, **kwargs)` classmethod —— 加隐藏 `id` 输入后引擎会向 `IS_CHANGED` 传入 `id`, 故签名须含 `**kwargs` 吸收(否则崩);
- **继续类**(proceed):`any` 为 None(未拉取上游)时**不清 `_data_cache`**、不覆盖 `widgets_values`/`proceedState` 等节点数据——None 只表示"本次没有数据",不等于"清空"。`IS_CHANGED` 含 `_reset_generation`(每次 `/proceed/reset` 递增)+ 是否已放行 → 每次 Run 后继续节点必重新执行(重拉上游填 `_data_cache`),不被 ComfyUI 全局执行缓存跳过(否则同进程重跑同图时「继续」400「没有上游数据」)。

### 前端状态与后端同步约定(全部 15 节点)

**核心原则: 后端是唯一事实来源。前端页面加载/刷新后一律"从后端读回并重建", 绝不在加载时清后端状态。**

#### 三类状态, 生命周期各不相同

| 类别 | 存在哪 | 例子 | 页面刷新 | 默认 Run(`/reset`) |
|------|--------|------|----------|--------------------|
| **媒体态** | `_last_output[nid]` | `audio` / `video` / `images` | **保留**(否则「保存」按钮没数据) | 保留(重新执行会覆盖) |
| **界面态** | `_last_output[nid]` + 前端 widget state | `segments`(截段列表) / `selected_frames`(截帧列表) | **保留**, 前端读回重建 | 清 |
| **执行态** | 模块级集合/计数 | `_done` / `_released` / `_data_cache` / `_reset_generation` | 保留 | 清 + 递增代际 |

#### 前端(`web/js/*.js`)要求

- **`setup()` 不得 POST `/clear` 之类的清状态端点** —— 那会让刷新丢掉上一次的结果;
- **媒体预览一律用「拉模式」, 不依赖 `UI.Preview*` 事件** —— 原生 `UI.PreviewImage` / `UI.PreviewVideo` / `UI.PreviewAudio` 是**一次性 WebSocket 事件**, 页面刷新后不会重发, 依赖它的节点预览区就空了。四个预览节点因此都: ① 后端提供 `GET /xxx-url/{id}` 返回 `/view` URL(复用 execute 时的缓存, 不重新编码); ② 前端在 `onConfigure` 拉 URL 填到节点上 —— **优先填 ComfyUI 渲染的原生 `<img>`/`<video>`, 找不到才显示自备的备用元素**(备用默认 `display:none`, 避免出现两个播放器):
  - `preview-image` → `GET /preview-image/image-url/{id}` → `restoreImages()`
  - `preview-video` → `GET /preview-video/video-url/{id}` → `restoreVideo()`
  - `preview-audio` → `GET /preview-audio/audio-url/{id}` → `refreshPlayer()`
  - `audio-trim` → `GET /audio-trim/audio-url/{id}` → `refreshWaveform()` 内一并设置
- 在 `onConfigure`(工作流加载完成)末尾调用"读回重建":
  - `audio-trim` → `refreshWaveform()`:GET `/audio-trim/waveform/{id}` 一次拿回 peaks + segments;
  - `preview-video` → `restoreFrames()`:GET `/preview-video/state/{id}` 拿帧号, 再逐个 POST `/preview-video/frame/{id}`(`append=false`)取 PNG 转 blob URL;
- 界面态同步要**双向且含空值**: `Array.isArray(data.segments)` 为真就写回(即便是空数组), 否则删光段后刷新会残留旧列表。

#### 后端(`nodes.py`)要求

- `/xxx/clear` 端点若因兼容保留, 必须 **no-op**(只回 ok), 不得清 `_last_output` 或任何界面态字段;
- `/xxx/reset` 只在**默认 Run** 分支被调(前端包装 `app.queuePrompt`, 判断 `queueNodeIds` 为空), 清执行态 + 递增 `_reset_generation`;
- **绝不写 `_last_output.clear()`** —— 那会把媒体态一起清掉。

#### 为什么必须有 `_reset_generation`

ComfyUI 在服务端缓存每个节点的输出(`caches.outputs`), 同进程内重跑同一张图时节点会被**直接跳过**。递增 `_reset_generation` → `fingerprint_inputs` 返回值变化 → ComfyUI 认为节点"变了" → 强制执行。`proceed` / `preview-video` / `audio-trim` / `preview-audio` 都用这一招(否则改了段/帧再 Run 会拿到旧结果, 或「继续」报 400「没有上游数据」)。

#### 反面教材(均已修)

- `preview-audio` 的 `_handle_clear` 曾写成 `_last_output.clear()` —— 刷新即清空音频缓存,「保存」与播放器都没数据; 更糟的是 ComfyUI 执行缓存还在, 导致全量 Run 时该节点被跳过、缓存再也填不回来;
- `preview-video` / `audio-trim` 曾在 `setup()` POST `/clear` 清界面态 —— 刷新丢掉上一次的截帧/截段结果。

### 分段执行约定(lazy 门控 + partial 提交)

「先跑到本节点停住 → 点按钮只跑下游」这套机制(**preview-video 的截帧/audio-trim 的截段/proceed 的继续**)由两半组成, **缺一不可**:

**① lazy 门控(后端) —— 决定"上游跑不跑"**

- **输入必须显式声明 `lazy=True`**(V3: `IO.Audio.Input("audio", lazy=True, ...)`), 否则引擎不会调用节点的 `check_lazy_status`, 写了也等于没写 —— 每次都照常拉上游;
- `check_lazy_status` 返回需要拉取的上游输入名: **已放行(完成/继续)→ `[]` 不拉**; 未放行 → `["audio"]` 拉上游更新缓存;
- 用 `MISSING = object()` 哨兵区分"该输入没连线"(`MISSING`)与"连了线但上游未求值"(`None`);
- `execute` 里 `audio is None`(lazy 未拉上游)时**用 `_last_output` 缓存继续**; 未放行则返回 `ExecutionBlocker(None)` 阻断全部下游。
- **对照**: `preview-video` 的 `IO.Video.Input("video", lazy=True, ...)` 是正确样板; `audio-trim` 曾经漏掉 `lazy=True`, 表现为「点完成仍重新加载模型、耗时 90s+」。

**② partial 提交(前端) —— 决定"下游跑哪些"**

- 提交**完整图**(不裁剪 `prompt.output`), 另带 `partial_execution_targets` = 本节点下游的输出节点 id 列表;
- ComfyUI 的 `validate_prompt` 只把 targets 里的 output node 纳入执行(`execution.py`), 上游是否执行由 ① 的 lazy 边界决定;
- **不要按 targets 反推依赖闭包去裁剪 prompt** —— 多余且会掩盖问题(曾因此误判"partial 已生效");
- 第三参数是**选项对象**: `fetchApi("/prompt", {body: JSON.stringify({prompt, partial_execution_targets})})`。注意 `api.queuePrompt(index, prompt, options)` 的第 3 参是 `{partialExecutionTargets}`, 传裸数组会被静默忽略、退化成全量提交。

## 软链接映射

| 路径 | 类型 | 相对目标 | 实际指向 |
|------|------|------|------|
| `.claude` | SymbolicLink(目录级) | `.agents` | 根 `.agents`(智能体配置目录,Claude Code 兼容垫片,2026-08-13 建) |

## 项目规则 (`.agents/rules/`)

> `.claude` 是指向 `.agents` 的相对符号链接;Claude Code 经 `.claude/rules/` 读取的规则,实际存放在 `.agents/rules/`。

| 规则文件 | 说明 |
|---------|------|
| [.agents/rules/project.md](.agents/rules/project.md) | 项目开发规范: API 使用, 节点开发, 错误处理, 异步执行 |

## 开发与提交约定

- 节点注册:V1 `NODE_CLASS_MAPPINGS` + `NODE_DISPLAY_NAME_MAPPINGS`;V3 `IO.ComfyNode` 走 `DesktopPluginsExtension` 扩展注册
- 改代码后重启 ComfyUI 生效(插件经软链接即时加载,无需复制文件)
- git 提交:严格 `git add .` → `commit` → `push`
