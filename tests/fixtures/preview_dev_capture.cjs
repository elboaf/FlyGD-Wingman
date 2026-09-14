// Real dev driver + production capture consumer, no fabricated capture transport.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createDOM} = require('./screenshot_dom.cjs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const {document, Element} = createDOM(data.page);
Element.prototype.hasAttribute = function(name) { return this.getAttribute(name) !== null; };
const window = new Element('window');
Object.assign(window, {window, document, console, Promise, URLSearchParams, location: {search: '?dev=1'},
  setTimeout: () => 1, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {},
  getComputedStyle: () => ({visibility: 'visible'}),
  Event: class { constructor(type) { this.type = type; } },
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }});
const context = vm.createContext(window);
for (const script of ['app.js', 'previews.js', 'fleetsharing.js', 'panel.js', 'dev.js']) {
  vm.runInContext(fs.readFileSync(web + '/' + script, 'utf8'), context);
}
const tick = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  const api = window.pywebview.api;
  const initial = await api.get_preview_hotkey_state();
  window.onPreviewHotkeys(initial);
  const names = initial.characters.filter(name => !initial.excluded.includes(name));
  const [a, b] = names;
  const bind = name => [...document.querySelectorAll('#preview-binds .lab')].find(el => el.title === name).parentNode.querySelector('.bindbtn');
  const events = [];
  const consume = window.onPreviewBindCaptured;
  window.onPreviewBindCaptured = payload => { events.push(payload); consume(payload); };
  const arms = [];
  const arm = api.set_bind_capture;
  api.set_bind_capture = (...args) => { arms.push(args); return arm(...args); };
  bind(a).click(); await tick();
  const sessionA = arms.at(-1)[1];
  window.DEV.previewBindCaptured(); await tick();
  assert.equal(events[0].session, sessionA, 'dev helper emits its armed page session');
  assert.equal((await api.get_preview_hotkey_state()).hotkeys.characters[a], 'Ctrl+Alt+F9');
  const count = events.length;
  window.DEV.previewBindCaptured(); assert.equal(events.length, count, 'native consume immediately disarms dev capture');
  bind(a).click(); await tick();
  const retired = arms.at(-1)[1]; window.WM.endPreviewCapture(); await tick();
  window.DEV.previewBindCaptured(); assert.equal(events.length, count, 'explicit disarm suppresses delivery');
  bind(b).click(); await tick();
  const sessionB = arms.at(-1)[1];
  await arm(true, retired); await arm(false, retired); await arm(false);
  consume({gesture: 'Ctrl+F8', session: retired}); consume({gesture: 'Ctrl+F8'});
  assert.ok(bind(b).classList.contains('capturing'), 'stale and unidentified production events stay rejected');
  window.DEV.previewBindCaptured(); await tick();
  assert.equal(events.at(-1).session, sessionB, 'stale arm/disarm cannot replace current session');
  assert.equal((await api.get_preview_hotkey_state()).hotkeys.characters[b], 'Ctrl+Alt+F9');
  await arm(false, sessionB + 1); await arm(true, sessionB + 1);
  window.DEV.previewBindCaptured(); assert.equal(events.length, count + 1, 'disarm before arm retires that session');
  console.log('PASS dev');
})().catch(error => { console.error(error); process.exitCode = 1; });
