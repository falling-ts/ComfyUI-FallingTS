/**
 * FallingTS 运行前命令 (2026-09-30)。
 *
 * 需求: 每次「点击运行」或 Ctrl+Enter 提交之前, 先执行一条在系统设置里配置的命令; 配置为空则跳过。
 *
 * 挂点: `app.queuePrompt` 是前端**唯一的提交入口** ——
 *   - 运行按钮 ComfyQueueButton → 命令 `Comfy.QueuePrompt` → `app.queuePrompt(0, batchCount, {intent})`
 *   - Ctrl+Enter 就是这个命令的默认键位
 *   - Shift+运行 = `Comfy.QueuePromptFront`(排到队首), 同样走 `app.queuePrompt(-1, ...)`
 *   所以包装它即可覆盖用户要求的两种触发方式, 不必逐个去挂按钮/键位。
 *
 * ⚠️ 只在「默认 Run」上执行(第三参没有显式 queueNodeIds): 继续/截帧那类 partial 提交是"往下跑一段",
 *    不是新的一次运行, 每截一帧就重跑一次前置命令会很莫名其妙(例如重复拷贝输入文件)。
 *    要变成"任何提交都执行", 去掉 `isDefaultRun(...)` 判断即可。
 *
 * 语义(与后端 pre-run/nodes.py 对齐): 非 0 退出码 / 超时 → **取消本次提交**(等价 pre-commit 拦下 commit)
 * 并弹 error toast; 命令为空 → 完全跳过, 连后端都不请求。
 *
 * 设置项位置: 侧栏「常规 › 其他」面板里, 排在「成功或失败提示音」下面 ——
 *   单元素 category 会被前端 buildTree 变成 root 叶子, 再被 useSettingUI 收进合成的 'Other' 节点;
 *   右栏各组按 sortOrder **降序**排(见 SettingDialog.vue 的 sortedGroups), 故本项 10、提示音那项 20。
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const SETTING_ID = "FallingTS.PreRun.Command";
const ENDPOINT = "/fallingts_prerun/run";

/**
 * 读取当前配置的命令(设置服务不可用时按空串处理 = 跳过, 保证本扩展永不成为提交链路的故障点)。
 * @returns {string} 去空白后的命令; 空串表示未配置
 */
function getCommand() {
  try {
    return String(app.ui?.settings?.getSettingValue(SETTING_ID) ?? "").trim();
  } catch {
    return "";
  }
}

/**
 * 判断这次提交是不是「默认 Run」。
 * 原生 Run 传 `{intent}`(没有 queueNodeIds); partial 提交传节点 id 数组或 `{queueNodeIds:[...]}`。
 * @param {unknown} third queuePrompt 的第三参
 * @returns {boolean} true = 默认 Run(应当执行前置命令)
 */
function isDefaultRun(third) {
  if (third === undefined || third === null) return true;
  if (Array.isArray(third)) return third.length === 0;
  if (typeof third === "object") return !third.queueNodeIds?.length;
  return true;
}

/**
 * 请求后端执行前置命令。
 * 网络/服务异常一律转成 `{ok:false}`, 由调用方决定取消提交, 不向上抛。
 * @param {string} command 命令原文
 * @returns {Promise<{ok:boolean, skipped?:boolean, code?:number|null, output?:string, cwd?:string, ms?:number, timeout?:boolean, error?:string}>}
 */
async function runPreCommand(command) {
  try {
    const resp = await api.fetchApi(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    const data = await resp.json().catch(() => null);
    if (data) return data;
    return { ok: false, error: `HTTP ${resp.status} ${resp.statusText || ""}`.trim() };
  } catch (err) {
    return { ok: false, error: `无法连接后端: ${err?.message || err}` };
  }
}

/** 失败时弹提示(toast 不可用则只留控制台)。 */
function notifyFailure(title, detail) {
  console.error(`[FallingTS.PreRun] ${title}\n${detail}`);
  try {
    app.extensionManager?.toast?.add({
      severity: "error",
      summary: title,
      detail: String(detail || "").slice(-600),
      life: 12000,
    });
  } catch { /* toast 服务不可用时忽略(已有 console) */ }
}

app.registerExtension({
  name: "FallingTS.PreRunCommand",

  /**
   * 扩展初始化: 注册设置项, 并包装全局提交入口 app.queuePrompt。
   * @returns {void}
   */
  setup() {
    // 1. 设置项: 普通 text 设置(前端 FormItem 对未知 type 一律回退 InputText),
    //    自带标签 + 问号 tooltip + 焦点/持久化, 无需自绘 HTML。
    try {
      app.ui?.settings?.addSetting({
        id: SETTING_ID,
        name: "开始前命令",
        type: "text",
        defaultValue: "",
        category: ["开始前命令"],
        sortOrder: 10,
        tooltip:
          "每次点击「运行」或按 Ctrl+Enter 提交之前, 在宿主上执行这条命令; 留空则不执行。" +
          "命令在 Comfy 工作区根目录(即 custom_nodes 的上一级, 本机 D:\\AI\\Comfy)下执行, " +
          "所以 scripts\\xxx.py 这类相对路径可直接写。非 0 退出码或超时(10 分钟)会取消本次运行; " +
          "输出与退出码记在 ComfyUI\\user\\comfyui.log。继续/截帧这类局部执行不触发。",
        attrs: {
          style: "width: 30rem",
          placeholder: "留空 = 不执行; 例: .venv\\Scripts\\python.exe scripts\\prep.py",
        },
      });
    } catch { /* 设置面板不可用时功能静默降级 */ }

    // 2. 包装提交入口(与 proceed/preview-video/route/fanout 的包装链叠加, 顺序无关)
    const orig = app.queuePrompt?.bind(app);
    if (!orig) return;
    /**
     * 包装 queuePrompt: 默认 Run 且配了命令时, 先同步执行命令并等它结束, 成功才提交。
     * 参数原样透传(第三参可能是节点数组, 也可能是 {queueNodeIds,intent} 选项对象)。
     * @param {...unknown} args 原始 queuePrompt 实参
     * @returns {Promise<boolean|unknown>} 命令失败时返回 false(未提交)
     */
    app.queuePrompt = async function (...args) {
      const command = getCommand();
      if (command && isDefaultRun(args[2])) {
        const res = await runPreCommand(command);
        if (res?.ok === false) {
          const code = res.timeout ? "超时" : `退出码 ${res.code ?? "?"}`;
          notifyFailure(
            "开始前命令失败, 已取消本次运行",
            `${command}\n── ${code} (${res.cwd || "?"}, ${res.ms ?? "?"}ms)\n${res.output || res.error || ""}`
          );
          return false;
        }
        if (res?.output) {
          console.log(
            `[FallingTS.PreRun] 完成 ${res.ms}ms (cwd=${res.cwd})\n${res.output}`
          );
        }
      }
      return orig(...args);
    };
  },
});
