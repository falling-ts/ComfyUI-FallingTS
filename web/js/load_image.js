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
 * 3. 节点内预览 / 左上角「编辑遮罩」/ 拖放与粘贴加载 —— **一律不在这里实现**。
 *    这四项都由前端内置的 Comfy.UploadImage 扩展提供: 它只认 INPUT_TYPES 里的
 *    image_upload(见 load-image/nodes.py docstring), 命中后给 image 这个 combo 补一个
 *    IMAGEUPLOAD 控件, 于是 ① 值变化时 useNodeImage + setNodeOutputs 把选中图变成节点
 *    输出图(节点内预览), ② isImageNode 依据 previewMediaType==="image" 让选中节点后左上角
 *    出现「编辑遮罩」按钮, ③ 从媒体库拖入 / 从系统拖入文件走 onDragOver/onDragDrop,
 *    ④ 粘贴图片走 pasteFiles。早期版本在这里自建过 addDOMWidget("<img>"), 与内置预览
 *    功能重叠、还多出一个会写进 widgets_values 的控件, 已删除。
 *
 * 4. 短守护 —— 让"刷新"和"打开工作流"都不再改写已选的子目录资源:
 *    - 刷新(手动点刷新按钮 / 跑完流程后的 Auto-refresh): 后端 remote 配置里不设
 *      control_after_refresh, 前端 useRemoteWidget 的 onRefresh() 直接 no-op, 不需要前端参与;
 *    - 首次加载(打开工作流): useRemoteWidget 的 onFirstLoad 是无条件的, 它只认远端候选
 *      列表, 不分青红皂白把 widget.value 设成候选首项(候选按 mtime 倒序 ⇒ 最近改动的文件)。
 *      上游没有开关可关, 所以在节点 configure 之后开一个短守护窗口: 只有当当前值
 *      **不在候选列表里**时(占位默认值 Loading... 被写进 widget), 才恢复成工作流存的值。
 *
 * 守护只持续数秒, 且只在"值不在候选列表里"时动作一次, 因此用户自己在下拉里选的
 * 任何一项(哪怕正好是候选首项)都不会被回拨; 窗口之外本扩展完全不管。
 *
 * ⚠️ 若存档值指向的文件已被删除/改名, 这里会保留该值(而不是跳到首项) —— 提交时由后端
 * VALIDATE_INPUTS 报 "Invalid image file", 明确报错好过静默换图。
 */

import { app } from "../../../scripts/app.js";
import { armComboRefresh } from "./load_combo_refresh.js";
import { armComboMenu, armedComboNode } from "./load_combo_menu.js";

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
 * 「节点创建时自动取一次」与「打开工作流时用存档值」是并发的两件事: 若存档值先落地、
 * 异步 fetch 后返回, 就会把存档值覆盖成当前的下一个编号(实测 0016: 存档 00002 被
 * 覆盖回 00001, 两条流还都变成同一个号)。用节点上的代际序号做闸门 —— configure
 * 写存档值时递增它, 令在途的那次自动刷新作废(与 load_audio.js 同一套)。
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
 * 上游 useRemoteWidget 的 onFirstLoad 是**无条件**的: 它拿到远端候选后直接把
 * widget.value 设成候选首项(候选按 mtime 倒序)。而它的候选缓存以
 * (route, query_params) 为键**全局共享**($b 这个 Map) —— 同一个工作流里的第二个加载节点
 * 一创建就看到"缓存已初始化", 于是立刻触发自己的 onFirstLoad, 把自己存档里的图
 * 换成候选首项。实测 0016_建模拆图: 节点 1 存 0016_.../00001_陈落_左边.png、
 * 节点 2 存 0012_.../00001_陈落出门装.png, 打开工作流后两个节点都加载了节点 1 那张,
 * 相当于静默改图。这里在 configure 之后开一个短守护窗口, 把这类**非用户操作**的自动改值
 * 拨回存档值。
 *
 * 「非用户操作」靠一次性的 pointerdown 判定: 只要用户碰过这个节点的 DOM、在画布上点过
 * 它的 widget、或点过属于它的下拉弹窗(弹窗是 body 下的 portal, 靠 armedComboNode()
 * 认领), 就把 touched 置真, 此后**再也不回拨** —— 用户自己选的值(哪怕正好是候选首项)
 * 因此不可能被误判。这与早期版本"值不在候选列表里才回正"的区别在于: onFirstLoad
 * 换成的候选首项**本身就在候选列表里**, 那条判据抓不到它。
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

  let touched = false;
  const markTouched = (event) => {
    if (touched) return;
    if (app.canvas?.node_widget?.[0] === node) {
      touched = true;
      return;
    }
    const target = event?.target;
    if (target?.closest?.("[data-node-id]")?.dataset?.nodeId === String(node.id)) {
      touched = true;
      return;
    }
    // 下拉弹窗挂在 body 下, 不在节点 DOM 里; 只有"正打开着本节点下拉"才算用户操作
    if (target?.closest?.('[data-pc-name="popover"]') && armedComboNode() === node) {
      touched = true;
    }
  };
  document.addEventListener("pointerdown", markTouched, true);

  const deadline = Date.now() + GUARD_MS;
  const timer = setInterval(() => {
    if (node.removed || Date.now() > deadline) {
      clearInterval(timer);
      document.removeEventListener("pointerdown", markTouched, true);
      return;
    }
    // 用户还没碰过这个节点 ⇒ 此刻值变了只可能是 onFirstLoad 那一次自动改值, 拨回去
    if (!touched && widget.value !== stored) widget.value = stored;
  }, POLL_MS);

  const onRemoved = node.onRemoved;
  node.onRemoved = function () {
    clearInterval(timer);
    document.removeEventListener("pointerdown", markTouched, true);
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

    // 注册时抄一份静态候选 —— 远端 combo 的 options.values 会被换成访问器, 候选没进缓存
    // 之前它返回的是字符串默认值, Vue 侧对象展开会把那个字符串拍进控件描述符(见
    // load_combo_refresh.js 的 repairRemoteValues)。这里抄下来当兜底。
    const staticValues = nodeData.input?.required?.image?.[1]?.options;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      // upload 按钮自己声明了 options.serialize:false, 但 1.52.7 存盘只看 widget.serialize
      // (options 那份没拷上来), 它会照样占掉 widgets_values 的一格。配合上面的「钉到最尾」,
      // 这里再补一刀: 它排在尾部且不序列化 ⇒ 存盘长度与旧存档(6 格)一致, 恢复也不移位。
      const uploadWidget = node.widgets?.find((w) => w.name === "upload");
      if (uploadWidget) uploadWidget.serialize = false;

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
      // ⚠️ 控件顺序 = 存档下标, 不能随意动:
      // 1.52.7 的 Comfy.Workflow.NamedValuesRestore 默认 **false**, configure 走
      //    「按位置」恢复 —— 它用一个只数**可序列化**控件的计数器去读 widgets_values,
      //    而存盘时写的是控件的**数组下标**(非序列化项留空洞)。两者只有在"空洞都在
      //    尾巴上"时才一致。前端 Comfy.UploadImage 会依 image_upload 自动补一个 upload
      //    按钮, 若让它插在中间, 下标就会整体错位一格(「序列号」读到 refresh 那一格)。
      //    因此这里把 upload 钉到控件表**最尾**, 并让「序列号 + 刷新序列号」排在
      //    refresh 之后 —— 恢复出来的下标与加 image_upload 之前的旧存档完全一致。
      const reflow = () => {
        const widgets = node.widgets;
        if (!widgets) return;
        const upload = widgets.find((w) => w.name === "upload");
        if (upload) {
          const at = widgets.indexOf(upload);
          if (at >= 0 && at !== widgets.length - 1) {
            widgets.splice(at, 1);
            widgets.push(upload);
          }
        }
        const seq = widgets.find((w) => w.name === "sequence");
        const btn = widgets.find((w) => w.name === "刷新序列号");
        if (!seq || !btn) return;
        const tail = widgets.find((w) => w.name === "refresh");
        for (const w of [seq, btn]) {
          const at = widgets.indexOf(w);
          if (at >= 0) widgets.splice(at, 1);
        }
        const pos = tail ? widgets.indexOf(tail) : -1;
        if (pos < 0) widgets.push(seq, btn);
        else widgets.splice(pos + 1, 0, seq, btn);
        // 再钉一次: 上面插入可能又把 upload 挤到中间
        const again = widgets.indexOf(upload);
        if (again >= 0 && again !== widgets.length - 1) {
          widgets.splice(again, 1);
          widgets.push(upload);
        }
      };
      reflow();
      setTimeout(reflow, 300);

      // ── 下拉候选: 点开/点节点即自动刷新(见 load_combo_refresh.js) ──
      armComboRefresh(node, "image", staticValues);

      // ── 下拉弹窗: 抹掉 " [output]" 标注 + 「排序方式」左侧的刷新按钮(见 load_combo_menu.js) ──
      armComboMenu(node, "image");

      // 新节点自动取一次序列号(打开工作流时保留存档值, 由 onConfigure 决定)
      refreshSequence(node, false);
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      const result = onConfigure?.apply(this, arguments);
      const stored = info?.widgets_values_named?.sequence;
      // 存档值优先: 先递增代际让 onNodeCreated 那次在途的自动刷新作废, 再写存档值
      this._fallingtsSeqToken = (this._fallingtsSeqToken || 0) + 1;
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
