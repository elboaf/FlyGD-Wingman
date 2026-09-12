/* Executable Fittings regressions: real app.js/fittings.js, deferred bridge
 * replies and a stateful DOM subset. No browser/layout/focus claims. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const web = path.join(__dirname, '..', 'wingman', 'web');

class EventTarget {
  constructor() { this.listeners = {}; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
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
  set textContent(value) {
    this.text = String(value);
    this.children.forEach(child => { child.parentNode = null; });
    this.children = [];
  }
  get textContent() { return this.text + this.children.map(c => c.textContent).join(''); }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  contains(node) { return this === node || this.children.some(c => c.contains(node)); }
  querySelectorAll(selector) {
    const found = [];
    const matches = node => selector.split(',').some(part => {
      if (part.includes(':disabled') && node.disabled) return false;
      if (part.includes('[hidden]') && node.hidden) return false;
      part = part.replace(/:not\([^)]*\)/g, '').trim();
      if (part.startsWith('.')) return node.classList.contains(part.slice(1));
      return node.tagName === part.toUpperCase();
    });
    const walk = node => node.children.forEach(child => {
      if (matches(child)) found.push(child);
      walk(child);
    });
    walk(this);
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  getClientRects() { return this.hidden ? [] : [{}]; }
  focus() {}
  blur() {}
  click() { if (!this.disabled) this.dispatchEvent({ type: 'click' }); }
}

async function flush() { await new Promise(resolve => setImmediate(resolve)); }
async function settle(call, payload) {
  assert.ok(call, 'expected a pending bridge call');
  call.resolve(payload);
  await flush();
}
function input(node, value) { node.value = value; node.dispatchEvent({ type: 'input' }); }
function tick(node) { node.checked = !node.checked; node.dispatchEvent({ type: 'change' }); }

async function page() {
  const nodes = new Map();
  const document = new EventTarget();
  // Actual static IDs, plus a tree search for controls created by fittings.js.
  const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
  for (const match of html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const node = new Element(match[1]);
    node.id = match[2];
    node.hidden = /\bhidden\b/.test(match[0]);
    node.disabled = /\bdisabled\b/.test(match[0]);
    nodes.set(node.id, node);
  }
  const findId = (node, id) => node.id === id ? node
    : node.children.map(child => findId(child, id)).find(Boolean);
  document.getElementById = id => nodes.get(id)
    || [...nodes.values()].map(node => findId(node, id)).find(Boolean) || null;
  document.createElement = tag => new Element(tag);
  document.querySelectorAll = () => [];
  document.querySelector = () => null;
  document.contains = node => [...nodes.values()].some(root => root.contains(node));
  const calls = [];
  const errors = [];
  const confirmations = [];
  const api = {};
  for (const method of ['fittings_state', 'fittings_detail', 'fittings_update_metadata',
    'fittings_set_membership', 'fittings_refresh', 'fittings_delete_entry',
    'fittings_preflight_copy', 'fittings_start_copy', 'fittings_cancel_copy']) {
    api[method] = (...args) => new Promise((resolve, reject) => {
      calls.push({ method, args, resolve, reject });
    });
  }
  api.list_rows = api.get_settings = api.update_status = () => null;
  const window = new EventTarget();
  window.pywebview = { api };
  window.getComputedStyle = () => ({ visibility: 'visible' });
  const timers = new Map();
  let timerId = 0;
  const context = vm.createContext({
    window, document,
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
    clearTimeout: id => timers.delete(id),
    CustomEvent: class { constructor(type, options = {}) {
      this.type = type; this.detail = options.detail;
    } },
    console: { warn: (...args) => errors.push(args), error: (...args) => errors.push(args) }
  });
  for (const file of ['app.js', 'fittings.js']) {
    vm.runInContext(fs.readFileSync(path.join(web, file), 'utf8'), context, { filename: file });
  }
  window.WM.confirm = (...args) => new Promise(resolve => confirmations.push({ args, resolve }));
  await flush();
  return {
    el: id => document.getElementById(id),
    calls: method => calls.filter(call => !method || call.method === method),
    last: method => calls.filter(call => call.method === method).at(-1),
    route: async name => { window.WM.route(name); await flush(); },
    changed: async payload => { window.onFittingsChanged(payload); await flush(); },
    progress: async payload => { window.onFittingsProgress(payload); await flush(); },
    screenshot: async payload => { window.onFittingsScreenshotState(payload); await flush(); },
    timers: async () => { for (const fn of timers.values()) fn(); timers.clear(); await flush(); },
    confirmations, errors
  };
}

function state(ids = ['fit-1']) {
  return {
    available: true, warnings: [], refreshing: false,
    filters: { collection_id: 'all', search: '', ship_type_id: null },
    collections: [{ id: 'all', name: 'All fittings', count: ids.length },
                  { id: 'doctrine', name: 'Doctrine', count: 1 }],
    characters: [{ character_id: 42, character_name: 'Pilot', status: 'enabled',
                   fetched_utc: '2026-09-07T12:00:00Z', stale: false }],
    ships: [], page: 1, page_size: 100, total: ids.length,
    rows: ids.map(id => ({ id, name: 'Sabre tackle', ship_type_id: 22456,
      ship_name: 'Sabre', presence_count: 0, collection_ids: [],
      deployable: true, superseded_by: null }))
  };
}
function detail(id = 'fit-1', name = 'Sabre tackle', description = 'Saved description') {
  return { id, name, description, ship_type_id: 22456, items: [], aliases: [],
           presences: [], collection_ids: [], superseded_by: null };
}
function button(root, label) {
  const node = root.querySelectorAll('button').find(node => node.textContent === label);
  assert.ok(node, 'missing button: ' + label);
  return node;
}
function metadata(p) { return p.el('fittings-list').querySelector('.fit-metadata'); }
async function editor() {
  const p = await page();
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  await settle(p.last('fittings_detail'), detail());
  return p;
}
async function repaint(p, payload = state(), value = detail()) {
  await p.changed({ reason: 'collection_membership', entry_id: 'fit-1' });
  await settle(p.last('fittings_state'), payload);
  await settle(p.last('fittings_detail'), value);
}
function assertDraft(p, name, description) {
  assert.equal(p.el('fit-name-fit-1').value, name);
  assert.equal(p.el('fit-desc-fit-1').value, description);
  assert.match(metadata(p).textContent, /Unsaved changes/);
}

// A render using server metadata must not erase text that was never submitted.
test('membership push and refresh preserve both metadata drafts without saving on blur', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Draft name');
  input(p.el('fit-desc-fit-1'), 'Draft description');
  p.el('fit-name-fit-1').dispatchEvent({ type: 'blur' });
  tick(p.el('fittings-list').querySelector('.fit-collections').querySelector('input'));
  await flush();
  assert.deepEqual(p.last('fittings_set_membership').args, ['fit-1', 'doctrine', true]);
  await repaint(p);
  assertDraft(p, 'Draft name', 'Draft description');
  p.el('fittings-refresh-all').click();
  await repaint(p);
  assertDraft(p, 'Draft name', 'Draft description');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
  assert.deepEqual(p.errors, []);
});

test('draft follows its fitting through collapse, another editor, filters and route re-entry', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Keep me');
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  assert.match(p.el('fittings-list').textContent, /Unsaved changes/);
  input(p.el('fittings-search'), 'other');
  await p.timers();
  const filtered = state(['fit-2']);
  filtered.filters.search = 'other';
  await settle(p.last('fittings_state'), filtered);
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  await settle(p.last('fittings_detail'), detail('fit-2', 'Other fit'));
  assert.equal(p.el('fit-name-fit-2').value, 'Other fit');
  input(p.el('fit-name-fit-2'), 'Second draft');
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), filtered);
  await settle(p.last('fittings_detail'), detail('fit-2', 'Other fit'));
  assert.equal(p.el('fit-name-fit-2').value, 'Second draft');
  p.el('fittings-filter-clear').click();
  await flush();
  await settle(p.last('fittings_state'), state(['fit-1', 'fit-2']));
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  await settle(p.last('fittings_detail'), detail());
  assertDraft(p, 'Keep me', 'Saved description');
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

test('older save acknowledgement cannot erase newer typing or allow overlapping saves', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Submitted');
  button(metadata(p), 'Save').click();
  await flush();
  const save = p.last('fittings_update_metadata');
  input(p.el('fit-name-fit-1'), 'Newer typing');
  await repaint(p, state(), detail('fit-1', 'Submitted'));
  assertDraft(p, 'Newer typing', 'Saved description');
  assert.equal(metadata(p).querySelector('button').disabled, true);
  await settle(save, true);
  assertDraft(p, 'Newer typing', 'Saved description');
  button(metadata(p), 'Save').click();
  await flush();
  assert.deepEqual(p.last('fittings_update_metadata').args,
                   ['fit-1', 'Newer typing', 'Saved description']);
  assert.equal(p.calls('fittings_update_metadata').length, 2);
});

for (const failure of ['false', 'null', 'reject']) {
  test(`metadata ${failure} retains editable draft for explicit successful retry`, async () => {
    const p = await editor();
    input(p.el('fit-desc-fit-1'), 'Keep after failure');
    button(metadata(p), 'Save').click();
    await flush();
    if (failure === 'reject') p.last('fittings_update_metadata').reject(new Error('injected'));
    else p.last('fittings_update_metadata').resolve(failure === 'false' ? false : null);
    await flush();
    await settle(p.last('fittings_state'), state());
    await settle(p.last('fittings_detail'), detail());
    assertDraft(p, 'Sabre tackle', 'Keep after failure');
    assert.match(metadata(p).textContent, /not confirmed|could not|failed/i);
    assert.equal(button(metadata(p), 'Save').disabled, false);
    button(metadata(p), 'Save').click();
    await flush();
    await settle(p.last('fittings_update_metadata'), true);
    assert.doesNotMatch(metadata(p).textContent, /Unsaved changes|not confirmed|could not|failed/i);
    assert.equal(p.el('fit-desc-fit-1').value, 'Keep after failure');
    await repaint(p, state(), detail('fit-1', 'Sabre tackle', 'Keep after failure'));
    assert.equal(p.el('fit-desc-fit-1').value, 'Keep after failure');
    assert.equal(p.errors.length, failure === 'reject' ? 1 : 0);
  });
}

test('save acknowledgement invalidates an older detail reply without losing accepted text', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Accepted name');
  button(metadata(p), 'Save').click();
  await flush();
  await p.changed({ reason: 'metadata', entry_id: 'fit-1' });
  await settle(p.last('fittings_state'), state());
  const staleDetail = p.last('fittings_detail');
  await settle(p.last('fittings_update_metadata'), true);
  await settle(staleDetail, detail());
  assert.equal(p.el('fit-name-fit-1').value, 'Accepted name');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
});

test('discard requires confirmation, restores persisted metadata and never writes', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Discard me');
  button(metadata(p), 'Discard changes').click();
  assert.equal(p.confirmations.length, 1);
  await settle(p.confirmations[0], false);
  assertDraft(p, 'Discard me', 'Saved description');
  button(metadata(p), 'Discard changes').click();
  await settle(p.confirmations[1], true);
  assert.equal(p.el('fit-name-fit-1').value, 'Sabre tackle');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
  assert.equal(p.calls('fittings_update_metadata').length, 0);
});

test('discard confirmation cannot erase typing entered after the dialog opened', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Older draft');
  button(metadata(p), 'Discard changes').click();
  input(p.el('fit-name-fit-1'), 'Newer draft');
  await settle(p.confirmations[0], true);
  assertDraft(p, 'Newer draft', 'Saved description');
});

test('delete notification retires the fitting draft, even while route is hidden', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Deleted draft');
  assertDraft(p, 'Deleted draft', 'Saved description');
  await p.route('main');
  await p.changed({ reason: 'delete', entry_id: 'fit-1' });
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  await settle(p.last('fittings_detail'), detail());
  assert.equal(p.el('fit-name-fit-1').value, 'Sabre tackle');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
});

test('a complete unfiltered library read retires drafts for removed IDs, not failed reads', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Removed draft');
  await p.changed({ reason: 'refresh' });
  await settle(p.last('fittings_state'), { available: false, warnings: ['Unavailable'] });
  await settle(p.last('fittings_detail'), null);
  await repaint(p);
  assertDraft(p, 'Removed draft', 'Saved description');
  await repaint(p, state([]), null);
  await repaint(p);
  assert.equal(p.el('fit-name-fit-1').value, 'Sabre tackle');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
});

test('older save failure keeps newer text across requery and requires another explicit save', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Submitted');
  button(metadata(p), 'Save').click();
  await flush();
  input(p.el('fit-name-fit-1'), 'Newer');
  await settle(p.last('fittings_update_metadata'), false);
  await settle(p.last('fittings_state'), state());
  await settle(p.last('fittings_detail'), detail());
  assertDraft(p, 'Newer', 'Saved description');
  assert.equal(p.calls('fittings_update_metadata').length, 1);
  assert.equal(button(metadata(p), 'Save').disabled, false);
});

test('collapse/reopen during a save cannot let a pre-ack detail read undo accepted metadata', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Accepted');
  button(metadata(p), 'Save').click();
  await flush();
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  const stale = p.last('fittings_detail');
  await settle(p.last('fittings_update_metadata'), true);
  await settle(stale, detail());
  assert.ok(!p.el('fit-name-fit-1') || p.el('fit-name-fit-1').value !== 'Sabre tackle');
  await settle(p.last('fittings_state'), state());
  await settle(p.last('fittings_detail'), detail('fit-1', 'Accepted'));
  assert.equal(p.el('fit-name-fit-1').value, 'Accepted');
  assert.doesNotMatch(metadata(p).textContent, /Unsaved changes/);
});

function preflight(ticket = 'ticket-1') {
  return { accepted: true, ticket_id: ticket, write_count: 1, counts: { ready: 1 },
    requires_resolution: false, pairs: [{ entry_id: 'fit-1', character_id: 42,
      fitting_name: 'Sabre tackle', character_name: 'Pilot', status: 'ready',
      chosen_name: 'Sabre tackle' }] };
}
async function reviewCopy(p, payload) {
  p.el('fittings-list').querySelectorAll('input').forEach(tick);
  p.el('fittings-copy-selected').click();
  tick(p.el('fittings-copy-body').querySelector('input'));
  p.el('fittings-copy-review').click();
  await flush();
  if (payload) await settle(p.last('fittings_preflight_copy'), payload);
}
async function startReviewedCopy(p) {
  p.el('fittings-copy-start').click();
  await settle(p.confirmations.at(-1), true);
  await settle(p.last('fittings_start_copy'), true);
}
function sameNameWorkspace() {
  const payload = state(['fit-1', 'fit-2']);
  payload.rows[0].name = payload.rows[1].name = 'Fleet tackle';
  payload.rows[1].ship_name = 'Flycatcher';
  payload.rows[1].ship_type_id = 22464;
  return payload;
}
function sameNamePreflight() {
  // Reversed relative to the workspace: correlation is by ID, not order or name.
  return { ...preflight(), counts: { ready: 1, present: 1, conflict: 0, unavailable: 0 },
    pairs: [
      { ...preflight().pairs[0], entry_id: 'fit-2', fitting_name: 'Fleet tackle',
        chosen_name: 'Fleet tackle alternate' },
      { ...preflight().pairs[0], fitting_name: 'Fleet tackle', status: 'present' }
    ] };
}

test('copy identity distinguishes same-name hulls across pending refresh and conflict recheck', async () => {
  const p = await page();
  await p.route('fittings');
  const workspace = sameNameWorkspace();
  await settle(p.last('fittings_state'), workspace);
  await reviewCopy(p);
  const pending = p.last('fittings_preflight_copy');
  assert.deepEqual(Array.from(pending.args[0]), ['fit-1', 'fit-2']);
  assert.deepEqual(Array.from(pending.args[1]), [42]);
  // Mutate and re-render the supplied rows while review is pending. Neither a
  // retained row object nor a lookup against current STATE is a snapshot.
  workspace.rows.forEach(row => { row.ship_name = 'Changed hull'; });
  await p.changed({ reason: 'refresh' });
  await settle(p.last('fittings_state'), workspace);
  const review = sameNamePreflight();
  review.requires_resolution = true;
  review.counts = { ready: 1, conflict: 1 };
  review.pairs[1].status = 'conflict';
  await settle(pending, review);
  const body = p.el('fittings-copy-body');
  assert.deepEqual(body.querySelectorAll('.fit-copy-pair-name').map(n => n.textContent),
    ['Fleet tackle (Flycatcher)', 'Fleet tackle (Sabre)']);
  assert.deepEqual(body.querySelectorAll('.fit-copy-character').map(n => n.textContent),
    ['Pilot', 'Pilot']);
  assert.match(body.textContent, /Ready as.*Fleet tackle alternate/);
  const alternate = body.querySelector('.fit-copy-alternate');
  assert.match(alternate.getAttribute('aria-label'), /Fleet tackle.*Sabre.*Pilot/);
  input(alternate, 'Fleet tackle new');
  p.el('fittings-copy-review').click();
  await flush();
  assert.equal(p.last('fittings_preflight_copy').args[2]['fit-1:42'], 'Fleet tackle new');
  review.requires_resolution = false;
  review.pairs[1].status = 'ready';
  review.pairs[1].chosen_name = 'Fleet tackle new';
  await settle(p.last('fittings_preflight_copy'), review);
  assert.deepEqual(body.querySelectorAll('.fit-copy-pair-name').map(n => n.textContent),
    ['Fleet tackle (Flycatcher)', 'Fleet tackle (Sabre)']);
  assert.match(body.textContent, /Ready as.*Fleet tackle new/);
  assert.equal(p.calls('fittings_start_copy').length, 0);
  assert.deepEqual(p.errors, []);
});

test('copy identity survives filtering, progress and reopening results without new bridge calls', async () => {
  const p = await page();
  await p.route('fittings');
  await settle(p.last('fittings_state'), sameNameWorkspace());
  const review = sameNamePreflight();
  await reviewCopy(p, review);
  input(p.el('fittings-search'), 'other');
  await p.timers();
  await settle(p.last('fittings_state'), state(['other-fit']));
  await startReviewedCopy(p);
  const before = p.calls().length;
  const rows = review.pairs.map(pair => ({ ...pair, attempted: pair.status === 'ready',
    status: pair.status === 'ready' ? 'success' : 'present', error: '' }));
  for (const [index, row] of rows.entries()) {
    await p.progress({ kind: 'copy', phase: 'progress', ticket_id: review.ticket_id,
      completed: index + 1, total: 2, result: row });
    const status = p.el('fittings-copy-status').textContent;
    assert.match(status, index === 0 ? /Fleet tackle.*Flycatcher.*Pilot.*Copied/
      : /Fleet tackle.*Sabre.*Pilot.*Already present/);
    assert.equal(p.el('fittings-copy-body').querySelector('.fit-copy-summary').textContent,
      (index + 1) + ' of 2 pairs checked');
  }
  await complete(p, { status: 'complete', operation_id: 'op-identity', write_count: 1, results: rows });
  const body = p.el('fittings-copy-body');
  const labels = body.querySelectorAll('.fit-copy-pair-name').map(n => n.textContent);
  assert.deepEqual(labels, ['Fleet tackle (Flycatcher)', 'Fleet tackle (Sabre)']);
  assert.match(body.querySelector('.fit-copy-summary').textContent, /1 copied.*1 already present/);
  assert.equal(p.calls().length, before);
  p.el('fittings-copy-close').click();
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.deepEqual(body.querySelectorAll('.fit-copy-pair-name').map(n => n.textContent), labels);
  assert.equal(p.calls().length, before);
  assert.deepEqual(p.errors, []);
});

test('copy identity uses known type IDs and never guesses hulls from matching names', async () => {
  const p = await page();
  await p.route('fittings');
  const workspace = state();
  workspace.rows[0].ship_name = '';
  await settle(p.last('fittings_state'), workspace);
  const review = preflight();
  review.pairs.push({ ...review.pairs[0], entry_id: 'not-selected' });
  await reviewCopy(p, review);
  const names = p.el('fittings-copy-body').querySelectorAll('.fit-copy-pair-name');
  assert.equal(names[0].textContent, 'Sabre tackle (Type 22456)');
  assert.equal(names[1].textContent, 'Sabre tackle');
  await startReviewedCopy(p);
  await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-1',
    completed: 1, total: 2, result: { entry_id: 'not-selected', character_id: 99, status: 'unknown' } });
  assert.match(p.el('fittings-copy-status').textContent, /Fitting not-selected.*Character 99.*Needs verification/);
  assert.doesNotMatch(p.el('fittings-copy-status').textContent, /Sabre|22456|undefined|NaN/);
  await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-1',
    completed: 2, total: 2, result: { status: 'present' } });
  assert.equal(p.el('fittings-copy-status').textContent, 'Already present',
    'identity-free events must not borrow identity from the last pair');
});

test('copy identity labels remain literal text for long markup-like names', async () => {
  const p = await page();
  await p.route('fittings');
  const workspace = state();
  const name = '<img src=x onerror=alert(1)>' + 'LongName'.repeat(20);
  workspace.rows[0].name = name;
  workspace.rows[0].ship_name = '<b>Sabre</b>';
  await settle(p.last('fittings_state'), workspace);
  const review = preflight();
  review.pairs[0].fitting_name = name;
  review.pairs[0].character_name = '<script>Pilot</script>';
  await reviewCopy(p, review);
  const label = p.el('fittings-copy-body').querySelector('.fit-copy-pair-name');
  assert.equal(label.textContent, name + ' (<b>Sabre</b>)');
  assert.equal(label.children.length, 0);
  await startReviewedCopy(p);
  await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-1',
    completed: 1, total: 1, result: { ...review.pairs[0], status: 'success' } });
  const status = p.el('fittings-copy-status');
  assert.ok(status.textContent.includes(name + ' (<b>Sabre</b>)'));
  assert.ok(status.textContent.includes('<script>Pilot</script>'));
  assert.equal(status.children.length, 0);
});

for (const count of [0, 1, 2]) {
  test(`copy counts ${count} distinguish plans, checked pairs, attempts and copied outcomes`, async () => {
    const p = await page();
    await p.route('fittings');
    await settle(p.last('fittings_state'), state());
    const review = preflight();
    review.write_count = count;
    review.counts = { ready: count, conflict: count, present: 4, unavailable: 3 };
    review.pairs = [...Array(count).fill('ready'), ...Array(count).fill('conflict'),
      ...Array(4).fill('present'), ...Array(3).fill('unavailable')].map((status, index) => ({
        ...preflight().pairs[0], character_id: 100 + index, character_name: 'Pilot ' + index,
        status, skipped: status === 'conflict'
      }));
    await reviewCopy(p, review);
    const body = p.el('fittings-copy-body');
    const summary = body.querySelector('.fit-copy-summary').textContent;
    assert.match(summary, new RegExp('^' + count + (count === 1 ? ' addition planned' : ' additions planned')));
    assert.match(summary, new RegExp('\\b' + count + (count === 1 ? ' conflict\\b(?!s)' : ' conflicts\\b')));
    assert.match(summary, /4 already present.*3 unavailable/);
    assert.doesNotMatch(summary, /remote write|copied|attempted|checked/);
    await startReviewedCopy(p);
    const total = count * 2 + 7;
    assert.equal(body.querySelector('.fit-copy-summary').textContent, '0 of ' + total + ' pairs checked');
    const results = review.pairs.map(pair => ({ ...pair, attempted: pair.status === 'ready',
      status: pair.status === 'ready' ? 'unknown' : pair.skipped ? 'conflict_skipped' : pair.status }));
    await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-1',
      completed: 1, total, result: results[0] });
    assert.equal(body.querySelector('.fit-copy-summary').textContent, '1 of ' + total + ' pairs checked');
    await complete(p, { status: 'complete', write_count: count, results });
    const completed = body.querySelector('.fit-copy-summary').textContent;
    assert.match(completed, /0 copied.*4 already present/);
    assert.match(completed, new RegExp(count + (count === 1 ? ' needs verification' : ' need verification')));
    assert.match(body.querySelector('.hint').textContent,
      new RegExp('^' + count + (count === 1 ? ' addition attempted' : ' additions attempted')));
    assert.doesNotMatch(body.textContent, /remote write|addition[s]? planned/);
    assert.match(body.textContent, /Nothing is retried automatically/);
  });
}

test('copy identity ignores stale and out-of-ticket progress after a newer copy starts', async () => {
  const p = await page();
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  await beginCopy(p);
  await p.route('main');
  await p.route('fittings');
  const workspace = state();
  workspace.rows[0].ship_name = 'Flycatcher';
  workspace.rows[0].ship_type_id = 22464;
  await settle(p.last('fittings_state'), workspace);
  await beginCopy(p, 'ticket-2');
  const current = { ...preflight('ticket-2').pairs[0], status: 'unknown' };
  await p.progress({ kind: 'copy', phase: 'progress', ticket_id: 'ticket-2',
    completed: 1, total: 1, result: current });
  const status = p.el('fittings-copy-status').textContent;
  assert.match(status, /Sabre tackle.*Flycatcher.*Pilot.*Needs verification/);
  const body = p.el('fittings-copy-body').textContent;
  for (const ticket of ['ticket-1', 'unrelated-ticket', undefined]) {
    await p.progress({ kind: 'copy', phase: 'progress', ticket_id: ticket,
      completed: 99, total: 99, result: { ...current, fitting_name: 'Wrong fitting', status: 'success' } });
    assert.equal(p.el('fittings-copy-status').textContent, status);
    assert.equal(p.el('fittings-copy-body').textContent, body);
  }
  await p.route('main');
  await complete(p, { status: 'cancelled', write_count: 1, results: [current] }, 'ticket-2');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state(['other-fit']));
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-body').querySelector('.fit-copy-pair-name').textContent,
    'Sabre tackle (Flycatcher)', 'off-route results retain their own submitted hull snapshot');
  assert.deepEqual(p.errors, []);
});

async function beginCopy(p, ticket = 'ticket-1', acknowledge = true) {
  const selected = p.el('fittings-list').querySelector('input');
  selected.checked = true;
  selected.dispatchEvent({ type: 'change' });
  p.el('fittings-copy-selected').click();
  tick(p.el('fittings-copy-body').querySelector('input'));
  p.el('fittings-copy-review').click();
  await flush();
  await settle(p.last('fittings_preflight_copy'), preflight(ticket));
  p.el('fittings-copy-start').click();
  await settle(p.confirmations.at(-1), true);
  if (acknowledge) await settle(p.last('fittings_start_copy'), true);
}
function result(statuses) {
  return { status: 'complete', operation_id: 'op-1', write_count: 3,
    results: statuses.map(status => ({ fitting_name: 'Fit ' + status,
      character_name: 'Pilot', status, error: '',
      attempted: ['success', 'failed', 'unknown'].includes(status) })) };
}
async function complete(p, value, ticket = 'ticket-1') {
  await p.progress({ kind: 'copy', phase: 'complete', ticket_id: ticket, result: value });
}

test('mixed copy results summarize outcomes and give status-specific safe next steps', async () => {
  const p = await editor();
  await beginCopy(p);
  const before = p.calls().length;
  await complete(p, result(['success', 'present', 'conflict_skipped', 'failed',
                            'unknown', 'unattempted_throttle', 'cancelled', 'unavailable']));
  const body = p.el('fittings-copy-body');
  const summary = body.querySelector('.fit-copy-summary').textContent;
  assert.match(summary, /1 copied/);
  assert.match(summary, /1 already present/);
  assert.match(summary, /1 needs verification/);
  assert.match(summary, /1 failed/);
  assert.match(summary, /4 not copied/);
  const pairs = body.querySelectorAll('.fit-copy-pair');
  const expectations = [
    /Copied/, /Already present/, /alternate name.*review/i,
    /error.*refresh.*review/i, /check.*target.*EVE.*refresh.*before.*retry/i,
    /wait.*refresh.*review/i, /not attempted.*review/i, /refresh.*review/i
  ];
  pairs.forEach((pair, index) => assert.match(pair.textContent, expectations[index]));
  assert.doesNotMatch(pairs[0].textContent, /No action needed/i);
  assert.doesNotMatch(pairs[1].textContent, /No action needed/i);
  assert.ok(pairs[4].querySelector('.fit-copy-guidance'));
  assert.equal(p.calls().length, before, 'displaying advice must not issue any operation');
  assert.equal(body.querySelector('button'), null, 'no automatic retry control');
});

test('last results reopen session-only, with no preflight/start and no stale ticket interference', async () => {
  const p = await editor();
  assert.doesNotMatch(p.el('fittings-notices').textContent, /Last copy results/);
  await beginCopy(p);
  await complete(p, result(['unknown']));
  p.el('fittings-copy-close').click();
  const before = p.calls().length;
  const reopen = button(p.el('fittings-notices'), 'Last copy results\u2026');
  reopen.click();
  assert.equal(p.el('fittings-copy-overlay').hidden, false);
  assert.equal(p.el('fittings-copy-title').textContent, 'Copy results');
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
  assert.equal(p.el('fittings-copy-start').hidden, true);
  assert.equal(p.el('fittings-copy-review').hidden, true);
  assert.equal(p.calls().length, before);
  p.el('fittings-copy-close').click();
  await beginCopy(p, 'ticket-2');
  assert.ok(reopen.disabled || !p.el('fittings-notices').contains(reopen));
  // Even a detached old button must not switch the active copy to old results.
  reopen.click();
  await complete(p, result(['success']), 'ticket-1');
  assert.equal(p.el('fittings-copy-title').textContent, 'Copying fittings');
  assert.equal(p.calls('fittings_start_copy').length, 2);
  assert.deepEqual(p.last('fittings_start_copy').args, ['ticket-2']);
  await complete(p, result(['present']), 'ticket-2');
  p.el('fittings-copy-close').click();
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.match(p.el('fittings-copy-body').textContent, /Already present/);
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 0);
  assert.equal(p.calls('fittings_cancel_copy').length, 0);
  const fresh = await page();
  await fresh.route('fittings');
  await settle(fresh.last('fittings_state'), state());
  assert.doesNotMatch(fresh.el('fittings-notices').textContent, /Last copy results/);
});

for (const terminal of ['complete', 'cancelled']) {
  test(`off-route ${terminal} retains the latest copy outcome before its start acknowledgement`, async () => {
    const p = await editor();
    await beginCopy(p, 'ticket-a');
    const first = result(['success']);
    first.operation_id = 'operation-a';
    await complete(p, first, 'ticket-a');
    p.el('fittings-copy-close').click();
    await beginCopy(p, 'ticket-b', false);
    const start = p.last('fittings_start_copy');
    await p.route('main');
    assert.deepEqual(p.last('fittings_cancel_copy').args, ['ticket-b']);
    const title = p.el('fittings-copy-title').textContent;
    const body = p.el('fittings-copy-body').textContent;
    const latest = result(['unknown', 'cancelled']);
    latest.status = terminal;
    latest.operation_id = 'operation-b';
    latest.write_count = 1;
    await complete(p, latest, 'ticket-b');
    await settle(start, true);
    // Neither stale operations nor duplicate delivery can replace the accepted result.
    await complete(p, first, 'ticket-a');
    await complete(p, first, 'unrelated-ticket');
    await complete(p, first, 'ticket-b');
    assert.equal(p.el('fittings-copy-overlay').hidden, true);
    assert.equal(p.el('fittings-copy-title').textContent, title);
    assert.equal(p.el('fittings-copy-body').textContent, body);
    await p.route('fittings');
    await settle(p.last('fittings_state'), state());
    const before = p.calls().length;
    button(p.el('fittings-notices'), 'Last copy results\u2026').click();
    assert.equal(p.el('fittings-copy-overlay').hidden, false);
    assert.equal(p.el('fittings-copy-status').textContent, 'Operation operation-b');
    assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
    assert.match(p.el('fittings-copy-body').textContent, /check.*target.*refresh/is);
    assert.match(p.el('fittings-copy-body').textContent, /Cancelled/);
    assert.equal(p.calls().length, before, 'reopening must not issue another operation');
    assert.equal(p.calls('fittings_start_copy').length, 2);
    assert.equal(p.calls('fittings_cancel_copy').length, 1);
    assert.deepEqual(p.errors, []);
  });
}

test('return during cancellation keeps old history unavailable until the matching result arrives', async () => {
  const p = await editor();
  await beginCopy(p, 'ticket-a');
  await complete(p, result(['success']), 'ticket-a');
  p.el('fittings-copy-close').click();
  await beginCopy(p, 'ticket-b');
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  const reopen = button(p.el('fittings-notices'), 'Last copy results\u2026');
  assert.equal(reopen.disabled, true);
  reopen.click();
  assert.equal(p.el('fittings-copy-overlay').hidden, true);
  await complete(p, result(['unknown']), 'ticket-b');
  assert.equal(p.el('fittings-copy-overlay').hidden, true);
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
  assert.equal(p.calls('fittings_cancel_copy').length, 1);
});

test('late background completion cannot replace a newer started copy or its final history', async () => {
  const p = await editor();
  await beginCopy(p, 'ticket-a');
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  await beginCopy(p, 'ticket-b');
  const currentBody = p.el('fittings-copy-body').textContent;
  await complete(p, result(['unknown']), 'ticket-a');
  assert.equal(p.el('fittings-copy-title').textContent, 'Copying fittings');
  assert.equal(p.el('fittings-copy-body').textContent, currentBody);
  const latest = result(['present']);
  latest.operation_id = 'operation-b';
  await complete(p, latest, 'ticket-b');
  p.el('fittings-copy-close').click();
  await p.route('main');
  await complete(p, result(['unknown']), 'ticket-a');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-status').textContent, 'Operation operation-b');
  assert.match(p.el('fittings-copy-body').textContent, /Already present/);
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 0);
});

test('a refused start releases history availability but its later failure push remains eligible', async () => {
  const p = await editor();
  await beginCopy(p, 'ticket-a');
  await complete(p, result(['success']), 'ticket-a');
  p.el('fittings-copy-close').click();
  await beginCopy(p, 'ticket-b', false);
  const refused = p.last('fittings_start_copy');
  await p.route('main');
  await settle(refused, false);
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  assert.equal(button(p.el('fittings-notices'), 'Last copy results\u2026').disabled, false);
  // A worker-start failure can publish its terminal push after the boolean reply.
  await complete(p, { status: 'failed', operation_id: '', results: [], write_count: 0 }, 'ticket-b');
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-status').textContent, 'Failed');
});

test('an older start refusal cannot release the history guard of a newer pending copy', async () => {
  const p = await editor();
  await beginCopy(p, 'ticket-a');
  await complete(p, result(['success']), 'ticket-a');
  p.el('fittings-copy-close').click();
  await beginCopy(p, 'ticket-b', false);
  const olderStart = p.last('fittings_start_copy');
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  await beginCopy(p, 'ticket-c', false);
  await p.route('main');
  await settle(olderStart, false);
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  assert.equal(button(p.el('fittings-notices'), 'Last copy results\u2026').disabled, true);
  await complete(p, result(['unknown']), 'ticket-c');
  button(p.el('fittings-notices'), 'Last copy results\u2026').click();
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
  assert.deepEqual(p.errors, []);
});

for (const outcome of ['null', 'reject']) {
  test(`uncertain ${outcome} start reply still accepts the off-route terminal outcome`, async () => {
    const p = await editor();
    await beginCopy(p, 'ticket-a');
    await complete(p, result(['success']), 'ticket-a');
    p.el('fittings-copy-close').click();
    await beginCopy(p, 'ticket-b', false);
    const start = p.last('fittings_start_copy');
    await p.route('main');
    if (outcome === 'reject') start.reject(new Error('injected start reply failure'));
    else start.resolve(null);
    await flush();
    await p.route('fittings');
    await settle(p.last('fittings_state'), state());
    assert.equal(button(p.el('fittings-notices'), 'Last copy results\u2026').disabled, true);
    await complete(p, result(['unknown']), 'ticket-b');
    button(p.el('fittings-notices'), 'Last copy results\u2026').click();
    assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
    assert.equal(p.errors.length, outcome === 'reject' ? 1 : 0);
  });
}

function devScreenshot(stage) {
  const source = fs.readFileSync(path.join(web, 'dev.js'), 'utf8');
  const start = source.indexOf('  var DEV_FITTINGS_SCREENSHOT_FIXTURE =');
  const end = source.indexOf('  fittings.max_copy_writes =', start);
  const fixture = vm.runInNewContext(source.slice(start, end) + '\nDEV_FITTINGS_SCREENSHOT_FIXTURE;');
  if (stage) fixture.copy_stage = stage;
  return fixture;
}

test('refused screenshot injection and cleanup never cancel a genuine submitted copy', async () => {
  const p = await editor();
  await reviewCopy(p, preflight());
  await startReviewedCopy(p);
  const before = p.calls().length;
  await p.screenshot(devScreenshot('progress'));
  await p.screenshot({kind: 'fittings-screenshot-v1', clear: true});
  assert.match(p.el('fittings-copy-body').textContent, /0 of 1 pair checked/);
  assert.equal(p.el('fittings-copy-overlay').hidden, false);
  assert.equal(p.calls().length, before, 'refused cleanup cannot leave the real route or cancel');
  await complete(p, result(['success']));
  assert.match(p.el('fittings-copy-body').textContent, /1 copied/);
});

test('a confirmation begun before fixture injection cannot start after fixture teardown', async () => {
  const p = await editor();
  await reviewCopy(p, preflight());
  p.el('fittings-copy-start').click();
  const confirmation = p.confirmations.at(-1);
  const before = p.calls().length;
  await p.screenshot(devScreenshot('progress'));
  await p.screenshot({kind: 'fittings-screenshot-v1', clear: true});
  await settle(confirmation, true);
  assert.equal(p.calls().length, before);
  assert.equal(p.el('fittings-copy-overlay').hidden, true);
});

test('screenshot review counts classified ready pairs, not present or unavailable selections', async () => {
  const p = await page();
  await p.route('fittings');
  await p.screenshot(devScreenshot());
  const before = p.calls().length;
  p.el('fittings-list').querySelectorAll('.fit-row').forEach(row => {
    const name = row.querySelector('.fit-name').textContent;
    if (/Generated Fit 00[123]/.test(name)
        || (name === 'Fleet Doctrine Alpha' && /^On 1 character/.test(row.querySelector('.fit-meta').textContent))) {
      tick(row.querySelector('input'));
    }
  });
  p.el('fittings-copy-selected').click();
  const target = p.el('fittings-copy-body').querySelectorAll('.fit-copy-target')
    .find(row => row.textContent === 'Eryn Voss');
  tick(target.querySelector('input'));
  p.el('fittings-copy-review').click(); await flush();
  assert.match(p.el('fittings-copy-body').textContent, /2 additions planned.*1 already present.*1 unavailable/);
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.fit-copy-pair').length, 4);
  assert.equal(p.calls().length, before);
});

test('tooling-only screenshot results do not become real session history', async () => {
  const p = await editor();
  const fixtureState = state(Array.from({ length: 21 }, (_, index) => 'fixture-' + index));
  const outcome = result(['unknown']);
  outcome.results[0].entry_id = 'fixture-0';
  await p.screenshot({ kind: 'fittings-screenshot-v1', characters: fixtureState.characters,
    collections: fixtureState.collections, entries: fixtureState.rows, details: {},
    mixed_preflight: { pairs: [] }, copy_result: outcome, copy_stage: 'results' });
  assert.equal(p.el('fittings-copy-body').querySelectorAll('.unknown').length, 1);
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  assert.doesNotMatch(p.el('fittings-notices').textContent, /Last copy results/);
  assert.equal(p.calls('fittings_start_copy').length, 0);
  assert.equal(p.calls('fittings_cancel_copy').length, 0);
});

test('a screenshot fixture cannot prune genuine unsaved metadata', async () => {
  const p = await editor();
  input(p.el('fit-name-fit-1'), 'Real draft');
  const fixtureState = state(Array.from({ length: 21 }, (_, index) => 'fixture-' + index));
  await p.screenshot({ kind: 'fittings-screenshot-v1', characters: fixtureState.characters,
    collections: fixtureState.collections, entries: fixtureState.rows, details: {},
    mixed_preflight: { pairs: [] }, copy_result: { results: [] } });
  await p.route('main');
  await p.route('fittings');
  await settle(p.last('fittings_state'), state());
  p.el('fittings-list').querySelector('.fit-row-toggle').click();
  await flush();
  await settle(p.last('fittings_detail'), detail());
  assertDraft(p, 'Real draft', 'Saved description');
});

test('partial cancellation does not describe the whole operation as unattempted', async () => {
  const p = await editor();
  await beginCopy(p);
  const value = result(['success', 'cancelled']);
  value.status = 'cancelled';
  value.write_count = 1;
  await complete(p, value);
  const body = p.el('fittings-copy-body');
  assert.match(body.querySelector('.fit-copy-summary').textContent, /1 copied.*1 not copied/);
  const operationNotice = body.querySelector('.notice');
  assert.ok(!operationNotice || !/Not attempted/.test(operationNotice.textContent));
  assert.match(body.querySelectorAll('.fit-copy-pair')[1].textContent, /Not attempted/);
});

test('non-deployable status is separate from truncating row metadata', async () => {
  const p = await page();
  await p.route('fittings');
  const payload = state(['fit-1', 'fit-2']);
  payload.rows[0].deployable = false;
  payload.rows[0].collection_ids = ['doctrine'];
  payload.rows[0].ship_name = '';
  payload.rows[0].name = 'A long doctrine name that must not hide deployment status';
  await settle(p.last('fittings_state'), payload);
  const rows = p.el('fittings-list').querySelectorAll('.fit-row');
  const status = rows[0].querySelector('.fit-deployability');
  assert.ok(status, 'deployment status needs its own visible element');
  assert.match(status.textContent, /Not deployable/i);
  assert.equal(status.hidden, false);
  assert.equal(rows[0].querySelector('.fit-meta').contains(status), false);
  assert.doesNotMatch(rows[0].querySelector('.fit-meta').textContent, /Not deployable/i);
  assert.match(rows[0].querySelector('.fit-ship').textContent, /Type 22456/);
  assert.equal(rows[1].querySelector('.fit-deployability'), null);
  assert.deepEqual(p.errors, []);
});

for (const limit of [7, undefined]) {
  test(`copy limit ${limit} is advisory before review, never a raw-selection gate`, async () => {
    const p = await page();
    await p.route('fittings');
    const payload = state(Array.from({ length: 21 }, (_, index) => 'fit-' + index));
    if (limit !== undefined) payload.max_copy_writes = limit;
    payload.characters.push({ ...payload.characters[0], character_id: 43, character_name: 'Second pilot' });
    await settle(p.last('fittings_state'), payload);
    p.el('fittings-list').querySelectorAll('input').forEach(tick);
    p.el('fittings-copy-selected').click();
    const body = p.el('fittings-copy-body');
    const advisory = body.querySelector('.fit-copy-limit');
    if (limit !== undefined) {
      assert.ok(advisory, 'show the controller limit before Review');
      assert.match(advisory.textContent, /7.*additions.*across.*targets/i);
      assert.match(advisory.textContent, /review.*new additions/i);
    } else {
      assert.equal(advisory, null, 'missing metadata must not invent a numeric limit');
    }
    assert.doesNotMatch(body.textContent, /undefined|NaN/);
    assert.equal(p.el('fittings-copy-review').disabled, true);
    const targets = body.querySelectorAll('input');
    tick(targets[0]);
    tick(targets[1]);
    assert.equal(p.el('fittings-copy-review').disabled, false);
    p.el('fittings-copy-review').click();
    await flush();
    assert.equal(p.last('fittings_preflight_copy').args[0].length, 21);
    assert.deepEqual(Array.from(p.last('fittings_preflight_copy').args[1]), [42, 43]);
    await settle(p.last('fittings_preflight_copy'), preflight());
    assert.equal(p.el('fittings-copy-start').hidden, false);
    assert.equal(p.calls('fittings_start_copy').length, 0);
    assert.deepEqual(p.errors, []);
  });
}

test('unavailable copy targets point to authentication or refresh without changing eligibility', async () => {
  const p = await page();
  await p.route('fittings');
  const payload = state();
  payload.characters = [
    { ...payload.characters[0], status: 'enable' },
    { ...payload.characters[0], character_id: 43, status: 'reauthenticate' },
    { ...payload.characters[0], character_id: 44, fetched_utc: '' },
    { ...payload.characters[0], character_id: 45, stale: true }
  ];
  await settle(p.last('fittings_state'), payload);
  tick(p.el('fittings-list').querySelector('input'));
  p.el('fittings-copy-selected').click();
  const targets = p.el('fittings-copy-body').querySelectorAll('.fit-copy-target');
  targets.forEach(target => assert.equal(target.querySelector('input').disabled, true));
  for (const target of targets.slice(0, 2)) {
    assert.match(target.textContent, /Authenticate character.*Settings.*Character access/i);
    assert.doesNotMatch(target.textContent, /enable Fittings|Fittings not enabled/i);
  }
  for (const target of targets.slice(2)) assert.match(target.textContent, /Refresh characters/);
  assert.equal(p.el('fittings-copy-review').disabled, true);
  assert.equal(p.calls('fittings_preflight_copy').length, 0);
});

test('copy recovery labels keep semantic outcomes and point to real authentication', async () => {
  const p = await editor();
  await beginCopy(p);
  const value = result(['success', 'unknown', 'unattempted_throttle', 'unavailable']);
  value.results[1].error = 'The request timed out before a response arrived.';
  const before = p.calls().length;
  await complete(p, value);
  const body = p.el('fittings-copy-body');
  const labels = body.querySelectorAll('.fit-copy-result');
  assert.equal(labels[0].textContent, 'Copied');
  assert.equal(labels[1].textContent, 'Needs verification');
  assert.equal(labels[1].classList.contains('unknown'), true);
  assert.match(labels[2].textContent, /Not attempted.*rate limit/i);
  assert.equal(labels[2].classList.contains('unattempted_throttle'), true);
  assert.match(body.querySelector('.fit-copy-summary').textContent, /1 needs verification/);
  const rows = body.querySelectorAll('.fit-copy-pair');
  assert.match(rows[1].textContent, /request timed out/);
  assert.match(rows[1].querySelector('.fit-copy-guidance').textContent, /Personal Fittings.*EVE.*refresh.*before.*retry/i);
  assert.match(rows[3].querySelector('.fit-copy-guidance').textContent, /Authenticate character.*Settings.*Character access/);
  assert.equal(p.calls().length, before);
  assert.equal(body.querySelector('button'), null);
});

test('empty worker refusal is explained without claiming successful completion', async () => {
  const p = await editor();
  await beginCopy(p);
  await complete(p, { status: 'invalid_ticket', operation_id: '', results: [], write_count: 0 });
  assert.match(p.el('fittings-copy-body').textContent, /expired.*review/i);
  assert.doesNotMatch(p.el('fittings-copy-body').textContent, /all.*copied/i);
  assert.equal(p.calls('fittings_start_copy').length, 1);
});
