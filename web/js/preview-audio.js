// preview-audio.js —— PreviewAudioSave(音频预览保存)前端增强。
//
// 职责单一: 预览 + 「保存」。波形与截段已拆到独立节点 audio-trim(FallingTSAudioTrim)。
//
// 1) 底部加「保存」按钮: 点它把当前音频写 output(同名覆盖), 不重跑工作流;
// 2) 节点内挂一个 <audio controls> 播放器: 节点自带 DOM widget 时 ComfyUI 的
//    PreviewAudio 播放器渲染不出来(实测节点 DOM 里 audio 元素数为 0), 故自备播放器,
//    源自后端 /preview-audio/audio-url/{id}(写 temp 后返回 /view URL);
// 3) 「保存」按钮样式(紫色渐变): 按文本匹配全局套用, 与 PreviewVideo/Image 同款做法。

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_CLASS = "PreviewAudioSave";

/**
 * 给 DOM 版「保存」按钮套紫色渐变样式。
 *
 * @param {HTMLElement} el 按钮元素
 * @returns {void}
 */
function applySaveBtnStyle(el) {
  el.style.height = "40px";
  el.style.minHeight = "40px";
  el.style.padding = "8px 12px";
  el.style.background = "linear-gradient(135deg,#7b5cf5,#a78bfa)";
  el.style.color = "#fff";
  el.style.borderRadius = "8px";
  el.style.fontSize = "15px";
  el.style.fontWeight = "700";
  el.style.letterSpacing = "1px";
  el.style.boxShadow = "0 2px 8px rgba(123,92,245,.35)";
  el.style.transition = "all .2s ease";
  el.style.border = "none";
  if (!el._fallingtsSaveStyled) {
    el._fallingtsSaveStyled = true;
    el.addEventListener("mouseenter", () => {
      el.style.background = "linear-gradient(135deg,#8b6ff7,#b9a0fc)";
      el.style.boxShadow = "0 4px 14px rgba(123,92,245,.5)";
      el.style.transform = "translateY(-1px)";
    });
    el.addEventListener("mouseleave", () => {
      el.style.background = "linear-gradient(135deg,#7b5cf5,#a78bfa)";
      el.style.boxShadow = "0 2px 8px rgba(123,92,245,.35)";
      el.style.transform = "";
    });
  }
}

/**
 * 判断是否为「保存」按钮(按文本/aria-label)。
 *
 * @param {HTMLElement} el 元素
 * @returns {boolean} 是否保存按钮
 */
function isSaveBtn(el) {
  if (!el || el.tagName !== "BUTTON") return false;
  const txt = (el.innerText || "").trim();
  const aria = (el.getAttribute("aria-label") || "").trim();
  return txt === "保存" || txt === "Save" || aria === "保存" || aria === "Save";
}

/**
 * 取当前工作流的名字, 用于让后端把产物写进 output 下的同名子目录。
 * 前端各版本存放位置不一, 逐级兜底; 取不到返回空串, 后端会退回 output 根目录。
 *
 * @returns {string} 工作流名(已去掉 .json 后缀); 取不到时为空串
 */
function currentWorkflowName() {
  try {
    // 新版前端把工作流挂在 extensionManager.workflow, 旧版在 app.workflowManager; 两者都探
    const store = app?.extensionManager?.workflow ?? app?.workflowManager;
    const wf = store?.activeWorkflow;
    const raw = wf?.name || wf?.filename || wf?.path || "";
    return String(raw).replace(/\.json$/i, "");
  } catch {
    return "";
  }
}

/** 遍历页面按钮, 给「保存」按钮套样式。 */
function styleSaveButtons() {
  document.querySelectorAll("button").forEach((el) => {
    if (isSaveBtn(el)) applySaveBtnStyle(el);
  });
}

/**
 * 取后端给出的可播放 URL 并设到播放器(同源不重复设置, 避免打断播放)。
 *
 * @param {LGraphNode} node 节点
 * @returns {Promise<void>} 无
 */
async function refreshPlayer(node) {
  const player = node._fallingtsPlayer;
  if (!player) return;
  try {
    const r = await fetch(`/preview-audio/audio-url/${node.id}`);
    const j = await r.json().catch(() => null);
    if (!r.ok || j?.status !== "ok" || !j.url) return;
    if (player.audioEl.dataset.src === j.url) return;
    player.audioEl.dataset.src = j.url;
    player.audioEl.src = j.url;
    player.audioEl.load();
  } catch {
    /* 后端未就绪时忽略, 下次轮询会重试 */
  }
}

/** 对所有 PreviewAudioSave 节点刷新播放源(带防抖)。 */
const _timers = new Map();
function refreshAllPlayers() {
  for (const node of app.graph?._nodes || []) {
    if (node.type !== NODE_CLASS) continue;
    const prev = _timers.get(node.id);
    if (prev) clearTimeout(prev);
    _timers.set(
      node.id,
      setTimeout(() => {
        _timers.delete(node.id);
        refreshPlayer(node);
      }, 300),
    );
  }
}

/**
 * 创建播放器 DOM widget。
 *
 * @param {LGraphNode} node 节点
 * @returns {object} widget
 */
function createPlayerWidget(node) {
  const root = document.createElement("div");
  root.style.cssText = "width:100%;box-sizing:border-box;padding:0 4px;";

  const audioEl = document.createElement("audio");
  audioEl.controls = true;
  audioEl.preload = "none";
  audioEl.style.cssText = "display:block;width:100%;height:32px;";

  root.appendChild(audioEl);

  const widget = node.addDOMWidget("player", "player", root, {
    serialize: false,
    hideOnZoom: false,
    getValue: () => "",
    setValue: () => {},
  });
  widget.computeSize = (width) => [width, 40];
  widget.audioEl = audioEl;
  widget.element = root;
  return widget;
}

app.registerExtension({
  name: "FallingTS.PreviewAudioSave",

  /**
   * 为 PreviewAudioSave 节点挂「保存」按钮与播放器。
   *
   * @param {object} nodeType 节点类型
   * @param {object} nodeData 节点数据
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_CLASS) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onCreated?.apply(this, arguments);
      const node = this;

      node.addWidget("button", "保存", null, async () => {
        const getWidget = (name) => node.widgets?.find((w) => w.name === name)?.value;
        const prefixLinked = node.inputs?.find((i) => i.name === "filename_prefix")?.link != null;
        const suffixLinked = node.inputs?.find((i) => i.name === "filename_suffix")?.link != null;
        try {
          const resp = await fetch(`/preview-audio/save/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_prefix: getWidget("filename_prefix") ?? "audio",
              filename_prefix_linked: prefixLinked,
              filename_suffix: getWidget("filename_suffix") ?? "",
              filename_suffix_linked: suffixLinked,
              format: getWidget("format") ?? "flac",
              quality: getWidget("quality") ?? "128k",
              // 当前工作流名: 后端据此在 output 下建同名子目录再保存(取不到则由后端回退 output 根)
              workflow_name: currentWorkflowName(),
            }),
          });
          const data = await resp.json().catch(() => ({}));
          const msg = data.message || (resp.ok ? "已保存" : "保存失败");
          if (app.extensionManager?.toast) {
            app.extensionManager.toast.add({
              severity: resp.ok ? "success" : "error",
              summary: "Preview Audio",
              detail: msg,
              life: 3000,
            });
          } else {
            console.log("[FallingTS] 保存:", msg);
          }
        } catch (err) {
          console.warn("[FallingTS] 保存失败:", err);
        }
      });

      node._fallingtsPlayer = createPlayerWidget(node);
      styleSaveButtons();
      refreshPlayer(node);
    };
  },

  /**
   * 全局初始化: 按钮样式持续套用 + 播放源刷新(executed 事件 + 轮询兜底) + queuePrompt 包装。
   *
   * @returns {void}
   */
  setup() {
    // 页面加载/刷新时不清后端状态: 音频缓存留在后端, 播放器由 onNodeCreated 与
    // refreshAllPlayers 从 /preview-audio/audio-url 读回 —— 刷新后仍能试听与「保存」。
    styleSaveButtons();
    new MutationObserver(styleSaveButtons).observe(document.body, { childList: true, subtree: true });

    // onExecuted 在 V3 节点上不可靠(实测不触发), 改监听 api 事件 + 轮询兜底
    api.addEventListener("executed", () => refreshAllPlayers());
    api.addEventListener("progress", () => refreshAllPlayers());
    setInterval(refreshAllPlayers, 5000);

    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    app.queuePrompt = async function (number, batch, queueNodeIds) {
      // 默认 Run(未显式指定目标)时重置, 让输出节点重新执行; partial 提交不重置
      if (!queueNodeIds?.length) {
        try {
          await fetch("/preview-audio/reset", { method: "POST" });
        } catch {
          /* 忽略 */
        }
      }
      return orig(number, batch, queueNodeIds);
    };
  },
});
