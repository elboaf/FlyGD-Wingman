# APPROVED DESIGN BASIS — Fleet callback creation identity

**Approved by user under coordinator U-01/F-01, 2026-09-08.**
The implementation continuation prompt authorizes the five token-first interfaces
and bounded file inventory below. Decisions 1–4 are accepted with F-01 constraints:
post-style atomic publication; attempt-owned failure cleanup; retirement before
shutdown detach/stop/destroy while retaining failed-destroy objects; already-entered
lifecycle-owned native calls and move's protected save may finish before retirement
acquires lifecycle. No instantaneous cancellation is promised.

No document epoch, positive fit acknowledgement, native visibility correction or
new authentication claim is authorized. The earlier proposal/evidence below is
retained as the reviewed design record; its requests for approval and prospective
wording describe the original checkpoint, superseded by U-01/F-01 and this header.
Implementation tracking: [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md).

Known integration overlap: main `75f3288e84c80018d6cee421ae2f32577ece53d3` (#185)
adds character title tooltips in fleetbar.js. Stay on the fixed base; preserve that
unrelated render change during later coordinator integration.

Original proposal: Worker F, 2026-09-08, with no source/test changes or commits.

Base: `ab06a6efde9ade0f40791d812d922356e8e6c16f` — Share overview and in-space layouts through new profiles (#183).
Worktree: `/mnt/c/dev/flygd-wingman/.worktrees/followup-fleet-design`.
Branch: `design/followup-fleet-identity`, still at the exact base.

## Intended outcome and current understanding

A callback originating in a replaced Fleet window must not read the replacement's
snapshot, resize/move it, save predecessor coordinates, or mark it ready. Give each
Python creation attempt a fresh opaque token in its URL fragment; the standalone
page captures it once and echoes it in all five callbacks. Python admits callbacks
only against the corresponding current concrete window. This is correlation,
**not authentication**: the shared bridge remains shared.

Keep the display-only product contract, native drag/geometry ownership, presentation
worker, main-page toggle/settings/character visibility endpoints, payload revisions,
and persisted schema unchanged. Simple off/on must reuse the window, token and
readiness. No EVE window may be moved or resized.

## Evidence and confirmed constraints

References below are at the fixed base unless marked pywebview.

- `wingman/web/fleetbar.js:12–44,128–140`: its local `send` calls exactly the five
  endpoints below. It waits for bridge readiness, converts missing methods/errors
  to null, hydrates alongside fonts, renders/fits/clamps, then calls ready. An
  independent 500 ms fit and mouseup position save also exist.
- `wingman/ui/api.py:2340–2344,2734–2815`: snapshot is presently unqualified;
  ready uses whichever live window is current; fit re-looks up the window each
  retry; move uses the current window; save-position has no lifecycle admission.
  Fit/move are enabled-gated. Ready may record readiness while disabled.
- `api.py:2372–2425`, `wingman/ui/fleetpresentation.py:22`: outbound deliveries
  already capture concrete targets, activation and revision. The worker reads
  the target under the presentation lock. It needs no new token or redesign.
- `wingman/ui/fleetbar.py:28–64,88–107`: creation is lifecycle-owned and hidden;
  it currently publishes the window before tool styling. Both toggle and startup
  restore can create. Restore failure only toggles off today — partial publication
  must not leave a failed live window eligible for ordinary reuse.
- `api.py:2652–2732`: on/off closes telemetry presentation, not the native creation
  lifetime. **Do not retire the token in `_close_fleet_presentation()`.**
- `api.py:2488–2506`, `wingman/__main__.py:943–966`: shutdown closes admission,
  detaches and bounded-stops before native destruction. A failed shutdown destroy
  retains its concrete object for retry. Preserve this ownership.
- `tests/test_fleet_bar.py:446–456,975–1049` pins disabled-ready reuse, hidden
  construction, native drag and geometry. `PRODUCT.md` and `DESIGN.md` require
  display-only behavior and distinguish headless tests from Windows acceptance.
- Diffing #182's merge `978f8b25…` against this base showed no changes in Fleet
  source/tests or main lifecycle. `api.py` changes are the save-dialog helper and
  Profiles setup wiring, outside this proposal; Fleet line numbers shifted.

Prior local records were read and left untouched: coordinator
`docs/plans/followups-20260908/FLEET-DISCOVERY.md`, current
`docs/plans/review-20260907/d-fleet/implementation-notes.md`, and D-01 in the
review-20260907 coordinator's `DECISIONS.md`. This proposal addresses D-01's
explicit inbound-identity deferral, not its already-shipped worker design.

## Decisions for review — independently approvable

### 1. Creation lifetime, not literal document lifetime — recommended

Use `secrets.token_hex(32)` for each creation attempt; no token persistence,
telemetry-generation derivation, HWND identity, or activation-counter reuse.
Append exactly `#fleet-page=<64 lowercase hexadecimal characters>` to the current
local `fleetbar.html` path. Capture the validated fragment once at IIFE execution;
never refresh that variable from location, a payload, or a shared endpoint.

**No supported same-window Fleet reload/navigation path was found.** A source-wide
navigation search found no Wingman `load_url`, `load_html`, document reload or
location reassignment caller. `ui/window.py:252–255` calls `webview.start` without
`debug`; pinned pywebview defaults it to false. Its Edge backend disables browser
accelerator keys, default context menus and DevTools when debug is false
(`platforms/edgechromium.py:286–294`). Wingman offers create/restore, hide/show and
replacement of a dead window, not a Fleet reload command. These are source facts,
not proof that no external/browser recovery mechanism can reload a document.

A same-URL reload retains its fragment. Old in-flight Python callbacks and the new
document then share the same creation token; this design does **not** isolate them
or reset readiness automatically. Recommend **no additional document epoch for
this bounded change**, explicitly excluding development/manual reload and browser
recovery from the guarantee. If same-window reload becomes supported, require a
separate navigation/document-epoch protocol before claiming document isolation;
a JS-generated epoch that can replace current authority via an unqualified shared
registration call is not sufficient. Revisit this decision if native testing finds
ordinary shipped use recreates documents in place.

### 2. Identity-only; preserve best-effort fit/ready returns — recommended

Do not silently turn the boot chain into a positive-fit acknowledgement protocol.
Today `fit_fleet_bar` returns None after success, refusal, exhausted retries, and
unreadable native dimensions. JS also proceeds to ready after null hydration.
The current ready docstring's “successful fit” is stronger than the implementation.

Keep these outcomes indistinguishable in this patch. A current valid ready request
can still mark readiness without proof of fit success. Stale fit may settle with
null and its predecessor may subsequently send move/ready — the unchanged captured
token makes those callbacks harmless to a replacement. A positive structured fit
result, reveal acknowledgement, or “remain hidden on null hydration” policy would
change observable failure/startup behavior and needs separate approval and tests.

### 3. Native invisibility until ready — source risk confirmed, native gate open

Preserve hidden construction and the intended (fonts + snapshot) → render → fit →
clamp → ready ordering. Do **not** claim token plumbing makes that ordering a
strict native visibility guarantee.

Installed distribution metadata and `pyproject.toml:49` both specify pywebview
**6.2.1**. In its `platforms/winforms.py:600–643`, resize calls `SetWindowPos` with
literal `64` (`0x0040`, SWP_SHOWWINDOW); move explicitly includes SWP_SHOWWINDOW.
Hidden creation itself uses opacity-zero Show/Hide (`:771–781`). Wingman's existing
`ui/sigbar.py:205–213` independently documents the resize-reveals-hidden behavior.
Fleet fit runs while enabled but before ready, so token admission does not remove
this exposure. Already-entered native calls cannot be cancelled.

Recommend treating strict invisibility as **unverified and potentially violated**,
not as acceptance proved by headless tests. Require an authorized Windows/WebView2
smoke with delayed fonts/snapshot/fit, native visibility observation before ready,
tool-window/no-activation checks, and DPI/monitor clamp checks. If a flash or early
show occurs, obtain a separate native-geometry correction decision; do not add a
resize-then-hide workaround, CSS hiding, pywebview upgrade or native patch here.
If strict invisibility is a prerequisite for shipping this change, native evidence
or that separately approved fix blocks release, not just documentation closure.

### 4. Failure handling remains bounded to admission and existing cleanup

Construction, styling or publication failure retires the attempt, even if enabled
rollback or native cleanup fails. No tokenless live object may be reused as a
successfully created page. Preserve existing best-effort creation-failure cleanup;
this proposal does not add an orphan-window cleanup registry. A destroy failure
may leave an unresponsive orphan native window, but cannot restore its callback
admission. Shutdown, unlike creation failure, already retains its failed destroy
target for a later retry; preserve that behavior explicitly.

Ordinary fit errors still retry; move errors still no-op; ready reveal errors still
follow the existing disable/hide path. Such errors alone need not end a valid
creation lifetime when the existing path keeps that same window for reuse. Any
path that abandons/replaces the window must retire its token first. This separates
creation failure from a reversible hide, rather than churning identity on all
native errors.

## Proposed bridge contract

Use token-first positional parameters, with defaults only to fail closed on omitted
arguments. The defaults are **not** a tokenless compatibility mode:

```python
fleet_bar_snapshot(self, page_id: str | None = None) -> dict | None
fit_fleet_bar(self, page_id: str | None = None, width=None, height=None) -> None
move_fleet_bar(self, page_id: str | None = None, x=None, y=None) -> None
save_fleet_bar_pos(self, page_id: str | None = None, x=None, y=None) -> None
fleet_bar_ready(self, page_id: str | None = None) -> None
```

- Accept only a string matching the entire `[0-9a-f]{64}` token and equal to the
  current `_fleetbar_page_id`, with a non-quitting, live concrete current window.
  Reject absent/null, booleans, numbers, containers, wrong length/case, whitespace,
  suffixes and stale values; do not coerce or trim. Validate identity before doing
  geometry conversion or persistence. Preserve existing geometry normalization.
- All rejected mutations return None (JS null), with no readiness, native,
  persistence or presentation-queue side effects. Rejected snapshot returns None,
  never the replacement payload or an empty successful snapshot. Normal native or
  settings failure handling remains as today; identity rejection itself does not
  throw or disclose a current token. A settings-save error can still reject its
  bridge promise and be converted to null by `send`.
- Snapshot, save-position and ready do **not** require enabled or already-ready.
  This preserves disabled-page reads and queued drag saves, and ready-while-disabled.
  Fit and move require enabled, but not ready (the first fit precedes ready).
- Add the captured page token to arguments in the Fleet-local `send` helper, which
  currently serves only these five methods. Missing/malformed fragment makes that
  helper resolve null without calling Python. Keep method-name literals visible
  to existing contract guards. New non-page calls must not accidentally inherit
  this helper's protocol.
- No current-token endpoint, no bootstrap-token request, no token in Fleet settings
  or telemetry payloads, no logging full tokens. The Python/JS bundle changes
  together; old/tokenless pages fail closed instead of operating a newer window.
  There is no persisted-data migration or public external-client compatibility
  shim. All added Api data attributes remain underscore-prefixed.

## Lock and lifetime contract

1. **Construction:** under `_fleetbar_lifecycle_lock`, retire the predecessor's
   admission before attempting replacement. Generate the new token locally, create
   the native window hidden with the fragment URL, apply existing tool styling,
   then publish `(concrete window, token, ready=False)` together in a short nested
   presentation-lock section. Keep both native construction and styling outside
   the presentation lock. No worker can observe a mixed pair.
2. **Early callbacks:** pywebview starts each bridge method on a separate thread
   (`util.py:249–340`). Calls arriving during creation wait for the lifecycle lock;
   after publication they can admit only the matching pair. If creation fails they
   reject. A synchronous same-thread test callback before publication must also
   reject — no provisional token-only admission. Creation must never wait for a
   page callback/JS promise while holding lifecycle. The fragment eliminates such
   a bootstrap dependency.
3. **Failure:** retain a local concrete reference until styling/publication has
   either completed or cleanup has been attempted. Treat a None create result as
   failure, not successful enabled startup. On failure publish no active pair and
   reset readiness before best-effort destruction and existing rollback handling.
   Apply this through both restore and toggle; retire even if rollback also fails.
   Never reinstate the previous token. A subsequent attempt gets a fresh token.
4. **Admission and work:** all five callbacks validate/capture under lifecycle.
   Snapshot copies its existing payload under lifecycle → presentation and returns
   it without an extra push. Save-position holds lifecycle through its settings
   transaction, remaining save-only; move holds it through the captured move and
   position save. Neither saves under presentation. An already-admitted snapshot
   can finish returning its captured data after retirement; it must not re-read a
   successor when forming a delayed result.
5. **Fit retry:** capture `(bar, page_id)` once before the loop. Before each native
   attempt, revalidate quitting, enabled, matching token, concrete object identity
   and liveness under lifecycle. Resize and read dimensions on that captured bar.
   Keep the current retry budget/tolerance and sleep outside lifecycle. Replacement
   during sleep ends this fit, never retargets it. Do not hold presentation across
   native calls. Already-entered native calls are non-cancellable.
6. **JS continuations:** the immutable IIFE token covers the initial bridge-ready
   wait, fonts/snapshot promises, render fits, delayed clamp, final ready, 500 ms
   timer and mouseup. A delayed callback always carries its original token; Python
   revalidates every endpoint. Do not fetch new identity after any promise settles.
   A hashchange after capture must not upgrade the document's authority.
7. **Hide/show:** keep pair and readiness unchanged across simple off/on. Current
   ready records readiness while disabled but never reveals then; re-enable reveals
   the same ready page. No token rotation based on worker activation/generation.
8. **Shutdown:** in `_stop_fleet_presentation`, revoke the token/reset readiness as
   acceptance closes, before unsubscribe, bounded join or destroy. Retain the
   current native object for the existing shutdown retry path even if destroy
   fails; it is cleanup-owned, not callback-admitted. Clear successful destruction
   bookkeeping in a short presentation section under lifecycle. Preserve global
   shutdown → lifecycle → short presentation order. No JS evaluation or worker
   join under lifecycle/presentation; no new reverse lock acquisition.

## Fragment mechanics and alternatives

Inspected installed source under
`/mnt/c/dev/flygd-wingman/.venv/lib/python3.11/site-packages/webview/`:

- `http.py:94–103` strips `#…` before calculating the local HTTP server root;
  `window.py:564–572` resolves the relative URL with the fragment intact.
  `platforms/edgechromium.py:218–220,305–306` passes the resolved URL to `Uri` and
  WebView2 Source, with no fragment-stripping branch.
- `__init__.py:415–428` can initialize/create a secondary native window before
  returning its Python Window. WinForms uses a synchronous Invoke for secondary
  construction (`platforms/winforms.py:836–839`). Therefore early callbacks are
  possible; “create returns before JS runs” is not a safe assumption.
- `util.py:223–245` generates/injects the bridge and then signals readiness/loaded;
  `window.py:436` gates evaluate_js on bridge readiness. A targeted bootstrap push
  needs an explicit delivery/registration strategy outside lifecycle locks, not a
  guessed timer. It must capture the concrete target/token before any wait.

**Recommended fragment:** available at script execution, keeps the current Api,
requires no acknowledgement or new delivery owner. Source inspection plus the
headless resolution exercise below support the transport; a packaged Windows
startup still needs smoke evidence.

**Per-window bridge facade:** structurally binds origin in Python, but broadens
proxy ownership, private-attribute/lifetime requirements and bridge contract tests.
It also does not automatically distinguish documents reloaded in the same window.
Not justified for these five endpoints.

**Targeted bootstrap push:** keeps a static URL but adds receiver registration,
missing-handler/no-op, retry, readiness and stale-target ordering questions to
hidden boot. Possible, but larger than a fragment. Never replace it with a shared
“give me the current token” method.

## Blind-spot pass summary

Confirmed constraints above cover ownership, concurrency, rollback, compatibility,
security, native startup and test seams. No new persisted model, dependency,
product surface, remote service, telemetry collection policy or deployment step
is required. Primary remaining blind spots are same-window browser recovery,
partial native creation with no returned handle, and actual visibility/focus/DPI
behavior. Headless success cannot resolve those. A native allocation failure
before pywebview returns a handle may leave cleanup beyond Wingman's existing
seams; do not claim the identity patch makes native creation transactional.

Potential scope traps: turning best-effort fit into acknowledgement, changing
native dragging to JS dragging, putting token retirement in activation closure,
adding a document epoch without a navigation owner, or changing the worker to
solve inbound requests. None is recommended here.

## Deterministic acceptance design — after approval only

Use Events/barriers and controlled promise resolvers, not race sleeps. Where
applicable, establish behavioral failures on the unmodified base (not merely
new-signature TypeErrors), then passes with the approved change. Proposed cases
have **not** been implemented or run.

| Scenario | Required assertions |
| --- | --- |
| Each of five A-token callbacks after B replaces A | Snapshot is null; neither window resizes/moves/reveals; coordinates/readiness/queue unchanged. Matching B calls still work. |
| Invalid identity matrix on all five | Omitted/null/type/length/case/whitespace/suffix/unknown tokens reject; no settings call, native call or replacement payload. Legacy two-coordinate calls do not accidentally admit. |
| Atomic creation and early callbacks | Block create and styling; concurrent callbacks cannot observe partial publication. Release success admits only the new pair; release failure rejects. Include same-thread prepublication callback and None-return creation seam. |
| Creation/styling failure through toggle AND restore | Pair stays retired and unready; known local candidate receives cleanup; rollback failure does not resurrect identity; next attempt has a new token. Cleanup failure never re-admits predecessor. |
| Replacement between fit retries | First A resize does not stick; replace during injected sleep; next attempt never touches B. Also cover disable/shutdown in the gap and unchanged retry exhaustion behavior. |
| Already-entered native operation | Block a captured native call; demonstrate its allowed completion, followed by rejection of later stages. Do not assert cancellation. |
| Shutdown, timed-out worker and destroy-fails-once | Admission retired before detach/stop/destroy. All five callbacks reject even while object retained. Next shutdown retries only failed destruction; no re-enable/replacement worker. |
| Disable → ready → re-enable | Same window/token/readiness, no extra create or worker churn; disabled fit/move no-op; ready does not reveal until enabled; disabled current save remains save-only. |
| Delayed real JS boot/fit continuations | Run real fleetbar.js with separate A/B VM documents; defer bridge-ready, fonts, snapshot and fit replies. Every A continuation, timer and mouseup echoes A even after B exists or A's hash changes. Null hydration and null/exhausted fit still follow the existing best-effort boot contract. |
| JS malformed fragment and revision ordering | No bridge calls with invalid fragment; real onFleetSnapshot accepts/rejects revisions as before, including newer push ahead of hydration; null rejection never erases newer rendered state. |
| Same-URL reload limitation | Two document contexts with the same fragment capture the same token. Record the explicit lack of document-epoch isolation rather than asserting a protection this design lacks. |

Executable JS coverage must drive real handlers, DOM measurements, timers,
mouseup, deferred promises and argument arrays. Existing name/lexical tests and
all-page top-level smoke do not execute these continuations. Follow the existing
Node `node:test`/VM harness and pytest-wrapper pattern; no browser framework needed.

Preserve shipped fixture corrections: `tests/test_fleet_presentation_worker.py:7–14`
uses the real `make_api` plus the explicitly imported headless native helper;
`:536–545` prevents unintended fake-window replacement. Do not replace those real
worker tests with the non-thread-starting wrapper in `test_fleet_bar.py:19–23`.
`tests/test_startup.py:85–89` stubs Windows service builders. Extend its actual
`:179` Fleet stop/destroy test, not a nonexistent `test_main_telemetry.py`.

**Separate authorized native smoke:** packaged fragment hydration; initial hidden
startup under deferred fonts/fit; visibility/tool-window/no-activation at each
stage; off/on during boot and sharing-active operation; replacement and Quit
under delayed callbacks; drag persistence/clamp across DPI and monitor layouts.
Use controlled Wingman/test targets, never resize or move real EVE windows. This
worker did not launch any desktop/native app.

## Precise prospective changed-file inventory

No implementation is authorized by this inventory; sequence and details remain
conditional on approval of the decisions above.

| File | Proposed later change |
| --- | --- |
| `wingman/ui/api.py` | Private token field/admission and retirement helpers; five signatures; callback capture/revalidation; stop and failed-toggle bookkeeping. Fleet-owned regions only. |
| `wingman/ui/fleetbar.py` | Fragment URL, local construction token, atomic post-style publication and retirement/cleanup through create/restore. |
| `wingman/web/fleetbar.js` | Once-only fragment capture and token-first local send arguments; preserve existing promise/drag/fit behavior. |
| `wingman/__main__.py` | Only Fleet native-destruction bookkeeping to keep retirement/retained retry ownership and short-lock publication consistent. No worker/startup redesign. |
| `tests/test_fleet_bar.py` | Pair-aware fixtures/fake creators and direct calls; URL/handshake guards; stale/invalid/retry/creation/disabled-ready regressions. |
| `tests/test_fleet_presentation_worker.py` | Token-bearing snapshot call/fixtures and retirement assertions without weakening real-worker tests or headless corrections. |
| `tests/test_startup.py` | Retirement-before-detach/stop/destroy and Fleet destroy-retry assertions; preserve service-builder isolation. |
| `tests/test_bridge_contract.py` | Pin the five names/signatures and standalone ownership without widening main-page token requirements. |
| `scripts/test_fleetbar_runtime.js` (new) | Executable production JS continuation/argument/revision tests with controlled DOM, timers and promises. |
| `tests/test_fleetbar_runtime.py` (new) | Focused Node harness wrapper following `test_skills_runtime.py`. |

No expected changes to fleetpresentation.py, telemetry, settings schemas, HTML/CSS,
main-page modules, dependencies, CI or js_smoke.js (its stub already has
`location.hash`). Shared smoke/approval records remain coordinator-owned; this
packet supplies proposed additions, not edits to those records.

Conditional verification order: focused new regression failures on base → focused
Python and Node passes → bridge/page guards and all-page smoke → Ruff/diff checks →
broader suite under documented Node/native-codec prerequisites → separately
recorded authorized Windows smoke. Implementation must stop for a new decision
if reload support, a positive boot acknowledgement or a native visibility fix is
required; this is not an accepted implementation plan.

## Verification actually performed for this proposal

- Verified repository/worktree HEAD, clean starting status, branch and ignored
  `.worktrees`; created only the assigned worktree at the fixed base. Read-only
  `gh pr view 182/183 -R elboaf/FlyGD-Wingman` confirmed both MERGED and their
  exact merge commits; no amendment or old branch reuse.
- Inspected installed pywebview 6.2.1 source/metadata. A scratch Python `-B`
  exercise called the installed BottleServer root/Window URL resolver with server
  thread startup patched out: ordinary Linux path, a path containing spaces, and
  Windows Program Files path arithmetic via `ntpath` all retained the fragment
  and resolved `/fleetbar.html` correctly. No HTTP listener/native GUI was started.
  An AST assertion confirmed resize's final SetWindowPos argument equals `0x40`.
  These are source/headless mechanics, not real Windows URI/native proof.
- From the assigned worktree, using the existing primary checkout interpreter:
  `PYTHONDONTWRITEBYTECODE=1 /mnt/c/dev/flygd-wingman/.venv/bin/python -B -m pytest tests/test_fleet_bar.py tests/test_fleet_presentation_worker.py tests/test_startup.py tests/test_bridge_contract.py -p no:cacheprovider -q`
  — **188 passed in 13.11s**. Baseline evidence only; no token protocol exists yet.
- `node scripts/js_smoke.js` — every module on all three pages loaded successfully.
  This is baseline top-level execution, not continuation or native acceptance.
- Read-only structured architecture pass independently checked lifecycle locks,
  creation failure and the exact existing fixture corrections. It made no edits.
- Final document inspection and `git diff --no-index --check /dev/null docs/plans/followups/fleet/PROPOSAL.md` passed. Scope inspection found only this untracked proposal; tracked files and HEAD remain unchanged.

No full environment build/full-suite run, new regression implementation, native
smoke, live API mutation, user-state/EVE action, commit, push, PR or issue creation
was performed. Return this packet to the coordinator for explicit decisions 1–4;
no approval or implementation follows implicitly from these checks.
