// comfy-desktop-plugins 前端扩展:
// 在节点上按鼠标中键 → 遍历该节点输出对象的所有 key/value,
// 只要任意值里包含图片, 就调起全屏大图预览
// (与队列/媒体资产的大屏预览同款), 并复用 media_lightbox_zoom.js 的滚轮缩放。
//
// 判断逻辑(2026-08-04 调整):
//   不再只看 outputs.images, 而是递归遍历节点输出对象的所有键和值,
//   并叠加官方预览通道(node.images / node.imgs), 按官方取图顺序:
//   node.images → getNodeOutputs(node).images → node.imgs[i].src
//   图片判定 = 图片链接(/view?、/view/、http(s)、data:、blob:) +
//              所有常见图片后缀(jpg/jpeg/png/gif/webp/bmp/svg/tif/tiff/
//              avif/ico/heic/heif/jfif/pjpeg/pjp/apng/jxl)。
//   单图统一规范成只有 1 张的数组, 兼容 1 张的情况;
//   多图在底部显示 1/n, 左/右方向循环切换(1 后是 n, n 后是 1)。
//   仅修改本插件文件, 不碰 ComfyUI 核心源码与前端包。
//
// 两路触发:
//   - 画布模式(默认): 包装 LGraphCanvas.prototype._processMiddleButton
//   - Vue DOM 模式: 捕获阶段 mousedown 按 [data-node-id] + .image-preview 定位

const { app } = window.comfyAPI.app;

let lastOpenedAt = 0;

/**
 * 从 Vue pinia store 按 id 取 store 对象。
 *
 * @param {string} id store id(如 "nodeOutput")
 * @returns {object|null} pinia store 对象; 不可用时返回 null
 */
function getStore(id) {
  try {
    const el = document.getElementById('vue-app');
    const pinia = el?.__vue_app__?.config?.globalProperties?.$pinia;
    return pinia?._s?.get(id) ?? null;
  } catch {
    return null;
  }
}

/**
 * 按节点 id 从 LGraph 画布找对应 LGraphNode 对象。
 *
 * @param {string|number} nodeId 节点 id
 * @returns {LGraphNode|null} 画布节点对象; 找不到返回 null
 */
function getLGraphNode(nodeId) {
  const graph = app.graph;
  if (!graph?._nodes) return null;
  const sid = String(nodeId);
  for (const n of graph._nodes) {
    if (String(n.id) === sid) return n;
  }
  return null;
}

// 常见图片后缀(扩展名判断用)
const IMAGE_EXTS = new Set([
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'tif', 'tiff',
  'avif', 'ico', 'heic', 'heif', 'jfif', 'pjpeg', 'pjp', 'apng', 'jxl',
]);

/**
 * 取字符串的文件扩展名(小写)。
 *
 * @param {string} s 文件名或 URL
 * @returns {string} 扩展名; 无扩展名返回空串
 */
function getExt(s) {
  const m = typeof s === 'string' ? /\.([a-z0-9]+)(?:[?#].*)?$/i.exec(s) : null;
  return m ? m[1].toLowerCase() : '';
}

/**
 * 判断字符串是否为常见图片路径(按扩展名)。
 *
 * @param {string} s 文件名或 URL
 * @returns {boolean} 是常见图片格式返回 true
 */
function isImagePath(s) {
  return IMAGE_EXTS.has(getExt(s));
}

// 单图 → 数组: 统一成数组格式, 兼容只有 1 张的情况
/**
 * 把单值规范成数组(单图 → 只有 1 张的数组)。
 *
 * @param {*} v 单值或数组
 * @returns {Array} 数组形式
 */
function normalizeToArray(v) {
  return Array.isArray(v) ? v : [v];
}

// 把非 URL 的图片路径/文件名转成 ComfyUI 元数据(默认按 input 目录)
/**
 * 把非 URL 的图片路径/文件名转成 ComfyUI 图片元数据(默认按 input 目录)。
 *
 * @param {string} p 图片路径(可含子目录)
 * @returns {{filename: string, subfolder: string, type: string}} 图片元数据
 */
function pathToImageEntry(p) {
  const parts = String(p).replace(/\\/g, '/').split('/').filter(Boolean);
  const filename = parts.pop() ?? '';
  return { filename, subfolder: parts.join('/'), type: 'input' };
}

// 遍历节点输出对象的所有 key/value + 官方预览通道(node.images / node.imgs),
// 递归收集"看起来像图片"的条目
/**
 * 遍历节点输出对象的所有 key/value + 官方预览通道(node.images / node.imgs),
 * 递归收集"看起来像图片"的条目(去重)。
 *
 * @param {LGraphNode} node 画布节点对象
 * @returns {Array<{filename?: string, subfolder?: string, type?: string, url?: string}>} 图片条目数组
 */
function collectImageEntries(node) {
  const store = getStore('nodeOutput');
  if (!store) return [];

  const found = [];
  const seen = new Set();
  const isUrlLike = (s) =>
    typeof s === 'string' &&
    (s.startsWith('/view?') ||
      s.startsWith('/view/') ||
      /^(https?:|data:|blob:)/i.test(s));

  const push = (entry) => {
    let key;
    if (entry.url) {
      try {
        const u = new URL(entry.url, location.href);
        if (u.pathname.endsWith('/view') || u.pathname.endsWith('/view/')) {
          key = `${u.searchParams.get('filename')}|${u.searchParams.get('subfolder') ?? ''}|${u.searchParams.get('type') ?? ''}`;
        } else {
          key = entry.url;
        }
      } catch {
        key = entry.url;
      }
    } else {
      key = `${entry.filename}|${entry.subfolder ?? ''}|${entry.type ?? ''}`;
    }
    if (!key || seen.has(key)) return;
    seen.add(key);
    found.push(entry);
  };

  // 来源 1: 官方 store 取图函数(优先 nodePreviewImages, 其次 outputs.images)
  if (typeof store.getNodeImageUrls === 'function') {
    const urls = store.getNodeImageUrls(node);
    if (Array.isArray(urls)) {
      for (const u of urls) {
        if (typeof u === 'string') push({ url: u });
      }
    }
  }

  // 来源 2: 递归遍历节点输出对象的所有 key/value
  const outputs =
    typeof store.getNodeOutputs === 'function'
      ? store.getNodeOutputs(node)
      : null;
  const walkArray = (arr, depth) => {
    for (const item of arr) walk(item, depth + 1);
  };
  const walk = (value, depth) => {
    if (value == null || depth > 6) return;
    if (Array.isArray(value)) {
      walkArray(value, depth);
      return;
    }
    if (typeof value === 'object') {
      // 带 filename 且后缀是常见图片格式的 ComfyUI 图片元数据
      if (typeof value.filename === 'string' && isImagePath(value.filename)) {
        push({
          filename: value.filename,
          subfolder: value.subfolder ?? '',
          type: value.type ?? 'output',
        });
        return;
      }
      // 带 url / src / path 的对象: 图片链接或图片路径都算
      const directUrl = value.url ?? value.src ?? value.path;
      if (isUrlLike(directUrl)) {
        push({
          url: directUrl,
          filename:
            typeof value.filename === 'string' ? value.filename : '',
        });
        return;
      }
      if (isImagePath(directUrl)) {
        push(pathToImageEntry(directUrl));
        return;
      }
      // 普通对象 → 每个值先规范成数组再深入(单图也会被当作 1 张)
      for (const v of Object.values(value)) {
        walkArray(normalizeToArray(v), depth);
      }
      return;
    }
    // 字符串: 图片链接 或 常见图片后缀
    if (isUrlLike(value)) push({ url: value });
    else if (isImagePath(value)) push(pathToImageEntry(value));
  };

  if (outputs) {
    // 每个 key 的值先规范成数组(单图 → 只有 1 张的数组)
    for (const key of Object.keys(outputs)) {
      walkArray(normalizeToArray(outputs[key]), 0);
    }
  }

  // 来源 3: node.images(Desktop 同步的输出图片元数据)
  if (Array.isArray(node.images)) {
    for (const img of node.images) {
      if (img && typeof img.filename === 'string' && isImagePath(img.filename)) {
        push({
          filename: img.filename,
          subfolder: img.subfolder ?? '',
          type: img.type ?? 'output',
        });
      } else if (img && typeof img.src === 'string') {
        push({ url: img.src });
      }
    }
  }

  // 来源 4: node.imgs(KSampler 等 latent 预览的 legacy 预览图, 元素带 .src)
  if (Array.isArray(node.imgs)) {
    for (const img of node.imgs) {
      if (img && typeof img.src === 'string' && img.src) {
        push({ url: img.src });
      }
    }
  }

  return found;
}

// 把收集到的图片条目拼成可展示的 /view URL(全尺寸)
/**
 * 把收集到的图片条目拼成可展示的 /view URL(全尺寸, 带防缓存参数)。
 *
 * @param {LGraphNode} node 画布节点对象
 * @returns {string[]} 图片 URL 数组; 没有图片返回空数组
 */
function buildImageUrls(node) {
  const entries = collectImageEntries(node);
  if (!entries.length) return [];

  const rand =
    typeof app.getRandParam === 'function' ? app.getRandParam() : '';
  const base = window.comfyAPI?.api?.api?.api_base ?? '';

  return entries.map((img) => {
    if (img.url) {
      // 完整 URL(https/data/blob)直接用; /view 开头补 base 和防缓存参数
      if (/^(https?:|data:|blob:)/i.test(img.url)) return img.url;
      return base + img.url + rand;
    }
    const params = new URLSearchParams({
      filename: img.filename ?? '',
      subfolder: img.subfolder ?? '',
      type: img.type ?? 'output',
    });
    return base + '/view?' + params.toString() + rand;
  });
}

let overlay = null;
let urls = [];
let current = 0;

/**
 * 渲染当前选中图: 单图布局直接换 img.src, 派发 mlz:focus(重置缩放基准), 更新 1/n 计数。
 *
 * @returns {void}
 */
function renderOverlay() {
  if (!overlay) return;
  // 单图布局: 切换当前图直接换 src(与内置 MediaLightbox 一致)
  const img = overlay.querySelector('.mlz-img');
  if (img && urls[current] && img.src !== urls[current]) {
    img.src = urls[current];
  }
  window.dispatchEvent(new CustomEvent('mlz:focus', { detail: img || null }));
  const counter = overlay.querySelector('.mlz-counter');
  if (counter) {
    if (urls.length > 1) {
      counter.style.display = '';
      counter.textContent = current + 1 + ' / ' + urls.length;
      try {
        counter.title =
          new URL(urls[current] ?? '', location.href).searchParams.get(
            'filename'
          ) || '';
      } catch {
        counter.title = '';
      }
    } else {
      // 单图不显示 1/1
      counter.style.display = 'none';
      counter.textContent = '';
      counter.title = '';
    }
  }
}

/**
 * 关闭预览遮罩并清空状态。
 *
 * @returns {void}
 */
function closeOverlay() {
  overlay?.remove();
  overlay = null;
  urls = [];
  current = 0;
}

/**
 * 创建带悬浮高亮的圆形图标按钮。
 *
 * @param {string} text 按钮文字(如 "×"/"‹"/"›")
 * @param {string} title 悬浮提示
 * @param {Function} onClick 点击回调
 * @returns {HTMLButtonElement} 按钮元素
 */
function mkBtn(text, title, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = text;
  b.title = title;
  b.setAttribute('aria-label', title);
  b.style.cssText =
    'background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);' +
    'color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;';
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
 * 打开预览遮罩: 构建与内置 MediaLightbox 同款布局(单图居中, max 90vh/90vw),
 * 供 media_lightbox_zoom 接管缩放(放大可撑满屏幕); 左右按钮/方向键循环切换, 点遮罩关闭。
 *
 * @param {string[]} list 图片 URL 数组
 * @param {number} startIndex 初始选中图下标
 * @returns {void}
 */
function openOverlay(list, startIndex) {
  if (!list.length) return;

  closeOverlay();
  lastOpenedAt = Date.now();
  urls = list;
  current = Math.max(0, Math.min(startIndex, list.length - 1));

  const dlg = document.createElement('div');
  dlg.setAttribute('data-mask', '');
  dlg.setAttribute('role', 'dialog');
  dlg.setAttribute('aria-modal', 'true');
  dlg.setAttribute('tabindex', '-1');
  // 类名与内置 MediaLightbox 保持一致, 让 media_lightbox_zoom.js 自动接管滚轮缩放
  dlg.className =
    'fixed inset-0 z-9999 flex items-center justify-center bg-black/90 outline-none';

  const counter = document.createElement('div');
  counter.className = 'mlz-counter';
  counter.style.cssText =
    'position:fixed;bottom:76px;left:50%;transform:translateX(-50%);z-index:10;' +
    'color:rgba(255,255,255,.85);font-size:13px;' +
    'background:rgba(15,17,26,.6);padding:4px 12px;border-radius:9999px;';

  const closeBtn = mkBtn('×', '关闭 (Esc)', closeOverlay);
  closeBtn.style.cssText +=
    'position:absolute;top:16px;right:16px;z-index:10;border-radius:9999px;' +
    'width:36px;height:36px;font-size:18px;';

  const prevBtn = mkBtn('‹', '上一张 (←)', () => {
    current = (current - 1 + urls.length) % urls.length;
    renderOverlay();
  });
  prevBtn.style.cssText +=
    'position:fixed;top:50%;left:16px;z-index:10;transform:translateY(-50%);' +
    'border-radius:9999px;width:40px;height:40px;font-size:22px;';

  const nextBtn = mkBtn('›', '下一张 (→)', () => {
    current = (current + 1) % urls.length;
    renderOverlay();
  });
  nextBtn.style.cssText +=
    'position:fixed;top:50%;right:16px;z-index:10;transform:translateY(-50%);' +
    'border-radius:9999px;width:40px;height:40px;font-size:22px;';

  // 单图居中(与内置 MediaLightbox 布局一致): 容器不裁剪(overflow visible),
  // 图片 max 90vh/90vw object-contain —— 放大(transform scale)时图片自然撑满屏幕,
  // 不出现滚动条、不被容器裁剪, 靠拖拽平移查看细节
  const container = document.createElement('div');
  container.className = 'mlz-container';
  container.style.cssText =
    'display:flex;max-height:100%;max-width:100%;align-items:center;justify-content:center;';
  const img = document.createElement('img');
  img.className = 'mlz-img';
  img.src = urls[current];
  img.alt = '';
  img.draggable = false;
  img.style.cssText = 'max-height:90vh;max-width:90vw;object-fit:contain;';
  container.appendChild(img);

  dlg.append(counter, closeBtn, prevBtn, container, nextBtn);

  // 点遮罩关闭(与内置弹层相同逻辑: 按下和松开都在遮罩上才关闭)
  let maskDown = null;
  dlg.addEventListener('mousedown', (e) => {
    maskDown = e.target;
  });
  dlg.addEventListener('mouseup', (e) => {
    if (maskDown === e.target && e.target.hasAttribute?.('data-mask')) {
      closeOverlay();
    }
  });

  dlg.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeOverlay();
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      current = (current - 1 + urls.length) % urls.length;
      renderOverlay();
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      current = (current + 1) % urls.length;
      renderOverlay();
    }
  });

  document.body.appendChild(dlg);
  overlay = dlg;
  dlg.focus();
  renderOverlay();
}

// 两路触发共用: 节点任意 key/value 里有图片则打开预览
/**
 * 两路触发共用: 节点任意 key/value 里有图片则打开预览, 并阻止默认事件。
 *
 * @param {LGraphNode} node 画布节点对象
 * @param {number} startIndex 初始图下标(默认取 node.imageIndex)
 * @param {Event} [e] 触发事件(可空)
 * @returns {boolean} 是否打开了预览
 */
function tryOpenForNode(node, startIndex, e) {
  if (!node) return false;
  const list = buildImageUrls(node);
  if (!list.length) return false;
  if (e) {
    e.preventDefault?.();
    e.stopPropagation?.();
  }
  openOverlay(
    list,
    startIndex ?? (typeof node.imageIndex === 'number' ? node.imageIndex : 0)
  );
  return true;
}

/**
 * 判断是否刚打开过预览(300ms 内), 避免中键按下后拖动被误判为重复单击。
 *
 * @returns {boolean} 刚打开过返回 true
 */
function wasJustOpened() {
  return Date.now() - lastOpenedAt < 300;
}

// 与官方一致的槽位命中判定(官方矩形: 中心 ±15 x ±10)
/**
 * 与官方一致的槽位命中判定(官方矩形: 中心 ±15 x ±10)。
 *
 * @param {LGraphNode} node 画布节点对象
 * @param {Event} e 事件(含 canvasX / canvasY)
 * @returns {boolean} 鼠标落在输入/输出槽上返回 true
 */
function isOnSocket(node, e) {
  if (!node) return false;
  const x = e.canvasX;
  const y = e.canvasY;
  if (node.outputs) {
    for (let i = 0; i < node.outputs.length; i++) {
      const p = node.getOutputPos?.(i);
      if (p && Math.abs(x - p[0]) <= 15 && Math.abs(y - p[1]) <= 10) {
        return true;
      }
    }
  }
  if (node.inputs) {
    for (let i = 0; i < node.inputs.length; i++) {
      const p = node.getInputPos?.(i);
      if (p && Math.abs(x - p[0]) <= 15 && Math.abs(y - p[1]) <= 10) {
        return true;
      }
    }
  }
  return false;
}

// 画布模式(默认): 包装 LGraphCanvas.prototype._processMiddleButton
// 官方 processMouseDown 已把中键事件 + 鼠标下的节点传进来。
// 只在“节点主体单击”这一官方原本无操作的场景注册大屏预览回调,
// 槽位点击(中键加默认节点)、折叠节点、无图节点、中键拖动画布
// 全部原样交给官方方法处理, 不影响官方中键行为。
/**
 * 画布模式补丁: 包装 LGraphCanvas.prototype._processMiddleButton,
 * 只在"节点主体单击中键"且节点有图时注册单击回调打开预览(槽位/折叠/拖动画布交给官方)。
 *
 * @returns {boolean} 是否安装成功
 */
function installMiddleButtonPatch() {
  const canvas = app.canvas;
  const proto = canvas?.constructor?.prototype;
  if (!proto) return false;
  if (proto.__mlzMiddlePatched) return true;

  const orig = proto._processMiddleButton;
  if (typeof orig !== 'function') return false;

  proto._processMiddleButton = function (e, node) {
    // 节点主体(非槽位、非折叠)中键单击 → 节点任意值里有图片则注册预览回调
    if (
      node &&
      !node.flags?.collapsed &&
      !isOnSocket(node, e) &&
      !wasJustOpened()
    ) {
      const list = buildImageUrls(node);
      if (list.length) {
        const start =
          typeof node.imageIndex === 'number' ? node.imageIndex : 0;
        // 与官方“中键槽位加默认节点”同一机制: 注册单击回调,
        // 只有按下后未拖动(真单击)才会触发, 拖动仍交给官方拖动画布
        if (this.pointer) {
          this.pointer.onClick = () => openOverlay(list, start);
        }
      }
    }
    return orig.apply(this, [e, node]);
  };

  proto.__mlzMiddlePatched = true;
  return true;
}

// Vue DOM 模式: 捕获阶段 mousedown, 按 [data-node-id] + .image-preview 定位
/**
 * Vue DOM 模式: 捕获阶段 mousedown, 按 [data-node-id] + .image-preview 定位节点, 中键打开预览。
 *
 * @param {MouseEvent} e 鼠标事件
 * @returns {void}
 */
function onPreviewMouseDown(e) {
  if (e.button !== 1) return;
  const target = e.target;
  if (!(target instanceof Element)) return;

  const nodeEl = target.closest('[data-node-id]');
  const previewEl = nodeEl && target.closest('.image-preview');
  if (!nodeEl || !previewEl) return;
  if (target.closest('.actions')) return;

  const node = getLGraphNode(nodeEl.getAttribute('data-node-id'));
  if (!node) return;

  let start = 0;
  const grid = target.closest('[data-testid="image-grid"]');
  if (grid) {
    const btn = target.closest('button');
    if (btn) {
      const idx = Array.prototype.indexOf.call(grid.children, btn);
      if (idx >= 0) start = idx;
    }
  } else if (typeof node.imageIndex === 'number') {
    start = node.imageIndex;
  }

  tryOpenForNode(node, start, e);
}

app.registerExtension({
  name: 'ComfyDesktop.NodeImageMiddleClick',

  /**
   * 扩展初始化钩子: 挂 Vue DOM mousedown 捕获 + 画布中键补丁(失败每秒重试直到画布就绪)。
   *
   * @returns {void}
   */
  setup() {
    document.body.addEventListener('mousedown', onPreviewMouseDown, true);
    // 画布模式补丁: 立即尝试, 失败则每秒重试(等 app.canvas 就绪)
    const tryInstall = () => {
      if (!installMiddleButtonPatch()) setTimeout(tryInstall, 1000);
    };
    tryInstall();
  },
});
