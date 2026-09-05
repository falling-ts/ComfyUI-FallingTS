/**
 * PreviewAudioSave 前端: 底部追加「保存」按钮(大气样式, canvas 渐变绘制)。
 *
 * 行为:
 * - 预览部分由节点原生 UI.PreviewAudio 负责(播放 temp 目录 flac);
 * - 点「保存」: 把 文件名/格式/质量 POST 到 /preview-audio/save/{id},
 *   后端用 execute 时缓存的音频数据直接写 output({filename_prefix}.{format}, 同名覆盖、无序号) ——
 *   【不触发任何工作流重跑】, 保存的是当前画面上播放的这段音频。
 * - 按钮为 ComfyUI canvas widget(canvasOnly), 无 DOM element, 故覆写 widget.draw
 *   用 canvas 绘制: 渐变圆角、阴影、白字; 点击时下压反馈。
 */

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "PreviewAudioSave";

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

// 初始扫描 + MutationObserver 持续监控(Nodes 2.0 懒渲染按钮), 全局只跑一次
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

  // 按钮行更高
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

app.registerExtension({
  name: "FallingTS.PreviewAudioSave",

  /**
   * 节点定义注册前钩子: 给 PreviewAudioSave 追加「保存」按钮。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 追加「保存」按钮并套用大气样式。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      /**
       * 「保存」按钮点击处理: 把文件名/格式/质量 POST 到后端, 后端用缓存的音频直接写 output
       * ({filename_prefix}.{format}, 同名覆盖, 无序号), 【不重跑工作流】。
       * 回调参数: 无(addWidget 内部触发)。
       * @returns {Promise<void>} 保存请求异步流程
       */
      node.addWidget("button", "保存", null, async () => {
        const getWidget = (name) => node.widgets?.find((w) => w.name === name)?.value;
        // filename_prefix 是否被上游连线(如 MDTable 的 ID 列): 连线时 widget 只是占位符,
        // 需后端用 execute 时实际接收到的值, 否则保存会落到占位符 "audio"
        const prefixLinked =
          node.inputs?.find((i) => i.name === "filename_prefix")?.link != null;
        // filename_suffix 同前缀: 连线时用 execute 实际接收值, 手动输入用 widget 值
        const suffixLinked =
          node.inputs?.find((i) => i.name === "filename_suffix")?.link != null;
        const fmtVal = getWidget("format");
        try {
          const resp = await fetch(`/preview-audio/save/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_prefix: getWidget("filename_prefix") ?? "audio",
              filename_prefix_linked: prefixLinked,
              filename_suffix: getWidget("filename_suffix") ?? "",
              filename_suffix_linked: suffixLinked,
              format: fmtVal?.format ?? "flac",
              quality: fmtVal?.quality ?? "128k",
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
    };
  },
});
