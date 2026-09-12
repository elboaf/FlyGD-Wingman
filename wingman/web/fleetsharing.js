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
  var actionsInFlight = 0;
  var bindingGeneration = 0;
  var sourceRequests = [];
  var actionMessage = '';
  // Last-known labels/observations are presentation only, never a roster or
  // permission to mutate. Only an authoritative snapshot replaces this set.
  var knownSources = [];
  var knownCharacters = [];
  var readFailed = false;
  var preferencePending = false;
  var preferenceWanted = false;
  var desiredBoss = '';
  var boss = WM.el('sharing-boss');
  var enabled = WM.el('sharing-enabled');
  var connect = WM.el('sharing-connect');
  var start = WM.el('sharing-start');
  var grant = WM.el('sharing-grant');
  var sources = WM.el('sharing-sources');
  var history = WM.el('sharing-history');
  var historySources = WM.el('sharing-history-sources');
  var historySummary = WM.el('sharing-history-summary');
  var pairingMode = 'initial';
  var changeOrigin = false;
  var screenshotFixture = null, screenshotLive = null, screenshotEpoch = 0;
  WM.fleetSharingScreenshot = function (payload) {
    if (payload && (payload.kind !== 'fleet-sharing-screenshot-v1' || JSON.stringify(payload).length > 16384
        || !payload.state || !payload.state.metadata || !payload.state.sources
        || payload.state.sources.characters.length !== 2 || payload.state.sources.sources.length !== 2)) {
      throw new Error('Invalid Fleet sharing screenshot fixture');
    }
    if (payload && !screenshotFixture && (preferencePending || sourceRequests.length || actionsInFlight)) {
      throw new Error('Fleet sharing action in progress — retry capture when settled');
    }
    if (!payload && !screenshotFixture) return;
    var live = screenshotFixture ? screenshotLive : {state: state, boss: desiredBoss,
      sources: knownSources, characters: knownCharacters, message: actionMessage, readFailed: readFailed};
    screenshotEpoch += 1; watchGeneration += 1; actionAttempt += 1; bindingGeneration += 1;
    screenshotFixture = payload ? JSON.parse(JSON.stringify(payload)) : null;
    screenshotLive = payload ? live : null;
    // Restoring cached state is not new read authority. Keep its version in
    // place so render cannot clear a failed Refresh merely because we reset.
    state = payload ? null : live.state; hydrated = false;
    knownSources = payload ? [] : live.sources; knownCharacters = payload ? [] : live.characters;
    desiredBoss = payload ? '' : live.boss; actionMessage = payload ? '' : live.message;
    readFailed = payload ? false : live.readFailed;
    sources.textContent = ''; historySources.textContent = ''; boss.removeAttribute('data-roster');
    history.open = false; WM.el('sharing-eligible').open = false;
    if (payload || live.state) render(payload ? screenshotFixture.state : live.state, false, true);
    else {
      history.hidden = true; historySummary.textContent = 'Previous attempts (0)';
      boss.textContent = ''; enabled.checked = false;
      connect.hidden = false; connect.textContent = 'Connect…';
      WM.el('sharing-eligible-list').textContent = '';
      ['sharing-consent', 'sharing-eligibility', 'sharing-preference', 'sharing-browser-error',
        'sharing-action', 'sharing-source-status'].forEach(function (id) { text(id, ''); });
      unavailable();
    }
  };
  var unavailableMessage = 'Fleet sharing is unavailable in this session.';
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
    return WM.current_route === 'settings' && WM.current_section === 'fleet' && !document.hidden;
  }
  function text(id, value) { WM.el(id).textContent = value || ''; }
  function binding() { return state && state.metadata.binding; }
  function selected() {
    return ((state && state.sources && state.sources.characters) || []).filter(function (row) {
      return String(row.character_id) === boss.value;
    })[0];
  }
  function sourceKey(id) { return id.toLowerCase(); }
  function sourceUnknown() { return !state.sources || !state.available || readFailed; }
  function nameFor(id) {
    var character = knownCharacters.filter(function (row) {
      return row.character_id === id;
    })[0];
    return character ? character.character_name : (id ? 'Character ' + id : 'Unknown character');
  }
  function paintBoss() {
    var character = selected();
    var ready = !!(character && character.has_fleet_read && character.token_usable);
    grant.disabled = !hydrated || !character || sourceUnknown();
    start.disabled = !hydrated || !ready || sourceUnknown() || state.metadata.feature_enabled === false;
    text('sharing-grant-status', !state.metadata.loaded ? 'Reading saved connection…'
      : !binding() ? 'Connect to read your owned characters.'
      : readFailed ? 'Current character state unknown. Refresh to retry.'
      : !state.sources ? 'Loading owned characters. Refresh if needed.'
      : !state.sources.characters.length ? 'No owned characters found in this account.'
      : !character ? 'Choose your fleet boss.'
      : ready ? 'Fleet Read ready. Start checks this character is boss.'
      : 'Grant Fleet Read using the paired account, then Refresh.');
  }
  function paintCharacters() {
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
      boss.setAttribute('data-roster', signature);
    }
    var value = state.sources ? desiredBoss : '';
    if (boss.value !== value) boss.value = value;
    boss.disabled = sourceUnknown() || !characters.length;
    paintBoss();
    var list = WM.el('sharing-eligible-list');
    list.textContent = '';
    var eligibility = readFailed ? null : state.eligibility;
    text('sharing-eligibility', readFailed ? 'Current eligibility unknown. Refresh to retry.'
      : !eligibility ? 'Eligibility has not been observed.'
      : eligibility.state === 'ready' ? 'Currently eligible for sparse telemetry:'
      : eligibility.state === 'participation_off' ? 'Server participation is Off.'
      : 'No verified roster currently makes these characters eligible.');
    ((eligibility && eligibility.characters) || []).forEach(function (row) {
      list.appendChild(WM.make('li', '', nameFor(row.character_id)));
    });
  }
  function nextStart() {
    var characters = state.sources ? state.sources.characters : [];
    var character = selected();
    if (!binding()) return 'Connect to read your owned characters.';
    if (!characters.length) return 'No owned characters found in this account.';
    if (state.metadata.feature_enabled === false) return details.feature_disabled;
    if (character && (!character.has_fleet_read || !character.token_usable)) {
      return 'Grant Fleet Read using the paired account, then Refresh.';
    }
    if (!characters.some(function (row) { return row.has_fleet_read && row.token_usable; })) {
      return 'Choose your current fleet boss, grant Fleet Read using the paired account, then Refresh.';
    }
    return 'Choose your current fleet boss, then Start verification to try again.';
  }
  function paintAction() {
    var messages = actionMessage ? [actionMessage] : [];
    sourceRequests.forEach(function (request) {
      if (!request.source_id) messages.push('Start request in progress for ' + request.name + '…');
    });
    text('sharing-action', messages.join(' '));
  }
  function paintSources() {
    var rows = Object.create(null);
    var existing = Object.create(null);
    [sources, historySources].forEach(function (container) {
      Array.prototype.forEach.call(container.children, function (row) { existing[row.getAttribute('data-source')] = row; });
    });
    function item(id) {
      var key = sourceKey(id);
      if (!rows[key]) rows[key] = {};
      return rows[key];
    }
    knownSources.forEach(function (row) { item(row.source_id).observed = row; });
    (state.source_results || []).forEach(function (result) { item(result.source_id).result = result; });
    (state.pending_sources || []).forEach(function (pending) { item(pending.source_id).pending = pending; });
    sourceRequests.forEach(function (request) {
      if (request.source_id) item(request.source_id).request = request;
    });
    var positions = [0, 0];
    var reasons = Object.create(null);
    var focusTarget = null;
    Object.keys(rows).forEach(function (id) {
      var entry = rows[id];
      var observed = entry.observed;
      var pending = entry.pending;
      var result = entry.result;
      var request = entry.request;
      // Retained observations are not fresh acknowledgements of a current
      // local result. A real observation supersedes that result; a cache cannot.
      var localResult = result && (!observed || sourceUnknown());
      var ended = !!(observed && observed.state === 'ended' && !pending && !request && !localResult);
      var row = existing[id];
      if (!row) {
        row = WM.make('div', 'sharing-source');
        row.setAttribute('data-source', id);
        row.appendChild(WM.make('div', 'sharing-source-text'));
        var stop = WM.make('button', 'btn', 'Stop');
        stop.addEventListener('click', function () {
          if (!hydrated || stop.disabled) return;
          action('fleet_sharing_stop_source', id, binding());
        });
        row.appendChild(stop);
      }
      delete existing[id];
      var focused = row.contains(document.activeElement) ? document.activeElement : null;
      var characterId = (observed && observed.character_id) || (pending && pending.character_id)
        || (result && result.character_id) || (request && request.character_id);
      var label = nameFor(characterId);
      if (label === 'Unknown character') label = 'Source ' + id.slice(0, 8);
      var description = label + ' · ' + (localResult && !pending
        ? result.stage === 'rejected' ? 'Start not saved. Too many pending source controls. Wait, then Start again explicitly.' : 'Start expired. Start again explicitly.'
        : observed ? observed.state : 'Not yet observed');
      if (observed && (!localResult || pending)) {
        if (observed.reason) description += ' — ' + observed.reason.replace(/_/g, ' ');
        if (sourceUnknown()) description += ' · Last known';
      }
      if (pending) description += ' · ' + (pending.operation === 'stop' ? 'Stop' : 'Start')
        + (pending.stage === 'queued' ? ' queued locally' : ' saved, awaiting authGD');
      if (request) description += ' · Stop request in progress…';
      row.firstChild.textContent = description;
      row.firstChild.title = 'Source ' + id;
      // A page request, like worker-pending work, does not itself disable Stop.
      // Disabling on click would blur the control before settlement can move
      // its focus to history. Only current source/pending evidence authorizes it.
      row.lastChild.disabled = !hydrated || !state.available || readFailed
        || (!pending && (sourceUnknown() || !observed || !!localResult || ended));
      row.lastChild.setAttribute('aria-label', 'Stop source for ' + label + ' ' + id);
      var index = ended ? 1 : 0;
      var container = ended ? historySources : sources;
      var position = positions[index]++;
      // Even appendChild(existingRow) drops native keyboard focus in Chrome.
      // Reconcile both lists together, moving only rows whose position changed.
      if (container.children[position] !== row) {
        container.insertBefore(row, container.children[position] || null);
        if (focused && !focused.disabled) focusTarget = focused;
      }
      if (ended) {
        var reason = observed.reason ? observed.reason.replace(/_/g, ' ') : 'No reason reported';
        reasons[reason] = (reasons[reason] || 0) + 1;
        if (focused && (!history.open || focused.disabled)) focusTarget = historySummary;
      }
    });
    Object.keys(existing).forEach(function (id) { existing[id].remove(); });
    history.hidden = positions[1] === 0;
    historySummary.textContent = 'Previous attempts (' + positions[1] + ')';
    if (focusTarget) focusTarget.focus();
    var requestingStart = sourceRequests.some(function (request) { return !request.source_id; });
    text('sharing-source-status', !binding() ? 'Connect to view account sources.'
      : sourceUnknown() ? 'Current source state unknown. Last-known attempts and current local requests are shown below.'
      : !positions[0] && !requestingStart && positions[1] ? 'No current verification. Previous attempts: '
        + Object.keys(reasons).sort().map(function (reason) { return reason + ' (' + reasons[reason] + ')'; }).join('; ')
        + '. ' + nextStart()
      : !positions[0] && !requestingStart && !positions[1] ? 'No sources reported for this account.' : '');
  }
  function unavailable() {
    // A failed read is not a payload or a saved preference. Keep mutations
    // disarmed without inventing connection data or promising worker recovery.
    hydrated = false;
    text('sharing-connection', unavailableMessage);
    text('sharing-grant-status', '');
    Array.prototype.forEach.call(WM.el('fleet-sharing').querySelectorAll('button, input, select'), function (control) {
      control.disabled = true;
    });
  }
  function render(payload, successfulRead, synthetic) {
    if (screenshotFixture && !synthetic) {
      if (payload && (!screenshotLive.state || payload.presentation_order >= screenshotLive.state.presentation_order)) {
        if (successfulRead || !screenshotLive.state || payload.presentation_order > screenshotLive.state.presentation_order) {
          screenshotLive.readFailed = false;
        }
        if (screenshotLive.state && payload.metadata.binding !== screenshotLive.state.metadata.binding) {
          screenshotLive.boss = ''; screenshotLive.sources = []; screenshotLive.characters = [];
        }
        screenshotLive.state = payload;
      }
      return false;
    }
    if (!payload) return false;
    if (state && payload.presentation_order < state.presentation_order) return false;
    var newer = !state || payload.presentation_order > state.presentation_order;
    if (state && payload.metadata.binding !== state.metadata.binding) {
      boss.value = '';
      desiredBoss = '';
      actionAttempt += 1;
      bindingGeneration += 1;
      sourceRequests = [];
      actionMessage = '';
      knownSources = [];
      knownCharacters = [];
      sources.textContent = '';
      historySources.textContent = '';
      history.open = false;
    }
    state = payload;
    // Identical cached replies can arrive after a failed Refresh. Only newer
    // evidence or a successful current watch read may restore read authority.
    if (newer || successfulRead) readFailed = false;
    if (state.sources) {
      knownSources = state.sources.sources;
      knownCharacters = state.sources.characters;
      // Clearing a native select's options also clears its value. Keep the
      // user's choice separately through unknown reads, but revalidate on every
      // authoritative roster, including one delivered while the section is hidden.
      if (!knownCharacters.some(function (row) { return String(row.character_id) === desiredBoss; })) desiredBoss = '';
    }
    // Delivery while hidden still settles requests and invalidates bindings.
    // Only painting and watching belong to section visibility.
    paint();
    return true;
  }
  function paint() {
    if (!state || !visible()) return;
    hydrated = true;
    var meta = state.metadata;
    enabled.checked = preferencePending ? preferenceWanted : state.enabled;
    enabled.disabled = !state.available; // never disable Off behind queued On
    WM.el('sharing-refresh').disabled = !state.available;
    var connection = !state.available ? unavailableMessage
      : !meta.loaded ? 'Reading saved connection…'
      : !meta.binding ? 'Not connected. Connect to ' + state.configured_origin + '.'
      : 'Paired with ' + meta.paired_origin + '.' + (meta.has_session ? '' : ' Reconnecting…');
    if (readFailed) connection += ' Could not refresh current source state. Refresh to retry.';
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
    WM.el('sharing-confirm-on').disabled = !state.available;
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
    paintAction();
    if (!state.available) unavailable();
  }
  function action(method) {
    var args = Array.prototype.slice.call(arguments);
    if (screenshotFixture || !hydrated) return;
    var attempt = ++actionAttempt;
    var requestedBinding = binding();
    var generation = bindingGeneration;
    actionMessage = '';
    var sourceAction = method === 'fleet_sharing_start_source' || method === 'fleet_sharing_stop_source';
    if (sourceAction) {
      // Start has no UUID until Python returns one. Keep character feedback,
      // not a fabricated source row. A Stop already identifies its keyed row.
      sourceRequests.push({attempt: attempt,
        source_id: method === 'fleet_sharing_stop_source' ? sourceKey(args[1]) : null,
        character_id: method === 'fleet_sharing_start_source' ? args[1] : null,
        name: method === 'fleet_sharing_start_source' ? nameFor(args[1]) : ''});
    }
    paintSources();
    paintAction();
    actionsInFlight += 1;
    WM.send.apply(WM, args).then(function (result) {
      // WM.send resolves bridge failures as null. Retire every actual call,
      // including a superseded pairing/grant reply, before testing ownership.
      actionsInFlight -= 1;
      if (generation !== bindingGeneration || requestedBinding !== binding()) return;
      // Every actual bridge completion retires only its own request, even when
      // a newer action owns the message. Worker pending stages remain separate.
      sourceRequests = sourceRequests.filter(function (request) { return request.attempt !== attempt; });
      if (!sourceAction && attempt !== actionAttempt) { paint(); return; }
      // Another source action may own the message, but this versioned payload
      // can still report pending worker work for the source that just replied.
      if (result && result.state && !render(result.state)) { paint(); return; }
      if (attempt !== actionAttempt) { paint(); return; }
      // Historical acceptance, not an ongoing waiting claim. Exact queued /
      // saved / server stages belong to the corresponding source row below.
      var accepted = method === 'fleet_sharing_start_source' ? 'Start requested.'
        : method === 'fleet_sharing_stop_source' ? 'Stop requested.'
        : method === 'fleet_sharing_grant_fleet_read' ? 'Fleet Read browser requested. Use the paired account, then Refresh.'
        : 'Setup requested.';
      actionMessage = result && result.queued ? accepted
        : (result && result.error) || 'The action could not be queued. Refresh and retry.';
      paint();
    });
  }
  function preference(value) {
    if (screenshotFixture || !hydrated) return;
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
        if (!render(result.state)) paint();
      } else {
        if (!result || !result.applied) enabled.checked = state.enabled;
        text('sharing-preference', !result ? 'Could not apply the sharing choice.' : result.error || '');
      }
    });
  }
  enabled.addEventListener('change', function () { preference(enabled.checked); });
  WM.el('sharing-confirm-on').addEventListener('click', function () { preference(true); });
  boss.addEventListener('change', function () {
    if (!hydrated || boss.disabled) return;
    desiredBoss = boss.value;
    paintBoss();
    paintSources();
  });
  start.addEventListener('click', function () {
    var character = selected();
    if (character && !start.disabled) action('fleet_sharing_start_source', character.character_id, character.character_link_epoch, binding());
  });
  grant.addEventListener('click', function () {
    var character = selected();
    if (character && !grant.disabled) action('fleet_sharing_grant_fleet_read', character.character_id, binding());
  });
  connect.addEventListener('click', function () {
    if (screenshotFixture || !hydrated) return;
    if (pairingMode !== 'fresh') { action('fleet_sharing_pair', pairingMode); return; }
    var originText = changeOrigin ? 'Switches to ' + state.configured_origin + '. ' : '';
    var owner = screenshotEpoch;
    WM.confirm('Fresh fleet setup', originText + 'Creates a new device key. Old identity-bound pending actions will not carry over. Continue?').then(function (ok) {
      if (ok && owner === screenshotEpoch) action('fleet_sharing_pair', 'fresh', changeOrigin);
    });
  });
  function watch() {
    if (screenshotFixture) { paint(); return; }
    var owner = screenshotEpoch;
    var current = ++watchGeneration;
    var open = visible();
    var requestedState;
    paint();
    // Serialize enter/leave so a slow bridge enter cannot overtake its leave.
    watchChain = watchChain.then(function () {
      if (owner !== screenshotEpoch) return null;
      requestedState = state;
      return WM.send('fleet_sharing_watch', open);
    }).then(function (result) {
      if (owner !== screenshotEpoch || current !== watchGeneration || !open || !visible()) return;
      if (result && result.state) render(result.state, true);
      // An unversioned failure cannot supersede newer evidence received during
      // this read. Equal-version copies are still the same last-known state.
      // Off stays reachable because preference ownership is separate.
      else if (!state) unavailable();
      else if (requestedState && state.presentation_order === requestedState.presentation_order) {
        readFailed = true;
        paint();
      }
    });
  }
  WM.el('sharing-refresh').addEventListener('click', watch);
  document.addEventListener('wm:section', watch);
  document.addEventListener('visibilitychange', watch);
}());
