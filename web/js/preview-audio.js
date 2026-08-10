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
 * Nodes 2.0 渲染模式: 保存按钮由 WidgetButton 组件渲染为 DOM <button aria-label="保存">,
 * 不走 LiteGraph canvas widget(旧版 canvas 已由 styleSaveButton 处理)。
 * 这里注入全局 CSS 统一美化(更高、渐变、圆角、hover)。
 *
 * @returns {void}
 */
function injectSaveButtonStyle() {
  if (document.getElementById("fallingts-save-btn-style")) return;
  const style = document.createElement("style");
  style.id = "fallingts-save-btn-style";
  style.textContent =
    'button[aria-label="保存"]{height:40px!important;min-height:40px!important;' +
    'padding:8px 12px!important;background:linear-gradient(135deg,#6a5cff 0%,#9d5cff 100%)!important;' +
    'color:#fff!important;border-radius:8px!important;font-size:15px!important;' +
    'font-weight:700!important;letter-spacing:1px!important;' +
    'box-shadow:0 2px 8px rgba(106,92,255,.35)!important;transition:all .2s ease!important}' +
    'button[aria-label="保存"]:hover{background:linear-gradient(135deg,#7b6dff 0%,#ad6dff 100%)!important;' +
    'box-shadow:0 4px 14px rgba(106,92,255,.5)!important;transform:translateY(-1px)!important}';
  document.head.appendChild(style);
}
injectSaveButtonStyle();

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
  btn.computedHeight = 42;

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
    // 阴影层
    drawRoundRect(ctx, 6, y + 6, W - 12, H - 8, 10);
    ctx.fillStyle = "rgba(0,0,0,.22)";
    ctx.fill();
    // 渐变主体
    drawRoundRect(ctx, 6, y + 3 + dy, W - 12, H - 8, 10);
    const g = ctx.createLinearGradient(0, y, 0, y + H);
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
    ctx.fillText("保存", W / 2, y + H / 2 + 1 + dy);
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
        const fmtVal = getWidget("format");
        try {
          const resp = await fetch(`/preview-audio/save/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_prefix: getWidget("filename_prefix") ?? "audio",
              filename_prefix_linked: prefixLinked,
              format: fmtVal?.format ?? "flac",
              quality: fmtVal?.quality ?? "128k",
            }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            alert(data?.message ?? "保存失败");
            return;
          }
          alert(data?.message ?? "已保存");
        } catch (err) {
          console.error("[FallingTS] 保存失败:", err);
          alert("保存失败: 无法连接后端");
        }
      });

      styleSaveButton(node);
    };
  },
});
