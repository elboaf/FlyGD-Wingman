# UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inherited script-era Tkinter UI with a native-looking
Windows 11 interface — sv-ttk theming that follows the OS light/dark setting, a
real `ttk.Treeview` video list, DPI-sharp text, and a proper app icon — without
adding features or touching any logic module.

**Architecture:** A new `obs_youtube_uploader/theme.py` owns colour tokens, OS
theme detection, and a single `apply()` entry point that every window registers
with; live OS theme switches are driven from the existing 3-second `poll()` loop
rather than a new thread. The video list becomes a `ttk.Treeview` while
selection state stays in `dict[Path, tk.BooleanVar]`, so `_chosen`, `_set_all`,
and `_start_upload` are untouched. DPI awareness ships as its own commit because
it changes the physical meaning of every fixed pixel constant at once.

**Tech Stack:** Python 3.11+, Tkinter/ttk, sv-ttk, Pillow (already present for
pystray), PyInstaller 6.x, Inno Setup 6.3+.

**Spec:** `docs/superpowers/specs/2026-08-20-ui-refresh-design.md`

## Global Constraints

- **Presentation layer only.** Do not modify `library.py`, `stitch.py`,
  `uploader.py`, `watcher.py`, `obsconfig.py`, `settings.py`,
  `credentials.py`, `combatlog.py`, or `discord.py`. **One narrow exception:**
  Task 8 adds an *additive*
  `icon_file()` helper to `paths.py`. `paths.py` is a resource-location
  module, that is exactly the concern, and nothing existing in it changes —
  but `tests/test_paths.py` must still pass untouched. No other logic module
  may be edited for any reason; if a task seems to require it, stop and
  escalate.
- **No features.** No new settings, columns, filtering, thumbnails, or
  drag-to-reorder. Where a native widget changes a gesture (Copy/Open moving to
  a context menu) that is accepted; adding capability is not. **Do not remove
  capability either** — the **Upload combat logs** button and the **Discord
  (combat logs)** settings frame must survive every rewrite in this plan.
- **`python -m pytest tests/` must stay green** after every task, at the
  baseline count recorded in the ledger at execution start. The figure "175
  passed" was measured against `main` and is **obsolete** — `test_main.py`,
  `test_combatlog.py`, and `test_discord.py` do not exist there. Record the
  real baseline before Task 1 and gate on that number.
- **UI test coverage is almost, but not entirely, absent.** No file in `tests/`
  imports `app`, `settingsui`, or `UploaderWindow` — but `tests/test_main.py`
  imports `configure_logging` and `resolve_recording_dir` from `__main__`, so
  Tasks 3 and 4 (which edit `main()` and `poll()`) have a real automated gate.
  Do not invent assert-nothing tests for the rest; `docs/smoke-checklist.md` is
  the verification surface, and Task 9 updates it.
- **`theme.py` is the single theming owner.** Windows register consumers with
  it. No module applies a theme, resolves a raw colour, or regenerates a themed
  image on its own.
- **Degrade, never block startup — for optional presentation capabilities.**
  Theme application, icon loading, and DPI calls must not raise. Follow
  `configure_logging` and `resolve_binary`. Note this is *not* a codebase-wide
  rule: `paths.ensure_dirs()` and the initial `settings_mod.save(cfg)` in
  `main()` are deliberately unguarded startup requirements — leave them alone.
- **Log through the existing rotating handler.** With `console=False` in
  `packaging/uploader.spec`, `logging.getLogger(__name__).warning(...,
  exc_info=True)` is the only place a swallowed failure can surface.
- **Windows-only guards follow the existing pattern:** `sys.platform !=
  "win32"` early-return, as in `acquire_single_instance()`. The test suite runs
  on Linux in CI and must keep passing.
- **Tk is not thread-safe.** Worker threads reach the UI only through
  `UploaderWindow._ui()` (which wraps `root.after`). No task may introduce a
  thread that touches a widget directly.
- **Conventional commits**, one commit per task minimum.

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `obs_youtube_uploader/theme.py` | Colour tokens, OS theme detection, the single `apply()` owner, consumer registry. The only module that knows a hex colour. |
| `tests/test_theme.py` | Unit tests for token resolution and mode detection — the one genuinely testable piece of this plan. |
| `obs_youtube_uploader/assets/app.ico` | Application icon: both windows, tray, executable. |

**Modified:**

| Path | Change |
|---|---|
| `obs_youtube_uploader/app.py` | `Treeview` list, action bar, status bar, token consumers. The largest change. |
| `obs_youtube_uploader/settingsui.py` | Spacing scale, auth status row, label alignment, accent Save. |
| `obs_youtube_uploader/__main__.py` | DPI awareness, theme application at startup, live switch in `poll()`, real tray icon. |
| `packaging/uploader.spec` | `datas` for sv-ttk `.tcl` files and the icon; `icon=` on `EXE`. |
| `.github/workflows/build.yml` | `sv_ttk` in the importability check, plus a new post-build bundle assertion. |
| `pyproject.toml` | `sv-ttk` dependency. |
| `docs/smoke-checklist.md` | New and reworded manual verification items. |

**Deliberately untouched:** every logic module, `packaging/installer.iss` (the
icon reaches it for free via `UninstallDisplayIcon`), and `.github/workflows/ci.yml`.

## Task Order and Rationale

1. **Packaging first** (Task 1) so the frozen build proves sv-ttk ships
   *before* any visual work depends on it — the spec's explicit sequencing.
2. **`theme.py`** (Task 2) — the only genuinely unit-testable piece.
3. **Startup + live switch** (Task 3) — makes Task 2's registry real.
4. **DPI** (Task 4) isolated between the theming work and the list rewrite so
   its smoke pass is entangled with neither.
5. **`Treeview`** (Task 5), then **chrome** (Task 6) — the list is rewritten
   before the bar around it is regrouped, so the chrome task lays out against
   the final list widget rather than one that is about to be deleted.
6. **Settings dialog** (Task 7), **icon** (Task 8), **checklist** (Task 9) last.

### Theming ownership: one consumer per window, registered once

Each window registers **exactly one** `theme.register(...)` consumer, named
`_on_theme_changed` in both `UploaderWindow` and `SettingsWindow`. Do not add
a second consumer to a window that already has one, and do not invent a
differently-named one — a window with two consumers double-applies on every
switch and the second silently masks bugs in the first.

Because of this, the colour-token migration is **not** a standalone task. Each
token consumer is written by the task that owns the widget it colours:

| Widget | Owning task |
|---|---|
| Checkbox images, `Treeview` row tags, link cell | Task 5 |
| Status line, ffmpeg warning, action bar | Task 6 |
| Auth status row, hint labels | Task 7 |

`UploaderWindow._on_theme_changed` is therefore **created in Task 5 and
extended in Task 6** — Task 6 adds to the existing method, it does not define
a second one.

### `SettingsWindow` must unregister — deviation from the spec

The spec's §1 "single owner" design says windows register with `theme.py`, but
did not say how they *un*-register. Assembling the tasks exposed the gap:
`SettingsWindow` is constructed fresh on every `_open_settings()` call, so
without removal, opening Settings ten times leaves ten consumers in
`theme._consumers`, nine of them holding destroyed `Toplevel`s. Every
subsequent theme switch then raises `TclError` nine times — caught and logged
by `apply()`, so not fatal, but a genuine leak and a log-spam source.

Task 2 therefore also provides `unregister(consumer)`, and `SettingsWindow`
calls it from its destroy path. This is a deliberate amendment to the spec,
recorded here rather than applied silently.

---

### Task 1: sv-ttk dependency and frozen-bundle proof

**Files:**
- Modify: `pyproject.toml:6-11`
- Modify: `packaging/uploader.spec:1-16`
- Modify: `.github/workflows/build.yml:53-60`
- Modify: `.github/workflows/build.yml:88-113` (insert new step after this one)

**Interfaces:**
- Consumes: Nothing
- Produces: A bundled `sv_ttk` package (with its `.tcl` theme data) under `dist/OBSYouTubeUploader/_internal/sv_ttk/` in the frozen build — this is what `theme.py` (Task 2) and `__main__.py`'s later `sv_ttk.set_theme(...)` call depend on at runtime.

This task has no unit tests — it is packaging config and CI workflow only. `python -m pytest tests/` cannot exercise PyInstaller's `Analysis.datas` resolution or the Windows-only build runner, so verification here is concrete commands and, ultimately, a `workflow_dispatch` run.

- [ ] **Step 1: Add `sv-ttk` to `pyproject.toml` dependencies**

Current block:

```toml
dependencies = [
    "google-api-python-client",
    "google-auth-oauthlib",
    "google-auth-httplib2",
    "pystray",
    "Pillow",
]
```

Edited:

```toml
dependencies = [
    "google-api-python-client",
    "google-auth-oauthlib",
    "google-auth-httplib2",
    "pystray",
    "Pillow",
    "sv-ttk",
]
```

Verify it installs cleanly:

```bash
pip install -e .
python -c "import sv_ttk; print(sv_ttk.__file__)"
```

Commit:

```bash
git add pyproject.toml
git commit -m "build: add sv-ttk dependency for themed ttk chrome"
```

- [ ] **Step 2: Bundle sv-ttk's `.tcl` data in the PyInstaller spec**

`packaging/uploader.spec` currently has no imports beyond `Path` and an empty `datas=[]`:

```python
# packaging/uploader.spec
# One-folder build. Deliberately not one-file: one-file unpacks to temp on
# every launch (slow with ffmpeg bundled) and trips antivirus heuristics
# markedly more often.
from pathlib import Path

ROOT = Path(SPECPATH).parent
BIN = ROOT / "packaging" / "bin"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[
        (str(BIN / "ffmpeg.exe"), "bin"),
        (str(BIN / "ffprobe.exe"), "bin"),
    ],
    datas=[],
```

Edited (two changes: the new import, and `datas=[]` → `datas=collect_data_files("sv_ttk")`):

```python
# packaging/uploader.spec
# One-folder build. Deliberately not one-file: one-file unpacks to temp on
# every launch (slow with ffmpeg bundled) and trips antivirus heuristics
# markedly more often.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
BIN = ROOT / "packaging" / "bin"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[
        (str(BIN / "ffmpeg.exe"), "bin"),
        (str(BIN / "ffprobe.exe"), "bin"),
    ],
    # sv-ttk ships its theme as .tcl files (sun-valley.tcl,
    # theme/light.tcl, theme/dark.tcl) plus image assets. modulegraph only
    # follows Python imports, so without this the package's .py file lands
    # in the bundle but sv_ttk.set_theme() fails at runtime looking for
    # data that was never copied. PyInstaller exits 0 either way (see the
    # ffmpeg comment below), which is why build.yml also gets a post-build
    # assertion in Step 4.
    datas=collect_data_files("sv_ttk"),
```

Confirm locally which files this actually collects (informational only — the real proof is the frozen build in Step 6):

```bash
python -c "from PyInstaller.utils.hooks import collect_data_files; [print(d) for d in collect_data_files('sv_ttk')]"
```

Commit:

```bash
git add packaging/uploader.spec
git commit -m "build: bundle sv-ttk's .tcl theme data in the frozen app"
```

- [ ] **Step 3: Add `sv_ttk` to the pre-build importability check**

`.github/workflows/build.yml`, existing step:

```yaml
      - name: Verify the app's dependencies are importable
        # PyInstaller only reports "Hidden import not found" as an ERROR line
        # and still exits 0, so a missing dependency yields a successful build
        # of a broken application. Fail here instead, where it is obvious.
        shell: pwsh
        run: |
          python -c "import pystray, PIL, googleapiclient, google_auth_oauthlib; print('runtime deps importable')"
          if ($LASTEXITCODE -ne 0) { throw "the app's runtime dependencies are not installed" }
```

Edited:

```yaml
      - name: Verify the app's dependencies are importable
        # PyInstaller only reports "Hidden import not found" as an ERROR line
        # and still exits 0, so a missing dependency yields a successful build
        # of a broken application. Fail here instead, where it is obvious.
        #
        # This only proves sv_ttk is installed on the *build* runner, before
        # PyInstaller has run - it says nothing about whether the .tcl data
        # actually reached the frozen bundle. See the post-build assertion
        # below for that.
        shell: pwsh
        run: |
          python -c "import pystray, PIL, googleapiclient, google_auth_oauthlib, sv_ttk; print('runtime deps importable')"
          if ($LASTEXITCODE -ne 0) { throw "the app's runtime dependencies are not installed" }
```

Commit:

```bash
git add .github/workflows/build.yml
git commit -m "ci: verify sv_ttk is importable in the build environment"
```

- [ ] **Step 4: Add a post-build assertion that sv-ttk's theme data reached the bundle**

Insert a new step immediately after the existing "Show what PyInstaller produced" step and before "Build installer" (`.github/workflows/build.yml`, around line 113):

```yaml
      - name: Verify sv-ttk theme data is bundled
        # Mirrors the ffmpeg check above and exists for the same reason:
        # PyInstaller exits 0 even when a `datas` entry resolves to nothing,
        # so a wrong collect_data_files() call would produce a green build
        # of an app that raises the moment __main__.py calls
        # sv_ttk.set_theme() - and nothing in CI would notice without this.
        # This assertion only proves the files are present; it cannot prove
        # they load correctly, which is what actually launching the app
        # (manually, from the downloaded artifact) is for.
        shell: pwsh
        run: |
          $svTtk = "dist\OBSYouTubeUploader\_internal\sv_ttk"
          if (-not (Test-Path $svTtk)) {
            throw "sv_ttk package data not found at $svTtk - the datas= entry in uploader.spec did not collect it, and sv_ttk.set_theme() will fail at runtime"
          }
          Get-ChildItem -Recurse $svTtk
          foreach ($tcl in @("sun-valley.tcl", "theme\light.tcl", "theme\dark.tcl")) {
            $path = Join-Path $svTtk $tcl
            if (-not (Test-Path $path)) { throw "$tcl missing from bundled sv_ttk data at $path" }
          }
```

Commit:

```bash
git add .github/workflows/build.yml
git commit -m "ci: assert sv-ttk theme data lands in the frozen bundle"
```

- [ ] **Step 5: Confirm the logic test suite is unaffected**

```bash
python -m pytest tests/
```

Expected: the ledger's recorded baseline count, unchanged. None of these edits touch a logic module, so this is a sanity check, not new coverage.

- [ ] **Step 6: Trigger the `workflow_dispatch` "Test build" workflow and confirm**

```bash
gh workflow run "Test build" --ref <branch>
gh run watch <run-id>
```

Confirm, in order:
1. "Verify the app's dependencies are importable" passes (sv_ttk importable on the runner).
2. The new "Verify sv-ttk theme data is bundled" step passes and its `Get-ChildItem -Recurse` output shows `sun-valley.tcl`, `theme/light.tcl`, and `theme/dark.tcl`.
3. Download the `OBS-YouTube-Uploader-unpacked` artifact and launch `OBSYouTubeUploader.exe` directly — it must start without a traceback dialog. The bundle assertion only proves the files exist; only launching proves they're loadable. (No theme is applied to anything yet at this point in the plan — this run only proves the packaging plumbing works.)

Record the run URL and pass/fail in the PR description when this task is executed.

---

### Task 2: theme.py — tokens, OS detection, single apply owner

**Files:**
- Create: `obs_youtube_uploader/theme.py`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: Nothing (Task 1's bundled `sv_ttk` is what `apply()` imports and calls at runtime; this task's tests monkeypatch that dependency out, so it does not block on Task 1 landing first)
- Produces:
  ```python
  Mode = str  # "light" | "dark"
  TOKENS: dict[str, dict[str, str]]
  def read_apps_use_light_theme() -> int | None
  def detect_mode(reader=read_apps_use_light_theme) -> Mode
  def current_mode() -> Mode
  def token(name: str, mode: Mode | None = None) -> str
  def register(consumer) -> None
  def unregister(consumer) -> None
  def apply(root, mode: Mode) -> None
  ```
  Later tasks (colour-token consumers in `app.py`/`settingsui.py`, the `Treeview` row tags, `__main__.py`'s startup call and `poll()`'s registry-check block) call `theme.token(...)`, `theme.register(...)`, and `theme.apply(...)` exactly as declared above.

- [ ] **Step 1: Write the failing test for `detect_mode`**

Create `tests/test_theme.py`:

```python
import logging

import pytest

from obs_youtube_uploader import theme


@pytest.fixture(autouse=True)
def _clear_consumers():
    """theme._consumers is module-level state that register() mutates;
    without this, consumers registered by one test leak into the next."""
    saved = list(theme._consumers)
    theme._consumers.clear()
    yield
    theme._consumers.clear()
    theme._consumers.extend(saved)


def test_detect_mode_dark_when_reader_returns_zero():
    assert theme.detect_mode(reader=lambda: 0) == "dark"


def test_detect_mode_light_when_reader_returns_one():
    assert theme.detect_mode(reader=lambda: 1) == "light"


def test_detect_mode_light_when_reader_returns_none():
    # Safe default: an unreadable registry value must not be treated as dark.
    assert theme.detect_mode(reader=lambda: None) == "light"
```

Run it and show the expected failure (module doesn't exist yet):

```bash
python -m pytest tests/test_theme.py -v
```

Expected: `ModuleNotFoundError: No module named 'obs_youtube_uploader.theme'` (or a collection error to that effect).

- [ ] **Step 2: Minimal implementation — `read_apps_use_light_theme` and `detect_mode`**

Create `obs_youtube_uploader/theme.py`:

```python
"""Theme tokens, OS dark/light detection, and the single apply() entry point.

sv-ttk restyles ttk widgets only. Everything else in this app - directly
assigned widget colours, Treeview row tags, the classic tk.Text box, and the
generated checkbox images - must be re-themed explicitly, and a live OS theme
switch means re-doing it to widgets that already exist. apply() is therefore
the one place that owns re-theming: it sets the sv-ttk theme and then walks
every registered consumer. Nothing else re-themes itself ad hoc, or a live
switch produces a half-themed window.
"""
import logging
import sys
from typing import Callable

log = logging.getLogger(__name__)

Mode = str  # "light" | "dark"

try:
    import sv_ttk
except ImportError:  # pragma: no cover - exercised via monkeypatch, not absence
    sv_ttk = None


def read_apps_use_light_theme() -> int | None:
    """Read HKCU...Personalize\\AppsUseLightTheme. None on any failure or
    off-Windows - this is an optional presentation capability, not a
    startup requirement, so it degrades rather than raises."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return int(value)
    except Exception:
        return None


def detect_mode(reader=read_apps_use_light_theme) -> Mode:
    """reader is injectable so this is testable off-Windows, mirroring
    library.py's runner= convention for subprocess.run."""
    if reader() == 0:
        return "dark"
    return "light"
```

Run it:

```bash
python -m pytest tests/test_theme.py -v
```

Expected: the 3 `detect_mode` tests pass.

Commit:

```bash
git add obs_youtube_uploader/theme.py tests/test_theme.py
git commit -m "feat: add theme.detect_mode with an injectable registry reader"
```

- [ ] **Step 3: Write failing tests for `TOKENS` and `token()`**

Append to `tests/test_theme.py`:

```python
TOKEN_NAMES = [
    "SUCCESS",
    "ERROR",
    "WARNING",
    "MUTED",
    "LINK",
    "FG",
    "ROW_ODD",
    "ROW_EVEN",
    "ROW_PRESELECT",
]


def test_tokens_has_exactly_light_and_dark_modes():
    assert set(theme.TOKENS.keys()) == {"light", "dark"}


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("name", TOKEN_NAMES)
def test_every_token_name_present_in_both_modes(mode, name):
    assert name in theme.TOKENS[mode]
    assert theme.TOKENS[mode][name].startswith("#")


def test_token_uses_explicit_mode():
    assert theme.token("SUCCESS", "dark") == theme.TOKENS["dark"]["SUCCESS"]


def test_token_defaults_to_current_mode(monkeypatch):
    monkeypatch.setattr(theme, "current_mode", lambda: "dark")
    assert theme.token("SUCCESS") == theme.TOKENS["dark"]["SUCCESS"]


def test_token_raises_keyerror_on_unknown_name():
    with pytest.raises(KeyError):
        theme.token("NOT_A_REAL_TOKEN", "light")
```

Run it and show the expected failure:

```bash
python -m pytest tests/test_theme.py -v
```

Expected: `AttributeError: module 'obs_youtube_uploader.theme' has no attribute 'TOKENS'` (and no `token`/`current_mode`).

- [ ] **Step 4: Minimal implementation — `TOKENS`, `current_mode`, `token`**

Append to `obs_youtube_uploader/theme.py`:

```python
TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "SUCCESS": "#1a7f37",
        "ERROR": "#c0392b",
        "WARNING": "#b8860b",
        "MUTED": "#6c6c6c",
        "LINK": "#0645ad",
        # Neutral status foreground. Exists because _combat_log_worker sets
        # foreground="black" literally, which is invisible on a dark
        # background - a real bug, not just a suboptimal shade.
        "FG": "#1a1a1a",
        "ROW_ODD": "#ffffff",
        "ROW_EVEN": "#f5f5f5",
        "ROW_PRESELECT": "#fff3b0",
    },
    "dark": {
        "SUCCESS": "#3fb950",
        "ERROR": "#f85149",
        "WARNING": "#d29922",
        "MUTED": "#9198a1",
        "LINK": "#58a6ff",
        "FG": "#e6edf3",
        "ROW_ODD": "#1e1e1e",
        "ROW_EVEN": "#252526",
        "ROW_PRESELECT": "#3a3a1e",
    },
}

# Module-level "current" mode, mutated only by apply(). Seeded from a real
# detection at import time so token()/current_mode() are sensible even
# before __main__.py calls apply() once at startup.
_current_mode: Mode = detect_mode()

_consumers: list[Callable[[Mode], None]] = []


def current_mode() -> Mode:
    return _current_mode


def token(name: str, mode: Mode | None = None) -> str:
    """Raises KeyError for an unknown token name - a typo here should fail
    loudly in a test, not silently render as a missing colour."""
    return TOKENS[mode if mode is not None else current_mode()][name]
```

Run it:

```bash
python -m pytest tests/test_theme.py -v
```

Expected: all tests so far pass.

Commit:

```bash
git add obs_youtube_uploader/theme.py tests/test_theme.py
git commit -m "feat: add theme.TOKENS and theme.token() lookup"
```

- [ ] **Step 5: Write failing tests for `register`/`apply`**

Append to `tests/test_theme.py`:

```python
class _FakeRoot:
    """Stand-in for tk.Tk() - apply() must not require a real display,
    since this test suite runs on ubuntu-latest with no Tk available."""


def test_apply_calls_every_registered_consumer_with_the_mode(monkeypatch):
    monkeypatch.setattr(theme, "sv_ttk", None)
    calls = []
    theme.register(lambda mode: calls.append(("a", mode)))
    theme.register(lambda mode: calls.append(("b", mode)))

    theme.apply(_FakeRoot(), "dark")

    assert calls == [("a", "dark"), ("b", "dark")]
    assert theme.current_mode() == "dark"


def test_apply_continues_past_a_raising_consumer(monkeypatch, caplog):
    monkeypatch.setattr(theme, "sv_ttk", None)
    calls = []

    def bad(mode):
        raise RuntimeError("boom")

    theme.register(bad)
    theme.register(lambda mode: calls.append(mode))

    with caplog.at_level(logging.WARNING):
        theme.apply(_FakeRoot(), "light")

    assert calls == ["light"]  # the second consumer still ran
    assert any("boom" in r.message or r.exc_info for r in caplog.records)


def test_apply_never_raises_when_sv_ttk_is_unavailable(monkeypatch):
    monkeypatch.setattr(theme, "sv_ttk", None)
    theme.apply(_FakeRoot(), "dark")  # must not raise


def test_apply_swallows_sv_ttk_set_theme_failure(monkeypatch, caplog):
    class _BadSvTtk:
        @staticmethod
        def set_theme(mode, root=None):
            raise RuntimeError("no display")

    monkeypatch.setattr(theme, "sv_ttk", _BadSvTtk())
    calls = []
    theme.register(lambda mode: calls.append(mode))

    with caplog.at_level(logging.WARNING):
        theme.apply(_FakeRoot(), "dark")  # must not raise

    assert calls == ["dark"]  # consumers still run even though sv_ttk failed


def test_unregister_removes_the_consumer(monkeypatch):
    monkeypatch.setattr(theme, "sv_ttk", None)
    calls = []

    def consumer(mode):
        calls.append(mode)

    theme.register(consumer)
    theme.unregister(consumer)
    theme.apply(_FakeRoot(), "dark")

    assert calls == []


def test_unregister_is_idempotent():
    # SettingsWindow may be destroyed more than once in edge cases; a
    # double-unregister must not raise.
    theme.unregister(lambda mode: None)  # never registered - must be a no-op
```

Run it and show the expected failure:

```bash
python -m pytest tests/test_theme.py -v
```

Expected: `AttributeError: module 'obs_youtube_uploader.theme' has no attribute 'register'` (and `apply`).

- [ ] **Step 6: Minimal implementation — `register` and `apply`**

Append to `obs_youtube_uploader/theme.py`:

```python
def register(consumer: Callable[[Mode], None]) -> None:
    """consumer is called with the active Mode on every apply(), both at
    startup and on a live OS theme switch. Windows register themselves here
    instead of re-theming ad hoc - see the module docstring."""
    _consumers.append(consumer)


def unregister(consumer: Callable[[Mode], None]) -> None:
    """Remove a consumer. Idempotent: removing one that was never
    registered is a no-op, not an error.

    SettingsWindow is rebuilt on every _open_settings() call, so without
    this each open would leave another consumer holding a destroyed
    Toplevel behind. apply() would then raise TclError once per stale
    window on every theme switch - caught and logged, but a real leak.
    """
    try:
        _consumers.remove(consumer)
    except ValueError:
        pass


def apply(root, mode: Mode) -> None:
    """The single owner of re-theming. Must never raise: a failure here is
    an optional presentation capability, not a startup requirement (unlike
    paths.ensure_dirs() or settings.save() in main()), so it is wrapped the
    same way resolve_binary/probe_duration/icon.notify are - degrade, don't
    crash the app or kill a live switch."""
    global _current_mode
    _current_mode = mode

    if sv_ttk is not None:
        try:
            sv_ttk.set_theme(mode, root=root)
        except Exception:
            log.warning("sv_ttk.set_theme(%r) failed", mode, exc_info=True)

    for consumer in _consumers:
        try:
            consumer(mode)
        except Exception:
            log.warning(
                "theme consumer %r raised while applying mode %r",
                consumer, mode, exc_info=True,
            )
```

Run the full suite:

```bash
python -m pytest tests/test_theme.py -v
python -m pytest tests/
```

Expected: all `test_theme.py` cases pass, and every pre-existing test still passes. The new total is the ledger's baseline plus however many cases `test_theme.py` expands to under `parametrize` — check that no pre-existing test changed status rather than matching an exact total.

Commit:

```bash
git add obs_youtube_uploader/theme.py tests/test_theme.py
git commit -m "feat: add theme.register/apply as the single re-theming entry point"
```

- [ ] **Step 7: Final review pass**

```bash
python -m pytest tests/ -v
```

Confirm: no test outside `tests/test_theme.py` changed status, and `theme.py` exports exactly the interface declared above and nothing later tasks rely on that isn't in that list.

---

### Task 3: Wire theming into startup and live OS switching

**Files:**
- Modify: `obs_youtube_uploader/__main__.py:1-17` (imports)
- Modify: `obs_youtube_uploader/__main__.py:115-137` (`main()` startup)
- Modify: `obs_youtube_uploader/__main__.py:161-225` (`poll()`)

**Interfaces:**
- Consumes: `theme.detect_mode() -> str`, `theme.current_mode() -> str`, `theme.apply(root, mode) -> None` (never raises).
- Produces: the app is themed at startup and stays in sync with the OS while running. Every later task's `_on_theme_changed` consumer is dead code without this.

- [ ] **Step 1: Import `theme` in `__main__.py`**

```python
from . import app as app_mod
from . import obsconfig, paths, settings as settings_mod, stitch, theme, watcher
```

- [ ] **Step 2: Apply the theme once at startup, before the window is built**

```python
    root = tk.Tk()
    root.withdraw()  # Created on the main thread up front, shown on demand.
    theme.apply(root, theme.detect_mode())

    rec_dir = resolve_recording_dir(cfg)
```

`theme.apply` never raises, so no extra `try/except` is needed here — a failure inside it degrades to default `ttk`.

- [ ] **Step 3: Give the theme check in `poll()` its own try/except, separate from the watcher's**

The watcher's existing `except Exception` increments `consecutive_failures` and eventually fires the "watcher is having trouble" notification at `FAILURE_NOTIFY_THRESHOLD`. A registry read failure must never feed that counter. Add a second, independent `try/except` at the top of `poll()`:

```python
    def poll() -> None:
        # Everything here is guarded by a single try/finally so the loop
        # always reschedules itself: a `poll_once()` error, or an error
        # raised while showing/refreshing the window, must not silently
        # and permanently kill the watcher with no error shown to the user.
        nonlocal consecutive_failures, refresh_deferred
        try:
            # Independent of the watcher block below: a failed registry
            # read is a theming problem, not a watcher problem, and must
            # never be counted toward FAILURE_NOTIFY_THRESHOLD.
            detected_mode = theme.detect_mode()
            if detected_mode != theme.current_mode():
                theme.apply(root, detected_mode)
        except Exception:
            logger.warning("Theme check failed", exc_info=True)
        try:
            ready = w.poll_once()
            ...  # (the entire existing watcher body is UNCHANGED below this point)
```

The rest of `poll()` — the `ready`/`uploading` handling, the deferred-refresh `elif`, `consecutive_failures = 0`, the watcher's own `except`, and the `finally` that reschedules — is left exactly as it is today. Do not re-indent or restructure it.

The `if detected_mode != theme.current_mode()` guard is required: `poll()` runs every 3 seconds, and re-applying sv-ttk plus regenerating checkbox images unconditionally would flicker the whole UI.

- [ ] **Step 4: Run the existing suite**

```bash
python -m pytest tests/
```

Expect the ledger's baseline plus Task 2's theme tests; no pre-existing test changes status. **`tests/test_main.py` is the one that matters here** — it imports `configure_logging` and `resolve_recording_dir` from `__main__`, the file this task edits.

- [ ] **Step 5: Manual verification (no automated UI coverage exists)**

1. Launch the app, open the main window (tray icon → "Open uploader") and Settings. Both render in the theme matching `Settings > Personalization > Colors > Choose your mode`.
2. With both windows open, flip Windows between Light and Dark. Within ~3 seconds both re-theme.
3. Rename or unmount the recording folder while running, so `w.poll_once()` throws. Confirm exactly **one** "watcher is having trouble" notification after ~15s (5 failures × 3s) — not sooner, not repeated. This is the proof that the theme `try/except` is isolated from the watcher's counter.

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/__main__.py
git commit -m "feat: apply theme at startup and follow live OS theme changes"
```

---

### Task 4: DPI awareness (its own commit)

**Files:**
- Modify: `obs_youtube_uploader/__main__.py` (new helpers + `main()`)
- Modify: `obs_youtube_uploader/app.py` (new `dpi_scale` helper near `resolve_binary`; geometry)
- Modify: `obs_youtube_uploader/settingsui.py:30-44` (sizing block)

**Interfaces:**
- Consumes: Nothing from `theme.py`.
- Produces: `app.dpi_scale(widget) -> float`, imported by `settingsui.py` and used by Task 5 for checkbox image sizing. **Task 5 must use this helper, not its own `winfo_fpixels` calculation** — two different scale computations would drift.

- [ ] **Step 1: Declare process DPI awareness before any window exists**

In `__main__.py`, near `acquire_single_instance` (same guard style):

```python
def set_dpi_awareness() -> None:
    """PROCESS_SYSTEM_DPI_AWARE, not Per-Monitor V2.

    System-DPI-aware is correct for a single-window tray utility and avoids
    handling WM_DPICHANGED when the window is dragged between monitors of
    different scale. Guarded exactly as acquire_single_instance() guards its
    Win32 call: off-Windows the process simply stays DPI-unaware, which only
    matters for local development.
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
    except (AttributeError, OSError):
        pass  # shcore.dll predates Windows 8.1; nothing to do on older hosts.


def get_system_dpi() -> int:
    """96 (100%) is the correct fallback off-Windows or on very old hosts."""
    if sys.platform != "win32":
        return 96
    import ctypes
    try:
        return ctypes.windll.user32.GetDpiForSystem()
    except (AttributeError, OSError):
        return 96
```

Call it as the very first line of `main()`, before the mutex and before any Tk call:

```python
def main() -> int:
    set_dpi_awareness()
    handle = acquire_single_instance()
```

- [ ] **Step 2: Set `tk scaling` once, immediately after the root exists**

```python
    root = tk.Tk()
    root.withdraw()  # Created on the main thread up front, shown on demand.
    root.tk.call("tk", "scaling", get_system_dpi() / 72.0)  # points-per-pixel, not /96
    theme.apply(root, theme.detect_mode())
```

This must be the **only** `tk scaling` call in the codebase. Double-scaling is this task's whole risk.

- [ ] **Step 3: Add the shared scale-factor helper in `app.py`**

Next to `resolve_binary` (no import cycle: `app.py` imports `settingsui` lazily inside `_open_settings`):

```python
def dpi_scale(widget: tk.Misc) -> float:
    """Scale factor relative to 100% (96 DPI), for pixel constants chosen
    before this process was DPI-aware.

    `tk scaling` is points-per-pixel (set once in __main__.py as dpi/72);
    dividing by the 96-DPI baseline's own scaling value (96/72) converts
    that back to a plain "1.0 at 100%, 1.5 at 150%" multiplier.
    """
    return float(widget.tk.call("tk", "scaling")) / (96.0 / 72.0)
```

- [ ] **Step 4: Scale `app.py`'s fixed geometry, clamped to the screen**

Replacing the literal `root.geometry("1350x650")` / `root.minsize(750, 450)` lines (`root.title(...)` stays immediately above):

```python
        scale = dpi_scale(root)
        width = min(int(1350 * scale), root.winfo_screenwidth())
        height = min(int(650 * scale), root.winfo_screenheight())
        root.geometry(f"{width}x{height}")
        root.minsize(int(750 * scale), int(450 * scale))
```

- [ ] **Step 5: Scale `settingsui.py`'s `max(520, ...)` floor, updating the b23f9cc comment rather than deleting it**

```python
        # Size the window to what its content actually needs rather than a
        # fixed guess: at higher Windows display-scaling factors (125%,
        # 150%) the six packed LabelFrames are taller than any hard-coded
        # height, which used to clip the Recording folder frame and the
        # Save/Cancel row right off the bottom of the dialog (fixed in
        # b23f9cc, when there were five — the Discord frame has since been
        # added, so there is more content to clip, not less). Now that the
        # process declares DPI awareness (PROCESS_SYSTEM_DPI_AWARE,
        # __main__.py) instead of being bitmap-stretched by the OS,
        # winfo_reqwidth/winfo_reqheight already reflect real scaled pixels
        # — but the *floor* below was chosen in the pre-DPI-aware world and
        # must scale with it too, or it under-sizes the dialog at 125%/150%
        # relative to today's fix. Compute the natural size after layout,
        # keep a scaled starting width, and let height follow the content,
        # clamped to the screen so the dialog cannot open larger than the
        # work area at 150%. Resizable + minsize means a user at an unusual
        # DPI or font size is never trapped below the window's usable size.
        self.win.update_idletasks()
        scale = app_mod.dpi_scale(self.win)
        width = max(int(520 * scale), self.win.winfo_reqwidth())
        width = min(width, self.win.winfo_screenwidth())
        height = min(self.win.winfo_reqheight(), self.win.winfo_screenheight())
        self.win.geometry(f"{width}x{height}")
        self.win.minsize(width, height)
        self.win.resizable(True, True)
```

Import it at the top of `settingsui.py` as `from . import app as app_mod` — `app.py` only imports `settingsui` lazily inside `_open_settings()`, so this does not create a cycle.

- [ ] **Step 6: Run the existing suite**

```bash
python -m pytest tests/
```

Expect no pre-existing test to change status.

- [ ] **Step 7: Manual verification at 100%, 125%, and 150% (`Settings > Display > Scale`)**

1. At each scale, launch fresh: the main window opens fully on-screen with text at native sharpness, not blurry.
2. At each scale, open Settings and **re-run the exact b23f9cc clipping check**: the "Recording folder" frame and the Save/Cancel row must both be fully visible.
3. At 150%, neither window opens larger than the screen, and `minsize` still prevents shrinking below usable size.
4. Resize each window by hand at each scale — no widget overlaps or truncates.

- [ ] **Step 8: Commit (separately, per spec §4)**

```bash
git add obs_youtube_uploader/__main__.py obs_youtube_uploader/app.py obs_youtube_uploader/settingsui.py
git commit -m "feat: declare DPI awareness and scale fixed pixel constants"
```

---

### Task 5: Replace the hand-built list with `ttk.Treeview`

**Files:**
- Modify: `obs_youtube_uploader/app.py:1-11` (imports), `:82-98` (`__init__`), `:108-163` (`_build`, list portion), `:165-196` (`refresh`), `:205-229` (`_copy`, `_open`, `_set_link`)

**Interfaces:**
- Consumes: `theme.token`, `theme.register`, `theme.current_mode`; `app.dpi_scale(widget)` from Task 4; `library.VideoInfo.date_str/size_str/duration_str` (unchanged).
- Produces: `self.tree: ttk.Treeview`; `self.links: dict[Path, str]` (**type change** from `dict[Path, tk.Entry]`); `self._checkbox_images: dict[bool, tk.PhotoImage]`; `self._preselected: set[Path]`; `self._sort_reverse: dict[str, bool]`; `_copy(path)` / `_open(path)` (**signature change** — they took a `tk.Entry` before); and `UploaderWindow._on_theme_changed(mode)`, **which Task 6 extends rather than replacing**.
- `self.selected: dict[Path, tk.BooleanVar]` is unchanged in type and semantics, so `_chosen`, `_set_all`, and `_start_upload` need **zero edits** and are not touched.

**Why sorting is safe:** `_chosen()` iterates `self.infos`, populated in discovery order — it never reads Treeview display order. `stitch.order_for_stitch()` independently re-sorts by `mtime`. Reordering rows therefore cannot change which files upload, in what order, or how stitched output is numbered. This task only calls `self.tree.move(...)`; `self.infos` order is never touched.

- [ ] **Step 1: Add the `theme` import and new instance state**

```python
from . import library, paths, settings as settings_mod, stitch, theme, uploader
```

```python
    def __init__(self, root: tk.Tk, state: AppState):
        self.root = root
        self.state = state
        self.infos: list[library.VideoInfo] = []
        self.selected: dict[Path, tk.BooleanVar] = {}
        self.links: dict[Path, str] = {}
        self._preselected: set[Path] = set()
        self._sort_reverse: dict[str, bool] = {}
        self._checkbox_images: dict[bool, tk.PhotoImage] = {}
        self.upload_thread: threading.Thread | None = None
        self.on_deleted = None  # set by the tray app to notify the watcher
        self.on_settings_saved = None  # set by the tray app; see _settings_saved
        self.retry_state: "RetryState | None" = None
```

(The `root.title` / geometry / `protocol` / `_build()` / `refresh()` lines that follow are unchanged here — Task 4 already rewrote the geometry lines.)

- [ ] **Step 2: Replace the header/canvas/scrollbar/inner-frame block with a `ttk.Treeview`**

Removes the `hdr` row, `Canvas`, `Scrollbar`, and `inner` frame entirely:

```python
        self.list_frame = ttk.Frame(self.root)
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=5)

        # Task 4's shared helper — do not compute scale independently here,
        # or checkbox images and window geometry can disagree.
        self._dpi_scale = dpi_scale(self.root)

        self.tree = ttk.Treeview(
            self.list_frame,
            columns=("filename", "date", "size", "duration", "link"),
            show="tree headings",
            selectmode="none",
        )
        self.tree.heading("#0", text="☑", command=lambda: self._sort_by("checked"))
        self.tree.column("#0", width=int(34 * self._dpi_scale), anchor=tk.CENTER, stretch=False)
        for key, text, chars in (
            ("filename", "Filename", 30),
            ("date", "Date", 14),
            ("size", "Size", 9),
            ("duration", "Duration", 8),
            ("link", "YouTube Link", 48),
        ):
            self.tree.heading(key, text=text, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=int(chars * 7 * self._dpi_scale), anchor=tk.W)

        scroll = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._build_checkbox_images()
        self._configure_tree_tags()
        self._build_context_menu()
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-Button-1>", self._on_row_double_click)
        theme.register(self._on_theme_changed)
```

`selectmode="none"` is deliberate: the checkbox is the selection model, and a competing highlight-selection would give the user two contradictory notions of "selected."

- [ ] **Step 3: Generate the checkbox images**

Follows `build_tray`'s runtime-PIL pattern (no asset file). Held on `self` so Tk's PhotoImage GC cannot collect them out from under a visible row.

```python
    def _build_checkbox_images(self) -> None:
        """Generate checked/unchecked box images at the current DPI scale
        and theme colours. Must be re-called on every theme switch — the
        colours are baked into the pixels, not read live like a ttk style.
        """
        from PIL import Image, ImageDraw, ImageTk

        size = max(16, int(16 * self._dpi_scale))
        border = theme.token("MUTED")
        check = theme.token("SUCCESS")
        inset = max(1, size // 8)

        def make(checked: bool) -> tk.PhotoImage:
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle(
                (inset, inset, size - inset, size - inset),
                radius=max(2, size // 8),
                outline=border,
                width=max(1, size // 10),
            )
            if checked:
                mid_x, mid_y = size * 0.4, size - inset - size * 0.15
                draw.line((inset + size * 0.15, size * 0.5, mid_x, mid_y),
                          fill=check, width=max(2, size // 8))
                draw.line((mid_x, mid_y, size - inset - size * 0.1, inset + size * 0.15),
                          fill=check, width=max(2, size // 8))
            return ImageTk.PhotoImage(img)

        # Held on self so the PhotoImage objects stay referenced; Tk drops
        # unreferenced PhotoImages even while still assigned to a widget.
        self._checkbox_images = {False: make(False), True: make(True)}

    def _checkbox_image(self, checked: bool) -> tk.PhotoImage:
        return self._checkbox_images[checked]
```

Note: this adds `PIL.ImageTk` at runtime. `packaging/uploader.spec` already lists `PIL._tkinter_finder` as a hidden import with a comment calling it "precautionary, not known-required" — it is now genuinely required. Update that comment when this task lands.

- [ ] **Step 4: Row tag configuration**

```python
    def _configure_tree_tags(self) -> None:
        self.tree.tag_configure("row_odd", background=theme.token("ROW_ODD"))
        self.tree.tag_configure("row_even", background=theme.token("ROW_EVEN"))
        self.tree.tag_configure("row_preselect", background=theme.token("ROW_PRESELECT"))
        self.tree.tag_configure("has_link", foreground=theme.token("LINK"))

    def _row_tags(self, path: Path, position: int) -> tuple[str, ...]:
        # ttk.Treeview gives priority to whichever conflicting tag is
        # listed FIRST, so preselect (a background) must precede the zebra
        # tag (also a background) to win.
        tags = []
        if path in self._preselected:
            tags.append("row_preselect")
        tags.append("row_odd" if position % 2 else "row_even")
        if self.links.get(path):
            tags.append("has_link")
        return tuple(tags)

    def _apply_zebra_tags(self) -> None:
        """Recompute tags for every displayed row, in current display order.

        Needed both after a sort (position changed) and after _set_link
        (has_link tag changed) — cheap enough to just redo all of them.
        """
        for position, iid in enumerate(self.tree.get_children("")):
            path = Path(iid)
            self.tree.item(iid, tags=self._row_tags(path, position))
```

- [ ] **Step 5: Click-to-sort headers**

```python
    def _sort_by(self, column: str) -> None:
        info_by_path = {i.path: i for i in self.infos}

        def key(path: Path):
            info = info_by_path[path]
            if column == "checked":
                return self.selected[path].get()
            if column == "filename":
                return info.path.name.lower()
            if column == "date":
                return info.mtime
            if column == "size":
                return info.size
            if column == "duration":
                return info.duration if info.duration is not None else -1.0
            if column == "link":
                return self.links.get(path, "")
            raise ValueError(f"unknown sort column: {column}")

        reverse = self._sort_reverse.get(column, False)
        ordered = sorted(info_by_path.keys(), key=key, reverse=reverse)
        for index, path in enumerate(ordered):
            self.tree.move(str(path), "", index)
        self._sort_reverse[column] = not reverse
        self._apply_zebra_tags()
```

- [ ] **Step 6: Checkbox click handling**

```python
    def _on_tree_click(self, event: tk.Event) -> None:
        if self.tree.identify_region(event.x, event.y) != "tree":
            return  # click landed in a data column, not the checkbox column
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        var = self.selected.get(Path(iid))
        if var is None:
            return
        var.set(not var.get())
        self.tree.item(iid, image=self._checkbox_image(var.get()))
```

- [ ] **Step 7: Right-click context menu + double-click open**

```python
    def _build_context_menu(self) -> None:
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy link", command=self._context_copy)
        self.context_menu.add_command(label="Open in browser", command=self._context_open)
        self._context_path: Path | None = None

    def _show_context_menu(self, event: tk.Event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        path = Path(iid)
        self._context_path = path
        state = tk.NORMAL if self.links.get(path) else tk.DISABLED
        self.context_menu.entryconfig("Copy link", state=state)
        self.context_menu.entryconfig("Open in browser", state=state)
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def _context_copy(self) -> None:
        if self._context_path is not None:
            self._copy(self._context_path)

    def _context_open(self) -> None:
        if self._context_path is not None:
            self._open(self._context_path)

    def _on_row_double_click(self, event: tk.Event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid:
            self._open(Path(iid))
```

- [ ] **Step 8: The theme-change consumer**

**This is `UploaderWindow`'s only theme consumer. Task 6 extends this method; it must not define a second one.**

```python
    def _on_theme_changed(self, mode: str) -> None:
        """Registered with theme.register in _build. Regenerates everything
        that bakes theme colours into pixels rather than reading a ttk
        style live: checkbox images and Treeview tag colours.

        Task 6 extends this method for the status line and ffmpeg warning.
        """
        self._build_checkbox_images()
        self._configure_tree_tags()
        for iid in self.tree.get_children(""):
            var = self.selected.get(Path(iid))
            if var is not None:
                self.tree.item(iid, image=self._checkbox_image(var.get()))
```

- [ ] **Step 9: Rewrite `refresh()` to populate the Treeview**

`self.links` is still cleared here, exactly as today — deliberate per spec §3, not an oversight.

```python
    def refresh(self, preselect: set | None = None) -> None:
        """Rebuild the list. Paths in *preselect* start checked.

        The watcher passes newly-ready recordings here so the common case —
        finish a fight, open the window, hit Upload — needs no clicking.
        """
        preselect = preselect or set()
        self._preselected = set(preselect)
        self.selected.clear()
        self.links.clear()
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        self.infos = [
            library.build_info(p, self.state.ffprobe_bin)
            for p in library.discover(self.state.recording_dir)
        ]
        first_preselected_iid = None
        for position, info in enumerate(self.infos):
            var = tk.BooleanVar(value=info.path in preselect)
            self.selected[info.path] = var
            iid = str(info.path)
            self.tree.insert(
                "", tk.END, iid=iid,
                image=self._checkbox_image(var.get()),
                values=(info.path.name, info.date_str, info.size_str, info.duration_str, ""),
                tags=self._row_tags(info.path, position),
            )
            if info.path in preselect and first_preselected_iid is None:
                first_preselected_iid = iid
        if first_preselected_iid is not None:
            self.tree.see(first_preselected_iid)
        self.status.config(text=f"Found {len(self.infos)} video(s)")
```

- [ ] **Step 10: Update `_copy`, `_open`, `_set_link` for the `Path -> str` links dict**

```python
    def _copy(self, path: Path) -> None:
        url = self.links.get(path)
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self._status_kind = "SUCCESS"
            self.status.config(text="Link copied to clipboard",
                               foreground=theme.token("SUCCESS"))

    def _open(self, path: Path) -> None:
        url = self.links.get(path)
        if url:
            webbrowser.open(url)

    def _set_link(self, path: Path, video_id: str) -> None:
        """Link rows by source path, never by list position.

        Position-based matching (as in b04c3a7) shifts every subsequent row
        when one upload returns no ID.

        The existence check below guards a `_ui`-queued update arriving for
        a path no longer in the rebuilt tree (e.g. the file was deleted, or
        refresh() ran mid-upload). It does NOT protect against refresh()
        clearing self.links on every rebuild — that clearing is preserved
        deliberately (see refresh()); this guard is a different case.
        """
        iid = str(path)
        if not self.tree.exists(iid):
            return
        url = f"https://www.youtube.com/watch?v={video_id}"
        self.links[path] = url
        self.tree.set(iid, "link", url)
        self._apply_zebra_tags()
```

`self._status_kind` is introduced here and consumed by Task 6 — add `self._status_kind: str | None = None` to `__init__` in Step 1 above.

- [ ] **Step 11: Run the logic test suite**

```bash
python -m pytest tests/
```

No pre-existing test may change status. None of them import `app`, so this proves only that the refactor did not leak into logic modules. **No automated coverage exists for the Treeview itself; Step 12 is the only real verification.**

- [ ] **Step 12: Manual verification (no automated UI coverage exists)**

1. Launch against a folder with several videos of differing sizes, durations, and dates.
2. Header reads exactly: checkbox, Filename, Date, Size, Duration, YouTube Link.
3. Click each header once, then again — rows reorder ascending then descending; a different header re-sorts from scratch.
4. Click a checkbox cell — image toggles; Upload Selected with only that row checked uploads only that file (proves `self.selected` still drives `_chosen` regardless of sort).
5. Sort by Filename descending, then stitch-upload two videos — the stitched clip order follows **timestamp**, not on-screen order. This is the sort-safety claim in practice.
6. Right-click a row with no link — both items greyed. Upload it, right-click again — both enabled; Copy link puts a working URL on the clipboard; Open in browser opens the YouTube page, not the local file.
7. Double-click an uploaded row — opens the YouTube link.
8. Trigger the deferred-refresh path: start an upload, drop a new file into the folder, let the upload finish. The just-finished upload's link column is empty after the deferred refresh — pre-existing behavior, unchanged.
9. With `notify_mode: popup`, drop a recording in while the window is closed — the window opens with the row checked, scrolled into view, and highlighted, even with enough rows that it would be below the fold.
10. Switch Windows light↔dark while open — checkbox images and striping repaint to the new theme's colours.

- [ ] **Step 13: Commit**

```bash
git add obs_youtube_uploader/app.py
git commit -m "refactor(ui): replace hand-built video list with ttk.Treeview"
```

---

### Task 6: Main window chrome

**Files:**
- Modify: `obs_youtube_uploader/app.py` — module-level spacing constants; the action bar and progress/status blocks in `_build`; the `foreground=` literals in `_upload_worker`, `_upload_one.on_retry`, `_retry_worker`; and an extension to `_on_theme_changed`.

**Interfaces:**
- Consumes: `theme.token`; `self.tree` from Task 5 (untouched here); `self._status_kind` from Task 5; `self.status`, `self.progress`, `self.stitch_var`, `self.stitch_chk`, `self.retry_btn` (same names as today, so `_upload_worker` / `_upload_one` / `_retry_worker` / `_manual_retry` need no signature changes).
- Produces: module-level `PAD_TIGHT`, `PAD_NORMAL`, `PAD_LOOSE`, `FRAME_PADDING` in `app.py`, imported by Task 7; `self.ffmpeg_warn_label`.

- [ ] **Step 1: Add the shared spacing scale**

```python
# module level, after imports, before AppState
PAD_TIGHT = 4    # between closely related controls (e.g. buttons in one row)
PAD_NORMAL = 8   # between distinct groups (e.g. a frame and the window edge)
PAD_LOOSE = 12   # around a whole section
FRAME_PADDING = 8  # internal padding for bordered frames
```

- [ ] **Step 2: Apply the scale to the sections `_build` already has**

```python
        meta = ttk.LabelFrame(self.root, text="Video details", padding=FRAME_PADDING)
        meta.pack(fill=tk.X, padx=PAD_NORMAL, pady=PAD_TIGHT)
```

```python
        self.list_frame = ttk.Frame(self.root)
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=PAD_NORMAL)
```

- [ ] **Step 3: Regroup the action bar**

Today's loop mixes `side=tk.LEFT` and `side=tk.RIGHT`, rendering the buttons right-aligned in *reverse* declaration order. The bar carries **six** controls, including **Upload combat logs** — which the replacement below must keep. Replace the whole `bot` block:

```python
        self.stitch_var = tk.BooleanVar(value=False)
        bot = ttk.Frame(self.root)
        bot.pack(fill=tk.X, padx=PAD_NORMAL, pady=PAD_NORMAL)

        ttk.Button(bot, text="Settings", command=self._open_settings).pack(
            side=tk.LEFT, padx=(0, PAD_LOOSE))
        ttk.Button(bot, text="Delete Selected", command=self._delete_selected).pack(
            side=tk.LEFT, padx=PAD_TIGHT)
        ttk.Button(bot, text="Select All", command=lambda: self._set_all(True)).pack(
            side=tk.LEFT, padx=PAD_TIGHT)
        ttk.Button(bot, text="Select None", command=lambda: self._set_all(False)).pack(
            side=tk.LEFT, padx=PAD_TIGHT)

        self.stitch_chk = ttk.Checkbutton(bot, text="Stitch selected videos",
                                          variable=self.stitch_var)
        self.stitch_chk.pack(side=tk.LEFT, padx=(PAD_LOOSE, PAD_TIGHT))
        self.ffmpeg_warn_label = None
        if not self.state.ffmpeg_bin:
            self.stitch_chk.state(["disabled"])
            self.ffmpeg_warn_label = ttk.Label(
                bot, text="(ffmpeg not found — stitching unavailable)",
                foreground=theme.token("WARNING"))
            self.ffmpeg_warn_label.pack(side=tk.LEFT, padx=PAD_TIGHT)

        # Right side, packed in visual order: Upload Selected is the accent
        # action, Retry sits beside it, and Upload combat logs — added by the
        # combat-log feature — is a peer upload action, NOT accented, so the
        # primary action stays unambiguous.
        ttk.Button(bot, text="Upload Selected", style="Accent.TButton",
                   command=self._start_upload).pack(side=tk.RIGHT, padx=PAD_TIGHT)
        self.retry_btn = ttk.Button(bot, text="Retry", command=self._manual_retry)
        self.retry_btn.pack(side=tk.RIGHT, padx=PAD_TIGHT)
        self.retry_btn.state(["disabled"])
        ttk.Button(bot, text="Upload combat logs",
                   command=self._start_combat_log_upload).pack(
            side=tk.RIGHT, padx=PAD_TIGHT)
```

**Do not drop `Upload combat logs`.** It is a working feature on this branch (`app.py:156-157`), and an earlier draft of this plan — written against `main` — omitted it.

- [ ] **Step 4: Merge progress bar and status label into one fixed-height bar**

Today they are separately packed; wrapping status text or the bar switching to `indeterminate` during stitching each change the row height and shift the window.

```python
        status_bar = ttk.Frame(self.root, height=48)
        status_bar.pack(fill=tk.X, padx=PAD_NORMAL, pady=(0, PAD_NORMAL))
        status_bar.pack_propagate(False)  # fixed height regardless of child content
        self.progress = ttk.Progressbar(status_bar, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(PAD_TIGHT, 0))
        self.status = ttk.Label(status_bar, text="")
        self.status.pack(fill=tk.X, anchor=tk.W, pady=(PAD_TIGHT, 0))
```

- [ ] **Step 5: Tokenise the status-line colours, tracking the transient kind**

The status line's colour reflects whichever transient state a worker last set, so a live theme switch must re-derive it rather than reset it. Every site sets `self._status_kind` (introduced in Task 5) alongside the colour:

```python
# _upload_worker success
            self.retry_state = None
            self._status_kind = "SUCCESS"
            self._ui(self.status.config,
                     {"text": "Upload complete!", "foreground": theme.token("SUCCESS")})
```

```python
# _upload_worker UploadFailed
            self._status_kind = "ERROR"
            self._ui(self.status.config, {"text": str(exc), "foreground": theme.token("ERROR")})
```

```python
# _upload_worker generic Exception
            self._status_kind = "ERROR"
            self._ui(self.status.config,
                     {"text": f"Error: {exc}", "foreground": theme.token("ERROR")})
```

```python
# _upload_one.on_retry
        def on_retry(attempt: int, delay: float) -> None:
            self._status_kind = "WARNING"
            self._ui(self.status.config,
                     {"text": f"Network problem — retrying in {delay:.0f}s "
                              f"(attempt {attempt})", "foreground": theme.token("WARNING")})
```

```python
# _retry_worker UploadFailed
            self._status_kind = "ERROR"
            self._ui(self.status.config, {"text": str(exc), "foreground": theme.token("ERROR")})
```

```python
# _retry_worker success
            self._status_kind = "SUCCESS"
            self._ui(self.status.config,
                     {"text": "Upload complete!", "foreground": theme.token("SUCCESS")})
```

Setting `self._status_kind` on the worker thread is safe: it is a plain attribute write, not a Tk call. Only the widget mutation goes through `self._ui`.

- [ ] **Step 5b: Tokenise `_combat_log_worker`'s status colours**

The combat-log worker is a **second** writer to the same status line, with its own colour literals — including one that is outright broken in dark mode.

**This method was reworked by the squash-merge of `origin/main` (commit `fd8c974`). The code below matches the CURRENT file — read `_combat_log_worker` before editing and do not trust any older description of it.** It now opens with `archive = None`, uses `combatlog.summarize_archive(...)`, builds a `status_text` with `combatlog.dropped_note(...)` on the success branch, and has a longer `except` that appends the archive path. Change **only** the colour arguments and add `self._status_kind` beside each; touch none of the combat-log logic.

```python
# First status line — currently foreground="black", which is INVISIBLE on a
# dark background. This is the FG token's reason to exist.
            self._status_kind = "FG"
            self._ui(self.status.config,
                     {"text": "Collecting combat logs…",
                      "foreground": theme.token("FG")})
```

Three status lines set text with **no** `foreground` at all, so they inherit whatever colour the previous message left behind — including a stale red from an earlier failure. Give each an explicit kind and colour:

```python
            self._status_kind = "FG"
            self._ui(self.status.config,
                     {"text": "No combat logs found.", "foreground": theme.token("FG")})
```

```python
            self._status_kind = "FG"
            self._ui(self.status.config,
                     {"text": "Building archive…", "foreground": theme.token("FG")})
```

```python
            self._status_kind = "FG"
            self._ui(self.status.config,
                     {"text": "Posting to Discord…", "foreground": theme.token("FG")})
```

The success branch now sends `status_text` (message plus any `dropped_note`), not `result.message` — keep that variable, change only the colour:

```python
                self._status_kind = "SUCCESS"
                self._ui(self.status.config,
                         {"text": status_text, "foreground": theme.token("SUCCESS")})
```

Both failure paths — the `not result.ok` branch and the trailing `except Exception` — become:

```python
                self._status_kind = "ERROR"
                self._ui(self.status.config,
                         {"text": result.message, "foreground": theme.token("ERROR")})
```

```python
            self._status_kind = "ERROR"
            self._ui(self.status.config,
                     {"text": f"Error: {exc}", "foreground": theme.token("ERROR")})
```

Leave `archive = None`, `summarize_archive`, `dropped_note`, the archive-retention comment, and the `detail`-building `except` body exactly as they are. They are combat-log behaviour, not presentation, and they were added by a reviewed PR.

- [ ] **Step 6: Extend `_on_theme_changed` — do not add a second consumer**

Add these lines to the **existing** method from Task 5:

```python
    def _on_theme_changed(self, mode: str) -> None:
        self._build_checkbox_images()
        self._configure_tree_tags()
        for iid in self.tree.get_children(""):
            var = self.selected.get(Path(iid))
            if var is not None:
                self.tree.item(iid, image=self._checkbox_image(var.get()))
        # Added in Task 6: widgets whose colour was set directly rather
        # than through a ttk style. _status_kind survives the switch so a
        # red error stays red rather than snapping back to default.
        if self.ffmpeg_warn_label is not None:
            self.ffmpeg_warn_label.config(foreground=theme.token("WARNING", mode))
        if self._status_kind is not None:
            self.status.config(foreground=theme.token(self._status_kind, mode))
```

- [ ] **Step 7: Run the logic test suite**

```bash
python -m pytest tests/
```

No pre-existing test changes status. This exercises none of the layout — Step 8 is the only check of the chrome.

- [ ] **Step 8: Manual verification (no automated UI coverage exists)**

1. Left-to-right: Settings, Delete Selected, Select All, Select None, stitch checkbox (+ optional warning); Upload Selected and Retry right-aligned, Upload visually accented.
2. Narrow the window until the status text would wrap — the bottom bar's height does not change and the progress bar does not shift.
3. Stitch-upload two videos: during "Stitching with FFmpeg…" the bar switches to the indeterminate animation with no window resize or label jump, then returns to determinate and reaches 100%.
4. Disconnect the network mid-upload: status turns red, Retry enables; click Retry and confirm state transitions are correct.
5. With ffmpeg absent, the warning renders in the warning colour and the stitch checkbox is disabled.
6. Flip the OS theme **while a red error status is showing** — it must re-colour to the other theme's red, not reset to default. Repeat mid-retry-backoff for the orange warning.

- [ ] **Step 9: Commit**

```bash
git add obs_youtube_uploader/app.py
git commit -m "refactor(ui): regroup main window chrome and merge progress/status bar"
```

---

### Task 7: Settings dialog

**Files:**
- Modify: `obs_youtube_uploader/settingsui.py`

**Interfaces:**
- Consumes: `theme.token`, `theme.register`, `theme.unregister`; `PAD_TIGHT`, `PAD_NORMAL`, `PAD_LOOSE`, `FRAME_PADDING` from Task 6; `app_mod.dpi_scale` from Task 4.
- Produces: Nothing — leaf UI, nothing imports from `settingsui.py`.

- [ ] **Step 1: Import the shared spacing scale and theme**

```python
from . import app as app_mod
from . import paths, settings as settings_mod, theme, uploader
```

Then replace `_build`'s local `pad = {"padx": 8, "pady": 6}` and every ad-hoc literal: `**pad` → `padx=PAD_NORMAL, pady=PAD_TIGHT`, `padding=10` → `padding=app_mod.FRAME_PADDING`, `pady=(6, 0)` → `pady=(app_mod.PAD_TIGHT, 0)`, `pady=(4, 0)` → `pady=(app_mod.PAD_TIGHT, 0)`. No visual change from this step alone — it removes the mixed literals the spec calls out.

- [ ] **Step 2: Add the status-dot auth row**

```python
        acct = ttk.LabelFrame(self.win, text="Google account",
                              padding=app_mod.FRAME_PADDING)
        acct.pack(fill=tk.X, padx=app_mod.PAD_NORMAL, pady=app_mod.PAD_TIGHT)

        auth_row = ttk.Frame(acct)
        auth_row.pack(anchor=tk.W, fill=tk.X)
        self.auth_dot = tk.Canvas(auth_row, width=10, height=10, highlightthickness=0)
        self.auth_dot.pack(side=tk.LEFT, padx=(0, app_mod.PAD_TIGHT))
        self._auth_dot_id = self.auth_dot.create_oval(1, 1, 9, 9, outline="")
        self.lbl_auth = ttk.Label(auth_row, text="Checking…")
        self.lbl_auth.pack(side=tk.LEFT)

        ttk.Button(acct, text="Connect Google Account",
                   command=self._connect).pack(anchor=tk.W, pady=(app_mod.PAD_TIGHT, 0))
        self.lbl_acct_hint = ttk.Label(
            acct,
            text=("If this is a pre-release build, only approved testers can "
                  "sign in."),
            foreground=theme.token("MUTED"), wraplength=460, justify=tk.LEFT,
        )
        self.lbl_acct_hint.pack(anchor=tk.W, pady=(app_mod.PAD_TIGHT, 0))
```

- [ ] **Step 3: One helper sets dot and text together, so they cannot disagree**

```python
    def _set_auth_status(self, text: str, token_name: str) -> None:
        """Update the status dot + text together. _auth_kind is retained so
        a live theme switch can re-derive the colour rather than reset it."""
        self._auth_kind = token_name
        color = theme.token(token_name)
        self.auth_dot.itemconfig(self._auth_dot_id, fill=color)
        self.lbl_auth.config(text=text, foreground=color)

    def _refresh_auth_label(self) -> None:
        creds = uploader.load_credentials(paths.token_file())
        if creds is not None and not uploader.needs_reauth(creds):
            self._set_auth_status("Connected", "SUCCESS")
        else:
            self._set_auth_status("Not connected", "ERROR")

    def _connect(self) -> None:
        """Run OAuth off the main thread; it blocks on a browser round-trip.

        This worker thread must never touch a Tk widget directly (Tk is not
        thread-safe) -- all UI updates are marshaled back via
        ``self.win.after(0, ...)``.
        """
        self._set_auth_status("Waiting for browser…", "WARNING")

        def worker() -> None:
            try:
                creds = uploader.run_oauth_flow()
                uploader.save_credentials(creds, paths.token_file())
                self.win.after(0, self._refresh_auth_label)
            except Exception as exc:
                self.win.after(0, lambda: messagebox.showerror(
                    "Connection failed", str(exc)))
                self.win.after(0, self._refresh_auth_label)

        threading.Thread(target=worker, daemon=True).start()
```

Add `self._auth_kind: str | None = None` in `__init__` before `_build()` runs.

- [ ] **Step 4: Align the "Upload defaults" label column**

```python
        up = ttk.LabelFrame(self.win, text="Upload defaults",
                            padding=app_mod.FRAME_PADDING)
        up.pack(fill=tk.X, padx=app_mod.PAD_NORMAL, pady=app_mod.PAD_TIGHT)
        up.columnconfigure(0, minsize=int(90 * app_mod.dpi_scale(self.win)))
        ttk.Label(up, text="Privacy:", anchor=tk.E).grid(row=0, column=0, sticky=tk.E)
        ttk.Combobox(up, textvariable=self.privacy, values=PRIVACY_CHOICES,
                     state="readonly", width=12).grid(
            row=0, column=1, sticky=tk.W, padx=app_mod.PAD_TIGHT)
        ttk.Label(up, text="Category ID:", anchor=tk.E).grid(
            row=1, column=0, sticky=tk.E, pady=(app_mod.PAD_TIGHT, 0))
        ttk.Entry(up, textvariable=self.category, width=8).grid(
            row=1, column=1, sticky=tk.W, padx=app_mod.PAD_TIGHT,
            pady=(app_mod.PAD_TIGHT, 0))
        self.lbl_category_hint = ttk.Label(up, text="(20 = Gaming)",
                                           foreground=theme.token("MUTED"))
        self.lbl_category_hint.grid(row=1, column=2, sticky=tk.W)
```

`minsize` is scaled — a fixed 90px column would be too narrow at 150%, which is the same class of bug Task 4 exists to prevent.

- [ ] **Step 5: Accent Save button**

```python
        row = ttk.Frame(self.win)
        row.pack(fill=tk.X, padx=app_mod.PAD_NORMAL, pady=app_mod.PAD_TIGHT)
        ttk.Button(row, text="Save", command=self._save,
                   style="Accent.TButton").pack(side=tk.RIGHT)
        ttk.Button(row, text="Cancel", command=self.win.destroy).pack(
            side=tk.RIGHT, padx=app_mod.PAD_TIGHT)
```

`Accent.TButton` is registered by sv-ttk, which Task 3 applies before any `SettingsWindow` is constructed.

- [ ] **Step 5b: Apply the spacing scale and MUTED token to the Discord frame**

The dialog has **six** `LabelFrame`s on this branch, not five. The Discord frame is the newest and the one an out-of-date plan would silently drop — it must keep its webhook entry, its `lbl_webhook` status line, the Gamelogs entry, and both **Browse…** and **Detect** buttons:

```python
        disc = ttk.LabelFrame(self.win, text="Discord (combat logs)",
                              padding=app_mod.FRAME_PADDING)
        disc.pack(fill=tk.X, padx=app_mod.PAD_NORMAL, pady=app_mod.PAD_TIGHT)
        disc.columnconfigure(0, minsize=int(90 * app_mod.dpi_scale(self.win)))
        ttk.Label(disc, text="Webhook URL:", anchor=tk.E).grid(
            row=0, column=0, sticky=tk.E)
        ttk.Entry(disc, textvariable=self.webhook, width=44).grid(
            row=0, column=1, sticky=tk.EW, padx=app_mod.PAD_TIGHT)
        self.lbl_webhook = ttk.Label(disc, text="", foreground=theme.token("MUTED"))
        self.lbl_webhook.grid(row=1, column=1, sticky=tk.W, padx=app_mod.PAD_TIGHT)
        ttk.Label(disc, text="Gamelogs:", anchor=tk.E).grid(
            row=2, column=0, sticky=tk.E, pady=(app_mod.PAD_TIGHT, 0))
        ttk.Entry(disc, textvariable=self.gamelogs).grid(
            row=2, column=1, sticky=tk.EW, padx=app_mod.PAD_TIGHT,
            pady=(app_mod.PAD_TIGHT, 0))
        btns = ttk.Frame(disc)
        btns.grid(row=2, column=2, sticky=tk.W, pady=(app_mod.PAD_TIGHT, 0))
        ttk.Button(btns, text="Browse…", command=self._browse_gamelogs).pack(side=tk.LEFT)
        ttk.Button(btns, text="Detect", command=self._detect_gamelogs).pack(
            side=tk.LEFT, padx=(app_mod.PAD_TIGHT, 0))
        disc.columnconfigure(1, weight=1)
```

The label column uses the same scaled `minsize` as "Upload defaults", so `Webhook URL:` and `Gamelogs:` align to the same edge as `Privacy:` and `Category ID:` — the point of a shared scale.

The Recording folder frame also gained a **Detect** button on this branch; give its three buttons the same `padx=app_mod.PAD_TIGHT` treatment, leaving `_browse`, `_detect`, `_browse_gamelogs`, and `_detect_gamelogs` themselves untouched — they are behaviour.

`lbl_webhook` is set by `_refresh_webhook_label`, which sets **text only**, so its `MUTED` colour survives. Add it to the theme consumer in Step 6.

- [ ] **Step 6: Register the theme consumer AND unregister on destroy**

This dialog is rebuilt on every `_open_settings()`, so a consumer that is never removed leaks — see "Theming ownership" above.

**The `__init__` region you are editing was changed by the merge of `origin/main` (commit `fd8c974`).** It now ends with a `webhook.trace_add(...)` call and its explanatory comment, added by a reviewed PR:

```python
        self._build()
        self._refresh_auth_label()
        self._refresh_webhook_label()
        # Keep the label in step with the field. Without this it describes
        # whatever was configured when the dialog opened, so a user who
        # pastes a new webhook sees the OLD one summarised underneath it --
        # misleading in the one place they look to confirm they pasted the
        # right thing. parse_webhook is a regex and a urlparse, so running
        # it per keystroke costs nothing worth caching.
        self.webhook.trace_add("write", lambda *_: self._refresh_webhook_label())
```

**Preserve that call and its comment verbatim.** Add the theme registration and window protocol after it:

```python
        theme.register(self._on_theme_changed)
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        self.win.bind("<Destroy>", self._on_destroy)
```

```python
    def _on_theme_changed(self, mode: str) -> None:
        """Re-apply colours set directly rather than through a ttk style:
        the Canvas dot, the auth label, and the three hint labels.

        Deferred via after_idle for the same reason UploaderWindow defers:
        sv_ttk.set_theme() fires ttk's <<ThemeChanged>>, which Tk QUEUES, and
        on the next tick tk_setPalette resets any directly-configured widget
        foreground to the new theme's default. Setting them inline here would
        be silently undone one tick later — verified on a real window during
        Task 6. Treeview tags and images are NOT affected; a directly-set
        ttk::Label/Canvas colour is.
        """
        self.win.after_idle(lambda: self._repaint_tokens(mode))

    def _repaint_tokens(self, mode: str) -> None:
        if not self.win.winfo_exists():
            return  # dialog closed between the switch and the idle callback
        self.lbl_acct_hint.config(foreground=theme.token("MUTED", mode))
        self.lbl_category_hint.config(foreground=theme.token("MUTED", mode))
        self.lbl_webhook.config(foreground=theme.token("MUTED", mode))
        if self._auth_kind is not None:
            color = theme.token(self._auth_kind, mode)
            self.auth_dot.itemconfig(self._auth_dot_id, fill=color)
            self.lbl_auth.config(foreground=color)

    def _on_destroy(self, event) -> None:
        # <Destroy> fires for every child widget too, so ignore all but the
        # toplevel's own event, or the consumer is removed while the dialog
        # is still alive.
        if event.widget is self.win:
            theme.unregister(self._on_theme_changed)

    def _close(self) -> None:
        self.win.destroy()
```

The `winfo_exists()` guard matters here in a way it does not for `UploaderWindow`: this dialog can be destroyed between a theme switch and the deferred callback, and an `after_idle` closure holding a destroyed widget would raise `TclError`. `UploaderWindow` is withdrawn, never destroyed, so it has no equivalent window.

`self._save` and the Cancel button both call `self.win.destroy()`, so `<Destroy>` covers every exit path without touching either.

- [ ] **Step 7: Run the logic test suite**

```bash
python -m pytest tests/
```

No pre-existing test changes status.

- [ ] **Step 8: Manual verification (no automated UI coverage exists)**

1. Open Settings: `Privacy:` and `Category ID:` right-align to the same edge; Save renders accented, Cancel neutral.
2. At 125% and 150% scaling, no LabelFrame and no part of the Save/Cancel row is clipped — the b23f9cc regression check again.
3. Click Connect Google Account: the row shows dot + "Waiting for browser…" in the warning colour, then dot + "Connected" in success (or "Not connected" in error if cancelled).
4. Flip the OS theme while Settings is open — dot, auth text, and both hint labels re-colour; nothing is left in the old theme.
5. **Leak check:** open and close Settings five times, then flip the OS theme. Confirm `%LOCALAPPDATA%\OBSYouTubeUploader\logs\uploader_debug.log` contains no `TclError` warnings from stale consumers. This verifies Step 6's unregister.

- [ ] **Step 9: Commit**

```bash
git add obs_youtube_uploader/settingsui.py
git commit -m "refactor(settingsui): unify spacing, add status-dot auth row, accent Save"
```

---

### Task 8: Application icon

**Files:**
- Create: `obs_youtube_uploader/assets/app.ico`
- Modify: `obs_youtube_uploader/paths.py` (additive helper only)
- Modify: `obs_youtube_uploader/app.py` (`root.iconbitmap` in `UploaderWindow.__init__`)
- Modify: `obs_youtube_uploader/settingsui.py` (`self.win.iconbitmap`)
- Modify: `obs_youtube_uploader/__main__.py` (`build_tray`)
- Modify: `packaging/uploader.spec` (`datas` entry + `icon=` on `EXE`)

**Interfaces:**
- Consumes: Nothing from `theme.py` — independent of theming.
- Produces: `paths.icon_file() -> Path | None`.

- [ ] **Step 1: Create the icon asset**

The repo has no `assets/` directory. Create one and place a real multi-resolution `.ico`:

```bash
mkdir -p obs_youtube_uploader/assets
```

Include at minimum 16×16, 32×32, 48×48, and 256×256 — Windows picks the closest for title bar, taskbar, Start Menu, and Add/Remove Programs respectively, and a single low-res frame looks soft in the larger contexts. From a PNG source, using Pillow (already a dependency):

```python
from PIL import Image
img = Image.open("source.png")
img.save("obs_youtube_uploader/assets/app.ico",
         sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
```

- [ ] **Step 2: Add a source/frozen-aware resolution helper in `paths.py`**

`bundle_dir()` returns `sys._MEIPASS` when frozen and the **repository root** in a source checkout. `resolve_binary()` in `app.py` documents this exact hazard for ffmpeg. The icon needs the equivalent: frozen builds collect it at the bundle root via `datas` (Step 4), but in a source checkout it lives under the package, and `bundle_dir() / "assets" / "app.ico"` would wrongly resolve to `<repo>/assets/app.ico`.

```python
def icon_file() -> Path | None:
    """Locate the bundled app icon, or None if it isn't present.

    Mirrors app.resolve_binary()'s two-case handling of bundle_dir():
    frozen builds collect the icon at the bundle root via uploader.spec's
    `datas` entry, so `bundle_dir() / "app.ico"` is correct there. A source
    checkout has no such collection step, so bundle_dir() (the repo root)
    is wrong; the real file lives under the package's own assets/ folder.
    Returning None rather than raising lets callers treat a missing icon as
    optional, the same policy resolve_binary() and configure_logging() use.
    """
    frozen_candidate = bundle_dir() / "app.ico"
    if frozen_candidate.exists():
        return frozen_candidate
    source_candidate = Path(__file__).resolve().parent / "assets" / "app.ico"
    if source_candidate.exists():
        return source_candidate
    return None
```

This is additive: no existing function in `paths.py` changes, and `tests/test_paths.py` must still pass untouched.

- [ ] **Step 3: Wire `iconbitmap` into both windows without risking startup**

In `app.py`, after `root.title(...)`:

```python
        icon_path = paths.icon_file()
        if icon_path is not None:
            try:
                root.iconbitmap(str(icon_path))
            except tk.TclError:
                pass  # Cosmetic only; a bad/missing .ico must not block startup.
```

In `settingsui.py`, after `self.win.title("Settings")`:

```python
        icon_path = paths.icon_file()
        if icon_path is not None:
            try:
                self.win.iconbitmap(str(icon_path))
            except tk.TclError:
                pass  # Same optional-cosmetic policy as the main window.
```

`iconbitmap()` raises `tk.TclError` (not `OSError`) on a malformed `.ico`, which is why the guard names that type specifically.

- [ ] **Step 4: Bundle the icon and set it on `EXE`**

```python
ICON = ROOT / "obs_youtube_uploader" / "assets" / "app.ico"
```

```python
    datas=collect_data_files("sv_ttk") + [
        # Collected at the bundle root so paths.icon_file()'s frozen-case
        # lookup (bundle_dir() / "app.ico") finds it directly.
        (str(ICON), "."),
    ],
```

Note this **extends** Task 1's `datas=collect_data_files("sv_ttk")` rather than replacing it — dropping the sv-ttk collection here would undo Task 1 and the build.yml assertion would catch it, loudly.

```python
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
```

Free win: `installer.iss` already sets `UninstallDisplayIcon={app}\{#AppExe}`, which reads the icon embedded in the exe — so the Start Menu shortcut and Add/Remove Programs entry are fixed with **no `installer.iss` change**.

- [ ] **Step 5: Replace the PIL-drawn tray placeholder**

```python
def build_tray(on_open, on_quit):
    """Tray icon backed by the bundled .ico, generated art as a fallback."""
    import pystray
    from PIL import Image, ImageDraw

    icon_path = paths.icon_file()
    image = None
    if icon_path is not None:
        try:
            image = Image.open(icon_path)
        except OSError:
            image = None

    if image is None:
        # Fallback only: keeps the tray icon present per the codebase's
        # degrade-don't-block policy for optional presentation capabilities.
        image = Image.new("RGB", (64, 64), "#1f1f1f")
        draw = ImageDraw.Draw(image)
        draw.ellipse((10, 10, 54, 54), fill="#ff0000")
        draw.polygon([(27, 22), (27, 42), (45, 32)], fill="#ffffff")

    menu = pystray.Menu(
        pystray.MenuItem("Open uploader", lambda *_: on_open(), default=True),
        pystray.MenuItem("Quit", lambda *_: on_quit()),
    )
    return pystray.Icon("obs_youtube_uploader", image, "OBS → YouTube Uploader", menu)
```

- [ ] **Step 6: Run the logic test suite**

```bash
python -m pytest tests/
```

`tests/test_paths.py` in particular must pass untouched — `icon_file()` is purely additive.

- [ ] **Step 7: Manual verification (no automated UI coverage exists)**

1. Run from source: the real icon (not the Tk feather) appears in the main window title bar, the Settings title bar, the taskbar, and the tray.
2. Temporarily rename `app.ico` and relaunch: the app still starts, windows fall back to the default icon, and the tray falls back to the drawn placeholder — proving the missing-asset path is non-fatal.
3. Restore it, build the installer, and run it: the icon appears on the Start Menu shortcut and in `Settings > Apps > Installed apps`. These two can only be checked against a real installed build.

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/assets/app.ico obs_youtube_uploader/paths.py \
        obs_youtube_uploader/app.py obs_youtube_uploader/settingsui.py \
        obs_youtube_uploader/__main__.py packaging/uploader.spec
git commit -m "feat: replace Tk feather with a real app icon everywhere"
```

---

### Task 9: Update the smoke checklist

**Files:**
- Modify: `docs/smoke-checklist.md`

**Interfaces:**
- Consumes: Nothing programmatically.
- Produces: Nothing. This is the project's only real verification surface for UI work.

- [ ] **Step 1: Update the preamble**

`docs/smoke-checklist.md` on this branch already has a **Combat logs** section added by the combat-log feature — this task **adds to** the file, it does not rewrite it. Read the current file before editing.

Append to the existing opening paragraph:

```markdown
The UI refresh (theming, the Treeview list, DPI awareness, the real app
icon) is likewise untested by `pytest` — no file under `tests/` imports
`app` or `settingsui` — so this checklist is the only real verification
those changes get.
```

- [ ] **Step 1b: Fold the combat-log UI into the new checks**

The Combat logs section already contains a **"Settings dialog at 100% and 150% Windows display scaling"** item that names "all five sections". Update it to six, naming Discord (combat logs) explicitly, and cross-reference the new Look-and-feel scaling items rather than duplicating them.

Also add to the Combat logs section:

```markdown
- [ ] **Combat-log status messages are legible in dark mode.** With Windows
      set to Dark, run a combat-log upload and watch the status line through
      "Collecting combat logs…", "Building archive…", and "Posting to
      Discord…". All three must be readable. Before this refresh the first
      of them was hardcoded to black, which was invisible on a dark
      background — this item exists to catch that regressing.
- [ ] **The Upload combat logs button survived the chrome rework.** Confirm
      it is present in the action bar, sits beside Retry on the right, and
      is NOT styled as the accent button — Upload Selected is the primary
      action.
```

- [ ] **Step 2: Add a new "Look and feel" section after "First run"**

**This section is the single most important artifact this plan produces.** Everything below was found by reading code or by driving Tk under WSLg's X11 translation — none of it has ever run on native Windows Tk. Where a behaviour is marked LOAD-BEARING, correct code depends on Windows behaving the way X11 did, and if it does not, the feature is broken in a way nothing in CI or this repo can detect.

```markdown
## Look and feel

### Theming
- [ ] **Launches in light mode when Windows is set to Light.**
      `Settings > Personalization > Colors > Choose your mode > Light`, then
      launch. Both windows render with sv-ttk's light theme — no dark chrome,
      and no illegible text in status messages, hint labels, or the ffmpeg
      warning.
- [ ] **Launches in dark mode when Windows is set to Dark.** Same with `Dark`.
      Also check Treeview row striping and the description `tk.Text` box — a
      classic Tk widget sv-ttk does not theme, so confirm it is at least
      legible (a known accepted limitation).
- [ ] **LOAD-BEARING: switching the OS theme live, with both windows open.**
      Open the main window and Settings together, then flip
      `Choose your mode`. Within a few seconds both must re-theme fully:
      status line, ffmpeg warning, auth status dot and text, hint labels,
      Treeview striping, the preselect highlight, and the checkbox images.
      No half-themed widget anywhere.
      *Why this is load-bearing:* the app sets these colours from a deferred
      `after_idle` callback because `sv_ttk.set_theme()` fires a QUEUED
      `<<ThemeChanged>>` event that runs `tk_setPalette` on the next tick and
      resets any directly-set widget foreground. That ordering was observed
      under WSLg. If native Windows Tk dispatches differently, colours may
      revert one tick after the switch — watch for a correct flash followed
      by a reset.
- [ ] **A red error status survives a live theme switch.** Force an upload
      failure so the status line is red, then flip the OS theme. It must
      re-colour to the other theme's red — not reset to the default
      foreground, and not stay in the old theme's red.
- [ ] **A rapid double-flip settles correctly.** Flip light→dark→light
      quickly. Intermediate flicker is acceptable; a stuck or wrong final
      colour is not.
- [ ] **Opening Settings repeatedly does not leak theme consumers.** Open and
      close Settings five times, then flip the OS theme. Confirm
      `%LOCALAPPDATA%\OBSYouTubeUploader\logs\uploader_debug.log` contains no
      `TclError` warnings from stale consumers holding destroyed windows.
- [ ] **A failed theme read does not trigger the watcher's failure
      notification.** Run several minutes with the theme untouched and
      confirm zero "watcher is having trouble" notifications. The theme check
      has its own try/except inside `poll()`, separate from the watcher's
      consecutive-failure counter; that notification must stay reserved for
      real recording-folder faults.

### Display scaling
- [ ] **100% scaling.** Both windows render at native size, text sharp, no
      clipping.
- [ ] **125% scaling.** Settings dialog not clipped — Recording folder frame
      and the Save/Cancel row fully visible AND above the taskbar.
- [ ] **150% scaling.** Neither window opens larger than the screen.
- [ ] **LOAD-BEARING: on a NARROW window and a SHORT screen, not just
      1080p.** The minsize clamping fixes only bite in those configurations —
      a default 1080p pass exercises neither. On a short screen, confirm the
      Settings dialog can still be resized smaller and moved, i.e. Save and
      Cancel are always reachable.
- [ ] **LOAD-BEARING: the list checkbox is not clipped at 125%, 150%, and
      200%.** sv-ttk sets Treeview row height from a font that does not
      follow `tk scaling`, so the app raises the row height itself to fit the
      scaled checkbox image. This was measured under WSLg only. Also confirm
      a light↔dark switch does not re-clip it — sv-ttk re-asserts its own row
      height on every `set_theme`.
- [ ] **Text is sharp, not bitmap-stretched, at 150%.** The process declares
      DPI awareness but the HRESULT is discarded, so blurriness is the only
      observable sign the call silently failed.

### The list
- [ ] **LOAD-BEARING: clicking a checkbox toggles it.** The click handler
      relies on `identify_region()` returning `"tree"` for the checkbox
      column and something else elsewhere. That was confirmed on X11 only.
      Also confirm clicking a data column does NOT toggle.
- [ ] **LOAD-BEARING: the context menu releases its grab.** Right-click a
      row, then dismiss it by clicking elsewhere; repeat and dismiss with
      Escape. After each, confirm the window still responds to clicks. This
      path has NO automated coverage of any kind — a retained pointer grab
      presents as "the app is frozen".
- [ ] **Copy link and Open in browser** from the context menu work on a row
      with a link, and are greyed out on a row without one.
- [ ] **Double-click opens the YouTube link** — and does NOT open a browser
      when double-clicking the checkbox column.
- [ ] **Keyboard: Space toggles the focused row.** Tab to the list, use the
      arrow keys to move, press Space. Confirm it toggles exactly one row and
      that Upload Selected agrees with what is checked. Then trigger a list
      rebuild (delete a file, or save Settings) and confirm the keyboard
      still works afterwards without touching the mouse.
- [ ] **Treeview tag colours actually render** — zebra striping, the
      preselect highlight, and the blue link foreground, in both light and
      dark. Tag backgrounds under a themed Treeview style are historically
      theme- and version-dependent.
- [ ] **Sorting does not affect upload order or stitch order.** Sort by each
      column, then select rows out of their displayed order and upload —
      first with Stitch off, then on. The `(1/n)` numbering and stitched clip
      order must follow the underlying data, not the display.
- [ ] **Newly announced recordings are pre-checked, scrolled into view, and
      visibly highlighted** — even when they would otherwise be below the
      fold.

### Icon
- [ ] **The icon appears in all five locations:** main window title bar,
      Settings title bar, taskbar, system tray, and — after running the built
      installer — the Start Menu shortcut and Add/Remove Programs entry.
      Note the icon can only ever be verified on Windows: on Linux,
      `iconbitmap` always fails because X11 Tk has no `.ico` support, so
      development runs show no icon by design.
- [ ] **A missing icon does not break startup.** Rename `app.ico` inside the
      install directory and relaunch: the app still starts, and the tray
      falls back to its drawn placeholder.

### Frozen build
- [ ] **LOAD-BEARING: the installed build renders themed, not plain ttk.**
      This is the only proof sv-ttk's `.tcl` files were both bundled AND are
      loadable. CI asserts the files exist; only launching proves they load.
- [ ] **Checkboxes appear in the list in the frozen build.** They are
      generated through `PIL.ImageTk`, which depends on the
      `PIL._tkinter_finder` hidden import. If that is wrong the list renders
      with no checkboxes at all, and no source-checkout test can see it.
- [ ] **`Accent.TButton` renders visually distinct** on Upload Selected and
      on Settings' Save.
```

- [ ] **Step 3: Reword the invalidated Watcher and Upload items**

Replace the existing "Newly announced recordings are already checked…" line with:

```markdown
- [ ] **Newly announced recordings are already checked when the window
      opens, scrolled into view, and visibly highlighted.** With the window
      closed, create a new recording so the watcher detects it, then open
      the window from the tray. Its row is pre-checked, the list is scrolled
      so the row is visible without manual scrolling (even if it would
      otherwise be below the fold), and it carries a distinct highlight
      (`ROW_PRESELECT`) visually different from the ordinary row stripes.
```

Replace the two "Copy button" / "Open button" lines with:

```markdown
- [ ] **Copy link via the row's right-click context menu puts a working URL
      on the clipboard.** Right-click a row with a completed upload, choose
      "Copy link", paste elsewhere to confirm. Confirm "Copy link" is greyed
      out on a row with no link yet.
- [ ] **Open in browser via the context menu opens the video's YouTube
      page** — not the local video file. Confirm it is greyed out on a row
      with no link yet.
- [ ] **Double-clicking a row with a completed upload opens its YouTube
      link**, same destination as the context menu. Double-clicking a row
      with no link does nothing.
```

- [ ] **Step 4: Add the icon item to the Release section**

```markdown
- [ ] **The app icon appears on the Start Menu shortcut and in Add/Remove
      Programs.** Run the built installer, then check the Start Menu entry's
      icon and `Settings > Apps > Installed apps`. Both should show the real
      icon rather than a generic exe icon, since `installer.iss`'s
      `UninstallDisplayIcon` reads the icon embedded by `uploader.spec`.
```

- [ ] **Step 5: Commit**

```bash
git add docs/smoke-checklist.md
git commit -m "docs: update smoke checklist for theming, Treeview, DPI, and icon"
```

---

