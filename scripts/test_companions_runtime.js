#!/usr/bin/env node
'use strict';

// Real shell and companion handlers, with only DOM/native bridge/dialog boundaries
// doubled. These tests execute bodies and delayed replies; they do not paint CSS.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '../wingman/web');
const tests = [];
function test(name, run) { tests.push({name, run}); }
function turn() { return new Promise(resolve => setImmediate(resolve)); }
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
class Element {
  constructor(tag, document) {
    this.tagName = tag.toUpperCase(); this.ownerDocument = document;
    this.id = ''; this.className = ''; this.value = ''; this.checked = false;
    this.hidden = false; this.disabled = false; this.dataset = {}; this.attributes = {}; this.style = {};
    this.children = []; this.parentNode = null; this.listeners = {}; this._text = '';
  }
  get options() { return this.querySelectorAll('option'); }
  get selectedIndex() { return this.options.findIndex(option => option.value === this.value); }
  get value() {
    if (this.tagName === 'SELECT' && !this._value) return this.options[0]?.value || '';
    return this._value;
  }
  set value(value) { this._value = value; }
  get textContent() { return this._text + this.children.map(x => x.textContent).join(''); }
  set textContent(value) {
    this.children.slice().forEach(x => x.remove()); this._text = String(value);
    if (this.tagName === 'SELECT') this._value = '';
  }
  set innerHTML(value) { throw new Error('Unexpected HTML interpolation: ' + value); }
  appendChild(node) { node.remove(); this.children.push(node); node.parentNode = this; return node; }
  remove() {
    if (!this.parentNode) return;
    if (this.contains(this.ownerDocument.activeElement)) this.ownerDocument.activeElement = this.ownerDocument.body;
    this.parentNode.children = this.parentNode.children.filter(x => x !== this); this.parentNode = null;
  }
  contains(node) { return node === this || this.children.some(x => x.contains(node)); }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'id') this.id = String(value);
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  dispatchEvent(event) {
    event.target ||= this; event.preventDefault ||= () => {}; event.stopPropagation ||= () => {};
    for (const callback of this.listeners[event.type] || []) callback.call(this, event);
  }
  focus() { this.ownerDocument.activeElement = this; }
  getClientRects() { return this.hidden ? [] : [{}]; }
  prepend(node) { node.remove(); this.children.unshift(node); node.parentNode = this; }
  get classList() {
    const node = this;
    return {
      contains(name) { return node.className.split(/\s+/).includes(name); },
      toggle(name, force) {
        const on = force === undefined ? !this.contains(name) : force;
        const values = node.className.split(/\s+/).filter(x => x && x !== name);
        if (on) values.push(name); node.className = values.join(' '); return on;
      },
      add(name) { this.toggle(name, true); }, remove(name) { this.toggle(name, false); }
    };
  }
  querySelectorAll(selector) {
    const matches = node => {
      if (selector === '.settings-pane > .settings') return node.classList.contains('settings');
      const attr = selector.match(/^(?:([\w-]+)|\.([\w-]+))?\[([\w-]+)(?:="([^"]*)")?\]$/);
      if (attr) return (!attr[1] || node.tagName === attr[1].toUpperCase())
        && (!attr[2] || node.classList.contains(attr[2]))
        && (attr[4] === undefined ? node.getAttribute(attr[3]) !== null : node.getAttribute(attr[3]) === attr[4]);
      if (selector.startsWith('.')) return node.classList.contains(selector.slice(1));
      return node.tagName === selector.toUpperCase();
    };
    return this.children.flatMap(node => [...(matches(node) ? [node] : []), ...node.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
const id = '00000000000040008000000000000001', otherId = '00000000000040008000000000000002';
function row(changes = {}) {
  return Object.assign({version: 1, id, label: 'Mapper', enabled: true, mode: 'whole',
    source: {executable_path: 'c:\\mapper.exe', executable_name: 'mapper.exe', window_class: 'Mapper',
      title_hint: 'Map', title_mode: 'exact', last_title: 'Map'},
    window: {x: 10, y: 20, w: 320, h: 210}, generation: 1, binding_revision: 1,
    status: 'off', error: null, pending_operation_id: null}, changes);
}
function state(revision = 1, rows = [], operations = {}, changes = {}) {
  return Object.assign({revision, available: true, enabled: false,
    runtime: {revision: 1, pump_epoch: 0, eve_epoch: 0, companion_epoch: 0,
      pump: 'stopped', eve: 'stopped', companions: 'stopped', selection_pending: false, error: null},
    limits: {definitions: 32, enabled: 8, live_available: 8, reason: null,
      label_max_chars: 80, title_hint_max_chars: 512, last_title_max_chars: 512,
      window_class_max_chars: 256, executable_path_max_chars: 32768},
    rows, operations: Object.values(operations)}, changes);
}
function receipt(operation_id, changes = {}) {
  return Object.assign({operation_id, id: null, pending: false, applied: true,
    persisted: true, error: null, revision: 2}, changes);
}
const sources = [
  {candidate_token: 'opaque-one', application: 'mapper.exe', title: 'Map'},
  {candidate_token: 'opaque-two', application: 'notes.exe', title: '<img src=x onerror=bad()>'}
];
async function page(payload = state(), integrated = false) {
  const document = new Element('document', null); document.ownerDocument = document;
  document.body = new Element('body', document); document.appendChild(document.body);
  document.activeElement = document.body;
  document.createElement = tag => new Element(tag, document);
  document.getElementById = id => {
    const walk = node => node.id === id ? node : node.children.map(walk).find(Boolean);
    return walk(document.body) || null;
  };
  // Existing IDs come from the actual document, so typos in new markup cannot
  // be papered over by a permissive getElementById stub.
  const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
  for (const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const node = document.createElement(match[1]); node.id = match[3];
    node.className = (match[2].match(/class="([^"]*)"/) || [,''])[1];
    node.textContent = html.slice(match.index + match[0].length).split('<')[0];
    document.body.appendChild(node);
  }
  for (const match of html.matchAll(/<button class="(rail-item[^"]*)" data-section="([^"]+)">([^<]+)<\/button>/g)) {
    const node = document.createElement('button'); node.className = match[1];
    node.dataset.section = match[2]; node.setAttribute('data-section', match[2]);
    node.textContent = match[3]; document.body.appendChild(node);
  }
  const window = {document, addEventListener() {}, location: {search: ''}, getComputedStyle() { return {visibility: 'visible'}; }};
  const calls = [], dialogs = [], errors = []; let disarmed = 0;
  const context = vm.createContext({window, document, Promise, console: {
    error: (...args) => errors.push(args.join(' ')), warn() {}, log() {}
  }, CustomEvent: function (type, data) { return {type, detail: data.detail}; }});
  vm.runInContext(fs.readFileSync(path.join(web, 'app.js'), 'utf8'), context);
  const WM = window.WM; context.WM = WM;
  WM.send = (method, ...args) => {
    const d = deferred(); calls.push({method, args: JSON.parse(JSON.stringify(args)), ...d});
    return d.promise.catch(() => null);
  };
  WM.endPreviewCapture = () => { disarmed += 1; };
  WM.choose = (...args) => {
    assert.ok(disarmed, 'source dialog must disarm capture');
    const d = deferred(); dialogs.push({kind: 'choose', args, ...d}); return d.promise;
  };
  WM.confirm = (...args) => {
    assert.ok(disarmed, 'remove dialog must disarm capture');
    const d = deferred(); dialogs.push({kind: 'confirm', args, ...d}); return d.promise;
  };
  const filename = path.join(web, 'companions.js');
  assert.ok(fs.existsSync(filename), 'Settings needs the production companion module');
  if (integrated) vm.runInContext(fs.readFileSync(path.join(web, 'previews.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(filename, 'utf8'), context, {filename});
  if (integrated) vm.runInContext(fs.readFileSync(path.join(web, 'panel.js'), 'utf8'), context);
  const p = {
    WM, window, calls, dialogs, errors, document,
    el: name => document.getElementById(name),
    field(name, owner = id) { return document.getElementById('companion-' + owner + '-' + name); },
    async enter() { WM.openSettingsSection('companions'); await turn(); },
    async leave() { WM.route('main'); await turn(); },
    async fire(node, type, extra = {}) {
      assert.ok(node, 'control exists'); node.dispatchEvent({type, ...extra}); await turn();
    },
    async click(name) { await this.fire(this.el(name), 'click'); },
    async edit(name, value, owner = id) {
      const field = this.field(name, owner); assert.ok(field); field.value = value;
      await this.fire(field, 'input');
    },
    async submit(name, value, owner = id) {
      await this.edit(name, value, owner); await this.fire(this.field(name, owner), 'keydown', {key: 'Enter'});
    },
    async push(value) { window.onCompanionPreviews(value); await turn(); assert.deepEqual(errors, []); },
    async reply(method, value, expected) {
      const index = calls.findIndex(call => call.method === method);
      assert.notEqual(index, -1, 'pending ' + method);
      const call = calls.splice(index, 1)[0]; if (expected) assert.deepEqual(call.args, expected);
      call.resolve(value); await turn(); assert.deepEqual(errors, []);
    },
    async choose(value) { const d = dialogs.shift(); assert.ok(d); d.resolve(value); await turn(); },
    async startAdd(mode = 'whole') {
      await this.click('companion-add'); this.el('companion-add-label').value = 'Notes';
      await this.fire(this.el('companion-add-label'), 'input');
      this.el('companion-add-' + mode).checked = true;
      await this.fire(this.el('companion-add-' + mode), 'change');
      await this.click('companion-add-source');
    }
  };
  assert.equal(calls.filter(call => call.method === 'companion_previews_state').length, 0, 'no companion fetch at boot');
  if (payload !== null) { await p.enter(); await p.reply('companion_previews_state', payload); }
  return p;
}

test('nothing commits before hydration, configuration remains live with master off', async () => {
  const p = await page(null);
  assert.equal(p.el('companion-enabled').disabled, true);
  await p.click('companion-add'); assert.equal(p.calls.length, 0);
  await p.enter(); await p.reply('companion_previews_state', state());
  assert.equal(p.el('companion-add').disabled, false);
  assert.match(p.el('companion-off-note').textContent, /off/i);
});

test('Companions rail stays available with EVE hidden and Settings remembers it', async () => {
  const p = await page(null);
  assert.equal(p.WM.current_section, 'uploading');
  p.WM.apply_eve_gate(false);
  assert.deepEqual(p.document.querySelectorAll('.rail-item').filter(node => !node.hidden)
    .map(node => node.dataset.section), ['uploading', 'companions', 'general']);
  p.WM.route('settings'); await turn();
  await p.fire(p.document.querySelector('.rail-item[data-section="companions"]'), 'click');
  await p.reply('companion_previews_state', state());
  assert.equal(p.WM.current_section, 'companions');
  assert.equal(p.el('section-companions').classList.contains('active'), true);
  assert.equal(p.el('section-previews').classList.contains('active'), false);
  assert.equal(p.el('companion-add').disabled, false);
  p.WM.apply_eve_gate(false);
  assert.equal(p.WM.current_section, 'companions');
  await p.leave(); p.WM.route('settings'); await turn();
  await p.reply('companion_previews_state', state());
  assert.equal(p.WM.current_section, 'companions');
  assert.equal(p.el('companion-add').disabled, false);
});

test('Previews does not hydrate companions; leaving Companions discards only local drafts', async () => {
  const p = await page(null);
  p.WM.openSettingsSection('previews'); await turn();
  assert.equal(p.calls.length, 0);
  await p.enter(); await p.reply('companion_previews_state', state(1, [row()]));
  await p.edit('label', 'Unsubmitted');
  p.WM.section('previews'); await turn();
  assert.equal(p.field('label').disabled, true);
  await p.enter(); await p.reply('companion_previews_state', state(1, [row()]));
  assert.equal(p.field('label').value, 'Mapper');
  assert.equal(p.calls.length, 0);
});

test('zero sources explains recovery without a chooser or mutation', async () => {
  const p = await page(); await p.startAdd();
  await p.reply('companion_previews_sources', receipt(1, {sources: [], revision: 1}));
  assert.match(p.el('companion-status').textContent, /No eligible/);
  assert.equal(p.dialogs.length, 0); assert.equal(p.calls.length, 0);
});

for (const mode of ['whole', 'region']) {
  test(mode + ' add explicitly chooses a source and submits the complete wire contract', async () => {
    const p = await page(); await p.startAdd(mode);
    await p.reply('companion_previews_sources', receipt(1, {sources: sources.slice(0, 1), revision: 1}));
    assert.equal(p.dialogs.length, 1, 'even one source needs explicit selection');
    await p.choose('opaque-one');
    await p.reply('companion_preview_select', receipt(2, {pending: true}),
      [null, 'opaque-one', mode, 'Notes', 'exact', 'Map', null]);
    assert.match(p.el('companion-status').textContent, /progress|Selecting|Waiting/);
    await p.push(state(2, [row({mode, label: 'Notes'})], {2: receipt(2, {id})}));
    assert.equal(p.el('companion-add-form').hidden, true);
    assert.ok(p.field('label'));
  });
}

test('operation event beating initial pending source reply still opens chooser once', async () => {
  const p = await page(); await p.startAdd();
  await p.push(state(2, [], {3: receipt(3, {sources})}));
  await p.reply('companion_previews_sources', receipt(3, {pending: true}));
  assert.equal(p.dialogs.length, 1);
  assert.equal(p.dialogs[0].args[2][0].options[1].label, 'notes.exe — <img src=x onerror=bad()>');
  await p.push(state(3, [], {3: receipt(3, {sources})}));
  assert.equal(p.dialogs.length, 1);
});

test('leaving Settings or Companions during source choice never submits a local selection', async () => {
  for (const navigation of ['route', 'section']) {
    for (const stage of ['enumerating', 'choosing']) {
      const p = await page(); await p.startAdd();
      if (stage === 'choosing') await p.reply('companion_previews_sources', receipt(1, {sources, revision: 1}));
      if (navigation === 'route') await p.leave();
      else { p.WM.section('previews'); await turn(); }
      if (stage === 'enumerating') await p.reply('companion_previews_sources', receipt(1, {sources, revision: 1}));
      else await p.choose('opaque-one');
      assert.equal(p.calls.filter(x => x.method === 'companion_preview_select').length, 0);
      assert.equal(p.dialogs.length, 0);
    }
  }
});

test('accepted native selection survives navigation and reentry hydrates its receipt', async () => {
  const p = await page(); await p.startAdd('region');
  await p.reply('companion_previews_sources', receipt(1, {sources, revision: 1})); await p.choose('opaque-one');
  await p.reply('companion_preview_select', receipt(2, {pending: true})); await p.leave();
  await p.push(state(3, [row({mode: 'region'})], {2: receipt(2, {id, revision: 3})}));
  await p.enter(); await p.reply('companion_previews_state', state(3, [row({mode: 'region'})]));
  assert.ok(p.field('region')); assert.equal(p.field('region').disabled, false);
  assert.equal(p.calls.length, 0, 'navigation never cancels server operation');
});

test('typing and focus survive new snapshots, with no blur commit', async () => {
  const p = await page(state(1, [row()]));
  p.field('label').focus(); await p.edit('label', 'Draft');
  await p.push(state(2, [row({status: 'waiting'})]));
  assert.equal(p.field('label').value, 'Draft'); assert.equal(p.document.activeElement, p.field('label'));
  await p.fire(p.field('label'), 'blur'); assert.equal(p.calls.length, 0);
});

test('row edits serialize, use acknowledged generation, and never submit another field draft', async () => {
  const p = await page(state(1, [row()]));
  await p.edit('title_hint', 'Unsubmitted');
  await p.submit('label', 'First'); await p.submit('label', 'Second');
  assert.equal(p.calls.length, 1);
  await p.push(state(2, [row({label: 'First', generation: 2})], {4: receipt(4, {id})}));
  await p.reply('companion_preview_edit', receipt(4, {pending: true}), [id, 'First', 'exact', 'Map', 1]);
  assert.equal(p.field('label').value, 'Second'); assert.equal(p.field('title_hint').value, 'Unsubmitted');
  await p.reply('companion_preview_edit', receipt(5, {applied: false, persisted: false, error: 'Refused'}),
    [id, 'Second', 'exact', 'Map', 2]);
  assert.equal(p.field('label').value, 'First');
});

test('stale edit error cannot replace newer typing or clear another field error', async () => {
  const p = await page(state(1, [row()]));
  await p.submit('title_hint', 'No match');
  await p.reply('companion_preview_edit', receipt(1, {applied: false, persisted: false, error: 'Title refused', revision: 1}));
  await p.submit('label', 'Old'); await p.edit('label', 'New draft');
  await p.reply('companion_preview_edit', receipt(2, {applied: false, persisted: false, error: 'Old refusal', revision: 1}));
  assert.equal(p.field('label').value, 'New draft');
  assert.doesNotMatch(p.field('label-status').textContent, /Old refusal/);
  assert.match(p.field('title_hint-status').textContent, /Title refused/);
});

test('removed rows cannot be resurrected by old state or pending edit replies', async () => {
  const p = await page(state(1, [row()])); await p.submit('label', 'Old request');
  await p.push(state(3));
  await p.reply('companion_preview_edit', receipt(1, {id, revision: 2}));
  await p.push(state(2, [row()])); assert.equal(p.field('label'), null);
});

test('remove names the definition, preserves source, and reset/region use current generation', async () => {
  const p = await page(state(1, [row({mode: 'region', generation: 7})]));
  await p.fire(p.field('region'), 'click');
  await p.reply('companion_preview_reselect_region', receipt(1, {applied: false, error: 'Source closed', revision: 1}), [id, 7]);
  assert.match(p.field('status').textContent, /Source closed/); assert.equal(p.field('label').value, 'Mapper');
  await p.fire(p.field('reset'), 'click');
  await p.reply('companion_preview_reset_geometry', receipt(2, {revision: 1}), [id, 7]);
  await p.fire(p.field('remove'), 'click');
  assert.match(p.dialogs[0].args[0], /Mapper/); assert.match(p.dialogs[0].args[1], /source application/);
  await p.choose(true);
  await p.push(state(2, [], {3: receipt(3, {id})}));
  await p.reply('companion_preview_remove', receipt(3, {pending: true}), [id, 7]);
  assert.equal(p.field('label'), null);
});

test('failed source discovery and null bridge replies are recoverable, not empty success', async () => {
  for (const result of [null, receipt(1, {applied: false, persisted: false, error: 'Source unavailable', revision: 1})]) {
    const p = await page(); await p.startAdd(); await p.reply('companion_previews_sources', result);
    assert.match(p.el('companion-status').textContent, /unavailable|confirm|failed/i);
    assert.equal(p.el('companion-add-source').disabled, false);
  }
});

test('backend limits govern add and code-point validation, not UTF-16 maxlength', async () => {
  const payload = state(1, [row()], {}, {limits: {definitions: 2, enabled: 2, label_max_chars: 2, title_hint_max_chars: 3}});
  const p = await page(payload);
  await p.submit('label', '😀x'); assert.equal(p.calls.length, 1);
  await p.reply('companion_preview_edit', receipt(1, {applied: false, error: 'Refused', revision: 1}));
  await p.submit('label', '😀xy'); assert.equal(p.calls.length, 0);
  assert.match(p.field('label-status').textContent, /2/);
  await p.push(state(2, [row(), row({id: otherId})], {}, {limits: payload.limits}));
  assert.equal(p.el('companion-add').disabled, true);
});

test('queued text waits for an external pending mutation and resumes with the new generation', async () => {
  const p = await page(state(1, [row({pending_operation_id: 17})], {17: receipt(17, {id, pending: true, revision: 1})}));
  await p.submit('label', 'Queued'); assert.equal(p.calls.length, 0);
  await p.push(state(2, [row({generation: 2})], {17: receipt(17, {id})}));
  await p.reply('companion_preview_edit', receipt(18, {applied: false, error: 'Refused', revision: 2}),
    [id, 'Queued', 'exact', 'Map', 2]);
});

test('a lost selection reply never traps the card after navigation and authoritative completion', async () => {
  const p = await page(); await p.startAdd('region');
  await p.reply('companion_previews_sources', receipt(1, {sources, revision: 1})); await p.choose('opaque-one');
  // Deliberately never resolve companion_preview_select.
  await p.leave(); await p.enter();
  await p.reply('companion_previews_state', state(3, [row({mode: 'region'})], {2: receipt(2, {id, revision: 3})}));
  assert.equal(p.el('companion-add').disabled, false);
  assert.equal(p.field('region').disabled, false);
});

test('rehydrated pending add remains visible and disarms duplicate source admission', async () => {
  const p = await page(state(2, [], {4: receipt(4, {id, pending: true})}));
  assert.match(p.el('companion-status').textContent, /progress/);
  assert.equal(p.el('companion-add').disabled, true);
  await p.push(state(3, [row()], {4: receipt(4, {id, revision: 3})}));
  assert.equal(p.el('companion-add').disabled, false);
});

test('master serializes rapid changes and refusal returns to the acknowledged value', async () => {
  const p = await page();
  p.el('companion-enabled').checked = true; await p.fire(p.el('companion-enabled'), 'change');
  p.el('companion-enabled').checked = false; await p.fire(p.el('companion-enabled'), 'change');
  assert.equal(p.calls.length, 1);
  await p.push(state(2, [], {8: receipt(8)}, {enabled: true}));
  await p.reply('set_companion_previews_enabled', receipt(8, {pending: true}), [true]);
  assert.equal(p.el('companion-enabled').checked, false);
  await p.reply('set_companion_previews_enabled', receipt(9, {applied: false, persisted: false, error: 'Save failed', revision: 2}), [false]);
  assert.equal(p.el('companion-enabled').checked, true);
  assert.match(p.el('companion-master-status').textContent, /Save failed/);
});

test('late refusal of a superseded generation does not attach an obsolete field error', async () => {
  const p = await page(state(1, [row()])); await p.submit('label', 'Old');
  await p.push(state(3, [row({label: 'Elsewhere', generation: 3})]));
  await p.reply('companion_preview_edit', receipt(3, {id, applied: false, persisted: false, error: 'Stale error', revision: 2}));
  assert.doesNotMatch(p.field('label-status').textContent, /Stale error/);
  assert.equal(p.field('label').value, 'Elsewhere');
});

test('reselection uses chosen capture mode and preserves committed row until native outcome', async () => {
  const p = await page(state(1, [row({mode: 'region', generation: 5})]));
  const radio = p.field('source').parentNode.parentNode.querySelectorAll('input').find(x => x.value === 'whole');
  radio.checked = true; await p.fire(radio, 'change');
  await p.fire(p.field('source'), 'click');
  await p.reply('companion_previews_sources', receipt(1, {sources, revision: 1})); await p.choose('opaque-two');
  assert.equal(p.field('label').value, 'Mapper');
  await p.reply('companion_preview_select', receipt(2, {applied: false, persisted: false, error: 'Source closed', revision: 1}),
    [id, 'opaque-two', 'whole', 'Mapper', 'exact', '<img src=x onerror=bad()>', 5]);
  assert.equal(p.field('region').hidden, false);
  assert.match(p.el('companion-status').textContent, /Source closed/);
});

test('runtime unavailability is visible and never invents a working capture control', async () => {
  const p = await page(state(1, [row()], {}, {available: false}));
  assert.equal(p.el('companion-add').disabled, true);
  assert.equal(p.field('source').disabled, true);
  assert.match(p.el('companion-status').textContent, /unavailable/);
});

test('real preview capture disarms on leaving for Companions before its source chooser', async () => {
  const p = await page(null, true);
  p.WM.openSettingsSection('previews'); await turn();
  p.window.onPreviewHotkeys({hotkeys: {characters: {}, cycle_next: '', cycle_prev: '', groups: [], group_by_character: {}},
    characters: [], roster: [], registration: {}, bookmark_chords: {active: [], latent: []},
    enabled: true, locked: [], lock_default: false, never_minimize: [], excluded: [], sizes: {},
    client_sizes: {}, sizable: [], layout_sources: []});
  assert.deepEqual(p.errors, []);
  const capture = p.el('preview-binds').querySelector('.bindbtn'); assert.ok(capture);
  await p.fire(capture, 'click'); await p.reply('set_bind_capture', true, [true]);
  assert.equal(capture.classList.contains('capturing'), true);
  await p.enter();
  await p.reply('set_bind_capture', true, [false]);
  assert.equal(capture.classList.contains('capturing'), false);
  await p.reply('companion_previews_state', state());
  await p.startAdd();
  await p.reply('companion_previews_sources', receipt(1, {sources, revision: 1}));
  assert.equal(p.el('overlay').hidden, false);
  assert.equal(p.el('dlg-select-label').textContent, 'Source');
  const options = p.el('dlg-select').querySelectorAll('option');
  assert.equal(options[1].textContent, 'notes.exe — <img src=x onerror=bad()>');
  await p.fire(p.document, 'keydown', {key: 'Escape'});
  assert.equal(p.el('overlay').hidden, true);
  assert.equal(p.calls.filter(call => call.method === 'capture_preview_bind').length, 0);
  assert.equal(p.calls.filter(call => call.method === 'companion_preview_select').length, 0);
});

test('real compact source chooser bounds Unicode captions, reveals full selected text, and resets for copy', async () => {
  const p = await page(state(), true);
  const title = '😀'.repeat(50) + ' <img src=x onerror=bad()>', application = 'notes.exe';
  const longSources = [{candidate_token: 'opaque-long', application, title}, sources[0]];
  await p.startAdd();
  await p.reply('companion_previews_sources', receipt(1, {sources: longSources, revision: 1}));
  assert.equal(p.el('dialog').classList.contains('compact-choice'), true);
  const select = p.el('dlg-select'), detail = p.el('dlg-select-detail');
  const options = select.querySelectorAll('option');
  assert.equal(options[0].textContent, 'notes.exe — ' + '😀'.repeat(31) + '…');
  assert.equal(Array.from(options[0].textContent).length, 44);
  assert.equal(options[0].textContent.isWellFormed(), true);
  assert.equal(options[0].value, 'opaque-long');
  assert.equal(options[1].textContent, 'mapper.exe — Map');
  assert.equal(detail.hidden, false);
  assert.equal(detail.textContent, application + ' — ' + title);
  assert.equal(select.getAttribute('aria-describedby'), 'dlg-select-detail');
  assert.equal(detail.querySelectorAll('img').length, 0);
  select.value = 'opaque-one'; await p.fire(select, 'change');
  assert.equal(detail.textContent, 'mapper.exe — Map');
  select.value = 'opaque-long'; await p.fire(select, 'change');
  await p.click('dlg-ok');
  await p.reply('companion_preview_select', receipt(2, {applied: false, persisted: false, error: 'Refused', revision: 1}),
    [null, 'opaque-long', 'whole', 'Notes', 'exact', title, null]);
  const ordinary = p.WM.choose('Copy preview geometry', 'Copy size and position.',
    [{label: 'Saved', options: [{value: 'copy-token', label: title}]}]);
  assert.equal(p.el('dialog').classList.contains('compact-choice'), false);
  assert.equal(select.querySelectorAll('option')[0].textContent, title);
  assert.equal(p.el('dlg-select-label').textContent, 'Copy from');
  assert.equal(detail.hidden, true);
  assert.equal(detail.textContent, '');
  assert.equal(select.getAttribute('aria-describedby'), null);
  await p.click('dlg-ok'); assert.equal(await ordinary, 'copy-token');
});

test('duplicate and hostile labels stay literal, keyed independently, and name their enabled controls', async () => {
  const label = '<img src=x onerror=bad()> __proto__';
  const p = await page(state(1, [row({label}), row({id: otherId, label})]));
  assert.equal(p.el('companion-list').querySelectorAll('.companion-name').length, 2);
  assert.equal(p.el('companion-list').querySelectorAll('img').length, 0);
  assert.equal(p.field('enabled').getAttribute('aria-label'), 'Enable ' + label);
  await p.submit('label', 'Changed', otherId);
  await p.push(state(2, [row({label}), row({id: otherId, label: 'Changed', generation: 2})], {1: receipt(1, {id: otherId})}));
  await p.reply('companion_preview_edit', receipt(1, {pending: true}), [otherId, 'Changed', 'exact', 'Map', 1]);
  assert.equal(p.field('label').value, label);
  assert.equal(p.field('enabled', otherId).getAttribute('aria-label'), 'Enable Changed');
});

test('title policy commits on change without including an unsubmitted label', async () => {
  const p = await page(state(1, [row()])); await p.edit('label', 'Draft');
  p.field('title_mode').value = 'contains'; await p.fire(p.field('title_mode'), 'change');
  await p.reply('companion_preview_edit', receipt(1, {applied: false, persisted: false, error: 'Refused', revision: 1}),
    [id, 'Mapper', 'contains', 'Map', 1]);
  assert.equal(p.field('title_mode').value, 'exact'); assert.equal(p.field('label').value, 'Draft');
});

test('enabled control submits the row generation and rolls back only its own refusal', async () => {
  const p = await page(state(1, [row()]));
  p.field('enabled').checked = false; await p.fire(p.field('enabled'), 'change');
  await p.edit('label', 'Draft');
  await p.reply('companion_preview_set_enabled', receipt(1, {applied: false, persisted: false, error: 'Refused', revision: 1}),
    [id, false, 1]);
  assert.equal(p.field('enabled').checked, true); assert.equal(p.field('label').value, 'Draft');
});

test('direct success awaits acknowledged state before dispatching a queued edit', async () => {
  const p = await page(state(1, [row()]));
  await p.submit('label', 'First'); await p.submit('label', 'Second');
  await p.reply('companion_preview_edit', receipt(1, {id, revision: 2}));
  assert.equal(p.calls.filter(call => call.method === 'companion_preview_edit').length, 0);
  await p.reply('companion_previews_state', state(2, [row({label: 'First', generation: 2})]));
  assert.equal(p.field('label').value, 'Second');
  await p.reply('companion_preview_edit', receipt(2, {id, applied: false, persisted: false, error: 'Refused', revision: 2}),
    [id, 'Second', 'exact', 'Map', 2]);
  assert.equal(p.field('label').value, 'First');
});

test('remove confirmation cannot act after the row changes or the section is left', async () => {
  for (const change of ['row', 'section']) {
    const p = await page(state(1, [row()])); await p.fire(p.field('remove'), 'click');
    if (change === 'row') await p.push(state(2, [row({generation: 2})])); else await p.leave();
    await p.choose(true);
    assert.equal(p.calls.filter(call => call.method === 'companion_preview_remove').length, 0);
  }
});

test('reentry recovers a terminal failure and a pending operation that later fails', async () => {
  for (const wasPending of [false, true]) {
    const failure = receipt(19, {id, applied: false, persisted: false, error: 'Could not save', revision: 3});
    const first = wasPending ? receipt(19, {id, pending: true, revision: 2}) : failure;
    const p = await page(state(first.revision, [], {19: first}));
    if (wasPending) await p.push(state(3, [], {19: failure}));
    assert.match(p.el('companion-status').textContent, /Could not save/);
    assert.equal(p.el('companion-add').disabled, false);
  }
});

(async () => {
  let failed = 0;
  for (const {name, run} of tests) {
    try { await run(); console.log('ok - ' + name); }
    catch (error) { failed += 1; console.error('not ok - ' + name + '\n' + error.stack); }
  }
  console.log(`${tests.length - failed}/${tests.length} companion runtime checks passed`);
  process.exitCode = failed ? 1 : 0;
})();
