/* FlyGD Wingman — the Fittings route.
 *
 * SDD task 9 of docs/superpowers/plans/2026-09-03-character-fittings.md:
 * the paged curation workspace that replaces Task 6's minimal shell.
 * Reuses Skills' established two-pane vocabulary (`.skills-rail` /
 * `.skills-main` in style.css) rather than a new idiom -- a collection
 * rail on the left, a paged, filterable fitting list with one expandable
 * detail row on the right.
 *
 * Task 10 wires the reserved Copy selected accent to an explicit additive
 * preflight. The page chooses targets and conflict names; Python owns every
 * classification, the short-lived ticket, durable intent, and one-attempt
 * write. There is no remote delete or replacement path.
 *
 * Search, collection scope, sort, and paging are backend queries
 * (fittings_state(filters)); this file never rebuilds or holds the whole
 * library. Row selection remains page-owned while it changes only the
 * render, is pruned whenever the page/filter scope changes, and crosses
 * the bridge only as current stable IDs when Python computes copy preflight.
 *
 * Every mutation (collections, metadata, membership, supersession,
 * delete, refresh) notifies through one semantic push, `onFittingsChanged`
 * -- never a second, competing state shape -- and the page re-asks for
 * whatever it is currently looking at. Deletion also retires that ID's draft.
 */
(function () {
  'use strict';
  var WM = window.WM;

  var STATE = null;        // last fittings_state() payload
  var asked = false;       // has the page asked Python for state yet
  var filters = { collection_id: 'all', search: '', ship_type_id: null, page: 1 };
  var expandedId = '';     // at most one expanded row, matching one detail fetch
  var detail = null;       // fittings_detail() payload for expandedId
  var detailSeq = 0;       // invalidates a superseded detail reply
  var detailError = '';
  var importDraft = emptyImportDraft();
  var importRequest = null; // distinct from queries: an import push can precede its receipt
  var detachedImportDraft = null;
  var locateOwner = null;
  var exportOwner = null;
  var selected = {};       // entry_id -> true, pruned to the rendered page
  var listRenderSequence = 0;
  // Only edited IDs, never a second library. The committed pair stays with its
  // draft/receipt owner across reads and off-page saves; equality is not disposal.
  // Deliberate discard and confirmed deletion still retire the whole record.
  var metadataDrafts = {};
  var metadataEditors = Object.create(null); // open/closed per ID, independent of drafts; session-only
  var progress = null;     // last refresh onFittingsProgress payload
  var copyOverlayOpen = false;
  var copyDialogGeneration = 0;
  var activeCopyTicket = '';
  var copyInvoker = null;
  var copyPhase = 'targets';
  var copyTargets = {};
  var copyPreflight = null;
  var copyPreflightRequest = null; // target/draft edits revoke only their pending review
  var copyReviewDirty = false;
  // Descriptive, detached facts only — never admission, classification or retry authority.
  var copyContext = null;
  var lastCopyContext = null;
  var copyHulls = Object.create(null); // selected entry ID -> detached hull label
  var lastCopyHulls = Object.create(null);
  var lastCopyResult = null; // session-only; reopening never reuses a copy ticket
  // Unlike the visible dialog ticket, this survives route-leave cancellation
  // until the latest submitted copy reports its terminal outcome.
  var copyHistoryOperation = null;
  var alternateNames = {};
  var alternateDrafts = {}; // Skip must not discard the text beside it on re-review
  var refreshInFlight = false; // optimistic, until the next full re-fetch confirms it
  var searchDebounce = null;
  var requestSequence = 0; // drops stale fittings_state reads
  // Non-null only while the Windows screenshot tool has explicitly injected
  // its bounded fixture over CDP. It is cleared on route leave and never set
  // by Python, startup, or a user control.
  var screenshotFixture = null;

  var RACK_ORDER = ['high', 'medium', 'low', 'rig', 'subsystem', 'service',
                     'Cargo', 'DroneBay', 'FighterBay', 'Invalid'];
  var RACK_LABEL = {
    high: 'High power', medium: 'Medium power', low: 'Low power',
    rig: 'Rigs', subsystem: 'Subsystems', service: 'Service slots',
    Cargo: 'Cargo', DroneBay: 'Drone bay', FighterBay: 'Fighter bay',
    Invalid: 'Invalid (not deployable)'
  };

  function currentFilters() {
    return {
      collection_id: filters.collection_id,
      search: filters.search,
      ship_type_id: filters.ship_type_id,
      page: filters.page
    };
  }

  function validScreenshotFixture(payload) {
    if (!payload || payload.kind !== 'fittings-screenshot-v1') return false;
    var encoded = '';
    try { encoded = JSON.stringify(payload); } catch (err) { return false; }
    if (encoded.length > 512 * 1024) return false;
    if (!Array.isArray(payload.characters) || payload.characters.length > 50) return false;
    if (!Array.isArray(payload.collections) || payload.collections.length > 205) return false;
    if (!Array.isArray(payload.entries)
        || payload.entries.length < 21 || payload.entries.length > 100) return false;
    if (!payload.details || Object.keys(payload.details).length > 100) return false;
    if (!payload.mixed_preflight
        || !Array.isArray(payload.mixed_preflight.pairs)
        || payload.mixed_preflight.pairs.length > 200) return false;
    if (!payload.copy_result || !Array.isArray(payload.copy_result.results)
        || payload.copy_result.results.length > 200) return false;
    if (payload.limit_preflight && (!Array.isArray(payload.limit_preflight.pairs)
        || payload.limit_preflight.pairs.length > 200)) return false;
    if (payload.copy_stage && ['progress', 'results'].indexOf(payload.copy_stage) === -1) return false;
    if (payload.copy_stage === 'progress' && (typeof payload.copy_progress_completed !== 'number'
        || payload.copy_progress_completed !== Math.floor(payload.copy_progress_completed)
        || payload.copy_progress_completed < 1
        || payload.copy_progress_completed > payload.copy_result.results.length)) return false;
    if (payload.clipboard) {
      var clipboard = payload.clipboard;
      var review = clipboard.review;
      if (typeof clipboard.text !== 'string' || typeof clipboard.entry_id !== 'string'
          || !review || !review.ok || typeof review.review_id !== 'string'
          || !Array.isArray(review.items) || review.items.length > 512
          || !Array.isArray(review.warnings) || review.warnings.length > 1024
          || !clipboard.receipt || !clipboard.export) return false;
    }
    return true;
  }

  function screenshotEntries() {
    return JSON.parse(JSON.stringify(screenshotFixture.entries));
  }

  function screenshotWorkspace(wanted) {
    var entries = screenshotEntries();
    if (wanted.collection_id === 'unfiled') {
      entries = entries.filter(function (entry) { return entry.is_unfiled; });
    } else if (wanted.collection_id === 'superseded') {
      entries = entries.filter(function (entry) { return !!entry.superseded_by; });
    } else if (wanted.collection_id !== 'all') {
      entries = entries.filter(function (entry) {
        return entry.collection_ids.indexOf(wanted.collection_id) !== -1;
      });
    }
    if (wanted.ship_type_id) {
      entries = entries.filter(function (entry) {
        return entry.ship_type_id === wanted.ship_type_id;
      });
    }
    var needle = (wanted.search || '').trim().toLowerCase();
    if (needle) {
      entries = entries.filter(function (entry) {
        return entry.name.toLowerCase().indexOf(needle) !== -1
          || entry.ship_name.toLowerCase().indexOf(needle) !== -1;
      });
    }
    entries.sort(function (left, right) {
      return left.name.toLowerCase().localeCompare(right.name.toLowerCase())
        || left.id.localeCompare(right.id);
    });
    var ships = {};
    screenshotEntries().forEach(function (entry) {
      ships[entry.ship_type_id] = entry.ship_name;
    });
    return {
      available: true,
      warnings: [],
      collections: JSON.parse(JSON.stringify(screenshotFixture.collections)),
      characters: JSON.parse(JSON.stringify(screenshotFixture.characters)),
      ships: Object.keys(ships).map(function (id) {
        return { type_id: parseInt(id, 10), name: ships[id] };
      }),
      rows: JSON.parse(JSON.stringify(entries)),
      total: entries.length,
      page: 1,
      page_size: 100,
      max_copy_writes: screenshotFixture.max_copy_writes,
      filters: currentFilters(),
      refreshing: false
    };
  }

  function screenshotDetail(id) {
    var value = screenshotFixture.details[id];
    return value ? JSON.parse(JSON.stringify(value)) : null;
  }

  function screenshotPreflight(entryIds, targetIds) {
    var payload = JSON.parse(JSON.stringify(screenshotFixture.mixed_preflight));
    var limit = screenshotFixture.limit_preflight;
    // Project only classified fixture pairs. Missing combinations fail closed;
    // never guess a live target's presence or manufacture a successful review.
    payload.pairs = payload.pairs.concat(limit ? limit.pairs : []).filter(function (pair) {
      return entryIds.indexOf(pair.entry_id) !== -1 && targetIds.indexOf(pair.character_id) !== -1;
    });
    payload.counts = { ready: 0, present: 0, conflict: 0, unavailable: 0 };
    payload.pairs.forEach(function (pair) { payload.counts[pair.status] += 1; });
    var missing = !entryIds.length || !targetIds.length
      || payload.pairs.length !== entryIds.length * targetIds.length;
    var overLimit = payload.counts.ready > screenshotFixture.max_copy_writes;
    payload.accepted = !missing && !overLimit;
    payload.write_count = payload.accepted ? payload.counts.ready : 0;
    payload.requires_resolution = payload.accepted && payload.pairs.some(function (pair) {
      return pair.status === 'conflict' && !pair.skipped;
    });
    payload.error = missing ? 'This selection is not covered by the screenshot fixture.'
      : overLimit ? payload.counts.ready + ' additions requested across all targets; limit '
        + screenshotFixture.max_copy_writes + ' ('
        + (payload.counts.ready - screenshotFixture.max_copy_writes) + ' over). '
        + 'Select fewer fittings or targets, then review again.' : '';
    if (!payload.accepted) { payload.ticket_id = ''; payload.created_utc = ''; }
    return payload;
  }

  function renderScreenshotState() {
    if (copyContextObserver) copyContextObserver.disconnect();
    copyPreflightRequest = null;
    copyDialogGeneration += 1;
    filters = { collection_id: 'all', search: '', ship_type_id: null, page: 1 };
    expandedId = '';
    detail = null;
    selected = {};
    progress = null;
    copyOverlayOpen = false;
    copyPhase = 'targets';
    activeCopyTicket = '';
    copyTargets = {};
    copyPreflight = null;
    copyContext = null;
    copyReviewDirty = false;
    copyHulls = Object.create(null);
    alternateNames = {};
    alternateDrafts = {};
    refreshInFlight = false;
    WM.el('fittings-search').value = '';
    WM.el('fittings-copy-overlay').hidden = true;
    render(screenshotWorkspace(currentFilters()));
    if (screenshotFixture.copy_stage) {
      var result = screenshotFixture.copy_result;
      result.results.forEach(function (pair) { selected[pair.entry_id] = true; });
      openCopyOverlay(); // snapshots every selected hull through the ordinary path
      presentCopyProgress('', result.results.length);
      if (screenshotFixture.copy_stage === 'progress') {
        var completed = screenshotFixture.copy_progress_completed;
        renderCopyProgress(completed, result.results.length, result.results[completed - 1]);
      } else finishCopy(result);
    }
  }

  function requestState() {
    cancelLocate();
    cancelExport();
    detailSeq += 1;
    requestSequence += 1;
    if (screenshotFixture) {
      render(screenshotWorkspace(currentFilters()));
      return;
    }
    var wanted = requestSequence;
    WM.send('fittings_state', currentFilters()).then(function (payload) {
      // A live read started before CDP injection must not repaint over the
      // deterministic screenshot state when its promise resolves later.
      if (screenshotFixture) return;
      if (!payload) { asked = false; return; }
      if (wanted !== requestSequence || WM.current_route !== 'fittings') return;
      render(payload);
    });
  }

  function requeryIfRejected(applied) {
    if (!applied) requestState();
  }

  function render(payload) {
    STATE = payload;
    if (!payload.refreshing && !(progress && progress.error)) progress = null;
    refreshInFlight = payload.refreshing;
    renderCounts();
    renderCollections();
    renderHead();
    renderNotices();
    renderShipFilterOptions();
    renderFilterBar();
    pruneSelection(payload.rows || []);
    pruneMetadataDrafts(payload);
    renderList();
    renderPager();
    renderRailButtons();
    if (expandedId) requestDetail(expandedId);
  }

  WM.handle('onFittingsChanged', function (payload) {
    // Revoke before a requery: a source rename/delete invalidates clipboard
    // delivery even while its replacement workspace is still in flight.
    cancelExport();
    // A page missing this ID may simply be filtered. Only an explicit deletion
    // retires an off-page draft, including when this route is hidden.
    if (payload && payload.reason === 'delete') delete metadataDrafts[payload.entry_id];
    // A semantic "something changed" signal, never a payload to render
    // directly -- see the design doc's "no whole-library pushes". The
    // page re-asks for whatever it is currently looking at.
    if (asked) requestState();
    if (!screenshotFixture && payload && payload.reason === 'delete'
        && importDraft.result && importDraft.result.entry_id === payload.entry_id) {
      setImportStatus('Fitting no longer exists. Close this panel or import a new fitting.', true);
    }
  });

  WM.handle('onFittingsProgress', function (payload) {
    if (payload && payload.kind === 'copy') {
      onCopyProgress(payload);
      return;
    }
    progress = payload;
    refreshInFlight = !(payload && payload.phase === 'complete');
    // A progress push races the first fittings_state() reply in theory
    // (independent async paths -- clicking Refresh does not wait on the
    // initial state fetch to land): nothing to update yet if STATE is
    // still null, and the next progress tick or the pending state reply
    // renders it once there is something to render into.
    if (!STATE) return;
    renderNotices();
    renderRailButtons();
  });

  // Tooling-only semantic state injection, following Previews'
  // onPreviewHotkeys screenshot precedent. No Python producer exists and no
  // user control calls it. The payload is owned by dev.js, bounded here at
  // the production-page boundary, and used only for local reads/presentation.
  // Copy presentation grants no writer admission, including on route leave.
  WM.handle('onFittingsScreenshotState', function (payload) {
    if (payload.kind === 'fittings-screenshot-v1' && payload.clear === true) {
      // Hide the synthetic workspace while its guard still owns route cleanup.
      // A refused injection must never navigate away from a genuine live copy.
      if (!screenshotFixture) return;
      WM.route('main');
      return;
    }
    if (WM.current_route !== 'fittings' || !validScreenshotFixture(payload)
        || (copyHistoryOperation && copyHistoryOperation.pending)) return;
    cancelImportRequest();
    cancelLocate();
    cancelExport();
    requestSequence += 1;
    detailSeq += 1;
    if (!screenshotFixture) detachedImportDraft = importDraft;
    importDraft = emptyImportDraft();
    renderImportDraft();
    screenshotFixture = JSON.parse(JSON.stringify(payload));
    renderScreenshotState();
  });

  document.addEventListener('wm:route', function (event) {
    if (event.detail !== 'fittings') {
      cancelImportRequest();
      cancelLocate();
      cancelExport();
      requestSequence += 1;
      detailSeq += 1;
      // Cleanup for the one thing this route arms outside its own markup:
      // a debounced search request.
      if (searchDebounce) { clearTimeout(searchDebounce); searchDebounce = null; }
      // Keyed to the ticket: this fires right after confirm and can reach
      // Python before the worker has consumed the ticket, and a cancel
      // with no key used to be erased by that start.
      if (copyPhase === 'progress' && !screenshotFixture) WM.send('fittings_cancel_copy', activeCopyTicket);
      closeCopyOverlay(true);
      if (screenshotFixture) {
        // The hidden fixture must not publish a delayed detail or carry its
        // expanded ID into the next live workspace read.
        detailSeq += 1;
        expandedId = '';
        detail = null;
      }
      screenshotFixture = null;
      if (detachedImportDraft) {
        importDraft = detachedImportDraft;
        detachedImportDraft = null;
        renderImportDraft();
      }
      clearSelection();
      // Settings owns sign-in and Forget, so a hidden-route authority change
      // must be picked up by the next real Fittings entry.
      asked = false;
      return;
    }
    if (asked) return;
    asked = true;
    requestState();
  });

  document.addEventListener('wm:eve-authority', function () {
    if (WM.current_route !== 'fittings') return;
    requestState();
  });

  // ---- rail: counts, collections ---------------------------------------

  function renderCounts() {
    var chars = (STATE.characters || []).length;
    WM.el('fittings-counts').textContent = chars
      ? chars + (chars === 1 ? ' character tracked' : ' characters tracked')
      : 'No EVE characters yet';
  }

  function currentCollection() {
    return (STATE.collections || []).filter(function (c) {
      return c.id === filters.collection_id;
    })[0];
  }

  function isCustomCollection(id) {
    return ['all', 'unfiled', 'superseded'].indexOf(id) === -1;
  }

  function renderCollections() {
    var host = WM.el('fittings-collections');
    host.textContent = '';
    (STATE.collections || []).forEach(function (collection) {
      var row = WM.make('button', 'rail-plan');
      if (collection.id === filters.collection_id) row.classList.add('active');
      row.appendChild(WM.make('span', 'rail-plan-name', collection.name));
      row.appendChild(WM.make('span', 'rail-ratio', String(collection.count)));
      row.addEventListener('click', function () { selectCollection(collection.id); });
      host.appendChild(row);
    });
    var current = currentCollection();
    var custom = !!current && isCustomCollection(current.id);
    WM.el('fittings-collection-rename').disabled = !custom;
    WM.el('fittings-collection-delete').disabled = !custom;
  }

  function selectCollection(id) {
    if (id === filters.collection_id) return;
    filters.collection_id = id;
    filters.page = 1;
    clearSelection();
    requestState();
  }

  WM.el('fittings-collection-new').addEventListener('click', function () {
    WM.prompt('New collection', 'A name for this collection.', '')
      .then(function (text) {
        if (text === null) return;
        var wanted = text.trim();
        if (!wanted) return;
        WM.send('fittings_create_collection', wanted).then(function (collectionId) {
          if (!collectionId) return;
          filters.collection_id = collectionId;
          filters.page = 1;
          requestState();
        });
      });
  });

  WM.el('fittings-collection-rename').addEventListener('click', function () {
    var current = currentCollection();
    if (!current) return;
    WM.prompt('Rename collection', 'A new name for this collection.', current.name)
      .then(function (text) {
        if (text === null) return;
        var wanted = text.trim();
        if (!wanted || wanted === current.name) return;
        WM.send('fittings_rename_collection', current.id, wanted)
          .then(requeryIfRejected);
      });
  });

  WM.el('fittings-collection-delete').addEventListener('click', function () {
    var current = currentCollection();
    if (!current) return;
    WM.confirm('Delete collection',
               '\u201c' + current.name + '\u201d has ' + current.count
               + (current.count === 1 ? ' fitting' : ' fittings')
               + '. Deleting it removes the grouping only -- every fitting '
               + 'stays in the library.',
               { destructive: true })
      .then(function (ok) {
        if (!ok) return;
        WM.send('fittings_delete_collection', current.id).then(function () {
          filters.collection_id = 'all';
          filters.page = 1;
          clearSelection();
          requestState();
        });
      });
  });

  WM.el('fittings-refresh-all').addEventListener('click', function () {
    // Optimistic: the controller's refresh is synchronous on its own
    // worker and the first onFittingsProgress may be seconds away (one
    // ESI round trip per character), so waiting for a push to disable
    // this button would leave it clickable for the length of that wait.
    progress = null;
    refreshInFlight = true;
    renderRailButtons();
    WM.send('fittings_refresh', null);
  });

  function renderRailButtons() {
    var refreshAll = WM.el('fittings-refresh-all');
    var busy = (STATE && STATE.refreshing) || refreshInFlight;
    refreshAll.textContent = busy ? 'Refreshing\u2026' : 'Refresh characters';
    refreshAll.disabled = busy || !(STATE && STATE.characters || []).length;
  }

  WM.el('fittings-manage-characters').addEventListener('click', function () {
    WM.openSettingsSection('characters');
  });

  // ---- main pane header, notices, filters ------------------------------

  function renderHead() {
    var current = currentCollection();
    WM.el('fittings-collection-name').textContent = current ? current.name : 'All fittings';
    var count = STATE.total || 0;
    WM.el('fittings-collection-count').textContent =
      count + (count === 1 ? ' fitting' : ' fittings');
  }

  function renderNotices() {
    if (copyOverlayOpen && copyPhase === 'targets') {
      // Applied library reads may prune selection while setup stays open. Only
      // refresh its description; an in-flight review still owns its submitted set.
      var heading = copyHeading({ fitting_count: visibleSelectedIds().length,
        targets: copyTargetSnapshot(selectedTargetIds()) }, true);
      var title = WM.el('fittings-copy-title');
      if (title.textContent !== heading) {
        title.textContent = heading;
        if (!WM.el('fittings-copy-limit-summary').hidden) {
          setCopyLimit('');
          if (!copyPreflightRequest) setCopyStatus('Review copy to check current additions.');
        }
      }
    }
    var host = WM.el('fittings-notices');
    host.textContent = '';
    var lines = [];
    if (STATE.refreshing) lines.push('Refreshing characters\u2026');
    if (progress && progress.total) {
      lines.push('Refreshed ' + progress.completed + ' of '
                 + progress.total + ' characters');
    }
    if (progress && progress.error) lines.push(progress.error);
    (STATE.warnings || []).forEach(function (text) { lines.push(text); });
    host.hidden = !lines.length && !lastCopyResult;
    lines.forEach(function (text) { host.appendChild(WM.make('p', 'notice', text)); });
    if (lastCopyResult) {
      var reopen = WM.make('button', 'btn', 'Last copy results\u2026');
      reopen.disabled = copyOverlayOpen || copyPhase === 'progress'
        || !!(copyHistoryOperation && copyHistoryOperation.pending);
      reopen.addEventListener('click', function () {
        if (copyOverlayOpen || copyPhase === 'progress'
            || (copyHistoryOperation && copyHistoryOperation.pending)) return;
        cancelExport();
        cancelLocate();
        copyDialogGeneration += 1;
        copyInvoker = reopen;
        copyOverlayOpen = true;
        copyPhase = 'results';
        copyHulls = lastCopyHulls;
        copyContext = lastCopyContext;
        WM.el('fittings-copy-overlay').hidden = false;
        renderCopyResults(lastCopyResult);
        renderNotices();
      });
      host.appendChild(reopen);
    }
  }

  function renderShipFilterOptions() {
    var select = WM.el('fittings-ship-filter');
    select.textContent = '';
    var all = WM.make('option', '', 'All ships');
    all.value = '';
    select.appendChild(all);
    (STATE.ships || []).forEach(function (ship) {
      var option = WM.make('option', '', ship.name || ('Type ' + ship.type_id));
      option.value = String(ship.type_id);
      select.appendChild(option);
    });
    select.value = filters.ship_type_id ? String(filters.ship_type_id) : '';
  }

  function renderFilterBar() {
    WM.el('fittings-filter-clear').hidden =
      !(filters.search.trim() || filters.ship_type_id);
  }

  WM.el('fittings-search').addEventListener('input', function () {
    cancelLocate();
    cancelExport();
    requestSequence += 1; // typing revokes before the debounce admits another query
    detailSeq += 1;
    filters.search = WM.el('fittings-search').value;
    filters.page = 1;
    clearSelection();
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(function () {
      searchDebounce = null;
      requestState();
    }, 200);
  });

  WM.el('fittings-ship-filter').addEventListener('change', function () {
    var value = WM.el('fittings-ship-filter').value;
    filters.ship_type_id = value ? parseInt(value, 10) : null;
    filters.page = 1;
    clearSelection();
    requestState();
  });

  WM.el('fittings-filter-clear').addEventListener('click', function () {
    WM.el('fittings-search').value = '';
    filters.search = '';
    filters.ship_type_id = null;
    filters.page = 1;
    clearSelection();
    requestState();
  });

  // ---- local clipboard import / export --------------------------------

  function emptyImportDraft() {
    return { open: false, text: '', review: null, result: null,
             needsReview: false, canReviewAgain: false, status: '', error: false };
  }

  function setImportStatus(text, isError) {
    importDraft.status = text;
    importDraft.error = !!isError;
    var node = WM.el('fittings-import-status');
    node.textContent = text;
    if (isError) node.classList.add('err');
    else node.classList.remove('err');
  }

  function importAvailable() {
    return WM.current_route === 'fittings' && importDraft.open && !copyOverlayOpen
      && WM.el('overlay').hidden;
  }

  function updateImportControls() {
    var pending = !!importRequest;
    WM.el('fittings-import-read').disabled = pending;
    WM.el('fittings-import-review').textContent = importDraft.canReviewAgain || importDraft.needsReview
      ? 'Review again' : 'Review';
    WM.el('fittings-import-review').disabled = pending || !importDraft.text.trim()
      || (!!importDraft.review && !importDraft.needsReview && !importDraft.canReviewAgain);
    WM.el('fittings-import-add').disabled = pending || !importDraft.review
      || importDraft.needsReview || !!importDraft.result;
    WM.el('fittings-import-show').hidden = !importDraft.result;
  }

  function renderImportDraft() {
    WM.el('fittings-import-panel').hidden = !importDraft.open;
    WM.el('fittings-import-open').setAttribute('aria-expanded', String(importDraft.open));
    WM.el('fittings-import-text').value = importDraft.text;
    var host = WM.el('fittings-import-candidate');
    host.textContent = '';
    host.hidden = !importDraft.review;
    if (importDraft.review) {
      var review = importDraft.review;
      host.appendChild(WM.make('p', '', review.name + ' \u2014 ' + review.ship_name));
      host.appendChild(modulesNode(review.items));
      // Keep source order and every warning, including after successful Add.
      // These describe the reviewed interpretation, not persisted metadata.
      review.warnings.forEach(function (warning) {
        host.appendChild(WM.make('p', 'fit-import-warning',
          warning.message));
      });
    }
    setImportStatus(importDraft.status, importDraft.error);
    updateImportControls();
  }

  function cancelImportRequest() {
    if (!importRequest) return;
    var kind = importRequest.kind;
    importRequest = null;
    // A sent Add may have committed even when its UI owner leaves. Keep the
    // review visible, but do not resurrect an ambiguously consumed ticket.
    if (kind === 'add') importDraft.needsReview = true;
    setImportStatus(kind === 'add'
      ? 'Add result not confirmed here. Check the library before reviewing again.'
      : 'Request cancelled. Your text is kept.');
    updateImportControls();
  }

  function newImportText(text) {
    cancelImportRequest();
    cancelLocate();
    importDraft.text = text;
    importDraft.review = null;
    importDraft.result = null;
    importDraft.needsReview = false;
    importDraft.canReviewAgain = false;
    importDraft.status = '';
    importDraft.error = false;
    // Do not replace the textarea while typing; its caret/scroll are native.
    var candidate = WM.el('fittings-import-candidate');
    candidate.textContent = '';
    candidate.hidden = true;
    setImportStatus('');
    updateImportControls();
  }

  function beginImportRequest(kind, button) {
    var owner = { kind: kind, draft: importDraft };
    importRequest = owner;
    // Handoff before disabling the invoking button; never focus on a reply.
    if (document.activeElement === button) WM.el('fittings-import-close').focus({ preventScroll: true });
    updateImportControls();
    return owner;
  }

  function ownsImport(owner) {
    return importRequest === owner && importDraft === owner.draft
      && WM.current_route === 'fittings' && importDraft.open;
  }

  function screenshotClipboard() {
    return screenshotFixture && screenshotFixture.clipboard;
  }

  WM.el('fittings-import-open').addEventListener('click', function () {
    if (WM.current_route !== 'fittings' || copyOverlayOpen) return;
    importDraft.open = true;
    renderImportDraft();
    WM.el('fittings-import-text').focus({ preventScroll: true });
    // One-click import for a fresh draft, never silent replacement of retained
    // text or a completed review whose warnings are still being read.
    if (!importDraft.text && !importDraft.review && !importDraft.result) {
      readImportClipboard(WM.el('fittings-import-read'));
    }
  });

  function closeImport() {
    var ownedFocus = WM.el('fittings-import-panel').contains(document.activeElement);
    cancelImportRequest();
    cancelLocate();
    importDraft = emptyImportDraft();
    renderImportDraft();
    if (ownedFocus && WM.current_route === 'fittings' && !copyOverlayOpen && WM.el('overlay').hidden) {
      WM.el('fittings-import-open').focus({ preventScroll: true });
    }
  }
  WM.el('fittings-import-close').addEventListener('click', closeImport);
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape' || event.defaultPrevented || !importAvailable()
        || !WM.el('fittings-import-panel').contains(event.target)) return;
    event.preventDefault();
    closeImport();
  });
  WM.el('fittings-import-text').addEventListener('input', function () {
    newImportText(WM.el('fittings-import-text').value);
  });

  WM.el('fittings-import-read').addEventListener('click', function () {
    readImportClipboard(this);
  });

  function readImportClipboard(button) {
    if (!importAvailable() || importRequest) return;
    var owner = beginImportRequest('read', button);
    setImportStatus('Reading clipboard\u2026');
    function failed() {
      if (!ownsImport(owner)) return;
      importRequest = null;
      setImportStatus(screenshotFixture ? 'No clipboard text in this screenshot fixture. Paste manually.'
        : 'Could not read the clipboard. Paste fitting text manually, then Review.', true);
      updateImportControls();
    }
    try {
      // Only opener/Read clicks reach this browser call. Detached screenshot
      // data must explicitly supply text; it never falls back to the OS clipboard.
      var fixture = screenshotClipboard();
      var pending = screenshotFixture
        ? (fixture ? Promise.resolve(fixture.text) : Promise.reject(new Error('No fixture')))
        : navigator.clipboard.readText();
      pending.then(function (text) {
        if (!ownsImport(owner)) return;
        importRequest = null;
        newImportText(text);
        WM.el('fittings-import-text').value = text;
        setImportStatus('Clipboard text ready. Review before adding.');
      }, failed);
    } catch (err) { failed(); }
  }

  WM.el('fittings-import-review').addEventListener('click', function () {
    if (!importAvailable() || this.disabled || importRequest || !importDraft.text.trim()) return;
    importDraft.review = null;
    importDraft.result = null;
    importDraft.needsReview = false;
    importDraft.canReviewAgain = false;
    renderImportDraft();
    var owner = beginImportRequest('review', this);
    setImportStatus('Reviewing fitting\u2026');
    var fixture = screenshotClipboard();
    var pending = screenshotFixture
      ? Promise.resolve(fixture && fixture.text === importDraft.text ? fixture.review : null)
      : WM.send('fittings_review_eft', importDraft.text);
    pending.then(function (payload) {
      if (!ownsImport(owner)) return;
      importRequest = null;
      if (!payload || !payload.ok) {
        setImportStatus(payload && payload.error || (screenshotFixture
          ? 'This text is not covered by the screenshot fixture.'
          : 'Review not confirmed. Your text is kept; try Review again.'), true);
        updateImportControls();
        return;
      }
      importDraft.review = payload;
      setImportStatus(payload.existing_entry_id
        ? 'Matching content is already in the library. Add will keep the existing fitting.'
        : 'Review the fitting and any warnings, then Add to library.');
      renderImportDraft();
    });
  });

  WM.el('fittings-import-add').addEventListener('click', function () {
    if (!importAvailable() || importRequest || !importDraft.review
        || importDraft.needsReview || importDraft.result) return;
    var owner = beginImportRequest('add', this);
    var reviewId = importDraft.review.review_id;
    setImportStatus('Adding to library\u2026');
    var fixture = screenshotClipboard();
    var pending = screenshotFixture
      ? Promise.resolve(fixture && fixture.review.review_id === reviewId ? fixture.receipt : null)
      : WM.send('fittings_import_eft', reviewId);
    pending.then(function (payload) {
      if (!ownsImport(owner)) return;
      importRequest = null;
      if (!payload || !payload.applied || !payload.persisted) {
        // A save refusal can retry this ID, but an expired/consumed ticket
        // needs a fresh Review. Offer both without classifying error prose.
        importDraft.canReviewAgain = true;
        setImportStatus(payload && payload.error
          || 'Add not confirmed. Your reviewed text is kept; try Add to library again.', true);
        updateImportControls();
        return;
      }
      importDraft.result = payload;
      importDraft.text = '';
      WM.el('fittings-import-text').value = '';
      setImportStatus(payload.created ? 'Added a new fitting to the library.'
        : 'Already in the library; the existing fitting was kept.');
      updateImportControls();
    });
  });

  function cancelLocate() {
    if (!locateOwner) return;
    locateOwner = null;
    setImportStatus('Show fitting cancelled. Use Show fitting to try again.');
  }

  document.addEventListener('focusin', function (event) {
    if (locateOwner && event.target !== WM.el('fittings-import-show')) locateOwner.focus = false;
    if (!WM.el('overlay').hidden) cancelExport();
  });

  WM.el('fittings-import-show').addEventListener('click', function () {
    if (!importAvailable() || !importDraft.result || locateOwner) return;
    cancelExport();
    if (searchDebounce) { clearTimeout(searchDebounce); searchDebounce = null; }
    requestSequence += 1;
    detailSeq += 1;
    var owner = { sequence: requestSequence, draft: importDraft,
                  focus: document.activeElement === this };
    locateOwner = owner;
    var id = importDraft.result.entry_id;
    setImportStatus('Finding fitting\u2026');
    var pending;
    if (screenshotFixture) {
      var workspace = screenshotWorkspace({collection_id: 'all', search: '', ship_type_id: null, page: 1});
      pending = Promise.resolve({ok: workspace.rows.some(function (row) { return row.id === id; }),
        entry_id: id, workspace: workspace, error: 'Fitting is not in this screenshot fixture.'});
    } else pending = WM.send('fittings_locate_entry', id);
    pending.then(function (payload) {
      if (locateOwner !== owner || owner.sequence !== requestSequence
          || owner.draft !== importDraft || WM.current_route !== 'fittings' || !importDraft.open) return;
      locateOwner = null;
      if (!payload || !payload.ok || !payload.workspace) {
        setImportStatus(payload && payload.error || 'Fitting is unavailable. Use Show fitting to try again.', true);
        return;
      }
      // Locator already owns one ordered workspace snapshot. Re-reading its
      // page would lose a target renamed/inserted across the boundary meanwhile.
      filters = {collection_id: 'all', search: '', ship_type_id: null, page: payload.workspace.page};
      WM.el('fittings-search').value = '';
      expandedId = payload.entry_id;
      detail = null;
      detailError = '';
      clearSelection();
      render(payload.workspace);
      setImportStatus('Showing fitting in All fittings.');
      var target = WM.el('fit-toggle-' + payload.entry_id);
      if (owner.focus && document.activeElement === WM.el('fittings-import-show') && target
          && !copyOverlayOpen && WM.el('overlay').hidden) {
        target.focus();
      }
    });
  });

  function cancelExport() {
    if (!exportOwner) return;
    var owner = exportOwner;
    exportOwner = null;
    owner.button.disabled = false;
    owner.status.textContent = 'Clipboard copy cancelled. Try Copy to clipboard again.';
  }

  function exportNode(current) {
    var box = WM.make('div', 'fit-clipboard-actions');
    var button = WM.make('button', 'btn', 'Copy to clipboard');
    var status = WM.make('p', 'field-msg fit-export-status');
    status.setAttribute('role', 'status');
    button.title = 'Export the saved fitting name and items, not unsaved metadata.';
    box.appendChild(button);
    box.appendChild(status);
    button.addEventListener('click', function () {
      if (exportOwner || WM.current_route !== 'fittings' || expandedId !== current.id
          || !document.contains(button) || copyOverlayOpen || !WM.el('overlay').hidden) return;
      var owner = {id: current.id, button: button, status: status, fixture: screenshotFixture};
      exportOwner = owner;
      if (document.activeElement === button) {
        WM.el('fit-toggle-' + current.id).focus({ preventScroll: true });
      }
      button.disabled = true;
      status.classList.remove('err');
      status.textContent = 'Preparing clipboard text\u2026';
      function owns() {
        return exportOwner === owner && WM.current_route === 'fittings'
          && expandedId === owner.id && owner.fixture === screenshotFixture
          && document.contains(button) && !copyOverlayOpen && WM.el('overlay').hidden;
      }
      function finish(text, error) {
        if (!owns()) return;
        exportOwner = null;
        button.disabled = false;
        status.textContent = text;
        if (error) status.classList.add('err');
        else status.classList.remove('err');
      }
      function failed() { finish('Could not write to the clipboard. Check clipboard access and try again.', true); }
      var fixture = screenshotClipboard();
      var pending = screenshotFixture
        ? Promise.resolve(fixture && fixture.entry_id === current.id ? fixture.export : null)
        : WM.send('fittings_export_eft', current.id);
      pending.then(function (payload) {
        if (!owns()) return;
        if (!payload || !payload.ok) {
          finish(payload && payload.error || (screenshotFixture
            ? 'This fitting has no clipboard export in the screenshot fixture.'
            : 'Export not confirmed. Try Copy to clipboard again.'), true);
          return;
        }
        try {
          // Check ownership immediately before the irreversible browser call.
          // The OS promise cannot be cancelled after delivery has started.
          var writing = screenshotFixture ? Promise.resolve() : navigator.clipboard.writeText(payload.text);
          writing.then(function () {
            finish(screenshotFixture ? 'Clipboard copy simulated for screenshot.' : 'Copied to clipboard.');
          }, failed);
        } catch (err) { failed(); }
      });
    });
    return box;
  }

  // ---- the list, one page at a time ------------------------------------

  function collectionNames(ids) {
    var byId = {};
    (STATE.collections || []).forEach(function (c) { byId[c.id] = c.name; });
    return ids.map(function (id) { return byId[id] || id; }).join(', ');
  }

  var stickyHeaderObserver = window.ResizeObserver
    ? new window.ResizeObserver(measureStickyClearance) : null;

  function measureStickyClearance() {
    var toggle = expandedId ? WM.el('fit-toggle-' + expandedId) : null;
    var top = toggle && toggle.parentNode;
    var scroller = WM.el('fittings-workspace-scroll');
    if (top && top.getClientRects().length) {
      scroller.style.setProperty('--fit-sticky-clearance',
        (top.getBoundingClientRect().height + 8) + 'px');
    } else scroller.style.removeProperty('--fit-sticky-clearance');
  }

  window.addEventListener('resize', measureStickyClearance);

  function renderList(rowActionId) {
    var renderToken = ++listRenderSequence;
    var renderRequest = requestSequence;
    var renderExpanded = expandedId;
    if (stickyHeaderObserver) stickyHeaderObserver.disconnect();
    cancelExport(); // the row's controls are about to detach, even without a query
    var host = WM.el('fittings-list');
    var empty = WM.el('fittings-empty');
    var editor = host.querySelector('.fit-metadata-disclosure');
    // A semantic push replaces the list twice (state, then detail). Snapshot
    // native disclosure/focus state before either rebuild, without saving text.
    if (editor) {
      var editorId = editor.getAttribute('data-entry-id');
      metadataEditors[editorId] = editor.open;
    }
    var active = document.activeElement;
    var immediate = host.querySelector('.fit-immediate');
    var warningId = active && host.contains(active) && active.classList.contains('fit-deployability')
      ? active.getAttribute('data-entry-id') : '';
    var focusId = (warningId && (!rowActionId || rowActionId === warningId))
      || (editor && editor.contains(active))
      || (immediate && immediate.contains(active))
      || (active && active.classList.contains('fit-row-toggle') && host.contains(active))
      ? active.id : '';
    var start = focusId ? active.selectionStart : null;
    var end = focusId ? active.selectionEnd : null;
    var direction = focusId ? active.selectionDirection : null;
    var scroller = WM.el('fittings-workspace-scroll');
    var scrollTop = scroller.scrollTop;
    host.textContent = '';
    // Removing a focused node can synchronously hand control to a newer render
    // or route. The retired owner must neither repaint nor reclaim its focus.
    if (renderToken !== listRenderSequence || renderRequest !== requestSequence
        || renderExpanded !== expandedId) return;
    var rows = STATE.rows || [];
    WM.el('fittings-list-head').hidden = !rows.length;
    if (!rows.length) {
      measureStickyClearance();
      empty.hidden = false;
      var filtered = !!(filters.search.trim() || filters.ship_type_id
                        || filters.collection_id !== 'all');
      empty.textContent = filtered
        ? 'No fittings match the current filters.'
        : 'Use Import from clipboard… to add a fitting, or authenticate a character in Settings › Character access and press Refresh characters.';
      return;
    }
    empty.hidden = true;
    rows.forEach(function (row, index) { host.appendChild(rowNode(row, index)); });
    measureStickyClearance();
    var expandedToggle = expandedId ? WM.el('fit-toggle-' + expandedId) : null;
    if (stickyHeaderObserver && expandedToggle) stickyHeaderObserver.observe(expandedToggle.parentNode);
    // Emptying the list can clamp its parent to zero, but a synchronous focus
    // successor also owns any scroll it established during that handoff.
    if (document.activeElement === active || document.activeElement === document.body) {
      scroller.scrollTop = scrollTop;
    }
    if (focusId && renderToken === listRenderSequence && renderRequest === requestSequence
        && renderExpanded === expandedId && WM.current_route === 'fittings' && !copyOverlayOpen
        && WM.el('overlay').hidden
        && (document.activeElement === active || document.activeElement === document.body)) {
      var replacement = WM.el(focusId);
      // Eligibility can remove Details; keep its continuation on the same row,
      // never in another fitting's editor. Removed rows have no fallback.
      // Discard/Save retain their existing editor-summary fallback.
      if (!replacement || replacement.disabled || !replacement.getClientRects().length) {
        replacement = warningId ? WM.el('fit-toggle-' + warningId) : editor
          ? WM.el('fit-metadata-summary-' + editor.getAttribute('data-entry-id')) : null;
      }
      if (replacement && replacement.getClientRects().length) {
        replacement.focus({ preventScroll: true });
        if (renderToken !== listRenderSequence || renderRequest !== requestSequence
            || renderExpanded !== expandedId || document.activeElement !== replacement) return;
        if (replacement.id === focusId && typeof start === 'number' && typeof end === 'number') {
          replacement.setSelectionRange(start, end, direction);
        }
        scroller.scrollTop = scrollTop;
      }
    }
  }

  function pruneSelection(rows) {
    var visible = {};
    rows.forEach(function (row) { visible[row.id] = true; });
    Object.keys(selected).forEach(function (id) {
      if (!visible[id]) delete selected[id];
    });
    renderSelectionCount();
  }

  function clearSelection() {
    selected = {};
    renderSelectionCount();
  }

  function visibleSelectedIds() {
    var selectedIds = selected;
    return ((STATE && STATE.rows) || []).filter(function (row) {
      return !!selectedIds[row.id];
    }).map(function (row) { return row.id; });
  }

  function renderSelectionCount() {
    var count = visibleSelectedIds().length;
    var button = WM.el('fittings-copy-selected');
    button.textContent = count ? 'Copy selected (' + count + ')' : 'Copy selected';
    button.disabled = count === 0 || copyPhase === 'progress';
    button.title = count ? '' : 'Select one or more fittings on this page.';
    WM.el('fittings-select-page').disabled = !((STATE && STATE.rows) || []).length
      || copyPhase === 'progress';
    WM.el('fittings-clear-selection').disabled = count === 0 || copyPhase === 'progress';
    // Selection is local paint only. Rebuilding the list would replace open
    // metadata controls, their drafts, focus and scroll for a checkbox change.
    var labels = WM.el('fittings-list').querySelectorAll('.fit-select');
    for (var i = 0; i < labels.length; i++) {
      var box = labels[i].querySelector('input');
      box.checked = !!selected[box.value];
    }
  }

  WM.el('fittings-select-page').addEventListener('click', function () {
    if (!STATE || !(STATE.rows || []).length || copyPhase === 'progress') return;
    STATE.rows.forEach(function (row) { selected[row.id] = true; });
    renderSelectionCount();
  });
  WM.el('fittings-clear-selection').addEventListener('click', function () {
    if (!visibleSelectedIds().length || copyPhase === 'progress') return;
    var ownedFocus = document.activeElement === WM.el('fittings-clear-selection');
    clearSelection();
    // Clear disables itself. Keep its keyboard continuation local without
    // taking focus from a metadata draft during a programmatic selection.
    if (ownedFocus) WM.el('fittings-select-page').focus({ preventScroll: true });
  });
  WM.el('fittings-copy-selected').addEventListener('click', openCopyOverlay);

  function metadataDirty(value) {
    return !!value && (value.pending || value.name !== value.committedName
      || value.description !== value.committedDescription);
  }

  function rowMetadata(row) {
    var meta = [];
    meta.push('On ' + row.presence_count
             + (row.presence_count === 1 ? ' character' : ' characters'));
    if (row.collection_ids.length) meta.push(collectionNames(row.collection_ids));
    if (row.superseded_by) meta.push('Superseded');
    if (metadataDirty(metadataDrafts[row.id])) meta.push('Unsaved changes');
    return meta.join(' \u00b7 ');
  }

  function updateRowMetadata(id) {
    var meta = WM.el('fit-meta-' + id);
    var row = (STATE.rows || []).filter(function (item) { return item.id === id; })[0];
    if (!meta || !row) return;
    meta.textContent = rowMetadata(row);
    meta.title = meta.textContent;
    // A keystroke changes only the cue, never the live editor/caret or scroller.
    measureStickyClearance();
  }

  function rowNode(row, index) {
    var shipName = row.ship_name || ('Type ' + row.ship_type_id);
    var node = WM.make('div', 'fit-row');
    if (expandedId === row.id) node.classList.add('open');

    var top = WM.make('div', 'fit-row-top');

    var box = document.createElement('input');
    box.type = 'checkbox';
    // The .check/.box pattern, not a bare input -- see
    // test_page_conventions.py's native-checkbox guard and evesettings.js's
    // own note on the same construction.
    var label = WM.make('label', 'check fit-select');
    label.appendChild(box);
    label.appendChild(WM.make('span', 'box'));
    // Names and hulls can both repeat; position distinguishes this rendered page.
    box.setAttribute('aria-label', 'Select ' + row.name + ' \u2014 ' + shipName
                     + ', row ' + (index + 1) + ' on this page');
    box.value = row.id;
    box.checked = !!selected[row.id];
    box.addEventListener('change', function () {
      if (box.checked) { selected[row.id] = true; } else { delete selected[row.id]; }
      renderSelectionCount();
    });
    top.appendChild(label);

    var toggle = WM.make('button', 'fit-row-toggle');
    toggle.id = 'fit-toggle-' + row.id;
    toggle.setAttribute('aria-expanded', expandedId === row.id ? 'true' : 'false');
    var chevron = WM.make('span', 'chev', expandedId === row.id ? '\u25be' : '\u25b8');
    chevron.setAttribute('aria-hidden', 'true');
    var identity = WM.make('span', 'fit-identity');
    identity.appendChild(chevron);
    var name = WM.make('span', 'fit-name', row.name);
    name.id = 'fit-row-name-' + row.id;
    name.title = row.name;
    identity.appendChild(name);
    toggle.appendChild(identity);
    var ship = WM.make('span', 'fit-ship', shipName);
    ship.id = 'fit-row-ship-' + row.id;
    ship.title = shipName;
    toggle.appendChild(ship);
    var status = WM.make('div', 'fit-row-status');
    var meta = WM.make('span', 'fit-meta', rowMetadata(row));
    meta.id = 'fit-meta-' + row.id;
    meta.title = meta.textContent;
    status.appendChild(meta);
    toggle.setAttribute('aria-labelledby', name.id + ' ' + ship.id + ' ' + meta.id);
    toggle.addEventListener('click', function () { toggleRow(row.id); });
    top.appendChild(toggle);
    if (!row.deployable) {
      var why = WM.make('button', 'linkbtn fit-deployability', 'Cannot copy \u00b7 Details\u2026');
      why.id = 'fit-deployability-' + row.id;
      why.setAttribute('data-entry-id', row.id);
      why.setAttribute('aria-label', row.name + ': cannot copy. Show details.');
      why.setAttribute('aria-expanded', expandedId === row.id ? 'true' : 'false');
      why.addEventListener('click', function () {
        if (expandedId !== row.id) toggleRow(row.id);
      });
      status.appendChild(why);
    }
    top.appendChild(status);

    node.appendChild(top);
    if (expandedId === row.id) node.appendChild(detailNode(row));
    return node;
  }

  function toggleRow(id) {
    cancelLocate();
    cancelExport();
    detailError = '';
    detailSeq += 1;
    var requestOwner = detailSeq;
    if (expandedId === id) {
      expandedId = '';
      detail = null;
      renderList(id);
      return;
    }
    expandedId = id;
    detail = null;
    renderList(id);
    // Focus/removal handlers may have handed the view to a newer row or route.
    if (requestOwner === detailSeq && expandedId === id && WM.current_route === 'fittings') {
      requestDetail(id);
    }
  }

  function requestDetail(id) {
    detailError = '';
    detailSeq += 1;
    var token = detailSeq;
    var committedRevision = metadataDrafts[id] ? metadataDrafts[id].committedRevision : 0;
    var pending = screenshotFixture
      ? Promise.resolve(screenshotDetail(id)) : WM.send('fittings_detail', id);
    pending.then(function (payload) {
      // A plan-switch-style guard: the row may have collapsed, or another
      // row may have been opened, while this reply was in flight.
      if (token !== detailSeq || expandedId !== id || WM.current_route !== 'fittings') return;
      var value = metadataDrafts[id];
      // This is a local ACK high-water mark, not a revision invented for Python.
      // Reads begun before acceptance cannot replace its pair, even if clean.
      if (value && value.committedRevision > committedRevision) return;
      if (payload && value && !metadataDirty(value) && !value.error) {
        value.name = value.committedName = payload.name;
        value.description = value.committedDescription = payload.description;
      }
      detail = payload;
      detailError = payload ? ''
        : 'Fitting detail is unavailable or no longer exists. Close and reopen it, or use Show fitting again.';
      renderList();
    });
  }

  // ---- expanded detail --------------------------------------------------

  function detailNode(row) {
    var box = WM.make('div', 'fit-detail');
    if (!detail) {
      box.appendChild(WM.make('p', 'hint', detailError || 'Loading\u2026'));
      return box;
    }
    if (!row.deployable) {
      box.appendChild(WM.make('p', 'notice',
        'Not deployable: this fitting cannot be copied safely. Choose a different fitting to copy.'));
    }
    var content = WM.make('div', 'fit-detail-content');
    if (detail.description) {
      content.appendChild(WM.make('p', 'fit-description', detail.description));
    }
    content.appendChild(exportNode(detail));
    content.appendChild(modulesNode(detail.items || []));
    box.appendChild(content);
    var management = WM.make('div', 'fit-detail-management');
    // Compare with the visible row title, not an independently refreshed detail
    // or an unsaved metadata draft. Alias provenance remains untouched.
    var aliases = (detail.aliases || []).filter(function (alias) { return alias.name !== row.name; });
    if (aliases.length) management.appendChild(aliasesNode(aliases));
    management.appendChild(presencesNode(detail.presences || []));
    management.appendChild(metadataDisclosureNode(detail));
    var immediate = WM.make('div', 'fit-immediate');
    var immediateNote = WM.make('p', 'hint fit-immediate-note',
      'Collections and Superseded by apply immediately.');
    immediateNote.id = 'fit-immediate-note-' + detail.id;
    immediate.appendChild(immediateNote);
    immediate.appendChild(collectionsNode(detail));
    immediate.appendChild(supersessionNode(detail));
    immediate.appendChild(deleteNode(detail));
    management.appendChild(immediate);
    box.appendChild(management);
    return box;
  }

  function modulesNode(items) {
    var box = WM.make('div', 'fit-modules');
    var byLocation = {};
    items.forEach(function (item) {
      (byLocation[item.location] = byLocation[item.location] || []).push(item);
    });
    RACK_ORDER.forEach(function (location) {
      var group = byLocation[location];
      if (!group || !group.length) return;
      var rack = WM.make('div', 'fit-rack');
      rack.appendChild(WM.make('div', 'fit-rack-name',
                               RACK_LABEL[location] || location));
      group.forEach(function (item) {
        var line = WM.make('div', 'fit-item-row');
        line.appendChild(WM.make('span', 'fit-item-name',
                                 item.type_name || ('Type ' + item.type_id)));
        if (item.quantity > 1) {
          line.appendChild(WM.make('span', 'fit-item-qty', '\u00d7' + item.quantity));
        }
        rack.appendChild(line);
      });
      box.appendChild(rack);
    });
    return box;
  }

  function aliasesNode(aliases) {
    var box = WM.make('div', 'fit-aliases');
    box.appendChild(WM.make('p', 'fit-subhead', 'Also known as'));
    aliases.forEach(function (alias) {
      box.appendChild(WM.make('p', 'fit-alias-row', alias.name));
    });
    return box;
  }

  function presencesNode(presences) {
    var box = WM.make('div', 'fit-presences');
    box.appendChild(WM.make('p', 'fit-subhead',
                            presences.length ? 'On these characters'
                                             : 'Not present on any character'));
    presences.forEach(function (presence) {
      var row = WM.make('div', 'fit-presence-row');
      row.appendChild(WM.make('span', 'fit-presence-name',
                              presence.character_name
                              || ('Character ' + presence.character_id)));
      var bits = [];
      if (presence.source_name && detail && presence.source_name !== detail.name) {
        bits.push('as \u201c' + presence.source_name + '\u201d');
      }
      if (presence.first_seen_utc) {
        bits.push('first seen ' + presence.first_seen_utc.slice(0, 10));
      }
      row.appendChild(WM.make('span', 'fit-presence-meta', bits.join(' \u00b7 ')));
      box.appendChild(row);
    });
    return box;
  }

  function pruneMetadataDrafts(payload) {
    var scope = payload.filters;
    // Recover a missed delete push only when this read proves the entire
    // library is present. Paginated/filtered absence and transport failures
    // say nothing about whether an off-page fitting still exists.
    if (screenshotFixture || !payload.available || !scope || scope.collection_id !== 'all'
        || scope.search || scope.ship_type_id
        || payload.total !== (payload.rows || []).length) return;
    var live = {};
    (payload.rows || []).forEach(function (row) { live[row.id] = true; });
    Object.keys(metadataDrafts).forEach(function (id) {
      if (!live[id]) delete metadataDrafts[id];
    });
  }

  function metadataDisclosureNode(current) {
    var disclosure = WM.make('details', 'fit-metadata-disclosure');
    disclosure.setAttribute('data-entry-id', current.id);
    // A retained draft is not permission to reopen an editor the user closed.
    disclosure.open = Object.prototype.hasOwnProperty.call(metadataEditors, current.id)
      ? metadataEditors[current.id] : metadataDirty(metadataDrafts[current.id]);
    var summary = WM.make('summary', '', 'Edit metadata\u2026');
    summary.id = 'fit-metadata-summary-' + current.id;
    disclosure.appendChild(summary);
    disclosure.appendChild(metadataFieldsNode(current));
    return disclosure;
  }

  function metadataFieldsNode(current) {
    var box = WM.make('div', 'fit-metadata');
    var draft = metadataDrafts[current.id];

    var nameRow = WM.make('div', 'row');
    var nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.className = 'field';
    nameInput.id = 'fit-name-' + current.id;
    var committedName = draft ? draft.committedName : current.name;
    nameInput.value = committedName;
    var committedNameView = nameInput.value;
    var initialName = draft ? draft.name : current.name;
    nameInput.value = initialName;
    var renderedName = nameInput.value;
    var nameLabel = WM.make('label', 'lab', 'Name');
    nameLabel.setAttribute('for', nameInput.id);
    nameRow.appendChild(nameLabel);
    nameRow.appendChild(nameInput);
    box.appendChild(nameRow);

    var descRow = WM.make('div', 'row');
    var descInput = document.createElement('textarea');
    descInput.className = 'field fit-description-field';
    descInput.id = 'fit-desc-' + current.id;
    var committedDescription = draft ? draft.committedDescription : current.description;
    descInput.value = committedDescription;
    var committedDescriptionView = descInput.value;
    var initialDescription = draft ? draft.description : current.description;
    descInput.value = initialDescription;
    var renderedDescription = descInput.value;
    var descLabel = WM.make('label', 'lab', 'Description');
    descLabel.setAttribute('for', descInput.id);
    descRow.appendChild(descLabel);
    descRow.appendChild(descInput);
    box.appendChild(descRow);

    var scope = WM.make('p', 'hint', 'Save applies only to the name and description.');
    scope.id = 'fit-metadata-scope-' + current.id;
    box.appendChild(scope);
    // Free text commits on an explicit button, never on blur -- the same
    // rule Settings states for its own fields (DESIGN.md).
    var save = WM.make('button', 'btn', 'Save');
    save.id = 'fit-metadata-save-' + current.id;
    save.setAttribute('aria-describedby', scope.id);
    var status = WM.make('p', 'hint fit-metadata-status');
    status.id = 'fit-metadata-status-' + current.id;
    nameInput.setAttribute('aria-describedby', scope.id + ' ' + status.id);
    descInput.setAttribute('aria-describedby', scope.id + ' ' + status.id);
    var discard = WM.make('button', 'btn danger', 'Discard changes');
    discard.id = 'fit-metadata-discard-' + current.id;
    function updateStatus() {
      var value = metadataDrafts[current.id];
      // Disabling a focused Save blurs it to body before a later render can
      // snapshot ownership. Hand off now, never after another control took it.
      if (value && value.pending && document.activeElement === save
          && WM.current_route === 'fittings' && !copyOverlayOpen && WM.el('overlay').hidden) {
        var summary = WM.el('fit-metadata-summary-' + current.id);
        if (summary && document.contains(save) && summary.getClientRects().length) {
          summary.focus({ preventScroll: true });
        }
      }
      var dirty = metadataDirty(value);
      save.disabled = !dirty || !!(value && value.pending);
      discard.hidden = !dirty && !(value && value.error);
      discard.disabled = !!(value && value.pending);
      status.textContent = (dirty ? 'Unsaved changes' : '')
        + (value && value.pending ? ' \u2014 saving\u2026'
          : value && value.error ? (dirty ? ' \u2014 ' : '') + value.error : '');
      updateRowMetadata(current.id);
    }
    function captureDraft() {
      // Native text controls can strip line breaks or display CRLF as LF. A
      // visual revert retains the exact committed string, including after a
      // rebuild with a newer draft. Preserve an untouched draft's raw string
      // too; newly edited values still come from the control, not normalization.
      var name = nameInput.value === committedNameView ? committedName
        : nameInput.value === renderedName ? initialName : nameInput.value;
      var description = descInput.value === committedDescriptionView ? committedDescription
        : descInput.value === renderedDescription ? initialDescription : descInput.value;
      var value = metadataDrafts[current.id];
      if (!value) {
        value = { name: name, description: description,
                  committedName: current.name, committedDescription: current.description,
                  committedRevision: 0, revision: 0, pending: false, error: '' };
        metadataDrafts[current.id] = value;
      }
      value.name = name;
      value.description = description;
      value.revision += 1;
      updateStatus();
      return value;
    }
    nameInput.addEventListener('input', captureDraft);
    descInput.addEventListener('input', captureDraft);
    save.addEventListener('click', function () {
      var value = metadataDrafts[current.id];
      if (!metadataDirty(value) || value.pending) return;
      value = captureDraft();
      var revision = value.revision;
      var name = value.name;
      var description = value.description;
      value.pending = true;
      value.error = '';
      updateStatus();
      cancelExport();
      WM.send('fittings_update_metadata', current.id, name, description)
        .then(function (applied) {
          if (metadataDrafts[current.id] !== value) return;
          value.pending = false;
          // WM.send converts a rejected bridge promise to null. A push or
          // matching text alone is not an acknowledgement of this submission.
          if (applied === true) {
            // Python persists these exact strings unchanged. Keep newer typing
            // and the receipt identity even when it happens to equal this pair.
            if (revision > value.committedRevision) {
              value.committedName = name;
              value.committedDescription = description;
              value.committedRevision = revision;
            }
            // Even a just-reopened row with no detail yet can have an older
            // read pending. It must not resurrect pre-save metadata.
            if (expandedId === current.id) detailSeq += 1;
            if (detail && detail.id === current.id) {
              detail.name = name;
              detail.description = description;
            }
          } else {
            value.error = 'save not confirmed. Your draft is kept; try Save again.';
          }
          renderList();
          requestState();
        });
    });
    discard.addEventListener('click', function () {
      var value = metadataDrafts[current.id];
      if (!value || value.pending) return;
      var revision = value.revision;
      WM.confirm('Discard changes', 'Discard the unsaved name and description for '
        + '\u201c' + current.name + '\u201d?', { destructive: true })
        .then(function (ok) {
          if (!ok || metadataDrafts[current.id] !== value
              || value.pending || value.revision !== revision) return;
          delete metadataDrafts[current.id];
          renderList();
        });
    });
    var actions = WM.make('div', 'fit-metadata-actions');
    actions.appendChild(save);
    actions.appendChild(discard);
    actions.appendChild(status);
    box.appendChild(actions);
    updateStatus();
    return box;
  }

  function collectionsNode(current) {
    var box = WM.make('div', 'fit-collections');
    box.appendChild(WM.make('p', 'fit-subhead', 'Collections'));
    var custom = (STATE.collections || []).filter(function (c) {
      return isCustomCollection(c.id);
    });
    if (!custom.length) {
      box.appendChild(WM.make('p', 'hint',
                              'No collections yet. Create one from the rail.'));
      return box;
    }
    custom.forEach(function (collection) {
      var check = document.createElement('input');
      check.type = 'checkbox';
      var label = WM.make('label', 'check');
      label.appendChild(check);
      label.appendChild(WM.make('span', 'box'));
      label.appendChild(WM.make('span', '', collection.name));
      check.id = 'fit-collection-' + current.id + '-' + collection.id;
      check.checked = current.collection_ids.indexOf(collection.id) !== -1;
      check.setAttribute('aria-describedby', 'fit-immediate-note-' + current.id);
      check.addEventListener('change', function () {
        WM.send('fittings_set_membership', current.id, collection.id,
                check.checked).then(requeryIfRejected);
      });
      box.appendChild(label);
    });
    return box;
  }

  function supersessionNode(current) {
    var box = WM.make('div', 'fit-supersession');
    var label = WM.make('p', 'fit-subhead', 'Superseded by');
    label.id = 'fit-supersession-label-' + current.id;
    box.appendChild(label);
    var select = WM.make('select', 'field');
    select.id = 'fit-supersession-' + current.id;
    select.setAttribute('aria-labelledby', label.id);
    select.setAttribute('aria-describedby', 'fit-immediate-note-' + current.id);
    var none = WM.make('option', '', 'Not superseded');
    none.value = '';
    select.appendChild(none);
    // Candidates are the current PAGE's same-hull rows only -- the
    // workspace never sends the whole catalog for one dropdown. Finding a
    // superseding entry on another page means visiting that page first.
    var matched = false;
    (STATE.rows || []).forEach(function (row) {
      if (row.id === current.id || row.ship_type_id !== current.ship_type_id) return;
      var option = WM.make('option', '', row.name);
      option.value = row.id;
      if (row.id === current.superseded_by) { option.selected = true; matched = true; }
      select.appendChild(option);
    });
    if (current.superseded_by && !matched) {
      var stale = WM.make('option', '', 'A fitting not on this page');
      stale.value = current.superseded_by;
      stale.selected = true;
      select.appendChild(stale);
    }
    select.addEventListener('change', function () {
      WM.send('fittings_set_supersession', current.id, select.value || null)
        .then(requeryIfRejected);
    });
    box.appendChild(select);
    return box;
  }

  function deleteNode(current) {
    var row = WM.make('div', 'forget-row');
    var hasPresence = (current.presences || []).length > 0;
    var button = WM.make('button', 'btn danger', 'Delete fitting');
    button.disabled = hasPresence;
    button.title = hasPresence
      ? 'This fitting is still present on a character and cannot be deleted.'
      : '';
    button.addEventListener('click', function () {
      cancelExport();
      WM.confirm('Delete fitting',
                 'Delete \u201c' + current.name + '\u201d from the library? '
                 + 'This never removes it from a character.',
                 { destructive: true })
        .then(function (ok) {
          if (!ok) return;
          WM.send('fittings_delete_entry', current.id).then(function (applied) {
            if (!applied) {
              requestState();
              return;
            }
            delete selected[current.id];
            delete metadataDrafts[current.id];
            renderSelectionCount();
            expandedId = '';
            detail = null;
          });
        });
    });
    row.appendChild(button);
    if (hasPresence) row.appendChild(WM.make('span', 'hint', button.title));
    return row;
  }

  // ---- paging ------------------------------------------------------------

  function renderPager() {
    var pager = WM.el('fittings-pager');
    // Defaulted the same defensive way pageSize/totalPages already were:
    // an unavailable payload (`{available: false, warnings: [...]}`) has
    // no `page` key at all, and render() does not gate on `available`
    // before calling this, so a malformed/unavailable payload must not
    // read "Page undefined of 1" even while [hidden] is doing its job --
    // see the .fit-pager[hidden] rule this pairs with in style.css.
    var page = STATE.page || 1;
    var pageSize = STATE.page_size || 1;
    var totalPages = Math.max(1, Math.ceil((STATE.total || 0) / pageSize));
    pager.hidden = totalPages <= 1;
    WM.el('fittings-page-label').textContent =
      'Page ' + page + ' of ' + totalPages;
    WM.el('fittings-page-prev').disabled = page <= 1;
    WM.el('fittings-page-next').disabled = page >= totalPages;
  }

  WM.el('fittings-page-prev').addEventListener('click', function () {
    if (filters.page <= 1) return;
    filters.page -= 1;
    clearSelection();
    requestState();
  });

  WM.el('fittings-page-next').addEventListener('click', function () {
    filters.page += 1;
    clearSelection();
    requestState();
  });

  // ---- additive-copy overlay ---------------------------------------------

  function copyControlAvailable(node) {
    return node && document.contains(node) && !node.disabled
      && node.getClientRects().length > 0
      && window.getComputedStyle(node).visibility === 'visible';
  }

  function copyFocusable(root) {
    // Follow panel.js's controls, but also exclude hidden ancestors: the
    // overlay lives inside a route and its controls change with each phase.
    return Array.prototype.filter.call(root.querySelectorAll(
      'button:not([hidden]):not(:disabled), input:not([hidden]):not(:disabled), '
      + 'select:not([hidden]):not(:disabled), [tabindex="0"]'), copyControlAvailable);
  }

  function focusCopyTarget(id) {
    // A generic confirmation owns the topmost layer even if a copy completes
    // underneath it. Phase changes must not take its focus back.
    if (WM.el('overlay').hidden) WM.el(id).focus();
  }

  function reconcileCopyFocus() {
    if (!copyOverlayOpen || WM.current_route !== 'fittings' || !WM.el('overlay').hidden) return;
    var dialog = WM.el('fittings-copy-dialog');
    var focusable = copyFocusable(dialog);
    if (focusable.indexOf(document.activeElement) === -1) {
      (focusable[0] || dialog).focus();
    }
  }

  // A generic dialog can outlive the copy control that invoked it. When its
  // normal restoration lands behind this modal, hand focus to the CURRENT
  // copy view synchronously; never retain an old phase/generation's target.
  document.addEventListener('focusin', function (event) {
    if (!WM.el('fittings-copy-dialog').contains(event.target)) reconcileCopyFocus();
  });

  function restoreCopyFocus(target) {
    // Route-leave cleanup must not pull focus back into the hidden route.
    if (WM.current_route !== 'fittings') return;
    if (copyControlAvailable(target)) {
      target.focus();
      if (document.activeElement === target) return;
    }
    // Completion clears selection, so Copy selected is normally disabled
    // by the time results close. Find a usable control on this route instead.
    var fallback = copyFocusable(WM.el('route-fittings'));
    for (var i = 0; i < fallback.length; i += 1) {
      fallback[i].focus();
      if (document.activeElement === fallback[i]) return;
    }
  }

  function setCopyStatus(text, isError, mirrorsHeader) {
    var status = WM.el('fittings-copy-status');
    status.classList.toggle('status-announcement', !!mirrorsHeader);
    if (status.textContent !== text) status.textContent = text;
    if (isError) status.classList.add('err');
    else status.classList.remove('err');
  }

  function openCopyOverlay() {
    if (!visibleSelectedIds().length) return;
    cancelExport();
    cancelLocate();
    copyDialogGeneration += 1;
    activeCopyTicket = '';
    copyInvoker = WM.el('fittings-copy-selected');
    copyPreflightRequest = null;
    copyOverlayOpen = true;
    copyPhase = 'targets';
    copyTargets = {};
    copyPreflight = null;
    copyContext = null;
    copyReviewDirty = false;
    // Names are not unique, and refresh/filter replies can replace STATE while
    // review is open. Keep only selected hull labels, never live row references.
    copyHulls = Object.create(null);
    (STATE.rows || []).forEach(function (row) {
      if (selected[row.id]) {
        copyHulls[row.id] = row.ship_name || (row.ship_type_id ? 'Type ' + row.ship_type_id : '');
      }
    });
    alternateNames = {};
    alternateDrafts = {};
    WM.el('fittings-copy-overlay').hidden = false;
    setCopyStatus('');
    renderCopyTargets();
    renderNotices();
    focusCopyTarget('fittings-copy-close');
  }

  function closeCopyOverlay(force) {
    if (copyPhase === 'progress' && !force) return;
    if (copyContextObserver) copyContextObserver.disconnect();
    copyPreflightRequest = null;
    if (force) copyPhase = 'targets';
    activeCopyTicket = '';
    copyContext = null;
    copyHulls = Object.create(null);
    if (!copyOverlayOpen) {
      renderSelectionCount();
      return;
    }
    copyOverlayOpen = false;
    copyPreflight = null;
    renderNotices();
    var target = copyInvoker;
    copyInvoker = null;
    var overlay = WM.el('fittings-copy-overlay');
    overlay.hidden = true;
    // Also release hidden focus when a route leave has no restoration target.
    if (overlay.contains(document.activeElement)) document.activeElement.blur();
    renderSelectionCount();
    restoreCopyFocus(target);
  }

  WM.el('fittings-copy-close').addEventListener('click', function () {
    closeCopyOverlay(false);
  });

  document.addEventListener('keydown', function (event) {
    if (!copyOverlayOpen) return;
    // WM.confirm sits above this workflow. Its capture listener may already
    // have dismissed that dialog; never handle the same Escape a second time.
    if (event.defaultPrevented || !WM.el('overlay').hidden) return;
    if (event.key === 'Escape') {
      if (copyPhase === 'progress') return;
      event.preventDefault();
      closeCopyOverlay(false);
    } else if (event.key === 'Tab') {
      var dialog = WM.el('fittings-copy-dialog');
      var focusable = copyFocusable(dialog);
      if (!focusable.length) {
        event.preventDefault();
        focusCopyTarget('fittings-copy-dialog');
        return;
      }
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (focusable.indexOf(document.activeElement) === -1) {
        // The cancellation fallback (or a programmatically focused heading)
        // can remain inside the dialog after its tab stops are repopulated.
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      }
    }
  });

  var copyContextObserver = window.ResizeObserver
    ? new window.ResizeObserver(measureCopyContextClearance) : null;

  function measureCopyContextClearance(event) {
    if (!copyOverlayOpen || WM.current_route !== 'fittings') return;
    var host = WM.el('fittings-copy-body');
    Array.prototype.forEach.call(host.querySelectorAll('.fit-copy-pair-context'), function (context) {
      if (context.getClientRects().length) {
        context.parentNode.style.setProperty('--fit-copy-context-clearance',
          (context.getBoundingClientRect().height + 8) + 'px');
      }
    });
    // A breakpoint can move the active field out of view. Only a viewport resize
    // reveals it; ordinary observation must not undo deliberate wheel scrolling.
    if (!event || event.type !== 'resize' || !WM.el('overlay').hidden) return;
    var focused = document.activeElement;
    if (focused === host || !host.contains(focused) || !copyControlAvailable(focused)) return;
    var bounds = host.getBoundingClientRect();
    var rect = focused.getBoundingClientRect();
    var row = focused.closest('.fit-copy-pair');
    var context = row && row.querySelector('.fit-copy-pair-context');
    var top = Math.max(bounds.top, context ? context.getBoundingClientRect().bottom : bounds.top);
    if (rect.top < top + 4 || rect.bottom > bounds.bottom - 4) {
      focused.scrollIntoView({ block: 'nearest' });
    }
  }

  window.addEventListener('resize', measureCopyContextClearance);

  function copyButtons(review, start, cancel) {
    // Observe only this rendered, bounded pair list; replacing a phase retires
    // its headers. No global sticky height or extra scroll owner is needed.
    if (copyContextObserver) {
      copyContextObserver.disconnect();
      Array.prototype.forEach.call(WM.el('fittings-copy-body').querySelectorAll('.fit-copy-pair-context'), function (context) {
        copyContextObserver.observe(context);
      });
    }
    measureCopyContextClearance();
    // Keyboard users need the bounded pair list itself, not only its buttons.
    // Targets have their checkboxes; progress retains Cancel/dialog focus.
    WM.el('fittings-copy-body').setAttribute('tabindex',
      copyPhase === 'preflight' || copyPhase === 'results' ? '0' : '-1');
    WM.el('fittings-copy-review').hidden = !review;
    WM.el('fittings-copy-start').hidden = !start;
    WM.el('fittings-copy-cancel').hidden = !cancel;
    WM.el('fittings-copy-cancel').setAttribute('aria-describedby', 'fittings-copy-cancel-note');
    WM.el('fittings-copy-cancel-note').hidden = !cancel;
    WM.el('fittings-copy-close').disabled = cancel;
  }

  function copyEligible(character) {
    return character.status === 'enabled' && !!character.fetched_utc && !character.stale;
  }

  function copyTargetSnapshot(ids) {
    return ids.map(function (id) {
      var character = ((STATE && STATE.characters) || []).filter(function (item) {
        return item.character_id === id;
      })[0];
      return { character_id: id, character_name: character && character.character_name || '' };
    });
  }

  function acceptedCopyContext(payload, request) {
    var entryIds = [], targets = [], entries = Object.create(null), characters = Object.create(null);
    // An accepted ticket contains the backend-deduplicated Cartesian product.
    // First occurrence retains accepted order; writes and result rows are not counts of fits.
    (payload.pairs || []).forEach(function (pair) {
      if (pair.entry_id && !entries[pair.entry_id]) {
        entries[pair.entry_id] = true;
        entryIds.push(pair.entry_id);
      }
      if ((pair.character_id || pair.character_name) && !characters[pair.character_id]) {
        characters[pair.character_id] = true;
        var submitted = request.targets.filter(function (target) {
          return target.character_id === pair.character_id;
        })[0];
        targets.push({ character_id: pair.character_id,
          character_name: pair.character_name || submitted && submitted.character_name || '' });
      }
    });
    return { ticket_id: payload.ticket_id, entry_ids: entryIds, fitting_count: entryIds.length,
      targets: targets, hulls: request.hulls };
  }

  function copyHeading(context) {
    var fallback = copyPhase === 'progress' ? 'Copying fittings'
      : copyPhase === 'results' ? 'Copy results' : 'Copy fittings';
    var count = context && context.fitting_count;
    if (!count) return fallback;
    var targets = context.targets || [];
    var label = 'Copy ' + count + (!targets.length ? ' selected' : '')
      + (count === 1 ? ' fitting' : ' fittings');
    if (targets.length === 1) return label + ' to ' + copyCharacterLabel(targets[0]);
    return label + (targets.length ? ' to ' + targets.length + ' characters' : '');
  }

  function setCopyHeader(summary, selecting) {
    var context = selecting ? { fitting_count: visibleSelectedIds().length,
      targets: copyTargetSnapshot(selectedTargetIds()) } : copyContext;
    WM.el('fittings-copy-title').textContent = copyHeading(context);
    var node = WM.el('fittings-copy-summary');
    node.textContent = summary || '';
    node.hidden = !summary;
    setCopyLimit('');
  }

  function setCopyLimit(text) {
    var node = WM.el('fittings-copy-limit-summary');
    node.textContent = text;
    node.hidden = !text;
  }

  function renderCopyTargets(keepView) {
    var host = WM.el('fittings-copy-body');
    var focused = document.activeElement;
    var focusId = keepView && host.contains(focused) && focused.id;
    var scroll = host.scrollTop;
    var generation = copyDialogGeneration, request = copyPreflightRequest;
    host.textContent = '';
    if (keepView && (!copyOverlayOpen || copyPhase !== 'targets'
        || generation !== copyDialogGeneration || request !== copyPreflightRequest)) return;
    setCopyHeader('Choose target characters.', true);
    if (STATE && STATE.max_copy_writes) {
      host.appendChild(WM.make('p', 'fit-copy-limit',
        'Each copy allows up to ' + STATE.max_copy_writes + ' additions across all targets. '
        + 'Review counts only new additions; fittings already present do not count.'));
    }
    var targets = WM.make('div', 'fit-copy-targets');
    ((STATE && STATE.characters) || []).forEach(function (character) {
      var row = WM.make('div', 'fit-copy-target');
      var box = document.createElement('input');
      box.type = 'checkbox';
      var label = WM.make('label', 'check');
      label.appendChild(box);
      label.appendChild(WM.make('span', 'box'));
      label.appendChild(WM.make('span', '', character.character_name
                                || String(character.character_id)));
      box.id = 'fit-copy-target-' + character.character_id;
      box.disabled = !copyEligible(character);
      box.checked = !!copyTargets[character.character_id];
      box.addEventListener('change', function () {
        if (!copyOverlayOpen || copyPhase !== 'targets' || !host.contains(box)) return;
        if (box.checked) copyTargets[character.character_id] = true;
        else delete copyTargets[character.character_id];
        copyPreflightRequest = null;
        setCopyHeader('Choose target characters.', true);
        setCopyStatus('');
        WM.el('fittings-copy-review').disabled = !selectedTargetIds().length;
      });
      row.appendChild(label);
      if (!copyEligible(character)) {
        row.appendChild(WM.make('span', 'fit-copy-target-state',
          character.status !== 'enabled'
            ? 'Use Authenticate character\u2026 in Settings \u203a Character access.'
            : character.stale ? 'Refresh failed. Use Refresh characters.'
              : 'Use Refresh characters first.'));
      }
      targets.appendChild(row);
    });
    if (!targets.children.length) {
      targets.appendChild(WM.make(
        'p', 'hint',
        'Authenticate a character in Settings › Character access, then return and press Refresh characters.'
      ));
    }
    host.appendChild(targets);
    copyButtons(true, false, false);
    WM.el('fittings-copy-review').textContent = 'Review copy';
    WM.el('fittings-copy-review').setAttribute('aria-describedby', 'fittings-copy-body');
    WM.el('fittings-copy-review').title = '';
    WM.el('fittings-copy-review').disabled = !selectedTargetIds().length;
    if (!keepView || !copyOverlayOpen || copyPhase !== 'targets'
        || generation !== copyDialogGeneration || request !== copyPreflightRequest
        || WM.current_route !== 'fittings' || !WM.el('overlay').hidden
        || (document.activeElement !== focused && document.activeElement !== document.body)) return;
    var target = focusId && document.getElementById(focusId);
    var beforeFocusScroll = host.scrollTop;
    if (focusId) {
      // Refresh roster facts without transferring focus to another character.
      if (!copyControlAvailable(target) || !host.contains(target)) target = host;
      target.focus({ preventScroll: true });
    } else target = focused;
    if (copyOverlayOpen && copyPhase === 'targets' && generation === copyDialogGeneration
        && request === copyPreflightRequest && WM.current_route === 'fittings'
        && WM.el('overlay').hidden && document.activeElement === target
        && host.scrollTop === beforeFocusScroll) host.scrollTop = scroll;
  }

  function selectedTargetIds() {
    return Object.keys(copyTargets).filter(function (id) {
      return copyTargets[id];
    }).map(function (id) { return parseInt(id, 10); });
  }

  WM.el('fittings-copy-review').addEventListener('click', requestCopyPreflight);

  function copySelectionMatches(entryIds) {
    // Selection is keyed by canonical entry ID; row order isn't membership.
    var current = visibleSelectedIds();
    return current.length === entryIds.length && current.every(function (id) {
      return entryIds.indexOf(id) !== -1;
    });
  }

  function requestCopyPreflight() {
    var choices = {};
    if (copyPreflight && copyPreflight.requires_resolution) {
      (copyPreflight.pairs || []).forEach(function (pair) {
        if (pair.status !== 'conflict' || pair.skipped) return;
        var key = pair.entry_id + ':' + pair.character_id;
        choices[key] = alternateNames[key] === null
          ? null : (alternateNames[key] || '').trim();
      });
    }
    var reviewButton = WM.el('fittings-copy-review');
    // Native disabling blurs the invoking button. Hand off before that blur;
    // the mounted body needs no completion claim and must not move its scroll.
    if (document.activeElement === reviewButton) {
      WM.el('fittings-copy-body').focus({ preventScroll: true });
    }
    reviewButton.disabled = true;
    setCopyStatus('Checking current fittings\u2026');
    var entryIds = visibleSelectedIds();
    var targetIds = selectedTargetIds();
    var request = { entry_ids: entryIds.slice(),
      targets: copyTargetSnapshot(targetIds), hulls: Object.create(null) };
    Object.keys(copyHulls).forEach(function (id) { request.hulls[id] = copyHulls[id]; });
    var generation = copyDialogGeneration;
    copyPreflightRequest = request;
    var pending = screenshotFixture
      ? Promise.resolve(screenshotPreflight(entryIds, targetIds))
      : WM.send('fittings_preflight_copy', entryIds, targetIds, choices);
    pending.then(function (payload) {
      if (!copyOverlayOpen || generation !== copyDialogGeneration
          || copyPreflightRequest !== request) return;
      if (!payload || !payload.accepted) {
        var rejection = payload && payload.error
          || 'The copy preflight could not be checked.';
        if (copyPhase === 'targets') renderCopyTargets(true);
        else if (copyPhase === 'preflight' && copyPreflight) {
          if (copySelectionMatches(request.entry_ids)) renderCopyPreflight(true);
          // An obsolete rejection must not replace the current conflict editors.
          else updateConflictReady();
        }
        if (!copyOverlayOpen || generation !== copyDialogGeneration
            || copyPreflightRequest !== request || WM.current_route !== 'fittings') return;
        copyPreflightRequest = null;
        // Re-check after rendering: a focus handoff can apply newer state.
        // Rejections, unlike accepted tickets, own only their submitted setup.
        if (!copySelectionMatches(request.entry_ids)) {
          setCopyLimit('');
          copyButtons(true, false, false);
          if (copyPhase === 'preflight' && copyPreflight && copyPreflight.requires_resolution) {
            updateConflictReady();
          } else reviewButton.disabled = !selectedTargetIds().length;
          setCopyStatus('Review copy to check current additions.');
          return;
        }
        var ready = payload && payload.counts && payload.counts.ready;
        var limit = STATE && STATE.max_copy_writes;
        if (typeof ready === 'number' && typeof limit === 'number' && ready > limit) {
          setCopyLimit(ready + ' additions requested \u00b7 limit ' + limit
            + ' (' + (ready - limit) + ' over)');
        }
        setCopyStatus(rejection, true);
        return;
      }
      copyPreflightRequest = null;
      copyPreflight = payload;
      copyContext = acceptedCopyContext(payload, request);
      copyHulls = copyContext.hulls;
      copyReviewDirty = false;
      copyPhase = 'preflight';
      renderCopyPreflight();
    });
  }

  function preflightSummary(payload) {
    var counts = payload.counts || {};
    return payload.write_count + (payload.write_count === 1 ? ' addition planned' : ' additions planned')
      + ' \u00b7 ' + (counts.present || 0) + ' already present'
      + ' \u00b7 ' + (counts.conflict || 0) + (counts.conflict === 1 ? ' conflict' : ' conflicts')
      + ' \u00b7 ' + (counts.unavailable || 0) + ' unavailable';
  }

  function copyFittingLabel(pair) {
    var name = pair.fitting_name || (pair.entry_id ? 'Fitting ' + pair.entry_id : 'Unknown fitting');
    var hull = copyHulls[pair.entry_id];
    return name + (hull ? ' (' + hull + ')' : '');
  }

  function copyCharacterLabel(pair) {
    return pair.character_name || (pair.character_id ? 'Character ' + pair.character_id : 'Unknown character');
  }

  function copyPairsChecked(completed, total) {
    return completed + ' of ' + total
      + (total === 1 ? ' fitting/character check complete' : ' fitting/character checks complete');
  }

  function copyProgressLabel(pair) {
    var status = copyResultLabel(pair.status);
    if (!pair.entry_id && !pair.fitting_name && !pair.character_id && !pair.character_name) return status;
    return copyFittingLabel(pair) + ' \u2192 ' + copyCharacterLabel(pair) + ': ' + status;
  }

  function pairStatusText(pair) {
    if (pair.status === 'ready') return 'Ready as \u201c' + pair.chosen_name + '\u201d';
    if (pair.status === 'present') return 'Already present';
    if (pair.status === 'unavailable') return 'Unavailable' + (pair.error ? ' \u2014 ' + pair.error : '');
    return pair.skipped ? 'Conflict / skipped'
      : 'Name conflict. Enter an alternate name or Skip this pair.';
  }

  function copyPairRow(pair, index) {
    var key = pair.entry_id && pair.character_id
      ? pair.entry_id + ':' + pair.character_id : 'row-' + index;
    var row = WM.make('div', 'fit-copy-pair');
    row.id = 'fit-copy-pair-' + key;
    row.setAttribute('role', 'group');
    var context = WM.make('div', 'fit-copy-pair-context');
    var name = WM.make('span', 'fit-copy-pair-name', copyFittingLabel(pair));
    name.id = 'fit-copy-name-' + key;
    var character = WM.make('span', 'fit-copy-character', copyCharacterLabel(pair));
    character.id = 'fit-copy-character-' + key;
    context.appendChild(name);
    context.appendChild(character);
    row.appendChild(context);
    row.setAttribute('aria-labelledby', name.id + ' ' + character.id);
    return row;
  }

  function describeCopyPair(row, node, suffix) {
    node.id = row.id.replace('fit-copy-pair-', 'fit-copy-' + suffix + '-');
    var previous = row.getAttribute('aria-describedby');
    row.setAttribute('aria-describedby', (previous ? previous + ' ' : '') + node.id);
    row.appendChild(node);
  }

  function renderCopyPreflight(keepStatus) {
    var generation = copyDialogGeneration, review = copyPreflight;
    function ownsView() {
      return copyOverlayOpen && WM.current_route === 'fittings'
        && generation === copyDialogGeneration && copyPhase === 'preflight'
        && copyPreflight === review;
    }
    var host = WM.el('fittings-copy-body');
    var focused = document.activeElement;
    var ownedFocus = WM.el('overlay').hidden && host.contains(focused) && focused.id;
    var start = focused.selectionStart, end = focused.selectionEnd, direction = focused.selectionDirection;
    var scroll = host.scrollTop;
    host.textContent = '';
    // Native removal/focus events may hand this modal to another route/setup.
    if (!ownsView()) return;
    var summary = preflightSummary(copyPreflight)
      + (copyReviewDirty ? ' \u00b7 Changes pending review' : '');
    setCopyHeader(summary);
    if (!keepStatus) setCopyStatus(summary, false, true);
    host.appendChild(WM.make('p', 'hint',
      'Copies only add fittings; existing fittings are kept.'));
    var hasUnavailable = false;
    (copyPreflight.pairs || []).forEach(function (pair, index) {
      var row = copyPairRow(pair, index);
      var status = WM.make('span', 'fit-copy-detail', pairStatusText(pair));
      describeCopyPair(row, status, 'instruction');
      if (pair.status === 'unavailable') {
        row.classList.add('fit-copy-unavailable');
        hasUnavailable = true;
      }
      if (pair.status === 'conflict' && !pair.skipped) {
        row.classList.add('fit-copy-needs-resolution');
        row.appendChild(conflictResolutionNode(pair));
      }
      host.appendChild(row);
    });
    if (hasUnavailable) {
      var recovery = WM.make('p', 'hint',
        'Close this review to change the selected fittings or target characters, then review again.');
      recovery.id = 'fittings-copy-unavailable-note';
      host.appendChild(recovery);
    }
    var resolving = !!copyPreflight.requires_resolution;
    copyButtons(resolving, !resolving, false);
    WM.el('fittings-copy-review').textContent = 'Review changes';
    if (resolving) {
      var note = WM.make('p', 'hint');
      note.id = 'fittings-copy-resolution-note';
      host.appendChild(note);
      WM.el('fittings-copy-review').setAttribute('aria-describedby', note.id);
    }
    updateConflictReady();
    if (!ownsView() || !WM.el('overlay').hidden) return;
    var scrollOwner = document.activeElement;
    if (scrollOwner !== focused && scrollOwner !== document.body) return;
    if (ownedFocus) {
      var replacement = document.getElementById(ownedFocus);
      if (!copyControlAvailable(replacement) || !host.contains(replacement)) {
        replacement = copyFocusable(WM.el('fittings-copy-dialog'))[0] || WM.el('fittings-copy-dialog');
      }
      replacement.focus({ preventScroll: true });
      if (!ownsView() || !WM.el('overlay').hidden || document.activeElement !== replacement) return;
      if (replacement.type === 'text' && typeof start === 'number') {
        replacement.setSelectionRange(start, end, direction);
      }
      scrollOwner = replacement;
    }
    // A focus/selection listener can establish newer scroll synchronously too.
    if (ownsView() && WM.el('overlay').hidden && document.activeElement === scrollOwner) {
      host.scrollTop = scroll;
    }
  }

  function conflictResolutionNode(pair) {
    var key = pair.entry_id + ':' + pair.character_id;
    var resolution = WM.make('div', 'fit-copy-resolution');
    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'field fit-copy-alternate';
    input.maxLength = 50;
    input.id = 'fit-copy-alternate-' + key;
    input.setAttribute('aria-describedby', 'fit-copy-instruction-' + key);
    input.setAttribute('aria-label', 'Alternate name for ' + copyFittingLabel(pair)
                       + ' on ' + copyCharacterLabel(pair));
    input.value = typeof alternateNames[key] === 'string' ? alternateNames[key] : alternateDrafts[key] || '';
    var skip = document.createElement('input');
    skip.type = 'checkbox';
    var skipLabel = WM.make('label', 'check');
    skipLabel.appendChild(skip);
    skipLabel.appendChild(WM.make('span', 'box'));
    skipLabel.appendChild(WM.make('span', '', 'Skip this pair'));
    skip.id = 'fit-copy-skip-' + key;
    skip.setAttribute('aria-label', 'Skip this pair: ' + copyFittingLabel(pair) + ' on ' + copyCharacterLabel(pair));
    skip.setAttribute('aria-describedby', 'fit-copy-instruction-' + key);
    skip.checked = alternateNames[key] === null;
    input.disabled = skip.checked;
    function draftChanged() {
      alternateDrafts[key] = input.value;
      copyPreflightRequest = null;
      copyReviewDirty = true;
      var summary = preflightSummary(copyPreflight) + ' \u00b7 Changes pending review';
      setCopyHeader(summary);
      // Keep a rejected review's complete recovery visible while it is edited.
      if (!WM.el('fittings-copy-status').classList.contains('err')) setCopyStatus(summary, false, true);
      updateConflictReady();
    }
    input.addEventListener('input', function () {
      if (!copyOverlayOpen || copyPhase !== 'preflight'
          || !WM.el('fittings-copy-body').contains(input)) return;
      alternateNames[key] = input.value;
      draftChanged();
    });
    skip.addEventListener('change', function () {
      if (!copyOverlayOpen || copyPhase !== 'preflight'
          || !WM.el('fittings-copy-body').contains(skip)) return;
      input.disabled = skip.checked;
      alternateNames[key] = skip.checked ? null : input.value;
      draftChanged();
    });
    var field = WM.make('div', 'fit-copy-alternate-field');
    var label = WM.make('label', 'lab', 'Alternate name');
    label.setAttribute('for', input.id);
    field.appendChild(label);
    field.appendChild(input);
    resolution.appendChild(field);
    resolution.appendChild(skipLabel);
    return resolution;
  }

  function updateConflictReady() {
    if (!copyPreflight || !copyPreflight.requires_resolution) return;
    var ready = (copyPreflight.pairs || []).every(function (pair) {
      if (pair.status !== 'conflict' || pair.skipped) return true;
      var value = alternateNames[pair.entry_id + ':' + pair.character_id];
      return value === null || (typeof value === 'string' && !!value.trim());
    });
    var reason = ready ? 'Review changes to check alternate names and skips.'
      : 'Enter an alternate name or select Skip for each conflict before reviewing changes.';
    WM.el('fittings-copy-review').disabled = !ready;
    WM.el('fittings-copy-review').title = ready ? '' : reason;
    WM.el('fittings-copy-resolution-note').textContent = reason;
  }

  function presentCopyProgress(ticketId, total) {
    copyPhase = 'progress';
    activeCopyTicket = ticketId;
    var host = WM.el('fittings-copy-body');
    host.textContent = '';
    var bar = WM.make('progress');
    bar.id = 'fittings-copy-progress';
    bar.setAttribute('aria-labelledby', 'fittings-copy-title');
    host.appendChild(bar);
    updateCopyProgress(0, total);
    setCopyStatus('Starting\u2026');
    WM.el('fittings-copy-cancel').disabled = false;
    copyButtons(false, false, true);
    renderSelectionCount();
    focusCopyTarget('fittings-copy-cancel');
  }

  WM.el('fittings-copy-start').addEventListener('click', function () {
    if (screenshotFixture || !copyPreflight || copyPreflight.requires_resolution) return;
    var writes = copyPreflight.write_count || 0;
    var generation = copyDialogGeneration;
    var ticketId = copyPreflight.ticket_id;
    WM.confirm('Copy fittings',
      'Create exactly ' + writes + (writes === 1 ? ' fitting' : ' fittings')
      + ' in EVE? This only adds fittings; it never deletes or replaces one.')
      .then(function (confirmed) {
        if (screenshotFixture || !confirmed || !copyOverlayOpen
            || generation !== copyDialogGeneration
            || !copyPreflight || copyPreflight.ticket_id !== ticketId) return;
        presentCopyProgress(ticketId, copyPreflight.pairs.length);
        // Record before sending: a worker may complete before its start reply.
        var historyOperation = { ticket_id: ticketId, pending: true,
          hulls: copyHulls, context: copyContext };
        copyHistoryOperation = historyOperation;
        WM.send('fittings_start_copy', ticketId).then(function (started) {
          if (started === false && copyHistoryOperation === historyOperation) {
            // A definite refusal releases the history control, but its failure
            // push may still be in transit. Null is not proof no worker started.
            historyOperation.pending = false;
            if (WM.current_route === 'fittings') renderNotices();
          }
          if (!started && copyOverlayOpen && copyPhase === 'progress'
              && generation === copyDialogGeneration
              && activeCopyTicket === ticketId) {
            activeCopyTicket = '';
            copyPhase = 'preflight';
            setCopyStatus('The copy could not start.', true);
            renderCopyPreflight(true);
            reconcileCopyFocus();
          }
        });
      });
  });

  WM.el('fittings-copy-cancel').addEventListener('click', function () {
    if (!copyOverlayOpen || copyPhase !== 'progress') return;
    WM.el('fittings-copy-cancel').disabled = true;
    setCopyStatus('Cancelling after the current request\u2026');
    focusCopyTarget('fittings-copy-dialog');
    if (!screenshotFixture) WM.send('fittings_cancel_copy', activeCopyTicket);
  });

  function updateCopyProgress(completed, total) {
    var valid = typeof total === 'number' && isFinite(total) && total > 0
      && typeof completed === 'number' && isFinite(completed) && completed >= 0 && completed <= total;
    var bar = WM.el('fittings-copy-progress');
    bar.hidden = !valid;
    if (valid) {
      bar.max = total;
      bar.value = completed;
      bar.setAttribute('aria-valuemin', '0');
      bar.setAttribute('aria-valuemax', String(total));
      bar.setAttribute('aria-valuenow', String(completed));
    } else {
      ['value', 'max', 'aria-valuemin', 'aria-valuemax', 'aria-valuenow'].forEach(function (name) {
        bar.removeAttribute(name);
      });
    }
    setCopyHeader(valid ? copyPairsChecked(completed, total) : 'Checking fitting/character pairs\u2026');
  }

  function renderCopyProgress(completed, total, pair) {
    updateCopyProgress(completed, total);
    setCopyStatus(WM.el('fittings-copy-summary').textContent + ' \u00b7 ' + copyProgressLabel(pair));
  }

  function finishCopy(result) {
    activeCopyTicket = '';
    copyPhase = 'results';
    selected = {};
    renderSelectionCount();
    renderCopyResults(result);
    renderNotices();
  }

  function onCopyProgress(payload) {
    // Retain the outcome independently of the display guard: leaving cancels
    // after the current request, whose final result may still be Unknown.
    if (!screenshotFixture && payload.phase === 'complete'
        && copyHistoryOperation
        && payload.ticket_id === copyHistoryOperation.ticket_id) {
      lastCopyResult = payload.result || { results: [], write_count: 0 };
      lastCopyHulls = copyHistoryOperation.hulls;
      lastCopyContext = copyHistoryOperation.context;
      copyHistoryOperation = null;
      if (WM.current_route === 'fittings') renderNotices();
    }
    // Synthetic presentation is owned by the bounded fixture handler, never
    // an unrelated live progress push or a fake writer ticket.
    if (screenshotFixture || !copyOverlayOpen || copyPhase !== 'progress'
        || !activeCopyTicket || payload.ticket_id !== activeCopyTicket) return;
    if (payload.phase === 'progress') {
      renderCopyProgress(payload.completed, payload.total, payload.result);
      return;
    }
    if (payload.phase === 'complete') finishCopy(payload.result || { results: [], write_count: 0 });
  }

  function copyResultLabel(status) {
    var labels = {
      success: 'Copied', present: 'Already present',
      conflict_skipped: 'Conflict / skipped', failed: 'Failed',
      unknown: 'Needs verification', unattempted_throttle: 'Not attempted: rate limit',
      throttled: 'Copy stopped: rate limit',
      cancelled: 'Cancelled', unavailable: 'Unavailable',
      invalid_ticket: 'Preflight expired. Review the copy again.',
      needs_resolution: 'Resolve every name conflict before copying.',
      busy: 'Another fitting copy is already running.',
      shutting_down: 'Wingman is shutting down.'
    };
    return labels[status] || status;
  }

  function copyResultGuidance(status) {
    var guidance = {
      success: '',
      present: '',
      conflict_skipped: 'Choose an alternate name in a new copy review if you still want this fitting.',
      failed: 'Check the error, refresh the target, then review a new copy if still needed.',
      unknown: 'Before any retry, check each target\u2019s Personal Fittings in EVE, then refresh characters. These fittings may already exist.',
      unattempted_throttle: 'Wait for the ESI limit to clear, refresh characters, then review a new copy for fittings not attempted.',
      cancelled: 'Not attempted. Review a new copy if this fitting is still needed.',
      unavailable: 'Check the reason. For sign-in, use Authenticate character\u2026 in Settings \u203a Character access. Then refresh the target and review a new copy.',
      invalid_ticket: 'Preflight expired. Close these results and review a new copy.',
      needs_resolution: 'Close these results and resolve every name conflict in a new copy review.',
      busy: 'Another fitting copy is running. Wait for it to finish before reviewing a new copy.',
      shutting_down: 'Reopen Wingman, refresh characters, then review a new copy.',
      persistence_failed: 'Check the errors and refresh characters to reconcile remote outcomes before reviewing a new copy.',
      throttled: 'Wait for the ESI limit to clear, refresh characters, then review a new copy.'
    };
    return Object.prototype.hasOwnProperty.call(guidance, status) ? guidance[status]
      : 'Check the target in EVE and refresh characters before reviewing a new copy.';
  }

  function copyOutcomeSummary(result) {
    var counts = { success: 0, present: 0, unknown: 0, failed: 0, other: 0 };
    (result.results || []).forEach(function (pair) {
      if (['success', 'present', 'unknown', 'failed'].indexOf(pair.status) !== -1) {
        counts[pair.status] += 1;
      } else counts.other += 1;
    });
    // Lead with work that needs attention without changing pair order or outcomes.
    var parts = [];
    if (counts.unknown) parts.push(counts.unknown + (counts.unknown === 1 ? ' needs verification' : ' need verification'));
    if (counts.failed) parts.push(counts.failed + ' failed');
    if (counts.other) parts.push(counts.other + ' not copied');
    if (counts.success) parts.push(counts.success + ' copied');
    if (counts.present) parts.push(counts.present + ' already present');
    return parts.join(' \u00b7 ') || 'No copy results.';
  }

  function renderCopyResults(result) {
    var host = WM.el('fittings-copy-body');
    host.textContent = '';
    setCopyHeader(copyOutcomeSummary(result));
    host.appendChild(WM.make('p', 'hint',
      (result.write_count || 0) + (result.write_count === 1 ? ' addition attempted'
                                                         : ' additions attempted')
      + '. Nothing is retried automatically.'));
    // Shared recovery belongs above the results; each row keeps its own outcome
    // and error. Verify uncertain copies before the rate-limit advice to retry.
    var sharedRecovery = Object.create(null);
    sharedRecovery.unknown = (result.results || []).some(function (pair) {
      return pair.status === 'unknown';
    });
    sharedRecovery.unattempted_throttle = result.status === 'throttled'
      || (result.results || []).some(function (pair) {
        return pair.status === 'unattempted_throttle';
      });
    var recovery = WM.make('div', 'fit-copy-recovery');
    Object.keys(sharedRecovery).forEach(function (status) {
      if (!sharedRecovery[status]) return;
      recovery.appendChild(WM.make('p', 'hint operational-status fit-copy-guidance',
        (status === 'unknown' ? copyResultLabel(status) : 'Rate limit')
        + ': ' + copyResultGuidance(status)));
    });
    if (recovery.children.length) host.appendChild(recovery);
    if ((!(result.results || []).length || result.status !== 'complete')
        && result.status !== 'throttled') {
      host.appendChild(WM.make('p', 'notice', result.status === 'cancelled'
        ? 'Copy cancelled. Completed copies are kept; review a new copy for any remaining fittings.'
        : copyResultGuidance(result.status)));
    }
    (result.results || []).forEach(function (pair, index) {
      var row = copyPairRow(pair, index);
      var status = WM.make('span', 'fit-copy-result ' + pair.status,
                           copyResultLabel(pair.status));
      describeCopyPair(row, status, 'outcome');
      if (pair.error) describeCopyPair(row, WM.make('span', 'fit-copy-detail', pair.error), 'error');
      var guidance = copyResultGuidance(pair.status);
      if (guidance && !sharedRecovery[pair.status]) {
        describeCopyPair(row, WM.make('span', 'fit-copy-detail fit-copy-guidance', guidance), 'guidance');
      }
      host.appendChild(row);
    });
    if (result.operation_id) {
      var technical = WM.make('details', 'fit-copy-technical');
      technical.id = 'fittings-copy-technical';
      var disclosure = WM.make('summary', '', 'Technical details');
      disclosure.setAttribute('tabindex', '0');
      technical.appendChild(disclosure);
      var operation = WM.make('p', '', 'Operation ID: ' + result.operation_id);
      operation.id = 'fittings-copy-operation-id';
      technical.appendChild(operation);
      host.appendChild(technical);
    }
    var hasOutcomes = !!(result.results || []).length || result.status === 'complete';
    setCopyStatus(hasOutcomes ? copyOutcomeSummary(result) : copyResultLabel(result.status), false, hasOutcomes);
    copyButtons(false, false, false);
    WM.el('fittings-copy-close').disabled = false;
    focusCopyTarget('fittings-copy-close');
  }

}());
