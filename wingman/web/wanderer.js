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
  var tokenBinding = null;
  var tokenStarted = false;
  var testWaiting = false;
  var testObserved = false;
  var testRevision = -1;
  var testPriorResult = null;
  var fields = {};
  var keys = {enabled: 'enabled', url: 'base_url', map: 'map_identifier'};
  ['enabled', 'url', 'map', 'token', 'test', 'remove'].forEach(function (name) {
    fields[name] = {edit: 0, request: 0, pending: 0, error: '', tail: Promise.resolve()};
  });

  function el(name) { return WM.el('wanderer-' + name); }
  function value(name) { return name === 'enabled' ? el(name).checked : el(name).value; }
  function restore(name) {
    if (name === 'enabled') el(name).checked = acknowledged.enabled;
    else if (keys[name]) el(name).value = acknowledged[keys[name]];
  }
  function dirty(name) { return acknowledged && value(name) !== acknowledged[keys[name]]; }
  function binding() { return [acknowledged.base_url, acknowledged.map_identifier]; }
  function sameBinding(expected) {
    return expected && acknowledged && expected[0] === acknowledged.base_url
      && expected[1] === acknowledged.map_identifier;
  }
  function bindingClean() {
    return hydrated && !dirty('url') && !dirty('map')
      && !fields.url.pending && !fields.map.pending
      && acknowledged.base_url && acknowledged.map_identifier;
  }
  function tokenReady() {
    return bindingClean() && el('token').value && sameBinding(tokenBinding);
  }
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
      credential_error: p.credential_error};
    if (testWaiting && testRevision !== p.revision) testWaiting = false;
    return true;
  }

  function connectionText(p) {
    if (!acknowledged.enabled) return 'Off — connection settings remain editable.';
    if (acknowledged.credential_error) return 'Token unreadable — replace or remove it.';
    if (!acknowledged.base_url || !acknowledged.map_identifier || !acknowledged.credential_present) {
      return 'Setup needed — apply the URL, map and token.';
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
      el(name + '-apply').disabled = !hydrated;
      el(name + '-draft').textContent = fields[name].pending ? 'Applying…'
        : dirty(name) ? 'Not applied — press Enter or Apply.' : '';
    });
    Object.keys(fields).forEach(function (name) {
      var slot = el(name + '-error');
      slot.textContent = fields[name].error;
      slot.className = 'field-msg err';
      slot.hidden = !fields[name].error;
    });
    el('token-apply').disabled = !tokenReady();
    el('token-draft').textContent = !bindingClean()
      ? 'Apply the URL and map before replacing the token.'
      : el('token').value && !sameBinding(tokenBinding)
        ? 'Connection changed — clear and re-enter the token.'
        : 'Stored only on this PC, protected by Windows. Replacement clears this entry.';
    var currentHealth = health && acknowledged && health.revision === acknowledged.revision ? health : null;
    var testing = testWaiting || (currentHealth && (currentHealth.test_pending || currentHealth.test_in_flight));
    el('test').disabled = !bindingClean() || !acknowledged.credential_present
      || !!connectionBusy() || !!fields.test.pending || !!testing;
    // Remove can also delete a credential left bound to an earlier URL/map.
    el('remove').disabled = !hydrated || confirming || !!connectionBusy();
    el('test-status').textContent = fields.test.error ? ''
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
    if (testWaiting && p.revision === testRevision) {
      if (p.test_pending || p.test_in_flight) testObserved = true;
      // The publisher is ordered, but can coalesce pending/in-flight away.
      // A result is the HTTP outcome; the mutation reply is admission only.
      if (p.test_result !== null && p.test_result !== undefined
          && (testObserved || afterTestAdmission || p.test_result !== testPriorResult)) {
        testObserved = true;
        testWaiting = false;
      }
    }
    paint();
  }

  // Separate per-field request/edit counters and errors, even on the shared
  // connection lane. Ignoring old replies alone cannot order Python's threads.
  function commit(name, send) {
    if (!hydrated) return;
    var field = fields[name];
    var request = ++field.request;
    var edit = ++field.edit;
    field.pending += 1;
    delivery += 1;
    interaction += 1;
    var tail = name === 'enabled' ? field.tail : connectionTail;
    field.tail = tail.then(send).then(function (res) {
      field.pending -= 1;
      delivery += 1;
      var owns = request === field.request && edit === field.edit;
      acceptAcknowledged(res && res.acknowledged);
      if (res && res.applied && res.persisted) {
        field.error = '';
        if (owns && keys[name]) restore(name);
      } else if (owns) {
        field.error = res && res.error ? res.error : 'Could not reach the app. Nothing was changed.';
        if (keys[name]) restore(name);
      }
      if (name === 'test' && request === field.request) {
        if (!res || !res.applied || testRevision !== acknowledged.revision) testWaiting = false;
        else if (testObserved) testWaiting = !!(health && (health.test_pending || health.test_in_flight));
        else if (testPriorResult !== null) {
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

  function applyURL() {
    var submitted = el('url').value;
    commit('url', function () { return WM.send('set_wanderer_url', submitted); });
  }
  function applyMap() {
    var submitted = el('map').value;
    commit('map', function () { return WM.send('set_wanderer_map', submitted); });
  }
  function applyToken() {
    if (!tokenReady()) { paint(); return; }
    var submitted = el('token').value;
    var expected = tokenBinding;
    // Clear at submission, not acknowledgement. The promise never owns a
    // future password draft, and no secret becomes an acknowledged baseline.
    el('token').value = '';
    tokenBinding = null;
    tokenStarted = false;
    commit('token', function () {
      if (!sameBinding(expected)) {
        submitted = null;
        return {applied: false, persisted: false, error: 'Connection changed — re-enter the token.'};
      }
      var response = WM.send('replace_wanderer_token', submitted, expected[0], expected[1]);
      submitted = null;
      return response;
    });
  }

  ['url', 'map', 'token'].forEach(function (name) {
    el(name).addEventListener('input', function () {
      fields[name].edit += 1;
      interaction += 1;
      if (name === 'token') {
        if (!el(name).value) { tokenStarted = false; tokenBinding = null; }
        else if (!tokenStarted) { tokenStarted = true; tokenBinding = bindingClean() ? binding() : null; }
      }
      paint();
    });
    var apply = name === 'url' ? applyURL : name === 'map' ? applyMap : applyToken;
    el(name).addEventListener('keydown', function (event) {
      if (event.key === 'Enter') { event.preventDefault(); apply(); }
    });
    el(name + '-apply').addEventListener('click', apply);
  });
  el('enabled').addEventListener('change', function () {
    var submitted = el('enabled').checked;
    commit('enabled', function () { return WM.send('set_wanderer_enabled', submitted); });
  });
  el('test').addEventListener('click', function () {
    if (el('test').disabled) return;
    testWaiting = true;
    testObserved = false;
    testRevision = acknowledged.revision;
    testPriorResult = health && health.revision === testRevision ? health.test_result : null;
    commit('test', function () { return WM.send('test_wanderer_connection'); });
  });
  el('remove').addEventListener('click', function () {
    if (el('remove').disabled) return;
    var owner = interaction;
    var revision = acknowledged.revision;
    confirming = true;
    paint();
    WM.confirm('Remove Wanderer token?', 'Deletes the protected token from this PC. '
      + 'The URL, map and enabled preference stay unchanged. You will need to enter a token again.').then(function (ok) {
      confirming = false;
      if (ok && owner === interaction && revision === acknowledged.revision) {
        commit('remove', function () { return WM.send('remove_wanderer_connection'); });
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
