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
    WM.el('es-eve-state').textContent =
      payload.eve_running ? 'EVE running' : 'EVE closed';

    var warning = WM.el('es-warning');
    // "Couldn't read" and "nothing there" are different answers, and only
    // one of them means the folder is wrong.
    warning.hidden = !payload.unreadable;
    warning.textContent = payload.unreadable
      ? "Couldn't read that folder. Check it still exists and is readable."
      : '';

    fill('es-server', payload.servers, payload.server);
    fill('es-profile', payload.profiles, payload.profile);
    renderSource();
    renderTargets();
    renderBackups();
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
    rows().forEach(function (row) {
      if (row.path === source) return;
      if (needle && row.name.toLowerCase().indexOf(needle) === -1) return;
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
    (state.backups || []).forEach(function (item) {
      var line = document.createElement('div');
      line.className = 'row';
      line.appendChild(document.createTextNode(
        item.created + ' · ' + item.kind + ' · ' + item.stem
        + (item.origin === 'auto' ? ' (auto)' : '')));
      line.appendChild(button('Restore', function () {
        WM.send('eve_settings_restore', item.path).then(refresh);
      }));
      line.appendChild(button('Delete', function () {
        WM.send('eve_settings_delete_backup', item.path).then(refresh);
      }));
      host.appendChild(line);
    });
  }

  function button(text, handler) {
    var el = document.createElement('button');
    el.textContent = text;
    el.addEventListener('click', handler);
    return el;
  }

  function chosenTargets() {
    return Object.keys(selected).filter(function (path) {
      return selected[path];
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
      rows().forEach(function (row) { selected[row.path] = true; });
      renderTargets();
    });

    WM.el('es-none').addEventListener('click', function () {
      selected = {};
      renderTargets();
    });

    WM.el('es-copy').addEventListener('click', function () {
      var targets = chosenTargets();
      if (!targets.length) return;
      WM.send('eve_settings_copy', WM.el('es-source').value, targets)
        .then(function () { window.setTimeout(refresh, 250); });
    });

    WM.el('es-backup-profile').addEventListener('click', function () {
      WM.send('eve_settings_backup', state.profile, 'profile')
        .then(function () { window.setTimeout(refresh, 250); });
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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
}());
