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
//
// ⚠️ 节点数的判据是 `activeWorkflow.activeState.nodes.length`(工作流存档内容), **不是**
//    `app.rootGraph._nodes.length` —— 前端 1.55.18 起画布渲染走 Vue 节点层, `rootGraph` 在
//    打开工作流后仍停在启动时的默认图(实测恒为 10 个节点、与真实工作流 41/28/39 无关),
//    用它做断言会得出"节点数 0 / 恒 10"的错误结论。

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
  window.__verifyDump = out;
  try {
  var el = document.getElementById('vue-app');
  var pinia = el.__vue_app__.config.globalProperties.$pinia;
  var wf = pinia._s.get('workflow');
  var cmd = pinia._s.get('command');
  var app = window.comfyAPI.app.app;
  function snap(tag) {
    var aw = wf.activeWorkflow;
    var st = aw && aw.activeState;
    var rg = app.rootGraph;
    out.steps.push({ tag: tag, open: wf.openWorkflows.map(function (w) { return w.path; }),
      active: aw && aw.path,
      nodes: st && st.nodes ? st.nodes.length : 0,
      links: st && st.links ? st.links.length : 0,
      // 画布真实节点数: 关闭最后一个工作流后必须为 0(2026-11-12 新增, 治"标签空了画布还留着旧图")
      canvasNodes: rg && rg._nodes ? rg._nodes.length : -1,
      canvasLinks: rg && rg.links ? Object.keys(rg.links).length : -1,
      graphId: rg && rg.id });
  }
  var pick = function (s) {
    var list = (wf.workflows && wf.workflows.value) ? wf.workflows.value : wf.workflows;
    if (!list) return undefined;
    for (var i = 0; i < list.length; i++) if (list[i] && String(list[i].path).indexOf(s) >= 0) return list[i];
    return undefined;
  };
  await wf.loadWorkflows();
  await new Promise(function (r) { setTimeout(r, 1500); });
  snap('startup');
  var a = pick('0060_'), b = pick('0061_'), c = pick('0062_');
  if (!a || !b || !c) {
    out.missing = { a: !!a, b: !!b, c: !!c,
      available: (function(){ var l=(wf.workflows&&wf.workflows.value)?wf.workflows.value:wf.workflows; return l?l.map(function(w){return w.path}):[] })() };
    return JSON.stringify(out);
  }
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
  await wf.openWorkflow(c);
  await new Promise(function (r) { setTimeout(r, 2500); });
  snap('reopened');
  if (cmd && cmd.execute) { cmd.execute('Comfy.LoadDefaultWorkflow'); }
  await new Promise(function (r) { setTimeout(r, 4000); });
  snap('explicit-default');
  return JSON.stringify(out);
  } catch (e) {
    window.__verifyError = (e && e.stack) || String(e);
    throw e;
  }
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
  // 场景脚本是 async IIFE: reject 时重抛进 window.__verifyError, 这里先把真实原因打出来,
  // 否则外层只能看到一个 "[object Object] is not valid JSON" 的 JSON.parse 报错(实测踩过)。
  if (res.exceptionDetails || typeof res.result.value !== 'string') {
    const e = await send('Runtime.evaluate', { expression: 'String(window.__verifyError || "")', returnByValue: true });
    console.error('场景脚本失败:', (res.exceptionDetails && res.exceptionDetails.text) || '', e.result && e.result.value);
    const dump = await send('Runtime.evaluate', { expression: 'JSON.stringify(window.__verifyDump || null)', returnByValue: true });
    console.error('已走过的步骤:', dump.result && dump.result.value);
    try { child.kill(); } catch (x) {}
    process.exit(1);
  }
  const out = JSON.parse(res.result.value);
  const noAuto = logs.filter((l) => /NoAutoWorkflow/i.test(l.text)).map((l) => l.text);
  try { child.kill(); } catch (e) {}

  console.log('=== NoAutoWorkflow 日志 ===');
  for (const l of noAuto) console.log(l);
  console.log('=== 场景快照 ===');
  for (const s of out.steps) console.log(s.tag + ': open=' + JSON.stringify(s.open) + ' active=' + s.active + ' nodes=' + s.nodes + ' canvas=' + s.canvasNodes);

  const fails = [];
  // 钩子必须真的装上, 否则"关闭后清空画布"这条新行为根本没生效(静默失败最难查)
  if (!noAuto.some((l) => /closeWorkflow 钩子已就位/.test(l))) {
    fails.push('closeWorkflow 钩子未安装(关闭后不会清空画布)');
  }
  if (out.missing) {
    console.log('=== SKIP ===');
    console.log(' 工作流列表里找不到测试用的文件: ' + JSON.stringify(out.missing));
    process.exit(2);
  }
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
    if (!(inactive.open && inactive.open.length === 1 && inactive.open[0].indexOf('0061_') >= 0)) fails.push('关非活动标签误伤: ' + JSON.stringify(inactive));
    // ⚠️ 2026-11-12: 关闭最后一个工作流后必须「一个都不剩」。
    //    判据是 store 状态(openWorkflows 空 + activeWorkflow null), **不是** rootGraph._nodes:
    //    headless Edge 下 rootGraph._nodes 恒为 0(工作流真实内容在 activeWorkflow.activeState),
    //    拿它断言会得到"永远通过"的假阳性 —— 实测踩过。
    //    canvasNodes 只作为诊断打印, 不参与断言。
    if (!empty(last)) fails.push('关最后一个应无残留: ' + JSON.stringify(last));
    if (!(reopened.open && reopened.open.length === 1 && reopened.active && reopened.active.indexOf('0062_') >= 0)) fails.push('关闭后重开失败: ' + JSON.stringify(reopened));
    if (!(explicit.active && explicit.nodes > 0)) fails.push('显式加载默认工作流被误拦: ' + JSON.stringify(explicit));
    // ⚠️ 回归护栏: 拦截路径绝不能把画布/workflow 清空。打开真实工作流后必须带节点与连线,
    //    这正是 1.55.18 上 blankCanvas() → app.clean() 造成「画布空白、节点数 0」的地方。
    if (!(two.nodes > 0)) fails.push('打开工作流后节点数为 0(拦截把图清空了): ' + JSON.stringify(two));
    if (!(two.links > 0)) fails.push('打开工作流后连线数为 0(拦截把图清空了): ' + JSON.stringify(two));
    if (!(inactive.nodes > 0)) fails.push('关闭无关标签后活动工作流节点数归零: ' + JSON.stringify(inactive));
    if (!(reopened.nodes > 0)) fails.push('关闭后再打开的工作流节点数为 0: ' + JSON.stringify(reopened));
  }
  if (fails.length) {
    console.log('=== FAIL ===');
    for (const f of fails) console.log(' - ' + f);
    process.exit(1);
  }
  console.log(OFF ? '=== PASS (基线对照) ===' : '=== PASS ===');
  process.exit(0);
})().catch((e) => { console.error('FATAL', e); try { child.kill(); } catch (x) {} process.exit(1); });
