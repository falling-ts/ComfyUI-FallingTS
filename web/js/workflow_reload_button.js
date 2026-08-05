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

// 使用 ComfyUI 稳定暴露的旧版确认弹窗 (window.comfyAPI.ui.ComfyDialog),
// 不依赖任何带 hash 的构建 chunk, 前端升级后依然可用。
function confirmUnsaved(workflowPath) {
  return new Promise((resolve) => {
    const ComfyDialog =
      window.comfyAPI?.ui?.ComfyDialog || window.comfyAPI?.dialog?.ComfyDialog;
    if (!ComfyDialog) {
      console.warn('[WorkflowReload] ComfyDialog 不可用,回退到 window.confirm');
      resolve(window.confirm('工作流未保存, 重载会丢失, 是否确认'));
      return;
    }

    let settled = false;
    const finish = (val) => {
      if (settled) return;
      settled = true;
      dialog.close();
      resolve(val);
    };

    const okBtn = document.createElement('button');
    okBtn.type = 'button';
    okBtn.textContent = '确认';
    okBtn.onclick = () => finish(true);
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = '取消';
    cancelBtn.onclick = () => finish(false);

    const dialog = new ComfyDialog('div', [okBtn, cancelBtn]);
    const msg =
      '工作流未保存, 重载会丢失, 是否确认' +
      (workflowPath ? '\n' + workflowPath : '');
    dialog.show(msg);
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
    // 注意: reloadCurrentWorkflow 位于 appMode store(源码确认), 不是 workflow store
    const appMode = getStore('appMode');
    if (userFile?.syncFiles && appMode?.reloadCurrentWorkflow) {
      await userFile.syncFiles();
      await appMode.reloadCurrentWorkflow();
      console.log('[WorkflowReload] 已从磁盘重新加载当前工作流(内置机制)');
      return;
    }

    // 回退: 直接拉取磁盘 JSON 并按 id 匹配当前画布
    console.warn('[WorkflowReload] 内部 store 不可用,使用回退方式', {
      userFile: !!userFile,
      appMode: !!appMode,
    });
    const currentId = app?.rootGraph?.id;
    if (!currentId) return;
    const list = await (
      await fetch(
        '/userdata?dir=workflows&recurse=true&split=false&full_info=true',
        { cache: 'no-store' }
      )
    ).json();
    for (const f of list) {
      if (f.type && f.type !== 'file') continue;
      // 列表接口(dir=workflows)返回的 path 相对 workflows 目录, 需补前缀(前端 syncEntities 同款逻辑)
      const fullPath = 'workflows/' + f.path;
      const r = await fetch('/userdata/' + encodeURIComponent(fullPath), {
        cache: 'no-store',
      });
      if (!r.ok) continue;
      const json = await r.json();
      if (json?.id === currentId) {
        // 关键: 第 4 个参数必须传当前工作流对象(或文件名),
        // 否则 afterLoadNewGraph 会 createNewTemporary 开新标签
        await app.loadGraphData(json, true, true, activeWorkflow ?? f.path);
        console.log('[WorkflowReload] 已从磁盘加载:', fullPath);
        return;
      }
    }
    console.warn('[WorkflowReload] 未找到与当前画布匹配的工作流文件');
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
