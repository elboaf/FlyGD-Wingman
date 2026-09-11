/* FlyGD Wingman — standalone fleet combat display. */
(function () {
  'use strict';

  // Capture creation identity once — delayed continuations must not adopt a
  // replacement window's token after a hash change.
  var pageMatch = /^#fleet-page=([0-9a-f]{64})$/.exec(window.location.hash);
  var pageId = pageMatch ? pageMatch[1] : null;

  var ready = new Promise(function (resolve) {
    if (window.pywebview && window.pywebview.api) { resolve(); return; }
    window.addEventListener('pywebviewready', function () { resolve(); },
                            { once: true });
  });
  var lastRevision = -1;
  var resizeTimer = 0;
  var resizePending = false;
  var resizeSettling = false;
  var resizeSettleVersion = 0;
  var widthFeedbackVersion = 0;
  var widthFeedbackAccepted = 0;
  var fitDeferred = false;
  var headerDrag = null;
  var dragPending = false;
  var dragVersion = 0;
  var dragActionVersion = 0;
  var dragWork = Promise.resolve(null);
  var activationPromise = null;
  var activationActive = false;

  function send(method) {
    if (!pageId) return Promise.resolve(null);
    var args = [pageId].concat(Array.prototype.slice.call(arguments, 1));
    return ready.then(function () {
      var api = window.pywebview && window.pywebview.api;
      var fn = api && api[method];
      if (typeof fn !== 'function') return null;
      return fn.apply(api, args);
    }).catch(function (err) {
      console.error('bridge: ' + method + ' failed', err);
      return null;
    });
  }

  function currentContentWidth() {
    var shell = document.querySelector('.fleet-shell');
    if (!shell) return 0;
    var rect = shell.getBoundingClientRect ? shell.getBoundingClientRect() : null;
    var width = rect && rect.width;
    if (typeof width !== 'number' || !isFinite(width) || width <= 0) {
      width = shell.offsetWidth;
    }
    return Math.max(0, Math.round(width || 0));
  }

  function titleNodes() {
    return {
      end: document.getElementById('fleet-title-end'),
      health: document.getElementById('fleet-health'),
      error: document.getElementById('fleet-title-error')
    };
  }

  function showTitleError(text) {
    var nodes = titleNodes();
    if (!nodes.error || !nodes.health) return;
    var message = text || '';
    setText(nodes.error, message);
    nodes.error.hidden = !message;
    nodes.health.hidden = Boolean(message);
    if (nodes.end && nodes.end.classList) {
      nodes.end.classList.toggle('error-active', Boolean(message));
    }
  }

  function clearTitleError() {
    showTitleError('');
  }

  function setText(node, text) {
    if (!node) return;
    text = text || '';
    if (node.textContent !== text) node.textContent = text;
  }

  function isFieldResult(result) {
    return !!result && typeof result === 'object'
      && typeof result.applied === 'boolean'
      && typeof result.persisted === 'boolean'
      && Object.prototype.hasOwnProperty.call(result, 'error')
      && (result.error === null || typeof result.error === 'string');
  }

  function fieldResult(result, failureMessage) {
    if (!isFieldResult(result)) {
      showTitleError(failureMessage);
      return null;
    }
    if (result.error) showTitleError(result.error);
    else clearTitleError();
    return result;
  }

  function acceptWidthFeedback(result, version, actionVersion) {
    if (actionVersion !== dragActionVersion || version < widthFeedbackAccepted) return;
    // A viewport event may be our own clamp before the save reply. Transient
    // 'resizing' also covers position-only headers and canceled gestures; only
    // an actual newer field outcome supersedes that reply (Reset/Hide above).
    if (isFieldResult(result)) {
      widthFeedbackAccepted = version;
      fieldResult(result, 'Could not save Fleet Bar width.');
    }
  }

  function tableHeightCap() {
    var table = document.querySelector('.fleet-table');
    if (!table) return;
    // Use monitor bounds, not viewport height: the native window starts at
    // 90px and grows to content. A vh cap would trap it at that initial size.
    table.style.maxHeight = Math.max(30, Math.min(480, screen.availHeight - 100)) + 'px';
  }

  function fitHeight() {
    if (resizePending || resizeSettling || dragPending) {
      fitDeferred = true;
      return Promise.resolve(null);
    }
    var shell = document.querySelector('.fleet-shell');
    if (!shell) return Promise.resolve(null);
    tableHeightCap();
    return send('fit_fleet_bar_height', shell.offsetHeight);
  }

  function drainDeferredFit() {
    if (!fitDeferred) return Promise.resolve(null);
    fitDeferred = false;
    return fitHeight();
  }

  function settleResize() {
    resizeTimer = 0;
    resizePending = false;
    if (dragPending) return Promise.resolve(null);
    resizeSettling = true;
    var version = ++resizeSettleVersion;
    var feedbackVersion = ++widthFeedbackVersion;
    var actionVersion = dragActionVersion;
    // A width equality cannot prove intent: a genuine second gesture may
    // return to the session-only width. Native provenance owns that decision.
    return send('settle_fleet_bar_resize', currentContentWidth(), window.screenX).then(function (result) {
      acceptWidthFeedback(result, feedbackVersion, actionVersion);
      if (version !== resizeSettleVersion) return null;
      resizeSettling = false;
      if (result && result.status === 'resizing') {
        // A paused native drag need not emit another resize on release. Keep
        // one 150ms timer until EXIT, superseded by any newer resize/action.
        scheduleResizeSettlement();
        return null;
      }
      if (!isFieldResult(result) && (!result || result.status !== 'ignored')) {
        fieldResult(result, 'The Fleet Bar could not be resized.');
      }
      // Ignored geometry feedback is not successful persistence and must not
      // retire a session-only warning from the action that caused it.
      return drainDeferredFit();
    });
  }

  function scheduleResizeSettlement() {
    ++resizeSettleVersion;
    resizePending = true;
    fitDeferred = true;
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(settleResize, 150);
  }

  function cancelResizeSettlement(supersede) {
    if (supersede !== false) ++resizeSettleVersion;
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = 0;
    resizePending = false;
    resizeSettling = false;
  }

  function bindHeaderDrag() {
    var header = document.getElementById('fleet-drag');
    if (!header) return;
    header.addEventListener('mousedown', function (event) {
      if (event.button !== 0 || headerDrag) return;
      var current = { version: ++dragVersion, actionVersion: dragActionVersion };
      var x = window.screenX;
      var y = window.screenY;
      headerDrag = current;
      dragPending = true;
      fitDeferred = true;
      // Moving does not supersede the result of an already submitted width
      // save. Keep its feedback, but postpone further resize work until end.
      cancelResizeSettlement(false);
      // Do not intercept or implement movement. pywebview customize.js arms
      // its own mousemove handler when this event bubbles to document.body.
      // Serialize admission/end so delayed bridge replies cannot swap owners.
      current.start = dragWork.then(function () {
        if (current.version !== dragVersion) return null;
        return send('save_fleet_bar_pos', x, y, 'begin');
      });
      dragWork = current.start;
    });
    window.addEventListener('mouseup', function () {
      var current = headerDrag;
      if (!current) return;
      headerDrag = null;
      var x = window.screenX;
      var y = window.screenY;
      dragWork = current.start.then(function (started) {
        if (!started || started.status !== 'dragging') return null;
        current.feedbackVersion = ++widthFeedbackVersion;
        return send('save_fleet_bar_pos', x, y, 'end', started.drag_id);
      }).then(function (result) {
        // Another position-only drag cannot retire a failed width save. The
        // serialized chain keeps width outcomes ordered; Reset/Hide supersedes
        // them immediately, even while waiting for that chain to finish.
        acceptWidthFeedback(result, current.feedbackVersion, current.actionVersion);
        if (current.version !== dragVersion) return null;
        dragPending = false;
        scheduleResizeSettlement();
        return null;
      });
    });
  }

  function cancelHeaderDrag() {
    ++dragVersion;
    ++dragActionVersion;
    headerDrag = null;
    dragPending = false;
    cancelResizeSettlement();
    // Reset/Hide follows any already issued admission/end, then the API
    // retires its private owner. No late begin can land after the action.
    return dragWork;
  }

  function focusAction(node) {
    if (node && typeof node.focus === 'function') node.focus();
  }

  function activateForAction(node) {
    if (activationActive) {
      clearTitleError();
      focusAction(node);
      return Promise.resolve(true);
    }
    if (!activationPromise) {
      activationPromise = send('activate_fleet_bar').then(function (activated) {
        activationPromise = null;
        activationActive = activated === true;
        if (!activationActive) {
          showTitleError('Use the main window controls.');
        }
        return activationActive;
      });
    }
    return activationPromise.then(function (activated) {
      if (activated) {
        clearTitleError();
        focusAction(node);
      }
      return activated;
    });
  }

  function deactivateIfActive() {
    if (activationPromise) {
      return activationPromise.then(function (activated) {
        if (!activated) return false;
        return deactivateIfActive();
      });
    }
    if (!activationActive) return Promise.resolve(false);
    activationActive = false;
    return send('deactivate_fleet_bar');
  }

  function bindAction(id, run) {
    var node = document.getElementById(id);
    if (!node) return;
    node.addEventListener('pointerdown', function (event) {
      if (event && typeof event.button === 'number' && event.button !== 0) return;
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      activateForAction(node);
    });
    node.addEventListener('click', function (event) {
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      activateForAction(node).then(function (activated) {
        if (!activated) return null;
        return run(node);
      });
    });
  }

  function bindTableActionTraversal() {
    var table = document.getElementById('fleet-table');
    var reset = document.getElementById('fleet-reset-width');
    if (!table || !reset) return;
    table.addEventListener('keydown', function (event) {
      if (!event || event.key !== 'Tab' || event.shiftKey) return;
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      focusAction(reset);
    });
  }

  function cell(className, text, role) {
    var node = document.createElement('span');
    node.className = className;
    node.setAttribute('role', role || 'cell');
    node.textContent = text;
    return node;
  }

  var DPS_DISPLAY_BOUND = 10000000; // beyond this, show '>10m' defensively

  function readDps(row, key) {
    var value = row ? row[key] : null;
    if (typeof value !== 'number' || !isFinite(value) || value < 0) return null;
    return value;
  }

  function isStaleRemote(row) {
    return row && row.remote === true && row.state === 'stale';
  }

  function hasIncomingThreat(row) {
    return !isStaleRemote(row) && readDps(row, 'incoming_dps') > 0;
  }

  function hasEwarThreat(row) {
    return !isStaleRemote(row) && Array.isArray(row && row.ewar) && row.ewar.length > 0;
  }

  function maxDps(rows, key) {
    var max = 0;
    rows.forEach(function (row) {
      if (isStaleRemote(row)) return;
      var value = readDps(row, key);
      if (value !== null && value > max) max = value;
    });
    return max;
  }

  function fillRatio(value, maximum) {
    if (typeof value !== 'number' || !isFinite(value) || value <= 0) return 0;
    if (typeof maximum !== 'number' || !isFinite(maximum) || maximum <= 0) return 0;
    return Math.max(0, Math.min(1, value / maximum));
  }

  function displayDps(value) {
    if (typeof value !== 'number' || !isFinite(value) || value < 0) return '—';
    if (value > DPS_DISPLAY_BOUND) return '>10m';
    return String(value);
  }

  function presentational(node) {
    node.setAttribute('role', 'presentation');
    return node;
  }

  function damageHalf(kind, value, ratio, highlightClass) {
    // kind is 'out' or 'in'; each half is a value plus a slim 3px rail. OUT
    // reads [value, track] (value toward Character, rail toward the axis);
    // IN reads [track, value] (rail toward the axis, value toward EWAR) --
    // the mirror is DOM order here and transform-origin in CSS, nothing else.
    var half = presentational(document.createElement('span'));
    half.className = 'fleet-damage-' + kind + (highlightClass ? ' ' + highlightClass : '');
    var track = presentational(document.createElement('span'));
    track.className = 'fleet-damage-track';
    var fill = presentational(document.createElement('span'));
    fill.className = 'fleet-damage-fill';
    // Set directly, no transition: a live combat feed must snap to the new
    // reading immediately rather than animate toward a value already stale.
    fill.style.transform = 'scaleX(' + ratio + ')';
    track.appendChild(fill);
    var number = presentational(document.createElement('span'));
    number.className = 'fleet-damage-value';
    number.textContent = displayDps(value);
    if (kind === 'out') {
      half.appendChild(number);
      half.appendChild(track);
    } else {
      half.appendChild(track);
      half.appendChild(number);
    }
    return half;
  }

  function axisNode() {
    var axis = document.createElement('span');
    axis.className = 'fleet-damage-axis';
    return presentational(axis);
  }

  function dpsAriaPart(prefix, value) {
    // Missing is unavailable, never a measured zero: a merged NO LOG state
    // is handled separately below, so a null here means this one direction
    // could not be measured while the other could.
    if (value === null) return prefix + ' unavailable';
    var label = value > DPS_DISPLAY_BOUND ? 'more than 10 million' : String(value);
    return prefix + ' ' + label + ' DPS';
  }

  function damageCell(row, maxOutgoing, maxIncoming) {
    var node = document.createElement('span');
    node.className = 'fleet-damage';
    node.setAttribute('role', 'cell');
    var out = readDps(row, 'outgoing_dps');
    var incoming = readDps(row, 'incoming_dps');

    if ((out === null || incoming === null) && row && row.log_status) {
      // A single merged NO LOG state replaces OUT/axis/IN: there is nothing
      // directional to show, and two empty rails would be two lies.
      node.classList.add('unavailable');
      node.setAttribute('aria-label', row.log_status);
      var status = presentational(document.createElement('span'));
      status.className = 'fleet-damage-status';
      status.textContent = row.log_status;
      node.appendChild(status);
      return node;
    }

    // No log_status here: each direction stands on its own. A numeric value
    // renders and fills normally; a null value is unavailable (em dash, no
    // fill, no highlight) rather than a fabricated zero.
    node.setAttribute('aria-label',
      dpsAriaPart('Outgoing', out) + ', ' + dpsAriaPart('incoming', incoming));

    var stale = isStaleRemote(row);
    node.appendChild(damageHalf('out', out, stale ? 0 : fillRatio(out, maxOutgoing),
      (!stale && out !== null && out > 0) ? 'live' : null));
    node.appendChild(axisNode());
    node.appendChild(damageHalf('in', incoming, stale ? 0 : fillRatio(incoming, maxIncoming),
      hasIncomingThreat(row) ? 'warn' : null));
    return node;
  }

  function ewarText(row) {
    return (Array.isArray(row && row.ewar) && row.ewar.length)
      ? row.ewar.join(' · ') : '—';
  }

  function ewarAriaLabel(row) {
    var ewar = Array.isArray(row && row.ewar) ? row.ewar : [];
    var labels = [];
    ewar.forEach(function (effect) {
      if (row && row.remote === true && effect === 'SCRAM/POINT') {
        labels.push('Remote tackle: scram or point.');
      } else {
        labels.push(effect);
      }
    });
    return labels.length ? labels.join(', ') : null;
  }

  function healthLabel(health) {
    var state = (health && health.state) || 'stopped';
    if (state === 'active') return 'LIVE';
    if (state === 'running') return 'WAITING';
    if (state === 'missing_folder') return 'NO LOG FOLDER';
    if (state === 'stale') return 'STALE';
    if (state === 'error') return 'ERROR';
    return 'WAITING';
  }

  function recoveryNote(payload, health) {
    if (payload && payload.metric_error) return payload.metric_error;
    var state = (health && health.state) || 'stopped';
    if (state === 'missing_folder') return 'Set the Gamelog folder in Settings › Alerts.';
    if (state === 'stale') return 'Gamelogs have stopped updating.';
    if (state === 'error') return 'Gamelogs could not be read.';
    return '';
  }

  function render(payload) {
    payload = payload || {};
    var revision = payload.revision;
    if (typeof revision !== 'number' || !isFinite(revision) || revision < 0 ||
        Math.floor(revision) !== revision) {
      return Promise.resolve(null);
    }
    if (revision < lastRevision) {
      return Promise.resolve(null);
    }
    lastRevision = revision;
    var rows = Array.isArray(payload.rows) ? payload.rows : [];
    var runningCount = Number(payload.running_count) || 0;
    var health = payload.stream_health || { state: 'stopped', detail: null };
    var rowsNode = document.getElementById('fleet-rows');
    var empty = document.getElementById('fleet-empty');
    var healthNode = document.getElementById('fleet-health');
    var note = document.getElementById('fleet-note');

    rowsNode.textContent = '';
    var maxOutgoing = maxDps(rows, 'outgoing_dps');
    var maxIncoming = maxDps(rows, 'incoming_dps');
    rows.forEach(function (row) {
      var line = document.createElement('div');
      var ewar = ewarText(row);
      var stale = isStaleRemote(row);
      var ewarThreat = hasEwarThreat(row);
      var threat = ewarThreat || hasIncomingThreat(row);
      line.className = 'fleet-grid fleet-row'
        + (stale ? ' stale' : '')
        + (threat ? ' threat' : '')
        + (ewarThreat ? ' ewar-threat' : '');
      line.setAttribute('role', 'row');
      var character = cell('fleet-character', row.character || '—');
      character.title = character.textContent;
      character.removeAttribute('role');
      var identity = cell('fleet-identity', '');
      identity.appendChild(character);
      if (row.remote === true) {
        var marker = document.createElement('span');
        marker.className = 'fleet-remote';
        marker.textContent = stale ? 'REMOTE · STALE' : 'REMOTE';
        identity.appendChild(marker);
      }
      line.appendChild(identity);
      line.appendChild(damageCell(row, maxOutgoing, maxIncoming));
      var incoming = cell('fleet-ewar' + (ewarThreat ? ' active' : ''), ewar);
      incoming.title = incoming.textContent;
      var ariaLabel = ewarAriaLabel(row);
      if (ariaLabel) incoming.setAttribute('aria-label', ariaLabel);
      line.appendChild(incoming);
      rowsNode.appendChild(line);
    });

    empty.hidden = rows.length !== 0;
    var emptyText = runningCount > 0
      ? 'All running characters are hidden.'
      : 'Waiting for EVE clients…';
    setText(empty, emptyText);
    setText(healthNode, 'LOCAL ' + healthLabel(health));
    healthNode.classList.toggle('warn', health.state === 'stale' ||
      health.state === 'missing_folder');
    healthNode.classList.toggle('err', health.state === 'error');

    var noteText = recoveryNote(payload, health);
    note.hidden = !noteText;
    setText(note, noteText);
    note.classList.toggle('err', Boolean(payload.metric_error) || health.state === 'error');
    return fitHeight();
  }

  window.onFleetSnapshot = render;

  window.addEventListener('resize', scheduleResizeSettlement);
  window.addEventListener('blur', function () {
    deactivateIfActive();
  });
  window.addEventListener('keydown', function (event) {
    if (!event || event.key !== 'Escape') return;
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    clearTitleError();
    deactivateIfActive();
  });

  bindHeaderDrag();
  bindTableActionTraversal();

  bindAction('fleet-reset-width', function () {
    return cancelHeaderDrag().then(function () {
      return send('reset_fleet_bar_page_width');
    }).then(function (result) {
      return fieldResult(result, 'Could not reset Fleet Bar width.');
    });
  });
  bindAction('fleet-hide', function () {
    activationActive = false;
    activationPromise = null;
    return cancelHeaderDrag().then(function () {
      return send('hide_fleet_bar');
    }).then(function (result) {
      return fieldResult(result, 'Could not hide the Fleet Bar.');
    });
  });

  var fontsReady = (document.fonts && document.fonts.ready)
    ? document.fonts.ready : Promise.resolve();
  Promise.all([send('fleet_bar_snapshot'), fontsReady]).then(function (values) {
    if (!values[0]) return null;
    return render(values[0]);
  }).then(function () {
    return send('fleet_bar_ready');
  });
  setTimeout(function () {
    fitHeight();
  }, 500);
})();
