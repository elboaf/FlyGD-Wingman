// The Streaming section (#317): one card, the mirror as its subject.
//
// A READ on section entry, not a launch push, for the reason alerts.js
// documents: the supervisor exists before the window, so a state
// discovered at launch would be pushed into nothing. The poll tick's
// onMirrorStatus keeps the row honest while the section is visible.
(function () {
  var stateEl = WM.el('mirror-state');
  if (!stateEl) { return; }

  var toggleBtn = WM.el('mirror-toggle');
  var errorEl = WM.el('mirror-error');
  var visible = false;

  function render(payload) {
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

  function refresh() {
    WM.send('stream_mirror_state').then(render);
  }

  toggleBtn.addEventListener('click', function () {
    var wantStart = toggleBtn.textContent === 'Start mirror';
    var method = wantStart ? 'stream_mirror_start' : 'stream_mirror_stop';
    WM.send(method).then(function (result) {
      if (result && result.error) { errorEl.textContent = result.error; }
      refresh();
    });
  });

  WM.handle('onMirrorStatus', function (payload) {
    // The tick pushes for every route; render only while visible, the
    // alerts.js rule -- a stale handler must not write a hidden card.
    if (visible) { render(payload); }
  });

  document.addEventListener('wm:section', function (ev) {
    if (ev.detail === 'streaming') {
      if (!visible) { visible = true; }
      refresh();
    } else {
      visible = false;
    }
  });
}());
