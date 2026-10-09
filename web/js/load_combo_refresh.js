/**
 * FallingTS 共用: 让 combo 下拉的候选"永远是最新的"。
 *
 * 为什么需要它 —— 加载节点的候选由 remote 路由喂, 但前端只在三个时机拉:
 * ① 节点类型注册(NodeDef 里的 options 是后端现扫的快照)、② 点「refresh」按钮、
 * ③ 跑完流程的 Auto-refresh。**"点开下拉"这一下, 前端不会重新拉我们的候选**
 * (WidgetSelectDropdown 的 handleIsOpenUpdate 只刷新「已保存」那份资产列表)。
 * 于是刚出现的子目录/新文件必须手动点一次刷新才进列表, 用户看到的就是"第一次点开
 * 不显示子目录资源"。
 *
 * 这里补三个时机:
 * 1. 节点创建 / 加载工作流后立刻拉一次 —— 堵掉"第一次点开"之前的空窗;
 * 2. 在节点上按下鼠标时拉一次 —— 贴着"点开下拉"那一下;
 * 3. 页面可见时每 COMBO_POLL_MS 兜底拉一次 —— 目录里新出现的资源无需任何操作即进候选。
 *
 * 前提: 节点不给 remote 设 control_after_refresh(两个加载节点都没设), 因此
 * widget.refresh() 只换候选列表, 绝不会改写用户已经选好的值。
 */

// 兜底轮询间隔: 4 秒既能让"点开即是新的", 又不至于把目录扫得太频繁
const COMBO_POLL_MS = 4000;

/**
 * 修掉"远端候选还没进缓存时 values 退化成字符串"的上游缺陷。
 *
 * 带 remote 的 combo 由 addComboWidget → bindDynamicValuesOption 把 options.values
 * 换成访问器对: get 返回 useRemoteWidget.getValue(), 而它在候选还没进缓存时给的是
 * getDefaultValue() —— **spec.options[0] 那个字符串**(只有 set 才写回数组)。Vue 侧
 * computeProcessedWidgets 用对象展开合并 options({...r.options}), 会当场把 getter
 * **取一次值**, 于是候选没到位时那个字符串被拍进 widgets 描述符;
 * useWidgetSelectItems 的 inputItems 再判 Array.isArray(values) 为假 ⇒ 候选全空,
 * 下拉只剩"当前值不在候选里"补出来的那一项。
 *
 * 实测 0016_建模拆图(两个加载节点): 先渲染的那个下拉只显示 1 项(冻结在
 * 0010_灰度遮罩/00001_陈落换装.png, 正是 /object_info 快照的 options[0]), 后渲染的
 * 因为候选已进缓存而正常显示 13 项 —— 所以"只有一个加载节点"的工作流必中, 有两个时
 * 是第一个中招。
 *
 * 兜底加在访问器上: get 拿到的不是非空数组时, 依次回退到 ① 最后一次见到的真数组、
 * ② 注册时从 nodeData 抄下来的静态候选(/object_info 现扫, 见 load_image.js 传入)。
 *
 * @param {object} widget combo widget
 * @param {string[]} staticValues 注册时抄下的静态候选(可为空)
 * @returns {void}
 */
function repairRemoteValues(widget, staticValues) {
  if (widget._fallingtsValuesFixed) return;
  const descriptor = Object.getOwnPropertyDescriptor(widget.options, "values");
  if (!descriptor?.get || !descriptor?.set) return;
  widget._fallingtsValuesFixed = true;

  const fallback = Array.isArray(staticValues) && staticValues.length ? staticValues.slice() : null;
  let last = fallback;
  Object.defineProperty(widget.options, "values", {
    configurable: true,
    enumerable: true,
    get() {
      const value = descriptor.get.call(this);
      if (Array.isArray(value) && value.length) {
        last = value;
        return value;
      }
      return last ?? value;
    },
    set(value) {
      if (Array.isArray(value) && value.length) last = value;
      descriptor.set.call(this, value);
    },
  });
}

/**
 * 给节点上的 combo widget 装上"点开即最新"。
 *
 * 同一个 widget 只装一次; 没有 remote(即没有 refresh 方法)的普通 combo 直接跳过。
 *
 * @param {LGraphNode} node 节点
 * @param {string} widgetName combo widget 的名字(image / video)
 * @param {string[]} [staticValues] 注册时从 nodeData 抄下的静态候选(喂给 repairRemoteValues)
 * @returns {void}
 */
export function armComboRefresh(node, widgetName, staticValues) {
  const widget = node.widgets?.find((w) => w.name === widgetName);
  if (!widget || widget._fallingtsComboArmed) return;
  repairRemoteValues(widget, staticValues);
  if (typeof widget.refresh !== "function") return;
  widget._fallingtsComboArmed = true;

  const kick = () => {
    if (node.removed) return;
    try {
      widget.refresh();
    } catch (err) {
      console.warn("[FallingTS] 刷新下拉候选失败:", err);
    }
  };

  // 1) 创建/加载工作流后立刻拉一次
  setTimeout(kick, 0);

  // 2) 在节点上按下鼠标(点开下拉前的那一下)
  const prevMouseDown = node.onMouseDown;
  node.onMouseDown = function () {
    kick();
    return prevMouseDown?.apply(this, arguments);
  };

  // 3) 兜底轮询: 页面不可见 / 节点已删除时停手
  const timer = setInterval(() => {
    if (document.hidden || node.removed) return;
    kick();
  }, COMBO_POLL_MS);

  const prevRemoved = node.onRemoved;
  node.onRemoved = function () {
    clearInterval(timer);
    return prevRemoved?.apply(this, arguments);
  };
}
