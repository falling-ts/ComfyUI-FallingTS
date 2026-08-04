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

function syncSelection(node) {
  const itemsWidget = node.widgets?.find((w) => w.name === "items");
  const selWidget = node.widgets?.find((w) => w.name === "selection");
  if (!itemsWidget || !selWidget) return;

  const options = splitItems(itemsWidget.value);

  // 关键: 新前端 combo 渲染绑定的是 options.values 的数组引用,
  // 必须原地 splice 更新, 替换整个 options 对象不会触发下拉刷新。
  let values = selWidget.options?.values;
  if (!Array.isArray(values)) {
    values = [];
    selWidget.options = { ...(selWidget.options || {}), values };
  }
  values.splice(0, values.length, ...[...new Set(options)]);

  if (!options.includes(selWidget.value)) {
    selWidget.value = options[0] ?? "";
    selWidget.callback?.(selWidget.value);
  }
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
      return result;
    };
  },
});
