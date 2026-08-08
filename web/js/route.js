/**
 * FallingTSRoute 前端扩展: 让 route 的「假输出」分支真正执行。
 *
 * 问题: partial 执行(点「继续」)只跑 targets + targets 的上游祖先; route 假输出分支的
 * 末端输出节点(如保存节点) 不在 targets 里, 引擎不调度它 -> 值到了但节点不跑, "保存本段并停止"失效。
 *
 * 修法: 包装 app.queuePrompt, partial 提交时把图中每个 switch=false 的 route 节点
 * 假输出分支下游的输出节点并进 targets —— 假输出后面不管接什么节点(保存/预览/对比)都能被执行并拿到数据。
 *
 * 为什么只补假输出分支:
 * - 真输出分支(放大/重绘)本就是"下一个继续节点"的上游, 已被继续节点的 partial targets 覆盖, 无需处理;
 * - 假输出分支(保存并停止)是末端, 不会被任何 targets 覆盖, 只能由这里补;
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
 * @returns {boolean} true=真输出分支激活, false=假输出分支激活
 */
function getSwitchValue(node) {
  const w = node.widgets?.find((x) => x.name === "switch") ?? node.widgets?.[0];
  return !!w?.value;
}

/**
 * 从 route 节点假输出分支(slot0)下游 BFS, 收集输出节点(遇到继续节点停止)。
 * 收集到的节点 ID 在 partial 提交时并入 targets, 让假输出分支真正执行。
 *
 * @param {LGraphNode} routeNode route 节点
 * @returns {string[]} 输出节点的 ID 字符串数组(已去重); 一个都没有时返回空数组
 */
function collectFalseBranchOutputs(routeNode) {
  const out = routeNode.outputs?.[0]; // output_false = slot 0
  if (!out) return [];
  const targets = new Set();
  const visited = new Set();
  const queue = [];
  for (const linkId of out.links ?? []) {
    const link = getLink(routeNode.graph, linkId);
    if (link) queue.push(link.target_id);
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
 * 收集图中所有 switch=false 的 route 节点假输出分支的输出节点(去重)。
 *
 * @param {LGraph} graph 画布图对象
 * @returns {string[]} 输出节点的 ID 字符串数组
 */
function collectAllFalseBranchTargets(graph) {
  const targets = new Set();
  for (const n of graph?._nodes ?? []) {
    if (!isRouteNode(n)) continue;
    if (getSwitchValue(n)) continue; /* 只处理假输出分支(真分支由继续节点 targets 覆盖) */
    for (const t of collectFalseBranchOutputs(n)) targets.add(t);
  }
  return [...targets];
}

app.registerExtension({
  name: "FallingTS.Route",

  /**
   * 扩展初始化钩子: 包装全局提交入口 app.queuePrompt。
   * partial 提交(继续, queueNodeIds 非空)时, 把 switch=false 的 route 节点假输出分支
   * 下游的输出节点并进 targets, 让"保存本段并停止"真正执行。
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
});
