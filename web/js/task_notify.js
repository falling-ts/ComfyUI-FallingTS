/**
 * FallingTS 任务完成/失败 浏览器提示音 (web-ding 移植, 2026-09)。
 *
 * 参考 D:\deepseek-harness-plugins\dsh-web-ding 的思路:
 *  - 提示音 100% 由浏览器 JS (Web Audio API) 合成, 宿主/后端不发声、不弹系统通知;
 *  - 两组独立音调设置(成功/失败), 各自开关 + 音量 + 音色频率 + 衰减时长;
 *  - 设置以「自定义 HTML 渲染」挂在 ComfyUI 设置面板, 分类名「成功或失败提示音」,
 *    卡片内嵌音符图标; 文字颜色随 ComfyUI 当前主题自动反色(深色主题=亮字, 浅色主题=暗字)。
 *
 * ComfyUI 设置系统对 addSetting({ type: () => HTMLElement }) 会走内置
 * CustomFormValue 组件: 把 type() 返回的 DOM 元素插进设置项, 因此这里可以
 * 自由编排 HTML + 内联 CSS + 事件监听(与 web-ding 在 Cordis 设置面板用
 * React 组件等价, use-everywhere 插件的 About 项即用此机制)。
 *
 * 与 web-ding 的差异(适配 ComfyUI 环境):
 *  - ComfyUI 没有「弹出用户选择」概念, 只做任务结束(成功)/任务失败(错误/中断)两档提醒;
 *  - 事件源改用 ComfyUI 前端总线: execution_success / execution_error / execution_interrupted;
 *  - 每次成功后顺带弹一个 Win11 风格右下角 toast, 显示本次执行耗时与状态。
 */

import { api } from "../../../scripts/api.js";
import { app } from "../../../scripts/app.js";

// ── 设置键名(ComfyUI 设置服务里以 id 标识, 前缀避免与其它插件冲突) ──────────────
const SET = {
  successEnabled: "FallingTS.Notify.Success.Enabled",
  successVolume: "FallingTS.Notify.Success.Volume",
  successFreq: "FallingTS.Notify.Success.Freq",
  successDecayMs: "FallingTS.Notify.Success.DecayMs",
  failEnabled: "FallingTS.Notify.Fail.Enabled",
  failVolume: "FallingTS.Notify.Fail.Volume",
  failFreq: "FallingTS.Notify.Fail.Freq",
  failDecayMs: "FallingTS.Notify.Fail.DecayMs",
};

/** 各设置项默认值(与 web-ding 的 turnEnd 块一致: 音量 0.7 / 频率 880Hz / 衰减 900ms)。 */
const DEFAULTS = {
  [SET.successEnabled]: true,
  [SET.successVolume]: 0.7,
  [SET.successFreq]: 880,
  [SET.successDecayMs]: 900,
  [SET.failEnabled]: true,
  [SET.failVolume]: 0.7,
  [SET.failFreq]: 440, // 失败用低音, 与成功高音区分
  [SET.failDecayMs]: 1100,
};

/**
 * 读取一个设置的当前值(类型收敛: 数字无效时回退默认, 布尔无效时按默认)。
 * @param {string} key 设置 id
 * @returns {unknown} 当前值(带默认兜底)
 */
function getSetting(key) {
  try {
    const v = app.ui?.settings?.getSettingValue(key);
    if (v === undefined || v === null) return DEFAULTS[key];
    return v;
  } catch {
    return DEFAULTS[key];
  }
}

/**
 * 写入一个设置值(ComfyUI settings store 持久化; 面板/其它标签同步刷新)。
 * @param {string} key 设置 id
 * @param {unknown} value 新值
 */
function setSetting(key, value) {
  try {
    app.ui?.settings?.setSettingValue(key, value);
  } catch { /* 设置服务不可用时忽略 */ }
}

// ── Web Audio 「叮」播放器(逐字移植自 web-ding) ─────────────────────────────
// 完全前端合成: 三个正弦振荡器叠加(基频 + 高八度泛音 + 2.5 倍铃感泛音),
// 各自带指数衰减包络。不加载任何音频资产。
let audio = null;

function ensureAudio() {
  if (audio) {
    if (audio.ctx.state === "closed") audio = null;
    else return audio;
  }
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;
  const ctx = new Ctx();
  audio = { ctx };
  return audio;
}

/** 浏览器自动播放策略: 首次用户手势预热 AudioContext。 */
function warmup() {
  const a = ensureAudio();
  if (a && a.ctx.state === "suspended") {
    void a.ctx.resume().catch(() => {});
  }
}
if (typeof window !== "undefined") {
  window.addEventListener("pointerdown", warmup, { once: true });
  window.addEventListener("keydown", warmup, { once: true });
}

/**
 * 播放一声提示音。
 * @param {{volume?:number, freq?:number, decayMs?:number}} opts
 * @returns {boolean} 是否成功调度(Web Audio 不可用时 false)
 */
function playDing(opts) {
  const o = opts || {};
  const a = ensureAudio();
  if (!a) return false;
  const ctx = a.ctx;
  if (ctx.state === "suspended") void ctx.resume().catch(() => {});
  const volume = Math.min(1, Math.max(0, Number(o.volume) || 0.7));
  const freq = Math.min(2000, Math.max(120, Number(o.freq) || 880));
  const decay = Math.min(2000, Math.max(100, Number(o.decayMs) || 900)) / 1000;
  const t0 = ctx.currentTime + 0.02;
  const schedule = (f, peak, start, dur) => {
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(f, start);
    g.gain.setValueAtTime(0.0001, start);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0001, peak), start + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
    osc.connect(g);
    g.connect(ctx.destination);
    osc.start(start);
    osc.stop(start + dur + 0.05);
  };
  schedule(freq, volume * 0.55, t0, decay);                    // 基频主体
  schedule(freq * 2.0, volume * 0.2, t0, decay * 0.75);        // 高八度泛音
  schedule(freq * 2.5, volume * 0.07, t0 + 0.004, decay * 0.6); // 铃感泛音
  return true;
}

// ── 右下角 toast(Win11 风格, 纯内联样式, 零资产) ────────────────────────────
function makeToastBG(kind, dark) {
  const g = dark ? 0.09 : 0.18;
  return kind === "fail"
    ? `linear-gradient(135deg, rgba(239,68,68,${g}), rgba(239,68,68,${g * 0.4}))`
    : `linear-gradient(135deg, rgba(16,185,129,${g}), rgba(16,185,129,${g * 0.4}))`;
}
const TOAST_ACCENT_SUCCESS = "#10b981";
const TOAST_ACCENT_FAIL = "#ef4444";
let toastLayer = null;

function ensureToastLayer() {
  if (toastLayer && document.body.contains(toastLayer)) return toastLayer;
  toastLayer = document.createElement("div");
  Object.assign(toastLayer.style, {
    position: "fixed", right: "20px", bottom: "20px", zIndex: 2147483000,
    display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "12px",
    pointerEvents: "none",
  });
  document.body.appendChild(toastLayer);
  return toastLayer;
}

function dismissToast(el) {
  el.style.transition = "opacity 0.22s ease, transform 0.28s cubic-bezier(0.16, 1, 0.3, 1)";
  el.style.opacity = "0";
  el.style.transform = "translateX(28px) scale(0.97)";
  window.setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
}

function pad(n) { return String(n).padStart(2, "0"); }

/**
 * 弹出一个右下角 toast(文字颜色随主题反色)。
 * @param {string} kind "success" | "fail"
 * @param {string} title 主标题文本
 * @param {string} detail 副标题文本
 */
function showToast(kind, title, detail) {
  const layer = ensureToastLayer();
  const dark = isDarkTheme();
  const el = document.createElement("div");
  Object.assign(el.style, {
    pointerEvents: "auto", position: "relative", width: 360, minHeight: 84,
    background: dark ? "rgba(30,30,30,0.92)" : "rgba(255,255,255,0.9)",
    backdropFilter: "blur(20px) saturate(1.5)",
    WebkitBackdropFilter: "blur(20px) saturate(1.5)",
    backgroundImage: makeToastBG(kind, dark),
    border: dark ? "1px solid rgba(255,255,255,0.1)" : "1px solid rgba(0,0,0,0.06)",
    borderRadius: 16,
    boxShadow: "0 1px 2px rgba(0,0,0,0.04), 0 6px 16px rgba(0,0,0,0.08), 0 20px 48px rgba(0,0,0,0.14)",
    overflow: "hidden",
    display: "flex", alignItems: "stretch", cursor: "pointer",
    opacity: "0", transform: "translateX(28px) scale(0.97)",
    transition: "opacity 0.22s ease, transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Microsoft YaHei', sans-serif",
    color: dark ? "#e5e5e5" : "#1f1f1f", fontSize: 13,
  });
  const accent = document.createElement("div");
  Object.assign(accent.style, {
    width: 4, flexShrink: 0,
    background: kind === "fail" ? TOAST_ACCENT_FAIL : TOAST_ACCENT_SUCCESS,
  });
  const body = document.createElement("div");
  Object.assign(body.style, { padding: "16px 18px 15px", minWidth: 0 });
  const titleEl = document.createElement("div");
  titleEl.textContent = title;
  Object.assign(titleEl.style, { fontSize: 14, fontWeight: 600, letterSpacing: 0.2, color: dark ? "#f0f0f0" : "#1f1f1f" });
  const textEl = document.createElement("div");
  textEl.textContent = detail;
  Object.assign(textEl.style, { marginTop: 8, lineHeight: 1.6, color: dark ? "rgba(255,255,255,0.62)" : "rgba(0,0,0,0.62)" });
  body.appendChild(titleEl);
  body.appendChild(textEl);
  el.appendChild(accent);
  el.appendChild(body);
  layer.appendChild(el);
  void el.offsetHeight; // force reflow → 进入动画
  el.style.opacity = "1";
  el.style.transform = "translateX(0) scale(1)";
  el._timer = window.setTimeout(() => dismissToast(el), 6000);
  el.addEventListener("click", () => {
    window.clearTimeout(el._timer);
    dismissToast(el);
  });
}

// ── 执行状态跟踪: 记录开始时间, 供成功 toast 展示耗时 ───────────────────────
let executionStartAt = null;

function formatDuration(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return s + " 秒";
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m + " 分 " + r + " 秒";
}

// ── 主题自适应: 检测 ComfyUI 当前主题是深色还是浅色 ──────────────────────────
// 不依赖版本可能变动的主题开关, 直接量页面 body 背景亮度:
// 亮度 < 128 → 深色主题 → 文字用亮色; 反之用暗色。渲染与弹 toast 时各取一次。
function isDarkTheme() {
  try {
    const bg = getComputedStyle(document.body).backgroundColor;
    const m = bg.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (m) {
      const r = Number(m[1]), g = Number(m[2]), b = Number(m[3]);
      // 相对亮度(加权): 0~255
      const lum = 0.299 * r + 0.587 * g + 0.114 * b;
      return lum < 128;
    }
  } catch { /* 计算样式不可用时按深色处理(ComfyUI 默认深色) */ }
  return true;
}

// ── 自定义 HTML 设置项渲染 ───────────────────────────────────────────────────
// ComfyUI 设置系统把 addSetting({ type: fn }) 的 fn 返回值(DOM 元素)渲染进设置面板。
// 分类名为「成功或失败提示音」, 卡片顶部内嵌音符图标(SVG), 全部内联样式并随主题反色。

/** 音符图标 SVG(两个八分音符, 矢量, 继承 currentColor)。 */
function musicNoteIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "18");
  svg.setAttribute("height", "18");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.innerHTML =
    '<path d="M9 18V5l12-2v13"/>' +
    '<circle cx="6" cy="18" r="3"/>' +
    '<circle cx="18" cy="16" r="3"/>';
  return svg;
}

/** 构造一个带标签的滑块行。 */
function makeSliderRow(labelKey, label, min, max, step, fmt, dark) {
  const row = document.createElement("div");
  Object.assign(row.style, {
    display: "grid", gridTemplateColumns: "1fr 150px", gap: "10px 14px",
    alignItems: "center", padding: "8px 0",
    borderBottom: dark ? "1px solid rgba(255,255,255,0.08)" : "1px solid rgba(0,0,0,0.07)",
  });
  const lab = document.createElement("span");
  lab.textContent = label;
  Object.assign(lab.style, { fontSize: 13, fontWeight: 500, color: dark ? "#e8e8e8" : "#1f1f1f" });
  const side = document.createElement("div");
  Object.assign(side.style, { display: "flex", alignItems: "center", gap: 10 });
  const input = document.createElement("input");
  input.type = "range";
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(getSetting(labelKey));
  input.style.cssText = "flex:1;min-width:0;accent-color:#4a8ef5;background:transparent;";
  const val = document.createElement("span");
  val.textContent = fmt(Number(input.value));
  Object.assign(val.style, {
    minWidth: 56, textAlign: "right",
    fontVariantNumeric: "tabular-nums", fontSize: 13,
    color: dark ? "rgba(255,255,255,0.6)" : "rgba(0,0,0,0.55)",
  });
  input.addEventListener("input", () => {
    const v = Number(input.value);
    val.textContent = fmt(v);
    setSetting(labelKey, v);
  });
  side.append(input, val);
  row.append(lab, side);
  return row;
}

/** 构造一个分组的开关行(布尔设置)。 */
function makeToggleRow(key, label, dark) {
  const row = document.createElement("div");
  Object.assign(row.style, {
    display: "grid", gridTemplateColumns: "1fr 150px", gap: "10px 14px",
    alignItems: "center", padding: "8px 0",
    borderBottom: dark ? "1px solid rgba(255,255,255,0.08)" : "1px solid rgba(0,0,0,0.07)",
  });
  const lab = document.createElement("span");
  lab.textContent = label;
  Object.assign(lab.style, { fontSize: 13, fontWeight: 500, color: dark ? "#e8e8e8" : "#1f1f1f" });
  const wrap = document.createElement("label");
  Object.assign(wrap.style, { display: "flex", alignItems: "center", gap: 8, cursor: "pointer" });
  const chk = document.createElement("input");
  chk.type = "checkbox";
  chk.checked = getSetting(key) !== false;
  Object.assign(chk.style, { width: 16, height: 16, accentColor: "#4a8ef5" });
  const state = document.createElement("span");
  const sync = () => { state.textContent = chk.checked ? "开启" : "关闭"; };
  sync();
  Object.assign(state.style, { fontSize: 13, minWidth: 34, color: dark ? "rgba(255,255,255,0.6)" : "rgba(0,0,0,0.55)" });
  chk.addEventListener("change", () => { sync(); setSetting(key, chk.checked); });
  wrap.append(chk, state);
  row.append(lab, wrap);
  return row;
}

/**
 * 构造「成功或失败提示音」设置卡片: 音符图标标题 + 成功/失败两组音调 + 试听。
 * 作为 addSetting({ type }) 的渲染函数返回(每次渲染时取一次主题).
 * @returns {HTMLElement}
 */
function renderNotifyPanel() {
  const dark = isDarkTheme();
  const card = document.createElement("div");
  Object.assign(card.style, {
    border: dark ? "1px solid rgba(255,255,255,0.12)" : "1px solid rgba(0,0,0,0.1)",
    borderRadius: 12,
    background: dark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.025)",
    padding: "4px 16px 6px",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Microsoft YaHei', sans-serif",
    color: dark ? "#e8e8e8" : "#1f1f1f",
  });

  const pct = (n) => Math.round(n * 100) + "%";
  const hz = (n) => Math.round(n) + " Hz";
  const ms = (n) => Math.round(n) + " ms";

  // 卡片主标题: 音符图标 + 分类名
  const head = document.createElement("div");
  Object.assign(head.style, {
    display: "flex", alignItems: "center", gap: 8,
    fontSize: 15, fontWeight: 700, padding: "12px 0 4px",
    color: dark ? "#f0f0f0" : "#1f1f1f",
  });
  const iconWrap = document.createElement("span");
  Object.assign(iconWrap.style, {
    display: "inline-flex", alignItems: "center",
    color: dark ? "#8ab4ff" : "#4a8ef5",
  });
  iconWrap.appendChild(musicNoteIcon());
  const headText = document.createElement("span");
  headText.textContent = "成功或失败提示音";
  head.append(iconWrap, headText);
  card.appendChild(head);

  // 成功组
  const sHead = document.createElement("div");
  Object.assign(sHead.style, {
    fontSize: 13, fontWeight: 600, padding: "10px 0 4px",
    display: "flex", alignItems: "center", gap: 8,
    color: dark ? "#e0e0e0" : "#1f1f1f",
  });
  const sDot = document.createElement("span");
  Object.assign(sDot.style, {
    width: 9, height: 9, borderRadius: "50%",
    background: TOAST_ACCENT_SUCCESS, flexShrink: 0,
  });
  sHead.append(sDot, document.createTextNode("任务完成"));
  card.appendChild(sHead);
  card.appendChild(makeToggleRow(SET.successEnabled, "启用", dark));
  card.appendChild(makeSliderRow(SET.successVolume, "音量", 0, 1, 0.05, pct, dark));
  card.appendChild(makeSliderRow(SET.successFreq, "音色频率", 120, 2000, 10, hz, dark));
  card.appendChild(makeSliderRow(SET.successDecayMs, "衰减时长", 100, 2000, 50, ms, dark));

  // 失败组
  const fHead = document.createElement("div");
  Object.assign(fHead.style, {
    fontSize: 13, fontWeight: 600, padding: "12px 0 4px",
    display: "flex", alignItems: "center", gap: 8,
    color: dark ? "#e0e0e0" : "#1f1f1f",
  });
  const fDot = document.createElement("span");
  Object.assign(fDot.style, {
    width: 9, height: 9, borderRadius: "50%",
    background: TOAST_ACCENT_FAIL, flexShrink: 0,
  });
  fHead.append(fDot, document.createTextNode("任务失败"));
  card.appendChild(fHead);
  card.appendChild(makeToggleRow(SET.failEnabled, "启用", dark));
  card.appendChild(makeSliderRow(SET.failVolume, "音量", 0, 1, 0.05, pct, dark));
  card.appendChild(makeSliderRow(SET.failFreq, "音色频率", 120, 2000, 10, hz, dark));
  card.appendChild(makeSliderRow(SET.failDecayMs, "衰减时长", 100, 2000, 50, ms, dark));

  // 试听行
  const prevRow = document.createElement("div");
  Object.assign(prevRow.style, {
    display: "flex", alignItems: "center", gap: 10,
    padding: "14px 0 10px",
  });
  const prevLabel = document.createElement("span");
  prevLabel.textContent = "试听";
  Object.assign(prevLabel.style, {
    fontSize: 13, fontWeight: 500, width: 168, flexShrink: 0,
    color: dark ? "#e8e8e8" : "#1f1f1f",
  });
  const btnBase = {
    padding: "6px 14px", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 500,
    border: dark ? "1px solid rgba(255,255,255,0.28)" : "1px solid rgba(0,0,0,0.22)",
    background: dark ? "rgba(255,255,255,0.06)" : "transparent",
    color: dark ? "#e5e5e5" : "#1f1f1f",
  };
  const btnSuccess = document.createElement("button");
  btnSuccess.type = "button";
  btnSuccess.textContent = "播放 成功音";
  Object.assign(btnSuccess.style, btnBase);
  btnSuccess.addEventListener("click", () => {
    warmup();
    playDing({
      volume: getSetting(SET.successVolume),
      freq: getSetting(SET.successFreq),
      decayMs: getSetting(SET.successDecayMs),
    });
  });
  const btnFail = document.createElement("button");
  btnFail.type = "button";
  btnFail.textContent = "播放 失败音";
  Object.assign(btnFail.style, btnBase);
  btnFail.addEventListener("click", () => {
    warmup();
    playDing({
      volume: getSetting(SET.failVolume),
      freq: getSetting(SET.failFreq),
      decayMs: getSetting(SET.failDecayMs),
    });
  });
  prevRow.append(prevLabel, btnSuccess, btnFail);
  card.appendChild(prevRow);

  const note = document.createElement("div");
  note.textContent = "浏览器自动播放策略: 首次与页面交互(点击/按键)或点击试听后, 任务结束/失败提示音才会出声。声音由浏览器 Web Audio 纯前端合成, 宿主不发声、不弹系统通知。";
  Object.assign(note.style, {
    fontSize: 12, lineHeight: 1.55,
    padding: "8px 0 12px",
    borderTop: dark ? "1px solid rgba(255,255,255,0.08)" : "1px solid rgba(0,0,0,0.07)",
    color: dark ? "rgba(255,255,255,0.5)" : "rgba(0,0,0,0.45)",
  });
  card.appendChild(note);

  return card;
}

app.registerExtension({
  name: "ComfyDesktop.FallingTS.TaskNotify",

  /**
   * 扩展初始化: 注册设置项(自定义 HTML 渲染), 并挂接执行成功/失败/中断总线事件。
   * @returns {void}
   */
  setup() {
    // 1. 注册设置: 整块「成功或失败 提示音」用函数型 type 渲染自定义 HTML
    //    (官方 CustomFormValue 支持), 分类名为「成功或失败提示音」。
    //    设置值读写仍走标准 settings store(getSettingValue/setSettingValue)。
    try {
      app.ui?.settings?.addSetting({
        id: "FallingTS.Notify.Panel",
        name: "成功或失败提示音",
        type: renderNotifyPanel,
        category: ["成功或失败提示音"],
        tooltip: "任务完成/失败时在浏览器播放一声提示音(Web Audio 前端合成)；文字颜色随主题自动反色",
      });
    } catch { /* 设置面板不可用时功能静默降级 */ }

    // 2. 监听执行事件(先挂监听, 再在 api bus 上统一分发)
    api.addEventListener("execution_start", () => {
      executionStartAt = Date.now();
    });
    api.addEventListener("execution_success", () => {
      const dur = executionStartAt !== null ? formatDuration(Date.now() - executionStartAt) : "";
      executionStartAt = null;
      if (getSetting(SET.successEnabled) === false) return;
      playDing({
        volume: getSetting(SET.successVolume),
        freq: getSetting(SET.successFreq),
        decayMs: getSetting(SET.successDecayMs),
      });
      showToast("success", "任务完成", dur ? "执行耗时 " + dur + " · 浏览器播放成功提示音" : "浏览器播放成功提示音");
    });
    const onFail = (label) => {
      const dur = executionStartAt !== null ? formatDuration(Date.now() - executionStartAt) : "";
      executionStartAt = null;
      if (getSetting(SET.failEnabled) === false) return;
      playDing({
        volume: getSetting(SET.failVolume),
        freq: getSetting(SET.failFreq),
        decayMs: getSetting(SET.failDecayMs),
      });
      showToast("fail", "任务" + label, dur ? "执行耗时 " + dur + " · 浏览器播放失败提示音" : "浏览器播放失败提示音");
    };
    api.addEventListener("execution_error", () => onFail("失败"));
    api.addEventListener("execution_interrupted", () => onFail("中断"));
  },
});