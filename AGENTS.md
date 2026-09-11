# AGENTS.md

Guidance for any coding agent (and any human) working in this repository. It
is tool-neutral: `CLAUDE.md` imports it rather than repeating it, and other
agent front-ends read it directly. Keep it as the single copy; a second copy
drifts, and the last one did — the architecture section still said the
bridge was "~2.6k lines" when it was 6.8k, and five subpackages had been
added without a mention.

## What this is

FlyGD Wingman: a Windows-only, tray-resident desktop app for EVE Online
multiboxing (bookmark keybinds, live client previews, settings profiles, skill
plans, fittings, gamelog alerts, fleet telemetry) that also uploads OBS
recordings to YouTube. Python backend + a frameless WebView2 window
(pywebview) whose UI is plain HTML/CSS/ES5 — no framework, no build step, no
bundler.

`PRODUCT.md` decides *what belongs in the product*; `DESIGN.md` decides *how a
screen is built*. Read both before adding or reshaping a screen — they are
short, and most non-obvious rules in the UI live there rather than in comments.

The package, executable, install directory and state directory are all
named `wingman` / `FlyGD Wingman` as of 4.0.0. Installs from 3.x are
handled explicitly rather than by keeping the old names: the installer
uninstalls the predecessor by its old `AppId`, and `paths.migrate_state_dir()`
renames `%LOCALAPPDATA%\OBSYouTubeUploader` on first launch. Several
references to the old identity are load-bearing and must not be tidied
away: `LEGACY_MUTEX_NAME` in `wingman/__main__.py` (stops 3.x and 4.0
running at once), `LEGACY_APP_NAME` in `wingman/paths.py` (the migration
source directory), the legacy `AppId` uninstall key in
`packaging/installer.iss` (`RemovePredecessor()`), the legacy `.lnk` name in
`installer.iss`'s `[InstallDelete]` and in `autostart.py`'s
`_LEGACY_SHORTCUT_NAMES`, and the legacy name in `installer.iss`'s
`AppMutex`.

## Commands

Full-suite prerequisites include **Node on PATH and the built release settings
codec installed in this checkout's `packaging/bin`**. Follow the
[local prerequisite commands](docs/overview-layout-sharing-verification.md#local-verification-prerequisites)
before pytest. Native setup integration deliberately fails if the codec is absent;
Node/native skips are not acceptable full-suite coverage. CI checks Node and
builds/installs the codec before pytest, plus runs the independent Cargo regression.

```bash
uv sync --locked --extra dev              # what CI installs
uv run --no-sync python -m pytest tests/ -rs  # full suite; inspect skips
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .  # CI gates on this; run it locally
python -m wingman            # run the app (Windows only)
```

Single test / single file:

```bash
uv run python -m pytest tests/test_api_upload.py -v
uv run python -m pytest tests/test_api_upload.py::test_name -v
```

CI (`.github/workflows/ci.yml`) has two jobs. `checks` (ubuntu) asserts the
WebView2 detection predicate agrees between `packaging/installer.iss` and
`ui/preflight.py`, and runs `ruff check`, `ruff format --check` and the executable
JS smoke gate. `test` runs pytest on **both** ubuntu-latest and windows-latest,
and `cargo test` for the settings-codec sidecar in `packaging/settings-codec/`.
The old grep that compared three hand-typed version literals is gone on purpose:
the version is
derived from `wingman/__init__.py` and `tests/test_packaging_version.py`
asserts the derivation chain instead. Do not reinstate the grep.

After cloning, once: `git config blame.ignoreRevsFile .git-blame-ignore-revs`.

## Architecture

**Process shape** (`__main__.py:main`): DPI awareness → single-instance
mutexes (new and legacy) → `paths.migrate_state_dir()` → logging → settings
→ `preflight.require_webview2()` (before *anything* imports pywebview; exits
`EXIT_NO_WEBVIEW2=2`) → `AppState`, `HotkeyEngine`, preview host, alert
policy, telemetry coordinator, fleet-sharing worker, `Api` → pystray tray
icon on its own thread → the window, whose `run()` blocks the main thread.
`Api` owns the sharing subscription and one startup pending-command probe,
including with sharing Off or telemetry unavailable. A failed telemetry build
can be retried lazily; the Preview discovery callback is bound before host start.
The separate `ui/fleetpresentation.py` worker owns local Fleet presentation and
its subscription; the dispatcher only hands off state to both workers.
Shutdown closes runtime admission and detaches both subscribers **before**
native window destruction or coordinator stop. Joins run outside their state
locks; timed-out owners remain tracked, never replaced by a second owner.

`webview.start()` carries no event loop of its own, and that fact shapes two
modules: `ui/scheduler.py` (self-rescheduling timer loop replacing the old
`root.after` — watcher poll, deferred refresh, probe drain; its `finally`
always re-arms), and `preview/host.py` (its own thread with a real
`GetMessage` pump, required by `RegisterHotKey` and `SetWinEventHook`).

**The bridge** (`ui/api.py`, ~5.2k lines — the hub, and still the largest
file after the Profiles and Uploader extractions):
- Page → Python: `WM.send()` → `pywebview.api.<method>`. pywebview 6.2.1
  runs each call on its own thread, so a slow bridge method delays only its
  own promise, not the page.
- Python → page: `self._push("handlerName", payload)`, which renders as
  `window.<handler> && window.<handler>(...)` — a missing handler is a **silent
  no-op**, never an error. Every push is mirrored into the floating sig bar
  window when it exists.
- **Every non-method attribute on `Api` must be underscore-prefixed.** pywebview
  walks public attributes to build its JS proxy; a public attribute holding a
  `webview.Window` or `pystray.Icon` recurses into WinForms natives until
  `RecursionError` kills the process ~8s after launch. `test_api.py` asserts it.
- Workers never touch the page directly; they go through `_push`.
- Python pushes *semantic events*, never widget calls. Sort order and row
  focus are client state and never cross the bridge, and neither does
  selection that changes only what the page draws. Selection that changes
  what **Python computes** does cross, because the computation is here —
  today that means `skills_select_plan`, `skills_select_group`, and
  `eve_settings_select` (which persists a setting *and* rescopes the
  profile tree the next `eve_settings_state` call returns), but the list is
  whatever currently does this, not a closed set.
- **Controllers, not more bridge.** Domain orchestration that needs
  status/progress/confirm/push lives in a controller behind a small ports
  object, and `Api` keeps one-line facades: `evesettings/controller.py`
  (`ProfilesPorts`, PR #175) is the template, `upload/controller.py`
  (`UploaderPorts`) follows it exactly, and `eveskills/controller.py` and
  `evefittings/controller.py` follow the same shape with a `_push_cb`. A
  controller imports nothing from `ui` and never holds the window.
  `test_bridge_contract.py` pins the facades lexically; keep every
  `_push("literal")` visible to that guard when you move code.

**Subsystems** (each importable and unit-tested on Linux; Windows APIs are
reached through injected seams or lazy `windll` binding):
- `bookmarks.py` — pure keybind notation/validation/INI generation. The engine
  that consumes it (`hotkeys.py`, supervising the bundled AutoHotkey script in
  `engine/`, with AHK named nowhere in its public interface) cannot be tested,
  so coverage lives in the pure module.
- `preview/` — always-on-top mirrors of running EVE clients: discovery, layered
  windows, gestures, cycle keybinds, per-character geometry store, and the
  cropped-preview family (`crops.py` pure geometry, `cropstore.py` committed
  authority, `cropcontroller.py`/`cropwindow.py`/`croppicker.py` pump-owned
  natives). `host.py` is the pump thread and owns every HWND.
  **Wingman must never move or resize a real EVE client window** — EVE reads a
  resize as a resolution change and rewrites its own config.
- `telemetry/` — the one serialized coordinator (`coordinator.py`) over a
  source-aware gamelog stream (`gamelogs.py`, polling, not FS events) and
  shared client discovery (`clients.py`); `parsing.py` and `metrics.py` are
  pure. Everything downstream (alerts, previews, fleet bar, sharing) is a
  subscriber of this one dispatcher thread, so nothing slow may run on it.
- `alerts/` — gamelog alert policy: `patterns.py` (line in, event out),
  `state.py` (what an alert does over time), `service.py` (focus gating and
  sound dispatch), `sound.py`. The focus gate fails closed: EVE broadcasts
  warp lines fleet-wide, so an alert with no proven owner must not fire.
- `eveauth/` — shared EVE SSO: identities, grants, PKCE, JWT validation, the
  loopback listener, DPAPI wrapping. Capability-agnostic; Skills and
  Fittings both authenticate here and neither imports the other. The
  per-character gate serialises token refresh against re-consent.
  `eveesi.py` is the one ESI transport (path hardening, bounded retries,
  ETags, error-limit headers); the `eveskills/esi.py`, `sso.py`, `jwt.py`,
  `dpapi.py`, `loopback.py`, `tokens.py`, `application.py` modules are
  compatibility re-exports and new code imports `eveauth`/`eveesi` directly.
- `eveskills/` — skill-plan evaluation over ESI reads. `controller.py` is the
  **only writer** of the skills state document; every read-modify-write happens
  under its lock with the save in the same critical section. `evaluator.py`,
  `plans.py`, `training.py` are pure.
- `evefittings/` — personal fittings library and cross-character copy.
  `controller.py` is the single writer of the consolidated library
  (`store.py`); `model.py` is pure. Every ESI write records an on-disk
  intent first so a crash mid-copy cannot duplicate a fitting.
- `evesettings/` — copy one character's/account's EVE settings onto others,
  backup first. Copy loops never abort on first failure; they report per target.
  `codec.py` is the only module that knows a `.dat` has structure; it drives a
  bundled sidecar (`packaging/settings-codec/`, our own crate) that is a pure
  stdin/stdout filter and never opens a file. `formations.py` and
  `formation_sharing.py` are pure and speak meters.
- `wanderer/` — default-off, read-only map names for current primary preview
  sessions. `model.py` pins the deployed v1 snapshot contract; `credentials.py`
  DPAPI-protects the entire URL/map/token binding separately from settings.
  `client.py` makes one bounded HTTPS attempt; `worker.py` retains one HTTP lane
  (Test included) and an independent monotonic expiry owner. A 304 never renews
  location deadlines; 401/403 headers clear cached names before body reads finish.
  `controller.py` persists before reconfiguration and fences the host generation
  before worker admission. Host callbacks only cache detached revision/session
  snapshots; separate controller handoff/health owners do the work. No network,
  disk, DPAPI or page work belongs on discovery, telemetry, expiry or the native
  pump. PreviewHost's coalescing metadata mailbox is keyed by full ClientSessionId,
  bounded by its current admitted roster (not recent-name CAP64); only its pump
  touches the existing two-line label. Final shutdown detaches/closes metadata
  admission before native destruction and retains timed-out owners. No location
  history, ESI/OAuth, map writes, fleet-sharing publication or companion dependency.
- `fleetsharing/` — default-off publisher of projected fleet telemetry to an
  external relay: `projection.py`, `crypto.py`, `model.py`, `state.py` are pure
  or local-persistence seams; `client.py` is the signed transport; `worker.py`
  is the coalescing publisher. Gated by `settings.validated_fleet_sharing`.
- `watcher.py` — polls the recording folder (not FS events); a file is announced
  only after its size holds steady across consecutive polls **and** a
  share-mode-0 open proves no one still holds it. The second condition is not
  redundant: OBS's muxer flushes in bursts (measured 17-20s apart on a quiet
  scene, against a 9s settle), so a steady size alone re-announced the same
  in-progress recording once per flush for the length of the recording.
- `upload/` — the Uploader runtime. `controller.py` owns the rows, the
  durations/link stores, the probe drain, the upload worker, Retry, Cancel
  and the combat-log post; `ui/api.py` keeps one-line facades and one literal
  `_push` adapter per `publish_*` port. `gate.py` is the work gate that
  upload, the app updater and Quit all claim against — **one** instance,
  built in `Api.__init__` and injected into the controller, because the
  updater and `_claim_quit` still live on the bridge and a gate they cannot
  see would let an installer launch over a running upload.
- `uploader.py`, `stitch.py` (bundled FFmpeg), `combatlog.py` + `discord.py`,
  `library.py`, `durations.py`, `links.py`, `settings.py`, `paths.py`,
  `atomicio.py`, `updates.py` (release discovery with strict validation),
  `fightrecorder.py` (the OBS plugin), `obsconfig.py`, `evewindows.py`,
  `autostart.py`, `procid.py`. `durations.py` and `links.py` are the same
  `(size, mtime)` key for two different reasons — a stale duration is
  cosmetic, a stale link opens the wrong video — which is why only the first
  one prunes.

**UI layer** (`wingman/ui/`): `preflight.py`, `window.py` (construction,
lifecycle, `MIN_WIDTH`/`MIN_HEIGHT`), `chrome.py` (the resize border a
frameless window does not get), `copy.py` (every user-visible string the UI
decides, as pure functions), `rows.py` (the recording row model as the page
sees it), `scheduler.py`, and two auxiliary always-on-top windows,
`sigbar.py` and `fleetbar.py`, each with its own page.

**Web layer** (`wingman/web/`): `app.js` is the shell and bridge client with a
strict `WM.HANDLERS` allowlist; one route/screen per JS file, loaded by
`index.html` in this order: `characters`, `bookmarks`, `fleet`, `previews`, `wanderer`, `fleetsharing`, `alerts`,
`evesettings` (the Profiles route), `formations`, `uisetup`, `list`, `panel` (upload
panel, status strip, dialog layer), `settings`, `skills`, `fittings`,
`firstrun`, `dev`. `fleet.js` owns Fleet telemetry's local display settings and
its global status-strip toggle; its boot hydration is independent of section
visibility. Section re-entry retries only failed initial hydration, never adds
reads after success. `fleetsharing.js` owns the shared setup view, not worker lifetime.
`wanderer.js` owns the Wanderer names card in Settings > Previews; health pushes
never overwrite field drafts. Test saves submitted URL/map/token as one connection;
blank tokens reuse only the current normalized binding, and Remove clears all three
while retaining the independent enable preference.
`WM.route` switches destinations, `WM.section` switches
Settings groups; both have enter/leave contracts, and leaving is load-bearing
(keybind capture listeners must disarm). `dev.js` renders the page with fake
data in a plain browser via `?dev=1` — the only file that fabricates data,
inert in the app. `fleetbar.html`/`sigbar.html` are separate documents that
do **not** load `app.js`: their handlers are bare `window.onX` globals and
their bridge calls go through a local `send()`, so the allowlist and its
tests do not see them.

## Working on the UI

**Nothing in the pytest suite renders the page.** Most web guards are lexical;
the Node smoke gate executes top-level page scripts, and focused Node harnesses
execute production modules against DOM/bridge doubles (including setup's real
route/owner wiring), not CSS or WebView2. Handlers register at the top of each
module's IIFE, so one bad name throws mid-module and every registration below it
silently never runs — the screen loads as an inert, empty copy of itself with no
error anywhere. Assume a new screen is broken until opened by hand, and treat
`docs/smoke-checklist.md` as part of the change.

The lexical guards cover conventions beyond the focused runtime harnesses;
keep them and the executable smoke gate green and extend them with new conventions:
- `test_bridge_contract.py` — every `_push("name")` in `ui/api.py` exists in
  `WM.HANDLERS`, every `WM.send('name')` exists on `Api`, every handler has
  exactly one owner, and facades delegate to their controller.
- `scripts/js_smoke.js` (run by CI's `checks` job and by `test_js_smoke.py`
  where node is on PATH) — the **executable top-level** gate: loads `app.js` and
  every `<script src>` of all three pages under node with a DOM stub and
  fails on anything an IIFE throws at top level (unknown handler names,
  misspelled identifiers, missing `WM.*` members, wrong script order). It
  cannot catch a handler body failing on a real payload, a missing element
  id, or CSS; only synchronous top level runs, never timers or listeners.
- `test_page_conventions.py` — the mechanical half of `DESIGN.md`.
- `test_engine_invariants.py`, `test_no_tk.py` (Tk is gone and must stay gone),
  `test_packaging_completeness.py`, `test_packaging_version.py`.

Hard rules from `DESIGN.md` worth knowing before you touch a screen:
- Checkboxes/radios must use the `.check`/`.radio` wrappers; a bare input is a
  white Win32 widget on a dark card.
- Never `window.confirm/prompt/alert` — use `WM.confirm` / `WM.prompt`. A
  page-initiated dialog is owned by the page; Python's `_confirm` exists for
  workers that must park until the user answers, and it is never called from
  a bridge method.
- `hidden` needs an explicit `[hidden]` override on any selector that sets a
  display.
- Colours are decided only by `:root` tokens. 4.5:1 text contrast, 3:1 focus.
- Settings has no Save button: every field commits through a per-field endpoint
  returning `{applied, persisted, error}`. Discrete controls commit on change;
  free text commits on Enter or an explicit button, never on blur. Wanderer's
  bound URL/map/token are the scoped grouped exception: Test saves the connection,
  while each field still owns its drafts. Nothing commits before the first payload
  renders.
- Title-bar space is the scarce resource; `MIN_WIDTH`/`MIN_HEIGHT` in
  `ui/window.py` are **logical** pixels, measured not derived, so the CSS
  viewport floor is 840x625 at every scaling — not 840/scale. Do the
  arithmetic before adding a destination.

## Conventions

- Comments here carry the *why*, often naming the incident that caused the rule.
  Match that: explain the tradeoff, not the code. Do not delete a comment because
  its rule looks arbitrary. Em dashes are house style.
- Ruff lint selects `BLE` (blind except) among others; every new `# noqa: BLE001`
  must state why the exception is swallowed. `E501` is off — the formatter owns
  line length (88).
- `packaging/` and `*.md` are excluded from ruff (`force-exclude = true`); the
  design/plan `.md` files under `docs/history/` are historical records of
  completed work and are not reformatted or corrected after the fact — code
  and tests cite them by path and line. Finished design/plan docs under
  `docs/` move there; `docs/reference/` holds shipped reference material.
  The repo root keeps only `README.md`, `AGENTS.md`, `CLAUDE.md`,
  `PRODUCT.md`, `DESIGN.md` and `THIRD-PARTY-NOTICES.md` (the last is
  shipped by the installer).
- `[tool.setuptools] packages` is an explicit list — a new subpackage must be
  added by hand or it installs cleanly and fails at import in the frozen build.
- Anything derived (counts, key lists) must be derived or asserted in a test, not
  retyped; hand-kept copies have drifted into user-visible text before.
- `tests/conftest.py` redirects `LOCALAPPDATA` per test (autouse), so all state
  paths land in `tmp_path`. Don't stub `paths.settings_file()` instead.
- `pywebview==6.2.1` is pinned exactly; treat an upgrade as a change needing a
  full manual smoke pass.
- `credentials.py` holds placeholders in the source tree; real OAuth client
  config is injected from secrets by `release.yml`. Never commit real values.
- Pull requests target `elboaf/FlyGD-Wingman` `main` from a branch pushed to
  the `fork` remote; pass `-R` to `gh` explicitly, it guesses wrong.
