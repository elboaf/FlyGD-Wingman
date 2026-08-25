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
   'set_discord_webhook', 'clear_discord_webhook',
   'set_alert_enabled', 'set_alert_pve_filter', 'set_alert_persist',
   // M3. Same three-key shape, and it belongs in this list rather than the
   // generic one for the same reason: the ABOUT card reverts its checkbox
   // on anything that is not `applied`.
   'set_start_on_login'
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

  // Same tier as the block above: set_alert_event and test_alert both
  // return {applied, persisted, error} and the page reads all three.
  api.set_alert_event = function (event, field, value) {
    console.log('DEV api.set_alert_event(', event, field, value, ')');
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
            alerts: { enabled: true, pve_filter: true,
              persist_until_selected: true,
              events: {
                combat: { enabled: true, cooldown_s: 1, duration_ms: 1200,
                  pulses: 3, color: '#ff4d4d', sound: 'chime' },
                warp_scramble: { enabled: true, cooldown_s: 8,
                  duration_ms: 1200, pulses: 3, color: '#ffd24d',
                  sound: 'bell' },
                decloak: { enabled: true, cooldown_s: 8, duration_ms: 1200,
                  pulses: 3, color: '#4dd2ff', sound: 'chime' }
              }
            }
          }
        }, patch || {}),
      webhook_status: statusLine === undefined
        ? 'webhook 1538615213203656754 in #combat-logs' : statusLine,
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
      windows: ['EVE - Aiga Otsolen', 'EVE - Zuelo Parvi'],
      // Keyed by the parsed AHK string, valued with every bind id claiming
      // it -- bookmarks.collisions() only returns entries of length > 1.
      collisions: { '^+1': ['Fin1', 'Fin2'] },
      displays: {
        ConvertScout: 'Ctrl+Shift+S', SetRoot: 'Ctrl+Shift+R',
        GrabSig: 'Ctrl+Shift+G', Fin1: 'Ctrl+Shift+1',
        Fin2: 'Ctrl+Shift+1'
      },
      engine: { state: 'on', last_error: null, blockers: [] }
    });
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
    // `enabled: false`, and everything downstream of it honest about that.
    // The real method gates on `host.is_running`, so a stopped host
    // returns characters [] and registration {} -- there is no state in
    // which previews are off and Windows is holding chords. A fixture
    // showing registered chords beside an unticked Enable box would be
    // more complete than the thing it doubles, which is how a harness
    // starts hiding the bug it exists to catch. Off is also what the
    // settings payload says, since it carries no `preview` key at all.
    //
    // The rows are therefore the offline kind: bound characters whose
    // client is not running, which is a real and under-looked-at state --
    // the binding is saved and works the moment they log in.
    return Promise.resolve({
      enabled: false,
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
      roster: ['Aiga Otsolen', 'Zuelo Parvi', 'Kaska Rin'],
      characters: [],
      registration: {},
      // Latent rather than active, for the same consistency: bookmarks
      // register nothing while this chord could still be taken later.
      bookmark_chords: { active: [], latent: ['Ctrl+Alt+1'] }
    });
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
    determinate: function (pct) {
      window.onProgress({ mode: 'determinate', pct: pct,
                          text: 'Uploading file 1 of 3\u2026 ' + pct + '%',
                          kind: 'FG', busy: true });
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
    characters: eveNames.map(function (name, i) {
      return { path: 'c' + i, id: String(90000000 + i), name: name };
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
