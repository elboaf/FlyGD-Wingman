/* FlyGD Wingman — the Fittings route.
 *
 * MINIMAL SHELL (SDD task 6 of
 * docs/superpowers/plans/2026-09-03-character-fittings.md). This file is
 * route entry, the EVE gate, and a safe unavailable-state render -- not
 * the fitting workspace. `Api.fittings_state` is a stub today (ruling
 * recorded in the SDD ledger: Task 8 wires a private `_fittings` slot,
 * Task 9 replaces the stub with real controller delegation and is where
 * the curation UI this file will eventually hold gets built). Adding the
 * route now, ahead of that controller, is deliberate: it is what let
 * Task 6 measure the fourth destination's title-bar geometry before any
 * of that work started.
 *
 * Follows the same enter/leave contract every other route in this app
 * follows (DESIGN.md; alerts.js and formations.js carry the same shape on
 * their own `wm:route` listeners) -- entering asks Python for state
 * exactly once, the same rule app.js:139-148 states for rows and
 * settings, and restated by skills.js's own `asked` guard. Nothing here
 * holds a poll or an armed capture yet, so the leave branch is a no-op
 * today; it is the hook Task 9's cleanup attaches to, not a placeholder
 * to delete once real content lands.
 */
(function () {
  'use strict';
  var WM = window.WM;

  var asked = false;

  function render(payload) {
    var host = WM.el('fittings-empty');
    // A null/undefined payload is a bridge failure (app.js's own note on
    // WM.send), not an answer with nothing to say -- the caller resets
    // `asked` in that case so the next entry retries rather than leaving
    // the route silently blank forever. Either way the text is the same:
    // there is nothing yet to distinguish "the stub answered" from "the
    // request failed" for a user who cannot fix either from here.
    var warnings = (payload && payload.warnings && payload.warnings.length)
      ? payload.warnings
      : ['The EVE fitting library is not available yet.'];
    host.textContent = warnings.join(' ');
  }

  document.addEventListener('wm:route', function (event) {
    if (event.detail !== 'fittings') {
      // Nothing armed on this route yet -- see the file header. Kept as
      // an explicit early return, matching alerts.js/formations.js,
      // rather than folded into the block below, so the seam a future
      // poll or capture disarms from already exists.
      return;
    }
    // Asked on FIRST entry only, same reasoning as skills.js:149-160: a
    // subsystem that costs nothing until opened must not re-ask on every
    // later visit.
    if (asked) return;
    asked = true;
    WM.send('fittings_state').then(function (payload) {
      if (!payload) asked = false;
      render(payload);
    });
  });
}());
