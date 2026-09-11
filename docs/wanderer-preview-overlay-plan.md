# Wanderer preview overlay implementation plan

> Execute task-by-task with test-driven development and focused spec/quality checkpoints. User authorization covers execution after this self-review; no new design approval loop.

**Goal:** Show fresh map-local Wanderer system names below named EVE preview labels, with secure default-off setup under Settings > Previews.

**Architecture:** `wingman.wanderer` owns strict contract parsing, bound DPAPI credentials, one serialized HTTP lane and an independent monotonic expiry scheduler, and a controller behind ports. PreviewHost owns a separate coalescing session-keyed metadata mailbox; only its existing pump touches labels. Settings health delivery is decoupled from expiry and never runs on the preview/discovery/telemetry threads.

**Tech stack:** Python, existing HTTPS/DPAPI/Pillow primitives, Win32 pump, plain ES5/HTML, pytest and Node.

**Spec:** `../../preview-growth-design/docs/wanderer-preview-overlay-design.md` in the sibling worktree, design commit `2a22f640b09000dc49e6f1beb7b9b3852d7852bf`. API authority is deployed Wanderer commit `2ddff24516c27ecde7b175991fcd74d608a35932`, `docs/tracked-character-locations-api.md` and executing serializer/controller at that commit—not the supplied checkout HEAD or public PR #160.

## Global constraints and discovery decisions

- Base `83b7741bd997b7e0ea951c894183e10e4c68ae3b`; configurable alerts merge `04e9e9b9` is present. Preserve its mailbox/priority semantics.
- User overrides historical design: no companion foundation dependency; authentication errors invalidate cached data immediately. No OAuth/ESI, provider framework, distributed auth, history, map mutations, version bump, push, PR or deployment.
- Default off; one HTTPS application base (path prefix retained), one map, separate DPAPI credential bound to normalized base/map. No plaintext token in settings, page responses, exceptions, logs or telemetry.
- Exact deployed ten-key records; 2,000 records, 1 MiB success, 2 KiB errors, names 255 codepoints/1,024 UTF-8 bytes, Authorization 512 bytes, map selector 255 bytes, conditional headers 1,024 bytes. Reject whole malformed snapshots and extra fields.
- Freshness deadline = receipt monotonic + max(0, 15 - (envelope observed_at - location_observed_at)); reject future/malformed record time. 304 never renews deadlines. Healthy cadence 2 seconds; backoff/Retry-After only slow it. One request in flight, including Test connection.
- Current `ClientSessionId(hwnd, pid, character, first_seen_generation)` from `telemetry.model` is identity. Live roster has no numeric cap; bound pending metadata by the admitted current session set, not persisted recent-name CAP=64. Drop unknown/old sessions and old generations; close admission before joins; retain timed-out owners.
- Existing pill is an owned click-through overlay. Extend it, not thumbnail geometry or alert frames. Cache both strings, styles, dimensions and visibility; character primary and secondary text >=4.5:1 contrast.
- Settings transactions use `settings.update()`; grouped Test/Enter saves the submitted base/map/token before Test admission. Blank tokens reuse only the current normalized binding. Remove is revision-fenced and clears the saved URL, map and protected token while preserving the independent enable preference. Two-document writes compensate on settings failure; failed compensation closes admission and reports persistence failure. No cross-document crash atomicity is claimed.
- “Immediate logout” means at the first admitted discovery observation; an unobserved between-scan logout cannot be inferred. No live EVE window geometry changes.

## Task 1: Pure deployed contract and protected storage

**Files:** new `wingman/wanderer/{__init__,model,credentials}.py`; modify `pyproject.toml`; new `tests/test_wanderer_model.py`, `tests/test_wanderer_credentials.py`, `tests/fixtures/wanderer/` provenance and representative JSON.
**Interfaces:** `normalize_base_url(value) -> str`, `normalize_map_identifier(value) -> str`; immutable `LocationRecord` / `Snapshot` via `parse_snapshot(body: bytes, receipt_monotonic: float) -> Snapshot`; record display uses a monotonic deadline. `CredentialStore.load(base,map) -> str | None`, `replace(base,map,token)`, `remove()` use injected DPAPI primitives and atomic bounded storage. Errors expose safe fixed context only.
- [x] RED: fixture parity, hidden/unmapped/raw/unavailable states, duplicates/extra-sensitive fields, timestamp/type/size/name bounds, negative age, exact 15-second expiry, URL prefix/security, DPAPI binding/redaction/failure/replace/remove, package registration.
- [x] GREEN: implement the immutable strict model and independent versioned protected document; verify focused tests and lint, inspect diff, commit.

## Task 2: Single-attempt HTTPS and independent expiry worker

**Files:** new `wingman/wanderer/{client,worker}.py`; new `tests/test_wanderer_client.py`, `tests/test_wanderer_worker.py`.
**Interfaces:** `WandererClient.fetch(base,map,token,etag=None)` returns a typed success/unchanged/error result with bounded Retry-After and safe error codes. `WandererWorker.configure(...)`, `set_sessions(...)`, `test_connection()`, `close_admission()`, `stop(timeout)`, `state()` coordinate one generation, one request lane and scheduler. Publications are semantic session->system strings; health is cached separately and consumed off the expiry path. Exact typed configuration/publication signatures are recorded in the task report for controller integration.
- [x] RED: real HTTP boundary with injected connection/SSL seam (no production HTTP escape); fixed connect/read timeouts, redirect refusal, bounded slow/oversized/error bodies, no secret leakage; 200 replacement, 304 retention, auth clearing/pause, backoff and Retry-After; expiry while request blocked/backing off/paused; configuration races, Test serialization and shutdown barriers without sleeps.
- [x] GREEN: strict transport, one retained request owner and independent scheduler; callbacks never block on UI/network, stale generations discarded. Verify focused tests, inspect diff, commit.

## Task 3: Session-fenced host metadata and two-line labels

**Files:** modify `wingman/preview/{host,win32,window,chrome}.py`; optional focused pure mailbox `wingman/preview/metadata.py`; new `tests/test_preview_metadata.py`, extend `tests/test_preview_{host,window,chrome}.py`.
**Interfaces:** `PreviewHost.metadata_sessions()` returns immutable currently previewed named sessions; `set_metadata_callback(callback)` publishes detached roster/availability changes without I/O; `set_metadata_generation(generation)` clears/fences old worker publications; `submit_metadata(generation, updates)` coalesces only current sessions. `PreviewWindow.set_system_name(text)` changes only the existing label cache; `chrome.label_size` / `render_label` gain optional secondary text.
- [x] RED: coalesced wake signals/updates bounded by roster, stale worker/session rejection, same-name process replacement, logout/character-select clear at roster admission/application, final callbacks harmless; one/two-line dimensions, independent ellipsis/equal-size-text cache invalidation, labels off, move/resize/hide, alert inset/selection/opacity/click-through preserved.
- [x] GREEN: independent mailbox and existing pump handler; retain full session identity without repurposing crop epochs or altering alerts. Verify focused native-double/Pillow tests, inspect diff, commit.

## Task 4: Controller, committed settings and runtime wiring

**Files:** new `wingman/wanderer/controller.py`; modify `wingman/settings.py`, `wingman/ui/{api,copy}.py`, `wingman/__main__.py`; new `tests/test_wanderer_controller.py`, `tests/test_wanderer_wiring.py`; extend `tests/test_bridge_contract.py`.
**Interfaces (including approved grouped-connection follow-up):** `WandererPorts` supplies persistence, host admission/session/publication and health delivery; `WandererController` owns configuration/status and protected store. Four thin Api facades: `wanderer_state()`, `set_wanderer_enabled(enabled)`, `test_wanderer_connection(base,map,token)`, `remove_wanderer_connection(revision)`; literal `_push("onWandererState", payload)` adapter. Mutation results return `{applied,persisted,error,acknowledged}` with nonsecret acknowledged values. Test saves the submitted connection as a group before requesting the existing HTTP lane; `{test_accepted,test_error,test_generation}` describes Test admission separately from configuration persistence. Blank tokens reuse only the current normalized binding. Revision-fenced Remove clears URL/map/token, retaining enable.
- [x] RED: defaults/normalization and upgrade compatibility, rollback, binding changes and failed credential operations, token never returned; gated runtime (enabled/previews/host/config/credential), Test without enable and serialized against polling, no worker replacement after timed-out stop; startup and both early/final shutdown paths; semantic current-session-only coverage and all health states; bridge facades.
- [x] GREEN: persistence-first configuration, connection-action serialization, read-only health projection/delivery separate from deadline scheduler; early detach before native destruction, joins outside locks. Verify focused API/controller/lifecycle tests, inspect diff, commit.

## Task 5: Wanderer names Settings card and ES5 ownership

**Files:** new `wingman/web/wanderer.js`, `scripts/test_wanderer_runtime.js`, `tests/test_wanderer_page.py`; modify `wingman/web/{app.js,index.html,dev.js,style.css}` where required; extend bridge/page/dev guards and smoke coverage.
**Interfaces (including approved grouped-connection follow-up):** sole `onWandererState` handler; read on Previews section entry; grouped connection commits retain field-owned drafts and separate acknowledged baseline/draft revisions. Health pushes never overwrite drafts. All methods use the four Task 4 literal facades. Test connection or Enter in any URL/map/token field saves all three submitted fields as one connection, then requests Test; no per-field Apply controls or blur writes. Enable commits independently. The page distinguishes connection-save failure from refused Test admission and asynchronous Test progress/results. Removal confirmation is page-owned and sends the acknowledged revision.
- [x] RED: focused Node execution for hydration guard, delayed/stale replies, refused-write rollback, newer draft preservation, queued writes, cross-field errors, health without draft clobber, token clearing/no return, binding races, Test not enabling, remove confirmation, editable while off; bridge/page/smoke gates.
- [x] GREEN: compact accessible card, wrapped checkbox, password input, no independent styling controls or rail changes; safe dev fixtures only. Run Node harness, JS smoke, bridge/page/dev tests, inspect diff, commit.

## Task 6: Integration, polish, packaging and acceptance record

**Files:** new `tests/test_wanderer_integration.py`, `docs/wanderer-preview-overlay-verification.md`; update `docs/smoke-checklist.md`, `AGENTS.md` architecture and relevant privacy/network documentation; packaging assertions if needed.
- [x] RED/GREEN: complete synthetic snapshot HTTP -> worker -> session-fenced host/labels, credential and Settings lifecycle; package/wheel inclusion and existing font path; deterministic barriers for in-flight shutdown/reconfiguration.
- [x] Run `polish-core --fix` on the feature diff, inspect every edit, fix only scoped findings and rerun fresh focused tests/Node smoke/bridge/page checks, Ruff lint/format, full pytest with skips, Cargo, packaging completeness and wheel inspection. Baseline prerequisites already passed: locked dev sync, Node 26.5.0, release settings codec installed; baseline 10,608 passed, 11 Windows-only skips.
- [x] Record exact verified Wingman SHA and Wanderer `2ddff245`, automated counts/skips, and Windows/deployed results separately. All 15 requested live scenarios (stationary/moving/aliases/raw/hidden/offline/expiry/network/304/auth/restart/start-stop/DPI/frozen DPAPI-font) require actual observation. No deployed instance URL/token/version is supplied; unavailable live/frozen checks remain explicitly NOT RUN, not inferred from tests.
- [x] Inspect final diff against scope, commit reviewable integration/evidence slice, use change-explainer; do not push, deploy, open PR or bump version.
- [ ] Remaining acceptance: run all deployed/real-EVE Windows scenarios and repeat the complete Windows suite with symlink privileges. See `wanderer-preview-overlay-verification.md` for exact results and limits; executed gates do not imply all passed.

## Self-review

Coverage: Tasks 1–2 cover the executing API/security/freshness contract; Task 3 isolates existing pump/session/render ownership; Task 4 covers committed state and both shutdown paths; Task 5 owns field drafts and all bridge surfaces; Task 6 covers integration/packaging/native acceptance evidence. Ordering follows the interfaces above. No existing settings migration is required beyond additive default-off normalization; old versions ignore the new section and separate credential file. Disable is reversible; revision-fenced Remove clears Wingman's saved URL, map and protected token while retaining enable. Grouped Test/Enter saves a new binding only with a submitted token; a blank token cannot rebind the existing credential. Ordinary write failures preserve the acknowledged connection through compensation; failed compensation stops names and reports uncertain persistence. No location history, unrelated characters, public API changes or companion foundation are introduced. No placeholders or unresolved security/PreviewHost-ownership contradictions remain; actual Windows/deployed acceptance is an environment-dependent gate, not a claim automated tests can satisfy.
