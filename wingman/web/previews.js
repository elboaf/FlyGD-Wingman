// Fleet Bar controls live here because both views belong to Previews: the
// settings card and the status-strip shortcut. Register the pushed handler
// before the much larger preview module below can fail during setup.
(function () {
  var button = WM.el('btn-fleetbar');
  var check = WM.el('fleetbar-enabled');
  var status = WM.el('fleetbar-enabled-status');
  var lastGood = false;
  var defaultStatus = status ? status.textContent : '';

  function render(section) {
    lastGood = !!(section && section.enabled);
    WM.fleet_bar_on = lastGood;
    if (button) {
      button.classList.toggle('active', lastGood);
      button.setAttribute('aria-pressed', lastGood ? 'true' : 'false');
      button.hidden = WM.eve_shown === false && !lastGood;
    }
    if (check && check !== document.activeElement) { check.checked = lastGood; }
  }

  function failed() {
    render({enabled: lastGood});
    if (status) { status.textContent = 'Could not change the Fleet Bar.'; }
  }

  WM.handle('onFleetBarState', render);

  if (button) {
    button.addEventListener('click', function () {
      WM.send('toggle_fleet_bar', !lastGood).then(function (res) {
        if (!res || !res.applied) { failed(); }
        else if (status) { status.textContent = defaultStatus; }
      });
    });
  }
  if (check) {
    check.addEventListener('change', function () {
      WM.send('toggle_fleet_bar', check.checked).then(function (res) {
        if (!res || !res.applied) { failed(); }
        else if (status) { status.textContent = defaultStatus; }
      });
    });
  }

  document.addEventListener('wm:settings', function (ev) {
    render(((ev.detail || {}).settings || {}).fleet_bar || {});
  });
  WM.send('fleet_bar_settings').then(function (section) {
    if (section) { render(section); }
  });
}());

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
               locked: [], lock_default: false,
               never_minimize: [], excluded: [],
               sizes: {}, client_sizes: {}, sizable: [], layout_sources: []};
  var capturing = null;
  // preview.minimize_inactive_clients, off the settings payload rather
  // than the hotkey-state one: it lives in Settings' own Previews card
  // (settings.js), not here, and this file only needs to know its CURRENT
  // value to decide whether the Never-minimize disclosure is rendered at
  // all (D6: the block is absent while the toggle is off, not present and
  // dead -- renderNeverMinimizeBlock). Reusing
  // the wm:settings listener below (already read for inert_notes) avoids
  // a second round trip for one boolean.
  var minimizeInactive = false;
  // preview.show_labels, off the same settings payload and for the same
  // reason as minimizeInactive above: sizeHint's own math needs to know
  // whether the label band is on screen, and Settings' Previews card owns
  // this field, not this file.
  var showLabels = true;
  // Bumped every time `state` is replaced wholesale, by a push or by a
  // refresh. send() samples it before its bridge call so a save that
  // resolves late can tell that a newer table has landed meanwhile.
  var pushes = 0;
  // Set when a render is skipped because a capture is armed; flushed by
  // endCapture(). See requestRender() below for why this exists.
  var pendingRender = false;
  // Set while a group lifecycle write (create/rename/delete/bind) is in
  // flight. Lifecycle and assignment controls are disabled during this
  // window so concurrent mutations cannot race; cleared in both resolve
  // and rejection paths so a failed write never leaves the form stuck.
  var groupBusy = false;
  // Whether the "Manage groups" details disclosure was open the last time
  // render() ran.  Persisted across rerenders so focus can land in the
  // Add-name field after a successful group mutation (the disclosure must
  // still be open at that point).  Defaults to false (collapsed) so a
  // fresh install does not force the panel open.
  var groupManagerOpen = false;
  // One inline configuration disclosure at a time. This is presentation
  // state only; authoritative payloads retain it only for surviving rows.
  var openDetailName = null;
  // A contained control is replaced by a render after its mutation. Keep its
  // identity long enough to focus the recreated detail, never a detached node.
  var detailFocusIntent = null;
  // Every Configure interaction supersedes pending detail work. A late bridge
  // response must not pull focus back after the user opens or closes a detail.
  var detailInteraction = 0;
  // A Copy result belongs to one chooser attempt. Another Copy, a Configure
  // change, or leaving Previews invalidates the older result and its focus.
  var copyAttempt = 0;
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
    // group_by_character: a character with a persisted group assignment
    // but no running/seen/bind entry needs a row so the select can clear
    // the assignment (design §6: "offline membership is still editable").
    Object.keys(state.hotkeys.group_by_character || {}).forEach(function (n) {
      if (!seen[n]) { seen[n] = 1; out.push({name: n, online: false}); }
    });
    return out;
  }

  function sharers(gesture) {
    // Which characters hold this chord. Several is a supported setup, not
    // a mistake: a multiboxer runs a different subset of their characters
    // each session and wants one key to mean "go to whoever of these is
    // up". host.plan_registrations merges them onto one registration and
    // picks between the running ones, so this is information, not a
    // warning -- see makeRow.
    //
    // Opted-out characters are excluded, because Python has already
    // stopped both claims this function feeds from being true of them:
    // PreviewHost._registerable drops them before plan_registrations, so
    // they neither win a chord nor share one. Without this the CYCLE row
    // -- which is live and undimmed -- painted a `duplicate` clash saying
    // the cycle keybind loses a chord it had in fact just won, and a
    // sharing character's row offered "Pressing it goes to whichever of
    // them is logged in" for a character it would never reach.
    if (!gesture) { return []; }
    var binds = state.hotkeys.characters || {};
    return Object.keys(binds).filter(function (n) {
      return binds[n] === gesture && !isExcluded(n);
    }).sort();
  }

  function clashes(gesture) {
    if (!gesture) { return null; }
    // Only a collision ACROSS the two kinds is a conflict. Focus and
    // cycle are different actions with nothing to merge into, so one of
    // them genuinely loses the registration -- unlike two characters,
    // which now share it.
    var cycles = 0;
    if (state.hotkeys.cycle_next === gesture) { cycles += 1; }
    if (state.hotkeys.cycle_prev === gesture) { cycles += 1; }
    // Named group cycles also compete for registrations; a group chord
    // matching cycle_next/cycle_prev (or another group) is a duplicate.
    state.hotkeys.groups.forEach(function (g) {
      if (g.cycle === gesture) { cycles += 1; }
    });
    if (cycles > 1 || (cycles && sharers(gesture).length)) {
      return 'duplicate';
    }
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

  function cycleOwners(gesture) {
    var owners = [];
    if (state.hotkeys.cycle_next === gesture) { owners.push('All forward'); }
    if (state.hotkeys.cycle_prev === gesture) { owners.push('All back'); }
    groups().forEach(function (group) {
      if (group.cycle === gesture) { owners.push('cycle group ' + group.name); }
    });
    return owners;
  }

  function makeBindConflict(label, gesture, character, off) {
    // An opted-out character owns no preview registration. Its retained bind
    // is deliberately visible on the row, but it cannot conflict locally.
    if (off) { return null; }
    var clash = clashes(gesture);
    var bookmark = bookmarkClash(gesture);
    // Read the registration payload here rather than infer Windows state from
    // the bind map. `clashes` owns that distinction and remains the source of
    // truth for refused versus unknown registrations.
    var registration = state.registration || {};
    var text = '';
    if (character && clash === 'duplicate') {
      // Direct-character sharing is a supported registration plan. On its
      // rows, name only the cycle owner that makes this chord incompatible.
      var owners = cycleOwners(gesture).filter(function (owner) {
        return owner !== 'cycle group ' + label;
      });
      text = gesture + ' conflicts with ' + (owners.join(', ') || 'another cycle keybind') + '.';
    } else if (clash === 'duplicate') {
      // A cycle row has no supported shared-owner role: direct characters
      // using its chord are the incompatible registrations to identify.
      var owners = cycleOwners(gesture).concat(sharers(gesture)).filter(function (owner) {
        return owner !== label && owner !== 'cycle group ' + label;
      });
      text = gesture + ' conflicts with ' + (owners.join(', ') || 'another cycle keybind') + '.';
    } else if (clash === 'refused' && registration[gesture] === false) {
      text = gesture + ' is already owned by another application.';
    } else if (bookmark === 'active') {
      text = gesture + ' conflicts with an active EVE bookmark keybind.';
    }
    return text ? WM.make('div', 'preview-bind-conflict', text) : null;
  }

  // Ordered array of named preview cycle groups from the current hotkeys
  // state. Returns a stable empty array when the payload predates groups,
  // so callers do not need null checks.
  function groups() {
    return state.hotkeys.groups || [];
  }

  function makeRow(label, gesture, online, onSet, character) {
    var row = WM.make('div', 'row');
    var lab = WM.make('span', 'lab');
    // The name in a span of its own, not as `.lab`'s own text. The cell is
    // a flex row (style.css) so that the name can ellipsize inside its
    // bounded 210px-to-320px track while any name that outgrows it
    // ellipsizes. Appended to `lab`, NOT to `row`: an extra child on
    // the row would be an extra grid cell, and the cell-count guard reads
    // appends lexically, so it could not see one that appears on offline
    // rows only.
    lab.appendChild(WM.make('span', 'lab-name', label));
    // The track is bounded rather than content-sized, so a long name ellipsizes. The title is
    // the only place the whole of it can be read. Unconditional, including
    // for names that plainly fit: knowing whether this one truncated means
    // comparing scrollWidth to clientWidth, which is a forced reflow per
    // row -- thirteen of them to avoid a tooltip repeating a short name.
    // It carries the name alone; the offline state is visible text in the
    // cell and does not need a second home here.
    lab.title = label;
    // Offline is information, not an error: the binding is still saved and
    // still works the moment that character logs in.
    //
    // The word used to be here, once per row, and round 6 moved it to a
    // STICKY GROUP HEADING over the offline block (render). The encoding is
    // still text -- `.dim` alone is colour-only state, WCAG 1.4.1, and that
    // is not what this is. What changed is how many times the reader is
    // told: eleven of thirteen rows are offline on a typical fleet, so the
    // word was on the majority of rows and the two that mattered were the
    // ones without it.
    //
    // The heading answers the objection that killed the ORIGINAL legend
    // too. That one sat above the first row of a list ~780px tall and had
    // scrolled off for most of the rows it explained; this one is
    // `position: sticky` and cannot leave while its own block is on
    // screen. See the note on `#preview-binds .bind-group` in style.css.
    if (online === false) { lab.classList.add('dim'); }
    row.appendChild(lab);

    // Whether this character is opted out of previews entirely. The
    // controls that can no longer DO anything go inert with it: there is
    // no window to lock or resize, no registration to rebind and no place
    // in the cycle, so a live control there would be one that saves a
    // setting nothing reads.
    //
    // `Never minimize` is the exception and stays live. It governs the
    // real EVE window, not the preview, and opting out does not stop it --
    // see renderLockBlock (passes `isExcluded(name)`) versus
    // renderNeverMinimizeBlock (does not) for where that asymmetry is
    // expressed now that both live in their own disclosures, not this row.
    //
    // The NAME is deliberately not dimmed either. `.dim` on a .lab means
    // "not logged in", now named once by the sticky Offline heading.
    // Borrowing it for opt-out would make that state false for every opted-
    // out character who is in fact online. The inert controls and unticked
    // Preview box carry the distinct opt-out state instead.
    var off = !!(character && isExcluded(character));

    // Track 2 of every row. A cycle row gets a filler rather than a box:
    // cycle forward/back are app commands, not characters, and there is
    // nothing to opt them out of. The ternary keeps the collapsed shape
    // unconditional without a separate character/cycle branch.
    row.appendChild(character ? makeExcludedCheck(character)
                              : document.createElement('span'));

    var button = WM.make('button', 'bindbtn', gesture || 'Not set');
    // Quiets an unbound row without a border or a fill -- see the CSS rule
    // this class adds for the measurements behind that choice. Cannot
    // collide with the three classes the chain below adds: clashes()
    // returns null for an empty gesture and no bookmark chord list
    // contains '', so an unset button is never also .clash, .unknown or
    // .dim.
    if (!gesture) { button.classList.add('unset'); }
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
      button.title = 'A cycle keybind uses this too. Only one of them can '
                     + 'have it, and the cycle keybind is the one that loses.';
    } else if (clash === 'unknown') {
      button.title = 'Not registered right now — previews are off, or ' +
                     'Windows has not reported on this keybind yet.';
    } else if (shadow === 'active') {      button.title = 'An EVE bookmark uses this keybind. This binding takes ' +
                     'it while an EVE client is focused.';
    } else if (shadow === 'latent') {
      button.title = 'An EVE bookmark is configured with this keybind. ' +
                     'Enabling bookmarks would make them collide.';
    }
    // Overwrites whatever the chain above chose, and has to. An excluded
    // character's chord is dropped by PreviewHost._registerable, so -- if
    // no other character shares it -- it never reaches hotkey_status() and
    // clashes() returns `unknown`. That branch's sentence then offers two
    // causes ("previews are off, or Windows has not reported on this
    // keybind yet") which are both FALSE here: the real cause is the
    // ticked box on this very row, and the user put it there. Left alone
    // it reads as an unexplained warning rather than as the consequence of
    // their own click.
    if (off) {
      button.title = 'Previews are off for this character, so this keybind '
                   + 'is not registered. It is still saved, and comes back '
                   + 'when you tick Preview again.';
    }
    // Appended, not another branch in the chain above: a shared chord is
    // not a warning and does not compete with one. As its own `else if`
    // it was invisible in the state the tab spends most of its time in --
    // with previews off every chord is `unknown`, which would have won
    // the chain and hidden the one sentence explaining what the key does.
    // Skipped for `duplicate`, where the cycle collision is the thing the
    // user has to act on, and for the two cycle rows, which cannot share
    // a registration with a character -- that is `duplicate` by
    // definition.
    if (character && clash !== 'duplicate') {
      var others = sharers(gesture).filter(function (n) {
        return n !== character;
      });
      if (others.length) {
        var shared = 'Shared with ' + others.join(', ') + '. Pressing it '
                     + 'goes to whichever of them is logged in.';
        button.title = button.title ? button.title + ' ' + shared : shared;
      }
    }
    button.addEventListener('click', function () {
      beginCapture(button, onSet);
    });
    // Gate on both !off (character opted out) and !groupBusy (a group write
    // is in flight). Group-cycle rows have no character so off is always
    // false there; without the groupBusy gate they would stay live while a
    // rename/delete/add/setGroupBind is pending, allowing overlapping writes.
    WM.setEnabled(button, !(off || groupBusy));
    row.appendChild(button);

    // One cell, not two tracks. Two adjacent link buttons in their own
    // tracks forced two blank header cells, which is the ragged gap
    // between "Keybind" and "Size" the table used to have.
    var acts = WM.make('span', 'rowacts');

    // Built only where there is something to act on. D6's rule (do not
    // draw a control in the state where it can only refuse), applied to
    // the control that broke it worst: `Clear` used to render on every
    // row and sit disabled on every unbound one, which on a fresh install
    // was all of them.
    //
    // Still gated on `off`, same as capture and Edit…, once it's built --
    // that part of the old behaviour was never the problem. Undoing the
    // gate too would leave `Clear` as the one live control on an
    // opted-out row: the bind button, Edit… and Size… all go inert, and
    // the tooltip on that very button promises the chord "is still saved,
    // and comes back when you tick Preview again." A live `Clear` beside
    // that sentence lets you delete the thing it just promised was kept.
    // Only the render-at-all gate (D6's rule) was the fix; whether it's
    // ALSO inert for an opted-out character is the separate, pre-existing
    // question this doesn't touch.
    if (gesture) {
      var clear = WM.make('button', 'linkbtn', 'Clear');
      clear.addEventListener('click', function () { endCapture(); onSet(''); });
      WM.setEnabled(clear, !(off || groupBusy));
      acts.appendChild(clear);
    }

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
    WM.setEnabled(typed, !(off || groupBusy));
    acts.appendChild(typed);
    row.appendChild(acts);

    // The fifth collapsed cell is Configure. Group assignment and geometry
    // live in the full-grid detail it controls, so roster scanning remains
    // identity, Preview state, and keybind first.
    var configure = null;
    if (character) {
      configure = WM.make('button', 'btn preview-configure', 'Configure');
      configure.setAttribute('aria-expanded',
                             openDetailName === character ? 'true' : 'false');
      configure.setAttribute('aria-controls', detailId(character));
      configure.setAttribute('data-preview-configure', character);
      configure.addEventListener('click', function () {
        endCapture();
        detailInteraction += 1;
        copyAttempt += 1;
        detailFocusIntent = null;
        copyStatus('', false);
        openDetailName = openDetailName === character ? null : character;
        requestRender();
        var detail = document.getElementById(detailId(character));
        if (detail) { detail.scrollIntoView({block: 'nearest'}); }
        focusConfigure(character);
      });
    }
    row.appendChild(configure || document.createElement('span'));

    // The collapsed row has one unconditional five-cell shape. Character-
    // specific group and geometry controls live in the full-grid detail;
    // cycle rows use the fillers already selected by the two ternaries above.
    // Keeping the shape branch-free makes the shared-grid invariant explicit.
    return row;
  }

  function detailId(name) {
    // URI encoding produces a stable DOM id without turning a character name
    // into selector syntax. All later identity lookups use getElementById.
    return 'preview-character-detail-' + encodeURIComponent(name);
  }

  function makeCharacterDetail(characterName, off) {
    var detail = WM.make('div', 'preview-character-detail');
    detail.id = detailId(characterName);
    detail.setAttribute('role', 'group');
    detail.setAttribute('aria-label', 'Configure ' + characterName);

    if (groups().length) {
      var assignment = WM.make('div', 'preview-detail-field');
      assignment.appendChild(WM.make('span', 'preview-detail-label', 'Cycle group'));
      assignment.appendChild(makeGroupSelect(characterName));
      detail.appendChild(assignment);
    }

    var geometry = WM.make('div', 'preview-detail-field');
    geometry.appendChild(WM.make('span', 'preview-detail-label', 'Saved geometry'));
    geometry.appendChild(makeGeometryActions(characterName, off));
    detail.appendChild(geometry);
    return detail;
  }

  function rememberDetailFocus(characterName, control) {
    detailFocusIntent = {
      name: characterName, control: control, interaction: detailInteraction
    };
  }

  function clearDetailFocus(characterName, control) {
    if (detailFocusIntent && detailFocusIntent.name === characterName
        && detailFocusIntent.control === control) {
      detailFocusIntent = null;
    }
  }

  function focusRosterHeading() {
    var heading = WM.el('preview-roster-heading');
    if (heading) { heading.focus(); return; }
    // The generated header is absent with no characters. Its attached empty
    // state is the only programmatic fallback that remains in the roster.
    var empty = WM.el('preview-binds-empty');
    if (empty && !empty.hidden) { empty.focus(); }
  }

  function focusConfigure(characterName) {
    var buttons = host.querySelectorAll('button.preview-configure');
    for (var i = 0; i < buttons.length; i++) {
      if (buttons[i].getAttribute('data-preview-configure') === characterName) {
        buttons[i].focus();
        return;
      }
    }
    focusRosterHeading();
  }

  function focusCharacterDetailControl(characterName, control) {
    var detail = document.getElementById(detailId(characterName));
    if (detail) {
      var target = detail.querySelector(
        '[data-preview-detail-control="' + control + '"]');
      if (target && !target.disabled && !target.hidden) {
        target.focus();
        return;
      }
    }
    focusConfigure(characterName);
  }

  function restoreDetailFocus() {
    if (!detailFocusIntent || groupBusy) { return; }
    var intent = detailFocusIntent;
    detailFocusIntent = null;
    if (intent.interaction !== detailInteraction || openDetailName !== intent.name) {
      return;
    }
    focusCharacterDetailControl(intent.name, intent.control);
  }

  // Follows the same shape as the Edit… path: disarm, prompt, send the raw
  // text to Python to parse, then commit. The page never parses the string
  // itself -- nothing in the suite executes this file, so the one
  // definition of what a size looks like belongs in geometry.py. Unlike
  // Edit…, an empty submission here is a no-op identical to Cancel, not a
  // clear -- there is no "unset size" to clear to, only the fallback this
  // dialog already shows as its default.
  function makeSizeButton(name, off) {
    var btn = WM.make('button', 'linkbtn', 'Size…');
    WM.setEnabled(btn, !off);
    btn.setAttribute('data-preview-detail-control', 'size');
    btn.addEventListener('click', function () {
      // Same trap bookmarks.js documents: an armed capture's document
      // keydown handler preventDefault()s every key, so a prompt opened
      // while one is live cannot be typed into.
      endCapture();
      var size = (state.sizes || {})[name];
      WM.prompt('Size for "' + name + '"', sizeHint(name),
                size ? size[0] + 'x' + size[1] : '')
        .then(function (text) {
          if (text === null || text === '') { return; }
          WM.send('parse_preview_size', text).then(function (parsed) {
            if (!parsed) { return; }
            if (parsed.error) {
              WM.send('alert_bookmarks', parsed.error);
              return;
            }
            var before = pushes;
            WM.send('set_preview_size', name, parsed.w, parsed.h)
              .then(function (res) {
                if (!res || !res.applied) {
                  if (res && res.error) { WM.send('alert_bookmarks', res.error); }
                  return;
                }
                if (pushes !== before) { return; }
                state.sizes = state.sizes || {};
                state.sizes[name] = [parsed.w, parsed.h];
              });
          });
        });
    });
    return btn;
  }

  // Plain prose: panel.js sets the dialog body with textContent, so no
  // markup survives here.
  function copySources(name) {
    return (state.layout_sources || []).filter(function (source) {
      return source && source.name !== name;
    });
  }

  // Install the intent only in refresh's authoritative-payload path, and
  // only while the detail and Copy attempt that began it are still current.
  // A cancellation, section leave, newer Copy, or Configure click cannot then
  // let a late refresh steal focus from the user's newer destination.
  function restoreCopyFocusAfterRefresh(name, interaction, attempt) {
    if (interaction !== detailInteraction || openDetailName !== name
        || attempt !== copyAttempt) { return; }
    refresh(function () {
      if (interaction === detailInteraction && openDetailName === name
          && attempt === copyAttempt) {
        rememberDetailFocus(name, 'copy');
      }
    });
  }

  function copyStatus(text, error) {
    var status = WM.el('preview-copy-status');
    if (!status) { return; }
    status.textContent = text || '';
    status.classList.toggle('err', !!error);
    status.hidden = !status.textContent;
  }

  function copyStatusForCurrent(name, interaction, attempt, text, error) {
    if (interaction !== detailInteraction || openDetailName !== name
        || attempt !== copyAttempt) { return; }
    copyStatus(text, error);
  }

  function makeCopyButton(name, off) {
    var btn = WM.make('button', 'linkbtn', 'Copy…');
    btn.setAttribute('data-copy-target', name);
    btn.setAttribute('data-preview-detail-control', 'copy');
    WM.setEnabled(btn, !off);
    btn.addEventListener('click', function () {
      endCapture();
      var interaction = detailInteraction;
      var attempt = ++copyAttempt;
      copyStatus('', false);
      var sources = copySources(name);
      var groups = [
        {label: 'Online', options: []},
        {label: 'Offline', options: []},
        {label: 'Saved placements', options: []}
      ];
      sources.forEach(function (source) {
        var group = source.online === true ? 0
                  : (source.online === false ? 1 : 2);
        groups[group].options.push({
          value: source.name, label: source.name
        });
      });
      groups = groups.filter(function (group) { return group.options.length; });
      WM.choose('Copy preview geometry',
                'Copy saved size and position to "' + name + '".',
                groups, 'Copy').then(function (source) {
        if (source === null) {
          clearDetailFocus(name, 'copy');
          return;
        }
        WM.send('copy_preview_layout', name, source).then(function (result) {
          if (!result || !result.applied) {
            copyStatusForCurrent(
              name, interaction, attempt,
              result && result.error
                ? result.error
                : 'That preview placement could not be copied.', true);
            restoreCopyFocusAfterRefresh(name, interaction, attempt);
            return;
          }
          copyStatusForCurrent(
            name, interaction, attempt,
            'Copied ' + source + '’s geometry to ' + name + '.', false);
          restoreCopyFocusAfterRefresh(name, interaction, attempt);
        });
      });
    });
    return btn;
  }

  function makeGeometryActions(name, off) {
    var actions = WM.make('span', 'geometry-actions');
    // The filler goes in whenever Size… does not. Copy… and Size… share a
    // detail field, so the dash keeps Copy from becoming an unexplained lone
    // action while preserving the guidance that a size needs a preview first.
    if (isSizable(name)) {
      actions.appendChild(makeSizeButton(name, off));
    } else {
      actions.appendChild(makeSizeFiller());
    }
    if (copySources(name).length) {
      actions.appendChild(makeCopyButton(name, off));
    }
    return actions;
  }

  function sizeHint(name) {
    var client = (state.client_sizes || {})[name];
    if (!client) {
      return 'Width x height in pixels, for example 1280x720. This client is '
           + 'not running, so the size applies next time it is.';
    }
    var size = (state.sizes || {})[name];
    // _preview_sizes (api.py) now guarantees an entry for every name that
    // can reach this branch -- client is truthy here only for a character
    // in host.client_sizes(), which is a subset of host.characters(), and
    // the bridge defaults exactly that set to (preview.width, height) when
    // no dragged/typed layout exists yet. 320 -- preview.width's own
    // default -- is kept only as a defensive fallback, not because this
    // path is expected to run.
    var width = size ? size[0] : 320;
    // Chrome: BORDER*2 across and down, and nothing else -- the character
    // name is an overlay window riding above the video now, so the window
    // is picture plus 2px on each side whether labels are on or off.
    var dw = 4, dh = 4;
    var tall = Math.round((width - dw) * client[1] / client[0]) + dh;
    return 'Your client is ' + client[0] + 'x' + client[1] + '. At this width '
         + 'an undistorted preview is ' + width + 'x' + tall
         + '; a different shape will stretch the picture.';
  }

  // The EFFECTIVE lock, not membership. Since preview.lock_default landed,
  // `locked` holds the characters that DIFFER from the default, so a plain
  // membership test would paint every box inverted the moment the default
  // was on. Resolved the same way PreviewHost._is_locked resolves it --
  // the two have to agree, and this is the page's half.
  function isLocked(name) {
    var member = (state.locked || []).indexOf(name) !== -1;
    return !!state.lock_default !== member;
  }
  function isNeverMinimize(name) {
    return (state.never_minimize || []).indexOf(name) !== -1;
  }
  function isExcluded(name) {
    return (state.excluded || []).indexOf(name) !== -1;
  }
  // Whether set_preview_size can succeed for this character at all. Python
  // decides it (api.py's `sizable`) and the page only reads the answer --
  // the rule is layout.deserialize's, and restating "running, or already in
  // layouts" here would put it in two places.
  function isSizable(name) {
    return (state.sizable || []).indexOf(name) !== -1;
  }

  // All three checkboxes follow the same shape: read the live membership list
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
  function makeLockCheck(name, off) {
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = isLocked(name);
    // The wrapper is built HERE, before the listener, and that ordering is
    // load-bearing: test_page_conventions.py looks for `'box'` within 600
    // characters of `.type = 'checkbox'`, and the listener below is long
    // enough to push it out of that window. The rule it guards is real --
    // a bare input is a white Win32 widget on a dark card -- so the fix is
    // to keep the wrapper next to the input, not to widen the window.
    //
    // The name is VISIBLE text here, not an aria-label. Under a column
    // header the word beside the box is the header repeated once per row,
    // which is why it used to be dropped and the accessible name moved
    // onto the input (DESIGN.md). In a list there is no header to carry
    // it, so the word comes back and the aria-label goes: a label with
    // text AND an aria-label would override the visible one, which is the
    // failure WCAG 2.5.3 names. What the tick MEANS reaches the reader
    // through the group's aria-labelledby, once, not per row.
    var label = WM.make('label', 'check', name);
    label.title = 'Stops this preview being moved. Right-drag is the only '
                + 'move gesture, and a lock blocks it; a left click still '
                + 'switches to the client.';
    label.prepend(WM.make('span', 'box'));
    label.prepend(box);
    box.addEventListener('change', function () {
      var wanted = box.checked;
      // Sampled before the bridge call, exactly as makeSizeButton does:
      // onPreviewHotkeys replaces `state` wholesale and fires whenever an
      // EVE client opens or closes -- routinely while someone is setting
      // rows up. Without this the patch below lands on top of the newer
      // payload using a pre-write answer, and for Lock it would also read
      // `state.lock_default` off the NEW state while `wanted` came from
      // the old render.
      var before = pushes;
      // The DEFAULT this click was made under, captured as a value rather
      // than as a revision counter. Membership is `wanted !== default`, so
      // pairing a `wanted` the user chose under one default with the other
      // one stores the exact opposite -- silently, and Python would have
      // stored the right thing, so the page and the file then disagree.
      //
      // Deliberately NOT solved by bumping `pushes` in the lock-default
      // listener, which was the first attempt. `pushes` is read by send()
      // for a different question -- "did a newer HOTKEYS TABLE land?" --
      // and a lock-default toggle replaces no such table, so bumping it
      // there made send() drop a keybind save that Python had accepted and
      // leave the page showing the old chord.
      var defaultAtSend = !!state.lock_default;
      WM.send('set_preview_locked', name, wanted).then(function (res) {
        if (!res || !res.applied) { box.checked = !wanted; return; }
        if (pushes !== before) { return; }
        if (!!state.lock_default !== defaultAtSend) {
          // The write landed against whatever Python read at the time, so
          // the file is right and only this page is behind. Re-read rather
          // than returning quietly the way the pushes guard does: there is
          // no newer payload here to be repainted from, so a bare return
          // would leave every Lock box drawn from a roster this click just
          // changed.
          refresh();
          return;
        }
        // `wanted` is the effective lock; the roster stores who DIFFERS
        // from lock_default. Python computes the same membership in
        // set_preview_locked -- this patch only has to reach the same
        // answer, or the next render would repaint from a stale list.
        var member = wanted !== defaultAtSend;
        var without = (state.locked || []).filter(function (n) {
          return n !== name;
        });
        // Filtered first and concatenated onto the filtered list, so a
        // name already present cannot be added twice.
        state.locked = member ? without.concat(name) : without;
        // The block's summary reads this list, so patching it without a
        // repaint leaves the sentence above the box stating the state
        // before the click. The SUMMARY only, and the hazard it dodges
        // has two levels: a full render() while a keybind capture is
        // armed detaches the armed button, and rebuilding this block's
        // roster would detach the checkbox running this very handler --
        // Chromium moves focus to <body> when the focused element is
        // removed, so a keyboard user ticking names would be thrown back
        // to the top of the page on every tick. See paintLockSummary.
        paintLockSummary();
      });
    });
    return inert(label, box, off);
  }

  // The row's own master switch: preview.excluded, the character-name list
  // PreviewHost reads in three places (no window, no hotkey registration,
  // no place in the cycle). Same shape as the two above, with one
  // difference that matters -- it is never passed an `off`, because it is
  // the control that turns `off` back on. Gating it with the rest would
  // opt a character out permanently, the only way back being a
  // hand-edited settings file.
  //
  // Unlike Lock and Never minimize, this one cannot patch `state` and stop
  // there: the whole row's controls are drawn from it, so a re-render is
  // what actually greys them. requestRender rather than render, so it
  // cannot detach a bind button armed by beginCapture.
  function makeExcludedCheck(name) {
    var box = document.createElement('input');
    box.type = 'checkbox';
    // Ticked means THIS CHARACTER GETS A PREVIEW, the inverse of what is
    // stored. `preview.excluded` stays an opt-out roster -- absent means
    // shown, which is what every existing install expects, so nothing
    // migrates (settings.py says so where the key is declared). Only the
    // control is inverted, because ticking a box named `Off` to turn
    // something off is a negation the reader unwinds on every row. Every
    // other checkbox in the app is ticked-means-on; this was the one that
    // was not.
    //
    // It also reads correctly at rest for the first time. Unticked-means-
    // shown made the ordinary state of this screen thirteen empty boxes
    // beside thirteen working previews -- the opposite of the truth.
    box.checked = !isExcluded(name);
    // No word beside the box: the column header carries it once. That
    // RETIRES the width problem this control was named for, rather than
    // working around it. Measured at the 840px floor when the label was
    // still a word: the card interior is 586px and the six other controls
    // then spent 504.75px of it, so a seventh track had 81.25px minus a
    // 10px column-gap to live in. " No preview" measured 93.66, which put
    // the control line at 608.41 -- 22.41px past the card's content edge,
    // and grid tracks do not wrap, so that is a clipped control at every
    // window width rather than a reflow. That is why the honest phrase was
    // once cut down to " Off".
    //
    // Those are PRE-CHANGE figures and no longer describe this screen.
    // The next measurement was taken with the words gone but the layout
    // still SEVEN tracks: they and their six intervening gaps took
    // 502.16px of the same 586px -- counted the same way 504.75 was,
    // which excludes the gap before the trailing 1fr. (Counting that gap
    // gives 512.16, and an earlier draft printed it beside 504.75, so the
    // two numbers put side by side to be compared were counted
    // differently.) That layout is gone in its turn: Lock and Never
    // minimize left for their own disclosures, the name came inline, and
    // the five tracks left measure 519.25px. The figures stand as taken,
    // because what they demonstrate has not changed -- a cell with no
    // text wants the box's 15px, so the phrase moved into a heading
    // rendered once instead of being cut to fit a track.
    box.setAttribute('aria-label', 'Show a preview for ' + name);
    var label = WM.make('label', 'check optout', '');
    label.title = 'Untick to give this character no preview window. Its own '
                + 'keybind and the cycle keybinds skip it too. Its keybind, '
                + 'size and position are kept for when you tick it again.';
    label.prepend(WM.make('span', 'box'));
    label.prepend(box);
    box.addEventListener('change', function () {
      // `wanted` is what the BOX now says (this character is previewed);
      // `excluded` is what the roster stores, and they are opposites. The
      // endpoint keeps the roster's sense, so the inversion happens here,
      // once, at the boundary -- not in api.py, which would change a
      // persisted key's meaning for the sake of a label.
      var wanted = box.checked;
      // Same generation guard the Lock and Size handlers carry, and for
      // the same reason: onPreviewHotkeys replaces `state` wholesale when
      // an EVE client opens or closes, so a save resolving after that
      // would write a pre-write roster over the newer payload. Filter
      // first and concatenate onto the filtered list, so a name the newer
      // payload already carries cannot be added twice.
      var before = pushes;
      WM.send('set_preview_excluded', name, !wanted).then(function (res) {
        if (!res || !res.applied) { box.checked = !wanted; return; }
        if (pushes !== before) { return; }
        var without = (state.excluded || []).filter(function (n) {
          return n !== name;
        });
        state.excluded = wanted ? without : without.concat(name);
        requestRender();
      });
    });
    return label;
  }

  // A control that is present but cannot do anything, for the .check
  // wrapper. WM.setEnabled sets `disabled` on the node it is given, which
  // for a checkbox is the INPUT -- and that alone would dim nothing, since
  // the input is taken out of the layout and the .box span is what shows.
  // The class dims the label; style.css also reaches the box directly.
  // Both halves are set here together so the look and the behaviour
  // cannot disagree.
  //
  // "A rule could dim the box but not the word beside it, so dim the
  // whole label" is live reasoning again, not history: `inert()` has
  // exactly one caller, makeLockCheck, and its label inside the Lock
  // disclosure carries the character's name as visible text. Dimming the
  // 15px square while the name beside it stayed at full strength would
  // read as a rendering fault. The class also carries `cursor`, which
  // sits on `.check` and nothing else can reach. style.css keeps the full
  // record where the rule lives, including the spell in between when Lock
  // sat in the row grid with an empty label and only a box to dim.
  function inert(label, box, off) {
    WM.setEnabled(box, !off);
    label.classList.toggle('inert', !!off);
    return label;
  }

  // Called only from renderNeverMinimizeBlock, which is itself hidden
  // while the global minimize toggle is off (D6) -- so this box, unlike
  // makeLockCheck, is never built into a row at all; `.check.nm.disabled`
  // went with the row it used to dim, and style.css records that where
  // the rule used to be.
  function makeNeverMinimizeCheck(name) {
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = isNeverMinimize(name);
    // Visible text, not an aria-label -- see makeLockCheck for the full
    // reasoning. `.nm` stays in the class list: it is how the smoke pass
    // and the layout probes tell this checkbox from Lock.
    var label = WM.make('label', 'check nm', name);
    label.title = 'Leaves this character\u2019s real EVE window alone when '
                + 'you switch away from it.';
    label.prepend(WM.make('span', 'box'));
    label.prepend(box);
    box.addEventListener('change', function () {
      var wanted = box.checked;
      // The fourth handler of this shape, and the last to get the guard.
      // Same reasoning as the other three.
      var before = pushes;
      WM.send('set_never_minimize', name, wanted).then(function (res) {
        if (!res || !res.applied) { box.checked = !wanted; return; }
        if (pushes !== before) { return; }
        var without = (state.never_minimize || []).filter(function (n) {
          return n !== name;
        });
        state.never_minimize = wanted ? without.concat(name) : without;
        // Summary only, never the roster -- the same two-level hazard
        // makeLockCheck's handler records, and the same reason: this
        // handler is running on a checkbox the roster owns.
        paintNeverMinimizeSummary();
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
                 previous: button.textContent, armed: false};
    // Armed BEFORE the row says "Press a key…", and only after Python
    // confirms. A chord that is already registered never reaches this
    // page -- Windows delivers it to the preview window as WM_HOTKEY --
    // so a key pressed before the host knew a capture was armed would
    // switch clients and take the foreground with it, which is what made
    // overwriting an existing bind impossible without clearing it first.
    // The host answers such a chord with onPreviewBindCaptured below;
    // an unregistered chord still arrives as an ordinary keydown.
    //
    // The row is left showing its old value until then. That window is
    // one bridge call, and a row inviting a keystroke it cannot yet
    // receive is worse than one that invites it a moment late.
    var session = capturing;
    WM.send('set_bind_capture', true).then(function () {
      // Escape, another row, or a Clear may have landed in the meantime.
      if (capturing !== session) { return; }
      session.armed = true;
      button.textContent = 'Press a key…';
      button.classList.add('capturing');
    });
  }

  function endCapture() {
    if (!capturing) { return; }
    capturing.button.classList.remove('capturing');
    capturing.button.textContent = capturing.previous || 'Not set';
    capturing = null;
    // Unconditional, including on the paths that never armed the host
    // (a capture ended inside the round trip above). Disarming something
    // already disarmed costs one bridge call; leaving it armed makes the
    // next preview hotkey a no-op until the host's own deadline expires.
    WM.send('set_bind_capture', false);
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

  function makeSizeFiller() {
    // Keeps the Saved geometry detail action legible when Size… is unavailable,
    // and says why on hover rather than leaving an unexplained blank control.
    // Withdrawing Size… must not withdraw the guidance it formerly returned.
    //
    // The dash is not decoration. An EMPTY span measured 46.44 x 0 in the
    // detail flex action layout and elementFromPoint at its centre returned null, so the title
    // below had no hover target and the explanation was unreachable. It
    // also says "nothing here, and that is expected" to someone who never
    // hovers -- an unexplained gap in one column of one row otherwise
    // reads as a rendering fault. `—` is this page's established no-value
    // glyph (bookmarks.js, list.js).
    var cell = WM.make('span', 'size-none', '—');
    cell.title = 'A size can only be set once this preview exists. Start '
               + 'the client, or move or resize its preview once.';
    return cell;
  }

  // The column headers, built ONCE above the character rows -- which is
  // the whole point of them. `Off`, `Lock` and `Never minimize` used to
  // spell their own names on every row instead of living in a header;
  // all three have since moved out -- Off's word into the `Preview`
  // heading below, Lock and Never minimize into their own per-toggle
  // disclosures (renderLockBlock, renderNeverMinimizeBlock). The
  // character name came the other way, out of a full-width line of its
  // own and into a fixed track, which is what `Character` names. So this
  // header now names a fixed five tracks, not a conditional six or seven.
  // `Clear` and `Edit...` share one cell now (`.rowacts`, built in
  // makeRow). `Size...` lives in the expanded Saved geometry detail; all
  // three are verbs on controls, not names of collapsed-row columns.
  //
  // The width that bought is not per-row. Each column is ONE shared
  // max-content track, so the longest text in a column sizes it for the
  // header and all thirteen rows together.
  //
  // Sentence case at --fs-muted with no tracking, matching the recording
  // list's headers (index.html's .list-head) rather than .bind-group-name
  // -- these label data, and DESIGN.md's rule is that a header sits below
  // body size for exactly that reason. It also keeps this out of the four
  // uppercase .14em rules test_page_conventions.py pins by name.
  //
  // NOT built inside makeRow, and not merely for tidiness: the cell-count
  // guard derives the per-row track count from makeRow's own appends, so
  // a header appended there would be counted as extra controls on every
  // row. It contributes the same number of TRACK cells a character row
  // does -- five. (It used to contribute one FEWER than a character row
  // appends, because the `.lab` spanned the whole row rather than sitting
  // in a track and the guard subtracted it. The name is a track now, so
  // the two counts are simply equal.)
  //
  // The one blank cell is `.rowacts`'s track: Clear and Edit... share it
  // rather than each claiming a heading of their own. They are
  // subordinate to the bind button they act on -- naming them in the
  // header would claim they are columns of data, and they are verbs.
  //
  // A wrong cell count here reaches the rows below, not just the header,
  // because the columns are shared `max-content` tracks. Measured in the
  // ?dev=1 harness at 840x625 against the SEVEN-column layout, before
  // Lock and Never minimize moved to their own disclosures and before the
  // name came inline: deleting a heading in turn, every later column's
  // controls shifted right by the width the deleted heading no longer
  // claimed. Only the LAST cell was ever free to delete without moving
  // anything after it. The layout it was taken on is gone; the mechanism
  // it demonstrates is not, which is why the figures stand as taken.
  //
  // Vertical placement genuinely does not cascade -- but the rule that
  // makes that true has changed hands. Every row used to lead with
  // `.lab { grid-column: 1 / -1 }`, whose definite column-start of 1 reset
  // the auto-placement cursor to a fresh row for free. The name sits in a
  // track now, so `#preview-binds .row > :first-child
  // { grid-column-start: 1 }` in style.css does that job instead, and the
  // hazard arrived with the inline name rather than with the grid.
  function makeHeadRow() {
    var row = WM.make('div', 'row bind-head');
    var cells = ['Character', 'Preview', 'Keybind', '', 'Configure'];
    cells.forEach(function (text, index) {
      var cell = WM.make('span', '', text);
      if (index === 0) {
        // The generated Character cell is the roster's stable focus fallback
        // and the narrow screenshot anchor, not the static card heading.
        cell.id = 'preview-roster-heading';
        cell.setAttribute('tabindex', '-1');
      }
      row.appendChild(cell);
    });
    return row;
  }

  // How many names a summary spells out before it counts the rest. Same
  // number and same reason as alerts.js's HEALTH_NAMES_MAX: a list of
  // names is what the reader can act on, and a bare count is not.
  var EXC_NAMES_MAX = 3;

  function nameList(names) {
    var shown = names.slice(0, EXC_NAMES_MAX);
    var rest = names.length - shown.length;
    return rest > 0 ? shown.join(', ') + ' and ' + rest + ' more'
                    : shown.join(', ');
  }

  // The summary is keyed on the RESOLVED state, not on the exception list
  // being empty. With lock_default on and no exceptions every character is
  // already locked, so a door inviting the reader to lock one would offer
  // something already done.
  function lockSummary(names, all) {
    if (!names.length) { return 'Lock individual characters'; }
    if (names.length === all.length) { return 'Locked: every character'; }
    var unlocked = all.filter(function (n) {
      return names.indexOf(n) === -1;
    });
    // Past halfway the exception is shorter than the rule, and naming the
    // shorter side is what makes the sentence readable at 13 characters.
    if (unlocked.length < names.length) {
      return 'Locked: every character except ' + nameList(unlocked);
    }
    return 'Locked: ' + nameList(names);
  }

  // The summary sentence on its own, split out from the roster beneath it
  // because that roster CONTAINS the checkbox whose change handler asks
  // for the repaint. Rebuilding the list from there empties it and builds
  // a fresh box for every character including the one just clicked;
  // Chromium moves focus to <body> when the focused element is removed,
  // so a keyboard user ticking names loses focus on every tick and has to
  // Tab from the top of the page again -- thirteen characters, thirteen
  // restarts.
  //
  // The rebuild would also be pure waste. set_preview_locked changes one
  // name, the clicked box already shows its own value, and no other box's
  // isLocked() answer moves. The one thing that DOES move them all is
  // lock_default changing mid-flight, and makeLockCheck's defaultAtSend
  // branch answers that with a full refresh() rather than through here.
  function paintLockSummary() {
    var summary = WM.el('preview-lock-exceptions-summary');
    if (!summary) { return; }
    var all = rows().map(function (entry) { return entry.name; });
    summary.textContent = lockSummary(all.filter(isLocked), all);
  }

  // The character-list half of the Lock disclosure: which characters are
  // currently locked, and -- through paintLockSummary -- the sentence that
  // names them. Called from render() only. The change handler repaints the
  // summary and leaves the roster standing, for the reason above.
  function renderLockBlock() {
    var box = WM.el('preview-lock-exceptions');
    var list = WM.el('preview-lock-exceptions-list');
    if (!box || !list) { return; }
    var all = rows().map(function (entry) { return entry.name; });
    paintLockSummary();
    list.textContent = '';
    all.forEach(function (name) {
      list.appendChild(makeLockCheck(name, isExcluded(name)));
    });
    box.hidden = !all.length;
  }

  // never_minimize has no default toggle of its own to resolve against --
  // it is a plain membership list, unlike locked/lock_default -- so this
  // summary has two states where lockSummary has four.
  function nmSummary(names) {
    return names.length ? 'Never minimized: ' + nameList(names)
                        : 'Exempt individual characters';
  }

  // The summary half, split from the roster for the reason
  // paintLockSummary states in full: the roster holds the checkbox that
  // asks for this repaint, and rebuilding it there would detach that
  // checkbox and drop the keyboard user's focus to <body>.
  function paintNeverMinimizeSummary() {
    var summary = WM.el('preview-nm-exceptions-summary');
    if (!summary) { return; }
    var all = rows().map(function (entry) { return entry.name; });
    summary.textContent = nmSummary(all.filter(isNeverMinimize));
  }

  // The character-list half of the Never-minimize disclosure, mirroring
  // renderLockBlock. Called from render() only; makeNeverMinimizeCheck's
  // change handler goes through paintNeverMinimizeSummary instead, so the
  // summary never lags one click behind the box the user just ticked
  // without the roster being rebuilt underneath them.
  function renderNeverMinimizeBlock() {
    var box = WM.el('preview-nm-exceptions');
    var list = WM.el('preview-nm-exceptions-list');
    if (!box || !list) { return; }
    var all = rows().map(function (entry) { return entry.name; });
    // D6: the whole block is absent while the global toggle is off, not
    // present and dead -- nothing here can do anything in that state.
    // Decided here rather than in the summary painter, which is only ever
    // reached from inside a block that is on screen.
    box.hidden = !minimizeInactive || !all.length;
    if (box.hidden) { return; }
    paintNeverMinimizeSummary();
    list.textContent = '';
    all.forEach(function (name) {
      // NOT gated on isExcluded, unlike the Lock block above. Opting a
      // character out stops their preview; _activate_client still
      // consults this for the real EVE window, so a dimmed box here would
      // leave a setting in force with no control to change it.
      list.appendChild(makeNeverMinimizeCheck(name));
    });
  }

  function appendBindRow(label, gesture, online, onSet, character) {
    host.appendChild(makeRow(label, gesture, online, onSet, character));
    if (character && openDetailName === character) {
      host.appendChild(makeCharacterDetail(character, isExcluded(character)));
    }
    var conflict = makeBindConflict(label, gesture, character, isExcluded(character));
    if (conflict) { host.appendChild(conflict); }
  }

  function render() {
    var list = rows();
    var openDetailMissing = openDetailName && !list.some(function (entry) {
      return entry.name === openDetailName;
    });
    if (openDetailMissing) {
      openDetailName = null;
      detailFocusIntent = null;
    }
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
      off.hidden = !!(state.enabled || !off.textContent);
    }

    // `true`, not state.enabled: the cycle chords are not characters and
    // have no online state to report. Dimming them while previews were
    // off was half of what made the whole list grey at once.
    appendBindRow('All forward', state.hotkeys.cycle_next,
                  true, function (g) { setBind('cycle_next', g); });
    appendBindRow('All back', state.hotkeys.cycle_prev,
                  true, function (g) { setBind('cycle_prev', g); });

    // Named group keybind rows. Each group gets its own row rendered by
    // the shared makeRow so it inherits the five-track shape and the same
    // Clear/Edit… controls. Rendered after All rows and before the
    // character divider -- the task brief's wireframe B ordering.
    groups().forEach(function (group) {
      appendBindRow(group.name, group.cycle, true,
                    function (g) { setGroupBind(group.id, g); });
    });

    // Manage groups disclosure: Add/Rename…/Delete. Rendered after group
    // rows and before the character separator so it lives in the "keys"
    // section of the table. Rendered even when groups().length is 0 so
    // the Add field is always available.
    host.appendChild(makeGroupManager());

    // An UNNAMED rule, then the column headers. The rule used to be a
    // `.bind-group` reading `Characters`, which sat one line above a
    // column header reading `Character` -- the same word twice, naming the
    // same thing, in two type treatments. The word went; the separation
    // stayed, because the two cycle rows above are app commands with no
    // character attached and ran into the list without it.
    //
    // It is a spanning element rather than a border on the header cells
    // because `.row` is display:contents here: a per-cell border is cut by
    // every column gap and renders as dashes. See the note on
    // `#preview-binds .bind-group:empty` in style.css.
    //
    // Rendered only when there are characters to head. With none, the
    // #preview-binds-empty hint below is the whole story and a rule over
    // nothing is worse than no rule.
    if (list.length) {
      host.appendChild(WM.make('div', 'bind-group'));
      host.appendChild(makeHeadRow());
    }

    // Online first, then a heading, then the rest. `rows()` already returns
    // them in that order, so this splits rather than sorts.
    //
    // ONLY while previews are on. With the host stopped Python sends
    // characters: [] and every row would fall into the offline half, which
    // is a claim we cannot make -- the same reason makeRow is passed null
    // rather than false below. The banner above says "off" instead, and
    // one undivided list is the honest shape for "we do not know".
    var running = list;
    var offline = [];
    if (state.enabled) {
      running = list.filter(function (e) { return e.online; });
      offline = list.filter(function (e) { return !e.online; });
    }

    function paint(entry) {
      appendBindRow(
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
        entry.name);
    }

    running.forEach(paint);
    if (offline.length) {
      // The whole encoding of the offline state, and the only place it is
      // written. Every row below it is dim; the dimming reinforces the
      // word rather than replacing it, which is what keeps this out of
      // WCAG 1.4.1.
      var off = WM.make('div', 'bind-group');
      off.appendChild(WM.make('span', 'bind-group-name', 'Offline'));
      host.appendChild(off);
      offline.forEach(paint);
    }

    var empty = WM.el('preview-binds-empty');
    if (empty) { empty.hidden = list.length > 0; }
    var copyEmpty = WM.el('preview-copy-empty');
    if (copyEmpty) {
      copyEmpty.hidden = !list.length || list.some(function (entry) {
        return copySources(entry.name).length > 0;
      });
    }
    renderLockBlock();
    renderNeverMinimizeBlock();
    if (openDetailMissing) { focusRosterHeading(); }
    else { restoreDetailFocus(); }
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
        //
        // The sentence no longer offers "another keybind may already use
        // it" as a cause. set_preview_binds refuses a chord it cannot
        // parse or a table it cannot persist, and nothing else -- a chord
        // another CHARACTER holds is now a supported setup that saves
        // like any other, so naming it here sent people to look at a row
        // that was never the problem.
        WM.send('alert_bookmarks',
                'That binding was not saved. The keybind could not be ' +
                'read, or the settings file could not be written.');
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

  // Narrow group keybind writer. Calls set_preview_cycle_group_bind instead
  // of the full set_preview_binds (send(next)) so only the one group's chord
  // changes and all other groups/characters/cycle_next/prev are untouched.
  // The generation guard uses `pushes` as in send(): a push that overtook
  // the bridge call carries the authoritative table.
  function setGroupBind(groupId, gesture) {
    // Synchronous guard: a second click while a write is already in flight
    // must be rejected immediately, before endCapture() or any send.
    // requestRender() defers during capture, so without this guard old
    // controls remain live and a repeated click under capture would race.
    if (groupBusy) { return; }
    endCapture();
    // Participates in the shared groupBusy serialisation lock so that
    // assignment selects, lifecycle controls, and other group writes stay
    // disabled for the duration of this in-flight bridge call.
    groupBusy = true;
    requestRender();
    var generation = pushes;
    WM.send('set_preview_cycle_group_bind', groupId, gesture).then(function (res) {
      groupBusy = false;
      if (!res || !res.applied) {
        // On refusal: apply the authoritative table from res.hotkeys when
        // available and no newer push has landed.  This avoids showing a
        // stale/deleted group for the extra round-trip that refresh() would
        // require.  Fall back to refresh() only when res or res.hotkeys is
        // absent (bridge error or server omission).
        if (res && res.hotkeys && generation === pushes) {
          state.hotkeys = res.hotkeys;
          state.hotkeys.groups = state.hotkeys.groups || [];
          state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
          requestRender();
        } else {
          refresh();
        }
        WM.send('alert_bookmarks',
                res && res.error
                  ? res.error
                  : 'That binding was not saved. The keybind could not be ' +
                    'read, or the settings file could not be written.');
        return;
      }
      if (generation !== pushes) {
        // A newer push already applied authoritative state; skip the stale
        // response but still repaint so the busy lock is visually cleared.
        requestRender();
        return;
      }
      if (res.hotkeys) {
        state.hotkeys = res.hotkeys;
        state.hotkeys.groups = state.hotkeys.groups || [];
        state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
      }
      requestRender();
    });
  }

  // Build the group assignment <select> for one character detail. The
  // detail spans the grid, so returning this control never adds a row cell.
  //
  // Not gated on the `off` (opted-out) state: unlike the keybind button
  // and Size..., which can do nothing for an opted-out character, group
  // membership is saved and waits for the preview to come back.
  function makeGroupSelect(characterName) {
    var sel = WM.make('select', 'field preview-group-select');
    sel.setAttribute('aria-label', 'Cycle group for ' + characterName);
    sel.setAttribute('data-preview-detail-control', 'group');

    // Always-first option: no group assigned (All only).
    var allOpt = document.createElement('option');
    allOpt.value = '';
    allOpt.textContent = 'All only';
    sel.appendChild(allOpt);

    // One option per named group, in creation order.
    groups().forEach(function (g) {
      var opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = g.name;
      sel.appendChild(opt);
    });

    // Reflect current assignment.
    var gbc = state.hotkeys.group_by_character || {};
    sel.value = gbc[characterName] || '';
    // Disabled during any group write (assignment, lifecycle, or bind) so
    // concurrent changes from multiple selects can't stack.
    WM.setEnabled(sel, !groupBusy);

    sel.addEventListener('change', function () {
      // Synchronous guard: a concurrent write must be rejected before any
      // state change.  Without this, rapid changes under an armed capture
      // (where requestRender() defers) can stack.
      if (groupBusy) { return; }
      var selectedId = sel.value;
      rememberDetailFocus(characterName, 'group');
      // Disable lifecycle and assignment controls for the duration.
      groupBusy = true;
      requestRender();
      // Capture the push generation before the bridge call. If a newer
      // onPreviewHotkeys push arrives while the call is in flight it
      // replaces state.hotkeys wholesale; applying the stale response
      // on top of that would overwrite the authoritative table. Same
      // guard as setGroupBind.
      var before = pushes;
      WM.send('set_preview_character_group', characterName, selectedId)
        .then(function (res) {
          groupBusy = false;
          if (!res || !res.applied) {
            // Revert: re-read from state.
            sel.value = (state.hotkeys.group_by_character || {})[characterName] || '';
            WM.send('alert_bookmarks',
                    res && res.error
                      ? res.error
                      : 'That group change was not saved.');
            // Apply the authoritative table when available and no newer push
            // has landed since the call was issued.  This keeps the groups
            // list coherent without a full refresh() round-trip.
            if (res && res.hotkeys && pushes === before) {
              state.hotkeys = res.hotkeys;
              state.hotkeys.groups = state.hotkeys.groups || [];
              state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
            }
            requestRender();
            focusGroupSelect(characterName);
            return;
          }
          if (pushes !== before) {
            // A newer push already applied authoritative state; skip the
            // stale hotkeys update but still repaint so disabled controls
            // are re-enabled (groupBusy is already false above).
            requestRender();
            focusGroupSelect(characterName);
            return;
          }
          if (res.hotkeys) {
            state.hotkeys = res.hotkeys;
            state.hotkeys.groups = state.hotkeys.groups || [];
            state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
          }
          requestRender();
          focusGroupSelect(characterName);
        });
    });
    return sel;
  }

  // Restore only the still-current detail intent. `restoreDetailFocus` owns
  // the interaction token check, preventing a late assignment reply from
  // focusing a closed detail or any control after the section has changed.
  function focusGroupSelect(characterName) {
    if (!detailFocusIntent || detailFocusIntent.name !== characterName) { return; }
    restoreDetailFocus();
  }

  // Rename a named group. Called from the management disclosure. Ends the
  // capture first (an armed capture's keydown handler would eat the dialog).
  function renameGroup(group) {
    // Synchronous guard: reject if a write is already in flight before
    // ending capture or opening the prompt.
    if (groupBusy) { return; }
    endCapture();
    WM.prompt('Rename group', 'Enter a new name for "' + group.name + '"',
              group.name).then(function (text) {
      if (text === null || text.trim() === '') { return; }
      groupBusy = true;
      requestRender();
      var before = pushes;
      WM.send('rename_preview_cycle_group', group.id, text.trim())
        .then(function (res) {
          groupBusy = false;
          if (!res || !res.applied) {
            WM.send('alert_bookmarks',
                    res && res.error
                      ? res.error
                      : 'That group change was not saved.');
            // Apply the authoritative table when available and no newer push
            // has landed.  A refused rename carries the unchanged name.
            if (res && res.hotkeys && pushes === before) {
              state.hotkeys = res.hotkeys;
              state.hotkeys.groups = state.hotkeys.groups || [];
              state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
            }
            requestRender();
            focusGroupManager();
            return;
          }
          if (pushes !== before) {
            // A newer push has already applied authoritative state; skip
            // the stale response but still repaint with current data.
          } else if (res.hotkeys) {
            state.hotkeys = res.hotkeys;
            state.hotkeys.groups = state.hotkeys.groups || [];
            state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
          }
          requestRender();
          focusGroupManager();
        });
    });
  }

  // Restore keyboard focus to the first surviving group management control
  // (a Delete button for a remaining group), then the Add-name field, then
  // any enabled control in the Previews section.
  //
  // Called AFTER requestRender() rebuilds the DOM so it queries attached
  // nodes only. The pattern matches focusCopyTarget: named target first,
  // section-level fallback second, no focus on detached nodes.
  function focusGroupManager() {
    var section = WM.el('section-previews');
    if (!section) { return; }
    // Prefer the Add-name field: it is always present and is never the
    // logically-deleted group's own control, so it stays valid even when
    // a stale push causes the deleted group to re-appear transiently.
    // A Delete button for a surviving group is a valid but less-stable
    // target because the DOM order after a stale push can be ambiguous.
    var addField = section.querySelector(
      '.group-add-name:not([hidden]):not(:disabled)');
    if (addField) { addField.focus(); return; }
    // If the Add field is somehow absent, try a surviving group's button.
    var delBtn = section.querySelector(
      '.group-delete-btn:not([hidden]):not(:disabled)');
    if (delBtn) { delBtn.focus(); return; }
    // Last resort: any enabled interactive control in the section.
    var fallback = section.querySelector(
      'button:not([hidden]):not(:disabled), '
      + 'input:not([hidden]):not(:disabled), '
      + 'select:not([hidden]):not(:disabled)');
    if (fallback) { fallback.focus(); }
  }

  // Delete a named group. Called from the management disclosure. Ends the
  // capture first, then shows a WM.confirm with the group name and member
  // count so the user knows what they are removing.
  function deleteGroup(group) {
    // Synchronous guard: reject if a write is already in flight before
    // ending capture or computing the member count.
    if (groupBusy) { return; }
    endCapture();
    var gbc = state.hotkeys.group_by_character || {};
    var members = Object.keys(gbc).filter(function (n) {
      return gbc[n] === group.id;
    });
    var memberText = members.length === 1
      ? '1 character' : members.length + ' characters';
    var msg = 'Delete group "' + group.name + '"? ' + memberText +
              ' will return to All only cycling.';
    WM.confirm('Delete group', msg).then(function (confirmed) {
      if (!confirmed) { return; }
      groupBusy = true;
      requestRender();
      var before = pushes;
      WM.send('delete_preview_cycle_group', group.id).then(function (res) {
        groupBusy = false;
        if (!res || !res.applied) {
          WM.send('alert_bookmarks',
                  res && res.error
                    ? res.error
                    : 'That group change was not saved.');
          // Apply the authoritative table when available and no newer push
          // has landed.  A refused delete confirms the group is still present.
          if (res && res.hotkeys && pushes === before) {
            state.hotkeys = res.hotkeys;
            state.hotkeys.groups = state.hotkeys.groups || [];
            state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
          }
          requestRender();
          // Refusal: the group is still present; repaint re-enables its
          // controls but focus falls to <body> without an explicit restore.
          focusGroupManager();
          return;
        }
        if (pushes !== before) {
          // A newer push has already applied authoritative state.
          // Skip the stale hotkeys but still repaint and restore focus --
          // the group is gone either way and focus must not fall to <body>.
        } else if (res.hotkeys) {
          state.hotkeys = res.hotkeys;
          state.hotkeys.groups = state.hotkeys.groups || [];
          state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
        }
        requestRender();
        focusGroupManager();
      });
    });
  }

  // Build the "Manage groups" disclosure: a collapsed <details> with a
  // <summary> showing "Manage groups (N)", then a text field and Add button,
  // then one Rename…/Delete row per existing group.  Rendered inside
  // #preview-binds spanning the full grid width via .preview-group-manager.
  // Uses <details> rather than a plain div so:
  //   1. The panel is collapsible -- it does not stay permanently expanded.
  //   2. It does NOT inherit the bind-group sticky-header CSS that would
  //      pin it at the top and overlay character rows.
  // Called from render() after the group keybind rows and before the
  // character separator.  Open state is preserved across rerenders via
  // groupManagerOpen so focus restoration works.
  function makeGroupManager() {
    var el = document.createElement('details');
    el.className = 'preview-group-manager';
    // Restore open state from the module-level flag so a rerender does not
    // collapse the panel while the user is typing or clicking.
    if (groupManagerOpen) { el.open = true; }
    el.addEventListener('toggle', function () {
      groupManagerOpen = el.open;
    });

    var sumEl = document.createElement('summary');
    var count = groups().length;
    sumEl.textContent = count
      ? 'Manage groups (' + count + ')'
      : 'Manage groups';
    el.appendChild(sumEl);

    var body = WM.make('div', 'group-manager-body');
    var addRow = WM.make('div', 'group-add-row');
    var nameField = WM.make('input', 'field group-add-name');
    nameField.type = 'text';
    nameField.placeholder = 'New group name';
    nameField.setAttribute('aria-label', 'New group name');
    var addBtn = WM.make('button', 'btn group-add-btn', 'Add');
    WM.setEnabled(addBtn, !groupBusy);
    WM.setEnabled(nameField, !groupBusy);

    function doAdd() {
      if (groupBusy) { return; }
      var name = nameField.value.trim();
      if (!name) { return; }
      groupBusy = true;
      requestRender();
      var before = pushes;
      WM.send('create_preview_cycle_group', name).then(function (res) {
        groupBusy = false;
        if (!res || !res.applied) {
          WM.send('alert_bookmarks',
                  res && res.error
                    ? res.error
                    : 'That group change was not saved.');
          // Apply the authoritative table when available and no newer push
          // has landed.  A refused create may carry a table that already
          // reflects the reason for refusal (e.g. duplicate name).
          if (res && res.hotkeys && pushes === before) {
            state.hotkeys = res.hotkeys;
            state.hotkeys.groups = state.hotkeys.groups || [];
            state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
          }
          requestRender();
          // The old nameField is detached by requestRender(); query the new
          // one so focus reaches the rebuilt Add field, not a detached node.
          focusGroupManager();
          return;
        }
        if (pushes !== before) {
          // A newer push has already applied authoritative state; skip
          // the stale response but still repaint.
        } else if (res.hotkeys) {
          state.hotkeys = res.hotkeys;
          state.hotkeys.groups = state.hotkeys.groups || [];
          state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
        }
        // Clear the submitted name so the field does not show a stale value
        // after repaint (a non-empty field invites a duplicate-add attempt).
        nameField.value = '';
        requestRender();
        // The old nameField is detached by requestRender(); query the new one.
        focusGroupManager();
      });
    }

    // Commit on Enter (not blur -- Settings commit rule: free text commits on
    // Enter or an explicit button, never on blur).
    nameField.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); doAdd(); }
    });
    addBtn.addEventListener('click', doAdd);

    addRow.appendChild(nameField);
    addRow.appendChild(addBtn);
    body.appendChild(addRow);

    // Per-group Rename…/Delete rows.
    groups().forEach(function (group) {
      var gRow = WM.make('div', 'group-manage-row');
      var gName = WM.make('span', 'group-manage-name', group.name);
      var renBtn = WM.make('button', 'btn group-rename-btn', 'Rename…');
      var delBtn = WM.make('button', 'btn danger group-delete-btn', 'Delete');
      WM.setEnabled(renBtn, !groupBusy);
      WM.setEnabled(delBtn, !groupBusy);
      renBtn.addEventListener('click', function () { renameGroup(group); });
      delBtn.addEventListener('click', function () { deleteGroup(group); });
      gRow.appendChild(gName);
      gRow.appendChild(renBtn);
      gRow.appendChild(delBtn);
      body.appendChild(gRow);
    });

    el.appendChild(body);
    return el;
  }

  function refresh(beforeRender) {
    return WM.send('get_preview_hotkey_state').then(function (payload) {
      if (!payload) { return; }
      state = payload;
      pushes += 1;
      state.hotkeys = state.hotkeys || {characters: {}, cycle_next: '',
                                        cycle_prev: ''};
      state.hotkeys.groups = state.hotkeys.groups || [];
      state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
      state.locked = state.locked || [];
      state.never_minimize = state.never_minimize || [];
      state.excluded = state.excluded || [];
      if (beforeRender) { beforeRender(); }
      requestRender();
    });
  }

  document.addEventListener('keydown', function (event) {
    if (!capturing) { return; }
    // Not armed until Python has confirmed and the row SAYS "Press a
    // key…". Between the click and that ack there is one bridge call, and
    // swallowing a keystroke during it would be the armed-but-invisible
    // failure the smoke checklist already has an entry for -- the key
    // disappears with nothing on screen claiming to want it. Returning
    // without preventDefault leaves the press behaving as though the
    // capture had not started yet, which is the truth.
    if (!capturing.armed) { return; }
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
    state.hotkeys.groups = state.hotkeys.groups || [];
    state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
    state.locked = state.locked || [];
    state.never_minimize = state.never_minimize || [];
    state.excluded = state.excluded || [];
    requestRender();
  });

  // The other half of the capture path. A chord this app has already
  // registered is delivered to the preview window as WM_HOTKEY and never
  // reaches this page, so the keydown listener below cannot see it --
  // the host redirects it here instead while a capture is armed.
  //
  // No parse step: the text is the canonical display form
  // plan_registrations registered, which is the same notation
  // capture_preview_bind and parse_preview_bind return. Nothing on this
  // page has ever decided what a chord looks like, and this does not
  // start.
  WM.handle('onPreviewBindCaptured', function (payload) {
    if (!capturing || !payload || !payload.gesture) { return; }
    // Same ordering as the keydown path below: hold the session, disarm,
    // then apply -- onSet re-renders, which detaches the armed button.
    var apply = capturing.onSet;
    endCapture();
    apply(payload.gesture);
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
    // Absent means on, matching settings.py's default -- same spelling as
    // settings.js's own box.checked line and minimizeInactive above, which
    // is `!!(...)` for the identical reason: when s.preview is missing,
    // `s.preview.show_labels !== false` is undefined, not true.
    showLabels = !(s.preview && s.preview.show_labels === false);
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

  // The same narrow exception, for the same reason, and here it is not a
  // convenience: every Lock box on this screen is painted by resolving
  // `state.lock_default` against the roster (isLocked), so a stale copy
  // does not merely lag -- it shows the exact INVERSE of every row. The
  // control that writes it is in this same Settings section, a few
  // hundred pixels above the table, so the wrong state would be on screen
  // beside the thing that caused it.
  document.addEventListener('wm:preview-lock-default', function (event) {
    state.lock_default = !!(event.detail && event.detail.enabled);
    requestRender();
  });

  // Refreshed on route entry rather than polled, same reasoning as
  // bookmarks.js: the live/known character set changes when EVE clients
  // open and close, which is not something worth a timer. `wm:settings`
  // (dispatched only when the global settings payload changes) would not
  // fire on a plain tab switch and was the wrong event to listen for here.
  // wm:section, not wm:route -- see the matching comment in bookmarks.js.
  document.addEventListener('wm:section', function (event) {
    copyAttempt += 1;
    copyStatus('', false);
    if (event.detail === 'previews') {
      refresh();
      return;
    }
    // A response after navigation must not move focus into a hidden section.
    detailInteraction += 1;
    detailFocusIntent = null;
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
