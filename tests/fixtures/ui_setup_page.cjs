const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const page = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const scenario = process.argv[3];

// PageTree supplies real production ancestry/attributes. Only DOM mechanics and
// bridge/clipboard delivery are doubled; no setup page state lives in this DOM.
class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase(); this.attrs = {...attrs};
    this.id = attrs.id || ''; this.className = attrs.class || '';
    this.children = []; this.listeners = {}; this.value = attrs.value || '';
    this.disabled = 'disabled' in attrs; this.hidden = 'hidden' in attrs;
  }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
  querySelectorAll(selector) {
    const all = this.children.flatMap(child => [child, ...child.querySelectorAll('*')]);
    if (selector === '*') return all;
    return all.filter(el => selector === el.tagName.toLowerCase());
  }
  get classList() { return {toggle: (name, on) => {
    const list = this.className.split(/\s+/).filter(x => x && x !== name);
    if (on) list.push(name); this.className = list.join(' ');
  }}; }
  get options() { return this.children; }
  get selectedIndex() { return this.children.findIndex(child => child.value === this.value); }
  set textContent(text) { this.children = []; this.text = String(text); }
  get textContent() { return (this.text || '') + this.children.map(x => x.textContent).join(''); }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  getAttribute(key) { return this.attrs[key] ?? null; }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  dispatchEvent(event) {
    event.target ||= this; event.preventDefault ||= () => {};
    (this.listeners[event.type] || []).forEach(callback => callback(event));
  }
  click() { if (!this.disabled) this.dispatchEvent({type: 'click'}); }
  focus() { document.activeElement = this; }
  scrollIntoView() {} // Geometry is checked by the isolated browser driver, not this DOM.
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
const contexts = [], limits = [], snapshots = [], saves = [], clipboardWrites = [], mutations = [];
const reviews = [], discards = [], creates = [], reads = [], clipboardReads = [], profilesReads = [];
const handlers = {}; let formationsCompletions = 0;
function deferred(args) {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {args, promise, resolve, reject};
}
const navigator = {clipboard: {readText: () => {
  const read = deferred([]); clipboardReads.push(read); return read.promise;
}, writeText: text => {
  if (scenario === 'copy-throws') throw new Error('Clipboard unavailable');
  const write = deferred([text]); clipboardWrites.push(write); return write.promise;
}}};
if (scenario === 'copy-unavailable') delete navigator.clipboard;
const WM = {
  current_route: 'evesettings',
  handle: (name, handler) => { assert.equal(handlers[name], undefined); handlers[name] = handler; },
  formationsDone: () => { formationsCompletions++; },
  el: id => { assert.ok(ids[id], 'Missing production markup: ' + id); return ids[id]; },
  make: (tag, cls, text) => {
    const el = new Element(tag, {class: cls});
    if (text !== undefined) el.textContent = text;
    return el;
  },
  setEnabled: (id, value) => { WM.el(id).disabled = !value; },
  route: name => {
    WM.current_route = name;
    document.dispatchEvent({type: 'wm:route', detail: name});
  },
  send: (method, ...args) => {
    const request = deferred(args);
    const destinations = {eve_settings_setup_context: contexts, eve_settings_setup_limits: limits,
      eve_settings_setup_export: snapshots, eve_settings_setup_save_file: saves,
      eve_settings_setup_review: reviews, eve_settings_setup_discard: discards,
      eve_settings_setup_create: creates, eve_settings_setup_read_file: reads,
      eve_settings_state: profilesReads};
    if (method === 'eve_settings_setup_create') {
      assert.equal(WM.el('setup-create').disabled, true, 'lock before sending Create');
      assert.equal(WM.el('setup-text').disabled, true, 'lock editing before sending Create');
      assert.match(WM.el('setup-back').textContent, /Back/);
      if (scenario === 'done-before-accepted' || scenario === 'done-before-refused') {
        assert.equal(WM.uiSetupDone(completion(args)), true, 'identity must exist before send');
      }
    }
    if (!destinations[method]) { mutations.push({method, args}); assert.fail('Unexpected/mutation call: ' + method); }
    destinations[method].push(request); return request.promise;
  }
};
assert.ok(ids['route-uisetup'], 'Missing production setup route');
assert.ok(fs.existsSync(process.argv[4]), 'Missing production setup module');
vm.runInNewContext(fs.readFileSync(process.argv[4], 'utf8'), {
  WM, document, window: {}, navigator, console, Promise
}, {filename: process.argv[4]});
if (scenario === 'forwarded-completion') {
  // Execute the entire production owner. Only defer DOMContentLoaded wiring;
  // completion handlers register immediately, exactly as they do in the app.
  document.readyState = 'loading';
  document.querySelector = () => null;
  const owner = require('node:path').join(require('node:path').dirname(process.argv[4]), 'evesettings.js');
  vm.runInNewContext(fs.readFileSync(owner, 'utf8'), {WM, document, window: {}, console, Promise});
  document.readyState = 'complete';
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const click = id => WM.el(id).click();
function change(id, value) { WM.el(id).value = value; WM.el(id).dispatchEvent({type: 'change'}); }
const status = () => WM.el('us-status').textContent;
const plain = value => JSON.parse(JSON.stringify(value));
function context(profile = 'profile-A') {
  const data = {ok: true, error: '', root: 'root', server: 'server', profile,
    profiles: [{path: 'profile-A', name: 'Base A', file_count: 4}, {path: 'profile-B', name: 'Base B', file_count: 4}],
    accounts: [
      {path: 'account-A', id: '10', name: 'Account <A>', display_name: 'Account <A>', display_meta: '', account_name: 'Account A', character_ids: ['11']},
      {path: 'account-B', id: '20', name: 'Account B', display_name: 'Account B', display_meta: '', account_name: 'Account B', character_ids: ['21']}
    ],
    characters: [
      {path: 'char-A', id: '11', name: 'Pilote é 𐐀 <img>', display_name: 'Pilote é 𐐀 <img>', display_meta: ''},
      {path: 'char-B', id: '21', name: 'Pilot B', display_name: 'Pilot B', display_meta: ''}
    ], account_identity_available: true, setup_available: true};
  if (profile === 'profile-B') {
    data.accounts = [{path: 'B-account', id: '40', name: 'Other account', character_ids: ['41']}];
    data.characters = [{path: 'B-char', id: '41', name: 'Other recipient'}];
  }
  return data;
}
// Use the real facade limits, parser/exporter and summary with synthetic fixture
// data. Both directions explicitly use UTF-8 bytes, even under cp1252 stdio.
function python(kind, text = 'Étiquette 𐐀 <b>literal</b>') {
  const script = [
    'import json,sys',
    'from wingman.ui.api import Api',
    'from wingman.evesettings.controller import ProfilesController',
    'from wingman.evesettings import setup_model, setup_sharing',
    'from tests.setup_fixtures import wire',
    'kind,label=json.loads(sys.stdin.buffer.read().decode("utf-8"))',
    'api=Api.__new__(Api); api._profiles=ProfilesController.__new__(ProfilesController)',
    'value=wire(); value["overview"]["shipLabels"][0]["pre"]=label',
    'result=api.eve_settings_setup_limits() if kind=="limits" else {"ok":True,"error":"","text":setup_sharing.export_text(value),"summary":setup_model.summarize(setup_model.validate_wingman(value)),"warnings":["2 effective unsaved filter definitions override saved definitions in this snapshot."]}',
    'if kind=="native":',
    ' from pathlib import Path',
    ' text=Path("tests/fixtures/ui_setup/native-complete.yaml").read_text(encoding="utf-8"); parsed=setup_sharing.parse_text(text)',
    ' result={"text":text,"summary":setup_model.summarize(parsed),"warnings":list(parsed.warnings),"ambiguous":parsed.ambiguous_labels}',
    'if kind=="boundary":',
    ' import tempfile,pytest',
    ' from pathlib import Path',
    ' from dataclasses import replace',
    ' from tests.test_ui_setup_controller import setup,review',
    ' with tempfile.TemporaryDirectory() as temp, pytest.MonkeyPatch.context() as patch:',
    '  patch.setenv("LOCALAPPDATA",temp)',
    '  ctl,_,base=setup.__wrapped__(Path(temp),patch)',
    '  if label=="eve-unknown": ctl._ports=replace(ctl._ports,profile_copy_refusal=lambda:"Cannot confirm that EVE is closed.")',
    '  result=review(ctl,base,text="broken: [" if label=="malformed-text" else None)',
    '  if label=="stale-manifest":',
    '   assert result["ok"],result',
    '   (base.profile/"prefs.ini").write_bytes(b"changed after review")',
    '   result=ctl.setup_create(result["review_id"],"ui-boundary")',
    '   assert not result["accepted"] and not ctl._done_pushes',
    '  else: assert not result["ok"]',
    'sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode("utf-8"))'
  ].join('\n');
  const result = spawnSync(process.argv[5], ['-c', script], {input: JSON.stringify([kind, text]), encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr); return JSON.parse(result.stdout);
}
const exported = python('export');
async function open(data = context()) {
  const opener = {mode: 'export', context: data, preferred_character: 'char-A'};
  WM.openUiSetup(opener);
  assert.deepEqual(plain(contexts.at(-1).args), [data.profile]);
  // A caller owns its payload; mutating it cannot change this view's request.
  data.profile = 'caller-changed';
  limits.at(-1).resolve(python('limits'));
  contexts.at(-1).resolve(context()); await tick();
  assert.equal(WM.el('us-character').value, 'char-A');
  assert.equal(WM.el('us-account').value, '', 'preferred character must not select an account');
  assert.equal(snapshots.length, 0, 'opening or prefill alone must not snapshot');
}
async function selectPair() {
  change('us-account', 'account-A');
  assert.deepEqual(plain(snapshots.at(-1).args), ['profile-A', 'account-A', 'char-A']);
  snapshots.at(-1).resolve(exported); await tick();
}
function assertRetry() {
  assert.equal(WM.el('us-copy').disabled, false);
  assert.equal(WM.el('us-save').disabled, false);
  assert.equal(WM.el('us-back').disabled, false);
}
async function main() {
  if (process.argv[6] === 'import') { await importMain(); console.log('PASS ' + scenario); return; }
  assert.equal(WM.el('us-copy').disabled, true);
  assert.equal(WM.el('us-save').disabled, true);
  if (scenario === 'context-failure') {
    WM.openUiSetup({mode: 'export', context: context(), preferred_character: ''});
    limits.at(-1).resolve(python('limits')); contexts.at(-1).reject(new Error('offline')); await tick();
    assert.match(status(), /context|profile/i); assert.equal(WM.el('us-copy').disabled, true);
    assert.equal(WM.el('us-refresh').disabled, false); click('us-refresh');
    contexts.at(-1).resolve(context()); limits.at(-1).resolve(python('limits')); await tick();
    assert.equal(WM.el('us-character').disabled, false);
  } else if (scenario === 'late-context') {
    WM.openUiSetup({mode: 'export', context: context()});
    const old = contexts.at(-1), oldLimits = limits.at(-1);
    WM.openUiSetup({mode: 'export', context: context('profile-B')});
    contexts.at(-1).resolve(context('profile-B')); limits.at(-1).resolve(python('limits')); await tick();
    const before = status(); old.resolve({ok: false, error: 'Old context failed'});
    oldLimits.resolve(python('limits')); await tick();
    assert.equal(status(), before); assert.equal(WM.el('us-profile').value, 'profile-B');
    assert.equal(WM.el('us-copy').disabled, true);
  } else if (scenario === 'unavailable-pairs') {
    for (const variant of ['accounts', 'characters', 'links', 'codec', 'identity']) {
      WM.openUiSetup({mode: 'export', context: context(), preferred_character: 'char-A'});
      const data = context();
      if (variant === 'accounts' || variant === 'characters') data[variant] = [];
      if (variant === 'links') data.accounts.forEach(a => a.character_ids = []);
      if (variant === 'codec') data.setup_available = false;
      if (variant === 'identity') data.account_identity_available = false;
      contexts.at(-1).resolve(data); limits.at(-1).resolve(python('limits')); await tick();
      change('us-account', 'account-A'); click('us-copy'); click('us-save');
      assert.equal(snapshots.length, 0); assert.equal(saves.length, 0);
      assert.equal(WM.el('us-copy').disabled, true); assert.ok(status());
    }
  } else if (scenario === 'singular-counts') {
    await open(); change('us-account', 'account-A');
    const one = plain(exported);
    for (const key of Object.keys(one.summary.counts)) one.summary.counts[key] = 1;
    snapshots.at(-1).resolve(one); await tick();
    assert.equal(WM.el('us-counts').textContent, '1 filter · 1 tab · 1 overview group · 1 ship label · 1 layout window');
  } else {
    await open();
    if (scenario === 'missing-pair') {
      const count = snapshots.length;
      change('us-account', 'account-B');
      assert.equal(snapshots.length, count); assert.match(status(), /confirmed|pair/i);
      assert.equal(WM.el('us-copy').disabled, true);
      change('us-character', 'char-B'); assert.equal(snapshots.length, count + 1);
      snapshots.at(-1).resolve(exported); await tick(); assertRetry();
    } else {
      await selectPair();
      assert.match(WM.el('us-counts').textContent, /3 filters.*8 tabs.*3 overview.*9 ship.*12 layout/i);
      assert.match(WM.el('us-windows').textContent, /Probe scanner/);
      assert.match(WM.el('us-warnings').textContent, /2 effective unsaved/);
      assert.match(WM.el('us-source').textContent, /Pilote é 𐐀 <img>/);
      assert.equal(WM.el('us-source').children.length, 0, 'user names are text, not markup');
      assert.match(WM.el('us-limits').textContent, /256 filters/);
      assert.equal(WM.el('us-actions').parentNode, WM.el('us-work').parentNode, 'actions must be outside scrolling work');
      assert.equal(WM.uiSetupDone({operation: 'ui_setup_create', request_id: 'old', review_id: 'old', ok: true}), false);
      const isSave = scenario.startsWith('save-');
      click(isSave ? 'us-save' : 'us-copy');
      const pending = snapshots.at(-1);
      assert.equal(snapshots.length, 2, 'every action must take a fresh snapshot');
      assert.deepEqual(plain(pending.args), ['profile-A', 'account-A', 'char-A']);
      if (['export-source-change', 'export-route-exit', 'export-reopen', 'context-change', 'late-errors'].includes(scenario)) {
        if (scenario === 'export-source-change') change('us-character', 'char-B');
        else if (scenario === 'export-route-exit') WM.route('main');
        else if (scenario === 'context-change') change('us-profile', 'profile-B');
        else WM.openUiSetup({mode: 'export', context: context(), preferred_character: 'char-B'});
        const before = status();
        if (scenario === 'late-errors') pending.reject(new Error('stale failure')); else pending.resolve(exported);
        await tick(); assert.equal(status(), before); assert.equal(clipboardWrites.length, 0); assert.equal(saves.length, 0);
        assert.equal(WM.el('us-counts').textContent, '', 'invalidation clears the old summary');
      } else if (scenario === 'unsupported-stack') {
        pending.resolve({ok: false, error: 'Unsupported stack: overview_1, selecteditemview', text: '', summary: {}, warnings: []});
        await tick(); assert.match(status(), /stack.*overview_1/); assert.equal(clipboardWrites.length, 0); assertRetry();
      } else {
        const fresh = python('export', 'Fresh é 𐐀 <script>');
        pending.resolve(fresh); await tick();
        if (isSave) {
          assert.equal(saves.length, 1); assert.equal(saves[0].args[0], fresh.text);
          assert.doesNotMatch(status(), /saved/i);
          if (scenario === 'save-cancel') saves[0].resolve({ok: false, cancelled: true, error: '', path: ''});
          else if (scenario === 'save-failure') saves[0].resolve({ok: false, cancelled: false, error: 'Disk <full>', path: ''});
          else if (scenario === 'save-rejected') saves[0].reject(new Error('disconnected'));
          else {
            WM.openUiSetup({mode: 'export', context: context()});
            const before = status(); saves[0].resolve({ok: true, cancelled: false, error: '', path: 'file.json'});
            await tick(); assert.equal(status(), before);
          }
          await tick();
          if (scenario === 'save-cancel') { assert.match(status(), /cancel/i); assertRetry(); }
          if (scenario === 'save-failure') { assert.match(status(), /Disk <full>/); assertRetry(); }
          if (scenario === 'save-rejected') { assert.match(status(), /Could not save/); assertRetry(); }
        } else if (scenario === 'copy-unavailable' || scenario === 'copy-throws') {
          assert.equal(clipboardWrites.length, 0); assert.match(status(), /clipboard.*Save file|Save file.*clipboard/i); assertRetry();
        } else {
          assert.equal(clipboardWrites.length, 1); assert.equal(clipboardWrites[0].args[0], fresh.text);
          assert.doesNotMatch(status(), /copied/i);
          if (scenario === 'copy-denied') {
            clipboardWrites[0].reject(new Error('denied')); await tick();
            assert.match(status(), /clipboard.*Save file|Save file.*clipboard/i); assertRetry();
            click('us-copy'); snapshots.at(-1).resolve(fresh); await tick(); clipboardWrites.at(-1).resolve(); await tick();
            assert.match(status(), /copied/i);
          } else if (scenario === 'copy-late-success' || scenario === 'copy-late-denial') {
            change('us-account', 'account-B'); const before = status();
            if (scenario === 'copy-late-denial') clipboardWrites[0].reject(new Error('late denial'));
            else clipboardWrites[0].resolve();
            await tick();
            assert.equal(status(), before); assert.doesNotMatch(status(), /copied/i);
          } else {
            clipboardWrites[0].resolve(); await tick(); assert.match(status(), /copied/i); assertRetry();
            assert.match(JSON.parse(clipboardWrites[0].args[0]).overview.shipLabels[0].pre, /Fresh é 𐐀/);
            click('us-save'); snapshots.at(-1).resolve(fresh); await tick();
            saves.at(-1).resolve({ok: true, cancelled: false, error: '', path: 'local-é.json'}); await tick();
            assert.match(status(), /saved.*local-é.json/i); assertRetry();
          }
        }
      }
    }
  }
  assert.equal(mutations.length, 0, 'export never mutates EVE settings');
  assert.equal(WM.el('us-back').disabled, false);
  console.log('PASS ' + scenario);
}
const importStatus = () => WM.el('setup-status').textContent;
const input = (id, value) => { WM.el(id).value = value; WM.el(id).dispatchEvent({type: 'input'}); };
function completion(args, extra = {}) {
  return {ok: true, operation: 'ui_setup_create', request_id: args[1], review_id: args[0],
    published: true, path: 'root/server/settings_Imported', selection_persisted: true,
    error_code: '', error: '', warning: '', ...extra};
}
function offer(id = 'r1', fixture = exported) {
  return {ok: true, error: '', error_code: '', review_id: id, summary: fixture.summary,
    warnings: fixture.warnings, needs_label_choice: false};
}
async function importOpen() {
  const data = context(); WM.openUiSetup({mode: 'import', context: data, preferred_character: 'char-A'});
  assert.ok(contexts.length, 'Import must read its own setup context');
  assert.deepEqual(plain(contexts.at(-1).args), ['profile-A']); data.profile = 'caller-mutated';
  contexts.at(-1).resolve(context()); limits.at(-1).resolve(python('limits')); await tick();
  assert.equal(WM.el('setup-account').value, '');
  change('setup-account', 'account-A'); input('setup-text', exported.text); input('setup-name', 'Imported');
  assert.equal(WM.el('setup-review').disabled, false);
}
async function reviewed(id = 'r1') {
  click('setup-review');
  assert.deepEqual(plain(reviews.at(-1).args), [WM.el('setup-text').value, 'profile-A', 'account-A', 'char-A', WM.el('setup-name').value, !!WM.el('setup-keep-labels').checked]);
  reviews.at(-1).resolve(offer(id)); await tick();
  assert.equal(WM.el('setup-create').disabled, false);
}
function freshReviewRequired() {
  assert.equal(WM.el('setup-create').disabled, true);
  assert.equal(WM.el('setup-text').disabled, false);
  assert.equal(WM.el('setup-review').disabled, false);
  assert.match(importStatus(), /review.*again|fresh review/i);
}
async function importMain() {
  await importOpen();
  if (scenario === 'context-does-not-select') {
    assert.equal(WM.el('setup-base').value, 'profile-A'); click('setup-back');
    assert.equal(WM.current_route, 'evesettings'); assert.equal(document.activeElement.id, 'es-setup-import');
  } else if (scenario === 'base-rosters-differ' || scenario === 'edit-during-context') {
    change('setup-base', 'profile-B');
    assert.equal(WM.el('setup-character').value, ''); assert.equal(WM.el('setup-account').value, '');
    if (scenario === 'edit-during-context') input('setup-name', 'While loading');
    contexts.at(-1).resolve(context('profile-B')); limits.at(-1).resolve(python('limits')); await tick();
    assert.equal(WM.el('setup-character').children.some(e => e.value === 'char-A'), false);
    change('setup-character', 'B-char'); change('setup-account', 'B-account'); click('setup-review');
    assert.deepEqual(plain(reviews.at(-1).args).slice(1, 4), ['profile-B', 'B-account', 'B-char']);
  } else if (scenario.startsWith('review-invalidated-by-') || scenario === 'keep-invalidates') {
    await reviewed();
    const field = scenario.split('-').at(-1);
    if (field === 'text') input('setup-text', exported.text + ' ');
    else if (field === 'name') input('setup-name', 'Other');
    else if (field === 'base') change('setup-base', 'profile-B');
    else if (scenario === 'keep-invalidates') { WM.el('setup-keep-labels').checked = true; change('setup-keep-labels', ''); }
    else change('setup-account', 'account-B');
    assert.equal(WM.el('setup-create').disabled, true); click('setup-create');
    assert.deepEqual(plain(discards.at(-1).args), ['r1']); assert.equal(creates.length, 0);
    assert.equal(WM.el('setup-summary').hidden, true);
    // A response in flight for an earlier input cannot restore authorization.
    if (field === 'name' || field === 'text') {
      click('setup-review'); const pending = reviews.at(-1); input('setup-name', 'Newer');
      pending.resolve(offer('old-input')); await tick();
      assert.equal(WM.el('setup-create').disabled, true);
      assert.deepEqual(plain(discards.at(-1).args), ['old-input']);
    }
  } else if (scenario === 'old-discard-after-new-review') {
    await reviewed('old'); input('setup-name', 'Newer'); const cleanup = discards.at(-1);
    await reviewed('new'); cleanup.resolve(false); await tick();
    assert.equal(WM.el('setup-create').disabled, false); click('setup-create');
    assert.equal(creates.at(-1).args[0], 'new');
  } else if (scenario === 'pending-pair' || scenario === 'pending-base' || scenario === 'late-review-error') {
    click('setup-review'); const old = reviews.at(-1);
    if (scenario === 'pending-pair') change('setup-character', 'char-B');
    else if (scenario === 'pending-base') change('setup-base', 'profile-B');
    else input('setup-name', 'Newer');
    const before = importStatus();
    if (scenario === 'late-review-error') old.reject(new Error('late error')); else old.resolve(offer('old'));
    await tick(); assert.equal(importStatus(), before); assert.equal(WM.el('setup-create').disabled, true);
    if (scenario !== 'late-review-error') assert.deepEqual(plain(discards.at(-1).args), ['old']);
  } else if (scenario === 'import-context-failure' || scenario === 'import-late-context' || scenario === 'import-limits-failure') {
    change('setup-base', 'profile-B'); const old = contexts.at(-1), oldLimits = limits.at(-1);
    if (scenario === 'import-late-context') {
      click('setup-refresh'); contexts.at(-1).resolve(context('profile-B')); limits.at(-1).resolve(python('limits')); await tick();
      const before = importStatus(); old.resolve(context()); oldLimits.resolve(python('limits')); await tick();
      assert.equal(importStatus(), before); assert.equal(WM.el('setup-base').value, 'profile-B');
    } else {
      if (scenario === 'import-limits-failure') { old.resolve(context('profile-B')); oldLimits.reject(new Error('limits failed')); }
      else { old.reject(new Error('context failed')); oldLimits.resolve(python('limits')); }
      await tick(); assert.equal(WM.el('setup-create').disabled, true);
      assert.equal(WM.el('setup-refresh').disabled, false); click('setup-refresh');
      contexts.at(-1).resolve(context('profile-B')); limits.at(-1).resolve(python('limits')); await tick();
      assert.equal(WM.el('setup-character').disabled, false);
    }
  } else if (scenario === 'old-review-after-new') {
    click('setup-review'); const old = reviews.at(-1);
    input('setup-name', 'Newer'); click('setup-review'); const current = reviews.at(-1);
    current.resolve(offer('new')); await tick(); old.resolve(offer('old')); await tick();
    assert.deepEqual(plain(discards.at(-1).args), ['old']);
    discards.at(-1).resolve(true); await tick();
    assert.equal(WM.el('setup-create').disabled, false); click('setup-create');
    assert.equal(creates.at(-1).args[0], 'new');
  } else if (scenario === 'cancel-during-review' || scenario === 'cancel-reviewed') {
    click('setup-review'); const pending = reviews.at(-1);
    if (scenario === 'cancel-reviewed') { pending.resolve(offer()); await tick(); }
    click('setup-back'); assert.equal(WM.current_route, 'evesettings');
    if (scenario === 'cancel-during-review') { pending.resolve(offer()); await tick(); }
    assert.deepEqual(plain(discards.at(-1).args), ['r1']); assert.equal(creates.length, 0);
    assert.equal(WM.el('setup-text').value, '');
  } else if (scenario === 'yaml-label-choice' || scenario === 'yaml-no-layout') {
    const native = python('native'); assert.equal(native.ambiguous, true);
    input('setup-text', native.text); click('setup-review');
    reviews.at(-1).resolve({...offer('', native), ok: false, needs_label_choice: true,
      error: 'Choose Keep my ship labels explicitly for this YAML.', error_code: 'label_choice_required'}); await tick();
    assert.equal(WM.el('setup-create').disabled, true);
    assert.equal(WM.el('setup-label-choice').hidden, false); assert.equal(WM.el('setup-keep-labels').checked, false);
    assert.equal(WM.el('setup-keep-labels').parentNode.className, 'check');
    assert.match(WM.el('setup-native').textContent, /configuration only.*no window layout/i);
    assert.match(WM.el('setup-native').textContent, /one.*primary overview/i);
    WM.el('setup-keep-labels').checked = true; change('setup-keep-labels', ''); click('setup-review');
    assert.equal(reviews.at(-1).args[5], true); reviews.at(-1).resolve(offer('native', native)); await tick();
    assert.match(WM.el('setup-counts').textContent, /42 filters.*8 tabs.*1 overview group.*0 layout windows/);
    assert.match(WM.el('setup-retention').textContent, /ship labels.*retained|keep.*ship labels/i);
    if (scenario === 'yaml-label-choice') {
      input('setup-text', exported.text); assert.equal(WM.el('setup-keep-labels').checked, false);
      assert.equal(WM.el('setup-label-choice').hidden, true); assert.equal(WM.el('setup-create').disabled, true);
    }
  } else if (scenario === 'eve-unknown' || scenario === 'malformed-text') {
    const text = scenario === 'malformed-text' ? 'broken: [' : exported.text;
    input('setup-text', text); click('setup-review');
    assert.equal(reviews.at(-1).args[0], text);
    const refusal = python('boundary', scenario); reviews.at(-1).resolve(refusal); await tick();
    assert.equal(WM.el('setup-create').disabled, true); assert.equal(creates.length, 0);
    assert.ok(importStatus().includes(refusal.error)); assert.equal(WM.el('setup-text').value, text);
  } else if (scenario === 'missing-review-id' || scenario === 'review-rejected' || scenario === 'review-blank' || scenario === 'missing-summary') {
    if (scenario === 'review-blank') { input('setup-text', '  '); click('setup-review'); assert.equal(reviews.length, 0); }
    else {
      click('setup-review');
      if (scenario === 'missing-review-id') reviews.at(-1).resolve(offer(''));
      else if (scenario === 'missing-summary') reviews.at(-1).resolve({...offer(), summary: {}});
      else reviews.at(-1).reject(new Error('disconnected'));
      await tick(); assert.ok(importStatus());
    }
    assert.equal(WM.el('setup-create').disabled, true);
  } else if (scenario.startsWith('file-') || scenario.startsWith('paste-')) {
    await reviewed(); click(scenario.startsWith('file-') ? 'setup-file' : 'setup-paste');
    const pending = scenario.startsWith('file-') ? reads.at(-1) : clipboardReads.at(-1);
    assert.equal(WM.el('setup-create').disabled, true);
    if (scenario.endsWith('-late')) {
      input('setup-text', 'New text'); pending.resolve(scenario.startsWith('file-') ? {ok: true, cancelled: false, error: '', text: exported.text} : exported.text);
      await tick(); assert.equal(WM.el('setup-text').value, 'New text');
    } else if (scenario === 'file-cancel') {
      pending.resolve({ok: false, cancelled: true, error: '', text: ''}); await tick();
      assert.equal(WM.el('setup-text').value, exported.text); assert.match(importStatus(), /cancel/i);
    } else if (scenario === 'file-failure' || scenario === 'paste-denied') {
      pending.reject(new Error('denied')); await tick(); assert.match(importStatus(), /could not/i);
    } else {
      WM.el('setup-keep-labels').checked = true;
      pending.resolve({ok: true, cancelled: false, error: '', text: 'new file'}); await tick();
      assert.equal(WM.el('setup-text').value, 'new file'); assert.equal(WM.el('setup-keep-labels').checked, false);
    }
  } else if (scenario === 'labels-render-as-text' || scenario === 'import-unicode') {
    input('setup-name', 'Étiquette 𐐀 <img>'); await reviewed();
    assert.match(WM.el('setup-target').textContent, /Pilote é 𐐀 <img>/);
    assert.match(WM.el('setup-destination').textContent, /Étiquette 𐐀 <img>/);
    assert.equal(WM.el('setup-target').children.length, 0); assert.equal(WM.el('setup-destination').children.length, 0);
    assert.equal(reviews.at(-1).args[0], exported.text);
  } else if (scenario === 'import-unavailable-pairs') {
    for (const variant of ['accounts', 'characters', 'links', 'codec', 'identity']) {
      WM.openUiSetup({mode: 'import', context: context(), preferred_character: 'char-A'});
      const data = context();
      if (variant === 'accounts' || variant === 'characters') data[variant] = [];
      if (variant === 'links') data.accounts.forEach(a => a.character_ids = []);
      if (variant === 'codec') data.setup_available = false;
      if (variant === 'identity') data.account_identity_available = false;
      contexts.at(-1).resolve(data); limits.at(-1).resolve(python('limits')); await tick();
      input('setup-text', exported.text); input('setup-name', 'New'); change('setup-account', 'account-A');
      click('setup-review'); assert.equal(reviews.length, 0); assert.equal(WM.el('setup-create').disabled, true);
    }
  } else {
    await reviewed(); click('setup-create'); const pending = creates.at(-1);
    assert.ok(pending.args[1].length > 0 && pending.args[1].length <= 128);
    for (const id of ['setup-text', 'setup-base', 'setup-character', 'setup-account', 'setup-name', 'setup-keep-labels', 'setup-review', 'setup-create', 'setup-paste', 'setup-file']) {
      assert.equal(WM.el(id).disabled, true, 'sent create locks ' + id);
    }
    click('setup-create'); assert.equal(creates.length, 1);
    if (scenario === 'forwarded-completion') {
      handlers.onEveSettingsDone(completion(pending.args));
      assert.match(importStatus(), /created.*settings_Imported/);
      assert.equal(formationsCompletions, 0); assert.equal(profilesReads.length, 0);
      const hook = WM.uiSetupDone; delete WM.uiSetupDone;
      handlers.onEveSettingsDone(completion(pending.args)); WM.uiSetupDone = hook;
      assert.equal(formationsCompletions, 0);
      handlers.onEveSettingsDone({ok: true, operation: 'formation_save'});
      assert.equal(formationsCompletions, 1); assert.equal(profilesReads.length, 1);
    } else if (scenario === 'failed-create') {
      assert.equal(WM.uiSetupDone(completion(pending.args, {published: false, ok: false, error: 'Stage <failed>', error_code: 'create_failed', path: ''})), true);
      freshReviewRequired(); const before = importStatus(); pending.resolve({accepted: true}); await tick();
      assert.equal(importStatus(), before); assert.match(before, /Stage <failed>/);
    } else if (scenario === 'start-refused' || scenario === 'stale-manifest') {
      const refusal = scenario === 'stale-manifest' ? python('boundary', scenario) : {accepted: false, error: 'Busy <operation>'};
      pending.resolve(refusal); await tick(); freshReviewRequired(); assert.ok(importStatus().includes(refusal.error));
      assert.deepEqual(plain(discards.at(-1).args), ['r1']);
    } else if (scenario === 'create-rejected') {
      pending.reject(new Error('lost response')); await tick();
      assert.equal(WM.el('setup-text').disabled, true); assert.match(importStatus(), /could not confirm/i);
      assert.equal(WM.uiSetupDone(completion(pending.args)), true);
    } else if (scenario === 'done-before-accepted' || scenario === 'done-before-refused') {
      const before = importStatus(); pending.resolve({accepted: scenario === 'done-before-accepted', error: 'late refusal'}); await tick();
      assert.equal(importStatus(), before); assert.match(before, /created/i);
    } else if (scenario === 'route-exit-during-create') {
      assert.match(importStatus(), /leaving does not cancel/i); click('setup-back');
      assert.equal(discards.length, 0, 'a sent create cannot be cancelled');
      await importOpen(); const before = importStatus();
      assert.equal(WM.uiSetupDone(completion(pending.args)), false);
      pending.resolve({accepted: true, error: ''}); await tick(); assert.equal(importStatus(), before);
    } else {
      pending.resolve({accepted: true, error: ''}); await tick();
      if (scenario === 'completion-correlation') {
        const before = importStatus();
        for (const extra of [{operation: 'copy'}, {request_id: 'wrong'}, {review_id: 'wrong'}]) {
          assert.equal(WM.uiSetupDone(completion(pending.args, extra)), false); assert.equal(importStatus(), before);
        }
      }
      const warning = scenario === 'published-with-warning' ? 'Could not remember <selection>.' : '';
      assert.equal(WM.uiSetupDone(completion(pending.args, {selection_persisted: !warning, warning})), true);
      assert.match(importStatus(), /created.*settings_Imported/i); assert.match(importStatus(), /restart.*launcher/i);
      if (warning) assert.ok(importStatus().includes(warning));
      const done = importStatus(); assert.equal(WM.uiSetupDone(completion(pending.args, {published: false, ok: false, error: 'duplicate'})), false);
      assert.equal(importStatus(), done);
    }
  }
  assert.equal(mutations.length, 0, 'no selection or other EVE mutation endpoint');
  assert.equal(snapshots.length, 0, 'import never exports a local snapshot');
  assert.equal(WM.el('setup-back').disabled, false);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
