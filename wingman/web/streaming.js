// The Streaming section (#317): one card, the mirror as its subject --
// and (#319) the Combat auto-start section inside it, whose recorded
// chord IS the consent gate: no checkbox, presence = enabled, clearing =
// the explicit off.
//
// A READ on section entry, not a launch push, for the reason alerts.js
// documents: the supervisor exists before the window, so a state
// discovered at launch would be pushed into nothing. The poll tick's
// onMirrorStatus keeps the mirror row honest while the section is
// visible. The chord row is deliberately NOT tick-rendered -- the tick
// would fight an armed capture's "Press a key…" label and wipe a fresh
// capture warning -- so it renders on entry and on its own commits only.
// Nothing else writes the chord: this card is its only surface.
(function () {
  var stateEl = WM.el('mirror-state');
  var chordBtn = WM.el('chord-capture');
  if (!stateEl || !chordBtn) { return; }

  var toggleBtn = WM.el('mirror-toggle');
  var errorEl = WM.el('mirror-error');
  // The ceremony (#321): the register/start/pick walk under the mirror row
  // with its never-main-exe warning, the resolved exe path Discord's Add-it
  // dialog needs, and the chord-side map instruction plus the diagnostic
  // that lives next to the armed row it explains. All hide with their
  // halves of the card when the installation has no mirror -- setup text
  // for a feature that cannot run is its own failure mode.
  var ceremonyEl = WM.el('mirror-ceremony');
  var exeWarningEl = WM.el('mirror-exe-warning');
  var exePathEl = WM.el('mirror-exe-path');
  // The rest of the registration family: the EVE-slider warning (Discord
  // must not detect the raw EVE client) and the stream-settings advice,
  // which is about the mirror's own stream entry.
  var eveOffEl = WM.el('mirror-eve-off');
  var streamSettingsEl = WM.el('stream-settings-hint');
  var groupEl = WM.el('combat-autostart-group');
  var enableHintEl = WM.el('chord-enable-hint');
  var chordCeremonyEl = WM.el('chord-ceremony');
  var diagnosticEl = WM.el('chord-diagnostic');
  var chordClear = WM.el('chord-clear');
  var collisionEl = WM.el('chord-collision');
  var msgEl = WM.el('chord-msg');
  var sendableEl = WM.el('chord-sendable');
  var quietInput = WM.el('coupling-quiet');
  var couplingStateEl = WM.el('coupling-state');
  var latchedEl = WM.el('coupling-latched');
  var lastFiredEl = WM.el('coupling-last-fired');
  var visible = false;
  var capturing = false;
  var chordDisplay = '';
  var quietDraft = null;
  // The last mirror payload the card rendered: the toggle reads it to
  // decide which half it is sending, and a refused toggle leaves it
  // untouched so the row keeps showing what is true.
  var lastMirror = null;

  function renderMirror(payload) {
    if (!payload || !payload.available) {
      lastMirror = null;
      stateEl.textContent = 'Not available in this installation';
      toggleBtn.hidden = true;
      errorEl.textContent = '';
      ceremonyEl.hidden = true;
      exeWarningEl.hidden = true;
      exePathEl.hidden = true;
      eveOffEl.hidden = true;
      streamSettingsEl.hidden = true;
      return;
    }
    ceremonyEl.hidden = false;
    exeWarningEl.hidden = false;
    eveOffEl.hidden = false;
    streamSettingsEl.hidden = false;
    lastMirror = payload;
    // The registration path (#321): resolved by Python -- the installed
    // location is not one a user could guess. Hidden when the resolution
    // failed so the ceremony never points at a line that is not there.
    exePathEl.textContent = payload.exe_path || '';
    exePathEl.hidden = !payload.exe_path;
    toggleBtn.hidden = false;
    if (payload.state === 'running') {
      stateEl.textContent = 'Running';
      toggleBtn.textContent = 'Stop mirror';
    } else if (payload.state === 'given-up') {
      stateEl.textContent = 'Stopped (restarts paused)';
      toggleBtn.textContent = 'Start mirror';
    } else if (payload.state === 'off') {
      stateEl.textContent = 'Off';
      toggleBtn.textContent = 'Start mirror';
    } else {
      stateEl.textContent = 'Not running';
      toggleBtn.textContent = 'Start mirror';
    }
    errorEl.textContent = payload.error || '';
  }

  function applyChord() {
    if (!capturing) {
      chordBtn.textContent = chordDisplay || 'Not set';
    }
    // Round 3, B2's disabled rule, the bookmarks rows' version: Clear is
    // enabled exactly when there is something to clear.
    WM.setEnabled(chordClear, !!chordDisplay);
    // The collision line is true of every chord -- Wingman presses the
    // chord into whatever window is focused, EVE included -- so it shows
    // whenever a chord is recorded, not only in the second after a
    // capture. Warn, never prevent (the spec's failure-modes line).
    collisionEl.hidden = !chordDisplay;
  }

  function renderChord(payload) {
    if (!payload || !payload.available) {
      // No mirror process in this installation means no combat auto-start
      // either: unavailable hides the section's controls with the mirror
      // row's, not just the toggle. #321 extends that to the section's
      // words too -- the header, the enable hint and the ceremony text
      // are instructions for a feature that cannot run.
      chordBtn.hidden = true;
      chordClear.hidden = true;
      collisionEl.hidden = true;
      sendableEl.hidden = true;
      groupEl.hidden = true;
      enableHintEl.hidden = true;
      chordCeremonyEl.hidden = true;
      diagnosticEl.hidden = true;
      quietInput.parentNode.hidden = true;
      couplingStateEl.parentNode.hidden = true;
      latchedEl.parentNode.hidden = true;
      lastFiredEl.parentNode.hidden = true;
      showMsg('');
      return;
    }
    chordBtn.hidden = false;
    chordClear.hidden = false;
    groupEl.hidden = false;
    enableHintEl.hidden = false;
    chordCeremonyEl.hidden = false;
    diagnosticEl.hidden = false;
    chordDisplay = payload.chord_display || '';
    applyChord();
    showMsg('');
  }

  // The armed row (#320): the user's visibility into a background
  // key-presser. It says armed, never live -- nothing Python-side knows
  // whether Discord is actually streaming, and this row must never claim
  // to. Tick-pushed like the mirror rows: it carries no draft except the
  // quiet field's, which the draft rule below protects.
  function renderCoupling(payload) {
    if (!payload) return;
    var lines = {
      'inert': 'Off',
      'standby': 'Standing by \u2014 start the mirror to arm',
      'armed': 'Armed',
      'held': 'Holding'
    };
    couplingStateEl.textContent = lines[payload.state] || 'Checking\u2026';
    var latched = payload.latched || [];
    if (payload.state === 'held' && latched.length) {
      latchedEl.textContent = 'Episode running for ' + latched.join(', ') +
        ' \u2014 ' + formatRemaining(payload.latched_remaining_s) + ' left';
      latchedEl.hidden = false;
    } else {
      latchedEl.textContent = '';
      latchedEl.hidden = true;
    }
    if (payload.last_fired_character) {
      lastFiredEl.textContent = 'Last fired ' + payload.last_fired_display +
        ' \u2014 ' + payload.last_fired_character;
      lastFiredEl.hidden = false;
    } else if (payload.last_fired_action === 'stop') {
      // The auto-stop press (#320 field finding): the fight went quiet
      // and Wingman pressed the toggle closed. A press report, not a
      // claim that Discord obeyed -- same rule as every row here.
      lastFiredEl.textContent = 'Last fired ' + payload.last_fired_display +
        ' \u2014 stop press (fight quiet)';
      lastFiredEl.hidden = false;
    } else {
      lastFiredEl.textContent = '';
      lastFiredEl.hidden = true;
    }
    // A chord recorded but untypeable would sit armed and never fire --
    // the exact failure this card exists to make visible. Anything but
    // inert without a sendable chord gets the line, display or not.
    sendableEl.hidden = !(payload.state !== 'inert' && !payload.chord_sendable);
    if (!quietEditing) {
      quietInput.value = payload.quiet_s;
    }
  }

  function formatRemaining(seconds) {
    var whole = Math.max(0, Math.floor(seconds || 0));
    var m = Math.floor(whole / 60);
    var s = whole % 60;
    return m + ':' + (s < 10 ? '0' + s : s);
  }

  function commitQuiet() {
    // Enter-commit only (the settings rule for free text): a draft is
    // what the user typed and it persists exactly when they say so.
    if (quietDraft === null) return;
    WM.send('stream_quiet_set', quietDraft).then(function (result) {
      if (!result) return;
      if (result.applied === false) { showMsg(result.error); return; }
      quietDraft = null;
      // The clamped value, echoed: what the field shows is what is stored.
      quietInput.value = result.quiet_s;
      showMsg('');
    });
  }

  var quietEditing = false;
  quietInput.addEventListener('focus', function () { quietEditing = true; });
  quietInput.addEventListener('blur', function () { quietEditing = false; });
  quietInput.addEventListener('input', function () {
    quietDraft = quietInput.value;
  });
  quietInput.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    commitQuiet();
  });

  function refresh() {
    WM.send('stream_mirror_state').then(function (payload) {
      renderMirror(payload);
      renderChord(payload);
    });
    WM.send('stream_coupling_state').then(function (payload) {
      // Re-entry is a fresh read: a draft typed before leaving dies here,
      // the same rule the chord row's msg line follows on re-render.
      quietDraft = null;
      renderCoupling(payload);
    });
  }

  function showMsg(text) {
    // The row's one message line: a degraded capture's position warning
    // (ADR 0002) or a refused write. A fresh capture replaces it and
    // entering the section clears it -- nothing stale survives a re-render.
    msgEl.textContent = text || '';
    msgEl.hidden = !text;
  }

  function endCapture() {
    if (!capturing) return;
    capturing = false;
    chordBtn.classList.remove('capturing');
    // Restore from the last committed display, not a bridge read: Escape
    // must not cost a round trip, and a commit that raced the disarm
    // arrives to capturing === false and is dropped below.
    chordBtn.textContent = chordDisplay || 'Not set';
  }

  // The mirror toggle is the card's one writer of mirror_on: start
  // persists the sticky ask, stop clears it. Which half it sends comes
  // from the last rendered state, not the button label -- same data, but
  // parsing copy couples the send to a wording change. A refused toggle
  // writes the error row and leaves the state to the tick; a taken one
  // re-reads, so the row never shows a state this click invented. The
  // pending guard collapses double-clicks into one ask -- pywebview runs
  // each bridge call on its own thread, so a second click would interleave
  // a stop into the start's round trip.
  //
  // This listener was MISSING until the #321 build test: the button
  // rendered and re-labelled but nothing sent anything, and no lexical
  // guard can see a listener that was never attached -- which is why the
  // streaming page runtime exists to click the real module.
  var mirrorPending = false;
  toggleBtn.addEventListener('click', function () {
    if (!visible || mirrorPending || !lastMirror) return;
    mirrorPending = true;
    var stopping = lastMirror.state === 'running';
    WM.send(stopping ? 'stream_mirror_stop' : 'stream_mirror_start').then(
      function (result) {
        mirrorPending = false;
        if (!result) return;
        if (result.ok === false) {
          errorEl.textContent = result.error || '';
          return;
        }
        WM.send('stream_mirror_state').then(renderMirror);
      }
    );
  });

  chordBtn.addEventListener('click', function () {
    if (!visible || capturing) return;
    capturing = true;
    chordBtn.textContent = 'Press a key…';
    chordBtn.classList.add('capturing');
    showMsg('');
  });

  chordClear.addEventListener('click', function () {
    // Any other control acting on the row cancels the capture (the
    // bookmarks rule): the keydown handler's staleness check alone cannot
    // catch this, so a later keystroke would silently re-store a chord
    // this click just cleared.
    endCapture();
    WM.send('stream_chord_set', '').then(function (result) {
      if (!result) return;
      if (result.ok === false) { showMsg(result.error); return; }
      chordDisplay = result.chord_display || '';
      applyChord();
      showMsg('');
    });
  });

  // Page-level capture, the Bookmarks pattern -- #319's chosen fork. The
  // document-level keydown preventDefault()s EVERY key while armed, so a
  // key that reaches the page is resolved through the one ADR 0002 seam
  // (capture_bind) and stored by stream_chord_set; Escape cancels. If
  // real Discord proves to swallow or double-fire the keydown before it
  // gets here (its bind is global), the fallback is the previews'
  // native-armed capture path -- set_bind_capture arm-then-prompt, result
  // pushed back as onPreviewBindCaptured -- and this handler moves to
  // that seam; the smoke checklist's chord step is the test that decides.
  document.addEventListener('keydown', function (event) {
    if (!capturing) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.key === 'Escape') { endCapture(); return; }
    // Held synchronously: by the time the bridge resolves, the user may
    // have pressed Escape or left the section. Reading `capturing` inside
    // the callback is what makes a raced result land on nobody.
    WM.send('capture_bind', {
      ctrl: event.ctrlKey, alt: event.altKey,
      shift: event.shiftKey, meta: event.metaKey, code: event.code
    }).then(function (result) {
      // A modifier-only press is not an error the user needs told about --
      // they are still reaching for the combination; stay armed. A null
      // result (bridge failure) also stays armed rather than silently
      // disarming, so the user can simply press another key or Escape.
      if (!result || result.error === 'modifier-only') return;
      // A result for a capture the user has since abandoned is not theirs
      // to apply.
      if (!capturing) return;
      endCapture();
      if (result.error) return;
      WM.send('stream_chord_set', result.ahk).then(function (stored) {
        if (!stored) return;
        if (stored.ok === false) { showMsg(stored.error); return; }
        chordDisplay = stored.chord_display || '';
        applyChord();
        // ADR 0002: a key with no single produced character (dead key,
        // multi-character result) still stores by position and says so
        // here, one line, until the next capture or re-entry replaces it.
        showMsg(result.warn ? WM.positionWarn(result.warn) : '');
      });
    });
  }, true);

  WM.handle('onMirrorStatus', function (payload) {
    // The tick pushes for every route; render only while visible, the
    // alerts.js rule -- a stale handler must not write a hidden card.
    // Mirror rows only: the chord row renders on entry and on its own
    // commits, never under a tick that would fight an armed capture.
    if (visible) { renderMirror(payload); }
    // An availability flip never happens in a live session (the exe
    // resolution is a launch-time fact), but if a push ever says
    // unavailable, the Combat auto-start words go with the mirror rows --
    // instructions for a feature that cannot run. Hiding only: the chord
    // controls stay entry/commit-rendered, so nothing here can fight a
    // capture. (#321 field test: entry hid them, a push did not.)
    if (visible && (!payload || !payload.available)) {
      groupEl.hidden = true;
      enableHintEl.hidden = true;
      chordCeremonyEl.hidden = true;
      diagnosticEl.hidden = true;
    }
  });

  WM.handle('onStreamCouplingState', function (payload) {
    // Same visibility rule. The armed row carries no capture state, so
    // the tick may write it; the quiet field's draft is protected inside
    // renderCoupling, not by suppressing the push.
    if (visible) { renderCoupling(payload); }
  });

  WM.handle('onStreamCouplingFired', function (payload) {
    // The one-chord-per-fight event -- now both directions: start when
    // the fight opens the stream, stop when the quiet period closes it.
    // The state push right behind it carries the same last-fired line;
    // this marks the moment even if a tick somehow ate the state diff
    // in between.
    if (!visible || !payload) { return; }
    if (payload.action === 'stop') {
      lastFiredEl.textContent = 'Last fired ' + (payload.display || '') +
        ' \u2014 stop press (fight quiet)';
      lastFiredEl.hidden = false;
      return;
    }
    if (payload.character) {
      lastFiredEl.textContent = 'Last fired ' + (payload.display || '') +
        ' \u2014 ' + payload.character;
      lastFiredEl.hidden = false;
    }
  });

  document.addEventListener('wm:section', function (ev) {
    if (ev.detail === 'streaming') {
      if (!visible) { visible = true; }
      refresh();
    } else {
      visible = false;
      // Leaving is load-bearing (wm:section('') fires on route leave too,
      // so one listener covers both): an armed capture left running would
      // preventDefault() every key app-wide, Tab included -- swallowing a
      // path or a webhook being typed in another section.
      endCapture();
    }
  });
}());
