// Real app.js route/bridge and fleetsharing.js, with DOM and delivery seams only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const scenario = process.argv[3];
const web = process.argv[4];
let activeElement = null;
class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase(); this.attrs = {...attrs};
    this.id = attrs.id || ''; this.className = attrs.class || '';
    this.children = []; this.listeners = {}; this.value = attrs.value || '';
    this.disabled = 'disabled' in attrs; this.hidden = 'hidden' in attrs;
    this.checked = 'checked' in attrs; this.open = 'open' in attrs;
    this.dataset = Object.fromEntries(Object.entries(attrs).filter(([k]) => k.startsWith('data-')).map(([k, v]) => [k.slice(5), v]));
  }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
  set value(value) {
    if (this.tagName === 'SELECT') {
      // Native selects cannot remember a value with no matching option.
      this.selectedOption = this.children.find(option => option.value === String(value)) || null;
    } else this._value = String(value);
  }
  get value() {
    if (this.tagName === 'SELECT') return this.children.includes(this.selectedOption) ? this.selectedOption.value : '';
    return this._value || '';
  }
  set disabled(value) {
    this._disabled = Boolean(value);
    if (this._disabled && activeElement === this) activeElement = null;
  }
  get disabled() { return this._disabled; }
  get options() { return this.children; }
  get firstChild() { return this.children[0]; }
  get lastChild() { return this.children[this.children.length - 1]; }
  contains(node) { return this === node || this.children.some(child => child.contains(node)); }
  focus() { if (!this.disabled && !this.hidden) document.activeElement = this; }
  remove() {
    if (this.contains(document.activeElement)) document.activeElement = document;
    this.parentNode.children = this.parentNode.children.filter(c => c !== this);
    this.parentNode = null;
  }
  insertBefore(child, before) { if (child.parentNode) child.remove(); const i = this.children.indexOf(before); this.children.splice(i < 0 ? this.children.length : i, 0, child); child.parentNode = this; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return (this.text || '') + this.children.map(c => c.textContent).join(''); }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  getAttribute(key) { return this.attrs[key] ?? null; }
  get classList() { return {toggle: (key, on) => {
    const classes = this.className.split(/\s+/).filter(c => c && c !== key);
    if (on) classes.push(key); this.className = classes.join(' ');
  }}; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  dispatchEvent(event) { event.target ||= this; (this.listeners[event.type] || []).forEach(fn => fn(event)); }
  querySelectorAll(selector) {
    const all = this.children.flatMap(c => [c, ...c.querySelectorAll('*')]);
    if (selector === '*') return all;
    if (selector === 'button, input, select') return all.filter(c => ['BUTTON', 'INPUT', 'SELECT'].includes(c.tagName));
    if (selector === '.settings-pane > .settings') return all.filter(c => c.className.split(/\s+/).includes('settings') && c.parentNode.className.split(/\s+/).includes('settings-pane'));
    assert.match(selector, /^\.[\w-]+$/);
    return all.filter(c => c.className.split(/\s+/).includes(selector.slice(1)));
  }
}
const ids = {};
function build(node) {
  const el = new Element(node.tag, node.attrs); el.text = node.text || '';
  if (el.id) ids[el.id] = el;
  node.children.forEach(child => el.appendChild(build(child)));
  return el;
}
const document = build(input.page);
document.hidden = false;
Object.defineProperty(document, 'activeElement', {get: () => activeElement, set: value => { activeElement = value; }});
document.getElementById = id => ids[id] || null;
document.createElement = tag => new Element(tag);
const window = new Element('window');
const calls = [];
const api = {};
for (const method of ['fleet_sharing_watch', 'fleet_sharing_set_enabled', 'fleet_sharing_pair', 'fleet_sharing_start_source', 'fleet_sharing_stop_source', 'fleet_sharing_grant_fleet_read']) {
  api[method] = (...args) => new Promise((resolve, reject) => calls.push({method, args, resolve, reject}));
}
for (const method of ['list_rows', 'get_settings', 'update_status']) api[method] = () => Promise.resolve(null);
window.pywebview = {api};
const errors = [];
const runtime = vm.createContext({window, document, Promise, console: {error: (...args) => errors.push(args), warn: (...args) => errors.push(args)},
  CustomEvent: class {constructor(type, options) { this.type = type; this.detail = options.detail; }}});
vm.runInContext(fs.readFileSync(web + '/app.js', 'utf8'), runtime);
const WM = runtime.WM = window.WM;
vm.runInContext(fs.readFileSync(web + '/fleetsharing.js', 'utf8'), runtime);
const turn = () => new Promise(resolve => setImmediate(resolve));
const watches = () => calls.filter(c => c.method === 'fleet_sharing_watch');
const mutationCount = () => calls.filter(c => c.method !== 'fleet_sharing_watch').length;
function attemptMutations() {
  ids['sharing-enabled'].dispatchEvent({type: 'change'});
  ids['sharing-confirm-on'].dispatchEvent({type: 'click'});
  ids['sharing-connect'].dispatchEvent({type: 'click'});
  ids['sharing-start'].dispatchEvent({type: 'click'});
}
function unavailable() {
  assert.match(ids['sharing-connection'].textContent, /unavailable in this session/i);
  assert.doesNotMatch(ids['sharing-connection'].textContent, /Reading|Refresh/);
  for (const id of ['sharing-enabled', 'sharing-connect', 'sharing-refresh', 'sharing-boss', 'sharing-start', 'sharing-grant']) assert.equal(ids[id].disabled, true, id);
}
const A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const C = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
let order = input.live.presentation_order;
const clone = value => JSON.parse(JSON.stringify(value));
function source(id, state = 'ended', reason = 'pending_expired', character_id = 1) {
  return {source_id: id, generation: 1, character_id, state, reason, pending_expires_at: null};
}
function pending(id, operation, stage = 'queued') {
  return {source_id: id, operation, stage, character_id: operation === 'start' ? 1 : null};
}
function payload(rows = [], changes = {}) {
  return {...clone(input.live), presentation_order: ++order,
    sources: {characters: clone(input.live.sources.characters), sources: rows},
    pending_sources: [], source_results: [], ...changes};
}
function push(value) { window.onFleetSharingState(value); }
const currentRows = () => ids['sharing-sources'].children;
const historyRows = () => ids['sharing-history-sources'].children;
const status = () => ids['sharing-source-status'].textContent;
const feedback = () => ids['sharing-action'].textContent;
function counts(current, history) {
  assert.equal(currentRows().length, current, 'primary source count');
  assert.equal(historyRows().length, history, 'previous attempt count');
  assert.equal(ids['sharing-history'].hidden, history === 0);
  assert.equal(ids['sharing-history-summary'].textContent, 'Previous attempts (' + history + ')');
}
function chooseBoss() {
  ids['sharing-boss'].value = '1';
  ids['sharing-boss'].dispatchEvent({type: 'change'});
}
async function enterAgain(reply = null) {
  WM.openSettingsSection('fleet'); await turn();
  watches().at(-1).resolve(reply); await turn();
}
async function leave() {
  WM.route('main'); await turn();
  watches().at(-1).resolve(null); await turn();
}
async function historyScenario(first) {
  first.resolve({queued: true, state: payload()}); await turn();
  const history = ids['sharing-history'];
  if (scenario === 'scope-copy') {
    const local = ids['fleetbar-characters'];
    assert.match(local.firstChild.textContent, /Show.*characters.*Fleet Bar/i);
    const localScope = ids['fleetbar-character-scope'];
    assert.ok(localScope && local.contains(localScope), 'visibility scope stays with the character controls');
    assert.match(localScope.textContent, /local display only/i);
    assert.match(localScope.textContent, /not.*collection.*sharing/i);
    const sharedScope = ids[ids['sharing-enabled'].getAttribute('aria-describedby')];
    assert.ok(sharedScope, 'sharing switch describes its transmission scope');
    assert.match(sharedScope.textContent, /current DPS.*scram.*point/i);
    assert.match(sharedScope.textContent, /eligible.*same.*fleet/i);
    assert.match(sharedScope.textContent, /never raw logs or history/i);
    for (let node = sharedScope; node; node = node.parentNode) {
      assert.notEqual(node.tagName, 'DETAILS', 'transmission scope cannot require opening a disclosure');
      assert.equal(node.hidden, false);
    }
    assert.equal(mutationCount(), 0);
  } else if (scenario === 'verification-scope') {
    push(payload([source(A, 'active', null), source(B)], {pending_sources: [pending(C, 'start')]}));
    counts(2, 1);
    const card = ids['fleet-sharing'];
    const order = card.querySelectorAll('*');
    assert.ok(order.indexOf(ids['sharing-sources']) < order.indexOf(ids['sharing-boss']),
      'current/pending verification precedes selection for a new attempt');
    const headings = order.filter(node => node.tagName === 'H3');
    assert.match(headings[0].textContent, /current.*pending.*verification/i);
    const label = order.find(node => node.getAttribute('for') === 'sharing-boss');
    assert.match(label.textContent, /boss.*new attempt/i);
    assert.match(ids['sharing-grant-status'].textContent, /Choose.*boss/i);
    assert.doesNotMatch(ids['sharing-boss'].options[0].textContent, /Choose/i,
      'the selector need not repeat its disabled-action guidance');
    assert.equal(ids['sharing-start'].disabled, true);
    chooseBoss();
    assert.equal(ids['sharing-start'].disabled, false);
    assert.equal(currentRows()[0].lastChild.disabled, false, 'source Stop remains independent');
    assert.equal(mutationCount(), 0, 'boss selection cannot alter current verification');
    push(payload([source(B)])); counts(0, 1);
    assert.match(status(), /No current verification.*pending expired/);
    assert.match(status(), /Start verification below/);
    assert.doesNotMatch(status(), /Choose.*boss/i);
  } else if (scenario === 'mixed-history') {
    push(payload([source(A, 'active', null), source(B), source(C)]));
    counts(1, 2); assert.equal(history.open, false);
    assert.equal(currentRows()[0].getAttribute('data-source'), A);
    assert.match(historyRows()[0].textContent, /Alice.*ended.*pending expired/);
    assert.equal(mutationCount(), 0);
  } else if (scenario === 'ended-only') {
    push(payload([source(C), source(A), source(B, 'ended', 'stopped')]));
    counts(0, 3);
    assert.match(status(), /No current verification/);
    assert.match(status(), /pending expired \(2\)/);
    assert.match(status(), /stopped \(1\)/);
    assert.match(status(), /Start verification below/);
    assert.doesNotMatch(status(), /latest|recent|failed|failure/i);
    push(payload()); counts(0, 0);
    assert.match(status(), /No sources reported/);
    assert.doesNotMatch(status(), /No current verification|unknown/i);
  } else if (scenario === 'ended-prerequisites') {
    const ended = [source(A)];
    const noOwned = payload(ended); noOwned.sources.characters = [];
    push(noOwned); assert.match(status(), /No owned characters/);
    assert.doesNotMatch(status(), /then Start verification/);
    const noGrant = payload(ended); noGrant.sources.characters[0].has_fleet_read = false;
    push(noGrant);
    assert.match(status(), /[Gg]rant Fleet Read/, 'missing Fleet Read needs guidance even before selection');
    chooseBoss(); assert.match(status(), /[Gg]rant Fleet Read/);
    assert.equal(ids['sharing-start'].disabled, true);
    const disconnected = payload([], {metadata: {...input.live.metadata, binding: null}});
    push(disconnected); assert.match(status(), /Connect/);
  } else if (scenario === 'pending-precedence') {
    for (const operation of ['start', 'stop']) {
      for (const stage of ['queued', 'persisted']) {
        push(payload([source(A.toUpperCase())], {pending_sources: [pending(A, operation, stage)],
          source_results: [pending(A.toUpperCase(), 'start', 'expired')]}));
        counts(1, 0);
        assert.equal(currentRows()[0].getAttribute('data-source'), A);
        assert.match(currentRows()[0].textContent, operation === 'start' ? /Start/ : /Stop/);
        assert.match(currentRows()[0].textContent, stage === 'queued' ? /queued locally/ : /saved, awaiting authGD/);
      }
    }
    const row = currentRows()[0];
    push(payload([source(A)])); counts(0, 1);
    assert.equal(historyRows()[0], row, 'settlement reuses the keyed row');
  } else if (scenario === 'local-results') {
    push(payload([], {source_results: [pending(A, 'start', 'rejected'), pending(B, 'start', 'expired')]}));
    counts(2, 0);
    assert.match(currentRows()[0].textContent, /Start not saved.*Start.*again/i);
    assert.match(currentRows()[1].textContent, /Start expired.*Start again explicitly/);
    assert.ok(currentRows().every(row => row.lastChild.disabled));
    push(payload([source(A.toUpperCase())], {source_results: [pending(A, 'start', 'expired')]}));
    counts(0, 1); assert.equal(historyRows()[0].getAttribute('data-source'), A);
    push(payload([source(A.toUpperCase(), 'active', null)], {source_results: [pending(A, 'start', 'expired')]}));
    counts(1, 0); assert.equal(currentRows()[0].lastChild.disabled, false, 'an observed active source supersedes its old local result');
  } else if (scenario === 'retained-unknown') {
    push(payload([source(A)])); history.open = true; const row = historyRows()[0];
    chooseBoss();
    push(payload([], {sources: null, eligibility: null, metadata: {...input.live.metadata, has_session: false},
      pending_sources: [pending(A, 'stop', 'persisted')]}));
    counts(1, 0); assert.equal(currentRows()[0], row);
    assert.match(row.textContent, /last.known/i);
    assert.match(row.textContent, /Stop saved, awaiting authGD/);
    assert.equal(ids['sharing-start'].disabled, true);
    assert.equal(ids['sharing-boss'].disabled, true);
    push(payload([], {sources: null, eligibility: null})); counts(0, 1);
    assert.equal(historyRows()[0], row); assert.equal(history.open, true);
    assert.match(status(), /Current source state unknown/);
    assert.doesNotMatch(status(), /No current verification/);
    push(payload([], {pending_sources: [pending(B, 'start')]})); counts(1, 0);
    assert.equal(currentRows()[0].getAttribute('data-source'), B);
    assert.doesNotMatch(status(), /unknown/i);
  } else if (scenario === 'failed-refresh-history') {
    push(payload([source(A, 'active', null), source(B)], {eligibility: {
      participation_generation: 1, state: 'ready', characters: [{character_id: 1, source_id: A,
        source_generation: 1, authority_generation: 1, expires_at: '2026-09-07T12:05:00.000Z'}]}})); chooseBoss();
    assert.match(ids['sharing-eligible-list'].textContent, /Alice/);
    history.open = true; const row = historyRows()[0];
    ids['sharing-refresh'].dispatchEvent({type: 'click'}); await turn();
    watches().at(-1).resolve(null); await turn();
    counts(1, 1); assert.equal(historyRows()[0], row); assert.equal(history.open, true);
    assert.match(status(), /Current source state unknown/);
    assert.match(row.textContent, /last.known/i);
    assert.match(ids['sharing-connection'].textContent, /refresh.*failed|could not refresh/i);
    assert.equal(ids['sharing-start'].disabled, true);
    assert.equal(currentRows()[0].lastChild.disabled, true);
    assert.equal(ids['sharing-eligible-list'].children.length, 0, 'a failed read cannot claim last-known eligibility is current');
    push(payload([], {available: false, sources: null})); counts(1, 1); unavailable();
    push(payload([])); counts(0, 0);
    assert.doesNotMatch(ids['sharing-connection'].textContent, /refresh.*failed|could not refresh/i);
  } else if (scenario === 'binding-invalidation') {
    push(payload([source(A)])); chooseBoss(); history.open = true;
    const oldRow = historyRows()[0];
    push(payload([], {metadata: {...input.live.metadata, binding: 'new-binding'}, sources: null}));
    counts(0, 0); assert.equal(history.open, false); assert.equal(ids['sharing-boss'].value, '');
    push(payload([source(A)], {metadata: {...input.live.metadata, binding: 'new-binding'}}));
    counts(0, 1); assert.notEqual(historyRows()[0], oldRow);
  } else if (scenario === 'bridge-source-rejection') {
    chooseBoss(); ids['sharing-start'].dispatchEvent({type: 'click'}); await turn();
    assert.match(feedback(), /Start request.*progress/i);
    calls.find(c => c.method === 'fleet_sharing_start_source').reject(new Error('controlled Start failure'));
    await turn();
    assert.doesNotMatch(feedback(), /progress/i);
    assert.match(feedback(), /could not be queued/i);
    push(payload([source(A, 'active', null)]));
    currentRows()[0].lastChild.dispatchEvent({type: 'click'}); await turn();
    push(payload([source(A)])); counts(1, 0);
    calls.find(c => c.method === 'fleet_sharing_stop_source').reject(new Error('controlled Stop failure'));
    await turn(); counts(0, 1);
    assert.doesNotMatch(historyRows()[0].textContent, /request.*progress/i);
    assert.match(feedback(), /could not be queued/i);
    const message = ids['sharing-action'];
    const card = ids['fleet-sharing'];
    const order = card.querySelectorAll('*');
    assert.equal(message.getAttribute('role'), 'status');
    assert.equal(message.parentNode, card, 'shared feedback stays outside disclosures and forms');
    assert.ok(order.filter(node => node.tagName === 'H3').every(heading => order.indexOf(message) < order.indexOf(heading)),
      'rejected Stop feedback belongs to the account-wide area, before verification subsections');
  } else if (scenario === 'inflight-stop') {
    push(payload([source(A.toUpperCase(), 'active', null)]));
    const row = currentRows()[0]; row.lastChild.focus(); row.lastChild.dispatchEvent({type: 'click'}); await turn();
    const request = calls.find(c => c.method === 'fleet_sharing_stop_source');
    assert.equal(request.args[0].toLowerCase(), A);
    push(payload([source(A)])); counts(1, 0);
    assert.match(row.textContent, /Stop request.*progress|Requesting Stop/i);
    const queued = payload([source(A)], {pending_sources: [pending(A, 'stop', 'persisted')]});
    request.resolve({queued: true, source_id: A, state: queued}); await turn();
    counts(1, 0); assert.match(row.textContent, /Stop saved, awaiting authGD/);
    push(payload([source(A)])); counts(0, 1); assert.equal(historyRows()[0], row);
    assert.ok(document.activeElement === ids['sharing-history-summary'], 'a focused Stop settles onto the visible history summary');
  } else if (scenario === 'inflight-start-leave') {
    chooseBoss(); ids['sharing-start'].dispatchEvent({type: 'click'}); await turn();
    const request = calls.find(c => c.method === 'fleet_sharing_start_source');
    assert.match(feedback(), /Alice.*Start|Start.*Alice/); counts(0, 0);
    const staleReply = payload([], {pending_sources: [pending(A, 'start')]});
    push(payload([source(A)])); counts(0, 1);
    assert.match(feedback(), /Alice.*Start|Start.*Alice/);
    await leave();
    request.resolve({queued: true, source_id: A, state: staleReply}); await turn();
    await enterAgain({state: payload([source(A)])}); counts(0, 1);
    assert.doesNotMatch(feedback(), /progress|Requesting/i);
    // A second reply delivered while hidden must hydrate pending worker work,
    // not be discarded merely because it cannot paint at that instant.
    chooseBoss(); ids['sharing-start'].dispatchEvent({type: 'click'}); await turn();
    const second = calls.filter(c => c.method === 'fleet_sharing_start_source')[1];
    await leave();
    second.resolve({queued: true, source_id: B, state: payload([source(A)], {pending_sources: [pending(B, 'start')]})}); await turn();
    await enterAgain(); counts(1, 1);
    assert.match(currentRows()[0].textContent, /Start queued locally/);
    assert.match(feedback(), /Start requested/);
  } else if (scenario === 'inflight-binding-reply') {
    chooseBoss(); ids['sharing-start'].dispatchEvent({type: 'click'}); await turn();
    const oldRequest = calls.find(c => c.method === 'fleet_sharing_start_source');
    await leave();
    const newMeta = {...input.live.metadata, binding: 'new-binding'};
    push(payload([], {metadata: newMeta}));
    await enterAgain({state: payload([], {metadata: newMeta})}); chooseBoss();
    ids['sharing-start'].dispatchEvent({type: 'click'}); await turn();
    assert.match(feedback(), /Alice.*Start|Start.*Alice/);
    const before = feedback();
    oldRequest.resolve({queued: true, source_id: A, state: payload([source(A)])}); await turn();
    counts(0, 0); assert.equal(feedback(), before, 'old binding cannot clear a new request');
    calls.filter(c => c.method === 'fleet_sharing_start_source')[1].resolve({queued: false, error: 'New request refused.'}); await turn();
    assert.match(feedback(), /New request refused/);
    assert.doesNotMatch(feedback(), /progress|Requesting/i);
  } else if (scenario === 'stable-history-focus') {
    const stable = [source(A, 'active', null), source(B)];
    const long = payload(stable); long.sources.characters[0].character_name = '<b>' + 'Long name '.repeat(20) + '</b>';
    push(long); chooseBoss(); history.open = true;
    const row = currentRows()[0]; const oldHistory = historyRows()[0];
    row.lastChild.focus();
    push({...clone(long), presentation_order: ++order});
    assert.equal(document.activeElement, row.lastChild);
    assert.equal(currentRows()[0], row); assert.equal(historyRows()[0], oldHistory);
    assert.equal(history.open, true); assert.equal(ids['sharing-boss'].value, '1');
    assert.match(row.firstChild.textContent, /<b>Long name/);
    assert.equal(row.firstChild.children.length, 0, 'external identity is text, not HTML');
    await leave();
    WM.openSettingsSection('fleet'); await turn();
    watches().at(-1).resolve({queued: true, state: {...clone(long), presentation_order: ++order}}); await turn();
    assert.equal(history.open, true); assert.equal(ids['sharing-boss'].value, '1');
    history.open = false; row.lastChild.focus();
    push(payload([source(A), source(B)])); counts(0, 2);
    assert.equal(document.activeElement, ids['sharing-history-summary']);
    // The fallback also applies to a now-disabled Stop in open history.
    push(payload(stable)); history.open = true; currentRows()[0].lastChild.focus();
    push(payload([source(A), source(B)]));
    assert.equal(document.activeElement, ids['sharing-history-summary']);
    ids['sharing-boss'].focus(); push(payload(stable)); push(payload([source(A), source(B)]));
    assert.equal(document.activeElement, ids['sharing-boss'], 'unfocused settlement never steals focus');
  } else if (scenario === 'retained-local-result') {
    push(payload([source(A)])); const row = historyRows()[0];
    push(payload([], {sources: null, source_results: [pending(A.toUpperCase(), 'start', 'expired')]}));
    counts(1, 0);
    assert.ok(currentRows()[0] === row, 'a local result reuses the retained observation row');
    assert.match(row.textContent, /Start expired.*Start again explicitly/);
    assert.match(status(), /Current source state unknown/);
    push(payload([source(A)])); counts(0, 1);
  } else if (scenario === 'concurrent-stop-replies') {
    push(payload([source(A, 'active', null), source(B, 'active', null)]));
    currentRows()[0].lastChild.dispatchEvent({type: 'click'});
    currentRows()[1].lastChild.dispatchEvent({type: 'click'}); await turn();
    const requests = calls.filter(c => c.method === 'fleet_sharing_stop_source');
    push(payload([source(A), source(B)])); counts(2, 0);
    requests[0].resolve({queued: true, source_id: A, state: payload([source(A), source(B)], {pending_sources: [pending(A, 'stop', 'persisted')]})}); await turn();
    counts(2, 0);
    assert.match(currentRows()[0].textContent, /Stop saved, awaiting authGD/);
    assert.match(currentRows()[1].textContent, /Stop request in progress/);
    requests[1].resolve({queued: false, error: 'Second Stop refused.'}); await turn();
    counts(1, 1); assert.match(feedback(), /Second Stop refused/);
    push(payload([source(A), source(B)])); counts(0, 2);
  } else if (scenario === 'inflight-reenter') {
    chooseBoss(); ids['sharing-start'].dispatchEvent({type: 'click'}); await turn();
    await leave();
    await enterAgain({state: payload()});
    assert.match(feedback(), /Alice.*Start|Start.*Alice/); counts(0, 0);
    await leave();
    calls.find(c => c.method === 'fleet_sharing_start_source').resolve({queued: false, error: 'Choose an owned boss with usable Fleet Read.'}); await turn();
    await enterAgain({state: payload()});
    assert.match(feedback(), /Choose an owned boss with usable Fleet Read/);
    assert.doesNotMatch(feedback(), /progress|Requesting/i);
    assert.equal(mutationCount(), 1, 'navigation never retries activation');
  } else if (scenario === 'stale-preference-after-failed-refresh' || scenario === 'equal-preference-after-failed-refresh') {
    const rows = [source(A, 'active', null), source(B)];
    push(payload(rows)); chooseBoss(); history.open = true;
    const row = currentRows()[0]; const oldHistory = historyRows()[0];
    ids['sharing-enabled'].checked = true;
    ids['sharing-enabled'].dispatchEvent({type: 'change'}); await turn();
    const preference = calls.find(c => c.method === 'fleet_sharing_set_enabled');
    const oldReply = payload(rows, {enabled: true});
    const pushed = scenario === 'equal-preference-after-failed-refresh' ? clone(oldReply) : payload(rows, {enabled: true});
    push(pushed);
    ids['sharing-refresh'].dispatchEvent({type: 'click'}); await turn();
    if (scenario === 'equal-preference-after-failed-refresh') push(clone(pushed));
    watches().at(-1).resolve(null); await turn();
    assert.match(status(), /Current source state unknown/);
    assert.equal(row.lastChild.disabled, true);
    preference.resolve({applied: true, persisted: true, state: oldReply}); await turn();
    assert.match(status(), /Current source state unknown/, 'a stale preference reply is not a successful source refresh');
    assert.match(ids['sharing-connection'].textContent, /could not refresh/i);
    for (const id of ['sharing-boss', 'sharing-start', 'sharing-grant']) assert.equal(ids[id].disabled, true, id);
    assert.equal(row.lastChild.disabled, true);
    assert.match(row.textContent, /last.known/i);
    assert.ok(currentRows()[0] === row && historyRows()[0] === oldHistory);
    assert.equal(history.open, true);
    assert.equal(ids['sharing-enabled'].checked, true);
    assert.equal(ids['sharing-enabled'].disabled, false, 'Off remains reachable');
    ids['sharing-start'].dispatchEvent({type: 'click'}); row.lastChild.dispatchEvent({type: 'click'}); await turn();
    assert.equal(mutationCount(), 1, 'unknown source controls cannot submit after a stale preference reply');
    if (scenario === 'equal-preference-after-failed-refresh') {
      push(clone(pushed));
      assert.match(status(), /Current source state unknown/, 'an identical delayed push cannot clear failed-read state');
      ids['sharing-refresh'].dispatchEvent({type: 'click'}); await turn();
      watches().at(-1).resolve({state: clone(pushed)}); await turn();
    } else push(payload(rows, {enabled: true}));
    assert.equal(ids['sharing-start'].disabled, false, 'a newer snapshot or successful fresh read restores authority');
    assert.doesNotMatch(status(), /unknown/i);
  } else if (scenario === 'boss-selection-across-unknown') {
    chooseBoss(); assert.equal(ids['sharing-boss'].value, '1');
    const unknown = () => payload([], {sources: null, eligibility: null});
    push(unknown()); push(unknown());
    for (const id of ['sharing-boss', 'sharing-start', 'sharing-grant']) assert.equal(ids[id].disabled, true, id);
    assert.equal(ids['sharing-boss'].value, '', 'unknown roster has no authoritative selectable boss');
    assert.equal(ids['sharing-boss'].options.some(option => option.value === '1'), false);
    ids['sharing-start'].dispatchEvent({type: 'click'}); ids['sharing-grant'].dispatchEvent({type: 'click'}); await turn();
    assert.equal(mutationCount(), 0);
    await leave(); await enterAgain({state: unknown()});
    push(payload());
    assert.equal(ids['sharing-boss'].value, '1', 'same-binding authoritative roster restores the desired boss');
    assert.equal(ids['sharing-start'].disabled, false);
    // Fresh authority can revoke Fleet Read without discarding the choice.
    push(unknown()); const revoked = payload(); revoked.sources.characters[0].has_fleet_read = false;
    push(revoked); assert.equal(ids['sharing-boss'].value, '1'); assert.equal(ids['sharing-start'].disabled, true);
    // A confirmed absence clears the remembered choice even if delivered while hidden.
    await leave();
    const absent = payload(); absent.sources.characters = [];
    push(absent); push(payload());
    await enterAgain({state: payload()});
    assert.equal(ids['sharing-boss'].value, '', 'a removed character is not silently reselected if it returns');
    chooseBoss(); push(unknown());
    const newMeta = {...input.live.metadata, binding: 'new-binding'};
    push(payload([], {sources: null, metadata: newMeta}));
    push(payload([], {metadata: newMeta}));
    assert.equal(ids['sharing-boss'].value, '', 'a binding change invalidates an unknown-state choice');
    assert.equal(ids['sharing-start'].disabled, true);
    assert.equal(mutationCount(), 0);
  } else if (scenario === 'visibility-ownership') {
    WM.section('previews'); await turn();
    assert.equal(watches().at(-1).args[0], false); watches().at(-1).resolve(null); await turn();
    WM.section('fleet'); await turn();
    assert.equal(watches().at(-1).args[0], true); watches().at(-1).resolve({state: payload()}); await turn();
    document.hidden = true; document.dispatchEvent({type: 'visibilitychange'}); await turn();
    assert.equal(watches().at(-1).args[0], false); watches().at(-1).resolve(null); await turn();
    document.hidden = false; document.dispatchEvent({type: 'visibilitychange'}); await turn();
    assert.equal(watches().at(-1).args[0], true); watches().at(-1).resolve({state: payload()}); await turn();
    assert.equal(mutationCount(), 0);
  } else {
    throw new Error('Unknown history scenario: ' + scenario);
  }
}
async function run() {
  WM.openSettingsSection('fleet'); await turn();
  assert.deepEqual(watches().map(c => c.args[0]), [true]);
  assert.match(ids['sharing-connection'].textContent, /Reading/);
  attemptMutations(); await turn(); assert.equal(mutationCount(), 0);
  const first = watches()[0];
  if (scenario === 'leave' || scenario === 'reenter') {
    WM.route('main');
    if (scenario === 'reenter') WM.openSettingsSection('fleet');
    await turn(); assert.equal(watches().length, 1, 'leave stays serialized');
    first.resolve(input.missing); await turn();
    assert.match(ids['sharing-connection'].textContent, /Reading/);
    assert.deepEqual(watches()[1].args, [false]);
    watches()[1].resolve(null); await turn();
    if (scenario === 'reenter') {
      assert.deepEqual(watches()[2].args, [true]);
      watches()[2].resolve(null); await turn(); unavailable();
      WM.section('uploading'); await turn(); watches()[3].resolve(null); await turn();
    }
  } else if (scenario === 'rejected-admission') {
    first.resolve({queued: true, state: input.live}); await turn();
    const row = ids['sharing-sources'].children.find(row => row.getAttribute('data-source') === input.rejected);
    assert.ok(row, 'the refused original UUID stays visible');
    assert.match(row.textContent, /Start not saved/);
    assert.doesNotMatch(row.textContent, /expired/);
    assert.equal(row.lastChild.disabled, true);
  } else if (scenario === 'failed-refresh-during-on') {
    first.resolve({queued: true, state: input.live}); await turn();
    ids['sharing-refresh'].dispatchEvent({type: 'click'}); await turn();
    ids['sharing-enabled'].checked = true;
    ids['sharing-enabled'].dispatchEvent({type: 'change'}); await turn();
    watches()[1].resolve(null); await turn();
    assert.equal(ids['sharing-enabled'].disabled, false, 'failed Refresh cannot disable Off behind pending On');
    ids['sharing-enabled'].checked = false;
    ids['sharing-enabled'].dispatchEvent({type: 'change'}); await turn();
    assert.deepEqual(calls.filter(c => c.method === 'fleet_sharing_set_enabled').map(c => c.args[0]), [true, false]);
  } else if (scenario === 'newer-push' || scenario === 'stale-state') {
    window.onFleetSharingState(input.live); await turn();
    const before = ids['sharing-connection'].textContent;
    first.resolve(scenario === 'newer-push' ? null : {queued: true, state: input.older}); await turn();
    assert.equal(ids['sharing-connection'].textContent, before);
    assert.equal(ids['sharing-enabled'].disabled, false);
  } else if (['scope-copy', 'verification-scope', 'mixed-history', 'ended-only', 'ended-prerequisites', 'pending-precedence', 'local-results',
    'retained-unknown', 'failed-refresh-history', 'binding-invalidation', 'inflight-stop', 'bridge-source-rejection',
    'inflight-start-leave', 'inflight-binding-reply', 'stable-history-focus', 'visibility-ownership',
    'retained-local-result', 'concurrent-stop-replies', 'inflight-reenter',
    'stale-preference-after-failed-refresh', 'equal-preference-after-failed-refresh', 'boss-selection-across-unknown'].includes(scenario)) {
    await historyScenario(first);
  } else {
    if (scenario === 'reject') first.reject(new Error('controlled bridge failure'));
    else first.resolve(scenario === 'missing-worker' ? input.missing : scenario === 'error-no-state' ? {queued: false, error: 'Fleet sharing is unavailable.'} : null);
    await turn(); unavailable();
    attemptMutations(); await turn(); assert.equal(mutationCount(), 0);
    // Re-entry can hydrate normally; unavailable is not a poisoned watch chain.
    WM.section('uploading'); await turn(); watches()[1].resolve(null); await turn();
    WM.section('fleet'); await turn(); watches()[2].resolve({queued: true, state: input.live}); await turn();
    assert.match(ids['sharing-connection'].textContent, /Paired/);
    assert.equal(ids['sharing-enabled'].disabled, false);
    assert.equal(ids['sharing-confirm-on'].disabled, false, 'recovery rearms every available control');
  }
  assert.equal(errors.length, scenario === 'bridge-source-rejection' ? 2 : scenario === 'reject' ? 1 : 0);
  console.log('PASS ' + scenario);
}
run().catch(error => { console.error(error); process.exitCode = 1; });
