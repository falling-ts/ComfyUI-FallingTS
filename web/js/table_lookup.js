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
import { app } from "../../../scripts/app.js";

const WIDGET_TYPE = "FALLINGTS_TABLE";
const MAX_COLS = 52;

const DEFAULT_STATE = {
  row_count: 3,
  col_count: 3,
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
  return { row_count, col_count, data };
}

// 让节点输出端口与列数对齐: 名称固定 A/B/C..., 类型固定 STRING
function syncOutputs(node, colCount) {
  const target = Math.min(
    MAX_COLS,
    Math.max(1, Math.floor(Number(colCount)) || 1)
  );
  while ((node.outputs?.length ?? 0) > target) {
    node.removeOutput(node.outputs.length - 1);
  }
  while ((node.outputs?.length ?? 0) < target) {
    node.addOutput(colName(node.outputs.length), "STRING");
  }
  for (let i = 0; i < target; i++) {
    const o = node.outputs[i];
    o.name = colName(i);
    o.type = "STRING";
    // 纯字母输出: 清掉旧版/历史遗留的本地化显示名 (如"高度"/"批次"),
    // 画布上始终只显示 A/B/C/D/E...
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
  return { root, table, footer };
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

function createTableWidget(node, inputName, inputData) {
  let state = normalize(inputData?.[1]?.default ?? DEFAULT_STATE);
  const { root, table, footer } = buildRoot();

  function emitDirty() {
    node.setDirtyCanvas?.(true, true);
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
      th.textContent = colName(c);
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
          "width:100%;box-sizing:border-box;resize:vertical;background:#1f1f1f;" +
          "color:#eee;border:1px solid #444;border-radius:3px;font-size:11px;padding:2px;";
        ta.addEventListener("input", () => {
          state.data[r][c] = ta.value;
          emitDirty();
        });
        td.appendChild(ta);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);

    // 底部: 行数 / 列数 (最少 1)
    footer.innerHTML = "";
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
      syncOutputs(node, state.col_count);
      emitDirty();
    });
    footer.appendChild(colInput);
    footer.appendChild(
      mkLabel(`(${state.row_count} 行 × ${state.col_count} 列)`)
    );
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
      syncOutputs(node, state.col_count);
    },
    getMinHeight: () => 200,
    serialize: true,
  });

  // 新节点: 按默认列数裁剪后端声明的最多 52 个输出
  render();
  syncOutputs(node, state.col_count);

  // 加载/还原工作流: configure 末尾 (widgets_values 已应用) 再对齐一次输出
  const prevOnConfigure = node.onConfigure;
  node.onConfigure = function (info) {
    prevOnConfigure?.call(this, info);
    state = normalize(state);
    syncOutputs(node, state.col_count);
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
      syncOutputs(this, st.col_count);
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
