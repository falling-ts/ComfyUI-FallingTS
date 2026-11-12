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
//   3. 关闭最后一个工作流时**清空画布**, 启动时不动画布。两条路径必须区别对待:
//      a) close-last(关闭最后一个): 上游 closeWorkflow 不再塞默认工作流了(被本扩展拦掉),
//         而清画布原本是**靠被拦掉的那条 loadDefaultWorkflow→clean() 顺带完成**的 ——
//         于是画布上留着刚关掉那份图的节点, 标签栏却空了。这就是「打开关闭但画布不清空」的根因。
//         修复见 installCloseWorkflowHook: 包住 store.closeWorkflow, 在**关闭真正成功后**
//         判断 openWorkflows 是否已空, 是则清画布 + 置空 activeWorkflow。
//      b) startup(页面启动): 画布本来就空, 清不清等价, 一律不碰最安全。
//      ⚠️ 绝不能把清空放进 loadGraphData 拦截点(早期写法), 两点原因:
//         ① 拦截那刻 store 还没摘掉标签, 关闭可能被用户取消(弹窗选「取消」), 清了就是误伤;
//         ② 与上游后半段的 removeDraft / discardPreviewsForWorkflow 交错, 状态机不干净。
//         前面说的「延迟清空会清掉真实加载」也仍未变 —— 任何 clear 都不能跨 await 落后于加载。
//   4. 关完之后 activeWorkflow 仍指着那个已不在 openWorkflows 里的旧对象, 必须置空;
//      前端源码里 activeWorkflow 到处都有 `?.` / `if (!activeWorkflow) return` 守卫,
//      null 是安全状态(useWorkflowPersistenceV2 的 restoreState 也显式处理了空值)。
//
// ⚠️ 验收陷阱(2026-11-12 实测): 判断「画布有没有节点」**不能用 `app.rootGraph._nodes`**。
//    在 headless Edge 下它恒为 0(工作流真实内容在 `activeWorkflow.activeState.nodes`, 0062 是 12),
//    也从未走到 `rootGraph.configure()`。拿它做断言会得到"永远通过"的假阳性。
//    可验的是**副作用探针**: 给 `rootGraph.clear` 装计数, 确认「关最后一个 = 1 次、
//    关非活动标签 = 0 次」; 真实视觉上的画布清空需要人眼在浏览器里确认一次。


const { app } = window.comfyAPI.app;

/**
 * 扩展行为开关(改完刷新页面即可生效)。
 *
 * 2026-11-12: 补上「关闭最后一个工作流时清空画布」。此前只拦"自动打开"、不碰画布, 结果是
 * **标签栏空了但画布上还留着刚关掉那份图的节点**(上游 closeWorkflow 只摘标签, 清画布原本是
 * 靠它后续的 loadDefaultWorkflow→clean() 顺带完成, 那条已被拦掉 ⇒ 没人清)。
 *
 * 实现位置是 `installCloseWorkflowHook`(包 store.closeWorkflow), 不是 loadGraphData 拦截点 ——
 * 那里能确定「关闭已成功」, 不会误伤用户取消关闭的场景。
 */
const OPTIONS = {
  /** 关闭最后一个工作流后不再自动打开默认/空白工作流 */
  suppressOnClose: true,
  /** 页面加载后不自动打开默认工作流(每次刷新都是空白画布 + 0 标签) */
  suppressOnStartup: true,
  /** 关闭最后一个工作流后把画布上的节点清空(否则标签空了画布还留着旧图) */
  clearCanvasOnClose: true,
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

/** 已挂 closeWorkflow 钩子的 store(避免重复包装) */
const closeHookInstalled = new WeakSet();

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
 * 清空画布上的所有节点与连线。
 *
 * 关闭最后一个工作流后必须调用: 上游 `closeWorkflow` 只从 store 里摘标签, 而"清画布"原本
 * 由它后续的 `loadDefaultWorkflow() → loadGraphData() → clean()` 顺带完成 —— 那条调用已被
 * 本扩展拦掉, 于是画布会**留着刚关掉那份图的节点**, 出现"标签栏空了但画布还有图"的怪状。
 *
 * ⚠️ 必须**同步**执行(在拦截点当场清), 绝不能放进 setTimeout/await 之后:
 * 前端 1.55.18+ 的 `loadGraphData` 原地复用同一个 `rootGraph`(`rootGraph.configure(e)`),
 * 延迟清空会落在**紧接着的真实加载之后**, 把用户刚点开的工作流清成空图。
 *
 * 清空方式与前端 `app.clean()` 内部保持一致(`rootGraph.clear()`), 但**不调 `app.clean()` 本身**:
 * 它会额外 `resetAllOutputsAndPreviews()`(抹掉所有节点的预览缓存)与 `setActiveGraph(null)`,
 * 在前端正在关闭工作流的中途调用容易与后续的 activateLoadedWorkflow 抢状态。这里只清根图,
 * 并 `setDirtyCanvas(true, true)` 让 LiteGraph 立刻重绘画布。
 *
 * @returns {boolean} 确实执行了清空返回 true
 */
function clearCanvasNow() {
  try {
    const g = app?.rootGraph;
    if (!g || typeof g.clear !== 'function') {
      console.warn(LOG, '清空画布跳过: rootGraph 不可用');
      return false;
    }
    const before = g._nodes?.length ?? 0;
    g.clear();
    // 重绘: `setDirtyCanvas` 挂在 **graph** 上(不是 canvas 上), 前端自己的用法见
    // GraphView 里的 `node.graph?.setDirtyCanvas(!0,!0)`, 两个实参分别是"清背景/清前景缓存"。
    try {
      g.setDirtyCanvas?.(true, true);
    } catch (e) {
      console.warn(LOG, 'graph.setDirtyCanvas 失败(不影响清空)', e);
    }
    console.log(LOG, `画布已清空(移除 ${before} 个节点)`);
    return true;
  } catch (e) {
    console.warn(LOG, '清空画布失败', e);
    return false;
  }
}

/**
 * 包装 workflow store 的 `closeWorkflow`, 在**它自己关完之后**判断"是不是一个都不剩了",
 * 是则回收悬空的 activeWorkflow 并清空画布。
 *
 * 为什么不在 loadGraphData 拦截点清(原实现的写法):
 *   拦截点只说明"上游正要塞默认图", 而 store 里那个工作流**还没被摘掉**
 *   (`t.closeWorkflow(e)` 是上游函数的最后一步)。那一刻清画布虽然能让 canvas 变空, 但
 *   ① 关闭可能被用户取消(弹窗里选「取消」), 此时清空就是误伤;
 *   ② 与上游后半段的 removeDraft / discardPreviewsForWorkflow 交错, 状态机不干净。
 * 包在 store 层就没有这些问题: 走到这里说明**关闭已经成功**, openWorkflows 是最终状态。
 *
 * @returns {boolean} 已安装返回 true(store 未就绪则 false, 由调用方重试)
 */
function installCloseWorkflowHook() {
  const ws = workflowStore();
  if (!ws || typeof ws.closeWorkflow !== 'function') return false;
  if (closeHookInstalled.has(ws)) return true;
  if (isDisabledByQuery()) return false;

  const original = ws.closeWorkflow;
  ws.closeWorkflow = async function (...args) {
    const result = await original.apply(this, args);
    try {
      // 关闭失败(用户取消 / 脏文件未保存) → 什么都不做, 保持原样
      if (result === false) return result;
      const open = this.openWorkflows ?? [];
      if (open.length === 0) {
        if (OPTIONS.clearCanvasOnClose) clearCanvasNow();
        reapDetachedActiveWorkflow();
      }
    } catch (e) {
      console.warn(LOG, '关闭后收尾失败', e);
    }
    return result;
  };

  closeHookInstalled.add(ws);
  console.log(LOG, 'closeWorkflow 钩子已就位(关闭最后一个工作流时清空画布)');
  return true;
}

/**
 * 拦截"自动打开工作流", 换成"保持不打开任何工作流"。
 *
 * 本函数**只负责拦加载**, 不产生任何副作用: 不新建标签、不加载任何图、不碰画布。
 * "关闭后清空画布 / 把悬空 activeWorkflow 置空"由 `installCloseWorkflowHook` 在
 * store 层完成 —— 那里能确定关闭已经成功, 且 openWorkflows 是最终状态。
 *
 * @param {string} kind classifyAutoOpen 的判定结果
 * @returns {Promise<void>} 与原调用同样可 await
 */
function suppressAutoOpen(kind) {
  // 只拦"加载", 不做任何收尾动作 —— 清画布与置空 activeWorkflow 都归 installCloseWorkflowHook
  // (它挂在 store.closeWorkflow 上, 在关闭真正成功后执行, 时序确定; 见该函数的注释)。
  // 这里若也清一次, 关闭被用户取消时会误伤, 故一律不碰。
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
   * 扩展初始化钩子: 接管 loadGraphData, 并轮询等 #vue-app 与 workflow store 挂出来后
   * 分别给 getMostRecentWorkflow(识别关闭时机) 与 closeWorkflow(关闭后清画布) 挂钩子。
   *
   * @returns {void}
   */
  setup() {
    installLoadGraphDataHook();

    let tries = 0;
    const timer = setInterval(() => {
      // 两个钩子都要装: 前哨负责"让拦截生效", closeWorkflow 钩子负责"关闭后清空画布"。
      // 用 & 而非 || 保证同一次轮询里两个都试一遍, store 未就绪则下轮重试。
      const sentinel = installCloseSentinel();
      const closeHook = installCloseWorkflowHook();
      if ((sentinel && closeHook) || ++tries > 240) clearInterval(timer);
    }, 50);
  },
});
