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
 * comment on that function); the roster and its in-row expansion are what
 * everything else here builds toward.
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
  var filterText = '';
  var asked = false;      // has the page asked Python for state yet
  var requestSequence = 0; // drops stale skills_state reads
  var autoExpanded = false; // has the one-shot small-roster expansion run
  var copyStatusPlan = ''; // plan named by the current clipboard attempt
  var copyAttemptSeq = 0; // invalidates superseded asynchronous completions

  /* S1. The expanded row still answers the route's scoped question -- why
   * this character can or cannot fly the selected plan -- and it opened
   * behind a chevron on a screen with ~900 CSS px of void under it. Rows
   * still LOAD collapsed in the markup sense -- this expands them once, on
   * the first payload that carries anyone -- so nothing about the
   * disclosure or the toggle changes; what changes is the state the screen
   * is first seen in.
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

  /* How many characters the current scope holds. This is the denominator
   * of every rail ratio AND the population the roster shows, so it is
   * derived once: two places deriving it separately is how `4/9` for a
   * four-character crew happens.
   *
   * `found` stays 0 if `current` matches nothing in `groups()` -- which
   * would render as an n/0 ratio. That is unreachable today only because
   * controller.py's `_groups_locked` and `_selected_group_locked` are
   * proven, by a shared iteration order under one lock hold, to always
   * agree on which spelling represents the selection (see the comments on
   * those two functions). Do not paper over this with a
   * `|| characters().length` fallback if it ever fires -- that would show a
   * confidently WRONG denominator instead of an obviously broken one. */
  function scopedTotal() {
    var current = selectedGroup();
    if (!current) return characters().length;
    var found = 0;
    groups().forEach(function (group) {
      if (group.name.toLowerCase() === current.toLowerCase()) {
        found = group.member_count;
      }
    });
    return found;
  }

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

  function requestState() {
    requestSequence += 1;
    var wanted = requestSequence;
    WM.send('skills_state').then(function (payload) {
      // A null/undefined reply means the request itself failed rather
      // than answering with an empty state -- render() already no-ops on
      // that, but leaving `asked` set would make every later route entry
      // believe the initial ask already happened and skip retrying it
      // forever, stranding the page with no state at all.
      if (!payload) {
        asked = false;
        return;
      }
      if (wanted !== requestSequence || WM.current_route !== 'skills') return;
      render(payload);
    });
  }

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
    requestState();
  });

  document.addEventListener('wm:eve-authority', function () {
    if (WM.current_route !== 'skills') return;
    requestState();
  });

  // ---- left rail ------------------------------------------------------
  /* The ready COUNT used to be part of this line ("2 characters - 0
   * ready") and is deliberately gone. It was scoped to the selected plan,
   * because `readiness` is, but it sits above `Manage characters…` and detached
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
   * beside it, so it is the one that says what it counts. `added` names
   * scope rather than the control below it now that the button is a
   * Settings handoff, not an add action.
   *
   * The rule the two comments at groupNode() and statusLine() establish is
   * unchanged and is why the noun stays: every number on this screen
   * carries the noun it counts. This adds the scope that noun was missing.
   */
  function renderRail() {
    var chars = characters();
    var scoped = scopedTotal();
    WM.el('skills-counts').textContent = !chars.length
      ? 'No characters yet'
      : selectedGroup()
        ? scoped + ' of ' + chars.length + ' characters'
        : chars.length + (chars.length === 1 ? ' character added'
                                             : ' characters added');

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
    var total = scopedTotal();
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
    // Feedback belongs to the old selection, and either asynchronous stage
    // of its copy attempt may still complete after this click.
    copyAttemptSeq += 1;
    resetCopyStatus('');
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
    // The page only sends and waits; Python's push is the sole cause of
    // what renders. Unlike selectPlan, this deliberately does NOT drop the
    // detail/pendingDetail caches -- those are scored against the PLAN, and
    // a group change does not invalidate them the way a plan change does.
    WM.send('skills_select_group', name);
  }

  function renderRailButtons() {
    var refresh = WM.el('skills-refresh');
    refresh.textContent = STATE.refresh_in_flight
      ? 'Refreshing…' : 'Refresh characters';
    refresh.disabled = STATE.refresh_in_flight || !characters().length;
  }

  WM.el('skills-manage-characters').addEventListener('click', function () {
    WM.openSettingsSection('characters');
  });

  WM.el('skills-refresh').addEventListener('click', function () {
    WM.send('skills_refresh');
  });

  WM.el('skills-open-folder').addEventListener('click', function () {
    WM.send('skills_open_plans_folder');
  });

  WM.el('skills-reload-plans').addEventListener('click', function () {
    // A reload can replace a plan without renaming it, so invalidate pending
    // clipboard work as well as detail data before asking Python to reload.
    copyAttemptSeq += 1;
    resetCopyStatus('');
    details = {};
    pendingDetail = {};
    WM.send('skills_reload_plans');
  });

  // None of the three button handlers above inspect the return value.
  // Every one is a mutation, and a mutation pushes onSkills on both its
  // success and failure paths -- the push is the answer, and acting on
  // the return as well would render the same state twice.

  WM.el('skills-rename-group').addEventListener('click', function () {
    var current = selectedGroup();
    if (!current) return;
    // Third argument is the PREFILLED VALUE, not a callback: the current
    // name, so a rename starts from what is being renamed. WM.prompt
    // resolves with the typed text or null on cancel.
    WM.prompt('Rename group', 'A new name for this group.', current)
      .then(function (text) {
        if (text === null) return;
        var wanted = text.trim();
        if (!wanted || wanted === current) return;
        // A rename ONTO a name that already has members merges two crews.
        // That is the honest reading of the operation, not an error -- but
        // it is not what someone correcting a typo expects, so it is asked
        // first. A case-only change is NOT a merge (it is one group
        // respelled), which is why the collision test excludes a name that
        // differs from the current one only in case.
        var collides = false;
        groups().forEach(function (group) {
          if (group.name.toLowerCase() === wanted.toLowerCase()
              && group.name.toLowerCase() !== current.toLowerCase()) {
            collides = true;
          }
        });
        if (!collides) {
          WM.send('skills_rename_group', current, wanted);
          return;
        }
        WM.confirm('Merge groups',
                   '“' + wanted + '” already exists. Renaming “'
                   + current + '” will merge the two into one group.',
                   { destructive: true })
          .then(function (ok) {
            if (ok) WM.send('skills_rename_group', current, wanted);
          });
      });
  });

  WM.el('skills-delete-group').addEventListener('click', function () {
    var current = selectedGroup();
    if (!current) return;
    var total = scopedTotal();
    WM.confirm('Delete group',
               'Delete “' + current + '”? Its ' + total
               + (total === 1 ? ' character' : ' characters')
               + ' stay on the roster and become ungrouped.',
               { destructive: true })
      .then(function (ok) {
        if (ok) WM.send('skills_delete_group', current);
      });
  });

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
    // Task 6. There is nothing to assume about until a plan is selected --
    // the estimator itself is never even asked (Task 5's ruling: an empty
    // `training_estimate_status` means no estimate was requested, not a
    // fifth failure mode), so the button that explains its assumptions has
    // nothing to explain either.
    WM.el('skills-estimate-info').hidden = !name;
    // The object of this action is the plan, so with no plan selected
    // there is nothing to copy and the control says so by being disabled
    // rather than by failing when pressed.
    var copy = WM.el('skills-copy-plan');
    copy.disabled = !name;
    copy.title = name
      ? 'Copies every skill in “' + name + '” for EVE\u2019s skill plan '
        + 'import. The game drops the ones already trained.'
      : '';
    // A feedback message describes one plan. An authoritative push can also
    // change the selection (for example after plans are reloaded), so it must
    // invalidate the old attempt just like an explicit plan click does.
    if (copyStatusPlan && copyStatusPlan !== name) {
      copyAttemptSeq += 1;
      resetCopyStatus('');
    }
  }

  function setCopyStatus(message, failed) {
    var status = WM.el('skills-copy-status');
    status.textContent = message;
    status.classList.toggle('err', !!failed);
  }

  function resetCopyStatus(plan) {
    copyStatusPlan = plan;
    setCopyStatus('', false);
  }

  function copyAttemptIsCurrent(token, plan) {
    return token === copyAttemptSeq && plan === copyStatusPlan;
  }

  WM.el('skills-copy-plan').addEventListener('click', function () {
    var name = (STATE && STATE.selected_plan_name) || '';
    if (!name) return;
    // Claim ownership before either asynchronous stage can fail. The token
    // also distinguishes two attempts for the same plan and a switch away
    // and back, where comparing only the plan name would accept stale work.
    copyAttemptSeq += 1;
    var token = copyAttemptSeq;
    resetCopyStatus(name);
    // Python returns the text and the page owns the clipboard write, the
    // same split list.js:396-401 uses for `Copy link`: with Tk gone there
    // is no toolkit clipboard and navigator.clipboard is right here.
    // "" is a plan the last reload invalidated, not an empty plan, because
    // plans.parse rejects a file with no requirements.
    WM.send('skills_plan_text', name).then(function (text) {
      if (!copyAttemptIsCurrent(token, name)) return;
      // Python owns the missing-plan warning: it knows this listed plan
      // vanished during a reload, while the page only owns clipboard results.
      if (!text) { return; }
      try {
        navigator.clipboard.writeText(text).then(function () {
          if (!copyAttemptIsCurrent(token, name)) return;
          setCopyStatus('Plan copied to clipboard.', false);
        }, function () {
          if (!copyAttemptIsCurrent(token, name)) return;
          setCopyStatus('Could not copy the plan to the clipboard.', true);
        });
      } catch (err) {
        // A clipboard denied before it returns a promise has the same
        // user-facing result as a rejected write.
        if (!copyAttemptIsCurrent(token, name)) return;
        setCopyStatus('Could not copy the plan to the clipboard.', true);
      }
    });
  });

  /* Fix round 1, WCAG 1.4.13. The primitive's `:focus-visible` addition
   * made this tooltip appear on keyboard focus and STAY until focus left
   * -- with no way to dismiss it that does not also move focus, which is
   * exactly what 1.4.13 forbids. Escape suppresses the pseudo-tooltip
   * WITHOUT blurring the button (no `.blur()` call here -- focus stays
   * exactly where the reader left it), and only a real blur (Tab away,
   * click elsewhere) clears the suppression, so returning to the button
   * later shows the tooltip again rather than disabling it for the rest
   * of the session. `.tip-dismissed` carries no visual treatment of its
   * own; style.css's `.skills-estimate-info.tip-dismissed:focus-visible
   * ::after` rule is the only thing that reads it, and its three-selector
   * specificity is what lets it beat the primitive's own
   * `[data-tip]:focus-visible::after` rule.
   */
  var estimateInfo = WM.el('skills-estimate-info');
  estimateInfo.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      estimateInfo.classList.add('tip-dismissed');
    }
  });
  estimateInfo.addEventListener('blur', function () {
    estimateInfo.classList.remove('tip-dismissed');
  });

  function renderNotices() {
    var host = WM.el('skills-notices');
    host.textContent = '';
    var lines = [];
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
      rows.sort(comparatorFor(name));
      groups.push({ name: name, rows: rows });
    });
    return groups;
  }

  // Task 6. One comparator per group, chosen by the group's OWN name --
  // never a blanket default with per-group exceptions bolted on, because
  // that shape is how a Ready or Locked row would silently start sorting
  // by a training-time field it has no opinion about the moment a future
  // group's name collided with a stray `if`.
  function comparatorFor(name) {
    if (name === 'Training') return byTrainingFinishThenName;
    if (name === 'Missing') return byTrainingRemainingThenName;
    return byName;
  }

  function byName(a, b) {
    return (a.character_name || '').toLowerCase()
      .localeCompare((b.character_name || '').toLowerCase());
  }

  /* Task 6. Soonest first, same as the group's own status line reads --
   * `estimated_finish_utc` is EVE's own queue fact (the analysis' queued
   * requirements), not the plan's whole remaining-duration estimate, so a
   * character already training finishes when its QUEUE says, never when
   * training.estimate() guesses. A timing-unknown row has no finish to
   * compare at all -- EVE reported a paused queue -- and claiming one from
   * the rest would be exactly the guess the group's own status line
   * refuses to make, so it sorts last rather than first or by name alone.
   */
  function byTrainingFinishThenName(a, b) {
    var aTime = Date.parse(a.estimated_finish_utc || '');
    var bTime = Date.parse(b.estimated_finish_utc || '');
    var aKnown = !isNaN(aTime);
    var bKnown = !isNaN(bTime);
    if (aKnown !== bKnown) return aKnown ? -1 : 1;
    if (aKnown && aTime !== bTime) return aTime - bTime;
    return byName(a, b);
  }

  /* Task 6. Replaces byMissingThenName (fewest requirements first), which
   * answered "how much is left" rather than "how long does it take" --
   * two skills at level V cost far more training time than five at level
   * I, and the count sort put the five-skill row first regardless. Sorts
   * on the RAW seconds Task 5 published, never the formatted label: a
   * text sort would put "1d 2h" before "9h", which is backwards. A
   * character with no usable estimate (an unresolved skill, stale
   * attributes, an incomplete SP snapshot) sorts last, the same way an
   * unknown Training finish does. */
  function byTrainingRemainingThenName(a, b) {
    var aKnown = typeof a.training_remaining_seconds === 'number';
    var bKnown = typeof b.training_remaining_seconds === 'number';
    if (aKnown !== bKnown) return aKnown ? -1 : 1;
    if (aKnown && a.training_remaining_seconds !== b.training_remaining_seconds) {
      return a.training_remaining_seconds - b.training_remaining_seconds;
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
   *   Missing    how many requirements are still unqueued -- the other
   *              half of S1 -- and, when Task 5's estimator could answer,
   *              how long the whole plan still takes to train. `unqueued`
   *              rather than `missing`: every one of these is about to be
   *              queued, not merely absent, and the number also explains
   *              the group's own sort (byTrainingRemainingThenName).
   *   Training   how many are already queued, and the ETA that answer
   *              someone came here for -- EVE's own queue fact, not a
   *              guess. The word `Training` in front of it was the
   *              header's.
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
   *
   * Task 6's estimate carries the same discipline one status word
   * further: `training_estimate_status` is one of Task 5's four real
   * failure/success words ONLY when a plan is selected and the row's
   * readiness could therefore be `Missing` at all -- the empty string
   * means no estimate was ever asked for (Task 5's ruling), which
   * controller._character_row can only pair with `Unscored`, never with
   * `Missing`. The `? :` below is not defensive filler: it is what stops
   * that empty string from ever being folded into "training time
   * unavailable", a claim about a REAL failure, if that invariant ever
   * moved.
   */
  function statusLine(ch) {
    if (ch.readiness === 'Training') {
      var queued = ch.queued_count + ' queued';
      var eta = formatEta(ch.estimated_finish_utc);
      return (ch.queue_timing_unknown || !eta)
        ? queued + ' \u00b7 timing unknown'
        : queued + ' \u00b7 ready in ' + eta;
    }
    if (ch.readiness === 'Missing') {
      var unqueued = ch.missing_count + ' unqueued';
      if (ch.training_estimate_status === 'available') {
        return unqueued + ' \u00b7 ' + ch.training_remaining_label
          + ' training remaining';
      }
      return ch.training_estimate_status ?
        unqueued + ' \u00b7 training time unavailable' : unqueued;
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

  /* The two filters intersect. This DOES hide rows, but that is already
   * true of the text filter beside it, and `All` is one click away. The
   * LOCKOUT GUARD above buildRoster is not weakened: it forbids
   * ENUMERATING known readiness groups, so that a character in an
   * unrecognised state still gets a row. It says nothing about a filter
   * the user chose. */
  function matching() {
    var needle = filterText.trim().toLowerCase();
    var group = selectedGroup().toLowerCase();
    return characters().filter(function (ch) {
      if (group && (ch.group || '').toLowerCase() !== group) return false;
      if (!needle) return true;
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
      // and PRODUCT.md's rule is to name things the way the user does.
      empty.textContent =
        'No characters yet. Press “Manage characters…” to authenticate one '
        + 'in Settings.';
      return;
    }

    var rows = matching();
    // The plans-empty and no-match hints are shown BESIDE the roster, never
    // instead of it -- see THE LOCKOUT GUARD above buildRoster. A missing
    // or empty plans folder changes what every character's readiness IS
    // (Unscored, most likely), it does not change whether that character
    // gets a row: the route still has to answer who the selected plan fits,
    // and a character stuck at Unscored because the plans folder is empty
    // still belongs in that answer.
    var hint = '';
    if (!plans().length) {
      hint = 'No local plans yet. Drop a .txt plan in the plans folder, '
        + 'then reload.';
    } else if (!rows.length && selectedGroup() && !filterText.trim()) {
      hint = 'No characters in “' + selectedGroup() + '”.';
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

  /* Two, not controller._ROSTER_NAME_CAP's three. That backend cap
   * bounds the PAYLOAD -- evaluator.missing_names's own docstring calls
   * it "a payload bound, not a display decision" -- and the display
   * decision belongs here, independently of it: if the payload cap ever
   * moves, this does not have to move with it, and vice versa.
   *
   * Smaller than ui/copy.py's _COPY_NAME_CAP (6) on purpose, not just
   * coincidentally: that modal is a dialog the reader stopped at on
   * purpose and reads once, `shown`/`rest` derived the same way this row
   * does (copy.py:555-563). A roster row is read in passing, across many
   * rows in one scan, not opened and stopped at -- so it can afford fewer
   * names than a confirmation the user is already reading closely.
   */
  var ROSTER_ROW_NAME_CAP = 2;

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
      var statusNode = WM.make('span', 'skills-status status-' + ch.readiness,
                               status);
      // Task 6. The info button beside the plan heading is the
      // keyboard-reachable affordance for the assumptions behind this
      // number; this carries the SAME text so a mouse resting on the
      // number gets the same explanation without tabbing up to the
      // header. Read off the button rather than retyped, so the two
      // copies of this sentence cannot drift apart -- and only on
      // Missing, whose status is the one that names a duration at all.
      if (ch.readiness === 'Missing') {
        var tip = WM.el('skills-estimate-info').getAttribute('data-tip');
        if (tip) statusNode.setAttribute('data-tip', tip);
      }
      top.appendChild(statusNode);
    }
    top.addEventListener('click', function () { toggle(ch.character_id); });
    row.appendChild(top);
    // Round 6, P1-2. `9 requirements` beside 420 CSS px of empty pane made
    // the one screen whose job is "which of my characters can fly this"
    // hide WHICH nine behind a row expand. The names ride the roster
    // payload -- see controller._ROSTER_NAME_CAP; they are taken off the
    // same tuple missing_count counts, so they cannot disagree with the
    // number to their left. The row shows fewer of them still, capped
    // again below at ROSTER_ROW_NAME_CAP.
    //
    // Appended to the ROW, not to `top`: it is a second line under the
    // name, and putting it in the button's flex row would make it compete
    // with the status for the same track. The row stays one click target
    // either way -- this span is inside the <button>'s sibling, so it does
    // not nest interactive content.
    var shown = (ch.missing_names || []).slice(0, ROSTER_ROW_NAME_CAP);
    if (shown.length) {
      // Derived from `shown.length`, NOT from `ch.missing_names.length`:
      // the payload can carry up to controller._ROSTER_NAME_CAP names,
      // capped again here to ROSTER_ROW_NAME_CAP for what this row prints.
      // Deriving the remainder from the payload's own length would make a
      // payload-cap change silently change what "and N more" states
      // without either cap actually moving on its own.
      var rest = ch.missing_count - shown.length;
      var text = shown.join(', ');
      // The remainder is stated, never implied by a truncation: `and 6
      // more` is a fact, a trailing ellipsis is a mystery. Same rule
      // ui/copy.py's _COPY_NAME_CAP follows for the copy confirm.
      if (rest > 0) text += ' and ' + rest + ' more';
      row.appendChild(WM.make('span', 'skills-missing', text));
    }

    if (expanded[ch.character_id]) row.appendChild(detailNode(ch));
    return row;
  }

  function toggle(id) {
    if (expanded[id]) {
      delete expanded[id];
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

  /* A discrete control, so it commits on change -- the rule Settings
   * states for its own fields. Creating a group happens HERE rather than
   * on the rail because a group exists exactly as long as someone is in
   * it: there is nothing to create until a character joins one. */
  function groupPickerNode(ch) {
    var row = WM.make('div', 'skills-detail-row');
    var label = WM.make('label', '', 'Group');
    var select = WM.make('select', 'field');
    label.setAttribute('for', 'skills-group-' + ch.character_id);
    select.id = 'skills-group-' + ch.character_id;

    var none = WM.make('option', '', 'None');
    none.value = '';
    select.appendChild(none);

    var known = false;
    groups().forEach(function (group) {
      var option = WM.make('option', '', group.name);
      option.value = group.name;
      if (group.name.toLowerCase() === (ch.group || '').toLowerCase()) {
        option.selected = true;
        known = true;
      }
      select.appendChild(option);
    });
    // A character whose group is not in the derived list cannot happen
    // from Python -- the list IS the roster's groups. It can happen from a
    // stale page held across a change, and silently showing `None` would
    // invite a click that clears a membership the user still has.
    if (ch.group && !known) {
      var stale = WM.make('option', '', ch.group);
      stale.value = ch.group;
      stale.selected = true;
      select.appendChild(stale);
    }

    // No sentinel VALUE: any magic string is a group name someone
    // could legitimately type. The option marks itself instead, so
    // `New group` and a real group called "New group" stay distinct.
    var newOption = WM.make('option', '', 'New group…');
    newOption.value = '';
    newOption.dataset.newGroup = '1';
    select.appendChild(newOption);

    select.addEventListener('change', function () {
      var chosen = select.options[select.selectedIndex];
      if (!chosen || !chosen.dataset.newGroup) {
        WM.send('skills_set_character_group', ch.character_id,
                select.value);
        return;
      }
      // Reset first: if the prompt is cancelled the control must not sit
      // showing `New group…` as though it were a membership.
      select.value = ch.group || '';
      // WM.prompt(title, body, initialValue) resolves with the typed text
      // or null -- the same contract window.prompt had. It is NOT
      // callback-taking; bookmarks.js:288 and previews.js:153 are the two
      // existing call sites and both read the result through .then.
      WM.prompt('New group',
                'A name for the characters who fly together.', '')
        .then(function (text) {
          if (text === null) return;
          var wanted = text.trim();
          if (!wanted) return;
          WM.send('skills_set_character_group', ch.character_id, wanted);
        });
    });

    row.appendChild(label);
    row.appendChild(select);
    return row;
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
        + 'rejected and has been removed. Manage characters in Settings to '
        + 'authenticate it again.'));
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

    box.appendChild(groupPickerNode(ch));
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

}());
