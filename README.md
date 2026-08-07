# ComfyUI-FallingTS

ComfyUI 自定义节点插件:一组**通用工具节点** + **前端增强**。

## 功能

### 工具节点

| 节点 | Node ID | 功能 |
|------|---------|------|
| FallingTS 继续节点 | `FallingTSContinue` | 工作流分段执行控制:暂停 →「继续」放行 /「重跑」从中断点重跑下游 |
| FallingTS 下拉选择器 | `FallingTSSelector` | 文本+下拉:逗号分隔选项实时更新下拉,选中项输出索引(INT) + 选项文本(STRING) |
| FallingTS 分组开关 | `FallingTSSwitch` | 参考官方切换:一个 switch 布尔同时控制 total 组(每组 为假时/为真时 → 输出,ANY),total 最少 1 |
| FallingTS 通用表格 | `FallingTSTable` | Excel 式通用表格(数据内嵌工作流):最左索引列 + A/B/C... 列,输入行索引输出该行各列字符串(STRING),行数/列数可调,输出端口随列数增减;格子按内容自动撑高,节点随之长高 |
| Preview Video | `PreviewVideo` | 视频预览(不保存) |

### Web 前端增强(安装即用,无需配置)

| 文件 | 功能 |
|------|------|
| `web/js/node_image_middleclick.js` | 节点图片中键全屏预览(多图左右循环切换) |
| `web/js/media_lightbox_zoom.js` | 图片灯箱缩放查看 |
| `web/js/assets_tab_rename.js` | 资源标签页重命名 |
| `web/js/workflow_reload_button.js` | 工作流刷新按钮 |
| `web/js/proceed.js` | 继续节点的按钮与重跑逻辑 |

### 分段执行(FallingTS 继续节点)

在任意节点之后插入「FallingTS 继续节点」即可把工作流分成多段:

1. 运行到该节点时自动暂停(节点变黄色,出现按钮);
2. **▶ 继续**:放行当前运行,继续往后执行;
3. **↻ 重跑(从本节点)**:先中断当前(下游)运行,再从本节点重新执行下游;
4. 支持反复继续:每次执行到该节点都会再次暂停。

数据透传(输入 `data` 原样输出)。

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

安装后**重启 ComfyUI**。

## 前置条件

- ComfyUI(dev 分支 / v0.29+,依赖 V3 扩展 API `comfy_api.latest`)
- **无额外 Python 依赖**(复用 ComfyUI 内置 `comfy_api_nodes.util`)

## 架构

```
ComfyUI-FallingTS/
├── __init__.py       # 入口:WEB_DIRECTORY + NODE_CLASS_MAPPINGS
├── plugin.py         # 节点注册(V1 映射 + V3 ComfyExtension)
├── proceed/          # 分段执行控制节点(暂停/继续/重跑)
│   ├── nodes.py      #   FallingTSContinue 节点 + HTTP 路由
│   └── __init__.py
├── combo/            # 通用表格节点 (Excel 式)
│   ├── nodes.py      #   FallingTSTable 节点 (A/B/C... 列, STRING 输出)
│   └── __init__.py
├── selector/         # 下拉选择器节点
│   └── nodes.py
├── switch/           # 分组开关节点
│   ├── nodes.py
│   └── __init__.py
├── previewvideo/     # 视频预览节点(不保存)
│   ├── nodes.py
│   └── __init__.py
├── web/js/           # 前端扩展(ComfyUI 自动加载)
├── locales/          # i18n 翻译(zh/nodeDefs.json, 节点与控件显示名)
└── README.md
```

## License

[MIT](LICENSE)
