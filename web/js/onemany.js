// FallingTS 一对多选择节点前端联动 (多对一选择的镜像, 参考 selector.js 的 total/items 动态端口范式):
// - total 组数 (最少 1) = 左侧输入端口数 (每组一个 input_i, 第 1 组在前第 2 组在后), 端口标签 = 组号;
// - items 组名列表(英文逗号分隔)变化时, 实时同步 selection 下拉选项 (选项 = 所有组名);
// - 输出槽位: 前 2 个固定 selected (选中项) / index (索引), 其后 total × 组名数量
//   (第 i 组 = 每个组名一个输出, 端口标签循环为组名), 动态部分按 total×M 显隐, 增删只动尾部;
// - 旧布局迁移: 早期版本前 2 个槽位直接是 output_1/output_2 (无固定 selected/index),
//   加载旧工作流时整体后移 2 位补齐固定端口, 已有连线按端口名重接, 槽位含义永不漂移;
// - selection 选中项 (下拉框, 选项 = 组名, 可连线接多对一 选中项), 选中第 k 个组名 ->
//   第 i 组 input_i 路由到第 i 组该组名对应的输出, 第 i 组其余输出 None;
// - 关键(预加载): partial 提交(点「继续」)时, 把本节点每组「选中组名」对应的输出下游的输出节点
//   并入 targets, 让各组的选中分支下游真正执行 —— 与 route.js 补假分支同一机制。

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "FallingTSOneToMany";
const CONTINUE_CLASS = "FallingTSContinue";
const MAX_GROUPS = 50;
const MAX_OUTPUTS = 50;
const DEFAULT_TOTAL = 2;
const FIXED_OUTPUTS = 2; // 固定前 2 个输出: selected (选中项) / index (索引)

/**
 * 把逗号分隔文本拆成去空白的组名数组。
 *
 * @param {string} text 逗号分隔的组名文本
 * @returns {string[]} 去空白后的非空组名数组
 */
function splitItems(text) {
  return String(text ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * 读取节点 total widget 的当前组数, 非法值回退默认, 再裁到 [1, MAX_GROUPS]。
 *
 * @param {object} node 一对多节点对象
 * @returns {number} 有效组数(1 ~ MAX_GROUPS)
 */
function getTotal(node) {
  const w = node.widgets?.find((w) => w.name === "total");
  let v = w ? Math.floor(Number(w.value)) : DEFAULT_TOTAL;
  if (!Number.isFinite(v)) v = DEFAULT_TOTAL;
  return Math.min(MAX_GROUPS, Math.max(1, v));
}

/**
 * 判断输入槽是否为动态展开的组端口 (inputN), 排除 widget 槽 (items/total/selection)。
 *
 * @param {object} input 输入槽对象
 * @returns {boolean} 是否动态组端口
 */
function isDynamicInput(input) {
  return !input.widget && /^input\d+$/.test(input.name || "");
}

/**
 * 从新前端 widgetValue store 取节点某个 widget 的真实对象(优先), 否则返回 null。
 * 新前端 combo 渲染优先读 store 里的真实 widget (node.widgets 只是兼容层), 两层都要同步。
 *
 * @param {object} node 画布节点对象
 * @param {string} name widget 名(如 "selection")
 * @returns {object|null} store 里的真实 widget 对象; store 不可用时返回 null
 */
function getStoreWidget(node, name) {
  try {
    const el = document.getElementById("vue-app");
    const pinia = el?.__vue_app__?.config?.globalProperties?.$pinia;
    const store = pinia?._s?.get("widgetValue");
    const w = node.widgets?.find((w) => w.name === name);
    if (w?.widgetId && store?.getWidget) {
      return store.getWidget(w.widgetId) ?? null;
    }
  } catch {
    // store 不可用时退化为只更新 node.widgets
  }
  return null;
}

/**
 * 选中项 -> 组名索引: 按选中项匹配, 失配回退 0 (与后端 _resolve_index 一致)。
 *
 * @param {string[]} names 组名列表
 * @param {*} selection 选中项 (下拉选中的组名)
 * @returns {number} 0 ~ names.length-1 的组名索引
 */
function resolveSelectionIndex(names, selection) {
  const idx = names.indexOf(String(selection ?? "").trim());
  return idx >= 0 ? idx : 0;
}

/**
 * 旧布局迁移: 早期版本的输出槽位直接是 output_1..outputN (无前 2 个固定 selected/index),
 * 加载旧工作流时把动态端口整体后移 2 位, 补上固定端口, 已有连线按端口名重接。
 *
 * 步骤: 捕获各 outputN 端口的连线目标 -> 删除全部输出 -> 重建 selected/index + outputN
 * (outputN 由 syncNode 的尾部增删补齐) -> 按端口名把连线接回。新布局 (首槽位 = selected) 直接跳过。
 *
 * @param {object} node 一对多节点对象
 * @returns {void}
 */
function migrateLegacyLayout(node) {
  const outs = node.outputs ?? [];
  if (!outs.length || outs[0].name === "selected") return;
  const graph = node.graph;
  const captured = new Map(); // 端口名 outputN -> [{ targetId, targetSlot, type }]
  for (const o of outs) {
    if (!/^output_\d+$/.test(o.name || "")) continue;
    const targets = [];
    for (const linkId of o.links ?? []) {
      const link = getLink(graph, linkId);
      if (link?.target_id != null) {
        targets.push({ targetId: link.target_id, targetSlot: link.target_slot, type: link.type ?? "*" });
      }
    }
    if (targets.length) captured.set(o.name, targets);
  }
  while ((node.outputs ?? []).length) {
    node.removeOutput(node.outputs.length - 1);
  }
  node.addOutput("selected", "STRING");
  node.addOutput("index", "INT");
  for (const [name, targets] of captured) {
    const slot = (node.outputs ?? []).findIndex((o) => o.name === name);
    if (slot < 0) continue; // 该端口已被尾部增删裁掉 (total×M 变小), 连线丢弃
    for (const t of targets) {
      const targetNode = graph?.getNodeById?.(t.targetId);
      if (!targetNode) continue;
      node.connect(slot, targetNode, t.targetSlot, t.type);
    }
  }
}

/**
 * 按 total + items 对齐节点: 组输入端口 (total 个, 每组一个) + 固定 selected/index + total×M 输出端口
 * (按组名标注) + 下拉选项。
 *
 * 槽位稳定性: 输入只从尾部增删 (widget 槽之后追加); 输出 = 固定前 2 个 + 动态 total×M,
 * 动态部分只从尾部增删, 已有连线的槽位含义永不漂移 (旧布局经 migrateLegacyLayout 一次性后移)。
 *
 * @param {object} node 一对多节点对象
 * @returns {void}
 */
function syncNode(node) {
  const total = getTotal(node);
  const options = [...new Set(splitItems(node.widgets?.find((w) => w.name === "items")?.value))];
  const M = options.length;

  // 0) 旧布局迁移 (首槽位不是 selected 时整体后移 2 位, 连线按端口名重接)
  migrateLegacyLayout(node);

  // 1) selection 下拉选项同步 (兼容层 + widgetValue store 两层)
  //    选项 = 所有组名; 选中项越界 (改 items 后) 自动重置为第一组名
  const getOptions = () => [...new Set(splitItems(node.widgets?.find((w) => w.name === "items")?.value))];
  const applyTo = (widget) => {
    if (!widget) return;
    widget.options = { ...(widget.options || {}), values: getOptions };
    const opts = getOptions();
    if (widget.value !== "" && !opts.includes(widget.value)) {
      widget.value = opts[0] ?? "";
      widget.callback?.(widget.value);
    }
  };
  applyTo(node.widgets?.find((w) => w.name === "selection"));
  applyTo(getStoreWidget(node, "selection"));

  // 2) 动态组输入端口 input1..input_total (每组一个, 最多 MAX_GROUPS)
  //    类型恒为 * (ANY); 端口标签 = 组号 (组1..组total), 内部名称保持 inputN 供后端定位
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
    dyn[i].localized_name = `组${i + 1}`;
  }

  // 3) 输出端口: 固定 selected/index 2 个 + total × M (第 i 组 = 每个组名一个输出, 标签循环为组名,
  //    动态部分最多 MAX_OUTPUTS, 只动尾部)。后端声明 selected/index + output_1..output_MAX_OUTPUTS,
  //    未使用的动态端口被删除, 不进入 prompt
  const wantOutputs = M ? FIXED_OUTPUTS + Math.min(total * M, MAX_OUTPUTS) : FIXED_OUTPUTS;
  while ((node.outputs ?? []).length > wantOutputs) {
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs ?? []).length < wantOutputs) {
    const idx = (node.outputs ?? []).length + 1 - FIXED_OUTPUTS;
    node.addOutput(`output_${idx}`, "*");
  }
  node.outputs[0].localized_name = "选中项";
  node.outputs[1].localized_name = "索引";
  for (let i = 0; i < wantOutputs - FIXED_OUTPUTS; i++) {
    const nameIdx = M ? i % M : -1;
    node.outputs[FIXED_OUTPUTS + i].localized_name = M ? options[nameIdx] : `输出 ${i + 1}`;
  }

  node.setDirtyCanvas?.(true, true);
}

/**
 * 节点高度收回自然高度(只缩不扩: 用户手动拉高的高度保留)。
 *
 * 后端声明共 52 个输出 (固定 selected/index 2 + 动态 output_1..output_50), 新建节点时构造器
 * 先加上全部 52 个输出并把初始高度撑到容纳 52 个输出 (上千 px); syncNode 按 2 + total×M
 * 删掉多余端口后需把多余高度收回, 否则新建节点异常高大。仅新建时生效(onNodeCreated):
 * 加载工作流时 configure 恢复保存的高度, 不受影响。
 *
 * @param {object} node 一对多节点对象
 * @returns {void}
 */
function fitHeight(node) {
  const natural = node.computeSize?.();
  if (!natural || !node.size) return;
  if (node.size[1] > natural[1]) {
    node.setSize([node.size[0], natural[1]]);
  }
}

// ─── 判断/链路工具 (与 selector.js / route.js 同款) ─────────────────────────

/** 判断是否为「一对多」节点。 */
function isOneToManyNode(node) {
  return node?.type === NODE_CLASS || node?.constructor?.comfyClass === NODE_CLASS;
}

/** 判断是否为「继续节点」(分段边界, BFS 收集到此停止)。 */
function isContinueNode(node) {
  return node?.type === CONTINUE_CLASS || node?.constructor?.comfyClass === CONTINUE_CLASS;
}

/** 判断是否为「输出节点」(保存/预览等终端节点, nodeData.output_node === true)。 */
function isOutputNode(node) {
  return node?.constructor?.nodeData?.output_node === true;
}

/** 按 linkId 从图的链路表取链路对象(不存在/已断开时为 null)。 */
function getLink(graph, linkId) {
  return graph?.links?.[linkId] ?? null;
}

/**
 * 从本节点每组「选中组名」对应的输出 (第 i 组槽位 2 + i×M+k, 前 2 槽位为固定 selected/index) 下游 BFS,
 * 收集输出节点 (遇到继续节点停止)。收集到的节点 ID 在 partial 提交时并入 targets, 让各组的选中分支真正执行。
 *
 * @param {object} node 一对多节点对象
 * @returns {string[]} 输出节点 ID 字符串数组(已去重); 一个都没有时返回空数组
 */
function collectActiveBranchOutputs(node) {
  const total = getTotal(node);
  const names = splitItems(node.widgets?.find((w) => w.name === "items")?.value);
  const M = names.length;
  if (!M) return [];
  const k = resolveSelectionIndex(names, node.widgets?.find((w) => w.name === "selection")?.value);
  const outs = node.outputs ?? [];
  const targets = new Set();
  const visited = new Set();
  const queue = [];
  for (let i = 0; i < total; i++) {
    const slot = FIXED_OUTPUTS + i * M + k;
    const o = outs[slot];
    if (!o) continue;
    for (const linkId of o.links ?? []) {
      const link = getLink(node.graph, linkId);
      if (link) queue.push(link.target_id);
    }
  }
  while (queue.length) {
    const nid = queue.shift();
    if (visited.has(nid)) continue;
    visited.add(nid);
    const n = node.graph?.getNodeById?.(nid);
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
 * 收集图中所有一对多节点每组「选中组名」分支下游的输出节点(去重)。
 *
 * @param {object} graph 画布图对象
 * @returns {string[]} 输出节点 ID 字符串数组
 */
function collectAllTargets(graph) {
  const targets = new Set();
  for (const n of graph?._nodes ?? []) {
    if (!isOneToManyNode(n)) continue;
    for (const t of collectActiveBranchOutputs(n)) targets.add(t);
  }
  return [...targets];
}

app.registerExtension({
  name: "FallingTS.OneToMany",

  /**
   * 扩展初始化钩子: 包装全局提交入口 app.queuePrompt。
   * partial 提交(点「继续」, queueNodeIds 非空)时, 把图中每个一对多节点每组「选中组名」
   * 输出下游的输出节点并入 targets, 让各组的选中分支下游真正执行(预加载)。
   *
   * @returns {void}
   */
  async setup() {
    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    /**
     * 包装 queuePrompt: 只处理 partial 提交分支(队列 NodeIds 非空), 并入选中分支 targets。
     *
     * @param {number} number 提交次数
     * @param {number} batch 批次数
     * @param {Array<string>|undefined} queueNodeIds 继续节点显式指定的目标节点 ID 列表
     * @returns {Promise} 原始 queuePrompt 的返回值
     */
    app.queuePrompt = async function (number, batch, queueNodeIds) {
      if (queueNodeIds?.length) {
        const graph = app.graph ?? app.rootGraph;
        const targets = collectAllTargets(graph);
        if (targets.length) {
          queueNodeIds = [...new Set([...queueNodeIds, ...targets])];
        }
      }
      return orig(number, batch, queueNodeIds);
    };
  },

  /**
   * 节点定义注册前钩子: 给 FallingTSOneToMany 绑定 total/items → 输入端口/输出端口/下拉选项联动。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: total/items 变化时同步输入端口/输出端口/下拉选项; 加载工作流时按保存的值对齐。
     * selection 为标准下拉 widget (可连线, 接多对一 选中项), 选项由 items 实时生成。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const node = this;

      const bindWidget = (name) => {
        const widget = node.widgets?.find((w) => w.name === name);
        if (!widget) return;
        const orig = widget.callback;
        /** widget 回调: total/items 值变化后重新对齐输入端口/输出端口/下拉选项。 */
        widget.callback = function (value) {
          const out = orig?.apply(this, arguments);
          syncNode(node);
          return out;
        };
      };
      bindWidget("items");
      bindWidget("total");

      // 兜底: 新前端输入可能不走 widget.callback, 用节点级 onWidgetChanged 再同步一次
      const onWidgetChanged = nodeType.prototype.onWidgetChanged;
      /** 节点级 widget 变化钩子: total/items 变化时同步端口与下拉。 */
      nodeType.prototype.onWidgetChanged = function (widget, value, ...args) {
        const out = onWidgetChanged?.apply(this, arguments);
        if (widget?.name === "items" || widget?.name === "total") {
          syncNode(this);
        }
        return out;
      };

      // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次
      const prevOnConfigure = node.onConfigure;
      /** configure 钩子: 工作流加载完成后按保存的 total/items 对齐端口与下拉。 */
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        syncNode(node);
      };

      syncNode(node);
      fitHeight(node);
      // 节点刚创建时 widgetValue store 可能还没注册完成, 下一 tick 再同步一次
      setTimeout(() => {
        syncNode(node);
        fitHeight(node);
      }, 0);
      return result;
    };
  },
});
