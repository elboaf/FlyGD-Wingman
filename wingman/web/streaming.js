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
  var chordClear = WM.el('chord-clear');
  var collisionEl = WM.el('chord-collision');
  var msgEl = WM.el('chord-msg');
  var visible = false;
  var capturing = false;
  var chordDisplay = '';

  function renderMirror(payload) {
    if (!payload || !payload.available) {
      stateEl.textContent = 'Not available in this installation';
      toggleBtn.hidden = true;
      errorEl.textContent = '';
      return;
    }
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
      // row's, not just the toggle.
      chordBtn.hidden = true;
      chordClear.hidden = true;
      collisionEl.hidden = true;
      showMsg('');
      return;
    }
    chordBtn.hidden = false;
    chordClear.hidden = false;
    chordDisplay = payload.chord_display || '';
    applyChord();
    showMsg('');
  }

  function refresh() {
    WM.send('stream_mirror_state').then(function (payload) {
      renderMirror(payload);
      renderChord(payload);
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
