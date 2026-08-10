/**
 * PreviewAudioSave 前端: 底部追加「保存」按钮。
 *
 * 行为:
 * - 预览部分由节点原生 UI.PreviewAudio 负责(播放 temp 目录 flac);
 * - 点「保存」: 把 文件名/格式/质量 POST 到 /preview-audio/save/{id},
 *   后端用 execute 时缓存的音频数据直接写 output({filename_prefix}.{format}, 同名覆盖、无序号) ——
 *   【不触发任何工作流重跑】, 保存的是当前画面上播放的这段音频。
 */

import { app } from "../../../scripts/app.js";

const NODE_CLASS = "PreviewAudioSave";

app.registerExtension({
  name: "FallingTS.PreviewAudioSave",

  /**
   * 节点定义注册前钩子: 给 PreviewAudioSave 追加「保存」按钮。
   *
   * @param {Function} nodeType 节点类型构造函数(原型上挂方法)
   * @param {object} nodeData 节点定义数据(来自 /object_info)
   * @returns {void}
   */
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    /**
     * 节点创建钩子: 追加「保存」按钮。
     *
     * @returns {*} 原 onNodeCreated 的返回值
     */
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      /**
       * 「保存」按钮点击处理: 把文件名/格式/质量 POST 到后端, 后端用缓存的音频直接写 output
       * ({filename_prefix}.{format}, 同名覆盖, 无序号), 【不重跑工作流】。
       * 回调参数: 无(addWidget 内部触发)。
       * @returns {Promise<void>} 保存请求异步流程
       */
      node.addWidget("button", "保存", null, async () => {
        const getWidget = (name) => node.widgets?.find((w) => w.name === name)?.value;
        // filename_prefix 是否被上游连线(如 MDTable 的 ID 列): 连线时 widget 只是占位符,
        // 需后端用 execute 时实际接收到的值, 否则保存会落到占位符 "audio"
        const prefixLinked =
          node.inputs?.find((i) => i.name === "filename_prefix")?.link != null;
        const fmtVal = getWidget("format");
        try {
          const resp = await fetch(`/preview-audio/save/${node.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename_prefix: getWidget("filename_prefix") ?? "audio",
              filename_prefix_linked: prefixLinked,
              format: fmtVal?.format ?? "flac",
              quality: fmtVal?.quality ?? "128k",
            }),
          });
          const data = await resp.json().catch(() => null);
          if (!resp.ok) {
            alert(data?.message ?? "保存失败");
            return;
          }
          alert(data?.message ?? "已保存");
        } catch (err) {
          console.error("[FallingTS] 保存失败:", err);
          alert("保存失败: 无法连接后端");
        }
      });
    };
  },
});
