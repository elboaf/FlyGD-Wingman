# Fleet creation identity — implementation evidence

## Authority and scope

Approved design: [PROPOSAL.md](PROPOSAL.md), coordinator U-01/F-01.
Execution checklist: [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md).
Worktree `/mnt/c/dev/flygd-wingman/.worktrees/followup-fleet-design`;
branch `design/followup-fleet-identity`; fixed base
`ab06a6efde9ade0f40791d812d922356e8e6c16f`.

This is a local implementation candidate, not coordinator acceptance or native /
packaged / release validation. No moving-main integration occurred. Main #185
(`75f3288e84c80018d6cee421ae2f32577ece53d3`) adds title tooltips inside Fleet's
character render body. Our JS diff changes only IIFE capture and local send;
coordinator integration must preserve the later tooltip change.

## Implementation

Python adds private creation publication, retirement and admission helpers in
Fleet-owned Api regions. `fleetbar.create` retires predecessor admission, generates
`secrets.token_hex(32)`, retains its candidate locally through native hidden create
and style, then publishes `(window, token, unready)` under lifecycle → presentation.
Native None, style or publication failure revokes the attempt before best-effort
local cleanup. Both restore and toggle use this path; failed rollback cannot
re-admit it. No orphan registry was introduced.

All five standalone callbacks have token-first defaults exactly as approved:
`snapshot(page_id=None)`, `fit(page_id=None,width=None,height=None)`,
`move(page_id=None,x=None,y=None)`, `save-position(page_id=None,x=None,y=None)`,
`ready(page_id=None)` (full names in the spec/signature test). Snapshot rejection
is None; rejected mutations return None without effects. Token shape, equality,
quitting, concrete window presence and native liveness admit under lifecycle.
Enabled still gates only fit/move; disabled-current snapshot/save/ready work.
No main-page interface, payload revision, persistence schema or worker changed.

Fit captures the original concrete bar once, revalidates both token and object
on each retry and sleeps outside lifecycle. Move's native operation plus save,
and save-position's transaction, stay under lifecycle. Snapshot nests only the
short existing payload read under presentation. Neither native work nor saves nor
JS nor joins are under presentation. Already-entered lifecycle-owned work can
finish before stop obtains lifecycle; the regression intentionally permits it.

Stop revokes token/readiness before detach/join, retaining its concrete window
for existing shutdown destroy retries. Successful destruction clears bookkeeping
under lifecycle → presentation. Ordinary activation close and off/on do not revoke
creation identity or readiness. The real worker timeout and headless fixture
corrections remain intact.

JS validates/captures the fragment exactly once and prepends its token in local
send; invalid fragments resolve null without waiting for or calling the bridge.
Existing literals, promise chain, null hydration/fit behavior, 500 ms fit, mouseup
save, render and revision ordering remain unchanged.

## Deterministic TDD evidence

Commands below ran from the lane checkout with
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-fleet-identity-venv uv run --no-sync`, except
scratch replay uses that interpreter directly without changing its editable install.

1. Before source changes:
   `python -m pytest tests/test_fleet_bar.py -k page_identity -q --tb=short`
   — **93 failed / 16 passed / 46 deselected**, 12.94s.
   Failures show actual replacement-payload disclosure, resize/move/save/reveal
   effects, publication before styling, fit retry retargeting and non-retired stop.
   `_page_call` is a test-only signature adapter for replaying the old interface;
   it drops identity only on old code rather than failing on arity. A separate
   bridge test requires the new signatures/defaults/standalone ownership.
2. New startup retirement, destroy retry, real-worker timed-out stop and signature
   guard selected explicitly — **4 failed** on base, 6.38s; then **4 passed** on
   implementation, 3.37s. New initial Python matrix then **109 passed**, 3.10s.
3. JS subtask wrote the real-script Node harness before source: **33 failed / 2
   passed** on unchanged JS; **35 passed** after capture/send change. Parent read
   its complete harness/diff and independently reran it.
4. Existing direct Python callers/fake creators were adapted to the approved
   signatures/pairs. The first broader run exposed nine expected stale fixture/
   URL expectations; they were corrected without weakening old assertions.
   Scoped Fleet/startup/bridge/runtime/page/smoke group then **447 passed**, 18.69s.
5. Added five real replacement-path cases and queued-failed-creation coverage.
   Final tests were copied into a scratch archive of the exact base:
   `/tmp/wingman-fleet-base-red.wfNvPi`; imported wingman path was asserted by output
   to be that archive, not the editable candidate. Replay command:
   `/tmp/wingman-fleet-identity-venv/bin/python -m pytest tests/test_fleet_bar.py -k page_identity -q --tb=short`
   — **98 failed / 16 passed / 46 deselected**, 3.46s. Real-script JS replay there:
   `node --test scripts/test_fleetbar_runtime.js` — **33 failed / 2 passed**.
   Logs: `/tmp/wingman-fleet-final-base-red.log`, `/tmp/wingman-fleet-js-base-red.log`.

The Python scenarios cover invalid/missing/stale tokens for every callback,
current dead/absent/quitting/tokenless window, real replacement and valid-successor
controls, lifecycle-free fit retry gaps, atomic post-style publication, reentrant
and queued early callbacks, None/style/partial-publication failure through both
paths, cleanup+rollback failure, retained native shutdown retry, and admitted
move/save-before-retirement. Controlled Events and joins replace race sleeps.

The 35 Node cases execute production fleetbar.js against DOM/bridge/timer doubles:
A/B document contexts, deferred bridge/fonts/snapshot/fit/move, immutable token
after fragment mutation, all timer/mouseup argument arrays, invalid fragments,
null/rejected/missing methods, older hydration versus newer pushes, invalid/equal/
zero revisions and same-URL reload identity reuse. They do not render CSS or run
WebView2.

## Candidate checkpoint verification

Independent lane venv created with:
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-fleet-identity-venv uv sync --locked --extra dev`.
No other editable installation was changed. Node: v26.5.0. Ran the documented
locked **release** Cargo build and copied its executable into this worktree's
ignored `packaging/bin`; `codec.codec_available()` asserted true. Release/installed
SHA-256 both:
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.
This is Linux native-codec evidence, not Windows UI evidence.

- `python -m pytest tests/ -q -rs --junitxml=/tmp/wingman-fleet-identity-full-checkpoint.xml`
  — **8,628 passed / 11 skipped**, 446.98s. Full output:
  `/tmp/wingman-fleet-identity-full-checkpoint.log`.
- `ruff check .` — passed; `ruff format --check .` — **330 files formatted**.
- `node --test scripts/test_fleetbar_runtime.js` — **35 passed**, zero skips.
- `node scripts/js_smoke.js` — all modules on all three pages passed.
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`
  — **1 passed**, zero failed/ignored.
- `git diff --check` — passed; complete production diff inspected before checkpoint.

All 11 skips were inspected: profile-copy junctions (3), setup junctions (2),
DPAPI/WinDLL (2), real Windows message pump/window station (1), user32/gdi32/dwmapi
bindings (3). **No missing Node/codec skips.** No native app or global-hook test
was launched; Linux skips the interactive Windows coverage.

## Committed-range polish and final handback

Source/test checkpoint: `915d42caebdf2c31177b3f518bfbebf10b46a4d1` —
**Bind Fleet page callbacks to their native creation**, committed with normal hooks.
This commit includes the approved spec, plan and checkpoint evidence. Final
handback changes after it are documentation-only, recorded in a separate additive
commit; no source/test correction or history rewrite followed review. Exact
ordered history is `git log --reverse --oneline ab06a6efde9ade0f40791d812d922356e8e6c16f..HEAD`.

Ran polish-core **fix mode** on the non-empty committed range
`ab06a6efde9ade0f40791d812d922356e8e6c16f..915d42caebdf2c31177b3f518bfbebf10b46a4d1`.
Python/JavaScript rules were read with repository ES5 conventions taking priority.
Parent inspected the production diff and relevant source/tests, searched helper
callers and all callback sites, and checked the approved inventory. There were
**zero auto-fix edits and zero actionable review findings**. All four read-only
role reviews completed; none was omitted as late:

| Role | Agent | Result |
| --- | --- | --- |
| Independent code reviewer | `0a5bb313-ee5e-4ec` | No findings |
| Silent failure hunter | `e306f85e-0a94-4d9` | No introduced failure-path findings; Node 35 passed |
| Comment/contract analyzer | `48f765ce-546d-44e` | Claims match source/tests; Node 35 passed |
| Interface/type analyzer | `059f7b01-65e5-40d` | No introduced interface findings; focused Python 305 and Node 35 passed |

Agent policy denied read-only Git access; parent supplied the exact complete
2,229-line diff and inventory as `/tmp/wingman-fleet-polish.diff` and
`/tmp/wingman-fleet-polish-files.txt`. Every role finished its range review from
that artifact. This is not an empty-range invocation or review of only a summary.

### Fresh post-polish parent verification

Same independent environment prefix as above; clean source/test checkpoint at
start. No source/test edits followed these commands:

- `python -m pytest tests/ -q -rs --junitxml=/tmp/wingman-fleet-identity-full-final.xml`
  — **8,628 passed / 11 skipped**, **465.66s**. Full output:
  `/tmp/wingman-fleet-identity-full-final.log`. Skip set is exactly the Windows-only
  set above, with no Node/codec skips.
- `python -m pytest tests/test_fleet_bar.py tests/test_fleet_presentation_worker.py tests/test_startup.py tests/test_bridge_contract.py tests/test_fleetbar_runtime.py tests/test_page_conventions.py tests/test_js_smoke.py -q -rs`
  — **452 passed**, **21.85s**, no skips.
- `ruff check .` and `ruff format --check .` — passed; **330 files formatted**.
- `node --check wingman/web/fleetbar.js` and
  `node --check scripts/test_fleetbar_runtime.js` — passed.
- `node --test scripts/test_fleetbar_runtime.js` — **35 passed**, zero skips.
- `node scripts/js_smoke.js` — all three pages passed.
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`
  — **1 passed**, zero failed/ignored.
- `git diff ab06a6efde9ade0f40791d812d922356e8e6c16f..HEAD --check` — passed.

### Changed-file inventory and decisions

Four production files: `wingman/ui/api.py` (Fleet fields/helpers/endpoints/stop),
`wingman/ui/fleetbar.py` (creation attempt ownership), `wingman/__main__.py`
(successful Fleet destroy bookkeeping only), `wingman/web/fleetbar.js` (capture/send
only). Six test files: `tests/test_fleet_bar.py`,
`tests/test_fleet_presentation_worker.py`, `tests/test_startup.py`,
`tests/test_bridge_contract.py`, new `scripts/test_fleetbar_runtime.js`, new
`tests/test_fleetbar_runtime.py`. Three lane docs: approved `PROPOSAL.md`,
`IMPLEMENTATION-PLAN.md`, this evidence/handback document. No other tracked file
changed, and `fleetpresentation.py` remains untouched.

No material deviation from U-01/F-01. The test-only signature adapter makes
base-red evidence behavioral while the separate signature guard prevents it from
masking removal of the new interface. Existing lexical comments overstating fit
success were corrected, not converted into a stronger runtime acknowledgement.
Source scope remains separate from main #185; its tooltip must survive eventual
integration. There is no claim of integration, packaged URI, Windows or release
readiness.

### Knowledge check for reviewers

1. Why does an off/on activation change retain the creation token while native replacement retires it?
2. Which lock prevents a delayed fit retry from switching to a successor, and where is that lock released?
3. Why does shutdown revoke admission but retain a window whose native destroy failed?
4. Why can ready follow a null hydration or failed fit without granting a predecessor access to its replacement?
5. Which document-reload and native-visibility guarantees are deliberately absent despite the passing headless suites?

## Accepted limitations and reviewer focus

- Creation tokens correlate origins, not authenticate the shared bridge. A
  same-window reload/recovery retains the fragment and is not document-isolated.
- Fit/ready are still best-effort; null hydration, fit refusal/exhaustion and
  unreadable dimensions do not introduce positive acknowledgements or hidden-on-null.
- Existing pinned WinForms resize/move SWP_SHOWWINDOW behavior is untouched.
  Strict pre-ready invisibility, packaged URL behavior, focus/tool-window/DPI and
  actual Windows native behavior remain unverified; no CSS/native workaround.
- Already-entered native work and its protected move save are non-cancellable;
  shutdown does not promise instant retirement while another owner holds lifecycle.
- Creation-failure native cleanup is best-effort; no returned handle / failed
  destroy may leave an orphan. Shutdown retains its existing known failed target.
- Reviewer focus: no mixed pair publication, no admission restored by cleanup/
  rollback failure, no retry lookup of a successor, no off/on token churn, and
  preserved real-worker/startup fixture seams. Integrators must retain #185 tooltip.

No push, PR/issue, merge, release, worktree cleanup, real user-state/account action,
live upload/ESI, native desktop launch or EVE operation was performed.
