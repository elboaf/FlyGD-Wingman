// Real app.js route/bridge and fleetsharing.js, with DOM and delivery seams only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const scenario = process.argv[3];
const web = process.argv[4];
class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase(); this.attrs = {...attrs};
    this.id = attrs.id || ''; this.className = attrs.class || '';
    this.children = []; this.listeners = {}; this.value = attrs.value || '';
    this.disabled = 'disabled' in attrs; this.hidden = 'hidden' in attrs;
    this.checked = 'checked' in attrs;
    this.dataset = Object.fromEntries(Object.entries(attrs).filter(([k]) => k.startsWith('data-')).map(([k, v]) => [k.slice(5), v]));
  }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
  set disabled(value) { this._disabled = Boolean(value); }
  get disabled() { return this._disabled; }
  get options() { return this.children; }
  get firstChild() { return this.children[0]; }
  get lastChild() { return this.children[this.children.length - 1]; }
  remove() { this.parentNode.children = this.parentNode.children.filter(c => c !== this); }
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
async function run() {
  WM.openSettingsSection('previews'); await turn();
  assert.deepEqual(watches().map(c => c.args[0]), [true]);
  assert.match(ids['sharing-connection'].textContent, /Reading/);
  attemptMutations(); await turn(); assert.equal(mutationCount(), 0);
  const first = watches()[0];
  if (scenario === 'leave' || scenario === 'reenter') {
    WM.route('main');
    if (scenario === 'reenter') WM.openSettingsSection('previews');
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
  } else {
    if (scenario === 'reject') first.reject(new Error('controlled bridge failure'));
    else first.resolve(scenario === 'missing-worker' ? input.missing : scenario === 'error-no-state' ? {queued: false, error: 'Fleet sharing is unavailable.'} : null);
    await turn(); unavailable();
    attemptMutations(); await turn(); assert.equal(mutationCount(), 0);
    // Re-entry can hydrate normally; unavailable is not a poisoned watch chain.
    WM.section('uploading'); await turn(); watches()[1].resolve(null); await turn();
    WM.section('previews'); await turn(); watches()[2].resolve({queued: true, state: input.live}); await turn();
    assert.match(ids['sharing-connection'].textContent, /Paired/);
    assert.equal(ids['sharing-enabled'].disabled, false);
    assert.equal(ids['sharing-confirm-on'].disabled, false, 'recovery rearms every available control');
  }
  assert.equal(errors.length, scenario === 'reject' ? 1 : 0);
  console.log('PASS ' + scenario);
}
run().catch(error => { console.error(error); process.exitCode = 1; });
