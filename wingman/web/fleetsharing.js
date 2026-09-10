// Setup only. The worker owns identities, consent journals and source UUIDs;
// this view never treats queue acceptance as a server acknowledgement.
(function () {
  'use strict';
  WM.handle('onFleetSharingState', render);

  var state = null;
  var hydrated = false;
  var watchGeneration = 0;
  var watchChain = Promise.resolve();
  var preferenceAttempt = 0;
  var actionAttempt = 0;
  var preferencePending = false;
  var preferenceWanted = false;
  var boss = WM.el('sharing-boss');
  var enabled = WM.el('sharing-enabled');
  var connect = WM.el('sharing-connect');
  var start = WM.el('sharing-start');
  var grant = WM.el('sharing-grant');
  var sources = WM.el('sharing-sources');
  var pairingMode = 'initial';
  var changeOrigin = false;
  var details = {
    needs_upgrade: 'This device needs sharing approval. Upgrade the connection in your browser.',
    needs_fresh_key: 'This device was revoked or its key conflicts. Fresh setup is available.',
    needs_fresh_intent: 'Confirm sharing On again after the newer server choice.',
    needs_pairing: 'Connect this Wingman to your authGD account.',
    feature_disabled: 'Fleet sharing is disabled on authGD. Local tools are unaffected.',
    service_unavailable: 'authGD is unavailable. Pending controls will retry.',
    account_ineligible: 'Your authGD account is not currently eligible. Use the correct Member account.',
    unauthorized: 'Reconnecting by device proof. No browser setup is needed.',
    fleet_read_required: 'The selected boss needs Fleet Read. Grant it, then Start explicitly.',
    transport_error: 'Cannot reach authGD. Pending controls will retry.',
    persistence_failed: 'A sharing-state write failed. Queued is not saved or acknowledged.',
    pairing_expired: 'Approval expired. Connect again when ready.',
    fresh_key_not_authorized: 'Fresh setup is not authorized. Use the existing connection.',
    use_key_recovery: 'Reconnecting with this device key; do not pair a replacement.',
    local_failure: 'Fleet sharing could not continue. Retry or restart Wingman.',
    source_queue_full: 'Too many pending source controls. Stop or wait for existing work.',
    update_required: 'This server requires a supported Wingman build.',
    forbidden: 'authGD refused this operation. Check account eligibility and connection.',
    capability_required: 'This connection needs sharing approval.',
    conflict: 'Waiting for authGD to reconcile the current action.'
  };

  function visible() {
    return WM.current_route === 'settings' && WM.current_section === 'previews' && !document.hidden;
  }
  function text(id, value) { WM.el(id).textContent = value || ''; }
  function binding() { return state && state.metadata.binding; }
  function selected() {
    return ((state && state.sources && state.sources.characters) || []).filter(function (row) {
      return String(row.character_id) === boss.value;
    })[0];
  }
  function nameFor(id) {
    var character = ((state && state.sources && state.sources.characters) || []).filter(function (row) {
      return row.character_id === id;
    })[0];
    return character ? character.character_name : (id ? 'Character ' + id : 'Unknown character');
  }
  function paintBoss() {
    var character = selected();
    var ready = !!(character && character.has_fleet_read && character.token_usable);
    grant.disabled = !hydrated || !character || !state.available;
    start.disabled = !hydrated || !ready || !state.available || state.metadata.feature_enabled === false;
    text('sharing-grant-status', !state.metadata.loaded ? 'Reading saved connection…'
      : !binding() ? 'Connect to read your owned characters.'
      : !state.sources ? 'Loading owned characters. Refresh if needed.'
      : !state.sources.characters.length ? 'No owned characters found in this account.'
      : !character ? 'Choose your fleet boss.'
      : ready ? 'Fleet Read ready. Start checks this character is boss.'
      : 'Grant Fleet Read using the paired account, then Refresh.');
  }
  function paintCharacters() {
    var previous = boss.value;
    var characters = state.sources ? state.sources.characters : [];
    // Do not rebuild a focused native select on every watch heartbeat.
    var signature = JSON.stringify(characters);
    if (boss.getAttribute('data-roster') !== signature) {
      boss.textContent = '';
      boss.appendChild(WM.make('option', '', characters.length ? 'Choose your fleet boss' : 'No owned characters available'));
      boss.options[0].value = '';
      characters.forEach(function (character) {
        var option = WM.make('option', '', character.character_name);
        option.value = String(character.character_id);
        boss.appendChild(option);
      });
      boss.value = previous;
      boss.setAttribute('data-roster', signature);
    }
    boss.disabled = !state.available || !characters.length;
    paintBoss();
    var list = WM.el('sharing-eligible-list');
    list.textContent = '';
    text('sharing-eligibility', !state.eligibility ? 'Eligibility has not been observed.'
      : state.eligibility.state === 'ready' ? 'Currently eligible for sparse telemetry:'
      : state.eligibility.state === 'participation_off' ? 'Server participation is Off.'
      : 'No verified roster currently makes these characters eligible.');
    ((state.eligibility && state.eligibility.characters) || []).forEach(function (row) {
      list.appendChild(WM.make('li', '', nameFor(row.character_id)));
    });
  }
  function paintSources() {
    var rows = Object.create(null);
    var existing = Object.create(null);
    Array.prototype.forEach.call(sources.children, function (row) { existing[row.getAttribute('data-source')] = row; });
    ((state.sources && state.sources.sources) || []).forEach(function (row) {
      rows[row.source_id] = {observed: row, pending: null};
    });
    (state.source_results || []).forEach(function (result) {
      if (!rows[result.source_id]) rows[result.source_id] = {observed: null, result: result};
    });
    (state.pending_sources || []).forEach(function (pending) {
      if (!rows[pending.source_id]) rows[pending.source_id] = {observed: null};
      rows[pending.source_id].pending = pending;
    });
    var position = 0;
    Object.keys(rows).forEach(function (id) {
      var item = rows[id];
      var observed = item.observed;
      var pending = item.pending;
      var result = item.result;
      var row = existing[id];
      if (!row) {
        row = WM.make('div', 'sharing-source');
        row.setAttribute('data-source', id);
        row.appendChild(WM.make('div', 'sharing-source-text'));
        var stop = WM.make('button', 'btn', 'Stop');
        stop.addEventListener('click', function () {
          if (!hydrated) return;
          action('fleet_sharing_stop_source', id, binding());
        });
        row.appendChild(stop);
      }
      delete existing[id];
      var label = nameFor(observed ? observed.character_id : pending ? pending.character_id : result.character_id);
      if (label === 'Unknown character') label = 'Source ' + id.slice(0, 8);
      var description = label + ' · ' + (observed ? observed.state : result && !pending ? 'Start expired. Start again explicitly.' : 'Not yet observed');
      if (observed && observed.reason) description += ' — ' + observed.reason.replace(/_/g, ' ');
      if (pending) description += ' · ' + (pending.operation === 'stop' ? 'Stop' : 'Start')
        + (pending.stage === 'queued' ? ' queued locally' : ' saved, awaiting authGD');
      row.firstChild.textContent = description;
      row.firstChild.title = 'Source ' + id;
      row.lastChild.disabled = !state.available || (!pending && (result || (observed && observed.state === 'ended')));
      row.lastChild.setAttribute('aria-label', 'Stop source for ' + label + ' ' + id);
      // Even appendChild(existingRow) drops native keyboard focus in Chrome.
      // Do not move an already-correct keyed row on a watch heartbeat.
      if (sources.children[position] !== row) sources.insertBefore(row, sources.children[position] || null);
      position += 1;
    });
    Object.keys(existing).forEach(function (id) { existing[id].remove(); });
    text('sharing-source-status', !binding() ? 'Connect to view account sources.'
      : !state.sources ? 'Source state unknown. Saved requests remain stoppable below.'
      : !Object.keys(rows).length ? 'No sources reported for this account.' : '');
  }
  function render(payload) {
    if (!payload || !visible()) return false;
    if (state && payload.presentation_order < state.presentation_order) return false;
    if (state && payload.metadata.binding !== state.metadata.binding) {
      boss.value = '';
      actionAttempt += 1;
      text('sharing-action', '');
    }
    state = payload;
    hydrated = true;
    var meta = state.metadata;
    enabled.checked = preferencePending ? preferenceWanted : state.enabled;
    enabled.disabled = !state.available; // never disable Off behind queued On
    WM.el('sharing-refresh').disabled = !state.available;
    var connection = !state.available ? 'Fleet sharing is unavailable in this session.'
      : !meta.loaded ? 'Reading saved connection…'
      : !meta.binding ? 'Not connected. Connect to ' + state.configured_origin + '.'
      : 'Paired with ' + meta.paired_origin + '.' + (meta.has_session ? '' : ' Reconnecting…');
    if (state.runtime_error) connection += ' ' + state.runtime_error;
    else if (state.enabled && !state.telemetry_available) connection += ' Local telemetry is unavailable. Source controls still work.';
    if (state.detail) connection += ' ' + (details[state.detail] || state.detail.replace(/_/g, ' ') + '.');
    if (state.pairing === 'queued') connection += ' Setup queued locally.';
    else if (state.pairing === 'persisted') connection += ' Setup saved, contacting authGD.';
    else if (state.pairing === 'awaiting_approval' && !state.browser_error) connection += ' Approve setup in your browser.';
    text('sharing-connection', connection);
    var retryBrowser = state.browser_retry === 'pair';
    changeOrigin = !!(meta.binding && meta.paired_origin !== state.configured_origin);
    // Retry obtains a new admission for the saved key/origin, not another
    // identity transition just because this build has a different default.
    pairingMode = retryBrowser ? 'initial' : state.detail === 'needs_fresh_key' || changeOrigin ? 'fresh'
      : state.detail === 'needs_upgrade' || state.detail === 'capability_required' ? 'upgrade' : 'initial';
    text('sharing-browser-error', state.browser_error);
    connect.textContent = retryBrowser ? 'Retry setup…' : pairingMode === 'fresh' ? 'Fresh setup…' : pairingMode === 'upgrade' ? 'Upgrade connection…' : 'Connect…';
    connect.hidden = !retryBrowser && !!(meta.binding && pairingMode === 'initial' && state.pairing !== 'needs_retry' && state.detail !== 'pairing_expired');
    connect.disabled = !state.available || !meta.loaded || (!retryBrowser && ['queued', 'persisted', 'awaiting_approval'].indexOf(state.pairing) !== -1);
    WM.el('sharing-confirm-on').hidden = !(state.enabled && (state.local_inhibited || state.participation === 'needs_confirmation'));
    text('sharing-preference', state.preference_error);
    var observed = state.observed_participation;
    var consent = 'This PC: ' + (state.enabled ? 'On' : 'Off')
      + (state.enabled && state.local_inhibited ? ', transmission paused.' : '.')
      + ' authGD participation: ' + (observed ? (observed.enabled ? 'On' : 'Off') : 'not yet observed') + '.';
    if (state.participation === 'queued') consent += ' Choice queued locally.';
    else if (state.participation === 'persisted') consent += ' Choice saved, awaiting authGD.';
    text('sharing-consent', consent);
    paintCharacters();
    paintSources();
    return true;
  }
  function action(method) {
    var args = Array.prototype.slice.call(arguments);
    if (!hydrated) return;
    var attempt = ++actionAttempt;
    var requestedBinding = binding();
    text('sharing-action', '');
    WM.send.apply(WM, args).then(function (result) {
      if (attempt !== actionAttempt || requestedBinding !== binding()) return;
      if (result && result.state && !render(result.state)) return;
      if (attempt !== actionAttempt) return;
      // Historical acceptance, not an ongoing waiting claim. Exact queued /
      // saved / server stages belong to the corresponding source row below.
      var accepted = method === 'fleet_sharing_start_source' ? 'Start requested.'
        : method === 'fleet_sharing_stop_source' ? 'Stop requested.'
        : method === 'fleet_sharing_grant_fleet_read' ? 'Fleet Read browser requested. Use the paired account, then Refresh.'
        : 'Setup requested.';
      text('sharing-action', result && result.queued ? accepted
        : (result && result.error) || 'The action could not be queued. Refresh and retry.');
    });
  }
  function preference(value) {
    if (!hydrated) return;
    var attempt = ++preferenceAttempt;
    preferencePending = true;
    preferenceWanted = value;
    // Paint the user's local request immediately so an in-flight On always
    // leaves a reachable Off. An older reply cannot revert a newer choice.
    enabled.checked = value;
    WM.send('fleet_sharing_set_enabled', value).then(function (result) {
      if (attempt !== preferenceAttempt) return;
      preferencePending = false;
      if (result && result.state) {
        if (!render(result.state)) render(state);
      } else {
        if (!result || !result.applied) enabled.checked = state.enabled;
        text('sharing-preference', !result ? 'Could not apply the sharing choice.' : result.error || '');
      }
    });
  }
  enabled.addEventListener('change', function () { preference(enabled.checked); });
  WM.el('sharing-confirm-on').addEventListener('click', function () { preference(true); });
  boss.addEventListener('change', paintBoss);
  start.addEventListener('click', function () {
    var character = selected();
    if (character) action('fleet_sharing_start_source', character.character_id, character.character_link_epoch, binding());
  });
  grant.addEventListener('click', function () {
    var character = selected();
    if (character) action('fleet_sharing_grant_fleet_read', character.character_id, binding());
  });
  connect.addEventListener('click', function () {
    if (!hydrated) return;
    if (pairingMode !== 'fresh') { action('fleet_sharing_pair', pairingMode); return; }
    var originText = changeOrigin ? 'Switches to ' + state.configured_origin + '. ' : '';
    WM.confirm('Fresh fleet setup', originText + 'Creates a new device key. Old identity-bound pending actions will not carry over. Continue?').then(function (ok) {
      if (ok) action('fleet_sharing_pair', 'fresh', changeOrigin);
    });
  });
  function watch() {
    var current = ++watchGeneration;
    var open = visible();
    // Serialize enter/leave so a slow bridge enter cannot overtake its leave.
    watchChain = watchChain.then(function () { return WM.send('fleet_sharing_watch', open); }).then(function (result) {
      if (current === watchGeneration && open && result && result.state) render(result.state);
    });
  }
  WM.el('sharing-refresh').addEventListener('click', watch);
  document.addEventListener('wm:section', watch);
  document.addEventListener('visibilitychange', watch);
}());
