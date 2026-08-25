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

  // ---- the note ---------------------------------------------------------
  // #firstrun-note is one element doing three jobs: the standing
  // explanation of Detect, a detection that found nothing, and a folder
  // Python refused. There was no rule about which wins, and the refusal
  // path simply overwrote the element -- so a user who mistyped a path,
  // read the error and then wanted the Detect explanation back had lost it
  // for the session.
  //
  // The rule: a message about the action the user just took outranks the
  // standing explanation, and the standing explanation comes back the
  // moment they do something that could change the outcome it was about --
  // typing in the field, or a Browse or Detect that succeeded.
  //
  // Read out of the DOM rather than retyped here. DESIGN.md's "State that
  // must not be retyped" is the whole reason: a second copy of a sentence
  // is a sentence that drifts.
  var standing = WM.el('firstrun-note').textContent.replace(/\s+/g, ' ').trim();

  function note(text, tone) {
    var el = WM.el('firstrun-note');
    el.textContent = text || standing;
    // The same two tokens the status strip and .field-msg use, so one
    // severity reads the same everywhere in the app.
    el.className = 'firstrun-note' + (text && tone ? ' ' + tone : '');
  }

  function setChosen(path) {
    chosen = path || '';
    WM.el('f-firstrun-dir').value = chosen;
    WM.el('btn-firstrun-continue').disabled = !chosen;
  }

  WM.el('btn-firstrun-browse').addEventListener('click', function () {
    WM.send('pick_folder', 'recording').then(function (path) {
      // Api.pick_folder returns "" on cancel, and this used to hand that
      // straight to setChosen -- so cancelling a second Browse wiped the
      // path the first one found and re-disabled Continue. Settings'
      // applyFolder has always guarded this ("a cancelled dialog is also a
      // valid result"); this screen did not.
      if (!path) { return; }
      setChosen(path);
      note('');
    });
  });

  WM.el('btn-firstrun-detect').addEventListener('click', function () {
    WM.send('detect_folder', 'recording', chosen).then(function (path) {
      if (path) { setChosen(path); note(''); return; }
      // A detection that finds nothing used to do nothing at all: the
      // field stayed empty, the note still explained Detect, and Continue
      // stayed disabled, so a failed detection and a dead button were
      // indistinguishable -- on the one screen with no way out. settings.js
      // has said so all along, in a sibling module twenty lines away.
      note('Detect could not find a recording folder in OBS’s '
         + 'configuration — use Browse to pick it yourself.', 'warn');
    });
  });

  // Typing is allowed as well as picking: a user who knows the path should
  // not have to walk a tree to it.
  WM.el('f-firstrun-dir').addEventListener('input', function (ev) {
    chosen = ev.target.value.trim();
    WM.el('btn-firstrun-continue').disabled = !chosen;
    // Whatever the last message was about, they are now changing the thing
    // it was about. This is the restore half of the precedence rule.
    note('');
  });

  // ---- leaving, either way ---------------------------------------------
  // Both exits from this screen end in the same three-outcome envelope
  // every commit in the app returns, and both hit the awkward one the same
  // way. DESIGN.md's treatment for "applied but not persisted" is to leave
  // the control where the user put it and warn that it will not survive a
  // restart -- but these two controls exist to LEAVE, and routing away
  // takes the only sentence that says the question is coming back with it.
  //
  // So the warning gets one press and the next press goes anyway. Shared
  // between the two buttons rather than one flag each: it records that the
  // user has read it, which is true whichever button they read it from.
  var pressedThrough = false;

  function leave(res, unsaved) {
    // WM.send resolves to null on a bridge failure rather than rejecting
    // (app.js), and a refusal is a dict with applied:false, so both have to
    // be checked before navigating -- dropping the user into an empty list
    // with no explanation is exactly what this guard prevents.
    if (!res) {
      note('Could not reach the app. Nothing was changed.', 'err');
      return;
    }
    if (!res.applied) {
      // The fallback matters more here than the message it replaces: a
      // blank note silently reverts to the standing explanation, which on
      // this screen is indistinguishable from the button doing nothing.
      note(res.error || 'That was not accepted.', 'err');
      return;
    }
    if (!res.persisted && !pressedThrough) {
      pressedThrough = true;
      note(unsaved, 'warn');
      return;
    }
    WM.route('main');
  }

  WM.el('btn-firstrun-continue').addEventListener('click', function () {
    // set_folder, the same endpoint Settings uses. There used to be two:
    // set_recording_dir could only CREATE a watcher and save_settings could
    // only REPOINT one, so whichever was called in the wrong state left the
    // folder persisted with nothing polling it. One endpoint handles both.
    WM.send('set_folder', 'recording', chosen).then(function (res) {
      leave(res, 'Wingman is watching that folder now, but it could not '
               + 'be written to settings — it will ask again next launch. '
               + 'Press Continue again to carry on.');
    });
  });

  // ---- leaving without a folder ----------------------------------------
  // PRODUCT.md: "It must not require the EVE tools to upload a video, or a
  // Google account to use the EVE tools. The two halves must stay
  // independent." A recording folder configures the UPLOADER half, and
  // this was the only screen in the app with no exit -- so a wormhole
  // multiboxer who installed Wingman for previews and bookmark keybinds
  // was stopped at a mandatory OBS folder.
  //
  // Api.skip_first_run persists the dismissal (in a key of its own, not a
  // sentinel recording_dir) so the screen does not simply return on the
  // next launch. main already renders an empty state for a skipped
  // install: list_rows pushes an empty list rather than returning silently.
  WM.el('btn-firstrun-skip').addEventListener('click', function () {
    WM.send('skip_first_run').then(function (res) {
      leave(res, 'Skipped for now, but it could not be written to settings '
               + '— Wingman will ask again next launch. Press again to '
               + 'carry on.');
    });
  });

  WM.handle('onFirstRun', function () {
    setChosen('');
    note('');
    pressedThrough = false;
    WM.route('firstrun');
  });
}());
