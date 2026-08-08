// comfy-desktop-plugins 前端扩展:
// 为"媒体资产 / 队列"全屏预览(MediaLightbox)补上图片缩放能力:
//   滚轮 = 以鼠标位置为中心缩放; 拖拽 = 平移; 双击 = 1x <-> 2.2x; +/-/0 键盘快捷;
//   底部工具条: ＋ / － / 重置 / 百分比指示。
// 实现方式: DOM 层注入, 不修改官方前端文件; 前端升级后若弹层类名变化, 只需调整选择器。

const { app } = window.comfyAPI.app;

const ZOOM_MIN = 0.1;
const ZOOM_MAX = 8;

const state = {
  dialog: null, // 当前 Lightbox 弹层元素
  img: null, // 当前预览图片
  zoom: 1,
  pan: { x: 0, y: 0 },
  dragging: false,
  dragLast: null,
  dragStartPan: { x: 0, y: 0 },
  toolbar: null,
  label: null,
};

// 定位 MediaLightbox 弹层: fixed 黑色遮罩 + 内含受限尺寸预览图
/**
 * 判断元素是否为内置 MediaLightbox 弹层(fixed 黑色遮罩 + 相关 class)。
 *
 * @param {Element|null} el DOM 元素
 * @returns {boolean} 是弹层返回 true
 */
function isLightbox(el) {
  return (
    el &&
    el.matches?.('div[role="dialog"][data-mask]') &&
    el.classList.contains('bg-black/90') &&
    el.classList.contains('z-9999')
  );
}

/**
 * 在当前 DOM 中查找处于打开状态的 MediaLightbox 弹层。
 *
 * @returns {Element|null} 弹层元素; 未找到返回 null
 */
function findLightbox() {
  const dialogs = document.querySelectorAll('div[role="dialog"][data-mask]');
  for (const d of dialogs) {
    if (!isLightbox(d)) continue;
    const img = d.querySelector('img');
    if (
      img &&
      (img.classList.contains('max-h-[90vh]') ||
        img.classList.contains('mlz-img'))
    ) {
      return d;
    }
  }
  return null;
}

// 取图片"未变形"时的视口矩形(临时清掉 transform 同步读取, 保证布局中心准确)
/**
 * 取图片"未变形"时的视口矩形(临时清掉 transform 同步读取, 保证缩放锚点中心准确)。
 *
 * @returns {DOMRect|null} 布局矩形; 无图片返回 null
 */
function layoutRect() {
  const img = state.img;
  if (!img) return null;
  const prevTransform = img.style.transform;
  const prevOrigin = img.style.transformOrigin;
  img.style.transform = '';
  img.style.transformOrigin = 'center';
  const rect = img.getBoundingClientRect();
  img.style.transform = prevTransform;
  img.style.transformOrigin = prevOrigin;
  return rect;
}

// 宽松限制平移范围: 允许大幅拖动, 但图片不会完全飞出可视区
/**
 * 宽松限制平移范围: 允许大幅拖动, 但图片不会完全飞出可视区。
 *
 * @returns {void}
 */
function clampPan() {
  const img = state.img;
  if (!img) return;
  const w = img.offsetWidth || 1;
  const h = img.offsetHeight || 1;
  const z = state.zoom;
  const maxX = (w * z) / 2 + w / 2;
  const maxY = (h * z) / 2 + h / 2;
  state.pan.x = Math.max(-maxX, Math.min(maxX, state.pan.x));
  state.pan.y = Math.max(-maxY, Math.min(maxY, state.pan.y));
}

/**
 * 更新底部工具条的缩放百分比与显示状态。
 *
 * @returns {void}
 */
function updateToolbar() {
  if (state.label) {
    state.label.textContent = Math.round(state.zoom * 100) + '%';
  }
  if (state.toolbar) {
    state.toolbar.style.display = state.img ? 'flex' : 'none';
  }
}

/**
 * 应用缩放/平移 transform 到图片: 滚轮/拖拽即时生效, 双击/重置用短暂过渡动画。
 *
 * @param {boolean} [smooth] 是否启用过渡动画
 * @returns {void}
 */
function applyTransform(smooth) {
  const img = state.img;
  if (!img) return;
  img.style.transformOrigin = 'center';
  // 滚轮/拖拽必须即时生效(否则视觉滞后导致图片偏离鼠标锚点"乱跑"),
  // 只有双击/重置这类"跳变"才允许短暂过渡动画
  img.style.transition = smooth ? 'transform 150ms ease-out' : 'none';
  img.style.userSelect = state.zoom > 1 ? 'none' : '';
  img.style.webkitUserSelect = state.zoom > 1 ? 'none' : '';
  if (state.zoom < 1) {
    // 缩小到 100% 以下时保持居中
    state.pan = { x: 0, y: 0 };
    img.style.transform = 'scale(' + state.zoom + ')';
    img.style.cursor = 'default';
  } else if (state.zoom <= 1.0001) {
    state.zoom = 1;
    state.pan = { x: 0, y: 0 };
    img.style.transform = '';
    img.style.cursor = 'default';
  } else {
    img.style.transform =
      'translate(' + state.pan.x + 'px, ' + state.pan.y + 'px) scale(' + state.zoom + ')';
    img.style.cursor = state.dragging ? 'grabbing' : 'grab';
  }
  updateToolbar();
}

/**
 * 重置缩放为 1x 并居中。
 *
 * @returns {void}
 */
function resetZoom() {
  state.zoom = 1;
  state.pan = { x: 0, y: 0 };
  applyTransform(true);
}

// 以鼠标位置为锚点缩放
/**
 * 以鼠标位置为锚点缩放: 锚点处内容在缩放前后保持不动。
 *
 * @param {number} clientX 鼠标 X
 * @param {number} clientY 鼠标 Y
 * @param {number} factor 缩放倍率(>1 放大, <1 缩小)
 * @returns {void}
 */
function zoomAt(clientX, clientY, factor) {
  const img = state.img;
  if (!img) return;
  const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, state.zoom * factor));
  if (Math.abs(next - state.zoom) < 1e-4) return;
  const rect = layoutRect();
  if (!rect) return;
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const dx = clientX - cx;
  const dy = clientY - cy;
  const ratio = next / state.zoom;
  state.pan.x = state.pan.x * ratio + dx * (1 - ratio);
  state.pan.y = state.pan.y * ratio + dy * (1 - ratio);
  state.zoom = next;
  applyTransform();
}

/**
 * 以图片中心为锚点缩放(供 +/-/0 快捷键与工具条用)。
 *
 * @param {number} factor 缩放倍率
 * @returns {void}
 */
function zoomAtCenter(factor) {
  const img = state.img;
  if (!img) return;
  const rect = img.getBoundingClientRect();
  zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor);
}

/**
 * 滚轮/触控板缩放处理: deltaY 归一化后用指数映射, 以鼠标位置为锚点。
 *
 * @param {WheelEvent} e 滚轮事件
 * @returns {void}
 */
function onWheel(e) {
  if (!state.img) return;
  e.preventDefault();
  // 兼容滚轮 / 触控板 / 捏合: deltaY 归一化后用指数映射
  const delta = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY;
  const factor = Math.exp(-delta * 0.002);
  zoomAt(e.clientX, e.clientY, Math.min(2, Math.max(0.5, factor)));
}

/**
 * 鼠标按下开始拖拽平移(仅放大状态, 左键)。
 *
 * @param {MouseEvent} e 鼠标事件
 * @returns {void}
 */
function onMouseDown(e) {
  if (e.button !== 0 || !state.img || state.zoom <= 1.0001) return;
  state.dragging = true;
  state.dragLast = { x: e.clientX, y: e.clientY };
  state.dragStartPan = { x: state.pan.x, y: state.pan.y };
  e.preventDefault();
  applyTransform();
}

/**
 * 鼠标移动: 更新平移偏移并应用(带范围限制)。
 *
 * @param {MouseEvent} e 鼠标事件
 * @returns {void}
 */
function onMouseMove(e) {
  if (!state.dragging || !state.img) return;
  const dx = e.clientX - state.dragLast.x;
  const dy = e.clientY - state.dragLast.y;
  state.pan = {
    x: state.dragStartPan.x + dx,
    y: state.dragStartPan.y + dy,
  };
  clampPan();
  applyTransform();
}

/**
 * 鼠标松开结束拖拽。
 *
 * @returns {void}
 */
function onMouseUp() {
  if (!state.dragging) return;
  state.dragging = false;
  applyTransform();
}

/**
 * 双击: 放大状态 → 重置 1x; 未放大 → 以点击处为锚点放大 2.2x。
 *
 * @param {MouseEvent} e 鼠标事件
 * @returns {void}
 */
function onDblClick(e) {
  if (!state.img) return;
  e.preventDefault();
  if (state.zoom > 1.0001) {
    resetZoom();
  } else {
    zoomAt(e.clientX, e.clientY, 2.2);
  }
}

/**
 * 键盘快捷键: +/= 放大, -/_ 缩小, 0 重置。
 *
 * @param {KeyboardEvent} e 键盘事件
 * @returns {void}
 */
function onKeyDown(e) {
  if (!state.img) return;
  if (e.key === '+' || e.key === '=') {
    e.preventDefault();
    zoomAtCenter(1.25);
  } else if (e.key === '-' || e.key === '_') {
    e.preventDefault();
    zoomAtCenter(0.8);
  } else if (e.key === '0') {
    e.preventDefault();
    resetZoom();
  }
}

/**
 * 创建底部工具条按钮(圆形, 悬浮高亮)。
 *
 * @param {string} text 按钮文字(如 ＋/−/↺)
 * @param {string} title 悬浮提示
 * @param {Function} onClick 点击回调
 * @returns {HTMLButtonElement} 按钮元素
 */
function makeToolbarBtn(text, title, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = text;
  b.title = title;
  b.setAttribute('aria-label', title);
  b.style.cssText =
    'width:26px;height:26px;border-radius:9999px;border:1px solid rgba(255,255,255,.25);' +
    'background:rgba(255,255,255,.12);color:#fff;font-size:14px;line-height:1;cursor:pointer;' +
    'display:flex;align-items:center;justify-content:center;';
  b.addEventListener('mouseenter', () => {
    b.style.background = 'rgba(255,255,255,.28)';
  });
  b.addEventListener('mouseleave', () => {
    b.style.background = 'rgba(255,255,255,.12)';
  });
  b.addEventListener('click', (e) => {
    e.stopPropagation();
    onClick();
  });
  return b;
}

/**
 * 在弹层底部创建/复用缩放工具条(＋/−/百分比/↺)。
 *
 * @param {Element} dialog 弹层元素
 * @returns {void}
 */
function ensureToolbar(dialog) {
  if (dialog.querySelector('.mlz-toolbar')) return;
  const tb = document.createElement('div');
  tb.className = 'mlz-toolbar';
  tb.style.cssText =
    'position:fixed;bottom:18px;left:50%;transform:translateX(-50%);z-index:10000;' +
    'display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:9999px;' +
    'background:rgba(15,17,26,.82);border:1px solid rgba(255,255,255,.15);' +
    'backdrop-filter:blur(6px);box-shadow:0 4px 16px rgba(0,0,0,.35);';
  const minus = makeToolbarBtn('−', '缩小 (滚轮向下 / -)', () => zoomAtCenter(0.8));
  const label = document.createElement('span');
  label.className = 'mlz-label';
  label.style.cssText =
    'color:#e5e7eb;font-size:12px;min-width:46px;text-align:center;' +
    'font-variant-numeric:tabular-nums;user-select:none;';
  label.textContent = '100%';
  const plus = makeToolbarBtn('＋', '放大 (滚轮向上 / +)', () => zoomAtCenter(1.25));
  const reset = makeToolbarBtn('↺', '重置 (双击 / 0)', resetZoom);
  tb.append(minus, label, plus, reset);
  dialog.appendChild(tb);
  state.toolbar = tb;
  state.label = label;
}

/**
 * 初始化一个弹层的缩放控制: 定位图片、重置缩放、建工具条、绑定滚轮/拖拽/双击/键盘事件。
 *
 * @param {Element} dialog 弹层元素
 * @returns {void}
 */
function initDialog(dialog) {
  state.dialog = dialog;
  const imgs = [...dialog.querySelectorAll('.mlz-img')];
  state.imgs = imgs.length ? imgs : null;
  state.img = imgs.length ? imgs[0] : dialog.querySelector('img');
  resetZoom();

  // 禁用原生图片拖拽, 交给自定义平移
  if (state.img) state.img.draggable = false;

  ensureToolbar(dialog);

  dialog.addEventListener('wheel', onWheel, { passive: false });
  dialog.addEventListener('mousedown', onMouseDown);
  dialog.addEventListener('dblclick', onDblClick);
  dialog.addEventListener('keydown', onKeyDown);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
}

/**
 * 清理弹层的缩放状态并解绑所有事件监听。
 *
 * @param {Element} dialog 弹层元素
 * @returns {void}
 */
function cleanupDialog(dialog) {
  if (dialog) {
    dialog.removeEventListener('wheel', onWheel);
    dialog.removeEventListener('mousedown', onMouseDown);
    dialog.removeEventListener('dblclick', onDblClick);
    dialog.removeEventListener('keydown', onKeyDown);
  }
  window.removeEventListener('mousemove', onMouseMove);
  window.removeEventListener('mouseup', onMouseUp);
  state.dialog = null;
  state.img = null;
  state.imgs = null;
  state.zoom = 1;
  state.pan = { x: 0, y: 0 };
  state.dragging = false;
  state.toolbar = null;
  state.label = null;
}

app.registerExtension({
  name: 'ComfyDesktop.MediaLightboxZoom',

  /**
   * 扩展初始化钩子: MutationObserver 监听弹层开合, 打开即接管缩放; 监听 mlz:focus 跟随当前图。
   *
   * @returns {void}
   */
  setup() {
    let currentDialog = null;

    const tick = () => {
      const dlg = findLightbox();
      if (dlg && dlg !== currentDialog) {
        if (currentDialog) cleanupDialog(currentDialog);
        initDialog(dlg);
        currentDialog = dlg;
      } else if (!dlg && currentDialog) {
        cleanupDialog(currentDialog);
        currentDialog = null;
      } else if (dlg === currentDialog && currentDialog) {
        // 切换上一张/下一张: 图片元素被 Vue 重建(key 变化), 重置缩放并重新绑定
        if (!currentDialog.querySelector('.mlz-row')) {
          const img = currentDialog.querySelector('img');
          if (img && img !== state.img) {
            state.img = img;
            img.draggable = false;
            resetZoom();
          }
        }
      }
    };

    tick();
    const observer = new MutationObserver(tick);
    observer.observe(document.body, { childList: true, subtree: true });
    // 自研横向预览: 中键插件切换聚焦图时, 跟随当前图并重置缩放基准
    window.addEventListener('mlz:focus', (e) => {
      if (e.detail && currentDialog) {
        state.img = e.detail;
        if (state.img) {
          state.img.draggable = false;
          resetZoom();
        }
      }
    });
  },
});
