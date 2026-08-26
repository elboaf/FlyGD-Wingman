# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FlyGD Wingman: a Windows-only, tray-resident desktop app for EVE Online
multiboxing (bookmark keybinds, live client previews, settings profiles, skill
plans) that also uploads OBS recordings to YouTube. Python backend + a
frameless WebView2 window (pywebview) whose UI is plain HTML/CSS/ES5 — no
framework, no build step, no bundler.

`PRODUCT.md` decides *what belongs in the product*; `DESIGN.md` decides *how a
screen is built*. Read both before adding or reshaping a screen — they are
short, and most non-obvious rules in the UI live there rather than in comments.

The package/import name, executable name, and `%LOCALAPPDATA%\OBSYouTubeUploader`
state directory all keep the old `wingman` name on purpose so
existing installs stay upgradeable. Do not rename them.

## Commands

```bash
uv sync --locked --extra dev              # what CI installs
uv run --no-sync python -m pytest tests/  # full suite
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .  # CI gates on this; run it locally
python -m wingman            # run the app (Windows only)
```

Single test / single file:

```bash
uv run python -m pytest tests/test_api_upload.py -v
uv run python -m pytest tests/test_api_upload.py::test_name -v
```

CI (`.github/workflows/ci.yml`) gates on: pytest on **both** ubuntu-latest and
windows-latest, `ruff check`, `ruff format --check`, plus text checks that the
version agrees across `pyproject.toml` / `wingman/__init__.py` /
`packaging/installer.iss`, and that the WebView2 detection predicate agrees
between `packaging/installer.iss` and `ui/preflight.py`.

After cloning, once: `git config blame.ignoreRevsFile .git-blame-ignore-revs`.

## Architecture

**Process shape** (`__main__.py:main`): single-instance mutex → DPI awareness →
logging → `preflight.require_webview2()` (before *anything* imports pywebview;
exits `EXIT_NO_WEBVIEW2=2`) → build `AppState`, `HotkeyEngine`, `Api`, preview
host → pystray tray icon → `webview.start()`.

`webview.start()` carries no event loop of its own, and that fact shapes three
modules: `ui/scheduler.py` (self-rescheduling timer loop replacing the old
`root.after` — watcher poll, deferred refresh, probe drain; its `finally`
always re-arms), and `preview/host.py` (its own thread with a real `GetMessage`
pump, required by `RegisterHotKey` and `SetWinEventHook`).

**The bridge** (`ui/api.py`, ~2.6k lines — the hub):
- Page → Python: `WM.send()` → `pywebview.api.<method>`.
- Python → page: `self._push("handlerName", payload)`, which renders as
  `window.<handler> && window.<handler>(...)` — a missing handler is a **silent
  no-op**, never an error.
- **Every non-method attribute on `Api` must be underscore-prefixed.** pywebview
  walks public attributes to build its JS proxy; a public attribute holding a
  `webview.Window` or `pystray.Icon` recurses into WinForms natives until
  `RecursionError` kills the process ~8s after launch. `test_api.py` asserts it.
- Workers never touch the page directly; they go through `_push`.
- Python pushes *semantic events*, never widget calls. Selection, sort order and
  row focus are client state and never cross the bridge.

**Subsystems** (each importable and unit-tested on Linux; Windows APIs are
reached through injected seams or lazy `windll` binding):
- `bookmarks.py` — pure keybind notation/validation/INI generation. The engine
  that consumes it (`hotkeys.py`, supervising a bundled AutoHotkey process, with
  AHK named nowhere in its public interface) cannot be tested, so coverage lives
  in the pure module.
- `preview/` — always-on-top mirrors of running EVE clients: discovery, layered
  windows, gestures, cycle keybinds, per-character geometry store.
  **Wingman must never move or resize a real EVE client window** — EVE reads a
  resize as a resolution change and rewrites its own config.
- `evesettings/` — copy one character's/account's EVE settings onto others,
  backup first. Copy loops never abort on first failure; they report per target.
- `eveskills/` — EVE SSO + ESI, skill-plan evaluation. `controller.py` is the
  **only writer** of the skills state document; every read-modify-write happens
  under its lock with the save in the same critical section.
- `watcher.py` — polls the recording folder (not FS events); a file is announced
  only after its size holds steady across consecutive polls.
- `uploader.py`, `stitch.py` (bundled FFmpeg), `combatlog.py` + `discord.py`,
  `library.py`, `durations.py`, `links.py`, `settings.py`, `paths.py`,
  `atomicio.py`. `durations.py` and `links.py` are the same `(size, mtime)`
  key for two different reasons — a stale duration is cosmetic, a stale link
  opens the wrong video — which is why only the first one prunes.

**Web layer** (`wingman/web/`): `app.js` is the shell and bridge
client with a strict `WM.HANDLERS` allowlist; one route/screen per JS file.
`WM.route` switches destinations, `WM.section` switches Settings groups; both
have enter/leave contracts, and leaving is load-bearing (keybind capture
listeners must disarm). `dev.js` renders the page with fake data in a plain
browser via `?dev=1` — the only file that fabricates data, inert in the app.

## Working on the UI

**Nothing in the test suite renders the page.** pytest reads web source
lexically; it never executes it. Handlers register at the top of each module's
IIFE, so one bad name throws mid-module and every registration below it silently
never runs — the screen loads as an inert, empty copy of itself with no error
anywhere. Assume a new screen is broken until opened by hand, and treat
`docs/smoke-checklist.md` as part of the change.

The lexical guards that stand in for a JS harness — keep them green and extend
them when you add a convention:
- `test_bridge_contract.py` — every `_push("name")` in `ui/api.py` exists in
  `WM.HANDLERS`.
- `test_page_conventions.py` — the mechanical half of `DESIGN.md`.
- `test_engine_invariants.py`, `test_no_tk.py` (Tk is gone and must stay gone),
  `test_packaging_completeness.py`.

Hard rules from `DESIGN.md` worth knowing before you touch a screen:
- Checkboxes/radios must use the `.check`/`.radio` wrappers; a bare input is a
  white Win32 widget on a dark card.
- Never `window.confirm/prompt/alert` — use `WM.confirm` / `WM.prompt`. Python's
  `_confirm` cannot serve a page-initiated dialog (it deadlocks).
- `hidden` needs an explicit `[hidden]` override on any selector that sets a
  display.
- Colours are decided only by `:root` tokens. 4.5:1 text contrast, 3:1 focus.
- Settings has no Save button: every field commits through a per-field endpoint
  returning `{applied, persisted, error}`. Discrete controls commit on change;
  free text commits on Enter or an explicit button, never on blur. Nothing
  commits before the first payload renders.
- Title-bar space is the scarce resource; `MIN_WIDTH`/`MIN_HEIGHT` in
  `ui/window.py` are **logical** pixels, measured not derived, so the CSS
  viewport floor is 840x625 at every scaling — not 840/scale. Do the
  arithmetic before adding a destination.

## Conventions

- Comments here carry the *why*, often naming the incident that caused the rule.
  Match that: explain the tradeoff, not the code. Do not delete a comment because
  its rule looks arbitrary.
- Ruff lint selects `BLE` (blind except) among others; every new `# noqa: BLE001`
  must state why the exception is swallowed. `E501` is off — the formatter owns
  line length (88).
- `packaging/` and `*.md` are excluded from ruff (`force-exclude = true`); the
  design/plan `.md` files under `docs/history/` are historical records of
  completed work and are not reformatted or corrected after the fact. The repo
  root keeps only `README.md`, `CLAUDE.md`, `PRODUCT.md`, `DESIGN.md` and
  `THIRD-PARTY-NOTICES.md` (the last is shipped by the installer).
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
