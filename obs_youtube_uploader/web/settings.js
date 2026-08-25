/* The Settings route.
 *
 * Rendered in the same window as a route rather than a separate OS
 * window, which removes a whole second toplevel's worth of lifecycle
 * code. The OAuth flow becomes an ordinary worker plus onAuthState
 * pushes, with no polling loop at all.
 */
(function () {
  'use strict';
  var WM = window.WM;

  var YOUTUBE_TOS_URL = 'https://www.youtube.com/t/terms';

  var current = {};    // last settings dict from Python
  var detected = {};   // detected-folder suggestions from the same payload
  // Fetched once from Python rather than duplicated here: ui/copy.py's
  // AUTH_STATES is the tested source, and a second table in JavaScript
  // would drift the moment a label changes.
  var authLabels = {};
  var pendingAuth = null;

  WM.send('auth_labels').then(function (table) {
    authLabels = table || {};
    if (pendingAuth) { renderAuth(pendingAuth); pendingAuth = null; }
  });

  // ---- immediate save -------------------------------------------------
  // There is no Save button. Every field commits on its own through a
  // per-field endpoint returning {applied, persisted, error}.
  //
  // THE HYDRATION GATE. get_settings resolves asynchronously (app.js), and
  // until it does every field on this screen is blank. Any commit fired in
  // that window would send blanks over a configured install -- exactly the
  // regression tests/test_api_settings.py:409-421 exists to prevent. The
  // Save button made that window nearly unreachable; committing on change
  // reopens it for any early focus, so nothing may commit until the first
  // payload has landed.
  var hydrated = false;

  function say(slot, text, tone) {
    var el = WM.el(slot);
    if (!el) { return; }
    el.textContent = text || '';
    el.className = 'field-msg' + (tone ? ' ' + tone : '');
    el.hidden = !text;
  }

  // `revert` repaints the field from the last known-good payload. Called
  // only when Python REFUSED a value -- never on a failed write, where the
  // setting really did take effect for this session and snapping the
  // control back would misreport it.
  function commit(slot, args, revert, onOk) {
    if (!hydrated) { return; }
    WM.send.apply(null, args).then(function (res) {
      // WM.send resolves to null on any bridge failure rather than
      // rejecting (app.js). A dict is always truthy, so null is still the
      // only thing that means "the call never landed".
      if (!res) {
        say(slot, 'Could not reach the app. Nothing was changed.', 'err');
        if (revert) { revert(); }
        return;
      }
      if (!res.applied) {
        say(slot, res.error || 'That value was not accepted.', 'err');
        if (revert) { revert(); }
        return;
      }
      if (!res.persisted) {
        // In effect for this session but not on disk. The control stays
        // where the user put it; what it cannot do is survive a restart,
        // and saying nothing is how they find that out the hard way.
        say(slot, 'Changed for this session, but could not be written to '
                + 'settings — it will not survive a restart.', 'warn');
        return;
      }
      say(slot, '');
      if (onOk) { onOk(); }
    });
  }

  // ---- fields ---------------------------------------------------------
  function setNotify(mode) {
    var inputs = document.querySelectorAll('input[name="notify"]');
    Array.prototype.forEach.call(inputs, function (input) {
      input.checked = (input.value === mode);
    });
  }

  function notifyValue() {
    var picked = document.querySelector('input[name="notify"]:checked');
    return picked ? picked.value : 'toast';
  }

  // Every successful commit pushes the COMPLETE settings payload back, so
  // a plain assignment would rewrite whichever field the user is still
  // typing in -- including rewriting a path into str(Path(...)) form
  // under the cursor. The focused field is left alone; it holds the more
  // recent value by definition.
  function setField(id, value) {
    var el = WM.el(id);
    if (!el || el === document.activeElement) { return; }
    el.value = value;
  }

  // Same activeElement guard as setField, for the same reason: the title
  // must not start describing a value the field no longer holds while the
  // user is mid-edit. An empty title attribute is removed rather than left
  // as an empty tooltip.
  function setTitle(id, value) {
    var el = WM.el(id);
    if (!el || el === document.activeElement) { return; }
    if (value) { el.title = value; } else { el.removeAttribute('title'); }
  }

  function render(payload) {
    var s = payload.settings || {};
    var d = payload.detected || {};
    current = s;
    detected = d;
    setField('f-privacy', s.privacy || 'unlisted');
    setField('f-category', s.category || '20');
    if (document.activeElement
        && document.activeElement.name !== 'notify') {
      setNotify(s.notify_mode || 'toast');
    }
    // Absent means shown: an upgrading user's file predates the key, and
    // hiding four things they already use would be a silent removal.
    if (WM.el('show-eve-tools') !== document.activeElement) {
      WM.el('show-eve-tools').checked = s.show_eve_tools !== false;
    }
    setField('f-recdir', s.recording_dir || '');
    setField('f-gamelogs', s.gamelogs_dir || '');
    // An <input> cannot ellipsize and does not wrap, so a path longer than
    // the field is cut mid-word with nothing to say it was cut
    // (walkthrough Settings 16). S2's stacking widened the field to 422px,
    // which is enough for the reported path and not enough for a
    // OneDrive-redirected Documents folder -- measured, it clips from about
    // 59 characters. The hover title is the only place the whole value can
    // be read back, on a field whose entire job is naming a location the
    // user has to confirm.
    setTitle('f-recdir', s.recording_dir || '');
    setTitle('f-gamelogs', s.gamelogs_dir || '');
    // The input holds the REAL value and the browser draws the mask, so
    // the mask can never be written back over the stored webhook — the
    // failure mode a hand-rolled bullet string invites.
    setField('f-webhook', s.discord_webhook || '');
    // webhook_status() is a pure Python function with its own test and is
    // the only description of what is stored; discord.describe omits the
    // token by construction. TOP-LEVEL key, and never reconstructed here.
    WM.el('webhook-status').textContent = payload.webhook_status
      || (s.discord_webhook ? '' : 'not configured');
    // X1 / Settings 14. Show reveals nothing and Remove removes nothing
    // when there is no webhook stored, and both rendered at full strength.
    // The app already KNOWS neither can act from the state it is holding,
    // which is exactly WM.setEnabled's rule; a refusal from Python would
    // have been unreachable once these are inert, so there is no backend
    // half to this.
    //
    // The FIELD stays live -- it is the only route back out of the state
    // that disabled these two, which the helper's own comment forbids
    // closing off.
    var configured = !!s.discord_webhook;
    WM.setEnabled('btn-webhook-show', configured);
    WM.setEnabled('btn-webhook-remove', configured);
    // A revealed webhook that is then removed would leave `Hide` on a
    // disabled button over an empty field.
    if (!configured) { remask(); }
    // Detect is always offered, but say so when there is nothing to find.
    WM.el('detect-note').textContent = (d.recording || d.gamelogs)
      ? 'Detect reads the recording folder from OBS’s own config, and the '
        + 'gamelogs folder from your EVE Online documents folder.'
      : 'Detect found neither folder automatically — use Browse to pick '
        + 'them yourself.';
    // M2. Pushed from __version__ through the payload, never typed here. A
    // payload without the key leaves the em dash rather than painting
    // "undefined" -- the same tolerance app.js gives the titlebar copy, so
    // merge order between the two surfaces cannot matter.
    if (payload.version) {
      WM.el('about-version').textContent = 'Version ' + payload.version;
    }
    // M3. Read live from the registry on every render rather than from a
    // stored setting, so an entry the user deleted by hand outside Wingman
    // shows as off here instead of claiming to be on.
    if (WM.el('start-on-login') !== document.activeElement) {
      WM.el('start-on-login').checked = !!payload.start_on_login;
    }
    // Last: everything above has painted real values, so a commit fired
    // from here on sends what is stored rather than a blank form.
    hydrated = true;
  }

  // ---- committing each field -------------------------------------------
  // The gate. Refused rather than applied while either EVE feature is
  // running, so the checkbox has to go back where it was and say why --
  // this is the one control on the screen whose refusal is expected
  // rather than exceptional.
  WM.el('show-eve-tools').addEventListener('change', function () {
    var box = WM.el('show-eve-tools');
    commit('msg-general', ['set_show_eve_tools', box.checked],
           function () { box.checked = !box.checked; },
           // Applied HERE, not left to the wm:settings push: the per-field
           // endpoints deliberately do not push, because re-sending the
           // whole payload is what used to rewrite the field still being
           // edited. Without this the value was written and nothing
           // repainted until the next launch -- the tabs stayed put.
           function () { WM.apply_eve_gate(box.checked); });
  });

  // M3. Start-on-login writes outside the app's own config -- an
  // HKCU\...\Run value -- so a refusal is real: a managed machine can deny
  // the key by policy. It goes through the same commit() as every other
  // field, which reports {applied, persisted, error} without this site
  // hand-rolling a branch for an outcome set_start_on_login cannot
  // produce: the registry entry IS the state, so there is no in-memory
  // half that could apply while the write fails.
  WM.el('start-on-login').addEventListener('change', function () {
    var box = WM.el('start-on-login');
    commit('msg-about', ['set_start_on_login', box.checked],
           function () { box.checked = !box.checked; });
  });

  // Discrete controls commit on change. There is nothing to mistype, the
  // value is one of a fixed set, and a refusal is recoverable.
  WM.el('f-privacy').addEventListener('change', function () {
    commit('msg-uploads', ['set_privacy', WM.el('f-privacy').value],
           function () { setField('f-privacy', current.privacy || 'unlisted'); });
  });

  // `change` on a text input fires on blur AND on Enter. That is safe for
  // this field -- it drives nothing but its own value, and a refusal is
  // shown inline. It is NOT safe for the folders and the webhook below.
  WM.el('f-category').addEventListener('change', function () {
    commit('msg-uploads', ['set_category', WM.el('f-category').value],
           function () { setField('f-category', current.category || '20'); });
  });

  Array.prototype.forEach.call(
    document.querySelectorAll('input[name="notify"]'), function (input) {
      input.addEventListener('change', function () {
        commit('msg-notify', ['set_notify_mode', notifyValue()],
               function () { setNotify(current.notify_mode || 'toast'); });
      });
    });

  // panel.js owns the onSettings handler (it renders the destination line)
  // and re-dispatches the payload, so both modules consume one push
  // without either owning it exclusively.
  document.addEventListener('wm:settings', function (ev) {
    render(ev.detail || {});
  });

  // ---- folder pickers -------------------------------------------------
  // Both folders carry BOTH actions: Settings has distinct Detect paths
  // for the recording directory (via OBS's own config) and the EVE
  // gamelogs directory. `which` matches Api.pick_folder/detect_folder.
  var TARGET_FIELD = { recording: 'f-recdir', gamelogs: 'f-gamelogs' };

  // A folder is NEVER committed on blur. save_settings rebinds the live
  // watcher, and Watcher.rebind marks every file already in the folder as
  // seen -- so committing a half-typed path that happens to name a real
  // directory silently suppresses the announcement for every recording
  // that arrived this session, and the corrective commit does it again to
  // the right folder. Irreversible from here.
  //
  // Browse and Detect are explicit choices and commit directly. Typing
  // commits on Enter; a blur with unsaved text says so and keeps the text,
  // so nothing is lost either way.
  function commitFolder(which) {
    var field = WM.el(TARGET_FIELD[which]);
    if (!field) { return; }
    commit('msg-folders', ['set_folder', which, field.value], function () {
      setField(TARGET_FIELD[which],
               (which === 'gamelogs' ? current.gamelogs_dir
                                     : current.recording_dir) || '');
    });
  }

  function applyFolder(which, path) {
    if (!path) return;   // a cancelled dialog is also a valid result
    var field = WM.el(TARGET_FIELD[which]);
    if (field) { field.value = path; }
    commitFolder(which);
  }

  Object.keys(TARGET_FIELD).forEach(function (which) {
    var field = WM.el(TARGET_FIELD[which]);
    if (!field) { return; }
    field.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter') { return; }
      ev.preventDefault();
      commitFolder(which);
    });
    field.addEventListener('blur', function () {
      var stored = (which === 'gamelogs' ? current.gamelogs_dir
                                         : current.recording_dir) || '';
      if (field.value.trim() === stored) { return; }
      say('msg-folders', 'Press Enter to use this folder, or click '
                       + 'Browse\u2026', 'warn');
    });
  });

  document.querySelectorAll('[data-browse]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var which = btn.dataset.browse;
      WM.send('pick_folder', which).then(function (path) {
        applyFolder(which, path);
      });
    });
  });

  document.querySelectorAll('[data-detect]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var which = btn.dataset.detect;
      // The field's LIVE value, not the stored setting: a detection that
      // agrees with what the user has already typed is reported as
      // agreement rather than silently rewriting the field.
      var field = WM.el(TARGET_FIELD[which]);
      WM.send('detect_folder', which, field ? field.value : '')
        .then(function (path) { applyFolder(which, path); });
    });
  });

  // ---- webhook mask ---------------------------------------------------
  var webhook = WM.el('f-webhook');
  var showBtn = WM.el('btn-webhook-show');

  showBtn.addEventListener('click', function () {
    var revealed = webhook.type === 'text';
    webhook.type = revealed ? 'password' : 'text';
    showBtn.textContent = revealed ? 'Show' : 'Hide';
    showBtn.setAttribute('aria-pressed', String(!revealed));
  });

  // Same rule as the folders, for a different reason: an empty value used
  // to mean "clear the webhook", so select-all, Delete and look away
  // destroyed a configured secret. Setting one commits on Enter; removing
  // one is its own button.
  webhook.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter') { return; }
    ev.preventDefault();
    commit('msg-discord', ['set_discord_webhook', webhook.value],
           function () { setField('f-webhook', current.discord_webhook || ''); });
  });

  webhook.addEventListener('blur', function () {
    if (webhook.value.trim() === (current.discord_webhook || '')) { return; }
    say('msg-discord', 'Press Enter to save this webhook.', 'warn');
  });

  WM.el('btn-webhook-remove').addEventListener('click', function () {
    commit('msg-discord', ['clear_discord_webhook']);
  });

  function remask() {
    webhook.type = 'password';
    showBtn.textContent = 'Show';
    showBtn.setAttribute('aria-pressed', 'false');
  }

  // Leaving re-masks, so a revealed credential cannot be left on screen by
  // navigating away and back. Both events, not just the route: Discord is
  // one section among several now, and switching to Folders leaves the
  // webhook just as thoroughly as switching to the Uploader does -- while
  // firing no route change at all.
  document.addEventListener('wm:route', function (ev) {
    if (ev.detail !== 'settings') remask();
  });
  document.addEventListener('wm:section', function (ev) {
    if (ev.detail !== 'discord') remask();
  });

  // ---- Google account -------------------------------------------------
  function renderAuth(p) {
    var spec = authLabels[p.state] || authLabels.disconnected;
    if (!spec) { pendingAuth = p; return; }   // labels not fetched yet
    var btn = WM.el('btn-auth');
    btn.textContent = spec.label;
    btn.disabled = !spec.enabled;
    var pill = WM.el('auth-pill');
    var tone = { connected: 'ok', connecting: 'warn', revoking: 'warn' };
    pill.className = 'pill ' + (tone[p.state] || 'idle');
    // The message is Python's string when it sends one; the table's is the
    // fallback.
    WM.el('auth-text').textContent = p.message || spec.message;
  }

  WM.handle('onAuthState', renderAuth);

  WM.el('btn-auth').addEventListener('click', function () {
    // No optimistic local disable: Python answers with a `connecting`
    // push, and one source of truth for the button is what keeps the pill
    // and the button two views of ONE state.
    WM.send('connect_google');
  });

  WM.el('tos-link').addEventListener('click', function () {
    window.open(YOUTUBE_TOS_URL, '_blank');
  });

  // No save / cancel block. Every field above commits on its own, and a
  // Cancel would promise a rollback nothing here can perform: `current` is
  // reassigned on every render, so no pre-edit snapshot survives.
}());

// ---- EVE client previews -------------------------------------------------
// Deliberately not in bookmarks.js: that module owns the AutoHotkey engine
// and its status plumbing, and previews share none of it.
//
// It calls its own endpoint because toggling this has to start or stop a
// thread, not merely persist a field. That was already true when the rest
// of this screen still had a Save button; now every field commits on its
// own, this block is simply the first that always did.
(function () {
  var box = WM.el('preview-enabled');
  if (!box) { return; }

  box.addEventListener('change', function () {
    var wanted = box.checked;
    // WM.send resolves to null on any bridge failure rather than
    // rejecting (app.js:38-43), so check the resolved value. Python
    // returns True on success precisely so this can tell the two apart.
    WM.send('set_preview_enabled', wanted).then(function (ok) {
      if (!ok) {
        // Put it back rather than leave the checkbox showing a state the
        // backend never accepted.
        box.checked = !wanted;
      }
      // #preview-enabled and the Alerts card share one section with no
      // navigation between them (alerts.js's wm:section refresh never
      // fires), so the card would otherwise keep showing a stale "watching
      // N characters" line -- persistently, since the backend really did
      // stop the poll thread -- until the user left and returned to the
      // route. Dispatched after the bridge call settles, not on the raw
      // change, so alerts.js's get_alert_state read cannot race ahead of
      // set_preview_enabled's own host.stop()/alerts.reconcile().
      document.dispatchEvent(new CustomEvent('wm:preview-enabled-changed'));
    });
  });

  // panel.js owns the onSettings handler and re-dispatches it, so this
  // listens on the same custom event the folder fields above use rather
  // than claiming a handler that already has an owner.
  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    box.checked = !!(s.preview && s.preview.enabled);
  });
}());

// ---- Where a preview opens -----------------------------------------------
// Separate from the previews block above: this key is written by its own
// bridge method so a write that fails can be reported rather than silently
// lost. Its {applied, persisted} return is the shape the per-field
// endpoints at the top of this file were modelled on.
//
// This replaces the card that used to move the GAME windows. EVE reads a
// resize as a resolution change and rewrites its own configuration, so
// Wingman no longer touches a client's rect at all -- only the preview's.
(function () {
  var box = WM.el('restore-preview-positions');
  var status = WM.el('restore-preview-positions-status');
  if (!box || !status) { return; }

  var DEFAULT_HINT = status.textContent;

  function say(text) { status.textContent = text || DEFAULT_HINT; }

  // Walkthrough Settings 2: with previews switched off, this checked box
  // was the ONE accent-coloured element on the whole section -- the eye
  // pulled to the least consequential control present, below the switch
  // that turned its feature off.
  //
  // The accent is not the fault. S1's approved rule is that accent marks
  // what is SELECTED and what will happen, and a ticked box is what is
  // selected; taking the colour off it would be a wave-1 reversal, and the
  // rule lives in a region this lane does not own either way. Nor can the
  // control be disabled: S3's handoff is explicit that Previews controls
  // stay live, because recording a preference for later is an action that
  // CAN be carried out.
  //
  // What is actually wrong is that a dependent option is rendered as a
  // peer of the switch it depends on, with nothing saying so. So the row
  // says so, in the same voice as INERT_NOTES' previews_off sentence one
  // card below -- and only while it is true.
  var DEPENDS = 'Previews are off, so this changes nothing yet — it '
              + 'applies when you turn them back on.';

  // Read from the switch itself rather than cached from the payload. The
  // Enable checkbox lives in the block above and commits through its own
  // endpoint, which does NOT push a settings payload, so a cached copy
  // would keep reporting the state this row had when the section opened.
  function previewsOn() {
    var enable = WM.el('preview-enabled');
    return !!(enable && enable.checked);
  }

  function sayDependence() { if (!previewsOn()) { say(DEPENDS); } }

  box.addEventListener('change', function () {
    var wanted = box.checked;
    // WM.send resolves to null on any bridge failure rather than
    // rejecting (app.js:38-43). A dict is always truthy, so null is
    // still the only thing that reverts the box -- and a failed write
    // is no longer mistaken for one.
    WM.send('set_restore_preview_positions', wanted).then(function (res) {
      if (!res) { box.checked = !wanted; return; }
      if (!res.persisted) {
        // The setting really did change for this session, so the box
        // stays where the user put it. What it cannot do is survive a
        // restart, and saying nothing is how they find that out the
        // hard way.
        say('Reopening previews in place is ' + (wanted ? 'on' : 'off')
          + ' for this session, but could not be written to settings — '
          + 'it will not survive a restart.');
      } else {
        // The checkbox itself is the success feedback. Restoring the
        // hint (rather than confirming) clears a prior failure message
        // without adding noise on every successful toggle.
        say('');
        sayDependence();
      }
    });
  });

  // panel.js owns onSettings and re-dispatches it, so listen on the same
  // custom event the blocks above use rather than claiming a handler that
  // already has an owner.
  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    // Absent means on: an upgrading user's file predates the key, and
    // showing the box unchecked would misreport what will happen.
    box.checked = !(s.preview
      && s.preview.restore_preview_positions === false);
    refreshDependence();
  });

  // The switch this row depends on. Its own handler is in the block above
  // and reverts the box on a bridge failure without re-firing `change`, so
  // this can be one push behind in that one case -- the next settings
  // payload corrects it, and a failed bridge call has already put more
  // than this sentence out of step.
  var enableBox = WM.el('preview-enabled');
  if (enableBox) {
    enableBox.addEventListener('change', refreshDependence);
  }

  // Only ever overwrites the default hint, never a live message. A failure
  // reported by the commit above is more urgent than a dependence note and
  // must not be wiped by an unrelated field's settings push.
  function refreshDependence() {
    if (status.textContent === DEFAULT_HINT) { sayDependence(); }
    else if (previewsOn() && status.textContent === DEPENDS) { say(''); }
  }
}());

// ---- Preview labels -------------------------------------------------------
// Same shape as restore-preview-positions above, with one difference:
// _write_preview_setting (ui/api.py) reports a persistence failure as
// `applied: false`, not `applied: true, persisted: false` -- settings_mod.
// update restores the LIVE dict on OSError here, so the value genuinely
// never took effect either. That is why this checks `res.applied` before
// falling back to `res.persisted`, rather than only the falsy-`res` check
// restore-preview-positions's writer gets away with.
(function () {
  var box = WM.el('preview-show-labels');
  var status = WM.el('preview-show-labels-status');
  if (!box || !status) { return; }

  var DEFAULT_HINT = status.textContent;

  function say(text) { status.textContent = text || DEFAULT_HINT; }

  // Same dependence note as Position above: PreviewHost.restyle() only
  // touches previews that are actually open, so with previews off this
  // sets tomorrow's label, not today's.
  var DEPENDS = 'Previews are off, so this changes nothing yet — it '
              + 'applies when you turn them back on.';

  function previewsOn() {
    var enable = WM.el('preview-enabled');
    return !!(enable && enable.checked);
  }

  function sayDependence() { if (!previewsOn()) { say(DEPENDS); } }

  box.addEventListener('change', function () {
    var wanted = box.checked;
    WM.send('set_preview_show_labels', wanted).then(function (res) {
      if (!res || !res.applied) {
        // Refused: the live value never changed either, so put the box
        // back rather than show a state the app is not in.
        box.checked = !wanted;
        say(res && res.error);
        return;
      }
      if (!res.persisted) {
        say('Showing character names is ' + (wanted ? 'on' : 'off')
          + ' for this session, but could not be written to settings — '
          + 'it will not survive a restart.');
      } else {
        say('');
        sayDependence();
      }
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    // Absent means on: settings.py's default is True, and an upgrading
    // user's file predates the key.
    box.checked = !(s.preview && s.preview.show_labels === false);
    refreshDependence();
  });

  var enableBox = WM.el('preview-enabled');
  if (enableBox) { enableBox.addEventListener('change', refreshDependence); }

  function refreshDependence() {
    if (status.textContent === DEFAULT_HINT) { sayDependence(); }
    else if (previewsOn() && status.textContent === DEPENDS) { say(''); }
  }
}());

// ---- Preview opacity --------------------------------------------------
// The "border and label stay full strength" sentence is a separate static
// hint in index.html, not this status line: it has to stay on screen even
// while this line is reporting a write failure or the previews-off
// dependence note, because it is the one sentence in this card that
// contradicts what a TriffView user would otherwise assume.
(function () {
  var box = WM.el('preview-opacity');
  var readout = WM.el('preview-opacity-value');
  var status = WM.el('preview-opacity-status');
  if (!box || !readout || !status) { return; }

  // The last value the backend actually accepted, so a refusal can put
  // the slider back rather than leave it showing what the user dragged to.
  var lastGood = box.value;

  var DEFAULT_HINT = status.textContent;

  function say(text) { status.textContent = text || DEFAULT_HINT; }

  var DEPENDS = 'Previews are off, so this changes nothing yet — it '
              + 'applies when you turn them back on.';

  function previewsOn() {
    var enable = WM.el('preview-enabled');
    return !!(enable && enable.checked);
  }

  function sayDependence() { if (!previewsOn()) { say(DEPENDS); } }

  // Live readout as the thumb moves; the setting itself commits only on
  // `change` (DESIGN.md: discrete controls commit on change, and a range
  // fires `input` per pixel dragged -- a write per pixel is the bug this
  // rule exists to prevent).
  box.addEventListener('input', function () {
    readout.textContent = box.value;
  });

  box.addEventListener('change', function () {
    var wanted = parseInt(box.value, 10);
    WM.send('set_preview_opacity', wanted).then(function (res) {
      if (!res || !res.applied) {
        // Refused: put the slider back where it was rather than show a
        // value the app never actually took.
        box.value = lastGood;
        readout.textContent = box.value;
        say(res && res.error);
        return;
      }
      lastGood = box.value;
      if (!res.persisted) {
        say('Opacity ' + wanted + ' is set for this session, but could '
          + 'not be written to settings — it will not survive a restart.');
      } else {
        say('');
        sayDependence();
      }
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    var value = (s.preview && s.preview.opacity) || 255;
    box.value = value;
    lastGood = box.value;
    readout.textContent = box.value;
    refreshDependence();
  });

  var enableBox = WM.el('preview-enabled');
  if (enableBox) { enableBox.addEventListener('change', refreshDependence); }

  function refreshDependence() {
    if (status.textContent === DEFAULT_HINT) { sayDependence(); }
    else if (previewsOn() && status.textContent === DEPENDS) { say(''); }
  }
}());

// ---- Minimize inactive clients ---------------------------------------
// Same {applied, persisted, error} shape and revert-on-refusal posture as
// show_labels/opacity above. One difference worth flagging: unlike those
// two, this flag is read PER SWITCH (build_preview_host's closure in
// __main__.py), not applied to every open preview by restyle() the moment
// it changes -- so index.html's static hint already says "applies the
// next time a client is switched away from, not this one." This file's
// status line stays reserved for the states show_labels/opacity's already
// cover (refused, persist-failed, previews-off) and does not repeat that.
(function () {
  var box = WM.el('preview-minimize-inactive');
  var status = WM.el('preview-minimize-inactive-status');
  if (!box || !status) { return; }

  var DEFAULT_HINT = status.textContent;

  function say(text) { status.textContent = text || DEFAULT_HINT; }

  var DEPENDS = 'Previews are off, so this changes nothing yet — it '
              + 'applies when you turn them back on.';

  function previewsOn() {
    var enable = WM.el('preview-enabled');
    return !!(enable && enable.checked);
  }

  function sayDependence() { if (!previewsOn()) { say(DEPENDS); } }

  box.addEventListener('change', function () {
    var wanted = box.checked;
    WM.send('set_minimize_inactive_clients', wanted).then(function (res) {
      if (!res || !res.applied) {
        box.checked = !wanted;
        say(res && res.error);
        return;
      }
      // applied is true whether or not persistence succeeded -- update.
      // update never reverts the in-memory dict on an OSError, only on
      // raising before that (see _write_preview_setting's own comment),
      // so the live value really did change here and previews.js's
      // per-row Never-minimize checkboxes need to know now, not at the
      // next full page load. wm:settings itself cannot carry this: it is
      // deliberately never re-dispatched after a single-field write (see
      // list.js's refreshRecordingDir), because repainting the whole
      // Settings form would clobber whatever else the user is mid-edit on.
      document.dispatchEvent(new CustomEvent('wm:preview-minimize-inactive', {
        detail: { enabled: wanted }
      }));
      if (!res.persisted) {
        say('Minimizing inactive clients is ' + (wanted ? 'on' : 'off')
          + ' for this session, but could not be written to settings — '
          + 'it will not survive a restart.');
      } else {
        say('');
        sayDependence();
      }
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    // Absent means off: matches build_preview_host's minimize_inactive_
    // clients closure default (__main__.py) -- minimizing a real EVE
    // client window must be asked for, never assumed on upgrade.
    box.checked = !!(s.preview && s.preview.minimize_inactive_clients);
    refreshDependence();
  });

  var enableBox = WM.el('preview-enabled');
  if (enableBox) { enableBox.addEventListener('change', refreshDependence); }

  function refreshDependence() {
    if (status.textContent === DEFAULT_HINT) { sayDependence(); }
    else if (previewsOn() && status.textContent === DEPENDS) { say(''); }
  }
}());
