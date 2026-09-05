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
 * 状态 state = {frames: [{url, fno}]}; 截帧状态刷新即清空 —— configure 还原时
 * setValue 不再把序列化的帧写回 state(保持空列表), 后端由页面加载时的
 * /preview-video/clear 同步清空。
 *
 * @param {LGraphNode} node 节点对象
 * @returns {object} addDOMWidget 创建的 widget
 */
function createFrameListWidget(node) {
  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.gap = "6px";
  root.style.maxHeight = "400px";
  root.style.overflowY = "auto";
  root.style.width = "100%";

  const state = { frames: [] };

  const render = () => {
    root.innerHTML = "";
    if (state.frames.length === 0) {
      const hint = document.createElement("div");
      hint.textContent = "点击「截帧」选取视频帧";
      hint.style.cssText = "color:#888;font-size:12px;padding:8px 4px;text-align:center;";
      root.appendChild(hint);
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
      img.style.cssText = "width:72px;height:auto;border-radius:4px;display:block;";

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
  };

  const widget = node.addDOMWidget("frame_list", "fallingts_frame_list", root, {
    getValue: () => state,
    setValue: () => {
      // 刷新即清空: 不再还原序列化的帧列表, state 保持空(后端已由 /preview-video/clear 同步清空)
      render();
    },
    getMinHeight: () => Math.min(420, 60 + state.frames.length * 84 + 12),
    serialize: true,
  });
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
 * 高度收回/扩展到自然高度 (宽度保留用户设置)。
 * 构造器按 nodeData 生成全部 64 个 image 输出先把高度撑满, 同步裁剪端口后需收回多余高度;
 * total 增大补端口时同样需要扩展到位。
 * @param {LGraphNode} node
 */
function fitHeight(node) {
  const natural = node.computeSize?.();
  if (!natural || !node.size) return;
  if (Math.abs(node.size[1] - natural[1]) > 1) {
    node.setSize([node.size[0], natural[1]]);
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

app.registerExtension({
  name: "FallingTS.PreviewVideo",

  /**
   * 扩展初始化钩子: ① 截帧状态刷新即清空 —— 页面加载时 POST /preview-video/clear 同步清空
   * 后端所有 PreviewVideo 的 selected_frames/_done(前端 state 随刷新本就回空, 这里清的是
   * 进程内存, 避免"前端列表已空但后端还留着旧帧号"导致下次截帧追加到旧帧后);
   * ② 包装全局提交入口 app.queuePrompt: 默认 Run(未显式指定目标节点)时,
   * 先 POST /preview-video/reset 重置所有预览节点为未完成, 再按原逻辑全量提交 ——
   * 保证每次 Run 都从开头执行、重新拉上游生成视频(与继续节点同语义)。
   *
   * @returns {void}
   */
  async setup() {
    try {
      await fetch("/preview-video/clear", { method: "POST" });
    } catch {
      /* 后端未就绪时忽略: 下次 Run 的 reset 会兜底清空 */
    }
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
        // (旧工作流 widgets_values 按位置对齐, 尾部 null 落到 suffix 槽, ?? "" 兜底)
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
        // 读节点预览 video 当前播放位置(浏览器原生 currentTime = 秒)
        let positionSeconds = 0;
        try {
          const domNode = document.querySelector(`[data-node-id="${node.id}"]`);
          const videoEl =
            domNode?.querySelector("video") ??
            node.videoContainer?.querySelector?.("video") ??
            node.doc?.querySelector?.("video");
          if (videoEl && typeof videoEl.currentTime === "number") {
            positionSeconds = videoEl.currentTime || 0;
          }
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
          frameList.render();
          syncFrameState(node, frameList.state);
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
          await app.queuePrompt(0, 1, targets);
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
          // 旧结构(含「重新截帧」按钮): [filename, 保存, 截帧, 完成, 重新截帧, 输出帧数, frame_list]
          // 新结构:                      [filename, 保存, 截帧, 完成,      输出帧数, frame_list]
          // 删除「重新截帧」按钮后按位置恢复会错位(输出帧数吃 None / frame_list 吃数字),
          // 此处按旧结构特征(7 项且第 6/7 位为 number + {frames})显式迁移。
          const wv = info?.widgets_values;
          if (Array.isArray(wv) && wv.length === 7 && typeof wv[5] === "number" && wv[6] && Array.isArray(wv[6].frames)) {
            const tw = node._fallingtsTotalWidget;
            // 无条件修正 total(ComfyUI 已按位置恢复过, 错位后 tw.value 可能不是合法值)
            if (tw) tw.value = wv[5];
            // 刷新即清空: 帧列表不再还原, 序列化载荷里的旧帧一并清掉, 保存时即为干净格式
            info.widgets_values = [wv[0], wv[1], wv[2], wv[3], wv[5], { frames: [] }];
          }
          // 同步裁剪到 1+total: configure 是同步的, 渲染发生在 configure 完成后,
          // 因此不会出现"先显示全部 64 端口再隐藏"的闪烁 —— 一次成型。
          // 安全: syncFrameState 只删无链接尾部端口(带链接的保留, 绝不动),
          // configure 阶段 node.outputs 已是保存的端口列表(links 字段齐备),
          // 与 route/fanout/composite 的 onConfigure 同步对齐行为一致。
          syncFrameState(node, node._fallingtsFrameList?.state ?? { frames: [] });
          fitHeight(node);
        }
      };
    };
  },
});