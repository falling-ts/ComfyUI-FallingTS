// comfy-desktop-plugins 前端扩展:
// 在运行按钮面板末尾添加"刷新工作流"图标按钮, 点击后从磁盘重新加载当前工作流, 无需刷新页面。
//
// 实现要点:
//   1. 通过 DOM 注入把图标按钮追加到运行面板容器末尾(运行按钮/中断/队列切换之后)
//   2. 点击后优先走内置机制: userFile.syncFiles() 检测外部修改并 unload,
//      workflow.reloadCurrentWorkflow() 重新从磁盘加载(保留工作流关联与撤销历史)
//   3. 若拿不到内部 store(前端版本变化), 回退为直接 fetch 磁盘 JSON + loadGraphData
//   4. 当前标签有未保存改动时跳过刷新, 防止覆盖

const { app } = window.comfyAPI.app;

function getStore(id) {
  try {
    const el = document.getElementById('vue-app');
    const pinia = el?.__vue_app__?.config?.globalProperties?.$pinia;
    return pinia?._s?.get(id) ?? null;
  } catch {
    return null;
  }
}

// 自包含确认弹窗: 不依赖 ComfyDialog / window.confirm(前端升级后这些 API 可能变化/失效),
// 用纯 DOM 渲染, 保证"未保存→确认"弹窗一定出现。
function confirmUnsaved(workflowPath) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.style.cssText =
      'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;' +
      'background:rgba(0,0,0,.55);';
    const box = document.createElement('div');
    box.style.cssText =
      'background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:8px;padding:20px 24px;' +
      'max-width:480px;box-shadow:0 10px 40px rgba(0,0,0,.6);font-size:14px;';
    const msg = document.createElement('div');
    msg.style.cssText = 'margin-bottom:18px;white-space:pre-wrap;line-height:1.6;';
    msg.textContent =
      '工作流未保存, 重载会丢失, 是否确认' + (workflowPath ? '\n' + workflowPath : '');
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:12px;justify-content:flex-end;';
    const mkBtn = (label, primary) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.style.cssText =
        'padding:6px 16px;border-radius:6px;cursor:pointer;border:1px solid #555;' +
        (primary ? 'background:#4a8ef5;color:#fff;' : 'background:#333;color:#ccc;');
      return b;
    };
    const ok = mkBtn('确认', true);
    const cancel = mkBtn('取消', false);
    let done = false;
    const finish = (val) => {
      if (done) return;
      done = true;
      overlay.remove();
      resolve(val);
    };
    ok.onclick = () => finish(true);
    cancel.onclick = () => finish(false);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) finish(false);
    });
    row.append(ok, cancel);
    box.append(msg, row);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
  });
}

async function reloadFromDisk() {
  try {
    // 安全检查: 当前标签有未保存改动 → 弹窗确认, 防止误覆盖
    const workflowStore = getStore('workflow');
    const activeWorkflow = workflowStore?.activeWorkflow;
    if (activeWorkflow?.isModified) {
      const ok = await confirmUnsaved(activeWorkflow.path);
      if (!ok) {
        console.warn('[WorkflowReload] 用户取消刷新(工作流未保存)');
        return;
      }
      console.warn('[WorkflowReload] 用户确认刷新,未保存改动将被覆盖');
    }

    // 优先: 内置机制(保留工作流关联 / 撤销历史 / 草稿)
    const userFile = getStore('userFile');
    // reloadCurrentWorkflow 定义在"含 activeWorkflow"的 workflow store 里(前端源码确认),
    // 不在 appMode store —— 之前误查 appMode 导致主路径失效、落入回退、刷成第一个工作流。
    const reloadFn =
      workflowStore?.reloadCurrentWorkflow ??
      getStore('appMode')?.reloadCurrentWorkflow;
    if (userFile?.syncFiles && reloadFn) {
      await userFile.syncFiles();
      await reloadFn();
      console.log('[WorkflowReload] 已从磁盘重新加载当前工作流(内置机制)');
      return;
    }

    // 回退: 直接按"当前激活工作流"的 path 读盘。
    // 注意: 不能用 app.rootGraph.id —— rootGraph 指向第一个打开的工作流, 不是当前标签。
    console.warn('[WorkflowReload] 内部 reloadCurrentWorkflow 不可用,使用回退方式', {
      userFile: !!userFile,
      reloadFn: !!reloadFn,
      activeWorkflowPath: activeWorkflow?.path,
    });
    const wfPath = activeWorkflow?.path;
    if (!wfPath) {
      console.warn('[WorkflowReload] 拿不到当前激活工作流 path,放弃');
      return;
    }
    const candidates = wfPath.startsWith('workflows/')
      ? [wfPath]
      : ['workflows/' + wfPath, wfPath];
    for (const fullPath of candidates) {
      const r = await fetch('/userdata/' + encodeURIComponent(fullPath), {
        cache: 'no-store',
      });
      if (!r.ok) continue;
      const json = await r.json();
      // 关键: 第 4 个参数必须传当前工作流对象(或文件名),
      // 否则 afterLoadNewGraph 会 createNewTemporary 开新标签
      await app.loadGraphData(json, true, true, activeWorkflow);
      console.log('[WorkflowReload] 已从磁盘加载当前工作流:', fullPath);
      return;
    }
    console.warn('[WorkflowReload] 读取当前工作流失败:', candidates);
  } catch (e) {
    console.error('[WorkflowReload] 刷新失败:', e);
  }
}

function injectRefreshButton() {
  // 定位运行面板里的队列切换按钮(唯一), 追加到其父容器(运行按钮那一簇)末尾
  const toggle = document.querySelector('[data-testid="queue-overlay-toggle"]');
  const container = toggle?.parentElement;
  if (!container || container.querySelector('.wf-reload-btn')) return;

  const btn = document.createElement('button');
  btn.type = 'button';
  // 复用"0 个活动任务"队列按钮的同款样式类(PrimeVue secondary/md), 只追加标记类用于去重
  btn.className = ((toggle.className || '').replace(/wf-reload-btn/g, '') + ' wf-reload-btn').trim();
  btn.title = '从磁盘重新加载当前工作流(无需刷新页面)';
  btn.setAttribute('aria-label', btn.title);
  btn.innerHTML = '<i class="icon-[lucide--refresh-cw] block size-4 leading-none"></i>';
  btn.addEventListener('click', reloadFromDisk);
  container.appendChild(btn);
}

app.registerExtension({
  name: 'ComfyDesktop.WorkflowReloadButton',
  setup() {
    injectRefreshButton();
    // 运行面板可能重新渲染(停靠/浮动/队列变化), 用 MutationObserver 保持按钮存在
    const observer = new MutationObserver(() => injectRefreshButton());
    observer.observe(document.body, { childList: true, subtree: true });
  },
});
