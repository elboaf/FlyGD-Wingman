/* Executable Fittings regressions: real app.js/fittings.js, deferred bridge
 * replies and a stateful DOM subset. No browser/layout/focus claims. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const web = path.join(__dirname, '..', 'wingman', 'web');

class EventTarget {
  constructor() { this.listeners = {}; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  dispatchEvent(event) {
    event.target ||= this;
    for (const fn of this.listeners[event.type] || []) fn.call(this, event);
  }
}

class Element extends EventTarget {
  constructor(tag = 'div') {
    super();
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.className = '';
    this.value = '';
    this.hidden = false;
    this.disabled = false;
    this.open = false;
    this.text = '';
    const properties = new Map();
    this.style = {
      setProperty: (name, value) => properties.set(name, value),
      getPropertyValue: name => properties.get(name) || '',
      removeProperty: name => properties.delete(name)
    };
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      toggle: (name, force) => {
        const on = force === undefined ? !this.classList.contains(name) : force;
        const names = this.className.split(/\s+/).filter(n => n && n !== name);
        if (on) names.push(name);
        this.className = names.join(' ');
        return on;
      },
      add: name => this.classList.toggle(name, true),
      remove: name => this.classList.toggle(name, false)
    };
  }
  set value(value) {
    if (!this.ownerDocument?.nativeTextValues) { this._value = value; return; }
    const text = String(value);
    this._value = this.tagName === 'TEXTAREA' ? text.replace(/\r\n?/g, '\n')
      : this.tagName === 'INPUT' && this.type === 'text' ? text.replace(/[\r\n]/g, '') : text;
  }
  get value() { return this._value; }
  set disabled(value) {
    this._disabled = !!value;
    // Chromium blurs a focused control as soon as it becomes disabled.
    if (this._disabled && this.ownerDocument?.activeElement === this) this.blur();
  }
  get disabled() { return this._disabled; }
  set textContent(value) {
    this.text = String(value);
    this.children.forEach(child => { child.parentNode = null; });
    this.children = [];
    if (this.onChildrenCleared) this.onChildrenCleared();
  }
  get textContent() { return this.text + this.children.map(c => c.textContent).join(''); }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  contains(node) { return this === node || this.children.some(c => c.contains(node)); }
  querySelectorAll(selector) {
    const found = [];
    const matches = node => selector.split(',').some(part => {
      if (part.includes(':disabled') && node.disabled) return false;
      if (part.includes('[hidden]') && node.hidden) return false;
      part = part.replace(/:not\([^)]*\)/g, '').trim();
      if (part === '[tabindex="0"]') return node.getAttribute('tabindex') === '0';
      if (part.startsWith('.')) return node.classList.contains(part.slice(1));
      return node.tagName === part.toUpperCase();
    });
    const walk = node => node.children.forEach(child => {
      if (matches(child)) found.push(child);
      walk(child);
    });
    walk(this);
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) {
    for (let node = this; node; node = node.parentNode) {
      if (selector.startsWith('.') ? node.classList.contains(selector.slice(1))
        : node.tagName === selector.toUpperCase()) return node;
    }
    return null;
  }
  getBoundingClientRect() {
    const height = this.measuredHeight ?? 36;
    return {top: 0, bottom: height, left: 0, right: 120, width: 120, height};
  }
  getClientRects() {
    for (let node = this; node; node = node.parentNode) {
      if (node.hidden || (node.parentNode?.tagName === 'DETAILS'
          && !node.parentNode.open && node.tagName !== 'SUMMARY')) return [];
    }
    return [{}];
  }
  focus(options) {
    this.lastFocusOptions = options;
    if (!this.disabled && this.getClientRects().length) this.ownerDocument.activeElement = this;
  }
  blur() {
    if (this.ownerDocument.activeElement === this) this.ownerDocument.activeElement = this.ownerDocument.body;
  }
  setSelectionRange(start, end, direction) {
    this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction;
  }
  click() { if (!this.disabled) this.dispatchEvent({ type: 'click' }); }
}

async function flush() { await new Promise(resolve => setImmediate(resolve)); }
async function settle(call, payload) {
  assert.ok(call, 'expected a pending bridge call');
  call.resolve(payload);
  await flush();
}
function input(node, value) { node.value = value; node.dispatchEvent({ type: 'input' }); }
function tick(node) { node.checked = !node.checked; node.dispatchEvent({ type: 'change' }); }

async function page(options = {}) {
  const nodes = new Map();
  const document = new EventTarget();
  document.nativeTextValues = !!options.nativeTextValues;
  document.body = Object.assign(new Element('body'), { ownerDocument: document });
  document.activeElement = document.body;
  // Actual static IDs, plus a tree search for controls created by fittings.js.
  const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
  for (const match of html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const node = new Element(match[1]);
    node.ownerDocument = document;
    node.id = match[2];
    node.className = match[0].match(/\bclass="([^"]*)"/)?.[1] || '';
    node.textContent = html.slice(match.index + match[0].length).match(/^[^<]*/)[0].trim();
    node.hidden = /\bhidden\b/.test(match[0]);
    node.disabled = /\bdisabled\b/.test(match[0]);
    nodes.set(node.id, node);
  }
  // The clipboard panel is static, unlike rebuilt rows. Keep its real parent
  // relationships for Escape/focus ownership without fabricating controls.
  const panel = nodes.get('fittings-import-panel');
  if (panel) {
    for (const id of ['fittings-import-text', 'fittings-import-read', 'fittings-import-review',
      'fittings-import-add', 'fittings-import-close', 'fittings-import-show',
      'fittings-import-status', 'fittings-import-candidate']) panel.appendChild(nodes.get(id));
  }
  const copyDialog = nodes.get('fittings-copy-dialog');
  nodes.get('fittings-copy-overlay').appendChild(copyDialog);
  for (const id of ['fittings-copy-title', 'fittings-copy-summary', 'fittings-copy-limit-summary',
    'fittings-copy-body', 'fittings-copy-status', 'fittings-copy-cancel-note',
    'fittings-copy-close', 'fittings-copy-review', 'fittings-copy-start', 'fittings-copy-cancel']) {
    if (nodes.has(id)) copyDialog.appendChild(nodes.get(id));
  }
  const findId = (node, id) => node.id === id ? node
    : node.children.map(child => findId(child, id)).find(Boolean);
  document.getElementById = id => nodes.get(id)
    || [...nodes.values()].map(node => findId(node, id)).find(Boolean) || null;
  document.createElement = tag => Object.assign(new Element(tag), { ownerDocument: document });
  document.querySelectorAll = () => [];
  document.querySelector = () => null;
  document.contains = node => [...nodes.values()].some(root => root.contains(node));
  const calls = [];
  const errors = [];
  const confirmations = [];
  const api = {};
  for (const method of ['fittings_state', 'fittings_detail', 'fittings_update_metadata',
    'fittings_set_membership', 'fittings_set_supersession', 'fittings_refresh', 'fittings_delete_entry',
    'fittings_preflight_copy', 'fittings_start_copy', 'fittings_cancel_copy',
    'fittings_review_eft', 'fittings_import_eft', 'fittings_export_eft', 'fittings_locate_entry']) {
    api[method] = (...args) => new Promise((resolve, reject) => {
      calls.push({ method, args, resolve, reject });
    });
  }
  api.list_rows = api.get_settings = api.update_status = () => null;
  const window = new EventTarget();
  window.pywebview = { api };
  window.getComputedStyle = () => ({ visibility: 'visible' });
  const observers = [];
  window.ResizeObserver = class {
    constructor(callback) { this.callback = callback; this.targets = []; observers.push(this); }
    observe(node) { this.targets.push(node); }
    disconnect() { this.targets = []; }
  };
  const timers = new Map();
  let timerId = 0;
  const reads = [], writes = [];
  const clipboard = {};
  for (const [method, records] of [['readText', reads], ['writeText', writes]]) {
    clipboard[method] = (...args) => {
      if (options[method] === 'throw') throw new Error('Clipboard denied synchronously');
      return new Promise((resolve, reject) => records.push({ args, resolve, reject }));
    };
  }
  const navigator = { clipboard: options.clipboard === false ? undefined : clipboard };
  window.navigator = navigator;
  const context = vm.createContext({
    window, document, navigator,
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
    clearTimeout: id => timers.delete(id),
    CustomEvent: class { constructor(type, options = {}) {
      this.type = type; this.detail = options.detail;
    } },
    console: { warn: (...args) => errors.push(args), error: (...args) => errors.push(args) }
  });
  for (const file of ['app.js', 'fittings.js']) {
    vm.runInContext(fs.readFileSync(path.join(web, file), 'utf8'), context, { filename: file });
  }
  window.WM.confirm = (...args) => new Promise(resolve => confirmations.push({ args, resolve }));
  await flush();
  return {
    el: id => document.getElementById(id),
    focused: () => document.activeElement,
    calls: method => calls.filter(call => !method || call.method === method),
    last: method => calls.filter(call => call.method === method).at(-1),
    route: async name => { window.WM.route(name); await flush(); },
    changed: async payload => { window.onFittingsChanged(payload); await flush(); },
    progress: async payload => { window.onFittingsProgress(payload); await flush(); },
    screenshot: async payload => { window.onFittingsScreenshotState(payload); await flush(); },
    timers: async () => { for (const fn of timers.values()) fn(); timers.clear(); await flush(); },
    key: (key, shiftKey = false) => document.dispatchEvent({type: 'keydown', key, shiftKey, target: document.activeElement,
      preventDefault() { this.defaultPrevented = true; }}),
    focusEvent: node => { node.focus(); document.dispatchEvent({type: 'focusin', target: node}); },
    resize: () => window.dispatchEvent({type: 'resize'}),
    resizeObserved: node => observers.forEach(observer => {
      if (observer.targets.includes(node)) observer.callback([{target: node}]);
    }),
    throwBridge: method => { api[method] = () => { throw new Error('injected synchronous bridge refusal'); }; },
    reads, writes, confirmations, errors
  };
}

function state(ids = ['fit-1']) {
  return {
    available: true, warnings: [], refreshing: false,
    filters: { collection_id: 'all', search: '', ship_type_id: null },
    collections: [{ id: 'all', name: 'All fittings', count: ids.length },
                  { id: 'doctrine', name: 'Doctrine', count: 1 }],
    characters: [{ character_id: 42, character_name: 'Pilot', status: 'enabled',
                   fetched_utc: '2026-09-07T12:00:00Z', stale: false }],
    ships: [], page: 1, page_size: 100, total: ids.length,
    rows: ids.map(id => ({ id, name: 'Sabre tackle', ship_type_id: 22456,
      ship_name: 'Sabre', presence_count: 0, collection_ids: [],
      deployable: true, superseded_by: null }))
  };
}
function detail(id = 'fit-1', name = 'Sabre tackle', description = 'Saved description') {
  return { id, name, description, ship_type_id: 22456, items: [], aliases: [],
           presences: [], collection_ids: [], superseded_by: null };
}
function button(root, label) {
  const node = root.querySelectorAll('button').find(node => node.textContent === label);
  assert.ok(node, 'missing button: ' + label);
  return node;
}
function metadata(p) { return p.el('fittings-list').querySelector('.fit-metadata'); }
function metadataDisclosure(p) { return p.el('fittings-list').querySelector('.fit-metadata-disclosure'); }
function setMetadataOpen(p, open) {
  const disclosure = metadataDisclosure(p);
  if (disclosure) { disclosure.open = open; disclosure.dispatchEvent({ type: 'toggle' }); }
}
async function editor(openMetadata = true) {
  const p = await page();
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  await settle(p.last('fittings_detail'), detail());
  if (openMetadata) setMetadataOpen(p, true);
  return p;
}
async function repaint(p, payload = state(), value = detail()) {
  await p.changed({ reason: 'collection_membership', entry_id: 'fit-1' });
  await settle(p.last('fittings_state'), payload);
  await settle(p.last('fittings_detail'), value);
}
function assertDraft(p, name, description) {
  assert.equal(p.el('fit-name-fit-1').value, name);
  assert.equal(p.el('fit-desc-fit-1').value, description);
  assert.match(metadata(p).textContent, /Unsaved changes/);
  assert.equal(metadataDisclosure(p)?.open, true, 'a draft stays exposed after rerender');
}

async function nativeTextEditor(name, description) {
  const p = await page({nativeTextValues: true});
  await p.route('fittings');
  const payload = state(); payload.rows[0].name = name;
  await settle(p.last('fittings_state'), payload);
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  await settle(p.last('fittings_detail'), detail('fit-1', name, description));
  setMetadataOpen(p, true);
  return p;
}

for (const [label, name, description] of [
  ['CRLF description', 'Saved name', 'First\r\nSecond'],
  ['line break in name', 'Saved\nname', 'Description']
]) {
  for (const field of ['name', 'desc']) {
    test('native text values: edit/revert ' + field + ' with ' + label + ' is clean', async () => {
      const p = await nativeTextEditor(name, description);
      const control = p.el('fit-' + field + '-fit-1');
      const initial = control.value;
      input(control, 'Temporary');
      input(control, initial);
      assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
      assert.equal(button(metadata(p), 'Save').disabled, true);
      assert.equal(p.calls('fittings_update_metadata').length, 0);
    });
  }
  for (const phase of ['refresh', 'refused', 'ack-newer']) {
    test('native text values: committed mapping survives ' + phase + ' for ' + label, async () => {
      const p = await nativeTextEditor(name, description);
      const field = label === 'CRLF description' ? 'desc' : 'name';
      const other = field === 'desc' ? 'name' : 'desc';
      const originalDisplay = p.el('fit-' + field + '-fit-1').value;
      if (phase === 'ack-newer') {
        input(p.el('fit-' + other + '-fit-1'), 'Other changed');
        button(metadata(p), 'Save').click(); await flush();
        input(p.el('fit-' + field + '-fit-1'), 'Temporary');
        await settle(p.last('fittings_update_metadata'), true);
      } else {
        input(p.el('fit-' + field + '-fit-1'), 'Temporary');
        if (phase === 'refused') {
          button(metadata(p), 'Save').click(); await flush();
          await settle(p.last('fittings_update_metadata'), false);
        } else {
          const payload = state(); payload.rows[0].name = name;
          await repaint(p, payload, detail('fit-1', name, description));
        }
      }
      input(p.el('fit-' + field + '-fit-1'), originalDisplay);
      assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
      assert.equal(button(metadata(p), 'Save').disabled, true);
      if (phase === 'refused') assert.match(metadata(p).textContent, /save not confirmed/);
      input(p.el('fit-' + other + '-fit-1'), 'Another edit');
      button(metadata(p), 'Save').click(); await flush();
      assert.deepEqual(p.last('fittings_update_metadata').args,
        ['fit-1', other === 'name' ? 'Another edit' : name,
          other === 'desc' ? 'Another edit' : description]);
    });
  }
  test('native text values: changing the other field preserves exact ' + label, async () => {
    const p = await nativeTextEditor(name, description);
    const field = label === 'CRLF description' ? 'name' : 'desc';
    input(p.el('fit-' + field + '-fit-1'), 'Changed');
    button(metadata(p), 'Save').click();
    await flush();
    assert.deepEqual(p.last('fittings_update_metadata').args,
      ['fit-1', field === 'name' ? 'Changed' : name, field === 'desc' ? 'Changed' : description]);
    await settle(p.last('fittings_update_metadata'), true);
    assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
    assert.equal(button(metadata(p), 'Save').disabled, true);
  });
}

function selectionBoxes(p) {
  return p.el('fittings-list').querySelectorAll('.fit-select').map(label => label.querySelector('input'));
}
function selectedRows(p) { return selectionBoxes(p).filter(box => box.checked).map(box => box.value); }

for (const [name, names, expected] of [
  ['current title only', ['Sabre tackle', 'Sabre tackle'], []],
  ['one alternative', ['Fleet tackle'], ['Fleet tackle']],
  ['exact title match only', ['Sabre tackle', 'sabre tackle', 'Other'], ['sabre tackle', 'Other']],
  ['no aliases', [], []]
]) {
  test('alias presentation keeps provenance and filters the visible title: ' + name, async () => {
    const p = await page(); await p.route('fittings');
    await settle(p.last('fittings_state'), state());
    p.el('fittings-list').querySelector('.fit-row-toggle').click(); await flush();
    const payload = detail('fit-1', 'Independent detail title');
    payload.aliases = names.map((value, index) => ({name: value, description: 'Source ' + index}));
    const unchanged = JSON.stringify(payload);
    await settle(p.last('fittings_detail'), payload);
    const aliases = () => p.el('fittings-list').querySelectorAll('.fit-alias-row').map(row => row.textContent);
    assert.deepEqual(aliases(), expected);
    assert.equal(!!p.el('fittings-list').querySelector('.fit-aliases'), expected.length > 0);
    setMetadataOpen(p, true);
    input(p.el('fit-name-fit-1'), 'Fleet tackle');
    assert.deepEqual(aliases(), expected, 'an unsaved metadata draft is not the displayed title');
    assert.equal(JSON.stringify(payload), unchanged, 'presentation must not edit alias provenance');
    assert.equal(p.calls().length, 2, 'rendering and drafting must not issue writes');
  });
}

test('selection names distinguish identical fit and hull names by current page row without changing selection', async () => {
  const p = await page(); await p.route('fittings');
  const payload = state(['fit-1', 'fit-2', 'fit-3']);
  payload.rows[2].ship_name = ''; payload.rows[2].ship_type_id = 999;
  await settle(p.last('fittings_state'), payload);
  function names() { return selectionBoxes(p).map(box => box.getAttribute('aria-label')); }
  assert.deepEqual(names(), [
    'Select Sabre tackle — Sabre, row 1 on this page',
    'Select Sabre tackle — Sabre, row 2 on this page',
    'Select Sabre tackle — Type 999, row 3 on this page'
  ]);
  tick(selectionBoxes(p)[1]);
  assert.deepEqual(selectedRows(p), ['fit-2']);
  assert.equal(p.calls().length, 1, 'selection remains local');
  await p.changed({reason: 'metadata', entry_id: 'fit-2'});
  const refreshed = state(['fit-2', 'fit-1']);
  refreshed.total = 3; refreshed.page_size = 2;
  refreshed.rows[0].name = 'Renamed & <fit>';
  await settle(p.last('fittings_state'), refreshed);
  assert.deepEqual(names(), [
    'Select Renamed & <fit> — Sabre, row 1 on this page',
    'Select Sabre tackle — Sabre, row 2 on this page'
  ]);
  assert.deepEqual(selectedRows(p), ['fit-2'], 'position is not the selection key');
  const rows = p.el('fittings-list').querySelectorAll('.fit-row');
  selectionBoxes(p).forEach((box, index) => {
    assert.ok(box.getAttribute('aria-label').includes(rows[index].querySelector('.fit-name').textContent));
    assert.ok(box.getAttribute('aria-label').includes(rows[index].querySelector('.fit-ship').textContent));
    assert.ok(!box.getAttribute('aria-label').includes(box.value), 'opaque ID is not the user-facing identity');
  });
  p.el('fittings-page-next').click(); await flush();
  const nextPage = state(['fit-4']); nextPage.page = 2;
  await settle(p.last('fittings_state'), nextPage);
  assert.deepEqual(names(), ['Select Sabre tackle — Sabre, row 1 on this page']);
  assert.deepEqual(selectedRows(p), [], 'page changes still prune selection');
});

test('Superseded by names the current select and retains the existing change endpoint', async () => {
  const p = await page(); await p.route('fittings');
  await settle(p.last('fittings_state'), state(['fit-1', 'fit-2']));
  async function expand(index, id) {
    p.el('fittings-list').querySelectorAll('.fit-row-toggle')[index].click(); await flush();
    await settle(p.last('fittings_detail'), detail(id));
    const group = p.el('fittings-list').querySelector('.fit-supersession');
    const select = group.querySelector('select');
    const reference = select.getAttribute('aria-labelledby');
    assert.ok(reference, 'select must reference its visible label');
    const label = p.el(reference);
    assert.ok(label && group.contains(label), 'association resolves inside the current detail');
    assert.equal(label.textContent, 'Superseded by');
    return select;
  }
  const first = await expand(0, 'fit-1');
  first.value = 'fit-2'; first.dispatchEvent({type: 'change'}); await flush();
  assert.deepEqual(p.last('fittings_set_supersession').args, ['fit-1', 'fit-2']);
  await settle(p.last('fittings_set_supersession'), true);
  const second = await expand(1, 'fit-2');
  assert.notEqual(second.getAttribute('aria-labelledby'), first.getAttribute('aria-labelledby'));
  second.value = ''; second.dispatchEvent({type: 'change'}); await flush();
  assert.deepEqual(p.last('fittings_set_supersession').args, ['fit-2', null]);
  await settle(p.last('fittings_set_supersession'), true);
  assert.deepEqual(p.errors, []);
});

test('page selection helpers stay inert before hydration and for empty results', async () => {
  const p = await page();
  const select = p.el('fittings-select-page'), clear = p.el('fittings-clear-selection');
  assert.ok(select && clear, 'the bounded page selection helpers must exist');
  await p.route('fittings');
  for (const payload of [null, state([])]) {
    if (payload) await settle(p.last('fittings_state'), payload);
    const before = p.calls().length;
    for (const helper of [select, clear]) {
      assert.equal(helper.disabled, true);
      helper.dispatchEvent({type: 'click'}); // guards must survive forced dispatch
    }
    assert.equal(p.calls().length, before);
    assert.equal(p.el('fittings-copy-selected').disabled, true);
  }
});

test('Select page uses only rendered filtered rows; deselection and Clear stay local until explicit review', async () => {
  const p = await page(); await p.route('fittings');
  const payload = state(['fit-2', 'fit-4']);
  payload.total = 50; payload.page_size = 2;
  payload.filters.search = 'tackle';
  await settle(p.last('fittings_state'), payload);
  const select = p.el('fittings-select-page'), clear = p.el('fittings-clear-selection');
  assert.ok(select && clear, 'the bounded page selection helpers must exist');
  const before = p.calls().length;
  assert.equal(clear.disabled, true);
  select.click();
  assert.deepEqual(selectedRows(p), ['fit-2', 'fit-4']);
  assert.equal(p.el('fittings-copy-selected').textContent, 'Copy selected (2)');
  tick(selectionBoxes(p)[0]);
  assert.deepEqual(selectedRows(p), ['fit-4']);
  assert.equal(p.el('fittings-copy-selected').textContent, 'Copy selected (1)');
  clear.click();
  assert.deepEqual(selectedRows(p), []);
  assert.equal(clear.disabled, true);
  assert.equal(p.el('fittings-copy-selected').disabled, true);
  select.click();
  assert.equal(p.calls().length, before, 'selection must neither fetch nor preflight');
  p.el('fittings-copy-selected').click();
  tick(p.el('fittings-copy-body').querySelector('input'));
  p.el('fittings-copy-review').click(); await flush();
  assert.deepEqual(Array.from(p.last('fittings_preflight_copy').args[0]), ['fit-2', 'fit-4']);
});

test('selection helpers preserve metadata node, draft, focus, text selection and scroll identity', async () => {
  const p = await editor();
  const select = p.el('fittings-select-page'), clear = p.el('fittings-clear-selection');
  assert.ok(select && clear, 'the bounded page selection helpers must exist');
  const host = p.el('fittings-list'), disclosure = metadataDisclosure(p);
  const name = p.el('fit-name-fit-1'), description = p.el('fit-desc-fit-1');
  input(name, 'Unsubmitted name'); input(description, 'Unsubmitted description');
  name.focus(); name.setSelectionRange(2, 7, 'backward'); host.scrollTop = 93;
  const row = host.children[0], before = p.calls().length;
  for (const helper of [select, clear]) {
    helper.click();
    assert.equal(host.children[0] === row, true, 'no list rebuild for a checkbox change');
    assert.equal(metadataDisclosure(p) === disclosure, true);
    assert.equal(disclosure.open, true);
    assert.equal(p.el('fit-name-fit-1') === name, true);
    assert.equal(p.el('fit-desc-fit-1') === description, true);
    assert.equal(p.focused() === name, true);
    assert.deepEqual([name.selectionStart, name.selectionEnd, name.selectionDirection], [2, 7, 'backward']);
    assert.equal(host.scrollTop, 93);
    assertDraft(p, 'Unsubmitted name', 'Unsubmitted description');
  }
  assert.equal(p.calls().length, before);
});

test('focused Clear selection continues at Select page without replacing drafts or scrolling', async () => {
  const p = await editor();
  const select = p.el('fittings-select-page'), clear = p.el('fittings-clear-selection');
  const host = p.el('fittings-list'), disclosure = metadataDisclosure(p);
  const name = p.el('fit-name-fit-1');
  input(name, 'Unsubmitted name');
  select.click(); clear.focus(); host.scrollTop = 93;
  const before = p.calls().length;
  clear.click();
  assert.equal(clear.disabled, true);
  assert.equal(p.focused() === select, true, 'clearing must not strand keyboard focus on the document body');
  assert.deepEqual(selectedRows(p), []);
  assert.equal(p.el('fit-name-fit-1') === name, true);
  assert.equal(metadataDisclosure(p) === disclosure, true);
  assert.equal(disclosure.open, true);
  assert.equal(name.value, 'Unsubmitted name');
  assert.equal(host.scrollTop, 93);
  assert.equal(p.calls().length, before);
});

test('selection helpers follow existing read pruning, page/filter clears and stale-read fencing', async () => {
  const p = await page(); await p.route('fittings');
  const first = state(['fit-1', 'fit-2']); first.total = 4; first.page_size = 2;
  await settle(p.last('fittings_state'), first);
  const select = p.el('fittings-select-page');
  assert.ok(select, 'the bounded page selection helper must exist');
  await p.changed({reason: 'refresh'});
  const stale = p.last('fittings_state');
  select.click();
  await p.changed({reason: 'refresh'});
  await settle(p.last('fittings_state'), state(['fit-2', 'fit-3']));
  assert.deepEqual(selectedRows(p), ['fit-2'], 'retain only the intersection, never select new rows');
  await settle(stale, first);
  assert.deepEqual(selectionBoxes(p).map(box => box.value), ['fit-2', 'fit-3']);
  p.el('fittings-page-next').dispatchEvent({type: 'click'}); await flush();
  assert.deepEqual(selectedRows(p), [], 'clear current checkbox paint while a page read is pending');
  select.click(); // still acts on STATE.rows, not the not-yet-delivered next page
  await settle(p.last('fittings_state'), state(['fit-4']));
  assert.deepEqual(selectedRows(p), []);
  select.click();
  input(p.el('fittings-search'), 'new filter');
  assert.deepEqual(selectedRows(p), []);
  await p.timers();
  await settle(p.last('fittings_state'), state(['fit-5']));
  assert.deepEqual(selectedRows(p), []);
  select.click(); await p.route('main'); await p.route('fittings');
  await settle(p.last('fittings_state'), state(['fit-5']));
  assert.deepEqual(selectedRows(p), [], 'route cleanup is still unconditional');
});

test('copy progress disables and handler-guards selection helpers, then completion releases them', async () => {
  const p = await editor();
  await repaint(p, state(['fit-1', 'fit-2']));
  const select = p.el('fittings-select-page'), clear = p.el('fittings-clear-selection');
  assert.ok(select && clear, 'the bounded page selection helpers must exist');
  await beginCopy(p);
  const before = p.calls().length;
  for (const helper of [select, clear]) {
    assert.equal(helper.disabled, true);
    helper.dispatchEvent({type: 'click'});
    assert.deepEqual(selectedRows(p), ['fit-1']);
    assert.equal(p.el('fittings-copy-selected').textContent, 'Copy selected (1)');
  }
  assert.equal(p.calls().length, before);
  await complete(p, result(['success']));
  assert.equal(select.disabled, false);
  assert.equal(clear.disabled, true);
  assert.deepEqual(selectedRows(p), []);
});

test('Delete fitting exposes its presence restriction beside the action and removes it when eligible', async () => {
  const p = await editor(false);
  const present = detail();
  present.presences = [{ character_id: 42, character_name: 'Pilot',
    source_name: 'Sabre tackle', first_seen_utc: '2026-09-01T12:00:00Z' }];
  await repaint(p, state(), present);
  const remove = button(p.el('fittings-list'), 'Delete fitting');
  assert.equal(remove.disabled, true);
  const reason = remove.parentNode.querySelector('.hint');
  assert.ok(reason, 'a tooltip alone hides the reason for a disabled action');
  assert.equal(reason.textContent, remove.title, 'use the existing restriction authority');
  assert.ok(reason.getClientRects().length, 'the reason is outside the closed metadata editor');
  remove.click();
  assert.equal(p.confirmations.length, 0);
  assert.equal(p.calls('fittings_delete_entry').length, 0);
  await repaint(p);
  const enabled = button(p.el('fittings-list'), 'Delete fitting');
  assert.equal(enabled.disabled, false);
  assert.equal(enabled.parentNode.querySelector('.hint'), null, 'no stale restriction after presence clears');
});

test('metadata and immediate controls expose distinct commit scopes without changing their writes', async () => {
  const p = await editor();
  await repaint(p, state(['fit-1', 'fit-2']));
  const box = p.el('fittings-list').querySelector('.fit-detail');
  const save = button(metadata(p), 'Save');
  const saveScopeId = save.getAttribute('aria-describedby');
  assert.ok(saveScopeId, 'Save explains which fields it commits');
  assert.match(p.el(saveScopeId).textContent, /only.*name.*description/i);
  const membership = box.querySelector('.fit-collections').querySelector('input');
  const supersession = box.querySelector('.fit-supersession').querySelector('select');
  const immediateScopeId = membership.getAttribute('aria-describedby');
  assert.ok(immediateScopeId, 'immediate changes have their own visible scope');
  assert.equal(supersession.getAttribute('aria-describedby'), immediateScopeId);
  assert.notEqual(immediateScopeId, saveScopeId);
  const immediateScope = p.el(immediateScopeId);
  assert.match(immediateScope.textContent, /Collections.*Superseded by.*immediately/i);
  assert.equal(metadataDisclosure(p).contains(immediateScope), false);
  input(p.el('fit-name-fit-1'), 'Keep this draft');
  tick(membership);
  supersession.value = 'fit-2';
  supersession.dispatchEvent({ type: 'change' });
  await flush();
  assert.deepEqual(Array.from(p.last('fittings_set_membership').args), ['fit-1', 'doctrine', true]);
  assert.deepEqual(Array.from(p.last('fittings_set_supersession').args), ['fit-1', 'fit-2']);
  assert.equal(p.calls('fittings_update_metadata').length, 0);
  save.click(); await flush();
  assert.deepEqual(Array.from(p.last('fittings_update_metadata').args), ['fit-1', 'Keep this draft', 'Saved description']);
  setMetadataOpen(p, false);
  assert.ok(immediateScope.getClientRects().length, 'closing metadata never hides immediate-change guidance');
});

test('metadata is read-first with native disclosure state retained through unrelated renders', async () => {
  const p = await editor(false);
  const disclosure = metadataDisclosure(p);
  assert.ok(disclosure, 'metadata needs a separate disclosure, not an always-open form');
  assert.equal(disclosure.tagName, 'DETAILS');
  assert.equal(disclosure.open, false);
  assert.match(disclosure.querySelector('summary').textContent, /Edit metadata/);
  assert.ok(disclosure.contains(metadata(p)));
  assert.equal(p.el('fit-name-fit-1').getClientRects().length, 0);
  setMetadataOpen(p, true);
  await repaint(p);
  assert.equal(metadataDisclosure(p).open, true, 'reading a refresh does not close an opened editor');
  setMetadataOpen(p, false);
  await repaint(p);
  assert.equal(metadataDisclosure(p).open, false, 'a pristine closed editor stays closed');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

test('pristine metadata disclosure choices follow each fitting independently of drafts', async () => {
  const p = await editor();
  await repaint(p, state(['fit-1', 'fit-2']));
  p.el('fittings-list').querySelectorAll('.fit-row-toggle')[1].click(); await flush();
  await settle(p.last('fittings_detail'), detail('fit-2'));
  assert.equal(metadataDisclosure(p).open, false, 'an opened first editor does not open another fitting');
  setMetadataOpen(p, true);
  await repaint(p, state(['fit-1', 'fit-2']), detail('fit-2'));
  p.el('fittings-list').querySelectorAll('.fit-row-toggle')[0].click(); await flush();
  await settle(p.last('fittings_detail'), detail());
  assert.equal(metadataDisclosure(p).open, true, 'the first fitting retains its edit intent without a draft');
  setMetadataOpen(p, false);
  p.el('fittings-list').querySelectorAll('.fit-row-toggle')[1].click(); await flush();
  await settle(p.last('fittings_detail'), detail('fit-2'));
  assert.equal(metadataDisclosure(p).open, true);
  p.el('fittings-list').querySelectorAll('.fit-row-toggle')[0].click(); await flush();
  await settle(p.last('fittings_detail'), detail());
  assert.equal(metadataDisclosure(p).open, false, 'deliberately closing one editor does not affect another');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

test('dirty metadata stays explicitly closed through membership and refresh without saving', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Draft name');
  input(p.el('fit-desc-fit-1'), 'Draft description');
  setMetadataOpen(p, false);
  tick(p.el('fittings-list').querySelector('.fit-collections').querySelector('input'));
  await repaint(p);
  assert.equal(metadataDisclosure(p).open, false, 'membership must not reopen a deliberately closed draft');
  assert.equal(p.el('fit-name-fit-1').getClientRects().length, 0);
  p.el('fittings-refresh-all').click();
  await repaint(p);
  assert.equal(metadataDisclosure(p).open, false, 'refresh must preserve the same closed choice');
  setMetadataOpen(p, true);
  assertDraft(p, 'Draft name', 'Draft description');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

test('dirty metadata disclosure choices follow each fitting across collection changes', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Closed draft');
  setMetadataOpen(p, false);
  button(p.el('fittings-collections'), 'Doctrine1').click(); await flush();
  const filtered = state(['fit-2']);
  filtered.filters.collection_id = 'doctrine';
  await settle(p.last('fittings_state'), filtered);
  p.el('fittings-list').querySelector('.fit-row-toggle').click(); await flush();
  await settle(p.last('fittings_detail'), detail('fit-2', 'Other fit'));
  assert.equal(metadataDisclosure(p).open, false);
  setMetadataOpen(p, true);
  input(p.el('fit-name-fit-2'), 'Open draft');
  button(p.el('fittings-collections'), 'All fittings1').click(); await flush();
  await settle(p.last('fittings_state'), state(['fit-1', 'fit-2']));
  p.el('fittings-list').querySelectorAll('.fit-row-toggle')[0].click(); await flush();
  await settle(p.last('fittings_detail'), detail());
  assert.equal(metadataDisclosure(p).open, false, 'the first fitting remembers closed, despite its draft');
  assert.equal(p.el('fit-name-fit-1').value, 'Closed draft');
  p.el('fittings-list').querySelectorAll('.fit-row-toggle')[1].click(); await flush();
  await settle(p.last('fittings_detail'), detail('fit-2', 'Other fit'));
  assert.equal(metadataDisclosure(p).open, true, 'the other fitting keeps its independent open choice');
  assert.equal(p.el('fit-name-fit-2').value, 'Open draft');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

for (const applied of [true, false]) {
  test(`closed metadata stays closed through pending Save and ${applied ? 'acceptance' : 'refusal'}`, async () => {
    const p = await editor();
    input(p.el('fit-name-fit-1'), 'Submitted');
    button(metadata(p), 'Save').click(); await flush();
    const save = p.last('fittings_update_metadata');
    input(p.el('fit-name-fit-1'), 'Newer draft');
    setMetadataOpen(p, false);
    await repaint(p);
    assert.equal(metadataDisclosure(p).open, false, 'pending work cannot override explicit closed');
    assert.equal(button(metadata(p), 'Save').disabled, true);
    await settle(save, applied);
    assert.equal(metadataDisclosure(p).open, false, 'neither an acknowledgement nor an error reopens the editor');
    await settle(p.last('fittings_state'), state());
    await settle(p.last('fittings_detail'), detail('fit-1', applied ? 'Submitted' : 'Sabre tackle'));
    assert.equal(metadataDisclosure(p).open, false);
    setMetadataOpen(p, true);
    assertDraft(p, 'Newer draft', 'Saved description');
    assert.equal(button(metadata(p), 'Save').disabled, false);
    if (!applied) assert.match(metadata(p).textContent, /save not confirmed/);
    assert.equal(p.calls('fittings_update_metadata').length, 1);
  });
}

test('metadata acknowledgement does not take focus from a modal or a departed route', async () => {
  for (const owner of ['modal', 'route']) {
    const p = await editor();
    input(p.el('fit-name-fit-1'), 'Submitted');
    button(metadata(p), 'Save').click(); await flush();
    p.el('fit-name-fit-1').focus();
    if (owner === 'modal') {
      p.el('overlay').hidden = false;
      p.el('dlg-ok').focus();
    } else {
      await p.route('main');
      p.el('nav-main').focus();
    }
    const active = p.focused();
    await settle(p.last('fittings_update_metadata'), true);
    assert.ok(p.focused() === active, owner + ' retains focus after background acknowledgement');
  }
});

test('discarding a focused draft returns to a live metadata control', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Discard me');
  const discard = button(metadata(p), 'Discard changes');
  discard.focus(); discard.click();
  await settle(p.confirmations.at(-1), true);
  assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'),
    'the retired Discard action hands focus to its visible summary');
  assert.equal(p.el('fit-name-fit-1').value, 'Sabre tackle');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

test('metadata input focus and caret survive both state and detail rerenders', async () => {
  const p = await editor();
  input(p.el('fit-desc-fit-1'), 'Draft description');
  p.el('fit-desc-fit-1').focus();
  p.el('fit-desc-fit-1').setSelectionRange(2, 7, 'backward');
  await p.changed({ reason: 'collection_membership', entry_id: 'fit-1' });
  await settle(p.last('fittings_state'), state());
  assert.ok(p.focused() === p.el('fit-desc-fit-1'), 'state repaint must restore the live editor control');
  await settle(p.last('fittings_detail'), detail());
  assert.ok(p.focused() === p.el('fit-desc-fit-1'), 'detail repaint must restore the live editor control');
  assert.equal(p.focused().selectionStart, 2);
  assert.equal(p.focused().selectionEnd, 7);
  assert.equal(p.focused().selectionDirection, 'backward');
  assertDraft(p, 'Sabre tackle', 'Draft description');
  p.el('fittings-search').focus();
  await repaint(p);
  assert.ok(p.focused() === p.el('fittings-search'), 'a background draft cannot steal focus');
});

test('metadata Save and summary focus survive acknowledgement without collapsing the editor', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Accepted name');
  const save = button(metadata(p), 'Save');
  save.focus(); save.click();
  assert.equal(save.disabled, true);
  assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'),
    'handoff must precede disabling Save, which would otherwise blur to body');
  await flush();
  const pending = p.last('fittings_update_metadata');
  await repaint(p);
  assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'), 'summary remains owned while pending');
  await settle(pending, true);
  assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'), 'restore the current summary after acceptance');
  assert.equal(button(metadata(p), 'Save').disabled, true, 'accepted unchanged values are clean');
  assert.equal(metadataDisclosure(p).open, true);
  const summary = metadataDisclosure(p).querySelector('summary');
  summary.focus();
  await repaint(p, state(), detail('fit-1', 'Accepted name'));
  assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'), 'restore the current summary');
  assert.equal(metadataDisclosure(p).open, true);
  assert.equal(p.el('fit-name-fit-1').value, 'Accepted name');
  assert.equal(p.calls('fittings_update_metadata').length, 1);
});

test('focused metadata Save keeps a live summary after refusal and an explicit retry', async () => {
  const p = await editor();
  input(p.el('fit-desc-fit-1'), 'Keep after refusal');
  const save = button(metadata(p), 'Save');
  save.focus(); save.click(); await flush();
  assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'));
  await settle(p.last('fittings_update_metadata'), false);
  await settle(p.last('fittings_state'), state());
  await settle(p.last('fittings_detail'), detail());
  assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'));
  assertDraft(p, 'Sabre tackle', 'Keep after refusal');
  assert.match(metadata(p).textContent, /save not confirmed/);
  const retry = button(metadata(p), 'Save');
  retry.focus(); retry.click(); await flush();
  assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'));
  await settle(p.last('fittings_update_metadata'), true);
  assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'));
  assert.equal(p.calls('fittings_update_metadata').length, 2);
});

for (const applied of [true, false]) {
  test(`metadata Save ${applied ? 'acceptance' : 'refusal'} preserves newer typing and its focus`, async () => {
    const p = await editor();
    input(p.el('fit-name-fit-1'), 'Submitted');
    const save = button(metadata(p), 'Save');
    save.focus(); save.click(); await flush();
    assert.ok(p.focused() === metadataDisclosure(p).querySelector('summary'));
    p.el('fit-name-fit-1').focus();
    input(p.el('fit-name-fit-1'), 'Newer typing');
    p.el('fit-name-fit-1').setSelectionRange(2, 5, 'backward');
    await settle(p.last('fittings_update_metadata'), applied);
    await settle(p.last('fittings_state'), state());
    await settle(p.last('fittings_detail'), detail('fit-1', applied ? 'Submitted' : 'Sabre tackle'));
    assertDraft(p, 'Newer typing', 'Saved description');
    assert.ok(p.focused() === p.el('fit-name-fit-1'), 'new typing owns focus, not the earlier Save');
    assert.equal(p.focused().selectionStart, 2);
    assert.equal(p.focused().selectionEnd, 5);
    assert.equal(p.focused().selectionDirection, 'backward');
    assert.equal(p.calls('fittings_update_metadata').length, 1);
  });
}

test('metadata Save never takes focus from another control, modal or route', async () => {
  for (const owner of ['search', 'modal', 'copy', 'route']) {
    for (const changeBeforeSave of [true, false]) {
      const p = await editor();
      input(p.el('fit-name-fit-1'), 'Submitted');
      const save = button(metadata(p), 'Save');
      save.focus();
      if (!changeBeforeSave) { save.click(); await flush(); }
      if (owner === 'modal') {
        p.el('overlay').hidden = false;
        p.el('dlg-ok').focus();
      } else if (owner === 'copy') {
        tick(p.el('fittings-list').querySelector('input'));
        p.el('fittings-copy-selected').click();
        p.el('fittings-copy-close').focus();
      } else if (owner === 'route') {
        await p.route('main');
        p.el('nav-main').focus();
      } else p.el('fittings-search').focus();
      const active = p.focused();
      // Programmatic activation does not focus Save; it cannot claim focus the
      // user moved elsewhere, even if the handler runs after that move.
      if (changeBeforeSave) { save.click(); await flush(); }
      assert.ok(p.focused() === active, owner + ' owns focus during pending Save');
      await settle(p.last('fittings_update_metadata'), true);
      assert.ok(p.focused() === active, owner + ' owns focus after acknowledgement');
    }
  }
});

// A render using server metadata must not erase text that was never submitted.
test('membership push and refresh preserve both metadata drafts without saving on blur', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Draft name');
  input(p.el('fit-desc-fit-1'), 'Draft description');
  p.el('fit-name-fit-1').dispatchEvent({ type: 'blur' });
  tick(p.el('fittings-list').querySelector('.fit-collections').querySelector('input'));
  await flush();
  assert.deepEqual(p.last('fittings_set_membership').args, ['fit-1', 'doctrine', true]);
  await repaint(p);
  assertDraft(p, 'Draft name', 'Draft description');
  p.el('fittings-refresh-all').click();
  await repaint(p);
  assertDraft(p, 'Draft name', 'Draft description');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
  assert.deepEqual(p.errors, []);
});

test('draft follows its fitting through collapse, another editor, filters and route re-entry', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Keep me');
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  assert.match(p.el('fittings-list').textContent, /Unsaved changes/);
  input(p.el('fittings-search'), 'other');
  await p.timers();
  const filtered = state(['fit-2']);
  filtered.filters.search = 'other';
  await settle(p.last('fittings_state'), filtered);
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  await settle(p.last('fittings_detail'), detail('fit-2', 'Other fit'));
  assert.equal(p.el('fit-name-fit-2').value, 'Other fit');
  setMetadataOpen(p, true);
  input(p.el('fit-name-fit-2'), 'Second draft');
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), filtered);
  await settle(p.last('fittings_detail'), detail('fit-2', 'Other fit'));
  assert.equal(p.el('fit-name-fit-2').value, 'Second draft');
  p.el('fittings-filter-clear').click();
  await flush();
  await settle(p.last('fittings_state'), state(['fit-1', 'fit-2']));
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  await settle(p.last('fittings_detail'), detail());
  assertDraft(p, 'Keep me', 'Saved description');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

test('older save acknowledgement cannot erase newer typing or allow overlapping saves', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Submitted');
  button(metadata(p), 'Save').click();
  await flush();
  const save = p.last('fittings_update_metadata');
  input(p.el('fit-name-fit-1'), 'Newer typing');
  await repaint(p, state(), detail('fit-1', 'Submitted'));
  assertDraft(p, 'Newer typing', 'Saved description');
  assert.equal(metadata(p).querySelector('button').disabled, true);
  await settle(save, true);
  assertDraft(p, 'Newer typing', 'Saved description');
  button(metadata(p), 'Save').click();
  await flush();
  assert.deepEqual(p.last('fittings_update_metadata').args,
                   ['fit-1', 'Newer typing', 'Saved description']);
  assert.equal(p.calls('fittings_update_metadata').length, 2);
});

for (const failure of ['false', 'null', 'reject']) {
  test(`metadata ${failure} retains editable draft for explicit successful retry`, async () => {
    const p = await editor();
    input(p.el('fit-desc-fit-1'), 'Keep after failure');
    button(metadata(p), 'Save').click();
    await flush();
    if (failure === 'reject') p.last('fittings_update_metadata').reject(new Error('injected'));
    else p.last('fittings_update_metadata').resolve(failure === 'false' ? false : null);
    await flush();
    await settle(p.last('fittings_state'), state());
    await settle(p.last('fittings_detail'), detail());
    assertDraft(p, 'Sabre tackle', 'Keep after failure');
    assert.match(metadata(p).textContent, /not confirmed|could not|failed/i);
    assert.equal(button(metadata(p), 'Save').disabled, false);
    button(metadata(p), 'Save').click();
    await flush();
    await settle(p.last('fittings_update_metadata'), true);
    assert.doesNotMatch(metadata(p).textContent, /Unsaved changes|not confirmed|could not|failed/i);
    assert.equal(p.el('fit-desc-fit-1').value, 'Keep after failure');
    await repaint(p, state(), detail('fit-1', 'Sabre tackle', 'Keep after failure'));
    assert.equal(p.el('fit-desc-fit-1').value, 'Keep after failure');
    assert.equal(p.errors.length, failure === 'reject' ? 1 : 0);
  });
}

test('save acknowledgement invalidates an older detail reply without losing accepted text', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Accepted name');
  button(metadata(p), 'Save').click();
  await flush();
  await p.changed({ reason: 'metadata', entry_id: 'fit-1' });
  await settle(p.last('fittings_state'), state());
  const staleDetail = p.last('fittings_detail');
  await settle(p.last('fittings_update_metadata'), true);
  await settle(staleDetail, detail());
  assert.equal(p.el('fit-name-fit-1').value, 'Accepted name');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
});

test('discard requires confirmation, restores persisted metadata and never writes', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Discard me');
  button(metadata(p), 'Discard changes').click();
  assert.equal(p.confirmations.length, 1);
  await settle(p.confirmations[0], false);
  assertDraft(p, 'Discard me', 'Saved description');
  button(metadata(p), 'Discard changes').click();
  await settle(p.confirmations[1], true);
  assert.equal(p.el('fit-name-fit-1').value, 'Sabre tackle');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

test('discard confirmation cannot erase typing entered after the dialog opened', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Older draft');
  button(metadata(p), 'Discard changes').click();
  input(p.el('fit-name-fit-1'), 'Newer draft');
  await settle(p.confirmations[0], true);
  assertDraft(p, 'Newer draft', 'Saved description');
});

test('delete notification retires the fitting draft, even while route is hidden', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Deleted draft');
  assertDraft(p, 'Deleted draft', 'Saved description');
  await p.route('main');
  await p.changed({ reason: 'delete', entry_id: 'fit-1' });
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  await settle(p.last('fittings_detail'), detail());
  assert.equal(p.el('fit-name-fit-1').value, 'Sabre tackle');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
});

test('a complete unfiltered library read retires drafts for removed IDs, not failed reads', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Removed draft');
  await p.changed({ reason: 'refresh' });
  await settle(p.last('fittings_state'), { available: false, warnings: ['Unavailable'] });
  await settle(p.last('fittings_detail'), null);
  await repaint(p);
  assertDraft(p, 'Removed draft', 'Saved description');
  await repaint(p, state([]), null);
  await repaint(p);
  assert.equal(p.el('fit-name-fit-1').value, 'Sabre tackle');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
});

test('older save failure keeps newer text across requery and requires another explicit save', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Submitted');
  button(metadata(p), 'Save').click();
  await flush();
  input(p.el('fit-name-fit-1'), 'Newer');
  await settle(p.last('fittings_update_metadata'), false);
  await settle(p.last('fittings_state'), state());
  await settle(p.last('fittings_detail'), detail());
  assertDraft(p, 'Newer', 'Saved description');
  assert.equal(p.calls('fittings_update_metadata').length, 1);
  assert.equal(button(metadata(p), 'Save').disabled, false);
});

test('collapse/reopen during a save cannot let a pre-ack detail read undo accepted metadata', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Accepted');
  button(metadata(p), 'Save').click();
  await flush();
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  const stale = p.last('fittings_detail');
  await settle(p.last('fittings_update_metadata'), true);
  await settle(stale, detail());
  assert.ok(!p.el('fit-name-fit-1') || p.el('fit-name-fit-1').value !== 'Sabre tackle');
  await settle(p.last('fittings_state'), state());
  await settle(p.last('fittings_detail'), detail('fit-1', 'Accepted'));
  assert.equal(p.el('fit-name-fit-1').value, 'Accepted');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
});

// Native subtree removal blurs its focused control before the replacement mounts.
async function warningPage() {
  const p = await page();
  await p.route('fittings');
  const payload = state(['fit-1', 'fit-2']);
  payload.total = 200;
  payload.rows.forEach(row => { row.deployable = false; });
  await settle(p.last('fittings_state'), payload);
  p.el('fittings-list').onChildrenCleared = () => {
    const active = p.focused();
    if (!active.ownerDocument.contains(active)) active.blur();
  };
  return p;
}
function warning(p, id = 'fit-1') {
  return p.el('fit-toggle-' + id)?.parentNode.querySelector('.fit-deployability');
}

test('warning focus: keyboard-equivalent activation follows both rebuilt warning controls', async () => {
  const p = await warningPage();
  const original = warning(p);
  original.focus(); original.click(); await flush();
  const replacement = warning(p);
  assert.notEqual(replacement, original);
  assert.equal(p.focused(), replacement, 'rebuilding must not leave keyboard focus on BODY');
  assert.equal(replacement.id, 'fit-deployability-fit-1');
  assert.equal(replacement.getAttribute('aria-expanded'), 'true');
  assert.equal(replacement.getAttribute('aria-label'), 'Sabre tackle: cannot copy. Show details.');
  assert.equal(replacement.lastFocusOptions.preventScroll, true);
  await settle(p.last('fittings_detail'), detail());
  assert.equal(p.focused(), warning(p), 'detail receipt keeps the current warning owner');
  const expanded = warning(p), calls = p.calls().length;
  expanded.click(); await flush();
  assert.equal(warning(p), expanded, 'already expanded Details remains an open-only action');
  assert.equal(p.focused(), expanded);
  assert.equal(p.calls().length, calls);
});

test('warning focus: disappearing eligibility action falls back to its own row, not the editor', async () => {
  const p = await warningPage();
  warning(p).focus(); warning(p).click(); await flush();
  await settle(p.last('fittings_detail'), detail());
  warning(p).focus();
  await p.changed({reason: 'refresh'});
  await settle(p.last('fittings_state'), state(['fit-1', 'fit-2']));
  assert.equal(warning(p), null);
  assert.equal(p.focused(), p.el('fit-toggle-fit-1'));
  assert.equal(p.focused().lastFocusOptions.preventScroll, true);
  await settle(p.last('fittings_detail'), detail());
  assert.equal(p.focused(), p.el('fit-toggle-fit-1'));
});

for (const owner of ['control', 'dialog', 'route', 'row', 'filter', 'page']) {
  test('warning focus: delayed detail yields to newer ' + owner, async () => {
    const p = await warningPage();
    warning(p).focus(); warning(p).click(); await flush();
    const stale = p.last('fittings_detail');
    if (owner === 'control') p.el('fittings-search').focus();
    if (owner === 'dialog') { p.el('overlay').hidden = false; p.el('dlg-ok').focus(); }
    if (owner === 'route') { await p.route('main'); p.el('nav-main').focus(); }
    if (owner === 'row') {
      p.el('fit-toggle-fit-2').focus(); p.el('fit-toggle-fit-2').click(); await flush();
      await settle(p.last('fittings_detail'), detail('fit-2'));
    }
    if (owner === 'filter' || owner === 'page') {
      warning(p).focus();
      if (owner === 'filter') { input(p.el('fittings-search'), 'Other'); await p.timers(); }
      else { p.el('fittings-page-next').click(); await flush(); }
      const payload = state(['fit-2']); payload.rows[0].deployable = false;
      payload.filters.search = owner === 'filter' ? 'Other' : '';
      payload.page = owner === 'page' ? 2 : 1;
      await settle(p.last('fittings_state'), payload);
      assert.equal(p.el('fit-toggle-fit-1'), null);
    }
    const active = p.focused();
    await settle(stale, detail());
    assert.equal(p.focused(), active);
  });
}

test('warning focus: programmatic expansion of another row revokes the old warning owner', async () => {
  const p = await warningPage();
  warning(p).focus();
  p.el('fit-toggle-fit-2').click(); await flush();
  assert.notEqual(p.focused(), warning(p));
  await settle(p.last('fittings_detail'), detail('fit-2'));
  assert.notEqual(p.focused(), warning(p));
});

for (const owner of ['control', 'dialog', 'route', 'render']) {
  test('warning focus: synchronous removal yields to newer ' + owner, async () => {
    const p = await warningPage();
    const host = p.el('fittings-list'), nativeRemoval = host.onChildrenCleared;
    const scroller = p.el('fittings-workspace-scroll');
    scroller.scrollTop = 40;
    const other = p.el('fit-toggle-fit-2');
    host.onChildrenCleared = () => {
      nativeRemoval(); host.onChildrenCleared = nativeRemoval;
      if (owner === 'control') { p.el('fittings-search').focus(); scroller.scrollTop = 123; }
      if (owner === 'dialog') { p.el('overlay').hidden = false; p.el('dlg-ok').focus(); }
      if (owner === 'route') { p.route('main'); p.el('nav-main').focus(); }
      if (owner === 'render') other.click();
    };
    warning(p).focus(); warning(p).click(); await flush();
    assert.notEqual(p.focused(), warning(p));
    if (owner === 'control') {
      assert.equal(p.focused(), p.el('fittings-search'));
      assert.equal(scroller.scrollTop, 123, 'new owner scroll survives the old repaint');
    }
    if (owner === 'dialog') assert.equal(p.focused(), p.el('dlg-ok'));
    if (owner === 'route') assert.equal(p.focused(), p.el('nav-main'));
    if (owner === 'render') {
      assert.equal(host.querySelectorAll('.fit-row').length, 2, 'older render cannot append over its successor');
      assert.equal(p.el('fit-toggle-fit-2').getAttribute('aria-expanded'), 'true');
      assert.deepEqual(p.calls('fittings_detail').map(call => call.args[0]), ['fit-2'],
        'the retired row action cannot invalidate the newer detail request');
      await settle(p.last('fittings_detail'), detail('fit-2'));
      assert.ok(p.el('fit-name-fit-2'), 'the newer row must finish loading');
    }
  });
}

test('warning focus: focus-event handoff keeps the newer owner and its scroll', async () => {
  const p = await warningPage();
  const doc = warning(p).ownerDocument, create = doc.createElement;
  const scroller = p.el('fittings-workspace-scroll');
  doc.createElement = tag => {
    const node = create(tag), focus = node.focus;
    node.focus = function (options) {
      focus.call(this, options);
      if (this.id === 'fit-deployability-fit-1' && options?.preventScroll) {
        p.el('fittings-search').focus();
        scroller.scrollTop = 123;
      }
    };
    return node;
  };
  warning(p).focus(); warning(p).click(); await flush();
  assert.equal(p.focused(), p.el('fittings-search'));
  assert.equal(scroller.scrollTop, 123, 'old restore cannot overwrite a focus-event successor');
});

// Committed equality is distinct from retaining a draft/receipt owner.
function assertMetadataDirty(p, dirty, pending = false) {
  const status = metadata(p).querySelector('.fit-metadata-actions').querySelector('p');
  assert.ok(status, 'metadata has its own ordinary outcome paragraph');
  assert.equal(status.tagName, 'P');
  assert.equal(status.getAttribute('role'), null);
  assert.equal(status.getAttribute('aria-live'), null);
  assert.equal(/Unsaved changes/.test(status.textContent), dirty);
  assert.equal(/Unsaved changes/.test(p.el('fittings-list').querySelector('.fit-meta').textContent), dirty,
    'row cue and editor must use the same equality/pending predicate');
  assert.equal(button(metadata(p), 'Save').disabled, !dirty || pending);
}

test('metadata clean Save is disabled and handler-guarded before any edit', async () => {
  const p = await editor();
  const save = button(metadata(p), 'Save');
  assert.equal(save.disabled, true, 'an unchanged fitting has nothing to save');
  save.dispatchEvent({type: 'click'}); await flush();
  assert.equal(p.calls('fittings_update_metadata').length, 0);
  assertMetadataDirty(p, false);
});

test('metadata exact edit and revert updates both cues without replacing controls or selection', async () => {
  const p = await editor();
  const name = p.el('fit-name-fit-1'), description = p.el('fit-desc-fit-1');
  const disclosure = metadataDisclosure(p), row = p.el('fittings-list').children[0];
  const scroller = p.el('fittings-workspace-scroll');
  name.focus(); name.setSelectionRange(2, 7, 'backward'); scroller.scrollTop = 91;
  for (const [field, value, dirty] of [
    [name, 'Sabre tackle ', true], [description, 'Saved description\n', true],
    [name, 'Sabre tackle', true], [description, 'Saved description', false],
    [description, '', true], [description, 'Saved description', false]
  ]) {
    input(field, value);
    assertMetadataDirty(p, dirty);
    const meta = row.querySelector('.fit-meta');
    assert.equal(meta.title, meta.textContent, 'ellipsis keeps the complete current status in its title');
    assert.equal(p.el('fittings-list').children[0] === row, true);
    assert.equal(metadataDisclosure(p) === disclosure, true);
    assert.equal(p.el('fit-name-fit-1') === name, true);
    assert.equal(p.focused() === name, true);
    assert.deepEqual([name.selectionStart, name.selectionEnd, name.selectionDirection], [2, 7, 'backward']);
    assert.equal(scroller.scrollTop, 91);
  }
  button(metadata(p), 'Save').dispatchEvent({type: 'click'}); await flush();
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

for (const failure of ['false', 'null', 'reject']) {
  test(`metadata ${failure} never advances baseline; reverting becomes clean without erasing refusal`, async () => {
    const p = await editor();
    input(p.el('fit-name-fit-1'), 'Submitted');
    button(metadata(p), 'Save').click(); await flush();
    if (failure === 'reject') p.last('fittings_update_metadata').reject(new Error('injected'));
    else p.last('fittings_update_metadata').resolve(failure === 'false' ? false : null);
    await flush();
    // Even matching readback is not the missing Boolean acknowledgement.
    await settle(p.last('fittings_state'), state());
    await settle(p.last('fittings_detail'), detail('fit-1', 'Submitted'));
    assertMetadataDirty(p, true);
    input(p.el('fit-name-fit-1'), 'Sabre tackle');
    assertMetadataDirty(p, false);
    assert.match(metadata(p).textContent, /save not confirmed/);
    await repaint(p, state(), detail('fit-1', 'Submitted'));
    assert.equal(p.el('fit-name-fit-1').value, 'Sabre tackle', 'refused display is not hydrated away');
    assertMetadataDirty(p, false);
    assert.match(metadata(p).textContent, /save not confirmed/);
    button(metadata(p), 'Save').dispatchEvent({type: 'click'}); await flush();
    assert.equal(p.calls('fittings_update_metadata').length, 1);
    input(p.el('fit-name-fit-1'), 'Submitted');
    assertMetadataDirty(p, true);
    button(metadata(p), 'Save').click(); await flush();
    assert.equal(p.calls('fittings_update_metadata').length, 2);
    await settle(p.last('fittings_update_metadata'), true);
    assertMetadataDirty(p, false);
    assert.doesNotMatch(metadata(p).textContent, /save not confirmed/);
  });
}

for (const newer of ['Sabre tackle', 'Submitted', 'Newer text']) {
  test('metadata pending survives revert; ACK compares newer generation exactly: ' + newer, async () => {
    const p = await editor();
    input(p.el('fit-name-fit-1'), 'Submitted');
    button(metadata(p), 'Save').click(); await flush();
    const save = p.last('fittings_update_metadata');
    input(p.el('fit-name-fit-1'), 'Intermediate');
    input(p.el('fit-name-fit-1'), newer);
    assertMetadataDirty(p, true, true);
    button(metadata(p), 'Save').dispatchEvent({type: 'click'}); await flush();
    assert.equal(p.calls('fittings_update_metadata').length, 1, 'pending receipt retains exclusive admission');
    await repaint(p, state(), detail('fit-1', 'Submitted'));
    assertMetadataDirty(p, true, true); // matching read cannot acknowledge the save
    await settle(save, true);
    assert.equal(p.el('fit-name-fit-1').value, newer);
    assertMetadataDirty(p, newer !== 'Submitted');
    input(p.el('fit-name-fit-1'), 'Submitted');
    assertMetadataDirty(p, false, false);
    input(p.el('fit-name-fit-1'), 'Second submitted');
    button(metadata(p), 'Save').click(); await flush();
    const second = p.last('fittings_update_metadata');
    input(p.el('fit-name-fit-1'), 'Submitted');
    assertMetadataDirty(p, true, true);
    await settle(second, true);
    assert.equal(p.el('fit-name-fit-1').value, 'Submitted');
    assertMetadataDirty(p, true, false);
    input(p.el('fit-name-fit-1'), 'Second submitted');
    assertMetadataDirty(p, false, false);
    assert.equal(p.calls('fittings_update_metadata').length, 2);
  });
}

test('metadata true ACK preserves exact whitespace, newline and non-BMP submitted pair', async () => {
  const p = await editor();
  const name = '  Tacklé \u{1f680}  ', description = '  first\n\nsecond \u{1f680}\n';
  input(p.el('fit-name-fit-1'), name); input(p.el('fit-desc-fit-1'), description);
  button(metadata(p), 'Save').click(); await flush();
  assert.deepEqual(p.last('fittings_update_metadata').args, ['fit-1', name, description]);
  await settle(p.last('fittings_update_metadata'), true);
  assert.equal(p.el('fit-name-fit-1').value, name);
  assert.equal(p.el('fit-desc-fit-1').value, description);
  assertMetadataDirty(p, false);
  input(p.el('fit-name-fit-1'), name.trim()); assertMetadataDirty(p, true);
  input(p.el('fit-name-fit-1'), name); assertMetadataDirty(p, false);
  input(p.el('fit-desc-fit-1'), description.trim()); assertMetadataDirty(p, true);
  input(p.el('fit-desc-fit-1'), description); assertMetadataDirty(p, false);
  assert.equal(p.calls('fittings_update_metadata').length, 1);
});

test('metadata accepted clean detail becomes the next baseline, not the list row summary', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Temporary'); input(p.el('fit-name-fit-1'), 'Sabre tackle');
  await repaint(p, state(), detail('fit-1', 'Fresh detail', 'Fresh description'));
  assert.equal(p.el('fit-name-fit-1').value, 'Fresh detail');
  assert.equal(p.el('fit-desc-fit-1').value, 'Fresh description');
  assertMetadataDirty(p, false);
  input(p.el('fit-name-fit-1'), 'Sabre tackle'); assertMetadataDirty(p, true);
  input(p.el('fit-name-fit-1'), 'Fresh detail'); assertMetadataDirty(p, false);
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

test('metadata two accepted saves fence older detail and retain HWM through failed refresh', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'First'); button(metadata(p), 'Save').click(); await flush();
  await settle(p.last('fittings_update_metadata'), true);
  await settle(p.last('fittings_state'), state());
  const preSecond = p.last('fittings_detail');
  input(p.el('fit-name-fit-1'), 'Second'); button(metadata(p), 'Save').click(); await flush();
  input(p.el('fit-name-fit-1'), 'Third');
  await settle(p.last('fittings_update_metadata'), true);
  await settle(preSecond, detail('fit-1', 'First'));
  assert.equal(p.el('fit-name-fit-1').value, 'Third');
  input(p.el('fit-name-fit-1'), 'Second'); assertMetadataDirty(p, false);
  input(p.el('fit-name-fit-1'), 'Third');
  await settle(p.last('fittings_state'), null);
  assert.equal(p.el('fit-name-fit-1').value, 'Third');
  // A null state reply clears `asked`; route re-entry explicitly retries it.
  const failedState = p.last('fittings_state');
  await p.route('main'); await p.route('fittings');
  assert.notEqual(p.last('fittings_state'), failedState);
  await settle(p.last('fittings_state'), state());
  assert.notEqual(p.last('fittings_detail'), preSecond);
  await settle(p.last('fittings_detail'), null);
  // A failed detail read must not retire the draft or acknowledged pair.
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  p.el('fittings-list').querySelector('.fit-row-toggle').click(); await flush();
  await settle(p.last('fittings_detail'), detail('fit-1', 'Second'));
  assert.equal(p.el('fit-name-fit-1').value, 'Third');
  assertMetadataDirty(p, true);
  input(p.el('fit-name-fit-1'), 'Second'); assertMetadataDirty(p, false);
  input(p.el('fit-name-fit-1'), 'First'); assertMetadataDirty(p, true);
  input(p.el('fit-name-fit-1'), 'Second'); assertMetadataDirty(p, false);
  assert.equal(p.calls('fittings_update_metadata').length, 2);
});

for (const applied of [true, false]) {
  test('metadata off-row and hidden-route receipt preserves baseline: ' + applied, async () => {
    const p = await editor();
    input(p.el('fit-name-fit-1'), 'Submitted');
    button(metadata(p), 'Save').click(); await flush();
    const save = p.last('fittings_update_metadata');
    input(p.el('fit-name-fit-1'), 'Newer');
    input(p.el('fittings-search'), 'other'); await p.timers();
    const filtered = state(['fit-2']); filtered.filters.search = 'other';
    await settle(p.last('fittings_state'), filtered);
    p.el('fittings-list').querySelector('.fit-row-toggle').click(); await flush();
    await settle(p.last('fittings_detail'), detail('fit-2', 'Other'));
    await p.route('main'); p.el('nav-main').focus();
    await settle(save, applied);
    assert.equal(p.focused() === p.el('nav-main'), true);
    await p.route('fittings'); await settle(p.last('fittings_state'), filtered);
    await settle(p.last('fittings_detail'), detail('fit-2', 'Other'));
    p.el('fittings-filter-clear').click(); await flush();
    await settle(p.last('fittings_state'), state(['fit-1', 'fit-2']));
    p.el('fittings-list').querySelector('.fit-row-toggle').click(); await flush();
    await settle(p.last('fittings_detail'), detail('fit-1', applied ? 'Submitted' : 'Sabre tackle'));
    assert.equal(p.el('fit-name-fit-1').value, 'Newer');
    input(p.el('fit-name-fit-1'), applied ? 'Submitted' : 'Sabre tackle');
    assertMetadataDirty(p, false);
    if (!applied) assert.match(metadata(p).textContent, /save not confirmed/);
    assert.equal(p.calls('fittings_update_metadata').length, 1);
  });
}

test('metadata discard uses last accepted pair and deleted receipt cannot taint replacement record', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Accepted'); button(metadata(p), 'Save').click(); await flush();
  await settle(p.last('fittings_update_metadata'), true);
  input(p.el('fit-name-fit-1'), 'Discard this');
  button(metadata(p), 'Discard changes').click(); await settle(p.confirmations.at(-1), true);
  assert.equal(p.el('fit-name-fit-1').value, 'Accepted'); assertMetadataDirty(p, false);
  input(p.el('fit-name-fit-1'), 'Deleted submission'); button(metadata(p), 'Save').click(); await flush();
  const deletedSave = p.last('fittings_update_metadata');
  await p.changed({reason: 'delete', entry_id: 'fit-1'});
  await settle(p.last('fittings_state'), state([])); await settle(p.last('fittings_detail'), null);
  await repaint(p, state(), detail('fit-1', 'Replacement'));
  input(p.el('fit-name-fit-1'), 'Replacement draft');
  await settle(deletedSave, true);
  assert.equal(p.el('fit-name-fit-1').value, 'Replacement draft');
  input(p.el('fit-name-fit-1'), 'Replacement'); assertMetadataDirty(p, false);
  assert.equal(p.calls('fittings_update_metadata').length, 2);
});

test('fitting row tracks preserve complete accessible identity and independent warning action', async () => {
  const p = await page(); await p.route('fittings');
  const payload = state(['fit-1', 'fit-2']);
  Object.assign(payload.rows[0], {name: 'Long fitting & <identity>', ship_name: 'Long hull identity',
    presence_count: 2, collection_ids: ['doctrine'], superseded_by: 'fit-2', deployable: false});
  await settle(p.last('fittings_state'), payload);
  const row = p.el('fittings-list').children[0], top = row.querySelector('.fit-row-top');
  const toggle = row.querySelector('.fit-row-toggle'), status = row.querySelector('.fit-row-status');
  assert.ok(status, 'ownership and warning get their own sibling track');
  assert.deepEqual(top.children.map(node => node.className), ['check fit-select', 'fit-row-toggle', 'fit-row-status']);
  assert.equal(toggle.tagName, 'BUTTON'); assert.equal(toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(toggle.children[0].className, 'fit-identity');
  assert.equal(toggle.children[0].querySelector('.chev').getAttribute('aria-hidden'), 'true');
  assert.equal(toggle.children[0].querySelector('.fit-name').title, 'Long fitting & <identity>');
  assert.equal(toggle.querySelector('.fit-ship').title, 'Long hull identity');
  const labels = toggle.getAttribute('aria-labelledby').split(' ').map(id => p.el(id));
  assert.deepEqual(labels.map(node => node.textContent), ['Long fitting & <identity>', 'Long hull identity',
    'On 2 characters · Doctrine · Superseded']);
  assert.equal(labels[2].parentNode === status, true);
  assert.equal(labels[2].title, 'On 2 characters · Doctrine · Superseded');
  const warning = status.querySelector('.fit-deployability');
  assert.equal(warning.textContent, 'Cannot copy · Details…');
  assert.equal(warning.getAttribute('aria-label'), 'Long fitting & <identity>: cannot copy. Show details.');
  assert.equal(toggle.contains(warning), false, 'no nested interactive buttons');
  warning.click(); await flush(); await settle(p.last('fittings_detail'), detail());
  assert.equal(p.el('fit-toggle-fit-1').getAttribute('aria-expanded'), 'true');
  assert.match(p.el('fittings-list').querySelector('.notice').textContent,
    /Not deployable: this fitting cannot be copied safely\. Choose a different fitting to copy\./);
  assert.equal(p.calls('fittings_preflight_copy').length, 0);
});

test('fitting detail groups keep reading content before management and separate immediate controls', async () => {
  const p = await editor();
  const payload = detail(); payload.aliases = [{name: 'Alternative', description: ''}];
  await repaint(p, state(), payload);
  const box = p.el('fittings-list').querySelector('.fit-detail');
  assert.deepEqual(box.children.map(node => node.className), ['fit-detail-content', 'fit-detail-management']);
  const [content, management] = box.children;
  assert.deepEqual(content.children.map(node => node.className), ['fit-description', 'fit-clipboard-actions', 'fit-modules']);
  assert.deepEqual(management.children.map(node => node.className),
    ['fit-aliases', 'fit-presences', 'fit-metadata-disclosure', 'fit-immediate']);
  assert.deepEqual(management.querySelector('.fit-immediate').children.map(node => node.className),
    ['hint fit-immediate-note', 'fit-collections', 'fit-supersession', 'forget-row']);
  const status = metadata(p).querySelector('.fit-metadata-status');
  for (const id of ['fit-name-fit-1', 'fit-desc-fit-1']) {
    assert.ok(p.el(id).getAttribute('aria-describedby').split(' ').includes(status.id));
  }
});

for (const kind of ['membership', 'supersession']) {
  for (const applied of [true, false]) {
    test(`immediate ${kind} ${applied ? 'push' : 'refusal'} preserves owned focus and dirty metadata`, async () => {
      const p = await editor(); await repaint(p, state(['fit-1', 'fit-2']));
      input(p.el('fit-name-fit-1'), 'Unsubmitted');
      const group = kind === 'membership' ? '.fit-collections' : '.fit-supersession';
      const tag = kind === 'membership' ? 'input' : 'select';
      let control = p.el('fittings-list').querySelector(group).querySelector(tag);
      control.focus(); const id = control.id;
      assert.ok(id, 'stable control identity is required for guarded focus restoration');
      if (kind === 'membership') tick(control);
      else { control.value = 'fit-2'; control.dispatchEvent({type: 'change'}); }
      await flush(); await settle(p.last('fittings_set_' + kind), applied);
      if (applied) await p.changed({reason: kind, entry_id: 'fit-1'});
      await settle(p.last('fittings_state'), state(['fit-1', 'fit-2']));
      assert.equal(p.focused() === p.el(id), true, 'state refresh preserves current owner');
      await settle(p.last('fittings_detail'), detail());
      assert.equal(p.focused() === p.el(id), true, 'detail refresh preserves current owner');
      assert.equal(p.el('fit-name-fit-1').value, 'Unsubmitted'); assertMetadataDirty(p, true);
      assert.equal(p.calls('fittings_update_metadata').length, 0);
      p.el('fittings-search').focus(); await repaint(p, state(['fit-1', 'fit-2']));
      assert.equal(p.focused() === p.el('fittings-search'), true, 'refresh cannot reclaim relinquished focus');
    });
  }
}

test('expanded fitting sticky clearance follows measured header height without moving focus or scroll', async () => {
  const p = await editor();
  const scroller = p.el('fittings-workspace-scroll');
  const top = p.el('fittings-list').querySelector('.fit-row-top');
  const name = p.el('fit-name-fit-1'); name.focus(); scroller.scrollTop = 109;
  assert.equal(scroller.style.getPropertyValue('--fit-sticky-clearance'), '44px', 'render measures the header plus eight');
  top.measuredHeight = 93.5; p.resize();
  assert.equal(scroller.style.getPropertyValue('--fit-sticky-clearance'), '101.5px');
  top.measuredHeight = 112; p.resizeObserved(top);
  assert.equal(scroller.style.getPropertyValue('--fit-sticky-clearance'), '120px', 'font/wrapping changes update the same clearance');
  assert.equal(p.focused() === name, true); assert.equal(scroller.scrollTop, 109);
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  top.measuredHeight = 300; p.resizeObserved(top);
  assert.equal(scroller.style.getPropertyValue('--fit-sticky-clearance'), '', 'collapsed/detached header no longer owns clearance');
});

function preflight(ticket = 'ticket-1') {
  return { accepted: true, ticket_id: ticket, write_count: 1, counts: { ready: 1 },
    requires_resolution: false, pairs: [{ entry_id: 'fit-1', character_id: 42,
      fitting_name: 'Sabre tackle', character_name: 'Pilot', status: 'ready',
      chosen_name: 'Sabre tackle' }] };
}
async function reviewCopy(p, payload) {
  p.el('fittings-list').querySelectorAll('input').forEach(tick);
  p.el('fittings-copy-selected').click();
  tick(p.el('fittings-copy-body').querySelector('input'));
  p.el('fittings-copy-review').click();
  await flush();
  if (payload) await settle(p.last('fittings_preflight_copy'), payload);
}
async function startReviewedCopy(p) {
  p.el('fittings-copy-start').click();
  await settle(p.confirmations.at(-1), true);
  await settle(p.last('fittings_start_copy'), true);
}
function sameNameWorkspace() {
  const payload = state(['fit-1', 'fit-2']);
  payload.rows[0].name = payload.rows[1].name = 'Fleet tackle';
  payload.rows[1].ship_name = 'Flycatcher';
  payload.rows[1].ship_type_id = 22464;
  return payload;
}
function sameNamePreflight() {
  // Reversed relative to the workspace: correlation is by ID, not order or name.
  return { ...preflight(), counts: { ready: 1, present: 1, conflict: 0, unavailable: 0 },
    pairs: [
      { ...preflight().pairs[0], entry_id: 'fit-2', fitting_name: 'Fleet tackle',
        chosen_name: 'Fleet tackle alternate' },
      { ...preflight().pairs[0], fitting_name: 'Fleet tackle', status: 'present' }
    ] };
}

for (const resolving of [false, true]) {
  test(`additive-only reassurance follows the ${resolving ? 'conflict' : 'ready'} review summary once`, async () => {
    const p = await page();
    await p.route('fittings');
    await settle(p.last('fittings_state'), state());
    const review = preflight();
    if (resolving) {
      review.requires_resolution = true;
      review.write_count = 0;
      review.counts = { conflict: 1 };
      review.pairs[0].status = 'conflict';
    }
    await reviewCopy(p, review);
    const body = p.el('fittings-copy-body');
    assert.ok(p.el('fittings-copy-summary'), 'summary stays outside the scroller');
    const reassurance = body.children[0];
    assert.match(reassurance.textContent, /only add fittings.*existing fittings.*kept/i,
      'safety context belongs before the pair list, including without conflicts');
    assert.equal(body.querySelectorAll('p').filter(node => /only add fittings/i.test(node.textContent)).length, 1);
    if (resolving) {
      input(body.querySelector('.fit-copy-alternate'), 'Alternate tackle');
      const reason = p.el(p.el('fittings-copy-review').getAttribute('aria-describedby'));
      assert.match(reason.textContent, /review.*alternate names.*skips/i);
      assert.doesNotMatch(reason.textContent, /only add fittings/i, 'resolution help must not duplicate safety context');
    }
    assert.equal(p.calls('fittings_start_copy').length, 0);
  });
}

test('unresolved copy conflicts keep labels, recovery instructions and review reason until checked', async () => {
  const p = await page();
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  const conflict = preflight();
  conflict.requires_resolution = true;
  conflict.write_count = 0;
  conflict.counts = { conflict: 1 };
  conflict.pairs[0].status = 'conflict';
  await reviewCopy(p, conflict);
  const body = p.el('fittings-copy-body');
  const row = body.querySelector('.fit-copy-pair');
  assert.equal(row.classList.contains('fit-copy-needs-resolution'), true);
  const alternate = row.querySelector('.fit-copy-alternate');
  const label = row.querySelectorAll('label').find(node => node.getAttribute('for') === alternate.id);
  assert.ok(label && label.textContent, 'alternate name has a persistent associated label');
  assert.match(row.textContent, /name.*skip/i);
  const review = p.el('fittings-copy-review');
  assert.equal(review.disabled, true);
  const reason = p.el(review.getAttribute('aria-describedby'));
  assert.ok(reason && !reason.hidden, 'disabled review exposes a visible reason');
  assert.match(reason.textContent, /name.*skip/i);
  input(alternate, '  ');
  assert.equal(review.disabled, true);
  input(alternate, 'Alternate tackle');
  assert.equal(review.disabled, false);
  assert.equal(label.textContent.length > 0, true, 'typing does not erase the field label');
  assert.match(body.textContent, /add.*fitting|existing fittings.*kept/i);
  review.click(); await flush();
  await settle(p.last('fittings_preflight_copy'), { accepted: false, error: 'Name already exists on Pilot.' });
  assert.equal(body.querySelector('.fit-copy-alternate').value, 'Alternate tackle');
  assert.match(p.el('fittings-copy-status').textContent, /Name already exists on Pilot/);
  assert.equal(p.el('fittings-copy-status').classList.contains('err'), true);
  const skip = body.querySelectorAll('input').find(node => node.type === 'checkbox');
  tick(skip);
  assert.equal(body.querySelector('.fit-copy-alternate').disabled, true);
  assert.equal(review.disabled, false);
  assert.match(p.el('fittings-copy-status').textContent, /Name already exists on Pilot/,
    'local choice editing must not discard rejected-review context');
  review.click(); await flush();
  assert.equal(p.last('fittings_preflight_copy').args[2]['fit-1:42'], null);
  await settle(p.last('fittings_preflight_copy'), preflight('resolved'));
  assert.equal(body.querySelector('.fit-copy-needs-resolution'), null);
  assert.equal(p.el('fittings-copy-status').classList.contains('err'), false);
  assert.equal(p.calls('fittings_start_copy').length, 0);
});

test('copy refusal error styling clears on checking, accepted review and reopening', async () => {
  const p = await page();
  await p.route('fittings');
  const workspace = state(['fit-1', 'fit-2', 'fit-3']);
  workspace.characters.push({ ...workspace.characters[0], character_id: 43, character_name: 'Second pilot' });
  await settle(p.last('fittings_state'), workspace);
  const error = '5 additions requested across all targets; limit 2 (3 over). Select fewer fittings or targets, then review again.';
  const refusal = { accepted: false, ticket_id: '', created_utc: '', write_count: 0,
    counts: { ready: 5, present: 1, conflict: 0, unavailable: 0 },
    requires_resolution: false, pairs: workspace.rows.flatMap(row => workspace.characters.map(character => ({
      ...preflight().pairs[0], entry_id: row.id, character_id: character.character_id,
      character_name: character.character_name,
      status: row.id === 'fit-1' && character.character_id === 42 ? 'present' : 'ready'
    }))), error };
  p.el('fittings-list').querySelectorAll('input').forEach(tick);
  p.el('fittings-copy-selected').click();
  p.el('fittings-copy-body').querySelectorAll('input').forEach(tick);
  p.el('fittings-copy-review').click(); await flush();
  await settle(p.last('fittings_preflight_copy'), refusal);
  assert.equal(p.el('fittings-list').querySelectorAll('input').filter(node => node.checked).length, 3);
  assert.equal(p.el('fittings-copy-body').querySelector('input').checked, true);
  assert.equal(p.el('fittings-copy-start').hidden, true);
  assert.equal(p.el('fittings-copy-review').disabled, false);
  const status = p.el('fittings-copy-status');
  assert.equal(status.classList.contains('err'), true, 'refusal must not look like ordinary guidance');
  assert.ok(status.textContent.includes(error), 'retain cap and recovery details');
  p.el('fittings-copy-review').click(); await flush();
  assert.equal(status.classList.contains('err'), false, 'checking is not a stale error');
  await settle(p.last('fittings_preflight_copy'), preflight());
  assert.equal(status.classList.contains('err'), false);
  p.el('fittings-copy-close').click();
  p.el('fittings-copy-selected').click();
  p.el('fittings-copy-body').querySelectorAll('input').forEach(tick);
  p.el('fittings-copy-review').click(); await flush();
  await settle(p.last('fittings_preflight_copy'), refusal);
  assert.equal(status.classList.contains('err'), true);
  p.el('fittings-copy-close').click();
  p.el('fittings-copy-selected').click();
  assert.equal(status.classList.contains('err'), false);
  assert.equal(status.textContent, '');
  assert.equal(p.calls('fittings_start_copy').length, 0);
});

test('active copy exposes cancellation boundary and retained copies before Cancel and through progress', async () => {
  const p = await editor();
  await beginCopy(p);
  const note = p.el('fittings-copy-cancel-note');
  assert.ok(note, 'the progress footer needs a dedicated cancellation note');
  assert.equal(note.hidden, false);
  assert.match(note.textContent, /current request/i);
  assert.match(note.textContent, /completed copies.*kept/i);
  assert.equal(p.calls('fittings_cancel_copy').length, 0, 'consequence is visible before cancelling');
  await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-1',
    completed: 1, total: 2, result: { ...preflight().pairs[0], status: 'success' } });
  assert.equal(note.hidden, false, 'pair progress cannot replace the cancellation note');
  p.el('fittings-copy-cancel').click(); await flush();
  assert.equal(note.hidden, false);
  assert.equal(p.calls('fittings_cancel_copy').length, 1);
  await complete(p, result(['success']));
  assert.equal(note.hidden, true, 'terminal results do not keep active-copy guidance');
  assert.deepEqual(p.errors, []);
});

test('copy identity distinguishes same-name hulls across pending refresh and conflict recheck', async () => {
  const p = await page();
  await p.route('fittings');
  const workspace = sameNameWorkspace();
  await settle(p.last('fittings_state'), workspace);
  await reviewCopy(p);
  const pending = p.last('fittings_preflight_copy');
  assert.deepEqual(Array.from(pending.args[0]), ['fit-1', 'fit-2']);
  assert.deepEqual(Array.from(pending.args[1]), [42]);
  // Mutate and re-render the supplied rows while review is pending. Neither a
  // retained row object nor a lookup against current STATE is a snapshot.
  workspace.rows.forEach(row => { row.ship_name = 'Changed hull'; });
  await p.changed({ reason: 'refresh' });
  await settle(p.last('fittings_state'), workspace);
  const review = sameNamePreflight();
  review.requires_resolution = true;
  review.counts = { ready: 1, conflict: 1 };
  review.pairs[1].status = 'conflict';
  await settle(pending, review);
  const body = p.el('fittings-copy-body');
  assert.deepEqual(body.querySelectorAll('.fit-copy-pair-name').map(n => n.textContent),
    ['Fleet tackle (Flycatcher)', 'Fleet tackle (Sabre)']);
  assert.deepEqual(body.querySelectorAll('.fit-copy-character').map(n => n.textContent),
    ['Pilot', 'Pilot']);
  assert.match(body.textContent, /Ready as.*Fleet tackle alternate/);
  const alternate = body.querySelector('.fit-copy-alternate');
  assert.match(alternate.getAttribute('aria-label'), /Fleet tackle.*Sabre.*Pilot/);
  input(alternate, 'Fleet tackle new');
  p.el('fittings-copy-review').click();
  await flush();
  assert.equal(p.last('fittings_preflight_copy').args[2]['fit-1:42'], 'Fleet tackle new');
  review.requires_resolution = false;
  review.pairs[1].status = 'ready';
  review.pairs[1].chosen_name = 'Fleet tackle new';
  await settle(p.last('fittings_preflight_copy'), review);
  assert.deepEqual(body.querySelectorAll('.fit-copy-pair-name').map(n => n.textContent),
    ['Fleet tackle (Flycatcher)', 'Fleet tackle (Sabre)']);
  assert.match(body.textContent, /Ready as.*Fleet tackle new/);
  assert.equal(p.calls('fittings_start_copy').length, 0);
  assert.deepEqual(p.errors, []);
});

test('copy identity survives filtering, progress and reopening results without new bridge calls', async () => {
  const p = await page();
  await p.route('fittings');
  await settle(p.last('fittings_state'), sameNameWorkspace());
  const review = sameNamePreflight();
  await reviewCopy(p, review);
  input(p.el('fittings-search'), 'other');
  await p.timers();
  await settle(p.last('fittings_state'), state(['other-fit']));
  await startReviewedCopy(p);
  const before = p.calls().length;
  const rows = review.pairs.map(pair => ({ ...pair, attempted: pair.status === 'ready',
    status: pair.status === 'ready' ? 'success' : 'present', error: '' }));
  for (const [index, row] of rows.entries()) {
    await p.progress({ kind: 'copy', phase: 'progress', ticket_id: review.ticket_id,
      completed: index + 1, total: 2, result: row });
    const status = p.el('fittings-copy-status').textContent;
    assert.match(status, index === 0 ? /Fleet tackle.*Flycatcher.*Pilot.*Copied/
      : /Fleet tackle.*Sabre.*Pilot.*Already present/);
    assert.equal(p.el('fittings-copy-summary').textContent,
      (index + 1) + ' of 2 fitting/character checks complete');
  }
  await complete(p, { status: 'complete', operation_id: 'op-identity', write_count: 1, results: rows });
  const body = p.el('fittings-copy-body');
  const labels = body.querySelectorAll('.fit-copy-pair-name').map(n => n.textContent);
  assert.deepEqual(labels, ['Fleet tackle (Flycatcher)', 'Fleet tackle (Sabre)']);
  assert.match(p.el('fittings-copy-summary').textContent, /1 copied.*1 already present/);
  assert.equal(p.calls().length, before);
  p.el('fittings-copy-close').click();
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.deepEqual(body.querySelectorAll('.fit-copy-pair-name').map(n => n.textContent), labels);
  assert.equal(p.calls().length, before);
  assert.deepEqual(p.errors, []);
});

test('copy identity uses known type IDs and never guesses hulls from matching names', async () => {
  const p = await page();
  await p.route('fittings');
  const workspace = state();
  workspace.rows[0].ship_name = '';
  await settle(p.last('fittings_state'), workspace);
  const review = preflight();
  review.pairs.push({ ...review.pairs[0], entry_id: 'not-selected' });
  await reviewCopy(p, review);
  const names = p.el('fittings-copy-body').querySelectorAll('.fit-copy-pair-name');
  assert.equal(names[0].textContent, 'Sabre tackle (Type 22456)');
  assert.equal(names[1].textContent, 'Sabre tackle');
  await startReviewedCopy(p);
  await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-1',
    completed: 1, total: 2, result: { entry_id: 'not-selected', character_id: 99, status: 'unknown' } });
  assert.match(p.el('fittings-copy-status').textContent, /Fitting not-selected.*Character 99.*Needs verification/);
  assert.doesNotMatch(p.el('fittings-copy-status').textContent, /Sabre|22456|undefined|NaN/);
  await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-1',
    completed: 2, total: 2, result: { status: 'present' } });
  assert.equal(p.el('fittings-copy-status').textContent, '2 of 2 fitting/character checks complete · Already present',
    'identity-free events must not borrow identity from the last pair');
});

test('copy identity labels remain literal text for long markup-like names', async () => {
  const p = await page();
  await p.route('fittings');
  const workspace = state();
  const name = '<img src=x onerror=alert(1)>' + 'LongName'.repeat(20);
  workspace.rows[0].name = name;
  workspace.rows[0].ship_name = '<b>Sabre</b>';
  await settle(p.last('fittings_state'), workspace);
  const review = preflight();
  review.pairs[0].fitting_name = name;
  review.pairs[0].character_name = '<script>Pilot</script>';
  await reviewCopy(p, review);
  const label = p.el('fittings-copy-body').querySelector('.fit-copy-pair-name');
  assert.equal(label.textContent, name + ' (<b>Sabre</b>)');
  assert.equal(label.children.length, 0);
  await startReviewedCopy(p);
  await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-1',
    completed: 1, total: 1, result: { ...review.pairs[0], status: 'success' } });
  const status = p.el('fittings-copy-status');
  assert.ok(status.textContent.includes(name + ' (<b>Sabre</b>)'));
  assert.ok(status.textContent.includes('<script>Pilot</script>'));
  assert.equal(status.children.length, 0);
});

for (const [count, outcomeSummary] of [
  [0, '3 not copied · 4 already present'],
  [1, '1 needs verification · 4 not copied · 4 already present'],
  [2, '2 need verification · 5 not copied · 4 already present']
]) {
  test(`copy counts ${count} distinguish plans, fitting/character checks, attempts and copied outcomes`, async () => {
    const p = await page();
    await p.route('fittings');
    await settle(p.last('fittings_state'), state());
    const review = preflight();
    review.write_count = count;
    review.counts = { ready: count, conflict: count, present: 4, unavailable: 3 };
    review.pairs = [...Array(count).fill('ready'), ...Array(count).fill('conflict'),
      ...Array(4).fill('present'), ...Array(3).fill('unavailable')].map((status, index) => ({
        ...preflight().pairs[0], character_id: 100 + index, character_name: 'Pilot ' + index,
        status, skipped: status === 'conflict'
      }));
    await reviewCopy(p, review);
    const body = p.el('fittings-copy-body');
    const summary = p.el('fittings-copy-summary').textContent;
    assert.match(summary, new RegExp('^' + count + (count === 1 ? ' addition planned' : ' additions planned')));
    assert.match(summary, new RegExp('\\b' + count + (count === 1 ? ' conflict\\b(?!s)' : ' conflicts\\b')));
    assert.match(summary, /4 already present.*3 unavailable/);
    assert.doesNotMatch(summary, /remote write|copied|attempted|checked/);
    await startReviewedCopy(p);
    const total = count * 2 + 7;
    assert.equal(p.el('fittings-copy-summary').textContent, '0 of ' + total + ' fitting/character checks complete');
    const results = review.pairs.map(pair => ({ ...pair, attempted: pair.status === 'ready',
      status: pair.status === 'ready' ? 'unknown' : pair.skipped ? 'conflict_skipped' : pair.status }));
    await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-1',
      completed: 1, total, result: results[0] });
    assert.equal(p.el('fittings-copy-summary').textContent, '1 of ' + total + ' fitting/character checks complete');
    await complete(p, { status: 'complete', write_count: count, results });
    const completed = p.el('fittings-copy-summary').textContent;
    assert.equal(completed, outcomeSummary);
    assert.match(body.querySelector('.hint').textContent,
      new RegExp('^' + count + (count === 1 ? ' addition attempted' : ' additions attempted')));
    assert.doesNotMatch(body.textContent, /remote write|addition[s]? planned/);
    assert.match(body.textContent, /Nothing is retried automatically/);
  });
}

test('copy identity ignores stale and out-of-ticket progress after a newer copy starts', async () => {
  const p = await page();
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  await beginCopy(p);
  await p.route('main');
  await p.route('fittings');
  const workspace = state();
  workspace.rows[0].ship_name = 'Flycatcher';
  workspace.rows[0].ship_type_id = 22464;
  await settle(p.last('fittings_state'), workspace);
  await beginCopy(p, 'ticket-2');
  const current = { ...preflight('ticket-2').pairs[0], status: 'unknown' };
  await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-2',
    completed: 1, total: 1, result: current });
  const status = p.el('fittings-copy-status').textContent;
  assert.match(status, /Sabre tackle.*Flycatcher.*Pilot.*Needs verification/);
  const body = p.el('fittings-copy-body').textContent;
  for (const ticket of ['ticket-1', 'unrelated-ticket', undefined]) {
    await p.progress({ kind: 'copy', phase: 'progress', ticket_id: ticket,
      completed: 99, total: 99, result: { ...current, fitting_name: 'Wrong fitting', status: 'success' } });
    assert.equal(p.el('fittings-copy-status').textContent, status);
    assert.equal(p.el('fittings-copy-body').textContent, body);
  }
  await p.route('main');
  await complete(p, { status: 'cancelled', write_count: 1, results: [current] }, 'ticket-2');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state(['other-fit']));
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-body').querySelector('.fit-copy-pair-name').textContent,
    'Sabre tackle (Flycatcher)', 'off-route results retain their own submitted hull snapshot');
  assert.deepEqual(p.errors, []);
});

async function beginCopy(p, ticket = 'ticket-1', acknowledge = true) {
  const selected = p.el('fittings-list').querySelector('input');
  selected.checked = true;
  selected.dispatchEvent({ type: 'change' });
  p.el('fittings-copy-selected').click();
  tick(p.el('fittings-copy-body').querySelector('input'));
  p.el('fittings-copy-review').click();
  await flush();
  await settle(p.last('fittings_preflight_copy'), preflight(ticket));
  p.el('fittings-copy-start').click();
  await settle(p.confirmations.at(-1), true);
  if (acknowledge) await settle(p.last('fittings_start_copy'), true);
}
function result(statuses) {
  return { status: 'complete', operation_id: 'op-1', write_count: 3,
    results: statuses.map(status => ({ fitting_name: 'Fit ' + status,
      character_name: 'Pilot', status, error: '',
      attempted: ['success', 'failed', 'unknown'].includes(status) })) };
}
async function complete(p, value, ticket = 'ticket-1') {
  await p.progress({ kind: 'copy', phase: 'complete', ticket_id: ticket, result: value });
}

test('mixed copy results summarize outcomes and give status-specific safe next steps', async () => {
  const p = await editor();
  await beginCopy(p);
  const before = p.calls().length;
  await complete(p, result(['success', 'present', 'conflict_skipped', 'failed',
                            'unknown', 'unattempted_throttle', 'cancelled', 'unavailable']));
  const body = p.el('fittings-copy-body');
  const summary = p.el('fittings-copy-summary').textContent;
  assert.equal(summary, '1 needs verification · 1 failed · 4 not copied · 1 copied · 1 already present');
  const pairs = body.querySelectorAll('.fit-copy-pair');
  const expectations = [
    /Copied/, /Already present/, /alternate name.*review/i,
    /error.*refresh.*review/i, /Needs verification/i,
    /not attempted.*rate limit/i, /not attempted.*review/i, /refresh.*review/i
  ];
  pairs.forEach((pair, index) => assert.match(pair.textContent, expectations[index]));
  assert.doesNotMatch(pairs[0].textContent, /No action needed/i);
  assert.doesNotMatch(pairs[1].textContent, /No action needed/i);
  assert.match(body.textContent, /before.*retry.*check.*target.*EVE.*refresh/i);
  assert.match(body.textContent, /rate limit.*wait.*refresh.*review/i);
  assert.equal(p.calls().length, before, 'displaying advice must not issue any operation');
  assert.equal(body.querySelector('button'), null, 'no automatic retry control');
});

for (const [statuses, expected] of [
  [[], 'No copy results.'],
  [['success'], '1 copied'],
  [['present', 'present'], '2 already present'],
  [['unknown'], '1 needs verification'],
  [['unknown', 'unknown'], '2 need verification'],
  [['failed'], '1 failed'],
  [['cancelled', 'unavailable', 'future_status'], '3 not copied']
]) {
  test(`copy outcome summary omits absent categories: ${expected}`, async () => {
    const p = await editor();
    await beginCopy(p);
    const before = p.calls().length;
    await complete(p, result(statuses));
    const body = p.el('fittings-copy-body');
    assert.equal(p.el('fittings-copy-summary').textContent, expected);
    assert.equal(body.querySelectorAll('.fit-copy-pair').length, statuses.length);
    assert.equal(p.calls().length, before, 'summarizing must not issue operations');
    assert.match(body.textContent, /Nothing is retried automatically/);
  });
}

for (const operationStatus of ['complete', 'throttled']) {
  test(`repeated ${operationStatus} copy recovery is shared without losing fitting, hull, target or error`, async () => {
    const p = await page();
    await p.route('fittings');
    await settle(p.last('fittings_state'), sameNameWorkspace());
    const review = sameNamePreflight();
    await reviewCopy(p, review);
    await startReviewedCopy(p);
    const rows = ['unknown', 'unknown', 'failed', 'unattempted_throttle', 'unattempted_throttle'].map((status, index) => ({
      ...review.pairs[index % 2], character_name: 'Target ' + index, status,
      error: 'Reason ' + index, attempted: ['unknown', 'failed'].includes(status)
    }));
    const before = p.calls().length;
    await complete(p, { status: operationStatus, operation_id: '', write_count: 3, results: rows });
    const body = p.el('fittings-copy-body');
    const recovery = body.querySelector('.fit-copy-recovery');
    assert.ok(recovery, 'shared advice has one scroll-persistent group inside the existing body');
    assert.equal(recovery.parentNode, body, 'recovery stays within the dialog scroll budget');
    assert.equal(body.querySelectorAll('.fit-copy-recovery').length, 1);
    const guidance = recovery.querySelectorAll('.fit-copy-guidance');
    assert.equal(guidance.length, 2, 'one verification and one rate-limit recovery, not one per row');
    assert.ok(guidance.every(node => node.classList.contains('hint') && node.classList.contains('operational-status')));
    assert.ok(body.children.indexOf(recovery) < body.children.indexOf(body.querySelector('.fit-copy-pair')));
    assert.equal(p.focused(), p.el('fittings-copy-close'), 'results retain their Close focus owner');
    assert.match(guidance[0].textContent, /verification.*before.*retry.*Personal Fittings.*EVE.*refresh/i);
    assert.match(guidance[0].textContent, /may already exist/i);
    assert.match(guidance[1].textContent, /rate limit.*wait.*refresh.*review/i);
    const rendered = body.querySelectorAll('.fit-copy-pair');
    assert.equal(rendered.length, 5);
    rendered.forEach((row, index) => {
      assert.equal(row.querySelector('.fit-copy-pair-name').textContent,
        'Fleet tackle (' + (index % 2 ? 'Sabre' : 'Flycatcher') + ')');
      assert.equal(row.querySelector('.fit-copy-character').textContent, 'Target ' + index);
      assert.ok(row.textContent.includes('Reason ' + index));
      assert.match(row.querySelector('.fit-copy-result').textContent,
        index < 2 ? /Needs verification/ : index === 2 ? /Failed/ : /Not attempted.*rate limit/i);
      if (index === 2) assert.match(row.querySelector('.fit-copy-guidance').textContent, /error.*refresh/i);
      else assert.equal(row.querySelector('.fit-copy-guidance'), null);
    });
    assert.equal(body.querySelectorAll('.notice').length, 0, 'operation rate limit does not duplicate recovery');
    assert.equal(p.calls().length, before, 'rendering recovery never retries an uncertain copy');
    assert.equal(body.querySelector('button'), null);
  });
}

test('shared recovery resets with each result and copy phase without bridge or focus side effects', async () => {
  const p = await editor();
  const body = p.el('fittings-copy-body');
  const cases = [
    {statuses: ['unattempted_throttle', 'unknown', 'unknown'], count: 2},
    {statuses: ['unknown'], count: 1, first: /Needs verification/},
    {statuses: ['success'], count: 0},
    {statuses: [], status: 'throttled', count: 1, first: /Rate limit/}
  ];
  for (const [index, item] of cases.entries()) {
    const ticket = 'recovery-' + index;
    await beginCopy(p, ticket);
    assert.equal(body.querySelector('.fit-copy-recovery'), null, 'progress retires previous recovery');
    const before = p.calls().length;
    const outcome = result(item.statuses);
    if (item.status) outcome.status = item.status;
    await complete(p, outcome, ticket);
    const recovery = body.querySelector('.fit-copy-recovery');
    assert.equal(recovery?.children.length || 0, item.count);
    if (!item.count) assert.equal(recovery, null, 'no empty sticky surface on ordinary results');
    if (item.first) assert.match(recovery.children[0].textContent, item.first);
    if (item.count === 2) {
      assert.match(recovery.children[0].textContent, /Needs verification/);
      assert.match(recovery.children[1].textContent, /Rate limit/);
    }
    assert.equal(p.focused(), p.el('fittings-copy-close'));
    body.focus(); body.scrollTop = 200;
    await p.progress({kind: 'copy', phase: 'progress', ticket_id: 'obsolete', completed: 1, total: 1});
    assert.equal(p.focused(), body, 'stale pushes do not move the result reader');
    assert.equal(body.scrollTop, 200);
    assert.equal(body.querySelector('.fit-copy-recovery'), recovery);
    assert.equal(p.calls().length, before);
    p.el('fittings-copy-close').click();
    button(p.el('fittings-notices'), 'Last copy results\u2026').click();
    assert.equal(body.querySelector('.fit-copy-recovery')?.children.length || 0, item.count, 'reopening does not duplicate recovery');
    assert.equal(p.calls().length, before);
    p.el('fittings-copy-close').click();
  }
  assert.deepEqual(p.errors, []);
});

test('last results reopen session-only, with no preflight/start and no stale ticket interference', async () => {
  const p = await editor();
  assert.doesNotMatch(p.el('fittings-notices').textContent, /Last copy results/);
  await beginCopy(p);
  await complete(p, result(['unknown']));
  p.el('fittings-copy-close').click();
  const before = p.calls().length;
  const reopen = button(p.el('fittings-notices'), 'Last copy results\u2026');
  reopen.click();
  assert.equal(p.el('fittings-copy-overlay').hidden, false);
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
  assert.equal(p.el('fittings-copy-start').hidden, true);
  assert.equal(p.el('fittings-copy-review').hidden, true);
  assert.equal(p.calls().length, before);
  p.el('fittings-copy-close').click();
  await beginCopy(p, 'ticket-2');
  assert.ok(reopen.disabled || !p.el('fittings-notices').contains(reopen));
  // Even a detached old button must not switch the active copy to old results.
  reopen.click();
  await complete(p, result(['success']), 'ticket-1');
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
  assert.equal(p.calls('fittings_start_copy').length, 2);
  assert.deepEqual(p.last('fittings_start_copy').args, ['ticket-2']);
  await complete(p, result(['present']), 'ticket-2');
  p.el('fittings-copy-close').click();
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.match(p.el('fittings-copy-body').textContent, /Already present/);
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 0);
  assert.equal(p.calls('fittings_cancel_copy').length, 0);
  const fresh = await page();
  await fresh.route('fittings');
  await settle(fresh.last('fittings_state'), state());
  assert.doesNotMatch(fresh.el('fittings-notices').textContent, /Last copy results/);
});

for (const terminal of ['complete', 'cancelled']) {
  test(`off-route ${terminal} retains the latest copy outcome before its start acknowledgement`, async () => {
    const p = await editor();
    await beginCopy(p, 'ticket-a');
    const first = result(['success']);
    first.operation_id = 'operation-a';
    await complete(p, first, 'ticket-a');
    p.el('fittings-copy-close').click();
    await beginCopy(p, 'ticket-b', false);
    const start = p.last('fittings_start_copy');
    await p.route('main');
    assert.deepEqual(p.last('fittings_cancel_copy').args, ['ticket-b']);
    const title = p.el('fittings-copy-title').textContent;
    const body = p.el('fittings-copy-body').textContent;
    const latest = result(['unknown', 'cancelled']);
    latest.status = terminal;
    latest.operation_id = 'operation-b';
    latest.write_count = 1;
    await complete(p, latest, 'ticket-b');
    await settle(start, true);
    // Neither stale operations nor duplicate delivery can replace the accepted result.
    await complete(p, first, 'ticket-a');
    await complete(p, first, 'unrelated-ticket');
    await complete(p, first, 'ticket-b');
    assert.equal(p.el('fittings-copy-overlay').hidden, true);
    assert.equal(p.el('fittings-copy-title').textContent, title);
    assert.equal(p.el('fittings-copy-body').textContent, body);
    await p.route('fittings');
    await settle(p.last('fittings_state'), state());
    const before = p.calls().length;
    button(p.el('fittings-notices'), 'Last copy results\u2026').click();
    assert.equal(p.el('fittings-copy-overlay').hidden, false);
    assert.equal(p.el('fittings-copy-operation-id').textContent, 'Operation ID: operation-b');
    assert.equal(p.el('fittings-copy-status').textContent, '1 needs verification · 1 not copied');
    assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
    assert.match(p.el('fittings-copy-body').textContent, /check.*target.*refresh/is);
    assert.match(p.el('fittings-copy-body').textContent, /Cancelled/);
    assert.equal(p.calls().length, before, 'reopening must not issue another operation');
    assert.equal(p.calls('fittings_start_copy').length, 2);
    assert.equal(p.calls('fittings_cancel_copy').length, 1);
    assert.deepEqual(p.errors, []);
  });
}

test('return during cancellation keeps old history unavailable until the matching result arrives', async () => {
  const p = await editor();
  await beginCopy(p, 'ticket-a');
  await complete(p, result(['success']), 'ticket-a');
  p.el('fittings-copy-close').click();
  await beginCopy(p, 'ticket-b');
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  const reopen = button(p.el('fittings-notices'), 'Last copy results\u2026');
  assert.equal(reopen.disabled, true);
  reopen.click();
  assert.equal(p.el('fittings-copy-overlay').hidden, true);
  await complete(p, result(['unknown']), 'ticket-b');
  assert.equal(p.el('fittings-copy-overlay').hidden, true);
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
  assert.equal(p.calls('fittings_cancel_copy').length, 1);
});

test('late background completion cannot replace a newer started copy or its final history', async () => {
  const p = await editor();
  await beginCopy(p, 'ticket-a');
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  await beginCopy(p, 'ticket-b');
  const currentBody = p.el('fittings-copy-body').textContent;
  await complete(p, result(['unknown']), 'ticket-a');
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
  assert.equal(p.el('fittings-copy-body').textContent, currentBody);
  const latest = result(['present']);
  latest.operation_id = 'operation-b';
  await complete(p, latest, 'ticket-b');
  p.el('fittings-copy-close').click();
  await p.route('main');
  await complete(p, result(['unknown']), 'ticket-a');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-operation-id').textContent, 'Operation ID: operation-b');
  assert.equal(p.el('fittings-copy-status').textContent, '1 already present');
  assert.match(p.el('fittings-copy-body').textContent, /Already present/);
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 0);
});

test('a refused start releases history availability but its later failure push remains eligible', async () => {
  const p = await editor();
  await beginCopy(p, 'ticket-a');
  await complete(p, result(['success']), 'ticket-a');
  p.el('fittings-copy-close').click();
  await beginCopy(p, 'ticket-b', false);
  const refused = p.last('fittings_start_copy');
  await p.route('main');
  await settle(refused, false);
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  assert.equal(button(p.el('fittings-notices'), 'Last copy results\u2026').disabled, false);
  // A worker-start failure can publish its terminal push after the boolean reply.
  await complete(p, { status: 'failed', operation_id: '', results: [], write_count: 0 }, 'ticket-b');
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-status').textContent, 'Failed');
});

test('an older start refusal cannot release the history guard of a newer pending copy', async () => {
  const p = await editor();
  await beginCopy(p, 'ticket-a');
  await complete(p, result(['success']), 'ticket-a');
  p.el('fittings-copy-close').click();
  await beginCopy(p, 'ticket-b', false);
  const olderStart = p.last('fittings_start_copy');
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  await beginCopy(p, 'ticket-c', false);
  await p.route('main');
  await settle(olderStart, false);
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  assert.equal(button(p.el('fittings-notices'), 'Last copy results\u2026').disabled, true);
  await complete(p, result(['unknown']), 'ticket-c');
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
  assert.deepEqual(p.errors, []);
});

for (const outcome of ['null', 'reject']) {
  test(`uncertain ${outcome} start reply still accepts the off-route terminal outcome`, async () => {
    const p = await editor();
    await beginCopy(p, 'ticket-a');
    await complete(p, result(['success']), 'ticket-a');
    p.el('fittings-copy-close').click();
    await beginCopy(p, 'ticket-b', false);
    const start = p.last('fittings_start_copy');
    await p.route('main');
    if (outcome === 'reject') start.reject(new Error('injected start reply failure'));
    else start.resolve(null);
    await flush();
    await p.route('fittings');
    await settle(p.last('fittings_state'), state());
    assert.equal(button(p.el('fittings-notices'), 'Last copy results\u2026').disabled, true);
    await complete(p, result(['unknown']), 'ticket-b');
    button(p.el('fittings-notices'), 'Last copy results\u2026').click();
    assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
    assert.equal(p.errors.length, outcome === 'reject' ? 1 : 0);
  });
}

function devScreenshot(stage) {
  const source = fs.readFileSync(path.join(web, 'dev.js'), 'utf8');
  const start = source.indexOf('  var DEV_FITTINGS_SCREENSHOT_FIXTURE =');
  const end = source.indexOf('  fittings.max_copy_writes =', start);
  const fixture = vm.runInNewContext(source.slice(start, end) + '\nDEV_FITTINGS_SCREENSHOT_FIXTURE;');
  if (stage) fixture.copy_stage = stage;
  return fixture;
}

test('refused screenshot injection and cleanup never cancel a genuine submitted copy', async () => {
  const p = await editor();
  await reviewCopy(p, preflight());
  await startReviewedCopy(p);
  const before = p.calls().length;
  await p.screenshot(devScreenshot('progress'));
  await p.screenshot({kind: 'fittings-screenshot-v1', clear: true});
  assert.match(p.el('fittings-copy-summary').textContent, /0 of 1 fitting\/character check complete/);
  assert.equal(p.el('fittings-copy-overlay').hidden, false);
  assert.equal(p.calls().length, before, 'refused cleanup cannot leave the real route or cancel');
  await complete(p, result(['success']));
  assert.match(p.el('fittings-copy-summary').textContent, /1 copied/);
});

test('a confirmation begun before fixture injection cannot start after fixture teardown', async () => {
  const p = await editor();
  await reviewCopy(p, preflight());
  p.el('fittings-copy-start').click();
  const confirmation = p.confirmations.at(-1);
  const before = p.calls().length;
  await p.screenshot(devScreenshot('progress'));
  await p.screenshot({kind: 'fittings-screenshot-v1', clear: true});
  await settle(confirmation, true);
  assert.equal(p.calls().length, before);
  assert.equal(p.el('fittings-copy-overlay').hidden, true);
});

test('screenshot review counts classified ready pairs, not present or unavailable selections', async () => {
  const p = await page();
  await p.route('fittings');
  await p.screenshot(devScreenshot());
  const before = p.calls().length;
  p.el('fittings-list').querySelectorAll('.fit-row').forEach(row => {
    const name = row.querySelector('.fit-name').textContent;
    if (/Generated Fit 00[123]/.test(name)
        || (name === 'Fleet Doctrine Alpha' && /^On 1 character/.test(row.querySelector('.fit-meta').textContent))) {
      tick(row.querySelector('input'));
    }
  });
  p.el('fittings-copy-selected').click();
  const target = p.el('fittings-copy-body').querySelectorAll('.fit-copy-target')
    .find(row => row.textContent === 'Eryn Voss');
  tick(target.querySelector('input'));
  p.el('fittings-copy-review').click(); await flush();
  assert.match(p.el('fittings-copy-summary').textContent, /2 additions planned.*1 already present.*1 unavailable/);
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.fit-copy-pair').length, 4);
  assert.equal(p.calls().length, before);
});

for (const [count, limit, requested, excess] of [[11, 20, 22, 2], [10, 7, 20, 13], [11, 7, 22, 15]]) {
  test(`screenshot cap refusal counts ${count} selected fits against the current ${limit} limit`, async () => {
    const p = await page();
    await p.route('fittings');
    const fixture = devScreenshot();
    fixture.max_copy_writes = limit;
    await p.screenshot(fixture);
    const before = p.calls().length;
    const selected = p.el('fittings-list').querySelectorAll('.fit-row').filter(row => {
      const name = row.querySelector('.fit-name').textContent;
      const number = Number(name.match(/^Generated Fit (\d+)$/)?.[1]);
      return number >= 2 && number <= count + 1;
    });
    assert.equal(selected.length, count);
    selected.forEach(row => tick(row.querySelector('input')));
    p.el('fittings-copy-selected').click();
    const body = p.el('fittings-copy-body');
    body.querySelectorAll('.fit-copy-target').forEach(row => {
      if (['Eryn Voss', 'Fio Kest'].includes(row.textContent)) tick(row.querySelector('input'));
    });
    p.el('fittings-copy-review').click(); await flush();
    const error = p.el('fittings-copy-status').textContent;
    assert.match(error, new RegExp(requested + ' additions requested'));
    assert.match(error, new RegExp('limit ' + limit + '\\b'));
    assert.match(error, new RegExp(excess + ' over'));
    if (count === 11 && limit === 20) assert.equal(error, fixture.limit_preflight.error);
    assert.equal(selected.every(row => row.querySelector('input').checked), true);
    assert.equal(body.querySelectorAll('input').filter(node => node.checked).length, 2);
    assert.equal(p.el('fittings-copy-start').hidden, true);
    assert.equal(p.el('fittings-copy-review').disabled, false);
    assert.equal(p.calls().length, before, 'synthetic refusal cannot call the real bridge');
  });
}

test('tooling-only screenshot results do not become real session history', async () => {
  const p = await editor();
  const fixtureState = state(Array.from({ length: 21 }, (_, index) => 'fixture-' + index));
  const outcome = result(['unknown']);
  outcome.results[0].entry_id = 'fixture-0';
  await p.screenshot({ kind: 'fittings-screenshot-v1', characters: fixtureState.characters,
    collections: fixtureState.collections, entries: fixtureState.rows, details: {},
    mixed_preflight: { pairs: [] }, copy_result: outcome, copy_stage: 'results' });
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  assert.doesNotMatch(p.el('fittings-notices').textContent, /Last copy results/);
  assert.equal(p.calls('fittings_start_copy').length, 0);
  assert.equal(p.calls('fittings_cancel_copy').length, 0);
});

test('a screenshot fixture cannot prune genuine unsaved metadata', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Real draft');
  const fixtureState = state(Array.from({ length: 21 }, (_, index) => 'fixture-' + index));
  await p.screenshot({ kind: 'fittings-screenshot-v1', characters: fixtureState.characters,
    collections: fixtureState.collections, entries: fixtureState.rows, details: {},
    mixed_preflight: { pairs: [] }, copy_result: { results: [] } });
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  await settle(p.last('fittings_detail'), detail());
  assertDraft(p, 'Real draft', 'Saved description');
});

test('partial cancellation does not describe the whole operation as unattempted', async () => {
  const p = await editor();
  await beginCopy(p);
  const value = result(['success', 'cancelled']);
  value.status = 'cancelled';
  value.write_count = 1;
  await complete(p, value);
  const body = p.el('fittings-copy-body');
  assert.equal(p.el('fittings-copy-summary').textContent, '1 not copied · 1 copied');
  const operationNotice = body.querySelector('.notice');
  assert.ok(!operationNotice || !/Not attempted/.test(operationNotice.textContent));
  assert.match(body.querySelectorAll('.fit-copy-pair')[1].textContent, /Not attempted/);
});

test('non-deployable status is separate from truncating row metadata', async () => {
  const p = await page();
  await p.route('fittings');
  const payload = state(['fit-1', 'fit-2']);
  payload.rows[0].deployable = false;
  payload.rows[0].collection_ids = ['doctrine'];
  payload.rows[0].ship_name = '';
  payload.rows[0].name = 'A long doctrine name that must not hide deployment status';
  await settle(p.last('fittings_state'), payload);
  const rows = p.el('fittings-list').querySelectorAll('.fit-row');
  const status = rows[0].querySelector('.fit-deployability');
  assert.ok(status, 'deployment status needs its own visible element');
  assert.match(status.textContent, /Cannot copy.*Details/i);
  assert.equal(status.tagName, 'BUTTON', 'the restriction has a keyboard-usable route to details');
  assert.equal(status.hidden, false);
  assert.equal(rows[0].querySelector('.fit-meta').contains(status), false);
  assert.doesNotMatch(rows[0].querySelector('.fit-meta').textContent, /Not deployable/i);
  assert.match(rows[0].querySelector('.fit-ship').textContent, /Type 22456/);
  assert.equal(rows[1].querySelector('.fit-deployability'), null);
  status.click(); await flush();
  await settle(p.last('fittings_detail'), detail());
  assert.equal(p.el('fittings-list').querySelector('.fit-row-toggle').getAttribute('aria-expanded'), 'true');
  assert.match(p.el('fittings-list').querySelector('.fit-detail').textContent, /cannot be copied safely/i);
  assert.equal(p.calls('fittings_preflight_copy').length, 0);
  assert.deepEqual(p.errors, []);
});

for (const limit of [7, undefined]) {
  test(`copy limit ${limit} is advisory before review, never a raw-selection gate`, async () => {
    const p = await page();
    await p.route('fittings');
    const payload = state(Array.from({ length: 21 }, (_, index) => 'fit-' + index));
    if (limit !== undefined) payload.max_copy_writes = limit;
    payload.characters.push({ ...payload.characters[0], character_id: 43, character_name: 'Second pilot' });
    await settle(p.last('fittings_state'), payload);
    p.el('fittings-list').querySelectorAll('input').forEach(tick);
    p.el('fittings-copy-selected').click();
    const body = p.el('fittings-copy-body');
    const advisory = body.querySelector('.fit-copy-limit');
    if (limit !== undefined) {
      assert.ok(advisory, 'show the controller limit before Review');
      assert.match(advisory.textContent, /7.*additions.*across.*targets/i);
      assert.match(advisory.textContent, /review.*new additions/i);
    } else {
      assert.equal(advisory, null, 'missing metadata must not invent a numeric limit');
    }
    assert.doesNotMatch(body.textContent, /undefined|NaN/);
    assert.equal(p.el('fittings-copy-review').disabled, true);
    const targets = body.querySelectorAll('input');
    tick(targets[0]);
    tick(targets[1]);
    assert.equal(p.el('fittings-copy-review').disabled, false);
    p.el('fittings-copy-review').click();
    await flush();
    assert.equal(p.last('fittings_preflight_copy').args[0].length, 21);
    assert.deepEqual(Array.from(p.last('fittings_preflight_copy').args[1]), [42, 43]);
    await settle(p.last('fittings_preflight_copy'), preflight());
    assert.equal(p.el('fittings-copy-start').hidden, false);
    assert.equal(p.calls('fittings_start_copy').length, 0);
    assert.deepEqual(p.errors, []);
  });
}

test('unavailable preflight pairs retain diagnosis, distinct status and a selection recovery route', async () => {
  const p = await editor();
  const review = preflight();
  review.counts = { ready: 1, present: 1, conflict: 0, unavailable: 2 };
  const pair = review.pairs[0];
  review.pairs = [pair,
    { ...pair, character_id: 43, status: 'present' },
    { ...pair, character_id: 44, status: 'unavailable', error: 'Refresh fittings to reconcile an earlier copy.' },
    { ...pair, character_id: 45, status: 'unavailable', error: '' }];
  await reviewCopy(p, review);
  const body = p.el('fittings-copy-body');
  const rows = body.querySelectorAll('.fit-copy-pair');
  assert.equal(rows[1].querySelector('.fit-copy-detail').textContent, 'Already present');
  for (const row of rows.slice(2)) {
    assert.match(row.querySelector('.fit-copy-detail').textContent, /^Unavailable\b/);
    assert.equal(row.classList.contains('fit-copy-unavailable'), true);
  }
  assert.match(rows[2].textContent, /Refresh fittings to reconcile an earlier copy\./);
  assert.doesNotMatch(rows[3].textContent, /authenticate|capacity|timeout/i, 'missing diagnostics must not invent a cause');
  assert.equal(rows[1].classList.contains('fit-copy-unavailable'), false);
  assert.match(p.el('fittings-copy-unavailable-note').textContent, /Close.*fittings.*target characters/i);
  assert.match(p.el('fittings-copy-summary').textContent, /1 addition planned.*1 already present.*2 unavailable/);
  assert.equal(p.el('fittings-copy-start').hidden, false);
  assert.equal(p.calls('fittings_start_copy').length, 0, 'rendering guidance never starts a copy');
  assert.equal(p.calls('fittings_preflight_copy').length, 1, 'guidance does not reclassify or recheck pairs');
});

test('ready preflight does not show unavailable-pair recovery guidance', async () => {
  const p = await editor();
  await reviewCopy(p, preflight());
  assert.equal(p.el('fittings-copy-body').querySelector('.fit-copy-unavailable'), null);
  assert.equal(p.el('fittings-copy-body').textContent.includes('Close this review to change'), false);
});

test('unavailable copy targets point to authentication or refresh without changing eligibility', async () => {
  const p = await page();
  await p.route('fittings');
  const payload = state();
  payload.characters = [
    { ...payload.characters[0], status: 'enable' },
    { ...payload.characters[0], character_id: 43, status: 'reauthenticate' },
    { ...payload.characters[0], character_id: 44, fetched_utc: '' },
    { ...payload.characters[0], character_id: 45, stale: true }
  ];
  await settle(p.last('fittings_state'), payload);
  tick(p.el('fittings-list').querySelector('input'));
  p.el('fittings-copy-selected').click();
  const targets = p.el('fittings-copy-body').querySelectorAll('.fit-copy-target');
  targets.forEach(target => assert.equal(target.querySelector('input').disabled, true));
  for (const target of targets.slice(0, 2)) {
    assert.match(target.textContent, /Authenticate character.*Settings.*Character access/i);
    assert.doesNotMatch(target.textContent, /enable Fittings|Fittings not enabled/i);
  }
  for (const target of targets.slice(2)) assert.match(target.textContent, /Refresh characters/);
  assert.equal(p.el('fittings-copy-review').disabled, true);
  assert.equal(p.calls('fittings_preflight_copy').length, 0);
});

test('copy recovery labels keep semantic outcomes and point to real authentication', async () => {
  const p = await editor();
  await beginCopy(p);
  const value = result(['success', 'unknown', 'unattempted_throttle', 'unavailable']);
  value.results[1].error = 'The request timed out before a response arrived.';
  const before = p.calls().length;
  await complete(p, value);
  const body = p.el('fittings-copy-body');
  const labels = body.querySelectorAll('.fit-copy-result');
  assert.equal(labels[0].textContent, 'Copied');
  assert.equal(labels[1].textContent, 'Needs verification');
  assert.equal(labels[1].classList.contains('unknown'), true);
  assert.match(labels[2].textContent, /Not attempted.*rate limit/i);
  assert.equal(labels[2].classList.contains('unattempted_throttle'), true);
  assert.match(p.el('fittings-copy-summary').textContent, /1 needs verification/);
  const rows = body.querySelectorAll('.fit-copy-pair');
  assert.match(rows[1].textContent, /request timed out/);
  assert.match(body.querySelector('.fit-copy-guidance').textContent, /before.*retry.*Personal Fittings.*EVE.*refresh/i);
  assert.match(rows[3].querySelector('.fit-copy-guidance').textContent, /Authenticate character.*Settings.*Character access/);
  assert.equal(p.calls().length, before);
  assert.equal(body.querySelector('button'), null);
});

// Step 9: presentation facts must follow the accepted operation, never current
// selection, counts of writes, hull keys, or a later setup's mutable controls.
async function copySetup(ids = ['fit-1'], characters) {
  const p = await page(); await p.route('fittings');
  const workspace = state(ids); workspace.max_copy_writes = 20;
  if (characters) workspace.characters = characters;
  await settle(p.last('fittings_state'), workspace);
  p.el('fittings-select-page').click(); p.el('fittings-copy-selected').click();
  return p;
}
function copySummary(p) { return p.el('fittings-copy-summary'); }
function conflictReview(ticket = 'ticket-1') {
  const value = preflight(ticket);
  value.requires_resolution = true; value.write_count = 0;
  value.counts = {ready: 0, present: 0, conflict: 1, unavailable: 0};
  value.pairs[0].status = 'conflict';
  return value;
}
async function requestReview(p) {
  p.el('fittings-copy-review').click(); await flush();
  return p.last('fittings_preflight_copy');
}

for (const [ids, initial, one, many] of [
  [['fit-1'], 'Copy 1 selected fitting', 'Copy 1 fitting to Pilot', 'Copy 1 fitting to 2 characters'],
  [['fit-1', 'fit-2'], 'Copy 2 selected fittings', 'Copy 2 fittings to Pilot', 'Copy 2 fittings to 2 characters']
]) {
  test('copy heading uses selection and targets, not additions: ' + initial, async () => {
    const characters = state().characters;
    characters.push({...characters[0], character_id: 43, character_name: 'Second pilot'});
    const p = await copySetup(ids, characters);
    assert.equal(p.el('fittings-copy-title').textContent, initial);
    const boxes = p.el('fittings-copy-body').querySelectorAll('input');
    tick(boxes[0]); assert.equal(p.el('fittings-copy-title').textContent, one);
    tick(boxes[1]); assert.equal(p.el('fittings-copy-title').textContent, many);
    tick(boxes[1]); assert.equal(p.el('fittings-copy-title').textContent, one);
    const review = preflight(); review.write_count = 0;
    review.counts = {present: ids.length};
    review.pairs = ids.map(id => ({...review.pairs[0], entry_id: id, status: 'present'}));
    await settle(await requestReview(p), review);
    assert.equal(p.el('fittings-copy-title').textContent, one);
    assert.match(copySummary(p).textContent, /^0 additions planned/);
    assert.equal(copySummary(p).hidden, false);
    assert.equal(p.el('fittings-copy-body').querySelector('.fit-copy-summary'), null);
    assert.equal(copySummary(p).getAttribute('aria-live'), null);
    await startReviewedCopy(p);
    assert.equal(p.el('fittings-copy-title').textContent, one);
    assert.match(p.confirmations.at(-1).args[1], /exactly 0 fittings/);
    await complete(p, {status: 'busy', results: [], write_count: 0});
    assert.equal(p.el('fittings-copy-title').textContent, one);
    assert.equal(p.el('fittings-copy-status').textContent, 'Another fitting copy is already running.');
  });
}

for (const pending of [false, true]) {
  test('setup heading follows background pruning without revoking accepted request: ' + pending, async () => {
    const p = await copySetup(['fit-1', 'fit-2']);
    const target = p.el('fittings-copy-body').querySelector('input');
    tick(target); target.focus();
    const request = pending ? await requestReview(p) : null;
    await p.changed({reason: 'refresh'});
    await settle(p.last('fittings_state'), state(['fit-1']));
    assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
    assert.equal(p.el('fittings-copy-body').querySelector('input'), target);
    assert.equal(p.focused(), target);
    if (request) {
      const accepted = preflight();
      accepted.pairs.push({...accepted.pairs[0], entry_id: 'fit-2', status: 'present'});
      accepted.counts = {ready: 1, present: 1};
      await settle(request, accepted);
      assert.equal(p.el('fittings-copy-title').textContent, 'Copy 2 fittings to Pilot');
      await startReviewedCopy(p);
      assert.deepEqual(p.last('fittings_start_copy').args, ['ticket-1']);
    }
  });
}

test('background pruning invalidates a rejected cap estimate without guessing new additions', async () => {
  const ids = Array.from({length: 22}, (_, i) => 'fit-' + i);
  const p = await copySetup(ids); tick(p.el('fittings-copy-body').querySelector('input'));
  await settle(await requestReview(p), {accepted: false, ticket_id: '', write_count: 0,
    counts: {ready: 22}, pairs: ids.map(id => ({...preflight().pairs[0], entry_id: id})),
    error: '22 additions requested across all targets; limit 20 (2 over). Review again.'});
  assert.equal(p.el('fittings-copy-limit-summary').hidden, false);
  await p.changed({reason: 'refresh'});
  const next = state(['fit-0']); next.max_copy_writes = 20;
  await settle(p.last('fittings_state'), next);
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
  assert.equal(p.el('fittings-copy-limit-summary').hidden, true);
  assert.doesNotMatch(p.el('fittings-copy-status').textContent, /22 additions/);
  assert.match(p.el('fittings-copy-status').textContent, /Review copy/);
  assert.equal(p.el('fittings-copy-review').disabled, false);
  assert.equal(p.el('fittings-copy-start').hidden, true);
  assert.equal(p.calls('fittings_preflight_copy').length, 1);
});

function rejectedCopyLimit() {
  return {accepted: false, ticket_id: '', write_count: 0, counts: {ready: 22}, pairs: [],
    error: '22 additions requested across all targets; limit 20 (2 over). Review again.'};
}

for (const reply of ['limit', 'null', 'other-error']) {
  test('late rejected review suppresses feedback after selection pruning: ' + reply, async () => {
    const ids = Array.from({length: 22}, (_, i) => 'fit-' + (i + 1));
    const p = await copySetup(ids); const target = p.el('fittings-copy-body').querySelector('input');
    tick(target); const pending = await requestReview(p);
    assert.deepEqual(Array.from(pending.args[0]), ids);
    await p.changed({reason: 'refresh'});
    const current = state(['fit-1']); current.max_copy_writes = 20;
    await settle(p.last('fittings_state'), current);
    target.focus(); p.el('fittings-copy-body').scrollTop = 73;
    await settle(pending, reply === 'null' ? null : reply === 'other-error'
      ? {accepted: false, error: 'Obsolete selected fittings no longer exist.'} : rejectedCopyLimit());
    assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
    assert.equal(p.el('fittings-copy-limit-summary').hidden, true);
    assert.equal(p.el('fittings-copy-limit-summary').textContent, '');
    assert.doesNotMatch(copySummary(p).textContent, /22|2 over|planned/);
    assert.equal(p.el('fittings-copy-status').textContent, 'Review copy to check current additions.');
    assert.equal(p.el('fittings-copy-status').classList.contains('err'), false);
    assert.equal(p.el('fittings-copy-review').disabled, false);
    assert.equal(p.el('fittings-copy-start').hidden, true);
    assert.equal(p.el('fittings-copy-body').querySelector('input').id, target.id);
    assert.equal(p.focused(), p.el(target.id)); assert.equal(p.el('fittings-copy-body').scrollTop, 73);
    assert.equal(p.calls('fittings_preflight_copy').length, 1);
    await settle(await requestReview(p), preflight('fresh-ticket'));
    assert.deepEqual(Array.from(p.last('fittings_preflight_copy').args[0]), ['fit-1']);
    await startReviewedCopy(p);
    assert.deepEqual(p.last('fittings_start_copy').args, ['fresh-ticket']);
  });
}

for (const order of ['unchanged', 'reordered', 'bridge-array-mutated']) {
  test('matching selection retains rejected limit and target focus: ' + order, async () => {
    const ids = Array.from({length: 22}, (_, i) => 'fit-' + (i + 1));
    const p = await copySetup(ids); const target = p.el('fittings-copy-body').querySelector('input');
    tick(target); const pending = await requestReview(p);
    if (order === 'reordered') {
      await p.changed({reason: 'refresh'});
      const next = state(ids.slice().reverse()); next.max_copy_writes = 20;
      await settle(p.last('fittings_state'), next);
    }
    if (order === 'bridge-array-mutated') pending.args[0].push('not-in-submitted-snapshot');
    target.focus(); p.el('fittings-copy-body').scrollTop = 73;
    await settle(pending, rejectedCopyLimit());
    assert.match(p.el('fittings-copy-limit-summary').textContent, /22 additions requested.*2 over/);
    assert.equal(p.el('fittings-copy-status').textContent, rejectedCopyLimit().error);
    assert.equal(p.el('fittings-copy-review').disabled, false);
    assert.equal(p.el('fittings-copy-start').hidden, true);
    assert.equal(p.el('fittings-copy-body').querySelector('input').id, target.id);
    assert.equal(p.focused(), p.el(target.id)); assert.equal(p.el('fittings-copy-body').scrollTop, 73);
  });
}

for (const transition of ['refresh', 'stale', 'add', 'remove', 'rename']) {
  test('rejected review refreshes target presentation with logical focus ownership: ' + transition, async () => {
    const ids = Array.from({length: 22}, (_, i) => 'fit-' + (i + 1));
    const characters = state().characters;
    characters.push({...characters[0], character_id: 43, character_name: 'Second pilot', stale: true});
    const p = await copySetup(ids, characters);
    const first = p.el('fittings-copy-body').querySelector('input'); tick(first);
    const pending = await requestReview(p);
    const next = state(ids); next.max_copy_writes = 20;
    next.characters = characters.map(c => ({...c}));
    if (transition === 'refresh') next.characters[1].stale = false;
    if (transition === 'stale') next.characters[0].stale = true;
    if (transition === 'add') next.characters.push({...characters[0], character_id: 44, character_name: 'Third pilot'});
    if (transition === 'remove') next.characters.shift();
    if (transition === 'rename') next.characters[0].character_name = 'Renamed pilot';
    await p.changed({reason: 'refresh'}); await settle(p.last('fittings_state'), next);
    first.focus(); p.el('fittings-copy-body').scrollTop = 31;
    await settle(pending, rejectedCopyLimit());
    const boxes = p.el('fittings-copy-body').querySelectorAll('input');
    assert.equal(boxes.length, next.characters.length);
    if (transition === 'refresh') {
      assert.equal(boxes[1].disabled, false);
      assert.doesNotMatch(boxes[1].parentNode.parentNode.textContent, /Refresh failed/);
    }
    if (transition === 'stale') {
      assert.equal(boxes[0].disabled, true);
      assert.match(boxes[0].parentNode.parentNode.textContent, /Refresh failed/);
    }
    if (transition === 'rename') assert.match(boxes[0].parentNode.textContent, /Renamed pilot/);
    assert.equal(p.focused(), ['stale', 'remove'].includes(transition) ? p.el('fittings-copy-body') : boxes[0]);
    assert.equal(p.el('fittings-copy-body').scrollTop, 31);
    assert.match(p.el('fittings-copy-limit-summary').textContent, /22 additions requested/);
    assert.equal(p.el('fittings-copy-review').disabled, false);
  });
}

for (const handoff of ['request', 'target-edit', 'scroll']) {
  test('rejection target refresh yields to a synchronous newer owner: ' + handoff, async () => {
    const p = await copySetup(['fit-1']);
    const target = p.el('fittings-copy-body').querySelector('input'); tick(target);
    const old = await requestReview(p); target.focus(); p.el('fittings-copy-body').scrollTop = 31;
    const original = Element.prototype.focus; let handedOff = false;
    Element.prototype.focus = function (options) {
      original.call(this, options);
      if (this.id !== target.id || this === target || handedOff) return;
      handedOff = true;
      if (handoff === 'request') p.el('fittings-copy-review').click();
      if (handoff === 'target-edit') tick(this);
      p.el('fittings-copy-body').scrollTop = 198;
    };
    try { await settle(old, rejectedCopyLimit()); } finally { Element.prototype.focus = original; }
    assert.equal(handedOff, true);
    assert.equal(p.el('fittings-copy-body').scrollTop, 198);
    assert.equal(p.focused(), p.el(target.id));
    if (handoff === 'request') {
      assert.equal(p.el('fittings-copy-status').textContent, 'Checking current fittings\u2026');
      assert.equal(p.el('fittings-copy-review').disabled, true);
      await settle(p.last('fittings_preflight_copy'), preflight('newer-focus-ticket'));
      assert.equal(p.el('fittings-copy-start').hidden, false);
    } else if (handoff === 'target-edit') {
      assert.equal(p.el('fittings-copy-limit-summary').hidden, true);
      assert.equal(p.el('fittings-copy-status').textContent, '');
      assert.equal(p.el('fittings-copy-review').disabled, true);
    } else assert.equal(p.el('fittings-copy-status').textContent, rejectedCopyLimit().error);
  });
}

for (const successor of ['accepted', 'setup', 'suppressed']) {
  test('old rejection yields to newer review ownership: ' + successor, async () => {
    const p = await copySetup(['fit-1', 'fit-2']);
    const target = p.el('fittings-copy-body').querySelector('input'); tick(target);
    const old = await requestReview(p);
    tick(target); tick(target); // A new target edit retires the old read.
    if (successor !== 'setup') {
      const next = await requestReview(p);
      if (successor === 'suppressed') {
        await p.changed({reason: 'refresh'});
        await settle(p.last('fittings_state'), state(['fit-1']));
        await settle(next, rejectedCopyLimit());
      } else await settle(next, preflight('new-ticket'));
    }
    const owner = successor === 'accepted' ? p.el('fittings-copy-start') : p.el(target.id);
    owner.focus(); p.el('fittings-copy-body').scrollTop = 51;
    const title = p.el('fittings-copy-title').textContent;
    const summary = copySummary(p).textContent, status = p.el('fittings-copy-status').textContent;
    await settle(old, rejectedCopyLimit());
    assert.equal(p.el('fittings-copy-title').textContent, title);
    assert.equal(copySummary(p).textContent, summary);
    assert.equal(p.el('fittings-copy-status').textContent, status);
    assert.equal(p.el('fittings-copy-limit-summary').hidden, true);
    assert.equal(p.focused(), owner); assert.equal(p.el('fittings-copy-body').scrollTop, 51);
    if (successor === 'accepted') {
      assert.equal(p.el('fittings-copy-start').hidden, false);
      await startReviewedCopy(p); assert.deepEqual(p.last('fittings_start_copy').args, ['new-ticket']);
    }
  });
}

for (const skipped of [false, true]) {
  test('stale rejection preserves accepted conflict editors and their ownership: ' + skipped, async () => {
    const p = await copySetup(['fit-1', 'fit-2']); tick(p.el('fittings-copy-body').querySelector('input'));
    const review = conflictReview();
    review.pairs.push({...review.pairs[0], entry_id: 'fit-2', status: 'present'});
    review.counts.present = 1;
    await settle(await requestReview(p), review);
    const name = p.el('fit-copy-alternate-fit-1:42'), skip = p.el('fit-copy-skip-fit-1:42');
    input(name, 'Keep alternate'); if (skipped) tick(skip);
    const pending = await requestReview(p);
    await p.changed({reason: 'refresh'}); await settle(p.last('fittings_state'), state(['fit-1']));
    const owner = skipped ? skip : name; owner.focus(); name.setSelectionRange(2, 6, 'backward');
    p.el('fittings-copy-body').scrollTop = 48;
    await settle(pending, rejectedCopyLimit());
    assert.equal(p.el('fittings-copy-status').textContent, 'Review copy to check current additions.');
    assert.equal(p.el('fittings-copy-limit-summary').hidden, true);
    assert.equal(p.el('fit-copy-alternate-fit-1:42'), name);
    assert.equal(p.el('fit-copy-skip-fit-1:42'), skip);
    assert.equal(p.focused(), owner); assert.equal(p.el('fittings-copy-body').scrollTop, 48);
    assert.equal(name.value, 'Keep alternate'); assert.equal(skip.checked, skipped);
    assert.equal(name.selectionStart, 2); assert.equal(name.selectionEnd, 6);
    assert.equal(name.selectionDirection, 'backward');
    assert.equal(p.el('fittings-copy-review').disabled, false);
    assert.equal(p.el('fittings-copy-start').hidden, true);
    const fresh = await requestReview(p);
    assert.deepEqual(Array.from(fresh.args[0]), ['fit-1']);
    assert.equal(fresh.args[2]['fit-1:42'], skipped ? null : 'Keep alternate');
  });
}

for (const terminal of ['busy', 'invalid_ticket', 'failed']) {
  test('empty ' + terminal + ' history keeps A context after abandoned setup B', async () => {
    const p = await copySetup(['fit-1', 'fit-2']);
    // Opening hulls contain two IDs; actual later submitted set contains one.
    await p.changed({reason: 'refresh'});
    await settle(p.last('fittings_state'), state(['fit-1']));
    tick(p.el('fittings-copy-body').querySelector('input'));
    const call = await requestReview(p);
    assert.deepEqual(Array.from(call.args[0]), ['fit-1']);
    const review = preflight('ticket-a'); review.pairs[0].character_name = 'Accepted <Pilot>';
    await settle(call, review); await startReviewedCopy(p);
    // The retained descriptive context must not retain payload objects.
    review.pairs[0].character_name = 'Mutated payload';
    await p.route('main');
    await complete(p, {status: terminal, operation_id: '', results: [], write_count: 0}, 'ticket-a');
    await p.route('fittings');
    const later = state(['fit-9']);
    later.characters = [{...later.characters[0], character_id: 43, character_name: 'Setup B'}];
    await settle(p.last('fittings_state'), later);
    p.el('fittings-select-page').click(); p.el('fittings-copy-selected').click();
    tick(p.el('fittings-copy-body').querySelector('input'));
    assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Setup B');
    p.el('fittings-copy-close').click();
    const before = p.calls().length;
    button(p.el('fittings-notices'), 'Last copy results\u2026').click();
    assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Accepted <Pilot>');
    assert.equal(p.el('fittings-copy-title').children.length, 0);
    assert.equal(copySummary(p).textContent, 'No copy results.');
    assert.equal(p.el('fittings-copy-start').hidden, true);
    assert.equal(p.el('fittings-copy-technical'), null);
    assert.equal(p.calls().length, before);
  });
}

for (const [ids, heading] of [
  [['fit-1'], 'Copy 1 selected fitting'],
  [['fit-1', 'fit-2'], 'Copy 2 selected fittings']
]) {
  test('known fitting count without accepted target identity retains fallback: ' + heading, async () => {
    const p = await copySetup(ids); tick(p.el('fittings-copy-body').querySelector('input'));
    const review = preflight();
    review.pairs = ids.map(entry_id => ({entry_id, fitting_name: 'Known fitting',
      status: 'ready', chosen_name: 'Known fitting'}));
    await settle(await requestReview(p), review);
    assert.equal(p.el('fittings-copy-title').textContent, heading);
    await startReviewedCopy(p);
    assert.deepEqual(p.last('fittings_start_copy').args, ['ticket-1'], 'missing descriptive facts do not change admission');
    assert.equal(p.el('fittings-copy-title').textContent, heading);
    await complete(p, {status: 'busy', results: [], write_count: 0});
    assert.equal(p.el('fittings-copy-title').textContent, heading);
    p.el('fittings-copy-close').click();
    button(p.el('fittings-notices'), 'Last copy results\u2026').click();
    assert.equal(p.el('fittings-copy-title').textContent, heading);
  });
}

test('unknown descriptive fitting IDs cannot invent a count from a preflight row', async () => {
  const p = await copySetup(); tick(p.el('fittings-copy-body').querySelector('input'));
  const review = preflight(); review.pairs = [{status: 'ready'}];
  await settle(await requestReview(p), review);
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy fittings');
  await startReviewedCopy(p);
  assert.equal(p.el('fittings-copy-title').textContent, 'Copying fittings');
  await complete(p, {status: 'failed', results: [], write_count: 0});
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy results');
});

test('accepted Cartesian pairs count unique fittings and characters in accepted order', async () => {
  const characters = state().characters;
  characters.push({...characters[0], character_id: 43, character_name: 'Other'});
  const p = await copySetup(['fit-1', 'fit-2'], characters);
  p.el('fittings-copy-body').querySelectorAll('input').forEach(tick);
  const review = preflight(); review.write_count = 1;
  review.counts = {ready: 1, present: 3};
  review.pairs = [43, 42].flatMap(character_id => ['fit-2', 'fit-1'].map(entry_id => ({
    ...review.pairs[0], character_id, entry_id, character_name: 'Target ' + character_id,
    status: character_id === 43 && entry_id === 'fit-2' ? 'ready' : 'present'
  })));
  await settle(await requestReview(p), review);
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 2 fittings to 2 characters');
  assert.deepEqual(p.el('fittings-copy-body').querySelectorAll('.fit-copy-character').map(n => n.textContent),
    ['Target 43', 'Target 43', 'Target 42', 'Target 42']);
  await startReviewedCopy(p); await complete(p, result(['success']));
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 2 fittings to 2 characters', 'one result row cannot shrink context');
});

for (const olderAccepted of [true, false]) {
  test('reverse preflight ' + olderAccepted + ' cannot replace latest ticket and context', async () => {
    const characters = state().characters;
    characters.push({...characters[0], character_id: 43, character_name: 'Later'});
    const p = await copySetup(['fit-1'], characters);
    const boxes = p.el('fittings-copy-body').querySelectorAll('input'); tick(boxes[0]);
    const older = await requestReview(p);
    tick(boxes[0]); tick(boxes[1]);
    const latest = await requestReview(p);
    const review = preflight('latest'); review.pairs[0].character_id = 43; review.pairs[0].character_name = 'Later';
    await settle(latest, review);
    await settle(older, olderAccepted ? preflight('older') : {accepted: false, error: 'Stale rejection'});
    assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Later');
    assert.doesNotMatch(p.el('fittings-copy-status').textContent, /Stale/);
    await startReviewedCopy(p);
    assert.deepEqual(p.last('fittings_start_copy').args, ['latest']);
  });
}

test('target edit invalidates an outstanding preflight even without a replacement request', async () => {
  const p = await copySetup(); const box = p.el('fittings-copy-body').querySelector('input');
  tick(box); const pending = await requestReview(p); tick(box);
  await settle(pending, preflight());
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 selected fitting');
  assert.equal(p.el('fittings-copy-start').hidden, true);
  assert.equal(p.el('fittings-copy-review').disabled, true);
});

test('limit refusal reports classified requested additions, not a plan or disabled roster pairs', async () => {
  const characters = state().characters;
  characters.push({...characters[0], character_id: 43, status: 'reauthenticate'});
  const p = await copySetup(['fit-1'], characters);
  tick(p.el('fittings-copy-body').querySelector('input'));
  const error = '22 additions requested across all targets; limit 20 (2 over). Select fewer fittings or targets, then review again.';
  await settle(await requestReview(p), {accepted: false, ticket_id: '', write_count: 0,
    counts: {ready: 22, present: 7, conflict: 0, unavailable: 0}, pairs: [], error});
  const limit = p.el('fittings-copy-limit-summary');
  assert.ok(limit && !limit.hidden);
  assert.match(limit.textContent, /22 additions requested.*20.*2 over/);
  assert.doesNotMatch(limit.textContent, /planned|attempted/);
  assert.equal(p.el('fittings-copy-status').textContent, error);
  assert.equal(p.el('fittings-copy-start').hidden, true);
  assert.equal(p.el('fittings-copy-review').disabled, false);
  assert.doesNotMatch(copySummary(p).textContent, /1 unavailable/);
  tick(p.el('fittings-copy-body').querySelector('input'));
  assert.equal(limit.hidden, true); assert.equal(limit.textContent, '');
  assert.doesNotMatch(p.el('fittings-copy-status').textContent, /22|2 over/);
  assert.equal(p.el('fittings-copy-start').hidden, true);
});

test('conflict drafts mark counts pending review without inventing new classifications', async () => {
  const p = await editor(); await reviewCopy(p, conflictReview());
  const summary = copySummary(p); assert.ok(summary);
  const original = '0 additions planned · 0 already present · 1 conflict · 0 unavailable';
  assert.equal(summary.textContent, original);
  input(p.el('fit-copy-alternate-fit-1:42'), 'Alternative');
  assert.equal(summary.textContent, original + ' · Changes pending review');
  const pending = await requestReview(p);
  input(p.el('fit-copy-alternate-fit-1:42'), 'Newer draft');
  assert.doesNotMatch(p.el('fittings-copy-status').textContent, /Checking current fittings/, 'revoked read must not claim to check the newer draft');
  await settle(pending, preflight('stale-resolved'));
  assert.equal(p.el('fit-copy-alternate-fit-1:42').value, 'Newer draft');
  assert.equal(p.el('fittings-copy-start').hidden, true);
  assert.match(summary.textContent, /Changes pending review/);
  tick(p.el('fit-copy-skip-fit-1:42'));
  assert.equal(p.el('fittings-copy-review').disabled, false);
  await settle(await requestReview(p), preflight('resolved'));
  assert.doesNotMatch(summary.textContent, /pending review/i);
  await startReviewedCopy(p);
  assert.deepEqual(p.last('fittings_start_copy').args, ['resolved']);
});

for (const phase of ['review', 'results']) {
  test('pair identity owns labelled status, error and controls in ' + phase, async () => {
    const p = await editor();
    if (phase === 'review') await reviewCopy(p, conflictReview());
    else { await beginCopy(p); await complete(p, {status: 'complete', write_count: 1, results: [
      {...preflight().pairs[0], status: 'failed', error: 'Not attempted. Full error.'}]}); }
    const row = p.el('fittings-copy-body').querySelector('.fit-copy-pair');
    const context = row.querySelector('.fit-copy-pair-context');
    assert.ok(context); assert.equal(context.parentNode, row);
    const name = context.querySelector('.fit-copy-pair-name');
    const character = context.querySelector('.fit-copy-character');
    assert.equal(name.textContent, 'Sabre tackle (Sabre)'); assert.equal(character.textContent, 'Pilot');
    assert.equal(row.getAttribute('role'), 'group');
    assert.deepEqual(row.getAttribute('aria-labelledby').split(' ').map(id => p.el(id)), [name, character]);
    const references = row.getAttribute('aria-describedby').split(' ').map(id => p.el(id));
    assert.ok(references.every(node => node && node.parentNode === row));
    if (phase === 'review') {
      const skip = p.el('fit-copy-skip-fit-1:42'); assert.ok(skip);
      assert.match(skip.getAttribute('aria-label'), /^Skip this pair.*Sabre tackle.*Sabre.*Pilot/);
      assert.equal(p.el('fit-copy-alternate-fit-1:42').getAttribute('aria-describedby'), 'fit-copy-instruction-fit-1:42');
    } else {
      assert.ok(references.some(node => node.textContent === 'Not attempted. Full error.'));
      assert.ok(references.some(node => /refresh.*review/i.test(node.textContent)));
    }
  });
}

for (const control of ['alternate', 'skip']) {
  for (const accepted of [true, false]) {
    test('copy rerender preserves owned ' + control + ' focus, draft, caret and scroll: ' + accepted, async () => {
      const p = await editor(); await reviewCopy(p, conflictReview());
      input(p.el('fit-copy-alternate-fit-1:42'), 'Draft name');
      if (control === 'skip') tick(p.el('fit-copy-skip-fit-1:42'));
      const pending = await requestReview(p);
      const id = 'fit-copy-' + control + '-fit-1:42', old = p.el(id);
      old.focus(); old.setSelectionRange(2, 6, 'backward');
      const body = p.el('fittings-copy-body'); body.scrollTop = 123;
      await settle(pending, accepted ? conflictReview('reviewed-again') : {accepted: false, error: 'Still conflicting'});
      assert.equal(p.focused(), p.el(id)); assert.notEqual(p.el(id), old);
      assert.equal(body.scrollTop, 123);
      assert.equal(p.el('fit-copy-alternate-fit-1:42').value, 'Draft name', 'Skip preserves the adjacent text draft');
      if (control === 'alternate') assert.deepEqual([p.el(id).selectionStart, p.el(id).selectionEnd, p.el(id).selectionDirection], [2, 6, 'backward']);
      else assert.equal(p.el(id).checked, true);
    });
  }
}

for (const newer of ['close', 'dialog', 'route', 'setup']) {
  test('preflight rerender cannot steal focus from newer ' + newer, async () => {
    const p = await editor(); await reviewCopy(p, conflictReview());
    input(p.el('fit-copy-alternate-fit-1:42'), 'Draft');
    const pending = await requestReview(p);
    if (newer === 'close') p.el('fittings-copy-close').focus();
    if (newer === 'dialog') { p.el('overlay').hidden = false; p.el('dlg-ok').focus(); }
    if (newer === 'route') { await p.route('main'); p.el('nav-main').focus(); }
    if (newer === 'setup') { p.el('fittings-copy-close').click(); p.el('fittings-copy-selected').click(); }
    const focused = p.focused();
    await settle(pending, conflictReview('later'));
    assert.equal(p.focused(), focused);
  });
}

test('resolved conflict hands retired input focus to the current copy view only', async () => {
  const p = await editor(); await reviewCopy(p, conflictReview());
  const inputNode = p.el('fit-copy-alternate-fit-1:42'); input(inputNode, 'Alternative');
  const pending = await requestReview(p); inputNode.focus();
  await settle(pending, preflight('resolved'));
  assert.equal(p.focused(), p.el('fittings-copy-body'), 'removing the owned editor cannot strand focus behind the modal');
  assert.equal(p.el('fittings-copy-start').hidden, false);
});

test('determinate pair-check progress updates one native node without moving controls or scroll', async () => {
  const p = await editor(); await beginCopy(p);
  const body = p.el('fittings-copy-body'), bar = p.el('fittings-copy-progress');
  assert.ok(bar); assert.equal(bar.tagName, 'PROGRESS');
  assert.equal(bar.getAttribute('aria-labelledby'), 'fittings-copy-title');
  assert.equal(bar.getAttribute('aria-valuemin'), '0');
  assert.equal(bar.getAttribute('aria-valuenow'), '0');
  assert.equal(bar.getAttribute('aria-valuemax'), '1');
  const cancel = p.el('fittings-copy-cancel'); cancel.focus(); body.scrollTop = 64;
  for (const n of [0, 1]) {
    await p.progress({kind: 'copy', phase: 'progress', ticket_id: 'ticket-1', completed: n, total: 1, result: preflight().pairs[0]});
    assert.equal(p.el('fittings-copy-progress'), bar); assert.equal(bar.hidden, false);
    assert.equal(Number(bar.value), n); assert.equal(Number(bar.max), 1);
    assert.equal(bar.getAttribute('aria-valuenow'), String(n));
    assert.equal(copySummary(p).textContent, n + ' of 1 fitting/character check complete');
    assert.equal(p.focused(), cancel); assert.equal(body.scrollTop, 64);
    assert.equal(p.el('fittings-copy-close').disabled, true);
    assert.equal(cancel.hidden, false);
    assert.equal(bar.getAttribute('aria-live'), null);
  }
  cancel.click(); await flush();
  assert.equal(cancel.disabled, true); assert.equal(p.focused(), p.el('fittings-copy-dialog'));
  await p.progress({kind: 'copy', phase: 'progress', ticket_id: 'ticket-1', completed: 1, total: 1, result: preflight().pairs[0]});
  assert.equal(cancel.disabled, true); assert.equal(p.focused(), p.el('fittings-copy-dialog'));
  assert.equal(p.calls('fittings_cancel_copy').length, 1);
});

for (const [completed, total] of [[0, 0], [0, undefined], [undefined, 1], [2, 1], [-1, 2], [NaN, 2], [1, Infinity], [1, '2']]) {
  test('invalid progress does not invent a percentage: ' + completed + '/' + total, async () => {
    const p = await editor(); await beginCopy(p);
    await p.progress({kind: 'copy', phase: 'progress', ticket_id: 'ticket-1', completed, total, result: preflight().pairs[0]});
    const bar = p.el('fittings-copy-progress'); assert.ok(bar); assert.equal(bar.hidden, true);
    for (const attr of ['value', 'max', 'aria-valuenow', 'aria-valuemax']) assert.equal(bar.getAttribute(attr), null);
    assert.equal(copySummary(p).textContent, 'Checking fitting/character pairs…');
    assert.doesNotMatch(copySummary(p).textContent, /undefined|NaN|Infinity|%/);
    assert.match(p.el('fittings-copy-status').textContent, /Sabre tackle.*Pilot/);
  });
}

for (const stage of ['progress', 'results']) {
  test('direct screenshot ' + stage + ' has generic context without accepted preflight', async () => {
    const p = await page(); await p.route('fittings'); const fixture = devScreenshot(stage);
    if (stage === 'progress') fixture.copy_progress_completed = 2;
    await p.screenshot(fixture);
    assert.equal(p.el('fittings-copy-title').textContent, stage === 'progress' ? 'Copying fittings' : 'Copy results');
    assert.equal(p.calls('fittings_preflight_copy').length, 0);
    assert.equal(p.calls('fittings_start_copy').length, 0);
  });
}

test('Technical details is a native session-only disclosure, not a live operation-ID announcement', async () => {
  const p = await editor(); await beginCopy(p); await complete(p, result(['unknown']));
  const technical = p.el('fittings-copy-technical'); assert.ok(technical);
  assert.equal(technical.tagName, 'DETAILS'); assert.equal(technical.open, false);
  assert.equal(technical.className, 'fit-copy-technical');
  const summary = technical.querySelector('summary');
  assert.equal(summary.textContent, 'Technical details'); assert.equal(summary.getAttribute('tabindex'), '0');
  const id = p.el('fittings-copy-operation-id');
  assert.equal(id.textContent, 'Operation ID: op-1'); assert.equal(id.parentNode, technical);
  assert.equal(id.children.length, 0);
  assert.equal(p.el('fittings-copy-status').textContent, '1 needs verification');
  assert.equal(copySummary(p).textContent, '1 needs verification');
  const before = p.calls().length;
  summary.focus(); p.focusEvent(summary); assert.equal(p.focused(), summary);
  technical.open = true; technical.dispatchEvent({type: 'toggle'});
  assert.equal(p.focused(), summary); assert.equal(p.calls().length, before);
  p.el('fittings-copy-close').focus(); p.key('Tab');
  assert.equal(p.focused(), p.el('fittings-copy-body'));
  p.el('fittings-copy-body').focus(); p.key('Tab', true);
  assert.equal(p.focused(), p.el('fittings-copy-close'));
  p.el('fittings-copy-close').click();
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-technical').open, false);
  assert.equal(p.el('fittings-copy-operation-id').textContent, 'Operation ID: op-1');
  assert.equal(p.calls().length, before);
});

for (const phase of ['targets', 'preflight']) {
  for (const accepted of [true, false]) {
    test('focused Review hands focus to the mounted copy body while pending and after ' + phase + ': ' + accepted, async () => {
      const p = phase === 'targets' ? await copySetup() : await editor();
      if (phase === 'targets') tick(p.el('fittings-copy-body').querySelector('input'));
      else { await reviewCopy(p, conflictReview()); input(p.el('fit-copy-alternate-fit-1:42'), 'Draft'); }
      const review = p.el('fittings-copy-review'), body = p.el('fittings-copy-body');
      body.scrollTop = 79; review.focus();
      const pending = await requestReview(p);
      assert.equal(p.focused(), body, 'native disabling must not send keyboard/pointer focus behind the modal');
      assert.equal(body.lastFocusOptions.preventScroll, true);
      assert.equal(body.scrollTop, 79);
      assert.equal(review.disabled, true);
      await settle(pending, accepted ? preflight('checked') : {accepted: false, error: 'Complete rejected-review reason.'});
      assert.equal(p.focused(), body, 'reply does not claim completion focus');
      assert.equal(body.scrollTop, 79);
    });
  }
}

for (const newer of ['control', 'dialog', 'route']) {
  test('focused Review pending handoff yields to newer ' + newer, async () => {
    const p = await copySetup(); tick(p.el('fittings-copy-body').querySelector('input'));
    p.el('fittings-copy-review').focus(); const pending = await requestReview(p);
    assert.equal(p.focused(), p.el('fittings-copy-body'));
    if (newer === 'control') p.el('fittings-copy-close').focus();
    if (newer === 'dialog') { p.el('overlay').hidden = false; p.el('dlg-ok').focus(); }
    if (newer === 'route') { await p.route('main'); p.el('nav-main').focus(); }
    const successor = p.focused(); await settle(pending, preflight());
    assert.equal(p.focused(), successor);
  });
}

test('copy summaries use the existing live owner once per changed text, with visible errors preserved', async () => {
  const p = await editor(); await reviewCopy(p, conflictReview());
  const status = p.el('fittings-copy-status');
  assert.equal(status.textContent, copySummary(p).textContent);
  assert.equal(status.classList.contains('status-announcement'), true);
  let writes = 0; status.onChildrenCleared = () => { writes++; };
  input(p.el('fit-copy-alternate-fit-1:42'), 'A');
  assert.equal(status.textContent, copySummary(p).textContent);
  assert.match(status.textContent, /Changes pending review/);
  assert.equal(writes, 1);
  input(p.el('fit-copy-alternate-fit-1:42'), 'AB');
  input(p.el('fit-copy-alternate-fit-1:42'), 'ABC');
  tick(p.el('fit-copy-skip-fit-1:42'));
  assert.equal(writes, 1, 'unchanged category/marker text is not rewritten on each keystroke');
  const pending = await requestReview(p);
  assert.equal(status.classList.contains('status-announcement'), false);
  assert.match(status.textContent, /Checking current fittings/);
  await settle(pending, {accepted: false, error: 'Full recovery: choose a different fitting name.'});
  assert.equal(status.classList.contains('status-announcement'), false);
  assert.equal(status.textContent, 'Full recovery: choose a different fitting name.');
  tick(p.el('fit-copy-skip-fit-1:42'));
  assert.equal(status.textContent, 'Full recovery: choose a different fitting name.', 'draft announcement never removes actionable rejection');
  await settle(await requestReview(p), preflight('resolved'));
  assert.equal(status.textContent, copySummary(p).textContent);
  assert.equal(status.classList.contains('status-announcement'), true);
  await startReviewedCopy(p);
  assert.equal(status.classList.contains('status-announcement'), false);
  assert.equal(status.textContent, 'Starting…');
  await p.progress({kind: 'copy', phase: 'progress', ticket_id: 'resolved', completed: 1, total: 1,
    result: {...preflight().pairs[0], status: 'success'}});
  assert.match(status.textContent, /1 of 1 fitting\/character check complete.*Sabre tackle.*Copied/);
  assert.equal(status.classList.contains('status-announcement'), false);
  p.el('fittings-copy-cancel').click(); await flush();
  assert.match(status.textContent, /Cancelling/); assert.equal(status.classList.contains('status-announcement'), false);
  await complete(p, result(['success']), 'resolved');
  assert.equal(status.textContent, copySummary(p).textContent);
  assert.equal(status.classList.contains('status-announcement'), true);
});

for (const accepted of [true, false]) {
  for (const newer of ['control', 'dialog', 'setup', 'route']) {
    test('copy removal yields its scroll and render to newer ' + newer + ': ' + accepted, async () => {
      const p = await editor(); await reviewCopy(p, conflictReview());
      input(p.el('fit-copy-alternate-fit-1:42'), 'Draft');
      const pending = await requestReview(p), body = p.el('fittings-copy-body');
      p.el('fit-copy-alternate-fit-1:42').focus(); body.scrollTop = 34;
      let successor;
      body.onChildrenCleared = () => {
        body.onChildrenCleared = null;
        if (newer === 'control') p.el('fittings-copy-close').focus();
        if (newer === 'dialog') { p.el('overlay').hidden = false; p.el('dlg-ok').focus(); }
        if (newer === 'setup') { p.el('fittings-copy-close').click(); p.el('fittings-copy-selected').click(); }
        if (newer === 'route') { p.route('main'); p.el('nav-main').focus(); }
        body.scrollTop = 198; successor = p.focused();
      };
      await settle(pending, accepted ? conflictReview('checked') : {accepted: false, error: 'Obsolete refusal'});
      assert.equal(body.scrollTop, 198, 'a retired reader cannot overwrite newer scroll');
      assert.equal(p.focused(), successor);
      if (newer === 'setup') {
        assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 selected fitting');
        assert.equal(body.querySelector('.fit-copy-pair'), null);
        assert.doesNotMatch(p.el('fittings-copy-status').textContent, /Obsolete refusal/);
      }
    });
  }
}

test('copy focus-event handoff cannot restore old caret or scroll over a newer control', async () => {
  const p = await editor(); await reviewCopy(p, conflictReview());
  const old = p.el('fit-copy-alternate-fit-1:42'); input(old, 'Draft name');
  const pending = await requestReview(p); old.focus(); old.setSelectionRange(2, 6, 'backward');
  const body = p.el('fittings-copy-body'); body.scrollTop = 34;
  const doc = old.ownerDocument, create = doc.createElement;
  doc.createElement = tag => {
    const node = create(tag), focus = node.focus;
    node.focus = function (options) {
      focus.call(this, options);
      if (this.id === old.id && options?.preventScroll) {
        p.el('fittings-copy-close').focus(); body.scrollTop = 287;
      }
    };
    return node;
  };
  await settle(pending, conflictReview('checked'));
  assert.equal(p.focused(), p.el('fittings-copy-close'));
  assert.equal(body.scrollTop, 287);
  assert.equal(p.el(old.id).selectionStart, undefined, 'a newer focus event also revokes old caret ownership');
});

test('copy pair focus clearance measures its own identity at render, resize and wrapping', async () => {
  const p = await editor(); await reviewCopy(p, conflictReview());
  const row = p.el('fittings-copy-body').querySelector('.fit-copy-pair');
  const context = row.querySelector('.fit-copy-pair-context');
  const name = p.el('fit-copy-alternate-fit-1:42'); name.focus();
  p.el('fittings-copy-body').measuredHeight = 350;
  name.getBoundingClientRect = () => ({top: 140, bottom: 172});
  p.el('fittings-copy-body').scrollTop = 91;
  assert.equal(row.style.getPropertyValue('--fit-copy-context-clearance'), '44px');
  context.measuredHeight = 82.5; p.resize();
  assert.equal(row.style.getPropertyValue('--fit-copy-context-clearance'), '90.5px');
  context.measuredHeight = 110; p.resizeObserved(context);
  assert.equal(row.style.getPropertyValue('--fit-copy-context-clearance'), '118px');
  assert.equal(p.focused(), name); assert.equal(p.el('fittings-copy-body').scrollTop, 91);
  p.el('fittings-copy-close').click();
  context.measuredHeight = 500; p.resizeObserved(context);
  assert.equal(row.style.getPropertyValue('--fit-copy-context-clearance'), '118px', 'closed views no longer own observation');
});

for (const mode of ['above', 'under-identity', 'below', 'visible', 'new-dialog', 'other-control', 'observation-only', 'off-route', 'skip']) {
  test('resize reveals only the currently obscured copy control: ' + mode, async () => {
    const p = await editor(); await reviewCopy(p, conflictReview());
    const host = p.el('fittings-copy-body');
    const context = host.querySelector('.fit-copy-pair-context');
    const input = p.el('fit-copy-alternate-fit-1:42');
    const control = mode === 'skip' ? p.el('fit-copy-skip-fit-1:42') : input;
    host.getBoundingClientRect = () => ({top: 100, bottom: 350});
    context.getBoundingClientRect = () => ({top: 100, bottom: 148, height: 48});
    const top = mode === 'above' ? 60 : mode === 'below' ? 340 : mode === 'visible' ? 180 : 120;
    control.getBoundingClientRect = () => ({top, bottom: top + 32});
    control.focus(); input.value = 'Retained alternate'; input.setSelectionRange(2, 5, 'backward');
    host.scrollTop = 91;
    const reveals = [];
    control.scrollIntoView = options => { reveals.push({...options}); host.scrollTop = 123; };
    if (mode === 'new-dialog') p.el('overlay').hidden = false;
    if (mode === 'other-control') p.el('fittings-copy-close').focus();
    if (mode === 'off-route') await p.route('main');
    const owner = p.focused();
    if (mode === 'observation-only') p.resizeObserved(context); else p.resize();
    const expected = ['above', 'under-identity', 'below', 'skip'].includes(mode);
    assert.deepEqual(reveals, expected ? [{block: 'nearest'}] : []);
    assert.equal(p.focused(), owner);
    assert.equal(input.selectionStart, 2); assert.equal(input.selectionEnd, 5);
    assert.equal(input.selectionDirection, 'backward');
    assert.equal(host.scrollTop, expected ? 123 : 91);
  });
}

test('accepted name fallback comes from submitted snapshot, not later roster state', async () => {
  const p = await copySetup(); tick(p.el('fittings-copy-body').querySelector('input'));
  const pending = await requestReview(p);
  const later = state(); later.characters[0].character_name = 'Renamed later';
  await p.changed({reason: 'refresh'}); await settle(p.last('fittings_state'), later);
  const review = preflight(); review.pairs[0].character_name = '';
  await settle(pending, review);
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
  p.el('fittings-copy-title').textContent = 'Copy 999 fittings to Fake';
  copySummary(p).textContent = '999 additions planned';
  await startReviewedCopy(p);
  assert.match(p.confirmations.at(-1).args[1], /exactly 1 fitting in EVE/);
  assert.deepEqual(p.last('fittings_start_copy').args, ['ticket-1'], 'displayed prose is never admission');
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
});

test('off-route A completion during setup B cannot borrow B or replace its visible context', async () => {
  const p = await editor(); await beginCopy(p, 'A'); await p.route('main');
  await p.route('fittings'); const workspace = state(['fit-2', 'fit-3']);
  workspace.characters[0].character_name = 'Different target';
  await settle(p.last('fittings_state'), workspace);
  p.el('fittings-select-page').click(); p.el('fittings-copy-selected').click();
  tick(p.el('fittings-copy-body').querySelector('input'));
  await complete(p, {status: 'busy', results: [], write_count: 0}, 'A');
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 2 fittings to Different target');
  p.el('fittings-copy-close').click();
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
  await complete(p, result(['success']), 'A');
  assert.equal(copySummary(p).textContent, 'No copy results.', 'duplicate completion cannot replace retained terminal state');
});

// Clipboard regressions exercise production listeners, not a second state machine.
const eftText = '[Rifter, Fleet <fit>]\n200mm AutoCannon II, Republic Fleet EMP S /offline\nHobgoblin II x5\n';
function eftReview() {
  return {ok: true, review_id: 'opaque-review', name: 'Fleet <fit>', ship_name: 'Rifter',
    items: [{flag: 'HiSlot0', location: 'high', type_id: 2889, type_name: '200mm AutoCannon II', quantity: 1},
      {flag: 'DroneBay', location: 'DroneBay', type_id: 2456, type_name: 'Hobgoblin II', quantity: 5}],
    warnings: [
      {code: 'loaded_charge_omitted', line_number: 2, message: 'Line 2: Loaded charge selection Republic Fleet EMP S is not retained; EFT specifies no quantity. Explicit cargo quantities are unchanged.'},
      {code: 'offline_omitted', line_number: 2, message: 'Line 2: Offline state is not retained; the module remains in the fitting.'},
      {code: 'bay_convention', line_number: 3, message: 'Line 3: Hobgoblin II x5 is interpreted as DroneBay content; EFT does not preserve Cargo/bay intent.'}
    ], existing_entry_id: '', error: ''};
}
function importControl(p, name) {
  const node = p.el('fittings-import-' + name);
  assert.ok(node, 'missing clipboard import control: ' + name);
  return node;
}
async function importPage(options) {
  const p = await page(options); await p.route('fittings');
  const empty = state([]); empty.characters = [];
  await settle(p.last('fittings_state'), empty);
  assert.equal(p.reads.length, 0, 'route entry must not read the clipboard');
  importControl(p, 'open').click();
  assert.equal(importControl(p, 'panel').hidden, false);
  return p;
}
async function reviewedImport(options) {
  const p = await importPage(options);
  input(importControl(p, 'text'), eftText);
  importControl(p, 'review').click(); await flush();
  assert.deepEqual(p.last('fittings_review_eft').args, [eftText]);
  await settle(p.last('fittings_review_eft'), eftReview());
  return p;
}
async function addedImport(created = true) {
  const p = await reviewedImport();
  importControl(p, 'add').click(); await flush();
  await settle(p.last('fittings_import_eft'), {applied: true, persisted: true,
    entry_id: 'imported', created, error: ''});
  return p;
}
function locatorSnapshot() {
  const payload = state(['imported', 'neighbour']);
  payload.page = 2; payload.page_size = 100; payload.total = 202;
  payload.rows[0].name = 'Located snapshot';
  return {ok: true, entry_id: 'imported', workspace: payload, error: ''};
}

test('clipboard warnings retain exactly one codec-owned line prefix before and after Add', async () => {
  const fixtures = path.join(__dirname, '..', 'tests', 'fixtures', 'evefittings', 'eft');
  const cases = JSON.parse(fs.readFileSync(path.join(fixtures, 'cases.json'), 'utf8')).cases;
  for (const fixture of cases.filter(c => c.approved_import.ok && c.approved_import.warnings.length)) {
    const p = await importPage();
    input(importControl(p, 'text'), fs.readFileSync(path.join(fixtures, fixture.file), 'utf8'));
    importControl(p, 'review').click(); await flush();
    const review = eftReview();
    review.warnings = fixture.approved_import.warnings;
    await settle(p.last('fittings_review_eft'), review);
    for (const stage of ['Review', 'Add']) {
      if (stage === 'Add') {
        importControl(p, 'add').click(); await flush();
        await settle(p.last('fittings_import_eft'), {applied: true, persisted: true,
          entry_id: 'imported', created: true, error: ''});
      }
      const messages = importControl(p, 'candidate').querySelectorAll('.fit-import-warning').map(w => w.textContent);
      assert.deepEqual(messages, fixture.approved_import.warnings.map(w => w.message), fixture.id + ' after ' + stage);
      assert.ok(messages.every(message => (message.match(/Line \d+:/g) || []).length === 1));
    }
  }
});

test('clipboard import is explicit, usable without characters and reviews normalized rows/warnings before Add', async () => {
  const p = await importPage();
  assert.match(p.el('fittings-empty').textContent, /Import from clipboard/);
  assert.equal(importControl(p, 'add').disabled, true);
  assert.equal(p.reads.length, 1, 'the fresh opener click requests clipboard text without a second click');
  await settle(p.reads[0], eftText);
  assert.equal(importControl(p, 'text').value, eftText);
  assert.equal(p.calls('fittings_review_eft').length, 0, 'paste is not Review');
  importControl(p, 'review').click(); await flush();
  assert.equal(importControl(p, 'add').disabled, true);
  await settle(p.last('fittings_review_eft'), eftReview());
  const candidate = importControl(p, 'candidate');
  assert.match(candidate.textContent, /Fleet <fit>.*Rifter/);
  assert.match(candidate.textContent, /200mm AutoCannon II.*Hobgoblin II.*5/s);
  const warnings = candidate.querySelectorAll('.fit-import-warning');
  assert.deepEqual(warnings.map(w => w.textContent), eftReview().warnings.map(w => w.message));
  assert.ok(warnings.every(w => w.getClientRects().length && w.children.length === 0));
  assert.equal(importControl(p, 'add').disabled, false);
  assert.equal(p.calls('fittings_import_eft').length, 0, 'Review never adds');
  importControl(p, 'add').click(); await flush();
  assert.deepEqual(p.last('fittings_import_eft').args, ['opaque-review'], 'Add sends only the opaque ticket');
  assert.doesNotMatch(importControl(p, 'status').textContent, /Added|Already in/);
  // Real controller notification may precede its receipt; neither may select a row.
  await p.changed({reason: 'import', entry_id: 'imported'});
  await settle(p.last('fittings_state'), state(['imported']));
  await settle(p.last('fittings_import_eft'), {applied: true, persisted: true, entry_id: 'imported', created: true, error: ''});
  assert.equal(importControl(p, 'text').value, '');
  assert.match(importControl(p, 'status').textContent, /Added.*library/);
  assert.equal(candidate.querySelectorAll('.fit-import-warning').length, 3, 'warnings survive successful Add');
  assert.equal(importControl(p, 'show').hidden, false);
  assert.deepEqual(selectedRows(p), []);
  assert.equal(p.calls('fittings_preflight_copy').length, 0);
  assert.equal(p.calls('fittings_detail').length, 0, 'success does not automatically open or focus a fit');
});

for (const mode of ['missing', 'throw', 'reject']) {
  test('clipboard read ' + mode + ' keeps manual paste usable without auto-review', async () => {
    const p = await importPage(mode === 'missing' ? {clipboard: false} : {readText: mode});
    if (mode === 'reject') {
      assert.equal(p.reads.length, 1, 'fresh opener attempts the read');
      p.reads.at(-1).reject(new Error('denied'));
    }
    await flush();
    assert.equal(importControl(p, 'text').value, '');
    assert.match(importControl(p, 'status').textContent, /paste.*manually/i);
    input(importControl(p, 'text'), eftText);
    importControl(p, 'read').click();
    if (mode === 'reject') p.reads.at(-1).reject(new Error('replacement denied'));
    await flush();
    assert.equal(importControl(p, 'text').value, eftText, 'failed explicit replacement preserves the manual draft');
    assert.match(importControl(p, 'status').textContent, /paste.*manually/i);
    assert.equal(importControl(p, 'read').disabled, false);
    assert.equal(p.calls('fittings_review_eft').length, 0);
    importControl(p, 'review').click(); await flush();
    await settle(p.last('fittings_review_eft'), eftReview());
    assert.equal(importControl(p, 'add').disabled, false);
  });
}

for (const stage of ['read', 'review', 'add']) {
  for (const revoke of ['typing', 'route', 'screenshot', 'close']) {
    test('clipboard delayed ' + stage + ' loses ownership to ' + revoke, async () => {
      const p = stage === 'add' ? await reviewedImport() : await importPage();
      input(importControl(p, 'text'), eftText);
      if (stage === 'add') {
        importControl(p, 'review').click(); await flush();
        await settle(p.last('fittings_review_eft'), eftReview());
      }
      importControl(p, stage === 'read' ? 'read' : stage === 'review' ? 'review' : 'add').click(); await flush();
      const pending = stage === 'read' ? p.reads.at(-1) : p.last('fittings_' + (stage === 'review' ? 'review_eft' : 'import_eft'));
      assert.ok(pending);
      if (revoke === 'typing') input(importControl(p, 'text'), 'Newer draft');
      if (revoke === 'route') { await p.route('main'); p.el('nav-main').focus(); }
      if (revoke === 'screenshot') await p.screenshot(devScreenshot());
      if (revoke === 'close') importControl(p, 'close').click();
      const active = p.focused(), text = importControl(p, 'text').value;
      await settle(pending, stage === 'read' ? 'Old clipboard' : stage === 'review' ? eftReview()
        : {applied: true, persisted: true, entry_id: 'imported', created: true, error: ''});
      assert.equal(importControl(p, 'text').value, text);
      assert.equal(p.focused(), active, 'a stale promise cannot reclaim focus');
      assert.equal(importControl(p, 'show').hidden, true);
      if (revoke === 'typing') assert.equal(importControl(p, 'candidate').textContent, '');
    });
  }
}

for (const failure of ['refused', 'reject']) {
  test('clipboard Add ' + failure + ' retains reviewed text and same-ID retry', async () => {
    const p = await reviewedImport();
    const before = importControl(p, 'candidate').textContent;
    importControl(p, 'add').click(); await flush();
    if (failure === 'reject') p.last('fittings_import_eft').reject(new Error('lost reply'));
    else await settle(p.last('fittings_import_eft'), {applied: false, persisted: false, entry_id: '', created: false, error: 'Disk full'});
    await flush();
    assert.equal(importControl(p, 'text').value, eftText);
    assert.equal(importControl(p, 'candidate').textContent, before);
    assert.equal(importControl(p, 'add').disabled, false);
    assert.equal(importControl(p, 'review').disabled, false, 're-review is available without requiring it for same-ID save retry');
    assert.equal(importControl(p, 'review').textContent, 'Review again');
    assert.match(importControl(p, 'status').textContent, failure === 'refused' ? /Disk full/ : /not confirmed/i);
    importControl(p, 'add').click(); await flush();
    assert.deepEqual(p.last('fittings_import_eft').args, ['opaque-review']);
    assert.equal(p.calls('fittings_review_eft').length, 1);
    await settle(p.last('fittings_import_eft'), {applied: true, persisted: true, entry_id: 'imported', created: false, error: ''});
    assert.match(importControl(p, 'status').textContent, /Already in.*library/i);
    assert.equal(importControl(p, 'candidate').textContent, before);
  });
}

test('clipboard fresh opener preserves newer typing and reopening drafts requires explicit replacement', async () => {
  const p = await importPage();
  assert.equal(p.reads.length, 1);
  const first = p.reads[0];
  input(importControl(p, 'text'), 'Manual draft');
  await settle(first, 'Stale initial clipboard');
  assert.equal(importControl(p, 'text').value, 'Manual draft');
  importControl(p, 'open').click();
  assert.equal(p.reads.length, 1, 'reopening a nonempty draft must not replace it');
  assert.equal(importControl(p, 'text').value, 'Manual draft');
  importControl(p, 'read').click();
  assert.equal(p.reads.length, 2, 'Read clipboard explicitly replaces an existing draft');
  await settle(p.reads.at(-1), eftText);
  assert.equal(importControl(p, 'text').value, eftText);
  assert.equal(p.calls('fittings_review_eft').length, 0);
  importControl(p, 'close').click(); importControl(p, 'open').click();
  assert.equal(p.reads.length, 3, 'closing starts a fresh empty-draft open');
});

test('clipboard opener keeps reviewed warnings and successful result instead of reading again', async () => {
  const p = await reviewedImport();
  const reads = p.reads.length;
  const candidate = importControl(p, 'candidate').textContent;
  await p.route('main'); await p.route('fittings');
  importControl(p, 'open').click();
  assert.equal(p.reads.length, reads);
  assert.equal(importControl(p, 'text').value, eftText);
  assert.equal(importControl(p, 'candidate').textContent, candidate);
  importControl(p, 'add').click(); await flush();
  await settle(p.last('fittings_import_eft'), {applied: true, persisted: true, entry_id: 'imported', created: true, error: ''});
  importControl(p, 'open').click();
  assert.equal(p.reads.length, reads, 'a cleared successful submission is not a fresh draft');
  assert.equal(importControl(p, 'candidate').textContent, candidate);
  assert.equal(importControl(p, 'show').hidden, false);
});

test('clipboard expiry refusal offers Review again without editing text or parsing backend prose', async () => {
  const p = await reviewedImport();
  const candidate = importControl(p, 'candidate').textContent;
  importControl(p, 'add').click(); await flush();
  // Exact current controller shape/message for expired OR consumed tickets.
  await settle(p.last('fittings_import_eft'), {applied: false, persisted: false, entry_id: '', created: false,
    error: 'Review the fitting text again before adding it.'});
  assert.equal(importControl(p, 'text').value, eftText);
  assert.equal(importControl(p, 'candidate').textContent, candidate);
  assert.equal(importControl(p, 'add').disabled, false);
  assert.equal(importControl(p, 'review').disabled, false);
  assert.equal(importControl(p, 'review').textContent, 'Review again');
  importControl(p, 'review').click(); await flush();
  assert.equal(p.calls('fittings_review_eft').length, 2);
  assert.deepEqual(p.last('fittings_review_eft').args, [eftText]);
  assert.equal(importControl(p, 'add').disabled, true, 'old ticket cannot be added during replacement review');
  await settle(p.last('fittings_review_eft'), {...eftReview(), review_id: 'fresh-review'});
  importControl(p, 'add').click(); await flush();
  assert.deepEqual(p.last('fittings_import_eft').args, ['fresh-review']);
  await settle(p.last('fittings_import_eft'), {applied: true, persisted: true, entry_id: 'imported', created: false, error: ''});
  assert.equal(importControl(p, 'text').value, '');
  assert.match(importControl(p, 'status').textContent, /Already in/);
});

for (const replyTiming of ['during-results', 'after-close']) {
  test('clipboard export cancelled by Last copy results: ' + replyTiming, async () => {
    const p = await editor();
    await beginCopy(p); await complete(p, result(['success']));
    p.el('fittings-copy-close').click();
    const copy = button(p.el('fittings-list'), 'Copy to clipboard');
    copy.click(); await flush();
    const exportReply = p.last('fittings_export_eft');
    button(p.el('fittings-notices'), 'Last copy results\u2026').click();
    if (replyTiming === 'after-close') p.el('fittings-copy-close').click();
    await settle(exportReply, {ok: true, text: 'obsolete export', error: ''});
    if (replyTiming === 'during-results') p.el('fittings-copy-close').click();
    assert.equal(p.writes.length, 0, 'results entry revokes delivery permanently, not just while the overlay is open');
    assert.equal(copy.disabled, false, 'cancelled export cannot strand its button');
    assert.doesNotMatch(p.el('fittings-list').textContent, /Preparing clipboard text/);
    copy.click(); await flush();
    assert.equal(p.calls('fittings_export_eft').length, 2, 'cancelled owner cannot block a new explicit export');
  });
}

test('clipboard import exposes its public ESI lookup notice before Review', async () => {
  const p = await importPage();
  const note = p.el('fittings-import-help');
  assert.match(note.textContent, /Type names may be looked up through ESI\./);
  assert.ok(note.getClientRects().length);
  assert.equal(p.calls('fittings_review_eft').length, 0);
});

test('clipboard invalid review retains text, exposes refusal, and never enables Add', async () => {
  const p = await importPage();
  input(importControl(p, 'text'), 'invalid');
  importControl(p, 'review').click(); await flush();
  await settle(p.last('fittings_review_eft'), {ok: false, review_id: '', name: '', ship_name: '',
    items: [], warnings: [], existing_entry_id: '', error: 'Line 1: expected a fitting header.'});
  assert.equal(importControl(p, 'text').value, 'invalid');
  assert.match(importControl(p, 'status').textContent, /Line 1/);
  assert.equal(importControl(p, 'candidate').textContent, '');
  assert.equal(importControl(p, 'add').disabled, true);
  importControl(p, 'add').dispatchEvent({type: 'click'});
  assert.equal(p.calls('fittings_import_eft').length, 0);
});

test('clipboard close returns focus locally; importing and selection paint preserve metadata nodes and scroll', async () => {
  const p = await editor();
  const name = p.el('fit-name-fit-1'), host = p.el('fittings-list');
  input(name, 'Metadata draft'); name.focus(); host.scrollTop = 76;
  importControl(p, 'open').click();
  input(importControl(p, 'text'), eftText);
  p.el('fittings-select-page').click();
  assert.equal(p.el('fit-name-fit-1'), name);
  assert.equal(name.value, 'Metadata draft');
  assert.equal(metadataDisclosure(p).open, true);
  assert.equal(host.scrollTop, 76);
  importControl(p, 'text').focus(); p.key('Escape');
  assert.equal(importControl(p, 'panel').hidden, true);
  assert.equal(p.focused(), importControl(p, 'open'));
});

test('clipboard Show fitting renders the locator snapshot directly when live ordering crosses a page boundary', async () => {
  const p = await addedImport();
  const before = p.calls('fittings_state').length;
  importControl(p, 'show').focus(); importControl(p, 'show').click(); await flush();
  assert.deepEqual(p.last('fittings_locate_entry').args, ['imported']);
  const snapshot = locatorSnapshot();
  // The live next read would exclude the target after a rename/insertion.
  // No second state call is permitted to recreate that race.
  await settle(p.last('fittings_locate_entry'), snapshot);
  assert.equal(p.calls('fittings_state').length, before);
  assert.equal(p.el('fittings-page-label').textContent, 'Page 2 of 3');
  assert.match(p.el('fittings-list').textContent, /Located snapshot/);
  assert.deepEqual(p.last('fittings_detail').args, ['imported']);
  await settle(p.last('fittings_detail'), detail('imported', 'Renamed after snapshot'));
  assert.match(p.el('fittings-list').textContent, /Saved description/);
  assert.deepEqual(selectedRows(p), []);
  assert.equal(importControl(p, 'candidate').querySelectorAll('.fit-import-warning').length, 3);
});

for (const revoke of ['search', 'page', 'collection', 'query', 'route', 'screenshot', 'row']) {
  test('clipboard Show fitting loses pending locator/focus to ' + revoke, async () => {
    const p = await addedImport();
    await p.changed({reason: 'refresh'});
    await settle(p.last('fittings_state'), state(['fit-1', 'fit-2']));
    importControl(p, 'show').focus(); importControl(p, 'show').click(); await flush();
    const pending = p.last('fittings_locate_entry');
    if (revoke === 'search') input(p.el('fittings-search'), 'new filter');
    if (revoke === 'page') p.el('fittings-page-next').dispatchEvent({type: 'click'});
    if (revoke === 'collection') p.el('fittings-collections').children[1].click();
    if (revoke === 'query') {
      await p.changed({reason: 'refresh'});
      await settle(p.last('fittings_state'), state(['newer']));
    }
    if (revoke === 'route') await p.route('main');
    if (revoke === 'screenshot') await p.screenshot(devScreenshot());
    if (revoke === 'row') p.el('fittings-list').querySelector('.fit-row-toggle').click();
    p.el('fittings-search').focus();
    const active = p.focused(), list = p.el('fittings-list').textContent;
    await settle(pending, locatorSnapshot());
    assert.equal(p.el('fittings-list').textContent, list);
    assert.equal(p.focused(), active);
    assert.equal(p.calls('fittings_detail').some(call => call.args[0] === 'imported'), false);
    assert.doesNotMatch(importControl(p, 'status').textContent, /Finding/);
  });
}

for (const phase of ['locate', 'detail']) {
  test('clipboard Show fitting deletion during ' + phase + ' ends with recoverable status, not endless Loading', async () => {
    const p = await addedImport();
    importControl(p, 'show').click(); await flush();
    if (phase === 'locate') await settle(p.last('fittings_locate_entry'), {ok: false, entry_id: '', workspace: null, error: 'Fitting no longer exists.'});
    else {
      await settle(p.last('fittings_locate_entry'), locatorSnapshot());
      await settle(p.last('fittings_detail'), null);
    }
    assert.match(importControl(p, 'status').textContent + p.el('fittings-list').textContent, /no longer|unavailable/i);
    assert.doesNotMatch(p.el('fittings-list').textContent, /Loading/);
    assert.equal(importControl(p, 'show').disabled, false);
  });
}

test('clipboard export uses saved identity and reports Copied only after actual write completion', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Unsaved different name');
  button(p.el('fittings-list'), 'Copy to clipboard').click(); await flush();
  assert.deepEqual(p.last('fittings_export_eft').args, ['fit-1']);
  assert.equal(p.writes.length, 0);
  await settle(p.last('fittings_export_eft'), {ok: true, text: '[Sabre, Saved name]\n', error: ''});
  assert.deepEqual(p.writes[0].args, ['[Sabre, Saved name]\n']);
  assert.doesNotMatch(p.el('fittings-list').textContent, /Copied to clipboard/);
  await settle(p.writes[0], undefined);
  assert.match(p.el('fittings-list').textContent, /Copied to clipboard/);
  assert.equal(p.el('fit-name-fit-1').value, 'Unsaved different name');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

for (const mode of ['refused', 'throw', 'reject', 'missing']) {
  test('clipboard export ' + mode + ' never claims Copied', async () => {
    const p = await page(mode === 'missing' ? {clipboard: false} : {writeText: mode});
    await p.route('fittings'); await settle(p.last('fittings_state'), state());
    p.el('fittings-list').querySelector('.fit-row-toggle').click(); await flush();
    await settle(p.last('fittings_detail'), detail());
    button(p.el('fittings-list'), 'Copy to clipboard').click(); await flush();
    await settle(p.last('fittings_export_eft'), mode === 'refused'
      ? {ok: false, text: '', error: 'Stored charge cannot be represented.'}
      : {ok: true, text: 'EFT', error: ''});
    if (mode === 'reject') { p.writes[0].reject(new Error('denied')); await flush(); }
    assert.doesNotMatch(p.el('fittings-list').textContent, /Copied to clipboard/);
    assert.match(p.el('fittings-list').textContent, mode === 'refused' ? /Stored charge/ : /clipboard.*(denied|unavailable|failed)|could not.*clipboard/i);
    assert.equal(button(p.el('fittings-list'), 'Copy to clipboard').disabled, false);
    if (mode !== 'reject') assert.equal(p.writes.length, 0);
  });
}

for (const revoke of ['collapse', 'row', 'route', 'source-push', 'rename', 'delete', 'screenshot', 'filter']) {
  test('clipboard export revokes before OS delivery on ' + revoke, async () => {
    const p = await editor();
    await repaint(p, state(['fit-1', 'fit-2']));
    const exportButton = button(p.el('fittings-list'), 'Copy to clipboard');
    exportButton.click(); await flush();
    const pending = p.last('fittings_export_eft');
    if (revoke === 'collapse') p.el('fittings-list').querySelector('.fit-row-toggle').click();
    if (revoke === 'row') p.el('fittings-list').querySelectorAll('.fit-row-toggle')[1].click();
    if (revoke === 'route') await p.route('main');
    if (revoke === 'source-push') await p.changed({reason: 'metadata', entry_id: 'fit-1'});
    if (revoke === 'rename') { input(p.el('fit-name-fit-1'), 'Rename'); button(metadata(p), 'Save').click(); }
    if (revoke === 'delete') { button(p.el('fittings-list'), 'Delete fitting').click(); await settle(p.confirmations.at(-1), true); }
    if (revoke === 'screenshot') await p.screenshot(devScreenshot());
    if (revoke === 'filter') input(p.el('fittings-search'), 'new');
    await settle(pending, {ok: true, text: 'stale text', error: ''});
    assert.equal(p.writes.length, 0, 'revocation must precede touching clipboard');
    const before = p.calls('fittings_export_eft').length;
    exportButton.dispatchEvent({type: 'click'});
    await flush();
    if (['collapse', 'row', 'route', 'screenshot'].includes(revoke)) {
      assert.equal(p.calls('fittings_export_eft').length, before, 'detached controls are not admission');
    }
  });
}

test('clipboard screenshot simulates only its explicit case and restores the detached real draft', async () => {
  const p = await reviewedImport();
  const fixture = devScreenshot();
  assert.ok(fixture.clipboard, 'dev.js must supply an explicit simulated clipboard case');
  const liveReads = p.reads.length;
  await p.screenshot(fixture);
  const before = p.calls().length;
  importControl(p, 'open').click(); importControl(p, 'read').click(); await flush();
  assert.equal(importControl(p, 'text').value, fixture.clipboard.text);
  importControl(p, 'review').click(); await flush();
  assert.equal(importControl(p, 'candidate').querySelectorAll('.fit-import-warning').length, 3);
  importControl(p, 'add').click(); await flush();
  importControl(p, 'show').click(); await flush();
  button(p.el('fittings-list'), 'Copy to clipboard').click(); await flush();
  assert.match(p.el('fittings-list').textContent, /simulated/i);
  assert.equal(p.calls().length, before);
  assert.equal(p.reads.length, liveReads); assert.equal(p.writes.length, 0);
  await p.screenshot({kind: 'fittings-screenshot-v1', clear: true});
  await p.route('fittings');
  assert.equal(importControl(p, 'text').value, eftText);
  assert.equal(importControl(p, 'candidate').querySelectorAll('.fit-import-warning').length, 3);
  assert.equal(importControl(p, 'show').hidden, true, 'synthetic result never becomes a real locator target');
  assert.equal(importControl(p, 'add').disabled, false);
});

test('clipboard dev endpoints and navigator shim simulate exact cases, not permissive fallback success', async () => {
  const source = fs.readFileSync(path.join(web, 'dev.js'), 'utf8');
  const start = source.indexOf('  // ---- simulated fittings clipboard ----');
  const end = source.indexOf('  // ---- end simulated fittings clipboard ----', start);
  assert.ok(start !== -1 && end > start, 'dev clipboard simulation must be explicit');
  const fixture = devScreenshot();
  assert.deepEqual(fixture.clipboard.review.items, fixture.details['fit-clipboard'].items,
    'the explicit screenshot review and saved example cannot drift');
  assert.equal(fixture.collections.find(row => row.id === 'all').count, fixture.entries.length);
  assert.equal(fixture.collections.find(row => row.id === 'unfiled').count,
    fixture.entries.filter(row => row.is_unfiled).length);
  let realClipboardCalls = 0;
  const navigator = {clipboard: {readText() { realClipboardCalls++; }, writeText() { realClipboardCalls++; }}};
  const api = {}, fittings = {entries: []};
  const context = vm.createContext({navigator, api, fittings, Promise,
    DEV_FITTINGS_SCREENSHOT_FIXTURE: fixture,
    fitPushChanged() {},
    // The existing dev workspace implementation is exercised separately by
    // page runtime. The locator must supply it directly, not expose an index.
    fitWorkspace(filters) { return {...state(['fit-clipboard']), page: filters.page}; },
    FIT_PAGE_SIZE: 100});
  const orderStart = source.indexOf('  function fitOrder(');
  const orderEnd = source.indexOf('  function fitWorkspace(', orderStart);
  vm.runInContext(source.slice(orderStart, orderEnd) + source.slice(start, end), context);
  const text = await navigator.clipboard.readText();
  assert.equal(text, fixture.clipboard.text);
  const refused = await api.fittings_review_eft('not the authored fixture');
  assert.equal(refused.ok, false); assert.equal(refused.review_id, '');
  assert.deepEqual(Array.from(refused.items), []);
  const review = await api.fittings_review_eft(text);
  assert.equal(review.ok, true); assert.equal(review.warnings.length, 3);
  assert.equal((await api.fittings_import_eft('guessed')).applied, false);
  const created = await api.fittings_import_eft(review.review_id);
  assert.equal(created.created, true); assert.equal(created.persisted, true);
  const repeated = await api.fittings_review_eft(text);
  assert.equal((await api.fittings_import_eft(repeated.review_id)).created, false);
  assert.equal((await api.fittings_export_eft('unknown')).ok, false);
  const exported = await api.fittings_export_eft(created.entry_id);
  assert.equal(exported.ok, true);
  await navigator.clipboard.writeText(exported.text);
  assert.equal(await navigator.clipboard.readText(), exported.text);
  assert.equal(realClipboardCalls, 0, 'dev must never fall back to the real browser clipboard');
  assert.equal((await api.fittings_locate_entry(created.entry_id)).workspace.rows[0].id, 'fit-clipboard');
  assert.equal((await api.fittings_locate_entry('deleted')).ok, false);
});

for (const phase of ['read', 'review', 'add', 'locate']) {
  test('clipboard ' + phase + ' survives a generic dialog without stranding its pending owner', async () => {
    const p = phase === 'locate' ? await addedImport() : phase === 'add' ? await reviewedImport() : await importPage();
    if (phase === 'review') input(importControl(p, 'text'), eftText);
    importControl(p, phase === 'locate' ? 'show' : phase).click(); await flush();
    p.el('overlay').hidden = false; p.el('dlg-ok').focus();
    const pending = phase === 'read' ? p.reads[0] : p.last('fittings_' +
      ({review: 'review_eft', add: 'import_eft', locate: 'locate_entry'}[phase]));
    await settle(pending, phase === 'read' ? eftText : phase === 'review' ? eftReview()
      : phase === 'locate' ? locatorSnapshot() : {applied: true, persisted: true, entry_id: 'imported', created: true, error: ''});
    assert.equal(p.focused(), p.el('dlg-ok'));
    p.el('overlay').hidden = true;
    assert.equal(importControl(p, 'read').disabled, false);
    assert.doesNotMatch(importControl(p, 'status').textContent, /Reading|Reviewing|Adding|Finding/);
  });
}

for (const phase of ['review', 'add', 'export', 'locate']) {
  test('clipboard bridge ' + phase + ' synchronous refusal remains recoverable', async () => {
    const p = phase === 'add' ? await reviewedImport() : phase === 'locate' ? await addedImport()
      : phase === 'export' ? await editor() : await importPage();
    const method = 'fittings_' + ({review: 'review_eft', add: 'import_eft', export: 'export_eft', locate: 'locate_entry'}[phase]);
    p.throwBridge(method);
    if (phase === 'review') input(importControl(p, 'text'), eftText);
    if (phase === 'export') button(p.el('fittings-list'), 'Copy to clipboard').click();
    else importControl(p, phase === 'locate' ? 'show' : phase).click();
    await flush();
    const status = phase === 'export' ? p.el('fittings-list').textContent : importControl(p, 'status').textContent;
    assert.match(status, /not confirmed|unavailable/i);
    assert.equal(p.errors.length, 1, 'WM.send catches the synchronous bridge exception');
    assert.equal(p.writes.length, 0);
    if (phase === 'add') assert.equal(importControl(p, 'add').disabled, false);
  });
}

test('clipboard Show fitting fences both a previous query and its delayed detail against newer search', async () => {
  const p = await addedImport();
  await p.changed({reason: 'refresh'});
  const oldState = p.last('fittings_state');
  importControl(p, 'show').focus(); importControl(p, 'show').click(); await flush();
  await settle(p.last('fittings_locate_entry'), locatorSnapshot());
  const lateDetail = p.last('fittings_detail');
  await settle(oldState, state(['old-page']));
  assert.match(p.el('fittings-list').textContent, /Located snapshot/);
  input(p.el('fittings-search'), 'new'); p.el('fittings-search').focus();
  await p.timers(); await settle(p.last('fittings_state'), state(['new-page']));
  await settle(lateDetail, detail('imported', 'Stale', 'Do not render this'));
  assert.doesNotMatch(p.el('fittings-list').textContent, /Located snapshot|Do not render/);
  assert.equal(p.focused(), p.el('fittings-search'));
});

for (const outcome of ['resolve', 'reject']) {
  test('clipboard write ' + outcome + ' after collapse cannot repaint or block a new export', async () => {
    const p = await editor();
    button(p.el('fittings-list'), 'Copy to clipboard').click(); await flush();
    await settle(p.last('fittings_export_eft'), {ok: true, text: 'text', error: ''});
    p.el('fittings-list').querySelector('.fit-row-toggle').click();
    p.el('fittings-list').querySelector('.fit-row-toggle').click(); await flush();
    await settle(p.last('fittings_detail'), detail());
    if (outcome === 'reject') { p.writes[0].reject(new Error('late')); await flush(); }
    else await settle(p.writes[0], undefined);
    assert.doesNotMatch(p.el('fittings-list').textContent, /Copied to clipboard|Could not write/);
    button(p.el('fittings-list'), 'Copy to clipboard').click(); await flush();
    assert.equal(p.calls('fittings_export_eft').length, 2);
  });
}

test('clipboard workspace scroll survives list replacement and focus handoff stays local to the invoking export', async () => {
  const p = await editor();
  const scroller = p.el('fittings-workspace-scroll');
  const host = p.el('fittings-list');
  // Simulate the browser clamping the enclosing scroller when its tall child
  // is emptied. Restoring the retired list's own scrollTop cannot recover it.
  host.onChildrenCleared = () => { scroller.scrollTop = 0; };
  scroller.scrollTop = 214;
  input(p.el('fit-name-fit-1'), 'Kept');
  await repaint(p);
  assert.equal(scroller.scrollTop, 214);
  const copy = button(host, 'Copy to clipboard');
  copy.focus(); copy.click(); await flush();
  assert.equal(p.focused(), p.el('fit-toggle-fit-1'), 'handoff precedes disabling the focused export');
  assert.equal(scroller.scrollTop, 214);
  p.el('fittings-search').focus();
  await settle(p.last('fittings_export_eft'), {ok: true, text: 'text', error: ''});
  await settle(p.writes[0], undefined);
  assert.equal(p.focused(), p.el('fittings-search'), 'a completed write does not take focus back');
});

test('clipboard shown target deleted by push remains recoverable when its old detail is fenced out', async () => {
  const p = await addedImport();
  importControl(p, 'show').click(); await flush();
  await settle(p.last('fittings_locate_entry'), locatorSnapshot());
  const pending = p.last('fittings_detail');
  await p.changed({reason: 'delete', entry_id: 'imported'});
  await settle(p.last('fittings_state'), state([]));
  await settle(pending, detail('imported'));
  assert.match(importControl(p, 'status').textContent, /no longer exists/);
  assert.doesNotMatch(p.el('fittings-list').textContent, /Loading/);
  assert.equal(importControl(p, 'show').disabled, false);
});

test('clipboard locator focus relinquishment cannot revive when focus returns to Show', async () => {
  const p = await addedImport();
  p.focusEvent(importControl(p, 'show')); importControl(p, 'show').click(); await flush();
  p.focusEvent(p.el('fittings-search'));
  p.focusEvent(importControl(p, 'show'));
  await settle(p.last('fittings_locate_entry'), locatorSnapshot());
  assert.equal(p.focused(), importControl(p, 'show'));
});

test('clipboard export released by row repaint permits another export rather than retaining detached controls', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'draft');
  button(p.el('fittings-list'), 'Copy to clipboard').click(); await flush();
  const old = p.last('fittings_export_eft');
  button(metadata(p), 'Discard changes').click(); await settle(p.confirmations.at(-1), true);
  await settle(old, {ok: true, text: 'obsolete', error: ''});
  assert.equal(p.writes.length, 0);
  button(p.el('fittings-list'), 'Copy to clipboard').click(); await flush();
  assert.equal(p.calls('fittings_export_eft').length, 2);
});

test('clipboard screenshot without an explicit clipboard fixture fails closed for every new operation', async () => {
  const p = await editor();
  const fixture = devScreenshot(); delete fixture.clipboard;
  await p.screenshot(fixture);
  const before = p.calls().length;
  importControl(p, 'open').click(); importControl(p, 'read').click(); await flush();
  input(importControl(p, 'text'), eftText); importControl(p, 'review').click(); await flush();
  importControl(p, 'add').dispatchEvent({type: 'click'});
  importControl(p, 'show').dispatchEvent({type: 'click'});
  p.el('fittings-list').querySelector('.fit-row-toggle').click(); await flush();
  const copy = p.el('fittings-list').querySelectorAll('button').find(node => node.textContent === 'Copy to clipboard');
  if (copy) copy.click();
  await flush();
  assert.equal(p.calls().length, before);
  assert.equal(p.reads.length, 0); assert.equal(p.writes.length, 0);
  assert.match(importControl(p, 'status').textContent, /screenshot/i);
});

test('empty worker refusal is explained without claiming successful completion', async () => {
  const p = await editor();
  await beginCopy(p);
  await complete(p, { status: 'invalid_ticket', operation_id: '', results: [], write_count: 0 });
  assert.equal(p.el('fittings-copy-summary').textContent, 'No copy results.');
  assert.match(p.el('fittings-copy-body').textContent, /expired.*review/i);
  assert.doesNotMatch(p.el('fittings-copy-body').textContent, /all.*copied/i);
  assert.equal(p.calls('fittings_start_copy').length, 1);
});
