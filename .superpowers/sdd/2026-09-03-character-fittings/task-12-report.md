# Task 12 report: Packaging, Dev Scenarios, Documentation, and Smoke Coverage

## Status

Complete on `feature/fittings-management`, ready for the controller's required
post-task `polish-core --fix` pass. The Task 12 commit is
`docs: complete fittings release integration`.

This worker did not run a real Windows/WebView2 install or a live EVE
Personal-Fittings read/create. Every new Windows/live-EVE smoke item remains
explicitly unverified. `docs/assets/wingman-screenshot.png` was not modified;
no screenshot binary was fabricated from Chromium or the dev harness.

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

The strict `DEV_FITTINGS_COPY_RESULT_FIXTURE` is consumed by screenshot tooling
rather than duplicating crafted outcomes in Python. During final browser review,
the inherited dev-copy implementation was corrected to match production result
semantics: `write_count` counts attempted requests, the pair receiving the
scripted throttle response is Failed/attempted, and only later pairs are
Unattempted due to throttle. A two-fit/three-character run therefore reports
three attempted writes: Success, Unknown, and throttle Failed, followed by
three unattempted rows.

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

The inherited staging needed two correctness fixes found during audit:

- collection switches and page changes resolve through `requestState()`
  promises, while the shooter's `Runtime.evaluate` does not await those
  promises. Reset, the Alliance scope switch, the detail-page advance, and the
  final row action are now separate CDP evaluations with settle boundaries;
  otherwise detail searched stale page 1 immediately after clicking Next;
- copy result data was moved out of the Python shooter into the strict dev
  fixture, preserving `dev.js` as the only fabricated-data source.

Every setup fails closed when its required control/row is absent. Tests also
assert that no Fittings screenshot setup calls a remote or durable writer,
including `fittings_start_copy`, refresh, capability enable, Forget, collection
or metadata mutations. The copy preflight call is classification-only; the
progress/result screens use the page's semantic handler.

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
storage. The exact page was then loaded and force-reloaded:

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

Assertions covered the 100-row default page and page 2, derived collection
views, recent Alliance source evidence, rack/presence detail, all character
access states and stale error, present/conflict/non-deployable preflight,
20-write refusal, progress, every result label, and the real asynchronous dev
copy loop's attempted-write count.

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

Focused Task 12 suites after the final scenario/result fixes:

```text
uv run --no-sync python -m pytest \
  tests/test_packaging_completeness.py tests/test_dev_harness.py \
  tests/test_shoot_screens.py tests/test_page_conventions.py -q
250 passed, 1 skipped in 6.51s
```

The skip is the existing optional built settings-codec artifact check.

Fresh final full suite:

```text
uv run --no-sync python -m pytest tests/
3989 passed, 8 skipped in 62.16s
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
  tests/test_packaging_completeness.py tests/test_page_conventions.py \
  tests/test_shoot_screens.py
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
- The screenshot setup scripts perform no live write. The full Windows shooter
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
