// ComfyUI-FallingTS 前端扩展: 真正"不打开任何工作流"
//
// 目标状态: 关闭工作流之后, 标签里既没有打开的工作流, 也没有未保存的占位工作流
//           —— 标签栏为空 + 画布空白 + 没有活动工作流(activeWorkflow === null)。
//
// 背景(前端包 1.53.10 源码, 两条硬编码路径, 都没有设置开关):
//
//   ① workflowService.ts 的 closeWorkflow():
//        let e = workflowStore.getMostRecentWorkflow()
//        if (e) { await openWorkflow(e) }
//        else if (await loadDefaultWorkflow() === false) return false
//        ...
//        await workflowStore.closeWorkflow(workflow)
//        workflowDraftStore.removeDraft(workflow.path)
//      → 关掉最后一个标签(没有更近的标签可切)时会先塞一个 "Unsaved Workflow"
//        (默认图: SD1.5 + Z-Image Turbo 两组节点), 再把原来那个关掉, 于是永远残留一个未保存工作流。
//      ⚠️ 1.52.7 里这段顺序是反的(先 removeDraft 与 closeWorkflow, 再判
//        openWorkflows.length === 1 才 loadDefaultWorkflow); 1.53.x 把"塞默认工作流"
//        提到前面, 于是旧版 removeDraft 前哨失效 —— 这是本插件一度失效的根因。
//
//   ② useWorkflowPersistenceV2.ts 的 resolveStartupOutcome():
//        Comfy.TutorialCompleted ? await comfyApp.loadGraphData()   // 零实参 → defaultGraph
//                                : await loadBlankWorkflow()
//      → 每次刷新页面也必定自动打开一个 "Unsaved Workflow"。
//
//   ComfyUI 内置设置里没有对应项(整张设置表只有 WorkflowTabsPosition = Sidebar/Topbar,
//   那是"标签放顶部还是侧栏", 不是"要不要打开工作流")。所以只能在前端拦截。
//
// 实现要点:
//   1. 包住 app.loadGraphData —— 这是"打开工作流"的唯一入口(内部经 afterLoadNewGraph
//      → activateLoadedWorkflow → createNewTemporary 建标签)。
//   2. 识别两个"自动打开"时机:
//      a) 关闭最后一个工作流: 用 workflow store 的 getMostRecentWorkflow 做前哨 ——
//         上游 closeWorkflow() 在"塞默认工作流"之前同步调它找下一个要切换的标签:
//         返回 null(没有更近的)且 openWorkflows 只剩那一个活动工作流时, 紧接着就调
//         loadDefaultWorkflow()。它只被 closeWorkflow 这一条路径调用(见 workflowStore),
//         所以这里能精确识别"正在关最后一个"。
//         ⚠️ 前端 1.53.x 把"塞默认工作流"挪到了 t.closeWorkflow()/removeDraft() 之前
//         (旧版是之后), 所以用 removeDraft 做前哨的写法永远等不到 —— 关闭时 openWorkflows
//         里已经多了新塞进来的 Unsaved Workflow, open.length === 1 与 removeDraft(path)
//         的判定都不再成立。改用 getMostRecentWorkflow 后与上游同步点重新对齐。
//      b) 页面启动: 零实参的 loadGraphData() 在整个前端只有启动这一处(其余调用都至少带图数据);
//         另有未完成新手引导时的启动分支 loadBlankWorkflow() → loadGraphData(空白图),
//         用"启动时间窗 + 空图 + 无活动工作流 + 无打开工作流"共同限定。
//   3. 拦截后绝不新建标签: 把当前活动工作流当作第 4 实参传给 loadGraphData ——
//      activateLoadedWorkflow 里的 workflowStore.openWorkflow() 会因 isActive() 直接返回,
//      不会 createNewTemporary(这一招正是本插件 workflow_reload_button.js 注释里记过的坑)。
//   4. 关完之后 activeWorkflow 仍指着那个已不在 openWorkflows 里的旧对象, 用一次性兜底置空;
//      前端源码里 activeWorkflow 到处都有 `?.` / `if (!activeWorkflow) return` 守卫,
//      null 是安全状态(useWorkflowPersistenceV2 的 restoreState 也显式处理了空值)。

const { app } = window.comfyAPI.app;

/** 扩展行为开关(改完刷新页面即可生效) */
const OPTIONS = {
  /** 关闭最后一个工作流后不再自动打开默认/空白工作流 */
  suppressOnClose: true,
  /** 页面加载后不自动打开默认工作流(每次刷新都是空白画布 + 0 标签) */
  suppressOnStartup: true,
};

const LOG = '[NoAutoWorkflow]';

/**
 * 调试开关: URL 上加 `?noAutoWorkflow=off` 可临时停用本扩展(用于对照排查)。
 *
 * @returns {boolean} 被 URL 停用返回 true
 */
function isDisabledByQuery() {
  try {
    return new URLSearchParams(location.search).get('noAutoWorkflow') === 'off';
  } catch {
    return false;
  }
}

/** 与前端 src/scripts/defaultGraph.ts 的 blankGraph 逐字一致 */
const BLANK_GRAPH = {
  last_node_id: 0,
  last_link_id: 0,
  nodes: [],
  links: [],
  groups: [],
  config: {},
  extra: {},
  version: 0.4,
};

/** 启动时间窗: 只在这个窗口内把"空图 + 无任何工作流"的加载当成启动自动打开 */
const STARTUP_WINDOW_MS = 20000;
const bootAt = Date.now();

/**
 * 用户是否已经碰过页面。
 * 启动自动打开一定发生在任何交互之前; 一旦用户点过/按过键, 之后的加载都算用户意图
 * (例如 legacy 菜单的 "Load default workflow?" 按钮也是零实参调 loadGraphData)。
 */
let userInteracted = false;
window.addEventListener('pointerdown', () => (userInteracted = true), {
  capture: true,
  once: true,
});
window.addEventListener('keydown', () => (userInteracted = true), {
  capture: true,
  once: true,
});

/** 已挂前哨的 store(避免重复包装) */
const sentinelInstalled = new WeakSet();

/**
 * 是否正处于"关闭最后一个工作流"的同步块内(由 getMostRecentWorkflow 前哨写入)。
 * 上游 closeWorkflow() 在这一步之后同步调用 loadDefaultWorkflow() → loadGraphData,
 * 中间没有 await 点会把这个标记拖到别的调用上, 故用布尔量即可。
 */
let closingLastWorkflow = false;

let loadGraphDataHooked = false;

/**
 * 从 Vue pinia store 按 id 取 store 对象。
 *
 * @param {string} id store id(如 "workflow" / "execution")
 * @returns {object|null} pinia store 对象; 不可用时返回 null
 */
function getStore(id) {
  try {
    const el = document.getElementById('vue-app');
    const pinia = el?.__vue_app__?.config?.globalProperties?.$pinia;
    return pinia?._s?.get(id) ?? null;
  } catch {
    return null;
  }
}

/**
 * 取工作流 store(useWorkflowStore, id = "workflow")。
 *
 * @returns {object|null} workflow store
 */
function workflowStore() {
  return getStore('workflow');
}

/**
 * 只清空画布, 不建任何工作流。等价于 loadGraphData 里 `canvas.setGraph(rootGraph)` + `clean()`
 * 那两步, 用于"启动时不加载任何东西"的分支。
 *
 * @returns {void}
 */
function blankCanvas() {
  try {
    // isGraphReady 是官方的"安全判据" —— 直接读 app.rootGraph 会在图未初始化时
    // 打一行 console.error('ComfyApp graph accessed before initialization')
    if (!app.canvas || !app.isGraphReady) return;
    app.canvas.setGraph(app.rootGraph);
    app.clean();
  } catch (e) {
    console.warn(LOG, '清空画布失败', e);
  }
}

/**
 * 兜底收尾: 关完最后一个工作流后 activeWorkflow 仍指向那个已不在 openWorkflows 里的对象,
 * 把它置空才是"没有任何打开的工作流"。若期间用户又打开了别的(或会话恢复), isOpen 为真, 直接放过。
 *
 * @returns {void}
 */
function reapDetachedActiveWorkflow() {
  const ws = workflowStore();
  if (!ws) return;
  const active = ws.activeWorkflow;
  if (!active) return;
  if (ws.isOpen?.(active)) return;
  ws.activeWorkflow = null;
  console.log(LOG, '已置空 activeWorkflow(当前没有任何打开的工作流)');
}

/**
 * 判断图数据是否是"空图"(blankGraph 的形状)。只用于识别启动的空白工作流分支。
 *
 * @param {unknown} graphData loadGraphData 的第一个实参
 * @returns {boolean} 是空图返回 true
 */
function isEmptyGraph(graphData) {
  return (
    !!graphData &&
    typeof graphData === 'object' &&
    !Array.isArray(graphData) &&
    Array.isArray(graphData.nodes) &&
    graphData.nodes.length === 0
  );
}

/**
 * 给 workflow store 的 getMostRecentWorkflow 挂前哨。
 *
 * 上游 closeWorkflow() 在"塞默认工作流"之前会同步调 getMostRecentWorkflow() 找下一个标签:
 *   let e = t.getMostRecentWorkflow()
 *   if (n) { openWorkflow(n) } else if (await loadDefaultWorkflow() === false) return
 * 这里正是判定"正在关最后一个"的位置 —— 没有更近的标签(返回 null)且打开列表此刻只剩
 * 那个正要被关的活动工作流, 接下来的 loadDefaultWorkflow 就该被拦截。
 * 它只被 closeWorkflow 调用, 其它路径不会触发, 所以不会误伤。
 *
 * getMostRecentWorkflow 是"基于现状算一次"的普通函数: 上游在此刻打开列表里还只有那一个
 * 工作流(新标签是稍后在 closeWorkflow 内才塞进来的), 所以 open.length === 1 成立。
 * 标记只在同步块内有效 —— 紧接着的 loadGraphData 同步发生, 不跨 await。
 *
 * @returns {boolean} 前哨已就位返回 true(store 还没挂出来则 false, 由调用方重试)
 */
function installCloseSentinel() {
  const ws = workflowStore();
  if (!ws || typeof ws.getMostRecentWorkflow !== 'function') return false;
  if (sentinelInstalled.has(ws)) return true;
  if (isDisabledByQuery()) return false;

  const original = ws.getMostRecentWorkflow;
  ws.getMostRecentWorkflow = function (...args) {
    const result = original.apply(this, args);
    try {
      const open = this.openWorkflows ?? [];
      if (result == null && open.length === 1) {
        closingLastWorkflow = true;
        // 兜底: 上游若因异常没走到 loadGraphData, 标记不许跨拍存活(它会同步发生在微任务里)
        setTimeout(() => {
          closingLastWorkflow = false;
        }, 0);
      }
    } catch (e) {
      console.warn(LOG, 'getMostRecentWorkflow 前哨判定失败', e);
    }
    return result;
  };

  sentinelInstalled.add(ws);
  console.log(LOG, 'getMostRecentWorkflow 前哨已就位(用于识别"正在关闭最后一个工作流")');
  return true;
}

/**
 * 判断这次 loadGraphData 是不是"自动打开工作流", 是则返回类型标识。
 *
 * @param {Array} args 传给 app.loadGraphData 的原始实参
 * @returns {string|null} "close-last" / "startup" / "startup-blank"; 不该拦截则 null
 */
function classifyAutoOpen(args) {
  const [graphData, , , workflow] = args;

  // 显式指定了工作流(点开某个工作流 / 会话恢复 / 撤销重做) → 不拦
  if (workflow != null) return null;

  const ws = workflowStore();
  if (!ws) return null;

  // (a) 关闭最后一个工作流时塞进来的默认工作流
  // 前哨在上游调用 getMostRecentWorkflow() 时置位(此刻打开列表里还只有那一个工作流),
  // 紧接着的 loadDefaultWorkflow() → loadGraphData(Hd) 落到这里; 用后立即复位。
  if (OPTIONS.suppressOnClose && closingLastWorkflow) {
    closingLastWorkflow = false;
    const open = ws.openWorkflows ?? [];
    if (open.length === 1) return 'close-last';
  }

  // (b) 页面启动时自动打开默认/空白工作流
  if (!OPTIONS.suppressOnStartup) return null;
  if (userInteracted) return null;
  if (ws.activeWorkflow) return null;
  if ((ws.openWorkflows?.length ?? 0) > 0) return null;
  // 零实参调用在启动路径之外只有 legacy 菜单的 "Load default workflow?" 按钮, 已被上面的
  // userInteracted 挡掉
  if (args.length === 0) return 'startup';
  // 未完成新手引导时的启动分支: loadBlankWorkflow() → loadGraphData(blankGraph)
  if (Date.now() - bootAt < STARTUP_WINDOW_MS && isEmptyGraph(graphData)) {
    return 'startup-blank';
  }
  return null;
}

/**
 * 拦截"自动打开工作流", 换成"保持不打开任何工作流"。
 *
 * @param {Function} original 原始 app.loadGraphData
 * @param {Array} args 原始实参
 * @param {string} kind classifyAutoOpen 的判定结果
 * @returns {Promise<void>} 与原调用同样可 await
 */
function suppressAutoOpen(original, args, kind) {
  if (kind !== 'close-last') {
    // 启动: 本来就没有任何工作流, 不加载即可(画布清一遍保证干净)
    blankCanvas();
    return Promise.resolve();
  }

  // close-last: 清空画布但绝不新建标签。
  // 把"当前活动工作流"当第 4 实参传进去, activateLoadedWorkflow → workflowStore.openWorkflow()
  // 会因 isActive() 直接返回, 不会走 createNewTemporary。
  const ws = workflowStore();
  const active = ws?.activeWorkflow;
  let pending;
  if (active) {
    pending = Promise.resolve(
      original.call(app, BLANK_GRAPH, true, true, active, args[4] ?? {})
    );
  } else {
    blankCanvas();
    pending = Promise.resolve();
  }

  // 外层 closeWorkflow 之后还要选下一个 / 真正关闭 / 清预览才结束, 用一次性兜底收尾
  setTimeout(reapDetachedActiveWorkflow, 0);
  setTimeout(reapDetachedActiveWorkflow, 120);
  return pending;
}

/**
 * 接管 app.loadGraphData(幂等)。
 *
 * @returns {boolean} 已接管返回 true
 */
function installLoadGraphDataHook() {
  if (loadGraphDataHooked) return true;
  if (isDisabledByQuery()) return false;
  if (typeof app?.loadGraphData !== 'function') return false;

  const original = app.loadGraphData;
  app.loadGraphData = function (...args) {
    let kind = null;
    try {
      kind = classifyAutoOpen(args);
    } catch (e) {
      console.warn(LOG, '自动打开判定失败, 按原行为加载', e);
    }
    if (!kind) return original.apply(app, args);

    console.log(LOG, `拦截自动打开工作流(${kind}) → 保持"不打开任何工作流"`);
    return suppressAutoOpen(original, args, kind);
  };

  loadGraphDataHooked = true;
  console.log(LOG, '已接管 app.loadGraphData');
  return true;
}

// 扩展脚本在 app.setup() 期间加载, 早于 GraphCanvas 的 initializeWorkflow, 这里先接管一次
installLoadGraphDataHook();

app.registerExtension({
  name: 'ComfyDesktop.NoAutoWorkflow',

  /**
   * 扩展初始化钩子: 接管 loadGraphData, 并轮询等 #vue-app 挂出来后给 removeDraft 挂前哨。
   *
   * @returns {void}
   */
  setup() {
    installLoadGraphDataHook();

    let tries = 0;
    const timer = setInterval(() => {
      if (installCloseSentinel() || ++tries > 240) clearInterval(timer);
    }, 50);
  },
});
