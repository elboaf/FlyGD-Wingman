#!/usr/bin/env node
'use strict';

// Real alerts.js, explicit DOM/bridge boundaries. This exercises ownership and
// keyboard intent, not layout or Windows/WebView2 focus/native presentation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '../wingman/web');
const source = fs.readFileSync(path.join(web, 'alerts.js'), 'utf8');
const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
const tests = [];
function test(name, run) { tests.push({name, run}); }
function turn() { return new Promise(resolve => setImmediate(resolve)); }
function plain(value) { return JSON.parse(JSON.stringify(value)); }
const initial = {revision: 1, rules: [], limit: 8, previews_enabled: false,
  alerts_enabled: false, reader: {running: false, last_error: null,
    characters: [], gamelogs_folder: null}, matcher: {state: 'inactive', detail: null}};
function rule(id = 'r1', extra = {}) {
  return Object.assign({id, name: 'Custom alert', search: '', enabled: false,
    color: '#ff8c42', sound: 'none', cooldown_s: 8}, extra);
}
function state(revision, rules, extra = {}) { return Object.assign({}, initial, {revision, rules}, extra); }
function result(revision, rules, extra = {}) {
  return Object.assign({applied: true, persisted: true, error: null,
    rule_id: rules[0]?.id || null, state: state(revision, rules)}, extra);
}
function decode(text) {
  return text.replace(/&(?:amp|lt|gt|quot|nbsp|mdash);/g,
    entity => ({'&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&nbsp;': ' ', '&mdash;': '—'})[entity]);
}
class Element {
  constructor(tag, document) {
    this.tagName = tag.toUpperCase(); this.ownerDocument = document;
    this.id = ''; this.value = ''; this.checked = false; this.hidden = false;
    this.disabled = false; this.open = false; this.className = ''; this.dataset = {};
    this.attributes = {}; this.children = []; this.parentNode = null;
    this.listeners = {}; this._text = ''; this.style = {setProperty() {}};
  }
  get disabled() { return this._disabled; }
  set disabled(value) {
    this._disabled = value;
    // Conservative DOM focus boundary: do not assume disabled or detached
    // controls retain focus. Browser/native acceptance remains independent.
    if (value && this.ownerDocument?.activeElement === this) this.ownerDocument.activeElement = this.ownerDocument;
  }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set textContent(text) {
    if (this.children.some(child => child.contains(this.ownerDocument.activeElement))) this.ownerDocument.activeElement = this.ownerDocument;
    this.children.forEach(child => { child.parentNode = null; });
    this.children = []; this._text = String(text);
  }
  get options() { assert.equal(this.tagName, 'SELECT'); return this.children; }
  get firstChild() { return this.children[0] || null; }
  appendChild(child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    this.children.push(child); child.parentNode = this; return child;
  }
  removeChild(child) {
    assert.ok(this.children.includes(child)); this.children.splice(this.children.indexOf(child), 1);
    if (child.contains(this.ownerDocument.activeElement)) this.ownerDocument.activeElement = this.ownerDocument;
    child.parentNode = null; return child;
  }
  contains(child) { return this === child || this.children.some(node => node.contains(child)); }
  setAttribute(name, value) {
    value = String(value); this.attributes[name] = value;
    if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
    else if (name === 'class') this.className = value;
    else if (['hidden', 'disabled', 'checked', 'open'].includes(name)) this[name] = true;
    else if (['id', 'value', 'type', 'name', 'title'].includes(name)) this[name] = value;
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatchEvent(event) {
    event.target ||= this;
    event.preventDefault ||= function () { this.defaultPrevented = true; };
    event.stopPropagation ||= function () { this.stopped = true; };
    for (const fn of this.listeners[event.type] || []) fn.call(this, event);
    if (!event.stopped && this.parentNode) this.parentNode.dispatchEvent(event);
    return !event.defaultPrevented;
  }
  focus() { this.ownerDocument.activeElement = this; }
  click() { if (!this.disabled) this.dispatchEvent({type: 'click'}); }
  querySelectorAll(selector) {
    let match;
    if (selector === 'input' || selector === 'option') match = node => node.tagName === selector.toUpperCase();
    else if (selector === 'input:checked') match = node => node.tagName === 'INPUT' && node.checked;
    else if (selector === '[data-rule-id]') match = node => node.dataset.ruleId !== undefined;
    else throw new Error('Unhandled selector: ' + selector);
    const found = [];
    function visit(node) { for (const child of node.children) { if (match(child)) found.push(child); visit(child); } }
    visit(this); return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
function page() {
  const document = new Element('document'); document.ownerDocument = document;
  document.activeElement = document;
  document.createElement = tag => new Element(tag, document);
  document.getElementById = id => {
    function visit(node) { if (node.id === id) return node; for (const child of node.children) { const found = visit(child); if (found) return found; } return null; }
    return visit(document);
  };
  // Parse actual Alerts markup (including sound options), not a permissive ID
  // factory. A misspelling/missing element fails before behavior can be tested.
  const section = html.slice(html.indexOf('<div class="settings" id="section-alerts"'), html.indexOf('<div class="settings" id="section-', html.indexOf('id="section-alerts"') + 1));
  const stack = [document];
  for (const token of section.replace(/<!--[\s\S]*?-->/g, '').match(/<[^>]+>|[^<]+/g) || []) {
    if (token.startsWith('</')) { stack.pop(); continue; }
    if (!token.startsWith('<')) { stack[stack.length - 1]._text += decode(token); continue; }
    const tag = token.match(/^<([\w-]+)/)?.[1]; if (!tag) continue;
    const node = document.createElement(tag);
    for (const attr of token.slice(tag.length + 1, -1).matchAll(/([\w-]+)(?:="([^"]*)")?/g)) node.setAttribute(attr[1], decode(attr[2] || ''));
    stack[stack.length - 1].appendChild(node);
    if (!['input', 'br', 'hr', 'img'].includes(tag)) stack.push(node);
  }
  for (const id of ['alert-enabled', 'custom-alerts', 'custom-alert-list',
    'custom-alert-add', 'custom-alert-health', 'custom-alert-status']) {
    assert.ok(document.getElementById(id), 'Missing required static ID in index.html: ' + id);
  }
  const calls = [], confirms = [], intervals = new Map(); let intervalId = 0;
  const WM = {
    el: id => document.getElementById(id),
    setEnabled: (id, enabled) => { const el = typeof id === 'string' ? WM.el(id) : id; el.disabled = !enabled; },
    confirm: (...args) => new Promise(resolve => confirms.push({args, resolve})),
    send: (method, ...args) => new Promise((resolve, reject) => calls.push({method, args: plain(args), resolve, reject}))
  };
  const window = {WM, setInterval(fn, ms) { const id = ++intervalId; intervals.set(id, {fn, ms}); return id; },
    clearInterval(id) { intervals.delete(id); }};
  vm.runInNewContext(source, {window, WM, document, Promise}, {filename: 'wingman/web/alerts.js'});
  const api = {
    calls, confirms, intervals, document,
    el(id) { const el = WM.el(id); assert.ok(el, 'Missing rendered ID: ' + id); return el; },
    enter() { document.dispatchEvent({type: 'wm:route', detail: 'settings'}); document.dispatchEvent({type: 'wm:section', detail: 'alerts'}); },
    leave(kind = 'section') { document.dispatchEvent({type: 'wm:' + kind, detail: kind === 'section' ? 'general' : 'upload'}); },
    fire(id, type, extra = {}) {
      const node = this.el(id);
      if (node.disabled && ['click', 'change', 'keydown'].includes(type)) return;
      node.dispatchEvent(Object.assign({type}, extra));
    },
    edit(id, value) { this.el(id).value = value; this.fire(id, 'input'); },
    toggle(id, value) { this.el(id).checked = value; this.fire(id, 'change'); },
    choose(id, value) { this.el(id).value = value; this.fire(id, 'change'); },
    color(id, value) {
      const group = this.el('custom-alert-' + id + '-color');
      const input = group.querySelectorAll('input').find(node => node.value === value); assert.ok(input);
      group.querySelectorAll('input').forEach(node => { node.checked = node === input; });
      input.dispatchEvent({type: 'change'});
    },
    tick() { for (const {fn, ms} of intervals.values()) { assert.equal(ms, 2000); fn(); } },
    async reply(method, res, index = 0, reject = false) {
      const call = calls.filter(c => c.method === method)[index]; assert.ok(call, 'Expected pending call to ' + method);
      calls.splice(calls.indexOf(call), 1); if (reject) call.reject(new Error('unreachable')); else call.resolve(res);
      await turn(); return call;
    },
    async confirm(yes) { assert.ok(confirms.length); confirms.shift().resolve(yes); await turn(); },
    rows() {
      return this.el('custom-alert-list').querySelectorAll('[data-rule-id]').map(node => {
        const id = node.dataset.ruleId, field = suffix => this.el('custom-alert-' + id + '-' + suffix);
        return {id, name: field('name').value, search: field('search').value, enabled: field('enabled').checked,
          color: field('color').querySelector('input:checked')?.value, sound: field('sound').value,
          cooldown_s: Number(field('cooldown').value)};
      });
    }
  };
  return api;
}

test('add waits for authority and renders only its acknowledgement', async () => {
  const p = page(); p.enter(); p.fire('custom-alert-add', 'click');
  assert.equal(p.calls.filter(c => c.method === 'add_custom_alert').length, 0);
  await p.reply('get_custom_alert_state', initial);
  p.fire('custom-alert-add', 'click');
  assert.equal(p.calls.filter(c => c.method === 'add_custom_alert').length, 1);
  assert.equal(p.rows().length, 0);
  await p.reply('add_custom_alert', result(2, [rule()]));
  assert.equal(p.rows().length, 1); assert.equal(p.rows()[0].enabled, false);
});

async function loaded(rules = [rule('r1', {search: 'accepted'})], extra = {}) {
  const p = page(); p.enter(); await p.reply('get_custom_alert_state', state(1, rules, extra)); return p;
}
function edit(p, value, id = 'r1') { p.edit('custom-alert-' + id + '-search', value); }
function apply(p, id = 'r1') { p.fire('custom-alert-' + id + '-apply', 'click'); }
function pending(p, method) { return p.calls.filter(c => c.method === method); }

test('empty list teaches Add; capacity is acknowledged and globally serialized', async () => {
  const p = await loaded([]); assert.match(p.el('custom-alert-list').textContent, /Add/);
  const rules = [];
  for (let n = 1; n <= 8; n++) {
    p.fire('custom-alert-add', 'click'); p.fire('custom-alert-add', 'click');
    assert.equal(pending(p, 'add_custom_alert').length, 1);
    rules.push(rule('r' + n));
    await p.reply('add_custom_alert', result(n + 1, rules.slice(), {rule_id: 'r' + n}));
  }
  assert.equal(p.rows().length, 8); assert.equal(p.el('custom-alert-add').disabled, true);
  p.fire('custom-alert-add', 'click'); assert.equal(pending(p, 'add_custom_alert').length, 0);
  const q = await loaded([rule()], {limit: 1}); assert.equal(q.el('custom-alert-add').disabled, true);
});

test('one disclosure, focus after add/cancel, duplicate names remain ID-addressed', async () => {
  const p = await loaded([rule('r1'), rule('r2')]);
  p.fire('custom-alert-r1-edit', 'click'); assert.equal(p.document.activeElement.id, 'custom-alert-r1-name');
  p.fire('custom-alert-r2-edit', 'click');
  assert.equal(p.el('custom-alert-r1-editor').hidden, true); assert.equal(p.el('custom-alert-r2-editor').hidden, false);
  assert.notEqual(p.el('custom-alert-r1-edit').getAttribute('aria-label'), p.el('custom-alert-r2-edit').getAttribute('aria-label'));
  p.fire('custom-alert-r2-cancel', 'click'); assert.equal(p.document.activeElement.id, 'custom-alert-r2-edit');
  p.el('custom-alert-add').focus(); p.fire('custom-alert-add', 'click');
  await p.reply('add_custom_alert', result(2, [rule('r1'), rule('r2'), rule('r3')], {rule_id: 'r3'}));
  assert.equal(p.document.activeElement.id, 'custom-alert-r3-name');
});

test('Enter in either text field and Apply capture complete drafts; blur never submits', async () => {
  const p = await loaded(); p.fire('custom-alert-r1-edit', 'click');
  p.edit('custom-alert-r1-name', 'New name'); edit(p, 'draft'); p.fire('custom-alert-r1-search', 'blur');
  assert.equal(pending(p, 'edit_custom_alert').length, 0);
  for (const field of ['name', 'search']) {
    p.fire('custom-alert-r1-' + field, 'keydown', {key: 'Enter'});
    const call = pending(p, 'edit_custom_alert')[0];
    assert.deepEqual(call.args, ['r1', {name: 'New name', search: 'draft', enabled: false, color: '#ff8c42', sound: 'none', cooldown_s: 8}]);
    await p.reply('edit_custom_alert', result(2, [rule('r1', {name: 'New name', search: 'draft'})]));
  }
});

test('clear atomically disables; enable refusal restores acknowledged box near its row', async () => {
  const p = await loaded([rule('r1', {search: 'accepted', enabled: true})]);
  edit(p, ''); apply(p); await p.reply('edit_custom_alert', result(2, [rule()]));
  assert.equal(p.rows()[0].enabled, false);
  p.toggle('custom-alert-r1-enabled', true);
  assert.deepEqual(pending(p, 'set_custom_alert_enabled')[0].args, ['r1', true]);
  await p.reply('set_custom_alert_enabled', result(2, [rule()], {applied: false, persisted: false, error: 'Enter a search before enabling this alert.'}));
  assert.equal(p.rows()[0].enabled, false); assert.match(p.el('custom-alert-r1-msg').textContent, /Enter a search/);
});

test('discrete style commits acknowledged text, Test sends style only, drafts still need Apply', async () => {
  const p = await loaded(); p.edit('custom-alert-r1-name', 'Unsubmitted'); edit(p, '<new draft>');
  for (const [suffix, value, field] of [['sound', 'sly', 'sound'], ['cooldown', '12', 'cooldown_s']]) {
    p.choose('custom-alert-r1-' + suffix, value);
    const sent = pending(p, 'edit_custom_alert')[0].args[1];
    assert.equal(sent.name, 'Custom alert'); assert.equal(sent.search, 'accepted');
    assert.equal(sent[field], field === 'cooldown_s' ? 12 : value);
    await p.reply('edit_custom_alert', result(2, [rule('r1', sent)]));
    assert.equal(p.rows()[0].search, '<new draft>'); assert.match(p.el('custom-alert-r1-msg').textContent, /Apply/);
  }
  p.color('r1', '#4dff7a');
  p.fire('custom-alert-r1-test', 'click');
  const call = pending(p, 'test_custom_alert')[0];
  assert.deepEqual(call.args, ['r1', {color: '#4dff7a', sound: 'sly', cooldown_s: 12}]);
  await p.reply('test_custom_alert', {applied: true, persisted: false, error: null});
  assert.doesNotMatch(p.el('custom-alert-r1-msg').textContent, /restart|save failed/);
  assert.match(p.el('custom-alert-r1-msg').textContent, /Apply/);
});

for (const applied of [true, false]) {
  test('old ' + (applied ? 'success' : 'refusal') + ' retains typing, focus, and latest acknowledgment', async () => {
    const p = await loaded(); p.fire('custom-alert-r1-edit', 'click'); edit(p, 'submitted'); apply(p);
    edit(p, 'newer draft'); p.el('custom-alert-r1-search').focus();
    await p.reply('edit_custom_alert', result(2, [rule('r1', {search: applied ? 'submitted' : 'accepted'})],
      {applied, persisted: applied, error: applied ? null : 'Invalid search'}));
    assert.equal(p.rows()[0].search, 'newer draft'); assert.equal(p.document.activeElement.id, 'custom-alert-r1-search');
    assert.match(p.el('custom-alert-r1-msg').textContent, /Apply/);
    edit(p, 'invalid'); apply(p);
    await p.reply('edit_custom_alert', result(2, [rule('r1', {search: applied ? 'submitted' : 'accepted'})],
      {applied: false, persisted: false, error: 'Invalid search'}));
    assert.equal(p.rows()[0].search, applied ? 'submitted' : 'accepted');
  });
}

test('full edits and enable toggles share FIFO; queued style rebases on accepted text', async () => {
  const p = await loaded(); edit(p, 'first'); apply(p); edit(p, 'second'); apply(p);
  p.toggle('custom-alert-r1-enabled', true); p.choose('custom-alert-r1-sound', 'sly');
  assert.equal(pending(p, 'edit_custom_alert').length, 1); assert.equal(pending(p, 'set_custom_alert_enabled').length, 0);
  await p.reply('edit_custom_alert', result(2, [rule('r1', {search: 'first'})]));
  assert.equal(p.rows()[0].search, 'second'); assert.equal(pending(p, 'edit_custom_alert')[0].args[1].search, 'second');
  await p.reply('edit_custom_alert', result(3, [rule('r1', {search: 'second'})]));
  await p.reply('set_custom_alert_enabled', result(4, [rule('r1', {search: 'second', enabled: true})]));
  const draft = pending(p, 'edit_custom_alert')[0].args[1];
  assert.equal(draft.search, 'second'); assert.equal(draft.enabled, true);
  await p.reply('edit_custom_alert', result(5, [rule('r1', draft)]));
});

test('remove confirms by name; cancellation has no bridge call; deletion cannot resurrect', async () => {
  const p = await loaded([rule('r1'), rule('r2')]); p.el('custom-alert-r1-remove').focus();
  p.fire('custom-alert-r1-remove', 'click'); assert.match(p.confirms[0].args.join(' '), /Custom alert/);
  await p.confirm(false); assert.equal(pending(p, 'remove_custom_alert').length, 0);
  p.tick(); p.fire('custom-alert-r1-remove', 'click'); await p.confirm(true);
  assert.deepEqual(pending(p, 'remove_custom_alert')[0].args, ['r1']);
  await p.reply('remove_custom_alert', result(2, [rule('r2')], {rule_id: 'r1'}));
  assert.deepEqual(p.rows().map(r => r.id), ['r2']); assert.equal(p.document.activeElement.id, 'custom-alert-r2-edit');
  await p.reply('get_custom_alert_state', state(1, [rule('r1'), rule('r2')]));
  assert.deepEqual(p.rows().map(r => r.id), ['r2']);
});

test('poll never repaints drafts, disclosures or a row failure', async () => {
  const p = await loaded(); p.fire('custom-alert-r1-edit', 'click'); edit(p, 'invalid'); apply(p);
  await p.reply('edit_custom_alert', result(1, [rule('r1', {search: 'accepted'})], {applied: false, persisted: false, error: 'Cannot save'}));
  edit(p, 'draft'); p.tick(); await p.reply('get_custom_alert_state', state(8, [rule('r1', {search: 'external'})]));
  assert.equal(p.rows()[0].search, 'draft'); assert.equal(p.el('custom-alert-r1-editor').hidden, false);
  assert.match(p.el('custom-alert-r1-msg').textContent, /Cannot save/);
});

test('higher-revision sibling response is authority; older target ack cannot regress it', async () => {
  const p = await loaded([rule('r1', {search: 'original'}), rule('r2')]);
  edit(p, 'submitted'); apply(p); p.toggle('custom-alert-r2-enabled', true);
  const rules = [rule('r1', {search: 'canonical later'}), rule('r2')];
  await p.reply('set_custom_alert_enabled', result(4, rules, {applied: false, persisted: false, error: 'Needs search'}));
  await p.reply('edit_custom_alert', result(2, [rule('r1', {search: 'submitted'}), rule('r2')]));
  edit(p, 'invalid'); apply(p);
  await p.reply('edit_custom_alert', result(4, rules, {applied: false, persisted: false, error: 'Invalid'}));
  assert.equal(p.rows()[0].search, 'canonical later');
  assert.match(p.el('custom-alert-r2-msg').textContent, /Needs search/);
});

for (const kind of ['section', 'route']) {
  test(kind + ' exit stops the sole timer; prehydration retained-row edits and late replies are fenced', async () => {
    const p = await loaded(); p.enter(); assert.equal(p.intervals.size, 1);
    edit(p, 'pending'); apply(p); p.leave(kind); assert.equal(p.intervals.size, 0);
    p.enter(); p.fire('custom-alert-r1-edit', 'click'); p.fire('custom-alert-r1-search', 'keydown', {key: 'Enter'});
    assert.equal(pending(p, 'edit_custom_alert').length, 1);
    await p.reply('get_custom_alert_state', state(1, [rule('r1', {search: 'stale'})]));
    await p.reply('edit_custom_alert', result(2, [rule('r1', {search: 'pending'})]));
    await p.reply('get_custom_alert_state', state(1, [rule('r1', {search: 'stale'})]));
    // The old owned write causes a new current-view read; stale entry cannot regress it.
    await p.reply('get_custom_alert_state', state(2, [rule('r1', {search: 'pending'})]));
    edit(p, 'invalid'); apply(p);
    await p.reply('edit_custom_alert', result(2, [rule('r1', {search: 'pending'})], {applied: false, persisted: false, error: 'Invalid'}));
    assert.equal(p.rows()[0].search, 'pending');
  });
}

for (const reject of [false, true]) {
  test('uncertain Add ' + (reject ? 'rejection' : 'null') + ' reads authority and never retries automatically', async () => {
    const p = await loaded([]); p.fire('custom-alert-add', 'click');
    await p.reply('add_custom_alert', null, 0, reject);
    assert.equal(pending(p, 'add_custom_alert').length, 0); assert.equal(p.el('custom-alert-add').disabled, true);
    assert.match(p.el('custom-alert-status').textContent, /reach/);
    await p.reply('get_custom_alert_state', state(2, [rule()]));
    assert.equal(p.rows().length, 1); assert.match(p.el('custom-alert-status').textContent, /reach/);
  });
}

test('null edit refreshes authority without erasing newer typing or blaming persistence', async () => {
  const p = await loaded(); edit(p, 'submitted'); apply(p); edit(p, 'new draft');
  await p.reply('edit_custom_alert', null);
  assert.match(p.el('custom-alert-r1-msg').textContent, /reach/);
  await p.reply('get_custom_alert_state', state(2, [rule('r1', {search: 'submitted'})]));
  assert.equal(p.rows()[0].search, 'new draft');
  p.fire('custom-alert-r1-cancel', 'click'); assert.equal(p.rows()[0].search, 'submitted');
});

test('markup is literal; orange, extra colours, labels and bundled sound choices survive rendering', async () => {
  const p = await loaded([rule('r1', {name: '<img onerror=bad>', search: '<b>literal</b>', color: '#123abc'})]);
  assert.equal(p.rows()[0].name, '<img onerror=bad>'); assert.equal(p.rows()[0].search, '<b>literal</b>');
  assert.equal(p.rows()[0].color, '#123abc');
  const colors = p.el('custom-alert-r1-color').querySelectorAll('input');
  assert.ok(colors.some(c => c.value === '#ff8c42' && c.getAttribute('aria-label') === 'Orange'));
  assert.deepEqual(p.el('custom-alert-r1-sound').options.map(o => o.value), p.el('alert-event-combat-sound').options.map(o => o.value));
  for (const suffix of ['name', 'search', 'sound', 'cooldown']) {
    const field = p.el('custom-alert-r1-' + suffix);
    assert.ok(field.getAttribute('aria-label') || field.parentNode.children.some(n => n.getAttribute('for') === field.id));
  }
});

const watching = {previews_enabled: true, alerts_enabled: true,
  reader: {running: true, last_error: null, characters: ['Bob', 'Alice'], gamelogs_folder: 'logs'}};
for (const [extra, pattern] of [
  [{}, /inactive.*preferences|preferences.*inactive/i],
  [Object.assign({}, watching, {matcher: {state: 'waiting', detail: null}}), /waiting.*new.*line/i],
  [Object.assign({}, watching, {matcher: {state: 'active', detail: null}}), /active.*Alice.*Bob/i],
  [Object.assign({}, watching, {reader: {running: true, characters: []}}), /no characters/i],
  [Object.assign({}, watching, {reader: {running: false, last_error: 'Reader stopped', characters: ['Bob']}}), /not watching.*Reader stopped/i],
  [Object.assign({}, watching, {matcher: {state: 'degraded', detail: 'matcher_failed'}}), /custom.*fail.*built-in.*Fleet/i]
]) {
  test('custom health: ' + pattern, async () => {
    const p = await loaded([rule('r1', {search: 'query', enabled: true})], extra);
    assert.match(p.el('custom-alert-health').textContent, pattern);
    assert.equal(p.el('custom-alert-r1-edit').disabled, false);
  });
}

test('reverse/null health replies cannot revive stale active state, recovery needs current invocation', async () => {
  const p = await loaded([rule('r1', {search: 'query', enabled: true})], watching);
  p.tick(); p.tick();
  await p.reply('get_custom_alert_state', null, 1);
  await p.reply('get_custom_alert_state', state(1, [rule()], Object.assign({}, watching, {matcher: {state: 'active'}})));
  assert.match(p.el('custom-alert-health').textContent, /reach/);
  p.tick(); await p.reply('get_custom_alert_state', state(1, [rule()], Object.assign({}, watching, {matcher: {state: 'degraded'}})));
  assert.match(p.el('custom-alert-health').textContent, /failed/);
  p.tick(); await p.reply('get_custom_alert_state', state(1, [rule('r1', {enabled: true})], Object.assign({}, watching, {matcher: {state: 'active'}})));
  assert.match(p.el('custom-alert-health').textContent, /active/);
});

test('overall health does not claim nothing can alert for custom-only configuration', async () => {
  const p = await loaded([rule('r1', {search: 'query', enabled: true})], watching);
  await p.reply('get_alert_state', {running: true, characters: ['Alice'], previews_enabled: true,
    gamelogs_folder: 'logs', alerts: {enabled: true, events: {combat: {enabled: false}}, custom_rules: [rule('r1', {enabled: true})]}});
  assert.doesNotMatch(p.el('alerts-health').textContent, /nothing can alert/);
});

test('a health poll overtaking entry hydration cannot strand Add or repaint newer health', async () => {
  const p = page(); p.enter(); p.tick();
  await p.reply('get_custom_alert_state', state(1, [], watching), 1);
  await p.reply('get_custom_alert_state', initial);
  assert.equal(p.el('custom-alert-add').disabled, false);
  assert.doesNotMatch(p.el('custom-alert-health').textContent, /Preferences remain editable/);
});

test('late removal across reentry schedules an owned read, not a stranded deleted row', async () => {
  const p = await loaded(); p.fire('custom-alert-r1-remove', 'click'); await p.confirm(true);
  p.leave(); p.enter();
  await p.reply('remove_custom_alert', result(2, [], {rule_id: 'r1'}));
  assert.equal(pending(p, 'get_custom_alert_state').length, 2);
  await p.reply('get_custom_alert_state', state(1, [rule()]));
  await p.reply('get_custom_alert_state', state(2, []));
  assert.equal(p.rows().length, 0); assert.equal(p.el('custom-alert-add').disabled, false);
});

test('null removal learns a completed delete; poll cannot strand its recovery read', async () => {
  const p = await loaded(); p.fire('custom-alert-r1-remove', 'click'); await p.confirm(true);
  await p.reply('remove_custom_alert', null); p.tick();
  await p.reply('get_custom_alert_state', state(2, []), 1);
  await p.reply('get_custom_alert_state', state(2, []));
  assert.equal(p.rows().length, 0);
});

test('Add never steals focus after the user chooses another row', async () => {
  const p = await loaded(); p.el('custom-alert-add').focus(); p.fire('custom-alert-add', 'click');
  p.fire('custom-alert-r1-edit', 'click');
  await p.reply('add_custom_alert', result(2, [rule(), rule('r2')], {rule_id: 'r2'}));
  assert.equal(p.document.activeElement.id, 'custom-alert-r1-name');
  assert.equal(p.el('custom-alert-r1-editor').hidden, false);
});

test('stale entry state after Add cannot overwrite its accepted revision', async () => {
  const p = await loaded([]); p.enter(); p.fire('custom-alert-add', 'click');
  await p.reply('add_custom_alert', result(2, [rule()]));
  await p.reply('get_custom_alert_state', initial);
  assert.equal(p.rows().length, 1);
});

test('failed persistence restores latest authority; Test is neither a save nor an error clearer', async () => {
  const p = await loaded(); edit(p, 'latest'); apply(p);
  await p.reply('edit_custom_alert', result(2, [rule('r1', {search: 'latest'})]));
  edit(p, 'rejected'); apply(p);
  await p.reply('edit_custom_alert', result(2, [rule('r1', {search: 'latest'})], {applied: false, persisted: false, error: 'Could not save custom alerts.'}));
  assert.equal(p.rows()[0].search, 'latest');
  p.fire('custom-alert-r1-test', 'click');
  await p.reply('test_custom_alert', {applied: true, persisted: false, error: null});
  assert.match(p.el('custom-alert-r1-msg').textContent, /Could not save/);
  assert.doesNotMatch(p.el('custom-alert-r1-msg').textContent, /restart/);
});

test('cancel while a write is pending cannot be undone by its acknowledgement', async () => {
  const p = await loaded(); p.fire('custom-alert-r1-edit', 'click'); edit(p, 'submitted'); apply(p);
  p.fire('custom-alert-r1-cancel', 'click');
  await p.reply('edit_custom_alert', result(2, [rule('r1', {search: 'submitted'})]));
  assert.equal(p.el('custom-alert-r1-editor').hidden, true);
  assert.equal(p.document.activeElement.id, 'custom-alert-r1-edit');
  p.fire('custom-alert-r1-cancel', 'click'); assert.equal(p.rows()[0].search, 'submitted');
});

test('overall no-events note survives only when both custom and built-in sets are disabled', async () => {
  const p = await loaded([]);
  await p.reply('get_alert_state', {running: true, characters: ['Alice'], previews_enabled: true,
    gamelogs_folder: 'logs', alerts: {enabled: true, events: {}, custom_rules: []}});
  assert.match(p.el('alerts-health').textContent, /nothing can alert/);
  p.tick(); p.tick(); await p.reply('get_alert_state', null, 1);
  await p.reply('get_alert_state', {running: true, alerts: {events: {combat: {enabled: true}}}});
  assert.match(p.el('alerts-health').textContent, /reach/);
});

test('a palette choice from a stored extra colour keeps its focused radio after acknowledgment', async () => {
  const p = await loaded([rule('r1', {color: '#123abc'})]);
  const radio = p.el('custom-alert-r1-color').querySelectorAll('input').find(el => el.value === '#ff8c42');
  radio.focus(); p.color('r1', '#ff8c42');
  await p.reply('edit_custom_alert', result(2, [rule()]));
  assert.ok(p.document.activeElement === radio, 'the original radio still owns focus');
  assert.ok(p.el('custom-alert-r1-color').contains(radio));
});

test('remove cannot steal focus from a sibling editor opened during its write', async () => {
  const p = await loaded([rule('r1'), rule('r2')]); p.el('custom-alert-r1-remove').focus();
  p.fire('custom-alert-r1-remove', 'click'); await p.confirm(true); p.fire('custom-alert-r2-edit', 'click');
  await p.reply('remove_custom_alert', result(2, [rule('r2')]));
  assert.equal(p.document.activeElement.id, 'custom-alert-r2-name');
});

test('last-row removal returns keyboard focus to Add', async () => {
  const p = await loaded(); p.el('custom-alert-r1-remove').focus();
  p.fire('custom-alert-r1-remove', 'click'); await p.confirm(true);
  await p.reply('remove_custom_alert', result(2, []));
  assert.equal(p.document.activeElement.id, 'custom-alert-add');
});

test('late reads and a confirmation after section exit cannot mutate the hidden view', async () => {
  const p = await loaded(); p.tick(); p.fire('custom-alert-r1-remove', 'click');
  const health = p.el('custom-alert-health').textContent;
  p.leave(); p.tick(); await p.confirm(true);
  assert.equal(pending(p, 'remove_custom_alert').length, 0);
  await p.reply('get_custom_alert_state', state(2, [], watching));
  await p.reply('get_alert_state', {running: true, characters: ['Late reader'], alerts: {}});
  assert.equal(p.el('custom-alert-health').textContent, health);
  assert.equal(p.rows().length, 1); assert.equal(p.intervals.size, 0);
});

test('an uncertain removed row retains focus ownership through its recovery read', async () => {
  const p = await loaded(); p.el('custom-alert-r1-remove').focus();
  p.fire('custom-alert-r1-remove', 'click'); await p.confirm(true);
  await p.reply('remove_custom_alert', null);
  await p.reply('get_custom_alert_state', state(2, []));
  assert.equal(p.document.activeElement.id, 'custom-alert-add');
});

test('enable refusal reconciles its checkbox while queued style and newer text remain owned', async () => {
  const p = await loaded([rule('r1'), rule('r2')]);
  p.toggle('custom-alert-r2-enabled', true);
  await p.reply('set_custom_alert_enabled', result(1, [rule('r1'), rule('r2')],
    {applied: false, persisted: false, error: 'Second row requires search'}));
  p.toggle('custom-alert-r1-enabled', true); p.choose('custom-alert-r1-sound', 'sly');
  edit(p, 'unsubmitted query'); p.edit('custom-alert-r1-name', 'unsubmitted name');
  await p.reply('set_custom_alert_enabled', result(1, [rule('r1'), rule('r2')],
    {applied: false, persisted: false, error: 'Enter a search before enabling this alert.'}));
  assert.equal(p.rows()[0].enabled, false, 'unrelated newer drafts do not own enabled');
  assert.equal(p.rows()[0].sound, 'sly'); assert.equal(p.rows()[0].search, 'unsubmitted query');
  assert.match(p.el('custom-alert-r1-msg').textContent, /Enter a search/);
  const draft = pending(p, 'edit_custom_alert')[0].args[1];
  assert.equal(draft.enabled, false); assert.equal(draft.search, ''); assert.equal(draft.name, 'Custom alert');
  await p.reply('edit_custom_alert', result(2, [rule('r1', draft), rule('r2')]));
  assert.equal(p.rows()[0].enabled, false); assert.equal(p.rows()[0].name, 'unsubmitted name');
  assert.match(p.el('custom-alert-r1-msg').textContent, /Apply/);
  assert.match(p.el('custom-alert-r2-msg').textContent, /Second row requires search/);
});

test('clear-to-disable reconciles enabled independently of queued style and newer text', async () => {
  const p = await loaded([rule('r1', {search: 'accepted', enabled: true})]);
  edit(p, ''); apply(p); p.choose('custom-alert-r1-sound', 'sly'); edit(p, 'new draft');
  await p.reply('edit_custom_alert', result(2, [rule()]));
  assert.equal(p.rows()[0].enabled, false); assert.equal(p.rows()[0].search, 'new draft');
  assert.equal(p.rows()[0].sound, 'sly');
  const draft = pending(p, 'edit_custom_alert')[0].args[1];
  assert.equal(draft.enabled, false); assert.equal(draft.search, '');
  await p.reply('edit_custom_alert', result(3, [rule('r1', draft)]));
  assert.equal(p.rows()[0].enabled, false); assert.equal(p.rows()[0].search, 'new draft');
});

test('mixed-kind acknowledgments preserve genuinely newer enabled intents in FIFO order', async () => {
  const p = await loaded();
  p.toggle('custom-alert-r1-enabled', true); p.choose('custom-alert-r1-sound', 'sly');
  p.toggle('custom-alert-r1-enabled', false); p.toggle('custom-alert-r1-enabled', true);
  await p.reply('set_custom_alert_enabled', result(1, [rule('r1', {search: 'accepted'})],
    {applied: false, persisted: false, error: 'Enable refused'}));
  assert.equal(p.rows()[0].enabled, true);
  const draft = pending(p, 'edit_custom_alert')[0].args[1]; assert.equal(draft.enabled, false);
  await p.reply('edit_custom_alert', result(2, [rule('r1', draft)]));
  assert.equal(p.rows()[0].enabled, true, 'queued toggle still owns enabled after style acknowledgment');
  assert.deepEqual(pending(p, 'set_custom_alert_enabled')[0].args, ['r1', false]);
  await p.reply('set_custom_alert_enabled', result(2, [rule('r1', draft)]));
  assert.equal(p.rows()[0].enabled, true);
  assert.deepEqual(pending(p, 'set_custom_alert_enabled')[0].args, ['r1', true]);
  await p.reply('set_custom_alert_enabled', result(3, [rule('r1', {...draft, enabled: true})]));
  assert.equal(p.rows()[0].enabled, true);
});

test('Apply canonicalizes unchanged name while a newer search and style keep their intent', async () => {
  const p = await loaded(); p.edit('custom-alert-r1-name', ' Trimmed '); edit(p, 'submitted'); apply(p);
  edit(p, 'newer search'); p.choose('custom-alert-r1-sound', 'sly');
  await p.reply('edit_custom_alert', result(2, [rule('r1', {name: 'Trimmed', search: 'submitted'})]));
  assert.equal(p.rows()[0].name, 'Trimmed'); assert.equal(p.rows()[0].search, 'newer search');
  assert.equal(p.rows()[0].sound, 'sly');
});

test('style refusal restores its unchanged controls without repainting a newer checkbox', async () => {
  const p = await loaded(); p.color('r1', '#4dff7a'); p.toggle('custom-alert-r1-enabled', true);
  await p.reply('edit_custom_alert', result(1, [rule('r1', {search: 'accepted'})],
    {applied: false, persisted: false, error: 'Style refused'}));
  assert.equal(p.rows()[0].color, '#ff8c42'); assert.equal(p.rows()[0].enabled, true);
  assert.match(p.el('custom-alert-r1-msg').textContent, /Style refused/);
});

test('one style field can reconcile while another holds newer intent', async () => {
  const p = await loaded(); p.color('r1', '#4dff7a'); p.choose('custom-alert-r1-sound', 'sly');
  await p.reply('edit_custom_alert', result(1, [rule('r1', {search: 'accepted'})],
    {applied: false, persisted: false, error: 'Colour refused'}));
  assert.equal(p.rows()[0].color, '#ff8c42'); assert.equal(p.rows()[0].sound, 'sly');
  // A later full style submission can retry the captured colour explicitly.
  assert.equal(pending(p, 'edit_custom_alert')[0].args[1].color, '#4dff7a');
});

for (const reject of [false, true]) {
  test('entry issued before uncertain Add cannot release admission, rejected=' + reject, async () => {
    const p = await loaded([]); p.fire('custom-alert-add', 'click'); p.leave(); p.enter();
    await p.reply('add_custom_alert', null, 0, reject);
    assert.equal(pending(p, 'get_custom_alert_state').length, 2);
    await p.reply('get_custom_alert_state', initial);
    assert.equal(p.el('custom-alert-add').disabled, true, 'pre-outcome entry is not recovery authority');
    p.fire('custom-alert-add', 'click'); assert.equal(pending(p, 'add_custom_alert').length, 0);
    await p.reply('get_custom_alert_state', state(2, [rule()]));
    assert.equal(p.el('custom-alert-add').disabled, false); assert.equal(p.rows().length, 1);
    assert.equal(pending(p, 'add_custom_alert').length, 0);
  });
}

test('pre-edit hydration cannot resume a queued style after uncertain persistence', async () => {
  const p = await loaded(); p.enter();
  edit(p, 'possibly persisted'); apply(p); p.choose('custom-alert-r1-sound', 'sly'); edit(p, 'newer typing');
  await p.reply('edit_custom_alert', null);
  assert.equal(pending(p, 'edit_custom_alert').length, 0);
  await p.reply('get_custom_alert_state', state(1, [rule('r1', {search: 'accepted'})]));
  assert.equal(pending(p, 'edit_custom_alert').length, 0, 'old hydration cannot resume the FIFO');
  assert.equal(p.el('custom-alert-r1-apply').disabled, true);
  await p.reply('get_custom_alert_state', state(2, [rule('r1', {search: 'possibly persisted'})]));
  const draft = pending(p, 'edit_custom_alert')[0].args[1];
  assert.equal(draft.search, 'possibly persisted'); assert.equal(draft.sound, 'sly');
  assert.equal(p.rows()[0].search, 'newer typing');
  await p.reply('edit_custom_alert', result(3, [rule('r1', draft)]));
  assert.equal(p.rows()[0].search, 'newer typing');
});

test('each uncertain row requires a read issued after its own outcome', async () => {
  const rules = [rule('r1', {search: 'first'}), rule('r2', {search: 'second'})];
  const p = await loaded(rules);
  edit(p, 'first updated'); apply(p); p.choose('custom-alert-r1-sound', 'sly');
  edit(p, 'second updated', 'r2'); apply(p, 'r2'); p.choose('custom-alert-r2-sound', 'sly');
  await p.reply('edit_custom_alert', null); // issues first recovery read
  await p.reply('edit_custom_alert', null); // issues second recovery read
  await p.reply('get_custom_alert_state', state(2, [rule('r1', {search: 'first updated'}), rules[1]]));
  assert.equal(pending(p, 'edit_custom_alert').length, 1);
  assert.equal(pending(p, 'edit_custom_alert')[0].args[0], 'r1');
  assert.equal(p.el('custom-alert-r2-apply').disabled, true);
  await p.reply('get_custom_alert_state', state(3, [rule('r1', {search: 'first updated'}), rule('r2', {search: 'second updated'})]));
  const second = pending(p, 'edit_custom_alert').find(call => call.args[0] === 'r2');
  assert.equal(second.args[1].search, 'second updated');
});

test('fresh equal-revision recovery can release Add; old-view recovery cannot', async () => {
  const p = await loaded([]); p.fire('custom-alert-add', 'click');
  await p.reply('add_custom_alert', null); p.leave(); p.enter();
  await p.reply('get_custom_alert_state', initial); // recovery belongs to the left view
  assert.equal(p.el('custom-alert-add').disabled, true);
  await p.reply('get_custom_alert_state', initial); // fresh current-view read, no commit occurred
  assert.equal(p.el('custom-alert-add').disabled, false);
  assert.equal(pending(p, 'add_custom_alert').length, 0);
});

test('null recovery keeps the row queue blocked until a later owned authority read', async () => {
  const p = await loaded(); edit(p, 'unknown'); apply(p); p.choose('custom-alert-r1-sound', 'sly');
  await p.reply('edit_custom_alert', null); await p.reply('get_custom_alert_state', null);
  assert.equal(pending(p, 'edit_custom_alert').length, 0);
  p.tick(); await p.reply('get_custom_alert_state', state(1, [rule('r1', {search: 'accepted'})]));
  assert.equal(pending(p, 'edit_custom_alert').length, 0, 'health alone cannot release uncertainty');
  p.leave(); p.enter();
  await p.reply('get_custom_alert_state', state(1, [rule('r1', {search: 'accepted'})]));
  assert.equal(pending(p, 'edit_custom_alert')[0].args[1].search, 'accepted');
});

(async function () {
  let failures = 0;
  for (const {name, run} of tests) {
    try { await run(); console.log('PASS ' + name); }
    catch (error) { failures++; console.error('FAIL ' + name + '\n' + error.stack); }
  }
  console.log(`${tests.length - failures}/${tests.length} alerts runtime tests passed`);
  if (failures) process.exitCode = 1;
}());
