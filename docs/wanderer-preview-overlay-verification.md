# Wanderer preview overlay — verification record

## Status and authority

**Implementation and bounded integration coverage exist; final release gates and
all 15 live/native acceptance scenarios remain pending. This is not a release or
deployed-connectivity sign-off.**

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

## Final gates still pending

The parent will append exact commands, final SHA, counts/skips and artifacts after
whole-feature polish. Until those results are recorded, these gates are pending:

- whole-feature `polish-core --fix`, inspection and fresh verification;
- full Linux/Windows pytest with skip review, actual release codec and Node;
- fresh whole-tree Ruff, Node runtime/JS smoke, bridge/page convention gates;
- independent Cargo settings-codec regression;
- wheel contents/imports and frozen PyInstaller/build asset inspection;
- Windows execution of the new real credential-document test;
- installed/frozen application behavior and native visual/live acceptance.

The 15 explicit scenarios in
[the smoke checklist](smoke-checklist.md#wanderer-names--livenative-acceptance)
are **all NOT RUN**: stationary confirmation; movement; aliases; reset/raw;
hidden/unmapped; roster/offline/session changes; independent expiry; network
loss/recovery; 304; authorization errors; credential/field lifecycle; Wanderer
restart; Wingman/Preview start-stop; native DPI/input; frozen DPAPI/font.

To replace NOT RUN with a result, record the actual observed Wingman SHA/build,
instance URL/version (without secrets), Windows/display conditions, scenario and
sanitized expected-versus-observed outcome. A successful synthetic test, an API
contract commit, or a browser screenshot cannot fill those fields by inference.
