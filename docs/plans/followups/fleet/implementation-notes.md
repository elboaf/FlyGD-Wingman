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

## Remaining work at this checkpoint

Commit candidate locally with normal hooks, run committed-range polish-core --fix
from the exact base, inspect any edits and rerun fresh gates. Final polish and
verification results will be appended before coordinator handback.

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
