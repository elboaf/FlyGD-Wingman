#!/usr/bin/env node
'use strict';

// Production ES5, controlled DOM/bridge boundaries. No network, storage or render.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '../wingman/web');
const tests = [];
function test(name, run) { tests.push({name, run}); }
function turn() { return new Promise(resolve => setImmediate(resolve)); }
function state(overrides = {}) {
  return Object.assign({enabled: false, base_url: 'https://wanderer.example/prefix',
    map_identifier: 'home', revision: 1, credential_present: false, credential_error: false, persistence_error: false,
    generation: 1, automatic_ready: false, status: 'off', error_code: null, paused: false,
    in_flight: false, test_pending: false, test_in_flight: false, test_result: null,
    last_success_monotonic: null, next_request_monotonic: null,
    previewed: 0, matched: 0, available: 0, stale: 0,
    previews_enabled: true, host_available: true,
    status_text: 'Wanderer names are off.', test_result_text: ''}, overrides);
}
function result(overrides = {}, error = null) {
  const p = state(overrides);
  const acknowledged = {};
  for (const key of ['enabled', 'base_url', 'map_identifier', 'revision',
    'credential_present', 'credential_error', 'persistence_error']) acknowledged[key] = p[key];
  return {applied: !error, persisted: !error, error, acknowledged,
    test_accepted: !error, test_error: null, test_generation: p.generation};
}
class Element {
  constructor(id) {
    Object.assign(this, {id, value: '', checked: false, disabled: false, hidden: false,
      textContent: '', className: '', listeners: {}, attributes: {}});
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatchEvent(event) {
    event.target ||= this;
    event.preventDefault ||= function () {};
    for (const fn of this.listeners[event.type] || []) fn(event);
  }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  removeAttribute(key) { delete this.attributes[key]; }
}
function page() {
  // Real markup IDs: a misspelled production lookup must fail, not fabricate a node.
  const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
  const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)]
    .map(match => [match[1], new Element(match[1])]));
  const document = new Element('document');
  const calls = [], confirmations = [], handlers = {}, logs = [];
  const WM = {
    el: id => elements[id] || null,
    setEnabled: (id, enabled) => { (typeof id === 'string' ? elements[id] : id).disabled = !enabled; },
    handle: (name, handler) => {
      assert.equal(name, 'onWandererState');
      assert.equal(handlers[name], undefined, 'one handler owner');
      handlers[name] = handler;
    },
    send: (method, ...args) => new Promise(resolve => calls.push({method, args, resolve})),
    confirm: (...args) => new Promise(resolve => confirmations.push({args, resolve}))
  };
  const sourcePath = path.join(web, 'wanderer.js');
  assert.ok(fs.existsSync(sourcePath), 'Wanderer Settings owner is implemented');
  vm.runInNewContext(fs.readFileSync(sourcePath, 'utf8'), {
    window: {WM}, WM, document, Promise,
    console: {log: (...args) => logs.push(args), error: (...args) => logs.push(args)}
  }, {filename: 'wanderer.js'});
  return {
    calls, confirmations, elements, logs,
    el: id => elements['wanderer-' + id],
    enter(section = 'previews') { document.dispatchEvent({type: 'wm:section', detail: section}); },
    push(payload) { handlers.onWandererState(payload); },
    fire(id, type, extra = {}) { this.el(id).dispatchEvent(Object.assign({type}, extra)); },
    edit(id, value) { this.el(id).value = value; this.fire(id, 'input'); },
    async apply(id, value) { if (value !== undefined) this.edit(id, value); this.fire(id, 'keydown', {key: 'Enter'}); await turn(); },
    async click(id) { this.fire(id, 'click'); await turn(); },
    async toggle(value) { this.el('enabled').checked = value; this.fire('enabled', 'change'); await turn(); },
    async reply(method, response, args) {
      const index = calls.findIndex(call => call.method === method);
      assert.notEqual(index, -1, 'pending call ' + method);
      const call = calls.splice(index, 1)[0];
      if (args) assert.deepEqual(call.args, args);
      call.resolve(response); await turn();
    },
    async hydrate(overrides = {}) { this.enter(); await this.reply('wanderer_state', state(overrides)); }
  };
}

test('hydrates only on Previews entry and refuses early actions', async () => {
  const p = page();
  p.enter('fleet');
  assert.equal(p.calls.length, 0);
  for (const id of ['enabled', 'url', 'map', 'token']) assert.equal(p.el(id).disabled, true);
  await p.toggle(true); await p.apply('url', 'https://early.example');
  await p.click('test'); await p.click('remove');
  assert.equal(p.calls.length, 0); assert.equal(p.confirmations.length, 0);
  await p.hydrate();
  // Synthetic pre-hydration input still belongs to the user, not the late read.
  assert.equal(p.el('url').value, 'https://early.example');
  assert.equal(p.el('map').value, 'home');
  for (const id of ['enabled', 'url', 'map', 'token']) assert.equal(p.el(id).disabled, false);
});

test('new push fences initial stale hydration without losing pre-read draft', async () => {
  const p = page(); p.enter();
  p.edit('map', 'draft');
  p.push(state({revision: 3, generation: 3, base_url: 'https://new.example'}));
  assert.equal(p.el('url').value, '', 'a push must not hydrate inputs');
  await p.reply('wanderer_state', state());
  assert.equal(p.el('url').value, 'https://new.example');
  assert.equal(p.el('map').value, 'draft');
});

test('failed hydration is retryable and later hydration never repaints drafts', async () => {
  const p = page(); p.enter(); await p.reply('wanderer_state', null);
  assert.equal(p.el('url').disabled, true);
  assert.match(p.el('health').textContent, /unavailable|reach|load/i);
  await p.hydrate(); p.edit('map', 'draft'); p.enter();
  p.push(state({revision: 3, generation: 3, enabled: true, credential_present: true, status: 'connecting'}));
  await p.reply('wanderer_state', state());
  assert.equal(p.el('map').value, 'draft');
  assert.match(p.el('health').textContent, /Connecting/);
});

for (const [field, key, value] of [
  ['url', 'base_url', 'https://accepted.example'],
  ['map', 'map_identifier', 'accepted']
]) {
  const method = 'test_wanderer_connection';
  test(field + ' refusal restores last acknowledged canonical submission', async () => {
    const p = page(); await p.hydrate();
    await p.apply(field, ' ' + value + ' ');
    await p.reply(method, Object.assign(result({[key]: value, revision: 2}), {test_accepted: false, test_error: 'Saved; Test unavailable.'}));
    assert.equal(p.el(field).value, value);
    await p.apply(field, 'invalid');
    await p.reply(method, result({[key]: value, revision: 2}, 'Could not save.'));
    assert.equal(p.el(field).value, value);
    assert.match(p.el('connection-error').textContent, /Could not save/);
    await p.apply(field, value); p.edit(field, 'newer draft');
    await p.reply(method, result({[key]: value, revision: 2}));
    assert.equal(p.el(field).value, 'newer draft');
    assert.equal(p.el('connection-error').textContent, '');
    assert.match(p.el(field + '-draft').textContent, /Test|Enter/);
  });
  test(field + ' pending form write never clobbers a newer field draft on refusal', async () => {
    const p = page(); await p.hydrate();
    await p.apply(field, 'first'); p.edit(field, 'second');
    await p.click('test');
    assert.equal(p.calls.length, 1, 'one form mutation at a time');
    await p.reply(method, result({}, 'Old refusal'));
    assert.equal(p.el(field).value, 'second');
    await p.apply(field, 'accepted');
    p.edit(field, 'third draft');
    await p.reply(method, Object.assign(result({[key]: 'accepted', revision: 2}), {test_accepted: false}));
    assert.equal(p.el(field).value, 'third draft');
    await p.apply(field, 'invalid');
    await p.reply(method, null);
    assert.equal(p.el(field).value, 'accepted');
  });
}

test('checkbox rapid writes serialize and use acknowledgement baseline', async () => {
  const p = page(); await p.hydrate();
  await p.toggle(true); await p.toggle(false);
  assert.equal(p.calls.length, 1);
  await p.reply('set_wanderer_enabled', result({enabled: true, revision: 2}), [true]);
  assert.equal(p.el('enabled').checked, false);
  await p.reply('set_wanderer_enabled', result({enabled: true, revision: 2}, 'Not saved'), [false]);
  assert.equal(p.el('enabled').checked, true);
});

test('concurrent field replies and retries keep independent errors and baselines', async () => {
  const p = page(); await p.hydrate();
  await p.apply('url', 'bad'); await p.toggle(true);
  assert.equal(p.calls.length, 2, 'enabled is independent of the connection lane');
  await p.reply('set_wanderer_enabled', result({}, 'Enable refused'));
  await p.reply('test_wanderer_connection', result({}, 'Connection refused'));
  await p.apply('url', 'https://ok.example');
  await p.reply('test_wanderer_connection', result({base_url: 'https://ok.example', revision: 2}));
  assert.equal(p.el('connection-error').textContent, '');
  assert.equal(p.el('enabled-error').textContent, 'Enable refused');
});

test('pushes never touch inputs; stale mutation cannot rewind safe acknowledgement', async () => {
  const p = page(); await p.hydrate();
  await p.apply('url', 'https://accepted.example');
  p.edit('map', 'unsent');
  p.push(state({revision: 3, generation: 3, base_url: 'https://latest.example',
    credential_present: true}));
  assert.equal(p.el('url').value, 'https://accepted.example');
  assert.equal(p.el('map').value, 'unsent');
  await p.reply('test_wanderer_connection', result({base_url: 'https://accepted.example', revision: 2}));
  assert.equal(p.el('url').value, 'https://latest.example');
  assert.match(p.el('credential').textContent, /stored|Stored/);
  p.push(state({revision: 1, generation: 1}));
  assert.match(p.el('credential').textContent, /stored|Stored/);
});

test('old worker generation and delayed same-revision read cannot rewind health', async () => {
  const p = page(); await p.hydrate({enabled: true}); p.enter();
  p.push(state({enabled: true, credential_present: true, generation: 5, status: 'connected', previewed: 3, matched: 2, available: 1}));
  await p.reply('wanderer_state', state({enabled: true, generation: 5, status: 'connecting'}));
  p.push(state({enabled: true, generation: 4, status: 'connecting'}));
  assert.match(p.el('health').textContent, /Connected/);
  assert.match(p.el('coverage').textContent, /1 of 3/);
});

test('a new config revision cannot reuse old worker-generation coverage', async () => {
  const p = page(); await p.hydrate({enabled: true, credential_present: true, status: 'connected',
    previewed: 3, matched: 2, available: 2});
  p.push(state({enabled: true, credential_present: true, revision: 2, generation: 1,
    map_identifier: 'next', status: 'connected', previewed: 3, matched: 2, available: 2}));
  assert.doesNotMatch(p.el('health').textContent, /Connected/);
  assert.equal(p.el('coverage').textContent, '');
  p.push(state({enabled: true, credential_present: true, revision: 2, generation: 2,
    map_identifier: 'next', status: 'connecting', previewed: 3}));
  assert.match(p.el('health').textContent, /Connecting/);
  assert.match(p.el('coverage').textContent, /0 of 3/);
});

test('text commits as one form on Test, never blur or change', async () => {
  const p = page(); await p.hydrate();
  for (const field of ['url', 'map', 'token']) {
    p.edit(field, 'draft'); p.fire(field, 'blur'); p.fire(field, 'change');
  }
  await turn(); assert.equal(p.calls.length, 0);
  await p.click('test');
  assert.equal(p.calls[0].method, 'test_wanderer_connection');
  assert.deepEqual(p.calls[0].args, ['draft', 'draft', 'draft']);
});

for (const order of [['token', 'map', 'url'], ['url', 'token', 'map'], ['map', 'url', 'token']]) {
  test('first setup accepts reordered fields and Enter from ' + order[2], async () => {
    const p = page(); await p.hydrate({base_url: '', map_identifier: ''});
    const values = {url: 'https://new.example', map: 'next', token: 'ephemeral-input'};
    for (const field of order) p.edit(field, values[field]);
    await p.apply(order[2]);
    assert.deepEqual(p.calls[0].args, [values.url, values.map, values.token]);
    assert.equal(p.el('token').value, '');
    assert.equal(p.el('enabled').checked, false);
    for (const field of order) assert.equal(p.el(field).disabled, false);
  });
}

test('partial setup still allows Test to explain refusal and owns only submitted fields', async () => {
  const p = page(); await p.hydrate({base_url: '', map_identifier: ''});
  p.edit('token', 'ephemeral-input'); await p.click('test');
  assert.deepEqual(p.calls[0].args, ['', '', 'ephemeral-input']);
  p.edit('map', 'newer-map');
  await p.reply('test_wanderer_connection', result({base_url: '', map_identifier: ''}, 'Enter a valid URL, map and token.'));
  assert.equal(p.el('map').value, 'newer-map');
  assert.match(p.el('connection-error').textContent, /URL/);
});

test('token clears on submission, never on response over a newer token draft', async () => {
  const p = page(); await p.hydrate();
  await p.apply('token', 'ephemeral-input');
  assert.equal(p.el('token').value, '');
  assert.deepEqual(p.calls[0].args, ['https://wanderer.example/prefix', 'home', 'ephemeral-input']);
  p.edit('token', 'newer-ephemeral-input');
  await p.reply('test_wanderer_connection', result({}, 'Could not protect the token.'));
  assert.equal(p.el('token').value, 'newer-ephemeral-input');
  p.push(state({revision: 2, credential_present: true}));
  assert.equal(p.el('token').value, 'newer-ephemeral-input');
  assert.equal(p.logs.length, 0);
  for (const el of Object.values(p.elements)) {
    assert.doesNotMatch(el.textContent + JSON.stringify(el.attributes), /ephemeral-input/);
  }
});

test('captured token is sent only with submitted fields despite newer health and typing', async () => {
  const p = page(); await p.hydrate();
  p.edit('token', 'ephemeral-input'); p.fire('token', 'keydown', {key: 'Enter'});
  p.push(state({revision: 2, generation: 2, map_identifier: 'next'}));
  p.edit('map', 'later-map');
  await turn();
  assert.deepEqual(p.calls[0].args, ['https://wanderer.example/prefix', 'home', 'ephemeral-input']);
  assert.equal(p.el('token').value, '');
  await p.reply('test_wanderer_connection', result({revision: 3, generation: 3, credential_present: true}));
  assert.equal(p.el('map').value, 'later-map');
});

test('blank token reuse is decided against submitted normalized binding by the controller', async () => {
  const p = page(); await p.hydrate({credential_present: true});
  await p.apply('url', ' HTTPS://WANDERER.example:443/prefix/ ');
  assert.deepEqual(p.calls[0].args, [' HTTPS://WANDERER.example:443/prefix/ ', 'home', '']);
  await p.reply('test_wanderer_connection', Object.assign(result({credential_present: true}), {test_accepted: false}));
  assert.equal(p.el('url').value, 'https://wanderer.example/prefix');
  await p.apply('map', 'new-map');
  assert.deepEqual(p.calls[0].args, ['https://wanderer.example/prefix', 'new-map', '']);
  await p.reply('test_wanderer_connection', result({credential_present: true}, 'Enter a token for this URL and map.'));
  assert.equal(p.el('map').value, 'home');
  assert.match(p.el('connection-error').textContent, /token/);
});

test('Test admission is separate from auto health, waits for push and never enables', async () => {
  const p = page(); await p.hydrate({credential_present: true});
  await p.click('test'); assert.equal(p.calls[0].method, 'test_wanderer_connection');
  assert.equal(p.el('test').disabled, true);
  await p.reply('test_wanderer_connection', result({credential_present: true}));
  assert.match(p.el('test-status').textContent, /queued|Waiting/i);
  p.push(state({credential_present: true, test_pending: true}));
  assert.match(p.el('test-status').textContent, /queued|Waiting/i);
  p.push(state({credential_present: true, test_in_flight: true}));
  assert.match(p.el('test-status').textContent, /Testing/);
  p.push(state({credential_present: true, test_result: 'success', test_result_text: 'Connected to Wanderer.'}));
  assert.match(p.el('test-status').textContent, /Connected/);
  assert.match(p.el('health').textContent, /^Off/);
  p.push(state({credential_present: true, status: 'error', error_code: 'timeout',
    test_result: 'success', test_result_text: 'Connected to Wanderer.'}));
  assert.match(p.el('test-status').textContent, /Connected/);
  assert.equal(p.el('enabled').checked, false); assert.equal(p.calls.length, 0);
});

test('Test completion push before admission response does not return to pending', async () => {
  const p = page(); await p.hydrate({credential_present: true}); await p.click('test');
  p.push(state({credential_present: true, test_in_flight: true}));
  p.push(state({credential_present: true, test_result: 'success', test_result_text: 'Connected to Wanderer.'}));
  await p.reply('test_wanderer_connection', result({credential_present: true}));
  assert.match(p.el('test-status').textContent, /Connected/);
  assert.equal(p.el('test').disabled, false);
});

for (const stage of ['unobserved', 'queued', 'inflight']) {
  for (const admission of ['before', 'after']) {
    for (const delivery of ['push', 'read']) {
      test(`Test ${stage} generation cancellation via ${delivery}, admission ${admission}`, async () => {
        const p = page(); await p.hydrate({credential_present: true, generation: 4});
        await p.click('test');
        if (admission === 'before') await p.reply('test_wanderer_connection', result({credential_present: true}));
        if (stage !== 'unobserved') p.push(state({credential_present: true, generation: 4,
          test_pending: stage === 'queued', test_in_flight: stage === 'inflight'}));
        if (stage === 'inflight') {
          p.push(state({credential_present: true, generation: 5, host_available: false, test_in_flight: true}));
          assert.equal(p.el('test').disabled, true, 'retired HTTP owner still occupies the lane');
        }
        const canceled = state({credential_present: true, generation: 5, host_available: false});
        if (delivery === 'push') p.push(canceled);
        else { p.enter(); await p.reply('wanderer_state', canceled); }
        assert.doesNotMatch(p.el('test-status').textContent, /queued|Testing/i);
        assert.match(p.el('test-error').textContent, /changed|unknown|interrupt/i);
        if (admission === 'after') await p.reply('test_wanderer_connection', result({credential_present: true}));
        assert.equal(p.el('test').disabled, false);
        assert.match(p.el('test-error').textContent, /changed|unknown|interrupt/i);
        p.push(state({credential_present: true, generation: 4, test_result: 'success', test_result_text: 'Connected to Wanderer.'}));
        p.enter(); await p.reply('wanderer_state', canceled);
        assert.equal(p.el('test').disabled, false, 'section re-entry cannot resurrect canceled ownership');
        assert.doesNotMatch(p.el('test-status').textContent, /queued|Connected/i);
        await p.click('test');
        await p.reply('test_wanderer_connection', result({credential_present: true}));
        p.push(state({credential_present: true, generation: 5, test_result: 'success', test_result_text: 'Connected to Wanderer.'}));
        assert.match(p.el('test-status').textContent, /Connected/);
        assert.equal(p.el('enabled').checked, false);
      });
    }
  }
}

test('Test admitted in the newer generation recovers uncertain ownership before late admission reply', async () => {
  const p = page(); await p.hydrate({credential_present: true, generation: 4}); await p.click('test');
  p.push(state({credential_present: true, generation: 5}));
  assert.match(p.el('test-error').textContent, /changed|unknown|interrupt/i);
  p.push(state({credential_present: true, generation: 5, test_pending: true}));
  assert.equal(p.el('test-error').textContent, '');
  assert.match(p.el('test-status').textContent, /queued/i);
  p.push(state({credential_present: true, generation: 5, test_result: 'success', test_result_text: 'Connected to Wanderer.'}));
  await p.reply('test_wanderer_connection', result({credential_present: true}));
  assert.match(p.el('test-status').textContent, /Connected/);
  assert.equal(p.el('test').disabled, false);
});

test('delayed post-admission read cannot replace generation cancellation with old Test success', async () => {
  const previous = {credential_present: true, generation: 4, test_result: 'success', test_result_text: 'Connected to Wanderer.'};
  const p = page(); await p.hydrate(previous); await p.click('test');
  await p.reply('test_wanderer_connection', result({credential_present: true}));
  p.push(state({credential_present: true, generation: 5}));
  await p.reply('wanderer_state', state(previous));
  assert.equal(p.el('test').disabled, false);
  assert.doesNotMatch(p.el('test-status').textContent, /queued|Connected/);
  assert.match(p.el('test-error').textContent, /changed|unknown|interrupt/i);
});

test('saved configuration and refused Test admission remain distinct from independent errors', async () => {
  const p = page(); await p.hydrate({credential_present: true});
  await p.toggle(true);
  await p.reply('set_wanderer_enabled', result({credential_present: true}, 'Enable refused'));
  p.edit('map', ' next '); p.edit('token', 'ephemeral-input'); await p.click('test');
  await p.reply('test_wanderer_connection', Object.assign(result({credential_present: true, map_identifier: 'next', revision: 2, generation: 2}),
    {test_accepted: false, test_error: 'Connection saved, but Test could not start.'}));
  assert.equal(p.el('map').value, 'next');
  assert.equal(p.el('connection-error').textContent, '');
  assert.match(p.el('test-error').textContent, /saved/);
  assert.match(p.el('enabled-error').textContent, /Enable refused/);
  assert.equal(p.el('test').disabled, false);
});

test('Remove is page-confirmed, clears connection and preserves newer field drafts', async () => {
  const p = page(); await p.hydrate({credential_present: true});
  await p.click('remove'); assert.equal(p.calls.length, 0);
  assert.match(p.confirmations[0].args.join(' '), /token/i);
  p.confirmations.shift().resolve(false); await turn(); assert.equal(p.calls.length, 0);
  await p.click('remove'); p.confirmations.shift().resolve(true); await turn();
  assert.equal(p.calls[0].method, 'remove_wanderer_connection');
  assert.deepEqual(p.calls[0].args, [1]);
  p.edit('token', 'newer-ephemeral-input'); p.edit('map', 'newer-map');
  await p.reply('remove_wanderer_connection', result({revision: 2, base_url: '', map_identifier: ''}));
  assert.equal(p.el('url').value, '');
  assert.equal(p.el('map').value, 'newer-map');
  assert.equal(p.el('token').value, 'newer-ephemeral-input');
  assert.equal(p.el('enabled').checked, false);
});

test('a connection edit or section exit invalidates an open Remove confirmation', async () => {
  for (const invalidate of [p => p.edit('map', 'draft'), p => p.enter('general'),
    p => p.push(state({revision: 2, generation: 2}))]) {
    const p = page(); await p.hydrate({credential_present: true}); await p.click('remove');
    invalidate(p); p.confirmations.shift().resolve(true); await turn();
    assert.equal(p.calls.length, 0);
  }
});

for (const [overrides, expected] of [
  [{enabled: false}, /^Off/],
  [{enabled: true, base_url: ''}, /Setup/],
  [{enabled: true, credential_present: true, status: 'connecting'}, /Connecting/],
  [{enabled: true, credential_present: true, status: 'connected', previewed: 3, matched: 2, available: 2}, /Connected/],
  [{enabled: true, credential_present: true, status: 'connected', previewed: 3}, /No tracked/],
  [{enabled: true, credential_present: true, status: 'error', error_code: 'invalid_token', paused: true}, /token|auth/i],
  [{enabled: true, credential_present: true, status: 'error', error_code: 'wrong_map', paused: true}, /map/i],
  [{enabled: true, credential_present: true, status: 'error', error_code: 'disabled', paused: true}, /API.*disabled/i],
  [{enabled: true, credential_present: true, status: 'error', error_code: 'timeout'}, /Retrying/],
  [{enabled: true, credential_present: true, status: 'stale', stale: 2, previewed: 2, matched: 2}, /Stale/],
  [{enabled: true, credential_present: true, previews_enabled: false}, /previews/i],
  [{enabled: true, credential_present: true, host_available: false}, /previews/i]
]) {
  test('health ' + JSON.stringify(overrides), async () => {
    const p = page(); await p.hydrate(overrides);
    assert.match(p.el('health').textContent, expected);
    assert.equal(p.el('url').disabled, false); assert.equal(p.el('token').disabled, false);
  });
}

test('coverage uses only current-session counters, including partial stale coverage', async () => {
  const p = page(); await p.hydrate({enabled: true, credential_present: true, status: 'connected',
    previewed: 4, matched: 3, available: 1, stale: 2});
  assert.match(p.el('coverage').textContent, /1 of 4/);
  assert.match(p.el('coverage').textContent, /3 of 4/);
  assert.match(p.el('coverage').textContent, /2 stale/);
  p.push(state({enabled: true, credential_present: true, status: 'connected', generation: 2}));
  assert.match(p.el('coverage').textContent, /No named previews/);
});

test('entering the connection card disarms real preview keybind capture before typing', async () => {
  const source = fs.readFileSync(path.join(web, 'previews.js'), 'utf8');
  // Exercise the existing capture owner plus the new card ingress, not its roster renderer.
  const capture = source.slice(source.indexOf('  function beginCapture('),
    source.indexOf('  // Every push- or fetch-driven redraw'));
  for (const event of ['focusin', 'pointerdown']) {
    const card = new Element('wanderer-settings');
    const tabs = new Element('settings-tabs-previews');
    const calls = [];
    const context = {capturing: null, pendingRender: false, screenshotLive: null,
      WM: {el: id => {
        if (id === 'settings-tabs-previews') return tabs;
        assert.equal(id, 'wanderer-settings'); return card;
      },
        send: (...args) => {calls.push(args); return Promise.resolve();}},
      render: () => {throw Error('no roster update pending');}};
    vm.createContext(context); vm.runInContext(capture, context);
    const button = {textContent: 'Old keybind', classList: {add() {}, remove() {}}};
    context.beginCapture(button, () => {throw Error('credential input cannot become a keybind');});
    await turn(); assert.equal(button.textContent, 'Press a key…');
    card.dispatchEvent({type: event});
    assert.equal(context.capturing, null, 'card entry releases native and page capture');
    assert.equal(button.textContent, 'Old keybind');
    assert.deepEqual(calls, [['set_bind_capture', true], ['set_bind_capture', false]]);
  }
});

test('previous Test result in an early push is not a new Test outcome', async () => {
  const p = page(); await p.hydrate({credential_present: true, test_result: 'success',
    test_result_text: 'Connected to Wanderer.', last_success_monotonic: 10});
  await p.click('test');
  p.push(state({credential_present: true, test_result: 'success',
    test_result_text: 'Connected to Wanderer.', last_success_monotonic: 10}));
  assert.match(p.el('test-status').textContent, /Saving/i);
  await p.reply('test_wanderer_connection', result({credential_present: true}));
  // A post-admission read can settle a coalesced repeated outcome without
  // pretending the old push has a sequence number the API does not provide.
  await p.reply('wanderer_state', state({credential_present: true, test_pending: true}));
  assert.match(p.el('test-status').textContent, /queued|Waiting/i);
  p.push(state({credential_present: true, test_result: 'success',
    test_result_text: 'Connected to Wanderer.', last_success_monotonic: 12}));
  assert.match(p.el('test-status').textContent, /Connected/);
});

test('Test read failure releases admission feedback without claiming a new success', async () => {
  const p = page(); await p.hydrate({credential_present: true, test_result: 'success',
    test_result_text: 'Connected to Wanderer.'});
  await p.click('test'); await p.reply('test_wanderer_connection', result({credential_present: true}));
  await p.reply('wanderer_state', null);
  assert.match(p.el('test-error').textContent, /status|read/i);
  assert.doesNotMatch(p.el('test-status').textContent, /queued|Connected/);
  assert.equal(p.el('test').disabled, false);
});

for (const early of [true, false]) {
  test('grouped save owns new Test revision with outcome ' + (early ? 'before' : 'after') + ' acknowledgement', async () => {
    const p = page(); await p.hydrate();
    p.edit('url', 'https://new.example'); p.edit('map', 'new'); p.edit('token', 'ephemeral-input');
    await p.click('test');
    const next = {base_url: 'https://new.example', map_identifier: 'new', credential_present: true,
      revision: 2, generation: 2};
    const completed = state(Object.assign({}, next, {test_result: 'success', test_result_text: 'Connected to Wanderer.'}));
    if (early) p.push(completed);
    await p.reply('test_wanderer_connection', result(next));
    if (!early) {
      assert.match(p.el('test-status').textContent, /queued/i);
      p.push(completed);
    }
    assert.match(p.el('test-status').textContent, /Connected/);
    assert.equal(p.el('test').disabled, false);
    assert.equal(p.el('enabled').checked, false);
  });
}

test('grouped save cancellation after its admitted generation does not wait forever', async () => {
  const p = page(); await p.hydrate(); p.edit('token', 'ephemeral-input');
  await p.click('test');
  const next = {revision: 2, generation: 2, credential_present: true};
  p.push(state(Object.assign({}, next, {generation: 3, host_available: false})));
  await p.reply('test_wanderer_connection', result(next));
  assert.match(p.el('test-error').textContent, /changed|unknown|interrupt/i);
  assert.equal(p.el('test').disabled, false);
});

test('reopened failed-compensation state cannot advertise a retained old Test success', async () => {
  const p = page(); await p.hydrate({enabled: true, persistence_error: true, credential_error: true,
    status: 'persistence_error', test_result: 'success', test_result_text: 'Connected to Wanderer.'});
  assert.match(p.el('health').textContent, /restart|stopped|restore/i);
  assert.doesNotMatch(p.el('test-status').textContent, /Connected/);
});

test('failed compensation never paints a healthy saved credential or an old Test result', async () => {
  const p = page(); await p.hydrate({enabled: true, credential_present: true, status: 'connected',
    test_result: 'success', test_result_text: 'Connected to Wanderer.'});
  p.edit('token', 'ephemeral-input'); await p.click('test');
  await p.reply('test_wanderer_connection', result({enabled: true, revision: 2, persistence_error: true,
    credential_error: true}, 'Could not restore the saved connection. Restart Wingman.'));
  assert.match(p.el('health').textContent, /restart|stopped|restore/i);
  assert.doesNotMatch(p.el('health').textContent, /^Connected/);
  assert.doesNotMatch(p.el('credential').textContent, /^Token stored/);
  assert.doesNotMatch(p.el('test-status').textContent, /Connected/);
});

// The controller regression supplies an actual barrier-controlled read trace.
// Replaying it here pins both sampling coherence and the page's handoff fence.
if (process.argv[2] === '--handoff-trace') {
  const [initial, raced, settled] = JSON.parse(process.argv[3]);
  test('controller reverse-handoff trace recovers connected coverage on section read', async () => {
    const p = page(); p.enter(); await p.reply('wanderer_state', initial);
    p.edit('map', 'unsubmitted draft');
    p.push(raced);
    p.enter(); await p.reply('wanderer_state', settled);
    assert.match(p.el('health').textContent, /Connected/);
    assert.match(p.el('coverage').textContent, /2 of 2/);
    assert.equal(p.el('map').value, 'unsubmitted draft');
  });
}

(async () => {
  let failed = 0;
  for (const item of tests) {
    try { await item.run(); console.log('ok ' + item.name); }
    catch (error) { failed++; console.error('FAIL ' + item.name + '\n' + error.stack); }
  }
  console.log(`${tests.length - failed} passed, ${failed} failed`);
  process.exitCode = failed ? 1 : 0;
})();
