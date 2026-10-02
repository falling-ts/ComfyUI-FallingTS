/**
 * FallingTS.LoadAudio 前端扩展: 只对 FallingTSLoadAudio 生效。
 *
 * 1. 「名称 / 序列号 / 刷新序列号」—— 与「加载图像 / 加载视频」同一套: 编号 = 该工作流产物
 *    目录里已有 "数字_" 命名的文件的最大编号 + 1(目录不存在/为空为 00000), 可手改, 按钮随时重算。
 *    编号与目录口径都由后端 output_subdir 解析(有 md 数据表用表文件名, 没有才用工作流名)。
 *
 * 2. 下拉候选"点开即最新" —— 见 load_combo_refresh.js; 弹窗里抹掉 " [output]" 标注 +
 *    工具条「排序方式」左侧的刷新按钮 —— 见 load_combo_menu.js。
 *
 * 3. 短守护 —— 让"刷新"和"打开工作流"都不再改写已选的资源:
 *    - 刷新(手动点刷新按钮 / 跑完流程后的 Auto-refresh): 后端 remote 配置里不设
 *      control_after_refresh, 前端 onRefresh() 直接 no-op, 不需要前端参与;
 *    - 首次加载(打开工作流): useRemoteWidget 的 onFirstLoad 是无条件的, 它只认远端候选列表,
 *      会把 widget.value 设成候选首项(候选按 mtime 倒序 ⇒ 最近改动的文件)。上游没有开关,
 *      所以在 configure 之后开一个短守护窗口: 一旦发现值被换成候选首项(且不是存档值), 就恢复存档值。
 *
 * 4. 节点内试听播放器不在这里 —— 它由前端 Comfy.AudioWidget 的 AUDIO_UI 控件提供
 *    (后端声明了 audioUI 输入): 页面刷新后按已选值重建, 执行完由 UI.PreviewAudio 事件更新。
 *    「保存」按钮**不复制**: 写盘仍归 PreviewAudioSave。
 */

import { app } from "../../../scripts/app.js";
import { armComboRefresh } from "./load_combo_refresh.js";
import { armComboMenu } from "./load_combo_menu.js";

const NODE_CLASS = "FallingTSLoadAudio";
const ROUTE = "/fallingts_load_audio";
// 编号显示宽度: 与产物目录的 5 位编号口径一致(00000, 00001 …)
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
 * 把整数编号格式化成 5 位文本(00000 / 00001 …)。
 *
 * @param {number|string} value 编号
 * @returns {string} 5 位文本
 */
function sequenceText(value) {
  const n = Math.max(0, Number(value) || 0);
  return String(Math.trunc(n)).padStart(SEQ_WIDTH, "0");
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
 * 「节点创建时自动取一次」与「打开工作流时用存档值」是并发的两件事: 若存档值先落地、
 * 异步 fetch 后返回, 就会把存档值覆盖成当前的下一个编号。用节点上的代际序号做闸门 ——
 * configure 写存档值时递增它, 令在途的那次自动刷新作废。
 *
 * @param {LGraphNode} node 节点
 * @param {boolean} notify 是否弹提示(手动点刷新时为真)
 * @returns {Promise<number>} 重算后的编号; 失败/作废时返回 -1
 */
async function refreshSequence(node, notify) {
  const token = (node._fallingtsSeqToken || 0) + 1;
  node._fallingtsSeqToken = token;
  try {
    const url = ROUTE + "/next_sequence?workflow_name=" + encodeURIComponent(currentWorkflowName());
    const r = await fetch(url);
    const j = await r.json().catch(() => null);
    if (!r.ok || j?.status !== "ok") {
      if (notify) app.extensionManager.toast.add({ severity: "error", summary: "刷新序列号失败", life: 3000 });
      return -1;
    }
    if (node._fallingtsSeqToken !== token) return -1;
    setSequence(node, j.sequence);
    if (notify) {
      app.extensionManager.toast.add({ severity: "info", summary: "序列号已刷新: " + sequenceText(j.sequence), life: 3000 });
    }
    return Number(j.sequence) || 0;
  } catch (err) {
    console.error("[FallingTS] 刷新序列号失败:", err);
    if (notify) app.extensionManager.toast.add({ severity: "error", summary: "刷新序列号失败: 无法连接后端", life: 3000 });
    return -1;
  }
}

/**
 * 取工作流里存的音频值(configure 时传入的节点数据)。
 *
 * 优先 widgets_values_named(按 widget 名索引, 不受 widget 顺序变化影响),
 * 退回到 widgets_values 里 audio widget 的同下标项。
 *
 * 注意区分"存的就是空串"(如 0070 由 audio_in 驱动、下拉不选文件)与"没有存档值":
 * 前者要守护成空, 后者(null)不守护 —— 否则新节点上手选候选首项会被误回拨。
 *
 * @param {LGraphNode} node 节点
 * @param {object} info configure 数据
 * @returns {string|null} 存档值; 没有存档值时返回 null
 */
function storedAudioValue(node, info) {
  const named = info?.widgets_values_named;
  if (named && typeof named.audio === "string") return named.audio;

  const list = info?.widgets_values;
  if (!Array.isArray(list)) return null;
  const index = node.widgets?.findIndex((w) => w.name === "audio") ?? -1;
  const value = index >= 0 ? list[index] : undefined;
  return typeof value === "string" ? value : null;
}

/**
 * 短守护: 把被 onFirstLoad 换掉的 audio 值恢复成工作流里存的那个。
 *
 * @param {LGraphNode} node 节点
 * @param {object} info configure 数据
 * @returns {void}
 */
function keepStoredAudio(node, info) {
  const stored = storedAudioValue(node, info);
  if (stored === null) return;

  const widget = node.widgets?.find((w) => w.name === "audio");
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
        widget.callback?.(stored);
        clearInterval(timer);
      }
      return;
    }
    // 候选还没拉到: 此刻被改只可能是占位默认值(Loading...), 直接回正
    if (widget.value !== stored) widget.value = stored;
  }, POLL_MS);

  const onRemoved = node.onRemoved;
  node.onRemoved = function () {
    clearInterval(timer);
    return onRemoved?.apply(this, arguments);
  };
}

app.registerExtension({
  name: "FallingTS.LoadAudio",

  /**
   * 节点定义注册前钩子: 只处理加载音频节点。
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

      // ── 序列号刷新按钮: 插到「序列号」控件之后(音频下拉的刷新按钮由 remote 组件追加) ──
      const seqWidget = node.widgets?.find((w) => w.name === "sequence");
      const refreshBtn = node.addWidget("button", "刷新序列号", null, async () => {
        await refreshSequence(node, true);
      });
      if (seqWidget && refreshBtn) {
        const at = node.widgets.indexOf(refreshBtn);
        node.widgets.splice(at, 1);
        node.widgets.splice(node.widgets.indexOf(seqWidget) + 1, 0, refreshBtn);
      }

      // 输出端口 1 是 prefix(「序列号_名称」): 前端按 schema 的 display_name 命名端口, 这里统一成
      // name=prefix / label=文件名前缀(与「加载视频」一致, 后续按端口名引用时不会两处不一致)
      if (node.outputs?.[1]) {
        node.outputs[1].name = "prefix";
        node.outputs[1].label = "文件名前缀";
      }

      // ── 下拉候选: 点开/点节点即自动刷新(见 load_combo_refresh.js) ──
      armComboRefresh(node, "audio");

      // ── 下拉弹窗: 抹掉 " [output]" 标注 + 「排序方式」左侧的刷新按钮(见 load_combo_menu.js) ──
      armComboMenu(node, "audio");

      // 新节点自动取一次序列号(打开工作流时保留存档值, 由 onConfigure 决定)
      refreshSequence(node, false);
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      const result = onConfigure?.apply(this, arguments);
      const stored = info?.widgets_values_named?.sequence;
      if (stored == null || String(stored).trim() === "") {
        refreshSequence(this, false);
      } else {
        // 存档值优先, 并让在途的自动刷新作废(否则它回来会把存档值覆盖成当前编号)
        this._fallingtsSeqToken = (this._fallingtsSeqToken || 0) + 1;
        setSequence(this, stored);
      }
      keepStoredAudio(this, info);
      return result;
    };
  },
});
