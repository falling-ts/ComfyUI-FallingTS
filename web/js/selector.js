// FallingTS 下拉选择器前端联动:
// items 文本框(英文逗号分隔选项)变化时, 实时同步 selection 下拉框的选项;
// 若当前选中项不在新列表里, 自动重置为第一项。

import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FallingTSSelector";

/**
 * 把逗号分隔文本拆成去空白的选项数组。
 *
 * @param {string} text 逗号分隔的选项文本
 * @returns {string[]} 去空白后的非空选项数组
 */
function splitItems(text) {
  return String(text ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

// 新前端 combo 渲染优先读 widgetValue store 里的真实 widget (通过 widgetId),
// node.widgets 只是兼容层; 两层都要同步。
/**
 * 从新前端 widgetValue store 取节点某个 widget 的真实对象(优先), 否则返回 null。
 * 新前端 combo 渲染优先读 store 里的真实 widget(node.widgets 只是兼容层), 两层都要同步。
 *
 * @param {LGraphNode} node 画布节点对象
 * @param {string} name widget 名(如 "selection")
 * @returns {object|null} store 里的真实 widget 对象; store 不可用时返回 null
 */
function getStoreWidget(node, name) {
  try {
    const el = document.getElementById("vue-app");
    const pinia = el?.__vue_app__?.config?.globalProperties?.$pinia;
    const store = pinia?._s?.get("widgetValue");
    const w = node.widgets?.find((w) => w.name === name);
    if (w?.widgetId && store?.getWidget) {
      return store.getWidget(w.widgetId) ?? null;
    }
  } catch {
    // store 不可用时退化为只更新 node.widgets
  }
  return null;
}

/**
 * 同步 items 文本到 selection 下拉的选项: items 变化时实时更新下拉选项,
 * 若当前选中项不在新列表里则自动重置为第一项。兼容层与 widgetValue store 两层都更新。
 *
 * @param {LGraphNode} node 选择器节点对象
 * @returns {void}
 */
function syncSelection(node) {
  const itemsWidget = node.widgets?.find((w) => w.name === "items");
  if (!itemsWidget) return;

  // 新前端 WidgetSelect 支持 options.values 为函数: 每次渲染下拉时实时调用,
  // 这样 items 变化后无需手动 splice, 打开下拉即是最新选项。
  const getOptions = () => [...new Set(splitItems(itemsWidget.value))];

  const applyTo = (widget) => {
    if (!widget) return;
    widget.options = { ...(widget.options || {}), values: getOptions };
    const options = getOptions();
    if (!options.includes(widget.value)) {
      widget.value = options[0] ?? "";
      widget.callback?.(widget.value);
    }
  };

  // 兼容层 + store 真实对象, 两层都更新
  applyTo(node.widgets?.find((w) => w.name === "selection"));
  applyTo(getStoreWidget(node, "selection"));
  node.setDirtyCanvas(true, true);
}

app.registerExtension({
  name: "FallingTS.Selector",

  /**
   * 节点定义注册前钩子: 给 FallingTSSelector 绑定 items → selection 联动。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 包装 items 的 callback 与节点级 onWidgetChanged, 使 items 变化即同步下拉。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);

      const node = this;
      const itemsWidget = node.widgets?.find((w) => w.name === "items");
      if (itemsWidget) {
        const orig = itemsWidget.callback;
        /** items 文本框回调: 值变化后同步 selection 下拉。 */
        itemsWidget.callback = function (value) {
          const out = orig?.apply(this, arguments);
          syncSelection(node);
          return out;
        };
      }

      // 兜底: 新前端文本输入可能不走 widget.callback, 用节点级 onWidgetChanged 再同步一次
      const onWidgetChanged = nodeType.prototype.onWidgetChanged;
      /** 节点级 widget 变化钩子: items 变化时同步 selection。 */
      nodeType.prototype.onWidgetChanged = function (widget, value, ...args) {
        const out = onWidgetChanged?.apply(this, arguments);
        if (widget?.name === "items") {
          syncSelection(this);
        }
        return out;
      };

      syncSelection(node);
      // 节点刚创建时 widgetValue store 可能还没注册完成, 下一 tick 再同步一次
      setTimeout(() => syncSelection(node), 0);
      return result;
    };
  },
});
