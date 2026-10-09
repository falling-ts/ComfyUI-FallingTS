/**
 * FallingTS 加载节点的下拉弹窗增强(「加载图像」/「加载视频」共用)。
 *
 * 1. 去掉选项末尾的 " [output]" / " [input]" 标注。
 *    前端给 output 资产项硬编码拼了这个来源后缀(WidgetSelect 里 outputItems 构造
 *    '<subfolder>/<name> [output]'), 用来和 input 目录的同名文件区分; 而本工作区
 *    input/ 与 output/ 是同一物理目录的软链, 两侧文件完全相同, 于是列表里既有带标注的
 *    资产项、又有不带标注的 remote 候选项(后端路由故意不带标注, 见两个 nodes.py 的
 *    docstring —— 带标注会让预览图按 type=input 拼出 404)。两者混在一起又重复又乱。
 *    本模块在弹窗 DOM 上把标注抹掉, 并给 widget.value 装上清洗: 万一点到的是资产项,
 *    落到节点/提交给后端的也是纯文件名(后端按 default_dir=output 解析, 不需要后缀)。
 *
 * 2. 在弹窗工具条「排序方式」左侧插一个「刷新」按钮。
 *    弹窗里原本没有刷新入口, 新出现的子目录/文件只能靠节点外的 refresh 按钮或
 *    跑完流程的自动刷新进列表。按钮点一下会调 widget.refresh() 重新扫一遍 output
 *    目录(含数字目录内部的整棵子树 —— 扫描口径在后端 remote 路由里)。
 *    ⚠️ 弹窗里的候选列表是"打开时算一次"的(WidgetSelectDropdown 读的是普通对象
 *    widget.options.values, 不是 Vue 的响应式数据, 刷新换了数组也不会重算), 所以刷新
 *    成功后本模块会关掉弹窗再自动点开一次, 让列表用新候选重新渲染。
 *
 * 只对登记过的 widget 生效(armComboMenu), 其它节点/插件的下拉完全不受影响。
 */

import { app } from "../../../scripts/app.js";

// 末尾的来源标注: "xxx [output]" / "xxx [input]"
const TAG_SUFFIX = /\s*\[(?:output|input)\]\s*$/i;
// 弹窗根(PrimeVue popover, pt.root 把类设成 "absolute z-50")与菜单根
const POPOVER_SELECTOR = '[data-pc-name="popover"]';
const MENU_SELECTOR = '[data-testid="form-dropdown-menu"]';
// 「排序方式」按钮的 title/aria-label(中英文界面都认)
const SORT_LABEL = /排序|sort/i;
// 刷新按钮的类名(幂等标记)
const REFRESH_CLASS = "fallingts-combo-refresh";
// 弹窗出现的重试时刻: 点开那一下之后弹窗是异步挂载的
const RETRY_MS = [0, 60, 200, 500];
// 刷新图标(逆时针箭头)
const REFRESH_ICON =
  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 3 21 9 15 9"/></svg>';
const SPIN_CSS =
  ".fallingts-combo-refresh{display:inline-flex;align-items:center;justify-content:center}" +
  ".fallingts-combo-refresh.fallingts-busy svg{animation:fallingts-combo-spin 0.9s linear infinite}" +
  "@keyframes fallingts-combo-spin{to{transform:rotate(360deg)}}";

// 已登记的 combo widget: [{node, widget, button}]
const watched = [];
// 最近一次被点开的那个 —— 弹窗只能属于一个 combo
let current = null;
let installed = false;

/**
 * 抹掉字符串末尾的来源标注。
 *
 * @param {*} value 原值
 * @returns {*} 去掉 " [output]"/" [input]" 的值(非字符串原样返回)
 */
function stripTag(value) {
  return typeof value === "string" ? value.replace(TAG_SUFFIX, "") : value;
}

/**
 * 取按钮的可读标签(title 优先, 再看 aria-label)。
 *
 * @param {HTMLElement} button 按钮
 * @returns {string} 标签文本
 */
function buttonLabel(button) {
  return String(button.getAttribute("title") || button.getAttribute("aria-label") || "");
}

/**
 * 给 widget.value 装清洗: 读到的永远是纯文件名, 写进来的标注顺手剥掉。
 *
 * 包装成访问器是为了覆盖"从下拉里选了一个资产项"这条路径 —— 前端选中时是
 * widget.value = item.name, 而资产项的 name 带标注。序列化(保存工作流)与提交
 * (graphToPrompt)读的都是 widget.value, 因此装在这里两边都干净。
 *
 * 2026-10-09: 访问器改成转发到 widget._state.value(见函数内注释) —— 只做剥标注,
 * 不再自己存值, 否则 combo 按钮显示的路径与实际提交/预览的路径会永久分家。
 *
 * @param {object} widget combo widget
 * @returns {void}
 */
function cleanWidgetValue(widget) {
  if (widget._fallingtsCleanValue) return;
  widget._fallingtsCleanValue = true;

  // ⚠️ 访问器必须转发到 widget._state.value(2026-10-09 修):
  // 1.52.7 里 combo 的显示文本由 Vue 组件从 widget._state.value 读
  // (safeWidgetMapper 的 createWidgetUpdateHandler 写 _state, 再经 pinia 的
  // widgetValue store 驱动重渲染), 与这个访问器毫无关系。早期版本用闭包 raw
  // 存值: widget.value 写进去后, 提交的确实是新值(graphToPrompt 读
  // widget.value), 但 combo 按钮上的文字纹丝不动 —— 用户看到
  // 0010_灰度遮罩/… 实际加载的却是 0016_建模拆图/…; 反过来改 _state.value
  // 又会与 raw 分家, 两边永久不一致。正确做法是让访问器只做「剥标注」的转发:
  // 读 _state.value, 写 _state.value。
  const initial = stripTag(widget.value);
  if (widget._state) widget._state.value = initial;
  Object.defineProperty(widget, "value", {
    configurable: true,
    enumerable: true,
    get: () => (widget._state ? stripTag(widget._state.value) : initial),
    set: (value) => {
      const clean = stripTag(value);
      if (widget._state) widget._state.value = clean;
      widget.triggerDraw?.();
    },
  });
}

/**
 * 把弹窗列表里的 " [output]"/" [input]" 标注从文本节点上抹掉。
 *
 * 兼容两种结构: 标注与文件名在同一个文本节点里, 或标注单独占一个文本节点。
 *
 * @param {HTMLElement} menu 弹窗菜单根
 * @returns {void}
 */
function cleanMenu(menu) {
  const walker = document.createTreeWalker(menu, NodeFilter.SHOW_TEXT);
  let text;
  while ((text = walker.nextNode())) {
    const cleaned = stripTag(text.nodeValue);
    if (cleaned !== text.nodeValue) text.nodeValue = cleaned;
  }
}

/**
 * 在「排序方式」左侧插刷新按钮(已经插过就跳过)。
 *
 * @param {HTMLElement} menu 弹窗菜单根
 * @param {{node: object, widget: object}} item 当前弹窗对应的节点与 widget
 * @returns {void}
 */
function addRefreshButton(menu, item) {
  if (menu.querySelector("." + REFRESH_CLASS)) return;
  const sortButton = [...menu.querySelectorAll("button")].find((b) => SORT_LABEL.test(buttonLabel(b)));
  if (!sortButton) return;

  const button = document.createElement("button");
  button.type = "button";
  button.className = sortButton.className + " " + REFRESH_CLASS;
  button.title = "刷新资源(重新扫描目录与子目录)";
  button.setAttribute("aria-label", "刷新资源");
  button.innerHTML = REFRESH_ICON;
  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    refreshCandidates(item, button);
  });
  sortButton.parentNode.insertBefore(button, sortButton);
}

/**
 * 重新扫目录并刷新候选列表(刷完重开一次弹窗, 见模块头注释)。
 *
 * @param {{node: object, widget: object}} item 当前弹窗对应的节点与 widget
 * @param {HTMLElement} button 触发按钮(用于转圈与防重入)
 * @returns {Promise<void>} 刷新完成
 */
async function refreshCandidates(item, button) {
  if (button.classList.contains("fallingts-busy")) return;
  button.classList.add("fallingts-busy");
  try {
    const widget = item.widget;
    if (typeof widget.refresh === "function") await widget.refresh();
    app.extensionManager.toast.add({
      severity: "info",
      summary: "已刷新资源列表(含子目录)",
      life: 3000,
    });
    reopenDropdown(item);
  } catch (err) {
    console.warn("[FallingTS] 刷新下拉候选失败:", err);
    app.extensionManager.toast.add({ severity: "error", summary: "刷新资源列表失败", life: 3000 });
  } finally {
    button.classList.remove("fallingts-busy");
  }
}

/**
 * 刷新后重开一次下拉。
 *
 * 弹窗里的候选列表是"打开时算一次"的: WidgetSelectDropdown 读的是普通对象
 * widget.options.values(不是响应式数据), 刷新换了数组它也**不会重算**(组件复用,
 * computed 缓存的旧值直接沿用) —— 只有把弹窗关掉(组件卸载)再打开才会重新读。
 * 所以这里按 Escape 关闭, 再用"真鼠标"的顺序点一下 combo 按钮。
 *
 * @param {{node: object, widget: object, button: HTMLElement}} item 当前弹窗对应的条目
 * @returns {void}
 */
function reopenDropdown(item) {
  const button = item.button && document.body.contains(item.button) ? item.button : comboButtonOf(item);
  if (!button) return;
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  // PrimeVue 关/开各有一段过渡, 太早的那一拍会被丢掉(实测第一拍常打不开) ⇒ 两拍兜底
  for (const delay of [500, 1400]) {
    setTimeout(() => {
      if (item.node && item.node.removed) return;
      const again = item.button && document.body.contains(item.button) ? item.button : comboButtonOf(item);
      if (again) clickLike(again);
    }, delay);
  }
}

/**
 * 找节点上那个 combo 按钮: Vue 节点里显示当前值的就是它。
 *
 * @param {{widget: object}} item 当前弹窗对应的条目
 * @returns {HTMLElement|null} combo 按钮(找不到返回 null)
 */
function comboButtonOf(item) {
  const text = String(item.widget.value ?? "").trim();
  if (!text) return null;
  const leaves = [...document.querySelectorAll("*")]
    .filter((el) => el.children.length === 0 && (el.textContent || "").trim() === text);
  if (!leaves.length) return null;
  const leaf = leaves[leaves.length - 1];
  return leaf.closest("button") || leaf.parentElement;
}

/**
 * 按"真鼠标"的顺序点一个按钮: 下拉是靠 pointerdown 那一拍展开的, 只发 click 打不开。
 *
 * @param {HTMLElement} button 目标按钮
 * @returns {void}
 */
function clickLike(button) {
  const sequence = ["pointerdown", "mousedown", "pointerup", "mouseup", "click"];
  sequence.forEach((type, index) => {
    setTimeout(() => {
      if (type === "mousedown" || type === "click") {
        button.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, button: 0 }));
        return;
      }
      button.dispatchEvent(new PointerEvent(type, {
        bubbles: true,
        cancelable: true,
        composed: true,
        pointerType: "mouse",
        button: 0,
        buttons: type === "pointerdown" ? 1 : 0,
      }));
    }, index * 40);
  });
}

/**
 * 菜单内容变化(切换分类/搜索/刷新后重渲染)时重新抹标注。
 *
 * @param {HTMLElement} menu 弹窗菜单根
 * @returns {void}
 */
function watchMenu(menu) {
  if (menu._fallingtsMenuWatched) return;
  menu._fallingtsMenuWatched = true;
  const observer = new MutationObserver(() => cleanMenu(menu));
  observer.observe(menu, { childList: true, subtree: true, characterData: true });
}

/**
 * 增强当前弹窗: 抹标注 + 插刷新按钮。
 *
 * @returns {void}
 */
function enhanceCurrent() {
  if (!current || current.node?.removed) return;
  const popover = document.querySelector(POPOVER_SELECTOR);
  if (!popover) return;
  const menu = popover.querySelector(MENU_SELECTOR);
  if (!menu) return;
  cleanMenu(menu);
  addRefreshButton(menu, current);
  watchMenu(menu);
}

/**
 * 记住"弹窗属于哪个 combo", 并在弹窗挂载后增强它。
 *
 * @param {{node: object, widget: object}} item 命中的节点与 widget
 * @returns {void}
 */
function arm(item) {
  current = item;
  for (const delay of RETRY_MS) setTimeout(enhanceCurrent, delay);
}

/**
 * 全局安装(只装一次): 两条"点开下拉"的识别路径 + 弹窗出现时的增强。
 *
 * @returns {void}
 */
function install() {
  if (installed) return;
  installed = true;

  const style = document.createElement("style");
  style.textContent = SPIN_CSS;
  document.head.appendChild(style);

  // 路径一(Vue 节点): 节点体里的 combo 是真实 DOM 按钮, 按钮文本就是当前值
  document.addEventListener("click", (event) => {
    const button = event.target?.closest?.("button");
    if (!button) return;
    const text = (button.textContent || "").trim();
    if (!text) return;
    const hit = watched.find((entry) => !entry.node?.removed
      && String(entry.widget.value ?? "").trim() === text);
    if (!hit) return;
    hit.button = button;
    arm(hit);
  }, true);

  // 路径二(画布模式): LiteGraph 会把鼠标下的 widget 记在 canvas.node_widget 上
  document.addEventListener("pointerdown", () => {
    const pair = app.canvas?.node_widget;
    const node = pair?.[0];
    const widget = pair?.[1];
    if (!node || !widget) return;
    const hit = watched.find((entry) => entry.node === node && entry.widget === widget);
    if (hit) arm(hit);
  }, false);

  // 弹窗被复用(同一元素反复显示)时不会有新增节点, 只能靠上面的两拍重试兜底;
  // 这里再补一次新增监听, 覆盖"弹窗是新建出来的"那种情况
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const added of record.addedNodes) {
        if (added.nodeType !== 1 || !added.matches?.(POPOVER_SELECTOR)) continue;
        for (const delay of RETRY_MS) setTimeout(enhanceCurrent, delay);
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: false });
}

/**
 * 给加载节点的 combo 装上「弹窗增强」。
 *
 * 同一个 widget 只装一次; 节点被删除后不再参与。
 *
 * @param {LGraphNode} node 节点
 * @param {string} widgetName combo widget 的名字(image / video)
 * @returns {void}
 */
/**
 * 当前打开着下拉弹窗的那个节点(没有则返回 null)。
 *
 * 弹窗是挂在 body 下的 portal, 不在节点 DOM 里 —— 别的扩展想知道"用户正在操作哪个
 * 加载节点的下拉"只能靠这里记录的 current。
 *
 * @returns {LGraphNode|null} 节点
 */
export function armedComboNode() {
  return current && !current.node?.removed ? current.node : null;
}

export function armComboMenu(node, widgetName) {
  const widget = node.widgets?.find((w) => w.name === widgetName);
  if (!widget || widget._fallingtsMenuArmed) return;
  widget._fallingtsMenuArmed = true;
  cleanWidgetValue(widget);
  watched.push({ node, widget });
  install();
}
