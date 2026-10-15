// FallingTS 分组运行节点前端 (total 动态输入端口 + 「运行本组」按钮):
// - total 决定左侧输入端口个数 input1..inputN, 每个接本组一个输出节点(如自动保存图片);
// - 节点**没有输出端口**(后端 RETURN_TYPES 为空), 它只是"本组唯一执行锚点";
// - 点「运行本组」→ 以本节点 id 作 partial_execution_targets 提交 → 执行引擎从本节点
//   沿非 lazy 输入向上游遍历 → 只执行本组那一条流, 另一组不受影响(无需「继续」)。
//
// 为什么自己 fetch("/prompt") 而不是 app.queuePrompt(0, 1, [本节点id]):
// `api.queuePrompt` 的第 3 参数是**选项对象** `{partialExecutionTargets}`(驼峰),
// 传裸数组会被静默忽略、退化成**全量提交**(= 两套流都跑, 正是要避免的事)。
// 老前端 `app.queuePrompt` 恰好做了 `Array.isArray(n) ? {queueNodeIds:n} : n` 兼容,
// 但这是版本相关的实现细节, 不能依赖 —— 本插件其余 partial 提交(load_video/audio-trim)
// 一律直接 POST /prompt, 这里沿用同一口径(见 load_video.js 的 submitPartial)。
// 走 api.fetchApi 而非原生 fetch: auto_save_image.js 包装了它, 会往 body 注入工作流名
// (AutoSaveImage 的子目录解析依赖这个), 自己 fetch 会漏掉那层注入。

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_CLASS = "FallingTSRunGroup";
const MAX_INPUTS = 50;
const DEFAULT_TOTAL = 2;

/**
 * 读取节点 total widget 的当前值, 非法值回退默认, 再裁到 [1, MAX_INPUTS]。
 *
 * @param {LGraphNode} node 分组运行节点对象
 * @returns {number} 有效输入端口数(1 ~ MAX_INPUTS)
 */
function getTotal(node) {
  const w = node.widgets?.find((w) => w.name === "total");
  let v = w ? Math.floor(Number(w.value)) : DEFAULT_TOTAL;
  if (!Number.isFinite(v)) v = DEFAULT_TOTAL;
  return Math.min(MAX_INPUTS, Math.max(1, v));
}

/**
 * 判断输入槽是否为动态展开的组端口 (inputN), 排除 widget 槽。
 *
 * @param {object} input 输入槽对象
 * @returns {boolean} 是否动态组端口
 */
function isDynamicInput(input) {
  return !input.widget && /^input\d+$/.test(input.name || "");
}

/**
 * 按 total 对齐左侧输入端口 input1..inputN。
 *
 * 槽位稳定性: 只从尾部增删, 已有连线的槽位索引永不漂移。
 *
 * @param {LGraphNode} node 分组运行节点对象
 * @returns {void}
 */
function syncNode(node) {
  const total = getTotal(node);
  let dyn = (node.inputs ?? []).filter(isDynamicInput);
  while (dyn.length > total) {
    const slot = dyn[dyn.length - 1];
    node.removeInput(node.inputs.indexOf(slot));
    dyn = (node.inputs ?? []).filter(isDynamicInput);
  }
  while (dyn.length < total) {
    const idx = dyn.length + 1;
    node.addInput(`input${idx}`, "*");
    dyn = (node.inputs ?? []).filter(isDynamicInput);
  }
  for (let i = 0; i < dyn.length; i++) {
    dyn[i].localized_name = `输入 ${i + 1}`;
  }
  node.setDirtyCanvas?.(true, true);
}

/**
 * 节点高度收回自然高度(只缩不扩: 用户手动拉高的高度保留)。
 *
 * 后端声明 MAX_INPUTS 个可选输入, 新建节点时构造器会先加上全部端口并把初始高度撑高;
 * syncNode 按 total 删掉多余端口后需把多余高度收回。仅新建时生效: 加载工作流时
 * configure 恢复保存的高度, 不受影响。
 *
 * @param {LGraphNode} node 分组运行节点对象
 * @returns {void}
 */
function fitHeight(node) {
  const natural = node.computeSize?.();
  if (!natural || !node.size) return;
  if (node.size[1] > natural[1]) {
    node.setSize([node.size[0], natural[1]]);
  }
}

/**
 * 只提交「本组」的部分执行(partial execution): 以本节点为唯一执行目标。
 *
 * ⚠️ 不能写成 app.queuePrompt(0, 1, [node.id]): api.queuePrompt 的第 3 参数是
 * **选项对象** {partialExecutionTargets}(驼峰), 传裸数组会被静默忽略、退化成全量提交。
 * 这里与 load_video.js 的 submitPartial 同一口径直接 POST /prompt —— 只有这条路径
 * 能保证 partial_execution_targets 一定生效, 且能吃 auto_save_image.js 的工作流名注入。
 *
 * @param {LGraphNode} node 分组运行节点(唯一执行目标)
 * @returns {Promise<object>} 后端响应
 */
async function submitPartial(node) {
  const prompt = await app.graphToPrompt();
  const resp = await api.fetchApi("/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: api.clientId,
      prompt: prompt.output,
      partial_execution_targets: [String(node.id)],
      extra_data: { extra_pnginfo: { workflow: prompt.workflow } },
    }),
  });
  if (!resp.ok) {
    const t = await resp.text().catch(() => "");
    throw new Error(`HTTP ${resp.status} ${t.slice(0, 200)}`);
  }
  return resp.json();
}

/**
 * 「运行本组」: 以本节点为唯一 partial 目标提交, 只执行本组那一条流。
 *
 * 本节点是输出节点(OUTPUT_NODE)且输入非 lazy, 所以执行引擎会从本节点沿输入边
 * 向上游遍历, 把本组整条流拉起来执行; 另一组不在这个子图里, 不受影响。
 *
 * @param {LGraphNode} node 分组运行节点对象
 * @returns {Promise<void>} 提交流程
 */
async function runGroup(node) {
  const linked = (node.inputs ?? []).filter((i) => isDynamicInput(i) && i.link != null);
  if (!linked.length) {
    app.extensionManager.toast.add({
      severity: "warning",
      summary: "本节点还没有接入任何节点, 请先把本组各节点连到它的输入上",
      life: 3000,
    });
    return;
  }
  try {
    await submitPartial(node);
  } catch (err) {
    console.error("[FallingTS] 运行本组失败:", err);
    app.extensionManager.toast.add({
      severity: "error",
      summary: `运行本组失败: ${err?.message ?? err}`,
      life: 4000,
    });
    return;
  }
  node.graph?.setDirtyCanvas(true, false);
}

app.registerExtension({
  name: "FallingTS.RunGroup",

  /**
   * 节点定义注册前钩子: 给 FallingTSRunGroup 绑定 total → 输入端口联动。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    // ⚠️ 节点级 onWidgetChanged 的包装必须在**这一层**只做一次 ——
    // 它挂在 nodeType.prototype 上, 若写进 onNodeCreated 内部, 每创建一个节点
    // 就会把 prototype 上的旧实现再包一层, 同一次拖动里 syncNode 被调用 N 次。
    const onWidgetChanged = nodeType.prototype.onWidgetChanged;
    /**
     * 节点级 widget 变化钩子: total 变化时同步端口。
     *
     * 新前端某些输入路径不走 widget.callback, 这里兜底(两条都接也无害:
     * syncNode 是幂等的)。
     *
     * @returns {*} 原 onWidgetChanged 的返回值
     */
    nodeType.prototype.onWidgetChanged = function (widget, value, ...args) {
      const out = onWidgetChanged?.apply(this, arguments);
      if (widget?.name === "total") syncNode(this);
      return out;
    };

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 绑定 total 联动 + 追加「运行本组」按钮 + 按存档对齐端口。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const node = this;

      const widget = node.widgets?.find((w) => w.name === "total");
      if (widget) {
        const orig = widget.callback;
        /** widget 回调: total 变化后重新对齐输入端口。 */
        widget.callback = function (value) {
          const out = orig?.apply(this, arguments);
          syncNode(node);
          return out;
        };
      }

      // 运行按钮: 每个分组运行节点各一个, 点它只跑本组
      node.addWidget("button", "▶ 运行本组", null, async () => {
        await runGroup(node);
      });

      // 加载/还原工作流: configure 末尾按保存的 total 对齐端口
      const prevOnConfigure = node.onConfigure;
      /** configure 钩子: 工作流加载完成后按保存的 total 对齐端口。 */
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        syncNode(node);
      };

      syncNode(node);
      fitHeight(node);
      // 节点刚创建时输入可能还没完全就绪, 下一 tick 再对齐一次
      setTimeout(() => {
        syncNode(node);
        fitHeight(node);
      }, 0);
      return result;
    };
  },
});
