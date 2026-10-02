// comfy-desktop-plugins 前端扩展:
// 把「已导入」统一显示成「已保存」, 共两处:
//   1. 左侧「媒体资产」面板的标签(原 i18n key: sideToolbar.labels.imported);
//   2. 节点上「加载图像」下拉**展开的弹窗**里的分类按钮 —— 它由
//      useWidgetSelectItems 的 filterOptions 用**同一个 key** 渲染
//      (t('sideToolbar.labels.imported')), 所以 i18n 合并一旦生效, 两处一起变。
// 两种手段双保险:
//   1. 合并 i18n 文案 sideToolbar.labels.imported →「已保存」(响应式, 重渲染也不变);
//   2. DOM 兜底: 把任何文本恰为「已导入」的元素直接改名 —— 覆盖"i18n 合并失败"或
//      "文案来自别的 key/硬编码"的情况。MutationObserver 监听重渲染, 保证切换视图/重载后仍保持。

const { app } = window.comfyAPI.app;

const OLD_TEXT = '已导入';
const NEW_TEXT = '已保存';

/**
 * 取 i18n 组合器(Vue i18n 的 composer)。
 *
 * ⚠️ 必须兼容两种形态: createI18n() 返回的实例(i18n.global)与**已被注入成 composer
 * 的实例**($i18n 本身就是 composer)。原实现写死 \`i18n.global\`, 没有 global 时直接
 * return —— 于是 i18n 合并**从未生效**, 只剩 DOM 兜底(只认 id=tab-input), 左侧栏改名了
 * 而节点下拉弹窗里仍是「已导入」(前端包 1.52.7 实测)。
 *
 * @returns {object|null} 可用的 i18n composer, 取不到时 null(交给 DOM 兜底)
 */
function getI18nComposer() {
  try {
    const el = document.getElementById('vue-app');
    const i18n = el?.__vue_app__?.config?.globalProperties?.$i18n;
    const composer = i18n?.global ?? i18n;
    if (!composer || typeof composer.mergeLocaleMessage !== 'function') return null;
    return composer;
  } catch {
    return null;
  }
}

/**
 * 合并 i18n 文案: 「已导入」→「已保存」(响应式, 重渲染也不用再改 DOM)。
 *
 * @returns {void}
 */
function mergeI18nLabel() {
  const composer = getI18nComposer();
  if (!composer) return;
  const locale = composer.locale?.value ?? composer.locale ?? 'zh';
  if (typeof locale !== 'string') return;
  try {
    composer.mergeLocaleMessage(locale, {
      sideToolbar: { labels: { imported: NEW_TEXT } },
    });
  } catch {
    /* i18n 不可写时交给 DOM 兜底 */
  }
}

/**
 * 把子树里所有文本恰为「已导入」的文本节点改成「已保存」。
 *
 * @param {Node|null} root 起始节点
 * @returns {void}
 */
function patchText(root) {
  if (!root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (node.nodeValue && node.nodeValue.trim() === OLD_TEXT) {
      // 保留原有前后空白, 只换词
      node.nodeValue = node.nodeValue.replace(OLD_TEXT, NEW_TEXT);
    }
    node = walker.nextNode();
  }
}

/**
 * DOM 兜底改名: 首次全量扫一遍; 后续只扫变更涉及的子树(页面大时全量太贵)。
 *
 * @param {MutationRecord[]} [records] MutationObserver 记录; 缺省 = 全量
 * @returns {void}
 */
function patchDom(records) {
  if (!records) {
    patchText(document.body);
    return;
  }
  for (const record of records) {
    if (record.target) patchText(record.target);
    for (const added of record.addedNodes) patchText(added);
  }
  // 左侧栏标签(旧兜底路径)保持不变, 名字一样在 patchText 里覆盖
  for (const btn of document.querySelectorAll('button[role="tab"], [role="tab"]')) {
    if ((btn.textContent || '').trim() === OLD_TEXT) btn.textContent = NEW_TEXT;
  }
}

app.registerExtension({
  name: 'ComfyDesktop.AssetsTabRename',

  /**
   * 扩展初始化钩子: 执行一次改名并挂 MutationObserver, 保证重渲染后仍保持「已保存」。
   *
   * @returns {void}
   */
  setup() {
    mergeI18nLabel();
    patchDom();
    const observer = new MutationObserver((records) => {
      mergeI18nLabel();
      patchDom(records);
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  },
});
