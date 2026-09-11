// Wanderer Settings owns drafts and acknowledgements; pushes own health only.
(function () {
  'use strict';
  var WM = window.WM;
  WM.handle('onWandererState', function (payload) { receive(payload); });

  var hydrated = false;
  var acknowledged = null;
  var health = null;
  var healthGeneration = -1;
  var delivery = 0;
  var readRequest = 0;
  var interaction = 0;
  var confirming = false;
  var connectionTail = Promise.resolve();
  var testWaiting = false;
  var testObserved = false;
  var testRevision = -1;
  var testGeneration = -1;
  var testInterrupted = false;
  var testPriorResult = null;
  var fields = {};
  var keys = {enabled: 'enabled', url: 'base_url', map: 'map_identifier'};
  ['enabled', 'url', 'map', 'token', 'connection', 'test', 'remove'].forEach(function (name) {
    fields[name] = {edit: 0, request: 0, pending: 0, error: '', tail: Promise.resolve()};
  });

  function el(name) { return WM.el('wanderer-' + name); }
  function value(name) { return name === 'enabled' ? el(name).checked : el(name).value; }
  function restore(name) {
    if (name === 'enabled') el(name).checked = acknowledged.enabled;
    else if (keys[name]) el(name).value = acknowledged[keys[name]];
  }
  function dirty(name) { return acknowledged && value(name) !== acknowledged[keys[name]]; }
  function connectionBusy() {
    return fields.url.pending || fields.map.pending || fields.token.pending || fields.remove.pending;
  }

  // Read only safe fields. A later acknowledgement from another field may
  // already contain this write; older replies must never rewind its baseline.
  function acceptAcknowledged(p) {
    if (!p || typeof p.revision !== 'number'
        || (acknowledged && p.revision < acknowledged.revision)) return false;
    acknowledged = {revision: p.revision, enabled: p.enabled, base_url: p.base_url,
      map_identifier: p.map_identifier, credential_present: p.credential_present,
      credential_error: p.credential_error, persistence_error: p.persistence_error};
    if (testWaiting && testRevision !== p.revision) testWaiting = false;
    return true;
  }

  function connectionText(p) {
    if (acknowledged.persistence_error) return 'Saved connection could not be restored — names stopped. Restart Wingman and re-enter the connection.';
    if (!acknowledged.enabled) return 'Off — connection settings remain editable.';
    if (acknowledged.credential_error) return 'Token unreadable — enter it again or remove the connection.';
    if (!acknowledged.base_url || !acknowledged.map_identifier || !acknowledged.credential_present) {
      return 'Setup needed — enter the URL, map and token, then test the connection.';
    }
    if (!p || p.revision < acknowledged.revision) return 'Connecting…';
    if (!p.previews_enabled || !p.host_available) return 'Waiting for previews — enable them to show names.';
    if (p.status === 'error') {
      switch (p.error_code) {
        case 'invalid_token': return 'Token rejected — replace it, then test again.';
        case 'wrong_map': return 'Wrong map — this token belongs to another map.';
        case 'disabled': return 'API disabled — enable it on the Wanderer server.';
        default: return (p.paused ? 'Connection paused — ' : 'Retrying — ') + p.status_text;
      }
    }
    if (p.status === 'connecting') return 'Connecting…';
    if (p.status === 'stale') return 'Stale — waiting for fresh location confirmations.';
    if (p.status === 'connected') {
      return p.previewed && !p.matched ? 'Connected — No tracked characters among your previews.' : 'Connected to Wanderer.';
    }
    return p.status_text && p.status !== 'off' ? p.status_text : 'Connecting…';
  }

  function paint() {
    ['enabled', 'url', 'map', 'token'].forEach(function (name) {
      el(name).disabled = !hydrated;
    });
    ['url', 'map'].forEach(function (name) {
      el(name + '-draft').textContent = fields[name].pending ? 'Saving submitted connection…'
        : dirty(name) ? 'Not saved — press Enter or Test connection.' : '';
    });
    ['enabled', 'connection', 'test', 'remove'].forEach(function (name) {
      var slot = el(name + '-error');
      slot.textContent = fields[name].error;
      slot.className = 'field-msg err';
      slot.hidden = !fields[name].error;
    });
    el('token-draft').textContent = 'Stored only on this PC, protected by Windows. Leave blank to reuse only the same saved URL and map.';
    var currentHealth = health && acknowledged && health.revision === acknowledged.revision ? health : null;
    var testing = testWaiting || (currentHealth && (currentHealth.test_pending || currentHealth.test_in_flight));
    el('test').disabled = !hydrated || confirming || !!connectionBusy() || !!testing;
    // Remove can also delete a credential left bound to an earlier URL/map.
    el('remove').disabled = !hydrated || confirming || !!connectionBusy();
    el('test-status').textContent = fields.test.pending && !testObserved ? 'Saving connection and requesting Test…'
      : fields.test.error || fields.connection.error || (acknowledged && acknowledged.persistence_error) ? ''
      : currentHealth && currentHealth.test_in_flight ? 'Testing connection…'
      : testing ? 'Test queued — waiting for the request lane.'
        : currentHealth && currentHealth.test_result_text ? 'Test: ' + currentHealth.test_result_text : '';
    if (!acknowledged) return;
    el('credential').textContent = acknowledged.credential_error ? 'Stored token could not be read.'
      : acknowledged.credential_present ? 'Token stored for this connection.' : 'No token stored for this connection.';
    el('health').textContent = connectionText(currentHealth);
    // These are WorkerState's current-session projection counts, never a map
    // roster or persisted recent-character list. Expired names are not available.
    el('coverage').textContent = !currentHealth ? '' : !currentHealth.previewed ? 'No named previews open.'
      : currentHealth.available + ' of ' + currentHealth.previewed + ' previews have a fresh system name — '
        + currentHealth.matched + ' of ' + currentHealth.previewed + ' tracked'
        + (currentHealth.stale ? ', ' + currentHealth.stale + ' stale' : '') + '.';
  }

  function receive(p, afterTestAdmission) {
    if (!p || p.generation < healthGeneration || !acceptAcknowledged(p)) return;
    delivery += 1;
    // Controller settings can advance just before its worker reconfiguration.
    // Keep the safe acknowledgement, not coverage from the previous binding.
    if (health && p.revision > health.revision && p.generation <= health.generation) {
      paint();
      return;
    }
    healthGeneration = p.generation;
    health = p;
    if ((testWaiting || testInterrupted) && p.revision === testRevision) {
      var newerGeneration = p.generation > testGeneration;
      var hasResult = p.test_result !== null && p.test_result !== undefined;
      if (newerGeneration && !p.test_pending && !p.test_in_flight && !hasResult) {
        // Preview readiness can replace the worker generation without changing
        // Wanderer settings. A retired Test has no outcome to keep waiting for.
        testWaiting = false;
        testInterrupted = true;
        testObserved = false;
        fields.test.error = 'Preview state changed — Test outcome is unknown. Test again.';
      } else if (testWaiting || (newerGeneration && (p.test_pending || hasResult))) {
        if (testInterrupted) fields.test.error = '';
        testInterrupted = false;
        testWaiting = true;
        // Pending proves admission in this generation; in-flight alone can
        // still describe the old, retained HTTP owner draining after configure.
        if (newerGeneration && p.test_pending) testGeneration = p.generation;
        if (p.test_pending || p.test_in_flight) testObserved = true;
        // A new-generation result cannot be the previous Test's cached result.
        if (hasResult && (testObserved || afterTestAdmission || newerGeneration
            || p.test_result !== testPriorResult)) {
          testObserved = true;
          testWaiting = false;
        }
      }
    }
    paint();
  }

  // The connection writes as a group, but a reply owns each field separately.
  // Enable has its own lane; neither response may erase newer connection drafts.
  function commit(name, send) {
    if (!hydrated) return;
    var field = fields[name];
    var request = ++field.request;
    var edit = ++field.edit;
    var owned = {};
    var inputs = name === 'enabled' ? ['enabled'] : ['url', 'map', 'token'];
    inputs.forEach(function (key) {
      owned[key] = fields[key].edit;
      if (key !== name) fields[key].pending += 1;
    });
    field.pending += 1;
    delivery += 1;
    interaction += 1;
    var tail = name === 'enabled' ? field.tail : connectionTail;
    field.tail = tail.then(send).then(function (res) {
      field.pending -= 1;
      delivery += 1;
      var owns = request === field.request && edit === field.edit;
      acceptAcknowledged(res && res.acknowledged);
      inputs.forEach(function (key) {
        if (key !== name) fields[key].pending -= 1;
        if (owned[key] === fields[key].edit && keys[key]) restore(key);
      });
      var saved = res && res.applied && res.persisted;
      var errorField = name === 'test' ? fields.connection : field;
      if (saved) errorField.error = '';
      else if (owns) errorField.error = res && res.error ? res.error
        : 'Could not reach the app. Reopen Previews to check the saved connection.';
      if (name === 'test' && request === field.request) {
        if (!saved || !res.test_accepted) {
          testWaiting = false;
          field.error = saved ? res.test_error || 'Connection saved, but Test could not start.' : '';
        } else if (res.acknowledged.revision !== testRevision
            && res.acknowledged.revision === acknowledged.revision) {
          // A grouped save advances configuration before Test admission. Adopt
          // its actual fenced generation, not a pre-save result or coverage.
          testRevision = res.acknowledged.revision;
          testGeneration = res.test_generation;
          testWaiting = true;
          testObserved = testInterrupted = false;
          testPriorResult = null;
          field.error = '';
          if (health && health.revision === testRevision
              && health.generation >= testGeneration) receive(health, true);
        } else if (testInterrupted || testRevision !== acknowledged.revision) testWaiting = false;
        else {
          field.error = '';
          if (testObserved) testWaiting = !!(health && (health.test_pending || health.test_in_flight));
        }
        if (saved && res.test_accepted && testWaiting && !testObserved && testPriorResult !== null) {
          // No per-Test sequence exists in the state contract. A repeated
          // outcome with coalesced progress needs a read AFTER admission;
          // an early push of the previous result cannot prove completion.
          var atRead = delivery;
          WM.send('wanderer_state').then(function (p) {
            if (request !== field.request || !testWaiting
                || (atRead !== delivery && testObserved)) return;
            if (p) receive(p, true);
            else {
              testWaiting = false;
              field.error = 'Could not read Test status — test again to retry.';
              paint();
            }
          });
        }
      }
      paint();
    });
    if (name !== 'enabled') connectionTail = field.tail;
    paint();
  }

  function testConnection() {
    if (el('test').disabled) return;
    var base = el('url').value;
    var map = el('map').value;
    var token = el('token').value;
    // Clear at submission, never on a later reply over a newer password draft.
    // The secret has no acknowledged baseline or binding history on the page.
    el('token').value = '';
    testWaiting = true;
    testObserved = false;
    testRevision = acknowledged.revision;
    testGeneration = healthGeneration;
    testInterrupted = false;
    testPriorResult = health && health.revision === testRevision ? health.test_result : null;
    fields.test.error = '';
    commit('test', function () {
      var response = WM.send('test_wanderer_connection', base, map, token);
      token = null;
      return response;
    });
  }

  ['url', 'map', 'token'].forEach(function (name) {
    el(name).addEventListener('input', function () {
      fields[name].edit += 1;
      interaction += 1;
      paint();
    });
    el(name).addEventListener('keydown', function (event) {
      if (event.key === 'Enter') { event.preventDefault(); testConnection(); }
    });
  });
  el('enabled').addEventListener('change', function () {
    var submitted = el('enabled').checked;
    commit('enabled', function () { return WM.send('set_wanderer_enabled', submitted); });
  });
  el('test').addEventListener('click', testConnection);
  el('remove').addEventListener('click', function () {
    if (el('remove').disabled) return;
    var owner = interaction;
    var revision = acknowledged.revision;
    confirming = true;
    paint();
    WM.confirm('Remove Wanderer connection?', 'Deletes the saved URL, map and protected token from this PC. '
      + 'The enabled preference stays unchanged. You will need to enter the connection again.').then(function (ok) {
      confirming = false;
      if (ok && owner === interaction && revision === acknowledged.revision) {
        el('token').value = '';
        commit('remove', function () { return WM.send('remove_wanderer_connection', revision); });
      }
      paint();
    });
  });

  document.addEventListener('wm:section', function (event) {
    interaction += 1;
    if (event.detail !== 'previews') return;
    var request = ++readRequest;
    var atRead = delivery;
    WM.send('wanderer_state').then(function (p) {
      if (request !== readRequest) return;
      // A push or write since admission owns health, even at the same revision.
      if (atRead === delivery) receive(p);
      if (!hydrated && acknowledged) {
        Object.keys(keys).forEach(function (name) {
          if (!fields[name].edit) restore(name);
        });
        hydrated = true;
      }
      paint();
      if (!acknowledged) el('health').textContent = 'Could not load Wanderer settings — reopen Previews to retry.';
    });
  });
  paint();
}());
