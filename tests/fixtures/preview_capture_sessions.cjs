// Production capture transport, with independently delayed bridge replies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createDOM} = require('./screenshot_dom.cjs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const {document, Element} = createDOM(data.page);
Element.prototype.hasAttribute = function(name) { return this.getAttribute(name) !== null; };
const window = new Element('window');
Object.assign(window, {window, document, console, Promise, setTimeout, clearTimeout,
  getComputedStyle: () => ({visibility: 'visible'}),
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }});
const context = vm.createContext(window);
vm.runInContext(fs.readFileSync(web + '/app.js', 'utf8'), context);
const arms = [], parses = [], writes = [];
window.WM.send = (method, ...args) => {
  if (method === 'get_preview_hotkey_state') return Promise.resolve(data.initial);
  if (method === 'set_bind_capture') return new Promise(resolve => arms.push({args, resolve}));
  if (method === 'capture_preview_bind') return new Promise(resolve => parses.push(resolve));
  if (method === 'set_preview_binds') { writes.push(args[0]); return Promise.resolve(true); }
  if (method === 'get_preview_crop_state') return Promise.resolve(null);
  throw Error(method);
};
vm.runInContext(fs.readFileSync(web + '/previews.js', 'utf8'), context);
const tick = () => new Promise(resolve => setImmediate(resolve));
const bind = name => Array.from(document.querySelectorAll('#preview-binds .lab')).find(el => el.title === name).parentNode.querySelector('.bindbtn');
const key = () => document.dispatchEvent({type: 'keydown', key: 'F8', code: 'F8', ctrlKey: true});
const native = (session, gesture = 'Ctrl+F8') => window.onPreviewBindCaptured({session, gesture});
(async () => {
  await tick();
  bind('Alice').click();
  const a = arms.at(-1);
  assert.equal(a.args[0], true);
  assert.equal(typeof a.args[1], 'number', 'page supplies an identified session');
  assert.equal(bind('Alice').classList.contains('capturing'), false, 'wait before inviting key');
  key(); assert.equal(parses.length, 0, 'no local key accepted before arm reply');
  if (data.scenario === 'local') {
    a.resolve(false); await tick(); // native unavailable: local path still works
    key(); assert.equal(parses.length, 1);
    window.WM.endPreviewCapture();
    bind('Bob').click(); const b = arms.at(-1); b.resolve(false); await tick();
    parses[0]({gesture: 'Ctrl+F7'}); await tick();
    assert.equal(writes.length, 0, 'late local parse from A cannot bind B');
    key(); parses[1]({gesture: 'Ctrl+F9'}); await tick();
    assert.equal(writes[0].characters.Bob, 'Ctrl+F9');
  } else if (data.scenario === 'boundary') {
    document.dispatchEvent({type: 'wm:section', detail: {section: 'alerts'}});
    assert.deepEqual(Array.from(arms.at(-1).args), [false, a.args[1]]);
    a.resolve(true); await tick(); native(a.args[1]);
    assert.equal(writes.length, 0);
    bind('Bob').click(); const b = arms.at(-1); b.resolve(true); await tick();
    window.WM.previewCropScreenshot({kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: data.initial,
      crops: {...data.initial.crops, definitions: {Alice: {}}}});
    native(b.args[1]);
    window.WM.previewCropScreenshot(null);
    native(b.args[1]);
    assert.equal(writes.length, 0, 'screenshot ingress retires live capture even after exit');
  } else {
    window.WM.endPreviewCapture();
    const disarm = arms.at(-1);
    assert.deepEqual(Array.from(disarm.args), [false, a.args[1]]);
    bind('Bob').click(); const b = arms.at(-1);
    assert.ok(b.args[1] > a.args[1]);
    b.resolve(true); await tick();
    a.resolve(true); disarm.resolve(true); await tick();
    native(a.args[1]); native(undefined); await tick();
    assert.equal(writes.length, 0, 'old or unidentified result cannot bind current B');
    assert.ok(bind('Bob').classList.contains('capturing'));
    native(b.args[1], 'Ctrl+F9'); await tick();
    assert.equal(writes.length, 1);
    assert.equal(writes[0].characters.Bob, 'Ctrl+F9');
    assert.equal(writes[0].characters.Alice, undefined);
    assert.deepEqual(Array.from(arms.at(-1).args), [false, b.args[1]]);
  }
  console.log('PASS ' + data.scenario);
})().catch(error => {console.error(error); process.exitCode = 1;});
