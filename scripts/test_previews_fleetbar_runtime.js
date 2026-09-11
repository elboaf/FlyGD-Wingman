#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Keep this harness filename stable; Settings and the global toggle now have
// their own complete production module, independent of Preview initialization.
const fleetPath = path.join(__dirname, '../wingman/web/fleet.js');
assert.ok(fs.existsSync(fleetPath), 'Fleet Settings ownership must live in wingman/web/fleet.js');
const fleetSource = fs.readFileSync(fleetPath, 'utf8');
const tests = [];
function test(name, run) { tests.push({name, run}); }
function turn() { return new Promise(resolve => setImmediate(resolve)); }

class Element {
  constructor(id, tagName = 'div', ownerDocument = null) {
    this.id = id;
    this.ownerDocument = ownerDocument;
    this.tagName = tagName.toUpperCase();
    this.checked = false;
    this.hidden = false;
    this.disabled = false;
    this.textContent = '';
    this.className = '';
    this.value = '';
    this.type = 'text';
    this.attributes = {};
    this.children = [];
    this.parentNode = null;
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
  appendChild(child) {
    return this.insertBefore(child, null);
  }
  insertBefore(child, reference) {
    assert.ok(reference === null || this.children.includes(reference));
    if (child === reference) reference = this.children[this.children.indexOf(child) + 1] || null;
    // Native insertion relocates an existing node, blurring a focused descendant
    // even when appending it to the same parent. Never duplicate the old entry.
    child.remove();
    const index = reference === null ? this.children.length : this.children.indexOf(reference);
    this.children.splice(index, 0, child);
    child.parentNode = this;
    return child;
  }
  contains(node) {
    for (; node; node = node.parentNode) {
      if (node === this) return true;
    }
    return false;
  }
  focus() {
    if (!this.disabled && this.ownerDocument.body.contains(this)) {
      this.ownerDocument.activeElement = this;
    }
  }
  remove() {
    if (!this.parentNode) return;
    if (this.ownerDocument && this.contains(this.ownerDocument.activeElement)) {
      this.ownerDocument.activeElement = this.ownerDocument.body;
    }
    this.parentNode.children = this.parentNode.children.filter(item => item !== this);
    this.parentNode = null;
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  getAttribute(name) {
    return this.attributes[name] ?? null;
  }
  querySelectorAll(selector) {
    const attribute = selector.match(/^\[(data-fleet-(?:character|group))(?:="([^"]*)")?\]$/);
    let matches;
    if (attribute) {
      matches = child => attribute[2] === undefined
        ? child.getAttribute(attribute[1]) !== null
        : child.getAttribute(attribute[1]) === attribute[2];
    } else if (selector === 'input[type="checkbox"]') {
      matches = child => child.tagName === 'INPUT' && child.type === 'checkbox';
    } else if (selector === '.fleet-character-name') {
      matches = child => child.classList.contains('fleet-character-name');
    } else {
      throw new Error('Unsupported Fleet harness selector: ' + selector);
    }
    const result = [];
    for (const child of this.children) {
      if (matches(child)) result.push(child);
      result.push(...child.querySelectorAll(selector));
    }
    return result;
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
  get classList() {
    const self = this;
    function names() { return self.className ? self.className.split(/\s+/).filter(Boolean) : []; }
    return {
      contains(name) { return names().includes(name); },
      add(name) {
        if (!this.contains(name)) self.className = names().concat(name).join(' ');
      },
      remove(name) {
        self.className = names().filter(item => item !== name).join(' ');
      },
      toggle(name, force) {
        const on = force === undefined ? !this.contains(name) : !!force;
        if (on) this.add(name); else this.remove(name);
        return on;
      }
    };
  }
}

function state(enabled, revision, characters = []) {
  return { enabled, revision, characters };
}

function page() {
  const ids = [
    'btn-fleetbar', 'fleetbar-enabled', 'fleetbar-reset',
    'fleetbar-enabled-status', 'fleetbar-character-list',
    'fleetbar-characters-empty', 'fleetbar-characters-status', 'section-fleet'
  ];
  const document = {
    activeElement: null, body: null, listeners: {},
    addEventListener: Element.prototype.addEventListener,
    dispatchEvent: Element.prototype.dispatchEvent
  };
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id, 'div', document)]));
  elements['btn-fleetbar'].tagName = 'BUTTON';
  elements['fleetbar-enabled'].tagName = 'INPUT';
  elements['fleetbar-enabled'].type = 'checkbox';
  elements['fleetbar-reset'].tagName = 'BUTTON';
  elements['fleetbar-enabled-status'].textContent = 'Default hint';
  const body = new Element('body', 'BODY', document);
  // Start outside Fleet so boot hydration cannot depend on section entry.
  elements['section-fleet'].hidden = true;
  body.appendChild(elements['btn-fleetbar']);
  body.appendChild(elements['section-fleet']);
  ids.filter(id => id !== 'btn-fleetbar' && id !== 'section-fleet').forEach(id => {
    elements['section-fleet'].appendChild(elements[id]);
  });
  document.activeElement = body;
  document.body = body;
  const handlers = {};
  const calls = [];
  const WM = {
    current_route: 'main',
    current_section: 'general',
    eve_shown: true,
    el: id => elements[id] || null,
    make: (tag, className, text) => {
      const node = new Element('', tag, document);
      node.className = className || '';
      node.textContent = text || '';
      return node;
    },
    handle: (name, listener) => { handlers[name] = listener; },
    send: (method, ...args) => {
      let resolve, reject;
      const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
      calls.push({method, args, resolve, reject});
      // WM.send in app.js converts bridge rejections into resolved nulls.
      return promise.catch(() => null);
    }
  };
  vm.runInNewContext(fleetSource, {window: {WM}, WM, document, Promise}, {
    filename: 'wingman/web/fleet.js'
  });
  return {
    WM,
    document,
    el: id => elements[id],
    calls,
    async reply(method, result, args) {
      const index = calls.findIndex(call => call.method === method);
      assert.notEqual(index, -1, 'Expected pending call to ' + method);
      const call = calls.splice(index, 1)[0];
      if (args) assert.deepEqual(call.args, args);
      call.resolve(result);
      await turn();
    },
    async reject(method, args) {
      const index = calls.findIndex(call => call.method === method);
      assert.notEqual(index, -1, 'Expected pending call to ' + method);
      const call = calls.splice(index, 1)[0];
      if (args) assert.deepEqual(call.args, args);
      call.reject(new Error('bridge failed'));
      await turn();
    },
    async push(payload) {
      assert.equal(typeof handlers.onFleetBarState, 'function');
      handlers.onFleetBarState(payload);
      await turn();
    },
    async section(name) {
      WM.current_section = name;
      elements['section-fleet'].hidden = name !== 'fleet';
      document.dispatchEvent({type: 'wm:section', detail: name});
      await turn();
    },
    focus(id) { document.activeElement = elements[id]; },
    async click(id) {
      elements[id].dispatchEvent({type: 'click'});
      await turn();
    },
    async toggle(value) {
      document.activeElement = elements['fleetbar-enabled'];
      elements['fleetbar-enabled'].checked = value;
      elements['fleetbar-enabled'].dispatchEvent({type: 'change'});
      await turn();
    }
  };
}

const toggleWarning = 'Applied for this session only. Your saved choice may return after restart.';
const resetWarning = 'The Fleet Bar width changed, but it will not survive restart.';

test('controls stay disarmed before boot hydration without entering Fleet Settings', async () => {
  const p = page();
  for (const id of ['btn-fleetbar', 'fleetbar-enabled', 'fleetbar-reset']) {
    assert.equal(p.el(id).disabled, true, id + ' must start disabled');
  }
  await p.click('btn-fleetbar');
  await p.click('fleetbar-reset');
  await p.toggle(true);
  assert.deepEqual(p.calls.map(call => ({method: call.method, args: call.args})), [
    {method: 'fleet_bar_settings', args: []}
  ]);
  await p.reply('fleet_bar_settings', state(false, 1), []);
  for (const id of ['btn-fleetbar', 'fleetbar-enabled', 'fleetbar-reset']) {
    assert.equal(p.el(id).disabled, false, id + ' must enable after hydration');
  }
});

test('failed boot hydration explains how to retry and keeps controls disarmed', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', null, []);
  assert.equal(p.el('fleetbar-enabled-status').textContent,
    'Could not read Fleet Bar settings. Reopen Fleet telemetry to retry.');
  for (const id of ['btn-fleetbar', 'fleetbar-enabled', 'fleetbar-reset']) {
    assert.equal(p.el(id).disabled, true, id + ' must stay disabled after a failed read');
  }
  await p.click('btn-fleetbar');
  await p.click('fleetbar-reset');
  await p.toggle(true);
  assert.deepEqual(p.calls, [], 'failed hydration cannot admit writes or retry automatically');
});

test('only Fleet reentry retries failed hydration and coalesces pending reads', async () => {
  const p = page();
  await p.section('fleet');
  await p.section('general');
  await p.section('fleet');
  assert.deepEqual(p.calls.map(call => call.method), ['fleet_bar_settings'],
    'section entry during the boot read must not duplicate it');
  await p.reply('fleet_bar_settings', null, []);
  await p.section('general');
  await p.section('previews');
  assert.deepEqual(p.calls, [], 'other sections must not retry Fleet hydration');

  await p.section('fleet');
  await p.section('fleet');
  await p.section('general');
  await p.section('fleet');
  assert.deepEqual(p.calls.map(call => call.method), ['fleet_bar_settings'],
    'repeated entry must share one pending retry');
  await p.reply('fleet_bar_settings', state(true, 2), []);
  assert.equal(p.el('fleetbar-enabled-status').textContent, 'Default hint');
  assert.equal(p.el('fleetbar-enabled').checked, true);
  for (const id of ['btn-fleetbar', 'fleetbar-enabled', 'fleetbar-reset']) {
    assert.equal(p.el(id).disabled, false, id + ' must enable after recovery');
  }
  await p.section('general');
  await p.section('fleet');
  assert.deepEqual(p.calls, [], 'healthy reentry must not read or write');
});

test('healthy boot hydration needs no extra reads on Fleet entry', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', state(false, 1), []);
  for (const section of ['fleet', 'general', 'fleet', 'previews', 'fleet']) {
    await p.section(section);
  }
  assert.deepEqual(p.calls, [], 'healthy entry must not read or write');
});

test('an authoritative push clears the hydration failure without needing a retry', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', null, []);
  assert.match(p.el('fleetbar-enabled-status').textContent, /Could not read Fleet Bar settings/);
  await p.push(state(true, 2));
  assert.equal(p.el('fleetbar-enabled-status').textContent, 'Default hint');
  assert.equal(p.el('fleetbar-enabled').checked, true);
  assert.equal(p.el('fleetbar-reset').disabled, false);
  await p.section('fleet');
  assert.deepEqual(p.calls, []);
});

test('a newer push suppresses a delayed null boot response', async () => {
  const p = page();
  await p.push(state(true, 2));
  await p.reply('fleet_bar_settings', null, []);
  assert.equal(p.el('fleetbar-enabled-status').textContent, 'Default hint');
  assert.equal(p.WM.fleet_bar_on, true);
  assert.equal(p.el('fleetbar-enabled').checked, true);
  assert.equal(p.el('btn-fleetbar').getAttribute('aria-pressed'), 'true');
  assert.equal(p.el('fleetbar-reset').disabled, false);
  await p.section('fleet');
  assert.deepEqual(p.calls, []);
});

for (const [control, method, warning] of [
  ['btn-fleetbar', 'toggle_fleet_bar', toggleWarning],
  ['fleetbar-reset', 'reset_fleet_bar_width', resetWarning]
]) {
  test('pushes and late boot failure preserve the ' + method + ' session-only warning', async () => {
    const p = page();
    await p.push(state(true, 2));
    await p.click(control);
    await p.reply(method, {applied: true, persisted: false, error: warning});
    await p.push(state(true, 3));
    await p.reply('fleet_bar_settings', null, []);
    await p.section('fleet');
    assert.equal(p.el('fleetbar-enabled-status').textContent, warning);
    assert.equal(p.WM.fleet_bar_on, true);
    assert.equal(p.el('fleetbar-enabled').checked, true);
    assert.deepEqual(p.calls, []);
  });
}

test('late hydration recovery cannot clear a newer mutation failure', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', null, []);
  await p.section('fleet');
  await p.push(state(true, 3));
  await p.click('fleetbar-reset');
  await p.reply('reset_fleet_bar_width', {
    applied: false, persisted: false, error: 'Width reset was refused.'
  }, []);
  await p.reply('fleet_bar_settings', state(false, 2), []);
  await p.push(state(true, 4));
  assert.equal(p.el('fleetbar-enabled-status').textContent, 'Width reset was refused.');
  assert.equal(p.WM.fleet_bar_on, true);
  assert.equal(p.el('fleetbar-enabled').checked, true);
});

test('a newer push wins over the late boot response while Fleet Settings stays closed', async () => {
  const p = page();
  await p.push(state(true, 2));
  await p.reply('fleet_bar_settings', state(false, 1), []);
  assert.equal(p.WM.fleet_bar_on, true);
  assert.equal(p.el('fleetbar-enabled').checked, true);
  assert.equal(p.el('btn-fleetbar').getAttribute('aria-pressed'), 'true');
  assert.equal(p.el('fleetbar-reset').disabled, false);
});

test('the global toggle and tokenless reset synchronize results while Fleet Settings stays closed', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', state(false, 1), []);
  await p.click('btn-fleetbar');
  await p.reply('toggle_fleet_bar', {
    applied: true, persisted: true, error: null, state: state(true, 2)
  }, [true]);
  assert.equal(p.WM.fleet_bar_on, true);
  assert.equal(p.el('fleetbar-enabled').checked, true);
  assert.equal(p.el('btn-fleetbar').getAttribute('aria-pressed'), 'true');
  assert.ok(p.el('btn-fleetbar').classList.contains('active'));

  await p.click('fleetbar-reset');
  await p.push(state(false, 4));
  await p.reply('reset_fleet_bar_width', {
    applied: true, persisted: false, error: resetWarning, state: state(true, 3)
  }, []);
  assert.equal(p.WM.fleet_bar_on, false);
  assert.equal(p.el('fleetbar-enabled').checked, false);
  assert.equal(p.el('btn-fleetbar').getAttribute('aria-pressed'), 'false');
  assert.equal(p.el('btn-fleetbar').classList.contains('active'), false);
  assert.equal(p.el('fleetbar-enabled-status').textContent, resetWarning);

  await p.click('btn-fleetbar');
  await p.reply('toggle_fleet_bar', {
    applied: true, persisted: true, error: null, state: state(true, 5)
  }, [true]);
  assert.equal(p.WM.fleet_bar_on, true);
  assert.equal(p.el('fleetbar-enabled').checked, true);
  assert.equal(p.el('btn-fleetbar').getAttribute('aria-pressed'), 'true');
  assert.equal(p.el('fleetbar-enabled-status').textContent, 'Default hint');
});

test('toggle session-only result keeps authoritative state and shows the warning', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', state(false, 1));
  await p.click('btn-fleetbar');
  await p.push(state(true, 2));
  await p.reply('toggle_fleet_bar', {applied: true, persisted: false, error: toggleWarning}, [true]);
  assert.equal(p.el('fleetbar-enabled').checked, true);
  assert.equal(p.el('btn-fleetbar').getAttribute('aria-pressed'), 'true');
  assert.ok(p.el('btn-fleetbar').classList.contains('active'));
  assert.equal(p.el('fleetbar-enabled-status').textContent, toggleWarning);
});

test('a later persisted toggle clears the prior session-only warning back to the default hint', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', state(false, 1));
  await p.click('btn-fleetbar');
  await p.push(state(true, 2));
  await p.reply('toggle_fleet_bar', {applied: true, persisted: false, error: toggleWarning}, [true]);
  await p.click('btn-fleetbar');
  await p.push(state(false, 3));
  await p.reply('toggle_fleet_bar', {applied: true, persisted: true, error: null}, [false]);
  assert.equal(p.el('fleetbar-enabled').checked, false);
  assert.equal(p.el('btn-fleetbar').getAttribute('aria-pressed'), 'false');
  assert.equal(p.el('fleetbar-enabled-status').textContent, 'Default hint');
});

test('reset session-only result keeps its warning visible', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', state(true, 1));
  await p.click('fleetbar-reset');
  await p.reply('reset_fleet_bar_width', {applied: true, persisted: false, error: resetWarning}, []);
  assert.equal(p.el('fleetbar-enabled').checked, true);
  assert.ok(p.el('btn-fleetbar').classList.contains('active'));
  assert.equal(p.el('fleetbar-enabled-status').textContent, resetWarning);
});

test('toggle bridge failure restores the last authoritative state and shows an error', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', state(false, 1));
  await p.toggle(true);
  await p.reject('toggle_fleet_bar', [true]);
  assert.equal(p.el('fleetbar-enabled').checked, false);
  assert.equal(p.el('fleetbar-enabled-status').textContent, 'Could not change the Fleet Bar.');
});

for (const running of [true, null]) {
  test('same-order local character heartbeats preserve keyed rows and focus with running=' + running, async () => {
    const p = page();
    const characters = [
      {name: 'Alice Example', running, visible: true},
      {name: 'Bravo Example', running: running === null ? null : false, visible: false}
    ];
    await p.reply('fleet_bar_settings', state(true, 1, characters));
    p.el('section-fleet').hidden = false;
    const host = p.el('fleetbar-character-list');
    const original = host.children.slice();
    const input = host.querySelector('input[type="checkbox"]');
    assert.ok(input, 'nonempty local character payload must render a checkbox');
    assert.equal(input.getAttribute('aria-label'), 'Show Alice Example in Fleet Bar');
    assert.equal(host.querySelector('.fleet-character-name').textContent, 'Alice Example');
    assert.equal(p.el('fleetbar-characters-empty').hidden, true);
    input.focus();
    assert.ok(p.document.activeElement === input, 'the local checkbox starts focused');

    for (const revision of [2, 3]) {
      await p.push(state(true, revision, characters));
      assert.ok(p.document.activeElement === input, 'unchanged local Fleet heartbeat keeps checkbox focus');
      assert.equal(host.children.length, original.length, 'heartbeat must not duplicate headings or rows');
      original.forEach((node, index) => assert.equal(host.children[index], node));
      assert.equal(host.querySelectorAll('input[type="checkbox"]')[1].checked, false);
    }
    assert.deepEqual(p.calls, [], 'heartbeats need no extra hydration or mutation calls');
  });
}

test('local roster regrouping reuses rows and removes stale characters and headings', async () => {
  const p = page();
  await p.reply('fleet_bar_settings', state(true, 1, [
    {name: 'Alice Example', running: true, visible: true},
    {name: 'Bravo Example', running: false, visible: false},
    {name: 'Cyra Example', running: false, visible: true}
  ]));
  const host = p.el('fleetbar-character-list');
  const [alice, bravo, cyra] = host.querySelectorAll('[data-fleet-character]');
  const [running, offline] = host.querySelectorAll('[data-fleet-group]');
  function order() {
    return host.children.map(node => node.getAttribute('data-fleet-group')
      || node.getAttribute('data-fleet-character'));
  }
  assert.deepEqual(order(), ['Running', 'Alice Example', 'Offline', 'Bravo Example', 'Cyra Example']);

  await p.push(state(true, 2, [
    {name: 'Alice Example', running: false, visible: false},
    {name: 'Bravo Example', running: true, visible: true},
    {name: 'Delta Example', running: false, visible: true}
  ]));
  assert.deepEqual(order(), ['Running', 'Bravo Example', 'Offline', 'Alice Example', 'Delta Example']);
  assert.equal(host.children[0], running);
  assert.equal(host.children[1], bravo);
  assert.equal(host.children[2], offline);
  assert.equal(host.children[3], alice);
  assert.equal(cyra.parentNode, null);
  assert.equal(alice.querySelector('input[type="checkbox"]').checked, false);
  assert.equal(bravo.querySelector('input[type="checkbox"]').checked, true);
  const delta = host.children[4];

  await p.push(state(true, 3, [
    {name: 'Alice Example', running: null, visible: false},
    {name: 'Bravo Example', running: null, visible: true},
    {name: 'Delta Example', running: null, visible: true}
  ]));
  assert.deepEqual(order(), ['Known characters', 'Alice Example', 'Bravo Example', 'Delta Example']);
  assert.equal(host.children[1], alice);
  assert.equal(host.children[2], bravo);
  assert.equal(host.children[3], delta);
  assert.equal(running.parentNode, null);
  assert.equal(offline.parentNode, null);
  const known = host.children[0];

  await p.push(state(true, 4, [{name: 'Bravo Example', running: true, visible: true}]));
  assert.deepEqual(order(), ['Running', 'Bravo Example']);
  assert.equal(host.children[1], bravo);
  for (const removed of [known, alice, delta]) assert.equal(removed.parentNode, null);

  await p.push(state(true, 5));
  assert.deepEqual(order(), []);
  assert.equal(bravo.parentNode, null);
  assert.equal(p.el('fleetbar-characters-empty').hidden, false);
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
  console.log(`${tests.length - failures}/${tests.length} Fleet Settings/status-strip runtime tests passed`);
  if (failures) process.exitCode = 1;
}());
