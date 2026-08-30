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

  // ---- style ---------------------------------------------------------
  // Writes the stored bg color/opacity as CSS channels. The color is
  // DATA from settings (validated to #rrggbb in settings.py), not a
  // decision made here; parse it into the triplet rgb()/the alpha token
  // form the <style> block consumes. A bad value falls through to the
  // defaults the stylesheet already declares.
  function applyStyle(section) {
    var hex = /^#([0-9a-fA-F]{6})$/.exec(section.bg_color);
    if (hex) {
      var n = parseInt(hex[1], 16);
      document.documentElement.style.setProperty(
        '--sigbar-bg', ((n >> 16) & 255) + ' ' + ((n >> 8) & 255) + ' ' + (n & 255));
    }
    var opacity = section.opacity;
    if (typeof opacity === 'number' && opacity >= 0 && opacity <= 100) {
      document.documentElement.style.setProperty(
        '--sigbar-alpha', String(opacity / 100));
    }
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
    fit();
  };

  window.onSigBarState = function (payload) {
    applyStyle(payload || {});
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
  ready.then(function () {
    // Pulled once, not pushed: style is configuration, not a live event,
    // and the push that follows a change only helps a page that already
    // knows its starting look.
    return send('sig_bar_settings');
  }).then(function (section) {
    if (section) applyStyle(section);
    fit();
  });

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
