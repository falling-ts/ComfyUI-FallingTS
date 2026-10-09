/**
 * FallingTS.LoadImage 前端扩展: 只对 FallingTSLoadImage 生效。三件事:
 *
 * 1. 「序列号 / 刷新序列号」—— 与「加载视频」同一套: 编号 = 该工作流产物目录里已有
 *    "数字_" 命名的文件的最大编号 + 1(目录不存在/为空为 00001), 可手改, 按钮随时重算。
 *    编号与目录口径都由后端 output_subdir 解析(有 md 数据表用表文件名, 没有才用工作流名)。
 *
 * 2. 下拉候选"点开即最新" —— 见 load_combo_refresh.js(补上"点开下拉/点节点/每 4 秒"
 *    三个拉取时机; 后端 INPUT_TYPES 里也已经现扫一份候选, 页面加载时列表就是完整的)。
 *
 * 3. 短守护 —— 让"刷新"和"打开工作流"都不再改写已选的子目录资源:
 *    - 刷新(手动点刷新按钮 / 跑完流程后的 Auto-refresh): 后端 remote 配置里不设
 *      control_after_refresh, 前端 useRemoteWidget 的 onRefresh() 直接 no-op, 不需要前端参与;
 *    - 首次加载(打开工作流): useRemoteWidget 的 onFirstLoad 是无条件的, 它只认远端候选
 *      列表, 不分青红皂白把 widget.value 设成候选首项(候选按 mtime 倒序 ⇒ 最近改动的文件)。
 *      上游没有开关可关, 所以在节点 configure 之后开一个短守护窗口: 一旦发现值被换成了
 *      候选首项(且不是工作流里存的那个), 就恢复成工作流存的值。
 *
 * 守护只持续数秒、且只在"值恰好等于候选首项"时动作一次, 因此用户自己在下拉里选第一项
 * 不会被回拨; 窗口之外本扩展完全不管。
 *
 * ⚠️ 若存档值指向的文件已被删除/改名, 这里会保留该值(而不是跳到首项) —— 提交时由后端
 * VALIDATE_INPUTS 报 "Invalid image file", 明确报错好过静默换图。
 */

import { app } from "../../../scripts/app.js";
import { armComboRefresh } from "./load_combo_refresh.js";
import { armComboMenu } from "./load_combo_menu.js";

const NODE_CLASS = "FallingTSLoadImage";
const ROUTE = "/fallingts_load_image";
// 编号显示宽度: 与产物目录的 5 位编号口径一致(00001, 00002 …)
const SEQ_WIDTH = 5;
// 守护窗口: remote 首次 fetch 通常几百毫秒内完成, 4 秒足够覆盖慢盘/大目录
const GUARD_MS = 4000;
const POLL_MS = 150;

/**
 * 取当前工作流的名字, 用于让后端按 output/<工作流名>/ 算序列号。
 * 前端各版本存放位置不一, 逐级兜底; 取不到返回空串, 后端会退回 output 根目录。
 *
 * @returns {string} 工作流名(已去掉 .json 后缀); 取不到时为空串
 */
function currentWorkflowName() {
  try {
    const store = app?.extensionManager?.workflow ?? app?.workflowManager;
    const wf = store?.activeWorkflow;
    const raw = wf?.name || wf?.filename || wf?.path || "";
    return String(raw).replace(/\.json$/i, "");
  } catch {
    return "";
  }
}

/**
 * 把整数编号格式化成 5 位文本(00001 / 00002 …)。
 *
 * @param {number|string} value 编号
 * @returns {string} 5 位文本
 */
function sequenceText(value) {
  // 序列号从 00001 开始: 0 / 空值 / 非法值都回退到 1, 不再显示 00000
  const n = Math.max(1, Number(value) || 1);
  return String(Math.trunc(n)).padStart(SEQ_WIDTH, "0");
}

/**
 * 判断存档里的序列号是否属于「未设置」: 空、0、负数都视为未设置,
 * 打开工作流时重新向后端拉取当前目录的下一个可用编号。
 *
 * @param {*} value 存档值
 * @returns {boolean} 是否未设置
 */
function sequenceUnset(value) {
  const text = String(value ?? "").trim();
  return text === "" || Number(text) <= 0;
}

/**
 * 写入节点上的「序列号」控件(始终按 5 位显示)。
 *
 * @param {LGraphNode} node 节点
 * @param {number|string} value 编号
 * @returns {void}
 */
function setSequence(node, value) {
  const widget = node.widgets?.find((w) => w.name === "sequence");
  if (widget) widget.value = sequenceText(value);
}

/**
 * 从后端重算序列号并写入节点。
 *
 * @param {LGraphNode} node 节点
 * @param {boolean} notify 是否弹提示(手动点刷新时为真)
 * @returns {Promise<number>} 重算后的编号; 失败时返回 -1
 */
async function refreshSequence(node, notify) {
  try {
    const url = ROUTE + "/next_sequence?workflow_name=" + encodeURIComponent(currentWorkflowName());
    const r = await fetch(url);
    const j = await r.json().catch(() => null);
    if (!r.ok || j?.status !== "ok") {
      if (notify) app.extensionManager.toast.add({ severity: "error", summary: "刷新序列号失败", life: 3000 });
      return -1;
    }
    setSequence(node, j.sequence);
    if (notify) {
      app.extensionManager.toast.add({ severity: "info", summary: "序列号已刷新: " + sequenceText(j.sequence), life: 3000 });
    }
    return Number(j.sequence) || 1;
  } catch (err) {
    console.error("[FallingTS] 刷新序列号失败:", err);
    if (notify) app.extensionManager.toast.add({ severity: "error", summary: "刷新序列号失败: 无法连接后端", life: 3000 });
    return -1;
  }
}

/**
 * 取工作流里存的 image 值(configure 时传入的节点数据)。
 *
 * 优先 widgets_values_named(按 widget 名索引, 不受 widget 顺序变化影响),
 * 退回到 widgets_values 里 image widget 的同下标项。
 *
 * @param {LGraphNode} node 节点
 * @param {object} info configure 数据
 * @returns {string} 存档值(取不到返回空串)
 */
function storedImageValue(node, info) {
  const named = info?.widgets_values_named;
  if (named && typeof named.image === "string" && named.image) return named.image;

  const list = info?.widgets_values;
  if (!Array.isArray(list)) return "";
  const index = node.widgets?.findIndex((w) => w.name === "image") ?? -1;
  const value = index >= 0 ? list[index] : undefined;
  return typeof value === "string" ? value : "";
}

/**
 * 短守护: 把被 onFirstLoad 换掉的 image 值恢复成工作流里存的那个。
 *
 * @param {LGraphNode} node 节点
 * @param {object} info configure 数据
 * @returns {void}
 */
function keepStoredImage(node, info) {
  const stored = storedImageValue(node, info);
  if (!stored) return;

  const widget = node.widgets?.find((w) => w.name === "image");
  if (!widget) return;

  // configure 与 onFirstLoad 的先后不确定, 先立刻回正一次
  if (widget.value !== stored) widget.value = stored;

  const deadline = Date.now() + GUARD_MS;
  const timer = setInterval(() => {
    if (node.removed || Date.now() > deadline) {
      clearInterval(timer);
      return;
    }
    const values = widget.options?.values;
    if (Array.isArray(values) && values.length) {
      // 只认"被换成了候选首项"这一种自动改值, 纠正后即收手
      if (widget.value === values[0] && values[0] !== stored) {
        widget.value = stored;
        clearInterval(timer);
      }
      return;
    }
    // 候选还没拉到时**不做任何回正** —— 之前这里有一句无条件回拨
    // 「if (widget.value !== stored) widget.value = stored」, 把守护窗口(4s)内
    // 用户自己在下拉里选的值也一并拨回存档值。实测 2026-10-09: 打开 0016_建模拆图 后
    // 立刻选 0011_万物建模/00001_陈落.png, 提交给后端的却是存档里的
    // 灰度遮罩_纯白.png(见 /history 里 prompt[2]["2"].inputs.image),
    // 于是拆解结果整片纯白。remote 候选是异步拉的, 窗口内经常还没到位,
    // 「值被占位默认值(Loading...)顶掉」并不需要本扩展兜底 —— 提交前还有一次。
  }, POLL_MS);

  const onRemoved = node.onRemoved;
  node.onRemoved = function () {
    clearInterval(timer);
    return onRemoved?.apply(this, arguments);
  };
}

app.registerExtension({
  name: "FallingTS.LoadImage",

  /**
   * 节点定义注册前钩子: 只处理加载图像节点。
   *
   * @param {Function} nodeType 节点类型构造函数
   * @param {object} nodeData 节点定义数据
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      // ── 序列号刷新按钮: 插到「序列号」控件之后 ──
      const seqWidget = node.widgets?.find((w) => w.name === "sequence");
      const refreshBtn = node.addWidget("button", "刷新序列号", null, async () => {
        await refreshSequence(node, true);
      });
      if (seqWidget && refreshBtn) {
        const at = node.widgets.indexOf(refreshBtn);
        node.widgets.splice(at, 1);
        node.widgets.splice(node.widgets.indexOf(seqWidget) + 1, 0, refreshBtn);
      }

      // remote 组件在 combo 之后追加 Auto-refresh / refresh / upload, 而 upload 可能比本钩子
      // 更晚挂上 ⇒ 分两拍把「序列号 + 刷新序列号」挪到这些控件之后(节点最底部的一组)。
      // ⚠️ 序列号绝不能提到 image 之前: V1 节点按 widgets_values 的**下标**恢复旧工作流,
      // 旧数组是 [name, image], 提前会让 image 值整体错位。
      const reflow = () => {
        const widgets = node.widgets;
        if (!widgets) return;
        const seq = widgets.find((w) => w.name === "sequence");
        const btn = widgets.find((w) => w.name === "刷新序列号");
        if (!seq || !btn) return;
        const tail = widgets.find((w) => w.name === "upload") || widgets.find((w) => w.name === "refresh");
        for (const w of [seq, btn]) {
          const at = widgets.indexOf(w);
          if (at >= 0) widgets.splice(at, 1);
        }
        const pos = tail ? widgets.indexOf(tail) : -1;
        if (pos < 0) widgets.push(seq, btn);
        else widgets.splice(pos + 1, 0, seq, btn);
      };
      reflow();
      setTimeout(reflow, 300);

      // ── 下拉候选: 点开/点节点即自动刷新(见 load_combo_refresh.js) ──
      armComboRefresh(node, "image");

      // ── 下拉弹窗: 抹掉 " [output]" 标注 + 「排序方式」左侧的刷新按钮(见 load_combo_menu.js) ──
      armComboMenu(node, "image");

      // 新节点自动取一次序列号(打开工作流时保留存档值, 由 onConfigure 决定)
      refreshSequence(node, false);
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      const result = onConfigure?.apply(this, arguments);
      const stored = info?.widgets_values_named?.sequence;
      if (sequenceUnset(stored)) {
        refreshSequence(this, false);
      } else {
        setSequence(this, stored);
      }
      keepStoredImage(this, info);
      return result;
    };
  },
});
