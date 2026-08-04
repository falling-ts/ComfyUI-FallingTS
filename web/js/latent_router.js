// FallingTS Latent 路由前端联动:
// input_count widget 控制 (enable_i + latent_i) 输入对数量,
// 变化时动态增删输入槽, 保持平级结构, 支持大量档位。

import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FallingTSLatentRouter";

function updateInputs(node) {
  const countWidget = node.widgets?.find((w) => w.name === "input_count");
  const count = Math.max(1, Math.min(100, Math.floor(countWidget?.value ?? 2)));

  // 统计现有 latent_i 输入对数
  let existing = 0;
  for (const inp of node.inputs) {
    if (inp.name?.startsWith("latent_")) existing++;
  }

  // 追加不足的输入对
  for (let i = existing + 1; i <= count; i++) {
    node.addInput(`latent_${i}`, "LATENT");
    node.addInput(`enable_${i}`, "BOOLEAN");
  }

  // 移除多余的输入对 (尾部成对删除)
  for (let i = existing; i > count; i--) {
    const tailEnable = node.inputs[node.inputs.length - 1];
    const tailLatent = node.inputs[node.inputs.length - 2];
    if (tailEnable?.name === `enable_${i}` && tailLatent?.name === `latent_${i}`) {
      node.removeInput(node.inputs.length - 1);
      node.removeInput(node.inputs.length - 1);
    } else {
      break;
    }
  }

  node.setSize?.(node.computeSize?.() ?? node.size);
  node.setDirtyCanvas(true, true);
}

app.registerExtension({
  name: "FallingTS.LatentRouter",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const node = this;

      const countWidget = node.widgets?.find((w) => w.name === "input_count");
      if (countWidget) {
        const orig = countWidget.callback;
        countWidget.callback = function (value) {
          const out = orig?.apply(this, arguments);
          updateInputs(node);
          return out;
        };
      }

      updateInputs(node);
      // 节点刚创建/加载时 inputs 可能尚未就绪, 下一 tick 再对齐一次
      setTimeout(() => updateInputs(node), 0);
      return result;
    };
  },
});
