#!/usr/bin/env node
'use strict';

// Execute the real settings module with the DOM/bridge boundaries replaced.
// Deferred replies make edits between submission and acknowledgement repeatable;
// this is not a renderer or a substitute for Windows/WebView2 smoke testing.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../wingman/web/settings.js'), 'utf8');
const {createDOM} = require('../tests/fixtures/screenshot_dom.cjs');
const {document: markup} = createDOM(JSON.parse(fs.readFileSync(0, 'utf8')));
const tests = [];
function test(name, run) { tests.push({name, run}); }
function turn() { return new Promise(resolve => setImmediate(resolve)); }
const accepted = {applied: true, persisted: true, error: null};
const refused = {applied: false, persisted: false, error: 'Not accepted'};

test('startup settings and their feedback stay separate from build information', () => {
  const startup = markup.getElementById('start-on-login').closest('section');
  const about = markup.getElementById('about-version').closest('section');
  assert.ok(startup !== about, 'startup is configuration, not build information');
  assert.ok(startup.contains(markup.getElementById('msg-about')), 'startup outcome stays with its control');
  assert.ok(markup.getElementById('section-general').contains(startup));
});

test('plugin readiness and stored-token context stay beside their owning controls', () => {
  const status = markup.getElementById('fr-status');
  assert.equal(status.getAttribute('role'), 'status');
  assert.ok(status.classList.contains('operational-status'));
  assert.ok(status.closest('section').contains(markup.getElementById('btn-fr-check')));
  assert.equal(status.hidden, false);
  const token = markup.getElementById('wanderer-token');
  const cue = markup.getElementById('wanderer-credential');
  assert.ok(token.parentNode === cue.parentNode, 'stored credential context is beside the token input');
  assert.ok(token.parentNode.children.indexOf(cue) < token.parentNode.children.indexOf(token),
    'stored-state cue precedes the intentionally empty token input');
  assert.ok(token.getAttribute('aria-describedby').split(/\s+/).includes(cue.id));
  assert.equal(markup.querySelectorAll('#wanderer-credential').length, 1, 'one credential feedback owner');
});

class Element {
  constructor(id) {
    this.id = id;
    this.value = '';
    this.checked = false;
    this.hidden = false;
    this.disabled = false;
    this.textContent = '';
    this.className = '';
    this.title = '';
    this.type = 'text';
    this.dataset = {};
    this.listeners = {};
  }
  addEventListener(name, listener) {
    (this.listeners[name] || (this.listeners[name] = [])).push(listener);
  }
  dispatchEvent(event) {
    event.target = event.target || this;
    event.preventDefault = event.preventDefault || function () {};
    for (const listener of this.listeners[event.type] || []) listener.call(this, event);
  }
  setAttribute(name, value) { this[name] = value; }
  removeAttribute(name) { delete this[name]; }
  get classList() {
    return {toggle: (name, on) => {
      const classes = this.className.split(/\s+/).filter(value => value && value !== name);
      if (on) classes.push(name);
      this.className = classes.join(' ');
    }};
  }
}

function page(hydrate = true, fightrecorder = false, previewSize = false) {
  const ids = [
    'f-privacy', 'f-category', 'f-recdir', 'f-gamelogs', 'f-webhook',
    'show-eve-tools', 'start-on-login', 'webhook-status', 'btn-webhook-show',
    'btn-webhook-remove', 'detect-note', 'gamelogs-note', 'about-version',
    'msg-general', 'msg-about', 'msg-uploads', 'msg-notify', 'msg-recdir',
    'msg-gamelogs', 'msg-discord', 'category-draft', 'btn-auth', 'tos-link', 'btn-update-check',
    'btn-update-download', 'btn-update-install', 'restore-preview-positions',
    'restore-preview-positions-status', 'preview-label-size', 'preview-label-size-status',
    'preview-hide-active-preview', 'preview-hide-active-preview-status'
  ];
  if (fightrecorder) ids.push('fr-status', 'btn-fr-check', 'btn-fr-update', 'msg-fightrecorder',
    'preview-minimize-inactive', 'preview-minimize-inactive-status', 'sigbar-enabled', 'sigbar-enabled-status');
  if (previewSize) ids.push('preview-default-size', 'preview-default-size-status');
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
  const categoryDraft = markup.getElementById('category-draft');
  if (categoryDraft) elements['category-draft'].hidden = categoryDraft.hidden;
  if (previewSize) elements['preview-default-size-status'].textContent = markup.getElementById('preview-default-size-status').textContent;
  if (fightrecorder) elements['btn-fr-update'].className = 'btn acc';
  const labelSize = markup.getElementById('preview-label-size');
  // Only this select needs options in the focused seam. Use the actual markup
  // supplied by pytest, not a second hand-kept copy of the preset table.
  elements['preview-label-size'].options = labelSize ? labelSize.options : [];
  if (labelSize) elements['preview-label-size'].value = labelSize.value;
  const notify = ['toast', 'popup'].map(value => {
    const input = new Element('notify-' + value);
    input.name = 'notify';
    input.type = 'radio';
    input.value = value;
    return input;
  });
  const browse = ['recording', 'gamelogs'].map(which => {
    const input = new Element('browse-' + which);
    input.dataset.browse = which;
    return input;
  });
  const detect = ['recording', 'gamelogs'].map(which => {
    const input = new Element('detect-' + which);
    input.dataset.detect = which;
    return input;
  });
  const document = new Element('document');
  document.activeElement = new Element('body');
  document.querySelectorAll = selector => {
    if (selector === 'input[name="notify"]') return notify;
    if (selector === '[data-browse]') return browse;
    if (selector === '[data-detect]') return detect;
    throw new Error('Unhandled selector: ' + selector);
  };
  document.querySelector = selector => {
    assert.equal(selector, 'input[name="notify"]:checked');
    return notify.find(input => input.checked) || null;
  };
  const calls = [];
  const restoreEvents = [];
  document.addEventListener('wm:preview-restore-positions', event => restoreEvents.push(event.detail.enabled));
  const gates = [];
  const WM = {
    el: id => elements[id] || null,
    setEnabled: (id, enabled) => {
      const element = typeof id === 'string' ? elements[id] : id;
      element.disabled = !enabled;
    },
    apply_eve_gate: value => gates.push(value),
    handle: () => {},
    confirm: () => Promise.resolve(true),
    send: (method, ...args) => {
      if (method === 'auth_labels') return Promise.resolve({});
      let resolve;
      const promise = new Promise(done => { resolve = done; });
      calls.push({method, args, resolve});
      return promise;
    }
  };
  vm.runInNewContext(source, {window: {WM}, WM, document, Promise,
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }}, {
    filename: 'wingman/web/settings.js'
  });
  const api = {
    el: id => elements[id], calls, gates, notify, restoreEvents,
    hydrate(settings = {}) {
      document.dispatchEvent({type: 'wm:settings', detail: {
        settings: Object.assign({privacy: 'unlisted', category: '20', notify_mode: 'toast',
          show_eve_tools: true, recording_dir: 'C:\\old', gamelogs_dir: 'C:\\logs',
          discord_webhook: '', preview: {restore_preview_positions: true}}, settings),
        start_on_login: false, detected: {}, webhook_status: 'not configured'
      }});
    },
    focus(id) { document.activeElement = elements[id]; },
    fire(id, type, extra = {}) { elements[id].dispatchEvent(Object.assign({type}, extra)); },
    edit(id, value) {
      elements[id].value = value;
      this.fire(id, 'input');
    },
    async submit(id, value, event = id === 'f-category' ? 'keydown' : 'change') {
      this.edit(id, value);
      this.fire(id, event, {key: 'Enter'});
      await turn();
    },
    async toggle(id, value) {
      elements[id].checked = value;
      this.fire(id, 'change');
      await turn();
    },
    async choose(value) {
      notify.forEach(input => { input.checked = input.value === value; });
      notify.find(input => input.checked).dispatchEvent({type: 'change'});
      await turn();
    },
    picked() { return notify.find(input => input.checked).value; },
    async reply(method, result, args) {
      const index = calls.findIndex(call => call.method === method);
      assert.notEqual(index, -1, 'Expected pending call to ' + method);
      const call = calls.splice(index, 1)[0];
      if (args) assert.deepEqual(call.args, args);
      call.resolve(result);
      await turn();
    },
    async pick(which, kind, value) {
      const button = (kind === 'browse' ? browse : detect).find(
        item => item.dataset[kind] === which);
      button.dispatchEvent({type: 'click'});
      await this.reply(kind === 'browse' ? 'pick_folder' : 'detect_folder', value);
    }
  };
  if (hydrate) api.hydrate();
  return api;
}

for (const [name, clientSizes, identity, dimensions, preview] of [
  ['named', {'Pilot Example': [1600, 900]}, 'Pilot Example', '1600x900', '400x227'],
  ['named after unnamed', {'hwnd:0x123': [1024, 768], 'Pilot Example': [1600, 900]}, 'Pilot Example', '1600x900', '400x227'],
  ['unnamed only', {'hwnd:0x123': [1024, 768]}, null, '1024x768', '400x301']
]) {
  test('default-size guidance identifies ' + name + ' without exposing native identity', async () => {
    const p = page(true, false, true);
    p.hydrate({preview: {width: 400, height: 240}});
    const original = JSON.stringify(clientSizes);
    await p.reply('get_preview_hotkey_state', {client_sizes: clientSizes});
    const hint = p.el('preview-default-size-status').textContent;
    if (identity) assert.ok(hint.includes(identity), 'prefer the available character name');
    else assert.match(hint, /unnamed.*client/i);
    assert.doesNotMatch(hint, /hwnd:|0x123/);
    assert.ok(hint.includes(dimensions), 'dimensions belong to the chosen client');
    assert.ok(hint.includes(preview), 'the chosen client supplies the undistorted height');
    assert.equal(p.el('preview-default-size').value, '400x240', 'guidance never applies a size');
    assert.equal(JSON.stringify(clientSizes), original, 'identity keys remain unchanged');
    assert.deepEqual(p.calls, []);
  });
}

test('default-size guidance has no invented client when the read is empty or unavailable', async () => {
  for (const payload of [{client_sizes: {}}, null]) {
    const p = page(true, false, true);
    const initial = p.el('preview-default-size-status').textContent;
    await p.reply('get_preview_hotkey_state', payload);
    assert.equal(p.el('preview-default-size-status').textContent, initial);
    assert.deepEqual(p.calls, []);
  }
});

test('a delayed client-size hint never replaces the default-size refusal', async () => {
  const p = page(true, false, true);
  p.hydrate({preview: {width: 400, height: 240}});
  await p.submit('preview-default-size', 'bad size', 'keydown');
  await p.reply('parse_preview_size', {error: 'Size refused.'});
  await p.reply('get_preview_hotkey_state', {client_sizes: {'hwnd:0x123': [1024, 768], 'Pilot Example': [1600, 900]}});
  assert.equal(p.el('preview-default-size-status').textContent, 'Size refused.');
  assert.equal(p.el('preview-default-size').value, 'bad size');
  assert.deepEqual(p.calls, []);
});

test('active preview checkbox hydrates before writing and stays editable while off', async () => {
  const box = markup.getElementById('preview-hide-active-preview');
  assert.ok(box, 'active-preview control is present');
  assert.ok(box.closest('label').classList.contains('check'));
  const p = page(false);
  await p.toggle('preview-hide-active-preview', true);
  assert.equal(p.calls.length, 0);
  p.hydrate({preview: {enabled: false, hide_active_preview: true}});
  assert.equal(p.el('preview-hide-active-preview').checked, true);
  assert.equal(p.el('preview-hide-active-preview').disabled, false);
  p.hydrate({preview: {enabled: false}});
  assert.equal(p.el('preview-hide-active-preview').checked, false);
});

test('active preview rapid replies preserve queued choices and field-local refusal', async () => {
  const p = page();
  await p.toggle('preview-hide-active-preview', true);
  await p.toggle('preview-hide-active-preview', false);
  assert.equal(p.calls.length, 1);
  p.hydrate({preview: {hide_active_preview: true}});
  assert.equal(p.el('preview-hide-active-preview').checked, false);
  await p.reply('set_preview_hide_active_preview', accepted, [true]);
  assert.equal(p.el('preview-hide-active-preview').checked, false);
  await p.reply('set_preview_hide_active_preview', refused, [false]);
  assert.equal(p.el('preview-hide-active-preview').checked, true);
  assert.equal(p.el('preview-hide-active-preview-status').textContent, 'Not accepted');
  p.el('preview-label-size-status').textContent = 'Other field failure';
  await p.toggle('preview-hide-active-preview', false);
  await p.reply('set_preview_hide_active_preview', accepted, [false]);
  assert.equal(p.el('preview-hide-active-preview').checked, false);
  assert.equal(p.el('preview-hide-active-preview-status').textContent, '');
  assert.equal(p.el('preview-label-size-status').textContent, 'Other field failure');
});

for (const reply of [null, {applied: false, persisted: false}, {applied: true, persisted: false}]) {
  test('active preview gives honest feedback for ' + JSON.stringify(reply), async () => {
    const p = page();
    await p.toggle('preview-hide-active-preview', true);
    await p.reply('set_preview_hide_active_preview', reply);
    assert.equal(p.el('preview-hide-active-preview').checked, !!(reply && reply.applied));
    assert.ok(p.el('preview-hide-active-preview-status').textContent);
    if (!reply || !reply.applied) assert.doesNotMatch(p.el('preview-hide-active-preview-status').textContent, /for this session/);
  });
}

test('label size has production markup and a registered change owner', async () => {
  assert.ok(markup.getElementById('preview-label-size'), 'label-size select exists');
  assert.ok(markup.getElementById('preview-label-size-status'), 'label-size status exists');
  const p = page();
  assert.equal((p.el('preview-label-size').listeners.change || []).length, 1);
});

for (const stored of ['large', undefined]) {
  test('first label-size hydration overrides uncommitted focused interaction: ' + stored, async () => {
    const p = page(false);
    p.focus('preview-label-size');
    await p.submit('preview-label-size', 'extra_large');
    assert.deepEqual(p.calls, [], 'nothing writes before hydration');
    p.hydrate({preview: {label_size: stored}});
    assert.equal(p.el('preview-label-size').value, stored || 'standard');
    await p.submit('preview-label-size', 'large');
    await p.reply('set_preview_label_size', accepted, ['large']);
  });
}

test('label size serializes and rolls back to the acknowledged key', async () => {
  const p = page();
  await p.submit('preview-label-size', 'large');
  await p.submit('preview-label-size', 'extra_large');
  assert.equal(p.calls.filter(c => c.method === 'set_preview_label_size').length, 1);
  await p.reply('set_preview_label_size', accepted, ['large']);
  assert.equal(p.el('preview-label-size').value, 'extra_large');
  await p.reply('set_preview_label_size', refused, ['extra_large']);
  assert.equal(p.el('preview-label-size').value, 'large');
  assert.ok(p.el('preview-label-size-status').textContent);
});

for (const outcome of [refused, null]) {
  test('focused label-size refusal restores acknowledgement despite stale hydration: ' + JSON.stringify(outcome), async () => {
    const p = page();
    p.focus('preview-label-size');
    await p.submit('preview-label-size', 'large');
    await p.reply('set_preview_label_size', accepted);
    await p.submit('preview-label-size', 'extra_large');
    p.hydrate({preview: {label_size: 'standard'}});
    assert.equal(p.el('preview-label-size').value, 'extra_large');
    await p.reply('set_preview_label_size', outcome);
    assert.equal(p.el('preview-label-size').value, 'large');
    assert.ok(p.el('preview-label-size-status').textContent);
  });
}

for (const outcome of [accepted, refused, null]) {
  test('older label-size reply preserves a newer unsubmitted draft: ' + JSON.stringify(outcome), async () => {
    const p = page();
    await p.submit('preview-label-size', 'large');
    p.edit('preview-label-size', 'extra_large');
    await p.reply('set_preview_label_size', outcome);
    assert.equal(p.el('preview-label-size').value, 'extra_large');
  });
}

test('label-size retry clears only its own error and retains a newer draft', async () => {
  const p = page();
  await p.submit('preview-label-size', 'large');
  await p.reply('set_preview_label_size', refused);
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', refused);
  await p.submit('preview-label-size', 'large');
  p.edit('preview-label-size', 'extra_large');
  await p.reply('set_preview_label_size', accepted);
  assert.equal(p.el('preview-label-size').value, 'extra_large');
  assert.equal(p.el('preview-label-size-status').textContent, '');
  assert.equal(p.el('preview-label-size-status').hidden, true);
  assert.ok(p.el('msg-uploads').textContent);
});

test('an unrelated success does not clear the label-size error', async () => {
  const p = page();
  await p.submit('preview-label-size', 'large');
  await p.reply('set_preview_label_size', refused);
  await p.submit('f-category', '22');
  await p.reply('set_category', accepted);
  assert.ok(p.el('preview-label-size-status').textContent);
});

test('label size stays editable with previews and labels off', async () => {
  const p = page();
  p.hydrate({preview: {enabled: false, show_labels: false, label_size: 'extra_large'}});
  assert.equal(p.el('preview-label-size').value, 'extra_large');
  assert.equal(p.el('preview-label-size').disabled, false);
  await p.submit('preview-label-size', 'large');
  await p.reply('set_preview_label_size', accepted, ['large']);
  assert.equal(p.el('preview-label-size').value, 'large');
});

for (const latest_tag of ['', 'v1.2.3']) {
  test('FightRecorder unknown currency does not claim a verified update: ' + latest_tag, async () => {
    const p = page(true, true);
    await p.reply('fightrecorder_status', {installed: true, detected: true, path: 'synthetic.dll',
      up_to_date: null, latest_tag, error: ''}, [false]);
    assert.match(p.el('fr-status').textContent, /Installed.*update status unknown/i);
    if (!latest_tag) assert.match(p.el('fr-status').textContent, /Check for updates/);
    if (latest_tag) assert.ok(p.el('fr-status').textContent.includes(latest_tag));
    assert.doesNotMatch(p.el('fr-status').textContent, /update is available|up to date/i);
    assert.equal(p.el('btn-fr-update').textContent, 'Install latest');
    assert.equal(p.el('btn-fr-update').hidden, false);
    assert.equal(p.el('btn-fr-update').disabled, false);
    assert.equal(p.calls.length, 0, 'no automatic check or install');
    p.fire('btn-fr-check', 'click');
    await p.reply('fightrecorder_status', {installed: true, detected: true, path: 'synthetic.dll',
      up_to_date: false, latest_tag: 'v1.2.4', error: ''}, [true]);
    assert.match(p.el('fr-status').textContent, /update is available.*v1\.2\.4/i);
    assert.equal(p.el('btn-fr-update').textContent, 'Update');
    assert.equal(p.el('btn-fr-update').hidden, false);
    p.fire('btn-fr-check', 'click');
    await p.reply('fightrecorder_status', {installed: true, detected: true, path: 'synthetic.dll',
      up_to_date: true, latest_tag: 'v1.2.4', error: ''}, [true]);
    assert.match(p.el('fr-status').textContent, /Up to date/);
    assert.equal(p.el('btn-fr-update').hidden, true);
    assert.equal(p.calls.length, 0);
  });
}

test('FightRecorder install emphasis follows known need without disabling unknown-state recovery', async () => {
  const p = page(true, true);
  const button = p.el('btn-fr-update');
  const local = {installed: true, detected: true, path: 'synthetic.dll',
    up_to_date: null, latest_tag: '', error: ''};
  await p.reply('fightrecorder_status', local, [false]);
  assert.doesNotMatch(button.className, /\bacc\b/);
  assert.match(button.className, /\bbtn\b/);
  assert.equal(button.disabled, false);
  assert.equal(button.hidden, false);
  p.fire('btn-fr-update', 'click');
  assert.equal(button.disabled, true);
  await p.reply('update_fightrecorder', {ok: true, tag: 'v1.2.4'}, []);
  await p.reply('fightrecorder_status', local, [false]);
  assert.doesNotMatch(button.className, /\bacc\b/);
  assert.equal(button.disabled, false);
  for (const [change, accented, hidden] of [
    [{up_to_date: false, latest_tag: 'v1.2.5'}, true, false],
    [{up_to_date: null}, false, false],
    [{installed: false}, true, false],
    [{up_to_date: true}, false, true],
    [{up_to_date: false}, true, false],
    [{error: 'Could not check releases.'}, false, true],
    [{installed: false}, true, false],
    [{detected: false}, false, true]
  ]) {
    p.fire('btn-fr-check', 'click');
    await p.reply('fightrecorder_status', Object.assign({}, local, change), [true]);
    assert.equal(/\bacc\b/.test(button.className), accented, JSON.stringify(change));
    assert.match(button.className, /\bbtn\b/);
    assert.equal(button.hidden, hidden);
    assert.equal(button.disabled, false, 'emphasis never changes existing admission');
  }
  assert.equal(p.calls.length, 0);
});

test('category draft guidance is associated with its input, separate from shared outcomes', () => {
  const field = markup.getElementById('f-category');
  const hint = markup.getElementById('category-draft');
  assert.ok(hint, 'category has a draft-only hint');
  assert.equal(markup.querySelectorAll('#category-draft').length, 1);
  assert.ok(field.closest('section').contains(hint));
  assert.ok(field.getAttribute('aria-describedby').split(/\s+/).includes(hint.id));
  assert.ok(field.getAttribute('aria-describedby').split(/\s+/).includes('msg-uploads'));
  assert.ok(hint !== markup.getElementById('msg-uploads'), 'drafts never take the refusal slot');
  assert.equal(hint.hidden, true);
});

test('category gestures before hydration neither commit nor claim an unsaved setting', async () => {
  const p = page(false);
  p.focus('f-category');
  p.edit('f-category', '22');
  p.fire('f-category', 'change');
  p.fire('f-category', 'blur');
  p.fire('f-category', 'keydown', {key: 'Enter'});
  await turn();
  assert.deepEqual(p.calls, []);
  assert.equal(p.el('category-draft').hidden, true);
  p.hydrate();
  assert.equal(p.el('f-category').value, '22', 'focused early draft survives hydration');
  assert.match(p.el('category-draft').textContent, /Enter/);
  assert.deepEqual(p.calls, [], 'hydration does not submit the early draft');
});

test('category change and dirty blur keep the draft without submitting', async () => {
  const p = page();
  p.edit('f-category', '22');
  p.fire('f-category', 'change');
  p.fire('f-category', 'blur');
  await turn();
  assert.deepEqual(p.calls, [], 'only Enter submits free text');
  assert.equal(p.el('f-category').value, '22');
  assert.equal(p.el('category-draft').hidden, false);
  assert.match(p.el('category-draft').textContent, /Enter/);
  assert.equal(p.el('msg-uploads').textContent, '', 'one owner for draft feedback');
  p.edit('f-category', ' 20 ');
  p.fire('f-category', 'blur');
  assert.equal(p.el('category-draft').hidden, true, 'returning to the accepted value clears guidance');
  assert.deepEqual(p.calls, []);
});

test('category Enter submits the numeric string once and settles guidance on acceptance', async () => {
  const p = page();
  p.edit('f-category', ' 022 ');
  p.fire('f-category', 'keydown', {key: 'Tab'});
  await turn();
  assert.deepEqual(p.calls, []);
  let prevented = false;
  p.fire('f-category', 'keydown', {key: 'Enter', preventDefault() { prevented = true; }});
  p.fire('f-category', 'change');
  p.fire('f-category', 'blur');
  await turn();
  assert.equal(prevented, true);
  assert.equal(p.calls.length, 1, 'the Enter/change/blur sequence sends one write');
  assert.equal(p.el('category-draft').hidden, true, 'already-submitted text needs no Enter reminder');
  await p.reply('set_category', accepted, [' 022 ']);
  assert.equal(p.el('category-draft').hidden, true);
  p.fire('f-category', 'blur');
  assert.equal(p.el('category-draft').hidden, true);
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', refused);
  assert.equal(p.el('f-category').value, '022', 'the baseline remains a trimmed string, not an integer');
  assert.equal(p.el('category-draft').hidden, true, 'a restored refusal is not an unsaved draft');
});

for (const outcome of [accepted, refused, null]) {
  test('queued category refusal restores the latest accepted baseline: ' + JSON.stringify(outcome), async () => {
    const p = page();
    await p.submit('f-category', '22');
    await p.submit('f-category', 'invalid');
    p.fire('f-category', 'blur');
    assert.equal(p.el('category-draft').hidden, true, 'the newest edit is already queued');
    assert.equal(p.calls.length, 1, 'one category request at a time');
    await p.reply('set_category', outcome, ['22']);
    assert.equal(p.el('f-category').value, 'invalid');
    assert.equal(p.el('category-draft').hidden, true, 'an old reply cannot mark queued text as unsubmitted');
    await p.reply('set_category', refused, ['invalid']);
    assert.equal(p.el('f-category').value, outcome && outcome.applied ? '22' : '20');
    assert.equal(p.el('category-draft').hidden, true);
    assert.match(p.el('msg-uploads').className, /err/);
  });

  test('a late privacy reply cannot erase category draft guidance: ' + JSON.stringify(outcome), async () => {
    const p = page();
    await p.submit('f-privacy', 'private');
    p.edit('f-category', '22');
    p.fire('f-category', 'blur');
    const guidance = p.el('category-draft').textContent;
    assert.match(guidance, /Enter/);
    await p.reply('set_privacy', outcome, ['private']);
    assert.equal(p.el('f-category').value, '22');
    assert.equal(p.el('category-draft').textContent, guidance);
    assert.equal(p.el('category-draft').hidden, false);
    if (!outcome || !outcome.applied) assert.match(p.el('msg-uploads').className, /err/);
    assert.deepEqual(p.calls, [], 'a discrete field reply never submits a category draft');
  });
}

test('newer unsubmitted text warns while category writes are queued', async () => {
  const p = page();
  await p.submit('f-category', '22');
  await p.submit('f-category', '23');
  p.edit('f-category', '24');
  p.fire('f-category', 'blur');
  const guidance = p.el('category-draft').textContent;
  assert.match(guidance, /Enter/);
  await p.reply('set_category', accepted, ['22']);
  assert.equal(p.el('category-draft').textContent, guidance);
  await p.reply('set_category', accepted, ['23']);
  assert.equal(p.el('f-category').value, '24');
  assert.equal(p.el('category-draft').textContent, guidance);
  assert.equal(p.el('category-draft').hidden, false);
});

test('an older accepted category reply clears a now-clean draft hint without erasing privacy refusal', async () => {
  const p = page();
  await p.submit('f-privacy', 'private');
  await p.reply('set_privacy', Object.assign({}, refused, {error: 'Privacy not saved.'}));
  await p.submit('f-category', '22');
  p.edit('f-category', '23');
  p.edit('f-category', ' 22 ');
  p.fire('f-category', 'blur');
  assert.match(p.el('category-draft').textContent, /Enter/);
  await p.reply('set_category', accepted, ['22']);
  assert.equal(p.el('f-category').value, ' 22 ', 'semantic reconciliation never rewrites the draft');
  assert.equal(p.el('category-draft').hidden, true, 'the draft now equals the accepted value');
  assert.equal(p.el('msg-uploads').textContent, 'Privacy not saved.');
  assert.match(p.el('msg-uploads').className, /err/);
});

test('an accepted category reply reveals a newer draft made dirty by the new baseline', async () => {
  const p = page();
  await p.submit('f-category', '22');
  p.edit('f-category', '20');
  assert.equal(p.el('category-draft').hidden, true, 'the draft still equals the old baseline');
  await p.reply('set_category', accepted, ['22']);
  assert.equal(p.el('f-category').value, '20');
  assert.equal(p.el('category-draft').hidden, false);
  assert.match(p.el('category-draft').textContent, /Enter/);
});

test('category draft guidance and its successful write preserve an unrelated privacy refusal', async () => {
  const p = page();
  await p.submit('f-privacy', 'private');
  await p.reply('set_privacy', Object.assign({}, refused, {error: 'Privacy not saved.'}));
  p.edit('f-category', '22');
  p.fire('f-category', 'blur');
  assert.match(p.el('category-draft').textContent, /Enter/);
  assert.equal(p.el('msg-uploads').textContent, 'Privacy not saved.');
  await p.submit('f-category', '22');
  await p.reply('set_category', accepted);
  assert.equal(p.el('category-draft').hidden, true);
  assert.equal(p.el('msg-uploads').textContent, 'Privacy not saved.');
  assert.match(p.el('msg-uploads').className, /err/);
});

for (const focused of [false, true]) {
  test('category refusal restores acknowledged 22, focused=' + focused, async () => {
    const p = page();
    if (focused) p.focus('f-category');
    await p.submit('f-category', ' 22 ');
    await p.reply('set_category', accepted, [' 22 ']);
    await p.submit('f-category', 'invalid');
    await p.reply('set_category', refused);
    assert.equal(p.el('f-category').value, '22');
    assert.match(p.el('msg-uploads').className, /err/);
  });
}

for (const [which, id, slot] of [
  ['recording', 'f-recdir', 'msg-recdir'], ['gamelogs', 'f-gamelogs', 'msg-gamelogs']
]) {
  test(which + ' accepted folder then blur has no unsaved warning', async () => {
    const p = page();
    p.focus(id);
    await p.submit(id, ' C:\\new ', 'keydown');
    await p.reply('set_folder', accepted, [which, ' C:\\new ']);
    p.fire(id, 'blur');
    assert.doesNotMatch(p.el(slot).textContent, /Press Enter/);
    await p.submit(id, 'missing', 'keydown');
    await p.reply('set_folder', refused);
    assert.equal(p.el(id).value, 'C:\\new');
    assert.equal(p.el(id).title, 'C:\\new');
  });
  for (const kind of ['browse', 'detect']) {
    test(which + ' ' + kind + ' advances the folder baseline', async () => {
      const p = page();
      await p.pick(which, kind, 'C:\\picked');
      await p.reply('set_folder', accepted, [which, 'C:\\picked']);
      p.fire(id, 'blur');
      assert.doesNotMatch(p.el(slot).textContent, /Press Enter/);
    });
  }
}

test('privacy refusal restores accepted value even while focused', async () => {
  const p = page();
  p.focus('f-privacy');
  await p.submit('f-privacy', 'private');
  await p.reply('set_privacy', accepted, ['private']);
  await p.submit('f-privacy', 'public');
  await p.reply('set_privacy', refused);
  assert.equal(p.el('f-privacy').value, 'private');
});

test('notify refusal restores the accepted radio', async () => {
  const p = page();
  await p.choose('popup');
  await p.reply('set_notify_mode', accepted, ['popup']);
  await p.choose('toast');
  await p.reply('set_notify_mode', refused);
  assert.equal(p.picked(), 'popup');
});

for (const [id, method, initial] of [
  ['show-eve-tools', 'set_show_eve_tools', true],
  ['start-on-login', 'set_start_on_login', false],
  ['restore-preview-positions', 'set_restore_preview_positions', true]
]) {
  test(id + ' rapid toggles serialize and restore the last acknowledgement', async () => {
    const p = page();
    p.focus(id);
    await p.toggle(id, !initial);
    await p.toggle(id, initial);
    assert.equal(p.calls.filter(call => call.method === method).length, 1,
      'one in-flight write per field preserves backend order');
    await p.reply(method, {applied: true, persisted: true}, [!initial]);
    assert.equal(p.el(id).checked, initial, 'older acknowledgement must not repaint newer edit');
    if (id === 'show-eve-tools') assert.deepEqual(p.gates, [false]);
    await p.reply(method, {applied: false, persisted: false}, [initial]);
    assert.equal(p.el(id).checked, !initial);
  });
}

test('reopen consequence reports acknowledgements, never drafts or refused preferences', async () => {
  const p = page();
  await p.toggle('restore-preview-positions', false);
  assert.deepEqual(p.restoreEvents, []);
  await p.reply('set_restore_preview_positions', accepted);
  assert.deepEqual(p.restoreEvents, [false]);
  await p.toggle('restore-preview-positions', true);
  await p.reply('set_restore_preview_positions', refused);
  assert.deepEqual(p.restoreEvents, [false]);
});

test('restore-preview refusal is not an applied-but-unsaved result', async () => {
  const p = page();
  await p.toggle('restore-preview-positions', false);
  await p.reply('set_restore_preview_positions', {applied: false, persisted: false});
  assert.equal(p.el('restore-preview-positions').checked, true);
  assert.doesNotMatch(p.el('restore-preview-positions-status').textContent, /for this session/);
  assert.ok(p.el('restore-preview-positions-status').textContent);
});

for (const outcome of [accepted, refused, null]) {
  test('older category reply preserves newer edit: ' + JSON.stringify(outcome), async () => {
    const p = page();
    await p.submit('f-category', '22');
    p.edit('f-category', '23');
    p.fire('f-category', 'blur');
    const guidance = p.el('category-draft').textContent;
    assert.match(guidance, /Enter/);
    await p.reply('set_category', outcome);
    assert.equal(p.el('f-category').value, '23');
    assert.equal(p.el('category-draft').textContent, guidance);
    assert.equal(p.el('category-draft').hidden, false);
    await p.submit('f-category', 'invalid');
    await p.reply('set_category', refused);
    assert.equal(p.el('f-category').value, outcome && outcome.applied ? '22' : '20');
  });
}

test('queued requests retain submission order and never regress the baseline', async () => {
  const p = page();
  await p.submit('f-category', '22');
  await p.submit('f-category', '23');
  assert.equal(p.calls.filter(call => call.method === 'set_category').length, 1);
  await p.reply('set_category', accepted, ['22']);
  assert.equal(p.el('f-category').value, '23');
  await p.reply('set_category', accepted, ['23']);
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', refused);
  assert.equal(p.el('f-category').value, '23');
});

test('separate fields remain independent and an old reply cannot clear a newer error', async () => {
  const p = page();
  await p.submit('f-privacy', 'private');
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', refused);
  await p.reply('set_privacy', accepted);
  assert.match(p.el('msg-uploads').className, /err/);
});

for (const privacyFirst of [false, true]) {
  test('an unrelated privacy success cannot hide a category refusal, privacyFirst=' + privacyFirst, async () => {
    const p = page();
    await p.submit('f-category', 'invalid');
    await p.submit('f-privacy', 'private');
    const error = Object.assign({}, refused, {error: 'Category must be a number.'});
    if (privacyFirst) await p.reply('set_privacy', accepted);
    await p.reply('set_category', error);
    if (!privacyFirst) await p.reply('set_privacy', accepted);
    assert.equal(p.el('f-category').value, '20');
    assert.match(p.el('msg-uploads').textContent, /Category must be a number/);
    await p.submit('f-category', '22');
    await p.reply('set_category', accepted);
    assert.equal(p.el('msg-uploads').textContent, '');
  });
}

test('retrying one field clears only its own shared-slot error', async () => {
  const p = page();
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', Object.assign({}, refused, {error: 'Category rejected.'}));
  await p.submit('f-privacy', 'private');
  await p.reply('set_privacy', Object.assign({}, refused, {error: 'Privacy not saved.'}));
  assert.match(p.el('msg-uploads').textContent, /Category rejected/);
  assert.match(p.el('msg-uploads').textContent, /Privacy not saved/);
  await p.submit('f-category', '22');
  await p.reply('set_category', accepted);
  assert.doesNotMatch(p.el('msg-uploads').textContent, /Category rejected/);
  assert.match(p.el('msg-uploads').textContent, /Privacy not saved/);
});

test('accepted retry clears its obsolete refusal while preserving a newer draft', async () => {
  const p = page();
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', refused);
  await p.submit('f-category', '22');
  p.edit('f-category', '23');
  await p.reply('set_category', accepted);
  assert.equal(p.el('f-category').value, '23');
  assert.equal(p.el('msg-uploads').textContent, '');
  assert.equal(p.el('msg-uploads').hidden, true);
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', refused);
  assert.equal(p.el('f-category').value, '22');
});

test('accepted retry with a newer draft removes only its own displayed refusal', async () => {
  const p = page();
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', Object.assign({}, refused, {error: 'Category rejected.'}));
  await p.submit('f-privacy', 'private');
  await p.reply('set_privacy', Object.assign({}, refused, {error: 'Privacy not saved.'}));
  await p.submit('f-category', '22');
  p.edit('f-category', '23');
  p.fire('f-category', 'blur');
  const guidance = p.el('category-draft').textContent;
  assert.match(guidance, /Enter/);
  await p.reply('set_category', accepted);
  assert.equal(p.el('f-category').value, '23');
  assert.equal(p.el('category-draft').textContent, guidance);
  assert.equal(p.el('category-draft').hidden, false);
  assert.doesNotMatch(p.el('msg-uploads').textContent, /Category rejected/);
  assert.match(p.el('msg-uploads').textContent, /Privacy not saved/);
  assert.match(p.el('msg-uploads').className, /err/);
});

for (const [id, method, slot, value] of [
  ['f-recdir', 'set_folder', 'msg-recdir', 'C:\\accepted'],
  ['f-webhook', 'set_discord_webhook', 'msg-discord', 'https://discord.com/api/webhooks/1/a']
]) {
  test(id + ' accepted retry preserves a newer draft warning instead of repainting refusals', async () => {
    const p = page();
    await p.submit(id, 'invalid', 'keydown');
    await p.reply(method, refused);
    await p.submit(id, value, 'keydown');
    p.edit(id, 'newer draft');
    p.fire(id, 'blur');
    const warning = p.el(slot).textContent;
    assert.match(warning, /Press Enter/);
    await p.reply(method, accepted);
    assert.equal(p.el(id).value, 'newer draft');
    assert.equal(p.el(slot).textContent, warning);
    assert.match(p.el(slot).className, /warn/);
  });
}

test('folder acknowledgement does not label a later draft as saved', async () => {
  const p = page();
  await p.submit('f-recdir', 'C:\\accepted', 'keydown');
  p.edit('f-recdir', 'C:\\draft');
  p.fire('f-recdir', 'blur');
  await p.reply('set_folder', accepted);
  assert.equal(p.el('f-recdir').value, 'C:\\draft');
  assert.match(p.el('msg-recdir').textContent, /Press Enter/);
  await p.submit('f-recdir', 'missing', 'keydown');
  await p.reply('set_folder', refused);
  assert.equal(p.el('f-recdir').value, 'C:\\accepted');
});

test('webhook acknowledgement captures the trimmed submission, not the later input', async () => {
  const p = page();
  const url = 'https://discord.com/api/webhooks/1/accepted';
  p.focus('f-webhook');
  await p.submit('f-webhook', ' ' + url + ' ', 'keydown');
  p.edit('f-webhook', 'later draft');
  await p.reply('set_discord_webhook', Object.assign({}, accepted, {webhook_status: 'accepted hook'}));
  assert.equal(p.el('f-webhook').value, 'later draft');
  p.fire('f-webhook', 'blur');
  assert.match(p.el('msg-discord').textContent, /Press Enter/);
  assert.equal(p.el('webhook-status').textContent, 'accepted hook');
  assert.equal(p.el('btn-webhook-remove').disabled, false);
  await p.submit('f-webhook', 'invalid', 'keydown');
  await p.reply('set_discord_webhook', refused);
  assert.equal(p.el('f-webhook').value, url);
});

test('webhook set and clear are one queue, and clear cannot erase a newer draft', async () => {
  const p = page();
  await p.submit('f-webhook', 'https://discord.com/api/webhooks/1/a', 'keydown');
  await p.reply('set_discord_webhook', Object.assign({}, accepted, {webhook_status: 'hook A'}));
  await p.submit('f-webhook', 'https://discord.com/api/webhooks/2/b', 'keydown');
  p.fire('btn-webhook-remove', 'click');
  await turn();
  assert.equal(p.calls.some(call => call.method === 'clear_discord_webhook'), false);
  await p.reply('set_discord_webhook', Object.assign({}, accepted, {webhook_status: 'hook B'}));
  p.edit('f-webhook', 'new draft');
  await p.reply('clear_discord_webhook', Object.assign({}, accepted, {webhook_status: 'not configured'}));
  assert.equal(p.el('f-webhook').value, 'new draft');
  assert.equal(p.el('btn-webhook-remove').disabled, true);
  await p.submit('f-webhook', 'invalid', 'keydown');
  await p.reply('set_discord_webhook', refused);
  assert.equal(p.el('f-webhook').value, '');
});

test('an applied session-only response advances the baseline but warns', async () => {
  const p = page();
  await p.submit('f-category', '22');
  await p.reply('set_category', {applied: true, persisted: false, error: null});
  assert.match(p.el('msg-uploads').className, /warn/);
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', refused);
  assert.equal(p.el('f-category').value, '22');
});

test('hydration preserves a focused draft but refusal restores the baseline', async () => {
  const p = page(false);
  p.focus('f-category');
  p.edit('f-category', 'draft');
  p.hydrate();
  assert.equal(p.el('f-category').value, 'draft');
  await p.submit('f-category', 'invalid');
  await p.reply('set_category', refused);
  assert.equal(p.el('f-category').value, '20');
});

test('editing away and back still protects a newer unsubmitted category draft', async () => {
  const p = page();
  await p.submit('f-category', '22');
  p.edit('f-category', '23');
  p.edit('f-category', '22');
  p.fire('f-category', 'blur');
  const guidance = p.el('category-draft').textContent;
  assert.match(guidance, /Enter/);
  await p.reply('set_category', refused);
  assert.equal(p.el('f-category').value, '22');
  assert.equal(p.el('category-draft').textContent, guidance);
});

test('a trimmed accepted webhook does not warn on blur', async () => {
  const p = page();
  p.focus('f-webhook');
  await p.submit('f-webhook', ' https://discord.com/api/webhooks/1/a ', 'keydown');
  await p.reply('set_discord_webhook', Object.assign({}, accepted, {webhook_status: 'hook A'}));
  p.fire('f-webhook', 'blur');
  assert.doesNotMatch(p.el('msg-discord').textContent, /Press Enter/);
});

test('an empty accepted gamelogs folder remains the refusal baseline', async () => {
  const p = page();
  await p.submit('f-gamelogs', '', 'keydown');
  await p.reply('set_folder', accepted, ['gamelogs', '']);
  await p.submit('f-gamelogs', 'missing', 'keydown');
  await p.reply('set_folder', refused);
  assert.equal(p.el('f-gamelogs').value, '');
});

test('hydration during a pending write cannot overwrite that field or its accepted baseline', async () => {
  const p = page();
  await p.submit('f-category', '22');
  await p.reply('set_category', accepted);
  await p.submit('f-category', 'invalid');
  p.hydrate();
  assert.equal(p.el('f-category').value, 'invalid');
  await p.reply('set_category', refused);
  assert.equal(p.el('f-category').value, '22');
});

test('hydration during pending checkbox/radio/webhook writes preserves their presentation', async () => {
  const p = page();
  await p.toggle('show-eve-tools', false);
  await p.toggle('start-on-login', true);
  await p.toggle('restore-preview-positions', false);
  await p.choose('popup');
  await p.submit('f-webhook', 'https://discord.com/api/webhooks/1/a', 'keydown');
  await p.reply('set_discord_webhook', Object.assign({}, accepted, {webhook_status: 'hook A'}));
  await p.submit('f-webhook', 'https://discord.com/api/webhooks/2/b', 'keydown');
  p.hydrate();
  assert.equal(p.el('show-eve-tools').checked, false);
  assert.equal(p.el('start-on-login').checked, true);
  assert.equal(p.el('restore-preview-positions').checked, false);
  assert.equal(p.picked(), 'popup');
  assert.equal(p.el('f-webhook').value, 'https://discord.com/api/webhooks/2/b');
  assert.equal(p.el('webhook-status').textContent, 'hook A');
  await p.reply('set_discord_webhook', refused);
  assert.equal(p.el('f-webhook').value, 'https://discord.com/api/webhooks/1/a');
});

test('no scalar or restore-preview commit before hydration', async () => {
  const p = page(false);
  await p.submit('f-category', '22');
  await p.submit('f-recdir', 'C:\\new', 'keydown');
  await p.submit('f-webhook', 'https://discord.com/api/webhooks/1/a', 'keydown');
  await p.toggle('show-eve-tools', false);
  await p.toggle('start-on-login', true);
  await p.toggle('restore-preview-positions', false);
  await p.choose('popup');
  assert.deepEqual(p.calls, []);
});

(async function () {
  let failures = 0;
  for (const {name, run} of tests) {
    try {
      await run();
      console.log('PASS ' + name);
    } catch (error) {
      failures += 1;
      console.error('FAIL ' + name + '\n' + error.stack);
    }
  }
  console.log(`${tests.length - failures}/${tests.length} settings runtime tests passed`);
  if (failures) process.exitCode = 1;
}());
