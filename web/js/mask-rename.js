/**
 * FallingTS.MaskRename 前端扩展: 仅对 PreviewImageSave 节点生效。
 * 从该节点打开遮罩编辑器保存后:
 * - 后端把 4 个 clipspace-{ts} 文件保存到 input/clipspace/(= output/clipspace, 同一物理目录),
 *   保留原名 —— 内置编辑器 type=input 仍能找到, 重新打开可完整恢复 -mask/-paint 层继续编辑;
 * - 后端复制 clipspace-painted-masked-{ts}.png -> output/{base}.png(按 ID 命名成品, 同名覆盖);
 * - 前端把节点引用更新到 clipspace 子目录(edit_ref), 让重新打开遮罩编辑器能加载。
 *
 * base 名 = 预览节点 execute 时缓存的 filename_prefix(连到 MD 表格 ID 时即行 ID)。
 * 其它官方节点打开遮罩编辑器保存时【不】触发。
 *
 * 原理(全部走抛出接口, 不改打包前端):
 * - 检测: 遮罩编辑器保存时会执行 `node.images = [clipspace引用]`。在 PreviewImageSave
 *   的 onNodeCreated 里给 node.images 装 setter, 赋值时若文件名以 clipspace-painted-masked-
 *   开头且为近期保存即触发整理;
 * - 整理: POST /fallingts_mask/rename, 后端完成保存到 clipspace 子目录 + 复制成品。
 */

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "PreviewImageSave";
const PREFIX = "clipspace-painted-masked-";
// 只在遮罩「刚保存」时整理(ts 在 5 分钟内); 加载旧工作流带的历史 clipspace 引用不动作,
// 避免误动很久以前生成的遮罩文件
const FRESH_WINDOW_MS = 5 * 60 * 1000;
// 兜底轮询间隔(images 属性不可重定义等罕见情况)
const POLL_MS = 2000;

/**
 * 判断文件名是否为「近期生成的遮罩引用」(clipspace-painted-masked-{ts}.png 且 ts 在窗口内)。
 *
 * @param {string} filename 文件名
 * @returns {boolean} 是否近期遮罩引用
 */
function isFreshClipspace(filename) {
  const m = /^clipspace-painted-masked-(\d+)\.png$/.exec(filename || "");
  if (!m) return false;
  const ts = parseInt(m[1], 10);
  return Number.isFinite(ts) && Date.now() - ts < FRESH_WINDOW_MS;
}

/**
 * 触发整理(带防重入标记)。
 *
 * @param {LGraphNode} node 节点
 * @param {object|null} ref node.images[0]
 * @returns {void}
 */
function triggerRename(node, ref) {
  if (isFreshClipspace(ref?.filename) && !node.__fallingtsRenaming) {
    node.__fallingtsRenaming = true;
    renameMask(node, ref.filename).finally(() => {
      node.__fallingtsRenaming = false;
    });
  }
}

/**
 * 调用后端完成遮罩文件整理(保存到 clipspace + 复制成品), 并更新节点引用到 clipspace。
 *
 * @param {LGraphNode} node 预览保存节点
 * @param {string} imageRef 当前引用的 clipspace 文件名
 * @returns {Promise<void>} 整理流程
 */
async function renameMask(node, imageRef) {
  let resp;
  try {
    resp = await fetch("/fallingts_mask/rename", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: String(node.id), image_ref: imageRef }),
    });
  } catch (err) {
    console.warn("[FallingTS] 遮罩整理请求失败:", err);
    return;
  }
  const data = await resp.json().catch(() => null);
  if (!resp.ok || !data?.ok) {
    console.warn("[FallingTS] 遮罩整理失败:", data?.error ?? resp.status);
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

  app.extensionManager?.toast?.add?.({
    severity: "success",
    summary: data.out_ref?.filename
      ? `已整理: 编辑文件→clipspace, 成品→${data.out_ref.filename}`
      : "遮罩文件已整理",
  });
}

app.registerExtension({
  name: "FallingTS.MaskRename",

  /**
   * 节点定义注册前钩子: **只处理 PreviewImageSave**, 给 node.images 装 setter 检测遮罩编辑器保存。
   * 其它官方节点不安装钩子, 保存遮罩时【不】触发整理。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

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
