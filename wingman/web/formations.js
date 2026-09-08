/* FlyGD Wingman — the probe formation editor.
 *
 * A sub-screen of Profiles on a route id the title bar never shows (see
 * app.js's WM.route map and index.html's #route-formations comment).
 *
 * Edit state lives here in km (positions) and AU (ranges); the bridge and
 * the .dat both speak meters. fromSharedMeters converts portable geometry;
 * fromMeters additionally normalizes ordinary reads. toMeters handles Save
 * and Copy snapshots. Never convert again in a caller: a formation 1000x
 * out still draws as a formation. Executable page tests cover all callers.
 *
 * Ids travel with their formation (null = new). The client keys its
 * selectedFormationID on the id, so a save that re-numbered by list
 * position would move which formation the client has selected -- the bug
 * docs/eve-settings-decode-design.md names in eve-wrench.
 *
 * Deliberately dumb about file validity: what a legal formation IS lives
 * in wingman/evesettings/formations.py. The executable page tests cover
 * edit/correlation flow; Python still validates every document before a
 * write. This file captures edits, sends them, and renders the answer.
 *
 * `problem()` is the one exception, and it does not move the authority.
 * A refusal from validate() discards the WHOLE save rather than the
 * offending formation, so three states this editor can build -- an empty
 * name, a duplicate name, a formation whose last probe was removed --
 * would cost the user every other edit in the list. It restates three of
 * validate()'s rules to keep Save from sending such a document at all;
 * Python still decides, and still checks the rules the controls here
 * cannot break.
 */
(function () {
  'use strict';

  // Explicit tooling-only read state. Never installed by startup or Python;
  // the real opener/renderers still own the view, and route leave retires it.
  var screenshotFixture = null, screenshotLastAccount = '';
  WM.formationsScreenshot = function (payload) {
    if (!payload) {
      if (!screenshotFixture) return;
      closeImportReview(false);
      loadGeneration += 1;
      state.path = ''; state.contentRevision = ''; state.formations = [];
      state.dirty = false; state.busy = false;
      accountChoices = []; selectedAccountPath = '';
      lastSuccessfulPath = screenshotLastAccount;
      screenshotFixture = null;
      return;
    }
    if (payload.kind !== 'formations-screenshot-v1' || JSON.stringify(payload).length > 65536
        || !payload.accounts || payload.accounts.length !== 1 || !payload.snapshot
        || !payload.snapshot.ok || !payload.snapshot.formations.length || !payload.import_reply) {
      throw new Error('Invalid formations screenshot fixture');
    }
    WM.formationsScreenshot(null);
    screenshotLastAccount = lastSuccessfulPath;
    screenshotFixture = JSON.parse(JSON.stringify(payload));
    WM.openFormations(screenshotFixture.accounts, screenshotFixture.accounts[0].path);
  };

  var KM = 1000;
  var AU = 149597870700;
  // The launcher holds eight. Kept in step with formations.MAX_PROBES by
  // Python refusing a ninth -- this only stops the button offering one.
  var MAX_PROBES = 8;
  // Valid scan ranges are powers of two from 0.25 to 64 AU. Core probes
  // stop at 32; combat probes reach 64, and a formation does not know
  // which kind will launch it, so the editor offers the union.
  var RANGES = [0.25, 0.5, 1, 2, 4, 8, 16, 32, 64];
  // Screen-reader label for each internal axis letter, matching the column
  // headers ('West (km)', 'Up (km)', 'North (km)') rather than the raw x/y/z.
  var AXIS_LABELS = { x: 'West', y: 'Up', z: 'North' };

  var state = {
    path: '', contentRevision: '', formations: [], selected: 0,
    dirty: false, busy: false
  };
  // Account paths in the supplied choice list are UI identities. Python
  // resolves a requested path before reading it, so the returned path can
  // differ for a junction, symlink, or Windows case normalization; that
  // resolved path is only the save target.
  var accountChoices = [], selectedAccountPath = '', lastSuccessfulPath = '';
  // Bumped by every edit, and sampled when a save is sent. A save takes a
  // worker and a push to finish, and the pane stays live throughout -- so
  // without this, an edit made WHILE saving is marked clean by the push
  // that answers the older state and is then thrown away by `‹ Profiles`
  // without a confirm. Disabling the whole pane for the duration would
  // also fix it, and would punish the common case for the rare one.
  var revision = 0, savingAt = -1;
  // Correlation only, never authorization. A fresh page cannot reuse a prior
  // page's request IDs even if its generation and sequence start over.
  var pageSession = String(Date.now()) + '-' + Math.random().toString(36).slice(2);
  var loadGeneration = 0, readAttempt = 0, saveSequence = 0, pendingSave = null;
  // Sharing selection is independent of the open editor row. Object identity
  // survives rename/deletion without moving a tick onto a different formation.
  var copySelection = [], copyAttempt = 0, sharingLimits = null;
  // Review geometry remains canonical meters, separate from the draft. Attempts
  // never reset: editing text/names, cancelling, or leaving invalidates replies.
  var importReview = null, importAttempt = 0;
  var yaw = 0.6, pitch = 0.4, dragging = false, lastX = 0, lastY = 0;

  function probe(x, y, z) { return { x: x, y: y, z: z, range: 32 }; }
  function spread(d) {
    return [probe(d, 0, 0), probe(-d, 0, 0), probe(0, 0, d), probe(0, 0, -d),
            probe(0, d, 0), probe(0, -d, 0), probe(0, 2 * d, 0),
            probe(0, -2 * d, 0)];
  }
  // A line of seven along one axis plus one counterweight so the centroid
  // is zero: EVE re-centres a launched formation on its centroid, so a
  // one-sided line would launch centred on the ship rather than reaching
  // the way it is drawn.
  function stack(axis, sign) {
    var total = 0, out = [], i, d;
    for (i = 1; i <= 7; i++) { total += i * 200; }
    for (i = 1; i <= 8; i++) {
      d = (i <= 7 ? i * 200 : -total) * sign;
      out.push(probe(axis === 'x' ? d : 0, axis === 'y' ? d : 0,
                     axis === 'z' ? d : 0));
    }
    return out;
  }
  var PRESETS = [
    { id: 'blank', label: 'Blank spread (250 km)',
      probes: function () { return spread(250); } },
    { id: 'pinpoint', label: 'Pinpoint (500 km)',
      probes: function () { return spread(500); } },
    { id: 'drifter', label: 'Drifter', probes: function () {
      return [probe(11000, 3400, 0), probe(-11000, -3400, 0)]
        .concat(spread(250).slice(0, 6));
    } },
    { id: 'north', label: 'Stack north',
      probes: function () { return stack('z', 1); } },
    { id: 'south', label: 'Stack south',
      probes: function () { return stack('z', -1); } },
    { id: 'west', label: 'Stack west',
      probes: function () { return stack('x', 1); } },
    { id: 'east', label: 'Stack east',
      probes: function () { return stack('x', -1); } },
    { id: 'up', label: 'Stack up',
      probes: function () { return stack('y', 1); } },
    { id: 'down', label: 'Stack down',
      probes: function () { return stack('y', -1); } }
  ];

  function current() { return state.formations[state.selected] || null; }
  function round3(v) { return Math.round(v * 1000) / 1000; }
  function markDirty() { state.dirty = true; revision += 1; paintCommit(); }

  function centroid(f) {
    var c = { x: 0, y: 0, z: 0 }, n = f.probes.length, i;
    if (!n) { return c; }
    for (i = 0; i < n; i++) {
      c.x += f.probes[i].x; c.y += f.probes[i].y; c.z += f.probes[i].z;
    }
    return { x: c.x / n, y: c.y / n, z: c.z / n };
  }
  function shift(f) {
    var c = centroid(f);
    return Math.sqrt(c.x * c.x + c.y * c.y + c.z * c.z);
  }
  // Half a km, not zero: the coordinates are f64 meters coming back from
  // the file and a formation the user drew as symmetric can miss by
  // floating-point dust. Half a km is invisible at every scan range and
  // is well under the smallest offset anyone types.
  function balanced(f) { return shift(f) < 0.5; }

  // Zero the centroid with one counterweight: append if the launcher has
  // room, otherwise repurpose the last probe.
  function balance() {
    var f = current(), full, rest, s = { x: 0, y: 0, z: 0 }, i, cw;
    if (!f || !f.probes.length || balanced(f)) { return; }
    full = f.probes.length >= MAX_PROBES;
    rest = full ? f.probes.slice(0, -1) : f.probes;
    for (i = 0; i < rest.length; i++) {
      s.x += rest[i].x; s.y += rest[i].y; s.z += rest[i].z;
    }
    cw = { x: round3(-s.x), y: round3(-s.y), z: round3(-s.z),
           range: rest[0].range };
    if (full) { f.probes[f.probes.length - 1] = cw; } else { f.probes.push(cw); }
    markDirty(); renderProbes(); renderPreview();
  }

  /* ---- meter boundary, ordinary reads / sharing / save ---- */
  // The range is rounded to six decimal places OF AN AU on the way in;
  // the positions are not.
  //
  // The tolerance is 1e-6 AU, which is about 150 km -- enormous in
  // absolute terms, and irrelevant at this scale: the ranges the client
  // offers are 0.25 AU apart, i.e. about 37 million km, so nothing this
  // rounding can move is a range anybody chose. (An earlier version of
  // this comment claimed "well under a metre at one AU", which is wrong
  // by five orders of magnitude. A metre would be 1e-11 AU.)
  //
  // What it is FOR is narrow: rangeSelect matches a range against RANGES
  // by value and appends anything else as a selectable option -- the
  // escape hatch the design doc asks for, so an unusual value in an
  // existing file is never silently rewritten. Float dust in the file's
  // f64 would spend that escape hatch on `3.9999999996 AU`, which is not
  // an unusual value at all. A position IS the user's own number, so it
  // is left exactly as the file has it.
  function fromMeters(f) {
    var converted = fromSharedMeters(f);
    converted.id = f.id;
    converted.probes.forEach(function (p) {
      p.range = Math.round(p.range * 1e6) / 1e6;
    });
    return converted;
  }
  // Sharing preserves supported fractional ranges until an ordinary file read.
  // Never reuse read normalization for an imported preview or Add snapshot.
  function fromSharedMeters(f) {
    return { id: null, name: f.name, probes: f.probes.map(function (p) {
      return { x: p.x / KM, y: p.y / KM, z: p.z / KM, range: p.range / AU };
    }) };
  }
  function toMeters(f) {
    return { id: f.id, name: f.name, probes: f.probes.map(function (p) {
      return { x: p.x * KM, y: p.y * KM, z: p.z * KM, range: p.range * AU };
    }) };
  }

  function renderAccounts(path) {
    var select = WM.el('fm-account');
    select.textContent = '';
    accountChoices.forEach(function (account) {
      var option = document.createElement('option');
      option.value = account.path;
      option.textContent = account.name;
      select.appendChild(option);
    });
    select.value = path;
    var currentAccount = accountChoices.filter(function (account) {
      return account.path === path;
    })[0];
    select.title = currentAccount ? currentAccount.name : '';
  }

  function accountPath(preferredPath) {
    var paths = accountChoices.map(function (account) { return account.path; });
    if (paths.indexOf(lastSuccessfulPath) !== -1) return lastSuccessfulPath;
    if (paths.indexOf(preferredPath) !== -1) return preferredPath;
    return paths[0] || '';
  }

  // Two optional arguments for rereads, automatic after Save or explicit.
  //
  // keepIndex: the list comes back with Python's minted ids, and dropping
  // the user back on the first formation would make a save read as a
  // navigation.
  //
  // protect: abandon the answer rather than paint over an edit made while
  // it was in flight. This is a SECOND async window, and it is not the one
  // formationsDone's revision check covers -- that one guards send ->
  // push; this one guards push -> re-read, and the pane stays live through
  // both. Without it the reload's `.then` overwrites state.formations and
  // clears dirty unconditionally, which is the same silent loss the reload
  // itself was added to close, one step later.
  //
  // An INITIAL open passes neither: it is a replacement, not a refresh --
  // the pane is still showing whatever the last account held, and there is
  // nothing there worth protecting from the file being opened.
  function load(path, mode, keepIndex, protect) {
    closeImportReview(false);
    var startedAt = revision;
    if (mode === 'switch') { loadGeneration += 1; }
    var generation = loadGeneration, attempt = ++readAttempt;
    state.busy = true; paintCommit();
    var pending = screenshotFixture ? Promise.resolve(JSON.parse(JSON.stringify(screenshotFixture.snapshot)))
      : WM.send('eve_settings_formations', path);
    return pending.then(function (reply) {
      // Even failure belongs to the request that caused it. Check identity
      // before clearing busy, showing a dialog, or touching either baseline.
      if (WM.current_route !== 'formations' || generation !== loadGeneration
          || attempt !== readAttempt) { return; }
      state.busy = false;
      if (!reply || !reply.ok) {
        // A failed reread is not a reason to eject: after Save the draft
        // may include newer edits, and an explicit Reload has only agreed
        // to discard if its replacement arrives. Routing away here would
        // lose work through the error path instead of the clobber below.
        // The lock is a realistic cause and clears on its own.
        //
        // `dirty` is deliberately not touched: it already describes the
        // retained document, whether just saved or still awaiting Save.
        if (mode === 'switch') {
          // Keep the old document after a failed switch. The select changed
          // before the request was sent, so put it back on the only document
          // still represented by state rather than leaving the two disagreeing.
          WM.el('fm-account').value = selectedAccountPath;
          paintCommit();
          WM.confirm('Formations',
                     (reply && reply.error) || 'The file could not be read.');
          return;
        }
        if (protect) {
          saveStatus((reply && reply.error) || 'The file could not be re-read.');
          paintCommit();
          WM.confirm('Formations',
                     (reply && reply.error) || 'The file could not be re-read.');
          return;
        }
        // Back to Profiles FIRST, so the answer is read over the screen
        // that offered the button rather than over an empty editor.
        //
        // WM.confirm, because it is the only dialog the page owns and it
        // has no OK-only face (panel.js hides Cancel for kind 'info',
        // which only Python can raise). Both answers mean the same thing
        // here -- you are already back on Profiles -- so the reply is
        // deliberately not read.
        WM.route('evesettings');
        WM.confirm('Formations',
                   (reply && reply.error) || 'The file could not be read.');
        return;
      }
      // The editor stays live while an account read is in flight. If an
      // edit lands before a switch answer, retain the document it changed
      // and restore its account choice rather than painting another account
      // over it. The save reload has the same revision guard below, but its
      // selector already represents the document on screen.
      if (mode === 'switch' && revision !== startedAt) {
        state.dirty = true;
        WM.el('fm-account').value = selectedAccountPath;
        paintCommit();
        return;
      }
      // The edit on screen wins over the answer to a question asked
      // before it existed. Nothing is written and nothing is discarded:
      // the list keeps its `id: null` for any new formation, so the next
      // save re-mints exactly once more and the reload after THAT one
      // settles the ids. An id churned once is the price of never losing
      // a keystroke, and it is the same trade formationsDone makes.
      if (protect && revision !== startedAt) {
        state.dirty = true;
        paintCommit();
        return;
      }
      state.path = reply.path;
      state.contentRevision = reply.content_revision;
      if (mode !== 'reload') { saveStatus(''); }
      selectedAccountPath = path;
      lastSuccessfulPath = path;
      state.formations = reply.formations.map(fromMeters);
      sharingLimits = reply.sharing_limits;
      copySelection = [];
      // A post-save reread can replace the document without a new generation.
      // No export still preparing the prior document may reach the clipboard.
      copyAttempt += 1;
      setShareStatus('', false);
      state.selected = 0;
      if (typeof keepIndex === 'number' && state.formations.length) {
        state.selected = Math.min(Math.max(0, keepIndex),
                                  state.formations.length - 1);
      }
      state.dirty = false;
      savingAt = -1;
      renderAccounts(selectedAccountPath);
      renderAll();
    });
  }

  function save() {
    if (screenshotFixture) return;
    if (importReview || state.busy || !state.path || !state.contentRevision) { return; }
    var request = {
      id: pageSession + ':' + loadGeneration + ':' + (++saveSequence),
      path: state.path, generation: loadGeneration, revision: revision
    };
    pendingSave = request;
    state.busy = true;
    savingAt = request.revision;
    saveStatus('');
    paintCommit();
    WM.send('eve_settings_save_formations', request.path,
            state.formations.map(toMeters), state.contentRevision,
            request.id).then(function (accepted) {
      // Completion can beat this bool reply, even starting a reread or a
      // second save. Only the request still pending may release its busy state.
      if (!accepted && pendingSave === request
          && request.generation === loadGeneration
          && WM.current_route === 'formations') {
        pendingSave = null;
        state.busy = false;
        saveStatus('The save could not be started. Your edits are still here.');
        paintCommit();
      }
    });
  }

  function setShareStatus(text, isError) {
    var status = WM.el('fm-share-status');
    status.textContent = text;
    status.className = isError ? 'hint err' : 'hint';
  }

  function paintSharing() {
    WM.setEnabled('fm-paste', !importReview && !state.busy && !!state.path && !!sharingLimits);
    WM.el('fm-copy').textContent = 'Copy selected (' + copySelection.length + ')';
    WM.setEnabled('fm-copy', !state.busy && copySelection.length > 0);
    WM.el('fm-share-hint').textContent = sharingLimits
      ? 'Up to ' + sharingLimits.max_formations + ' formations, '
        + (sharingLimits.max_bytes / 1024) + ' KiB.'
      : '';
  }

  function copySelected() {
    if (screenshotFixture) return;
    if (state.busy || !copySelection.length) { return; }
    var attempt = ++copyAttempt, generation = loadGeneration;
    var items = state.formations.filter(function (f) {
      return copySelection.indexOf(f) !== -1;
    }).map(toMeters);
    function stillCurrent() {
      return generation === loadGeneration && attempt === copyAttempt
        && WM.current_route === 'formations';
    }
    setShareStatus('Preparing formations…', false);
    WM.send('eve_settings_export_formations', items).then(function (reply) {
      if (!stillCurrent()) { return; }
      if (!reply || !reply.ok) {
        setShareStatus((reply && reply.error) || 'Could not prepare formations.', true);
        return;
      }
      // Once this OS call begins it cannot be revoked. Ignore stale outcomes
      // rather than reporting another account's copy as this account's success.
      try {
        navigator.clipboard.writeText(reply.text).then(function () {
          if (stillCurrent()) { setShareStatus('Formations copied.', false); }
        }, function () {
          if (stillCurrent()) {
            setShareStatus('Could not copy formations to the clipboard.', true);
          }
        });
      } catch (error) {
        if (stillCurrent()) {
          setShareStatus('Could not copy formations to the clipboard.', true);
        }
      }
    }, function () {
      if (stillCurrent()) { setShareStatus('Could not prepare formations.', true); }
    });
  }

  function saveStatus(text) {
    WM.el('fm-save-status').textContent = text;
  }

  /* ---- inline import review: no account mutation until explicit Save ---- */
  function setImportStatus(text, isError) {
    var status = WM.el('fm-import-status');
    status.textContent = text;
    status.className = isError ? 'hint err' : 'hint';
  }

  function importTextProblem(text) {
    // TextEncoder counts UTF-8 bytes, not JS UTF-16 units. Python rejects bad
    // Unicode too; this is immediate size feedback, not a second parser.
    if (sharingLimits && new TextEncoder().encode(text).length > sharingLimits.max_bytes) {
      return 'Shared text exceeds ' + sharingLimits.max_bytes
        + ' UTF-8 bytes. Copy fewer formations.';
    }
    return '';
  }

  function paintImportButtons() {
    var review = importReview;
    WM.setEnabled('fm-import-review', !!review && !review.pending
      && !!review.text.trim() && !importTextProblem(review.text));
    WM.setEnabled('fm-import-add', !!review && !review.pending
      && review.candidates.length > 0 && !review.conflicts.length);
  }

  function openImportReview() {
    if (importReview || state.busy || !state.path || !sharingLimits) { return; }
    importAttempt += 1;
    importReview = { text: '', candidates: [], selected: 0, conflicts: [],
      path: state.path, generation: loadGeneration, request: null, pending: '' };
    WM.el('fm-import-text').value = '';
    WM.el('fm-import-list').textContent = '';
    WM.el('fm-editor-work').hidden = true;
    WM.el('fm-commit').hidden = true;
    WM.el('fm-import-work').hidden = false;
    WM.el('fm-import-commit').hidden = false;
    setImportStatus('Paste shared text, then choose Review. Nothing is saved until Save formations.', false);
    renderImportPreview(); paintImportButtons(); paintCommit();
    WM.el('fm-import-text').focus();
  }

  function closeImportReview(restoreInvokerFocus) {
    importAttempt += 1;
    importReview = null;
    WM.el('fm-import-text').value = '';
    WM.el('fm-import-list').textContent = '';
    WM.el('fm-import-preview').textContent = '';
    WM.el('fm-import-work').hidden = true;
    WM.el('fm-import-commit').hidden = true;
    WM.el('fm-editor-work').hidden = false;
    WM.el('fm-commit').hidden = false;
    setImportStatus('', false);
    paintImportButtons(); paintCommit(); renderPreview();
    // Do not rebuild the ordinary pane: Cancel must preserve raw input/focus
    // targets as well as committed draft values and sharing ticks.
    if (restoreInvokerFocus) { WM.el('fm-paste').focus(); }
  }

  function existingNames() {
    return state.formations.map(function (f) { return f.name; });
  }

  function importReplyIsCurrent(review, request) {
    if (importReview !== review || review.request !== request
        || importAttempt !== request.attempt || WM.current_route !== 'formations'
        || review.path !== state.path || review.generation !== loadGeneration) { return false; }
    if (request.revision !== revision) {
      importAttempt += 1;
      review.pending = '';
      setImportStatus('The draft changed while checking. Review or Add again.', true);
      paintImportButtons();
      return false;
    }
    return true;
  }

  function renderImportPreview() {
    var f = importReview && importReview.candidates[importReview.selected];
    renderFormationPreview(WM.el('fm-import-preview'), f ? fromSharedMeters(f) : null);
  }

  function paintImportRows() {
    var review = importReview;
    if (!review) { return; }
    Array.prototype.forEach.call(WM.el('fm-import-list').children, function (row, i) {
      var conflict = review.conflicts.indexOf(i) !== -1;
      var name = review.candidates[i].name;
      row.querySelector('.hint').textContent = conflict
        ? 'This account already has this name. Choose a different name.' : '';
      row.querySelector('input').setAttribute('aria-invalid', conflict ? 'true' : 'false');
      row.querySelector('button').setAttribute('aria-label', 'Preview ' + name);
      row.querySelector('button').setAttribute('aria-pressed', i === review.selected ? 'true' : 'false');
    });
  }

  function renderImportList() {
    var box = WM.el('fm-import-list'), review = importReview;
    box.textContent = '';
    review.candidates.forEach(function (f, i) {
      var row = WM.make('div', 'fm-import-row');
      var input = document.createElement('input');
      input.type = 'text'; input.className = 'field'; input.value = f.name;
      input.id = 'fm-import-name-' + i;
      input.setAttribute('aria-describedby', 'fm-import-conflict-' + i);
      var label = WM.make('label', 'lab', 'Formation ' + (i + 1) + ' name ('
        + f.probes.length + (f.probes.length === 1 ? ' probe)' : ' probes)'));
      label.setAttribute('for', input.id);
      var preview = WM.make('button', 'btn', 'Preview');
      preview.type = 'button';
      var conflict = WM.make('span', 'hint err');
      conflict.id = 'fm-import-conflict-' + i;
      row.appendChild(label); row.appendChild(input); row.appendChild(preview); row.appendChild(conflict);
      input.addEventListener('input', function () {
        if (importReview !== review) { return; }
        f.name = input.value;
        importAttempt += 1; review.pending = ''; review.conflicts = [];
        setImportStatus('Names changed. Add formations checks every name again.', false);
        // Paint in place so typing and the following native click keep focus.
        paintImportRows(); paintImportButtons();
      });
      preview.addEventListener('click', function () {
        if (importReview !== review) { return; }
        review.selected = i; paintImportRows(); renderImportPreview();
      });
      box.appendChild(row);
    });
    paintImportRows(); renderImportPreview();
  }

  function reviewImport() {
    var review = importReview;
    if (!review || review.pending || !review.text.trim() || importTextProblem(review.text)) { return; }
    var request = { attempt: ++importAttempt, revision: revision };
    review.request = request;
    review.pending = 'review'; review.candidates = []; review.conflicts = [];
    renderImportList(); paintImportButtons(); setImportStatus('Reviewing formations…', false);
    var pending = screenshotFixture ? Promise.resolve(JSON.parse(JSON.stringify(screenshotFixture.import_reply)))
      : WM.send('eve_settings_parse_formations', review.text, existingNames());
    pending.then(function (reply) {
      if (!importReplyIsCurrent(review, request)) { return; }
      review.pending = '';
      if (!reply || !reply.ok) {
        setImportStatus((reply && reply.error) || 'Could not review formations.', true);
      } else {
        review.candidates = reply.formations; review.conflicts = reply.conflicts; review.selected = 0;
        renderImportList();
        setImportStatus(reply.conflicts.length ? 'Resolve the marked names before adding.'
          : 'Review the names and previews, then Add formations to your draft.', !!reply.conflicts.length);
      }
      paintImportButtons();
    }, function () {
      if (!importReplyIsCurrent(review, request)) { return; }
      review.pending = ''; setImportStatus('Could not review formations. Try Review again.', true);
      paintImportButtons();
    });
  }

  function addImport() {
    if (screenshotFixture) return;
    var review = importReview;
    if (!review || review.pending || !review.candidates.length || review.conflicts.length) { return; }
    var request = { attempt: ++importAttempt, revision: revision };
    review.request = request;
    // Deep snapshot: later name edits must not alter an in-flight request.
    var items = review.candidates.map(function (f) {
      return { id: null, name: f.name, probes: f.probes.map(function (p) {
        return { x: p.x, y: p.y, z: p.z, range: p.range };
      }) };
    });
    review.pending = 'add'; paintImportButtons(); setImportStatus('Checking formations…', false);
    WM.send('eve_settings_validate_formation_import', items, existingNames()).then(function (reply) {
      if (!importReplyIsCurrent(review, request) || review.pending !== 'add') { return; }
      review.pending = '';
      if (!reply || !reply.ok || reply.conflicts.length) {
        review.conflicts = reply && reply.ok ? reply.conflicts : [];
        paintImportRows(); paintImportButtons();
        setImportStatus(reply && reply.ok ? 'Resolve the marked names before adding.'
          : (reply && reply.error) || 'Could not validate formations.', true);
        return;
      }
      // Convert the whole batch before the one mutation. No IDs or file writes
      // happen here; the existing explicit Save path alone owns those effects.
      var firstAdded = state.formations.length;
      var additions = reply.formations.map(fromSharedMeters);
      state.formations = state.formations.concat(additions);
      state.selected = firstAdded;
      markDirty();
      closeImportReview(false);
      renderAll();
      WM.el('fm-list').children[firstAdded].querySelector('.fm-item').focus();
    }, function () {
      if (!importReplyIsCurrent(review, request)) { return; }
      review.pending = ''; setImportStatus('Could not validate formations. Try Add again.', true);
      paintImportButtons();
    });
  }

  function reload() {
    if (state.busy || !state.path) { return; }
    var generation = loadGeneration, path = selectedAccountPath;
    function readAgain() {
      if (WM.current_route !== 'formations' || generation !== loadGeneration
          || path !== selectedAccountPath || state.busy) { return; }
      // Confirming a discard is provisional until a read actually succeeds.
      loadGeneration += 1;
      load(path, 'explicit-reload', state.selected, true);
    }
    if (!state.dirty) { readAgain(); return; }
    WM.confirm('Reload formations?',
               'Discard your unsaved formation edits and read this account again?',
               { destructive: true }).then(function (yes) {
      if (yes) { readAgain(); }
    });
  }

  // onEveSettingsDone has ONE owner, evesettings.js: WM.handle assigns
  // window[name] outright, so a second registration here would silently
  // replace the Profiles handler and leave copy, backup and restore stuck
  // busy for the rest of the session. Profiles forwards the push here
  // instead. test_page_conventions.py pins both halves.
  WM.formationsDone = function (payload) {
    if (!pendingSave || !payload || payload.operation !== 'formations_save'
        || payload.request_id !== pendingSave.id || payload.path !== pendingSave.path
        || state.path !== pendingSave.path || pendingSave.generation !== loadGeneration
        || WM.current_route !== 'formations') { return; }
    savingAt = pendingSave.revision;
    pendingSave = null;
    state.busy = false;
    if (!payload.ok) {
      saveStatus(payload.error || 'Formations were not saved. Your edits are still here.');
      paintCommit();
      return;
    }
    // The committed bytes become our baseline even when newer edits make
    // reloading unsafe. Otherwise the next save would conflict with our own.
    state.contentRevision = payload.content_revision;
    saveStatus(payload.warning || 'Formations saved.');
    // An edit landed after the send, and the push says nothing about it.
    // Keeping it beats reloading over it: a reload here would throw away
    // work the user can see on screen, while the cost of NOT reloading is
    // that a brand-new formation keeps id null for one more save and gets
    // re-minted (below). Losing an edit is worse than churning an id, and
    // the next clean save reloads and settles it.
    if (revision !== savingAt) { paintCommit(); return; }
    state.dirty = false;
    // Re-read, and this is not a refresh for its own sake. A new
    // formation is sent with id null and Python MINTS one at write time;
    // without reading it back the page still holds null, so the next save
    // mints a second id and write_formations drops the first -- which
    // repoints the client's selectedFormationID at whatever is now the
    // head of the table. That is exactly the churn ids exist to prevent,
    // and this file's header claims not to cause.
    load(selectedAccountPath, 'reload', state.selected, true);
  };

  /* ---- rendering ---- */
  function renderAll() {
    renderList(); renderPane(); renderPreview(); renderImportPreview(); paintCommit();
  }

  function renderList() {
    var box = WM.el('fm-list');
    box.textContent = '';
    if (!state.formations.length) {
      box.appendChild(WM.make('div', 'empty', 'No formations yet.'));
      return;
    }
    state.formations.forEach(function (f, i) {
      var row = WM.make('div', 'fm-list-row');
      var input = document.createElement('input');
      input.type = 'checkbox';
      var check = WM.make('label', 'check');
      check.appendChild(input);
      check.appendChild(WM.make('span', 'box'));
      input.checked = copySelection.indexOf(f) !== -1;
      input.addEventListener('change', function () {
        var selected = copySelection.indexOf(f);
        if (input.checked && selected === -1) { copySelection.push(f); }
        else if (!input.checked && selected !== -1) { copySelection.splice(selected, 1); }
        // Never rebuild the pane for a sharing tick: it can hold unblurred input.
        paintSharing();
      });
      row.appendChild(check);
      // .fm-item, NOT .rail-item. The two share one rule in style.css
      // because they are one affordance, but app.js sweeps every
      // `.rail-item` on the page when a Settings section changes and
      // toggles `active` from its data-section -- which would quietly
      // un-select whichever formation is open. Same treatment, different
      // name, so that sweep cannot reach here.
      var item = WM.make('button', 'fm-item' + (i === state.selected ? ' active' : ''));
      item.type = 'button';
      item.addEventListener('click', function () {
        state.selected = i;
        renderAll();
      });
      row.appendChild(item);
      paintListName(row, f);
      box.appendChild(row);
    });
  }

  function paintListName(row, f) {
    var name = f.name || 'Unnamed';
    row.querySelector('.fm-item').textContent = name;
    row.querySelector('input').setAttribute('aria-label', 'Select ' + name + ' for sharing');
  }

  function renderPane() {
    var f = current();
    WM.el('fm-name').value = f ? f.name : '';
    WM.setEnabled('fm-name', !!f);
    WM.setEnabled('fm-delete', !!f);
    WM.setEnabled('fm-add-probe', !!f && f.probes.length < MAX_PROBES);
    renderProbes();
  }

  function rangeSelect(value, onChange, label) {
    var sel = document.createElement('select'), opts = RANGES.slice();
    sel.className = 'field';
    sel.setAttribute('aria-label', label);
    // Keep an out-of-range value from an existing file SELECTABLE rather
    // than rewriting it: the design doc's format note is explicit that a
    // value the editor does not offer is still the user's.
    if (opts.indexOf(value) === -1 && isFinite(value)) {
      opts.push(value);
      opts.sort(function (a, b) { return a - b; });
    }
    opts.forEach(function (r) {
      var o = document.createElement('option');
      o.value = String(r);
      o.textContent = r + ' AU';
      sel.appendChild(o);
    });
    sel.value = String(value);
    sel.addEventListener('change', function () { onChange(Number(sel.value)); });
    return sel;
  }

  function renderProbes() {
    var grid = WM.el('fm-probes'), f = current();
    grid.textContent = '';
    if (!f) {
      WM.setEnabled('fm-all-range', false);
      paintBalance();
      return;
    }
    ['#', 'West (km)', 'Up (km)', 'North (km)', 'Range', ''].forEach(function (h) {
      grid.appendChild(WM.make('div', 'fm-head', h));
    });
    f.probes.forEach(function (p, i) {
      grid.appendChild(WM.make('div', 'fm-idx', String(i + 1)));
      ['x', 'y', 'z'].forEach(function (axis) {
        var input = document.createElement('input');
        input.type = 'number';
        input.className = 'field';
        input.step = 'any';
        input.value = String(p[axis]);
        input.setAttribute(
          'aria-label',
          'Probe ' + (i + 1) + ' ' + AXIS_LABELS[axis] + ' km'
        );
        // Protect the raw field through both async save windows, even when
        // a partial sign/exponent has no numeric value yet. Only `change`
        // below updates the model; input activity must not coerce it to zero.
        input.addEventListener('input', markDirty);
        // `change`, so a half-typed value never commits: DESIGN.md's rule
        // for free text is Enter or an explicit button, never blur alone,
        // and a number input fires change on both.
        input.addEventListener('change', function () {
          var n = Number(input.value);
          if (input.value !== '' && isFinite(n)) {
            p[axis] = n;
            markDirty();
            // paintBalance, NOT renderProbes: rebuilding the grid from
            // inside one of its own inputs' change handler destroys the
            // element the event is still running on and drops the focus
            // the user was about to tab out of.
            paintBalance();
            renderPreview();
          } else {
            input.value = String(p[axis]);
          }
        });
        grid.appendChild(input);
      });
      grid.appendChild(rangeSelect(p.range, function (r) {
        p.range = r;
        markDirty();
      }, 'Probe ' + (i + 1) + ' range'));
      var rm = WM.make('button', 'linkbtn', 'Remove');
      rm.type = 'button';
      rm.addEventListener('click', function () {
        f.probes.splice(i, 1);
        markDirty();
        renderPane();
        renderPreview();
      });
      grid.appendChild(rm);
    });
    // An ACTION, not a value: the first option is a placeholder so the
    // control never states a range the formation does not have, and it
    // returns to the placeholder after applying one.
    var all = WM.el('fm-all-range');
    all.textContent = '';
    var head = document.createElement('option');
    head.value = '';
    head.textContent = 'Set every range…';
    all.appendChild(head);
    RANGES.forEach(function (r) {
      var o = document.createElement('option');
      o.value = String(r);
      o.textContent = 'All ' + r + ' AU';
      all.appendChild(o);
    });
    all.value = '';
    WM.setEnabled('fm-all-range', !!f.probes.length);
    paintBalance();
  }

  // The one line on this screen that is about what the CLIENT will do
  // rather than about what is drawn: EVE re-centres a launched formation
  // on its centroid, so a formation whose centroid is not the ship lands
  // somewhere other than where it was drawn. Split out of renderProbes
  // because a coordinate edit changes it without changing the grid.
  function paintBalance() {
    var f = current();
    WM.el('fm-balance-note').textContent = f && f.probes.length
      ? (balanced(f)
          ? 'Launches as drawn.'
          : 'Launch shifts every probe by ' + formatKm(shift(f)) + '.')
      : '';
    WM.setEnabled('fm-balance', !!(f && f.probes.length && !balanced(f)));
  }

  function formatKm(km) {
    var AU_KM = AU / KM;
    return km >= AU_KM / 100
      ? (km / AU_KM).toFixed(2) + ' AU'
      : Math.round(km).toLocaleString() + ' km';
  }

  /* ---- SVG preview: yaw/pitch projection, equatorial rings, tethers ----
     Hand-rolled, the way eve-wrench's is: forty lines of trigonometry, no
     library, no build step -- which is the only shape wingman/web/ has
     room for. */
  var SVG = 'http://www.w3.org/2000/svg';
  function el(tag, attrs) {
    var node = document.createElementNS(SVG, tag), k;
    for (k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) {
        node.setAttribute(k, String(attrs[k]));
      }
    }
    return node;
  }
  function project(x, y, z) {
    var x1 = x * Math.cos(yaw) + z * Math.sin(yaw);
    var z1 = -x * Math.sin(yaw) + z * Math.cos(yaw);
    var y1 = y * Math.cos(pitch) - z1 * Math.sin(pitch);
    var depth = y * Math.sin(pitch) + z1 * Math.cos(pitch);
    return { sx: x1, sy: -y1, depth: depth };
  }
  function niceStep(target) {
    var pow = Math.pow(10, Math.floor(Math.log(target) / Math.LN10));
    var mults = [1, 2, 2.5, 5, 10], i;
    for (i = 0; i < mults.length; i++) {
      if (pow * mults[i] >= target) { return pow * mults[i]; }
    }
    return pow * 10;
  }

  // The viewBox is set to the element's own CSS pixel size on every draw,
  // rather than being a fixed square the browser then scales. One user
  // unit is one CSS pixel, so a stroke of 1 is a hairline and the ring
  // labels can take --fs-label from the stylesheet and mean it. A fixed
  // viewBox scaled 9px type down to about 5px at the 840x625 floor, which
  // is the whole reason this is computed rather than declared.
  var MARGIN = 26;

  function renderPreview() {
    renderFormationPreview(WM.el('fm-preview'), current());
  }

  function renderFormationPreview(svg, f) {
    var rect = svg.getBoundingClientRect();
    var w = Math.round(rect.width), h = Math.round(rect.height);
    var cx = w / 2, cy = h / 2;
    var extent = 1, scale, step, i, r, a, pts, p, c, items, label;
    svg.textContent = '';
    // Off-route (or mid-layout) the element has no box, and every
    // coordinate below would be NaN.
    if (!f || w < 2 || h < 2) { return; }
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    // A formation with no probes left has no scale, and drawing rings
    // against the fallback extent of 1 km printed `1 km`, `1 km`, `2 km`
    // -- two rings claiming the same distance. The ship alone is the
    // honest picture of it, and #fm-dirty is what says how to fix it.
    if (!f.probes.length) {
      svg.appendChild(el('circle', { cx: cx, cy: cy, r: 3, 'class': 'fm-ship' }));
      return;
    }
    f.probes.forEach(function (q) {
      extent = Math.max(extent, Math.abs(q.x), Math.abs(q.y), Math.abs(q.z));
    });
    step = niceStep(extent / 3);
    // The outer ring, not the outermost probe, decides the scale: niceStep
    // rounds up, so three rings can reach half again as far as the widest
    // probe and the outer one would be drawn outside the box.
    scale = Math.max(10, Math.min(w, h) / 2 - MARGIN) / Math.max(extent, step * 3);
    for (i = 1; i <= 3; i++) {
      r = step * i;
      pts = [];
      for (a = 0; a < 72; a++) {
        p = project(r * Math.cos(a / 72 * Math.PI * 2), 0,
                    r * Math.sin(a / 72 * Math.PI * 2));
        pts.push((cx + p.sx * scale).toFixed(1) + ','
                 + (cy + p.sy * scale).toFixed(1));
      }
      svg.appendChild(el('polygon', { points: pts.join(' '), 'class': 'fm-ring' }));
      // At the ring's widest point, end-anchored so the text lands INSIDE
      // the ring it names, and stepped down by a line each so the three do
      // not pile up: the rings flatten with pitch, and at a shallow one
      // three labels on one horizontal line overlap each other.
      label = el('text', { x: cx + r * scale - 4, y: cy + (i - 2) * 13,
                           'class': 'fm-ring-label' });
      label.textContent = formatKm(r);
      svg.appendChild(label);
    }
    // Painted back to front, so a probe in front of another overlaps it
    // rather than the draw order deciding at random.
    items = f.probes.map(function (q, idx) {
      var top = project(q.x, q.y, q.z), base = project(q.x, 0, q.z);
      return { idx: idx, x: cx + top.sx * scale, y: cy + top.sy * scale,
               depth: top.depth,
               bx: cx + base.sx * scale, by: cy + base.sy * scale };
    }).sort(function (m, n) { return m.depth - n.depth; });
    items.forEach(function (it) {
      svg.appendChild(el('line', { x1: it.bx, y1: it.by, x2: it.x, y2: it.y,
                                   'class': 'fm-tether' }));
      svg.appendChild(el('circle', { cx: it.x, cy: it.y, r: 5,
                                     'class': 'fm-probe' }));
      var t = el('text', { x: it.x + 7, y: it.y - 7, 'class': 'fm-probe-label' });
      t.textContent = String(it.idx + 1);
      svg.appendChild(t);
    });
    svg.appendChild(el('circle', { cx: cx, cy: cy, r: 3, 'class': 'fm-ship' }));
    // The centroid is drawn only when it is off the ship, because that is
    // the one state it explains: where the formation will actually be
    // centred once launched. Balance is the control that closes it.
    if (!balanced(f)) {
      c = centroid(f);
      p = project(c.x, c.y, c.z);
      svg.appendChild(el('circle', { cx: cx + p.sx * scale, cy: cy + p.sy * scale,
                                     r: 4, 'class': 'fm-centroid' }));
    }
  }

  // The first reason this list cannot be written, or '' if it can.
  //
  // These are formations.py's own rules (validate), restated for ONE
  // purpose: to keep Save from sending a document Python will refuse
  // whole. The editor could build all three states with no signal at all
  // -- an empty name after trim, two formations casefolding to the same
  // name, a formation whose last probe was removed -- and a refusal
  // discards the entire save, not the offending formation. Python stays
  // the authority (it checks finiteness and range > 0 as well, which the
  // controls here cannot produce); this is the half the user needs
  // BEFORE the click, on the screen holding the mistake.
  //
  // Order matches validate(): unnamed, duplicate, empty. First one wins,
  // because a line naming three problems is a paragraph.
  function problem() {
    var seen = {}, why = '', key, i, f;
    for (i = 0; i < state.formations.length; i++) {
      f = state.formations[i];
      // 'Unnamed formation' is what the rail already paints for this one,
      // so the line names it the way the screen does.
      if (!f.name) { return 'Unnamed formation: needs a name'; }
      key = f.name.toLowerCase();
      if (Object.prototype.hasOwnProperty.call(seen, key)) {
        return f.name + ': name used twice';
      }
      seen[key] = true;
      if (!why && !f.probes.length) { why = f.name + ': needs a probe'; }
    }
    return why;
  }

  // The first index no formation is using, so deleting one of three and
  // adding another cannot mint a second `Formation 3` -- a duplicate name
  // Python refuses, produced by the button whose whole job is to make a
  // valid formation. Bounded by length + 1, where an unused index always
  // exists.
  function nextName() {
    var used = {}, i, candidate;
    state.formations.forEach(function (f) {
      used[(f.name || '').toLowerCase()] = true;
    });
    for (i = 1; i <= state.formations.length + 1; i++) {
      candidate = 'Formation ' + i;
      if (!Object.prototype.hasOwnProperty.call(used, candidate.toLowerCase())) {
        return candidate;
      }
    }
    return 'Formation ' + (state.formations.length + 1);
  }

  function paintCommit() {
    // A pending or failed account switch still displays the old document.
    // Name that document here, never the select's unacknowledged choice.
    var account = accountChoices.filter(function (choice) {
      return choice.path === selectedAccountPath;
    })[0];
    WM.el('fm-account-context').textContent = account && state.path
      ? 'Account: ' + account.name : '';
    var why = state.busy ? '' : problem();
    WM.setEnabled('fm-save', !importReview && state.dirty && !state.busy && !!state.contentRevision && !why);
    WM.setEnabled('fm-reload', !!state.path && !state.busy);
    WM.el('fm-dirty').textContent = state.busy
      ? (pendingSave ? 'Saving…' : 'Loading…')
      : (why || (state.dirty ? 'Unsaved changes' : ''));
    // .hint is the faintest tone the sheet has, which is right for
    // `Unsaved changes` and wrong for the one line explaining why the
    // button beside it is dead -- the same inversion the bookmark
    // engine's "Stopped" message was found in (style.css, .hint.err).
    // One class toggle over one element; no second accent, no dialog.
    WM.el('fm-dirty').className = why ? 'hint err' : 'hint';
    WM.setEnabled('fm-add', !importReview && !state.busy);
    WM.setEnabled('fm-account', !state.busy && accountChoices.length > 0);
    paintSharing();
  }

  /* ---- wiring ---- */
  function wire() {
    var svg = WM.el('fm-preview'), preset = WM.el('fm-preset');
    PRESETS.forEach(function (pr) {
      var o = document.createElement('option');
      o.value = pr.id;
      o.textContent = pr.label;
      preset.appendChild(o);
    });

    WM.el('fm-back').addEventListener('click', function () {
      var generation = loadGeneration;
      if (!state.dirty) { WM.route('evesettings'); return; }
      WM.confirm('Discard changes?',
                 'Your formation edits have not been saved.',
                 { destructive: true }).then(function (yes) {
        if (generation !== loadGeneration || WM.current_route !== 'formations') { return; }
        if (yes) { state.dirty = false; WM.route('evesettings'); }
      });
    });

    WM.el('fm-add').addEventListener('click', function () {
      if (importReview || state.busy) { return; }
      var pr = PRESETS.filter(function (x) {
        return x.id === preset.value;
      })[0] || PRESETS[0];
      state.formations.push({
        id: null,
        name: nextName(),
        probes: pr.probes()
      });
      state.selected = state.formations.length - 1;
      markDirty();
      renderAll();
    });

    WM.el('fm-delete').addEventListener('click', function () {
      var f = current(), list = state.formations, generation = loadGeneration;
      if (!f) { return; }
      // "when you save", because nothing has been written yet: the delete
      // is an edit to the list this screen holds, and Save is the only
      // thing that touches the file.
      WM.confirm('Delete formation?',
                 '"' + f.name + '" is removed when you save.',
                 { destructive: true }).then(function (yes) {
        if (!yes || generation !== loadGeneration
            || WM.current_route !== 'formations') { return; }
        // A read started before this dialog can replace the document without
        // another generation change. Neither a retained index nor a reused ID
        // authorizes deleting its replacement; require the same selected object.
        if (list !== state.formations || current() !== f) {
          saveStatus('The formation changed while confirming. Nothing was deleted. Choose Delete again.');
          return;
        }
        var removed = state.formations.splice(state.selected, 1)[0];
        var selected = copySelection.indexOf(removed);
        if (selected !== -1) { copySelection.splice(selected, 1); }
        state.selected = Math.max(0, state.selected - 1);
        markDirty();
        renderAll();
      });
    });

    // A focused draft must outlive a completion/reread before blur fires.
    // Counting activity leaves the existing change-time model update intact.
    WM.el('fm-name').addEventListener('input', function () {
      if (current()) { markDirty(); }
    });
    WM.el('fm-name').addEventListener('change', function () {
      var f = current();
      if (f) {
        f.name = WM.el('fm-name').value.trim();
        markDirty();
        // Blur can commit the name between pointer-down and a sharing click.
        // Keep those controls connected so the native click/focus can finish.
        paintListName(WM.el('fm-list').children[state.selected], f);
      }
    });

    WM.el('fm-add-probe').addEventListener('click', function () {
      var f = current();
      if (f && f.probes.length < MAX_PROBES) {
        f.probes.push(probe(0, 0, 0));
        markDirty();
        renderPane();
        renderPreview();
      }
    });

    WM.el('fm-all-range').addEventListener('change', function () {
      var f = current(), r = Number(WM.el('fm-all-range').value);
      if (!f || WM.el('fm-all-range').value === '' || !isFinite(r)) { return; }
      f.probes.forEach(function (p) { p.range = r; });
      markDirty();
      renderProbes();
    });

    WM.el('fm-balance').addEventListener('click', balance);
    WM.el('fm-save').addEventListener('click', save);
    WM.el('fm-reload').addEventListener('click', reload);
    WM.el('fm-copy').addEventListener('click', copySelected);
    WM.el('fm-paste').addEventListener('click', openImportReview);
    WM.el('fm-import-review').addEventListener('click', reviewImport);
    WM.el('fm-import-add').addEventListener('click', addImport);
    WM.el('fm-import-cancel').addEventListener('click', function () { closeImportReview(true); });
    WM.el('fm-import-text').addEventListener('input', function () {
      if (!importReview) { return; }
      importAttempt += 1;
      importReview.text = WM.el('fm-import-text').value;
      importReview.pending = ''; importReview.candidates = []; importReview.conflicts = [];
      renderImportList(); paintImportButtons();
      var why = importTextProblem(importReview.text);
      setImportStatus(why || 'Text changed. Choose Review to check it.', !!why);
    });

    WM.el('fm-account').addEventListener('change', function () {
      var nextPath = WM.el('fm-account').value, generation = loadGeneration;
      if (!nextPath || nextPath === selectedAccountPath || state.busy) return;
      if (!state.dirty) {
        load(nextPath, 'switch');
        return;
      }
      WM.confirm('Discard changes?',
                 'Your formation edits have not been saved.',
                 { destructive: true }).then(function (yes) {
        if (generation !== loadGeneration || WM.current_route !== 'formations'
            || state.busy) { return; }
        if (yes) {
          load(nextPath, 'switch');
        } else {
          WM.el('fm-account').value = selectedAccountPath;
        }
      });
    });

    [svg, WM.el('fm-import-preview')].forEach(function (preview) {
      preview.addEventListener('mousedown', function (e) {
        e.preventDefault();
        dragging = true;
        lastX = e.clientX;
        lastY = e.clientY;
      });
    });
    window.addEventListener('mouseup', function () { dragging = false; });
    window.addEventListener('mousemove', function (e) {
      if (!dragging) { return; }
      yaw += (e.clientX - lastX) * 0.01;
      pitch = Math.max(-Math.PI / 2,
                       Math.min(Math.PI / 2, pitch + (e.clientY - lastY) * 0.01));
      lastX = e.clientX;
      lastY = e.clientY;
      renderPreview(); renderImportPreview();
    });

    // The viewBox is the element's own pixel size, so a resize changes
    // every coordinate in the drawing.
    window.addEventListener('resize', function () {
      if (WM.current_route === 'formations') { renderPreview(); renderImportPreview(); }
    });

    // Leaving invalidates outstanding reads, saves and confirmations. The
    // drag listeners are also on `window`: a pointer released elsewhere
    // must not leave the preview spinning under the next screen.
    document.addEventListener('wm:route', function (event) {
      if (event.detail !== 'formations') {
        WM.formationsScreenshot(null);
        closeImportReview(false);
        dragging = false;
        loadGeneration += 1;
        pendingSave = null;
      }
    });
  }

  // The Profiles tool's entry point, and the only way in. Keep only the
  // account identity the editor needs: Python owns the canonical name.
  WM.openFormations = function (accounts, preferredPath) {
    loadGeneration += 1;
    pendingSave = null;
    accountChoices = (accounts || []).map(function (account) {
      return { path: account.path, name: account.name };
    });
    var path = accountPath(preferredPath);
    renderAccounts(path);
    WM.route('formations');
    load(path, 'entry');
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
}());
