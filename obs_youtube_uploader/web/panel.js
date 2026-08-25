/* Upload panel, status strip, and the modal dialog layer.
 *
 * The panel owns no upload logic: it collects the fields, hands them to
 * start_upload, and renders what comes back. Every guard, warning, and
 * confirmation is still composed in Python (start_upload,
 * delete_selected, format_upload_confirm) and merely rendered here — a
 * page-side confirmation would be a second copy of that text with nothing
 * keeping the two in step.
 */
(function () {
  'use strict';
  var WM = window.WM;

  // Privacy and category are NOT held here and are NOT sent. They are
  // settings, and start_upload reads them from Python's own state — the
  // page cannot hold a stale copy of a value it never holds.

  // ---- selection-dependent copy ---------------------------------------
  // Asked of Python rather than recomputed here. Both strings are pure,
  // tested functions whose decisions are subtle enough that a JavaScript
  // twin would drift within a release: the summary's "+" appears only when
  // a probe is outstanding and never on size, and the title hint discloses
  // that build_body numbers a batch -- added in 2.2.0 after users got ten
  // differently-named public videos. The round trip is in-process and
  // fires on a human click, so its cost is invisible.
  var panelSeq = 0;

  function refreshPanelText() {
    var seq = ++panelSeq;
    WM.send('panel_text', WM.list.selectedIds(), WM.el('f-stitch').checked)
      .then(function (text) {
        // Clicks can outrun replies; only the newest answer may paint, or a
        // slow earlier reply overwrites a newer count.
        if (seq !== panelSeq || !text) return;
        WM.el('selection-summary').textContent = text.summary;
        WM.el('lab-title').textContent = text.title_hint;
      });
  }
  document.addEventListener('wm:selection', refreshPanelText);
  // Stitching collapses a batch into ONE video, so the numbering
  // disclosure must appear and disappear with this checkbox too.
  WM.el('f-stitch').addEventListener('change', refreshPanelText);

  // ---- what can act, and what cannot -----------------------------------
  // X1 execution, through S1's WM.setEnabled. The rule in its comment is
  // that a control is inert when the app ALREADY KNOWS the action cannot
  // be carried out from the state it is holding -- not when it might fail
  // once attempted -- and that nothing may disable the only route back out
  // of the state that disabled it. Both apply here:
  //
  //   Upload    needs at least one selected recording (Uploader 1). It was
  //             full-strength accent with a glow and nothing to do, while
  //             the blocker whispered from the foot of the card above it.
  //   Stitch    is meaningless below two selected. Disabled, NOT hidden --
  //             see the note beside it in index.html.
  //   the list  is not disabled by any of this: selecting a row is the way
  //             out of every state above, so it must stay live.
  //
  // Nothing here disables Delete: it acts on a selection too, but it lives
  // in the list footer beside Select all / Select none, and list.js owns
  // it for the same reason it owns those.
  function refreshEnabled() {
    var selected = WM.list.selectedIds().length;
    var rows = WM.list.rowCount();

    // Uploader 13. The panel used to be identical with an empty folder --
    // live fields, accent Upload, nothing acknowledging there was nothing
    // to act on -- so the empty and full states read as the same product
    // in the wrong direction. An empty folder is a fact about the folder,
    // so it is stated once and the note is the whole of the treatment.
    //
    // Title and Description stay LIVE, deliberately. S1's rule disables a
    // control when the action cannot be carried out, and typing a title is
    // an action that can -- the same reading that keeps the Previews
    // keybinds live under Settings 1 (recording a keybind for later is
    // still recording it). Upload is already inert here through the
    // selection test below, because an empty folder has nothing selected
    // in it, so nothing needs a second predicate for the empty case.
    var empty = rows === 0;
    WM.el('panel-empty-note').hidden = !empty;

    WM.setEnabled('btn-upload', selected > 0);
    WM.setEnabled('f-stitch', selected > 1);
    // Only while there IS something to stitch. With an empty folder the
    // empty note above is the whole explanation, and a second sentence
    // telling the user to select two of nothing would be the "three
    // statements of the same emptiness" the walkthrough counted (14).
    WM.el('stitch-hint').hidden = empty || selected > 1;
    WM.el('lab-stitch').classList.toggle('disabled', selected < 2);
    // A box left ticked while its control is inert would still be read by
    // start_upload's caller below, so the checked state has to follow.
    if (selected < 2) WM.el('f-stitch').checked = false;
  }
  document.addEventListener('wm:selection', refreshEnabled);

  // ---- actions -------------------------------------------------------
  // Upload still sends unconditionally, even though refreshEnabled above
  // disables it with an empty selection. The guard and the disabled state
  // are not redundant: "select at least one video to upload" is composed
  // in Python (start_upload's _alert) and a page-side early return would
  // silently swallow it, and the button can be reached by a keyboard or a
  // stale render in the window between a selection changing and the event
  // landing. The disabled attribute is what the user reads; the Python
  // message is what they get if they arrive anyway.
  WM.el('btn-upload').addEventListener('click', function () {
    // Four arguments, not five. The combat-log checkbox is gone
    // (Uploader 8) and start_upload's `logs` parameter went with it in the
    // same commit; logs are unconditional and a configured webhook is what
    // decides the post.
    WM.send('start_upload',
            WM.el('f-title').value,
            WM.el('f-desc').value,
            WM.el('f-stitch').checked,
            WM.list.selectedIds());
  });

  WM.el('btn-retry').addEventListener('click', function () {
    WM.send('retry');
  });

  // ---- the no-webhook fact --------------------------------------------
  // This used to gate a checkbox. There is no checkbox now (Uploader 8):
  // logs are posted whenever a webhook exists, so the absence of one is a
  // standing fact about the install rather than a caveat on an option, and
  // it is stated wherever it is true instead of footnoting a control the
  // maintainer read past while asking for exactly this behaviour.
  //
  // Api._post_combat_logs is silent in this case ON PURPOSE and says so:
  // with no checkbox, a "combat logs skipped" strip on a webhook-less
  // install would fire on every upload forever, which is the recurring-
  // failure pattern format_upload_confirm's docstring records as a past
  // bug. The panel carrying the fact is what makes that silence honest.
  //
  // This tests for an ABSENT webhook, not an invalid one, and the
  // difference is deliberate. Whether a stored value actually posts is
  // discord.parse_webhook's answer, and format_upload_confirm runs that
  // exact function so the dialog cannot drift from the upload -- a second
  // predicate here, in JavaScript, is the drift ui/copy.py warns about in
  // as many words. So the page states only what it can verify itself
  // (nothing is stored) and leaves "this is stored but will not parse" to
  // the confirm, which says so in Python's words. A configured-but-broken
  // webhook still earns its WARNING strip from _post_combat_logs, because
  // nothing else will tell them.
  //
  // The sentence is read off the payload rather than typed here: S3 put
  // the app's one voice for an unmet precondition in copy.py (INERT_NOTES)
  // so the two screens that need one cannot drift apart.
  document.addEventListener('wm:settings', function (ev) {
    var detail = ev.detail || {};
    var cfg = detail.settings || {};
    var notes = detail.inert_notes || {};
    var configured = String(cfg.discord_webhook || '').trim() !== '';
    var note = WM.el('logs-note');
    note.textContent = notes.no_webhook || '';
    // Empty text as well as configured: a payload without the table would
    // otherwise unhide an empty paragraph holding 8px of margin.
    note.hidden = configured || !note.textContent;
  });

  // ---- status strip ---------------------------------------------------
  var KINDS = ['FG', 'SUCCESS', 'WARNING', 'ERROR'];

  // The strip is global chrome, and app.js deliberately never tells Python
  // which route is showing, so the page cannot work out on its own whether
  // what the strip holds is still true. Round 3's finding 14 is what that
  // costs: a green `Posted combatlogs-2026-08-24_21-54.zip (15 KB).` and a
  // bar at 100% were still on screen in a capture of a DIFFERENT folder
  // with zero recordings, and again on the Profiles and Skills routes. The
  // completion state of one upload outlived everything it described.
  //
  // `busy` on every strip payload is the missing fact, and Python is the
  // only place that has it (ui/api.py, _status / _progress). A RESULT is
  // cleared when the route changes; something STILL RUNNING never is,
  // because during an upload the strip is the only feedback there is
  // (finding 12) and a stitch can go minutes between pushes -- blanking it
  // there would leave the app looking idle mid-job.
  var stripBusy = false;

  // Read off the markup, not retyped: index.html carries the word and the
  // paragraph explaining why the resting text is `Idle` and not `Ready`.
  var IDLE = WM.el('status').textContent;

  function setStatus(text, kind) {
    var node = WM.el('status');
    node.textContent = text;
    node.className = KINDS.indexOf(kind) === -1 ? 'FG' : kind;
    node.title = text;   // the strip ellipsises a long ffmpeg error
  }

  function resetStrip() {
    if (stripBusy) return;
    setStatus(IDLE, 'FG');
    WM.el('track').classList.remove('indeterminate');
    // Back to the markup's resting state: no inline width, and an EMPTY
    // percentage rather than `0%`, which would read as a stalled job.
    WM.el('bar').style.width = '';
    WM.el('pct').textContent = '';
  }

  document.addEventListener('wm:route', resetStrip);

  WM.handle('onStatus', function (p) {
    stripBusy = !!p.busy;
    setStatus(p.text || '', p.kind);
  });

  WM.handle('onProgress', function (p) {
    stripBusy = !!p.busy;
    var track = WM.el('track'), bar = WM.el('bar'), pct = WM.el('pct');
    if (p.mode === 'indeterminate') {
      // A stitch reports no readable percentage. The bar must say
      // "working" without claiming one, so the number is blanked too.
      track.classList.add('indeterminate');
      bar.style.width = '';
      pct.textContent = '';
    } else {
      track.classList.remove('indeterminate');
      var value = Math.max(0, Math.min(100, Number(p.pct) || 0));
      bar.style.width = value + '%';
      pct.textContent = Math.round(value) + '%';
    }
    if (p.text) setStatus(p.text, p.kind);
  });

  WM.handle('onRetryAvailable', function (p) {
    WM.el('btn-retry').disabled = !p.available;
  });

  // ---- upload destination ---------------------------------------------
  // Rendered by Python and pushed, not composed here: format_destination
  // states the "learned from the first upload" case in words, and that
  // explanation is tested copy rather than a template.
  WM.handle('onChannel', function (p) {
    if (p.destination) WM.el('destination').textContent = p.destination;
  });

  WM.handle('onSettings', function (p) {
    if (p.destination) WM.el('destination').textContent = p.destination;
    // Settings owns the rest of this payload; it re-dispatches so both
    // modules can consume one push without either owning the handler.
    document.dispatchEvent(new CustomEvent('wm:settings', { detail: p }));
  });

  // ---- dialog layer ----------------------------------------------------
  // A queue, not a single slot: workers can push a warning and a confirm
  // in quick succession, and a second arriving dialog must not silently
  // discard the first — which for a `confirm` would strand Python waiting
  // on a dialog_response that never comes.
  var queue = [];
  var active = null;

  var overlay = WM.el('overlay');
  var dlg = WM.el('dialog');
  var btnOk = WM.el('dlg-ok');
  var btnCancel = WM.el('dlg-cancel');
  var dlgInput = WM.el('dlg-input');

  function show(item) {
    active = item;
    dlg.className = 'dialog ' + (item.kind || 'info');
    WM.el('dlg-title').textContent = item.title || '';
    WM.el('dlg-body').textContent = item.body || '';
    var isConfirm = item.kind === 'confirm';
    var isPrompt = item.kind === 'prompt';
    dlgInput.hidden = !isPrompt;
    if (isPrompt) { dlgInput.value = item.value || ''; }
    // A prompt is answerable too, so it needs the same way out.
    btnCancel.hidden = !(isConfirm || isPrompt);
    btnOk.textContent = isConfirm ? 'Confirm' : (isPrompt ? 'Set' : 'OK');
    // Upload is the app's only irreversible action, so the accent stays on
    // the affirming button of a confirm and on nothing else in the dialog.
    btnOk.className = isConfirm ? 'btn acc' : 'btn';
    overlay.hidden = false;
    // The field, not the button: a prompt exists to be typed into, and
    // landing on OK means every user starts with a Tab.
    if (isPrompt) { dlgInput.focus(); dlgInput.select(); } else { btnOk.focus(); }
  }

  function next() {
    active = null;
    overlay.hidden = true;
    if (queue.length) show(queue.shift());
  }

  function answer(ok) {
    if (!active) return;
    // A page-raised confirm resolves its own promise; a Python-raised one
    // answers across the bridge. Never both: Python is not waiting on a
    // dialog it did not ask for, and a spurious dialog_response would
    // answer somebody else's question.
    if (active.resolve) {
      // A prompt answers with its text, or null for cancel -- matching
      // window.prompt, so the call sites' `=== null` guards still hold.
      active.resolve(active.kind === 'prompt'
                     ? (ok ? dlgInput.value : null)
                     : ok);
    } else if (active.kind === 'confirm' && active.request_id !== undefined
               && active.request_id !== null) {
      WM.send('dialog_response', active.request_id, ok);
    }
    next();
  }

  // The page's own confirm, for a destructive action the page owns.
  //
  // Python's _confirm cannot serve these: it BLOCKS the calling thread
  // until dialog_response arrives, so it must run on a worker -- calling
  // it from a bridge method would deadlock the very thread that has to
  // deliver the answer. That is why reset_binds reached for
  // window.confirm, which WebView2 renders as browser chrome captioned
  // with the page's origin.
  //
  // Same queue, same styling, same Escape-is-No rule as a Python dialog.
  WM.confirm = function (title, body) {
    return new Promise(function (resolve) {
      var item = { kind: 'confirm', title: title, body: body,
                   resolve: resolve };
      if (active) { queue.push(item); } else { show(item); }
    });
  };

  // Resolves with the typed text, or null if cancelled -- the same
  // contract window.prompt had, so callers keep their `=== null` guard.
  WM.prompt = function (title, body, value) {
    return new Promise(function (resolve) {
      var item = { kind: 'prompt', title: title, body: body,
                   value: value, resolve: resolve };
      if (active) { queue.push(item); } else { show(item); }
    });
  };

  btnOk.addEventListener('click', function () { answer(true); });
  btnCancel.addEventListener('click', function () { answer(false); });

  document.addEventListener('keydown', function (ev) {
    if (overlay.hidden) return;
    if (ev.key === 'Escape') {
      ev.preventDefault();
      // Escape on a confirm is a No, never a silent dismissal: Python is
      // blocked on an answer and must get one. A prompt cancels the same
      // way -- answering true would set whatever happened to be in the
      // field.
      answer(active && (active.kind === 'confirm' || active.kind === 'prompt')
             ? false : true);
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      answer(true);
    }
  }, true);

  WM.handle('onDialog', function (p) {
    if (active) queue.push(p); else show(p);
  });
}());
