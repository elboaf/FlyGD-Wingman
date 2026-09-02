/* The recording list.
 *
 * Selection, sort order, and row focus are CLIENT state and never cross
 * the bridge. The only selection input from Python is the `preselected`
 * flag on onRows, because the watcher preselects newly-finished
 * recordings so the common case needs no clicking.
 */
(function () {
  'use strict';
  var WM = window.WM;

  // CELL_HELP, copied verbatim from ui/copy.py. Both glyphs were
  // unexplained: the list showed "?" and the arrow with nothing anywhere
  // saying what either meant. Keyed on the RENDERED text, not the
  // underlying value, so it cannot disagree with what the user sees.
  var CELL_HELP = {
    duration: {
      '?': 'Length could not be read. ffprobe could not open this file, so\n'
         + 'combat-log upload is unavailable for it.',
      // The dash is about the INSTALL, the "?" about the file. They shared
      // the "?" glyph until round 2, so an install with no ffprobe accused
      // every recording in the folder of being unreadable.
      '—': 'Length was not measured: ffprobe was not found.\n'
         + 'Wingman bundles it, so reinstalling restores lengths and\n'
         + 'combat-log upload.',
      '…': 'Measuring length…'
    },
    link: {
      '↗': 'Uploaded to YouTube.\n'
              + 'Double-click to open it, or right-click to copy the link.'
    }
  };
  var LINK_GLYPH = '↗';

  function tooltipForCell(column, text) {
    var col = CELL_HELP[column];
    return (col && col[text]) || null;
  }

  // ---- state --------------------------------------------------------
  var rows = [];              // in Python's delivery order (newest first)
  var order = [];             // ids, in display order
  var selected = Object.create(null);
  var focusId = null;
  var sortKey = null;         // null == Python's delivery order
  var sortDesc = false;
  var ctxId = null;

  // ---- pure helpers -------------------------------------------------
  // Kept as free functions with no DOM access so they can be exercised
  // directly from the devtools console (WM.list.parseSize etc.), which is
  // the whole of the verification budget for pure logic here.
  var UNITS = { B: 1, KB: 1024, MB: 1048576, GB: 1073741824, TB: 1099511627776 };

  function parseSize(text) {
    var m = /^([\d.]+)\s*(B|KB|MB|GB|TB)$/.exec(String(text || '').trim());
    return m ? parseFloat(m[1]) * UNITS[m[2]] : -1;
  }

  function parseDuration(text) {
    // "12:31" -> 751, "2:07:07" -> 7627. "?", the dash and the ellipsis
    // are not measurements: -1 sorts them together at the bottom rather
    // than letting a non-answer claim a position among real lengths.
    //
    // The hours group is optional because library.format_duration omits a
    // zero hour. It is NOT decoration: this sort reads the cell back out
    // of its own rendered text, so a format that emits a field this regex
    // rejects does not fail here, it returns -1 for those rows and the
    // column silently stops sorting. Round 3 landed the hours field; this
    // is the other half of that change.
    var m = /^(?:(\d+):)?(\d+):(\d{2})$/.exec(String(text || '').trim());
    if (!m) return -1;
    return (m[1] ? parseInt(m[1], 10) * 3600 : 0)
      + parseInt(m[2], 10) * 60 + parseInt(m[3], 10);
  }

  function compareRows(a, b, key) {
    if (key === 'checked') {
      return (selected[a.id] ? 1 : 0) - (selected[b.id] ? 1 : 0);
    }
    if (key === 'filename') {
      var an = String(a.name).toLowerCase(), bn = String(b.name).toLowerCase();
      return an < bn ? -1 : an > bn ? 1 : 0;
    }
    if (key === 'date') {
      // The date CELL is a rendered string ("3h ago", "yesterday",
      // "2025 Nov 02") and cannot be ordered as text -- format_date's
      // docstring warns a text sort would put Aug before Dec, and the
      // relative forms are worse still ("2d ago" before "3h ago").
      // Python delivers rows newest-first, so delivery INDEX is the date
      // order, and it stays correct across years.
      //
      // The example above read "Aug 21  19:04" until the Age column came
      // back: that was the ABSOLUTE format this column had before it was
      // dropped, and the comment outlived it by two rounds because no
      // header reached this branch to contradict it.
      return b._index - a._index;
    }
    if (key === 'size') return parseSize(a.size) - parseSize(b.size);
    if (key === 'duration') {
      return parseDuration(a.duration) - parseDuration(b.duration);
    }
    if (key === 'link') {
      return (a.link ? 1 : 0) - (b.link ? 1 : 0);
    }
    throw new Error('unknown sort column: ' + key);
  }

  function byId(id) {
    for (var i = 0; i < rows.length; i++) if (rows[i].id === id) return rows[i];
    return null;
  }

  // ---- rendering ----------------------------------------------------
  function recomputeOrder() {
    var ids = rows.map(function (r) { return r.id; });
    if (sortKey !== null) {
      var sorted = rows.slice().sort(function (a, b) {
        return compareRows(a, b, sortKey);
      });
      if (sortDesc) sorted.reverse();
      ids = sorted.map(function (r) { return r.id; });
    }
    order = ids;
  }

  function rowNode(row) {
    var node = WM.make('div', 'grid-row list-row');
    node.dataset.id = row.id;
    if (selected[row.id]) node.classList.add('sel');
    if (row.id === focusId) node.classList.add('focused');

    var check = WM.make('span', 'c-check');
    check.appendChild(WM.make('span', 'box'));
    node.appendChild(check);

    var name = WM.make('span', 'c-name', row.name);
    name.title = row.name;   // the elastic column ellipsises at narrow widths
    node.appendChild(name);

    // Pre-rendered by library.format_date, like every other cell here.
    // Deliberately not computed in JS from a timestamp: rows.py's Row
    // docstring makes the rule explicit -- a second implementation of a
    // format drifts from Python's, and the drift is invisible because
    // both sides keep working.
    //
    // The cost of a relative string, stated because it is real: the list
    // rebuilds on a new recording, a delete, a folder change or an
    // explicit refresh, and NOT on a timer (poll_tick refuses to rebuild
    // mid-upload -- it re-mints row ids and would drop links and
    // selection). So a window left open with no new recordings keeps the
    // ages it opened with. Accepted: the case where the ages go stale is
    // the case where nothing has happened.
    node.appendChild(WM.make('span', 'c-date', row.date));

    node.appendChild(WM.make('span', 'c-size', row.size));

    var dur = WM.make('span', 'c-len', row.duration);
    var durTip = tooltipForCell('duration', row.duration);
    if (durTip) {
      dur.setAttribute('data-tip', durTip);
      // Three glyphs, three states -- "?" the file is unreadable, "—" the
      // measurement was never taken, "…" it is being taken now. The first
      // two share a treatment (both are a standing non-answer); the third
      // is the transient one. Keyed off the rendered text, like the help
      // table above, so this cannot disagree with what is on screen.
      dur.classList.add(row.duration === '…' ? 'dur-pending' : 'dur-unknown');
    }
    node.appendChild(dur);

    var link = WM.make('span', 'c-link');
    if (row.link) {
      var glyph = WM.make('span', 'glyph-link', LINK_GLYPH);
      var tip = tooltipForCell('link', LINK_GLYPH);
      if (tip) glyph.setAttribute('data-tip', tip);
      link.appendChild(glyph);
    }
    node.appendChild(link);
    return node;
  }

  function render() {
    recomputeOrder();
    var body = WM.el('list-body');
    var frag = document.createDocumentFragment();
    order.forEach(function (id) {
      var row = byId(id);
      if (row) frag.appendChild(rowNode(row));
    });
    body.textContent = '';
    body.appendChild(frag);

    WM.el('list-empty').hidden = rows.length > 0;
    WM.el('list-count').textContent =
      rows.length + (rows.length === 1 ? ' recording' : ' recordings');

    Array.prototype.forEach.call(
      WM.el('list-head').children, function (head) {
        var active = head.dataset.sort === sortKey;
        head.classList.toggle('sorted', active);
        head.classList.toggle('desc', active && sortDesc);
        var label = head.title || 'Sort by ' + head.textContent.trim().toLowerCase();
        head.setAttribute('aria-label', label + (active
          ? ', ' + (sortDesc ? 'descending' : 'ascending')
          : ''));
      });

    document.dispatchEvent(new CustomEvent('wm:selection'));
  }

  // ---- the empty state ----------------------------------------------
  // "No recordings found in the watched folder" told the user neither
  // WHICH folder was watched nor how to change it, on the screen a
  // first-run user lands on immediately after nominating one -- so it is
  // exactly where a wrong pick surfaces, and the one place it said
  // nothing. PRODUCT.md's tone rule is to say what happened and what to
  // do.
  //
  // The sentence stays here rather than moving to ui/copy.py, which is
  // where almost every other user-facing string in the app is composed.
  // The path is already on the page -- _settings_payload returns
  // `settings` wholesale and panel.js re-dispatches it -- so naming it
  // costs a read, while migrating the sentence would mean a new push or
  // payload key for something that is otherwise static. Moving it is a
  // separate change from making it true.
  var recordingDir = '';

  // Uploader 12: "No recordings in D:\Videos", where D:\Videos was the
  // folder that DID have the recordings and the configured-and-empty one
  // was elsewhere. The next line then offered to open the wrong folder.
  //
  // Confirmed by S3, in Api.set_folder: it persists, rebinds the watcher
  // and calls list_rows, but never re-delivers the settings payload -- so
  // the cached recordingDir below kept naming the PREVIOUS folder while
  // the scan was of the new one. Exactly the reported symptom.
  //
  // Fixed by re-reading rather than by asking Python to push. S3 declined
  // to push onSettings and gave the reason: get_settings is a return and
  // never a push, because a whole-document delivery discards unsaved edits
  // in an open Settings form -- the trap DESIGN.md records under "an
  // endpoint whose effect reaches outside its own control".
  //
  // For the same reason this does NOT re-dispatch wm:settings. The event
  // repaints every field on the Settings route, and list_rows fires on
  // every watcher poll; riding it would rewrite a folder path the user was
  // still typing, several times a minute. Only the one value this module
  // renders is taken, and only when the empty state is what is showing --
  // which is the only time the folder is named at all.
  function refreshRecordingDir() {
    WM.send('get_settings').then(function (payload) {
      if (!payload) return;
      var dir = (payload.settings || {}).recording_dir || '';
      if (dir === recordingDir) return;
      recordingDir = dir;
      renderEmpty();
    });
  }

  function renderEmpty() {
    var host = WM.el('list-empty');
    host.textContent = '';
    if (!recordingDir) {
      // No folder configured at all -- a skipped first run. There is
      // nothing to name, and Settings is the only thing to say.
      host.appendChild(document.createTextNode(
        'No recording folder is set yet.'));
      host.appendChild(WM.make('div', 'where',
        'Choose one in Settings \u203A Folders.'));
      return;
    }
    host.appendChild(document.createTextNode('No recordings in '));
    host.appendChild(WM.make('span', 'path', recordingDir));
    host.appendChild(WM.make('div', 'where',
      'Open folder below to check it, or change it in '
      + 'Settings \u203A Folders.'));
  }

  document.addEventListener('wm:settings', function (ev) {
    // panel.js owns the onSettings handler and re-dispatches it, so this
    // listens on the same event settings.js does rather than competing
    // for the handler.
    var cfg = (ev.detail || {}).settings || {};
    recordingDir = cfg.recording_dir || '';
    renderEmpty();
  });

  // Repaint one row in place, so a landing ffprobe result or a new link
  // does not scroll the list or drop the focus ring.
  function repaint(id) {
    var old = WM.el('list-body').querySelector('[data-id="' + id + '"]');
    var row = byId(id);
    if (!old || !row) return;
    old.replaceWith(rowNode(row));
  }

  // ---- selection ----------------------------------------------------
  // One toggle path, shared by mouse and keyboard, so the drawn box can
  // never drift out of step with what selectedIds() reports.
  function toggle(id) {
    if (!byId(id)) return;
    selected[id] = !selected[id];
    var node = WM.el('list-body').querySelector('[data-id="' + id + '"]');
    if (node) node.classList.toggle('sel', !!selected[id]);
    // A "checked" sort is a snapshot, not a live constraint: re-sorting on
    // every tick would move the row out from under the pointer.
    document.dispatchEvent(new CustomEvent('wm:selection'));
  }

  function setFocus(id) {
    var body = WM.el('list-body');
    var prev = body.querySelector('.list-row.focused');
    if (prev) prev.classList.remove('focused');
    focusId = id;
    var node = id && body.querySelector('[data-id="' + id + '"]');
    if (node) {
      node.classList.add('focused');
      node.scrollIntoView({ block: 'nearest' });
    }
  }

  // Tk's arrow handler returns immediately when the focus item is "", and
  // refresh() leaves it "" because every row is reinserted. Without this,
  // tabbing to the list and pressing Down does nothing and Space is
  // unreachable without first reaching for the mouse.
  function ensureFocusItem() {
    if (focusId && byId(focusId)) return;
    setFocus(order.length ? order[0] : null);
  }

  // ---- events -------------------------------------------------------
  function sortBy(key) {
    sortDesc = (key === sortKey) ? !sortDesc : false;
    sortKey = key;
    render();
    // No focus re-seed here. sortBy() and render() own client-only sorting,
    // and the header sits OUTSIDE #list-scroll, so sorting it does not focus
    // the list. Seeding here would draw a ring on a list the user has still
    // never tabbed to, which is the same divergence the onRows guard prevents.
  }

  WM.el('list-head').addEventListener('click', function (ev) {
    var head = ev.target.closest('[data-sort]');
    if (!head) return;
    sortBy(head.dataset.sort);
  });

  WM.el('list-head').addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
      var head = ev.target.closest('[data-sort]');
      if (!head) return;
      ev.preventDefault();
      sortBy(head.dataset.sort);
    }
  });

  var body = WM.el('list-body');

  body.addEventListener('click', function (ev) {
    var node = ev.target.closest('.list-row');
    if (!node) return;
    // event.detail === 2 is the SECOND click of a double-click. Skipping
    // it leaves exactly one toggle landed by the time dblclick fires,
    // which is the situation the Tk handler was written against.
    if (ev.detail > 1) return;
    // The WHOLE row is the click target, not just the checkbox cell: a
    // 34px column is a small thing to ask someone to hit when "I mean this
    // recording" is unambiguous anywhere on the line.
    setFocus(node.dataset.id);
    toggle(node.dataset.id);
  });

  body.addEventListener('dblclick', function (ev) {
    var node = ev.target.closest('.list-row');
    if (!node) return;
    // Exactly one toggle has already landed; undo it. Opening a video is
    // not a selection gesture, and a user reaching for their upload should
    // not find an extra row ticked afterwards.
    toggle(node.dataset.id);
    WM.send('open_path', node.dataset.id);
  });

  var scroll = WM.el('list-scroll');
  scroll.addEventListener('focus', ensureFocusItem);
  scroll.addEventListener('keydown', function (ev) {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      ensureFocusItem();
      var at = order.indexOf(focusId);
      var next = at + (ev.key === 'ArrowDown' ? 1 : -1);
      if (next >= 0 && next < order.length) setFocus(order[next]);
      return;
    }
    if (ev.key === ' ' || ev.key === 'Spacebar') {
      // Keyboard equivalent of clicking the checkbox. preventDefault is
      // the browser's answer to Tk's "break": without it Space also
      // page-scrolls the list.
      ev.preventDefault();
      ensureFocusItem();
      if (focusId) toggle(focusId);
    }
  });

  // ---- context menu -------------------------------------------------
  var menu = WM.el('ctxmenu');
  var ctxCopy = WM.el('ctx-copy');
  var ctxOpen = WM.el('ctx-open');
  var ctxPlay = WM.el('ctx-play');
  var ctxRename = WM.el('ctx-rename');

  function hideMenu() { menu.hidden = true; ctxId = null; }

  body.addEventListener('contextmenu', function (ev) {
    var node = ev.target.closest('.list-row');
    if (!node) { hideMenu(); return; }
    ev.preventDefault();
    ctxId = node.dataset.id;
    setFocus(ctxId);
    var row = byId(ctxId);
    // Copy link and Open in browser act on the YouTube link (app._copy /
    // app._open), so both are dead without one.
    //
    // Play and Rename are NOT gated, and that follows the same rule rather
    // than excepting it: WM.setEnabled disables a control when the app
    // ALREADY KNOWS the action cannot be carried out. Whether the file is
    // still on disk is a fact about the disk that goes stale, and the row
    // payload carries no such field -- adding one would be worse, because
    // rebuild() only ever emits rows for files that existed at scan time,
    // so it would read true for every row forever. Python runs them and
    // reports on the strip.
    var has = !!(row && row.link);
    ctxCopy.disabled = !has;
    ctxOpen.disabled = !has;
    menu.hidden = false;
    // Clamp inside the window: a menu opened on the last row would
    // otherwise hang below the status strip.
    var w = menu.offsetWidth, h = menu.offsetHeight;
    menu.style.left = Math.min(ev.clientX, window.innerWidth - w - 6) + 'px';
    menu.style.top = Math.min(ev.clientY, window.innerHeight - h - 6) + 'px';
  });

  ctxCopy.addEventListener('click', function () {
    if (ctxId) {
      // Python returns the URL; the page owns the clipboard write, because
      // with Tk gone there is no toolkit clipboard and navigator.clipboard
      // is right there.
      var id = ctxId;
      WM.send('copy_path', id).then(function (url) {
        if (url) navigator.clipboard.writeText(url);
      });
    }
    hideMenu();
  });
  ctxOpen.addEventListener('click', function () {
    if (ctxId) WM.send('open_path', ctxId);
    hideMenu();
  });

  // Play opens the RECORDING, where the two items above open the video it
  // became. The screen is about a folder's contents and every affordance
  // on it used to act on the link instead; "is this the fight I think it
  // is" is answered by watching two seconds of it.
  ctxPlay.addEventListener('click', function () {
    if (ctxId) WM.send('play_recording', ctxId);
    hideMenu();
  });

  // Rename prompts for the STEM and Python reappends the extension, so a
  // user cannot turn .mkv into .mp4 by typing -- that would be a rename
  // claiming a remux happened.
  //
  // WM.prompt, never window.prompt: WebView2 renders the native one as
  // browser chrome captioned with the page origin. Python's _confirm
  // cannot serve this either -- it blocks until dialog_response arrives,
  // on the very bridge thread that would have to deliver it (DESIGN.md,
  // "Which confirmation").
  //
  // The id is captured BEFORE the dialog opens, because hideMenu() nulls
  // ctxId and the answer arrives seconds later -- the same local-copy the
  // Copy handler above takes for the same reason.
  //
  // A refusal re-opens the prompt with the typed text still in it, so a
  // typo costs a keystroke rather than the whole name. Every sentence in
  // it is composed in Python: the page does not know that CON is
  // reserved, that a name cannot end in a dot, or that an upload is
  // running.
  function promptRename(id, name, message) {
    var dot = name.lastIndexOf('.');
    var stem = dot > 0 ? name.slice(0, dot) : name;
    WM.prompt('Rename recording', message || 'New name:', stem)
      .then(function (answer) {
        if (answer === null) return;
        WM.send('rename_recording', id, answer).then(function (result) {
          if (!result || result.ok) return;
          promptRename(id, name, result.error);
        });
      });
  }

  ctxRename.addEventListener('click', function () {
    var id = ctxId;
    var row = id && byId(id);
    hideMenu();
    if (row) promptRename(id, row.name);
  });
  document.addEventListener('mousedown', function (ev) {
    if (!menu.hidden && !menu.contains(ev.target)) hideMenu();
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') hideMenu();
  });
  window.addEventListener('blur', hideMenu);

  // Round 3, finding 7 (and round 2's Settings 14, the same species one
  // screen over): all three of these were live at `0 recordings`, so three
  // of the four footer controls could not do anything and said nothing
  // about it. WM.setEnabled's rule is that a control whose object is
  // ABSENT is inert -- Select all's object is the list, and Select none's
  // and Delete's is the selection.
  //
  // Open folder is deliberately NOT here: its object is the folder, which
  // exists whether or not it holds recordings, and it is the one control
  // that helps when the list is empty. Nor does this disable the list
  // itself, which is the only route out of the state that disabled these.
  function refreshFooter() {
    var any = rows.length > 0;
    var picked = WM.list.selectedIds().length > 0;
    WM.setEnabled('btn-select-all', any);
    WM.setEnabled('btn-select-none', picked);
    WM.setEnabled('btn-delete', picked);
  }
  document.addEventListener('wm:selection', refreshFooter);

  WM.el('btn-select-all').addEventListener('click', function () {
    rows.forEach(function (r) { selected[r.id] = true; });
    render();
  });
  WM.el('btn-select-none').addEventListener('click', function () {
    rows.forEach(function (r) { selected[r.id] = false; });
    render();
  });

  // Sends unconditionally, including with no folder configured: every
  // refusal is a specific message composed in Python and pushed to the
  // status strip (Api.open_recording_dir), and a page-side early return
  // would swallow the one that says WHY nothing opened.
  WM.el('btn-open-folder').addEventListener('click', function () {
    WM.send('open_recording_dir');
  });

  // Uploader 2's third seam: this deletes files from disk, and it used to
  // sit in the panel under a card headed PUBLISH, beside the button that
  // sends them to YouTube. It acts on the same selection as Select all /
  // Select none and on the same files the list is showing, so it lives
  // with them and list.js owns it for the same reason it owns those.
  //
  // Sends unconditionally, like the rest of this footer: "select at least
  // one video" is composed in Python (Api.delete_selected) and a page-side
  // early return would swallow it.
  WM.el('btn-delete').addEventListener('click', function () {
    WM.send('delete_selected', WM.list.selectedIds());
  });

  // ---- bridge handlers ----------------------------------------------
  WM.handle('onRows', function (payload) {
    var incoming = payload.rows || [];
    var known = Object.create(null);
    incoming.forEach(function (r, i) { r._index = i; known[r.id] = true; });
    // Ids are minted fresh on every rebuild (see ui/rows.py), so a
    // selection carried across a refresh by id would silently attach to
    // different recordings. Selection therefore starts from whatever
    // Python marked preselected, and stale entries are dropped.
    Object.keys(selected).forEach(function (id) {
      if (!known[id]) delete selected[id];
    });
    incoming.forEach(function (r) {
      if (r.preselected) selected[r.id] = true;
    });
    rows = incoming;
    if (focusId && !known[focusId]) focusId = null;
    render();
    // Uploader 12. Only when the empty state is the thing on screen: that
    // is the only render that names the folder, and set_folder reaches
    // here through list_rows without the settings payload following it.
    if (!rows.length) refreshRecordingDir();
    // Re-seed the focus item ONLY if the user is already on the list.
    // Rebuilding cleared it, and without this arrow keys go dead
    // mid-session with no focus event coming to fix them -- but seeding
    // unconditionally would put a focus ring on a list nobody has tabbed
    // to yet. This is the guard app.py's refresh() used verbatim
    // (`if self.tree.focus_get() is self.tree`).
    if (document.activeElement === scroll
        || scroll.contains(document.activeElement)) {
      ensureFocusItem();
    }
  });

  WM.handle('onDuration', function (payload) {
    var row = byId(payload.id);
    if (!row) return;   // a refresh may have dropped it mid-probe
    row.duration = payload.duration;
    row.definitive = !!payload.definitive;
    repaint(payload.id);
    document.dispatchEvent(new CustomEvent('wm:selection'));
  });

  WM.handle('onLink', function (payload) {
    var row = byId(payload.id);
    if (!row) return;
    // The URL arrives finished. This used to concatenate one from
    // payload.video_id, which made it the third place in the app that knew
    // what a YouTube watch URL looks like -- see uploader.watch_url.
    row.link = payload.url;
    repaint(payload.id);
  });

  // One row, repainted in place. NOT a rebuild: list_rows re-mints every
  // id (ui/rows.py), and this file drops every selection and focus id it
  // no longer recognises on each onRows -- so a rebuild would cost the
  // user's ticks and their keyboard position. (The sort key survives; it
  // lives here, not in Python.) Every other rebuild follows something
  // that changed the folder; a rename changes one row's text.
  WM.handle('onRowRenamed', function (payload) {
    var row = byId(payload.id);
    if (!row) return;
    row.name = payload.name;
    repaint(payload.id);
  });

  // ---- exports for the other page modules ---------------------------
  WM.list = {
    selectedIds: function () {
      return order.filter(function (id) { return !!selected[id]; });
    },
    selectedRows: function () {
      return order.map(byId).filter(function (r) { return r && selected[r.id]; });
    },
    rowCount: function () { return rows.length; },
    // For the panel's completion state (round 3, finding 5). Selection is
    // list.js's own state and no other module touches `selected` directly;
    // this is the one operation the panel needs and it goes through
    // render(), so the drawn boxes, the footer's enabled rule and the
    // panel's summary all settle from the same dispatch.
    clearSelection: function () {
      rows.forEach(function (r) { selected[r.id] = false; });
      render();
    },
    // Exposed for console verification of the pure logic.
    parseSize: parseSize,
    parseDuration: parseDuration,
    compareRows: compareRows,
    tooltipForCell: tooltipForCell
  };
}());
