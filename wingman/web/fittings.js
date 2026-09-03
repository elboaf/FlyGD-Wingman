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
 * -- never a second, competing state shape -- and this file's only
 * reaction to it is to re-ask for whatever it is currently looking at.
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
  var selected = {};       // entry_id -> true, pruned to the rendered page
  var progress = null;     // last refresh onFittingsProgress payload
  var copyOverlayOpen = false;
  var copyPhase = 'targets';
  var copyTargets = {};
  var copyPreflight = null;
  var alternateNames = {};
  var refreshInFlight = false; // optimistic, until the next full re-fetch confirms it
  var searchDebounce = null;
  var charactersOverlayOpen = false;
  var confirmingForgetId = 0;

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

  function requestState() {
    WM.send('fittings_state', currentFilters()).then(function (payload) {
      if (!payload) { asked = false; return; }
      render(payload);
    });
  }

  function render(payload) {
    STATE = payload;
    if (!payload.refreshing) progress = null;
    refreshInFlight = payload.refreshing;
    renderCounts();
    renderCollections();
    renderHead();
    renderNotices();
    renderShipFilterOptions();
    renderFilterBar();
    pruneSelection(payload.rows || []);
    renderList();
    renderPager();
    renderRailButtons();
    if (charactersOverlayOpen) renderCharactersOverlay();
    if (expandedId) requestDetail(expandedId);
  }

  WM.handle('onFittingsChanged', function () {
    // A semantic "something changed" signal, never a payload to render
    // directly -- see the design doc's "no whole-library pushes". The
    // page re-asks for whatever it is currently looking at.
    if (asked) requestState();
  });

  WM.handle('onFittingsProgress', function (payload) {
    if (payload && payload.kind === 'copy') {
      onCopyProgress(payload);
      return;
    }
    progress = payload;
    refreshInFlight = true;
    // A progress push races the first fittings_state() reply in theory
    // (independent async paths -- clicking Refresh does not wait on the
    // initial state fetch to land): nothing to update yet if STATE is
    // still null, and the next progress tick or the pending state reply
    // renders it once there is something to render into.
    if (!STATE) return;
    renderNotices();
    renderRailButtons();
    if (charactersOverlayOpen) renderCharactersOverlay();
  });

  document.addEventListener('wm:route', function (event) {
    if (event.detail !== 'fittings') {
      // Cleanup for the one thing this route arms outside its own markup:
      // a debounced search request, and the Characters overlay, which
      // floats above the route and must not still be open on return to a
      // completely different screen.
      if (searchDebounce) { clearTimeout(searchDebounce); searchDebounce = null; }
      closeCharactersOverlay();
      if (copyPhase === 'progress') WM.send('fittings_cancel_copy');
      closeCopyOverlay(true);
      clearSelection();
      return;
    }
    if (asked) return;
    asked = true;
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
        WM.send('fittings_rename_collection', current.id, wanted);
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

  // ---- main pane header, notices, filters ------------------------------

  function renderHead() {
    var current = currentCollection();
    WM.el('fittings-collection-name').textContent = current ? current.name : 'All fittings';
    var count = STATE.total || 0;
    WM.el('fittings-collection-count').textContent =
      count + (count === 1 ? ' fitting' : ' fittings');
  }

  function renderNotices() {
    var host = WM.el('fittings-notices');
    host.textContent = '';
    var lines = [];
    if (STATE.refreshing) lines.push('Refreshing characters\u2026');
    if (progress && progress.total) {
      lines.push('Refreshed ' + progress.completed + ' of '
                 + progress.total + ' characters');
    }
    (STATE.warnings || []).forEach(function (text) { lines.push(text); });
    host.hidden = !lines.length;
    lines.forEach(function (text) { host.appendChild(WM.make('p', 'notice', text)); });
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

  // ---- the list, one page at a time ------------------------------------

  function collectionNames(ids) {
    var byId = {};
    (STATE.collections || []).forEach(function (c) { byId[c.id] = c.name; });
    return ids.map(function (id) { return byId[id] || id; }).join(', ');
  }

  function renderList() {
    var host = WM.el('fittings-list');
    var empty = WM.el('fittings-empty');
    host.textContent = '';
    var rows = STATE.rows || [];
    if (!rows.length) {
      empty.hidden = false;
      var filtered = !!(filters.search.trim() || filters.ship_type_id
                        || filters.collection_id !== 'all');
      empty.textContent = filtered
        ? 'No fittings match the current filters.'
        : 'No fittings yet. Enable and refresh a character from '
          + '\u201cCharacters\u2026\u201d to import from EVE.';
      return;
    }
    empty.hidden = true;
    rows.forEach(function (row) { host.appendChild(rowNode(row)); });
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
  }

  WM.el('fittings-copy-selected').addEventListener('click', openCopyOverlay);

  function rowNode(row) {
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
    box.checked = !!selected[row.id];
    box.addEventListener('change', function () {
      if (box.checked) { selected[row.id] = true; } else { delete selected[row.id]; }
      renderSelectionCount();
    });
    top.appendChild(label);

    var toggle = WM.make('button', 'fit-row-toggle');
    toggle.setAttribute('aria-expanded', expandedId === row.id ? 'true' : 'false');
    toggle.appendChild(WM.make('span', 'chev',
                               expandedId === row.id ? '\u25be' : '\u25b8'));
    toggle.appendChild(WM.make('span', 'fit-name', row.name));
    toggle.appendChild(WM.make('span', 'fit-ship',
                               row.ship_name || ('Type ' + row.ship_type_id)));
    var meta = [];
    meta.push(row.presence_count
             + (row.presence_count === 1 ? ' character' : ' characters'));
    if (row.collection_ids.length) meta.push(collectionNames(row.collection_ids));
    if (row.superseded_by) meta.push('Superseded');
    if (!row.deployable) meta.push('Not deployable');
    toggle.appendChild(WM.make('span', 'fit-meta', meta.join(' \u00b7 ')));
    toggle.addEventListener('click', function () { toggleRow(row.id); });
    top.appendChild(toggle);

    node.appendChild(top);
    if (expandedId === row.id) node.appendChild(detailNode(row));
    return node;
  }

  function toggleRow(id) {
    if (expandedId === id) {
      expandedId = '';
      detail = null;
      renderList();
      return;
    }
    expandedId = id;
    detail = null;
    renderList();
    requestDetail(id);
  }

  function requestDetail(id) {
    detailSeq += 1;
    var token = detailSeq;
    WM.send('fittings_detail', id).then(function (payload) {
      // A plan-switch-style guard: the row may have collapsed, or another
      // row may have been opened, while this reply was in flight.
      if (token !== detailSeq || expandedId !== id) return;
      detail = payload;
      renderList();
    });
  }

  // ---- expanded detail --------------------------------------------------

  function detailNode(row) {
    var box = WM.make('div', 'fit-detail');
    if (!detail) {
      box.appendChild(WM.make('p', 'hint', 'Loading\u2026'));
      return box;
    }
    if (detail.description) {
      box.appendChild(WM.make('p', 'fit-description', detail.description));
    }
    box.appendChild(modulesNode(detail.items || []));
    if ((detail.aliases || []).length > 1) box.appendChild(aliasesNode(detail.aliases));
    box.appendChild(presencesNode(detail.presences || []));
    box.appendChild(metadataFieldsNode(detail));
    box.appendChild(collectionsNode(detail));
    box.appendChild(supersessionNode(detail));
    box.appendChild(deleteNode(detail));
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
        bits.push('seen ' + presence.first_seen_utc.slice(0, 10));
      }
      row.appendChild(WM.make('span', 'fit-presence-meta', bits.join(' \u00b7 ')));
      box.appendChild(row);
    });
    return box;
  }

  function metadataFieldsNode(current) {
    var box = WM.make('div', 'fit-metadata');

    var nameRow = WM.make('div', 'skills-detail-row');
    var nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.className = 'field';
    nameInput.id = 'fit-name-' + current.id;
    nameInput.value = current.name;
    var nameLabel = WM.make('label', '', 'Name');
    nameLabel.setAttribute('for', nameInput.id);
    nameRow.appendChild(nameLabel);
    nameRow.appendChild(nameInput);
    box.appendChild(nameRow);

    var descRow = WM.make('div', 'skills-detail-row');
    var descInput = document.createElement('textarea');
    descInput.className = 'field fit-description-field';
    descInput.id = 'fit-desc-' + current.id;
    descInput.value = current.description;
    var descLabel = WM.make('label', '', 'Description');
    descLabel.setAttribute('for', descInput.id);
    descRow.appendChild(descLabel);
    descRow.appendChild(descInput);
    box.appendChild(descRow);

    // Free text commits on an explicit button, never on blur -- the same
    // rule Settings states for its own fields (DESIGN.md).
    var save = WM.make('button', 'btn', 'Save');
    save.addEventListener('click', function () {
      WM.send('fittings_update_metadata', current.id, nameInput.value,
              descInput.value);
    });
    box.appendChild(save);
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
      check.checked = current.collection_ids.indexOf(collection.id) !== -1;
      check.addEventListener('change', function () {
        WM.send('fittings_set_membership', current.id, collection.id,
                check.checked);
      });
      box.appendChild(label);
    });
    return box;
  }

  function supersessionNode(current) {
    var box = WM.make('div', 'fit-supersession');
    box.appendChild(WM.make('p', 'fit-subhead', 'Superseded by'));
    var select = WM.make('select', 'field');
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
      WM.send('fittings_set_supersession', current.id, select.value || null);
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
      WM.confirm('Delete fitting',
                 'Delete \u201c' + current.name + '\u201d from the library? '
                 + 'This never removes it from a character.',
                 { destructive: true })
        .then(function (ok) {
          if (!ok) return;
          WM.send('fittings_delete_entry', current.id).then(function () {
            delete selected[current.id];
            renderSelectionCount();
            expandedId = '';
            detail = null;
          });
        });
    });
    row.appendChild(button);
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

  function openCopyOverlay() {
    if (!visibleSelectedIds().length) return;
    copyOverlayOpen = true;
    copyPhase = 'targets';
    copyTargets = {};
    copyPreflight = null;
    alternateNames = {};
    WM.el('fittings-copy-overlay').hidden = false;
    WM.el('fittings-copy-title').textContent = 'Copy fittings';
    WM.el('fittings-copy-status').textContent = '';
    renderCopyTargets();
    WM.el('fittings-copy-close').focus();
  }

  function closeCopyOverlay(force) {
    if (!copyOverlayOpen || (copyPhase === 'progress' && !force)) return;
    copyOverlayOpen = false;
    copyPreflight = null;
    WM.el('fittings-copy-overlay').hidden = true;
  }

  WM.el('fittings-copy-close').addEventListener('click', function () {
    closeCopyOverlay(false);
  });

  document.addEventListener('keydown', function (event) {
    if (!copyOverlayOpen || event.key !== 'Escape' || copyPhase === 'progress') return;
    event.preventDefault();
    closeCopyOverlay(false);
    WM.el('fittings-copy-selected').focus();
  });

  function copyButtons(review, start, cancel) {
    WM.el('fittings-copy-review').hidden = !review;
    WM.el('fittings-copy-start').hidden = !start;
    WM.el('fittings-copy-cancel').hidden = !cancel;
    WM.el('fittings-copy-close').disabled = cancel;
  }

  function copyEligible(character) {
    return character.status === 'enabled' && !!character.fetched_utc && !character.stale;
  }

  function renderCopyTargets() {
    var host = WM.el('fittings-copy-body');
    host.textContent = '';
    host.appendChild(WM.make('p', 'fit-copy-summary',
      visibleSelectedIds().length + ' selected. Choose target characters.'));
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
      box.disabled = !copyEligible(character);
      box.checked = !!copyTargets[character.character_id];
      box.addEventListener('change', function () {
        if (box.checked) copyTargets[character.character_id] = true;
        else delete copyTargets[character.character_id];
        WM.el('fittings-copy-review').disabled = !selectedTargetIds().length;
      });
      row.appendChild(label);
      if (!copyEligible(character)) {
        row.appendChild(WM.make('span', 'fit-copy-target-state',
          character.status !== 'enabled' ? 'Fittings not enabled'
            : character.stale ? 'Refresh failed' : 'Refresh required'));
      }
      targets.appendChild(row);
    });
    if (!targets.children.length) {
      targets.appendChild(WM.make('p', 'hint', 'No EVE characters available.'));
    }
    host.appendChild(targets);
    copyButtons(true, false, false);
    WM.el('fittings-copy-review').textContent = 'Review copy';
    WM.el('fittings-copy-review').disabled = !selectedTargetIds().length;
  }

  function selectedTargetIds() {
    return Object.keys(copyTargets).filter(function (id) {
      return copyTargets[id];
    }).map(function (id) { return parseInt(id, 10); });
  }

  WM.el('fittings-copy-review').addEventListener('click', requestCopyPreflight);

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
    WM.el('fittings-copy-review').disabled = true;
    WM.el('fittings-copy-status').textContent = 'Checking current fittings\u2026';
    WM.send('fittings_preflight_copy', visibleSelectedIds(), selectedTargetIds(), choices)
      .then(function (payload) {
        if (!copyOverlayOpen) return;
        if (!payload || !payload.accepted) {
          var rejection = payload && payload.error
            || 'The copy preflight could not be checked.';
          if (copyPhase === 'targets') renderCopyTargets();
          else if (copyPhase === 'preflight' && copyPreflight) renderCopyPreflight();
          WM.el('fittings-copy-status').textContent = rejection;
          return;
        }
        copyPreflight = payload;
        WM.el('fittings-copy-status').textContent = '';
        copyPhase = 'preflight';
        renderCopyPreflight();
      });
  }

  function preflightSummary(payload) {
    var counts = payload.counts || {};
    return payload.write_count + (payload.write_count === 1 ? ' remote write' : ' remote writes')
      + ' \u00b7 ' + (counts.present || 0) + ' already present'
      + ' \u00b7 ' + (counts.conflict || 0) + ' conflicts'
      + ' \u00b7 ' + (counts.unavailable || 0) + ' unavailable';
  }

  function pairStatusText(pair) {
    if (pair.status === 'ready') return 'Ready as \u201c' + pair.chosen_name + '\u201d';
    if (pair.status === 'present') return 'Already present';
    if (pair.status === 'unavailable') return pair.error || 'Unavailable';
    return pair.skipped ? 'Conflict / skipped' : 'Name conflict';
  }

  function renderCopyPreflight() {
    var host = WM.el('fittings-copy-body');
    host.textContent = '';
    host.appendChild(WM.make('p', 'fit-copy-summary', preflightSummary(copyPreflight)));
    (copyPreflight.pairs || []).forEach(function (pair) {
      var row = WM.make('div', 'fit-copy-pair');
      row.appendChild(WM.make('span', 'fit-copy-pair-name', pair.fitting_name));
      row.appendChild(WM.make('span', 'fit-copy-character', pair.character_name));
      row.appendChild(WM.make('span', 'fit-copy-detail', pairStatusText(pair)));
      if (pair.status === 'conflict' && !pair.skipped) {
        row.appendChild(conflictResolutionNode(pair));
      }
      host.appendChild(row);
    });
    var resolving = !!copyPreflight.requires_resolution;
    copyButtons(resolving, !resolving, false);
    WM.el('fittings-copy-review').textContent = 'Review changes';
    updateConflictReady();
  }

  function conflictResolutionNode(pair) {
    var key = pair.entry_id + ':' + pair.character_id;
    var resolution = WM.make('div', 'fit-copy-resolution');
    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'field fit-copy-alternate';
    input.maxLength = 50;
    input.placeholder = 'Alternate name';
    input.setAttribute('aria-label', 'Alternate name for ' + pair.fitting_name
                       + ' on ' + pair.character_name);
    input.value = typeof alternateNames[key] === 'string' ? alternateNames[key] : '';
    var skip = document.createElement('input');
    skip.type = 'checkbox';
    var skipLabel = WM.make('label', 'check');
    skipLabel.appendChild(skip);
    skipLabel.appendChild(WM.make('span', 'box'));
    skipLabel.appendChild(WM.make('span', '', 'Skip this pair'));
    skip.checked = alternateNames[key] === null;
    input.disabled = skip.checked;
    input.addEventListener('input', function () {
      alternateNames[key] = input.value;
      updateConflictReady();
    });
    skip.addEventListener('change', function () {
      input.disabled = skip.checked;
      alternateNames[key] = skip.checked ? null : input.value;
      updateConflictReady();
    });
    resolution.appendChild(input);
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
    WM.el('fittings-copy-review').disabled = !ready;
  }

  WM.el('fittings-copy-start').addEventListener('click', function () {
    if (!copyPreflight || copyPreflight.requires_resolution) return;
    var writes = copyPreflight.write_count || 0;
    WM.confirm('Copy fittings',
      'Create exactly ' + writes + (writes === 1 ? ' fitting' : ' fittings')
      + ' in EVE? This only adds fittings; it never deletes or replaces one.')
      .then(function (confirmed) {
        if (!confirmed || !copyOverlayOpen) return;
        copyPhase = 'progress';
        WM.el('fittings-copy-title').textContent = 'Copying fittings';
        WM.el('fittings-copy-body').textContent = '';
        WM.el('fittings-copy-body').appendChild(WM.make('p', 'fit-copy-summary',
          '0 of ' + copyPreflight.pairs.length + ' pairs checked'));
        WM.el('fittings-copy-status').textContent = 'Starting\u2026';
        copyButtons(false, false, true);
        renderSelectionCount();
        WM.send('fittings_start_copy', copyPreflight.ticket_id).then(function (started) {
          if (!started && copyOverlayOpen) {
            copyPhase = 'preflight';
            WM.el('fittings-copy-status').textContent = 'The copy could not start.';
            renderCopyPreflight();
          }
        });
      });
  });

  WM.el('fittings-copy-cancel').addEventListener('click', function () {
    WM.el('fittings-copy-cancel').disabled = true;
    WM.el('fittings-copy-status').textContent = 'Cancelling after the current request\u2026';
    WM.send('fittings_cancel_copy');
  });

  function onCopyProgress(payload) {
    if (!copyOverlayOpen) return;
    if (payload.phase === 'progress') {
      WM.el('fittings-copy-body').textContent = '';
      WM.el('fittings-copy-body').appendChild(WM.make('p', 'fit-copy-summary',
        payload.completed + ' of ' + payload.total + ' pairs checked'));
      WM.el('fittings-copy-status').textContent = copyResultLabel(payload.result.status);
      return;
    }
    if (payload.phase === 'complete') {
      copyPhase = 'results';
      selected = {};
      renderSelectionCount();
      renderCopyResults(payload.result || { results: [], write_count: 0 });
    }
  }

  function copyResultLabel(status) {
    var labels = {
      success: 'Success', present: 'Already present',
      conflict_skipped: 'Conflict / skipped', failed: 'Failed',
      unknown: 'Unknown', unattempted_throttle: 'Unattempted due to throttle',
      cancelled: 'Cancelled', unavailable: 'Unavailable',
      invalid_ticket: 'Preflight expired. Review the copy again.',
      needs_resolution: 'Resolve every name conflict before copying.',
      busy: 'Another fitting copy is already running.',
      shutting_down: 'Wingman is shutting down.'
    };
    return labels[status] || status;
  }

  function renderCopyResults(result) {
    var host = WM.el('fittings-copy-body');
    host.textContent = '';
    WM.el('fittings-copy-title').textContent = 'Copy results';
    host.appendChild(WM.make('p', 'fit-copy-summary',
      result.write_count + (result.write_count === 1 ? ' remote write attempted'
                                                     : ' remote writes attempted')));
    (result.results || []).forEach(function (pair) {
      var row = WM.make('div', 'fit-copy-pair');
      row.appendChild(WM.make('span', 'fit-copy-pair-name', pair.fitting_name));
      row.appendChild(WM.make('span', 'fit-copy-character', pair.character_name));
      var status = WM.make('span', 'fit-copy-result ' + pair.status,
                           copyResultLabel(pair.status));
      row.appendChild(status);
      if (pair.error) row.appendChild(WM.make('span', 'fit-copy-detail', pair.error));
      host.appendChild(row);
    });
    WM.el('fittings-copy-status').textContent = result.operation_id
      ? 'Operation ' + result.operation_id : copyResultLabel(result.status);
    copyButtons(false, false, false);
    WM.el('fittings-copy-close').disabled = false;
  }

  // ---- the Characters overlay --------------------------------------------
  //
  // App-owned, not the shared #overlay/#dialog confirm/prompt layer
  // (panel.js's queue answers one question at a time; this shows a whole
  // roster). A page-initiated confirmation inside it still goes through
  // WM.confirm, never a browser dialog.

  WM.el('fittings-characters-open').addEventListener('click', function () {
    charactersOverlayOpen = true;
    WM.el('fittings-characters-overlay').hidden = false;
    renderCharactersOverlay();
  });

  WM.el('fittings-characters-close').addEventListener('click', closeCharactersOverlay);

  function closeCharactersOverlay() {
    if (!charactersOverlayOpen) return;
    charactersOverlayOpen = false;
    confirmingForgetId = 0;
    WM.el('fittings-characters-overlay').hidden = true;
  }

  function renderCharactersOverlay() {
    var host = WM.el('fittings-characters-body');
    host.textContent = '';
    var chars = (STATE && STATE.characters) || [];
    if (!chars.length) {
      host.appendChild(WM.make('p', 'hint',
                               'No EVE characters yet. Add one from Skills.'));
      return;
    }
    chars.forEach(function (ch) { host.appendChild(characterRowNode(ch)); });
  }

  function characterStatusLabel(ch) {
    if (ch.status === 'reauthenticate') return 'Needs re-authentication';
    if (ch.status === 'enable') return 'Skills only';
    if (ch.stale) return 'Stale';
    if (ch.fetched_utc) return 'Refreshed';
    return 'Never refreshed';
  }

  function characterRowNode(ch) {
    var row = WM.make('div', 'fit-char-row');
    row.appendChild(WM.make('span', 'fit-char-name',
                            ch.character_name || String(ch.character_id)));
    row.appendChild(WM.make('span', 'fit-char-status', characterStatusLabel(ch)));

    var actions = WM.make('div', 'fit-char-actions');
    if (ch.status === 'reauthenticate') {
      actions.appendChild(WM.make('span', 'hint',
                                  'Re-authenticate this character from Skills first.'));
    } else if (ch.status === 'enable') {
      var enable = WM.make('button', 'btn', 'Enable fittings');
      enable.addEventListener('click', function () {
        WM.send('fittings_enable_character', ch.character_id);
      });
      actions.appendChild(enable);
    } else if (ch.status === 'enabled') {
      var refresh = WM.make('button', 'btn', 'Refresh');
      refresh.disabled = refreshInFlight;
      refresh.addEventListener('click', function () {
        refreshInFlight = true;
        renderRailButtons();
        renderCharactersOverlay();
        WM.send('fittings_refresh', [ch.character_id]);
      });
      actions.appendChild(refresh);
    }

    if (confirmingForgetId === ch.character_id) {
      actions.appendChild(WM.make('span', 'forget-warn',
                                  'Forget ' + (ch.character_name || 'this character')
                                  + '? You will have to sign in to EVE again to add '
                                  + 'it back.'));
      var yes = WM.make('button', 'btn danger', 'Forget');
      yes.addEventListener('click', function () {
        confirmingForgetId = 0;
        WM.send('fittings_forget_character', ch.character_id).then(requestState);
      });
      var no = WM.make('button', 'btn', 'Cancel');
      no.addEventListener('click', function () {
        confirmingForgetId = 0;
        renderCharactersOverlay();
      });
      actions.appendChild(yes);
      actions.appendChild(no);
    } else {
      var forget = WM.make('button', 'btn danger', 'Forget');
      forget.addEventListener('click', function () {
        confirmingForgetId = ch.character_id;
        renderCharactersOverlay();
      });
      actions.appendChild(forget);
    }

    row.appendChild(actions);
    if (ch.error) row.appendChild(WM.make('p', 'row-error', ch.error));
    return row;
  }
}());
