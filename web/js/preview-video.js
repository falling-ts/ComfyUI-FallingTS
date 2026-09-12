/**
 * PreviewVideo 前端: 「保存」按钮 + 「截帧」功能(选中帧列表 + 动态输出端口)。
 *
 * 行为:
 * - 预览部分由节点原生 UI.PreviewVideo 负责(播放 temp 目录文件);
 * - 点「保存」: 把 文件名前缀 POST 到 /preview-video/save/{id},
 *   后端用 execute 时缓存的视频数据直接写 output({filename_prefix}.mp4, 同名覆盖、无序号) ——
 *   【不触发任何工作流重跑】, 保存的是当前画面上播放的这段视频。
 * - 点「截帧」: 读取节点预览 <video> 的当前播放时间(秒), POST 到
 *   /preview-video/frame/{id} {position_seconds} —— 后端按 fps 折算帧号, 从 execute 时缓存的
 *   帧集合取该帧转 PNG 返回; 前端把 PNG 追加到下方选中帧列表(从上往下渲染 <img>),
 *   并同步记录帧号列表到 selected_frames (DOM widget state);
 *   同时按选中帧数量动态增删 IMAGE 输出端口 (image_1..image_64, 未选中槽后端返回 None)。
 * - 输出端口与 md_table 同模式: 后端定长槽 (MAX_FRAMES=64) + 前端 addOutput/removeOutput 对齐,
 *   选中 k 帧即有 k 个 image 输出, 直连 FallingTSImageComposite 合成一张。
 * - 截帧状态刷新即清空: 页面加载(setup)时 POST /preview-video/clear 同步清空后端各节点
 *   selected_frames/_done; frame_list 的 configure 还原(setValue)不再写回 state ——
 *   浏览器刷新后回到未截帧初始态(前端缩略图与后端帧号都不保留; 视频缓存不清,「保存」仍可用)。
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_CLASS = "PreviewVideo";
const MAX_FRAMES = 64;

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
// 只做保存按钮扫描; 截帧按钮扫描独立于本门控(见下方 __fallingtsFrameBtnInited),
// 避免 preview-image/preview-audio 先加载时把本文件的门控置 true 导致截帧扫描缺失。
if (!window.__fallingtsSaveBtnInited) {
  window.__fallingtsSaveBtnInited = true;
  const init = () => {
    styleSaveButtons();
    new MutationObserver(styleSaveButtons).observe(document.body, { childList: true, subtree: true });
  };
  if (document.body) init();
  else document.addEventListener("DOMContentLoaded", init);
}

// 截帧按钮扫描: 独立门控 + 独立 MutationObserver(只属于 PreviewVideo)。
// 不与 __fallingtsSaveBtnInited 共享, 保证无论任何 js 先加载, 截帧按钮样式都会注册。
if (!window.__fallingtsFrameBtnInited) {
  window.__fallingtsFrameBtnInited = true;
  const initFrame = () => {
    styleFrameButtons();
    new MutationObserver(styleFrameButtons).observe(document.body, { childList: true, subtree: true });
  };
  if (document.body) initFrame();
  else document.addEventListener("DOMContentLoaded", initFrame);
}

// 完成按钮(红)扫描: 独立门控 + 独立 MutationObserver
if (!window.__fallingtsDoneBtnInited) {
  window.__fallingtsDoneBtnInited = true;
  const initDone = () => {
    styleDoneButtons();
    new MutationObserver(styleDoneButtons).observe(document.body, { childList: true, subtree: true });
  };
  if (document.body) initDone();
  else document.addEventListener("DOMContentLoaded", initDone);
}

/**
 * Nodes 2.0 渲染模式: 截帧按钮由 WidgetButton 组件渲染为 DOM <button>(canvas 覆写不生效),
 * 与保存按钮同款做法: 按文本/aria 匹配"截帧", 逐个设置 element.style(青绿渐变、圆角、更高);
 * 由 styleFrameButtons + MutationObserver 持续监控懒渲染。
 *
 * @param {HTMLElement} el 按钮元素
 * @returns {void}
 */
function applyFrameBtnStyle(el) {
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
  if (!el._fallingtsFrameStyled) {
    el._fallingtsFrameStyled = true;
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
 * 判断是否为截帧按钮(文本或 aria-label 为 截帧/Frame capture)。
 *
 * @param {HTMLElement} el 元素
 * @returns {boolean} 是否截帧按钮
 */
function isFrameBtn(el) {
  if (!el || el.tagName !== "BUTTON") return false;
  const txt = (el.innerText || "").trim();
  const aria = (el.getAttribute("aria-label") || "").trim();
  return txt === "截帧" || txt === "Frame capture" || aria === "截帧" || aria === "Frame capture";
}

/**
 * 遍历页面按钮, 对截帧按钮套样式(青绿)。
 *
 * @returns {void}
 */
function styleFrameButtons() {
  document.querySelectorAll("button").forEach((el) => {
    if (isFrameBtn(el)) applyFrameBtnStyle(el);
  });
}

/**
 * Nodes 2.0 渲染模式: 「完成」按钮由 WidgetButton 组件渲染为 DOM <button>。
 * 红色渐变(canvas 覆写不生效), 与保存/截帧同款做法: 按文本/aria 匹配, 逐套 element.style。
 *
 * @param {HTMLElement} el 按钮元素
 * @returns {void}
 */
function applyDoneBtnStyle(el) {
  el.style.height = "40px";
  el.style.minHeight = "40px";
  el.style.padding = "8px 12px";
  el.style.background = "linear-gradient(135deg,#e5484d,#ff6b70)";
  el.style.color = "#fff";
  el.style.borderRadius = "8px";
  el.style.fontSize = "15px";
  el.style.fontWeight = "700";
  el.style.letterSpacing = "1px";
  el.style.boxShadow = "0 2px 8px rgba(229,72,77,.35)";
  el.style.transition = "all .2s ease";
  el.style.border = "none";
  if (!el._fallingtsDoneStyled) {
    el._fallingtsDoneStyled = true;
    el.addEventListener("mouseenter", () => {
      el.style.background = "linear-gradient(135deg,#f05459,#ff7a80)";
      el.style.boxShadow = "0 4px 14px rgba(229,72,77,.5)";
      el.style.transform = "translateY(-1px)";
    });
    el.addEventListener("mouseleave", () => {
      el.style.background = "linear-gradient(135deg,#e5484d,#ff6b70)";
      el.style.boxShadow = "0 2px 8px rgba(229,72,77,.35)";
      el.style.transform = "";
    });
  }
}

/**
 * 判断是否为完成按钮(文本或 aria-label 为 完成/Finish/Done)。
 *
 * @param {HTMLElement} el 元素
 * @returns {boolean} 是否完成按钮
 */
function isDoneBtn(el) {
  if (!el || el.tagName !== "BUTTON") return false;
  const txt = (el.innerText || "").trim();
  const aria = (el.getAttribute("aria-label") || "").trim();
  return txt === "完成" || txt === "Finish" || txt === "Done" ||
    aria === "完成" || aria === "Finish" || aria === "Done";
}

/**
 * 遍历页面按钮, 对完成按钮套红色样式。
 *
 * @returns {void}
 */
function styleDoneButtons() {
  document.querySelectorAll("button").forEach((el) => {
    if (isDoneBtn(el)) applyDoneBtnStyle(el);
  });
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
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/**
 * 给「保存」按钮 widget 应用大气样式: 覆写 draw 用 canvas 绘制渐变圆角按钮,
 * 行高提高到 42; 点击时下压反馈(hover 由 ComfyUI/LiteGraph 的 widget.mouse 事件更新)。
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

  /**
   * 自定义绘制: 阴影层 + 渐变圆角主体 + 白字「保存」; _pressed 时下压。
   *
   * @param {CanvasRenderingContext2D} ctx canvas 上下文(已变换到节点局部)
   * @param {LGraphNode} _node 节点
   * @param {number} widget_width 控件宽
   * @param {number} y 控件在节点内纵坐标
   * @param {number} H 行高
   * @returns {void}
   */
  btn.draw = function (ctx, _node, widget_width, y, H) {
    const W = widget_width;
    const dy = this._pressed ? 1 : 0; // 点击时按钮下压 1px
    const BH = 52; // 按钮目标高度(固定, 不依赖外部 H)
    // 阴影层
    drawRoundRect(ctx, 6, y + 6, W - 12, BH - 8, 10);
    ctx.fillStyle = "rgba(0,0,0,.22)";
    ctx.fill();
    // 渐变主体
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
    // 白字
    ctx.fillStyle = "#ffffff";
    ctx.font = "700 16px 'Segoe UI','Microsoft YaHei',sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("保存", W / 2, y + BH / 2 + 1 + dy);
  };

  /**
   * 鼠标事件: 记录按下状态(下压反馈), 其余交给原 mouse(触发点击回调)。
   *
   * @param {Event} event 鼠标事件
   * @param {Array} pos 节点局部坐标
   * @param {LGraphNode} node 节点
   * @returns {*} 原 mouse 的返回值
   */
  btn.mouse = function (event, pos, node) {
    const inBtn = this.last_y != null && pos[1] >= this.last_y && pos[1] <= this.last_y + (this.computedHeight || 20);
    if (event.type === "mousedown") this._pressed = true;
    if (event.type === "mouseup" || (event.type === "mousedown" && !inBtn)) this._pressed = false;
    return origMouse ? origMouse.call(this, event, pos, node) : false;
  };

  node.setDirtyCanvas(true, true);
}

/**
 * 给「截帧」按钮 widget 应用样式: 覆写 draw 用 canvas 绘制渐变圆角按钮。
 * 用与保存按钮不同的 青绿色 (保存=紫渐变, 截帧=青绿渐变)。
 *
 * @param {LGraphNode} node 节点对象(其 widgets 里含 type === "button" 的截帧按钮)
 * @returns {void}
 */
function styleFrameButton(node) {
  const btn = node.widgets?.find((w) => w.type === "button" && w.name === "截帧");
  if (!btn) return;

  btn.computedHeight = 56;

  const origDraw = btn.draw;
  const origMouse = btn.mouse;

  /**
   * 自定义绘制: 阴影层 + 青绿渐变圆角主体 + 白字「截帧」; _pressed 时下压。
   */
  btn.draw = function (ctx, _node, widget_width, y, H) {
    const W = widget_width;
    const dy = this._pressed ? 1 : 0;
    const BH = 52;
    drawRoundRect(ctx, 6, y + 6, W - 12, BH - 8, 10);
    ctx.fillStyle = "rgba(0,0,0,.22)";
    ctx.fill();
    drawRoundRect(ctx, 6, y + 3 + dy, W - 12, BH - 8, 10);
    const g = ctx.createLinearGradient(0, y, 0, y + BH);
    if (this._pressed) {
      g.addColorStop(0, "#0c9e6a");
      g.addColorStop(1, "#12c98c");
    } else {
      g.addColorStop(0, "#0bb47d");
      g.addColorStop(1, "#17d9a0");
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
    ctx.fillText("截帧", W / 2, y + BH / 2 + 1 + dy);
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
 * 给「完成」按钮 widget 应用样式: 覆写 draw 用 canvas 绘制红色渐变圆角按钮。
 * (当前 Nodes 2.0 以 DOM <button> 渲染为主, canvas 版为兜底, 与保存/截帧按钮同构)
 *
 * @param {LGraphNode} node 节点对象(其 widgets 里含 type === "button" 的完成按钮)
 * @returns {void}
 */
function styleDoneButton(node) {
  const btn = node.widgets?.find((w) => w.type === "button" && w.name === "完成");
  if (!btn) return;

  btn.computedHeight = 56;

  const origDraw = btn.draw;
  const origMouse = btn.mouse;

  btn.draw = function (ctx, _node, widget_width, y, H) {
    const W = widget_width;
    const dy = this._pressed ? 1 : 0;
    const BH = 52;
    drawRoundRect(ctx, 6, y + 6, W - 12, BH - 8, 10);
    ctx.fillStyle = "rgba(0,0,0,.22)";
    ctx.fill();
    drawRoundRect(ctx, 6, y + 3 + dy, W - 12, BH - 8, 10);
    const g = ctx.createLinearGradient(0, y, 0, y + BH);
    if (this._pressed) {
      g.addColorStop(0, "#d0353a");
      g.addColorStop(1, "#f04b50");
    } else {
      g.addColorStop(0, "#e5484d");
      g.addColorStop(1, "#ff6b70");
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
    ctx.fillText("完成", W / 2, y + BH / 2 + 1 + dy);
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
 * 在节点上创建「选中帧列表」DOM widget: 内嵌容器, 从上往下渲染截帧 <img>。
 * 列表不固定高度、不封顶、不滚动: 高度按帧数无限撑开(getMinHeight = 帧数×行高),
 * 节点高度随列表内容自然扩展, 有多少帧撑多高, 不压缩、不跳变。
 * 状态 state = {frames: [{url, fno}]}; 截帧状态刷新即清空 —— configure 还原时
 * setValue 不再把序列化的帧写回 state(保持空列表), 后端由页面加载时的
 * /preview-video/clear 同步清空。
 *
 * @param {LGraphNode} node 节点对象
 * @returns {object} {widget, state, render} —— addDOMWidget 创建的 widget、帧状态、列表重绘函数
 */
function createFrameListWidget(node) {
  // 列表高度: 不固定、不封顶, 按帧数无限撑开(有多少帧撑多高);
  // 每行 = 缩略图 56px + 上下 padding 8px = ROW_H(64px), 行间距 GAP_H(6px);
  // 空态占位 EMPTY_H(一行提示)。
  const EMPTY_H = 44;
  const ROW_H = 64;
  const GAP_H = 6;
  /**
   * 当前列表总高度: 空态 EMPTY_H; 有帧 = 帧数×ROW_H + (帧数-1)×GAP_H(无限撑开, 不封顶)。
   * @returns {number} 列表总高(px)
   */
  const frameBoxHeight = () =>
    state.frames.length === 0
      ? EMPTY_H
      : state.frames.length * ROW_H + (state.frames.length - 1) * GAP_H;

  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.gap = GAP_H + "px";
  root.style.overflow = "visible"; // 不滚动: 列表按内容无限撑开, 节点高度随之扩展
  root.style.width = "100%";
  root.style.boxSizing = "border-box";

  const state = { frames: [] };

  const render = () => {
    // 列表按内容无限撑开(不设 height, overflow visible): 先重建 DOM, 再 fitHeight 同步节点
    // 到精确高度(列表高度 = 帧数×行高)。关键: fitHeight 必须在 DOM 重建之后,
    // 否则截帧后会按旧(更少)高度压缩节点 = "自动缩高度"。
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
      row.style.display = "flex";
      row.style.alignItems = "center";
      row.style.gap = "8px";
      row.style.padding = "4px";
      row.style.background = "rgba(255,255,255,.04)";
      row.style.borderRadius = "6px";

      const img = document.createElement("img");
      img.src = f.url;
      img.style.cssText = "height:56px;width:auto;border-radius:4px;display:block;";

      const labelWrap = document.createElement("div");
      labelWrap.style.cssText = "flex:1;display:flex;flex-direction:column;gap:2px;min-width:0;";
      const fnoEl = document.createElement("div");
      fnoEl.textContent = `帧 ${f.fno}`;
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
          await fetch(`/preview-video/frame-remove/${node.id}`, {
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

  // 增量 fitHeight 基准: 初始列表 minHeight(空态 EMPTY_H), 后续按 delta 调整节点高度,
  // 保证「节点高度增加量 = 列表增加量」, distributeSpace 后 video 预览高度不变。
  node._fallingtsListMin = frameBoxHeight();

  const widget = node.addDOMWidget("frame_list", "fallingts_frame_list", root, {
    getValue: () => state,
    setValue: () => {
      // 刷新即清空: 不再还原序列化的帧列表, state 保持空(后端已由 /preview-video/clear 同步清空)
      render();
    },
    getMinHeight: () => frameBoxHeight(),
    // 固定上限: maxSize = 列表 minHeight, 不让列表无上限扩展抢 distributeSpace 剩余空间
    // (剩余空间 e 被列表吃满时 video = e - 列表高 会被挤小)。多余空间留给 video,
    // 配合增量 fitHeight, 视频框高度稳定不压缩。
    getMaxHeight: () => frameBoxHeight(),
    serialize: true,
  });
  render(); // 创建即渲染占位提示 + 定滚动盒初始高度
  return { widget, state, render };
}

/**
 * 同步选中帧状态: 更新 total 下限 + 按 total 对齐输出端口数量。
 *
 * total 规则(与 composite 同款):
 * - total 最小 = max(1, selected_images 长度): 截帧后选中数 > total 时自动抬高 total;
 * - 输出端口数 = 1(video) + total 个 image, 而非按选中数;
 * - 选中数变为 0 时 total 最小回到 1(不得为 0)。
 *
 * @param {LGraphNode} node 节点对象
 * @param {object} state 选中帧列表状态 {frames: [{url, fno}]}
 * @returns {void}
 */
function syncFrameState(node, state) {
  // 1) total 下限随选中数: min = max(1, frames.length)
  const totalWidget = node._fallingtsTotalWidget;
  const selectedCount = state?.frames?.length ?? 0;
  const minTotal = Math.max(1, selectedCount);
  if (totalWidget?.options) {
    totalWidget.options.min = minTotal;
    // 截帧后 total < 选中数 -> 抬高到选中数; 大于等于不做处理
    const cur = Number(totalWidget.value) || 1;
    if (cur < minTotal) {
      totalWidget.value = minTotal;
      totalWidget.callback?.(minTotal);
    }
  }

  // 2) 输出端口: [0]=video, [1..]=image_1..N; 数量 = 1 + total
  const total = Math.max(1, Number(totalWidget?.value) || 1);
  const target = 1 + total;
  const startIdx = 1; // video 端口保留在 0
  // 只删"无链接"的尾部端口: 加载工作流时端口可能带着已有链接(保存的 image_1..N),
  // 强删带链接端口会让前端链接重建时对已删端口写 .link -> "Cannot set properties of undefined"。
  // 若尾部端口都带链接(实际选中数超出 target), 则保留, 待用户操作后自然收敛。
  while ((node.outputs?.length ?? 0) > target) {
    const tail = node.outputs[node.outputs.length - 1];
    if (tail && (tail.links?.length ?? 0) > 0) break;
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < target) {
    node.addOutput("image_" + (node.outputs.length - startIdx + 1), "IMAGE");
  }
  for (let i = startIdx; i < (node.outputs?.length ?? 0); i++) {
    const fno = state.frames[i - startIdx]?.fno ?? (i - startIdx + 1);
    node.outputs[i].name = `image_${i}`;
    node.outputs[i].label = `选中帧 ${fno}`;
  }
  emitDirty(node);
}

/**
 * 截帧列表撑开时增量同步节点高度: 高度变化量 = 列表 minHeight 变化量。
 *
 * 为什么不用 computeSize: ComfyUI 节点把「剩余空间 e = 节点高 - 标题 - 固定 widget」
 * 经 distributeSpace 分给所有 DOM widget(video 预览 + 本列表), 二者 maxSize 都无上限。
 * computeSize 基于「上一轮布局」的 computedHeight, 截帧后偏小(不含新列表增量 Δ);
 * 用它设节点高 → e 偏小 → distributeSpace 把 e 让给新列表, video = e - 列表高 被挤小 Δ
 * (即「点截帧视频框自动压缩」)。
 *
 * 增量法: 节点高 += Δ, 则 e += Δ, distributeSpace 后 video = e - 新列表高
 * = (e_旧 + Δ) - (列表_旧 + Δ) = e_旧 - 列表_旧 = video_旧, 视频框高度不变。
 * 宽度保留用户设置, 只动高度。
 *
 * @param {LGraphNode} node
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
 * 完成截帧后的 partial execution 用它收集执行目标: 只执行预览节点之后的部分。
 * @param {LGraphNode} node 画布节点对象
 * @returns {boolean} 该节点的 nodeData.output_node 为 true 返回 true
 */
function isOutputNode(node) {
  return node?.constructor?.nodeData?.output_node === true;
}

/**
 * 从 startNode 下游 BFS, 收集所有输出节点, 作为 partial_execution_targets 传给 /prompt。
 * 完成截帧后只执行本段子图(预览节点 -> 合成 -> 保存), 上游(模型/采样/预览节点之前)
 * 因 video 输入 lazy 门控被跳过 —— 运行时看不到预览视频前面的所有节点。
 *
 * @param {LGraphNode} startNode 锚点节点(通常是预览视频节点自身), 从其输出开始遍历
 * @returns {string[]} 输出节点的 ID 字符串数组(已去重); 一个都没有时返回空数组
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
 * 注意不能写成 app.queuePrompt(0, 1, targets): ComfyUI 的 api.queuePrompt 第 3 参数
 * 是选项对象 {partialExecutionTargets}(驼峰), 传裸数组会被 `?.partialExecutionTargets`
 * 静默取成 undefined, 于是退化成全量提交(上游采样白跑一遍)。
 * 这里直接用 graphToPrompt 的结果 POST /prompt, 显式带 partial_execution_targets。
 *
 * @param {LGraphNode} node 锚点节点(预览视频节点自身)
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
    throw new Error(`提交失败 HTTP ${resp.status} ${t.slice(0, 200)}`);
  }
  return resp.json();
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
  videoEl.style.cssText =
    "display:block;width:100%;max-height:240px;background:#000;border-radius:6px;";

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
 * @param {LGraphNode} node 节点
 * @returns {Promise<void>} 无
 */
async function restoreVideo(node) {
  const fb = node._fallingtsVideoFallback;
  let url = null;
  try {
    const r = await fetch(`/preview-video/video-url/${node.id}`);
    const j = await r.json().catch(() => null);
    if (r.ok && j?.status === "ok") url = j.url;
  } catch {
    /* 后端未就绪时忽略 */
  }
  if (!url) {
    if (fb) fb.element.style.display = "none";
    return;
  }

  // 节点内已有的原生 <video>(排除备用播放器自己)
  const host = document.querySelector(`[data-node-id="${node.id}"]`);
  const nativeVid = host
    ? [...host.querySelectorAll("video")].find((v) => !(fb?.element?.contains(v) ?? false))
    : null;

  if (nativeVid) {
    if (nativeVid.dataset.src !== url) {
      nativeVid.dataset.src = url;
      nativeVid.src = url;
      nativeVid.controls = true;
    }
    if (fb) fb.element.style.display = "none";
    return;
  }

  if (fb) {
    fb.element.style.display = "";
    if (fb.videoEl.dataset.src !== url) {
      fb.videoEl.dataset.src = url;
      fb.videoEl.src = url;
      fb.videoEl.load();
    }
  }
}

/**
 * 从后端读回截帧状态并重建前端帧列表(页面刷新/工作流重载后恢复上一次的截帧结果)。
 *
 * 后端是唯一事实来源: GET /state 拿帧号, 再对每个帧号 POST /frame(append=false) 取回 PNG,
 * 转成 blob URL 填进 frame_list。这样刷新不会丢截帧, 也不再把后端状态清掉。
 *
 * @param {LGraphNode} node 预览视频节点
 * @param {object} frameList 帧列表 DOM widget
 * @returns {Promise<void>} 无
 */
async function restoreFrames(node, frameList) {
  if (!frameList) return;
  try {
    const r = await fetch(`/preview-video/state/${node.id}`);
    const st = await r.json().catch(() => null);
    if (!r.ok || st?.status !== "ok") return;
    const fnos = st.selected_frames || [];
    if (!fnos.length) return;

    const frames = [];
    for (const fno of fnos) {
      const resp = await fetch(`/preview-video/frame/${node.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "frame", frame_index: fno, append: false }),
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

app.registerExtension({
  name: "FallingTS.PreviewVideo",

  /**
   * 扩展初始化钩子。
   *
   * 页面加载/刷新时**不清后端状态** —— 截帧列表改由 restoreFrames 从
   * GET /preview-video/state 读回并重建, 刷新不再丢上一次的截帧结果。
   * 仍然包装全局提交入口 app.queuePrompt: 默认 Run(未显式指定目标节点)时,
   * 先 POST /preview-video/reset 重置所有预览节点为未完成, 再按原逻辑全量提交 ——
   * 保证每次 Run 都从开头执行、重新拉上游生成视频(与继续节点同语义)。
   *
   * @returns {void}
   */
  async setup() {
    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    /**
     * 包装 queuePrompt: 拦截"默认 Run"(queueNodeIds 为空)分支, 先重置预览节点再提交。
     * 完成截帧后的 partial 提交(带 queueNodeIds)保留已放行状态, 不重置。
     *
     * @param {number} number 提交次数
     * @param {number} batch 批次数
     * @param {Array<string>|undefined} queueNodeIds 「完成」按钮显式指定的目标节点 ID 列表, 非空时跳过重置
     * @returns {Promise} 原始 queuePrompt 的返回值(提交任务后的 Promise)
     */
    app.queuePrompt = async function (number, batch, queueNodeIds) {
      /* 默认 Run (无显式目标): 重置所有预览节点为未完成, 再全量提交 */
      if (!queueNodeIds?.length) {
        try {
          await fetch("/preview-video/reset", { method: "POST" });
        } catch {
          /* 忽略 */
        }
      }
      return orig(number, batch, queueNodeIds);
    };
  },

  /**
   * 扩展初始化: 监听执行事件, 让视频预览在跑完后重新判定一次。
   *
   * ComfyUI 的原生预览 <video> 是收到 UI.PreviewVideo 事件后才渲染的 —— 比 onConfigure 晚。
   * 因此执行结束后再调一次 restoreVideo: 原生播放器一出现就把备用播放器收起来, 避免两个
   * 播放器并存时用户拖到隐藏的那个(截帧会读到 currentTime=0, 表现为每次都截到第 1 帧、
   * 提示「帧 1 已在选中列表中」)。
   *
   * @returns {Promise<void>} 无
   */
  async setup() {
    let timer = null;
    const refresh = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        for (const n of app.graph?._nodes || []) {
          if (n.type === NODE_CLASS) restoreVideo(n);
        }
      }, 600);
    };
    api.addEventListener("executed", refresh);
    api.addEventListener("progress", refresh);
  },

  /**
   * 节点定义注册前钩子: 给 PreviewVideo 追加「截帧」按钮 + 选中帧列表 + 端口对齐。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 追加「保存」按钮(保留) + 「截帧」按钮 + 选中帧列表 + 帧 DOM widget。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      // 原「保存」按钮(逻辑不变)
      node.addWidget("button", "保存", null, async () => {
        const prefixWidget = node.widgets?.find((w) => w.name === "filename_prefix");
        const prefixLinked =
          node.inputs?.find((i) => i.name === "filename_prefix")?.link != null;
        // filename_suffix 同前缀: 连线时用 execute 实际接收值, 手动输入用 widget 值
        // (旧工作流由 onConfigure 按旧形状迁移, suffix 恒有值; ?? "" 兜底)
        const suffixWidget = node.widgets?.find((w) => w.name === "filename_suffix");
        const suffixLinked =
          node.inputs?.find((i) => i.name === "filename_suffix")?.link != null;
        try {
          const resp = await fetch(`/preview-video/save/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_prefix: prefixWidget?.value ?? "video",
              filename_prefix_linked: prefixLinked,
              filename_suffix: suffixWidget?.value ?? "",
              filename_suffix_linked: suffixLinked,
            }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            app.extensionManager.toast.add({ severity: "error", summary: data?.message ?? "保存失败" });
            return;
          }
          app.extensionManager.toast.add({ severity: "success", summary: data?.message ?? "已保存" });
        } catch (err) {
          console.error("[FallingTS] 保存失败:", err);
          app.extensionManager.toast.add({ severity: "error", summary: "保存失败: 无法连接后端" });
        }
      });
      styleSaveButton(node);

      // ── 截帧功能区: 截帧按钮 → 输出帧数 → 选中帧列表(列表必须在按钮下方) ──

      /**
       * 「截帧」按钮点击处理: 读节点预览 <video> 当前时间, POST 后端取帧 PNG,
       * 追加到选中帧列表并同步输出端口。
       *
       * 后端按播放时间(秒)×fps 折算帧号取帧; 无 preview video 时回退取 start。 
       * @returns {Promise<void>} 截帧请求异步流程
       */
      node.addWidget("button", "截帧", null, async () => {
        // 读「用户实际在拖动的」播放器的当前播放位置(浏览器原生 currentTime = 秒)。
        //
        // 节点里可能同时存在两个 <video>: ComfyUI 原生预览(跑过之后才渲染) + 我方备用播放器
        // (刷新后恢复预览用, 默认 display:none)。不能盲取 querySelector("video") 的第一个 ——
        // 隐藏的备用元素 currentTime 恒为 0, 会导致每次都截到第 1 帧, 表现为
        // 「帧 1 已在选中列表中」。改为: 收集全部候选, 优先「可见且已设置 src」, 其中取
        // currentTime 最大者(即用户拖动过的那个)。
        let positionSeconds = 0;
        try {
          const domNode = document.querySelector(`[data-node-id="${node.id}"]`);
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
          if (pick) positionSeconds = pick.currentTime || 0;
        } catch (err) {
          console.warn("[FallingTS] 读取播放时间失败, 取 0 秒:", err);
        }

        try {
          const resp = await fetch(`/preview-video/frame/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ position_seconds: positionSeconds }),
          });
          if (!resp.ok) {
            const data = await resp.json().catch(() => null);
            app.extensionManager.toast.add({ severity: "error", summary: data?.message ?? "截帧失败" });
            return;
          }
          // 后端返回 PNG 字节 + X-Frame-Index 帧号(1-based)
          const fno = Number(resp.headers.get("X-Frame-Index") || frameList.state.frames.length + 1);
          const blob = await resp.blob();
          const url = URL.createObjectURL(blob);

          if ((frameList.state.frames.length) >= MAX_FRAMES) {
            app.extensionManager.toast.add({ severity: "warn", summary: `已达截帧上限 ${MAX_FRAMES} 张` });
            URL.revokeObjectURL(url);
            return;
          }

          frameList.state.frames.push({ url, fno });
          // 先对齐输出端口/total, 再重绘列表(render 内按新盒高同步节点高度)
          syncFrameState(node, frameList.state);
          frameList.render();
          // ── 一次性诊断: 截帧后 video 框高度变化根源 ──
          setTimeout(() => {
            const domRoot = node.dom || node.doc || node.videoContainer || null;
            const videoContainer =
              domRoot?.querySelector?.(".comfy-img-preview") ||
              node.doc?.querySelector?.(".comfy-img-preview");
            const videoWidget = node.widgets?.find((w) => w.name === "video-preview");
            const listWidget = node.widgets?.find((w) => w.name === "frame_list");
            console.log("[FallingTS][diag] ===== 截帧后高度诊断 =====");
            console.log("帧数:", frameList.state.frames.length);
            console.log("节点高度 node.size[1]:", node.size?.[1]);
            console.log("video 容器 actual height:", videoContainer?.getBoundingClientRect?.()?.height);
            console.log("video widget computeLayoutSize:", videoWidget?.computeLayoutSize?.());
            console.log("列表 widget computeLayoutSize:", listWidget?.computeLayoutSize?.());
            console.log("列表容器 actual height:", listWidget?.element?.getBoundingClientRect?.()?.height);
            console.log("node.dom/doc/videoContainer 存在:", !!node.dom, !!node.doc, !!node.videoContainer);
            console.log("[FallingTS][diag] ===== 诊断结束 =====");
          }, 150);
        } catch (err) {
          console.error("[FallingTS] 截帧失败:", err);
          app.extensionManager.toast.add({ severity: "error", summary: "截帧失败: 无法连接后端" });
        }
      });
      styleFrameButton(node);

      // ── 完成: 完全实现继续节点功能(无帧=预加载上游, 有帧=懒加载截断上游) ──
      // 语义(与持续节点同套):
      // - 无选中帧: 「完成」= 放行往上的节点预加载 —— 全量提交(Run), 上游生成视频到本节点
      //   缓存并预览供截帧(不输出帧, 因为还没选);
      // - 有选中帧: 「完成」= 懒加载截断 —— 后端置 done, 本节点 video 输入 lazy 门控
      //   不拉上游(用缓存的视频/帧), 前端 partial_execution_targets 只提交本节点之后的下游
      //   输出节点, 运行时看不到预览视频前面的所有节点。
      node.addWidget("button", "完成", null, async () => {
        const frames = node._fallingtsFrameList?.state?.frames ?? [];
        const selectedCount = frames.length;
        try {
          if (selectedCount === 0) {
            // 无帧: 预加载上游 —— reset(清 done -> lazy 拉上游) + 全量提交
            try {
              await fetch("/preview-video/reset", { method: "POST" });
            } catch { /* 忽略 */ }
            await app.queuePrompt(0, 1);
            app.extensionManager.toast.add({ severity: "info", summary: "已开始生成视频, 播放后可截帧" });
            return;
          }
          // 有帧: 置 done(后端校验有帧且同步前端帧号) -> partial 提交只跑下游
          const fnos = frames.map((f) => f.fno).filter((v) => Number.isFinite(v));
          const resp = await fetch(`/preview-video/done/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ frames: fnos }),
          });
          if (!resp.ok) {
            app.extensionManager.toast.add({ severity: "error", summary: "完成失败: 后端无响应" });
            return;
          }
          const data = await resp.json().catch(() => null);
          if (!data?.done) {
            app.extensionManager.toast.add({ severity: "warning", summary: "请先截帧再点完成" });
            return;
          }
          // 释放上一段用过的生成模型内存(可选, 失败不影响)
          try {
            await fetch("/free", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ unload_models: true, free_memory: true }),
            });
          } catch { /* 忽略 */ }
          // partial 目标: 本节点之后的所有输出节点(合成/预览/保存...)
          const targets = collectOutputsAfter(node);
          if (!targets.length) {
            console.warn("[FallingTS] 预览节点之后没有输出节点");
            return;
          }
          await submitPartial(node, targets);
          app.extensionManager.toast.add({ severity: "success", summary: "已完成, 截帧输出到下游" });
        } catch (err) {
          console.error("[FallingTS] 完成失败:", err);
          app.extensionManager.toast.add({ severity: "error", summary: "完成失败: 无法连接后端" });
        }
      });
      styleDoneButton(node);

      // ── 输出帧数参数: 输出 image 端口数量 (默认 1, 最小 = max(1, 选中帧数), 上限 MAX_FRAMES) ──
      const totalWidget = node.addWidget("number", "输出帧数", 1, (value) => {
        syncFrameState(node, node._fallingtsFrameList?.state ?? { frames: [] });
      }, { min: 1, max: MAX_FRAMES, step: 1, precision: 0 });
      totalWidget.options.min = 1;
      totalWidget.options.max = MAX_FRAMES;
      node._fallingtsTotalWidget = totalWidget;

      // 选中帧列表 DOM widget(截帧按钮 + 输出帧数之下, 从上往下渲染截帧图)
      const frameList = createFrameListWidget(node);
      node._fallingtsFrameList = frameList;

      // 备用视频播放器: 页面刷新后原生 UI.PreviewVideo 不重发, 由 restoreVideo 补上
      node._fallingtsVideoFallback = createVideoFallbackWidget(node);

      // 节点创建后立即按 total 对齐输出端口(与 route/fanout/composite 同款同步做法):
// 新拖入节点无任何链接, 直接裁到 1(video)+total 个 image; configure 阶段(同步)
// 会用保存的端口列表覆盖, 无需担心此处裁剪影响链接恢复。
      if ((node.outputs ?? []).length > 0) syncFrameState(node, { frames: [] });
      fitHeight(node);

      // 端口对齐: onConfigure 末尾按 total 对齐端口(截帧状态刷新即清空, 帧列表不再还原)
      const prevOnConfigure = node.onConfigure;
      node.onConfigure = function (info) {
        prevOnConfigure?.call(this, info);
        if (node._fallingtsFrameList) {
          // ── 旧版 widgets_values 迁移 ──
          // 当前结构: [filename, suffix, 保存, 截帧, 完成, 输出帧数, frame_list] (7 槽, suffix 紧挨前缀)
          // 旧结构 A(含「重新截帧」按钮): [filename, 保存, 截帧, 完成, 重新截帧, 输出帧数, frame_list]
          // 旧结构 B(删「重新截帧」、加 suffix 前): [filename, 保存, 截帧, 完成, 输出帧数, frame_list]
          // 旧结构 C(最早, 仅保存按钮): [filename, 保存]
          // 新版前端保存的文件带 widgets_values_named(含 filename_suffix 键) → 位置已是新序, 跳过;
          // 其余按旧形状检测: A 按位置恰好对齐只需清帧; B 输出帧数槽吃到旧 frame_list 对象, 按名修正;
          // 各旧结构 suffix 槽落到旧按钮值 null → 统一空串; 帧列表刷新即清空, 一并清出序列化载荷。
          const named = info?.widgets_values_named;
          const isNewFormat = named && typeof named === "object" && "filename_suffix" in named;
          const wv = info?.widgets_values;
          if (!isNewFormat && Array.isArray(wv)) {
            const tw = node._fallingtsTotalWidget;
            if (wv.length === 7 && typeof wv[5] === "number" && wv[6] && Array.isArray(wv[6].frames)) {
              // 旧结构 A: 位置恢复后各槽恰好对齐(重新截帧 null 落完成槽), 修正 total + 清帧
              if (tw) tw.value = wv[5];
              info.widgets_values = [wv[0], "", wv[1], wv[2], wv[3], wv[5], { frames: [] }];
            } else if (wv.length === 6 && typeof wv[4] === "number") {
              // 旧结构 B: 输出帧数槽吃到旧 frame_list 对象, 按名修正 total
              if (tw) tw.value = wv[4];
              info.widgets_values = [wv[0], "", wv[1], wv[2], wv[3], wv[4], { frames: [] }];
            }
            const sw = node.widgets?.find((w) => w.name === "filename_suffix");
            if (sw && sw.value == null) sw.value = "";
          }
          // 同步裁剪到 1+total: configure 是同步的, 渲染发生在 configure 完成后,
          // 因此不会出现"先显示全部 64 端口再隐藏"的闪烁 —— 一次成型。
          // 安全: syncFrameState 只删无链接尾部端口(带链接的保留, 绝不动),
          // configure 阶段 node.outputs 已是保存的端口列表(links 字段齐备),
          // 与 route/fanout/composite 的 onConfigure 同步对齐行为一致。
          syncFrameState(node, node._fallingtsFrameList?.state ?? { frames: [] });
          fitHeight(node);
          // 后端是唯一事实来源: 从它读回截帧列表与视频预览并重建前端(刷新不丢)
          restoreFrames(node, node._fallingtsFrameList);
          restoreVideo(node);
        }
      };
    };
  },
});