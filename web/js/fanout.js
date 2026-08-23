// FallingTS 扇出选择节点前端联动 (多对一选择的镜像, 参考 selector.js 的 total/items 动态端口范式):
// - total 组数 (最少 1) = 左侧输入端口数 (每组一个 input_i, 第 1 组在前第 2 组在后), 端口标签 = 输入N;
// - items 组名列表(英文逗号分隔)变化时, 实时同步 selection 下拉选项 (选项 = 所有组名);
// - 输出槽位: total × 组名数量 (第 i 组 = 每个组名一个输出, 端口标签循环为组名), 按 total×M 显隐;
//   增删只动尾部, 已有连线的槽位索引永不漂移;
// - selection 选中项 (下拉框, 选项 = 组名), 槽位类型同步为 STRING,INT (多类型, 逗号匹配) ->
//   可连线接多对一 选中项 (STRING 组名) 或 索引 (INT, 0 起, 传入索引直接选中所属索引的组名),
//   选中第 k 个组名 -> 第 i 组 input_i 路由到第 i 组该组名对应的输出, 第 i 组其余输出 None;
// - 陈旧输入槽自愈: 旧版单一输入 value 遗留槽 (保存的工作流会原样保留) 在加载/同步时自动移除,
//   节点左侧只剩 输入1..输入total + widget 控件;
// - 关键(预加载): partial 提交(点「继续」)时, 把本节点每组「选中组名」对应的输出下游的输出节点
//   并入 targets, 让各组的选中分支下游真正执行 —— 与 route.js 补假分支同一机制。
// - 关键(拦截): 提交时按 partial_execution_targets(「继续」同款机制)拦截未选中分支 ——
//   未选中组名槽位下游的输出节点不进 targets, 引擎不调度, 根本不执行(不产生 None 下游):
//   - partial 提交(点「继续」): 从 targets 中剔除未选中分支下游输出节点;
//   - 全量 Run(图中无继续节点): 显式列出「全部输出节点 - 未选中分支下游输出节点」提交;
//   - selection 已连线时值运行时才确定, 无法预知选中哪条分支 -> 不拦截, 靠下游 None 容忍兜底。

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "FallingTSFanout";
const CONTINUE_CLASS = "FallingTSContinue";
const MAX_GROUPS = 50;
const MAX_OUTPUTS = 50;
const DEFAULT_TOTAL = 2;

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
 * @param {object} node 扇出节点对象
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
 * 选中项 -> 组名索引: 传入索引 (number, 0 起) 直接取该索引; 传入组名 (string) 按名匹配;
 * 失配/越界回退 0 (与后端 _resolve_index 一致)。
 *
 * @param {string[]} names 组名列表
 * @param {*} selection 选中项 (下拉选中的组名, 或连线传入的索引)
 * @returns {number} 0 ~ names.length-1 的组名索引
 */
function resolveSelectionIndex(names, selection) {
  if (typeof selection === "number" && Number.isFinite(selection)) {
    const k = Math.floor(selection);
    return k >= 0 && k < names.length ? k : 0;
  }
  const idx = names.indexOf(String(selection ?? "").trim());
  return idx >= 0 ? idx : 0;
}

/**
 * 按 total + items 对齐节点: 组输入端口 (total 个, 每组一个) + total×M 输出端口 (按组名标注) + 下拉选项
 * + 陈旧非 widget 输入槽清理 (旧版 value 遗留)。
 *
 * 槽位稳定性: 输入只从尾部增删 (widget 槽之后追加); 输出按 total×M 追加, 只从尾部增删,
 * 已有连线的槽位索引永不漂移。
 *
 * @param {object} node 扇出节点对象
 * @returns {void}
 */
function syncNode(node) {
  const total = getTotal(node);
  const options = [...new Set(splitItems(node.widgets?.find((w) => w.name === "items")?.value))];
  const M = options.length;

  // 1) selection 下拉选项同步 (兼容层 + widgetValue store 两层)
  //    选项 = 所有组名; 选中项越界 (改 items 后) 自动重置为第一组名
  const getOptions = () => [...new Set(splitItems(node.widgets?.find((w) => w.name === "items")?.value))];
  const applyTo = (widget) => {
    if (!widget) return;
    widget.options = { ...(widget.options || {}), values: getOptions };
    const opts = getOptions();
    if (typeof widget.value === "string" && widget.value !== "" && !opts.includes(widget.value)) {
      widget.value = opts[0] ?? "";
      widget.callback?.(widget.value);
    }
  };
  applyTo(node.widgets?.find((w) => w.name === "selection"));
  applyTo(getStoreWidget(node, "selection"));

  // 2) 陈旧输入槽清理: 本节点合法输入 = 3 个 widget 槽 (items/total/selection) + total 个组端口
  //    (input1..input_total); 其余非 widget 槽 (如旧版单一输入 value 遗留, 保存的工作流会原样保留)
  //    直接移除, 加载/同步时自愈, 左侧只剩 输入1..输入total
  for (const slot of [...(node.inputs ?? [])]) {
    if (!slot.widget && !/^input\d+$/.test(slot.name || "")) {
      node.removeInput(node.inputs.indexOf(slot));
    }
  }

  // 2b) selection 槽类型 -> "STRING,INT" (新前端 isValidConnection 按逗号多类型匹配):
  //     多对一 选中项 (STRING 组名) 与 索引 (INT, 0 起) 均可连入; 下拉 widget 保留 (选项 = 组名),
  //     未连线时手动选组名, 连线传索引时后端直接选中所属索引的组名
  const selSlot = (node.inputs ?? []).find((i) => i.name === "selection");
  if (selSlot && selSlot.type !== "STRING,INT") {
    selSlot.type = "STRING,INT";
  }

  // 3) 动态组输入端口 input1..input_total (每组一个, 最多 MAX_GROUPS)
  //    类型恒为 * (ANY); 端口标签 = 输入N (输入1..输入total), 内部名称保持 inputN 供后端定位
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
    dyn[i].localized_name = `输入${i + 1}`;
  }

  // 4) 输出端口: total × M (第 i 组 = 每个组名一个输出, 标签循环为组名, 最多 MAX_OUTPUTS, 只动尾部)
  //    后端声明 output_1..output_MAX_OUTPUTS, 未使用的端口被删除, 不进入 prompt
  const wantOutputs = M ? Math.min(total * M, MAX_OUTPUTS) : 0;
  while ((node.outputs ?? []).length > wantOutputs) {
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs ?? []).length < wantOutputs) {
    const idx = (node.outputs ?? []).length + 1;
    node.addOutput(`output_${idx}`, "*");
  }
  for (let i = 0; i < wantOutputs; i++) {
    const nameIdx = M ? i % M : -1;
    node.outputs[i].localized_name = M ? options[nameIdx] : `输出 ${i + 1}`;
  }

  node.setDirtyCanvas?.(true, true);
}

/**
 * 节点高度收回自然高度(只缩不扩: 用户手动拉高的高度保留)。
 *
 * 后端声明 MAX_OUTPUTS=50 个输出, 新建节点时构造器先加上全部 50 个输出并把初始高度
 * 撑到容纳 50 个输出 (上千 px); syncNode 按 total×M 删掉多余端口后需把多余高度收回,
 * 否则新建节点异常高大。仅新建时生效(onNodeCreated): 加载工作流时 configure 恢复
 * 保存的高度, 不受影响。
 *
 * @param {object} node 扇出节点对象
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

/** 判断是否为「扇出」节点。 */
function isFanoutNode(node) {
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
 * 从本节点每组「选中组名」对应的输出 (第 i 组槽位 i×M+k) 下游 BFS, 收集输出节点
 * (遇到继续节点停止)。收集到的节点 ID 在 partial 提交时并入 targets, 让各组的选中分支真正执行。
 * selection 已连线时, 运行时值 (组名/索引) 执行时才确定, 无法预知选中哪条分支 -> 每组全部组名分支都收集。
 *
 * @param {object} node 扇出节点对象
 * @returns {string[]} 输出节点 ID 字符串数组(已去重); 一个都没有时返回空数组
 */
function collectActiveBranchOutputs(node) {
  const total = getTotal(node);
  const names = splitItems(node.widgets?.find((w) => w.name === "items")?.value);
  const M = names.length;
  if (!M) return [];
  const k = resolveSelectionIndex(names, node.widgets?.find((w) => w.name === "selection")?.value);
  const selSlot = (node.inputs ?? []).find((i) => i.name === "selection");
  const connected = selSlot?.link != null;
  const outs = node.outputs ?? [];
  const targets = new Set();
  const visited = new Set();
  const queue = [];
  for (let i = 0; i < total; i++) {
    const start = connected ? i * M : i * M + k;
    const end = connected ? i * M + M : start + 1;
    for (let slot = start; slot < end; slot++) {
      const o = outs[slot];
      if (!o) continue;
      for (const linkId of o.links ?? []) {
        const link = getLink(node.graph, linkId);
        if (link) queue.push(link.target_id);
      }
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
 * 收集图中所有扇出节点每组「选中组名」分支下游的输出节点(去重)。
 *
 * @param {object} graph 画布图对象
 * @returns {string[]} 输出节点 ID 字符串数组
 */
function collectAllTargets(graph) {
  const targets = new Set();
  for (const n of graph?._nodes ?? []) {
    if (!isFanoutNode(n)) continue;
    for (const t of collectActiveBranchOutputs(n)) targets.add(t);
  }
  return [...targets];
}

/**
 * 收集图中所有输出节点(保存/预览等终端节点)的 ID(去重)。
 *
 * @param {object} graph 画布图对象
 * @returns {string[]} 输出节点 ID 字符串数组
 */
function collectAllOutputNodes(graph) {
  const ids = new Set();
  for (const n of graph?._nodes ?? []) {
    if (isOutputNode(n)) ids.add(String(n.id));
  }
  return [...ids];
}

/**
 * 计算应被拦截(不进执行 targets)的「未选中组名槽位下游输出节点」ID。
 *
 * 规则(保守): 输出节点在某扇出节点未选中槽位下游、且不在任何扇出节点选中槽位下游 -> 拦截;
 * 选中/未选中分支都下游到它(混合)或只在选中分支下游 -> 保留(执行, 收 None 由下游容忍兜底)。
 * selection 已连线时运行时值(组名/索引)才确定, 无法预知选中哪条分支 -> 该节点不做拦截。
 *
 * @param {object} graph 画布图对象
 * @returns {string[]} 被拦截的输出节点 ID 字符串数组
 */
function collectBlockedOutputNodes(graph) {
  const fanouts = (graph?._nodes ?? []).filter(isFanoutNode);
  if (!fanouts.length) return [];
  const unselSets = [];
  const selSets = [];
  for (const f of fanouts) {
    const selSlot = (f.inputs ?? []).find((i) => i.name === "selection");
    const names = splitItems(f.widgets?.find((w) => w.name === "items")?.value);
    const M = names.length;
    const unsel = new Set();
    const sel = new Set();
    // selection 未连线且组名非空: 选中项 = widget 当前值 (与后端 _resolve_index 一致)
    if (selSlot?.link == null && M) {
      const total = getTotal(f);
      const k = resolveSelectionIndex(names, f.widgets?.find((w) => w.name === "selection")?.value);
      /** 从某输出槽下游 BFS 收集节点(遇到继续节点停止, 与 collectActiveBranchOutputs 同款)。 */
      const bfs = (slot, set) => {
        const o = f.outputs?.[slot];
        if (!o) return;
        const visited = new Set();
        const queue = [];
        for (const linkId of o.links ?? []) {
          const link = getLink(f.graph, linkId);
          if (link) queue.push(link.target_id);
        }
        while (queue.length) {
          const nid = queue.shift();
          if (visited.has(nid)) continue;
          visited.add(nid);
          const n = f.graph?.getNodeById?.(nid);
          if (!n) continue;
          if (isContinueNode(n)) continue; /* 遇到继续: 本段到此为止 */
          set.add(nid);
          for (const out of n.outputs ?? []) {
            for (const linkId of out.links ?? []) {
              const link = getLink(n.graph, linkId);
              if (link) queue.push(link.target_id);
            }
          }
        }
      };
      for (let i = 0; i < total; i++) {
        for (let s = 0; s < M; s++) {
          bfs(i * M + s, s === k ? sel : unsel);
        }
      }
    }
    unselSets.push(unsel);
    selSets.push(sel);
  }
  const blocked = new Set();
  for (const n of graph?._nodes ?? []) {
    if (!isOutputNode(n)) continue;
    const id = String(n.id);
    let inUnsel = false;
    let inSel = false;
    for (let j = 0; j < unselSets.length; j++) {
      if (unselSets[j].has(id)) inUnsel = true;
      if (selSets[j].has(id)) inSel = true;
    }
    if (inUnsel && !inSel) blocked.add(id);
  }
  return [...blocked];
}

app.registerExtension({
  name: "FallingTS.Fanout",

  /**
   * 扩展初始化钩子: 包装全局提交入口 app.queuePrompt。
   * - partial 提交(点「继续」, queueNodeIds 非空): 把每个扇出节点每组「选中组名」输出下游的输出节点
   *   并入 targets(预加载), 再剔除未选中分支下游输出节点(拦截);
   * - 全量 Run(queueNodeIds 为空且图中无继续节点): 显式列出「全部输出节点 - 未选中分支下游输出节点」
   *   提交, 未选中分支下游不进调度表, 根本不执行; 图含继续节点时保持原分段行为(全量提交)。
   *
   * @returns {void}
   */
  async setup() {
    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    /**
     * 包装 queuePrompt: 按 partial_execution_targets(「继续」同款机制)预加载选中分支 + 拦截未选中分支。
     *
     * @param {number} number 提交次数
     * @param {number} batch 批次数
     * @param {Array<string>|undefined} queueNodeIds 继续节点显式指定的目标节点 ID 列表
     * @returns {Promise} 原始 queuePrompt 的返回值
     */
    app.queuePrompt = async function (number, batch, queueNodeIds) {
      const graph = app.graph ?? app.rootGraph;
      const blocked = collectBlockedOutputNodes(graph);
      if (queueNodeIds?.length) {
        const targets = collectAllTargets(graph);
        if (targets.length) {
          queueNodeIds = [...new Set([...queueNodeIds, ...targets])];
        }
        if (blocked.length) {
          const blockedSet = new Set(blocked);
          queueNodeIds = queueNodeIds.filter((id) => !blockedSet.has(id));
        }
      } else if (blocked.length && !graph?._nodes?.some(isContinueNode)) {
        const blockedSet = new Set(blocked);
        const kept = collectAllOutputNodes(graph).filter((id) => !blockedSet.has(id));
        if (kept.length) {
          queueNodeIds = kept;
        }
      }
      return orig(number, batch, queueNodeIds);
    };
  },

  /**
   * 节点定义注册前钩子: 给 FallingTSFanout 绑定 total/items → 输入端口/输出端口/下拉选项联动。
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
     * selection 为标准下拉 widget (槽类型 STRING,INT: 可连线接多对一 选中项组名/索引), 选项由 items 实时生成。
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
