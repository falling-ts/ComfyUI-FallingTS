// comfy-desktop-plugins 前端扩展:
// 把左侧"媒体资产"面板的「已导入」标签改为「已保存」。
// 两种手段双保险:
//   1. 合并 i18n 文案 sideToolbar.labels.imported → "已保存"(响应式, 重渲染也不变)
//   2. DOM 兜底: 找到 id=tab-input 且文本为「已导入」的标签直接改名
// MutationObserver 监听重渲染, 保证切换视图/重载后仍保持「已保存」。

const { app } = window.comfyAPI.app;

function mergeI18nLabel() {
  try {
    const el = document.getElementById('vue-app');
    const i18n = el?.__vue_app__?.config?.globalProperties?.$i18n;
    const global = i18n?.global;
    if (!global || typeof global.mergeLocaleMessage !== 'function') return;
    const locale = global.locale?.value ?? 'zh';
    global.mergeLocaleMessage(locale, {
      sideToolbar: { labels: { imported: '已保存' } }
    });
  } catch {
    /* i18n 不可用时交给 DOM 兜底 */
  }
}

function patchTabDom() {
  for (const btn of document.querySelectorAll('button[role="tab"]')) {
    if (btn.id !== 'tab-input') continue;
    if ((btn.textContent || '').trim() === '已导入') {
      btn.textContent = '已保存';
    }
  }
}

app.registerExtension({
  name: 'ComfyDesktop.AssetsTabRename',
  setup() {
    mergeI18nLabel();
    patchTabDom();
    const observer = new MutationObserver(() => {
      mergeI18nLabel();
      patchTabDom();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  },
});
