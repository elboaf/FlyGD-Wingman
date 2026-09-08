/* Profiles' read-only overview/layout export tool. No EVE mutations here. */
(function () {
  'use strict';

  var generation = 0;
  var context = null;
  var roster = null;
  var busy = false;
  var mode = '';

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
    if (mode !== 'export' || !roster || !roster.setup_available
        || !roster.account_identity_available) return null;
    var character = selected(roster.characters, WM.el('us-character').value);
    var account = selected(roster.accounts, WM.el('us-account').value);
    if (!character || !account || account.character_ids.indexOf(character.id) === -1) return null;
    return {profile: context.profile, account: account.path, character: character.path,
      label: character.name + ' · ' + account.name + ' · '
        + selected(roster.profiles, context.profile).name};
  }

  function controls() {
    var ready = !!pair() && !busy && WM.current_route === 'uisetup';
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
    if (!source || busy || WM.current_route !== 'uisetup') return;
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

  WM.openUiSetup = function (options) {
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
    WM.route('uisetup');
    controls();
    WM.el('us-back').focus();
    if (mode !== 'export') {
      status('Setup import is not available yet. Return to Profiles.');
      return;
    }
    load(context.profile, options.preferred_character || '', '');
  };

  WM.uiSetupDone = function () {
    // Export never starts creation, so it cannot own a matching request/review.
    // Acceptance and correlated completion must be added together when import
    // becomes available, not as a partial mutation lifecycle.
    return false;
  };

  function back() {
    WM.route('evesettings');
    WM.el('es-setup-share').focus();
  }

  function wire() {
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
      invalidate();
      context = null;
      roster = null;
      mode = '';
      ['us-profile', 'us-character', 'us-account'].forEach(function (id) {
        fill(id, [], '', '');
      });
      WM.el('us-limits').textContent = '';
      controls();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
}());
