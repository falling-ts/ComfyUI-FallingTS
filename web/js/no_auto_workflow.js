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
//   3. 拦截后绝不新建标签、也绝不改动画布: 直接不调用原 loadGraphData。
//      ⚠️ 早期实现是"再加载一次空图"或"app.clean() 清一遍画布", 在 1.55.18 上会**清掉
//      紧接着真实加载的内容**(新版原地复用同一个 rootGraph, 清空动作落在真实加载之后),
//      表现为「画布空白 / 点开任何工作流节点数都是 0 / 连线全没」。现版本一律不碰画布,
//      详见 suppressAutoOpen 的注释。
//   4. 关完之后 activeWorkflow 仍指着那个已不在 openWorkflows 里的旧对象, 用一次性兜底置空;
//      前端源码里 activeWorkflow 到处都有 `?.` / `if (!activeWorkflow) return` 守卫,
//      null 是安全状态(useWorkflowPersistenceV2 的 restoreState 也显式处理了空值)。

const { app } = window.comfyAPI.app;

/**
 * 扩展行为开关(改完刷新页面即可生效)。
 *
 * 2026-10-24: 两个开关重新置为 true, 但拦截方式已重做 —— 不再触碰画布, 只"不加载"。
 * 上一版之所以被迫关闭, 是因为它在拦截时清空画布(app.clean / 空图重载), 而前端 1.55.18
 * 改为**原地复用同一个 rootGraph**(`rootGraph.configure(e)`), 清空动作会落在真实加载之后,
 * 把用户点开的工作流清成空图。现在拦截路径完全无副作用: 启动/关闭时**不加载任何东西**,
 * 画布交给下一次真实加载, 因此既有「不自动打开」的行为, 又不会破坏任何后续加载。
 */
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

/**
 * 启动时间窗: 只在这个窗口内把"空图 + 无任何工作流"的加载当成启动自动打开。
 *
 * ⚠️ 旧值是 20000ms, 太宽了 —— 页面起来后 20 秒内用户点开任何工作流都会落进这个窗口。
 * 启动自动打开实际发生在首屏渲染阶段(通常 <3s), 收紧到 6s 并配合"当前无任何工作流 +
 * 空图"两道状态判据才不会误伤正常打开。
 */
const STARTUP_WINDOW_MS = 6000;
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
  // 只认「启动窗口内」的自动打开。⚠️ 不能再用 args.length / 第 4 实参判断:
  // 前端 1.55.x 把 loadGraphData 改成了单参签名 `async function (data)`, 调用方也不再
  // 传第 4 实参(工作流改由 afterLoadNewGraph → activateLoadedWorkflow 内部认领)。旧逻辑
  // 于是把用户点开的正常工作流也当成 `startup` 拦掉 —— 画布空白、标签不新增、节点数 0。
  if (Date.now() - bootAt > STARTUP_WINDOW_MS) return null;

  // 启动自动打开只发生在首屏, 且此时画布上不会已经有节点。用「图里已有节点」做最后一道
  // 否决: 用户点开的工作流必然带着节点, 绝不能因为"打开列表还空着"就被当成启动。
  const rootNodes = app?.rootGraph?._nodes;
  if (Array.isArray(rootNodes) && rootNodes.length > 0) return null;

  // 启动路径要么零实参(默认图), 要么 loadBlankWorkflow() 传空图(graphData 为 undefined 也算)
  if (args.length === 0 || graphData == null || isEmptyGraph(graphData)) {
    return args.length === 0 ? 'startup' : 'startup-blank';
  }
  return null;
}

/**
 * 拦截"自动打开工作流", 换成"保持不打开任何工作流"。
 *
 * ⚠️ 关键约束(2026-10-24 实测): 这里**绝不能调用 `app.clean()`**(旧版 `blankCanvas()` 就是
 * 它), 也不能再走一次 `loadGraphData(BLANK_GRAPH, true, ...)`。原因是前端 1.55.18 的
 * `loadGraphData` 开头有一段:
 *
 *     t && (this.canvas.setGraph(this.rootGraph), this.clean())
 *
 * `clean()` 会 `this.rootGraph.clear()` —— 清的是**同一个 rootGraph 对象**(新版不再新建图,
 * 而是原地 `rootGraph.configure(e)` 复用)。而本拦截发生在关闭/启动链路里, 与紧接着的真实
 * 加载**共用同一条 async 队列**, 于是清空动作落在真实加载之后 ⇒ 用户点开的工作流被清成空图,
 * 表现为「画布空白 / 节点数 0 / 连线全没」。
 *
 * 因此现在的做法是**只做状态回收, 一律不碰画布**:
 *   - startup: 直接不加载。启动时画布本来就是空的(根图无节点), 无需再清;
 *   - close-last: 什么都不加载。关闭方(`closeWorkflow`)自己会把活动工作流从
 *     `openWorkflows` 里摘掉, 这里只需在之后把悬空的 `activeWorkflow` 置空。
 * 画布的最终内容由下一次真实加载决定, 本扩展不再产生任何中间态。
 *
 * @param {string} kind classifyAutoOpen 的判定结果
 * @returns {Promise<void>} 与原调用同样可 await
 */
function suppressAutoOpen(kind) {
  // 两种情形都不加载任何东西: 不新建标签、不刷新画布、不改 rootGraph。
  if (kind === 'close-last') {
    // 关闭链路后续还要摘活动标签/清预览, 用一次性兜底把悬空的 activeWorkflow 置空
    setTimeout(reapDetachedActiveWorkflow, 0);
    setTimeout(reapDetachedActiveWorkflow, 120);
  }
  return Promise.resolve();
}

/**
 * 接管 app.loadGraphData(幂等)。
 *
 * 前端 1.55.18 仍然从这里进出: 打开工作流走 store 的 `openWorkflow` → `Q.loadGraphData(...)`,
 * 关闭后补图走 `loadDefaultWorkflow=()=>queueWorkflowLoad(()=>Q.loadGraphData(oI))`,
 * 启动走 `loadBlankWorkflow()` / 零实参。所以包这一层依然有效 —— 上一版"钩子失效"的判断
 * 是错的, 真正的故障是拦截动作本身会清空画布(见 suppressAutoOpen)。
 *
 * @returns {boolean} 已接管返回 true
 */
function installLoadGraphDataHook() {
  if (loadGraphDataHooked) return true;
  if (isDisabledByQuery()) return false;
  if (!OPTIONS.suppressOnClose && !OPTIONS.suppressOnStartup) return false;
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
    return suppressAutoOpen(kind);
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
