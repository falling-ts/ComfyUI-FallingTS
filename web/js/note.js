/**
 * FallingTS 笔记节点前端 —— 官方 Markdown Note 的可复制版。
 *
 * ## 做了什么
 *
 * 1. **官方同款 markdown 渲染**: 用 `ComfyWidgets.MARKDOWN` 给节点加文本控件,
 *    与官方 `MarkdownNoteNode` 完全同一套(tiptap 富文本, 支持标题/表格/代码块)。
 * 2. **标记为虚拟节点**: 设 `isVirtualNode = true`, 于是 `graphToPrompt()` 里
 *    的 `if (e.isVirtualNode) continue` 会跳过本节点 —— 不进 prompt、不参与执行、
 *    不占校验, 行为与官方 Note 一致(后端注册只是为了 `/object_info` 有定义,
 *    让节点面板能搜到、存档不报缺失)。
 * 3. **右上角复制按钮**: 点一下把**整段 markdown 源码(原文, 不是渲染后的富文本)**
 *    写进剪贴板。
 *
 * ## 复制到"访问服务的电脑"
 *
 * 按钮由前端点击, 写的是**浏览器所在电脑**的剪贴板, 也就是发起访问的那台,
 * 不是跑 ComfyUI 的服务器 —— 天然满足这个诉求, 不需要后端参与。
 *
 * ⚠️ 但剪贴板 API 有条件: `navigator.clipboard` **只在 secure context 存在**。
 * 用 `http://127.0.0.1:8188` 访问时算 secure context, 有;
 * 用局域网 `http://192.168.100.4:8188` 访问时**没有**(http 非 localhost),
 * `navigator.clipboard` 是 undefined。所以这里留了 `execCommand` 回退通道,
 * 否则局域网那台电脑点按钮会静默失败。
 *
 * ## ⚠️ 为什么按钮走 DOM 注入而不是 canvas 绘制
 *
 * 本机开了 Vue 节点渲染(`Comfy.VueNodes.Enabled = true`)。实测结论:
 * **`onDrawForeground` 在这个模式下一次都不会被调用**(挂上计数器跑 3 秒, 计数恒为 0),
 * 节点是 Vue 组件渲染的 DOM(`div[data-node-id]`), 不再是 canvas 上画的方块。
 * 所以按钮只能往 DOM 里塞。
 *
 * 插入点选在标题栏的 `.justify-between` 行: 实测该行**只有左侧一个子元素**
 * (折叠按钮 + 标题, 带 `mr-auto`), 右侧是空的 —— 追加第二个子元素就自动靠右,
 * 正好是"右上角", 也不用调 z-index 或绝对定位去和节点拖拽抢事件。
 *
 * canvas 模式的绘制代码保留着(见 drawCopyButton), 供关掉 Vue 节点渲染时兜底。
 */

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "FallingTSNote";

/** 官方 Note 的配色(柠檬黄), 与官方 Note/MarkdownNote 视觉一致 */
const NOTE_COLORS = { color: "#432", bgcolor: "#653" };

/** canvas 模式: 复制按钮的边长与内边距(像素, 画布坐标) */
const BTN_SIZE = 18;
const BTN_PAD = 4;

/**
 * 取全局 LiteGraph(前端把核心挂在 window 上, 新版可能是 window.LiteGraph)。
 *
 * @returns {object|null} LiteGraph 命名空间; 拿不到返回 null
 */
function getLiteGraph() {
  return window.LiteGraph ?? window.comfyAPI?.liteGraph?.LiteGraph ?? null;
}

/**
 * 取前端 ComfyWidgets 表(含官方 MARKDOWN 控件构造器)。
 *
 * @returns {object|null} ComfyWidgets; 拿不到返回 null
 */
function getComfyWidgets() {
  return window.comfyAPI?.widgets?.ComfyWidgets ?? null;
}

/**
 * 读取节点上的 markdown 原文。
 *
 * Vue 节点模式下值的权威来源是 widget 的 `value`(Vue 的 WidgetMarkdown 组件用
 * `modelValue` 双向绑定它), 拿不到再退回 `properties.text`(官方 Note 的初始位置)。
 *
 * @param {LGraphNode} node 笔记节点
 * @returns {string} markdown 原文; 空节点返回空串
 */
function readNoteText(node) {
  const w = node.widgets?.find((x) => x.name === "text");
  if (w && typeof w.value === "string") return w.value;
  if (typeof node.properties?.text === "string") return node.properties.text;
  return "";
}

/**
 * 把文本写进浏览器所在电脑的剪贴板。
 *
 * 两条通道, 按可靠性依次尝试:
 * 1. `navigator.clipboard.writeText` —— 现代通道, 但**只在 secure context 存在**
 *    (localhost / 127.0.0.1 / https); 局域网 http 访问时压根没有这个对象。
 * 2. `document.execCommand('copy')` —— 老通道, 不受 secure context 限制。
 *    做法是临时插一个不在视口内(但**不能 display:none**, 否则选不中)的
 *    textarea, 选中内容后执行复制, 最后移除。
 *
 * @param {string} text 要复制的文本
 * @returns {Promise<boolean>} 复制成功返回 true
 */
async function copyToClipboard(text) {
  // 1. 现代通道(secure context 才有)
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* 权限被拒/窗口非聚焦等, 落到老通道 */
    }
  }

  // 2. 老通道: 临时 textarea + execCommand
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    // 必须是"可选中"的元素: 移到视口外, 但不能 display:none / visibility:hidden
    ta.setAttribute("readonly", "");
    ta.style.cssText =
      "position:fixed;top:0;left:-9999px;width:1px;height:1px;opacity:0;";
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch {
    return false;
  }
}

/**
 * 弹一条前端 toast(优先用官方 extensionManager, 拿不到退回 console)。
 *
 * @param {string} summary 提示文案
 * @param {"success"|"error"|"info"} severity 级别
 * @returns {void}
 */
function toast(summary, severity) {
  try {
    const t = app.extensionManager?.toast;
    if (t?.add) {
      t.add({ severity, summary, life: 2000 });
      return;
    }
  } catch {
    /* 忽略 */
  }
  console.log("[FallingTS.Note]", severity, summary);
}

/**
 * 给按钮一个短暂的"已复制"视觉反馈(换成对勾图标 + 绿色)。
 *
 * @param {HTMLButtonElement} btn 复制按钮
 * @returns {void}
 */
function flashButton(btn) {
  if (!btn) return;
  const icon = btn.querySelector("i");
  if (!icon) return;
  const original = icon.className;
  icon.className = "icon-[lucide--check] size-4 text-green-400";
  btn.disabled = true;
  setTimeout(() => {
    icon.className = original;
    btn.disabled = false;
  }, 900);
}

/**
 * 执行一次复制(Vue DOM 按钮与 canvas 点击共用)。
 *
 * @param {LGraphNode} node 笔记节点
 * @param {HTMLButtonElement} [btn] Vue 模式下的按钮, 用于给视觉反馈
 * @returns {Promise<void>} 无
 */
async function doCopy(node, btn) {
  const text = readNoteText(node);
  if (!text) {
    toast("笔记是空的, 没有可复制的内容", "info");
    return;
  }
  const ok = await copyToClipboard(text);
  if (ok) {
    flashButton(btn);
    const lines = text.split("\n").length;
    toast(`已复制 ${text.length} 字符 / ${lines} 行到剪贴板`, "success");
  } else {
    toast("复制失败: 浏览器拒绝了剪贴板访问", "error");
  }
}

// ─────────────────────────── Vue 节点模式: DOM 注入 ───────────────────────────

/**
 * 复制按钮的样式(复用节点标题栏按钮的观感, 尺寸与官方图标按钮一致)。
 *
 * 直接写内联样式而不是依赖 tailwind 类名: 类名随前端版本变化, 内联样式不会。
 *
 * ⚠️ `position:relative + z-index` 不是可有可无的装饰 —— 它是按钮"能点"的前提。
 * 节点四角各有一个透明(`opacity-0`)、`pointer-events-auto`、20×20 的**缩放把手**
 * (`div.absolute.h-5.w-5`), 其中右上角那个正好压在标题栏右端。把手是节点(host)
 * 的直接子元素且排在标题栏**之后**, 同层级下后出现的赢 → 实测真实鼠标点击
 * 全部被把手吃掉(`elementFromPoint` 返回的是把手, 按钮一个事件都收不到;
 * 而程序化的 `btn.click()` 走不到命中测试, 所以看起来是好的)。
 * 抬 z-index 让按钮在把手之上, 点击才落得到按钮上。
 *
 * @returns {string} cssText
 */
function buttonStyle() {
  return [
    "display:inline-flex",
    "align-items:center",
    "justify-content:center",
    "width:20px",
    "height:20px",
    "padding:0",
    "margin-left:4px",
    "border:none",
    "background:transparent",
    "border-radius:4px",
    "cursor:pointer",
    "color:inherit",
    "opacity:.65",
    "transition:opacity .15s, background .15s",
    "flex:0 0 auto",
    // 盖过四角的透明缩放把手(见上方说明)
    "position:relative",
    "z-index:20",
    // 不要参与节点拖拽的手势, 也不要在缩小时被挤没
    "touch-action:manipulation",
  ].join(";");
}

/**
 * 把复制按钮注入到节点标题栏右侧(Vue 节点模式)。
 *
 * 插入点: `.lg-node-header .justify-between` —— 实测这一行只有左侧那个带 `mr-auto`
 * 的子元素(折叠按钮 + 标题), 追加第二个即自动靠右, 正是右上角。
 *
 * 幂等: 已经注入过(节点上记着按钮且仍在文档里)就直接返回。
 *
 * @param {LGraphNode} node 笔记节点
 * @returns {boolean} 注入成功(或已注入)返回 true
 */
function injectCopyButton(node) {
  if (!node) return false;
  // 已注入且仍挂在页面上
  if (node._fallingtsNoteBtn?.isConnected) return true;

  const host = document.querySelector(`[data-node-id="${node.id}"]`);
  if (!host) return false;
  const header = host.querySelector(".lg-node-header");
  if (!header) return false;
  const row = header.querySelector(".justify-between") ?? header;

  // 防止重复(节点重渲染后旧按钮会被 Vue 丢掉, 这里按标记类兜住并发注入)
  if (row.querySelector(".fallingts-note-copy")) {
    node._fallingtsNoteBtn = row.querySelector(".fallingts-note-copy");
    return true;
  }

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "fallingts-note-copy";
  btn.style.cssText = buttonStyle();
  btn.title = "复制 Markdown 原文到本机剪贴板";
  btn.setAttribute("aria-label", btn.title);
  // 用 lucide 的 copy 图标(前端已内置 lucide 图标集, 本项目其它脚本也这么用)
  btn.innerHTML = '<i class="icon-[lucide--copy] size-4 leading-none"></i>';

  // 悬停提亮
  btn.addEventListener("mouseenter", () => {
    btn.style.opacity = "1";
    btn.style.background = "rgba(255,255,255,.18)";
  });
  btn.addEventListener("mouseleave", () => {
    btn.style.opacity = ".65";
    btn.style.background = "transparent";
  });

  // 点一下复制。
  // ⚠️ pointerdown 必须吞掉: 标题栏是节点拖拽的启动区域, 不拦的话按下时
  // 一移动就把节点拖走了, 按钮的 click 反而可能不触发。
  btn.addEventListener("pointerdown", (e) => {
    e.stopPropagation();
    e.preventDefault();
  });
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
    doCopy(node, btn);
  });

  row.appendChild(btn);
  node._fallingtsNoteBtn = btn;
  return true;
}

/**
 * 拆掉已注入的按钮(节点删除时清理, 避免留下游离 DOM)。
 *
 * @param {LGraphNode} node 笔记节点
 * @returns {void}
 */
function removeCopyButton(node) {
  try {
    node?._fallingtsNoteBtn?.remove();
  } catch {
    /* 忽略 */
  }
  if (node) node._fallingtsNoteBtn = null;
}

/**
 * 遍历画布上全部笔记节点, 补注入复制按钮(幂等, 供 MutationObserver 反复调用)。
 *
 * 两处节点表都要扫: `app.graph` 是当前打开的图, `app.rootGraph` 是根图;
 * 在子图(subgraph)里编辑时两者不是同一个, 子图内的笔记节点只在 app.graph 里。
 * ⚠️ 不能用 `a?._nodes ?? b?._nodes` —— 前者是**空数组**时 `??` 不会回退到后者,
 * 正好漏掉"当前图空、根图有节点"的情形。
 *
 * @returns {void}
 */
function sweepInject() {
  const seen = new Set();
  for (const g of [app.graph, app.rootGraph]) {
    for (const n of g?._nodes ?? []) {
      if (n?.type !== NODE_CLASS || seen.has(n.id)) continue;
      seen.add(n.id);
      injectCopyButton(n);
    }
  }
}

// ─────────────────────────── canvas 模式: 绘制回退 ───────────────────────────

/**
 * 按钮在节点内的矩形(画布坐标系, 以节点左上角为原点)。
 *
 * @param {LGraphNode} node 笔记节点
 * @returns {{x:number,y:number,w:number,h:number}} 矩形
 */
function buttonRect(node) {
  const w = Array.isArray(node.size) ? node.size[0] : 200;
  return { x: w - BTN_SIZE - BTN_PAD, y: BTN_PAD, w: BTN_SIZE, h: BTN_SIZE };
}

/**
 * 判断画布坐标是否落在复制按钮上。
 *
 * @param {LGraphNode} node 笔记节点
 * @param {number[]} pos 画布绝对坐标 [x, y]
 * @returns {boolean} 命中返回 true
 */
function hitButton(node, pos) {
  if (!pos) return false;
  const r = buttonRect(node);
  const lx = pos[0] - node.pos[0];
  const ly = pos[1] - node.pos[1];
  return lx >= r.x && lx <= r.x + r.w && ly >= r.y && ly <= r.y + r.h;
}

/**
 * 在节点右上角画复制按钮(canvas 模式专用, 仅在关掉 Vue 节点渲染时生效)。
 *
 * @param {CanvasRenderingContext2D} ctx 画布上下文
 * @param {LGraphNode} node 笔记节点
 * @returns {void}
 */
function drawCopyButton(ctx, node) {
  const r = buttonRect(node);
  const hovering = node._fallingtsNoteHover === true;
  ctx.save();
  ctx.fillStyle = hovering ? "rgba(255,255,255,.28)" : "rgba(0,0,0,.28)";
  ctx.beginPath();
  const rad = 4;
  ctx.moveTo(r.x + rad, r.y);
  ctx.arcTo(r.x + r.w, r.y, r.x + r.w, r.y + r.h, rad);
  ctx.arcTo(r.x + r.w, r.y + r.h, r.x, r.y + r.h, rad);
  ctx.arcTo(r.x, r.y + r.h, r.x, r.y, rad);
  ctx.arcTo(r.x, r.y, r.x + r.w, r.y, rad);
  ctx.closePath();
  ctx.fill();

  // 复制图形: 两个重叠的圆角矩形
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 1.4;
  const ix = r.x + 4.5;
  const iy = r.y + 4.5;
  const s = r.w - 9;
  ctx.strokeRect(ix + 2.2, iy, s - 3.5, s - 3.5);
  ctx.fillStyle = hovering ? "rgba(80,80,80,1)" : "rgba(50,50,50,1)";
  ctx.fillRect(ix, iy + 2.2, s - 3.5, s - 3.5);
  ctx.strokeRect(ix, iy + 2.2, s - 3.5, s - 3.5);
  ctx.restore();
}

// ─────────────────────────── 节点初始化 ───────────────────────────

/**
 * 给节点装上 markdown 控件 + 复制按钮的全部行为。
 *
 * @param {LGraphNode} node 笔记节点(刚创建)
 * @returns {void}
 */
function setupNoteNode(node) {
  // 官方 Note 的配色, 一眼能认出这是"注释"类节点
  node.color = NOTE_COLORS.color;
  node.bgcolor = NOTE_COLORS.bgcolor;

  // ── 1. markdown 控件(官方同款) ──
  // 官方 MarkdownNoteNode 构造器里就是 ComfyWidgets.MARKDOWN(this, "text", ["STRING", {...}], app)
  const CW = getComfyWidgets();
  const initial = typeof node.properties?.text === "string" ? node.properties.text : "";
  const before = node.widgets?.length ?? 0;
  if (CW?.MARKDOWN && !node.widgets?.some((w) => w.name === "text")) {
    try {
      CW.MARKDOWN(node, "text", ["STRING", { default: initial }], app);
    } catch (e) {
      console.warn("[FallingTS.Note] markdown 控件创建失败, 退回纯文本:", e);
    }
  }
  // 极端兜底: MARKDOWN 不可用时至少给个能编辑的多行文本框
  if (!node.widgets?.some((w) => w.name === "text")) {
    console.warn("[FallingTS.Note] 拿不到 ComfyWidgets.MARKDOWN, 退回纯文本控件");
    node.addWidget("text", "text", initial, () => {}, { multiline: true });
  } else if (initial && (node.widgets?.length ?? 0) > before) {
    // 新建节点时把默认文本写进 widget —— Vue 的 WidgetMarkdown 用 widget.value 当
    // modelValue, 不写的话首屏渲染是空的(实测: 只给 MARKDOWN 的 default 参数不够,
    // 那条通路只喂给 detached 的原生 element)
    const w = node.widgets.find((x) => x.name === "text");
    if (w && !w.value) w.value = initial;
  }

  // ── 2. 虚拟节点标记 ──
  // graphToPrompt() 里 `if (e.isVirtualNode) continue` 会跳过本节点
  node.isVirtualNode = true;
  node.serialize_widgets = true;

  // 初始尺寸: 官方 MarkdownNote 的 minNodeSize 是 [400,200], 这里给它舒适的默认值
  if (!Array.isArray(node.size) || node.size[0] < 260 || node.size[1] < 140) {
    node.setSize?.([420, 280]);
  }

  // ── 3. canvas 模式回退(仅关掉 Vue 节点渲染时生效) ──
  const prevDraw = node.onDrawForeground;
  /** 绘制钩子: 在节点前景画复制按钮(Vue 模式下不会被调用)。 */
  node.onDrawForeground = function (ctx) {
    const ret = prevDraw?.apply(this, arguments);
    if (!this.flags?.collapsed) drawCopyButton(ctx, this);
    return ret;
  };

  const prevMouseMove = node.onMouseMove;
  /** 鼠标移动钩子: canvas 模式下维护按钮 hover 高亮。 */
  node.onMouseMove = function (e, pos) {
    const ret = prevMouseMove?.apply(this, arguments);
    const on = !this.flags?.collapsed && hitButton(this, pos);
    if (on !== this._fallingtsNoteHover) {
      this._fallingtsNoteHover = on;
      this.setDirtyCanvas?.(true, false);
    }
    return ret;
  };

  const prevMouseDown = node.onMouseDown;
  /** 鼠标按下钩子: canvas 模式点在按钮上就复制并吞掉事件。 */
  node.onMouseDown = function (e, pos) {
    if (!this.flags?.collapsed && hitButton(this, pos)) {
      if (e?.button === 0 || e?.button === undefined) {
        doCopy(this);
        return true;
      }
    }
    return prevMouseDown ? prevMouseDown.apply(this, arguments) : false;
  };

  // ── 4. Vue 模式: 注入 DOM 按钮 ──
  // 节点 DOM 是 Vue 异步渲染的, onNodeCreated 这一刻通常还没挂出来, 所以多拍重试。
  // MutationObserver(见 setup)负责后续的重渲染/新建兜底。
  [0, 80, 250, 600, 1200].forEach((ms) => {
    setTimeout(() => injectCopyButton(node), ms);
  });

  const prevRemoved = node.onRemoved;
  /** 节点移除钩子: 清掉注入的 DOM 按钮。 */
  node.onRemoved = function () {
    removeCopyButton(this);
    return prevRemoved?.apply(this, arguments);
  };
}

app.registerExtension({
  name: "FallingTS.Note",

  /**
   * 扩展初始化钩子: 用 MutationObserver 兜住节点 DOM 的重渲染与新建。
   *
   * Vue 节点模式下节点 DOM 会随折叠/展开/改尺寸/切换工作流重建, 重建后注入的
   * 按钮就没了。这里监听 body 子树变化, 每次变化都做一次幂等补注入(只在有新
   * 笔记节点缺按钮时才会真正动 DOM, 开销可忽略)。
   *
   * @returns {void}
   */
  setup() {
    let pending = false;
    const schedule = () => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => {
        pending = false;
        sweepInject();
      });
    };
    const obs = new MutationObserver(schedule);
    obs.observe(document.body, { childList: true, subtree: true });
    // 页面已就绪时先扫一遍(扩展可能在既有节点之后才加载)
    sweepInject();
  },

  /**
   * 节点定义注册前钩子: 给 FallingTSNote 补上节点创建逻辑。
   *
   * @param {Function} nodeType 节点类型构造函数
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 加 markdown 控件、标记虚拟节点、装复制按钮。
     *
     * @returns {*} 原钩子返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      const ret = onNodeCreated?.apply(this, arguments);
      setupNoteNode(this);
      return ret;
    };
  },

  /**
   * 节点创建完成钩子: 兜住"节点已建好但 onNodeCreated 未走到"的情况
   * (从存档恢复等), 并立刻补一次 DOM 注入。
   *
   * @param {LGraphNode} node 新节点
   * @returns {void}
   */
  nodeCreated(node) {
    if (node?.type !== NODE_CLASS) return;
    if (!node.widgets?.some((w) => w.name === "text")) setupNoteNode(node);
    [0, 120, 500].forEach((ms) => setTimeout(() => injectCopyButton(node), ms));
  },
});

// 供其它扩展/验收脚本复用
window.FallingTS = window.FallingTS || {};
window.FallingTS.readNoteText = readNoteText;
window.FallingTS.copyToClipboard = copyToClipboard;
window.FallingTS.injectNoteCopyButton = injectCopyButton;
