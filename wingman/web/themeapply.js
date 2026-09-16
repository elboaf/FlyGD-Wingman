// Theme applier: turns a bridge theme payload into CSS custom properties.
// Deliberately app.js-free — the sig and fleet bar pages are separate
// documents that do not load the shell (see their header notes), and all
// three render the same :root tokens. Every page that links style.css
// loads this file and gets window.onTheme; _push's `handler &&` guard
// makes the main page's registration order irrelevant.
(function () {
  'use strict';

  function apply(payload) {
    if (!payload || !payload.effective) return;
    var root = document.documentElement;
    var roles = payload.effective;
    Object.keys(roles).forEach(function (role) {
      root.style.setProperty(role, roles[role]);
    });
    root.setAttribute('data-theme', payload.preset || '');
    try {
      // On document, matching the page's other cross-module events
      // (wm:settings, wm:section): listeners register on document.
      document.dispatchEvent(new CustomEvent('wm:theme', { detail: payload }));
    } catch (err) {
      // CustomEvent is unavailable in no browser object anywhere.
    }
  }

  window.WingmanTheme = { apply: apply };
})();
