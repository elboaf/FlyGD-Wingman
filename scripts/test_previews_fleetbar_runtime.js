#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../wingman/web/previews.js'), 'utf8');
const fleetSource = source.split('// Preview hotkeys.', 1)[0];
const tests = [];
function test(name, run) { tests.push({name, run}); }
function turn() { return new Promise(resolve => setImmediate(resolve)); }

class Element {
  constructor(id, tagName = 'div') {
    this.id = id;
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
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  remove() {
    if (!this.parentNode) return;
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
    if (selector === '[data-fleet-character]' || selector === '[data-fleet-group]') return [];
    if (selector === 'input[type="checkbox"]') return this.children.filter(child => child.tagName === 'INPUT' && child.type === 'checkbox');
    if (selector === '.fleet-character-name') return this.children.filter(child => child.className === 'fleet-character-name');
    return [];
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

function state(enabled, revision) {
  return { enabled, revision, characters: [] };
}

function page() {
  const ids = [
    'btn-fleetbar', 'fleetbar-enabled', 'fleetbar-reset',
    'fleetbar-enabled-status', 'fleetbar-character-list',
    'fleetbar-characters-empty', 'fleetbar-characters-status'
  ];
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
  elements['btn-fleetbar'].tagName = 'BUTTON';
  elements['fleetbar-enabled'].tagName = 'INPUT';
  elements['fleetbar-enabled'].type = 'checkbox';
  elements['fleetbar-reset'].tagName = 'BUTTON';
  elements['fleetbar-enabled-status'].textContent = 'Default hint';
  const body = new Element('body', 'BODY');
  const document = { activeElement: body, body };
  const handlers = {};
  const calls = [];
  const WM = {
    el: id => elements[id] || null,
    make: (tag, className, text) => {
      const node = new Element('', tag);
      node.className = className || '';
      node.textContent = text || '';
      return node;
    },
    handle: (name, listener) => { handlers[name] = listener; },
    send: (method, ...args) => {
      let resolve, reject;
      const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
      calls.push({method, args, resolve, reject});
      return promise;
    }
  };
  vm.runInNewContext(fleetSource, {window: {WM}, WM, document, Promise}, {
    filename: 'wingman/web/previews.js'
  });
  return {
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
  await p.reply('reset_fleet_bar_width', {applied: true, persisted: false, error: resetWarning});
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
  console.log(`${tests.length - failures}/${tests.length} previews Fleet Bar runtime tests passed`);
  if (failures) process.exitCode = 1;
}());
