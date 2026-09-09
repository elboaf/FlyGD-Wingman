/* Executable Fleet regressions: real fleetbar.js with controlled DOM
 * measurements, bridge continuations, and directional damage rendering --
 * no native/CSS/WebView2 claims.
 *
 * Two families share this one node:test harness: creation-identity (token
 * captured from `#fleet-page=<64 lowercase hex>`, every bridge call bound to
 * it, stale/replaced pages rejected, delayed fit/move/ready continuations
 * keeping identity) and split Damage rendering (independent OUT/IN rails,
 * mixed-null unavailable, zero, >10m, EWAR, accessibility). Do not split
 * this back into two frameworks in one file. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const web = path.join(__dirname, '..', 'wingman', 'web');
const source = fs.readFileSync(path.join(web, 'fleetbar.js'), 'utf8');
const html = fs.readFileSync(path.join(web, 'fleetbar.html'), 'utf8');
const A = '0123456789abcdef'.repeat(4);
const B = 'b'.repeat(64);
const fragment = token => '#fleet-page=' + token;

class EventTarget {
  constructor() { this.listeners = {}; }
  addEventListener(name, fn, options = {}) {
    (this.listeners[name] ||= []).push({ fn, once: options.once });
  }
  dispatchEvent(event) {
    for (const listener of [...(this.listeners[event.type] || [])]) {
      if (listener.once) {
        this.listeners[event.type] = this.listeners[event.type].filter(l => l !== listener);
      }
      listener.fn(event);
    }
  }
}

class Element {
  constructor() {
    this.children = [];
    this.attributes = {};
    this.className = '';
    this.hidden = false;
    this.style = {};
    this.title = '';
    this.text = '';
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
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

// Drain actual promise continuations, without race sleeps or real page timers.
async function flush() { await new Promise(resolve => setImmediate(resolve)); }
async function settle(call, value = null) { call.resolve(value); await flush(); }
async function fail(call) {
  call.reject(new Error('injected bridge rejection'));
  await flush();
}

async function page(options = {}) {
  const nodes = new Map();
  // IDs come from the real document so misspelled lookups cannot invent nodes.
  for (const match of html.matchAll(/\bid="([^"]+)"/g)) {
    nodes.set(match[1], new Element());
  }
  const shell = new Element();
  shell.offsetWidth = options.width ?? 420;
  shell.offsetHeight = options.height ?? 114;
  const document = new EventTarget();
  document.getElementById = id => nodes.get(id) || null;
  document.createElement = () => new Element();
  document.querySelector = selector => selector === '.fleet-shell' ? shell : null;
  const fonts = deferred();
  if (options.fonts !== false) document.fonts = { ready: fonts.promise };
  const calls = [];
  const errors = [];
  const timers = [];
  const api = {};
  for (const method of ['fleet_bar_snapshot', 'fit_fleet_bar', 'move_fleet_bar',
                         'save_fleet_bar_pos', 'fleet_bar_ready']) {
    api[method] = (...args) => {
      const reply = deferred();
      calls.push({ method, args, ...reply });
      return reply.promise;
    };
  }
  const window = new EventTarget();
  window.location = { hash: options.hash ?? fragment(A) };
  window.screenX = options.x ?? 20;
  window.screenY = options.y ?? 30;
  if (options.bridgeReady !== false) window.pywebview = { api };
  const screen = options.screen ?? {
    availLeft: 0, availTop: 0, availWidth: 1280, availHeight: 720
  };
  const context = vm.createContext({
    window, document, screen,
    setTimeout: (fn, delay) => { timers.push({ fn, delay }); return timers.length; },
    console: { error: (...args) => errors.push(args) }
  });
  // Do not rewrite the script or inject a token variable: production must capture
  // the supplied fragment itself, before any of these controlled gates open.
  vm.runInContext(source, context, { filename: 'fleetbar.js' });
  await flush();
  return {
    window, document, shell, fonts, api, errors, timers,
    el: id => document.getElementById(id),
    calls: method => calls.filter(call => call.method === method),
    log: () => calls.map(({ method, args }) => [method, ...args]),
    attachBridge: async () => {
      window.pywebview = { api };
      window.dispatchEvent({ type: 'pywebviewready' });
      await flush();
    },
    push: async payload => { window.onFleetSnapshot(payload); await flush(); },
    mouseup: async () => { document.dispatchEvent({ type: 'mouseup' }); await flush(); },
    fireTimer: async () => {
      assert.equal(timers.length, 1);
      const timer = timers.shift();
      assert.equal(timer.delay, 500);
      timer.fn();
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

// The Damage cell's DOM contract: OUT half, axis, IN half, in that order,
// inside one role=cell node. fillOf/valueOf read into a half's rail fill and
// its number, respectively, mirroring fleetbar.js's damageHalf() structure.
function fillOf(half) {
  const track = half.children.find(child => child.className === 'fleet-damage-track');
  assert.ok(track, half.className + ' has no track');
  return track.children[0];
}

function valueOf(half) {
  return half.children.find(child => child.className.indexOf('fleet-damage-value') === 0);
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
  assert.equal(p.el('fleet-health').textContent, 'LIVE');
  assert.equal(p.el('fleet-note').hidden, true);
}

const displaced = {
  x: 50, y: 900,
  screen: { availLeft: -1280, availTop: 40, availWidth: 1280, availHeight: 720 }
};

test('A keeps its identity through delayed bridge, fonts, snapshot, fit, move and ready after B boots', async () => {
  const a = await page({ bridgeReady: false, ...displaced });
  assert.deepEqual(a.log(), []);
  const b = await page({ hash: fragment(B), width: 460, height: 166 });
  await settle(b.fonts);
  await settle(b.calls('fleet_bar_snapshot')[0], snapshot(1, 'B pilot'));
  await settle(b.calls('fit_fleet_bar')[0]);
  await settle(b.calls('fleet_bar_ready')[0]);
  assertRendered(b, 'B pilot');
  assert.deepEqual(b.log(), [
    ['fleet_bar_snapshot', B], ['fit_fleet_bar', B, 460, 166], ['fleet_bar_ready', B]
  ]);

  a.window.location.hash = fragment(B);
  await a.attachBridge();
  assert.deepEqual(a.log(), [['fleet_bar_snapshot', A]]);
  await settle(a.calls('fleet_bar_snapshot')[0], snapshot(1, 'A pilot'));
  assert.equal(a.el('fleet-rows').children.length, 0, 'fonts still gate hydration');
  assert.equal(a.calls('fleet_bar_ready').length, 0);
  await settle(a.fonts);
  assertRendered(a, 'A pilot');
  assert.deepEqual(a.calls('fit_fleet_bar')[0].args, [A, 420, 114]);
  assert.equal(a.calls('move_fleet_bar').length, 0, 'clamp waits for the fit reply');
  assert.equal(a.calls('fleet_bar_ready').length, 0);
  // Dimensions belong to this fit; screen coordinates are sampled after it settles.
  a.shell.offsetWidth = 480;
  a.shell.offsetHeight = 190;
  a.window.screenX = 30;
  a.window.screenY = 950;
  await settle(a.calls('fit_fleet_bar')[0]);
  assert.deepEqual(a.calls('move_fleet_bar')[0].args, [A, -420, 646]);
  assert.equal(a.calls('fleet_bar_ready').length, 0, 'ready also waits for move');
  await settle(a.calls('move_fleet_bar')[0]);
  await settle(a.calls('fleet_bar_ready')[0]);
  assert.deepEqual(a.log(), [
    ['fleet_bar_snapshot', A], ['fit_fleet_bar', A, 420, 114],
    ['move_fleet_bar', A, -420, 646], ['fleet_bar_ready', A]
  ]);

  await a.fireTimer();
  assert.deepEqual(a.calls('fit_fleet_bar')[1].args, [A, 480, 190]);
  await settle(a.calls('fit_fleet_bar')[1]);
  assert.deepEqual(a.calls('move_fleet_bar')[1].args, [A, -480, 570]);
  await settle(a.calls('move_fleet_bar')[1]);
  await a.mouseup();
  assert.deepEqual(a.calls('save_fleet_bar_pos')[0].args, [A, 30, 950]);
  await settle(a.calls('save_fleet_bar_pos')[0]);
  assert.equal(a.calls('fleet_bar_ready').length, 1);
  assert.equal(b.log().length, 3, 'A continuations never call B\'s bridge');
  assert.deepEqual(a.errors.concat(b.errors), []);
});

test('500ms fit and mouseup queued before bridge readiness keep the initial token', async () => {
  const p = await page({ bridgeReady: false, ...displaced });
  await p.fireTimer();
  await p.mouseup();
  assert.deepEqual(p.log(), []);
  p.window.location.hash = fragment(B);
  await p.attachBridge();
  assert.deepEqual(p.log(), [
    ['fleet_bar_snapshot', A], ['fit_fleet_bar', A, 420, 114],
    ['save_fleet_bar_pos', A, 50, 900]
  ]);
  await settle(p.calls('fit_fleet_bar')[0]);
  assert.deepEqual(p.calls('move_fleet_bar')[0].args, [A, -420, 646]);
  assert.equal(p.calls('fleet_bar_ready').length, 0);
  assert.deepEqual(p.errors, []);
});

test('later fragment removal cannot revoke or replace the captured creation identity', async () => {
  const p = await page({ bridgeReady: false });
  p.window.location.hash = '';
  await p.attachBridge();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0]);
  await p.mouseup();
  assert.deepEqual(p.log(), [
    ['fleet_bar_snapshot', A], ['fleet_bar_ready', A],
    ['save_fleet_bar_pos', A, 20, 30]
  ]);
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
    const p = await page({ hash, bridgeReady: false, ...displaced });
    p.window.location.hash = fragment(B);
    await p.attachBridge();
    await settle(p.fonts);
    await p.push(snapshot());
    await p.fireTimer();
    await p.mouseup();
    assertRendered(p);
    assert.deepEqual(p.log(), []);
    assert.deepEqual(p.errors, []);
  });
}

test('invalid identity resolves null without waiting for a bridge that never arrives', async () => {
  const p = await page({ hash: '', bridgeReady: false, ...displaced });
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
    await settle(p.calls('fleet_bar_ready')[0]);
    assert.deepEqual(p.errors.map(error => error[0]),
                     outcome === 'reject' ? ['bridge: fleet_bar_snapshot failed'] : []);
  });
}

for (const fitOutcome of ['null', 'reject']) {
  for (const moveOutcome of ['null', 'reject']) {
    test(`${fitOutcome} fit then ${moveOutcome} move still reaches token-bound ready`, async () => {
      const p = await page(displaced);
      await settle(p.fonts);
      await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
      assert.equal(p.calls('fleet_bar_ready').length, 0);
      const fit = p.calls('fit_fleet_bar')[0];
      assert.deepEqual(fit.args, [A, 420, 114]);
      if (fitOutcome === 'null') await settle(fit);
      else await fail(fit);
      const move = p.calls('move_fleet_bar')[0];
      assert.deepEqual(move.args, [A, -420, 646]);
      assert.equal(p.calls('fleet_bar_ready').length, 0);
      if (moveOutcome === 'null') await settle(move);
      else await fail(move);
      assert.deepEqual(p.calls('fleet_bar_ready')[0].args, [A]);
      await settle(p.calls('fleet_bar_ready')[0]);
      assertRendered(p);
      const expectedErrors = [];
      if (fitOutcome === 'reject') expectedErrors.push('bridge: fit_fleet_bar failed');
      if (moveOutcome === 'reject') expectedErrors.push('bridge: move_fleet_bar failed');
      assert.deepEqual(p.errors.map(error => error[0]), expectedErrors);
    });
  }
}

test('native dragging stays native; only mouseup saves current coordinates and rejection is best-effort', async () => {
  const p = await page();
  await settle(p.fonts);
  await settle(p.calls('fleet_bar_snapshot')[0]);
  await fail(p.calls('fleet_bar_ready')[0]);
  const before = p.log();
  p.document.dispatchEvent({ type: 'mousedown', screenX: 20, screenY: 30 });
  p.document.dispatchEvent({ type: 'mousemove', screenX: 70, screenY: 80 });
  await flush();
  assert.deepEqual(p.log(), before);
  // Native drag owns these coordinates; the page must not implement drag moves.
  p.window.screenX = 70;
  p.window.screenY = 80;
  await p.mouseup();
  assert.deepEqual(p.calls('save_fleet_bar_pos')[0].args, [A, 70, 80]);
  await fail(p.calls('save_fleet_bar_pos')[0]);
  assert.equal(p.calls('move_fleet_bar').length, 0);
  assert.deepEqual(p.errors.map(error => error[0]),
                   ['bridge: fleet_bar_ready failed', 'bridge: save_fleet_bar_pos failed']);
});

test('missing bridge methods remain null best-effort outcomes', async () => {
  const p = await page({ bridgeReady: false, ...displaced });
  for (const method of Object.keys(p.api)) delete p.api[method];
  await p.attachBridge();
  await settle(p.fonts);
  assert.equal(await p.window.onFleetSnapshot(snapshot()), null);
  await p.fireTimer();
  await p.mouseup();
  assertRendered(p);
  assert.deepEqual(p.log(), []);
  assert.deepEqual(p.errors, []);
});

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
    assert.equal(p.calls('fit_fleet_bar').length, 1, 'discarded hydration cannot refit');
    assert.deepEqual(p.calls('fit_fleet_bar')[0].args, [A, 420, 114]);
    // Existing best-effort semantics: ignoring hydration does not wait for a
    // separate push's pending fit, and does not require a positive fit result.
    assert.deepEqual(p.calls('fleet_bar_ready')[0].args, [A]);
    await settle(p.calls('fit_fleet_bar')[0]);
    await settle(p.calls('fleet_bar_ready')[0]);
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
  const fits = p.calls('fit_fleet_bar').length;
  assert.equal(fits, 3);
  for (const revision of [6, undefined, null, '8', -1, 1.5, NaN, Infinity, -Infinity]) {
    const invalid = snapshot(1, 'Invalid');
    invalid.revision = revision;
    assert.equal(await p.window.onFleetSnapshot(invalid), null);
    assertRendered(p, 'Latest');
    assert.equal(p.calls('fit_fleet_bar').length, fits);
  }
  assert.deepEqual(p.errors, []);
});

test('missing FontFaceSet preserves hydration, fit and ready ordering', async () => {
  const p = await page({ fonts: false });
  await settle(p.calls('fleet_bar_snapshot')[0], snapshot());
  assertRendered(p);
  assert.equal(p.calls('fleet_bar_ready').length, 0);
  await settle(p.calls('fit_fleet_bar')[0]);
  assert.deepEqual(p.log(), [
    ['fleet_bar_snapshot', A], ['fit_fleet_bar', A, 420, 114], ['fleet_bar_ready', A]
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
  await settle(reloaded.calls('fit_fleet_bar')[0]);
  // A delayed old-document fit can still lead to ready with that same token.
  await settle(old.calls('fit_fleet_bar')[0]);
  for (const p of [old, reloaded]) {
    assert.deepEqual(p.log(), [
      ['fleet_bar_snapshot', A], ['fit_fleet_bar', A, 420, 114], ['fleet_bar_ready', A]
    ]);
    await settle(p.calls('fleet_bar_ready')[0]);
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
