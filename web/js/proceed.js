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
  // 部署版前端 app.queuePrompt 第 3 参即 queueNodeIds 数组 (非 options 对象)
  await app.queuePrompt(number, 1, targets);
  return true;
}

// 取 nodeOutput store (与 node_image_middleclick.js 同一访问方式)
function getNodeOutputStore() {
  try {
    const el = document.getElementById("vue-app");
    const pinia = el?.__vue_app__?.config?.globalProperties?.$pinia;
    return pinia?._s?.get("nodeOutput") ?? null;
  } catch {
    return null;
  }
}

// 沿继续节点输入链路上溯, 跳过其它继续节点, 找最近的"有资源数据"的节点
// (输出节点在 store 里有 images/audio/video 记录; 数据存在 -> 可用 temp 路径回灌)
function findPreviousDataNode(node) {
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
    if (isContinueNode(n)) continue; // 上游继续节点不再深入
    const store = getNodeOutputStore();
    const out = store?.getNodeOutputs?.(n);
    if (
      out &&
      ((Array.isArray(out.images) && out.images.length) ||
        (Array.isArray(out.audio) && out.audio.length) ||
        (Array.isArray(out.video) && out.video.length))
    ) {
      return n;
    }
    for (const inp of n.inputs ?? []) {
      const link = getLink(n.graph, inp.link);
      if (link) queue.push(link.origin_id);
    }
  }
  return null;
}

// 取上一节点的第一个资源文件, 并判断类型
function getPreviousResult(prevNode) {
  const store = getNodeOutputStore();
  const out = store?.getNodeOutputs?.(prevNode);
  if (!out) return null;
  if (Array.isArray(out.images) && out.images.length) {
    const f = out.images[0];
    if (f && typeof f.filename === "string") return { kind: "IMAGE", file: f };
  }
  if (Array.isArray(out.audio) && out.audio.length) {
    const f = out.audio[0];
    if (f && typeof f.filename === "string") return { kind: "AUDIO", file: f };
  }
  if (Array.isArray(out.video) && out.video.length) {
    const f = out.video[0];
    if (f && typeof f.filename === "string") return { kind: "VIDEO", file: f };
  }
  return null;
}

// 拼 annotated 路径: 例如 "ComfyUI_temp_xxx.png [temp]" / "sub/f.png [output]"
function annotatedFilePath(file) {
  const name = file.subfolder
    ? String(file.subfolder).replace(/\\/g, "/") + "/" + file.filename
    : file.filename;
  const tag =
    file.type === "input"
      ? "[input]"
      : file.type === "output"
        ? "[output]"
        : "[temp]";
  return name + " " + tag;
}

// 回灌模式: 上一段有资源数据时, 注入加载节点直接读 temp/output 文件,
// 把继续节点输入指向它, 提交本段 partial_execution_targets -> 上游完全不执行。
async function queueSegmentFromPrevious(node, targets) {
  if (!targets?.length) return false;
  const prev = findPreviousDataNode(node);
  const res = prev ? getPreviousResult(prev) : null;
  if (!res) return false;

  let gtp = null;
  try {
    gtp = app.graphToPrompt ? await app.graphToPrompt(app.graph) : null;
  } catch {
    gtp = null;
  }
  const prompt = gtp?.output ?? gtp;
  const nodeKey = String(node.id);
  if (!prompt || !prompt[nodeKey]) return false;

  const loaderId = "mlz_prev_" + node.id;
  const path = annotatedFilePath(res.file);
  if (res.kind === "IMAGE") {
    prompt[loaderId] = { class_type: "LoadImage", inputs: { image: path } };
  } else if (res.kind === "AUDIO") {
    prompt[loaderId] = { class_type: "LoadAudio", inputs: { audio: path } };
  } else if (res.kind === "VIDEO") {
    prompt[loaderId] = { class_type: "LoadVideo", inputs: { file: path } };
  } else {
    return false;
  }
  prompt[nodeKey].inputs.any = [loaderId, 0];

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
    if (!resp.ok) return false; // 校验失败(如 temp 文件已被清理) -> 回退缓存模式
    return true;
  } catch {
    return false;
  }
}

// 默认 Run 被我们改成分段执行 (isPartialExecution=true) 后,
// ComfyUI 官方 nextValueForLinkedTarget 会跳过 randomize/increment/decrement,
// 导致种子不变、KSampler 一直命中缓存。这里在提交前手动执行一次值更新。
function randomizeValueControlWidgets(graph) {
  const vc = window.comfyAPI?.valueControl;
  if (!vc?.computeNextControlledValue) return;
  for (const node of graph?._nodes ?? []) {
    for (const w of node.widgets ?? []) {
      // 与官方 nextValueForLinkedTarget 方向一致: 从 value widget 出发,
      // 在它的 linkedWidgets 里找 control_after_generate 控件
      // (KSampler 自带 seed 只有 value->control 单向关联, 反向查找会漏掉)
      const control = (w.linkedWidgets ?? []).find(
        (x) => x !== w && x.name?.includes("control_after_generate")
      );
      if (!control) continue;
      const mode = control.value;
      if (mode === "fixed") continue;
      if (typeof w.value !== "number") continue;
      const next = vc.computeNextControlledValue(w, mode, { nodeId: node.id });
      if (next !== undefined) {
        w.value = next;
        w.callback?.(next);
      }
    }
  }
}

// 状态图标: 直接放在按钮文字前面 (▶ 可继续 / ↻ 可重跑),
// 两种渲染模式都显示在按钮控件上, 不再单独绘制 icon。
const BTN_LABEL_CONTINUE = "\u25b6 \u7ee7\u7eed"; // ▶ 继续
const BTN_LABEL_RERUN = "\u21bb \u91cd\u8dd1"; // ↻ 重跑

app.registerExtension({
  name: "FallingTS.Continue",

  async setup() {
    // 拦截默认 Run: 图中含继续节点时, 默认只执行第一段 (到第一个继续节点之前)
    const originalQueuePrompt = app.queuePrompt?.bind(app);
    if (originalQueuePrompt) {
      app.queuePrompt = async function (number, batch, queueNodeIds) {
        // 仅当调用方没有显式指定 queueNodeIds 时 (默认 Run / 自动队列),
        // 才把本次执行限制到"第一个继续节点之前"的第一段;
        // 「继续/重跑」按钮会显式传 queueNodeIds, 这里绝不能覆盖。
        if (!queueNodeIds?.length) {
          // 分段执行会跳过官方随机化, 手动先更新 randomize/increment/decrement
          randomizeValueControlWidgets(app.graph);
          const first = firstContinueNode(app.graph);
          if (first) {
            const targets = collectOutputsBefore(first);
            if (targets.length) {
              queueNodeIds = targets;
            }
          }
        }
        // 部署版前端第 3 参即数组 (非 options 对象), 直接透传
        return originalQueuePrompt(number, batch, queueNodeIds);
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
      btn.name = s === "rerun" ? BTN_LABEL_RERUN : BTN_LABEL_CONTINUE;
      btn.label = btn.name;
    };

    const btn = node.addWidget("button", BTN_LABEL_CONTINUE, null, async () => {
      const targets = collectOutputsAfter(node);
      if (!targets.length) {
        console.warn("[FallingTS] 该继续节点之后没有可执行的输出节点");
        return;
      }
      if (getState() === "continue") {
        try {
          await fetch(`/proceed/continue/${node.id}`, { method: "POST" });
          const usedPrev = await queueSegmentFromPrevious(node, targets);
          if (!usedPrev) await queueSegment(targets); // 无上一段数据/失败时保持缓存模式
          setState("rerun");
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
