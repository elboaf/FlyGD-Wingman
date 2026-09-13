# Named group Back keybinds — verified implementation

## Final engineering verification — PASS

Reviewed code/test commit: `29db34b75641fa413a7209bcbd28a68593ed65fc`.
Base: `4a6db85a6a90c18515baf0fb122080ba0c81e0cb`, still `origin/main` when
rechecked before external review. Branch: `feature/preview-group-backward`.
These final evidence notes are a separately inspected documentation-only update;
they are not represented as part of the earlier CodeRabbit-reviewed bytes.

- Independent general and silent-failure re-review closed **GA211-1, SF211-1 and
  SF211-2**. No new change-specific findings. Comment and type checks found none.
  Full current-file coverage includes all18 changed files, with the five correction
  files reread through EOF. No speculative cleanup or unrelated refactor applied.
- Actual CodeRabbit CLI, once in normal committed mode, reviewed all18 files against
  the exact base: **exit0, `review_completed`, zero findings**. No review ID emitted,
  retries, light mode, credits override or substitute reviewer.
- Fresh coordinator full suite after external review: **12405 passed,13 skipped
  in336.34s**. JUnit independently parsed:12418 total, zero failures/errors. Every
  skip identity/reason matches the previous full run and requires Windows; no
  Node, codec, filesystem or font-availability skips.
- Fresh Ruff check and format check passed (**435 files**), all seven changed
  JS/CJS syntax checks and all-page Node smoke passed, independent Cargo regression
  **1 passed**, and whitespace/source-identity checks passed.
- The reviewed source matches the final private Chrome evidence:8 new cases with
  72 checks,10 existing interaction cases,30 geometry cases. This is browser
  verification, not Windows/WebView2/native hotkey/DPI/live-EVE acceptance.

Exact coordinator commands, from this linked checkout:

```bash
coderabbit review --agent --committed --base-commit 4a6db85a6a90c18515baf0fb122080ba0c81e0cb
unset PYTHONPYCACHEPREFIX
PYTHONDONTWRITEBYTECODE=1 /tmp/wingman-preview-group-backward-venv/bin/python -B -m pytest tests/ -q -rs --tb=short -p no:cacheprovider --basetemp=/tmp/wingman-211-final-29db34b7-coordinator --junitxml=.superpowers/sdd/preview-group-backward/post-review-final/full.xml
/tmp/wingman-preview-group-backward-venv/bin/ruff check --no-cache .
/tmp/wingman-preview-group-backward-venv/bin/ruff format --check --no-cache .
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-group-backward-cargo
git diff --check 4a6db85a..HEAD
```

`node --check` also ran for `previews.js`, `dev.js`, the Wanderer runtime script,
and the four changed CJS fixtures. Before the full gate, Node26.5.0, Python3.11.15,
editable wingman5.6.2 resolving THIS checkout, and THIS checkout's installed release
codec availability/path were verified. Test data remained in case-sensitive Linux
`/tmp`, bytecode/cache disabled; only evidence lives in the ignored worktree path.
Raw CodeRabbit output is `coderabbit-29db34b7.log`; final environment/static/Cargo
logs and full XML/log are under `post-review-final/`, beneath the existing evidence
root. All failed earlier gates remain preserved as historical evidence below.

### Remaining limits and deliberately unchanged behavior

- **Windows/WebView2/native/EVE acceptance remains NOT RUN.** Publication/CI and
  operator smoke acceptance are separate gates; a local pass does not imply them.
- A reviewer reproduced a pre-existing deferred-crop caret/focus limitation: arm
  capture, focus Add and select text, receive a roster-changing crop push deferred
  behind capture, then change the selection (or focus another field and blur)
  before Escape. The older crop edit can still restore its prior caret/focus.
  The same stale-owner behavior was demonstrated on base4a6db85a, initial64010b95
  and current29db34b7. The reported ordinary crop direction-loss case is fixed;
  broader deferred-crop/capture ownership hardening is deliberately separate.
  This limitation is not hidden behind the passing ordinary-push tests.
- No downgrade-retention promise for the new optional field: an older binary may
  discard fields it does not understand. Existing forward settings/APIs, All
  cycling and runtime authority remain compatible on upgrade.
- No merge, issue closure or publication is implied by this verification record.

---

## Historical review correction round 1 — scoped verification PASS

Follow-up to `64010b9566b7ea1252517a6698feecd4dbc0e79b`. Final local commit is
recorded in `.superpowers/sdd/preview-group-backward/review-fix-1-report.md`.
Production scope is **only `wingman/web/previews.js`**; associated changes are
`tests/test_preview_group_backward.py`, `tests/fixtures/preview_group_backward.cjs`
and `scripts/test_wanderer_runtime.js`. No backend/schema/cycling/CSS/native changes.

- **GA211-1:** capture stable manager control/group identity before Rename/Delete
  opens its own panel dialog. A revocable local lease tolerates dialog focus and
  the panel's single synchronous dismissal fallback, not a newer field/pointer,
  navigation, capture, disclosure closure or queued dialog. Recover the current
  matching control before starting the mutation, using today's draft rather than
  the pre-dialog text. Cancel restores the stable invoker without a write; normal
  mutation receipt recovery still uses the existing Add field behavior.
- **SF211-1:** screenshot entry uses an empty local draft; cleanup restores the
  saved live text/selection through a one-shot boundary snapshot, with focus
  explicitly excluded. Replacement fixtures start fresh too. Latest live payloads
  and marker acknowledgements keep their independent authority. A pending first
  hydration also uses an explicit empty live default, never outgoing fake text.
- **SF211-2:** the existing crop roster restoration now carries and restores
  selection direction along with start/end; it does not add another focus owner.
- Wanderer's partial capture VM includes the real updated state/helpers and
  asserts that capture revokes both pending manager recovery and its dialog lease.

### Test-first and verification evidence

All new artifacts are under `.superpowers/sdd/preview-group-backward/review-fix-1/`;
older evidence remains untouched. Commands run from THIS worktree, with
`PYTHONPYCACHEPREFIX` unset, `PYTHONDONTWRITEBYTECODE=1`, dedicated editable
`/tmp/wingman-preview-group-backward-venv/bin/python`, Node v26.5.0 and THIS checkout's
release codec availability verified. All pytest basetemps are case-sensitive `/tmp`.

| Gate | Actual result | Artifact |
|---|---|---|
| Three primary regressions on unfixed64010 | 3 failed,53 deselected,4.02s; own-dialog focus, live/fake text and backward direction assertions | `red.xml`, `red.log` |
| Dialog ownership matrix | 6 passed,50 deselected,7.61s | `dialog-green.xml` |
| Related screenshot/Wanderer/group/marker | 216 passed,39.19s,0 skips | `related-green.xml` |
| Unhydrated fixture boundary regression | 1 failed,56 deselected,4.01s; fake text on cleanup | `unhydrated-red.xml` |
| Fresh final focused gate | **1274 passed,1 skipped,69.08s** | `final-focused.xml`, `final-focused.log` |
| Ruff / format / JS syntax / all-page Node / whitespace | PASS;435 formatted files | `final-static.log` |
| Fresh private Chrome840x625 +839x621 | 8/8 cases,72 inner checks;0 page/console errors | `browser-final/results.json`, PNGs |
| Existing #211 controls/lifecycle/G1/marker first native select opening | 10/10 cases | `browser-existing-final/results.json`, PNGs |
| Existing six-width geometry | 30/30 cases at839/840/841/873/874/1280 | `layout-final/results.json`, PNGs |

The sole final skip is `tests/test_preview_host.py:1860`, requiring a real Windows
message pump/window station; no Node/codec skips. New Node scenarios cover both
operations, receipt/push orderings, applied/refused/cancel outcomes, eleven newer
owner types, fixture replacement/latest push/first hydration and both crop selection
directions. Browser fixture cases also settle a real live marker receipt during
staging and verify it survives cleanup; no fixture group writes occur.

Exact final commands:

```bash
unset PYTHONPYCACHEPREFIX
PYTHONDONTWRITEBYTECODE=1 /tmp/wingman-preview-group-backward-venv/bin/python -m pytest tests/test_preview_group_backward.py tests/test_settings_preview.py tests/test_preview_cycle.py tests/test_preview_host.py tests/test_preview_wiring.py tests/test_preview_runtime_boundaries.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_preview_labelmarkers_page.py tests/test_preview_warning_grouping.py tests/test_js_smoke.py tests/test_new_screenshots.py tests/test_wanderer_page.py tests/test_wanderer_controller.py -q -rs --tb=short -p no:cacheprovider --basetemp=/tmp/wingman-211-rf1-final --junitxml=.superpowers/sdd/preview-group-backward/review-fix-1/final-focused.xml
PYTHONDONTWRITEBYTECODE=1 /tmp/wingman-preview-group-backward-venv/bin/ruff check .
PYTHONDONTWRITEBYTECODE=1 /tmp/wingman-preview-group-backward-venv/bin/ruff format --check .
node --check wingman/web/previews.js
node --check tests/fixtures/preview_group_backward.cjs
node --check scripts/test_wanderer_runtime.js
node scripts/js_smoke.js
node .superpowers/sdd/preview-group-backward/review-fix-1/browser-review.cjs browser-final
node .superpowers/sdd/preview-group-backward/browser.cjs review-fix-1/browser-existing-final
node .superpowers/sdd/preview-group-backward/layout-regression.cjs review-fix-1/layout-final
git diff --check
```

Fresh browser/test source `previews.js` SHA256:
`710d71e04202b2a075ac8b3cb5e80f3aeec00a11b4c4a03164acb2d38ee061f1`.
Inspected representative final PNGs for839 own-modal/unbroken-warning layout and
840 fixture boundary. Interaction/selection assertions are recorded in JSON, not
inferred from screenshots.

Retained unsuccessful attempts: `crop-green.xml` exposed a new test reusing
revision10 after11 (correctly rejected); changed only that fixture to monotonic
revisions. `browser-1/` passed28 modal/owner checks plus first fixture check, then
its next iteration toggled a retained open Configure closed. Driver now explicitly
closes each iteration's detail. No arbitrary sleeps, retries of unchanged failures,
assertion weakening or timeout inflation. One shell invocation was denied before
execution because of shell-variable syntax; the direct command then ran the RED.

Local post-implementation inspection applied the polish safety rules to this
bounded diff, with no cleanup/autofix items and no additional known blocker. It
found the same SF211-1 unhydrated boundary, corrected test-first as above. No
subagents/external review were used; coordinator re-review remains authoritative.
**No full suite or independent Cargo regression was run this pass**, per the scoped
brief. The older12400-pass full applies64010 only. No Windows/WebView2/native/live-EVE
acceptance is claimed. Coordinator owns actual CodeRabbit, fresh full and all
publication actions. Reviewer focus: the panel fallback ordering assumption,
revocation after newer focus, and keeping draft snapshots separate from live data.

---

# Historical initial implementation evidence

## Status: PASS — worker verification, independent review pending

The candidate is the commit containing this document, based on
`4a6db85a6a90c18515baf0fb122080ba0c81e0cb` on
`feature/preview-group-backward`. Its final SHA is recorded in the ignored
`.superpowers/sdd/preview-group-backward/implementation-report.md` and
`progress.md` after the ordinary local commit. No amend, hook bypass, external
review or remote action. Coordinator owns independent review, polish, CodeRabbit
and the fresh final publication gate; this is not release/native acceptance.

### Authorized test-seam correction and fresh results

Coordinator `test-seams-ruling.md` authorized the two diagnosed harness fixes and
one fresh full suite after those causal corrections. Production sources did not
change in this continuation:

- `tests/fixtures/screenshot_pages.cjs`: group Clear now selects and asserts the
  intended `Forward · DPS` row and its actual Clear button. Fixture no-write and
  ordinary live-resumption assertions remain intact.
- `scripts/test_wanderer_runtime.js`: bounded capture VM also evaluates the real
  production `groupFocusPending` declaration and `releaseGroupFocus` helper. New
  capture must revoke pending manager focus; native/page capture and exact
  true/false disarm delivery assertions are unchanged. No no-op helper/fallback.
- Repository-wide search of JS/CJS/Python consumers found no other affected label
  lookup or capture extractor. The existing Preview lexical split and Bookmarks'
  separate capture implementation are unaffected.

| Fresh gate | Result | Artifact under `.superpowers/sdd/preview-group-backward/` |
|---|---|---|
| The three originally failing cases | 3 passed in3.48s | `seams-three-green.xml` |
| Related screenshot/Wanderer controller+page/group/marker/warnings | 212 passed in35.66s, no skips | `seams-related-green.xml` |
| Full suite after causal corrections | **12400 passed,13 skipped in329.12s**,0failures | `full-after-seams.xml`, `full-after-seams.log` |
| Independent Cargo | 1 passed,0 failed/ignored | `cargo-after-seams.log` |
| Ruff check / format | PASS /435 files already formatted | `seams-static-green.log` |
| Both changed scripts' Node syntax; all-page Node smoke; whitespace | PASS | `seams-static-green.log` |

All13 skip identities/reasons were compared to the original failed full-run XML:
unchanged Windows-only boundaries, listed below. No Node/codec skips, no timeout
inflation or skipped failure. Original `full-final.xml`/`.log` retain
12397passed/3failed/13skipped; they have not been relabelled or overwritten.

Commands ran from this linked checkout with `PYTHONPYCACHEPREFIX` unset:

```bash
PYTHONDONTWRITEBYTECODE=1 UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-group-backward-venv uv run --no-sync python -m pytest 'tests/test_new_screenshots.py::test_crop_screenshot_blocks_live_controls[group-clear]' tests/test_wanderer_controller.py::test_state_retries_reverse_handoff_and_page_recovers_coverage tests/test_wanderer_page.py::test_wanderer_runtime -q -rs --tb=short -p no:cacheprovider --basetemp=/tmp/wingman-211-seams-three-green --junitxml=.superpowers/sdd/preview-group-backward/seams-three-green.xml
PYTHONDONTWRITEBYTECODE=1 UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-group-backward-venv uv run --no-sync python -m pytest tests/test_new_screenshots.py tests/test_wanderer_page.py tests/test_wanderer_controller.py tests/test_preview_group_backward.py tests/test_preview_labelmarkers_page.py tests/test_preview_warning_grouping.py -q -rs --tb=short -p no:cacheprovider --basetemp=/tmp/wingman-211-seams-related-green --junitxml=.superpowers/sdd/preview-group-backward/seams-related-green.xml
PYTHONDONTWRITEBYTECODE=1 UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-group-backward-venv uv run --no-sync python -m pytest tests/ -q -rs --tb=short -p no:cacheprovider --basetemp=/tmp/wingman-211-full-after-seams --junitxml=.superpowers/sdd/preview-group-backward/full-after-seams.xml
PYTHONDONTWRITEBYTECODE=1 UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-group-backward-venv uv run --no-sync ruff check .
PYTHONDONTWRITEBYTECODE=1 UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-group-backward-venv uv run --no-sync ruff format --check .
node --check tests/fixtures/screenshot_pages.cjs
node --check scripts/test_wanderer_runtime.js
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-group-backward-cargo
git diff --check
```

Editable wingman5.6.2 still resolves THIS checkout; Node26.5.0 and the installed
release codec availability/path/hash were rechecked. Test data stayed under Linux
`/tmp`; only reports/images/logs in the ignored artifact directory.

### Browser evidence applies to byte-identical production

`sha256sum` verified all six source hashes against the earlier report. Therefore
browser10/10 and geometry30/30 below apply unchanged; no new browser run was needed
for this test-only delta. This is reuse of recorded private Chrome evidence, not
fresh Windows/WebView2/native/EVE acceptance.

| Production path | Verified SHA256 |
|---|---|
| wingman/settings.py | 641fefe90881778e2397e499771295af0492e7e9af53e8e5f43c7c189d3098a5 |
| wingman/preview/host.py | 8bfdbecd90c82f6d3bb7a5bec5590e206e89ac146e86951b073cd8ffeb53aeac |
| wingman/ui/api.py | 8c5a8f7c787d16398aea327ac8a4fc62c7d23cb76259807a30ccaa3fefbfb257 |
| wingman/web/previews.js | 31e0e3df180ae8c06c76b24c1047f1d1da712d64a9ec6e23b78464d1f84e4e31 |
| wingman/web/dev.js | 47a8583a37afac44f2c5dc38c2292cf18fbd49a02efd2dc4b10e6d71d6a2b870 |
| wingman/web/style.css | 46242914125493c6c8200726dfb9d18d64d2d4763d0d9e0c5208b5698d371e42 |

### Reviewer focus

Prioritize persisted-field compatibility, all-forwards-before-backs priority,
shared history/revocation and local manager interaction ownership. Explicit Add
clearing remains intentionally separate from ordinary push draft retention. The
approved shared-grid correction preserves roster tracks/width/hit areas. No
Bookmarks reverse-summary expansion, other feature lane, new dependency, runtime
owner or native plumbing change belongs to this candidate.

Knowledge check:
1. Why must every named forward registration precede every new named back?
2. Which existing cursor/history rules govern a reverse action outside its group?
3. How does the narrow back endpoint preserve concurrent forward updates?
4. Which newer interactions revoke pending manager focus recovery?
5. What do the browser and Linux gates leave unverified on Windows?

---

# Historical checkpoint — prior full-suite stop, resolved above

## Status: BLOCKED on the single full-suite gate

Worktree `.worktrees/preview-group-backward`, branch `feature/preview-group-backward`.
Starting/current HEAD: `4a6db85a6a90c18515baf0fb122080ba0c81e0cb`
(`Add per-character preview identification markers (#226)`). No new commit:
source/test changes remain uncommitted because the full gate is not green.
No remote actions or independent review occurred. Coordinator owns polish,
independent review, CodeRabbit and the fresh final publication gate.

The original #211 feature and approved grid work were resumed, not reimplemented.
Production scope remains six files: `wingman/settings.py`, `wingman/ui/api.py`,
`wingman/preview/host.py`, `wingman/web/previews.js`, `wingman/web/dev.js`,
`wingman/web/style.css`. The latest focus correction changes only `previews.js`.

## Behavior and decisions

- Optional group `cycle_prev` normalizes independently. Existing `cycle` remains
  Forward and the exact two-argument forward endpoint remains compatible. A new
  previous-direction endpoint uses the same private writer and persistence lock.
- Native `cycle_group_prev` uses the existing negative step and shared group
  history. Every existing forward registration precedes every new named back;
  UI warning ownership follows that priority despite paired Forward/Back rows.
- The measured grid correction changes gaps and cycle-label containment only:
  3px through873px, 10px from874px; cycle buttons150×30, full text in accessible
  content/tooltips/Edit. Identity210–320px, roster width and cells stay unchanged.
  Unbroken warnings wrap rather than widening/clipping the grid.
- The user-approved manager fix snapshots current control/group identity and Add
  text/selection/direction immediately before rendering. Restore uses exact stable
  attributes, not selector-interpolated IDs or row positions. Native visibility
  includes hidden ancestors and closed details. Removed controls fall back to Add.
- Mutation focus recovery is separate, revoked by newer focus/pointer interaction,
  capture, route/section/tab changes, closing the disclosure or screenshot entry.
  A late receipt cannot pull a new owner back, even if it subsequently blurred to
  BODY. Detached disclosures cannot change current open state through queued toggles.
- Explicit Add attempts retain the existing cleared-field behavior (success and
  refusal); ordinary refreshes retain unsent text. Clearing occurs before the
  submission repaint, not by writing to an already-detached input in the receipt.
  No blur commits, extra reads/writes, timers, sleeps or renderer framework.

## Fresh continuation verification

All pytest runs used THIS checkout's editable wingman5.6.2 and dedicated
`/tmp/wingman-preview-group-backward-venv`, Node26.5.0, unset
`PYTHONPYCACHEPREFIX`, `PYTHONDONTWRITEBYTECODE=1`, `uv run --no-sync`,
`-p no:cacheprovider`, Linux `/tmp` basetemp. Reports only are in the ignored
`.superpowers/sdd/preview-group-backward/` artifact directory. The release codec
was rechecked available at THIS `packaging/bin/wingman-settings-codec`, SHA256
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.

| Gate | Result | Artifact |
|---|---|---|
| Focus tracer RED, current unfixed source | 1failed/48deselected,3.97s; real ordinary-push focus loss | `focus-draft-red-bounded.xml` |
| Focus tracer GREEN | 1passed/48deselected,3.43s | `focus-draft-green.xml` |
| Ownership RED | 2failed/1passed/49deselected,4.37s | `focus-ownership-red.xml` |
| Focus scenarios GREEN | 4passed/48deselected,4.17s | `focus-all-green.xml` |
| Nearby affected tests | 228passed,14.42s | `focus-nearby.xml` |
| Fresh focused suite | 1139passed/1Windows-pump skip,35.43s | `focused-after-focus-guard.xml` |
| Ruff check / format | PASS /435files already formatted | recorded in report |
| All-page Node smoke | PASS index/fleetbar/sigbar modules | recorded in report |
| Single complete pytest | 12397passed/3failed/13Windows-only skips,345.41s | `full-final.xml`, `full-final.log` |
| Independent Cargo | 1passed/0failed/0ignored | `cargo-final.log` |

Focus tests exercise real app/previews/panel handlers over PageTree/deferred bridge
seams: 12 Add/Rename/Delete × ordering × outcome combinations,9 newer-owner cases,
Add selection/direction, stable-ID reorder/rename/removal and capture supersession.
The local test DOM models native removal focus loss, ancestor visibility, focusin
bubbling and selection. No test-only production fallback was introduced.

Preserved harness corrections: the initial RED timed out30s while Node formatted
an enormous cyclic DOM equality failure; boolean identity assertions bounded the
report without changing timeouts or production. Ownership RED also exposed a test
loop failing to reset its prior draft. The first broad focus gate failed an old
lexical Add assertion requiring a clear in the receipt; its placement assumption
was updated, retaining the guard and real completion/refusal coverage. All failed
XML remains. No full-suite retry was performed.

## Browser evidence, not native acceptance

Private Chrome153.0.8010.36, own temporary profiles/local dev page only; no app,
user browser, EVE, user clipboard or live settings. All profiles closed/deleted.

- `group-focus-green/{results.json,baseline.png,current.png}`: matched starting-SHA
  source still drops focus to BODY; current source keeps Add-name after the deferred
  delete push. Original `group-focus-probe/` is untouched.
- `browser-final-spy/results.json`:10/10 passed at840×625 and839×621. Each floor
  covers both direction controls, long labels/warnings/legacy payloads, delayed
  refusal/stale receipts/navigation/rename/delete, back capture → deferred roster →
  first native marker menu, and G1 unsent draft/selection plus Copy Escape.
  Actual create/copy bridge methods are included in the mutation spy. Earlier
  `browser-after-focus/` remains, but its Copy-Escape spy omitted those methods.
- `layout-after-focus/results.json`:30/30 passed (five modes at six widths).
  Grid client/scroll:839→591/591,840→592/592,841→593/593,873→625/625,
  874→626/626,1280→884/884. Actual fonts awaited. Cycle hit areas unchanged.
- Inspected `group-focus-green/current.png`,
  `browser-after-focus/839-marker-first-native-open.png` and
  `layout-after-focus/839-unbroken-conflicts.png`: focus/menu and wrapped warning
  text visible. Final driver also saves corresponding PNGs.

## Confirmed full-suite blockers and next bounded work

1. `tests/fixtures/screenshot_pages.cjs:229` selects group Clear by old literal
   label `DPS`; paired rows now render `Forward · DPS` / `Back · DPS`, so lookup
   returns undefined before exercising the guard. Failure:
   `test_crop_screenshot_blocks_live_controls[group-clear]`. Correct the fixture
   to select the intended Forward owner (and consider the new Back boundary).
2. `scripts/test_wanderer_runtime.js:490–507` extracts only the capture source
   slice into an isolated VM. It now invokes real `beginCapture()` without the
   new local `releaseGroupFocus()` helper, causing ReferenceError. Both
   `test_wanderer_runtime` and
   `test_state_retries_reverse_handoff_and_page_recovers_coverage` run that same
   harness. Include the real local helper/ownership state in that harness (not
   a no-op production fallback), or use existing complete-module seams.

These two harness corrections have NOT been applied: implementation stopped and
source was inspected as requested after the unexpected full-gate failures. The
single full-suite budget is spent. No commit is authorized over this failed gate.
Coordinator must approve the bounded continuation/fresh full-gate policy.

All13 skips are actual Windows boundaries:3 profile-copy junction cases,
2 DPAPI/WinDLL cases,1 preview pump,3 preview Win32 bindings,1 pystray backend,
2 setup-profile junction cases and1 Wanderer user-bound DPAPI case. No Node or
codec skip. Windows/WebView2/DPI/native hotkey/live-EVE acceptance remains NOT RUN;
the appended smoke checklist is an acceptance contract, not a success claim.
