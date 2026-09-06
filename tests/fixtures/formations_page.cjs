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
  querySelector(selector) {
    return descendants(this).find(element => selector.startsWith('.')
      ? element.className.split(' ').includes(selector.slice(1))
      : element.tagName.toLowerCase() === selector) || null;
  }
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
const reads = [], saves = [], confirms = [], exportRequests = [], clipboardWrites = [];
function deferred(args) {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {args, promise, resolve, reject};
}
const navigator = {clipboard: {writeText: text => {
  if (scenario === 'copy-throws') throw new Error('Clipboard unavailable');
  const write = deferred([text]); clipboardWrites.push(write); return write.promise;
}}};
if (scenario === 'copy-missing-clipboard') delete navigator.clipboard;
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
    else if (method === 'eve_settings_export_formations') exportRequests.push(request);
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
  WM, document, window, navigator, console, Date, Math
}, {filename: process.argv[4]});
const A = 'a'.repeat(64), B = 'b'.repeat(64), C = 'c'.repeat(64);
const accounts = [{path: 'choice-A', name: 'Account A'}, {path: 'choice-B', name: 'Account B'}];
function reply(revision = A, name = 'Original', path = 'resolved-A') {
  return {ok: true, path, name: 'Account', content_revision: revision,
    sharing_limits: {max_bytes: 65536, max_formations: 32, max_name_codepoints: 128,
      max_probes: 8, au_meters: 149597870700, min_range_meters: 149597.8707,
      max_range_meters: 9804044142182400, max_coordinate_meters: 10000000000000000},
    formations: [
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
function descendants(element) {
  return element.children.flatMap(child => [child, ...descendants(child)]);
}
function shareBoxes() { return descendants(WM.el('fm-list')).filter(e => e.type === 'checkbox'); }
function rowButtons() { return descendants(WM.el('fm-list')).filter(e => e.className.split(' ').includes('fm-item')); }
function selectShare(index, checked = true) {
  const box = shareBoxes()[index]; assert.ok(box, 'Missing sharing checkbox');
  box.checked = checked; box.dispatchEvent({type: 'change'});
}
function shareStatus() { return WM.el('fm-share-status').textContent; }
function assertShareCount(count) {
  assert.match(WM.el('fm-copy').textContent, new RegExp('Copy selected.*' + count));
}
async function copyScenario() {
  assert.equal(WM.el('fm-copy').disabled, true);
  assert.equal(shareStatus(), '');
  if (scenario === 'copy-empty-limits') {
    WM.openFormations(accounts, 'choice-A');
    const empty = reply(); empty.formations = [];
    empty.sharing_limits.max_formations = 2; empty.sharing_limits.max_bytes = 2048;
    reads.at(-1).resolve(empty); await tick();
    assert.equal(WM.el('fm-copy').disabled, true); assertShareCount(0);
    assert.match(WM.el('fm-share-hint').textContent, /2 formations/);
    assert.match(WM.el('fm-share-hint').textContent, /2 KiB/);
    click('fm-add'); selectShare(0); assert.equal(WM.el('fm-copy').disabled, false);
    assert.equal(saves.length, 0); return;
  }
  if (scenario === 'copy-draft-selection' || scenario === 'copy-selection-identity') {
    const data = reply();
    data.formations.push({id: 8, name: 'Other', probes: [{x: -1000, y: 3000, z: 4000, range: 149597870700}]});
    data.formations.push({id: 9, name: 'Unselected', probes: []});
    WM.openFormations(accounts, 'choice-A'); reads.at(-1).resolve(data); await tick();
    for (const [i, checkbox] of shareBoxes().entries()) {
      assert.equal(checkbox.getAttribute('aria-label'), 'Select ' + data.formations[i].name + ' for sharing');
      const label = checkbox.parentNode;
      assert.equal(label.tagName, 'LABEL'); assert.ok(label.className.split(' ').includes('check'));
      assert.ok(label.children.some(e => e.className === 'box'));
      assert.equal(label.parentNode, rowButtons()[i].parentNode, 'checkbox label must be a sibling of the editor button');
      assert.ok(!descendants(rowButtons()[i]).includes(checkbox), 'never nest interactive controls');
    }
    selectShare(0); selectShare(1); assertShareCount(2);
    rowButtons()[2].click(); assert.equal(WM.el('fm-name').value, 'Unselected');
    assert.equal(WM.el('fm-save').disabled, true, 'unselected invalid formation still prevents Save');
    assert.equal(WM.el('fm-copy').disabled, false, 'unselected invalid formation must not block Copy');
    if (scenario === 'copy-selection-identity') {
      // Remove an unselected row before the selected one: indexes cannot key selection.
      selectShare(0, false); rowButtons()[0].click(); click('fm-delete');
      confirms.at(-1).resolve(true); await tick(); assertShareCount(1);
      assert.equal(shareBoxes()[0].checked, true); assert.equal(shareBoxes()[1].checked, false);
      click('fm-copy'); assert.equal(exportRequests[0].args[0][0].name, 'Other');
      click('fm-delete'); confirms.at(-1).resolve(true); await tick();
      assertShareCount(0); assert.equal(WM.el('fm-copy').disabled, true); return;
    }
    rowButtons()[0].click(); rename('Edited <pair>');
    const x = WM.el('fm-probes').children.find(e => e.getAttribute('aria-label') === 'Probe 1 West km');
    x.value = '12.5'; x.dispatchEvent({type: 'input'}); x.dispatchEvent({type: 'change'});
    const range = WM.el('fm-probes').children.find(e => e.getAttribute('aria-label') === 'Probe 1 range');
    range.value = '0.5'; range.dispatchEvent({type: 'change'});
    assert.equal(shareBoxes()[0].getAttribute('aria-label'), 'Select Edited <pair> for sharing');
    rowButtons()[2].click(); click('fm-copy');
    assert.deepEqual(JSON.parse(JSON.stringify(exportRequests[0].args)), [[
      {id: 7, name: 'Edited <pair>', probes: [{x: 12500, y: 0, z: 0, range: 74798935350}]},
      {id: 8, name: 'Other', probes: [{x: -1000, y: 3000, z: 4000, range: 149597870700}]}
    ]], 'export only selected current drafts, in meters, with no destination path');
    rowButtons()[0].click(); rename('Later edit');
    assert.equal(exportRequests[0].args[0][0].name, 'Edited <pair>', 'Copy must snapshot the invocation');
    const text = '{"prepared":"exact bridge text"}'; exportRequests[0].resolve({ok: true, text}); await tick();
    assert.equal(clipboardWrites[0].args[0], text); assert.doesNotMatch(shareStatus(), /copied/i);
    clipboardWrites[0].resolve(); await tick(); assert.equal(shareStatus(), 'Formations copied.');
    assert.equal(WM.el('fm-dirty').textContent, 'Unselected: needs a probe');
    assert.equal(saves.length, 0); return;
  }
  selectShare(0); assertShareCount(1);
  assert.equal(WM.el('fm-copy').disabled, false);
  assert.equal(WM.el('fm-dirty').textContent, '', 'sharing selection is not an account edit');
  if (scenario === 'copy-busy-recovery') {
    rename('Draft'); click('fm-save'); assert.equal(WM.el('fm-copy').disabled, true);
    const error = "This account's settings changed. Nothing was saved. Your edits are still here.";
    complete(saves[0], {ok: false, error_code: 'stale_file', error});
    assert.equal(WM.el('fm-copy').disabled, false); click('fm-copy');
    exportRequests[0].resolve({ok: true, text: 'recovery'}); await tick();
    clipboardWrites[0].resolve(); await tick(); assert.equal(shareStatus(), 'Formations copied.');
    assert.equal(WM.el('fm-save-status').textContent, error);
    switchTo('choice-B'); confirms.at(-1).resolve(true); await tick();
    assert.equal(WM.el('fm-copy').disabled, true); click('fm-copy'); assert.equal(exportRequests.length, 1);
    return;
  }
  if (scenario === 'copy-rename-retains-controls') {
    // Native Chromium establishes that change runs between pointer-down and
    // click. Pin the control identity here without faking browser event order.
    const checkbox = shareBoxes()[0], label = checkbox.parentNode, button = rowButtons()[0];
    rename('Renamed <pair>');
    assert.ok(shareBoxes()[0] === checkbox, 'rename must not detach the pending sharing click target');
    assert.ok(checkbox.parentNode === label);
    assert.ok(rowButtons()[0] === button, 'rename must not detach an editor navigation target either');
    assert.equal(button.textContent, 'Renamed <pair>');
    assert.equal(checkbox.getAttribute('aria-label'), 'Select Renamed <pair> for sharing');
    assert.equal(checkbox.checked, true); assertShareCount(1);
    selectShare(0, false); assertShareCount(0);
    rename('   ');
    assert.ok(shareBoxes()[0] === checkbox); assert.ok(rowButtons()[0] === button);
    assert.equal(button.textContent, 'Unnamed');
    assert.equal(checkbox.getAttribute('aria-label'), 'Select Unnamed for sharing');
    assert.equal(checkbox.checked, false);
    rename('Final name'); selectShare(0); click('fm-copy');
    assert.equal(exportRequests[0].args[0][0].name, 'Final name');
    assert.equal(WM.el('fm-dirty').textContent, 'Unsaved changes');
    assert.equal(saves.length, 0); return;
  }
  if (scenario === 'copy-typing-keeps-input') {
    const field = WM.el('fm-name'); field.focus(); field.value = 'Unblurred';
    field.dispatchEvent({type: 'input'}); selectShare(0, false); selectShare(0);
    click('fm-copy'); exportRequests[0].resolve({ok: true, text: 'original'}); await tick();
    clipboardWrites[0].resolve(); await tick();
    assert.equal(field.value, 'Unblurred'); assert.equal(document.activeElement, field);
    assert.equal(WM.el('fm-dirty').textContent, 'Unsaved changes'); assert.equal(saves.length, 0); return;
  }
  click('fm-copy'); const first = exportRequests[0];
  if (scenario === 'copy-selection-replacement') {
    // Automatic post-save rereads do not increment loadGeneration.
    rename('Saved'); click('fm-save'); complete(saves[0]);
    reads.at(-1).resolve(reply(B, 'Saved')); await tick();
    assertShareCount(0); assert.equal(WM.el('fm-copy').disabled, true);
    first.resolve({ok: true, text: 'old document'}); await tick();
    assert.equal(clipboardWrites.length, 0); assert.equal(shareStatus(), ''); return;
  }
  if (scenario === 'copy-bridge-error' || scenario === 'copy-bridge-rejection' || scenario === 'copy-bridge-empty') {
    if (scenario === 'copy-bridge-rejection') first.reject(new Error('Disconnected'));
    else first.resolve(scenario === 'copy-bridge-empty' ? null : {ok: false, error: '<bad name>'});
    await tick(); assert.equal(clipboardWrites.length, 0);
    assert.equal(shareStatus(), scenario === 'copy-bridge-error' ? '<bad name>' : 'Could not prepare formations.');
    assert.match(WM.el('fm-share-status').className, /err/);
    assert.equal(WM.el('fm-share-status').children.length, 0, 'error text is not HTML'); return;
  }
  if (scenario === 'copy-repeated-bridge') {
    click('fm-copy'); first.resolve({ok: true, text: 'old'}); await tick();
    assert.equal(clipboardWrites.length, 0);
    exportRequests[1].resolve({ok: true, text: 'latest'}); await tick();
    assert.equal(clipboardWrites[0].args[0], 'latest');
    clipboardWrites[0].resolve(); await tick(); assert.equal(shareStatus(), 'Formations copied.'); return;
  }
  if (['copy-stale-account', 'copy-stale-route', 'copy-stale-bridge-error', 'copy-stale-bridge-rejection'].includes(scenario)) {
    if (scenario === 'copy-stale-account') switchTo('choice-B');
    else { WM.route('evesettings'); WM.openFormations(accounts, 'choice-A'); }
    reads.at(-1).resolve(reply(C, 'New account', 'resolved-B')); await tick();
    if (scenario === 'copy-stale-bridge-rejection') first.reject(new Error('old failure'));
    else first.resolve(scenario === 'copy-stale-bridge-error' ? {ok: false, error: 'old failure'} : {ok: true, text: 'old'});
    await tick(); assert.equal(clipboardWrites.length, 0); assert.equal(shareStatus(), ''); assertShareCount(0); return;
  }
  first.resolve({ok: true, text: 'selected text'}); await tick();
  if (scenario === 'copy-repeated-clipboard') {
    click('fm-copy'); exportRequests[1].resolve({ok: true, text: 'latest'}); await tick();
    clipboardWrites[1].resolve(); await tick(); clipboardWrites[0].reject(new Error('old denial')); await tick();
    assert.equal(shareStatus(), 'Formations copied.'); return;
  }
  if (scenario.startsWith('copy-stale-clipboard-')) {
    WM.route('evesettings'); WM.openFormations(accounts, 'choice-A');
    reads.at(-1).resolve(reply(C, 'Reopened')); await tick();
    if (scenario.endsWith('denied')) clipboardWrites[0].reject(new Error('old denial'));
    else clipboardWrites[0].resolve();
    await tick(); assert.equal(shareStatus(), ''); assert.equal(WM.el('fm-name').value, 'Reopened'); return;
  }
  if (scenario === 'copy-denied') { clipboardWrites[0].reject(new Error('denied')); await tick(); }
  else assert.ok(['copy-throws', 'copy-missing-clipboard'].includes(scenario), 'unknown copy scenario');
  assert.equal(shareStatus(), 'Could not copy formations to the clipboard.');
  assert.match(WM.el('fm-share-status').className, /err/);
  assert.equal(saves.length, 0); assert.equal(WM.el('fm-copy').disabled, false);
}
async function main() {
  await open();
  if (scenario.startsWith('copy-')) await copyScenario();
  else if (scenario === 'commit-keeps-newer-edit' || scenario === 'second-save-retained-draft') {
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
