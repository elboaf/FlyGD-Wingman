// Preview hotkeys. The row shape deliberately mirrors bookmarks.js: a
// capture button, a Clear, and a Type... escape hatch. That is not copied
// for consistency -- capture reads event.code, which maps a physical key to
// the wrong character on non-US layouts, and manual entry is the way out.
// Both paths are validated by the same Python rules so they cannot disagree.
(function () {
  var host = WM.el('preview-binds');
  if (!host) { return; }

  var state = {hotkeys: {characters: {}, cycle_next: '', cycle_prev: ''},
               characters: [], roster: [], registration: {},
               bookmark_chords: {active: [], latent: []}, enabled: false};
  var capturing = null;

  function bookmarkClash(gesture) {
    // Active: the bookmark bind is registered right now, so this chord
    // takes it away while EVE is focused. Latent: bookmarks are off or no
    // window is enabled, so nothing is stolen yet -- but turning them on
    // would, with nothing on screen to explain it.
    var chords = state.bookmark_chords || {};
    if ((chords.active || []).indexOf(gesture) !== -1) { return 'active'; }
    if ((chords.latent || []).indexOf(gesture) !== -1) { return 'latent'; }
    return null;
  }

  function rows() {
    // Running first, then known-but-offline, then any binding whose
    // character is in neither -- a chord with no row would be invisible.
    var seen = {}, out = [];
    state.characters.forEach(function (n) {
      if (!seen[n]) { seen[n] = 1; out.push({name: n, online: true}); }
    });
    state.roster.forEach(function (n) {
      if (!seen[n]) { seen[n] = 1; out.push({name: n, online: false}); }
    });
    Object.keys(state.hotkeys.characters || {}).forEach(function (n) {
      if (!seen[n]) { seen[n] = 1; out.push({name: n, online: false}); }
    });
    return out;
  }

  function clashes(gesture) {
    if (!gesture) { return null; }
    var count = 0;
    var binds = state.hotkeys.characters || {};
    Object.keys(binds).forEach(function (n) {
      if (binds[n] === gesture) { count += 1; }
    });
    if (state.hotkeys.cycle_next === gesture) { count += 1; }
    if (state.hotkeys.cycle_prev === gesture) { count += 1; }
    if (count > 1) { return 'duplicate'; }
    if (state.registration[gesture] === false) { return 'refused'; }
    return null;
  }

  function makeRow(label, gesture, online, onSet) {
    var row = WM.make('div', 'row');
    var lab = WM.make('span', 'lab', label);
    // Offline is information, not an error: the binding is still saved and
    // still works the moment that character logs in.
    if (online === false) { lab.classList.add('dim'); }
    row.appendChild(lab);

    var button = WM.make('button', 'bindbtn', gesture || 'Not set');
    var clash = clashes(gesture);
    var shadow = bookmarkClash(gesture);
    // An active bookmark collision warns like any other clash; a latent one
    // only marks, because nothing is being taken away yet.
    if (clash || shadow === 'active') { button.classList.add('clash'); }
    else if (shadow === 'latent') { button.classList.add('dim'); }
    if (clash === 'refused') {
      button.title = 'Another application already owns this chord.';
    } else if (clash === 'duplicate') {
      button.title = 'This chord is bound twice here.';
    } else if (shadow === 'active') {
      button.title = 'An EVE bookmark uses this chord. This binding takes ' +
                     'it while an EVE client is focused.';
    } else if (shadow === 'latent') {
      button.title = 'An EVE bookmark is configured with this chord. ' +
                     'Enabling bookmarks would make them collide.';
    }
    button.addEventListener('click', function () {
      beginCapture(button, onSet);
    });
    row.appendChild(button);

    var clear = WM.make('button', 'linkbtn', 'Clear');
    clear.addEventListener('click', function () { endCapture(); onSet(''); });
    row.appendChild(clear);

    var typed = WM.make('button', 'linkbtn', 'Type…');
    typed.addEventListener('click', function () {
      endCapture();
      var text = window.prompt(
        'Hotkey for "' + label + '"\n' +
        'Ctrl, Alt, Shift and Win, plus a key. Example: Ctrl+Alt+F1',
        gesture || '');
      if (text === null) { return; }
      if (text === '') { onSet(''); return; }
      WM.send('parse_preview_bind', text).then(function (result) {
        if (!result) { return; }
        if (result.error) {
          WM.send('alert_bookmarks',
                  'That is not a hotkey Windows can register. It needs at ' +
                  'least one of Ctrl, Alt, Shift or Win, plus a key.');
          return;
        }
        onSet(result.gesture);
      });
    });
    row.appendChild(typed);
    return row;
  }

  function beginCapture(button, onSet) {
    if (capturing) {
      // Revert the previous button WITHOUT a full re-render: that would
      // detach the button just clicked before it is armed below. Same trap
      // bookmarks.js documents.
      capturing.button.classList.remove('capturing');
      capturing.button.textContent = capturing.previous || 'Not set';
    }
    capturing = {button: button, onSet: onSet,
                 previous: button.textContent};
    button.textContent = 'Press a key…';
    button.classList.add('capturing');
  }

  function endCapture() {
    if (!capturing) { return; }
    capturing.button.classList.remove('capturing');
    capturing.button.textContent = capturing.previous || 'Not set';
    capturing = null;
  }

  function render() {
    host.textContent = '';
    host.appendChild(makeRow('Cycle forward', state.hotkeys.cycle_next, true,
                             function (g) { setBind('cycle_next', g); }));
    host.appendChild(makeRow('Cycle back', state.hotkeys.cycle_prev, true,
                             function (g) { setBind('cycle_prev', g); }));

    var list = rows();
    list.forEach(function (entry) {
      host.appendChild(makeRow(
        entry.name, (state.hotkeys.characters || {})[entry.name],
        entry.online,
        function (g) { setCharacterBind(entry.name, g); }));
    });

    var empty = WM.el('preview-binds-empty');
    if (empty) { empty.style.display = list.length ? 'none' : ''; }
  }

  function send(next) {
    WM.send('set_preview_binds', next).then(function (ok) {
      if (!ok) {
        // WM.send resolves to null on a bridge error, and Python returns
        // false on a rejected chord. Either way the page must not keep
        // showing a binding the backend never accepted.
        refresh();
        return;
      }
      state.hotkeys = next;
      render();
    });
  }

  function setBind(key, gesture) {
    endCapture();
    var next = JSON.parse(JSON.stringify(state.hotkeys));
    next[key] = gesture;
    send(next);
  }

  function setCharacterBind(name, gesture) {
    endCapture();
    var next = JSON.parse(JSON.stringify(state.hotkeys));
    next.characters = next.characters || {};
    if (gesture) { next.characters[name] = gesture; }
    else { delete next.characters[name]; }
    send(next);
  }

  function refresh() {
    WM.send('get_preview_hotkey_state').then(function (payload) {
      if (!payload) { return; }
      state = payload;
      state.hotkeys = state.hotkeys || {characters: {}, cycle_next: '',
                                        cycle_prev: ''};
      render();
    });
  }

  document.addEventListener('keydown', function (event) {
    if (!capturing) { return; }
    event.preventDefault();
    event.stopPropagation();
    if (event.key === 'Escape') { endCapture(); return; }
    // Held synchronously: by the time the bridge resolves the user may have
    // pressed Escape or clicked another row.
    var session = capturing;
    WM.send('capture_preview_bind', {
      ctrl: event.ctrlKey, alt: event.altKey,
      shift: event.shiftKey, meta: event.metaKey, code: event.code
    }).then(function (result) {
      if (!result || result.error === 'modifier-only') { return; }
      if (capturing !== session) { return; }
      if (result.error) {
        endCapture();
        WM.send('alert_bookmarks',
                result.error === 'no-modifier'
                  ? 'A preview hotkey needs at least one of Ctrl, Alt, ' +
                    'Shift or Win, or it would fire in every application.'
                  : 'That key cannot be used as a hotkey.');
        return;
      }
      var apply = session.onSet;
      endCapture();
      apply(result.gesture);
    });
  }, true);

  // Python volunteers this when registration or the client set changes.
  window.onPreviewHotkeys = function (payload) {
    if (!payload) { return; }
    state = payload;
    state.hotkeys = state.hotkeys || {characters: {}, cycle_next: '',
                                      cycle_prev: ''};
    render();
  };

  // Refreshed on route entry rather than polled, same reasoning as
  // bookmarks.js: the live/known character set changes when EVE clients
  // open and close, which is not something worth a timer. `wm:settings`
  // (dispatched only when the global settings payload changes) would not
  // fire on a plain tab switch and was the wrong event to listen for here.
  document.addEventListener('wm:route', function (event) {
    if (event.detail === 'previews') { refresh(); }
  });

  refresh();
}());
