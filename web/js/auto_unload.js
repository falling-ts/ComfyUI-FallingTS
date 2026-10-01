/**
 * FallingTS 跑完自动卸载模型 (2026-10)。
 *
 * 需求: 每次工作流跑完且队列为空时, 自动卸载全部已加载模型, 释放显存。
 *
 * 为什么不用内置的 POST /free: /free 只是**置旗**(unload_models), 旗标在 prompt 主循环里
 * **下一次 prompt 执行完之后**才被消费 ⇒ 单次"跑完"永远不会生效。后端自建路由直调
 * 内置按钮最终调用的核心函数(unload_all_models + gc + empty_cache), 见 auto-unload/nodes.py。
 *
 * 挂点: 前端总线 `execution_success` 事件(每个 prompt 成功完成后触发, 含继续/截帧的 partial 提交)
 * → POST /fallingts_auto_unload/unload。后端是"卸不卸"的唯一裁决者:
 *   - 队列非空(多任务连跑) → skipped, 只有最后一个真正卸载;
 *   - 队列为空 → 卸载并返回释放的显存, 弹 info toast(life 3000)。
 * 只监听 success: 失败时保留模型, 下次重试不必重新加载。
 *
 * ⚠️ 后端路由不存在(404/405)不算失败: 前端 js 经 /extensions 从磁盘即时加载, 后端路由却要
 *    重启才注册 ⇒ 页面一刷新就会出现"新前端 + 旧后端"的混搭。此时**只提示一次并放行**。
 *
 * 设置项: 系统设置「常规 › 其它」里的「跑完自动卸载模型」(boolean, 默认开, 排在「开始前命令」下面)。
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const SETTING_ID = "FallingTS.AutoUnload.Enabled";
const ENDPOINT = "/fallingts_auto_unload/unload";

let routeMissingNotified = false;
let busy = false;

/**
 * 读取开关; 设置服务不可用时按"开"处理(功能保持可用, 用户可在设置里关掉)。
 * @returns {boolean}
 */
function isEnabled() {
  try {
    const v = app.ui?.settings?.getSettingValue(SETTING_ID);
    return v === undefined || v === null ? true : !!v;
  } catch {
    return true;
  }
}

function toast(severity, summary, detail) {
  try {
    app.extensionManager?.toast?.add({ severity, summary, detail, life: 3000 });
  } catch (e) {
    console.warn("[FallingTS.AutoUnload] toast failed:", e);
  }
}

async function runAutoUnload() {
  if (busy) return;
  busy = true;
  try {
    const resp = await fetch(ENDPOINT, { method: "POST" });
    if (resp.status === 404 || resp.status === 405) {
      if (!routeMissingNotified) {
        routeMissingNotified = true;
        console.warn(
          `[FallingTS.AutoUnload] 后端路由 ${ENDPOINT} 不存在(404/405): 多半是 ComfyUI 还没重启。`
        );
        toast("warn", "自动卸载模型未生效", "请重启 ComfyUI 启用「跑完自动卸载模型」");
      }
      return;
    }
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      console.warn("[FallingTS.AutoUnload] 后端返回错误:", data);
      return;
    }
    if (data.skipped) return; // 多任务连跑, 不是最后一个, 不提示
    toast(
      "info",
      "自动卸载模型完成",
      `释放 ${data.freed_mb} MB 显存(当前空闲 ${data.free_mb} MB, ${data.ms} ms)`
    );
  } catch (e) {
    console.warn("[FallingTS.AutoUnload] 请求失败:", e);
  } finally {
    busy = false;
  }
}

app.registerExtension({
  name: "FallingTS.AutoUnload",
  async setup() {
    // 1. 设置项: 内置 boolean 类型, 自带开关 + 问号 tooltip + 持久化, 无需自绘 HTML。
    try {
      app.ui?.settings?.addSetting({
        id: SETTING_ID,
        name: "跑完自动卸载模型",
        type: "boolean",
        defaultValue: true,
        category: ["跑完自动卸载模型"],
        sortOrder: 5,
        tooltip:
          "每次工作流跑完且队列为空时, 自动卸载全部已加载模型(等效内置「卸载模型」按钮)释放显存; " +
          "多任务连跑时只有最后一个卸载。只在工作流成功时触发, 失败保留模型便于重试。",
      });
    } catch { /* 设置面板不可用时功能静默降级(默认开) */ }

    // 2. 完成事件: 每个 prompt 成功完成后触发一次(含 partial 提交); 失败/中断不触发。
    api.addEventListener("execution_success", () => {
      if (isEnabled()) runAutoUnload();
    });
  },
});
