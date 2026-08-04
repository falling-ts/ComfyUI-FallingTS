// FallingTS 分组开关前端联动 (参考官方 ComfySwitchNode 的批量版):
// - 一个 switch 布尔 + total 组数 (最少 1), 每组 = 为假时/为真时/输出 (ANY);
// - 本前端中 legacy 的 BOOLEAN/INT 输入是纯 widget (无 socket),
//   node.inputs 里只有各组 ANY 端口 (false_i / true_i), 按 total 动态增删。
import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FallingTSSwitch";
const MAX_GROUPS = 50;
const DEFAULT_TOTAL = 2;

function getTotal(node) {
  const w = node.widgets?.find((w) => w.name === "total");
  let v = w ? Math.floor(Number(w.value)) : DEFAULT_TOTAL;
  if (!Number.isFinite(v)) v = DEFAULT_TOTAL;
  return Math.min(MAX_GROUPS, Math.max(1, v));
}

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
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      const totalWidget = node.widgets?.find((w) => w.name === "total");
      if (totalWidget) {
        const cb = totalWidget.callback;
        totalWidget.callback = function (v) {
          cb?.call(this, v);
          syncGroups(node);
        };
      }

      // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次
      const prevOnConfigure = node.onConfigure;
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        syncGroups(node);
      };

      syncGroups(node);
    };
  },
});
