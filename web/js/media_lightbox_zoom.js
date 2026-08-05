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
function isLightbox(el) {
  return (
    el &&
    el.matches?.('div[role="dialog"][data-mask]') &&
    el.classList.contains('bg-black/90') &&
    el.classList.contains('z-9999')
  );
}

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

function updateToolbar() {
  if (state.label) {
    state.label.textContent = Math.round(state.zoom * 100) + '%';
  }
  if (state.toolbar) {
    state.toolbar.style.display = state.img ? 'flex' : 'none';
  }
}

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

function resetZoom() {
  state.zoom = 1;
  state.pan = { x: 0, y: 0 };
  applyTransform(true);
}

// 以鼠标位置为锚点缩放
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

function zoomAtCenter(factor) {
  const img = state.img;
  if (!img) return;
  const rect = img.getBoundingClientRect();
  zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor);
}

function onWheel(e) {
  if (!state.img) return;
  e.preventDefault();
  // 兼容滚轮 / 触控板 / 捏合: deltaY 归一化后用指数映射
  const delta = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY;
  const factor = Math.exp(-delta * 0.002);
  zoomAt(e.clientX, e.clientY, Math.min(2, Math.max(0.5, factor)));
}

function onMouseDown(e) {
  if (e.button !== 0 || !state.img || state.zoom <= 1.0001) return;
  state.dragging = true;
  state.dragLast = { x: e.clientX, y: e.clientY };
  state.dragStartPan = { x: state.pan.x, y: state.pan.y };
  e.preventDefault();
  applyTransform();
}

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

function onMouseUp() {
  if (!state.dragging) return;
  state.dragging = false;
  applyTransform();
}

function onDblClick(e) {
  if (!state.img) return;
  e.preventDefault();
  if (state.zoom > 1.0001) {
    resetZoom();
  } else {
    zoomAt(e.clientX, e.clientY, 2.2);
  }
}

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
