/* FlyGD Wingman — the floating sig bar's page script.
 *
 * Deliberately NOT app.js: that file is the main page's shell (routes,
 * dialog layer, WM bus) and none of it exists here. This page needs
 * exactly three things — a wait for the bridge, the onEveStatus render,
 * and the style/fit round-trip — so it registers its two handlers as
 * plain globals. Api._push's script already guards with `window.<handler>
 * &&`, so a push landing before this file ran is dropped, not thrown; the
 * next 3s poll tick re-sends it, which is why nothing here re-requests
 * the status.
 */
(function () {
  'use strict';

  var ready = new Promise(function (resolve) {
    if (window.pywebview && window.pywebview.api) { resolve(); return; }
    window.addEventListener('pywebviewready', function () { resolve(); },
                            { once: true });
  });

  function send(method) {
    var args = Array.prototype.slice.call(arguments, 1);
    return ready.then(function () {
      var api = window.pywebview && window.pywebview.api;
      var fn = api && api[method];
      if (typeof fn !== 'function') return null;
      return fn.apply(api, args);
    }).catch(function (err) {
      // Same rule as WM.send: a bridge failure must never take the page
      // down. The bar would stay stale with no console to say so.
      console.error('bridge: ' + method + ' failed', err);
      return null;
    });
  }

  // ---- fit -----------------------------------------------------------
  // pywebview's resize takes the CLIENT size in logical units; the page
  // measures the laid-out content, which is exactly that. Sent on EVERY
  // render with no dedup: an early fit can land before the native handle
  // exists and be lost, and a "nothing changed" guard would then suppress
  // every retry forever -- a window frozen at its opening size. A resize
  // per 3s poll tick costs nothing.
  function fit() {
    var w = document.body.scrollWidth;
    var h = document.body.scrollHeight;
    send('fit_sig_bar', w, h);
  }

  // ---- handlers (globals, called by Api._push) ------------------------
  // The prime lifecycle dot (#353): this page shares no code with the
  // main page, so it carries its own copy of the word->severity map and
  // the ~10s consumed pulse (page state; Python schedules nothing).
  // No word -> NO dot (hidden): the issue offers "absent/grey when
  // nothing to report" and absent is what keeps the bar's measured
  // width honest -- it moves by a fixed 13px only while a prime is in
  // flight. "Then grey" in the spec's consumed transition is the
  // visible-unlit state after the pulse, until the word goes away. The
  // pulse's episode key is the prime's EVENT id: the engine keeps its
  // standing prime until the next Set Root, so Python keeps answering
  // 'consumed' for the same event on every tick -- keying by event is
  // what arms the pulse once and rests grey after, instead of pulsing
  // forever.
  var PRIME_PULSE_MS = 10000;
  var primePulseTimer = null;
  var primePulseEvent = null;

  function renderPrimeDot(primeState, primeEvent, live) {
    var el = document.getElementById('bar-prime-dot');
    var visible = live && !!primeState;
    el.hidden = !visible;
    if (!visible) {
      if (primePulseEvent !== null) {
        if (primePulseTimer !== null) clearTimeout(primePulseTimer);
        primePulseTimer = null;
        primePulseEvent = null;
        el.classList.remove('pulse');
      }
      el.classList.remove('ok');
      el.classList.remove('warn');
      el.classList.remove('err');
      return;
    }
    el.classList.toggle('ok', primeState === 'staged' || primeState === 'consumed');
    el.classList.toggle('warn', primeState === 'staging');
    el.classList.toggle('err', primeState === 'failed');
    if (primeState !== 'consumed') {
      if (primePulseEvent !== null) {
        if (primePulseTimer !== null) clearTimeout(primePulseTimer);
        primePulseTimer = null;
        primePulseEvent = null;
        el.classList.remove('pulse');
      }
      return;
    }
    if (primePulseEvent === primeEvent && primePulseTimer === null) {
      // This event's pulse already ran its ~10s: rest grey. The dot
      // stays visible and unlit until the word itself goes away.
      el.classList.remove('pulse');
      el.classList.remove('ok');
      el.classList.remove('warn');
      el.classList.remove('err');
      return;
    }
    if (primePulseEvent !== primeEvent) {
      el.classList.remove('warn');
      el.classList.remove('err');
      el.classList.add('pulse');
      primePulseEvent = primeEvent;
      if (primePulseTimer !== null) clearTimeout(primePulseTimer);
      primePulseTimer = setTimeout(function () {
        primePulseTimer = null;
        // The pulse ends in grey -- consumed and gone.
        el.classList.remove('pulse');
        el.classList.remove('ok');
      }, PRIME_PULSE_MS);
    }
  }

  window.onEveStatus = function (payload) {
    payload = payload || {};
    // Values are shown ONLY while running; every other state renders the
    // same em-dash placeholders the markup opens with, dressed in the
    // degraded (muted) tokens the main strip uses for the same meaning.
    // Unlike the main strip, the row is never hidden: a floating pill
    // that vanishes when the engine stops is indistinguishable from a
    // bar that failed to open.
    var live = payload.state === 'running';
    document.getElementById('bar-sig').textContent =
      live && payload.sig ? payload.sig : '\u2014';
    document.getElementById('bar-root').textContent =
      live && payload.root ? payload.root : '\u2014';
    document.getElementById('bar-next').textContent =
      live && payload.next_num
        ? payload.next_num + ' / ' + (payload.next_alpha || '\u2014') : '\u2014';
    document.getElementById('sigbar-stat').classList.toggle('degraded', !live);
    renderPrimeDot(payload.prime_state,
                   payload.prime && payload.prime.event, live);
    fit();
  };

  // ---- drag position --------------------------------------------------
  // Persisted from HERE, not from Python's `moved` event: a drag is dozens
  // of WM_MOVEs a second, and every one of them spawning a Python handler
  // thread against the UI thread is the race that hung the app (see the
  // block comment at the bottom of ui/sigbar.py). mouseup fires once per
  // drag; screenX/screenY are the window's screen position in CSS pixels
  // -- the same logical units pywebview's move/geometry use.
  document.addEventListener('mouseup', function () {
    send('save_sig_bar_pos', window.screenX, window.screenY);
  });

  // ---- boot ----------------------------------------------------------
  // Nothing to pull at load: the background is fixed in the stylesheet
  // and the first onEveStatus push follows the toggle (or the 3s poll if
  // the bar was restored at launch). The placeholders are already on
  // screen either way.
  fit();

  // The Inter face is font-display:block, but the FIRST fit can still run
  // before the font resolves; a fallback-metrics width would leave a
  // window the wrong width until the next tick. Re-fit once fonts settle,
  // and once more shortly after boot in case the first fit landed before
  // the native handle existed.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(fit);
  }
  setTimeout(fit, 500);
})();
