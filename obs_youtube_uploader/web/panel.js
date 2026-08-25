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

  // ---- actions -------------------------------------------------------
  // Every one of these sends unconditionally, including with an empty
  // selection: the "select at least one video" warnings are distinct
  // messages composed in Python, and a page-side early return would
  // silently swallow them.
  WM.el('btn-upload').addEventListener('click', function () {
    WM.send('start_upload',
            WM.el('f-title').value,
            WM.el('f-desc').value,
            WM.el('f-stitch').checked,
            WM.el('f-logs').checked,
            WM.list.selectedIds());
  });

  WM.el('btn-delete').addEventListener('click', function () {
    WM.send('delete_selected', WM.list.selectedIds());
  });

  WM.el('btn-retry').addEventListener('click', function () {
    WM.send('retry');
  });

  // ---- the combat-log option is only real with a webhook ---------------
  // The box shipped ticked with nothing gating it, so on a fresh install
  // it looked like a feature the user had: they ticked nothing, confirmed,
  // and the run ended on a WARNING strip saying logs were skipped -- once
  // per upload, forever, reading as a recurring failure rather than as an
  // unconfigured option.
  //
  // This tests for an ABSENT webhook, not an invalid one, and the
  // difference is deliberate. Whether a stored value actually posts is
  // discord.parse_webhook's answer, and format_upload_confirm now runs
  // that exact function so the dialog cannot drift from the upload -- a
  // second predicate here, in JavaScript, is the drift ui/copy.py warns
  // about in as many words. So the page states only what it can verify
  // itself (nothing is stored) and leaves "this is stored but will not
  // parse" to the confirm, which says so in Python's words. Both
  // statements are true; neither is a copy of the other.
  var forcedOff = false;

  document.addEventListener('wm:settings', function (ev) {
    var cfg = (ev.detail || {}).settings || {};
    var configured = String(cfg.discord_webhook || '').trim() !== '';
    var box = WM.el('f-logs');
    box.disabled = !configured;
    if (!configured) {
      // Only remembered as ours if it was actually on. A user who unticked
      // the box deliberately and then cleared their webhook must not find
      // it ticked again when they put the webhook back.
      if (box.checked) { box.checked = false; forcedOff = true; }
    } else if (forcedOff) {
      box.checked = true;
      forcedOff = false;
    }
    WM.el('lab-logs').classList.toggle('disabled', !configured);
    WM.el('logs-hint').hidden = configured;
  });

  // ---- status strip ---------------------------------------------------
  var KINDS = ['FG', 'SUCCESS', 'WARNING', 'ERROR'];

  function setStatus(text, kind) {
    var node = WM.el('status');
    node.textContent = text;
    node.className = KINDS.indexOf(kind) === -1 ? 'FG' : kind;
    node.title = text;   // the strip ellipsises a long ffmpeg error
  }

  WM.handle('onStatus', function (p) {
    setStatus(p.text || '', p.kind);
  });

  WM.handle('onProgress', function (p) {
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
