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
const tests = [];
function test(name, run) { tests.push({name, run}); }
function turn() { return new Promise(resolve => setImmediate(resolve)); }
const accepted = {applied: true, persisted: true, error: null};
const refused = {applied: false, persisted: false, error: 'Not accepted'};

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
}

function page(hydrate = true) {
  const ids = [
    'f-privacy', 'f-category', 'f-recdir', 'f-gamelogs', 'f-webhook',
    'show-eve-tools', 'start-on-login', 'webhook-status', 'btn-webhook-show',
    'btn-webhook-remove', 'detect-note', 'gamelogs-note', 'about-version',
    'msg-general', 'msg-about', 'msg-uploads', 'msg-notify', 'msg-recdir',
    'msg-gamelogs', 'msg-discord', 'btn-auth', 'tos-link', 'btn-update-check',
    'btn-update-download', 'btn-update-install', 'restore-preview-positions',
    'restore-preview-positions-status'
  ];
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
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
  vm.runInNewContext(source, {window: {WM}, WM, document, Promise}, {
    filename: 'wingman/web/settings.js'
  });
  const api = {
    el: id => elements[id], calls, gates, notify,
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
    async submit(id, value, event = 'change') {
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
    await p.reply('set_category', outcome);
    assert.equal(p.el('f-category').value, '23');
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
  await p.reply('set_category', refused);
  assert.equal(p.el('f-category').value, '22');
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
