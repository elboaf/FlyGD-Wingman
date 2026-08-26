/* FlyGD Wingman — the Skills route.
 *
 * Answers one question: who can fly this plan? Every judgement that
 * produces that answer -- readiness precedence, ETA, requirement state --
 * happens in Python's evaluator, because this repo has no way to test
 * JavaScript (docs/history/webview-replatform-design.md:545). This file
 * groups, sorts, filters, and renders what Python already decided.
 *
 * The one derived value here is the plan rail's ready RATIO: Python sends
 * each plan's ready_count, and the denominator is characters.length, which
 * the page already holds.
 *
 * buildRoster() groups characters by readiness (see the lockout guard
 * comment on that function); the roster, its in-row expansion, and the
 * two-step forget confirm are what everything else here builds toward.
 */
(function () {
  'use strict';
  var WM = window.WM;

  var STATE = null;       // last onSkills payload, whole
  var progress = null;    // last onSkillsProgress, cleared when a refresh ends
  var expanded = {};      // character_id -> true
  var details = {};       // character_id -> character_detail() payload
  var pendingDetail = {}; // character_id -> in-flight request id
  var detailSeq = 0;
  var confirming = 0;     // character_id whose Forget is awaiting confirmation
  var filterText = '';
  var asked = false;      // has the page asked Python for state yet
  var autoExpanded = false; // has the one-shot small-roster expansion run

  /* S1. The expanded row is the ONLY surface in the whole application for
   * forgetting a character or re-authenticating it (see THE LOCKOUT GUARD
   * below), and it opened behind a chevron on a screen with ~900 CSS px of
   * void under it. Rows still LOAD collapsed in the markup sense -- this
   * expands them once, on the first payload that carries anyone -- so
   * nothing about the disclosure or the toggle changes; what changes is
   * the state the screen is first seen in.
   *
   * THE CAP IS ABOUT COST AND CONSENT, NOT ABOUT FIT. One expanded row can
   * be thirty-six requirement lines, so no cap makes the pane "fit"; what
   * a cap decides is how many detail evaluations the page orders on entry
   * without being asked. requestDetail's own note states the ceiling it
   * was written against -- "a forty-character roster asking for forty
   * requirement lists on entry would evaluate thirty-nine plans nobody
   * opened" -- and that reasoning is about FETCH COST and is untouched
   * here: at or below this cap the cost is a handful of in-process round
   * trips, and above it the user is running a fleet-sized roster and did
   * not ask for a fleet-sized evaluation.
   *
   * Six because six is this app's existing answer to "how many is a
   * handful": ui/copy.py's _COPY_NAME_CAP names six targets in the copy
   * confirm and then counts the rest, reasoning that past a handful a list
   * stops being read as a list. That is a DIFFERENT question -- how many
   * names a reader will check -- so this is a precedent for the size of
   * the word, not a derived value, and the two are free to move apart. If
   * this one moves, docs/smoke-checklist.md states it too and
   * tests/test_skills_page.py asserts the pair.
   *
   * One-shot, and armed by the first NON-EMPTY payload: a roster that
   * arrives empty (before the first refresh answers) has nothing to
   * expand, and re-running this on every push would re-open every row the
   * user has since collapsed. */
  var AUTO_EXPAND_MAX = 6;

  function autoExpand() {
    if (autoExpanded) return;
    var chars = characters();
    if (!chars.length) return;
    autoExpanded = true;
    if (chars.length > AUTO_EXPAND_MAX) return;
    chars.forEach(function (ch) { expanded[ch.character_id] = true; });
  }

  function characters() { return (STATE && STATE.characters) || []; }
  function plans() { return (STATE && STATE.plans) || []; }
  function groups() { return (STATE && STATE.groups) || []; }
  function selectedGroup() { return (STATE && STATE.selected_group) || ''; }

  function render(payload) {
    if (!payload) return;
    STATE = payload;
    // Every cached detail was computed from the PREVIOUS onSkills payload's
    // character/plan data, and a fresh payload means a character's skills,
    // training queue, or requirement scoring may have just changed --
    // periodic refresh, a completed re-authentication, a forgotten and
    // re-added character reusing an id. That data IS stale and must not be
    // trusted once a refresh finishes, but onSkills is pushed once PER
    // CHARACTER during _refresh_pass (controller.py:614), not once per
    // refresh -- every commit stamps fetched_utc, so the payload-level
    // dedupe never applies here. Wiping `details` on every one of those N
    // pushes, as this used to, made every expanded row flip to "Loading
    // requirements…" and back N times over a single refresh. Instead, keep
    // the stale detail on screen and force a fresh request per still-open
    // row; requestDetail's token check already drops any reply that is no
    // longer the latest one asked for, so the row ends up showing exactly
    // the detail for the LAST of these pushes once everything settles --
    // it just does not go blank on the way there.
    //
    // Progress lines describe a refresh in flight. onSkills is pushed on
    // BOTH the success and failure paths of every mutation, so the end of
    // a refresh always arrives here -- which is what stops "Refreshed 3 of
    // 7 characters" sitting on screen forever after a failure.
    if (!payload.refresh_in_flight) progress = null;
    // Before the renders, so the roster is BUILT open rather than drawn
    // shut and reopened, and before the requestDetail loop at the foot of
    // this function, which is what fetches the details these rows now
    // need -- no second fetch path.
    autoExpand();
    renderRail();
    renderHead();
    renderNotices();
    renderIssues();
    renderRoster();
    Object.keys(expanded).forEach(function (id) {
      requestDetail(parseInt(id, 10), true);
    });
  }

  WM.handle('onSkills', render);

  document.addEventListener('wm:route', function (event) {
    if (event.detail !== 'skills') return;
    // The page asks; Python does not push unprompted at boot. Same rule
    // app.js:139-148 follows for rows and settings -- a subsystem that
    // costs nothing until you open it cannot be pushing state at launch.
    // Asked on FIRST entry only: after that every mutation pushes onSkills,
    // so re-asking on each entry would be a redundant round trip carrying
    // the largest payload in the app.
    if (asked) return;
    asked = true;
    WM.send('skills_state').then(function (payload) {
      // A null/undefined reply means the request itself failed rather
      // than answering with an empty state -- render() already no-ops on
      // that, but leaving `asked` set would make every later route entry
      // believe the initial ask already happened and skip retrying it
      // forever, stranding the page with no state at all.
      if (!payload) asked = false;
      render(payload);
    });
  });

  // ---- left rail ------------------------------------------------------
  /* The ready COUNT used to be part of this line ("2 characters - 0
   * ready") and is deliberately gone. It was scoped to the selected plan,
   * because `readiness` is, but it sits above `Add character` and detached
   * from the plan list, where the only available reading is "0 of your 2
   * characters are ready" -- a roster statement the plan list contradicts
   * four rows down, where the selected plan's own ratio says otherwise.
   *
   * It was also the third copy of one number. The same fact is already
   * under the READY column header beside the plan it belongs to, and again
   * in the roster's `Ready N` group head, both of which say what they are
   * counting. This line now says only the thing that IS roster-scoped. */
  /* S3. This line and the roster's group heads both rendered the bare
   * words `3 characters`, 200 CSS px apart in two panes, counting two
   * different sets: this one is the whole roster, that one is how many
   * are Ready (or Missing, or Training). The group head is scoped by the
   * group name printed immediately left of it; this one had nothing
   * beside it, so it is the one that says what it counts. `added` is the
   * scope AND the verb of the button directly under it, `Add character`.
   *
   * The rule the two comments at groupNode() and statusLine() establish is
   * unchanged and is why the noun stays: every number on this screen
   * carries the noun it counts. This adds the scope that noun was missing.
   */
  function renderRail() {
    var chars = characters();
    WM.el('skills-counts').textContent = chars.length
      ? chars.length + (chars.length === 1 ? ' character added'
                                           : ' characters added')
      : 'No characters yet';

    renderRailButtons();
    renderPlans();
    renderGroups();
  }

  function renderPlans() {
    var host = WM.el('skills-plans');
    host.textContent = '';
    var list = plans();
    if (!list.length) {
      host.appendChild(WM.make('p', 'hint', 'No plans found.'));
      return;
    }
    var total = characters().length;
    var selected = (STATE.selected_plan_name || '').toLowerCase();
    list.forEach(function (plan) {
      var row = WM.make('button', 'rail-plan');
      if ((plan.name || '').toLowerCase() === selected) {
        row.classList.add('active');
      }
      row.appendChild(WM.make('span', 'rail-plan-name', plan.name));
      // The numerator is Python's ready_count for this plan; the
      // denominator is simply how many characters exist, which the page
      // already holds. Deriving the ratio here rather than sending a
      // formatted string keeps the payload keys plain numbers.
      row.appendChild(WM.make('span', 'rail-ratio',
                              plan.ready_count + '/' + total));
      // Both numbers spelled out, because the bare ratio counts CHARACTERS
      // while the pane header two inches to its right counts the plan's
      // SKILLS -- "3/12" beside "12 requirements". The .rail-head-key
      // column header carries the short version for someone scanning; this
      // is for someone who stopped on one row to check.
      row.title = plan.name + ' — ' + plan.ready_count + ' of ' + total
        + (total === 1 ? ' character is ready' : ' characters are ready');
      row.addEventListener('click', function () { selectPlan(plan.name); });
      host.appendChild(row);
    });
  }

  function selectPlan(name) {
    if (!STATE || name === STATE.selected_plan_name) return;
    // Every cached detail was computed against the OLD plan and is now
    // answering a question nobody asked. Dropping pendingDetail as well is
    // what makes the in-flight replies land in requestDetail's mismatch
    // branch and be discarded rather than rendered under the new plan.
    details = {};
    pendingDetail = {};
    WM.send('skills_select_plan', name).then(function (ok) {
      // `!ok` rather than `=== false`: WM.send resolves to null on any
      // bridge failure (app.js:38-43), and select_plan returns True even
      // for a no-op precisely so the page can tell the two apart
      // (ui/api.py's convention). Either way the push re-syncs us, so
      // there is nothing to do but re-request the open rows.
      if (!ok) return;
      Object.keys(expanded).forEach(function (id) {
        requestDetail(parseInt(id, 10));
      });
    });
  }

  /* `All` is a selection, not a group: it is how you stop scoping, and it
   * carries the whole roster's count so the rail states the denominator
   * the ratios below it are using. Rename and delete are disabled while it
   * is current, per the control vocabulary's disabled-when-the-object-is-
   * absent rule -- there is no object to rename. */
  function renderGroups() {
    var host = WM.el('skills-groups');
    host.textContent = '';
    var current = selectedGroup();

    var all = WM.make('button', 'rail-plan');
    if (!current) all.classList.add('active');
    all.appendChild(WM.make('span', 'rail-plan-name', 'All'));
    all.appendChild(WM.make('span', 'rail-ratio',
                            String(characters().length)));
    all.addEventListener('click', function () { selectGroup(''); });
    host.appendChild(all);

    groups().forEach(function (group) {
      var row = WM.make('button', 'rail-plan');
      if (group.name.toLowerCase() === current.toLowerCase()) {
        row.classList.add('active');
      }
      row.appendChild(WM.make('span', 'rail-plan-name', group.name));
      row.appendChild(WM.make('span', 'rail-ratio',
                              String(group.member_count)));
      row.addEventListener('click', function () { selectGroup(group.name); });
      host.appendChild(row);
    });

    WM.el('skills-rename-group').disabled = !current;
    WM.el('skills-delete-group').disabled = !current;
  }

  function selectGroup(name) {
    if (name.toLowerCase() === selectedGroup().toLowerCase()) return;
    // Optimistic, then corrected by the push: the same shape selectPlan
    // uses. Python is the only writer, so a refusal re-renders from truth.
    WM.send('skills_select_group', name);
  }

  function renderRailButtons() {
    var add = WM.el('skills-add');
    var refresh = WM.el('skills-refresh');
    // Auth is unconfigured when application.py still holds the placeholder
    // client id -- a source checkout of a fork that has not registered its
    // own EVE application. Disabling with a reason beats a button that
    // opens a browser to an OAuth error.
    add.disabled = !STATE.auth_configured;
    add.title = STATE.auth_configured ? ''
      : 'This build has no EVE application id configured.';
    add.textContent = STATE.auth_in_progress
      ? 'Cancel sign-in' : 'Add character';
    refresh.textContent = STATE.refresh_in_flight
      ? 'Refreshing…' : 'Refresh characters';
    refresh.disabled = STATE.refresh_in_flight || !characters().length;
  }

  WM.el('skills-add').addEventListener('click', function () {
    if (!STATE) return;
    WM.send(STATE.auth_in_progress
            ? 'skills_cancel_auth' : 'skills_add_character');
  });

  WM.el('skills-refresh').addEventListener('click', function () {
    WM.send('skills_refresh');
  });

  WM.el('skills-open-folder').addEventListener('click', function () {
    WM.send('skills_open_plans_folder');
  });

  WM.el('skills-reload-plans').addEventListener('click', function () {
    // A reload can change which plan names exist, so the cached details
    // are no more trustworthy than after a plan switch.
    details = {};
    pendingDetail = {};
    WM.send('skills_reload_plans');
  });

  // None of the four button handlers above inspect the return value.
  // Every one is a mutation, and a mutation pushes onSkills on both its
  // success and failure paths -- the push is the answer, and acting on
  // the return as well would render the same state twice.

  // ---- main pane header ------------------------------------------------
  function renderHead() {
    var name = STATE.selected_plan_name || '';
    WM.el('skills-plan-name').textContent = name || 'No plan selected';
    var count = 0;
    plans().forEach(function (plan) {
      if ((plan.name || '').toLowerCase() === name.toLowerCase()) {
        count = plan.requirement_count;
      }
    });
    WM.el('skills-plan-count').textContent = name
      ? count + (count === 1 ? ' requirement' : ' requirements') : '';
    // The object of this action is the plan, so with no plan selected
    // there is nothing to copy and the control says so by being disabled
    // rather than by failing when pressed.
    var copy = WM.el('skills-copy-plan');
    copy.disabled = !name;
    copy.title = name
      ? 'Copies every skill in “' + name + '” for EVE\u2019s skill plan '
        + 'import. The game drops the ones already trained.'
      : '';
  }

  WM.el('skills-copy-plan').addEventListener('click', function () {
    var name = (STATE && STATE.selected_plan_name) || '';
    if (!name) return;
    // Python returns the text and the page owns the clipboard write, the
    // same split list.js:396-401 uses for `Copy link`: with Tk gone there
    // is no toolkit clipboard and navigator.clipboard is right here.
    // Python has already put the outcome on the status strip either way --
    // "" is a plan the last reload invalidated, not an empty plan, because
    // plans.parse rejects a file with no requirements.
    WM.send('skills_plan_text', name).then(function (text) {
      if (text) navigator.clipboard.writeText(text);
    });
  });

  function renderNotices() {
    var host = WM.el('skills-notices');
    host.textContent = '';
    var lines = [];
    if (STATE.auth_in_progress) {
      lines.push('Waiting for EVE SSO…');
    }
    if (progress && progress.total) {
      lines.push('Refreshed ' + progress.completed + ' of '
                 + progress.total + ' characters');
    }
    (STATE.warnings || []).forEach(function (text) { lines.push(text); });
    host.hidden = !lines.length;
    lines.forEach(function (text) {
      host.appendChild(WM.make('p', 'notice', text));
    });
  }

  WM.handle('onSkillsProgress', function (payload) {
    progress = payload;
    // Only the strip moves. A progress tick during a forty-character
    // refresh must not rebuild forty rows and collapse the one the user is
    // reading -- and it carries nothing the roster renders anyway.
    renderNotices();
  });

  function renderIssues() {
    var host = WM.el('skills-issues');
    var issues = STATE.plan_issues || [];
    host.hidden = !issues.length;
    if (!issues.length) return;
    WM.el('skills-issues-summary').textContent =
      issues.length + (issues.length === 1
                       ? ' plan file has problems' : ' plan files have problems');
    var body = WM.el('skills-issues-body');
    body.textContent = '';
    issues.forEach(function (issue) {
      body.appendChild(WM.make('p', 'issue-file', issue.file_name));
      body.appendChild(WM.make('p', 'issue-message', issue.message));
      (issue.diagnostics || []).forEach(function (diag) {
        // Line 0 is the contract's whole-file diagnostic (plans.py's
        // Diagnostic docs it), so it must not print as "line 0".
        body.appendChild(WM.make(
          'p', 'issue-line',
          diag.line ? 'Line ' + diag.line + ': ' + diag.message
                    : diag.message));
      });
    });
  }
  // Collapsed by default because <details> is: a plan file with a typo is
  // worth surfacing, not worth pushing the roster down the page.

  // ---- the roster ------------------------------------------------------
  // Group order is fixed and matches evaluator.READINESS_ORDER, with a
  // trailing catch-all. OTHER is not in that list on purpose: it exists to
  // catch a readiness string this page has never heard of.
  var GROUPS = ['Ready', 'Training', 'Locked', 'Missing', 'Unknown',
                'Unscored'];
  var OTHER = 'Other';

  // 'Unscored' is deliberately CAUSE-NEUTRAL. It was 'Not yet refreshed',
  // which named one cause and pointed at the Refresh button -- but an
  // empty or broken plans folder puts EVERY character in this group (see
  // the lockout guard below), and then the label is simply false and sends
  // the user to the wrong control. The cause is already stated where it is
  // known: renderRoster's hint says "No local plans yet" beside the roster,
  // and a per-character failure states itself in the expanded row.
  //
  // 'Unknown' was 'Unknown skills', and the word was doing two jobs one
  // above the other: this GROUP header counts CHARACTERS whose worst
  // requirement was never injected, while the rows inside it labelled a
  // REQUIREMENT in that state. Worse, "unknown" attaches in English to the
  // speaker rather than the subject -- "unknown to us" -- so a correct
  // statement about the character read as the app failing to look
  // something up. It is now stated the way the readiness is derived, in
  // the same shape as the `Missing requirements` group beside it.
  var GROUP_LABEL = {
    Ready: 'Ready', Training: 'Training', Locked: 'Locked',
    Missing: 'Missing requirements', Unknown: 'Untrained requirements',
    Unscored: 'Not scored yet', Other: 'Unrecognised'
  };

  /* THE LOCKOUT GUARD.
   *
   * This iterates CHARACTERS and selects a group for each one. It must
   * NEVER enumerate the readiness groups and pull matching characters out
   * of them -- the trailing OTHER bucket exists so that a readiness string
   * this page does not recognise still produces a row.
   *
   * That is not tidiness. The expanded row is the ONLY surface in the
   * whole application for forgetting a character or re-authenticating it,
   * so a character with no row is a character that cannot be repaired --
   * not from here, not from Settings, not from anywhere but deleting
   * eve_skills.json by hand.
   *
   * And the group most likely to be affected is the most common one:
   * "Unscored" is the state of EVERY character between authorisation and
   * its first successful refresh, and of every character whose first
   * refresh failed. A roster driven by enumerating known groups would
   * strand exactly the characters most likely to need repair -- the ones
   * that just failed to authenticate.
   *
   * The same guard applies one level up, in renderRoster: a populated
   * roster with a broken or empty plans folder must still call
   * buildRoster and render every character's row. Returning early to show
   * only the "no plans" hint -- as this used to do -- silently applies
   * the same lockout from a different angle: every character reads as
   * Unscored (there is nothing to score against), which is not a reason
   * to withhold the one place that state can be fixed from.
   */
  function buildRoster(chars) {
    var buckets = {};
    GROUPS.forEach(function (name) { buckets[name] = []; });
    buckets[OTHER] = [];

    chars.forEach(function (ch) {
      var key = GROUPS.indexOf(ch.readiness) === -1 ? OTHER : ch.readiness;
      buckets[key].push(ch);
    });

    var order = GROUPS.concat([OTHER]);
    var groups = [];
    order.forEach(function (name) {
      var rows = buckets[name];
      if (!rows.length) return;          // empty groups are omitted
      rows.sort(name === 'Missing' ? byMissingThenName : byName);
      groups.push({ name: name, rows: rows });
    });
    return groups;
  }

  function byName(a, b) {
    return (a.character_name || '').toLowerCase()
      .localeCompare((b.character_name || '').toLowerCase());
  }

  // Fewest missing first. This is the whole surviving remnant of
  // TriffView's "Train next" tab: the tab never shipped, but the ordering
  // it existed to provide did, as the sort inside this one group.
  function byMissingThenName(a, b) {
    if (a.missing_count !== b.missing_count) {
      return a.missing_count - b.missing_count;
    }
    return byName(a, b);
  }

  /* THE ROW MAY NOT RESTATE ITS GROUP HEADER. S2, and the rows are
   * grouped BY STATUS, so by construction the status column could not say
   * anything the header above it had not already said: `Ready 2` over two
   * rows each reading `Ready`, `Untrained requirements` over three rows
   * each reading `Not trained`. Each state was stated three times -- the
   * swatch, the group name, the row -- and the maintainer volunteered the
   * screen had "some unneeded text" before seeing any of this analysis.
   *
   * What is left is only what the header CANNOT carry, because it varies
   * per character inside one group:
   *
   *   Missing    how many requirements -- and it carries its noun, which
   *              is the other half of S1. `Missing 2` under a header
   *              reading `Missing requirements` was the collision; `2
   *              requirements` under it is not. The number also explains
   *              the group's own sort (byMissingThenName, fewest first).
   *   Training   the ETA, which is the answer someone came here for. The
   *              word `Training` in front of it was the header's.
   *   Other      the raw readiness string. NOT a restatement: the
   *              catch-all header says `Unrecognised` for every row in
   *              it, so the string that put a character there is stated
   *              nowhere else. Same reasoning as the OTHER bucket itself.
   *
   * Everything else returns "" and the row is a name under a heading.
   * That also retires one of the three `Ready`s round 2's finding 3 was
   * left with, and it is what let the roster narrow (S8 sizes the list to
   * its widest row).
   *
   * "timing unknown" is a real state, not a fallback: a queued
   * requirement with no finish date means EVE reported a paused queue,
   * and claiming an ETA from the rest would be a guess.
   */
  function statusLine(ch) {
    if (ch.readiness === 'Training') {
      var eta = formatEta(ch.estimated_finish_utc);
      return (ch.queue_timing_unknown || !eta) ? 'timing unknown' : eta;
    }
    if (ch.readiness === 'Missing') {
      return ch.missing_count
        + (ch.missing_count === 1 ? ' requirement' : ' requirements');
    }
    if (GROUPS.indexOf(ch.readiness) !== -1) return '';
    return ch.readiness || '';
  }

  // "2d 4h", "4h 20m", "12m". Two units at most: a plan finishing in
  // eleven days does not want its minutes.
  function formatEta(iso) {
    if (!iso) return '';
    var finish = Date.parse(iso);
    if (isNaN(finish)) return '';
    var mins = Math.round((finish - Date.now()) / 60000);
    // A finish date already in the past means the queue completed since
    // the snapshot was taken. "Due" is honest; a negative duration is not.
    if (mins <= 0) return 'due';
    var days = Math.floor(mins / 1440);
    var hours = Math.floor((mins % 1440) / 60);
    if (days) return days + 'd ' + hours + 'h';
    if (hours) return hours + 'h ' + (mins % 60) + 'm';
    return mins + 'm';
  }

  function matching() {
    var needle = filterText.trim().toLowerCase();
    if (!needle) return characters();
    return characters().filter(function (ch) {
      return (ch.character_name || '').toLowerCase().indexOf(needle) !== -1;
    });
  }

  function renderRoster() {
    var host = WM.el('skills-roster');
    var empty = WM.el('skills-empty');
    host.textContent = '';
    empty.textContent = '';
    WM.el('skills-filter-clear').hidden = !filterText.trim();

    if (!characters().length) {
      empty.hidden = false;
      // Names the control rather than where it is: "the actions on the
      // left" is a location the rail is narrow enough to be scanned past,
      // and PRODUCT.md's rule is to name things the way the user does --
      // the button says "Add character", so this does too.
      empty.textContent =
        'No characters yet. Press “Add character” to sign one in with '
        + 'EVE SSO.';
      return;
    }

    var rows = matching();
    // The plans-empty and no-match hints are shown BESIDE the roster, never
    // instead of it -- see THE LOCKOUT GUARD above buildRoster. A missing
    // or empty plans folder changes what every character's readiness IS
    // (Unscored, most likely), it does not change whether that character
    // gets a row: the row is still the only surface for forgetting it or
    // re-authenticating it, and a character stuck at Unscored because the
    // plans folder is empty needs that surface just as much as any other.
    var hint = '';
    if (!plans().length) {
      hint = 'No local plans yet. Drop a .txt plan in the plans folder, '
        + 'then reload.';
    } else if (!rows.length) {
      // The clear action is already visible (it is shown whenever a filter
      // is active), so this line does not repeat it as a button.
      hint = 'No characters match “' + filterText.trim() + '”.';
    }
    empty.hidden = !hint;
    empty.textContent = hint;

    buildRoster(rows).forEach(function (group) {
      host.appendChild(groupNode(group));
    });
  }

  function groupNode(group) {
    var block = WM.make('div', 'skills-group');
    var head = WM.make('div', 'skills-group-head');
    head.appendChild(WM.make('span', 'skills-key key-' + group.name));
    head.appendChild(WM.make('span', 'skills-group-name',
                             GROUP_LABEL[group.name] || group.name));
    // S1. The number counts CHARACTERS while the header beside it names
    // REQUIREMENTS -- `Missing requirements 1` sat 34 CSS px above a row
    // reading `Missing 2`, the same word with adjacent numbers counting
    // different nouns, under a plan heading stating a third number in the
    // same vocabulary (`14 requirements`). Round 2's finding 2 renamed the
    // vocabulary and the mismatch survived the rename, so the fix this
    // time is on the NUMBERS: every one on this screen now carries the
    // noun it counts, and the row half of the same finding is at
    // statusLine() below.
    var count = group.rows.length;
    head.appendChild(WM.make('span', 'skills-group-count',
                             count + (count === 1 ? ' character'
                                                  : ' characters')));
    block.appendChild(head);
    group.rows.forEach(function (ch) { block.appendChild(rowNode(ch)); });
    return block;
  }

  WM.el('skills-filter').addEventListener('input', function () {
    filterText = WM.el('skills-filter').value;
    renderRoster();
  });

  WM.el('skills-filter-clear').addEventListener('click', function () {
    WM.el('skills-filter').value = '';
    filterText = '';
    renderRoster();
  });

  function rowNode(ch) {
    var row = WM.make('div', 'skills-row');
    if (expanded[ch.character_id]) row.classList.add('open');

    var top = WM.make('button', 'skills-row-top');
    // The other half of S1: the chevron is the whole disclosure, and a
    // glyph is not a name. settings.js:349 states the same state on its
    // reveal toggle with aria-pressed; this one is a disclosure, so it is
    // aria-expanded. Nothing visible changes -- the row already carries
    // the character's name, which is the label this control wants.
    top.setAttribute('aria-expanded', expanded[ch.character_id] ? 'true'
                                                                : 'false');
    top.appendChild(WM.make('span', 'chev',
                            expanded[ch.character_id] ? '▾' : '▸'));
    top.appendChild(WM.make('span', 'skills-name', ch.character_name
                                                   || String(ch.character_id)));
    // EXCEPTION-ONLY, and this is the considered half of it: an earlier
    // draft carried a per-row "Current" label beside this one. In the
    // common case every row had one, which is noise -- a badge that is
    // always present tells you nothing. Stale is worth a badge precisely
    // because it is rare.
    if (ch.stale) {
      var badge = WM.make('span', 'badge-stale', 'Stale');
      badge.title = 'You are looking at the last data that fetched '
        + 'successfully. The most recent refresh failed.';
      top.appendChild(badge);
    }
    // Appended only when it says something. An empty span still costs the
    // row's 9px flex gap, and on the four groups whose rows now carry no
    // status at all that is a gap after the last thing on the line.
    var status = statusLine(ch);
    if (status) {
      top.appendChild(
        WM.make('span', 'skills-status status-' + ch.readiness, status));
    }
    top.addEventListener('click', function () { toggle(ch.character_id); });
    row.appendChild(top);

    if (expanded[ch.character_id]) row.appendChild(detailNode(ch));
    return row;
  }

  function toggle(id) {
    if (expanded[id]) {
      delete expanded[id];
      // Collapsing abandons a half-typed confirmation. Leaving it armed
      // would mean re-opening the row a minute later shows a Forget button
      // already primed to fire on one click.
      if (confirming === id) confirming = 0;
    } else {
      expanded[id] = true;
      requestDetail(id);
    }
    renderRoster();
  }

  /* Details are requested lazily -- one call per expansion, never a
   * prefetch. A forty-character roster asking for forty requirement lists
   * on entry would evaluate thirty-nine plans nobody opened.
   *
   * `force` bypasses the "already have it" guard for a row that IS already
   * expanded but whose detail is now stale (render()'s per-push
   * re-request); a bare call from toggle() never needs it, since expanding
   * a row that has no cached detail already falls through the guard.
   *
   * The request id is what makes the reply safe to render. A plan switch
   * clears `details` and `pendingDetail` while a call is in flight, and
   * that reply describes the OLD plan -- rendering it would put the wrong
   * requirement list under an open row, with nothing on screen to say so.
   * A cleared or superseded entry no longer matches, so the reply is
   * dropped. The same check is what makes `force` safe against a refresh
   * that pushes several times in a row: only the reply to the LAST call
   * for a given id ever matches its token, so an intermediate reply from
   * an earlier, now-superseded push is discarded rather than briefly
   * flashing on screen before the final one overwrites it.
   */
  function requestDetail(id, force) {
    if (details[id] && !force) return;
    detailSeq += 1;
    var token = detailSeq;
    pendingDetail[id] = token;
    var plan = (STATE && STATE.selected_plan_name) || '';
    WM.send('skills_character_detail', id, plan).then(function (payload) {
      if (pendingDetail[id] !== token) return;
      delete pendingDetail[id];
      // A null is a bridge failure, not an answer (app.js:38-43). The row
      // must say something rather than sit on "Loading requirements…"
      // forever.
      details[id] = payload || {
        ok: false, message: 'The requirement list could not be loaded.',
        requirements: []
      };
      renderRoster();
    });
  }

  /* S6/D3. `Never fetched` was printed above rows stating queue timing
   * for the same character, which cannot both be true, and the maintainer
   * reported not knowing what the string meant.
   *
   * The contradiction was a BRIDGE BUG, not a state: `fetched_label` is
   * built in ui/api.py and, until D3's fix, only the skills_state METHOD
   * applied it. The page asks for state on first entry only (see the
   * wm:route handler above), so every render after the first push arrived
   * with no such key and this line's own `|| 'Never fetched'` invented the
   * fact. The fallback is gone with it: an absent label is a label we do
   * not have, not a claim about history. Python's own "Never fetched" is
   * still rendered, because when Python says it, it is true.
   *
   * The second half of S6 survives that fix and is the branch below.
   * `Never fetched` on its own explained nothing and had no affordance
   * beside it -- `Refresh characters` is ~700 CSS px away in the rail, with
   * nothing connecting them -- and PRODUCT.md obliges Wingman to explain
   * itself. So a character with no snapshot says what is missing, says
   * what would fix it, and carries the control that does.
   *
   * Not shown when the character needs re-authentication: that banner is
   * already at the top of this row, says why there is no data, and offers
   * the only action that can produce any. Two notes stacked would put the
   * one that cannot work first. */
  function fetchedNode(ch) {
    // Null rather than an empty node in both silent cases: .skills-detail
    // is a flex column with an 8px gap, so an empty <p> is a blank line.
    if (ch.fetched_utc) {
      return ch.fetched_label
        ? WM.make('p', 'row-fetched', ch.fetched_label) : null;
    }
    if (ch.needs_reauth) return null;
    var note = WM.make('div', 'row-note');
    note.appendChild(WM.make(
      'span', '',
      'Wingman has not read this character\u2019s skills from EVE yet, so '
      + 'nothing has been scored against this plan.'));
    var now = WM.make('button', 'btn',
                      STATE.refresh_in_flight ? 'Refreshing…'
                                              : 'Refresh characters');
    // The rail's control, in the row that needs it. There is one refresh
    // and it covers every character, so this is deliberately the SAME
    // action under the same name rather than a per-character one the
    // controller does not have.
    now.disabled = STATE.refresh_in_flight;
    now.addEventListener('click', function () { WM.send('skills_refresh'); });
    note.appendChild(now);
    return note;
  }

  function detailNode(ch) {
    var box = WM.make('div', 'skills-detail');

    // The re-authenticate banner comes FIRST: it is the only action that
    // makes any of the rest of this row work again.
    if (ch.needs_reauth) {
      var banner = WM.make('div', 'reauth');
      banner.appendChild(WM.make(
        'span', '',
        'This character needs to sign in to EVE again. Its stored token was '
        + 'rejected and has been removed.'));
      var again = WM.make('button', 'btn', 'Re-authenticate');
      // The same call Add character makes. EVE's own flow is what decides
      // which character comes back, and re-authorising an existing one
      // updates it in place rather than adding a second row.
      again.disabled = !STATE.auth_configured || STATE.auth_in_progress;
      again.addEventListener('click', function () {
        WM.send('skills_add_character');
      });
      banner.appendChild(again);
      box.appendChild(banner);
    }

    if (ch.error) box.appendChild(WM.make('p', 'row-error', ch.error));
    var fetched = fetchedNode(ch);
    if (fetched) box.appendChild(fetched);

    var detail = details[ch.character_id];
    if (!detail) {
      box.appendChild(WM.make('p', 'hint', 'Loading requirements…'));
    } else if (!detail.ok) {
      box.appendChild(WM.make('p', 'row-error',
                              detail.message || 'No requirements available.'));
    } else {
      box.appendChild(requirementsNode(detail));
    }

    box.appendChild(forgetNode(ch));
    return box;
  }

  /* 'Unknown' renders as 'Not trained', and this is the string the whole
   * rename started from: on a character with nothing trained for a plan it
   * appeared seventeen times in twenty-four rows, and reads as seventeen
   * lookup failures rather than seventeen skills the character has never
   * injected. `Missing` is the neighbouring state and means something
   * genuinely different -- the skill IS trained, below the level the plan
   * asks for -- so the two words have to stay distinguishable.
   *
   * The colours these two states get are the other half of the same
   * finding; see .state-Missing / .state-Unknown in style.css. */
  var STATE_LABEL = {
    TrainedInactive: 'Trained, inactive', Queued: 'Queued',
    Missing: 'Missing', Unknown: 'Not trained'
  };

  /* Outstanding requirements arrive in PLAN order, which is the order the
   * user wrote the file in and answers nothing. On a character with 36
   * outstanding rows that interleaves the two actionable states down the
   * whole list, so "what do I train next" -- one of the two questions this
   * screen exists for -- means reading every row.
   *
   * Ordered by what the reader would do about it, not by severity:
   *
   *   Missing         trained, below the level asked for. Nearest to done,
   *                   so it is the cheapest thing to train next.
   *   Not trained     never injected. Actionable, and more work.
   *   Trained, inactive   not a training problem at all -- an inactive
   *                   clone or a lapsed Omega. Fixed somewhere else.
   *   Queued          already being trained. Nothing to decide.
   *
   * Note this is NOT evaluator.READINESS_ORDER, which ranks Unknown WORSE
   * than Missing and is right to: it scores how far a character is from
   * flying the plan. This list answers a different question, and the two
   * orders disagree only between the first two rows, which the colour
   * treats as one bucket anyway.
   *
   * The index tie-break keeps plan order inside each state and does not
   * lean on sort stability. */
  var STATE_RANK = {
    Missing: 0, Unknown: 1, TrainedInactive: 2, Queued: 3
  };

  function stateRank(state) {
    // A state this page has never heard of sorts last rather than
    // vanishing or landing at the top -- same reasoning as the roster's
    // OTHER bucket.
    var rank = STATE_RANK[state];
    return rank === undefined ? 9 : rank;
  }

  function sortByState(reqs) {
    return reqs
      .map(function (req, i) { return { req: req, i: i }; })
      .sort(function (a, b) {
        var ra = stateRank(a.req.state);
        var rb = stateRank(b.req.state);
        return ra === rb ? a.i - b.i : ra - rb;
      })
      .map(function (d) { return d.req; });
  }

  function requirementsNode(detail) {
    var list = WM.make('div', 'req-list');
    // Active requirements are FILTERED OUT. This list answers "what does
    // it still need"; a requirement already met at the active level is not
    // outstanding, and on a nearly-ready character the met ones would bury
    // the two that are not.
    var outstanding = (detail.requirements || []).filter(function (req) {
      return req.state !== 'Active';
    });
    outstanding = sortByState(outstanding);
    if (!outstanding.length) {
      // TWO reasons for an empty list, and they are opposites. A character
      // with no snapshot is Unscored with an EMPTY requirement tuple --
      // evaluator.evaluate returns before it scores anything (its
      // has_snapshot gate) -- so the congratulation below was printed,
      // verbatim, for a character whose skills had never been read. That
      // is the same contradiction S6 reported one line up, from the other
      // side: `Never fetched` above "every requirement is trained and
      // active". Unscored is the ONLY way the evaluator produces an empty
      // list without meaning it, which is what makes readiness the right
      // thing to branch on.
      list.appendChild(WM.make(
        'p', 'hint',
        detail.readiness === 'Unscored'
          ? 'Not scored yet — this character\u2019s skills have not been '
            + 'read from EVE.'
          : 'Nothing outstanding — every requirement is trained and '
            + 'active.'));
      return list;
    }
    outstanding.forEach(function (req) {
      var line = WM.make('div', 'req');
      line.appendChild(WM.make('span', 'req-name',
                               req.skill_name + ' ' + roman(req.required_level)));
      var note = STATE_LABEL[req.state] || req.state;
      if (req.state === 'Queued') {
        var eta = req.queue_timing_unknown ? '' : formatEta(req.queued_finish_utc);
        note = eta ? 'Queued — ' + eta : 'Queued — timing unknown';
      }
      line.appendChild(WM.make('span', 'req-state state-' + req.state, note));
      list.appendChild(line);
    });
    return list;
  }

  // Plans are written in roman numerals and EVE shows skills that way, so
  // the requirement reads back in the notation it was authored in.
  function roman(level) {
    return ['', 'I', 'II', 'III', 'IV', 'V'][level] || String(level);
  }

  /* Two-step, and inline rather than window.confirm. Forget deletes the
   * character's stored refresh token along with its snapshot -- the whole
   * point of one document is that this is a single atomic write -- so
   * recovering from a misclick means a full SSO round trip through a
   * browser.
   *
   * `confirming` holds an id rather than a flag because arming a second
   * row overwrites it, so only one row can ever be armed at once -- but
   * arming happens only from the Forget-button click below, never from
   * expansion, so an armed row stays armed while another row is opened
   * and inspected. What actually disarms it: collapsing the armed row
   * (toggle(), above), Cancel, or Forget itself.
   */
  function forgetNode(ch) {
    var foot = WM.make('div', 'forget-row');
    if (confirming !== ch.character_id) {
      // .btn.danger, the app's one destructive treatment (round 3, L5).
      // This was the last site of the retired `red text, no button`
      // vocabulary -- and the worst of the three, because red text is not
      // a control at all: it read as a warning label, in the same --err
      // the row above it used for `Missing`, about 130 CSS px away.
      // TREATMENT only. The two-step below stays: this row is the only
      // surface in the app for forgetting or re-authenticating a
      // character, so a dialog would cover the thing being acted on.
      var start = WM.make('button', 'btn danger', 'Forget character');
      start.addEventListener('click', function () {
        confirming = ch.character_id;
        renderRoster();
      });
      foot.appendChild(start);
      return foot;
    }
    foot.appendChild(WM.make(
      'span', 'forget-warn',
      'Forget ' + (ch.character_name || 'this character')
      + '? You will have to sign in to EVE again to add it back.'));
    var yes = WM.make('button', 'btn danger', 'Forget');
    yes.addEventListener('click', function () {
      confirming = 0;
      // False is a real answer here, unlike the other mutations: it means
      // the character was already gone (contract: `True` / `False`). Either
      // way the push re-syncs the roster, so the row is dropped by the
      // render that follows rather than by this callback.
      WM.send('skills_forget_character', ch.character_id);
      delete expanded[ch.character_id];
      delete details[ch.character_id];
      delete pendingDetail[ch.character_id];
    });
    var no = WM.make('button', 'btn', 'Cancel');
    no.addEventListener('click', function () {
      confirming = 0;
      renderRoster();
    });
    foot.appendChild(yes);
    foot.appendChild(no);
    return foot;
  }
}());
