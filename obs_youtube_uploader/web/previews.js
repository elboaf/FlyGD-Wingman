// Preview hotkeys. The row shape deliberately mirrors bookmarks.js: a
// capture button, a Clear, and an Edit... escape hatch. That is not copied
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
  // Bumped every time `state` is replaced wholesale, by a push or by a
  // refresh. send() samples it before its bridge call so a save that
  // resolves late can tell that a newer table has landed meanwhile.
  var pushes = 0;
  // Set when a render is skipped because a capture is armed; flushed by
  // endCapture(). See requestRender() below for why this exists.
  var pendingRender = false;
  // ui/copy.py's INERT_NOTES, off the settings payload. Empty until the
  // first payload lands, which is why render() falls back to the sentence
  // in the markup rather than blanking the element.
  var inertNotes = {};

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
    //
    // Object.create(null), not {}: a character named "constructor" or
    // "__proto__" finds a truthy INHERITED property on an object literal
    // and is dropped from the list along with whatever it is bound to.
    var seen = Object.create(null), out = [];
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
    // Three states, not two. Python sends true for a chord Windows
    // accepted and false for one it refused -- but it sends NEITHER once
    // the host has stopped, because get_preview_hotkey_state gates on
    // is_running and returns an empty map. A plain lookup yields
    // undefined for both "absent" and "refused is false", so testing
    // `=== false` alone made every chord render as registered at the one
    // moment Windows was holding none of them.
    //
    // hasOwnProperty rather than `in`: the map comes off a JSON payload,
    // so an entry literally named "toString" would otherwise be found on
    // Object.prototype and reported as registered.
    var known = state.registration || {};
    if (!Object.prototype.hasOwnProperty.call(known, gesture)) {
      return 'unknown';
    }
    return known[gesture] === false ? 'refused' : null;
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
    // only marks, because nothing is being taken away yet. `unknown` is
    // neither: nothing is wrong, we simply cannot say whether Windows is
    // holding the chord, so it must not borrow the warning colour -- nor
    // .dim, which already means a latent bookmark collision.
    if (clash === 'duplicate' || clash === 'refused'
        || shadow === 'active') { button.classList.add('clash'); }
    else if (clash === 'unknown') { button.classList.add('unknown'); }
    else if (shadow === 'latent') { button.classList.add('dim'); }
    if (clash === 'refused') {
      button.title = 'Another application already owns this keybind.';
    } else if (clash === 'duplicate') {
      button.title = 'This keybind is bound twice here.';
    } else if (clash === 'unknown') {
      button.title = 'Not registered right now — previews are off, or ' +
                     'Windows has not reported on this keybind yet.';
    } else if (shadow === 'active') {
      button.title = 'An EVE bookmark uses this keybind. This binding takes ' +
                     'it while an EVE client is focused.';
    } else if (shadow === 'latent') {
      button.title = 'An EVE bookmark is configured with this keybind. ' +
                     'Enabling bookmarks would make them collide.';
    }
    button.addEventListener('click', function () {
      beginCapture(button, onSet);
    });
    row.appendChild(button);

    var clear = WM.make('button', 'linkbtn', 'Clear');
    clear.addEventListener('click', function () { endCapture(); onSet(''); });
    row.appendChild(clear);

    // `Edit…`, not `Type…` -- round 3's B6; the reasoning is on the
    // matching control in bookmarks.js. The two lists build the same row
    // and their labels have to agree.
    var typed = WM.make('button', 'linkbtn', 'Edit…');
    typed.addEventListener('click', function () {
      endCapture();
      // The app's own dialog -- see the matching comment in bookmarks.js.
      WM.prompt('Keybind for "' + label + '"',
                'Ctrl, Alt, Shift and Win, plus a key. Example: Ctrl+Alt+F1',
                gesture || '').then(function (text) {
        if (text === null) { return; }
        if (text === '') { onSet(''); return; }
        WM.send('parse_preview_bind', text).then(function (result) {
          if (!result) { return; }
          if (result.error) {
            WM.send('alert_bookmarks',
                    'That is not a keybind Windows can register. It needs at '
                    + 'least one of Ctrl, Alt, Shift or Win, plus a key.');
            return;
          }
          onSet(result.gesture);
        });
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
    // Flush whatever render() call was deferred while this capture was
    // armed -- see requestRender(). Runs AFTER capturing is cleared, so
    // render() below sees a clean state and does not try to redraw
    // "Press a key…" onto a row that no longer means it.
    if (pendingRender) { pendingRender = false; render(); }
  }

  // Every push- or fetch-driven redraw goes through this instead of
  // calling render() directly. render() rebuilds every row from scratch,
  // which detaches whatever button is currently armed by beginCapture();
  // the capturing object then points at a node no longer in the page, but
  // capturing stays non-null, so the document keydown handler below keeps
  // intercepting and swallowing every keystroke -- for a capture the user
  // can no longer see. bookmarks.js documents the click-triggered version
  // of this same trap (endCapture() must not re-render mid-arm); this is
  // the push-triggered route into it, which is why it needs its own
  // guard: get_preview_hotkey_state/onPreviewHotkeys fire independently
  // of anything the user clicked, most commonly exactly while someone is
  // capturing a bind -- an EVE client opening or closing is the ordinary
  // thing a multiboxer is doing while setting hotkeys up. Deferring (over
  // ending the capture outright) keeps the user's in-flight keypress
  // valid; the cost is that the row list can be briefly stale until the
  // capture ends, which is preferable to silently cancelling whatever
  // they were in the middle of doing every time a client toggles.
  function requestRender() {
    if (capturing) { pendingRender = true; return; }
    render();
  }

  function render() {
    host.textContent = '';

    var off = WM.el('preview-binds-off');
    if (off) {
      // Settings 1. The sentence is ui/copy.py's INERT_NOTES, delivered on
      // the settings payload as `inert_notes`. The whole table ships and
      // the page picks the entry that applies, because which notes are
      // showing is a render decision made from state this file already
      // holds -- putting that predicate in Python would put it in two
      // places. index.html carries no copy of the words at all, for the
      // same reason.
      //
      // So the slot is empty until the first payload lands, and an empty
      // note stays hidden rather than opening a blank row: inert_note()'s
      // own docstring names "" as the shape the page handles.
      off.textContent = inertNotes.previews_off || '';
      off.style.display = (state.enabled || !off.textContent) ? 'none' : '';
    }

    // `true`, not state.enabled: the cycle chords are not characters and
    // have no online state to report. Dimming them while previews were
    // off was half of what made the whole list grey at once.
    host.appendChild(makeRow('Cycle forward', state.hotkeys.cycle_next,
                             true,
                             function (g) { setBind('cycle_next', g); }));
    host.appendChild(makeRow('Cycle back', state.hotkeys.cycle_prev,
                             true,
                             function (g) { setBind('cycle_prev', g); }));

    var list = rows();
    list.forEach(function (entry) {
      host.appendChild(makeRow(
        entry.name, (state.hotkeys.characters || {})[entry.name],
        // null, not false, while previews are off. makeRow dims only on
        // a strict false, and dimming means "this character is logged
        // off" -- a claim we cannot make with the host stopped, because
        // Python then sends characters: [] and every row would look
        // offline whoever is actually online. A uniformly dim list is
        // indistinguishable from one where everyone really has logged
        // out; the banner above says "off" instead.
        state.enabled ? entry.online : null,
        function (g) { setCharacterBind(entry.name, g); }));
    });

    var empty = WM.el('preview-binds-empty');
    if (empty) { empty.style.display = list.length ? 'none' : ''; }
  }

  function send(next) {
    // Held across the bridge call. onPreviewHotkeys replaces `state`
    // wholesale and fires whenever an EVE client opens or closes --
    // routinely while someone is setting a bind. Without this, a save
    // resolving after such a push wrote its own older table back over
    // the newer one, and the page then disagreed with Python until the
    // next refresh.
    var generation = pushes;
    WM.send('set_preview_binds', next).then(function (ok) {
      if (!ok) {
        // WM.send resolves to null on a bridge error, and Python returns
        // false on a rejected chord. Either way the page must not keep
        // showing a binding the backend never accepted.
        refresh();
        // ...and must not put it back in silence: repainting from the
        // backend with nothing said looks exactly like the click never
        // registering, which is how the same chord gets tried twice.
        WM.send('alert_bookmarks',
                'That binding was not saved. Another keybind may already ' +
                'use it, or the settings file could not be written.');
        return;
      }
      if (generation !== pushes) {
        // A push overtook this save. It carries the newer table, so
        // dropping this write is what keeps the page and Python in step.
        return;
      }
      state.hotkeys = next;
      requestRender();
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
      pushes += 1;
      state.hotkeys = state.hotkeys || {characters: {}, cycle_next: '',
                                        cycle_prev: ''};
      requestRender();
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
                  ? 'A preview keybind needs at least one of Ctrl, Alt, ' +
                    'Shift or Win, or it would fire in every application.'
                  : 'That key cannot be used as a keybind.');
        return;
      }
      var apply = session.onSet;
      endCapture();
      apply(result.gesture);
    });
  }, true);

  // Python volunteers this when registration or the client set changes.
  //
  // Through WM.handle, not a direct window assignment: app.js installs a
  // stub for every name in WM.HANDLERS so a push arriving before this
  // module loads is logged instead of silently vanishing, and assigning
  // straight to window skipped that. tests/test_bridge_contract.py holds
  // the two lists together.
  WM.handle('onPreviewHotkeys', function (payload) {
    if (!payload) { return; }
    state = payload;
    pushes += 1;
    state.hotkeys = state.hotkeys || {characters: {}, cycle_next: '',
                                      cycle_prev: ''};
    requestRender();
  });

  // The inert-note table, which is settings-payload state rather than
  // hotkey state. panel.js owns the onSettings handler and re-dispatches
  // it, so this listens on the same custom event settings.js uses rather
  // than claiming a handler that already has an owner. A re-render is
  // requested (not called) so it cannot detach an armed capture button.
  document.addEventListener('wm:settings', function (event) {
    inertNotes = (event.detail || {}).inert_notes || {};
    requestRender();
  });

  // Refreshed on route entry rather than polled, same reasoning as
  // bookmarks.js: the live/known character set changes when EVE clients
  // open and close, which is not something worth a timer. `wm:settings`
  // (dispatched only when the global settings payload changes) would not
  // fire on a plain tab switch and was the wrong event to listen for here.
  // wm:section, not wm:route -- see the matching comment in bookmarks.js.
  document.addEventListener('wm:section', function (event) {
    if (event.detail === 'previews') {
      refresh();
      return;
    }
    // Leaving must disarm an in-progress capture. bookmarks.js installs
    // its own document-level keydown listener too; stopPropagation() only
    // stops OTHER listeners further along the same dispatch, not a sibling
    // listener already attached to the same document node, so an armed
    // capture left running here would still consume the next keystroke
    // typed anywhere else -- writing a keybind meant for a bookmark bind
    // into this one instead, off-screen and silently persisted.
    //
    // Now that the neighbours are Folders and Discord rather than another
    // route, an escaped capture would swallow a path or a webhook mid-type:
    // its handler preventDefault()s every key, Tab included.
    endCapture();
  });

  refresh();
}());
