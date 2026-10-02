# ComfyUI-FallingTS

我的 ComfyUI 自定义节点插件:通用工具节点集(Continue/Route/Selector/Table/Switch/MarkDown 数据表/多图合成)+ 媒体预览保存节点(图片/视频/音频)+ 前端增强。位于 `custom_nodes\ComfyUI-FallingTS`,经根 `custom_nodes` 目录级软链接被 ComfyUI 加载。

## 项目目录结构

```
ComfyUI-FallingTS/
├── plugin.py                   # 插件入口:V1 节点注册表 (NODE_CLASS_MAPPINGS, 19 节点) + V3 ComfyExtension (DesktopPluginsExtension)
├── __init__.py                 # 包初始化
├── numbered_subdirs.py         # 让文件列表/LoadImage 下拉/预览取到"数字开头子目录"里的文件
├── output_subdir.py            # 产物子目录名解析: 优先用工作流的 md 表文件名, 没有 md 表才用工作流名
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
├── load-image/
│   └── nodes.py                # FallingTSLoadImageNode 加载图像 (来自输出): 内置 LoadImageOutput 的超集 —— ① 下拉候选改由自身路由 GET /fallingts_load_image/files 提供(output 根 + **数字目录(^\d+_)内部整棵子树的图片**, 值形如 0010_灰度遮罩/00001_手部.png, 不带 " [output]" 标注, 由 load_image 的 default_dir=output 定位; 内置 /internal/files/output 只列一层 ⇒ 本机下拉基本为空); ② 「名称」输入框排在 image 下拉之前(刷新按钮由 remote 组件在 combo 之后追加 ⇒ 名称框在其上方), 遮罩保存时带给 POST /fallingts_mask/rename, 成品 0010_灰度遮罩/0000N_名称.png; ③ remote **不设 control_after_refresh** —— 刷新按钮与跑完自动刷新只重新拉候选列表, 不再把已选值换成候选首项(内置 LoadImageOutput 设 "first", 而候选按 mtime 倒序 ⇒ 刚保存的产物必然夺走选中权); 首次加载时上游 onFirstLoad 仍会无条件改值, 由前端 web/js/load_image.js 短守护恢复成存档值; ④ 「序列号」+「刷新序列号」按钮(与「加载视频」同一套: output/<当前工作流名目录> 里已有 "数字_" 命名**文件**的最大编号 + 1, 编号口径与目录解析都取自 output_subdir; 路由 GET /fallingts_load_image/next_sequence) —— 排在 image **之后**并声明为 **optional**: 位置不能提前(V1 节点按 widgets_values 的**下标**恢复旧工作流, 插在中间会让老工作流的 image 值整体错位), optional 则保证无头 API 不带该输入也能跑; ⑤ INPUT_TYPES 里**现扫**一份 options(每次 /object_info 都重扫) ⇒ 页面加载/新建节点时候选已是含子目录的完整列表(与 V3 的 define_schema 同口径)
├── load-video/
│   └── nodes.py                # FallingTSLoadVideoNode 加载视频 (来自输出 + 截帧): 内置 LoadVideo 的超集 —— ⓪ **prefix 输出**(输出 2, 位于 audio 之后、选中帧之前): \`<序列号>_<名称>\` 接各预览保存节点的 filename_prefix, 且不受「完成」门控; ① 下拉候选由自身路由 GET /fallingts_load_video/files 提供(output 根 + **数字目录(^\d+_)内部整棵子树的视频**, 值形如 0035_场景截帧/00001_书房旋镜视频.mp4, 不带 " [output]" 标注, 由 get_annotated_filepath(default_dir=output) 定位), remote **不设 control_after_refresh**(刷新只更新候选, 不改写已选值); ② 「序列号」= output/<工作流产物目录>/ 里已有编号最大值 + 1(目录不存在/没有编号文件时为 0, 5 位显示 00000), 可手改, 右侧「刷新序列号」按钮随时重算(int), 保存帧后续到下一个可用号; ③ 「名称」是保存帧的文件名; ④ 「保存帧」把选中帧逐张写成 output/<产物目录>/<序列号>_<名称>.png(撞号顺延, 不覆盖); ⑤ **截帧/完成/选中帧输出自 PreviewVideo 迁移** —— 执行时编码 temp + UI.PreviewVideo + get_components() 拆帧缓存; 未「完成」时 **video 与 image_1..image_N 输出 ExecutionBlocker(None)** 阻断下游(到本节点停下等截帧), 「完成」输出 image_1..image_N; fingerprint_inputs 纳入文件名/mtime/选中帧/完成态/重置代际, 已完成时 execute 直接走缓存不重新解码; ⑥ **audio 输出**(2026-10-02): get_components() 的音轨直出, **不受「完成」门控**(拆音无需截帧)⇒「加载视频 → 音频后处理」这条链未点完成也能跑(端到端实测: 音频有输出、image 被阻断); ⑦ **可选 VIDEO 输入 video_in**: 数据表「原视频」列这类外部来源接这里(下拉是 COMBO, 前端 isValidConnection 实测不允许 VIDEO/STRING 连进 COMBO), 连上就优先用它, 不连则用自身下拉; ⚠️ 与「加载音频」同一个校验坑: 校验阶段 linked 输入实参是 None, 「是否连线」只能靠 `input_types` 形参判断(否则 0050/0051 会以「Invalid video file: 」被整次拦掉); 路由 /fallingts_load_video/{files,next_sequence,frame,frame-remove,done,reset,state,preview-url,save_frames}
├── load-audio/
│   └── nodes.py                # FallingTSLoadAudioNode 加载音频 (来自输出): 内置 LoadAudio 的超集 —— ⓪ **prefix 输出**(输出 1): \`<序列号>_<名称>\` 接各预览保存节点的 filename_prefix(见 output_subdir.sequence_prefix); ① 下拉候选由自身路由 GET /fallingts_load_audio/files 提供(output 根 + **数字目录内部整棵子树的音频**, 值形如 0060_背景音乐/00001_夜雨.mp3, 不带 " [output]" 标注; 内置 LoadAudio 只从 input 目录列一层 ⇒ 本机下拉是空的), remote **不设 control_after_refresh**(刷新只更新候选); ② 「名称」+「序列号」+「刷新序列号」按钮(与加载图像/加载视频同一套: 序列号 = output/<产物目录>/ 里已有编号最大值 + 1, 路由 GET /fallingts_load_audio/next_sequence); ③ **节点内试听**: 声明 `audioUI` (AUDIO_UI) 输入 ⇒ 前端 Comfy.AudioWidget 的 AUDIO_UI 工厂挂上原生 <audio controls> 播放器(页面刷新后按已选值重建), 执行时发 UI.PreviewAudio 让播放器指向本次解码的音频。⚠️ 这个输入**必须自己声明**: 前端 Comfy.UploadAudio 的上传按钮要求节点上存在名为 audioUI 的控件, 缺了会在**创建节点时**抛 TypeError(内置 LoadAudio 由前端按 comfyClass 白名单自动补); 且必须 **optional** —— 该 DOM 控件在前端 serialize=false, 提交 prompt 不带它, 声明成 required 每次 Run 都会报 "Required input is missing: audioUI"。④ **可选 AUDIO 输入 audio_in**(2026-10-02): 给数据表「原声音」列这类外部来源用(下拉是 COMBO, 前端不允许把 AUDIO 连进 COMBO) —— 连上就透传, 不连才读文件; ⑤ ⚠️ **校验阶段连线的输入拿不到值**: execution.py 的 get_input_data 在 execution_list 为空时把 linked 输入标成 missing(实参 None), 所以「是不是连线进来的」**只能靠声明 `input_types` 形参判断**(ComfyUI 会把各连线输入的上游类型传进来) —— 只看 `audio_in is None` 会把"下拉为空 + audio_in 接线"(0070 就是这种)误判成「Invalid audio file: 」而整次拦掉(实测)。⑥ 「保存」**不在本节点**: 写盘仍归 PreviewAudioSave(用户明确要求原预览音频功能不动)
├── world-refine/
│   └── nodes.py                # FallingTSWorldRefinePLYNode (节点 id `WorldRefinePLY`) 世界重建精修 → 落临时 PNG(+可选相机先验 JSON) → 用 HYWM2 隔离环境的解释器跑 `world-refine\refine_0034_gs.py` (504 前馈 + 2% 尺度过滤 + 3DGS 全参数精修[去多视图双重曝光]) → 取回 stdout 的 `[OUT]` 路径交给 PLY 视口。主进程只做编排(**故意不放 comfy-env.toml**, gsplat 只在 hywm2-nodes 里), 图里只有一次前馈不与图内重建抢显存
├── world-panorama/
│   └── nodes.py                # 360° 视频 → 横向展开长图 (`WorldSurroundPanorama`: 按画面位移自适应抽帧步长 + **自适应补密(治不均匀转速: 静止段/甩镜段)** + 一圈闭环吸附(需首末帧几何重合) + ORB/RANSAC 纯偏航单应与重叠区光度一致性定焦距 + 逐像素 winner-take-all(不帧间平均) + 上行=天/自动裁黑边; 近静止直接报错) + 长图 → 视角批与**精确位姿** (`WorldPanoramaViews`: w2c 外参/内参, 外参口径同 HYWM2SamplePanorama; 等距圆柱竖直朝向按世界地图口径修正, 多 v_range/v_center 竖向范围)
├── fonts/
│   └── Alibaba-PuHuiTi-Heavy.ttf  # CJK 字体 (随包, 合成节点标注渲染用)
├── preview-image/
│   ├── __init__.py
│   └── nodes.py                # PreviewImageSaveNode 图片预览保存
├── preview-video/
│   ├── __init__.py
│   └── nodes.py                # PreviewVideoNode 视频预览保存 (只做「预览 + 保存」: 编码 temp + UI.PreviewVideo, 点「保存」写 output; **截帧/完成/选中帧输出已于 2026-10-02 迁到 load-video 的 FallingTSLoadVideo**)
├── preview-audio/
│   ├── __init__.py
│   └── nodes.py                # PreviewAudioSaveNode 音频预览保存 (纯预览 + 「保存」, 不切段)
├── audio-trim/
│   ├── __init__.py
│   └── nodes.py                # FallingTSAudioTrimNode 音频截段 (波形拖选区 → 多段输出 + 保存)
├── mask-rename/
│   └── nodes.py                # 遮罩编辑器文件整理:包装 /upload/image 路由 + POST /fallingts_mask/rename(带 name 时按 0010_灰度遮罩 里已有的 5 位编号自增 → 0000N_名称.png, 撞号顺延; 无 name 走旧口径)
├── pre-run/
│   └── nodes.py                # 运行前命令后端: POST /fallingts_prerun/run (工作区根 cwd 执行命令, 空则跳过, 非0/超时即拦截本次提交)
├── auto-unload/
│   └── nodes.py                # 跑完自动卸载模型后端: POST /fallingts_auto_unload/unload (队列为空时逐出全部已加载模型释放显存, 否则跳过; 直调内置按钮同款核心函数, 不用 /free 置旗)
├── dev/                        # **开发/验收工具链**(41 个脚本, 不参与 ComfyUI 加载): 拆解类工作流的生成脚本(`build-decompose-workflows.py`, 幂等: 重建 0050_视频拆帧 / 0051_视频拆音 / 0070_截取声音(三者不再要 md 数据表, 文件名前缀取自加载节点的 prefix 输出)+ 清空 0040..0044 的 PreviewVideo 尾部 + 0035 端口与前缀归一, 自带布局六规范自检)与它们的验收(`_verify-005x-decompose.py` / `_verify-0070-trim-audio.py`, 需临时实例跑在 8189)、加载音频节点的后端/浏览器验收(`_verify-load-audio.py` / `_verify-load-audio-ui.py`, 同上)、**离线单测** `_unit-validate-inputs.py`(校验 "连线输入的实参是 None" 这个坑, 不需要起服务)、 0034 世界模型的生成/验收、world-panorama 展开的合成真值/转速谱系/方位对拍/布局校验、运行前命令的离线与浏览器自检、跑完自动卸载的离线自检、加载图像与遮罩编号自检(`_verify-load-image.py` / `_verify-load-image-ui.py`)、两个加载节点的下拉候选/序列号浏览器验收(`_verify-load-dropdown.py`), 下拉弹窗增强(抹掉 ` [output]` 标注 + 「排序方式」左侧的刷新按钮)的浏览器验收(`_verify-combo-menu.py`, 传 `custom_nodes\ComfyUI-FallingTS\dev\_verify-combo-menu.py` 跑)。**根仓库 `scripts\` 只放临时文件(随时可清空), 凡"随时要能复跑"的脚本一律放这里**; 脚本一律按工作区根相对路径跑(如 `.venv\Scripts\python.exe custom_nodes\ComfyUI-FallingTS\dev\_verify-0034-360.py`), 内部用 `Path(__file__).resolve().parent.parent.parent.parent` 反推工作区根。⚠️ 插件的**运行期**硬依赖不放这里 —— 精修脚本 `refine_0034_gs.py` 放在用它的节点旁边(`world-refine\`)
└── web/
    ├── js/                     # 前端扩展脚本 (经 GET /extensions 加载,不参与前端打包)
        ├── assets_tab_rename.js        # 「已导入」→「已保存」(左侧媒体资产面板 + 节点下拉弹窗的分类按钮)。⚠️ 1.52.7 的 `globalProperties.$i18n` 是 **null-prototype 普通对象**(无 `t`/`mergeLocaleMessage`) ⇒ i18n 合并不可用, 只能靠 `MutationObserver`+`TreeWalker` 做 DOM 文本兜底(弹窗是 body 下的 portal, 属新增子树)
        ├── load_combo_menu.js           # 两个加载节点共用: 下拉弹窗增强 —— ① 抹掉选项末尾的 " [output]"/" [input]" 标注(前端给 output 资产项硬编码拼的来源后缀, 而本工作区 input/output 是同一物理目录的软链 ⇒ 列表里既有带标注的资产项又有不带标注的 remote 候选项, 又重复又乱; 本模块改弹窗 DOM 的文本节点, 并给 widget.value 装访问器式清洗 ⇒ 点到资产项时落到节点/提交给后端的也是纯文件名); ② 在弹窗工具条「排序方式」左侧插一个「刷新」按钮, 点一下调 widget.refresh() 重扫 output(含数字目录子树), 刷新后按 Escape 关掉弹窗再自动点开一次 —— 弹窗的候选列表是"打开时算一次"的(WidgetSelectDropdown 读普通对象 widget.options.values, 非 Vue 响应式, 换了数组也不重算), 不重开就永远停在旧列表; 只对登记过的 widget 生效(armComboMenu), 识别"弹窗属于哪个 combo"走两条路: Vue 节点的 combo 按钮文本 == 当前值(capture 阶段 click), 画布模式读 app.canvas.node_widget
        ├── mask-rename.js              # PreviewImageSave / FallingTSLoadImage 遮罩编辑器保存联动(后者带上它的「名称」输入框, 后端按 0010_灰度遮罩 自增编号命名成品)
        ├── load_combo_refresh.js        # 两个加载节点共用: combo 候选"点开即最新" —— 前端只在 ① NodeDef 注册 ② 点 refresh 按钮 ③ 跑完流程的 Auto-refresh 这三个时机拉候选, **"点开下拉"这一下不拉**(弹窗的 handleIsOpenUpdate 只刷新「已保存」那份资产列表), 于是新出现的子目录/文件必须手动点一次刷新才进列表(用户反馈的"第一次点开不显示子目录资源"); 本模块补上 节点创建后 / 在节点上按下鼠标 / 每 4 秒(页面可见时) 三个时机调 widget.refresh()。前提: remote 不设 control_after_refresh ⇒ 刷新只换候选、绝不改写已选值
        ├── load_image.js               # FallingTSLoadImage: 序列号(后端 /fallingts_load_image/next_sequence 按当前工作流名解析目录) + 「刷新序列号」按钮(两拍重排到 remote 追加的 Auto-refresh/refresh/upload 之后) + armComboRefresh(node,"image") + 短守护 —— 刷新改值已由后端不设 control_after_refresh 根治; 上游 onFirstLoad 在节点首次加载时仍会无条件把 image 值设成候选首项(候选按 mtime 倒序), 本扩展在 onConfigure 后 4 秒内只在"值被换成候选首项"时恢复成工作流存的值
        ├── md_table.js                 # MarkDown 数据表前端 (选文件/内嵌表格弹窗)
        ├── media_lightbox_zoom.js      # 全屏预览缩放 (滚轮/拖拽/双击/快捷键)
        ├── node_image_middleclick.js   # 节点中键 → 全屏大图预览
        ├── preview-image.js            # PreviewImageSave 底部控件 + 保存按钮
        ├── preview-video.js            # PreviewVideo 底部保存按钮 + 备用播放器/restoreVideo(刷新后从后端重建预览)
        ├── load_video.js               # FallingTSLoadVideo: 序列号(自动取产物目录最大编号 + 1 / 刷新按钮重算) + 截帧/完成(partial 只跑下游) + 保存帧(<序列号>_<名称>.png) + 选中帧列表 + 备用播放器/restoreVideo —— 自 preview-video.js 迁移。输出端口布局 = **video(0) + audio(1) + prefix(2) + image_1..N(从 3 起)**: syncFrameState 的 startIdx=3, 并把老存档里占着端口 1/2 的旧 image_1/image_2 就地纠正成 audio/prefix —— ⚠️ prefix 必须排在选中帧**之前**, 因为 syncFrameState 会把无链接的**尾部**端口裁到「3 + 输出帧数」
        ├── load_audio.js               # FallingTSLoadAudio: 序列号(自动取产物目录最大编号 + 1 / 刷新按钮重算, 带代际闸门防"在途刷新覆盖存档值") + 「刷新序列号」按钮 + armComboRefresh(node,"audio") + armComboMenu(node,"audio") + 短守护(onFirstLoad 把 audio 值换候选首项时恢复存档值)。**不含「保存」**(写盘仍归 PreviewAudioSave); 节点内试听播放器由前端 AUDIO_UI 控件提供(后端声明的 audioUI 输入), 故本文件不建播放器
        ├── preview-audio.js            # PreviewAudioSave 底部保存按钮 + 内置播放器
        ├── audio-trim.js               # FallingTSAudioTrim 波形+播放器+截段/完成按钮+段列表(刷新后从后端重建)
        ├── proceed.js                  # 继续节点前端 (节点缓存 + partial execution)
        ├── route.js                    # total组路由节点: total 动态端口 + 假分支真正执行
        ├── fanout.js                  # 扇出选择(多对一镜像): total=组数=输入端口数(input_i 每组一个) + 输出=组数×组名数(标签=组名) + 选中项下拉选项联动(槽类型 STRING,INT: 可连线接多对一 选中项组名/索引, 索引直接选中所属索引组名) + 选中组分支真正执行 + 旧版 value 遗留输入槽加载时自动清理
        ├── selector.js                 # 多对一选择: items 展开输入端口 + 下拉联动
        ├── switch.js                   # 分组开关前端联动
        ├── composite.js                # 多图合成: total 决定左侧图端口 image1..imageN + 节点内 label1..labelN 标注表单文本框 (按 total 自动扩充) + 旧版 7 槽 / 中间版 12 槽 widgets_values 加载时自动迁移
        ├── table_lookup.js             # 通用表格 Excel 式控件
        ├── no_auto_workflow.js         # 真正"不打开任何工作流": 关掉最后一个不再残留未保存工作流 + 启动不自动打开
        ├── pre_run_command.js          # 运行前命令: 系统设置「其它」里的输入框 + 包装 queuePrompt(默认 Run 前先执行, 非0/超时即取消本次运行)
        ├── auto_unload.js              # 跑完自动卸载模型: 系统设置「其它」里的开关 + execution_success 后触发后端卸载(队列非空后端自跳过)
        └── workflow_reload_button.js   # 刷新工作流按钮
    └── viewer/                 # 独立三维场景查看页(静态 HTML,不经前端打包): 取 /history 里的 GLB 网格 → three.js + 指针锁定第一人称漫游
        ├── scene-walk.html
        └── vendor/             # three.js 与 GLTFLoader / BufferGeometryUtils / PointerLockControls 的 .mjs 副本(各自保留 MIT 许可证头)
```

## 节点一览

| 包 | 节点 | 说明 |
|------|------|------|
| proceed | FallingTSContinue | 继续节点 (分段执行控制: any 输入 lazy + 节点缓存 + partial execution; 未放行时拉上游填缓存并阻塞下游, 点「继续」放行后上游不再重跑、用缓存继续下游。2030-场景旋镜 接在合成与合成预览之间: #1 原视角→73.image1, 58/59/60(右面/后面/左面 PreviewImageSave, 扇出三角度输出)→73.image2/3/4 实时直连(无需 LoadImage 加载已存图), 73→76.any→74(合成预览保存), 73/74 常开; 全量 Run 跑生成段+合成段(76 缓存合成结果+阻塞保存), 点 76「继续」只跑保存段, 不重跑生成与合成)。⚠️ **继续节点的下游若还要用到上游那张图, 必须从继续节点的输出接, 不能从继续节点上游的节点直接接**: partial 提交只把继续节点的**下游**输出节点纳入执行, 从上游直接接会让 ImageCompare / 合成这类节点把整条上游链重新拉回来重跑(主生成段白跑, 分段执行失去意义); 从继续节点接则走它的 `_data_cache`, 上游不重跑。实测 2026-09-22: `00110_万物建模2.1` / `00200_场景首帧2.1` 的 `ImageCompare.image_a` 原本直连「主结果 保存/预览」(继续节点上游), 已改为接继续节点输出 —— 对照原版 `0011_万物建模` / `0020_场景首帧` / `0021_场景拉镜` 三处, 一直是正确接法) |
| route | FallingTSRoute | 路由节点 (total组路由, 参考分组开关: 1个 switch + total 组数, 每组 = 为假时_i/为真时_i 输入 + 输出_i) |
| fanout | FallingTSFanout | 扇出选择 (多对一的镜像: items 逗号分隔组名(与多对一同源), total 组数(最少 1, 最多 50) = 左侧输入端口数(每组一个 input_i), 右侧输出 = 组数 × 组名数量(每组每个组名一个, 标签=组名), selection 选中项(下拉框, 选项=组名, 可连线直接接多对一 选中项组名/索引, 索引直接选中所属索引组名)选中第 k 个组名 → 每组 input_i 路由到该组该组名对应的输出, 第 i 组其余输出 None; partial 提交时每组选中组名输出下游输出节点真正执行; 提交时按 partial_execution_targets 拦截未选中分支: partial 提交剔除未选中组名槽位下游输出节点, 全量 Run(图无继续节点)显式列「全部输出节点-未选中分支下游输出节点」提交, 未选中分支下游根本不执行(selection 连线时值运行时才定, 不拦截, 靠下游 None 容忍兜底)) |
| selector | FallingTSSelector | 多对一选择 (多组切换, 通用 ANY: items 逗号分隔组名, total 组数(最少 1), 左侧输入 = 组数 × 组名数量(第1组在前第2组在后), 下拉选一个组名, 右侧各组 选中值 输出各自该组名的输入, 顶部固定 选中项/索引) |
| table | FallingTSTable | 通用表格 (Excel 式; rows=None 如未连接 → 输出本节点最近一次输出行(sticky), 从未输出则回退默认表) |
| switch | FallingTSSwitch | 分组开关 (total组)。⚠️ **`total` 必须等于真正接好线的组数**: 第 i 组没连线时 `kwargs.get("false_i")` 取到 None(引擎不传未连接的 optional 输入), 若这一路输出还接着 KSampler 的 `cfg`/`denoise` 这类必填数值, 下游就在 `math.isclose(cond_scale, 1.0)` 处以 `TypeError: must be real number, not NoneType` 崩掉 —— 报错完全看不出是开关的问题。2026-09-22 实测 `00110_万物建模2.1` / `00200_场景首帧2.1` 的「编辑 4步/40步 切换」正是 total=4 而第 4 组(cfg)悬空。**改 total 后逐组确认 `为假时i`/`为真时i` 都已连线**; 只用 3 组就别把 total 留成 4。一次性排查脚本: 根仓库 `scripts\_audit-switch.py` |
| mdtable | FallingTSMarkDownTable | MarkDown 数据表 (data=None 如未连接 → 输出本节点最近一次输出(sticky), 从未输出则回退默认状态) |
| fps | FallingTSFrameRateConvert | 帧率转换 (图像序列按目标帧率抽帧: 步长 = max(1, round(source_fps/target_fps)), 每 stride 帧保留 1 帧, stride=1 原样透传; 目标帧率未连接/None 时原样透传不抽帧; **images=None → 输出本节点最近一次抽帧结果(sticky), 从未处理则透传 None**; 音频不动, 配合 CreateVideo 的 fps 参数输出) |
| composite | FallingTSImageComposite | 多图合成 (total 驱动: total 最少 1 不设上限 默认 4 (端口口径 64), 左侧只有 image1..imageN 图端口, 标注是节点内 label1..labelN 表单文本框 (按 total 自动扩充), **前端按 total 动态增删 image_i 图端口、扩充 label_i 标注表单文本框 (未启用的图端口/文本框不进提交载荷)**, 与 switch/route/fanout/selector 同套机制; 图 image1..64 (optional, 未连接/None = 该格用底色空白占位, **total 图全空 → 输出本节点最近一次合成结果(sticky), 从未合成则输出 None**) + label1..64 (节点内表单文本框, widget 默认空串 = 不画, 值为 None 时才回退默认标注 前面/右面/后面/左面/上面/下面/近处/远处); 网格列数 = ceil(sqrt(total)) 行优先填充 (total=4 → 2×2, 与旧版布局一致), 统一尺寸 (取最大高宽), 每张子图左上角 CJK 白字黑描边标注, 合成单张图; 字号/间距/底色 None=默认 8/6/#000000, 底色非法值回退黑色) |
| load-image | FallingTSLoadImage | 加载图像 (来自输出): 内置 \`LoadImageOutput\` 的超集。① **下拉候选由自身路由 \`GET /fallingts_load_image/files\` 提供** —— 内置 \`/internal/files/output\` 用 \`os.scandir\` 只列 output 根一层, 而本工作区产物全落在数字目录(\`0010_灰度遮罩/\`、\`0011_万物建模/\` …)里 ⇒ 内置节点的下拉在本机基本是空的; 本路由按「媒体资产」侧栏同一口径扫描: output 根图片 + **数字目录(\`^\d+_\`)内部整棵子树的图片**(数字目录外如 \`clipspace/\` 不收, 隐藏文件/非图片不收), 按 mtime 倒序, 值形如 \`0010_灰度遮罩/00001_手部.png\`(**不带 " [output]" 标注** —— 前端给候选算预览图时一律拼 type=input 且不剥离标注, 带标注会让 /api/view 404; 本节点 \`load_image\`/\`IS_CHANGED\`/\`VALIDATE_INPUTS\` 用 \`default_dir=output\` 解析, 带标注的值仍按标注走), 前端 remote 组件直接当 \`widget.options.values\` 用(即弹窗「已导入/已保存」与「全部」两个分类的内容)。② **「名称」输入框排在 image 下拉之前** —— 内置刷新按钮由 remote 组件在 combo 之后 \`addWidget('button','refresh',...)\` 追加, 故名称框天然落在刷新按钮上方; 遮罩编辑器保存时前端把它带给 \`POST /fallingts_mask/rename\`, 成品按 \`0010_灰度遮罩/0000N_名称.png\` 落盘(编号 = 目录里已有 5 位编号最大值 + 1, 撞号顺延到下一个空号); 名称留空则退回旧口径(前端 base > 预览缓存 filename_prefix > \`mask-{ts}\`)。③ \`load_image\` / \`IS_CHANGED\` / \`VALIDATE_INPUTS\` 与内置 \`LoadImage\` 同一实现(视频/动图序列 + PIL 回退), 输出 IMAGE/MASK。④ remote **不设 `control_after_refresh`** —— 刷新按钮与跑完自动刷新只重新拉候选列表, 不再把已选值换成候选首项(内置 `LoadImageOutput` 设 `"first"`, 而候选按 mtime 倒序 ⇒ 刚保存的产物必然夺走选中权); 首次加载时上游 `onFirstLoad` 仍会无条件改值, 由前端 `web/js/load_image.js` 短守护(4s, 只认"被换成候选首项"这一种覆盖)恢复成存档值。⑤ **「序列号」+「刷新序列号」**(2026-10-02 加, 与「加载视频」同一套) —— 编号 = `output/<当前工作流名目录>/` 里已有 `数字_` 命名**文件**的最大编号 + 1(目录不存在/没有编号文件为 0, 显示成 5 位 `00000`), 可手改、按钮随时重算; 目录口径走共用的 `output_subdir`(有 md 数据表用表文件名, 没有才用工作流名), 路由 `GET /fallingts_load_image/next_sequence`。⚠️ 序列号排在 image **之后**且声明为 **optional**: V1 节点按 `widgets_values` 的**下标**恢复旧工作流, 插在中间会让老工作流的 image 值整体错位; optional 保证无头 API 不带该输入也能跑。⑥ **下拉候选在 `INPUT_TYPES` 里也现扫一份 `options`**(每次 `/object_info` 都重扫, 与 V3 的 `define_schema` 同口径) ⇒ 页面加载/新建节点时列表就已完整; 再配合前端 `load_combo_refresh.js`(节点创建 / 按下鼠标 / 每 4 秒 三个时机拉 remote) 彻底消除"第一次点开不显示子目录资源" |
| preview-image | PreviewImageSave | 图片预览保存 (始终预览 temp, 点「保存」才写 output 同名覆盖无序号; images=None 如扇出未选中分支 → 回放上次预览 + **输出该节点最近一次预览的图**(sticky)供下游合成, 从未预览则输出 None) |
| load-video | FallingTSLoadVideo | 加载视频 (来自输出 + 截帧): 内置 `LoadVideo` 的超集。① **下拉候选由自身路由 `GET /fallingts_load_video/files` 提供**(与「加载图像」同口径: output 根视频 + **数字目录内部整棵子树的视频**, 值形如 `0035_场景截帧/00001_书房旋镜视频.mp4`, 不带 " [output]" 标注), remote **不设 control_after_refresh**(刷新/跑完自动刷新只重新拉候选)。② **「序列号」** = output/<产物目录>/ 里已有编号最大值 + 1(目录不存在或没有 `数字_` 命名的文件时为 0, 显示成 5 位 00000), 可手改; **「刷新序列号」按钮**随时重算, 「保存帧」成功后自动续到下一个可用号。③ **「名称」**是保存帧的文件名。④ **「保存帧」**把选中帧逐张写成 `output/<产物目录>/<序列号>_<名称>.png`(编号撞上已有文件时顺延, 不覆盖; 产物目录由 `output_subdir.resolve_subdir` 解析 —— 有 md 数据表用表名, 没有才用工作流名)。⑤ **截帧/完成/选中帧输出自 PreviewVideo 迁移**(2026-10-02): 视频编码 temp + `UI.PreviewVideo` 预览, 同时 `get_components()` 拆出帧集合缓存; 未「完成」时 **video 与** `image_1..image_64` 输出 `ExecutionBlocker(None)` 阻断下游(到本节点停下等截帧), 「完成」按选中帧输出 `image_1..image_64`; `fingerprint_inputs` 纳入文件名 + mtime + 选中帧 + 完成态 + 重置代际(否则被全局执行缓存跳过、下游拿到旧帧), 已完成时 execute 直接取缓存不重新解码视频(partial 提交时本节点会再次执行)。⑥ **加 audio 输出**(2026-10-02): 音轨直出且**不受「完成」门控** —— 拆音不需要截帧, 「加载视频 → 音频截段 → 预览音频」这条链未点「完成」也能跑(端到端实测: 未完成时 audio 有输出、image 被阻断)。⑦ **加可选 VIDEO 输入 video_in**(2026-10-02): 给数据表「原视频」列这类外部来源用 —— 节点自身下拉是 COMBO, 而前端 `isValidConnection` **不允许 VIDEO/STRING 连进 COMBO**(实测为假), 只能另开一个 VIDEO 口; 连上就优先用它, 不连则用下拉。⚠️ 同一处校验坑见「加载音频」: 校验阶段 linked 输入实参是 None, 「是否连线」要用 `input_types` 判断, 否则 0050/0051 会以「Invalid video file: 」被整次拦掉。⑧ 输出 **video(0) + audio(1) + prefix(2) + 64 个选中帧槽(从 3 起)**(前端按「输出帧数」增删端口; prefix 排在选中帧之前, 否则会被 syncFrameState 的尾部裁剪删掉)。⑨ **加 prefix 输出**(2026-10-02): `<序列号>_<名称>`(口径见 `output_subdir.sequence_prefix`), 接各预览保存节点的 `filename_prefix` —— 拆帧/拆音/截取这类工作流因此不再需要 md 数据表提供文件名前缀, 一条线分发给本图所有预览/保存节点(保存节点再用 `filename_suffix` 区分, 如 `00007_书房_首帧.png`); 与 `audio` 一样**不受「完成」门控**(拆音链未截帧时也要能落盘) |
| load-audio | FallingTSLoadAudio | 加载音频 (来自输出): 内置 `LoadAudio` 的超集。① **下拉候选由自身路由 `GET /fallingts_load_audio/files` 提供**(与加载图像/加载视频同口径: output 根音频 + **数字目录内部整棵子树的音频**, 值形如 `0060_背景音乐/00001_夜雨.mp3`, 不带 " [output]" 标注; 内置 LoadAudio 只从 **input** 目录列一层 ⇒ 本机下拉是空的), remote **不设 control_after_refresh**(刷新/跑完自动刷新只重新拉候选)。② **「名称」+「序列号」+「刷新序列号」按钮**(与加载图像/加载视频同一套: 序列号 = output/<产物目录>/ 里已有编号最大值 + 1, 目录口径走共用的 output_subdir, 路由 `GET /fallingts_load_audio/next_sequence`)。③ **节点内试听**(抄「预览音频」的试听体验, 但走前端原生音频控件): 声明 `audioUI`(AUDIO_UI) 输入 ⇒ 前端 Comfy.AudioWidget 的 AUDIO_UI 工厂给节点挂上 `<audio controls>` DOM 播放器, 页面刷新后按已选值重建(不依赖一次性事件); 执行时发 `UI.PreviewAudio` 让播放器指向本次解码出来的音频。⚠️ 这个输入**必须自己声明**且**必须是 optional** —— 前端 Comfy.UploadAudio 的上传按钮要求节点上存在名为 audioUI 的控件(缺了**创建节点时**直接抛 TypeError; 内置 LoadAudio 由前端按 comfyClass 白名单自动补), 而该 DOM 控件 serialize=false、提交 prompt 不带它(声明成 required 会每次 Run 报 "Required input is missing: audioUI")。④ **可选 AUDIO 输入 `audio_in`** —— 数据表「原声音」列这类外部来源接这里(下拉是 COMBO, 连不进 AUDIO): 连上就透传, 不连才读文件。⑤ ⚠️ **校验阶段连线的输入拿不到值**(execution.py 把 linked 输入标成 missing, 实参 None), 所以「是否连线」只能靠声明 `input_types` 形参判断 —— 否则"下拉为空 + audio_in 接线"会被误判成「Invalid audio file: 」整次拦掉(实测)。⑥ **加 prefix 输出**(2026-10-02): 输出 0 = `audio`, 输出 1 = `prefix`(`<序列号>_<名称>`, 口径同「加载视频」), 接各预览保存节点的 `filename_prefix` —— 截取/拆音工作流不再需要 md 数据表供前缀(本节点无动态端口, 加在 audio 之后不影响任何前端逻辑)。⑦ **不包括「保存」** —— 写盘仍归 PreviewAudioSave(原有功能一行未动) |
| preview-video | PreviewVideo | 视频预览保存 (**只做「预览 + 保存」**, 与核心 SaveVideo 的分工一致): 编码 temp + `UI.PreviewVideo` 预览, video=None(扇出未选中分支)→ 回放上次预览并输出缓存视频, 从未预览则输出 None; 点「保存」写 output(`{filename_prefix}{filename_suffix}.mp4`, 同名覆盖无序号)。**截帧/完成/选中帧输出已迁到 `FallingTSLoadVideo`**(2026-10-02), 输出只剩 video |
| preview-audio | PreviewAudioSave | 音频预览保存 (纯预览与保存, 不切段; audio=None 如扇出未选中分支 → 回放上次预览 + **输出该节点最近一次预览的音频**(sticky), 从未预览则输出 None; 切段已拆到 audio-trim) |
| audio-trim | FallingTSAudioTrim | 音频截段 (节点内波形拖两侧把手选区 → 点「截段」累积多段 → 点「完成」按段输出 audio_1..audio_N; 未「完成」时用 ExecutionBlocker 阻断下游, 只发预览事件供试听与切段; 同样带「保存」与内置播放器; 输出 1 + 64 槽) |
| video-components | FallingTSVideoComponents | 视频拆解 (参考视频 → 帧序列/音频/帧率/位深/色彩空间, **None 安全替代核心 GetVideoComponents**: 核心节点的 `video` 是 required 且 execute 内直接调 `video.get_components()`, 收到 None 抛 `AttributeError: 'NoneType' object has no attribute 'get_components'`; 本节点 `video` 为 **optional**, None (mdtable 空 `<Video N>` 字段 / 上游无值) 时**全部输出 None 且不报错**, 下游 H3 Ref2VA 的 `ref_video_N` 是可选输入, None 被其内部 `if video_frames is None: continue` 安全跳过; **不做 sticky 回放** —— None 在此表示"该行没有视频参考", 回放上一次的视频会让生成张冠李戴。3020-参考场景 / 4030-参考视频 各 3 处已换用) |
| h3-guide | FallingTSH3AddGuide | H3 引导锚定 (**None 安全替代核心 MiniMaxH3AddGuide**: 核心节点在 image 与 audio 同为 None 时直接抛 `ValueError("MiniMaxH3AddGuide needs an image or an audio to anchor")`, 而 mdtable 空列按"可选输入惯例"输出 None、`execution.py` 又把上游 None 原样传给下游(`input_data_all[x] = obj`, 不走 `mark_missing`), 于是 N 路引导串联时只要有一列留空就整图失败; 本节点空输入时**原样透传 positive**(等价于该列无锚点), 有值时**直接委派 `MiniMaxH3AddGuide.execute`** 不复制其实现 —— 锚定语义与官方完全一致。4025-关键帧视频 的 9 路引导链已换用, 空槽因此可留空 (首帧 / 尾帧固定槽位照常参与, 只是两端都应填写); **并带同帧去重** —— 4025 的帧索引由「首帧硬钉第 0 帧 + 中间帧逐列 `关键帧n所在秒数` 换算 (`max(0, min(round(秒数 x 24), length - 1))`) + 尾帧取 `length - 1`」确定, 两个中间帧秒数相同或换算后落在同一帧时会撞在同一帧, 本节点发现本次图片锚点与上游某槽撞帧时**撤掉本次图片锚点并告警**(仅撤图片 `latent`, 同帧音频锚点保留), 避免同一时刻钉上两个互相矛盾的画面致物件漂移) |
| world-refine | WorldRefinePLY | 世界重建精修 (md 表的 8 视图批 → **504 前馈 + 2% 尺度过滤 + 3DGS 全参数精修** → 一个最高质量 `.ply` 的路径; 节点在主进程只做编排: 按 8 张图的**内容哈希**落 `temp\worldrefine\<hash>\00..07.png` → 用 HYWM2 隔离环境的解释器跑 `world-refine\refine_0034_gs.py` → 取回 stdout 的 `[OUT] ` 路径; **故意不放 `comfy-env.toml`**, 因为 gsplat 只在 `hywm2-nodes` 环境里, 而图内 `HYWM2Reconstruct` 先装模型再测空闲显存只能拿 406; 这样图里**只有一次前馈**、不与图内重建抢 8GB 显存。`images` 批序必须是 前面/前右/右面/右后/后面/后左/左面/左前, 张数≠8 才报错; `images=None` → 回放上次产出的 PLY(无产出输出空串, 下游视口显示 not found 不崩)。⚠️ 只依赖一个绝对路径 `hywm2-nodes\python.exe`(在 AppData 内, 不在仓库内); 精修脚本与 HYWM2 根目录由**本文件位置 realpath 反推项目根**得到(`ComfyUI\custom_nodes` 那层目录软链会被解开), 项目整体搬家后自动跟随(2026-09-30 由 `D:\Comfy` 搬到 `D:\AI\Comfy` 时改); 改本节点后必须**重启 ComfyUI**)。⚠️ **子进程 stdout 必须钉 UTF-8**(2026-09-28 实测): Windows 上 stdout 接到管道时 Python 退回 GBK, 而产物路径带中文(`output\0034_世界模型\`), 父进程按 UTF-8 解出来是 `\ufffd` ⇒ `os.path.isfile` 为假、节点误报「脚本没报出 PLY 路径」; **此时脚本其实已成功写出 PLY** —— 只按产物文件验收会误判 PASS, 必须查 `/history` 的 `status.status_str`。三保险: 子进程 env 带 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`、脚本自己 `sys.stdout.reconfigure(encoding="utf-8")`、`[OUT] ` 解析失败时回退 `--asset-dir`/`--out-name` 约定路径 —— 于是**不依赖启动 ComfyUI 时带没带 UTF-8 环境**。⚠️ **`f_dc_*` 是 SH 的 DC 系数, 不是 RGB** —— 落盘必须写 `sh[:, 0, :]` 原值, 因为读取端一律再算一次 `0.5 + C0*f_dc`(本插件自己的 `process_ply_to_splat`、浏览器视口 mkkellogg、核心 `RenderSplat` 都是这个口径); 传已经 `*C0+0.5` 过的 RGB 进去 = 变换做两遍, 整间书房被抬到中灰(实测 8 张参考图均值 `[0.165,0.136,0.101]` → PLY 解码成 `[0.556,0.546,0.535]`, 亮度 +0.41、饱和度只剩 1/3.5), 视口里就是"参考图的颜色没进世界模型"一片发白。参数 **9** 个: 步数 / mode(**默认 `all`**) / **几何信任域 `reg`**(仅 mode=all 时生效: 上游推理**不做跨视图融合** —— `rasterization.py:240-242` 在 `is_inference` 直接 return, 把体素合并 / 置信度过滤短路掉, 每个视图按自己的深度 + 自己预测的位姿反投影(`:522`)⇒ 每个可见表面 2 层壳, 这就是视口里的"影像重叠/重影"; 只修外观(mode=appearance)冻结几何去不掉, mode=all 才会把壳收拢, 但几何动多了门框/墙角会出"焦边暗斑", reg 0→10 的取舍实测见 `docs\HY-World-2.0-ComfyUI可行性-2026-09-27.md` §8.7, 默认 3.0) / 透明度信任域 / **颜色信任域**(每步只监督 1 个视角, 个别高斯会被撑成彩虹色去凑那一个视角, DC-only 渲染里就是墙角上的粉/绿噪点; 0.5 把"饱和度>0.3"从 3.07% 压到 1.58%) / 前馈长边 / 颜色监督长边 / 剪枝阈值 / 重算前馈) **+ 2 个可选先验输入** `extrinsics`([N,4,4] w2c, 上游 `WorldPanoramaViews`)/ `intrinsics`([3,3] 或 [N,3,3]): 接了就把位姿作为相机先验注入前馈(`cond_flags=[cam,0,intr]`), 位姿**不再由模型预测** —— 这是从源头消重影的入口。节点把 w2c 逐视角取逆落成 `prior_camera.json`(口径同 HYWM2 `_dump_camera_priors_json`), 脚本带 `--prior-camera` 传给 `pipe._run_inference`; **先验内容也进缓存哈希**(换先验必然重跑前馈), 脚本还会打印「先验生效度: 预测位姿 vs 注入先验的旋转/平移偏差」(实测 6 视角全景: 旋转偏差中位 1.16°、最大 1.77°, 平移 0.0088) —— 这是判断先验有没有真的约束住位姿头的量化指标。视图数不再死钉 8: `>=2` 即可(接全景视角批时是 6/12/21…), 无先验且 ≠8 时告警。`gt` 也要跟着改(全景路径 = 视角边长 952) |
| world-panorama | WorldSurroundPanorama | 360° 视频 → **横向展开长图**(等距圆柱条带, 上行=天) + `valid_band`(有效竖向跨度) + `v_center`(竖向中心) + `report`。`mode=equirect`(真 360 相机导出)直接抽帧; `mode=unfold`/`auto` 走旋转展开 —— **2026-09-28 v2 重做**: ① 粗采样估「每帧画面位移」→ 按 `target_shift_percent`(默认 12% 画面宽)**自动定抽帧步长**(转得快少抽/转得慢多抽, **末帧必采到**), 再**自适应补密**: 只对「几何模型解不出(匹配不足/RANSAC 失败) 或 位移超上限(3× 目标)」的相邻采样对插中间帧(专治"长静止段 + 甩镜段"这类不均匀转速), 静止段保守抽稀(位移<0.5px 才丢, 至少留 8 帧)。⚠️ **补密判据别用"单应内点比例"**: 真实素材帧间有内容漂移/运动模糊, 比例常年 0.24~0.37 却几何完好 —— 拿比例<0.40 触发会给 0031 平白补 11 帧、f 311.8→332.4px、与源帧 NCC 0.74→0.51; 也不能只看位移中位数(88° 错配对会给出 13.7px 的"正常"值 ⇒ 补密永不触发)。首末采样帧**几何重合**(匹配≥40 + 单应内点比例≥0.3 + 内点中位位移 <0.35×典型帧间位移 + 在解出的 f 下对应点转角 <5°)才判定「整整一圈」并把总转角吸附成 360°(实测 0031 逐帧位移累积只有 311°, 吸附后与独立 ORB 曲线一致; 只用位移中位数会被误匹配骗过 ⇒ 低纹理素材把 200° 弧**静默**拉成 360°、漂移 31.8°); **吸附窗口不能靠 `|span−2π|<10°`**(48 帧素材采样弧 352.4° 被拉成 360° ⇒ 尺度错 2.15%、中段漂移 3.1°、NCC 0.572); 整段累计横向位移 <6% 画面宽(近乎静止) ⇒ **直接报错**「不是环绕镜头」; ② 相邻帧 ORB + RANSAC 纯偏航单应 → 用**对应点纯旋转一致性**(Δ 的鲁棒相对离散度 + 竖直残差, 无量纲 ⇒ 不会退化成「f 越大越好」) 与**相邻帧重叠区稠密光度一致性**联立定焦距, 闭环值/单对单应只作交叉校验(实测 0031: 光度 311.8px / 对应点 295.8 / 闭环 290.7 / 单对单应 380.1 —— 单应受平移污染会高估 22%); ③ **逐像素 winner-take-all**: 每个输出像素只取光学轴夹角最小的那一帧, 从不做帧间平均 ⇒ 结构上不可能有重影; 换帧处只对**低频**羽化(`seam_feather` 默认 7px, 高频仍来自唯一那一帧), 帧间亮度差用相邻帧曝光链(链式偏差不在 2%~12% 时自动关闭, 免得把噪声当曝光漂移); ④ 输出**紧贴有效带的横条**(不再输出 2:1 画布 —— 旋转视频只有 ±36° 有数据, v1 的 2:1 上下各 30% 是纯黑), 没被完全覆盖的行自动裁掉 ⇒ 一条黑边都没有; ⑤ **竖直朝向改回世界地图口径**(第 0 行 = 仰角 +band/2): v1 的行映射把源图下方放到第 0 行 ⇒ 长图**倒立**(实测帧 0 同角度区: 正放 NCC 0.16 / 上下翻转 0.52)。实测 0031 旋镜视频(832x480/24fps/243 帧, **转速不均匀**: 前 24 帧只转 8°、末 24 帧 转 39°): 抽 21→20 帧(步长 12, 8.4px/帧), f=311.8px → h_fov 106.3°, 长图 **2939x592 = 8.16px/度**(v1 只有 5.76), 有效带 72.6°, **空白 0%**, 对齐残差 2.7/255; 与源帧同内容处 NCC **0.74**(v1 0.55)、拉普拉斯锐度 **12.3 vs 2.9(4.3 倍)**; 在整圈 9 个位置扫偏航峰值与独立 ORB 位移曲线一致(≤5°)。`video`(VIDEO)/`images`(IMAGE) 二选一, 都为空则全部输出 None(不 sticky) |
| world-panorama | WorldPanoramaViews | 横向长图 → 一网格透视视角 + **每视角精确 w2c 外参 / 内参**(相机全在球心, 纯旋转 ⇒ 平移恒 0, 外参正交)。外参口径与上游 `HYWM2SamplePanorama` 一致(`f_px=(size/2)/tan(fov/2)`, `cx=cy=(size-1)/2`, 外参取 `R.T`), **等距圆柱的竖直朝向按世界地图口径修正**: `elev=asin(-ry)`、`eq_y=(elev_top-elev)/v_range·(H-1)`(v1/上游那套要求长图上行=地, 拿真 equirect 图会上下颠倒; 本节点与 `WorldSurroundPanorama` **成对**修正, 切出来的视角画面与 v1 **完全一致** —— 老长图+老公式对源帧 0.724、新长图+新公式 0.71)。竖向采样由 `v_center`/`v_range` 决定(接长图的 v_center / valid_band): `step=fov·(1-重叠%)`, `num_h=ceil(360/step)`, **`v_range ≤ fov` 时只切一行**(旋转视频的 valid_band 正是这个量级; 按 `ceil(v_range/step)` 会切出 2 行、每行一半黑边 —— 实测 12 视角时前馈 token 预算只够 406, 改单行 6 视角后涨到 **574**), 否则 `num_v=ceil(v_range/step)`(v_range=150/180 时 3 行, 供真全景用); 竖向档位以 `v_center` 为中心**对称**摆放。⚠️ 长图是 2:1 而 `v_range` 没接到 valid_band 时告警。`panorama` 为空 → images/extrinsics/intrinsics 全 None(不 sticky) |

注:`preview-image` / `preview-video` / `preview-audio` / `audio-trim` / `load-image` / `load-video` / `load-audio` 目录名含连字符,不能直接 `from xxx import`,入口经 `importlib` 按名加载。

注(分类, 2026-10-02): **20 个节点 CATEGORY 统一为顶级 `FallingTS`**(V1 `CATEGORY=`, V3 `category=`) —— 双击画布的选择面板里都在同一 `FallingTS` 分组下, 原有子分组与核心 `image`/`video`/`audio` 归属均已收拢。

注(灰度遮罩, 2026-10-02): **灰度遮罩资源表已废弃** —— `stories/<故事库>/0010_灰度遮罩.md` 与 `stories/template/0010_灰度遮罩.md` 已删除。遮罩改为「加载图像」节点(`FallingTSLoadImage`, 工作流 `0010_灰度遮罩`)加载原图 → 遮罩编辑器绘制 → 保存进 `output/0010_灰度遮罩/<5位编号>_名称.png`(编号自增)。资源表侧只需在万物变化的 `灰度遮罩(MASK)` 列写 `@{0010_灰度遮罩/编号_名称}` —— `@{}` 按 output/input 目录找文件, **不读数据表**, 故删表不影响引用解析。

### 产物落盘目录约定(三个预览保存节点)

预览保存节点(`PreviewImageSave` / `PreviewVideo` / `PreviewAudioSave`)点「保存」时把文件写进 `output/<子目录>/<文件名>`。子目录名由 `output_subdir.resolve_subdir` 解析(2026-09-24 起):

- 工作流的 API prompt 里有 `FallingTSMarkDownTable` 节点 → 用它的 `data.md_path` **表文件名**(去 `.md`)作子目录名;
- 没有 md 表节点 → 退回前端 POST 的 `workflow_name`(原行为)。

这样产物目录与资源表 `@{表文件名/行 ID}` 的口径一致(mdtable 解析器严格按 `output/<表文件名>/` 找文件),引用因此走**严格命中**而非递归兜底。代价:`0011_万物建模` 与 `00110_万物建模_QI2.1` 共用同一张表 ⇒ 落同一个目录,同一行 ID 的产物互相覆盖。

⚠️ **V3 节点的 hidden 不进 `execute` 实参** —— `execution.py` 的 `get_finalized_class_inputs` 把 hidden 单独摘出,只能经 `cls.hidden.<name>` 取(`HiddenHolder.__getattr__` 对未知键返回 None)。所以 `preview-video` / `preview-audio` 的 `execute` 里**不能**写 `prompt=None` 形参(写了恒为 None, 静默失效),prompt 一律从 `cls.hidden.prompt` 读;`preview-image` 是 V1 节点(`"hidden": {"prompt": "PROMPT"}`),prompt 才是真正的 execute 实参。**加/改任何依赖 hidden 的 V3 节点逻辑前先确认这一点。**

### None 容忍约定(全部 19 节点)

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
- **世界模型 —— 360 视频/全景源**(world-panorama 两节点):`video`+`images` 全空 → `panorama=None`;`panorama=None` → `images/extrinsics/intrinsics` 全 None;**故意不做 sticky** —— 回放上一次的长图/视角会把另一段视频的世界模型张冠李戴(与 video-components 同一条理由);`WorldRefinePLY` 则相反: 它是**输出类**节点, `images=None` 时回放**上次产出的 PLY 路径**(无产出则空串, 下游视口显示 not found 不崩), 这样单独点视口节点不会把整条重建链拉回来重跑;
- **继续类**(proceed):`any` 为 None(未拉取上游)时**不清 `_data_cache`**、不覆盖 `widgets_values`/`proceedState` 等节点数据——None 只表示"本次没有数据",不等于"清空"。`IS_CHANGED` 含 `_reset_generation`(每次 `/proceed/reset` 递增)+ 是否已放行 → 每次 Run 后继续节点必重新执行(重拉上游填 `_data_cache`),不被 ComfyUI 全局执行缓存跳过(否则同进程重跑同图时「继续」400「没有上游数据」)。

### 前端状态与后端同步约定(全部 19 节点)

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
  - `preview-image` → `GET /preview-image/image-url/{id}?workflow_id=<app.rootGraph.id>` → `restoreImages()`
  - `preview-video` → `GET /preview-video/video-url/{id}` → `restoreVideo()`
  - `preview-audio` → `GET /preview-audio/audio-url/{id}` → `refreshPlayer()`
  - `audio-trim` → `GET /audio-trim/audio-url/{id}` → `refreshWaveform()` 内一并设置
- 在 `onConfigure`(工作流加载完成)末尾调用"读回重建":
  - `audio-trim` → `refreshWaveform()`:GET `/audio-trim/waveform/{id}` 一次拿回 peaks + segments;
  - `load-video` → `restoreFrames()`:GET `/fallingts_load_video/state/{id}` 拿帧号, 再逐个 POST `/fallingts_load_video/frame/{id}`(`append=false`)取 PNG 转 blob URL;
- 界面态同步要**双向且含空值**: `Array.isArray(data.segments)` 为真就写回(即便是空数组), 否则删光段后刷新会残留旧列表。
- ⚠️ **每一个 `app.extensionManager.toast.add({...})` 都必须显式带 `life: 3000`** —— PrimeVue 的 `ToastMessage` 只在 `message.life` 为真时才起定时器(`vendor-primevue-*.js`:`this.message.life&&(this.closeTimeout=setTimeout(...))`), **没有默认值**;漏写 `life` 的 toast 会永久挂在右上角不消失(2026-10-01 实测: 本插件原有 29 处漏写, 全是「保存/截帧/完成/继续」的成功与失败提示)。插件自绘的右下角 toast(`task_notify.js`)同样按 3000ms 收口。

#### 后端(`nodes.py`)要求

- `/xxx/clear` 端点若因兼容保留, 必须 **no-op**(只回 ok), 不得清 `_last_output` 或任何界面态字段;
- `/xxx/reset` 只在**默认 Run** 分支被调(前端包装 `app.queuePrompt`, 判断 `queueNodeIds` 为空), 清执行态 + 递增 `_reset_generation`;
- **绝不写 `_last_output.clear()`** —— 那会把媒体态一起清掉。

#### 预览缓存的键必须带工作流作用域(`preview-image`,2026-09-24)

`_last_output` / `_last_ui` 的键是 **`<工作流根 id>::<节点 id>`**(工作流 id 取不到时退回纯节点 id)。根 id 两边同源:后端从 `extra_pnginfo.workflow.id` 取(前端 `graphToPrompt()` 把 `graph.serialize()` 整个塞进 `extra_pnginfo.workflow`,而 `serialize()` 返回 `{id: this.id, ...}`),前端从 **`app.rootGraph.id`** 取(必须取根图 —— 取子图 `node.graph` 会拿到别的 id)。

**为什么**:只按节点 id 缓存会**跨工作流串图** —— 节点 id 在各工作流之间大量重复(实测 `18` 撞 6 个工作流、`62` 撞 4 个、`901`~`908` 各撞 3~4 个、`6013/6014` 撞 2 个),打开工作流 B 时会把之前跑过的 A 的同 id 节点预览当成 B 的预览显示出来(「遗留预览」)。同一份缓存还被「保存」按钮使用, 所以串图会把 **A 的图写进 B 的产物目录**。

- `GET /preview-image/image-url/{id}` 必须带 `?workflow_id=`;`POST /preview-image/save/{id}` 必须带 body 字段 `workflow_id`;
- 读缓存一律走 `_cache_get(cache, node_id, workflow_id)`:优先带作用域的键, 再退回纯节点 id —— 退回是为了兼容「那次执行没带工作流标识」的写入(无头 API 提交时 `extra_pnginfo` 为空), 否则页面刷新后这类预览再也读不回来;
- `image-url` 返回前用 `_temp_file_exists()` 过滤掉指向已被清理的 temp 文件的死条目(纯内存缓存 + 会被清理的 temp 目录 ⇒ 死条目必然出现, 不过滤就会在节点上挂一张加载失败的图);
- ⚠️ **`preview-video` / `preview-audio` / `audio-trim` 的 `_last_output` 目前仍只按节点 id 索引**, 有同样的跨工作流串图风险(它们的备用播放器会在执行后被收起, 所以可见症状限于"跑之前显示别的工作流的媒体")。要修就照本节同一套做法。

#### 预览区「两个图片 / 两个播放器」的通用根因

备用元素是**普通 widget**(`addDOMWidget`), 在 Vue 节点体里的渲染顺序是 `端口 → widgets → 提升预览 → 原生预览`, 所以备用元素排在**原生预览之前(上方)**;而 `restoreXxx()` 只在 `onConfigure` 跑一次, 那时 Vue 节点 DOM 往往还没挂出来 → 判定"节点里没有原生预览"→ 显示备用元素。此后**没有任何时机再收它**, 跑完流程原生预览出现, 节点上就成了两个(备用在上、原生在下)。

**所以每个预览节点都必须在执行结束后再判定一次**: `api.addEventListener("executed" / "execution_success")` 后按 600ms / 2.5s 两拍重跑 `restoreXxx()`(第二拍给 Vue 异步挂载留余量)。

- `preview-video`(挂 `executed` / `progress`)、`preview-audio`(同)已有;
- `preview-image` 2026-09-24 补上, 只挂 `executed` / `execution_success` —— **不挂 `progress`**: progress 每个采样步都发, 会把"跑完再判定"变成高频轮询(每个预览节点一次 HTTP)。

#### 为什么必须有 `_reset_generation`

ComfyUI 在服务端缓存每个节点的输出(`caches.outputs`), 同进程内重跑同一张图时节点会被**直接跳过**。递增 `_reset_generation` → `fingerprint_inputs` 返回值变化 → ComfyUI 认为节点"变了" → 强制执行。`proceed` / `preview-video` / `audio-trim` / `preview-audio` 都用这一招(否则改了段/帧再 Run 会拿到旧结果, 或「继续」报 400「没有上游数据」)。

#### 反面教材(均已修)

- `preview-audio` 的 `_handle_clear` 曾写成 `_last_output.clear()` —— 刷新即清空音频缓存,「保存」与播放器都没数据; 更糟的是 ComfyUI 执行缓存还在, 导致全量 Run 时该节点被跳过、缓存再也填不回来;
- `preview-video` / `audio-trim` 曾在 `setup()` POST `/clear` 清界面态 —— 刷新丢掉上一次的截帧/截段结果;
- **`preview-video.js` 曾有 `app.registerExtension({...})` 里两个 `setup()`** —— JS 对象字面量的重复键**以后者为准**, 于是包装 `app.queuePrompt`(默认 Run 前 POST `/preview-video/reset`)的那段成了**死代码**: `_reset_generation` 不递增 → `fingerprint_inputs` 不变 → PreviewVideo 被执行缓存跳过 → 不重新生成视频、不发新 UI 事件, 前端预览一直停在**上一次的 temp 文件**上; 该文件一旦被清理(ComfyUI 重启/清 temp), 点播放就报「视频加载失败 / Invalid URL」。已合并为一个 `setup()`。**注册对象里的方法名不允许重复**(排查:`Select-String` 找同一对象里的同名键);
- `preview-video` 的 `restoreVideo()` 曾把后端返回的 `/view?...` **原样**写给 `<video>`, 且**无条件覆盖**前端自己算出的地址 —— 前者是相对路径, 而前端原生 `VideoPreview` 组件的文件名标签用 `new URL(e)` 解析(无 base), 加载失败时标签会显示成 `Invalid URL`; 后者让播放器指向上一次执行的旧文件。现在一律转**绝对**地址, 且只在"指向的文件不是本次这个"时才改写 src。**不要往 `app.nodePreviewImages[nodeId]` 写地址**: `getNodeImageUrls` 会优先读它, 写进去后前端后续渲染一直用这个快照值(预览反而停在旧文件), 实测还会让节点预览进入递归更新、页面主线程卡死。
- **`preview-image` 曾只按节点 id 缓存预览, 且备用图只在 `onConfigure` 判定一次**(2026-09-24 修) —— 两个后果: ① 打开别的工作流时, 同 id 节点上会显示**上一次别的流程留下的图**(实测后端 `_last_ui["2"]` 残留一张 64×64 的 E2E 测试图, 而 `0010_灰度遮罩` 的 `PreviewImageSave` 正好是节点 2); ② 跑完流程后节点上**同时**显示两张图 —— 上面是插件备用 `<img>`(陈旧, 只反映加载那一刻的缓存), 下面是原生 Vue 预览(本次真实结果)。因为备用图是 widget、渲染在原生预览之前, 而它**不在前端 `nodePreviewImages`/`nodeOutputs` 里**, 鼠标中键也点不到它 —— `node_image_middleclick.js` 的取图通道只有前端自己那四路, 且 Vue DOM 模式那一路要求 `target.closest('.image-preview')`(只有原生预览组件带这个类)。修法见上两节。

### 分段执行约定(lazy 门控 + partial 提交)

「先跑到本节点停住 → 点按钮只跑下游」这套机制(**load-video 的截帧/audio-trim 的截段/proceed 的继续**)由两半组成, **缺一不可**:

**① lazy 门控(后端) —— 决定"上游跑不跑"**

- **输入必须显式声明 `lazy=True`**(V3: `IO.Audio.Input("audio", lazy=True, ...)`), 否则引擎不会调用节点的 `check_lazy_status`, 写了也等于没写 —— 每次都照常拉上游;
- `check_lazy_status` 返回需要拉取的上游输入名: **已放行(完成/继续)→ `[]` 不拉**; 未放行 → `["audio"]` 拉上游更新缓存;
- 用 `MISSING = object()` 哨兵区分"该输入没连线"(`MISSING`)与"连了线但上游未求值"(`None`);
- `execute` 里 `audio is None`(lazy 未拉上游)时**用 `_last_output` 缓存继续**; 未放行则返回 `ExecutionBlocker(None)` 阻断全部下游。
- **对照**: `audio-trim` 的 `IO.Audio.Input("audio", lazy=True, ...)` 是正确样板(它的输入是上游数据, 不拉就重跑不了上游); `audio-trim` 曾经漏掉 `lazy=True`, 表现为「点完成仍重新加载模型、耗时 90s+」。
- `load-video`(`FallingTSLoadVideo`)**不用 lazy**: 它的 `video` 是文件下拉(input/输出目录里的文件名), 没有"上游数据"可拉 —— 未完成时靠 `ExecutionBlocker` 阻断下游, 已完成时 execute 直接取 `_last_output` 缓存(不重新解码), 于是 partial 提交把它重新执行也只是取缓存, 上游(加载/解码)不会白跑。

**② partial 提交(前端) —— 决定"下游跑哪些"**

- 提交**完整图**(不裁剪 `prompt.output`), 另带 `partial_execution_targets` = 本节点下游的输出节点 id 列表;
- ComfyUI 的 `validate_prompt` 只把 targets 里的 output node 纳入执行(`execution.py`), 上游是否执行由 ① 的 lazy 边界决定;
- **不要按 targets 反推依赖闭包去裁剪 prompt** —— 多余且会掩盖问题(曾因此误判"partial 已生效");
- 第三参数是**选项对象**: `fetchApi("/prompt", {body: JSON.stringify({prompt, partial_execution_targets})})`。注意 `api.queuePrompt(index, prompt, options)` 的第 3 参是 `{partialExecutionTargets}`, 传裸数组会被静默忽略、退化成全量提交。

### 「不打开任何工作流」前端扩展(`no_auto_workflow.js`,2026-09-24)

目标: 关掉工作流之后标签栏为空、画布空白、**没有活动工作流** —— 既不残留打开的工作流,也不残留未保存的占位工作流。

**上游两条硬编码路径(前端包 1.52.7, 都没有设置开关)**:

- `workflowService.ts` 的 `closeWorkflow()`: 在 `openWorkflows.length === 1` 时**先** `await loadDefaultWorkflow()`(即 `app.loadGraphData(defaultGraph)`)**再**关闭原工作流 ⇒ 关掉最后一个标签必然残留一个 `Unsaved Workflow`(默认图,10 个节点);
- `useWorkflowPersistenceV2.ts` 的 `resolveStartupOutcome()`: `Comfy.TutorialCompleted ? await comfyApp.loadGraphData() : await loadBlankWorkflow()` ⇒ **每次刷新页面也必定自动打开一个** `Unsaved Workflow`。
- 内置设置里**没有**对应项:`Comfy.Workflow.WorkflowTabsPosition`(`Sidebar`/`Topbar`)只是"标签放顶部还是侧栏", 不改变"要不要打开工作流"。

**实现(包 `app.loadGraphData` —— 打开工作流的唯一入口, 内部经 `afterLoadNewGraph` → `activateLoadedWorkflow` → `createNewTemporary` 建标签)**:

1. **识别关闭最后一个**: 给 `workflowDraftV2` store 的 `removeDraft` 挂前哨 —— 上游在塞默认工作流之前**同步**调它, 且它只被 `close`/`delete` 调用; 判定条件 `openWorkflows.length === 1 && openWorkflows[0].path === 被移除的 path`。标记只保留一个事件循环拍(`setTimeout(…, 0)` 清), 因为其它调用点(`discardStartupBlankDraft`)后面不跟加载, 不会误伤。
2. **识别启动自动打开**: 零实参的 `loadGraphData()` 在启动路径之外只有 legacy 菜单的 `Load default workflow?` 按钮; 另有未完成新手引导时的 `loadBlankWorkflow() → loadGraphData(空白图)`, 用"启动 20s 时间窗 + 空图 + 无活动工作流 + 无打开工作流"共同限定。两者都再加一道 **`userInteracted`**(首次 `pointerdown`/`keydown` 即置真)—— 启动自动打开必然发生在任何交互之前, 一旦用户碰过页面, 之后的加载都算用户意图(否则刷新后 20 秒内按 Ctrl+N「New Blank Workflow」会被误拦)。
3. **拦截后绝不新建标签**: 把**当前活动工作流**当作第 4 实参传进去 —— `activateLoadedWorkflow` 里的 `workflowStore.openWorkflow()` 会因 `isActive()` 直接返回, 不走 `createNewTemporary`(与 `workflow_reload_button.js` 注释里记的坑同源), 同时把载荷换成 `blankGraph` 让画布清空。
4. **收尾**: 关完之后 `activeWorkflow` 仍指着那个已不在 `openWorkflows` 里的旧对象, 用一次性 `setTimeout` 兜底置空(前端源码里 `activeWorkflow` 到处都有 `?.` / `if (!activeWorkflow) return` 守卫, `useWorkflowPersistenceV2` 的 `restoreState` 也显式处理空值, 所以 `null` 是安全状态)。
5. ⚠️ `blankCanvas()` 必须用官方的 `app.isGraphReady` 判据 —— 直接读 `app.rootGraph` 会在图未初始化时打一行 `console.error('ComfyApp graph accessed before initialization')`。

**调试**: URL 加 `?noAutoWorkflow=off` 可临时停用本扩展做对照。
**验证**: `scripts\_verify-no-auto-workflow.py`(无头 chromium + CDP 真跑; `--off` 跑基线对照, `--port N` 换端口)。基线(停用)实测: 启动后 `open=['workflows/Unsaved Workflow.json']`, 关掉最后一个后仍残留 1 个;启用后两处都是 `open=[] / active=null / nodes=0`。
⚠️ 跑该脚本前确认没有残留的 headless chromium 占着调试端口 —— 根仓库 `scripts\cdp.py` 的 `start()` 现在会先探测端口(占用就直接报错), `close()` 在 Windows 除 `taskkill /T /F` 外还**按 `--user-data-dir` 兜底杀**。只 `terminate()`/`taskkill` Popen 的 pid 都不够: chrome 会自我重启, 真正持有调试端口的常是另一个进程, 于是浏览器活下来继续占端口, 下一次会静默复用旧 profile 里的 localStorage, 验证结果不可信(实测踩过两次)。

### 「运行前命令」(`pre-run/nodes.py` + `pre_run_command.js`,2026-09-30)

需求: **每次「点击运行」或按 Ctrl+Enter 提交之前**, 先在宿主上执行一条在系统设置里配置的命令; 配置为空则跳过。

**开箱可测**: 工作区根有个现成的测试脚本 `test-start.py` —— 每次提交前**打开系统记事本, 里面写着「Comfy 开始了」**, 设置里填 `.venv\Scripts\python.exe test-start.py` 即可验证整条链路。脚本先把这句话写进 `logs\test-start.txt`(UTF-8 **带 BOM**, 记事本据此认编码, 中文不乱码 —— 无 BOM 的 UTF-8 在老版记事本上会按 ANSI/GBK 解读), 再用后台 `notepad.exe` 打开它; 不装任何第三方库, **不 `wait()` 记事本退出**, 且**子进程三根标准流都接 `DEVNULL`** —— 后端是**用管道读命令输出**的, 记事本若继承了管道写端, 本脚本即使已经退出, 后端仍要一直等到管道 EOF(= 关掉记事本)才提交, 表现为「运行」永远转圈; 并且**永远退出 0** —— 非 0 会被后端当成前置命令失败而拦掉运行, "记事本没弹出来"这种小事不该连带拦掉工作流。⚠️ 2026-09-30 由 `test-start-command.py`(右下角弹 WinRT 通知, 带 `--note/--title/--no-notify/--fail`)换成现在这个; 仍要测「前置命令失败 → 取消本次运行」那条路径, 把命令临时换成 `cmd /c exit 1` 即可。

**挂点选 `app.queuePrompt`(前端唯一提交入口)**: 运行按钮 `ComfyQueueButton` → 命令 `Comfy.QueuePrompt` → `app.queuePrompt(0, batchCount, {intent})`; Ctrl+Enter 就是这条命令的默认键位; Shift+运行 = `Comfy.QueuePromptFront`(排到队首)同样走它。所以包装一处即可覆盖两种触发方式, 不必逐个挂按钮/键位(与 `proceed.js` / `preview-video.js` / `route.js` / `fanout.js` 的包装链叠加, 顺序无关)。

**只对「默认 Run」生效**(第三参没有显式 `queueNodeIds`): 继续/截帧那类 partial 提交是"往下跑一段", 每截一帧都重跑一次前置命令会很莫名其妙(例如重复拷贝输入文件)。判据 `isDefaultRun(third)`: `undefined|null` → 真、数组看长度、对象看 `queueNodeIds?.length`。要改成"任何提交都执行"就去掉这个判断。

**语义照 git 的 pre-commit 钩子**(后端 `POST /fallingts_prerun/run`, body `{command}`):

| 情况 | 后端 | 前端 |
|------|------|------|
| 命令为空/纯空白(含 body 不是 JSON) | `{ok:true, skipped:true}`, **什么都不执行** | **连请求都不发**(本地判空直接放行) |
| 成功(exit 0) | `{ok:true, code:0, output, cwd, ms}` | 提交照常进行 |
| 非 0 退出 | `{ok:false, code:N, output}` | **取消本次运行**(返回 `false`) + error toast(带命令/退出码/输出尾部; 2026-10-01 起统一 `life: 3000`, 原为 12000) |
| 超时(600s) | 先 `taskkill /F /T` **杀整棵进程树**(只杀 shell 会留孤儿), `{ok:false, timeout:true}` | 同上, 原因显示「超时」 |
| **路由不存在(404/405)** | —— 后端根本没加载 | **只提示一次**(console.warn + warn toast)且**放行**, 绝不拦截 |

⚠️ 最后一行是必须的:**前端 js 经 `/extensions` 从磁盘即时加载, 后端路由却要重启才注册** ⇒ 页面一刷新就会出现"新前端 + 旧后端"的混搭。若把 404/405 当失败处理, 用户配了命令又没重启时**每次点运行都会被莫名取消**(本扩展永远不能成为提交链路的故障点)。

**cwd = Comfy 工作区根**(`custom_nodes` 的上一级, 本机 `D:\AI\Comfy`)—— 由本文件位置 realpath 反推(`ComfyUI\custom_nodes` 那层目录软链会被解开), 项目搬家后自动跟随, 不写死盘符; 反推失败(布局被改)则退回进程工作目录并告警。于是 `.venv\Scripts\python.exe scripts\prep.py` 这类相对路径可以直接写。

⚠️ **子进程输出必须逐个候选编码严格试解, 不能只试 `utf-8` + `locale.getpreferredencoding()`**: 后者受 `PYTHONUTF8=1` 影响会变成 utf-8, 而 `cmd` 的**内建命令**(`echo`/`dir`)写进管道时用的是控制台代码页(简中 = GBK) ⇒ 中文提示语会解成 `\ufffd`。候选表 = `utf-8` → 本地编码 → Windows 的 `oem`(输出代码页) → `mbcs`(ANSI), 全失败才 `errors="replace"` 兜底; 同时给子进程钉 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`。实测: 带 `PYTHONUTF8=1` 时 GBK 字节 **PASS**(修前 FAIL)。

**设置项位置(系统设置 → 常规 › 其它 → 提示音下面)**:

- 单元素 `category`(如 `["开始前命令"]`)会被前端 `buildTree` 变成 **root 叶子**, 再被 `useSettingUI` 收进合成的 `Other` 节点 ⇒ 侧栏「其它」分类里的**独立一项**; 一个叶子只能装一个设置, 所以"排在提示音下面"**必须另起一个 category**, 不能塞进提示音那个分类;
- 右栏各分组按 `SettingDialog.vue` 的 `sortedGroups` 以 **`sortOrder` 降序**排 ⇒ 提示音 `sortOrder: 20`(2026-09-30 补), 开始前命令 `sortOrder: 10`, 于是**提示音在上、开始前命令在下**;
- 设置项用内置 `type: "text"`(前端 `FormItem` 对未知 type 一律回退 `InputText`), 自带标签/问号 tooltip/持久化, 无需自绘 HTML; `attrs.placeholder` 给示例, `attrs.style` 限宽。

**验证**(改后端后**必须重启 ComfyUI**; 前端 js 只需强刷):

- 离线路由自检 `custom_nodes\ComfyUI-FallingTS\dev\_verify-prerun.py`(桩掉 `PromptServer`, 直调 handler): 空/纯空白/非 JSON body → `skipped`; 成功 + 中文输出 + cwd 生效 + 编码兜底; 非 0 退出码透传; 超时(临时把 `_TIMEOUT_S` 改 2s)强杀进程树 —— 5 组全 PASS;
- 浏览器端到端 `custom_nodes\ComfyUI-FallingTS\dev\_verify-prerun-ui.py`(无头 Edge + CDP, 参数 = 目标 URL): 设置项定义/排位 + 真开设置对话框量 `data-setting-id` 元素的 `getBoundingClientRect().top` 判上下 + 四种提交场景。**判"有没有被拦"不能用 `queuePrompt` 的返回值** —— 空白画布上原生 `queuePrompt` 本身就返回 `false`, 会假阳性; 用两个探针: ① `promptQueueing` 事件(原生入口被走到 ⇒ 包装放行)、② `/fallingts_prerun/run` 请求数(前置命令是否被请求) + 命令自己写标记文件验落盘。实测(2026-09-30, 前端包 1.52.7): 空命令 `reqs=0 / fired=1`; 失败 `reqs=1 / fired=0 / 标记落盘 / 返回 false`; 成功 `reqs=1 / fired=1 / 标记落盘`; partial `reqs=0 / fired=1 / 无标记`; 「其它」里 `提示音 top=220` < `开始前命令 top=877`, 输入框 placeholder 与 tooltip 均在。
- 混搭场景(新前端 + 旧后端)`custom_nodes\ComfyUI-FallingTS\dev\_verify-prerun-noroute.py`(直接打**没重启**的实例): 请求过后端(405)但**不拦截**(`fired=1`)、后端确实没执行(无标记文件)、console.warn 与 warn toast 各只 1 次且第二次提交不再提示 —— 实测打 8188(旧后端)全 PASS;
- ⚠️ 验证脚本要用**独立端口**(如 `--cpu --port 8189`)的临时实例: 主实例若由**提权 shell** 启动, 非提权会话 `taskkill` 会 `Access is denied`,`comfy-server.sh` 的停旧服务**静默失败**、而它的"端口已监听"判据会被**旧进程**满足 ⇒ 报告"就绪"但实际跑的还是旧代码(实测踩过: 新实例 `Port 8188 is already in use` 死在日志里, 路由一直 405)。启动临时实例时还要注意它日志里的 `Database is locked. Another ComfyUI process is already using this database.`(共享同一个 user 库, 不影响只读验证)。
- ⚠️ 脚本收尾**按 `--user-data-dir` 兜底杀浏览器时, 匹配串必须只命中 `msedge.exe`**: 早先写成 `CommandLine -like '*prerun-*'` 会把**调用方 shell 自己**(命令行里含脚本名)一起杀掉, 连带 dsh 的作业进程(报 `Windows Job runner exited with exit code 4294967295`)。

### 「跑完自动卸载模型」(`auto-unload/nodes.py` + `auto_unload.js`,2026-10)

需求: **每次工作流跑完(成功)且队列为空时**, 自动卸载全部已加载模型, 释放显存(等效内置「卸载模型」按钮, 但自动触发)。

**为什么不用内置的 `POST /free`**: /free 只是**置旗**(`unload_models`), 旗标在 prompt 主循环里**下一次 prompt 执行完之后**才被消费 ⇒ 单次"跑完"永远不会生效。故自建路由直调旗标最终调用的核心函数: `comfy.model_management.unload_all_models()`(对每个设备 `free_memory(1e30)` 强逐全部已加载模型, 逐不动就逐能逐的, 不抛异常) → `gc.collect()` → `soft_empty_cache()`(sync + empty_cache + ipc_collect)。

**挂点**: 前端总线 `execution_success` 事件(每个 prompt 成功完成后触发, 含继续/截帧的 partial 提交) → `POST /fallingts_auto_unload/unload`。后端是"卸不卸"的唯一裁决者:

- 队列非空(`PromptQueue.get_tasks_remaining() > 0`, 多任务连跑) → `{skipped: true}`, 只有最后一个真正卸载, 避免中途把模型逐掉导致下一个任务被迫重新加载;
- 队列为空 → 工作线程池里卸载(逐大模型 + empty_cache 可能耗时数秒, 不能阻塞 aiohttp 事件循环), 返回 `freed_mb/free_mb/ms`(`get_free_memory` 前后差值), 前端弹 info toast(`life: 3000`), 结果同时落 `logging`(`[FallingTS.AutoUnload]` 行, 写 `comfyui.log`)。

**只监听 success**: 失败/中断时保留模型, 下次重试不必重新加载(大模型重载约 60s)。时序安全: `execution_success` 到达浏览器时该 prompt 已被 `task_done` 从队列 pop、`queue_updated` 已推送, 与执行线程无竞态; 唯一竞态是"跑完立刻又提交新任务", 最坏情况 = 新任务的模型多加载一次(与内置按钮在运行中被点击等效), 不崩溃。

**404/405 处理**同运行前命令: 前端 js 经 `/extensions` 从磁盘即时加载, 后端路由却要重启才注册 ⇒ "新前端 + 旧后端"混搭时**只提示一次并放行**。

**设置项**: 系统设置 → 常规 › 其它 → 「跑完自动卸载模型」(内置 `type: "boolean"`, 默认开, 单元素 category + `sortOrder: 5` ⇒ 排在「开始前命令」(10) 下面; 提示音 20 > 开始前命令 10 > 本项 5)。

**验证**(改后端后**必须重启 ComfyUI**; 前端 js 只需强刷):

- 离线路由自检 `dev\_verify-auto-unload.py`(桩掉 `PromptServer` 与 `model_management`, 直调 handler): 队列非空 → `skipped` 且**完全不调用**卸载; 队列为空 → 卸载 + 显存差值正确 + 调用顺序 `unload → soft_empty_cache`; 逐不动(空闲不涨)时 `freed_mb` 不为负 —— 全 PASS;
- 真实实例(8189 临时实例, `--cpu`): `/extensions` 含 `auto_unload.js`; 提交 prompt 后紧循环打路由, 同时抓到 `(skipped, remaining=1)` 与真正卸载两种状态; 日志出现 `[FallingTS.AutoUnload] 已卸载全部模型` 行。
- ⚠️ 主实例(8188)重启前跑的是旧后端: 强刷页面后前端会提示一次「自动卸载模型未生效」, 属预期, 重启即好。

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
