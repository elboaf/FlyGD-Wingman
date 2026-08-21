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
    // "12:31" -> 751. "?" and the ellipsis are not measurements and sort
    // to the bottom, exactly as app._sort_by's -1.0 does.
    var m = /^(\d+):(\d{2})$/.exec(String(text || '').trim());
    return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : -1;
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
      // The date CELL is a rendered string ("Aug 21  19:04") and cannot be
      // ordered as text — format_date's docstring warns a text sort would
      // put Aug before Dec. Python delivers rows newest-first, so delivery
      // INDEX is the date order, and it stays correct across years.
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

    node.appendChild(WM.make('span', 'c-date', row.date));
    node.appendChild(WM.make('span', 'c-size', row.size));

    var dur = WM.make('span', 'c-len', row.duration);
    var durTip = tooltipForCell('duration', row.duration);
    if (durTip) {
      dur.setAttribute('data-tip', durTip);
      dur.classList.add(row.duration === '?' ? 'dur-unknown' : 'dur-pending');
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
      });

    document.dispatchEvent(new CustomEvent('wm:selection'));
  }

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
  WM.el('list-head').addEventListener('click', function (ev) {
    var head = ev.target.closest('[data-sort]');
    if (!head) return;
    var key = head.dataset.sort;
    sortDesc = (key === sortKey) ? !sortDesc : false;
    sortKey = key;
    render();
    // No focus re-seed here. app.py's _sort_by re-orders and re-applies
    // zebra tags and nothing else -- and the header sits OUTSIDE
    // #list-scroll, so clicking it does not focus the list. Seeding here
    // would draw a ring on a list the user has still never tabbed to,
    // which is the same divergence the onRows guard exists to prevent.
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

  function hideMenu() { menu.hidden = true; ctxId = null; }

  body.addEventListener('contextmenu', function (ev) {
    var node = ev.target.closest('.list-row');
    if (!node) { hideMenu(); return; }
    ev.preventDefault();
    ctxId = node.dataset.id;
    setFocus(ctxId);
    var row = byId(ctxId);
    // Both items act on the YouTube link (app._copy / app._open), so both
    // are dead without one.
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
  document.addEventListener('mousedown', function (ev) {
    if (!menu.hidden && !menu.contains(ev.target)) hideMenu();
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') hideMenu();
  });
  window.addEventListener('blur', hideMenu);

  WM.el('btn-select-all').addEventListener('click', function () {
    rows.forEach(function (r) { selected[r.id] = true; });
    render();
  });
  WM.el('btn-select-none').addEventListener('click', function () {
    rows.forEach(function (r) { selected[r.id] = false; });
    render();
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
    row.link = 'https://www.youtube.com/watch?v=' + payload.video_id;
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
    // Exposed for console verification of the pure logic.
    parseSize: parseSize,
    parseDuration: parseDuration,
    compareRows: compareRows,
    tooltipForCell: tooltipForCell
  };
}());
