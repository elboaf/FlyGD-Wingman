// Executes generated capture expressions and whole production modules against
// real markup ancestry. Only DOM mechanics and external delivery are doubled.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const scrolls = [];
class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase(); this.attrs = {...attrs};
    this.id = attrs.id || ''; this.className = attrs.class || '';
    this.children = []; this.listeners = {}; this.style = {};
    this.value = attrs.value || ''; this.hidden = 'hidden' in attrs;
    this.disabled = 'disabled' in attrs; this.checked = 'checked' in attrs;
    this.dataset = Object.fromEntries(Object.entries(attrs).filter(([k]) => k.startsWith('data-'))
      .map(([k, v]) => [k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase()), v]));
  }
  appendChild(el) { this.children.push(el); el.parentNode = this; return el; }
  prepend(el) { this.children.unshift(el); el.parentNode = this; }
  insertBefore(el, before) { this.children.splice(this.children.indexOf(before), 0, el); el.parentNode = this; }
  removeChild(el) { this.children.splice(this.children.indexOf(el), 1); el.parentNode = null; return el; }
  get firstChild() { return this.children[0] || null; }
  get firstElementChild() { return this.firstChild; }
  get nextSibling() { return this.parentNode?.children[this.parentNode.children.indexOf(this) + 1] || null; }
  get previousElementSibling() { return this.parentNode?.children[this.parentNode.children.indexOf(this) - 1] || null; }
  set textContent(text) { this.children = []; this.text = String(text); }
  get textContent() { return (this.text || '') + this.children.map(el => el.textContent).join(''); }
  set innerHTML(text) { assert.equal(text, ''); this.textContent = ''; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'id') this.id = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  removeAttribute(k) { delete this.attrs[k]; }
  get classList() { return {
    contains: name => this.className.split(/\s+/).includes(name),
    toggle: (name, on) => {
      if (on === undefined) on = !this.classList.contains(name);
      this.className = this.className.split(/\s+/).filter(x => x && x !== name).concat(on ? [name] : []).join(' ');
    },
    add: name => this.classList.toggle(name, true), remove: name => this.classList.toggle(name, false)
  }; }
  matches(selector) {
    let s = selector;
    if (s === '*') return true;
    if (s.includes(':not(:empty)')) { if (!this.children.length && !this.text) return false; s = s.replace(':not(:empty)', ''); }
    if (s.includes(':checked')) { if (!this.checked) return false; s = s.replace(':checked', ''); }
    const attributes = [...s.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)];
    if (!attributes.every(m => m[2] === undefined ? this.getAttribute(m[1]) !== null
      : (m[1] === 'type' ? this.type || this.getAttribute('type') : this.getAttribute(m[1])) === m[2])) return false;
    s = s.replace(/\[[^\]]+\]/g, '');
    const id = s.match(/#([\w-]+)/); if (id && this.id !== id[1]) return false;
    if (![...s.matchAll(/\.([\w-]+)/g)].every(m => this.classList.contains(m[1]))) return false;
    const tag = s.match(/^[\w-]+/); return !tag || this.tagName.toLowerCase() === tag[0];
  }
  querySelectorAll(selector) {
    const descendants = this.children.flatMap(el => [el, ...el.querySelectorAll('*')]);
    return descendants.filter(el => selector.split(',').some(part => {
      const chain = part.trim().split(/\s+(?![^\[]*\])/);
      let node = el;
      if (!node.matches(chain.pop())) return false;
      while (chain.length) {
        const parent = chain.pop();
        if (parent === '>') { node = node.parentNode; if (!node || !node.matches(chain.pop())) return false; }
        else { node = node.parentNode; while (node && !node.matches(parent)) node = node.parentNode; if (!node) return false; }
      }
      return true;
    }));
  }
  querySelector(s) { return this.querySelectorAll(s)[0] || null; }
  closest(s) { let el = this; while (el && !el.matches(s)) el = el.parentNode; return el; }
  contains(el) { return el === this || this.querySelectorAll('*').includes(el); }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  removeEventListener(name, callback) { this.listeners[name] = (this.listeners[name] || []).filter(x => x !== callback); }
  dispatchEvent(event) {
    event.target ||= this; event.preventDefault ||= () => {}; event.stopPropagation ||= () => {};
    (this.listeners[event.type] || []).forEach(callback => callback(event));
  }
  click() { if (!this.disabled) this.dispatchEvent({type: 'click'}); }
  focus() { document.activeElement = this; }
  scrollIntoView(options) { scrolls.push({element: this, options}); }
  getBoundingClientRect() { return {width: 400, height: 240, top: 0, bottom: 240, left: 0, right: 400}; }
}
function build(node) { const el = new Element(node.tag, node.attrs); node.children.forEach(child => el.appendChild(build(child))); return el; }
const document = build(data.page);
document.readyState = 'complete'; document.body = document.querySelector('body');
document.getElementById = id => document.querySelectorAll('*').find(el => el.id === id) || null;
document.createElement = tag => new Element(tag);
document.createElementNS = (_, tag) => new Element(tag);
const window = new Element('window');
Object.assign(window, {document, console: {...console, error: (...args) => { throw Error(args.join(' ')); }},
  navigator: {clipboard: {readText: () => assert.fail('clipboard read'), writeText: () => assert.fail('clipboard write')}},
  Promise, Math, Date, TextEncoder, URLSearchParams,
  Event: class { constructor(type) { this.type = type; } },
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
  setTimeout, clearTimeout, requestAnimationFrame: callback => setTimeout(callback, 0),
  matchMedia: () => ({matches: false}), location: {search: ''}});
window.window = window;
const runtime = vm.createContext(window);
const run = expression => vm.runInContext(expression, runtime);
run(fs.readFileSync(web + '/app.js', 'utf8'));
const WM = window.WM;
const calls = [];
let staging = false;
let bridgeReply = () => null;
WM.send = (method, ...args) => {
  calls.push([method, ...args]);
  if (staging) assert.fail('Staged screen reached bridge: ' + method);
  return Promise.resolve(bridgeReply(method, ...args));
};
WM.confirm = () => { if (staging) assert.fail('Unexpected confirmation'); return Promise.resolve(false); };
const crop = data.key.startsWith('settings-');
const moduleName = data.key === 'fittings-detail' ? 'fittings'
  : crop ? 'previews' : data.key.includes('formations') ? 'formations' : 'uisetup';
run(fs.readFileSync(web + '/' + moduleName + '.js', 'utf8'));
const tick = () => new Promise(resolve => setTimeout(resolve, 10));
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };
async function cropRegression() {
  const scenario = data.regression;
  const fixture = data.crop_fixture;
  const owner = fixture.owner;
  const live = JSON.parse(JSON.stringify(fixture.preview));
  live.hotkeys.characters[owner] = 'Ctrl+Alt+9';
  live.crops = JSON.parse(JSON.stringify(fixture.crops));
  live.crops.revision = 10;
  document.activeElement = document.body;
  window.onPreviewHotkeys(live);
  document.dispatchEvent({type: 'wm:preview-minimize-inactive', detail: {enabled: true}});
  run(data.stage);
  const detail = name => document.querySelector('[data-preview-detail-control="' + name + '"]');
  const button = (selector, text) => {
    const el = document.querySelectorAll(selector).find(el => el.textContent === text);
    assert.ok(el, 'rendered ' + text); return el;
  };
  const change = (el, value) => {
    assert.ok(el, 'rendered change control'); assert.equal(el.disabled, false);
    if (el.type === 'checkbox') el.checked = !el.checked; else el.value = value;
    el.dispatchEvent({type: 'change'});
  };
  const actions = {
    clear: () => button('.rowacts button', 'Clear').click(),
    'group-clear': () => document.querySelectorAll('.row').find(row => row.querySelector('.lab-name')?.textContent === 'DPS').querySelector('.rowacts button').click(),
    capture: () => document.querySelector('.bindbtn').click(),
    bind: () => button('.rowacts button', 'Edit…').click(),
    size: () => detail('size').click(), copy: () => detail('copy').click(),
    exclude: () => change(document.querySelector('.optout input')),
    lock: () => change(document.querySelector('[data-preview-lock]')),
    'never-minimize': () => change(document.querySelector('.nm input')),
    group: () => change(detail('group'), 'g-logi'),
    add: () => { document.querySelector('.group-add-name').value = 'New group'; document.querySelector('.group-add-btn').click(); },
    rename: () => document.querySelector('.group-rename-btn').click(),
    delete: () => document.querySelector('.group-delete-btn').click(),
    'crop-select': () => detail('crop-select').click(),
    'crop-remove': () => detail('crop-remove').click(),
    'crop-enabled': () => change(detail('crop-enabled')),
    reentry: () => WM.section('previews')
  };
  const expected = {
    clear: 'set_preview_binds', 'group-clear': 'set_preview_cycle_group_bind', capture: 'set_bind_capture',
    bind: 'set_preview_binds', size: 'set_preview_size', copy: 'copy_preview_layout',
    exclude: 'set_preview_excluded', lock: 'set_preview_locked', 'never-minimize': 'set_never_minimize',
    group: 'set_preview_character_group', add: 'create_preview_cycle_group', rename: 'rename_preview_cycle_group',
    delete: 'delete_preview_cycle_group', 'crop-select': 'select_preview_crop', 'crop-remove': 'remove_preview_crop',
    'crop-enabled': 'set_preview_crop_enabled', reentry: 'get_preview_hotkey_state'
  };
  if (scenario.operation) {
    // A real request has its receipt and pending getter before capture begins.
    const pending = {...live.crops, revision: 11, busy: true,
      operations: {'50': {operation_id: 50, name: owner, pending: true}}, statuses: {[owner]: 'saving'}};
    bridgeReply = method => method === 'select_preview_crop' ? {applied: true, operation_id: 50, pending: true}
      : method === 'get_preview_crop_state' ? pending : null;
    actions['crop-select'](); await tick();
    assert.match(document.querySelector('.preview-crop-status').textContent, /Saving/);
    calls.length = 0; staging = true;
    run(data.prepare); run(data.stage);
    const id = {matching: 50, newer: 51, older: 49}[scenario.operation];
    window.onPreviewCrops({...live.crops, revision: 12,
      operations: {[id]: {operation_id: id, name: owner, pending: false}}});
    run(data.cleanup); run(data.stage);
    const status = document.querySelector('.preview-crop-status').textContent;
    if (scenario.operation === 'older') assert.match(status, /Saving/, 'an older terminal ID cannot settle this request');
    else {
      assert.doesNotMatch(status, /Saving/, 'cleanup must settle the buffered terminal request without another event');
      assert.equal(detail('crop-select').disabled, false);
    }
    assert.equal(calls.length, 0);
    return;
  }
  const parsed = scenario.control === 'size' ? {w: 640, h: 360} : {gesture: 'Ctrl+Alt+8'};
  const dialogValue = {size: '640x360', bind: 'Ctrl+Alt+8', copy: 'Tanuki Solette', rename: 'Renamed'}[scenario.control] ?? true;
  const waiting = deferred();
  let dialogCalls = 0;
  for (const name of ['prompt', 'confirm', 'choose']) WM[name] = () => {
    assert.equal(staging, false, 'fixture must not open a live dialog'); dialogCalls++;
    return scenario.late === 'dialog' ? waiting.promise : Promise.resolve(dialogValue);
  };
  bridgeReply = method => method === 'get_preview_hotkey_state' ? live
    : method === 'get_preview_crop_state' ? live.crops
    : method.startsWith('parse_preview_') ? (scenario.late === 'parser' ? waiting.promise : parsed)
    : {applied: true, operation_id: null};
  if (scenario.late) {
    actions[scenario.control](); await tick();
    assert.equal(dialogCalls, 1, 'dialog began on live data');
    if (scenario.late === 'parser') assert.ok(calls.some(call => call[0].startsWith('parse_preview_')));
  }
  calls.length = 0; staging = true;
  run(data.prepare); run(data.stage);
  if (scenario.late) waiting.resolve(scenario.late === 'parser' ? parsed : dialogValue);
  else actions[scenario.control]();
  await tick();
  assert.equal(calls.length, 0, 'fixture interaction and late continuations must not reach the bridge');
  run(data.cleanup); await tick();
  assert.equal(calls.length, 0, 'cleanup must remain local');
  staging = false;
  if (!scenario.late) {
    run(data.stage); actions[scenario.control](); await tick();
    assert.ok(calls.some(call => call[0] === expected[scenario.control]), 'ordinary action resumes after cleanup');
    if (scenario.control === 'clear') {
      const table = calls.find(call => call[0] === 'set_preview_binds')[1];
      assert.equal(table.characters[owner], 'Ctrl+Alt+9', 'normal write uses restored live table, not synthetic binds');
    }
  }
}
async function fittingsDetailRegression() {
  const scenario = data.regression;
  const pendingState = deferred();
  bridgeReply = method => { assert.equal(method, 'fittings_state'); return pendingState.promise; };
  WM.route('fittings'); await tick(); calls.length = 0; staging = true;
  const step = async expression => { if (expression) run(expression); await tick(); };
  const toggle = name => document.querySelectorAll('#fittings-list .fit-row-toggle')
    .find(el => el.querySelector('.fit-name').textContent === name);
  const verify = () => { if (data.verify) run(data.verify); };
  // Start exactly where the preceding Alliance capture leaves the real page.
  await step(data.fixture); await step(data.reset);
  await step(data.previous_prepare); await step(data.previous_stage);
  assert.equal(toggle('Merlin - Fleet Doctrine').getAttribute('aria-expanded'), 'true');
  for (let iteration = 0; iteration < 2; iteration++) {
    WM.route('fittings'); await tick();
    await step(data.prepare); await step(data.fixture); await step(data.reset);
    await step(data.fittings_prepare);
    const waiting = deferred();
    const nativePromise = window.Promise;
    if (['unresolved', 'late-reset', 'late-reinject'].includes(scenario)) {
      // Delay the fixture read's delivery, not the renderer or its handlers.
      window.Promise = {resolve: value => waiting.promise.then(() => value)};
    }
    run(data.stage); window.Promise = nativePromise;
    if (scenario === 'late-reset') run(data.reset);
    if (scenario === 'late-reinject') run(data.fixture);
    if (scenario !== 'unresolved') waiting.resolve();
    await tick();
    if (scenario === 'late-state') {
      pendingState.resolve({available: false, rows: [], collections: [], characters: [], filters: {}});
      await tick();
    }
    const row = toggle('Rifter - Solo PvP').closest('.fit-row');
    if (scenario === 'unresolved') assert.match(row.querySelector('.fit-detail').textContent, /Loading/);
    else if (['late-reset', 'late-reinject'].includes(scenario)) {
      assert.equal(toggle('Rifter - Solo PvP').getAttribute('aria-expanded'), 'false');
      assert.equal(row.querySelector('.fit-detail'), null, 'late detail must not undo a reset');
    } else {
      assert.equal(toggle('Rifter - Solo PvP').getAttribute('aria-expanded'), 'true');
      assert.equal(document.querySelectorAll('.fit-row.open').length, 1);
      const texts = selector => row.querySelectorAll(selector).map(el => el.textContent);
      assert.deepEqual(texts('.fit-rack-name'), ['High power', 'Medium power', 'Low power']);
      assert.deepEqual(texts('.fit-item-name'), ['150mm Light AutoCannon II', '1MN Afterburner II', 'Gyrostabilizer II']);
      assert.deepEqual(texts('.fit-alias-row'), ['Rifter - Solo PvP', 'Rifter Tackle Fit']);
      assert.deepEqual(texts('.fit-presence-name'), ['Aria Voss', 'Bex Talon']);
      verify();
      assert.ok(scrolls.at(-1)?.element === toggle('Rifter - Solo PvP'),
        'frame the newly rendered detail row, not the stale toggle from before its reply');
      assert.equal(scrolls.at(-1).options.block, 'start');
      assert.equal(scrolls.at(-1).options.behavior, 'instant');
    }
    if (scenario === 'collapsed') toggle('Rifter - Solo PvP').click();
    else if (scenario === 'wrong-target') { toggle('Merlin - Fleet Doctrine').click(); await tick(); }
    else if (scenario.startsWith('missing-')) {
      const selector = {'missing-detail': '.fit-detail', 'missing-rack': '.fit-rack',
        'missing-alias': '.fit-alias-row', 'missing-presence': '.fit-presence-row'}[scenario];
      const missing = row.querySelector(selector); missing.parentNode.removeChild(missing);
    }
    if (['settled', 'late-state'].includes(scenario)) verify();
    else assert.throws(verify, /Screenshot content did not settle: fittings-detail/);
    assert.equal(calls.length, 0, 'all fixture actions and delayed replies remain local');
  }
  console.log('PASS screenshot fittings-detail ' + scenario);
}
(async () => {
  if (moduleName === 'fittings') { await fittingsDetailRegression(); return; }
  WM.route(crop ? 'settings' : moduleName);
  if (crop) WM.section('previews');
  await tick(); calls.length = 0;
  if (data.regression) {
    await cropRegression();
    console.log('PASS screenshot regression ' + JSON.stringify(data.regression));
    return;
  }
  staging = true;
  // Exercise the exact expressions emitted by the Python shooter twice: a
  // screenshot must not inherit the previous capture's review or disclosure.
  for (let iteration = 0; iteration < 2; iteration++) {
    run(data.prepare); await tick();
    run(data.stage); await tick();
    run(data.verify);
    if (crop) {
      // New live host revisions cannot paint over the isolated fixture.
      window.onPreviewCrops({revision: 900 + iteration, definitions: {}, operations: {}, statuses: {}});
      run(data.verify);
      document.querySelector('[data-preview-detail-control="crop-select"]').click();
    } else if (moduleName === 'uisetup') {
      for (const id of ['us-copy', 'us-save', 'setup-create', 'setup-paste', 'setup-file']) WM.el(id).click();
      // The merged catalog source must obey the same read-only seam. Dispatch
      // directly too: hiding/disabling a button is not a bridge safety boundary.
      for (const id of ['setup-catalog-open', 'setup-catalog-retry', 'setup-catalog-use']) {
        WM.el(id).dispatchEvent({type: 'click'});
      }
      assert.equal(WM.el('setup-catalog').hidden, true);
      assert.equal(WM.el('setup-catalog-origin').textContent, '');
    } else {
      WM.el('fm-save').click(); WM.el('fm-copy').click();
    }
    // Missing/unstaged content must fail before capture, not look complete.
    if (crop) document.querySelector('[data-preview-configure][aria-expanded="true"]').setAttribute('aria-expanded', 'false');
    else if (data.key === 'profiles-formations') WM.el('fm-name').value = '';
    else WM.el(data.key === 'profiles-formations-import' ? 'fm-import-work'
      : data.key === 'profiles-setup-share' ? 'us-summary' : 'setup-summary').hidden = true;
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
    run(data.cleanup); await tick();
    assert.equal(calls.length, 0, 'including cleanup');
    if (moduleName === 'uisetup') {
      assert.equal(WM.el('setup-text').value, '');
      assert.equal(WM.el('setup-summary').hidden, true);
    }
    if (crop) assert.equal(document.querySelector('[data-preview-configure][aria-expanded="true"]'), null);
  }
  // Leaving before the promise microtasks settle must also be harmless.
  run(data.prepare); run(data.cleanup); await tick();
  assert.equal(calls.length, 0);
  if (moduleName === 'uisetup' && data.key.endsWith('import')) {
    run(data.prepare); await tick(); run(data.stage); run(data.cleanup); await tick();
    assert.equal(calls.length, 0, 'late synthetic review must not discard a real backend offer');
  }
  staging = false;
  if (moduleName === 'formations') WM.openFormations([{path: 'live-account', name: 'Live'}], 'live-account');
  else if (moduleName === 'uisetup') {
    WM.openUiSetup({mode: 'export', context: {root: 'live', server: 'tq', profile: 'live-base'}});
    assert.ok(calls.length, 'ordinary export reads resume after cleanup');
    WM.openUiSetup({mode: 'import', context: {root: 'live', server: 'tq', profile: 'live-base'}});
    const beforeCatalogRead = calls.length;
    WM.el('setup-catalog-open').click();
    assert.ok(calls.slice(beforeCatalogRead).some(call => call[0] === 'eve_settings_setup_catalog'), 'ordinary catalog reads resume after cleanup');
  } else WM.section('previews');
  assert.ok(calls.length, 'ordinary reads resume after cleanup');
  console.log('PASS screenshot ' + data.key);
})().catch(error => { console.error(error); process.exitCode = 1; });
