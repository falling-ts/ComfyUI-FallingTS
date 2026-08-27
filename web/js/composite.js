// FallingTS 多图合成前端联动 (参考本插件 switch/route 的 total 动态端口模式):
// - total = 图片张数 (widget, INT, 最少 1, 最多 MAX_TOTAL=8), 按 total 动态增删 image_i 输入端口;
// - label1..label8 / font_size / padding / background_color 均为纯 widget (无 socket), 常驻显示;
// - 后端声明 MAX_TOTAL 个 image_i optional 端口, 本前端中未启用的 image_i 端口被删除, 不进入 prompt。
import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FallingTSImageComposite";
const MAX_TOTAL = 8;
const DEFAULT_TOTAL = 4;

/**
 * 读取节点 total widget 的当前张数, 非法值回退默认, 再裁到 [1, MAX_TOTAL]。
 *
 * @param {LGraphNode} node 多图合成节点对象
 * @returns {number} 有效张数 (1 ~ MAX_TOTAL)
 */
function getTotal(node) {
  const w = node.widgets?.find((w) => w.name === "total");
  let v = w ? Math.floor(Number(w.value)) : DEFAULT_TOTAL;
  if (!Number.isFinite(v)) v = DEFAULT_TOTAL;
  return Math.min(MAX_TOTAL, Math.max(1, v));
}

/**
 * 按 total 对齐 image_i 输入端口: 保留 image_1..image_total, 删除多余的 image_i 端口。
 * label 等为纯 widget 不参与端口管理; 未启用的 image_i 端口被删除, 不进入 prompt。
 *
 * @param {LGraphNode} node 多图合成节点对象
 * @returns {void}
 */
function syncPorts(node) {
  const total = getTotal(node);

  // image_i 端口: 逐个检查 node.inputs, 名称 image_k 且 k>total 的移除,
  // 缺失的补齐 (load 后端口可能少于 total)。
  const inputs = [...(node.inputs ?? [])];
  for (const inp of inputs) {
    const mm = /^image_(\d+)$/.exec(inp.name ?? "");
    if (mm && Number(mm[1]) > total) {
      node.removeInput(inputs.indexOf(inp));
    }
  }
  while ((node.inputs?.length ?? 0) < total) {
    const k = node.inputs.length + 1;
    node.addInput("image_" + k, "IMAGE");
  }
  for (const inp of node.inputs ?? []) {
    const mm = /^image_(\d+)$/.exec(inp.name ?? "");
    if (mm) inp.localized_name = "\u56fe " + mm[1];
  }

  node.setDirtyCanvas?.(true, true);
}

/**
 * 节点高度收回自然高度 (只缩不扩: 用户手动拉高的高度保留)。
 *
 * 后端声明 MAX_TOTAL=8 个 image_i 端口, 新建节点时构造器先把它们全部加上
 * (初始高度偏大), syncPorts 按 total 删掉多余端口后需收回多余高度,
 * 否则新建节点异常高大。仅新建时生效 (onNodeCreated): 加载工作流时
 * configure 恢复保存的高度, 不受影响。
 *
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
   * 节点定义注册前钩子: 给 FallingTSImageComposite 绑定 total -> 端口增删联动。
   *
   * @param {Function} nodeType 节点类型构造函数 (原型上挂方法)
   * @param {object} nodeData 节点定义数据 (来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: total 变化时同步端口; 加载工作流时按保存的 widgets_values 对齐。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      const totalWidget = node.widgets?.find((w) => w.name === "total");
      if (totalWidget) {
        const cb = totalWidget.callback;
        /** total widget 回调: 张数变化后重新对齐 image_i 端口。 */
        totalWidget.callback = function (v) {
          cb?.call(this, v);
          syncPorts(node);
        };
      }

      // 加载/还原工作流: configure 前先做旧格式迁移, 末尾按保存的 total 再对齐一次
      const prevOnConfigure = node.onConfigure;
      /**
       * configure 钩子: 兼容旧版 7 项 widgets_values (label1..4/font_size/padding/bg)
       * —— 新版首项为 total, 旧数组直接按位套用会把标签错移到 total 等后续槽位。
       * 识别特征: 恰好 7 项 (新版恒为 12 项), 在基类应用前插入 total=4 并补空
       * 标注 5..8, 之后由基类按新顺序套用。
       */
      node.onConfigure = function (info) {
        const wv = info?.widgets_values;
        if (Array.isArray(wv) && wv.length === 7) {
          const [l1, l2, l3, l4, fs, pd, bg] = wv;
          info.widgets_values = [DEFAULT_TOTAL, l1, l2, l3, l4, "", "", "", fs, pd, bg];
        }
        prevOnConfigure?.call(this, info);
        syncPorts(node);
      };

      syncPorts(node);
      fitHeight(node);
    };
  },
});
