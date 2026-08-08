/**
 * FallingTS 继续节点前端 (2026-08-08 重构: 节点缓存 + partial execution)。
 *
 * 行为:
 * - 后端继续节点把收到的 any 缓存在节点上(新数据覆盖), 未放行时阻塞下游;
 * - Run(默认): 先调 /proceed/reset 重置所有继续为阻塞并清缓存, 手动推进一次种子,
 *   再按 partial 只提交到"第一个继续节点之后"的输出节点 -> 生成段, #43 缓存+阻塞;
 *   (partial 时官方跳过种子随机化, 上游缓存保持有效, 之后点「继续」不会重跑开头);
 * - 点「继续」#N: 后端校验节点有缓存(否则报"没有上游数据")并放行;
 *   #N 的 any 输入声明为 lazy, 后端 check_lazy_status 按放行状态决定不拉上游(节点用自身缓存),
 *   连线无需断开; partial_execution_targets = "下一个继续节点之后"的输出节点 ->
 *   执行子图穿过并到达下一个继续, 它收到本段预览输出 -> 缓存 -> 阻塞。于是从 #N 开始往下跑, 绝不从开头跑。
 *
 * 数据完全来自节点自身的缓存, 不依赖注入、不依赖全局缓存判断从哪跑。
 * 提交走 app.queuePrompt 标准队列流程(官方「队列所选输出节点」同款), 队列面板有记录、节点有执行流动动画。
 */

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "FallingTSContinue";

/**
 * 判断节点是否为「继续节点」, 兼容新旧前端两种节点类型标记方式(type / constructor.comfyClass)。
 *
 * @param {LGraphNode} node 画布节点对象
 * @returns {boolean} 是继续节点返回 true
 */
function isContinueNode(node) {
  return node?.type === NODE_CLASS || node?.constructor?.comfyClass === NODE_CLASS;
}

/**
 * 判断节点是否为「输出节点」(保存/预览等终端节点)。
 * 分段执行用它收集 partial execution 目标: 执行只需跑到这些节点为止。
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
 * @param {number} linkId 链路 ID(节点输出槽 links 数组里的元素)
 * @returns {object|null} 链路对象(含 source_id / target_id / target_slot / type 等), 不存在时为 null
 */
function getLink(graph, linkId) {
  return graph?.links?.[linkId] ?? null;
}

/**
 * BFS 沿输出链路向下游搜索, 返回第一个遇到的继续节点(下一个分段边界)。
 * 点「继续」时用来确定 partial execution 的锚点: 锚点之前的子图不执行。
 *
 * @param {LGraphNode} startNode 起始节点(通常是当前继续节点)
 * @returns {LGraphNode|null} 下游第一个继续节点; 下游没有继续节点时返回 null
 */
function findNextContinue(startNode) {
  const visited = new Set();
  const queue = [];
  for (const out of startNode.outputs ?? []) {
    for (const linkId of out.links ?? []) {
      const link = getLink(startNode.graph, linkId);
      if (link) queue.push(link.target_id);
    }
  }
  while (queue.length) {
    const nid = queue.shift();
    if (visited.has(nid)) continue;
    visited.add(nid);
    const n = startNode.graph?.getNodeById?.(nid);
    if (!n) continue;
    if (isContinueNode(n)) return n;
    for (const out of n.outputs ?? []) {
      for (const linkId of out.links ?? []) {
        const link = getLink(n.graph, linkId);
        if (link) queue.push(link.target_id);
      }
    }
  }
  return null;
}

/**
 * 从 startNode 下游 BFS, 收集所有输出节点, 遇到下一个继续节点即停止。
 * 收集到的节点 ID 数组作为 partial_execution_targets 传给 /prompt: 只执行本段的子图。
 *
 * @param {LGraphNode} startNode 锚点节点(通常是"下一个继续节点", 没有则取当前继续节点自身), 从其输出开始遍历
 * @returns {string[]} 输出节点的 ID 字符串数组(已去重); 一个都没有时返回空数组
 */
function collectOutputsAfter(startNode) {
  const targets = new Set();
  const visited = new Set();
  const queue = [];
  for (const out of startNode.outputs ?? []) {
    for (const linkId of out.links ?? []) {
      const link = getLink(startNode.graph, linkId);
      if (link) queue.push(link.target_id);
    }
  }
  while (queue.length) {
    const nid = queue.shift();
    if (visited.has(nid)) continue;
    visited.add(nid);
    const n = startNode.graph?.getNodeById?.(nid);
    if (!n) continue;
    if (isContinueNode(n)) continue; /* 遇到继续: 本段到此为止 */
    if (isOutputNode(n)) targets.add(String(n.id));
    for (const out of n.outputs ?? []) {
      for (const linkId of out.links ?? []) {
        const link = getLink(n.graph, linkId);
        if (link) queue.push(link.target_id);
      }
    }
  }
  return [...targets];
}

/**
 * 手动推进一次 control_after_generate 种子 (randomize/increment/decrement)。
 * 分段执行(partial)时 ComfyUI 官方 nextValueForLinkedTarget 会跳过随机化
 * (settingStore: if(e.isPartialExecution) return), 导致种子不变、上游 KSampler 一直命中缓存 ——
 * 默认 Run 改成 partial 后, 这里在提交前手动更新一次, 保证每次 Run 都能出新的生成结果。
 *
 * @param {LGraph} graph 画布图对象(与提交时 app.queuePrompt 读取的同一张图)
 * @returns {void}
 */
function randomizeValueControlWidgets(graph) {
  const vc = window.comfyAPI?.valueControl;
  if (!vc?.computeNextControlledValue) return;
  for (const node of graph?._nodes ?? []) {
    for (const w of node.widgets ?? []) {
      if (!w.name?.includes("control_after_generate")) continue;
      const mode = w.value;
      if (mode === "fixed") continue;
      const linked = (w.linkedWidgets ?? []).find((x) => x !== w);
      if (!linked || typeof linked.value !== "number") continue;
      const next = vc.computeNextControlledValue(linked, mode, { nodeId: node.id });
      if (next !== undefined) {
        linked.value = next;
        linked.callback?.(next);
      }
    }
  }
}

/**
 * 找到图中第一个继续节点(按画布执行序 order 最小)。
 * 默认 Run 用它确定"只执行到第一个继续节点为止"的 partial targets。
 *
 * @param {LGraph} graph 画布图对象
 * @returns {LGraphNode|null} 第一个继续节点; 图中没有继续节点时返回 null
 */
function firstContinueNode(graph) {
  const list = (graph?._nodes ?? []).filter((n) => isContinueNode(n));
  if (!list.length) return null;
  return [...list].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))[0];
}

app.registerExtension({
  name: "FallingTS.Continue",

  /**
   * 扩展初始化钩子: 包装全局提交入口 app.queuePrompt。
   * 默认 Run(未显式指定目标节点)时, 先 POST /proceed/reset 重置继续节点并清缓存, 手动推进种子,
   * 再按 partial 提交到第一个继续之后 —— 保证每次 Run 重新分段、出新的生成结果、上游缓存保持有效。
   *
   * @returns {void}
   */
  async setup() {
    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    /**
     * 包装 queuePrompt: 拦截"默认 Run"(queueNodeIds 为空)分支。
     * 分段执行的工作流里, Run 被改为"只执行到第一个继续节点为止"的 partial:
     * 1. POST /proceed/reset 把所有继续节点重置为阻塞并清空缓存(重新从头分段);
     * 2. randomizeValueControlWidgets 手动推进一次种子 —— partial 会跳过官方随机化,
     *    不手动推进的话每次 Run 种子不变、出图相同;
     * 3. collectOutputsAfter(第一个继续) 作为 partial targets 提交, 让第一个继续节点执行并
     *    缓存本段输出、阻断后续段 —— partial(isPartialExecution=true)时上游缓存保持有效,
     *    之后点「继续」不会重跑开头。
     * 「继续」按钮会显式传 queueNodeIds(非空), 这里绝不覆盖。
     *
     * @param {number} number 提交次数
     * @param {number} batch 批次数
     * @param {Array<string>|undefined} queueNodeIds 「继续」按钮显式指定的目标节点 ID 列表, 非空时跳过 Run 拦截
     * @returns {Promise} 原始 queuePrompt 的返回值(提交任务后的 Promise)
     */
    app.queuePrompt = async function (number, batch, queueNodeIds) {
      /* 默认 Run (无显式目标): 重置继续节点 -> 手动推进种子 -> partial 提交到第一个继续之后 */
      if (!queueNodeIds?.length) {
        try {
          await fetch("/proceed/reset", { method: "POST" });
        } catch {
          /* 忽略 */
        }
        const graph = app.graph ?? app.rootGraph;
        if (graph && graph._nodes?.some((n) => isContinueNode(n))) {
          randomizeValueControlWidgets(graph);
          const first = firstContinueNode(graph);
          if (first) {
            const targets = collectOutputsAfter(first);
            if (targets.length) {
              return orig(number, batch, targets);
            }
          }
        }
      }
      return orig(number, batch, queueNodeIds);
    };
  },

  /**
   * 节点创建钩子: 只对「继续节点」生效, 在节点上添加「▶ 继续」按钮。
   *
   * @param {LGraphNode} node 新创建的节点对象
   * @returns {void}
   */
  nodeCreated(node) {
    if (!isContinueNode(node)) return;

    /**
     * 「▶ 继续」按钮点击处理: 放行本节点 -> 只执行本段子图 -> 停在下个继续节点。
     * 回调参数: 无(addWidget 内部触发, 回调不接收事件对象)。
     * @returns {Promise<void>} 整段"放行 + partial 提交"的异步流程
     */
    const btn = node.addWidget("button", "▶ 继续", null, async () => {
      /* 1. 后端校验节点缓存并放行 (无缓存 -> 400 "没有上游数据") */
      try {
        const resp = await fetch(`/proceed/continue/${node.id}`, { method: "POST" });
        if (!resp.ok) {
          const data = await resp.json().catch(() => null);
          alert(data?.message ?? "没有上游数据, 请先运行到该节点");
          return;
        }
      } catch (err) {
        console.error("[FallingTS] 继续失败:", err);
        alert("继续失败: 无法连接后端");
        return;
      }

      /* 2. 确定本段 partial targets: 目标是"下一个继续节点之后"的输出节点
            (让执行子图穿过并到达下一个继续, 它收到本段预览输出 -> 缓存 -> 阻塞) */
      const next = findNextContinue(node);
      const anchor = next ?? node;
      const targets = collectOutputsAfter(anchor);
      if (!targets.length) {
        console.warn("[FallingTS] 该继续节点之后没有输出节点");
        return;
      }

      /* 3. 提交 partial execution: 走标准队列流程 app.queuePrompt(number, batch, nodeIds)
            (官方「队列所选输出节点」同款) —— 内部自动 graphToPrompt 当前画布, 并把 nodeIds
            转成 partial_execution_targets 发给 /prompt; 队列面板有记录、节点有执行流动动画。
            第二个参数 batch=1: 每次「继续」只跑本段一遍。 */
      try {
        await app.queuePrompt(0, 1, targets);
      } catch (err) {
        console.error("[FallingTS] 继续提交失败:", err);
        return;
      }
      app.graph.setDirtyCanvas(true, false);
    });
  },
});
