/* The first-run recording-folder screen.
 *
 * A deliberate behaviour change, not a port: pywebview's
 * create_file_dialog is a method on a window, so the pre-window OS dialog
 * the Tk build showed cannot exist here. Python signals this state by
 * pushing onFirstRun; the page cannot infer it, because an empty list and
 * an unconfigured folder look identical from here.
 */
(function () {
  'use strict';
  var WM = window.WM;

  var chosen = '';

  function setChosen(path) {
    chosen = path || '';
    WM.el('f-firstrun-dir').value = chosen;
    WM.el('btn-firstrun-continue').disabled = !chosen;
  }

  WM.el('btn-firstrun-browse').addEventListener('click', function () {
    WM.send('pick_folder', 'recording').then(setChosen);
  });

  WM.el('btn-firstrun-detect').addEventListener('click', function () {
    WM.send('detect_folder', 'recording', chosen).then(function (path) {
      if (path) setChosen(path);
    });
  });

  // Typing is allowed as well as picking: a user who knows the path should
  // not have to walk a tree to it.
  WM.el('f-firstrun-dir').addEventListener('input', function (ev) {
    chosen = ev.target.value.trim();
    WM.el('btn-firstrun-continue').disabled = !chosen;
  });

  WM.el('btn-firstrun-continue').addEventListener('click', function () {
    // Python validates, persists, starts the watcher, and pushes onRows.
    // It returns false if the folder is not usable, in which case we stay
    // put rather than dropping the user into an empty list.
    WM.send('set_recording_dir', chosen).then(function (ok) {
      if (ok !== false) WM.route('main');
    });
  });

  WM.handle('onFirstRun', function () {
    setChosen('');
    WM.route('firstrun');
  });
}());
