/**
 * AutoSaveImage 前端: 格式联动 + 刷新后重建图片预览 + 提交时注入当前工作流名。
 *
 * 与 preview-image.js 的分工: 本节点**没有「保存」按钮**(后端 execute 里已把图片写进 output),
 * 所以不复制那套按钮样式与点击逻辑; 预览回填复用 preview-image 的同一条路由
 * `GET /preview-image/image-url/{id}`(两者共用后端同一份 _last_ui 缓存, 键口径也相同),
 * 故本文件不改动 preview-image.js。
 *
 * 唯一的前端专属职责是**工作流名注入**: 自动保存发生在后端 execute 里, 那时没有按钮可问前端,
 * 工作流名只能随 prompt 一起送进后端 —— 这里包装 `api.fetchApi` 的 POST /prompt 分支, 把当前
 * 工作流名写进 `extra_pnginfo.workflow.extra.fallingts_workflow_name`(键名与后端
 * `auto-save-image/nodes.py` 的 WORKFLOW_NAME_EXTRA_KEY 一致)。
 *
 * 注入点为什么选 api.fetchApi 而不是 api.queuePrompt: 插件里「截帧/完成/继续/扇出」这些 partial
 * 提交是直接 fetch("/prompt") 的, 包装 queuePrompt 会漏掉它们; 也不能包装 app.graphToPrompt()
 * —— 保存/导出工作流同样走它, 工作流名会被写进存档的 workflow JSON。
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_CLASS = "AutoSaveImage";
// 与后端 auto-save-image/nodes.py 的 WORKFLOW_NAME_EXTRA_KEY 一致
const WORKFLOW_NAME_EXTRA_KEY = "fallingts_workflow_name";

/**
 * 取当前工作流的名字, 用于让后端把产物写进 output 下的同名子目录。
 * 前端各版本存放位置不一, 逐级兜底; 取不到返回空串, 后端退回 output 根
 * (工作流里有 md 数据表节点时后端优先用表文件名, 与这里取不取得到无关)。
 *
 * @returns {string} 工作流名(已去掉 .json 后缀); 取不到时为空串
 */
function currentWorkflowName() {
  try {
    // 新版前端把工作流挂在 extensionManager.workflow, 旧版在 app.workflowManager; 两者都探
    const store = app?.extensionManager?.workflow ?? app?.workflowManager;
    const wf = store?.activeWorkflow;
    const raw = wf?.name || wf?.filename || wf?.path || "";
    return String(raw).replace(/\.json$/i, "");
  } catch {
    return "";
  }
}

/**
 * 取当前工作流的根 id(= 工作流 JSON 的根 id, 即 graph.serialize().id)。
 *
 * 后端用它给预览缓存加作用域 —— 只按节点 id 缓存会让各工作流之间同 id 的节点互相串图。
 * 后端 execute 时从 extra_pnginfo.workflow.id 取到的是同一个值。
 *
 * @returns {string} 工作流根 id; 取不到时为空串(后端退回纯节点 id)
 */
function currentWorkflowId() {
  try {
    // 必须取根图: 前端 graphToPrompt() 默认序列化 rootGraph; 取子图(node.graph)会拿到别的 id
    const g = app?.rootGraph ?? app?.graph;
    if (!g) return "";
    return String(g.id || g.serialize?.()?.id || "");
  } catch {
    return "";
  }
}

// 各格式合法的 位深 / 色彩空间(与后端 _encode_image 支持的组合一致)
const FORMAT_OPTIONS = {
  png: { bit_depth: ["8-bit", "16-bit"], colorspace: ["sRGB"] },
  exr: { bit_depth: ["16-bit float", "32-bit float"], colorspace: ["sRGB", "HDR", "HDR PQ", "linear", "HDR LogC3", "HDR ACEScct"] },
};

/**
 * 按 format 联动 bit_depth / input_color_space 的合法选项;
 * 当前选中值不在新选项里时自动重置为第一项。
 *
 * @param {LGraphNode} node 节点对象
 * @returns {void}
 */
function syncFormatDependentWidgets(node) {
  const fmt = node.widgets?.find((x) => x.name === "format")?.value ?? "png";
  const opts = FORMAT_OPTIONS[fmt] ?? FORMAT_OPTIONS.png;
  const applyTo = (name, values) => {
    const w = node.widgets?.find((x) => x.name === name);
    if (!w) return;
    w.options = { ...(w.options || {}), values: () => [...values] };
    if (!values.includes(w.value)) {
      w.value = values[0];
      w.callback?.(w.value);
    }
  };
  applyTo("bit_depth", opts.bit_depth);
  applyTo("input_color_space", opts.colorspace);
  node.setDirtyCanvas(true, true);
}

/**
 * 创建备用图片预览 widget(仅在原生预览缺失时显示)。
 *
 * 原生 UI.PreviewImage 是一次性 WebSocket 事件, 页面刷新后不会重发, 预览区就空了。
 * 这个备用 <img> 由 restoreImages() 从 /preview-image/image-url 拉 URL 填上; 若节点上已有
 * ComfyUI 渲染的原生 <img>, 则隐藏它以免出现"两个图片"。
 *
 * @param {LGraphNode} node 节点
 * @returns {object} widget
 */
function createImageFallbackWidget(node) {
  const root = document.createElement("div");
  root.style.cssText = "width:100%;box-sizing:border-box;padding:0 4px;display:none;";

  const imgEl = document.createElement("img");
  imgEl.style.cssText =
    "display:block;width:100%;max-height:320px;object-fit:contain;background:#111;border-radius:6px;";

  root.appendChild(imgEl);

  const widget = node.addDOMWidget("image_fallback", "image", root, {
    serialize: false,
    hideOnZoom: false,
    getValue: () => "",
    setValue: () => {},
  });
  widget.computeSize = (width) => [width, 0];
  widget.element = root;
  widget.imgEl = imgEl;
  return widget;
}

/**
 * 刷新后重建图片预览: 拉回 URL 并填到原生 <img>, 原生不存在时改用备用 <img>。
 *
 * 请求必须带 workflow_id —— 后端缓存按 (工作流根 id, 节点 id) 索引, 不带就只能按节点 id 查,
 * 会把别的工作流留下的同 id 节点预览拉回来当成这个节点的预览(遗留预览)。
 *
 * @param {LGraphNode} node 节点
 * @returns {Promise<void>} 无
 */
async function restoreImages(node) {
  const fb = node._fallingtsImageFallback;
  let urls = [];
  try {
    const wid = encodeURIComponent(currentWorkflowId());
    const r = await fetch(`/preview-image/image-url/${node.id}?workflow_id=${wid}`);
    const j = await r.json().catch(() => null);
    if (r.ok && j?.status === "ok") urls = j.urls || [];
  } catch {
    /* 后端未就绪时忽略 */
  }
  if (!urls.length) {
    if (fb) fb.element.style.display = "none";
    return;
  }

  // 节点内已有的原生 <img>(排除备用自己)
  const host = document.querySelector(`[data-node-id="${node.id}"]`);
  const nativeImgs = host
    ? [...host.querySelectorAll("img")].filter((im) => !(fb?.element?.contains(im) ?? false))
    : [];

  if (nativeImgs.length) {
    nativeImgs.forEach((im, i) => {
      if (urls[i] && im.dataset.src !== urls[i]) {
        im.dataset.src = urls[i];
        im.src = urls[i];
      }
    });
    if (fb) fb.element.style.display = "none";
    return;
  }

  if (fb) {
    fb.element.style.display = "";
    const first = urls[0];
    if (fb.imgEl.dataset.src !== first) {
      fb.imgEl.dataset.src = first;
      fb.imgEl.src = first;
    }
  }
}

/**
 * 包装 api.fetchApi: POST /prompt 时把当前工作流名注入 extra_pnginfo, 供自动保存解析产物子目录。
 *
 * 只在画布上确实有 AutoSaveImage 节点时注入(免得给别的提交平添一个键); 注入的是本次
 * graphToPrompt() 刚序列化出来的 workflow 副本, 只影响这次提交、不落盘。任何异常都不拦提交 ——
 * 注入失败只是退回"没有工作流名", 后端会退到 output 根。
 *
 * @returns {void} 无
 */
function installWorkflowNameInjection() {
  if (window.__fallingtsAutoSaveWfInjection) return;
  window.__fallingtsAutoSaveWfInjection = true;
  const orig = api.fetchApi?.bind(api);
  if (!orig) return;

  api.fetchApi = function (url, options) {
    try {
      const isSubmit =
        String(url) === "/prompt" &&
        options?.method === "POST" &&
        typeof options.body === "string" &&
        (app.graph?._nodes || []).some((n) => n?.type === NODE_CLASS);
      if (isSubmit) {
        const body = JSON.parse(options.body);
        const wf = body?.extra_data?.extra_pnginfo?.workflow;
        const name = currentWorkflowName();
        if (wf && name) {
          wf.extra = wf.extra || {};
          wf.extra[WORKFLOW_NAME_EXTRA_KEY] = name;
          options = { ...options, body: JSON.stringify(body) };
        }
      }
    } catch {
      /* 注入失败不拦提交 */
    }
    return orig(url, options);
  };
}

app.registerExtension({
  name: "FallingTS.AutoSaveImage",

  /**
   * 扩展初始化: 跑完流程后重新判定一次「备用图要不要显示」。
   *
   * 原生预览是收到 executed 后才由 Vue 异步挂载的, 比 onConfigure 晚; restoreImages 只在
   * onConfigure 跑一次, 那时节点 DOM 往往还没挂出来 → 判定"没有原生 <img>" → 显示备用图;
   * 此后没有任何时机再收它, 跑完流程就成了两个图片(备用在上 + 原生在下)。这里在
   * executed / execution_success 后按 600ms / 2.5s 两拍各重跑一次, 原生一出现就把备用收起。
   * 只挂这两个低频事件(不挂 progress —— 每采样步都发, 会变成高频轮询)。
   *
   * @returns {void} 无
   */
  setup() {
    installWorkflowNameInjection();

    const timers = [];
    /**
     * 安排两拍重扫: 清掉上一轮未触发的定时器, 再排 600ms / 2.5s 两拍。
     *
     * @returns {void} 无
     */
    const refresh = () => {
      timers.splice(0).forEach(clearTimeout);
      /**
       * 对画布上每个 AutoSaveImage 节点重跑一次 restoreImages。
       *
       * @returns {void} 无
       */
      const run = () => {
        for (const n of app.graph?._nodes || []) {
          if (n.type === NODE_CLASS) restoreImages(n);
        }
      };
      timers.push(setTimeout(run, 600), setTimeout(run, 2500));
    };
    api.addEventListener("executed", refresh);
    api.addEventListener("execution_success", refresh);
  },

  /**
   * 节点定义注册前钩子: 给 AutoSaveImage 绑定 format 联动 + 备用预览容器。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 包装 format callback 做选项联动, 建备用预览容器。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      const fmtWidget = node.widgets?.find((w) => w.name === "format");
      if (fmtWidget) {
        const cb = fmtWidget.callback;
        /** format 变化回调: 同步位深/色彩空间合法选项。 */
        fmtWidget.callback = function (v) {
          cb?.call(this, v);
          syncFormatDependentWidgets(node);
        };
      }

      syncFormatDependentWidgets(node);

      // 备用图片预览: 页面刷新后原生 UI.PreviewImage 不重发, 由 restoreImages 补上
      node._fallingtsImageFallback = createImageFallbackWidget(node);

      const prevOnConfigure = node.onConfigure;
      /**
       * 加载钩子: 后端是唯一事实来源 —— 从它读回预览图并重建前端(刷新不丢)。
       *
       * @param {object} info 节点序列化数据
       * @returns {*} 原 onConfigure 的返回值
       */
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        restoreImages(node);
      };
    };
  },
});
