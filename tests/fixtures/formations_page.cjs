const assert = require('node:assert/strict');
const fs = require('node:fs');
const readline = require('node:readline');
const vm = require('node:vm');
const {isNativeError} = require('node:util').types;
const {spawnSync} = require('node:child_process');
const {performance} = require('node:perf_hooks');

const page = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const productionModule = process.argv[3];
const pythonExe = process.argv[4];

async function runScenario(request) {
const scenario = request.scenario;
const started = performance.now();
const unhandledRejections = [];
const onUnhandledRejection = error => unhandledRejections.push(error);
const encodingBoundaries = [];
process.on('unhandledRejection', onUnhandledRejection);

try {
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
  appendChild(node) {
    if (node.parentNode) node.parentNode.children.splice(node.parentNode.children.indexOf(node), 1);
    this.children.push(node); node.parentNode = this; return node;
  }
  insertBefore(node, reference) {
    this.children.splice(this.children.indexOf(reference), 0, node); node.parentNode = this; return node;
  }
  set textContent(text) { this.children = []; this.text = String(text); }
  get textContent() { return (this.text || '') + this.children.map(x => x.textContent).join(''); }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  getAttribute(key) { return this.attrs[key] ?? null; }
  querySelector(selector) {
    return descendants(this).find(element => selector.startsWith('.')
      ? element.className.split(' ').includes(selector.slice(1))
      : element.tagName.toLowerCase() === selector) || null;
  }
  getBoundingClientRect() { return this.rect || {width: 300, height: 200}; }
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
const parses = [], validations = [];
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
    else if (method === 'eve_settings_parse_formations') parses.push(request);
    else if (method === 'eve_settings_validate_formation_import') validations.push(request);
    else assert.fail('Unexpected bridge call: ' + method);
    return request.promise;
  },
  confirm: (...args) => {
    const request = deferred(args);
    confirms.push(request);
    return request.promise;
  }
};
vm.runInNewContext(fs.readFileSync(productionModule, 'utf8'), {
  WM, document, window, navigator, console, Date, Math, TextEncoder
}, {filename: productionModule});
const A = 'a'.repeat(64), B = 'b'.repeat(64), C = 'c'.repeat(64);
const accounts = [{path: 'choice-A', name: 'Account A'}, {path: 'choice-B', name: 'Account B'}];
function reply(revision = A, name = 'Original', path = 'resolved-A') {
  return {ok: true, path, name: 'Account', content_revision: revision,
    sharing_limits: {max_bytes: 65536, max_formations: 32, max_name_codepoints: 128,
      max_probes: 8, au_meters: 149597870700, min_range_meters: 149597.8707,
      max_range_meters: 9804046054195200, max_coordinate_meters: 10000000000000000},
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
// Python, not a JS approximation, answers actual production requests. Compose
// the real facade/controller without account/session state for these pure endpoints.
function pythonReply(method, args) {
  const env = {...process.env, ...((request.payload && request.payload.env) || {})};
  const result = spawnSync(pythonExe, ['-c', [
    'import json,os,sys',
    'from wingman.ui.api import Api',
    'from wingman.evesettings.controller import ProfilesController',
    'api=Api.__new__(Api)',
    'api._profiles=ProfilesController.__new__(ProfilesController)',
    'method,args=json.loads(sys.stdin.buffer.read().decode("utf-8"))',
    'reply={"result":getattr(api,method)(*args),"encoding":os.environ.get("PYTHONIOENCODING","")}',
    'sys.stdout.buffer.write(json.dumps(reply,ensure_ascii=False).encode("utf-8"))'
  ].join('\n')], {input: JSON.stringify([method, args]), encoding: 'utf8', env});
  assert.equal(result.status, 0, result.stderr);
  const reply = JSON.parse(result.stdout);
  encodingBoundaries.push(reply.encoding);
  return reply.result;
}
function deliverParse(request = parses.at(-1)) {
  request.resolve(pythonReply('eve_settings_parse_formations', request.args));
}
function deliverAdd(request = validations.at(-1)) {
  request.resolve(pythonReply('eve_settings_validate_formation_import', request.args));
}
const plain = value => JSON.parse(JSON.stringify(value));
function shared(name = 'Incoming', range = 149597870700) {
  return {name, probes: [{x: -1250.5, y: 3000, z: 2500.25, range}]};
}
function artifact(items = [shared()]) {
  return JSON.stringify({format: 'wingman-preset', version: 1, type: 'probe-formations', formations: items});
}
function inputText(text) {
  WM.el('fm-import-text').value = text;
  WM.el('fm-import-text').dispatchEvent({type: 'input'});
}
function importNames() { return descendants(WM.el('fm-import-list')).filter(e => e.tagName === 'INPUT'); }
function importButtons() { return descendants(WM.el('fm-import-list')).filter(e => e.tagName === 'BUTTON'); }
function importRename(index, name) {
  importNames()[index].value = name;
  importNames()[index].dispatchEvent({type: 'input'});
}
function importStatus() { return WM.el('fm-import-status').textContent; }
function assertReview(opened) {
  assert.equal(WM.el('fm-import-work').parentNode, WM.el('fm-import-commit').parentNode,
    'pinned actions must be siblings of the scroller, not its children');
  assert.equal(WM.el('fm-import-work').parentNode, WM.el('fm-editor-work').parentNode);
  assert.equal(WM.el('fm-import-work').hidden, !opened);
  assert.equal(WM.el('fm-import-commit').hidden, !opened);
  assert.equal(WM.el('fm-editor-work').hidden, opened);
  assert.equal(WM.el('fm-commit').hidden, opened);
  assert.equal(WM.el('fm-import-cancel').disabled, false);
  assert.equal(WM.el('fm-back').disabled, false);
}
async function review(items = [shared()]) {
  click('fm-paste'); inputText(artifact(items)); click('fm-import-review');
  deliverParse(); await tick();
}
async function pasteScenario() {
  if (scenario === 'paste-empty' || scenario === 'paste-invalid-destination') {
    WM.openFormations(accounts, 'choice-A'); const data = reply();
    if (scenario === 'paste-empty') data.formations = [];
    else data.formations[0].probes = [];
    reads.at(-1).resolve(data); await tick();
  }
  if (scenario === 'paste-cancel-draft') {
    rename('Unsaved <draft>'); selectShare(0);
    const row = rowButtons()[0];
    click('fm-paste'); assertReview(true);
    assert.equal(document.activeElement, WM.el('fm-import-text'));
    assert.equal(WM.el('fm-add').disabled, true); assert.equal(WM.el('fm-save').disabled, true);
    assert.equal(WM.el('fm-import-text').disabled, false);
    click('fm-add'); click('fm-save'); assert.equal(rowButtons().length, 1);
    inputText(artifact()); assert.equal(parses.length, 0, 'typing never crosses the bridge');
    click('fm-import-review'); deliverParse(); await tick();
    click('fm-import-cancel'); assertReview(false);
    assert.equal(document.activeElement, WM.el('fm-paste'));
    assert.equal(WM.el('fm-name').value, 'Unsaved <draft>'); assert.equal(rowButtons()[0], row);
    assertShareCount(1); assertEditable('Unsaved <draft>');
    assert.equal(saves.length, 0); assert.equal(reads.length, 1); return;
  }
  if (scenario === 'paste-invalid-text' || scenario === 'paste-byte-limit') {
    click('fm-paste');
    const texts = scenario === 'paste-byte-limit' ? ['é'.repeat(32769), '𐐀'.repeat(16385)]
      : ['{', '['.repeat(2000) + ']'.repeat(2000), artifact().replace('"version":1', '"version":1,"version":1'), artifact().replace('"x":-1250.5', '"x":true'),
        artifact([shared('Too small', 149597.87069999997)]), artifact([shared('Too big', 9804046054195202)]),
        artifact().replace('"x":-1250.5', '"x":10000000000000001')];
    for (const text of texts) {
      inputText(text);
      if (scenario === 'paste-byte-limit') {
        assert.match(importStatus(), /65536.*UTF-8|UTF-8.*65536/);
        assert.equal(WM.el('fm-import-text').value, text, 'oversize paste must not be clipped');
        click('fm-import-review'); assert.equal(parses.length, 0);
      } else {
        click('fm-import-review'); deliverParse(); await tick(); assert.ok(importStatus());
      }
      assert.equal(WM.el('fm-import-add').disabled, true); assertReview(true);
      assert.equal(importNames().length, 0); assert.equal(rowButtons().length, 1);
    }
    inputText(artifact()); click('fm-import-review'); deliverParse(); await tick();
    assert.equal(WM.el('fm-import-add').disabled, false);
    assert.equal(saves.length, 0); return;
  }
  if (scenario.includes('during-parse') || scenario === 'paste-rejected-parse') {
    click('fm-paste'); inputText(artifact()); click('fm-import-review'); const old = parses.at(-1);
    if (scenario === 'paste-text-during-parse') inputText(artifact([shared('Edited')]));
    else if (scenario === 'paste-account-during-parse') switchTo('choice-B');
    else if (scenario === 'paste-route-during-parse') WM.route('evesettings');
    if (scenario === 'paste-rejected-parse') old.reject(new Error('offline')); else deliverParse(old);
    await tick(); assert.equal(importNames().length, 0); assert.equal(saves.length, 0);
    if (scenario === 'paste-rejected-parse') { assert.ok(importStatus()); assertReview(true); }
    else if (scenario === 'paste-text-during-parse') {
      assert.equal(WM.el('fm-import-text').value, artifact([shared('Edited')]));
      click('fm-import-review'); deliverParse(); await tick(); assert.equal(importNames()[0].value, 'Edited');
    } else assertReview(false);
    return;
  }
  if (scenario === 'paste-range-cycles') {
    const ranges = [149597.8707, 149597.87070000003, 9804046054195200,
      9804046054195198, 187.25000012345 * 149597870700, 18469.135803 * 149597870700];
    for (let cycle = 0; cycle < 2; cycle++) {
      const coordinates = [-1e16, -9999999999999998, 1e16, 9999999999999998, 0, -1250.5];
      const items = ranges.map((range, i) => {
        const f = shared('Cycle ' + cycle + ' / ' + i, range);
        f.probes[0].x = coordinates[i]; return f;
      });
      const prior = rowButtons().length;
      await review(items); click('fm-import-add'); deliverAdd(); await tick();
      assert.equal(saves.length, cycle * 2, 'Add never invokes Save');
      click('fm-save'); const request = saves.at(-1);
      assert.equal(request.args[1][0].id, 7);
      const batch = request.args[1].slice(prior);
      assert.equal(batch.length, ranges.length);
      batch.forEach((f, i) => {
        assert.equal(f.id, null); assert.ok(Math.abs(f.probes[0].range - ranges[i]) <= Math.abs(ranges[i]) * Number.EPSILON);
        assert.ok(Math.abs(f.probes[0].x - coordinates[i]) <= Math.abs(coordinates[i]) * Number.EPSILON);
        assert.equal(f.probes[0].y, 3000); assert.equal(f.probes[0].z, 2500.25);
      });
      // Emulate only file reply/ID allocation, not ordinary fromMeters: the
      // real page rereads these meter values and normalizes them itself.
      complete(request); const saved = reply(B);
      saved.formations = plain(request.args[1]).map((f, i) => ({...f, id: f.id === null ? 100 + i : f.id}));
      reads.at(-1).resolve(saved); await tick();
      assert.equal(WM.el('fm-name').value, items[0].name, 'post-save selection stays on first addition');
      selectShare(prior); click('fm-copy'); const copied = exportRequests.at(-1);
      assert.equal(copied.args[0][0].id, 100 + prior);
      assert.equal(copied.args[0][0].probes[0].range, 149597.8707);
      // A second Save after ordinary reload retains minted IDs and normalized
      // ranges, including both near-boundary neighbors and fractional values.
      rename(items[0].name + ' saved'); click('fm-save'); const second = saves.at(-1);
      const normalized = [149597.8707, 149597.8707, 9804046054195200,
        9804046054195200, 28012201288575, 18469.135803 * 149597870700];
      second.args[1].slice(prior).forEach((f, i) => {
        assert.equal(f.id, 100 + prior + i); assert.equal(f.probes[0].range, normalized[i]);
        assert.ok(Math.abs(f.probes[0].x - coordinates[i]) <= Math.abs(coordinates[i]) * Number.EPSILON);
      });
      complete(second); saved.formations = plain(second.args[1]); reads.at(-1).resolve(saved); await tick();
      // Count completed saves independently below, two per full cycle.
      assert.equal(saves.length, (cycle + 1) * 2);
    }
    return;
  }
  const names = scenario === 'paste-conflict' ? ['Straße', 'Fresh']
    : scenario === 'paste-unicode-name' ? ['𐐀'.repeat(128), '<img src=x onerror=alert(1)>'] : ['Incoming', 'Second'];
  if (scenario === 'paste-conflict') rename('STRASSE');
  const items = names.map(name => shared(name));
  items[1].probes.push({x: 25000000, y: 0, z: 0, range: 149597870700});
  await review(items);
  assertReview(true); assert.equal(importNames().length, 2);
  for (const field of importNames()) {
    const label = field.parentNode.querySelector('label');
    assert.equal(label.getAttribute('for'), field.id);
    assert.ok(field.parentNode.children.some(e => e.id === field.getAttribute('aria-describedby')));
    assert.equal(field.getAttribute('maxlength'), null);
  }
  assert.equal(descendants(WM.el('fm-import-list')).some(e => e.tagName === 'IMG'), false);
  assert.deepEqual(plain(parses.at(-1).args[1]), scenario === 'paste-empty' ? [] : [scenario === 'paste-conflict' ? 'STRASSE' : 'Original']);
  if (scenario === 'paste-conflict') {
    assert.match(WM.el('fm-import-list').textContent, /already|conflict|used/i);
    assert.equal(importNames()[0].value, 'Straße', 'no automatic rename');
    importRename(0, ' Resolved ');
    assert.equal(validations.length, 0, 'name typing must stay local');
  }
  if (scenario === 'paste-invalid-renames') {
    for (const name of ['Second', '𐐀'.repeat(129), 'bad\u0000name', '']) {
      importRename(0, name); click('fm-import-add'); deliverAdd(); await tick();
      assertReview(true); assert.equal(rowButtons().length, 1); assert.ok(importStatus());
      assert.equal(saves.length, 0);
    }
    importRename(0, 'Corrected');
  }
  if (scenario === 'paste-batch') {
    const labels = importNames().map(field => field.parentNode.querySelector('label'));
    assert.match(labels[0].textContent, /\b1 probe\b/, 'the first incoming row must expose its one-probe count');
    assert.match(labels[1].textContent, /\b2 probes\b/, 'the second incoming row must expose its two-probe count');
    labels.forEach((label, i) => {
      assert.equal(label.getAttribute('for'), importNames()[i].id, 'visible count belongs to the accessible name');
      assert.equal(label.hidden, false); assert.notEqual(label.getAttribute('aria-hidden'), 'true');
    });
    selectShare(0); rowButtons()[0].click();
    assert.equal(WM.el('fm-name').value, 'Original', 'import rendering cannot replace current draft');
    importButtons()[1].click();
    const probes = descendants(WM.el('fm-import-preview')).filter(e => e.getAttribute('class') === 'fm-probe');
    assert.equal(probes.length, 2, 'review must draw selected incoming geometry');
    assert.equal(WM.el('fm-name').value, 'Original');
    assert.ok(descendants(WM.el('fm-import-preview')).some(e => e.className === 'fm-probe' || e.getAttribute('class') === 'fm-probe'));
  }
  if (scenario === 'paste-new-target-conflict') rename('INCOMING');
  if (scenario === 'paste-route-during-add') importRename(0, 'Renamed before Add');
  click('fm-import-add'); const pending = validations.at(-1);
  assert.ok(pending, 'explicit Add must revalidate');
  assert.equal(pending.args.length, 2); assert.equal(saves.length, 0);
  const outstandingCount = validations.length;
  if (scenario === 'paste-double-add') { click('fm-import-add'); assert.equal(validations.length, outstandingCount); }
  if (scenario === 'paste-name-during-add') {
    importRename(0, 'Later name');
    assert.equal(pending.args[0][0].name, 'Incoming', 'request names must be a snapshot');
  }
  if (scenario === 'paste-text-during-add') inputText(artifact([shared('New text')]));
  if (scenario === 'paste-draft-during-add') rename('Changed draft');
  if (scenario === 'paste-route-during-add') {
    assert.equal(pending.args[0][0].name, 'Renamed before Add'); WM.route('evesettings');
  }
  if (scenario === 'paste-account-during-add') switchTo('choice-B');
  if (scenario === 'paste-reopen-during-add') WM.openFormations(accounts, 'choice-A');
  if (scenario === 'paste-cancel-during-add') click('fm-import-cancel');
  if (scenario === 'paste-rejected-add') pending.reject(new Error('offline')); else deliverAdd(pending);
  await tick();
  if (scenario === 'paste-new-target-conflict') {
    assertReview(true); assert.equal(rowButtons().length, 1); assert.equal(saves.length, 0);
    assert.deepEqual(plain(pending.args[1]), ['INCOMING']);
    assert.equal(importNames()[0].getAttribute('aria-invalid'), 'true');
    assert.equal(WM.el('fm-import-add').disabled, true); return;
  }
  if (scenario.includes('during-add') || scenario === 'paste-rejected-add') {
    assert.equal(rowButtons().length, 1, 'a stale/refused result must not insert any part of a batch');
    assert.equal(saves.length, 0);
    if (['paste-name-during-add', 'paste-draft-during-add', 'paste-rejected-add'].includes(scenario)) {
      assertReview(true); click('fm-import-add'); deliverAdd(); await tick();
      assert.equal(rowButtons().length, 3, 'retry is usable after staleness/failure');
    } else if (scenario === 'paste-text-during-add') {
      assertReview(true); assert.equal(importNames().length, 0);
      assert.equal(WM.el('fm-import-add').disabled, true);
      assert.equal(WM.el('fm-import-text').value, artifact([shared('New text')]));
    } else assertReview(false);
    return;
  }
  assertReview(false);
  const first = scenario === 'paste-empty' ? 0 : 1;
  assert.equal(rowButtons().length, first + 2); assert.equal(document.activeElement, rowButtons()[first]);
  assert.equal(saves.length, 0); assert.equal(reads.length, scenario === 'paste-empty' || scenario === 'paste-invalid-destination' ? 2 : 1);
  if (scenario === 'paste-double-add') { deliverAdd(pending); await tick(); click('fm-import-add'); assert.equal(rowButtons().length, 3); }
  if (scenario === 'paste-invalid-destination') { assert.equal(WM.el('fm-save').disabled, true); return; }
  click('fm-save'); const added = saves[0].args[1].slice(first);
  assert.deepEqual(added.map(f => f.id), [null, null]);
  assert.equal(added[0].name, scenario === 'paste-conflict' ? 'Resolved' : scenario === 'paste-invalid-renames' ? 'Corrected' : names[0]);
  assert.deepEqual(plain(added[0].probes), shared().probes);
  if (first) assert.equal(saves[0].args[1][0].id, 7);
  if (scenario === 'paste-batch') { assertShareCount(1); assert.equal(shareBoxes()[0].checked, true); }
}
async function deleteScenario() {
  // Same local IDs/names can recur after a read; they cannot authorize an old Yes.
  const data = reply();
  data.formations.push({id: 8, name: 'Other', probes: [{x: 0, y: 0, z: 0, range: 149597870700}]});
  WM.openFormations(accounts, 'choice-A'); reads.at(-1).resolve(data); await tick();
  selectShare(0); selectShare(1);
  if (scenario === 'delete-during-reload') click('fm-reload');
  if (scenario === 'delete-during-save-reread' || scenario === 'delete-live-during-save') {
    rename('Submitted'); click('fm-save');
    if (scenario === 'delete-during-save-reread') complete(saves[0]);
  }
  assert.equal(WM.el('fm-delete').disabled, false, 'live draft editing must remain available');
  click('fm-delete'); const confirmation = confirms.at(-1);
  assert.match(confirmation.args[1], scenario.includes('save') ? /"Submitted"/ : /"Original"/);
  const saveCount = saves.length;
  if (scenario === 'delete-during-reload' || scenario === 'delete-during-save-reread') {
    const replacement = plain(data);
    replacement.content_revision = C;
    replacement.formations[0].probes[0].x = 9000;
    // Identical local ID and name, but a distinct external document.
    reads.at(-1).resolve(replacement); await tick();
  } else if (scenario === 'delete-after-exit' || scenario === 'delete-after-reopen') {
    WM.route('evesettings');
    // Keep the entry read unresolved: the old object still occupies the pane.
    // A current-object-only guard is not a session guard.
    if (scenario === 'delete-after-reopen') WM.openFormations(accounts, 'choice-A');
  } else if (scenario === 'delete-selection-changed') rowButtons()[1].click();
  confirmation.resolve(true); await tick();
  assert.equal(saves.length, saveCount, 'Delete never writes an account file');
  if (scenario === 'delete-live-during-save') {
    assert.deepEqual(rowButtons().map(e => e.textContent), ['Other']); assertShareCount(1);
    complete(saves[0]);
    assert.equal(reads.length, 2, 'completion cannot reload over a newer deletion');
    assertEditable('Other'); click('fm-save');
    assert.equal(saves[1].args[2], B);
    assert.deepEqual(plain(saves[1].args[1]).map(f => [f.id, f.name]), [[8, 'Other']]);
    return;
  }
  assert.deepEqual(rowButtons().map(e => e.textContent), ['Original', 'Other'], 'stale Yes must not delete any current formation');
  if (scenario === 'delete-after-exit' || scenario === 'delete-after-reopen') {
    assert.equal(WM.el('fm-save-status').textContent, '', 'an old session must not report into the new one');
    if (scenario === 'delete-after-reopen') {
      reads.at(-1).resolve(data); await tick();
      assert.deepEqual(rowButtons().map(e => e.textContent), ['Original', 'Other']);
      assert.equal(WM.el('fm-dirty').textContent, '');
    } else assert.equal(WM.current_route, 'evesettings');
    return;
  }
  assert.equal(WM.el('fm-dirty').textContent, '');
  assert.match(WM.el('fm-save-status').textContent, /Nothing was deleted.*Delete again/);
  if (scenario === 'delete-selection-changed') {
    assert.equal(WM.el('fm-name').value, 'Other'); assertShareCount(2);
  } else {
    assert.equal(WM.el('fm-name').value, 'Original'); assertShareCount(0);
    const x = WM.el('fm-probes').children.find(e => e.getAttribute('aria-label') === 'Probe 1 West km');
    assert.equal(x.value, '9');
  }
  // Retrying Delete is live; No is harmless, Yes removes only the now-named row.
  click('fm-delete'); confirms.at(-1).resolve(false); await tick();
  assert.equal(rowButtons().length, 2); assert.equal(WM.el('fm-dirty').textContent, '');
  click('fm-delete'); confirms.at(-1).resolve(true); await tick();
  const expected = scenario === 'delete-selection-changed' ? 'Original' : 'Other';
  assert.deepEqual(rowButtons().map(e => e.textContent), [expected]);
  assert.equal(WM.el('fm-dirty').textContent, 'Unsaved changes');
  assert.equal(saves.length, saveCount);
}
function svgNodes(svg, cls) {
  return descendants(svg).filter(e => e.getAttribute('class') === cls);
}
function ringLabels(svg) {
  // Accept labels anywhere first: the precision test must expose rounding,
  // independently of whether the annotation lane has been implemented yet.
  return descendants(svg.parentNode).filter(e =>
    (e.className || e.getAttribute('class')) === 'fm-ring-label');
}
function assertExternalKey(svg, expected) {
  assert.deepEqual(ringLabels(svg).map(e => e.textContent), expected);
  assert.equal(svgNodes(svg, 'fm-ring-label').length, 0,
    'ring distances must not share the rotating probe drawing area');
  const key = descendants(svg.parentNode).find(e => e.id === svg.getAttribute('aria-describedby'));
  assert.ok(key, 'the SVG must describe its scale through the visible external key');
  assert.match(key.textContent, /inner.*outer/i, 'the key must explain which ring each distance names');
  assert.equal(key.hidden, false);
  assert.equal(svg.getAttribute('role'), 'img');
  assert.ok(svg.getAttribute('aria-label'));
}
async function previewScenario() {
  const svg = WM.el('fm-preview');
  svg.rect = {width: 150, height: 150};
  const data = reply();
  if (scenario === 'preview-key-separation') {
    data.formations[0].probes = [
      {x: -10000000, y: 0, z: 0, range: 598391482800},
      {x: 10000000, y: 0, z: 0, range: 598391482800},
      {x: 0, y: -10000000, z: 0, range: 598391482800},
      {x: 0, y: 10000000, z: 0, range: 598391482800}
    ];
  } else if (scenario === 'preview-origin-scale') data.formations[0].probes[0].x = 0;
  else if (scenario === 'preview-fractional-scale') data.formations[0].probes[0].x = 7000;
  WM.openFormations(accounts, 'choice-A'); reads.at(-1).resolve(data); await tick();
  assert.equal(svg.getAttribute('viewBox'), '0 0 150 150');
  assert.equal(svgNodes(svg, 'fm-ring').length, 3);
  if (scenario === 'preview-origin-scale' || scenario === 'preview-fractional-scale') {
    assertExternalKey(svg, scenario === 'preview-origin-scale'
      ? ['0.5 km', '1 km', '1.5 km'] : ['2.5 km', '5 km', '7.5 km']);
  } else if (scenario === 'preview-key-separation') {
    assertExternalKey(svg, ['5,000 km', '10,000 km', '15,000 km']);
    assert.equal(svgNodes(svg, 'fm-probe').length, 4);
  } else if (scenario === 'preview-empty-scale') {
    assertExternalKey(svg, ['1 km', '2 km', '3 km']);
    WM.el('fm-probes').children.find(e => e.textContent === 'Remove').click();
    assert.equal(svgNodes(svg, 'fm-ring').length, 0);
    assert.equal(ringLabels(svg).length, 0, 'removing the last probe must clear the previous scale');
    assert.equal(svgNodes(svg, 'fm-ship').length, 1);
    data.formations = [];
    WM.openFormations(accounts, 'choice-A'); reads.at(-1).resolve(data); await tick();
    assert.equal(svg.children.length, 0); assert.equal(ringLabels(svg).length, 0);
  } else if (scenario === 'preview-import-key') {
    const imported = WM.el('fm-import-preview'); imported.rect = {width: 150, height: 150};
    const incoming = shared(); incoming.probes[0] = {x: 0, y: 0, z: 0, range: 149597870700};
    await review([incoming]);
    assertExternalKey(imported, ['0.5 km', '1 km', '1.5 km']);
    assert.equal(svgNodes(imported, 'fm-probe').length, 1);
    inputText('');
    assert.equal(svgNodes(imported, 'fm-ring').length, 0);
    assert.equal(ringLabels(imported).length, 0, 'invalidating a review must clear its scale');
  } else if (scenario === 'preview-rotation') {
    const positions = () => svgNodes(svg, 'fm-probe').map(e => [e.getAttribute('cx'), e.getAttribute('cy')]);
    const before = positions();
    // Original 150px projection of (2, 0, 0) km, checked independently.
    assert.ok(Math.abs(Number(before[0][0]) - 101.96096) < 0.001);
    assert.ok(Math.abs(Number(before[0][1]) - 67.817) < 0.001);
    svg.dispatchEvent({type: 'mousedown', clientX: 0, clientY: 0});
    for (const [x, y] of [[100, -40], [200, 120], [-300, -200], [60, 30]]) {
      window.dispatchEvent({type: 'mousemove', clientX: x, clientY: y});
      assertExternalKey(svg, ['1 km', '2 km', '3 km']);
    }
    assert.notDeepEqual(positions(), before, 'drag must still rotate the real projection');
    window.dispatchEvent({type: 'mouseup'});
    const released = positions();
    window.dispatchEvent({type: 'mousemove', clientX: 900, clientY: 900});
    assert.deepEqual(positions(), released, 'mouseup must stop rotation');
    svg.rect = {width: 300, height: 200}; window.dispatchEvent({type: 'resize'});
    assert.equal(svg.getAttribute('viewBox'), '0 0 300 200');
    assert.notDeepEqual(positions(), released);
    assert.equal(WM.el('fm-dirty').textContent, '', 'rotation and resize are not document edits');
    rename('Rotated'); click('fm-save'); assertSave(saves[0], A, 'Rotated');
  } else assert.fail('Unknown preview scenario: ' + scenario);
  if (scenario !== 'preview-rotation') assert.equal(saves.length, 0);
}
async function main() {
  await open();
  if (scenario.startsWith('preview-')) await previewScenario();
  else if (scenario.startsWith('delete-')) await deleteScenario();
  else if (scenario.startsWith('paste-')) await pasteScenario();
  else if (scenario.startsWith('copy-')) await copyScenario();
  else if (scenario === 'account-context') {
    const context = () => WM.el('fm-account-context').textContent;
    assert.equal(context(), 'Account: Account A');
    assert.equal(WM.el('fm-account').title, 'Account A');
    switchTo('choice-B'); await tick();
    assert.equal(context(), 'Account: Account A', 'pending switch still shows the loaded account');
    reads.at(-1).resolve({ok: false, error: 'unreadable'}); await tick();
    assert.equal(context(), 'Account: Account A', 'failed switch must not relabel the draft');
    switchTo('choice-B'); await tick();
    reads.at(-1).resolve(reply(C, 'Other', 'resolved-B')); await tick();
    assert.equal(context(), 'Account: Account B');
    assert.equal(WM.el('fm-account').title, 'Account B');
  }
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
}
await main();
await tick();
if (unhandledRejections.length) {
  const error = unhandledRejections[0];
  throw isNativeError(error) ? error : new Error(String(error));
}
const encodingBoundary = encodingBoundaries[0] || '';
assert.ok(encodingBoundaries.every(value => value === encodingBoundary),
  'all Python children must receive the same request environment');
return {duration_ms: performance.now() - started, output: 'PASS ' + scenario,
  encoding_boundary: encodingBoundary};
} finally {
  process.removeListener('unhandledRejection', onUnhandledRejection);
}
}

async function serve() {
  const input = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
  for await (const line of input) {
    let request;
    const requestStarted = performance.now();
    try {
      request = JSON.parse(line);
      const result = await runScenario(request);
      process.stdout.write(JSON.stringify({
        id: request.id,
        scenario: request.scenario,
        ok: true,
        duration_ms: result.duration_ms,
        error: '',
        stack: '',
        output: result.output,
        encoding_boundary: result.encoding_boundary
      }) + '\n');
    } catch (error) {
      process.stdout.write(JSON.stringify({
        id: request && Number.isInteger(request.id) ? request.id : 0,
        scenario: request && typeof request.scenario === 'string' ? request.scenario : '',
        ok: false,
        duration_ms: performance.now() - requestStarted,
        error: isNativeError(error) ? error.message : String(error),
        stack: isNativeError(error) ? error.stack || '' : ''
      }) + '\n');
    }
  }
}

serve().catch(error => { console.error(error); process.exitCode = 1; });
