/* Executable Skills lifecycle regressions. Real app.js/skills.js, deferred
 * bridge promises, and a stateful DOM subset — no browser/layout claims. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const web = path.join(__dirname, '..', 'wingman', 'web');

class EventTarget {
  constructor() { this.listeners = {}; }
  addEventListener(name, fn) {
    (this.listeners[name] ||= []).push(fn);
  }
  dispatchEvent(event) {
    for (const fn of this.listeners[event.type] || []) fn(event);
  }
}

class Element extends EventTarget {
  constructor(tag = 'div') {
    super();
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.className = '';
    this.value = '';
    this.hidden = false;
    this.disabled = false;
    this.text = '';
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      toggle: (name, force) => {
        const on = force === undefined ? !this.classList.contains(name) : force;
        const names = this.className.split(/\s+/).filter(n => n && n !== name);
        if (on) names.push(name);
        this.className = names.join(' ');
        return on;
      },
      add: name => this.classList.toggle(name, true),
      remove: name => this.classList.toggle(name, false)
    };
  }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() {
    return this.text + this.children.map(child => child.textContent).join('');
  }
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  click() { this.dispatchEvent({ type: 'click' }); }
}

// Drain bridge/read continuation jobs without sleeps or wall-clock ordering.
async function flush() {
  await new Promise(resolve => setImmediate(resolve));
}

async function page() {
  const nodes = new Map();
  const document = new EventTarget();
  // Use the page's actual IDs: typos must not silently create fake elements.
  const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
  for (const match of html.matchAll(/\bid="([^"]+)"/g)) {
    nodes.set(match[1], new Element());
  }
  document.getElementById = id => nodes.get(id) || null;
  document.createElement = tag => new Element(tag);
  document.querySelectorAll = () => [];
  document.querySelector = () => null;
  const calls = [];
  const errors = [];
  const api = {};
  for (const method of ['skills_state', 'skills_character_detail',
                         'skills_select_plan', 'skills_reload_plans']) {
    api[method] = (...args) => new Promise((resolve, reject) => {
      calls.push({ method, args, resolve, reject });
    });
  }
  // app.js boot reads are unrelated to this lane; no payload/push needed.
  api.list_rows = api.get_settings = api.update_status = () => null;
  const window = new EventTarget();
  window.pywebview = { api };
  const context = vm.createContext({
    window, document,
    CustomEvent: class { constructor(type, options = {}) {
      this.type = type; this.detail = options.detail;
    } },
    console: { warn: (...args) => errors.push(args),
               error: (...args) => errors.push(args) }
  });
  for (const file of ['app.js', 'skills.js']) {
    vm.runInContext(fs.readFileSync(path.join(web, file), 'utf8'), context,
                    { filename: file });
  }
  await flush();
  return {
    el: id => document.getElementById(id),
    calls: method => calls.filter(call => call.method === method),
    reads: () => calls.filter(call => call.method === 'skills_state'),
    route: async name => { window.WM.route(name); await flush(); },
    authority: async () => { window.onEveAuthorityChanged({}); await flush(); },
    push: async payload => { window.onSkills(payload); await flush(); },
    errors
  };
}

function state(name = 'New', readiness = 'Ready') {
  return {
    selected_plan_name: name, selected_group: '', groups: [],
    plans: [{ name, ready_count: readiness === 'Ready' ? 1 : 0,
              requirement_count: 1 }],
    characters: [{
      character_id: 42, character_name: 'Pilot', group: '', readiness,
      stale: false, needs_reauth: false, error: '',
      fetched_utc: '2026-09-07T12:00:00Z', fetched_label: 'Just now',
      active_count: readiness === 'Ready' ? 1 : 0,
      trained_inactive_count: 0, unknown_count: 0,
      missing_count: readiness === 'Ready' ? 0 : 1,
      missing_names: readiness === 'Ready' ? [] : ['Navigation'],
      queued_count: 0, estimated_finish_utc: '', queue_timing_unknown: false,
      training_estimate_status: 'available', training_remaining_seconds: 0,
      training_remaining_label: '0m'
    }],
    refresh_in_flight: false, warnings: [], plan_issues: [], plans_updated_utc: ''
  };
}

function detail(skill) {
  return {
    ok: true, message: '', character_id: 42, plan_name: 'New',
    readiness: 'Missing', estimated_finish_utc: '', queue_timing_unknown: false,
    requirements: [{
      skill_name: skill, required_level: 5, state: 'Missing',
      queued_finish_utc: '', queue_timing_unknown: false
    }]
  };
}

function assertState(p, name = 'New', readiness = 'Ready') {
  assert.equal(p.el('skills-plan-name').textContent, name);
  assert.match(p.el('skills-plans').textContent,
               readiness === 'Ready' ? /1\/1/ : /0\/1/);
  assert.match(p.el('skills-roster').textContent,
               readiness === 'Ready' ? /Ready1 character/ : /Missing requirements1 character/);
  assert.match(p.el('skills-roster').textContent, /Pilot/);
}

async function settle(call, payload) { call.resolve(payload); await flush(); }

async function revisit(p, times = 3) {
  for (let i = 0; i < times; i++) {
    await p.route('main');
    await p.route('skills');
  }
}

test('initial reply abandoned while hidden can hydrate on re-entry', async () => {
  const p = await page();
  await p.route('skills');
  await p.route('main');
  await settle(p.reads()[0], state());
  await p.route('skills');
  // Either a preserved valid state or one bounded retry is acceptable.
  if (p.reads().length === 2) await settle(p.reads()[1], state());
  assertState(p);
  const hydratedReads = p.reads().length;
  assert.ok(hydratedReads <= 2);
  await revisit(p);
  assert.equal(p.reads().length, hydratedReads);
  assert.deepEqual(p.errors, []);
});

test('a newer push wins over an older state read, including readiness', async () => {
  const p = await page();
  await p.route('skills');
  await p.push(state());
  assertState(p);
  await settle(p.reads()[0], state('Old', 'Missing'));
  assertState(p);
  assert.equal(p.calls('skills_character_detail').length, 1,
               'discarded reads must not restart detail work');
  assert.deepEqual(p.errors, []);
});

for (const outcome of ['null', 'reject']) {
  for (const newer of ['push', 'read']) {
    test(`older ${outcome} cannot undo hydration from a newer ${newer}`, async () => {
      const p = await page();
      await p.route('skills');
      const old = p.reads()[0];
      if (newer === 'push') await p.push(state());
      else {
        await p.authority();
        await settle(p.reads()[1], state());
      }
      if (outcome === 'null') old.resolve(null);
      else old.reject(new Error('injected bridge rejection'));
      await flush();
      assertState(p);
      const count = p.reads().length;
      await revisit(p);
      assert.equal(p.reads().length, count, 'valid hydration must survive old failures');
      assert.equal(p.errors.length, outcome === 'reject' ? 1 : 0);
      if (outcome === 'reject') {
        assert.equal(p.errors[0][0], 'bridge: skills_state failed');
      }
    });
  }
}

test('repeated entries share an initial pending read; overlapping authority reads keep newest', async () => {
  const p = await page();
  await p.route('skills');
  await revisit(p, 5);
  assert.equal(p.reads().length, 1);
  await p.authority();
  await p.authority();
  assert.equal(p.reads().length, 3);
  await settle(p.reads()[1], state('Middle', 'Missing'));
  assert.equal(p.el('skills-plan-name').textContent, '');
  await settle(p.reads()[2], state());
  await settle(p.reads()[0], state('Old', 'Missing'));
  assertState(p);
  await revisit(p, 5);
  assert.equal(p.reads().length, 3);
  assert.deepEqual(p.errors, []);
});

test('an older failed read cannot release a newer pending hydration read', async () => {
  const p = await page();
  await p.route('skills');
  await p.authority();
  await settle(p.reads()[0], null);
  await revisit(p);
  assert.equal(p.reads().length, 2);
  await settle(p.reads()[1], state());
  assertState(p);
  assert.deepEqual(p.errors, []);
});

test('a superseded success cannot hydrate after the latest read fails', async () => {
  const p = await page();
  await p.route('skills');
  await p.authority();
  await settle(p.reads()[1], null);
  await settle(p.reads()[0], state('Old', 'Missing'));
  await revisit(p);
  assert.equal(p.reads().length, 3);
  await settle(p.reads()[2], state());
  assertState(p);
  assert.deepEqual(p.errors, []);
});

test('a push before first entry already hydrates the page', async () => {
  const p = await page();
  await p.push(state());
  await p.route('skills');
  assertState(p);
  assert.equal(p.reads().length, 0);
  assert.deepEqual(p.errors, []);
});

test('a valid empty roster is hydrated, not a failed read', async () => {
  const p = await page();
  await p.route('skills');
  const empty = state();
  empty.characters = [];
  empty.plans = [];
  empty.selected_plan_name = '';
  await settle(p.reads()[0], empty);
  await revisit(p);
  assert.equal(p.reads().length, 1);
  assert.match(p.el('skills-empty').textContent, /No characters yet/);
  assert.equal(p.el('skills-copy-plan').disabled, true);
  assert.deepEqual(p.errors, []);
});

test('failed initial read retries on entry without a background retry loop', async () => {
  const p = await page();
  await p.route('skills');
  await settle(p.reads()[0], null);
  assert.equal(p.reads().length, 1);
  await revisit(p);
  assert.equal(p.reads().length, 2);
  await settle(p.reads()[1], state());
  assertState(p);
  assert.deepEqual(p.errors, []);
});

test('failed authority refresh retains useful cached state on later visits', async () => {
  const p = await page();
  await p.route('skills');
  await settle(p.reads()[0], state());
  await p.authority();
  await settle(p.reads()[1], null);
  await revisit(p);
  assertState(p);
  assert.equal(p.reads().length, 2);
  assert.deepEqual(p.errors, []);
});

test('pushes refresh open detail without blanking it; stale detail replies cannot win', async () => {
  const p = await page();
  await p.route('skills');
  await settle(p.reads()[0], state());
  await settle(p.calls('skills_character_detail')[0], detail('Cached'));
  assert.match(p.el('skills-roster').textContent, /Cached V/);
  await p.push(state());
  await p.push(state());
  assert.match(p.el('skills-roster').textContent, /Cached V/);
  assert.doesNotMatch(p.el('skills-roster').textContent, /Loading requirements/);
  await settle(p.calls('skills_character_detail')[2], detail('Latest'));
  await settle(p.calls('skills_character_detail')[1], detail('Stale'));
  assert.match(p.el('skills-roster').textContent, /Latest V/);
  assert.doesNotMatch(p.el('skills-roster').textContent, /Stale V/);
  assert.deepEqual(p.errors, []);
});

for (const action of ['select', 'reload']) {
  test(`${action} invalidates detail requests before its resulting state push`, async () => {
    const p = await page();
    await p.route('skills');
    const payload = state();
    payload.plans.push({ name: 'Other', ready_count: 0, requirement_count: 1 });
    await settle(p.reads()[0], payload);
    const oldDetail = p.calls('skills_character_detail')[0];
    if (action === 'select') {
      p.el('skills-plans').children[1].click();
    } else {
      p.el('skills-reload-plans').click();
    }
    await flush();
    const method = action === 'select' ? 'skills_select_plan' : 'skills_reload_plans';
    assert.equal(p.calls(method).length, 1);
    if (action === 'select') assert.deepEqual(p.calls(method)[0].args, ['Other']);
    await settle(oldDetail, detail('Discarded'));
    assert.doesNotMatch(p.el('skills-roster').textContent, /Discarded V/);
    await p.push(state('Other', 'Missing'));
    const fresh = p.calls('skills_character_detail')[1];
    assert.deepEqual(fresh.args, [42, 'Other']);
    await settle(fresh, detail('Replacement'));
    await settle(p.calls(method)[0], true);
    assert.match(p.el('skills-roster').textContent, /Replacement V/);
    assert.deepEqual(p.errors, []);
  });
}

test('authority refresh stays route-scoped and preserves leave behavior', async () => {
  const p = await page();
  await p.authority();
  assert.equal(p.reads().length, 0);
  await p.route('skills');
  await settle(p.reads()[0], state('Old', 'Missing'));
  await p.authority();
  assert.equal(p.reads().length, 2);
  await settle(p.reads()[1], state());
  assertState(p);
  assert.equal(p.calls('skills_character_detail').length, 2);
  await p.route('main');
  await p.authority();
  assert.equal(p.reads().length, 2);
  await p.push(state('Hidden', 'Missing'));
  await p.route('skills');
  assertState(p, 'Hidden', 'Missing');
  assert.equal(p.reads().length, 2);
  assert.deepEqual(p.errors, []);
});
