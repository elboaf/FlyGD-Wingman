/* FlyGD Wingman — standalone fleet combat display. */
(function () {
  'use strict';

  var ready = new Promise(function (resolve) {
    if (window.pywebview && window.pywebview.api) { resolve(); return; }
    window.addEventListener('pywebviewready', function () { resolve(); },
                            { once: true });
  });

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
    send('fit_fleet_bar', document.body.scrollWidth, document.body.scrollHeight);
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
    var rows = Array.isArray(payload.rows) ? payload.rows : [];
    var health = payload.stream_health || { state: 'stopped', detail: null };
    var rowsNode = document.getElementById('fleet-rows');
    var empty = document.getElementById('fleet-empty');
    var healthNode = document.getElementById('fleet-health');
    var note = document.getElementById('fleet-note');

    rowsNode.textContent = '';
    rows.forEach(function (row) {
      var line = document.createElement('div');
      var hasDps = typeof row.dps === 'number';
      var ewar = Array.isArray(row.ewar) && row.ewar.length
        ? row.ewar.join(' \u00b7 ') : '\u2014';
      line.className = 'fleet-grid fleet-row';
      line.setAttribute('role', 'row');
      line.appendChild(cell('fleet-character', row.character || '\u2014'));
      line.appendChild(cell('fleet-dps' + (hasDps ? ' live' : ''),
                            hasDps ? String(row.dps) : (row.log_status || 'WAITING')));
      line.appendChild(cell('fleet-ewar' + (ewar !== '\u2014' ? ' active' : ''), ewar));
      rowsNode.appendChild(line);
    });

    empty.hidden = rows.length !== 0;
    healthNode.textContent = healthLabel(health);
    healthNode.classList.toggle('warn', health.state === 'stale' ||
      health.state === 'missing_folder');
    healthNode.classList.toggle('err', health.state === 'error');

    var detail = payload.metric_error ||
      ((health.state === 'stale' || health.state === 'error') ? health.detail : null);
    note.hidden = !detail;
    note.textContent = detail || '';
    note.classList.toggle('err', Boolean(payload.metric_error) || health.state === 'error');
    fit();
  }

  window.onFleetSnapshot = render;

  document.addEventListener('mouseup', function () {
    send('save_fleet_bar_pos', window.screenX, window.screenY);
  });

  send('fleet_bar_snapshot').then(function (payload) {
    if (payload) render(payload);
  });
  fit();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  setTimeout(fit, 500);
})();
