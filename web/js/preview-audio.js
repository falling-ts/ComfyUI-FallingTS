/**
 * preview-audio.js — PreviewAudioSave 前端增强。
 *
 * 三块能力:
 * 1. 「保存」按钮(原有): 把 文件名/格式/质量 POST 到 /preview-audio/save/{id},
 *    后端用 execute 时缓存的音频直接写 output({filename_prefix}{filename_suffix}.{format}), 不重跑工作流;
 * 2. 波形截段(新增): 节点内画音频波形, 两侧把手可拖动确定起始与长度;
 *    点「截段」把 {start, duration} POST 到 /preview-audio/segment/{id} 累积到段列表,
 *    段列表每项可单独删除(点 × → /preview-audio/segment-remove/{id});
 * 3. 「完成」按钮(新增): 有段时 POST /preview-audio/done/{id} 并只提交下游(partial),
 *    使本节点按其缓存音频输出 audio_1..audio_N; 无段时 reset + 全量提交(先生成音频)。
 *
 * 设计对应后端 preview-audio/nodes.py 的同名路由; 段参数与 PreviewVideo 的 selected_frames 同套机制。
 */

import { app } from "../../scripts/app.js";

const NODE_CLASS = "PreviewAudioSave";
const MAX_SEGMENTS = 64;
const WAVE_H = 96;

/**
 * 统一的提示条输出。
 *
 * @param {"success"|"error"|"info"|"warn"} severity 级别
 * @param {string} summary 文本
 * @returns {void}
 */
function toast(severity, summary) {
  app.extensionManager?.toast?.add({ severity, summary });
}

/**
 * 把秒格式化为紧凑显示(两位小数)。
 *
 * @param {number} v 秒
 * @returns {string} 形如 "1.25"
 */
function fmt(v) {
  return Number(v || 0).toFixed(2);
}

/**
 * canvas 圆角矩形路径(老浏览器无 ctx.roundRect 时用 arcTo 手绘)。
 *
 * @param {CanvasRenderingContext2D} ctx 上下文
 * @param {number} x 左上 x
 * @param {number} y 左上 y
 * @param {number} w 宽
 * @param {number} h 高
 * @param {number} r 圆角半径
 * @returns {void}
 */
function roundRectPath(ctx, x, y, w, h, r) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

/**
 * 创建段列表 DOM widget: 每行显示 序号/起止/时长 + 删除按钮。
 *
 * 列表高度随段数增长(每行 24px), 始终完整可见。
 *
 * @param {LGraphNode} node 节点
 * @returns {object} widget 对象(带 render/state)
 */
function createSegmentListWidget(node) {
  const state = { segments: [] };
  const root = document.createElement("div");
  root.style.cssText =
    "display:flex;flex-direction:column;gap:2px;padding:4px 6px;box-sizing:border-box;" +
    "font:12px 'Segoe UI','Microsoft YaHei',sans-serif;color:#e8e8e8;overflow:hidden;";

  /**
   * 重绘列表内容(段为空时显示占位提示)。
   *
   * @returns {void}
   */
  const render = () => {
    root.innerHTML = "";
    if (!state.segments.length) {
      const empty = document.createElement("div");
      empty.textContent = "在波形上拖动选择区间, 点「截段」加入";
      empty.style.cssText = "opacity:.55;padding:3px 2px;";
      root.appendChild(empty);
      return;
    }
    state.segments.forEach((seg, i) => {
      const row = document.createElement("div");
      row.style.cssText =
        "display:flex;align-items:center;gap:6px;padding:2px 4px;border-radius:4px;background:rgba(255,255,255,.06);";
      const label = document.createElement("span");
      label.textContent = `#${i + 1}  ${fmt(seg.start)}s → ${fmt(seg.start + seg.duration)}s  (${fmt(seg.duration)}s)`;
      label.style.cssText = "flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
      const del = document.createElement("button");
      del.textContent = "×";
      del.title = "删除该段";
      del.style.cssText =
        "width:18px;height:18px;line-height:16px;border-radius:4px;border:1px solid rgba(255,255,255,.25);" +
        "background:rgba(200,60,60,.75);color:#fff;cursor:pointer;font-size:12px;padding:0;";
      del.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          const resp = await fetch(`/preview-audio/segment-remove/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index: i + 1 }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            toast("error", data?.message ?? "删除失败");
            return;
          }
          state.segments.splice(i, 1);
          render();
          syncSegmentState(node, state);
        } catch (err) {
          console.error("[FallingTS] 删除截段失败:", err);
          toast("error", "删除失败: 无法连接后端");
        }
      });
      row.appendChild(label);
      row.appendChild(del);
      root.appendChild(row);
    });
  };

  const widget = node.addDOMWidget("segment_list", "segments", root, {
    serialize: false,
    hideOnZoom: false,
    getValue: () => "",
    setValue: () => {},
  });
  widget.state = state;
  widget.render = render;
  /**
   * 列表所需高度(供 LiteGraph 布局)。
   *
   * @param {number} width 可用宽
   * @returns {[number, number]} [宽, 高]
   */
  widget.computeSize = (width) => [width, Math.max(24, state.segments.length * 24 + 10)];
  widget.element = root;
  return widget;
}

/**
 * 创建波形 widget: 画波形 + 选区 + 两侧把手, 支持拖动改起始/长度。
 *
 * 交互:
 * - 拖左把手 → 改 start(保留下一个把手位置, 不越过它);
 * - 拖右把手 → 改 end(同理);
 * - 在选区内拖动 → 整体平移选区;
 * - 在选区外按下 → 以该点为锚点重新拉一个选区。
 *
 * @param {LGraphNode} node 节点
 * @returns {object} widget 对象
 */
function createWaveformWidget(node) {
  const state = {
    peaks: [],
    duration: 0,
    start: 0,
    end: 0,
    dragging: null,
    dragOffset: 0,
    loaded: false,
  };

  // 把手命中判定像素半径
  const HIT = 8;

  /**
   * 节点局部 x 坐标 → 秒。
   *
   * @param {number} x 局部 x
   * @param {number} w 波形宽
   * @returns {number} 秒
   */
  const xToSec = (x, w) => {
    const usable = Math.max(1, w - 2 * HIT);
    const t = (x - HIT) / usable;
    return Math.max(0, Math.min(1, t)) * (state.duration || 0);
  };

  /**
   * 秒 → 节点局部 x 坐标。
   *
   * @param {number} sec 秒
   * @param {number} w 波形宽
   * @returns {number} 局部 x
   */
  const secToX = (sec, w) => {
    const usable = Math.max(1, w - 2 * HIT);
    const t = state.duration > 0 ? sec / state.duration : 0;
    return HIT + Math.max(0, Math.min(1, t)) * usable;
  };

  const widget = {
    type: "waveform",
    name: "waveform",
    value: "",
    options: { serialize: false },
    state,
    /**
     * 是否已有可拖动的选区。
     *
     * @returns {boolean} 结果
     */
    hasRange() {
      return state.end > state.start;
    },
    /**
     * 画波形与选区。
     *
     * @param {CanvasRenderingContext2D} ctx 上下文
     * @param {LGraphNode} n 节点
     * @param {number} w 宽
     * @param {number} y 顶边 y
     * @param {number} h 高
     * @returns {void}
     */
    draw(ctx, n, w, y, h) {
      const H = WAVE_H;
      ctx.save();
      ctx.translate(0, y);
      // 背景
      roundRectPath(ctx, 4, 0, w - 8, H, 6);
      ctx.fillStyle = "#1b1e24";
      ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,.12)";
      ctx.lineWidth = 1;
      ctx.stroke();

      if (!state.loaded || !state.peaks.length) {
        ctx.fillStyle = "rgba(255,255,255,.4)";
        ctx.font = "12px 'Segoe UI','Microsoft YaHei',sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("运行到本节点后显示波形(点「完成」先生成)", w / 2, H / 2);
        ctx.restore();
        return;
      }

      const innerW = Math.max(1, w - 8 - 2 * HIT);
      const midY = H / 2;
      const halfH = H / 2 - 10;

      // 选区高亮
      if (state.end > state.start) {
        const x1 = secToX(state.start, w - 8) + 4;
        const x2 = secToX(state.end, w - 8) + 4;
        ctx.fillStyle = "rgba(90,170,255,.22)";
        ctx.fillRect(x1, 2, Math.max(1, x2 - x1), H - 4);
      }

      // 波形(上下对称)
      ctx.strokeStyle = "rgba(150,210,255,.85)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      const n_ = state.peaks.length;
      for (let i = 0; i < n_; i++) {
        const x = 4 + HIT + (i / Math.max(1, n_ - 1)) * innerW;
        const a = Math.min(1, Math.abs(state.peaks[i] || 0)) * halfH;
        ctx.moveTo(x, midY - a);
        ctx.lineTo(x, midY + a);
      }
      ctx.stroke();

      // 中线
      ctx.strokeStyle = "rgba(255,255,255,.15)";
      ctx.beginPath();
      ctx.moveTo(4 + HIT, midY);
      ctx.lineTo(4 + HIT + innerW, midY);
      ctx.stroke();

      // 两个把手
      if (state.end > state.start) {
        for (const [sec, color] of [
          [state.start, "#5aaaff"],
          [state.end, "#ffb454"],
        ]) {
          const x = secToX(sec, w - 8) + 4;
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(x, 2);
          ctx.lineTo(x, H - 2);
          ctx.stroke();
          ctx.fillStyle = color;
          roundRectPath(ctx, x - 4, midY - 9, 8, 18, 3);
          ctx.fill();
        }
      }
      ctx.restore();
    },
    computeSize(width) {
      return [width, WAVE_H];
    },
    /**
     * 鼠标交互: 拖动把手改起止, 拖选区内平移, 选区外重新拉选。
     *
     * @param {Event} event 鼠标事件
     * @param {[number,number]} pos 节点局部坐标
     * @param {LGraphNode} n 节点
     * @returns {boolean} 是否消费该事件
     */
    mouse(event, pos, n) {
      if (!state.loaded || state.duration <= 0) return false;
      const w = (n.size?.[0] ?? 300) - 8;
      const x = pos[0];
      const xs = secToX(state.start, w) + 4;
      const xe = secToX(state.end, w) + 4;
      const has = state.end > state.start;

      if (event.type === "mousedown") {
        if (has && Math.abs(x - xs) <= HIT) state.dragging = "start";
        else if (has && Math.abs(x - xe) <= HIT) state.dragging = "end";
        else if (has && x > xs && x < xe) {
          state.dragging = "range";
          state.dragOffset = xToSec(x, w) - state.start;
        } else {
          // 选区外: 以该点为锚点重新拉选
          state.dragging = "end";
          state.start = xToSec(x, w);
          state.end = state.start;
        }
        n.setDirtyCanvas(true, true);
        return true;
      }
      if (event.type === "mousemove" && state.dragging) {
        const sec = xToSec(x, w);
        if (state.dragging === "start") {
          state.start = Math.min(sec, state.end);
        } else if (state.dragging === "end") {
          state.end = Math.max(sec, state.start);
        } else if (state.dragging === "range") {
          const len = state.end - state.start;
          let s = Math.max(0, Math.min(state.duration - len, sec - state.dragOffset));
          state.start = s;
          state.end = s + len;
        }
        n.setDirtyCanvas(true, true);
        return true;
      }
      if (event.type === "mouseup") {
        if (state.dragging) {
          state.dragging = null;
          n.setDirtyCanvas(true, true);
        }
        return true;
      }
      return false;
    },
  };
  node.addCustomWidget(widget);
  return widget;
}

/**
 * 同步段状态到节点输出槽可见性(与 PreviewVideo 的 syncFrameState 同思路)。
 *
 * 这里只做画布重绘与标题提示 —— 输出槽由后端 schema 固定为 audio_1..audio_64,
 * 未截到的槽在后端输出 None, 无需前端动态增删端口。
 *
 * @param {LGraphNode} node 节点
 * @param {object} state 段状态
 * @returns {void}
 */
function syncSegmentState(node, state) {
  const n = state.segments?.length ?? 0;
  node.title = n > 0 ? `Preview Audio (保存+截段) · ${n} 段` : "Preview Audio (保存+截段)";
  node.setDirtyCanvas(true, true);
}

/**
 * 从后端拉波形峰值与已有段列表, 刷新波形 widget 与段列表。
 *
 * @param {LGraphNode} node 节点
 * @param {object} waveWidget 波形 widget
 * @param {object} listWidget 段列表 widget
 * @returns {Promise<void>} 拉取流程
 */
async function refreshWaveform(node, waveWidget, listWidget) {
  try {
    const resp = await fetch(`/preview-audio/waveform/${node.id}`);
    const data = await resp.json().catch(() => null);
    if (!resp.ok || !data || data.status !== "ok") return;
    waveWidget.state.peaks = data.peaks || [];
    waveWidget.state.duration = Number(data.duration || 0);
    waveWidget.state.loaded = true;
    if (Array.isArray(data.segments) && data.segments.length) {
      listWidget.state.segments = data.segments.map((s) => ({
        start: Number(s.start || 0),
        duration: Number(s.duration || 0),
      }));
    }
    if (waveWidget.state.end <= waveWidget.state.start) {
      waveWidget.state.start = 0;
      waveWidget.state.end = waveWidget.state.duration;
    }
    listWidget.render();
    syncSegmentState(node, listWidget.state);
    node.setDirtyCanvas(true, true);
  } catch (err) {
    console.warn("[FallingTS] 拉取波形失败:", err);
  }
}

app.registerExtension({
  name: "FallingTS.PreviewAudioSave",

  /**
   * 扩展初始化: 页面加载时清空后端截段状态(与 PreviewVideo 的 clear 同语义 ——
   * 前端刷新后列表回空, 后端若不清理会把新段追加到旧段后面)。
   *
   * @returns {Promise<void>} 清理流程
   */
  async setup() {
    try {
      await fetch("/preview-audio/clear", { method: "POST" });
    } catch (err) {
      console.warn("[FallingTS] 清空截段状态失败:", err);
    }
  },

  /**
   * 节点定义注册前钩子: 给 PreviewAudioSave 追加波形截段 UI 与按钮。
   *
   * @param {Function} nodeType 节点类型构造函数
   * @param {object} nodeData 节点定义数据
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 建波形 widget / 段列表 / 「截段」「完成」「保存」按钮。
     *
     * @returns {*} 原 onNodeCreated 返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      // 波形(在原有控件之后、按钮之前插入)
      const waveWidget = createWaveformWidget(node);
      const listWidget = createSegmentListWidget(node);
      node._fallingtsWave = waveWidget;
      node._fallingtsSegments = listWidget;

      /**
       * 「截段」按钮: 把当前选区 POST 到后端累积, 并加入前端列表。
       *
       * @returns {Promise<void>} 请求流程
       */
      node.addWidget("button", "截段", null, async () => {
        const st = waveWidget.state;
        if (!st.loaded) {
          toast("warn", "还没有音频波形, 请先点「完成」生成或运行工作流");
          return;
        }
        const duration = st.end - st.start;
        if (duration <= 0.01) {
          toast("warn", "请先在波形上拖动选出区间");
          return;
        }
        if (listWidget.state.segments.length >= MAX_SEGMENTS) {
          toast("warn", `已达截段上限 ${MAX_SEGMENTS} 段`);
          return;
        }
        try {
          const resp = await fetch(`/preview-audio/segment/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ start: st.start, duration }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            toast("error", data?.message ?? "截段失败");
            return;
          }
          listWidget.state.segments.push({ start: st.start, duration });
          listWidget.render();
          syncSegmentState(node, listWidget.state);
          toast("success", `已添加第 ${data?.index ?? listWidget.state.segments.length} 段`);
        } catch (err) {
          console.error("[FallingTS] 截段失败:", err);
          toast("error", "截段失败: 无法连接后端");
        }
      });

      /**
       * 「完成」按钮: 有段 → 置 done 并只提交下游; 无段 → reset + 全量提交(先生成音频)。
       *
       * @returns {Promise<void>} 请求流程
       */
      node.addWidget("button", "完成", null, async () => {
        const segs = listWidget.state.segments;
        try {
          if (!segs.length) {
            try {
              await fetch("/preview-audio/reset", { method: "POST" });
            } catch {
              /* 忽略: reset 失败不阻塞生成 */
            }
            await app.queuePrompt(0, 1);
            toast("info", "已开始生成音频, 回来后可拖动波形截段");
            return;
          }
          const resp = await fetch(`/preview-audio/done/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ segments: segs }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            toast("error", data?.message ?? "完成失败");
            return;
          }
          await refreshWaveform(node, waveWidget, listWidget);
          toast("success", `已置完成(${segs.length} 段), 提交后各段从 audio_1.. 输出`);
        } catch (err) {
          console.error("[FallingTS] 完成失败:", err);
          toast("error", "完成失败: 无法连接后端");
        }
      });

      /**
       * 「保存」按钮: 把文件名/格式/质量 POST 到后端, 后端用缓存音频直接写 output,
       * 【不重跑工作流】。
       *
       * @returns {Promise<void>} 保存请求异步流程
       */
      node.addWidget("button", "保存", null, async () => {
        const getWidget = (name) => node.widgets?.find((w) => w.name === name)?.value;
        const prefixLinked = node.inputs?.find((i) => i.name === "filename_prefix")?.link != null;
        const suffixLinked = node.inputs?.find((i) => i.name === "filename_suffix")?.link != null;
        const fmtVal = getWidget("format");
        try {
          const resp = await fetch(`/preview-audio/save/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_prefix: getWidget("filename_prefix") ?? "audio",
              filename_prefix_linked: prefixLinked,
              filename_suffix: getWidget("filename_suffix") ?? "",
              filename_suffix_linked: suffixLinked,
              format: fmtVal?.format ?? "flac",
              quality: fmtVal?.quality ?? "128k",
              segment_index: 0,
            }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            toast("error", data?.message ?? "保存失败");
            return;
          }
          toast("success", data?.message ?? "已保存");
        } catch (err) {
          console.error("[FallingTS] 保存失败:", err);
          toast("error", "保存失败: 无法连接后端");
        }
      });

      // 首帧数据(工作流加载/运行后)到位时拉一次波形
      const onExecuted = node.onExecuted;
      node.onExecuted = function (message) {
        onExecuted?.apply(this, arguments);
        refreshWaveform(node, waveWidget, listWidget);
      };

      waveWidget.state.start = 0;
      waveWidget.state.end = 0;
      listWidget.render();
      syncSegmentState(node, listWidget.state);
      node.setSize([Math.max(320, node.size?.[0] ?? 320), node.size?.[1] ?? 200]);
    };
  },
});
