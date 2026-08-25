// ---- Gamelog alerts --------------------------------------------------
// Third card in Settings > Previews, alongside previews.js and the
// keybind block in settings.js. Not folded into either: this owns none
// of the win32/AutoHotkey machinery those files do, and gets its own
// bridge endpoints for the same reason set_preview_enabled does --
// toggling `enabled` here starts or stops a polling thread (the gamelog
// tailer), not merely a settings write.
//
// A READ, not a push: get_alert_state exists precisely so this can ask
// on wm:section, the same reasoning get_preview_hotkey_state documents --
// the tailer can start before the webview exists (start_previews_if_
// enabled runs before window_mod.run()), so a health change discovered
// at launch would be pushed into a window that is not there yet.
(function () {
  var enabledBox = WM.el('alert-enabled');
  if (!enabledBox) { return; }

  var pveBox = WM.el('alert-pve-filter');
  var persistBox = WM.el('alert-persist');
  var offBanner = WM.el('alerts-previews-off');
  var folderBanner = WM.el('alerts-no-folder');
  var healthLine = WM.el('alerts-health');
  var status = WM.el('alerts-status');

  var EVENTS = [
    {id: 'combat', label: 'Combat'},
    {id: 'warp_scramble', label: 'Warp scramble'},
    {id: 'decloak', label: 'Decloak'}
  ];

  // Last-known-good color/sound per event, so a refused or bridge-
  // failed change has something to revert the control to -- by the
  // time 'change' fires the browser has already committed the new
  // value into the element, so the element itself cannot tell us
  // what it was before.
  var lastGood = {};

  function say(text) { if (status) { status.textContent = text || ''; } }

  function eventRow(id) {
    return {
      enabled: WM.el('alert-event-' + id + '-enabled'),
      color: WM.el('alert-event-' + id + '-color'),
      sound: WM.el('alert-event-' + id + '-sound'),
      test: WM.el('alert-event-' + id + '-test')
    };
  }

  // Shared by the wm:settings hydration and refresh() (get_alert_state),
  // so the per-event rows repaint from the same shape either way.
  function applyAlerts(alerts) {
    var events = (alerts && alerts.events) || {};
    EVENTS.forEach(function (ev) {
      var row = eventRow(ev.id);
      if (!row.enabled) { return; }
      var spec = events[ev.id] || {};
      row.enabled.checked = !!spec.enabled;
      var color = spec.color || row.color.value;
      var sound = spec.sound || 'none';
      row.color.value = color;
      row.sound.value = sound;
      lastGood[ev.id] = {color: color, sound: sound};
    });
  }

  // Shared by all three top-level checkboxes. WM.send resolves to null
  // on a bridge failure (app.js) -- that reverts the box, same as
  // `applied: false`, which the bridge now also returns when a settings
  // write raised and was rolled back (api.py's _write_alert_setting):
  // the value genuinely never took effect, so leaving the checkbox
  // showing it would be showing a state the app is not in. Only
  // `applied: true, persisted: false` (a session-only write) leaves the
  // box alone -- that one really did take effect, and reverting it
  // would be the opposite lie. Mirrors set_restore_preview_positions in
  // previews.js.
  function writeFlag(box, method, label) {
    box.addEventListener('change', function () {
      var wanted = box.checked;
      WM.send(method, wanted).then(function (res) {
        if (!res || !res.applied) {
          box.checked = !wanted;
          if (res && res.error) { say(res.error); }
          return;
        }
        if (!res.persisted) {
          say(label + ' is ' + (wanted ? 'on' : 'off')
            + ' for this session, but could not be written to settings — '
            + 'it will not survive a restart.');
        } else {
          say('');
        }
        if (method === 'set_alert_enabled') { refresh(); }
      });
    });
  }

  writeFlag(enabledBox, 'set_alert_enabled', 'Alerts');
  writeFlag(pveBox, 'set_alert_pve_filter', 'The PvE filter');
  writeFlag(persistBox, 'set_alert_persist', 'Persisting alerts');

  EVENTS.forEach(function (ev) {
    var row = eventRow(ev.id);
    if (!row.enabled) { return; }

    row.enabled.addEventListener('change', function () {
      var wanted = row.enabled.checked;
      WM.send('set_alert_event', ev.id, 'enabled', wanted).then(function (res) {
        // set_alert_event refuses an unknown event/field outright but a
        // clamped value is still applied -- only a refusal or a bridge
        // failure reverts the box.
        if (!res || !res.applied) { row.enabled.checked = !wanted; }
      });
    });
    row.color.addEventListener('change', function () {
      var wanted = row.color.value;
      WM.send('set_alert_event', ev.id, 'color', wanted).then(function (res) {
        if (!res || !res.applied) {
          row.color.value = (lastGood[ev.id] || {}).color || wanted;
          return;
        }
        lastGood[ev.id] = lastGood[ev.id] || {};
        lastGood[ev.id].color = wanted;
        if (!res.persisted) {
          say(ev.label + ' colour is set for this session, but could not '
            + 'be written to settings — it will not survive a restart.');
        } else {
          say('');
        }
      });
    });
    row.sound.addEventListener('change', function () {
      var wanted = row.sound.value;
      WM.send('set_alert_event', ev.id, 'sound', wanted).then(function (res) {
        if (!res || !res.applied) {
          row.sound.value = (lastGood[ev.id] || {}).sound || wanted;
          return;
        }
        lastGood[ev.id] = lastGood[ev.id] || {};
        lastGood[ev.id].sound = wanted;
        if (!res.persisted) {
          say(ev.label + ' sound is set for this session, but could not '
            + 'be written to settings — it will not survive a restart.');
        } else {
          say('');
        }
      });
    });
    row.test.addEventListener('click', function () {
      // Never persistent (api.py's test_alert docstring): nothing here
      // is looking at a preview to acknowledge it, so nothing is saved.
      WM.send('test_alert', ev.id).then(function (res) {
        if (res && res.error) { say(res.error); }
      });
    });
  });

  // The health line and the character count are ALWAYS one sentence, on
  // purpose: a count rendered on its own keeps reading "watching 4
  // characters" after the tailer thread has died, which is a healthy-
  // looking card sitting above a feature that stopped alerting.
  function healthText(state) {
    if (!state.running) {
      return state.last_error
        ? 'Not watching gamelogs — ' + state.last_error
        : 'Not watching gamelogs.';
    }
    var n = (state.characters || []).length;
    return 'Watching gamelogs — ' + n + ' character'
      + (n === 1 ? '' : 's') + ' online.';
  }

  // Three states, and a card that silently shows nothing is the failure
  // mode this feature exists to avoid:
  //   1. Previews off -- alerts cannot draw, so say that plainly.
  //   2. No Gamelogs folder -- the important one, since without it
  //      alerts silently do nothing, indistinguishable from nothing
  //      happening in game.
  //   3. Otherwise, the health line above (running + character count).
  function render(state) {
    if (offBanner) {
      offBanner.style.display = state.previews_enabled ? 'none' : '';
    }
    if (folderBanner) {
      folderBanner.style.display = state.gamelogs_folder ? 'none' : '';
    }
    if (healthLine) { healthLine.textContent = healthText(state); }
    applyAlerts(state.alerts);
  }

  function refresh() {
    WM.send('get_alert_state').then(function (state) {
      if (!state) { return; }
      render(state);
    });
  }

  // panel.js owns onSettings and re-dispatches it; the three checkboxes
  // and the per-event rows hydrate from `preview.alerts`, which
  // _settings_payload ships for free as part of its shallow dict(cfg).
  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    var alerts = (s.preview && s.preview.alerts) || {};
    enabledBox.checked = !!alerts.enabled;
    // Absent means on, matching restore-preview-positions's precedent in
    // previews.js: an upgrading user's file predates the key.
    pveBox.checked = alerts.pve_filter !== false;
    persistBox.checked = alerts.persist_until_selected !== false;
    applyAlerts(alerts);
  });

  // Refreshed on route entry, same reasoning as previews.js and
  // bookmarks.js: this is a read, not a push, so nothing keeps it
  // current while the tab is not showing.
  document.addEventListener('wm:section', function (event) {
    if (event.detail === 'previews') { refresh(); }
  });

  // #preview-enabled and this card share ONE section (#section-previews)
  // with no navigation between them, so toggling previews off must not
  // wait for a route change to stop showing a healthy-looking card:
  // set_preview_enabled really does stop the poll thread. settings.js
  // dispatches this once its own bridge call settles (not on the raw
  // DOM change), so this refresh cannot race ahead of the host.stop() /
  // alerts.reconcile() that call performs.
  document.addEventListener('wm:preview-enabled-changed', refresh);
}());
