/**
 * FallingTS.MaskRename 前端扩展: 对 PreviewImageSave 与 FallingTSLoadImage 两个节点生效。
 * 从该节点打开遮罩编辑器保存后:
 * - 后端把 4 个 clipspace-{ts} 文件保存到 input/clipspace/(= output/clipspace, 同一物理目录),
 *   保留原名 —— 内置编辑器 type=input 仍能找到, 重新打开可完整恢复 -mask/-paint 层继续编辑;
 * - 后端复制 clipspace-painted-masked-{ts}.png -> output/{base}.png(按 ID 命名成品, 同名覆盖);
 * - 前端把节点引用更新到 clipspace 子目录(edit_ref), 让重新打开遮罩编辑器能加载。
 *
 * 成品名:
 * - FallingTSLoadImage 节点: 用它的「名称」输入框 → 0010_灰度遮罩/0000N_名称.png
 *   (N = 目录里已有 5 位编号的最大值 + 1, 由后端算, 每次保存新增一个编号);
 * - PreviewImageSave 节点: 预览节点 execute 时缓存的 filename_prefix(连到 MD 表格 ID 时即行 ID)。
 * 其它官方节点打开遮罩编辑器保存时【不】触发。
 *
 * 原理(全部走抛出接口, 不改打包前端):
 * - 检测: 遮罩编辑器保存时会执行 `node.images = [clipspace引用]`。在 PreviewImageSave
 *   的 onNodeCreated 里给 node.images 装 setter, 赋值时若文件名以 clipspace-painted-masked-
 *   开头且为近期保存即触发整理;
 * - 整理: POST /fallingts_mask/rename, 后端完成保存到 clipspace 子目录 + 复制成品。
 */

import { app } from "../../../scripts/app.js";

// 挂勾子的节点: 预览保存 + 自带「名称」输入框的加载图像节点
const NODE_CLASSES = ["PreviewImageSave", "FallingTSLoadImage"];
const PREFIX = "clipspace-painted-masked-";
// 只在遮罩「刚保存」时整理(ts 在 5 分钟内); 加载旧工作流带的历史 clipspace 引用不动作,
// 避免误动很久以前生成的遮罩文件
const FRESH_WINDOW_MS = 5 * 60 * 1000;
// 兜底轮询间隔(images 属性不可重定义等罕见情况)
const POLL_MS = 2000;
// 整理请求超时: 超时即中止, 让在途标志走 finally 释放 —— 挂死的 fetch 会把标志卡住,
// 之后每次保存都被静默跳过(2026-10-02 那次「保存零产物」即此因)
const RENAME_TIMEOUT_MS = 10000;
// 在途标志滞留阈值: 持有超过此时长视为卡死(无超时的挂死请求), 清掉重试
const STALE_FLAG_MS = 15000;

/**
 * 提取 clipspace-painted-masked-{ts}.png 文件名里的 ts(毫秒时间戳串)。
 *
 * @param {string} filename 文件名
 * @returns {string|null} ts 串; 非遮罩引用格式返回 null
 */
function clipspaceTs(filename) {
  const m = /^clipspace-painted-masked-(\d+)\.png$/.exec(filename || "");
  return m ? m[1] : null;
}

/**
 * 判断文件名是否为「近期生成的遮罩引用」(clipspace-painted-masked-{ts}.png 且 ts 在窗口内)。
 *
 * @param {string} filename 文件名
 * @returns {boolean} 是否近期遮罩引用
 */
function isFreshClipspace(filename) {
  const ts = clipspaceTs(filename);
  if (ts === null) return false;
  return Date.now() - Number(ts) < FRESH_WINDOW_MS;
}

/**
 * 弹提示(toast 服务不可用时忽略, 只留控制台 —— 绝不能因为提示失败把整理流程打断)。
 *
 * @param {string} severity "success" | "error" | "warn"
 * @param {string} summary 标题
 * @param {string} [details] 细节(失败原因等)
 * @returns {void}
 */
function notify(severity, summary, details) {
  try {
    app.extensionManager?.toast?.add?.({
      severity,
      summary,
      details,
      life: 3000,
    });
  } catch {
    /* toast 不可用: 控制台已有记录 */
  }
}

/**
 * 触发整理(防重入 + ts 级去重)。
 *
 * ts 级去重: 同一个 ts 最多发起一次整理。保存返回后前端 store 重绘会把同一引用
 * 再赋回 node.images(数组身份不同 → setter 再次触发), 不去重则后端编号进位,
 * 多出 00001/00002 两个相同成品(2026-10-02 「保存两次」即此因); 新保存必然带
 * 新 ts(Date.now()), 不受影响。
 *
 * @param {LGraphNode} node 节点
 * @param {object|null} ref node.images[0]
 * @returns {void}
 */
function triggerRename(node, ref) {
  if (!isFreshClipspace(ref?.filename)) return;
  if (node.__fallingtsRenaming) {
    if (Date.now() - (node.__fallingtsRenamingAt || 0) < STALE_FLAG_MS) return;
    // 上一次请求挂死未释放标志: 清掉重试
    console.warn("[FallingTS] 遮罩整理标志滞留超 15s(疑似挂死), 清除后重试");
    node.__fallingtsRenaming = false;
  }
  const ts = clipspaceTs(ref.filename);
  if (ts === null || node.__fallingtsLastTs === ts) return;
  node.__fallingtsLastTs = ts;
  node.__fallingtsRenaming = true;
  node.__fallingtsRenamingAt = Date.now();
  renameMask(node, ref.filename).finally(() => {
    node.__fallingtsRenaming = false;
  });
}

/**
 * 调用后端完成遮罩文件整理(保存到 clipspace + 复制成品), 并更新节点引用到 clipspace。
 *
 * @param {LGraphNode} node 预览保存 / 加载图像节点
 * @param {string} imageRef 当前引用的 clipspace 文件名
 * @returns {Promise<void>} 整理流程
 */
async function renameMask(node, imageRef) {
  // 「加载图像」节点的名称输入框(没有该 widget 的节点传空串 → 后端走旧口径命名)
  const nameWidget = node.widgets?.find((w) => w.name === "name");
  const maskName =
    typeof nameWidget?.value === "string" ? nameWidget.value.trim() : "";

  // 超时中止: 挂死的请求不再把在途标志卡死(标志卡死 ⇒ 之后每次保存被静默跳过)
  const controller = new AbortController();
  const timeoutTimer = setTimeout(() => controller.abort(), RENAME_TIMEOUT_MS);
  let resp;
  try {
    // workflow_id 取根图 id: 后端 _last_output 的键是 "<工作流根 id>::<节点 id>",
    // 不带就拿不到该节点缓存的 filename_prefix(= 行 ID), 成品会退化成 mask-{ts}。
    // 必须取 app.rootGraph —— 取 node.graph 在子图里会拿到别的 id。
    const workflowId = app.rootGraph?.id ?? null;
    resp = await fetch("/fallingts_mask/rename", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        node_id: String(node.id),
        image_ref: imageRef,
        workflow_id: workflowId,
        name: maskName,
      }),
      signal: controller.signal,
    });
  } catch (err) {
    console.warn("[FallingTS] 遮罩整理请求失败:", err);
    notify(
      "error",
      err?.name === "AbortError"
        ? "遮罩整理失败: 请求超时"
        : "遮罩整理失败: 请求发不出去",
      String(err?.message ?? err),
    );
    return;
  } finally {
    clearTimeout(timeoutTimer);
  }
  const data = await resp.json().catch(() => null);
  if (!resp.ok || !data?.ok) {
    // 失败必须弹出来: 曾经这里只 console.warn, 后端 500 时用户看不到任何提示
    // (2026-10-01 后端 NameError 就是这么静默的)。
    const reason = data?.error ?? `HTTP ${resp.status}`;
    console.warn("[FallingTS] 遮罩整理失败:", reason);
    notify("error", "遮罩整理失败: 成品未写入 0010_灰度遮罩", reason);
    return;
  }

  // 更新节点引用到 clipspace 子目录 —— 内置编辑器靠它重新打开时完整恢复 -mask/-paint 层继续编辑
  // (input=output=media, 所以 input/clipspace 就是 output/clipspace)
  const editRef = data.edit_ref;
  if (editRef) {
    if (Array.isArray(node.images) && node.images.length) {
      node.images[0] = editRef;
    } else {
      node.images = [editRef];
    }
    // image 控件值: "clipspace/文件名 [input]" —— 内置 parseImageWidgetValue 能解析出 subfolder
    const imgWidget = node.widgets?.find((w) => w.name === "image");
    if (imgWidget) {
      imgWidget.value = `${editRef.subfolder}/${editRef.filename} [${editRef.type}]`;
    }
  }

  node.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);

  notify(
    "success",
    data.out_ref?.filename
      ? `已整理: 编辑文件→clipspace, 成品→${
          data.out_ref.subfolder ? `${data.out_ref.subfolder}/` : ""
        }${data.out_ref.filename}`
      : "遮罩文件已整理"
  );
}

app.registerExtension({
  name: "FallingTS.MaskRename",

  /**
   * 节点定义注册前钩子: 只处理 PreviewImageSave / FallingTSLoadImage, 给 node.images 装 setter
   * 检测遮罩编辑器保存。其它官方节点不安装钩子, 保存遮罩时【不】触发整理。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_CLASSES.includes(nodeData?.name)) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      // 遮罩编辑器保存时执行 node.images = [clipspace引用] —— 用 setter 拦截精确触发整理
      let _images = node.images;
      try {
        Object.defineProperty(node, "images", {
          configurable: true,
          enumerable: true,
          get() {
            return _images;
          },
          set(val) {
            _images = val;
            triggerRename(node, Array.isArray(val) ? val[0] : null);
          },
        });
      } catch (err) {
        // defineProperty 失败(如属性不可配置): 降级为定时轮询 node.images 检测(仅本节点)
        console.warn("[FallingTS] 遮罩整理 images 钩子安装失败, 降级轮询:", err);
        const timer = setInterval(() => {
          if (node?.removed) {
            clearInterval(timer);
            return;
          }
          triggerRename(node, node.images?.[0]);
        }, POLL_MS);
      }
    };
  },
});
