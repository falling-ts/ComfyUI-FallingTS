/**
 * audio-trim.js — FallingTSAudioTrim 前端增强(截段版)。
 *
 * 与 PreviewVideo 同套机制, 只是 画面帧 -> 音频时间段:
 * 1. 「保存」按钮: 把 文件名/格式/质量 POST 到 /audio-trim/save/{id},
 *    后端用 execute 时缓存的音频直接写 output, 不重跑工作流;
 * 2. 波形截段: 节点内画波形, 两侧把手可拖动确定起始与长度;
 *    点「截段」把 {start, duration} POST 到 /audio-trim/segment/{id} 累积;
 *    段列表每项可单独删除;
 * 3. 「输出段数」参数: 输出 audio 端口数量(默认 1, 最小 = max(1, 选中段数), 上限 MAX_SEGMENTS)。
 *    端口按 total 动态对齐 —— 界面上只有 1(audio) + total 个端口, 不是全部 64 个;
 * 4. 「完成」按钮: 有段 → POST /audio-trim/done/{id} + 释放生成模型内存 +
 *    collectOutputsAfter 收集下游输出节点 → queuePrompt(0,1,targets) 只跑下游;
 *    无段 → reset + 全量提交(先生成音频)。
 *
 * 输出端口与后端定长槽(MAX_SEGMENTS=64)配合: 后端始终定义 64 个槽, 前端按 total 裁剪显示。
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_CLASS = "FallingTSAudioTrim";
const MAX_SEGMENTS = 64;
const WAVE_H = 96;
const HIT = 8;

/**
 * 统一的提示条输出。
 *
 * @param {"success"|"error"|"info"|"warn"|"warning"} severity 级别
 * @param {string} summary 文本
 * @returns {void}
 */
function toast(severity, summary) {
  app.extensionManager?.toast?.add({ severity, summary });
}

/**
 * 秒格式化为两位小数。
 *
 * @param {number} v 秒
 * @returns {string} 形如 "1.25"
 */
function fmt(v) {
  return Number(v || 0).toFixed(2);
}

/**
 * canvas 圆角矩形路径(老浏览器无 ctx.roundRect 时用手绘)。
 *
 * @param {CanvasRenderingContext2D} ctx 上下文
 * @param {number} x 左上 x
 * @param {number} y 左上 y
 * @param {number} w 宽
 * @param {number} h 高
 * @param {number} r 圆角半径
 * @returns {void}
 */
function roundRectPath(ctx, x, y, w, h, r) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

/**
 * 标记节点与画布为脏(触发重绘)。
 *
 * @param {LGraphNode} node 节点
 * @returns {void}
 */
function emitDirty(node) {
  node.setDirtyCanvas?.(true, true);
  node.graph?.setDirtyCanvas?.(true, true);
}

/**
 * 给 DOM 版「截段」按钮套青绿渐变样式(与 PreviewVideo 的「截帧」同款配色)。
 *
 * Nodes 2.0 把 button widget 渲染成 DOM <button>; PreviewVideo 的全局样式器只按
 * 「保存/截帧/完成」三个文本匹配, 本节点的「截段」不在其中, 故在此自行套用。
 *
 * @param {HTMLElement} el 按钮元素
 * @returns {void}
 */
function applySegmentBtnStyle(el) {
  el.style.height = "40px";
  el.style.minHeight = "40px";
  el.style.padding = "8px 12px";
  el.style.background = "linear-gradient(135deg,#0bb47d,#17d9a0)";
  el.style.color = "#fff";
  el.style.borderRadius = "8px";
  el.style.fontSize = "15px";
  el.style.fontWeight = "700";
  el.style.letterSpacing = "1px";
  el.style.boxShadow = "0 2px 8px rgba(11,180,125,.35)";
  el.style.transition = "all .2s ease";
  el.style.border = "none";
  if (!el._fallingtsSegmentStyled) {
    el._fallingtsSegmentStyled = true;
    el.addEventListener("mouseenter", () => {
      el.style.background = "linear-gradient(135deg,#0ecc90,#22edb2)";
      el.style.boxShadow = "0 4px 14px rgba(11,180,125,.5)";
      el.style.transform = "translateY(-1px)";
    });
    el.addEventListener("mouseleave", () => {
      el.style.background = "linear-gradient(135deg,#0bb47d,#17d9a0)";
      el.style.boxShadow = "0 2px 8px rgba(11,180,125,.35)";
      el.style.transform = "";
    });
  }
}

/**
 * 判断是否为「截段」按钮(按文本或 aria-label)。
 *
 * @param {HTMLElement} el 元素
 * @returns {boolean} 是否截段按钮
 */
function isSegmentBtn(el) {
  if (!el || el.tagName !== "BUTTON") return false;
  const txt = (el.innerText || "").trim();
  const aria = (el.getAttribute("aria-label") || "").trim();
  return txt === "截段" || aria === "截段";
}

/**
 * 遍历页面按钮, 给「截段」按钮套样式。
 *
 * @returns {void}
 */
function styleSegmentButtons() {
  document.querySelectorAll("button").forEach((el) => {
    if (isSegmentBtn(el)) applySegmentBtnStyle(el);
  });
}

/**
 * 判断节点是否为「输出节点」(保存/预览等终端节点)。
 *
 * @param {LGraphNode} node 画布节点
 * @returns {boolean} nodeData.output_node 为 true 时 true
 */
function isOutputNode(node) {
  return node?.constructor?.nodeData?.output_node === true;
}

/**
 * 从 startNode 下游 BFS 收集所有输出节点, 作为 partial_execution_targets 传给 /prompt。
 *
 * 完成截段后只执行本段子图(预览节点 -> 下游保存/合成), 上游(模型/采样)因 audio 输入
 * lazy 门控被跳过 —— 运行时看不到预览节点之前的部分。
 *
 * @param {LGraphNode} startNode 锚点节点
 * @returns {string[]} 输出节点 ID 字符串数组(去重)
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
 * 给 canvas 版「截段」按钮 widget 套样式: 覆写 draw 绘制青绿渐变圆角按钮。
 *
 * Nodes 2.0 以 DOM <button> 渲染为主, 这里是旧渲染模式(canvas)的兜底,
 * 与 PreviewVideo 的 styleFrameButton 同构。
 *
 * @param {LGraphNode} node 节点
 * @returns {void}
 */
function styleSegmentButton(node) {
  const btn = node.widgets?.find((w) => w.type === "button" && w.name === "截段");
  if (!btn) return;

  btn.computedHeight = 56;
  const origMouse = btn.mouse;

  /**
   * 自定义绘制: 阴影层 + 青绿渐变圆角主体 + 白字「截段」; _pressed 时下压。
   *
   * @param {CanvasRenderingContext2D} ctx 上下文
   * @param {LGraphNode} _n 节点(未用)
   * @param {number} widget_width 控件宽
   * @param {number} y 顶边 y
   * @returns {void}
   */
  btn.draw = function (ctx, _n, widget_width, y) {
    const W = widget_width;
    const dy = this._pressed ? 1 : 0;
    const BH = 52;
    roundRectPath(ctx, 6, y + 6, W - 12, BH - 8, 10);
    ctx.fillStyle = "rgba(0,0,0,.22)";
    ctx.fill();
    roundRectPath(ctx, 6, y + 3 + dy, W - 12, BH - 8, 10);
    const g = ctx.createLinearGradient(0, y, 0, y + BH);
    g.addColorStop(0, this._pressed ? "#0c9e6a" : "#0bb47d");
    g.addColorStop(1, this._pressed ? "#12c98c" : "#17d9a0");
    ctx.fillStyle = g;
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,.2)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = "#ffffff";
    ctx.font = "700 16px 'Segoe UI','Microsoft YaHei',sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("截段", W / 2, y + BH / 2 + 1 + dy);
  };

  /**
   * 鼠标事件: 记录按下状态(下压反馈), 其余交给原 mouse 触发点击回调。
   *
   * @param {Event} event 事件
   * @param {Array} pos 节点局部坐标
   * @param {LGraphNode} n2 节点
   * @returns {*} 原 mouse 返回值
   */
  btn.mouse = function (event, pos, n2) {
    const inBtn =
      this.last_y != null && pos[1] >= this.last_y && pos[1] <= this.last_y + (this.computedHeight || 20);
    if (event.type === "mousedown") this._pressed = true;
    if (event.type === "mouseup" || (event.type === "mousedown" && !inBtn)) this._pressed = false;
    return origMouse ? origMouse.call(this, event, pos, n2) : false;
  };

  node.setDirtyCanvas(true, true);
}

/**
 * 只提交「本节点下游」的部分执行(partial execution)。
 *
 * 注意不能写成 app.queuePrompt(0, 1, targets): ComfyUI 的 api.queuePrompt 第 3 参数
 * 是选项对象 {partialExecutionTargets}(驼峰), 传裸数组会被 `?.partialExecutionTargets`
 * 静默取成 undefined, 于是退化成全量提交(上游采样白跑一遍)。
 * 这里直接用 graphToPrompt 的结果 POST /prompt, 显式带 partial_execution_targets,
 * 不依赖上层包装的签名。
 *
 * @param {LGraphNode} node 锚点节点(截段节点自身)
 * @param {string[]} targets 下游输出节点 id 列表
 * @returns {Promise<object>} 后端响应
 */
async function submitPartial(node, targets) {
  const prompt = await app.graphToPrompt();
  // 只保留 targets 及其依赖: 否则同一个图里别的输出节点(例如 PreviewVideo)也会被执行一遍,
  // 把上游采样重新拉起来 —— 与「点完成只跑下游」的意图正好相反。
  const keep = new Set();
  const walk = (id) => {
    if (keep.has(id)) return;
    keep.add(id);
    for (const v of Object.values(prompt.output[id]?.inputs || {})) {
      if (Array.isArray(v) && typeof v[0] === "string") walk(v[0]);
    }
  };
  for (const t of targets) walk(t);
  const pruned = {};
  for (const id of keep) {
    if (prompt.output[id]) pruned[id] = prompt.output[id];
  }
  const resp = await api.fetchApi("/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: api.clientId,
      prompt: pruned,
      partial_execution_targets: targets,
      extra_data: { extra_pnginfo: { workflow: prompt.workflow } },
    }),
  });
  if (!resp.ok) {
    const t = await resp.text().catch(() => "");
    throw new Error(`提交失败 HTTP ${resp.status} ${t.slice(0, 200)}`);
  }
  return resp.json();
}

/**
 * 创建段列表 DOM widget: 每行显示 序号/起止/时长 + 删除按钮。
 *
 * @param {LGraphNode} node 节点
 * @returns {object} widget 对象(带 render/state)
 */
function createSegmentListWidget(node) {
  const state = { segments: [] };
  const root = document.createElement("div");
  root.style.cssText =
    "display:flex;flex-direction:column;gap:2px;padding:4px 6px;box-sizing:border-box;" +
    "font:12px 'Segoe UI','Microsoft YaHei',sans-serif;color:#e8e8e8;overflow:hidden;";

  /**
   * 重绘列表(段为空时显示占位提示)。
   *
   * @returns {void}
   */
  const render = () => {
    root.innerHTML = "";
    if (!state.segments.length) {
      const empty = document.createElement("div");
      empty.textContent = "在波形上拖动选择区间, 点「截段」加入";
      empty.style.cssText = "opacity:.55;padding:3px 2px;";
      root.appendChild(empty);
      return;
    }
    state.segments.forEach((seg, i) => {
      const row = document.createElement("div");
      row.style.cssText =
        "display:flex;align-items:center;gap:6px;padding:2px 4px;border-radius:4px;background:rgba(255,255,255,.06);";
      const label = document.createElement("span");
      label.textContent = `#${i + 1}  ${fmt(seg.start)}s → ${fmt(seg.start + seg.duration)}s  (${fmt(seg.duration)}s)`;
      label.style.cssText = "flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
      const del = document.createElement("button");
      del.textContent = "×";
      del.title = "删除该段";
      del.style.cssText =
        "width:18px;height:18px;line-height:16px;border-radius:4px;border:1px solid rgba(255,255,255,.25);" +
        "background:rgba(200,60,60,.75);color:#fff;cursor:pointer;font-size:12px;padding:0;";
      del.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          const resp = await fetch(`/audio-trim/segment-remove/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index: i + 1 }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            toast("error", data?.message ?? "删除失败");
            return;
          }
          state.segments.splice(i, 1);
          render();
          syncSegmentState(node, state);
        } catch (err) {
          console.error("[FallingTS] 删除截段失败:", err);
          toast("error", "删除失败: 无法连接后端");
        }
      });
      row.appendChild(label);
      row.appendChild(del);
      root.appendChild(row);
    });
  };

  const widget = node.addDOMWidget("segment_list", "segments", root, {
    serialize: false,
    hideOnZoom: false,
    getValue: () => "",
    setValue: () => {},
  });
  widget.state = state;
  widget.render = render;
  /**
   * 列表所需高度。
   *
   * @param {number} width 可用宽
   * @returns {[number, number]} [宽, 高]
   */
  widget.computeSize = (width) => [width, Math.max(24, state.segments.length * 24 + 10)];
  widget.element = root;
  return widget;
}

/**
 * 创建波形 widget: 画波形 + 选区 + 两侧把手, 支持拖动改起始/长度。
 *
 * 交互:
 * - 拖左侧把手 → 改 start(不越过右侧);
 * - 拖右侧把手 → 改 end(不越过左侧);
 * - 在选区内拖动 → 整体平移选区;
 * - 在选区外按下 → 以该点为锚点重新拉一个选区。
 *
 * @param {LGraphNode} node 节点
 * @returns {object} widget 对象
 */
function createWaveformWidget(node) {
  const state = { peaks: [], duration: 0, start: 0, end: 0, dragging: null, dragOffset: 0, loaded: false };

  // Nodes 2.0 下 canvas 自定义 widget 的 draw 不生效(与 PreviewVideo 的按钮同理),
  // 所以这里用 addDOMWidget 挂一个真实的 <canvas> 元素来画。
  const root = document.createElement("div");
  root.style.cssText = "width:100%;box-sizing:border-box;padding:0 4px;";

  const canvas = document.createElement("canvas");
  canvas.style.cssText =
    `display:block;width:100%;height:${WAVE_H}px;border-radius:6px;` +
    "background:#1b1e24;border:1px solid rgba(255,255,255,.12);cursor:crosshair;";
  root.appendChild(canvas);

  // 节点自带的 DOM widget 占满了内容区, ComfyUI 的 PreviewAudio 播放器渲染不出来,
  // 所以这里自备一个 <audio>, 源自后端 /audio-trim/audio-url/{id}。
  const audioEl = document.createElement("audio");
  audioEl.controls = true;
  audioEl.preload = "none";
  audioEl.style.cssText = "display:block;width:100%;height:32px;margin-top:4px;";
  root.appendChild(audioEl);
  const ctx = canvas.getContext("2d");

  /** 画布可用宽度(CSS 像素)。 */
  const boxW = () => Math.max(1, canvas.clientWidth || 300);

  /**
   * 画布 x → 秒。
   *
   * @param {number} x 画布 x
   * @returns {number} 秒
   */
  const xToSec = (x) => {
    const w = boxW();
    const usable = Math.max(1, w - 2 * HIT);
    const t = (x - HIT) / usable;
    return Math.max(0, Math.min(1, t)) * (state.duration || 0);
  };

  /**
   * 秒 → 画布 x。
   *
   * @param {number} sec 秒
   * @returns {number} 画布 x
   */
  const secToX = (sec) => {
    const w = boxW();
    const usable = Math.max(1, w - 2 * HIT);
    const t = state.duration > 0 ? sec / state.duration : 0;
    return HIT + Math.max(0, Math.min(1, t)) * usable;
  };

  /** 重绘画布(波形 + 选区 + 两侧把手)。 */
  const redraw = () => {
    const w = boxW();
    const H = WAVE_H;
    ctx.clearRect(0, 0, w, H);
    ctx.fillStyle = "#1b1e24";
    ctx.fillRect(0, 0, w, H);

    if (!state.loaded || !state.peaks.length) {
      ctx.fillStyle = "rgba(255,255,255,.4)";
      ctx.font = "12px 'Segoe UI','Microsoft YaHei',sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("运行到本节点后显示波形(点「完成」先生成)", w / 2, H / 2);
      return;
    }

    const midY = H / 2;
    const halfH = H / 2 - 10;

    if (state.end > state.start) {
      const x1 = secToX(state.start);
      const x2 = secToX(state.end);
      ctx.fillStyle = "rgba(90,170,255,.22)";
      ctx.fillRect(x1, 2, Math.max(1, x2 - x1), H - 4);
    }

    ctx.strokeStyle = "rgba(150,210,255,.85)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    const cnt = state.peaks.length;
    for (let i = 0; i < cnt; i++) {
      const x = HIT + (i / Math.max(1, cnt - 1)) * Math.max(1, w - 2 * HIT);
      const a = Math.min(1, Math.abs(state.peaks[i] || 0)) * halfH;
      ctx.moveTo(x, midY - a);
      ctx.lineTo(x, midY + a);
    }
    ctx.stroke();

    ctx.strokeStyle = "rgba(255,255,255,.15)";
    ctx.beginPath();
    ctx.moveTo(HIT, midY);
    ctx.lineTo(w - HIT, midY);
    ctx.stroke();

    if (state.end > state.start) {
      for (const [sec, color] of [
        [state.start, "#5aaaff"],
        [state.end, "#ffb454"],
      ]) {
        const x = secToX(sec);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, 2);
        ctx.lineTo(x, H - 2);
        ctx.stroke();
        ctx.fillStyle = color;
        roundRectPath(ctx, x - 4, midY - 9, 8, 18, 3);
        ctx.fill();
      }
    }
  };

  /** 按设备像素比调整画布分辨率后重绘。 */
  const fit = () => {
    const dpr = window.devicePixelRatio || 1;
    const w = boxW();
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(WAVE_H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    redraw();
  };

  // 鼠标交互: 拖把手改起止 / 拖选区内平移 / 选区外重新拉选
  canvas.addEventListener("mousedown", (e) => {
    if (!state.loaded || state.duration <= 0) return;
    const x = e.offsetX;
    const xs = secToX(state.start);
    const xe = secToX(state.end);
    const has = state.end > state.start;
    if (has && Math.abs(x - xs) <= HIT) state.dragging = "start";
    else if (has && Math.abs(x - xe) <= HIT) state.dragging = "end";
    else if (has && x > xs && x < xe) {
      state.dragging = "range";
      state.dragOffset = xToSec(x) - state.start;
    } else {
      state.dragging = "end";
      state.start = xToSec(x);
      state.end = state.start;
    }
    canvas.style.cursor = state.dragging === "range" ? "grabbing" : "ew-resize";
    redraw();
    e.preventDefault();
  });

  canvas.addEventListener("mousemove", (e) => {
    if (!state.loaded || state.duration <= 0) return;
    const x = e.offsetX;
    if (!state.dragging) {
      const xs = secToX(state.start);
      const xe = secToX(state.end);
      const has = state.end > state.start;
      canvas.style.cursor = has && (Math.abs(x - xs) <= HIT || Math.abs(x - xe) <= HIT) ? "ew-resize" : "crosshair";
      return;
    }
    const sec = xToSec(x);
    if (state.dragging === "start") {
      state.start = Math.min(sec, state.end);
    } else if (state.dragging === "end") {
      state.end = Math.max(sec, state.start);
    } else if (state.dragging === "range") {
      const len = state.end - state.start;
      const s = Math.max(0, Math.min(state.duration - len, sec - state.dragOffset));
      state.start = s;
      state.end = s + len;
    }
    redraw();
  });

  const endDrag = () => {
    if (!state.dragging) return;
    state.dragging = null;
    canvas.style.cursor = "crosshair";
    redraw();
  };
  canvas.addEventListener("mouseup", endDrag);
  canvas.addEventListener("mouseleave", endDrag);

  // 节点宽度变化时重排画布
  const ro = new ResizeObserver(() => fit());
  ro.observe(canvas);
  window.addEventListener("resize", fit);

  const widget = node.addDOMWidget("waveform", "waveform", root, {
    serialize: false,
    hideOnZoom: false,
    getValue: () => "",
    setValue: () => {},
  });
  widget.computeSize = (width) => [width, WAVE_H + 8 + 36];
  widget.state = state;
  widget.redraw = redraw;
  widget.fit = fit;
  widget.canvas = canvas;
  widget.audioEl = audioEl;
  /**
   * 设置播放源(后端 temp 文件的 /view URL); 同源不重复设置以免打断播放。
   *
   * @param {string} url 可播放 URL
   * @returns {void}
   */
  widget.setAudioUrl = (url) => {
    if (!url || audioEl.dataset.src === url) return;
    audioEl.dataset.src = url;
    audioEl.src = url;
    audioEl.load();
  };
  widget.element = root;
  requestAnimationFrame(fit);
  return widget;
}

/**
 * 同步截段状态: 更新 total 下限 + 按 total 对齐输出端口数量。
 *
 * total 规则(与 PreviewVideo/composite 同款):
 * - total 最小 = max(1, 选中段数): 截段后选中数 > total 时自动抬高 total;
 * - 输出端口数 = 1(audio) + total 个 audio_N, 而非按选中段数;
 * - 选中数变为 0 时 total 最小回到 1(不得为 0)。
 *
 * @param {LGraphNode} node 节点
 * @param {object} state 段状态 {segments: [...]}
 * @returns {void}
 */
function syncSegmentState(node, state) {
  // 1) total 下限随选中段数
  const totalWidget = node._fallingtsTotalWidget;
  const selectedCount = state?.segments?.length ?? 0;
  const minTotal = Math.max(1, selectedCount);
  if (totalWidget?.options) {
    totalWidget.options.min = minTotal;
    const cur = Number(totalWidget.value) || 1;
    if (cur < minTotal) {
      totalWidget.value = minTotal;
      totalWidget.callback?.(minTotal);
    }
  }

  // 2) 输出端口: [0]=audio, [1..]=audio_1..N; 数量 = 1 + total
  const total = Math.max(1, Number(totalWidget?.value) || 1);
  const target = 1 + total;
  const startIdx = 1;
  // 只删"无链接"的尾部端口: 加载工作流时尾部端口可能带着已有链接,
  // 强删会让前端链接重建时对已删端口写 .link 而报错。
  while ((node.outputs?.length ?? 0) > target) {
    const tail = node.outputs[node.outputs.length - 1];
    if (tail && (tail.links?.length ?? 0) > 0) break;
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < target) {
    node.addOutput("audio_" + (node.outputs.length - startIdx + 1), "AUDIO");
  }
  for (let i = startIdx; i < (node.outputs?.length ?? 0); i++) {
    node.outputs[i].name = `audio_${i}`;
    node.outputs[i].label = `截段 ${i}`;
  }
  emitDirty(node);
}

/**
 * 从后端拉波形峰值与已有段列表, 刷新波形 widget 与段列表。
 *
 * @param {LGraphNode} node 节点
 * @param {object} waveWidget 波形 widget
 * @param {object} listWidget 段列表 widget
 * @returns {Promise<void>} 拉取流程
 */
async function refreshWaveform(node, waveWidget, listWidget) {
  try {
    const resp = await fetch(`/audio-trim/waveform/${node.id}`);
    const data = await resp.json().catch(() => null);
    if (!resp.ok || !data || data.status !== "ok") return;
    waveWidget.state.peaks = data.peaks || [];
    waveWidget.state.duration = Number(data.duration || 0);
    waveWidget.state.loaded = true;
    if (Array.isArray(data.segments) && data.segments.length) {
      listWidget.state.segments = data.segments.map((s) => ({
        start: Number(s.start || 0),
        duration: Number(s.duration || 0),
      }));
    }
    if (waveWidget.state.end <= waveWidget.state.start) {
      waveWidget.state.start = 0;
      waveWidget.state.end = waveWidget.state.duration;
    }
    listWidget.render();
    syncSegmentState(node, listWidget.state);
    waveWidget.redraw?.();   // DOM 版波形: 直接重绘画布(不依赖 canvas 自定义 widget 的 draw)
    // 顺带取可播放 URL(节点自备 <audio> 用)
    try {
      const ar = await fetch(`/audio-trim/audio-url/${node.id}`);
      const aj = await ar.json().catch(() => null);
      if (ar.ok && aj?.status === "ok") waveWidget.setAudioUrl?.(aj.url);
    } catch {
      /* 播放源失败不影响波形显示 */
    }
  } catch (err) {
    console.warn("[FallingTS] 拉取波形失败:", err);
  }
}

/**
 * 从节点上找波形 / 段列表 widget(不依赖私有字段, 因为它们可能在 onConfigure 后被重建)。
 *
 * @param {LGraphNode} node 节点
 * @returns {{wave: object|undefined, list: object|undefined}} 两个 widget
 */
function findAudioWidgets(node) {
  const widgets = node.widgets || [];
  return {
    wave: widgets.find((w) => w.name === "waveform"),
    list: widgets.find((w) => w.name === "segment_list"),
  };
}

/**
 * 对图上所有 FallingTSAudioTrim 节点刷新波形(带防抖, 同一节点 800ms 内不重复拉)。
 *
 * @returns {void}
 */
const _refreshTimers = new Map();
function refreshAllAudioNodes() {
  for (const node of app.graph?._nodes || []) {
    if (node.type !== NODE_CLASS) continue;
    const prev = _refreshTimers.get(node.id);
    if (prev) clearTimeout(prev);
    _refreshTimers.set(
      node.id,
      setTimeout(() => {
        _refreshTimers.delete(node.id);
        const { wave, list } = findAudioWidgets(node);
        if (wave && list) refreshWaveform(node, wave, list);
      }, 300),
    );
  }
}

app.registerExtension({
  name: "FallingTS.AudioTrim",

  /**
   * 扩展初始化钩子: ① 页面加载时 POST /audio-trim/clear 同步清空后端段状态
   * (前端刷新后列表本就回空, 清的是进程内存, 避免下次截段追加到旧段后面);
   * ② 包装全局 app.queuePrompt: 默认 Run(未指定目标节点)时先 POST reset 把预览节点
   * 全部置回未完成, 再按原逻辑全量提交 —— 保证每次 Run 都从开头执行重新生成音频。
   *
   * @returns {Promise<void>} 初始化流程
   */
  async setup() {
    try {
      await fetch("/audio-trim/clear", { method: "POST" });
    } catch {
      /* 后端未就绪时忽略: 下次 Run 的 reset 会兜底清空 */
    }
    // 「截段」按钮样式: Nodes 2.0 把 button widget 渲染为 DOM <button>,
    // 节点增删/重绘会重建元素, 故持续套用(与 PreviewVideo 的 styleFrameButtons 同做法)
    styleSegmentButtons();
    new MutationObserver(styleSegmentButtons).observe(document.body, { childList: true, subtree: true });

    // 波形刷新: onExecuted 在 V3 节点上不可靠(实测从未触发), 改为监听 ComfyUI 的
    // executed 事件 + 工作流加载完成 + 低频轮询兜底, 三路保证波形最终会拉起来。
    api.addEventListener("executed", () => refreshAllAudioNodes());
    api.addEventListener("progress", () => refreshAllAudioNodes());
    setInterval(refreshAllAudioNodes, 5000);

    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    /**
     * 包装 queuePrompt: 默认 Run 分支先重置, partial 提交(带 queueNodeIds)不重置。
     *
     * @param {number} number 提交次数
     * @param {number} batch 批次数
     * @param {Array<string>|undefined} queueNodeIds 显式目标节点列表
     * @returns {Promise} 原 queuePrompt 返回值
     */
    app.queuePrompt = async function (number, batch, queueNodeIds) {
      if (!queueNodeIds?.length) {
        try {
          await fetch("/audio-trim/reset", { method: "POST" });
        } catch {
          /* 忽略 */
        }
      }
      return orig(number, batch, queueNodeIds);
    };
  },
  /**
   * 节点定义注册前钩子: 追加按钮 / 波形 / 段列表 / 输出段数, 并对齐端口。
   *
   * @param {Function} nodeType 节点类型构造函数
   * @param {object} nodeData 节点定义数据
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 建 保存/截段/完成 按钮 + 输出段数 + 波形 + 段列表。
     *
     * @returns {*} 原 onNodeCreated 返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      /**
       * 「保存」按钮: 把文件名/格式/质量 POST 到后端, 后端用缓存音频直接写 output,
       * 【不重跑工作流】。
       *
       * @returns {Promise<void>} 保存流程
       */
      node.addWidget("button", "保存", null, async () => {
        const getWidget = (name) => node.widgets?.find((w) => w.name === name)?.value;
        const prefixLinked = node.inputs?.find((i) => i.name === "filename_prefix")?.link != null;
        const suffixLinked = node.inputs?.find((i) => i.name === "filename_suffix")?.link != null;
        try {
          const resp = await fetch(`/audio-trim/save/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_prefix: getWidget("filename_prefix") ?? "audio",
              filename_prefix_linked: prefixLinked,
              filename_suffix: getWidget("filename_suffix") ?? "",
              filename_suffix_linked: suffixLinked,
              format: getWidget("format") ?? "flac",
              quality: getWidget("quality") ?? "128k",
              segment_index: 0,
            }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            toast("error", data?.message ?? "保存失败");
            return;
          }
          toast("success", data?.message ?? "已保存");
        } catch (err) {
          console.error("[FallingTS] 保存失败:", err);
          toast("error", "保存失败: 无法连接后端");
        }
      });

      // ── 截段功能区: 波形 → 截段按钮 → 输出段数 → 段列表 ──
      const waveWidget = createWaveformWidget(node);

      /**
       * 「截段」按钮: 把当前选区 POST 到后端累积, 并加入前端列表与端口。
       *
       * @returns {Promise<void>} 请求流程
       */
      node.addWidget("button", "截段", null, async () => {
        const st = waveWidget.state;
        if (!st.loaded) {
          toast("warn", "还没有音频波形, 请先点「完成」生成或运行工作流");
          return;
        }
        const duration = st.end - st.start;
        if (duration <= 0.01) {
          toast("warn", "请先在波形上拖动选出区间");
          return;
        }
        const listWidget = node._fallingtsSegments;
        if (listWidget.state.segments.length >= MAX_SEGMENTS) {
          toast("warn", `已达截段上限 ${MAX_SEGMENTS} 段`);
          return;
        }
        try {
          const resp = await fetch(`/audio-trim/segment/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ start: st.start, duration }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            toast("error", data?.message ?? "截段失败");
            return;
          }
          // 先对齐输出端口/total, 再重绘列表
          listWidget.state.segments.push({ start: st.start, duration });
          syncSegmentState(node, listWidget.state);
          listWidget.render();
          toast("success", `已添加第 ${data?.index ?? listWidget.state.segments.length} 段`);
        } catch (err) {
          console.error("[FallingTS] 截段失败:", err);
          toast("error", "截段失败: 无法连接后端");
        }
      });

      /**
       * 「完成」按钮: 有段 → 置 done + 释放生成模型内存 + 只提交下游; 无段 → reset + 全量提交。
       *
       * @returns {Promise<void>} 请求流程
       */
      node.addWidget("button", "完成", null, async () => {
        const segs = node._fallingtsSegments?.state?.segments ?? [];
        try {
          if (!segs.length) {
            try {
              await fetch("/audio-trim/reset", { method: "POST" });
            } catch {
              /* 忽略 */
            }
            await app.queuePrompt(0, 1);
            toast("info", "已开始生成音频, 回来后可拖动波形截段");
            return;
          }
          const resp = await fetch(`/audio-trim/done/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ segments: segs }),
          });
          const data = await resp.json().catch(() => null);
          if (!data?.done) {
            toast("warn", "请先截段再点完成");
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
          // partial 目标: 本节点之后的所有输出节点
          const targets = collectOutputsAfter(node);
          if (!targets.length) {
            console.warn("[FallingTS] 音频截段节点之后没有输出节点");
            toast("warn", "本节点之后没有可执行的输出节点(接下游预览/保存节点后再试)");
            return;
          }
          await submitPartial(node, targets);
          toast("success", `已完成(${segs.length} 段), 各段从 audio_1.. 输出到下游`);
        } catch (err) {
          console.error("[FallingTS] 完成失败:", err);
          toast("error", "完成失败: 无法连接后端");
        }
      });

      // ── 输出段数参数: 输出 audio 端口数量(默认 1, 最小 = max(1, 选中段数), 上限 MAX_SEGMENTS) ──
      const totalWidget = node.addWidget(
        "number",
        "输出段数",
        1,
        () => {
          syncSegmentState(node, node._fallingtsSegments?.state ?? { segments: [] });
        },
        { min: 1, max: MAX_SEGMENTS, step: 1, precision: 0 },
      );
      totalWidget.options.min = 1;
      totalWidget.options.max = MAX_SEGMENTS;
      node._fallingtsTotalWidget = totalWidget;

      // 段列表 DOM widget(波形 + 按钮之下)
      const segList = createSegmentListWidget(node);
      node._fallingtsSegments = segList;

      // 节点创建后立即按 total 对齐输出端口(与 route/fanout/composite 同款):
      // 新拖入节点无链接, 直接裁到 1(audio) + total 个 audio_N。
      if ((node.outputs ?? []).length > 0) syncSegmentState(node, { segments: [] });
      const onExecuted = node.onExecuted;
      node.onExecuted = function () {
        onExecuted?.apply(this, arguments);
        refreshWaveform(node, waveWidget, segList);
      };
      styleSegmentButton(node);
      segList.render();
      node.setSize([Math.max(340, node.size?.[0] ?? 340), Math.max(300, node.size?.[1] ?? 300)]);

      // 端口对齐: onConfigure 末尾按 total 对齐(configure 同步执行, 渲染在其后,
      // 因此不会出现"先显示全部 64 端口再隐藏"的闪烁 —— 一次成型)。
      const prevOnConfigure = node.onConfigure;
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        if (node._fallingtsSegments) {
          // 旧版 widgets_values 兜底: 老工作流里 suffix 槽可能落到按钮值 null
          const sw = node.widgets?.find((w) => w.name === "filename_suffix");
          if (sw && sw.value == null) sw.value = "";
          syncSegmentState(node, node._fallingtsSegments?.state ?? { segments: [] });
        }
      };
    };
  },
});
