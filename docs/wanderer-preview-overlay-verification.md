# Wanderer preview overlay — verification record

## Connection-form follow-up — separate scoped evidence

After baseline `d81ed329`, the approved connection-form simplification is implemented
in `19699ca2` (protected snapshots), `c4d2b5ff` (grouped controller/API), and
`69d65d3f` (ES5 form/dev fixtures). The parent completed the post-polish checks
below against **`fdeca0c305e81a7b5460c9e5f8652e94d36a9dd3`**; the subsequent
changes are documentation only. **Sections after this follow-up describe the
previous candidate, not fresh acceptance of this form.** No running app,
test-profile credential or live service was inspected or changed by this work.

Test connection now saves submitted URL/map/token together, then requests Test
without changing the enable preference. Blank token reuse requires the currently
acknowledged normalized URL/map; an older matching credential file is not reused.
Remove confirms against a configuration revision and clears URL/map/token, keeping
the independent enable preference. Each input retains draft ownership even though
the save is grouped. The old Apply/Replace buttons and per-field bridge endpoints
are removed. Existing HTTP serialization, expiry scheduling and native rendering
are unchanged.

The persistence boundary snapshots at most 16 KiB of protected document bytes,
writes the candidate protected credential, saves settings, then commits runtime
once. Settings failure restores the exact prior protected bytes (or absence)
without admitting candidate work. Compensation failure closes admission and
returns an explicit safe `persistence_error` acknowledgement; the page must not
advertise a retained old Test success. This is bounded in-process compensation,
**not a crash-atomic transaction or durable recovery journal**.

The bridge now exposes `test_wanderer_connection(base, map, token)` and
`remove_wanderer_connection(revision)`, alongside unchanged `wanderer_state()` and
`set_wanderer_enabled(enabled)`. Test returns configuration
`applied/persisted/error/acknowledged` separately from
`test_accepted/test_error/test_generation`; asynchronous outcomes remain in health
state. A successful save is never reported as a persistence refusal merely because
Test could not start.

Observed test-first checkpoints: credential snapshot tests **3 failed / 45 passed**
before implementation, then **48 passed**; grouped controller tests **29 failed /
20 passed** before implementation, then **49 passed**; production Node form tests
**20 failed / 39 passed** before implementation. A final self-review regression
caught a retained old Test success after reopening failed-compensation state
(**1 failed / 59 passed**) before its presentation fix.

Fresh Linux verification on the completed code, using the existing locked venv:

```sh
/tmp/wingman-wanderer-venv/bin/python -m pytest tests/test_wanderer*.py tests/test_preview_metadata.py tests/test_preview_wiring.py tests/test_api.py tests/test_api_settings_fields.py tests/test_settings_transactions.py tests/test_settings_page.py tests/test_settings_runtime.py tests/test_dev_harness.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_js_smoke.py tests/test_packaging_completeness.py -q -rs --tb=short
node scripts/test_wanderer_runtime.js
node scripts/js_smoke.js
/tmp/wingman-wanderer-venv/bin/ruff check .
/tmp/wingman-wanderer-venv/bin/ruff format --check .
git diff --check
```

Results: **1,255 passed, 1 skipped** in 36.62s; the sole skip is real Windows
user-bound DPAPI (`test_real_windows_credential_document_roundtrip_replace_binding_and_remove`).
Node ownership: **60 passed, 0 failed**. JS smoke: all three pages passed.
Ruff lint passed; **398 files already formatted**. These are the implementation
checkpoint results, not the parent-owned post-polish gates below.

### Parent post-polish verification

The scoped `polish-core --fix` pass covered `d81ed329..fdeca0c3`. It found no
blocking correctness/security issue and no safe code edits. One obsolete README
sentence still named Apply; that sentence was removed and the edit inspected.
The following fresh verification ran afterward without production changes:

| Gate | Result |
|---|---|
| Complete Linux pytest | **11,095 passed, 12 Windows-only skips**, 228.10s |
| Windows Wanderer/bridge/page/packaging selection | **783 passed, 1 skipped**, 8.33s; sole skip is an unrelated packaging symlink-privilege test |
| Node ownership harness | **60 passed, 0 failed** |
| Executable JS smoke | All three pages passed |
| Ruff lint / format | Passed; **398 files already formatted** |
| Browser/CDP at 839/840/1280px | No horizontal overflow, all controls within card, no page/resource errors; URL draft survived health push |
| Windows PyInstaller build and archive/asset inspection | Passed; all six Wanderer modules present, current web bytes match source, bundled Inter bytes match and font loads |

Commands used the existing locked environments and Node/native codec prerequisites:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wanderer-form-final-linux --junitxml=/tmp/wanderer-form-final-linux.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff format --check .
node scripts/test_wanderer_runtime.js
node scripts/js_smoke.js
node .superpowers/sdd/wanderer-preview-overlay-plan/browser-check.cjs
```

Windows PowerShell, with `UV_PROJECT_ENVIRONMENT=%TEMP%\wingman-wanderer-venv`
and the previously prepared Node directory on the process PATH:

```powershell
$tests = Get-ChildItem tests/test_wanderer*.py | Select-Object -ExpandProperty FullName
uv run --no-sync python -m pytest @tests tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_packaging_completeness.py -q -rs --tb=short --basetemp="$env:TEMP\wanderer-form-final-windows"
uv run --no-sync python -m PyInstaller packaging/uploader.spec --noconfirm --clean --distpath dist/wanderer-form-check --workpath build/wanderer-form-check
uv run --no-sync python .superpowers/sdd/wanderer-preview-overlay-plan/inspect_frozen.py dist/wanderer-form-check/Wingman
```

New artifact: `dist/wanderer-form-check/Wingman/Wingman.exe`, SHA-256
`36cb5188425a91f4b6103eed20b92a1491a0ba29bc0fcda358e156c4281375ce`.
Built separately: the running earlier executable and isolated test profile were
not overwritten. This new executable has **not yet been launched**. The user
reported that the earlier local candidate worked, but that is not acceptance of
this new form or completion of the live/native matrix. The full Windows suite
was not repeated for this follow-up; its earlier six symlink-privilege fixture
failures remain documented below. No privilege changes or unrelated fixes were
made. Browser observations use synthetic dev data and are not WebView2 acceptance.

Manual follow-up is in smoke-checklist item 11. Reviewer focus remains bounded
protected-byte compensation, canonical blank-token binding, independent saved/Test
outcomes and per-input ownership under one grouped submission.

## Status and authority

**Implementation, focused review, post-implementation polish, full Linux tests,
and wheel/Windows frozen artifact checks are complete. The full Windows suite
has six environment-privilege failures in unchanged tests; all Wanderer tests
pass there. All 15 live/native acceptance scenarios remain NOT RUN. This is not
a release or deployed-connectivity sign-off.**

Post-polish verified candidate: **`7d6b0e17ab55071c88049eee05f8afcd7c55e912`**.
The final evidence commit changes documentation only; it does not change the
Python/JavaScript implementation or tests verified below.

- Wingman implementation examined by Task 6:
  `137d1272b3b9da130f37db0ee81e54611fb5432c`
  (`fix: reconcile Wanderer health and Test generation ownership`). Task 6 adds
  tests/documentation only; it does not change that production implementation.
- Task 6 integration test commit:
  `cd98717859bb6e561103709c2d54f4897c42db89`
  (`test: integrate Wanderer HTTP lifecycle with preview labels`).
- Feature base: `83b7741bd997b7e0ea951c894183e10e4c68ae3b`.
- Wanderer API authority:
  `2ddff24516c27ecde7b175991fcd74d608a35932`, specifically its tracked-character
  locations documentation and executing serializer/controller. This is the
  pinned contract authority, **not an observed version of a running instance**.
- [`tests/fixtures/wanderer/README.md`](../tests/fixtures/wanderer/README.md)
  records exact upstream paths. `deployed-v1.json` is a synthetic reproduction,
  not a live capture: First Pilot is Jita/HOME, Hidden Pilot is Amarr with no
  map alias/timestamp, and unmapped/offline/unavailable cases retain the deployed
  field shape. No actual token, roster or history is included.
- Implementation constraints remain in
  [`wanderer-preview-overlay-plan.md`](wanderer-preview-overlay-plan.md). The
  plan has not been moved. No companion-preview dependency, OAuth/ESI extension,
  map mutation, deployment, version bump or push is included.

No deployed URL, usable integration token, observed instance version or live EVE
session was supplied for this acceptance pass. None is fabricated below.

## Implemented decisions

### Contract, privacy and freshness

`wingman/wanderer/model.py` validates the complete deployed v1 envelope and exact
ten-key records. One malformed record rejects the candidate snapshot. Limits
include 2,000 records, 1 MiB success/2 KiB error bodies, 255 codepoints/1,024 UTF-8
bytes per name, 512 bytes for Authorization, 255 bytes for the map selector, and
1,024 bytes per conditional header. Character matching is normalized exact text,
not substring matching; only currently admitted named primary sessions are
projected to labels. The response can include other tracked characters, but the
page receives safe health/counts, not that roster.

`client.py` makes one bounded, certificate-verified HTTPS attempt and preserves
the configured application prefix. Redirects are refused, not reauthorized.
Socket connect/read timeouts are five seconds; the header/body read budget is ten
seconds. OS DNS cancellation is not promised. The expiry owner and retained
shutdown ownership remain necessary even with bounded socket operations.

Freshness is `receipt_monotonic + max(0, 15 - server_observation_age)`. Future
record times are rejected; local wall-clock skew is irrelevant. Valid 200 replaces
the snapshot; 304 preserves its original deadlines. Other failures retain only
last-good data until expiry. **401/403 headers clear cached data immediately,
before reading the error body**, and pause automatic polling. A changed connection
or successful explicit Test can recover authorization; readiness flaps alone
cannot. This deliberately overrides the historical design's grace-after-auth rule.

No current/history location data is written to settings, diagnostics or fleet
sharing. The configured map selector, bearer integration token and protocol headers
travel only to the selected HTTPS endpoint; local preview names are not uploaded.
The README network table now describes both automatic polling and explicit Test.

### Configuration and ownership

`credentials.py` stores `wanderer_credentials.json` separately from settings.
DPAPI protects the complete normalized URL/map/token binding and document identity.
The page sees presence/error flags only. A URL/map edit does not rebind an old
credential; token submission carries the expected acknowledged binding. Disable
retains the protected token; Remove connection deletes only that local credential,
leaving URL/map/enabled unchanged. Removal does not revoke anything on Wanderer.
Atomic file replacement is not a cross-document or power-loss durability promise.
DPAPI does not protect against code running as the same Windows user.

`controller.py` persists settings before committing the runtime generation.
Failed persistence retains the prior acknowledged configuration. One worker is
retained across toggles, Test, and connection changes. Its single HTTP lane
serializes Test with polling/backoff; healthy requests are at least two seconds
apart after completion. A separate scheduler expires names even while HTTP is
blocked. Controller handoff and page-health delivery have separate owners; neither
network nor page delivery runs on expiry, discovery, telemetry or the native pump.

The host generation is fenced **before** worker configuration. PreviewHost's
separate coalescing mailbox admits full
`ClientSessionId(hwnd, pid, character, first_seen_generation)` identities and is
bounded by the current roster, not the recent-name CAP64. Discovery admission
revokes departed sessions; only the pump changes native labels. “Immediate logout”
means the first admitted discovery observation, with pixels cleared at the next
available pump opportunity, not an inferred between-scan event.

Final shutdown detaches and closes host metadata admission before native teardown
and joins outside state locks. A timed-out HTTP owner remains retained, never
replaced. Existing API startup/early-shutdown/final-shutdown wiring has dedicated
`test_wanderer_wiring.py` coverage in addition to the integration tests below.

The existing owned click-through label becomes a two-line pill; the character
stays primary. Both lines ellipsize independently, Show labels governs the whole
pill, and cache identity includes both strings, clipped layout and style. It uses
the existing bundled Inter font and never resizes/moves the EVE source window.
`wanderer.js` owns the card and field replies; health updates do not overwrite
user drafts. Test remains explicit and does not turn names on.

## Task 6 automated evidence

Commands ran on Linux from `.worktrees/wanderer-overlay`, using the locked
`/tmp/wingman-wanderer-venv`. The production source was the SHA above, with the new
Task 6 tests/docs in the worktree. No full-suite/build result is implied.

### Integration boundary

`tests/test_wanderer_integration.py` executes the real HTTP client, worker,
controller, Settings file transactions, credential document/atomic I/O, host
mailbox, PreviewWindow label cache and Pillow renderer. A single loopback HTTP
server controls responses; an injected HTTPConnection sits below the still-HTTPS
URL validator. There is **no insecure production option**. Win32 calls are native
doubles. Integration encryption uses an authenticated Fernet seam; the separate
Windows-only credential test uses default DPAPI protect/unprotect on `tmp_path`.

Eight end-to-end scenarios cover:

- fixture 200 through current-session matching to one/two-line label images;
- 304 retaining the exact original deadline while the next real HTTP body blocks;
- immediate auth-header clearing while the real error body remains blocked;
- binding replacement fencing an old response and serializing queued Test;
- same-name process replacement and logout clearing at discovery admission;
- Off Test and Preview master gates without duplicate worker owners;
- fresh controller/store startup from persisted settings, restart and removal;
- shutdown admission closure before native teardown, retaining blocked HTTP.

Two additional tests cover the real Windows credential document round trip,
replacement/binding/removal and the existing frozen font lookup/render path using
a copied bundled font. The latter executes the real module's import-time font
resolution but is **not** a PyInstaller artifact or installed-rendering test.
Exhaustive input/error/race matrices remain in the focused unit suites.

All race ordering uses manual monotonic clocks, Events, queues and observed
condition re-parking. Wall-time waits bound failures; no sleeps establish order.
The client and worker share the same injected monotonic domain.

### RED and GREEN history

The production feature already existed. Rather than fabricate a missing-feature
RED, Task 6 added integration assertions and proved their sensitivity with
**in-memory-only mutations**, never editing production files:

| Exercise | Actual result |
|---|---|
| Renew deadlines on 304; suppress early authentication rejection; select `-k '304 or auth_headers'` | **2 failed, 8 deselected**: expiry did not clear HOME; the blocked auth response retained Connected/unpaused state. |
| Remove final response generation fencing; select `-k binding_replacement` | **1 failed, 9 deselected**: a superseded old-map snapshot produced matched/available=1 rather than 0. |
| Unchanged production, integration-only GREEN | **9 passed, 1 skipped**; the skip requires real Windows DPAPI. |

Initial harness runs were **7 passed, 2 failed, 1 skipped**, then **8 passed,
1 failed, 1 skipped**. These were test assumptions, not production defects:
PreviewWindow uses a discovery-client adapter rather than `RosterClient.session`;
font lookup happens at module import; and the first blocked-request schedule
coincided with the client's independent ten-second read budget. The tests now use
the host's admitted full-session set, a detached real font-module import, and a
request begun at monotonic 110 so location expiry at 114 cannot be an HTTP timeout.
No production fix was necessary.

Fresh covering command:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest \
  tests/test_wanderer_integration.py tests/test_wanderer_client.py \
  tests/test_wanderer_worker.py tests/test_wanderer_controller.py \
  tests/test_wanderer_credentials.py tests/test_wanderer_wiring.py \
  tests/test_preview_metadata.py tests/test_packaging_completeness.py \
  -q -rs --tb=short --basetemp=/tmp/wanderer-task6-focused
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff check \
  wingman/wanderer tests/test_wanderer_integration.py
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff format --check \
  wingman/wanderer tests/test_wanderer_integration.py
```

Fresh final result (test source committed unchanged as `cd987178`):
**344 passed, 1 skipped in 11.98s**; skip:
`test_real_windows_credential_document_roundtrip_replace_binding_and_remove`
(real Windows user-bound DPAPI required). Ruff lint passed; **7 files already
formatted**. Existing packaging-completeness assertions are included; wheel and
frozen artifact inspection are not claimed by this command. An additional
integration-only rerun immediately before it was **9 passed, 1 skipped in 1.83s**;
these are repeated executions of the same cases, not extra distinct coverage.
Working/staged `git diff --check` passed. The mistakenly tracked Task 1 scratch
report was removed from the index only and remains locally present/ignored; no
scratch reports belong to this evidence document's committed inputs.

## Earlier scoped evidence — not cumulative full coverage

The implementation task records supplied the following results. Selections overlap
and changed between tasks; **do not add their counts together**. The baseline was
10,608 passed with 11 Windows-only skips after Node/release-codec prerequisites;
it is not a post-feature full-suite result.

| Scope | Recorded evidence | Limit |
|---|---|---|
| Task 1 model/storage plus packaging and reused crypto/atomic I/O | 360 Linux passed | Storage tests used injected crypto. |
| Task 2 client/worker/model/storage | 337 Linux passed; parent rerun 337 Windows passed | Synthetic HTTP, not deployed connectivity. |
| Task 3 host/window/chrome/metadata/native bindings | 449 Linux passed, 4 Windows-only skips; parent later reported **453 Windows passed, no skips**, including real message-only pump and bindings | Not live EVE visuals or mixed-DPI acceptance. |
| Task 4 controller/runtime/API and related lifecycle selections | 965 Linux passed; separate Fleet lifecycle selection 409 passed; parent reported **420 Windows passed** for its controller-related selection | Different overlapping selections, not a full suite. |
| Latest Task 5 UI/controller correction at `137d1272` | 544 Linux passed; 53 standalone Node cases; JS smoke passed. Parent reported **472 Windows passed** for latest UI/controller coverage | Node doubles do not render WebView2. |
| Parent's Windows primitive DPAPI coverage | **50 passed**; two primitive tests are Linux skips | Separate from the newly added real credential-document test, which Task 6 has not run on Windows. |
| Parent's Chromium/CDP inspection | At 840/839/1280 widths: no overflow or page errors; a draft survived health updates. Scratch evidence: `browser-results.json` | Browser/dev fixture observations, not native previews, installed WebView2 or live Wanderer. |

The parent owns reconciliation of these earlier observations with the final
post-polish SHA. Task 6 did not independently rerun Windows or browser checks.

## Final post-polish verification

The parent ran `polish-core --fix` against `83b7741b..7d6b0e17`, using one
consolidated changed-code pass for quality, silent failures, comment accuracy and
type/interface checks. No actionable findings or safe edits were identified.
The clean diff was inspected; no polish edits needed reversion or acceptance.
This also approved Task 6's integration/evidence slice. No further architecture
review loop or unrelated refactoring followed.

### Prerequisites and exact commands

Linux: CPython 3.11.15, locked dev environment `/tmp/wingman-wanderer-venv`, Node
26.5.0. The locked release codec was built and installed in this worktree before
the baseline suite. Windows: CPython 3.11.16, locked dev/build environment
`%TEMP%\wingman-wanderer-venv`, portable Node 26.5.0 downloaded from nodejs.org
and checked against its published SHA-256. No global Windows settings changed.
The Windows codec was reused from a local isolated build whose codec sources and
Cargo lock are identical to the feature base, SHA-256
`18b85ebda93670814f68793e87a971c5d510cd0b0946f226dc6c2ba85c577eef`.
This is artifact reuse, not a new Windows Cargo build or a companion dependency.

From the feature worktree:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wanderer-final-linux --junitxml=/tmp/wanderer-final-linux.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer*.py tests/test_preview_metadata.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_packaging_completeness.py -q -rs --basetemp=/tmp/wanderer-final-focused
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff format --check .
node scripts/test_wanderer_runtime.js
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv build --wheel --out-dir /tmp/wanderer-final-wheel
git diff --check 83b7741b..HEAD
```

Windows, with the prepared Node directory on the process PATH and
`UV_PROJECT_ENVIRONMENT` set to the environment above:

```powershell
uv run --no-sync python -m pytest tests/ -q -rs --basetemp="$env:TEMP\wanderer-final-windows" --junitxml="$env:TEMP\wanderer-final-windows.xml"
uv run --no-sync python -m PyInstaller packaging/uploader.spec --noconfirm --clean --distpath dist/wanderer-check --workpath build/wanderer-check
uv run --no-sync python .superpowers/sdd/wanderer-preview-overlay-plan/inspect_frozen.py
```

| Fresh gate | Observed result |
|---|---|
| Full Linux pytest | **11,079 passed, 12 skipped**, 238.55s |
| Focused Wanderer/metadata/bridge/page/packaging pytest | **794 passed, 1 skipped**, 22.36s |
| Full Windows pytest | **11,029 passed, 56 skipped, 6 failed**, 237.46s; details below |
| Windows Wanderer cases, extracted from full-suite JUnit | **426 passed, no skips/failures**, including real DPAPI credential document |
| Ruff lint / format | Passed; **397 files already formatted** |
| Focused Node ownership harness | **53 passed, 0 failed** |
| Executable JS smoke | Passed all three pages, including Wanderer script registration/order |
| Independent Cargo regression | **1 passed, 0 failed/ignored** |
| Wheel build and contents/import exercise | Passed; all six Wanderer modules byte-match source and import from the wheel |
| Windows PyInstaller build and archive/assets inspection | Passed; six Wanderer modules in PYZ, changed web bytes and Inter font match source, bundled font loads, required sidecars present |
| Browser/CDP rerun | 839/840/1280px: no horizontal overflow, no page/resource errors, controls within card, URL draft survives health push |
| Whitespace and final scope inspection | Passed; no version change, dependency changes, tracked scratch reports, debug output or excluded companion work |

Linux skips are the original 11 Windows-only junction/DPAPI/WinDLL/pump/binding
cases plus the new real Wanderer DPAPI credential test. Windows skips are explicit
POSIX mode/case/special-file checks, unavailable symlink creation, off-Windows
guards and a test deliberately avoiding a native modal. Neither suite skipped
Node or codec coverage. The actual Windows message-only pump and native bindings
ran successfully; these do not render real EVE previews.

### Windows full-suite limitation — not a green gate

All six failures raise **WinError 1314 (required symlink privilege unavailable)**
while preparing unrelated test fixtures. The following files are byte-unchanged
from `83b7741b`; the diff was checked. No permission was elevated and no tests
were weakened or skipped to hide these failures.

- `tests/test_setup_catalog.py::test_assets_must_be_regular_without_symlink_aliases`:
  the three `symlink` cases for catalog, preset and licence files.
- `tests/test_setup_catalog.py::test_catalog_directory_is_not_created_or_followed[symlink]`.
- `tests/test_ui_setup_controller.py::test_context_refuses_fallback_or_untrusted_bases[escaped]`.
- `tests/test_ui_setup_controller.py::test_pairs_require_unambiguous_confirmed_links_and_real_local_files[export-escape]`.

A full Windows green run still needs an environment with the existing suite's
symlink prerequisites. This was not a baseline Windows full-suite replay; the
failure classification rests on the explicit fixture exceptions and unchanged
source. Logs/JUnit remain `/tmp/wanderer-final-linux.{log,xml}` and Windows
`%TEMP%\wanderer-final-windows.{log,xml}`.

### Artifact and browser limits

Actual frozen artifact: `dist/wanderer-check/Wingman/Wingman.exe`, SHA-256
`acdb8cbd070d9d1a79a4370d1e1e448c1b15a42db08984a0d849e1830569b080`.
The full application was **not launched or installed**. Module/archive checks,
font-byte/loading checks and source DPAPI tests do not prove installed credential
retention or native label rendering. The wheel build emitted setuptools' existing
`wingman.assets` package-discovery warning; the only package-list change is the
explicit `wingman.wanderer` entry, and all six new modules were verified.

The browser run used an isolated new page, local dev fixtures and blocked
non-local requests on Linux HeadlessChrome 152.0.0.0, deviceScaleFactor=1.
The 839px and 840px screenshots were inspected. This is CSS/handler evidence,
not Windows/WebView2 or mixed-monitor scaling evidence. Reports, screenshots,
inspection scripts and frozen inspection JSON remain in the ignored task scratch
folder; no token was entered or captured.

## Live/deployed acceptance remains NOT RUN

The 15 explicit scenarios in
[the smoke checklist](smoke-checklist.md#wanderer-names--livenative-acceptance)
remain **all NOT RUN**: stationary confirmation; movement; temporary and persistent
aliases; reset/raw fallback; hidden/unmapped; roster/offline/session changes;
independent expiry; network loss/recovery; 304; authorization errors;
credential/field lifecycle; Wanderer restart; Wingman/Preview start-stop;
native DPI/input; frozen DPAPI/font.

**Observed deployed instance version: unknown, no instance was contacted.**
The API authority is `2ddff24516c27ecde7b175991fcd74d608a35932`; it is not a claim
about an observed running build. Required Windows conditions remain minimum
preview size, 100/125/150/200% scaling, mixed monitors, movement/resizing, clicks,
selection and alert pulses. Record the actual Wingman SHA/build and instance
version with sanitized expected-versus-observed outcomes when these checks run.
A fixture, contract commit, source test or browser screenshot cannot fill those
fields by inference.

## Reviewer-facing completion notes

The feature is additive/default-off: ordinary settings gain only enabled/base/map,
and the bound DPAPI document is separate. No destructive migration is required.
Disable preserves credentials; explicit Remove deletes the local protected token,
not Wanderer's token. Old versions ignore the additive settings and credential
file. No locations are persisted. This makes local rollback straightforward
without claiming cross-document atomicity.

Implementation decisions discovered in the current repository: the live roster
is not capped at 64, HTTP must not own expiry scheduling, host restart needs a
fresh metadata generation, and a field response cannot own a newer draft.
Focused checkpoints caught and fixed retiring-HWND wake ownership, Windows test
ID/font-metric assumptions, Test cancellation on generation changes and mixed
configuration/worker state sampling. They did not expand into a provider system,
companion foundation or authentication redesign.

Review focus: host-before-worker fencing; server-relative monotonic deadlines;
secret-safe persistence/transport boundaries; field-owned token binding; and the
explicit distinction between automated evidence and remaining native acceptance.

### Local commit slices

All commits are local on `feature/wanderer-overlay`; nothing was pushed or released.

| Commits | Slice |
|---|---|
| `146313b6` | Self-reviewed six-task plan |
| `e0eb28e3`, `6ee37323` | Strict model/DPAPI storage and coherent pinned fixtures |
| `51bddd09`, `d40a8722`, `7869ba7d` | HTTPS client, independent expiry worker and early-auth fencing |
| `2099caac`, `4571ebb6` | Checkpoint report bookkeeping and portable Windows test IDs; scratch report removed from tracking |
| `178aa29f`, `2b4b1ef0` | Session-fenced native metadata/labels and retired-HWND wake correction |
| `ef060c56`, `59781b89`, `b8e432c0` | Committed controller, bridge/lifecycle wiring and shutdown/acknowledgement hardening |
| `e1c72a35`, `137d1272` | Settings card, field-owned responses and generation-ordering corrections |
| `cd987178`, `7d6b0e17` | End-to-end integration, privacy/manual-acceptance documentation and remaining scratch cleanup |

A subsequent documentation-only commit records these final verification results
and the plan's completed engineering tasks. The complete final diff is 44 files:
the six-module Wanderer package, four existing preview modules, settings/bridge/
startup/copy wiring, the new Settings owner and five existing web files, one Node
harness, focused tests/fixtures, package registration and five documentation files.
No source version, dependency lock, telemetry dispatcher, OAuth/ESI module or
companion runtime changed.

### Knowledge check

1. Why can a 304 update connection health without extending any label deadline?
2. Why does the metadata mailbox use the full client session rather than a name or the recent-name cap?
3. Why must the host generation be fenced before worker reconfiguration?
4. How does a token draft remain bound while URL/map edits and responses overlap?
5. Which behavior remains unproved by a successful frozen archive inspection?
