/* Manual-verification harness. Inert inside the real app: it does nothing
 * unless the page is loaded WITHOUT pywebview and with ?dev=1, which can
 * only happen in a browser opened by hand. It exists so the page can be
 * eyeballed without launching Python, and is deliberately the only file
 * that fabricates data. */
(function () {
  'use strict';
  if (window.pywebview) return;
  if (!/[?&]dev=1/.test(window.location.search)) return;

  var log = function (name) {
    return function () {
      var args = Array.prototype.slice.call(arguments);
      console.log('DEV api.' + name + '(', args, ')');
      return Promise.resolve(null);
    };
  };

  var api = {};
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
   'skills_add_character', 'skills_cancel_auth', 'skills_refresh',
   'skills_reload_plans', 'skills_open_plans_folder'
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

  api.skills_forget_character = function (id) {
    console.log('DEV api.skills_forget_character(', id, ')');
    skills.characters = skills.characters.filter(function (ch) {
      return ch.character_id !== id;
    });
    setTimeout(function () { window.onSkills(skills); }, 0);
    return Promise.resolve(true);
  };

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
  var skills = {
    auth_configured: true, auth_in_progress: false, refresh_in_flight: false,
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
        missing_count: 0, unknown_count: 0, group: 'Wolfpack' },
      { character_id: 2, character_name: 'Zuelo Parvi',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Training',
        estimated_finish_utc: '2026-08-26T12:00:00+00:00',
        queue_timing_unknown: false,
        active_count: 12, trained_inactive_count: 0, queued_count: 2,
        missing_count: 0, unknown_count: 0, group: 'Wolfpack' },
      { character_id: 3, character_name: 'Kaska Rin',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Training',
        estimated_finish_utc: '', queue_timing_unknown: true,
        active_count: 13, trained_inactive_count: 0, queued_count: 1,
        missing_count: 0, unknown_count: 0, group: 'Wolfpack' },
      { character_id: 4, character_name: 'Delen Vok',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Locked',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 11, trained_inactive_count: 3, queued_count: 0,
        missing_count: 0, unknown_count: 0, group: 'Logi Wing' },
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
                        'Gunnery V'] },
      { character_id: 6, character_name: 'Nera Tal',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Missing',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 12, trained_inactive_count: 0, queued_count: 0,
        missing_count: 2, unknown_count: 0, group: 'Wolfpack',
        // Under the cap, so no remainder clause.
        missing_names: ['Motion Prediction V', 'Sharpshooter IV'] },
      { character_id: 7, character_name: 'Orin Kesh',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Unknown',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 13, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 1, group: 'Logi Wing' },
      { character_id: 8, character_name: 'Tavi Solen', fetched_utc: '',
        fetched_label: 'Never fetched',
        error: 'The refresh token was rejected', needs_reauth: true,
        stale: false, readiness: 'Unscored', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 0, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0, group: '' },
      { character_id: 9, character_name: 'Mira Halcyon', fetched_utc: '',
        fetched_label: 'Never fetched',
        error: '', needs_reauth: false, stale: false,
        readiness: 'Ascendant', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 0, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0, group: '' }
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
              events: {
                combat: { enabled: true, cooldown_s: 1, duration_ms: 1200,
                  pulses: 3, color: '#ff4d4d', sound: 'alarm' },
                warp_scramble: { enabled: true, cooldown_s: 8,
                  duration_ms: 1200, pulses: 3, color: '#ffd24d',
                  sound: 'ring' },
                decloak: { enabled: true, cooldown_s: 8, duration_ms: 1200,
                  pulses: 3, color: '#4dd2ff', sound: 'notify' }
              }
            }
          },
          // The floating sig bar's section, present because the real
          // payload ships `dict(cfg)` whole. ON against a shipped default
          // of off, for the same reason hide_on_lost_focus is: the
          // harness is where the card's controls are eyeballed, and a
          // default-valued fixture cannot show they read the payload.
          sig_bar: { enabled: true, x: null, y: null }
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

  // The bar page pulls its section once at load; so does bookmarks.js
  // for the toggle's initial paint. Returns the same object the payload
  // above carries, so the two doubles cannot disagree.
  api.sig_bar_settings = function () {
    console.log('DEV api.sig_bar_settings()');
    return Promise.resolve(settingsPayload().settings.sig_bar);
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

  api.get_preview_hotkey_state = function () {
    console.log('DEV api.get_preview_hotkey_state()');
    // Shapes taken from Api.get_preview_hotkey_state and the settings
    // schema, not guessed: `hotkeys` is
    // {characters: {name: chord}, cycle_next, cycle_prev} -- NOT
    // cycle_forward/cycle_back -- `registration` is keyed by CHORD with a
    // boolean value, and `bookmark_chords` is {active: [], latent: []}.
    // The first draft of this fixture invented three of those and rendered
    // every row as "Not set" while looking plausible, which is the exact
    // failure this file's own comment warns about: a double that models a
    // shape the bridge does not produce.
    //
    // `enabled: true`, not false. This fixture originally shipped with
    // previews OFF -- deliberately, to exercise the under-looked-at
    // offline-binding path -- but that meant every row went through
    // `makeRow`'s `online === null` branch (previews.js: `state.enabled ?
    // entry.online : null`), and `.dim` never got added to a single row.
    // Previews being ON is the normal state for anyone using this
    // feature, so an always-off fixture left the branch users actually
    // see unrendered and unverified. `characters` (below) now lists who
    // is running -- Windows genuinely cannot hold chords with the host
    // stopped, so `enabled: true` requires this to be non-empty, unlike
    // the old `enabled: false` + `characters: []` pair.
    return Promise.resolve({
      enabled: true,
      // Preview gestures are stored as preview/gestures.py display()
      // strings -- "Ctrl+Alt+Right" -- and NOT as AHK. Bookmarks use AHK
      // and send a separate `displays` table; previews render the stored
      // value directly, so the two subsystems genuinely differ here. The
      // first draft of this fixture wrote AHK and rendered "^!Right" in
      // the button, which looks like a formatting bug in the page rather
      // than a wrong fixture. Verified by running from_capture() rather
      // than typed.
      hotkeys: {
        characters: {
          'Aiga Otsolen': 'Ctrl+Alt+1',
          'Zuelo Parvi': 'Ctrl+Alt+2'
        },
        cycle_next: 'Ctrl+Alt+Right',
        cycle_prev: ''
      },
      // Running (online) characters. Both are also owed a row by
      // `hotkeys.characters` above, so this is what flips them from the
      // offline/dim branch to the online one now that `enabled: true`.
      characters: ['Aiga Otsolen', 'Zuelo Parvi'],
      // `roster` is every character previews knows about, running or
      // not -- `rows()` (previews.js) already de-dupes against
      // `characters`, so listing the same two names again here is
      // harmless and matches what the real bridge sends. Four distinct
      // rows total, not three: a three-row fixture never has to prove
      // `.settings-pane`'s vertical scroller (overflow-y: auto, style.css)
      // actually does anything at the 625px floor, and never puts an
      // offline (dim) row next to an online one so both render at once.
      //
      // 'Aleksandrina Shadowbanes Voidstriders' (37 chars) stays, and is
      // load-bearing again. It was added when the name was
      // #preview-binds's own first column and the only track that could
      // shrink; B1 then gave the name a full-width line of its own, where
      // nothing could squeeze it; the name is back in a column now, a
      // FIXED 150px one. At 291px of text against that track it is the
      // only fixture row that exercises the ellipsis, the `title` that
      // carries the untruncated name, and -- with this row also being
      // offline -- the proof that the `offline` tag keeps its full width
      // while the name yields, which is what the flex split of `.lab`
      // exists to do. It also still proves the older half: a name wider
      // than the control line neither wraps badly nor pushes the card into
      // horizontal overflow at the 840px floor.
      roster: [
        'Aiga Otsolen', 'Zuelo Parvi', 'Tanuki Solette',
        'Aleksandrina Shadowbanes Voidstriders'
      ],
      // Windows holding all three configured chords -- the normal case
      // once the host is actually running, unlike the old `{}` that
      // matched `enabled: false`'s "nothing can be registered" state.
      registration: {
        'Ctrl+Alt+1': true,
        'Ctrl+Alt+2': true,
        'Ctrl+Alt+Right': true
      },
      // One lock and one never-minimize, on different characters on
      // purpose: 'Aiga Otsolen' is running and 'Tanuki Solette' is not.
      // Neither checkbox sits on a row any more -- both moved into the
      // disclosures under their global toggles, where every character is
      // listed the same way regardless of whether their client is up. The
      // split is kept because the two rosters are built from the same
      // `rows()` the table is, so a fixture whose ticks all landed on
      // running characters would not show that an offline character
      // reaches the blocks at all.
      locked: ['Aiga Otsolen'],
      // Rides THIS payload, not the settings one -- previews.js resolves
      // isLocked from `state`, which is the hotkey payload wholesale. The
      // settings fixture carries a copy for settings.js's own checkbox;
      // both are false and must stay in step, or the harness shows the
      // table disagreeing with the control that governs it.
      //
      // Present rather than omitted even though `!!undefined` is already
      // false: Api.get_preview_hotkey_state always sends the bool, and a
      // fixture that leans on a JS coercion the real payload never
      // exercises is a fixture that agrees by luck.
      lock_default: false,
      never_minimize: ['Tanuki Solette'],
      // One opted-out character, and deliberately one that is ONLINE and
      // holds a keybind ('Zuelo Parvi'): that is the row where the state
      // is visible -- a live client whose controls are all grey and whose
      // saved chord is still showing on an inert button. An offline
      // opted-out row would look almost the same as an ordinary offline
      // one and would prove nothing.
      excluded: ['Zuelo Parvi'],
      // Task 8: one character with both a saved size and a live client
      // size ('Aiga Otsolen' -- exercises sizeHint's computed-height
      // branch), one with a client size but no saved one yet (defaults to
      // 640 wide), and one offline with neither ('Tanuki Solette' --
      // exercises the "not running" branch). Without both branches present
      // the Size… control cannot be exercised at all under ?dev=1.
      sizes: { 'Aiga Otsolen': [1280, 720] },
      client_sizes: { 'Aiga Otsolen': [1920, 1080], 'Zuelo Parvi': [1600, 900] },
      // Which characters set_preview_size can succeed for -- Api computes
      // it as (running | in layouts), and the page renders Size... only
      // for these. Deliberately NOT every name above: the two online
      // characters plus 'Tanuki Solette', who is offline but has been
      // dragged once, so the harness shows both states of the column. If
      // this listed everyone the fixture would hide the whole point of the
      // gate, which is that most of a real roster cannot be sized.
      sizable: ['Aiga Otsolen', 'Zuelo Parvi', 'Tanuki Solette'],
      // Sources deliberately cross the online boundary: the picker groups
      // both in words, and offline geometry is the feature's primary value.
      layout_sources: [
        {name: 'Aiga Otsolen', online: true},
        {name: 'Tanuki Solette', online: false}
      ],
      // ACTIVE, matching what Api._bookmark_chords would return for the
      // get_bookmarks fixture above: it ships `enabled: true` with
      // 'EVE - Aiga Otsolen' ticked, which is exactly the pair that makes a
      // bookmark chord registered. This said `latent` under a comment
      // reasoning that "bookmarks register nothing" -- true of no fixture
      // in this file. Caught by review while C6 was adding the other half.
      bookmark_chords: { active: ['Ctrl+Alt+1'], latent: [] }
    });
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
  window.DEV = {
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
    skillsAuth: function (busy) {
      skills.auth_in_progress = !!busy;
      window.onSkills(skills);
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
      window.onEveSettingsNames();
    },
    eveUnreadable: function () {
      eve.unreadable = true;
      eve.characters = []; eve.accounts = [];
      window.onEveSettingsNames();
    },
    eveSelectiveAvailable: function (available) {
      eve.selective_copy_available = !!available;
      window.onEveSettingsNames();
    },
    skillsEmpty: function () {
      skills.characters = [];
      skills.plans = [];
      skills.selected_plan_name = '';
      window.onSkills(skills);
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
  var identitySearch = new URLSearchParams(window.location.search);
  var identityScenarioRequested = identitySearch.has('identity');
  var identityScenario = identitySearch.get('identity') || 'idle';
  var backupsScenario = identitySearch.get('backups') || '';
  var copyScenario = identitySearch.get('copy') || '';
  var formationsAccountScenario = identitySearch.get('formations-account') || '';
  var profilesScenarioRequested = !!(backupsScenario || copyScenario
    || formationsAccountScenario);
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
    selective_copy_available: true,
    copy_groups: selective.groups_payload,
    servers: [{ path: 'tq', name: 'Tranquility' }],
    profiles: [{ path: 'default', name: 'Default', file_count: 72 }],
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
    eve.server = server; eve.profile = profile;
    return Promise.resolve(true);
  };
  api.eve_settings_resolve_names = function () {
    console.log('DEV api.eve_settings_resolve_names()');
    return Promise.resolve(null);
  };
  var pendingDevCandidate = null;

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
    return Promise.resolve({ status: 'watching', error: null });
  };
  api.eve_settings_identification_check = function () {
    var result = selectedIdentityScenario.check
      || { status: 'watching', error: null };
    pendingDevCandidate = result.status === 'candidate' ? result : null;
    if (result.status !== 'candidate') return Promise.resolve(result);
    var account = devAccount(result.account_id);
    return Promise.resolve({
      status: 'candidate', error: null,
      account: { id: account.id, primary: account.display_name,
                 secondary: account.display_meta, option: account.name },
      characters: result.character_ids.map(devCharacter).filter(Boolean)
    });
  };
  api.eve_settings_identification_cancel = function () {
    pendingDevCandidate = null;
    eve.identification_active = false;
    return Promise.resolve(true);
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
    }
  }

  function showIdentityScenario() {
    WM.route('accountidentity');
  }

  function showProfilesScenario() {
    WM.route('evesettings');
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
  }
}());
