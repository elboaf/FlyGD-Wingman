// Execute the real shell and both capture owners; only DOM/bridge are doubled.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const {document, Element} = require('./screenshot_dom.cjs').createDOM(data.page);
const window = new Element('window');
Object.assign(window, {document, console, Promise, Math, Date,
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
  setTimeout, clearTimeout, requestAnimationFrame: callback => setTimeout(callback, 0)});
window.window = window;
const runtime = vm.createContext(window);
const load = name => vm.runInContext(fs.readFileSync(web + '/' + name + '.js', 'utf8'), runtime);
load('app');
const WM = window.WM;
const calls = [];
WM.send = (method, ...args) => {
  calls.push([method, ...args]);
  return Promise.resolve(method === 'get_bookmarks' ? data.bookmarks
    : method === 'get_preview_hotkey_state' ? data.previews : null);
};
load('bookmarks');
load('fleet');
load('previews');
const turn = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  await turn();
  for (const section of ['bookmarks', 'previews']) {
    WM.openSettingsSection(section);
    await turn();
    const pane = document.getElementById('section-' + section);
    const bind = pane.querySelector('.bindbtn');
    assert.ok(bind, section + ' renders a capture control');
    bind.click();
    await turn();
    assert.ok(bind.classList.contains('capturing'), section + ' capture armed');
    calls.length = 0;
    if (section === 'previews') document.getElementById('preview-fleet-settings').click();
    else document.querySelector('.rail-item[data-section="fleet"]').click();
    await turn();
    assert.equal(WM.current_section, 'fleet');
    assert.equal(pane.querySelector('.capturing'), null);
    let consumed = false;
    for (const [key, code] of [['Tab', 'Tab'], ['x', 'KeyX']]) {
      document.dispatchEvent({type: 'keydown', key, code,
        preventDefault() { consumed = true; }, stopPropagation() { consumed = true; }});
    }
    await turn();
    assert.equal(consumed, false, section + ' capture cannot escape into Fleet');
    assert.ok(calls.every(([method, value]) => method === 'set_bind_capture' && value === false),
      'navigation may release capture, never save a bind or opt into a feature: ' + JSON.stringify(calls));
    if (section === 'previews') assert.deepEqual(calls, [['set_bind_capture', false]]);
  }
  console.log('PASS Fleet navigation releases both capture owners without mutations');
})().catch(error => { console.error(error); process.exitCode = 1; });
