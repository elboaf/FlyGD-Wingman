/* Manual-verification harness. Inert inside the real app: it does nothing
 * unless the page is loaded WITHOUT pywebview and with ?dev=1, which can
 * only happen in a browser opened by hand. It exists so the page can be
 * eyeballed without launching Python, and is deliberately the only file
 * that fabricates data. */
(function () {
  'use strict';
  if (window.pywebview) return;
  if (!/[?&]dev=1/.test(window.location.search)) return;

  var devSearch = new URLSearchParams(window.location.search);

  var log = function (name) {
    return function () {
      var args = Array.prototype.slice.call(arguments);
      console.log('DEV api.' + name + '(', args, ')');
      return Promise.resolve(null);
    };
  };

  var api = {};
  // The roster is deliberately derived below: visible follows hidden, as it
  // does in Api.fleet_bar_settings(), so the harness cannot paint a state
  // Python would never return. The three base rows show running-visible,
  // running-hidden, and known-offline character states.
  var fleetBar = {
    enabled: true,
    x: null,
    y: null,
    seen: ['Ariadne', 'Basilisk', 'Cairn'],
    hidden: ['Basilisk'],
    running: ['Ariadne', 'Basilisk'],
    revision: 1
  };

  function fleetBarState() {
    return {
      enabled: fleetBar.enabled,
      x: fleetBar.x,
      y: fleetBar.y,
      seen: fleetBar.seen.slice(),
      hidden: fleetBar.hidden.slice(),
      revision: fleetBar.revision,
      characters: fleetBar.seen.map(function (name) {
        return {
          name: name,
          running: fleetBar.enabled
            ? fleetBar.running.indexOf(name) !== -1 : null,
          visible: fleetBar.hidden.indexOf(name) === -1
        };
      })
    };
  }
  ['delete_selected', 'start_upload', 'retry', 'cancel_upload',
   'open_path', 'copy_path', 'detect_folder',
   // The Uploader's three quick actions. Doubled rather than added to
   // test_dev_harness.py's known-gaps list because ?dev=1 is the only way
   // any of them is seen outside Windows: play_recording and
   // post_recent_logs both end in a Python-side shell or network call the
   // harness cannot model, but the CONTROLS -- a menu item that acts and
   // closes, a button that goes inert while a post runs -- are exactly
   // what needs eyeballing. rename_recording answers below, because it
   // has a return value the page renders.
   'play_recording', 'post_recent_logs',
   'connect_google', 'dialog_response', 'minimize', 'close',
   'skills_refresh', 'skills_reload_plans', 'skills_open_plans_folder'
  ].forEach(function (name) { api[name] = log(name); });

  // Answers {ok, error}, which is the shape list.js branches on: a
  // refusal re-opens the prompt with the typed text still in it. The
  // double accepts everything, so the harness shows the accepting path;
  // the refusing path is Python's, and every sentence in it is composed
  // there (an upload running, a reserved device name, a collision).
  api.rename_recording = function (rowId, stem) {
    console.log('DEV api.rename_recording(', rowId, stem, ')');
    return Promise.resolve({ ok: true, error: '' });
  };

  // NOT generic stubs. The per-field endpoints return
  // {applied, persisted, error} and the page reads all three, so the
  // generic stub's null would read as a bridge failure and revert every
  // control -- a dev harness that lies about the flow it is most used to
  // exercise. There is no Save button to exercise any more; each of these
  // is a commit on its own.
  ['set_privacy', 'set_notify_mode', 'set_category',
   'set_discord_webhook', 'clear_discord_webhook',
   'set_alert_enabled', 'set_alert_pve_filter', 'set_alert_persist',
   'set_alert_volume',
   // M3. Same three-key shape, and it belongs in this list rather than the
   // generic one for the same reason: the ABOUT card reverts its checkbox
   // on anything that is not `applied`.
   'set_start_on_login',
   // Task 6: same shape again, and set_preview_show_labels/set_preview_
   // opacity revert their control on a refused write just like the rest
   // of this list.
   'set_preview_show_labels', 'set_preview_opacity',
   // Task 10: same shape; settings.js reverts the checkbox on anything
   // that is not `applied`, same as every entry above.
   'set_minimize_inactive_clients',
   // Task 8: same shape; previews.js and the (future) layout-reset control
   // read `applied`/`error` the same way, even though neither reverts a
   // control state on refusal -- Size… is a one-shot dialog, not a
   // persistent checkbox.
   'set_preview_size', 'copy_preview_layout', 'reset_preview_layouts',
   // Task 9: same shape; settings.js reverts the checkbox on anything
   // that is not `applied`, same as show_labels/opacity above.
   'set_preview_snap',
   // Same shape again: settings.js reverts the checkbox on anything that
   // is not `applied`.
   'set_preview_lock_aspect',
   // Same shape once more: a discrete checkbox settings.js reverts on
   // anything that is not `applied`.
   'set_preview_lock_default',
   // And again. The harness cannot show what this one DOES -- hiding
   // happens in the preview host, which ?dev=1 has none of -- only that
   // the checkbox renders, commits and reports.
   'set_preview_hide_on_lost_focus',
   // The floating sig bar's writer. Same shape: settings.js reverts the
   // checkbox on anything that is not `applied`, like every entry above.
   'toggle_sig_bar',
   // The selection ring's colour picker. Same shape; settings.js reports
   // the error string on anything that is not `applied`.
   'set_preview_selection_color',
   // The apply-to-open-previews action. Same shape; there is no control
   // state to revert, only a status line to fill.
   'apply_preview_default_size'
  ].forEach(function (name) {
    api[name] = function (value) {
      console.log('DEV api.' + name + '(', value, ')');
      var res = {applied: true, persisted: true, error: null};
      // The two webhook endpoints carry the new summary line back on their
      // own return, because nothing repaints the Settings route after page
      // load. A double without it leaves the harness showing the stale
      // line this fixes -- which is the bug, not the fix.
      if (name === 'set_discord_webhook') {
        res.webhook_status = 'discord.com/api/webhooks/1…';
      } else if (name === 'clear_discord_webhook') {
        res.webhook_status = 'not configured';
      }
      return Promise.resolve(res);
    };
  });

  // The one endpoint that returns a fourth key. `note` is set_folder's
  // post-commit report (round 3, B11): the count only exists once the
  // rebind has walked the folder, so the page cannot be checked against a
  // three-key double here -- the slot it fills would simply never appear.
  // Recording folder only, like the real one. The unchanged-path early
  // return is NOT doubled: it is Python's branch and has its own test,
  // and reproducing it here would only make the slot harder to reach in
  // the harness that exists to show it.
  api.set_folder = function (which, path) {
    console.log('DEV api.set_folder(', which, ',', path, ')');
    var res = {applied: true, persisted: true, error: null};
    if (which === 'recording' && path) {
      res.note = 'Now watching ' + path
               + '. 12 recordings already there were not announced.';
    }
    return Promise.resolve(res);
  };

  // Same tier as the block above: set_alert_event and test_alert both
  // return {applied, persisted, error} and the page reads all three.
  api.set_alert_event = function (event, field, value) {
    console.log('DEV api.set_alert_event(', event, field, value, ')');
    return Promise.resolve({applied: true, persisted: true, error: null});
  };

  // Task 11: same tier -- previews.js reverts the row's checkbox on
  // anything that is not `applied`, same as the rest of this file.
  api.set_preview_locked = function (name, locked) {
    console.log('DEV api.set_preview_locked(', name, locked, ')');
    return Promise.resolve({applied: true, persisted: true, error: null});
  };

  api.set_never_minimize = function (name, enabled) {
    console.log('DEV api.set_never_minimize(', name, enabled, ')');
    return Promise.resolve({applied: true, persisted: true, error: null});
  };

  // Same tier again. The real endpoint also sweeps and rebinds, neither of
  // which exists under ?dev=1 -- what the harness has to double is the
  // {applied, persisted, error} shape previews.js reverts the box on, and
  // the re-render it drives off a successful reply, which is how an
  // opted-out row's other controls go grey in the browser.
  api.set_preview_excluded = function (name, excluded) {
    console.log('DEV api.set_preview_excluded(', name, excluded, ')');
    return Promise.resolve({applied: true, persisted: true, error: null});
  };

  // Task 8: a read that validates rather than a plain double -- the page
  // sends whatever was typed and expects {w, h, error} back, mirroring
  // Api.parse_preview_size (geometry.py owns the one definition of what a
  // size looks like; this fixture only has to match its SHAPE, not
  // reimplement its rules).
  api.parse_preview_size = function (text) {
    console.log('DEV api.parse_preview_size(', text, ')');
    var m = /^\s*(\d+)\s*[xX]\s*(\d+)\s*$/.exec(text || '');
    if (!m) {
      return Promise.resolve({w: 0, h: 0, error: 'Sizes look like 1280x720.'});
    }
    return Promise.resolve({w: parseInt(m[1], 10), h: parseInt(m[2], 10), error: null});
  };

  // Two arguments, so it cannot ride the single-value allowlist above.
  // Same {applied, persisted, error} shape settings.js reverts the field
  // on -- and `persisted: true`, because the not-persisted branch has its
  // own sentence and a harness that never reaches it would hide one.
  api.set_preview_default_size = function (w, h) {
    console.log('DEV api.set_preview_default_size(', w, h, ')');
    return Promise.resolve({applied: true, persisted: true, error: null});
  };

  api.test_alert = function (event) {
    console.log('DEV api.test_alert(', event, ')');
    return Promise.resolve({applied: true, persisted: false, error: null});
  };

  // get_alert_state is a read (like get_preview_hotkey_state), not a
  // push -- see alerts.js. Kept in one place so the Alerts card can be
  // eyeballed under ?dev=1 without launching Python.
  api.get_alert_state = function () {
    console.log('DEV api.get_alert_state()');
    return Promise.resolve({
      previews_enabled: true,
      alerts: settingsPayload().settings.preview.alerts,
      running: true,
      last_error: null,
      characters: ['Aiga Otsolen', 'Zuelo Parvi'],
      gamelogs_folder: 'C:\\Users\\tng\\Documents\\EVE\\logs\\Gamelogs'
    });
  };

  // NOT generic stubs, for the same reason save_settings above is not: the
  // page guards on `!ok`, and the real bridge returns True even for a
  // no-op. A null here would make plan switching and forget dead in the
  // browser while working under Python.
  api.skills_select_plan = function (name) {
    console.log('DEV api.skills_select_plan(', name, ')');
    skills.selected_plan_name = name;
    setTimeout(function () { window.onSkills(skills); }, 0);
    return Promise.resolve(true);
  };

  api.skills_select_group = function (name) {
    console.log('DEV api.skills_select_group(', name, ')');
    skills.selected_group = name || '';
    setTimeout(function () { window.onSkills(skills); }, 0);
    return Promise.resolve(true);
  };

  api.skills_set_character_group = function (id, name) {
    console.log('DEV api.skills_set_character_group(', id, name, ')');
    skills.characters.forEach(function (ch) {
      if (ch.character_id === id) ch.group = name || '';
    });
    devRecountGroups();
    setTimeout(function () { window.onSkills(skills); }, 0);
    return Promise.resolve(true);
  };

  api.skills_rename_group = function (oldName, newName) {
    console.log('DEV api.skills_rename_group(', oldName, newName, ')');
    skills.characters.forEach(function (ch) {
      if (ch.group.toLowerCase() === oldName.toLowerCase()) ch.group = newName;
    });
    if (skills.selected_group.toLowerCase() === oldName.toLowerCase()) {
      skills.selected_group = newName;
    }
    devRecountGroups();
    setTimeout(function () { window.onSkills(skills); }, 0);
    return Promise.resolve(true);
  };

  api.skills_delete_group = function (name) {
    console.log('DEV api.skills_delete_group(', name, ')');
    skills.characters.forEach(function (ch) {
      if (ch.group.toLowerCase() === name.toLowerCase()) ch.group = '';
    });
    if (skills.selected_group.toLowerCase() === name.toLowerCase()) {
      skills.selected_group = '';
    }
    devRecountGroups();
    setTimeout(function () { window.onSkills(skills); }, 0);
    return Promise.resolve(true);
  };

  // Python derives `groups` from the roster (controller._groups_locked).
  // The fake must derive it the same way or the rail and the rows disagree
  // the moment anything is reassigned here.
  function devRecountGroups() {
    var byKey = {};
    skills.characters.forEach(function (ch) {
      if (!ch.group) return;
      var key = ch.group.toLowerCase();
      if (byKey[key]) byKey[key].member_count += 1;
      else byKey[key] = { name: ch.group, member_count: 1 };
    });
    skills.groups = Object.keys(byKey).sort().map(function (k) { return byKey[k]; });
  }

  // NOT a generic stub, for the same reason skills_select_plan is not: the
  // page guards on the returned text and writes it to the clipboard, so a
  // null would make `Copy plan` look dead in the browser while working
  // under Python. Roman numerals and a trailing newline, because that is
  // what plans.format_lines emits -- the harness has to show the text the
  // user would actually paste into EVE.
  api.skills_plan_text = function (name) {
    console.log('DEV api.skills_plan_text(', name, ')');
    return Promise.resolve('Amarr Cruiser V\nGallente Cruiser V\n'
                           + 'Energy Grid Upgrades IV\n'
                           + 'Heavy Assault Cruisers I\n');
  };

  api.skills_state = function () {
    console.log('DEV api.skills_state()');
    return Promise.resolve(skills);
  };

  // Shared EVE character-management scenarios. Deliberately independent of
  // Skills' own route payload and Fittings' workspace payload: the Settings
  // roster is a fresh read of eve_characters_state(), not a projection of a
  // sibling screen, and both the manual harness and screenshot tool must
  // exercise that read without inventing credentials, hashes, or raw scopes.
  var charactersScenarioRequested = devSearch.has('characters');
  var charactersScenario = devSearch.get('characters') || 'partial';
  var DEV_CHARACTERS_SCENARIOS = {
    "full": {
      "available": true,
      "auth_configured": true,
      "authorization_activity": "idle",
      "authorization_notice": "",
      "warnings": [],
      "characters": [
        {"character_id": 7, "character_name": "Aiga Otsolen", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 9, "character_name": "Zuelo Parvi", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 11, "character_name": "Rhea Vestibule", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""}
      ]
    },
    "partial": {
      "available": true,
      "auth_configured": true,
      "authorization_activity": "idle",
      "authorization_notice": "",
      "warnings": [],
      "characters": [
        {"character_id": 7, "character_name": "Aiga Otsolen", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 4, "character_name": "Skills Only", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 11, "character_name": "Rhea Vestibule", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""}
      ]
    },
    "reauthentication": {
      "available": true,
      "auth_configured": true,
      "authorization_activity": "idle",
      "authorization_notice": "Character ownership changed. Re-authenticate.",
      "warnings": [],
      "characters": [
        {"character_id": 4, "character_name": "Needs Reauth", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "sign_in", "fittings": "sign_in", "needs_reauth": true, "persistence_error": "Character ownership changed; cached skill data was cleared."},
        {"character_id": 7, "character_name": "Aiga Otsolen", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""}
      ]
    },
    "warning": {
      "available": true,
      "auth_configured": true,
      "authorization_activity": "idle",
      "authorization_notice": "Wingman stores at most 50 characters. Forget one before adding another.",
      "warnings": [],
      "characters": [
        {"character_id": 7, "character_name": "Aiga Otsolen", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 4, "character_name": "Skills Only", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""}
      ]
    },
    "empty": {
      "available": true,
      "auth_configured": true,
      "authorization_activity": "idle",
      "authorization_notice": "",
      "warnings": [],
      "characters": []
    },
    "waiting": {
      "available": true,
      "auth_configured": true,
      "authorization_activity": "waiting",
      "authorization_notice": "",
      "warnings": [],
      "characters": [
        {"character_id": 7, "character_name": "Aiga Otsolen", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 4, "character_name": "Skills Only", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""}
      ]
    },
    "terminal-failure": {
      "available": true,
      "auth_configured": true,
      "authorization_activity": "idle",
      "authorization_notice": "Character ownership changed. Forget the existing character before authenticating it again.",
      "warnings": [],
      "characters": [
        {"character_id": 7, "character_name": "Aiga Otsolen", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 4, "character_name": "Skills Only", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""}
      ]
    },
    "partial-cleanup": {
      "available": true,
      "auth_configured": true,
      "authorization_activity": "idle",
      "authorization_notice": "This character was removed, but some cleanup was not saved. Reconcile first before adding it back.",
      "warnings": [],
      "characters": [
        {"character_id": 7, "character_name": "Aiga Otsolen", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 11, "character_name": "Rhea Vestibule", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""}
      ]
    },
    "maximum-50": {
      "available": true,
      "auth_configured": true,
      "authorization_activity": "idle",
      "authorization_notice": "",
      "warnings": [],
      "characters": [
        {"character_id": 90000000, "character_name": "Character 01", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000001, "character_name": "Character 02", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000002, "character_name": "Character 03", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000003, "character_name": "Character 04", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000004, "character_name": "Character 05", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000005, "character_name": "Character 06", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000006, "character_name": "Character 07", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000007, "character_name": "Character 08", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000008, "character_name": "Character 09", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000009, "character_name": "Character 10", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000010, "character_name": "Character 11", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000011, "character_name": "Character 12", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000012, "character_name": "Character 13", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000013, "character_name": "Character 14", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000014, "character_name": "Character 15", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000015, "character_name": "Character 16", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000016, "character_name": "Character 17", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000017, "character_name": "Character 18", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000018, "character_name": "Character 19", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000019, "character_name": "Character 20", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000020, "character_name": "Character 21", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000021, "character_name": "Character 22", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000022, "character_name": "Character 23", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000023, "character_name": "Character 24", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000024, "character_name": "Character 25", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000025, "character_name": "Character 26", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000026, "character_name": "Character 27", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000027, "character_name": "Character 28", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000028, "character_name": "Character 29", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000029, "character_name": "Character 30", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000030, "character_name": "Character 31", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000031, "character_name": "Character 32", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000032, "character_name": "Character 33", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000033, "character_name": "Character 34", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000034, "character_name": "Character 35", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000035, "character_name": "Character 36", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000036, "character_name": "Character 37", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000037, "character_name": "Character 38", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000038, "character_name": "Character 39", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000039, "character_name": "Character 40", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000040, "character_name": "Character 41", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000041, "character_name": "Character 42", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000042, "character_name": "Character 43", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000043, "character_name": "Character 44", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000044, "character_name": "Character 45", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000045, "character_name": "Character 46", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000046, "character_name": "Character 47", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000047, "character_name": "Character 48", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000048, "character_name": "Character 49", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "authorized", "needs_reauth": false, "persistence_error": ""},
        {"character_id": 90000049, "character_name": "Character 50", "authenticated_utc": "2026-09-04T12:00:00+00:00", "skills": "authorized", "fittings": "sign_in", "needs_reauth": false, "persistence_error": ""}
      ]
    },
    "unavailable": {
      "available": false,
      "auth_configured": true,
      "authorization_activity": "idle",
      "authorization_notice": "",
      "warnings": ["Restore eve_authority.json, then restart Wingman."],
      "characters": []
    }
  };
  var _devCharacters = devCharactersScenario(charactersScenario);

  function devCharactersText(value) {
    return value == null ? '' : String(value);
  }

  function devCharactersScenario(name) {
    var scenario = DEV_CHARACTERS_SCENARIOS[devCharactersText(name)]
      || DEV_CHARACTERS_SCENARIOS.partial;
    return JSON.parse(JSON.stringify(scenario));
  }

  function devCharactersState() {
    return JSON.parse(JSON.stringify(_devCharacters));
  }

  function devPushCharactersChanged(reason) {
    setTimeout(function () {
      if (window.onEveAuthorityChanged) {
        window.onEveAuthorityChanged({ reason: reason });
      }
    }, 0);
  }

  api.eve_characters_state = function () {
    console.log('DEV api.eve_characters_state()');
    return Promise.resolve(devCharactersState());
  };

  api.eve_characters_authenticate = function () {
    console.log('DEV api.eve_characters_authenticate()');
    if (!_devCharacters.auth_configured) {
      return Promise.resolve({
        accepted: false,
        error: 'This build has no EVE application id configured.'
      });
    }
    if (_devCharacters.authorization_activity === 'waiting') {
      return Promise.resolve({
        accepted: false,
        error: 'An EVE sign-in is already in progress.'
      });
    }
    _devCharacters.authorization_activity = 'waiting';
    _devCharacters.authorization_notice = '';
    devPushCharactersChanged('authenticate');
    return Promise.resolve({ accepted: true, error: '' });
  };

  api.eve_characters_cancel_auth = function () {
    console.log('DEV api.eve_characters_cancel_auth()');
    if (_devCharacters.authorization_activity !== 'waiting') {
      return Promise.resolve({
        accepted: false,
        error: 'The EVE sign-in is not running.'
      });
    }
    _devCharacters.authorization_activity = 'idle';
    _devCharacters.authorization_notice = '';
    devPushCharactersChanged('cancel');
    return Promise.resolve({ accepted: true, error: '' });
  };

  api.eve_characters_forget = function (characterId) {
    console.log('DEV api.eve_characters_forget(', characterId, ')');
    var before = _devCharacters.characters.length;
    _devCharacters.characters = _devCharacters.characters.filter(function (row) {
      return row.character_id !== characterId;
    });
    if (_devCharacters.characters.length === before) {
      return Promise.resolve({
        applied: false,
        persisted: false,
        error: 'That character is already gone.'
      });
    }
    _devCharacters.authorization_notice = '';
    devPushCharactersChanged('forget');
    return Promise.resolve({ applied: true, persisted: true, error: '' });
  };

  // Task 9's fixture library: enough entries and characters to exercise
  // every state the workspace can render by hand -- unfiled/filed/
  // superseded scoping, search and ship filters, a >100-row page 2, an
  // unresolved type name, a non-deployable (Invalid-flag) fit, and copy
  // target eligibility states without route-owned authorization controls.
  // This module is the only file allowed to fabricate data (see the file
  // banner), so this is where that fabrication lives rather than in
  // fittings.js.
  var fittings = {
    refreshing: false,
    characters: [
      { character_id: 90000010, character_name: 'Aria Voss', status: 'enabled',
        fetched_utc: '2026-09-03T10:00:00+00:00', error: '', stale: false },
      { character_id: 90000011, character_name: 'Bex Talon', status: 'enabled',
        fetched_utc: '2026-08-20T08:00:00+00:00',
        error: 'ESI request failed (500): Internal Server Error', stale: true },
      { character_id: 90000012, character_name: 'Cato Rune', status: 'enable',
        fetched_utc: '', error: '', stale: false },
      { character_id: 90000013, character_name: 'Dess Marlow',
        status: 'reauthenticate', fetched_utc: '', error: '', stale: false },
      // Three more enabled/fresh characters, added so a single copy batch
      // can show more than one outcome at once -- Aria alone (the only
      // enabled+fresh+not-stale character above) cannot demonstrate
      // "partial" results, because copyEligible() requires all three of
      // those and every other character above fails at least one. Task 12
      // scenario characters, driven by fittings_start_copy below:
      // Eryn is the plain success case, Fio is scripted to come back
      // Unknown (ambiguous no-response), and Gio is scripted to trip the
      // fitting-bucket throttle stop -- matching the design doc's "a
      // fitting-bucket 429 also stops the whole batch" policy.
      { character_id: 90000014, character_name: 'Eryn Voss', status: 'enabled',
        fetched_utc: '2026-09-03T10:00:00+00:00', error: '', stale: false },
      { character_id: 90000015, character_name: 'Fio Kest', status: 'enabled',
        fetched_utc: '2026-09-03T10:00:00+00:00', error: '', stale: false },
      { character_id: 90000016, character_name: 'Gio Renn', status: 'enabled',
        fetched_utc: '2026-09-03T10:00:00+00:00', error: '', stale: false }
    ],
    collections: [
      { id: 'dev-alliance', name: 'Alliance' },
      { id: 'dev-ratting', name: 'Ratting' }
    ],
    entries: [
      { id: 'fit-rifter-solo', name: 'Rifter - Solo PvP', ship_type_id: 587,
        ship_name: 'Rifter', description: 'Fast tackle, disengages on a scram.',
        collection_ids: [], superseded_by: null, deployable: true,
        created_utc: '2026-08-01T00:00:00+00:00',
        updated_utc: '2026-08-01T00:00:00+00:00',
        items: [
          { location: 'high', type_id: 2456, type_name: '150mm Light AutoCannon II', quantity: 3 },
          { location: 'medium', type_id: 3244, type_name: '1MN Afterburner II', quantity: 1 },
          { location: 'low', type_id: 519, type_name: 'Gyrostabilizer II', quantity: 2 }
        ],
        aliases: [{ name: 'Rifter - Solo PvP', description: '' },
                  { name: 'Rifter Tackle Fit', description: 'imported alias' }],
        presences: [
          { character_id: 90000010, character_name: 'Aria Voss', source_name: 'Rifter - Solo PvP',
            first_seen_utc: '2026-08-01T00:00:00+00:00',
            last_confirmed_utc: '2026-09-03T10:00:00+00:00', discovered_batch_id: 'batch-1' },
          { character_id: 90000011, character_name: 'Bex Talon', source_name: 'Rifter Tackle Fit',
            first_seen_utc: '2026-08-05T00:00:00+00:00',
            last_confirmed_utc: '2026-08-20T08:00:00+00:00', discovered_batch_id: 'batch-2' }
        ] },
      { id: 'fit-merlin-fleet', name: 'Merlin - Fleet Doctrine', ship_type_id: 603,
        ship_name: 'Merlin', description: 'Standard fleet doctrine fit.',
        collection_ids: ['dev-alliance'], superseded_by: null, deployable: true,
        created_utc: '2026-09-01T00:00:00+00:00',
        updated_utc: '2026-09-01T00:00:00+00:00',
        items: [
          { location: 'high', type_id: 2453, type_name: 'Light Neutron Blaster II', quantity: 3 },
          { location: 'medium', type_id: 12613, type_name: 'Medium Shield Extender II', quantity: 2 },
          { location: 'low', type_id: 519, type_name: 'Gyrostabilizer II', quantity: 1 }
        ],
        aliases: [{ name: 'Merlin - Fleet Doctrine', description: '' }],
        presences: [
          { character_id: 90000010, character_name: 'Aria Voss', source_name: 'Merlin - Old Doctrine',
            first_seen_utc: '2026-09-01T00:00:00+00:00',
            last_confirmed_utc: '2026-09-03T10:00:00+00:00', discovered_batch_id: 'batch-3' }
        ] },
      { id: 'fit-merlin-old', name: 'Merlin - Old Doctrine', ship_type_id: 603,
        ship_name: 'Merlin', description: 'Superseded by the current doctrine.',
        collection_ids: ['dev-alliance'], superseded_by: 'fit-merlin-fleet', deployable: true,
        created_utc: '2026-06-01T00:00:00+00:00',
        updated_utc: '2026-09-01T00:00:00+00:00',
        items: [
          { location: 'high', type_id: 2453, type_name: 'Light Neutron Blaster II', quantity: 3 }
        ],
        aliases: [{ name: 'Merlin - Old Doctrine', description: '' }],
        // No presence left on any character -- exercised as the entry the
        // Delete flow can actually complete against in the harness.
        presences: [] },
      { id: 'fit-unresolved', name: 'Unnamed Import', ship_type_id: 99999,
        ship_name: '', description: '',
        collection_ids: ['dev-ratting'], superseded_by: null, deployable: true,
        created_utc: '2026-09-02T00:00:00+00:00',
        updated_utc: '2026-09-02T00:00:00+00:00',
        items: [{ location: 'high', type_id: 88888, type_name: '', quantity: 1 }],
        aliases: [{ name: 'Unnamed Import', description: '' }],
        presences: [] },
      { id: 'fit-noncombat', name: 'Impairor - Rookie', ship_type_id: 590,
        ship_name: 'Impairor', description: 'A rookie ship template; nothing to copy.',
        collection_ids: [], superseded_by: null, deployable: false,
        created_utc: '2026-07-01T00:00:00+00:00',
        updated_utc: '2026-07-01T00:00:00+00:00',
        items: [{ location: 'Invalid', type_id: 1, type_name: 'Rookie Fitting', quantity: 1 }],
        aliases: [{ name: 'Impairor - Rookie', description: '' }],
        presences: [] },
      { id: 'fit-stale-owner', name: 'Punisher - Mission Runner', ship_type_id: 598,
        ship_name: 'Punisher', description: 'Last confirmed before Bex went stale.',
        collection_ids: [], superseded_by: null, deployable: true,
        created_utc: '2026-08-10T00:00:00+00:00',
        updated_utc: '2026-08-10T00:00:00+00:00',
        items: [{ location: 'high', type_id: 2860, type_name: 'Small Focused Beam Laser II', quantity: 3 }],
        aliases: [{ name: 'Punisher - Mission Runner', description: '' }],
        presences: [
          { character_id: 90000011, character_name: 'Bex Talon', source_name: 'Punisher - Mission Runner',
            first_seen_utc: '2026-08-10T00:00:00+00:00',
            last_confirmed_utc: '2026-08-20T08:00:00+00:00', discovered_batch_id: 'batch-2' }
        ] },
      // A deliberately engineered name conflict: two different fits (a
      // Merlin and a Rifter, so they can never canonically match) that
      // share one preferred name. fit-conflict-existing is already on
      // Eryn under that name; copying fit-conflict-source (no presence
      // anywhere) to Eryn hits devCopyPair's conflict branch below,
      // because Eryn already has a DIFFERENT entry's presence recorded
      // under that same casefolded name.
      { id: 'fit-conflict-existing', name: 'Fleet Doctrine Alpha', ship_type_id: 603,
        ship_name: 'Merlin', description: 'Occupies the name the source fit also wants.',
        collection_ids: [], superseded_by: null, deployable: true,
        created_utc: '2026-08-15T00:00:00+00:00',
        updated_utc: '2026-08-15T00:00:00+00:00',
        items: [{ location: 'high', type_id: 2453, type_name: 'Light Neutron Blaster II', quantity: 3 }],
        aliases: [{ name: 'Fleet Doctrine Alpha', description: '' }],
        presences: [
          { character_id: 90000014, character_name: 'Eryn Voss', source_name: 'Fleet Doctrine Alpha',
            first_seen_utc: '2026-08-15T00:00:00+00:00',
            last_confirmed_utc: '2026-09-03T10:00:00+00:00', discovered_batch_id: 'batch-4' }
        ] },
      { id: 'fit-conflict-source', name: 'Fleet Doctrine Alpha', ship_type_id: 587,
        ship_name: 'Rifter', description: 'Wants a name Eryn already has on a different hull.',
        collection_ids: [], superseded_by: null, deployable: true,
        created_utc: '2026-09-02T00:00:00+00:00',
        updated_utc: '2026-09-02T00:00:00+00:00',
        items: [{ location: 'high', type_id: 2456, type_name: '150mm Light AutoCannon II', quantity: 3 }],
        aliases: [{ name: 'Fleet Doctrine Alpha', description: '' }],
        presences: [] }
    ]
  };

  // Over one hundred filler entries so paging (page 2 of the "All
  // fittings" scope) is reachable by hand rather than only by pytest.
  (function () {
    var ships = [
      { id: 603, name: 'Merlin' }, { id: 587, name: 'Rifter' },
      { id: 598, name: 'Punisher' }, { id: 594, name: 'Incursus' },
      { id: 591, name: 'Tormentor' }
    ];
    for (var index = 0; index < 108; index += 1) {
      var ship = ships[index % ships.length];
      var label = (index < 9 ? '00' : index < 99 ? '0' : '') + (index + 1);
      fittings.entries.push({
        id: 'fit-gen-' + index, name: 'Generated Fit ' + label,
        ship_type_id: ship.id, ship_name: ship.name,
        // The very first generated row ("Generated Fit 001") is
        // deliberately non-deployable, and deliberately the ONLY thing
        // that differs from the rest of this loop. Task 12's copy-preflight
        // and copy-limit screenshot stages need a non-deployable pair and
        // a >20-write refusal respectively, both alongside curated fixtures
        // that sort BEFORE this loop ("Fleet Doctrine Alpha" x2) -- and
        // fittings_state() pages at 100, so anything sorting after this
        // block (Impairor, Merlin, Punisher, Rifter, Unnamed above) lands
        // on page 2 and cannot share a page, or a copy selection, with
        // them. Reusing the first row of a block that is already on page 1
        // avoids inventing a ninth curated fixture just to dodge paging.
        description: index === 0 ? 'A rookie template; nothing to copy.' : '',
        collection_ids: [], superseded_by: null, deployable: index !== 0,
        created_utc: '2026-09-01T00:00:00+00:00', updated_utc: '2026-09-01T00:00:00+00:00',
        items: index === 0
          ? [{ location: 'Invalid', type_id: 1, type_name: 'Rookie Fitting', quantity: 1 }]
          : [{ location: 'high', type_id: 2453, type_name: 'Light Neutron Blaster II', quantity: 1 }],
        aliases: [{ name: 'Generated Fit ' + label, description: '' }],
        presences: []
      });
    }
  }());

  var FIT_PAGE_SIZE = 100;

  function fitScoped(collectionId) {
    if (collectionId === 'unfiled') {
      return fittings.entries.filter(function (e) { return !e.collection_ids.length; });
    }
    if (collectionId === 'superseded') {
      return fittings.entries.filter(function (e) { return !!e.superseded_by; });
    }
    if (collectionId === 'all' || !collectionId) return fittings.entries.slice();
    return fittings.entries.filter(function (e) {
      return e.collection_ids.indexOf(collectionId) !== -1;
    });
  }

  function fitFiltered(scoped, search, shipTypeId) {
    var out = shipTypeId
      ? scoped.filter(function (e) { return e.ship_type_id === shipTypeId; })
      : scoped;
    var needle = (search || '').trim().toLowerCase();
    if (!needle) return out;
    return out.filter(function (e) {
      if (e.name.toLowerCase().indexOf(needle) !== -1) return true;
      if ((e.ship_name || '').toLowerCase().indexOf(needle) !== -1) return true;
      return e.aliases.some(function (a) { return a.name.toLowerCase().indexOf(needle) !== -1; });
    });
  }

  function fitCollectionSummaries() {
    var unfiled = fittings.entries.filter(function (e) { return !e.collection_ids.length; }).length;
    var superseded = fittings.entries.filter(function (e) { return !!e.superseded_by; }).length;
    var counts = {};
    fittings.collections.forEach(function (c) { counts[c.id] = 0; });
    fittings.entries.forEach(function (e) {
      e.collection_ids.forEach(function (id) {
        if (id in counts) counts[id] += 1;
      });
    });
    return [
      { id: 'all', name: 'All fittings', count: fittings.entries.length },
      { id: 'unfiled', name: 'Unfiled', count: unfiled },
      { id: 'superseded', name: 'Superseded', count: superseded }
    ].concat(fittings.collections.map(function (c) {
      return { id: c.id, name: c.name, count: counts[c.id] };
    }));
  }

  function fitShipOptions(scoped) {
    var byId = {};
    scoped.forEach(function (e) {
      if (!(e.ship_type_id in byId)) byId[e.ship_type_id] = e.ship_name;
    });
    return Object.keys(byId).map(function (key) {
      return { type_id: parseInt(key, 10), name: byId[key] };
    }).sort(function (a, b) {
      return (a.name || '').localeCompare(b.name || '') || a.type_id - b.type_id;
    });
  }

  function fitSummaryRow(entry) {
    return {
      id: entry.id, name: entry.name, ship_type_id: entry.ship_type_id,
      ship_name: entry.ship_name, collection_ids: entry.collection_ids.slice(),
      is_unfiled: !entry.collection_ids.length, superseded_by: entry.superseded_by,
      presence_count: entry.presences.length, deployable: entry.deployable,
      updated_utc: entry.updated_utc
    };
  }

  function fitPushChanged(reason) {
    // Mirrors production timing: Python's push is fire-and-forget through
    // evaluate_js, never synchronous with the bridge call that triggered it.
    setTimeout(function () {
      if (window.onFittingsChanged) window.onFittingsChanged({ reason: reason });
    }, 0);
  }

  api.fittings_state = function (filters) {
    console.log('DEV api.fittings_state(', filters, ')');
    filters = filters || {};
    var collectionId = filters.collection_id || 'all';
    var page = filters.page && filters.page > 0 ? filters.page : 1;
    var scoped = fitScoped(collectionId);
    var filtered = fitFiltered(scoped, filters.search, filters.ship_type_id);
    filtered = filtered.slice().sort(function (a, b) {
      var an = a.name.toLowerCase();
      var bn = b.name.toLowerCase();
      if (an < bn) return -1;
      if (an > bn) return 1;
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
    });
    var start = (page - 1) * FIT_PAGE_SIZE;
    var rows = filtered.slice(start, start + FIT_PAGE_SIZE).map(fitSummaryRow);
    return Promise.resolve({
      available: true,
      warnings: [],
      collections: fitCollectionSummaries(),
      characters: fittings.characters.map(function (ch) {
        return { character_id: ch.character_id, character_name: ch.character_name,
                 status: ch.status, fetched_utc: ch.fetched_utc, error: ch.error,
                 stale: ch.stale };
      }),
      ships: fitShipOptions(scoped),
      rows: rows,
      total: filtered.length,
      page: page,
      page_size: FIT_PAGE_SIZE,
      filters: { collection_id: collectionId, search: filters.search || '',
                 ship_type_id: filters.ship_type_id || null },
      refreshing: fittings.refreshing
    });
  };

  api.fittings_detail = function (entryId) {
    console.log('DEV api.fittings_detail(', entryId, ')');
    var entry = fittings.entries.filter(function (e) { return e.id === entryId; })[0];
    if (!entry) return Promise.resolve(null);
    return Promise.resolve({
      id: entry.id, name: entry.name, description: entry.description,
      ship_type_id: entry.ship_type_id, ship_name: entry.ship_name,
      items: entry.items, deployable: entry.deployable,
      collection_ids: entry.collection_ids.slice(), superseded_by: entry.superseded_by,
      aliases: entry.aliases, presences: entry.presences,
      created_utc: entry.created_utc, updated_utc: entry.updated_utc
    });
  };

  api.fittings_refresh = function (characterIds) {
    console.log('DEV api.fittings_refresh(', characterIds, ')');
    fittings.refreshing = true;
    var targets = characterIds || fittings.characters
      .filter(function (c) { return c.status === 'enabled'; })
      .map(function (c) { return c.character_id; });
    var total = targets.length;
    if (!total) { fittings.refreshing = false; return Promise.resolve(true); }
    targets.forEach(function (characterId, index) {
      setTimeout(function () {
        if (window.onFittingsProgress) {
          window.onFittingsProgress({ character_id: characterId, completed: index + 1,
                                       total: total, error: '' });
        }
        if (index === total - 1) {
          fittings.refreshing = false;
          fitPushChanged('refresh');
        }
      }, (index + 1) * 350);
    });
    return Promise.resolve(true);
  };

  api.fittings_create_collection = function (name) {
    console.log('DEV api.fittings_create_collection(', name, ')');
    var id = 'dev-collection-' + (fittings.collections.length + 1);
    fittings.collections.push({ id: id, name: name });
    fitPushChanged('collection');
    return Promise.resolve(id);
  };

  api.fittings_rename_collection = function (collectionId, name) {
    console.log('DEV api.fittings_rename_collection(', collectionId, name, ')');
    var collection = fittings.collections.filter(function (c) { return c.id === collectionId; })[0];
    if (collection) collection.name = name;
    fitPushChanged('collection');
    return Promise.resolve(!!collection);
  };

  api.fittings_delete_collection = function (collectionId) {
    console.log('DEV api.fittings_delete_collection(', collectionId, ')');
    fittings.collections = fittings.collections.filter(function (c) { return c.id !== collectionId; });
    fittings.entries.forEach(function (e) {
      e.collection_ids = e.collection_ids.filter(function (id) { return id !== collectionId; });
    });
    fitPushChanged('collection');
    return Promise.resolve(true);
  };

  api.fittings_update_metadata = function (entryId, name, description) {
    console.log('DEV api.fittings_update_metadata(', entryId, name, description, ')');
    var entry = fittings.entries.filter(function (e) { return e.id === entryId; })[0];
    if (entry) { entry.name = name; entry.description = description; }
    fitPushChanged('metadata');
    return Promise.resolve(!!entry);
  };

  api.fittings_set_membership = function (entryId, collectionId, member) {
    console.log('DEV api.fittings_set_membership(', entryId, collectionId, member, ')');
    var entry = fittings.entries.filter(function (e) { return e.id === entryId; })[0];
    if (entry) {
      var has = entry.collection_ids.indexOf(collectionId) !== -1;
      if (member && !has) entry.collection_ids.push(collectionId);
      if (!member && has) {
        entry.collection_ids = entry.collection_ids.filter(function (id) { return id !== collectionId; });
      }
    }
    fitPushChanged('collection_membership');
    return Promise.resolve(!!entry);
  };

  api.fittings_set_supersession = function (entryId, supersededBy) {
    console.log('DEV api.fittings_set_supersession(', entryId, supersededBy, ')');
    var entry = fittings.entries.filter(function (e) { return e.id === entryId; })[0];
    if (entry) entry.superseded_by = supersededBy || null;
    fitPushChanged('supersession');
    return Promise.resolve(!!entry);
  };

  api.fittings_delete_entry = function (entryId) {
    console.log('DEV api.fittings_delete_entry(', entryId, ')');
    var entry = fittings.entries.filter(function (e) { return e.id === entryId; })[0];
    if (entry && entry.presences.length) return Promise.resolve(false);
    fittings.entries = fittings.entries.filter(function (e) { return e.id !== entryId; });
    fittings.entries.forEach(function (e) {
      if (e.superseded_by === entryId) e.superseded_by = null;
    });
    fitPushChanged('delete');
    return Promise.resolve(!!entry);
  };

  // Strict JSON and the sole fabricated-data source for both ?dev=1 and
  // the live-app screenshot tool. fittings.js accepts it only through its
  // bounded, CDP-invoked screenshot handler; ordinary production reads and
  // writes never consult it. Keep result rows in an order the dev copy loop
  // can really produce: first fit succeeds/turns Unknown/hits throttle, then
  // every pair for the second fit is unattempted.
  var DEV_FITTINGS_SCREENSHOT_FIXTURE = {
    "kind": "fittings-screenshot-v1",
    "copy_roles": {
      "unknown_character_id": 90000015,
      "throttle_character_id": 90000016
    },
    "characters": [
      {"character_id": 90000010, "character_name": "Aria Voss", "status": "enabled", "fetched_utc": "2026-09-03T10:00:00+00:00", "error": "", "stale": false},
      {"character_id": 90000011, "character_name": "Bex Talon", "status": "enabled", "fetched_utc": "2026-08-20T08:00:00+00:00", "error": "ESI request failed (500): Internal Server Error", "stale": true},
      {"character_id": 90000012, "character_name": "Cato Rune", "status": "enable", "fetched_utc": "", "error": "", "stale": false},
      {"character_id": 90000013, "character_name": "Dess Marlow", "status": "reauthenticate", "fetched_utc": "", "error": "", "stale": false},
      {"character_id": 90000014, "character_name": "Eryn Voss", "status": "enabled", "fetched_utc": "2026-09-03T10:00:00+00:00", "error": "", "stale": false},
      {"character_id": 90000015, "character_name": "Fio Kest", "status": "enabled", "fetched_utc": "2026-09-03T10:00:00+00:00", "error": "", "stale": false},
      {"character_id": 90000016, "character_name": "Gio Renn", "status": "enabled", "fetched_utc": "2026-09-03T10:00:00+00:00", "error": "", "stale": false}
    ],
    "collections": [
      {"id": "all", "name": "All fittings", "count": 27},
      {"id": "unfiled", "name": "Unfiled", "count": 25},
      {"id": "superseded", "name": "Superseded", "count": 1},
      {"id": "dev-alliance", "name": "Alliance", "count": 2},
      {"id": "dev-ratting", "name": "Ratting", "count": 0}
    ],
    "entries": [
      {"id": "fit-conflict-existing", "name": "Fleet Doctrine Alpha", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 1, "deployable": true, "updated_utc": "2026-08-15T00:00:00+00:00"},
      {"id": "fit-conflict-source", "name": "Fleet Doctrine Alpha", "ship_type_id": 587, "ship_name": "Rifter", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-02T00:00:00+00:00"},
      {"id": "fit-merlin-fleet", "name": "Merlin - Fleet Doctrine", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": ["dev-alliance"], "is_unfiled": false, "superseded_by": null, "presence_count": 1, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-merlin-old", "name": "Merlin - Old Doctrine", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": ["dev-alliance"], "is_unfiled": false, "superseded_by": "fit-merlin-fleet", "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-rifter-solo", "name": "Rifter - Solo PvP", "ship_type_id": 587, "ship_name": "Rifter", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 2, "deployable": true, "updated_utc": "2026-08-01T00:00:00+00:00"},
      {"id": "fit-gen-0", "name": "Generated Fit 001", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": false, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-1", "name": "Generated Fit 002", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-2", "name": "Generated Fit 003", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-3", "name": "Generated Fit 004", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-4", "name": "Generated Fit 005", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-5", "name": "Generated Fit 006", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-6", "name": "Generated Fit 007", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-7", "name": "Generated Fit 008", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-8", "name": "Generated Fit 009", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-9", "name": "Generated Fit 010", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-10", "name": "Generated Fit 011", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-11", "name": "Generated Fit 012", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-12", "name": "Generated Fit 013", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-13", "name": "Generated Fit 014", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-14", "name": "Generated Fit 015", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-15", "name": "Generated Fit 016", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-16", "name": "Generated Fit 017", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-17", "name": "Generated Fit 018", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-18", "name": "Generated Fit 019", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-19", "name": "Generated Fit 020", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-20", "name": "Generated Fit 021", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"},
      {"id": "fit-gen-21", "name": "Generated Fit 022", "ship_type_id": 603, "ship_name": "Merlin", "collection_ids": [], "is_unfiled": true, "superseded_by": null, "presence_count": 0, "deployable": true, "updated_utc": "2026-09-01T00:00:00+00:00"}
    ],
    "details": {
      "fit-rifter-solo": {
        "id": "fit-rifter-solo", "name": "Rifter - Solo PvP", "description": "Fast tackle, disengages on a scram.", "ship_type_id": 587, "ship_name": "Rifter", "deployable": true, "collection_ids": [], "superseded_by": null, "created_utc": "2026-08-01T00:00:00+00:00", "updated_utc": "2026-08-01T00:00:00+00:00",
        "items": [
          {"location": "high", "type_id": 2456, "type_name": "150mm Light AutoCannon II", "quantity": 3},
          {"location": "medium", "type_id": 3244, "type_name": "1MN Afterburner II", "quantity": 1},
          {"location": "low", "type_id": 519, "type_name": "Gyrostabilizer II", "quantity": 2}
        ],
        "aliases": [{"name": "Rifter - Solo PvP", "description": ""}, {"name": "Rifter Tackle Fit", "description": "imported alias"}],
        "presences": [
          {"character_id": 90000010, "character_name": "Aria Voss", "source_name": "Rifter - Solo PvP", "first_seen_utc": "2026-08-01T00:00:00+00:00", "last_confirmed_utc": "2026-09-03T10:00:00+00:00", "discovered_batch_id": "batch-1"},
          {"character_id": 90000011, "character_name": "Bex Talon", "source_name": "Rifter Tackle Fit", "first_seen_utc": "2026-08-05T00:00:00+00:00", "last_confirmed_utc": "2026-08-20T08:00:00+00:00", "discovered_batch_id": "batch-2"}
        ]
      },
      "fit-merlin-fleet": {
        "id": "fit-merlin-fleet", "name": "Merlin - Fleet Doctrine", "description": "Standard fleet doctrine fit.", "ship_type_id": 603, "ship_name": "Merlin", "deployable": true, "collection_ids": ["dev-alliance"], "superseded_by": null, "created_utc": "2026-09-01T00:00:00+00:00", "updated_utc": "2026-09-01T00:00:00+00:00",
        "items": [{"location": "high", "type_id": 2453, "type_name": "Light Neutron Blaster II", "quantity": 3}, {"location": "medium", "type_id": 12613, "type_name": "Medium Shield Extender II", "quantity": 2}, {"location": "low", "type_id": 519, "type_name": "Gyrostabilizer II", "quantity": 1}],
        "aliases": [{"name": "Merlin - Fleet Doctrine", "description": ""}],
        "presences": [{"character_id": 90000010, "character_name": "Aria Voss", "source_name": "Merlin - Old Doctrine", "first_seen_utc": "2026-09-01T00:00:00+00:00", "last_confirmed_utc": "2026-09-03T10:00:00+00:00", "discovered_batch_id": "batch-3"}]
      }
    },
    "mixed_preflight": {
      "accepted": true, "ticket_id": "screenshot-ticket", "created_utc": "2026-09-03T10:01:00+00:00", "write_count": 0,
      "counts": {"ready": 0, "present": 1, "conflict": 1, "unavailable": 1}, "requires_resolution": true, "error": "",
      "pairs": [
        {"entry_id": "fit-conflict-existing", "character_id": 90000014, "fitting_name": "Fleet Doctrine Alpha", "character_name": "Eryn Voss", "chosen_name": "Fleet Doctrine Alpha", "status": "present", "error": "", "skipped": false},
        {"entry_id": "fit-gen-0", "character_id": 90000014, "fitting_name": "Generated Fit 001", "character_name": "Eryn Voss", "chosen_name": "Generated Fit 001", "status": "unavailable", "error": "This fitting has no safe deployment template.", "skipped": false},
        {"entry_id": "fit-conflict-source", "character_id": 90000014, "fitting_name": "Fleet Doctrine Alpha", "character_name": "Eryn Voss", "chosen_name": "Fleet Doctrine Alpha", "status": "conflict", "error": "", "skipped": false}
      ]
    },
    "copy_result": {
      "status": "complete", "operation_id": "dev-operation-results", "write_count": 3,
      "results": [
        {"entry_id": "fit-gen-1", "character_id": 90000014, "fitting_name": "Generated Fit 002", "character_name": "Eryn Voss", "chosen_name": "Generated Fit 002", "status": "success", "remote_fitting_id": 9101, "error": "", "attempted": true},
        {"entry_id": "fit-gen-1", "character_id": 90000015, "fitting_name": "Generated Fit 002", "character_name": "Fio Kest", "chosen_name": "Generated Fit 002", "status": "unknown", "remote_fitting_id": null, "error": "No response was received before the request timed out.", "attempted": true},
        {"entry_id": "fit-gen-1", "character_id": 90000016, "fitting_name": "Generated Fit 002", "character_name": "Gio Renn", "chosen_name": "Generated Fit 002", "status": "failed", "remote_fitting_id": null, "error": "The fitting write rate limit was reached; the remaining batch was stopped.", "attempted": true},
        {"entry_id": "fit-gen-2", "character_id": 90000014, "fitting_name": "Generated Fit 003", "character_name": "Eryn Voss", "chosen_name": "Generated Fit 003", "status": "unattempted_throttle", "remote_fitting_id": null, "error": "Stopped after a fitting-bucket throttle response on an earlier pair.", "attempted": false},
        {"entry_id": "fit-gen-2", "character_id": 90000015, "fitting_name": "Generated Fit 003", "character_name": "Fio Kest", "chosen_name": "Generated Fit 003", "status": "unattempted_throttle", "remote_fitting_id": null, "error": "Stopped after a fitting-bucket throttle response on an earlier pair.", "attempted": false},
        {"entry_id": "fit-gen-2", "character_id": 90000016, "fitting_name": "Generated Fit 003", "character_name": "Gio Renn", "chosen_name": "Generated Fit 003", "status": "unattempted_throttle", "remote_fitting_id": null, "error": "Stopped after a fitting-bucket throttle response on an earlier pair.", "attempted": false}
      ]
    }
  };

  var fitCopyTickets = {};
  var fitCopyTicketIndex = 0;
  var fitCopyCancelled = false;
  // Set once a scripted throttle pair (see FIT_COPY_THROTTLE_CHARACTER
  // below) has fired, so every pair still queued behind it in the same
  // batch is also reported unattempted -- matching the design doc's "a
  // fitting-bucket 429 also stops the whole batch" policy, rather than
  // only the one pair that tripped it.
  var fitCopyThrottled = false;
  // Task 12 scenario characters: fixed IDs the harness scripts a specific
  // non-success outcome for, so a hand reviewer can reach Unknown and
  // throttle-stop without needing a real ESI failure. Both are otherwise
  // ordinary eligible copy targets (see the characters array above).
  var FIT_COPY_UNKNOWN_CHARACTER =
    DEV_FITTINGS_SCREENSHOT_FIXTURE.copy_roles.unknown_character_id; // Fio Kest
  var FIT_COPY_THROTTLE_CHARACTER =
    DEV_FITTINGS_SCREENSHOT_FIXTURE.copy_roles.throttle_character_id; // Gio Renn

  function devCopyPair(entry, character, names) {
    var base = {
      entry_id: entry.id, character_id: character.character_id,
      fitting_name: entry.name, character_name: character.character_name,
      chosen_name: entry.name, error: '', skipped: false
    };
    if (!entry.deployable || character.status !== 'enabled' || character.stale
        || !character.fetched_utc) {
      base.status = 'unavailable';
      base.error = !entry.deployable ? 'This fitting has no safe deployment template.'
                                     : 'Refresh or enable this character first.';
      return base;
    }
    if (entry.presences.some(function (p) {
      return p.character_id === character.character_id;
    })) {
      base.status = 'present';
      return base;
    }
    var conflict = fittings.entries.some(function (other) {
      return other.id !== entry.id && other.presences.some(function (p) {
        return p.character_id === character.character_id
          && p.source_name.toLowerCase() === entry.name.toLowerCase();
      });
    });
    if (!conflict) {
      base.status = 'ready';
      return base;
    }
    var key = entry.id + ':' + character.character_id;
    if (!(key in names)) {
      base.status = 'conflict';
      return base;
    }
    if (names[key] === null) {
      base.status = 'conflict';
      base.skipped = true;
      return base;
    }
    base.status = 'ready';
    base.chosen_name = names[key];
    return base;
  }

  api.fittings_preflight_copy = function (entryIds, characterIds, names) {
    console.log('DEV api.fittings_preflight_copy(', entryIds, characterIds, names, ')');
    names = names || {};
    var entries = fittings.entries.filter(function (entry) {
      return entryIds.indexOf(entry.id) !== -1;
    });
    var characters = fittings.characters.filter(function (character) {
      return characterIds.indexOf(character.character_id) !== -1;
    });
    var emptyCounts = { ready: 0, present: 0, conflict: 0, unavailable: 0 };
    if (!entries.length || !characters.length) {
      return Promise.resolve({
        accepted: false, ticket_id: '', created_utc: '', write_count: 0,
        counts: emptyCounts, requires_resolution: false, pairs: [],
        error: 'Select fittings and target characters first.'
      });
    }

    var usedNames = {};
    fittings.entries.forEach(function (entry) {
      entry.presences.forEach(function (presence) {
        usedNames[presence.character_id + ':' + presence.source_name.toLowerCase()] = true;
      });
    });
    var invalidChoices = {};
    var choiceError = '';
    Object.keys(names).forEach(function (key) {
      if (typeof names[key] !== 'string' || !names[key].trim()) return;
      var characterId = parseInt(key.slice(key.lastIndexOf(':') + 1), 10);
      var nameKey = characterId + ':' + names[key].trim().toLowerCase();
      if (usedNames[nameKey]) {
        invalidChoices[key] = true;
        if (!choiceError) choiceError = '\u201c' + names[key].trim()
          + '\u201d is already used on this character.';
      } else {
        usedNames[nameKey] = true;
      }
    });

    var pairs = [];
    entries.forEach(function (entry) {
      characters.forEach(function (character) {
        var pair = devCopyPair(entry, character, names);
        if (invalidChoices[pair.entry_id + ':' + pair.character_id]) {
          pair.status = 'conflict';
          pair.chosen_name = pair.fitting_name;
        }
        pairs.push(pair);
      });
    });
    var counts = { ready: 0, present: 0, conflict: 0, unavailable: 0 };
    pairs.forEach(function (pair) { counts[pair.status] += 1; });
    var overLimit = counts.ready > 20;
    var accepted = !choiceError && !overLimit;
    var requires = accepted && pairs.some(function (pair) {
      return pair.status === 'conflict' && !pair.skipped;
    });
    var ticketId = accepted ? 'dev-copy-' + (++fitCopyTicketIndex) : '';
    if (accepted) {
      fitCopyTickets[ticketId] = { pairs: pairs, write_count: counts.ready };
    }
    return Promise.resolve({
      accepted: accepted, ticket_id: ticketId,
      created_utc: accepted ? new Date().toISOString() : '',
      write_count: accepted ? counts.ready : 0,
      counts: counts, requires_resolution: requires, pairs: pairs,
      error: choiceError || (overLimit
        ? 'Split this copy into batches of 20 fittings or fewer.' : '')
    });
  };

  api.fittings_start_copy = function (ticketId) {
    console.log('DEV api.fittings_start_copy(', ticketId, ')');
    var ticket = fitCopyTickets[ticketId];
    if (!ticket) return Promise.resolve(false);
    delete fitCopyTickets[ticketId];
    fitCopyCancelled = false;
    fitCopyThrottled = false;
    var results = [];
    var index = 0;
    var operationId = 'dev-operation-' + fitCopyTicketIndex;
    function advance() {
      if (index >= ticket.pairs.length) {
        if (window.onFittingsProgress) {
          window.onFittingsProgress({
            kind: 'copy', phase: 'complete', operation_id: operationId,
            completed: results.length, total: ticket.pairs.length,
            result: {
              status: fitCopyCancelled ? 'cancelled' : 'complete',
              operation_id: operationId, results: results,
              write_count: results.filter(function (row) {
                return row.attempted;
              }).length
            }
          });
        }
        return;
      }
      var pair = ticket.pairs[index++];
      var result = {};
      Object.keys(pair).forEach(function (key) { result[key] = pair[key]; });
      result.attempted = false;
      if (pair.status === 'ready') {
        if (fitCopyThrottled) {
          // The batch already stopped at an earlier pair in this same
          // operation; everything still queued behind it is unattempted,
          // not retried and not silently dropped.
          result.status = 'unattempted_throttle';
        } else if (fitCopyCancelled) {
          result.status = 'cancelled';
        } else if (pair.character_id === FIT_COPY_UNKNOWN_CHARACTER) {
          result.attempted = true;
          // Ambiguous transport failure: an HTTP response was never
          // received, so the outcome is Unknown rather than Failed --
          // the design doc's "timeout, no response, 408, or 5xx is
          // Unknown unless ESI documents that the response guarantees
          // non-creation." This pair is not retried until an
          // authoritative refresh past the cache horizon reconciles it.
          result.status = 'unknown';
          result.error = 'No response was received before the request timed out.';
        } else if (pair.character_id === FIT_COPY_THROTTLE_CHARACTER) {
          // A fitting-bucket 429: this pair is itself unattempted, and it
          // also stops the remainder of the batch (see fitCopyThrottled
          // above), matching the design doc's conservative stop policy.
          result.status = 'failed';
          result.attempted = true;
          result.error = 'The fitting write rate limit was reached; the '
            + 'remaining batch was stopped.';
          fitCopyThrottled = true;
        } else {
          result.status = 'success';
          result.attempted = true;
          result.remote_fitting_id = 9100 + index;
        }
      } else if (pair.status === 'conflict' && pair.skipped) {
        result.status = 'conflict_skipped';
      }
      results.push(result);
      if (window.onFittingsProgress) {
        window.onFittingsProgress({
          kind: 'copy', phase: 'progress', operation_id: operationId,
          completed: results.length, total: ticket.pairs.length, result: result
        });
      }
      setTimeout(advance, 250);
    }
    setTimeout(advance, 250);
    return Promise.resolve(true);
  };

  api.fittings_cancel_copy = function () {
    console.log('DEV api.fittings_cancel_copy()');
    fitCopyCancelled = true;
    return Promise.resolve(true);
  };

  api.skills_character_detail = function (id, plan) {
    console.log('DEV api.skills_character_detail(', id, plan, ')');
    return Promise.resolve({
      ok: true, message: '', character_id: id, plan_name: plan,
      readiness: 'Missing', estimated_finish_utc: '',
      queue_timing_unknown: false,
      // Deliberately in PLAN order and deliberately interleaved: every
      // state the requirement list can render, shuffled, so the harness
      // shows sortByState() doing its job rather than agreeing with an
      // already-sorted fixture. The 'Active' row must vanish entirely --
      // requirementsNode filters met requirements out.
      requirements: [
        { skill_name: 'Energy Grid Upgrades', required_level: 4,
          active_level: 3, trained_level: 3, state: 'Queued',
          queued_finish_utc: '2026-08-27T04:00:00+00:00',
          queue_timing_unknown: false },
        { skill_name: 'Gallente Cruiser', required_level: 5,
          active_level: 0, trained_level: 0, state: 'Unknown',
          queued_finish_utc: '', queue_timing_unknown: false },
        { skill_name: 'Amarr Cruiser', required_level: 5, active_level: 4,
          trained_level: 4, state: 'Missing', queued_finish_utc: '',
          queue_timing_unknown: false },
        { skill_name: 'Spaceship Command', required_level: 3,
          active_level: 5, trained_level: 5, state: 'Active',
          queued_finish_utc: '', queue_timing_unknown: false },
        { skill_name: 'Heavy Assault Cruisers', required_level: 1,
          active_level: 0, trained_level: 1, state: 'TrainedInactive',
          queued_finish_utc: '', queue_timing_unknown: false },
        { skill_name: 'Heavy Assault Missile Specialization',
          required_level: 4, active_level: 0, trained_level: 0,
          state: 'Unknown', queued_finish_utc: '',
          queue_timing_unknown: false }
      ]
    });
  };

  // One character per readiness group, plus a deliberately unrecognised
  // one so the roster's catch-all bucket is visible in the browser. The
  // Unscored row is the common case, not padding: every character is
  // Unscored between authorisation and its first refresh.
  //
  // Task 6 adds every sort/status edge byTrainingFinishThenName and
  // byTrainingRemainingThenName exist to handle, on top of the original
  // nine: a third Training row so the two dated ones are out of name
  // order (Zuelo finishes before Bel despite sorting after it
  // alphabetically); a Missing tie (Zara/Aveline Castellane, inserted in
  // that order so array order alone cannot stand in for the name
  // tie-break); a Missing row with an unavailable estimate
  // (Petra Ilyenko); and a Missing row carrying both `queued_count` and
  // `missing_count` above zero with a long character name and the
  // longest skill name EVE has (.skills-main's own CSS comment measures
  // it). Every character below now carries all three of Task 5's
  // estimate fields, matching what a real payload always sends once a
  // plan is selected.
  var skills = {
    refresh_in_flight: false,
    selected_plan_name: 'Ishtar',
    selected_group: '',
    // Left EMPTY on purpose and filled by devRecountGroups() at startup
    // (below). Typing the counts here beside the per-character `group`
    // fields would be two sources for one derived fact, and a fake payload
    // that contradicts itself makes the harness lie about exactly what
    // Tasks 8-9 use it to check. Python derives this list too
    // (controller._groups_locked).
    groups: [],
    plans: [
      { name: 'Ishtar', requirement_count: 14, ready_count: 1 },
      { name: 'Loki', requirement_count: 22, ready_count: 0 }
    ],
    characters: [
      { character_id: 1, character_name: 'Aiga Otsolen',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Ready',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 14, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0, group: 'Wolfpack',
        // Ready: every plan skill is already trained and active, so
        // there is nothing left to train.
        training_remaining_seconds: 0, training_remaining_label: '0m',
        training_estimate_status: 'available' },
      { character_id: 2, character_name: 'Zuelo Parvi',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Training',
        // Earlier than Bel Ansgar (character_id 10) below despite sorting
        // AFTER it alphabetically -- byTrainingFinishThenName must put
        // Zuelo first, which a name sort would get backwards.
        estimated_finish_utc: '2026-08-25T09:00:00+00:00',
        queue_timing_unknown: false,
        active_count: 12, trained_inactive_count: 0, queued_count: 2,
        missing_count: 0, unknown_count: 0, group: 'Wolfpack',
        training_remaining_seconds: 45000,
        training_remaining_label: '12h 30m', training_estimate_status: 'available' },
      { character_id: 3, character_name: 'Kaska Rin',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Training',
        estimated_finish_utc: '', queue_timing_unknown: true,
        active_count: 13, trained_inactive_count: 0, queued_count: 1,
        missing_count: 0, unknown_count: 0, group: 'Wolfpack',
        // A timing-unknown queue does not stop the SEPARATE plan-wide
        // estimate from being available -- the two are different
        // computations (EVE's queue fact vs training.estimate()).
        training_remaining_seconds: 93600,
        training_remaining_label: '1d 2h', training_estimate_status: 'available' },
      { character_id: 4, character_name: 'Delen Vok',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Locked',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 11, trained_inactive_count: 3, queued_count: 0,
        missing_count: 0, unknown_count: 0, group: 'Logi Wing',
        // Locked is an inactive-clone problem, not a training one: the
        // trained_inactive skills are already paid for.
        training_remaining_seconds: 0, training_remaining_label: '0m',
        training_estimate_status: 'available' },
      { character_id: 5, character_name: 'Gustav Oswaldo',
        fetched_utc: '2026-08-23T20:00:00+00:00',
        fetched_label: 'Last fetched 17h ago',
        error: 'ESI returned 503', needs_reauth: false, stale: true,
        readiness: 'Missing', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 8, trained_inactive_count: 0, queued_count: 0,
        missing_count: 6, unknown_count: 0, group: '',
        // Round 6: three names and a stated remainder, the capped case
        // (controller._ROSTER_NAME_CAP).
        missing_names: ['Heavy Assault Cruisers V',
                        'Tactical Shield Manipulation V',
                        'Gunnery V'],
        // Task 6: stale carries a REAL training estimate, same as a fresh
        // row -- the last successful refresh is what it is scored
        // against, and the multi-week case (the largest duration in the
        // fixture, so it sorts last among available estimates).
        training_remaining_seconds: 1296000,
        training_remaining_label: '15d 0h', training_estimate_status: 'available' },
      { character_id: 6, character_name: 'Nera Tal',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Missing',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 12, trained_inactive_count: 0, queued_count: 0,
        missing_count: 2, unknown_count: 0, group: 'Wolfpack',
        // Under the cap, so no remainder clause.
        missing_names: ['Motion Prediction V', 'Sharpshooter IV'],
        // The short case -- smallest duration in the fixture, so it sorts
        // first among available estimates.
        training_remaining_seconds: 5400,
        training_remaining_label: '1h 30m', training_estimate_status: 'available' },
      { character_id: 7, character_name: 'Orin Kesh',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Unknown',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 13, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 1, group: 'Logi Wing',
        // A skill this build has never resolved an id for -- the
        // metadata_unavailable case.
        training_remaining_seconds: null, training_remaining_label: '',
        training_estimate_status: 'metadata_unavailable' },
      { character_id: 8, character_name: 'Tavi Solen', fetched_utc: '',
        fetched_label: 'Never fetched',
        error: 'The refresh token was rejected', needs_reauth: true,
        stale: false, readiness: 'Unscored', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 0, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0, group: '',
        // No snapshot at all -- skill_points_complete is never true, so
        // this is the refresh_required case, not the empty ("no plan")
        // status: a plan IS selected here, and Unscored is the only
        // readiness this status can pair with.
        training_remaining_seconds: null, training_remaining_label: '',
        training_estimate_status: 'refresh_required' },
      { character_id: 9, character_name: 'Mira Halcyon', fetched_utc: '',
        fetched_label: 'Never fetched',
        error: '', needs_reauth: false, stale: false,
        readiness: 'Ascendant', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 0, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0, group: '',
        training_remaining_seconds: null, training_remaining_label: '',
        training_estimate_status: 'refresh_required' },
      { character_id: 10, character_name: 'Bel Ansgar',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Training',
        // Later than Zuelo Parvi (character_id 2) above -- the two dated
        // Training rows are deliberately out of name order.
        estimated_finish_utc: '2026-08-27T21:00:00+00:00',
        queue_timing_unknown: false,
        active_count: 10, trained_inactive_count: 0, queued_count: 3,
        missing_count: 0, unknown_count: 0, group: '',
        training_remaining_seconds: 100800,
        training_remaining_label: '1d 4h', training_estimate_status: 'available' },
      // The tie-break pair. Inserted Zara-then-Aveline -- alphabetically
      // backwards -- so a fixture whose array order already matched the
      // name order could not make byTrainingRemainingThenName's tie-break
      // pass by accident.
      { character_id: 11, character_name: 'Zara Castellane',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Missing',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 9, trained_inactive_count: 0, queued_count: 0,
        missing_count: 3, unknown_count: 0, group: '',
        missing_names: ['Advanced Spaceship Command III',
                        'Target Painting IV'],
        training_remaining_seconds: 172800,
        training_remaining_label: '2d 0h', training_estimate_status: 'available' },
      { character_id: 12, character_name: 'Aveline Castellane',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Missing',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 10, trained_inactive_count: 0, queued_count: 0,
        missing_count: 2, unknown_count: 0, group: '',
        missing_names: ['Signature Focusing V'],
        training_remaining_seconds: 172800,
        training_remaining_label: '2d 0h', training_estimate_status: 'available' },
      { character_id: 13, character_name: 'Petra Ilyenko',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Missing',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 7, trained_inactive_count: 0, queued_count: 0,
        missing_count: 4, unknown_count: 0, group: '',
        missing_names: ['Cynosural Field Theory V', 'Titan Synergy V'],
        // Confirmed but unusable attributes (attributes_fetched_utc set,
        // attributes_error non-empty) -- the unavailable case, which must
        // sort last regardless of missing_count.
        training_remaining_seconds: null, training_remaining_label: '',
        training_estimate_status: 'attributes_unavailable' },
      { character_id: 14,
        // Long enough to exercise .skills-main's 240px --name-col ellipsis.
        character_name: 'Konstantina Alexandrovna Winterbourne',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Missing',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 11, trained_inactive_count: 0,
        // Both above zero: some of this plan is already queued while the
        // rest is entirely untrained, which is what makes the overall
        // readiness Missing even though training has started.
        queued_count: 2, missing_count: 3, unknown_count: 0, group: '',
        // The exact skill .skills-main's own CSS comment measures as the
        // longest name EVE has (39 characters).
        missing_names: ['Heavy Assault Missile Specialization V'],
        training_remaining_seconds: 604800,
        training_remaining_label: '7d 0h', training_estimate_status: 'available' }
    ],
    plan_issues: [
      { file_name: 'Broken.txt', message: 'The file was rejected.',
        diagnostics: [{ line: 4, message: 'Missing a level' },
                      { line: 0, message: 'No requirements were parsed' }] }
    ],
    warnings: [],
    plans_updated_utc: '2026-08-24T08:00:00+00:00'
  };

  devRecountGroups();   // Fills skills.groups from the roster above.

  api.pick_folder = function (which) {
    console.log('DEV api.pick_folder(', which, ')');
    return Promise.resolve('D:\\Videos\\' + which);
  };

  // Mirrors Api.panel_text: the page asks Python for both strings rather
  // than reimplementing format_selection_summary / format_title_hint here.
  api.panel_text = function (ids, stitch) {
    console.log('DEV api.panel_text(', ids, stitch, ')');
    var hint = ids.length <= 1 ? 'Title'
      : stitch ? 'Title (one stitched video)'
      : 'Title (applies to all ' + ids.length + ', numbered 1-'
        + ids.length + ')';
    return Promise.resolve({
      summary: ids.length
        ? ids.length + ' selected \u00b7 1.4 GB \u00b7 12:31'
        : 'Nothing selected',
      title_hint: hint
    });
  };

  api.auth_labels = function () {
    return Promise.resolve({
      disconnected: { message: 'Not connected', label: 'Sign in with Google', enabled: true },
      connecting: { message: 'Waiting for browser\u2026', label: 'Connecting\u2026', enabled: false },
      connected: { message: 'Connected', label: 'Switch account', enabled: true },
      revoking: { message: 'Signing out\u2026', label: 'Signing out\u2026', enabled: false }
    });
  };

  // The settings payload Python returns from get_settings(). Kept here so
  // the stub and the manual DEV.settings() driver share one shape.
  function settingsPayload(patch, statusLine) {
    return {
      settings: Object.assign(
        { privacy: 'unlisted', category: '20', notify_mode: 'toast',
          recording_dir: 'D:\\Videos',
          gamelogs_dir: 'C:\\Users\\tng\\Documents\\EVE\\logs\\Gamelogs',
          discord_webhook: 'https://discord.com/api/webhooks/1/tok',
          channel_id: 'UC123', channel_title: 'FlyGD',
          // Was entirely absent before the Alerts card: _settings_payload
          // ships preview.alerts for free (a shallow dict(cfg)), so this
          // is what makes the card eyeballable under ?dev=1 at all.
          preview: { enabled: true, restore_preview_positions: true,
            show_labels: true, opacity: 255, snap: true, lock_aspect: true,
            selection_color: '#ff5a00',
            // The global default size. Present because the real payload
            // always carries it -- get_settings ships `dict(cfg)` whole --
            // and without it the Default preview size field renders EMPTY
            // under ?dev=1, which is indistinguishable from a field whose
            // listener never ran. Deliberately not 320x210: a fixture that
            // matches the shipped default cannot show that the field is
            // reading the payload rather than a hardcoded fallback.
            width: 480, height: 300,
            // Off, matching the shipped default, so the harness shows the
            // per-character Lock boxes in their ordinary sense (ticked
            // means locked) rather than as exceptions.
            lock_default: false,
            // Task 10: read here by settings.js's own wm:settings listener
            // AND by previews.js's. ON so the harness renders the
            // Never-minimize disclosure at all -- D6 makes the whole block
            // absent while this is off, so the shipped-default value would
            // leave half the exception UI unreachable in the harness.
            minimize_inactive_clients: true,
            // TRUE, against a shipped default of false: the harness is
            // where the checkbox is eyeballed, and a fixture matching the
            // default cannot show that settings.js reads the payload
            // rather than leaving the box at its markup state.
            hide_on_lost_focus: true,
            alerts: { enabled: true, pve_filter: true,
              persist_until_selected: true,
              // 70, against a shipped default of 100, for the same reason
              // hide_on_lost_focus is true above: a fixture matching the
              // default cannot show that the slider reads the payload
              // rather than sitting where the markup left it.
              volume: 70,
              events: {
                combat: { enabled: true, cooldown_s: 1, flash_rate: 'fast',
                  pulses: 3, color: '#ff4d4d', sound: 'system-fault' },
                warp_scramble: { enabled: true, cooldown_s: 8,
                  flash_rate: 'normal', pulses: 3, color: '#ffd24d',
                  sound: 'obey' },
                decloak: { enabled: true, cooldown_s: 8, flash_rate: 'slow',
                  pulses: 5, color: '#4dd2ff', sound: 'sly' }
              }
            }
          },
          // The floating sig bar's section, present because the real
          // payload ships `dict(cfg)` whole. ON against a shipped default
          // of off, for the same reason hide_on_lost_focus is: the
          // harness is where the card's controls are eyeballed, and a
          // default-valued fixture cannot show they read the payload.
          sig_bar: { enabled: true, x: null, y: null },
          // Separate from previews.enabled on purpose: the approved runtime
          // contract allows this bar to stay live with previews off.
          fleet_bar: fleetBarState()
        }, patch || {}),
      // discord.describe()'s shape for the fake webhook stored above, not
      // a prose invention: it is host/api/webhooks/<id>… by construction,
      // and settings.js reads that shape to tell a description apart from
      // a parse error before naming the webhook in the Remove confirm. A
      // fixture in a different shape made that branch untestable by hand
      // -- the dialog said "this webhook" in the harness and named it in
      // the app. tests/test_settings_page.py holds the two in step.
      webhook_status: statusLine === undefined
        ? 'discord.com/api/webhooks/1…' : statusLine,
      detected: { recording: 'D:\\Videos',
                  gamelogs: 'C:\\Users\\tng\\Documents\\EVE\\logs\\Gamelogs' },
      destination: 'Uploads go to FlyGD \u00b7 unlisted',
      // S3's INERT_NOTES, shipped on every settings payload. The panel
      // reads no_webhook from here (Uploader 8: the sentence outlived the
      // checkbox), and Settings reads previews_off. Doubled with the real
      // strings rather than placeholders, because what these have to prove
      // is that the sentence FITS -- the Uploader's panel overflows its
      // pane at the window floor and this is three lines of it.
      inert_notes: {
        previews_off: 'Previews are off, so every keybind below is '
          + 'unregistered until you turn them back on.',
        no_webhook: 'No Discord webhook is configured, so combat logs are '
          + 'not posted. Set one in Settings \u203a Discord.'
      },
      // Python sends this from __version__; the double carries a value
      // of the same SHAPE and not the real one, so a stale fake cannot
      // be mistaken for the app agreeing with itself.
      version: '0.0.0-dev',
      // Read live from the registry by autostart.is_enabled(). Default is
      // opt-in, so an install that was never asked reads false -- which is
      // what this shows.
      start_on_login: false
    };
  }

  // Exact copy of Api._update_snapshot_locked's permission policy for a
  // cached release in a frozen build. Keeping every state here makes fixture
  // drift visible instead of letting base defaults silently grant an action.
  var DEV_UPDATE_PERMISSIONS = JSON.parse('{"idle":{"can_check":true,"can_download":false,"can_install":false},"checking":{"can_check":false,"can_download":false,"can_install":false},"current":{"can_check":true,"can_download":false,"can_install":false},"unavailable":{"can_check":true,"can_download":false,"can_install":false},"available":{"can_check":true,"can_download":true,"can_install":false},"check_failed":{"can_check":true,"can_download":true,"can_install":false},"download_failed":{"can_check":true,"can_download":true,"can_install":false},"downloading":{"can_check":false,"can_download":false,"can_install":false},"ready":{"can_check":false,"can_download":false,"can_install":true},"handing_off":{"can_check":false,"can_download":false,"can_install":false},"revalidating":{"can_check":false,"can_download":false,"can_install":false},"launching":{"can_check":false,"can_download":false,"can_install":false},"closed":{"can_check":false,"can_download":false,"can_install":false}}');

  function devUpdateState() {
    // ?dev=1&update=<state> selects which of the card's states renders,
    // so every state Task 7's smoke checklist calls for is reachable by
    // hand without touching Python: current, checking, an automatic
    // offline failure, available, downloading (with real bytes for the
    // progress bar), ready (declared frozen so Install actually shows,
    // which a real source checkout never is), and a manual failure.
    var match = /[?&]update=([\w-]+)/.exec(window.location.search);
    var state = match ? match[1] : 'available';
    var base = {
      installed_version: '0.0.0-dev',
      available_version: '4.9.0',
      downloaded_bytes: 0,
      total_bytes: 42000000,
      error: ''
    };
    var payload;
    // update_available mirrors Api._update_snapshot_locked: true whenever
    // a release is cached, which survives through check_failed/ready/
    // download_failed rather than flickering off the moment a later
    // action fails -- app.js's gear badge reads exactly this field.
    switch (state) {
      case 'idle':
        payload = Object.assign({}, base, {
          state: 'idle', available_version: '', update_available: false
        });
        break;
      case 'checking':
        payload = Object.assign({}, base, {
          state: 'checking', available_version: '', update_available: false
        });
        break;
      case 'current':
        payload = Object.assign({}, base, {
          state: 'current', available_version: '', update_available: false
        });
        break;
      case 'unavailable':
        payload = Object.assign({}, base, {
          state: 'unavailable', available_version: '', update_available: false
        });
        break;
      case 'downloading':
        payload = Object.assign({}, base, {
          state: 'downloading', downloaded_bytes: 18000000,
          update_available: true
        });
        break;
      case 'ready':
        payload = Object.assign({}, base, {
          state: 'ready', downloaded_bytes: 42000000, update_available: true
        });
        break;
      case 'error':
        payload = Object.assign({}, base, {
          state: 'download_failed', update_available: true,
          error: 'The download did not match what the release published. '
               + 'Try downloading again.'
        });
        break;
      default:
        payload = Object.assign({}, base, {
          state: 'available', update_available: true
        });
    }
    return Object.assign(payload, DEV_UPDATE_PERMISSIONS[payload.state]);
  }

  // The bar page pulls its section once at load; so does bookmarks.js
  // for the toggle's initial paint. Returns the same object the payload
  // above carries, so the two doubles cannot disagree.
  api.sig_bar_settings = function () {
    console.log('DEV api.sig_bar_settings()');
    return Promise.resolve(settingsPayload().settings.sig_bar);
  };

  api.fleet_bar_settings = function () {
    console.log('DEV api.fleet_bar_settings()');
    return Promise.resolve(fleetBarState());
  };

  api.toggle_fleet_bar = function (enabled) {
    console.log('DEV api.toggle_fleet_bar(', enabled, ')');
    if (fleetBar.enabled !== !!enabled) {
      fleetBar.enabled = !!enabled;
      fleetBar.revision += 1;
    }
    if (window.onFleetBarState) { window.onFleetBarState(fleetBarState()); }
    return Promise.resolve({applied: true, persisted: true, error: null});
  };

  api.set_fleet_bar_character_visible = function (name, visible) {
    var index = fleetBar.seen.indexOf(name);
    var hiddenIndex = fleetBar.hidden.indexOf(name);
    var state;
    console.log('DEV api.set_fleet_bar_character_visible(', name, visible, ')');
    if (index === -1 || typeof visible !== 'boolean') {
      return Promise.resolve({
        applied: false,
        persisted: false,
        error: 'Choose a character from the Fleet list.',
        state: fleetBarState()
      });
    }
    if (!visible && hiddenIndex === -1 && fleetBar.hidden.length >= 64) {
      return Promise.resolve({
        applied: false,
        persisted: false,
        error: 'Show a hidden character before hiding another.',
        state: fleetBarState()
      });
    }
    if (visible && hiddenIndex !== -1) {
      fleetBar.hidden.splice(hiddenIndex, 1);
      fleetBar.revision += 1;
    } else if (!visible && hiddenIndex === -1) {
      fleetBar.hidden.push(name);
      fleetBar.revision += 1;
    }
    state = fleetBarState();
    if (window.onFleetBarState) { window.onFleetBarState(state); }
    return Promise.resolve({applied: true, persisted: true, error: null, state: state});
  };

  // A RETURN, not a push, because that is what the bridge does. The first
  // version of this file pushed onSettings from the list_rows stub, which
  // modelled a push the real bridge never emitted — so the page looked
  // correct under ?dev=1 and was wrong under Python. A double that is more
  // complete than the thing it doubles hides exactly the bug it should
  // have caught.
  api.get_settings = function () {
    console.log('DEV api.get_settings()');
    return Promise.resolve(settingsPayload());
  };

  api.update_status = function () {
    return Promise.resolve(devUpdateState());
  };

  api.check_for_updates = function () {
    return Promise.resolve(devUpdateState());
  };

  api.download_update = function () {
    console.log('DEV api.download_update()');
    return Promise.resolve(devUpdateState());
  };

  api.install_update = function () {
    console.log('DEV api.install_update()');
    return Promise.resolve(devUpdateState());
  };

  // ---- FightRecorder: the harness has no OBS and no network, so the
  // stub reports a plausible installed-and-current state. Check for
  // updates returns up_to_date=true so the card exercises its "nothing
  // to do" paint, which is the state most users will sit in.
  api.fightrecorder_status = function (check) {
    console.log('DEV api.fightrecorder_status(', check, ')');
    return Promise.resolve({
      installed: true,
      path: 'C:\\Program Files\\obs-studio\\obs-plugins\\64bit\\'
            + 'obs-fightrecorder.dll',
      detected: true,
      up_to_date: check === true ? true : null,
      latest_tag: check === true ? 'v1.1.2' : '',
      error: ''
    });
  };

  api.update_fightrecorder = function () {
    console.log('DEV api.update_fightrecorder()');
    return Promise.resolve({ok: true, error: '', tag: 'v1.1.2'});
  };

  // ---- Bookmarks and Previews, the two sections the harness could not
  // reach at all. Both call a real Api method that had no stub here, so
  // WM.send rejected to the console and the page rendered whatever it
  // could without the data.
  //
  // The Previews one was merely loud: `bridge: no such method:
  // get_preview_hotkey_state` in the console, three times a load, on every
  // lane's verification run for two rounds.
  //
  // The Bookmarks one was the dangerous kind and is why these are being
  // added now. #eve-binds is filled entirely from get_bookmarks, so the
  // section rendered three cards, their headings, their prose and a Reset
  // button with ZERO keybind rows -- a screen that looks finished and is
  // missing its whole subject. That is the failure the top of DESIGN.md
  // opens with, sitting inside the harness five sessions verified through;
  // the lane that reshaped those eighteen rows had to synthesise them by
  // hand to see its own work.
  //
  // The ids are NOT hand-kept: tests/test_dev_harness.py asserts this
  // list against bookmarks.BIND_IDS. Four places once carried a count of
  // these binds and three of them were wrong, so a fixture that quietly
  // drifted to seventeen would put the harness back to lying, just less
  // obviously than an empty list does.
  var bookmarkBinds = [
    'GrabSig', 'SetRoot', 'FormatEnf', 'ConvertScout',
    'FinH', 'FinL', 'FinN', 'Fin13',
    'Fin1', 'Fin2', 'Fin3', 'Fin4', 'Fin5', 'Fin6',
    'FinETag', 'FinSlash', 'FinS', 'FinC'
  ];

  // Labels come from bookmarks.BIND_LABELS in the real payload; the same
  // test asserts these against it, for the same reason.
  var bookmarkLabels = {
    GrabSig: 'Grab Sig ID', SetRoot: 'Set Root',
    FormatEnf: 'Format Enforcer',
    ConvertScout: 'Convert EvE-Scout Bookmarks',
    FinH: 'Finisher: HS (highsec)', FinL: 'Finisher: LS (lowsec)',
    FinN: 'Finisher: NS (nullsec)', Fin13: 'Finisher: C13 (shattered)',
    Fin1: 'Finisher: C1', Fin2: 'Finisher: C2', Fin3: 'Finisher: C3',
    Fin4: 'Finisher: C4', Fin5: 'Finisher: C5', Fin6: 'Finisher: C6',
    FinETag: 'e Tag (end of life)', FinSlash: '/ Tag (half mass)',
    FinS: 'f Tag (frig hole)', FinC: 'c Tag (critical)'
  };

  // The groups Api.get_bookmarks derives from BIND_LABELS via
  // bookmarks.bind_groups(). A literal here for the same reason the two
  // fixtures above are literals -- dev.js must not re-implement a rule it
  // is meant to be a fixture for -- and asserted against the real
  // derivation by tests/test_dev_harness.py, so it cannot drift.
  var bookmarkGroups = [
    { name: '', ids: ['GrabSig', 'SetRoot', 'FormatEnf', 'ConvertScout'],
      short: { GrabSig: 'Grab Sig ID', SetRoot: 'Set Root',
               FormatEnf: 'Format Enforcer',
               ConvertScout: 'Convert EvE-Scout Bookmarks' } },
    { name: 'Finishers',
      ids: ['FinH', 'FinL', 'FinN', 'Fin13',
            'Fin1', 'Fin2', 'Fin3', 'Fin4', 'Fin5', 'Fin6'],
      short: { FinH: 'HS (highsec)', FinL: 'LS (lowsec)',
               FinN: 'NS (nullsec)', Fin13: 'C13 (shattered)',
               Fin1: 'C1', Fin2: 'C2', Fin3: 'C3',
               Fin4: 'C4', Fin5: 'C5', Fin6: 'C6' } },
    { name: 'Tags', ids: ['FinETag', 'FinSlash', 'FinS', 'FinC'],
      short: { FinETag: 'e (end of life)', FinSlash: '/ (half mass)',
               FinS: 'f (frig hole)', FinC: 'c (critical)' } }
  ];

  api.get_bookmarks = function () {
    console.log('DEV api.get_bookmarks()');
    var keybinds = {};
    bookmarkBinds.forEach(function (id) { keybinds[id] = ''; });
    // A spread of states rather than DEFAULT_BINDS' one bound key: an
    // all-blank fixture cannot show what a bound row, a collision or a
    // shared chord look like, and those are the rows the layout work is
    // about. ConvertScout keeps its real default.
    keybinds.ConvertScout = '^+s';
    keybinds.SetRoot = '^+r';
    keybinds.GrabSig = '^+g';
    // Deliberately the same chord twice, so `collisions` below is not an
    // empty list nobody has seen rendered.
    keybinds.Fin1 = '^+1';
    keybinds.Fin2 = '^+1';
    // C6: the same chord a preview character is bound to in the Previews
    // fixture below, so the harness renders the "a Previews keybind takes
    // this one" mark rather than leaving that branch unseen. FormatEnf is
    // in the leading flat group, so the mark is visible without opening a
    // dense block.
    keybinds.FormatEnf = '^!1';
    return Promise.resolve({
      // settings is the `eve_bookmarks` section verbatim:
      // {enabled, keybinds, windows}. `windows` is a per-title enabled
      // MAP, not a list -- the list of titles is the top-level `windows`
      // below, from evewindows.list_eve_windows(). One of the two is left
      // off, because a state where every window is ticked is the one that
      // needs the least looking at.
      settings: {
        enabled: true,
        keybinds: keybinds,
        windows: { 'EVE - Aiga Otsolen': true, 'EVE - Zuelo Parvi': false }
      },
      labels: bookmarkLabels,
      order: bookmarkBinds,
      groups: bookmarkGroups,
      // C6's counterpart of `bookmark_chords` on the Previews payload
      // below, and deliberately the SAME chord: 'Ctrl+Alt+1' is bound to a
      // character there, so the harness shows the collision on both
      // screens at once rather than only on the one whose lane happened to
      // be looking.
      //
      // ACTIVE, because that is what Api._preview_chords would return for
      // the fixture below: it ships `enabled: true` with 'Ctrl+Alt+1' in
      // its `registration` map as `true`, so Windows is holding the chord
      // and the bookmark bind genuinely cannot fire. The first draft said
      // latent under a comment claiming previews shipped off, which was
      // simply wrong about the fixture two hundred lines down -- and a
      // harness whose payload contradicts its own neighbouring payload is
      // the failure this file's tests exist to prevent, just spread across
      // two calls where no test could see it.
      //
      // The dim/latent branch is therefore NOT covered here. It was
      // verified in the real window instead, by binding Ctrl+Alt+F9 on
      // both sides with previews off.
      preview_chords: { active: ['Ctrl+Alt+1'], latent: [] },
      windows: ['EVE - Aiga Otsolen', 'EVE - Zuelo Parvi'],
      // Keyed by the parsed AHK string, valued with every bind id claiming
      // it -- bookmarks.collisions() only returns entries of length > 1.
      collisions: { '^+1': ['Fin1', 'Fin2'] },
      displays: {
        ConvertScout: 'Ctrl+Shift+S', SetRoot: 'Ctrl+Shift+R',
        GrabSig: 'Ctrl+Shift+G', Fin1: 'Ctrl+Shift+1',
        Fin2: 'Ctrl+Shift+1', FormatEnf: 'Ctrl+Alt+1'
      },
      engine: { state: 'on', last_error: null, blockers: [] }
    });
  };

  api.set_bind_capture = function (armed) {
    console.log('DEV api.set_bind_capture(' + armed + ')');
    // False, not true: in a plain browser there is no preview host and so
    // no chord redirection, and the harness must not imply otherwise. The
    // page does not branch on the value -- it waits for the call, then
    // arms the row -- so capture here still works through the ordinary
    // keydown path, which is the only path a browser has.
    return Promise.resolve(false);
  };

  // DEV_PREVIEW_HOTKEYS_FIXTURE is the single authoritative source for the
  // preview hotkey state in ?dev=1 mode.  Strict JSON-compatible text: all keys
  // and strings double-quoted, no functions or comments inside the literal body,
  // so shoot_screens.py can parse it directly with json.loads.
  //
  // Both get_preview_hotkey_state and _devPreviewHotkeys derive deep copies
  // from this one declaration -- the fixture data can never drift between the
  // initial page load and subsequent mutation pushes.
  //
  // Character assignments:
  //   Zuelo Parvi and Corvin Veles -- online, share a supported direct bind.
  //   Aiga Otsolen      -- online, NOT excluded, assigned to DPS.
  //   Tanuki Solette    -- offline, assigned to Logistics and conflicts with
  //                        All forward, so the local conflict copy renders.
  //   Aleksandrina ...  -- offline, assigned to DPS and Copy-enabled.
  //   Mara Veld         -- offline, assigned to DPS.
  //   Sera Vahn         -- offline, assigned to Logistics, excluded (opted-out
  //                        AND assigned -- the combination the page must handle).
  //
  // Groups:
  //   DPS      (g-dps)    -- members Aiga + Aleksandrina + Mara,
  //                          cycle Ctrl+Shift+1.
  //   Logistics (g-logi)  -- members Tanuki + Sera, cycle Ctrl+Shift+1
  //                          (deliberate collision with DPS so the collision
  //                          branch renders).
  //   Empty group (g-empty) -- zero members, no bind (zero-member UI path).
  //
  // excluded[]: Sera only, while still assigned to Logistics. Zuelo is All-only
  // (non-excluded, unassigned), a different and independently-exercised state.
  //
  // Gesture strings use preview/gestures.py display() canonical form
  // ("Ctrl+Alt+Right"), NOT AHK ("^!Right"). Verified by from_capture().
  //
  // lock_default: false -- must match the settings fixture checkbox; the bool is
  // always sent by Api.get_preview_hotkey_state, so omitting and relying on
  // JS coercion would let the table disagree with the control that governs it.
  //
  // bookmark_chords.active: ["Ctrl+Alt+1"] -- matches the get_bookmarks fixture
  // (enabled: true, 'EVE - Aiga Otsolen' ticked), which makes that chord
  // registered.  Must stay in step with the bookmarks fixture.
  //
  // 'Aleksandrina Shadowbanes Voidstriders' (37 chars) is load-bearing: the
  // only row that exercises ellipsis in the bounded name track and the title
  // attribute fallback at the 840px viewport floor.
  var DEV_PREVIEW_HOTKEYS_FIXTURE = {
    "enabled": true,
    "hotkeys": {
      "characters": {
        "Aiga Otsolen": "Ctrl+Alt+1",
        "Zuelo Parvi": "Ctrl+Alt+2",
        "Corvin Veles": "Ctrl+Alt+2",
        "Tanuki Solette": "Ctrl+Alt+Right",
        "Mara Veld": "Ctrl+Shift+2",
        "Niko Avar": "Ctrl+Shift+3"
      },
      "cycle_next": "Ctrl+Alt+Right",
      "cycle_prev": "",
      "groups": [
        {"id": "g-dps",   "name": "DPS",         "cycle": "Ctrl+Shift+1"},
        {"id": "g-logi",  "name": "Logistics",    "cycle": "Ctrl+Shift+1"},
        {"id": "g-empty", "name": "Empty group",  "cycle": ""}
      ],
      "group_by_character": {
        "Aiga Otsolen": "g-dps",
        "Tanuki Solette": "g-logi",
        "Aleksandrina Shadowbanes Voidstriders": "g-dps",
        "Mara Veld": "g-dps",
        "Sera Vahn": "g-logi"
      }
    },
    "characters": ["Aiga Otsolen", "Zuelo Parvi", "Corvin Veles"],
    "roster": [
      "Aiga Otsolen", "Zuelo Parvi", "Corvin Veles", "Tanuki Solette",
      "Aleksandrina Shadowbanes Voidstriders", "Mara Veld", "Niko Avar",
      "Sera Vahn", "Dorin Kalt", "Iria Sol", "Vex Noren", "Yara Tolen"
    ],
    "registration": {
      "Ctrl+Alt+1": true,
      "Ctrl+Alt+2": true,
      "Ctrl+Alt+Right": true,
      "Ctrl+Shift+2": true,
      "Ctrl+Shift+3": true
    },
    "locked": ["Aiga Otsolen"],
    "lock_default": false,
    "never_minimize": ["Tanuki Solette"],
    "excluded": ["Sera Vahn"],
    "sizes": {"Aiga Otsolen": [1280, 720]},
    "client_sizes": {"Aiga Otsolen": [1920, 1080], "Zuelo Parvi": [1600, 900]},
    "sizable": ["Aiga Otsolen", "Zuelo Parvi", "Corvin Veles", "Tanuki Solette", "Mara Veld"],
    "layout_sources": [
      {"name": "Aiga Otsolen", "online": true},
      {"name": "Tanuki Solette", "online": false}
    ],
    "bookmark_chords": {"active": ["Ctrl+Alt+1"], "latent": []}
  };

  api.get_preview_hotkey_state = function () {
    console.log('DEV api.get_preview_hotkey_state()');
    return Promise.resolve(JSON.parse(JSON.stringify(DEV_PREVIEW_HOTKEYS_FIXTURE)));
  };

  // ---- Stateful dev stubs for the five preview cycle-group methods.
  //
  // _devPreviewHotkeys is a deep copy of DEV_PREVIEW_HOTKEYS_FIXTURE.hotkeys.
  // Mutations update it in place; _devPushHotkeys rebuilds the full state from
  // DEV_PREVIEW_HOTKEYS_FIXTURE (providing enabled, characters, roster, excluded,
  // etc.) with the current _devPreviewHotkeys substituted as the hotkeys field,
  // so onPreviewHotkeys always receives the correct full-state shape.
  //
  // All five stubs return the production result shape {applied, persisted,
  // error, hotkeys} where hotkeys is the current _devPreviewHotkeys copy.
  var _devPreviewHotkeys = JSON.parse(JSON.stringify(DEV_PREVIEW_HOTKEYS_FIXTURE.hotkeys));

  function _devHotkeysCopy() {
    return JSON.parse(JSON.stringify(_devPreviewHotkeys));
  }

  function _devGroupResult(applied, error) {
    return {
      applied: applied,
      persisted: applied,
      error: error || null,
      hotkeys: _devHotkeysCopy()
    };
  }

  function _devPushHotkeys() {
    // Deferred via setTimeout to match production's async push behaviour:
    // Api._push is fired from a worker thread so it never runs inline within
    // a promise resolution.  A synchronous push here causes re-entrant renders
    // and makes the timing non-deterministic relative to the caller.
    //
    // Rebuilds the full state from DEV_PREVIEW_HOTKEYS_FIXTURE (provides
    // enabled, characters, roster, excluded, etc.) with the mutated
    // _devPreviewHotkeys substituted as the hotkeys field, so
    // onPreviewHotkeys replaces state with the correct full-state shape
    // instead of a partial hotkeys-only object.
    setTimeout(function () {
      if (window.onPreviewHotkeys) {
        var full = JSON.parse(JSON.stringify(DEV_PREVIEW_HOTKEYS_FIXTURE));
        full.hotkeys = _devHotkeysCopy();
        window.onPreviewHotkeys(full);
      }
    }, 0);
  }

  api.create_preview_cycle_group = function (name) {
    console.log('DEV api.create_preview_cycle_group(', name, ')');
    if (!name || !name.trim()) {
      return Promise.resolve(_devGroupResult(false, 'Group name must be a non-empty string'));
    }
    var clean = name.trim();
    var folded = clean.toLowerCase();
    var groups = _devPreviewHotkeys.groups;
    for (var i = 0; i < groups.length; i++) {
      if (groups[i].name.toLowerCase() === folded) {
        return Promise.resolve(_devGroupResult(false, 'A group named \'' + clean + '\' already exists'));
      }
    }
    var id = 'g-dev-' + Date.now();
    groups.push({id: id, name: clean, cycle: ''});
    _devPushHotkeys();
    return Promise.resolve(_devGroupResult(true, null));
  };

  api.rename_preview_cycle_group = function (groupId, name) {
    console.log('DEV api.rename_preview_cycle_group(', groupId, name, ')');
    if (!groupId) {
      return Promise.resolve(_devGroupResult(false, 'Invalid group_id'));
    }
    if (!name || !name.trim()) {
      return Promise.resolve(_devGroupResult(false, 'Group name must be a non-empty string'));
    }
    var clean = name.trim();
    var folded = clean.toLowerCase();
    var groups = _devPreviewHotkeys.groups;
    var target = null;
    for (var i = 0; i < groups.length; i++) {
      if (groups[i].id === groupId) { target = groups[i]; break; }
    }
    if (!target) {
      return Promise.resolve(_devGroupResult(false, 'No group with id \'' + groupId + '\''));
    }
    for (var j = 0; j < groups.length; j++) {
      if (groups[j] !== target && groups[j].name.toLowerCase() === folded) {
        return Promise.resolve(_devGroupResult(false, 'A group named \'' + clean + '\' already exists'));
      }
    }
    target.name = clean;
    _devPushHotkeys();
    return Promise.resolve(_devGroupResult(true, null));
  };

  api.delete_preview_cycle_group = function (groupId) {
    console.log('DEV api.delete_preview_cycle_group(', groupId, ')');
    if (!groupId) {
      return Promise.resolve(_devGroupResult(false, 'Invalid group_id'));
    }
    var groups = _devPreviewHotkeys.groups;
    var idx = -1;
    for (var i = 0; i < groups.length; i++) {
      if (groups[i].id === groupId) { idx = i; break; }
    }
    if (idx === -1) {
      return Promise.resolve(_devGroupResult(false, 'No group with id \'' + groupId + '\''));
    }
    groups.splice(idx, 1);
    var gbc = _devPreviewHotkeys.group_by_character;
    Object.keys(gbc).forEach(function (charName) {
      if (gbc[charName] === groupId) { delete gbc[charName]; }
    });
    _devPushHotkeys();
    return Promise.resolve(_devGroupResult(true, null));
  };

  api.set_preview_cycle_group_bind = function (groupId, gesture) {
    console.log('DEV api.set_preview_cycle_group_bind(', groupId, gesture, ')');
    if (!groupId) {
      return Promise.resolve(_devGroupResult(false, 'Invalid group_id'));
    }
    var groups = _devPreviewHotkeys.groups;
    var target = null;
    for (var i = 0; i < groups.length; i++) {
      if (groups[i].id === groupId) { target = groups[i]; break; }
    }
    if (!target) {
      return Promise.resolve(_devGroupResult(false, 'No group with id \'' + groupId + '\''));
    }
    target.cycle = gesture || '';
    _devPushHotkeys();
    return Promise.resolve(_devGroupResult(true, null));
  };

  api.set_preview_character_group = function (name, groupId) {
    console.log('DEV api.set_preview_character_group(', name, groupId, ')');
    if (!name) {
      return Promise.resolve(_devGroupResult(false, 'Invalid character name'));
    }
    var groups = _devPreviewHotkeys.groups;
    var gbc = _devPreviewHotkeys.group_by_character;
    if (!groupId) {
      // Empty string removes assignment (All-only).
      delete gbc[name];
    } else {
      var valid = false;
      for (var i = 0; i < groups.length; i++) {
        if (groups[i].id === groupId) { valid = true; break; }
      }
      if (!valid) {
        return Promise.resolve(_devGroupResult(false, 'No group with id \'' + groupId + '\''));
      }
      gbc[name] = groupId;
    }
    _devPushHotkeys();
    return Promise.resolve(_devGroupResult(true, null));
  };

  api.list_rows = function () {
    console.log('DEV api.list_rows()');
    setTimeout(function () {
      window.onRows({ rows: [
        // The `date` values are library.format_date's OWN output forms,
        // not timestamps. They were absolute ("Aug 21  19:04") here long
        // after Python went relative, which is the harness lying about
        // the exact thing this column is sized against -- r5 carries the
        // widest string format_date can produce so the age track's width
        // is exercised rather than assumed.
        { id: 'r1', name: '2026-08-21 19-04-11.mkv', date: 'just now',
          size: '1.4 GB', duration: '12:31', link: null, preselected: true },
        { id: 'r2', name: '2026-08-21 17-58-02.mkv', date: '3h ago',
          size: '812.0 MB', duration: '\u2026', link: null, preselected: false },
        { id: 'r3', name: '2026-08-20 22-10-49.mkv', date: 'yesterday',
          size: '2.1 GB', duration: '?', link: null, preselected: false },
        { id: 'r4', name: '2026-08-19 21-00-03.mkv', date: '6d ago',
          size: '640.5 MB', duration: '4:07',
          link: 'https://youtu.be/abc123XYZ', preselected: false },
        { id: 'r5', name: '2025-11-02 22-11-40.mkv', date: '2025 Nov 02',
          size: '318.2 MB', duration: '1:03:09', link: null,
          preselected: false }
      ] });
      window.onChannel({ channel_id: 'UC123', channel_title: 'FlyGD',
                         destination: 'Uploads go to FlyGD \u00b7 unlisted' });
      window.onAuthState({ state: 'connected', message: 'Connected' });
      window.onStatus({ text: 'Idle', kind: 'FG', busy: false });
    }, 0);
    return Promise.resolve(null);
  };

  // Manual drivers for the pushes no click can produce in a browser.
  // Typed into the devtools console during verification.
  //
  // `busy` is carried here exactly as Python carries it, because it is the
  // flag that decides whether a route change clears the strip: without it
  // the harness cannot show that a LIVE upload survives a trip to Skills
  // and a finished one does not, which is the whole of round 3's
  // finding 14.
  // Pushes an onEveSettingsNames payload carrying the current
  // devIdentificationGeneration so acceptIdentification() in evesettings.js
  // accepts it. deleted_candidate_ids is always empty here — the console
  // helpers only change structural state, not character existence.
  function devPushEveNames() {
    window.onEveSettingsNames({
      identification_generation: devIdentificationGeneration,
      deleted_candidate_ids: []
    });
  }

  window.DEV = {
    // `DEV.fleetHiddenLimit()` makes the backend's exact cap reachable from
    // the browser console: Ariadne stays visible, the other 64 known names
    // are hidden, and clicking Ariadne exercises the inline refusal/rollback.
    // This remains a helper rather than a URL scenario because it is a
    // mutation checkpoint entered after the Settings › Previews card is open.
    fleetHiddenLimit: function () {
      var index, name;
      fleetBar.seen = ['Ariadne'];
      fleetBar.hidden = [];
      fleetBar.running = ['Ariadne'];
      for (index = 1; index <= 64; index += 1) {
        name = 'Hidden ' + index;
        fleetBar.seen.push(name);
        fleetBar.hidden.push(name);
      }
      fleetBar.revision += 1;
      window.onFleetBarState(fleetBarState());
    },
    // The same bounded fixture scripts/shoot_screens.py injects into the live
    // app. This manual driver keeps every field browser-consumed rather than
    // leaving a Python-only JSON island in dev.js.
    fittingsScreenshot: function () {
      window.onFittingsScreenshotState(
        JSON.parse(JSON.stringify(DEV_FITTINGS_SCREENSHOT_FIXTURE)));
    },
    // `busy` defaults to true -- a percentage arriving usually means a live
    // transfer -- but it is a PARAMETER because the two payloads that carry
    // busy=false were otherwise unreachable from this harness, and both are
    // load-bearing since round 5's G1 made the track's visibility depend on
    // them. `DEV.determinate(100, false)` is a settled result and
    // `DEV.determinate(0, false)` is the error/cancel-at-zero shape that
    // must draw no bar at all.
    //
    // Without the argument this driver gave a FALSE PASS on finding 14:
    // DEV.determinate(100) then a route change left the bar on screen
    // because resetStrip early-returns on stripBusy, i.e. for the opposite
    // reason to the settled-result rule the check was meant to prove.
    determinate: function (pct, busy) {
      window.onProgress({ mode: 'determinate', pct: pct,
                          text: 'Uploading file 1 of 3\u2026 ' + pct + '%',
                          kind: 'FG',
                          busy: busy === undefined ? true : !!busy });
    },
    stitching: function () {
      window.onProgress({ mode: 'indeterminate', pct: 0,
                          text: 'Stitching with FFmpeg\u2026',
                          kind: 'FG', busy: true });
    },
    status: function (text, kind, busy) {
      window.onStatus({ text: text, kind: kind, busy: !!busy });
    },
    retry: function (available) {
      window.onRetryAvailable({ available: available });
    },
    // D5's control. Drives the same slot as `retry` above, and the two are
    // never armed together in the app -- so this is also the way to check
    // by hand that the page honours that rather than stacking both.
    cancel: function (available) {
      window.onCancelAvailable({ available: available });
    },
    // The completion event the panel clears its selection on (finding 5).
    // Worth driving on its own: in the app it arrives with a success strip
    // and a row link, and the panel's half of the change is only visible
    // if the selection actually drops.
    done: function () {
      window.onUploadDone({});
    },
    channel: function (title) {
      window.onChannel({ channel_id: 'UC123', channel_title: title,
                         destination: 'Uploads go to ' + title
                                      + ' \u00b7 unlisted' });
    },
    info: function () {
      window.onDialog({ kind: 'info', title: 'Upload complete',
                        body: 'All 3 recordings were uploaded.' });
    },
    warn: function () {
      window.onDialog({ kind: 'warning', title: 'No Selection',
                        body: 'Select at least one video to upload.' });
    },
    err: function () {
      window.onDialog({ kind: 'error', title: 'Upload failed',
                        body: 'HttpError 403: quotaExceeded' });
    },
    confirm: function () {
      window.onDialog({ kind: 'confirm', title: 'Confirm Upload',
        request_id: 'req-7',
        body: 'Upload 2 recordings to YouTube?\n\n'
            + 'Channel:  FlyGD\nPrivacy:  unlisted\n'
            + 'Title:    "Fight (1/2)" \u2026 "Fight (2/2)"\n'
            + 'Total:    3.5 GB \u00b7 0:24:11\n\n'
            + 'Publishing to YouTube cannot be undone from this app.' });
    },
    twoDialogs: function () {
      window.DEV.warn();
      window.DEV.confirm();
    },
    authState: function (state, message) {
      window.onAuthState({ state: state, message: message });
    },
    settings: function (patch, statusLine) {
      window.onSettings(settingsPayload(patch, statusLine));
    },
    skillsProgress: function (completed, total) {
      window.onSkillsProgress({ character_id: 2, character_name: 'Zuelo Parvi',
                                completed: completed, total: total, error: '' });
    },
    skillsRefreshing: function (busy) {
      skills.refresh_in_flight = !!busy;
      window.onSkills(skills);
    },
    // The Profiles states a click cannot reach. eveRunning() is the hazard
    // both pills paint; eveNoFolder() is the empty state that used to claim
    // "No other characters in this profile" when there was no profile.
    eveRunning: function (running) {
      eve.eve_running = running === undefined ? true : running;
      window.onEveSettingsRunning({ running: eve.eve_running });
    },
    eveNoFolder: function () {
      eve.root = ''; eve.server = ''; eve.profile = '';
      eve.servers = []; eve.profiles = [];
      eve.characters = []; eve.accounts = [];
      devPushEveNames();
    },
    eveUnreadable: function () {
      eve.unreadable = true;
      eve.characters = []; eve.accounts = [];
      devPushEveNames();
    },
    eveSelectiveAvailable: function (available) {
      eve.selective_copy_available = !!available;
      devPushEveNames();
    },
    skillsEmpty: function () {
      skills.characters = [];
      skills.plans = [];
      skills.selected_plan_name = '';
      window.onSkills(skills);
    },
    eveCharacters: function (name) {
      _devCharacters = devCharactersScenario(name);
      devPushCharactersChanged('scenario:' + devCharactersText(name || 'partial'));
    }
  };

  // ---- Profiles -------------------------------------------------------
  // The Profiles route had NO stub at all, so `?dev=1` rendered it as an
  // inert copy of itself: eve_settings_state hit "bridge: no such method",
  // render() bailed on the null, and the screen showed empty dropdowns and
  // no roster. That is indistinguishable from the bug this page's whole
  // failure mode produces, and it made the one screen whose findings are
  // about THIRTY-FIVE ROWS the one screen that could not be eyeballed.
  //
  // Thirty-five characters, because the number is the point: the roster's
  // column count, the page-versus-inner scrolling and the commit row's
  // wrapping all only misbehave at a real roster's size.
  var identitySearch = devSearch;
  var identityScenarioRequested = identitySearch.has('identity');
  var identityScenario = identitySearch.get('identity') || 'idle';
  var backupsScenario = identitySearch.get('backups') || '';
  var copyScenario = identitySearch.get('copy') || '';
  var formationsAccountScenario = identitySearch.get('formations-account') || '';
  // Task 7: the whole-profile copy checkpoints. A named scenario drives
  // the eve_settings_copy_profile double below through the real panel
  // rather than through a harness-only shortcut.
  var profileCopyScenario = identitySearch.get('profile') || '';
  var profilesScenarioRequested = !!(backupsScenario || copyScenario
    || formationsAccountScenario || profileCopyScenario);
  var identityScenarios = JSON.parse('{"idle":{"stage":"intro","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000","90000001","90000002"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":null},"waiting":{"stage":"observe","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"watching","error":null}},"none":{"stage":"check","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"none","error":"No account and character changes were found. Make a small settings change in the client, then close it completely and check again."}},"ambiguous":{"stage":"check","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"ambiguous","error":"More than one account changed. Close the other EVE clients and start again."}},"candidate-multiple":{"stage":"candidate","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"candidate","error":null,"account_id":"1003","character_ids":["90000004","90000005"]}},"pending-name":{"stage":"name","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"candidate","error":null,"account_id":"1003","character_ids":["90000004"]}},"existing-name":{"stage":"candidate","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"candidate","error":null,"account_id":"1001","character_ids":["90000001"]}},"roster-one":{"stage":"roster","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"candidate","error":null,"account_id":"1001","character_ids":["90000000"]},"roster_account":"1001"},"roster-two":{"stage":"roster","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000","90000001"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"candidate","error":null,"account_id":"1001","character_ids":["90000000"]},"roster_account":"1001"},"roster-three":{"stage":"roster","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000","90000001","90000002"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"candidate","error":null,"account_id":"1001","character_ids":["90000000"]},"roster_account":"1001"},"roster-empty":{"stage":"roster","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"candidate","error":null,"account_id":"1001","character_ids":["90000000"]},"discovered":["90000000"],"roster_account":"1001"},"move":{"stage":"move","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":{"status":"candidate","error":null,"account_id":"1002","character_ids":["90000000"]}},"full":{"stage":"manage","accounts":[{"id":"1001","account_name":"alpha@example","character_ids":["90000000","90000001","90000002"]},{"id":"1002","account_name":"beta@example","character_ids":["90000003"]},{"id":"1003","account_name":"","character_ids":[]}],"check":null,"roster_account":"1001"}}');
  var selectedIdentityScenario = identityScenarios[identityScenario]
    || identityScenarios.idle;

  var eveNames = [
    'Suartad Arsten', 'Yas Kalkoken', 'Zuelo Parvi', 'Mikan Antollare',
    'Rhea Vestibule', 'Tovan Kuvakei', 'Ceptaris Enderas', 'Dokan Kaundur',
    'Elsebeth Rhiannon', 'Fenrir Blackmoor', 'Gwyn Aldent', 'Hakan Ceres',
    'Ithra Vaelor', 'Jorunn Sakkert', 'Kael Ortan', 'Liris Ostus',
    'Marek Vetruvian', 'Nomi Sarum', 'Oren Tash-Murkon', 'Pell Kordaine',
    'Quinn Arkaral', 'Rask Amarantine', 'Sable Ithron', 'Tarek Nadire',
    'Uxor Kelendi', 'Vale Trystan', 'Wren Solette', 'Xander Voll',
    'Yrsa Halvorsen', 'Zeth Karidan', 'Aria Nostrade', 'Brann Ulvsson',
    'Corr Sevaine', 'Dain Holloway', 'Eir Sandvik'
  ];

  // The account-label resolver knows every character Wingman has named.
  // `identity_characters` below remains the narrower picker list for a
  // checkpoint, just as the production account label resolves associations
  // through the names service instead of through that picker.
  var knownIdentityCharacters = eveNames.map(function (name, i) {
    return { id: String(90000000 + i), name: name };
  });

  // Exact Python payload shape, asserted against selective.groups_payload
  // so this visual fixture cannot drift from the decoder's public groups.
  var selective = {
    groups_payload: {
      characters: [
        { id: 'windows', label: 'Window layout', default_on: true },
        { id: 'neocom', label: 'Neocom sidebar', default_on: true },
        { id: 'chat', label: 'Chat channels', default_on: true },
        { id: 'infopanels', label: 'Info panels', default_on: true },
        { id: 'dockpanels', label: 'Docked panels', default_on: true },
        { id: 'search_history', label: 'Search history & suggestions', default_on: false }
      ],
      accounts: [
        { id: 'overview', label: 'Overview profiles', default_on: true },
        { id: 'probes', label: 'Probe formations', default_on: true },
        { id: 'suppress', label: 'Suppressed dialogs', default_on: true },
        { id: 'audio', label: 'Audio settings', default_on: true },
        { id: 'camera_graphics', label: 'Camera & graphics', default_on: true },
        { id: 'market', label: 'Market & contracts', default_on: true },
        { id: 'slots', label: 'Module slot layout', default_on: false },
        { id: 'tabgroups', label: 'Window tab groups', default_on: true },
        { id: 'search_history', label: 'Search history & suggestions', default_on: false }
      ]
    }
  };

  var eve = {
    root: 'C:\\Users\\tng\\AppData\\Local\\CCP\\EVE',
    default_root: 'C:\\Users\\tng\\AppData\\Local\\CCP\\EVE',
    server: 'tq', profile: 'default',
    unreadable: false, too_broad: false,
    // null, not false: the real probe answers AFTER the state it triggered
    // has already been returned, and the pill's "Checking for EVE..." face
    // is the one a stub that guessed `false` would never show.
    eve_running: null,
    identification_active: selectedIdentityScenario.stage !== 'intro'
      && selectedIdentityScenario.stage !== 'manage',
    // True unconditionally: the dev harness always points at a Tranquility
    // fixture. Without this the canIdentify guard Task 6 added hides every
    // identity control and all identification scenarios render as inert.
    account_identity_available: true,
    selective_copy_available: true,
    copy_groups: selective.groups_payload,
    servers: [{ path: 'tq', name: 'Tranquility' }],
    // Two profiles, not one: every profile-copy checkpoint needs a real
    // Replace target, and 'multiple profiles with Default selected' is
    // itself one of the named scenarios below.
    profiles: [
      { path: 'default', name: 'Default', file_count: 72 },
      { path: 'fleet', name: 'Fleet', file_count: 58 }
    ],
    // Name-ordered, because the payload is: R1/D4 moved the roster's sort
    // out of evesettings.tree (which has only file ids) and into
    // Api.eve_settings_state (which has the resolved labels), so a
    // fixture in hand-written order would show a screen the app no longer
    // produces -- and R1 is precisely a finding about the order 32 names
    // arrive in. Same key as api.py's `roster`: case-folded name, id as
    // the tie-break.
    characters: eveNames.map(function (name, i) {
      var id = String(90000000 + i);
      return { path: 'c' + i, id: id, name: name,
               display_name: name, display_meta: 'Character ' + id };
    }).sort(function (a, b) {
      var an = a.name.toLowerCase(), bn = b.name.toLowerCase();
      if (an !== bn) return an < bn ? -1 : 1;
      return a.id < b.id ? -1 : (a.id > b.id ? 1 : 0);
    }),
    identity_characters: knownIdentityCharacters.filter(function (character) {
      return !selectedIdentityScenario.discovered
        || selectedIdentityScenario.discovered.indexOf(character.id) !== -1;
    }),
    backups_unreadable: false,
    // True, so the harness shows the Probe formations tool. The real
    // answer is Api.eve_settings_state's codec_available(), which is false
    // on a checkout with no sidecar bundled -- and a harness that mirrored
    // that would hide the one screen this fixture exists to let anyone
    // eyeball.
    formations_available: true,
    auto_keep: 10,
    backups: [
      { path: 'b1', created: '20260824-140300', origin: 'auto',
        kind: 'character', stem: 'core_char_90000001',
        display_name: 'Yas Kalkoken', display_meta: 'Character 90000001' },
      { path: 'b2', created: '20260824-140300', origin: 'auto',
        kind: 'account', stem: 'core_user_1001',
        display_name: "alpha@example", display_meta: "Suartad Arsten + 2 · Account 1001" },
      { path: 'b3', created: '20260821-091544', origin: 'manual',
        kind: 'profile', stem: 'Default',
        display_name: 'Default', display_meta: 'Profile' }
    ]
  };

  if (backupsScenario === 'empty') {
    eve.backups = [];
  } else if (backupsScenario === 'unreadable') {
    // enumerate_backups() returns no rows when it cannot read the directory.
    eve.backups_unreadable = true;
    eve.backups = [];
  }

  var identityScenarioQueued = false;
  var profilesScenarioQueued = false;
  api.eve_settings_state = function () {
    console.log('DEV api.eve_settings_state()');
    if (identityScenarioRequested && !identityScenarioQueued) {
      identityScenarioQueued = true;
      // The timer runs after this resolved payload has rendered. Tying the
      // visual transition to the read avoids a machine-speed delay that can
      // click before the route owns its state.
      window.setTimeout(paintIdentityScenario, 0);
    }
    if (profilesScenarioRequested && !profilesScenarioQueued) {
      profilesScenarioQueued = true;
      // As with identity, use the real route after the payload has painted.
      // The route-entry refresh is part of what these fixtures exercise.
      window.setTimeout(paintProfilesScenario, 0);
    }
    return Promise.resolve(JSON.parse(JSON.stringify(eve)));
  };

  // Returns rather than pushes, exactly as the bridge does, and returns the
  // path so a stub cannot look more decisive than the real one: Python's
  // detector returns "" for "already set to this folder" too, having said
  // so through an alert the page never sees.
  api.eve_settings_pick_root = function () {
    console.log('DEV api.eve_settings_pick_root()');
    return Promise.resolve(eve.root);
  };
  api.eve_settings_detect_root = function () {
    console.log('DEV api.eve_settings_detect_root()');
    return Promise.resolve(eve.root);
  };
  api.eve_settings_select = function (server, profile) {
    console.log('DEV api.eve_settings_select(', server, ',', profile, ')');
    // '' is not "no profile": Api.eve_settings_select hands discover()
    // `profile or None`, and an empty token is its one deliberate
    // fallback -- "the requested server's first profile". evesettings.js
    // relies on it, sending '' on a SERVER change rather than the old
    // server's profile path (which the endpoint would refuse). Assigning
    // the token straight through emptied the Profile select here and
    // disabled every control gated on state.profile, which no real server
    // change does. The fixture carries one server and one flat `profiles`
    // list -- that list IS what this server offers -- so its first entry
    // is the faithful answer without inventing a per-server association
    // the payload does not carry.
    var resolved = profile || (eve.profiles.length ? eve.profiles[0].path : '');
    eve.server = server; eve.profile = resolved;
    return Promise.resolve(true);
  };
  api.eve_settings_resolve_names = function () {
    console.log('DEV api.eve_settings_resolve_names()');
    return Promise.resolve(null);
  };
  // Task 7's specialized double. Validated the same way the bridge
  // validates it -- against a freshly discovered tree's current
  // selection -- so a stale token reads as the same refusal a real race
  // would produce. Every outcome after that point is one of the eleven
  // named checkpoints in PROFILE_COPY_SCENARIOS
  // (tests/test_dev_harness.py), selected by ?dev=1&profile=<key> and
  // driven through the real panel by paintProfileCopyScenario() below.
  //
  // Round 1 fix: PROFILE_COPY_SCENARIO_REQUESTS below pins the exact
  // mode/destination each scripted checkpoint's driver sends, and the
  // double refuses a request that does not match -- a sender-wiring
  // regression (sendProfileCopy shipping the wrong mode, or reading the
  // wrong field) is caught here rather than silently rendering some
  // OTHER checkpoint's canned outcome. This is a bridge-argument check
  // only: it never evaluates whether a name is well-formed or a
  // destination genuinely collides on disk -- that stays Python's job,
  // and a double that second-guessed it would drift from the bridge it
  // exists to imitate.
  var PROFILE_COPY_SCENARIO_REQUESTS = {
    'invalid-name': { mode: 'new', destination: '' },
    'collision': { mode: 'new', destination: 'dEfAuLt' },
    'busy': { mode: 'new', destination: 'New Ops' },
    'created': { mode: 'new', destination: 'New Ops' },
    'unsaved-selection': { mode: 'new', destination: 'New Ops' },
    'eve-running': { mode: 'new', destination: 'New Ops' },
    'replaced': { mode: 'replace', destination: 'fleet' },
    'rollback-failed': { mode: 'replace', destination: 'fleet' }
  };
  api.eve_settings_copy_profile = function (expectedSource, mode, destination) {
    console.log('DEV api.eve_settings_copy_profile(', expectedSource, mode,
                destination, ')');
    if (expectedSource !== eve.profile) {
      return Promise.resolve({ accepted: false, error: 'The selected profile changed.' });
    }
    var expectedRequest = PROFILE_COPY_SCENARIO_REQUESTS[profileCopyScenario];
    if (expectedRequest
        && (mode !== expectedRequest.mode || destination !== expectedRequest.destination)) {
      return Promise.resolve({
        accepted: false,
        error: 'Dev harness: the \'' + profileCopyScenario + '\' checkpoint expected '
          + 'mode=' + expectedRequest.mode + ' destination='
          + JSON.stringify(expectedRequest.destination) + ', got mode=' + mode
          + ' destination=' + JSON.stringify(destination) + '.'
      });
    }
    if (profileCopyScenario === 'invalid-name') {
      return Promise.resolve({
        accepted: false, error: 'Profile name cannot be empty.'
      });
    }
    if (profileCopyScenario === 'collision') {
      return Promise.resolve({
        accepted: false,
        error: 'A profile named \'' + destination + '\' already exists.'
      });
    }
    window.setTimeout(function () {
      // The accepted-busy checkpoint: the request was taken, but nothing
      // ever completes, so the disabled panel stays inspectable exactly
      // as the character-copy busy fixture already leaves it.
      if (profileCopyScenario === 'busy') return;
      var payload = {
        ok: true, operation: 'profile_copy', mode: mode,
        published: true, selection_persisted: true, error: null
      };
      if (profileCopyScenario === 'created') {
        // Mirrors Api._eve_select_created_profile: a successful creation
        // both adds the new profile and moves the selection onto it.
        var createdProfile = { path: 'newops', name: destination, file_count: 0 };
        eve.profiles = eve.profiles.concat([createdProfile]);
        eve.profile = createdProfile.path;
      } else if (profileCopyScenario === 'unsaved-selection') {
        eve.profiles = eve.profiles.concat(
          [{ path: 'newops', name: destination, file_count: 0 }]);
        payload.selection_persisted = false;
        payload.error = 'Created ' + destination + ', but Wingman '
          + 'could not remember the selection. Select it from Profile.';
      } else if (profileCopyScenario === 'eve-running') {
        payload.ok = false;
        payload.published = false;
        payload.selection_persisted = false;
        payload.error = 'EVE is running. Close EVE and retry.';
      } else if (profileCopyScenario === 'rollback-failed') {
        var target = eve.profiles.filter(function (profile) {
          return profile.path === destination;
        })[0];
        payload.ok = false;
        payload.published = false;
        payload.error = (target ? target.name : destination) + ' may now hold '
          + 'a mix of both profiles and Wingman could not put it back. '
          + 'Restore core_profile_20260824-140300.zip from Backups.';
      }
      window.onEveSettingsDone(payload);
    }, 250);
    return Promise.resolve({ accepted: true, error: null });
  };
  var pendingDevCandidate = null;
  // Monotonic counter matching Task 5's Python generation scheme: bumped
  // on every start and cancel so a stale promise from a superseded pass
  // is rejected by acceptIdentification() the same way it would be in
  // production. Carried by start/check/cancel responses and by every
  // onEveSettingsNames push.
  var devIdentificationGeneration = 0;

  function devAccount(accountId) {
    return eve.accounts.filter(function (item) { return item.id === accountId; })[0];
  }

  function devKnownCharacter(characterId) {
    return knownIdentityCharacters.filter(function (item) {
      return item.id === characterId;
    })[0];
  }

  function devCharacter(characterId) {
    return eve.identity_characters.filter(function (item) {
      return item.id === characterId;
    })[0];
  }

  function devAccountLabel(account) {
    var names = account.character_ids.map(devKnownCharacter).filter(Boolean)
      .map(function (item) { return item.name; }).sort();
    var summary = names.length
      ? names[0] + (names.length > 1 ? ' + ' + (names.length - 1) : '') : '';
    var primary = account.account_name || 'Account ' + account.id;
    var secondary = account.account_name
      ? (summary ? summary + ' · ' : '') + 'Account ' + account.id
      : 'Not identified';
    return { primary: primary, secondary: secondary,
             option: primary + ' · ' + secondary };
  }

  function refreshDevAccount(account) {
    var label = devAccountLabel(account);
    account.display_name = label.primary;
    account.display_meta = label.secondary;
    account.name = label.option;
  }

  // Each identity scenario changes its account associations. Build this
  // initial route payload after eve's character lookup exists rather than
  // applying the idle scenario's labels to every visual checkpoint.
  function devFixtureAccounts(scenario) {
    return scenario.accounts.map(function (seed, i) {
      var label = devAccountLabel(seed);
      return { path: 'a' + i, id: seed.id,
        name: label.option,
        display_name: label.primary,
        display_meta: label.secondary,
        account_name: seed.account_name,
        character_ids: seed.character_ids.slice() };
    });
  }

  eve.accounts = devFixtureAccounts(selectedIdentityScenario);

  function validateDevName(accountId, value) {
    var name = typeof value === 'string' ? value.trim() : '';
    if (!name) return { name: '', error: 'Enter an EVE Online username.' };
    if (name.length > 80) {
      return { name: '', error: 'Account names can be up to 80 characters.' };
    }
    var duplicate = eve.accounts.some(function (account) {
      return account.id !== accountId && account.account_name
        && account.account_name.toLowerCase() === name.toLowerCase();
    });
    return duplicate
      ? { name: '', error: 'That EVE Online username is already assigned to another account.' }
      : { name: name, error: null };
  }

  function validateDevRoster(accountId, ids, pendingName) {
    var account = devAccount(accountId);
    if (!account || !(account.account_name || pendingName)) {
      return 'Name this account before adding characters.';
    }
    if (!Array.isArray(ids)) return 'Choose a valid account and characters.';
    if (ids.length > 3) return 'An EVE account can have up to three characters.';
    if (ids.some(function (id, i) {
      return !/^[0-9]+$/.test(id) || ids.indexOf(id) !== i || !devCharacter(id);
    })) {
      return 'That character is not known to Wingman.';
    }
    return null;
  }

  function applyDevRoster(accountId, ids) {
    eve.accounts.forEach(function (account) {
      account.character_ids = account.id === accountId ? ids.slice()
        : account.character_ids.filter(function (id) { return ids.indexOf(id) === -1; });
      refreshDevAccount(account);
    });
  }

  api.eve_settings_identification_start = function () {
    pendingDevCandidate = null;
    eve.identification_active = true;
    // Bump the generation so any in-flight check promise resolves stale.
    devIdentificationGeneration += 1;
    return Promise.resolve({
      status: 'watching', error: null,
      identification_generation: devIdentificationGeneration
    });
  };
  api.eve_settings_identification_check = function () {
    var result = selectedIdentityScenario.check
      || { status: 'watching', error: null };
    pendingDevCandidate = result.status === 'candidate' ? result : null;
    if (result.status !== 'candidate') {
      return Promise.resolve(Object.assign({}, result,
        { identification_generation: devIdentificationGeneration }));
    }
    var account = devAccount(result.account_id);
    return Promise.resolve({
      status: 'candidate', error: null,
      identification_generation: devIdentificationGeneration,
      account: { id: account.id, primary: account.display_name,
                 secondary: account.display_meta, option: account.name },
      characters: result.character_ids.map(devCharacter).filter(Boolean)
    });
  };
  api.eve_settings_identification_cancel = function () {
    pendingDevCandidate = null;
    eve.identification_active = false;
    // Bump so any racing check that resolves after this cancel is rejected.
    devIdentificationGeneration += 1;
    return Promise.resolve({
      status: 'cancelled',
      identification_generation: devIdentificationGeneration
    });
  };
  api.eve_settings_identification_confirm = function (accountId, characterId, name) {
    var offered = pendingDevCandidate
      && pendingDevCandidate.account_id === accountId
      && pendingDevCandidate.character_ids.indexOf(characterId) !== -1;
    if (!offered) {
      return Promise.resolve({ applied: false, persisted: false,
        error: 'That account match is no longer available.' });
    }
    var account = devAccount(accountId);
    var checked = validateDevName(accountId, name);
    var ids = account ? account.character_ids.slice() : [];
    if (checked.error) {
      return Promise.resolve({ applied: false, persisted: false, error: checked.error });
    }
    if (ids.indexOf(characterId) === -1) ids.push(characterId);
    var rosterError = validateDevRoster(accountId, ids, checked.name);
    if (rosterError) {
      return Promise.resolve({ applied: false, persisted: false, error: rosterError });
    }
    // Validate first, then update both maps as one fake commit. A rejected
    // candidate therefore cannot leave a name without its first link.
    account.account_name = checked.name;
    applyDevRoster(accountId, ids);
    pendingDevCandidate = null;
    eve.identification_active = false;
    return Promise.resolve({ applied: true, persisted: true, error: null });
  };

  api.eve_settings_set_account_name = function (accountId, name) {
    var account = devAccount(accountId);
    var checked = validateDevName(accountId, name);
    if (!account || checked.error) {
      return Promise.resolve({ applied: false, persisted: false,
        error: checked.error || 'Choose a valid account.' });
    }
    account.account_name = checked.name;
    refreshDevAccount(account);
    return Promise.resolve({ applied: true, persisted: true, error: null });
  };
  api.eve_settings_set_account_characters = function (accountId, ids) {
    var error = validateDevRoster(accountId, ids);
    if (error) {
      return Promise.resolve({ applied: false, persisted: false, error: error });
    }
    applyDevRoster(accountId, ids);
    return Promise.resolve({ applied: true, persisted: true, error: null });
  };
  api.eve_settings_set_auto_keep = function (value) {
    var wanted = Number(value);
    if (wanted < 1 || wanted > 100 || Math.floor(wanted) !== wanted) {
      return Promise.resolve({ accepted: false, value: eve.auto_keep,
                               error: 'Enter a number from 1 to 100.' });
    }
    eve.auto_keep = wanted;
    setTimeout(function () { window.onEveSettingsDone({ ok: true }); }, 600);
    return Promise.resolve({ accepted: true, value: wanted, error: null });
  };

  // Every mutation returns "a worker started" and then pushes, because the
  // page's `if (!accepted) setBusy(false)` branch exists for the case where
  // one did NOT -- a stub that answered synchronously would leave the busy
  // path, which is what disables half the screen, permanently unexercised.
  function eveMutation(name) {
    return function () {
      console.log('DEV api.' + name + '(',
                  Array.prototype.slice.call(arguments), ')');
      // ?copy=busy intentionally leaves the worker pending so its disabled
      // controls remain inspectable; ?copy=success uses the normal delayed
      // completion and therefore settles on the production follow-up.
      if (name !== 'eve_settings_copy' || copyScenario !== 'busy') {
        setTimeout(function () {
          window.onEveSettingsDone({ ok: true });
        }, 600);
      }
      return Promise.resolve(true);
    };
  }
  ['eve_settings_copy', 'eve_settings_backup', 'eve_settings_restore',
   'eve_settings_delete_backup'
  ].forEach(function (name) { api[name] = eveMutation(name); });

  // Probe formations, in METERS, exactly as the bridge returns them: the
  // editor's whole km/AU boundary is in fromMeters/toMeters, so a fixture
  // written in km would render correctly and prove nothing. `Test` is the
  // real formation read back off a live account file during Slice 0 --
  // four probes, f64 positions, a 4 AU range (598391482800 m) -- and
  // `Drifter` is the two-probe wide pair the presets offer.
  //
  // Copied per account below, and the save stub writes into that account's
  // copy, so a save-then-reopen in the harness round-trips through meters
  // the way the app does. That is the only check the unit conversion gets
  // anywhere: nothing in the test suite executes this file or formations.js.
  var devFormations = [
    { id: 0, name: 'Test', probes: [
      { x: -2048, y: 0, z: 0, range: 598391482800 },
      { x: -2048, y: 299195727872, z: 0, range: 598391482800 },
      { x: 299195727872, y: 0, z: 0, range: 598391482800 },
      { x: 92456566784, y: 0, z: 284552069120, range: 598391482800 }
    ] },
    { id: 3, name: 'Drifter', probes: [
      { x: 11000000, y: 3400000, z: 0, range: 4787715862400 },
      { x: -11000000, y: -3400000, z: 0, range: 4787715862400 }
    ] }
  ];
  // Each account has its own file and therefore its own formations. The
  // second fixture differs visibly, so ?formations-account=switch proves
  // the clean account switch replaces the editor rather than only its label.
  var devFormationsByAccount = {};
  eve.accounts.forEach(function (account, index) {
    var formations = JSON.parse(JSON.stringify(devFormations));
    if (index === 1) formations[0].name = 'Second account test';
    devFormationsByAccount[account.path] = formations;
  });
  // Deliberately SLOW, the way eveMutation deliberately is. This is a
  // read, so the obvious stub resolves at once -- and resolving at once
  // erases the window formations.js's reload runs in, which is where an
  // edit can be painted over. A harness that cannot reproduce a race
  // cannot verify the guard against it, and this one was invisible in
  // ?dev=1 until the delay went in.
  api.eve_settings_formations = function (path) {
    console.log('DEV api.eve_settings_formations(', path, ')');
    var account = eve.accounts.filter(function (a) {
      return a.path === path;
    })[0];
    return new Promise(function (resolve) {
      setTimeout(function () {
        resolve({
          ok: true, path: path, name: account ? account.name : path,
          formations: JSON.parse(JSON.stringify(devFormationsByAccount[path] || []))
        });
      }, 150);
    });
  };
  // The save MINTS an id for every `id: null`, because write_formations
  // does -- above every id the file has ever held. Without this the stub
  // stored the page's own nulls and handed them straight back, so the
  // harness could not show the one behaviour that makes the editor reload
  // after a save: a brand-new formation coming back with a real id.
  // Highest id wins the next number, matching `max(taken) + 1`.
  api.eve_settings_save_formations = function (path, items) {
    var existing = devFormationsByAccount[path] || [];
    var next = -1;
    existing.concat(items).forEach(function (f) {
      if (typeof f.id === 'number' && f.id > next) { next = f.id; }
    });
    devFormationsByAccount[path] = JSON.parse(JSON.stringify(items)).map(function (f) {
      if (f.id === null || f.id === undefined) { next += 1; f.id = next; }
      return f;
    });
    return eveMutation('eve_settings_save_formations')(path, items);
  };

  window.pywebview = { api: api };
  window.dispatchEvent(new Event('pywebviewready'));

  // Open the requested visual checkpoint without teaching production page
  // code about harness-only states. Each click follows the real route's
  // event handlers and bridge calls, including focus movement and refreshes.
  function paintIdentityScenario() {
    var stage = selectedIdentityScenario.stage;
    if (stage === 'intro') WM.el('ai-intro-heading').focus();
    if (stage === 'check' || stage === 'candidate' || stage === 'move'
        || stage === 'name' || stage === 'roster') {
      WM.el('es-identify-check').click();
    }
    if (stage === 'name' || stage === 'roster' || stage === 'move') {
      window.setTimeout(function () { WM.el('es-identify-link').click(); }, 0);
    } else if (stage === 'manage') {
      WM.el('es-manage-toggle').click();
      var account = selectedIdentityScenario.move_account
        || selectedIdentityScenario.roster_account;
      WM.el('es-identity-account').value = account;
      WM.el('es-identity-account').dispatchEvent(new Event('change'));
      if (selectedIdentityScenario.move_character) {
        WM.el('es-character-add').value = selectedIdentityScenario.move_character;
        WM.el('es-character-add-btn').click();
      } else {
        WM.el('es-identity-account').focus();
      }
    }
  }

  function paintProfilesScenario() {
    if (backupsScenario === 'empty' || backupsScenario === 'unreadable'
        || backupsScenario === 'filtered') {
      // Backups is entered through its real route handler. For the filtered
      // state, set the real field after that handler's refresh has painted.
      WM.route('backups');
      if (backupsScenario === 'filtered') {
        window.setTimeout(function () {
          var filter = WM.el('es-backup-filter');
          filter.value = 'no matching backup';
          filter.dispatchEvent(new Event('input'));
        }, 0);
      }
      return;
    }
    if (copyScenario === 'busy' || copyScenario === 'success') {
      // The actual target and Copy click retain the delayed worker window:
      // busy displays "Copy operation in progress…", while success waits for
      // its push and displays the page's "Copy complete." follow-up.
      var target = WM.el('es-targets').querySelector('input[type="checkbox"]');
      if (target) target.click();
      WM.el('es-copy').click();
      return;
    }
    if (formationsAccountScenario) {
      WM.openFormations(eve.accounts, eve.accounts[0].path);
      if (formationsAccountScenario === 'switch' && eve.accounts[1]) {
        window.setTimeout(function () {
          var picker = WM.el('fm-account');
          picker.value = eve.accounts[1].path;
          picker.dispatchEvent(new Event('change'));
        }, 250);
      }
      return;
    }
    if (profileCopyScenario) {
      paintProfileCopyScenario();
    }
  }

  // The eleven whole-profile-copy checkpoints, driven through the real
  // panel controls (open, mode radios, name/destination fields, submit)
  // rather than a harness-only shortcut. 'multiple' is the fixture's own
  // base state -- see the profiles list above -- so it opens nothing.
  function paintProfileCopyScenario() {
    if (profileCopyScenario === 'multiple') return;
    WM.el('es-profile-copy-open').click();
    if (profileCopyScenario === 'new-disclosure') return;
    if (profileCopyScenario === 'replace-disclosure') {
      WM.el('es-profile-copy-replace').click();
      return;
    }
    if (profileCopyScenario === 'replaced' || profileCopyScenario === 'rollback-failed') {
      WM.el('es-profile-copy-replace').click();
      WM.el('es-profile-copy-destination').value = 'fleet';
    } else if (profileCopyScenario === 'collision') {
      WM.el('es-profile-copy-name').value = 'dEfAuLt';
    } else if (profileCopyScenario === 'invalid-name') {
      // No field to set: the checkpoint is a blank, untouched name field,
      // submitted as-is -- the same request an idle click would send.
    } else if (profileCopyScenario === 'busy' || profileCopyScenario === 'created'
        || profileCopyScenario === 'eve-running'
        || profileCopyScenario === 'unsaved-selection') {
      WM.el('es-profile-copy-name').value = 'New Ops';
    }
    WM.el('es-profile-copy-submit').click();
  }

  function showIdentityScenario() {
    WM.route('accountidentity');
  }

  function showProfilesScenario() {
    WM.route('evesettings');
  }

  function showCharactersScenario() {
    WM.route('settings');
    WM.section('characters');
  }

  if (identityScenarioRequested) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', showIdentityScenario, { once: true });
    } else {
      showIdentityScenario();
    }
  } else if (profilesScenarioRequested) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', showProfilesScenario, { once: true });
    } else {
      showProfilesScenario();
    }
  } else if (charactersScenarioRequested) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', showCharactersScenario, { once: true });
    } else {
      showCharactersScenario();
    }
  }
}());
