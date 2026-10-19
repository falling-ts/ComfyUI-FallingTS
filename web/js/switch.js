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

/** 组输入端口名: false_i / true_i。switch/total 等 widget 端口不匹配。 */
const GROUP_RE = /^(false|true)_(\d+)$/;

/**
 * 判断输入端口是否为组端口(false_i / true_i), 而非 switch/total 这类 widget 端口。
 *
 * @param {object} inp 输入端口对象
 * @returns {boolean} 是组端口返回 true
 */
function isGroupInput(inp) {
  return GROUP_RE.test(inp?.name ?? "");
}

/**
 * 取组端口的组号(1 起); 非组端口返回 NaN。
 *
 * @param {object} inp 输入端口对象
 * @returns {number} 组号
 */
function groupIndexOf(inp) {
  return Number(GROUP_RE.exec(inp?.name ?? "")?.[2]);
}

/**
 * 按 total 对齐节点端口: 输入每 2 个一组(false_i, true_i), 输出 output_1..output_total。
 * 未使用且未连线的端口被删除, 不进入 prompt。
 *
 * ⚠️ 只按端口名识别组端口, 不再用 inputs.length 计数: 旧版工作流把 switch/total 也
 * 序列化进 inputs(共 4 个端口), 早先按 total*2 计数会从末尾裁掉 false_1/true_1 并
 * 连带断开它们的连线(0031_首帧场景 丢 link 395/398 事故的根因)。
 *
 * @param {LGraphNode} node 分组开关节点对象
 * @returns {void}
 */
function syncGroups(node) {
  const total = getTotal(node);

  // 组输入: 每 2 个一组 (false_i, true_i)。
  // 先删多余组端口 —— 仅限组号 > total 且未连线; 已连线的保留(后端只取 i<=total, 多留无害)。
  for (let i = node.inputs.length - 1; i >= 0; i--) {
    const inp = node.inputs[i];
    if (isGroupInput(inp) && groupIndexOf(inp) > total && inp.link == null) {
      node.removeInput(i);
    }
  }

  // 再补缺失组端口: 保证 false_1/true_1 .. false_total/true_total 齐全。
  for (let g = 1; g <= total; g++) {
    for (const side of ["false", "true"]) {
      const name = `${side}_${g}`;
      if (!node.inputs.some((inp) => inp.name === name)) node.addInput(name, "*");
    }
  }

  // 统一本地化名(只处理组端口, widget 端口保持后端给的名字)
  for (const inp of node.inputs) {
    if (!isGroupInput(inp)) continue;
    inp.localized_name =
      (inp.name.startsWith("false") ? "\u4e3a\u5047\u65f6 " : "\u4e3a\u771f\u65f6 ") + groupIndexOf(inp);
  }

  // 输出: output_1..output_total; 末尾已连线的输出保留, 不放空
  while ((node.outputs?.length ?? 0) > total) {
    if (node.outputs[node.outputs.length - 1].links?.length) break;
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

/**
 * 节点高度收回自然高度(只缩不扩: 用户手动拉高的高度保留)。
 *
 * 后端声明 MAX_GROUPS=50 个输出, 新建节点时构造器先加上全部 50 个输出并把初始高度
 * 撑到容纳 50 个输出 (上千 px); syncGroups 按 total 删掉多余端口后需把多余高度收回,
 * 否则新建节点异常高大。仅新建时生效(onNodeCreated): 加载工作流时 configure 恢复
 * 保存的高度, 不受影响。
 *
 * @param {LGraphNode} node 分组开关节点对象
 * @returns {void}
 */
function fitHeight(node) {
  const natural = node.computeSize?.();
  if (!natural || !node.size) return;
  if (node.size[1] > natural[1]) {
    node.setSize([node.size[0], natural[1]]);
  }
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
      fitHeight(node);
    };
  },
});
