// FallingTS 一对多下拉选择 (total 组) 前端 (参考 selector.js 的 total/items 动态端口范式):
// - total 输出组数 (最少 1, 最多 MAX_GROUPS), 按 total 动态增删输出端口 output_1..output_total;
// - items 组名列表 (逗号分隔, 与多对一选择 items 同源), 输出端口标签 = 组名 (缺省 组i);
// - selection 为可连线 STRING 输入 (直接接多对一 选中项, 连线值优先), 值 = 逗号分隔组名 (如 "右面,后面");
//   选中组的输出 = value 输入, 未选中组 None; 未连线且为空时默认第一组;
// - total/items 变化时: 输出端口增删 + 端口标签同步 + 高度收回;
// - 关键(预加载): partial 提交(点「继续」)时, 把本节点所有「选中组」输出下游的输出节点并入 targets,
//   让选中的多个分支下游真正执行 —— 与 route.js 补假分支同一机制, 但这里是「所有选中组」而非单一假分支。

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "FallingTSOneToMany";
const CONTINUE_CLASS = "FallingTSContinue";
const MAX_GROUPS = 50;
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
 * 把 selection 文本 (逗号分隔组名) 解析为组名集合。
 *
 * @param {*} value 逗号分隔组名文本 (如 "右面,后面"), 可为空/None/数组
 * @returns {Set<string>} 组名集合, 空项忽略
 */
function parseSelection(value) {
  const items = Array.isArray(value) ? value : String(value ?? "").split(",");
  const set = new Set();
  for (const s of items) {
    const name = String(s).trim();
    if (name) set.add(name);
  }
  return set;
}

/**
 * 取节点组名列表 (items 拆分, 按 total 补全为 组i)。
 *
 * @param {object} node 一对多节点对象
 * @returns {string[]} 长度 = total 的组名数组
 */
function getGroupNames(node) {
  const total = getTotal(node);
  const items = splitItems(node.widgets?.find((w) => w.name === "items")?.value);
  const names = [];
  for (let i = 0; i < total; i++) {
    names.push(items[i] || "组" + (i + 1));
  }
  return names;
}

/**
 * 按 total 对齐输出端口: output_1..output_total (只动尾部, 已有连线的槽位永不漂移),
 * 端口标签 = 组名 (items 来源, 缺省 输出 i)。
 *
 * @param {object} node 一对多节点对象
 * @returns {void}
 */
function syncOutputs(node) {
  const total = getTotal(node);
  while ((node.outputs?.length ?? 0) > total) {
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < total) {
    const idx = (node.outputs?.length ?? 0) + 1;
    node.addOutput("output_" + idx, "*");
  }
  const names = getGroupNames(node);
  for (let i = 0; i < total; i++) {
    node.outputs[i].localized_name = names[i] || "输出 " + (i + 1);
  }
  node.setDirtyCanvas?.(true, true);
}

/**
 * 节点高度收回自然高度(只缩不扩: 用户手动拉高的高度保留)。
 *
 * 后端声明 MAX_GROUPS=50 个输出, 新建节点时构造器先加上全部 50 个输出并把初始高度
 * 撑到容纳 50 个输出 (上千 px); syncOutputs 按 total 删掉多余端口后需把多余高度收回,
 * 否则新建节点异常高大。
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

/**
 * 整体同步: 输出端口对齐 + 高度收回。total/items 变化 / 节点创建 / 加载工作流 时统一调用。
 *
 * @param {object} node 一对多节点对象
 * @returns {void}
 */
function syncAll(node) {
  syncOutputs(node);
  fitHeight(node);
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
 * 取节点 selection 输入当前选中的组名集合。
 *
 * @param {object} node 一对多节点对象
 * @returns {Set<string>} 选中组名集合
 */
function getSelectedNames(node) {
  return parseSelection(node.widgets?.find((w) => w.name === "selection")?.value);
}

/**
 * 从本节点所有「选中组」输出(组名属于 selected 的槽位)下游 BFS, 收集输出节点
 * (遇到继续节点停止)。收集到的节点 ID 在 partial 提交时并入 targets, 让选中的多个分支真正执行。
 *
 * @param {object} node 一对多节点对象
 * @returns {string[]} 输出节点 ID 字符串数组(已去重); 一个都没有时返回空数组
 */
function collectSelectedBranchOutputs(node) {
  const selected = getSelectedNames(node);
  const total = getTotal(node);
  const names = getGroupNames(node);
  const outs = node.outputs ?? [];
  const targets = new Set();
  const visited = new Set();
  const queue = [];
  for (let i = 0; i < total; i++) {
    const name = names[i];
    if (!name || !selected.has(name)) continue;
    const o = outs[i];
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
 * 收集图中所有一对多节点「选中组」分支下游的输出节点(去重)。
 *
 * @param {object} graph 画布图对象
 * @returns {string[]} 输出节点 ID 字符串数组
 */
function collectAllTargets(graph) {
  const targets = new Set();
  for (const n of graph?._nodes ?? []) {
    if (!isOneToManyNode(n)) continue;
    for (const t of collectSelectedBranchOutputs(n)) targets.add(t);
  }
  return [...targets];
}

app.registerExtension({
  name: "FallingTS.OneToMany",

  /**
   * 扩展初始化钩子: 包装全局提交入口 app.queuePrompt。
   * partial 提交(点「继续」, queueNodeIds 非空)时, 把图中每个一对多节点「选中组」
   * 输出下游的输出节点并入 targets, 让选中的多个分支下游真正执行(预加载)。
   *
   * @returns {void}
   */
  async setup() {
    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    /**
     * 包装 queuePrompt: 只处理 partial 提交分支(队列 NodeIds 非空), 并入选中组分支 targets。
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
   * 节点定义注册前钩子: 给 FallingTSOneToMany 绑定 total/items → 输出端口/标签联动。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: total/items 变化时同步输出端口与标签; 加载工作流时按保存的值对齐。
     * selection 为标准 STRING widget (可连线, 接多对一 选中项), 无需自定义 DOM。
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
        /** widget 回调: total/items 值变化后重新对齐输出端口与标签。 */
        widget.callback = function (value) {
          const out = orig?.apply(this, arguments);
          syncAll(node);
          return out;
        };
      };
      bindWidget("items");
      bindWidget("total");

      // 兜底: 新前端输入可能不走 widget.callback, 用节点级 onWidgetChanged 再同步一次
      const onWidgetChanged = nodeType.prototype.onWidgetChanged;
      /** 节点级 widget 变化钩子: total/items 变化时同步输出端口与标签。 */
      nodeType.prototype.onWidgetChanged = function (widget, value, ...args) {
        const out = onWidgetChanged?.apply(this, arguments);
        if (widget?.name === "items" || widget?.name === "total") {
          syncAll(this);
        }
        return out;
      };

      // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次
      const prevOnConfigure = node.onConfigure;
      /** configure 钩子: 工作流加载完成后按保存的 total/items 对齐输出端口与标签。 */
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        syncAll(node);
      };

      syncAll(node);
      fitHeight(node);
      // 节点刚创建时 widgetValue store 可能还没注册完成, 下一 tick 再同步一次
      setTimeout(() => {
        syncAll(node);
        fitHeight(node);
      }, 0);
      return result;
    };
  },
});
