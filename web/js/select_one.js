// FallingTS 多对一选择节点前端联动 (通用 ANY 节点):
// - items 文本框(英文逗号分隔)变化时, 实时同步 selection 下拉选项 (同 selector.js);
// - 按 items 选项数量在节点左侧展开 input1..inputN 输入端口 (同 switch.js 的动态端口范式),
//   端口标签直接用 items 里的实际内容 (如 "右侧提示词"), 内部名称保持 inputN 用于后端定位;
// - 输入/输出类型恒为 * (ANY), 不传播类型 —— 节点通用, 可接任意类型;
// - 未选中的输入在服务端声明 lazy, 不会执行上游 —— "没有选择的不输出"。

import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FallingTSSelectOne";
const MAX_INPUTS = 50;

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

/**
 * 判断输入槽是否为动态展开的数据端口 (inputN), 排除 widget 槽 (items/selection)。
 *
 * @param {object} input 输入槽对象
 * @returns {boolean} 是否动态端口
 */
function isDynamicInput(input) {
  return !input.widget && /^input\d+$/.test(input.name || "");
}

/**
 * 从新前端 widgetValue store 取节点某个 widget 的真实对象(优先), 否则返回 null。
 * 新前端 combo 渲染优先读 store 里的真实 widget (node.widgets 只是兼容层), 两层都要同步。
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
 * 按 items 对齐节点: 下拉选项 + 动态输入端口数量。
 *
 * @param {LGraphNode} node 多对一选择节点对象
 * @returns {void}
 */
function syncInputs(node) {
  const itemsWidget = node.widgets?.find((w) => w.name === "items");
  if (!itemsWidget) return;

  const options = [...new Set(splitItems(itemsWidget.value))];

  // 1) selection 下拉选项同步 (兼容层 + widgetValue store 两层)
  const getOptions = () => [...new Set(splitItems(itemsWidget.value))];
  const applyTo = (widget) => {
    if (!widget) return;
    widget.options = { ...(widget.options || {}), values: getOptions };
    const opts = getOptions();
    if (!opts.includes(widget.value)) {
      widget.value = opts[0] ?? "";
      widget.callback?.(widget.value);
    }
  };
  applyTo(node.widgets?.find((w) => w.name === "selection"));
  applyTo(getStoreWidget(node, "selection"));

  // 2) 动态输入端口 input1..inputN 与选项数量对齐 (未使用的端口被删除, 不进入 prompt)
  //    类型恒为 * (ANY); 端口标签用 items 实际内容, 内部名称保持 inputN 供后端按索引定位
  const want = Math.min(options.length, MAX_INPUTS);
  while ((node.inputs ?? []).filter(isDynamicInput).length < want) {
    const idx = (node.inputs ?? []).filter(isDynamicInput).length + 1;
    node.addInput(`input${idx}`, "*");
  }
  let dyn = (node.inputs ?? []).filter(isDynamicInput);
  while (dyn.length > want) {
    const slot = dyn[dyn.length - 1];
    node.removeInput(node.inputs.indexOf(slot));
    dyn = (node.inputs ?? []).filter(isDynamicInput);
  }
  for (let i = 0; i < want; i++) {
    dyn[i].localized_name = options[i] ?? `input${i + 1}`;
  }

  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "FallingTS.SelectOne",

  /**
   * 节点定义注册前钩子: 给 FallingTSSelectOne 绑定 items → 端口/下拉联动。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: items 变化时同步下拉与端口; 加载工作流时按保存的 items 对齐。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const node = this;

      const itemsWidget = node.widgets?.find((w) => w.name === "items");
      if (itemsWidget) {
        const orig = itemsWidget.callback;
        /** items 文本框回调: 值变化后重新同步下拉与输入端口。 */
        itemsWidget.callback = function (value) {
          const out = orig?.apply(this, arguments);
          syncInputs(node);
          return out;
        };
      }

      // 兜底: 新前端文本输入可能不走 widget.callback, 用节点级 onWidgetChanged 再同步一次
      const onWidgetChanged = nodeType.prototype.onWidgetChanged;
      /** 节点级 widget 变化钩子: items 变化时同步端口与下拉。 */
      nodeType.prototype.onWidgetChanged = function (widget, value, ...args) {
        const out = onWidgetChanged?.apply(this, arguments);
        if (widget?.name === "items") {
          syncInputs(this);
        }
        return out;
      };

      // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次
      const prevOnConfigure = node.onConfigure;
      /** configure 钩子: 工作流加载完成后按保存的 items 对齐端口。 */
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        syncInputs(node);
      };

      syncInputs(node);
      // 节点刚创建时 widgetValue store 可能还没注册完成, 下一 tick 再同步一次
      setTimeout(() => syncInputs(node), 0);
      return result;
    };
  },
});
