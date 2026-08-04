// FallingTS 继续节点前端 (2026-08-04 重构):
// 分段执行由前端 partial execution 控制, 后端继续节点纯透传。
//
// 行为:
// - 默认 Run 被拦截: 图中含继续节点时, 只提交"第一个继续节点之前"的部分执行,
//   执行到分段边界即正常完成 (任务显示 Completed);
// - 节点上单个按钮: 状态「继续」→ 点击后提交"本节点往后到下一个继续节点之前"
//   的部分执行 (前半段命中缓存不重跑), 按钮文字变为「重跑」;
// - 「重跑」: 先中断当前运行, 后端内部 run_token+1 破除缓存, 重新提交本段;
// - run_token 已移入后端内部, 前端不再显示。

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_CLASS = "FallingTSContinue";

function isContinueNode(node) {
  return node?.type === NODE_CLASS || node?.constructor?.comfyClass === NODE_CLASS;
}

function isOutputNode(node) {
  return node?.constructor?.nodeData?.output_node === true;
}

function getLink(graph, linkId) {
  return graph?.links?.[linkId] ?? null;
}

// 检查 node 是否依赖"执行序比 startNode 更靠后的继续节点"
// (若是, 它属于更靠后的分段, 不应在本段收集)
function dependsOnLaterContinue(node, startNode) {
  const visited = new Set();
  const queue = [];
  for (const inp of node.inputs ?? []) {
    const link = getLink(node.graph, inp.link);
    if (link) queue.push(link.origin_id);
  }
  while (queue.length) {
    const nid = queue.shift();
    if (visited.has(nid)) continue;
    visited.add(nid);
    const n = node.graph?.getNodeById?.(nid);
    if (!n) continue;
    if (isContinueNode(n) && nid !== startNode.id && (n.order ?? 0) > (startNode.order ?? 0)) {
      return true;
    }
    for (const inp of n.inputs ?? []) {
      const link = getLink(n.graph, inp.link);
      if (link) queue.push(link.origin_id);
    }
  }
  return false;
}

// 从 startNode 的下游 BFS: 收集输出节点, 遇到下一个继续节点停止
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
    if (isContinueNode(n)) continue; // 下一个继续节点: 该段到此为止
    if (isOutputNode(n) && !dependsOnLaterContinue(n, startNode)) {
      targets.add(String(n.id));
    }
    for (const out of n.outputs ?? []) {
      for (const linkId of out.links ?? []) {
        const link = getLink(n.graph, linkId);
        if (link) queue.push(link.target_id);
      }
    }
  }
  return [...targets];
}

// 从 startNode 的上游 BFS: 收集输出节点 (不含 startNode 自身及下游)
function collectOutputsBefore(startNode) {
  const targets = new Set();
  const visited = new Set();
  const queue = [];
  for (const inp of startNode.inputs ?? []) {
    const link = getLink(startNode.graph, inp.link);
    if (link) queue.push(link.origin_id);
  }
  while (queue.length) {
    const nid = queue.shift();
    if (visited.has(nid)) continue;
    visited.add(nid);
    const n = startNode.graph?.getNodeById?.(nid);
    if (!n) continue;
    if (isContinueNode(n)) continue; // 上游继续节点不再深入
    if (isOutputNode(n) && !dependsOnLaterContinue(n, startNode)) {
      targets.add(String(n.id));
    }
    for (const inp of n.inputs ?? []) {
      const link = getLink(n.graph, inp.link);
      if (link) queue.push(link.origin_id);
    }
  }
  return [...targets];
}

// 第一个继续节点 (按执行序 order 最小)
function firstContinueNode(graph) {
  const list = (graph?._nodes ?? []).filter((n) => isContinueNode(n));
  if (!list.length) return null;
  return [...list].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))[0];
}

async function queueSegment(targets, number = 0) {
  if (!targets?.length) return false;
  await app.queuePrompt(number, 1, { queueNodeIds: targets });
  return true;
}

// 默认 Run 被我们改成分段执行 (isPartialExecution=true) 后,
// ComfyUI 官方 nextValueForLinkedTarget 会跳过 randomize/increment/decrement,
// 导致种子不变、KSampler 一直命中缓存。这里在提交前手动执行一次值更新。
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

app.registerExtension({
  name: "FallingTS.Continue",

  async setup() {
    // 拦截默认 Run: 图中含继续节点时, 默认只执行第一段 (到第一个继续节点之前)
    const originalQueuePrompt = app.queuePrompt?.bind(app);
    if (originalQueuePrompt) {
      app.queuePrompt = async function (number, batch, opts = {}) {
        // 仅当调用方没有显式指定 queueNodeIds 时 (默认 Run / 自动队列),
        // 才把本次执行限制到"第一个继续节点之前"的第一段;
        // 「继续/重跑」按钮会显式传 queueNodeIds, 这里绝不能覆盖。
        if (!opts?.queueNodeIds?.length) {
          // 分段执行会跳过官方随机化, 手动先更新 randomize/increment/decrement
          randomizeValueControlWidgets(app.graph);
          const first = firstContinueNode(app.graph);
          if (first) {
            const targets = collectOutputsBefore(first);
            if (targets.length) {
              opts = { ...opts, queueNodeIds: targets };
            }
          }
        }
        return originalQueuePrompt(number, batch, opts);
      };
    }
  },

  nodeCreated(node) {
    if (!isContinueNode(node)) return;

    const stateKey = "proceedState";
    const getState = () => (node.properties?.[stateKey] === "rerun" ? "rerun" : "continue");
    const setState = (s) => {
      node.properties = node.properties || {};
      node.properties[stateKey] = s;
    };

    const btn = node.addWidget("button", "继续", null, async () => {
      const targets = collectOutputsAfter(node);
      if (!targets.length) {
        console.warn("[FallingTS] 该继续节点之后没有可执行的输出节点");
        return;
      }
      if (getState() === "continue") {
        try {
          await fetch(`/proceed/continue/${node.id}`, { method: "POST" });
          await queueSegment(targets);
          setState("rerun");
          btn.name = "重跑";
          app.graph.setDirtyCanvas(true, false);
        } catch (err) {
          console.error("[FallingTS] 继续失败:", err);
        }
      } else {
        // 重跑: 中断当前运行 -> run_token+1 破缓存 -> 重新提交本段
        try {
          try {
            const q = await api.getQueue();
            if (q?.queue_running?.length > 0) await api.interrupt();
          } catch {
            // 忽略
          }
          await fetch(`/proceed/restart/${node.id}`, { method: "POST" });
          await queueSegment(targets);
        } catch (err) {
          console.error("[FallingTS] 重跑失败:", err);
        }
      }
    });
  },
});
