# Probe formation sharing: verification record

## Status and scope

**2026-09-06 — implementation-wide polish and fresh local verification complete;
not release-ready.** All four independent polish roles returned; their two
consolidated findings were corrected with runtime and native Chromium RED/GREEN
evidence. All six task reviews and the final whole-branch review are complete with
no outstanding code findings; the controller independently reran the local gates.
Windows/WebView2, real OS clipboard and live-EVE acceptance/restoration remain
**unverified**. Passing Linux tests do not satisfy those gates.

Task base: `227397f61c143a8f378555f3f973d5b8d8314c76`.
Implementation-wide polish base: `3d77b738cc7758933b44401eb4164a6028ecdde6`.
All repository commands below ran in
`/mnt/c/dev/flygd-wingman/.worktrees/settings-sharing-design` on
`design/settings-sharing`. Python 3.11.15, uv 0.11.3, Node v26.5.0, Cargo 1.91.0;
Linux test scratch used ordinary `/tmp` and tool caches. No user/EVE files, other
checkout, real clipboard, push, merge, amend or hook bypass was used.

Checkpoint `b62d180e5fc826c4241fa4d0705b9b09026f937e` added tests and smoke
documentation only. Those tests passed when added: **added coverage, not a claimed
RED/GREEN production fix**. The subsequent polish corrections below change only
the formation editor, its runtime tests, and scoped documentation; they have
separate observed RED/GREEN evidence.

## Implemented flow

- **Copy:** independent sharing checkboxes select current draft objects, including
  valid unsaved edits. `formation_sharing.py` validates and explicitly projects
  names and meter-valued geometry into versioned JSON. Account identities, paths,
  local IDs and revisions do not travel. The page reports success only after its
  clipboard-write promise succeeds.
- **Paste:** the page sends explicit review text to pure Python endpoints. Candidates
  remain separate from the account draft, with editable names, derived probe counts
  and the existing geometry preview. Python owns strict validation and casefold
  conflicts; no file lookup or write occurs in these endpoints.
- **Add:** current candidate names and current draft names are revalidated. Only a
  matching, current response appends the whole batch as ID-less draft items. Cancel,
  malformed input and stale responses cannot partially add or replace data.
- **Save:** the existing recipient writer allocates local IDs. The API requires the
  loaded content revision; the codec hashes the same bytes it decodes and checks
  the expected revision around backup before atomic publication. Publication is
  the success boundary, so later housekeeping failure is a warning, not a false
  claim that nothing was saved.
- **Lifecycle:** content revisions, local edit revisions and session/request
  identities answer different questions. Committed baselines advance while newer
  edits remain intact. Native typing, checkbox clicks and stale Delete confirmations
  have regressions; error recovery never force-saves or automatically merges files.

## Cross-account production-API coverage

`tests/test_api_evesettings.py` now exercises:

- `eve_settings_formations` on source A and recipient B, then export → parse with
  B's actual names → explicit rename → validate → guarded Save → decode.
- Source IDs 900/901 cannot become recipient authority. Recipient IDs 2/17 stay
  intact; additions receive 18/19; selected ID 17, scratch ID −4, unrelated keys
  and all probe values survive. A's bytes remain unchanged throughout.
- Existing `STRASSE` conflicts with incoming `Straße` via Python casefold. Only
  the explicit rename resolves it. Export has exactly the portable allowlisted
  fields. Reads/export/review/validation create no file write or backup.
- Content revisions equal SHA-256 of the bytes actually read/published. An external
  B mutation is refused without changing its new bytes or making a backup.
- Real backup-first publication writes a restorable archive of B's pre-save bytes,
  not A. A pruning exception after publication leaves `ok: true`, the committed
  revision and an explicit warning. The real backup restore function restores
  only the test-owned B; this does not certify the Windows Backups UI.
- Both read and save reject an outside-root account and an in-root symlink to it,
  using real `require_under` resolution, valid codec bytes and real workers.
  Rejection leaves outside bytes unchanged, makes no backup, and releases the lock.

There are 48 lifecycle cases (eight numeric fixtures × three outcomes × two codec
transports), plus four containment cases. One transport substitutes only codec
`_run` with a lossless signature/JSON filter; all application logic, hashing,
backup and atomic publication remain real. The other uses the locally built native
codec without substituting codec calls. Windows discovery/ESI are external seams;
the injected prune exception tests the real API's housekeeping boundary.

The numeric fixtures include minimum/maximum ranges and their supported neighbors:
`149597.8707`, `149597.87070000003`, `9804046054195200`, and
`9804046054195198` meters; the page lifecycle's `187.25000012345 * 149597870700`
and `18469.135803 * 149597870700` meter ranges; another fractional range
`184688731163.59283`; ±10^16-meter coordinates and supported neighbors;
and fractional positions. These are not only integer/binary-exact geometry.
Every native fixture passed exact encode/verify/decode equality; no codec guard
was relaxed and no native refusal was hidden. This is evidence for these fixtures,
not a claim of universal codec fidelity or EVE acceptance of all supported ranges.

The 78 executable formation-page scenarios consume production HTML via
`tests/html_tree.py:PageTree` and run actual `formations.js`. Their strict
parse/validate responses come from Python, not a JS copy of validation. Copy
success/error replies and file responses/IDs in that harness are controlled
fixtures, not evidence of real export or file publication. Node controls DOM
mechanics and asynchronous delivery. The new API integration exercises real
export and publication; the browser pass below also uses Python's real exporter. Existing tests cover retained-edit second saves,
late/stale callbacks, clipboard failures, atomic Add/cancel, Unicode and numeric
bounds, and ordinary reload normalization. Sharing keeps supported fractional
ranges; ordinary editor reads still normalize ranges to six decimal AU places.

## Checkpoint commands and observed results

| Command | Observed result |
| --- | --- |
| `uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_evesettings_codec.py tests/test_evesettings_formation_sharing.py tests/test_formations_page.py -q` before changes/build installation | 827 passed, 1 skipped in 63.45s; codec absent |
| `cargo build --offline --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir .superpowers/sdd/probe-formation-sharing-plan/codec-target` | Exit 0; release build completed in 5.03s |
| `mkdir -p packaging/bin` then `cp .superpowers/sdd/probe-formation-sharing-plan/codec-target/release/wingman-settings-codec packaging/bin/wingman-settings-codec` | Exit 0; only generated native binary installed into ignored location |
| `uv run --no-sync python -m pytest tests/test_evesettings_codec.py -q -rs` | 72 passed in 1.14s; real-codec round-trip ran |
| `uv run --no-sync python -m pytest tests/test_api_evesettings.py -k 'shared_formation_lifecycle or shared_formation_account_boundary' -q -rs` | Initial smaller matrix: 16 passed, 234 deselected in 3.64s; expanded matrix: 52 passed, 234 deselected in 7.27s |
| `uv run --no-sync ruff format tests/test_api_evesettings.py` | 1 file reformatted; no production edits |
| `uv run --no-sync ruff check tests/test_api_evesettings.py` | All checks passed |
| `uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_evesettings_codec.py tests/test_evesettings_formation_sharing.py tests/test_formations_page.py -q -rs` | 880 passed in 68.73s; no skips, including Node and native codec |
| `uv sync --locked --extra dev` | Exit 0; resolved 55 packages, checked 38 packages |
| `uv run --no-sync python -m pytest tests/ -q -rs` | First full pass: 6,119 passed, 9 skipped in 145.83s; final checkpoint pass after distinct recipient-geometry assertions: 6,119 passed, 9 skipped in 144.08s |
| `uv run --no-sync ruff check .` | All checks passed |
| `uv run --no-sync ruff format --check .` | 284 files already formatted |
| `node --check wingman/web/formations.js` | Exit 0 |
| `node --check wingman/web/dev.js` | Exit 0 |
| `node --check tests/fixtures/formations_page.cjs` | Exit 0 |
| `git diff --check` | Exit 0 |
| `cargo test --offline --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir .superpowers/sdd/probe-formation-sharing-plan/codec-target` | 1 passed: `large_float_survives_the_json_and_marshal_round_trip_exactly`; exit 0 |

The first copy attempt found `packaging/bin` absent (`cp: cannot create regular
file 'packaging/bin/wingman-settings-codec': No such file or directory`). Creating
that ignored directory resolved the artifact-installation issue; it was not a
codec failure. Cargo source, lockfile and dependencies were not edited. Both the
target directory and binary were confirmed ignored with `git check-ignore`.
Generated binary SHA-256:
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.

The nine full-suite skips were three real Windows junction cases in
`test_evesettings_profilecopy.py`, two real DPAPI/WinDLL cases in
`test_eveskills_dpapi.py`, one real window-station/message-pump case in
`test_preview_host.py`, and three native user32/gdi32/dwmapi cases in
`test_preview_win32.py`. No Node or codec test skipped in this local full run.

CI's Ubuntu/Windows matrix is unchanged. Current `.github/workflows/ci.yml` does
not explicitly provision Node; runtime tests skip when Node is absent. No remote
CI run was verified here, so runtime coverage there is not claimed. CI runs pytest
before its separate Cargo tests and does not install a native codec into
`packaging/bin` for pytest; the availability-gated Python/native integration cases
will skip without that artifact. No JS package, build pipeline or CI change was
added as part of this task.

## Fresh isolated Linux Chromium evidence

After inspecting the prior task's script, ran `node /tmp/task5-browser.cjs` against
this worktree's `file://.../wingman/web/index.html?dev=1&formations-share=...`.
**PASS**, no page errors. The script created a new tab and closed it in `finally`;
it did not modify existing tabs, profiles or browser processes. Clipboard writes
were captured in that page only; clipboard reads threw without consulting the OS.
Strict export/parse/validate replies came from actual Python API calls. Dev account
reads/saves remained visual fixtures, not real accounts.

Fresh checks: invalid/conflict/slow/empty/stale/unsaved visual states; native rename
blur then checkbox toggle without replacing the control; Copy including the unsaved
name; keyboard open/Review/rename/preview/Add; Cancel/focus preservation after a
Python parse error; maximum 32 long-name rows; Python rejection of 129 supplementary
code points, acceptance of 128; markup-shaped names remaining text; delayed Add
reply discarded after route exit; repeated Add producing one validation request;
and no Save or clipboard read during the tested Add/Cancel interactions.

| Viewport | Document scroll width | Review/Add/Cancel vertical bounds | Status bounds |
| --- | ---: | --- | --- |
| 840 × 625 | 840 | y=507–538 | x=238–828, y=542–560 |
| 839 × 621 | 839 | y=503–534 | x=238–827, y=538–556 |

The same measurements held with 32 long names and a code-point error. The ordinary
work/commit panes computed to `display: none`; review content scrolled independently.
These are Linux Chromium layout/native-event observations, not WebView2, Windows
scaling or screen-reader observations. The scratch script is not a shipped test;
its observed results are retained here even if `/tmp` is later cleaned.

## Polish completion and approved corrections

Polish used `--fix` mode against `3d77b738cc7758933b44401eb4164a6028ecdde6`.
The checkpoint's main pass and all four controller-owned independent roles were
retained, not rerun or replaced. The resumed implementer completed the outstanding
full-content read of `wingman/ui/api.py:1051–5900`; together with the earlier
partitions this closes the API reading gap. No unrelated change was inferred from
that coverage. Repository ES5 and established imports take precedence over generic
modernization advice. No new reviewer/subagent was dispatched.

| Finding / origin | Disposition |
| --- | --- |
| Minor, HIGH: incoming rows omit probe counts (code-reviewer) | Fixed as an approved-spec correction: derive `f.probes.length` directly in each existing name label. Both visible text and the input's accessible name now distinguish one and two probes. No stored count, API field, CSS or generic abstraction. |
| Important, HIGH: pending Delete silently retargets after a read replaces the selected index (silent-failure-hunter; controller-confirmed in Chromium) | Fixed by capturing the formation object, its document array and load generation. The callback refuses a changed session, document or selected object instead of splicing an unrelated row. |
| Low, HIGH: route-exit comment claims confirmations are invalidated, but Delete was not guarded (comment-analyzer) | Deduplicated with the Delete defect. Fixed behavior, not narrowed wording. The comment remains accurate for mutation-bearing confirmation callbacks, including Delete after exit/reopen. |
| Type/interface review (type-design-analyzer) | No retained finding; no interface change made. |

These were explicit controller-approved semantic corrections, not unreviewed
behavior-preserving auto-fixes. Final self-polish found no further in-scope fix.
No import became orphaned. Scope inspection found no placeholders, debug output,
new dependency/route, account-file or clipboard access, or unrelated cleanup.

### Reviewer-facing explanation

The cross-account tests above exercise the entire production lifecycle using
real file publication, backup, revision and domain logic with only external seams
controlled. The resumed corrections close two UI gaps found independently after
that checkpoint. Smoke checks now cover both, and the design's status links here
instead of claiming implementation has not started. Its requirements are unchanged.

Delete previously captured `f` for the prompt alone, then called
`splice(state.selected, 1)` when Yes arrived. Starting Reload advances generation,
but a dialog opened **after** that start samples the same generation as its read.
Successful read publication replaces the formation array and objects without
another generation increment. A generation-only fix therefore misses the exact
reported failure; a same-ID/name check also fails when a new document reuses them.

The callback now first rejects No and stale routes/generations without reporting
into another session. In the same session, a changed document array or selected
object leaves every row, sharing tick and dirty flag intact and reports:
“The formation changed while confirming. Nothing was deleted. Choose Delete again.”
A fresh Delete can then be canceled or confirmed normally. The existing live-edit
path still marks a valid deletion dirty and removes only that object's sharing
selection. Save completion advances its committed baseline without reloading over
that newer deletion, so a subsequent explicit Save can submit the retained draft.
There is no blanket busy guard or editor disabling.

Counts use the existing associated `<label>` rather than a second description or
stored metadata. Conflict descriptions, name editing, projection, tab order and
layout remain unchanged. Chromium's accessibility tree confirms the count forms
part of the computed input name; that is not a screen-reader test.

### Fresh post-polish commands and results

| Command | Observed result |
| --- | --- |
| `uv run --no-sync python -m pytest tests/test_formations_page.py -k 'delete or paste-batch' -q` before production correction | **RED:** 6 failed, 1 passed, 71 deselected in 6.05s. Missing count plus five stale-deletion failures; ordinary live Delete during Save already passed. |
| Same focused command after correction | **GREEN:** 7 passed, 71 deselected in 7.11s. |
| `node .superpowers/sdd/probe-formation-sharing-plan/task-6-browser-regressions.cjs` before correction | **RED:** six corresponding failures, live Delete during Save passed. Real page-owned dialog: `"Test" is removed when you save.` then old Yes removed `External B`, leaving `[Drifter]`. No Save in the Reload case. |
| Same Chromium command after correction, then again during final gates | **GREEN:** all seven scenarios passed, no page errors. Reload's old Yes retains `[External B, Drifter]`; stale selection/session answers preserve their lists. |
| `uv run --no-sync python -m pytest tests/test_formations_page.py tests/test_profiles_page.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_api_evesettings.py -q -rs` | **737 passed in 106.49s**; no skips. |
| `uv sync --locked --extra dev` | Exit 0; resolved 55 packages, checked 38. |
| `uv run --no-sync python -m pytest tests/ -q -rs` | First resumed full run: **1 failed, 6,124 passed, 9 skipped in 203.38s**; unrelated updater timing failure described below. Fresh serial rerun: **6,125 passed, 9 skipped in 210.23s**. |
| `uv run --no-sync python -m pytest tests/test_api_updates.py::test_process_handle_close_failure_does_not_abandon_a_launched_installer -q` | **1 passed in 2.96s**, immediately after the full-run failure; no code changes. |
| `uv run --no-sync ruff check .` | All checks passed. |
| `uv run --no-sync ruff format --check .` | 284 files already formatted. |
| `node --check wingman/web/formations.js`, `node --check wingman/web/dev.js`, `node --check tests/fixtures/formations_page.cjs` | All exit 0. |
| `git diff --check` | Exit 0. |
| `cargo test --offline --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir .superpowers/sdd/probe-formation-sharing-plan/codec-target` | **1 passed**, no failures/ignored tests; exit 0. No source/lock/dependency edits. |
| `uv run --no-sync python -m pytest tests/test_evesettings_codec.py -q -rs` | **72 passed in 2.61s**, real-codec round trip ran. |
| `uv run --no-sync python -m pytest tests/test_api_evesettings.py -k 'shared_formation_lifecycle or shared_formation_account_boundary' -q -rs` | **52 passed, 234 deselected in 10.14s**; both codec transports ran. |
| `node /tmp/task5-browser.cjs` | Fresh **PASS**, no page errors; existing native sharing/keyboard/rename/32-row floor checks retained. |
| `sha256sum packaging/bin/wingman-settings-codec` and `git check-ignore` for binary/target directory | Same checkpoint SHA-256 above; both artifacts remain ignored. Native binary preserved, no integration setup repeated. |

The failed full-run assertion was `tests/test_api_updates.py:1407`, expecting
`shutdown == [True]` but observing `[]`. Read-only inspection found a timing window:
`_join_update` samples `api._update.worker`, which the install worker clears before
closing the process handle and invoking shutdown. If the helper samples after
that clear, it does not join. The updater test and implementation are unchanged
from the resumed checkpoint. No unrelated fix, assertion weakening or hook bypass
was made. The isolated and serial full reruns passed, but this evidence does not
claim the timing window is repaired. All nine final skips are the same Windows-only
cases enumerated above; no Node/native-codec scenario skipped.

### Native Chromium boundary and reviewer focus

The scratch regression script opens its own browser context/tab on Chromium
152.0.7977.64 and closes the context in `finally`. It runs actual production JS,
HTML, CSS and `WM.confirm`; only delayed file bridge replies and save completions
are controlled. Sharing responses use the production Python endpoints. Clipboard
writes are page-local captures and reads throw without consulting the OS.

The five stale cases cover explicit Reload, post-save reread, route exit,
exit/reopen **before its entry read resolves**, and selection change. Route and
selection events are injected under the real modal; this does not claim a pointer
can click through it. Node additionally replaces a document with identical local
ID/name and different geometry, proving identity rather than label equality. The
sixth deletion case confirms live deletion during Save and the next Save's baseline.
The count case inspects visible labels and Chromium's computed accessibility names
for `1 probe` and `2 probes` at both floors, then cancels with focus restored.
No OS clipboard or real account files are involved in these browser scenarios.

At 840×625, Add/Cancel remain y=507–538 and status y=542–560/right=828; at
839×621 they remain y=503–534 and status y=538–556/right=827. Document widths
remain exactly 840 and 839. The separate refreshed 32-long-name/error checks have
the same pinned-action bounds. No new CSS was needed.

Review the distinct object/document/session guards and their ordering, especially
why busy and edit revision are not blanket confirmation invalidators. Preserve the
same-byte/guarded-publication tests and the explicit separation between page-local
behavior, native codec fidelity and live-EVE acceptance. Independent task/branch
review remains separate from the four completed polish roles.

### Knowledge check for reviewers

1. Why does sharing project selected draft values instead of reusing selective-copy output or serializing an account response?
2. When must a committed Save advance the content baseline even though newer local edits prevent a reload?
3. Why is the shared-meter conversion separate from ordinary load normalization, and what do the accepted range bounds guarantee?
4. Which distinct identities prevent stale Add and Delete replies from changing a replacement document or another session?
5. Which checks prove actual recipient-file/codec behavior, which prove only page behavior, and which release gates remain unverified?

## Final independent review and controller verification

The final reviewer inspected all 21 changed files in
`57ce91dfea854d23714b8209db3c3e6ced854e73..689493c343933519b088999d969836538a83925e`
against the approved design, plan and relevant callers. Verdict: no Critical,
Important or new actionable Minor finding; code ready subject to fresh checks,
**not release-ready**. Task 6's separate review also approved its production-boundary
coverage and both polish corrections. No final code-fix wave was required.

The controller independently verified the same committed implementation while the
review proceeded (not just implementer reports):

- `uv sync --locked --extra dev`: resolved 55 packages, checked 38, exit 0.
- `uv run --no-sync python -m pytest tests/ -q -rs`: **6,125 passed, 9 Windows-only
  skips in 204.25s**. No updater failure in this run; the earlier observed timing
  window remains documented and unfixed.
- `uv run --no-sync ruff check .` and `uv run --no-sync ruff format --check .`:
  clean; 284 files already formatted.
- `node --check` on `wingman/web/formations.js`, `wingman/web/dev.js`, and
  `tests/fixtures/formations_page.cjs`: all exit 0.
- The same offline/locked release `cargo test` command recorded above: **1 passed**.
  The native-codec Python integration also ran within the full suite; no codec or
  Node scenario skipped.
- Both recorded Chromium scripts were inspected and rerun: all seven Delete/count
  regressions and the sharing/Unicode/keyboard/32-row scenarios passed. Tabs/contexts
  were closed; clipboard boundaries stayed page-local and file replies stayed
  controlled. These remain Linux-browser observations, not the manual gates below.
- Current CI's WebView2 predicate-token comparison and build-action `uv run`
  invocation check both passed locally. Version derivation is covered by the
  current packaging tests, not a reinstated comparison of removed version literals.
- `git diff --check` and tracked worktree status were clean.

Only documentation completion records follow this reviewed/tested implementation;
no production or test code is changed by recording these outcomes. The branch has
not been pushed, merged, or released. Its fork point is recorded above; integration
with later changes on `main` requires its own verification.

## Controller rulings retained from the execution ledger

The following decisions were recorded in the ignored `progress.md`; their rationale
must survive scratch cleanup:

1. **Share the actual-markup test parser.** Task 2 review found duplicate HTML
   parser ownership. The controller authorized one test-only
   `tests/html_tree.py:PageTree` consumed by Formations and Fittings instead of the
   plan-mandated duplicate. The requirement was actual-markup execution, not two
   copies of the parser. This is the smallest durable fix; its cost is coupling
   the two wrappers, so both suites must be rerun. It is reversible and authorized
   no production restructuring.
2. **Allow normal Linux scratch/cache semantics.** Earlier wording forced tests
   onto `/mnt/c`, causing permission/case/timestamp failures unrelated to product
   behavior. The controller authorized ordinary test-owned `/tmp` scratch and tool
   caches while keeping repository/persistent-user-state changes inside the
   worktree. The cost is disposable test/cache files outside the worktree, not
   authorization to touch persistent user/EVE data. Full tests must run normally,
   rather than accepting those environmental failures.

## Unverified gates and remaining release obligations

- **OBSERVED — unrelated updater test timing window.** One full run failed at the
  shutdown assertion described above; isolated and serial full reruns passed.
  The updater is unchanged and the window is not claimed fixed.
- **UNVERIFIED — packaged Windows/WebView2.** No Windows application launch,
  100/125/150/200% scaling, actual Windows junction handling for these new tests,
  keyboard/platform integration or screen-reader pass ran here.
- **UNVERIFIED — real OS clipboard.** Linux checks used page-local boundaries only;
  permission behavior and transfer through real Windows clipboard still need a
  deliberate manual test.
- **UNVERIFIED — two-account live EVE.** No real profile was opened or modified.
  With authorization and prepared unrelated-account copies/backups, verify actual
  probe geometry/ranges, selected formation, unrelated settings, source integrity,
  EVE-closed refusal and Backups-manager restoration as specified in the
  [Probe formations smoke checklist](smoke-checklist.md#probe-formations-profiles--edit-formations).
- **KNOWN LIMIT — optimistic stale checks.** Another process can still write after
  the final hash check; this is not an atomic compare-and-swap. EVE must remain
  closed and external editors idle during Save. No force-save or automatic merge
  is provided.
