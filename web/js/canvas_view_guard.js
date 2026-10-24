/**
 * FallingTS.CanvasViewGuard —— 保护「工作流保存的画布视图(ds)」不被第三方插件强改。
 *
 * ## 问题(2026-10-24 实测确认)
 *
 * 加载工作流后, 画布视图本应由前端 `fitView` 按工作流 `extra.ds` 恢复:
 *   savedDs   = { scale: 0.675, offset: [-4691, -253] }
 *   fitView 后 = { scale: 0.675, offset: [-4691, -253] }   ← 正确(纯核心环境实测)
 *
 * 但装了 `comfyui-mixlab-nodes` 后, 它的 `loadedGraphNode(node, app)` 钩子对**每一个节点**
 * 无条件执行:
 *   if ((app.graph._nodes[last].id, node.id)) {   // 逗号表达式, 恒为真
 *     app.canvas.centerOnNode(node)
 *     app.canvas.setZoom(0.45)                    // 硬编码 0.45
 *   }
 * —— 于是每加载一个节点就把视图拽到该节点并缩放到 0.45, 最后一个节点赢。
 * 实测 39 个节点 ⇒ 39 次 setZoom(0.45), 最终 ds 变成 { scale: 0.45, offset: [-6817, 141] }。
 *
 * 表现: 打开工作流后**节点和连线都在屏幕外**, 看起来就是「画布空白 / 连线没了」。
 * 用 Proxy 拦截 ds 写入抓到的调用栈(节选):
 *   at LGraphCanvas.setZoom (settingStore-DZ2-HL-F.js:2:404244)
 *   at Object.loadedGraphNode (extensions/comfyui-mixlab-nodes/javascript/ui_mixlab.js:2211)
 *
 * ## 对策
 *
 * 不去改第三方插件源码(上游子模块不允许提交), 而是在前端把 `setZoom` / `centerOnNode`
 * 在「工作流加载窗口」内临时钉住:
 *   - 窗口 = 一次图加载的 loadedGraphNode 批量执行期间, 用微任务在批量结束后自动解除;
 *   - 窗口内**保留第一次**的合法调用(若前端自己要恢复视图), 只丢弃后续强制改写;
 *   - 窗口外完全放行, 用户手动滚轮缩放、双击适配、其它插件的正常居中一律不受影响。
 *
 * 实测(屏蔽 mixlab 的 setZoom + centerOnNode 后加载 0020):
 *   savedDs  = { scale: 0.675, offset: [-4691, -253] }
 *   actualDs = { scale: 0.675, offset: [-4691, -254] }   ← 完全复原, 节点连线都在视野内
 *
 * ## 关闭方式
 *
 * URL 加 `?canvasViewGuard=off` 即可停用(排查用)。
 */

import { app } from "../../../scripts/app.js";

const LOG = "[CanvasViewGuard]";

/**
 * 开关: URL 加 `?canvasViewGuard=off` 可临时停用。
 *
 * @returns {boolean} 被 URL 停用返回 true
 */
function isDisabledByQuery() {
  try {
    return new URLSearchParams(location.search).get("canvasViewGuard") === "off";
  } catch {
    return false;
  }
}

/** 已知会无条件强改视图的调用方特征(仅用于日志, 不参与拦截判定) */
const KNOWN_OFFENDERS = ["ui_mixlab.js", "mixlab"];

/**
 * 是否处于「工作流批量加载中」。
 *
 * 前端在 loadGraphData 里逐个触发 extensions.loadedGraphNode, 这整段是同步的;
 * 用一个同步窗口标记 + 微任务收尾即可精确覆盖, 不会误伤用户后续的手动缩放。
 */
let loadWindowDepth = 0;
/** 本次窗口内已放行过几次视图改写(只放行第一次) */
let allowedWrites = 0;

/**
 * 判断某个调用是否来自已知的有害插件。
 *
 * @returns {boolean} 来自 mixlab 一类强制改写者返回 true
 */
function isFromKnownOffender() {
  try {
    const stack = new Error().stack || "";
    return KNOWN_OFFENDERS.some((k) => stack.includes(k));
  } catch {
    return false;
  }
}

/** 记录被拦截的次数, 便于日志汇总 */
let blockedCount = 0;

/**
 * 在加载窗口内钉住画布视图 API(幂等)。
 *
 * @returns {boolean} 已安装返回 true
 */
let installed = false;
function installGuard() {
  if (installed) return true;
  if (isDisabledByQuery()) {
    console.log(LOG, "已被 URL 停用");
    return false;
  }
  const canvas = app?.canvas;
  if (!canvas || typeof canvas.setZoom !== "function") return false;
  if (typeof canvas.centerOnNode !== "function") return false;

  const proto = Object.getPrototypeOf(canvas);
  if (!proto || proto.__fallingtsViewGuard) return true;

  const origSetZoom = canvas.setZoom;
  const origCenterOnNode = canvas.centerOnNode;

  /**
   * 通用拦截器: 只在加载窗口内、且来自已知害插件时丢弃。
   *
   * 之所以按调用方过滤而不是「窗口内一律丢弃」—— 前端自身恢复 ds 也走这两个 API,
   * 一律丢弃会把正确的视图也挡掉。
   *
   * @param {Function} original 原方法
   * @param {string} name 方法名(日志用)
   * @returns {Function} 包装后的方法
   */
  function wrap(original, name) {
    return function (...args) {
      if (loadWindowDepth > 0 && isFromKnownOffender()) {
        blockedCount++;
        if (blockedCount === 1) {
          console.log(LOG, `已拦截第三方插件的画布视图强制改写(${name}), 后续同类静默丢弃`);
        }
        return undefined;
      }
      return original.apply(this, args);
    };
  }

  canvas.setZoom = wrap(origSetZoom, "setZoom");
  canvas.centerOnNode = wrap(origCenterOnNode, "centerOnNode");
  proto.__fallingtsViewGuard = true;
  installed = true;
  console.log(LOG, "已就位(保护工作流保存的画布视图)");
  return true;
}

/**
 * 打开「工作流批量加载」窗口, 并在当前同步批次结束后自动关闭。
 *
 * @returns {void}
 */
function openLoadWindow() {
  loadWindowDepth++;
  allowedWrites = 0;
  // 微任务收尾: 前端 loadedGraphNode 的批量调用是同步的, 一个微任务足够覆盖整批
  queueMicrotask(() => {
    if (loadWindowDepth > 0) loadWindowDepth--;
  });
}

app.registerExtension({
  name: "FallingTS.CanvasViewGuard",

  /**
   * 扩展初始化: 尽早接管画布视图 API。
   *
   * @returns {void}
   */
  setup() {
    const boot = () => {
      if (installGuard()) return;
      setTimeout(boot, 200);
    };
    boot();
  },

  /**
   * 图配置前(每个工作流加载时触发一次): 打开保护窗口。
   *
   * @returns {void}
   */
  beforeConfigureGraph() {
    installGuard();
    openLoadWindow();
  },

  /**
   * 每个节点加载后触发。这里是 mixlab 强改视图的时机, 保证窗口仍然开着。
   *
   * @returns {void}
   */
  loadedGraphNode() {
    // 前端每个节点都会进这里; 若窗口已因微任务关闭, 重新打开一格,
    // 让伴随的同步 centerOnNode/setZoom 仍在窗口内
    loadWindowDepth++;
    queueMicrotask(() => {
      if (loadWindowDepth > 0) loadWindowDepth--;
    });
  },

  /**
   * 图配置完成后: 汇总本次拦截情况。
   *
   * @returns {void}
   */
  afterConfigureGraph() {
    if (blockedCount > 0) {
      console.log(LOG, `本次加载共拦截 ${blockedCount} 次视图强制改写, 画布视图按工作流保存值恢复`);
      blockedCount = 0;
    }
  },
});
