/* Executable Fleet regressions: real fleetbar.js with controlled DOM
 * measurements, bridge continuations, resize settlement, header actions,
 * and directional damage rendering -- no native/CSS/WebView2 claims.
 *
 * Two families share this one node:test harness: creation-identity/page
 * lifecycle (token captured from `#fleet-page=<64 lowercase hex>`, every
 * bridge call bound to it, the final token-bound standalone surface, and
 * delayed fit/settle/ready continuations keeping identity) and split Damage
 * rendering (independent OUT/IN rails, mixed-null unavailable, zero, >10m,
 * EWAR, accessibility). Do not split this back into two frameworks in one
 * file. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const web = path.join(__dirname, '..', 'wingman', 'web');
const source = fs.readFileSync(path.join(web, 'fleetbar.js'), 'utf8');
const html = fs.readFileSync(path.join(web, 'fleetbar.html'), 'utf8');
assert.ok(process.env.WINGMAN_PYWEBVIEW_CUSTOMIZE,
  'Run via tests/test_fleetbar_runtime.py or set WINGMAN_PYWEBVIEW_CUSTOMIZE to the installed pywebview js/customize.js');
const customizeOptions = { text_select: 'True', easy_drag: 'False',
  drag_region_direct_target_only: 'False', drag_selector: '.pywebview-drag-region',
  zoomable: 'True', draggable: 'True' };
const customize = fs.readFileSync(process.env.WINGMAN_PYWEBVIEW_CUSTOMIZE, 'utf8')
  .replace(/%\((\w+)\)s/g, (_, name) => {
    assert.ok(Object.hasOwn(customizeOptions, name), 'unrecognized pywebview option ' + name);
    return customizeOptions[name];
  });
const A = '0123456789abcdef'.repeat(4);
const B = 'b'.repeat(64);
const fragment = token => '#fleet-page=' + token;

class EventTarget {
  constructor() { this.listeners = {}; }
  addEventListener(name, fn, options = {}) {
    (this.listeners[name] ||= []).push({ fn, once: options.once });
  }
  removeEventListener(name, fn) {
    this.listeners[name] = (this.listeners[name] || []).filter(listener => listener.fn !== fn);
  }
  dispatchEvent(event) {
    event = event || {};
    if (!event.type) throw new Error('event.type required');
    if (!event.target) event.target = this;
    event.currentTarget = this;
    if (!event.preventDefault) {
      event.defaultPrevented = false;
      event.preventDefault = function () { this.defaultPrevented = true; };
    }
    for (const listener of [...(this.listeners[event.type] || [])]) {
      if (listener.once) {
        this.listeners[event.type] = this.listeners[event.type].filter(l => l !== listener);
      }
      listener.fn(event);
    }
    return !event.defaultPrevented;
  }
}

class Element extends EventTarget {
  constructor(document, id = '') {
    super();
    this.ownerDocument = document;
    this.nodeType = 1;
    this.id = id;
    this.children = [];
    this.attributes = {};
    this.className = '';
    this.hidden = false;
    this.disabled = false;
    this.style = {};
    this.title = '';
    this.text = '';
    this.offsetWidth = 0;
    this.offsetHeight = 0;
    this.rectWidth = null;
    this.parentNode = null;
    this.classList = {
      contains: name => this.className.split(/\s+/).filter(Boolean).includes(name),
      add: name => {
        if (!this.classList.contains(name)) {
          this.className = (this.className + ' ' + name).trim();
        }
      },
      remove: name => {
        this.className = this.className.split(/\s+/).filter(n => n && n !== name).join(' ');
      },
      toggle: (name, force) => {
        const on = force === undefined ? !this.classList.contains(name) : force;
        if (on) this.classList.add(name); else this.classList.remove(name);
        return on;
      }
    };
  }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() {
    return this.text + this.children.map(child => child.textContent).join('');
  }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  getBoundingClientRect() {
    return {
      width: this.rectWidth == null ? this.offsetWidth : this.rectWidth,
      height: this.offsetHeight,
      left: 0,
      top: 0,
      right: this.rectWidth == null ? this.offsetWidth : this.rectWidth,
      bottom: this.offsetHeight
    };
  }
  focus() {
    if (this.ownerDocument && typeof this.ownerDocument.canFocus === 'function' &&
        !this.ownerDocument.canFocus(this)) return;
    const previous = this.ownerDocument.activeElement;
    if (previous && previous !== this) previous.dispatchEvent({ type: 'blur' });
    this.ownerDocument.activeElement = this;
    this.dispatchEvent({ type: 'focus' });
  }
  blur() {
    if (this.ownerDocument.activeElement === this) {
      this.ownerDocument.activeElement = null;
    }
    this.dispatchEvent({ type: 'blur' });
  }
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function flush() { await new Promise(resolve => setImmediate(resolve)); }
async function settle(call, value = null) { call.resolve(value); await flush(); }
async function fail(call) {
  call.reject(new Error('injected bridge rejection'));
  await flush();
}

async function page(options = {}) {
  const nodes = new Map();
  for (const match of html.matchAll(/\bid="([^"]+)"/g)) {
    nodes.set(match[1], new Element(null, match[1]));
  }
  const document = new EventTarget();
  document.body = new Element(document);
  document.documentElement = new Element(document);
  document.activeElement = null;
  for (const node of nodes.values()) node.ownerDocument = document;
  const shell = nodes.get('fleet-shell');
  shell.offsetWidth = options.width ?? 420;
  shell.rectWidth = options.width ?? 420;
  shell.offsetHeight = options.height ?? 114;
  shell.parentNode = document.body;
  const title = nodes.get('fleet-title');
  const drag = nodes.get('fleet-drag');
  drag.parentNode = title;
  drag.className = 'fleet-drag pywebview-drag-region';
  title.offsetHeight = 29;
  const titleEnd = nodes.get('fleet-title-end');
  const actions = nodes.get('fleet-title-actions');
  const reset = nodes.get('fleet-reset-width');
  const hide = nodes.get('fleet-hide');
  const table = nodes.get('fleet-table');
  table.offsetHeight = options.tableHeight ?? 95;
  title.parentNode = shell;
  titleEnd.parentNode = title;
  actions.parentNode = titleEnd;
  reset.parentNode = actions;
  hide.parentNode = actions;
  table.parentNode = shell;
  const fonts = deferred();
  if (options.fonts !== false) document.fonts = { ready: fonts.promise };
  const actionsNeedVisibleFocus = /\.fleet-title-actions[\s\S]*?visibility:\s*hidden/.test(html);
  document.canFocus = node => {
    if (!node || node.disabled || node.hidden) return false;
    if ((node.id === 'fleet-reset-width' || node.id === 'fleet-hide') &&
        actionsNeedVisibleFocus &&
        document.activeElement !== node) {
      return false;
    }
    return true;
  };
  document.getElementById = id => nodes.get(id) || null;
  document.createElement = () => new Element(document);
  document.querySelectorAll = selector => selector === '.pywebview-drag-region' ? [drag] : [];
  document.querySelector = selector => selector === '.fleet-shell' ? shell
    : selector === '.fleet-table' ? table : null;

  const calls = [];
  const errors = [];
  const api = {};
  for (const method of [
    'fleet_bar_snapshot', 'fit_fleet_bar_height', 'settle_fleet_bar_resize',
    'reset_fleet_bar_page_width', 'save_fleet_bar_pos', 'fleet_bar_ready',
    'activate_fleet_bar', 'deactivate_fleet_bar', 'hide_fleet_bar'
  ]) {
    api[method] = (...args) => {
      const reply = deferred();
      calls.push({ method, args, ...reply });
      return reply.promise;
    };
  }

  let now = 0;
  let nextTimerId = 1;
  const timers = [];
  function sortTimers() { timers.sort((a, b) => a.at - b.at || a.id - b.id); }
  function setTimer(fn, delay) {
    const id = nextTimerId++;
    timers.push({ id, at: now + Number(delay || 0), fn });
    sortTimers();
    return id;
  }
  function clearTimer(id) {
    const index = timers.findIndex(timer => timer.id === id);
    if (index !== -1) timers.splice(index, 1);
  }

  const window = new EventTarget();
  window.location = { hash: options.hash ?? fragment(A) };
  window.screenX = options.x ?? 20;
  window.screenY = options.y ?? 30;
  const nativeMoves = [];
  function attachNativeBridge() {
    window.pywebview = { api, platform: 'edgechromium', _jsApiCallback: (method, args, id) => {
      assert.equal(method, 'pywebviewMoveWindow');
      assert.equal(id, 'move');
      nativeMoves.push(Array.from(args));
      [window.screenX, window.screenY] = args;
    } };
    vm.runInContext(customize, context, { filename: 'pywebview/customize.js' });
  }
  const screen = options.screen ?? {
    availLeft: 0, availTop: 0, availWidth: 1280, availHeight: 720
  };
  const context = vm.createContext({
    window, document, screen,
    setTimeout: setTimer,
    clearTimeout: clearTimer,
    console: { error: (...args) => errors.push(args) },
    Promise
  });
  if (options.bridgeReady !== false) attachNativeBridge();
  vm.runInContext(source, context, { filename: 'fleetbar.js' });
  await flush();
  return {
    window, document, shell, table, fonts, api, errors, nativeMoves,
    el: id => document.getElementById(id),
    calls: method => calls.filter(call => call.method === method),
    log: () => calls.map(({ method, args }) => [method, ...args]),
    attachBridge: async () => {
      attachNativeBridge();
      window.dispatchEvent({ type: 'pywebviewready' });
      await flush();
    },
    push: async payload => { window.onFleetSnapshot(payload); await flush(); },
    mousedown: async (id = 'fleet-drag', button = 0) => {
      const target = document.getElementById(id);
      const event = { type: 'mousedown', target, button, clientX: 15, clientY: 10,
        screenX: window.screenX + 15, screenY: window.screenY + 10 };
      for (let node = target; node; node = node.parentNode) node.dispatchEvent(event);
      document.dispatchEvent(event);
      window.dispatchEvent(event);
      await flush();
    },
    mousemove: async (x, y) => {
      window.dispatchEvent({ type: 'mousemove', screenX: x + 15, screenY: y + 10 });
      await flush();
    },
    mouseup: async () => {
      document.dispatchEvent({ type: 'mouseup' });
      window.dispatchEvent({ type: 'mouseup' });
      await flush();
    },
    resize: async width => {
      shell.offsetWidth = width;
      shell.rectWidth = width;
      window.dispatchEvent({ type: 'resize' });
      await flush();
    },
    advance: async ms => {
      now += ms;
      while (timers.length) {
        sortTimers();
        if (timers[0].at > now) break;
        const timer = timers.shift();
        timer.fn();
        await flush();
      }
    },
    pointerdown: async id => {
      const node = document.getElementById(id);
      assert.ok(node, id + ' missing from fleetbar.html');
      node.dispatchEvent({ type: 'pointerdown', button: 0 });
      await flush();
    },
    click: async id => {
      const node = document.getElementById(id);
      assert.ok(node, id + ' missing from fleetbar.html');
      if (!node.disabled) node.dispatchEvent({ type: 'click' });
      await flush();
    },
    keydown: async key => {
      const event = { type: 'keydown', key };
      const target = document.activeElement;
      if (target) target.dispatchEvent(event);
      window.dispatchEvent(event);
      document.dispatchEvent(event);
      await flush();
      return event;
    },
    tab: async () => {
      const focusables = ['fleet-reset-width', 'fleet-hide', 'fleet-table']
        .map(id => document.getElementById(id))
        .filter(Boolean)
        .filter(node => !node.disabled && !node.hidden);
      const current = document.activeElement;
      const event = { type: 'keydown', key: 'Tab' };
      if (current) current.dispatchEvent(event);
      if (!event.defaultPrevented) {
        const index = current ? focusables.indexOf(current) : -1;
        const next = focusables[index + 1] || null;
        if (next) next.focus();
      }
      window.dispatchEvent(event);
      document.dispatchEvent(event);
      await flush();
      return document.activeElement;
    },
    actionsVisible: () => {
      const title = document.getElementById('fleet-title');
      const titleEnd = document.getElementById('fleet-title-end');
      const active = document.activeElement;
      return !titleEnd.classList.contains('error-active') && contains(title, active);
    },
    blur: async () => {
      document.activeElement = null;
      window.dispatchEvent({ type: 'blur' });
      await flush();
    }
  };
}

function snapshot(revision = 1, character = 'Pilot', outgoing = 43, incoming = 20) {
  return {
    revision,
    rows: [{
      character, outgoing_dps: outgoing, incoming_dps: incoming,
      ewar: ['SCRAM', 'NEUT'], log_status: null
    }],
    running_count: 1,
    stream_health: { state: 'active', detail: null },
    metric_error: null
  };
}

function fillOf(half) {
  const track = half.children.find(child => child.className === 'fleet-damage-track');
  assert.ok(track, half.className + ' has no track');
  return track.children[0];
}

function valueOf(half) {
  return half.children.find(child => child.className.indexOf('fleet-damage-value') === 0);
}

function contains(node, target) {
  while (target) {
    if (target === node) return true;
    target = target.parentNode;
  }
  return false;
}

function assertRendered(p, character = 'Pilot', outgoing = 43, incoming = 20) {
  const rows = p.el('fleet-rows').children;
  assert.equal(rows.length, 1);
  assert.equal(rows[0].getAttribute('role'), 'row');
  assert.ok(rows[0].children.every(cell => cell.getAttribute('role') === 'cell'));
  const [charCell, damage, ewarCell] = rows[0].children;
  assert.equal(charCell.textContent, character);
  assert.equal(ewarCell.textContent, 'SCRAM \u00b7 NEUT');

  assert.equal(damage.children.length, 3);
  const [out, axis, incomingHalf] = damage.children;
  assert.equal(out.className.indexOf('fleet-damage-out'), 0);
  assert.equal(axis.className, 'fleet-damage-axis');
  assert.equal(incomingHalf.className.indexOf('fleet-damage-in'), 0);
  assert.equal(valueOf(out).textContent, String(outgoing));
  assert.equal(valueOf(incomingHalf).textContent, String(incoming));
  assert.equal(
    damage.getAttribute('aria-label'),
    `Outgoing ${outgoing} DPS, incoming ${incoming} DPS`
  );

  assert.equal(p.el('fleet-empty').hidden, true);
  assert.equal(p.el('fleet-health').textContent, 'LOCAL LIVE');
  assert.equal(p.el('fleet-note').hidden, true);
}

test('A keeps its identity through delayed bridge, fonts, snapshot, height fit and ready after B boots', async () => {
  const a = await page({ bridgeReady: false, x: 50, y: 900 });
  assert.deepEqual(a.log(), []);
  const b = await page({ hash: fragment(B), width: 460, height: 166 });
  await settle(b.fonts);
  await settle(b.calls('fleet_bar_snapshot')[0], snapshot(1, 'B pilot'));
  assert.deepEqual(b.calls('fit_fleet_bar_height')[0].args, [B, 166]);
  await settle(b.calls('fit_fleet_bar_height')[0]);
  assert.deepEqual(b.calls('fleet_bar_ready')[0].args, [B]);
  await settle(b.calls('fleet_bar_ready')[0], true);
  assertRendered(b, 'B pilot');
  assert.deepEqual(b.log(), [
    ['fleet_bar_snapshot', B], ['fit_fleet_bar_height', B, 166], ['fleet_bar_ready', B]
  ]);

  a.window.location.hash = fragment(B);
  await a.attachBridge();
  assert.deepEqual(a.log(), [['fleet_bar_snapshot', A]]);
  await settle(a.calls('fleet_bar_snapshot')[0], snapshot(1, 'A pilot'));
  assert.equal(a.el('fleet-rows').children.length, 0, 'fonts still gate hydration');
  assert.equal(a.calls('fleet_bar_ready').length, 0);
  await settle(a.fonts);
  assertRendered(a, 'A pilot');
  assert.deepEqual(a.calls('fit_fleet_bar_height')[0].args, [A, 114]);
  assert.equal(a.calls('fleet_bar_ready').length, 0);
  a.shell.offsetHeight = 190;
  a.window.screenX = 30;
  a.window.screenY = 950;
  await settle(a.calls('fit_fleet_bar_height')[0]);
  assert.deepEqual(a.calls('fleet_bar_ready')[0].args, [A]);
  await settle(a.calls('fleet_bar_ready')[0], true);

  await a.advance(500);
  assert.deepEqual(a.calls('fit_fleet_bar_height')[1].args, [A, 190]);
  await settle(a.calls('fit_fleet_bar_height')[1]);
  await a.mousedown();
  await a.mouseup();
  assert.deepEqual(a.calls('save_fleet_bar_pos')[0].args, [A, 30, 950, 'begin']);
  await settle(a.calls('save_fleet_bar_pos')[0], { status: 'dragging', drag_id: 9 });
  assert.deepEqual(a.calls('save_fleet_bar_pos')[1].args, [A, 30, 950, 'end', 9]);
  await settle(a.calls('save_fleet_bar_pos')[1]);
  assert.equal(b.log().length, 3, 'A continuations never call B\'s bridge');
  assert.deepEqual(a.errors.concat(b.errors), []);
});

test('500ms fit, 150ms resize settlement, and mouseup queued before bridge readiness keep the initial token', async () => {
  const p = await page({ bridgeReady: false, x: 50, y: 900 });
  await p.resize(480);
  await p.advance(150);
  await p.advance(350);
  await p.mousedown();
  await p.mouseup();
  assert.deepEqual(p.log(), []);
  p.window.location.hash = fragment(B);
  await p.attachBridge();
  assert.deepEqual(p.log(), [
    ['fleet_bar_snapshot', A],
    ['settle_fleet_bar_resize', A, 480, 50],
    ['save_fleet_bar_pos', A, 50, 900, 'begin']
  ]);
  await settle(p.calls('settle_fleet_bar_resize')[0], { applied: true, persisted: true, error: null });
  assert.equal(p.calls('fit_fleet_bar_height').length, 0, 'header ownership supersedes the earlier resize reply');
  await settle(p.calls('save_fleet_bar_pos')[0], { status: 'dragging', drag_id: 3 });
  assert.deepEqual(p.calls('save_fleet_bar_pos')[1].args, [A, 50, 900, 'end', 3]);
  await settle(p.calls('save_fleet_bar_pos')[1]);
  await p.advance(150);
  await settle(p.calls('settle_fleet_bar_resize')[1], { status: 'ignored' });
  assert.deepEqual(p.calls('fit_fleet_bar_height')[0].args, [A, 114]);
  assert.deepEqual(p.errors, []);
});

test('later fragment removal cannot revoke or replace the captured creation identity', async () => {
  const p = await page({ bridgeReady: false });
  p.window.location.hash = '';
  await p.attachBridge();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0]);
  assert.deepEqual(p.calls('fleet_bar_ready')[0].args, [A]);
  await settle(p.calls('fleet_bar_ready')[0], true);
  await p.mousedown();
  await p.mouseup();
  await settle(p.calls('save_fleet_bar_pos')[0], { status: 'dragging', drag_id: 1 });
  assert.deepEqual(p.log(), [
    ['fleet_bar_snapshot', A], ['fleet_bar_ready', A],
    ['save_fleet_bar_pos', A, 20, 30, 'begin'], ['save_fleet_bar_pos', A, 20, 30, 'end', 1]
  ]);
  await settle(p.calls('save_fleet_bar_pos')[1]);
  assert.deepEqual(p.errors, []);
});

const invalidFragments = [
  '', '#', '#fleet-page=', fragment('a'.repeat(63)), fragment('a'.repeat(65)),
  fragment(A.toUpperCase()), fragment('g'.repeat(64)), '#Fleet-page=' + A,
  ' ' + fragment(A), fragment(A) + ' ', fragment(A) + '\n', fragment(A) + '\r\n',
  fragment(A) + '&other=value', fragment(A) + '#extra',
  fragment(A) + '&fleet-page=' + B, '#other=value&fleet-page=' + A,
  fragment('%61' + 'a'.repeat(63))
];
for (const hash of invalidFragments) {
  test(`invalid fragment ${JSON.stringify(hash)} never calls the bridge or upgrades after mutation`, async () => {
    const p = await page({ hash, bridgeReady: false });
    p.window.location.hash = fragment(B);
    await p.attachBridge();
    await settle(p.fonts);
    await p.push(snapshot());
    await p.resize(480);
    await p.advance(650);
    await p.mouseup();
    assertRendered(p);
    assert.deepEqual(p.log(), []);
    assert.deepEqual(p.errors, []);
  });
}

test('invalid identity resolves null without waiting for a bridge that never arrives', async () => {
  const p = await page({ hash: '', bridgeReady: false });
  let finished = false;
  p.window.onFleetSnapshot(snapshot()).then(value => {
    assert.equal(value, null);
    finished = true;
  });
  await flush();
  assert.equal(finished, true);
  assert.deepEqual(p.log(), []);
});

for (const outcome of ['null', 'reject']) {
  test(`${outcome} hydration still waits for fonts then sends ready without a positive fit acknowledgement`, async () => {
    const p = await page();
    const read = p.calls('fleet_bar_snapshot')[0];
    if (outcome === 'null') await settle(read);
    else await fail(read);
    assert.equal(p.calls('fleet_bar_ready').length, 0);
    await settle(p.fonts);
    assert.deepEqual(p.log(), [['fleet_bar_snapshot', A], ['fleet_bar_ready', A]]);
    assert.equal(p.el('fleet-rows').children.length, 0);
    await settle(p.calls('fleet_bar_ready')[0], true);
    assert.deepEqual(p.errors.map(error => error[0]),
                     outcome === 'reject' ? ['bridge: fleet_bar_snapshot failed'] : []);
  });
}

for (const fitOutcome of ['null', 'reject']) {
  test(`${fitOutcome} height fit still reaches token-bound ready`, async () => {
    const p = await page();
    await settle(p.fonts);
    await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
    assert.equal(p.calls('fleet_bar_ready').length, 0);
    const fit = p.calls('fit_fleet_bar_height')[0];
    assert.deepEqual(fit.args, [A, 114]);
    if (fitOutcome === 'null') await settle(fit);
    else await fail(fit);
    assert.deepEqual(p.calls('fleet_bar_ready')[0].args, [A]);
    await settle(p.calls('fleet_bar_ready')[0], true);
    assertRendered(p);
    const expectedErrors = [];
    if (fitOutcome === 'reject') expectedErrors.push('bridge: fit_fleet_bar_height failed');
    assert.deepEqual(p.errors.map(error => error[0]), expectedErrors);
  });
}

test('initial and telemetry renders call only height fit; telemetry never persists width', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot(1, 'First'));
  assertRendered(p, 'First');
  assert.deepEqual(p.calls('fit_fleet_bar_height')[0].args, [A, 114]);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 0);
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);
  p.shell.offsetHeight = 166;
  await p.push(snapshot(2, 'Second'));
  assertRendered(p, 'Second');
  assert.deepEqual(p.calls('fit_fleet_bar_height')[1].args, [A, 166]);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 0);
  assert.deepEqual(p.errors, []);
});

test('programmatic feedback preserves a session-only warning and native resizing polls until complete', async () => {
  const p = await page();
  await p.resize(620);
  await p.advance(150);
  const warning = 'The Fleet Bar width changed, but it will not survive restart.';
  await settle(p.calls('settle_fleet_bar_resize')[0], { applied: true, persisted: false, error: warning });
  await p.resize(588);
  await p.advance(150);
  await settle(p.calls('settle_fleet_bar_resize')[1], { status: 'ignored' });
  assert.equal(p.el('fleet-title-error').textContent, warning);
  await p.resize(500);
  await p.advance(150);
  await settle(p.calls('settle_fleet_bar_resize')[2], { status: 'resizing' });
  assert.equal(p.el('fleet-title-error').textContent, warning);
  await p.advance(149);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 3);
  await p.advance(1);
  assert.deepEqual(p.calls('settle_fleet_bar_resize')[3].args, [A, 500, 20]);
  await settle(p.calls('settle_fleet_bar_resize')[3], { applied: true, persisted: true, error: null });
  assert.equal(p.el('fleet-title-error').hidden, true);
  await p.advance(450);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 4, 'completion stops polling');
});

for (const ignoredFirst of [false, true]) {
  test('clamp feedback before the width reply retains its actual outcome; ignored first=' + ignoredFirst, async () => {
    const p = await page();
    await p.resize(720);
    await p.advance(150);
    const submitted = p.calls('settle_fleet_bar_resize')[0];
    assert.deepEqual(submitted.args, [A, 720, 20]);
    // Python's clamp can emit this viewport event before its save reply.
    await p.resize(588);
    if (ignoredFirst) {
      await p.advance(150);
      await settle(p.calls('settle_fleet_bar_resize')[1], { status: 'ignored' });
    }
    await settle(submitted, { applied: true, persisted: false, error: 'Width is session-only' });
    assert.equal(p.el('fleet-title-error').textContent, 'Width is session-only');
    if (!ignoredFirst) {
      await p.advance(150);
      await settle(p.calls('settle_fleet_bar_resize')[1], { status: 'ignored' });
    }
    assert.equal(p.el('fleet-title-error').textContent, 'Width is session-only');
  });
}

for (const result of [
  { applied: true, persisted: true, error: null },
  { applied: false, persisted: false, error: 'New refusal' }
]) {
  test('newer authoritative resize feedback supersedes delayed width outcome: ' + JSON.stringify(result), async () => {
    const p = await page();
    await p.resize(720);
    await p.advance(150);
    const old = p.calls('settle_fleet_bar_resize')[0];
    await p.resize(620);
    await p.advance(150);
    await settle(p.calls('settle_fleet_bar_resize')[1], result);
    await settle(old, { applied: true, persisted: false, error: 'Obsolete warning' });
    assert.equal(p.el('fleet-title-error').textContent, result.error || '');
  });
}

for (const warningWhen of ['before-status', 'after-status', 'after-end']) {
  test('actual customize position-only header status cannot retire delayed width failure: ' + warningWhen, async () => {
    const p = await page();
    await p.resize(720);
    await p.advance(150);
    const first = p.calls('settle_fleet_bar_resize')[0];
    await p.resize(588);
    await p.advance(150);
    const corrective = p.calls('settle_fleet_bar_resize')[1];
    // The corrective call is pending when header begin reaches the API.
    await p.mousedown();
    await settle(p.calls('save_fleet_bar_pos')[0], { status: 'dragging', drag_id: 17 });
    await p.mousemove(200, 240);
    assert.deepEqual(p.nativeMoves, [[200, 240]]);
    const warning = { applied: true, persisted: false, error: 'Width is session-only' };
    if (warningWhen === 'before-status') await settle(first, warning);
    await settle(corrective, { status: 'resizing' });
    if (warningWhen === 'after-status') await settle(first, warning);
    await p.mouseup();
    assert.deepEqual(p.calls('save_fleet_bar_pos')[1].args, [A, 200, 240, 'end', 17]);
    await settle(p.calls('save_fleet_bar_pos')[1]);
    await p.advance(150);
    await settle(p.calls('settle_fleet_bar_resize')[2], { status: 'ignored' });
    if (warningWhen === 'after-end') await settle(first, warning);
    assert.equal(p.el('fleet-title-error').textContent, 'Width is session-only');
    assert.deepEqual(p.errors, []);
  });
}

test('a native gesture that ends without a field outcome cannot discard an earlier width failure', async () => {
  const p = await page();
  await p.resize(720);
  await p.advance(150);
  const first = p.calls('settle_fleet_bar_resize')[0];
  await p.resize(620);
  await p.advance(150);
  await settle(p.calls('settle_fleet_bar_resize')[1], { status: 'resizing' });
  await p.advance(150);
  await settle(p.calls('settle_fleet_bar_resize')[2], { status: 'ignored' });
  await settle(first, { applied: true, persisted: false, error: 'Width is session-only' });
  assert.equal(p.el('fleet-title-error').textContent, 'Width is session-only');
});

test('an unproven resize event does not discard actual successful width persistence', async () => {
  const p = await page();
  await p.resize(620);
  await p.advance(150);
  await settle(p.calls('settle_fleet_bar_resize')[0], {
    applied: true, persisted: false, error: 'Session-only width'
  });
  await p.resize(600);
  await p.advance(150);
  const old = p.calls('settle_fleet_bar_resize')[1];
  await p.resize(500);
  await settle(old, { applied: true, persisted: true, error: null });
  assert.equal(p.el('fleet-title-error').textContent, '');
  await p.advance(149);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 2);
  await p.advance(1);
  await settle(p.calls('settle_fleet_bar_resize')[2], { status: 'ignored' });
  assert.equal(p.el('fleet-title-error').textContent, '');
});

for (const [id, method] of [['fleet-reset-width', 'reset_fleet_bar_page_width'], ['fleet-hide', 'hide_fleet_bar']]) {
  test(id + ' owns feedback over an older resize reply and cancels its poll', async () => {
    const p = await page();
    await p.resize(620);
    await p.advance(150);
    const old = p.calls('settle_fleet_bar_resize')[0];
    await p.pointerdown(id);
    await p.click(id);
    await settle(p.calls('activate_fleet_bar')[0], true);
    await settle(p.calls(method)[0], { applied: true, persisted: false, error: 'Action stayed session-only' });
    await settle(old, { status: 'resizing' });
    await p.advance(450);
    assert.equal(p.calls('settle_fleet_bar_resize').length, 1);
    assert.equal(p.el('fleet-title-error').textContent, 'Action stayed session-only');
  });
}

for (const [id, method] of [['fleet-reset-width', 'reset_fleet_bar_page_width'], ['fleet-hide', 'hide_fleet_bar']]) {
  test(id + ' actual result owns feedback over an older failed width save', async () => {
    const p = await page();
    await p.resize(720);
    await p.advance(150);
    const old = p.calls('settle_fleet_bar_resize')[0];
    await p.pointerdown(id);
    await p.click(id);
    await settle(p.calls('activate_fleet_bar')[0], true);
    await settle(p.calls(method)[0], { applied: true, persisted: true, error: null });
    await settle(old, { applied: true, persisted: false, error: 'Obsolete width warning' });
    assert.equal(p.el('fleet-title-error').textContent, '');
    await p.advance(450);
    assert.equal(p.calls('settle_fleet_bar_resize').length, 1);
  });
}

test('resize bursts coalesce for 150ms and native provenance decides even a one-pixel report', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);
  await p.advance(500);
  await settle(p.calls('fit_fleet_bar_height')[1]);

  await p.resize(500);
  await p.advance(149);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 0);
  await p.resize(530);
  await p.advance(149);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 0);
  await p.resize(531);
  await p.advance(149);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 0);
  await p.advance(1);
  assert.deepEqual(p.calls('settle_fleet_bar_resize')[0].args, [A, 531, 20]);
  await settle(p.calls('settle_fleet_bar_resize')[0], { applied: true, persisted: true, error: null });
  await p.resize(530);
  await p.advance(150);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 2);
  await settle(p.calls('settle_fleet_bar_resize')[1], { status: 'ignored' });
  assert.equal(p.el('fleet-title-error').hidden, true);
  assert.deepEqual(p.errors, []);
});

test('resize settlement rejection shows a generic failure and keeps the previous baseline', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);
  await p.advance(500);
  await settle(p.calls('fit_fleet_bar_height')[1]);

  await p.resize(531);
  await p.advance(150);
  assert.deepEqual(p.calls('settle_fleet_bar_resize')[0].args, [A, 531, 20]);
  await fail(p.calls('settle_fleet_bar_resize')[0]);
  assert.equal(p.el('fleet-title-error').textContent, 'The Fleet Bar could not be resized.');

  await p.resize(530);
  await p.advance(150);
  assert.deepEqual(p.calls('settle_fleet_bar_resize').map(call => call.args), [
    [A, 531, 20],
    [A, 530, 20]
  ]);
  assert.deepEqual(p.errors.map(error => error[0]), ['bridge: settle_fleet_bar_resize failed']);
});

test('returning to the accepted baseline still admits a fresh native gesture and supersedes older replies', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);
  await p.advance(500);
  await settle(p.calls('fit_fleet_bar_height')[1]);
  const fits = p.calls('fit_fleet_bar_height').length;

  await p.resize(480);
  await p.advance(150);
  assert.deepEqual(p.calls('settle_fleet_bar_resize')[0].args, [A, 480, 20]);

  await p.resize(420);
  p.shell.offsetHeight = 190;
  await p.push(snapshot(2, 'Back at baseline'));
  assertRendered(p, 'Back at baseline');
  assert.equal(p.calls('fit_fleet_bar_height').length, fits, 'fit still waits while baseline return is pending');

  await p.advance(150);
  assert.equal(p.calls('settle_fleet_bar_resize').length, 2, 'baseline equality must not swallow genuine native intent');
  assert.deepEqual(p.calls('settle_fleet_bar_resize')[1].args, [A, 420, 20]);
  await settle(p.calls('settle_fleet_bar_resize')[1], { applied: true, persisted: true, error: null });
  assert.equal(p.calls('fit_fleet_bar_height').length, fits + 1, 'latest native settlement drains the deferred fit');
  assert.deepEqual(p.calls('fit_fleet_bar_height')[fits].args, [A, 190]);

  await settle(p.calls('settle_fleet_bar_resize')[0], { applied: true, persisted: true, error: null });
  assert.equal(p.calls('fit_fleet_bar_height').length, fits + 1, 'stale reply must not drain fit again');

  await p.resize(479);
  await p.advance(150);
  assert.deepEqual(p.calls('settle_fleet_bar_resize').map(call => call.args), [
    [A, 480, 20],
    [A, 420, 20],
    [A, 479, 20]
  ]);
  assert.deepEqual(p.errors, []);
});

test('fit pauses until the latest overlapping resize settlement completes', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);
  await p.advance(500);
  await settle(p.calls('fit_fleet_bar_height')[1]);
  const fits = p.calls('fit_fleet_bar_height').length;

  await p.resize(480);
  await p.advance(150);
  assert.deepEqual(p.calls('settle_fleet_bar_resize')[0].args, [A, 480, 20]);

  await p.resize(500);
  p.shell.offsetHeight = 190;
  await p.push(snapshot(2, 'While resizing'));
  assertRendered(p, 'While resizing');
  assert.equal(p.calls('fit_fleet_bar_height').length, fits, 'fit still waits while the second settle is pending');
  await p.advance(150);
  assert.deepEqual(p.calls('settle_fleet_bar_resize')[1].args, [A, 500, 20]);

  await settle(p.calls('settle_fleet_bar_resize')[0], { applied: true, persisted: true, error: null });
  assert.equal(p.calls('fit_fleet_bar_height').length, fits, 'older replies cannot drain deferred fit');

  await settle(p.calls('settle_fleet_bar_resize')[1], { applied: true, persisted: true, error: null });
  assert.deepEqual(p.calls('fit_fleet_bar_height')[fits].args, [A, 190]);
  assert.deepEqual(p.errors, []);
});

test('fit pauses during resizing and resumes once after settlement', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);
  await p.advance(500);
  await settle(p.calls('fit_fleet_bar_height')[1]);
  const fits = p.calls('fit_fleet_bar_height').length;

  await p.resize(480);
  p.shell.offsetHeight = 190;
  await p.push(snapshot(2, 'While resizing'));
  assertRendered(p, 'While resizing');
  assert.equal(p.calls('fit_fleet_bar_height').length, fits, 'fit waits for resize settlement');
  await p.advance(150);
  assert.deepEqual(p.calls('settle_fleet_bar_resize')[0].args, [A, 480, 20]);
  assert.equal(p.calls('fit_fleet_bar_height').length, fits, 'fit still waits for the settle reply');
  await settle(p.calls('settle_fleet_bar_resize')[0], { applied: true, persisted: true, error: null });
  assert.deepEqual(p.calls('fit_fleet_bar_height')[fits].args, [A, 190]);
  assert.deepEqual(p.errors, []);
});

test('table keyboard traversal reaches Reset then Hide and reveals the action region on focus', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);

  p.el('fleet-table').focus();
  assert.equal(p.document.activeElement, p.el('fleet-table'));
  assert.equal(p.actionsVisible(), false);
  await p.tab();
  assert.equal(p.document.activeElement, p.el('fleet-reset-width'));
  assert.equal(p.actionsVisible(), true);
  await p.tab();
  assert.equal(p.document.activeElement, p.el('fleet-hide'));
  assert.equal(p.actionsVisible(), true);
  assert.deepEqual(p.errors, []);
});

test('pointerdown activates before Reset width and Reset retains activation until Escape', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);

  await p.pointerdown('fleet-reset-width');
  assert.deepEqual(p.calls('activate_fleet_bar')[0].args, [A]);
  await p.click('fleet-reset-width');
  assert.equal(p.calls('reset_fleet_bar_page_width').length, 0);
  await settle(p.calls('activate_fleet_bar')[0], true);
  assert.equal(p.document.activeElement, p.el('fleet-reset-width'));
  assert.deepEqual(p.calls('reset_fleet_bar_page_width')[0].args, [A]);
  await settle(p.calls('reset_fleet_bar_page_width')[0], { applied: true, persisted: true, error: null });
  assert.equal(p.calls('deactivate_fleet_bar').length, 0);
  await p.keydown('Escape');
  assert.deepEqual(p.calls('deactivate_fleet_bar')[0].args, [A]);
  assert.deepEqual(p.errors, []);
});

test('activation failure shows the main-window fallback and does not change header height', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);
  const before = p.el('fleet-title').offsetHeight;

  await p.pointerdown('fleet-reset-width');
  await p.click('fleet-reset-width');
  await settle(p.calls('activate_fleet_bar')[0], false);
  assert.equal(p.calls('reset_fleet_bar_page_width').length, 0);
  assert.equal(p.el('fleet-title-error').hidden, false);
  assert.match(p.el('fleet-title-error').textContent, /main window/i);
  assert.equal(p.el('fleet-title').offsetHeight, before);
  assert.equal(p.document.activeElement, null);
  assert.deepEqual(p.errors, []);
});

test('blur deactivates an explicit activation session', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);

  await p.pointerdown('fleet-reset-width');
  await settle(p.calls('activate_fleet_bar')[0], true);
  assert.equal(p.document.activeElement, p.el('fleet-reset-width'));
  await p.blur();
  assert.deepEqual(p.calls('deactivate_fleet_bar')[0].args, [A]);
  assert.deepEqual(p.errors, []);
});

test('Hide uses only the token-bound endpoint and action errors do not change header height', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(p.calls('fit_fleet_bar_height')[0]);
  await settle(p.calls('fleet_bar_ready')[0], true);
  const before = p.el('fleet-title').offsetHeight;

  await p.pointerdown('fleet-hide');
  await p.click('fleet-hide');
  assert.equal(p.calls('hide_fleet_bar').length, 0);
  await settle(p.calls('activate_fleet_bar')[0], true);
  assert.deepEqual(p.calls('hide_fleet_bar')[0].args, [A]);
  assert.equal(p.calls('deactivate_fleet_bar').length, 0);
  await settle(p.calls('hide_fleet_bar')[0], {
    applied: false,
    persisted: false,
    error: 'Could not save the Fleet Bar setting.'
  });
  assert.equal(p.el('fleet-title-error').hidden, false);
  assert.equal(p.el('fleet-title-error').textContent, 'Could not save the Fleet Bar setting.');
  assert.equal(p.el('fleet-title').offsetHeight, before);
  assert.deepEqual(p.errors, []);
});

for (const [id, method, message] of [
  ['fleet-reset-width', 'reset_fleet_bar_page_width', 'Could not reset Fleet Bar width.'],
  ['fleet-hide', 'hide_fleet_bar', 'Could not hide the Fleet Bar.']
]) {
  test(id + ' null result shows a generic action failure', async () => {
    const p = await page();
    await settle(p.fonts);
    await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
    await settle(p.calls('fit_fleet_bar_height')[0]);
    await settle(p.calls('fleet_bar_ready')[0], true);

    await p.pointerdown(id);
    await p.click(id);
    await settle(p.calls('activate_fleet_bar')[0], true);
    assert.deepEqual(p.calls(method)[0].args, [A]);
    await settle(p.calls(method)[0]);

    assert.equal(p.el('fleet-title-error').textContent, message);
    assert.deepEqual(p.errors, []);
  });
}

test('actual pywebview customize drag moves independently while header ownership brackets save and fit', async () => {
  const p = await page({ x: -700, y: -80 });
  await p.mousedown();
  assert.deepEqual(p.calls('save_fleet_bar_pos')[0].args, [A, -700, -80, 'begin']);
  await p.mousemove(-620, -40);
  assert.deepEqual(p.nativeMoves, [[-620, -40]], 'real customize.js still owns native movement');
  await p.push(snapshot(2, 'While dragging'));
  await p.advance(1200);
  assert.equal(p.calls('fit_fleet_bar_height').length, 0);
  assert.equal(p.calls('activate_fleet_bar').length, 0);
  assert.equal(p.calls('deactivate_fleet_bar').length, 0);
  await p.mouseup();
  await p.mousemove(-500, 0);
  assert.deepEqual(p.nativeMoves, [[-620, -40]], 'customize.js removed its move listener on release');
  assert.equal(p.calls('save_fleet_bar_pos').length, 1, 'end waits for begin admission');
  await settle(p.calls('save_fleet_bar_pos')[0], { status: 'dragging', drag_id: 17 });
  assert.deepEqual(p.calls('save_fleet_bar_pos')[1].args, [A, -620, -40, 'end', 17]);
  await settle(p.calls('save_fleet_bar_pos')[1], { applied: true, persisted: false, error: 'Width stayed session-only' });
  await p.advance(150);
  await settle(p.calls('settle_fleet_bar_resize')[0], { status: 'ignored' });
  assert.equal(p.el('fleet-title-error').textContent, 'Width stayed session-only');
  assert.equal(p.calls('fit_fleet_bar_height').length, 1);
});

for (const settledBeforeDrag of [false, true]) {
  test('actual customize resize-to-header drag ' + (settledBeforeDrag ? 'after' : 'before') + ' 150ms settlement preserves the latest owner', async () => {
    const p = await page();
    await p.resize(620);
    if (settledBeforeDrag) {
      await p.advance(150);
      await settle(p.calls('settle_fleet_bar_resize')[0], { applied: true, persisted: true, error: null });
    }
    const fits = p.calls('fit_fleet_bar_height').length;
    await p.mousedown();
    await settle(p.calls('save_fleet_bar_pos')[0], { status: 'dragging', drag_id: 8 });
    await p.mousemove(100, 120);
    await p.advance(1500);
    assert.equal(p.calls('fit_fleet_bar_height').length, fits);
    assert.equal(p.calls('settle_fleet_bar_resize').length, settledBeforeDrag ? 1 : 0);
    await p.mouseup();
    assert.deepEqual(p.nativeMoves, [[100, 120]]);
    assert.deepEqual(p.calls('save_fleet_bar_pos')[1].args, [A, 100, 120, 'end', 8]);
    await settle(p.calls('save_fleet_bar_pos')[1], settledBeforeDrag ? null : { applied: true, persisted: true, error: null });
    await p.advance(150);
    await settle(p.calls('settle_fleet_bar_resize').at(-1), { status: 'ignored' });
    assert.equal(p.calls('fit_fleet_bar_height').length, fits + 1);
    assert.equal(p.el('fleet-title-error').hidden, true);
  });
}

test('two actual customize drags serialize bridge ownership despite delayed first end', async () => {
  const p = await page();
  await p.mousedown();
  await p.mousemove(100, 120);
  await p.mouseup();
  await p.mousedown();
  await p.mousemove(200, 240);
  await p.mouseup();
  assert.deepEqual(p.nativeMoves, [[100, 120], [200, 240]]);
  assert.equal(p.calls('save_fleet_bar_pos').length, 1);
  await settle(p.calls('save_fleet_bar_pos')[0], { status: 'dragging', drag_id: 1 });
  assert.deepEqual(p.calls('save_fleet_bar_pos')[1].args, [A, 100, 120, 'end', 1]);
  await settle(p.calls('save_fleet_bar_pos')[1], { applied: true, persisted: false, error: 'Old warning' });
  assert.equal(p.el('fleet-title-error').textContent, 'Old warning', 'a later position-only drag did not persist the failed width');
  assert.deepEqual(p.calls('save_fleet_bar_pos')[2].args, [A, 100, 120, 'begin']);
  await settle(p.calls('save_fleet_bar_pos')[2], { status: 'dragging', drag_id: 2 });
  assert.deepEqual(p.calls('save_fleet_bar_pos')[3].args, [A, 200, 240, 'end', 2]);
  await settle(p.calls('save_fleet_bar_pos')[3]);
  assert.equal(p.el('fleet-title-error').textContent, 'Old warning');
});

test('non-header mouse input and header clicks do not claim width persistence or clear its warning', async () => {
  const p = await page();
  await p.resize(620);
  await p.advance(150);
  await settle(p.calls('settle_fleet_bar_resize')[0], { applied: true, persisted: false, error: 'Unsaved width' });
  for (const id of ['fleet-table', 'fleet-reset-width', 'fleet-hide']) {
    await p.mousedown(id);
    await p.mousemove(100, 200);
    await p.mouseup();
  }
  assert.deepEqual(p.nativeMoves, []);
  assert.equal(p.calls('save_fleet_bar_pos').length, 0);
  await p.mousedown();
  await settle(p.calls('save_fleet_bar_pos')[0], { status: 'dragging', drag_id: 5 });
  await p.mouseup();
  await settle(p.calls('save_fleet_bar_pos')[1]);
  assert.equal(p.el('fleet-title-error').textContent, 'Unsaved width');
  assert.equal(p.calls('activate_fleet_bar').length, 0);
});

for (const [id, method] of [['fleet-reset-width', 'reset_fleet_bar_page_width'], ['fleet-hide', 'hide_fleet_bar']]) {
  test(id + ' follows queued header admission and supersedes stale end feedback', async () => {
    const p = await page();
    await p.mousedown();
    await p.mousemove(100, 120);
    await p.mouseup();
    await p.pointerdown(id);
    await p.click(id);
    await settle(p.calls('activate_fleet_bar')[0], true);
    assert.equal(p.calls(method).length, 0, 'geometry action waits for the admitted header chain');
    await settle(p.calls('save_fleet_bar_pos')[0], { status: 'dragging', drag_id: 7 });
    await settle(p.calls('save_fleet_bar_pos')[1], { applied: true, persisted: false, error: 'Obsolete drag error' });
    assert.equal(p.el('fleet-title-error').textContent, '', 'stale drag feedback is superseded immediately');
    assert.equal(p.calls(method).length, 1);
    await settle(p.calls(method)[0], { applied: true, persisted: false, error: 'Current action warning' });
    await p.advance(600);
    assert.equal(p.el('fleet-title-error').textContent, 'Current action warning');
    assert.equal(p.calls('settle_fleet_bar_resize').length, 0, 'old drag completion did not rearm resize polling');
  });
}

for (const oldReply of ['older snapshot', 'null', 'reject']) {
  test(`newer push survives a delayed ${oldReply} hydration reply`, async () => {
    const p = await page();
    await settle(p.fonts);
    await p.push(snapshot(5, 'Latest'));
    assertRendered(p, 'Latest');
    const read = p.calls('fleet_bar_snapshot')[0];
    if (oldReply === 'reject') await fail(read);
    else await settle(read, oldReply === 'null' ? null : snapshot(4, 'Old'));
    assertRendered(p, 'Latest');
    assert.equal(p.calls('fit_fleet_bar_height').length, 1, 'discarded hydration cannot refit');
    assert.deepEqual(p.calls('fit_fleet_bar_height')[0].args, [A, 114]);
    assert.deepEqual(p.calls('fleet_bar_ready')[0].args, [A]);
    await settle(p.calls('fit_fleet_bar_height')[0]);
    await settle(p.calls('fleet_bar_ready')[0], true);
    assert.deepEqual(p.errors.map(error => error[0]),
                     oldReply === 'reject' ? ['bridge: fleet_bar_snapshot failed'] : []);
  });
}

test('revision zero and equal revisions render; stale and malformed revisions leave state and fit count intact', async () => {
  const p = await page();
  await p.push(snapshot(0, 'First'));
  assertRendered(p, 'First');
  await p.push(snapshot(0, 'Equal'));
  assertRendered(p, 'Equal');
  await p.push(snapshot(7, 'Latest'));
  assertRendered(p, 'Latest');
  const fits = p.calls('fit_fleet_bar_height').length;
  assert.equal(fits, 3);
  for (const revision of [6, undefined, null, '8', -1, 1.5, NaN, Infinity, -Infinity]) {
    const invalid = snapshot(1, 'Invalid');
    invalid.revision = revision;
    assert.equal(await p.window.onFleetSnapshot(invalid), null);
    assertRendered(p, 'Latest');
    assert.equal(p.calls('fit_fleet_bar_height').length, fits);
  }
  assert.deepEqual(p.errors, []);
});

test('missing FontFaceSet preserves hydration, height fit and ready ordering', async () => {
  const p = await page({ fonts: false });
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  assertRendered(p);
  assert.equal(p.calls('fleet_bar_ready').length, 0);
  await settle(p.calls('fit_fleet_bar_height')[0]);
  assert.deepEqual(p.log(), [
    ['fleet_bar_snapshot', A], ['fit_fleet_bar_height', A, 114], ['fleet_bar_ready', A]
  ]);
  assert.deepEqual(p.errors, []);
});

test('same-URL reload shares creation identity: no document-epoch isolation is promised', async () => {
  const old = await page();
  await settle(old.fonts);
  await settle(old.calls('fleet_bar_snapshot')[0], snapshot());
  const reloaded = await page({ hash: old.window.location.hash });
  await settle(reloaded.fonts);
  await settle(reloaded.calls('fleet_bar_snapshot')[0], snapshot());
  await settle(reloaded.calls('fit_fleet_bar_height')[0]);
  await settle(old.calls('fit_fleet_bar_height')[0]);
  for (const p of [old, reloaded]) {
    assert.deepEqual(p.log(), [
      ['fleet_bar_snapshot', A], ['fit_fleet_bar_height', A, 114], ['fleet_bar_ready', A]
    ]);
    await settle(p.calls('fleet_bar_ready')[0], true);
    assert.deepEqual(p.errors, []);
  }
});

// -- Split Damage rendering: independent OUT/IN rails, mixed-null
// unavailable, zero, >10m, EWAR, accessibility. --
//
// Two independent payloads, not one: a normal-range payload (Alice, Bravo,
// No Log) owns the exact independent-ratio assertions, and a separate
// defensive payload (Huge alone) owns the >10m / accessible-phrase
// assertions. A single combined payload would make Huge's 10,000,001 the
// normalization maximum and break the Alice/Bravo ratio expectations below.

const NORMAL_ROWS = [
  { character: 'Alice', outgoing_dps: 100, incoming_dps: 50, ewar: ['SCRAM'], log_status: null },
  { character: 'Bravo', outgoing_dps: 25, incoming_dps: 200, ewar: [], log_status: null },
  { character: 'No Log', outgoing_dps: null, incoming_dps: null, ewar: [], log_status: 'NO LOG' }
];

test('normal-range payload: OUT/IN DOM order, independent ratios, exact values', async () => {
  const p = await page();
  await p.push({
    revision: 1, rows: NORMAL_ROWS, running_count: 3,
    stream_health: { state: 'active' }
  });
  const rows = p.el('fleet-rows').children;
  assert.equal(rows.length, 3);

  const alice = rows[0].children[1];
  const bravo = rows[1].children[1];
  assert.equal(alice.getAttribute('role'), 'cell');

  // DOM contract: OUT half, axis, IN half, in that order, inside one cell.
  assert.equal(alice.children.length, 3);
  const [aliceOut, aliceAxis, aliceIn] = alice.children;
  assert.equal(aliceOut.className.indexOf('fleet-damage-out'), 0);
  assert.equal(aliceAxis.className, 'fleet-damage-axis');
  assert.equal(aliceIn.className.indexOf('fleet-damage-in'), 0);

  const [bravoOut, , bravoIn] = bravo.children;

  // Alice is the outgoing maximum (100 of max(100, 25)) -> ratio 1.
  assert.equal(fillOf(aliceOut).style.transform, 'scaleX(1)');
  assert.equal(valueOf(aliceOut).textContent, '100');
  // Bravo's outgoing (25) is a quarter of the outgoing maximum (100).
  assert.equal(fillOf(bravoOut).style.transform, 'scaleX(0.25)');
  assert.equal(valueOf(bravoOut).textContent, '25');

  // Alice's incoming (50) is a quarter of the incoming maximum (200).
  assert.equal(fillOf(aliceIn).style.transform, 'scaleX(0.25)');
  assert.equal(valueOf(aliceIn).textContent, '50');
  // Bravo is the incoming maximum (200 of max(50, 200)) -> ratio 1.
  assert.equal(fillOf(bravoIn).style.transform, 'scaleX(1)');
  assert.equal(valueOf(bravoIn).textContent, '200');

  // Positive IN shares --warn; OUT never does, regardless of magnitude.
  assert.ok(aliceIn.classList.contains('warn'));
  assert.ok(!aliceOut.classList.contains('warn'));
  assert.ok(!bravoOut.classList.contains('warn'));

  // Named accessible descriptions: exact numbers, no character name inside.
  assert.equal(alice.getAttribute('aria-label'), 'Outgoing 100 DPS, incoming 50 DPS');
  assert.equal(bravo.getAttribute('aria-label'), 'Outgoing 25 DPS, incoming 200 DPS');
  assert.ok(rows[0].classList.contains('threat'));
  assert.ok(rows[0].classList.contains('ewar-threat'));
  assert.ok(rows[1].classList.contains('threat'));
  assert.ok(!rows[1].classList.contains('ewar-threat'));
  assert.ok(!rows[2].classList.contains('threat'));
  assert.ok(!rows[2].classList.contains('ewar-threat'));

  // Bravo's empty EWAR list is the neutral "zero" case: a dash, not warm.
  const bravoEwar = rows[1].children[2];
  assert.equal(bravoEwar.getAttribute('role'), 'cell');
  assert.equal(bravoEwar.textContent, '\u2014');
  assert.ok(!bravoEwar.classList.contains('active'));
  // Alice's EWAR remains the following cell, unaffected by the Damage split.
  const aliceEwar = rows[0].children[2];
  assert.equal(aliceEwar.textContent, 'SCRAM');
  assert.ok(aliceEwar.classList.contains('active'));

  // No Log: a single unavailable Damage cell, neutral, named by log_status.
  const noLog = rows[2].children[1];
  assert.equal(noLog.children.length, 1);
  assert.ok(noLog.classList.contains('unavailable'));
  assert.ok(!noLog.classList.contains('warn'));
  assert.equal(noLog.getAttribute('aria-label'), 'NO LOG');
  assert.equal(noLog.textContent, 'NO LOG');
  const noLogEwar = rows[2].children[2];
  assert.equal(noLogEwar.textContent, '\u2014');
});

const DEFENSIVE_ROWS = [
  {
    character: 'Huge', outgoing_dps: 10000001, incoming_dps: 10000001,
    ewar: ['SCRAM', 'POINT', 'NEUT'], log_status: null
  }
];

test('defensive payload: values beyond ten million collapse to >10m and the accessible phrase', async () => {
  const p = await page();
  await p.push({
    revision: 1, rows: DEFENSIVE_ROWS, running_count: 1,
    stream_health: { state: 'active' }
  });
  const rows = p.el('fleet-rows').children;
  assert.equal(rows.length, 1);
  const huge = rows[0].children[1];
  const [hugeOut, , hugeIn] = huge.children;

  assert.equal(valueOf(hugeOut).textContent, '>10m');
  assert.equal(valueOf(hugeIn).textContent, '>10m');
  // Sole row: it is its own maximum, so the rail still reaches full scale.
  assert.equal(fillOf(hugeOut).style.transform, 'scaleX(1)');
  assert.equal(fillOf(hugeIn).style.transform, 'scaleX(1)');
  assert.equal(
    huge.getAttribute('aria-label'),
    'Outgoing more than 10 million DPS, incoming more than 10 million DPS'
  );

  const ewar = rows[0].children[2];
  assert.equal(ewar.textContent, 'SCRAM \u00b7 POINT \u00b7 NEUT');
});

const MIXED_NULL_ROWS = [
  { character: 'Charlie', outgoing_dps: 43, incoming_dps: null, ewar: [], log_status: null }
];

test('mixed-null payload without log_status: each direction renders independently', async () => {
  const p = await page();
  await p.push({
    revision: 1, rows: MIXED_NULL_ROWS, running_count: 1,
    stream_health: { state: 'active' }
  });
  const rows = p.el('fleet-rows').children;
  const charlie = rows[0].children[1];
  const [charlieOut, , charlieIn] = charlie.children;

  // Numeric OUT renders and fills normally.
  assert.equal(valueOf(charlieOut).textContent, '43');
  assert.ok(charlieOut.classList.contains('live'));

  // Missing IN is unavailable, not a measured zero: em dash, no fill, no warn.
  assert.equal(valueOf(charlieIn).textContent, '\u2014');
  assert.equal(fillOf(charlieIn).style.transform, 'scaleX(0)');
  assert.ok(!charlieIn.classList.contains('warn'));

  assert.equal(
    charlie.getAttribute('aria-label'),
    'Outgoing 43 DPS, incoming unavailable'
  );
  assert.ok(!rows[0].classList.contains('threat'));
  assert.ok(!rows[0].classList.contains('ewar-threat'));
});

test('remote rows keep incoming unknown, include live values in maxima, and clear stale threat and rails truthfully', async () => {
  const p = await page();
  const remote = {
    character: 'Remote pilot', outgoing_dps: 400, incoming_dps: null,
    ewar: ['SCRAM/POINT'], log_status: null, remote: true, state: 'live'
  };
  await p.push({ revision: 1, rows: NORMAL_ROWS.concat([remote]), running_count: 3,
                 stream_health: { state: 'stale' } });
  let rows = p.el('fleet-rows').children;
  assert.equal(p.el('fleet-health').textContent, 'LOCAL STALE');
  assert.equal(fillOf(rows[0].children[1].children[0]).style.transform, 'scaleX(0.25)');
  assert.equal(fillOf(rows[0].children[1].children[2]).style.transform, 'scaleX(0.25)');
  const assertRemote = (line, stale) => {
    const [identity, damage, ewar] = line.children;
    assert.equal(identity.children[1].textContent, stale ? 'REMOTE · STALE' : 'REMOTE');
    assert.equal(damage.getAttribute('aria-label'), 'Outgoing 400 DPS, incoming unavailable');
    assert.equal(damage.classList.contains('unavailable'), false);
    assert.equal(line.classList.contains('threat'), !stale);
    assert.equal(line.classList.contains('ewar-threat'), !stale);
    const [out, , incoming] = damage.children;
    assert.equal(valueOf(out).textContent, '400');
    assert.equal(fillOf(out).style.transform, stale ? 'scaleX(0)' : 'scaleX(1)');
    assert.equal(out.classList.contains('live'), !stale);
    assert.equal(valueOf(incoming).textContent, '—');
    assert.equal(fillOf(incoming).style.transform, 'scaleX(0)');
    assert.equal(incoming.classList.contains('warn'), false);
    assert.equal(ewar.classList.contains('active'), !stale);
    assert.equal(ewar.title, 'SCRAM/POINT');
    assert.equal(ewar.getAttribute('aria-label'), 'Remote tackle: scram or point.');
  };
  assertRemote(rows[3], false);
  await p.push({ revision: 2, rows: [{ ...remote, state: 'stale' }], running_count: 0 });
  assertRemote(p.el('fleet-rows').children[0], true);
  assert.equal(p.table.style.maxHeight, '480px');
  assert.deepEqual(p.errors, []);
});

test('exact ten million stays numeric beside combined EWAR', async () => {
  const p = await page();
  await p.push({
    revision: 1,
    rows: [{
      character: 'Bound', outgoing_dps: 10000000, incoming_dps: 10000000,
      ewar: ['SCRAM', 'POINT', 'NEUT'], log_status: null
    }],
    running_count: 1,
    stream_health: { state: 'active' }
  });
  const row = p.el('fleet-rows').children[0];
  assert.equal(valueOf(row.children[1].children[0]).textContent, '10000000');
  assert.equal(valueOf(row.children[1].children[2]).textContent, '10000000');
  assert.equal(row.children[2].textContent, 'SCRAM · POINT · NEUT');
  assert.ok(row.classList.contains('ewar-threat'));
});

test('health states use the approved Fleet Bar recovery copy', async () => {
  const p = await page();
  await p.push({
    revision: 1, rows: [], running_count: 0,
    stream_health: { state: 'missing_folder', detail: 'ignored' }
  });
  assert.equal(p.el('fleet-note').hidden, false);
  assert.equal(p.el('fleet-note').textContent, 'Set the Gamelog folder in Settings › Alerts.');
  await p.push({
    revision: 2, rows: [], running_count: 0,
    stream_health: { state: 'stale', detail: 'Local log stale' }
  });
  assert.equal(p.el('fleet-note').textContent, 'Gamelogs have stopped updating.');
  await p.push({
    revision: 3, rows: [], running_count: 0,
    stream_health: { state: 'error', detail: 'permission denied' }
  });
  assert.equal(p.el('fleet-note').textContent, 'Gamelogs could not be read.');
});

const ALL_ZERO_ROWS = [
  { character: 'Dana', outgoing_dps: 0, incoming_dps: 0, ewar: [], log_status: null }
];

test('all-zero bound row: numeric zero in both directions, never unavailable', async () => {
  const p = await page();
  await p.push({
    revision: 1, rows: ALL_ZERO_ROWS, running_count: 1,
    stream_health: { state: 'active' }
  });
  const rows = p.el('fleet-rows').children;
  const dana = rows[0].children[1];
  const [danaOut, , danaIn] = dana.children;

  assert.equal(valueOf(danaOut).textContent, '0');
  assert.equal(valueOf(danaIn).textContent, '0');
  assert.equal(fillOf(danaOut).style.transform, 'scaleX(0)');
  assert.equal(fillOf(danaIn).style.transform, 'scaleX(0)');
  assert.ok(!danaOut.classList.contains('live'));
  assert.ok(!danaIn.classList.contains('warn'));

  assert.equal(
    dana.getAttribute('aria-label'),
    'Outgoing 0 DPS, incoming 0 DPS'
  );
});
