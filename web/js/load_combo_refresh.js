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
 * 给节点上的 combo widget 装上"点开即最新"。
 *
 * 同一个 widget 只装一次; 没有 remote(即没有 refresh 方法)的普通 combo 直接跳过。
 *
 * @param {LGraphNode} node 节点
 * @param {string} widgetName combo widget 的名字(image / video)
 * @returns {void}
 */
export function armComboRefresh(node, widgetName) {
  const widget = node.widgets?.find((w) => w.name === widgetName);
  if (!widget || widget._fallingtsComboArmed) return;
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
