/**
 * PreviewImageSave 前端: 底部控件(文件名/格式/位深/色彩空间) + 「保存」按钮。
 *
 * 布局(自上而下): 图片展示区域(节点本体) → filename_prefix/format/bit_depth/input_color_space
 * 四个控件(INPUT_TYPES 声明的普通 widget) → 「保存」按钮(addWidget 追加)。
 *
 * 行为:
 * - format 变化时按格式联动 bit_depth / input_color_space 的合法选项(png→8/16bit+sRGB,
 *   exr→32bit float+sRGB/HDR/linear), 与 SaveImageAdvanced 的 DynamicCombo 一致;
 * - 点「保存」: 把 文件名/格式/位深/色彩空间 POST 到 /preview-image/save/{id},
 *   后端用 execute 时缓存的预览数据直接写 output(同名覆盖、无序号) ——
 *   【不触发任何工作流重跑】, 保存的是当前画面上显示的这张图。
 */

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "PreviewImageSave";

/**
 * 给「保存」按钮 widget 应用大气样式: 更高、渐变底色、圆角、阴影、hover 高亮。
 *
 * @param {LGraphNode} node 节点对象(其 widgets 里含 type === "button" 的保存按钮)
 * @returns {void}
 */
function styleSaveButton(node) {
  const btn = node.widgets?.find((w) => w.type === "button");
  if (!btn) return;

  // 布局行更高
  btn.computedHeight = 42;
  node.setDirtyCanvas(true, true);

  const apply = () => {
    const el = btn.element;
    if (!el) return;
    el.style.height = "40px";
    el.style.width = "100%";
    el.style.boxSizing = "border-box";
    el.style.margin = "6px 8px";
    el.style.background = "linear-gradient(135deg,#6a5cff 0%,#9d5cff 100%)";
    el.style.color = "#ffffff";
    el.style.fontSize = "16px";
    el.style.fontWeight = "700";
    el.style.letterSpacing = "2px";
    el.style.borderRadius = "10px";
    el.style.border = "1px solid rgba(255,255,255,.18)";
    el.style.cursor = "pointer";
    el.style.boxShadow = "0 3px 12px rgba(106,92,255,.4)";
    el.style.transition = "all .25s ease";
    if (!el._styled) {
      el._styled = true;
      el.addEventListener("mouseenter", () => {
        el.style.background = "linear-gradient(135deg,#7b6dff 0%,#ad6dff 100%)";
        el.style.boxShadow = "0 6px 20px rgba(106,92,255,.55)";
        el.style.transform = "translateY(-1px)";
      });
      el.addEventListener("mouseleave", () => {
        el.style.background = "linear-gradient(135deg,#6a5cff 0%,#9d5cff 100%)";
        el.style.boxShadow = "0 3px 12px rgba(106,92,255,.4)";
        el.style.transform = "";
      });
    }
  };

  // 节点每次绘制后应用(按钮 element 可能重建)
  const onDraw = node.onDrawForeground;
  node.onDrawForeground = function (...args) {
    onDraw?.apply(this, args);
    apply();
  };
  apply();
}

// 各格式合法的 位深 / 色彩空间(与后端 _encode_image 支持的组合一致)
const FORMAT_OPTIONS = {
  png: { bit_depth: ["8-bit", "16-bit"], colorspace: ["sRGB"] },
  exr: { bit_depth: ["32-bit float"], colorspace: ["sRGB", "HDR", "linear"] },
};

/**
 * 读取节点 format widget 的当前值。
 *
 * @param {LGraphNode} node 预览保存节点对象
 * @returns {string} 格式("png" / "exr")
 */
function getFormatValue(node) {
  const w = node.widgets?.find((x) => x.name === "format");
  return w?.value ?? "png";
}

/**
 * 按 format 联动 bit_depth / input_color_space 的合法选项;
 * 当前选中值不在新选项里时自动重置为第一项。
 *
 * @param {LGraphNode} node 预览保存节点对象
 * @returns {void}
 */
function syncFormatDependentWidgets(node) {
  const fmt = getFormatValue(node);
  const opts = FORMAT_OPTIONS[fmt] ?? FORMAT_OPTIONS.png;
  const applyTo = (name, values) => {
    const w = node.widgets?.find((x) => x.name === name);
    if (!w) return;
    w.options = { ...(w.options || {}), values: () => [...values] };
    if (!values.includes(w.value)) {
      w.value = values[0];
      w.callback?.(w.value);
    }
  };
  applyTo("bit_depth", opts.bit_depth);
  applyTo("input_color_space", opts.colorspace);
  node.setDirtyCanvas(true, true);
}

app.registerExtension({
  name: "FallingTS.PreviewImageSave",

  /**
   * 节点定义注册前钩子: 给 PreviewImageSave 绑定 format 联动 + 追加「保存」按钮。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 包装 format callback 做选项联动, 追加「保存」按钮。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      const fmtWidget = node.widgets?.find((w) => w.name === "format");
      if (fmtWidget) {
        const cb = fmtWidget.callback;
        /** format 变化回调: 同步位深/色彩空间合法选项。 */
        fmtWidget.callback = function (v) {
          cb?.call(this, v);
          syncFormatDependentWidgets(node);
        };
      }

      /**
       * 「保存」按钮点击处理: 把控件配置 POST 到后端, 后端用缓存的预览数据直接写 output
       * (同名覆盖, 无序号), 【不重跑工作流】。
       * 回调参数: 无(addWidget 内部触发)。
       * @returns {Promise<void>} 保存请求异步流程
       */
      node.addWidget("button", "保存", null, async () => {
        const getWidget = (name) =>
          node.widgets?.find((w) => w.name === name)?.value;
        // filename_prefix 是否被上游连线(如 MDTable 的 ID 列): 连线时 widget 只是占位符,
        // 需后端用 execute 时实际接收到的值, 否则保存会落到占位符 "preview"
        const prefixLinked =
          node.inputs?.find((i) => i.name === "filename_prefix")?.link != null;
        try {
          const resp = await fetch(`/preview-image/save/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_prefix: getWidget("filename_prefix") ?? "preview",
              filename_prefix_linked: prefixLinked,
              format: getWidget("format") ?? "png",
              bit_depth: getWidget("bit_depth") ?? "8-bit",
              input_color_space: getWidget("input_color_space") ?? "sRGB",
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

      syncFormatDependentWidgets(node);
      styleSaveButton(node);
    };
  },
});
