/**
 * PreviewVideo 前端: 「保存」按钮 + 「截帧」功能(选中帧列表 + 动态输出端口) + 预览恢复。
 *
 * 截帧机制与「加载视频」(web/js/load_video.js) 同套 —— 本节点是它的**输入版**:
 * 视频来自上游连线(CreateVideo), 而不是节点上的下拉文件。因此:
 *  - 截帧必须先运行到本节点: 帧集合是 execute 时 get_components() 拆出来缓存的,
 *    没有下拉值可供后端"现场拆帧"(加载视频那条懒解码兜底在这里不成立);
 *  - 其余(选中帧列表、完成门控、state 复原、动态端口、temp 预览兜底)与加载视频完全一致。
 *
 * 行为:
 * - 预览部分由节点原生 UI.PreviewVideo 负责(播放 temp 目录文件);
 * - 点「截帧」: 读取预览 <video> 的当前播放时间(秒), POST /preview-video/frame/{id}
 *   {position_seconds} —— 后端按 fps 折算帧号, 取帧转 PNG 返回并追加帧号到 selected_frames;
 * - 点「完成」(有帧): POST /preview-video/done/{id} 置完成, 再以 partial_execution_targets
 *   只提交本节点**下游**的输出节点 —— 上游因 lazy 边不进子图, 运行时看不到前面的节点;
 * - 点「完成」(无帧): POST /preview-video/reset 后全量提交 = 预加载上游(重新拉视频);
 * - 点「保存」: 把 文件名前缀/后缀 POST 到 /preview-video/save/{id},
 *   后端用 execute 时缓存的视频数据直接写 output({filename_prefix}{filename_suffix}.mp4,
 *   同名覆盖、无序号) —— 【不触发任何工作流重跑】;
 * - 刷新后重建: 原生 UI.PreviewVideo 是一次性 WebSocket 事件, 页面刷新后不重发,
 *   由 restoreVideo() 从 GET /preview-video/video-url/{id} 拉回 URL 填上;
 *   选中帧列表由 restoreFrames() 从 GET /preview-video/state/{id} 读回重绘(后端是唯一事实来源)。
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_CLASS = "PreviewVideo";
const MAX_FRAMES = 64;
// 固定端口数: video(0) + audio(1) + prefix(2), 选中帧自端口 3 起(与「加载视频」同布局)
const FIXED_OUTPUTS = 3;

/**
 * Nodes 2.0 渲染模式: 按钮由 WidgetButton 组件渲染为 DOM <button>。
 * 不依赖 CSS 选择器/aria-label, 直接用 JS 遍历按钮, 按文本/aria 匹配,
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
 * 后端拿它给预览/截帧缓存加作用域: 只按节点 id 缓存会让各工作流之间**同 id 的节点互相串片**
 * (节点 id 在工作流之间大量重复, 实测 18 撞 6 个工作流), 打开工作流 B 时会把之前跑过的
 * A 的同 id 节点预览当成 B 的预览播出来, 截帧也会从 A 的视频里取。后端在 execute 时从
 * extra_pnginfo.workflow.id 取到的是同一个值(graphToPrompt() 把 graph.serialize() 整个塞进去)。
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
 * 判断节点是否为「输出节点」(保存/预览等终端节点)。
 *
 * @param {LGraphNode} node 画布节点对象
 * @returns {boolean} 该节点的 nodeData.output_node 为 true 返回 true
 */
function isOutputNode(node) {
  return node?.constructor?.nodeData?.output_node === true;
}

/**
 * 从 startNode 下游 BFS, 收集所有输出节点, 作为 partial_execution_targets 传给 /prompt。
 *
 * @param {LGraphNode} startNode 锚点节点(本节点自身)
 * @returns {string[]} 输出节点的 ID 字符串数组(已去重)
 */
function collectOutputsAfter(startNode) {
  const targets = new Set();
  const visited = new Set();
  const queue = [];
  const graph = startNode.graph;
  for (const out of startNode.outputs ?? []) {
    for (const linkId of out.links ?? []) {
      const link = graph?.links?.[linkId];
      if (link) queue.push(link.target_id);
    }
  }
  while (queue.length) {
    const nid = queue.shift();
    if (visited.has(nid)) continue;
    visited.add(nid);
    const n = graph?.getNodeById?.(nid);
    if (!n) continue;
    if (isOutputNode(n)) targets.add(String(n.id));
    for (const out of n.outputs ?? []) {
      for (const linkId of out.links ?? []) {
        const link = graph?.links?.[linkId];
        if (link) queue.push(link.target_id);
      }
    }
  }
  return [...targets];
}

/**
 * 只提交「本节点下游」的部分执行(partial execution)。
 *
 * 注意不能写成 app.queuePrompt(0, 1, targets): api.queuePrompt 的第 3 参数是选项对象
 * {partialExecutionTargets}(驼峰), 传裸数组会被静默忽略、退化成全量提交。
 *
 * @param {LGraphNode} node 锚点节点
 * @param {string[]} targets 下游输出节点 id 列表
 * @returns {Promise<object>} 后端响应
 */
async function submitPartial(node, targets) {
  const prompt = await app.graphToPrompt();
  const resp = await api.fetchApi("/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: api.clientId,
      prompt: prompt.output,
      partial_execution_targets: targets,
      extra_data: { extra_pnginfo: { workflow: prompt.workflow } },
    }),
  });
  if (!resp.ok) {
    const t = await resp.text().catch(() => "");
    throw new Error("提交失败 HTTP " + resp.status + " " + t.slice(0, 200));
  }
  return resp.json();
}

/**
 * 创建选中帧列表 DOM widget: 内嵌容器, 从上往下渲染截帧 <img>, 每行带「✕」删除按钮。
 *
 * 列表按内容无限撑开(不设固定 height), 高度变化经 fitHeight 增量同步到节点 ——
 * 用增量法而非 computeSize, 是因为 ComfyUI 会把「剩余空间」分给所有 DOM widget
 * (视频预览 + 本列表), 用 computeSize 会把视频框压扁。
 *
 * @param {LGraphNode} node 节点
 * @returns {{widget: object, state: object, render: Function}} 列表 widget 与其状态
 */
function createFrameListWidget(node) {
  const EMPTY_H = 44;
  const ROW_H = 64;
  const GAP_H = 6;
  const frameBoxHeight = () =>
    state.frames.length === 0
      ? EMPTY_H
      : state.frames.length * ROW_H + (state.frames.length - 1) * GAP_H;

  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.gap = GAP_H + "px";
  root.style.overflow = "visible";
  root.style.width = "100%";
  root.style.boxSizing = "border-box";

  const state = { frames: [] };

  const render = () => {
    // 列表按内容无限撑开: 先重建 DOM, 再 fitHeight 同步节点到精确高度 ——
    // fitHeight 必须在 DOM 重建之后, 否则截帧后节点会按旧(更少)高度压缩。
    root.innerHTML = "";
    if (state.frames.length === 0) {
      const hint = document.createElement("div");
      hint.textContent = "点击「截帧」选取视频帧";
      hint.style.cssText = "color:#888;font-size:12px;padding:8px 4px;text-align:center;";
      root.appendChild(hint);
      fitHeight(node);
      return;
    }
    state.frames.forEach((f, idx) => {
      const row = document.createElement("div");
      row.style.cssText =
        "display:flex;align-items:center;gap:8px;padding:4px;background:rgba(255,255,255,.04);border-radius:6px;";

      const img = document.createElement("img");
      img.src = f.url;
      img.style.cssText = "height:56px;width:auto;border-radius:4px;display:block;";

      const labelWrap = document.createElement("div");
      labelWrap.style.cssText = "flex:1;display:flex;flex-direction:column;gap:2px;min-width:0;";
      const fnoEl = document.createElement("div");
      fnoEl.textContent = "帧 " + f.fno;
      fnoEl.style.cssText = "font-size:12px;color:#eee;font-weight:600;";
      labelWrap.appendChild(fnoEl);

      row.appendChild(img);
      row.appendChild(labelWrap);

      // 删除该帧(后端同步移除, 刷新后不会复活)
      const del = document.createElement("button");
      del.type = "button";
      del.textContent = "✕";
      del.style.cssText =
        "background:transparent;border:none;color:#f66;font-size:14px;cursor:pointer;padding:4px;";
      del.addEventListener("click", async () => {
        try {
          await fetch("/preview-video/frame-remove/" + node.id, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ frame_index: f.fno, workflow_id: currentWorkflowId() }),
          });
        } catch (err) {
          console.warn("[FallingTS] 删除帧失败:", err);
        }
        state.frames.splice(idx, 1);
        syncFrameState(node, state);
        render();
        emitDirty(node);
      });
      row.appendChild(del);

      root.appendChild(row);
    });
    fitHeight(node);
  };

  // 增量 fitHeight 基准: 初始列表 minHeight(空态 EMPTY_H)
  node._fallingtsListMin = frameBoxHeight();

  const widget = node.addDOMWidget("frame_list", "fallingts_frame_list", root, {
    getValue: () => state,
    setValue: () => {
      render();
    },
    getMinHeight: () => frameBoxHeight(),
    getMaxHeight: () => frameBoxHeight(),
    serialize: true,
  });
  render();
  return { widget, state, render };
}

/**
 * 同步选中帧状态: 更新 total 下限 + 按 total 对齐输出端口数量。
 *
 * total 规则(与 composite 同款): 最小 = max(1, 选中数); 输出端口数 = 3 + total 个 image,
 * 端口 0/1/2 固定是 video/audio/prefix(后端 schema 顺序), 选中帧自端口 3 起。
 *
 * @param {LGraphNode} node 节点对象
 * @param {object} state 选中帧列表状态 {frames: [{url, fno}]}
 * @returns {void}
 */
function syncFrameState(node, state) {
  const totalWidget = node._fallingtsTotalWidget;
  const selectedCount = state?.frames?.length ?? 0;
  const minTotal = Math.max(1, selectedCount);
  if (totalWidget?.options) {
    totalWidget.options.min = minTotal;
    const cur = Number(totalWidget.value) || 1;
    if (cur < minTotal) {
      totalWidget.value = minTotal;
      totalWidget.callback?.(minTotal);
    }
  }

  const total = Math.max(1, Number(totalWidget?.value) || 1);
  const target = FIXED_OUTPUTS + total;
  // 只删"无链接"的尾部端口: 带链接的端口强删会让前端重建链接时报
  // "Cannot set properties of undefined"(与 route/fanout/composite 同款保护)。
  while ((node.outputs?.length ?? 0) > target) {
    const tail = node.outputs[node.outputs.length - 1];
    if (tail && (tail.links?.length ?? 0) > 0) break;
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < target) {
    node.addOutput("image_" + (node.outputs.length - FIXED_OUTPUTS + 1), "IMAGE");
  }
  // 端口 1/2 固定是 audio / prefix(后端 schema 顺序); 老存档(本节点只有 video 输出时)
  // 这里可能是别的残留端口, 一并纠正成正确的名字与类型。
  if (node.outputs?.[1]) {
    node.outputs[1].name = "audio";
    node.outputs[1].label = "audio";
    node.outputs[1].type = "AUDIO";
  }
  if (node.outputs?.[2]) {
    node.outputs[2].name = "prefix";
    node.outputs[2].label = "文件名前缀";
    node.outputs[2].type = "STRING";
  }
  for (let i = FIXED_OUTPUTS; i < (node.outputs?.length ?? 0); i++) {
    const fno = state?.frames?.[i - FIXED_OUTPUTS]?.fno ?? (i - FIXED_OUTPUTS + 1);
    node.outputs[i].name = "image_" + (i - FIXED_OUTPUTS + 1);
    node.outputs[i].label = "选中帧 " + fno;
  }
  emitDirty(node);
}

/**
 * 截帧列表撑开时增量同步节点高度: 高度变化量 = 列表 minHeight 变化量。
 *
 * 为什么不用 computeSize: ComfyUI 把「剩余空间 e」经 distributeSpace 分给所有 DOM widget
 * (视频预览 + 列表); 用增量法(节点高 += Δ)则视频框高度保持不变。
 *
 * @param {LGraphNode} node 节点
 * @returns {void}
 */
function fitHeight(node) {
  const listWidget = node.widgets?.find((w) => w.name === "frame_list");
  if (!listWidget || !node.size) return;
  const newMin = listWidget.getMinHeight?.() ?? 0;
  const last = node._fallingtsListMin ?? newMin;
  const delta = newMin - last;
  node._fallingtsListMin = newMin;
  if (Math.abs(delta) > 0.5) {
    node.setSize([node.size[0], node.size[1] + delta]);
  }
}

/**
 * 标记节点数据变更(重绘 + 保存工作流时序列化)。
 *
 * @param {LGraphNode} node 节点对象
 * @returns {void}
 */
function emitDirty(node) {
  node.setDirtyCanvas?.(true, true);
  node.graph?.setDirtyCanvas?.(true, true);
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
 * 两个关键点(修「点击播放报 视频加载失败 / Invalid URL」):
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
 * 刷新后重建选中帧列表: 从后端读回帧号, 逐帧取 PNG 重绘缩略图。
 *
 * 后端是唯一事实来源(帧集合与选中帧号都在进程内存里), 前端 DOM state 只是它的投影 ——
 * 所以页面刷新后列表不丢, 与「截帧状态刷新即清空」的旧行为相反(旧行为已废弃)。
 *
 * @param {LGraphNode} node 节点
 * @param {object} frameList createFrameListWidget 的返回值
 * @returns {Promise<void>} 无
 */
async function restoreFrames(node, frameList) {
  if (!frameList) return;
  try {
    const wid = encodeURIComponent(currentWorkflowId());
    const r = await fetch(`/preview-video/state/${node.id}?workflow_id=${wid}`);
    const st = await r.json().catch(() => null);
    if (!r.ok || st?.status !== "ok") return;
    const fnos = st.selected_frames || [];
    if (!fnos.length) {
      if (frameList.state.frames.length) {
        frameList.state.frames = [];
        frameList.render();
        syncFrameState(node, frameList.state);
      }
      return;
    }

    const frames = [];
    for (const fno of fnos) {
      const resp = await fetch("/preview-video/frame/" + node.id, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "frame",
          frame_index: fno,
          append: false,
          workflow_id: currentWorkflowId(),
        }),
      });
      if (!resp.ok) continue;
      const blob = await resp.blob();
      frames.push({
        url: URL.createObjectURL(blob),
        fno: Number(resp.headers.get("X-Frame-Index") || fno),
      });
    }
    frameList.state.frames = frames;
    frameList.render();
    syncFrameState(node, frameList.state);
    fitHeight(node);
  } catch {
    /* 后端未就绪时忽略 */
  }
}

/**
 * 读当前「用户实际在拖动的」播放器的播放位置(秒)。
 *
 * 节点里可能同时存在两个 <video>: 原生预览 + 备用播放器(刷新后恢复预览用, 默认隐藏)。
 * 不能盲取第一个 —— 隐藏的备用元素 currentTime 恒为 0, 会导致每次都截到第 1 帧。
 *
 * @param {LGraphNode} node 节点
 * @returns {number} 播放位置(秒); 读不到为 0
 */
function currentPlaybackSeconds(node) {
  try {
    const domNode = document.querySelector('[data-node-id="' + node.id + '"]');
    const cands = [];
    if (domNode) cands.push(...domNode.querySelectorAll("video"));
    const fbEl = node._fallingtsVideoFallback?.videoEl;
    if (fbEl && !cands.includes(fbEl)) cands.push(fbEl);

    const playable = cands.filter((v) => v.src);
    const visible = playable.filter((v) => (v.getClientRects?.().length ?? 0) > 0);
    const pool = visible.length ? visible : playable;
    const pick = pool.reduce(
      (best, v) => (!best || (v.currentTime || 0) > (best.currentTime || 0) ? v : best),
      null,
    );
    return pick ? pick.currentTime || 0 : 0;
  } catch (err) {
    console.warn("[FallingTS] 读取播放时间失败, 取 0 秒:", err);
    return 0;
  }
}

/**
 * 老存档兼容: 本节点在「截帧/选中帧输出」迁出期间只保留了 video 一个输出端口。
 * 这里在 onConfigure 时按「输出帧数」把端口补/裁到 3 + total 个(syncFrameState 负责),
 * 并把老存档里可能残留的额外端口一并归位 —— 无链接的尾部端口直接裁掉, 带链接的保留
 * (强删会让前端重建链接时报 "Cannot set properties of undefined")。
 *
 * @param {LGraphNode} node 节点
 * @returns {void}
 */
function trimExtraOutputs(node) {
  while ((node.outputs?.length ?? 0) > FIXED_OUTPUTS) {
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
   *    /preview-video/reset 重置所有预览节点(全部回未完成态), 再按原逻辑全量提交 ——
   *    保证每次 Run 都重新拉上游、重新编码 temp 并发预览事件。partial 提交保留已放行状态。
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
   * 节点定义注册前钩子: 给 PreviewVideo 追加「保存/截帧/完成」按钮、选中帧列表与备用播放器。
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

      // ── 截帧按钮 → 输出帧数 → 选中帧列表(列表必须在按钮下方) ──
      node.addWidget("button", "截帧", null, async () => {
        const positionSeconds = currentPlaybackSeconds(node);
        try {
          const resp = await fetch("/preview-video/frame/" + node.id, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              position_seconds: positionSeconds,
              workflow_id: currentWorkflowId(),
            }),
          });
          if (!resp.ok) {
            const data = await resp.json().catch(() => null);
            app.extensionManager.toast.add({
              severity: "error",
              summary: data?.message ?? "截帧失败",
              life: 3000,
            });
            return;
          }
          const frameList = node._fallingtsFrameList;
          const fno = Number(resp.headers.get("X-Frame-Index") || (frameList?.state.frames.length ?? 0) + 1);
          const blob = await resp.blob();
          const url = URL.createObjectURL(blob);

          if ((frameList?.state.frames.length ?? 0) >= MAX_FRAMES) {
            app.extensionManager.toast.add({
              severity: "warn",
              summary: "已达截帧上限 " + MAX_FRAMES + " 张",
              life: 3000,
            });
            URL.revokeObjectURL(url);
            return;
          }

          frameList?.state.frames.push({ url, fno });
          // 先对齐输出端口/total, 再重绘列表(render 内按新盒高同步节点高度)
          syncFrameState(node, frameList?.state ?? { frames: [] });
          frameList?.render();
          // 节点上还没有播放器时(刷新后 / 首次运行延迟挂载), 用后端已建好的 temp 预览补一个;
          // 已有播放器则不动 —— 改写 src 会让用户正在播放的位置归零, 下一帧就截错地方
          const host = document.querySelector('[data-node-id="' + node.id + '"]');
          const players = [
            node._fallingtsVideoFallback?.videoEl,
            ...(host ? host.querySelectorAll("video") : []),
          ].filter((v) => v && v.src);
          const visible = players.filter((v) => (v.getClientRects?.().length ?? 0) > 0);
          const pool = visible.length ? visible : players;
          const broken = (v) => !v.getAttribute("src") || !!v.error || v.networkState === 3;
          if (!players.length || pool.some(broken)) restoreVideo(node);
        } catch (err) {
          console.error("[FallingTS] 截帧失败:", err);
          app.extensionManager.toast.add({ severity: "error", summary: "截帧失败: 无法连接后端", life: 3000 });
        }
      });

      // ── 完成: 无帧 = 视频已缓存则提示截帧, 否则只跑到本节点为止; 有帧 = 置完成后 partial 只跑下游 ──
      node.addWidget("button", "完成", null, async () => {
        const frames = node._fallingtsFrameList?.state?.frames ?? [];
        try {
          if (frames.length === 0) {
            // 无选中帧的「完成」= 让视频就绪供截帧。旧实现走 app.queuePrompt 全量提交,
            // 该入口被 proceed.js 包装过、会先 POST /proceed/reset 清空**全部**继续节点的
            // 放行态与 _data_cache ⇒ 之后点「继续」恒 400「没有上游数据」(与 e8b5d21 同源),
            // 且整图从头发跑一遍(实测 0031 跑了 18 与 186 两条链共 10 个输出节点)。
            //
            // 现在分两步, 都不经 app.queuePrompt:
            // ① 后端已有视频缓存 = 截帧与保存都能直接用, 无需重跑任何上游, 只提示去截帧;
            //    (本节点没截过帧但后端正缓存着视频, 是「刷新过页面」的常态 —— 前端 frame_list
            //    按设计刷新即清空, 而后端 _last_output 还在)
            // ② 确实没有视频才以本节点自身为唯一 partial 目标重跑: 引擎从本节点沿输入边
            //    向上游只拉本段生成链, 继续节点在旁支(不输入本节点)故不被触及,
            //    上游缓存/放行态原样保留。上游真有继续节点时(如二采预览), 那个继续节点
            //    会照旧把它自己的分段语义走完, 不会从整图最开头跑。
            let hasVideo = false;
            try {
              const wid = encodeURIComponent(currentWorkflowId());
              const st = await fetch(`/preview-video/state/${node.id}?workflow_id=${wid}`);
              if (st.ok) hasVideo = !!(await st.json())?.has_video;
            } catch {
              /* 查不到状态就按"没有视频"走, 由下面的部分提交兜底 */
            }
            if (hasVideo) {
              app.extensionManager.toast.add({
                severity: "info",
                summary: "视频已就绪, 请截帧后再点完成",
                life: 3000,
              });
              restoreFrames(node, node._fallingtsFrameList);
              restoreVideo(node);
              return;
            }
            try {
              await submitPartial(node, [String(node.id)]);
            } catch (err) {
              console.error("[FallingTS] 预加载失败:", err);
              app.extensionManager.toast.add({ severity: "error", summary: "预加载失败: 无法提交任务", life: 3000 });
              return;
            }
            app.extensionManager.toast.add({
              severity: "info",
              summary: "已开始生成视频, 播放后可截帧",
              life: 3000,
            });
            return;
          }
          const fnos = frames.map((f) => f.fno).filter((v) => Number.isFinite(v));
          const resp = await fetch("/preview-video/done/" + node.id, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ frames: fnos, workflow_id: currentWorkflowId() }),
          });
          if (!resp.ok) {
            app.extensionManager.toast.add({ severity: "error", summary: "完成失败: 后端无响应", life: 3000 });
            return;
          }
          const data = await resp.json().catch(() => null);
          if (!data?.done) {
            app.extensionManager.toast.add({ severity: "warning", summary: "请先截帧再点完成", life: 3000 });
            return;
          }
          // 释放上一段用过的生成模型内存(可选, 失败不影响)
          // ⚠️ 用自建路由而不是 POST /free: /free 只 set_flag, 要到下一次 prompt 跑完才被消费,
          // 与"提交前腾显存"的意图正好错开, 等于没卸。
          try {
            await fetch("/fallingts_auto_unload/unload", { method: "POST" });
          } catch {
            /* 忽略 */
          }
          const targets = collectOutputsAfter(node);
          if (!targets.length) {
            console.warn("[FallingTS] 预览视频节点之后没有输出节点");
            return;
          }
          await submitPartial(node, targets);
          app.extensionManager.toast.add({
            severity: "success",
            summary: "已完成, 截帧输出到下游",
            life: 3000,
          });
        } catch (err) {
          console.error("[FallingTS] 完成失败:", err);
          app.extensionManager.toast.add({ severity: "error", summary: "完成失败: 无法连接后端", life: 3000 });
        }
      });

      // ── 输出帧数: 输出 image 端口数量(默认 1, 最小 = max(1, 选中帧数), 上限 MAX_FRAMES) ──
      const totalWidget = node.addWidget(
        "number",
        "输出帧数",
        1,
        () => {
          syncFrameState(node, node._fallingtsFrameList?.state ?? { frames: [] });
        },
        { min: 1, max: MAX_FRAMES, step: 1, precision: 0 },
      );
      totalWidget.options.min = 1;
      totalWidget.options.max = MAX_FRAMES;
      node._fallingtsTotalWidget = totalWidget;

      const frameList = createFrameListWidget(node);
      node._fallingtsFrameList = frameList;

      // 备用视频播放器: 页面刷新后原生 UI.PreviewVideo 不重发, 由 restoreVideo 补上
      node._fallingtsVideoFallback = createVideoFallbackWidget(node);

      // 新拖入的节点: 裁到 3(video+audio+prefix) + total 个 image
      if ((node.outputs ?? []).length > 0) {
        trimExtraOutputs(node);
        syncFrameState(node, { frames: [] });
      }
      fitHeight(node);

      const prevOnConfigure = node.onConfigure;
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        if (!node._fallingtsFrameList) return;
        // 老存档兼容: 本节点曾只剩 video 一个输出端口(截帧迁出期间), 存档里也可能残留
        // 零散的选中帧端口 —— 先裁掉无链接的尾部端口, 再按存档的「输出帧数」重建。
        trimExtraOutputs(node);
        const _wv = info?.widgets_values;
        const _named = info?.widgets_values_named;
        // 本节点控件槽序: [前缀, 后缀, 保存, 截帧, 完成, 输出帧数, frame_list, video_fallback]
        // ⇒「输出帧数」在下标 5(不是加载视频那边的 10), 按名字取不到时只能按这个下标兜底
        const savedTotal = _named?.["输出帧数"] ?? (Array.isArray(_wv) ? _wv[5] : undefined);
        const tw = node._fallingtsTotalWidget;
        if (tw && savedTotal != null && savedTotal !== "" && Number(savedTotal) > 0) {
          tw.value = Math.min(MAX_FRAMES, Number(savedTotal));
        }
        // configure 是同步的, 渲染发生在 configure 完成后 ⇒ 一次成型, 不会先显示全部端口
        syncFrameState(node, node._fallingtsFrameList?.state ?? { frames: [] });
        fitHeight(node);
        // 后端是唯一事实来源: 从它读回截帧列表与视频预览并重建前端(刷新不丢)
        restoreFrames(node, node._fallingtsFrameList);
        restoreVideo(node);
      };
    };
  },
});
