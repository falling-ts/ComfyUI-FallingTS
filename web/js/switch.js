// FallingTS 分组开关前端联动 (参考官方 ComfySwitchNode 的批量版):
// - 一个 switch 布尔 + total 组数 (最少 1), 每组 = 为假时/为真时/输出 (ANY);
// - 本前端中 legacy 的 BOOLEAN/INT 输入是纯 widget (无 socket),
//   node.inputs 里只有各组 ANY 端口 (false_i / true_i), 按 total 动态增删。
import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FallingTSSwitch";
const MAX_GROUPS = 50;
const DEFAULT_TOTAL = 2;

/**
 * 读取节点 total widget 的当前组数, 非法值回退默认, 再裁到 [1, MAX_GROUPS]。
 *
 * @param {LGraphNode} node 分组开关节点对象
 * @returns {number} 有效组数(1 ~ MAX_GROUPS)
 */
function getTotal(node) {
  const w = node.widgets?.find((w) => w.name === "total");
  let v = w ? Math.floor(Number(w.value)) : DEFAULT_TOTAL;
  if (!Number.isFinite(v)) v = DEFAULT_TOTAL;
  return Math.min(MAX_GROUPS, Math.max(1, v));
}

/**
 * 按 total 对齐节点端口: 输入每 2 个一组(false_i, true_i), 输出 output_1..output_total。
 * 未使用的输入/输出端口被删除, 不进入 prompt。
 *
 * @param {LGraphNode} node 分组开关节点对象
 * @returns {void}
 */
function syncGroups(node) {
  const total = getTotal(node);

  // 组输入: 每 2 个一组 (false_i, true_i)
  const wantInputs = total * 2;
  while ((node.inputs?.length ?? 0) > wantInputs) {
    node.removeInput(node.inputs.length - 1);
  }
  while ((node.inputs?.length ?? 0) < wantInputs) {
    const idx = node.inputs.length;
    const g = Math.floor(idx / 2) + 1;
    node.addInput(idx % 2 === 0 ? `false_${g}` : `true_${g}`, "*");
  }
  for (let i = 0; i < wantInputs; i++) {
    const g = Math.floor(i / 2) + 1;
    node.inputs[i].localized_name = (i % 2 === 0 ? "\u4e3a\u5047\u65f6 " : "\u4e3a\u771f\u65f6 ") + g;
  }

  // 输出: output_1..output_total
  while ((node.outputs?.length ?? 0) > total) {
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < total) {
    node.addOutput(`output_${node.outputs.length + 1}`, "*");
  }
  for (let i = 0; i < total; i++) {
    node.outputs[i].localized_name = "\u8f93\u51fa " + (i + 1);
  }

  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "FallingTS.Switch",

  /**
   * 节点定义注册前钩子: 给 FallingTSSwitch 绑定 total → 端口增删联动。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: total 变化时同步端口; 加载工作流时按保存的 widgets_values 对齐。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      const totalWidget = node.widgets?.find((w) => w.name === "total");
      if (totalWidget) {
        const cb = totalWidget.callback;
        /** total widget 回调: 组数变化后重新对齐输入/输出端口。 */
        totalWidget.callback = function (v) {
          cb?.call(this, v);
          syncGroups(node);
        };
      }

      // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次
      const prevOnConfigure = node.onConfigure;
      /** configure 钩子: 工作流加载完成后按保存的 total 对齐端口。 */
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        syncGroups(node);
      };

      syncGroups(node);
    };
  },
});
