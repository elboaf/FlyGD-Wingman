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

  // Upload defaults live in Settings and ride along on start_upload.
  // Defaults mirror settings.DEFAULTS so a send before onSettings lands is
  // still a valid call rather than undefined.
  var prefs = { privacy: 'unlisted', category: '20' };

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
            prefs.privacy,
            prefs.category,
            WM.el('f-stitch').checked,
            WM.list.selectedIds());
  });

  WM.el('btn-combat').addEventListener('click', function () {
    WM.send('upload_combat_logs', WM.list.selectedIds());
  });

  WM.el('btn-delete').addEventListener('click', function () {
    WM.send('delete_selected', WM.list.selectedIds());
  });

  WM.el('btn-retry').addEventListener('click', function () {
    WM.send('retry');
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
    var s = p.settings || {};
    if (s.privacy) prefs.privacy = s.privacy;
    if (s.category) prefs.category = s.category;
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

  function show(item) {
    active = item;
    dlg.className = 'dialog ' + (item.kind || 'info');
    WM.el('dlg-title').textContent = item.title || '';
    WM.el('dlg-body').textContent = item.body || '';
    var isConfirm = item.kind === 'confirm';
    btnCancel.hidden = !isConfirm;
    btnOk.textContent = isConfirm ? 'Confirm' : 'OK';
    // Upload is the app's only irreversible action, so the accent stays on
    // the affirming button of a confirm and on nothing else in the dialog.
    btnOk.className = isConfirm ? 'btn acc' : 'btn';
    overlay.hidden = false;
    btnOk.focus();
  }

  function next() {
    active = null;
    overlay.hidden = true;
    if (queue.length) show(queue.shift());
  }

  function answer(ok) {
    if (!active) return;
    if (active.kind === 'confirm' && active.request_id !== undefined
        && active.request_id !== null) {
      WM.send('dialog_response', active.request_id, ok);
    }
    next();
  }

  btnOk.addEventListener('click', function () { answer(true); });
  btnCancel.addEventListener('click', function () { answer(false); });

  document.addEventListener('keydown', function (ev) {
    if (overlay.hidden) return;
    if (ev.key === 'Escape') {
      ev.preventDefault();
      // Escape on a confirm is a No, never a silent dismissal: Python is
      // blocked on an answer and must get one.
      answer(active && active.kind === 'confirm' ? false : true);
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      answer(true);
    }
  }, true);

  WM.handle('onDialog', function (p) {
    if (active) queue.push(p); else show(p);
  });
}());
