/* FlyGD Wingman — standalone fleet combat display. */
(function () {
  'use strict';

  var ready = new Promise(function (resolve) {
    if (window.pywebview && window.pywebview.api) { resolve(); return; }
    window.addEventListener('pywebviewready', function () { resolve(); },
                            { once: true });
  });
  var lastRevision = -1;

  function send(method) {
    var args = Array.prototype.slice.call(arguments, 1);
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
    var revision = Number(payload.revision);
    if (isFinite(revision) && revision < lastRevision) {
      return Promise.resolve(null);
    }
    if (isFinite(revision)) lastRevision = revision;
    var rows = Array.isArray(payload.rows) ? payload.rows : [];
    var runningCount = Number(payload.running_count) || 0;
    var health = payload.stream_health || { state: 'stopped', detail: null };
    var rowsNode = document.getElementById('fleet-rows');
    var empty = document.getElementById('fleet-empty');
    var healthNode = document.getElementById('fleet-health');
    var note = document.getElementById('fleet-note');

    rowsNode.textContent = '';
    rows.forEach(function (row) {
      var line = document.createElement('div');
      var hasDps = typeof row.dps === 'number';
      var unavailable = !hasDps && !!row.log_status;
      var ewar = unavailable ? row.log_status
        : (Array.isArray(row.ewar) && row.ewar.length
          ? row.ewar.join(' \u00b7 ') : '\u2014');
      line.className = 'fleet-grid fleet-row';
      line.setAttribute('role', 'row');
      line.appendChild(cell('fleet-character', row.character || '\u2014'));
      line.appendChild(cell('fleet-dps' + (hasDps ? ' live' : ''),
                            hasDps ? String(row.dps) + ' dps' : '\u2014'));
      line.appendChild(cell('fleet-ewar' +
        (!unavailable && ewar !== '\u2014' ? ' active' : ''), ewar));
      rowsNode.appendChild(line);
    });

    empty.hidden = rows.length !== 0;
    empty.textContent = runningCount > 0
      ? 'All running characters are hidden.'
      : 'Waiting for EVE clients\u2026';
    healthNode.textContent = healthLabel(health);
    healthNode.classList.toggle('warn', health.state === 'stale' ||
      health.state === 'missing_folder');
    healthNode.classList.toggle('err', health.state === 'error');

    var detail = payload.metric_error ||
      ((health.state === 'stale' || health.state === 'error') ? health.detail : null);
    note.hidden = !detail;
    note.textContent = detail || '';
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
    return render(values[0] || {});
  }).then(function () {
    return send('fleet_bar_ready');
  });
  setTimeout(fit, 500);
})();
