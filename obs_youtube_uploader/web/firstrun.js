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
    // set_folder, the same endpoint Settings uses. There used to be two:
    // set_recording_dir could only CREATE a watcher and save_settings could
    // only REPOINT one, so whichever was called in the wrong state left the
    // folder persisted with nothing polling it. One endpoint handles both.
    //
    // WM.send resolves to null on a bridge failure, and a refusal is a dict
    // with applied:false, so both have to be checked before navigating --
    // dropping the user into an empty list with no explanation is exactly
    // what this guard prevents.
    // Sent BEFORE the folder, and its result deliberately ignored: this is
    // cosmetic, and a failure here must not block the one thing first run
    // exists to do. The guard in set_show_eve_tools cannot refuse on a
    // fresh install anyway -- both EVE features default to off.
    WM.send('set_show_eve_tools', WM.el('firstrun-eve').checked);
    WM.send('set_folder', 'recording', chosen).then(function (res) {
      if (!res) { return; }
      if (!res.applied) {
        // No inline slot on this screen, so the note under the field
        // carries it. It already explains Detect; a real error outranks
        // that until the user tries again.
        WM.el('firstrun-note').textContent = res.error;
        return;
      }
      WM.route('main');
    });
  });

  WM.handle('onFirstRun', function () {
    setChosen('');
    WM.route('firstrun');
  });
}());
