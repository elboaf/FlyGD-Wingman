# FlyGD Wingman UI Replatform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Tkinter/ttk UI with a pywebview + WebView2 shell rendering plain HTML/CSS/JS, delivering the approved "direction B" design without changing any upload, stitching, combat-log, or Discord behaviour.

**Architecture:** Python keeps everything it does today except drawing — tray icon, folder watching, ffmpeg, OAuth, uploads — and gains a `js_api` bridge object that pushes semantic messages into a local page and receives method calls back. The page owns selection, sort, focus, and styling; Python owns state, work, and the filesystem. Tk's event loop is replaced by an explicit `Scheduler` for the watcher poll, because pywebview has no `root.after()` equivalent.

**Tech Stack:** Python 3.11+, pywebview 6.x (pinned) on the `edgechromium` backend, WebView2 Runtime (Evergreen), pystray, Pillow, PyInstaller 6.x one-folder, Inno Setup 6.3+, pytest.

**Spec:** `webview-replatform-design.md`

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the spec.

- **Windows-only.** No cross-platform support is in scope. Tests must still run headless on `ubuntu-latest`, so anything Windows-specific takes an injectable reader/alert argument, following `theme.py`'s existing `reader=` convention.
- **The `js_api` object exposes JS-callable METHODS ONLY.** Every other attribute is underscore-prefixed. pywebview builds its JS proxy by walking the object's public attributes; a public attribute holding a `webview.Window` or `pystray.Icon` sends that walk into the WinForms native object, where `Rectangle.Empty` returns itself, and it recurses until `RecursionError` terminates the process roughly eight seconds after launch. This is not theoretical — it was observed in the spike.
- **pywebview is pinned** to a known-good 6.x. 6.x has live API churn (`FOLDER_DIALOG` is already deprecated for `FileDialog.FOLDER`). Treat an upgrade as a change requiring a full smoke pass.
- **The backend is pinned to `gui="edgechromium"`.** Autodetection silently falling back to another backend would make a passing run meaningless.
- **Frameless windows get explicit `x`/`y`.** pywebview gives them no sensible default placement; the spike's window opened off-screen.
- **Nothing pywebview reports can be trusted to raise or to set a non-zero exit code.** When the WebView2 runtime was absent, initialization failed, `webview.start()` returned normally, and the process exited 0. Anything that must not fail silently needs its own explicit check.
- **No build step.** Plain HTML/CSS/JS only — no bundler, no framework, no Node in the release pipeline.
- **No light mode.** Direction B is a dark design; `theme.py`'s `AppsUseLightTheme` detection and live-switch machinery are deleted, not ported.
- **No Playwright or browser test toolchain.** The agreed strategy is bridge-level Python tests plus the manual smoke checklist in `docs/smoke-checklist.md`.
- **Every user-visible string is a pure module-level function**, following `format_selection_summary`. This convention was established in 2.2.0 because copy is what regresses and widgets are the one layer with no test harness. Extend it; never inline user-facing strings into HTML.
- **Compatibility is non-negotiable.** The `%LOCALAPPDATA%` state directory, settings file format and location, credentials file, durations cache, distribution name `obs-youtube-uploader`, PyInstaller entry point, Inno `AppId`, and the release workflow's credential-injection step all stay exactly as they are. An existing installation must upgrade in place with its settings and sign-in intact.
- **Type scale, adopted from 2.2.0, not reinvented:** 13px body, 15.5px headings (1.2×), 11.5px muted text and column headers (0.875×), 12px monospace for machine text, 10.5px uppercase tracked `.14em` for section labels. **Column headers sit below body size on purpose** — they label the data, they are not the data.
- **Design tokens** (CSS custom properties, replacing `theme.py`'s `TOKENS` dict): `--bg #0c0d10`, `--panel #14161b`, `--panel-border #1e2128`, `--field #0a0b0e`, `--field-border #23262e`, `--text #e8eaed`, `--text-dim #9aa2b1`, `--text-faint #6f7681`, `--brand #ff5a4d`, `--brand-deep #c81e12`, `--ok #4ade80`, `--warn #d29922`, `--err #f85149`.
- **Status severity values stay `FG` / `SUCCESS` / `WARNING` / `ERROR`**, matching today's `_status_kind`.
- **Rows cross the bridge as opaque ids, never filesystem paths**, and every API method resolves an id against the backend's current row snapshot.

## Bridge Protocol Reference

Every task that touches the bridge uses these exact names.

**Python → page** (fire-and-forget, via `evaluate_js` calling `window.<handler>(payload)`):

| Handler | Payload |
|---|---|
| `onRows` | `{rows: [{id, name, date, size, duration, link, preselected}]}` |
| `onDuration` | `{id, duration, definitive}` |
| `onProgress` | `{mode: "determinate"\|"indeterminate", pct, text, kind}` |
| `onStatus` | `{text, kind}` |
| `onRetryAvailable` | `{available: bool}` |
| `onLink` | `{id, video_id}` |
| `onSettings` | `{settings, webhook_status, detected, destination}` |
| `onChannel` | `{channel_id, channel_title, destination}` |
| `onAuthState` | `{state: "disconnected"\|"connecting"\|"connected"\|"revoking", message}` |
| `onDialog` | `{kind: "info"\|"error"\|"warning"\|"confirm", title, body, request_id}` |
| `onFirstRun` | `{}` — no recording folder is configured; show the first-run route |

**Page → Python** (via `pywebview.api.<method>`). Everything public on `Api` is
reachable from the page, so this list is exhaustive by construction:

| Method | Returns | Task |
|---|---|---|
| `list_rows()` | — | 6 |
| `panel_text(ids, stitch)` | `{summary, title_hint}` | 6 |
| `start_upload(title, description, privacy, category, stitch, ids)` | — | 7 |
| `retry()` | — | 7 |
| `upload_combat_logs(ids)` | — | 8 |
| `delete_selected(ids)` | — | 8 |
| `open_path(id)` | — | 8 |
| `copy_path(id)` | the URL, for the page to write to the clipboard | 8 |
| `save_settings(obj)` | `bool` — `False` means the form stays open | 9 |
| `pick_folder(which)` | the chosen path, or `""` on cancel | 9 |
| `detect_folder(which, current)` | the detected path, or `""` | 9 |
| `connect_google()` | — | 9 |
| `auth_labels()` | the four account states' `{message, label, enabled}` | 9 |
| `refresh_auth()` | — | 9 |
| `set_recording_dir(path)` | `bool` — `False` keeps the first-run route up | 13 |
| `dialog_response(request_id, ok)` | — | 4 |
| `minimize()` | — | 4 |
| `close()` | — **hides**, never destroys | 4 |

`which` is `"recording"` or `"gamelogs"` throughout — the same two values
`detect_folder`'s `detected` payload keys use.

`refresh_auth()` is called by `__main__` at startup, not by the page. It is
public because everything on `Api` that is not underscore-prefixed is, and the
methods-only rule leaves no third category; exposing it is harmless, since
calling it twice is idempotent by its own `_auth_busy()` guard.

`close()` **hides the window**. Destroying would return from `webview.start()`,
stop the tray, and end the process — so closing the window would silently stop
the recording watcher. Only the tray's Quit destroys, and it calls
`window.destroy()` directly rather than through the bridge. The Tk build bound
`WM_DELETE_WINDOW` to `hide()` for exactly this reason.

`onDialog`'s `confirm` variant is the only request/response pair in an otherwise fire-and-forget protocol: `Api._confirm()` pushes it with a `request_id` and blocks the calling worker thread on a `threading.Event` until the page answers via `dialog_response`.

**Client-side only, never crossing the bridge:** selection state, sort column and direction, row focus, column widths, checkbox rendering, striping, theme application. The one exception is the initial `preselected` flag arriving on `onRows`, because the watcher preselects newly-finished recordings so the common case needs no clicking.

**Rendered in Python, never composed in the page:** the selection summary and
Title hint (via `panel_text`), the destination line (pushed on `onChannel` and
`onSettings`), the webhook status line, the account-state labels (via
`auth_labels`), every dialog body, and the list's cell tooltips. All are pure
functions in `ui/copy.py` with their own tests. The page renders strings; it
does not decide them. This is 2.2.0's convention, and it is what lets the copy
and its tests cross the port untouched.

## File Structure

| File | Responsibility |
|---|---|
| `obs_youtube_uploader/ui/preflight.py` | WebView2 runtime detection and the native failure dialog |
| `obs_youtube_uploader/ui/copy.py` | Every user-visible string, as pure functions |
| `obs_youtube_uploader/ui/rows.py` | Row model, opaque ids, id → `VideoInfo` resolution |
| `obs_youtube_uploader/ui/api.py` | The `js_api` bridge — methods only |
| `obs_youtube_uploader/ui/scheduler.py` | Watcher poll timing, replacing `root.after()` |
| `obs_youtube_uploader/ui/window.py` | Frameless window construction and lifecycle |
| `obs_youtube_uploader/web/` | `index.html`, `style.css`, `app.js`, `list.js`, `panel.js`, `settings.js`, `dev.js` — the page. Settings is a **route inside `index.html`**, not a second document |
| `obs_youtube_uploader/__main__.py` | Startup ordering, tray, shutdown (rewritten) |

**Deleted at Task 16:** `app.py`, `settingsui.py`, `theme.py`, `tooltip.py`'s widget machinery, and seven widget-based test files.

## Ordering and the Point of No Return

Tasks 1–13 are additive: the Tk UI keeps working throughout, and every task is independently reviewable. **Task 16 is irreversible** — the Tk and webview UIs cannot run side by side, so the only mitigation is ordering. Do not start Task 16 until Tasks 14 and 15 are complete and the application has been driven against real recordings through the new UI.

---

### Task 1: WebView2 pre-flight check

**Files:**
- Create: `obs_youtube_uploader/ui/__init__.py`
- Create: `obs_youtube_uploader/ui/preflight.py`
- Modify: `pyproject.toml`
- Test: `tests/test_preflight.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"`
  - `REGISTRY_KEYS: tuple[tuple[str, str], ...]`
  - `DOWNLOAD_URL: str`, `MISSING_RUNTIME_TITLE: str`
  - `def missing_runtime_message() -> str`
  - `def _read_pv(hive: str, subkey: str) -> str | None`
  - `def webview2_version(reader=_read_pv) -> str | None`
  - `def _message_box(title: str, body: str) -> None`
  - `def require_webview2(version=webview2_version, alert=_message_box) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preflight.py
"""The WebView2 runtime pre-flight check.

Spike Q7 is the reason this module exists: with no runtime installed,
pywebview logs the initialization failure, returns from webview.start()
normally, and the process exits 0. A windowed build has no console, so the
user gets no window, no error, and a success exit code. Everything here is
about making that state loud.

Registry access and the native message box are injected, so the decision
logic is tested on ubuntu-latest with no Windows and no runtime present --
the same reader= convention theme.detect_mode uses.
"""
import sys

import pytest

from obs_youtube_uploader.ui import preflight


def _reader(present: dict):
    """A fake _read_pv over a {(hive, subkey): pv} mapping."""
    return lambda hive, subkey: present.get((hive, subkey))


def test_all_three_documented_keys_are_checked():
    """Per-machine 64-bit, per-machine 32-bit, and per-user are three real
    install shapes; checking only the first would call a per-user install
    absent and refuse to start on a machine that works."""
    hives = {hive for hive, _ in preflight.REGISTRY_KEYS}
    assert hives == {"HKLM", "HKCU"}
    assert len(preflight.REGISTRY_KEYS) == 3
    for _, subkey in preflight.REGISTRY_KEYS:
        assert subkey.endswith(preflight.WEBVIEW2_GUID)


@pytest.mark.parametrize("key", list(range(3)))
def test_a_version_under_any_single_key_counts_as_present(key):
    hive, subkey = preflight.REGISTRY_KEYS[key]
    found = preflight.webview2_version(
        reader=_reader({(hive, subkey): "151.0.4129.93"}))
    assert found == "151.0.4129.93"


def test_no_key_at_all_reads_as_absent():
    assert preflight.webview2_version(reader=_reader({})) is None


def test_a_zeroed_version_reads_as_absent():
    """EdgeUpdate leaves pv=0.0.0.0 behind after an uninstall. Treating that
    as a version is how a stale registry key turns into a silent no-window
    launch -- exactly the failure the check exists to prevent."""
    present = {k: "0.0.0.0" for k in preflight.REGISTRY_KEYS}
    assert preflight.webview2_version(reader=_reader(present)) is None


def test_an_empty_version_reads_as_absent():
    present = {k: "" for k in preflight.REGISTRY_KEYS}
    assert preflight.webview2_version(reader=_reader(present)) is None
    present = {k: "   " for k in preflight.REGISTRY_KEYS}
    assert preflight.webview2_version(reader=_reader(present)) is None


def test_a_usable_key_wins_over_an_emptied_one():
    """A machine can carry a stale zeroed per-machine key beside a live
    per-user install. Order of the scan must not decide the verdict."""
    stale = preflight.REGISTRY_KEYS[0]
    live = preflight.REGISTRY_KEYS[2]
    found = preflight.webview2_version(
        reader=_reader({stale: "0.0.0.0", live: "151.0.4129.93"}))
    assert found == "151.0.4129.93"


def test_a_reader_that_raises_does_not_take_down_startup():
    """Injected here, but the real reader wraps winreg, which raises for a
    dozen unremarkable reasons. An unreadable key means "not found here",
    never "crash before the window exists"."""
    def boom(hive, subkey):
        raise OSError("access denied")

    assert preflight.webview2_version(reader=boom) is None


def test_present_runtime_proceeds_without_alerting():
    alerts = []
    ok = preflight.require_webview2(
        version=lambda: "151.0.4129.93",
        alert=lambda title, body: alerts.append((title, body)))
    assert ok is True
    assert alerts == []


def test_absent_runtime_alerts_and_refuses_to_proceed():
    alerts = []
    ok = preflight.require_webview2(
        version=lambda: None,
        alert=lambda title, body: alerts.append((title, body)))
    assert ok is False
    assert len(alerts) == 1


def test_the_alert_names_the_runtime_and_where_to_get_it():
    """The user cannot act on "WebView2 failed". They can act on a product
    name and a URL, which is the entire content of this dialog."""
    body = preflight.missing_runtime_message()
    assert "WebView2" in body
    assert "Evergreen" in body
    assert preflight.DOWNLOAD_URL in body


def test_the_alert_title_says_what_is_missing():
    assert "WebView2" in preflight.MISSING_RUNTIME_TITLE


@pytest.mark.skipif(sys.platform == "win32",
                    reason="off-Windows degradation; on Windows it really reads the registry")
def test_the_real_reader_degrades_rather_than_raising_off_windows():
    for hive, subkey in preflight.REGISTRY_KEYS:
        assert preflight._read_pv(hive, subkey) is None


@pytest.mark.skipif(sys.platform == "win32",
                    reason="would pop a real modal dialog and hang the suite")
def test_the_real_message_box_is_a_no_op_off_windows():
    """ctypes.windll does not exist off Windows. This must degrade, not
    raise: the suite runs on ubuntu-latest."""
    assert preflight._message_box("title", "body") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_preflight.py -v`
Expected: FAIL — collection error, `ModuleNotFoundError: No module named 'obs_youtube_uploader.ui'`

- [ ] **Step 3: Create the package and write the implementation**

```python
# obs_youtube_uploader/ui/__init__.py
"""The webview UI layer: pre-flight, copy, row model, bridge, and window.

Separate from the package root so the Tk modules being replaced and the
webview modules replacing them can coexist during the port without either
importing the other by accident.
"""
```

```python
# obs_youtube_uploader/ui/preflight.py
"""Verify the WebView2 runtime before pywebview is allowed to try.

pywebview does not fail when the runtime is missing. It logs the exception,
returns from webview.start() normally, and the process exits 0 -- so a user
without the runtime gets no window, no error dialog, and a success exit
code. In a windowed build there is no console either, so even the logged
diagnostic is unreachable. Nothing downstream can detect this state, which
is why the check has to happen before webview is started rather than around
it.

The installer's Evergreen bootstrapper does not make this redundant: a
runtime can be uninstalled or broken after a successful install. The
installer's detection and this one are deliberately the same predicate over
the same three keys, and must stay that way.

Testable without a VM: point WEBVIEW2_BROWSER_EXECUTABLE_FOLDER at an empty
directory to reproduce the runtime-not-found path non-destructively.
"""
import logging
import sys

logger = logging.getLogger(__name__)

# EdgeUpdate's client id for the WebView2 Evergreen runtime. Also used by
# installer.iss -- if this constant changes, that one has to change with it.
WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

# All three are real install shapes and any one of them means present:
# per-machine on 64-bit Windows (WOW6432Node -- EdgeUpdate is a 32-bit
# process, so its per-machine keys land under the redirect even on x64),
# per-machine on 32-bit Windows, and per-user. Checking only the first
# would refuse to start on a machine with a working per-user runtime.
REGISTRY_KEYS = (
    ("HKLM", rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
    ("HKLM", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
    ("HKCU", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
)

# EdgeUpdate zeroes pv rather than deleting the key when the runtime is
# removed, so a bare "the key exists" test reports a runtime that is gone.
_ABSENT_VERSIONS = {"", "0.0.0.0"}

DOWNLOAD_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"

MISSING_RUNTIME_TITLE = "Microsoft WebView2 Runtime required"


def missing_runtime_message() -> str:
    """The body of the only dialog this app can show before it has a window.

    Pure and module-level for the usual reason, but with an extra one here:
    it is the single piece of copy no automated UI check will ever reach,
    since displaying it requires a machine without the runtime.

    Names the product and gives the URL because "WebView2 initialization
    failed" is not something a user can act on, and this dialog is their
    only chance -- the alternative, today, is a program that appears to do
    nothing at all.
    """
    return (
        "FlyGD Wingman needs the Microsoft Edge WebView2 Evergreen Runtime, "
        "which is not installed on this computer.\n\n"
        "Install it from:\n"
        f"{DOWNLOAD_URL}\n\n"
        "Then start FlyGD Wingman again."
    )


def _read_pv(hive: str, subkey: str) -> str | None:
    """Read one EdgeUpdate client key's `pv` value, or None.

    None on any failure and off Windows, mirroring
    theme.read_apps_use_light_theme: an unreadable key means "no runtime
    recorded here", and the caller has two more keys to try. Raising would
    turn a permissions quirk into a crash before any window exists, which
    is the failure mode this whole module was written to remove.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg

        root = winreg.HKEY_LOCAL_MACHINE if hive == "HKLM" else winreg.HKEY_CURRENT_USER
        key = winreg.OpenKey(root, subkey)
        try:
            value, _ = winreg.QueryValueEx(key, "pv")
        finally:
            winreg.CloseKey(key)
        return str(value)
    except Exception:
        return None


def webview2_version(reader=_read_pv) -> str | None:
    """The installed runtime version, or None if there is none.

    reader is injectable so the decision logic is tested off-Windows, the
    same convention as theme.detect_mode's reader= and library.discover's
    runner=.

    Scans all three keys rather than returning on the first hit's raw
    value, because a stale zeroed per-machine key can sit beside a live
    per-user install; stopping early would report absent on a machine where
    the runtime works.
    """
    for hive, subkey in REGISTRY_KEYS:
        try:
            value = reader(hive, subkey)
        except Exception:
            continue
        if value is None:
            continue
        value = value.strip()
        if value not in _ABSENT_VERSIONS:
            return value
    return None


def _message_box(title: str, body: str) -> None:
    """A native modal, because no webview exists to render an in-app one.

    MB_SETFOREGROUND|MB_TOPMOST are not decoration: this fires before any
    window is created, so the dialog has no owner and lands behind whatever
    the user was doing without them -- which would reproduce the very
    silence it is here to break.

    Off Windows this is a no-op so the suite runs on ubuntu-latest; the
    caller's decision does not depend on the dialog appearing.
    """
    if sys.platform != "win32":
        return None
    import ctypes

    MB_OK = 0x0
    MB_ICONERROR = 0x10
    MB_SETFOREGROUND = 0x10000
    MB_TOPMOST = 0x40000
    ctypes.windll.user32.MessageBoxW(
        None, body, title, MB_OK | MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST)
    return None


def require_webview2(version=webview2_version, alert=_message_box) -> bool:
    """True when it is safe to call webview.start(); False means exit non-zero.

    Returns rather than calls sys.exit so the caller keeps ordering control
    -- the tray icon may already be running by this point and needs
    stopping before the process ends.

    Logs as well as alerting: the dialog is for the user, the log line is
    for the support conversation afterwards, and Q7 proved neither exists
    by default.
    """
    found = version()
    if found is not None:
        logger.debug("WebView2 runtime %s detected", found)
        return True
    logger.error("WebView2 runtime not found; refusing to start a webview "
                 "that would silently render nothing")
    alert(MISSING_RUNTIME_TITLE, missing_runtime_message())
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preflight.py -v`
Expected: PASS (all cases; the two `skipif` cases run on Linux and skip on Windows)

- [ ] **Step 5: Declare the new subpackage so frozen builds keep it**

Edit `pyproject.toml`'s `[tool.setuptools]` block:

```toml
[tool.setuptools]
# Declared explicitly rather than left to auto-discovery. `packaging/` holds
# build scripts, not an importable package, but setuptools' flat-layout
# discovery sees it (and `packaging/bin/` once ffmpeg is fetched) as
# additional top-level packages, hits the multiple-top-level-packages error,
# and aborts the install entirely. That failure took down every dependency
# and produced a frozen build with no pystray in it.
#
# Subpackages are NOT implied by their parent here: an explicit list means
# every new one must be added by hand, and a missing entry installs cleanly
# and fails at import time in the built artifact, not in the checkout where
# the source tree makes it work anyway.
packages = ["obs_youtube_uploader", "obs_youtube_uploader.ui"]
```

- [ ] **Step 6: Verify the package really installs**

Run: `python -m pip install -e . --no-deps -q && python -c "from obs_youtube_uploader.ui import preflight; print(preflight.webview2_version())"`
Expected: PASS — prints `None` (off Windows), no ImportError

- [ ] **Step 7: Commit**

```bash
git add obs_youtube_uploader/ui/__init__.py obs_youtube_uploader/ui/preflight.py tests/test_preflight.py pyproject.toml
git commit -m "Pre-flight the WebView2 runtime instead of exiting 0 with no window"
```

---

### Task 2: Extract pure copy functions to `ui/copy.py`

**Files:**
- Create: `obs_youtube_uploader/ui/copy.py`
- Modify: `obs_youtube_uploader/app.py`
- Modify: `obs_youtube_uploader/settingsui.py`
- Modify: `obs_youtube_uploader/tooltip.py`
- Test: `tests/test_app.py`, `tests/test_app_upload_copy.py`, `tests/test_settingsui_copy.py`, `tests/test_tooltip.py`

**Interfaces:**
- Consumes: the `obs_youtube_uploader.ui` package from Task 1
- Produces:
  - `def format_selection_summary(infos: list) -> str`
  - `def format_upload_confirm(infos, title: str, privacy: str, channel_title: str, stitch: bool) -> str`
  - `def webhook_status(raw: str) -> str`
  - `CELL_HELP: dict[str, dict[str, str]]`

- [ ] **Step 1: Repoint `test_app.py`'s summary cases and add the re-export guard**

In `tests/test_app.py`, add to the imports:

```python
from obs_youtube_uploader.ui import copy as copy_mod
```

then replace every `app_mod.format_selection_summary` with `copy_mod.format_selection_summary` (6 occurrences). Assertions and docstrings stay exactly as they are — unchanged expectations are the proof the move was faithful.

Append this test to the same file:

```python
def test_app_still_exposes_the_moved_copy_helpers():
    """The Tk UI is not deleted in this commit, and it calls these by bare
    name. Re-exporting the same objects (identity, not a reimplementation)
    is what lets the port land one module at a time instead of all at once."""
    assert app_mod.format_selection_summary is copy_mod.format_selection_summary
    assert app_mod.format_upload_confirm is copy_mod.format_upload_confirm
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL — collection error, `ImportError: cannot import name 'copy' from 'obs_youtube_uploader.ui'`

- [ ] **Step 3: Create `ui/copy.py` with the selection summary**

```python
# obs_youtube_uploader/ui/copy.py
"""Every user-visible string the UI decides, as pure module-level functions.

2.2.0 established this split one function at a time (format_selection_summary,
webhook_status, tooltip's cell help) for one reason: copy is what regresses,
and widgets are the one layer this repo has no test harness for. Collecting
them here makes the reason structural instead of incidental -- the strings
now live in a module with no toolkit import at all, so they cross the
Tk-to-webview port untouched, along with their tests.

Nothing in here may import tkinter, pywebview, or any widget module. That is
the whole point: if it needs a window to test, it does not belong here.
"""
from .. import discord, library, uploader

# --- main window -----------------------------------------------------------


def format_selection_summary(infos: list[library.VideoInfo]) -> str:
    """The panel's "3 selected · 1.2 GB · 2:04:35" line.

    Two asymmetries are deliberate:

    * The "+" marks the duration total as a floor, not a value. A recording
      whose probe is still outstanding contributes 0, so an unmarked total
      would read as complete while being short. It reuses the duration
      column's own vocabulary for the same state ("…" per row) rather than
      inventing a second one.
    * Size is never marked partial: info.size comes from stat, so it is
      final from the moment the row exists, whatever the probe is doing.

    A probed recording with duration None is a finished verdict (ffprobe
    could not read it), so it also contributes 0 but leaves the total exact.
    Its own row already shows "?"; repeating that diagnosis in an aggregate
    would say nothing the user can act on.

    The count carries no noun ("3 selected"), which sidesteps agreement at
    every value instead of special-casing 1.
    """
    if not infos:
        return "Nothing selected"
    total_size = sum(info.size for info in infos)
    total_seconds = int(sum(info.duration or 0.0 for info in infos))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    partial = "+" if any(not info.probed for info in infos) else ""
    return (f"{len(infos)} selected · {library.format_size(total_size)}"
            f" · {hours}:{minutes:02d}:{seconds:02d}{partial}")


def _hms(total_seconds: int) -> str:
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"
```

In `obs_youtube_uploader/app.py`, delete `format_selection_summary` and `_hms`, and add below the existing `from . import (...)` block:

```python
# Re-exported, not reimplemented. The copy moved to ui/copy.py ahead of the
# webview port; these names stay resolvable because the Tk window still
# calls them by bare name and will until it is deleted.
from .ui.copy import format_selection_summary, format_upload_confirm  # noqa: F401
```

- [ ] **Step 4: Run tests to confirm the expected intermediate failure**

Run: `python -m pytest tests/test_app.py -v -k "summary or copy_helpers"`
Expected: FAIL — `ImportError: cannot import name 'format_upload_confirm' from 'obs_youtube_uploader.ui.copy'`. The re-export line names it one step early on purpose; Step 6 moves it.

- [ ] **Step 5: Repoint `test_app_upload_copy.py`'s confirm cases**

In `tests/test_app_upload_copy.py`, add to the imports:

```python
from obs_youtube_uploader.ui import copy as copy_mod
```

then replace every `app.format_upload_confirm`, `app.format_progress`, `app.format_destination`, and `app.format_title_hint` with the `copy_mod.` equivalent. All four move together: they are pure, they all have tests here, and `app.py` is deleted in Task 16, so anything left behind is lost.

- [ ] **Step 6: Move `format_upload_confirm`**

Append to `obs_youtube_uploader/ui/copy.py`:

```python
def format_upload_confirm(infos: list[library.VideoInfo], title: str,
                          privacy: str, channel_title: str,
                          stitch: bool) -> str:
    """The body of the confirm shown before anything is published.

    This is the app's only irreversible action and it was the only one with
    no confirmation: deleting local files, which are recoverable from the
    recycle bin, already confirmed with a full file list.

    The title preview is built through uploader.build_body rather than
    reformatted here, so the numbering shown is the numbering that will be
    sent. A second implementation of that rule would drift from it.
    """
    total_size = sum(i.size for i in infos)
    total_seconds = int(sum(i.duration or 0.0 for i in infos))
    count = len(infos)
    where = channel_title or "not known yet (learned from this upload)"

    if stitch:
        shown = uploader.build_body(title, "", privacy, "", 0, 1)["snippet"]["title"]
        what = f"{count} recordings stitched into one video"
        titles = f'"{shown}"'
    else:
        first = uploader.build_body(title, "", privacy, "", 0, count)["snippet"]["title"]
        what = f"{count} recording{'s' if count != 1 else ''}"
        titles = f'"{first}"'
        if count > 1:
            last = uploader.build_body(title, "", privacy, "", count - 1,
                                       count)["snippet"]["title"]
            titles += f' … "{last}"'

    return (f"Upload {what} to YouTube?\n\n"
            f"Channel:  {where}\n"
            f"Privacy:  {privacy}\n"
            f"Title:    {titles}\n"
            f"Total:    {library.format_size(total_size)} · "
            f"{_hms(total_seconds)}\n\n"
            "Publishing to YouTube cannot be undone from this app.")
```

Also append the three remaining status-line functions, moved verbatim from `app.py`
with their docstrings intact:

```python
def format_progress(index: int, total: int, fraction: float) -> str:
    """The status line during an upload.

    The progress BAR is driven by ((index + fraction) / total), so it tracks
    the whole batch. This text tracks the file. Saying so is the whole point
    of the function: the previous wording was "Uploading 3/10 — 94.8%" beside
    a bar sitting at 34%, and the two read as a contradiction rather than as
    two different measurements.

    A single-file upload gets no "file 1 of 1", which would be noise.
    """
    pct = f"{fraction * 100:.1f}%"
    if total <= 1:
        return f"Uploading… {pct}"
    return f"Uploading file {index + 1} of {total}… {pct}"


def format_destination(channel_title: str, privacy: str) -> str:
    """The line above Upload Selected naming where the video will land.

    Empty channel_title is the normal state before the first successful
    upload, not an error: SCOPES holds youtube.upload alone, which cannot
    call channels.list, so the destination is learned from an insert
    response (uploader.channel_of) rather than looked up. Saying that
    plainly beats an empty gap where a channel name should be.
    """
    if not channel_title:
        return f"Channel confirmed after the first upload · {privacy}"
    return f"Uploads go to {channel_title} · {privacy}"


def format_title_hint(count: int, stitch: bool) -> str:
    """The Title field's label, which depends on what is selected.

    uploader.build_body appends "(n/total)" to every title in a batch and
    substitutes "Untitled" for an empty one. Neither was disclosed anywhere,
    so a user typing one title got ten differently-named public videos and
    found out afterwards. The label is the cheapest place to say it.
    """
    if stitch or count <= 1:
        return "Title"
    return f"Title — each of the {count} uploads is numbered (1/{count})…"
```

Delete `format_upload_confirm`, `format_progress`, `format_destination`, and
`format_title_hint` from `obs_youtube_uploader/app.py`, and extend its
re-export line to cover all four.

- [ ] **Step 7: Run both repointed files to verify they pass**

Run: `python -m pytest tests/test_app.py tests/test_app_upload_copy.py -v`
Expected: PASS

- [ ] **Step 8: Repoint `test_settingsui_copy.py`'s webhook cases**

In `tests/test_settingsui_copy.py`, add to the imports:

```python
from obs_youtube_uploader.ui import copy as copy_mod
```

then replace every `settingsui.webhook_status` with `copy_mod.webhook_status` (5 occurrences).

**Delete the `auth_button_state` cases from this file**, and delete `auth_button_state`, `_AUTH_BUTTON`, and `_AUTH_BUTTON_DEFAULT` from `settingsui.py`. That helper is keyed on Tk status kinds (`SUCCESS`, `ERROR`, `MUTED`, `WARNING`), a vocabulary that does not survive the port. Task 9's `copy.auth_state` is its successor, keyed on the four bridge states, and its tests cover the same four decisions: connected offers to switch, disconnected asks for sign-in, both transient states disable the button, and an unknown state stays usable. Moving the old function would leave two tables keyed on vocabularies that cannot both be right.

- [ ] **Step 9: Run test to verify it fails**

Run: `python -m pytest tests/test_settingsui_copy.py -v`
Expected: FAIL — `AttributeError: module 'obs_youtube_uploader.ui.copy' has no attribute 'webhook_status'`

- [ ] **Step 10: Move `webhook_status`**

Append to `obs_youtube_uploader/ui/copy.py`:

```python
# --- settings --------------------------------------------------------------


def webhook_status(raw: str) -> str:
    """The line under the webhook field, describing what is stored.

    The field itself is masked, so this is the only confirmation of WHICH
    webhook is configured; discord.describe omits the token by construction.

    An unparseable value reports the parse error rather than "not
    configured", which is what it used to say for anything invalid -- a URL
    the user has visibly typed being described as absent reads as the app
    ignoring them and hides the actual mistake.
    """
    if not raw or not raw.strip():
        return "not configured"
    hook, error = discord.parse_webhook(raw)
    return discord.describe(hook) if hook else error
```

Delete `webhook_status` from `obs_youtube_uploader/settingsui.py`, and add below its existing `from . import ...` block:

```python
# Re-exported for the dialog's own call sites, which still call it by bare
# name. See ui/copy.py.
from .ui.copy import webhook_status  # noqa: F401
```

- [ ] **Step 11: Run tests to verify they pass**

Run: `python -m pytest tests/test_settingsui_copy.py -v`
Expected: PASS

- [ ] **Step 12: Move the tooltip cell help**

Append to `obs_youtube_uploader/ui/copy.py`:

```python
# --- list cell help --------------------------------------------------------

# Keyed by column identifier, then by the exact cell text library.VideoInfo
# renders. Both glyphs were unexplained: the list showed "?" and "↗" with
# nothing anywhere saying what either meant.
#
# Keyed on rendered text rather than on the underlying value so the help
# cannot disagree with what the user is actually looking at -- which also
# means a change to duration_str's glyphs silently orphans these entries.
# tests/test_tooltip.py guards exactly that coupling.
CELL_HELP: dict[str, dict[str, str]] = {
    "duration": {
        "?": "Length could not be read. ffprobe could not open this file, so\n"
             "combat-log upload is unavailable for it.",
        "…": "Measuring length…",
    },
    "link": {
        "↗": "Uploaded to YouTube.\n"
             "Double-click to open it, or right-click to copy the link.",
    },
}
```

Move `tooltip_for_cell` into `ui/copy.py` as well, directly below `CELL_HELP` — the table and its only reader belong together, and `tooltip.py` is deleted in Task 16:

```python
def tooltip_for_cell(column: str, text: str) -> str | None:
    """Help for one list cell, or None if it needs none.

    Keyed on the rendered text rather than on the underlying value so it
    cannot disagree with what the user is actually looking at.
    """
    return CELL_HELP.get(column, {}).get(text)
```

In `obs_youtube_uploader/tooltip.py`, delete both the `_CELL_HELP` literal and its own `tooltip_for_cell`, leaving the widget machinery importing the moved one:

```python
from .ui.copy import tooltip_for_cell  # noqa: F401
```

In `tests/test_tooltip.py`, repoint the import — the file imports `tooltip` directly, and that module does not survive Task 16:

```python
from obs_youtube_uploader import library
from obs_youtube_uploader.ui import copy as copy_mod
```

then replace every `tooltip.tooltip_for_cell` with `copy_mod.tooltip_for_cell`. The assertions are untouched, which is the proof the table moved intact.

- [ ] **Step 13: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS — 476 passed, the same count as before the refactor. A changed count means something was moved rather than re-exported.

- [ ] **Step 14: Verify the Tk entry point still imports**

Run: `python -c "from obs_youtube_uploader import app, settingsui, tooltip; print(app.format_upload_confirm, settingsui.webhook_status, tooltip.tooltip_for_cell)"`
Expected: PASS — three bound functions printed, no ImportError and no circular-import error

- [ ] **Step 15: Commit**

```bash
git add obs_youtube_uploader/ui/copy.py obs_youtube_uploader/app.py \
        obs_youtube_uploader/settingsui.py obs_youtube_uploader/tooltip.py \
        tests/test_app.py tests/test_app_upload_copy.py tests/test_settingsui_copy.py
git commit -m "Collect the pure copy functions into ui/copy.py"
```

---

### Task 3: Row model

**Files:**
- Create: `obs_youtube_uploader/ui/rows.py`
- Test: `tests/test_rows.py`

**Interfaces:**
- Consumes: the `obs_youtube_uploader.ui` package from Task 1; `library.discover`, `library.stat_info`, `library.VideoInfo`
- Produces:
  - `@dataclass(frozen=True) class Row` with fields `id, name, date, size, duration, link, preselected`
  - `class RowSnapshot` with `rebuild(directory, preselect=None) -> list[dict]`, `rows() -> list[dict]`, `resolve(row_id) -> library.VideoInfo | None`, `resolve_many(ids) -> list[library.VideoInfo]`, `set_link(row_id, video_id) -> None`, `set_duration(row_id, duration, definitive) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rows.py
"""The row model that backs every id crossing the bridge.

The Tk window got this property for free: _delete_selected operated on
_chosen(), which could only hold objects from the current discovered list.
The page cannot be trusted with paths in the same way -- not because it is
hostile (it is local, bundled, and loads nothing remote) but because it goes
stale, and a stale page acting on a path whose meaning has changed is a
deletion of the wrong file. Ids resolved against the current snapshot make
that fail cleanly instead.
"""
import dataclasses
import os
from pathlib import Path

import pytest

from obs_youtube_uploader import library
from obs_youtube_uploader.ui import rows as rows_mod


def _touch(directory: Path, name: str, size: int = 1024,
           mtime: float | None = None) -> Path:
    path = directory / name
    path.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _snapshot_over(directory: Path, preselect=None):
    snapshot = rows_mod.RowSnapshot()
    listed = snapshot.rebuild(directory, preselect=preselect)
    return snapshot, listed


# --- identity --------------------------------------------------------------

def test_ids_are_not_paths(tmp_path):
    """The whole reason ids exist. A path crossing the bridge would let a
    stale page name a file the backend never listed."""
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path)
    assert listed[0]["id"] != str(tmp_path / "a.mkv")
    assert "a.mkv" not in listed[0]["id"]
    assert os.sep not in listed[0]["id"]


def test_ids_are_unique_within_a_snapshot(tmp_path):
    for name in ("a.mkv", "b.mkv", "c.mkv"):
        _touch(tmp_path, name)
    _, listed = _snapshot_over(tmp_path)
    ids = [row["id"] for row in listed]
    assert len(set(ids)) == len(ids) == 3


def test_an_id_is_stable_for_the_life_of_its_snapshot(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    row_id = listed[0]["id"]
    snapshot.set_duration(row_id, 90.0, definitive=True)
    snapshot.set_link(row_id, "abc123")
    assert [row["id"] for row in snapshot.rows()] == [row_id]


def test_a_rebuild_mints_new_ids_so_a_stale_page_fails_cleanly(tmp_path):
    """The load-bearing case. After a refresh, an id the page is still
    holding must resolve to nothing -- not to whatever now sits in that
    position, which is how a delete hits the wrong recording."""
    _touch(tmp_path, "a.mkv", mtime=2000)
    snapshot, listed = _snapshot_over(tmp_path)
    stale_id = listed[0]["id"]

    (tmp_path / "a.mkv").unlink()
    _touch(tmp_path, "b.mkv", mtime=2000)
    snapshot.rebuild(tmp_path)

    assert snapshot.resolve(stale_id) is None
    assert snapshot.resolve_many([stale_id]) == []


# --- building --------------------------------------------------------------

def test_rows_are_newest_first_like_discover(tmp_path):
    _touch(tmp_path, "old.mkv", mtime=1000)
    _touch(tmp_path, "new.mkv", mtime=2000)
    _, listed = _snapshot_over(tmp_path)
    assert [row["name"] for row in listed] == ["new.mkv", "old.mkv"]


def test_a_row_carries_the_rendered_strings_not_raw_values(tmp_path):
    """The page does no formatting: date suppression, size units, and the
    duration glyphs are decisions library already owns, and a second
    implementation in JS would drift from it."""
    path = _touch(tmp_path, "a.mkv", size=2048, mtime=1000)
    _, listed = _snapshot_over(tmp_path)
    info = library.stat_info(path)
    assert listed[0]["size"] == info.size_str
    assert listed[0]["date"] == info.date_str
    assert listed[0]["duration"] == "…"  # not probed yet


def test_a_missing_directory_lists_nothing(tmp_path):
    _, listed = _snapshot_over(tmp_path / "gone")
    assert listed == []


def test_a_file_that_vanishes_mid_scan_is_skipped(tmp_path, monkeypatch):
    """discover() already tolerates this race, so the row build must too --
    otherwise one unlucky delete empties the whole list."""
    _touch(tmp_path, "a.mkv")
    _touch(tmp_path, "b.mkv")
    real = library.stat_info

    def flaky(path):
        if path.name == "a.mkv":
            raise OSError("vanished")
        return real(path)

    monkeypatch.setattr(library, "stat_info", flaky)
    _, listed = _snapshot_over(tmp_path)
    assert [row["name"] for row in listed] == ["b.mkv"]


# --- preselection ----------------------------------------------------------

def test_preselect_marks_only_the_named_paths(tmp_path):
    """The watcher's whole point: finish a fight, open the window, hit
    Upload with no clicking."""
    watched = _touch(tmp_path, "new.mkv", mtime=2000)
    _touch(tmp_path, "old.mkv", mtime=1000)
    _, listed = _snapshot_over(tmp_path, preselect={watched})
    marked = {row["name"]: row["preselected"] for row in listed}
    assert marked == {"new.mkv": True, "old.mkv": False}


def test_no_preselection_marks_nothing(tmp_path):
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path)
    assert listed[0]["preselected"] is False


def test_a_preselected_path_that_is_gone_is_simply_absent(tmp_path):
    """The watcher fires on a path that a delete can beat to the refresh."""
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path, preselect={tmp_path / "gone.mkv"})
    assert [row["preselected"] for row in listed] == [False]


# --- resolution ------------------------------------------------------------

def test_resolve_returns_the_backing_video_info(tmp_path):
    path = _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    info = snapshot.resolve(listed[0]["id"])
    assert isinstance(info, library.VideoInfo)
    assert info.path == path


def test_resolve_of_an_unknown_id_returns_none(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, _ = _snapshot_over(tmp_path)
    assert snapshot.resolve("nonsense") is None


def test_resolve_many_drops_ids_it_does_not_know(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    infos = snapshot.resolve_many([listed[0]["id"], "nonsense"])
    assert [info.path.name for info in infos] == ["a.mkv"]


def test_resolve_many_returns_snapshot_order_not_argument_order(tmp_path):
    """Uploads are numbered (n/total) in the order they are handed to
    build_body, so the batch must follow the list the user was looking at
    rather than whatever order the page's selection set iterated in."""
    _touch(tmp_path, "old.mkv", mtime=1000)
    _touch(tmp_path, "new.mkv", mtime=2000)
    snapshot, listed = _snapshot_over(tmp_path)
    ids = [row["id"] for row in listed]
    infos = snapshot.resolve_many(list(reversed(ids)))
    assert [info.path.name for info in infos] == ["new.mkv", "old.mkv"]


def test_resolve_many_of_nothing_is_empty(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, _ = _snapshot_over(tmp_path)
    assert snapshot.resolve_many([]) == []


# --- links -----------------------------------------------------------------

def test_set_link_puts_a_watch_url_on_the_row(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_link(listed[0]["id"], "abc123")
    assert snapshot.rows()[0]["link"] == "https://www.youtube.com/watch?v=abc123"


def test_a_row_starts_with_no_link(tmp_path):
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path)
    assert listed[0]["link"] is None


def test_set_link_on_an_unknown_id_is_ignored(tmp_path):
    """An upload finishing against a row deleted mid-flight."""
    _touch(tmp_path, "a.mkv")
    snapshot, _ = _snapshot_over(tmp_path)
    snapshot.set_link("nonsense", "abc123")
    assert snapshot.rows()[0]["link"] is None


def test_a_link_survives_the_refresh_the_upload_itself_triggers(tmp_path):
    """The watcher fires a refresh the moment an upload finishes. Clearing
    links on rebuild made the glyph appear and vanish a moment later."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_link(listed[0]["id"], "abc123")
    relisted = snapshot.rebuild(tmp_path)
    assert relisted[0]["link"] == "https://www.youtube.com/watch?v=abc123"


def test_a_link_is_dropped_once_its_recording_is_gone(tmp_path):
    """Pruned rather than kept: a path no longer listed cannot be shown or
    opened, so retaining it only grows the map for the life of the process."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_link(listed[0]["id"], "abc123")
    (tmp_path / "a.mkv").unlink()
    snapshot.rebuild(tmp_path)
    _touch(tmp_path, "a.mkv")
    relisted = snapshot.rebuild(tmp_path)
    assert relisted[0]["link"] is None


# --- durations -------------------------------------------------------------

def test_set_duration_renders_the_measured_length(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    assert snapshot.rows()[0]["duration"] == "1:30"


def test_set_duration_updates_the_backing_info_too(tmp_path):
    """format_selection_summary reads duration and probed off the infos, not
    off the rows, so the two must not drift."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    info = snapshot.resolve(listed[0]["id"])
    assert (info.duration, info.probed) == (90.0, True)


def test_an_unreadable_recording_stops_showing_as_pending(tmp_path):
    """"…" and "?" mean opposite things. A finished probe that read nothing
    must move off "measuring", or the summary keeps its partial "+"."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], None, definitive=True)
    assert snapshot.rows()[0]["duration"] == "?"
    assert snapshot.resolve(listed[0]["id"]).probed is True


def test_a_definitive_answer_is_never_replaced_by_a_probe_that_never_ran(tmp_path):
    """The race app._apply_duration guarded: a synchronous probe resolves a
    row, then the background worker's timeout lands for the same row. A
    timeout says nothing about the file and must not overwrite a good
    duration -- which would then be cached and survive restarts."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    snapshot.set_duration(listed[0]["id"], None, definitive=False)
    assert snapshot.rows()[0]["duration"] == "1:30"


def test_a_probe_that_never_ran_can_still_be_superseded(tmp_path):
    """The mirror of the case above. "No ffprobe configured" is not a
    verdict, so a real one landing later must win."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], None, definitive=False)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    assert snapshot.rows()[0]["duration"] == "1:30"


def test_set_duration_on_an_unknown_id_is_ignored(tmp_path):
    """A probe landing for a list that has since been rebuilt."""
    _touch(tmp_path, "a.mkv")
    snapshot, _ = _snapshot_over(tmp_path)
    snapshot.set_duration("nonsense", 90.0, definitive=True)
    assert snapshot.rows()[0]["duration"] == "…"


def test_a_rebuild_forgets_durations_because_the_cache_owns_them(tmp_path):
    """Deliberate: durations.resolve is the cache's job and needs the cache
    dict, which this module has no business holding. The caller re-applies
    hits through set_duration after each rebuild."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    relisted = snapshot.rebuild(tmp_path)
    assert relisted[0]["duration"] == "…"


# --- shape -----------------------------------------------------------------

def test_rows_returns_plain_dicts_for_the_bridge(tmp_path):
    """pywebview serialises what it is handed; a dataclass does not survive
    the trip."""
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path)
    assert isinstance(listed[0], dict)
    assert set(listed[0]) == {"id", "name", "date", "size", "duration",
                              "link", "preselected"}


def test_rebuild_returns_the_same_rows_it_stores(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    assert listed == snapshot.rows()


def test_a_row_cannot_be_mutated_in_place(tmp_path):
    """Rows are replaced, never edited: an in-place edit that misses the
    stored copy shows one thing and resolves to another."""
    row = rows_mod.Row(id="r1", name="a.mkv", date="", size="", duration="",
                       link=None, preselected=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.name = "b.mkv"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rows.py -v`
Expected: FAIL — collection error, `ImportError: cannot import name 'rows' from 'obs_youtube_uploader.ui'`

- [ ] **Step 3: Write the implementation**

```python
# obs_youtube_uploader/ui/rows.py
"""What a recording looks like once it has crossed to the page, and how it
gets resolved back.

The Tk window addressed rows by their filesystem path -- the Treeview iid
was str(info.path) -- and got a safety property for free along the way:
_delete_selected operated on _chosen(), which could only ever hold objects
from the list currently on screen. Handing paths to a web page loses that.
Not because the page is hostile (it is local, bundled in the installer,
loads no remote content, and is exactly as trusted as the Python) but
because it goes stale: a page holding a path it read before a refresh will
happily ask to delete it afterwards, and by then the path may mean a
different recording, or a file the app never listed at all.

So ids are opaque, minted per row, and never reused. An id from a previous
snapshot resolves to None, which turns "act on the wrong file" into "do
nothing" -- the only acceptable outcome for a delete.

This module owns no cache. durations.resolve needs the cache dict, and the
caller has it; rebuild() therefore produces rows with durations unknown and
the caller re-applies cache hits through set_duration.
"""
import dataclasses
from dataclasses import dataclass
from pathlib import Path

from .. import library


@dataclass(frozen=True)
class Row:
    """One list row, as the page sees it.

    Every field is already rendered. Date suppression, size units, and the
    "…"/"?" duration glyphs are decisions library.VideoInfo owns, and a
    second implementation in JS would drift from it -- tooltip's help table
    is keyed on those exact strings, so a drift there orphans the tooltips
    silently.

    Frozen because rows are replaced rather than edited: an in-place update
    that misses the stored copy leaves the page showing one thing while
    resolve() answers with another.
    """
    id: str
    name: str
    date: str
    size: str
    duration: str
    link: str | None
    preselected: bool


class RowSnapshot:
    """The backend's authoritative view of the list the page is showing."""

    def __init__(self) -> None:
        self._rows: list[Row] = []
        self._infos: dict[str, library.VideoInfo] = {}
        # Keyed by path, not by row id, precisely so links outlive a
        # rebuild -- ids do not. refresh() fires the instant an upload
        # finishes, and clearing links there is what made the glyph appear
        # and vanish a moment later.
        self._links: dict[Path, str] = {}
        self._definitive: set[str] = set()
        # Monotonic for the life of the snapshot, never reset by rebuild.
        # Restarting it per rebuild would recycle "r1" onto a different
        # recording, which is the entire failure this design prevents.
        self._minted = 0

    def _mint(self) -> str:
        self._minted += 1
        return f"r{self._minted}"

    def rebuild(self, directory, preselect: set | None = None) -> list[dict]:
        """Rediscover *directory* and mint a fresh row for every recording.

        Paths in *preselect* start checked; that is the watcher's channel
        for "finish a fight, open the window, hit Upload" with no clicking.
        A preselected path that has since been deleted is simply absent
        rather than an error -- the watcher fires on a path a delete can
        beat to the refresh.
        """
        preselect = preselect or set()
        infos: list[library.VideoInfo] = []
        for path in library.discover(Path(directory)):
            try:
                infos.append(library.stat_info(path))
            except OSError:
                # Vanished between discover() and stat. discover() already
                # tolerates this race; letting it out here would turn one
                # unlucky delete into an empty list for the whole folder.
                continue

        live = {info.path for info in infos}
        self._links = {path: url for path, url in self._links.items()
                       if path in live}
        self._infos = {}
        self._definitive = set()
        self._rows = []
        for info in infos:
            row_id = self._mint()
            self._infos[row_id] = info
            self._rows.append(Row(
                id=row_id,
                name=info.path.name,
                date=info.date_str,
                size=info.size_str,
                duration=info.duration_str,
                link=self._links.get(info.path),
                preselected=info.path in preselect,
            ))
        return self.rows()

    def rows(self) -> list[dict]:
        """The rows as plain dicts. pywebview serialises what it is handed,
        and a dataclass does not survive that trip."""
        return [dataclasses.asdict(row) for row in self._rows]

    def resolve(self, row_id: str):
        """The VideoInfo behind *row_id*, or None if this snapshot has never
        heard of it. None is the answer for every stale id, and callers must
        treat it as "do nothing", never as "not found, try harder"."""
        return self._infos.get(row_id)

    def resolve_many(self, ids: list[str]) -> list[library.VideoInfo]:
        """Every known id in *ids*, in snapshot order, unknown ones dropped.

        Snapshot order rather than argument order because uploader.build_body
        numbers a batch "(n/total)" in the order it is handed the files. The
        numbering the user sees in the upload confirmation has to match the
        list they were looking at, not whatever order the page's selection
        set happened to iterate in.
        """
        wanted = set(ids)
        return [self._infos[row.id] for row in self._rows if row.id in wanted]

    def set_link(self, row_id: str, video_id: str) -> None:
        """Record a finished upload against its row. Unknown id: no-op.

        The no-op matters -- an upload can finish against a row that was
        deleted or rebuilt out from under it mid-flight.
        """
        info = self._infos.get(row_id)
        if info is None:
            return
        url = f"https://www.youtube.com/watch?v={video_id}"
        self._links[info.path] = url
        self._replace(row_id, link=url)

    def set_duration(self, row_id: str, duration: float | None,
                     definitive: bool) -> None:
        """Record one probe result. Unknown id: no-op.

        *definitive* is library.probe's verdict flag, and it decides whether
        this answer can be superseded. A probe that never got a verdict --
        no ffprobe configured, launch failure, timeout -- is displayed (the
        row must stop reading "measuring") but stays open to a later real
        answer. A definitive one is final.

        That is the race app._apply_duration guarded, generalised: a
        synchronous probe resolves a row, then the background worker's
        timeout lands for the same row. Letting the timeout win would
        replace a good duration with an unreadable one, and the caller
        would then cache it under a (size, mtime) key that never changes
        again -- pinning that recording to "?" forever and blocking its
        combat-log upload with a message blaming ffprobe.
        """
        info = self._infos.get(row_id)
        if info is None or row_id in self._definitive:
            return
        info.duration = duration
        info.probed = True
        if definitive:
            self._definitive.add(row_id)
        self._replace(row_id, duration=info.duration_str)

    def _replace(self, row_id: str, **changes) -> None:
        for index, row in enumerate(self._rows):
            if row.id == row_id:
                self._rows[index] = dataclasses.replace(row, **changes)
                return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rows.py -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite for regressions**

Run: `python -m pytest -q`
Expected: PASS — `library` is untouched, so nothing else can have moved

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/ui/rows.py tests/test_rows.py
git commit -m "Model list rows behind opaque ids the page cannot forge"
```

---

### Task 4: `Api` skeleton, `_push`, and the dialog protocol

**Files:**
- Create: `obs_youtube_uploader/ui/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `@dataclass class AppState` with `recording_dir: Path`, `settings: dict`, `ffmpeg_bin: str | None`, `ffprobe_bin: str | None`
  - `class Api` — JS-callable methods `dialog_response(request_id: str, ok: bool) -> None`, `minimize() -> None`, `close() -> None`
  - `Api.__init__(self, state, *, id_factory=...)` — **takes no window.** `_window` is assigned after construction by `ui.window.create()`, because `webview.create_window()` needs `js_api` before a window object exists
  - internals `_push(handler: str, payload) -> None`, `_confirm(title: str, body: str) -> bool`, `_alert(kind: str, title: str, body: str) -> None`

- [ ] **Step 1: Write the failing test — construction, `_push`, and the RecursionError guard**

```python
# tests/test_api.py
"""Bridge-level tests for the js_api object.

These run headless with no webview installed: the Api never imports
pywebview, and every test drives it through a fake window that records the
JavaScript it was asked to evaluate. That is the whole reason `_window` is
assigned rather than constructed -- ui.window.create() does it in
production, and a test does it directly.
"""
import json
import threading
from pathlib import Path

import pytest

from obs_youtube_uploader.ui.api import Api, AppState


class FakeWindow:
    """Records evaluate_js calls instead of running them."""

    def __init__(self, fail=False):
        self.evaluated: list[str] = []
        self.minimized = 0
        self.hidden = 0
        self.destroyed = 0
        self._fail = fail

    def evaluate_js(self, script: str):
        if self._fail:
            raise RuntimeError("window is gone")
        self.evaluated.append(script)

    def minimize(self):
        self.minimized += 1

    def hide(self):
        self.hidden += 1

    def destroy(self):
        self.destroyed += 1


def make_state(tmp_path, **overrides):
    settings = {"privacy": "unlisted", "category": "20", "notify_mode": "toast",
                "recording_dir": str(tmp_path), "discord_webhook": "",
                "gamelogs_dir": None, "channel_id": "", "channel_title": ""}
    settings.update(overrides)
    return AppState(recording_dir=Path(tmp_path), settings=settings,
                    ffmpeg_bin="/usr/bin/ffmpeg", ffprobe_bin=None)


def make_api(tmp_path, window=None, **kwargs):
    api = Api(make_state(tmp_path), **kwargs)
    api._window = window if window is not None else FakeWindow()
    return api


def pushes(window: FakeWindow) -> list[tuple[str, object]]:
    """Decode recorded JS back into (handler, payload) pairs."""
    out = []
    for script in window.evaluated:
        handler = script.split("window.", 1)[1].split(" ", 1)[0]
        payload = json.loads(script[script.index("(", script.rindex(handler)) + 1:
                                    script.rindex(")")])
        out.append((handler, payload))
    return out


def test_push_calls_the_named_handler_with_a_json_payload(tmp_path):
    window = FakeWindow()
    api = make_api(tmp_path, window)

    api._push("onStatus", {"text": "Found 3 video(s)", "kind": "FG"})

    assert pushes(window) == [("onStatus", {"text": "Found 3 video(s)", "kind": "FG"})]


def test_push_guards_on_the_handler_existing(tmp_path):
    # A worker can push before the page has finished defining its handlers.
    # Without the guard that is a ReferenceError thrown into a callback
    # nobody is watching, and the message is lost with no diagnostic.
    window = FakeWindow()
    make_api(tmp_path, window)._push("onStatus", {"text": "x", "kind": "FG"})

    assert "window.onStatus &&" in window.evaluated[0]


def test_push_survives_a_dead_window(tmp_path):
    # Workers keep pushing while the user is closing the window. A teardown
    # race must not take down the upload thread.
    make_api(tmp_path, FakeWindow(fail=True))._push("onStatus",
                                                    {"text": "x", "kind": "FG"})


def test_close_hides_rather_than_destroying(tmp_path):
    """REGRESSION GUARD. This is a tray app: the Tk window bound
    WM_DELETE_WINDOW to hide(), and destroying here would return from
    webview.start(), stop the tray, and end the process -- so closing the
    window would silently stop the recording watcher."""
    window = FakeWindow()
    api = make_api(tmp_path, window)

    api.minimize()
    api.close()

    assert (window.minimized, window.hidden) == (1, 1)
    assert window.destroyed == 0, "close() must not destroy; only tray Quit does"


def test_api_exposes_no_public_non_method_attributes(tmp_path):
    """The single most expensive lesson from the spike, as an assertion.

    pywebview builds its JS proxy by walking the public attributes of the
    js_api object. A public attribute holding a webview.Window sends that
    walk into the WinForms native object, where Rectangle.Empty returns
    itself, and it recurses until RecursionError terminates the process --
    observed as a hard crash about eight seconds after launch, with no
    traceback pointing anywhere near the offending attribute.

    Checking dir() rather than __dict__ catches class-level constants and
    properties too, which the walk reaches just as readily.
    """
    api = make_api(tmp_path)

    public = [name for name in dir(api) if not name.startswith("_")]
    assert public, "guard is worthless if the class has no public surface at all"
    non_methods = [name for name in public if not callable(getattr(api, name))]
    assert non_methods == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.ui.api'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py
"""The js_api bridge: everything the page can call, everything Python pushes.

Two rules govern this module, and both are load-bearing.

**Methods only.** pywebview builds its JavaScript proxy by walking the
public attributes of this object. A public attribute holding a
`webview.Window` (or a `pystray.Icon`) sends that walk into the WinForms
native object, where `Rectangle.Empty` returns itself; it recurses until
`RecursionError` kills the process, roughly eight seconds after launch,
with nothing in the traceback naming the attribute responsible. Every
non-method attribute here is therefore underscore-prefixed, and
`test_api.py` asserts it rather than trusting anyone to remember.

**Workers never touch the page directly.** They call `_push`, which is the
successor to `UploaderWindow._ui` -- but semantic where `_ui` marshalled
widget method calls. `evaluate_js` is safe to call from any thread; there
is no UI thread to marshal onto.

`_window` is assigned by ui.window.create() after construction rather than
passed in: create_window() needs js_api before a window object exists.
"""
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Everything the bridge needs that is not the page.

    recording_dir is None until first run completes. Every consumer must
    handle that rather than substituting a default: a fallback to the home
    directory would have list_rows() scan it for recordings.

    `settings` is REPLACED wholesale by save_settings rather than mutated,
    so anything holding the original dict goes stale -- which is why the
    poll loop and the bridge both read it through this object each time.
    """
    recording_dir: Path | None
    settings: dict
    ffmpeg_bin: str | None = None
    ffprobe_bin: str | None = None


class Api:
    """JS-callable methods only. Every other attribute underscore-prefixed."""

    def __init__(self, state: AppState, *, id_factory=lambda: uuid.uuid4().hex):
        self._state = state
        self._window = None          # assigned by ui.window.create()
        # Injectable purely to make ids predictable in a test that needs to
        # assert on one; production never overrides it.
        self._id_factory = id_factory
        self._dialog_lock = threading.Lock()
        # request id -> [Event, answer]. An entry exists only while a worker
        # is parked on it.
        self._dialogs: dict[str, list] = {}

    # ----- page -> Python -------------------------------------------------

    def dialog_response(self, request_id: str, ok: bool) -> None:
        """Release the worker parked on *request_id*.

        An unknown id is ignored rather than raising. The page can answer a
        dialog whose worker has already given up, and a page reload leaves
        the user free to click a button belonging to a previous run of the
        app -- neither is an error, and an exception raised here surfaces
        only as a rejected promise in a page nobody is debugging.
        """
        with self._dialog_lock:
            entry = self._dialogs.get(request_id)
        if entry is None:
            logger.debug("Dialog response for unknown request %s", request_id)
            return
        entry[1] = bool(ok)
        entry[0].set()

    def minimize(self) -> None:
        self._window.minimize()

    def close(self) -> None:
        """HIDE, never destroy. This is a tray application.

        The Tk window bound WM_DELETE_WINDOW to hide() for the same reason:
        the watcher must keep running after the user closes the window, and
        destroying it here would return from webview.start(), stop the tray
        icon, and end the process -- so closing the window would silently
        turn the watcher off.

        Only the tray's Quit destroys, and it calls window.destroy()
        directly rather than coming through this method.
        """
        self._window.hide()

    # ----- Python -> page -------------------------------------------------

    def _push(self, handler: str, payload) -> None:
        """Fire-and-forget one message at the page.

        The `handler &&` guard is not defensive padding: pushes can land
        before app.js has finished defining its handlers (the watcher
        scheduler and the OAuth worker both start early), and an undefined
        call is a ReferenceError raised inside a callback with no console
        attached in a windowed build.

        Failures are swallowed for the same reason `_ui` could not fail:
        this runs on upload and probe workers, and a window destroyed
        mid-upload must cost a status line, not the upload.
        """
        script = (f"window.{handler} && "
                  f"window.{handler}({json.dumps(payload)})")
        try:
            self._window.evaluate_js(script)
        except Exception:
            logger.debug("Push of %s failed", handler, exc_info=True)

    def _alert(self, kind: str, title: str, body: str) -> None:
        """Non-blocking message box: info, error, or warning."""
        self._push("onDialog", {"kind": kind, "title": title, "body": body,
                                "request_id": None})

    def _confirm(self, title: str, body: str) -> bool:
        """Ask the page a yes/no question and block until it answers.

        This blocks the CALLING thread, which must be a worker -- exactly as
        `messagebox.askyesno` blocked the Tk main thread it was called on.
        The difference is which thread pays: calling this from the thread
        that services `pywebview.api.*` would deadlock, because
        `dialog_response` could never be delivered.

        The Event is registered before the push, not after: `evaluate_js`
        can complete and the user can answer before this method resumes.
        """
        request_id = self._id_factory()
        event = threading.Event()
        entry = [event, False]
        with self._dialog_lock:
            self._dialogs[request_id] = entry
        try:
            self._push("onDialog", {"kind": "confirm", "title": title,
                                    "body": body, "request_id": request_id})
            event.wait()
            return bool(entry[1])
        finally:
            with self._dialog_lock:
                self._dialogs.pop(request_id, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/ui/api.py tests/test_api.py
git commit -m "Add the js_api bridge skeleton with _push and the no-public-attributes guard"
```

- [ ] **Step 6: Write the failing test for the dialog protocol**

```python
# tests/test_api.py  (append)

def test_alert_pushes_a_dialog_with_no_request_id(tmp_path):
    window = FakeWindow()
    api = make_api(tmp_path, window)

    api._alert("warning", "Nothing selected", "Select at least one recording.")

    assert pushes(window) == [("onDialog", {
        "kind": "warning",
        "title": "Nothing selected",
        "body": "Select at least one recording.",
        "request_id": None,
    })]


def test_confirm_blocks_the_worker_until_the_page_answers(tmp_path):
    """The one request/response pair in an otherwise fire-and-forget protocol.

    Driven from two threads on purpose: the worker parks in _confirm exactly
    as it used to park in messagebox.askyesno, and the answer arrives on the
    thread servicing pywebview.api.* -- a different thread, which is what
    makes the Event necessary rather than decorative.
    """
    answered = threading.Event()

    class SignallingWindow(FakeWindow):
        def evaluate_js(self, script):
            super().evaluate_js(script)
            answered.set()

    window = SignallingWindow()
    api = make_api(tmp_path, window)
    result = {}

    worker = threading.Thread(
        target=lambda: result.update(ok=api._confirm("Delete 2 files?",
                                                     "This cannot be undone.")))
    worker.start()

    assert answered.wait(5), "confirm never reached the page"
    handler, payload = pushes(window)[0]
    assert handler == "onDialog"
    assert payload["kind"] == "confirm"
    assert payload["request_id"]
    assert worker.is_alive(), "confirm returned without waiting for an answer"

    api.dialog_response(payload["request_id"], True)
    worker.join(5)
    assert not worker.is_alive()
    assert result == {"ok": True}


def test_confirm_returns_false_when_the_page_declines(tmp_path):
    api = make_api(tmp_path, id_factory=lambda: "req-1")
    result = {}

    worker = threading.Thread(
        target=lambda: result.update(ok=api._confirm("Upload 3 videos?", "body")))
    worker.start()
    # id_factory is fixed, so the id is known without racing the push.
    for _ in range(500):
        api.dialog_response("req-1", False)
        worker.join(0.01)
        if not worker.is_alive():
            break
    assert result == {"ok": False}


def test_dialog_response_for_an_unknown_request_is_ignored(tmp_path):
    # A reloaded page can answer a dialog whose worker is long gone.
    make_api(tmp_path).dialog_response("nobody-is-waiting", True)


def test_confirm_forgets_the_request_once_answered(tmp_path):
    api = make_api(tmp_path, id_factory=lambda: "req-2")
    worker = threading.Thread(target=lambda: api._confirm("t", "b"))
    worker.start()
    for _ in range(500):
        api.dialog_response("req-2", True)
        worker.join(0.01)
        if not worker.is_alive():
            break
    # Left in the map, every dialog the app ever shows leaks an Event for the
    # life of the process.
    assert api._dialogs == {}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS — the dialog protocol was implemented in Step 3, and these tests pin the two-thread behaviour it exists for. If `test_confirm_blocks_the_worker_until_the_page_answers` hangs, `_confirm` is registering the Event after the push.

- [ ] **Step 8: Commit**

```bash
git add tests/test_api.py
git commit -m "Cover the confirm/dialog_response round trip across two threads"
```

---

### Task 5: `Scheduler`

**Files:**
- Create: `obs_youtube_uploader/ui/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: a timer factory with `threading.Timer`'s signature — `timer(interval_s, fn) -> object` with `.start()`, `.cancel()`, and a settable `daemon` attribute
- Produces: `class Scheduler` — `__init__(self, interval_s: float, fn, timer=threading.Timer)`, `start() -> None`, `stop() -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler.py
"""The replacement for root.after()'s self-rescheduling poll loop.

Tk's event loop is gone, and pywebview has no equivalent of `after`. The
watcher poll, the deferred-refresh flag, and the probe drain all rode on it.
The guarantee that has to survive the move is the one __main__.poll()
expressed as a try/finally: the loop reschedules itself no matter what the
body did, because a poll_once() error must not permanently and silently
kill the watcher.

Timers are injected so these tests are instant and deterministic -- nothing
here sleeps, and a real threading.Timer would make the always-reschedule
assertions timing-dependent, which is the one property they must not have.
"""
import threading

import pytest

from obs_youtube_uploader.ui.scheduler import Scheduler


class FakeTimer:
    def __init__(self, interval, fn):
        self.interval = interval
        self.fn = fn
        self.cancelled = False
        self.started = False
        self.daemon = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class FakeClock:
    """Hands out FakeTimers and lets a test fire the armed one."""

    def __init__(self):
        self.timers: list[FakeTimer] = []

    def timer(self, interval, fn):
        made = FakeTimer(interval, fn)
        self.timers.append(made)
        return made

    def fire(self):
        armed = self.timers[-1]
        assert not armed.cancelled, "fired a cancelled timer"
        armed.fn()


def test_start_arms_a_timer_without_running_the_body():
    clock = FakeClock()
    calls = []
    Scheduler(3.0, lambda: calls.append(1), timer=clock.timer).start()

    assert calls == []
    assert len(clock.timers) == 1
    assert clock.timers[0].interval == 3.0
    assert clock.timers[0].started


def test_timers_are_daemon_threads():
    # A live non-daemon timer keeps the process alive after webview.start()
    # returns, so the app would sit invisible in Task Manager after Quit.
    clock = FakeClock()
    Scheduler(3.0, lambda: None, timer=clock.timer).start()

    assert clock.timers[0].daemon is True


def test_each_tick_runs_the_body_and_rearms():
    clock = FakeClock()
    calls = []
    Scheduler(3.0, lambda: calls.append(1), timer=clock.timer).start()

    clock.fire()
    clock.fire()

    assert calls == [1, 1]
    assert len(clock.timers) == 3  # initial + one re-arm per tick


def test_a_raising_body_never_stops_the_loop():
    """__main__.poll()'s try/finally, preserved.

    This is the whole reason the class exists rather than a bare recursive
    Timer: an unreachable recording folder raises out of poll_once() every
    single tick, and the loop has to keep going so the watcher recovers by
    itself when the drive comes back.
    """
    clock = FakeClock()
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("network drive vanished")

    Scheduler(3.0, boom, timer=clock.timer).start()
    for _ in range(3):
        clock.fire()

    assert calls == [1, 1, 1]
    assert not clock.timers[-1].cancelled


def test_stop_cancels_the_armed_timer_and_prevents_rearming():
    clock = FakeClock()
    calls = []
    sched = Scheduler(3.0, lambda: calls.append(1), timer=clock.timer)
    sched.start()

    sched.stop()

    assert clock.timers[-1].cancelled
    assert len(clock.timers) == 1
    assert calls == []


def test_stop_from_inside_the_body_does_not_rearm():
    """The probe drain stops itself the tick it sees its sentinel.

    Naive rescheduling in a `finally` re-arms after that stop() and the loop
    outlives the work it was created for -- one leaked timer per refresh.
    """
    clock = FakeClock()
    sched = None
    calls = []

    def body():
        calls.append(1)
        sched.stop()

    sched = Scheduler(0.1, body, timer=clock.timer)
    sched.start()
    clock.fire()

    assert calls == [1]
    assert len(clock.timers) == 1, "re-armed after stop()"


def test_start_is_idempotent():
    # list_rows() can be re-entered by a watcher tick landing on a manual
    # refresh; a second start must not leave two loops running at double rate.
    clock = FakeClock()
    sched = Scheduler(3.0, lambda: None, timer=clock.timer)
    sched.start()
    sched.start()

    assert len(clock.timers) == 1


def test_stop_before_start_is_harmless():
    Scheduler(3.0, lambda: None, timer=FakeClock().timer).stop()


def test_default_timer_is_threading_timer():
    # The injection point exists for tests; production must not have to
    # remember to pass a real timer.
    sched = Scheduler(0.01, lambda: None)
    assert sched._timer_factory is threading.Timer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.ui.scheduler'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/ui/scheduler.py
"""A self-rescheduling timer loop: the successor to root.after().

Tk's event loop was doing more than UI. The watcher poll, the deferred
refresh during an upload, and the probe drain all rode on `root.after`, and
`webview.start()` carries none of it. This is the one mechanism that
replaces all three.

The guarantee carried over verbatim from `__main__.poll()` is its
`finally`: the loop re-arms whatever the body did. A poll tick that raises
looks identical to a quiet tick from the outside, and a loop that stopped
on the first raise would leave the tray icon looking healthy while the
watcher did nothing, forever, over an unreachable recording folder that
recovers on its own two minutes later.
"""
import logging
import threading

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, interval_s: float, fn, timer=threading.Timer) -> None:
        self._interval_s = interval_s
        self._fn = fn
        # Injected in tests so the suite neither sleeps nor depends on
        # timing; production always uses threading.Timer.
        self._timer_factory = timer
        self._lock = threading.Lock()
        self._timer = None
        self._running = False

    def start(self) -> None:
        with self._lock:
            if self._running:
                return  # Idempotent: a second start must not double the rate.
            self._running = True
        self._arm()

    def stop(self) -> None:
        """Stop the loop, including from inside the body it is running.

        `_running` is what makes the second case work: `_arm` consults it,
        so a stop() called from the body cannot be undone by the re-arm
        that follows the body's return.
        """
        with self._lock:
            self._running = False
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def _arm(self) -> None:
        with self._lock:
            if not self._running:
                return
            timer = self._timer_factory(self._interval_s, self._tick)
            # Daemon, so a live timer cannot keep the process alive after
            # webview.start() returns and the tray icon has stopped --
            # otherwise Quit leaves an invisible process behind.
            timer.daemon = True
            self._timer = timer
        # Started outside the lock: threading.Timer.start() spawns a thread,
        # and holding the lock across it would let a tick that fires
        # immediately contend with the arming that produced it.
        timer.start()

    def _tick(self) -> None:
        try:
            self._fn()
        except Exception:
            # Logged rather than propagated: this runs on a timer thread
            # where the traceback would go to stderr, which is nowhere at
            # all in a windowed build.
            logger.warning("Scheduled task failed", exc_info=True)
        finally:
            self._arm()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/ui/scheduler.py tests/test_scheduler.py
git commit -m "Add Scheduler, the always-reschedule replacement for root.after()"
```

---

### Task 6: Rows, durations, and the selection summary

**Files:**
- Modify: `obs_youtube_uploader/ui/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `ui.rows.RowSnapshot` (Task 3); `ui.copy.format_selection_summary` (Task 2); `ui.scheduler.Scheduler` (Task 5); `library.probe`; `durations.load/save/resolve/remember`; `paths.durations_file()`
- Produces:
  - `Api.list_rows(self, preselect: set | None = None) -> None` — rebuilds the snapshot and pushes `onRows`; returns nothing
  - `Api.panel_text(self, ids: list[str], stitch: bool) -> dict` — returns `{"summary": str, "title_hint": str}`; the page calls it on every selection or stitch change so `format_selection_summary` and `format_title_hint` stay the single tested implementations
  - `Api.__init__` gains `rows=None, durations_file=None, drain_interval_s=PROBE_DRAIN_S, spawn=threading.Thread, probe=library.probe, timer=threading.Timer`
  - Messages `onRows` (`{rows: [...]}`) and `onDuration` (`{id, duration, definitive}`)

> **Reconciliation note.** `onDuration` and `onLink` use the key `id`, never
> `row_id`. The page's handlers key off `id` because that is the field name on
> the row objects `onRows` delivers, and a mismatch here fails silently — Python
> pushes a key the page never reads, and the duration simply never appears.

- [ ] **Step 1: Write the failing test — rows out, durations streaming back, summary computed in Python**

```python
# tests/test_api.py  (append)
from obs_youtube_uploader import durations
from obs_youtube_uploader.ui.rows import RowSnapshot
from obs_youtube_uploader.ui.scheduler import Scheduler


class InlineThread:
    """Runs the worker synchronously on start().

    The probe worker is a plain daemon thread in production. Running it
    inline is what lets these tests assert on a full drain with no sleeps
    and no join timeouts -- the queue is already loaded by the time
    list_rows() returns.
    """

    def __init__(self, target=None, daemon=False):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture
def recordings(tmp_path):
    folder = tmp_path / "recordings"
    folder.mkdir()
    for name in ("a.mkv", "b.mkv"):
        (folder / name).write_bytes(b"\0" * 2048)
    return folder


def rows_api(recordings, tmp_path, clock, probe, window=None):
    api = Api(make_state(recordings), rows=RowSnapshot(),
              durations_file=tmp_path / "durations.json",
              spawn=InlineThread, probe=probe, timer=clock.timer)
    api._window = window if window is not None else FakeWindow()
    return api


def test_list_rows_pushes_every_row_then_streams_durations(recordings, tmp_path):
    window = FakeWindow()
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True), window=window)

    api.list_rows()

    # Rows go out immediately, drawn from a plain stat. The whole point of
    # the split is that the list appears before any ffprobe has run.
    handler, payload = pushes(window)[0]
    assert handler == "onRows"
    assert {row["name"] for row in payload["rows"]} == {"a.mkv", "b.mkv"}

    clock.fire()  # one drain tick

    streamed = [p for name, p in pushes(window) if name == "onDuration"]
    assert len(streamed) == 2
    assert {p["duration"] for p in streamed} == {12.5}
    assert all(p["definitive"] for p in streamed)
    # KEY IS `id`, matching the row objects onRows delivered.
    assert {p["id"] for p in streamed} == {r["id"] for r in payload["rows"]}


def test_preselect_marks_the_named_paths(recordings, tmp_path):
    """The watcher's channel: finish a fight, open the window, hit Upload."""
    window = FakeWindow()
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True), window=window)

    api.list_rows(preselect={recordings / "a.mkv"})

    _handler, payload = pushes(window)[0]
    marked = {row["name"]: row["preselected"] for row in payload["rows"]}
    assert marked == {"a.mkv": True, "b.mkv": False}


def test_the_panel_text_is_computed_in_python(recordings, tmp_path):
    """One tested implementation of each string, not two.

    Selection lives in the page, so the page asks for these rather than
    reimplementing format_selection_summary and format_title_hint in
    JavaScript. Both carry decisions subtle enough that a second copy would
    drift: the summary's "+" for an outstanding probe, and the title hint's
    disclosure that a batch is numbered.
    """
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()
    ids = [row["id"] for row in api._rows.rows()]

    assert api.panel_text([], False)["summary"] == "Nothing selected"
    assert api.panel_text(ids[:1], False)["summary"].startswith("1 selected")


def test_the_title_hint_discloses_batch_numbering_only_when_it_applies(
        recordings, tmp_path):
    """Stitching produces ONE video, so the "(1/n)" warning would be a lie."""
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()
    ids = [row["id"] for row in api._rows.rows()]

    assert api.panel_text(ids, False)["title_hint"] != "Title"
    assert api.panel_text(ids, True)["title_hint"] == "Title"
    assert api.panel_text(ids[:1], False)["title_hint"] == "Title"


def test_the_summary_ignores_ids_the_snapshot_does_not_know(recordings, tmp_path):
    """A stale page after a refresh must not make the summary lie."""
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()
    assert api.panel_text(["nonsense"], False)["summary"] == "Nothing selected"


def test_measured_durations_are_persisted_and_reused(recordings, tmp_path):
    cache_file = tmp_path / "durations.json"
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()
    clock.fire()

    assert set(durations.load(cache_file)) == {
        str(recordings / "a.mkv"), str(recordings / "b.mkv")}

    # Second Api, same cache file: nothing left to probe, so no worker and
    # no drain loop at all.
    window2 = FakeWindow()
    clock2 = FakeClock()

    def explode(path, binary):
        raise AssertionError("probed a file already in the cache")

    rows_api(recordings, tmp_path, clock2, probe=explode,
             window=window2).list_rows()

    assert [name for name, _ in pushes(window2)] == ["onRows"]
    assert clock2.timers == []


def test_an_indefinite_probe_result_is_not_cached(recordings, tmp_path):
    """library.probe's second return value, honoured end to end.

    (None, False) means ffprobe never got a verdict -- no binary, launch
    failure, timeout. The cache key is (size, mtime) and never changes
    again for a finished recording, so remembering that answer would pin
    the row to "?" forever and permanently block its combat-log upload.
    """
    clock = FakeClock()
    window = FakeWindow()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (None, False), window=window)
    api.list_rows()
    clock.fire()

    assert durations.load(tmp_path / "durations.json") == {}
    streamed = [p for name, p in pushes(window) if name == "onDuration"]
    assert [p["definitive"] for p in streamed] == [False, False]


def test_the_drain_loop_stops_once_the_worker_is_done(recordings, tmp_path):
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()

    clock.fire()

    # The worker's sentinel arrived in that same tick; leaving the loop
    # armed would burn a timer every 100ms for the life of the process.
    assert clock.timers[-1].cancelled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v -k "list_rows or summary or durations or probe_result or drain_loop or preselect"`
Expected: FAIL with `TypeError: Api.__init__() got an unexpected keyword argument 'rows'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py
# Extend the imports:
import queue

from .. import durations, library, paths
from . import copy as copy_mod
from .rows import RowSnapshot
from .scheduler import Scheduler

# 100ms, carried over from app.PROBE_DRAIN_MS: fast enough that durations
# appear to fill in live, slow enough that a folder of a hundred recordings
# is batched into a handful of drains rather than a hundred saves.
PROBE_DRAIN_S = 0.1

# Long enough for WebView2 to load the page and run app.js, short enough
# that a first-run user does not stare at an empty window wondering. The
# push is idempotent from the page's side, so an early one costs nothing
# beyond a logged drop.
FIRST_RUN_PUSH_S = 1.5


# Replace Api.__init__ ENTIRELY with this. The first four assignments are
# unchanged from Task 4; everything below _dialogs is new.

    def __init__(self, state: AppState, *,
                 id_factory=lambda: uuid.uuid4().hex,
                 rows=None, durations_file=None,
                 drain_interval_s=PROBE_DRAIN_S,
                 spawn=threading.Thread, probe=library.probe,
                 timer=threading.Timer):
        self._state = state
        self._window = None          # assigned by ui.window.create()
        self._id_factory = id_factory
        self._dialog_lock = threading.Lock()
        self._dialogs: dict[str, list] = {}

        self._rows = rows if rows is not None else RowSnapshot()
        self._durations_file = durations_file or paths.durations_file()
        self._cache = durations.load(self._durations_file)
        self._drain_interval_s = drain_interval_s
        self._spawn = spawn
        self._probe = probe
        self._timer = timer
        self._probe_queue: queue.Queue = queue.Queue()
        # Every list_rows() bumps this. A probe result carrying a stale
        # generation refers to rows that have since been replaced, and is
        # dropped rather than written into the current list.
        self._generation = 0
        self._drain: Scheduler | None = None


# --- inside class Api ------------------------------------------------------

    def list_rows(self, preselect: set | None = None) -> None:
        """Rebuild the list and push it, then fill durations in behind it.

        Successor to UploaderWindow.refresh(). Rows are drawn from a plain
        stat and pushed immediately; durations come from the cache where
        they can and a background probe where they cannot. The version this
        replaces once ran one synchronous ffprobe per file before the window
        appeared, which froze the app for seconds on every launch, tray
        open, settings save, and delete.

        *preselect* is a set of Path, not of strings -- it comes straight
        from the watcher's poll result.

        Returns without pushing when no recording folder is configured yet.
        That is first run, and the page is showing its own route for it; a
        push of an empty list here would replace that screen with an empty
        uploader and no explanation.
        """
        if self._state.recording_dir is None:
            return
        self._generation += 1
        generation = self._generation
        self._stop_drain()

        rebuilt = self._rows.rebuild(self._state.recording_dir, preselect=preselect)
        ids = [row["id"] for row in rebuilt]
        infos = self._rows.resolve_many(ids)
        pending = durations.resolve(self._cache, infos)
        # After the resolve, not after the rebuild: resolve() fills cache
        # hits into the very VideoInfo objects the snapshot renders from, so
        # rows() now reports them and the page never flashes "…" on a
        # duration that was already known.
        self._push("onRows", {"rows": self._rows.rows()})

        # Identity, not equality: VideoInfo is a plain dataclass, so two
        # recordings with the same size and mtime compare equal and an `in`
        # test over the pending list would probe the wrong row.
        outstanding = {id(info) for info in pending}
        work = [(row_id, info) for row_id, info in zip(ids, infos)
                if id(info) in outstanding]
        if work:
            self._start_probe(work, generation)

    def panel_text(self, ids: list[str], stitch: bool) -> dict:
        """Both selection-dependent strings, for the page to render.

        Selection and the stitch checkbox are client state and never cross
        the bridge, so the page asks for these strings on every change
        rather than reimplementing them in JavaScript. That keeps one
        tested implementation of each: format_selection_summary, whose two
        asymmetries ("+" when a probe is outstanding, never a partial
        marker on size) are subtle enough that a second copy would drift
        within a release; and format_title_hint, which discloses that
        build_body numbers a batch -- a disclosure added deliberately in
        2.2.0 after users got ten differently-named public videos.

        Returned together because both change on the same events, so one
        round trip serves both.

        Unknown ids are dropped by resolve_many, so a stale page produces a
        smaller honest summary rather than a wrong one.
        """
        infos = self._rows.resolve_many(ids)
        return {
            "summary": copy_mod.format_selection_summary(infos),
            "title_hint": copy_mod.format_title_hint(len(infos), bool(stitch)),
        }

    # ----- durations ------------------------------------------------------

    def _start_probe(self, work, generation: int) -> None:
        """Probe on a worker; apply results from a drain loop.

        The worker touches neither the snapshot nor the page: it pushes onto
        a queue that the drain reads. Pushing `onDuration` straight from the
        worker would be shorter, but it would also make the durations cache
        a structure written from two threads, and it would give up the
        batching that makes the per-tick save affordable.
        """
        def worker() -> None:
            try:
                for row_id, info in work:
                    if generation != self._generation:
                        break  # A newer list_rows owns the list now.
                    if info.probed:
                        continue  # Already resolved on demand.
                    duration, definitive = self._probe(info.path,
                                                       self._state.ffprobe_bin)
                    self._probe_queue.put(
                        (generation, row_id, info, duration, definitive))
            except Exception:
                # probe() swallows its own failures, so reaching here means
                # something unforeseen. Rows left unprobed sit on "…", and in
                # a windowed build stderr goes nowhere, so log it.
                logger.warning("Duration probe worker failed", exc_info=True)
            finally:
                # Always sent, including on early exit, so the drain loop
                # knows to stop rescheduling itself.
                self._probe_queue.put((generation, None, None, None, False))

        self._drain = Scheduler(
            self._drain_interval_s,
            lambda: self._drain_probes(generation),
            timer=self._timer,
        )
        self._spawn(target=worker, daemon=True).start()
        self._drain.start()

    def _drain_probes(self, generation: int) -> None:
        """Apply whatever the probe worker has finished since the last tick."""
        if generation != self._generation:
            self._stop_drain()  # Superseded; the newer list has its own loop.
            return
        done = False
        applied = 0
        while True:
            try:
                gen, row_id, info, duration, definitive = self._probe_queue.get_nowait()
            except queue.Empty:
                break
            if gen != self._generation:
                continue  # Straggler from a superseded refresh.
            if info is None:
                done = True
                continue
            if definitive:
                durations.remember(self._cache, info.path, info.size,
                                   info.mtime, duration)
            self._rows.set_duration(row_id, duration, definitive)
            self._push("onDuration", {"id": row_id, "duration": duration,
                                      "definitive": definitive})
            applied += 1
        # Per tick rather than once at the end: a cold scan of a large folder
        # takes a while, and a user who opens the window from the tray and
        # quits partway through would otherwise lose every duration measured
        # so far and start the whole scan again next launch.
        if applied:
            durations.save(self._durations_file, self._cache)
        if done:
            self._stop_drain()

    def _stop_drain(self) -> None:
        drain, self._drain = self._drain, None
        if drain is not None:
            drain.stop()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py tests/test_scheduler.py tests/test_rows.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/ui/api.py tests/test_api.py
git commit -m "Stream rows and probed durations across the bridge"
```

- [ ] **Step 6: Write the failing test for generation invalidation and per-tick persistence**

```python
# tests/test_api.py  (append)

def test_a_straggler_from_a_superseded_refresh_is_dropped(recordings, tmp_path):
    """The generation counter, which is what makes the async part safe.

    A probe started against the previous list can land after the list has
    been rebuilt -- the watcher fires a refresh on exactly the events that
    also start probes. Its result refers to rows that no longer exist, and
    writing it would put a duration from one recording onto another.
    """
    window = FakeWindow()
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True), window=window)
    api.list_rows()
    clock.fire()
    window.evaluated.clear()

    api.list_rows()  # bumps the generation; the drain above has stopped
    stale_id = api._rows.rows()[0]["id"]
    stale_info = api._rows.resolve(stale_id)
    api._probe_queue.put((0, stale_id, stale_info, 999.0, True))
    api._drain_probes(api._generation)

    assert [p for name, p in pushes(window) if name == "onDuration"] == []
    assert 999.0 not in {e.duration for e in
                         durations.load(tmp_path / "durations.json").values()}


def test_a_drain_for_a_superseded_generation_stops_itself(recordings, tmp_path):
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()
    stale_generation = api._generation
    api._generation += 1  # as a concurrent list_rows would

    api._drain_probes(stale_generation)

    assert clock.timers[-1].cancelled


def test_the_cache_is_written_on_every_tick_that_applied_something(
        recordings, tmp_path, monkeypatch):
    """Persist per drain, not once at the end.

    A cold scan of a large folder runs for a while. Saving only when the
    worker finishes means a user who quits partway through loses every
    duration measured so far -- and pays for the whole scan again on the
    next launch, which is the exact cost this cache exists to avoid.
    """
    from obs_youtube_uploader.ui import api as api_mod

    saves = []
    real_save = api_mod.durations.save
    monkeypatch.setattr(api_mod.durations, "save",
                        lambda path, cache: (saves.append(len(cache)),
                                             real_save(path, cache)))

    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    # Hand-drive the queue so results land across two ticks rather than one.
    api._generation += 1
    generation = api._generation
    api._rows.rebuild(recordings)
    rows = api._rows.rows()

    for row in rows:
        api._probe_queue.put((generation, row["id"], api._rows.resolve(row["id"]),
                              12.5, True))
        api._drain_probes(generation)
    api._drain_probes(generation)  # a tick with nothing waiting

    assert saves == [1, 2], "one save per tick that applied results, none for an empty tick"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 8: Run the full suite**

Run: `pytest tests/ -q`
Expected: PASS — `ui/api.py` imports no webview and no Tkinter, so the new tests run on `ubuntu-latest` with no display and no browser engine.

- [ ] **Step 9: Commit**

```bash
git add tests/test_api.py
git commit -m "Pin generation invalidation and per-tick duration persistence"
```

---

### Task 7: Upload flow through the bridge

**Files:**
- Create: `tests/fakes.py`
- Create: `tests/test_api_upload.py`
- Modify: `obs_youtube_uploader/ui/api.py`

**Interfaces:**
- Consumes: `RowSnapshot.resolve/resolve_many/set_link` (Task 3); `copy.format_upload_confirm`, `copy.format_progress` (Task 2); `Api._push/_confirm/_alert/list_rows` (Tasks 4, 6); `uploader.upload(request, *, on_progress, on_retry, on_response)`, `uploader.channel_of`, `uploader.build_body`, `uploader.UploadFailed`, `uploader.Outcome`
- Produces:
  - `Api.start_upload(title, description, privacy, category, stitch, ids) -> None`, `Api.retry() -> None`
  - `UploadJob` and `RetryState` dataclasses, `_close_media(media) -> None`, `YOUTUBE_WATCH`
  - private: `_busy()`, `_confirm_then_upload(job)`, `_upload_worker(job)`, `_upload_one(...)`, `_retry_worker(state)`, `_remember_channel(response)`, `_link(row_id, video_id)`; attributes `_upload_thread`, `_retry_state`, `_links`, `_last_pct`, `_watcher`
  - `tests/fakes.py`: `FakeWindow`, `FakeRows`, `FakeWatcher`, `FakeYouTube`, `Answers`, `Alerts`, `info(...)`, `build_api(...)`, `record_pushes(api)`, `payloads(sent, handler)`, `stub_auth(monkeypatch)`, `install_google(monkeypatch, insert)`

> **Reconciliation note.** `onLink` carries `{id, video_id}` and
> `onRetryAvailable` carries `{available: bool}`, matching the page handlers in
> Tasks 11 and 12. Neither is a bare value and neither uses `row_id`.

- [ ] **Step 1: Write the failing test — the shared fakes and the four gates before anything is published**

```python
# tests/fakes.py
"""Headless doubles for the bridge tests.

The Api reaches the page through exactly one call -- window.evaluate_js --
so a window that records that call is a complete stand-in for WebView2.
That is what lets these tests run on ubuntu-latest with no webview, no
display, and no Tk.
"""
import sys
import types
from pathlib import Path

from obs_youtube_uploader import library, uploader
from obs_youtube_uploader.ui import api as api_mod


class FakeWindow:
    """Records every script the bridge evaluates in the page."""

    def __init__(self):
        self.calls = []
        self.dialogs = []
        self.dialog_result = None

    def evaluate_js(self, script):
        self.calls.append(script)

    def create_file_dialog(self, dialog_type, directory=""):
        self.dialogs.append((dialog_type, directory))
        return self.dialog_result


class FakeRows:
    """ui.rows.RowSnapshot's methods, backed by a dict."""

    def __init__(self, mapping=None):
        self.infos = dict(mapping or {})
        self.links = {}

    def resolve(self, row_id):
        return self.infos.get(row_id)

    def resolve_many(self, ids):
        return [self.infos[i] for i in ids if i in self.infos]

    def set_link(self, row_id, video_id):
        self.links[row_id] = video_id

    def rows(self):
        return [{"id": rid} for rid in self.infos]

    def rebuild(self, directory, preselect=None):
        return self.rows()


class FakeWatcher:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.rebound = []
        self.forgotten = []

    def rebind(self, directory):
        self.rebound.append(Path(directory))
        self.directory = Path(directory)

    def forget(self, path):
        self.forgotten.append(Path(path))


class FakeYouTube:
    """youtube.videos().insert(...) without a network or a discovery doc."""

    def __init__(self):
        self.bodies = []

    def videos(self):
        return self

    def insert(self, part=None, body=None, media_body=None):
        self.bodies.append(body)
        return types.SimpleNamespace(body=body, media=media_body)


class Answers:
    """Stands in for _confirm, which normally blocks on the page."""

    def __init__(self, answer=True):
        self.answer = answer
        self.asked = []

    def __call__(self, title, body):
        self.asked.append((title, body))
        return self.answer


class Alerts:
    """Stands in for _alert."""

    def __init__(self):
        self.raised = []

    def __call__(self, kind, title, body):
        self.raised.append((kind, title, body))

    def titles(self):
        return [t for _, t, _ in self.raised]


def info(path, size=1000, duration=60.0, mtime=1000.0, probed=True):
    return library.VideoInfo(path=Path(path), mtime=mtime, size=size,
                             duration=duration, probed=probed)


def build_api(tmp_path, rows=None, settings=None, watcher=None):
    """Construct an Api the way ui.window.create() does: state in, window after."""
    cfg = {
        "privacy": "unlisted", "category": "20", "notify_mode": "toast",
        "recording_dir": str(tmp_path), "discord_webhook": "",
        "gamelogs_dir": None, "channel_id": "", "channel_title": "",
    }
    cfg.update(settings or {})
    state = api_mod.AppState(recording_dir=Path(tmp_path), settings=cfg,
                             ffmpeg_bin="/usr/bin/ffmpeg", ffprobe_bin=None)
    window = FakeWindow()
    api = api_mod.Api(state, rows=rows if rows is not None else FakeRows())
    api._window = window
    api._watcher = watcher
    return api, window


def record_pushes(api):
    """Record every semantic push AND let the real one run.

    Wrapping rather than replacing keeps the real _push in the path, so a
    payload that cannot be serialised still fails the test, while the
    assertions stay independent of the wire format.
    """
    sent = []
    real = api._push

    def spy(handler, payload):
        sent.append((handler, payload))
        real(handler, payload)

    api._push = spy
    return sent


def payloads(sent, handler):
    return [p for h, p in sent if h == handler]


def stub_auth(monkeypatch):
    """Credentials that are already valid, saved nowhere."""
    creds = types.SimpleNamespace(valid=True)
    monkeypatch.setattr(uploader, "load_credentials", lambda p: creds)
    monkeypatch.setattr(uploader, "needs_reauth", lambda c: False)
    monkeypatch.setattr(uploader, "save_credentials", lambda c, p: None)
    return creds


def install_google(monkeypatch, insert):
    """Fake googleapiclient modules for the worker's function-level imports."""

    class MediaFileUpload:
        def __init__(self, path, chunksize=None, resumable=False):
            self.path = path
            self.closed = False

        def stream(self):
            outer = self

            def close():
                outer.closed = True

            return types.SimpleNamespace(close=close)

    pkg = types.ModuleType("googleapiclient")
    disc = types.ModuleType("googleapiclient.discovery")
    http = types.ModuleType("googleapiclient.http")
    disc.build = lambda *a, **k: insert
    http.MediaFileUpload = MediaFileUpload
    monkeypatch.setitem(sys.modules, "googleapiclient", pkg)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", disc)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http)
    return MediaFileUpload
```

```python
# tests/test_api_upload.py
"""The upload flow across the bridge.

Every one of these ran through Tk's messagebox and widget calls before the
replatform; they are the behaviours that had no test at all because the
only thing asserting them was a widget.
"""
import threading

import pytest

from obs_youtube_uploader import uploader
from tests import fakes


def api_with(tmp_path, ids=("r1", "r2"), **kw):
    rows = fakes.FakeRows({rid: fakes.info(tmp_path / f"{rid}.mkv") for rid in ids})
    api, window = fakes.build_api(tmp_path, rows=rows, **kw)
    api._alert = fakes.Alerts()
    api._confirm = fakes.Answers()
    return api, window, rows


def join(api):
    thread = api._upload_thread
    if thread is not None:
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_uploading_nothing_says_so_rather_than_starting_an_empty_job(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api.start_upload("t", "d", "unlisted", "20", False, [])
    assert api._alert.raised == [
        ("warning", "No Selection", "Select at least one video to upload.")]
    assert api._upload_thread is None


def test_stitching_one_recording_is_refused_with_its_own_message(tmp_path):
    """Distinct from the no-selection warning: the user picked something,
    it just cannot be joined to itself."""
    api, _window, _rows = api_with(tmp_path)
    api.start_upload("t", "d", "unlisted", "20", True, ["r1"])
    assert api._alert.raised == [
        ("warning", "Stitch", "Select at least two videos to stitch.")]


def test_a_second_upload_is_refused_while_one_is_running(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    gate = threading.Event()
    api._upload_thread = threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        api.start_upload("t", "d", "unlisted", "20", False, ["r1"])
        assert api._alert.raised == [
            ("warning", "Busy", "An upload is already in progress.")]
    finally:
        gate.set()
        api._upload_thread.join(timeout=5)


def test_publishing_confirms_first_and_declining_uploads_nothing(monkeypatch, tmp_path):
    """The app's only irreversible action. 2.2.0 added this confirm
    deliberately; the port must not quietly drop it."""
    api, _window, _rows = api_with(tmp_path, settings={"channel_title": "Zoolanders"})
    api._confirm = fakes.Answers(answer=False)
    called = []
    monkeypatch.setattr(uploader, "upload", lambda *a, **k: called.append(a))
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())

    api.start_upload("Fight", "d", "public", "20", False, ["r1", "r2"])
    join(api)

    assert called == []
    (title, body), = api._confirm.asked
    assert title == "Confirm Upload"
    # Built through format_upload_confirm, so the numbering shown is the
    # numbering build_body will send.
    assert "Zoolanders" in body
    assert "public" in body
    assert '"Fight (1/2)"' in body and '"Fight (2/2)"' in body
    assert "cannot be undone" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_upload.py -v`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'start_upload'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py  (extend the imports)
from dataclasses import replace

from .. import settings as settings_mod, stitch, uploader

YOUTUBE_WATCH = "https://www.youtube.com/watch?v={video_id}"


def _close_media(media) -> None:
    """Release the file handle a MediaFileUpload holds, best effort.

    MediaFileUpload closes its descriptor only in `__del__`, so anything
    that needs the file released *now* -- to unlink a stitched temporary,
    or to stop blocking a rename of the user's own recording on Windows --
    has to close it explicitly. Tolerates None and objects without a
    stream so callers can hand it whatever they have.
    """
    stream = getattr(media, "stream", None)
    if stream is None:
        return
    try:
        stream().close()
    except Exception:
        logger.warning("Could not close upload stream", exc_info=True)


@dataclass
class UploadJob:
    """Every value the upload worker needs, captured before dispatch.

    `ids` runs parallel to `items` so a finished upload can be linked back
    to the row the page is showing without the worker re-resolving an id
    against a snapshot that may have been rebuilt underneath it.

    `start_index` lets a retry resume partway through without renumbering
    the "(2/3)" title suffixes: the worker skips earlier indices but still
    computes totals from the full list.
    """
    items: list
    ids: list[str]
    title: str
    description: str
    stitch: bool
    privacy: str
    category: str
    start_index: int = 0


@dataclass
class RetryState:
    """What a manual Retry needs to resume rather than restart."""
    job: UploadJob
    resume_index: int
    request: object | None


# Added to Api.__init__ (all underscore-prefixed: pywebview builds its JS
# proxy by walking public attributes, and a public attribute holding a
# native object sends that walk into a RecursionError that kills the
# process):
#     self._upload_thread: threading.Thread | None = None
#     self._retry_state: RetryState | None = None
#     self._links: dict[str, str] = {}
#     self._last_pct: float = 0.0
#     self._watcher = None


# --- inside class Api ------------------------------------------------------

    def _busy(self) -> bool:
        return self._upload_thread is not None and self._upload_thread.is_alive()

    def start_upload(self, title, description, privacy, category, stitch, ids) -> None:
        # Resolved one id at a time rather than through resolve_many so ids
        # and infos stay index-aligned when the page sends an id the
        # snapshot no longer knows (a stale page after a refresh).
        pairs = [(rid, info) for rid in ids
                 if (info := self._rows.resolve(rid)) is not None]
        if not pairs:
            self._alert("warning", "No Selection",
                        "Select at least one video to upload.")
            return
        if stitch and len(pairs) < 2:
            self._alert("warning", "Stitch",
                        "Select at least two videos to stitch.")
            return
        if self._busy():
            self._alert("warning", "Busy", "An upload is already in progress.")
            return
        job = UploadJob(items=[i for _, i in pairs], ids=[r for r, _ in pairs],
                        title=title, description=description, stitch=bool(stitch),
                        privacy=privacy, category=category)
        self._upload_thread = threading.Thread(
            target=self._confirm_then_upload, args=(job,), daemon=True)
        self._upload_thread.start()

    def _confirm_then_upload(self, job: UploadJob) -> None:
        # The confirm runs on the worker, not in start_upload, because
        # _confirm blocks until the page calls dialog_response -- and
        # start_upload is running on pywebview's bridge thread, which is
        # where that answer has to arrive. Asking there would deadlock the
        # bridge on itself. The busy guard is already set by the time this
        # dialog is up, which is also what we want.
        body = copy_mod.format_upload_confirm(
            job.items, job.title, job.privacy,
            self._state.settings.get("channel_title", ""), job.stitch)
        if not self._confirm("Confirm Upload", body):
            return
        self._upload_worker(job)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_upload.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/fakes.py tests/test_api_upload.py obs_youtube_uploader/ui/api.py
git commit -m "Gate start_upload on selection, stitch count, busy and confirm"
```

- [ ] **Step 6: Write the failing test — the success path pushes progress, links and the channel**

```python
# tests/test_api_upload.py  (append)

def fake_upload_ok(video_id="vid123", channel=("UC1", "Zoolanders"), fractions=(0.5, 1.0)):
    """uploader.upload's contract: drive on_progress, then on_response."""
    def _upload(request, *, on_progress=None, on_retry=None, on_response=None,
                **kw):
        for fraction in fractions:
            if on_progress is not None:
                on_progress(fraction)
        if on_response is not None:
            on_response({"id": video_id,
                         "snippet": {"channelId": channel[0],
                                     "channelTitle": channel[1]}})
        return video_id
    return _upload


def test_a_finished_upload_links_every_row_it_covered(monkeypatch, tmp_path):
    api, window, rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1", "r2"])
    join(api)

    links = fakes.payloads(sent, "onLink")
    # KEY IS `id`: the page's onLink handler looks up the row by that field.
    assert [l["id"] for l in links] == ["r1", "r2"]
    assert rows.links == {"r1": "vid123", "r2": "vid123"}
    # The messages really went through evaluate_js, not just through the spy.
    assert window.calls


def test_progress_text_names_the_file_and_the_bar_tracks_the_batch(monkeypatch, tmp_path):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok(fractions=(0.5,)))

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1", "r2"])
    join(api)

    bars = [p for p in fakes.payloads(sent, "onProgress") if p["text"]]
    assert bars[0] == {"mode": "determinate", "pct": 25.0,
                       "text": "Uploading file 1 of 2… 50.0%", "kind": "FG"}


def test_the_destination_channel_is_learned_and_persisted(monkeypatch, tmp_path):
    """Replaces test_app_last_upload, which drove a real window: the channel
    is the only thing the app ever learns about where uploads land, because
    it holds the youtube.upload scope alone."""
    saved = {}
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())
    monkeypatch.setattr("obs_youtube_uploader.ui.api.settings_mod.save",
                        lambda cfg, path=None: saved.update(cfg))

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1"])
    join(api)

    channel, = fakes.payloads(sent, "onChannel")
    assert channel["channel_id"] == "UC1"
    assert channel["channel_title"] == "Zoolanders"
    # The rendered line rides along, so the page never composes it.
    assert channel["destination"] == "Uploads go to Zoolanders · unlisted"
    assert saved["channel_title"] == "Zoolanders"
    assert api._state.settings["channel_id"] == "UC1"


def test_a_completed_upload_clears_retry_and_says_so(monkeypatch, tmp_path):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1"])
    join(api)

    assert {"text": "Upload complete!", "kind": "SUCCESS"} in fakes.payloads(sent, "onStatus")
    assert fakes.payloads(sent, "onRetryAvailable")[-1] == {"available": False}
    assert api._retry_state is None


def test_stitching_switches_the_bar_to_indeterminate_and_back(monkeypatch, tmp_path):
    """ffmpeg reports no progress this code can read, and a multi-gigabyte
    join is seconds of no other signal to the user."""
    import contextlib

    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    @contextlib.contextmanager
    def fake_stitched(sources, ffmpeg_bin, tmp):
        yield tmp_path / "merged.mkv"

    monkeypatch.setattr("obs_youtube_uploader.ui.api.stitch.stitched", fake_stitched)

    api.start_upload("Fight", "d", "unlisted", "20", True, ["r1", "r2"])
    join(api)

    modes = [p["mode"] for p in fakes.payloads(sent, "onProgress")]
    assert modes[0] == "indeterminate"
    assert "determinate" in modes[1:]
    # One stitched video, but every source row gets the link.
    assert sorted(l["id"] for l in fakes.payloads(sent, "onLink")) == ["r1", "r2"]
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_api_upload.py -v -k "linked or progress or channel or completed or stitching"`
Expected: FAIL with `AttributeError: 'Api' object has no attribute '_upload_worker'`

- [ ] **Step 8: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py  (inside class Api)

    def _link(self, row_id: str, video_id: str) -> None:
        """Record and announce one uploaded row.

        _links is kept here as well as in the snapshot because the
        RowSnapshot contract is write-only for links, and open_path /
        copy_path need to read one back.
        """
        self._links[row_id] = YOUTUBE_WATCH.format(video_id=video_id)
        self._rows.set_link(row_id, video_id)
        self._push("onLink", {"id": row_id, "video_id": video_id})

    def _upload_done(self) -> None:
        self._retry_state = None
        self._push("onStatus", {"text": "Upload complete!", "kind": "SUCCESS"})
        self._push("onProgress", {"mode": "determinate", "pct": 100.0,
                                  "text": "", "kind": "SUCCESS"})
        self._push("onRetryAvailable", {"available": False})

    def _upload_worker(self, job: UploadJob) -> None:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        index = job.start_index
        try:
            creds = uploader.load_credentials(paths.token_file())
            if uploader.needs_reauth(creds):
                creds = uploader.run_oauth_flow()
            elif not creds.valid:
                creds = uploader.refresh_credentials(creds)
            uploader.save_credentials(creds, paths.token_file())
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

            if job.stitch:
                ordered = stitch.order_for_stitch(job.items)
                sources = [i.path for i in ordered]
                # A stream copy runs at disk speed, but a multi-gigabyte
                # join is still seconds of no other signal to the user, and
                # ffmpeg reports no progress this code can read. The bar
                # says "working" rather than inventing a percentage.
                # The neutral kind is set with the text for the same reason
                # on_progress does it: start_upload writes no status before
                # dispatching, so a red error from the previous attempt
                # would otherwise survive into this message.
                self._push("onProgress", {"mode": "indeterminate", "pct": 0.0,
                                          "text": "Stitching with FFmpeg…",
                                          "kind": "FG"})
                with stitch.stitched(sources, self._state.ffmpeg_bin,
                                     paths.tmp_dir()) as merged:
                    self._push("onProgress", {"mode": "determinate", "pct": 0.0,
                                              "text": "", "kind": "FG"})
                    vid = self._upload_one(youtube, MediaFileUpload, merged,
                                           job, 0, 1, close_media=True)
                for row_id in job.ids:
                    self._link(row_id, vid)
            else:
                total = len(job.items)
                for index in range(job.start_index, total):
                    vid = self._upload_one(youtube, MediaFileUpload,
                                           job.items[index].path, job, index, total)
                    self._link(job.ids[index], vid)
            self._upload_done()
        except uploader.UploadFailed as exc:
            # Stitched failures cannot resume: the context manager has
            # already deleted the merged file the session points at, which
            # is the correct trade for never leaking multi-GB temporaries.
            # Retry re-stitches instead.
            # Gated on RETRY as well, not just on the stitch path: only a
            # RETRY outcome enables Retry, so for anything else the
            # retained request is unreachable -- and it keeps the
            # MediaFileUpload, and with it an open handle on the user's own
            # recording, alive until the next failure replaces this state.
            # On Windows that blocks renaming or deleting that file.
            resumable = (exc.request is not None and not job.stitch
                         and exc.outcome is uploader.Outcome.RETRY)
            self._retry_state = RetryState(
                job=job,
                # On the stitch path `index` never advances past
                # job.start_index, so resume_index is not the failing item --
                # but it is never read there either, since `resumable` above
                # forces request=None for stitch failures.
                resume_index=index,
                request=exc.request if resumable else None,
            )
            self._alert("error", "Upload Failed", str(exc))
            self._push("onStatus", {"text": str(exc), "kind": "ERROR"})
            if exc.outcome is uploader.Outcome.RETRY:
                self._push("onRetryAvailable", {"available": True})
        except Exception as exc:
            self._retry_state = None
            # Covers a stitch failure too (StitchError isn't an
            # UploadFailed): if the bar was left indeterminate above, put it
            # back rather than leaving it animating behind the error.
            self._push("onProgress", {"mode": "determinate", "pct": 0.0,
                                      "text": "", "kind": "FG"})
            self._alert("error", "Upload Failed", str(exc))
            self._push("onStatus", {"text": f"Error: {exc}", "kind": "ERROR"})

    def _upload_one(self, youtube, MediaFileUpload, path, job, index, total,
                    close_media: bool = False) -> str:
        body = uploader.build_body(job.title, job.description, job.privacy,
                                   job.category, index, total)
        media = MediaFileUpload(str(path), chunksize=uploader.CHUNK_SIZE,
                                resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body,
                                          media_body=media)

        def on_progress(fraction: float) -> None:
            self._last_pct = ((index + fraction) / total) * 100
            self._push("onProgress", {
                "mode": "determinate", "pct": self._last_pct,
                "text": copy_mod.format_progress(index, total, fraction),
                "kind": "FG"})

        def on_retry(attempt: int, delay: float) -> None:
            # Carries the last percentage rather than zero: the upload has
            # not lost the ground it covered, and a bar snapping backwards
            # while the text says "retrying" reads as a restart.
            self._push("onProgress", {
                "mode": "determinate", "pct": self._last_pct,
                "text": f"Network problem — retrying in {delay:.0f}s "
                        f"(attempt {attempt})",
                "kind": "WARNING"})

        try:
            return uploader.upload(request, on_progress=on_progress,
                                   on_retry=on_retry,
                                   on_response=self._remember_channel)
        finally:
            if close_media:
                # The caller is about to delete `path`, and Windows refuses
                # to unlink a file that still has an open handle. Off for
                # the plain path on purpose: UploadFailed hands the
                # resumable request to Retry, which resumes by reading from
                # this very stream.
                _close_media(media)

    def _remember_channel(self, response) -> None:
        """Learn the destination channel from a successful insert response.

        This is the only channel information the app can get: SCOPES holds
        youtube.upload alone, and channels.list needs a second scope, which
        would sign every existing user out.

        The settings write stays on this worker thread deliberately: it is
        a short plain-file write, and persisting here means the channel
        survives a crash before the next clean exit.

        Silent when the response carries no channel: the video uploaded
        fine, and a warning about a missing display field would be noise
        attached to a success.
        """
        channel_id, channel_title = uploader.channel_of(response)
        if not channel_title:
            return
        if (self._state.settings.get("channel_id") == channel_id
                and self._state.settings.get("channel_title") == channel_title):
            return
        self._state.settings["channel_id"] = channel_id
        self._state.settings["channel_title"] = channel_title
        try:
            settings_mod.save(self._state.settings)
        except OSError:
            # A settings file that cannot be written must not fail an
            # upload that succeeded.
            logger.exception("could not persist the destination channel")
        self._push("onChannel", {
            "channel_id": channel_id,
            "channel_title": channel_title,
            # Rendered here, not in the page: format_destination states the
            # "learned from the first upload" case in words, and that
            # explanation is copy with its own test, not a template.
            "destination": copy_mod.format_destination(
                channel_title, self._state.settings.get("privacy", "")),
        })
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_api_upload.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add tests/test_api_upload.py obs_youtube_uploader/ui/api.py
git commit -m "Port the upload worker onto semantic bridge pushes"
```

- [ ] **Step 11: Write the failing test — retry availability and resumability**

```python
# tests/test_api_upload.py  (append)

def failing_upload(outcome, request=object()):
    def _upload(req, **kw):
        raise uploader.UploadFailed(outcome, request=request)
    return _upload


def test_a_retryable_failure_offers_retry_and_keeps_the_session(monkeypatch, tmp_path):
    session = object()
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.RETRY, session))

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1", "r2"])
    join(api)

    assert fakes.payloads(sent, "onRetryAvailable")[-1] == {"available": True}
    assert api._retry_state.request is session
    assert api._retry_state.resume_index == 0
    assert api._alert.raised[-1][0] == "error"


def test_a_permanent_failure_offers_no_retry_and_drops_the_session(monkeypatch, tmp_path):
    """A non-RETRY outcome cannot be resumed, and holding the request would
    keep an open handle on the user's own recording -- which blocks
    renaming or deleting it on Windows."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.QUOTA, object()))

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1"])
    join(api)

    assert fakes.payloads(sent, "onRetryAvailable") == []
    assert api._retry_state.request is None


def test_a_stitched_failure_cannot_resume_even_when_retryable(monkeypatch, tmp_path):
    """The context manager has already deleted the merged file the resumable
    session points at. Retry re-stitches from scratch instead."""
    import contextlib

    api, _window, _rows = api_with(tmp_path)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.RETRY, object()))

    @contextlib.contextmanager
    def fake_stitched(sources, ffmpeg_bin, tmp):
        yield tmp_path / "merged.mkv"

    monkeypatch.setattr("obs_youtube_uploader.ui.api.stitch.stitched", fake_stitched)

    api.start_upload("Fight", "d", "unlisted", "20", True, ["r1", "r2"])
    join(api)

    assert api._retry_state.request is None
    assert api._retry_state.job.stitch is True


def test_retry_resumes_the_session_then_finishes_the_rest(monkeypatch, tmp_path):
    session = object()
    resumed = []
    api, _window, _rows = api_with(tmp_path)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.RETRY, session))
    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1", "r2"])
    join(api)

    def resume(req, *, on_progress=None, on_retry=None, on_response=None, **kw):
        resumed.append(req)
        if on_progress is not None:
            on_progress(1.0)
        return "vidA" if req is session else "vidB"

    monkeypatch.setattr(uploader, "upload", resume)
    sent = fakes.record_pushes(api)
    api.retry()
    join(api)

    # The FIRST call reuses the stored session -- that is what makes this
    # resume rather than restart -- and the second file follows on.
    assert resumed[0] is session
    assert [l["video_id"] for l in fakes.payloads(sent, "onLink")] == ["vidA", "vidB"]
    assert fakes.payloads(sent, "onRetryAvailable")[0] == {"available": False}
    assert api._retry_state is None


def test_retry_with_nothing_to_retry_does_nothing(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    api.retry()
    assert sent == []
    assert api._upload_thread is None
```

- [ ] **Step 12: Run test to verify it fails**

Run: `pytest tests/test_api_upload.py -v -k "retry or resume"`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'retry'`

- [ ] **Step 13: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py  (inside class Api)

    def retry(self) -> None:
        state = self._retry_state
        if state is None:
            return
        # Disabled immediately, not by the worker: the click that got here
        # must not be repeatable while the resume is being set up.
        self._push("onRetryAvailable", {"available": False})
        self._upload_thread = threading.Thread(
            target=self._retry_worker, args=(state,), daemon=True)
        self._upload_thread.start()

    def _retry_worker(self, state: RetryState) -> None:
        """Resume the interrupted upload, then finish the rest of the job."""
        if state.request is None:
            # Stitched, or no session to resume: redo the whole job. No
            # second confirm -- the user already approved this exact job,
            # and Retry is an explicit request to run it again.
            self._upload_worker(replace(state.job, start_index=0))
            return
        try:
            total = len(state.job.items)

            def on_progress(fraction: float) -> None:
                self._last_pct = ((state.resume_index + fraction) / total) * 100
                self._push("onProgress", {
                    "mode": "determinate", "pct": self._last_pct,
                    "text": copy_mod.format_progress(state.resume_index, total,
                                                     fraction),
                    "kind": "FG"})

            vid = uploader.upload(state.request, on_progress=on_progress)
            self._link(state.job.ids[state.resume_index], vid)
        except uploader.UploadFailed as exc:
            # Same gate as _upload_worker, for the same two reasons: only a
            # RETRY outcome re-enables Retry, so keeping the request for any
            # other outcome retains something unreachable -- and that
            # something owns an open handle on the user's own recording,
            # which blocks renaming or deleting it on Windows. Dropping the
            # reference is not enough on its own: closing is left to
            # MediaFileUpload.__del__, whose timing is exactly what made the
            # stitched temp file survive in the first place.
            retryable = exc.outcome is uploader.Outcome.RETRY
            if not retryable:
                _close_media(getattr(exc.request, "resumable", None))
            self._retry_state = replace(
                state, request=exc.request if retryable else None)
            self._push("onStatus", {"text": str(exc), "kind": "ERROR"})
            if retryable:
                self._push("onRetryAvailable", {"available": True})
            return
        # The resumed file is done; continue with whatever followed it.
        if state.resume_index + 1 < len(state.job.items):
            self._upload_worker(replace(state.job,
                                        start_index=state.resume_index + 1))
        else:
            self._upload_done()
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `pytest tests/test_api_upload.py -v`
Expected: PASS

- [ ] **Step 15: Commit**

```bash
git add tests/test_api_upload.py obs_youtube_uploader/ui/api.py
git commit -m "Port manual Retry and its resumability rules onto the bridge"
```

---

### Task 8: Combat logs, delete, open and copy

**Files:**
- Create: `tests/test_api_files.py`
- Modify: `obs_youtube_uploader/ui/api.py`

**Interfaces:**
- Consumes: Task 7's `_busy()`, `_links`, `_push`, `_alert`, `_confirm`, `_upload_thread`; `RowSnapshot.resolve/resolve_many`; `Api.list_rows()`; `library.delete`, `library.probe`; `combatlog.select_logs/build_archive/summarize_archive/dropped_note/find_gamelogs_dir`; `discord.parse_webhook/post_archive`; `tests/fakes.py`
- Produces: `Api.upload_combat_logs(ids) -> None`, `Api.delete_selected(ids) -> None`, `Api.open_path(row_id) -> None`, `Api.copy_path(row_id) -> str`; private `_delete_worker(pairs)`, `_combat_log_worker(...)`, `_probe_now(pairs)`; `Api._watcher` (the live `watcher.Watcher`, or None), set by the entry point — used here for `forget`, and by Task 9 for `rebind`

- [ ] **Step 1: Write the failing test — delete confirms with the file list and forgets only what actually went**

```python
# tests/test_api_files.py
"""Deleting, opening, copying, and combat-log upload across the bridge.

These went through Tk messageboxes and the clipboard before the
replatform. The confirmations and the partial-failure handling are the
parts with real consequences on disk.
"""
import datetime

import pytest

from obs_youtube_uploader import combatlog, discord, library
from obs_youtube_uploader.ui import api as api_mod
from tests import fakes


def api_with(tmp_path, names=("a.mkv", "b.mkv"), watcher=None, **kw):
    rows = {}
    for index, name in enumerate(names):
        path = tmp_path / name
        path.write_bytes(b"\0" * 1024)
        rows[f"r{index}"] = fakes.info(path, size=1024, mtime=1_700_000_000.0)
    api, window = fakes.build_api(tmp_path, rows=fakes.FakeRows(rows),
                                  watcher=watcher, **kw)
    api._alert = fakes.Alerts()
    api._confirm = fakes.Answers()
    api.list_rows = lambda preselect=None: None  # Task 6's refresh; not under test here.
    return api, window, rows


def join_delete(api):
    api._delete_thread.join(timeout=5)


def test_deleting_nothing_says_so(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api.delete_selected([])
    assert api._alert.raised == [
        ("warning", "No Selection", "Select at least one video to delete.")]


def test_delete_confirms_by_naming_every_file_and_saying_it_is_final(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api._confirm = fakes.Answers(answer=False)
    api.delete_selected(["r0", "r1"])
    join_delete(api)

    (title, body), = api._confirm.asked
    assert title == "Confirm Delete"
    assert "a.mkv" in body and "b.mkv" in body
    assert "cannot be undone" in body
    assert (tmp_path / "a.mkv").exists()


def test_declining_the_delete_leaves_the_files_alone(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api._confirm = fakes.Answers(answer=False)
    api.delete_selected(["r0"])
    join_delete(api)
    assert (tmp_path / "a.mkv").exists()


def test_only_files_that_actually_went_are_forgotten_by_the_watcher(monkeypatch, tmp_path):
    """A file that failed to delete still exists, and dropping its
    seen-entry would make the watcher announce it again as if it were new."""
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, rows = api_with(tmp_path, watcher=watcher)
    sent = fakes.record_pushes(api)
    kept = rows["r1"].path

    def half_fails(items):
        items[0].unlink()
        return 1, [(kept, "Permission denied")]

    monkeypatch.setattr(api_mod.library, "delete", half_fails)

    api.delete_selected(["r0", "r1"])
    join_delete(api)

    assert watcher.forgotten == [rows["r0"].path]
    assert fakes.payloads(sent, "onStatus")[-1] == {
        "text": "Deleted 1 file(s). 1 failed.", "kind": "FG"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_files.py -v`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'delete_selected'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py  (extend the imports)
from .. import combatlog, discord, library

# Added to Api.__init__:
#     self._delete_thread: threading.Thread | None = None


# --- inside class Api ------------------------------------------------------

    def delete_selected(self, ids) -> None:
        pairs = [(rid, info) for rid in ids
                 if (info := self._rows.resolve(rid)) is not None]
        if not pairs:
            self._alert("warning", "No Selection",
                        "Select at least one video to delete.")
            return
        # Same reason as _confirm_then_upload: _confirm blocks until the
        # page answers, and the page's answer arrives on the bridge thread
        # this method is running on.
        self._delete_thread = threading.Thread(
            target=self._delete_worker, args=(pairs,), daemon=True)
        self._delete_thread.start()

    def _delete_worker(self, pairs) -> None:
        infos = [info for _, info in pairs]
        names = "\n".join(f"  • {i.path.name}" for i in infos)
        if not self._confirm(
                "Confirm Delete",
                f"Permanently delete these files from disk?\n\n{names}"
                "\n\nThis cannot be undone."):
            return
        deleted, failures = library.delete([i.path for i in infos])
        # Forget only what actually went. A file that failed to delete still
        # exists, and dropping its seen-entry would make the watcher
        # announce it again as if it were new.
        failed_paths = {p for p, _ in failures}
        if self._watcher is not None:
            for info in infos:
                if info.path not in failed_paths:
                    self._watcher.forget(info.path)
        for row_id, _ in pairs:
            self._links.pop(row_id, None)
        self.list_rows()
        message = f"Deleted {deleted} file(s)."
        if failures:
            message += f" {len(failures)} failed."
        self._push("onStatus", {"text": message, "kind": "FG"})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_files.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_files.py obs_youtube_uploader/ui/api.py
git commit -m "Port delete, its confirmation and its partial-failure rule"
```

- [ ] **Step 6: Write the failing test — open and copy target the uploaded video**

```python
# tests/test_api_files.py  (append)

def test_copy_returns_the_link_and_reports_it(tmp_path):
    """The name is historical: what a row offers to copy or open is the
    YouTube link it earned, which is why both are inert before an upload."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    api._links["r0"] = "https://www.youtube.com/watch?v=abc"

    assert api.copy_path("r0") == "https://www.youtube.com/watch?v=abc"
    assert fakes.payloads(sent, "onStatus") == [
        {"text": "Link copied to clipboard", "kind": "SUCCESS"}]


def test_copy_on_a_row_with_no_link_returns_nothing_and_says_nothing(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    assert api.copy_path("r0") == ""
    assert sent == []


def test_open_launches_the_browser_for_a_linked_row(monkeypatch, tmp_path):
    opened = []
    api, _window, _rows = api_with(tmp_path)
    api._links["r0"] = "https://www.youtube.com/watch?v=abc"
    monkeypatch.setattr(api_mod.webbrowser, "open", opened.append)
    api.open_path("r0")
    assert opened == ["https://www.youtube.com/watch?v=abc"]


def test_open_on_an_unknown_row_does_nothing(monkeypatch, tmp_path):
    """A stale page after a refresh must fail cleanly rather than act on an
    id the backend no longer knows."""
    opened = []
    api, _window, _rows = api_with(tmp_path)
    monkeypatch.setattr(api_mod.webbrowser, "open", opened.append)
    api.open_path("gone")
    assert opened == []
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_api_files.py -v -k "copy or open"`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'copy_path'`

- [ ] **Step 8: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py  (extend the imports)
import webbrowser


# --- inside class Api ------------------------------------------------------

    def copy_path(self, row_id: str) -> str:
        """Return the row's link for the page to put on the clipboard.

        The write itself is the page's job: with Tk gone there is no
        toolkit clipboard, and navigator.clipboard is right there. Returning
        it rather than pushing it keeps this a plain request/response, which
        is what a button press is.
        """
        url = self._links.get(row_id, "")
        if not url:
            return ""
        self._push("onStatus", {"text": "Link copied to clipboard",
                                "kind": "SUCCESS"})
        return url

    def open_path(self, row_id: str) -> None:
        url = self._links.get(row_id)
        if url:
            webbrowser.open(url)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_api_files.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add tests/test_api_files.py obs_youtube_uploader/ui/api.py
git commit -m "Port open and copy for an uploaded row onto the bridge"
```

- [ ] **Step 11: Write the failing test — the combat-log guards, each with its own message**

```python
# tests/test_api_files.py  (append)

HOOK = "https://discord.com/api/webhooks/1538615213203656754/tok"


def test_combat_logs_with_nothing_selected_says_which_selection_is_missing(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api.upload_combat_logs([])
    assert api._alert.raised == [
        ("warning", "No Selection",
         "Select at least one recording to upload logs for.")]


def test_combat_logs_share_the_upload_busy_guard(tmp_path):
    """One upload of either kind at a time; this inherits the same warning
    and the same refresh deferral."""
    import threading as _threading
    api, _window, _rows = api_with(tmp_path, settings={"discord_webhook": HOOK})
    gate = _threading.Event()
    api._upload_thread = _threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        api.upload_combat_logs(["r0"])
        assert api._alert.titles() == ["Busy"]
    finally:
        gate.set()
        api._upload_thread.join(timeout=5)


def test_combat_logs_without_a_webhook_name_the_parse_error(tmp_path):
    api, _window, _rows = api_with(tmp_path, settings={"discord_webhook": ""})
    api.upload_combat_logs(["r0"])
    kind, title, body = api._alert.raised[0]
    assert (kind, title) == ("warning", "Discord not configured")
    assert "Add a webhook URL in Settings first." in body


def test_combat_logs_without_a_gamelogs_folder_say_so(monkeypatch, tmp_path):
    api, _window, _rows = api_with(tmp_path, settings={"discord_webhook": HOOK})
    monkeypatch.setattr(api_mod.combatlog, "find_gamelogs_dir", lambda: None)
    api.upload_combat_logs(["r0"])
    assert api._alert.titles() == ["Gamelogs not found"]


def test_a_recording_with_no_readable_duration_blocks_the_window(monkeypatch, tmp_path):
    """No duration means no start time, so there is no window to build --
    refuse rather than invent one that pulls logs from another fight."""
    logs = tmp_path / "logs"
    logs.mkdir()
    api, _window, rows = api_with(tmp_path,
                                  settings={"discord_webhook": HOOK,
                                            "gamelogs_dir": str(logs)})
    rows["r0"].duration = None
    rows["r0"].probed = True
    api.upload_combat_logs(["r0"])
    kind, title, body = api._alert.raised[0]
    assert title == "Cannot determine the time window"
    assert "a.mkv" in body


def test_an_unprobed_recording_is_probed_rather_than_blamed(monkeypatch, tmp_path):
    """The background probe walks the whole folder; a user who beats it to
    this button must not be told ffprobe is broken."""
    logs = tmp_path / "logs"
    logs.mkdir()
    api, _window, rows = api_with(tmp_path,
                                  settings={"discord_webhook": HOOK,
                                            "gamelogs_dir": str(logs)})
    rows["r0"].duration = None
    rows["r0"].probed = False
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(api_mod.library, "probe", lambda path, binary: (30.0, True))
    monkeypatch.setattr(api_mod.combatlog, "select_logs",
                        lambda d, s, e: combatlog.Selection(logs=[], dropped=0))

    api.upload_combat_logs(["r0"])
    api._upload_thread.join(timeout=5)

    # KEY IS `id`, matching every other duration message.
    assert fakes.payloads(sent, "onDuration") == [
        {"id": "r0", "duration": 30.0, "definitive": True}]
    assert api._alert.titles() == ["No logs found"]
```

- [ ] **Step 12: Run test to verify it fails**

Run: `pytest tests/test_api_files.py -v -k combat`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'upload_combat_logs'`

- [ ] **Step 13: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py  (extend the imports)
import datetime


# --- inside class Api ------------------------------------------------------

    def upload_combat_logs(self, ids) -> None:
        pairs = [(rid, info) for rid in ids
                 if (info := self._rows.resolve(rid)) is not None]
        if not pairs:
            self._alert("warning", "No Selection",
                        "Select at least one recording to upload logs for.")
            return
        # Reuses the SAME guard as the YouTube upload: one upload of either
        # kind at a time. This inherits the Busy warning and the scheduler's
        # refresh deferral, both of which key off _upload_thread.
        if self._busy():
            self._alert("warning", "Busy", "An upload is already in progress.")
            return

        cfg = self._state.settings
        hook, error = discord.parse_webhook(cfg.get("discord_webhook"))
        if hook is None:
            self._alert("warning", "Discord not configured",
                        f"{error}\n\nAdd a webhook URL in Settings first.")
            return

        gamelogs = cfg.get("gamelogs_dir")
        gamelogs_dir = Path(gamelogs) if gamelogs else combatlog.find_gamelogs_dir()
        if gamelogs_dir is None or not gamelogs_dir.is_dir():
            self._alert("warning", "Gamelogs not found",
                        "Could not find your EVE Gamelogs folder. "
                        "Set it in Settings.")
            return

        # Resolve any still-pending probe for THIS selection first: an
        # unprobed recording also leaves duration None, and refusing on that
        # would blame ffprobe for a probe that simply had not reached these
        # files yet.
        self._probe_now(pairs)
        missing = [i.path.name for _, i in pairs if i.duration is None]
        if missing:
            self._alert(
                "warning", "Cannot determine the time window",
                "These recordings have no readable duration, so the combat-log "
                "window cannot be worked out:\n\n  "
                + "\n  ".join(missing)
                + "\n\nThis usually means ffprobe is unavailable.")
            return

        # Union across the selection: earliest start to latest end, one
        # archive, matching how stitching treats a multi-selection.
        infos = [i for _, i in pairs]
        start_utc = min(
            datetime.datetime.fromtimestamp(i.mtime - i.duration,
                                            datetime.timezone.utc)
            for i in infos)
        end_utc = max(
            datetime.datetime.fromtimestamp(i.mtime, datetime.timezone.utc)
            for i in infos)

        self._upload_thread = threading.Thread(
            target=self._combat_log_worker,
            args=(hook, gamelogs_dir, start_utc, end_utc), daemon=True)
        self._upload_thread.start()

    def _probe_now(self, pairs) -> None:
        """Resolve a selection's durations synchronously, in place.

        Called from a bridge method that cannot continue without the answer.
        Blocking here is fine and blocking in the Tk version was not: this
        runs on pywebview's bridge thread, so the window keeps painting and
        the progress line below is genuinely live rather than a repaint
        forced between two frozen frames.

        A definitive result is REMEMBERED and the cache saved, exactly as
        _apply_duration did. Setting the in-memory flag alone would stop the
        background walker re-probing this row for the rest of the session
        and then lose the measurement at exit, so the file is re-probed on
        every launch -- precisely the cost the cache exists to avoid.
        """
        unprobed = [(rid, info) for rid, info in pairs if not info.probed]
        if not unprobed:
            return
        total = len(unprobed)
        measured = 0
        for index, (row_id, info) in enumerate(unprobed, start=1):
            self._push("onStatus", {
                "text": f"Reading recording lengths… ({index}/{total})",
                "kind": "FG"})
            duration, definitive = library.probe(info.path, self._state.ffprobe_bin)
            if definitive:
                durations.remember(self._cache, info.path, info.size,
                                   info.mtime, duration)
                measured += 1
            self._rows.set_duration(row_id, duration, definitive)
            self._push("onDuration", {"id": row_id, "duration": duration,
                                      "definitive": definitive})
        if measured:
            durations.save(self._durations_file, self._cache)

    def _combat_log_worker(self, hook, gamelogs_dir, start_utc, end_utc) -> None:
        archive = None
        try:
            self._push("onStatus", {"text": "Collecting combat logs…", "kind": "FG"})
            selection = combatlog.select_logs(gamelogs_dir, start_utc, end_utc)
            if not selection.logs:
                self._alert("info", "No logs found", (
                    "No EVE logs overlap that window.\n\n"
                    f"Window (UTC): {start_utc:%Y-%m-%d %H:%M} to {end_utc:%H:%M}\n"
                    f"Folder: {gamelogs_dir}\n\n"
                    "EVE writes log timestamps in UTC, so this window is in "
                    "UTC too."))
                self._push("onStatus", {"text": "No combat logs found.",
                                        "kind": "FG"})
                return

            stamp = start_utc.strftime("%Y-%m-%d_%H-%M")
            out = paths.tmp_dir() / f"combatlogs-{stamp}.zip"
            self._push("onStatus", {"text": "Building archive…", "kind": "FG"})
            archive = combatlog.build_archive(selection, out, start_utc, end_utc)

            content = combatlog.summarize_archive(archive, start_utc, end_utc)
            self._push("onStatus", {"text": "Posting to Discord…", "kind": "FG"})
            result = discord.post_archive(hook, archive.path, content)

            if result.ok:
                # Only remove the archive once Discord has it.
                try:
                    archive.path.unlink()
                except OSError:
                    pass
                # Discord's own message does not mention the cap; append the
                # same drop note so the status line does not quietly
                # disagree with the content the user just sent.
                status_text = result.message
                note = combatlog.dropped_note(archive.dropped)
                if note:
                    status_text += f" ({note})"
                self._push("onStatus", {"text": status_text, "kind": "SUCCESS"})
            else:
                # Keep the archive: the window is fixed by the recording and
                # there is no UI for selecting fewer logs, so a user told
                # "too large" has no move available unless the file survives.
                self._alert("error", "Combat log upload failed", (
                    f"{result.message}\n\nThe archive was kept so you can "
                    f"upload it by hand:\n{archive.path}"))
                self._push("onStatus", {"text": result.message, "kind": "ERROR"})
        except Exception as exc:
            # post_archive never raises, but build_archive and
            # summarize_archive can -- and by then the archive may already be
            # on disk. Without this the user gets a bare str(exc) and the
            # "kept so you can upload it by hand" promise, which the failed
            # -post branch above makes, quietly does not hold on this path.
            detail = str(exc)
            if archive is not None and archive.path.exists():
                detail += ("\n\nThe archive was kept so you can upload it "
                           f"by hand:\n{archive.path}")
            self._alert("error", "Combat log upload failed", detail)
            self._push("onStatus", {"text": f"Error: {exc}", "kind": "ERROR"})
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `pytest tests/test_api_files.py -v`
Expected: PASS

- [ ] **Step 15: Commit**

```bash
git add tests/test_api_files.py obs_youtube_uploader/ui/api.py
git commit -m "Port combat-log upload and its guards onto the bridge"
```

- [ ] **Step 16: Write the failing test — the combat-log worker's two outcomes**

```python
# tests/test_api_files.py  (append)

def ready_api(tmp_path, monkeypatch, logs):
    api, _window, rows = api_with(tmp_path,
                                  settings={"discord_webhook": HOOK,
                                            "gamelogs_dir": str(logs)})
    for info in rows.values():
        info.duration = 60.0
        info.probed = True
    # Field names are the real ones: SelectedLog is (path, listener,
    # span_start, span_end) -- there is no start=/end=.
    stamp = datetime.datetime(2026, 8, 21, 19, 0, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(api_mod.combatlog, "select_logs",
                        lambda d, s, e: combatlog.Selection(
                            logs=[combatlog.SelectedLog(
                                path=logs / "x.txt", listener="Pilot",
                                span_start=stamp,
                                span_end=stamp + datetime.timedelta(minutes=5))],
                            dropped=2))
    return api, rows


def test_a_posted_archive_is_deleted_and_the_drop_note_is_appended(monkeypatch, tmp_path):
    """The status line must not report a truncated export as a complete one."""
    logs = tmp_path / "logs"
    logs.mkdir()
    archive_path = tmp_path / "combatlogs.zip"
    archive_path.write_bytes(b"zip")
    api, _rows = ready_api(tmp_path, monkeypatch, logs)
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(api_mod.combatlog, "build_archive",
                        lambda sel, out, s, e: combatlog.ArchiveResult(
                            path=archive_path, file_count=1,
                            characters=["Pilot"], raw_bytes=10, zip_bytes=3,
                            dropped=2))
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda h, p, c: discord.PostResult(
                            ok=True, message="Posted combatlogs.zip (0.0 MB)."))

    api.upload_combat_logs(["r0"])
    api._upload_thread.join(timeout=5)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert final["kind"] == "SUCCESS"
    assert "Posted combatlogs.zip" in final["text"]
    assert "2 older logs omitted" in final["text"]
    assert not archive_path.exists()


def test_a_rejected_archive_is_kept_and_its_location_named(monkeypatch, tmp_path):
    """There is no UI for selecting fewer logs, so a user told "too large"
    has no move available unless the file survives."""
    logs = tmp_path / "logs"
    logs.mkdir()
    archive_path = tmp_path / "combatlogs.zip"
    archive_path.write_bytes(b"zip")
    api, _rows = ready_api(tmp_path, monkeypatch, logs)
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(api_mod.combatlog, "build_archive",
                        lambda sel, out, s, e: combatlog.ArchiveResult(
                            path=archive_path, file_count=1,
                            characters=["Pilot"], raw_bytes=10, zip_bytes=3,
                            dropped=0))
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda h, p, c: discord.PostResult(
                            ok=False, message="The archive is too large."))

    api.upload_combat_logs(["r0"])
    api._upload_thread.join(timeout=5)

    assert archive_path.exists()
    kind, title, body = api._alert.raised[-1]
    assert (kind, title) == ("error", "Combat log upload failed")
    assert str(archive_path) in body
    assert fakes.payloads(sent, "onStatus")[-1]["kind"] == "ERROR"


def test_a_failure_after_the_archive_exists_still_names_it(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    archive_path = tmp_path / "combatlogs.zip"
    archive_path.write_bytes(b"zip")
    api, _rows = ready_api(tmp_path, monkeypatch, logs)
    monkeypatch.setattr(api_mod.combatlog, "build_archive",
                        lambda sel, out, s, e: combatlog.ArchiveResult(
                            path=archive_path, file_count=1,
                            characters=["Pilot"], raw_bytes=10, zip_bytes=3,
                            dropped=0))

    def boom(archive, s, e):
        raise RuntimeError("manifest failed")

    monkeypatch.setattr(api_mod.combatlog, "summarize_archive", boom)

    api.upload_combat_logs(["r0"])
    api._upload_thread.join(timeout=5)

    body = api._alert.raised[-1][2]
    assert "manifest failed" in body
    assert str(archive_path) in body
```

- [ ] **Step 17: Run tests to verify they pass**

Run: `pytest tests/test_api_files.py tests/test_api_upload.py -v`
Expected: PASS

- [ ] **Step 18: Commit**

```bash
git add tests/test_api_files.py
git commit -m "Cover the combat-log worker's posted, rejected and crashed paths"
```

---

### Task 9: Settings through the bridge

**Files:**
- Create: `tests/test_api_settings.py`
- Modify: `obs_youtube_uploader/ui/api.py`
- Modify: `obs_youtube_uploader/ui/copy.py`

**Interfaces:**
- Consumes: `copy.webhook_status` (Task 2); `settings.load/save`; `obsconfig.find_recording_dir`; `combatlog.find_gamelogs_dir`; `discord.parse_webhook`; `uploader.run_oauth_flow/save_credentials/load_credentials/needs_reauth`; `Api._watcher` (Task 8)
- Produces:
  - `copy.AUTH_STATES: dict[str, tuple[str, str, bool]]` and `copy.auth_state(state) -> tuple[str, str, bool]` — `(status message, button label, button enabled)`
  - `Api.save_settings(values: dict) -> bool`, `Api.pick_folder(which: str) -> str`, `Api.detect_folder(which: str, current: str = "") -> str`, `Api.connect_google() -> None`, `Api.auth_labels() -> dict`, `Api.refresh_auth() -> None`
  - private: `_folder_dialog_kind()` (module level, lazy `webview` import), `_auth_worker()`, `_auth_check_worker()`, `_push_auth(state)`, `_auth_busy()`; attribute `_auth_thread`
  - `onSettings` payload: `{"settings": dict, "webhook_status": str, "detected": {"recording": str, "gamelogs": str}, "destination": str}` — **`webhook_status` and `destination` are TOP-LEVEL keys, not nested inside `settings`**

> **Reconciliation note.** `auth_labels()` is the single source of the account
> control's strings; Task 13's page reads it rather than hardcoding a second
> copy in JavaScript. `detect_folder` takes the field's live value as `current`,
> so Task 13 must pass it.

- [ ] **Step 1: Write the failing test — the four auth states and their copy**

```python
# tests/test_api_settings.py
"""Settings across the bridge.

The dialog is gone; what survives is the behaviour 2.2.0 put into it -- a
masked webhook that reports parse errors, an account control that tracks
four states, two independent Detect actions, and a Save that reaches the
live watcher and not just the settings file.
"""
import types

import pytest

from obs_youtube_uploader import uploader
from obs_youtube_uploader.ui import api as api_mod
from obs_youtube_uploader.ui import copy as copy_mod
from tests import fakes


def test_connected_offers_to_switch_rather_than_to_connect():
    """The button read "Connect Google Account" while the line above it read
    "Connected", which gave no clue what pressing it would do -- and it is
    exactly the control someone reaches for when they suspect the wrong
    account is signed in."""
    message, label, enabled = copy_mod.auth_state("connected")
    assert (message, label, enabled) == ("Connected", "Switch account", True)


def test_disconnected_asks_for_sign_in():
    assert copy_mod.auth_state("disconnected") == (
        "Not connected", "Sign in with Google", True)


def test_both_transient_states_disable_the_button():
    """A second press during the lookup races it, and during the browser
    flow it starts a second OAuth flow on top of the first."""
    for state in ("connecting", "revoking"):
        _message, _label, enabled = copy_mod.auth_state(state)
        assert enabled is False, state


def test_an_unknown_state_stays_usable():
    """Nothing should be able to leave the user with a dead button."""
    assert copy_mod.auth_state("nonsense") == (
        "Not connected", "Sign in with Google", True)


def test_the_page_can_read_the_whole_label_table_in_one_call(tmp_path):
    """Kept in Python, where it is tested, rather than duplicated in JS."""
    api, _window = fakes.build_api(tmp_path)
    table = api.auth_labels()
    assert table["connected"] == {"message": "Connected",
                                  "label": "Switch account", "enabled": True}
    assert set(table) == {"disconnected", "connecting", "connected", "revoking"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_settings.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.ui.copy' has no attribute 'auth_state'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/ui/copy.py  (append)

# (status message, button label, button enabled) per bridge auth state.
# The two transient states disable the button: a second press during the
# credential lookup races it, and during the browser flow it starts a
# second OAuth flow on top of the first.
AUTH_STATES = {
    "disconnected": ("Not connected", "Sign in with Google", True),
    "connecting": ("Waiting for browser…", "Connecting…", False),
    "connected": ("Connected", "Switch account", True),
    "revoking": ("Signing out…", "Signing out…", False),
}
_AUTH_DEFAULT = AUTH_STATES["disconnected"]


def auth_state(state: str) -> tuple[str, str, bool]:
    """(message, button label, button enabled) for one account state.

    Unknown states, including anything a future revision adds before this
    table learns about it, fall back to an enabled "Sign in with Google":
    an optimistic label on a working button beats a dead one.
    """
    return AUTH_STATES.get(state, _AUTH_DEFAULT)
```

```python
# obs_youtube_uploader/ui/api.py  (inside class Api)

    def auth_labels(self) -> dict:
        """The whole account-state table, for the page to render from.

        Returned rather than pushed because it never changes: the page asks
        once at load and then only needs the `state` each onAuthState
        carries. Keeping the strings here keeps them under test, and stops
        the page growing a second copy that drifts.
        """
        return {state: {"message": message, "label": label, "enabled": enabled}
                for state, (message, label, enabled)
                in copy_mod.AUTH_STATES.items()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_settings.py tests/test_copy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_settings.py obs_youtube_uploader/ui/copy.py obs_youtube_uploader/ui/api.py
git commit -m "Move the account-state copy onto the four bridge auth states"
```

- [ ] **Step 6: Write the failing test — save validates, persists, and rebinds the live watcher**

```python
# tests/test_api_settings.py  (append)

HOOK = "https://discord.com/api/webhooks/1538615213203656754/tok"


def settings_api(tmp_path, monkeypatch, watcher=None, **kw):
    saved = {}
    api, window = fakes.build_api(tmp_path, watcher=watcher, **kw)
    api._alert = fakes.Alerts()
    api.list_rows = lambda preselect=None: None
    monkeypatch.setattr(api_mod.settings_mod, "save",
                        lambda cfg, path=None: saved.update(cfg))
    monkeypatch.setattr(api_mod.settings_mod, "load", lambda path=None: dict(saved))
    return api, window, saved


def values(tmp_path, **kw):
    payload = {"privacy": "public", "category": "20", "notify_mode": "toast",
               "recording_dir": str(tmp_path), "discord_webhook": "",
               "gamelogs_dir": None}
    payload.update(kw)
    return payload


def test_saving_persists_and_reloads_the_canonical_settings(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    sent = fakes.record_pushes(api)

    assert api.save_settings(values(tmp_path)) is True

    assert saved["privacy"] == "public"
    assert api._state.settings["privacy"] == "public"
    pushed, = fakes.payloads(sent, "onSettings")
    assert pushed["settings"]["privacy"] == "public"


def test_saving_a_new_recording_folder_rebinds_the_live_watcher(monkeypatch, tmp_path):
    """Persisting the setting alone leaves the watcher polling the old
    folder, so new recordings in the new one are never noticed."""
    new_dir = tmp_path / "elsewhere"
    new_dir.mkdir()
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    api.save_settings(values(tmp_path, recording_dir=str(new_dir)))

    assert watcher.rebound == [new_dir]
    assert api._state.recording_dir == new_dir


def test_saving_the_same_folder_does_not_rebind(monkeypatch, tmp_path):
    """rebind() re-baselines `seen`; doing it on every Save would be work
    with a chance of announcing existing files as new."""
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)
    api.save_settings(values(tmp_path))
    assert watcher.rebound == []


def test_a_non_numeric_category_is_refused_before_anything_is_written(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.save_settings(values(tmp_path, category="gaming")) is False
    assert saved == {}
    assert api._alert.titles() == ["Invalid category"]


def test_an_invalid_webhook_is_refused_with_the_parse_error(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.save_settings(
        values(tmp_path, discord_webhook="http://discord.com/api/webhooks/1/2")) is False
    assert saved == {}
    kind, title, body = api._alert.raised[0]
    assert title == "Invalid webhook"
    assert "https" in body.lower()


def test_a_recording_folder_that_is_not_a_folder_is_refused(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.save_settings(
        values(tmp_path, recording_dir=str(tmp_path / "nope"))) is False
    assert saved == {}
    assert api._alert.titles() == ["Invalid folder"]


def test_a_settings_file_that_cannot_be_written_leaves_state_untouched(monkeypatch, tmp_path):
    """State and disk must never diverge: bail out before touching memory
    and tell the user, so their edits can be retried."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    def boom(cfg, path=None):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "save", boom)

    assert api.save_settings(values(tmp_path)) is False
    assert api._state.settings["privacy"] == "unlisted"
    assert api._alert.titles() == ["Could not save settings"]


def test_the_pushed_settings_describe_the_webhook_without_its_token(monkeypatch, tmp_path):
    """The field is masked in the page, so this line is the only
    confirmation of WHICH webhook is stored. Top-level key, not nested."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    sent = fakes.record_pushes(api)
    api.save_settings(values(tmp_path, discord_webhook=HOOK))
    pushed, = fakes.payloads(sent, "onSettings")
    assert "1538615213203656754" in pushed["webhook_status"]
    assert "tok" not in pushed["webhook_status"].split("/")[-1]
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_api_settings.py -v -k save`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'save_settings'`

- [ ] **Step 8: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py  (extend the imports)
from .. import obsconfig


# --- inside class Api ------------------------------------------------------

    def _settings_payload(self) -> dict:
        cfg = self._state.settings
        detected_rec = obsconfig.find_recording_dir()
        detected_logs = combatlog.find_gamelogs_dir()
        return {
            "settings": dict(cfg),
            # Top level, not inside `settings`: it is derived, not stored,
            # and nesting it invites the page to write it back on Save.
            "webhook_status": copy_mod.webhook_status(
                cfg.get("discord_webhook", "") or ""),
            "detected": {
                "recording": str(detected_rec) if detected_rec else "",
                "gamelogs": str(detected_logs) if detected_logs else "",
            },
            # Depends only on values Python owns (channel title and
            # privacy), so it is rendered here rather than templated in the
            # page -- format_destination is tested copy.
            "destination": copy_mod.format_destination(
                cfg.get("channel_title", ""), cfg.get("privacy", "")),
        }

    def save_settings(self, values: dict) -> bool:
        """Validate, persist, and make the change reach the running app.

        Returns False when the page should keep the form open with the
        user's edits intact.
        """
        category = str(values.get("category", "")).strip()
        if not category.isdigit():
            self._alert("warning", "Invalid category",
                        "Category ID must be a number, e.g. 20.")
            return False
        webhook_raw = str(values.get("discord_webhook", "") or "").strip()
        if webhook_raw:
            _, webhook_error = discord.parse_webhook(webhook_raw)
            if webhook_error:
                self._alert("warning", "Invalid webhook", webhook_error)
                return False
        rec_dir = Path(str(values.get("recording_dir", "")))
        if not rec_dir.is_dir():
            self._alert("warning", "Invalid folder", f"{rec_dir} is not a folder.")
            return False

        cfg = dict(self._state.settings)
        gamelogs = str(values.get("gamelogs_dir") or "").strip()
        cfg.update({
            "privacy": values.get("privacy"),
            "category": category,
            "notify_mode": values.get("notify_mode"),
            "recording_dir": str(rec_dir),
            "discord_webhook": webhook_raw,
            "gamelogs_dir": gamelogs or None,
        })
        try:
            settings_mod.save(cfg)
        except OSError as exc:
            # Bail out before touching in-memory state so state and disk
            # never diverge, and say so rather than failing silently -- the
            # page keeps the form open with the edits intact.
            self._alert("error", "Could not save settings",
                        f"Settings were not saved: {exc}")
            return False

        self._state.settings = settings_mod.load()
        self._state.recording_dir = rec_dir
        # The watcher is the reason this method is not just a file write.
        # It holds its own directory, so persisting the setting alone would
        # leave it polling the old folder forever. Guarded on a real change
        # because rebind() re-baselines `seen`.
        if self._watcher is not None and rec_dir != Path(self._watcher.directory):
            self._watcher.rebind(rec_dir)
        self._push("onSettings", self._settings_payload())
        self.list_rows()
        return True
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_api_settings.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add tests/test_api_settings.py obs_youtube_uploader/ui/api.py
git commit -m "Save settings through the bridge and rebind the live watcher"
```

- [ ] **Step 11: Write the failing test — Browse and the two independent Detect actions**

```python
# tests/test_api_settings.py  (append)

def test_browse_opens_a_native_folder_dialog_at_the_current_folder(monkeypatch, tmp_path):
    api, window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "FOLDER")
    window.dialog_result = (str(tmp_path / "picked"),)

    assert api.pick_folder("recording") == str(tmp_path / "picked")
    assert window.dialogs == [("FOLDER", str(tmp_path))]


def test_cancelling_the_folder_dialog_returns_nothing(monkeypatch, tmp_path):
    api, window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "FOLDER")
    window.dialog_result = None
    assert api.pick_folder("gamelogs") == ""


def test_detect_re_runs_obs_config_for_the_recording_folder(monkeypatch, tmp_path):
    """The recovery path for a bad stored recording_dir: the stored value
    normally outranks detection, so nothing else ever re-runs the guess."""
    found = tmp_path / "obs"
    found.mkdir()
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.obsconfig, "find_recording_dir", lambda: found)

    assert api.detect_folder("recording", current=str(tmp_path)) == str(found)
    assert api._alert.raised == []


def test_detect_for_gamelogs_is_a_separate_search(monkeypatch, tmp_path):
    found = tmp_path / "Gamelogs"
    found.mkdir()
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.combatlog, "find_gamelogs_dir", lambda: found)

    assert api.detect_folder("gamelogs", current="") == str(found)


def test_detect_says_when_it_cannot_find_the_recording_folder(monkeypatch, tmp_path):
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.obsconfig, "find_recording_dir", lambda: None)

    assert api.detect_folder("recording") == ""
    kind, title, body = api._alert.raised[0]
    assert (kind, title) == ("info", "Detect recording folder")
    assert "OBS" in body


def test_detect_says_when_it_cannot_find_the_gamelogs_folder(monkeypatch, tmp_path):
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.combatlog, "find_gamelogs_dir", lambda: None)

    assert api.detect_folder("gamelogs") == ""
    assert api._alert.titles() == ["Gamelogs not found"]


def test_detect_that_agrees_with_the_field_says_so_rather_than_nothing(monkeypatch, tmp_path):
    """Silently rewriting the field with the value already in it looks like
    a dead button."""
    found = tmp_path / "obs"
    found.mkdir()
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.obsconfig, "find_recording_dir", lambda: found)

    assert api.detect_folder("recording", current=str(found)) == ""
    assert "Already set" in api._alert.raised[0][2]
```

- [ ] **Step 12: Run test to verify it fails**

Run: `pytest tests/test_api_settings.py -v -k "browse or detect or cancelling"`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.ui.api' has no attribute '_folder_dialog_kind'`

- [ ] **Step 13: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py  (module level)

def _folder_dialog_kind():
    """pywebview's folder-dialog constant, imported at call time.

    Kept behind a function for two reasons: webview is not installed on the
    Linux CI box these tests run on, and 6.x renamed this constant once
    already (FOLDER_DIALOG -> FileDialog.FOLDER), so exactly one line has
    to change if it moves again.
    """
    import webview
    return webview.FileDialog.FOLDER


# --- inside class Api ------------------------------------------------------

    def pick_folder(self, which: str) -> str:
        """Native folder picker, seeded with what is configured now."""
        if which == "gamelogs":
            start = str(self._state.settings.get("gamelogs_dir") or "")
        else:
            start = str(self._state.recording_dir)
        chosen = self._window.create_file_dialog(_folder_dialog_kind(),
                                                 directory=start)
        # create_file_dialog returns a sequence of paths, or None on cancel.
        if not chosen:
            return ""
        return str(chosen[0])

    def detect_folder(self, which: str, current: str = "") -> str:
        """Re-run detection for one folder and hand back the suggestion.

        Returned rather than pushed through onSettings, and Save is still
        required: the user sees exactly what changed and can decline it,
        and pushing the whole settings dict would throw away every other
        unsaved edit in the form.

        `current` is the field's live value, not the stored setting, so a
        detection that agrees with what the user has already typed is
        reported as agreement instead of silently rewriting the field.
        """
        if which == "gamelogs":
            found = combatlog.find_gamelogs_dir()
            if found is None:
                self._alert("info", "Gamelogs not found",
                            "Could not find an EVE Gamelogs folder under "
                            "Documents or OneDrive\\Documents. Use Browse… "
                            "to point at it.")
                return ""
            if str(found) == current:
                self._alert("info", "Gamelogs",
                            f"Already set to the detected folder:\n{found}")
                return ""
            return str(found)

        detected = obsconfig.find_recording_dir()
        if detected is None or not detected.is_dir():
            self._alert("info", "Detect recording folder",
                        "Could not read OBS's configuration to detect a "
                        "recording folder. Make sure OBS is installed and has "
                        "recorded at least once, then try again.")
            return ""
        if str(detected) == current:
            self._alert("info", "Detect recording folder",
                        f"Already set to the detected folder:\n{detected}")
            return ""
        return str(detected)
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `pytest tests/test_api_settings.py -v`
Expected: PASS

- [ ] **Step 15: Commit**

```bash
git add tests/test_api_settings.py obs_youtube_uploader/ui/api.py
git commit -m "Port Browse and both Detect actions onto the bridge"
```

- [ ] **Step 16: Write the failing test — OAuth as a worker with no polling loop**

```python
# tests/test_api_settings.py  (append)

def test_connecting_announces_the_transient_state_before_the_browser_opens(monkeypatch, tmp_path):
    """The state, not just the outcome: the page disables the control while
    it is connecting so a second press cannot start a second OAuth flow."""
    api, _window = fakes.build_api(tmp_path)
    api._alert = fakes.Alerts()
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(uploader, "run_oauth_flow",
                        lambda: types.SimpleNamespace(valid=True))
    monkeypatch.setattr(uploader, "save_credentials", lambda c, p: None)

    api.connect_google()
    api._auth_thread.join(timeout=5)

    states = [p["state"] for p in fakes.payloads(sent, "onAuthState")]
    assert states == ["connecting", "connected"]
    assert fakes.payloads(sent, "onAuthState")[0]["message"] == "Waiting for browser…"


def test_a_failed_sign_in_reports_it_and_returns_to_disconnected(monkeypatch, tmp_path):
    api, _window = fakes.build_api(tmp_path)
    api._alert = fakes.Alerts()
    sent = fakes.record_pushes(api)

    def boom():
        raise RuntimeError("the user closed the browser")

    monkeypatch.setattr(uploader, "run_oauth_flow", boom)

    api.connect_google()
    api._auth_thread.join(timeout=5)

    assert [p["state"] for p in fakes.payloads(sent, "onAuthState")] == [
        "connecting", "disconnected"]
    kind, title, body = api._alert.raised[0]
    assert (kind, title) == ("error", "Connection failed")
    assert "browser" in body


def test_a_second_press_while_connecting_is_ignored(monkeypatch, tmp_path):
    """The button is disabled in the page, but the guard lives here too:
    two concurrent OAuth flows would fight over the loopback port."""
    import threading as _threading

    gate = _threading.Event()
    api, _window = fakes.build_api(tmp_path)
    api._alert = fakes.Alerts()
    monkeypatch.setattr(uploader, "run_oauth_flow",
                        lambda: (gate.wait(5), types.SimpleNamespace(valid=True))[1])
    monkeypatch.setattr(uploader, "save_credentials", lambda c, p: None)

    api.connect_google()
    first = api._auth_thread
    api.connect_google()
    assert api._auth_thread is first
    gate.set()
    first.join(timeout=5)


def test_the_startup_check_resolves_the_state_off_the_bridge_thread(monkeypatch, tmp_path):
    """load_credentials drags in google.auth, requests and cryptography;
    off a PyInstaller build's disk that is a visible pause."""
    api, _window = fakes.build_api(tmp_path)
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(uploader, "load_credentials",
                        lambda p: types.SimpleNamespace(valid=True))
    monkeypatch.setattr(uploader, "needs_reauth", lambda c: False)

    api.refresh_auth()
    api._auth_thread.join(timeout=5)

    assert [p["state"] for p in fakes.payloads(sent, "onAuthState")] == [
        "connecting", "connected"]


def test_an_unreadable_token_reads_as_not_connected(monkeypatch, tmp_path):
    """Never leave the control stuck mid-check: an unreadable token is
    indistinguishable from not being connected, and that is exactly what
    the user needs to be told."""
    api, _window = fakes.build_api(tmp_path)
    sent = fakes.record_pushes(api)

    def boom(path):
        raise OSError("token unreadable")

    monkeypatch.setattr(uploader, "load_credentials", boom)

    api.refresh_auth()
    api._auth_thread.join(timeout=5)

    assert fakes.payloads(sent, "onAuthState")[-1]["state"] == "disconnected"
```

- [ ] **Step 17: Run test to verify it fails**

Run: `pytest tests/test_api_settings.py -v -k "connect or sign_in or auth or token"`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'connect_google'`

- [ ] **Step 18: Write minimal implementation**

```python
# obs_youtube_uploader/ui/api.py  (inside class Api)

    # Added to Api.__init__:
    #     self._auth_thread: threading.Thread | None = None

    def _push_first_run_when_ready(self) -> None:
        """Tell the page to show its first-run route, once it can hear it.

        Deferred onto a short timer rather than pushed immediately: this is
        called before webview.start(), so app.js has not registered its
        handlers and _push would log the message and drop it. The page asks
        for state on load, but there is no state to ask for here -- an
        unconfigured folder is exactly the case list_rows() returns silently
        on -- so this is the one thing Python must volunteer.
        """
        timer = self._timer(FIRST_RUN_PUSH_S, lambda: self._push("onFirstRun", {}))
        timer.daemon = True
        timer.start()

    def _push_auth(self, state: str, message: str | None = None) -> None:
        if message is None:
            message = copy_mod.auth_state(state)[0]
        self._push("onAuthState", {"state": state, "message": message})

    def _auth_busy(self) -> bool:
        return self._auth_thread is not None and self._auth_thread.is_alive()

    def refresh_auth(self) -> None:
        """Resolve the stored credentials without blocking the bridge.

        load_credentials lazily imports google.oauth2, which drags in
        google.auth, requests and cryptography. Off a PyInstaller build's
        disk that is a visible pause, so it runs on a worker and the page
        holds the transient state until the answer lands. There is no
        polling loop: the worker pushes the result itself.
        """
        if self._auth_busy():
            return
        self._push_auth("connecting", "Checking…")
        self._auth_thread = threading.Thread(target=self._auth_check_worker,
                                             daemon=True)
        self._auth_thread.start()

    def _auth_check_worker(self) -> None:
        try:
            creds = uploader.load_credentials(paths.token_file())
            connected = creds is not None and not uploader.needs_reauth(creds)
        except Exception:
            # An unreadable token is indistinguishable from not being
            # connected, and leaving the control mid-check forever is the
            # one outcome that helps nobody.
            connected = False
        self._push_auth("connected" if connected else "disconnected")

    def connect_google(self) -> None:
        """Run OAuth off the bridge thread; it blocks on a browser round-trip.

        The guard is here as well as in the page's disabled button: two
        concurrent flows would fight over the loopback redirect port.
        """
        if self._auth_busy():
            return
        self._push_auth("connecting")
        self._auth_thread = threading.Thread(target=self._auth_worker, daemon=True)
        self._auth_thread.start()

    def _auth_worker(self) -> None:
        try:
            creds = uploader.run_oauth_flow()
            uploader.save_credentials(creds, paths.token_file())
        except Exception as exc:
            self._alert("error", "Connection failed", str(exc))
            self._push_auth("disconnected")
            return
        self._push_auth("connected")
```

- [ ] **Step 19: Run tests to verify they pass**

Run: `pytest tests/test_api_settings.py tests/test_api_files.py tests/test_api_upload.py -v`
Expected: PASS

- [ ] **Step 20: Commit**

```bash
git add tests/test_api_settings.py obs_youtube_uploader/ui/api.py
git commit -m "Replace the OAuth polling loop with an onAuthState worker"
```

---

### Task 10: Page shell, design tokens, custom title bar

**Files:**
- Create: `obs_youtube_uploader/web/index.html`
- Create: `obs_youtube_uploader/web/style.css`
- Create: `obs_youtube_uploader/web/app.js`
- Create: `obs_youtube_uploader/web/dev.js`

**Interfaces:**
- Consumes: nothing yet — registers the `window.on*` handler table Tasks 11–13 fill
- Produces: `WM.send(method, ...args)`, `WM.handle(name, fn)`, `WM.el(id)`, `WM.make(tag, cls, text)`, `WM.route(name)`, `WM.HANDLERS`; the containers `#route-main`, `#route-settings`, `#panel-slot`, `#statusbar-slot`, `#dialog-slot`; calls `pywebview.api.minimize()`, `close()`, `list_rows()`

> **Sorting note.** `onRows` carries `date` and `size` as *rendered strings*
> (`library.format_date` / `format_size`), which cannot be ordered as text —
> `format_date`'s own docstring warns a text sort "would silently start sorting
> Aug before Dec". Task 11 therefore sorts on a parsed numeric for size and on
> the row's delivery index for date, which Python already delivers newest-first
> from `library.discover`. This is the one place the contract's rendered strings
> are load-bearing.

- [ ] **Step 1: Create `web/style.css` with the token block, reset, and base type scale**

```css
/* FlyGD Wingman — page styles.
   Direction B, transcribed from the approved spike at wingman-spike/web.
   Tokens are the successor to theme.py's TOKENS dict. Dark only: light
   mode and the AppsUseLightTheme detection are dropped, not ported. */

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  /* ---- colour ---- */
  --bg: #0c0d10;
  --panel: #14161b;
  --panel-border: #1e2128;
  --field: #0a0b0e;
  --field-border: #23262e;
  --text: #e8eaed;
  --text-dim: #9aa2b1;
  --text-faint: #6f7681;
  --brand: #ff5a4d;
  --brand-deep: #c81e12;
  --ok: #4ade80;
  --warn: #d29922;
  --err: #f85149;

  /* ---- type scale ----
     Three steps, adopted from 2.2.0's sv-ttk-derived scale, not reinvented:
     headings 1.2x body, body, muted 0.875x body. COLUMN HEADERS USE
     --fs-muted DELIBERATELY — they sit BELOW body size because they label
     the data and are not the data. Making them larger undoes a considered
     decision. */
  --fs-head: 15.5px;
  --fs-body: 13px;
  --fs-muted: 11.5px;
  --fs-mono: 12px;
  --fs-label: 10.5px;   /* uppercase tracked section labels (direction B) */

  --font: "Inter", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, Consolas, monospace;

  --radius: 8px;
  --radius-sm: 6px;
  --row-h: 30px;
  --titlebar-h: 44px;
}

html, body {
  height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-size: var(--fs-body);
  /* A desktop chrome should not text-select or rubber-band like a web page. */
  user-select: none;
  overflow: hidden;
}

body { display: flex; flex-direction: column; }

h1 { font-size: var(--fs-head); font-weight: 620; }

/* ---- custom title bar (replaces the OS one; window is frameless) ------ */
.titlebar {
  display: flex; align-items: center; gap: 10px;
  height: var(--titlebar-h); padding: 0 6px 0 16px; flex: none;
  background: linear-gradient(180deg, #16181d, #101216);
  border-bottom: 1px solid #000;
  box-shadow: inset 0 1px 0 #24272e;
}
/* pywebview's documented drag handle for frameless windows. Only this
   element drags: the buttons must stay clickable. */
.pywebview-drag-region {
  flex: 1; height: 100%; display: flex; align-items: center; gap: 10px;
}
.mark {
  width: 20px; height: 20px; border-radius: 5px; flex: none;
  background: linear-gradient(150deg, var(--brand), var(--brand-deep));
  display: grid; place-items: center; font-size: 9px; color: #fff;
  box-shadow: 0 0 12px rgba(230, 50, 45, .45);
}
.name { font-weight: 650; letter-spacing: .3px; }
.sub {
  color: var(--text-faint); font-size: var(--fs-muted);
  letter-spacing: .12em; text-transform: uppercase;
}
.winbtn {
  width: 44px; height: 32px; border: 0; background: transparent;
  color: var(--text-faint); font-size: 13px; cursor: pointer;
  border-radius: 5px; font-family: inherit; flex: none;
}
.winbtn:hover { background: #22252c; color: var(--text); }
.winbtn.close:hover { background: #d9291c; color: #fff; }
.winbtn.gear { font-size: 15px; }
.winbtn.gear.active { background: #22252c; color: var(--brand); }

/* ---- routes ----------------------------------------------------------
   Settings is a ROUTE in this window, not a second OS window. */
.route { flex: 1; min-height: 0; display: none; }
.route.active { display: flex; }

/* ---- shared primitives ---------------------------------------------- */
.card {
  background: var(--panel); border: 1px solid var(--panel-border);
  border-radius: var(--radius); padding: 14px 16px;
}
.card > h2 {
  font-size: var(--fs-label); letter-spacing: .14em; text-transform: uppercase;
  color: #8b93a1; margin-bottom: 12px; font-weight: 600;
  display: flex; align-items: center; gap: 9px;
}
/* The short brand rule preceding every section label. */
.card > h2::before {
  content: ""; width: 3px; height: 12px; border-radius: 2px; flex: none;
  background: linear-gradient(180deg, var(--brand), var(--brand-deep));
}

.row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.row:last-child { margin-bottom: 0; }

input.field, textarea.field, select.field, span.field {
  flex: 1; min-width: 0; background: var(--field);
  border: 1px solid var(--field-border); border-radius: var(--radius-sm);
  padding: 7px 10px; font-size: var(--fs-body); color: var(--text);
  font-family: inherit; outline: none; user-select: text;
}
input.field.mono, span.field.mono, textarea.field.mono {
  font-family: var(--mono); font-size: var(--fs-mono);
}
span.field { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
input.field:focus, textarea.field:focus, select.field:focus {
  border-color: #39404d;
  box-shadow: 0 0 0 2px rgba(255, 90, 77, .14);
}
textarea.field { resize: none; line-height: 1.5; }

button.btn {
  background: #1c1f26; border: 1px solid #2a2e37; border-radius: var(--radius-sm);
  padding: 7px 12px; font-size: var(--fs-mono); color: #c8cdd6; flex: none;
  cursor: pointer; font-family: inherit;
}
button.btn:hover:not(:disabled) { background: #242832; color: var(--text); }
button.btn:disabled { opacity: .45; cursor: default; }
/* The ONE brand-accent control on any screen. */
button.btn.acc {
  background: linear-gradient(180deg, var(--brand), #d9291c);
  border-color: #ff7a6f; color: #fff; font-weight: 600;
  box-shadow: 0 2px 14px rgba(230, 50, 45, .35);
}
button.btn.acc:hover:not(:disabled) { filter: brightness(1.08); }
button.btn.acc:disabled { box-shadow: none; filter: grayscale(.5); }

.hint {
  color: var(--text-faint); font-size: var(--fs-muted);
  line-height: 1.5; margin-top: 8px; user-select: text;
}
.linkish { color: #7aa2f7; cursor: pointer; user-select: text; }
.linkish:hover { text-decoration: underline; }

/* ---- scrollbar ------------------------------------------------------
   Tk cannot restyle this at all; the classic Windows scrollbar is one of
   the most visible tells in newest-version.png and disappears here. */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: #262a33; border-radius: 5px; border: 2px solid var(--bg);
}
::-webkit-scrollbar-thumb:hover { background: #333845; }
::-webkit-scrollbar-corner { background: transparent; }
```

- [ ] **Step 2: Create `web/index.html` — the shell with both route containers**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FlyGD Wingman</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>

  <div class="titlebar">
    <div class="pywebview-drag-region">
      <span class="mark">&#9654;</span>
      <span class="name">WINGMAN</span>
      <span class="sub" id="route-label">Uploader</span>
    </div>
    <button class="winbtn gear" id="btn-settings" title="Settings">&#9881;</button>
    <button class="winbtn" id="btn-minimize" title="Minimize">&#8211;</button>
    <button class="winbtn close" id="btn-close" title="Close">&#10005;</button>
  </div>

  <!-- Filled by Task 11 (list) and Task 12 (upload panel). -->
  <div class="route active" id="route-main"></div>

  <!-- Filled by Task 13. -->
  <div class="route" id="route-settings"></div>

  <!-- Filled by Task 12 (status strip + progress bar). -->
  <div id="statusbar-slot"></div>

  <!-- Filled by Task 12 (modal dialog layer). -->
  <div id="dialog-slot"></div>

  <script src="app.js"></script>
  <script src="dev.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create `web/app.js` — the bridge client, handler registry, and title bar**

```js
/* FlyGD Wingman — bridge client and page shell.
 *
 * One rule carries over from app.py's _ui() chokepoint: Python pushes
 * semantic events, never widget calls. Python reaches the page only by
 * calling window.<handler>(payload); the page reaches Python only through
 * WM.send(), which wraps pywebview.api.
 *
 * Selection, sort order, and row focus are CLIENT state and never cross
 * the bridge — the sole exception is the `preselected` flag arriving on
 * onRows, because the watcher preselects newly-finished recordings so the
 * common case needs no clicking.
 */
(function () {
  'use strict';

  var WM = window.WM = {};

  // ---- bridge -------------------------------------------------------
  // pywebview injects window.pywebview.api asynchronously and fires
  // `pywebviewready` when it is usable. Every send() awaits that, so a
  // click landing during startup queues instead of throwing.
  var ready = new Promise(function (resolve) {
    if (window.pywebview && window.pywebview.api) { resolve(); return; }
    window.addEventListener('pywebviewready', function () { resolve(); },
                            { once: true });
  });

  WM.send = function (method) {
    var args = Array.prototype.slice.call(arguments, 1);
    return ready.then(function () {
      var api = window.pywebview && window.pywebview.api;
      var fn = api && api[method];
      if (typeof fn !== 'function') {
        console.error('bridge: no such method: ' + method);
        return null;
      }
      return fn.apply(api, args);
    }).catch(function (err) {
      // A bridge failure must never take the page down: the window would
      // stay up with a dead UI and no diagnostic.
      console.error('bridge: ' + method + ' failed', err);
      return null;
    });
  };

  // Handlers are registered here rather than assigned to window directly,
  // so a typo'd name is caught at registration and every Python push has
  // one visible owner.
  WM.HANDLERS = ['onRows', 'onDuration', 'onProgress', 'onStatus',
                 'onRetryAvailable', 'onLink', 'onSettings', 'onChannel',
                 'onAuthState', 'onDialog'];

  WM.handle = function (name, fn) {
    if (WM.HANDLERS.indexOf(name) === -1) {
      throw new Error('unknown bridge handler: ' + name);
    }
    window[name] = function (payload) {
      try {
        fn(payload || {});
      } catch (err) {
        console.error(name + ' handler failed', err, payload);
      }
    };
  };

  // Every handler exists from load, so a push arriving before its module
  // registers is logged rather than becoming "is not a function" in the
  // WebView2 console where nobody is looking.
  WM.HANDLERS.forEach(function (name) {
    window[name] = function (payload) {
      console.warn('bridge: ' + name + ' arrived before a handler was '
                   + 'registered', payload);
    };
  });

  // ---- dom helpers --------------------------------------------------
  WM.el = function (id) { return document.getElementById(id); };

  WM.make = function (tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  };

  // ---- routing ------------------------------------------------------
  // Settings is a route in this window, not a second OS window. Switching
  // is pure client state; Python is not told which route is showing.
  WM.route = function (name) {
    var main = WM.el('route-main');
    var settings = WM.el('route-settings');
    var on_settings = (name === 'settings');
    main.classList.toggle('active', !on_settings);
    settings.classList.toggle('active', on_settings);
    WM.el('route-label').textContent = on_settings ? 'Settings' : 'Uploader';
    WM.el('btn-settings').classList.toggle('active', on_settings);
    WM.current_route = on_settings ? 'settings' : 'main';
    document.dispatchEvent(new CustomEvent('wm:route',
                                           { detail: WM.current_route }));
  };

  // ---- title bar ----------------------------------------------------
  WM.el('btn-minimize').addEventListener('click', function () {
    WM.send('minimize');
  });
  WM.el('btn-close').addEventListener('click', function () {
    WM.send('close');
  });
  // Settings moves out of the bottom-left corner to the title bar, where a
  // window-level action belongs.
  WM.el('btn-settings').addEventListener('click', function () {
    WM.route(WM.current_route === 'settings' ? 'main' : 'settings');
  });

  // ---- startup ------------------------------------------------------
  ready.then(function () {
    // The page asks for state; Python does not push it unprompted at boot.
    WM.send('list_rows');
  });
}());
```

- [ ] **Step 4: Create `web/dev.js` — a self-guarding browser harness**

```js
/* Manual-verification harness. Inert inside the real app: it does nothing
 * unless the page is loaded WITHOUT pywebview and with ?dev=1, which can
 * only happen in a browser opened by hand. It exists so the page can be
 * eyeballed without launching Python, and is deliberately the only file
 * that fabricates data. */
(function () {
  'use strict';
  if (window.pywebview) return;
  if (!/[?&]dev=1/.test(window.location.search)) return;

  var log = function (name) {
    return function () {
      var args = Array.prototype.slice.call(arguments);
      console.log('DEV api.' + name + '(', args, ')');
      return Promise.resolve(null);
    };
  };

  var api = {};
  ['delete_selected', 'start_upload', 'upload_combat_logs', 'retry',
   'open_path', 'copy_path', 'detect_folder', 'save_settings',
   'connect_google', 'dialog_response', 'minimize', 'close'
  ].forEach(function (name) { api[name] = log(name); });

  api.pick_folder = function (which) {
    console.log('DEV api.pick_folder(', which, ')');
    return Promise.resolve('D:\\Videos\\' + which);
  };

  // Mirrors Api.panel_text: the page asks Python for both strings rather
  // than reimplementing format_selection_summary / format_title_hint here.
  api.panel_text = function (ids, stitch) {
    console.log('DEV api.panel_text(', ids, stitch, ')');
    var hint = (!stitch && ids.length > 1)
      ? 'Title \u2014 each of the ' + ids.length + ' uploads is numbered (1/'
        + ids.length + ')\u2026'
      : 'Title';
    return Promise.resolve({
      summary: ids.length
        ? ids.length + ' selected \u00b7 1.4 GB \u00b7 0:12:31'
        : 'Nothing selected',
      title_hint: hint
    });
  };

  api.auth_labels = function () {
    return Promise.resolve({
      disconnected: { message: 'Not connected', label: 'Sign in with Google', enabled: true },
      connecting: { message: 'Waiting for browser\u2026', label: 'Connecting\u2026', enabled: false },
      connected: { message: 'Connected', label: 'Switch account', enabled: true },
      revoking: { message: 'Signing out\u2026', label: 'Signing out\u2026', enabled: false }
    });
  };

  api.list_rows = function () {
    console.log('DEV api.list_rows()');
    setTimeout(function () {
      window.onRows({ rows: [
        { id: 'r1', name: '2026-08-21 19-04-11.mkv', date: 'Aug 21  19:04',
          size: '1.4 GB', duration: '12:31', link: null, preselected: true },
        { id: 'r2', name: '2026-08-21 17-58-02.mkv', date: 'Aug 21  17:58',
          size: '812.0 MB', duration: '\u2026', link: null, preselected: false },
        { id: 'r3', name: '2026-08-20 22-10-49.mkv', date: 'Aug 20  22:10',
          size: '2.1 GB', duration: '?', link: null, preselected: false },
        { id: 'r4', name: '2026-08-19 21-00-03.mkv', date: 'Aug 19  21:00',
          size: '640.5 MB', duration: '4:07',
          link: 'https://youtu.be/abc123XYZ', preselected: false }
      ] });
      window.onSettings({
        settings: { privacy: 'unlisted', category: '20', notify_mode: 'toast',
                    recording_dir: 'D:\\Videos',
                    gamelogs_dir: 'C:\\Users\\tng\\Documents\\EVE\\logs\\Gamelogs',
                    discord_webhook: 'https://discord.com/api/webhooks/1/tok',
                    channel_id: 'UC123', channel_title: 'FlyGD' },
        webhook_status: 'webhook 1538615213203656754 in #combat-logs',
        detected: { recording: 'D:\\Videos',
                    gamelogs: 'C:\\Users\\tng\\Documents\\EVE\\logs\\Gamelogs' },
        destination: 'Uploads go to FlyGD \u00b7 unlisted'
      });
      window.onChannel({ channel_id: 'UC123', channel_title: 'FlyGD',
                         destination: 'Uploads go to FlyGD \u00b7 unlisted' });
      window.onAuthState({ state: 'connected', message: 'Connected' });
      window.onStatus({ text: 'Ready', kind: 'FG' });
    }, 0);
    return Promise.resolve(null);
  };

  window.pywebview = { api: api };
  window.dispatchEvent(new Event('pywebviewready'));
}());
```

- [ ] **Step 5: Verify the shell renders and the title bar is wired**

Run:
```bash
python3 -m http.server 8765 --directory obs_youtube_uploader/web &
cmd.exe /c start msedge "http://localhost:8765/index.html?dev=1"
```
Expected, with the Edge devtools console open (F12):
1. A near-black `#0c0d10` page with a 44px title bar across the top: a red rounded logo mark with a visible glow, `WINGMAN` in semi-bold, then `UPLOADER` in small uppercase letter-spaced grey.
2. Three buttons at the right: gear, `–`, `✕`. Hovering `–` gives a dark grey pill; hovering `✕` turns it solid red `#d9291c` with white glyph.
3. Clicking `–` logs `DEV api.minimize( [] )`; clicking `✕` logs `DEV api.close( [] )`. Neither throws.
4. Clicking the gear turns it red-tinted, the title-bar sub-label changes `UPLOADER` → `SETTINGS`, and clicking it again changes it back. (Both route containers are still empty at this point, so the body stays blank — that is correct for this task.)
5. The console shows `DEV api.list_rows()` once at load, followed by `bridge: onXxx arrived before a handler was registered` warnings — proof the pre-registration stubs are catching pushes rather than throwing.
6. Selecting text anywhere in the title bar with the mouse does nothing (`user-select: none`).

- [ ] **Step 6: Verify no bare-browser crash without the harness flag**

Run: `cmd.exe /c start msedge "http://localhost:8765/index.html"`

Expected: the same title bar renders. The console shows no errors and no `DEV api.` lines; `WM.send('minimize')` typed into the console returns a pending promise that never rejects (it is waiting for `pywebviewready`, which correctly never fires in a plain browser). Nothing throws.

- [ ] **Step 7: Commit**

```bash
git add obs_youtube_uploader/web/index.html obs_youtube_uploader/web/style.css \
        obs_youtube_uploader/web/app.js obs_youtube_uploader/web/dev.js
git commit -m "web: page shell, design tokens, and custom title bar"
```

---

### Task 11: The recording list

**Files:**
- Create: `obs_youtube_uploader/web/list.js`
- Modify: `obs_youtube_uploader/web/index.html` (fill `#route-main`)
- Modify: `obs_youtube_uploader/web/style.css` (append the list section)

**Interfaces:**
- Consumes: `onRows({rows: [...]})`, `onDuration({id, duration, definitive})`, `onLink({id, video_id})`
- Produces: `pywebview.api.open_path(id)`, `pywebview.api.copy_path(id)`; the exports `WM.list.selectedIds()`, `WM.list.selectedRows()`, `WM.list.rowCount()`, `WM.list.parseSize`, `WM.list.parseDuration`, `WM.list.compareRows`, `WM.list.tooltipForCell`; the `wm:selection` DOM event
- Client-only, never crossing the bridge: selection state, sort column and direction, row focus

- [ ] **Step 1: Append the list styles to `web/style.css`**

```css
/* ====================== recording list ============================== */
/* Two panes, preserving today's split: list left, upload panel right. */
#route-main { padding: 12px; gap: 12px; align-items: stretch; }

.list-pane {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  background: var(--panel); border: 1px solid var(--panel-border);
  border-radius: var(--radius); overflow: hidden;
}

.list-scroll { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; }

/* One grid template shared by the header and every row, so the two can
   never disagree. Columns mirror COLUMN_SPEC: check, filename (elastic),
   date, size, length, link. */
.grid-row {
  display: grid;
  grid-template-columns: 34px minmax(120px, 1fr) 120px 84px 76px 46px;
  align-items: center;
  min-height: var(--row-h);
  padding: 0 10px;
}

.list-head {
  position: sticky; top: 0; z-index: 2;
  background: #101216;
  border-bottom: 1px solid var(--panel-border);
  /* --fs-muted, not --fs-body: headers label the data, they are not the
     data. This is the deliberate ordering carried over from 2.2.0. */
  font-size: var(--fs-muted);
  color: var(--text-dim);
  height: 30px;
}
.list-head > span {
  cursor: pointer; user-select: none; padding: 0 4px;
  display: flex; align-items: center; gap: 4px; white-space: nowrap;
}
.list-head > span:hover { color: var(--text); }
.list-head > span.sorted { color: var(--brand); }
/* Direction indicator on the active column only. */
.list-head > span.sorted::after { content: "\25B2"; font-size: 8px; }
.list-head > span.sorted.desc::after { content: "\25BC"; }
/* Each header is anchored like its column — headers centred over
   right-aligned data read as misalignment, not as a choice. */
.list-head > span.c-check { justify-content: center; padding: 0; }
.list-head > span.c-size,
.list-head > span.c-len  { justify-content: flex-end; }
.list-head > span.c-link { justify-content: center; padding: 0; }

/* 1px separators, NOT zebra striping: with a card surface and adequate row
   height, zebra is compensation for a flat list. */
.list-row {
  border-bottom: 1px solid #191c22;
  border-left: 2px solid transparent;
  cursor: default;
}
.list-row:last-child { border-bottom: 0; }
.list-row:hover { background: #171a20; }
/* Selected rows take a left brand rule and a slightly lifted surface. */
.list-row.sel { background: #191d24; border-left-color: var(--brand); }
/* Row focus is a real concept, not styling: it is what Space acts on. */
.list-row.focused { box-shadow: inset 0 0 0 1px #2f3540; }
.list-scroll:focus { outline: none; }
.list-scroll:focus .list-row.focused { box-shadow: inset 0 0 0 1px #4a5260; }

.c-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding: 0 4px;
}
.c-date { color: var(--text-dim); font-size: var(--fs-muted); padding: 0 4px; }
.c-size, .c-len {
  text-align: right; color: var(--text-dim);
  font-size: var(--fs-muted); font-variant-numeric: tabular-nums; padding: 0 4px;
}
.c-link { text-align: center; }

/* The checkbox: a real drawn control. app.py generated these with Pillow
   because ttk cannot draw one matching the theme; CSS just draws it. */
.c-check { display: flex; justify-content: center; }
.box {
  width: 14px; height: 14px; border-radius: 3px;
  border: 1.5px solid #3a3f49; background: var(--field);
  display: grid; place-items: center; flex: none;
}
.list-row.sel .box {
  background: linear-gradient(180deg, var(--brand), var(--brand-deep));
  border-color: #ff7a6f;
}
.box::after {
  content: "\2713"; font-size: 10px; line-height: 1; color: #fff;
  opacity: 0; font-weight: 700;
}
.list-row.sel .box::after { opacity: 1; }

/* The uploaded-row glyph is a real hover-highlighted control, not a text
   arrow. */
.glyph-link {
  display: inline-grid; place-items: center;
  width: 22px; height: 22px; border-radius: 5px;
  color: var(--text-faint); cursor: pointer;
}
.glyph-link:hover { background: #22252c; color: var(--brand); }
.dur-unknown, .dur-pending { color: var(--text-faint); cursor: help; }

.list-foot {
  flex: none; display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-top: 1px solid var(--panel-border);
  background: #101216;
}
.list-foot .count {
  margin-left: auto; color: var(--text-faint); font-size: var(--fs-muted);
}
.empty {
  padding: 28px 16px; text-align: center;
  color: var(--text-faint); font-size: var(--fs-muted);
}

/* ---- context menu (replaces the Tk tk_popup menu) ------------------- */
.ctxmenu {
  position: fixed; z-index: 40; min-width: 168px; padding: 4px;
  background: var(--panel); border: 1px solid #2a2e37;
  border-radius: var(--radius-sm);
  box-shadow: 0 10px 28px rgba(0, 0, 0, .55);
}
.ctxmenu[hidden] { display: none; }
.ctxmenu button {
  display: block; width: 100%; text-align: left; background: transparent;
  border: 0; border-radius: 4px; padding: 6px 10px;
  color: var(--text); font-family: inherit; font-size: var(--fs-mono);
  cursor: pointer;
}
.ctxmenu button:hover:not(:disabled) { background: #22252c; }
.ctxmenu button:disabled { color: var(--text-faint); cursor: default; }

/* ---- tooltips (replaces tooltip.py's borderless Toplevel) -----------
   DELAY_MS 450 is preserved as a transition-delay: long enough not to fire
   while the pointer crosses the list on its way somewhere else, short
   enough that resting on a glyph feels answered. */
[data-tip] { position: relative; }
[data-tip]::after {
  content: attr(data-tip);
  position: absolute; left: 50%; top: 100%; transform: translate(-50%, 6px);
  z-index: 50; pointer-events: none;
  background: var(--panel); border: 1px solid #2a2e37; border-radius: 6px;
  padding: 6px 8px; color: var(--text);
  font-size: var(--fs-muted); line-height: 1.45;
  /* attr() preserves the literal newlines in CELL_HELP's copy. */
  white-space: pre-line; text-align: left; width: max-content; max-width: 280px;
  box-shadow: 0 8px 22px rgba(0, 0, 0, .5);
  opacity: 0; visibility: hidden;
  transition: opacity .1s linear .45s, visibility 0s linear .45s;
}
[data-tip]:hover::after { opacity: 1; visibility: visible; }
/* Any click means the user is acting, not asking. */
[data-tip]:active::after { opacity: 0; visibility: hidden; transition: none; }
```

- [ ] **Step 2: Fill `#route-main` in `web/index.html`, and load `list.js`**

Replace the line `<div class="route active" id="route-main"></div>` with:

```html
  <div class="route active" id="route-main">

    <div class="list-pane">
      <div class="grid-row list-head" id="list-head">
        <!-- A bare check, deliberately NOT a box glyph: every heading here
             is a sort control, and a box in the header position reads as a
             select-all checkbox this column does not offer. -->
        <span class="c-check"  data-sort="checked"  title="Sort by selected">&#10003;</span>
        <span class="c-name"   data-sort="filename">Filename</span>
        <span class="c-date"   data-sort="date">Date</span>
        <span class="c-size"   data-sort="size">Size</span>
        <span class="c-len"    data-sort="duration">Length</span>
        <span class="c-link"   data-sort="link" title="Sort by uploaded">Link</span>
      </div>

      <div class="list-scroll" id="list-scroll" tabindex="0" role="listbox"
           aria-label="Recordings">
        <div id="list-body"></div>
        <div class="empty" id="list-empty" hidden>
          No recordings found in the watched folder.
        </div>
      </div>

      <div class="list-foot">
        <button class="btn" id="btn-select-all">Select all</button>
        <button class="btn" id="btn-select-none">Select none</button>
        <span class="count" id="list-count">0 recordings</span>
      </div>
    </div>

    <!-- Filled by Task 12 (upload panel). -->
    <div id="panel-slot"></div>

  </div>

  <div class="ctxmenu" id="ctxmenu" hidden>
    <button id="ctx-copy">Copy link</button>
    <button id="ctx-open">Open in browser</button>
  </div>
```

Then add the script tag, immediately before `<script src="dev.js"></script>`:

```html
  <script src="list.js"></script>
```

- [ ] **Step 3: Create `web/list.js` — rendering, pure comparators, and selection**

```js
/* The recording list.
 *
 * Selection, sort order, and row focus are CLIENT state and never cross
 * the bridge. The only selection input from Python is the `preselected`
 * flag on onRows, because the watcher preselects newly-finished
 * recordings so the common case needs no clicking.
 */
(function () {
  'use strict';
  var WM = window.WM;

  // CELL_HELP, copied verbatim from ui/copy.py. Both glyphs were
  // unexplained: the list showed "?" and the arrow with nothing anywhere
  // saying what either meant. Keyed on the RENDERED text, not the
  // underlying value, so it cannot disagree with what the user sees.
  var CELL_HELP = {
    duration: {
      '?': 'Length could not be read. ffprobe could not open this file, so\n'
         + 'combat-log upload is unavailable for it.',
      '\u2026': 'Measuring length\u2026'
    },
    link: {
      '\u2197': 'Uploaded to YouTube.\n'
              + 'Double-click to open it, or right-click to copy the link.'
    }
  };
  var LINK_GLYPH = '\u2197';

  function tooltipForCell(column, text) {
    var col = CELL_HELP[column];
    return (col && col[text]) || null;
  }

  // ---- state --------------------------------------------------------
  var rows = [];              // in Python's delivery order (newest first)
  var order = [];             // ids, in display order
  var selected = Object.create(null);
  var focusId = null;
  var sortKey = null;         // null == Python's delivery order
  var sortDesc = false;
  var ctxId = null;

  // ---- pure helpers -------------------------------------------------
  // Kept as free functions with no DOM access so they can be exercised
  // directly from the devtools console (WM.list.parseSize etc.), which is
  // the whole of the verification budget for pure logic here.
  var UNITS = { B: 1, KB: 1024, MB: 1048576, GB: 1073741824, TB: 1099511627776 };

  function parseSize(text) {
    var m = /^([\d.]+)\s*(B|KB|MB|GB|TB)$/.exec(String(text || '').trim());
    return m ? parseFloat(m[1]) * UNITS[m[2]] : -1;
  }

  function parseDuration(text) {
    // "12:31" -> 751. "?" and the ellipsis are not measurements and sort
    // to the bottom, exactly as app._sort_by's -1.0 does.
    var m = /^(\d+):(\d{2})$/.exec(String(text || '').trim());
    return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : -1;
  }

  function compareRows(a, b, key) {
    if (key === 'checked') {
      return (selected[a.id] ? 1 : 0) - (selected[b.id] ? 1 : 0);
    }
    if (key === 'filename') {
      var an = String(a.name).toLowerCase(), bn = String(b.name).toLowerCase();
      return an < bn ? -1 : an > bn ? 1 : 0;
    }
    if (key === 'date') {
      // The date CELL is a rendered string ("Aug 21  19:04") and cannot be
      // ordered as text — format_date's docstring warns a text sort would
      // put Aug before Dec. Python delivers rows newest-first, so delivery
      // INDEX is the date order, and it stays correct across years.
      return b._index - a._index;
    }
    if (key === 'size') return parseSize(a.size) - parseSize(b.size);
    if (key === 'duration') {
      return parseDuration(a.duration) - parseDuration(b.duration);
    }
    if (key === 'link') {
      return (a.link ? 1 : 0) - (b.link ? 1 : 0);
    }
    throw new Error('unknown sort column: ' + key);
  }

  function byId(id) {
    for (var i = 0; i < rows.length; i++) if (rows[i].id === id) return rows[i];
    return null;
  }

  // ---- rendering ----------------------------------------------------
  function recomputeOrder() {
    var ids = rows.map(function (r) { return r.id; });
    if (sortKey !== null) {
      var sorted = rows.slice().sort(function (a, b) {
        return compareRows(a, b, sortKey);
      });
      if (sortDesc) sorted.reverse();
      ids = sorted.map(function (r) { return r.id; });
    }
    order = ids;
  }

  function rowNode(row) {
    var node = WM.make('div', 'grid-row list-row');
    node.dataset.id = row.id;
    if (selected[row.id]) node.classList.add('sel');
    if (row.id === focusId) node.classList.add('focused');

    var check = WM.make('span', 'c-check');
    check.appendChild(WM.make('span', 'box'));
    node.appendChild(check);

    var name = WM.make('span', 'c-name', row.name);
    name.title = row.name;   // the elastic column ellipsises at narrow widths
    node.appendChild(name);

    node.appendChild(WM.make('span', 'c-date', row.date));
    node.appendChild(WM.make('span', 'c-size', row.size));

    var dur = WM.make('span', 'c-len', row.duration);
    var durTip = tooltipForCell('duration', row.duration);
    if (durTip) {
      dur.setAttribute('data-tip', durTip);
      dur.classList.add(row.duration === '?' ? 'dur-unknown' : 'dur-pending');
    }
    node.appendChild(dur);

    var link = WM.make('span', 'c-link');
    if (row.link) {
      var glyph = WM.make('span', 'glyph-link', LINK_GLYPH);
      var tip = tooltipForCell('link', LINK_GLYPH);
      if (tip) glyph.setAttribute('data-tip', tip);
      link.appendChild(glyph);
    }
    node.appendChild(link);
    return node;
  }

  function render() {
    recomputeOrder();
    var body = WM.el('list-body');
    var frag = document.createDocumentFragment();
    order.forEach(function (id) {
      var row = byId(id);
      if (row) frag.appendChild(rowNode(row));
    });
    body.textContent = '';
    body.appendChild(frag);

    WM.el('list-empty').hidden = rows.length > 0;
    WM.el('list-count').textContent =
      rows.length + (rows.length === 1 ? ' recording' : ' recordings');

    Array.prototype.forEach.call(
      WM.el('list-head').children, function (head) {
        var active = head.dataset.sort === sortKey;
        head.classList.toggle('sorted', active);
        head.classList.toggle('desc', active && sortDesc);
      });

    document.dispatchEvent(new CustomEvent('wm:selection'));
  }

  // Repaint one row in place, so a landing ffprobe result or a new link
  // does not scroll the list or drop the focus ring.
  function repaint(id) {
    var old = WM.el('list-body').querySelector('[data-id="' + id + '"]');
    var row = byId(id);
    if (!old || !row) return;
    old.replaceWith(rowNode(row));
  }

  // ---- selection ----------------------------------------------------
  // One toggle path, shared by mouse and keyboard, so the drawn box can
  // never drift out of step with what selectedIds() reports.
  function toggle(id) {
    if (!byId(id)) return;
    selected[id] = !selected[id];
    var node = WM.el('list-body').querySelector('[data-id="' + id + '"]');
    if (node) node.classList.toggle('sel', !!selected[id]);
    // A "checked" sort is a snapshot, not a live constraint: re-sorting on
    // every tick would move the row out from under the pointer.
    document.dispatchEvent(new CustomEvent('wm:selection'));
  }

  function setFocus(id) {
    var body = WM.el('list-body');
    var prev = body.querySelector('.list-row.focused');
    if (prev) prev.classList.remove('focused');
    focusId = id;
    var node = id && body.querySelector('[data-id="' + id + '"]');
    if (node) {
      node.classList.add('focused');
      node.scrollIntoView({ block: 'nearest' });
    }
  }

  // Tk's arrow handler returns immediately when the focus item is "", and
  // refresh() leaves it "" because every row is reinserted. Without this,
  // tabbing to the list and pressing Down does nothing and Space is
  // unreachable without first reaching for the mouse.
  function ensureFocusItem() {
    if (focusId && byId(focusId)) return;
    setFocus(order.length ? order[0] : null);
  }

  // ---- events -------------------------------------------------------
  WM.el('list-head').addEventListener('click', function (ev) {
    var head = ev.target.closest('[data-sort]');
    if (!head) return;
    var key = head.dataset.sort;
    sortDesc = (key === sortKey) ? !sortDesc : false;
    sortKey = key;
    render();
    ensureFocusItem();
  });

  var body = WM.el('list-body');

  body.addEventListener('click', function (ev) {
    var node = ev.target.closest('.list-row');
    if (!node) return;
    // event.detail === 2 is the SECOND click of a double-click. Skipping
    // it leaves exactly one toggle landed by the time dblclick fires,
    // which is the situation the Tk handler was written against.
    if (ev.detail > 1) return;
    // The WHOLE row is the click target, not just the checkbox cell: a
    // 34px column is a small thing to ask someone to hit when "I mean this
    // recording" is unambiguous anywhere on the line.
    setFocus(node.dataset.id);
    toggle(node.dataset.id);
  });

  body.addEventListener('dblclick', function (ev) {
    var node = ev.target.closest('.list-row');
    if (!node) return;
    // Exactly one toggle has already landed; undo it. Opening a video is
    // not a selection gesture, and a user reaching for their upload should
    // not find an extra row ticked afterwards.
    toggle(node.dataset.id);
    WM.send('open_path', node.dataset.id);
  });

  var scroll = WM.el('list-scroll');
  scroll.addEventListener('focus', ensureFocusItem);
  scroll.addEventListener('keydown', function (ev) {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      ensureFocusItem();
      var at = order.indexOf(focusId);
      var next = at + (ev.key === 'ArrowDown' ? 1 : -1);
      if (next >= 0 && next < order.length) setFocus(order[next]);
      return;
    }
    if (ev.key === ' ' || ev.key === 'Spacebar') {
      // Keyboard equivalent of clicking the checkbox. preventDefault is
      // the browser's answer to Tk's "break": without it Space also
      // page-scrolls the list.
      ev.preventDefault();
      ensureFocusItem();
      if (focusId) toggle(focusId);
    }
  });

  // ---- context menu -------------------------------------------------
  var menu = WM.el('ctxmenu');
  var ctxCopy = WM.el('ctx-copy');
  var ctxOpen = WM.el('ctx-open');

  function hideMenu() { menu.hidden = true; ctxId = null; }

  body.addEventListener('contextmenu', function (ev) {
    var node = ev.target.closest('.list-row');
    if (!node) { hideMenu(); return; }
    ev.preventDefault();
    ctxId = node.dataset.id;
    setFocus(ctxId);
    var row = byId(ctxId);
    // Both items act on the YouTube link (app._copy / app._open), so both
    // are dead without one.
    var has = !!(row && row.link);
    ctxCopy.disabled = !has;
    ctxOpen.disabled = !has;
    menu.hidden = false;
    // Clamp inside the window: a menu opened on the last row would
    // otherwise hang below the status strip.
    var w = menu.offsetWidth, h = menu.offsetHeight;
    menu.style.left = Math.min(ev.clientX, window.innerWidth - w - 6) + 'px';
    menu.style.top = Math.min(ev.clientY, window.innerHeight - h - 6) + 'px';
  });

  ctxCopy.addEventListener('click', function () {
    if (ctxId) {
      // Python returns the URL; the page owns the clipboard write, because
      // with Tk gone there is no toolkit clipboard and navigator.clipboard
      // is right there.
      var id = ctxId;
      WM.send('copy_path', id).then(function (url) {
        if (url) navigator.clipboard.writeText(url);
      });
    }
    hideMenu();
  });
  ctxOpen.addEventListener('click', function () {
    if (ctxId) WM.send('open_path', ctxId);
    hideMenu();
  });
  document.addEventListener('mousedown', function (ev) {
    if (!menu.hidden && !menu.contains(ev.target)) hideMenu();
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') hideMenu();
  });
  window.addEventListener('blur', hideMenu);

  WM.el('btn-select-all').addEventListener('click', function () {
    rows.forEach(function (r) { selected[r.id] = true; });
    render();
  });
  WM.el('btn-select-none').addEventListener('click', function () {
    rows.forEach(function (r) { selected[r.id] = false; });
    render();
  });

  // ---- bridge handlers ----------------------------------------------
  WM.handle('onRows', function (payload) {
    var incoming = payload.rows || [];
    var known = Object.create(null);
    incoming.forEach(function (r, i) { r._index = i; known[r.id] = true; });
    // Ids are minted fresh on every rebuild (see ui/rows.py), so a
    // selection carried across a refresh by id would silently attach to
    // different recordings. Selection therefore starts from whatever
    // Python marked preselected, and stale entries are dropped.
    Object.keys(selected).forEach(function (id) {
      if (!known[id]) delete selected[id];
    });
    incoming.forEach(function (r) {
      if (r.preselected) selected[r.id] = true;
    });
    rows = incoming;
    if (focusId && !known[focusId]) focusId = null;
    render();
    ensureFocusItem();
  });

  WM.handle('onDuration', function (payload) {
    var row = byId(payload.id);
    if (!row) return;   // a refresh may have dropped it mid-probe
    row.duration = payload.duration;
    row.definitive = !!payload.definitive;
    repaint(payload.id);
    document.dispatchEvent(new CustomEvent('wm:selection'));
  });

  WM.handle('onLink', function (payload) {
    var row = byId(payload.id);
    if (!row) return;
    row.link = 'https://www.youtube.com/watch?v=' + payload.video_id;
    repaint(payload.id);
  });

  // ---- exports for the other page modules ---------------------------
  WM.list = {
    selectedIds: function () {
      return order.filter(function (id) { return !!selected[id]; });
    },
    selectedRows: function () {
      return order.map(byId).filter(function (r) { return r && selected[r.id]; });
    },
    rowCount: function () { return rows.length; },
    // Exposed for console verification of the pure logic.
    parseSize: parseSize,
    parseDuration: parseDuration,
    compareRows: compareRows,
    tooltipForCell: tooltipForCell
  };
}());
```

- [ ] **Step 4: Verify rendering, sorting, and the pure comparators**

Run:
```bash
python3 -m http.server 8765 --directory obs_youtube_uploader/web &
cmd.exe /c start msedge "http://localhost:8765/index.html?dev=1"
```
Expected:
1. Four rows inside a `#14161b` card with a sticky header. Header text is visibly *smaller* than the row text (11.5px vs 13px) — if the headers look bigger, the type scale has been inverted and is wrong.
2. Rows are separated by hairline `#191c22` rules. There is **no** alternating row background — every unselected, unhovered row is the same colour.
3. `2026-08-21 19-04-11.mkv` is checked on load (a red gradient box with a white tick) and carries a red left rule; the other three do not. Nothing was clicked to achieve this — that is `preselected` arriving on `onRows`.
4. Clicking the `Size` header turns it red with a `▲` and reorders ascending: `640.5 MB, 812.0 MB, 1.4 GB, 2.1 GB`. Clicking again gives `▼` and the exact reverse. Only one header is ever red.
5. Clicking `Date` gives newest-first (`Aug 21 19:04` at top); clicking again gives oldest-first.
6. In the console, `WM.list.parseSize('1.4 GB')` returns `1503238553.6`, `WM.list.parseSize('?')` returns `-1`, `WM.list.parseDuration('12:31')` returns `751`, and `WM.list.parseDuration('…')` returns `-1`.
7. The list scrollbar (shrink the window until it appears) is a thin dark `#262a33` rounded thumb on a transparent track — not the classic Windows scrollbar.

- [ ] **Step 5: Verify the four preserved interactions**

With the same page open:
1. **Arrow-key focus.** Click once on the `Filename` cell of row 2 (this both focuses the list and toggles row 2 — expected). Press `↓` twice: a subtle 1px focus ring moves down two rows without changing any checkbox. Press `↑` three times: the ring stops at the top row and does not wrap.
2. **Space toggles the focused row.** With the ring on row 1, press `Space`: row 1's box changes state and the list does **not** scroll. Press `Space` again: it changes back.
3. **Focus on first entry.** Reload the page, press `Tab` until the list has keyboard focus, then press `↓` immediately. The ring appears on row 1 and moves to row 2 — it does not require a mouse click first.
4. **Context menu.** Right-click row 4 (the one with a link): a dark menu appears at the pointer with `Copy link` and `Open in browser` both enabled. Clicking `Copy link` logs `DEV api.copy_path( ["r4"] )` and closes the menu. Right-click row 1 (no link): both items render greyed and are unclickable. Right-clicking then pressing `Escape`, or clicking elsewhere, closes the menu and leaves the page fully responsive to clicks afterwards.
5. **Double-click opens without changing selection.** Note row 3's checkbox state, then double-click its filename. The console logs `DEV api.open_path( ["r3"] )` and **row 3's checkbox is exactly as it was before the double-click**. Repeat on row 1 (which starts checked) — it is still checked afterwards.

- [ ] **Step 6: Verify the CELL_HELP tooltips**

With the same page open:
1. Rest the pointer on row 2's `…` in the Length column. After roughly half a second a dark bordered tip appears reading `Measuring length…`. It does not appear instantly on a pointer that merely crosses the cell.
2. Rest on row 3's `?`. The tip reads, over two lines: `Length could not be read. ffprobe could not open this file, so` / `combat-log upload is unavailable for it.`
3. Rest on row 4's `↗` glyph (which also highlights to a red-tinted rounded button on hover). The tip reads, over two lines: `Uploaded to YouTube.` / `Double-click to open it, or right-click to copy the link.`
4. Press the mouse button while a tip is showing: it disappears immediately.
5. In the console, `WM.list.tooltipForCell('duration', '12:31')` returns `null` — only the two glyphs are annotated.

- [ ] **Step 7: Verify the JS copy still matches the Python copy**

Run:
```bash
python3 - <<'PY'
import pathlib
py = pathlib.Path('obs_youtube_uploader/ui/copy.py').read_text(encoding='utf-8')
js = pathlib.Path('obs_youtube_uploader/web/list.js').read_text(encoding='utf-8')
for phrase in ["Length could not be read. ffprobe could not open this file, so",
               "combat-log upload is unavailable for it.",
               "Measuring length",
               "Uploaded to YouTube.",
               "Double-click to open it, or right-click to copy the link."]:
    assert phrase in py, ("missing from ui/copy.py: " + phrase)
    assert phrase in js, ("missing from list.js: " + phrase)
print("CELL_HELP copy matches ui/copy.py")
PY
```
Expected: prints `CELL_HELP copy matches ui/copy.py` and exits 0. `test_tooltip.py` still guards the Python side; this check is what stops the JS copy drifting from it.

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/web/list.js obs_youtube_uploader/web/index.html \
        obs_youtube_uploader/web/style.css
git commit -m "web: the recording list"
```

---

### Task 12: Upload panel, status strip, and the dialog layer

**Files:**
- Create: `obs_youtube_uploader/web/panel.js`
- Modify: `obs_youtube_uploader/web/index.html` (fill `#panel-slot`, `#statusbar-slot`, `#dialog-slot`)
- Modify: `obs_youtube_uploader/web/style.css` (append the panel, status-strip, and dialog sections)
- Modify: `obs_youtube_uploader/web/dev.js` (add harness drivers)

**Interfaces:**
- Consumes: `onStatus({text, kind})`, `onProgress({mode, pct, text, kind})`, `onRetryAvailable({available})`, `onChannel({channel_id, channel_title})`, `onSettings({settings, webhook_status, detected})`, `onDialog({kind, title, body, request_id})`; `WM.list.selectedIds()` and the `wm:selection` event
- Produces: `pywebview.api.start_upload(...)`, `upload_combat_logs(ids)`, `delete_selected(ids)`, `retry()`, `dialog_response(request_id, ok)`, `panel_text(ids, stitch)`; re-dispatches `wm:settings` for Task 13

> **Reconciliation note.** The selection summary is **not** reimplemented in
> JavaScript. `format_selection_summary` is a pure Python function with tests,
> and its two asymmetries — `"+"` when a probe is outstanding, never a partial
> marker on size — are subtle enough that a second copy would drift within a
> release. The same applies to `format_title_hint` and `format_destination`. The page
> calls `panel_text(ids, stitch)` on every selection or stitch change, and renders the
> `destination` string pushed on `onChannel`/`onSettings`.

- [ ] **Step 1: Append the panel, status-strip, and dialog styles to `web/style.css`**

```css
/* ====================== upload panel ================================ */
#panel-slot { flex: none; display: flex; }

.panel {
  width: 320px; flex: none; display: flex; flex-direction: column; gap: 12px;
  overflow-y: auto;
}

.panel .card { flex: none; }

.panel .lab {
  display: block; color: var(--text-dim); font-size: var(--fs-muted);
  margin-bottom: 5px;
}

/* A sensible fixed height. NOT flex:1 — today the Description box consumes
   all remaining vertical space and reads as an empty void. */
#f-desc { height: 96px; }

.check {
  display: flex; align-items: center; gap: 9px; cursor: pointer;
  color: var(--text);
}
.check input { position: absolute; opacity: 0; width: 0; height: 0; }
.check .box { width: 15px; height: 15px; }
.check input:checked + .box {
  background: linear-gradient(180deg, var(--brand), var(--brand-deep));
  border-color: #ff7a6f;
}
.check input:checked + .box::after { opacity: 1; }
.check input:focus-visible + .box { box-shadow: 0 0 0 2px rgba(255, 90, 77, .3); }

.summary {
  color: var(--text-dim); font-size: var(--fs-muted);
  font-variant-numeric: tabular-nums;
}
/* The upload destination, learned from the videos.insert response. Always
   visible so the user can see where uploads actually go. */
.destination {
  color: var(--text-faint); font-size: var(--fs-muted);
  margin-bottom: 10px; line-height: 1.4;
}
.actions { display: flex; flex-direction: column; gap: 8px; }
.actions button.btn { width: 100%; text-align: center; padding: 9px 12px; }
.actions .secondary-row { display: flex; gap: 8px; }
.actions .secondary-row button.btn { flex: 1; }

/* ====================== status strip ================================ */
.statusbar {
  flex: none; display: flex; align-items: center; gap: 14px;
  padding: 10px 16px; border-top: 1px solid var(--panel-border);
  background: #101216;
}
#status {
  font-size: var(--fs-mono); color: var(--text-dim);
  min-width: 210px; flex: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* Severity kinds stay FG / SUCCESS / WARNING / ERROR, matching
   app._status_kind, so the semantics carry over even though the colours
   moved out of theme.py and into CSS. */
#status.FG { color: var(--text-dim); }
#status.SUCCESS { color: var(--ok); }
#status.WARNING { color: var(--warn); }
#status.ERROR { color: var(--err); }

.track {
  flex: 1; height: 4px; border-radius: 2px; background: #1e2128;
  overflow: hidden; position: relative;
}
.bar {
  height: 100%; width: 0%; border-radius: 2px;
  background: linear-gradient(90deg, var(--brand-deep), var(--brand));
  box-shadow: 0 0 10px rgba(255, 90, 77, .6);
  transition: width .12s linear;
}
/* Indeterminate: an ffmpeg stitch reports no readable progress, so the bar
   must say "working" without claiming a percentage. The transition is
   dropped here or it fights the animation. */
.track.indeterminate .bar {
  width: 34%; transition: none;
  animation: slide 1.15s cubic-bezier(.45, .05, .55, .95) infinite;
}
@keyframes slide {
  0%   { transform: translateX(-110%); }
  100% { transform: translateX(320%); }
}
.pct {
  flex: none; width: 42px; text-align: right;
  color: var(--text-faint); font-size: var(--fs-muted);
  font-variant-numeric: tabular-nums;
}

/* ====================== modal dialog layer ==========================
   Modals are native Tk message boxes today, called from workers. They
   become in-page modals; `confirm` is the only request/response pair in an
   otherwise fire-and-forget protocol. */
.overlay {
  position: fixed; inset: 0; z-index: 60;
  background: rgba(6, 7, 9, .62);
  display: grid; place-items: center; padding: 24px;
}
.overlay[hidden] { display: none; }

.dialog {
  width: min(460px, 100%);
  background: var(--panel); border: 1px solid #2a2e37;
  border-radius: var(--radius); padding: 18px 20px 16px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, .6);
}
.dialog h3 {
  font-size: var(--fs-head); font-weight: 620; margin-bottom: 10px;
  display: flex; align-items: center; gap: 9px;
}
.dialog h3::before {
  content: ""; width: 3px; height: 15px; border-radius: 2px; flex: none;
  background: var(--text-faint);
}
.dialog.error h3::before   { background: var(--err); box-shadow: 0 0 9px var(--err); }
.dialog.warning h3::before { background: var(--warn); box-shadow: 0 0 9px var(--warn); }
.dialog.confirm h3::before {
  background: linear-gradient(180deg, var(--brand), var(--brand-deep));
  box-shadow: 0 0 9px rgba(255, 90, 77, .5);
}
.dialog .body {
  /* format_upload_confirm composes a multi-line body with the exact
     (n/total) titles in it; pre-wrap is what keeps that layout. */
  white-space: pre-wrap; line-height: 1.55; color: var(--text-dim);
  max-height: 46vh; overflow-y: auto; user-select: text;
  font-size: var(--fs-body);
}
.dialog .buttons {
  display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px;
}
```

- [ ] **Step 2: Fill the three slots in `web/index.html`, and load `panel.js`**

Replace `<div id="panel-slot"></div>` with:

```html
    <div id="panel-slot">
      <div class="panel">

        <section class="card">
          <h2>Upload</h2>
          <label class="lab" for="f-title" id="lab-title">Title</label>
          <input class="field" id="f-title" type="text" spellcheck="false"
                 placeholder="Title for this upload">
          <label class="lab" for="f-desc" style="margin-top:10px">Description</label>
          <textarea class="field" id="f-desc" spellcheck="false"
                    placeholder="Optional description"></textarea>
          <label class="check" style="margin-top:12px">
            <input type="checkbox" id="f-stitch"><span class="box"></span>
            Stitch selected into one video
          </label>
          <p class="summary" id="selection-summary"
             style="margin-top:12px">Nothing selected</p>
        </section>

        <section class="card">
          <h2>Publish</h2>
          <p class="destination" id="destination">Channel confirmed after the first upload</p>
          <div class="actions">
            <button class="btn acc" id="btn-upload">Upload Selected</button>
            <button class="btn" id="btn-combat">Upload combat logs</button>
            <div class="secondary-row">
              <button class="btn" id="btn-retry" disabled>Retry</button>
              <button class="btn" id="btn-delete">Delete selected</button>
            </div>
          </div>
        </section>

      </div>
    </div>
```

Replace `<div id="statusbar-slot"></div>` with:

```html
  <div id="statusbar-slot">
    <div class="statusbar">
      <span id="status" class="FG">Ready</span>
      <div class="track" id="track"><div class="bar" id="bar"></div></div>
      <span class="pct" id="pct"></span>
    </div>
  </div>
```

Replace `<div id="dialog-slot"></div>` with:

```html
  <div id="dialog-slot">
    <div class="overlay" id="overlay" hidden>
      <div class="dialog" id="dialog" role="dialog" aria-modal="true"
           aria-labelledby="dlg-title">
        <h3 id="dlg-title"></h3>
        <div class="body" id="dlg-body"></div>
        <div class="buttons">
          <button class="btn" id="dlg-cancel" hidden>Cancel</button>
          <button class="btn acc" id="dlg-ok">OK</button>
        </div>
      </div>
    </div>
  </div>
```

Then add the script tag, immediately after `<script src="list.js"></script>`:

```html
  <script src="panel.js"></script>
```

- [ ] **Step 3: Create `web/panel.js`**

```js
/* Upload panel, status strip, and the modal dialog layer.
 *
 * The panel owns no upload logic: it collects the fields, hands them to
 * start_upload, and renders what comes back. Every guard, warning, and
 * confirmation is still composed in Python (start_upload,
 * delete_selected, format_upload_confirm) and merely rendered here — a
 * page-side confirmation would be a second copy of that text with nothing
 * keeping the two in step.
 */
(function () {
  'use strict';
  var WM = window.WM;

  // Upload defaults live in Settings and ride along on start_upload.
  // Defaults mirror settings.DEFAULTS so a send before onSettings lands is
  // still a valid call rather than undefined.
  var prefs = { privacy: 'unlisted', category: '20' };

  // ---- selection-dependent copy ---------------------------------------
  // Asked of Python rather than recomputed here. Both strings are pure,
  // tested functions whose decisions are subtle enough that a JavaScript
  // twin would drift within a release: the summary's "+" appears only when
  // a probe is outstanding and never on size, and the title hint discloses
  // that build_body numbers a batch -- added in 2.2.0 after users got ten
  // differently-named public videos. The round trip is in-process and
  // fires on a human click, so its cost is invisible.
  var panelSeq = 0;

  function refreshPanelText() {
    var seq = ++panelSeq;
    WM.send('panel_text', WM.list.selectedIds(), WM.el('f-stitch').checked)
      .then(function (text) {
        // Clicks can outrun replies; only the newest answer may paint, or a
        // slow earlier reply overwrites a newer count.
        if (seq !== panelSeq || !text) return;
        WM.el('selection-summary').textContent = text.summary;
        WM.el('lab-title').textContent = text.title_hint;
      });
  }
  document.addEventListener('wm:selection', refreshPanelText);
  // Stitching collapses a batch into ONE video, so the numbering
  // disclosure must appear and disappear with this checkbox too.
  WM.el('f-stitch').addEventListener('change', refreshPanelText);

  // ---- actions -------------------------------------------------------
  // Every one of these sends unconditionally, including with an empty
  // selection: the "select at least one video" warnings are distinct
  // messages composed in Python, and a page-side early return would
  // silently swallow them.
  WM.el('btn-upload').addEventListener('click', function () {
    WM.send('start_upload',
            WM.el('f-title').value,
            WM.el('f-desc').value,
            prefs.privacy,
            prefs.category,
            WM.el('f-stitch').checked,
            WM.list.selectedIds());
  });

  WM.el('btn-combat').addEventListener('click', function () {
    WM.send('upload_combat_logs', WM.list.selectedIds());
  });

  WM.el('btn-delete').addEventListener('click', function () {
    WM.send('delete_selected', WM.list.selectedIds());
  });

  WM.el('btn-retry').addEventListener('click', function () {
    WM.send('retry');
  });

  // ---- status strip ---------------------------------------------------
  var KINDS = ['FG', 'SUCCESS', 'WARNING', 'ERROR'];

  function setStatus(text, kind) {
    var node = WM.el('status');
    node.textContent = text;
    node.className = KINDS.indexOf(kind) === -1 ? 'FG' : kind;
    node.title = text;   // the strip ellipsises a long ffmpeg error
  }

  WM.handle('onStatus', function (p) {
    setStatus(p.text || '', p.kind);
  });

  WM.handle('onProgress', function (p) {
    var track = WM.el('track'), bar = WM.el('bar'), pct = WM.el('pct');
    if (p.mode === 'indeterminate') {
      // A stitch reports no readable percentage. The bar must say
      // "working" without claiming one, so the number is blanked too.
      track.classList.add('indeterminate');
      bar.style.width = '';
      pct.textContent = '';
    } else {
      track.classList.remove('indeterminate');
      var value = Math.max(0, Math.min(100, Number(p.pct) || 0));
      bar.style.width = value + '%';
      pct.textContent = Math.round(value) + '%';
    }
    if (p.text) setStatus(p.text, p.kind);
  });

  WM.handle('onRetryAvailable', function (p) {
    WM.el('btn-retry').disabled = !p.available;
  });

  // ---- upload destination ---------------------------------------------
  // Rendered by Python and pushed, not composed here: format_destination
  // states the "learned from the first upload" case in words, and that
  // explanation is tested copy rather than a template.
  WM.handle('onChannel', function (p) {
    if (p.destination) WM.el('destination').textContent = p.destination;
  });

  WM.handle('onSettings', function (p) {
    var s = p.settings || {};
    if (s.privacy) prefs.privacy = s.privacy;
    if (s.category) prefs.category = s.category;
    if (p.destination) WM.el('destination').textContent = p.destination;
    // Settings owns the rest of this payload; it re-dispatches so both
    // modules can consume one push without either owning the handler.
    document.dispatchEvent(new CustomEvent('wm:settings', { detail: p }));
  });

  // ---- dialog layer ----------------------------------------------------
  // A queue, not a single slot: workers can push a warning and a confirm
  // in quick succession, and a second arriving dialog must not silently
  // discard the first — which for a `confirm` would strand Python waiting
  // on a dialog_response that never comes.
  var queue = [];
  var active = null;

  var overlay = WM.el('overlay');
  var dlg = WM.el('dialog');
  var btnOk = WM.el('dlg-ok');
  var btnCancel = WM.el('dlg-cancel');

  function show(item) {
    active = item;
    dlg.className = 'dialog ' + (item.kind || 'info');
    WM.el('dlg-title').textContent = item.title || '';
    WM.el('dlg-body').textContent = item.body || '';
    var isConfirm = item.kind === 'confirm';
    btnCancel.hidden = !isConfirm;
    btnOk.textContent = isConfirm ? 'Confirm' : 'OK';
    // Upload is the app's only irreversible action, so the accent stays on
    // the affirming button of a confirm and on nothing else in the dialog.
    btnOk.className = isConfirm ? 'btn acc' : 'btn';
    overlay.hidden = false;
    btnOk.focus();
  }

  function next() {
    active = null;
    overlay.hidden = true;
    if (queue.length) show(queue.shift());
  }

  function answer(ok) {
    if (!active) return;
    if (active.kind === 'confirm' && active.request_id !== undefined
        && active.request_id !== null) {
      WM.send('dialog_response', active.request_id, ok);
    }
    next();
  }

  btnOk.addEventListener('click', function () { answer(true); });
  btnCancel.addEventListener('click', function () { answer(false); });

  document.addEventListener('keydown', function (ev) {
    if (overlay.hidden) return;
    if (ev.key === 'Escape') {
      ev.preventDefault();
      // Escape on a confirm is a No, never a silent dismissal: Python is
      // blocked on an answer and must get one.
      answer(active && active.kind === 'confirm' ? false : true);
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      answer(true);
    }
  }, true);

  WM.handle('onDialog', function (p) {
    if (active) queue.push(p); else show(p);
  });
}());
```

- [ ] **Step 4: Add the harness drivers to `web/dev.js`**

In `web/dev.js`, immediately before `window.pywebview = { api: api };`, insert:

```js
  // Manual drivers for the pushes no click can produce in a browser.
  // Typed into the devtools console during verification.
  window.DEV = {
    determinate: function (pct) {
      window.onProgress({ mode: 'determinate', pct: pct,
                          text: 'Uploading file 1 of 3\u2026 ' + pct + '%',
                          kind: 'FG' });
    },
    stitching: function () {
      window.onProgress({ mode: 'indeterminate', pct: 0,
                          text: 'Stitching with FFmpeg\u2026', kind: 'FG' });
    },
    status: function (text, kind) {
      window.onStatus({ text: text, kind: kind });
    },
    retry: function (available) {
      window.onRetryAvailable({ available: available });
    },
    channel: function (title) {
      window.onChannel({ channel_id: 'UC123', channel_title: title,
                         destination: 'Uploads go to ' + title
                                      + ' \u00b7 unlisted' });
    },
    info: function () {
      window.onDialog({ kind: 'info', title: 'Upload complete',
                        body: 'All 3 recordings were uploaded.' });
    },
    warn: function () {
      window.onDialog({ kind: 'warning', title: 'No Selection',
                        body: 'Select at least one video to upload.' });
    },
    err: function () {
      window.onDialog({ kind: 'error', title: 'Upload failed',
                        body: 'HttpError 403: quotaExceeded' });
    },
    confirm: function () {
      window.onDialog({ kind: 'confirm', title: 'Confirm Upload',
        request_id: 'req-7',
        body: 'Upload 2 recordings to YouTube?\n\n'
            + 'Channel:  FlyGD\nPrivacy:  unlisted\n'
            + 'Title:    "Fight (1/2)" \u2026 "Fight (2/2)"\n'
            + 'Total:    3.5 GB \u00b7 0:24:11\n\n'
            + 'Publishing to YouTube cannot be undone from this app.' });
    },
    twoDialogs: function () {
      window.DEV.warn();
      window.DEV.confirm();
    },
    authState: function (state, message) {
      window.onAuthState({ state: state, message: message });
    },
    settings: function (patch, statusLine) {
      window.onSettings({
        settings: Object.assign(
          { privacy: 'unlisted', category: '20', notify_mode: 'toast',
            recording_dir: 'D:\\Videos',
            gamelogs_dir: 'C:\\Users\\tng\\Documents\\EVE\\logs\\Gamelogs',
            discord_webhook: 'https://discord.com/api/webhooks/1/tok',
            channel_id: 'UC123', channel_title: 'FlyGD' }, patch || {}),
        webhook_status: statusLine === undefined
          ? 'webhook 1538615213203656754 in #combat-logs' : statusLine,
        detected: { recording: 'D:\\Videos',
                    gamelogs: 'C:\\Users\\tng\\Documents\\EVE\\logs\\Gamelogs' },
        destination: 'Uploads go to FlyGD \u00b7 unlisted'
      });
    }
  };
```

- [ ] **Step 5: Verify the panel layout and the selection summary**

Run:
```bash
python3 -m http.server 8765 --directory obs_youtube_uploader/web &
cmd.exe /c start msedge "http://localhost:8765/index.html?dev=1"
```
Expected:
1. A 320px right pane with two cards headed `UPLOAD` and `PUBLISH`, each preceded by a short red rule.
2. The Description box is a fixed 96px tall. Resizing the window taller makes the list grow and leaves the Description box exactly the same height — it never stretches to fill the pane. It cannot be drag-resized by its corner.
3. Exactly **one** brand-accent control is visible: `Upload Selected`. `Upload combat logs`, `Retry`, and `Delete selected` are flat secondary buttons, and `Retry` is greyed and unclickable at load with no push having arrived.
4. The summary line reads `1 selected · …` (row 1 is preselected), and the console shows `DEV api.panel_text( ["r1"] false )` — both strings came from Python, not from JavaScript.
5. Clicking rows changes the count and logs a fresh `panel_text` call each time. Clicking `Select none` logs a call with `[]` and the line reads `Nothing selected`.
6. With two or more rows selected and Stitch **off**, the Title label reads `Title — each of the 2 uploads is numbered (1/2)…`. Ticking **Stitch** logs another `panel_text` call and the label collapses back to plain `Title`, because stitching produces one video and the numbering disclosure would be a lie. Unticking restores it.

- [ ] **Step 6: Verify the actions and the destination line**

With the same page open and the console visible:
1. Reload, click `Upload Selected`. The console logs `DEV api.start_upload( ["", "", "unlisted", "20", false, ["r1"]] )`.
2. Type `Fight night` into Title, `gf` into Description, tick Stitch, click row 4 as well, then click `Upload Selected`: `start_upload( ["Fight night", "gf", "unlisted", "20", true, ["r1","r4"]] )`.
3. Click `Select none`, then `Upload Selected`. It still logs `start_upload` with an empty id array — the page does **not** guard the empty case, because that warning is a distinct Python message.
4. `Upload combat logs` and `Delete selected` log their calls with the same id array.
5. The destination reads `Uploads go to FlyGD · unlisted`. Run `DEV.channel('Second Channel')` — it updates immediately.
6. Run `DEV.retry(true)` — `Retry` becomes live and clicking it logs `retry`. `DEV.retry(false)` greys it again.

- [ ] **Step 7: Verify both progress modes and the status kinds**

In the console:
1. `DEV.determinate(0)` — bar empty, number `0%`, status `Uploading file 1 of 3… 0%`.
2. `DEV.determinate(45)` then `DEV.determinate(90)` — the red glowing bar animates smoothly and the number tracks it.
3. `DEV.stitching()` — the number **blanks** and a 34% segment slides across the track continuously with no percentage shown. Status reads `Stitching with FFmpeg…`.
4. `DEV.determinate(60)` — the animation stops immediately and the bar settles at 60%.
5. `DEV.status('Ready','FG')` → grey. `('Upload complete','SUCCESS')` → green. `('Skipped 1 file','WARNING')` → amber. `('Upload failed','ERROR')` → red. None changes the bar.

- [ ] **Step 8: Verify the dialog layer, including the confirm round-trip**

In the console:
1. `DEV.info()` — a dimmed overlay with a card titled `Upload complete`, a single non-accented `OK`, no `Cancel`. Clicking `OK` closes it and logs nothing.
2. `DEV.warn()` — amber rule beside the title. `DEV.err()` — red rule.
3. `DEV.confirm()` — a card titled `Confirm Upload` with a red rule, `Cancel`, and an accented `Confirm`. The body preserves line breaks exactly, showing `Channel:  FlyGD` with its double space intact and both `(1/2)` / `(2/2)` titles.
4. `Confirm` logs `dialog_response( ["req-7", true] )`; re-run and `Cancel` logs `[..., false]`.
5. Re-run and press `Escape`: logs `false` — Escape is a No, never a silent dismissal that would strand Python.
6. Re-run and press `Enter`: logs `true`.
7. `DEV.twoDialogs()` — the warning shows first; dismissing it reveals the confirm rather than losing it, and answering that logs its `dialog_response`. The overlay clears only after both.
8. While a dialog is open, clicking `Upload Selected` behind the overlay does nothing.

- [ ] **Step 9: Commit**

```bash
git add obs_youtube_uploader/web/panel.js obs_youtube_uploader/web/index.html \
        obs_youtube_uploader/web/style.css obs_youtube_uploader/web/dev.js
git commit -m "web: upload panel, status strip, and dialog layer"
```

---

### Task 13: Settings route and first-run route

**Files:**
- Create: `obs_youtube_uploader/web/settings.js`
- Create: `obs_youtube_uploader/web/firstrun.js`
- Modify: `obs_youtube_uploader/web/index.html` (fill `#route-settings`)
- Modify: `obs_youtube_uploader/web/style.css` (append the settings section)

**Interfaces:**
- Consumes: the `wm:settings` event Task 12 re-dispatches (carrying `{settings, webhook_status, detected}`), `onAuthState({state, message})`, and `pywebview.api.auth_labels()`
- Produces: `pywebview.api.save_settings(obj)`, `pick_folder(which)`, `detect_folder(which, current)`, `connect_google()`, `set_recording_dir(path)`; the `#route-firstrun` container and `WM.route('firstrun')`

> **Reconciliation notes.** `which` is `"recording"` or `"gamelogs"` — the values
> Task 9's `pick_folder`/`detect_folder` branch on — and the `detected` payload
> uses those same two keys. `webhook_status` is read from the payload's top
> level, not from inside `settings`. The account-state labels come from
> `auth_labels()` rather than a second table in JavaScript.

- [ ] **Step 1: Append the settings styles to `web/style.css`**

```css
/* ====================== settings route ==============================
   A route in this window, not a second OS window. */
#route-settings { flex-direction: column; overflow-y: auto; padding: 12px; }

.settings {
  display: flex; flex-direction: column; gap: 12px;
  width: 100%; max-width: 620px; margin: 0 auto;
}

/* One label column for the WHOLE screen, not per-card: label columns that
   do not align across groups are the first thing wrong in settings.png. */
.settings .row > .lab {
  width: 118px; flex: none; color: var(--text-dim);
  font-size: var(--fs-body); text-align: right;
}
/* Fields and their buttons share a baseline by sitting in the same
   align-items:center flex row at the same padding — the second thing
   wrong in settings.png. */
.settings .row > .field { flex: 1; min-width: 0; }
.settings .row > select.field { flex: 0 0 150px; }
.settings .row > input#f-category { flex: 0 0 90px; }

.settings .sub-hint {
  color: var(--text-faint); font-size: var(--fs-muted);
  margin: 6px 0 0 128px;
}
.settings .inline-hint { color: var(--text-faint); font-size: var(--fs-muted); }

/* "Connected" as a status PILL, not an oversized button. */
.pill {
  display: inline-flex; align-items: center; gap: 7px; flex: none;
  font-size: var(--fs-muted); color: var(--text-faint);
  padding: 3px 10px 3px 8px; border-radius: 999px;
  background: #101216; border: 1px solid var(--field-border);
}
.led {
  width: 7px; height: 7px; border-radius: 50%; flex: none;
  background: currentColor; box-shadow: 0 0 9px currentColor;
}
.pill.ok   { color: var(--ok); }
.pill.warn { color: var(--warn); }
.pill.err  { color: var(--err); }
.pill.idle { color: var(--text-faint); }
.pill.warn .led { animation: pulse 1.1s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }

.radio {
  display: flex; align-items: center; gap: 9px;
  margin-bottom: 8px; cursor: pointer;
}
.radio:last-child { margin-bottom: 0; }
.radio input { position: absolute; opacity: 0; width: 0; height: 0; }
.ring {
  width: 15px; height: 15px; border-radius: 50%;
  border: 1.5px solid #3a3f49; flex: none;
}
.radio input:checked + .ring {
  border: 4.5px solid var(--brand); background: var(--field);
  box-shadow: 0 0 10px rgba(255, 90, 77, .5);
}
.radio input:focus-visible + .ring { box-shadow: 0 0 0 2px rgba(255, 90, 77, .3); }

/* A masked webhook must not be rendered in a proportional font: the mask
   is what is on screen, and monospace keeps its length honest. */
#f-webhook { font-family: var(--mono); font-size: var(--fs-mono); letter-spacing: .04em; }
#f-webhook[type="text"] { letter-spacing: 0; }
.settings .toggle { flex: none; min-width: 62px; }

.settings-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 4px 0 8px;
}
```

- [ ] **Step 2: Fill `#route-settings` in `web/index.html`, and load `settings.js`**

Replace `<div class="route" id="route-settings"></div>` with:

```html
  <div class="route" id="route-settings">
    <div class="settings">

      <section class="card">
        <h2>Google account</h2>
        <div class="row">
          <span class="lab">Status</span>
          <span class="pill idle" id="auth-pill"><span class="led"></span><span id="auth-text">Checking&hellip;</span></span>
          <span style="flex:1"></span>
          <button class="btn" id="btn-auth">Sign in with Google</button>
        </div>
        <p class="hint">
          Google hasn't verified this app yet, so the sign-in page shows a warning.
          Click Advanced, then <b style="color:#c8cdd6">Go to FlyGD Wingman (unsafe)</b> to continue.
        </p>
        <p class="hint">
          Videos are uploaded to YouTube and are subject to the YouTube Terms of Service:
          <span class="linkish" id="tos-link">https://www.youtube.com/t/terms</span>
        </p>
      </section>

      <section class="card">
        <h2>Upload defaults</h2>
        <div class="row">
          <span class="lab">Privacy</span>
          <select class="field" id="f-privacy">
            <option value="private">private</option>
            <option value="unlisted">unlisted</option>
            <option value="public">public</option>
          </select>
        </div>
        <div class="row">
          <span class="lab">Category ID</span>
          <input class="field" id="f-category" type="text" inputmode="numeric"
                 spellcheck="false">
          <span class="inline-hint">(20 = Gaming)</span>
        </div>
      </section>

      <section class="card">
        <h2>When a recording finishes</h2>
        <label class="radio">
          <input type="radio" name="notify" value="toast"><span class="ring"></span>
          Show a tray notification
          <span class="inline-hint">&mdash; recommended</span>
        </label>
        <label class="radio">
          <input type="radio" name="notify" value="popup"><span class="ring"></span>
          Open the uploader window immediately
        </label>
      </section>

      <section class="card">
        <h2>Folders</h2>
        <div class="row">
          <span class="lab">Recordings</span>
          <input class="field mono" id="f-recdir" type="text" spellcheck="false">
          <button class="btn" data-browse="recording">Browse&hellip;</button>
          <button class="btn" data-detect="recording">Detect</button>
        </div>
        <div class="row">
          <span class="lab">EVE gamelogs</span>
          <input class="field mono" id="f-gamelogs" type="text" spellcheck="false">
          <button class="btn" data-browse="gamelogs">Browse&hellip;</button>
          <button class="btn" data-detect="gamelogs">Detect</button>
        </div>
        <p class="sub-hint" id="detect-note">
          Detect reads the recording folder from OBS's own config, and the gamelogs
          folder from your EVE Online documents folder.
        </p>
      </section>

      <section class="card">
        <h2>Discord (combat logs)</h2>
        <div class="row">
          <span class="lab">Webhook URL</span>
          <!-- Masked by default. A webhook URL is a credential: anyone
               holding it can post to the channel, and this screen is open
               on a second monitor while streaming and screenshotted when
               users help each other configure it. -->
          <input class="field" id="f-webhook" type="password" spellcheck="false"
                 autocomplete="off">
          <button class="btn toggle" id="btn-webhook-show"
                  aria-pressed="false">Show</button>
        </div>
        <p class="sub-hint" id="webhook-status">not configured</p>
      </section>

      <div class="settings-foot">
        <button class="btn" id="btn-settings-cancel">Cancel</button>
        <button class="btn acc" id="btn-settings-save">Save</button>
      </div>

    </div>
  </div>
```

Then add the script tag, immediately after `<script src="panel.js"></script>`:

```html
  <script src="settings.js"></script>
```

- [ ] **Step 3: Create `web/settings.js`**

```js
/* The Settings route.
 *
 * Rendered in the same window as a route rather than a separate OS
 * window, which removes a whole second toplevel's worth of lifecycle
 * code. The OAuth flow becomes an ordinary worker plus onAuthState
 * pushes, with no polling loop at all.
 */
(function () {
  'use strict';
  var WM = window.WM;

  var YOUTUBE_TOS_URL = 'https://www.youtube.com/t/terms';

  var current = {};    // last settings dict from Python
  var detected = {};   // detected-folder suggestions from the same payload
  // Fetched once from Python rather than duplicated here: ui/copy.py's
  // AUTH_STATES is the tested source, and a second table in JavaScript
  // would drift the moment a label changes.
  var authLabels = {};
  var pendingAuth = null;

  WM.send('auth_labels').then(function (table) {
    authLabels = table || {};
    if (pendingAuth) { renderAuth(pendingAuth); pendingAuth = null; }
  });

  // ---- fields ---------------------------------------------------------
  function setNotify(mode) {
    var inputs = document.querySelectorAll('input[name="notify"]');
    Array.prototype.forEach.call(inputs, function (input) {
      input.checked = (input.value === mode);
    });
  }

  function notifyValue() {
    var picked = document.querySelector('input[name="notify"]:checked');
    return picked ? picked.value : 'toast';
  }

  function render(payload) {
    var s = payload.settings || {};
    var d = payload.detected || {};
    current = s;
    detected = d;
    WM.el('f-privacy').value = s.privacy || 'unlisted';
    WM.el('f-category').value = s.category || '20';
    setNotify(s.notify_mode || 'toast');
    WM.el('f-recdir').value = s.recording_dir || '';
    WM.el('f-gamelogs').value = s.gamelogs_dir || '';
    // The input holds the REAL value and the browser draws the mask, so
    // the mask can never be written back over the stored webhook — the
    // failure mode a hand-rolled bullet string invites.
    WM.el('f-webhook').value = s.discord_webhook || '';
    // webhook_status() is a pure Python function with its own test and is
    // the only description of what is stored; discord.describe omits the
    // token by construction. TOP-LEVEL key, and never reconstructed here.
    WM.el('webhook-status').textContent = payload.webhook_status
      || (s.discord_webhook ? '' : 'not configured');
    // Detect is always offered, but say so when there is nothing to find.
    WM.el('detect-note').textContent = (d.recording || d.gamelogs)
      ? 'Detect reads the recording folder from OBS\u2019s own config, and the '
        + 'gamelogs folder from your EVE Online documents folder.'
      : 'Detect found neither folder automatically \u2014 use Browse to pick '
        + 'them yourself.';
  }

  // Task 12 owns the onSettings handler (it needs privacy/category for
  // start_upload) and re-dispatches the payload, so both modules consume
  // one push without either owning it exclusively.
  document.addEventListener('wm:settings', function (ev) {
    render(ev.detail || {});
  });

  // ---- folder pickers -------------------------------------------------
  // Both folders carry BOTH actions: Settings has distinct Detect paths
  // for the recording directory (via OBS's own config) and the EVE
  // gamelogs directory. `which` matches Api.pick_folder/detect_folder.
  var TARGET_FIELD = { recording: 'f-recdir', gamelogs: 'f-gamelogs' };

  function applyFolder(which, path) {
    if (!path) return;   // a cancelled dialog is also a valid result
    var field = WM.el(TARGET_FIELD[which]);
    if (field) field.value = path;
  }

  document.querySelectorAll('[data-browse]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var which = btn.dataset.browse;
      WM.send('pick_folder', which).then(function (path) {
        applyFolder(which, path);
      });
    });
  });

  document.querySelectorAll('[data-detect]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var which = btn.dataset.detect;
      // The field's LIVE value, not the stored setting: a detection that
      // agrees with what the user has already typed is reported as
      // agreement rather than silently rewriting the field.
      var field = WM.el(TARGET_FIELD[which]);
      WM.send('detect_folder', which, field ? field.value : '')
        .then(function (path) { applyFolder(which, path); });
    });
  });

  // ---- webhook mask ---------------------------------------------------
  var webhook = WM.el('f-webhook');
  var showBtn = WM.el('btn-webhook-show');

  showBtn.addEventListener('click', function () {
    var revealed = webhook.type === 'text';
    webhook.type = revealed ? 'password' : 'text';
    showBtn.textContent = revealed ? 'Show' : 'Hide';
    showBtn.setAttribute('aria-pressed', String(!revealed));
  });

  function remask() {
    webhook.type = 'password';
    showBtn.textContent = 'Show';
    showBtn.setAttribute('aria-pressed', 'false');
  }

  // Leaving the screen re-masks, so a revealed credential cannot be left
  // on screen by navigating away and back.
  document.addEventListener('wm:route', function (ev) {
    if (ev.detail !== 'settings') remask();
  });

  // ---- Google account -------------------------------------------------
  function renderAuth(p) {
    var spec = authLabels[p.state] || authLabels.disconnected;
    if (!spec) { pendingAuth = p; return; }   // labels not fetched yet
    var btn = WM.el('btn-auth');
    btn.textContent = spec.label;
    btn.disabled = !spec.enabled;
    var pill = WM.el('auth-pill');
    var tone = { connected: 'ok', connecting: 'warn', revoking: 'warn' };
    pill.className = 'pill ' + (tone[p.state] || 'idle');
    // The message is Python's string when it sends one; the table's is the
    // fallback.
    WM.el('auth-text').textContent = p.message || spec.message;
  }

  WM.handle('onAuthState', renderAuth);

  WM.el('btn-auth').addEventListener('click', function () {
    // No optimistic local disable: Python answers with a `connecting`
    // push, and one source of truth for the button is what keeps the pill
    // and the button two views of ONE state.
    WM.send('connect_google');
  });

  WM.el('tos-link').addEventListener('click', function () {
    window.open(YOUTUBE_TOS_URL, '_blank');
  });

  // ---- save / cancel --------------------------------------------------
  function collect() {
    return {
      privacy: WM.el('f-privacy').value,
      category: WM.el('f-category').value.trim(),
      notify_mode: notifyValue(),
      recording_dir: WM.el('f-recdir').value.trim() || null,
      gamelogs_dir: WM.el('f-gamelogs').value.trim() || null,
      // The real value, never the mask.
      discord_webhook: webhook.value.trim(),
      // Carried through untouched: settings.save projects onto DEFAULTS'
      // keys, so anything omitted here is dropped on every write.
      channel_id: current.channel_id || '',
      channel_title: current.channel_title || ''
    };
  }

  WM.el('btn-settings-save').addEventListener('click', function () {
    // save_settings rebinds the live watcher when recording_dir changes;
    // persisting the setting alone leaves the watcher on the old folder.
    // That is Python's job, not the page's. It returns false when it
    // refused, and the form stays open so the edits are not lost.
    WM.send('save_settings', collect()).then(function (ok) {
      if (ok === false) return;
      remask();
      WM.route('main');
    });
  });

  WM.el('btn-settings-cancel').addEventListener('click', function () {
    render({ settings: current, detected: detected,
             webhook_status: WM.el('webhook-status').textContent });
    remask();
    WM.route('main');
  });
}());
```

- [ ] **Step 4: Verify the layout, the aligned label column, and the shared baseline**

Run:
```bash
python3 -m http.server 8765 --directory obs_youtube_uploader/web &
cmd.exe /c start msedge "http://localhost:8765/index.html?dev=1"
```
Then click the gear. Expected:
1. The title-bar sub-label reads `SETTINGS`, the list and panel are gone, and the status strip is still visible — a route in the same window, not a second window.
2. Five cards: `GOOGLE ACCOUNT`, `UPLOAD DEFAULTS`, `WHEN A RECORDING FINISHES`, `FOLDERS`, `DISCORD (COMBAT LOGS)`.
3. Every label (`Status`, `Privacy`, `Category ID`, `Recordings`, `EVE gamelogs`, `Webhook URL`) is right-aligned and ends at the **same** x position across all five cards.
4. In each folder row, the field and its `Browse…` and `Detect` buttons are vertically centred on one another with aligned top and bottom edges. Same for the webhook field and its `Show` button.
5. Both folder rows carry **both** `Browse…` and `Detect`.
6. `Save` is the only brand-accent control on this screen.

- [ ] **Step 5: Verify field population and the folder pickers**

1. Privacy `unlisted`, Category `20` with `(20 = Gaming)` beside it, `Show a tray notification` filled with a red ring.
2. Recordings `D:\Videos` and EVE gamelogs `C:\Users\tng\Documents\EVE\logs\Gamelogs`, both monospace.
3. Click `Browse…` on Recordings: logs `DEV api.pick_folder( ["recording"] )` and the field becomes `D:\Videos\recording`. On gamelogs: `pick_folder( ["gamelogs"] )`, and only that field changes.
4. Click `Detect` on each row: logs `detect_folder( ["recording", "D:\\Videos"] )` and `detect_folder( ["gamelogs", "C:\\..."] )` — **the field's live value is passed as the second argument.** Neither field changes, because the harness stub returns `null`.
5. Run `DEV.settings({recording_dir: null, gamelogs_dir: null})`, reopen Settings: both folder fields are empty and the note still describes Detect.

- [ ] **Step 6: Verify the webhook is masked and the Show toggle round-trips**

1. The Webhook field shows dots, **not** the URL. Nothing on screen shows the token.
2. `WM.el('f-webhook').value` in the console returns the full real URL — the input holds the real value and the browser draws the mask, so a save cannot write the mask back.
3. `Show` reveals it in monospace and the button becomes `Hide` with `aria-pressed="true"`; clicking again re-masks.
4. Click `Show`, leave the route via the gear, return: the field is **masked again** and the button reads `Show`.
5. `DEV.settings({discord_webhook: ''}, 'not configured')` — the field is empty and the line reads `not configured`.
6. `DEV.settings({}, 'webhook 1538615213203656754 in #combat-logs')` — the line reads exactly that, the field stays masked, and no token appears.

- [ ] **Step 7: Verify all four auth states and the transient-state lockout**

In the console, with Settings open:
1. `DEV.authState('disconnected', null)` — grey pill `Not connected`, button live reading `Sign in with Google`.
2. `DEV.authState('connecting', null)` — amber pulsing pill `Waiting for browser…`, button reads `Connecting…` and is **greyed**. Clicking it repeatedly logs nothing.
3. `DEV.authState('connected', null)` — green glowing pill `Connected`, button reads `Switch account`.
4. `DEV.authState('revoking', null)` — amber pulsing pill `Signing out…`, button disabled.
5. `DEV.authState('connected', 'Connected as tng@example.com')` — the pill text becomes Python's message; the button still reads `Switch account`.
6. `DEV.authState('nonsense', null)` — falls back to an enabled `Sign in with Google` rather than a dead button.
7. Every label above came from `auth_labels()` — confirm the console logged that call once at load, and that no label strings appear in `settings.js`.

- [ ] **Step 8: Verify save and cancel**

1. Change Privacy to `public`, Category to `24`, select `Open the uploader window immediately`, click `Save`. The console logs `save_settings` with `privacy:"public"`, `category:"24"`, `notify_mode:"popup"`, the **real** webhook URL rather than dots, and `channel_id`/`channel_title` carried through so `settings.save`'s projection onto `DEFAULTS` does not drop them. The route returns to the list.
2. Reopen Settings, change Privacy to `private`, click `Cancel`: nothing is logged, the route returns, and reopening shows the previously rendered values.
3. Clear the Recordings field and click `Save`: the payload carries `recording_dir: null`, not `""`.

- [ ] **Step 9: Commit**

```bash
git add obs_youtube_uploader/web/settings.js obs_youtube_uploader/web/index.html \
        obs_youtube_uploader/web/style.css
git commit -m "web: settings route"
```

- [ ] **Step 10: Add the first-run route to `web/index.html` and `web/style.css`**

This is the deliberate behaviour change the spec records as Risk 6: `create_file_dialog` is a method on a window, so no folder dialog can exist before `webview.start()`. The pre-window OS dialog becomes an in-app screen.

Add a third route container immediately after `#route-settings`:

```html
  <div class="route" id="route-firstrun">
    <div class="firstrun">
      <h1>Choose your recording folder</h1>
      <p class="firstrun-body">
        Wingman watches one folder for new OBS recordings. Point it at the
        folder OBS saves to &mdash; you can change this later in Settings.
      </p>
      <div class="row">
        <input class="field mono" id="f-firstrun-dir" type="text"
               spellcheck="false" placeholder="No folder chosen yet">
        <button class="btn" id="btn-firstrun-browse">Browse&hellip;</button>
        <button class="btn" id="btn-firstrun-detect">Detect</button>
      </div>
      <p class="firstrun-note" id="firstrun-note">
        Detect reads the folder from OBS&rsquo;s own configuration.
      </p>
      <div class="firstrun-actions">
        <button class="btn acc" id="btn-firstrun-continue" disabled>Continue</button>
      </div>
    </div>
  </div>
```

Append to `style.css`:

```css
/* ====================== first-run route ============================== */
#route-firstrun { align-items: center; justify-content: center; padding: 24px; }

.firstrun {
  width: min(560px, 100%);
  background: var(--panel); border: 1px solid var(--panel-border);
  border-radius: var(--radius); padding: 26px 28px;
}
.firstrun h1 { margin-bottom: 10px; }
.firstrun-body {
  color: var(--text-dim); line-height: 1.55; margin-bottom: 18px;
}
.firstrun-note {
  color: var(--text-faint); font-size: var(--fs-muted); margin-top: 10px;
}
.firstrun-actions { display: flex; justify-content: flex-end; margin-top: 20px; }
```

Then add `<script src="firstrun.js"></script>` after `settings.js`, and extend `WM.route` in `app.js` so all three routes are mutually exclusive:

```js
  WM.route = function (name) {
    var routes = { main: 'route-main', settings: 'route-settings',
                   firstrun: 'route-firstrun' };
    var labels = { main: 'Uploader', settings: 'Settings',
                   firstrun: 'Setup' };
    Object.keys(routes).forEach(function (key) {
      WM.el(routes[key]).classList.toggle('active', key === name);
    });
    WM.el('route-label').textContent = labels[name] || 'Uploader';
    WM.el('btn-settings').classList.toggle('active', name === 'settings');
    // First run is not dismissable: the app cannot watch a folder it does
    // not have, so the gear is hidden rather than merely inert.
    WM.el('btn-settings').hidden = (name === 'firstrun');
    WM.current_route = name;
    document.dispatchEvent(new CustomEvent('wm:route', { detail: name }));
  };
```

- [ ] **Step 11: Create `web/firstrun.js`**

```js
/* The first-run recording-folder screen.
 *
 * A deliberate behaviour change, not a port: pywebview's
 * create_file_dialog is a method on a window, so the pre-window OS dialog
 * the Tk build showed cannot exist here. Python signals this state by
 * pushing onFirstRun; the page cannot infer it, because an empty list and
 * an unconfigured folder look identical from here.
 */
(function () {
  'use strict';
  var WM = window.WM;

  var chosen = '';

  function setChosen(path) {
    chosen = path || '';
    WM.el('f-firstrun-dir').value = chosen;
    WM.el('btn-firstrun-continue').disabled = !chosen;
  }

  WM.el('btn-firstrun-browse').addEventListener('click', function () {
    WM.send('pick_folder', 'recording').then(setChosen);
  });

  WM.el('btn-firstrun-detect').addEventListener('click', function () {
    WM.send('detect_folder', 'recording', chosen).then(function (path) {
      if (path) setChosen(path);
    });
  });

  // Typing is allowed as well as picking: a user who knows the path should
  // not have to walk a tree to it.
  WM.el('f-firstrun-dir').addEventListener('input', function (ev) {
    chosen = ev.target.value.trim();
    WM.el('btn-firstrun-continue').disabled = !chosen;
  });

  WM.el('btn-firstrun-continue').addEventListener('click', function () {
    // Python validates, persists, starts the watcher, and pushes onRows.
    // It returns false if the folder is not usable, in which case we stay
    // put rather than dropping the user into an empty list.
    WM.send('set_recording_dir', chosen).then(function (ok) {
      if (ok !== false) WM.route('main');
    });
  });

  WM.handle('onFirstRun', function () {
    setChosen('');
    WM.route('firstrun');
  });
}());
```

Register `onFirstRun` in `app.js`'s `WM.HANDLERS` array, alongside the other handlers.

- [ ] **Step 12: Add `set_recording_dir` to the bridge**

In `obs_youtube_uploader/ui/api.py`:

```python
    def set_recording_dir(self, path: str) -> bool:
        """Accept the first-run folder choice: persist it and start watching.

        Returns False when the folder is unusable, so the page keeps the
        first-run screen up rather than dropping the user into an empty
        list with no explanation of why.

        _on_recording_dir_ready is assigned by __main__ and is what actually
        creates the Watcher and starts the poll loop; the bridge does not
        own either.
        """
        folder = Path(str(path or "").strip())
        if not folder.is_dir():
            self._alert("warning", "Invalid folder",
                        f"{folder} is not a folder.")
            return False
        self._state.settings["recording_dir"] = str(folder)
        self._state.recording_dir = folder
        try:
            settings_mod.save(self._state.settings)
        except OSError as exc:
            self._alert("error", "Could not save settings",
                        f"Settings were not saved: {exc}")
            return False
        if self._on_recording_dir_ready is not None:
            self._on_recording_dir_ready(folder)
        self.list_rows()
        return True
```

Add `self._on_recording_dir_ready = None` to `Api.__init__`.

Append to `tests/test_api_settings.py`:

```python
def test_first_run_persists_the_folder_and_starts_the_watcher(monkeypatch, tmp_path):
    folder = tmp_path / "recordings"
    folder.mkdir()
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    started = []
    api._on_recording_dir_ready = started.append

    assert api.set_recording_dir(str(folder)) is True

    assert saved["recording_dir"] == str(folder)
    assert api._state.recording_dir == folder
    assert started == [folder], "the watcher was never started"


def test_first_run_refuses_a_folder_that_is_not_one(monkeypatch, tmp_path):
    """Returning False is what keeps the first-run screen up. Dropping the
    user into an empty list with no explanation is the failure mode."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    started = []
    api._on_recording_dir_ready = started.append

    assert api.set_recording_dir(str(tmp_path / "nope")) is False
    assert saved == {}
    assert started == []
    assert api._alert.titles() == ["Invalid folder"]
```

- [ ] **Step 13: Verify the first-run route**

Run the harness, then in the console: `window.onFirstRun({})`.

Expected:
1. The list and panel disappear, replaced by a centred card headed **Choose your recording folder**, and the title-bar sub-label reads `SETUP`.
2. **The gear is hidden** — first run is not dismissable, because the app cannot watch a folder it does not have.
3. `Continue` starts disabled. Clicking `Browse…` logs `pick_folder( ["recording"] )` and fills the field; `Continue` becomes enabled.
4. Typing a path by hand also enables `Continue`; clearing the field disables it again.
5. Clicking `Continue` logs `DEV api.set_recording_dir( ["D:\\Videos\\recording"] )` and the route returns to the list.
6. `Detect` logs `detect_folder( ["recording", "<field value>"] )`.

Add `set_recording_dir` to `dev.js`'s logged-method list so step 5 resolves.

- [ ] **Step 14: Commit**

```bash
git add obs_youtube_uploader/web/firstrun.js obs_youtube_uploader/web/index.html \
        obs_youtube_uploader/web/style.css obs_youtube_uploader/web/app.js \
        obs_youtube_uploader/web/dev.js obs_youtube_uploader/ui/api.py \
        tests/test_api_settings.py
git commit -m "web: first-run recording-folder route"
```

---

### Task 14: Window construction and lifecycle

**Files:**
- Create: `obs_youtube_uploader/ui/window.py`
- Test: `tests/test_window.py`

**Interfaces:**
- Consumes: `ui.api.Api` (Tasks 4–9); `obs_youtube_uploader/web/index.html` (Task 10)
- Produces: `create(api) -> "webview.Window"`, `run() -> None`; constants `TITLE`, `WIDTH`, `HEIGHT`, `BACKGROUND`, `GUI_BACKEND`; internals `_web_dir()`, `_screen_size()`, `_placement(width, height, metrics=_screen_size)`, `_silence_pywebview_logging()`

`create()` and `run()` import pywebview **inside the function body**, not at module scope. Two reasons, both load-bearing. First, Task 15's pre-flight must be able to fail and show its native message box *before* pywebview is loaded at all — a module-level import would run pywebview's import-time setup on a machine already determined to be unable to host it. Second, it is what lets `tests/test_window.py` inject a stub `webview` module and run headlessly on `ubuntu-latest`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_window.py
"""ui/window.py -- construction flags, placement, and the js_api guard.

No real pywebview here. window.py imports it lazily inside create()/run()
(see that module's docstring), which is what lets these tests inject a stub
module and run on a headless box with no WebView2 anywhere.
"""
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from obs_youtube_uploader.ui import window as window_mod
from obs_youtube_uploader.ui.api import Api


@pytest.fixture
def fake_webview(monkeypatch):
    """Stand in for the `webview` module and record what it was asked for."""
    calls = {}

    def create_window(title, url, **kwargs):
        calls["title"] = title
        calls["url"] = url
        calls["kwargs"] = kwargs
        calls["window"] = SimpleNamespace(label="the-window")
        return calls["window"]

    def start(**kwargs):
        calls["start_kwargs"] = kwargs

    monkeypatch.setitem(
        sys.modules, "webview",
        SimpleNamespace(create_window=create_window, start=start))
    return calls


def _bare_api():
    """An Api instance built without running __init__.

    Deliberate: this file tests the PUBLIC SURFACE that pywebview walks,
    which is a property of the class. Coupling it to whatever arguments the
    constructor happens to take would make the RecursionError guard below
    fail for an unrelated reason the day Api gains a parameter.
    """
    return Api.__new__(Api)


def test_the_window_is_frameless_with_drag_left_to_the_page(fake_webview):
    """easy_drag moves the whole window on any mousedown in the body, which
    would make every button, row, and text field drag the window instead of
    doing its job. The page marks its own title bar with
    `pywebview-drag-region` -- that is the entire drag surface."""
    window_mod.create(_bare_api())
    kwargs = fake_webview["kwargs"]
    assert kwargs["frameless"] is True
    assert kwargs["easy_drag"] is False


def test_the_window_is_given_an_explicit_position(fake_webview):
    """Frameless windows get no sensible default placement -- the spike's
    window opened somewhere not visible on the primary screen. x and y are
    not optional here."""
    window_mod.create(_bare_api())
    kwargs = fake_webview["kwargs"]
    assert isinstance(kwargs["x"], int)
    assert isinstance(kwargs["y"], int)


def test_the_native_background_matches_the_ground_token(fake_webview):
    """The native surface is painted before the first frame of HTML. If it
    does not match --bg, launch flashes white on a near-black design."""
    window_mod.create(_bare_api())
    assert fake_webview["kwargs"]["background_color"] == "#0c0d10"
    assert window_mod.BACKGROUND == "#0c0d10"


def test_the_window_loads_a_page_that_actually_exists(fake_webview):
    """PyInstaller exits 0 when a `datas` entry resolves to nothing, so a
    misresolved web/ shows up as a blank window rather than a build error.
    Asserting the file is really there is the cheap half of that guard."""
    window_mod.create(_bare_api())
    url = Path(fake_webview["url"])
    assert url.name == "index.html"
    assert url.exists()


def test_the_api_gets_the_window_after_construction(fake_webview):
    """create_window() needs js_api, and the window does not exist until it
    returns -- so the wiring is necessarily a second step."""
    api = _bare_api()
    window = window_mod.create(api)
    assert window is fake_webview["window"]
    assert api._window is window


def test_no_public_attribute_of_the_api_holds_the_window(fake_webview):
    """THE RecursionError guard, and the reason this test exists at all.

    pywebview builds its JS proxy by walking the js_api object's public
    attributes. A public attribute holding a webview.Window sends that walk
    into the WinForms native object, where Rectangle.Empty returns itself;
    it recurses until RecursionError terminates the process about eight
    seconds after launch, with no traceback a user would ever see.

    Every non-method attribute must be underscore-prefixed. Forever.
    """
    api = _bare_api()
    window_mod.create(api)

    assert all(name.startswith("_") for name in vars(api)), (
        f"public instance attribute on Api: {sorted(vars(api))}")
    for name in dir(api):
        if name.startswith("_"):
            continue
        assert callable(getattr(api, name)), (
            f"Api.{name} is public and is not a method; pywebview will walk it")


def test_run_pins_the_backend(fake_webview):
    """Autodetection silently falling back to another backend would make a
    passing run meaningless -- the whole design targets WebView2."""
    window_mod.run()
    assert fake_webview["start_kwargs"] == {"gui": "edgechromium"}


def test_run_silences_pywebviews_property_walk():
    """pywebview logs an unbounded property walk of native objects at DEBUG.
    Harmless in a windowed build; it would swamp the rotating log file."""
    log = logging.getLogger("pywebview")
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.StreamHandler())
    try:
        window_mod._silence_pywebview_logging()
        assert log.level == logging.WARNING
        assert log.handlers == []
        # propagate stays on: warnings and errors must still reach the
        # rotating file handler configure_logging() puts on the root logger.
        assert log.propagate is True
    finally:
        log.handlers = []
        log.setLevel(logging.NOTSET)


def test_placement_centres_the_window_on_the_screen():
    assert window_mod._placement(1000, 600, metrics=lambda: (1920, 1080)) == (460, 240)


def test_placement_never_goes_negative_on_a_small_screen():
    """A negative x on Windows is legal and puts the title bar off the left
    edge -- on a frameless window that means no way to drag it back."""
    assert window_mod._placement(1600, 1200, metrics=lambda: (1280, 720)) == (0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_window.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'obs_youtube_uploader.ui.window'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/ui/window.py
"""Window construction and lifecycle.

pywebview is imported lazily inside create() and run(), not at module
scope. Two reasons:

  * __main__ pre-flights the WebView2 runtime before touching pywebview at
    all. Importing it up here would run its import-time setup on a machine
    we have already decided cannot host a webview.
  * it lets tests inject a stub `webview` module, so this file's flags and
    placement are covered on a headless Linux box.

The flags below are not cosmetic. Every one of them was paid for by the
spike; see the comments at each.
"""
import logging
import sys
from pathlib import Path

TITLE = "FlyGD Wingman"

# Two panes plus a status strip. Wide enough that filename, date, size and
# length do not fight for the list's columns at 100% scaling.
WIDTH = 1040
HEIGHT = 680

# --bg from the token table. This paints the NATIVE surface, before the
# first frame of HTML exists; a mismatch here is a white flash on launch.
BACKGROUND = "#0c0d10"

# Pinned, never autodetected: a silent fallback to another backend would
# mean a "passing" run that proves nothing about the shipped product.
GUI_BACKEND = "edgechromium"


def _web_dir() -> Path:
    """Locate the bundled page, mirroring paths.icon_file()'s two cases.

    Frozen builds collect web/ at the bundle root via uploader.spec's
    `datas` entry; a source checkout has no such step and the real files
    live inside the package, next to ui/.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "web"
    return Path(__file__).resolve().parent.parent / "web"


def _screen_size() -> tuple[int, int]:
    """Primary screen size in pixels; a plausible default off-Windows.

    Guarded exactly as __main__.set_dpi_awareness() guards its Win32 call:
    off-Windows this is development only, and a wrong-but-sane number beats
    an import error at startup.
    """
    if sys.platform != "win32":
        return (1920, 1080)
    import ctypes
    try:
        user32 = ctypes.windll.user32
        return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    except (AttributeError, OSError):
        return (1920, 1080)


def _placement(width: int, height: int, metrics=_screen_size) -> tuple[int, int]:
    """Centre the window, clamped at the top-left corner.

    Frameless windows get NO sensible default placement from pywebview --
    the spike's opened somewhere not visible on the primary screen -- so
    x/y are mandatory, not a nicety.

    The clamp matters more than centring does: a negative x is legal on
    Windows and would put the custom title bar off the left edge, and a
    frameless window with no reachable drag region cannot be moved back.
    """
    screen_w, screen_h = metrics()
    return (max(0, (screen_w - width) // 2), max(0, (screen_h - height) // 2))


def _silence_pywebview_logging() -> None:
    """Stop pywebview writing its native-object property walk to stderr.

    It logs an unbounded walk of WinForms objects at DEBUG. Invisible in a
    windowed build, but stderr is redirected into the log file in some
    launch paths and this would swamp it.

    propagate is left ON deliberately: real warnings and errors must still
    reach the rotating file handler configure_logging() attached to the
    root logger. Only pywebview's own handlers and its DEBUG chatter go.
    """
    log = logging.getLogger("pywebview")
    log.setLevel(logging.WARNING)
    for handler in list(log.handlers):
        log.removeHandler(handler)
    log.propagate = True


def create(api) -> "webview.Window":
    """Build the main window and hand *api* its back-reference.

    The `api._window = window` assignment MUST use the underscore name and
    MUST stay a separate step:

      * separate, because create_window() needs js_api before a window
        object exists to assign;
      * underscore, because pywebview builds its JS proxy by walking the
        js_api object's PUBLIC attributes. A public attribute holding a
        webview.Window sends that walk into WinForms, where
        Rectangle.Empty returns itself, and it recurses until
        RecursionError kills the process about eight seconds after launch.

    tests/test_window.py asserts that invariant. Do not relax it.
    """
    import webview

    x, y = _placement(WIDTH, HEIGHT)
    window = webview.create_window(
        TITLE,
        str(_web_dir() / "index.html"),
        js_api=api,
        width=WIDTH,
        height=HEIGHT,
        x=x,
        y=y,
        frameless=True,
        # easy_drag would move the window on any mousedown in the body,
        # so every button, row, and text field would drag it. The page
        # marks its own title bar with `pywebview-drag-region`; that is
        # the whole drag surface, by design.
        easy_drag=False,
        background_color=BACKGROUND,
    )
    api._window = window
    return window


def run() -> None:
    """Hand the main thread to pywebview. Returns when the window is destroyed.

    Nothing this returns can be trusted as a success signal: when the
    WebView2 runtime is missing, pywebview logs the failure, start()
    returns normally, and the process exits 0. That is why __main__
    pre-flights the runtime before calling this.
    """
    _silence_pywebview_logging()
    import webview

    webview.start(gui=GUI_BACKEND)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_window.py -v`
Expected: PASS. If `test_the_window_loads_a_page_that_actually_exists` fails, `_web_dir()` and the location Task 10 wrote `index.html` to disagree — fix `_web_dir()`, not the test.

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/ui/window.py tests/test_window.py
git commit -m "Add ui/window.py: frameless window construction and lifecycle"
```

---

### Task 15: Rewrite `__main__.py` onto the webview lifecycle

**Files:**
- Modify: `obs_youtube_uploader/__main__.py`
- Modify: `obs_youtube_uploader/paths.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_app.py`
- Test: `tests/test_poll_tick.py`, `tests/test_paths.py`

**Interfaces:**
- Consumes: `ui.preflight.require_webview2()` (Task 1); `ui.window.create(api)`, `ui.window.run()` (Task 14); `ui.scheduler.Scheduler` (Task 5); `ui.api.Api(state)`, `AppState`, `Api.list_rows(preselect=None)`, `Api._busy()`, `Api._state`, `Api._watcher`, `Api.refresh_auth()` (Tasks 4–9)
- Produces: `poll_tick(w, api, icon, window, state: PollState) -> None`, `PollState`, `notify(icon, message) -> None`, `resolve_recording_dir(cfg) -> Path | None` (the `ask` parameter is gone), `main() -> int`, `EXIT_NO_WEBVIEW2`
- Removed: `tk_scaling_for()`, `get_system_dpi()` — Tk's `scaling` has no counterpart in WebView2, which reads system DPI itself. `set_dpi_awareness()` **stays**: WebView2 renders blurry in a DPI-unaware process.

> **Behaviour change, called out rather than buried.** First-run
> recording-folder selection moves from a pre-window OS dialog to an in-app
> screen. `create_file_dialog` is a method on a window, so no dialog can exist
> before `webview.start()`. `resolve_recording_dir()` loses its `ask` fallback
> and returns `None`; the page renders its first-run route and calls
> `pick_folder`. Existing installations have the setting persisted and never
> see it.

- [ ] **Step 1: Move `resolve_binary` out of the doomed module**

`main()` below needs it to populate `AppState.ffmpeg_bin` / `ffprobe_bin`, and it currently lives in `app.py`, which Task 16 deletes. It is pure binary resolution — `paths.bundle_dir()` plus `shutil.which` — and `paths.py` already refers to it as a sibling concern in two comments, so that is its home.

Cut `resolve_binary` from `obs_youtube_uploader/app.py` **verbatim, docstring included**, and paste it into `obs_youtube_uploader/paths.py` below `bundle_dir()`. Add `import shutil` and `import sys` to `paths.py` if absent. Then in `app.py`, so the Tk UI keeps working until Task 16 removes it:

```python
# Re-exported: resolve_binary moved to paths.py ahead of this module's
# deletion, because __main__ needs it and this file will not exist.
from .paths import resolve_binary  # noqa: F401
```

Append to `tests/test_paths.py`:

```python
def test_resolve_binary_prefers_the_bundled_copy(tmp_path, monkeypatch):
    """The frozen layout: bundle_dir()/bin/<name>.exe."""
    from obs_youtube_uploader import paths as paths_mod

    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.setattr(paths_mod, "bundle_dir", lambda: tmp_path)

    assert paths_mod.resolve_binary("ffmpeg") == str(binaries / "ffmpeg.exe")


def test_resolve_binary_finds_the_source_checkout_copy(tmp_path, monkeypatch):
    """packaging/fetch_ffmpeg.py writes to packaging/bin, not <repo>/bin.
    Without this lookup, running from source silently falls back to PATH
    and ignores the ffmpeg the build script just fetched."""
    from obs_youtube_uploader import paths as paths_mod

    packaging_bin = tmp_path / "packaging" / "bin"
    packaging_bin.mkdir(parents=True)
    (packaging_bin / "ffprobe.exe").write_bytes(b"")
    monkeypatch.setattr(paths_mod, "bundle_dir", lambda: tmp_path)
    monkeypatch.delattr(paths_mod.sys, "_MEIPASS", raising=False)

    assert paths_mod.resolve_binary("ffprobe") == str(packaging_bin / "ffprobe.exe")


def test_resolve_binary_falls_back_to_path(tmp_path, monkeypatch):
    from obs_youtube_uploader import paths as paths_mod

    monkeypatch.setattr(paths_mod, "bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(paths_mod.shutil, "which", lambda name: "/usr/bin/" + name)

    assert paths_mod.resolve_binary("ffmpeg") == "/usr/bin/ffmpeg"
```

Run: `pytest tests/test_paths.py -v`
Expected: PASS. Then `python -c "from obs_youtube_uploader import app; print(app.resolve_binary)"` still prints a bound function.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_poll_tick.py
"""The watcher tick, which no longer has a Tk event loop under it.

Under Tk this was a closure over root.after with no harness at all. It is a
module-level function now precisely so the three things that were only ever
verified by hand -- the deferred-refresh flag, the notify_mode branch, and
the one-shot failure notification -- have tests.
"""
from pathlib import Path

import pytest

from obs_youtube_uploader.__main__ import (
    FAILURE_NOTIFY_THRESHOLD, PollState, poll_tick,
)


class _FakeIcon:
    def __init__(self, exc=None):
        self.notifications = []
        self._exc = exc

    def notify(self, message, title):
        if self._exc is not None:
            raise self._exc
        self.notifications.append((message, title))


class _FakeState:
    def __init__(self, notify_mode):
        self.settings = {"notify_mode": notify_mode}


class _FakeApi:
    def __init__(self, uploading=False, notify_mode="toast"):
        self._state = _FakeState(notify_mode)
        self._uploading = uploading
        self.rows_calls = []

    def _busy(self):
        return self._uploading

    def list_rows(self, preselect=None):
        self.rows_calls.append(preselect)


class _FakeWindow:
    def __init__(self):
        self.shown = 0

    def show(self):
        self.shown += 1


class _FakeWatcher:
    def __init__(self, ready=(), exc=None):
        self._ready = list(ready)
        self._exc = exc

    def poll_once(self):
        if self._exc is not None:
            raise self._exc
        return self._ready


def test_new_recordings_refresh_the_list_and_toast():
    api, icon, window = _FakeApi(), _FakeIcon(), _FakeWindow()
    state = PollState()

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, state)

    # A set of Path, matching RowSnapshot.rebuild's contract -- not strings.
    assert api.rows_calls == [{Path("a.mkv")}]
    assert icon.notifications == [
        ("1 new recording(s) ready to upload", "FlyGD Wingman")]
    assert window.shown == 0


def test_popup_mode_raises_the_window_instead_of_toasting():
    api = _FakeApi(notify_mode="popup")
    icon, window = _FakeIcon(), _FakeWindow()

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, PollState())

    assert window.shown == 1
    assert icon.notifications == []


def test_notify_mode_is_read_live_not_snapshotted():
    """Settings is a route in the same window now, so this can change
    mid-run. Reading a startup snapshot would need a restart to take."""
    api, icon, window = _FakeApi(notify_mode="toast"), _FakeIcon(), _FakeWindow()
    state = PollState()

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, state)
    api._state.settings["notify_mode"] = "popup"
    poll_tick(_FakeWatcher([Path("b.mkv")]), api, icon, window, state)

    assert window.shown == 1
    assert len(icon.notifications) == 1


def test_a_refresh_during_an_upload_is_deferred_not_dropped():
    """Rebuilding the list mid-upload would wipe the links and progress of
    the upload actually running -- but the user still gets told."""
    api = _FakeApi(uploading=True)
    icon, window = _FakeIcon(), _FakeWindow()
    state = PollState()

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, state)

    assert state.refresh_deferred is True
    assert api.rows_calls == []
    assert len(icon.notifications) == 1


def test_the_deferred_refresh_lands_on_a_later_empty_tick():
    api = _FakeApi(uploading=True)
    icon, window = _FakeIcon(), _FakeWindow()
    state = PollState()
    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, state)

    api._uploading = False
    poll_tick(_FakeWatcher([]), api, icon, window, state)

    assert state.refresh_deferred is False
    assert api.rows_calls == [None]


def test_a_failing_tick_notifies_exactly_once_at_the_threshold():
    """A single failure is indistinguishable from "nothing new", which is
    fine for a blip and not for an unreachable folder. One message, not a
    stream -- and none before the threshold."""
    api = _FakeApi()
    icon, window = _FakeIcon(), _FakeWindow()
    state = PollState()
    watcher = _FakeWatcher(exc=OSError("recording folder is gone"))

    for _ in range(FAILURE_NOTIFY_THRESHOLD + 3):
        poll_tick(watcher, api, icon, window, state)

    assert len(icon.notifications) == 1
    assert "trouble" in icon.notifications[0][0]


def test_the_failure_counter_resets_on_a_clean_tick():
    api, icon, window = _FakeApi(), _FakeIcon(), _FakeWindow()
    state = PollState()
    failing = _FakeWatcher(exc=OSError("blip"))
    for _ in range(FAILURE_NOTIFY_THRESHOLD - 1):
        poll_tick(failing, api, icon, window, state)

    poll_tick(_FakeWatcher([]), api, icon, window, state)

    assert state.consecutive_failures == 0
    assert icon.notifications == []


def test_a_tick_never_raises():
    """Scheduler reschedules regardless, but the counter and the one-shot
    notification live in here and would be lost with the exception."""
    api, window = _FakeApi(), _FakeWindow()
    icon = _FakeIcon(exc=RuntimeError("no toast service"))

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, PollState())


def test_a_first_run_with_no_folder_no_longer_asks(monkeypatch):
    """The ask fallback is GONE: create_file_dialog is a method on a window
    and no window exists this early. None means "render the first-run
    route", not "give up"."""
    from obs_youtube_uploader import __main__ as main_mod

    monkeypatch.setattr(main_mod.obsconfig, "find_recording_dir", lambda: None)
    assert main_mod.resolve_recording_dir({}) is None
    assert "ask" not in main_mod.resolve_recording_dir.__code__.co_varnames
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_poll_tick.py -v`
Expected: FAIL at collection with `ImportError: cannot import name 'PollState' from 'obs_youtube_uploader.__main__'`

- [ ] **Step 4: Write minimal implementation**

Replace `obs_youtube_uploader/__main__.py`'s body below the imports. `configure_logging`, `acquire_single_instance`, `set_dpi_awareness`, and `build_tray` are **carried over from the current file unchanged, comments included** — do not retype or reword them; copy them across verbatim. Everything below is new.

```python
"""Entry point: single-instance tray application."""
import logging
import sys
import threading
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import obsconfig, paths, settings as settings_mod, stitch, watcher
from .ui import api as api_mod, preflight, window as window_mod
from .ui.scheduler import Scheduler

logger = logging.getLogger(__name__)

MUTEX_NAME = "Global\\OBSYouTubeUploader"
POLL_SECONDS = 3.0
FAILURE_NOTIFY_THRESHOLD = 5  # ~15s of consecutive poll failures at POLL_SECONDS

# Exit code for "the WebView2 runtime is not usable". Non-zero on purpose:
# pywebview's own behaviour in that situation is to log, return from
# start(), and exit 0, which is a silent no-op for the user and a false
# success for anything watching the process.
EXIT_NO_WEBVIEW2 = 2


# --- configure_logging(), acquire_single_instance(), set_dpi_awareness(),
# --- and build_tray() are carried over from 2.2.0 VERBATIM, comments
# --- included.
#
# set_dpi_awareness() stays despite Tk being gone: WebView2 renders blurry
# in a DPI-unaware process, so the call is still doing its job.
#
# get_system_dpi() and tk_scaling_for() are DELETED. `tk scaling` has no
# counterpart here -- WebView2 reads system DPI itself and CSS pixels
# scale with it.


def resolve_recording_dir(cfg: dict) -> Path | None:
    """Stored setting, then OBS's own config. No third option.

    The `ask` fallback is gone, and this is the one deliberate behaviour
    change in the replatform. pywebview's create_file_dialog is a method on
    a window, so no dialog can exist before webview.start() -- there is
    nothing to parent it to and nothing to run its modal loop. Returning
    None now means "the page must render its first-run route", which calls
    pick_folder once a window does exist.

    Existing installations have recording_dir persisted and never reach it.
    """
    stored = cfg.get("recording_dir")
    if stored and Path(stored).is_dir():
        return Path(stored)
    detected = obsconfig.find_recording_dir()
    if detected and detected.is_dir():
        return detected
    return None


def notify(icon, message: str) -> None:
    """Best-effort tray notification.

    Swallowed on purpose: there may be no toast service, notifications may
    be disabled by policy, or the shell may simply refuse. None of that is
    a reason to break a watcher tick.
    """
    try:
        icon.notify(message, "FlyGD Wingman")
    except Exception:
        pass


@dataclass
class PollState:
    """The two flags the tick carries between runs.

    A mutable object rather than nonlocals, so poll_tick can be a
    module-level function with a test harness. Under Tk this state lived in
    closure cells that nothing outside main() could reach.
    """
    consecutive_failures: int = 0
    refresh_deferred: bool = False


def poll_tick(w, api, icon, window, state: PollState) -> None:
    """One watcher tick. Runs on the Scheduler's thread, never the UI thread.

    Reaches the page only through the Api, which pushes; it never touches
    the DOM and never calls into pywebview except for window.show(), which
    spike Q6 proved is safe from a non-main thread.

    Must not raise. Scheduler reschedules regardless, but the failure
    counter and the one-shot "having trouble" notification live here and
    would be lost along with the exception.
    """
    try:
        ready = w.poll_once()
        uploading = api._busy()
        if ready:
            if uploading:
                # A full rebuild would wipe the links and progress of the
                # upload currently running. Defer it until that finishes --
                # but still tell the user recordings arrived.
                state.refresh_deferred = True
                notify(icon, f"{len(ready)} new recording(s) ready to upload")
            else:
                # A set of Path: RowSnapshot.rebuild matches preselect
                # against info.path, so strings would never match.
                api.list_rows(preselect=set(ready))
                # Live settings, not a snapshot taken at startup: Settings is
                # a route in this same window now and can change mid-run.
                if api._state.settings.get("notify_mode", "toast") == "popup":
                    window.show()
                else:
                    notify(icon, f"{len(ready)} new recording(s) ready to upload")
                state.refresh_deferred = False
        elif state.refresh_deferred and not uploading:
            # The upload that blocked the deferred rebuild has since
            # finished; catch the list up even though this tick found
            # nothing new.
            api.list_rows()
            state.refresh_deferred = False
        state.consecutive_failures = 0
    except Exception:
        # A single failure looks identical to "nothing new to upload," which
        # is fine for a blip but not for a persistent problem (unreachable
        # folder, permissions, a repeatedly failing seen-file write). Always
        # log it, and after enough consecutive failures surface exactly one
        # notification. The counter resets on any clean tick, so a long
        # outage produces one message rather than a stream.
        logger.warning("Poll tick failed", exc_info=True)
        state.consecutive_failures += 1
        if state.consecutive_failures == FAILURE_NOTIFY_THRESHOLD:
            notify(icon, "The recording watcher is having trouble — check the log")


def main() -> int:
    set_dpi_awareness()
    handle = acquire_single_instance()
    if handle is None:
        return 0  # Another instance owns the tray; nothing to do.

    paths.ensure_dirs()
    configure_logging()
    stitch.sweep_orphans(paths.tmp_dir())
    cfg = settings_mod.load()

    # BEFORE anything touches pywebview. When the runtime is absent,
    # pywebview logs the failure, webview.start() returns normally, and the
    # process exits 0 -- no window, no error, no crash dialog, and a
    # success exit code, with no console in a windowed build to show the
    # diagnostic. This check is the only thing standing between that and a
    # user who thinks the app is broken for no reason.
    if not preflight.require_webview2():
        return EXIT_NO_WEBVIEW2

    rec_dir = resolve_recording_dir(cfg)
    state = api_mod.AppState(
        # None until first run completes. NOT Path.home(): a fallback there
        # would send list_rows() scanning the user's entire home directory
        # for .mkv files on first launch, which is slow, alarming, and
        # produces a list that looks like a bug rather than an empty state.
        recording_dir=rec_dir,
        settings=cfg,
        ffmpeg_bin=resolve_binary("ffmpeg"),
        ffprobe_bin=resolve_binary("ffprobe"),
    )
    api = api_mod.Api(state)

    w = None
    scheduler = None
    window = None
    poll_state = PollState()

    def on_open() -> None:
        # Called on the pystray thread. show() and destroy() are safe from
        # there (spike Q6, confirmed twice); no marshalling needed, and
        # there is no event loop left to marshal onto anyway.
        #
        # The None guard is not paranoia: the tray thread is started before
        # create() returns, so a very fast click can land in the gap.
        if window is not None:
            window.show()

    def on_quit() -> None:
        if window is not None:
            window.destroy()  # unblocks window_mod.run() below

    icon = build_tray(on_open=on_open, on_quit=on_quit)
    threading.Thread(target=icon.run, daemon=True, name="pystray").start()

    window = window_mod.create(api)

    def start_watching(directory) -> None:
        """Create the watcher and start the poll loop. Idempotent.

        Called once the recording directory is known: at startup when it is
        already stored or detected, or later from the page's first-run
        route once the user picks one.
        """
        nonlocal w, scheduler
        if scheduler is not None:
            return
        w = watcher.Watcher(Path(directory), paths.seen_file())
        w.baseline()  # Prunes stale `seen` entries left by out-of-band deletes.
        # The Api holds the watcher directly: save_settings rebinds it when
        # the recording folder changes, and delete_selected forgets what it
        # actually removed. No callback indirection.
        api._watcher = w
        scheduler = Scheduler(POLL_SECONDS,
                              lambda: poll_tick(w, api, icon, window, poll_state))
        scheduler.start()

    api._on_recording_dir_ready = start_watching

    if rec_dir is not None:
        cfg["recording_dir"] = str(rec_dir)
        settings_mod.save(cfg)
        # Started before run() rather than from a page-loaded event: the
        # first tick is POLL_SECONDS away and the page asks for its own
        # state on load, so an early push has nothing to race with.
        start_watching(rec_dir)
    else:
        # First run, or a stored folder that has since disappeared. The page
        # cannot infer this state -- an unconfigured folder and an empty one
        # look identical from there -- so it is pushed explicitly. Deferred
        # until the page is up, because a push before app.js has registered
        # its handlers is logged and dropped (see Api._push).
        api._push_first_run_when_ready()

    # Resolve the account state off the bridge thread so the Settings route
    # is correct the first time it is opened rather than after a click.
    api.refresh_auth()

    window_mod.run()  # Blocks until the window is destroyed.

    icon.stop()
    if scheduler is not None:
        scheduler.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Retire the tests for the deleted Tk plumbing**

In `tests/test_main.py`, delete these tests and the `_FakeUser32` class — all cover `get_system_dpi` / `tk_scaling_for` / `app.dpi_scale`, none of which exist any more:

- `test_get_system_dpi_falls_back_to_96_off_windows`
- `test_get_system_dpi_floors_a_zero_return_at_96`
- `test_get_system_dpi_floors_any_sub_96_return`
- `test_get_system_dpi_passes_through_a_real_high_dpi_value`
- `test_get_system_dpi_survives_a_missing_user32_export`
- `test_dpi_scale_normalises_tk_scaling_to_a_100_percent_multiplier`
- `test_tk_scaling_uses_the_points_per_pixel_divisor`
- `test_tk_scaling_and_dpi_scale_round_trip`

Also delete `_unreachable_ask` and `test_no_stored_value_and_no_detection_asks_user` (replaced by `test_a_first_run_with_no_folder_no_longer_asks`), and drop the `ask=_unreachable_ask` argument from the three surviving precedence tests. Keep `_FakeShcore`, both `set_dpi_awareness` tests, and the redaction test unchanged. Update the import block to:

```python
from obs_youtube_uploader.__main__ import (
    configure_logging, resolve_recording_dir, set_dpi_awareness,
)
```

In `tests/test_upload_media_close.py`, repoint the import and the subject. It
imports `app` and drives `_upload_one` / `_close_media`, both of which moved to
`ui/api.py` in Task 7, and `app` does not survive Task 16:

```python
from obs_youtube_uploader import uploader
from obs_youtube_uploader.ui import api as api_mod
```

then replace every `app_mod._close_media` with `api_mod._close_media` and every
`app_mod.` reference to the upload path with its `api_mod.` equivalent. The
behaviour under test is unchanged — a stitched upload must close the media
handle so `stitch.stitched()` can unlink a multi-gigabyte temporary on Windows,
and the non-stitched path must NOT close, because `UploadFailed` carries the
resumable request that Retry resumes from. Both assertions carry over verbatim.

In `tests/test_app.py`, delete the `spacing()` and `tk_scaling_for` block, which dies with the Tk layout helpers. **Keep the `format_selection_summary` cases** — Task 2 repointed them at `ui.copy` and they are pure. Delete `test_app_still_exposes_the_moved_copy_helpers`, whose subject (`app.py`'s re-exports) disappears in Task 16, and rename the file to `tests/test_copy.py` so its name matches what it now covers:

```bash
git mv tests/test_app.py tests/test_copy.py
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_poll_tick.py tests/test_main.py tests/test_copy.py tests/test_window.py -v`
Expected: all pass. `pytest tests -q` still fails at collection on the seven Tk test files — expected, and Task 16's job.

- [ ] **Step 7: Commit**

```bash
git add obs_youtube_uploader/__main__.py tests/test_poll_tick.py tests/test_main.py tests/test_copy.py
git commit -m "Rewrite __main__ onto the webview lifecycle"
```

---

### Task 16: Delete the Tk UI and update dependencies

> **THIS TASK IS THE POINT OF NO RETURN.** Tasks 14 and 15 must be complete and the app must have been run against real recordings through the new UI before this lands. The Tk and webview UIs cannot run side by side (design, Risks item 5), so ordering is the only mitigation — once `app.py` is gone there is no working UI to fall back to except by reverting the commit.

**Files:**
- Delete: `obs_youtube_uploader/app.py`, `settingsui.py`, `theme.py`, `tooltip.py`
- Delete: `tests/test_app_layout.py`, `test_theme.py`, `test_typography.py`, `test_treeview_columns.py`, `test_row_click.py`, `test_app_selection_summary.py`, `test_app_last_upload.py`, `tests/conftest.py`
- Modify: `pyproject.toml`
- Test: `tests/test_no_tk.py`

**Interfaces:**
- Produces: nothing new. Removes the importable names `obs_youtube_uploader.app`, `.settingsui`, `.theme`, `.tooltip` and the `sv-ttk` dependency; adds `pywebview==6.2.1`

`tests/conftest.py` goes entirely rather than being emptied: `make_window` is its only fixture and only the deleted files use it, and a conftest that exists but defines nothing is a decoy for the next person looking for shared fixtures.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_no_tk.py
"""The Tk UI is gone, and must stay gone.

Two failure modes this guards, both of which look fine locally and break a
frozen build:

  * a module left importable invites a new call site against a UI that no
    longer has a window to attach to;
  * a stray `import tkinter` anywhere in the import graph drags Tcl/Tk into
    the PyInstaller bundle, silently adding megabytes and a dependency the
    spec says we no longer have.
"""
import importlib
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.mark.parametrize("name", ["app", "settingsui", "theme", "tooltip"])
def test_the_tk_ui_modules_are_gone(name):
    """Deleted, not deprecated -- the same reasoning that removed the
    unscaled pad constants rather than leaving them importable."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"obs_youtube_uploader.{name}")


def test_importing_the_entry_point_does_not_pull_in_tkinter():
    """Run in a subprocess on purpose: another test in this session may have
    imported tkinter already, which would make an in-process sys.modules
    check pass or fail for reasons unrelated to our import graph."""
    result = subprocess.run(
        [sys.executable, "-c",
         "import obs_youtube_uploader.__main__ as m, sys;"
         "print(','.join(n for n in sys.modules if n.startswith('tkinter')))"],
        capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "", (
        f"tkinter reached the import graph via: {result.stdout.strip()}")


def test_sv_ttk_is_no_longer_a_dependency():
    deps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"]
    assert not any(d.lower().startswith("sv-ttk") for d in deps)


def test_pywebview_is_pinned_not_ranged():
    """6.x has live API churn -- FOLDER_DIALOG was deprecated for
    FileDialog.FOLDER mid-series. A range would let an upgrade land without
    a smoke pass on a UI with no automated coverage."""
    deps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"]
    pins = [d for d in deps if d.lower().startswith("pywebview")]
    assert pins == ["pywebview==6.2.1"], pins


def test_pillow_is_kept():
    """It looks like a Tk-era dependency and is not: build_tray() opens the
    bundled .ico with it and draws the generated fallback icon."""
    deps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"]
    assert any(d.lower().startswith("pillow") for d in deps)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_no_tk.py -v`
Expected: FAIL — `test_the_tk_ui_modules_are_gone` fails all four parametrisations with `DID NOT RAISE`, and the two dependency tests fail on the current list.

- [ ] **Step 3: Delete the Tk implementation and its widget tests**

```bash
git rm obs_youtube_uploader/app.py \
       obs_youtube_uploader/settingsui.py \
       obs_youtube_uploader/theme.py \
       obs_youtube_uploader/tooltip.py

git rm tests/test_app_layout.py \
       tests/test_theme.py \
       tests/test_typography.py \
       tests/test_treeview_columns.py \
       tests/test_row_click.py \
       tests/test_app_selection_summary.py \
       tests/test_app_last_upload.py \
       tests/conftest.py
```

The two behaviours whose only coverage was in the deleted test files — a landing ffprobe result refreshing a summary that shows a partial `+` total, and the last-upload channel being surfaced after a successful upload — were re-expressed as bridge tests in Task 6 (`test_the_panel_text_is_computed_in_python`) and Task 7 (`test_the_destination_channel_is_learned_and_persisted`). Confirm both are present before continuing.

- [ ] **Step 4: Update `pyproject.toml`**

Replace the `dependencies` list:

```toml
dependencies = [
    "google-api-python-client",
    "google-auth-oauthlib",
    "google-auth-httplib2",
    "pystray",
    # Kept, despite looking like Tk-era baggage: build_tray() opens the
    # bundled .ico with it and draws the generated fallback icon.
    "Pillow",
    # Pinned exactly, not ranged. 6.x has live API churn -- FOLDER_DIALOG
    # was deprecated for FileDialog.FOLDER mid-series -- and pywebview is a
    # small project whose frameless-Windows support is its thinnest area.
    # 6.2.1 is the version the spike ran on. Treat an upgrade as a change
    # requiring a full smoke pass, not a routine bump.
    "pywebview==6.2.1",
]
```

Then refresh the lock and reinstall:

```bash
uv lock
uv sync --extra dev
```

- [ ] **Step 5: Prove nothing still references the deleted modules**

```bash
grep -rn -E "sv_ttk|sv-ttk|import tkinter|from tkinter|_tkinter_finder|\b(app|settingsui|theme|tooltip)\b" \
  --include="*.py" obs_youtube_uploader tests
```

Expected: no hits naming the four deleted modules, no `tkinter`, no `sv_ttk`. Word-boundary matches on generic words like `theme` may hit CSS-token comments or the `ui/copy.py` docstrings — read each hit rather than trusting the count.

Five test files import the doomed modules and are repointed rather than deleted,
because what they cover survives the port: `test_app_upload_copy.py` and
`test_settingsui_copy.py` and `test_tooltip.py` in Task 2, `test_copy.py`
(renamed from `test_app.py`) and `test_upload_media_close.py` in Task 15.
Confirm all five import only from `obs_youtube_uploader.ui` before deleting
anything — a stale `from obs_youtube_uploader import app` line collects fine
today and fails the moment `app.py` is gone.

If the grep finds one that was missed, that is a Task 2 or Task 15 regression,
not something to patch around: re-point the import and note it.

Scope: `.github/workflows/build.yml`, `release.yml`, `packaging/uploader.spec`, and `packaging/installer.iss` all still reference `sv_ttk` / `PIL._tkinter_finder`. They are deliberately **out of scope here** and are handled by Task 17 — this grep is restricted to `obs_youtube_uploader/` and `tests/` for that reason. The build will not be green until Task 17 lands.

- [ ] **Step 6: Run the full suite**

```bash
pytest tests -q
```

Expected: green. Confirm specifically that `tests/test_copy.py`, `tests/test_app_upload_copy.py`, `tests/test_settingsui_copy.py`, and `tests/test_tooltip.py` still pass — those are the copy decisions the whole port was designed to carry across untouched, and they are the cheapest signal that it did.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock tests/test_no_tk.py
git commit -m "Delete the Tk UI; swap sv-ttk for a pinned pywebview"
```

---

### Task 17: PyInstaller and CI

**Files:**
- Modify: `packaging/uploader.spec`
- Modify: `.github/workflows/build.yml`
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: `obs_youtube_uploader/web/` (Tasks 10–13); `obs_youtube_uploader/ui/` (Tasks 1–16); `pywebview` pinned in `pyproject.toml` and `sv-ttk` removed (Task 16)
- Produces: a frozen one-folder bundle at `dist/OBSYouTubeUploader/` whose executable sits at the top and whose page assets are at `_internal/web/index.html`. Task 18's `installer.iss` copies that tree unchanged; Task 19's "Frozen build" smoke items prove the page actually loads.

- [ ] **Step 1: Rewrite `packaging/uploader.spec`**

```python
# packaging/uploader.spec
# One-folder build. Deliberately not one-file: one-file unpacks to temp on
# every launch (slow with ffmpeg bundled) and trips antivirus heuristics
# markedly more often.
from pathlib import Path

ROOT = Path(SPECPATH).parent
BIN = ROOT / "packaging" / "bin"
ICON = ROOT / "obs_youtube_uploader" / "assets" / "app.ico"
WEB = ROOT / "obs_youtube_uploader" / "web"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[
        (str(BIN / "ffmpeg.exe"), "bin"),
        (str(BIN / "ffprobe.exe"), "bin"),
    ],
    datas=[
        # The page is data, not code: modulegraph only follows Python
        # imports, so nothing under web/ reaches the bundle unless it is
        # listed here. PyInstaller exits 0 either way (see the ffmpeg
        # comment in build.yml), and the failure is total rather than
        # partial -- window.py loads index.html by path, so a web/ that did
        # not get collected means a blank window with no error. Both
        # build.yml and release.yml therefore carry a post-build assertion.
        # Destination is "web" (not "."), so the runtime lookup is
        # bundle_dir() / "web" / "index.html" and resolves to
        # _internal/web/index.html under PyInstaller 6.x's one-folder
        # layout -- the exact path the spike confirmed.
        (str(WEB), "web"),
        # Collected at the bundle root so paths.icon_file()'s frozen-case
        # lookup (bundle_dir() / "app.ico") finds it directly.
        (str(ICON), "."),
    ],
    hiddenimports=[
        # pystray selects its backend implementation dynamically at
        # runtime, which modulegraph cannot follow statically.
        "pystray._win32",
        # Required, not precautionary: pywebview picks its rendering
        # backend at runtime from a string, so modulegraph never sees this
        # import. Without it the frozen app reaches webview.start(), finds
        # no backend, and -- per spike Q7 -- returns normally and exits 0
        # with no window and no error. The build-time import check in
        # build.yml is what catches a missing/renamed module here, because
        # PyInstaller reports "Hidden import not found" as an ERROR line
        # and still exits 0.
        "webview.platforms.edgechromium",
        # google.* and googleapiclient.* are PEP 420 namespace packages.
        # modulegraph has a known history of mishandling namespace-package
        # resolution, so these are listed explicitly as a safety net -- not
        # because the imports below are lazy/function-level (modulegraph
        # scans bytecode for IMPORT_NAME regardless of function nesting, so
        # it normally does find those just fine).
        "googleapiclient.discovery",
        "googleapiclient.http",
        "google_auth_oauthlib.flow",
        "google.oauth2.credentials",
        "google.auth.transport.requests",
        # Not imported by name anywhere in this package, but
        # googleapiclient.discovery.build() uses it internally to wrap
        # google.auth credentials in an httplib2 transport.
        "google_auth_httplib2",
    ],
    hookspath=[],
    runtime_hooks=[],
    # tkinter is excluded, not merely unused: the replatform removed every
    # import of it, and leaving it in drags the whole Tcl/Tk tree into the
    # bundle for nothing. The spike's spec excluded it the same way. A
    # residual `import tkinter` left somewhere fails LOUDLY at startup with
    # ImportError, unlike the silent datas/hiddenimports failures above, so
    # this needs no post-build assertion of its own.
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OBSYouTubeUploader",
    console=False,          # No console window behind the GUI.
    disable_windowed_traceback=False,
    icon=str(ICON),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,              # UPX compression increases antivirus false positives.
    name="OBSYouTubeUploader",
)
```

- [ ] **Step 2: Swap the runtime-dependency import check in `.github/workflows/build.yml`**

Replace the existing `Verify the app's dependencies are importable` step with:

```yaml
      - name: Verify the app's dependencies are importable
        # PyInstaller only reports "Hidden import not found" as an ERROR line
        # and still exits 0, so a missing dependency yields a successful build
        # of a broken application. Fail here instead, where it is obvious.
        #
        # This only proves the packages are installed on the *build* runner,
        # before PyInstaller has run - it says nothing about whether the web/
        # page data actually reached the frozen bundle. See the post-build
        # assertion below for that.
        shell: pwsh
        run: |
          python -c "import pystray, PIL, googleapiclient, google_auth_oauthlib, webview; print('runtime deps importable')"
          if ($LASTEXITCODE -ne 0) { throw "the app's runtime dependencies are not installed" }
          # Checked separately because it is the hiddenimports= entry, not an
          # ordinary import: nothing in the source imports this module by
          # name, so a rename or a broken pythonnet install would otherwise
          # surface only as a frozen app that opens no window and exits 0
          # (spike Q7). Named on its own line so the failure says which one.
          python -c "import webview.platforms.edgechromium; print('edgechromium backend importable')"
          if ($LASTEXITCODE -ne 0) { throw "webview.platforms.edgechromium is not importable - the hiddenimports entry in uploader.spec would resolve to nothing and the frozen app would exit 0 with no window" }
```

- [ ] **Step 3: Replace the sv-ttk bundle assertion in `.github/workflows/build.yml`**

Replace the whole `Verify sv-ttk theme data is bundled` step with:

```yaml
      - name: Verify the web page is bundled
        # Mirrors the ffmpeg check above and exists for the same reason the
        # sv-ttk assertion it replaces did: PyInstaller exits 0 even when a
        # `datas` entry resolves to nothing, so a wrong path in uploader.spec
        # would produce a green build of an app that opens a blank window -
        # and nothing in CI would notice without this. The trap is confirmed
        # still live: the spike's build.ps1 asserts on exactly this path for
        # exactly this reason.
        #
        # It is worse here than it was for sv-ttk. A missing .tcl file raised
        # at set_theme(); a missing web/ produces no exception at all, because
        # pywebview swallows load failures (spike Q7) and webview.start()
        # returns normally with exit code 0.
        #
        # This assertion only proves the files are present; it cannot prove
        # the page loads and renders, which is what actually launching the app
        # (manually, from the downloaded artifact) is for - see
        # docs/smoke-checklist.md, "Look and feel > Frozen build".
        shell: pwsh
        run: |
          $web = "dist\OBSYouTubeUploader\_internal\web"
          if (-not (Test-Path $web)) {
            throw "web/ not found at $web - the (WEB, 'web') datas entry in uploader.spec did not resolve, and the app will open a blank window and exit 0"
          }
          Get-ChildItem -Recurse $web
          # Every file the page loads by name. index.html is the entry point;
          # a missing style.css or any of the four scripts renders an
          # unstyled or inert page rather than failing. Settings is a ROUTE
          # inside index.html, so there is no second document to check.
          foreach ($asset in @("index.html", "style.css", "app.js", "list.js", "panel.js", "settings.js")) {
            $path = Join-Path $web $asset
            if (-not (Test-Path $path)) { throw "$asset missing from the bundled web/ data at $path" }
          }
```

- [ ] **Step 4: Verify the build workflow no longer mentions sv-ttk**

Run: `grep -rn "sv_ttk\|sv-ttk" .github/workflows/build.yml packaging/uploader.spec; echo "exit=$?"`

Expected: no matching lines and `exit=1` (grep's no-match code). Any hit is a leftover reference to a dependency that no longer exists.

- [ ] **Step 5: Strengthen `.github/workflows/release.yml`'s import check**

Replace its `Verify the app's dependencies are importable` step with:

```yaml
      - name: Verify the app's dependencies are importable
        # PyInstaller reports a missing hidden import as an ERROR line but
        # still exits 0, so a missing dependency yields a successful build of
        # a broken application. Fail here, where the cause is obvious.
        #
        # webview is checked here even though this list historically lagged
        # build.yml's: the release path must not be weaker than the test-build
        # path, and this is the dependency whose absence produces the quietest
        # failure of any of them (spike Q7 - no window, no error, exit 0).
        shell: pwsh
        run: |
          python -c "import pystray, PIL, googleapiclient, google_auth_oauthlib, webview; print('runtime deps importable')"
          if ($LASTEXITCODE -ne 0) { throw "the app's runtime dependencies are not installed" }
          # The hiddenimports= entry, checked separately so the failure names
          # it. Nothing imports this module by name, so PyInstaller dropping
          # it is invisible until a user launches the release.
          python -c "import webview.platforms.edgechromium; print('edgechromium backend importable')"
          if ($LASTEXITCODE -ne 0) { throw "webview.platforms.edgechromium is not importable - the hiddenimports entry in uploader.spec would resolve to nothing and the released app would exit 0 with no window" }
```

- [ ] **Step 6: Add a `web/` bundle assertion to `.github/workflows/release.yml`**

Insert a new step between the existing `Build executable` and `Build installer` steps:

```yaml
      - name: Verify the web page is bundled
        # release.yml previously had NO post-build bundle assertion of any
        # kind - build.yml carried them all, and a release built straight from
        # a tag skipped every one. That was survivable while the worst
        # outcome was an unthemed window. It is not survivable now: a `datas`
        # entry that resolves to nothing still leaves PyInstaller exiting 0,
        # and the resulting app opens no window and exits 0 as well (spike
        # Q7), so the first report would come from a user who downloaded a
        # release and saw nothing happen.
        #
        # Deliberately mirrors build.yml's step of the same name. If you
        # change one, change the other - they are the same assertion on the
        # same path, and the release path must not be the weaker of the two.
        shell: pwsh
        run: |
          $web = "dist\OBSYouTubeUploader\_internal\web"
          if (-not (Test-Path $web)) {
            throw "web/ not found at $web - the (WEB, 'web') datas entry in uploader.spec did not resolve, and the released app will open a blank window and exit 0"
          }
          Get-ChildItem -Recurse $web
          foreach ($asset in @("index.html", "style.css", "app.js", "list.js", "panel.js", "settings.js")) {
            $path = Join-Path $web $asset
            if (-not (Test-Path $path)) { throw "$asset missing from the bundled web/ data at $path" }
          }
```

- [ ] **Step 7: Verify both workflows assert the same bundle path**

Run: `grep -c '_internal\\web' .github/workflows/build.yml .github/workflows/release.yml`

Expected: `1` for each file. A path present in only one means the release path is weaker than the build path again.

- [ ] **Step 8: Verify the spec parses**

Run: `python -c "import ast,pathlib; ast.parse(pathlib.Path('packaging/uploader.spec').read_text()); print('spec parses')"`

Expected: `spec parses`. A full PyInstaller run is Windows-only and happens in CI; this catches a syntax error before pushing.

- [ ] **Step 9: Commit**

```bash
git add packaging/uploader.spec .github/workflows/build.yml .github/workflows/release.yml
git commit -m "Freeze the webview page instead of the sv-ttk theme"
```

---

### Task 18: WebView2 bootstrapper in the installer

**Files:**
- Create: `packaging/fetch_webview2.py`
- Modify: `packaging/installer.iss`
- Modify: `.github/workflows/build.yml`, `.github/workflows/release.yml`, `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `ui/preflight.py`'s `WEBVIEW2_GUID` and `webview2_version()` (Task 1) — the installer's `WebView2RuntimePresent()` must be the same predicate over the same three registry locations; `dist/OBSYouTubeUploader/` (Task 17)
- Produces: `dist/FlyGD-Wingman-Setup-<version>.exe`, which installs the Evergreen runtime when absent. Task 19's `## WebView2 runtime` smoke items verify it.

**Acquisition decision — bundled at build time, not downloaded at install time.** Both options ultimately need the network (the Evergreen *bootstrapper* is a ~1.7 MB stub that fetches the runtime itself; only the ~150 MB Standalone Installer is truly offline). Bundling wins on three counts and loses on one:

- The download happens on the CI runner, where a failure fails the *build* loudly, instead of on a user's machine, where it fails silently in the middle of a wizard.
- Integrity is verified once, at build time, with `Get-AuthenticodeSignature` on a Windows runner. An install-time download cannot do that portably from Pascal.
- `aka.ms`/`go.microsoft.com` link rot breaks CI, not shipped installers.
- Cost: ~1.7 MB on the installer, and the install still needs connectivity for the runtime payload itself. Accepted — the app cannot upload to YouTube offline either.

A SHA-256 pin is deliberately **not** used, unlike `fetch_ffmpeg.py`: Microsoft rotates the artifact behind a stable fwlink, so a pin would break the build every few weeks and train the maintainer to bump hashes without checking them. The Authenticode signature is the stronger check anyway — it verifies the publisher, not just that the bytes match whatever was downloaded the day the pin was set.

- [ ] **Step 1: Create `packaging/fetch_webview2.py`**

```python
# packaging/fetch_webview2.py
"""Download the WebView2 Evergreen bootstrapper at build time.

Bundled rather than downloaded during installation: a failed download then
fails the BUILD, loudly, instead of failing silently inside a user's install
wizard. See packaging/installer.iss for how it is invoked.

Deliberately NOT sha256-pinned, unlike fetch_ffmpeg.py. Microsoft rotates the
artifact behind the stable fwlink below, so a pin would break the build every
few weeks and teach whoever maintains it to bump the hash without looking.
Integrity comes from the Authenticode signature instead, checked on a Windows
runner by the "Verify the WebView2 bootstrapper is signed by Microsoft" step
in build.yml and release.yml -- that verifies the publisher, which a hash of
an ever-changing file never did.

What IS checked here, because none of it needs Windows:
  * the redirect chain terminates on a microsoft.com host
  * the payload is a PE executable
  * the size is within an order of magnitude of the ~1.7MB stub

The observed digest is printed and recorded in a sidecar so a change in the
artifact is at least visible in the build log.
"""
import hashlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Microsoft's documented permalink for the Evergreen Bootstrapper. It is a
# stub that downloads the runtime itself; it is not the offline installer.
BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
OUT_DIR = Path(__file__).parent / "bin"
OUT_NAME = "MicrosoftEdgeWebview2Setup.exe"
# The stub has sat near 1.7MB for years. The bounds are loose on purpose --
# they exist to catch an HTML error page or a truncated read, not to pin a
# size. An error page is a few KB; the standalone installer is ~150MB.
MIN_BYTES = 500_000
MAX_BYTES = 20_000_000
ALLOWED_HOST_SUFFIX = ".microsoft.com"
# Records the digest the bundled stub was fetched with, so a silent swap of
# the artifact shows up as a diff in the build log rather than nowhere.
DIGEST_FILE = OUT_DIR / ".webview2-sha256"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / OUT_NAME

    print(f"Downloading {BOOTSTRAPPER_URL}")
    try:
        with urllib.request.urlopen(BOOTSTRAPPER_URL) as response:
            final_url = response.geturl()
            payload = response.read()
    except (urllib.error.URLError, OSError) as exc:
        print(f"ERROR: download failed: {exc}")
        return 1

    # urlopen follows redirects, so this is the host that actually served the
    # bytes -- go.microsoft.com redirects to a msedge.sf.dl.delivery CDN host
    # under microsoft.com. A redirect landing anywhere else means the link was
    # repointed and must be reviewed by hand, not shipped.
    host = (urllib.parse.urlsplit(final_url).hostname or "").lower()
    if not (host == "microsoft.com" or host.endswith(ALLOWED_HOST_SUFFIX)):
        print(f"ERROR: redirect ended on an unexpected host: {final_url}")
        return 1
    print(f"  served by {host}")

    if not (MIN_BYTES <= len(payload) <= MAX_BYTES):
        print(
            f"ERROR: payload is {len(payload)} bytes, outside the expected "
            f"{MIN_BYTES}-{MAX_BYTES} range - this is probably an error page "
            f"or the wrong artifact"
        )
        return 1

    # 'MZ'. A captive-portal or error page fails here rather than being
    # bundled and handed to Exec() at install time.
    if payload[:2] != b"MZ":
        print("ERROR: payload is not a PE executable (no MZ header)")
        return 1

    digest = hashlib.sha256(payload).hexdigest()
    out_path.write_bytes(payload)
    DIGEST_FILE.write_text(digest)
    print(f"  wrote {out_path} ({len(payload)} bytes)")
    print(f"  sha256={digest}")
    print("  NOTE: the Authenticode signature check in CI is the real gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify the fetch script**

Run: `python packaging/fetch_webview2.py && ls -l packaging/bin/MicrosoftEdgeWebview2Setup.exe`

Expected: prints `served by` a `*.microsoft.com` host, a byte count near 1.7 MB, a `sha256=` line, and `ls` shows the file. `packaging/bin/` is already in `.gitignore`, so nothing is committed.

- [ ] **Step 3: Rewrite `packaging/installer.iss`**

Keep the existing `[Setup]` block's `AppId`, `DefaultDirName`, and `OutputBaseFilename` **exactly as they are** — `AppId` is the upgrade identity and renaming it strands every existing installation. Add the WebView2 pieces:

In `[Files]`, **before** the application tree:

```pascal
; FIRST on purpose. SolidCompression=yes means the archive must be
; decompressed from the beginning to reach any given file, so a dontcopy file
; placed after the whole application tree would force a second pass over
; every byte of it when ExtractTemporaryFile is called at ssPostInstall.
; Listed first, the extraction is nearly free.
;
; dontcopy: this is never installed into {app}. It is extracted to {tmp}
; only when the runtime is actually missing, and deleted with {tmp}.
Source: "bin\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy noencryption
```

Then append a `[Code]` section:

```pascal
[Code]
{ ------------------------------------------------------------------------
  WebView2 Evergreen runtime.

  The application renders its entire UI in WebView2. Without the runtime,
  pywebview logs a FileNotFoundException, webview.start() returns normally,
  and the process EXITS 0 -- no window, no error, no crash dialog, and a
  success exit code. In a windowed build the log line is not visible either.
  That is why this exists.

  This installer is only HALF the fix. The runtime can be uninstalled or
  broken after a successful install, so obs_youtube_uploader/ui/preflight.py
  runs the same check at every launch and shows a native message box before
  webview.start() is ever called.

  THE TWO CHECKS MUST BE THE SAME PREDICATE. The GUID below is duplicated in
  preflight.py's WEBVIEW2_GUID, and ci.yml's "Check the WebView2 detection
  predicate agrees" step fails the build if the two drift. If you change the
  rule here -- the keys, the pv handling, the 0.0.0.0 case -- change it there
  in the same commit.
  ------------------------------------------------------------------------ }
const
  { EdgeUpdate's client id for the Evergreen runtime. Microsoft documents
    this registry probe as the supported detection method; there is no API. }
  WEBVIEW2_GUID = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WEBVIEW2_CLIENT_PATH = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\';
  WEBVIEW2_DOWNLOAD_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/';

var
  WebView2Missing: Boolean;

function ReadRuntimeVersion(RootKey: Integer): String;
var
  Value: String;
begin
  Result := '';
  if RegQueryStringValue(RootKey, WEBVIEW2_CLIENT_PATH + WEBVIEW2_GUID, 'pv', Value) then
    Result := Trim(Value);
end;

function VersionIsReal(const Version: String): Boolean;
begin
  { An empty pv, or the literal '0.0.0.0', is what a partially removed or
    never-completed install leaves behind. Treating either as "present" is
    the exact mistake that produces the silent-exit-0 launch. }
  Result := (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2RuntimePresent(): Boolean;
begin
  { Three locations, matching preflight.py's three:

      HKLM32 -> HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{GUID}
                on 64-bit Windows. EdgeUpdate is a 32-bit process, so this is
                where a per-machine install actually lands, and it is the key
                observed present on the dev machine (pv=151.0.4129.93).
                On 32-bit Windows there is no redirection and this same view
                IS HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{GUID}.
      HKLM64 -> the native hive on 64-bit Windows. Guarded by IsWin64
                because the 64-bit root constants error on 32-bit Windows.
      HKCU   -> a per-user runtime install, which is what an UNELEVATED
                bootstrapper produces -- and PrivilegesRequired=lowest means
                that is our normal case, not an edge case.

    Any one of them counts. }
  Result := VersionIsReal(ReadRuntimeVersion(HKLM32));
  if not Result then
    Result := VersionIsReal(ReadRuntimeVersion(HKCU));
  if (not Result) and IsWin64 then
    Result := VersionIsReal(ReadRuntimeVersion(HKLM64));
end;

procedure ReportWebView2Failure();
var
  Message: String;
begin
  Message :=
    'The Microsoft Edge WebView2 runtime could not be installed.' + #13#10#13#10 +
    'FlyGD Wingman has been installed, but it will not open a window until' + #13#10 +
    'the runtime is present. This usually means the machine was offline: the' + #13#10 +
    'installer bundles a small downloader, not the runtime itself.' + #13#10#13#10 +
    'Connect to the internet and install it from:' + #13#10 +
    WEBVIEW2_DOWNLOAD_URL + #13#10#13#10 +
    'FlyGD Wingman will show this same message if you launch it before then.';
  Log('WebView2: ' + Message);
  { Never block an unattended install on a message box nobody can dismiss.
    /VERYSILENT is how the CI smoke install runs. }
  if WizardSilent() then
    Log('WebView2: setup is silent; suppressing the message box.')
  else
    MsgBox(Message, mbError, MB_OK);
end;

procedure InstallWebView2Runtime();
var
  SetupPath: String;
  ResultCode: Integer;
begin
  if WebView2RuntimePresent() then
  begin
    Log('WebView2: runtime already present, skipping the bootstrapper.');
    Exit;
  end;

  Log('WebView2: runtime absent, running the bundled Evergreen bootstrapper.');
  ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  SetupPath := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');

  { '/silent /install' is the documented pair. Without /install the
    bootstrapper shows its own UI; without /silent it puts a progress window
    on top of the wizard. ewWaitUntilTerminated because the check below is
    only meaningful once it has finished. }
  if not Exec(SetupPath, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Log('WebView2: the bootstrapper could not be started at all.');
    WebView2Missing := True;
    ReportWebView2Failure();
    Exit;
  end;
  Log(Format('WebView2: bootstrapper exited with %d', [ResultCode]));

  { Re-run the SAME predicate rather than trusting the exit code. The whole
    reason this feature exists is that a success code from something that did
    nothing is exactly the failure mode this app is vulnerable to. If the
    registry says the runtime is there, it is there, whatever the stub
    returned; if it does not, the install did not work, whatever it returned. }
  if not WebView2RuntimePresent() then
  begin
    WebView2Missing := True;
    ReportWebView2Failure();
  end
  else
    Log('WebView2: runtime installed successfully.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { ssPostInstall runs after the application tree is in place and BEFORE the
    [Run] entry's post-install "Launch FlyGD Wingman" checkbox can fire, so a
    user who ticks it gets a working runtime. }
  if CurStep = ssPostInstall then
    InstallWebView2Runtime();
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { Deliberately does NOT abort the installation on failure. Aborting would
    strand a user whose only problem is a dropped connection, leaving them
    with nothing installed and no app to retry from; and the runtime install
    frequently succeeds on a later attempt. Instead the app is installed, the
    failure is reported once here, and preflight.py repeats the message with
    the same URL on every launch until it is fixed. }
  if (CurPageID = wpFinished) and WebView2Missing then
    WizardForm.FinishedLabel.Caption :=
      WizardForm.FinishedLabel.Caption + #13#10#13#10 +
      'WARNING: the Microsoft Edge WebView2 runtime is still missing, so ' +
      'FlyGD Wingman will not open a window. Install it from ' +
      WEBVIEW2_DOWNLOAD_URL;
end;
```

- [ ] **Step 4: Add a CI check that the two detection predicates agree**

In `.github/workflows/ci.yml`, insert between `Check version consistency` and `Test`:

```yaml
      - name: Check the WebView2 detection predicate agrees
        # The installer decides whether to run the Evergreen bootstrapper and
        # the app decides whether to refuse to start, and they must be the
        # same question. They cannot share code -- one is Inno Pascal, the
        # other is Python -- so this asserts on the pieces that would silently
        # drift: the EdgeUpdate client GUID, the registry subkey, the value
        # name, and the 0.0.0.0 sentinel. A drift here means the installer
        # skips the bootstrapper on a machine the app then refuses to run on,
        # or vice versa, and nothing else in the pipeline would notice.
        run: |
          python - <<'PY'
          import pathlib, sys

          iss = pathlib.Path("packaging/installer.iss").read_text()
          py = pathlib.Path("obs_youtube_uploader/ui/preflight.py").read_text()

          tokens = {
              "EdgeUpdate client GUID": "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
              "registry subkey": r"SOFTWARE\Microsoft\EdgeUpdate\Clients",
              "value name": "pv",
              "empty-install sentinel": "0.0.0.0",
          }
          missing = []
          for label, token in tokens.items():
              if token not in iss:
                  missing.append(f"{label} ({token!r}) missing from packaging/installer.iss")
              if token not in py:
                  missing.append(f"{label} ({token!r}) missing from obs_youtube_uploader/ui/preflight.py")

          if missing:
              for line in missing:
                  print(f"::error::{line}")
              print("The installer's WebView2RuntimePresent() and preflight.py's")
              print("webview2_version() must be the same predicate.")
              sys.exit(1)
          print("WebView2 detection predicate agrees across installer.iss and preflight.py")
          PY
```

- [ ] **Step 5: Verify the predicate check catches a drift**

Run:
```bash
sed -i 's/F3017226-FE2A-4295-8BDF-00C3A9A7E4C5/F3017226-FE2A-4295-8BDF-00C3A9A7E4C6/' packaging/installer.iss
python3 - <<'PY'
import pathlib
iss = pathlib.Path("packaging/installer.iss").read_text()
py = pathlib.Path("obs_youtube_uploader/ui/preflight.py").read_text()
g = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
print("DRIFT DETECTED" if (g in py) != (g in iss) else "NOT DETECTED")
PY
git checkout -- packaging/installer.iss
```

Expected: prints `DRIFT DETECTED`, and `git checkout` restores the file. If it prints `NOT DETECTED`, the CI step would not catch a real drift either.

- [ ] **Step 6: Wire the bootstrapper fetch and signature check into `build.yml`**

Insert immediately after the existing `Fetch ffmpeg` step:

```yaml
      - name: Fetch the WebView2 bootstrapper
        run: python packaging/fetch_webview2.py

      - name: Verify the WebView2 bootstrapper is signed by Microsoft
        # This is the integrity gate, standing in for the sha256 pin
        # fetch_ffmpeg.py uses. A pin is not possible here: Microsoft rotates
        # the artifact behind a stable fwlink, so a pinned hash would break
        # the build every few weeks and train whoever maintains it to bump
        # hashes without checking them. Verifying the PUBLISHER is stronger
        # anyway, and it is the check that would actually catch a hijacked
        # redirect - which is the threat that matters when the file is
        # bundled into an installer and then Exec'd on a user's machine.
        # Needs Windows, which is why it lives here and not in the script.
        shell: pwsh
        run: |
          $stub = "packaging\bin\MicrosoftEdgeWebview2Setup.exe"
          if (-not (Test-Path $stub)) { throw "bootstrapper not found at $stub" }
          $sig = Get-AuthenticodeSignature $stub
          Write-Host "Status:  $($sig.Status)"
          Write-Host "Subject: $($sig.SignerCertificate.Subject)"
          if ($sig.Status -ne "Valid") {
            throw "WebView2 bootstrapper signature is $($sig.Status), not Valid - do NOT ship this"
          }
          if ($sig.SignerCertificate.Subject -notmatch "O=Microsoft Corporation") {
            throw "WebView2 bootstrapper is signed by $($sig.SignerCertificate.Subject), not Microsoft Corporation"
          }
```

- [ ] **Step 7: Wire the same two steps into `release.yml`**

Insert the identical pair immediately after release.yml's `Fetch ffmpeg` step, with the signature step's comment amended to note it matters more here: this artifact is bundled into a released installer and then `Exec`'d on every machine that installs it, so an unverified stub is a supply-chain problem rather than a broken build. If you change one of the two steps, change the other.

- [ ] **Step 8: Verify the installer compiles**

Run on the Windows machine (`iscc` is not on the Linux dev box): `iscc packaging\installer.iss`

Expected: `Successful compile` and `dist\FlyGD-Wingman-Setup-2.2.0.exe`. A Pascal syntax error, a missing `packaging\bin\MicrosoftEdgeWebview2Setup.exe`, or an Inno older than 6.3 all fail here with a named error.

- [ ] **Step 9: Verify the runtime-present path on the dev machine**

The only half of the bootstrapper chain testable without a VM — the dev machine has `pv=151.0.4129.93`, so `WebView2RuntimePresent()` must return True and the bootstrapper must never run.

Run (Windows): `dist\FlyGD-Wingman-Setup-2.2.0.exe /VERYSILENT /LOG=%TEMP%\wingman-install.log` then `findstr /C:"WebView2:" %TEMP%\wingman-install.log`

Expected: exactly one matching line, `WebView2: runtime already present, skipping the bootstrapper.` No `bootstrapper exited with` line, no message box, install completes, and the installed exe launches and renders the page.

**The absent-runtime path is NOT covered by this step and cannot be.** Uninstalling the Evergreen runtime on the dev machine also removes it from Edge, and the `WEBVIEW2_BROWSER_EXECUTABLE_FOLDER` trick from spike Q7 only fools the *loader* in one process — it does not touch the registry, so the installer would still see the runtime and skip. Verifying that the bootstrapper actually runs, succeeds online, and fails cleanly offline requires a clean Windows VM with no WebView2 runtime installed. That is recorded as an open smoke item in `docs/smoke-checklist.md` under `## WebView2 runtime`, to be ticked on a VM before the first release — and left explicitly unticked, not assumed, until then.

- [ ] **Step 10: Commit**

```bash
git add packaging/fetch_webview2.py packaging/installer.iss \
        .github/workflows/build.yml .github/workflows/release.yml .github/workflows/ci.yml
git commit -m "Install the WebView2 Evergreen runtime from the installer"
```

---

### Task 19: Smoke checklist

**Files:**
- Modify: `docs/smoke-checklist.md`

**Interfaces:**
- Consumes: the whole replatformed UI — `ui/window.py`'s title bar and tray wiring, `ui/api.py`'s `pick_folder`/`detect_folder`/`dialog_response`/`onProgress`, `ui/preflight.py`'s native message box, and Task 18's installer
- Produces: the only verification any of the above gets. `tests/test_api*.py` cover the bridge headlessly; nothing automated covers rendering, input, native dialogs, the tray, or the runtime-absent path.

- [ ] **Step 1: Correct the preamble and add a WebView2 runtime section**

Replace the paragraph beginning "The UI refresh (theming, the Treeview list, DPI awareness…" with:

```
The UI itself is likewise untested by `pytest`. `tests/test_api*.py` drive
the bridge headlessly against a fake window and cover what the API *says*
and accepts; nothing under `tests/` renders the page, sends it input, opens
a native dialog, or touches the tray. There is deliberately no Playwright
and no browser toolchain. **This checklist is the only verification any of
that gets.**
```

Then insert between the end of `## Install` and the `## First run` heading:

```
## WebView2 runtime

The app renders its entire UI in WebView2 and has no fallback. These items
exist because the failure mode is silent: without the runtime, pywebview
logs a load failure, `webview.start()` returns normally, and the process
exits **0** — no window, no error, no crash dialog, and a success code.

- [ ] **The installer skips the bootstrapper when the runtime is already
      there.** Run with `/VERYSILENT /LOG=%TEMP%\i.log`, then
      `findstr /C:"WebView2:" %TEMP%\i.log`. Expected: exactly one line,
      "runtime already present, skipping the bootstrapper", and no
      `bootstrapper exited with` line. A bootstrapper that runs on every
      install is a several-minute delay nobody asked for.
- [ ] **LOAD-BEARING: a missing runtime produces a native dialog and a
      NON-ZERO exit.** Testable without a VM, exactly as spike Q7 did it:
      point `WEBVIEW2_BROWSER_EXECUTABLE_FOLDER` at an empty directory for
      one process and launch the installed exe from `cmd`, then read
      `echo %ERRORLEVEL%`. Expected: a native Windows message box naming
      the Microsoft Edge WebView2 runtime and its download URL, and a
      non-zero exit code. **An exit code of 0 is the defect** — that is the
      pre-refactor behaviour, and it means the pre-flight check is not
      running before `webview.start()`. Nothing is uninstalled by this test
      and the variable dies with the shell.
- [ ] **The pre-flight message box is readable and dismissible.** Confirm
      it has a title, names the runtime by its full name, shows a URL that
      can be selected or typed out, and closes on OK without leaving a
      process behind (check Task Manager).
- [ ] **CLEAN VM ONLY: the bootstrapper actually installs the runtime.**
      On a fresh Windows VM with no WebView2 runtime, run the installer.
      Expected: the wizard pauses briefly at the end, the log shows "runtime
      absent, running the bundled Evergreen bootstrapper" followed by
      "runtime installed successfully", and the app launches and renders.
      There is no way to fake this on a machine that already has the runtime
      — the `WEBVIEW2_BROWSER_EXECUTABLE_FOLDER` trick fools the loader, not
      the registry. **Leave this unticked rather than assuming it; it is the
      largest untested risk in the release.**
- [ ] **CLEAN VM ONLY: an offline install fails honestly.** Same VM,
      network disconnected. Expected: the install still completes, ONE error
      dialog explains the runtime could not be installed and gives the
      download URL, the Finished page repeats the warning, and the app is
      installed rather than rolled back. Reconnect, install the runtime by
      hand, and confirm the app then starts with no reinstallation.
```

- [ ] **Step 2: Replace the Tk-only `## Look and feel` section**

Delete the entire existing `## Look and feel` section — every item asserts on sv-ttk, ttk styles, `tk.Menu`, `tk.Canvas`, `ttk.Treeview` row heights or `tk scaling`, none of which exist any more. Replace with:

```
## Look and feel

### Window chrome
- [ ] **LOAD-BEARING: the custom title bar drags the window.** The OS title
      bar is gone; dragging is the page's `pywebview-drag-region`. Grab the
      bar and move the window across two monitors, then to a screen edge to
      trigger Windows snap. Expected: the window follows with no lag and
      snaps normally. This is the single most visible thing that breaks with
      a frameless window and it has no automated coverage of any kind.
- [ ] **The drag region excludes the controls.** Press and hold on the gear,
      minimize and close in turn and move the pointer a few pixels.
      Expected: none of them drags the window; each still activates on
      release.
- [ ] **The title-bar controls do what they say.** The gear opens the
      Settings route in the same window (not a second OS window), minimize
      minimizes to the taskbar, and close HIDES to the tray rather than
      exiting — confirm the process is still running and the tray icon is
      still there.
- [ ] **The window opens fully on screen.** Launch on the primary monitor,
      again with a second monitor attached, then again after disconnecting
      it. Expected: fully visible and its title bar reachable every time.
- [ ] **Scrollbars are the app's, not Windows'.** Scroll a long list. The
      scrollbar must be the styled thin one, not the classic grey Windows
      scrollbar.

### Typography and layout
- [ ] **The three type steps are visibly distinct** — panel/section headings
      largest, filenames and field text body, column headers and hints
      smallest.
- [ ] **Column headers sit below the data, not above it.** The header row
      must read as quieter than the filenames beneath it. Deliberate,
      carried over from 2.2.0: headers label the data, they are not the data.
- [ ] **Machine text is monospace.** Paths, the webhook field and the
      webhook summary render in the monospace face; prose does not.
- [ ] **Display scaling at 100%, 125%, 150% and 200%.** Restart at each.
      Expected: text sharp AND the right apparent size next to Notepad;
      neither route opens larger than the screen; Title, Description,
      Stitch, the summary, Upload combat logs, Retry and Upload Selected all
      fully visible with nothing clipped.
- [ ] **Nothing is clipped at the minimum window size** at 150%. The
      Description box shrinks first and the Retry / Upload Selected row is
      still fully visible.

### The list
- [ ] **Clicking ANYWHERE on a row toggles it,** not just the checkbox cell.
      Rows accumulate — clicking a second must not clear the first.
- [ ] **Select all and Select none repaint every checkbox,** not just the
      summary. The two must never disagree.
- [ ] **Click-to-sort works on every column and shows direction,** on the
      active column only. Sorting is pure client state; a sort that
      round-trips to Python or clears the selection is a defect.
- [ ] **The leftmost header is a bare check, not a checkbox.** Clicking it
      SORTS by checked state — it must not select or clear anything.
- [ ] **Sorting does not affect upload order or stitch order.** Sort by each
      column, select out of displayed order, upload with Stitch off then on.
      The `(1/n)` numbering and clip order follow the underlying data.
- [ ] **Sorting by Length while durations are still loading.** Delete
      `durations.json`, launch against a large folder, click Length while
      rows read "…". Pending rows sort together and each fills in where it
      sits — rows do NOT re-order under the cursor as results arrive.
- [ ] **LOAD-BEARING: arrow keys move focus and Space toggles.** Tab in,
      move with ↑/↓, press Space. Focus is visibly distinct from "checked",
      Space toggles exactly the focused row, and Space does NOT scroll. Then
      trigger a rebuild (delete a file, or save Settings) and confirm the
      keyboard still works without touching the mouse.
- [ ] **LOAD-BEARING: the row context menu opens and dismisses cleanly.**
      Dismiss by clicking away; by Escape; and by right-clicking a different
      row while the first is open. After each, the window still responds and
      only one menu is ever visible.
- [ ] **Copy link and Open in browser work and grey out correctly.** Both
      work on a row with a completed upload, both greyed without one, and
      Copy link puts a URL that actually opens on the clipboard.
- [ ] **LOAD-BEARING: double-click opens the link and LEAVES THE CHECKBOX
      SELECTION UNCHANGED.** Tick two rows, double-click a third with a
      link: the browser opens and the third row is still unticked. Repeat on
      a row that starts ticked — still ticked afterwards. A row left changed
      here is a defect, not cosmetic.
- [ ] **Newly announced recordings are pre-checked, scrolled into view, and
      visibly highlighted** — even when below the fold.
- [ ] **Selected, focused and uploaded rows are distinguishable** from one
      another at a glance.
- [ ] **Hovering an unreadable Length explains it,** and a `…` cell reads
      "Measuring length…" instead — the two glyphs mean opposite things.
- [ ] **Hovering the link glyph explains both gestures,** and no tooltip
      appears over an empty Link cell, a filename, a header, or empty space.
- [ ] **The list at the minimum window width.** Every column still present,
      Filename truncates rather than pushing others off, NO horizontal
      scrollbar.

### Frozen build
- [ ] **LOAD-BEARING: the installed build renders the page at all.** The
      only proof `web/` was both bundled AND loadable. CI asserts the files
      exist at `_internal\web\`; only launching proves the window finds
      them. A blank window means the datas entry resolved to the wrong
      place — and the app will still exit 0 when you close it.
- [ ] **The frozen build loads nothing from the network.** Disconnect and
      launch. The page renders identically — fonts, icons and styles local.
- [ ] **The tray icon still draws in the frozen build.** Pillow survives
      solely for the tray. Confirm the icon is the real app icon, and that
      renaming `app.ico` falls back to the drawn placeholder rather than
      breaking startup.
- [ ] **The primary action is visually distinct.** `Upload Selected` is the
      only brand-accent control on the screen.
```

- [ ] **Step 3: Add folder-dialog and Settings-route items**

Insert at the end of the `## Settings` section:

```
- [ ] **The webhook is still masked after a route change.** Open Settings
      with a webhook saved, tick **Show**, navigate back to the list, then
      return. Expected: masked again. A revealed credential that survives
      navigation is a leak — the mockup's cleartext webhook is exactly the
      regression this port must not reintroduce.
- [ ] **The account control tracks state through the route.** Start a
      sign-in, navigate away mid-flow, return. Expected: still reads
      **Waiting for browser…** and still disabled — `onAuthState` is the
      source of truth, not the DOM that was torn down.

### Folder dialogs

Native OS dialogs opened from the page through the bridge. Nothing
automated reaches them; the bridge tests can only assert the call was made.

- [ ] **Browse picks the recording folder.** A native picker appears, modal
      to the app window, and the chosen path lands in the field. The window
      is still draggable and responsive afterwards.
- [ ] **Browse picks the Gamelogs folder,** same expectations.
- [ ] **Cancelling a Browse changes nothing** — the field keeps its previous
      value, not blank and not the dialog's starting directory.
- [ ] **Detect fills in the recording folder from OBS's own config,** and a
      second press with the field already at that path says it is already
      set rather than silently re-filling it.
- [ ] **Detect fills in the Gamelogs folder,** with the same already-set
      behaviour. With no EVE install, Detect says so rather than leaving the
      field blank with no explanation.
- [ ] **Saving a changed recording folder rebinds the live watcher.** Change
      it and Save without restarting. New recordings in the NEW folder are
      announced and the old folder is ignored. Persisting without rebinding
      is the specific failure to watch for — it looks correct until the next
      recording.
- [ ] **LOAD-BEARING: the first-run folder screen.** Delete
      `%LOCALAPPDATA%\OBSYouTubeUploader\settings.json` and launch with OBS
      absent. Expected: the window opens and shows an in-app "choose your
      recording folder" screen, from which Browse opens the native picker
      and choosing proceeds to the normal list. This is a deliberate
      behaviour change: there is no longer a bare OS dialog before any
      window exists. Confirm the screen cannot be skipped past into an
      unusable empty list.
```

- [ ] **Step 4: Add dialog and progress sections**

Insert between the end of `## Single instance` and the `## Release` heading:

```
## Dialogs and confirmations

Modal dialogs were native `messagebox` calls and are now in-page modals fed
by `onDialog`, with `confirm` answered by `dialog_response(id, ok)` — the one
request/response pair in an otherwise fire-and-forget protocol. A dropped
response leaves a worker waiting forever, which presents as a hung upload.

- [ ] **LOAD-BEARING: Upload Selected confirms before publishing anything.**
      Select two recordings and press it. Expected: a modal naming the
      destination channel, the privacy setting, the exact title(s) including
      `(1/2)` … `(2/2)` numbering, and the total size and duration. Choose
      No: nothing uploads and the app is not left busy. Then repeat and
      choose Yes. This is the app's only irreversible action.
- [ ] **The confirm is honest before the first upload.** With no upload ever
      completed, the Channel line reads "not known yet (learned from this
      upload)" rather than being blank.
- [ ] **The delete confirmation lists the correct filenames,** warns it
      cannot be undone, Cancel deletes nothing, Confirm removes and
      refreshes.
- [ ] **The no-selection and busy warnings are distinct messages.** Press
      Upload Selected, Upload combat logs and Delete selected each with
      nothing selected, and read all three. Then start an upload and press
      the other two mid-flight. These are several specific messages, not one
      generic guard.
- [ ] **Escape and the scrim answer a confirm as "no", never as nothing.**
      Both cancel cleanly and the app is immediately usable — no upload, no
      stuck busy state, and Upload Selected works on the next press.
- [ ] **A dialog raised from a worker thread reaches the page.** Kill the
      network mid-upload and let the retries exhaust. The error modal
      appears with plain-language text, not a traceback, and the window is
      responsive behind it.

## Progress

- [ ] **LOAD-BEARING: the progress bar is indeterminate during a stitch.**
      Select two, tick Stitch, upload. While ffmpeg runs the bar animates
      continuously with NO percentage — stitching reports no progress and a
      bar sitting at 0% reads as a hang — and switches to a real percentage
      the moment the upload begins. Stitch twice in one session and confirm
      it switches back correctly.
- [ ] **Progress renders during a real upload.** Upload three recordings.
      "Uploading file 2 of 3… 41.2%" with the bar tracking the whole batch,
      updating smoothly rather than jumping only at file boundaries.
- [ ] **The window stays responsive throughout.** Mid-upload, drag the
      window, scroll the list, sort a column and open the context menu. A UI
      that stalls means work is running on the wrong thread.
- [ ] **The retry countdown is visible.** Kill the network mid-upload:
      "retrying in Ns" counting down, then a resume — not a frozen bar. When
      the retries are exhausted, Retry becomes enabled.
- [ ] **Status severity colours are distinguishable.** Force a red error, a
      green success and an ordinary status in one session. All three legible
      against the near-black ground and clearly different.
```

- [ ] **Step 5: Verify the checklist**

Run:
```bash
python3 - <<'PY'
import pathlib, sys
p = pathlib.Path("docs/smoke-checklist.md")
text = p.read_text(encoding="utf-8")
lines = text.splitlines()
problems = []

n = sum(1 for line in lines if "- [ ]" in line)
print(f"unchecked items: {n}")
# A floor, not an exact count: items are expected to be added over time, and
# an exact assertion would fail on every legitimate addition.
if n < 100:
    problems.append(f"only {n} unchecked items; the replatform sections are missing")
if "- [x]" in text or "- [X]" in text:
    problems.append("a checked box was committed; every item must ship unticked")

# Every Tk-only assertion must be gone with the Tk UI.
for dead in ("sv-ttk", "sv_ttk", "Treeview", "tk.Menu", "tk.Canvas",
             "tk scaling", "_tkinter_finder"):
    if dead in text:
        problems.append(f"stale Tk reference still present: {dead}")

for anchor in (
    "## WebView2 runtime", "NON-ZERO exit", "CLEAN VM ONLY",
    "the custom title bar drags the window", "close HIDES to the tray",
    "### Folder dialogs", "Detect fills in the recording folder",
    "Detect fills in the Gamelogs folder",
    "Click-to-sort works on every column",
    "arrow keys move focus and Space toggles",
    "the row context menu opens and dismisses",
    "LEAVES THE CHECKBOX SELECTION UNCHANGED",
    "## Dialogs and confirmations",
    "Upload Selected confirms before publishing",
    "The delete confirmation lists the correct filenames",
    "The webhook is still masked after a route change",
    "## Progress", "indeterminate during a stitch",
    "Progress renders during a real upload",
):
    if anchor not in text:
        problems.append(f"missing required item: {anchor!r}")

for line in problems:
    print(f"FAIL: {line}")
sys.exit(1 if problems else 0)
PY
```

Expected: an item count of at least 100, no `FAIL:` lines, exit 0. A stale Tk reference means part of the old section survived the Step 2 deletion.

- [ ] **Step 6: Commit**

```bash
git add docs/smoke-checklist.md
git commit -m "Extend the smoke checklist for the webview UI"
```
