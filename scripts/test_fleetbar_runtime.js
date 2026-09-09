#!/usr/bin/env node
'use strict';

// Executes the real fleetbar.js render path -- window.onFleetSnapshot() --
// against representative rows with a stateful DOM subset. Not a renderer or
// a substitute for browser/WebView2 geometry; it proves handler-body
// behavior (DOM structure, ratios, classes, aria-label text) that neither
// the lexical assertions in tests/test_fleet_bar.py nor the top-level-load
// gate in scripts/js_smoke.js can see.
//
// Two independent payloads, not one: a normal-range payload (Alice, Bravo,
// No Log) owns the exact independent-ratio assertions, and a separate
// defensive payload (Huge alone) owns the >10m / accessible-phrase
// assertions. A single combined payload would make Huge's 10,000,001 the
// normalization maximum and break the Alice/Bravo ratio expectations below.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const web = path.join(__dirname, '..', 'wingman', 'web');
const source = fs.readFileSync(path.join(web, 'fleetbar.js'), 'utf8');

const tests = [];
function test(name, run) { tests.push({ name, run }); }
function flush() { return new Promise((resolve) => setImmediate(resolve)); }

class Element {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.children = [];
    this.attributes = {};
    this.className = '';
    this.style = {};
    this.title = '';
    this._text = '';
    this.classList = {
      contains: (name) => this.className.split(/\s+/).filter(Boolean).includes(name),
      add: (name) => {
        if (!this.classList.contains(name)) {
          this.className = (this.className + ' ' + name).trim();
        }
      },
      remove: (name) => {
        this.className = this.className.split(/\s+/).filter((n) => n && n !== name).join(' ');
      },
      toggle: (name, force) => {
        const on = force === undefined ? !this.classList.contains(name) : force;
        if (on) this.classList.add(name); else this.classList.remove(name);
        return on;
      },
    };
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join('');
  }
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name)
      ? this.attributes[name] : null;
  }
}

// Builds a fresh vm context with real recording elements for fleet-rows,
// fleet-empty, fleet-health and fleet-note (the ids fleetbar.js's render()
// looks up by getElementById), evaluates fleetbar.js, and returns a
// render() helper that invokes window.onFleetSnapshot() and drains
// microtasks so the render's returned promise settles before assertions.
function page() {
  const nodes = {
    'fleet-rows': new Element('div'),
    'fleet-empty': new Element('div'),
    'fleet-health': new Element('span'),
    'fleet-note': new Element('div'),
  };
  const document = {
    getElementById: (id) => nodes[id] || null,
    createElement: (tag) => new Element(tag),
    // fleetbar.js's fit() only runs if '.fleet-shell' resolves to an
    // element; returning null makes fit() a no-op after the DOM is built,
    // which is all this harness claims about (no geometry here).
    querySelector: () => null,
    addEventListener: () => {},
    fonts: { ready: Promise.resolve() },
  };
  const api = {
    fit_fleet_bar: () => null,
    move_fleet_bar: () => null,
    save_fleet_bar_pos: () => null,
    fleet_bar_snapshot: () => null,
    fleet_bar_ready: () => null,
  };
  const screen = { availLeft: 0, availTop: 0, availWidth: 1000, availHeight: 700 };
  const window = {
    pywebview: { api },
    addEventListener: () => {},
    screenX: 0,
    screenY: 0,
  };
  window.window = window;
  const context = vm.createContext({
    window, document, screen,
    console, Promise, Array, Object, Number, String, Math,
    isFinite, isNaN, parseInt, parseFloat,
    setTimeout, clearTimeout, setInterval, clearInterval,
  });
  vm.runInContext(source, context, { filename: 'fleetbar.js' });
  return {
    nodes,
    async render(payload) {
      await window.onFleetSnapshot(payload);
      await flush();
    },
  };
}

function fillOf(half) {
  const track = half.children.find((child) => child.className === 'fleet-damage-track');
  assert.ok(track, half.className + ' has no track');
  return track.children[0];
}

function valueOf(half) {
  return half.children.find((child) => child.className.indexOf('fleet-damage-value') === 0);
}

const NORMAL_ROWS = [
  { character: 'Alice', outgoing_dps: 100, incoming_dps: 50, ewar: ['SCRAM'], log_status: null },
  { character: 'Bravo', outgoing_dps: 25, incoming_dps: 200, ewar: [], log_status: null },
  { character: 'No Log', outgoing_dps: null, incoming_dps: null, ewar: [], log_status: 'NO LOG' },
];

test('normal-range payload: OUT/IN DOM order, independent ratios, exact values', async () => {
  const p = page();
  await p.render({
    revision: 1, rows: NORMAL_ROWS, running_count: 3,
    stream_health: { state: 'active' },
  });
  const rows = p.nodes['fleet-rows'].children;
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
    ewar: ['SCRAM', 'POINT', 'NEUT'], log_status: null,
  },
];

test('defensive payload: values beyond ten million collapse to >10m and the accessible phrase', async () => {
  const p = page();
  await p.render({
    revision: 1, rows: DEFENSIVE_ROWS, running_count: 1,
    stream_health: { state: 'active' },
  });
  const rows = p.nodes['fleet-rows'].children;
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
    'Outgoing more than 10 million DPS, incoming more than 10 million DPS',
  );

  const ewar = rows[0].children[2];
  assert.equal(ewar.textContent, 'SCRAM \u00b7 POINT \u00b7 NEUT');
});

(async function main() {
  let failures = 0;
  for (const { name, run } of tests) {
    try {
      await run();
      console.log('PASS ' + name);
    } catch (error) {
      failures += 1;
      console.error('FAIL ' + name + '\n' + error.stack);
    }
  }
  console.log(`${tests.length - failures}/${tests.length} fleetbar runtime tests passed`);
  if (failures) process.exitCode = 1;
}());
