/* FlyGD Wingman — the Bookmarks route.
 *
 * Deliberately dumb. Every decision about a key -- what it means, whether
 * it is legal, whether it collides -- happens in Python, because this repo
 * has no way to test JavaScript
 * (docs/history/webview-replatform-design.md:545). This file captures
 * events, sends them, and renders the answer.
 */
(function () {
  'use strict';

  var state = null;
  var capturing = null;

  function send(section) {
    WM.send('save_bookmarks', section).then(function (payload) {
      if (!payload) {
        // The save did not happen (bridge failure). A checkbox has
        // already flipped itself before its change handler ran, and
        // save_bookmarks never persisted anything -- re-render from the
        // last known-good state so the control shows what is actually
        // stored, instead of leaving it displaying something that was
        // never saved. `state` itself was never mutated: every caller
        // builds `section` from a deep clone of `state.settings`.
        render(state);
        return;
      }
      render(payload);
    });
  }

  function render(payload) {
    if (!payload) return;
    state = payload;
    WM.el('eve-enabled').checked = !!payload.settings.enabled;
    renderEngineState();
    renderBlockers();
    renderWindows();
    renderBinds();
  }

  // Enabled, running, and registering nothing. The two config states that
  // cause it are decided in Python (bookmarks.registration_blockers) and
  // only phrased here: RegisterBind ignores a blank key without recording a
  // failure, and the per-window loop never runs with no window ticked, so
  // failed_binds stays empty and the engine looks healthy while every
  // keypress does nothing.
  function renderBlockers() {
    var row = WM.el('eve-blockers-row');
    var el = WM.el('eve-blockers');
    if (!row || !el) return;
    var reasons = (state && state.engine && state.engine.blockers) || [];
    var text = {
      no_windows: 'no EVE window is enabled below',
      no_binds: 'no keybinds are set'
    };
    var parts = reasons.map(function (r) { return text[r]; })
                       .filter(Boolean);
    row.hidden = parts.length === 0;
    // Named in full rather than "check your settings": the whole point is
    // that the user cannot see which of the two is missing.
    el.textContent = parts.length
      ? 'No keybinds are registered — ' + parts.join(', and ') + '.'
      : '';
  }

  // Immediate feedback after a save. The live status push (a later task)
  // updates this same element on every poll tick, but that only starts once
  // the recording watcher is running -- so without this, ticking Enable and
  // having the engine fail to start would look like it worked until the
  // next tick, or forever if the watcher has not started.
  function renderEngineState() {
    var el = WM.el('eve-engine-state');
    if (!el) return;
    var engine = state && state.engine;
    if (!engine) {
      // No engine block at all -- a payload from before the key existed,
      // or a bridge that answered with less than it usually does. Treated
      // as off rather than left showing whatever the row said last: the
      // line is only ever news when it contradicts the switch, and it
      // cannot contradict anything we have not been told.
      showEngineRow('off', '');
      return;
    }
    var label = { off: 'Not running', stopped: 'Stopped',
                  stale: 'Not responding',
                  running: 'Running' }[engine.state] || '';
    // The reason matters more than the state: "Stopped" alone leaves the
    // user with no idea the engine is missing rather than merely idle.
    writeEngineState(el, engine.state, engine.last_error, label);
    showEngineRow(engine.state, engine.last_error);
  }

  // Both engine-state write sites go through this. They already drifted
  // once over last_error (see the poll handler below), and the class is
  // the same kind of thing: set in one place and forgotten in the other,
  // it would leave the route's render red and the next poll tick plain.
  //
  // `stale` and `stopped` are failures; `off` is the user's own choice and
  // is not. A last_error reddens whatever the state, for the same reason
  // showEngineRow keeps the row for one: it is the record of what broke.
  function writeEngineState(el, state, lastError, label) {
    if (!el) return;
    el.textContent = lastError ? label + ' \u2014 ' + lastError : label;
    var bad = !!lastError || state === 'stopped' || state === 'stale';
    el.classList.toggle('err', bad);
  }

  // Walkthrough Settings 8. "Not running" directly under an UNTICKED
  // `Register keybinds in EVE` is the same fact twice, the second time
  // unlabelled and dim -- the engine is not running because the user
  // switched it off, which the checkbox above already says. So the line is
  // withheld in exactly that state and shown in every other, where it is
  // genuinely news: "Not running" while the switch is ON means something
  // failed.
  //
  // A last_error keeps the row whatever the state. An error carried on an
  // `off` engine is the record of why it stopped, and hiding it would lose
  // the one actionable thing the user was told.
  //
  // The ROW is hidden, not the span: .lab:empty collapses the label but
  // the row keeps its 10px margin-bottom, so hiding only the text leaves a
  // gap under the checkbox with nothing in it.
  function showEngineRow(engineState, lastError) {
    var row = WM.el('eve-engine-row');
    if (!row) return;
    row.hidden = engineState === 'off' && !lastError;
  }

  // Every EVE client titles its window "EVE - <character>", so a list of
  // them begins every line with the word every line shares and puts the
  // character -- the only part that tells one row from another -- past the
  // eye's landing point (walkthrough Settings 7, the same instinct as
  // Uploader 11's `Fight ` prefix). The card is headed EVE WINDOWS inside
  // a section reached from an EVE-only rail item, so the prefix is carried
  // three times before the row repeats it.
  //
  // DISPLAY ONLY. `title` stays the identity: it is the key in
  // settings.windows, it is what the engine matches on, and a stripped
  // copy written back would silently unbind every window. Anything not
  // matching the pattern is shown whole rather than guessed at.
  var EVE_TITLE = /^EVE\s*-\s*(.+)$/;

  function windowLabel(title) {
    var m = EVE_TITLE.exec(title);
    return m ? m[1] : title;
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
      // Same .check/.box pattern the rest of the app uses: the real input
      // is opacity:0 and the span is the visible control. Without it these
      // rendered as native white checkboxes against the dark card.
      var label = WM.make('label', 'check', ' ' + windowLabel(title));
      // The real window title, for the one case the stripped name is not
      // enough to identify the row -- two clients whose titles differ only
      // in the part the prefix rule removed.
      label.title = title;
      label.prepend(WM.make('span', 'box'));
      label.prepend(box);
      // Round 5, C9, which walks back HALF of round 3's R4 finding 5 and
      // keeps the half that mattered. R4 was right that annotating only
      // the negative left "running" to be inferred from silence, on a
      // screen the maintainer sets once and never revisits -- so it
      // annotated both, and thirteen clients then printed "(running)"
      // thirteen times to say the unremarkable thing.
      //
      // What silence means is now DEFINED, once, by the card's own hint
      // ("All of these are running unless marked otherwise") instead of
      // being re-asserted per row. Nothing is inferred: the rule is
      // stated, and only the exception is marked. Same shape as the
      // Previews roster's "dimmed = not logged in" legend, in words rather
      // than a dim treatment because these labels are checkboxes and
      // dimming an enabled .check reads as a disabled one (see
      // makeNeverMinimizeCheck in previews.js for where that treatment IS
      // used, and what it means there).
      if (live.indexOf(title) === -1) {
        label.appendChild(WM.make('span', 'hint', ' (not running)'));
      }
      row.appendChild(label);
      host.appendChild(row);
    });
  }

  // Round 5, C6. previews.js's bookmarkClash() told this story from the
  // winning end only: a preview chord is a global RegisterHotKey and a
  // bookmark chord is an AHK hotkey scoped with #HotIf WinActive, so where
  // they collide the preview wins while EVE is focused and the bookmark
  // simply does not fire. Previews marked it; here -- on the binds that are
  // the ones actually overridden -- an overridden bind looked exactly like
  // a working one.
  //
  // Same vocabulary as previews.js on purpose, because it is the same fact:
  // `active` warns in the clash colour because the key is being taken right
  // now, `latent` only dims because previews are off and nothing is taken
  // yet. The two files build the same row and must not disagree about what
  // a mark means.
  function previewShadow(display) {
    var chords = (state && state.preview_chords) || {};
    if (!display) { return null; }
    if ((chords.active || []).indexOf(display) !== -1) { return 'active'; }
    if ((chords.latent || []).indexOf(display) !== -1) { return 'latent'; }
    return null;
  }

  function makeBindRow(id, label, clashing) {
    var row = WM.make('div', 'row');
    row.appendChild(WM.make('span', 'lab', label));

    var display = state.displays[id] || '';
    var button = WM.make('button', 'bindbtn', display || 'Not set');
    var shadow = previewShadow(display);
    if (clashing[id] || shadow === 'active') { button.classList.add('clash'); }
    else if (shadow === 'latent') { button.classList.add('dim'); }
    if (shadow === 'active') {
      button.title = 'A Previews keybind uses this. It takes the key while '
                   + 'an EVE client is focused, so this bookmark does not '
                   + 'fire.';
    } else if (shadow === 'latent') {
      button.title = 'A Previews keybind is configured with this. Turning '
                   + 'previews on would take the key from this bookmark.';
    }
    button.addEventListener('click', function () { beginCapture(id, button); });
    row.appendChild(button);

    var clear = WM.make('button', 'linkbtn', 'Clear');
    clear.addEventListener('click', function () { setBind(id, ''); });
    // Round 3, B2 and L5's disabled rule: the app already knows there is
    // nothing to clear from a bind reading `Not set`, which is exactly
    // when a control is disabled. The way back out of the state stays
    // open -- the bind button and Edit... both set a value -- so this
    // does not close off its own precondition (WM.setEnabled's rule).
    WM.setEnabled(clear, !!display);
    row.appendChild(clear);

    // Manual entry: the escape hatch for non-US layouts, where the
    // event.code table maps a physical key to the wrong character. The
    // typed string is validated by the same Python rules as capture, so
    // the two cannot disagree.
    //
    // Named for what it does, not for what the user must do. `Type…`
    // was the one control in the app whose label was an instruction
    // (round 3, B6) while every other one is a verb for its effect --
    // Clear, Restore, Detect, Refresh. The ellipsis is the app's own
    // "this opens something" mark, shared with Browse…, Change… and
    // Choose folder…, which is exactly what this does.
    var typed = WM.make('button', 'linkbtn', 'Edit…');
    typed.addEventListener('click', function () {
      // Disarm first, as previews.js already did. This did not matter
      // while the prompt was window.prompt: a native OS dialog takes
      // input outside the page entirely. WM.prompt is an in-page field,
      // and an armed capture's document-level keydown handler
      // preventDefault()s EVERY key -- so arming a capture on one bind
      // and pressing Edit… on another opened a prompt that could not be
      // typed into.
      endCapture();
      // The app's own dialog, not window.prompt: WebView2 captions that
      // with the page origin, so entering a keybind in a frameless dark
      // app raised a grey box mentioning localhost.
      //
      // The FULL label, not the group-relative short one: "C1" is enough
      // to read in a block headed Finishers and is not enough in a dialog
      // that has left the block behind.
      WM.prompt('Keybind for "' + state.labels[id] + '"',
                '^ = Ctrl, ! = Alt, + = Shift, # = Win. Example: ^+s',
                state.settings.keybinds[id] || '')
        .then(function (text) {
          if (text === null) return;
          WM.send('parse_bind', text).then(function (result) {
            if (!result) return;
            if (result.error) {
              WM.send('alert_bookmarks',
                      'That is not a keybind AutoHotkey can register.');
              return;
            }
            setBind(id, result.ahk);
          });
        });
    });
    row.appendChild(typed);
    return row;
  }

  // Round 5, C8. Eighteen binds rendered as one flat list, ten of them
  // opening with the same five characters, at 61.8px a row. The groups and
  // the shortened labels are DERIVED in bookmarks.bind_groups() and arrive
  // on the payload -- see its docstring for why the derivation reads
  // BIND_LABELS and why it is not a list in this file.
  //
  // A NAMED group renders dense (a multi-column block, .es-roster's
  // technique) and the unnamed leading group does not. That is not a second
  // decision: a group has a name exactly when its members shared a token
  // that could be lifted into the heading, which is exactly what makes the
  // labels left over short enough for a column. So one derivation decides
  // both, and a fork whose labels share nothing gets one unnamed group --
  // which renders as the flat list this replaced.
  function bindGroups() {
    var groups = (state && state.groups) || [];
    if (groups.length) { return groups; }
    // No `groups` on the payload: an older bridge, or a fork that stripped
    // it. The flat list is the honest fallback, not an empty screen.
    return [{name: '', ids: state.order, short: state.labels}];
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
    var combos = Object.keys(collisions);
    warn.hidden = combos.length === 0;
    if (combos.length) {
      // Name the ACTIONS, not the raw combo: "^+s" means nothing in a
      // nineteen-row list, but the two labels sharing it do. The combo's
      // display string is still shown, once per group, for reference.
      var groups = combos.map(function (combo) {
        var ids = collisions[combo];
        var display = state.displays[ids[0]] || combo;
        var names = ids.map(function (id) { return state.labels[id]; });
        return names.join(' and ') + ' both use ' + display;
      });
      warn.textContent = groups.join('; ') +
        '. Only one of each pair will work.';
    }

    bindGroups().forEach(function (group) {
      var target = host;
      if (group.name) {
        // Same .bind-group heading previews.js uses to separate the two
        // cycle commands from the character rows -- one divider treatment
        // inside a card, not a second card heading.
        var head = WM.make('div', 'bind-group');
        head.appendChild(WM.make('span', 'bind-group-name', group.name));
        host.appendChild(head);
        target = WM.make('div', 'bind-dense');
        host.appendChild(target);
      }
      var short = group.short || {};
      group.ids.forEach(function (id) {
        target.appendChild(
          makeBindRow(id, short[id] || state.labels[id], clashing));
      });
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
    // Any other control acting on the row being captured cancels the
    // capture. The keydown handler's identity check cannot catch this on
    // its own: nothing replaces `capturing` here, only `renderBinds()`
    // rebuilds around it, so it would still match and a later keystroke
    // would silently re-apply a binding this call just changed or cleared.
    if (capturing && capturing.id === id) { endCapture(); }
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
    // Static markup, so this listener is live before the first
    // get_bookmarks resolves -- unlike the bind and window rows, which are
    // only created once state exists. A click in that gap would throw and
    // silently do nothing.
    if (!state) {
      // Nothing to render from yet, so put the checkbox back by hand.
      // Assigning .checked from script does not itself dispatch `change`
      // (only real user interaction does), so this does not re-enter this
      // handler.
      WM.el('eve-enabled').checked = !WM.el('eve-enabled').checked;
      return;
    }
    var next = JSON.parse(JSON.stringify(state.settings));
    next.enabled = WM.el('eve-enabled').checked;
    send(next);
  });

  WM.el('eve-refresh-windows').addEventListener('click', function () {
    // The window list changes when clients open and close. Route entry
    // refreshes it too, but that is no help to someone already on the page
    // when a client launches.
    WM.send('get_bookmarks').then(render);
  });

  WM.el('eve-reset-binds').addEventListener('click', function () {
    // Overwrites all 18 (bookmarks.py BIND_IDS), so it is confirmed.
    //
    // NOT window.confirm, which is what this used to call under a comment
    // claiming it was "what the rest of the page uses for a destructive
    // action" -- it was the only window.confirm in the app, and WebView2
    // renders it as browser chrome captioned with the page's origin, so a
    // destructive prompt in a frameless dark app appeared as a grey box
    // mentioning localhost. Every other destructive action here goes
    // through the styled overlay; skills.js:624 records deliberately
    // avoiding window.confirm for the same reason.
    WM.confirm('Reset keybinds',
               'Replace all 18 keybinds with the recommended defaults?',
               { destructive: true })
      .then(function (ok) {
        if (!ok) { return; }
        WM.send('reset_binds').then(render);
      });
  });

  // No `eve-import` handler. The control it drove is gone from index.html
  // -- walkthrough Settings 19, on the maintainer's use report that nobody
  // uses it. Api.import_bookmarks, its `alert_import` counterpart and
  // tests/test_bookmarks_import.py are all left alone: removing a bridge
  // method is another lane's file, and the import logic is still correct.

  WM.handle('onBookmarks', render);

  // The one and only 'onEveStatus' registration: a second WM.handle call
  // for the same name would silently overwrite this, so it drives BOTH the
  // global status-bar segment (chrome, visible on every route) and this
  // route's engine-state line -- renderEngineState() above only covers the
  // instant after a save, before the next poll tick lands.
  WM.handle('onEveStatus', function (payload) {
    var host = WM.el('evestat');
    // Hidden entirely when off, so nothing changes for users who never
    // turn the feature on.
    host.hidden = (payload.state === 'off');
    // The route's own engine line follows the same rule as after a save --
    // see showEngineRow. Done BEFORE the early return, so an engine that
    // goes off on a poll tick takes the line with it rather than leaving
    // the last state it had on screen under an unticked box.
    showEngineRow(payload.state, payload.last_error);
    if (payload.state === 'off') return;

    var live = payload.state === 'running';
    // Values are shown ONLY while running. A stopped or stale engine
    // leaves its last status file on disk, and a plausible-looking dead
    // root system is worse than no readout -- it gets acted on.
    WM.el('eve-sig').textContent = live && payload.sig ? payload.sig : '—';
    WM.el('eve-root').textContent = live && payload.root ? payload.root : '—';
    WM.el('eve-next').textContent = live && payload.next_num
      ? payload.next_num + ' / ' + (payload.next_alpha || '—') : '—';

    var warn = WM.el('eve-warn');
    var failed = payload.failed_binds || [];
    warn.hidden = failed.length === 0;
    warn.title = failed.length
      ? failed.length + ' keybind(s) failed to register — see Settings › '
        + 'Bookmarks'
      : '';

    var label = { stopped: 'Stopped', stale: 'Not responding',
                  running: 'Running' }[payload.state] || '';
    var stateEl = WM.el('eve-engine-state');
    // Must include last_error, and must match how the route renders it
    // after a save. Otherwise ticking Enable with a missing engine shows
    // "Stopped — the engine is missing…" and the next poll tick a second
    // later overwrites it with a bare "Stopped", so the one actionable
    // thing the user was told silently disappears.
    writeEngineState(stateEl, payload.state, payload.last_error, label);
    host.classList.toggle('degraded', !live);
  });

  // wm:section, not wm:route: this is a section of the Settings route now,
  // so switching to Folders is a leave and fires no route change at all.
  // WM.route dispatches wm:section('') whenever it leaves Settings, so one
  // listener still covers BOTH ways of leaving -- see app.js.
  document.addEventListener('wm:section', function (event) {
    // Refreshed on entry rather than polled: the EVE window list changes
    // when clients open and close, which is not something worth a timer.
    if (event.detail === 'bookmarks') {
      WM.send('get_bookmarks').then(render);
      return;
    }
    // Leaving must disarm an in-progress capture. Both this file and
    // previews.js install their own document-level keydown listener;
    // stopPropagation() only stops OTHER listeners further along the same
    // dispatch, not a sibling listener already attached to the same
    // document node, so an armed capture left running here would still
    // consume the next keystroke typed anywhere else -- writing a keybind
    // meant for a preview bind into this one instead, off-screen and
    // silently persisted.
    //
    // The neighbours are now Folders and Discord rather than another
    // route, which makes this strictly worse if it ever regresses: the
    // capture handler preventDefault()s EVERY key, Tab included, so an
    // escaped capture would swallow a path or a webhook being typed.
    endCapture();
  });
}());
