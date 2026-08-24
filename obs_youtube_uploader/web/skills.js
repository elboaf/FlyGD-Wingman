/* FlyGD Wingman — the Skills route.
 *
 * Answers one question: who can fly this plan? Every judgement that
 * produces that answer -- readiness precedence, ETA, requirement state --
 * happens in Python's evaluator, because this repo has no way to test
 * JavaScript (webview-replatform-design.md:545). This file groups, sorts,
 * filters, and renders what Python already decided.
 *
 * The one derived value here is the plan rail's ready RATIO: Python sends
 * each plan's ready_count, and the denominator is characters.length, which
 * the page already holds.
 *
 * renderRoster() is a no-op stub in this task, replaced by Task 17's real
 * implementation -- expanded, details, pendingDetail, and filterText exist
 * here only as the seam it builds on. Nothing in THIS task ever populates
 * `expanded`, so the one caller that would reach into it (selectPlan,
 * below) never actually runs its body.
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

  function characters() { return (STATE && STATE.characters) || []; }
  function plans() { return (STATE && STATE.plans) || []; }

  function render(payload) {
    if (!payload) return;
    STATE = payload;
    // Progress lines describe a refresh in flight. onSkills is pushed on
    // BOTH the success and failure paths of every mutation, so the end of
    // a refresh always arrives here -- which is what stops "Refreshed 3 of
    // 7 characters" sitting on screen forever after a failure.
    if (!payload.refresh_in_flight) progress = null;
    renderRail();
    renderHead();
    renderNotices();
    renderIssues();
    renderRoster();
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
    WM.send('skills_state').then(render);
  });

  // ---- left rail ------------------------------------------------------
  function renderRail() {
    var chars = characters();
    var ready = 0;
    chars.forEach(function (ch) { if (ch.readiness === 'Ready') ready += 1; });
    WM.el('skills-counts').textContent = chars.length
      ? chars.length + (chars.length === 1 ? ' character' : ' characters')
        + ' · ' + ready + ' ready'
      : 'No characters yet';

    renderRailButtons();
    renderPlans();
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
  }

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

  // Replaced by Task 17, which builds the roster, its groups and the
  // in-row expansion. A no-op rather than an undefined call so this
  // commit renders a quiet empty pane instead of throwing a caught
  // ReferenceError into the console on every state push.
  function renderRoster() {}
}());
