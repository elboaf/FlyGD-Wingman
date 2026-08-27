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
   'connect_google', 'dialog_response', 'minimize', 'close',
   'skills_add_character', 'skills_cancel_auth', 'skills_refresh',
   'skills_reload_plans', 'skills_open_plans_folder'
  ].forEach(function (name) { api[name] = log(name); });

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
   'set_preview_size', 'reset_preview_layouts',
   // Task 9: same shape; settings.js reverts the checkbox on anything
   // that is not `applied`, same as show_labels/opacity above.
   'set_preview_snap',
   // Same shape again: settings.js reverts the checkbox on anything that
   // is not `applied`.
   'set_preview_lock_aspect'
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
            // Task 10: read here by settings.js's own wm:settings listener
            // AND by previews.js's (previews.js needs it to decide whether
            // each row's Never-minimize checkbox is enabled).
            minimize_inactive_clients: true,
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
          }
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
      // 'Aleksandrina Shadowbanes Voidstriders' (37 chars) stays, though
      // not for the reason it was added. It was added when the name was
      // #preview-binds's own first column and the only track that could
      // shrink; the name now takes a full-width line of its own
      // (`.lab { grid-column: 1 / -1 }`), so it cannot be squeezed by the
      // control tracks at all. What it still proves is the other half:
      // that a name wider than the control line neither wraps badly nor
      // pushes the card into horizontal overflow at the 840px floor.
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
      // One lock and one never-minimize, split across the online/offline
      // divide on purpose: 'Aiga Otsolen' is running (Lock on an online
      // row), 'Tanuki Solette' is not (Never-minimize on an offline/dim
      // row) -- so both checkboxes are proven against both branches
      // rather than only the offline one the prior fix round covered.
      locked: ['Aiga Otsolen'],
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

  var eve = {
    root: 'C:\\Users\\tng\\AppData\\Local\\CCP\\EVE',
    default_root: 'C:\\Users\\tng\\AppData\\Local\\CCP\\EVE',
    server: 'tq', profile: 'default',
    unreadable: false, too_broad: false,
    // null, not false: the real probe answers AFTER the state it triggered
    // has already been returned, and the pill's "Checking for EVE..." face
    // is the one a stub that guessed `false` would never show.
    eve_running: null,
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
      return { path: 'c' + i, id: String(90000000 + i), name: name };
    }).sort(function (a, b) {
      var an = a.name.toLowerCase(), bn = b.name.toLowerCase();
      if (an !== bn) return an < bn ? -1 : 1;
      return a.id < b.id ? -1 : (a.id > b.id ? 1 : 0);
    }),
    accounts: [
      { path: 'a0', id: '1001', name: 'Account 1001' },
      { path: 'a1', id: '1002', name: 'Account 1002' },
      { path: 'a2', id: '1003', name: 'Account 1003' }
    ],
    backups_unreadable: false,
    auto_keep: 10,
    backups: [
      { path: 'b1', created: '20260824-140300', origin: 'auto',
        kind: 'character', stem: 'core_char_90000001' },
      { path: 'b2', created: '20260824-140300', origin: 'auto',
        kind: 'character', stem: 'core_char_90000002' },
      { path: 'b3', created: '20260821-091544', origin: 'manual',
        kind: 'profile', stem: 'settings_Default' }
    ]
  };

  api.eve_settings_state = function () {
    console.log('DEV api.eve_settings_state()');
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

  // Every mutation returns "a worker started" and then pushes, because the
  // page's `if (!accepted) setBusy(false)` branch exists for the case where
  // one did NOT -- a stub that answered synchronously would leave the busy
  // path, which is what disables half the screen, permanently unexercised.
  function eveMutation(name) {
    return function () {
      console.log('DEV api.' + name + '(',
                  Array.prototype.slice.call(arguments), ')');
      setTimeout(function () {
        window.onEveSettingsDone({ ok: true });
      }, 600);
      return Promise.resolve(true);
    };
  }
  ['eve_settings_copy', 'eve_settings_backup', 'eve_settings_restore',
   'eve_settings_delete_backup'
  ].forEach(function (name) { api[name] = eveMutation(name); });

  window.pywebview = { api: api };
  window.dispatchEvent(new Event('pywebviewready'));
}());
