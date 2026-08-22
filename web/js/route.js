/**
 * FallingTSRoute 前端扩展 (total 组路由, 参考分组开关 switch.js 的 total 动态端口范式):
 * - 一个 switch 布尔 + total 组数 (最少 1), 每组 = 为假时_i/为真时_i 输入 + 输出_i 输出 (ANY);
 * - 本前端中 legacy 的 BOOLEAN/INT 输入是纯 widget (无 socket),
 *   node.inputs 里只有各组 ANY 端口 (false_i / true_i), 按 total 动态增删;
 * - 让路由节点的「假分支」下游真正执行: partial 提交(点「继续」)时,
 *   把 switch=false 的 route 节点各组输出下游的输出节点并入 targets。
 *
 * partial 执行为什么要补假分支:
 * - partial 执行(点「继续」)只跑 targets + targets 的上游祖先; 假分支的
 *   末端输出节点(如保存节点) 不在 targets 里, 引擎不调度它 -> 值到了但节点不跑, "保存本段并停止"失效;
 * - 修法: partial 提交时把图中每个 switch=false 的 route 节点各组输出下游的输出节点并进 targets ——
 *   假输出后面不管接什么节点(保存/预览/对比)都能被执行并拿到数据;
 * - 为什么只补假分支: 真输出分支(放大/重绘)本就是"下一个继续节点"的上游, 已被继续节点的 partial targets 覆盖, 无需处理;
 *   假输出分支(保存并停止)是末端, 不会被任何 targets 覆盖, 只能由这里补;
 * - switch=false 会阻断下个继续(#5401 拿不到输入不缓存), 所以假分支天然停在当前段,
 *   后续段点「继续」时不会误把前面段的假分支拉回来重跑。
 *
 * 与 proceed.js 的 queuePrompt 包装器链式叠加(两者顺序无关):
 * - 全量 Run: queueNodeIds 为空 -> 这里不加, proceed 负责 /proceed/reset;
 * - 继续: 非空 -> 这里并进假分支 target, proceed 负责跳过 reset。
 */

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "FallingTSRoute";
const CONTINUE_CLASS = "FallingTSContinue";
const MAX_GROUPS = 50;
const DEFAULT_TOTAL = 2;

/**
 * 读取节点 total widget 的当前组数, 非法值回退默认, 再裁到 [1, MAX_GROUPS]。
 *
 * @param {LGraphNode} node 路由节点对象
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
 * @param {LGraphNode} node 路由节点对象
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

/**
 * 判断节点是否为「路由节点」, 兼容新旧前端两种节点类型标记方式(type / constructor.comfyClass)。
 *
 * @param {LGraphNode} node 画布节点对象
 * @returns {boolean} 是路由节点返回 true
 */
function isRouteNode(node) {
  return node?.type === NODE_CLASS || node?.constructor?.comfyClass === NODE_CLASS;
}

/**
 * 判断节点是否为「继续节点」(分段边界, BFS 收集到此停止)。
 *
 * @param {LGraphNode} node 画布节点对象
 * @returns {boolean} 是继续节点返回 true
 */
function isContinueNode(node) {
  return node?.type === CONTINUE_CLASS || node?.constructor?.comfyClass === CONTINUE_CLASS;
}

/**
 * 判断节点是否为「输出节点」(保存/预览等终端节点)。
 *
 * @param {LGraphNode} node 画布节点对象
 * @returns {boolean} 该节点的 nodeData.output_node 为 true 返回 true
 */
function isOutputNode(node) {
  return node?.constructor?.nodeData?.output_node === true;
}

/**
 * 按 linkId 从图的链路表取链路对象(不存在/已断开时为 null)。
 *
 * @param {LGraph} graph 画布图对象
 * @param {number} linkId 链路 ID
 * @returns {object|null} 链路对象, 不存在时为 null
 */
function getLink(graph, linkId) {
  return graph?.links?.[linkId] ?? null;
}

/**
 * 取 route 节点 switch widget 值, 决定激活分支。
 *
 * @param {LGraphNode} node route 节点
 * @returns {boolean} true=各组真分支激活, false=各组假分支激活
 */
function getSwitchValue(node) {
  const w = node.widgets?.find((x) => x.name === "switch");
  return !!w?.value;
}

/**
 * 从 route 节点各组输出(slot 0..total-1, switch=false 时各取 为假时_i 分支)下游 BFS,
 * 收集输出节点(遇到继续节点停止)。
 * 收集到的节点 ID 在 partial 提交时并入 targets, 让各组假分支真正执行。
 *
 * @param {LGraphNode} routeNode route 节点
 * @returns {string[]} 输出节点的 ID 字符串数组(已去重); 一个都没有时返回空数组
 */
function collectFalseBranchOutputs(routeNode) {
  const outs = routeNode.outputs ?? [];
  const targets = new Set();
  const visited = new Set();
  const queue = [];
  for (const o of outs) {
    for (const linkId of o.links ?? []) {
      const link = getLink(routeNode.graph, linkId);
      if (link) queue.push(link.target_id);
    }
  }
  while (queue.length) {
    const nid = queue.shift();
    if (visited.has(nid)) continue;
    visited.add(nid);
    const n = routeNode.graph?.getNodeById?.(nid);
    if (!n) continue;
    if (isContinueNode(n)) continue; /* 遇到继续: 本段到此为止 */
    if (isOutputNode(n)) targets.add(String(n.id));
    for (const o of n.outputs ?? []) {
      for (const linkId of o.links ?? []) {
        const link = getLink(n.graph, linkId);
        if (link) queue.push(link.target_id);
      }
    }
  }
  return [...targets];
}

/**
 * 收集图中所有 switch=false 的 route 节点各组假分支的输出节点(去重)。
 *
 * @param {LGraph} graph 画布图对象
 * @returns {string[]} 输出节点的 ID 字符串数组
 */
function collectAllFalseBranchTargets(graph) {
  const targets = new Set();
  for (const n of graph?._nodes ?? []) {
    if (!isRouteNode(n)) continue;
    if (getSwitchValue(n)) continue; /* 只处理假分支(真分支由继续节点 targets 覆盖) */
    for (const t of collectFalseBranchOutputs(n)) targets.add(t);
  }
  return [...targets];
}

app.registerExtension({
  name: "FallingTS.Route",

  /**
   * 扩展初始化钩子: 包装全局提交入口 app.queuePrompt。
   * partial 提交(继续, queueNodeIds 非空)时, 把 switch=false 的 route 节点
   * 各组假分支下游的输出节点并入 targets, 让"保存本段并停止"真正执行。
   *
   * @returns {void}
   */
  async setup() {
    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    /**
     * 包装 queuePrompt: 只处理 partial 提交分支(队列 NodeIds 非空), 并进假分支 targets。
     *
     * @param {number} number 提交次数
     * @param {number} batch 批次数
     * @param {Array<string>|undefined} queueNodeIds 继续节点显式指定的目标节点 ID 列表
     * @returns {Promise} 原始 queuePrompt 的返回值(提交任务后的 Promise)
     */
    app.queuePrompt = async function (number, batch, queueNodeIds) {
      if (queueNodeIds?.length) {
        const graph = app.graph ?? app.rootGraph;
        const routeTargets = collectAllFalseBranchTargets(graph);
        if (routeTargets.length) {
          queueNodeIds = [...new Set([...queueNodeIds, ...routeTargets])];
        }
      }
      return orig(number, batch, queueNodeIds);
    };
  },

  /**
   * 节点定义注册前钩子: 给 FallingTSRoute 绑定 total → 端口增删联动。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

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
