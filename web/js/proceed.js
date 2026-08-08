// FallingTS 继续节点前端 (2026-08-08 重构: 节点缓存 + partial execution)。
//
// 行为:
// - 后端继续节点把收到的 any 缓存在节点上(新数据覆盖), 未放行时阻塞下游;
// - Run(默认): 先调 /proceed/reset 重置所有继续为阻塞并清缓存, 再全量提交 -> 生成段, #43 缓存+阻塞;
// - 点「继续」#N: 后端校验节点有缓存(否则报"没有上游数据")并放行;
//   前端断开 #N 的 any 输入(节点用自身缓存), partial_execution_targets =
//   "下一个继续节点之后"的输出节点 -> 执行子图穿过并到达下一个继续,
//   它收到本段预览输出 -> 缓存 -> 阻塞。于是从 #N 开始往下跑, 绝不从开头跑。
//
// 数据完全来自节点自身的缓存, 不依赖注入、不依赖全局缓存判断从哪跑。

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

// BFS 下游: 返回第一个遇到的继续节点 (下一个分段边界)
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

// 从 startNode 下游 BFS: 收集输出节点, 遇到下一个继续节点停止
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
    if (isContinueNode(n)) continue; // 遇到继续: 本段到此为止
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

app.registerExtension({
  name: "FallingTS.Continue",

  async setup() {
    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    app.queuePrompt = async function (number, batch, queueNodeIds) {
      // 默认 Run (无显式目标): 重置所有继续为阻塞并清缓存, 再全量提交
      if (!queueNodeIds?.length) {
        try {
          await fetch("/proceed/reset", { method: "POST" });
        } catch {
          // 忽略
        }
      }
      return orig(number, batch, queueNodeIds);
    };
  },

  nodeCreated(node) {
    if (!isContinueNode(node)) return;

    const btn = node.addWidget("button", "▶ 继续", null, async () => {
      // 1. 后端校验节点缓存并放行 (无缓存 -> 400 "没有上游数据")
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

      // 2. 确定本段 partial targets: 目标是"下一个继续节点之后"的输出节点
      //    (让执行子图穿过并到达下一个继续, 它收到本段预览输出 -> 缓存 -> 阻塞)
      const next = findNextContinue(node);
      const anchor = next ?? node;
      const targets = collectOutputsAfter(anchor);
      if (!targets.length) {
        console.warn("[FallingTS] 该继续节点之后没有输出节点");
        return;
      }

      // 3. 构建 prompt, 断开本继续节点的 any 输入 (节点用自身缓存, 上游不执行)
      let prompt = null;
      try {
        const gtp = app.graphToPrompt ? await app.graphToPrompt(app.graph) : null;
        prompt = gtp?.output ?? gtp;
      } catch {
        prompt = null;
      }
      if (!prompt || !prompt[String(node.id)]?.inputs) {
        console.error("[FallingTS] 无法构建 prompt");
        return;
      }
      delete prompt[String(node.id)].inputs.any; // any 是 optional, 断开 -> 节点返回缓存

      // 4. 提交 partial execution
      try {
        const resp = await api.fetchApi("/prompt", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt,
            client_id: api.client_id,
            partial_execution_targets: targets,
          }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => null);
          const msg = data?.error?.message || data?.error?.details || "继续提交失败";
          alert(`继续提交失败: ${msg}`);
          console.error("[FallingTS] /prompt 校验失败:", data);
          return;
        }
      } catch (err) {
        console.error("[FallingTS] 继续提交失败:", err);
        return;
      }
      app.graph.setDirtyCanvas(true, false);
    });
  },
});
