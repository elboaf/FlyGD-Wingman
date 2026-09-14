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
  const revealCases = ['focus', 'click', 'pointer-click', 'edit-focus', 'edit-click', 'group-height',
    'bottom-clamp', 'tall-warning', 'tall-visible-control', 'visible', 'top-cycle', 'hidden', 'inactive',
    'unrelated', 'resolved', 'passive'];
  const scenarios = ['collapsed', 'expanded', 'bookmark-repair', 'size-reason', 'sticky-normal']
    .concat(Object.keys(stickyErrors), revealCases.map(name => 'reveal-' + name));
  assert.ok(scenarios.includes(data.scenario), 'Unknown preview warning scenario: ' + data.scenario);
  await new Promise(resolve => setImmediate(resolve));
  calls.length = 0; // The module's initial read is not part of staging.
  if (data.scenario.startsWith('reveal-')) {
    // Only layout is doubled. Exercise the production focus/click listeners,
    // independently of shooter staging (which must never supply this behavior).
    const kind = data.scenario.slice(7);
    assert.equal(data.stage, null);
    window.WM.openSettingsSection('previews', 'characters');
    await new Promise(resolve => setImmediate(resolve));
    calls.length = 0;
    const payload = JSON.parse(JSON.stringify(data.fixture));
    if (kind === 'group-height') payload.characters = [];
    if (kind === 'top-cycle') payload.hotkeys.cycle_next = 'Ctrl+Alt+1';
    if (kind === 'resolved') payload.bookmark_chords.active = [];
    window.onPreviewHotkeys(payload);
    const host = document.getElementById('preview-binds');
    const row = kind === 'top-cycle' ? host.querySelector('.row') : configure().parentNode;
    const bind = row.querySelector('.bindbtn');
    const edit = row.querySelectorAll('.linkbtn').find(node => node.textContent === 'Edit…');
    const warning = row.querySelector('.preview-bind-conflict');
    const pane = document.getElementById('settings-previews-characters');
    const outer = document.querySelector('.settings-pane');
    outer.scrollTop = 57;
    pane.clientHeight = 400; pane.scrollHeight = 1600;
    let position = 430;
    const writes = [];
    Object.defineProperty(pane, 'scrollTop', {
      get: () => position,
      set: value => { position = Math.max(0, Math.min(value, pane.scrollHeight - pane.clientHeight)); writes.push(position); }
    });
    const rect = (top, height) => ({top, bottom: top + height, height, left: 0, right: 600, width: 600});
    let content = 400;
    const tall = kind === 'tall-warning' || kind === 'tall-visible-control';
    const warningHeight = tall ? 600 : 40;
    if (kind === 'tall-visible-control') position = 950;
    if (kind === 'visible') position = 300;
    if (kind === 'top-cycle') { position = 0; content = 20; }
    if (kind === 'bottom-clamp') { position = 0; content = 550; pane.scrollHeight = 622; }
    const start = position;
    const section = document.getElementById('section-previews');
    if (kind === 'hidden') pane.hidden = true;
    if (kind === 'inactive') section.classList.remove('active');
    Element.prototype.getBoundingClientRect = function () {
      if (pane.hidden || !section.classList.contains('active')) return rect(0, 0);
      if (this === pane) return rect(100, 400);
      if (this === row) throw new Error('display:contents rows have no geometry');
      if (this.parentNode?.classList.contains('bind-head')) return rect(kind === 'top-cycle' ? 450 : 100, 37);
      if (this.classList.contains('bind-group')) return this.textContent ? rect(137, 63) : rect(0, 0);
      if (this === warning) return rect(100 + content - position, warningHeight);
      if (this === bind || this === edit) return rect(100 + content + warningHeight + 4 - position, 28);
      return rect(0, 0);
    };
    Element.prototype.scrollIntoView = function () { throw new Error('reveal must not scroll any ancestor implicitly'); };
    const target = kind.startsWith('edit-') ? edit : kind === 'unrelated' ? row.querySelector('input') : bind;
    let prompts = 0;
    window.WM.prompt = () => { prompts += 1; return Promise.resolve(null); };
    // :active is browser state from press through release, unlike :focus.
    const matches = Element.prototype.matches;
    let pressed = false;
    Element.prototype.matches = function (selector) {
      return selector === ':active' ? this === target && pressed : matches.call(this, selector);
    };
    if (kind === 'pointer-click') pressed = true;
    target.focus();
    if (kind === 'pointer-click') {
      target.dispatchEvent({type: 'focus'});
      assert.equal(position, start, 'mouse-down focus must not move the click target before mouse-up');
      pressed = false;
      target.click();
    } else if (kind === 'passive') window.onPreviewHotkeys(payload);
    else if (kind === 'click' || kind === 'edit-click') target.click();
    else target.dispatchEvent({type: 'focus'});
    await new Promise(resolve => setImmediate(resolve));
    const noScroll = ['hidden', 'inactive', 'unrelated', 'resolved', 'passive', 'visible', 'top-cycle'].includes(kind);
    if (noScroll) assert.equal(position, start, kind + ' must not move the scroller');
    else {
      assert.notEqual(position, start, 'direct conflict interaction reveals the warning and its controls');
      const top = kind === 'group-height' ? 200 : 137;
      assert.ok(bind.getBoundingClientRect().top >= top, 'focused control clears actual sticky heights');
      assert.ok(bind.getBoundingClientRect().bottom <= 500, 'control remains reachable, including bottom clamp');
      if (!tall) assert.ok(warning.getBoundingClientRect().top >= top, 'warning clears actual sticky headers');
      else assert.ok(warning.getBoundingClientRect().bottom - top >= 250, 'use available space for oversized guidance without hiding the control');
      if (kind === 'bottom-clamp') assert.equal(position, 222);
      assert.ok(writes.length <= 2, 'bounded local adjustment, not a scroll feedback loop');
    }
    assert.equal(outer.scrollTop, 57);
    // This double does not model browser blur when a passive repaint removes
    // the old row. Only visible direct interactions establish focus retention.
    if (!['passive', 'hidden', 'inactive'].includes(kind)) {
      assert.ok(document.contains(target), 'the focus owner is still attached');
      assert.equal(document.activeElement, target, 'reveal preserves the interaction owner');
    }
    if (kind !== 'passive') assert.equal(row.parentNode, host, 'reveal does not rebuild rows');
    assert.equal(prompts, kind === 'edit-click' ? 1 : 0);
    const captured = kind === 'click' || kind === 'pointer-click';
    assert.deepEqual(calls, captured ? [['set_bind_capture', true]] : [], 'only the pre-existing explicit capture may cross the bridge');
    assert.equal(bind.classList.contains('capturing'), captured);
    console.log('PASS preview warning grouping ' + data.scenario);
    return;
  }
  if (data.scenario === 'bookmark-repair') {
    window.WM.openSettingsSection('previews', 'characters');
    await new Promise(resolve => setImmediate(resolve));
    calls.length = 0;
    const gesture = 'Ctrl+Alt+1';
    const payload = JSON.parse(JSON.stringify(data.fixture));
    payload.hotkeys = {characters: {[owner]: gesture}, cycle_next: '', cycle_prev: '', groups: [], group_by_character: {}};
    payload.registration = {[gesture]: true};
    payload.bookmark_chords = {active: [gesture], latent: []};
    payload.excluded = [];
    const warning = () => document.getElementById('preview-bind-conflict-' + encodeURIComponent('character:' + owner));
    const repair = () => warning()?.querySelector('button');
    window.onPreviewHotkeys(payload);
    assert.ok(repair(), 'active bookmark overlap needs a repair route without action-name data');
    assert.equal(repair().textContent, 'Open Bookmarks');
    assert.ok(repair().classList.contains('linkbtn'), 'recovery is subordinate to the owning bind');
    assert.equal(repair().disabled, false);
    const row = configure().parentNode;
    assert.equal(row.firstElementChild, warning());
    const bind = row.querySelector('.bindbtn');
    assert.equal(bind.getAttribute('aria-describedby'), warning().id);
    assert.match(warning().textContent, /^Aiga Otsolen: Ctrl\+Alt\+1 /);
    assert.equal(calls.length, 0, 'rendering does not look up bookmark actions');
    bind.click();
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(bind.classList.contains('capturing'));
    repair().click();
    assert.equal(window.WM.current_section, 'bookmarks');
    assert.ok(document.getElementById('section-bookmarks').classList.contains('active'));
    assert.ok(!document.getElementById('section-previews').classList.contains('active'));
    assert.ok(!bind.classList.contains('capturing'), 'the real navigation leave contract cancels capture');
    assert.deepEqual(calls, [['set_bind_capture', true], ['set_bind_capture', false]], 'navigation never edits either binding');
    let prevented = false;
    document.dispatchEvent({type: 'keydown', key: 'x', code: 'KeyX', ctrlKey: true, altKey: true,
      preventDefault() { prevented = true; }, stopPropagation() {}});
    assert.equal(prevented, false, 'capture must not swallow a key typed in Bookmarks');
    assert.equal(calls.length, 2);
    // The repair route belongs only to the bookmark warning, never a higher-
    // priority local conflict/refusal or an inactive/opted-out registration.
    for (const kind of ['duplicate', 'refused', 'latent', 'excluded', 'resolved', 'unknown']) {
      const next = JSON.parse(JSON.stringify(payload));
      if (kind === 'duplicate') next.hotkeys.cycle_next = gesture;
      if (kind === 'refused') next.registration[gesture] = false;
      if (kind === 'latent') next.bookmark_chords = {active: [], latent: [gesture]};
      if (kind === 'excluded') next.excluded = [owner];
      if (kind === 'resolved') next.bookmark_chords.active = [];
      if (kind === 'unknown') { next.enabled = false; next.registration = {}; }
      window.onPreviewHotkeys(next);
      if (kind === 'unknown') assert.ok(repair(), 'configured overlap remains repairable without a registration report');
      else assert.ok(!repair(), kind + ' must not offer an unrelated repair');
      if (kind === 'duplicate') assert.match(warning().textContent, /conflicts with All forward/);
      if (kind === 'refused') assert.match(warning().textContent, /owned by another application/);
      if (['latent', 'excluded', 'resolved'].includes(kind)) {
        assert.equal(warning(), null);
        assert.equal(configure().parentNode.querySelector('.bindbtn').getAttribute('aria-describedby'), null);
      }
    }
    console.log('PASS preview warning grouping ' + data.scenario);
    return;
  }
  if (data.scenario === 'size-reason') {
    const payload = JSON.parse(JSON.stringify(data.fixture));
    payload.sizable = [];
    payload.enabled = true;
    payload.layout_sources = [{name: 'Other Pilot', online: false}];
    window.onPreviewHotkeys(payload);
    configure().click();
    const detail = () => document.getElementById('preview-character-detail-' + encodeURIComponent(owner));
    const reason = detail().querySelector('.size-none');
    assert.ok(reason && !reason.hidden, 'unavailable size has a visible explanation');
    assert.match(reason.textContent, /preview|placement/i, 'the explanation is text, not only a hover title');
    assert.match(reason.textContent, /start|create/i);
    assert.match(reason.textContent, /copy.*size.*position/i, 'an enabled Copy offers an alternate to starting the client');
    assert.doesNotMatch(reason.textContent, /enable previews/i, 'acknowledged On must not request enabling again');
    payload.enabled = false;
    window.onPreviewHotkeys(payload);
    assert.match(detail().querySelector('.size-none').textContent, /enable previews.*start/i);
    assert.match(detail().querySelector('.size-none').textContent, /copy.*size.*position/i,
      'Copy remains usable with the global preview preference Off');
    assert.equal(detail().querySelector('[data-preview-detail-control="copy"]').disabled, false);
    payload.enabled = true;
    window.onPreviewHotkeys(payload);
    assert.equal(detail().querySelector('.size-none').textContent, reason.textContent);
    assert.equal(detail().querySelector('[data-preview-detail-control="size"]'), null);
    assert.equal(detail().querySelector('[data-preview-detail-control="copy"]').disabled, false);
    for (const sources of [[], [{name: owner, online: false}]]) {
      payload.layout_sources = sources;
      window.onPreviewHotkeys(payload);
      assert.doesNotMatch(detail().querySelector('.size-none').textContent, /copy/i,
        'no alternate is promised without another source');
      assert.equal(detail().querySelector('[data-preview-detail-control="copy"]'), null);
    }
    payload.layout_sources = [{name: 'Other Pilot', online: false}];
    payload.excluded = [owner];
    window.onPreviewHotkeys(payload);
    assert.equal(detail().querySelector('[data-preview-detail-control="copy"]').disabled, true);
    assert.doesNotMatch(detail().querySelector('.size-none').textContent, /copy/i,
      'a disabled Copy is not an available alternate');
    // Only the authoritative flag admits size editing, even without client dimensions.
    payload.excluded = [];
    payload.sizable = [owner]; payload.client_sizes = {}; payload.sizes = {};
    window.onPreviewHotkeys(payload);
    assert.equal(detail().querySelector('.size-none'), null);
    assert.equal(detail().querySelector('[data-preview-detail-control="size"]').disabled, false);
    assert.equal(calls.length, 0, 'guidance never changes size or placement');
    console.log('PASS preview warning grouping ' + data.scenario);
    return;
  }
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
