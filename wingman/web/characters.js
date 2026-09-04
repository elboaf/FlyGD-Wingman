/* The Characters Settings section shell.
 *
 * Task 7 owns only the section lifecycle and inert surface. Behaviour lands
 * later; for now this file proves the section can enter and leave cleanly
 * inside Settings without adding a second route or any duplicate globals.
 */
(function () {
  'use strict';

  var WM = window.WM;
  var section = WM && WM.el && WM.el('section-characters');
  if (!section) { return; }

  var live = WM.el('characters-live');
  var roster = WM.el('characters-roster');
  var filter = WM.el('characters-filter');
  var filterClear = WM.el('characters-filter-clear');
  var menu = WM.el('characters-menu');
  var forget = WM.el('characters-menu-forget');
  if (!live || !roster || !filter || !filterClear || !menu || !forget) {
    return;
  }

  var active = false;

  function enterSection() {
    active = true;
    menu.open = false;
  }

  function leaveSection() {
    if (!active) { return; }
    active = false;
    menu.open = false;
  }

  document.addEventListener('wm:section', function (ev) {
    if (ev.detail === 'characters') {
      enterSection();
      return;
    }
    leaveSection();
  });
})();
