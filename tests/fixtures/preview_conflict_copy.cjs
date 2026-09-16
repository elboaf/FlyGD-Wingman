// Execute the real renderer. DOM/bridge doubles do not prove native registration.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createDOM} = require('./screenshot_dom.cjs');
const {document, Element} = createDOM(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
const web = process.argv[3];
const window = new Element('window');
Object.assign(window, {window, document, console, Promise, setTimeout, clearTimeout,
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }});
const runtime = vm.createContext(window);
vm.runInContext(fs.readFileSync(web + '/app.js', 'utf8'), runtime);
const calls = [];
window.WM.send = (method, ...args) => {
  calls.push([method, ...args]);
  assert.ok(['get_preview_hotkey_state', 'get_preview_crop_state', 'sig_bar_settings'].includes(method), method);
  return Promise.resolve(null);
};
vm.runInContext(fs.readFileSync(web + '/previews.js', 'utf8'), runtime);
const gesture = 'Ctrl+Alt+1';
function render(hotkeys = {}, extra = {}) {
  window.onPreviewHotkeys({
    enabled: true, hotkeys: {characters: {}, groups: [], ...hotkeys},
    roster: ['Alice', 'Bravo'], characters: ['Alice'], registration: {[gesture]: true},
    bookmark_chords: {active: [], latent: []}, locked: [], lock_default: false,
    never_minimize: [], excluded: [], sizes: {}, client_sizes: {}, layout_sources: [], sizable: [],
    crops: {revision: 1, definitions: {}, operations: {}, statuses: {}}, ...extra
  });
}
function warning(owner) {
  return document.getElementById('preview-bind-conflict-' + encodeURIComponent(owner));
}
function message(owner) {
  const node = warning(owner);
  assert.ok(node, 'missing warning for ' + owner);
  assert.equal(node.parentNode.querySelector('.bindbtn').getAttribute('aria-describedby'), node.id);
  assert.match(node.textContent, /Edit or clear one of these keybinds/);
  return node.textContent;
}
(async () => {
  await new Promise(resolve => setImmediate(resolve));
  calls.length = 0;
  // Bookmark overlap is configuration evidence, not proof of hook/runtime state.
  render({characters: {Alice: gesture}}, {bookmark_chords: {active: [gesture], latent: []}});
  assert.match(message('character:Alice'), /configured EVE bookmark keybind/);
  assert.match(message('character:Alice'), /bookmark may take this keybind in its selected EVE windows/);
  assert.match(message('character:Alice'), /use different keys/);
  assert.doesNotMatch(message('character:Alice'), /preview.*takes priority|bookmark will not fire/i);
  // Neither an enabled preference nor a missing registration report proves operation.
  render({characters: {Alice: gesture}}, {enabled: false, registration: {}, bookmark_chords: {active: [gesture], latent: []}});
  assert.match(message('character:Alice'), /bookmark may take this keybind/);
  // Character focus always precedes any cycle in host.plan_registrations.
  render({characters: {Alice: gesture, Bravo: gesture},
    groups: [{id: 'g1', name: 'Fleet', cycle: gesture}]});
  for (const owner of ['character:Alice', 'character:Bravo', 'group:g1']) {
    assert.match(message(owner), /Character focus takes priority; this keybind will not cycle/);
  }
  assert.match(message('group:g1'), /conflicts with Alice, Bravo/);
  render({characters: {Bravo: gesture},
    groups: [{id: 'g1', name: 'Fleet', cycle: gesture}]});
  assert.match(message('group:g1'), /Character focus takes priority; this keybind will not cycle/,
    'a non-excluded offline focus owner still precedes cycling');
  // Forward beats back within a group; stored order breaks group-vs-group ties.
  render({groups: [{id: 'g1', name: 'Fleet', cycle: gesture},
    {id: 'g2', name: 'Backup', cycle_prev: gesture}]});
  assert.match(message('group-prev:g2'), /cycle group Fleet forward takes priority; the other cycle actions will not run/);
  assert.equal(warning('group-prev:g2').parentNode.querySelector('.bindbtn').title, message('group-prev:g2'),
    'the tooltip must not contradict which cycle action wins');
  render({groups: [{id: 'g2', name: 'Second', cycle: gesture}, {id: 'g1', name: 'First', cycle: gesture}]});
  assert.match(message('group:g1'), /cycle group Second forward takes priority/);
  // Same displayed label is not the same owner.
  render({groups: [{id: 'g1', name: 'Fleet', cycle: gesture}, {id: 'g2', name: 'Second', cycle: gesture}]});
  assert.match(message('group:g2'), /conflicts with cycle group Fleet forward/);
  // Supported character sharing must not acquire a new conflict or lose its help.
  render({characters: {Alice: gesture, Bravo: gesture}});
  assert.equal(warning('character:Alice'), null);
  assert.equal(warning('character:Bravo'), null);
  assert.match(document.querySelector('[data-preview-configure="Alice"]').parentNode.querySelector('.bindbtn').title, /Shared with Bravo/);
  // Existing exclusion, latent, and refused-registration guards stay authoritative.
  render({characters: {Alice: gesture},
    groups: [{id: 'g1', name: 'Fleet', cycle: gesture}]}, {excluded: ['Alice']});
  assert.equal(warning('character:Alice'), null);
  assert.equal(warning('group:g1'), null);
  render({characters: {Alice: gesture}}, {bookmark_chords: {active: [], latent: [gesture]}});
  assert.equal(warning('character:Alice'), null);
  render({characters: {Alice: gesture}}, {registration: {[gesture]: false}, bookmark_chords: {active: [gesture], latent: []}});
  assert.match(warning('character:Alice').textContent, /already owned by another application/);
  assert.doesNotMatch(warning('character:Alice').textContent, /bookmark will not fire/);
  render({characters: {Alice: gesture}});
  assert.equal(warning('character:Alice'), null, 'resolved conflict retires the warning');
  assert.equal(calls.length, 0, 'consequence rendering performs no bridge operations');
  vm.runInContext(fs.readFileSync(web + '/bookmarks.js', 'utf8'), runtime);
  await new Promise(resolve => setImmediate(resolve));
  calls.length = 0; // Bookmarks hydrates its separate sig-bar preference at boot.
  for (const kind of ['active', 'latent']) {
    window.onBookmarks({settings: {enabled: true, windows: {}, keybinds: {GrabSig: '^!1'}},
      engine: {state: 'off', last_error: '', blockers: []}, windows: [], collisions: {}, groups: [],
      order: ['GrabSig'], labels: {GrabSig: 'Grab Sig ID'}, displays: {GrabSig: gesture},
      preview_chords: {active: [], latent: [], [kind]: [gesture]}});
    const bind = document.getElementById('eve-binds').querySelector('.bindbtn');
    assert.equal(bind.classList.contains(kind === 'active' ? 'clash' : 'dim'), true);
    assert.match(bind.title, /bookmark may take the key.*selected EVE windows/i);
    assert.match(bind.title, /Edit or clear.*use different keys/);
    assert.doesNotMatch(bind.title, /bookmark does not fire|take the key from this bookmark/i);
  }
  assert.equal(calls.length, 0, 'Bookmark rendering also stays local');
  console.log('PASS preview conflict consequences');
})().catch(error => { console.error(error); process.exitCode = 1; });
