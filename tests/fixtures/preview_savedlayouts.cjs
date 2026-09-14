// Execute the production module against real Python-generated controller receipts.
// DOM/bridge doubles prove ordering, not CSS, WebView2 or native EVE acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createDOM} = require('./screenshot_dom.cjs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const clone = value => JSON.parse(JSON.stringify(value));
const tick = () => new Promise(resolve => setImmediate(resolve));
const {document, Element} = createDOM(data.page);
Element.prototype.hasAttribute = function(name) { return this.getAttribute(name) !== null; };
Element.prototype.select = function() { this.selectionStart = 0; this.selectionEnd = this.value.length; };
const window = new Element('window');
Object.assign(window, {window, document, console, Promise, setTimeout, clearTimeout,
  getComputedStyle: () => ({visibility: 'visible'}),
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }});
const context = vm.createContext(window);
vm.runInContext(fs.readFileSync(web + '/app.js', 'utf8'), context);
const getters = [], writes = [];
window.WM.send = (method, ...args) => {
  if (method === 'get_preview_hotkey_state') return new Promise(resolve => getters.push(resolve));
  if (method === 'set_preview_excluded' || method === 'set_preview_binds') return new Promise(resolve => writes.push({method, args, resolve}));
  if (method === 'set_bind_capture') return Promise.resolve(true);
  if (method === 'capture_preview_bind') return Promise.resolve({gesture: 'Ctrl+F8', error: null});
  if (method === 'get_preview_crop_state' || method === 'alert_bookmarks') return Promise.resolve(null);
  throw new Error('Unexpected bridge call ' + method);
};
vm.runInContext(fs.readFileSync(web + '/previews.js', 'utf8'), context);
const row = name => Array.from(document.querySelectorAll('#preview-binds .lab')).find(el => el.title === name).parentNode;
const box = name => row(name).querySelector('input[type=checkbox]');
const bind = name => row(name).querySelector('.bindbtn');
const push = receipt => window.onPreviewLayouts(clone(receipt.state));
function change(name, checked) {
  const control = box(name);
  assert.equal(control.disabled, false, name + ' remains explicitly retryable');
  control.checked = checked; control.dispatchEvent({type: 'change'});
  return writes.at(-1);
}
(async () => {
  if (data.scenario === 'early') {
    push(data.hidden);
    getters.shift()(clone(data.initial)); await tick();
    assert.equal(box('Alice').checked, false, 'old initial hydration cannot restore old exclusions');
    return console.log('PASS early');
  }
  getters.shift()(clone(data.initial)); await tick();
  if (data.scenario === 'reversed') {
    const first = change('Alice', false), second = change('Bob', false);
    second.resolve(clone(data.both)); await tick();
    first.resolve(clone(data.hidden)); await tick();
    assert.equal(box('Alice').checked, false);
    assert.equal(box('Bob').checked, false, 'older callback cannot drop another accepted choice');
    window.onPreviewHotkeys(clone(data.initial));
    assert.equal(box('Bob').checked, false, 'old whole-table payload cannot revert exclusions');
  } else if (data.scenario === 'bulk') {
    push(data.hidden);
    const pending = change('Alice', true);
    push(data.bulk);
    pending.resolve(clone(data.visible)); await tick();
    assert.equal(box('Alice').checked, false, 'bulk push outranks a delayed ordinary receipt');
    assert.equal(box('Bob').checked, false);
    const legacy = clone(data.initial); delete legacy.layout_state;
    window.onPreviewHotkeys(legacy);
    assert.equal(box('Alice').checked, false, 'missing revision is not authority after hydration');
  } else if (data.scenario === 'keybind') {
    bind('Alice').click(); await tick();
    document.dispatchEvent({type: 'keydown', key: 'F8', code: 'F8', ctrlKey: true}); await tick();
    const pending = writes.at(-1);
    assert.equal(pending.method, 'set_preview_binds');
    push(data.visible); // no hotkey table was replaced
    pending.resolve(true); await tick();
    assert.equal(bind('Alice').textContent, 'Ctrl+F8', 'layout handler must not invalidate keybind ownership');
  } else if (data.scenario === 'retry') {
    const pending = change('Alice', false);
    pending.resolve(clone(data.refused)); await tick();
    assert.equal(box('Alice').checked, false, 'refusal uses authoritative baseline, not inverse submission');
    const retry = change('Alice', true); // no push after native gesture completion
    retry.resolve(clone(data.retry)); await tick();
    assert.equal(box('Alice').checked, true);
    assert.equal(writes.length, 2);
  } else if (data.scenario === 'draft') {
    const field = document.querySelector('.group-add-name');
    field.value = 'Unsubmitted fleet';
    push(data.hidden);
    assert.equal(document.querySelector('.group-add-name').value, 'Unsubmitted fleet');
    assert.equal(writes.length, 0);
  } else if (data.scenario === 'named') {
    // A pending named operation is an actual local conflict, unlike an advisory drag.
    push({state: data.pending});
    assert.equal(box('Alice').disabled, true);
    push(data.bulk);
    assert.equal(box('Alice').disabled, false);
  } else if (data.scenario === 'staging') {
    // Existing screenshot interface isolates its display without authorizing writes.
    const fixture = {kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: clone(data.initial),
      crops: {...data.initial.crops, definitions: {Alice: {}}}};
    window.WM.previewCropScreenshot(fixture);
    push(data.bulk);
    assert.equal(box('Alice').checked, true, 'live state must not leak into staged screenshot');
    window.WM.previewCropScreenshot(null);
    assert.equal(box('Alice').checked, false, 'latest live state is restored on exit');
  }
  console.log('PASS ' + data.scenario);
})().catch(error => { console.error(error); process.exitCode = 1; });
