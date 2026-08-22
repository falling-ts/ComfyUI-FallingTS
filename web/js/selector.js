// FallingTS 多对一选择节点前端联动 (通用 ANY 节点, 参考 switch.js 的 total 动态端口范式):
// - total 组数 (最少 1) 变化时, 动态增删 input1..inputN 输入端口与 output1..outputN 输出端口;
//   组端口标签用 items 里的实际组名 (如 "右侧提示词"), 内部名称保持 inputN / outputN 供后端定位;
// - items 文本框(英文逗号分隔组名)变化时, 实时同步 selection 下拉选项 (选项 = 前 total 个组名);
// - 输出槽位: 前 3 个固定 selected_value/selected/index (与旧版槽位一致), 组输出 output1..outputN 追加其后;
//   增删只动尾部, 已有连线的槽位永不漂移;
// - 输入/输出类型恒为 * (ANY), 不传播类型 —— 节点通用, 可接任意类型;
// - 未选中的输入在服务端声明 lazy, 不会执行上游 —— "没有选择的不输出"。

import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FallingTSSelector";
const MAX_GROUPS = 50;
const DEFAULT_TOTAL = 2;
const EXTRA_OUTPUTS = 3; // 固定前 3 个输出: selected_value / selected / index

/**
 * 把逗号分隔文本拆成去空白的组名数组。
 *
 * @param {string} text 逗号分隔的组名文本
 * @returns {string[]} 去空白后的非空组名数组
 */
function splitItems(text) {
  return String(text ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * 读取节点 total widget 的当前组数, 非法值回退默认, 再裁到 [1, MAX_GROUPS]。
 *
 * @param {LGraphNode} node 多对一选择节点对象
 * @returns {number} 有效组数(1 ~ MAX_GROUPS)
 */
function getTotal(node) {
  const w = node.widgets?.find((w) => w.name === "total");
  let v = w ? Math.floor(Number(w.value)) : DEFAULT_TOTAL;
  if (!Number.isFinite(v)) v = DEFAULT_TOTAL;
  return Math.min(MAX_GROUPS, Math.max(1, v));
}

/**
 * 判断输入槽是否为动态展开的组端口 (inputN), 排除 widget 槽 (items/total/selection)。
 *
 * @param {object} input 输入槽对象
 * @returns {boolean} 是否动态组端口
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
 * 按 total + items 对齐节点: 组输入端口 input1..inputN + 组输出端口 output1..outputN + 下拉选项。
 *
 * 槽位稳定性: 组端口只从尾部增删 (输入: widget 槽之后追加; 输出: 固定 3 个附加输出之后追加),
 * 已有连线的槽位索引永不漂移。
 *
 * @param {LGraphNode} node 多对一选择节点对象
 * @returns {void}
 */
function syncNode(node) {
  const total = getTotal(node);
  const itemsWidget = node.widgets?.find((w) => w.name === "items");
  const options = [...new Set(splitItems(itemsWidget?.value))].slice(0, total);

  // 1) selection 下拉选项同步 (兼容层 + widgetValue store 两层)
  //    选项 = 前 total 个组名; 选中项越界 (改 total/items 后) 自动重置为第一组
  const getOptions = () => [...new Set(splitItems(node.widgets?.find((w) => w.name === "items")?.value))].slice(0, getTotal(node));
  const applyTo = (widget) => {
    if (!widget) return;
    widget.options = { ...(widget.options || {}), values: getOptions };
    const opts = getOptions();
    if (widget.value !== "" && !opts.includes(widget.value)) {
      widget.value = opts[0] ?? "";
      widget.callback?.(widget.value);
    }
  };
  applyTo(node.widgets?.find((w) => w.name === "selection"));
  applyTo(getStoreWidget(node, "selection"));

  // 2) 动态组输入端口 input1..inputN (widget 槽之后追加, 只动尾部)
  //    类型恒为 * (ANY); 端口标签用 items 实际组名, 内部名称保持 inputN 供后端按索引定位
  let dyn = (node.inputs ?? []).filter(isDynamicInput);
  while (dyn.length > total) {
    const slot = dyn[dyn.length - 1];
    node.removeInput(node.inputs.indexOf(slot));
    dyn = (node.inputs ?? []).filter(isDynamicInput);
  }
  while (dyn.length < total) {
    const idx = dyn.length + 1;
    node.addInput(`input${idx}`, "*");
    dyn = (node.inputs ?? []).filter(isDynamicInput);
  }
  for (let i = 0; i < dyn.length; i++) {
    dyn[i].localized_name = options[i] ?? `第 ${i + 1} 组`;
  }

  // 3) 组输出端口 output1..outputN (固定 3 个附加输出之后追加, 只动尾部)
  //    后端声明 output1..output50, 这里按 total 显隐; 未使用的端口被删除, 不进入 prompt
  const wantOutputs = total + EXTRA_OUTPUTS;
  while ((node.outputs ?? []).length > wantOutputs) {
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs ?? []).length < wantOutputs) {
    const slot = (node.outputs ?? []).length; // 0-based 槽位; 组编号 = 槽位 - EXTRA_OUTPUTS
    node.addOutput(`output_${slot - EXTRA_OUTPUTS + 1}`, "*");
  }
  for (let i = 0; i < total; i++) {
    node.outputs[EXTRA_OUTPUTS + i].localized_name = options[i] ?? `第 ${i + 1} 组`;
  }

  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "FallingTS.Selector",

  /**
   * 节点定义注册前钩子: 给 FallingTSSelector 绑定 total/items → 端口/下拉联动。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: total/items 变化时同步端口与下拉; 加载工作流时按保存的值对齐。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const node = this;

      const bindWidget = (name) => {
        const widget = node.widgets?.find((w) => w.name === name);
        if (!widget) return;
        const orig = widget.callback;
        /** widget 回调: total/items 值变化后重新对齐组端口与下拉。 */
        widget.callback = function (value) {
          const out = orig?.apply(this, arguments);
          syncNode(node);
          return out;
        };
      };
      bindWidget("items");
      bindWidget("total");

      // 兜底: 新前端输入可能不走 widget.callback, 用节点级 onWidgetChanged 再同步一次
      const onWidgetChanged = nodeType.prototype.onWidgetChanged;
      /** 节点级 widget 变化钩子: total/items 变化时同步端口与下拉。 */
      nodeType.prototype.onWidgetChanged = function (widget, value, ...args) {
        const out = onWidgetChanged?.apply(this, arguments);
        if (widget?.name === "items" || widget?.name === "total") {
          syncNode(this);
        }
        return out;
      };

      // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次
      const prevOnConfigure = node.onConfigure;
      /** configure 钩子: 工作流加载完成后按保存的 total/items 对齐端口。 */
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        syncNode(node);
      };

      syncNode(node);
      // 节点刚创建时 widgetValue store 可能还没注册完成, 下一 tick 再同步一次
      setTimeout(() => syncNode(node), 0);
      return result;
    };
  },
});
