// FallingTS 通用表格前端控件 (Excel 式, 数据内嵌工作流, 不读外部文件):
// - 最左侧固定「索引」列 (从 0 开始), 其后 A/B/C... 列 (Excel 列名规则, 最多 52 列);
// - 底部「行数/列数」数字输入框 (最少 1), 修改列数时右侧输出端口随之增减;
// - 所有单元格为字符串, 输出固定 STRING; 类型转换由下游节点自行完成。
//
// 值 (对象 {row_count, col_count, data}) 直接作为 widget 值序列化进工作流 widgets_values,
// 与后端 FallingTSTable 节点输入 "rows" 同名对接, 保证:
//   1. 保存/加载工作流时完整还原;
//   2. 前端构建 API prompt 时 rows 能按 widget.name 写入输入。
//
// 输出端口动态增删: 后端声明最多 MAX_COLS 个 STRING 输出;
// 前端根据列数 removeOutput/addOutput。加载工作流时 configure 的 cloneObject
// 先按保存的 outputs 覆盖端口, 再在 widget.setValue / onConfigure 中按列数对齐。
//
// 格子高度自适应 (2026-08-05):
// - 每个单元格是 textarea, 输入时按内容 (scrollHeight) 自动撑高, 整行随之变高,
//   不再需要手动拖拽 resize 手柄;
// - 表格整体高度会带动节点长高 (最多到滚动区上限), 内容清空后节点保持高度,
//   不会反向收缩打扰手动调整过的尺寸;
// - 鼠标滚轮在格子内滚动时优先滚动表格, 表格不能滚时才交给画布 (缩放/平移)。
import { app } from "../../../scripts/app.js";

const WIDGET_TYPE = "FALLINGTS_TABLE";
const MAX_COLS = 52;
const MIN_WIDGET_HEIGHT = 200; // 表格控件最小高度 (滚动区 420 + 底部行/列控件等)

const DEFAULT_STATE = {
  row_count: 3,
  col_count: 3,
  first_col_is_id: false,
  data: [
    ["", "", ""],
    ["", "", ""],
    ["", "", ""],
  ],
};

// 0->A, 25->Z, 26->AA ... 51->AZ (Excel 列名规则)
function colName(i) {
  let s = "";
  let n = i + 1;
  while (n > 0) {
    n -= 1;
    s = String.fromCharCode(65 + (n % 26)) + s;
    n = Math.floor(n / 26);
  }
  return s;
}

function normalize(v) {
  // 旧版兼容: 数组形式的行对象 (正|负|宽|高|批次) -> 转成 A..E 五列网格
  if (Array.isArray(v)) {
    const data = v.map((r) => [
      String(r?.pos ?? ""),
      String(r?.neg ?? ""),
      String(r?.w ?? 928),
      String(r?.h ?? 1664),
      String(r?.batch ?? 1),
    ]);
    const cc = data.length
      ? Math.max(...data.map((row) => row.length))
      : DEFAULT_STATE.col_count;
    return {
      row_count: Math.max(1, data.length),
      col_count: Math.min(MAX_COLS, Math.max(1, cc)),
      first_col_is_id: false,
      data,
    };
  }
  const s = v && typeof v === "object" ? v : {};
  const row_count = Math.max(1, Math.floor(Number(s.row_count)) || 1);
  const col_count = Math.min(
    MAX_COLS,
    Math.max(1, Math.floor(Number(s.col_count)) || 1)
  );
  const src = Array.isArray(s.data) ? s.data : [];
  const data = [];
  for (let r = 0; r < row_count; r++) {
    const srcRow = Array.isArray(src[r]) ? src[r] : [];
    const row = [];
    for (let c = 0; c < col_count; c++) row.push(String(srcRow[c] ?? ""));
    data.push(row);
  }
  return { row_count, col_count, first_col_is_id: s.first_col_is_id === true, data };
}

// 让节点输出端口与列数对齐: 首列为 ID 时第 0 端口命名 ID, 其后 A/B/C..., 类型固定 STRING
function syncOutputs(node, colCount, firstColIsId = false) {
  const target = Math.min(
    MAX_COLS,
    Math.max(1, Math.floor(Number(colCount)) || 1)
  );
  while ((node.outputs?.length ?? 0) > target) {
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < target) {
    node.addOutput("", "STRING");
  }
  for (let i = 0; i < target; i++) {
    const o = node.outputs[i];
    o.name = firstColIsId ? (i === 0 ? "ID" : colName(i - 1)) : colName(i);
    o.type = "STRING";
    // 纯字母输出: 清掉旧版/历史遗留的本地化显示名 (如"高度"/"批次"),
    // 画布上始终只显示 ID/A/B/C/D/E...
    if ("localized_name" in o) delete o.localized_name;
    if ("label" in o) delete o.label;
  }
  node.setDirtyCanvas?.(true, true);
}

// 清理旧版本残留、当前节点定义里不存在的输入槽 (如旧版 clip 输入),
// 避免加载旧工作流后构建 prompt 时报 "unknown input" 校验错误。
function pruneStaleInputs(node) {
  const def = node.constructor?.nodeData;
  const valid = new Set();
  for (const cat of ["required", "optional"]) {
    for (const k of Object.keys(def?.input?.[cat] ?? {})) valid.add(k);
  }
  for (let i = (node.inputs?.length ?? 0) - 1; i >= 0; i--) {
    if (!valid.has(node.inputs[i].name)) node.removeInput(i);
  }
}

function buildRoot() {
  const root = document.createElement("div");
  root.style.cssText =
    "display:flex;flex-direction:column;gap:6px;width:100%;box-sizing:border-box;padding:6px;";

  const scroll = document.createElement("div");
  scroll.style.cssText = "overflow:auto;max-height:420px;width:100%;";
  const table = document.createElement("table");
  table.style.cssText =
    "width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed;";
  scroll.appendChild(table);

  const footer = document.createElement("div");
  footer.style.cssText =
    "display:flex;align-items:center;gap:8px;font-size:12px;color:#ccc;flex-wrap:wrap;";

  root.appendChild(scroll);
  root.appendChild(footer);
  return { root, scroll, table, footer };
}

function mkLabel(text) {
  const s = document.createElement("span");
  s.textContent = text;
  return s;
}

function mkNumInput(min, max, value, onChange) {
  const inp = document.createElement("input");
  inp.type = "number";
  inp.min = String(min);
  inp.max = String(max);
  inp.value = String(value);
  inp.style.cssText =
    "width:64px;box-sizing:border-box;background:#1f1f1f;color:#eee;" +
    "border:1px solid #444;border-radius:3px;font-size:11px;padding:2px 4px;";
  const commit = () => {
    let v = Math.floor(Number(inp.value));
    if (!Number.isFinite(v)) v = min;
    v = Math.min(max, Math.max(min, v));
    inp.value = String(v);
    onChange(v);
  };
  inp.addEventListener("change", commit);
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter") inp.blur();
  });
  return inp;
}

// 让 textarea 高度跟随内容 (scrollHeight), 内容为空/元素未显示时保持原样
function autoGrow(ta) {
  ta.style.height = "auto";
  const h = ta.scrollHeight;
  if (h > 0) ta.style.height = h + "px";
}

function createTableWidget(node, inputName, inputData) {
  let state = normalize(inputData?.[1]?.default ?? DEFAULT_STATE);
  const { root, scroll, table, footer } = buildRoot();

  // addDOMWidget 返回后赋值; 用于读取 widget.y / margin 推算节点高度
  let widgetRef = null;
  // 一帧内多次输入只同步一次节点高度
  let rafPending = false;

  function emitDirty() {
    node.setDirtyCanvas?.(true, true);
  }

  // 表格控件当前应有的高度 = 表格实际渲染高度(受滚动区 max-height 限制)
  // + 底部行/列控件 + 容器上下 padding
  function currentWidgetTargetHeight() {
    return Math.max(
      MIN_WIDGET_HEIGHT,
      (scroll?.offsetHeight ?? 0) + (footer?.offsetHeight ?? 0) + 12
    );
  }

  // 内容变高时把节点撑到刚好容纳表格控件 (只增不减, 尊重用户手动调过的尺寸)
  function syncNodeHeight() {
    const w = widgetRef;
    if (!w || !node.graph) return;
    if (node.flags?.collapsed) return;
    // w.y 在第一次布局前为 0, 无法推算节点高度, 跳过 (等布局完成后再同步)
    if (typeof w.y !== "number" || w.y <= 0) return;
    const desired = w.y + currentWidgetTargetHeight() + (w.margin ?? 10);
    if (desired > node.size[1] + 4) {
      node.setSize?.([node.size[0], Math.max(120, Math.round(desired))]);
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

  function render() {
    table.innerHTML = "";

    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    const indexTh = document.createElement("th");
    indexTh.textContent = "索引";
    indexTh.style.cssText =
      "border:1px solid #555;padding:3px;background:#333;color:#ccc;" +
      "position:sticky;left:0;z-index:1;";
    indexTh.style.width = "44px";
    hr.appendChild(indexTh);
    for (let c = 0; c < state.col_count; c++) {
      const th = document.createElement("th");
      // 首列为 ID 时, 第 0 列表头显示 ID, 其后 A/B/C...
      th.textContent = state.first_col_is_id
        ? c === 0
          ? "ID"
          : colName(c - 1)
        : colName(c);
      th.style.cssText =
        "border:1px solid #555;padding:3px;background:#333;color:#ccc;";
      th.style.width = "120px";
      hr.appendChild(th);
    }
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (let r = 0; r < state.row_count; r++) {
      const tr = document.createElement("tr");
      const num = document.createElement("td");
      num.textContent = String(r);
      num.style.cssText =
        "border:1px solid #555;padding:2px;text-align:center;color:#aaa;" +
        "background:#2a2a2a;position:sticky;left:0;";
      tr.appendChild(num);

      for (let c = 0; c < state.col_count; c++) {
        const td = document.createElement("td");
        td.style.cssText = "border:1px solid #555;padding:2px;";
        const ta = document.createElement("textarea");
        ta.value = state.data[r][c];
        ta.rows = 1;
        ta.style.cssText =
          "width:100%;box-sizing:border-box;resize:none;overflow:hidden;" +
          "line-height:1.4;background:#1f1f1f;color:#eee;border:1px solid #444;" +
          "border-radius:3px;font-size:11px;padding:2px;";
        ta.addEventListener("input", () => {
          state.data[r][c] = ta.value;
          autoGrow(ta);
          emitDirty();
          scheduleSync();
        });
        // 滚轮: 表格可滚动时优先滚动表格; 否则(含 Ctrl 缩放/横向)交给画布
        ta.addEventListener(
          "wheel",
          (e) => {
            if (e.ctrlKey) return;
            if (scroll.scrollHeight <= scroll.clientHeight) return;
            if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
            e.preventDefault();
            e.stopPropagation();
            scroll.scrollTop += e.deltaY;
          },
          { passive: false }
        );
        td.appendChild(ta);
        tr.appendChild(td);
        // 已在 DOM 中, 立即按已有内容撑高 (初始为空时无影响)
        autoGrow(ta);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);

    // 底部: 选择下拉 + 行数 / 列数 (最少 1) + 首列ID
    footer.innerHTML = "";
    footer.appendChild(mkLabel("选择:"));
    const sel = document.createElement("select");
    sel.style.cssText =
      "width:170px;box-sizing:border-box;background:#1f1f1f;color:#eee;" +
      "border:1px solid #444;border-radius:3px;font-size:11px;padding:2px 4px;";
    for (let r = 0; r < state.row_count; r++) {
      const opt = document.createElement("option");
      opt.value = String(r);
      // 首列为 ID 时以第 0 列内容作标签, 否则用「第N行」
      const id = state.first_col_is_id
        ? String(state.data[r]?.[0] ?? "").trim()
        : "";
      opt.textContent = id || `第${r + 1}行`;
      sel.appendChild(opt);
    }
    // 默认跟随当前 index widget 值
    const curIdx = node.widgets?.find((w) => w.name === "index")?.value;
    if (Number.isFinite(curIdx) && curIdx >= 0 && curIdx < state.row_count) {
      sel.value = String(curIdx);
    }
    // 选择 -> 写 index widget, 下次 Run 输出该行
    sel.addEventListener("change", () => {
      const w = node.widgets?.find((w) => w.name === "index");
      const idx = Number(sel.value);
      if (!w) return;
      w.value = idx;
      w.callback?.(idx);
      node.setDirtyCanvas?.(true, true);
    });
    footer.appendChild(sel);
    footer.appendChild(mkLabel("行数:"));
    const rowInput = mkNumInput(1, 100000, state.row_count, (v) => {
      state.row_count = v;
      resizeData();
      render();
      emitDirty();
    });
    footer.appendChild(rowInput);
    footer.appendChild(mkLabel("列数:"));
    const colInput = mkNumInput(1, MAX_COLS, state.col_count, (v) => {
      state.col_count = v;
      resizeData();
      render();
      syncOutputs(node, state.col_count, state.first_col_is_id);
      emitDirty();
    });
    footer.appendChild(colInput);
    footer.appendChild(
      mkLabel(`(${state.row_count} 行 × ${state.col_count} 列)`)
    );
    // 首列为 ID: 控制表头/端口命名与下拉标签来源
    const idCb = document.createElement("input");
    idCb.type = "checkbox";
    idCb.checked = state.first_col_is_id === true;
    idCb.style.cssText = "accent-color:#999;";
    idCb.addEventListener("change", () => {
      state.first_col_is_id = idCb.checked;
      render();
      syncOutputs(node, state.col_count, state.first_col_is_id);
      emitDirty();
    });
    footer.appendChild(idCb);
    footer.appendChild(mkLabel("首列ID"));

    // 内容已重建: 等布局完成后统一撑高所有格子并同步节点高度;
    // 若控件还没挂载/显示 (如加载工作流早期) 量到的高度为 0, 最多重试几帧再量
    let measureAttempts = 0;
    const measureAndSync = () => {
      let measured = false;
      for (const ta of table.querySelectorAll("textarea")) {
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

  function resizeData() {
    const rc = state.row_count;
    const cc = state.col_count;
    const data = [];
    for (let r = 0; r < rc; r++) {
      const row = [];
      for (let c = 0; c < cc; c++) {
        row.push(String(state.data[r]?.[c] ?? ""));
      }
      data.push(row);
    }
    state.data = data;
  }

  const widget = node.addDOMWidget(inputName, "fallingts_table", root, {
    getValue: () => state,
    setValue: (v) => {
      state = normalize(v);
      render();
      syncOutputs(node, state.col_count, state.first_col_is_id);
    },
    getMinHeight: () => currentWidgetTargetHeight(),
    serialize: true,
  });
  widgetRef = widget;

  // 新节点: 按默认列数裁剪后端声明的最多 52 个输出
  render();
  syncOutputs(node, state.col_count, state.first_col_is_id);

  // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次输出
  const prevOnConfigure = node.onConfigure;
  node.onConfigure = function (info) {
    prevOnConfigure?.call(this, info);
    state = normalize(state);
    syncOutputs(node, state.col_count, state.first_col_is_id);
    pruneStaleInputs(node);
  };

  node.setSize?.([
    Math.max(node.size?.[0] ?? 700, 720),
    Math.max(node.size?.[1] ?? 320, 360),
  ]);
  return { widget };
}

app.registerExtension({
  name: "FallingTS.TableLookup",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== "FallingTSTable") return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      // 节点完全构建后 (输出端口已按后端声明填充为 MAX_COLS 个):
      // 新节点按默认列数裁剪; 加载工作流时 configure 会先恢复保存的输出,
      // 再由 widget.setValue / onConfigure 按保存的列数对齐。
      const w = this.widgets?.find((w) => w.name === "rows");
      const st = normalize(w?.value ?? DEFAULT_STATE);
      syncOutputs(this, st.col_count, st.first_col_is_id);
    };
  },
  getCustomWidgets() {
    return {
      [WIDGET_TYPE](node, inputName, inputData) {
        return createTableWidget(node, inputName, inputData);
      },
    };
  },
});
