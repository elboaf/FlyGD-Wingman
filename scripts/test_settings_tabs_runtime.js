#!/usr/bin/env node
'use strict';

// Execute the complete production shell and Settings/Preview owners. The DOM is
// a boundary double built from the real markup, not a CSS/WebView2 renderer.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createDOM} = require('../tests/fixtures/screenshot_dom.cjs');
const web = path.join(__dirname, '../wingman/web');
const markup = JSON.parse(fs.readFileSync(0, 'utf8'));
const tests = [];
function test(name, run) { tests.push({name, run}); }
function turn() { return new Promise(resolve => setImmediate(resolve)); }
const accepted = {applied: true, persisted: true, error: null};
const refused = {applied: false, persisted: false, error: 'Not accepted'};
const tabs = {previews: ['windows', 'characters', 'wanderer'], uploading: ['youtube', 'recording', 'combatlogs']};

function previewPayload(overrides = {}) {
  return {hotkeys: {characters: {}, cycle_next: '', cycle_prev: '',
    groups: [{id: 'group-a', name: 'Group A'}], group_by_character: {}},
    characters: ['Alice'], roster: ['Alice'], registration: {},
    bookmark_chords: {active: [], latent: []}, enabled: true, locked: [], lock_default: false,
    never_minimize: [], excluded: [], sizes: {}, client_sizes: {}, sizable: [], layout_sources: [],
    ...overrides};
}

async function page({previews = false, settings = false} = {}) {
  const {document, Element, scrolls} = createDOM(markup);
  document.activeElement = document.body;
  // This harness needs capture/bubble ordering; the shared screenshot DOM does not.
  Element.prototype.addEventListener = function (type, callback, options) {
    const capture = options === true || !!(options && options.capture);
    (this.listeners[type] ||= []).push({callback, capture});
  };
  Element.prototype.removeEventListener = function (type, callback, options) {
    const capture = options === true || !!(options && options.capture);
    this.listeners[type] = (this.listeners[type] || []).filter(listener =>
      listener.callback !== callback || listener.capture !== capture);
  };
  Element.prototype.dispatchEvent = function (event) {
    event.target = this;
    event.defaultPrevented = false;
    let stopped = false, immediate = false;
    event.preventDefault = () => { event.defaultPrevented = true; };
    event.stopPropagation = () => { stopped = true; };
    event.stopImmediatePropagation = () => { immediate = stopped = true; };
    const ancestors = [];
    for (let node = this.parentNode; node; node = node.parentNode) ancestors.push(node);
    function invoke(node, capture) {
      event.currentTarget = node;
      for (const listener of (node.listeners[event.type] || []).slice()) {
        if (immediate) break;
        if (listener.capture === capture) listener.callback(event);
      }
    }
    for (const node of ancestors.slice().reverse()) {
      invoke(node, true); if (stopped) return !event.defaultPrevented;
    }
    invoke(this, true); invoke(this, false);
    if (event.bubbles && !stopped) {
      for (const node of ancestors) { invoke(node, false); if (stopped) break; }
    }
    return !event.defaultPrevented;
  };
  Element.prototype.focus = function () {
    if (document.activeElement === this) return;
    document.activeElement = this;
    this.dispatchEvent({type: 'focusin', bubbles: true});
  };
  function add(tag, attrs, parent = document.body) {
    const node = new Element(tag, attrs); parent.appendChild(node); return node;
  }
  const el = id => document.getElementById(id);
  add('input', {id: 'retained-draft'}, el('settings-previews-wanderer'));
  add('details', {id: 'retained-disclosure'}, el('settings-previews-wanderer'));

  const calls = [], errors = [], events = [], sections = [];
  const window = {document, addEventListener() {}, location: {search: ''},
    getComputedStyle() { return {visibility: 'visible'}; },
    localStorage: {getItem() { throw Error('tabs must not read persisted state'); },
      setItem() { throw Error('tabs must not persist state'); }}};
  const context = vm.createContext({window, document, Promise,
    console: {error: (...args) => errors.push(args.join(' ')), warn() {}, log() {}},
    CustomEvent: function (type, options = {}) { return {type, detail: options.detail}; }});
  function load(name) {
    vm.runInContext(fs.readFileSync(path.join(web, name + '.js'), 'utf8'), context, {filename: name + '.js'});
  }
  load('app');
  const WM = window.WM; context.WM = WM;
  function defer(method, args) {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    calls.push({method, args: JSON.parse(JSON.stringify(args)), resolve});
    return promise;
  }
  WM.send = (method, ...args) => defer(method, args);
  WM.choose = (...args) => defer('choose', args);
  WM.prompt = (...args) => defer('prompt', args);
  WM.confirm = () => Promise.resolve(true);
  document.addEventListener('wm:settings-tab', event => events.push(JSON.parse(JSON.stringify(event.detail))));
  document.addEventListener('wm:section', event => sections.push(event.detail));
  if (previews) load('previews');
  if (settings) {
    load('settings');
    document.dispatchEvent({type: 'wm:settings', detail: {settings: {
      privacy: 'unlisted', category: '20', notify_mode: 'toast', show_eve_tools: true,
      recording_dir: 'C:\\old', gamelogs_dir: 'C:\\logs',
      discord_webhook: 'https://discord.com/api/webhooks/1/old', preview: {}
    }, detected: {}, webhook_status: 'configured hook'}});
  }
  const p = {WM, document, window, el, calls, errors, events, sections, scrolls,
    button: (section, name) => el('settings-tab-' + section + '-' + name),
    panel: (section, name) => el('settings-' + section + '-' + name),
    async fire(node, type, extra = {}) {
      assert.ok(node, 'event target exists');
      const event = {type, bubbles: true, ...extra};
      node.dispatchEvent(event);
      await turn(); assert.deepEqual(errors, []); return event;
    },
    async click(section, name) {
      const button = this.button(section, name);
      await this.fire(button, 'pointerdown'); button.focus();
      return this.fire(button, 'click');
    },
    async edit(id, value) { el(id).value = value; await this.fire(el(id), 'input'); },
    async reply(method, result, args) {
      const index = calls.findIndex(call => call.method === method);
      assert.notEqual(index, -1, 'Expected pending call to ' + method);
      const call = calls.splice(index, 1)[0];
      if (args) assert.deepEqual(call.args, args);
      call.resolve(result); await turn(); assert.deepEqual(errors, []);
    },
    async previewState() {
      window.onPreviewHotkeys(previewPayload());
      await turn(); assert.deepEqual(errors, []);
    }
  };
  await turn(); assert.deepEqual(errors, []); return p;
}

function selected(p, section, wanted) {
  for (const name of tabs[section]) {
    assert.equal(p.button(section, name).getAttribute('aria-selected'), String(name === wanted));
    assert.equal(String(p.button(section, name).getAttribute('tabindex')), name === wanted ? '0' : '-1');
    assert.equal(p.panel(section, name).hidden, name !== wanted);
  }
}

test('mouse activation toggles only static subpages, emits once, and retains drafts and scroll', async () => {
  const p = await page(); p.WM.openSettingsSection('previews');
  const draft = p.el('retained-draft'), disclosure = p.el('retained-disclosure');
  draft.value = 'unsaved'; disclosure.open = true; p.panel('previews', 'wanderer').scrollTop = 123;
  const sections = p.sections.slice(), calls = p.calls.length;
  await p.click('previews', 'wanderer'); selected(p, 'previews', 'wanderer');
  assert.deepEqual(p.events, [{section: 'previews', tab: 'wanderer', previous: 'windows'}]);
  await p.click('previews', 'wanderer');
  assert.equal(p.events.length, 1, 'same tab is a no-op');
  await p.click('previews', 'characters'); await p.click('previews', 'wanderer');
  assert.equal(p.el('retained-draft'), draft); assert.equal(draft.value, 'unsaved');
  assert.equal(p.el('retained-disclosure'), disclosure); assert.equal(disclosure.open, true);
  assert.equal(p.panel('previews', 'wanderer').scrollTop, 123);
  assert.deepEqual(p.sections, sections); assert.equal(p.calls.length, calls);
  assert.deepEqual(p.scrolls, []);
});

test('Left/Right wrap and Home/End activate with roving focus; unrelated keys pass through', async () => {
  const p = await page(); p.WM.openSettingsSection('uploading');
  for (const [from, key, to] of [['youtube', 'ArrowLeft', 'combatlogs'],
    ['combatlogs', 'ArrowRight', 'youtube'], ['youtube', 'End', 'combatlogs'],
    ['combatlogs', 'Home', 'youtube'], ['youtube', 'ArrowRight', 'recording']]) {
    p.button('uploading', from).focus();
    const event = await p.fire(p.button('uploading', from), 'keydown', {key});
    assert.equal(event.defaultPrevented, true); selected(p, 'uploading', to);
    assert.equal(p.document.activeElement, p.button('uploading', to));
  }
  for (const key of ['Tab', 'ArrowDown', 'x']) {
    const event = await p.fire(p.button('uploading', 'recording'), 'keydown', {key});
    assert.equal(event.defaultPrevented, false); selected(p, 'uploading', 'recording');
  }
});

test('invalid and gated targets are no-ops, including deep links after gate resolution', async () => {
  const p = await page(); p.WM.openSettingsSection('previews', 'characters');
  selected(p, 'previews', 'characters');
  p.el('retained-draft').focus(); const focused = p.document.activeElement;
  const count = p.events.length;
  for (const [section, tab] of [['previews', 'missing'], ['missing', 'windows'],
    ['previews', 'youtube'], ['previews', 'characters'], ['previews', '"bad']]) {
    p.WM.settingsTab(section, tab);
  }
  assert.equal(p.events.length, count); assert.equal(p.document.activeElement, focused);
  p.WM.apply_eve_gate(false);
  p.WM.settingsTab('previews', 'wanderer');
  p.WM.openSettingsSection('previews', 'wanderer');
  assert.equal(p.WM.current_section, 'general'); selected(p, 'previews', 'characters');
  assert.equal(p.events.length, count);
  p.WM.route('main'); p.WM.openSettingsSection('previews', 'windows');
  assert.equal(p.WM.current_route, 'settings'); assert.equal(p.WM.current_section, 'general');
  selected(p, 'previews', 'characters');
  p.WM.openSettingsSection('uploading', 'combatlogs'); selected(p, 'uploading', 'combatlogs');
});

test('ordinary entry remembers live selection; explicit deep links override without duplicate entry', async () => {
  const p = await page(); p.WM.route('skills');
  p.WM.openSettingsSection('previews', 'characters');
  assert.deepEqual(p.sections, ['', 'previews']); selected(p, 'previews', 'characters');
  p.WM.section('uploading'); p.WM.section('previews'); selected(p, 'previews', 'characters');
  p.WM.route('main'); p.WM.route('settings'); selected(p, 'previews', 'characters');
  p.WM.openSettingsSection('previews', 'wanderer'); selected(p, 'previews', 'wanderer');
  p.WM.openSettingsSection('previews'); selected(p, 'previews', 'wanderer');
  const fresh = await page(); selected(fresh, 'previews', 'windows'); selected(fresh, 'uploading', 'youtube');
});

test('programmatic activation rescues focus from a hidden panel without stealing outside focus', async () => {
  const p = await page(); p.WM.openSettingsSection('uploading', 'combatlogs');
  p.el('f-webhook').focus(); p.WM.settingsTab('uploading', 'recording');
  assert.equal(p.document.activeElement, p.button('uploading', 'recording'));
  p.el('btn-settings').focus(); p.WM.settingsTab('uploading', 'youtube');
  assert.equal(p.document.activeElement, p.el('btn-settings'));
  p.WM.route('main'); p.WM.settingsTab('previews', 'characters');
  assert.equal(p.document.activeElement, p.el('btn-settings'), 'hidden section cannot take focus');
});

for (const destination of ['tab', 'keyboard', 'section', 'route']) {
  test('real Preview capture releases on ' + destination + ' leave without swallowing the next key', async () => {
    const p = await page({previews: true}); p.WM.openSettingsSection('previews', 'characters');
    await p.previewState();
    const capture = p.el('preview-binds').querySelector('.bindbtn');
    await p.fire(capture, 'click'); await p.reply('set_bind_capture', true, [true]);
    assert.equal(capture.classList.contains('capturing'), true);
    const reads = p.calls.filter(call => call.method === 'get_preview_hotkey_state').length;
    assert.ok(reads > 0, 'Preview entry hydrated through the real owner');
    if (destination === 'tab') await p.click('previews', 'windows');
    if (destination === 'keyboard') {
      p.button('previews', 'characters').focus();
      await p.fire(p.button('previews', 'characters'), 'keydown', {key: 'ArrowRight', code: 'ArrowRight'});
    }
    if (destination === 'section') p.WM.section('uploading');
    if (destination === 'route') p.WM.route('main');
    await p.reply('set_bind_capture', true, [false]);
    assert.equal(capture.classList.contains('capturing'), false);
    const key = await p.fire(p.document, 'keydown', {key: 'x', code: 'KeyX'});
    assert.equal(key.defaultPrevented, false);
    assert.equal(p.calls.some(call => call.method === 'capture_preview_bind'), false);
    assert.equal(p.calls.filter(call => call.method === 'get_preview_hotkey_state').length, reads);
  });
}

test('armed Preview capture stops keydown before target and bubble handlers', async () => {
  const p = await page({previews: true}); p.WM.openSettingsSection('previews', 'characters');
  await p.previewState();
  const capture = p.el('preview-binds').querySelector('.bindbtn');
  capture.focus(); await p.fire(capture, 'click'); await p.reply('set_bind_capture', true, [true]);
  const reached = [];
  capture.addEventListener('keydown', () => reached.push('target'));
  p.document.addEventListener('keydown', () => reached.push('bubble'));
  p.document.addEventListener('keydown', () => reached.push('capture sibling'), true);
  const event = await p.fire(capture, 'keydown', {key: 'ArrowRight', code: 'ArrowRight'});
  assert.equal(event.defaultPrevented, true);
  assert.deepEqual(reached, ['capture sibling']);
  assert.equal(p.calls.filter(call => call.method === 'capture_preview_bind').length, 1);
});

for (const entry of ['focus', 'click', 'pointerdown']) {
  test('Preview tablist ' + entry + ' disarms capture even on the selected tab', async () => {
    const p = await page({previews: true}); p.WM.openSettingsSection('previews', 'characters');
    await p.previewState();
    const capture = p.el('preview-binds').querySelector('.bindbtn');
    capture.focus(); await p.fire(capture, 'click'); await p.reply('set_bind_capture', true, [true]);
    assert.equal(capture.classList.contains('capturing'), true);
    const button = p.button('previews', 'characters');
    const events = p.events.slice(), sections = p.sections.slice();
    const reads = p.calls.filter(call => call.method === 'get_preview_hotkey_state').length;
    if (entry === 'focus') button.focus();
    if (entry === 'click') await p.click('previews', 'characters');
    if (entry === 'pointerdown') {
      await p.fire(button, 'pointerdown');
      assert.equal(capture.classList.contains('capturing'), false, 'pointerdown disarms before focus');
      button.focus();
    }
    selected(p, 'previews', 'characters');
    assert.deepEqual(p.events, events, 'same-tab entry emits no tab change');
    const key = await p.fire(button, 'keydown', {key: 'ArrowRight', code: 'ArrowRight'});
    assert.equal(p.calls.some(call => call.method === 'capture_preview_bind'), false,
      'tab navigation must not be captured as a Preview bind');
    assert.equal(key.defaultPrevented, true); selected(p, 'previews', 'wanderer');
    assert.equal(p.document.activeElement, p.button('previews', 'wanderer'));
    await p.reply('set_bind_capture', true, [false]);
    assert.equal(capture.classList.contains('capturing'), false);
    assert.equal(p.events.length, events.length + 1);
    assert.deepEqual(p.sections, sections);
    assert.equal(p.calls.filter(call => call.method === 'get_preview_hotkey_state').length, reads);
  });
}

test('late Preview group reply cannot restore focus after a subpage navigation', async () => {
  const p = await page({previews: true}); p.WM.openSettingsSection('previews', 'characters');
  await p.previewState();
  await p.fire(p.el('preview-binds').querySelector('.preview-configure'), 'click');
  const group = p.document.querySelector('[data-preview-detail-control="group"]');
  group.value = 'group-a'; group.focus(); await p.fire(group, 'change');
  await p.click('previews', 'wanderer'); p.document.activeElement = p.document.body;
  await p.reply('set_preview_character_group', {applied: true, persisted: true});
  assert.ok(p.document.activeElement === p.document.body, 'late reply must not focus a hidden detail');
});

async function copyingPreview() {
  const p = await page({previews: true}); p.WM.openSettingsSection('previews', 'characters');
  const initial = previewPayload({layout_sources: [{name: 'Bob', online: null}]});
  // Drain real boot/section hydration so only Copy can request the next read.
  while (p.calls.some(call => call.method === 'get_preview_hotkey_state')) {
    await p.reply('get_preview_hotkey_state', initial);
  }
  await p.fire(p.el('preview-binds').querySelector('.preview-configure'), 'click');
  const copy = p.document.querySelector('[data-preview-detail-control="copy"]');
  copy.focus(); await p.fire(copy, 'click'); await p.reply('choose', 'Bob');
  assert.deepEqual(p.calls.map(call => [call.method, call.args]), [
    ['copy_preview_layout', ['Alice', 'Bob']]
  ]);
  return p;
}

function copyOutcome(p, text, error) {
  const status = p.el('preview-copy-status');
  assert.equal(status.textContent, text);
  assert.equal(status.hidden, false, 'Copy outcome stays available on return');
  assert.equal(status.classList.contains('err'), error);
}

for (const [label, outcome, text, error] of [
  ['accepted', accepted, 'Copied Bob’s geometry to Alice.', false],
  ['refused', refused, 'Not accepted', true],
  ['unconfirmed', null, 'That preview placement could not be copied.', true]
]) for (const transition of ['before result', 'before result and back', 'during refresh']) {
  test('Copy ' + label + ' survives subpage navigation ' + transition, async () => {
    const p = await copyingPreview(), sections = p.sections.slice();
    if (transition !== 'during refresh') {
      await p.click('previews', 'windows');
      if (transition === 'before result and back') await p.click('previews', 'characters');
      assert.deepEqual(p.calls.map(call => call.method), ['copy_preview_layout'],
        'subpage navigation must not rehydrate');
    }
    const focused = p.document.activeElement;
    await p.reply('copy_preview_layout', outcome, ['Alice', 'Bob']);
    copyOutcome(p, text, error);
    assert.equal(p.document.activeElement, focused, 'receipt alone must not move focus');
    assert.deepEqual(p.calls.map(call => call.method), ['get_preview_hotkey_state'],
      'completion requests its authoritative refresh even while hidden');
    if (transition === 'during refresh') await p.click('previews', 'windows');
    const nextFocus = p.document.activeElement;
    const refreshed = previewPayload({sizes: {Alice: [480, 300]}, sizable: ['Alice'],
      layout_sources: [{name: 'Carol', online: null}]});
    await p.reply('get_preview_hotkey_state', refreshed);
    assert.equal(p.document.activeElement, nextFocus, 'late refresh cannot restore stale Copy focus');
    await p.click('previews', 'characters'); selected(p, 'previews', 'characters');
    copyOutcome(p, text, error);
    assert.deepEqual(p.sections, sections, 'tabs must not fake section events');
    assert.deepEqual(p.calls, [], 'return does not refetch');
    const size = p.document.querySelector('[data-preview-detail-control="size"]');
    assert.ok(size, 'authoritative eligibility makes Size available');
    await p.fire(size, 'click');
    assert.equal(p.calls[0].method, 'prompt');
    assert.equal(p.calls[0].args[2], '480x300', 'Size uses refreshed dimensions');
    await p.reply('prompt', null);
    await p.fire(p.document.querySelector('[data-preview-detail-control="copy"]'), 'click');
    assert.deepEqual(p.calls[0].args[2], [
      {label: 'Saved placements', options: [{value: 'Carol', label: 'Carol'}]}
    ], 'the next chooser uses refreshed source eligibility, not Bob');
    await p.reply('choose', null);
  });
}

test('Copy refresh can remove its source control without focusing a hidden panel', async () => {
  const p = await copyingPreview();
  await p.click('previews', 'windows');
  await p.reply('copy_preview_layout', accepted);
  p.document.activeElement = p.document.body;
  await p.reply('get_preview_hotkey_state', previewPayload());
  assert.equal(p.document.activeElement, p.document.body, 'no hidden Configure fallback focus');
  await p.click('previews', 'characters');
  assert.equal(p.document.querySelector('[data-preview-detail-control="copy"]'), null);
  assert.equal(p.el('preview-copy-empty').hidden, false);
  copyOutcome(p, 'Copied Bob’s geometry to Alice.', false);
});

test('Copy still restores its recreated control when there was no navigation', async () => {
  const p = await copyingPreview();
  const oldCopy = p.document.activeElement;
  await p.reply('copy_preview_layout', accepted);
  await p.reply('get_preview_hotkey_state', previewPayload({layout_sources: [{name: 'Bob', online: null}]}));
  const newCopy = p.document.querySelector('[data-preview-detail-control="copy"]');
  assert.notEqual(newCopy, oldCopy);
  assert.equal(p.document.activeElement, newCopy);
  copyOutcome(p, 'Copied Bob’s geometry to Alice.', false);
});

for (const stale of [accepted, refused, null]) {
  test('superseded Copy ' + JSON.stringify(stale) + ' cannot overwrite a newer result after tabs', async () => {
    const p = await copyingPreview();
    const old = p.calls.shift();
    await p.click('previews', 'windows'); await p.click('previews', 'characters');
    await p.fire(p.document.querySelector('[data-preview-detail-control="copy"]'), 'click');
    await p.reply('choose', 'Bob');
    await p.reply('copy_preview_layout', {applied: false, persisted: false, error: 'Newer refusal'});
    await p.reply('get_preview_hotkey_state', previewPayload({layout_sources: [{name: 'Bob', online: null}]}));
    copyOutcome(p, 'Newer refusal', true);
    const focused = p.document.activeElement;
    old.resolve(stale); await turn();
    copyOutcome(p, 'Newer refusal', true);
    assert.equal(p.document.activeElement, focused);
    assert.deepEqual(p.calls, [], 'superseded completion must not trigger a refresh');
    assert.deepEqual(p.errors, []);
  });
}

for (const leave of ['configure', 'section', 'route']) {
  test('Copy completion remains invalidated by ' + leave, async () => {
    const p = await copyingPreview();
    if (leave === 'configure') await p.fire(p.el('preview-binds').querySelector('.preview-configure'), 'click');
    if (leave === 'section') p.WM.section('uploading');
    if (leave === 'route') p.WM.route('main');
    const focused = p.document.activeElement;
    await p.reply('copy_preview_layout', accepted);
    assert.equal(p.el('preview-copy-status').hidden, true);
    assert.equal(p.el('preview-copy-status').textContent, '');
    assert.equal(p.document.activeElement, focused);
    assert.deepEqual(p.calls, [], 'invalidated completion must not refresh');
  });
}

test('webhook is remasked on combatlogs leave, preserving section/route leave and same-tab reveal', async () => {
  const p = await page({settings: true}); p.WM.openSettingsSection('uploading', 'combatlogs');
  await p.fire(p.el('btn-webhook-show'), 'click'); assert.equal(p.el('f-webhook').type, 'text');
  await p.click('uploading', 'combatlogs'); assert.equal(p.el('f-webhook').type, 'text');
  await p.click('uploading', 'youtube');
  assert.equal(p.el('f-webhook').type, 'password');
  assert.equal(p.el('btn-webhook-show').textContent, 'Show');
  assert.equal(p.el('btn-webhook-show').getAttribute('aria-pressed'), 'false');
  for (const leave of [() => p.WM.section('previews'), () => p.WM.route('main')]) {
    p.WM.openSettingsSection('uploading', 'combatlogs');
    await p.fire(p.el('btn-webhook-show'), 'click'); leave();
    assert.equal(p.el('f-webhook').type, 'password');
  }
});

for (const [id, tab, method, submitted, draft] of [
  ['f-category', 'youtube', 'set_category', '22', '23'],
  ['f-recdir', 'recording', 'set_folder', 'C:\\accepted', 'C:\\draft'],
  ['f-webhook', 'combatlogs', 'set_discord_webhook', 'https://discord.com/api/webhooks/1/new', 'later draft']
]) for (const outcome of [accepted, refused, null]) {
  test(id + ' delayed ' + JSON.stringify(outcome) + ' reply retains newer drafts across tabs', async () => {
    const p = await page({settings: true}); p.WM.openSettingsSection('uploading', tab);
    const input = p.el(id); input.focus(); await p.edit(id, submitted);
    await p.fire(input, id === 'f-category' ? 'change' : 'keydown', {key: 'Enter'});
    await p.edit(id, draft);
    const away = tab === 'youtube' ? 'recording' : 'youtube';
    await p.click('uploading', away); selected(p, 'uploading', away);
    await p.reply(method, outcome);
    await p.click('uploading', tab); selected(p, 'uploading', tab);
    assert.equal(p.el(id), input); assert.equal(input.value, draft);
    assert.equal(p.calls.some(call => call.method === 'get_settings'), false);
  });
}

(async function () {
  let failures = 0;
  for (const {name, run} of tests) {
    try { await run(); console.log('PASS ' + name); }
    catch (error) { failures += 1; console.error('FAIL ' + name + '\n' + error.stack); }
  }
  console.log(`${tests.length - failures}/${tests.length} settings tab runtime tests passed`);
  if (failures) process.exitCode = 1;
}());
