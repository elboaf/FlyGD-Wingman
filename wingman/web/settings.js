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

  // What changing a recording folder costs, stated before the click. The
  // number belongs to the report set_folder sends back afterwards -- see
  // _folder_note in ui/api.py -- because it depends on the folder chosen.
  // Not "data loss": the recordings are still listed, they simply arrive
  // unticked and unannounced.
  var FOLDER_COST = 'Changing the recording folder starts watching it. '
                  + 'Recordings already there won\u2019t be announced, and '
                  + 'arrive unticked in the list.';

  // The gamelogs folder's own cost, and it is a DIFFERENT one -- which is
  // why round 5's E2 was a defect rather than a wording problem. The two
  // fields shared one note stating the sentence above, so repointing the
  // gamelogs path explained the recording watcher. This folder drives no
  // watcher: ui/api.py's set_folder calls AlertService.reconcile() on the
  // gamelogs branch, so the change takes effect on the spot rather than
  // costing anything.
  var GAMELOG_COST = 'Alerts read this folder. Changing it re-checks it '
                   + 'straight away.';

  // Per folder, because these are now in two different sections. A single
  // shared slot is what E2 actually was: with #msg-folders living in
  // Uploading, a gamelogs refusal would have rendered into a paragraph on
  // a pane the user was not looking at -- silent, and worse than the
  // mis-scoped sentence that prompted the split.
  var TARGET_NOTE = { recording: 'detect-note', gamelogs: 'gamelogs-note' };
  var TARGET_MSG = { recording: 'msg-recdir', gamelogs: 'msg-gamelogs' };
  var TARGET_COST = { recording: FOLDER_COST, gamelogs: GAMELOG_COST };
  var TARGET_NOUN = { recording: 'recording', gamelogs: 'gamelogs' };

  var current = {};    // last settings dict from Python
  var detected = {};   // detected-folder suggestions from the same payload
  // Task 5's bridge contract lands in app.js; About owns the render later.
  // Held here now so the event has a listener from the moment it exists.
  var latestUpdateStatus = null;
  document.addEventListener('wm:update-status', function (ev) {
    latestUpdateStatus = ev.detail || {};
  });
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
      // A `note` is the endpoint reporting what the commit actually
      // did, with a number no hint written beforehand could have had --
      // set_folder's is the only one so far (round 3, B11). Neutral tone
      // on purpose: it is not a warning, and it replaces any blur warning
      // still sitting in the slot.
      say(slot, res.note || '');
      if (onOk) { onOk(res); }
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
    renderWebhook(payload.webhook_status, !!s.discord_webhook);
    // Round 3, B11 and R4's finding 1. This slot used to explain what
    // Detect READS, which is the least valuable thing on the card and was
    // occupying the space the consequence needed. All three controls on
    // these rows -- Enter, Browse and Detect -- perform the same rebind,
    // so the sentence is written about the folder CHANGE rather than
    // about any one of them; a hint framed around Enter aims at the only
    // route that already warns on blur.
    //
    // Detect is always offered, but say so when there is nothing to find.
    // That half is a state report, not mechanism, so it survives -- after
    // the consequence, which is true whichever way the folder gets set.
    //
    // Round 5, E2: one loop over the two folders rather than one slot for
    // both. The detect clause used to read "Detect found NEITHER folder
    // ... pick THEM yourself" off `d.recording || d.gamelogs`, so it was
    // the second thing on this card scoped to the pair -- and once D2 put
    // the two fields in different sections it could not follow either one
    // intact. Each note now tests only its own folder and names it, which
    // is also strictly more accurate than the old clause: it was silent
    // when exactly one of the two was found, which is the common case.
    Object.keys(TARGET_NOTE).forEach(function (which) {
      var slot = WM.el(TARGET_NOTE[which]);
      if (!slot) { return; }
      slot.textContent = TARGET_COST[which] + (d[which]
        ? ''
        : ' Detect found no ' + TARGET_NOUN[which] + ' folder automatically'
          + ' — use Browse to pick it yourself.');
    });
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
    commit(TARGET_MSG[which], ['set_folder', which, field.value], function () {
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
      say(TARGET_MSG[which], 'Press Enter to use this folder, or click '
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
    // Applied HERE, exactly as show-eve-tools does above and for the same
    // reason: the per-field endpoints do not push, and get_settings is
    // fetched once at page load. Without this the webhook persisted while
    // the summary line kept reading `not configured` and Show/Remove
    // stayed disabled until the next launch.
    commit('msg-discord', ['set_discord_webhook', webhook.value],
           function () { setField('f-webhook', current.discord_webhook || ''); },
           function (res) {
             current.discord_webhook = webhook.value;
             renderWebhook(res.webhook_status, true);
           });
  });

  webhook.addEventListener('blur', function () {
    if (webhook.value.trim() === (current.discord_webhook || '')) { return; }
    say('msg-discord', 'Press Enter to save this webhook.', 'warn');
  });

  // Round 3, B12. This was the one destructive action in the app that
  // asked nothing: one click, no undo, on a value the field is masking so
  // the user cannot read what they are about to lose. The other five all
  // confirm, through three different mechanisms.
  //
  // WM.confirm, NOT Api._confirm. clear_discord_webhook is a plain bridge
  // method, so it runs on the pywebview thread -- the same thread that
  // would have to deliver dialog_response -- and _confirm blocks waiting
  // for it. That is a deadlock, and it is why `Reset keybinds` uses the
  // overlay too (DESIGN.md's table of the three mechanisms).
  //
  // The dialog names WHICH webhook, because the field cannot: it is
  // masked, and webhook-status is the only description of what is stored
  // (ui/copy.py's webhook_status, which omits the token by construction).
  // A confirm that says "the webhook" on a screen showing a row of dots
  // asks the user to approve something they still cannot identify.
  WM.el('btn-webhook-remove').addEventListener('click', function () {
    // webhook_status() renders a PARSE ERROR for a stored value it cannot
    // read, not only a description, so the line is interpolated as a name
    // only when it is one. Dropping to "this webhook" loses nothing the
    // dots on screen were telling the user anyway.
    var status = WM.el('webhook-status');
    var line = (status && status.textContent) || '';
    var which = (line.indexOf('/api/webhooks/') !== -1) ? line : 'this webhook';
    WM.confirm('Remove webhook',
               'Combat logs stop being posted to ' + which + ' — and '
             + 'Wingman cannot get the URL back. You would create a new '
             + 'webhook in Discord and paste it here.',
               { destructive: true })
      .then(function (ok) {
        if (!ok) { return; }
        commit('msg-discord', ['clear_discord_webhook'], null,
               function (res) {
                 current.discord_webhook = '';
                 setField('f-webhook', '');
                 renderWebhook(res.webhook_status, false);
               });
      });
  });

  // Both callers of this render the SAME two facts -- what is stored, and
  // whether the two buttons can act -- so they share one function rather
  // than one of them doing half of it. `status` is Python's
  // copy.webhook_status and is never reconstructed here; a caller with
  // nothing to say passes undefined and the line is left alone.
  function renderWebhook(status, configured) {
    if (status !== undefined) {
      WM.el('webhook-status').textContent = status
        || (configured ? '' : 'not configured');
    }
    // X1 / Settings 14. Show reveals nothing and Remove removes nothing
    // when there is no webhook stored, and both rendered at full strength.
    // The app already KNOWS neither can act from the state it is holding,
    // which is exactly WM.setEnabled's rule.
    //
    // The FIELD stays live -- it is the only route back out of the state
    // that disabled these two, which the helper's own comment forbids
    // closing off.
    WM.setEnabled('btn-webhook-show', configured);
    WM.setEnabled('btn-webhook-remove', configured);
    // A revealed webhook that is then removed would leave `Hide` on a
    // disabled button over an empty field.
    if (!configured) { remask(); }
  }

  function remask() {
    webhook.type = 'password';
    showBtn.textContent = 'Show';
    showBtn.setAttribute('aria-pressed', 'false');
  }

  // Leaving re-masks, so a revealed credential cannot be left on screen by
  // navigating away and back. Both events, not just the route: the webhook
  // is one card in a section among several, and switching to Alerts leaves
  // it just as thoroughly as switching to the Uploader does -- while
  // firing no route change at all.
  //
  // The section named here is the one the webhook card LIVES in, not a
  // sibling: round 5's E1 folded Discord into Uploading, so 'discord' is
  // no longer a section any event can carry and this test would have been
  // true on every switch -- re-masking correctly, but by accident, and
  // silently wrong again the day the card moves.
  document.addEventListener('wm:route', function (ev) {
    if (ev.detail !== 'settings') remask();
  });
  document.addEventListener('wm:section', function (ev) {
    if (ev.detail !== 'uploading') remask();
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
      // Kept, and no longer load-bearing. #preview-enabled and the Alerts
      // card used to share one section with no navigation between them
      // (alerts.js's wm:section refresh never fired), so the card would
      // otherwise keep showing a stale "watching N characters" line --
      // persistently, since the backend really did stop the poll thread --
      // until the user left and returned to the route. Round 5's D1 gave
      // Alerts its own section, so reaching that card now crosses a
      // section boundary and alerts.js refreshes on arrival by itself.
      // See the matching note on the listener there for why it stays.
      //
      // Dispatched after the bridge call settles, not on the raw change,
      // so alerts.js's get_alert_state read cannot race ahead of
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

// ---- The one dependence line for the whole card --------------------------
// Seven blocks below used to carry their own copy of this sentence, plus
// their own previewsOn/sayDependence/refreshDependence to place it. Six
// copies were identical, one had been shortened by round 3's R4, and one
// of the seven had drifted to spelling its local `enabled`. Turning the
// master switch off rendered the same sentence up to six times in one
// card, four of them inside a single 840x625 viewport.
//
// alerts.js has always done it this way for its own twelve controls, and
// the shape is the whole argument: a switch that governs a block gets ONE
// line, and the block reads as subordinate to it (`.pv-master` in
// style.css). Nothing here is disabled -- S3's rule, restated in
// ui/copy.py: recording a preference for later is an action that CAN be
// carried out, and disabling the only route to a control's own
// precondition is a dead end the reader cannot see the exit from.
//
// Does NOT open "Previews are off". That clause belongs to ui/copy.py's
// INERT_NOTES["previews_off"], which renders one card down in
// #preview-binds-off and is the single statement of the STATE (R4
// finding 3). This one carries only the consequence and the way out --
// which is the shape ui/copy.py's own note docstring asks for.
(function () {
  var slot = WM.el('preview-depends');
  var box = WM.el('preview-enabled');
  if (!slot || !box) { return; }

  slot.textContent = 'Nothing below is in effect yet — these apply when '
                   + 'you turn previews back on.';

  function refresh() { slot.hidden = !!box.checked; }

  // The settled event, not the raw `change` the per-row copies listened
  // to. set_preview_enabled can refuse, and the block above puts the box
  // back when it does; `change` fires before that is known, so the old
  // code could clear this line for a switch the backend never accepted.
  // wm:preview-enabled-changed is dispatched inside the .then(), after
  // the revert has already happened.
  document.addEventListener('wm:preview-enabled-changed', refresh);

  // ORDERING DEPENDENCY, and the reason this block sits directly below
  // the master switch's rather than with the other previews blocks: both
  // listen on wm:settings, this one reads `box.checked`, and the block
  // above is what sets it from the payload. Listeners fire in
  // registration order and the IIFEs run in source order, so the box
  // holds the new value by the time this runs -- move this block above
  // that one and the line reports the PREVIOUS payload's state, on a
  // screen where nothing else looks wrong.
  //
  // Reading `s.preview.enabled` here instead would remove the ordering
  // dependency and add a worse one: the truthiness of that key would then
  // be spelled out in two blocks with nothing holding them in step, which
  // is the shape this whole change exists to delete.
  document.addEventListener('wm:settings', refresh);

  // Hidden until the first payload lands: `hidden` is on the element in
  // index.html, and nothing here removes it before wm:settings has said
  // what the switch is. A line claiming previews are off on a screen that
  // has not loaded yet would be the hydration gate's own failure mode.
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
  // peer of the switch it depends on, with nothing saying so.
  //
  // ROUND 6 ANSWERS THAT STRUCTURALLY, and the dependence note is gone
  // from this block because of it. Saying it per-row was the first fix,
  // and round 3's R4 finding 3 already caught it going wrong -- "Previews
  // are off, so..." opening three sentences in one view -- and shortened
  // THIS one to "Applies when you turn previews back on." while leaving
  // ui/copy.py's INERT_NOTES["previews_off"] as the single statement of
  // the state. What R4 could not see from one row is that the same
  // sentence was being written into seven blocks: six long copies plus
  // this shortened one, with the machinery to place it (previewsOn,
  // sayDependence, refreshDependence) duplicated beside each. One copy had
  // already drifted, spelling its local `enabled` where the other six say
  // `enable`.
  //
  // The card now says it ONCE, in #preview-depends, the way alerts.js has
  // always said it for its own twelve controls -- and the master switch
  // carries `.pv-master`, so the block below it reads as subordinate
  // rather than as peers. The switch owning its dependants is what makes
  // one sentence enough. See the previews-depends block at the foot of
  // this file.
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
  });
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

  // Covered by #preview-depends like the rest of the card: PreviewHost.
  // restyle() only touches previews that are actually open, so with
  // previews off this sets tomorrow's label, not today's.
  box.addEventListener('change', function () {
    var wanted = box.checked;
    WM.send('set_preview_show_labels', wanted).then(function (res) {
      // WM.send resolves to null on any bridge failure rather than
      // rejecting (app.js), and a refusal may carry no error text either --
      // either way `say(res && res.error)` would clear the status line to
      // blank, telling the user nothing changed but not why. Put the box
      // back rather than show a state the app is not in, and always say
      // something.
      if (!res) {
        box.checked = !wanted;
        say('Could not reach the app. Nothing was changed.');
        return;
      }
      if (!res.applied) {
        box.checked = !wanted;
        say(res.error || 'That value was not accepted.');
        return;
      }
      if (!res.persisted) {
        say('Showing character names is ' + (wanted ? 'on' : 'off')
          + ' for this session, but could not be written to settings — '
          + 'it will not survive a restart.');
      } else {
        say('');
      }
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    // Absent means on: settings.py's default is True, and an upgrading
    // user's file predates the key.
    box.checked = !(s.preview && s.preview.show_labels === false);
  });
}());

// ---- Preview opacity --------------------------------------------------
// The "border and label stay full strength" sentence is a separate static
// hint in index.html, not this status line: it has to stay on screen even
// while this line is reporting a write failure, because it is the one
// sentence in this card that contradicts what a TriffView user would
// otherwise assume.
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

  // Round 5, C2. The control is a PERCENTAGE and the stored setting is the
  // DWM thumbnail's 0-255 alpha byte; these two are the whole conversion
  // and they are the only places either unit is crossed.
  //
  // The slider used to be min="20" max="255" with the raw value printed
  // beside it, so its floor read "20" -- which every reader takes for 20%
  // and which is 7.8%. Round 5 found the same shape three more times in
  // this app, which is why the fix is a unit change rather than a suffix.
  //
  // Not clamped here: index.html's min="8" is settings.validated_preview's
  // own 20-alpha floor expressed in percent (round(8 * 2.55) == 20), and
  // the range input enforces it. api.set_preview_opacity deliberately does
  // not clamp either -- validated_preview owns that range, in one place.
  var ALPHA_MAX = 255;
  function toAlpha(percent) {
    return Math.round(percent * ALPHA_MAX / 100);
  }
  function toPercent(alpha) {
    return Math.round(alpha * 100 / ALPHA_MAX);
  }
  function show() { readout.textContent = box.value + '%'; }

  // Live readout as the thumb moves; the setting itself commits only on
  // `change` (DESIGN.md: discrete controls commit on change, and a range
  // fires `input` per pixel dragged -- a write per pixel is the bug this
  // rule exists to prevent).
  box.addEventListener('input', show);

  box.addEventListener('change', function () {
    var wanted = parseInt(box.value, 10);
    WM.send('set_preview_opacity', toAlpha(wanted)).then(function (res) {
      // Same fallback-message gap as show_labels above: WM.send resolves
      // to null on a bridge failure, and a refusal may carry no error
      // text, so `say(res && res.error)` could clear the status line to
      // blank instead of telling the user anything.
      if (!res) {
        box.value = lastGood;
        show();
        say('Could not reach the app. Nothing was changed.');
        return;
      }
      if (!res.applied) {
        // Refused: put the slider back where it was rather than show a
        // value the app never actually took.
        box.value = lastGood;
        show();
        say(res.error || 'That value was not accepted.');
        return;
      }
      lastGood = box.value;
      if (!res.persisted) {
        say('Opacity ' + wanted + '% is set for this session, but could '
          + 'not be written to settings — it will not survive a restart.');
      } else {
        say('');
      }
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    var value = (s.preview && s.preview.opacity) || 255;
    box.value = toPercent(value);
    lastGood = box.value;
    show();
  });
}());

// ---- Hide previews while you are not in EVE ----------------------------
// Same shape as preview-snap below: a per-field endpoint reporting
// {applied, persisted, error}, a box that goes back if the write is
// refused, and the previews-off note when the setting is inert.
//
// Unlike snap, the confirmation line names WHERE the previews went. A
// setting whose whole effect is "things disappear" is the one most likely
// to be read as a bug, so ticking it says so in the same breath.
(function () {
  var box = WM.el('preview-hide-on-lost-focus');
  var status = WM.el('preview-hide-on-lost-focus-status');
  if (!box || !status) { return; }

  var DEFAULT_HINT = status.textContent;

  function say(text) { status.textContent = text || DEFAULT_HINT; }

  box.addEventListener('change', function () {
    var wanted = box.checked;
    WM.send('set_preview_hide_on_lost_focus', wanted).then(function (res) {
      if (!res || !res.applied) {
        box.checked = !wanted;
        say((res && res.error) || 'Could not save this.');
        return;
      }
      say(wanted
        ? 'Previews now hide whenever you leave EVE.'
        : 'Previews now stay on screen.');
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    // Absent means OFF here, the opposite of snap's `!== false` read: the
    // key is new and every existing install lacks it, so the wrong
    // default would blank the screen on upgrade.
    box.checked = !!(s.preview && s.preview.hide_on_lost_focus === true);
  });
}());

// ---- Snap to neighbours and screen edges -------------------------------
// Same shape as preview-show-labels above: a per-field endpoint that
// reports {applied, persisted, error}, and a box that goes back if the
// write is refused. The previews-off note is NOT here any more --
// #preview-depends states it once for the whole card.
// set_preview_snap's writer is _write_preview_setting, same as show_labels,
// so a persistence failure always comes back as `applied: false` -- there
// is no separate "saved for this session only" case to report here.
(function () {
  var box = WM.el('preview-snap');
  var status = WM.el('preview-snap-status');
  if (!box || !status) { return; }

  var DEFAULT_HINT = status.textContent;

  function say(text) { status.textContent = text || DEFAULT_HINT; }

  box.addEventListener('change', function () {
    var wanted = box.checked;
    WM.send('set_preview_snap', wanted).then(function (res) {
      if (!res || !res.applied) {
        box.checked = !wanted;
        say((res && res.error) || 'Could not save this.');
        return;
      }
      // The checkbox itself is the success feedback, which is the rule the
      // show-labels block above states and the one this block did not
      // follow: it confirmed with "Snapping is on.", a sentence the label
      // beside the box already says.
      //
      // That was survivable while this slot held a default hint of about
      // the same height -- the confirmation replaced it and the card did
      // not move. Round 6 deleted that hint (it inverted the label and
      // said nothing else), so the slot is empty, its row is collapsed by
      // the empty-row rule in style.css, and an unconditional confirmation
      // here would ADD a line on first toggle and never take it back.
      // Clearing restores the collapsed row instead. Errors are unaffected
      // -- the branch above still speaks, and for this endpoint a failed
      // write arrives as `applied: false` rather than as a silent success.
      say('');
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    box.checked = !(s.preview && s.preview.snap === false);
  });
}());

// ---- Keep previews the same shape as their client ----------------------
// Same shape as preview-snap above, and live for the same reason: the
// flag is sampled when a resize drag begins, so a write that did not
// restyle would leave this inert until the next launch.
(function () {
  var box = WM.el('preview-lock-aspect');
  var status = WM.el('preview-lock-aspect-status');
  if (!box || !status) { return; }

  var DEFAULT_HINT = status.textContent;

  function say(text) { status.textContent = text || DEFAULT_HINT; }

  box.addEventListener('change', function () {
    var wanted = box.checked;
    WM.send('set_preview_lock_aspect', wanted).then(function (res) {
      if (!res || !res.applied) {
        box.checked = !wanted;
        say((res && res.error) || 'Could not save this.');
        return;
      }
      say(wanted
        ? 'Previews keep their client\u2019s shape.'
        : 'The resize handle is freeform; the picture will stretch.');
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    box.checked = !(s.preview && s.preview.lock_aspect === false);
  });
}());

// ---- Lock previews by default ------------------------------------------
// A discrete control, so it commits on change (DESIGN.md). What it says is
// not "lock everything": preview.locked holds the characters that DIFFER
// from this, so ticking locks every character whose own box has not been
// changed. PreviewHost._is_locked resolves the pair; nothing here does.
//
// Unticking is not an undo. It restores the previous arrangement only if
// no per-character box was touched while it was on -- a box changed under
// a locked default means the opposite thing once the default goes back
// off. api.py's set_preview_lock_default carries the worked example.
(function () {
  var box = WM.el('preview-lock-default');
  var status = WM.el('preview-lock-default-status');
  if (!box || !status) { return; }

  var DEFAULT_HINT = status.textContent;
  function say(text) { status.textContent = text || DEFAULT_HINT; }

  box.addEventListener('change', function () {
    var wanted = box.checked;
    WM.send('set_preview_lock_default', wanted).then(function (res) {
      if (!res || !res.applied) {
        box.checked = !wanted;
        say((res && res.error) || 'Could not save this.');
        return;
      }
      // The Lock disclosure is directly beneath this toggle, on screen
      // right now, and every one of its checkboxes paints from this
      // boolean -- isLocked() resolves membership against it with an XOR
      // -- so a write that only touched settings would leave all of them
      // showing the exact inverse of the truth, silently, until the next
      // full reload. Its summary sentence resolves the same pair and
      // would be inverted with them.
      // Same narrow exception, same shape, and the same reason as
      // wm:preview-minimize-inactive below: wm:settings is deliberately
      // never re-dispatched after a single-field write, because repainting
      // the whole form would clobber whatever else is mid-edit.
      document.dispatchEvent(new CustomEvent('wm:preview-lock-default', {
        detail: { enabled: wanted }
      }));
      say(wanted
        ? 'New previews open locked. Untick a preview\'s Lock to move it.'
        : 'New previews can be right-dragged to move.');
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    box.checked = !!(s.preview && s.preview.lock_default);
  });
}());

// ---- Default preview size ----------------------------------------------
// FREE TEXT, so it commits on Enter and never on blur -- DESIGN.md's rule,
// and it bites here specifically: half a typed "1280x720" is "1280x72",
// which is a real size this would otherwise have saved on the way past.
//
// The page does not parse it. parse_preview_size is Python's, the same
// endpoint the per-character Size... dialog uses, so the one definition of
// what a size looks like stays in a module the suite can execute.
(function () {
  var field = WM.el('preview-default-size');
  var status = WM.el('preview-default-size-status');
  if (!field || !status) { return; }

  var DEFAULT_HINT = status.textContent;
  // The undistorted-size sentence, same helper text the per-character
  // Size... dialog shows, carried onto the global field. Built from the
  // ONE-SHOT hotkey-state read below: client sizes are live host data,
  // not persisted settings, so wm:settings never carries them.
  var clientHint = '';
  function say(text) {
    status.textContent = text || (DEFAULT_HINT + clientHint);
  }

  // Set from the payload, and compared against on commit so re-entering
  // the same value is a no-op rather than a write. Also what a refusal
  // reverts to: there is no Cancel on this page and no pre-edit snapshot
  // anywhere else, so the field has to carry its own way back.
  var applied = '';

  function commit() {
    var text = field.value.trim();
    if (text === applied) { return; }
    if (text === '') { field.value = applied; say(''); return; }
    WM.send('parse_preview_size', text).then(function (parsed) {
      // A null reply is a bridge failure, not a parse verdict. Reverting
      // and saying so matters more here than in the per-character Size...
      // dialog, which just closes: this is a PERSISTENT field, so leaving
      // the typed text in place would make the control state a size the
      // app is not using, with the hint still reading "Press Enter to
      // save" and nothing ever coming to correct it.
      if (!parsed) { field.value = applied; say('Could not save this.'); return; }
      if (parsed.error) { say(parsed.error); return; }
      WM.send('set_preview_default_size', parsed.w, parsed.h)
        .then(function (res) {
          if (!res || !res.applied) {
            field.value = applied;
            say((res && res.error) || 'Could not save this.');
            return;
          }
          applied = parsed.w + 'x' + parsed.h;
          appliedW = parsed.w;
          field.value = applied;
          // Three outcomes, not two (DESIGN.md): applied-but-not-persisted
          // leaves the control alone and warns that it will not survive a
          // restart, rather than reverting a change that really did take.
          say(res.persisted
              ? 'New previews open at ' + applied + '.'
              : 'Saved for this session only — settings could not be '
                + 'written.');
        });
    });
  }

  field.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); commit(); }
  });

  // The hint's undistorted half: for the first running client, the height
  // the current default width would need. Refreshed when the payload (or
  // a commit) changes the width, because the sentence quotes it.
  function rebuildClientHint() {
    if (!clientHintState) { return; }
    var name = Object.keys(clientHintState)[0];
    var client = name && clientHintState[name];
    if (!client) { clientHint = ''; return; }
    // Chrome is BORDER*2 across and down and nothing else -- the name is
    // an overlay above the video, not a band the picture shrinks for.
    // appliedW is the payload's own number, never re-parsed from text:
    // geometry.py owns what a size is, and this page never parses one.
    var width = appliedW || 320;
    var tall = Math.round((width - 4) * client[1] / client[0]) + 4;
    clientHint = ' ' + name + "'s client is " + client[0] + 'x' + client[1]
               + '; at ' + width + ' wide an undistorted preview is '
               + width + 'x' + tall + '.';
  }

  var clientHintState = null;
  var appliedW = 0;
  WM.send('get_preview_hotkey_state').then(function (payload) {
    clientHintState = (payload && payload.client_sizes) || null;
    rebuildClientHint();
    // Repaint only if no action message is showing; an outcome sentence
    // the user just earned outranks evergreen guidance.
    if (status.textContent === DEFAULT_HINT) { say(''); }
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    var p = s.preview || {};
    if (p.width && p.height) {
      applied = p.width + 'x' + p.height;
      appliedW = p.width;
      // Never while the user is mid-type: this fires on every per-field
      // write anywhere in Settings, and rewriting a focused field is what
      // the whole-document push used to do.
      if (document.activeElement !== field) { field.value = applied; }
      rebuildClientHint();
    }
  });
}());

// ---- Apply the default size to open previews ----------------------------
// The button half of the default-size field: Enter decides where the NEXT
// preview opens, this one resizes what is on screen now. Deliberately a
// separate action rather than a side effect of the commit -- a field that
// rearranges the screen every time it is saved is a field you save once
// and then never touch again.
(function () {
  var btn = WM.el('btn-preview-apply-size');
  var status = WM.el('preview-apply-size-status');
  if (!btn || !status) { return; }

  function say(text) { status.textContent = text || ''; }

  btn.addEventListener('click', function () {
    WM.send('apply_preview_default_size').then(function (res) {
      // A null reply is a bridge failure; anything else carries the
      // applied/error pair every field writer here uses.
      if (!res) { say('Could not resize the previews.'); return; }
      say(res.applied ? 'Resized every open preview.'
                      : (res.error || 'Could not resize the previews.'));
    });
  });
}());

// ---- Selection ring colour ----------------------------------------------
// A fixed palette of radios, not <input type="color">. alerts.js made this
// argument first and style.css's `.swatches` block records it: the native
// control opened
// the Win32 ChooseColor dialog and offered 16.7 million answers to a
// question with about five. Everything below is that decision applied to
// the one site it had not reached.
//
// Still a discrete control, so it still commits on change -- DESIGN.md's
// rule; there is no half-typed state to protect. The #rrggbb string is
// shipped verbatim and never unpacked here: Python owns the format, the
// same division the size field keeps with parse_preview_size.
(function () {
  var host = WM.el('preview-selection-color');
  var status = WM.el('preview-selection-color-status');
  if (!host || !status) { return; }

  // Five, well separated in hue and all bright enough to hold up as a
  // 1px-ish ring over moving game content.
  //
  // Teal first because it is settings.py's default AND window.py's
  // (0,200,220) -- test_page_conventions pins that the default is offered,
  // for the reason alerts.js gives: a default outside the palette would
  // render as an unlabelled sixth swatch on every fresh install.
  //
  // NO RED, deliberately, and it is the mirror of alerts.js's "no second
  // teal". That palette refuses teal because this ring owns it; this one
  // refuses red because alerts own it -- combat's default is #ff4d4d, and
  // a steady red ring around the selected client, beside a red pulse
  // meaning "you are being shot", is the one confusion in this app that
  // costs something. The two palettes are complementary on purpose.
  var COLOURS = ['#00c8dc', '#ffd24d', '#4dff7a', '#ff4db8', '#f5f7fa'];
  var COLOUR_NAMES = ['Teal', 'Amber', 'Green', 'Magenta', 'White'];

  function colourName(hex) {
    var i = COLOURS.indexOf(hex);
    return i === -1 ? hex : COLOUR_NAMES[i];
  }

  var DEFAULT_HINT = status.textContent;
  function say(text) { status.textContent = text || DEFAULT_HINT; }

  // Last-known-good, so a refused or bridge-failed change has something to
  // revert to: by the time 'change' fires the browser has committed the
  // new value into the radio, so the control cannot tell us what it was.
  var lastGood = '';

  // Lifted from alerts.js's paintSwatches, including the data-built guard
  // that makes a repaint from wm:settings a no-op when nothing changed --
  // rebuilding under the pointer would drop focus mid-choose.
  function paint(colour) {
    var wanted = COLOURS.slice();
    // An out-of-palette value (a hand-edited settings.json) is appended
    // rather than silently rewritten to a palette entry. Same escape hatch
    // alerts.js keeps, and the same reason: the file is the user's.
    if (colour && wanted.indexOf(colour) === -1) { wanted.push(colour); }

    if (host.getAttribute('data-built') !== wanted.join(',')) {
      host.textContent = '';
      wanted.forEach(function (hex) {
        var label = WM.make('label', 'swatch');
        var input = document.createElement('input');
        input.type = 'radio';
        input.name = 'preview-selection-color';
        input.value = hex;
        var dot = WM.make('span', 'dot');
        dot.style.setProperty('--swatch', hex);
        var name = colourName(hex);
        label.title = name === hex ? hex : name + ' (' + hex + ')';
        input.setAttribute('aria-label', name);
        label.appendChild(input);
        label.appendChild(dot);
        host.appendChild(label);
      });
      host.setAttribute('data-built', wanted.join(','));
    }

    var boxes = host.querySelectorAll('input');
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].checked = boxes[i].value === colour;
    }
  }

  // One listener on the host rather than one per radio, so a repaint does
  // not have to re-bind: the radios are replaced, the host is not.
  host.addEventListener('change', function (ev) {
    var input = ev.target;
    if (!input || input.type !== 'radio') { return; }
    var wanted = input.value;
    WM.send('set_preview_selection_color', wanted).then(function (res) {
      if (!res || !res.applied) {
        // Never took effect, so the control must not go on showing it.
        // `|| COLOURS[0]` for the same reason alerts.js keeps `|| wanted`
        // on its revert: paint('') would uncheck every swatch and leave a
        // palette with no selection, which is a state the setting cannot
        // actually be in.
        paint(lastGood || COLOURS[0]);
        say((res && res.error) || 'Could not save this.');
        return;
      }
      lastGood = wanted;
      say(res.persisted ? ''
        : 'Applied for this session only — settings could not be written.');
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var p = ((ev.detail || {}).settings || {}).preview || {};
    // Falls back rather than returning, which alerts.js (applyAlerts) also
    // does and for a sharper reason here: this listener is the ONLY thing
    // that ever builds these swatches, so a payload without the key would
    // leave a labelled row with no control in it at all -- silently, since
    // an empty container throws nothing. Unreachable today, because
    // validated_preview starts from _preview_defaults(); one `||` is
    // cheaper than depending on that staying true.
    lastGood = p.selection_color || COLOURS[0];
    // Unlike the old picker this cannot be "open", so there is no focused
    // state to protect -- and data-built makes a repaint a no-op unless the
    // palette SET changed, which is what keeps focus where it was.
    paint(lastGood);
  });
}());

// ---- Reset previews to defaults ----------------------------------------
// A one-shot action, not a persistent field: there is nothing to revert
// on refusal and nothing to read back from wm:settings. WM.confirm's
// body names the irreversibility plainly and quotes no count -- the
// number of saved layouts is derivable, and this repo's rule is that a
// derived number is derived or test-asserted, never retyped by hand.
(function () {
  var btn = WM.el('preview-reset');
  var status = WM.el('preview-reset-status');
  if (!btn || !status) { return; }

  var DEFAULT_HINT = status.textContent;

  function say(text) { status.textContent = text || DEFAULT_HINT; }

  btn.addEventListener('click', function () {
    WM.confirm('Reset previews',
               'Every preview goes back to its default size and place. The '
             + 'positions you have dragged are discarded, and Wingman '
             + 'cannot get them back.',
               { destructive: true })
      .then(function (ok) {
        if (!ok) { return; }
        WM.send('reset_preview_layouts').then(function (res) {
          say(res && res.applied
              ? 'Previews are back at their defaults.'
              : ((res && res.error) || 'Could not reset previews.'));
        });
      });
  });
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

  box.addEventListener('change', function () {
    var wanted = box.checked;
    WM.send('set_minimize_inactive_clients', wanted).then(function (res) {
      // Same fallback-message gap as show_labels/opacity above: `say(res
      // && res.error)` clears the status line to blank on a bridge
      // failure or an unexplained refusal instead of saying anything.
      if (!res) {
        box.checked = !wanted;
        say('Could not reach the app. Nothing was changed.');
        return;
      }
      if (!res.applied) {
        box.checked = !wanted;
        say(res.error || 'That value was not accepted.');
        return;
      }
      // applied is true whether or not persistence succeeded -- update.
      // update never reverts the in-memory dict on an OSError, only on
      // raising before that (see _write_preview_setting's own comment),
      // so the live value really did change here and previews.js needs to
      // know now, not at the next full page load. It decides more than an
      // enabled state: D6 says the Never-minimize disclosure beneath this
      // toggle is absent entirely while the toggle is off, so this event
      // is what makes the whole block appear and disappear.
      // wm:settings itself cannot carry this: it is
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
      }
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    // Absent means off: matches build_preview_host's minimize_inactive_
    // clients closure default (__main__.py) -- minimizing a real EVE
    // client window must be asked for, never assumed on upgrade.
    box.checked = !!(s.preview && s.preview.minimize_inactive_clients);
  });

  // ---- floating sig bar ----------------------------------------------
  // One checkbox, one endpoint, no local state: onSigBarState is the
  // state (it repaints the status-strip button too, bookmarks.js), and
  // wm:settings hydrates the box on load like every other field here.
  (function () {
    var check = WM.el('sigbar-enabled');
    var enabledStatus = WM.el('sigbar-enabled-status');

    document.addEventListener('wm:settings', function (ev) {
      var section = (ev.detail || {}).settings
        && (ev.detail || {}).settings.sig_bar;
      if (!section) { return; }
      if (check !== document.activeElement) { check.checked = !!section.enabled; }
    });

    check.addEventListener('change', function () {
      commit(enabledStatus, ['toggle_sig_bar', check.checked], null);
    });
  }());

  // ---- FightRecorder (OBS plugin) -------------------------------------
  // Local-on-load, network-on-demand: the initial state line comes from
  // fightrecorder_status's local half, and only the two buttons call
  // GitHub. Install/Update may raise ONE UAC prompt (OBS's plugin
  // directory is under Program Files; Wingman runs without admin), so
  // the button is disabled for the duration rather than allowing a
  // second click into a pending elevation.
  (function () {
    var status = WM.el('fr-status');
    var checkBtn = WM.el('btn-fr-check');
    var updateBtn = WM.el('btn-fr-update');
    var msg = WM.el('msg-fightrecorder');
    if (!status || !checkBtn || !updateBtn || !msg) { return; }

    function paint(res) {
      var text;
      var canInstall = false;
      if (!res) {
        text = 'Could not read the plugin state.';
      } else if (res.error) {
        text = res.error;
      } else if (!res.detected) {
        text = 'OBS Studio was not detected.';
      } else if (!res.installed) {
        text = 'Not installed.';
        canInstall = true;
      } else if (res.up_to_date === true) {
        text = 'Up to date.';
      } else if (res.up_to_date === false) {
        text = 'An update is available' +
               (res.latest_tag ? ' (' + res.latest_tag + ')' : '') + '.';
        canInstall = true;
      } else {
        text = 'Installed.' +
               (res.latest_tag ? ' Latest release: ' + res.latest_tag + '.' : '');
        canInstall = true;
      }
      status.textContent = text;
      updateBtn.hidden = !canInstall;
      updateBtn.textContent = res && res.installed ? 'Update' : 'Install';
    }

    function sayError(text) {
      msg.textContent = text;
      msg.hidden = false;
    }

    function busy(on) {
      WM.setEnabled('btn-fr-check', !on);
      WM.setEnabled('btn-fr-update', !on);
      if (on) { msg.hidden = true; }
    }

    function refresh(live) {
      busy(true);
      WM.send('fightrecorder_status', !!live).then(function (res) {
        busy(false);
        paint(res);
      });
    }

    checkBtn.addEventListener('click', function () { refresh(true); });

    updateBtn.addEventListener('click', function () {
      busy(true);
      status.textContent = 'Downloading and installing…';
      WM.send('update_fightrecorder').then(function (res) {
        busy(false);
        if (!res) { sayError('Could not reach the installer.'); return; }
        if (!res.ok) { sayError(res.error || 'The update did not happen.'); }
        else { status.textContent = 'Updated to ' + res.tag + '.'; }
        // The local half re-runs so the buttons match what is on disk.
        refresh(false);
      });
    });

    refresh(false);
  }());
}());
