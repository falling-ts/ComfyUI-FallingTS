/**
 * PreviewImageSave 前端: 底部控件(文件名/格式/位深/色彩空间) + 「保存」按钮。
 *
 * 布局(自上而下): 图片展示区域(节点本体) → filename_prefix/format/bit_depth/input_color_space
 * 四个控件(INPUT_TYPES 声明的普通 widget) → 「保存」按钮(addWidget 追加)。
 *
 * 行为:
 * - format 变化时按格式联动 bit_depth / input_color_space 的合法选项(png→8/16bit+sRGB,
 *   exr→32bit float+sRGB/HDR/linear), 与 SaveImageAdvanced 的 DynamicCombo 一致;
 * - 点「保存」: 先 POST /preview-image/save/{id} 让后端标记该节点"已请求保存",
 *   再 app.queuePrompt(0,1,[节点id]) 对本节点做 partial 重跑 —— 节点 execute 检测到标记
 *   即按控件配置写 output(同名覆盖、无序号), 并始终重新生成 temp 预览。
 */

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "PreviewImageSave";

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
       * 「保存」按钮点击处理: 标记后端 → partial 重跑本节点 → execute 写 output(覆盖, 无序号)。
       * 回调参数: 无(addWidget 内部触发)。
       * @returns {Promise<void>} 整段"标记 + 重跑"异步流程
       */
      node.addWidget("button", "保存", null, async () => {
        /* 1. 后端标记"已请求保存"(IS_CHANGED 变化 → 本节点将重新执行) */
        try {
          const resp = await fetch(`/preview-image/save/${node.id}`, { method: "POST" });
          if (!resp.ok) {
            const data = await resp.json().catch(() => null);
            alert(data?.message ?? "保存失败");
            return;
          }
        } catch (err) {
          console.error("[FallingTS] 保存失败:", err);
          alert("保存失败: 无法连接后端");
          return;
        }

        /* 2. partial 重跑本节点(标准队列流程, 有节点流动动画) */
        try {
          await app.queuePrompt(0, 1, [String(node.id)]);
        } catch (err) {
          console.error("[FallingTS] 保存重跑失败:", err);
          return;
        }
        app.graph.setDirtyCanvas(true, false);
      });

      syncFormatDependentWidgets(node);
    };
  },
});
