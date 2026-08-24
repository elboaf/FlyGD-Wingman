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

  function render(payload) {
    var s = payload.settings || {};
    var d = payload.detected || {};
    current = s;
    detected = d;
    WM.el('f-privacy').value = s.privacy || 'unlisted';
    WM.el('f-category').value = s.category || '20';
    setNotify(s.notify_mode || 'toast');
    WM.el('f-recdir').value = s.recording_dir || '';
    WM.el('f-gamelogs').value = s.gamelogs_dir || '';
    // The input holds the REAL value and the browser draws the mask, so
    // the mask can never be written back over the stored webhook — the
    // failure mode a hand-rolled bullet string invites.
    WM.el('f-webhook').value = s.discord_webhook || '';
    // webhook_status() is a pure Python function with its own test and is
    // the only description of what is stored; discord.describe omits the
    // token by construction. TOP-LEVEL key, and never reconstructed here.
    WM.el('webhook-status').textContent = payload.webhook_status
      || (s.discord_webhook ? '' : 'not configured');
    // Detect is always offered, but say so when there is nothing to find.
    WM.el('detect-note').textContent = (d.recording || d.gamelogs)
      ? 'Detect reads the recording folder from OBS’s own config, and the '
        + 'gamelogs folder from your EVE Online documents folder.'
      : 'Detect found neither folder automatically — use Browse to pick '
        + 'them yourself.';
  }

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

  function applyFolder(which, path) {
    if (!path) return;   // a cancelled dialog is also a valid result
    var field = WM.el(TARGET_FIELD[which]);
    if (field) field.value = path;
  }

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

  function remask() {
    webhook.type = 'password';
    showBtn.textContent = 'Show';
    showBtn.setAttribute('aria-pressed', 'false');
  }

  // Leaving the screen re-masks, so a revealed credential cannot be left
  // on screen by navigating away and back.
  document.addEventListener('wm:route', function (ev) {
    if (ev.detail !== 'settings') remask();
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

  // ---- save / cancel --------------------------------------------------
  function collect() {
    return {
      privacy: WM.el('f-privacy').value,
      category: WM.el('f-category').value.trim(),
      notify_mode: notifyValue(),
      recording_dir: WM.el('f-recdir').value.trim() || null,
      gamelogs_dir: WM.el('f-gamelogs').value.trim() || null,
      // The real value, never the mask.
      discord_webhook: webhook.value.trim(),
      // Carried through untouched: settings.save projects onto DEFAULTS'
      // keys, so anything omitted here is dropped on every write.
      channel_id: current.channel_id || '',
      channel_title: current.channel_title || ''
    };
  }

  WM.el('btn-settings-save').addEventListener('click', function () {
    // save_settings rebinds the live watcher when recording_dir changes;
    // persisting the setting alone leaves the watcher on the old folder.
    // That is Python's job, not the page's. It returns false when it
    // refused, and the form stays open so the edits are not lost.
    //
    // `!ok` rather than `=== false`: WM.send resolves to null on any bridge
    // failure, and treating that as success would navigate away with the
    // form reset and nothing saved — the exact outcome this guard exists
    // to prevent.
    WM.send('save_settings', collect()).then(function (ok) {
      if (!ok) return;
      remask();
      WM.route('main');
    });
  });

  WM.el('btn-settings-cancel').addEventListener('click', function () {
    render({ settings: current, detected: detected,
             webhook_status: WM.el('webhook-status').textContent });
    remask();
    WM.route('main');
  });
}());

// ---- EVE client previews -------------------------------------------------
// Deliberately not in bookmarks.js: that module owns the AutoHotkey engine
// and its status plumbing, and previews share none of it.
//
// Also not part of collect()/save_settings above: toggling this has to
// start or stop a thread, not just persist a field, so it calls its own
// endpoint.
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
// Separate from the previews block above, and not part of collect()/
// save_settings either: this key is written by its own bridge method so a
// write that fails can be reported rather than silently lost.
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
