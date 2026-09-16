// Executes generated capture expressions and whole production modules against
// real markup ancestry. Only DOM mechanics and external delivery are doubled.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const {createDOM} = require('./screenshot_dom.cjs');
const {document, Element, scrolls} = createDOM(data.page);
for (const [id, text] of Object.entries(data.texts || {})) document.getElementById(id).textContent = text;
const window = new Element('window');
Object.assign(window, {document, console: {...console, error: (...args) => { throw Error(args.join(' ')); }},
  navigator: {clipboard: {readText: () => assert.fail('clipboard read'), writeText: () => assert.fail('clipboard write')}},
  Promise, Math, Date, TextEncoder, URLSearchParams,
  Event: class { constructor(type) { this.type = type; } },
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
  setTimeout, clearTimeout, requestAnimationFrame: callback => setTimeout(callback, 0),
  matchMedia: () => ({matches: false}), getComputedStyle: () => ({visibility: 'visible'}), location: {search: ''}});
window.window = window;
const runtime = vm.createContext(window);
const run = expression => vm.runInContext(expression, runtime);
run(fs.readFileSync(web + '/app.js', 'utf8'));
const WM = window.WM;
const calls = [];
let staging = false;
let bridgeReply = () => null;
WM.send = (method, ...args) => {
  calls.push([method, ...args]);
  if (staging) assert.fail('Staged screen reached bridge: ' + method);
  return Promise.resolve(bridgeReply(method, ...args));
};
WM.confirm = () => { if (staging) assert.fail('Unexpected confirmation'); return Promise.resolve(false); };
const crop = data.key.startsWith('settings-');
const moduleName = data.key.startsWith('fittings-') ? 'fittings'
  : data.key.startsWith('settings-wanderer') ? 'wanderer'
  : data.key === 'profiles-copy-scope' ? 'evesettings'
  : data.key.startsWith('settings-characters') ? 'characters'
  : crop ? 'previews' : data.key.includes('formations') ? 'formations' : 'uisetup';
run(fs.readFileSync(web + '/' + moduleName + '.js', 'utf8'));
const tick = () => new Promise(resolve => setTimeout(resolve, 10));
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };
async function gapRegression() {
  const scenario = data.gap;
  const el = id => document.getElementById(id);
  const step = async text => { if (text) run(text); await tick(); };
  const profiles = moduleName === 'evesettings';
  const metadata = data.key === 'fittings-metadata-narrow';
  const preflight = data.key === 'fittings-copy-preflight-bottom-narrow';
  const wanderer = moduleName === 'wanderer';
  const state = {
    root: 'test/root', server: 'tq', profile: 'test/profile',
    servers: [{path: 'tq', name: 'Tranquility'}],
    profiles: [{path: 'test/profile', name: 'Test profile'}],
    characters: [], accounts: [], backups: [], identity_characters: [],
    unreadable: false, too_broad: false, eve_running: false,
    identification_active: false, account_identity_available: false,
    formations_available: false, backups_unreadable: false,
    selective_copy_available: !scenario.startsWith('codec-missing'),
    copy_groups: {characters: [{id: 'windows', label: 'Window layout', default_on: true}], accounts: []}
  };
  bridgeReply = method => {
    if (profiles) {
      assert.ok(['eve_settings_state', 'eve_settings_resolve_names'].includes(method));
      if (method === 'eve_settings_state') return scenario === 'unresolved'
        ? new Promise(() => {}) : state;
    }
    return null;
  };
  for (let iteration = 0; iteration < 2; iteration++) {
    staging = false;
    if (wanderer) {
      await step(data.prepare);
      staging = true; WM.openSettingsSection('previews');
    } else WM.route(profiles ? 'evesettings' : 'fittings');
    await tick(); calls.length = 0; staging = true;
    if (moduleName === 'fittings') { await step(data.fixture); await step(data.reset); }
    const nativePromise = window.Promise;
    if ((metadata || preflight) && scenario === 'unresolved') window.Promise = {resolve: () => new Promise(() => {})};
    if (data.stage) run(data.stage);
    window.Promise = nativePromise;
    await tick();
    assert.ok(data.verify, 'every added frame needs a settled-content postcondition');
    const verify = () => run(data.verify);
    if (scenario === 'unresolved') {
      assert.throws(verify, /Screenshot content did not settle/);
      assert.equal(calls.length, 0);
      if (data.cleanup) run(data.cleanup);
      return console.log('PASS screenshot gap ' + data.key + ' unresolved');
    }
    let anchor, pane, target;
    if (wanderer) {
      anchor = el('wanderer-save-note'); pane = el('settings-previews-wanderer'); target = el('wanderer-remove');
      assert.equal(el('wanderer-token').value, '');
      assert.equal(el('wanderer-token').type, 'password');
      assert.equal(el('wanderer-test').disabled, false);
      assert.equal(el('wanderer-remove').disabled, false);
      assert.equal(el('wanderer-save-note').textContent,
        'Test connection saves the map URL and token, then checks access. It does not turn names on.');
    } else if (profiles) {
      anchor = target = el('es-copy-scope-note'); pane = el('es-work');
      assert.equal(el('es-copy-scope').hidden, !state.selective_copy_available);
      assert.equal(target.classList.contains('warn'), !state.selective_copy_available);
      assert.equal(target.textContent, state.selective_copy_available
        ? 'Checked groups are copied as a unit. Unchecked groups stay unchanged. Everything else is copied.'
        : 'Selective groups unavailable — the bundled settings codec is missing. Copy will replace the whole settings file for each selected target. Reinstall Wingman from its installer to restore the codec.');
    } else if (metadata) {
      anchor = document.querySelector('.fit-metadata-disclosure'); pane = el('fittings-list');
      target = el('fit-metadata-save-fit-rifter-solo');
      assert.ok(anchor, 'the real detail must settle before late disclosure framing');
      if (!iteration) assert.ok(!anchor.open, 'the initial detail is read-first');
      assert.equal(el('fit-name-fit-rifter-solo').value, 'Rifter - Solo PvP');
      assert.equal(el('fit-desc-fit-rifter-solo').value, 'Fast tackle, disengages on a scram.');
      assert.equal(el('fit-metadata-discard-fit-rifter-solo').hidden, true, 'capture must not create a draft');
    } else if (preflight) {
      anchor = target = el('fittings-copy-resolution-note'); pane = el('fittings-copy-body');
      assert.ok(anchor, 'real preflight reply must settle before lower framing');
      assert.equal(anchor.textContent, 'Enter an alternate name or select Skip for each conflict before reviewing changes.');
      assert.equal(pane.querySelector('.fit-copy-summary').nextSibling.textContent,
        'Copies only add fittings; existing fittings are kept.');
      assert.equal(el('fittings-copy-review').disabled, true);
      assert.equal(document.querySelectorAll('.fit-copy-pair').length, 3);
    } else {
      pane = el('fittings-copy-body'); anchor = pane.querySelectorAll('.fit-copy-pair').at(-1);
      target = anchor.querySelector('.fit-copy-result');
      assert.equal(anchor.querySelector('.fit-copy-pair-name').textContent, 'Generated Fit 003 (Merlin)');
      assert.equal(anchor.querySelector('.fit-copy-character').textContent, 'Gio Renn');
      assert.equal(target.textContent, 'Not attempted: rate limit');
      assert.equal(anchor.querySelector('.fit-copy-detail'), null, 'unattempted row has no invented error or repeated guidance');
      const recovery = pane.querySelector('.fit-copy-recovery');
      assert.ok(recovery && recovery.parentNode === pane);
      assert.equal(recovery.children.length, 2);
      assert.match(recovery.children[0].textContent, /before any retry/i);
      assert.match(recovery.children[1].textContent, /Rate limit:.*fittings not attempted/);
      assert.equal(el('fittings-copy-close').disabled, false);
    }
    // Layout boundary inputs only: this harness does not render CSS. Nodes
    // enter the pane only when the generated script frames the settled anchor.
    window.innerWidth = 840; window.innerHeight = 625;
    let framed = false, overrun = 0, edge = 'bottom', covered = false, zero = false;
    const rect = (left, top, right, bottom) => ({left, top, right, bottom, width: right-left, height: bottom-top});
    const recordScroll = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (options) {
      recordScroll.call(this, options);
      if (this === anchor) framed = true;
    };
    const nativeRect = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function () {
      if (this === pane) return rect(100, 100, 800, 540);
      if (!framed) return rect(120, 700, 760, 730);
      const r = rect(120, 130, zero && this === target ? 120 : 760, 330);
      if (this === target && overrun) {
        r[edge] = {left: 100, top: 100, right: 800, bottom: 540}[edge]
          + (['top', 'left'].includes(edge) ? -overrun : overrun);
        r.width = r.right - r.left; r.height = r.bottom - r.top;
      }
      return r;
    };
    const nativeRects = Element.prototype.getClientRects;
    Element.prototype.getClientRects = function () {
      for (let node = this; node; node = node.parentNode) {
        if (node.hidden) return [];
        if (node.parentNode?.tagName === 'DETAILS' && !node.parentNode.open && node.tagName !== 'SUMMARY') return [];
      }
      return [this.getBoundingClientRect()];
    };
    // Each hit-test point belongs to the last measured node unless another
    // surface covers it. This isolates the generated guard, not CSS hit testing.
    let measured;
    const box = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function () { measured = this; return box.call(this); };
    document.elementFromPoint = () => covered ? document.body : measured;
    verify();
    assert.ok(framed, 'must frame the semantic anchor, not just click a control');
    assert.equal(scrolls.at(-1).element, anchor);
    assert.equal(scrolls.at(-1).options.behavior, 'instant');
    if (metadata) {
      assert.equal(anchor.open, true);
      assert.equal(el('fit-metadata-discard-fit-rifter-solo').hidden, true);
      assert.equal(el('fit-name-fit-rifter-solo').value, 'Rifter - Solo PvP');
    }
    const targetParent = target.parentNode, targetNext = target.nextSibling;
    if (scenario === 'missing') target.remove();
    else if (scenario === 'hidden') target.hidden = true;
    else if (scenario === 'wrong-text') target.textContent = 'stale or incomplete content';
    else if (scenario.endsWith('clipped')) overrun = 2;
    else if (/^(rounding|edge|overflow)-/.test(scenario)) {
      edge = scenario.split('-')[1];
      overrun = scenario.startsWith('rounding') ? 0.109375 : scenario.startsWith('edge') ? 1 : 1.01;
    } else if (scenario === 'covered-rounding') { overrun = 0.109375; covered = true; }
    else if (scenario === 'covered') covered = true;
    else if (scenario === 'zero-area') zero = true;
    else if (scenario === 'wrong-name') el('fit-name-fit-rifter-solo').value = 'Wrong fitting';
    else if (scenario === 'wrong-description') el('fit-desc-fit-rifter-solo').value = 'Wrong description';
    else if (scenario === 'missing-rack') document.querySelector('.fit-rack').remove();
    else if (scenario === 'redundant-alias') document.querySelector('.fit-aliases').appendChild(
      WM.make('p', 'fit-alias-row', 'Rifter - Solo PvP'));
    else if (scenario === 'missing-reassurance') pane.querySelector('.fit-copy-summary').nextSibling.remove();
    else if (scenario === 'inconsistent-capability') el('es-copy-scope-note').classList.add('warn');
    else if (scenario === 'wrong-pair') document.querySelector('.fit-copy-pair-name').textContent = 'Wrong fitting';
    else if (scenario === 'wrong-summary') document.querySelector('.fit-copy-summary').textContent = '6 copied · 0 failed';
    else if (scenario === 'missing-recovery') pane.querySelectorAll('.fit-copy-guidance')
      .find(node => /Rate limit:/.test(node.textContent)).remove();
    else if (scenario === 'hidden-recovery') pane.querySelectorAll('.fit-copy-guidance')
      .find(node => /before any retry/i.test(node.textContent)).hidden = true;
    else if (scenario === 'clipped-recovery') {
      target = pane.querySelector('.fit-copy-guidance'); overrun = 2;
    } else if (scenario === 'reversed-recovery') {
      const group = pane.querySelector('.fit-copy-recovery');
      group.insertBefore(group.children[1], group.children[0]);
    }
    if (scenario.startsWith('rounding-') || scenario.startsWith('edge-')) verify();
    else if (!['settled', 'codec-missing'].includes(scenario)) assert.throws(verify, /Screenshot content did not settle/, scenario);
    assert.equal(calls.length, 0, 'new staging/verification must not write, copy, Test, or use the clipboard');
    // Restore deliberate test damage before the real owner's cleanup paints.
    if (scenario === 'missing') targetParent.insertBefore(target, targetNext);
    Element.prototype.scrollIntoView = recordScroll;
    Element.prototype.getBoundingClientRect = nativeRect;
    Element.prototype.getClientRects = nativeRects;
    if (data.cleanup) await step(data.cleanup);
    assert.equal(calls.length, 0, 'fixture cleanup stays local');
    if (!['settled', 'codec-missing'].includes(scenario)) break;
  }
  console.log('PASS screenshot gap ' + data.key + ' ' + scenario);
}
async function cropRegression() {
  const scenario = data.regression;
  const fixture = data.crop_fixture;
  const owner = fixture.owner;
  const live = JSON.parse(JSON.stringify(fixture.preview));
  live.hotkeys.characters[owner] = 'Ctrl+Alt+9';
  live.crops = JSON.parse(JSON.stringify(fixture.crops));
  live.crops.revision = 10;
  document.activeElement = document.body;
  window.onPreviewHotkeys(live);
  document.dispatchEvent({type: 'wm:preview-minimize-inactive', detail: {enabled: true}});
  run(data.stage);
  const detail = name => document.querySelector('[data-preview-detail-control="' + name + '"]');
  const button = (selector, text) => {
    const el = document.querySelectorAll(selector).find(el => el.textContent === text);
    assert.ok(el, 'rendered ' + text); return el;
  };
  const change = (el, value) => {
    assert.ok(el, 'rendered change control'); assert.equal(el.disabled, false);
    if (el.type === 'checkbox') el.checked = !el.checked; else el.value = value;
    el.dispatchEvent({type: 'change'});
  };
  const actions = {
    // Clear a row that is NOT the owner's: the invariant under test is
    // that the write carries the RESTORED live table (owner's bind intact),
    // not the synthetic staged one. The group/All rows that used to sit
    // above the character rows are gone.
    // Clear a row that is NOT the owner's: the invariant under test is
    // that the write carries the RESTORED live table (owner's bind intact),
    // not the synthetic staged one. Character rows render online-first in
    // roster order with the owner first, so the second Clear button belongs
    // to a different character. The group/All rows that used to sit above
    // them are gone from this table.
    clear: () => {
      const clears = [...document.querySelectorAll('.rowacts button')]
        .filter(el => el.textContent === 'Clear');
      assert.ok(clears.length > 1, 'rendered character Clear controls');
      clears[1].click();
    },
    // Group chord rows live in the Cycle groups card now, one pair per
    // panel; DPS is the first panel with a forward bind.
    'group-clear': () => {
      const row = [...document.querySelectorAll('#preview-cycle-groups .row')]
        .find(row => row.querySelector('.lab-name')?.textContent === 'Forward');
      assert.ok(row, 'rendered a group forward chord row');
      const clear = row.querySelectorAll('.rowacts button').find(el => el.textContent === 'Clear');
      assert.ok(clear, 'rendered a group forward Clear control');
      clear.click();
    },
    capture: () => document.querySelector('.bindbtn').click(),
    bind: () => button('.rowacts button', 'Edit…').click(),
    size: () => detail('size').click(), copy: () => detail('copy').click(),
    exclude: () => change(document.querySelector('.optout input')),
    lock: () => change(document.querySelector('[data-preview-lock]')),
    'never-minimize': () => change(document.querySelector('.nm input')),
    // Membership moved into the Cycle groups card: assignment is the
    // group's Add select + Add button, writing the FULL member list
    // through set_preview_cycle_group_members.
    group: () => {
      const sel = document.querySelector(
        '#preview-cycle-groups .cycle-add-select[data-group-id="g-logi"]');
      assert.ok(sel, 'rendered the Logistics add-member select');
      sel.value = sel.options[0].value;
      const add = document.querySelector(
        '#preview-cycle-groups [data-group-control="add-confirm"][data-group-id="g-logi"]');
      assert.ok(add, 'rendered the Logistics Add button');
      add.click();
    },
    add: () => { document.querySelector('.group-add-name').value = 'New group'; document.querySelector('.group-add-btn').click(); },
    rename: () => document.querySelector('.group-rename-btn').click(),
    delete: () => document.querySelector('.group-delete-btn').click(),
    'crop-select': () => detail('crop-select').click(),
    'crop-remove': () => detail('crop-remove').click(),
    'crop-enabled': () => change(detail('crop-enabled')),
    reentry: () => WM.section('previews')
  };
  const expected = {
    clear: 'set_preview_binds', 'group-clear': 'set_preview_cycle_group_bind', capture: 'set_bind_capture',
    bind: 'set_preview_binds', size: 'set_preview_size', copy: 'copy_preview_layout',
    exclude: 'set_preview_excluded', lock: 'set_preview_locked', 'never-minimize': 'set_never_minimize',
    group: 'set_preview_cycle_group_members', add: 'create_preview_cycle_group', rename: 'rename_preview_cycle_group',
    delete: 'delete_preview_cycle_group', 'crop-select': 'select_preview_crop', 'crop-remove': 'remove_preview_crop',
    'crop-enabled': 'set_preview_crop_enabled', reentry: 'get_preview_hotkey_state'
  };
  if (scenario.operation) {
    // A real request has its receipt and pending getter before capture begins.
    const pending = {...live.crops, revision: 11, busy: true,
      operations: {'50': {operation_id: 50, name: owner, pending: true}}, statuses: {[owner]: 'saving'}};
    bridgeReply = method => method === 'select_preview_crop' ? {applied: true, operation_id: 50, pending: true}
      : method === 'get_preview_crop_state' ? pending : null;
    actions['crop-select'](); await tick();
    assert.match(document.querySelector('.preview-crop-status').textContent, /Saving/);
    calls.length = 0; staging = true;
    run(data.prepare); run(data.stage);
    const id = {matching: 50, newer: 51, older: 49}[scenario.operation];
    window.onPreviewCrops({...live.crops, revision: 12,
      operations: {[id]: {operation_id: id, name: owner, pending: false}}});
    run(data.cleanup); run(data.stage);
    const status = document.querySelector('.preview-crop-status').textContent;
    if (scenario.operation === 'older') assert.match(status, /Saving/, 'an older terminal ID cannot settle this request');
    else {
      assert.doesNotMatch(status, /Saving/, 'cleanup must settle the buffered terminal request without another event');
      assert.equal(detail('crop-select').disabled, false);
    }
    assert.equal(calls.length, 0);
    return;
  }
  const parsed = scenario.control === 'size' ? {w: 640, h: 360} : {gesture: 'Ctrl+Alt+8'};
  const dialogValue = {size: '640x360', bind: 'Ctrl+Alt+8', copy: 'Tanuki Solette', rename: 'Renamed'}[scenario.control] ?? true;
  const waiting = deferred();
  let dialogCalls = 0;
  for (const name of ['prompt', 'confirm', 'choose']) WM[name] = () => {
    assert.equal(staging, false, 'fixture must not open a live dialog'); dialogCalls++;
    return scenario.late === 'dialog' ? waiting.promise : Promise.resolve(dialogValue);
  };
  bridgeReply = method => method === 'get_preview_hotkey_state' ? live
    : method === 'get_preview_crop_state' ? live.crops
    : method.startsWith('parse_preview_') ? (scenario.late === 'parser' ? waiting.promise : parsed)
    : {applied: true, operation_id: null};
  if (scenario.late) {
    actions[scenario.control](); await tick();
    assert.equal(dialogCalls, 1, 'dialog began on live data');
    if (scenario.late === 'parser') assert.ok(calls.some(call => call[0].startsWith('parse_preview_')));
  }
  calls.length = 0; staging = true;
  run(data.prepare); run(data.stage);
  if (scenario.late) waiting.resolve(scenario.late === 'parser' ? parsed : dialogValue);
  else actions[scenario.control]();
  await tick();
  assert.equal(calls.length, 0, 'fixture interaction and late continuations must not reach the bridge');
  run(data.cleanup); await tick();
  assert.equal(calls.length, 0, 'cleanup must remain local');
  staging = false;
  if (!scenario.late) {
    run(data.stage); actions[scenario.control](); await tick();
    assert.ok(calls.some(call => call[0] === expected[scenario.control]), 'ordinary action resumes after cleanup');
    if (scenario.control === 'clear') {
      const table = calls.find(call => call[0] === 'set_preview_binds')[1];
      assert.equal(table.characters[owner], 'Ctrl+Alt+9', 'normal write uses restored live table, not synthetic binds');
    }
  }
}
async function fittingsDetailRegression() {
  const scenario = data.regression;
  const pendingState = deferred();
  bridgeReply = method => { assert.equal(method, 'fittings_state'); return pendingState.promise; };
  WM.route('fittings'); await tick(); calls.length = 0; staging = true;
  const step = async expression => { if (expression) run(expression); await tick(); };
  const toggle = name => document.querySelectorAll('#fittings-list .fit-row-toggle')
    .find(el => el.querySelector('.fit-name').textContent === name);
  const verify = () => { if (data.verify) run(data.verify); };
  // Start exactly where the preceding Alliance capture leaves the real page.
  await step(data.fixture); await step(data.reset);
  await step(data.previous_prepare); await step(data.previous_stage);
  assert.equal(toggle('Merlin - Fleet Doctrine').getAttribute('aria-expanded'), 'true');
  for (let iteration = 0; iteration < 2; iteration++) {
    WM.route('fittings'); await tick();
    await step(data.prepare); await step(data.fixture); await step(data.reset);
    await step(data.fittings_prepare);
    const waiting = deferred();
    const nativePromise = window.Promise;
    if (['unresolved', 'late-reset', 'late-reinject', 'late-cleanup'].includes(scenario)) {
      // Delay the fixture read's delivery, not the renderer or its handlers.
      window.Promise = {resolve: value => waiting.promise.then(() => value)};
    }
    run(data.stage); window.Promise = nativePromise;
    if (scenario === 'late-reset') run(data.reset);
    if (scenario === 'late-reinject') run(data.fixture);
    if (scenario === 'cleanup' || scenario === 'late-cleanup') {
      if (scenario === 'cleanup') await tick();
      const row = toggle('Rifter - Solo PvP').closest('.fit-row');
      if (scenario === 'late-cleanup') assert.match(row.querySelector('.fit-detail').textContent, /Loading/);
      else assert.ok(row.querySelector('.fit-metadata'), 'settled fixture has interactive detail');
      run(data.cleanup); // No caller navigation may hide a broken in-place clear.
      assert.equal(WM.current_route, 'main', 'cleanup itself leaves the synthetic workspace');
      assert.equal(WM.el('route-fittings').classList.contains('active'), false);
      const retiredList = WM.el('fittings-list').firstChild;
      waiting.resolve(); await tick();
      assert.ok(WM.el('fittings-list').firstChild === retiredList, 'late fixture detail cannot repaint after cleanup');
      assert.equal(WM.el('route-fittings').classList.contains('active'), false);
      WM.el('fittings-copy-cancel').dispatchEvent({type: 'click'});
      assert.equal(calls.length, 0, 'cleanup and delayed delivery remain bridge-free');
      break;
    }
    if (scenario !== 'unresolved') waiting.resolve();
    await tick();
    if (scenario === 'late-state') {
      pendingState.resolve({available: false, rows: [], collections: [], characters: [], filters: {}});
      await tick();
    }
    const row = toggle('Rifter - Solo PvP').closest('.fit-row');
    if (scenario === 'unresolved') assert.match(row.querySelector('.fit-detail').textContent, /Loading/);
    else if (['late-reset', 'late-reinject'].includes(scenario)) {
      assert.equal(toggle('Rifter - Solo PvP').getAttribute('aria-expanded'), 'false');
      assert.equal(row.querySelector('.fit-detail'), null, 'late detail must not undo a reset');
    } else {
      assert.equal(toggle('Rifter - Solo PvP').getAttribute('aria-expanded'), 'true');
      assert.equal(document.querySelectorAll('.fit-row.open').length, 1);
      const texts = selector => row.querySelectorAll(selector).map(el => el.textContent);
      assert.deepEqual(texts('.fit-rack-name'), ['High power', 'Medium power', 'Low power']);
      assert.deepEqual(texts('.fit-item-name'), ['150mm Light AutoCannon II', '1MN Afterburner II', 'Gyrostabilizer II']);
      assert.deepEqual(texts('.fit-alias-row'), ['Rifter Tackle Fit']);
      assert.deepEqual(texts('.fit-presence-name'), ['Aria Voss', 'Bex Talon']);
      const metadata = row.querySelector('.fit-metadata-disclosure');
      assert.ok(metadata && metadata.tagName === 'DETAILS', 'metadata editing uses native disclosure');
      assert.equal(metadata.open, false, 'staged fitting details are read-first');
      assert.ok(metadata.querySelector('summary'));
      assert.ok(metadata.contains(row.querySelector('.fit-metadata')));
      verify();
      assert.ok(scrolls.at(-1)?.element === toggle('Rifter - Solo PvP'),
        'frame the newly rendered detail row, not the stale toggle from before its reply');
      assert.equal(scrolls.at(-1).options.block, 'start');
      assert.equal(scrolls.at(-1).options.behavior, 'instant');
    }
    if (scenario === 'collapsed') toggle('Rifter - Solo PvP').click();
    else if (scenario === 'wrong-target') { toggle('Merlin - Fleet Doctrine').click(); await tick(); }
    else if (scenario.startsWith('missing-')) {
      const selector = {'missing-detail': '.fit-detail', 'missing-rack': '.fit-rack',
        'missing-alias': '.fit-alias-row', 'missing-presence': '.fit-presence-row'}[scenario];
      const missing = row.querySelector(selector); missing.parentNode.removeChild(missing);
    }
    if (['settled', 'late-state'].includes(scenario)) verify();
    else assert.throws(verify, /Screenshot content did not settle: fittings-detail/);
    assert.equal(calls.length, 0, 'all fixture actions and delayed replies remain local');
  }
  console.log('PASS screenshot fittings-detail ' + scenario);
}
async function fidelityRegression() {
  document.activeElement = document.body;
  const el = id => document.getElementById(id);
  const visible = node => {
    if (!node) return false;
    for (let child = node; child; child = child.parentNode) {
      if (child.hidden) return false;
      if (child.parentNode?.tagName === 'DETAILS' && !child.parentNode.open
          && child.tagName !== 'SUMMARY') return false;
    }
    return true;
  };
  WM.route(crop ? 'settings' : 'fittings');
  if (crop) WM.section(moduleName);
  await tick(); calls.length = 0; staging = true;
  const step = async text => { if (text) run(text); await tick(); };
  if (moduleName === 'fittings') { await step(data.fixture); await step(data.reset); }
  await step(data.stage);
  if (moduleName === 'previews') {
    const manager = document.querySelector('.preview-group-manager');
    assert.equal(manager.open, true, 'Groups capture must open Manage groups');
    assert.equal(scrolls.at(-1).element, manager, 'frame the existing disclosure, not the pane bottom');
    for (const selector of ['.group-add-name', '.group-add-btn', '.group-rename-btn', '.group-delete-btn']) {
      assert.ok(visible(manager.querySelector(selector)), 'visible group control: ' + selector);
    }
    assert.equal(manager.querySelector('.group-add-name').getAttribute('aria-label'), 'New group name');
    assert.equal(manager.querySelector('.group-add-btn').textContent, 'Add');
    assert.equal(manager.querySelector('.group-rename-btn').textContent, 'Rename…');
    assert.equal(manager.querySelector('.group-delete-btn').textContent, 'Delete');
    // Explicit layout boundary inputs, not a CSS renderer or always-hit stub.
    // The generated production guard must reject each independent failure.
    const outer = document.querySelector('.settings-pane');
    const pane = document.getElementById('settings-previews-characters');
    assert.equal(pane.hidden, false, 'Groups staging selects Characters');
    window.innerWidth = 840; window.innerHeight = 625;
    const rect = (left, top, right, bottom) => ({left, top, right, bottom, width: right-left, height: bottom-top});
    const boxes = new Map([[outer, rect(190, 44, 838, 585)],
      [pane, rect(200, 140, 828, 575)], [manager, rect(220, 150, 780, 350)]]);
    const summary = manager.querySelector('summary');
    boxes.set(summary, rect(220, 154, 780, 172));
    boxes.set(manager.querySelector('.group-add-name'), rect(220, 180, 700, 210));
    boxes.set(manager.querySelector('.group-add-btn'), rect(710, 180, 780, 210));
    manager.querySelectorAll('.group-manage-row').forEach((row, i) => {
      boxes.set(row.querySelector('.group-rename-btn'), rect(590, 220 + i*36, 690, 250 + i*36));
      boxes.set(row.querySelector('.group-delete-btn'), rect(700, 220 + i*36, 780, 250 + i*36));
    });
    for (const [node] of boxes) node.getBoundingClientRect = () => boxes.get(node);
    const hitChild = new Element('span');
    const add = manager.querySelector('.group-add-btn'); add.appendChild(hitChild);
    let obstruction = null, nullHit = false;
    document.elementFromPoint = (x, y) => {
      if (nullHit) return null;
      const inside = r => x > r.left && x < r.right && y > r.top && y < r.bottom;
      if (obstruction && inside(obstruction)) return pane;
      const hit = [...boxes].reverse().find(([node, r]) => visible(node) && inside(r));
      return hit?.[0] === add ? hitChild : hit?.[0] || null;
    };
    assert.ok(data.verify, 'a settled Groups postcondition is required'); run(data.verify);
    const geometry = data.regression?.geometry;
    if (geometry) {
      const target = geometry.includes('summary') ? summary : add;
      if (geometry === 'missing-summary') summary.remove();
      else if (geometry === 'hidden-summary') summary.hidden = true;
      else if (geometry === 'hidden-panel') {
        pane.hidden = true;
        // Leave the boundary double's boxes and hits intact: explicit hidden
        // rejection must not depend on a layout engine implementing hidden.
        pane.getClientRects = () => [boxes.get(pane)];
        document.elementFromPoint = (x, y) => [...boxes].reverse().find(([, r]) =>
          x > r.left && x < r.right && y > r.top && y < r.bottom)?.[0] || null;
      } else if (geometry === 'inside-outer-crossing-inner') {
        boxes.set(target, rect(800, 180, 830, 210));
        const r = boxes.get(target), p = boxes.get(outer);
        assert.ok(r.left > p.left && r.right < p.right && r.top > p.top && r.bottom < p.bottom);
        assert.ok(r.left < boxes.get(pane).right && r.right > boxes.get(pane).right);
      } else if (geometry === 'zero-area') boxes.set(target, rect(710, 180, 710, 210));
      else if (geometry.startsWith('pane-') || geometry.startsWith('viewport-')) {
        const viewport = geometry.startsWith('viewport-');
        if (viewport) boxes.set(pane, rect(-100, -100, 1000, 800));
        const bounds = viewport ? rect(0, 0, 840, 625) : boxes.get(pane);
        const r = {...boxes.get(target)};
        const edge = geometry.split('-')[1];
        r[edge] = bounds[edge] + (['top', 'left'].includes(edge) ? -1 : 1);
        boxes.set(target, rect(r.left, r.top, r.right, r.bottom));
      } else if (geometry === 'occluded-center') obstruction = rect(740, 190, 750, 200);
      else if (geometry === 'occluded-corner') obstruction = rect(710, 180, 716, 186);
      else if (geometry === 'null-hit') nullHit = true;
      if (geometry === 'descendant-hit') run(data.verify);
      else assert.throws(() => run(data.verify), /Screenshot content did not settle/, geometry);
      assert.equal(calls.length, 0, 'geometry verification must not click mutators');
      console.log('PASS screenshot Groups geometry ' + geometry); return;
    }
    manager.open = false;
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
    manager.open = true;
    manager.querySelector('.group-delete-btn').hidden = true;
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
  } else if (data.key === 'settings-characters-waiting') {
    const render = window.onEveAuthorityScreenshotState;
    const activity = el('characters-activity'), cancel = el('characters-cancel');
    // The generated expression must call the real renderer, not a copy-shaped
    // DOM stub. Repeat entry and reject malformed outcomes before any capture.
    for (let iteration = 0; iteration < 2; iteration++) {
      let pending;
      window.onEveAuthorityScreenshotState = payload => {
        pending = payload.authorization_activity;
        render(payload);
      };
      run(data.stage);
      assert.equal(pending, 'waiting');
      assert.equal(activity.textContent, 'Finish EVE sign-in in your browser.');
      assert.equal(el('characters-authenticate').disabled, true);
      assert.ok(visible(cancel)); assert.equal(cancel.disabled, false);
      for (const corrupt of ['idle', 'activity', 'hidden-cancel', 'disabled-cancel']) {
        window.onEveAuthorityScreenshotState = payload => {
          if (corrupt === 'idle') payload.authorization_activity = 'idle';
          render(payload);
          // Even convincing stale controls cannot substitute for pending state.
          if (corrupt === 'idle') {
            activity.textContent = 'Finish EVE sign-in in your browser.';
            cancel.hidden = false; cancel.disabled = false;
          }
          if (corrupt === 'activity') activity.textContent = '';
          if (corrupt === 'hidden-cancel') cancel.hidden = true;
          if (corrupt === 'disabled-cancel') cancel.disabled = true;
        };
        assert.throws(() => run(data.stage), /Characters (waiting state did not render|cancel control is unavailable)/, corrupt);
      }
    }
    window.onEveAuthorityScreenshotState = render;
    run(data.stage);
  } else if (moduleName === 'characters') {
    const notice = el('characters-notice');
    assert.match(notice.textContent, /Saved authorization for "Skills Only" was removed from Wingman/);
    assert.match(notice.textContent, /cleanup of local Skills\/Fittings data is incomplete/);
    assert.match(notice.textContent, /Restart Wingman to retry cleanup before authenticating this character again/);
    assert.equal(notice.classList.contains('warn'), true, 'same warning emphasis as production Forget');
    assert.ok(visible(notice));
    assert.doesNotMatch(el('characters-roster').textContent, /Skills Only/);
    assert.ok(data.verify, 'a settled cleanup postcondition is required'); run(data.verify);
    notice.classList.remove('warn');
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
  } else if (data.key === 'fittings-copy-limit') {
    const selectedIds = document.querySelectorAll('#fittings-list .fit-select input')
      .filter(node => node.checked).map(node => node.value).sort();
    assert.deepEqual(selectedIds, ['fit-gen-1', 'fit-gen-2', 'fit-gen-3', 'fit-gen-4',
      'fit-gen-5', 'fit-gen-6', 'fit-gen-7', 'fit-gen-8', 'fit-gen-9', 'fit-gen-10', 'fit-gen-11'].sort(),
      'select every intended entry exactly once, never an outside entry sharing its name');
    assert.equal(el('fittings-copy-status').textContent,
      '22 additions requested across all targets; limit 20 (2 over). Select fewer fittings or targets, then review again.');
    assert.equal(el('fittings-copy-status').classList.contains('err'), true,
      'the staged refusal must use the same error state as a live rejected review');
    assert.match(el('fittings-copy-body').textContent, /^11 selected\./,
      'refusal must be reachable with fewer than 20 selected fits across multiple targets');
    const targets = el('fittings-copy-body').querySelectorAll('input').filter(node => node.checked);
    assert.deepEqual(targets.map(node => node.closest('.fit-copy-target')
      .querySelector('label span:last-child').textContent).sort(), ['Eryn Voss', 'Fio Kest']);
    assert.ok(visible(el('fittings-copy-review')));
    assert.equal(el('fittings-copy-start').hidden, true);
    assert.ok(data.verify, 'a settled limit postcondition is required'); run(data.verify);
    el('fittings-copy-status').textContent = '';
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
    // Reducing targets permits the same selection; no selection-count shortcut.
    targets[1].checked = false; targets[1].dispatchEvent({type: 'change'});
    el('fittings-copy-review').click();
    assert.equal(el('fittings-copy-status').classList.contains('err'), false, 'checking clears stale error styling');
    await tick();
    assert.match(el('fittings-copy-body').textContent, /11 additions planned/);
    assert.equal(el('fittings-copy-status').classList.contains('err'), false);
    assert.equal(el('fittings-copy-start').hidden, false);
    el('fittings-copy-start').click(); await tick();
    assert.equal(calls.length, 0, 'even a synthetic accepted review cannot start a writer');
    el('fittings-copy-close').click();
    const lastFit = document.querySelectorAll('.fit-row')
      .find(row => row.querySelector('.fit-name').textContent === 'Generated Fit 012').querySelector('input');
    lastFit.checked = false; lastFit.dispatchEvent({type: 'change'});
    el('fittings-copy-selected').click();
    el('fittings-copy-body').querySelectorAll('.fit-copy-target').forEach(row => {
      if (['Eryn Voss', 'Fio Kest'].includes(row.querySelector('label span:last-child').textContent)) {
        const box = row.querySelector('input'); box.checked = true; box.dispatchEvent({type: 'change'});
      }
    });
    el('fittings-copy-review').click(); await tick();
    assert.match(el('fittings-copy-body').textContent, /20 additions planned/);
    assert.equal(el('fittings-copy-start').hidden, false, 'the exact additions limit remains allowed');
    el('fittings-copy-close').click();
  } else {
    const isProgress = data.key.endsWith('progress');
    assert.equal(el('fittings-copy-title').textContent, isProgress ? 'Copying fittings' : 'Copy results');
    assert.ok(visible(el('fittings-copy-overlay')));
    assert.equal(el('fittings-copy-review').hidden, true);
    assert.equal(el('fittings-copy-start').hidden, true);
    assert.equal(el('fittings-copy-cancel').hidden, !isProgress);
    assert.equal(el('fittings-copy-cancel-note').hidden, !isProgress);
    assert.equal(el('fittings-copy-close').disabled, isProgress);
    if (isProgress) {
      assert.equal(el('fittings-copy-body').textContent, '2 of 6 fitting/character checks complete');
      assert.match(el('fittings-copy-status').textContent, /Generated Fit 002 \(Merlin\).*Fio Kest: Needs verification/);
      assert.equal(el('fittings-copy-cancel').disabled, false);
      assert.ok(visible(el('fittings-copy-cancel-note')), 'cost remains visible while progress is active');
      assert.equal(el('fittings-copy-body').contains(el('fittings-copy-cancel-note')), false,
        'progress body replacement cannot discard cancellation guidance');
    } else {
      assert.match(el('fittings-copy-body').textContent, /3 additions attempted/);
      const labels = el('fittings-copy-body').querySelectorAll('.fit-copy-pair-name');
      assert.equal(labels.length, 6);
      assert.ok(labels.every(node => /\(Merlin\)/.test(node.textContent)), 'all result hull snapshots retained');
    }
    assert.ok(data.verify, 'a settled copy-state postcondition is required'); run(data.verify);
    if (isProgress) {
      el('fittings-copy-cancel').hidden = true;
      assert.throws(() => run(data.verify), /Screenshot content did not settle/);
      el('fittings-copy-cancel').hidden = false;
      if (data.regression === 'cancel') {
        el('fittings-copy-cancel').click(); await tick();
        assert.equal(el('fittings-copy-cancel').disabled, true);
        assert.match(el('fittings-copy-status').textContent, /Cancelling after the current request/);
      } else if (data.regression === 'close') {
        el('fittings-copy-close').click();
        assert.equal(el('fittings-copy-overlay').hidden, false);
      } else if (data.regression === 'start') {
        el('fittings-copy-start').dispatchEvent({type: 'click'}); await tick();
      } else if (data.regression === 'late-live') {
        window.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'unrelated-live', result: {results: []}});
        assert.equal(el('fittings-copy-title').textContent, 'Copying fittings');
      } else if (data.regression === 'teardown') {
        assert.ok(data.cleanup, 'progress capture must tear down in walk finally');
        await step(data.cleanup);
        assert.equal(el('fittings-copy-overlay').hidden, true);
        assert.equal(WM.current_route, 'main', 'generated cleanup hides synthetic rows without caller navigation');
        assert.equal(el('route-fittings').classList.contains('active'), false);
      }
    } else el('fittings-copy-close').click();
  }
  if (data.key === 'fittings-copy-result' || data.key === 'fittings-copy-limit') {
    await step(data.cleanup);
    assert.equal(WM.current_route, 'main', 'generated cleanup alone must hide the synthetic workspace');
    assert.equal(el('route-fittings').classList.contains('active'), false);
  } else if (data.regression !== 'teardown') { WM.route('main'); await tick(); }
  if (moduleName === 'fittings') {
    assert.equal(el('fittings-copy-overlay').hidden, true);
    // A queued event on the now-hidden Cancel must not lose fixture ownership
    // and fall through to an unkeyed real cancellation after route teardown.
    el('fittings-copy-cancel').dispatchEvent({type: 'click'});
  }
  assert.equal(calls.length, 0, 'staging, Cancel, Close, route leave and teardown are writer-free');
  if (moduleName === 'fittings') {
    staging = false; WM.route('fittings'); await tick();
    assert.ok(calls.some(call => call[0] === 'fittings_state'), 'ordinary reads resume after teardown');
    assert.ok(calls.every(call => call[0] === 'fittings_state'), 'reentry never resumes a synthetic writer');
  }
  console.log('PASS screenshot fidelity ' + data.key + ' ' + data.regression);
}
(async () => {
  if (data.gap) { await gapRegression(); return; }
  if (['settings-previews-groups', 'settings-characters-waiting', 'settings-characters-partial-cleanup', 'fittings-copy-limit',
       'fittings-copy-progress', 'fittings-copy-result'].includes(data.key)) {
    await fidelityRegression(); return;
  }
  if (moduleName === 'fittings') { await fittingsDetailRegression(); return; }
  WM.route(crop ? 'settings' : moduleName);
  if (crop) WM.section('previews');
  await tick(); calls.length = 0;
  if (data.regression) {
    await cropRegression();
    console.log('PASS screenshot regression ' + JSON.stringify(data.regression));
    return;
  }
  staging = true;
  // Exercise the exact expressions emitted by the Python shooter twice: a
  // screenshot must not inherit the previous capture's review or disclosure.
  for (let iteration = 0; iteration < 2; iteration++) {
    run(data.prepare); await tick();
    if (crop) WM.settingsTab('previews', 'wanderer');
    run(data.stage); await tick();
    run(data.verify);
    if (crop) {
      const panel = WM.el('settings-previews-characters');
      assert.equal(panel.hidden, false, 'crop staging must select Characters before framing');
      assert.equal(scrolls.at(-1).element.closest('.settings-subpage'), panel);
      WM.settingsTab('previews', 'windows');
      assert.throws(() => run(data.verify), /Screenshot content did not settle/);
      WM.settingsTab('previews', 'characters');
      // New live host revisions cannot paint over the isolated fixture.
      window.onPreviewCrops({revision: 900 + iteration, definitions: {}, operations: {}, statuses: {}});
      run(data.verify);
      document.querySelector('[data-preview-detail-control="crop-select"]').click();
    } else if (moduleName === 'uisetup') {
      for (const id of ['us-copy', 'us-save', 'setup-create', 'setup-paste', 'setup-file']) WM.el(id).click();
      // The merged catalog source must obey the same read-only seam. Dispatch
      // directly too: hiding/disabling a button is not a bridge safety boundary.
      for (const id of ['setup-catalog-open', 'setup-catalog-retry', 'setup-catalog-use']) {
        WM.el(id).dispatchEvent({type: 'click'});
      }
      assert.equal(WM.el('setup-catalog').hidden, true);
      assert.equal(WM.el('setup-catalog-origin').textContent, '');
    } else {
      WM.el('fm-save').click(); WM.el('fm-copy').click();
    }
    // Missing/unstaged content must fail before capture, not look complete.
    if (crop) document.querySelector('[data-preview-configure][aria-expanded="true"]').setAttribute('aria-expanded', 'false');
    else if (data.key === 'profiles-formations') WM.el('fm-name').value = '';
    else WM.el(data.key === 'profiles-formations-import' ? 'fm-import-work'
      : data.key === 'profiles-setup-share' ? 'us-summary' : 'setup-summary').hidden = true;
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
    run(data.cleanup); await tick();
    assert.equal(calls.length, 0, 'including cleanup');
    if (moduleName === 'uisetup') {
      assert.equal(WM.el('setup-text').value, '');
      assert.equal(WM.el('setup-summary').hidden, true);
    }
    if (crop) assert.equal(document.querySelector('[data-preview-configure][aria-expanded="true"]'), null);
  }
  // Leaving before the promise microtasks settle must also be harmless.
  run(data.prepare); run(data.cleanup); await tick();
  assert.equal(calls.length, 0);
  if (moduleName === 'uisetup' && data.key.endsWith('import')) {
    run(data.prepare); await tick(); run(data.stage); run(data.cleanup); await tick();
    assert.equal(calls.length, 0, 'late synthetic review must not discard a real backend offer');
  }
  staging = false;
  if (moduleName === 'formations') WM.openFormations([{path: 'live-account', name: 'Live'}], 'live-account');
  else if (moduleName === 'uisetup') {
    WM.openUiSetup({mode: 'export', context: {root: 'live', server: 'tq', profile: 'live-base'}});
    assert.ok(calls.length, 'ordinary export reads resume after cleanup');
    WM.openUiSetup({mode: 'import', context: {root: 'live', server: 'tq', profile: 'live-base'}});
    const beforeCatalogRead = calls.length;
    WM.el('setup-catalog-open').click();
    assert.ok(calls.slice(beforeCatalogRead).some(call => call[0] === 'eve_settings_setup_catalog'), 'ordinary catalog reads resume after cleanup');
  } else WM.section('previews');
  assert.ok(calls.length, 'ordinary reads resume after cleanup');
  console.log('PASS screenshot ' + data.key);
})().catch(error => { console.error(error); process.exitCode = 1; });
