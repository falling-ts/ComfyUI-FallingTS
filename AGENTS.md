# ComfyUI-FallingTS

我的 ComfyUI 自定义节点插件:通用工具节点集(Continue/Route/Selector/Table/Switch/MarkDown 数据表)+ 媒体预览保存节点(图片/视频/音频)+ 前端增强。位于 `custom_nodes\ComfyUI-FallingTS`,经根 `custom_nodes` 目录级软链接被 ComfyUI 加载。

## 项目目录结构

```
ComfyUI-FallingTS/
├── plugin.py                   # 插件入口:V1 节点注册表 (NODE_CLASS_MAPPINGS, 11 节点) + V3 ComfyExtension (DesktopPluginsExtension)
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
│   └── nodes.py                # FallingTSRouteNode 路由节点 (1进2出)
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
├── preview-image/
│   ├── __init__.py
│   └── nodes.py                # PreviewImageSaveNode 图片预览保存
├── preview-video/
│   ├── __init__.py
│   └── nodes.py                # PreviewVideoNode 视频预览保存
├── preview-audio/
│   ├── __init__.py
│   └── nodes.py                # PreviewAudioSaveNode 音频预览保存
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
        ├── preview-video.js            # PreviewVideo 底部保存按钮
        ├── preview-audio.js            # PreviewAudioSave 底部保存按钮
        ├── proceed.js                  # 继续节点前端 (节点缓存 + partial execution)
        ├── route.js                    # 路由节点「假输出」分支真正执行
        ├── selector.js                 # 多对一选择: items 展开输入端口 + 下拉联动
        ├── switch.js                   # 分组开关前端联动
        ├── table_lookup.js             # 通用表格 Excel 式控件
        └── workflow_reload_button.js   # 刷新工作流按钮
```

## 节点一览

| 包 | 节点 | 说明 |
|------|------|------|
| proceed | FallingTSContinue | 继续节点 |
| route | FallingTSRoute | 路由节点 (1进2出) |
| selector | FallingTSSelector | 多对一选择 (通用 ANY: items 展开输入端口且标签为实际项内容, 下拉选或输入组号(0 起, 可连上游 INT, -1 = 用下拉)切第几组, 就从右侧输出该组(selected_value/selected/index 三输出)) |
| table | FallingTSTable | 通用表格 (Excel 式) |
| switch | FallingTSSwitch | 分组开关 (total组) |
| mdtable | FallingTSMarkDownTable | MarkDown 数据表 |
| preview-image | PreviewImageSave | 图片预览保存 |
| preview-video | PreviewVideo | 视频预览保存 |
| preview-audio | PreviewAudioSave | 音频预览保存 |

注:`preview-image` / `preview-video` / `preview-audio` 目录名含连字符,不能直接 `from xxx import`,入口经 `importlib` 按名加载。

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
