// no_auto_workflow 前端扩展的浏览器验收(无头 Edge + CDP, 零第三方依赖)。
//
// 用法(工作区根, 需 8188 已在跑):
//   node custom_nodes/ComfyUI-FallingTS/dev/_verify-no-auto-workflow.js
//   node .../_verify-no-auto-workflow.js --port 9229 --wait 30000
//   node .../_verify-no-auto-workflow.js --off     # 基线对照: URL 加 ?noAutoWorkflow=off
//
// 五个场景对真实实例真跑(pinia store + 真实关闭按钮):
//   1 启动不自动打开; 2 关非活动标签不误伤; 3 关最后一个不残留;
//   4 关闭后再开正常工作流; 5 显式「加载默认工作流」命令照常执行。
// 断言失败退出码 1。

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

function arg(name, dflt) {
  const a = process.argv.indexOf(name);
  return a >= 0 ? process.argv[a + 1] : dflt;
}

const EDGE = process.env.EDGE_BIN || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = Number(arg('--port', 9229));
const WAIT = Number(arg('--wait', 30000));
const OFF = process.argv.includes('--off');
const URL = 'http://127.0.0.1:8188/' + (OFF ? '?noAutoWorkflow=off' : '');
const profile = path.join(__dirname, '_verify-noauto-profile');

// 上一次可能还有残留的 Edge 占用着 profile(Windows 会 EBUSY): 重试几次, 仍失败就换个目录
function prepareProfile(dir) {
  for (let i = 0; i < 5; i++) {
    try { fs.rmSync(dir, { recursive: true, force: true }); return dir; }
    catch (e) { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500); }
  }
  return dir + '-' + Date.now();
}
const child = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=' + PORT, '--user-data-dir=' + prepareProfile(profile), 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getTarget() {
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch('http://127.0.0.1:' + PORT + '/json/list');
      const list = await res.json();
      const page = list.find((t) => t.type === 'page');
      if (page && page.webSocketDebuggerUrl) return page;
    } catch (e) {}
    await sleep(500);
  }
  throw new Error('CDP not reachable on port ' + PORT);
}

const SCENARIOS = `
window.__verify = (async function () {
  var out = { steps: [], logs: [] };
  var el = document.getElementById('vue-app');
  var pinia = el.__vue_app__.config.globalProperties.$pinia;
  var wf = pinia._s.get('workflow');
  var cmd = pinia._s.get('command');
  var app = window.comfyAPI.app.app;
  function snap(tag) {
    out.steps.push({ tag: tag, open: wf.openWorkflows.map(function (w) { return w.path; }),
      active: wf.activeWorkflow && wf.activeWorkflow.path, nodes: app.rootGraph._nodes.length });
  }
  var pick = function (s) { return wf.workflows.filter(function (w) { return w.path.indexOf(s) >= 0; })[0]; };
  await wf.loadWorkflows();
  snap('startup');
  var a = pick('0011_'), b = pick('0012_');
  await wf.openWorkflow(a);
  await new Promise(function (r) { setTimeout(r, 1200); });
  await wf.openWorkflow(b);
  await new Promise(function (r) { setTimeout(r, 1500); });
  snap('two-open');
  await wf.closeWorkflow(a);
  await new Promise(function (r) { setTimeout(r, 2500); });
  snap('closed-inactive');
  var btn = document.querySelector('[data-testid=close-workflow-button]');
  if (btn) { btn.click(); } else { out.noButton = true; }
  await new Promise(function (r) { setTimeout(r, 4000); });
  snap('closed-last');
  var c = pick('0020_');
  await wf.openWorkflow(c);
  await new Promise(function (r) { setTimeout(r, 2500); });
  snap('reopened');
  if (cmd && cmd.execute) { cmd.execute('Comfy.LoadDefaultWorkflow'); }
  await new Promise(function (r) { setTimeout(r, 4000); });
  snap('explicit-default');
  return JSON.stringify(out);
})();
'ready';
`;

function step(out, tag) { return out.steps.find((s) => s.tag === tag) || {}; }
function empty(s) { return s.open && s.open.length === 0 && !s.active && s.nodes === 0; }

(async () => {
  const target = await getTarget();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const logs = [];
  const send = (method, params) => new Promise((resolve) => {
    const mid = ++id; pending.set(mid, resolve);
    ws.send(JSON.stringify({ id: mid, method, params: params || {} }));
  });
  ws.addEventListener('message', (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); return; }
    if (m.method === 'Runtime.consoleAPICalled') {
      const text = (m.params.args || []).map((x) => (x.value !== undefined ? String(x.value) : x.description || x.type)).join(' ');
      logs.push({ type: m.params.type, text: text });
    }
  });
  await new Promise((r) => ws.addEventListener('open', r));
  await send('Runtime.enable'); await send('Page.enable');
  await send('Page.navigate', { url: URL });
  await sleep(WAIT);
  await send('Runtime.evaluate', { expression: SCENARIOS, returnByValue: true });
  const res = await send('Runtime.evaluate', { expression: 'window.__verify', returnByValue: true, awaitPromise: true });
  const out = JSON.parse(res.result.value);
  const noAuto = logs.filter((l) => /NoAutoWorkflow/i.test(l.text)).map((l) => l.text);
  try { child.kill(); } catch (e) {}

  console.log('=== NoAutoWorkflow 日志 ===');
  for (const l of noAuto) console.log(l);
  console.log('=== 场景快照 ===');
  for (const s of out.steps) console.log(s.tag + ': open=' + JSON.stringify(s.open) + ' active=' + s.active + ' nodes=' + s.nodes);

  const fails = [];
  const startup = step(out, 'startup');
  const two = step(out, 'two-open');
  const inactive = step(out, 'closed-inactive');
  const last = step(out, 'closed-last');
  const reopened = step(out, 'reopened');
  const explicit = step(out, 'explicit-default');
  if (OFF) {
    if (!(startup.open && startup.open.length === 1)) fails.push('基线: 启动应自动打开 1 个工作流, 实际 ' + JSON.stringify(startup.open));
    if (!(last.open && last.open.length === 1)) fails.push('基线: 关最后一个应残留 1 个, 实际 ' + JSON.stringify(last.open));
  } else {
    if (!empty(startup)) fails.push('启动应空白: ' + JSON.stringify(startup));
    if (!(two.open && two.open.length === 2)) fails.push('应同时打开两个标签: ' + JSON.stringify(two.open));
    if (!(inactive.open && inactive.open.length === 1 && inactive.open[0].indexOf('0012_') >= 0)) fails.push('关非活动标签误伤: ' + JSON.stringify(inactive));
    if (!empty(last)) fails.push('关最后一个应无残留: ' + JSON.stringify(last));
    if (!(reopened.open && reopened.open.length === 1 && reopened.active && reopened.active.indexOf('0020_') >= 0)) fails.push('关闭后重开失败: ' + JSON.stringify(reopened));
    if (!(explicit.active && explicit.nodes > 0)) fails.push('显式加载默认工作流被误拦: ' + JSON.stringify(explicit));
  }
  if (fails.length) {
    console.log('=== FAIL ===');
    for (const f of fails) console.log(' - ' + f);
    process.exit(1);
  }
  console.log(OFF ? '=== PASS (基线对照) ===' : '=== PASS ===');
  process.exit(0);
})().catch((e) => { console.error('FATAL', e); try { child.kill(); } catch (x) {} process.exit(1); });
