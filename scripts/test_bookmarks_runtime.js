#!/usr/bin/env node
'use strict';
// Real shell, Bookmark owner and markup; only bridge and DOM mechanics are doubled.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createDOM} = require('../tests/fixtures/screenshot_dom.cjs');
const markup = JSON.parse(fs.readFileSync(0, 'utf8'));
const web = path.join(__dirname, '../wingman/web');
const tests = [];
const test = (name, run) => tests.push({name, run});
const turn = () => new Promise(resolve => setImmediate(resolve));
function payload(engine = {state: 'running', last_error: '', blockers: []}) {
  return {settings: {enabled: true, windows: {'EVE - Mapper': true}, keybinds: {Sig: '^q'}},
    windows: ['EVE - Mapper'], order: ['Sig'], labels: {Sig: 'Grab Sig ID'},
    displays: {Sig: 'Ctrl+Q'}, collisions: {}, engine};
}
function page() {
  const {document, Element} = createDOM(markup);
  const window = new Element('window');
  Object.assign(window, {document, Promise, console, Math, Date, location: {search: ''},
    Event: class { constructor(type) { this.type = type; } },
    CustomEvent: class { constructor(type, options = {}) { this.type = type; this.detail = options.detail; } },
    setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {},
    requestAnimationFrame: callback => callback(), getComputedStyle: () => ({visibility: 'visible'}),
    matchMedia: () => ({matches: false})});
  window.window = window;
  const context = vm.createContext(window);
  vm.runInContext(fs.readFileSync(path.join(web, 'app.js'), 'utf8'), context);
  const WM = window.WM, calls = [];
  WM.send = (method, ...args) => new Promise(resolve => calls.push({method, args, resolve}));
  vm.runInContext(fs.readFileSync(path.join(web, 'bookmarks.js'), 'utf8'), context);
  // Initial Sig settings is a local read, not part of the action under test.
  calls.shift().resolve({enabled: false});
  return {WM, window, document, calls, el: id => WM.el(id),
    bookmarks: value => window.onBookmarks(value),
    status: value => window.onEveStatus(value),
    async reply(method, value) {
      const index = calls.findIndex(call => call.method === method);
      assert.notEqual(index, -1, method); calls.splice(index, 1)[0].resolve(value); await turn();
    }};
}
for (const source of ['bookmarks', 'status']) {
  test(source + ' paints every engine transition in the same full-content status owner', async () => {
    const p = page(); p.bookmarks(payload());
    const status = p.el('eve-engine-state');
    for (const state of ['running', 'stopped', 'stale', 'off']) {
      for (const error of ['', 'Engine unavailable. '.repeat(40)]) {
        const engine = {state, last_error: error, blockers: []};
        p[source](source === 'bookmarks' ? payload(engine) : engine);
        assert.equal(p.el('eve-engine-state'), status);
        assert.equal(status.classList.contains('pill'), state === 'running' && !error);
        assert.equal(status.classList.contains('ok'), state === 'running' && !error);
        assert.equal(status.classList.contains('err'), !!error || state === 'stopped' || state === 'stale');
        assert.equal(p.el('eve-engine-row').hidden, false, 'live owner never has a hidden ancestor');
        if (state === 'off' && !error) assert.equal(status.textContent, '');
        else assert.match(status.textContent, new RegExp({running: 'Running', stopped: 'Stopped', stale: 'Not responding', off: 'Not running'}[state]));
        if (error) assert.ok(status.textContent.includes(error), 'full recovery remains in its original owner');
      }
    }
    assert.equal(status.getAttribute('role'), 'status');
    assert.equal(p.calls.length, 0, 'status presentation adds no calls');
  });
}
test('live status writes only changed text and never writes under a hidden row', async () => {
  const p = page(); const status = p.el('eve-engine-state');
  const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(status), 'textContent');
  const writes = [];
  Object.defineProperty(status, 'textContent', {get() { return descriptor.get.call(this); }, set(value) {
    writes.push({value, hidden: p.el('eve-engine-row').hidden}); descriptor.set.call(this, value);
  }});
  p.bookmarks(payload({state: 'off', last_error: ''}));
  p.bookmarks(payload({state: 'stopped', last_error: 'Engine unavailable.'}));
  p.status({state: 'stopped', last_error: 'Engine unavailable.'});
  p.status({state: 'stopped', last_error: 'Engine unavailable.'});
  assert.ok(writes.every(write => !write.hidden), 'full live content is exposed before any update');
  assert.equal(writes.filter(write => write.value.includes('Engine unavailable.')).length, 1, 'identical polls do not rewrite live text');
});
test('an Off push with an error cannot expose stale Running text', async () => {
  const p = page(); p.bookmarks(payload());
  p.status({state: 'off', last_error: 'Engine unavailable.'});
  assert.equal(p.el('eve-engine-row').hidden, false);
  assert.equal(p.el('eve-engine-state').textContent, 'Not running — Engine unavailable.');
});
test('missing engine cannot retain a Running pill and blockers remain independently visible', async () => {
  const p = page(); p.bookmarks(payload());
  p.bookmarks(payload(null));
  assert.equal(p.el('eve-engine-state').classList.contains('pill'), false);
  assert.equal(p.el('eve-engine-row').hidden, false);
  assert.equal(p.el('eve-engine-state').textContent, '');
  p.bookmarks(payload({state: 'running', blockers: ['no_windows', 'no_binds']}));
  assert.equal(p.el('eve-blockers-row').hidden, false);
  assert.match(p.el('eve-blockers').textContent, /no EVE window.*no keybinds/);
});
test('Refresh remains exactly one local read and preserves native title identities', async () => {
  const p = page(); p.bookmarks(payload());
  p.el('eve-refresh-windows').click();
  assert.deepEqual(p.calls.map(call => call.method), ['get_bookmarks']);
  const state = payload(); state.windows = []; await p.reply('get_bookmarks', state);
  assert.match(p.el('eve-windows').textContent, /Mapper.*not running/);
  assert.equal(p.el('eve-windows').querySelector('label').title, 'EVE - Mapper');
});
test('SIG retains shared push-owned choice, tooltip, accessible name and pressed state', async () => {
  const p = page(); await turn(); const btn = p.el('btn-sigbar');
  assert.equal(btn.textContent.trim(), 'SIG');
  assert.equal(btn.title, 'Floating sig bar');
  assert.equal(btn.getAttribute('aria-label'), 'Floating sig bar');
  btn.click();
  assert.deepEqual(p.calls.map(call => [call.method, ...call.args]), [['toggle_sig_bar', true]]);
  assert.equal(btn.classList.contains('active'), false, 'no optimistic repaint');
  p.window.onSigBarState({enabled: true});
  assert.equal(btn.getAttribute('aria-pressed'), 'true');
  assert.equal(p.el('sigbar-enabled').checked, true);
  p.window.onSigBarState({enabled: false});
  assert.equal(btn.getAttribute('aria-pressed'), 'false');
  assert.equal(btn.classList.contains('active'), false);
});
for (const leave of ['section', 'route']) {
  test(leave + ' leave disarms capture and revokes a late key response', async () => {
    const p = page();
    p.WM.openSettingsSection('bookmarks'); await p.reply('get_bookmarks', payload());
    const btn = p.el('eve-binds').querySelector('.bindbtn'); btn.click();
    p.document.dispatchEvent({type: 'keydown', key: 'x', code: 'KeyX', ctrlKey: true});
    assert.equal(p.calls[0].method, 'capture_bind');
    if (leave === 'route') p.WM.route('uploader'); else p.WM.section('general');
    await p.reply('capture_bind', {ahk: '^x'});
    p.document.dispatchEvent({type: 'keydown', key: 'y', code: 'KeyY'});
    assert.equal(p.calls.length, 0, 'hidden capture cannot save or capture another key');
    assert.equal(p.el('eve-binds').querySelector('.capturing'), null);
  });
}
(async () => {
  let failed = 0;
  for (const t of tests) {
    try { await t.run(); console.log('ok ' + t.name); }
    catch (error) { failed++; console.error('FAIL ' + t.name + '\n' + error.stack); }
  }
  console.log((tests.length - failed) + ' passed, ' + failed + ' failed');
  process.exitCode = failed ? 1 : 0;
})();
