// Real Preview renderer and listeners; DOM/bridge only are doubled.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createDOM} = require('./screenshot_dom.cjs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const {document, Element} = createDOM(data.page);
const window = new Element('window');
Object.assign(window, {window, document, console, Promise, setTimeout, clearTimeout,
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }});
const context = vm.createContext(window);
vm.runInContext(fs.readFileSync(web + '/app.js', 'utf8'), context);
const calls = [];
window.WM.send = (method, ...args) => {
  calls.push([method, ...args]);
  assert.ok(['set_bind_capture', 'get_preview_hotkey_state', 'get_preview_crop_state'].includes(method), method);
  return Promise.resolve(method === 'set_bind_capture' ? true : null);
};
vm.runInContext(fs.readFileSync(web + '/previews.js', 'utf8'), context);
const owner = 'Aiga Otsolen';
const configure = () => document.querySelector('[data-preview-configure="' + owner + '"]');
(async () => {
  const stickyErrors = {
    'sticky-missing-row': /owning row/,
    'sticky-wrong-owner': /owning keybind/,
    'sticky-covered': /sticky header/,
    'sticky-bottom-clamp': /bottom clamp/,
    'sticky-outside-scrollport': /scrollport/
  };
  const scenarios = ['collapsed', 'expanded', 'sticky-normal'].concat(Object.keys(stickyErrors));
  assert.ok(scenarios.includes(data.scenario), 'Unknown preview warning scenario: ' + data.scenario);
  await new Promise(resolve => setImmediate(resolve));
  calls.length = 0; // The module's initial read is not part of staging.
  if (data.scenario.startsWith('sticky-')) {
    // Geometry is a deterministic boundary double, not rendered evidence.
    // Production staging must validate ownership, occlusion and scroll clamps.
    const outer = document.querySelector('.settings-pane');
    outer.scrollTop = 57;
    const pane = document.getElementById('settings-previews-characters');
    pane.scrollTop = 0; pane.scrollHeight = 1625; pane.clientHeight = 625;
    const rect = (top, height) => ({top, bottom: top + height, height, left: 0, right: 600, width: 600});
    const contentTop = el => el.classList.contains('preview-bind-conflict') ? 400 : 444;
    Element.prototype.scrollIntoView = function () {
      assert.equal(pane.hidden, false, 'staging selects Characters before scrolling');
      assert.equal(this.closest('.settings-subpage'), pane);
      pane.scrollTop = contentTop(this);
    };
    Element.prototype.getBoundingClientRect = function () {
      if (this === pane) return rect(0, 625);
      if (this.parentNode?.classList.contains('bind-head')) return rect(40, 22);
      if (this.classList.contains('preview-bind-conflict')) {
        if (data.scenario === 'sticky-covered') return rect(20, 40);
        if (data.scenario === 'sticky-outside-scrollport') return rect(700, 40);
        return rect(400 - pane.scrollTop, 40);
      }
      return rect(444 - pane.scrollTop, 28);
    };
    if (data.scenario === 'sticky-bottom-clamp') pane.scrollHeight = 700;
    const getById = document.getElementById;
    document.getElementById = id => {
      const el = getById(id);
      if (el && id.startsWith('preview-bind-conflict-')) {
        if (data.scenario === 'sticky-missing-row') document.body.appendChild(el);
        if (data.scenario === 'sticky-wrong-owner') el.parentNode.querySelector('.bindbtn').setAttribute('aria-describedby', 'wrong-owner');
      }
      return el;
    };
    if (data.scenario === 'sticky-normal') {
      vm.runInContext(data.stage, context);
      const warning = document.querySelector('.preview-bind-conflict');
      assert.ok(warning.getBoundingClientRect().top >= 62);
      assert.ok(configure().parentNode.querySelector('.bindbtn').getBoundingClientRect().bottom < 625);
      assert.ok(pane.scrollTop < pane.scrollHeight - pane.clientHeight - 1);
    } else {
      assert.throws(() => vm.runInContext(data.stage, context), stickyErrors[data.scenario]);
    }
    assert.equal(outer.scrollTop, 57, 'the outer Settings pane is not the scroll owner');
    assert.equal(pane.hidden, false, 'Characters remains the selected subpage');
    assert.equal(calls.length, 0, 'staging stays local and read-only: ' + JSON.stringify(calls));
    console.log('PASS preview warning grouping ' + data.scenario);
    return;
  }
  window.onPreviewHotkeys(data.fixture);
  if (data.scenario === 'expanded') configure().click();
  const row = configure().parentNode;
  const warning = document.getElementById('preview-bind-conflict-' + encodeURIComponent('character:' + owner));
  assert.ok(warning, 'fixture produces a real conflict');
  assert.ok(warning.parentNode === row, 'warning belongs inside its owning row, not between unrelated rows');
  assert.ok(row.firstElementChild === warning, 'warning scrolls away before its own controls, never lingers above the next character');
  assert.equal(row.children[1].querySelector('.lab-name').textContent, owner);
  const bind = row.querySelector('.bindbtn');
  assert.equal(bind.getAttribute('aria-describedby'), warning.id);
  assert.match(warning.textContent, /^Aiga Otsolen: Ctrl\+Alt\+1 /);
  if (data.scenario === 'expanded') {
    assert.equal(row.nextSibling.id, 'preview-character-detail-' + encodeURIComponent(owner), 'optional geometry/crop detail follows warning and owning controls');
    assert.ok(document.activeElement === configure(), 'Configure keeps its normal focus return');
  }
  // Every conflict kind must be attached to precisely its own bind, not just Aiga.
  for (const message of document.querySelectorAll('.preview-bind-conflict')) {
    const owningRow = message.parentNode;
    assert.ok(owningRow.classList.contains('row'));
    assert.ok(owningRow.firstElementChild === message);
    assert.equal(owningRow.querySelector('.bindbtn').getAttribute('aria-describedby'), message.id);
    assert.equal(document.querySelectorAll('[aria-describedby="' + message.id + '"]').length, 1);
  }
  bind.focus(); bind.click(); await new Promise(resolve => setImmediate(resolve));
  assert.ok(document.activeElement === bind);
  assert.ok(bind.classList.contains('capturing'));
  document.dispatchEvent({type: 'wm:section', detail: 'general'});
  assert.ok(!bind.classList.contains('capturing'));
  const before = calls.length;
  document.dispatchEvent({type: 'keydown', key: 'x', ctrlKey: true, altKey: true});
  assert.equal(calls.length, before, 'leaving the section disarms capture listeners');
  const clean = JSON.parse(JSON.stringify(data.fixture));
  clean.bookmark_chords.active = [];
  window.onPreviewHotkeys(clean);
  assert.equal(configure().parentNode.querySelector('.bindbtn').getAttribute('aria-describedby'), null, 'resolved warning leaves no stale ID reference');
  console.log('PASS preview warning grouping ' + data.scenario);
})().catch(error => { console.error(error); process.exitCode = 1; });
