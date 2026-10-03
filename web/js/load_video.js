/**
 * FallingTSLoadVideo 前端: 加载视频节点的「序列号 / 刷新 / 截帧 / 完成」。
 *
 * 本文件自 preview-video.js 的截帧部分迁移而来(预览视频节点此后只保留「保存」):
 * - 预览部分由节点原生 UI.PreviewVideo 负责(播放 temp 目录文件);
 * - 点「截帧」: 读节点预览 <video> 的当前播放时间(秒), POST 到
 *   /fallingts_load_video/frame/{id} —— 后端按 fps 折算帧号, 从 execute 时缓存的帧集合
 *   取该帧转 PNG 返回; 前端追加到选中帧列表并同步输出端口 image_1..N;
 * - 点「完成」: 无帧 = 预加载(全量提交); 有帧 = 置完成后以 partial_execution_targets
 *   只提交本节点下游的输出节点(与 PreviewVideo / 继续节点同套语义);
 * - 「序列号」自动取 output/<产物目录>/ 里已有编号的最大值 + 1(目录为空或不存在为 00000),
 *   可手动改; 右侧「刷新序列号」按钮随时重算;
 * - 刷新后从后端读回截帧列表与视频预览重建(后端是唯一事实来源)。
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { armComboRefresh } from "./load_combo_refresh.js";
import { armComboMenu } from "./load_combo_menu.js";

const NODE_CLASS = "FallingTSLoadVideo";
const MAX_FRAMES = 64;
const ROUTE = "/fallingts_load_video";
// 编号显示宽度: 与产物目录的 5 位编号口径一致(00000, 00001 …)
const SEQ_WIDTH = 5;

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

// ─── 按钮样式(DOM 渲染): 按文本匹配, 逐个套 element.style ──────────────────

/**
 * 给按钮套样式(高度/渐变/圆角), 并挂一次性的 hover 反馈。
 *
 * @param {HTMLElement} el 按钮元素
 * @param {string} from 渐变起色
 * @param {string} to 渐变止色
 * @param {string} hoverFrom hover 渐变起色
 * @param {string} hoverTo hover 渐变止色
 * @returns {void}
 */
function paintButton(el, from, to, hoverFrom, hoverTo) {
  el.style.height = "40px";
  el.style.minHeight = "40px";
  el.style.padding = "8px 12px";
  el.style.background = "linear-gradient(135deg," + from + "," + to + ")";
  el.style.color = "#fff";
  el.style.borderRadius = "8px";
  el.style.fontSize = "15px";
  el.style.fontWeight = "700";
  el.style.letterSpacing = "1px";
  el.style.border = "none";
  el.style.boxShadow = "0 2px 8px rgba(0,0,0,.35)";
  el.style.transition = "all .2s ease";
  if (el._fallingtsPainted) return;
  el._fallingtsPainted = true;
  const base = el.style.background;
  el.addEventListener("mouseenter", () => {
    el.style.background = "linear-gradient(135deg," + hoverFrom + "," + hoverTo + ")";
    el.style.transform = "translateY(-1px)";
  });
  el.addEventListener("mouseleave", () => {
    el.style.background = base;
    el.style.transform = "";
  });
}

const BTN_STYLES = {
  截帧: ["#0bb47d", "#17d9a0", "#0ecc90", "#22edb2"],
  完成: ["#e5484d", "#ff6b70", "#f05459", "#ff7a80"],
  刷新序列号: ["#3a6ea5", "#4f96d8", "#477fbb", "#5fa9e8"],
};

/**
 * 遍历页面按钮, 给本节点用到的三种按钮(截帧/完成/刷新序列号)套样式。
 *
 * @returns {void}
 */
function styleButtons() {
  document.querySelectorAll("button").forEach((el) => {
    const txt = (el.innerText || "").trim();
    const aria = (el.getAttribute("aria-label") || "").trim();
    const key = BTN_STYLES[txt] ? txt : BTN_STYLES[aria] ? aria : null;
    if (!key) return;
    const style = BTN_STYLES[key];
    paintButton(el, style[0], style[1], style[2], style[3]);
  });
}

if (!window.__fallingtsLoadVideoBtnInited) {
  window.__fallingtsLoadVideoBtnInited = true;
  const init = () => {
    styleButtons();
    new MutationObserver(styleButtons).observe(document.body, { childList: true, subtree: true });
  };
  if (document.body) init();
  else document.addEventListener("DOMContentLoaded", init);
}

// ─── 序列号 ────────────────────────────────────────────────────────────────

/**
 * 把整数编号格式化成 5 位文本(00000 / 00001 …)。
 *
 * @param {number|string} value 编号
 * @returns {string} 5 位文本
 */
function sequenceText(value) {
  const n = Math.max(0, Number(value) || 0);
  return String(Math.trunc(n)).padStart(SEQ_WIDTH, "0");
}

/**
 * 写入节点上的「序列号」控件(始终按 5 位显示)。
 *
 * @param {LGraphNode} node 节点
 * @param {number|string} value 编号
 * @returns {void}
 */
function setSequence(node, value) {
  const widget = node.widgets?.find((w) => w.name === "sequence");
  if (widget) widget.value = sequenceText(value);
}

/**
 * 从后端重算序列号并写入节点(供 prefix 文件名前缀使用)。
 *
 * @param {LGraphNode} node 节点
 * @param {boolean} notify 是否弹提示(手动点刷新时为真)
 * @returns {Promise<number>} 重算后的编号; 失败时返回 -1
 */
async function refreshSequence(node, notify) {
  try {
    const url = ROUTE + "/next_sequence?workflow_name=" + encodeURIComponent(currentWorkflowName());
    const r = await fetch(url);
    const j = await r.json().catch(() => null);
    if (!r.ok || j?.status !== "ok") {
      if (notify) app.extensionManager.toast.add({ severity: "error", summary: "刷新序列号失败", life: 3000 });
      return -1;
    }
    setSequence(node, j.sequence);
    if (notify) {
      app.extensionManager.toast.add({ severity: "info", summary: "序列号已刷新: " + sequenceText(j.sequence), life: 3000 });
    }
    return Number(j.sequence) || 0;
  } catch (err) {
    console.error("[FallingTS] 刷新序列号失败:", err);
    if (notify) app.extensionManager.toast.add({ severity: "error", summary: "刷新序列号失败: 无法连接后端", life: 3000 });
    return -1;
  }
}

// ─── 选中帧列表 DOM widget ─────────────────────────────────────────────────

/**
 * 创建「选中帧列表」DOM widget: 内嵌容器, 从上往下渲染截帧 <img>。
 * 列表不固定高度、不封顶、不滚动: 高度按帧数无限撑开(getMinHeight = 帧数×行高),
 * 节点高度随列表内容自然扩展。
 *
 * @param {LGraphNode} node 节点对象
 * @returns {object} {widget, state, render} —— addDOMWidget 创建的 widget、帧状态、列表重绘函数
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
    // 列表按内容无限撑开(不设 height, overflow visible): 先重建 DOM, 再 fitHeight 同步节点
    // 到精确高度 —— fitHeight 必须在 DOM 重建之后, 否则截帧后节点会按旧(更少)高度压缩。
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
      row.style.cssText = "display:flex;align-items:center;gap:8px;padding:4px;background:rgba(255,255,255,.04);border-radius:6px;";

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

      // 删除该帧
      const del = document.createElement("button");
      del.type = "button";
      del.textContent = "✕";
      del.style.cssText = "background:transparent;border:none;color:#f66;font-size:14px;cursor:pointer;padding:4px;";
      del.addEventListener("click", async () => {
        try {
          await fetch(ROUTE + "/frame-remove/" + node.id, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ frame_index: f.fno }),
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
 * total 规则(与 composite 同款): 最小 = max(1, 选中数);
 * 输出端口数 = 3(video + audio + prefix) + total 个 image。
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
  const target = 3 + total;
  const startIdx = 3; // 0=video, 1=audio, 2=prefix(文件名前缀) 三个固定端口
  // 只删"无链接"的尾部端口: 带链接的端口强删会让前端重建链接时报
  // "Cannot set properties of undefined"(与 route/fanout/composite 同款保护)。
  while ((node.outputs?.length ?? 0) > target) {
    const tail = node.outputs[node.outputs.length - 1];
    if (tail && (tail.links?.length ?? 0) > 0) break;
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < target) {
    node.addOutput("image_" + (node.outputs.length - startIdx + 1), "IMAGE");
  }
  // 端口 1/2 固定是 audio / prefix(后端 schema 的顺序); 老存档里这里可能是旧的 image_1/image_2,
  // 一并纠正(否则选中帧会被当成字符串端口, 且少一个前缀端口)
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
  for (let i = startIdx; i < (node.outputs?.length ?? 0); i++) {
    const fno = state.frames[i - startIdx]?.fno ?? (i - startIdx + 1);
    node.outputs[i].name = "image_" + (i - startIdx + 1);
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

// ─── 预览: 备用播放器 + 刷新后重建 ─────────────────────────────────────────

/**
 * 创建备用 <video> widget(仅在原生视频预览缺失时显示)。
 *
 * 原生 UI.PreviewVideo 是一次性 WebSocket 事件, 页面刷新后不会重发;
 * 备用播放器由 restoreVideo() 从后端拉 URL 填上。
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
 * ① URL 一律转成**绝对**地址 —— 原生 VideoPreview 组件的文件名标签用 new URL(e) 解析,
 *    相对路径会让它抛错、标签显示成 "Invalid URL";
 * ② 原生播放器只在"指向的文件不是本次这个"时才改写 src。
 * ⚠️ 不要往 app.nodePreviewImages[nodeId] 里写地址: getNodeImageUrls 会优先读它, 写进去
 *    后前端后续渲染一直用这个快照值, 预览反而停在旧文件上。
 *
 * @param {LGraphNode} node 节点
 * @returns {Promise<void>} 无
 */
async function restoreVideo(node) {
  const fb = node._fallingtsVideoFallback;
  let url = null;
  try {
    const r = await fetch(ROUTE + "/preview-url/" + node.id);
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
    // 后端换了文件(懒解码重编码 / 重跑)或这个元素上一次就加载失败(旧 temp 已被清理 ⇒ 404)
    // 时重新指向; 否则保持 src 不动 —— 改写 src 会把用户正在播放的位置归零, 下一帧就截错地方
    if (curName !== newName || nativeVid.dataset.src !== absUrl || nativeVid.error) {
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
 * 从后端读回截帧状态并重建前端帧列表(页面刷新/工作流重载后恢复上一次的截帧结果)。
 *
 * 后端是唯一事实来源: GET /state 拿帧号, 再对每个帧号 POST /frame(append=false) 取回 PNG。
 *
 * @param {LGraphNode} node 节点
 * @param {object} frameList 帧列表 DOM widget
 * @returns {Promise<void>} 无
 */
async function restoreFrames(node, frameList) {
  if (!frameList) return;
  try {
    const r = await fetch(ROUTE + "/state/" + node.id);
    const st = await r.json().catch(() => null);
    if (!r.ok || st?.status !== "ok") return;
    const fnos = st.selected_frames || [];
    if (!fnos.length) return;

    const frames = [];
    for (const fno of fnos) {
      const resp = await fetch(ROUTE + "/frame/" + node.id, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "frame", frame_index: fno, append: false, ...nodePayload(node) }),
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
 * 取节点上「视频 / 名称 / 序列号」三个值, 随截帧请求一起发给后端。
 *
 * 后端在帧缓存为空时(重启 ComfyUI / 还没跑过本节点)靠这里的 video 现场拆帧 ——
 * 用户既然能在节点里播放视频, 就不该被「请先运行到该节点」挡住。
 *
 * @param {LGraphNode} node 节点
 * @returns {object} {video, name, sequence}
 */
function nodePayload(node) {
  const read = (name) => node.widgets?.find((w) => w.name === name)?.value ?? "";
  return { video: read("video"), name: read("name"), sequence: read("sequence") };
}

app.registerExtension({
  name: "FallingTS.LoadVideo",

  /**
   * 扩展初始化钩子。
   *
   * ① 包装全局提交入口 app.queuePrompt: 默认 Run 时先 POST reset 重置所有加载视频节点为
   *    未完成(重新拉视频填缓存), 再按原逻辑全量提交; partial 提交保留已放行状态。
   * ② 监听执行事件, 让视频预览在跑完后重新判定一次(原生 <video> 由 Vue 异步挂载, 比
   *    onConfigure 晚), 按 600ms / 2.5s 两拍各调一次 restoreVideo。
   *
   * @returns {Promise<void>} 无
   */
  async setup() {
    const orig = app.queuePrompt?.bind(app);
    if (orig) {
      app.queuePrompt = async function (number, batch, queueNodeIds) {
        if (!queueNodeIds?.length) {
          try {
            await fetch(ROUTE + "/reset", { method: "POST" });
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
    api.addEventListener("executed", refresh);
    api.addEventListener("progress", refresh);
  },

  /**
   * 节点定义注册前钩子: 给加载视频节点追加序列号刷新 + 截帧/完成 + 选中帧列表。
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

      // ── 下拉候选: 点开/点节点即自动刷新(见 load_combo_refresh.js) ──
      armComboRefresh(node, "video");

      // ── 下拉弹窗: 抹掉 " [output]" 标注 + 「排序方式」左侧的刷新按钮(见 load_combo_menu.js) ──
      armComboMenu(node, "video");

      // ── 序列号刷新按钮: 插到「序列号」控件之后(视频下拉的刷新按钮由 remote 组件追加) ──
      const seqWidget = node.widgets?.find((w) => w.name === "sequence");
      const refreshBtn = node.addWidget("button", "刷新序列号", null, async () => {
        await refreshSequence(node, true);
      });
      if (seqWidget && refreshBtn) {
        const at = node.widgets.indexOf(refreshBtn);
        node.widgets.splice(at, 1);
        node.widgets.splice(node.widgets.indexOf(seqWidget) + 1, 0, refreshBtn);
      }

      // ── 截帧按钮 → 输出帧数 → 选中帧列表(列表必须在按钮下方) ──
      node.addWidget("button", "截帧", null, async () => {
        const positionSeconds = currentPlaybackSeconds(node);
        try {
          const resp = await fetch(ROUTE + "/frame/" + node.id, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ position_seconds: positionSeconds, ...nodePayload(node) }),
          });
          if (!resp.ok) {
            const data = await resp.json().catch(() => null);
            app.extensionManager.toast.add({ severity: "error", summary: data?.message ?? "截帧失败", life: 3000 });
            return;
          }
          const fno = Number(resp.headers.get("X-Frame-Index") || frameList.state.frames.length + 1);
          const blob = await resp.blob();
          const url = URL.createObjectURL(blob);

          if (frameList.state.frames.length >= MAX_FRAMES) {
            app.extensionManager.toast.add({ severity: "warn", summary: "已达截帧上限 " + MAX_FRAMES + " 张", life: 3000 });
            URL.revokeObjectURL(url);
            return;
          }

          frameList.state.frames.push({ url, fno });
          // 先对齐输出端口/total, 再重绘列表(render 内按新盒高同步节点高度)
          syncFrameState(node, frameList.state);
          frameList.render();
          // 节点上还没有播放器时(刷新后 / 上传前), 用后端刚建好的 temp 预览补一个;
          // 已有播放器则不动 —— 改写 src 会让用户正在播放的位置归零, 下一帧就截错地方
          const host = document.querySelector('[data-node-id="' + node.id + '"]');
          const players = [
            node._fallingtsVideoFallback?.videoEl,
            ...(host ? host.querySelectorAll("video") : []),
          ].filter((v) => v && v.src);
          // 没有播放器、或可见的那个已经加载失败(指向被清理的 temp ⇒ 页面上「视频加载失败」
          // / Invalid URL)时, 用后端刚重建好的预览补上; 正在正常播放的播放器不动
          const visible = players.filter((v) => (v.getClientRects?.().length ?? 0) > 0);
          const pool = visible.length ? visible : players;
          const broken = (v) => !v.getAttribute("src") || !!v.error || v.networkState === 3;
          if (!players.length || pool.some(broken)) restoreVideo(node);
        } catch (err) {
          console.error("[FallingTS] 截帧失败:", err);
          app.extensionManager.toast.add({ severity: "error", summary: "截帧失败: 无法连接后端", life: 3000 });
        }
      });

      // ── 完成: 无帧 = 预加载; 有帧 = 置完成后 partial 只跑下游 ──
      node.addWidget("button", "完成", null, async () => {
        const frames = node._fallingtsFrameList?.state?.frames ?? [];
        try {
          if (frames.length === 0) {
            try {
              await fetch(ROUTE + "/reset", { method: "POST" });
            } catch {
              /* 忽略 */
            }
            await app.queuePrompt(0, 1);
            app.extensionManager.toast.add({ severity: "info", summary: "已开始加载视频, 播放后可截帧", life: 3000 });
            return;
          }
          const fnos = frames.map((f) => f.fno).filter((v) => Number.isFinite(v));
          const resp = await fetch(ROUTE + "/done/" + node.id, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ frames: fnos }),
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
          try {
            await fetch("/free", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ unload_models: true, free_memory: true }),
            });
          } catch {
            /* 忽略 */
          }
          const targets = collectOutputsAfter(node);
          if (!targets.length) {
            console.warn("[FallingTS] 加载视频节点之后没有输出节点");
            return;
          }
          await submitPartial(node, targets);
          app.extensionManager.toast.add({ severity: "success", summary: "已完成, 截帧输出到下游", life: 3000 });
        } catch (err) {
          console.error("[FallingTS] 完成失败:", err);
          app.extensionManager.toast.add({ severity: "error", summary: "完成失败: 无法连接后端", life: 3000 });
        }
      });

      // ── 输出帧数: 输出 image 端口数量(默认 1, 最小 = max(1, 选中帧数), 上限 MAX_FRAMES) ──
      const totalWidget = node.addWidget("number", "输出帧数", 1, () => {
        syncFrameState(node, node._fallingtsFrameList?.state ?? { frames: [] });
      }, { min: 1, max: MAX_FRAMES, step: 1, precision: 0 });
      totalWidget.options.min = 1;
      totalWidget.options.max = MAX_FRAMES;
      node._fallingtsTotalWidget = totalWidget;

      const frameList = createFrameListWidget(node);
      node._fallingtsFrameList = frameList;

      // 备用视频播放器: 页面刷新后原生 UI.PreviewVideo 不重发, 由 restoreVideo 补上
      node._fallingtsVideoFallback = createVideoFallbackWidget(node);

      // 新拖入的节点: 直接裁到 3(video+audio+prefix)+total 个 image
      if ((node.outputs ?? []).length > 0) syncFrameState(node, { frames: [] });
      fitHeight(node);

      // 新节点自动取一次序列号(打开工作流时保留存档值, 由 onConfigure 决定)
      refreshSequence(node, false);

      const prevOnConfigure = node.onConfigure;
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        if (!node._fallingtsFrameList) return;
        // 存档值优先: 工作流里存过序列号就沿用(用户可能手动改过), 只有空值才自动取
        const stored = info?.widgets_values_named?.sequence;
        if (stored == null || String(stored).trim() === "") {
          refreshSequence(node, false);
        } else {
          setSequence(node, stored);
        }
        // 老存档兼容: 「保存帧」按钮已删除, 但旧工作流的 widgets_values 还占着一格, 会让其后的
        // 输出帧数/frame_list/video_fallback 按位错位 —— 这里把输出帧数修正回来(frame_list /
        // video_fallback 稍后由 restoreFrames / restoreVideo 以后端为准重建)。
        const _wv = info?.widgets_values;
        const _named = info?.widgets_values_named;
        const _legacy = _named
          ? Object.prototype.hasOwnProperty.call(_named, "保存帧")
          : Array.isArray(_wv) && _wv.length === 13;
        if (_legacy) {
          const savedTotal = _named?.["输出帧数"] ?? (Array.isArray(_wv) ? _wv[10] : undefined);
          const tw = node._fallingtsTotalWidget;
          if (tw && savedTotal != null && savedTotal !== "") tw.value = Number(savedTotal) || tw.value;
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
