// FallingTS 多图合成前端联动 (参照 switch.js / fanout.js 的 total 驱动机制):
// - total 张数 (最少 1, 不设上限, 端口口径封顶 MAX_SLOTS=64) 决定左侧图端口 图1..图N (内部名 image1..imageN);
// - 标注是节点内 label1..labelN 表单文本框 (后端 required 文本控件), 按 total 自动扩充/收缩:
//   超出 total 的文本框被移除 (不进入提交载荷), 新增加自动补齐 (默认空串 = 不画);
// - 左侧未连接的图端口 = 该格底色空格占位; 标注文本框空串 = 不画;
// - 加载工作流时自动迁移旧版 widgets_values (旧版 7 槽 / 中间版 12 槽 -> 新版基础 4 槽首部,
//   标注文本框紧跟基础槽之后, 前缀序对齐无需特殊处理)。
import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FallingTSImageComposite";
// 图端口/标注文本框数量上限 (对齐后端 MAX_TOTAL); total 控件本身不设上限
const MAX_SLOTS = 64;
const DEFAULT_TOTAL = 4;

/**
 * 读取当前 total: 以 total widget 值为准; widget 尚未就绪/值非法时回退默认。
 * 最小 1, 不设上限, 端口与文本框口径封顶 MAX_SLOTS。
 * @param {LGraphNode} node
 * @returns {number} 有效张数 (>= 1, <= MAX_SLOTS)
 */
function getTotal(node) {
  const w = node.widgets?.find((x) => x.name === "total");
  const v = w != null ? Math.trunc(Number(w.value)) : NaN;
  return Math.max(1, Math.min(MAX_SLOTS, Number.isFinite(v) ? v : DEFAULT_TOTAL));
}

/**
 * 判断输入槽是否为动态图端口 (image1..image64; 排除控件转化的槽)。
 * @param {object} input 输入槽
 * @returns {boolean} 是否图端口
 */
function isImageInput(input) {
  return !input.widget && /^image\d+$/.test(input.name ?? "");
}

/** 判断 widget 是否为动态标注文本框 (label1..label64)。 */
function isLabelWidget(widget) {
  return /^label\d+$/.test(widget.name ?? "");
}

/** 收集当前动态图端口 (升序)。 */
function imageInputsOf(node) {
  return (node.inputs ?? []).filter(isImageInput);
}

/** 收集当前标注文本框 (数组序)。 */
function labelWidgetsOf(node) {
  return (node.widgets ?? []).filter(isLabelWidget);
}

/**
 * 补一个标注文本框 (type/options 抄现有标注框保持一致; 无模板时用默认 string 控件),
 * 追加到 widgets 尾部并挂中文标题。
 * @param {LGraphNode} node
 * @param {number} k 组号 (1 起)
 */
function addLabelWidget(node, k) {
  const tmpl = labelWidgetsOf(node)[0];
  const options = tmpl?.options ? { ...tmpl.options } : {};
  const w = node.addWidget("string", "label" + k, "", () => {}, options);
  w.label = "标注 " + k;
  return w;
}

/** 移除指定 widget (优先官方 ensureWidgetRemoved, 退回手动 splice)。 */
function dropWidget(node, w) {
  const i = node.widgets.indexOf(w);
  if (i === -1) return;
  if (typeof node.ensureWidgetRemoved === "function") {
    node.ensureWidgetRemoved(w);
  } else {
    w.onRemove?.();
    node.widgets.splice(i, 1);
    node._widgetSlotsDirty = true;
  }
}

/**
 * 按 total 对齐节点形态:
 * - 左侧只保留 image1..imageN 图端口 (超出的从尾部删除, 不足的从尾部补齐, 中文标签 图1..图N);
 * - 标注表单文本框只保留 label1..labelN (超出 total 的被移除而不进提交载荷, 不足的新增补齐),
 *   标题 标注1..标注N;
 * 不变量: widgets 序恒为 [total, font_size, padding, background_color, label1..labelN] 前缀序,
 * 保证保存的 widgets_values 按位置套用仍然对齐。
 * @param {LGraphNode} node
 */
function syncNode(node) {
  ensureNodeShape(node, getTotal(node));
}

/**
 * 按给定 total 对齐图端口与标注文本框 (syncNode 与加载期预对齐共用内部实现)。
 * 契约: 端口/控件维持 [image1..imageN | total, font_size, padding, background_color, label1..labelN] 顺序,
 * 与保存的 widgets_values 逐位对应, 保证按位置套用值时每一格都能命中已有控件。
 * @param {LGraphNode} node
 * @param {number} total 目标数量 (调用方已夹到 1..MAX_SLOTS)
 */
function ensureNodeShape(node, total) {

  // 1) 左侧图端口: image1..imageN (尾部多余的逐个移除, 不足的从尾部补齐)
  while (imageInputsOf(node).length > total) {
    const tail = node.inputs[node.inputs.length - 1];
    const idx = isImageInput(tail)
      ? node.inputs.length - 1
      : [...node.inputs].map((x, i) => (isImageInput(x) ? i : -1)).filter((i) => i !== -1).pop();
    node.removeInput(idx);
  }
  while (imageInputsOf(node).length < total) {
    const k = imageInputsOf(node).length + 1;
    node.addInput("image" + k, "IMAGE");
  }
  imageInputsOf(node).forEach((inp, i) => { inp.localized_name = "图 " + (i + 1); });

  // 0) 清理旧版「images 批量输入」残留槽 (后端已只支持逐格 image1..imageN):
  //    无链接的任意阶段直接移除; 有链接的留给宏任务(syncNode)经 removeInput 安全断开。
  //    先收集(倒序遍历移除, 避免索引错乱), 再统一 removeInput。
  const legacyImages = [];
  for (let i = (node.inputs ?? []).length - 1; i >= 0; i--) {
    const inp = node.inputs[i];
    if (inp && inp.name === "images" && !inp.widget && (inp.link ?? null) === null) legacyImages.push(i);
  }
  for (const idx of legacyImages) node.removeInput(idx);

  // 2) 标注表单文本框: label1..labelN (尾部多余移除, 尾部不足补齐)
  let lw = labelWidgetsOf(node);
  while (lw.length > total) {
    dropWidget(node, lw[lw.length - 1]);
    lw = labelWidgetsOf(node);
  }
  while (labelWidgetsOf(node).length < total) {
    addLabelWidget(node, labelWidgetsOf(node).length + 1);
  }
  labelWidgetsOf(node).forEach((w, i) => { w.label = "标注 " + (i + 1); });

  node.setDirtyCanvas?.(true, true);
}

/**
 * 高度收回/扩展到自然高度 (宽度保留用户设置)。
 * 后端声明全部 64 组端口/文本框, 构造器会把初始尺寸撑满, 同步裁剪后需收回多余高度;
 * total 增大补控件时同样需要扩展到位。
 * @param {LGraphNode} node
 */
function fitHeight(node) {
  const natural = node.computeSize?.();
  if (!natural || !node.size) return;
  if (Math.abs(node.size[1] - natural[1]) > 1) {
    node.setSize([node.size[0], natural[1]]);
  }
}

app.registerExtension({
  name: "FallingTS.Composite",

  /**
   * 节点定义注册前钩子: 给 FallingTSImageComposite 绑定 total -> 图端口/标注文本框增删联动。
   * @param {Function} nodeType 节点类型构造函数 (原型上挂方法)
   * @param {object} nodeData 节点定义数据 (来自 /object_info)
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: total 变化时同步图端口与标注文本框; 加载工作流时按保存的值对齐。
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const node = this;

      // 主链路: widget 值变化 (拖 spinner/输入/程序赋值) 都会经过 widget.callback
      const bindTotalWidget = () => {
        const tw = node.widgets?.find((w) => w.name === "total");
        if (!tw || tw.__ftsBound) return;
        tw.__ftsBound = true;
        const origCb = tw.callback;
        tw.callback = function (...cbArgs) {
          const cbOut = origCb?.apply(this, cbArgs);
          syncNode(node);
          fitHeight(node);
          return cbOut;
        };
      };
      bindTotalWidget();

      const onWidgetChanged = nodeType.prototype.onWidgetChanged;
      /** 节点级 widget 变化钩子: total 变化时同步端口/文本框 (双调用约定兼容)。 */
      // 新前端: (name, value, oldValue, widget); 旧版: (widget, value)
      nodeType.prototype.onWidgetChanged = function (name, value, oldValue, widget) {
        const out = onWidgetChanged?.apply(this, arguments);
        const nm = typeof name === "string" ? name : name?.name;
        if (nm === "total") {
          syncNode(this);
          fitHeight(this);
        }
        return out;
      };

      // 加载/还原工作流: configure 前先做旧格式迁移, 末尾按保存的 total 再对齐一次
      const prevOnConfigure = node.onConfigure;
      /**
       * configure 钩子: 兼容两种历史 widgets_values 格式:
       * - 旧版 7 槽 (label1..4/font_size/padding/bg): 标注成为表单文本框, 取尾部三槽并在首部插入 total=4
       *   (旧标注文案舍弃: 未填写 = 不画);
       * - 中间版 12 槽 (total + 旧 label1..8 + font/padding/bg): 取首部 total 与尾部三槽。
       * 其余格式 (新版基础 4 槽 / 基础 4 槽 + N 个标注文本框, 前缀序) 按位置直接套用, 无需迁移。
       */
      node.onConfigure = function (info) {
        const wv = info?.widgets_values;
        if (Array.isArray(wv) && wv.length === 7) {
          const [, , , , fs, pd, bg] = wv;
          info.widgets_values = [DEFAULT_TOTAL, fs, pd, bg];
        } else if (Array.isArray(wv) && wv.length === 12) {
          const [tt, , , , , , , , , fs, pd, bg] = wv;
          info.widgets_values = [tt ?? DEFAULT_TOTAL, fs, pd, bg];
        }
        // 关键时序: 先按保存的 total 预对齐端口/标注文本框, 再由 prevOnConfigure 套值——
        // 创建时构造器已把控件裁到默认 total (4), 若直接按位置套用 widgets_values,
        // 超出默认数量的标注值会因没有对应文本框而被丢弃, 且 image5..imageN 图端口尚不存在,
        // 引用高编号端口的连线无法挂接 (表现为输入连线缺失、标注文本缺失)。
        const savedHead = Array.isArray(info?.widgets_values) ? info.widgets_values[0] : Number.NaN;
        const savedTotal = Math.trunc(Number(savedHead));
        if (Number.isFinite(savedTotal) && savedTotal >= 1) {
          ensureNodeShape(this, Math.max(1, Math.min(MAX_SLOTS, savedTotal)));
        }
        prevOnConfigure?.call(this, info);
        syncNode(this);
        // 新版前端在调用 onConfigure 之前就已按位置套完 widgets_values, 彼时形状仍是默认裁减态,
        // 超出默认数量的标注值已被丢弃; 形状对齐后再按位置重套一次, 确保 label5..labelN 命中控件。
        const wvFinal = Array.isArray(info?.widgets_values) ? info.widgets_values : [];
        if (wvFinal.length) {
          const ws = (this.widgets ?? []).filter((w) => w && w.serialize !== false);
          ws.forEach((w, i) => {
            if (i < wvFinal.length && wvFinal[i] !== undefined) w.value = wvFinal[i];
          });
        }
        fitHeight(this);
      };

      syncNode(node);
      fitHeight(node);
      // 刚创建时 widget store 可能还没注册完成, 下一 tick 再绑定并对齐一次
      setTimeout(() => {
        bindTotalWidget();
        syncNode(node);
        fitHeight(node);
      }, 0);
      return result;
    };
  },
});
