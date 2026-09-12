// Real Settings owners + markup. Only the external bridge and DOM mechanics
// are doubled; generated shooter expressions are the system under test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = process.argv[3];
const {createDOM} = require('./screenshot_dom.cjs');
const {document, Element, scrolls} = createDOM(data.page);
const window = new Element('window');
Object.assign(window, {document, console: {...console, error: (...args) => { throw Error(args.join(' ')); }}, Promise, Math, Date,
  navigator: {clipboard: {readText: () => assert.fail('clipboard read'), writeText: () => assert.fail('clipboard write')}},
  Event: class { constructor(type) { this.type = type; } },
  CustomEvent: class { constructor(type, opts) { this.type = type; this.detail = opts.detail; } },
  setTimeout, clearTimeout, setInterval: () => 1, clearInterval: () => {},
  requestAnimationFrame: callback => setTimeout(callback, 0),
  matchMedia: () => ({matches: false}), getComputedStyle: () => ({visibility: 'visible'}), location: {search: ''}});
window.window = window;
const runtime = vm.createContext(window);
const run = text => { if (text) return vm.runInContext(text, runtime); };
const load = name => run(fs.readFileSync(web + '/' + name + '.js', 'utf8'));
load('app');
const WM = window.WM;
const calls = [], waiting = [];
let staging = false, hold = false, reply = () => null;
WM.send = (method, ...args) => {
  calls.push([method, ...args]);
  assert.equal(staging, false, 'synthetic stage reached bridge: ' + method);
  if (hold) return new Promise(resolve => waiting.push({method, resolve}));
  return Promise.resolve(reply(method, ...args));
};
WM.endPreviewCapture = () => {};
load('panel');
const family = data.scenario === 'preview-subpage' ? 'previews'
  : data.section === 'previews' ? 'wanderer' : data.section;
const methods = family === 'fleet' ? ['fleetScreenshot', 'fleetSharingScreenshot']
  : [family === 'wanderer' ? 'wandererScreenshot' : 'companionsScreenshot'];
const clone = value => JSON.parse(JSON.stringify(value));
const tick = () => new Promise(resolve => setTimeout(resolve, 5));
const live = data.fixture[family] ? clone(data.fixture[family]) : null;
// Live versions intentionally exceed the synthetic revision, proving separate
// ownership rather than a guessed high fixture revision.
if (family === 'companions') {
  live.state.revision = 7; live.state.rows[0].label = 'Live companion'; live.state.rows[0].generation = 7;
} else if (family === 'wanderer') {
  live.state.revision = 7; live.state.generation = 7;
  live.state.base_url = 'https://live.example'; live.state.map_identifier = 'live-map';
} else if (family === 'fleet') {
  live.display.state.revision = 7; live.display.state.enabled = true; live.display.state.characters[0].name = 'Live pilot';
  live.sharing.state.presentation_order = 7;
  live.sharing.state.metadata.paired_origin = 'https://live.example';
}
function pushLive() {
  if (family === 'companions') window.onCompanionPreviews(clone(live.state));
  else if (family === 'wanderer') window.onWandererState(clone(live.state));
  else { window.onFleetBarState(clone(live.display.state)); window.onFleetSharingState(clone(live.sharing.state)); }
}
function liveReply(method) {
  if (method === 'companion_previews_state' || method === 'wanderer_state') return live.state;
  if (method === 'fleet_bar_settings') return live.display.state;
  if (method === 'fleet_sharing_watch') return {state: live.sharing.state};
  return null;
}
function assertTab() {
  if (!data.tab) return;
  const panel = WM.el('settings-' + data.section + '-' + data.tab);
  assert.ok(panel, 'real markup has the expected subpage');
  assert.equal(panel.hidden, false, 'capture must select its tab before framing');
  const siblings = WM.el('section-' + data.section).querySelectorAll('.settings-subpage');
  assert.equal(siblings.filter(el => !el.hidden).length, 1);
}
function previousTab() {
  if (!data.tab) return;
  WM.settingsTab(data.section, data.tab === 'windows' || data.tab === 'youtube'
    ? (data.section === 'previews' ? 'characters' : 'combatlogs')
    : (data.section === 'previews' ? 'windows' : 'youtube'));
}
// Browser mechanics only: the shared DOM double has no layout engine. A hidden
// ancestor has no rendered boxes, and framing must use the selected panel.
Element.prototype.getClientRects = function () {
  for (let el = this; el; el = el.parentNode) if (el.hidden) return [];
  return [this.getBoundingClientRect()];
};
const click = Element.prototype.click;
Element.prototype.click = function () {
  if (staging && data.tab && this.closest('.settings-subpage')) {
    assertTab();
    assert.ok(this.getClientRects().length, 'cannot click a hidden screenshot control');
  }
  click.call(this);
};
const recordScroll = Element.prototype.scrollIntoView;
Element.prototype.scrollIntoView = function (options) {
  if (staging && data.tab) {
    assertTab();
    assert.ok(this.getClientRects().length, 'cannot frame a hidden descendant');
    assert.equal(this.closest('.settings-subpage')?.id, 'settings-' + data.section + '-' + data.tab);
  }
  recordScroll.call(this, options);
};
function assertContent() {
  assertTab();
  run(data.verify);
  assert.equal(WM.current_section, data.section);
  assert.ok(scrolls.length, 'semantic framing must run');
  if (family === 'companions') {
    assert.equal(document.querySelectorAll('.companion-row').length, 2);
    assert.match(WM.el('companion-list').textContent, /Mapper.*Whole window.*Fleet notes.*Selected region/);
    if (data.key.includes('detail')) assert.equal(document.querySelector('.companion-detail').open, true);
    if (data.key.endsWith('-add')) assert.equal(WM.el('companion-add-form').hidden, false);
    if (data.key.includes('source')) {
      assert.equal(WM.el('overlay').hidden, false);
      assert.ok(WM.el('dialog').classList.contains('compact-choice'));
      assert.match(WM.el('dlg-select').textContent, /Example map.*Example fleet notes/);
      assert.match(WM.el('dlg-select').options[0].textContent, /…$/);
      assert.match(WM.el('dlg-select-detail').textContent, /home chain and fleet route planning/);
    }
  } else if (family === 'wanderer') {
    assert.equal(WM.el('wanderer-url').value, 'https://wanderer.example');
    assert.equal(WM.el('wanderer-map').value, 'home-chain');
    assert.equal(WM.el('wanderer-token').value, '');
    assert.equal(WM.el('wanderer-url-draft').textContent, '');
    assert.match(WM.el('wanderer-health').textContent, /Connected to Wanderer/);
    assert.match(WM.el('wanderer-coverage').textContent, /2 of 3/);
  } else {
    assert.equal(WM.fleet_bar_on, true, 'a local fixture cannot change the global live EVE gate');
    assert.match(WM.el('fleetbar-character-list').textContent, /Running.*Aiga Otsolen.*Offline.*Tanuki Solette/);
    assert.match(WM.el('sharing-connection').textContent, /Paired with https:\/\/authgd.example/);
    assert.equal(WM.el('sharing-history').hidden, false);
    assert.match(WM.el('sharing-history-sources').textContent, /ended — boss changed/);
  }
}
function mutations() {
  const fire = (id, type = 'click') => WM.el(id).dispatchEvent({type});
  if (family === 'companions') {
    for (const suffix of ['reset', 'region', 'remove', 'label-apply']) fire('companion-screenshot-map-' + suffix);
    fire('companion-enabled', 'change'); fire('companion-screenshot-map-enabled', 'change');
    if (data.key.includes('source')) fire('dlg-ok'); // Must never select a native source.
  } else if (family === 'wanderer') {
    fire('wanderer-test'); fire('wanderer-remove'); fire('wanderer-enabled', 'change');
    WM.el('wanderer-token').dispatchEvent({type: 'keydown', key: 'Enter'});
  } else {
    for (const id of ['btn-fleetbar', 'fleetbar-reset', 'sharing-start', 'sharing-grant', 'sharing-connect', 'sharing-confirm-on']) fire(id);
    fire('fleetbar-enabled', 'change'); fire('sharing-enabled', 'change');
    document.querySelector('[data-fleet-character] input').dispatchEvent({type: 'change'});
    WM.el('sharing-refresh').click();
    WM.el('sharing-sources').querySelector('button').dispatchEvent({type: 'click'});
  }
}
(async () => {
  if (data.scenario === 'preview-subpage') {
    load('previews'); WM.openSettingsSection('previews'); await tick();
    const outer = document.querySelector('.settings-pane');
    outer.scrollTop = 57;
    const writes = [];
    for (const panel of WM.el('section-previews').querySelectorAll('.settings-subpage')) {
      let top = 73;
      panel.scrollHeight = 2000; panel.clientHeight = 400;
      Object.defineProperty(panel, 'scrollTop', {
        get: () => top,
        set: value => { assertTab(); assert.equal(panel.hidden, false); top = value; writes.push(panel.id); }
      });
    }
    calls.length = 0; staging = true;
    for (let iteration = 0; iteration < 2; iteration++) {
      previousTab();
      for (const name of ['appearance', 'placement', 'size', 'switching']) {
        WM.el('preview-group-' + name).open = iteration === 0;
      }
      run(data.prepare); run(data.stage); await tick(); assertTab(); run(data.verify);
      assert.equal(outer.scrollTop, 57, 'outer Settings pane must never own Preview scrolling');
      assert.ok(writes.length || scrolls.length, 'the selected panel must be framed');
      if (data.tab === 'windows') {
        const middle = data.key.endsWith('-middle');
        for (const name of ['appearance', 'placement']) assert.equal(WM.el('preview-group-' + name).open, !middle);
        for (const name of ['size', 'switching']) assert.equal(WM.el('preview-group-' + name).open, middle);
        if (middle) assert.equal(scrolls.at(-1).element.id, 'preview-group-size');
        else assert.equal(WM.el('settings-previews-windows').scrollTop, 0);
      }
      if (data.key === 'settings-previews-table') {
        assert.equal(WM.el('settings-previews-characters').scrollTop, 2000);
        assert.equal(document.querySelector('[data-preview-configure][aria-expanded="true"]'), null);
        // The next pass must close a detail inherited from an earlier capture.
        document.querySelector('[data-preview-configure]').click();
      }
      if (data.key === 'settings-previews-copy') WM.el('dlg-cancel').click();
      run(data.cleanup); await tick();
      assert.equal(calls.length, 0, 'tab selection and staging must not reach the bridge');
    }
    console.log('PASS current screenshot ' + data.key); return;
  }
  if (data.scenario === 'live-card') {
    const replies = {
      fightrecorder_status: {detected: false},
      get_bookmarks: {settings: {enabled: false, windows: {}, keybinds: {}},
        windows: [], order: ['sig'], labels: {sig: 'SIG'}, displays: {}, collisions: []},
      get_alert_state: {alerts: {enabled: false, events: {}}, previews_enabled: false},
      get_custom_alert_state: {revision: 1, rules: [], limit: 8, previews_enabled: false,
        alerts_enabled: false, reader: {running: false, last_error: null, characters: [], gamelogs_folder: null},
        matcher: {state: 'inactive', detail: null}}
    };
    reply = method => replies[method] || null;
    document.activeElement = document.body;
    load(data.section === 'uploading' ? 'settings' : data.section);
    WM.openSettingsSection(data.section);
    if (data.section === 'uploading') window.onSettings({settings: {category: '20'}});
    await tick();
    const expected = data.section === 'uploading' ? '#fr-status'
      : data.section === 'bookmarks' ? '#eve-windows' : '#custom-alert-health';
    assert.ok(document.querySelector(expected).textContent, 'real owner must hydrate the card');
    previousTab();
    calls.length = 0; staging = true;
    run(data.stage); assertTab(); run(data.verify);
    assert.equal(scrolls.at(-1).element.classList.contains('card'), true);
    assert.equal(scrolls.at(-1).options.block, 'start');
    assert.equal(calls.length, 0);
    const framed = scrolls.at(-1).element;
    framed.hidden = true;
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
    framed.hidden = false;
    if (data.section === 'alerts') {
      // Add is legitimately disabled at capacity; populated controls are still
      // a settled card, not a hydration failure.
      replies.get_custom_alert_state.rules = Array.from({length: 8}, (_, index) => ({
        id: 'rule-' + index, name: 'Rule ' + index, search: '', enabled: false,
        color: '#ff8c42', sound: 'none', cooldown_s: 8
      }));
      staging = false; WM.openSettingsSection('alerts'); await tick(); staging = true;
      assert.equal(WM.el('custom-alert-add').disabled, true);
      run(data.verify);
    }
    // The stage cannot silently accept the startup/blank rendering.
    if (data.section === 'uploading') WM.el('f-category').value = '';
    else if (data.section === 'bookmarks') WM.el('eve-windows').textContent = '';
    else WM.el('custom-alert-health').textContent = 'Loading custom alert status…';
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
    console.log('PASS current screenshot ' + data.key); return;
  }
  hold = data.scenario === 'late-read';
  if (family === 'fleet') { load('fleet'); load('fleetsharing'); }
  else load(family);
  WM.openSettingsSection(data.section); await tick();
  if (data.scenario === 'cold') {
    calls.length = 0; staging = true;
    run(data.prepare); WM.openSettingsSection(data.section); await tick(); run(data.stage); await tick(); run(data.verify);
    run(data.cleanup); await tick();
    assert.equal(calls.length, 0);
    if (family === 'companions') {
      assert.equal(WM.el('companion-list').children.length, 0);
      assert.equal(WM.el('companion-count').textContent, '');
      assert.equal(WM.el('companion-status').textContent, 'Loading companions…');
    } else if (family === 'wanderer') {
      assert.equal(WM.el('wanderer-url').value, '');
      assert.equal(WM.el('wanderer-map').value, '');
      assert.equal(WM.el('wanderer-token').value, '');
      assert.equal(WM.el('wanderer-coverage').textContent, '');
      assert.notEqual(WM.el('wanderer-credential').textContent, 'Token stored for this connection.');
    } else {
      assert.equal(WM.el('fleetbar-character-list').children.length, 0);
      assert.doesNotMatch(WM.el('fleet-sharing').textContent, /Aiga Otsolen|Ariadne|authgd.example/);
      assert.equal(WM.el('sharing-consent').textContent, '');
    }
    staging = false; reply = liveReply; WM.openSettingsSection(data.section); await tick();
    if (family === 'companions') assert.match(WM.el('companion-list').textContent, /Live companion/);
    else if (family === 'wanderer') assert.equal(WM.el('wanderer-url').value, 'https://live.example');
    else assert.match(WM.el('sharing-connection').textContent, /https:\/\/live.example/);
    console.log('PASS current screenshot cold cleanup'); return;
  }
  pushLive();
  if (data.scenario.startsWith('sharing-read-')) {
    WM.el('sharing-boss').value = '1'; WM.el('sharing-boss').dispatchEvent({type: 'change'});
    assert.equal(WM.el('sharing-start').disabled, false);
    WM.el('sharing-refresh').click(); await tick();
    const failedAuthority = () => {
      assert.match(WM.el('sharing-connection').textContent, /Could not refresh current source state/);
      assert.match(WM.el('sharing-eligibility').textContent, /Current eligibility unknown/);
      assert.equal(WM.el('sharing-eligible-list').children.length, 0);
      assert.equal(WM.el('sharing-start').disabled, true);
      assert.equal(WM.el('sharing-sources').querySelector('button').disabled, true);
    };
    failedAuthority(); calls.length = 0; staging = true;
    run(data.prepare);
    if (!data.scenario.endsWith('cached')) {
      if (data.scenario.endsWith('newer')) live.sharing.state.presentation_order += 1;
      window.onFleetSharingState(clone(live.sharing.state));
    }
    run(data.cleanup); await tick();
    assert.equal(calls.length, 0);
    if (data.scenario.endsWith('newer')) {
      assert.doesNotMatch(WM.el('sharing-connection').textContent, /Could not refresh/);
      assert.equal(WM.el('sharing-start').disabled, false);
      assert.equal(WM.el('sharing-eligible-list').children.length, 2);
    } else failedAuthority();
    // A real successful Refresh at the same version still recovers authority.
    staging = false; reply = liveReply; WM.el('sharing-refresh').click(); await tick();
    assert.doesNotMatch(WM.el('sharing-connection').textContent, /Could not refresh/);
    assert.equal(WM.el('sharing-start').disabled, false);
    assert.equal(WM.el('sharing-sources').querySelector('button').disabled, false);
    console.log('PASS current screenshot ' + data.scenario); return;
  }
  if (data.scenario.startsWith('wanderer-fence-')) {
    assert.equal(WM.el('wanderer-health').textContent, 'Connected to Wanderer.');
    const buffered = data.scenario.endsWith('buffered');
    calls.length = 0; staging = true;
    if (buffered) run(data.prepare);
    // Settings changed before worker reconfiguration. The acknowledgement is
    // current, but this coverage still belongs to the previous binding.
    const rebound = {...clone(live.state), revision: 8, generation: 7, map_identifier: 'new-binding'};
    window.onWandererState(rebound);
    if (buffered) {
      assert.equal(WM.el('wanderer-map').value, 'home-chain');
      run(data.cleanup);
      assert.equal(WM.el('wanderer-map').value, 'new-binding');
    }
    assert.equal(WM.el('wanderer-health').textContent, 'Connecting…');
    assert.equal(WM.el('wanderer-coverage').textContent, '');
    window.onWandererState({...rebound, generation: 8, available: 1});
    assert.equal(WM.el('wanderer-health').textContent, 'Connected to Wanderer.');
    assert.match(WM.el('wanderer-coverage').textContent, /^1 of 3/);
    assert.equal(calls.length, 0);
    console.log('PASS current screenshot ' + data.scenario); return;
  }
  if (data.scenario.startsWith('fleet-pending-')) {
    const action = data.scenario.slice('fleet-pending-'.length);
    hold = true; calls.length = 0;
    if (action === 'character') document.querySelector('[data-fleet-character] input').dispatchEvent({type: 'change'});
    else if (action === 'toggle-check') WM.el('fleetbar-enabled').dispatchEvent({type: 'change'});
    else WM.el(action === 'reset' ? 'fleetbar-reset' : 'btn-fleetbar').click();
    if (action === 'overlap') WM.el('fleetbar-reset').click();
    assert.equal(waiting.length, action === 'overlap' ? 2 : 1);
    const refuse = () => {
      staging = true; calls.length = 0;
      assert.throws(() => run(data.prepare), /Fleet.*in progress/);
      run(data.cleanup); assert.equal(calls.length, 0); staging = false;
    };
    refuse();
    const error = {applied: false, persisted: false, error: 'Live write failed'};
    waiting.shift().resolve(error); await tick();
    if (action === 'overlap') { refuse(); waiting.shift().resolve(error); await tick(); }
    assert.match(WM.el(action === 'character' ? 'fleetbar-characters-status' : 'fleetbar-enabled-status').textContent, /Live write failed/);
    hold = false; staging = true;
    run(data.prepare); run(data.cleanup); // Admission resumes only after every reply.
    console.log('PASS current screenshot ' + data.scenario); return;
  }
  if (data.scenario.startsWith('sharing-pending-')) {
    const action = data.scenario.slice('sharing-pending-'.length);
    live.sharing.state.presentation_order += 1;
    live.sharing.state.configured_origin = 'https://live.example';
    live.sharing.state.detail = 'needs_upgrade';
    window.onFleetSharingState(clone(live.sharing.state));
    WM.el('sharing-boss').value = '1'; WM.el('sharing-boss').dispatchEvent({type: 'change'});
    hold = true; calls.length = 0;
    WM.el(action === 'pair' ? 'sharing-connect' : 'sharing-grant').click();
    if (action === 'overlap') WM.el('sharing-connect').click();
    assert.equal(waiting.length, action === 'overlap' ? 2 : 1);
    const refuse = () => {
      staging = true; calls.length = 0;
      assert.throws(() => run(data.prepare), /Fleet sharing action in progress/);
      run(data.cleanup); assert.equal(calls.length, 0); staging = false;
    };
    refuse();
    const error = {queued: false, error: 'Browser launch failed'};
    // Settle the newer owner first: the older pending call still blocks capture.
    waiting.pop().resolve(error); await tick();
    if (action === 'overlap') { refuse(); waiting.pop().resolve(error); await tick(); }
    assert.match(WM.el('sharing-action').textContent, /Browser launch failed/);
    hold = false; staging = true;
    run(data.prepare); run(data.cleanup);
    assert.match(WM.el('sharing-action').textContent, /Browser launch failed/);
    console.log('PASS current screenshot ' + data.scenario); return;
  }
  if (data.scenario === 'fleet-focused') {
    const check = WM.el('fleetbar-enabled'); check.focus();
    assert.equal(check.checked, true);
    calls.length = 0; staging = true;
    run(data.prepare); assert.equal(check.checked, false);
    run(data.cleanup);
    assert.equal(check.checked, true, 'cleanup restores the acknowledged live value even while focused');
    assert.equal(document.activeElement, check);
    // Ordinary pushes still leave a focused checkbox alone.
    live.display.state.revision += 1; live.display.state.enabled = false;
    window.onFleetBarState(clone(live.display.state));
    assert.equal(check.checked, true);
    document.activeElement = document.body;
    window.onFleetBarState(clone(live.display.state));
    assert.equal(check.checked, false);
    assert.equal(calls.length, 0);
    console.log('PASS current screenshot fleet-focused'); return;
  }
  if (family === 'wanderer') {
    for (const [name, value] of [['url', 'https://private-draft.example'], ['map', 'private-map'], ['token', 'private-token']]) {
      WM.el('wanderer-' + name).value = value;
      WM.el('wanderer-' + name).dispatchEvent({type: 'input'});
    }
  }
  if (data.scenario === 'live-dialog') {
    WM.confirm('Live operation', 'Do not dismiss this to stage a screenshot.');
    calls.length = 0; staging = true;
    assert.throws(() => run(data.prepare), /dialog/);
    run(data.cleanup);
    assert.equal(WM.el('overlay').hidden, false);
    assert.equal(WM.el('dlg-title').textContent, 'Live operation');
    assert.equal(calls.length, 0);
    WM.el('dlg-cancel').click();
    console.log('PASS current screenshot live-dialog'); return;
  }
  calls.length = 0; staging = true;
  if (data.scenario === 'invalid') {
    for (const method of methods) assert.throws(() => WM[method]({kind: 'wrong'}), /Invalid .* screenshot fixture/);
  }
  for (let iteration = 0; iteration < 2; iteration++) {
    previousTab();
    run(data.prepare);
    WM.openSettingsSection(data.section);
    await tick(); run(data.stage); await tick();
    assertContent();
    if (data.scenario === 'late-read') {
      waiting.splice(0).forEach(item => item.resolve(liveReply(item.method)));
      await tick(); assertContent();
    }
    // A newer live delivery during capture must be retained, not merely
    // ignored until cleanup restores the old snapshot.
    if (family === 'companions') {
      live.state.revision += 1; live.state.rows[0].label = 'Live companion updated';
    } else if (family === 'wanderer') {
      live.state.revision += 1; live.state.generation += 1; live.state.map_identifier = 'live-map-updated';
    } else {
      live.display.state.revision += 1; live.display.state.characters[0].name = 'Live pilot updated';
      live.sharing.state.presentation_order += 1;
    }
    pushLive(); await tick(); assertContent();
    mutations(); await tick();
    run(data.cleanup); await tick();
    assert.equal(calls.length, 0, 'cleanup must stay local too');
    if (family === 'wanderer') {
      assert.equal(WM.el('wanderer-url').value, 'https://live.example');
      assert.equal(WM.el('wanderer-map').value, 'live-map-updated');
      assert.equal(WM.el('wanderer-token').value, '', 'never restore secret drafts');
    } else if (family === 'companions') {
      assert.match(WM.el('companion-list').textContent, /Live companion updated/);
      assert.equal(WM.el('companion-add-form').hidden, true);
      assert.equal(WM.el('companion-add-label').value, '');
      assert.equal(WM.el('overlay').hidden, true);
    } else {
      assert.match(WM.el('fleetbar-character-list').textContent, /Live pilot updated/);
      assert.match(WM.el('sharing-connection').textContent, /https:\/\/live.example/);
      assert.equal(WM.el('sharing-history').open, false);
    }
  }
  if (data.scenario === 'late-synthetic') {
    const NativePromise = window.Promise;
    let release;
    window.Promise = {resolve: value => new NativePromise(resolve => { release = () => resolve(value); })};
    run(data.prepare); WM.openSettingsSection(data.section); run(data.stage);
    run(data.cleanup); window.Promise = NativePromise;
    if (release) release(); await tick();
    assert.equal(calls.length, 0);
    assert.equal(WM.el('overlay').hidden, true);
  }
  // Verification rejects removed or half-initialized payloads.
  run(data.prepare); WM.openSettingsSection(data.section); await tick(); run(data.stage); await tick();
  if (family === 'companions') WM.el('companion-list').textContent = '';
  else if (family === 'wanderer') WM.el('wanderer-url').value = '';
  else WM.el('sharing-connection').textContent = '';
  assert.throws(() => run(data.verify), /Screenshot content did not settle/);
  run(data.cleanup); await tick();
  staging = false; hold = false; reply = liveReply;
  WM.openSettingsSection(data.section); await tick();
  if (family === 'fleet') WM.el('fleetbar-reset').click();
  else if (family === 'companions') WM.el('companion-screenshot-map-reset').click();
  else WM.el('wanderer-test').click();
  await tick(); assert.ok(calls.length, 'ordinary live behavior resumes');
  if (family === 'companions') {
    assert.deepEqual(calls.find(call => call[0] === 'companion_preview_reset_geometry'),
      ['companion_preview_reset_geometry', 'screenshot-map', 7]);
  } else if (family === 'wanderer') {
    assert.deepEqual(calls.find(call => call[0] === 'test_wanderer_connection'),
      ['test_wanderer_connection', 'https://live.example', 'live-map-updated', '']);
  }
  console.log('PASS current screenshot ' + data.key + ' ' + data.scenario);
})().catch(error => { console.error(error); process.exitCode = 1; });
