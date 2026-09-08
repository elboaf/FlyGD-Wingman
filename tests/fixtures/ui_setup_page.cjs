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
function deferred(args) {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {args, promise, resolve, reject};
}
const navigator = {clipboard: {writeText: text => {
  if (scenario === 'copy-throws') throw new Error('Clipboard unavailable');
  const write = deferred([text]); clipboardWrites.push(write); return write.promise;
}}};
if (scenario === 'copy-unavailable') delete navigator.clipboard;
const WM = {
  current_route: 'evesettings',
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
      eve_settings_setup_export: snapshots, eve_settings_setup_save_file: saves};
    if (!destinations[method]) { mutations.push({method, args}); assert.fail('Unexpected/mutation call: ' + method); }
    destinations[method].push(request); return request.promise;
  }
};
assert.ok(ids['route-uisetup'], 'Missing production setup route');
assert.ok(fs.existsSync(process.argv[4]), 'Missing production setup module');
vm.runInNewContext(fs.readFileSync(process.argv[4], 'utf8'), {
  WM, document, window: {}, navigator, console, Promise
}, {filename: process.argv[4]});
const tick = () => new Promise(resolve => setImmediate(resolve));
const click = id => WM.el(id).click();
function change(id, value) { WM.el(id).value = value; WM.el(id).dispatchEvent({type: 'change'}); }
const status = () => WM.el('us-status').textContent;
const plain = value => JSON.parse(JSON.stringify(value));
function context(profile = 'profile-A') {
  return {ok: true, error: '', root: 'root', server: 'server', profile,
    profiles: [{path: 'profile-A', name: 'Base A', file_count: 4}, {path: 'profile-B', name: 'Base B', file_count: 4}],
    accounts: [
      {path: 'account-A', id: '10', name: 'Account <A>', display_name: 'Account <A>', display_meta: '', account_name: 'Account A', character_ids: ['11']},
      {path: 'account-B', id: '20', name: 'Account B', display_name: 'Account B', display_meta: '', account_name: 'Account B', character_ids: ['21']}
    ],
    characters: [
      {path: 'char-A', id: '11', name: 'Pilote é 𐐀 <img>', display_name: 'Pilote é 𐐀 <img>', display_meta: ''},
      {path: 'char-B', id: '21', name: 'Pilot B', display_name: 'Pilot B', display_meta: ''}
    ], account_identity_available: true, setup_available: true};
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
    'sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode("utf-8"))'
  ].join('\n');
  const result = spawnSync(process.argv[5], ['-c', script], {input: JSON.stringify([kind, text]), encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr); return JSON.parse(result.stdout);
}
const exported = python('export');
async function open(data = context(), mode = 'export') {
  const opener = {mode, context: data, preferred_character: 'char-A'};
  WM.openUiSetup(opener);
  if (mode !== 'export') return;
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
  assert.equal(WM.el('us-copy').disabled, true);
  assert.equal(WM.el('us-save').disabled, true);
  if (scenario === 'import-unavailable') {
    await open(context(), 'import');
    assert.match(status(), /import.*not available/i); assert.equal(snapshots.length, 0);
    assert.equal(WM.el('us-copy').disabled, true); click('us-back');
    assert.equal(WM.current_route, 'evesettings');
  } else if (scenario === 'context-failure') {
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
main().catch(error => { console.error(error); process.exitCode = 1; });
