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

  function fit() {
    var shell = document.querySelector('.fleet-shell');
    if (!shell) return Promise.resolve(null);
    var width = shell.offsetWidth;
    var height = shell.offsetHeight;
    return send('fit_fleet_bar', width, height).then(function () {
      // Screen coordinates and available bounds are CSS/logical pixels, the
      // same units pywebview accepts. Keep roster growth on the current
      // monitor and recover coordinates left on a disconnected display.
      var left = (typeof screen.availLeft === 'number') ? screen.availLeft : 0;
      var top = (typeof screen.availTop === 'number') ? screen.availTop : 0;
      var right = left + screen.availWidth;
      var bottom = top + screen.availHeight;
      var x = Math.max(left, Math.min(window.screenX, right - width));
      var y = Math.max(top, Math.min(window.screenY, bottom - height));
      if (Math.abs(x - window.screenX) > 1 ||
          Math.abs(y - window.screenY) > 1) {
        return send('move_fleet_bar', x, y);
      }
      return null;
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

  function maxDps(rows, key) {
    var max = 0;
    rows.forEach(function (row) {
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
    if (typeof value !== 'number' || !isFinite(value) || value < 0) return '\u2014';
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

    node.appendChild(damageHalf('out', out, fillRatio(out, maxOutgoing),
      (out !== null && out > 0) ? 'live' : null));
    node.appendChild(axisNode());
    // Positive IN shares --warn with active EWAR; OUT never does.
    node.appendChild(damageHalf('in', incoming, fillRatio(incoming, maxIncoming),
      (incoming !== null && incoming > 0) ? 'warn' : null));
    return node;
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
      var ewar = (Array.isArray(row.ewar) && row.ewar.length)
        ? row.ewar.join(' \u00b7 ') : '\u2014';
      line.className = 'fleet-grid fleet-row';
      line.setAttribute('role', 'row');
      var character = cell('fleet-character', row.character || '\u2014');
      character.title = character.textContent;
      line.appendChild(character);
      line.appendChild(damageCell(row, maxOutgoing, maxIncoming));
      line.appendChild(cell('fleet-ewar' + (ewar !== '\u2014' ? ' active' : ''), ewar));
      rowsNode.appendChild(line);
    });

    empty.hidden = rows.length !== 0;
    var emptyText = runningCount > 0
      ? 'All running characters are hidden.'
      : 'Waiting for EVE clients\u2026';
    if (empty.textContent !== emptyText) {
      empty.textContent = emptyText;
    }
    healthNode.textContent = healthLabel(health);
    healthNode.classList.toggle('warn', health.state === 'stale' ||
      health.state === 'missing_folder');
    healthNode.classList.toggle('err', health.state === 'error');

    var detail = payload.metric_error ||
      ((health.state === 'stale' || health.state === 'error') ? health.detail : null);
    var noteText = detail || '';
    note.hidden = !noteText;
    if (note.textContent !== noteText) {
      note.textContent = noteText;
    }
    note.classList.toggle('err', Boolean(payload.metric_error) || health.state === 'error');
    return fit();
  }

  window.onFleetSnapshot = render;

  document.addEventListener('mouseup', function () {
    send('save_fleet_bar_pos', window.screenX, window.screenY);
  });

  var fontsReady = (document.fonts && document.fonts.ready)
    ? document.fonts.ready : Promise.resolve();
  Promise.all([send('fleet_bar_snapshot'), fontsReady]).then(function (values) {
    if (!values[0]) return null;
    return render(values[0]);
  }).then(function () {
    return send('fleet_bar_ready');
  });
  setTimeout(fit, 500);
})();
