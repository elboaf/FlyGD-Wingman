// Real modules with deferred bridge boundaries; no browser/native acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createDOM} = require('./screenshot_dom.cjs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const {document, Element} = createDOM(data.page);
// Match the browser's focus loss when a render removes the focused subtree.
let active = document.body;
Object.defineProperty(document, 'activeElement', {
  get: () => document.contains(active) ? active : document.body,
  set: value => { active = value; }
});
Element.prototype.hasAttribute = function (name) { return this.getAttribute(name) !== null; };
Element.prototype.setSelectionRange = function (start, end, direction = 'none') {
  this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction;
};
const window = new Element('window');
Object.assign(window, {window, document, console, Promise, setTimeout, clearTimeout,
  getComputedStyle: () => ({visibility: 'visible'}),
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }});
const context = vm.createContext(window);
vm.runInContext(fs.readFileSync(web + '/app.js', 'utf8'), context);
const calls = [], getters = [], writes = [], arms = [];
window.WM.send = (method, ...args) => {
  calls.push([method, ...args]);
  if (method === 'get_preview_hotkey_state') return new Promise(resolve => getters.push(resolve));
  if (method === 'set_preview_character_marker') return new Promise((resolve, reject) => writes.push({name: args[0], marker: args[1], resolve, reject}));
  if (method === 'set_bind_capture') {
    if (args[0] && data.scenario === 'capture-entry-before-arm') return new Promise(resolve => arms.push(resolve));
    return Promise.resolve(true);
  }
  if (method === 'capture_preview_bind') return Promise.resolve({gesture: 'Alt+Down', error: null});
  if (method === 'set_preview_binds') return Promise.resolve(true);
  if (method === 'get_preview_crop_state') return Promise.resolve(null);
  throw new Error('Unexpected bridge call ' + method);
};
vm.runInContext(fs.readFileSync(web + '/previews.js', 'utf8'), context);
if (['copy', 'reset-copy'].includes(data.scenario)) vm.runInContext(fs.readFileSync(web + '/panel.js', 'utf8'), context);
const tick = () => new Promise(resolve => setImmediate(resolve));
const clone = value => JSON.parse(JSON.stringify(value));
function payload(markers = {}) {
  return {enabled: true, characters: ['Alice'], roster: ['Alice', 'Bob'],
    hotkeys: {characters: {}, cycle_next: '', cycle_prev: '', groups: [], group_by_character: {}},
    label_markers: markers, marker_choices: data.choices, registration: {},
    bookmark_chords: {active: [], latent: []}, locked: [], excluded: [], never_minimize: [],
    sizes: {}, client_sizes: {}, sizable: [], layout_sources: [],
    crops: {revision: 1, definitions: {}, operations: {}, statuses: {}, cap: 8, live_count: 0, runtime_enabled: true}};
}
const configure = name => Array.from(document.querySelectorAll('[data-preview-configure]')).find(el => el.getAttribute('data-preview-configure') === name);
function open(name) { const button = configure(name); assert.ok(button, 'owner row ' + name); if (button.getAttribute('aria-expanded') !== 'true') button.click(); }
const select = () => document.querySelector('[data-preview-detail-control="marker"]');
function field(name) { open(name); assert.ok(select(), 'Identification marker select in Configure'); return select(); }
function change(name, value) { const el = field(name); el.focus(); el.value = value; el.dispatchEvent({type: 'change'}); return el; }
const error = () => document.getElementById(select().getAttribute('aria-describedby')).textContent;
const ok = marker => ({applied: true, persisted: true, error: null, marker});
function push(value) { window.onPreviewHotkeys(clone(value)); }
function section(name) { document.dispatchEvent({type: 'wm:section', detail: name}); }
function tab(name) { document.dispatchEvent({type: 'wm:settings-tab', detail: {section: 'previews', tab: name}}); }
(async () => {
  assert.equal(writes.length, 0);
  assert.equal(select(), null);
  getters.shift()(payload()); await tick();
  const initial = field('Alice');
  assert.equal(initial.tagName, 'SELECT');
  assert.equal(initial.getAttribute('aria-label'), 'Identification marker for Alice');
  assert.deepEqual(initial.options.map(el => ({key: el.value, label: el.textContent})), data.choices);
  assert.equal(document.querySelectorAll('[data-preview-detail-control="marker"]').length, 1);
  assert.equal(configure('Alice').parentNode.children.length, 5, 'no collapsed column');
  assert.equal(initial.disabled, false);
  assert.equal(writes.length, 0, 'hydration is not a submission');
  const scenario = data.scenario;
  if (scenario === 'hydration') {
    const off = payload({'Offline only': 'green'}); off.enabled = false; off.characters = []; off.excluded = ['Bob'];
    push(off); document.dispatchEvent({type: 'wm:settings', detail: {settings: {preview: {show_labels: false}}}});
    assert.equal(field('Bob').disabled, false);
    assert.equal(field('Offline only').value, 'green');
    assert.equal(writes.length, 0);
  } else if (scenario === 'receipts') {
    const stale = payload();
    change('Alice', 'cyan'); assert.equal(select().disabled, true);
    change('Alice', 'blue'); assert.equal(writes.length, 1, 'same-owner writes serialize');
    push(stale); assert.equal(field('Alice').value, '', 'no assignment before ack');
    writes[0].resolve(ok('cyan')); await tick();
    push(stale); assert.equal(field('Alice').value, 'cyan', 'stale push cannot erase ack');
    change('Alice', ''); writes[1].resolve(ok('')); await tick();
    push(payload({Alice: 'cyan'})); assert.equal(field('Alice').value, '', 'reset tombstone');
    for (const receipt of [null, {applied: false, persisted: false, error: 'Disk refused', marker: 'blue'}, ok(null), ok('bogus')]) {
      change('Alice', 'orange'); writes.at(-1).resolve(receipt); await tick();
      assert.equal(select().value, ''); assert.ok(error()); assert.equal(select().disabled, false);
    }
    change('Alice', 'green'); writes.at(-1).reject(new Error('bridge gone')); await tick();
    assert.equal(select().value, ''); assert.ok(error());
  } else if (scenario === 'owners') {
    push(payload(JSON.parse('{"constructor":"blue","__proto__":"purple"}')));
    for (const [name, value] of [['constructor', 'blue'], ['__proto__', 'purple']]) assert.equal(field(name).value, value);
    change('constructor', 'orange'); change('__proto__', 'yellow');
    assert.deepEqual(writes.map(w => w.name), ['constructor', '__proto__']);
    writes[0].resolve({applied: false, persisted: false, error: 'Constructor refused', marker: 'blue'});
    writes[1].resolve(ok('yellow')); await tick();
    assert.equal(field('__proto__').value, 'yellow');
    assert.equal(field('constructor').value, 'blue'); assert.match(error(), /Constructor refused/);
    change('__proto__', ''); writes[2].resolve(ok('')); await tick();
    assert.match((field('constructor'), error()), /Constructor refused/);
    change('constructor', 'green'); writes[3].resolve(ok('green')); await tick(); assert.equal(error(), '');
  } else if (scenario === 'retention') {
    const markers = Object.fromEntries(Array.from({length: 70}, (_, i) => ['Pilot' + i, 'cyan']));
    const p = payload(markers); p.roster = Array.from({length: 64}, (_, i) => 'Recent' + i); p.characters = [];
    push(p); assert.equal(document.querySelectorAll('[data-preview-configure]').length, 134);
    change('Pilot69', ''); writes[0].resolve(ok('')); await tick();
    assert.equal(configure('Pilot69'), undefined, 'reset-only owner ceases to source a row');
    assert.equal(document.activeElement.id, 'preview-roster-heading');
    push(p); assert.equal(configure('Pilot69'), undefined, 'tombstone blocks stale resurrection without sourcing empty row');
    assert.ok(configure('Pilot68'));
  } else if (scenario === 'refresh') {
    change('Alice', 'cyan'); writes[0].resolve(null); await tick();
    assert.equal(select().value, '');
    section('previews'); getters.shift()(payload({Alice: 'cyan'})); await tick();
    assert.equal(field('Alice').value, 'cyan', 'fresh getter recovers lost receipt');
    section('previews'); const older = getters.shift();
    change('Alice', 'orange'); writes[1].resolve(ok('orange')); await tick();
    older(payload({Alice: 'cyan'})); await tick();
    assert.equal(field('Alice').value, 'orange', 'older getter cannot overwrite newer submission');
    section('previews'); const inFlight = getters.shift();
    change('Alice', 'blue'); inFlight(payload({Alice: 'yellow'})); await tick();
    writes[2].resolve({applied: false, persisted: false, error: 'No', marker: 'orange'}); await tick();
    assert.equal(select().value, 'orange');
    assert.equal(calls.filter(c => c[0] === 'get_preview_hotkey_state').length, 4, 'no extra reads');
  } else if (scenario === 'navigation') {
    const bind = configure('Alice').parentNode.querySelector('.bindbtn'); bind.focus(); bind.click(); await tick();
    assert.ok(bind.classList.contains('capturing'));
    open('Bob'); assert.ok(!bind.classList.contains('capturing'));
    change('Bob', 'cyan'); const alice = field('Alice'); alice.focus();
    writes[0].resolve(ok('cyan')); await tick();
    assert.equal(document.activeElement, select(), 'other owner receipt preserves current detail control focus');
    assert.equal(select().getAttribute('aria-label'), 'Identification marker for Alice');
    const focused = select(); focused.focus();
    const crop = payload().crops; crop.revision = 2; crop.definitions = {'Crop only': {enabled: false}};
    window.onPreviewCrops(crop); assert.equal(document.activeElement, select(), 'crop roster rebuild preserves marker focus');
    change('Alice', 'green'); tab('windows');
    const destination = document.getElementById('preview-enabled'); destination.focus();
    writes[1].resolve(ok('green')); await tick(); assert.equal(document.activeElement, destination);
    change('Bob', 'orange'); section('general'); destination.focus();
    writes[2].resolve(ok('orange')); await tick(); assert.equal(document.activeElement, destination);
    const count = calls.length; document.dispatchEvent({type: 'keydown', key: 'x', code: 'KeyX'});
    assert.equal(calls.length, count, 'capture stays disarmed');
  } else if (scenario === 'copy') {
    const p = payload(); p.layout_sources = [{name: 'Source', online: false}]; push(p);
    change('Alice', 'cyan');
    const copy = document.querySelector('[data-preview-detail-control="copy"]');
    assert.ok(copy); copy.focus(); copy.click(); await tick();
    assert.equal(document.getElementById('overlay').hidden, false);
    const modalFocus = document.activeElement;
    writes[0].resolve(ok('cyan')); await tick();
    assert.equal(document.activeElement, modalFocus, 'receipt cannot steal modal focus');
    document.dispatchEvent({type: 'keydown', key: 'Escape'}); await tick();
    assert.equal(document.getElementById('overlay').hidden, true);
    assert.equal(document.activeElement, copy, 'Copy Escape retains its attached invoker');
    assert.equal(writes.length, 1);
  } else if (scenario === 'reset-copy') {
    const p = payload({Retired: 'cyan'}); p.layout_sources = [{name: 'Source', online: false}]; push(p);
    change('Retired', '');
    open('Alice');
    const copy = document.querySelector('[data-preview-detail-control="copy"]');
    assert.ok(copy); copy.focus(); copy.click(); await tick();
    const modalFocus = document.activeElement;
    writes[0].resolve(ok('')); await tick();
    assert.equal(configure('Retired'), undefined, 'reset-only row is removed');
    assert.ok(document.activeElement === modalFocus, 'unrelated chooser keeps modal focus');
    assert.ok(document.contains(copy), 'marker-only reset must retain the original unrelated Copy invoker');
    document.dispatchEvent({type: 'keydown', key: 'Escape'}); await tick();
    assert.equal(document.getElementById('overlay').hidden, true);
    assert.ok(document.activeElement === copy, 'Escape returns to the original attached Copy control');
    assert.equal(writes.length, 1);
  } else if (scenario === 'reset-draft') {
    push(payload({Retired: 'cyan'}));
    change('Retired', '');
    const manager = document.querySelector('.preview-group-manager');
    manager.open = true; manager.dispatchEvent({type: 'toggle'});
    const draft = document.querySelector('.group-add-name');
    draft.value = 'Fleet support'; draft.focus(); draft.setSelectionRange(2, 9, 'backward');
    writes[0].resolve(ok('')); await tick();
    assert.equal(configure('Retired'), undefined, 'reset-only row is removed');
    const surviving = document.querySelector('.group-add-name');
    assert.equal(surviving.value, 'Fleet support', 'marker-only reset must not erase an unsent group draft');
    assert.deepEqual([surviving.selectionStart, surviving.selectionEnd, surviving.selectionDirection], [2, 9, 'backward']);
    assert.ok(document.activeElement === draft && surviving === draft, 'original draft retains focus and attachment');
    assert.equal(manager.open, true);
    assert.equal(calls.filter(c => c[0] === 'create_preview_cycle_group').length, 0);
  } else if (scenario === 'reset-headings' || scenario === 'reset-headings-off') {
    const enabled = scenario === 'reset-headings';
    const p = payload({Retired: 'cyan'}); p.enabled = enabled; p.characters = enabled ? ['Alice'] : []; p.roster = ['Alice'];
    p.locked = ['Retired']; p.never_minimize = ['Retired']; push(p);
    document.dispatchEvent({type: 'wm:settings', detail: {settings: {preview: {minimize_inactive_clients: true}}}});
    const offline = () => document.querySelectorAll('.bind-group-name').filter(el => el.textContent === 'Offline');
    assert.equal(offline().length, enabled ? 1 : 0);
    change('Retired', '');
    const alice = configure('Alice');
    const lock = document.querySelector('[data-preview-lock="Alice"]'); lock.focus();
    const nm = document.getElementById('preview-nm-exceptions-list').querySelectorAll('label').find(el => el.textContent === 'Alice');
    writes[0].resolve(ok('')); await tick();
    assert.equal(configure('Retired'), undefined);
    assert.equal(offline().length, 0, 'last offline owner removes its heading');
    assert.ok(configure('Alice') === alice && document.contains(alice), 'surviving row is not rebuilt');
    assert.ok(document.activeElement === lock && document.contains(lock), 'surviving exception checkbox keeps focus');
    assert.ok(document.contains(nm), 'surviving Never minimize control is retained');
    for (const id of ['preview-lock-exceptions-list', 'preview-nm-exceptions-list']) {
      assert.equal(document.getElementById(id).textContent.includes('Retired'), false, 'vanished exception row is removed');
    }
    assert.equal(document.getElementById('preview-lock-exceptions-summary').textContent, 'Lock individual characters');
    assert.equal(document.getElementById('preview-nm-exceptions-summary').textContent, 'Exempt individual characters');
    assert.ok(document.querySelector('.bind-head'));
    assert.equal(document.getElementById('preview-binds-empty').hidden, true);
    assert.equal(document.getElementById('preview-copy-empty').hidden, false);
    const last = payload({Final: 'blue'}); last.enabled = enabled; last.characters = []; last.roster = []; push(last);
    change('Final', ''); writes[1].resolve(ok('')); await tick();
    assert.equal(configure('Final'), undefined);
    assert.equal(document.querySelector('.bind-head'), null, 'no character header with an empty roster');
    assert.equal(document.getElementById('preview-binds').querySelectorAll('.bind-group').length, 0, 'no orphan divider/offline heading');
    assert.equal(document.getElementById('preview-binds-empty').hidden, false);
    assert.equal(document.getElementById('preview-copy-empty').hidden, true);
    assert.equal(document.activeElement.id, 'preview-binds-empty');
    for (const id of ['preview-lock-exceptions', 'preview-nm-exceptions']) {
      assert.equal(document.getElementById(id).hidden, true);
      assert.equal(document.getElementById(id + '-list').children.length, 0);
    }
  } else if (scenario === 'reset-capture' || scenario === 'reset-owner-capture') {
    push(payload({Retired: 'cyan'})); change('Retired', '');
    const removedOwner = scenario === 'reset-owner-capture';
    const bind = configure(removedOwner ? 'Retired' : 'Alice').parentNode.querySelector('.bindbtn');
    bind.focus(); bind.click(); await tick();
    assert.ok(bind.classList.contains('capturing'));
    writes[0].resolve(ok('')); await tick();
    assert.ok(!configure('Retired'), 'reset does not defer a fake row behind capture');
    if (removedOwner) {
      assert.ok(!document.contains(bind) && !bind.classList.contains('capturing'));
      assert.deepEqual(calls.filter(c => c[0] === 'set_bind_capture').at(-1), ['set_bind_capture', false]);
      const count = calls.length; document.dispatchEvent({type: 'keydown', key: 'x', code: 'KeyX'});
      assert.equal(calls.length, count, 'vanished owner cannot keep a detached capture session');
    } else {
      assert.ok(document.contains(bind) && document.activeElement === bind && bind.classList.contains('capturing'));
      document.dispatchEvent({type: 'keydown', key: 'Escape'}); await tick();
      assert.ok(!bind.classList.contains('capturing') && document.contains(bind));
    }
  } else if (scenario.startsWith('capture-entry-')) {
    const beforeArm = scenario === 'capture-entry-before-arm';
    const deferred = beforeArm || scenario.endsWith('-deferred');
    const bind = configure('Alice').parentNode.querySelector('.bindbtn');
    bind.focus(); bind.click(); await tick();
    assert.equal(bind.classList.contains('capturing'), !beforeArm);
    const target = select();
    if (deferred) {
      const p = payload(); p.roster.push('New pilot'); push(p);
      assert.equal(configure('New pilot'), undefined, 'live roster paint waits behind capture');
    }
    const entry = scenario.includes('-pointer') ? 'mousedown' : 'focusin';
    if (entry === 'focusin') target.focus();
    target.dispatchEvent({type: entry});
    assert.deepEqual(calls.filter(c => c[0] === 'set_bind_capture').at(-1), ['set_bind_capture', false], 'marker entry must disarm before any marker key');
    assert.equal(select(), target, 'the first native select gesture keeps its original attached target');
    assert.ok(document.contains(target));
    if (entry === 'focusin') assert.equal(document.activeElement, target);
    if (deferred) assert.ok(configure('New pilot'), 'deferred live roster paint is flushed');
    if (beforeArm) { arms.shift()(true); await tick(); }
    assert.equal(document.querySelector('.capturing'), null, 'late native arm receipt cannot rearm');
    target.focus();
    const key = () => {
      let prevented = false;
      document.dispatchEvent({type: 'keydown', key: 'ArrowDown', code: 'ArrowDown', altKey: true,
        preventDefault() { prevented = true; }});
      assert.equal(prevented, false, 'marker keys retain their native default action');
    };
    key();
    change('Alice', 'cyan'); assert.equal(select().disabled, true);
    key(); writes[0].resolve(ok('cyan')); await tick(); key();
    assert.equal(select().value, 'cyan');
    change('Alice', 'purple');
    writes[1].resolve({applied: false, persisted: false, error: 'Disk refused', marker: 'cyan'}); await tick(); key();
    assert.equal(select().value, 'cyan'); assert.match(error(), /Disk refused/);
    window.onPreviewBindCaptured({gesture: 'Alt+Down'}); await tick();
    assert.equal(calls.filter(c => ['capture_preview_bind', 'set_preview_binds'].includes(c[0])).length, 0, 'marker keyboard/native delivery must not save an unrelated binding');
    change('Alice', 'green');
    const bob = configure('Bob').parentNode.querySelector('.bindbtn');
    bob.focus(); bob.click(); await tick();
    if (beforeArm) { arms.shift()(true); await tick(); }
    const disarms = calls.filter(c => c[0] === 'set_bind_capture' && !c[1]).length;
    writes[2].resolve(ok('green')); await tick();
    assert.equal(calls.filter(c => c[0] === 'set_bind_capture' && !c[1]).length, disarms, 'earlier marker receipt does not disarm later Bob capture');
    assert.ok(document.contains(bob) && bob.classList.contains('capturing') && document.activeElement === bob);
    document.dispatchEvent({type: 'keydown', key: 'Escape'}); await tick();
  } else if (scenario === 'screenshot-deferred') {
    change('Alice', 'cyan'); writes[0].resolve(ok('cyan')); await tick();
    const bind = configure('Alice').parentNode.querySelector('.bindbtn');
    bind.focus(); bind.click(); await tick();
    const p = payload({Alice: 'cyan'}); p.roster.push('New pilot'); push(p);
    assert.equal(configure('New pilot'), undefined);
    const fixture = payload({Alice: 'purple'});
    fixture.crops.definitions = {Alice: {enabled: false}};
    window.WM.previewCropScreenshot({kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: fixture, crops: fixture.crops});
    assert.equal(field('Alice').value, 'purple', 'deferred live paint must finish before screenshot marker isolation');
    change('Alice', 'green'); assert.equal(writes.length, 1, 'fixture never sends real marker writes');
    window.WM.previewCropScreenshot(null);
    assert.equal(field('Alice').value, 'cyan', 'accepted live field survives fixture exit');
    assert.ok(configure('New pilot'), 'snapshot retains deferred live roster');
    assert.equal(calls.filter(c => ['capture_preview_bind', 'set_preview_binds'].includes(c[0])).length, 0);
  } else if (scenario === 'screenshot') {
    change('Alice', 'cyan'); writes[0].resolve(ok('cyan')); await tick();
    change('Bob', 'orange');
    const fixture = payload({Alice: 'purple', Bob: 'yellow'});
    fixture.crops.definitions = {Alice: {enabled: false}};
    window.WM.previewCropScreenshot({kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: fixture, crops: fixture.crops});
    assert.equal(field('Alice').value, 'purple', 'fixture owns separate fake baseline');
    change('Alice', 'green'); assert.equal(writes.length, 2, 'fixture never sends real setter');
    push(payload({Alice: 'blue'})); // stale live push buffered while fixture is installed
    writes[1].resolve(ok('orange')); await tick();
    assert.equal(field('Bob').value, 'yellow', 'real receipt cannot rewrite fake owner');
    window.WM.previewCropScreenshot(null);
    assert.equal(field('Alice').value, 'cyan', 'fixture cannot contaminate accepted live baseline');
    assert.equal(field('Bob').value, 'orange', 'delayed receipt retains live owner');
    change('Bob', 'green');
    window.WM.previewCropScreenshot({kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: fixture, crops: fixture.crops});
    window.WM.previewCropScreenshot(null);
    writes[2].resolve(ok('green')); await tick(); assert.equal(field('Bob').value, 'green');
  } else throw new Error('Unknown scenario ' + scenario);
  console.log('PASS marker page ' + scenario);
})().catch(error => { console.error(error); process.exitCode = 1; });
