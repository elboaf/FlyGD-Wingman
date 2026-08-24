/* FlyGD Wingman — the EVE Settings route.
 *
 * Deliberately dumb, for the same reason bookmarks.js is: this repo has no
 * way to test JavaScript (webview-replatform-design.md:545), so every
 * decision -- what is a valid target, what may be overwritten, what gets
 * backed up -- happens in Python. This file captures events, sends them,
 * and renders the answer.
 */
(function () {
  'use strict';

  var state = null;
  var selected = {};
  // The rows renderTargets() actually drew. Select-all and the copy list
  // are both taken from this rather than from rows(), so what the filter
  // shows and what the button acts on can never disagree.
  var visible = [];
  var busy = false;

  function kind() {
    var checked = document.querySelector('input[name="es-kind"]:checked');
    return checked ? checked.value : 'characters';
  }

  function rows() {
    if (!state) return [];
    return kind() === 'accounts' ? state.accounts : state.characters;
  }

  function refresh() {
    WM.send('eve_settings_state').then(render);
  }

  function render(payload) {
    if (!payload) return;
    state = payload;
    WM.el('es-root').textContent = payload.root || 'No folder selected';
    paintPill(payload.eve_running);

    var warning = WM.el('es-warning');
    // "Couldn't read", "too wide to be an EVE folder" and "nothing there"
    // are three different answers, and each asks the user for something
    // different. Python decides which; this only picks the sentence.
    warning.hidden = !(payload.unreadable || payload.too_broad);
    if (payload.too_broad) {
      warning.textContent =
        'That folder was too large to search fully, so this list may be '
        + 'incomplete. Pick the EVE folder itself, usually '
        + (payload.default_root || '%LOCALAPPDATA%\\CCP\\EVE') + '.';
    } else if (payload.unreadable) {
      warning.textContent =
        "Couldn't read that folder. Check it still exists and is readable.";
    } else {
      warning.textContent = '';
    }

    fill('es-server', payload.servers, payload.server);
    fill('es-profile', payload.profiles, payload.profile);
    renderSource();
    renderTargets();
    renderBackups();
  }

  // Three states, not two. null means the probe has not answered yet, and
  // rendering that as "EVE closed" would be a reassuring guess about the
  // only warning shown before a copy -- the probe runs off the bridge
  // thread precisely because its first pass is slow.
  function paintPill(running) {
    var pill = WM.el('es-eve-state');
    if (!pill) return;
    if (running === null || running === undefined) {
      pill.textContent = 'Checking for EVE\u2026';
      pill.className = 'pill idle';
      return;
    }
    pill.textContent = running ? 'EVE running' : 'EVE closed';
    pill.className = 'pill ' + (running ? 'warn' : 'idle');
  }

  function fill(id, items, current) {
    var el = WM.el(id);
    el.innerHTML = '';
    (items || []).forEach(function (item) {
      var option = document.createElement('option');
      option.value = item.path;
      option.textContent = item.name;
      option.selected = item.path === current;
      el.appendChild(option);
    });
  }

  function renderSource() {
    var el = WM.el('es-source');
    var previous = el.value;
    el.innerHTML = '';
    rows().forEach(function (row) {
      var option = document.createElement('option');
      option.value = row.path;
      option.textContent = row.name;
      option.selected = row.path === previous;
      el.appendChild(option);
    });
  }

  function renderTargets() {
    var host = WM.el('es-targets');
    var needle = (WM.el('es-filter').value || '').toLowerCase();
    var source = WM.el('es-source').value;
    host.innerHTML = '';
    visible = [];
    rows().forEach(function (row) {
      if (row.path === source) return;
      if (needle && row.name.toLowerCase().indexOf(needle) === -1) return;
      visible.push(row);
      var label = document.createElement('label');
      label.className = 'row';
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.value = row.path;
      box.checked = !!selected[row.path];
      box.addEventListener('change', function () {
        selected[row.path] = box.checked;
      });
      label.appendChild(box);
      label.appendChild(document.createTextNode(' ' + row.name));
      host.appendChild(label);
    });
  }

  function renderBackups() {
    var host = WM.el('es-backups');
    host.innerHTML = '';
    // An empty list means one of two things and only Python knows which.
    // Saying "No backups yet" about a store we were denied would invite an
    // overwrite the user believes is protected.
    if (state.backups_unreadable || !(state.backups || []).length) {
      var note = document.createElement('p');
      note.className = 'hint';
      note.textContent = state.backups_unreadable
        ? "Couldn't read the backups folder. Check it is still readable."
        : 'No backups yet.';
      host.appendChild(note);
      if (state.backups_unreadable) return;
    }
    (state.backups || []).forEach(function (item) {
      var line = document.createElement('div');
      line.className = 'row';
      line.appendChild(document.createTextNode(
        item.created + ' · ' + item.kind + ' · ' + item.stem
        + (item.origin === 'auto' ? ' (auto)' : '')));
      line.appendChild(button('Restore', function () {
        mutate('eve_settings_restore', item.path);
      }));
      line.appendChild(button('Delete', function () {
        mutate('eve_settings_delete_backup', item.path);
      }));
      host.appendChild(line);
    });
  }

  function button(text, handler) {
    var el = document.createElement('button');
    el.className = 'btn';
    el.textContent = text;
    el.disabled = busy;
    el.addEventListener('click', handler);
    return el;
  }

  function chosenTargets() {
    // Only what is on screen: a path checked before the filter narrowed,
    // or before it became the source, is no longer a target the user can
    // see and must not inflate the confirmation's count.
    return visible.filter(function (row) {
      return !!selected[row.path];
    }).map(function (row) { return row.path; });
  }

  function setBusy(value) {
    busy = value;
    WM.el('es-copy').disabled = value;
    WM.el('es-backup-profile').disabled = value;
    Array.prototype.forEach.call(
      WM.el('es-backups').querySelectorAll('button'), function (el) {
        el.disabled = value;
      });
  }

  function mutate(method) {
    // Every mutation goes through here. The bridge returns as soon as the
    // worker is spawned, so a falsy answer means no worker started (the
    // lock was held, or the spawn failed) and nothing will ever push --
    // anything else waits for onEveSettingsDone.
    var args = Array.prototype.slice.call(arguments);
    if (busy) return;
    setBusy(true);
    WM.send.apply(null, args).then(function (accepted) {
      if (!accepted) setBusy(false);
    });
  }

  function wire() {
    WM.el('es-pick').addEventListener('click', function () {
      WM.send('eve_settings_pick_root').then(function () {
        selected = {};
        refresh();
        WM.send('eve_settings_resolve_names');
      });
    });

    ['es-server', 'es-profile'].forEach(function (id) {
      WM.el(id).addEventListener('change', function () {
        // A source picked in the old settings set does not exist in the new
        // one, so the selection is dropped rather than carried.
        selected = {};
        WM.send('eve_settings_select', WM.el('es-server').value,
                WM.el('es-profile').value).then(function () {
          refresh();
          WM.send('eve_settings_resolve_names');
        });
      });
    });

    Array.prototype.forEach.call(
      document.querySelectorAll('input[name="es-kind"]'), function (radio) {
        radio.addEventListener('change', function () {
          selected = {};
          renderSource();
          renderTargets();
        });
      });

    WM.el('es-filter').addEventListener('input', renderTargets);
    WM.el('es-source').addEventListener('change', renderTargets);

    WM.el('es-all').addEventListener('click', function () {
      visible.forEach(function (row) { selected[row.path] = true; });
      renderTargets();
    });

    WM.el('es-none').addEventListener('click', function () {
      selected = {};
      renderTargets();
    });

    WM.el('es-copy').addEventListener('click', function () {
      var targets = chosenTargets();
      if (!targets.length) return;
      mutate('eve_settings_copy', WM.el('es-source').value, targets);
    });

    WM.el('es-backup-profile').addEventListener('click', function () {
      // Saves a pointless round trip. It is NOT the guard: _eve_backup_worker
      // rejects an empty or missing path itself, because this file cannot be
      // tested and that decision has to be one that is.
      if (!state || !state.profile) return;
      mutate('eve_settings_backup', state.profile, 'profile');
    });

    document.addEventListener('wm:route', function (event) {
      if (event.detail !== 'evesettings') return;
      refresh();
      // Names are resolved on first open, never at launch: the tray app
      // starts hidden and must not make a network call nobody asked for.
      WM.send('eve_settings_resolve_names');
    });
  }

  WM.handle('onEveSettingsNames', function () { refresh(); });

  // The running-client probe answers after the state that triggered it was
  // already returned, so the pill is repainted in place. Only the pill: a
  // full refresh would rebuild the target checklist under the user's
  // cursor for an advisory badge nothing is blocked on.
  WM.handle('onEveSettingsRunning', function (payload) {
    if (state) state.eve_running = payload.running;
    paintPill(payload.running);
  });

  // The completion signal for every mutation. It replaces a setTimeout that
  // fired 250ms into a copy the worker had barely started, and it is what
  // re-enables the buttons disabled on send.
  WM.handle('onEveSettingsDone', function (payload) {
    if (payload.ok) selected = {};
    setBusy(false);
    refresh();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
}());
