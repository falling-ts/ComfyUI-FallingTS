import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_CLASS = "FallingTSContinue";
const PAUSED_COLOR = "#8b6914";

const postContinue = (id) => fetch(`/fallingts_continue/continue/${id}`, { method: "POST" });
const postRestart = (id) => fetch(`/fallingts_continue/restart/${id}`, { method: "POST" });
const postCancelAll = () => fetch("/fallingts_continue/cancel_all", { method: "POST" });

function setPaused(node, paused) {
  node.bgcolor = paused ? PAUSED_COLOR : undefined;
  app.graph.setDirtyCanvas(true, false);
}

app.registerExtension({
  name: "FallingTS.Continue",

  async setup() {
    api.addEventListener("fallingts_continue_paused", ({ detail }) => {
      const node = app.graph.getNodeById(String(detail.node_id));
      if (!node || node.comfyClass !== NODE_CLASS) return;
      setPaused(node, true);
    });

    // 全局中断(⏹)时, 唤醒所有被我们暂停的节点, 避免卡死
    const original_api_interrupt = api.interrupt;
    api.interrupt = function (...args) {
      postCancelAll();
      return original_api_interrupt.apply(this, args);
    };
  },

  nodeCreated(node) {
    if (node.comfyClass !== NODE_CLASS) return;

    node.addWidget("button", "▶ 继续", null, () => {
      setPaused(node, false);
      postContinue(node.id);
    });

    node.addWidget("button", "↻ 重跑(从本节点)", null, async () => {
      try {
        // 1) 标记重跑: 若本节点正暂停, 先取消当前运行
        await postRestart(node.id);
        // 2) 中断下游(若正在运行)
        api.interrupt();
        // 3) run_token +1 破除缓存, 重新入队 (上游已缓存, 从本节点开始重跑)
        const tokenWidget = node.widgets.find((w) => w.name === "run_token");
        if (tokenWidget) {
          tokenWidget.value = (Number(tokenWidget.value) || 0) + 1;
        }
        const p = await app.graphToPrompt();
        if (p?.output?.[String(node.id)]) {
          p.output[String(node.id)].inputs.run_token = Number(tokenWidget?.value) || 0;
        }
        setPaused(node, false);
        await api.queuePrompt(0, { output: p.output, workflow: p.workflow });
      } catch (err) {
        console.error("[FallingTS Continue] 重跑失败:", err);
      }
    });
  },
});
