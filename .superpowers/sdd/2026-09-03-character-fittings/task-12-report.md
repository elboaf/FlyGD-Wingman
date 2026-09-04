# Task 12 report: Packaging, Dev Scenarios, Documentation, and Smoke Coverage

## Status

Complete on `feature/fittings-management`, ready for the controller's required
post-task `polish-core --fix` pass. The Task 12 commit is
`docs: complete fittings release integration`.

This worker did not run a real Windows/WebView2 install or a live EVE
Personal-Fittings read/create. Every new Windows/live-EVE smoke item remains
explicitly unverified. `docs/assets/wingman-screenshot.png` was not modified;
no screenshot binary was fabricated from Chromium or the dev harness.

## Fix round 1/5

Review found that the nine variant scripts selected names that existed only in
`dev.js`, while the shooter deliberately launches the query-free live app. The
variants therefore could not succeed on a real machine. The repair follows the
existing Preview injection precedent without introducing a durable or remote
write path:

- `dev.js` now owns one strict, bounded `DEV_FITTINGS_SCREENSHOT_FIXTURE` with
  workspace summaries, details, characters, mixed preflight, and one
  production-reachable copy sequence;
- `app.js` allowlists `onFittingsScreenshotState`, and `fittings.js` owns its
  sole registration. There is no Python producer, startup call, or user
  control for this screenshot-only handler;
- the handler accepts only the versioned shape under 512 KiB with bounded
  characters, collections, entries, details, preflight rows, and result rows;
- while injected, state, detail, and preflight reads are answered page-side.
  A live state request started before injection cannot repaint over the fixture;
  route leave clears the fixture and restores ordinary bridge reads;
- `walk()` injects the fixture before the base Fittings capture and before every
  variant reset/action. Stage scripts invoke no Fittings writer, and the handler
  neither replaces nor calls one, so live EVE and durable local state remain
  untouched; and
- Alliance/detail generation now passes `action="open"` to an explicit helper.
  The previous silent string `.replace(...)` surgery is gone.

The former standalone copy-result JSON was also removed. Its stale Bex failure
and throttle actor could not come from the dev loop. The canonical result now
models two generated fits over Eryn, Fio, and Gio: Success, Unknown, the
throttle-triggering Failed/attempted row, then three Unattempted due to throttle
rows. `write_count` is derived from the three attempted rows. The dev loop's
Unknown/throttle role constants derive from this fixture, `DEV.fittingsScreenshot()`
renders it in a normal dev browser, and Python parses the same object for live
screenshot injection.

Focused tests were added for injection-before-action ordering, exact fixture
serialization, bounded/allowlisted production handler ownership, no Python
producer, local read interception, route-leave cleanup, absence of durable and
remote writers, explicit row-action generation, and fixture actor/status/
attempt consistency. The initial focused run failed in eight places for the
missing handler/injection/canonical fixture and the silent `.replace(...)`
path; the first complete green run was 212 passing tests, followed by the
broader 322-test page/convention set recorded below.

## Inherited work audited and completed

The worktree arrived with uncommitted Task 12 edits in the build action,
packaging tests, generalized page-convention guard, migration/path comments,
`dev.js`, and a large Fittings addition to `scripts/shoot_screens.py`. Those
changes were retained where valid and completed rather than reset.

### Packaging and frozen build

- The explicit setuptools list already contained `wingman.eveauth` and
  `wingman.evefittings` from the earlier package-creation tasks. Task 12 adds an
  explicit assertion for those two names while preserving the existing derived
  all-subpackages check.
- The Windows build action now imports `AuthorityController`,
  `SkillsController`, and `FittingsController` before freezing, so a missing or
  broken package fails where it is actionable.
- The frozen-web asset check now explicitly requires `fittings.js` beside the
  existing page scripts and fonts.

### Dev harness scenarios

`wingman/web/dev.js` remains the only owner of fabricated product data. Its
Fittings fixture now covers:

- the default paged library, Unfiled, Superseded, and Alliance collection;
- a recent Alliance entry with source-character/discovery evidence;
- expanded rack/alias/presence detail;
- enabled, Skills-only, reauthentication-required, and stale/error character
  rows;
- a true different-content/same-name conflict;
- a schema-defined `Invalid`, non-deployable fitting;
- more than 20 otherwise-ready writes;
- asynchronous progress and completion;
- Success, Already present, Conflict/skipped, Unavailable, Unknown,
  throttle-stopped remainder, Cancelled, and Failed results.

The strict `DEV_FITTINGS_SCREENSHOT_FIXTURE` is consumed by both the browser's
manual screenshot driver and Python screenshot tooling rather than duplicating
crafted outcomes. Its reachable two-fit/three-character result reports three
attempted writes: Success, Unknown, and throttle Failed, followed by three
unattempted rows.

`tests/test_dev_harness.py` now explicitly proves every bridge method called by
`fittings.js` has a double and pins the fixture's import/access, conflict,
Invalid, 20-write, progress, partial, Unknown, cancellation, and throttle
states.

### Screenshot inventory and staging

The single `SCREENS` inventory now contains the base Fittings route plus nine
Fittings variants:

1. Unfiled;
2. Superseded;
3. recent Alliance import;
4. expanded detail;
5. Characters/access and stale state;
6. mixed copy preflight;
7. over-20 refusal;
8. copy progress; and
9. partial copy results including Unknown.

All are EVE-gated, so gate-off runs skip and record every Fittings stage. Counts
in `tests/test_shoot_screens.py` are derived from `SCREENS` rather than repeated
integers or hand-maintained skip lists.

The final staging injects the canonical dev fixture into the query-free page
before any stage action. Collection/reset/action boundaries remain separate CDP
evaluations, and every required control/row fails closed. State, detail and
preflight are local read paths in screenshot mode; no Fittings screenshot setup
calls `fittings_start_copy`, refresh, capability enable, Forget, collection,
metadata, membership, supersession, delete, or any other durable/remote writer.
Progress/results use the same semantic handler as the controller.

### Page convention guard

The inherited hidden-state guard was generalized and retained:

- JavaScript modules are derived from `web/*.js` instead of manually listed, so
  `fittings.js` and future modules are included automatically;
- inline HTML `display:` declarations are detected across quoting/spacing and
  combined-style variations; and
- JavaScript dot notation, bracket notation, and `style.setProperty('display',
  ...)` are rejected.

`dev.js` remains the sole excluded module because its purpose is to fabricate
and stage internal browser state. The assertion message was corrected during
self-review so a violation reports the actual matched expression.

### Documentation and smoke coverage

- `PRODUCT.md` now lists Fittings as a secondary fleet-preparation destination
  and records why it is a destination rather than Settings configuration.
- `README.md` documents Personal-Fittings ingestion, local persistent files,
  both fitting scopes, exact-character per-row consent, Skills-only continuity,
  explicit additive writes, no automatic delete/replace, Unknown reconciliation,
  global Forget semantics, the EVE gate, and the external EVE application
  registration prerequisite.
- `DESIGN.md` records the final cleared-cache CDP recheck of the completed route
  at both known CSS floors while retaining the explicit limitation that this is
  not Windows/WebView2 DPI evidence.
- `docs/smoke-checklist.md` now has a complete EVE Fittings section covering
  pre-feature migration, fail-closed migration retry, Skills-only continuity,
  row-bound capability upgrade, wrong-character refusal/cancellation, real
  Personal-Fittings reads, deduplication, recent/source filtering, Alliance
  ingestion, collection/supersession curation, Invalid fits, paging/focus,
  every preflight/result class, the 20-write bound, real additive create,
  Unknown/cache-horizon reconciliation, cancellation, throttle, Forget races,
  restart after every durable mutation, EVE-gate routing, installed
  `fittings.js`, and title-bar geometry at 100/125/150/200% scaling.
- The inherited migration comment now records the deliberate one-save-cycle
  credential exposure in `eve_skills.json.bak`; the path docstring names the
  production startup migration rather than a future task.

## Browser verification actually performed

Chrome was attached over CDP after clearing its browser cache and file-origin
storage. Fix round 1 first loaded and force-reloaded the exact query-free
production page:

```text
file:///mnt/c/dev/flygd-wingman/.worktrees/fittings-management/wingman/web/index.html
```

`dev.js` remained inert (`window.DEV` absent). The shooter fixture was injected
through `onFittingsScreenshotState`, and all base/variant actions below rendered
without a Python bridge or a live state dependency. The browser then loaded the
exact dev page to verify `DEV.fittingsScreenshot()` consumes the same fixture
and to run the real asynchronous dev-copy loop:

```text
file:///mnt/c/dev/flygd-wingman/.worktrees/fittings-management/wingman/web/index.html?dev=1
```

The final pass exercised these states through the real page controls and
handlers, with no console or page exceptions:

```text
fittings
fittings-unfiled
fittings-superseded
fittings-alliance
fittings-detail
fittings-characters
fittings-copy-preflight
fittings-copy-limit
fittings-copy-progress
fittings-copy-result
fittings-copy-actual
```

Assertions covered the injected 27-row live-page state, derived collection
views, recent Alliance source evidence, rack/presence detail, all character
access states and stale error, present/conflict/non-deployable preflight,
20-write refusal, progress, the reachable copy-result sequence, and the real
asynchronous dev loop's attempted-write count. The ordinary dev fixture still
exercised its >100-row paging separately from screenshot injection.

Final browser-side title-bar measurements:

| CSS width | scroll/client | drag width | nav edges | close edges | labels |
|---|---:|---:|---:|---:|---|
| 840 | 840 / 840 | 379.859375 | 405.859375–672 | 790–834 | all four |
| 839 | 839 / 839 | 378.859375 | 404.859375–671 | 789–833 | all four |

At both widths the page had no horizontal overflow, close remained inside the
client width, the drag region exceeded its 105px floor, and Uploader, Profiles,
Skills, and Fittings remained visible.

This verifies deterministic Chromium rendering only. It does not verify
pywebview, WebView2, WinForms DPI rounding, installed assets, EVE SSO, ESI, or a
real fitting mutation.

## Automated verification actually performed

Focused screenshot/dev/page/bridge suites after fix round 1:

```text
uv run --no-sync python -m pytest tests/test_shoot_screens.py \
  tests/test_dev_harness.py tests/test_fittings_page.py \
  tests/test_bridge_contract.py tests/test_page_conventions.py -q
322 passed in 10.52s
```

Fresh final full suite after fix round 1:

```text
uv run --no-sync python -m pytest tests/
3996 passed, 8 skipped in 66.86s
```

Fresh static gates:

```text
uv run --extra dev ruff check .
All checks passed!

uv run --extra dev ruff format --check .
233 files already formatted

node --check wingman/web/*.js
14 JavaScript files passed node --check

python -m py_compile scripts/shoot_screens.py tests/test_dev_harness.py \
  tests/test_fittings_page.py tests/test_shoot_screens.py
# exit 0

git diff --check
# exit 0
```

## Final requirement and scope review

- The final diff contains only the expected Task 12 build, docs, dev harness,
  screenshot tooling, tests, and inherited comment corrections. No unexpected
  path was changed.
- Added lines contain no TODO, FIXME, XXX, debugger, `console.debug`,
  `NotImplementedError`, or new credential placeholder.
- `docs/assets/wingman-screenshot.png` has no status or diff. Its existing
  three-destination capture was not rewritten or relabeled without a real
  Windows capture.
- No remote fitting DELETE route or delete transport was added. Fittings uses
  the single `POST_PATH` through `post_once`; existing copy tests verify exactly
  one mutation attempt and no retry.
- Existing full-suite coverage remains green for Skills-only grants and refresh,
  fail-closed migration with no authority/completion marker, durable intent
  before POST and no send after intent-save failure, startup conversion to
  Unknown, post-horizon unconditional `200` reconciliation, `304` refusal, and
  Unknown blocking copy/Forget after failed reconciliation persistence.
- The screenshot setup scripts perform no live write. The query-free production
  page was exercised over CDP with `dev.js` inert, but the full Windows shooter
  itself was not run in this Linux environment.

## Explicitly unverified / remaining release risk

All new Windows/live-EVE checklist boxes remain open, including:

- migration of an actual pre-feature user file under Windows/DPAPI;
- Skills-only refresh after that real migration;
- exact-character EVE consent and wrong-character refusal;
- registered-application acceptance of both fitting scopes;
- live Personal Fittings read, deduplication, and additive create;
- real cache-horizon/Unknown reconciliation, cancellation, throttle, and Forget
  races;
- frozen `_internal\web\fittings.js` lookup;
- WebView2 focus/overlay behavior;
- title-bar geometry at 100%, 125%, 150%, and 200%; and
- a replacement product screenshot captured from the real Windows app.

No claim in this report treats `?dev=1` as evidence for those paths.

## Polish status

`polish-core` was intentionally not run, per the resumption instruction. The
controller will run it after reviewing this committed Task 12 slice.
