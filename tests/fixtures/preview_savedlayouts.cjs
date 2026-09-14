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
Element.prototype.setSelectionRange = function(start, end, direction) {
  this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction;
};
// This harness exercises shared dialog focus ownership: the structure-only DOM
// does not bubble focus events. Keep this behavior local to the interactive page.
Element.prototype.focus = function() {
  if (this.disabled || document.activeElement === this) return;
  document.activeElement = this;
  for (let target = this; target; target = target.parentNode) {
    target.dispatchEvent({type: 'focusin', target: this});
  }
};
const window = new Element('window');
Object.assign(window, {window, document, console, Promise, setTimeout, clearTimeout,
  getComputedStyle: () => ({visibility: 'visible'}),
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }});
const context = vm.createContext(window);
vm.runInContext(fs.readFileSync(web + '/app.js', 'utf8'), context);
const getters = [], writes = [];
window.WM.send = (method, ...args) => {
  if (method === 'get_preview_hotkey_state') return new Promise(resolve => getters.push(resolve));
  if (method === 'set_preview_excluded' || method === 'set_preview_binds' || method === 'set_preview_character_marker') return new Promise((resolve, reject) => writes.push({method, args, resolve, reject}));
  if (['set_preview_size', 'copy_preview_layout', 'create_preview_layout', 'apply_preview_layout', 'update_preview_layout',
       'rename_preview_layout', 'remove_preview_layout'].includes(method)) {
    return new Promise((resolve, reject) => writes.push({method, args, resolve, reject}));
  }
  if (method === 'parse_preview_size') return Promise.resolve({w: 600, h: 400, error: null});
  if (method === 'set_bind_capture') return Promise.resolve(true);
  if (method === 'capture_preview_bind') return Promise.resolve({gesture: 'Ctrl+F8', error: null});
  if (method === 'get_preview_crop_state' || method === 'alert_bookmarks') return Promise.resolve(null);
  throw new Error('Unexpected bridge call ' + method);
};
vm.runInContext(fs.readFileSync(web + '/previews.js', 'utf8'), context);
vm.runInContext(fs.readFileSync(web + '/panel.js', 'utf8'), context);
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
  if (data.scenario === 'controls-unhydrated') {
    for (const action of ['save', 'apply', 'update', 'rename', 'remove']) {
      const control = document.getElementById('preview-layout-' + action);
      assert.equal(control.disabled, true); control.click();
    }
    assert.equal(writes.length, 0);
    return console.log('PASS controls-unhydrated');
  }
  getters.shift()(clone(data.initial)); await tick();
  const el = id => document.getElementById(id);
  const stage = () => {
    const fixture = clone(data.initial);
    fixture.geometry_revision = 9999;
    fixture.sizes.Alice = [999, 777];
    fixture.layout_sources[0].geometry.w = 999;
    fixture.layout_state = clone(data.created.state);
    fixture.layout_state.revision = 9999;
    fixture.layout_state.excluded = ['Bob'];
    fixture.layout_state.layouts[0].name = 'Fixture only';
    window.WM.previewCropScreenshot({kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: fixture,
      crops: {...data.initial.crops, definitions: {Alice: {}}}});
  };
  const detailButton = (name, control) => {
    let button = document.querySelector('[data-preview-detail-control="' + control + '"]');
    if (!button || row(name).querySelector('[data-preview-configure]').getAttribute('aria-expanded') !== 'true') {
      row(name).querySelector('[data-preview-configure]').click();
      button = document.querySelector('[data-preview-detail-control="' + control + '"]');
    }
    return button;
  };
  if (data.scenario === 'owner-controls') {
    window.WM.openSettingsSection('previews', 'characters');
    const marker = detailButton('Target', 'marker');
    assert.equal(marker.disabled, false, 'displayed owner can change Identification');
    marker.focus(); marker.value = 'cyan'; marker.dispatchEvent({type: 'change'});
    assert.deepEqual(writes.at(-1).args, ['Target', 'cyan']);
    writes.at(-1).resolve(clone(data.marker)); await tick();
    assert.equal(document.querySelector('.preview-marker-select').value, 'cyan');
    assert.equal(el(marker.getAttribute('aria-describedby')).textContent, '');
    if (!box('Target').checked) { change('Target', true).resolve(clone(data.visible)); await tick(); }
    const copy = detailButton('Target', 'copy'); assert.equal(copy.disabled, false); copy.focus(); copy.click();
    el('dlg-select').value = 'Source'; el('dlg-ok').click(); await tick();
    assert.deepEqual(writes.at(-1).args, ['Target', 'Source']);
    assert.equal(data.copied.persisted, true);
    writes.at(-1).resolve(clone(data.copied)); await tick();
    assert.ok(!el('preview-copy-status').classList.contains('err'));
  } else if (data.scenario === 'geometry-detail-focus') {
    window.WM.openSettingsSection('previews', 'characters');
    const marker = detailButton('Alice', 'marker'); marker.focus();
    window.onPreviewGeometry(clone(data.newer_geometry));
    assert.ok(document.activeElement === marker && document.contains(marker), 'geometry must keep the attached Identification select focused');
    marker.value = 'cyan'; marker.dispatchEvent({type: 'change'});
    assert.deepEqual(writes.at(-1).args, ['Alice', 'cyan'], 'retained control still edits the real owner');
    writes.at(-1).resolve({applied: true, persisted: true, error: null, marker: 'cyan'}); await tick();
    assert.equal(document.querySelector('.preview-marker-select').value, 'cyan');
    const manager = document.querySelector('.preview-group-manager'); manager.open = true;
    const draft = document.querySelector('.group-add-name'); draft.value = 'Useful group draft'; draft.focus();
    draft.setSelectionRange(7, 12, 'backward');
    window.onPreviewGeometry(clone(data.newer_copy));
    assert.ok(document.activeElement === draft, 'geometry leaves ordinary text editing attached');
    assert.equal(draft.value, 'Useful group draft');
    assert.deepEqual([draft.selectionStart, draft.selectionEnd, draft.selectionDirection], [7, 12, 'backward']);
    const copy = detailButton('Alice', 'copy'); copy.focus();
    window.onPreviewGeometry(clone(data.newer_reset));
    assert.ok(document.activeElement !== copy, 'removed geometry action cannot retain focus');
    assert.ok(document.activeElement !== marker, 'removal cannot revive older Identification focus');
  } else if (data.scenario === 'geometry-detail-dialog') {
    window.WM.openSettingsSection('previews', 'characters');
    const size = detailButton('Alice', 'size'); size.focus(); size.click();
    const draft = el('dlg-input'); draft.value = '640x480'; draft.focus(); draft.setSelectionRange(0, 3, 'forward');
    window.onPreviewGeometry(clone(data.newer_geometry));
    assert.ok(document.activeElement === draft);
    assert.deepEqual([draft.value, draft.selectionStart, draft.selectionEnd], ['640x480', 0, 3]);
    el('dlg-cancel').click(); await tick();
    assert.ok(document.activeElement === size && document.contains(size), 'geometry keeps an owned ordinary dialog invoker attached');
  } else if (data.scenario === 'staging-roundtrip') {
    push(data.created);
    push(data.visible);
    const select = el('preview-layout-select');
    select.value = data.created.state.layouts[0].id; select.dispatchEvent({type: 'change'});
    el('preview-layout-save').click();
    el('dlg-input').value = 'Duplicate'; el('dlg-ok').click(); await tick();
    writes.at(-1).reject(new Error('Saved live feedback')); await tick();
    change('Alice', false).reject(new Error('Alice live feedback')); await tick();
    const feedback = el('preview-layout-status').textContent;
    const selection = select.value;
    stage();
    assert.equal(box('Bob').checked, false, 'fixture has different choices');
    window.WM.previewCropScreenshot(null); // deliberately no live push/receipt during staging
    detailButton('Alice', 'size').click();
    assert.equal(el('dlg-input').value, '500x300', 'fixture geometry must not mutate retained live state');
    el('dlg-cancel').click(); await tick();
    assert.equal(box('Bob').checked, true, 'fixture exclusions must not mutate retained live state');
    assert.equal(select.value, selection);
    assert.ok(select.options.some(option => option.textContent.includes('Hidden')));
    assert.equal(el('preview-layout-status').textContent, feedback);
    assert.match(el(box('Alice').getAttribute('aria-describedby')).textContent, /Alice live feedback/);
    window.onPreviewGeometry(clone(data.newer_geometry));
    detailButton('Alice', 'size').click();
    assert.equal(el('dlg-input').value, '700x450', 'fixture revision cannot poison live geometry high-water');
    el('dlg-cancel').click(); await tick();
    push(data.bulk);
    assert.equal(box('Bob').checked, false, 'live layout high-water is restored too');
  } else if (data.scenario.startsWith('copy-dialog-')) {
    const copy = detailButton('Bob', 'copy');
    copy.focus(); copy.click();
    el('dlg-select').value = 'Alice';
    const boundary = data.scenario.slice('copy-dialog-'.length);
    if (boundary === 'navigation') document.dispatchEvent({type: 'wm:section', detail: 'general'});
    if (boundary === 'subpage') {
      window.WM.settingsTab('previews', 'windows');
      window.WM.settingsTab('previews', 'characters');
    }
    if (boundary === 'staging') { stage(); window.WM.previewCropScreenshot(null); }
    if (boundary === 'configure') row('Alice').querySelector('[data-preview-configure]').click();
    if (boundary === 'attempt') copy.click(); // queued newer chooser, same detail interaction
    if (boundary === 'capture') { bind('Bob').focus(); bind('Bob').click(); await tick(); }
    el('dlg-ok').click(); await tick();
    assert.equal(writes.length, 0, 'stale chooser cannot admit Copy after ' + boundary);
    if (boundary === 'attempt') {
      el('dlg-select').value = 'Alice'; el('dlg-ok').click(); await tick();
      assert.equal(writes.length, 1, 'only the latest chooser may admit Copy');
      assert.deepEqual(writes[0].args, ['Bob', 'Alice']);
    }
    if (boundary === 'capture') {
      assert.ok(document.activeElement === bind('Bob'), 'old Copy dialog must not steal newer capture focus');
      assert.equal(bind('Bob').textContent, 'Press a key…');
    }
  } else if (data.scenario === 'dialog-focus-history') {
    const invoker = el('preview-layout-save');
    invoker.focus(); invoker.click();
    const queued = window.WM.confirm('Queued question', 'Must still be answered');
    bind('Bob').focus(); bind('Bob').click(); await tick();
    bind('Bob').blur(); // losing newer focus cannot revive the original lease
    el('dlg-input').focus();
    el('dlg-ok').click(); await tick();
    assert.equal(el('dlg-title').textContent, 'Queued question');
    el('dlg-cancel').click();
    assert.equal(await queued, false);
    assert.ok(document.activeElement !== invoker, 'returning to the dialog cannot revive revoked return focus');
    assert.equal(bind('Bob').textContent, 'Press a key…');
    assert.equal(writes.length, 0);
  } else if (data.scenario === 'dialog-owned-cancel') {
    for (const [name, action] of [['Alice', 'size'], ['Bob', 'copy']]) {
      const invoker = detailButton(name, action);
      invoker.focus(); invoker.click();
      const queued = window.WM.confirm('Queued question', 'Must still be answered');
      el('dlg-cancel').click(); await tick();
      assert.equal(el('dlg-title').textContent, 'Queued question');
      document.dispatchEvent({type: 'keydown', key: 'Escape'});
      assert.equal(await queued, false);
      assert.ok(document.activeElement === invoker, 'ordinary queued Cancel returns to ' + action);
      assert.equal(el('overlay').hidden, true);
      assert.equal(writes.length, 0);
    }
  } else if (data.scenario === 'copy-admitted-subpage') {
    window.WM.settingsTab('previews', 'characters');
    detailButton('Bob', 'copy').click();
    el('dlg-select').value = 'Alice'; el('dlg-ok').click(); await tick();
    const pending = writes.at(-1);
    assert.equal(pending.method, 'copy_preview_layout');
    window.WM.settingsTab('previews', 'windows');
    const newerFocus = el('preview-layout-save'); newerFocus.focus();
    pending.resolve({applied: true, persisted: true, error: null}); await tick();
    assert.equal(getters.length, 1, 'already-admitted Copy still refreshes after navigation');
    getters.shift()({...clone(data.initial), ...clone(data.newer_copy)}); await tick();
    assert.ok(document.activeElement === newerFocus, 'late refresh cannot reclaim detail focus');
  } else if (data.scenario.startsWith('controls-')) {
    const select = el('preview-layout-select');
    const button = action => el('preview-layout-' + action);
    assert.ok(select, 'labelled saved-layout selector exists');
    assert.equal(el('preview-layout-save').textContent, 'Save current as…');
    assert.equal(el('preview-layout-status').getAttribute('role'), 'status');
    const choose = receipt => {
      push(receipt);
      select.value = receipt.state.layouts[0].id;
      select.dispatchEvent({type: 'change'});
    };
    const accept = async text => {
      if (text !== undefined) el('dlg-input').value = text;
      el('dlg-ok').click(); await tick();
    };
    const status = () => el('preview-layout-status').textContent;
    if (data.scenario === 'controls-unavailable') {
      window.onPreviewHotkeys(clone(data.unavailable));
      assert.equal(button('save').disabled, true);
      assert.match(status(), /Open a named EVE client/);
    } else if (data.scenario === 'controls-reopen') {
      choose(data.created);
      assert.equal(el('preview-layout-reopen').hidden, true, 'unknown settings do not guess Off');
      document.dispatchEvent({type: 'wm:settings', detail: {settings: {preview: {restore_preview_positions: false}}}});
      assert.equal(el('preview-layout-reopen').hidden, false);
      button('apply').click();
      assert.match(el('dlg-body').textContent, /default stack/);
      el('dlg-cancel').click(); await tick();
      document.dispatchEvent({type: 'wm:preview-restore-positions', detail: {enabled: true}});
      assert.equal(el('preview-layout-reopen').hidden, true);
    } else if (data.scenario === 'controls-staged-receipt') {
      choose(data.created);
      button('apply').click(); await accept();
      const pending = writes.at(-1);
      window.WM.previewCropScreenshot({kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: clone(data.initial),
        crops: {...data.initial.crops, definitions: {Alice: {}}}});
      pending.resolve(clone(data.geometry_apply)); await tick();
      assert.equal(box('Alice').checked, true);
      button('save').click(); assert.equal(writes.length, 1);
      window.WM.previewCropScreenshot(null);
      assert.equal(select.value, data.created.state.layouts[0].id);
      assert.equal(box('Alice').checked, false);
      assert.equal(el('overlay').hidden, true);
    } else if (data.scenario === 'controls-failed-save' || data.scenario === 'controls-incomplete') {
      choose(data.created);
      button('save').click(); await accept('Refused');
      writes.at(-1).resolve(clone(data.scenario === 'controls-failed-save' ? data.failed_save : data.incomplete)); await tick();
      assert.match(status(), data.scenario === 'controls-failed-save' ? /Disk unavailable/ : /incomplete/);
      assert.equal(button('save').disabled, false);
    } else if (data.scenario === 'controls-empty') {
      assert.equal(button('apply').disabled, true);
      assert.equal(button('save').disabled, false, 'known offline owner can be saved');
      assert.match(status(), /Save current as/);
    } else if (data.scenario === 'controls-select') {
      choose(data.created);
      assert.equal(writes.length, 0);
      assert.equal(getters.length, 0);
      window.WM.settingsTab('previews', 'characters');
      window.WM.settingsTab('previews', 'windows');
      assert.equal(select.value, data.created.state.layouts[0].id);
      assert.equal(getters.length, 0, 'subpages never add reads');
      window.onPreviewHotkeys(clone(data.initial));
      assert.equal(select.value, data.created.state.layouts[0].id);
    } else if (data.scenario === 'controls-cancel') {
      choose(data.created);
      for (const action of ['save', 'apply', 'update', 'rename', 'remove']) {
        button(action).focus(); button(action).click();
        assert.equal(el('overlay').hidden, false);
        el('dlg-cancel').click(); await tick();
        assert.equal(writes.length, 0);
        assert.equal(document.activeElement, button(action), 'Cancel returns to the invoker');
      }
    } else if (data.scenario === 'controls-busy') {
      choose(data.created);
      push(data.refused);
      assert.equal(button('apply').disabled, false, 'external busy without a named operation remains retryable');
      button('apply').click(); await accept();
      writes.at(-1).resolve(clone(data.stale)); await tick();
      assert.match(status(), /changed/);
      assert.equal(button('apply').disabled, false);
    } else if (data.scenario === 'controls-errors') {
      choose(data.created);
      button('save').click(); await accept('HIDDEN');
      writes.at(-1).resolve(clone(data.duplicate)); await tick();
      assert.match(status(), /already/);
      button('apply').click(); await accept();
      writes.at(-1).resolve(clone(data.stale)); await tick();
      assert.match(status(), /changed/);
      button('save').click(); await accept('Fleet');
      writes.at(-1).reject(new Error('Bridge disconnected')); await tick();
      assert.match(status(), /Bridge disconnected/);
      assert.equal(button('save').disabled, false);
    } else if (data.scenario === 'controls-staging' || data.scenario === 'controls-capture') {
      choose(data.created);
      button('save').focus(); button('save').click();
      if (data.scenario === 'controls-staging') {
        window.WM.previewCropScreenshot({kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: clone(data.initial),
          crops: {...data.initial.crops, definitions: {Alice: {}}}});
        window.WM.previewCropScreenshot(null);
      } else {
        push(data.visible);
        bind('Bob').focus(); bind('Bob').click(); await tick();
      }
      await accept('Late');
      assert.equal(writes.length, 0, 'late dialog cannot mutate across staging or a newer capture');
      if (data.scenario === 'controls-capture') {
        assert.ok(document.activeElement === bind('Bob'), 'old Saved dialog must not steal newer capture focus');
        assert.equal(bind('Bob').textContent, 'Press a key…');
      }
    } else if (data.scenario === 'controls-pending') {
      choose(data.created);
      const ordinary = change('Alice', true);
      button('apply').click(); await accept();
      const apply = writes.at(-1);
      assert.equal(apply.method, 'apply_preview_layout');
      button('apply').click();
      assert.equal(writes.length, 2, 'repeated click cannot queue another operation');
      assert.equal(select.disabled, false, 'selection stays usable while named work is pending');
      push(data.bulk);
      ordinary.resolve(clone(data.visible)); await tick();
      assert.equal(box('Bob').checked, false);
      document.dispatchEvent({type: 'wm:section', detail: 'general'});
      const other = el('btn-settings'); other.focus();
      apply.resolve(clone(data.geometry_apply)); await tick();
      assert.equal(el('overlay').hidden, true);
      assert.equal(document.activeElement, other, 'late receipt cannot steal focus');
    } else {
      const action = data.scenario.slice('controls-'.length);
      choose(action === 'rename' ? data.updated : action === 'remove' ? data.renamed : data.created);
      const selected = select.value;
      button(action).click();
      assert.equal(el('overlay').hidden, false);
      if (action === 'remove') assert.equal(el('dlg-ok').classList.contains('danger'), true);
      if (action === 'apply') assert.match(el('dlg-body').textContent, /other characters|Other characters/);
      await accept(action === 'save' ? 'Hidden' : action === 'rename' ? '__proto__' : undefined);
      const pending = writes.at(-1);
      const methods = {save: 'create', apply: 'apply', update: 'update', rename: 'rename', remove: 'remove'};
      assert.equal(pending.method, methods[action] + '_preview_layout');
      if (action !== 'save') assert.equal(pending.args[0], selected);
      const receipt = {save: data.created, apply: data.geometry_apply, update: data.updated, rename: data.renamed, remove: data.removed}[action];
      pending.resolve(clone(receipt)); await tick();
      assert.match(status(), /saved|Saved|Applied|applied|Renamed|Removed/);
      if (action === 'remove') assert.equal(select.value, '');
      if (action === 'rename') assert.ok(select.options.some(option => option.textContent.includes('__proto__')));
    }
  } else if (data.scenario === 'row-rejected') {
    const pending = change('Alice', false);
    pending.reject(new Error('Bridge disconnected')); await tick();
    assert.equal(box('Alice').disabled, false);
    assert.match(document.getElementById(box('Alice').getAttribute('aria-describedby')).textContent, /Bridge disconnected/);
  } else if (data.scenario === 'row-feedback') {
    const first = change('Alice', false);
    first.resolve(clone(data.refused)); await tick();
    const described = box('Alice').getAttribute('aria-describedby');
    assert.ok(described, 'refusal is linked to its own row');
    assert.match(document.getElementById(described).textContent, /pending/);
    const second = change('Bob', false);
    second.resolve(clone(data.refused)); await tick();
    assert.match(document.getElementById(box('Alice').getAttribute('aria-describedby')).textContent, /pending/);
    const retry = change('Alice', true);
    retry.resolve(clone(data.retry)); await tick();
    assert.match(document.getElementById(box('Bob').getAttribute('aria-describedby')).textContent, /pending/);
  } else if (data.scenario.startsWith('geometry-')) {
    const sizeDialog = () => {
      if (!document.querySelector('[data-preview-detail-control="size"]')) {
        row('Alice').querySelector('[data-preview-configure]').click();
      }
      document.querySelector('[data-preview-detail-control="size"]').focus();
      document.querySelector('[data-preview-detail-control="size"]').click();
      return document.getElementById('dlg-input').value;
    };
    if (data.scenario.startsWith('geometry-dialog-')) {
      sizeDialog();
      if (data.scenario === 'geometry-dialog-navigation') document.dispatchEvent({type: 'wm:section', detail: 'general'});
      else { bind('Bob').focus(); bind('Bob').click(); await tick(); }
      document.getElementById('dlg-input').value = '600x400';
      document.getElementById('dlg-ok').click(); await tick();
      assert.equal(writes.length, 0, 'Size dialog may not act after navigation or a newer capture');
      if (data.scenario === 'geometry-dialog-capture') {
        assert.ok(document.activeElement === bind('Bob'), 'old Size dialog must not steal newer capture focus');
        assert.equal(bind('Bob').textContent, 'Press a key…');
      }
    } else if (data.scenario === 'geometry-ack') {
      assert.equal(sizeDialog(), '500x300');
      document.getElementById('dlg-input').value = '600x400';
      document.getElementById('dlg-ok').click(); await tick();
      const ack = writes.at(-1);
      assert.equal(ack.method, 'set_preview_size');
      // The 600 edit was never sampled. Apply returns equal 500 values with a
      // newer observation, so value comparison cannot fence the old ACK.
      window.onPreviewGeometry(clone(data.geometry_apply.geometry));
      ack.resolve(clone(data.size_ack)); await tick();
      assert.equal(sizeDialog(), '500x300', 'queue ACK must not overwrite settled Apply geometry');
      document.getElementById('dlg-cancel').click(); await tick();
      window.onPreviewGeometry(clone(data.newer_geometry));
      assert.equal(sizeDialog(), '700x450', 'later ordinary Size wins');
      document.getElementById('dlg-cancel').click(); await tick();
      window.onPreviewGeometry(clone(data.newer_copy));
      assert.equal(sizeDialog(), '640x480', 'later ordinary Copy wins');
      document.getElementById('dlg-cancel').click(); await tick();
      window.onPreviewGeometry(clone(data.newer_reset));
      assert.equal(document.querySelector('[data-preview-detail-control="size"]'), null, 'Reset retires geometry-only Size eligibility');
    } else if (data.scenario === 'geometry-getter') {
      document.dispatchEvent({type: 'wm:section', detail: 'previews'});
      window.onPreviewGeometry(clone(data.newer_geometry));
      getters.shift()(clone(data.initial)); await tick();
      assert.equal(sizeDialog(), '700x450', 'delayed getter overlays accepted geometry');
      document.getElementById('dlg-cancel').click(); await tick();
      window.onPreviewHotkeys(clone(data.initial));
      assert.equal(sizeDialog(), '700x450', 'full push overlays accepted geometry too');
    } else if (data.scenario === 'geometry-keybind') {
      bind('Alice').click(); await tick();
      document.dispatchEvent({type: 'keydown', key: 'F8', code: 'F8', ctrlKey: true}); await tick();
      const pending = writes.at(-1);
      window.onPreviewGeometry(clone(data.newer_geometry));
      pending.resolve(true); await tick();
      assert.equal(bind('Alice').textContent, 'Ctrl+F8');
    } else {
      const fixture = {kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: clone(data.initial),
        crops: {...data.initial.crops, definitions: {Alice: {}}}};
      window.WM.previewCropScreenshot(fixture);
      window.onPreviewGeometry(clone(data.newer_geometry));
      window.WM.previewCropScreenshot(null);
      assert.equal(sizeDialog(), '700x450');
    }
  } else if (data.scenario === 'reversed') {
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
