const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const scenario = process.argv[3];

// Only DOM/SVG mechanics and bridge delivery are simulated. No editor state,
// conversions, load/save logic, or production source rewriting lives here.
class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase();
    this.attrs = {...attrs};
    this.children = [];
    this.listeners = {};
    this.id = attrs.id || '';
    this.className = attrs.class || '';
    this.disabled = 'disabled' in attrs;
    this.hidden = 'hidden' in attrs;
    this.value = attrs.value || '';
    this.style = {};
  }
  appendChild(node) { this.children.push(node); node.parentNode = this; return node; }
  set textContent(text) { this.children = []; this.text = String(text); }
  get textContent() { return (this.text || '') + this.children.map(x => x.textContent).join(''); }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  getAttribute(key) { return this.attrs[key] ?? null; }
  getBoundingClientRect() { return {width: 300, height: 200}; }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  dispatchEvent(event) {
    event.target ||= this;
    event.preventDefault ||= () => {};
    (this.listeners[event.type] || []).forEach(callback => callback(event));
  }
  click() { if (!this.disabled) this.dispatchEvent({type: 'click'}); }
  focus() { document.activeElement = this; }
}
const ids = {};
function build(node) {
  const element = new Element(node.tag, node.attrs);
  if (element.id) ids[element.id] = element;
  node.children.forEach(child => element.appendChild(build(child)));
  return element;
}
const document = build(page);
document.readyState = 'complete';
document.createElement = tag => new Element(tag);
document.createElementNS = (ns, tag) => new Element(tag);
const window = new Element('window');
const reads = [], saves = [], confirms = [];
function deferred(args) {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return {args, promise, resolve};
}
const WM = {
  current_route: 'evesettings',
  el: id => { assert.ok(ids[id], 'Missing production markup: ' + id); return ids[id]; },
  make: (tag, cls, text) => {
    const element = new Element(tag, {class: cls});
    if (text !== undefined) element.textContent = text;
    return element;
  },
  setEnabled: (id, enabled) => { WM.el(id).disabled = !enabled; },
  route: route => {
    WM.current_route = route;
    document.dispatchEvent({type: 'wm:route', detail: route});
  },
  send: (method, ...args) => {
    const request = deferred(args);
    if (method === 'eve_settings_formations') reads.push(request);
    else if (method === 'eve_settings_save_formations') saves.push(request);
    else assert.fail('Unexpected bridge call: ' + method);
    return request.promise;
  },
  confirm: (...args) => {
    const request = deferred(args);
    confirms.push(request);
    return request.promise;
  }
};
vm.runInNewContext(fs.readFileSync(process.argv[4], 'utf8'), {
  WM, document, window, console, Date, Math
}, {filename: process.argv[4]});
const A = 'a'.repeat(64), B = 'b'.repeat(64), C = 'c'.repeat(64);
const accounts = [{path: 'choice-A', name: 'Account A'}, {path: 'choice-B', name: 'Account B'}];
function reply(revision = A, name = 'Original', path = 'resolved-A') {
  return {ok: true, path, name: 'Account', content_revision: revision, formations: [
    {id: 7, name, probes: [{x: 2000, y: 0, z: 0, range: 598391482800}]}
  ]};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const click = id => WM.el(id).click();
function rename(name) { WM.el('fm-name').value = name; WM.el('fm-name').dispatchEvent({type: 'change'}); }
function switchTo(path) { WM.el('fm-account').value = path; WM.el('fm-account').dispatchEvent({type: 'change'}); }
function complete(request, overrides = {}) {
  WM.formationsDone({ok: true, operation: 'formations_save', path: request.args[0],
    request_id: request.args[3], content_revision: B, error_code: '', error: '', warning: '', ...overrides});
}
function assertSave(request, revision, name) {
  assert.equal(request.args[0], 'resolved-A', 'save must use resolved identity, not choice');
  assert.equal(request.args[2], revision, 'save baseline must match the retained document/commit');
  assert.equal(request.args[1][0].name, name);
  assert.equal(request.args[1][0].id, 7);
  assert.deepEqual(JSON.parse(JSON.stringify(request.args[1][0].probes)),
    [{x: 2000, y: 0, z: 0, range: 598391482800}]);
}
function assertBusy() { assert.equal(WM.el('fm-save').disabled, true); assert.equal(WM.el('fm-account').disabled, true); }
function assertEditable(name) {
  assert.equal(WM.el('fm-name').disabled, false);
  assert.equal(WM.el('fm-name').value, name);
  assert.equal(WM.el('fm-save').disabled, false);
}
async function open() {
  WM.openFormations(accounts, 'choice-A');
  reads.at(-1).resolve(reply());
  await tick();
}
async function main() {
  await open();
  if (scenario === 'commit-keeps-newer-edit' || scenario === 'second-save-retained-draft') {
    rename('Submitted'); click('fm-save'); const first = saves[0];
    rename('Newer'); complete(first, {warning: 'Saved, but retention failed.'});
    assertEditable('Newer'); assert.equal(reads.length, 1);
    assert.match(WM.el('fm-save-status').textContent, /retention failed/);
    click('fm-save'); assertSave(saves[1], B, 'Newer');
    if (scenario === 'second-save-retained-draft') {
      complete(first); assertBusy();
      complete(saves[1], {content_revision: C});
      reads.at(-1).resolve(reply(C, 'Newer'));
      await tick();
      assert.equal(WM.el('fm-save').disabled, true);
      assert.equal(WM.el('fm-dirty').textContent, '');
    }
  } else if (scenario === 'ignored-read-keeps-baseline') {
    rename('Submitted'); click('fm-save'); complete(saves[0]);
    assert.equal(reads.length, 2);
    rename('During read'); reads[1].resolve(reply(C, 'External'));
    await tick(); assertEditable('During read');
    click('fm-save'); assertSave(saves[1], B, 'During read');
  } else if (scenario === 'old-completion-ignored') {
    rename('Submitted'); click('fm-save'); const old = saves[0];
    for (const mismatch of [{operation: 'profile_copy'}, {request_id: 'other'}, {path: 'resolved-B'}]) {
      complete(old, mismatch); assertBusy(); assert.equal(reads.length, 1);
    }
    WM.route('evesettings'); WM.openFormations([accounts[1]], 'choice-B');
    complete(old); assertBusy();
    reads.at(-1).resolve(reply(C, 'Other', 'resolved-B')); await tick();
    rename('Other edit'); click('fm-save');
    complete(old); assertBusy();
    assert.equal(WM.el('fm-name').value, 'Other edit');
    complete(saves.at(-1)); assert.equal(reads.at(-1).args[0], 'choice-B');
  } else if (scenario === 'start-reply-after-completion') {
    rename('Submitted'); click('fm-save'); const first = saves[0];
    complete(first); first.resolve(false); await tick(); assertBusy();
    rename('Newer'); reads.at(-1).resolve(reply(B)); await tick();
    click('fm-save'); assertSave(saves[1], B, 'Newer');
    complete(first); assertBusy();
  } else if (scenario === 'failed-switch' || scenario === 'switch-edit') {
    rename('Draft'); switchTo('choice-B'); confirms.at(-1).resolve(true); await tick();
    if (scenario === 'switch-edit') rename('During switch');
    reads.at(-1).resolve(scenario === 'failed-switch' ? {ok: false, error: 'unreadable'} : reply(C, 'Other', 'resolved-B'));
    await tick();
    const expected = scenario === 'failed-switch' ? 'Draft' : 'During switch';
    assertEditable(expected); assert.equal(WM.current_route, 'formations');
    assert.equal(WM.el('fm-account').value, 'choice-A');
    click('fm-save'); assertSave(saves[0], A, expected);
  } else if (scenario.startsWith('stale-read-')) {
    WM.openFormations(accounts, 'choice-A'); const old = reads.at(-1);
    if (scenario === 'stale-read-route') WM.route('evesettings');
    WM.openFormations(accounts, 'choice-A'); const latest = reads.at(-1);
    old.resolve(scenario === 'stale-read-error' ? {ok: false, error: 'old error'} : reply(C, 'Old'));
    await tick(); assertBusy(); assert.equal(confirms.length, 0);
    latest.resolve(reply(B, 'Latest')); await tick();
    rename('Current'); click('fm-save'); assertSave(saves[0], B, 'Current');
  } else if (scenario === 'reload-cancel-fail-success' || scenario === 'reload-edit') {
    rename('Draft'); click('fm-reload');
    assert.equal(reads.length, 1); assert.equal(confirms.length, 1);
    if (scenario === 'reload-cancel-fail-success') {
      confirms.at(-1).resolve(false); await tick(); assertEditable('Draft');
      click('fm-reload'); confirms.at(-1).resolve(true); await tick();
      reads.at(-1).resolve({ok: false, error: 'Cannot reload'}); await tick();
      assertEditable('Draft'); click('fm-save'); assertSave(saves[0], A, 'Draft');
      complete(saves[0], {ok: false, content_revision: '', error_code: 'save_failed', error: 'not saved'});
      click('fm-reload'); confirms.at(-1).resolve(true); await tick();
      reads.at(-1).resolve(reply(C, 'Reloaded')); await tick();
      assert.equal(WM.el('fm-name').value, 'Reloaded');
      assert.equal(WM.el('fm-save').disabled, true);
      rename('Next'); click('fm-save'); assertSave(saves[1], C, 'Next');
    } else {
      confirms.at(-1).resolve(true); await tick(); rename('During reload');
      reads.at(-1).resolve(reply(C, 'External')); await tick();
      assertEditable('During reload'); click('fm-save'); assertSave(saves[0], A, 'During reload');
    }
  } else if (scenario === 'stale-save-editable') {
    rename('Draft'); click('fm-save');
    const error = "This account's settings changed. Nothing was saved. Your edits are still here.";
    complete(saves[0], {ok: false, content_revision: '', error_code: 'stale_file', error});
    assertEditable('Draft'); assert.equal(reads.length, 1);
    assert.equal(WM.el('fm-save-status').textContent, error);
    rename('Recovery edit'); assert.equal(WM.el('fm-save-status').textContent, error);
    click('fm-save'); assertSave(saves[1], A, 'Recovery edit');
  } else if (scenario === 'start-refusal') {
    rename('Draft'); click('fm-save'); saves[0].resolve(false); await tick();
    assertEditable('Draft'); click('fm-save'); assertSave(saves[1], A, 'Draft');
  } else if (scenario === 'request-identity') {
    rename('Draft'); click('fm-save'); assertSave(saves[0], A, 'Draft');
    assert.match(saves[0].args[3], /^\d+-[a-z0-9]+[:-]\d+[:-]\d+$/);
    assert.ok(saves[0].args[3].length <= 128);
    saves[0].resolve(false); await tick(); click('fm-save');
    assert.notEqual(saves[0].args[3], saves[1].args[3]);
  } else if (scenario.startsWith('stale-confirm-')) {
    rename('Old draft');
    if (scenario === 'stale-confirm-switch') switchTo('choice-B');
    else click(scenario === 'stale-confirm-back' ? 'fm-back' : 'fm-reload');
    const old = confirms.at(-1);
    WM.route('evesettings'); WM.openFormations(accounts, 'choice-A');
    reads.at(-1).resolve(reply(B, 'Reopened')); await tick(); rename('New draft');
    const readCount = reads.length;
    old.resolve(true); await tick();
    assert.equal(WM.current_route, 'formations'); assert.equal(reads.length, readCount);
    assertEditable('New draft'); click('fm-save'); assertSave(saves[0], B, 'New draft');
  } else if (scenario.startsWith('typing-')) {
    const [, field, ...timing] = scenario.split('-');
    const duringRead = timing.join('-') === 'during-reread';
    const labels = {x: 'West', y: 'Up', z: 'North'};
    // Find the live control each time: asserting on a detached old input would
    // miss exactly the renderPane/renderProbes replacement this test guards.
    const control = () => field === 'name' ? WM.el('fm-name')
      : WM.el('fm-probes').children.find(element =>
        element.getAttribute('aria-label') === 'Probe 1 ' + labels[field] + ' km');
    function type(value) {
      control().focus();
      control().value = value;
      control().dispatchEvent({type: 'input'});
    }
    // Number inputs expose '' while a partial exponent/sign is being entered.
    // It is activity to protect, not a zero to put into the document.
    const raw = field === 'name' ? 'Still typing' : '';
    rename('Submitted'); click('fm-save');
    if (duringRead) complete(saves[0]);
    type(raw);
    assert.equal(saves.length, 1, 'input must never start a save');
    if (!duringRead) complete(saves[0]);
    if (reads.length > 1) { reads.at(-1).resolve(reply(C, 'Submitted')); await tick(); }
    assert.equal(control().value, raw, 'an async response discarded unblurred input');
    assert.equal(document.activeElement, control());
    assert.equal(WM.el('fm-dirty').textContent, 'Unsaved changes');
    assert.equal(WM.el('fm-save').disabled, false);
    assert.equal(reads.length, duringRead ? 2 : 1);

    if (field !== 'name') {
      // A direct Save before change may only serialize the last valid model,
      // never coerce the partial numeric text to 0 or NaN.
      click('fm-save'); assertSave(saves.at(-1), B, 'Submitted');
      complete(saves.at(-1), {ok: false, content_revision: '', error_code: 'save_failed', error: 'Retry later'});
      assert.equal(control().value, raw);
    }
    const beforeSave = saves.length;
    type(field === 'name' ? 'Finished name' : '12.5');
    control().dispatchEvent({type: 'change'});
    assert.equal(saves.length, beforeSave, 'change updates the draft, not the account file');
    click('fm-save');
    const saved = saves.at(-1);
    assert.equal(saved.args[2], B, 'ignored reread must not replace the committed baseline');
    const expectedName = field === 'name' ? 'Finished name' : 'Submitted';
    assert.equal(saved.args[1][0].name, expectedName);
    if (field !== 'name') assert.equal(saved.args[1][0].probes[0][field], 12500);
    complete(saved, {content_revision: C});
    const committed = reply(C, expectedName);
    if (field !== 'name') committed.formations[0].probes[0][field] = 12500;
    reads.at(-1).resolve(committed); await tick();
    assert.equal(WM.el('fm-dirty').textContent, '');

    // Explicit Reload is the intentional replacement route for a raw draft.
    type(raw); click('fm-reload'); const readCount = reads.length;
    confirms.at(-1).resolve(false); await tick();
    assert.equal(control().value, raw);
    assert.equal(reads.length, readCount);
    assert.equal(WM.el('fm-dirty').textContent, 'Unsaved changes');
    click('fm-reload'); confirms.at(-1).resolve(true); await tick();
    reads.at(-1).resolve(reply(C, 'Reloaded')); await tick();
    assert.equal(control().value, field === 'name' ? 'Reloaded' : (field === 'x' ? '2' : '0'));
    assert.equal(WM.el('fm-dirty').textContent, '');
    assert.equal(saves.length, beforeSave + 1, 'Reload must not write');
  } else if (scenario === 'back-dirty') {
    rename('Draft'); click('fm-back'); assert.equal(confirms.length, 1);
    confirms[0].resolve(false); await tick(); assertEditable('Draft');
    click('fm-back'); confirms[1].resolve(true); await tick();
    assert.equal(WM.current_route, 'evesettings');
  } else assert.fail('Unknown scenario: ' + scenario);
  console.log('PASS ' + scenario);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
