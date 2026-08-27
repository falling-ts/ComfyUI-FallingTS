// FallingTS 多图合成前端联动 (参照 switch.js / fanout.js 的 total 驱动机制):
// - total 张数 (最少 1, 最多 8) 决定左侧输入端口: 图1..图8 / 标注1..标注8 (image_i 与 label_i 交错排列);
// - 未启用的端口被删除, 不进入提交载荷; 标注可连线 (未连接 = 默认标注, 空串 = 不画);
// - 加载工作流时自动迁移旧版 widgets_values (旧版 7 槽 / 中间版 12 槽 -> 新版 4 槽: total/font_size/padding/bg)。
import { app } from "../../scripts/app.js";

const NODE_TYPE = "FallingTSImageComposite";
const MAX_SLOTS = 64; // 端口与合成上限 (对齐后端 MAX_TOTAL); total 控件本身不设上限
const DEFAULT_TOTAL = 4;

/**
 * 读取当前 total: 以 total widget 值为准; widget 尚未就绪/值非法时回退默认。
 * 最小 1, 不设上限, 端口数封顶 MAX_SLOTS。
 * @param {LGraphNode} node
 * @returns {number} 有效张数 (>= 1, 端口口径 <= MAX_SLOTS)
 */
function getTotal(node) {
  const w = node.widgets?.find((x) => x.name === "total");
  const v = w != null ? Math.trunc(Number(w.value)) : NaN;
  return Math.max(1, Math.min(MAX_SLOTS, Number.isFinite(v) ? v : DEFAULT_TOTAL));
}

/**
 * 按 total 对齐节点输入端口: image_i/label_i 成对增减 (未使用的端口被删除, 不进入提交载荷), 并按序刷新中文标签。
 * @param {LGraphNode} node 多图合成节点对象
 * @returns {void}
 */
function syncPorts(node) {
  const total = getTotal(node);
  const want = total * 2;
  while ((node.inputs?.length ?? 0) > want) {
    node.removeInput(node.inputs.length - 1);
  }
  while ((node.inputs?.length ?? 0) < want) {
    const k = Math.floor(node.inputs.length / 2) + 1;
    node.addInput(`image${k}`, "IMAGE");
    node.addInput(`label${k}`, "STRING");
  }
  for (let i = 0; i < want; i += 2) {
    const k = i / 2 + 1;
    node.inputs[i].localized_name = "图 " + k;
    node.inputs[i + 1].localized_name = "标注 " + k;
  }
  node.setDirtyCanvas?.(true, true);
}

/**
 * 节点高度收回自然高度 (只缩不扩: 用户手动拉高的高度保留)。
 * 后端声明 MAX_SLOTS 组输入端口, 新建节点时构造器先把全部端口加上并把初始高度撑满;
 * syncPorts 按 total 删掉多余端口后需把多余高度收回, 否则新建节点异常高大。
 * 仅新建时生效 (onNodeCreated): 加载工作流时 configure 恢复保存的高度, 不受影响。
 * @param {LGraphNode} node 多图合成节点对象
 * @returns {void}
 */
function fitHeight(node) {
  const natural = node.computeSize?.();
  if (!natural || !node.size) return;
  if (node.size[1] > natural[1]) {
    node.setSize([node.size[0], natural[1]]);
  }
}

app.registerExtension({
  name: "FallingTS.Composite",

  /**
   * 节点定义注册前钩子: 给 FallingTSImageComposite 绑定 total -> 图/标注端口增删联动。
   * @param {Function} nodeType 节点类型构造函数 (原型上挂方法)
   * @param {object} nodeData 节点定义数据 (来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: total 变化时同步 image_i/label_i 端口; 加载工作流时按保存的值对齐。
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const node = this;

      // 主链路: 新旧前端 widget 值变化(拖 spinner/输入/程序赋值)都会触发 widget.callback
      const bindTotalWidget = () => {
        const tw = node.widgets?.find((w) => w.name === "total");
        if (!tw || tw.__ftsBound) return;
        tw.__ftsBound = true;
        const origCb = tw.callback;
        tw.callback = function (...cbArgs) {
          const cbOut = origCb?.apply(this, cbArgs);
          syncPorts(node);
          fitHeight(node);
          return cbOut;
        };
      };
      bindTotalWidget();

      const onWidgetChanged = nodeType.prototype.onWidgetChanged;
      /** 节点级 widget 变化钩子: total 变化时同步端口。 */
      // 调用约定: 新前端 (name, value, oldValue, widget), name 为字符串;
      // 旧版 (widget, value), 首参为 widget 对象
      nodeType.prototype.onWidgetChanged = function (name, value, oldValue, widget) {
        const out = onWidgetChanged?.apply(this, arguments);
        const nm = typeof name === "string" ? name : name?.name;
        if (nm === "total") {
          syncPorts(this);
        }
        return out;
      };

      // 加载/还原工作流: configure 前先做旧格式迁移, 末尾按保存的 total 再对齐一次
      const prevOnConfigure = node.onConfigure;
      /**
       * configure 钩子: 兼容历史两种旧版 widgets_values 格式:
       * - 旧版 7 槽 (label1..4/font_size/padding/bg): 新版首部为 total, 标注成为可连线端口,
       *   取尾部三槽并在首部插入 total=4 (旧标注文案舍弃, 标注端口未连接 = 默认标注);
       * - 中间版 12 槽 (total + label1..8 + font/padding/bg): 取 total 与尾部三槽。
       * 之后由基类按新顺序套用 (total/font_size/padding/background_color, 共 4 槽)。
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
        prevOnConfigure?.call(this, info);
        syncPorts(this);
        fitHeight(this);
      };

      syncPorts(node);
      fitHeight(node);
      // 节点刚创建时 widgetValue store 可能还没注册完成, 下一 tick 再同步一次
      setTimeout(() => {
        bindTotalWidget();
        syncPorts(node);
        fitHeight(node);
      }, 0);
      return result;
    };
  },
});
