/**
 * PreviewVideo 前端: 「保存」按钮 + 预览恢复。
 *
 * 截帧/完成/选中帧输出已迁至加载视频节点(FallingTSLoadVideo, 见 web/js/load_video.js);
 * 本节点此后只做「预览 + 保存」, 与核心 SaveVideo 的分工一致。
 *
 * 行为:
 * - 预览部分由节点原生 UI.PreviewVideo 负责(播放 temp 目录文件);
 * - 点「保存」: 把 文件名前缀/后缀 POST 到 /preview-video/save/{id},
 *   后端用 execute 时缓存的视频数据直接写 output({filename_prefix}{filename_suffix}.mp4,
 *   同名覆盖、无序号) —— 【不触发任何工作流重跑】, 保存的是当前画面上播放的这段视频;
 * - 刷新后重建预览: 原生 UI.PreviewVideo 是一次性 WebSocket 事件, 页面刷新后不重发,
 *   由 restoreVideo() 从 GET /preview-video/video-url/{id} 拉回 URL 填上(优先填原生
 *   <video>, 找不到才显示备用播放器)。
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_CLASS = "PreviewVideo";

/**
 * Nodes 2.0 渲染模式: 保存按钮由 WidgetButton 组件渲染为 DOM <button>。
 * 不依赖 CSS 选择器/aria-label, 直接用 JS 遍历按钮, 按文本/aria 匹配"保存",
 * 逐个设置 element.style(渐变、圆角、更高); MutationObserver 持续监控懒渲染。
 * 全局只初始化一次(三个 preview js 共享)。
 *
 * @param {HTMLElement} el 按钮元素
 * @returns {void}
 */
function applySaveBtnStyle(el) {
  el.style.height = "40px";
  el.style.minHeight = "40px";
  el.style.padding = "8px 12px";
  el.style.background = "linear-gradient(135deg,#6a5cff,#9d5cff)";
  el.style.color = "#fff";
  el.style.borderRadius = "8px";
  el.style.fontSize = "15px";
  el.style.fontWeight = "700";
  el.style.letterSpacing = "1px";
  el.style.boxShadow = "0 2px 8px rgba(106,92,255,.35)";
  el.style.transition = "all .2s ease";
  el.style.border = "none";
  if (!el._fallingtsStyled) {
    el._fallingtsStyled = true;
    el.addEventListener("mouseenter", () => {
      el.style.background = "linear-gradient(135deg,#7b6dff,#ad6dff)";
      el.style.boxShadow = "0 4px 14px rgba(106,92,255,.5)";
      el.style.transform = "translateY(-1px)";
    });
    el.addEventListener("mouseleave", () => {
      el.style.background = "linear-gradient(135deg,#6a5cff,#9d5cff)";
      el.style.boxShadow = "0 2px 8px rgba(106,92,255,.35)";
      el.style.transform = "";
    });
  }
}

/**
 * 判断是否为保存按钮(文本或 aria-label 为 保存/Save)。
 *
 * @param {HTMLElement} el 元素
 * @returns {boolean} 是否保存按钮
 */
function isSaveBtn(el) {
  if (!el || el.tagName !== "BUTTON") return false;
  const txt = (el.innerText || "").trim();
  const aria = (el.getAttribute("aria-label") || "").trim();
  return txt === "保存" || txt === "Save" || aria === "保存" || aria === "Save";
}

/**
 * 取当前工作流的名字, 用于让后端把产物写进 output 下的同名子目录。
 * 前端各版本存放位置不一, 逐级兜底; 取不到返回空串, 后端会退回 output 根目录。
 *
 * @returns {string} 工作流名(已去掉 .json 后缀); 取不到时为空串
 */
function currentWorkflowName() {
  try {
    const store = app?.extensionManager?.workflow ?? app?.workflowManager;
    const wf = store?.activeWorkflow;
    const raw = wf?.name || wf?.filename || wf?.path || "";
    return String(raw).replace(/\.json$/i, "");
  } catch {
    return "";
  }
}

/**
 * 取当前工作流的根 id(= 工作流 JSON 的根 id, 即 graph.serialize().id)。
 *
 * 后端拿它给预览缓存加作用域: 只按节点 id 缓存会让各工作流之间**同 id 的节点互相串片**
 * (节点 id 在工作流之间大量重复, 实测 18 撞 6 个工作流), 打开工作流 B 时会把之前跑过的
 * A 的同 id 节点预览当成 B 的预览播出来。后端在 execute 时从 extra_pnginfo.workflow.id
 * 取到的是同一个值(前端 graphToPrompt() 把 graph.serialize() 整个塞进 extra_pnginfo.workflow)。
 *
 * @returns {string} 工作流根 id; 取不到时为空串(后端退回纯节点 id)
 */
function currentWorkflowId() {
  try {
    // 必须取**根图**: 前端 graphToPrompt() 默认序列化 rootGraph, extra_pnginfo.workflow.id
    // 来自它; 取子图(node.graph)会拿到别的 id, 与后端存的键对不上
    const g = app?.rootGraph ?? app?.graph;
    if (!g) return "";
    return String(g.id || g.serialize?.()?.id || "");
  } catch {
    return "";
  }
}

/**
 * 遍历页面按钮, 对保存按钮套样式。
 *
 * @returns {void}
 */
function styleSaveButtons() {
  document.querySelectorAll("button").forEach((el) => {
    if (isSaveBtn(el)) applySaveBtnStyle(el);
  });
}

// 保存按钮扫描: 沿用三个 preview js 共享的全局门控(由先加载的那个 js 初始化)
if (!window.__fallingtsSaveBtnInited) {
  window.__fallingtsSaveBtnInited = true;
  const init = () => {
    styleSaveButtons();
    new MutationObserver(styleSaveButtons).observe(document.body, { childList: true, subtree: true });
  };
  if (document.body) init();
  else document.addEventListener("DOMContentLoaded", init);
}

/**
 * 兼容 canvas roundRect(老浏览器无 ctx.roundRect 时用 arcTo 手绘圆角路径)。
 *
 * @param {CanvasRenderingContext2D} ctx canvas 上下文
 * @param {number} x 左上角 x
 * @param {number} y 左上角 y
 * @param {number} w 宽
 * @param {number} h 高
 * @param {number} r 圆角半径
 * @returns {void}
 */
function drawRoundRect(ctx, x, y, w, h, r) {
  if (ctx.roundRect) {
    ctx.roundRect(x, y, w, h, r);
    return;
  }
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x + w, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/**
 * 给「保存」按钮 widget 应用大气样式: 覆写 draw 用 canvas 绘制渐变圆角按钮,
 * 行高提高到 56; 点击时下压反馈(canvas 渲染模式下的兜底)。
 *
 * @param {LGraphNode} node 节点对象(其 widgets 里含 type === "button" 的保存按钮)
 * @returns {void}
 */
function styleSaveButton(node) {
  const btn = node.widgets?.find((w) => w.type === "button");
  if (!btn) return;

  btn.computedHeight = 56;

  const origDraw = btn.draw;
  const origMouse = btn.mouse;

  btn.draw = function (ctx, _node, widget_width, y, H) {
    const W = widget_width;
    const dy = this._pressed ? 1 : 0; // 点击时按钮下压 1px
    const BH = 52; // 按钮目标高度(固定, 不依赖外部 H)
    drawRoundRect(ctx, 6, y + 6, W - 12, BH - 8, 10);
    ctx.fillStyle = "rgba(0,0,0,.22)";
    ctx.fill();
    drawRoundRect(ctx, 6, y + 3 + dy, W - 12, BH - 8, 10);
    const g = ctx.createLinearGradient(0, y, 0, y + BH);
    if (this._pressed) {
      g.addColorStop(0, "#5a4cf0");
      g.addColorStop(1, "#8a4cf0");
    } else {
      g.addColorStop(0, "#6a5cff");
      g.addColorStop(1, "#9d5cff");
    }
    ctx.fillStyle = g;
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,.2)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = "#ffffff";
    ctx.font = "700 16px 'Segoe UI','Microsoft YaHei',sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("保存", W / 2, y + BH / 2 + 1 + dy);
  };

  btn.mouse = function (event, pos, node) {
    const inBtn = this.last_y != null && pos[1] >= this.last_y && pos[1] <= this.last_y + (this.computedHeight || 20);
    if (event.type === "mousedown") this._pressed = true;
    if (event.type === "mouseup" || (event.type === "mousedown" && !inBtn)) this._pressed = false;
    return origMouse ? origMouse.call(this, event, pos, node) : false;
  };

  node.setDirtyCanvas(true, true);
}

/**
 * 创建备用 <video> widget(仅在原生视频预览缺失时显示)。
 *
 * 原生 UI.PreviewVideo 是一次性 WebSocket 事件, 页面刷新后不会重发, 视频预览就空了。
 * 这个备用播放器由 restoreVideo() 从 /preview-video/video-url 拉 URL 填上; 若节点上
 * 已有 ComfyUI 渲染的原生 <video>, 则隐藏它以免出现两个播放器。
 *
 * @param {LGraphNode} node 节点
 * @returns {object} widget
 */
function createVideoFallbackWidget(node) {
  const root = document.createElement("div");
  root.style.cssText = "width:100%;box-sizing:border-box;padding:0 4px;display:none;";

  const videoEl = document.createElement("video");
  videoEl.controls = true;
  videoEl.preload = "none";
  videoEl.style.cssText = "display:block;width:100%;max-height:240px;background:#000;border-radius:6px;";
  root.appendChild(videoEl);

  const widget = node.addDOMWidget("video_fallback", "video", root, {
    serialize: false,
    hideOnZoom: false,
    getValue: () => "",
    setValue: () => {},
  });
  widget.computeSize = (width) => [width, 0];
  widget.element = root;
  widget.videoEl = videoEl;
  return widget;
}

/**
 * 刷新后重建视频预览: 拉回 URL 并填到原生 <video>, 原生不存在时改用备用播放器。
 *
 * 两个关键点(2026-09-22 修「点击播放报 视频加载失败 / Invalid URL」):
 * ① URL 一律转成**绝对**地址 —— 前端原生 VideoPreview 组件的文件名标签是
 *    new URL(e).searchParams.get("filename"), 相对路径("/view?..." 或 "/api/view?...")
 *    会让 new URL 抛错, 标签直接显示成 "Invalid URL";
 * ② 原生播放器只在"指向的文件不是本次这个"时才改写 src。
 *
 * ⚠️ 不要往 app.nodePreviewImages[nodeId] 里写地址: getNodeImageUrls 会**优先**读它,
 *    一旦写进去, 前端后续渲染就一直用这个快照值(每次执行后不会自己刷新), 预览反而
 *    停在旧文件上; 实测写它还会让节点预览进入递归更新、页面主线程卡死。
 *
 * @param {LGraphNode} node 节点
 * @returns {Promise<void>} 无
 */
async function restoreVideo(node) {
  const fb = node._fallingtsVideoFallback;
  let url = null;
  try {
    const wid = encodeURIComponent(currentWorkflowId());
    const r = await fetch(`/preview-video/video-url/${node.id}?workflow_id=${wid}`);
    const j = await r.json().catch(() => null);
    if (r.ok && j?.status === "ok") url = j.url;
  } catch {
    /* 后端未就绪时忽略 */
  }
  if (!url) {
    if (fb) fb.element.style.display = "none";
    return;
  }

  const absUrl = new URL(url, window.location.origin).href;

  // 节点内已有的原生 <video>(排除备用播放器自己)
  const host = document.querySelector('[data-node-id="' + node.id + '"]');
  const nativeVid = host
    ? [...host.querySelectorAll("video")].find((v) => !(fb?.element?.contains(v) ?? false))
    : null;

  if (nativeVid) {
    const cur = nativeVid.getAttribute("src");
    let curName = null;
    try {
      curName = cur ? new URL(cur, window.location.origin).searchParams.get("filename") : null;
    } catch {
      curName = null;
    }
    const newName = new URL(absUrl).searchParams.get("filename");
    if (curName !== newName) {
      nativeVid.dataset.src = absUrl;
      nativeVid.src = absUrl;
      nativeVid.controls = true;
    }
    if (fb) fb.element.style.display = "none";
    return;
  }

  if (fb) {
    fb.element.style.display = "";
    if (fb.videoEl.dataset.src !== absUrl) {
      fb.videoEl.dataset.src = absUrl;
      fb.videoEl.src = absUrl;
      fb.videoEl.load();
    }
  }
}

/**
 * 老存档兼容: PreviewVideo 在「截帧/选中帧输出」迁往 FallingTSLoadVideo 之前保存的工作流里,
 * 右侧会残留「选中帧 1..64」/ image_1..N 的输出端口(节点定义只剩 video, 但序列化数据把旧端口带了回来)。
 * 这里在节点配置时把它裁到只剩 video。与 load_video.js syncFrameState 同款保护:
 * 带链接的尾部端口不强删(强删会让前端重建链接时报 "Cannot set properties of undefined")。
 *
 * @param {LGraphNode} node PreviewVideo 节点
 * @returns {void}
 */
function trimFrameOutputs(node) {
  while ((node.outputs?.length ?? 0) > 1) {
    const tail = node.outputs[node.outputs.length - 1];
    if (tail && (tail.links?.length ?? 0) > 0) break;
    node.removeOutput(node.outputs.length - 1);
  }
}

app.registerExtension({
  name: "FallingTS.PreviewVideo",

  /**
   * 扩展初始化钩子。
   *
   * ① 包装全局提交入口 app.queuePrompt: 默认 Run(未显式指定目标节点)时, 先 POST
   *    /preview-video/reset 重置所有预览节点, 再按原逻辑全量提交 —— 保证每次 Run 都
   *    重新编码 temp 并发预览事件。partial 提交保留已放行状态, 不重置。
   * ② 监听执行事件, 让视频预览在跑完后重新判定一次(原生 <video> 由 Vue 异步挂载,
   *    比 onConfigure 晚), 按 600ms / 2.5s 两拍各调一次 restoreVideo。
   *
   * @returns {Promise<void>} 无
   */
  async setup() {
    const orig = app.queuePrompt?.bind(app);
    if (orig) {
      app.queuePrompt = async function (number, batch, queueNodeIds) {
        if (!queueNodeIds?.length) {
          try {
            await fetch("/preview-video/reset", { method: "POST" });
          } catch {
            /* 忽略 */
          }
        }
        return orig(number, batch, queueNodeIds);
      };
    }

    let timer = null;
    const refresh = () => {
      clearTimeout(timer);
      const run = () => {
        for (const n of app.graph?._nodes || []) {
          if (n.type === NODE_CLASS) restoreVideo(n);
        }
      };
      timer = setTimeout(run, 600);
      setTimeout(run, 2500);
    };
    // 只挂 executed / execution_success 两个低频事件: 原生 <video> 由 Vue 异步挂载,
    // 比 onConfigure 晚, 跑完后按 600ms / 2.5s 两拍重判定一次即可。
    // ⚠️ 不挂 progress —— 它每个采样步都发, 会把「跑完再判定」变成高频轮询。
    api.addEventListener("executed", refresh);
    api.addEventListener("execution_success", refresh);
  },

  /**
   * 节点定义注册前钩子: 给 PreviewVideo 追加「保存」按钮与备用播放器。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      node.addWidget("button", "保存", null, async () => {
        const prefixWidget = node.widgets?.find((w) => w.name === "filename_prefix");
        const prefixLinked = node.inputs?.find((i) => i.name === "filename_prefix")?.link != null;
        // filename_suffix 同前缀: 连线时用 execute 实际接收值, 手动输入用 widget 值
        const suffixWidget = node.widgets?.find((w) => w.name === "filename_suffix");
        const suffixLinked = node.inputs?.find((i) => i.name === "filename_suffix")?.link != null;
        try {
          const resp = await fetch("/preview-video/save/" + node.id, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_prefix: prefixWidget?.value ?? "video",
              filename_prefix_linked: prefixLinked,
              filename_suffix: suffixWidget?.value ?? "",
              filename_suffix_linked: suffixLinked,
              // 当前工作流名: 后端据此在 output 下建同名子目录再保存(取不到则由后端回退 output 根)
              workflow_name: currentWorkflowName(),
              // 当前工作流根 id: 后端据此定位「本次执行」的预览缓存 —— 不带就会把别的
              // 工作流同 id 节点缓存的视频存进来(跨工作流串片)
              workflow_id: currentWorkflowId(),
            }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            app.extensionManager.toast.add({ severity: "error", summary: data?.message ?? "保存失败", life: 3000 });
            return;
          }
          app.extensionManager.toast.add({ severity: "success", summary: data?.message ?? "已保存", life: 3000 });
        } catch (err) {
          console.error("[FallingTS] 保存失败:", err);
          app.extensionManager.toast.add({ severity: "error", summary: "保存失败: 无法连接后端", life: 3000 });
        }
      });
      styleSaveButton(node);

      // 备用视频播放器: 页面刷新后原生 UI.PreviewVideo 不重发, 由 restoreVideo 补上
      node._fallingtsVideoFallback = createVideoFallbackWidget(node);

      const prevOnConfigure = node.onConfigure;
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        // 老存档可能带回「选中帧/image_N」残端口: 裁到只剩 video(本节点已只保留保存功能)
        trimFrameOutputs(node);
        // 后端是唯一事实来源: 从它读回视频预览并重建前端(刷新不丢)
        restoreVideo(node);
      };
    };
  },
});
