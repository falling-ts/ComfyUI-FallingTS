// FallingTS 一对多下拉选择 (total 组) 前端 (参考 selector.js 的 total 动态端口范式 + table_lookup.js 的 DOM widget 范式):
// - total 输出组数 (最少 1, 最多 MAX_GROUPS), 按 total 动态增删输出端口 output_1..output_total;
// - selection 多选下拉 (选项 = 组号 1..total, 可多选), 值存为逗号分隔组号 (如 "1,3"),
//   被选中组的输出 = value 输入, 未选中组为 None;
// - total 变化时: 输出端口增删 + 下拉选项(1..total)重建 + 越界组号裁剪 + 高度收回;
// - 关键(预加载): partial 提交(点「继续」)时, 把本节点所有「选中组」输出下游的输出节点并入 targets,
//   让选中的多个分支下游真正执行 —— 与 route.js 补假分支同一机制, 但这里是「所有选中组」而非单一假分支。

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "FallingTSOneToMany";
const CONTINUE_CLASS = "FallingTSContinue";
const MAX_GROUPS = 50;
const DEFAULT_TOTAL = 2;
const WIDGET_TYPE = "FALLINGTS_ONEMANY_SELECT";

/**
 * 读取节点 total widget 的当前组数, 非法值回退默认, 再裁到 [1, MAX_GROUPS]。
 *
 * @param {LGraphNode} node 一对多节点对象
 * @returns {number} 有效组数(1 ~ MAX_GROUPS)
 */
function getTotal(node) {
  const w = node.widgets?.find((w) => w.name === "total");
  let v = w ? Math.floor(Number(w.value)) : DEFAULT_TOTAL;
  if (!Number.isFinite(v)) v = DEFAULT_TOTAL;
  return Math.min(MAX_GROUPS, Math.max(1, v));
}

/**
 * 把多选下拉的逗号分隔组号文本解析为去重组号集合 (1 起, 裁到 [1, MAX_GROUPS])。
 *
 * @param {*} value 逗号分隔组号文本 (如 "1,3"), 可为空/None/数组
 * @returns {Set<number>} 有效组号集合, 非法项忽略
 */
function parseSelection(value) {
  const items = Array.isArray(value) ? value : String(value ?? "").split(",");
  const set = new Set();
  for (const s of items) {
    const n = Math.floor(Number(String(s).trim()));
    if (Number.isFinite(n) && n >= 1 && n <= MAX_GROUPS) set.add(n);
  }
  return set;
}

/**
 * 把组号集合格式化为升序逗号分隔文本 (如 [1,3] -> "1,3"), 供 widget.value / 后端 selection 输入。
 *
 * @param {Set<number>} set 组号集合
 * @returns {string} 升序逗号分隔文本, 空集为 ""
 */
function formatSelection(set) {
  return [...set].sort((a, b) => a - b).join(",");
}

/**
 * 按 total 对齐输出端口: output_1..output_total (只动尾部, 已有连线的槽位永不漂移)。
 *
 * @param {LGraphNode} node 一对多节点对象
 * @returns {void}
 */
function syncOutputs(node) {
  const total = getTotal(node);
  while ((node.outputs?.length ?? 0) > total) {
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < total) {
    const idx = node.outputs.length + 1;
    node.addOutput("output_" + idx, "*");
  }
  for (let i = 0; i < total; i++) {
    node.outputs[i].localized_name = "输出 " + (i + 1);
  }
  node.setDirtyCanvas?.(true, true);
}

/**
 * 节点高度收回自然高度(只缩不扩: 用户手动拉高的高度保留)。
 *
 * 后端声明 MAX_GROUPS=50 个输出, 新建节点时构造器先加上全部 50 个输出并把初始高度
 * 撑到容纳 50 个输出 (上千 px); syncOutputs 按 total 删掉多余端口后需把多余高度收回,
 * 否则新建节点异常高大。仅新建时生效(onNodeCreated): 加载工作流时 configure 恢复保存高度。
 *
 * @param {LGraphNode} node 一对多节点对象
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
 * 整体同步: 输出端口对齐 + 多选下拉选项重建(越界裁剪) + 高度收回。
 * total 变化 / 节点创建 / 加载工作流 时统一调用。
 *
 * @param {LGraphNode} node 一对多节点对象
 * @returns {void}
 */
function syncAll(node) {
  syncOutputs(node);
  node._onemanyRebuildPanel?.();
  fitHeight(node);
}

// ─── 判断/链路工具 (与 proceed.js / route.js 同款) ─────────────────────────

/** 判断是否为「一对多下拉选择」节点。 */
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
 * 取节点 selection 多选下拉当前选中的组号集合。
 *
 * @param {LGraphNode} node 一对多节点对象
 * @returns {Set<number>} 选中组号集合
 */
function getSelectedSet(node) {
  return parseSelection(node.widgets?.find((w) => w.name === "selection")?.value);
}

/**
 * 从本节点所有「选中组」输出(slot 0..total-1 中属于 selected 的槽位)下游 BFS, 收集输出节点
 * (遇到继续节点停止)。收集到的节点 ID 在 partial 提交时并入 targets, 让选中的多个分支真正执行。
 *
 * @param {LGraphNode} node 一对多节点对象
 * @returns {string[]} 输出节点 ID 字符串数组(已去重); 一个都没有时返回空数组
 */
function collectSelectedBranchOutputs(node) {
  const selected = getSelectedSet(node);
  const total = getTotal(node);
  const outs = node.outputs ?? [];
  const targets = new Set();
  const visited = new Set();
  const queue = [];
  for (const i of selected) {
    if (i < 1 || i > total) continue;
    const o = outs[i - 1];
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
 * @param {LGraph} graph 画布图对象
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

// ─── selection 多选下拉 DOM widget (参考 table_lookup.js 的 addDOMWidget 范式) ────────

/**
 * 构建多选下拉 DOM: 顶部「选择: <组号> ▼」按钮行 + 下方展开的复选框面板 (选项 = 组号 1..total)。
 * widget 值 = 选中组号的升序逗号分隔文本, 序列化进工作流 widgets_values, 与后端 selection 输入对接。
 *
 * @param {LGraphNode} node 一对多节点对象
 * @param {string} inputName 输入名("selection")
 * @param {Array} inputData 输入定义([类型, {default, tooltip}])
 * @returns {{widget: object}} addDOMWidget 创建的 widget 对象
 */
function createSelectionWidget(node, inputName, inputData) {
  let selected = parseSelection(inputData?.[1]?.default ?? "1");

  const root = document.createElement("div");
  root.style.cssText = "position:relative;width:100%;";

  // 顶部按钮行: 选择: <组号> ▼
  const header = document.createElement("div");
  header.style.cssText =
    "display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none;" +
    "font-size:12px;color:#ccc;padding:4px 6px;border:1px solid #444;border-radius:4px;background:#222;";
  const label = document.createElement("span");
  label.textContent = "选择:";
  const valueText = document.createElement("span");
  valueText.style.cssText = "color:#9d7cff;font-weight:600;flex:1;";
  const arrow = document.createElement("span");
  arrow.textContent = "\u25bc";
  arrow.style.cssText = "color:#888;font-size:10px;";
  header.appendChild(label);
  header.appendChild(valueText);
  header.appendChild(arrow);
  root.appendChild(header);

  // 下拉面板: 复选框列表 (选项 = 组号 1..total) + 全选/清空
  const panel = document.createElement("div");
  panel.style.cssText =
    "display:none;position:absolute;left:0;right:0;top:100%;z-index:50;" +
    "max-height:220px;overflow:auto;background:#2a2a2a;border:1px solid #555;border-top:none;" +
    "border-radius:0 0 6px 6px;padding:6px;box-shadow:0 6px 16px rgba(0,0,0,.5);";
  root.appendChild(panel);

  let widgetRef = null;
  let open = false;

  function updateHeader() {
    valueText.textContent = selected.size ? formatSelection(selected) : "(未选择)";
  }

  function rebuildPanel() {
    const total = getTotal(node);
    // 裁剪越界组号 (total 变小后)
    for (const n of [...selected]) {
      if (n > total) selected.delete(n);
    }
    panel.innerHTML = "";
    for (let i = 1; i <= total; i++) {
      const row = document.createElement("label");
      row.style.cssText = "display:flex;align-items:center;gap:6px;font-size:12px;color:#ddd;padding:2px 4px;cursor:pointer;";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = selected.has(i);
      cb.style.cssText = "accent-color:#9d5cff;";
      cb.addEventListener("change", () => {
        if (cb.checked) selected.add(i);
        else selected.delete(i);
        commit();
      });
      const t = document.createElement("span");
      t.textContent = "输出 " + i;
      row.appendChild(cb);
      row.appendChild(t);
      panel.appendChild(row);
    }
    // 底部 全选/清空
    const bar = document.createElement("div");
    bar.style.cssText = "display:flex;gap:8px;padding-top:4px;border-top:1px solid #444;margin-top:4px;";
    const all = document.createElement("button");
    all.textContent = "全选";
    const clear = document.createElement("button");
    clear.textContent = "清空";
    [all, clear].forEach((b) => {
      b.style.cssText =
        "font-size:11px;background:#333;color:#ddd;border:1px solid #555;border-radius:3px;padding:2px 8px;cursor:pointer;";
    });
    all.addEventListener("click", () => {
      const total = getTotal(node);
      for (let i = 1; i <= total; i++) selected.add(i);
      commit();
    });
    clear.addEventListener("click", () => {
      selected.clear();
      commit();
    });
    bar.appendChild(all);
    bar.appendChild(clear);
    panel.appendChild(bar);
    updateHeader();
  }

  function commit() {
    rebuildPanel();
    if (widgetRef) {
      widgetRef.value = formatSelection(selected);
      widgetRef.callback?.(widgetRef.value);
    }
    node.setDirtyCanvas?.(true, true);
  }

  function toggle() {
    open = !open;
    panel.style.display = open ? "block" : "none";
  }

  header.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle();
  });
  // 面板内点击不冒泡关闭
  panel.addEventListener("click", (e) => e.stopPropagation());
  // 点击外部关闭
  document.addEventListener("click", () => {
    if (open) {
      open = false;
      panel.style.display = "none";
    }
  });

  const widget = node.addDOMWidget(inputName, WIDGET_TYPE, root, {
    getValue: () => formatSelection(selected),
    setValue: (v) => {
      selected = parseSelection(v);
      rebuildPanel();
    },
    getMinHeight: () => 34,
    serialize: true,
  });
  widgetRef = widget;

  // 暴露给 syncAll: total 变化 / 加载工作流时重建下拉选项
  node._onemanyRebuildPanel = rebuildPanel;

  // total 变化 -> 重建下拉选项(1..total) + 输出端口对齐 + 高度收回
  const tw = node.widgets?.find((w) => w.name === "total");
  if (tw) {
    const orig = tw.callback;
    tw.callback = function (v) {
      orig?.apply(this, arguments);
      syncAll(node);
    };
  }

  rebuildPanel();
  syncOutputs(node);
  return { widget };
}

app.registerExtension({
  name: "FallingTS.OneToMany",

  /**
   * 扩展初始化钩子: 包装全局提交入口 app.queuePrompt。
   * partial 提交(点「继续」, queueNodeIds 非空)时, 把图中每个一对多节点「选中组」
   * 输出下游的输出节点并入 targets, 让选中的多个分支下游真正执行(预加载)。
   * 与 proceed.js(默认 Run 重置) / route.js(补假分支) 链式叠加, 顺序无关。
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
   * 注册自定义 widget 工厂: FALLINGTS_ONEMANY_SELECT 类型 -> 多选下拉 DOM widget。
   *
   * @returns {object} 自定义 widget 工厂映射表
   */
  getCustomWidgets() {
    return {
      [WIDGET_TYPE](node, inputName, inputData) {
        return createSelectionWidget(node, inputName, inputData);
      },
    };
  },

  /**
   * 节点定义注册前钩子: 节点创建后按 total 对齐输出端口并收回高度。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 按 total 对齐输出端口并收回高度; total 联动由 selection DOM widget 内绑定。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const node = this;

      // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次
      const prevOnConfigure = node.onConfigure;
      /** configure 钩子: 工作流加载完成后按保存的 total 对齐输出与下拉选项。 */
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        syncAll(node);
      };

      syncAll(node);
      // 节点刚创建时 widgetValue store 可能还没注册完成, 下一 tick 再同步一次
      setTimeout(() => {
        syncAll(node);
      }, 0);
      return result;
    };
  },
});
