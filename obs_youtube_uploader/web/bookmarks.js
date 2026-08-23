/* FlyGD Wingman — the Bookmarks route.
 *
 * Deliberately dumb. Every decision about a key -- what it means, whether
 * it is legal, whether it collides -- happens in Python, because this repo
 * has no way to test JavaScript (webview-replatform-design.md:545). This
 * file captures events, sends them, and renders the answer.
 */
(function () {
  'use strict';

  var state = null;
  var capturing = null;

  function send(section) {
    WM.send('save_bookmarks', section).then(render);
  }

  function render(payload) {
    if (!payload) return;
    state = payload;
    WM.el('eve-enabled').checked = !!payload.settings.enabled;
    renderEngineState();
    renderWindows();
    renderBinds();
  }

  // Immediate feedback after a save. The live status push (a later task)
  // updates this same element on every poll tick, but that only starts once
  // the recording watcher is running -- so without this, ticking Enable and
  // having the engine fail to start would look like it worked until the
  // next tick, or forever if the watcher has not started.
  function renderEngineState() {
    var el = WM.el('eve-engine-state');
    if (!el || !state.engine) return;
    var label = { off: 'Not running', stopped: 'Stopped',
                  stale: 'Not responding',
                  running: 'Running' }[state.engine.state] || '';
    // The reason matters more than the state: "Stopped" alone leaves the
    // user with no idea the engine is missing rather than merely idle.
    el.textContent = state.engine.last_error
      ? label + ' — ' + state.engine.last_error
      : label;
  }

  function renderWindows() {
    var host = WM.el('eve-windows');
    host.textContent = '';
    var live = state.windows || [];
    var known = state.settings.windows || {};
    // Titles that are enabled but not currently running still matter: the
    // client may simply not be open yet, and dropping them would silently
    // disable a character's hotkeys.
    var titles = live.slice();
    Object.keys(known).forEach(function (t) {
      if (titles.indexOf(t) === -1) titles.push(t);
    });
    if (!titles.length) {
      host.appendChild(WM.make('p', 'hint', 'No EVE windows found.'));
      return;
    }
    titles.sort().forEach(function (title) {
      var row = WM.make('div', 'row');
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = !!known[title];
      box.addEventListener('change', function () {
        var next = JSON.parse(JSON.stringify(state.settings));
        next.windows[title] = box.checked;
        send(next);
      });
      var label = WM.make('label', null, ' ' + title);
      label.prepend(box);
      if (live.indexOf(title) === -1) {
        label.appendChild(WM.make('span', 'hint', ' (not running)'));
      }
      row.appendChild(label);
      host.appendChild(row);
    });
  }

  function renderBinds() {
    var host = WM.el('eve-binds');
    host.textContent = '';
    var collisions = state.collisions || {};
    var clashing = {};
    Object.keys(collisions).forEach(function (combo) {
      collisions[combo].forEach(function (id) { clashing[id] = combo; });
    });

    var warn = WM.el('eve-bind-warning');
    var names = Object.keys(collisions);
    warn.hidden = names.length === 0;
    if (names.length) {
      warn.textContent = 'Two actions share the same key: ' +
        names.join(', ') + '. Only one of them will work.';
    }

    state.order.forEach(function (id) {
      var row = WM.make('div', 'row');
      row.appendChild(WM.make('span', 'lab', state.labels[id]));

      var button = WM.make('button', 'bindbtn',
                           state.displays[id] || 'Not set');
      if (clashing[id]) button.classList.add('clash');
      button.addEventListener('click', function () { beginCapture(id, button); });
      row.appendChild(button);

      var clear = WM.make('button', 'linkbtn', 'Clear');
      clear.addEventListener('click', function () { setBind(id, ''); });
      row.appendChild(clear);

      // Manual entry: the escape hatch for non-US layouts, where the
      // event.code table maps a physical key to the wrong character. The
      // typed string is validated by the same Python rules as capture, so
      // the two cannot disagree.
      var typed = WM.make('button', 'linkbtn', 'Type…');
      typed.addEventListener('click', function () {
        var text = window.prompt(
          'AutoHotkey hotkey for "' + state.labels[id] + '"\n' +
          '^ = Ctrl, ! = Alt, + = Shift, # = Win. Example: ^+s',
          state.settings.keybinds[id] || '');
        if (text === null) return;
        WM.send('parse_bind', text).then(function (result) {
          if (!result) return;
          if (result.error) {
            WM.send('alert_import',
                    'That is not a hotkey AutoHotkey can register.');
            return;
          }
          setBind(id, result.ahk);
        });
      });
      row.appendChild(typed);

      host.appendChild(row);
    });
  }

  function beginCapture(id, button) {
    if (capturing) {
      // Revert the previous row's button WITHOUT the full renderBinds()
      // that endCapture() would normally trigger: that rebuilds every row's
      // button from scratch, including the one just clicked to start THIS
      // capture -- calling it here would detach `button` before it is
      // armed below. Reuses the same display expression renderBinds()
      // uses for a bound key, so the reverted label matches exactly what
      // a full re-render would have shown.
      capturing.button.classList.remove('capturing');
      capturing.button.textContent = state.displays[capturing.id] || 'Not set';
    }
    capturing = { id: id, button: button };
    button.textContent = 'Press a key…';
    button.classList.add('capturing');
  }

  function endCapture() {
    if (!capturing) return;
    capturing.button.classList.remove('capturing');
    capturing = null;
    renderBinds();
  }

  function setBind(id, ahk) {
    var next = JSON.parse(JSON.stringify(state.settings));
    next.keybinds[id] = ahk;
    send(next);
  }

  document.addEventListener('keydown', function (event) {
    if (!capturing) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.key === 'Escape') { endCapture(); return; }
    // Held synchronously: by the time the bridge resolves the user may have
    // pressed Escape (capturing is null) or clicked a different row
    // (capturing points elsewhere). Reading it in the callback would either
    // throw or bind this key to the wrong action.
    var session = capturing;
    WM.send('capture_bind', {
      ctrl: event.ctrlKey, alt: event.altKey,
      shift: event.shiftKey, meta: event.metaKey, code: event.code
    }).then(function (result) {
      // A modifier-only press is not an error the user needs told about --
      // they are still reaching for the combination. A null result (bridge
      // failure) falls into the same branch: the capture is left armed
      // rather than silently disarmed, so the user can simply press
      // another key or hit Escape.
      if (!result || result.error === 'modifier-only') return;
      // A result for a capture the user has since abandoned or replaced is
      // not theirs to apply.
      if (capturing !== session) return;
      endCapture();
      if (result.error) return;
      setBind(session.id, result.ahk);
    });
  }, true);

  WM.el('eve-enabled').addEventListener('change', function () {
    var next = JSON.parse(JSON.stringify(state.settings));
    next.enabled = WM.el('eve-enabled').checked;
    send(next);
  });

  WM.el('eve-set-root').addEventListener('click', function () {
    var value = WM.el('eve-root-input').value.trim();
    if (!value) return;
    WM.send('eve_command', 'set_root', value);
  });

  WM.el('eve-clear-root').addEventListener('click', function () {
    WM.send('eve_command', 'clear_root');
  });

  WM.el('eve-import').addEventListener('click', function () {
    WM.send('import_bookmarks').then(function (result) {
      if (!result || !result.ok) return;
      var lines = [];
      if (result.discarded.length) {
        lines.push('These no longer exist and were not imported: ' +
                   result.discarded.join(', ') + '.');
      }
      result.notes.forEach(function (note) { lines.push(note); });
      if (lines.length) WM.send('alert_import', lines.join('\n\n'));
      WM.send('get_bookmarks').then(render);
    });
  });

  WM.handle('onBookmarks', render);

  document.addEventListener('wm:route', function (event) {
    // Refreshed on entry rather than polled: the EVE window list changes
    // when clients open and close, which is not something worth a timer.
    if (event.detail === 'bookmarks') {
      WM.send('get_bookmarks').then(render);
    }
  });
}());
