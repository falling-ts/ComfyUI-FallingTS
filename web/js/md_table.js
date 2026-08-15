// FallingTSMarkDownTable 前端 (md 数据表超级节点):
// - 节点上: 「选择md文件」弹系统选择器 (后端 tkinter, 返回绝对路径, 路径框也可手动粘贴),
//   「打开数据」弹内嵌 HTML 表格弹窗 (各字段模糊搜索 + 分页 + 首列单选),
//   「确定」载入选中行到节点表单 (竖向排列, 按类型渲染控件, 可编辑), 「刷新」按 ID 重查 md 文件;
// - 弹窗: 无序号列, 首列单选 radio, 底部 每页 10/20/30/50/100 + 首页/上一页/下一页/尾页,
//   确定按钮仅在选中行后亮起 (蓝色), 取消关闭;
// - 表单类型 (来自表头 `标题(类型)`, 未标默认 STRING): INT/FLOAT -> 数字输入, BOOLEAN -> 复选,
//   TEXT -> 多行文本框(自动撑高), STRING -> 单行文本输入, IMAGE/VIDEO/AUDIO/MASK -> 路径输入 + 内嵌预览;
// - 输出端口动态: [0] ID, [1..] 各非 ID 字段 (按类型), 末位 整行数据 (整行 JSON), 沿用表格节点动态端口模式。
//
// 值 (对象 {md_path, fields, selected}) 作为 widget 值序列化进工作流 widgets_values,
// 与后端 FallingTSMarkDownTable 输入 "data" 同名对接; md 文件本身不随工作流保存, 只存路径+字段+选中行。
import { app } from "../../../scripts/app.js";

const NODE_CLASS = "FallingTSMarkDownTable";
const WIDGET_TYPE = "FALLINGTS_MD_TABLE";
const MAX_FIELDS = 40; // 与后端 parser.MAX_FIELDS 一致
const MAX_OUTPUTS = MAX_FIELDS + 2; // ID + 字段 + 整行数据
const MIN_WIDGET_HEIGHT = 150;

// 各字段类型显示色 (表单类型标签 / 弹窗表头) — 大写 ComfyUI 风格类型
const TYPE_COLORS = {
  STRING: "#9cdcfe",
  TEXT: "#b5cea8",
  INT: "#4ec9b0",
  FLOAT: "#4ec9b0",
  BOOLEAN: "#dcdcaa",
  IMAGE: "#c586c0",
  VIDEO: "#ce9178",
  AUDIO: "#ce9178",
  MASK: "#d19a66",
};

// 字段类型 -> 输出端口显示类型 (后端槽恒为 * ; 端口类型只影响显示/连线校验)
// IMAGE/VIDEO/AUDIO/MASK 字段后端已解析并加载为对应类型 -> 端口类型与之匹配;
// TEXT 与 STRING 一样输出 STRING
const PORT_TYPES = {
  INT: "INT",
  FLOAT: "FLOAT",
  BOOLEAN: "BOOLEAN",
  STRING: "STRING",
  TEXT: "STRING",
  IMAGE: "IMAGE",
  VIDEO: "VIDEO",
  AUDIO: "AUDIO",
  MASK: "MASK",
};

// 类型归一: 别名/旧小写 -> 大写 ComfyUI 类型 (未知回退 STRING)
const TYPE_ALIASES = {
  "str": "STRING", "string": "STRING",
  "text": "TEXT", "txt": "TEXT",
  "int": "INT", "integer": "INT",
  "float": "FLOAT", "double": "FLOAT", "number": "FLOAT",
  "bool": "BOOLEAN", "boolean": "BOOLEAN",
  "image": "IMAGE", "img": "IMAGE",
  "video": "VIDEO",
  "audio": "AUDIO",
  "mask": "MASK", "gray": "MASK", "grayscale": "MASK", "luminance": "MASK", "alpha": "MASK",
  "list": "STRING", "set": "STRING", "dict": "STRING", "json": "STRING",
};

/**
 * 把字段类型字符串归一化为大写 ComfyUI 类型。
 *
 * @param {*} t 原始类型
 * @returns {string} 归一化类型
 */
function normType(t) {
  const key = String(t ?? "STRING").trim().toLowerCase();
  return TYPE_ALIASES[key] ?? "STRING";
}

// bool 真值集合 (与后端 parser._TRUE_VALUES 保持一致)
const TRUE_VALUES = new Set([
  "true", "1", "yes", "y", "on", "是", "真", "开", "对", "t",
]);

const DEFAULT_STATE = {
  md_path: "",
  fields: [],
  selected: { id: "", values: {} },
};

// ─── 基础工具 ───────────────────────────────────────────────────────

/**
 * 规范化控件值: 统一为 {md_path, fields, selected}。
 *
 * @param {*} v 原始状态 (对象/未定义)
 * @returns {object} 规范化后的状态
 */
function normalize(v) {
  const s = v && typeof v === "object" ? v : {};
  const rawFields = Array.isArray(s.fields) ? s.fields : [];
  const fields = [];
  const seen = new Set();
  for (const f of rawFields) {
    const name = f && typeof f === "object" ? String(f.name ?? "") : "";
    if (!name || seen.has(name)) continue;
    seen.add(name);
    fields.push({ name, type: normType(f.type) });
  }
  if (!fields.length) fields.push({ name: "ID", type: "STRING" });
  fields[0].type = "STRING"; // 首列永远是 ID
  const sel = s.selected && typeof s.selected === "object" ? s.selected : {};
  const vals = sel.values && typeof sel.values === "object" ? sel.values : {};
  return {
    md_path: String(s.md_path ?? ""),
    fields,
    selected: { id: String(sel.id ?? ""), values: { ...vals } },
  };
}

/**
 * HTML 转义 (弹窗表头/单元格文本, 防 md 内容注入)。
 *
 * @param {string} s 原始文本
 * @returns {string} 转义后的文本
 */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/**
 * 按类型把 md/表单原始值转成表单显示值 (BOOLEAN -> 布尔, 其余 -> 字符串)。
 *
 * @param {*} raw 原始值
 * @param {string} type 字段类型
 * @returns {*} 显示值
 */
function coerceDisplay(raw, type) {
  if (type === "BOOLEAN") {
    if (typeof raw === "boolean") return raw;
    return TRUE_VALUES.has(String(raw ?? "").trim().toLowerCase());
  }
  // 字符串类: 前后 trim (TEXT 也去首尾空白/空行)
  return raw == null ? "" : String(raw).trim();
}

/**
 * 把整行 md 值按字段类型全部转成显示值。
 *
 * @param {object} rowValues 行 values (字段名 -> md 原始字符串)
 * @param {Array} fields 字段定义 [{name, type}]
 * @returns {object} 显示值对象
 */
function coerceDisplayAll(rowValues, fields) {
  const out = {};
  for (const f of fields) out[f.name] = coerceDisplay(rowValues?.[f.name], f.type);
  return out;
}

/**
 * 字段类型 -> 输出端口显示类型 (int/float/bool/str/image/video/audio 有具体类型, 其余 * )。
 *
 * @param {string} type 字段类型
 * @returns {string} 端口类型
 */
function portTypeFor(type) {
  return PORT_TYPES[type] ?? "*";
}

/**
 * 构造本地文件预览 URL (后端按绝对路径提供 image/video/audio)。
 *
 * @param {string} path 本地绝对路径
 * @returns {string} 预览 URL
 */
function previewUrl(path) {
  return `/fallingts_mdtable/preview?path=${encodeURIComponent(path)}`;
}

// 媒体字段类型 (前端需要提前解析为预览 URL 的)
const MEDIA_TYPES = new Set(["IMAGE", "MASK", "VIDEO", "AUDIO"]);

/**
 * 从 Vue pinia store 按 id 取 store 对象。
 *
 * @param {string} id store id(如 "nodeOutput")
 * @returns {object|null} pinia store 对象; 不可用时返回 null
 */
function getStore(id) {
  try {
    const el = document.getElementById("vue-app");
    const pinia = el?.__vue_app__?.config?.globalProperties?.$pinia;
    return pinia?._s?.get(id) ?? null;
  } catch {
    return null;
  }
}

/**
 * 把节点当前选中行的媒体字段(IMAGE/MASK/VIDEO/AUDIO)提前解析为前端预览 URL,
 * 写入官方 preview store —— 供 ImageCrop(拖框预览)/中键大图等
 * 前端组件即时使用(无需先跑工作流; `@{ID}` 由后端 /preview 路由即时解析)。
 * 图片(IMAGE/MASK)排在前面, WidgetImageCrop 取首个 URL 作预览。
 *
 * @param {LGraphNode} node 节点对象
 * @param {Array} fields 字段定义 [{name, type}]
 * @param {Object} values 选中行值 {字段名: 值}
 * @returns {void}
 */
function syncNodeMediaPreview(node, fields, values) {
  if (!node) return;
  node.hideOutputImages = true; // 只供 getNodeImageUrls / ImageCrop 取图, 不在节点上做大图预览
  const urls = [];
  for (const f of fields || []) {
    if (!MEDIA_TYPES.has(f.type)) continue;
    const raw = String(values?.[f.name] ?? "").trim();
    if (!raw) continue;
    urls.push(previewUrl(raw));
  }
  // 官方 preview store: 供 getNodeImageUrls / WidgetImageCrop 取预览
  // (节点底部会显示一张小预览图, 由 useNodePreviewState 触发, 无法关闭; 用 CSS 限高 + 节点折叠收起)
  const store = getStore("nodeOutput");
  if (store && typeof store.setNodePreviewsByNodeId === "function") {
    try {
      store.setNodePreviewsByNodeId(node.id, urls);
    } catch (err) {
      /* store 可能未就绪, 忽略 */
    }
  }
}

/**
 * 中键点击 md 表格图片预览 → 打开可缩放大图弹层。
 *
 * 必须在 **document 捕获阶段**拦截: ComfyUI 节点/画布的中键拖动处理用 pointerdown
 * 且在捕获阶段接管(表现为手形光标拖动节点), 事件到不了图片自身(target 阶段)的监听。
 * 捕获顺序 document→html→body→...→target, 在 document 捕获阶段 stopPropagation 最可靠。
 *
 * 弹层复用 node_image_middleclick 的 openImageOverlay + media_lightbox_zoom 的缩放;
 * z-index 提到最高以盖住「打开数据」弹窗。
 *
 * @param {PointerEvent} e 指针事件
 * @returns {void}
 */
function openImageZoomOnMiddleClick(e) {
  if (e.button !== 1) return;
  const target = e.target instanceof Element ? e.target : null;
  const img = target?.closest?.("img[data-fts-zoom]");
  if (!img) return;
  e.preventDefault?.();
  e.stopPropagation?.();
  const dlg = window.FallingTS?.openImageOverlay?.([img.src], 0);
  if (dlg) dlg.style.zIndex = "2147483000";
}

/**
 * 解析 md 文件 (后端路由), 返回 {ok, fields, rows, total, error}。
 *
 * @param {string} path md 绝对路径
 * @returns {Promise<object>} 读取结果
 */
async function readMd(path) {
  const resp = await fetch(
    `/fallingts_mdtable/read?path=${encodeURIComponent(path)}`
  );
  return resp.json();
}

/**
 * 构建弹窗单元格: IMAGE/MASK 列显示缩略图 + 值文本 (失败隐藏缩略图), 其余列纯文本。
 *
 * @param {object} field 字段定义 {name, type}
 * @param {string} value 单元格值
 * @param {boolean} isId 是否 ID 列
 * @returns {HTMLTableCellElement} 单元格
 */
function buildModalCell(field, value, isId) {
  const td = document.createElement("td");
  const v = String(value ?? "").trim();
  if (isId || (field.type !== "IMAGE" && field.type !== "MASK") || !v) {
    td.textContent = v;
    return td;
  }
  // 缩略图: 用后端 /preview 提供本地文件 (IMAGE/MASK 同格式)
  const thumb = document.createElement("img");
  thumb.src = previewUrl(v);
  thumb.alt = v;
  thumb.title = v + " (中键放大)";
  thumb.style.cssText =
    "max-width:48px;max-height:36px;display:block;margin:2px 0;" +
    "border-radius:3px;object-fit:cover;background:#2a2a2a;";
  thumb.dataset.ftsZoom = "1"; // document 捕获阶段中键拦截用
  thumb.addEventListener("error", () => {
    thumb.remove();
  });
  td.appendChild(thumb);
  const txt = document.createElement("div");
  txt.style.cssText = "font-size:10px;color:#9a9a9a;word-break:break-all;line-height:1.2;";
  txt.textContent = v;
  td.appendChild(txt);
  return td;
}

// ─── 数据弹窗 (打开数据) ────────────────────────────────────────────

let modalStyleInjected = false;

/**
 * 注入弹窗全局样式 (仅一次)。
 *
 * @returns {void}
 */
function injectModalStyle() {
  if (modalStyleInjected) return;
  modalStyleInjected = true;
  const style = document.createElement("style");
  style.textContent = `
.fts-md-overlay{position:fixed;inset:0;z-index:2147483000;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;font-family:'Segoe UI',Arial,sans-serif}
.fts-md-modal{background:#1e1e1e;border:1px solid #444;border-radius:8px;width:min(1240px,94vw);max-height:88vh;display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,.6);color:#ddd;font-size:12px}
.fts-md-head{padding:10px 14px;font-size:14px;font-weight:600;border-bottom:1px solid #333;display:flex;justify-content:space-between;align-items:center}
.fts-md-head .path{font-size:11px;color:#888;font-weight:400;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-left:12px}
.fts-md-search{padding:8px 14px;display:flex;gap:6px;flex-wrap:wrap;border-bottom:1px solid #333;background:#212121}
.fts-md-search input{width:130px;box-sizing:border-box;background:#171717;color:#eee;border:1px solid #444;border-radius:3px;font-size:11px;padding:3px 6px}
.fts-md-search input::placeholder{color:#777}
.fts-md-wrap{overflow:auto;padding:8px 14px;flex:1}
.fts-md-wrap table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}
.fts-md-wrap th,.fts-md-wrap td{border:1px solid #3a3a3a;padding:4px 6px;text-align:left;vertical-align:top;word-break:break-all}
.fts-md-wrap th{background:#2b2b2b;color:#ccc;position:sticky;top:0;z-index:1}
.fts-md-wrap th.radio-col{width:34px;text-align:center}
.fts-md-wrap td.radio-col{text-align:center}
.fts-md-wrap tbody tr:hover{background:#262626}
.fts-md-wrap tbody tr.selected{background:#1e3a5f}
.fts-md-type{font-size:10px;padding:0 4px;border-radius:2px;background:#333;margin-left:4px;vertical-align:middle}
.fts-md-foot{padding:10px 14px;border-top:1px solid #333;display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;background:#212121}
.fts-md-pager{display:flex;align-items:center;gap:6px;font-size:12px;flex-wrap:wrap}
.fts-md-pager select,.fts-md-pager button{background:#1f1f1f;color:#eee;border:1px solid #444;border-radius:3px;font-size:11px;padding:3px 8px;cursor:pointer}
.fts-md-pager button:disabled{opacity:.4;cursor:default}
.fts-md-btns{display:flex;gap:8px}
.fts-md-btn{background:#3a3a3a;color:#ddd;border:1px solid #555;border-radius:4px;font-size:13px;padding:6px 22px;cursor:pointer}
.fts-md-btn:disabled{opacity:.4;cursor:default}
.fts-md-btn-primary{background:#2a6df4;border-color:#2a6df4;color:#fff}
.fts-md-btn-primary:disabled{background:#3a3a3a;border-color:#555;color:#777}
`;
  document.head.appendChild(style);
}

/**
 * 打开数据弹窗: 各字段模糊搜索 + 分页 + 首列单选, 确定(选中才亮)/取消。
 *
 * @param {Array} fields 字段定义 [{name, type}]
 * @param {Array} rows 全部数据行 [{id, values}]
 * @param {Function} onConfirm 确认回调 (row) -> void
 * @param {string|null} preselectedId 已选 ID (节点当前选中行), 打开时自动定位到该行所在页并勾选
 * @returns {void}
 */
function openModal(fields, rows, onConfirm, preselectedId = null) {
  injectModalStyle();

  // 弹窗状态
  const m = {
    fields,
    all: rows,
    filtered: rows,
    page: 0,
    pageSize: 20,
    selectedId: null,
    searchInputs: [],
    uid: "fts-md-" + Math.random().toString(36).slice(2, 8),
  };

  // 已选记录预定位: 打开时自动跳到所属页并预勾选单选框
  const presel = rows.find((x) => String(x.id).trim() === String(preselectedId ?? "").trim());
  if (presel) {
    m.selectedId = presel.id;
    const idx = m.filtered.findIndex((x) => x.id === presel.id);
    if (idx >= 0) m.page = Math.floor(idx / m.pageSize);
  }

  const overlay = document.createElement("div");
  overlay.className = "fts-md-overlay";

  const modal = document.createElement("div");
  modal.className = "fts-md-modal";

  // 头部: 标题 + 文件名
  const head = document.createElement("div");
  head.className = "fts-md-head";
  head.innerHTML = `<span>打开数据<span class="path">${esc(m.fields[0]?.name ?? "ID")} 列作 ID · 共 ${m.all.length} 条</span></span>`;
  const closeX = document.createElement("span");
  closeX.textContent = "✕";
  closeX.style.cssText = "cursor:pointer;color:#888;font-size:14px;padding:0 4px";
  closeX.addEventListener("click", () => close());
  head.appendChild(closeX);
  modal.appendChild(head);

  // 顶部: 各字段模糊搜索输入
  const searchRow = document.createElement("div");
  searchRow.className = "fts-md-search";
  for (let i = 0; i < fields.length; i++) {
    const inp = document.createElement("input");
    inp.type = "text";
    inp.placeholder = `搜索 ${fields[i].name}…`;
    inp.addEventListener("input", () => {
      applyFilters();
    });
    m.searchInputs.push(inp);
    searchRow.appendChild(inp);
  }
  modal.appendChild(searchRow);

  // 表格滚动区
  const wrap = document.createElement("div");
  wrap.className = "fts-md-wrap";
  const table = document.createElement("table");
  wrap.appendChild(table);
  modal.appendChild(wrap);

  // 底部: 分页 + 取消/确定
  const foot = document.createElement("div");
  foot.className = "fts-md-foot";
  const pager = document.createElement("div");
  pager.className = "fts-md-pager";
  const sizeSelect = document.createElement("select");
  for (const n of [10, 20, 30, 50, 100]) {
    const opt = document.createElement("option");
    opt.value = String(n);
    opt.textContent = `每页 ${n}`;
    if (n === m.pageSize) opt.selected = true;
    sizeSelect.appendChild(opt);
  }
  sizeSelect.addEventListener("change", () => {
    m.pageSize = Number(sizeSelect.value);
    m.page = 0;
    render();
  });
  const info = document.createElement("span");
  const btnFirst = document.createElement("button");
  btnFirst.textContent = "首页";
  const btnPrev = document.createElement("button");
  btnPrev.textContent = "上一页";
  const btnNext = document.createElement("button");
  btnNext.textContent = "下一页";
  const btnLast = document.createElement("button");
  btnLast.textContent = "尾页";
  btnFirst.addEventListener("click", () => { m.page = 0; render(); });
  btnPrev.addEventListener("click", () => { m.page = Math.max(0, m.page - 1); render(); });
  btnNext.addEventListener("click", () => { m.page = Math.min(pageCount() - 1, m.page + 1); render(); });
  btnLast.addEventListener("click", () => { m.page = pageCount() - 1; render(); });
  pager.append(sizeSelect, btnFirst, btnPrev, info, btnNext, btnLast);

  const btns = document.createElement("div");
  btns.className = "fts-md-btns";
  const btnCancel = document.createElement("button");
  btnCancel.className = "fts-md-btn";
  btnCancel.textContent = "取消";
  btnCancel.addEventListener("click", () => close());
  const btnOk = document.createElement("button");
  btnOk.className = "fts-md-btn fts-md-btn-primary";
  btnOk.textContent = "确定";
  btnOk.disabled = true; // 未选行时灰
  btnOk.addEventListener("click", () => {
    const row = m.all.find((r) => r.id === m.selectedId);
    if (!row) return;
    close();
    onConfirm(row);
  });
  btns.append(btnCancel, btnOk);
  foot.append(pager, btns);
  modal.appendChild(foot);

  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  function pageCount() {
    return Math.max(1, Math.ceil(m.filtered.length / m.pageSize));
  }

  /**
   * 过滤全部行: 各字段搜索输入同时满足 (子串模糊匹配, 大小写不敏感)。
   *
   * @returns {void}
   */
  function applyFilters() {
    const queries = m.searchInputs.map((el) => el.value.trim().toLowerCase());
    m.filtered = m.all.filter((row) =>
      queries.every((q, i) => {
        if (!q) return true;
        const cell = i === 0 ? row.id : String(row.values?.[m.fields[i]?.name] ?? "");
        return cell.toLowerCase().includes(q);
      })
    );
    m.selectedId = null; // 过滤后选择失效
    m.page = 0;
    render();
  }

  /**
   * 渲染当前页表格 + 分页信息 + 确定按钮状态。
   *
   * @returns {void}
   */
  function render() {
    const pc = pageCount();
    m.page = Math.min(m.page, pc - 1);
    const start = m.page * m.pageSize;
    const pageRows = m.filtered.slice(start, start + m.pageSize);

    table.innerHTML = "";
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    const th0 = document.createElement("th");
    th0.className = "radio-col";
    th0.textContent = "";
    hr.appendChild(th0);
    for (const f of m.fields) {
      const th = document.createElement("th");
      th.textContent = f.name;
      th.appendChild(
        Object.assign(document.createElement("span"), {
          className: "fts-md-type",
          style: `color:${TYPE_COLORS[f.type] ?? "#9cdcfe"}`,
          textContent: f.type,
        })
      );
      hr.appendChild(th);
    }
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const row of pageRows) {
      const tr = document.createElement("tr");
      if (row.id === m.selectedId) tr.className = "selected";
      // 首列: 单选 radio (无序号)
      const td0 = document.createElement("td");
      td0.className = "radio-col";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = m.uid + "-sel";
      radio.checked = row.id === m.selectedId;
      radio.addEventListener("change", () => {
        m.selectedId = row.id;
        render(); // 重绘高亮 + 确定按钮
      });
      td0.appendChild(radio);
      tr.appendChild(td0);
      // 数据列
      for (let i = 0; i < m.fields.length; i++) {
        const val = i === 0 ? row.id : String(row.values?.[m.fields[i].name] ?? "");
        tr.appendChild(buildModalCell(m.fields[i], val, i === 0));
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);

    info.textContent = `第 ${m.page + 1}/${pc} 页 · 共 ${m.filtered.length} 条`;
    btnFirst.disabled = m.page === 0;
    btnPrev.disabled = m.page === 0;
    btnNext.disabled = m.page >= pc - 1;
    btnLast.disabled = m.page >= pc - 1;
    btnOk.disabled = m.selectedId == null; // 选中才亮起
  }

  function close() {
    overlay.remove();
  }

  render();
}

// ─── 节点 DOM 控件 ──────────────────────────────────────────────────

/**
 * 让 textarea 高度跟随内容。
 *
 * @param {HTMLTextAreaElement} ta textarea
 * @returns {void}
 */
function autoGrow(ta) {
  // 内容超过当前可视高度时增高到内容高度 (只增不减, 尊重手动拖拽的更大高度)
  if (ta.scrollHeight > ta.clientHeight) {
    ta.style.height = ta.scrollHeight + "px";
  }
}

/**
 * 创建类型标签 span (节点表单内使用, 内联样式)。
 *
 * @param {string} type 字段类型
 * @returns {HTMLSpanElement} 类型标签
 */
function mkTypeTag(type) {
  return Object.assign(document.createElement("span"), {
    style:
      `color:${TYPE_COLORS[type] ?? "#9cdcfe"};font-size:10px;padding:0 4px;` +
      "border-radius:2px;background:#333;margin-left:2px;",
    textContent: type,
  });
}

/**
 * 让节点输出端口与字段对齐: [0] ID, [1..] 各非 ID 字段, 末位 整行数据。
 *
 * @param {LGraphNode} node 节点对象
 * @param {Array} fields 字段定义
 * @returns {void}
 */
function syncOutputs(node, fields) {
  const nonId = Math.max(0, fields.length - 1);
  const target = Math.min(MAX_OUTPUTS, Math.max(2, 1 + nonId + 1)); // ID + 字段 + 整行数据
  while ((node.outputs?.length ?? 0) > target) {
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < target) {
    node.addOutput("", "*");
  }
  node.outputs[0].name = fields[0]?.name || "ID";
  node.outputs[0].type = "STRING";
  for (let i = 1; i <= nonId; i++) {
    const f = fields[i];
    // 字符串类 (STRING/TEXT/IMAGE/VIDEO/AUDIO/MASK) 端口不加大写类型后缀; INT/FLOAT/BOOLEAN 加
    const suffix = ["STRING", "TEXT", "IMAGE", "VIDEO", "AUDIO", "MASK"].includes(f.type)
      ? ""
      : ` [${f.type}]`;
    node.outputs[i].name = f.name + suffix;
    node.outputs[i].type = portTypeFor(f.type);
    if ("localized_name" in node.outputs[i]) delete node.outputs[i].localized_name;
  }
  const last = target - 1;
  node.outputs[last].name = "整行数据";
  node.outputs[last].type = "STRING";
  node.setDirtyCanvas?.(true, true);
}

/**
 * 创建节点按钮 (内联样式, 与 ComfyUI 深色主题一致)。
 *
 * @param {string} text 按钮文本
 * @returns {HTMLButtonElement} 按钮
 */
function mkNodeBtn(text) {
  const b = document.createElement("button");
  b.textContent = text;
  b.style.cssText =
    "background:#2b2b2b;color:#eee;border:1px solid #555;border-radius:3px;" +
    "font-size:11px;padding:3px 10px;cursor:pointer;";
  return b;
}

/**
 * 创建 DOM widget 根: 路径行(选择文件) + 操作行(打开数据) + 表单区 + 底部刷新。
 *
 * @returns {{root: HTMLDivElement, pathRow: HTMLDivElement, actionRow: HTMLDivElement,
 *            formEl: HTMLDivElement, refreshRow: HTMLDivElement}} DOM 引用集合
 */
function buildRoot() {
  const root = document.createElement("div");
  root.style.cssText =
    "display:flex;flex-direction:column;gap:6px;width:100%;box-sizing:border-box;padding:6px;";

  // 路径行: 选择文件按钮 + 路径输入 (可手动粘贴)
  const pathRow = document.createElement("div");
  pathRow.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:11px;";
  const btnPick = mkNodeBtn("📁 选择md文件");
  pathRow.appendChild(btnPick);
  const pathInput = document.createElement("input");
  pathInput.type = "text";
  pathInput.placeholder = "md 文件绝对路径 (可手动粘贴)";
  pathInput.style.cssText =
    "flex:1;min-width:160px;box-sizing:border-box;background:#1f1f1f;color:#eee;" +
    "border:1px solid #444;border-radius:3px;font-size:11px;padding:2px 6px;";
  pathRow.appendChild(pathInput);

  // 操作行: 打开数据 + 已选 ID
  const actionRow = document.createElement("div");
  actionRow.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:11px;color:#ccc;";
  const btnOpen = mkNodeBtn("🗂 打开数据");
  actionRow.appendChild(btnOpen);
  const selInfo = document.createElement("span");
  selInfo.style.cssText = "color:#9cdcfe;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:220px;";
  actionRow.appendChild(selInfo);

  // 表单区 (竖向排列, 按类型渲染)
  const formEl = document.createElement("div");
  formEl.style.cssText = "display:flex;flex-direction:column;gap:6px;width:100%;";

  // 底部刷新行
  const refreshRow = document.createElement("div");
  refreshRow.style.cssText = "display:flex;justify-content:flex-end;";
  const btnRefresh = mkNodeBtn("🔄 刷新");
  refreshRow.appendChild(btnRefresh);

  root.append(pathRow, actionRow, formEl, refreshRow);
  return { root, pathRow, actionRow, formEl, refreshRow, btnPick, btnOpen, btnRefresh, pathInput, selInfo };
}

/**
 * 创建 md 数据表 DOM widget: 路径/操作/表单/刷新 + 弹窗选行 + 动态输出端口。
 *
 * @param {LGraphNode} node 节点对象
 * @param {string} inputName 输入名 ("data")
 * @param {*} inputData 输入定义
 * @returns {{widget: object}} addDOMWidget 创建的 widget
 */
function createMdTableWidget(node, inputName, inputData) {
  let state = normalize(inputData?.[1]?.default ?? DEFAULT_STATE);
  const { root, formEl, btnPick, btnOpen, btnRefresh, pathInput, selInfo } = buildRoot();
  let widgetRef = null;
  let busy = false;

  function emitDirty() {
    node.setDirtyCanvas?.(true, true);
  }

  function widgetTargetHeight() {
    return Math.max(MIN_WIDGET_HEIGHT, root.offsetHeight || MIN_WIDGET_HEIGHT);
  }

  // 内容变高时把节点撑到刚好容纳 (只增不减, 尊重手动调整)
  let rafPending = false;
  function syncNodeHeight() {
    const w = widgetRef;
    if (!w || !node.graph || node.flags?.collapsed) return;
    if (typeof w.y !== "number" || w.y <= 0) return;
    const desired = w.y + widgetTargetHeight() + (w.margin ?? 10);
    if (desired > node.size[1] + 4) {
      node.setSize?.([node.size[0], Math.max(150, Math.round(desired))]);
    }
  }
  function scheduleSync() {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      syncNodeHeight();
    });
  }

  // 字段值读写
  function getVal(name) {
    return state.selected.values[name] ?? "";
  }
  function setVal(name, value) {
    state.selected.values[name] = value;
    emitDirty();
  }

  /**
   * 渲染表单区: 无选择时提示, 有选择时按字段类型逐行渲染可编辑控件 (竖向排列)。
   *
   * @returns {void}
   */
  function renderForm() {
    formEl.innerHTML = "";
    selInfo.textContent = state.selected.id ? `已选: ${state.selected.id}` : "未选择 (点「打开数据」选一行)";
    pathInput.value = state.md_path;
    // 选中行/字段变化 → 提前解析媒体字段为节点预览 (供 ImageCrop 等即时使用)
    syncNodeMediaPreview(node, state.fields, state.selected.values);

    if (!state.fields.length || !state.selected.id) {
      const hint = document.createElement("div");
      hint.style.cssText = "color:#777;font-size:11px;padding:6px 0;";
      hint.textContent = !state.md_path
        ? "① 选择md文件 → ② 打开数据选一行 → ③ 编辑表单 / 刷新"
        : "请点「打开数据」选一行数据";
      formEl.appendChild(hint);
      scheduleSync();
      return;
    }

    // 当前 ID 字段 (首列) 作为表单标题
    const idName = state.fields[0].name || "ID";
    const idTitle = document.createElement("div");
    idTitle.style.cssText = "font-size:11px;font-weight:600;color:#e0e0e0;padding:2px 0;border-bottom:1px dashed #333;";
    idTitle.appendChild(document.createTextNode(`${esc(idName)}: ${esc(state.selected.id)}`));
    formEl.appendChild(idTitle);

    for (const f of state.fields) {
      formEl.appendChild(buildFieldRow(f));
    }
    // TEXT 多行框: 挂进 DOM 后按实际内容撑高 (rAF 重测直到量到高度), 再同步节点高度
    let measureAttempts = 0;
    const measureAndSync = () => {
      let measured = false;
      for (const ta of formEl.querySelectorAll("textarea")) {
        if (ta.scrollHeight > 0) measured = true;
        autoGrow(ta);
      }
      if (!measured && measureAttempts++ < 10) {
        requestAnimationFrame(measureAndSync);
        return;
      }
      scheduleSync();
      emitDirty();
    };
    requestAnimationFrame(measureAndSync);
  }

  /**
   * 按类型构建一个字段行 (label + 控件)。
   * 类型: BOOLEAN→复选, INT/FLOAT→数字输入, IMAGE/VIDEO/AUDIO/MASK→路径+预览,
   *       TEXT→多行文本框(随内容自动撑高), STRING/其他→单行文本输入。
   *
   * @param {object} f 字段定义 {name, type}
   * @returns {HTMLDivElement} 字段行
   */
  function buildFieldRow(f) {
    const name = f.name;
    const type = f.type;
    const row = document.createElement("div");
    row.style.cssText = "display:flex;flex-direction:column;gap:2px;";

    const label = document.createElement("div");
    label.style.cssText = "font-size:11px;color:#ccc;display:flex;align-items:center;gap:4px;";
    label.appendChild(document.createTextNode(name));
    label.appendChild(mkTypeTag(type));
    row.appendChild(label);

    const inputCss =
      "width:100%;box-sizing:border-box;background:#1f1f1f;color:#eee;" +
      "border:1px solid #444;border-radius:3px;font-size:11px;padding:2px 6px;";

    if (type === "BOOLEAN") {
      const wrap = document.createElement("label");
      wrap.style.cssText = "display:flex;align-items:center;gap:6px;font-size:11px;color:#ddd;";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = getVal(name) === true;
      cb.style.cssText = "accent-color:#2a6df4;";
      cb.addEventListener("change", () => setVal(name, cb.checked));
      wrap.appendChild(cb);
      wrap.appendChild(document.createTextNode(getVal(name) === true ? "是" : "否"));
      row.appendChild(wrap);
    } else if (type === "INT" || type === "FLOAT") {
      const num = document.createElement("input");
      num.type = "number";
      num.step = type === "INT" ? "1" : "any";
      num.value = String(getVal(name));
      num.style.cssText = inputCss;
      num.addEventListener("change", () => setVal(name, num.value));
      row.appendChild(num);
    } else if (type === "IMAGE" || type === "VIDEO" || type === "AUDIO" || type === "MASK") {
      const mediaInput = document.createElement("input");
      mediaInput.type = "text";
      mediaInput.value = String(getVal(name));
      mediaInput.placeholder = "本地文件路径 或 @{ID} 引用";
      mediaInput.style.cssText = inputCss;
      mediaInput.addEventListener("change", () => {
        setVal(name, mediaInput.value);
        renderMedia();
        syncNodeMediaPreview(node, state.fields, state.selected.values);
      });
      row.appendChild(mediaInput);
      // 解析行: 显示 @{ID} 解析出的实际文件绝对路径
      const resolveLine = document.createElement("div");
      resolveLine.style.cssText = "font-size:10px;color:#8a8a8a;word-break:break-all;line-height:1.3;";
      // 预览容器 (随路径变化刷新)
      const previewBox = document.createElement("div");
      const renderMedia = () => {
        previewBox.innerHTML = "";
        const raw = String(getVal(name)).trim();
        if (!raw) {
          resolveLine.textContent = "";
          return;
        }
        resolveLine.textContent = "解析中…";
        // 后端解析实际文件地址 (@{ID} -> output/input 目录匹配)
        fetch(`/fallingts_mdtable/resolve?path=${encodeURIComponent(raw)}&kind=${type}`)
          .then((r) => r.json())
          .then((d) => {
            resolveLine.textContent = d.ok ? "文件: " + d.path : "未找到文件 (可手填路径)";
          })
          .catch(() => {
            resolveLine.textContent = "";
          });
        const isImage = type === "IMAGE" || type === "MASK";
        const el = document.createElement(isImage ? "img" : type.toLowerCase());
        el.src = previewUrl(raw);
        if (!isImage) el.controls = true;
        if (isImage) {
          el.title = "中键放大预览";
          el.dataset.ftsZoom = "1"; // document 捕获阶段中键拦截用
        }
        el.style.cssText =
          "max-width:320px;max-height:180px;display:block;margin-top:4px;border-radius:4px;";
        el.addEventListener("error", () => {
          previewBox.innerHTML = "";
          const tip = document.createElement("div");
          tip.style.cssText = "color:#c66;font-size:11px;margin-top:2px;";
          tip.textContent = "无法预览该文件";
          previewBox.appendChild(tip);
        });
        previewBox.appendChild(el);
      };
      renderMedia();
      row.appendChild(resolveLine);
      row.appendChild(previewBox);
    } else if (type === "TEXT") {
      // 多行文本框: 右下角可拖动高度, 内容超出现有高度时自动增高
      const ta = document.createElement("textarea");
      ta.value = String(getVal(name));
      ta.rows = Math.min(8, Math.max(2, String(getVal(name)).split("\n").length));
      ta.placeholder = "多行文本";
      ta.style.cssText =
        inputCss + "resize:vertical;overflow-y:auto;line-height:1.4;";
      ta.addEventListener("input", () => {
        setVal(name, ta.value);
        autoGrow(ta);
        scheduleSync();
      });
      row.appendChild(ta);
      autoGrow(ta);
    } else {
      // STRING / 未知 -> 单行文本输入
      const inp = document.createElement("input");
      inp.type = "text";
      inp.value = String(getVal(name));
      inp.style.cssText = inputCss;
      inp.addEventListener("change", () => setVal(name, inp.value));
      row.appendChild(inp);
    }
    return row;
  }

  // ── 按钮行为 ────────────────────────────────────────────────────

  // 选择文件: 后端 tkinter 系统选择器 -> 绝对路径 -> 读 md 更新字段/清空选择
  btnPick.addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    btnPick.textContent = "⏳ 选择中…";
    try {
      const resp = await fetch("/fallingts_mdtable/select_file", { method: "POST" });
      const data = await resp.json();
      if (!data.ok) {
        app.extensionManager.toast.add({ severity: "error", summary: data.error || "选择文件失败" });
        return;
      }
      await loadFromFile(data.path);
    } catch (err) {
      console.error("[FallingTS.MdTable] 选择文件失败:", err);
      app.extensionManager.toast.add({ severity: "error", summary: "选择文件失败: 无法连接后端" });
    } finally {
      busy = false;
      btnPick.textContent = "📁 选择md文件";
    }
  });

  // 路径框手动粘贴: 只记录路径, 需再点「打开数据」读取
  pathInput.addEventListener("change", () => {
    state.md_path = pathInput.value.trim();
    emitDirty();
  });

  // 打开数据: 重新解析 md -> 弹窗选行 -> 载入表单
  btnOpen.addEventListener("click", async () => {
    if (busy) return;
    if (!state.md_path) {
      app.extensionManager.toast.add({ severity: "warning", summary: "请先选择 md 文件" });
      return;
    }
    busy = true;
    btnOpen.textContent = "⏳ 读取中…";
    try {
      const r = await readMd(state.md_path);
      if (!r.ok) {
        app.extensionManager.toast.add({ severity: "error", summary: r.error || "读取失败" });
        return;
      }
      openModal(r.fields, r.rows, (row) => {
        state.fields = r.fields;
        state.selected = {
          id: String(row.id).trim(),
          values: coerceDisplayAll(row.values, r.fields),
        };
        renderForm();
        syncOutputs(node, state.fields);
        emitDirty();
      }, state.selected.id);
    } catch (err) {
      console.error("[FallingTS.MdTable] 读取失败:", err);
      app.extensionManager.toast.add({ severity: "error", summary: "读取 md 文件失败" });
    } finally {
      busy = false;
      btnOpen.textContent = "🗂 打开数据";
    }
  });

  // 刷新: 按 ID 重查 md 文件 -> 用磁盘最新值更新表单
  btnRefresh.addEventListener("click", async () => {
    if (busy) return;
    if (!state.md_path) {
      app.extensionManager.toast.add({ severity: "warning", summary: "请先选择 md 文件" });
      return;
    }
    if (!state.selected.id) {
      app.extensionManager.toast.add({ severity: "warning", summary: "还没有选择数据, 请先「打开数据」选一行" });
      return;
    }
    busy = true;
    btnRefresh.textContent = "⏳ 刷新中…";
    try {
      const r = await readMd(state.md_path);
      if (!r.ok) {
        app.extensionManager.toast.add({ severity: "error", summary: r.error || "读取失败" });
        return;
      }
      // 匹配按 trim 后的 ID 找 (md 手改可能留空格)
      const targetId = String(state.selected.id).trim();
      const row = r.rows.find((x) => String(x.id).trim() === targetId);
      if (!row) {
        app.extensionManager.toast.add({ severity: "error", summary: `md 文件中找不到 ID「${state.selected.id}」(可能已被删除)` });
        return;
      }
      state.fields = r.fields;
      state.selected = { id: String(row.id).trim(), values: coerceDisplayAll(row.values, r.fields) };
      renderForm();
      syncOutputs(node, state.fields);
      emitDirty();
    } catch (err) {
      console.error("[FallingTS.MdTable] 刷新失败:", err);
      app.extensionManager.toast.add({ severity: "error", summary: "刷新失败: 无法连接后端" });
    } finally {
      busy = false;
      btnRefresh.textContent = "🔄 刷新";
    }
  });

  // ── 载入文件: 读 md -> 更新字段, 清空选择 ──────────────────────
  /**
   * 设置 md 路径并读取解析, 更新字段与路径显示。
   *
   * @param {string} path md 绝对路径
   * @returns {Promise<void>}
   */
  async function loadFromFile(path) {
    const r = await readMd(path);
    if (!r.ok) {
      app.extensionManager.toast.add({ severity: "error", summary: r.error || "读取失败" });
      return;
    }
    state.md_path = path;
    state.fields = r.fields;
    state.selected = { id: "", values: {} };
    renderForm();
    syncOutputs(node, state.fields);
    emitDirty();
  }

  // ── widget 挂载 ─────────────────────────────────────────────────

  const widget = node.addDOMWidget(inputName, "fallingts_md_table", root, {
    getValue: () => state,
    setValue: (v) => {
      state = normalize(v);
      renderForm();
      syncOutputs(node, state.fields);
    },
    getMinHeight: () => widgetTargetHeight(),
    serialize: true,
  });
  widgetRef = widget;

  // 新节点: 按默认字段 (空) 对齐输出
  renderForm();
  syncOutputs(node, state.fields);

  // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次
  const prevOnConfigure = node.onConfigure;
  node.onConfigure = function (info) {
    prevOnConfigure?.call(this, info);
    state = normalize(state);
    renderForm();
    syncOutputs(node, state.fields);
  };

  node.setSize?.([
    Math.max(node.size?.[0] ?? 700, 480),
    Math.max(node.size?.[1] ?? 240, 260),
  ]);
  return { widget };
}

// ─── 扩展注册 ───────────────────────────────────────────────────────

app.registerExtension({
  name: "FallingTS.MarkDownTable",

  /**
   * 节点定义注册前钩子: 节点创建后按字段对齐输出端口。
   *
   * @param {Function} nodeType 节点类型构造函数
   * @param {object} nodeData 节点定义数据
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 新节点/加载工作流时按状态字段对齐输出端口。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const w = this.widgets?.find((w) => w.name === "data");
      const st = normalize(w?.value ?? DEFAULT_STATE);
      syncOutputs(this, st.fields);
      syncNodeMediaPreview(this, st.fields, st.selected.values);
    };
  },

  /**
   * 注册自定义 widget 工厂: FALLINGTS_MD_TABLE 类型 -> createMdTableWidget。
   *
   * @returns {object} 自定义 widget 工厂映射表
   */
  getCustomWidgets() {
    return {
      [WIDGET_TYPE](node, inputName, inputData) {
        return createMdTableWidget(node, inputName, inputData);
      },
    };
  },

  /**
   * 扩展初始化: document 捕获阶段拦截 md 表格预览图的中键点击。
   *
   * 必须在捕获阶段做 —— ComfyUI 节点拖动/画布平移会在 pointerdown 捕获阶段接管中键,
   * 事件到不了图片自身(target 阶段)的监听。
   *
   * @returns {void}
   */
  /**
   * 扩展初始化: 注入 CSS 隐藏节点底部预览图; document 捕获阶段拦截 md 表格预览图的中键点击。
   *
   * 节点底部那张预览图是 ComfyUI 供 getNodeImageUrls / ImageCrop 拖框预览用的(useNodePreviewState
   * 自动渲染), 用 CSS display:none 隐藏其显示即可 —— preview store 数据不受影响,
   * ImageCropV2 仍能正常取图拖框。
   * 选择器用 preview URL 特征 + 排除表单缩略图(data-fts-zoom), 不影响字段内嵌预览。
   *
   * @returns {void}
   */
  setup() {
    // 隐藏 MD 表节点底部预览图 + 分辨率文字(仅 JS 方案)。
    // 定位: node-type="FallingTSMarkDownTable" → 往上 data-testid="node-widgets"
    //   → 再往上找第一个「兄弟含 MD 表预览图」的祖元素 → 隐藏 img 与其后的 div(分辨率)。
    // 只命中 MD 表节点自身, 不影响 ImageCropV2 等引用同一预览图的节点。
    // preview store 数据不受影响, ImageCropV2 仍能取图拖框。
    const hideMdPreview = () => {
      document.querySelectorAll('[node-type="FallingTSMarkDownTable"]').forEach((mdEl) => {
        let widgets = mdEl;
        while (widgets && widgets.dataset?.testid !== "node-widgets") widgets = widgets.parentElement;
        if (!widgets) return;
        let node = widgets;
        while (node && node.parentElement) {
          const parent = node.parentElement;
          const img = Array.from(parent.children).find(
            (el) => el !== node && el.tagName === "IMG" &&
              (el.getAttribute("src") || "").includes("fallingts_mdtable/preview")
          );
          if (img) {
            img.style.display = "none";
            const next = img.nextElementSibling;
            if (next && next.tagName === "DIV") next.style.display = "none";
            return;
          }
          node = parent;
        }
      });
    };
    hideMdPreview();
    const obs = new MutationObserver(hideMdPreview);
    obs.observe(document.body, { childList: true, subtree: true });

    document.addEventListener("pointerdown", openImageZoomOnMiddleClick, true);
  },
});
