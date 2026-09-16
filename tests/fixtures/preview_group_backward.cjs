// Production page and bridge receipts; this is not native/WebView2 acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createDOM} = require('./screenshot_dom.cjs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const clone = value => JSON.parse(JSON.stringify(value));
const tick = () => new Promise(resolve => setImmediate(resolve));
const {document, Element} = createDOM(data.page);
Element.prototype.hasAttribute = function (name) { return this.getAttribute(name) !== null; };
Element.prototype.select = function () { this.selectionStart = 0; this.selectionEnd = this.value.length; };
// Focus cases model native removal, ancestor visibility, selection and bubbling.
// Keep these platform seams local; production handlers are not replaced.
if (data.scenario.startsWith('focus-')) {
  const removeChild = Element.prototype.removeChild;
  Element.prototype.removeChild = function (el) {
    if (el.contains(document.activeElement)) document.activeElement = document.body;
    return removeChild.call(this, el);
  };
  const text = Object.getOwnPropertyDescriptor(Element.prototype, 'textContent');
  Object.defineProperty(Element.prototype, 'textContent', {...text, set(value) {
    if (this !== document.activeElement && this.contains(document.activeElement)) document.activeElement = document.body;
    text.set.call(this, value);
  }});
  const matches = Element.prototype.matches;
  Element.prototype.matches = function (selector) {
    if (selector.includes(':not([hidden])') && this.hidden) return false;
    if (selector.includes(':not(:disabled)') && this.disabled) return false;
    return matches.call(this, selector.replaceAll(':not([hidden])', '').replaceAll(':not(:disabled)', ''));
  };
  Element.prototype.getClientRects = function () {
    if (!document.contains(this)) return [];
    let child = this;
    for (let el = this; el; child = el, el = el.parentNode) {
      if (el.hidden || (el.tagName === 'DETAILS' && !el.open && child.tagName !== 'SUMMARY')) return [];
    }
    return [this.getBoundingClientRect()];
  };
  Element.prototype.focus = function () {
    if (this.disabled || !this.getClientRects().length || document.activeElement === this) return;
    document.activeElement = this;
    for (let el = this; el; el = el.parentNode) el.dispatchEvent({type: 'focusin', target: this});
  };
  Element.prototype.setSelectionRange = function (start, end, direction = 'none') {
    this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction;
  };
  document.activeElement = document.body;
}
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
  if (['set_preview_cycle_group_bind', 'set_preview_cycle_group_prev_bind', 'rename_preview_cycle_group', 'delete_preview_cycle_group', 'create_preview_cycle_group'].includes(method)) {
    return new Promise(resolve => writes.push({method, args, resolve}));
  }
  if (method === 'set_bind_capture') return Promise.resolve(true);
  if (method === 'capture_preview_bind' || method === 'parse_preview_bind') return Promise.resolve({gesture: 'Ctrl+F8', error: null});
  if (method === 'get_preview_crop_state' || method === 'alert_bookmarks') return Promise.resolve(null);
  throw new Error('Unexpected bridge call ' + method);
};
vm.runInContext(fs.readFileSync(web + '/previews.js', 'utf8'), context);
vm.runInContext(fs.readFileSync(web + '/panel.js', 'utf8'), context);
function payload() {
  return {enabled: true, characters: ['Alice'], roster: ['Alice', 'Bob'],
    hotkeys: {characters: {}, groups: [
      {id: 'g', name: 'Fleet', members: ['Alice'], cycle: 'Ctrl+F2', cycle_prev: 'Ctrl+F3'},
      {id: 'g:prev', name: 'All back', members: [], cycle: 'Ctrl+F4'},
    ]},
    label_markers: {}, marker_choices: data.choices, registration: {},
    bookmark_chords: {active: [], latent: []}, locked: [], excluded: [], never_minimize: [],
    sizes: {}, client_sizes: {}, sizable: [], layout_sources: [],
    crops: {revision: 1, definitions: {}, operations: {}, statuses: {}, cap: 8, live_count: 0, runtime_enabled: true}};
}
function row(label) {
  const lab = Array.from(document.querySelectorAll('#preview-binds .lab')).find(el => el.title === label);
  assert.ok(lab, 'rendered bind row ' + label);
  return lab.parentNode;
}
const bind = label => row(label).querySelector('.bindbtn');
const action = (label, text) => Array.from(row(label).querySelectorAll('button')).find(el => el.textContent === text);
const gpanel = id => {
  const p = document.querySelector('#preview-cycle-groups .cycle-group-panel[data-group-id="' + id + '"]');
  assert.ok(p, 'cycle group panel ' + id);
  return p;
};
const grow = (id, dir) => {
  const lab = Array.from(gpanel(id).querySelectorAll('.lab')).find(el => el.title === dir);
  assert.ok(lab, 'group chord row ' + id + ' ' + dir);
  return lab.parentNode;
};
const gbind = (id, dir) => grow(id, dir).querySelector('.bindbtn');
const gaction = (id, dir, text) => Array.from(grow(id, dir).querySelectorAll('button')).find(el => el.textContent === text);
const warning = owner => document.getElementById('preview-bind-conflict-' + encodeURIComponent(owner));
function push(p) { window.onPreviewHotkeys(clone(p)); }
function key(key, code = key) { document.dispatchEvent({type: 'keydown', key, code, ctrlKey: true}); }
function settle(p, applied = true) {
  writes.at(-1).resolve({applied, persisted: applied, error: applied ? null : 'Disk refused', hotkeys: clone(p.hotkeys)});
}
(async () => {
  if (data.scenario === 'focus-fixture-unhydrated') {
    assert.equal(document.querySelector('.group-add-name'), null, 'live getter is still pending');
    const fixture = {kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: payload(), crops: {...payload().crops, definitions: {Alice: {}}}};
    window.WM.previewCropScreenshot(fixture);
    document.querySelector('.group-add-name').value = 'FAKE before hydration';
    getters.shift()(payload()); await tick();
    window.WM.previewCropScreenshot(null);
    assert.equal(document.querySelector('.group-add-name').value, '', 'no live draft means empty, never outgoing fake text');
    assert.equal(writes.length, 0);
    return console.log('PASS group backward ' + data.scenario);
  }
  getters.shift()(payload()); await tick();
  const scenario = data.scenario;
  if (scenario === 'dev') {
    const source = fs.readFileSync(web + '/dev.js', 'utf8');
    const start = source.indexOf('  var DEV_PREVIEW_HOTKEYS_FIXTURE = ');
    const end = source.indexOf('\n  };', start) + 5;
    const api = {}, timers = [], published = [];
    const dev = {api, Promise, console, setTimeout: fn => timers.push(fn),
      window: {onPreviewHotkeys: p => published.push(p)}, _devCropCopy: () => ({})};
    vm.createContext(dev);
    vm.runInContext(source.slice(start, end), dev);
    // The reworked hotkeys fixture no longer carries the saved-layout keys
    // its own layout slice reads at load; seed the minimum here so this
    // scenario can reach the cycle-group stubs below it.
    vm.runInContext('DEV_PREVIEW_HOTKEYS_FIXTURE.layout_state = {excluded: []};'
      + 'DEV_PREVIEW_HOTKEYS_FIXTURE.sizes = {}; DEV_PREVIEW_HOTKEYS_FIXTURE.sizable = [];'
      + 'DEV_PREVIEW_HOTKEYS_FIXTURE.client_sizes = {}; DEV_PREVIEW_HOTKEYS_FIXTURE.geometry_revision = 0;', dev);
    vm.runInContext(source.slice(source.indexOf('  // Saved layout browser fixtures'),
      source.indexOf('  // Companions are browser-only fixtures')), dev);
    vm.runInContext(source.slice(source.indexOf('  var _devPreviewHotkeys ='), source.indexOf('  api.list_rows =')), dev);
    assert.equal(typeof api.set_preview_cycle_group_prev_bind, 'function', 'dev back bridge exists');
    const created = await api.create_preview_cycle_group('Backward test');
    const g = created.hotkeys.groups.at(-1);
    assert.equal(g.cycle_prev, '', 'new dev group back is unset');
    assert.equal(g.cycle, '');
    await api.set_preview_cycle_group_bind(g.id, 'Ctrl+F2');
    const result = await api.set_preview_cycle_group_prev_bind(g.id, 'Ctrl+F3');
    assert.deepEqual(clone(result.hotkeys.groups.at(-1)), {id: g.id, name: 'Backward test', members: [], cycle: 'Ctrl+F2', cycle_prev: 'Ctrl+F3'});
    assert.equal((await api.set_preview_cycle_group_prev_bind('stale', 'Ctrl+F4')).applied, false);
    assert.equal((await api.set_preview_cycle_group_prev_bind(g.id, '')).hotkeys.groups.at(-1).cycle_prev, '');
    while (timers.length) timers.shift()();
    assert.ok(published.length);
  } else if (scenario === 'focus-draft') {
    window.WM.openSettingsSection('previews', 'characters');
    getters.shift()(payload()); await tick();
    const manager = document.querySelector('.preview-group-manager');
    manager.open = true; manager.dispatchEvent({type: 'toggle'});
    const field = document.querySelector('.group-add-name');
    field.focus(); field.value = 'Unsubmitted fleet'; field.setSelectionRange(2, 11, 'backward');
    assert.ok(document.activeElement === field, 'real owning field before push');
    const p = payload(); p.hotkeys.groups.reverse(); push(p);
    const fresh = document.querySelector('.group-add-name');
    assert.ok(document.activeElement === fresh, 'ordinary push retains Add-name focus');
    assert.equal(fresh.value, 'Unsubmitted fleet', 'ordinary push does not submit or erase text');
    const label = document.querySelector('.preview-group-manager').querySelector('label');
    assert.ok(label && label.textContent, 'the typed group name retains a visible label');
    assert.equal(label.getAttribute('for'), fresh.id, 'label follows the rebuilt input');
    assert.match(label.textContent, /group.*name/i);
    assert.deepEqual([fresh.selectionStart, fresh.selectionEnd, fresh.selectionDirection], [2, 11, 'backward']);
    assert.equal(writes.length, 0);
  } else if (scenario.startsWith('focus-')) {
    const manager = () => document.querySelector('.preview-group-manager');
    const name = () => document.querySelector('.group-add-name');
    async function open() {
      window.WM.openSettingsSection('previews', 'characters');
      while (getters.length) getters.shift()(payload());
      await tick(); push(payload()); name().value = '';
      manager().open = true; manager().dispatchEvent({type: 'toggle'});
    }
    async function mutation(operation) {
      if (operation === 'add') {
        name().focus(); name().value = 'Added fleet';
        name().dispatchEvent({type: 'keydown', key: 'Enter'});
      } else {
        const button = manager().querySelector(operation === 'delete' ? '.group-delete-btn' : '.group-rename-btn');
        button.focus(); button.click(); await tick();
        if (operation === 'rename') document.getElementById('dlg-input').value = 'Renamed fleet';
        document.getElementById('dlg-ok').click(); await tick();
      }
      assert.ok(name().disabled, 'groupBusy prevents concurrent lifecycle writes');
      return writes.at(-1);
    }
    if (scenario === 'focus-own-dialog' || scenario === 'focus-dialog-owners') {
      for (const operation of ['delete', 'rename']) for (const order of ['receipt-first', 'push-first']) for (const outcome of ['applied', 'refused', 'cancel']) {
        const owners = scenario === 'focus-own-dialog' ? ['own'] : ['field', 'blurred-field', 'pointer', 'tab', 'section', 'route', 'closed', 'hidden', 'capture', 'queued-dialog', 'post-fallback-focus'];
        for (const owner of owners) {
          await open(); const count = writes.length;
          const selector = operation === 'delete' ? '.group-delete-btn' : '.group-rename-btn';
          const button = manager().querySelector(selector); const id = button.getAttribute('data-group-id');
          button.focus(); button.click(); await tick();
          assert.ok(!document.getElementById('overlay').hidden, 'real panel dialog is open');
          const during = payload(); during.hotkeys.groups.reverse(); push(during);
          assert.ok(!document.contains(button), 'ordinary push detaches original dialog trigger');
          if (operation === 'rename') document.getElementById('dlg-input').value = 'Renamed fleet';
          if (owner === 'field' || owner === 'blurred-field') {
            document.getElementById('preview-enabled').focus();
            if (owner === 'blurred-field') document.getElementById('preview-enabled').blur();
          }
          if (owner === 'pointer') document.dispatchEvent({type: 'pointerdown', target: document.getElementById('preview-enabled')});
          if (owner === 'tab') window.WM.settingsTab('previews', 'windows');
          if (owner === 'section') window.WM.section('general');
          if (owner === 'route') window.WM.route('main');
          if (owner === 'closed') { manager().open = false; manager().dispatchEvent({type: 'toggle'}); }
          if (owner === 'hidden') document.getElementById('settings-previews-characters').hidden = true;
          if (owner === 'capture') { gbind('g', 'Back').click(); await tick(); }
          if (owner === 'queued-dialog') window.WM.prompt('Newer dialog', 'Own this focus', 'newer');
          const answer = document.getElementById(outcome === 'cancel' ? 'dlg-cancel' : 'dlg-ok');
          const newerFocus = () => document.getElementById('preview-enabled').focus();
          if (owner === 'post-fallback-focus') answer.addEventListener('click', newerFocus);
          answer.click(); answer.removeEventListener('click', newerFocus); await tick();
          const afterDialog = document.activeElement;
          const departed = ['tab', 'section', 'route', 'capture'].includes(owner);
          if (outcome !== 'cancel' && !departed) {
            assert.equal(writes.length, count + 1);
            const p = payload(); const applied = outcome === 'applied';
            if (applied && operation === 'delete') p.hotkeys.groups.shift();
            if (applied && operation === 'rename') p.hotkeys.groups[0].name = 'Renamed fleet';
            if (order === 'push-first') push(p);
            writes.at(-1).resolve({applied, persisted: applied, error: applied ? null : 'Disk refused', hotkeys: clone(p.hotkeys)}); await tick();
            if (order === 'receipt-first') push(p);
          } else assert.equal(writes.length, count, 'cancel or superseded dialog never mutates');
          if (owner === 'own') {
            if (outcome === 'cancel') {
              assert.equal(document.activeElement.getAttribute('data-group-id'), id, 'cancel restores stable group, not row index');
              assert.ok(document.activeElement.matches(selector));
            } else assert.ok(document.activeElement === name(), operation + '/' + order + '/' + outcome + ' recovers Add after own dialog push');
          } else {
            assert.ok(document.activeElement !== name(), owner + ' revokes own-dialog recovery');
            if (owner === 'queued-dialog') assert.ok(document.activeElement === afterDialog, 'queued dialog retains actual focus');
            if (owner === 'post-fallback-focus') assert.equal(document.activeElement.id, 'preview-enabled', 'real focus after panel fallback supersedes dialog recovery');
          }
          if (!document.getElementById('overlay').hidden) { document.getElementById('dlg-cancel').click(); await tick(); }
          if (document.querySelector('.capturing')) { key('Escape'); await tick(); }
          document.getElementById('settings-previews-characters').hidden = false;
        }
      }
    } else if (scenario === 'focus-fixture-draft') {
      for (const buffered of [false, true]) for (const replacement of [false, true]) {
        await open(); name().focus(); name().value = 'REAL unsent fleet'; name().setSelectionRange(2, 11, 'backward');
        const fixture = {kind: 'preview-crop-screenshot-v1', owner: 'Alice', preview: payload(), crops: {...payload().crops, definitions: {Alice: {}}}};
        window.WM.previewCropScreenshot(fixture);
        assert.equal(name().value, '', 'fixture must not expose the live unsent draft');
        name().focus(); name().value = 'FAKE screenshot fleet'; name().setSelectionRange(1, 5, 'forward');
        if (buffered) { const p = payload(); p.roster.push('Latest live pilot'); push(p); }
        if (replacement) {
          window.WM.previewCropScreenshot(fixture);
          assert.equal(name().value, '', 'replacement starts a fresh local draft');
          name().focus(); name().value = 'REPLACEMENT fake';
        }
        window.WM.previewCropScreenshot(null);
        assert.equal(name().value, 'REAL unsent fleet', 'cleanup restores live rather than fixture text');
        assert.deepEqual([name().selectionStart, name().selectionEnd, name().selectionDirection], [2, 11, 'backward']);
        assert.ok(document.activeElement !== name(), 'fixture cleanup cannot revive manager focus');
        assert.equal(!!document.querySelector('[data-preview-configure="Latest live pilot"]'), buffered, 'latest live roster survives staging/replacement');
        assert.equal(writes.length, 0, 'drafts and fixtures never submit');
      }
    } else if (scenario === 'focus-crop-direction') {
      await open(); let revision = 10;
      for (const direction of ['backward', 'forward']) for (const added of [true, false]) {
        name().focus(); name().value = 'Unsubmitted fleet'; name().setSelectionRange(2, 11, direction);
        const crops = {...payload().crops, revision: revision++, definitions: added ? {'Crop-only pilot': {}} : {}};
        window.onPreviewCrops(crops);
        assert.ok(document.activeElement === name(), 'crop roster redraw retains owning Add focus');
        assert.equal(name().value, 'Unsubmitted fleet');
        assert.deepEqual([name().selectionStart, name().selectionEnd, name().selectionDirection], [2, 11, direction], 'real crop delivery retains selection direction');
        assert.equal(!!document.querySelector('[data-preview-configure="Crop-only pilot"]'), added);
        if (!added) { await open(); }
      }
      const other = document.getElementById('preview-enabled'); other.focus();
      window.onPreviewCrops({...payload().crops, revision: 20, definitions: {'Another crop pilot': {}}});
      assert.ok(document.activeElement === other, 'crop render must not overwrite newer focus');
      assert.equal(writes.length, 0);
    } else if (scenario === 'focus-lifecycle') {
      for (const operation of ['delete', 'rename', 'add']) for (const order of ['receipt-first', 'push-first']) for (const applied of [true, false]) {
        await open(); const request = await mutation(operation); const p = payload();
        if (applied && operation === 'delete') p.hotkeys.groups.shift();
        if (applied && operation === 'rename') p.hotkeys.groups[0].name = 'Renamed fleet';
        if (applied && operation === 'add') p.hotkeys.groups.push({id: 'new', name: 'Added fleet', cycle: '', cycle_prev: ''});
        if (order === 'push-first') push(p);
        request.resolve({applied, persisted: applied, error: applied ? null : 'Disk refused', hotkeys: clone(p.hotkeys)}); await tick();
        assert.ok(document.activeElement === name(), operation + '/' + order + ' receipt focuses Add-name');
        assert.equal(name().value, '', 'explicit Add attempt keeps existing cleared-field semantics');
        name().value = 'Next draft'; name().setSelectionRange(1, 4, 'forward');
        push(p);
        assert.ok(document.activeElement === name(), operation + '/' + order + ' subsequent push retains focus');
        assert.equal(name().value, 'Next draft');
        assert.deepEqual([name().selectionStart, name().selectionEnd, name().selectionDirection], [1, 4, 'forward']);
        assert.ok(!name().disabled);
      }
    } else if (scenario === 'focus-ownership') {
      for (const owner of ['field', 'blurred-field', 'summary', 'dialog', 'tab', 'section', 'route', 'closed', 'hidden']) {
        await open(); const request = await mutation('delete');
        let target;
        if (owner === 'field' || owner === 'blurred-field') {
          target = document.getElementById('preview-enabled'); target.focus();
          if (owner === 'blurred-field') { target.blur(); target = document.body; }
        }
        if (owner === 'summary') { target = manager().querySelector('summary'); target.focus(); }
        if (owner === 'dialog') { window.WM.prompt('Newer dialog', 'Keep my focus', 'draft'); await tick(); target = document.getElementById('dlg-input'); }
        if (owner === 'tab') window.WM.settingsTab('previews', 'windows');
        if (owner === 'section') window.WM.section('general');
        if (owner === 'route') window.WM.route('main');
        if (owner === 'closed') { manager().open = false; manager().dispatchEvent({type: 'toggle'}); }
        if (owner === 'hidden') document.getElementById('settings-previews-characters').hidden = true;
        target ||= document.activeElement;
        const p = payload(); p.hotkeys.groups.shift(); push(p);
        request.resolve({applied: true, persisted: true, error: null, hotkeys: clone(p.hotkeys)}); await tick();
        if (owner === 'summary') assert.ok(document.activeElement === manager().querySelector('summary'), 'newer summary keeps logical focus');
        else assert.ok(document.activeElement === target, owner + ' supersedes old mutation focus');
        if (owner === 'dialog') { document.getElementById('dlg-cancel').click(); await tick(); }
        document.getElementById('settings-previews-characters').hidden = false;
      }
    } else if (scenario === 'focus-stable') {
      await open();
      let button = manager().querySelectorAll('.group-delete-btn')[1]; button.focus();
      const p = payload(); p.hotkeys.groups.reverse(); p.hotkeys.groups[0].name = 'Renamed elsewhere'; push(p);
      assert.equal(document.activeElement.getAttribute('data-group-id'), 'g:prev', 'reordering retains group identity, never row index');
      assert.ok(document.activeElement.classList.contains('group-delete-btn'));
      p.hotkeys.groups.shift(); push(p);
      assert.ok(document.activeElement === name(), 'removed focused group falls back to Add');
      name().value = 'G1 draft'; name().setSelectionRange(2, 5, 'backward');
      gbind('g', 'Back').focus(); gbind('g', 'Back').click(); await tick(); push(p);
      assert.ok(document.querySelector('.capturing'), 'ordinary push never steals armed capture');
      key('Escape'); await tick();
      assert.ok(document.activeElement !== name(), 'capture cancellation does not resurrect manager focus');
      assert.equal(name().value, 'G1 draft');
      assert.equal(writes.length, 0);
    }
  } else if (scenario === 'rows') {
    // Group chords live in the Cycle groups card now; the bind table
    // renders character rows only -- running first, then the roster.
    const labels = Array.from(document.querySelectorAll('#preview-binds .lab')).map(el => el.title);
    assert.deepEqual(labels, ['Alice', 'Bob']);
    assert.equal(gbind('g:prev', 'Back').textContent, 'Not set', 'legacy group missing field');
    assert.equal(gaction('g:prev', 'Back', 'Clear'), undefined);
    assert.ok(gaction('g:prev', 'Back', 'Edit…'));
    assert.equal(document.querySelector('[data-preview-configure="Alice"]').parentNode.children.length, 5);
    const p = payload(); p.hotkeys.groups = []; push(p);
    assert.equal(document.querySelectorAll('#preview-binds .bindbtn').length, 2, 'groups come and go; every known character keeps its row');
  } else if (scenario === 'conflicts') {
    const p = payload(); const chord = 'Ctrl+F3';
    p.hotkeys.groups[1].cycle = chord;
    p.hotkeys.groups[1].cycle_prev = chord;
    p.registration[chord] = true; push(p);
    for (const owner of ['group-prev:g', 'group:g:prev', 'group-prev:g:prev']) {
      assert.ok(warning(owner), 'disjoint arbitrary group IDs ' + owner);
      assert.match(warning(owner).textContent, /cycle group All back forward takes priority/);
      assert.equal(warning(owner).parentNode.querySelector('.bindbtn').getAttribute('aria-describedby'), warning(owner).id);
    }
    p.hotkeys.characters.Alice = chord; push(p);
    assert.match(warning('group-prev:g').textContent, /Character focus takes priority/);
    const lone = payload(); lone.bookmark_chords.active = [chord]; push(lone);
    assert.match(warning('group-prev:g').textContent, /configured EVE bookmark keybind/);
    lone.bookmark_chords.active = []; lone.registration[chord] = false; push(lone);
    assert.match(warning('group-prev:g').textContent, /owned by another application/);
    lone.registration = {}; push(lone);
    assert.equal(warning('group-prev:g'), null);
    assert.ok(gbind('g', 'Back').classList.contains('unknown'));
    for (const known of [undefined, false, true]) {
      lone.registration = known === undefined ? {} : {[chord]: known}; push(lone);
      const button = gbind('g', 'Back');
      assert.equal(button.textContent, chord, 'accessible name keeps full chord');
      assert.ok(button.title.includes(chord), 'ellipsized cycle chord remains in tooltip');
      if (known === undefined) assert.match(button.title, /Not registered right now/);
      if (known === false) assert.match(button.title, /Another application already owns/);
    }
  } else if (scenario === 'writes') {
    for (const [dir, endpoint, field] of [['Forward', 'set_preview_cycle_group_bind', 'cycle'], ['Back', 'set_preview_cycle_group_prev_bind', 'cycle_prev']]) {
      const p = payload(); push(p);
      gbind('g', dir).click(); await tick(); key('F8'); await tick();
      assert.deepEqual([writes.at(-1).method, ...writes.at(-1).args], [endpoint, 'g', 'Ctrl+F8']);
      assert.ok(gbind('g', 'Forward').disabled && gbind('g', 'Back').disabled);
      p.hotkeys.groups[0][field] = 'Ctrl+F8'; settle(p); await tick();
      assert.equal(gbind('g', dir).textContent, 'Ctrl+F8');
      gaction('g', dir, 'Clear').click(); assert.deepEqual(writes.at(-1).args, ['g', '']);
      settle(p, false); await tick(); assert.equal(gbind('g', dir).textContent, 'Ctrl+F8');
      assert.ok(!gbind('g', dir).disabled);
      gaction('g', dir, 'Edit…').click(); await tick();
      const input = document.getElementById('dlg-input'); input.value = 'Ctrl+F8';
      document.getElementById('dlg-ok').click(); await tick();
      assert.equal(writes.at(-1).method, endpoint); settle(p); await tick();
      gaction('g', dir, 'Clear').click(); p.hotkeys.groups[0][field] = ''; settle(p); await tick();
      assert.equal(gbind('g', dir).textContent, 'Not set');
    }
  } else if (scenario === 'stale') {
    const p = payload(); gaction('g', 'Back', 'Clear').click();
    p.hotkeys.groups[0].name = 'New name'; p.hotkeys.groups[0].cycle_prev = 'Ctrl+F9'; push(p);
    settle(payload()); await tick();
    assert.equal(gpanel('g').querySelector('.cycle-group-name').textContent, 'New name');
    assert.equal(gbind('g', 'Back').textContent, 'Ctrl+F9');
    assert.equal(gbind('g', 'Back').disabled, false);
    gaction('g', 'Back', 'Clear').click();
    const deleted = payload(); deleted.hotkeys.groups = []; push(deleted);
    settle(p); await tick(); assert.equal(document.querySelectorAll('#preview-cycle-groups .cycle-group-panel').length, 0);
  } else if (scenario === 'cancel') {
    for (const destination of ['Escape', 'dialog', 'tab', 'section']) {
      push(payload()); gbind('g', 'Back').click(); await tick();
      assert.ok(document.querySelector('.capturing'));
      if (destination === 'Escape') key('Escape');
      if (destination === 'dialog') gaction('g', 'Forward', 'Edit…').click();
      if (destination === 'tab') document.dispatchEvent({type: 'wm:settings-tab', detail: {section: 'previews', tab: 'windows'}});
      if (destination === 'section') document.dispatchEvent({type: 'wm:section', detail: 'general'});
      await tick(); assert.equal(document.querySelector('.capturing'), null);
      if (destination === 'dialog') { key('Escape'); await tick(); }
      window.onPreviewBindCaptured({gesture: 'Ctrl+F8'}); await tick();
      assert.equal(writes.length, 0, 'cancelled captures cannot write');
    }
  } else if (scenario === 'marker') {
    document.querySelector('[data-preview-configure="Alice"]').click();
    const marker = document.querySelector('[data-preview-detail-control="marker"]');
    gbind('g', 'Back').click(); await tick();
    const p = payload(); p.roster.push('New pilot'); push(p);
    assert.equal(document.querySelector('[data-preview-configure="New pilot"]'), null);
    marker.dispatchEvent({type: 'mousedown'});
    assert.equal(document.querySelector('.capturing'), null);
    assert.equal(document.querySelector('[data-preview-detail-control="marker"]'), marker, 'original select survives first native entry');
    assert.ok(document.contains(marker));
    assert.ok(document.querySelector('[data-preview-configure="New pilot"]'));
    window.onPreviewBindCaptured({gesture: 'Ctrl+F8'}); await tick(); assert.equal(writes.length, 0);
  } else throw new Error('Unknown scenario ' + scenario);
  console.log('PASS group backward ' + scenario);
})().catch(error => { console.error(error); process.exitCode = 1; });
