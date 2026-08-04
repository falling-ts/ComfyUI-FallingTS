// FallingTS 下拉选择器前端联动:
// items 文本框(英文逗号分隔选项)变化时, 实时同步 selection 下拉框的选项;
// 若当前选中项不在新列表里, 自动重置为第一项。

import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FallingTSSelector";

function splitItems(text) {
  return String(text ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

// 新前端 combo 渲染优先读 widgetValue store 里的真实 widget (通过 widgetId),
// node.widgets 只是兼容层; 两层都要同步。
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
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);

      const node = this;
      const itemsWidget = node.widgets?.find((w) => w.name === "items");
      if (itemsWidget) {
        const orig = itemsWidget.callback;
        itemsWidget.callback = function (value) {
          const out = orig?.apply(this, arguments);
          syncSelection(node);
          return out;
        };
      }

      // 兜底: 新前端文本输入可能不走 widget.callback, 用节点级 onWidgetChanged 再同步一次
      const onWidgetChanged = nodeType.prototype.onWidgetChanged;
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
