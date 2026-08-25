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
  ['delete_selected', 'start_upload', 'retry',
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
   'set_discord_webhook', 'clear_discord_webhook'
  ].forEach(function (name) {
    api[name] = function (value) {
      console.log('DEV api.' + name + '(', value, ')');
      return Promise.resolve({applied: true, persisted: true, error: null});
    };
  });

  api.set_folder = function (which, path) {
    console.log('DEV api.set_folder(', which, ',', path, ')');
    return Promise.resolve({applied: true, persisted: true, error: null});
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

  api.skills_forget_character = function (id) {
    console.log('DEV api.skills_forget_character(', id, ')');
    skills.characters = skills.characters.filter(function (ch) {
      return ch.character_id !== id;
    });
    setTimeout(function () { window.onSkills(skills); }, 0);
    return Promise.resolve(true);
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
        missing_count: 0, unknown_count: 0 },
      { character_id: 2, character_name: 'Zuelo Parvi',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Training',
        estimated_finish_utc: '2026-08-26T12:00:00+00:00',
        queue_timing_unknown: false,
        active_count: 12, trained_inactive_count: 0, queued_count: 2,
        missing_count: 0, unknown_count: 0 },
      { character_id: 3, character_name: 'Kaska Rin',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Training',
        estimated_finish_utc: '', queue_timing_unknown: true,
        active_count: 13, trained_inactive_count: 0, queued_count: 1,
        missing_count: 0, unknown_count: 0 },
      { character_id: 4, character_name: 'Delen Vok',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Locked',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 11, trained_inactive_count: 3, queued_count: 0,
        missing_count: 0, unknown_count: 0 },
      { character_id: 5, character_name: 'Gustav Oswaldo',
        fetched_utc: '2026-08-23T20:00:00+00:00',
        fetched_label: 'Last fetched 17h ago',
        error: 'ESI returned 503', needs_reauth: false, stale: true,
        readiness: 'Missing', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 8, trained_inactive_count: 0, queued_count: 0,
        missing_count: 6, unknown_count: 0 },
      { character_id: 6, character_name: 'Nera Tal',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Missing',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 12, trained_inactive_count: 0, queued_count: 0,
        missing_count: 2, unknown_count: 0 },
      { character_id: 7, character_name: 'Orin Kesh',
        fetched_utc: '2026-08-24T08:00:00+00:00',
        fetched_label: 'Last fetched 5h ago', error: '',
        needs_reauth: false, stale: false, readiness: 'Unknown',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 13, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 1 },
      { character_id: 8, character_name: 'Tavi Solen', fetched_utc: '',
        fetched_label: 'Never fetched',
        error: 'The refresh token was rejected', needs_reauth: true,
        stale: false, readiness: 'Unscored', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 0, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0 },
      { character_id: 9, character_name: 'Mira Halcyon', fetched_utc: '',
        fetched_label: 'Never fetched',
        error: '', needs_reauth: false, stale: false,
        readiness: 'Ascendant', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 0, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0 }
    ],
    plan_issues: [
      { file_name: 'Broken.txt', message: 'The file was rejected.',
        diagnostics: [{ line: 4, message: 'Missing a level' },
                      { line: 0, message: 'No requirements were parsed' }] }
    ],
    warnings: [],
    plans_updated_utc: '2026-08-24T08:00:00+00:00'
  };

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
        ? ids.length + ' selected \u00b7 1.4 GB \u00b7 0:12:31'
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
          channel_id: 'UC123', channel_title: 'FlyGD' }, patch || {}),
      webhook_status: statusLine === undefined
        ? 'webhook 1538615213203656754 in #combat-logs' : statusLine,
      detected: { recording: 'D:\\Videos',
                  gamelogs: 'C:\\Users\\tng\\Documents\\EVE\\logs\\Gamelogs' },
      destination: 'Uploads go to FlyGD \u00b7 unlisted',
      // Python sends this from __version__; the double carries a value
      // of the same SHAPE and not the real one, so a stale fake cannot
      // be mistaken for the app agreeing with itself.
      version: '0.0.0-dev'
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

  api.list_rows = function () {
    console.log('DEV api.list_rows()');
    setTimeout(function () {
      window.onRows({ rows: [
        { id: 'r1', name: '2026-08-21 19-04-11.mkv', date: 'Aug 21  19:04',
          size: '1.4 GB', duration: '12:31', link: null, preselected: true },
        { id: 'r2', name: '2026-08-21 17-58-02.mkv', date: 'Aug 21  17:58',
          size: '812.0 MB', duration: '\u2026', link: null, preselected: false },
        { id: 'r3', name: '2026-08-20 22-10-49.mkv', date: 'Aug 20  22:10',
          size: '2.1 GB', duration: '?', link: null, preselected: false },
        { id: 'r4', name: '2026-08-19 21-00-03.mkv', date: 'Aug 19  21:00',
          size: '640.5 MB', duration: '4:07',
          link: 'https://youtu.be/abc123XYZ', preselected: false }
      ] });
      window.onChannel({ channel_id: 'UC123', channel_title: 'FlyGD',
                         destination: 'Uploads go to FlyGD \u00b7 unlisted' });
      window.onAuthState({ state: 'connected', message: 'Connected' });
      window.onStatus({ text: 'Idle', kind: 'FG' });
    }, 0);
    return Promise.resolve(null);
  };

  // Manual drivers for the pushes no click can produce in a browser.
  // Typed into the devtools console during verification.
  window.DEV = {
    determinate: function (pct) {
      window.onProgress({ mode: 'determinate', pct: pct,
                          text: 'Uploading file 1 of 3\u2026 ' + pct + '%',
                          kind: 'FG' });
    },
    stitching: function () {
      window.onProgress({ mode: 'indeterminate', pct: 0,
                          text: 'Stitching with FFmpeg\u2026', kind: 'FG' });
    },
    status: function (text, kind) {
      window.onStatus({ text: text, kind: kind });
    },
    retry: function (available) {
      window.onRetryAvailable({ available: available });
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
    skillsEmpty: function () {
      skills.characters = [];
      skills.plans = [];
      skills.selected_plan_name = '';
      window.onSkills(skills);
    }
  };

  window.pywebview = { api: api };
  window.dispatchEvent(new Event('pywebviewready'));
}());
