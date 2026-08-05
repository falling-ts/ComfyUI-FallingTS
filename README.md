# ComfyUI-FallingTS

ComfyUI 自定义节点插件:通过**火山引擎(Volcengine)ARK API** 接入 **Seedance 2.0** 视频生成,并附带一组 ComfyUI 前端增强工具。

## 功能

### 视频生成节点(需 Volcengine API)

| 节点 | Node ID | 功能 |
|------|---------|------|
| Seedance 2.0 首尾帧生视频 | `Seedance2FirstLastFrame` | 首帧/尾帧图片 + 文本提示词,生成过渡视频 |
| Seedance 2.0 多模态参考生视频 | `Seedance2Reference` | 多张参考图 + 文本提示词,生成视频 |
| FallingTS 继续节点 | `FallingTSContinue` | 工作流分段执行控制:暂停 →「继续」放行 /「重跑」从中断点重跑下游(无需 API) |
| FallingTS 下拉选择器 | `FallingTSSelector` | 文本+下拉:逗号分隔选项实时更新下拉,选中项输出索引(INT) + 选项文本(STRING) |
| FallingTS 分组开关 | `FallingTSSwitch` | 参考官方切换:一个 switch 布尔同时控制 total 组(每组 为假时/为真时 → 输出,ANY),total 最少 1 |
| FallingTS 通用表格 | `FallingTSTable` | Excel 式通用表格(数据内嵌工作流):最左索引列 + A/B/C... 列,输入行索引输出该行各列字符串(STRING),行数/列数可调,输出端口随列数增减;格子按内容自动撑高,节点随之长高 |

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

数据透传(输入 `data` 原样输出),不依赖 Volcengine API。

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

## 初始化(下载后必做)

1. **开通 Seedance 2.0 服务**:https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement
2. **获取 API Key**:https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey
3. **配置环境变量**:复制 `.env.example` 为 `.env`(放在插件根目录),填入你的 Key:

   ```ini
   SEEDANCE_API_KEY=你的APIKey
   ```

   - 支持 `.env` 文件或系统环境变量两种方式,环境变量优先级更高
   - 可选配置:`SEEDANCE_MODEL_ID` / `SEEDANCE_MODEL_NAME` 覆盖默认模型
4. **重启 ComfyUI**,在节点列表搜索 `Seedance` 即可使用

## 前置条件

- ComfyUI(dev 分支 / v0.29+,依赖 V3 扩展 API `comfy_api.latest`)
- 火山引擎账号:账户余额 > 200 元或已购买资源包
- **无额外 Python 依赖**(复用 ComfyUI 内置 `comfy_api_nodes.util`)

## 架构

```
ComfyUI-FallingTS/
├── __init__.py       # 入口:WEB_DIRECTORY + NODE_CLASS_MAPPINGS
├── plugin.py         # 节点注册(V1 映射 + V3 ComfyExtension)
├── config.py         # .env 配置管理(纯 Python,无依赖)
├── proceed/              # 分段执行控制节点(暂停/继续/重跑)
│   ├── nodes.py          #   FallingTSContinue 节点 + HTTP 路由
│   └── __init__.py
├── combo/                # 通用表格节点 (Excel 式)
│   ├── nodes.py          #   FallingTSTable 节点 (A/B/C... 列, STRING 输出)
│   └── __init__.py
├── seedance/         # Seedance 2.0 视频生成
│   ├── nodes.py      #   节点定义(2 个)
│   ├── api.py        #   Volcengine HTTP 客户端
│   └── models.py     #   数据模型 + 定价
├── web/js/           # 前端扩展(ComfyUI 自动加载)
├── locales/          # i18n 翻译(zh/nodeDefs.json, 节点与控件显示名)
├── .env.example      # 环境配置模板
└── README.md
```

## License

[MIT](LICENSE)
