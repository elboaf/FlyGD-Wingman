/* Profiles' overview/layout sharing tool. Import creates a new profile only. */
(function () {
  'use strict';

  var generation = 0;
  var context = null;
  var roster = null;
  var busy = false;
  var mode = '';
  var draft = null;
  var requestSerial = 0;
  // Leaving destroys the private draft, not ownership of a sent Create. The
  // worker releases its lock before pushing, so more than one receipt can wait.
  var receipts = [];

  function isCurrent(captured) {
    return captured === generation && WM.current_route === 'uisetup';
  }

  function status(text, error) {
    var node = WM.el('us-status');
    node.textContent = text || '';
    node.className = error ? 'hint err' : 'hint';
  }

  function clearSummary() {
    WM.el('us-summary').hidden = true;
    ['us-source', 'us-counts', 'us-windows', 'us-warnings'].forEach(function (id) {
      WM.el(id).textContent = '';
    });
  }

  function invalidate() {
    generation += 1;
    busy = false;
    clearSummary();
    status('');
  }

  function selected(items, path) {
    return items.filter(function (item) { return item.path === path; })[0];
  }

  function pair() {
    if (!context || !roster || !roster.setup_available
        || !roster.account_identity_available || !selected(roster.profiles, context.profile)) return null;
    var prefix = mode === 'import' ? 'setup-' : 'us-';
    var character = selected(roster.characters, WM.el(prefix + 'character').value);
    var account = selected(roster.accounts, WM.el(prefix + 'account').value);
    if (!character || !account || account.character_ids.indexOf(character.id) === -1) return null;
    return {profile: context.profile, account: account.path, character: character.path,
      label: character.name + ' · ' + account.name + ' · '
        + selected(roster.profiles, context.profile).name};
  }

  function controls() {
    var ready = mode === 'export' && !!pair() && !busy && WM.current_route === 'uisetup';
    WM.setEnabled('us-copy', ready);
    WM.setEnabled('us-save', ready);
    // Refresh and Back remain exits from failed or pending reads.
    WM.setEnabled('us-refresh', mode === 'export' && !!context);
  }

  function fill(id, items, value, placeholder) {
    var node = WM.el(id);
    node.textContent = '';
    var option = WM.make('option', '', placeholder);
    option.value = '';
    node.appendChild(option);
    items.forEach(function (item) {
      var choice = WM.make('option', '', item.name);
      choice.value = item.path;
      node.appendChild(choice);
    });
    node.value = selected(items, value) ? value : '';
    node.disabled = !items.length;
  }

  function copyRoster(payload) {
    function rows(items) {
      return items.map(function (item) {
        return {path: item.path, id: item.id, name: item.name,
          character_ids: (item.character_ids || []).slice()};
      });
    }
    return {profiles: rows(payload.profiles), accounts: rows(payload.accounts),
      characters: rows(payload.characters), setup_available: payload.setup_available,
      account_identity_available: payload.account_identity_available};
  }

  function load(profile, character, account) {
    invalidate();
    context.profile = profile;
    roster = null;
    fill('us-character', [], '', 'Choose character');
    fill('us-account', [], '', 'Choose confirmed account');
    WM.el('us-limits').textContent = '';
    status('Reading local profile context…');
    controls();
    var captured = generation;
    Promise.all([WM.send('eve_settings_setup_context', profile),
      WM.send('eve_settings_setup_limits')]).then(function (results) {
      if (!isCurrent(captured)) return;
      var payload = results[0], limits = results[1];
      if (!payload || !payload.ok) {
        status(payload && payload.error || 'Could not read the local profile context. Refresh source to retry.', true);
        return;
      }
      if (payload.root !== context.root || payload.server !== context.server
          || payload.profile !== profile) {
        status('The Profiles context changed. Return to Profiles and reopen Share setup.', true);
        return;
      }
      roster = copyRoster(payload);
      fill('us-profile', roster.profiles, profile, 'Choose source profile');
      fill('us-character', roster.characters, character, 'Choose character');
      fill('us-account', roster.accounts, account, 'Choose confirmed account');
      WM.el('us-limits').textContent = 'Wingman support limits: ' + limits.max_presets
        + ' filters, ' + limits.max_tabs + ' tabs, ' + limits.max_window_groups
        + ' overview groups, ' + limits.max_ship_labels + ' ship labels, '
        + limits.max_layout_windows + ' layout records; ' + (limits.max_bytes / 1024 / 1024)
        + ' MiB UTF-8. Larger or unsupported setups are refused, never truncated.';
      sourceChanged();
    }).catch(function () {
      if (!isCurrent(captured)) return;
      status('Could not read the local profile context. Refresh source to retry.', true);
      controls();
    });
  }

  function sourceChanged() {
    invalidate();
    controls();
    if (roster && !roster.setup_available) {
      status('The settings codec is not available in this install.', true);
    } else if (roster && !roster.account_identity_available) {
      status('Account identification is not available for this profile.', true);
    } else if (!pair()) {
      status('Choose a confirmed account/character pair with both local files.');
    } else snapshot('preview');
  }

  function quantity(count, label) {
    return count + ' ' + label + (count === 1 ? '' : 's');
  }

  function renderSummary(result, source) {
    var counts = result.summary.counts;
    WM.el('us-source').textContent = 'Source: ' + source.label;
    WM.el('us-counts').textContent = [quantity(counts.presets, 'filter'),
      quantity(counts.tabs, 'tab'), quantity(counts.windowGroups, 'overview group'),
      quantity(counts.shipLabels, 'ship label'), quantity(counts.layoutWindows, 'layout window')].join(' · ');
    WM.el('us-windows').textContent = result.summary.windowLabels.join(', ');
    WM.el('us-warnings').textContent = result.warnings.join(' ');
    WM.el('us-summary').hidden = false;
  }

  function finish(captured, text, error) {
    if (!isCurrent(captured)) return;
    busy = false;
    status(text, error);
    controls();
  }

  function snapshot(action) {
    var source = pair();
    if (mode !== 'export' || !source || busy || WM.current_route !== 'uisetup') return;
    // A result is never reused by Copy/Save: the source files may have changed
    // since the preview. Only this invocation owns the returned artifact text.
    var captured = generation;
    busy = true;
    clearSummary();
    status('Taking a fresh snapshot for ' + source.label + '…');
    controls();
    WM.send('eve_settings_setup_export', source.profile, source.account, source.character)
      .then(function (result) {
        if (!isCurrent(captured)) return;
        if (!result || !result.ok) {
          finish(captured, result && result.error || 'Could not read the setup. Retry with EVE closed.', true);
          return;
        }
        renderSummary(result, source);
        if (action === 'preview') {
          finish(captured, 'Snapshot ready. Copy and Save each read a fresh snapshot.');
        } else if (action === 'copy') {
          var failed = function () {
            finish(captured, 'Could not copy to the clipboard. Try again or use Save file.', true);
          };
          status('Copying setup for ' + source.label + '…');
          // Clipboard APIs can be absent, synchronously throw, or reject later.
          // A successful serialization alone must never say "copied".
          try {
            navigator.clipboard.writeText(result.text).then(function () {
              finish(captured, 'Setup copied for ' + source.label + '.');
            }, failed);
          } catch (error) { failed(); }
        } else {
          status('Choose a file for ' + source.label + '…');
          return WM.send('eve_settings_setup_save_file', result.text).then(function (reply) {
            if (!isCurrent(captured)) return;
            if (reply && reply.cancelled) finish(captured, 'Save cancelled. Nothing was written.');
            else if (reply && reply.ok) finish(captured, 'Setup saved for ' + source.label + ': ' + reply.path);
            else finish(captured, reply && reply.error || 'Could not save the setup file. Try again.', true);
          }, function () {
            finish(captured, 'Could not save the setup file. Try again.', true);
          });
        }
      }).catch(function () {
        finish(captured, 'Could not read the setup. Retry with EVE closed.', true);
      });
  }

  function importStatus(text, error) {
    var node = WM.el('setup-status');
    node.textContent = text || '';
    node.className = error ? 'hint err' : 'hint';
  }

  function profilesStatus(text, error) {
    var node = WM.el('es-setup-status');
    node.textContent = text;
    node.className = error ? 'hint err' : 'hint';
  }

  function retireReceipt(pending) {
    pending.completed = true;
    receipts = receipts.filter(function (item) { return item !== pending; });
  }

  function discard(id) {
    if (!id) return;
    // Best-effort cleanup has no page authority. In particular its delayed
    // response must never clear an offer issued by a newer review.
    WM.send('eve_settings_setup_discard', id).catch(function () {});
  }

  function clearImportSummary() {
    WM.el('setup-summary').hidden = true;
    ['type', 'counts', 'target', 'destination', 'retention', 'windows', 'limitations', 'warnings'].forEach(function (id) {
      WM.el('setup-' + id).textContent = '';
    });
    WM.el('setup-native').hidden = true;
  }

  function clearImport() {
    if (draft) discard(draft.review);
    draft = null;
    ['setup-text', 'setup-name'].forEach(function (id) { WM.el(id).value = ''; });
    ['setup-base', 'setup-character', 'setup-account'].forEach(function (id) { fill(id, [], '', ''); });
    WM.el('setup-keep-labels').checked = false;
    WM.el('setup-label-choice').hidden = true;
    WM.el('setup-limits').textContent = '';
    clearImportSummary();
    importStatus('');
  }

  function editable() {
    return mode === 'import' && !!draft && !draft.creating && !draft.published
      && WM.current_route === 'uisetup';
  }

  function importControls() {
    var edit = editable();
    ['text', 'name', 'keep-labels', 'refresh'].forEach(function (id) { WM.setEnabled('setup-' + id, edit); });
    ['paste', 'file'].forEach(function (id) { WM.setEnabled('setup-' + id, edit && !draft.reading); });
    ['base', 'character', 'account'].forEach(function (id) {
      var rows = roster && roster[id === 'base' ? 'profiles' : id + 's'];
      WM.setEnabled('setup-' + id, edit && !!(rows && rows.length));
    });
    WM.setEnabled('setup-review', edit && !draft.reviewing && !draft.reading && !!pair()
      && !!draft.text.trim() && !!draft.name.trim());
    WM.setEnabled('setup-create', edit && !!draft.review);
    WM.el('setup-back').textContent = draft && (draft.creating || draft.published) ? 'Back to Profiles' : 'Cancel';
  }

  function importChanged(replacedText) {
    if (!editable()) return;
    draft.version += 1;
    draft.reviewing = false;
    draft.reading = false;
    discard(draft.review);
    draft.review = '';
    if (replacedText) {
      WM.el('setup-keep-labels').checked = false;
      WM.el('setup-label-choice').hidden = true;
    }
    draft.text = WM.el('setup-text').value;
    draft.name = WM.el('setup-name').value;
    draft.keep = WM.el('setup-keep-labels').checked;
    clearImportSummary();
    importStatus('Review the setup again before creating a profile.');
    importControls();
  }

  function loadImport(profile, character, account) {
    if (!editable()) return;
    importChanged(false);
    context.profile = profile;
    roster = null;
    fill('setup-character', [], '', 'Choose character');
    fill('setup-account', [], '', 'Choose confirmed account');
    importStatus('Reading local base profile…');
    importControls();
    // Typing a name/text while context is loading invalidates review, not this
    // independent read. A base change or leaving still invalidates the roster.
    var view = generation, read = ++draft.contextRead;
    Promise.all([WM.send('eve_settings_setup_context', profile), WM.send('eve_settings_setup_limits')])
      .then(function (results) {
        if (!isCurrent(view) || !draft || read !== draft.contextRead) return;
        var payload = results[0], limits = results[1];
        if (!payload || !payload.ok) {
          importStatus(payload && payload.error || 'Could not read the base. Refresh base to retry.', true);
          return;
        }
        if (payload.root !== context.root || payload.server !== context.server || payload.profile !== profile) {
          importStatus('The Profiles context changed. Cancel and reopen Import setup.', true);
          return;
        }
        roster = copyRoster(payload);
        fill('setup-base', roster.profiles, profile, 'Choose local base');
        fill('setup-character', roster.characters, character, 'Choose character');
        fill('setup-account', roster.accounts, account, 'Choose confirmed account');
        WM.el('setup-limits').textContent = 'Wingman support limits: ' + limits.max_presets
          + ' filters, ' + limits.max_tabs + ' tabs, ' + limits.max_window_groups
          + ' overview groups, ' + limits.max_ship_labels + ' ship labels, '
          + limits.max_layout_windows + ' layout records; ' + (limits.max_bytes / 1024 / 1024)
          + ' MiB UTF-8. Unsupported or larger inputs are refused, never truncated.';
        if (!roster.setup_available) importStatus('The settings codec is not available in this install.', true);
        else if (!roster.account_identity_available) importStatus('Account identification is not available for this profile.', true);
        else importStatus('Choose a confirmed local pair and a new name, then Review.');
        importControls();
      }).catch(function () {
        if (isCurrent(view) && draft && read === draft.contextRead) {
          importStatus('Could not read the base. Refresh base to retry.', true);
          importControls();
        }
      });
  }

  function readImport(file) {
    if (!editable() || draft.reading) return;
    importChanged(false);
    var view = generation, version = draft.version;
    draft.reading = true;
    importControls();
    importStatus(file ? 'Choose a setup file…' : 'Reading clipboard…');
    function current() { return isCurrent(view) && draft && version === draft.version; }
    function failed() {
      if (!current()) return;
      draft.reading = false;
      importStatus(file ? 'Could not read the setup file. Try again.' : 'Could not read the clipboard. Paste into the text field or choose a file.', true);
      importControls();
    }
    try {
      var request = file ? WM.send('eve_settings_setup_read_file') : navigator.clipboard.readText();
      request.then(function (reply) {
        if (!current()) return;
        draft.reading = false;
        if (file && (!reply || !reply.ok)) {
          importStatus(reply && reply.cancelled ? 'File choice cancelled. Input unchanged; Review again.'
            : reply && reply.error || 'Could not read the setup file. Try again.', !(reply && reply.cancelled));
          importControls();
          return;
        }
        WM.el('setup-text').value = file ? reply.text : reply;
        importChanged(true);
        WM.el('setup-text').focus();
      }, failed);
    } catch (error) { failed(); }
  }

  function renderReview(result, target, name, keep) {
    var counts = result.summary.counts;
    // The validated Wingman model always has overview geometry. Zero imported
    // layout windows is the native configuration-only case, not local geometry.
    var native = counts.layoutWindows === 0;
    WM.el('setup-type').textContent = native ? 'Native overview YAML' : 'Wingman overview and in-space layout preset';
    WM.el('setup-counts').textContent = [quantity(counts.presets, 'filter'), quantity(counts.tabs, 'tab'),
      quantity(counts.windowGroups, 'overview group'), quantity(counts.shipLabels, 'ship label'),
      quantity(counts.layoutWindows, 'layout window')].join(' · ');
    WM.el('setup-target').textContent = 'Recipient: ' + target.label;
    WM.el('setup-destination').textContent = 'New profile: ' + name.trim() + '. Existing profiles will not be overwritten.';
    WM.el('setup-retention').textContent = 'Retained from your local base: resolution, display mode, monitor preferences, UI scale, core_public__.yaml and prefs.ini, and unrelated settings.'
      + (keep ? ' Your complete ship labels are retained.' : ' Imported overview configuration replaces the active setup; unrelated saved filters remain.');
    WM.el('setup-native').textContent = native ? 'Overview configuration only; no window layout. Supplied tabs become one group in the primary overview window. Primary and non-overview geometry stay local; surplus overview instances are retired. Absent options, including omitted column settings, stay local.' : '';
    WM.el('setup-native').hidden = !native;
    WM.el('setup-windows').textContent = native ? 'No layout windows imported.' : 'Included layout windows: ' + result.summary.windowLabels.join(', ');
    var warnings = result.warnings.filter(function (text, index, items) { return items.indexOf(text) === index; });
    // Native parser warnings also appear in limitations. Keep their emphasized
    // owner below without dropping distinct limitations or extra worker warnings.
    WM.el('setup-limitations').textContent = result.summary.limitations.filter(function (text, index, items) {
      return warnings.indexOf(text) === -1 && items.indexOf(text) === index;
    }).join(' ');
    WM.el('setup-warnings').textContent = warnings.join(' ');
    WM.el('setup-summary').hidden = false;
  }

  function reviewImport() {
    if (!editable() || draft.reviewing || draft.reading || !pair() || !draft.text.trim() || !draft.name.trim()) return;
    importChanged(false);
    var view = generation, version = draft.version, target = pair(), name = draft.name, keep = draft.keep;
    draft.reviewing = true;
    importStatus('Reviewing the setup and local base with EVE closed…');
    importControls();
    WM.send('eve_settings_setup_review', draft.text, target.profile, target.account, target.character, name, keep)
      .then(function (result) {
        if (!isCurrent(view) || !draft || version !== draft.version) {
          discard(result && result.review_id);
          return;
        }
        draft.reviewing = false;
        if (result && result.needs_label_choice) WM.el('setup-label-choice').hidden = false;
        var summary = result && result.summary && result.summary.counts;
        if (summary) renderReview(result, target, name, keep);
        if (!result || !result.ok || !summary || typeof result.review_id !== 'string'
            || !result.review_id || result.needs_label_choice) {
          discard(result && result.review_id);
          importStatus(result && result.error || 'Review did not authorize creation. Review the setup again.', true);
        } else {
          draft.review = result.review_id;
          importStatus('Review ready. Create profile makes a new copy; Cancel creates nothing.');
        }
        importControls();
        if (result && result.needs_label_choice) {
          WM.el('setup-keep-labels').focus();
          // The wrapped checkbox's invisible input has absolute positioning;
          // focusing it alone can scroll away from its visible label at the floor.
          WM.el('setup-label-choice').scrollIntoView({block: 'center'});
        } else if (draft.review) {
          WM.el('setup-summary').focus();
          WM.el('setup-summary').scrollIntoView({block: 'start'});
        }
      }).catch(function () {
        if (!isCurrent(view) || !draft || version !== draft.version) return;
        draft.reviewing = false;
        importStatus('Could not review the setup. Review again with EVE closed.', true);
        importControls();
      });
  }

  function createImport() {
    if (!editable() || !draft.review) return;
    requestSerial += 1;
    var pending = {view: generation, review: draft.review,
      request: 'setup-' + Date.now() + '-' + requestSerial, completed: false};
    // A worker can finish before the starter promise resolves, even before
    // send returns. Install identity and lock the draft BEFORE crossing bridge.
    receipts.push(pending);
    draft.creating = pending;
    draft.review = '';
    importStatus('Creating profile. Leaving does not cancel creation.');
    importControls();
    function current() { return isCurrent(pending.view) && draft && draft.creating === pending && !pending.completed; }
    function uncertain() {
      if (pending.completed) return;
      var text = 'Could not confirm whether creation started. Leaving does not cancel creation. Check Profiles before trying again.';
      profilesStatus(text, true);
      if (current()) importStatus(text, true);
    }
    WM.send('eve_settings_setup_create', pending.review, pending.request).then(function (reply) {
      if (pending.completed) return;
      if (reply && reply.accepted === false) {
        var attached = current();
        retireReceipt(pending);
        discard(pending.review);
        var text = (reply.error || 'Creation was not started.') + ' Review the setup again before creating.';
        profilesStatus(text, true);
        if (attached) {
          draft.creating = null;
          importChanged(false);
          importStatus(text, true);
        }
      } else if (!reply || reply.accepted !== true) uncertain();
    }, uncertain);
  }

  WM.openUiSetup = function (options) {
    clearImport();
    invalidate();
    // Do not retain the mutable Profiles payload, its copy selection, or any
    // raw settings. Read the setup-specific roster/confirmed links afresh.
    var input = options.context || {};
    context = {root: input.root || '', server: input.server || '', profile: input.profile || ''};
    mode = options.mode;
    roster = null;
    fill('us-profile', [], '', 'Choose source profile');
    fill('us-character', [], '', 'Choose character');
    fill('us-account', [], '', 'Choose confirmed account');
    WM.el('us-limits').textContent = '';
    WM.el('us-export').hidden = mode !== 'export';
    WM.el('setup-import').hidden = mode !== 'import';
    // Only the active mode owns the accent; never two primaries on this route.
    WM.el('us-copy').className = mode === 'export' ? 'btn acc' : 'btn';
    WM.el('setup-create').className = mode === 'import' ? 'btn acc' : 'btn';
    WM.route('uisetup');
    controls();
    if (mode === 'import') {
      draft = {text: '', name: '', keep: false, version: 0, contextRead: 0,
        review: '', reviewing: false, reading: false, creating: null, published: false};
      loadImport(context.profile, options.preferred_character || '', '');
      WM.el('setup-back').focus();
    } else {
      WM.el('us-back').focus();
      load(context.profile, options.preferred_character || '', '');
    }
  };

  WM.uiSetupDone = function (payload) {
    if (!payload || payload.operation !== 'ui_setup_create') return false;
    var pending = receipts.filter(function (item) {
      return payload.request_id === item.request && payload.review_id === item.review;
    })[0];
    if (!pending) return false;
    retireReceipt(pending);
    var text = payload.published
      ? 'Profile created: ' + payload.path + '. Restart the launcher to refresh its profile list, then select it there. Wingman has not activated it in EVE.'
        + (payload.warning ? ' ' + payload.warning : '')
        + (!payload.selection_persisted && !payload.warning ? ' Wingman could not remember the new selection; choose the created profile in Profiles.' : '')
      : (payload.error || 'Profile creation failed.') + ' Review the setup again before creating.';
    profilesStatus(text, !payload.published);
    // This receipt still owns an outcome after Back, but not the current tool's
    // draft, authorization, focus or route. The sole completion owner refreshes
    // Profiles from state, never by selecting the outcome's path.
    if (isCurrent(pending.view) && draft && draft.creating === pending) {
      if (payload.published) draft.published = true;
      else {
        draft.creating = null;
        importChanged(false);
      }
      importStatus(text, !payload.published);
      importControls();
      WM.el('setup-status').focus();
    }
    return true;
  };

  function back() {
    var opener = mode === 'import' ? 'es-setup-import' : 'es-setup-share';
    WM.route('evesettings');
    WM.el(opener).focus();
  }

  function wire() {
    WM.el('setup-back').addEventListener('click', back);
    WM.el('setup-text').addEventListener('input', function () { importChanged(true); });
    WM.el('setup-name').addEventListener('input', function () { importChanged(false); });
    ['setup-character', 'setup-account', 'setup-keep-labels'].forEach(function (id) {
      WM.el(id).addEventListener('change', function () { importChanged(false); });
    });
    WM.el('setup-base').addEventListener('change', function () { loadImport(WM.el('setup-base').value, '', ''); });
    WM.el('setup-refresh').addEventListener('click', function () {
      if (context) loadImport(context.profile, WM.el('setup-character').value, WM.el('setup-account').value);
    });
    WM.el('setup-paste').addEventListener('click', function () { readImport(false); });
    WM.el('setup-file').addEventListener('click', function () { readImport(true); });
    WM.el('setup-review').addEventListener('click', reviewImport);
    WM.el('setup-create').addEventListener('click', createImport);
    WM.el('us-back').addEventListener('click', back);
    WM.el('us-copy').addEventListener('click', function () { snapshot('copy'); });
    WM.el('us-save').addEventListener('click', function () { snapshot('save'); });
    WM.el('us-refresh').addEventListener('click', function () {
      if (context && mode === 'export') load(context.profile,
        WM.el('us-character').value, WM.el('us-account').value);
    });
    WM.el('us-profile').addEventListener('change', function () {
      load(WM.el('us-profile').value, '', '');
    });
    ['us-character', 'us-account'].forEach(function (id) {
      WM.el(id).addEventListener('change', sourceChanged);
    });
    document.addEventListener('keydown', function (event) {
      if (WM.current_route === 'uisetup' && event.key === 'Escape') {
        event.preventDefault();
        back();
      }
    });
    document.addEventListener('wm:route', function (event) {
      if (event.detail === 'uisetup') return;
      clearImport();
      invalidate();
      context = null;
      roster = null;
      mode = '';
      ['us-profile', 'us-character', 'us-account'].forEach(function (id) {
        fill(id, [], '', '');
      });
      WM.el('us-limits').textContent = '';
      controls();
      importControls();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
}());
