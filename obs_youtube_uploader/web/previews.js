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
               bookmark_chords: {active: [], latent: []}, enabled: false,
               locked: [], never_minimize: []};
  var capturing = null;
  // preview.minimize_inactive_clients, off the settings payload rather
  // than the hotkey-state one: it lives in Settings' own Previews card
  // (settings.js), not here, and this file only needs to know its CURRENT
  // value to decide whether a row's Never-minimize box is usable. Reusing
  // the wm:settings listener below (already read for inert_notes) avoids
  // a second round trip for one boolean.
  var minimizeInactive = false;
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

  function makeRow(label, gesture, online, onSet, character) {
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
    // Round 3, B2. The site the walkthrough actually measured: `Clear`
    // was live beside a bind reading `Not set`. Same reasoning as the
    // matching control in bookmarks.js -- the two lists build the same
    // row and cannot disagree about when a control is live.
    WM.setEnabled(clear, !!gesture);
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

    // Cycle forward/back have no `character` -- they are chords, not
    // characters, and neither Lock nor Never-minimize means anything for
    // them. #preview-binds is a CSS grid with `.row { display: contents }`
    // (style.css), so every row must contribute the same number of cells
    // or a short row's children bleed into the next row's columns. Two
    // empty fillers keep the grid aligned instead of shrinking the column
    // count for those two rows only.
    //
    // Round 5, C3 and decision D6: the Never-minimize cell exists only
    // while the global "Minimize a client's window..." toggle is ON. It
    // used to be built for every character and then DISABLED whenever the
    // global was off -- which is the default -- so the ordinary state of
    // this screen was ~13 permanently dead controls, one per character,
    // each carrying a tooltip explaining why it could not be used. D6
    // keeps the setting per-character and stops it rendering at all in
    // the state where it can do nothing.
    //
    // The cell count stays uniform ACROSS rows within one render, which is
    // the invariant #preview-binds' grid actually needs; it is the track
    // COUNT that varies, and render() tells the stylesheet which it is.
    if (character) {
      row.appendChild(makeLockCheck(character));
      if (minimizeInactive) { row.appendChild(makeNeverMinimizeCheck(character)); }
    } else {
      row.appendChild(document.createElement('span'));
      if (minimizeInactive) { row.appendChild(document.createElement('span')); }
    }
    return row;
  }

  function isLocked(name) { return (state.locked || []).indexOf(name) !== -1; }
  function isNeverMinimize(name) {
    return (state.never_minimize || []).indexOf(name) !== -1;
  }

  // Both checkboxes follow the same shape: read the live membership list
  // for their initial state, write back through the matching endpoint on
  // `change` (DESIGN.md: discrete controls commit on change, never blur),
  // and on a refusal put the box back rather than show a state the app
  // never actually took -- same posture as settings.js's per-field
  // checkboxes, just without a status line (there is no room for one per
  // row, forty of them). `state` is patched in place on success instead of
  // waiting for the next full payload, matching setCharacterBind's own
  // shortcut for the common case; a push that lands in between (an EVE
  // client opening or closing) still wins because it replaces `state`
  // wholesale and this file always re-renders from it.
  function makeLockCheck(name) {
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = isLocked(name);
    box.addEventListener('change', function () {
      var wanted = box.checked;
      WM.send('set_preview_locked', name, wanted).then(function (res) {
        if (!res || !res.applied) { box.checked = !wanted; return; }
        state.locked = wanted
          ? (state.locked || []).concat(name)
          : (state.locked || []).filter(function (n) { return n !== name; });
      });
    });
    var label = WM.make('label', 'check', ' Lock');
    label.prepend(WM.make('span', 'box'));
    label.prepend(box);
    return label;
  }

  // Only ever called with the global minimize toggle ON -- see makeRow.
  // Until round 5 it was called unconditionally and disabled itself when
  // the global was off, which is what D6 removed; the `.check.nm.disabled`
  // rule that dimmed it went with it, and style.css records that where the
  // rule used to be.
  function makeNeverMinimizeCheck(name) {
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = isNeverMinimize(name);
    // `.nm` is kept as the control's name in the DOM even with no rule
    // hanging off it: it is how the smoke pass and the layout probes tell
    // this checkbox from Lock, which are otherwise two identical .check
    // labels in the same row.
    var label = WM.make('label', 'check nm', ' Never minimize');
    label.prepend(WM.make('span', 'box'));
    label.prepend(box);
    box.addEventListener('change', function () {
      var wanted = box.checked;
      WM.send('set_never_minimize', name, wanted).then(function (res) {
        if (!res || !res.applied) { box.checked = !wanted; return; }
        state.never_minimize = wanted
          ? (state.never_minimize || []).concat(name)
          : (state.never_minimize || [])
              .filter(function (n) { return n !== name; });
      });
    });
    return label;
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
    // D6: which grid template #preview-binds takes. makeRow appends four
    // cells per row instead of five while this is off, and a grid whose
    // template still declared five would leave a max-content track holding
    // nothing plus its 10px column-gap after the last live control.
    host.classList.toggle('no-nm', !minimizeInactive);

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
      off.hidden = !!(state.enabled || !off.textContent);
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
    // A subhead, because the two rows above are not the same KIND of thing
    // as the ones below: cycle_next/cycle_prev are app commands with no
    // character attached, and everything after this is one row per known
    // character. They were one flat list, so "Cycle forward" read as a
    // twelfth character on an install with eleven.
    //
    // Rendered only when there are characters to head. With none, the
    // #preview-binds-empty hint below is the whole story and a heading over
    // nothing is worse than no heading.
    if (list.length) {
      var head = WM.make('div', 'bind-group');
      head.appendChild(WM.make('span', 'bind-group-name', 'Characters'));
      // The legend earns its place only while a row is actually dimmed.
      // makeRow dims on a strict false, and `state.enabled ? ... : null`
      // below means nothing is dim while previews are off -- so this asks
      // the same question the rows do rather than a second, looser one.
      var anyOffline = state.enabled && list.some(function (e) {
        return e.online === false;
      });
      if (anyOffline) {
        head.appendChild(WM.make('span', 'bind-group-note',
                                 'dimmed = not logged in'));
      }
      host.appendChild(head);
    }
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
        function (g) { setCharacterBind(entry.name, g); },
        entry.name));
    });

    var empty = WM.el('preview-binds-empty');
    if (empty) { empty.hidden = list.length > 0; }
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
      state.locked = state.locked || [];
      state.never_minimize = state.never_minimize || [];
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
    state.locked = state.locked || [];
    state.never_minimize = state.never_minimize || [];
    requestRender();
  });

  // The inert-note table, and now preview.minimize_inactive_clients, both
  // settings-payload state rather than hotkey state. panel.js owns the
  // onSettings handler and re-dispatches it, so this listens on the same
  // custom event settings.js uses rather than claiming a handler that
  // already has an owner. A re-render is requested (not called) so it
  // cannot detach an armed capture button.
  document.addEventListener('wm:settings', function (event) {
    var detail = event.detail || {};
    inertNotes = detail.inert_notes || {};
    var s = detail.settings || {};
    // Absent means off, matching build_preview_host's own default: turning
    // on Never-minimize before this exists must not look possible.
    minimizeInactive = !!(s.preview && s.preview.minimize_inactive_clients);
    requestRender();
  });

  // wm:settings alone is not enough to keep this live: list.js's own
  // comment on refreshRecordingDir documents why get_settings is never
  // followed by a re-dispatch of wm:settings after a single-field write --
  // repainting the whole form would clobber whatever the user is mid-way
  // through typing elsewhere on the page. That means toggling "Minimize
  // inactive" in settings.js would otherwise leave every open row's
  // Never-minimize checkbox showing the state from page load until the
  // next full reload. This event is the narrow exception: one boolean,
  // dispatched only by settings.js's own successful write, touching
  // nothing a user could be typing into.
  document.addEventListener('wm:preview-minimize-inactive', function (event) {
    minimizeInactive = !!(event.detail && event.detail.enabled);
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
