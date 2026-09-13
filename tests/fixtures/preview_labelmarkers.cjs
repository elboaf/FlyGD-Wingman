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
const window = new Element('window');
Object.assign(window, {window, document, console, Promise, setTimeout, clearTimeout,
  getComputedStyle: () => ({visibility: 'visible'}),
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }});
const context = vm.createContext(window);
vm.runInContext(fs.readFileSync(web + '/app.js', 'utf8'), context);
const calls = [], getters = [], writes = [];
window.WM.send = (method, ...args) => {
  calls.push([method, ...args]);
  if (method === 'get_preview_hotkey_state') return new Promise(resolve => getters.push(resolve));
  if (method === 'set_preview_character_marker') return new Promise((resolve, reject) => writes.push({name: args[0], marker: args[1], resolve, reject}));
  if (method === 'set_bind_capture') return Promise.resolve(true);
  if (method === 'get_preview_crop_state') return Promise.resolve(null);
  throw new Error('Unexpected bridge call ' + method);
};
vm.runInContext(fs.readFileSync(web + '/previews.js', 'utf8'), context);
if (data.scenario === 'copy') vm.runInContext(fs.readFileSync(web + '/panel.js', 'utf8'), context);
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
