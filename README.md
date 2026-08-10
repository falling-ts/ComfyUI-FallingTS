# ComfyUI-FallingTS

ComfyUI 自定义节点插件:一组**通用工具节点** + **前端增强**。零外部依赖,基于 ComfyUI V3 扩展 API(`comfy_api.latest`)。

## 功能总览

### 工具节点

| 节点 | Node ID | 分类 | 功能 |
|------|---------|------|------|
| 继续节点 | `FallingTSContinue` | `FallingTS/控制` | 工作流**分段执行**:默认阻塞下游,「继续」放行一段,逐段运行到底(靠执行缓存,不重复算上游) |
| 路由节点 | `FallingTSRoute` | `FallingTS/控制` | 1 进 2 出:一个值按 `switch` 路由到两路输出之一,未选那路输出阻断(ExecutionBlocker),下游不执行 |
| 通用表格 | `FallingTSTable` | `FallingTS/表格` | Excel 式表格(数据内嵌工作流):顶部「选择」下拉选行,输出该行 A/B/C... 各列字符串;行/列数可调,输出端口随列数增减 |
| MarkDown 数据表 | `FallingTSMarkDownTable` | `FallingTS/表格` | **从 md 文件解析数据表**:系统选择器选文件 → 弹窗按字段搜索+分页单选一行 → 节点内按「标题(类型)」渲染可编辑表单(IMAGE/VIDEO/AUDIO/STRING/INT/FLOAT/BOOLEAN/TEXT),刷新按 ID 重查 md;输出选中行各字段(按类型)+ 整行数据 JSON |
| 下拉选择器 | `FallingTSSelector` | `FallingTS/工具` | 文本+下拉:逗号分隔选项实时更新下拉,选中项输出索引(INT) + 选项文本(STRING) |
| 分组开关 | `FallingTSSwitch` | `FallingTS/工具` | 一个 `switch` 布尔同时切换 total 组(每组 为假时/为真时 → 输出,ANY),total 最少 1 |
| 视频预览 | `PreviewVideo` | `video` | 预览到 temp 目录;点「保存」按 `filename_prefix` 写 output(`.mp4`,同名覆盖,无序号) |
| 图片预览保存 | `PreviewImageSave` | `FallingTS/工具` | 始终预览(temp 不写 output);点「**保存**」才按 文件名/格式/位深/色彩空间 写 output,**同名覆盖、无序号** |
| 音频预览保存 | `PreviewAudioSave` | `audio` | 预览到 temp 目录;点「**保存**」按 `filename_prefix`+格式 写 output(flac/mp3/opus,**同名覆盖、无序号**) |

### Web 前端增强(10 个,安装即用,无需配置)

| 文件 | 功能 |
|------|------|
| `web/js/proceed.js` | 继续节点按钮 + 分段执行逻辑 |
| `web/js/route.js` | 路由节点假输出分支真正执行:partial 提交时把 switch=false 的假输出分支下游输出节点并入 targets,保存本段并停止 |
| `web/js/preview-image.js` | 预览保存节点「保存」按钮 + format 联动位深/色彩空间 |
| `web/js/preview-video.js` | 视频预览节点「保存」按钮 |
| `web/js/preview-audio.js` | 音频预览节点「保存」按钮 |
| `web/js/table_lookup.js` | 表格 DOM 控件(Excel 网格 + 选择下拉 + 首列ID) |
| `web/js/md_table.js` | MarkDown 数据表 DOM 控件:系统选择器选文件 + 数据弹窗(搜索/分页/单选) + 按类型渲染表单 + 刷新 |
| `web/js/selector.js` | 选择器 `items` → 下拉选项实时联动,失配自动重置 |
| `web/js/switch.js` | 分组开关按 `total` 动态增删输入/输出端口 |
| `web/js/node_image_middleclick.js` | 节点图片**鼠标中键**全屏预览(单图居中,多图左右循环切换,与已生成预览同款布局) |
| `web/js/media_lightbox_zoom.js` | 图片灯箱缩放:滚轮/拖拽/双击/`+/−/0` 快捷键 |
| `web/js/assets_tab_rename.js` | 媒体资产面板「已导入」标签改为「已保存」 |
| `web/js/workflow_reload_button.js` | 运行面板"刷新工作流"按钮,磁盘重载当前工作流 |

---

## 节点详解

### 1. 继续节点 `FallingTSContinue`(分段执行)

**用途**:把工作流切成分段,逐段执行、逐段检查,不重复算已完成的段。

**原理(2026-08 重构,缓存式)**:
- 节点后端默认返回 **`ExecutionBlocker` 阻塞下游**;`any` 输入声明为 **lazy**,由 `check_lazy_status` 决定是否拉上游;
- **Run**(默认):前端 `POST /proceed/reset` 重置所有继续节点为阻塞并清缓存,再**全量提交**工作流 → 生成段执行,在第一个继续节点缓存并停下;
- 点「**继续**」:前端 `POST /proceed/continue/{id}` 放行该节点,再提交 `partial_execution_targets`(下一个继续之后的输出节点)→ 该继续已放行、`check_lazy_status` 返回 `[]` 不拉上游(**连线保留,上游不重跑**),从本节点起只跑新放行段,到下一个继续节点再停;
- 重复点「继续」逐段跑到底;
- 关键:「继续」**不依赖 ComfyUI 全局节点缓存**判断从哪跑 —— 靠 **lazy 门控**`check_lazy_status`(缓存无关,回溯时对 lazy 边根本不遍历) + 节点自身 `_data_cache`。

**工作流要求**:段与段之间的数据**只经继续节点传递**。若某段有绕过继续节点的**直连边**直取更上游节点的输出(如段 1 直接用段 0 的基图做 ColorMatch/对比),那部分上游仍会被执行列表回溯拉回重跑。解决:把这类直连边的源头改接到**继续节点下游**(如 #43 输出),让它也经过 lazy 门。

**与旧版的关键差异**:不再依赖"每个分段必须有输出节点"(旧版用 `partial_execution_targets` 收集段内输出节点,段内无预览/保存节点就会卡住)。现在纯靠 **`ExecutionBlocker` 门控 + 执行缓存**,任何结构都能分段。

**行为**:
1. Run → 执行到第一个继续节点暂停(节点显示「▶ 继续」按钮);
2. 点「继续」→ 放行本段,跑到下一个继续节点再停;
3. 想重头分段 → 再按 Run(重置所有继续为阻塞)。

**数据透传**:输入 `any` 原样输出到 `any`。

**HTTP 路由**(后端自动注册):
- `POST /proceed/continue/{node_id}` — 放行该节点
- `POST /proceed/reset` — 重置所有继续节点为阻塞
- `POST /proceed/restart/{node_id}` — 重跑令牌 +1 破除下游缓存,并回到阻塞

### 1.1 路由节点 `FallingTSRoute`(1 进 2 出)

**用途**:一个值按布尔开关路由到两路输出之一;**未选那路输出 `ExecutionBlocker`**,下游直接跳过不执行。

**输入**:
- `switch`(BOOLEAN,默认 true)
- `value`(ANY)

**输出**:
- `output_false` — switch=false 时输出 value,true 时为阻断
- `output_true` — switch=true 时输出 value,false 时为阻断

**行为**:
| switch | output_false | output_true |
|---|---|---|
| true | 阻断 | value |
| false | value | 阻断 |

**假输出分支真正执行(前端 route.js)**:分段执行(点「继续」)只跑 targets + targets 的上游祖先,而假输出分支的末端输出节点(保存等)不在其中,引擎不调度它。`web/js/route.js` 在 partial 提交时把 `switch=false` 的 route **假输出分支下游的输出节点并入 targets** —— 假输出后面接的保存/预览/对比节点都能真正执行并拿到数据;真输出分支本就是下一继续的上游、已被继续节点 targets 覆盖。

**典型用法**:继续节点后接路由,实现"false=保存本段并停止、true=继续下一段":
```
继续#N ─value→ FallingTSRoute ─output_false→ 保存图片(文件名用表格 ID)
        switch               └─output_true──→ 原下游(继续下一段)
```

### 2. 通用表格 `FallingTSTable`

**用途**:Excel 式表格,数据**内嵌工作流 JSON**(不读外部文件),按行输出各列字符串。

**输入**:仅 `rows`(`FALLINGTS_TABLE` DOM 控件)。**无独立行索引输入** —— 行选择由节点顶部「选择」下拉驱动。

**控件**(节点顶部一行):
- **选择** ▾:列出各行的选项 —— 开启「首列ID」时显示首列内容(如 `人物-陈落`),否则显示「第N行」;选中即写入 `selected_index`,下次 Run 输出该行;
- **行数 / 列数**:最少 1,改列数时右侧输出端口随之增减;
- **首列ID** ☑:开启后**第 0 列表头与输出端口命名为 `ID`**(其后 A/B/C...),选择下拉改用首列内容作标签。

**输出**:按列数动态生成 **ID/A/B/C...AZ(最多 52)** 的 STRING 端口,各端口输出选中行对应单元格字符串。

**特性**:
- 数据随工作流保存/加载完整还原;
- 单元格 textarea 按内容自动撑高,节点随之长高(只增不减,尊重手动调过的尺寸);
- 兼容旧版"行对象数组"数据(自动迁移为 A..E 五列网格);
- 类型转换由下游节点自行完成(如 `ComfyNumberConvert` 字符串转数值)。

### 2.1 MarkDown 数据表 `FallingTSMarkDownTable`

**用途**:把 md 文件里的一张数据表当作「数据库」:弹窗选一行 → 节点内按字段类型渲染**可编辑表单**,输出选中行的各字段值(按类型)。

**数据格式**(md 文件是唯一数据源,不随工作流保存):
- 含一张 GFM 表格(表头 + `---` 分隔行),取第一张;**第一列永远是 ID 列**,值为 str 中文字符串,常用 `-` 连接多段信息(如 `龙傲天-主角`);
- 表头格式 **`标题(类型)`**(括号内写类型;md 里 `[]` 是特殊语法,不用方括号),未标类型默认 `STRING`;支持类型:`IMAGE` / `VIDEO` / `AUDIO` / `STRING` / `INT` / `FLOAT` / `BOOLEAN` / `TEXT`(大小写不敏感,常见别名归一;`TEXT` 渲染为**多行文本框**且输出同为 STRING)。

**操作流程**:
1. **📁 选择md文件** — 后端 `tkinter` 弹**系统原生文件选择器**,节点记录绝对路径(路径框也可手动粘贴,headless 兜底);
2. **🗂 打开数据** — 内嵌 HTML 弹窗:顶部**各字段模糊搜索**、底部**分页**(每页 10/20/30/50/100 + 首页/上一页/下一页/尾页)、表格**无序号列、首列单选 radio**;
3. 选中一行后底部**确定**按钮由灰变**蓝**亮起,点击关闭弹窗,节点把该行数据载入表单;取消即关闭不生效;
4. 表单**竖向排列**各字段,按类型渲染控件(INT/FLOAT 数字输入、BOOLEAN 复选、TEXT 多行文本框**随内容自动撑高**、STRING 单行输入、IMAGE/VIDEO/AUDIO 路径输入 + 内嵌预览),可修改;
5. **🔄 刷新**(节点底部)— 按 ID 重新查询 md 文件,用磁盘最新值更新表单(md 文件被外部改动后同步)。

**输出**(动态端口,沿表格节点模式,未用槽不显示):
- `[0] ID`(STRING);
- `[1..]` 各非 ID 字段 — 按类型:`INT`/`FLOAT`/`BOOLEAN` 输出原生数值/布尔,`STRING`/`TEXT`/`IMAGE`/`VIDEO`/`AUDIO` 输出字符串(TEXT 可含换行,媒体为文件路径);
- 末位 `整行数据`(STRING)— 整行 `{id, values}` 的 JSON 字符串。

**示例 md**:
```markdown
| ID | 名称(STRING) | 头像(IMAGE) | 身高(FLOAT) | 启用(BOOLEAN) | 描述(TEXT) |
|----|-------------|-------------|-------------|--------------|-----------|
| 龙傲天-主角 | 龙傲天 | assets/avatar/lt.png | 180.5 | 是 | 主角,三视图 |
| 陈落-配角 | 陈落 | assets/avatar/cl.png | 165 | 否 | 配角,三视图 |
```

**HTTP 路由**(后端自动注册):
- `POST /fallingts_mdtable/select_file` — 弹系统文件选择器,返回绝对路径
- `GET /fallingts_mdtable/read?path=` — 解析 md,返回字段定义 + 全部数据行
- `GET /fallingts_mdtable/preview?path=` — 按绝对路径提供本地 image/video/audio 预览(支持 Range)

### 3. 下拉选择器 `FallingTSSelector`

- `items` 文本框(英文逗号分隔选项)实时联动下拉框;
- 输出选中项在列表中的**索引**(INT) + **选项文本**(STRING);
- 选中项不在列表时自动回退到第 0 项,不报错;
- 适合做"映射表路由":索引给下游,文本给人看/记录。

### 4. 分组开关 `FallingTSSwitch`

- 一个 `switch`(BOOLEAN)同时切换 **total 组**(最多 50 组);
- 每组 = `false_i` / `true_i`(ANY)两个输入 + `output_i`(ANY)一个输出;
- `switch` 为真 → 各组输出 `true_i`,为假 → 输出 `false_i`;
- 前端按 `total` 动态增删端口,未使用的端口不进入 prompt。

### 5. 视频预览 `PreviewVideo`(V3,带保存)

- 走 `IO.ComfyNode` V3 规范;
- 输入 `video` → 编码为 mp4 写入 **temp 临时目录**(非 output)→ 前端播放;
- 输入 `filename_prefix`(默认 `video`)→ 点「保存」按钮,后端用 execute 缓存的视频直接写 output(`{filename_prefix}.mp4`,同名覆盖、无 `_序号` 后缀),**不重跑工作流**;
- HTTP 路由:`POST /preview-video/save/{node_id}`(body: `filename_prefix` + `filename_prefix_linked`);
- 前端 `web/js/preview-video.js` 追加「保存」按钮;`filename_prefix` 可被上游连线(如 MDTable 的 ID 列),保存时用 execute 实际接收到的值。

### 6. 音频预览 `PreviewAudioSave`(V3,带保存)

- 走 `IO.ComfyNode` V3 规范;
- 输入 `audio` → 原生 `UI.PreviewAudio` 写 **temp 目录 flac** 供前端播放;
- 输入 `filename_prefix`(默认 `audio`) + `format`(flac/mp3/opus,含质量)→ 点「保存」按钮,后端用 execute 缓存的音频直接写 output(`{filename_prefix}.{format}`,同名覆盖、无 `_序号` 后缀),**不重跑工作流**;
- 多段波形时 `{prefix}_{i}`(仍无 5 位补零序号),`%batch_num%` 可替换;
- HTTP 路由:`POST /preview-audio/save/{node_id}`(body: `filename_prefix`/`filename_prefix_linked`/`format`/`quality`);
- 前端 `web/js/preview-audio.js` 追加「保存」按钮。

---

## 安装

### 方式 A:git clone 到 custom_nodes(推荐)

```bash
git clone https://github.com/falling-ts/ComfyUI-FallingTS.git ComfyUI/custom_nodes/ComfyUI-FallingTS
```

### 方式 B:仓库放项目根目录 + 相对软链接

```powershell
cd ComfyUI\custom_nodes
mklink /D ComfyUI-FallingTS ..\..\ComfyUI-FallingTS
```

安装后**重启 ComfyUI**(改代码后同样重启;改前端 web/js 后强刷浏览器即可)。

## 前置条件

- ComfyUI(dev 分支 / v0.29+,依赖 V3 扩展 API `comfy_api.latest`)
- **无额外 Python 依赖**(复用 ComfyUI 内置 `comfy_api_nodes.util`)

## 架构

```
ComfyUI-FallingTS/
├── __init__.py       # 入口:WEB_DIRECTORY + NODE_CLASS_MAPPINGS + sys.path
├── plugin.py         # 节点注册(V1 NODE_CLASS_MAPPINGS + V3 ComfyExtension,双轨)
├── proceed/          # 分段执行控制节点(阻塞/继续,缓存式)
│   ├── nodes.py      #   FallingTSContinue + HTTP 路由(continue/reset/restart)
│   └── __init__.py
├── route/            # 路由节点 (1 进 2 出)
│   ├── nodes.py      #   FallingTSRoute
│   └── __init__.py
├── table/            # 通用表格节点 (Excel 式)
│   ├── nodes.py      #   FallingTSTable(ID 首列 + 选择下拉, STRING 输出)
│   └── __init__.py
├── selector/         # 下拉选择器节点
│   └── nodes.py
├── mdtable/          # MarkDown 数据表超级节点
│   ├── nodes.py      #   FallingTSMarkDownTable + HTTP 路由(select_file/read/preview)
│   ├── parser.py     #   md 表格解析 + 值类型转换(纯函数, 可单测)
│   └── __init__.py
├── switch/           # 分组开关节点
│   ├── nodes.py
│   └── __init__.py
├── preview-video/    # 视频预览节点(预览+保存, V3; 目录名含连字符, 经 importlib 加载)
├── preview-audio/    # 音频预览节点(预览+保存, V3; 目录名含连字符, 经 importlib 加载)
│   ├── nodes.py
│   └── __init__.py
├── preview-image/    # 图片预览保存节点(始终预览 temp + 点「保存」写 output, 同名覆盖)
│   ├── nodes.py      #   PreviewImageSave + HTTP 路由(/preview-image/save)
│   └── __init__.py
├── web/js/           # 前端扩展(ComfyUI 经 /extensions 运行时加载,不参与前端打包)
├── locales/          # i18n 翻译(zh/nodeDefs.json, 节点与控件显示名)
└── README.md
```

**说明**:
- 插件 `web/js/*.js` 由 ComfyUI 的 `GET /extensions` 接口运行时加载,**不参与前端打包**;升级/重建前端打包目录不影响本插件;
- 节点注册双轨:V1 走 `NODE_CLASS_MAPPINGS`(4 个),V3 走 `DesktopPluginsExtension.get_node_list()`(`PreviewVideo`);
- 子包 `__init__.py` 使用相对导入,不依赖 sys.path 顺序。

## License

[MIT](LICENSE)
