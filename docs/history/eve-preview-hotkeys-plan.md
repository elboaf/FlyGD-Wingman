# Preview hotkeys implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Global keyboard chords that focus a named EVE client or cycle through the running ones, configured from the Previews tab and persisted across restarts.

**Architecture:** Two new pure modules (`gestures.py` parses chords to `(mods, vk)`; `cycle.py` resolves next/previous) plus a roster module, all Linux-testable. `preview/host.py` registers the chords with `RegisterHotKey` against its existing message-only window, so `WM_HOTKEY` arrives in the pump it already runs. Registration outcomes are held as readable state rather than announced once, because previews start before the webview exists.

**Tech Stack:** Python 3.11+, ctypes/Win32, pywebview bridge, vanilla JS page, pytest.

**Spec:** `eve-preview-hotkeys-design.md` (parent: `eve-preview-design.md`)

## Global Constraints

- **Every new module must import cleanly on Linux.** CI is `ubuntu-latest` only. `ctypes.wintypes` and `Structure` are fine off-Windows; `ctypes.WinDLL`, `ctypes.windll` and `ctypes.WINFUNCTYPE` are not — build those lazily inside functions (`preview/win32.py:1-16`).
- **Every ctypes function gets `argtypes` and `restype`.** Undeclared, ctypes truncates pointer-sized values to 32 bits and the symptom appears nowhere near the cause (`preview/win32.py:10-16`).
- **Every HWND touch happens on the preview thread.** Marshal with `PostMessageW`, never call across threads.
- **`MOD_NOREPEAT` is set on every registered chord**, without exception.
- **A chord with no modifier is rejected**, at parse time, on every entry path.
- **Only real character names are persisted.** Anything starting with `hwnd:` is a client at character-select and must never reach settings.
- **No new dependencies.**
- Run the full suite with `python -m pytest -q` from the worktree root.

---

## File structure

| File | Responsibility | Platform |
|---|---|---|
| `obs_youtube_uploader/preview/gestures.py` | **Create.** Chord ⇄ `(mods, vk)`, capture mapping | Pure |
| `obs_youtube_uploader/preview/cycle.py` | **Create.** Ordering and wrap-around | Pure |
| `obs_youtube_uploader/preview/roster.py` | **Create.** Most-recent-first list, eviction | Pure |
| `obs_youtube_uploader/settings.py` | **Modify.** `update()` primitive; hotkey + roster schema | Pure |
| `obs_youtube_uploader/preview/store.py` | **Modify.** Roster recording; atomic writes | Pure |
| `obs_youtube_uploader/preview/win32.py` | **Modify.** `WM_APP_REBIND` | Windows types |
| `obs_youtube_uploader/preview/host.py` | **Modify.** Client registry, registration, dispatch, teardown | Windows |
| `obs_youtube_uploader/ui/api.py` | **Modify.** Four bridge methods, status push, atomic writes | Any |
| `obs_youtube_uploader/__main__.py` | **Modify.** Wire callbacks | Any |
| `obs_youtube_uploader/web/previews.js` | **Create.** Bind list UI | Page |
| `obs_youtube_uploader/web/index.html` | **Modify.** Hotkeys section markup | Page |
| `docs/smoke-checklist.md` | **Modify.** Windows-only checks | Docs |

Tasks 1-2 are the prerequisite the spec names. Tasks 3-5 are pure logic and can be
built in any order. Tasks 6-13 depend on what precedes them.

---

### Task 1: A settings primitive that spans read-modify-write

The spec's prerequisite. `_SAVE_LOCK` (`settings.py:180-189`) serializes the
*write* but not the read-modify-write around it, and `ui/api.py:1055` builds
`cfg = dict(self._state.settings)` before saving — a snapshot, which the parent
design explicitly forbids. This task adds the primitive; Task 2 converts the
callers.

**Files:**
- Modify: `obs_youtube_uploader/settings.py:178-190`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `settings.update(data: dict, path: Path | None = None)` — a context
  manager yielding `data`, holding `_SAVE_LOCK` for the whole block, saving on
  clean exit and restoring `data` to its prior contents on any exception.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_settings.py`:

```python
def test_update_saves_on_clean_exit(tmp_path):
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    with settings.update(data, path) as doc:
        doc["privacy"] = "public"
    assert json.loads(path.read_text())["privacy"] == "public"


def test_update_rolls_back_and_does_not_write_on_failure(tmp_path):
    """A failed block must leave neither the file nor the live dict changed.

    ui/api.py bails before touching in-memory state precisely so state and
    disk cannot diverge; the primitive has to preserve that property or
    converting that caller would regress it.
    """
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    settings.save(data, path)
    with pytest.raises(RuntimeError):
        with settings.update(data, path) as doc:
            doc["privacy"] = "public"
            raise RuntimeError("boom")
    assert data["privacy"] == settings.DEFAULTS["privacy"]
    assert json.loads(path.read_text())["privacy"] == settings.DEFAULTS["privacy"]


def test_update_rollback_restores_nested_sections(tmp_path):
    """Shallow restore would leave a mutated nested dict in place, which is
    exactly where preview state lives."""
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    with pytest.raises(RuntimeError):
        with settings.update(data, path) as doc:
            doc["preview"]["seen"] = ["Scout Alt"]
            raise RuntimeError("boom")
    assert data["preview"]["seen"] == []


def test_concurrent_updates_do_not_lose_each_other(tmp_path):
    """The race this whole task exists for: one writer's read-modify-write
    interleaving with another's and reverting it."""
    import threading

    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    settings.save(data, path)
    barrier = threading.Barrier(2)

    def writer(key, value):
        barrier.wait()
        for _ in range(50):
            with settings.update(data, path) as doc:
                doc[key] = value

    threads = [threading.Thread(target=writer, args=("privacy", "public")),
               threading.Thread(target=writer, args=("category", "22"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    written = json.loads(path.read_text())
    assert written["privacy"] == "public"
    assert written["category"] == "22"
```

Add `import json`, `import pytest` and `import threading` at the top of the
file if they are not already there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_settings.py -k update -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.settings' has no attribute 'update'`

- [ ] **Step 3: Implement the primitive**

Add `import contextlib` and `import copy` to the imports at the top of
`obs_youtube_uploader/settings.py`, then insert after `save()`:

```python
@contextlib.contextmanager
def update(data: dict, path: Path | None = None):
    """Serialise a whole read-modify-write, not just the write.

    _SAVE_LOCK alone is not enough. save() projects the COMPLETE document
    from DEFAULTS, so a writer that reads, mutates and saves can be
    interleaved by another doing the same and have its keys reverted --
    silently, with no error and nothing in the log. Holding the lock across
    the caller's mutation closes that window.

    On any exception the live dict is restored to its prior contents and
    nothing is written, so a failed save cannot leave in-memory state and
    disk disagreeing. ui/api.py's save path depends on that property.

    Deep, not shallow: preview state lives in a nested section, and a
    shallow snapshot would leave a half-applied mutation behind.

    DO NOT call save() or update() from inside an update() block. The lock
    is not reentrant and the process will deadlock.
    """
    with _SAVE_LOCK:
        before = copy.deepcopy(data)
        try:
            yield data
            _save_locked(data, path)
        except BaseException:
            data.clear()
            data.update(before)
            raise
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_settings.py -k update -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: 987 passed, 4 skipped (plus the 4 new)

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/settings.py tests/test_settings.py
git commit -m "settings: add update(), an atomic read-modify-write"
```

---

### Task 2: Convert every settings writer to the primitive

Four writers exist. Until all of them hold the same lock across their whole
sequence, the roster in Task 10 would add a fifth participant to a race.

**Files:**
- Modify: `obs_youtube_uploader/ui/api.py:1055-1076` (`save_settings`)
- Modify: `obs_youtube_uploader/ui/api.py:718-742` (`_remember_channel`)
- Modify: `obs_youtube_uploader/ui/api.py:1236-1256` (`set_preview_enabled`)
- Modify: `obs_youtube_uploader/preview/store.py:24-30,61-73`
- Modify: `obs_youtube_uploader/__main__.py:298-300`
- Test: `tests/test_api_settings.py`, `tests/test_preview_store.py`

**Interfaces:**
- Consumes: `settings.update()` from Task 1.
- Produces: `LayoutStore(update_settings, debounce_s=..., timer=...)` — the
  `save_settings`/`read_settings` pair is replaced by one context-manager
  factory taking no arguments and yielding the live settings dict.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_preview_store.py`:

```python
def test_write_goes_through_one_atomic_transaction():
    """The store must not read settings, mutate, and save as three steps:
    another writer can land between the read and the save and lose one
    side's keys entirely."""
    import contextlib

    live = {"preview": {"layouts": {}}}
    opened = []

    @contextlib.contextmanager
    def fake_update():
        opened.append("enter")
        yield live
        opened.append("exit")

    store = LayoutStore(update_settings=fake_update, timer=_ImmediateTimer)
    store.record("Scout Alt", layout.Entry(Rect(1, 2, 3, 4), False))
    store.flush()

    assert opened == ["enter", "exit"]
    assert live["preview"]["layouts"]["Scout Alt"] == {
        "x": 1, "y": 2, "w": 3, "h": 4, "locked": False}
```

`_ImmediateTimer` already exists in that file if the current tests use one; if
they do not, add it above the test:

```python
class _ImmediateTimer:
    """Fires on start() instead of after a delay, so debounce does not make
    the test sleep."""

    def __init__(self, delay, fn):
        self._fn = fn

    def start(self):
        self._fn()

    def cancel(self):
        pass
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_preview_store.py -k atomic -v`
Expected: FAIL with `TypeError: LayoutStore.__init__() got an unexpected keyword argument 'update_settings'`

- [ ] **Step 3: Convert the store**

In `obs_youtube_uploader/preview/store.py`, replace the constructor and
`_write`:

```python
class LayoutStore:
    def __init__(self, update_settings, debounce_s=DEBOUNCE_S,
                 timer=threading.Timer):
        # One context manager, not a read/save pair. The pair could not be
        # made atomic by the caller: another writer lands between them and
        # reverts whatever this one did not re-read.
        self._update_settings = update_settings
        self._debounce_s = debounce_s
        self._timer_factory = timer
        self._pending = {}
        self._timer = None
        self._lock = threading.Lock()
```

```python
    def _write(self) -> None:
        with self._lock:
            pending, self._pending = dict(self._pending), {}
            self._timer = None
        if not pending:
            return
        try:
            with self._update_settings() as live:
                section = live.setdefault("preview", {})
                layouts = dict(section.setdefault("layouts", {}))
                layouts.update(layout.serialize(pending))   # per-key merge
                section["layouts"] = layouts
        except OSError:
            # A settings file that cannot be written must not take the
            # preview thread down -- same posture as ui/api.py's channel
            # persist, which swallows OSError for the same reason.
            logger.exception("Could not persist preview layouts")
```

Update the module docstring's second rule to name the primitive:

```python
  * Write inside settings.update(), never as a read-then-save pair. The
    document is projected complete from DEFAULTS, so a writer interleaving
    between another writer's read and its save reverts keys it never
    touched.
```

- [ ] **Step 4: Update the store's existing tests**

Every existing `LayoutStore(save_settings=..., read_settings=...)` construction
in `tests/test_preview_store.py` becomes a single `update_settings=` factory.
Where a test asserted a save happened, assert on the yielded dict instead. Where
a test asserted the settings document was re-read at write time rather than
snapshotted, keep it — the guarantee is unchanged, only its mechanism moved.

- [ ] **Step 5: Convert `build_preview_host`**

In `obs_youtube_uploader/__main__.py`, replace the store construction:

```python
        store = LayoutStore(
            update_settings=lambda: settings_mod.update(state.settings))
```

- [ ] **Step 6: Convert the three api.py writers**

`save_settings` (around `:1055`) — the snapshot goes away:

```python
        gamelogs = str(values.get("gamelogs_dir") or "").strip()
        try:
            with settings_mod.update(self._state.settings) as cfg:
                cfg.update({
                    "privacy": values.get("privacy"),
                    "category": category,
                    "notify_mode": values.get("notify_mode"),
                    "recording_dir": str(rec_dir),
                    "discord_webhook": webhook_raw,
                    "gamelogs_dir": gamelogs or None,
                })
        except OSError as exc:
            # update() restored the live dict before re-raising, so state
            # and disk still agree -- the property the old snapshot-then-
            # save order was written to protect.
            self._alert("error", "Could not save settings",
                        f"Settings were not saved: {exc}")
            return False
```

Leave the `self._state.settings = settings_mod.load()` line that follows
untouched: it re-applies validation, and it runs outside the lock.

`_remember_channel` (around `:740`):

```python
        try:
            with settings_mod.update(self._state.settings) as cfg:
                cfg["channel_id"] = channel_id
                cfg["channel_title"] = channel_title
        except OSError:
            logger.exception("Could not persist the channel")
```

Delete the two bare assignments above the old `try:` — the block now performs
them.

`set_preview_enabled` (around `:1250`):

```python
        try:
            with settings_mod.update(self._state.settings) as cfg:
                cfg.setdefault("preview", {})["enabled"] = enabled
        except OSError:
            logger.exception("Could not persist the preview setting")
```

Delete the `section = self._state.settings.setdefault(...)` /
`section["enabled"] = enabled` lines above it, but keep the early-return no-op
guard that precedes them — it reads state, it does not write.

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. Fix any test that constructed a `LayoutStore` the old way.

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/settings.py obs_youtube_uploader/preview/store.py \
        obs_youtube_uploader/ui/api.py obs_youtube_uploader/__main__.py \
        tests/test_preview_store.py tests/test_api_settings.py
git commit -m "settings: route every writer through update()"
```

---

### Task 3: `gestures.py` — chords to (mods, vk)

**Files:**
- Create: `obs_youtube_uploader/preview/gestures.py`
- Test: `tests/test_preview_gestures.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Gesture(mods: int, vk: int)` — a `NamedTuple`.
  - `parse(text: str) -> Gesture | None` — `None` when unparseable or
    modifier-less.
  - `display(g: Gesture) -> str` — canonical `"Ctrl+Alt+F1"`.
  - `from_capture(parts: dict) -> dict` — `{"gesture": str, "error": str | None}`.
  - `MOD_ALT`, `MOD_CONTROL`, `MOD_SHIFT`, `MOD_WIN`, `MOD_NOREPEAT`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preview_gestures.py`:

```python
"""Gesture parsing. Pure, so this is where the real coverage lives -- the
Win32 half cannot be exercised in CI at all."""
import pytest

from obs_youtube_uploader.preview import gestures


def test_parses_a_modified_function_key():
    g = gestures.parse("Ctrl+Alt+F1")
    assert g.vk == 0x70
    assert g.mods & gestures.MOD_CONTROL
    assert g.mods & gestures.MOD_ALT
    assert not g.mods & gestures.MOD_SHIFT


def test_every_parsed_gesture_carries_no_repeat():
    """Without MOD_NOREPEAT a held chord posts WM_HOTKEY at the keyboard
    repeat rate, and each one runs a full foreground-switch sequence."""
    for text in ("Ctrl+F1", "Alt+Shift+A", "Win+Ctrl+Numpad5"):
        assert gestures.parse(text).mods & gestures.MOD_NOREPEAT


def test_a_chord_with_no_modifier_is_rejected():
    """RegisterHotKey would happily claim a bare F1 desktop-wide, in every
    application, until the process exits."""
    assert gestures.parse("F1") is None
    assert gestures.parse("A") is None


def test_unknown_key_is_rejected():
    assert gestures.parse("Ctrl+Nonsense") is None
    assert gestures.parse("") is None
    assert gestures.parse("Ctrl+") is None


def test_round_trips_through_display():
    for text in ("Ctrl+F1", "Ctrl+Alt+Shift+A", "Win+Delete", "Ctrl+Numpad0",
                 "Ctrl+,", "Alt+["):
        assert gestures.display(gestures.parse(text)) == text


def test_display_orders_modifiers_canonically():
    """Two spellings of one chord must not read as two different bindings
    in the clash check."""
    assert gestures.display(gestures.parse("Alt+Ctrl+F2")) == "Ctrl+Alt+F2"


def test_accepts_explicit_virtual_key_forms():
    assert gestures.parse("Ctrl+VK_F1") == gestures.parse("Ctrl+F1")
    assert gestures.parse("Ctrl+0x70") == gestures.parse("Ctrl+F1")


def test_capture_maps_a_dom_event():
    result = gestures.from_capture({"ctrl": True, "alt": True, "shift": False,
                                    "meta": False, "code": "F1"})
    assert result == {"gesture": "Ctrl+Alt+F1", "error": None}


def test_capture_letters_and_digits():
    assert gestures.from_capture(
        {"ctrl": True, "code": "KeyA"})["gesture"] == "Ctrl+A"
    assert gestures.from_capture(
        {"ctrl": True, "code": "Digit4"})["gesture"] == "Ctrl+4"


def test_capture_reports_a_modifier_only_press_distinctly():
    """The user is still reaching for the combination -- not an error worth
    telling them about, but not a binding either."""
    result = gestures.from_capture({"ctrl": True, "code": "ControlLeft"})
    assert result["error"] == "modifier-only"
    assert result["gesture"] == ""


def test_capture_rejects_an_unmodified_key():
    result = gestures.from_capture({"code": "F1"})
    assert result["error"] == "no-modifier"


def test_capture_rejects_an_unmappable_code():
    result = gestures.from_capture({"ctrl": True, "code": "MediaPlayPause"})
    assert result["error"] == "unmappable"


def test_imports_without_windows():
    """settings.py imports this for validation, and CI is ubuntu-latest."""
    assert gestures.parse("Ctrl+F1") is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_preview_gestures.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.preview.gestures'`

- [ ] **Step 3: Implement the module**

Create `obs_youtube_uploader/preview/gestures.py`:

```python
"""Hotkey gestures for previews: text and DOM events in, (mods, vk) out.

Pure by construction -- no ctypes, no Windows -- because settings.py imports
it for validation and CI runs on ubuntu-latest.

Deliberately NOT bookmarks.py's AHK notation. That format exists because an
AutoHotkey engine consumes it literally, and it carries constraints from
that engine's storage: bookmarks reject "=" purely because their INI cannot
hold it (see preview/discovery.py's note on the same leak). These gestures
go to RegisterHotKey, which wants modifier flags and a virtual-key code, and
the translation between the two notations is lossy in both directions.
"""
from typing import NamedTuple

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
# Set on EVERY gesture. Without it a held chord posts WM_HOTKEY at the
# keyboard repeat rate and each message runs a foreground-switch sequence:
# invisible when testing with a tap, and awful in a fight.
MOD_NOREPEAT = 0x4000

# Order is display order, so two spellings of one chord produce one string
# and the clash check cannot be fooled by "Alt+Ctrl+F2" vs "Ctrl+Alt+F2".
_MODIFIERS = (("ctrl", MOD_CONTROL, "Ctrl"),
              ("alt", MOD_ALT, "Alt"),
              ("shift", MOD_SHIFT, "Shift"),
              ("meta", MOD_WIN, "Win"))

_MODIFIER_CODES = {"ControlLeft", "ControlRight", "AltLeft", "AltRight",
                   "ShiftLeft", "ShiftRight", "MetaLeft", "MetaRight"}

# name -> virtual-key. The name is what the user sees and types.
_KEYS = {
    "Space": 0x20, "Enter": 0x0D, "Tab": 0x09, "Esc": 0x1B,
    "Backspace": 0x08, "Delete": 0x2E, "Insert": 0x2D,
    "Home": 0x24, "End": 0x23, "PgUp": 0x21, "PgDn": 0x22,
    "Up": 0x26, "Down": 0x28, "Left": 0x25, "Right": 0x27,
    ",": 0xBC, ".": 0xBE, "/": 0xBF, ";": 0xBA, "'": 0xDE, "`": 0xC0,
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    "NumpadAdd": 0x6B, "NumpadSub": 0x6D, "NumpadMult": 0x6A,
    "NumpadDiv": 0x6F, "NumpadDot": 0x6E,
}
for _i in range(10):
    _KEYS[str(_i)] = 0x30 + _i
    _KEYS[f"Numpad{_i}"] = 0x60 + _i
for _i in range(26):
    _KEYS[chr(ord("A") + _i)] = 0x41 + _i
for _i in range(1, 25):
    _KEYS[f"F{_i}"] = 0x70 + _i - 1

_NAMES = {vk: name for name, vk in _KEYS.items()}

# DOM event.code -> our key name. Same US-layout assumption bookmarks.py
# documents, and mitigated the same way: a Type... escape hatch in the UI.
_CODES = {
    "Space": "Space", "Enter": "Enter", "Tab": "Tab", "Escape": "Esc",
    "Backspace": "Backspace", "Delete": "Delete", "Insert": "Insert",
    "Home": "Home", "End": "End", "PageUp": "PgUp", "PageDown": "PgDn",
    "ArrowUp": "Up", "ArrowDown": "Down", "ArrowLeft": "Left",
    "ArrowRight": "Right",
    "Comma": ",", "Period": ".", "Slash": "/", "Semicolon": ";",
    "Quote": "'", "Backquote": "`", "Minus": "-", "Equal": "=",
    "BracketLeft": "[", "BracketRight": "]", "Backslash": "\\",
    "NumpadAdd": "NumpadAdd", "NumpadSubtract": "NumpadSub",
    "NumpadMultiply": "NumpadMult", "NumpadDivide": "NumpadDiv",
    "NumpadDecimal": "NumpadDot",
}


class Gesture(NamedTuple):
    mods: int
    vk: int


def _code_to_name(code: str):
    if code in _CODES:
        return _CODES[code]
    if len(code) == 4 and code.startswith("Key"):
        return code[3].upper()
    if len(code) == 6 and code.startswith("Digit"):
        return code[5]
    if code.startswith("Numpad") and len(code) == 7 and code[6:].isdigit():
        return code
    if code.startswith("F") and code[1:].isdigit() and 1 <= int(code[1:]) <= 24:
        return code
    return None


def _vk(token: str):
    """Resolve a key token: a name, a VK_ name, or a hex literal."""
    if token in _KEYS:
        return _KEYS[token]
    upper = token.upper()
    if upper in _KEYS:
        return _KEYS[upper]
    if upper.startswith("VK_"):
        return _KEYS.get(upper[3:])
    if upper.startswith("0X"):
        try:
            value = int(upper, 16)
        except ValueError:
            return None
        return value if 0 < value <= 0xFF else None
    return None


def parse(text):
    """A gesture, or None if the text is not one.

    None rather than an exception: every caller -- typed entry, settings
    validation, the bridge -- treats an unparseable chord as "drop this one
    binding", never as a failure worth propagating.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    tokens = [t.strip() for t in text.split("+")]
    # A trailing "+" means the key token is empty, which is not the "+" key:
    # that arrives as "=" with Shift, or as NumpadAdd.
    if any(not t for t in tokens):
        return None

    mods, key = 0, tokens[-1]
    by_label = {label.lower(): flag for _, flag, label in _MODIFIERS}
    for token in tokens[:-1]:
        flag = by_label.get(token.lower())
        if flag is None:
            return None
        mods |= flag
    if not mods:
        return None      # a bare chord would be claimed desktop-wide
    vk = _vk(key)
    if vk is None:
        return None
    return Gesture(mods | MOD_NOREPEAT, vk)


def display(g) -> str:
    if g is None:
        return ""
    parts = [label for _, flag, label in _MODIFIERS if g.mods & flag]
    parts.append(_NAMES.get(g.vk, f"0x{g.vk:02X}"))
    return "+".join(parts)


def from_capture(parts) -> dict:
    """Translate a captured DOM key event.

    Returns the canonical gesture string rather than a structure, so the
    page holds no mapping table of its own and cannot drift from this one --
    the same contract bookmarks.to_ahk keeps.
    """
    if not isinstance(parts, dict):
        return {"gesture": "", "error": "unmappable"}
    code = parts.get("code") or ""
    if code in _MODIFIER_CODES:
        # Not an error the user needs told about: they are still reaching
        # for the combination.
        return {"gesture": "", "error": "modifier-only"}
    name = _code_to_name(code)
    if name is None:
        return {"gesture": "", "error": "unmappable"}
    labels = [label for key, _, label in _MODIFIERS if parts.get(key)]
    if not labels:
        return {"gesture": "", "error": "no-modifier"}
    return {"gesture": "+".join(labels + [name]), "error": None}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_preview_gestures.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/gestures.py tests/test_preview_gestures.py
git commit -m "preview: parse hotkey gestures to (mods, vk)"
```

---

### Task 4: `cycle.py` — ordering and wrap-around

**Files:**
- Create: `obs_youtube_uploader/preview/cycle.py`
- Test: `tests/test_preview_cycle.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ordered(keys) -> list[str]`
  - `step(keys, anchor, delta: int) -> str | None`
  - `next_key(keys, anchor) -> str | None`
  - `prev_key(keys, anchor) -> str | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preview_cycle.py`:

```python
"""Cycle resolution. The client set changes every 700ms, so everything here
is about behaving sanely when it does."""
from obs_youtube_uploader.preview import cycle


def test_next_advances_in_name_order():
    keys = {"Charlie", "Alice", "Bravo"}
    assert cycle.next_key(keys, "Alice") == "Bravo"
    assert cycle.next_key(keys, "Bravo") == "Charlie"


def test_next_wraps_at_the_end():
    assert cycle.next_key({"Alice", "Bravo"}, "Bravo") == "Alice"


def test_prev_wraps_at_the_start():
    assert cycle.prev_key({"Alice", "Bravo"}, "Alice") == "Bravo"


def test_order_is_by_name_not_insertion():
    """Discovery order reshuffles as clients come and go, which would make
    'next' mean something different between two presses."""
    assert cycle.ordered(["Zulu", "Alice"]) == ["Alice", "Zulu"]
    assert cycle.ordered(["Alice", "Zulu"]) == ["Alice", "Zulu"]


def test_a_missing_anchor_starts_at_the_beginning():
    """The anchor is the foreground client. It is legitimately absent when
    focus is on a browser, or when the last-cycled character logged off."""
    assert cycle.next_key({"Alice", "Bravo"}, None) == "Alice"
    assert cycle.next_key({"Alice", "Bravo"}, "Ghost") == "Alice"


def test_an_empty_set_resolves_to_nothing():
    assert cycle.next_key(set(), None) is None
    assert cycle.next_key(set(), "Alice") is None


def test_a_single_client_cycles_to_itself():
    assert cycle.next_key({"Alice"}, "Alice") == "Alice"
    assert cycle.prev_key({"Alice"}, "Alice") == "Alice"


def test_a_client_joining_does_not_skip_the_anchor():
    """The bug a stored index would have: the set grows and the cursor
    silently points at a different character."""
    assert cycle.next_key({"Alice", "Charlie"}, "Alice") == "Charlie"
    assert cycle.next_key({"Alice", "Bravo", "Charlie"}, "Alice") == "Bravo"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_preview_cycle.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the module**

Create `obs_youtube_uploader/preview/cycle.py`:

```python
"""Cycle resolution across the running clients. Pure integer/string work.

No cursor is stored as an INDEX anywhere, and that is the whole design. The
client set is rebuilt every 700ms sweep, so an index survives the set it was
taken from and silently addresses a different character the moment anyone
logs in or out. The anchor is an identity instead, and an identity that has
gone simply falls back to the start.
"""


def ordered(keys) -> list:
    """Deterministic order: by name.

    Not discovery order -- that reshuffles as clients appear and disappear,
    which would make "next" mean something different between two presses.
    """
    return sorted(keys)


def step(keys, anchor, delta: int):
    order = ordered(keys)
    if not order:
        return None
    if anchor not in order:
        # Legitimate and common: focus is on a browser, or the character
        # cycled to last has since logged off.
        return order[0]
    return order[(order.index(anchor) + delta) % len(order)]


def next_key(keys, anchor):
    return step(keys, anchor, 1)


def prev_key(keys, anchor):
    return step(keys, anchor, -1)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_preview_cycle.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/cycle.py tests/test_preview_cycle.py
git commit -m "preview: resolve cycle targets by identity, never by index"
```

---

### Task 5: `roster.py` — the list of characters seen

**Files:**
- Create: `obs_youtube_uploader/preview/roster.py`
- Test: `tests/test_preview_roster.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CAP = 64`
  - `touch(seen, name, *, cap=CAP, protected=()) -> list[str]`
  - `deserialize(raw, *, cap=CAP) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preview_roster.py`:

```python
"""The roster of characters seen. Exists so a binding can be made for an
alt that is not logged in right now."""
from obs_youtube_uploader.preview import roster


def test_a_new_name_goes_to_the_front():
    assert roster.touch(["Bravo"], "Alice") == ["Alice", "Bravo"]


def test_a_seen_name_moves_to_the_front_rather_than_duplicating():
    assert roster.touch(["Alice", "Bravo"], "Bravo") == ["Bravo", "Alice"]


def test_hwnd_keys_never_enter():
    """A client at character-select has no stable identity, and the parent
    design forbids persisting state against one. A roster of dead HWND keys
    would also fill the bind list with rows naming nothing."""
    assert roster.touch(["Alice"], "hwnd:0x1234") == ["Alice"]


def test_empty_and_non_string_names_are_ignored():
    assert roster.touch(["Alice"], "") == ["Alice"]
    assert roster.touch(["Alice"], None) == ["Alice"]


def test_eviction_takes_from_the_stale_end():
    seen = [f"Char{i}" for i in range(64)]
    result = roster.touch(seen, "New", cap=64)
    assert result[0] == "New"
    assert len(result) == 64
    assert "Char63" not in result       # the least recently seen
    assert "Char0" in result


def test_a_bound_character_is_never_evicted():
    """Evicting a character that still holds a chord would leave a binding
    the UI cannot show a row for."""
    seen = [f"Char{i}" for i in range(64)]
    result = roster.touch(seen, "New", cap=64, protected={"Char63"})
    assert "Char63" in result
    assert "Char62" not in result
    assert len(result) == 64


def test_an_all_protected_roster_grows_rather_than_dropping_a_binding():
    seen = [f"Char{i}" for i in range(4)]
    result = roster.touch(seen, "New", cap=4, protected=set(seen))
    assert len(result) == 5


def test_deserialize_drops_malformed_entries():
    """Same posture as preview/layout.py: a hand-edited file costs one
    entry, not the launch."""
    assert roster.deserialize(["Alice", 5, "", None, "hwnd:0x1",
                               "Bravo"]) == ["Alice", "Bravo"]
    assert roster.deserialize("nonsense") == []
    assert roster.deserialize(None) == []


def test_deserialize_dedupes_preserving_order():
    assert roster.deserialize(["Alice", "Bravo", "Alice"]) == ["Alice", "Bravo"]


def test_deserialize_applies_the_cap():
    assert len(roster.deserialize([f"C{i}" for i in range(200)])) == roster.CAP
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_preview_roster.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the module**

Create `obs_youtube_uploader/preview/roster.py`:

```python
"""Characters seen, most recently first.

A character can only be NAMED while it is running, so without this a user
could not bind an alt that flies on weekends without logging it in first.
preview.layouts is keyed by character but is written only on a rect change,
so a preview that was never dragged has no key -- it is not a roster.

Pure: list in, list out. The caller owns the file.
"""

CAP = 64


def _usable(name) -> bool:
    # "hwnd:" keys belong to clients at character-select, which have no
    # stable identity. discovery.py falls back to them precisely because
    # there is no name yet.
    return isinstance(name, str) and bool(name) and not name.startswith("hwnd:")


def touch(seen, name, *, cap: int = CAP, protected=()) -> list:
    """Record *name* as most recently seen.

    Move-to-front rather than append: the list is ordered by recency, and
    an append would leave a re-seen character at the stale end where
    eviction finds it first.
    """
    out = [n for n in seen if _usable(n) and n != name]
    if not _usable(name):
        return out
    out.insert(0, name)

    while len(out) > cap:
        for i in range(len(out) - 1, -1, -1):
            if out[i] not in protected:
                del out[i]
                break
        else:
            # Every remaining entry holds a binding. Overshooting the cap
            # is the lesser evil: dropping one would leave a chord the bind
            # list has no row for, which is worse than a slightly long file.
            break
    return out


def deserialize(raw, *, cap: int = CAP) -> list:
    """Rebuild the roster, dropping anything malformed.

    Deliberately forgiving, matching preview/layout.py and settings.py: a
    hand-edited file should cost one entry, not the launch.
    """
    if not isinstance(raw, list):
        return []
    out = []
    for name in raw:
        if _usable(name) and name not in out:
            out.append(name)
    return out[:cap]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_preview_roster.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/roster.py tests/test_preview_roster.py
git commit -m "preview: track characters seen, most recent first"
```

---

### Task 6: Settings schema for hotkeys and the roster

**Files:**
- Modify: `obs_youtube_uploader/settings.py:14-22` (`_preview_defaults`)
- Modify: `obs_youtube_uploader/settings.py:81-102` (`validated_preview`)
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `gestures.parse`, `roster.deserialize`.
- Produces: `settings["preview"]["hotkeys"]` with keys `characters` (dict),
  `cycle_next` (str), `cycle_prev` (str); and `settings["preview"]["seen"]`
  (list).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_settings.py`:

```python
def test_preview_defaults_carry_an_empty_hotkey_table():
    section = settings._preview_defaults()
    assert section["hotkeys"] == {"characters": {}, "cycle_next": "",
                                  "cycle_prev": ""}
    assert section["seen"] == []


def test_preview_defaults_are_not_shared_between_calls():
    """The nested-dict trap the existing defaults were written to avoid."""
    a, b = settings._preview_defaults(), settings._preview_defaults()
    a["hotkeys"]["characters"]["Alice"] = "Ctrl+F1"
    assert b["hotkeys"]["characters"] == {}


def test_validated_preview_keeps_parseable_gestures():
    section = settings.validated_preview(
        {"hotkeys": {"characters": {"Alice": "Ctrl+F1"},
                     "cycle_next": "Ctrl+Alt+Right", "cycle_prev": ""}})
    assert section["hotkeys"]["characters"] == {"Alice": "Ctrl+F1"}
    assert section["hotkeys"]["cycle_next"] == "Ctrl+Alt+Right"


def test_validated_preview_drops_one_bad_gesture_not_the_section():
    """Same posture as the layout entries: a hand-edited file costs one
    binding, not the launch."""
    section = settings.validated_preview(
        {"enabled": True,
         "hotkeys": {"characters": {"Alice": "Ctrl+F1", "Bravo": "nonsense",
                                    "Carol": "F1"}}})
    assert section["enabled"] is True
    assert section["hotkeys"]["characters"] == {"Alice": "Ctrl+F1"}


def test_validated_preview_canonicalises_gestures():
    """Stored in display form so the clash check compares strings."""
    section = settings.validated_preview(
        {"hotkeys": {"characters": {"Alice": "alt+ctrl+f2"}}})
    assert section["hotkeys"]["characters"]["Alice"] == "Ctrl+Alt+F2"


def test_validated_preview_falls_back_on_a_malformed_hotkey_section():
    section = settings.validated_preview({"hotkeys": "nonsense"})
    assert section["hotkeys"] == {"characters": {}, "cycle_next": "",
                                  "cycle_prev": ""}


def test_validated_preview_cleans_the_roster():
    section = settings.validated_preview({"seen": ["Alice", "hwnd:0x1", 7]})
    assert section["seen"] == ["Alice"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_settings.py -k preview -v`
Expected: FAIL with `KeyError: 'hotkeys'`

- [ ] **Step 3: Extend the defaults**

In `obs_youtube_uploader/settings.py`, replace the return in
`_preview_defaults()`:

```python
    return {"enabled": False, "width": 320, "height": 210,
            "opacity": 235, "layouts": {},
            # Flat cycle chords, not a group table. When named cycle groups
            # land these become the default group's, so the schema grows
            # without migrating anyone -- the same shape the parent design
            # used to defer profiles.
            "hotkeys": {"characters": {}, "cycle_next": "", "cycle_prev": ""},
            "seen": []}
```

- [ ] **Step 4: Extend the validator**

Add to the imports at the top of `settings.py`:

```python
from .preview import gestures as preview_gestures
from .preview import roster as preview_roster
```

Insert into `validated_preview()`, just before its `return section`:

```python
    raw_hotkeys = raw.get("hotkeys")
    if isinstance(raw_hotkeys, dict):
        characters = raw_hotkeys.get("characters")
        if isinstance(characters, dict):
            for name, text in characters.items():
                if not isinstance(name, str) or name.startswith("hwnd:"):
                    continue
                parsed = preview_gestures.parse(text)
                if parsed is not None:
                    # Canonical form, so "Alt+Ctrl+F2" and "Ctrl+Alt+F2"
                    # cannot read as two different bindings to the clash
                    # check.
                    section["hotkeys"]["characters"][name] = \
                        preview_gestures.display(parsed)
        for key in ("cycle_next", "cycle_prev"):
            parsed = preview_gestures.parse(raw_hotkeys.get(key))
            if parsed is not None:
                section["hotkeys"][key] = preview_gestures.display(parsed)

    section["seen"] = preview_roster.deserialize(raw.get("seen"))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_settings.py -v`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add obs_youtube_uploader/settings.py tests/test_settings.py
git commit -m "settings: validate preview hotkeys and the character roster"
```

---

### Task 7: `WM_APP_REBIND`

**Files:**
- Modify: `obs_youtube_uploader/preview/win32.py:50-53`
- Test: `tests/test_preview_win32.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `win32.WM_APP_REBIND`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_preview_win32.py`:

```python
def test_host_command_messages_are_distinct():
    """Two commands sharing a value would silently run the wrong handler."""
    commands = {win32.WM_APP_SHUTDOWN, win32.WM_APP_SWEEP_NOW,
                win32.WM_APP_REBIND}
    assert len(commands) == 3
    assert all(c >= win32.WM_APP for c in commands)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_preview_win32.py -k host_command -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'WM_APP_REBIND'`

- [ ] **Step 3: Add the constant**

In `obs_youtube_uploader/preview/win32.py`, after `WM_APP_SWEEP_NOW`:

```python
WM_APP_REBIND = WM_APP + 3
```

`RegisterHotKey` and `UnregisterHotKey` are already declared at `:235-236`,
and `GetForegroundWindow` at `:226`. Nothing else is needed here.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_preview_win32.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/win32.py tests/test_preview_win32.py
git commit -m "preview: add the rebind host command"
```

---

### Task 8: A retained client registry on the host

`_sweep` builds its `clients` map and throws it away, keeping only
`_windows` — which holds *only* clients whose window creation succeeded
(`host.py:195-221`, the `if win is not None` guard). Resolving a hotkey against
`_windows` would silently fail for a running, discovered client whose preview
could not be created, which is exactly when a keyboard shortcut is most useful.

**Files:**
- Modify: `obs_youtube_uploader/preview/host.py:41-56` (`__init__`), `:195-225` (`_sweep`)
- Test: `tests/test_preview_host.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `PreviewHost.characters() -> list[str]` — named characters currently
    discovered, sorted.
  - `PreviewHost._clients: dict[str, discovery.Client]` — refreshed wholesale
    each sweep.
  - `PreviewHost(..., on_clients_changed=None)` — called with the sorted
    character list when the discovered set changes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_preview_host.py`:

```python
class _FakeClient:
    def __init__(self, key, hwnd=0x1000, character=None):
        self.stable_key = key
        self.hwnd = hwnd
        self.character = character if character is not None else key
        self.title = f"EVE - {key}"
        self.pid = 4242


def test_the_client_registry_keeps_clients_with_no_window(monkeypatch):
    """A client whose preview could not be created is still running, and a
    chord aimed at it must still work."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "list_clients",
                        lambda: [_FakeClient("Alice"), _FakeClient("Bravo")])
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically",
                        lambda: None)
    monkeypatch.setattr(host.PreviewWindow, "create",
                        classmethod(lambda cls, *a, **k: None))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))

    h._sweep(libs=None)

    assert h._windows == {}
    assert sorted(h._clients) == ["Alice", "Bravo"]
    assert h.characters() == ["Alice", "Bravo"]


def test_the_registry_refreshes_hwnds_for_a_kept_key(monkeypatch):
    """reconcile() compares stable keys only, so a character that reappears
    on a NEW hwnd counts as 'kept' -- a retained record would point at a
    dead window."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically",
                        lambda: None)
    monkeypatch.setattr(host.PreviewWindow, "create",
                        classmethod(lambda cls, *a, **k: None))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))

    monkeypatch.setattr(host.discovery, "list_clients",
                        lambda: [_FakeClient("Alice", hwnd=0x1111)])
    h._sweep(libs=None)
    monkeypatch.setattr(host.discovery, "list_clients",
                        lambda: [_FakeClient("Alice", hwnd=0x2222)])
    h._sweep(libs=None)

    assert h._clients["Alice"].hwnd == 0x2222


def test_characters_excludes_clients_at_character_select(monkeypatch):
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically",
                        lambda: None)
    monkeypatch.setattr(host.PreviewWindow, "create",
                        classmethod(lambda cls, *a, **k: None))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(
        host.discovery, "list_clients",
        lambda: [_FakeClient("Alice"),
                 _FakeClient("hwnd:0x9", character=None)])
    h._sweep(libs=None)

    assert h.characters() == ["Alice"]


def test_a_changed_client_set_is_reported_once(monkeypatch):
    seen = []
    h = host.PreviewHost(on_layout_changed=lambda *a: None,
                         on_clients_changed=seen.append)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically",
                        lambda: None)
    monkeypatch.setattr(host.PreviewWindow, "create",
                        classmethod(lambda cls, *a, **k: None))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(host.discovery, "list_clients",
                        lambda: [_FakeClient("Alice")])

    h._sweep(libs=None)
    h._sweep(libs=None)      # unchanged: must not report again

    assert seen == [["Alice"]]
```

Add `from obs_youtube_uploader.preview import geometry` to that file's imports,
and `from obs_youtube_uploader.preview.window import PreviewWindow` if
`host.PreviewWindow` is not already reachable.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_preview_host.py -k registry -v`
Expected: FAIL with `AttributeError: 'PreviewHost' object has no attribute '_clients'`

- [ ] **Step 3: Extend `__init__`**

In `obs_youtube_uploader/preview/host.py`, add the parameter and fields:

```python
    def __init__(self, on_layout_changed, saved_layouts=None,
                 size=DEFAULT_SIZE, flush_layouts=None,
                 on_clients_changed=None):
        self._on_layout_changed = on_layout_changed
        self._flush_layouts = flush_layouts
        # Reported outward when the discovered set changes, so the page can
        # order the bind list by who is actually online. Nothing else
        # carries that out of the subsystem: _settings_payload returns
        # persisted settings only.
        self._on_clients_changed = on_clients_changed
        self._saved = dict(saved_layouts or {})
        self._size = size
        self._thread = None
        self._hwnd = None
        self._windows = {}
        # Every DISCOVERED client, not just those with a window. _windows
        # drops any whose creation failed, and a chord aimed at a running
        # client must not depend on its preview having been created.
        self._clients = {}
        self._hook = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
```

- [ ] **Step 4: Refresh the registry in `_sweep`**

Replace the first two statements of `_sweep` and add the reporting at its end:

```python
    def _sweep(self, libs) -> None:
        clients = {c.stable_key: c for c in discovery.list_clients()}
        discovery.flush_image_cache_periodically()
        before = self.characters()
        # Wholesale, never merged. reconcile() compares stable keys only, so
        # a character that reappears on a new HWND between sweeps counts as
        # "kept" -- keeping the old record would leave it pointing at a dead
        # window. Keys survive; handles are re-read.
        self._clients = clients
        added, removed, _kept = reconcile(set(self._windows), set(clients))
```

Then, at the very end of `_sweep`, after the existing `if added or removed:`
logging block:

```python
        now = self.characters()
        if now != before and self._on_clients_changed is not None:
            self._on_clients_changed(now)
```

- [ ] **Step 5: Add the accessor**

Add to `PreviewHost`, next to `is_running`:

```python
    def characters(self) -> list:
        """Named characters currently discovered, sorted. Safe from any
        thread: the registry is replaced wholesale, never mutated in place.

        Clients at character-select are excluded -- discovery falls their
        stable_key back to "hwnd:0x...", which names nothing a user could
        bind to.
        """
        return sorted(key for key in self._clients
                      if not key.startswith("hwnd:"))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_preview_host.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add obs_youtube_uploader/preview/host.py tests/test_preview_host.py
git commit -m "preview: retain the discovered client set on the host"
```

---

### Task 9: Registration, dispatch, status, teardown

**Files:**
- Modify: `obs_youtube_uploader/preview/host.py` — `__init__`, `_run`,
  `_host_proc`, `_teardown`
- Test: `tests/test_preview_host.py`

**Interfaces:**
- Consumes: `gestures.parse`, `cycle.next_key`/`prev_key`, `win32.WM_APP_REBIND`,
  `PreviewHost.characters()` from Task 8.
- Produces:
  - `PreviewHost.set_hotkeys(table: dict) -> None` — `table` is the
    `preview.hotkeys` section; safe from any thread.
  - `PreviewHost.hotkey_status() -> dict` — `{gesture_string: bool}` for the
    most recent registration pass.
  - `PreviewHost(..., on_hotkey_status=None)`.
  - `host.plan_registrations(table) -> list[tuple[int, str, tuple]]` — pure:
    `(hotkey_id, gesture_text, action)`, where action is `("focus", name)` or
    `("cycle", 1 | -1)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_preview_host.py`:

```python
def test_plan_assigns_one_id_per_binding():
    plan = host.plan_registrations(
        {"characters": {"Bravo": "Ctrl+F2", "Alice": "Ctrl+F1"},
         "cycle_next": "Ctrl+Alt+Right", "cycle_prev": "Ctrl+Alt+Left"})
    ids = [entry[0] for entry in plan]
    assert len(ids) == len(set(ids)) == 4
    assert all(0 < i <= 0xBFFF for i in ids)


def test_plan_is_stable_across_calls():
    """Rebinding unregisters and re-registers everything, so an unstable
    id assignment would churn registrations that did not change."""
    table = {"characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F2"},
             "cycle_next": "", "cycle_prev": ""}
    assert host.plan_registrations(table) == host.plan_registrations(table)


def test_plan_drops_unparseable_and_empty_gestures():
    plan = host.plan_registrations(
        {"characters": {"Alice": "", "Bravo": "nonsense", "Carol": "Ctrl+F3"},
         "cycle_next": "", "cycle_prev": ""})
    assert [entry[2] for entry in plan] == [("focus", "Carol")]


def test_plan_drops_a_duplicate_chord():
    """Windows would refuse the second registration anyway; catching it
    here keeps the reported status honest about which binding lost."""
    plan = host.plan_registrations(
        {"characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F1"},
         "cycle_next": "", "cycle_prev": ""})
    assert len(plan) == 1


def test_cycle_actions_carry_direction():
    plan = host.plan_registrations(
        {"characters": {}, "cycle_next": "Ctrl+Alt+Right",
         "cycle_prev": "Ctrl+Alt+Left"})
    actions = sorted(entry[2] for entry in plan)
    assert actions == [("cycle", -1), ("cycle", 1)]
```

And the lifecycle tests, using a fake `libs`:

```python
class _FakeUser32:
    def __init__(self, refuse=()):
        self.registered = {}
        self.unregistered = []
        self.calls = []
        self._refuse = set(refuse)

    def RegisterHotKey(self, hwnd, ident, mods, vk):
        self.calls.append(("register", ident))
        if (mods, vk) in self._refuse:
            return 0
        self.registered[ident] = (mods, vk)
        return 1

    def UnregisterHotKey(self, hwnd, ident):
        self.calls.append(("unregister", ident))
        self.unregistered.append(ident)
        self.registered.pop(ident, None)
        return 1


class _FakeLibs:
    def __init__(self, user32):
        self.user32 = user32


def test_rebind_unregisters_everything_before_registering():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    user32 = _FakeUser32()
    libs = _FakeLibs(user32)

    h._apply_hotkeys(libs, {"characters": {"Alice": "Ctrl+F1"},
                            "cycle_next": "", "cycle_prev": ""})
    user32.calls.clear()
    h._apply_hotkeys(libs, {"characters": {"Bravo": "Ctrl+F2"},
                            "cycle_next": "", "cycle_prev": ""})

    kinds = [kind for kind, _ in user32.calls]
    assert kinds.index("unregister") < kinds.index("register")
    assert list(user32.registered.values()) == [
        (gestures.parse("Ctrl+F2").mods, gestures.parse("Ctrl+F2").vk)]


def test_a_refused_chord_is_reported_and_the_others_still_register():
    refused = gestures.parse("Ctrl+F1")
    user32 = _FakeUser32(refuse={(refused.mods, refused.vk)})
    reported = []
    h = host.PreviewHost(on_layout_changed=lambda *a: None,
                         on_hotkey_status=reported.append)
    h._hwnd = 0x99

    h._apply_hotkeys(_FakeLibs(user32),
                     {"characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F2"},
                      "cycle_next": "", "cycle_prev": ""})

    assert h.hotkey_status() == {"Ctrl+F1": False, "Ctrl+F2": True}
    assert reported == [{"Ctrl+F1": False, "Ctrl+F2": True}]


def test_status_is_readable_after_a_pass_that_reported_to_nobody():
    """Previews start BEFORE the webview exists (__main__.py:406-411), so a
    conflict at launch is announced into the void. It has to be readable
    afterwards or it is lost for the session."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._apply_hotkeys(_FakeLibs(_FakeUser32()),
                     {"characters": {"Alice": "Ctrl+F1"},
                      "cycle_next": "", "cycle_prev": ""})
    assert h.hotkey_status() == {"Ctrl+F1": True}


def test_teardown_releases_hotkeys_before_destroying_the_host_window():
    """Ordering the parent design's Lifecycle section requires: chords must
    be released before the window they are registered against dies."""
    order = []

    class _Tracking(_FakeUser32):
        def UnregisterHotKey(self, hwnd, ident):
            order.append("unregister-hotkey")
            return super().UnregisterHotKey(hwnd, ident)

        def UnhookWinEvent(self, hook):
            order.append("unhook")
            return 1

        def KillTimer(self, hwnd, ident):
            return 1

        def DestroyWindow(self, hwnd):
            order.append("destroy-window")
            return 1

        def PostQuitMessage(self, code):
            order.append("quit")

    user32 = _Tracking()
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._hook = 0x55
    libs = _FakeLibs(user32)
    h._apply_hotkeys(libs, {"characters": {"Alice": "Ctrl+F1"},
                            "cycle_next": "", "cycle_prev": ""})

    h._teardown(libs)

    assert order == ["unregister-hotkey", "unhook", "destroy-window", "quit"]


def test_hotkey_focuses_the_named_character(monkeypatch):
    activated = []
    monkeypatch.setattr(host.window_mod, "activate",
                        lambda libs, hwnd: activated.append(hwnd) or True)
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1234)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0
    libs = _FakeLibs(user32)
    h._apply_hotkeys(libs, {"characters": {"Alice": "Ctrl+F1"},
                            "cycle_next": "", "cycle_prev": ""})

    ident = next(iter(user32.registered))
    h._on_hotkey(libs, ident)

    assert activated == [0x1234]


def test_cycle_hotkey_anchors_on_the_foreground_client(monkeypatch):
    activated = []
    monkeypatch.setattr(host.window_mod, "activate",
                        lambda libs, hwnd: activated.append(hwnd) or True)
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1111),
                  "Bravo": _FakeClient("Bravo", hwnd=0x2222)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0x1111
    libs = _FakeLibs(user32)
    h._apply_hotkeys(libs, {"characters": {}, "cycle_next": "Ctrl+Alt+Right",
                            "cycle_prev": ""})

    ident = next(iter(user32.registered))
    h._on_hotkey(libs, ident)

    assert activated == [0x2222]


def test_a_focus_chord_for_an_absent_character_does_nothing(monkeypatch):
    activated = []
    monkeypatch.setattr(host.window_mod, "activate",
                        lambda libs, hwnd: activated.append(hwnd) or True)
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {}
    user32 = _FakeUser32()
    libs = _FakeLibs(user32)
    h._apply_hotkeys(libs, {"characters": {"Ghost": "Ctrl+F1"},
                            "cycle_next": "", "cycle_prev": ""})

    h._on_hotkey(libs, next(iter(user32.registered)))

    assert activated == []
```

Add `from obs_youtube_uploader.preview import gestures` to the test imports.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_preview_host.py -k "plan_ or hotkey or teardown_releases" -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'plan_registrations'`

- [ ] **Step 3: Add the pure planner**

In `obs_youtube_uploader/preview/host.py`, extend the existing module-level
imports. The current lines are:

```python
from . import discovery, geometry, layout, win32
from .window import PreviewWindow
```

Replace them with:

```python
from . import cycle, discovery, gestures, geometry, layout, win32
from . import window as window_mod
from .window import PreviewWindow
```

Both window imports are needed: `PreviewWindow` is already used by `_sweep`,
and `window_mod` reaches the module-level `activate()` helper that hotkey
dispatch calls.

Then add the planner next to `reconcile`:
```python
HOTKEY_ID_BASE = 1
HOTKEY_ID_MAX = 0xBFFF     # Windows reserves 0xC000+ for DLLs


def plan_registrations(table) -> list:
    """(hotkey_id, gesture_text, action) for every registerable binding.

    Pure, and separated from the Win32 half for exactly that reason: id
    assignment, duplicate rejection and gesture validation are where the
    bugs are, and none of them need a window.

    Order is deterministic so a rebind that changed nothing produces the
    same ids -- rebinding unregisters and re-registers wholesale, and an
    unstable assignment would churn registrations that did not change.
    """
    table = table if isinstance(table, dict) else {}
    characters = table.get("characters")
    entries = []
    if isinstance(characters, dict):
        for name in sorted(characters):
            entries.append((characters[name], ("focus", name)))
    entries.append((table.get("cycle_next"), ("cycle", 1)))
    entries.append((table.get("cycle_prev"), ("cycle", -1)))

    plan, claimed = [], set()
    for text, action in entries:
        parsed = gestures.parse(text)
        if parsed is None:
            continue
        canonical = gestures.display(parsed)
        if canonical in claimed:
            # Windows would refuse the second registration anyway. Dropping
            # it here keeps the reported status honest about which binding
            # actually lost.
            continue
        ident = HOTKEY_ID_BASE + len(plan)
        if ident > HOTKEY_ID_MAX:
            logger.warning("Too many preview hotkeys; dropping %s", canonical)
            break
        claimed.add(canonical)
        plan.append((ident, canonical, action))
    return plan
```

- [ ] **Step 4: Add the host fields and public methods**

Add to `__init__`, after `self._clients = {}`:

```python
        self._on_hotkey_status = on_hotkey_status
        # The desired table, written by any thread and read by the preview
        # thread when it processes WM_APP_REBIND. PostMessage cannot carry
        # a dict, so the value travels in a field and only the signal is
        # posted -- the same shape _saved already uses.
        self._desired_hotkeys = {}
        self._registered = {}     # hotkey_id -> action
        self._hotkey_status = {}  # gesture text -> registered?
        self._last_cycled = None
```

and the parameter to the signature:

```python
    def __init__(self, on_layout_changed, saved_layouts=None,
                 size=DEFAULT_SIZE, flush_layouts=None,
                 on_clients_changed=None, on_hotkey_status=None):
```

Add the public methods next to `request_sweep`:

```python
    def set_hotkeys(self, table) -> None:
        """Replace the whole binding table. Safe from any thread.

        Wholesale rather than diffed: the table is a dozen entries, and
        diffing registration state against Windows is a bug farm for no
        measurable gain.
        """
        with self._lock:
            self._desired_hotkeys = dict(table or {})
        if self._hwnd:
            win32.bind().user32.PostMessageW(self._hwnd,
                                             win32.WM_APP_REBIND, 0, 0)

    def hotkey_status(self) -> dict:
        """Outcome of the most recent registration pass.

        Readable, not only announced. Previews start before the webview
        exists (__main__.py:406-411), so a conflict found at launch has
        nowhere to be pushed and would otherwise be lost for the session.
        """
        return dict(self._hotkey_status)
```

- [ ] **Step 5: Add registration, dispatch and teardown**

Add these methods to the "runs ON the preview thread" half of `PreviewHost`:

```python
    def _apply_hotkeys(self, libs, table) -> None:
        """Unregister everything, then register the new table."""
        for ident in list(self._registered):
            libs.user32.UnregisterHotKey(self._hwnd, ident)
        self._registered.clear()

        status = {}
        for ident, text, action in plan_registrations(table):
            parsed = gestures.parse(text)
            ok = bool(libs.user32.RegisterHotKey(self._hwnd, ident,
                                                 parsed.mods, parsed.vk))
            status[text] = ok
            if ok:
                self._registered[ident] = action
            else:
                # A chord another application already owns. User-actionable,
                # not a bug -- and the parent design requires it be visible
                # rather than logged only.
                logger.warning("Could not register preview hotkey %s; "
                               "another application may already own it", text)
        self._hotkey_status = status
        if self._on_hotkey_status is not None:
            self._on_hotkey_status(dict(status))

    def _on_hotkey(self, libs, ident) -> None:
        action = self._registered.get(ident)
        if action is None:
            return
        kind, value = action
        if kind == "focus":
            target = value
        else:
            foreground = libs.user32.GetForegroundWindow()
            anchor = next((key for key, client in self._clients.items()
                           if client.hwnd == foreground), None)
            # Fall back to the last chord's target when focus is not on a
            # client at all -- a browser, or Wingman itself.
            target = cycle.step(self.characters(),
                                anchor or self._last_cycled, value)
            self._last_cycled = target
        client = self._clients.get(target)
        if client is None:
            return    # bound to a character that is not running: correct no-op
        window_mod.activate(libs, client.hwnd)
```

Add the dispatch arm to `_host_proc`, before the `DefWindowProcW` fallthrough:

```python
        if msg == win32.WM_APP_REBIND:
            with self._lock:
                table = dict(self._desired_hotkeys)
            self._apply_hotkeys(libs, table)
            return 0
        if msg == win32.WM_HOTKEY:
            self._on_hotkey(libs, wparam)
            return 0
```

Register the initial table in `_run`, immediately after `self._install_hook(libs)`:

```python
        with self._lock:
            initial = dict(self._desired_hotkeys)
        self._apply_hotkeys(libs, initial)
```

And in `_teardown`, insert as the **first** HWND step, above the `if self._hook:`
block:

```python
        # Step 1, before the window they are registered against dies. The
        # parent design's Lifecycle section lists this first and noted its
        # absence; it stops being harmless the moment anything registers.
        for ident in list(self._registered):
            libs.user32.UnregisterHotKey(self._hwnd, ident)
        self._registered.clear()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_preview_host.py -v`
Expected: PASS

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/preview/host.py tests/test_preview_host.py
git commit -m "preview: register, dispatch and release hotkeys"
```

---

### Task 10: Record the roster from discovery

**Files:**
- Modify: `obs_youtube_uploader/preview/store.py`
- Test: `tests/test_preview_store.py`

**Interfaces:**
- Consumes: `roster.touch`, `LayoutStore` from Task 2.
- Produces: `LayoutStore.record_character(name: str) -> None` — debounced and
  merged like layout writes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_preview_store.py`:

```python
def test_record_character_moves_a_seen_name_to_the_front():
    live = {"preview": {"seen": ["Bravo", "Alice"]}}
    store = LayoutStore(update_settings=_updater(live), timer=_ImmediateTimer)
    store.record_character("Alice")
    store.flush()
    assert live["preview"]["seen"] == ["Alice", "Bravo"]


def test_record_character_never_persists_a_character_select_client():
    live = {"preview": {"seen": []}}
    store = LayoutStore(update_settings=_updater(live), timer=_ImmediateTimer)
    store.record_character("hwnd:0x1234")
    store.flush()
    assert live["preview"]["seen"] == []


def test_a_bound_character_is_protected_from_eviction():
    live = {"preview": {"seen": [f"C{i}" for i in range(64)],
                        "hotkeys": {"characters": {"C63": "Ctrl+F1"}}}}
    store = LayoutStore(update_settings=_updater(live), timer=_ImmediateTimer)
    store.record_character("New")
    store.flush()
    assert "C63" in live["preview"]["seen"]


def test_layout_and_roster_writes_share_one_transaction():
    """A drag and a discovery landing together must not open the settings
    document twice."""
    live = {"preview": {"layouts": {}, "seen": []}}
    opened = []
    store = LayoutStore(update_settings=_updater(live, opened),
                        timer=_ImmediateTimer)
    store.record("Alice", layout.Entry(Rect(1, 2, 3, 4), False))
    store.record_character("Alice")
    store.flush()
    assert opened.count("enter") == 1
    assert live["preview"]["seen"] == ["Alice"]
    assert "Alice" in live["preview"]["layouts"]
```

Add the helper above them:

```python
def _updater(live, log=None):
    import contextlib

    @contextlib.contextmanager
    def fake_update():
        if log is not None:
            log.append("enter")
        yield live
        if log is not None:
            log.append("exit")

    return fake_update
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_preview_store.py -k character -v`
Expected: FAIL with `AttributeError: 'LayoutStore' object has no attribute 'record_character'`

- [ ] **Step 3: Implement it**

In `obs_youtube_uploader/preview/store.py`, add `from . import layout, roster`
to the imports, then add the pending set and the method:

In `__init__`, after `self._pending = {}`:

```python
        self._pending_names = []
```

```python
    def record_character(self, name: str) -> None:
        """Note that *name* was seen. Safe from the preview thread.

        Shares the layout debounce rather than adding a second one: a sweep
        that discovers a client often coincides with a layout write, and two
        timers would open the settings document twice for one event.
        """
        with self._lock:
            if name in self._pending_names:
                return
            self._pending_names.append(name)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = self._timer_factory(self._debounce_s, self._write)
        self._timer.start()
```

Replace `_write`'s body with the combined version:

```python
    def _write(self) -> None:
        with self._lock:
            pending, self._pending = dict(self._pending), {}
            names, self._pending_names = list(self._pending_names), []
            self._timer = None
        if not pending and not names:
            return
        try:
            with self._update_settings() as live:
                section = live.setdefault("preview", {})
                if pending:
                    layouts = dict(section.setdefault("layouts", {}))
                    layouts.update(layout.serialize(pending))  # per-key merge
                    section["layouts"] = layouts
                for name in names:
                    # Bound characters are protected: evicting one would
                    # leave a chord the bind list has no row to show.
                    bound = set(section.get("hotkeys", {})
                                .get("characters", {}))
                    section["seen"] = roster.touch(section.get("seen", []),
                                                   name, protected=bound)
        except OSError:
            logger.exception("Could not persist preview state")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_preview_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/store.py tests/test_preview_store.py
git commit -m "preview: record every character seen into the roster"
```

---

### Task 11: Bridge methods and wiring

**Files:**
- Modify: `obs_youtube_uploader/ui/api.py:1214-1280` (preview section)
- Modify: `obs_youtube_uploader/__main__.py:283-324` (`build_preview_host`)
- Test: `tests/test_api.py`, `tests/test_preview_wiring.py`

**Interfaces:**
- Consumes: `PreviewHost.set_hotkeys`, `.hotkey_status`, `.characters`,
  `LayoutStore.record_character`, `gestures.from_capture`/`parse`/`display`.
- Produces (all callable from the page):
  - `Api.capture_preview_bind(parts) -> dict`
  - `Api.parse_preview_bind(text) -> dict`
  - `Api.set_preview_binds(section) -> bool`
  - `Api.get_preview_hotkey_state() -> dict` with keys `registration`
    (`{gesture: bool}`), `characters` (list), `roster` (list), `hotkeys`
    (dict), `enabled` (bool), and `bookmark_chords`
    (`{"active": [...], "latent": [...]}`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`:

```python
def test_capture_preview_bind_returns_a_canonical_gesture(api):
    result = api.capture_preview_bind({"ctrl": True, "alt": True,
                                       "code": "F1"})
    assert result == {"gesture": "Ctrl+Alt+F1", "error": None}


def test_parse_preview_bind_reports_a_rejected_chord(api):
    assert api.parse_preview_bind("F1")["error"] == "unparseable"
    assert api.parse_preview_bind("Ctrl+F1")["gesture"] == "Ctrl+F1"


def test_set_preview_binds_persists_and_pushes_to_the_host(api, fake_host):
    ok = api.set_preview_binds({"characters": {"Alice": "ctrl+f1"},
                                "cycle_next": "", "cycle_prev": ""})
    assert ok is True
    stored = api._state.settings["preview"]["hotkeys"]["characters"]
    assert stored == {"Alice": "Ctrl+F1"}          # canonicalised
    assert fake_host.hotkeys["characters"] == {"Alice": "Ctrl+F1"}


def test_set_preview_binds_rejects_an_unparseable_chord(api, fake_host):
    assert api.set_preview_binds({"characters": {"Alice": "nonsense"}}) is False
    assert api._state.settings["preview"]["hotkeys"]["characters"] == {}


def test_hotkey_state_reports_registration_and_live_characters(api, fake_host):
    fake_host.status = {"Ctrl+F1": False}
    fake_host.chars = ["Alice"]
    state = api.get_preview_hotkey_state()
    assert state["registration"] == {"Ctrl+F1": False}
    assert state["characters"] == ["Alice"]


def test_hotkey_state_is_readable_with_no_host(api_without_host):
    """Off Windows the host is None and every call site must stay a plain
    no-op rather than a platform check."""
    state = api_without_host.get_preview_hotkey_state()
    assert state["characters"] == []
    assert state["registration"] == {}


def test_bookmark_chords_are_active_only_when_they_are_registered(api,
                                                                 fake_host):
    """A bookmark bind is registered only for enabled window titles under an
    enabled feature. Warning about chords that are not registered anywhere
    would cry wolf -- but the collision goes latent rather than away, so it
    is still reported, just not as a warning."""
    api._state.settings["eve_bookmarks"] = {
        "enabled": True, "keybinds": {"GrabSig": "^q"},
        "windows": {"EVE - A": True}}
    chords = api.get_preview_hotkey_state()["bookmark_chords"]
    assert chords == {"active": ["Ctrl+Q"], "latent": []}

    api._state.settings["eve_bookmarks"]["enabled"] = False
    chords = api.get_preview_hotkey_state()["bookmark_chords"]
    assert chords == {"active": [], "latent": ["Ctrl+Q"]}

    api._state.settings["eve_bookmarks"]["enabled"] = True
    api._state.settings["eve_bookmarks"]["windows"] = {"EVE - A": False}
    chords = api.get_preview_hotkey_state()["bookmark_chords"]
    assert chords == {"active": [], "latent": ["Ctrl+Q"]}


def test_bookmark_chords_are_rendered_in_gesture_display_form(api, fake_host):
    """The two features store different notation on purpose, so the clash
    check needs a common form or it silently never matches."""
    api._state.settings["eve_bookmarks"] = {
        "enabled": True, "windows": {"EVE - A": True},
        "keybinds": {"GrabSig": "^+s", "FinH": "^y"}}
    assert api.get_preview_hotkey_state()["bookmark_chords"]["active"] == [
        "Ctrl+Shift+S", "Ctrl+Y"]
```

Add fixtures near the existing api fixtures in that file:

```python
class _FakeHost:
    def __init__(self):
        self.hotkeys = None
        self.status = {}
        self.chars = []
        self.started = False

    def set_hotkeys(self, table):
        self.hotkeys = table

    def hotkey_status(self):
        return dict(self.status)

    def characters(self):
        return list(self.chars)

    def start(self):
        self.started = True

    def stop(self):
        self.started = False


@pytest.fixture
def fake_host():
    return _FakeHost()
```

and make the existing `api` fixture accept `fake_host` by passing
`preview_host=fake_host` to the `Api(...)` construction, adding an
`api_without_host` fixture that passes `preview_host=None`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_api.py -k preview_bind -v`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'capture_preview_bind'`

- [ ] **Step 3: Add the bridge methods**

In `obs_youtube_uploader/ui/api.py`, add to the imports:

```python
from ..preview import gestures as preview_gestures
```

Append to the "EVE client previews" section:

```python
    def capture_preview_bind(self, parts) -> dict:
        return preview_gestures.from_capture(
            parts if isinstance(parts, dict) else {})

    def parse_preview_bind(self, text) -> dict:
        parsed = preview_gestures.parse(text if isinstance(text, str) else "")
        if parsed is None:
            return {"gesture": "", "error": "unparseable"}
        return {"gesture": preview_gestures.display(parsed), "error": None}

    def set_preview_binds(self, section) -> bool:
        """Replace the whole binding table, persist it, and push it down.

        Returns False on a chord that will not parse rather than silently
        dropping it: the page needs to tell a rejected entry from a saved
        one, and WM.send resolves to null on a bridge failure, so a bare
        None would be indistinguishable from a broken call.
        """
        if not isinstance(section, dict):
            return False
        table = {"characters": {}, "cycle_next": "", "cycle_prev": ""}
        characters = section.get("characters")
        if isinstance(characters, dict):
            for name, text in characters.items():
                if not isinstance(name, str) or name.startswith("hwnd:"):
                    return False
                if not text:
                    continue      # cleared, not invalid
                parsed = preview_gestures.parse(text)
                if parsed is None:
                    return False
                table["characters"][name] = preview_gestures.display(parsed)
        for key in ("cycle_next", "cycle_prev"):
            text = section.get(key)
            if not text:
                continue
            parsed = preview_gestures.parse(text)
            if parsed is None:
                return False
            table[key] = preview_gestures.display(parsed)

        try:
            with settings_mod.update(self._state.settings) as cfg:
                cfg.setdefault("preview", {})["hotkeys"] = table
        except OSError:
            logger.exception("Could not persist preview hotkeys")
            return False

        if self._preview_host is not None:
            self._preview_host.set_hotkeys(table)
        return True

    def get_preview_hotkey_state(self) -> dict:
        """Everything the bind list needs, in one read.

        A read, not a push, and that is the point: previews start before the
        webview exists (__main__.py:406-411), so a registration conflict
        found at launch is pushed into a window that is not there yet and
        _push swallows it. The page asks for this on load.
        """
        section = self._state.settings.get("preview", {})
        host = self._preview_host
        return {
            "enabled": bool(section.get("enabled")),
            "hotkeys": dict(section.get("hotkeys") or {}),
            "roster": list(section.get("seen") or []),
            "characters": host.characters() if host is not None else [],
            "registration": host.hotkey_status() if host is not None else {},
            "bookmark_chords": self._bookmark_chords(),
        }

    def _bookmark_chords(self) -> dict:
        """Bookmark chords, split by whether they are registered right now.

        A preview chord is global; a bookmark chord is an AHK hotkey scoped
        with #HotIf WinActive. Where they collide the preview wins WHILE EVE
        IS FOCUSED, silently taking a key from the feature that bind was
        written for -- and Windows reports nothing, because AHK's scoped
        hotkey is not a RegisterHotKey registration to collide with. Only
        Wingman can catch this, by reading both of its own sections.

        Split rather than filtered, because the collision does not stop
        existing when bookmarks are off -- it goes latent, and enabling them
        later resurrects it with nothing on screen to explain why that bind
        stopped working. "active" warns; "latent" only marks.

        Compared in display form. The two features store different notation
        on purpose (see preview/gestures.py), but bookmarks.parse_ahk
        renders "^q" as "Ctrl+Q" using the same modifier order and key names
        gestures.display uses, so the display string is the common ground.
        """
        eve = self._state.settings.get("eve_bookmarks") or {}
        chords = set()
        for value in (eve.get("keybinds") or {}).values():
            if not value:
                continue
            rendered = bookmarks.parse_ahk(value).get("display")
            if rendered:
                chords.add(rendered)
        live = bool(eve.get("enabled")) and any(eve.get("windows", {}).values())
        return {"active": sorted(chords) if live else [],
                "latent": [] if live else sorted(chords)}

    def push_preview_hotkeys(self, status=None) -> None:
        """Announce a change to a page that is already up. Never the only
        path -- see get_preview_hotkey_state."""
        payload = self.get_preview_hotkey_state()
        if status is not None:
            payload["registration"] = status
        self._push("onPreviewHotkeys", payload)
```

- [ ] **Step 4: Register the initial table at startup**

In `start_previews_if_enabled`, push the stored table down before starting, so
the first registration pass has it:

```python
        section = self._state.settings.get("preview", {})
        self._preview_host.set_hotkeys(section.get("hotkeys") or {})
        if section.get("enabled"):
            self._preview_host.start()
```

- [ ] **Step 5: Wire the callbacks**

In `obs_youtube_uploader/__main__.py`, `build_preview_host` gains an `api_ref`
mutable holder so the host can call back into the Api once it exists. Replace
the `PreviewHost(...)` construction:

```python
        def on_clients_changed(characters):
            for name in characters:
                store.record_character(name)
            api = api_box.get("api")
            if api is not None:
                api.push_preview_hotkeys()

        def on_hotkey_status(status):
            api = api_box.get("api")
            if api is not None:
                api.push_preview_hotkeys(status)

        return PreviewHost(
            on_layout_changed=on_layout_changed,
            saved_layouts=preview_layout.deserialize(section.get("layouts")),
            size=(section.get("width", 320), section.get("height", 210)),
            flush_layouts=store.flush,
            on_clients_changed=on_clients_changed,
            on_hotkey_status=on_hotkey_status)
```

Add the holder as a parameter, `def build_preview_host(state, api_box):`, and at
the call site:

```python
    api_box = {}
    api = api_mod.Api(state, preview_host=build_preview_host(state, api_box))
    api_box["api"] = api
```

A plain dict rather than a closure over `api`: the host is constructed *as an
argument to* `Api(...)`, so the name does not exist yet when the callbacks are
defined.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_api.py tests/test_preview_wiring.py -v`
Expected: PASS. Update `tests/test_preview_wiring.py` for the new
`build_preview_host` signature — that file exists to record what a lazily
resolved name cost last time, so keep its bound-method assertions intact.

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/ui/api.py obs_youtube_uploader/__main__.py \
        tests/test_api.py tests/test_preview_wiring.py
git commit -m "api: expose preview hotkey binding and status"
```

---

### Task 12: The bind list UI

**Files:**
- Create: `obs_youtube_uploader/web/previews.js`
- Modify: `obs_youtube_uploader/web/index.html:260-280`
- Test: manual (the page has no JS test harness; `tests/test_packaging_completeness.py` covers shipping the file)

**Interfaces:**
- Consumes: `get_preview_hotkey_state`, `set_preview_binds`,
  `capture_preview_bind`, `parse_preview_bind`, and the `onPreviewHotkeys` push.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Add the markup**

In `obs_youtube_uploader/web/index.html`, inside `#route-previews`, after the
existing hint row's `</section>`, add a second card:

```html
      <section class="card">
        <h2>Hotkeys</h2>
        <div class="row"><span class="lab"></span>
          <span class="hint">Chords are global: they work from any
            application, including a browser. They are released while
            previews are switched off.</span></div>
        <div id="preview-binds"></div>
        <div class="row"><span class="lab"></span>
          <span class="hint" id="preview-binds-empty">Start an EVE client to
            add a character here.</span></div>
      </section>
```

Add the script tag next to the other page modules, matching how `bookmarks.js`
is included:

```html
  <script src="previews.js"></script>
```

- [ ] **Step 2: Write the module**

Create `obs_youtube_uploader/web/previews.js`:

```javascript
// Preview hotkeys. The row shape deliberately mirrors bookmarks.js: a
// capture button, a Clear, and a Type... escape hatch. That is not copied
// for consistency -- capture reads event.code, which maps a physical key to
// the wrong character on non-US layouts, and manual entry is the way out.
// Both paths are validated by the same Python rules so they cannot disagree.
(function () {
  var host = WM.el('preview-binds');
  if (!host) { return; }

  var state = {hotkeys: {characters: {}, cycle_next: '', cycle_prev: ''},
               characters: [], roster: [], registration: {},
               bookmark_chords: {active: [], latent: []}, enabled: false};
  var capturing = null;

  function bookmarkClash(gesture) {
    // Active: the bookmark bind is registered right now, so this chord
    // takes it away while EVE is focused. Latent: bookmarks are off or no
    // window is enabled, so nothing is stolen yet -- but turning them on
    // would, with nothing on screen to explain it.
    var chords = state.bookmark_chords || {};
    if ((chords.active || []).indexOf(gesture) !== -1) { return 'active'; }
    if ((chords.latent || []).indexOf(gesture) !== -1) { return 'latent'; }
    return null;
  }

  function rows() {
    // Running first, then known-but-offline, then any binding whose
    // character is in neither -- a chord with no row would be invisible.
    var seen = {}, out = [];
    state.characters.forEach(function (n) {
      if (!seen[n]) { seen[n] = 1; out.push({name: n, online: true}); }
    });
    state.roster.forEach(function (n) {
      if (!seen[n]) { seen[n] = 1; out.push({name: n, online: false}); }
    });
    Object.keys(state.hotkeys.characters || {}).forEach(function (n) {
      if (!seen[n]) { seen[n] = 1; out.push({name: n, online: false}); }
    });
    return out;
  }

  function clashes(gesture) {
    if (!gesture) { return null; }
    var count = 0;
    var binds = state.hotkeys.characters || {};
    Object.keys(binds).forEach(function (n) {
      if (binds[n] === gesture) { count += 1; }
    });
    if (state.hotkeys.cycle_next === gesture) { count += 1; }
    if (state.hotkeys.cycle_prev === gesture) { count += 1; }
    if (count > 1) { return 'duplicate'; }
    if (state.registration[gesture] === false) { return 'refused'; }
    return null;
  }

  function makeRow(label, gesture, online, onSet) {
    var row = WM.make('div', 'row');
    var lab = WM.make('span', 'lab', label);
    // Offline is information, not an error: the binding is still saved and
    // still works the moment that character logs in.
    if (online === false) { lab.classList.add('dim'); }
    row.appendChild(lab);

    var button = WM.make('button', 'bindbtn', gesture || 'Not set');
    var clash = clashes(gesture);
    var shadow = bookmarkClash(gesture);
    // An active bookmark collision warns like any other clash; a latent one
    // only marks, because nothing is being taken away yet.
    if (clash || shadow === 'active') { button.classList.add('clash'); }
    else if (shadow === 'latent') { button.classList.add('dim'); }
    if (clash === 'refused') {
      button.title = 'Another application already owns this chord.';
    } else if (clash === 'duplicate') {
      button.title = 'This chord is bound twice here.';
    } else if (shadow === 'active') {
      button.title = 'An EVE bookmark uses this chord. This binding takes ' +
                     'it while an EVE client is focused.';
    } else if (shadow === 'latent') {
      button.title = 'An EVE bookmark is configured with this chord. ' +
                     'Enabling bookmarks would make them collide.';
    }
    button.addEventListener('click', function () {
      beginCapture(button, onSet);
    });
    row.appendChild(button);

    var clear = WM.make('button', 'linkbtn', 'Clear');
    clear.addEventListener('click', function () { endCapture(); onSet(''); });
    row.appendChild(clear);

    var typed = WM.make('button', 'linkbtn', 'Type…');
    typed.addEventListener('click', function () {
      endCapture();
      var text = window.prompt(
        'Hotkey for "' + label + '"\n' +
        'Ctrl, Alt, Shift and Win, plus a key. Example: Ctrl+Alt+F1',
        gesture || '');
      if (text === null) { return; }
      if (text === '') { onSet(''); return; }
      WM.send('parse_preview_bind', text).then(function (result) {
        if (!result) { return; }
        if (result.error) {
          WM.send('alert_bookmarks',
                  'That is not a hotkey Windows can register. It needs at ' +
                  'least one of Ctrl, Alt, Shift or Win, plus a key.');
          return;
        }
        onSet(result.gesture);
      });
    });
    row.appendChild(typed);
    return row;
  }

  function beginCapture(button, onSet) {
    if (capturing) {
      // Revert the previous button WITHOUT a full re-render: that would
      // detach the button just clicked before it is armed below. Same trap
      // bookmarks.js documents.
      capturing.button.classList.remove('capturing');
      capturing.button.textContent = capturing.previous || 'Not set';
    }
    capturing = {button: button, onSet: onSet,
                 previous: button.textContent};
    button.textContent = 'Press a key…';
    button.classList.add('capturing');
  }

  function endCapture() {
    if (!capturing) { return; }
    capturing.button.classList.remove('capturing');
    capturing.button.textContent = capturing.previous || 'Not set';
    capturing = null;
  }

  function render() {
    host.textContent = '';
    host.appendChild(makeRow('Cycle forward', state.hotkeys.cycle_next, true,
                             function (g) { setBind('cycle_next', g); }));
    host.appendChild(makeRow('Cycle back', state.hotkeys.cycle_prev, true,
                             function (g) { setBind('cycle_prev', g); }));

    var list = rows();
    list.forEach(function (entry) {
      host.appendChild(makeRow(
        entry.name, (state.hotkeys.characters || {})[entry.name],
        entry.online,
        function (g) { setCharacterBind(entry.name, g); }));
    });

    var empty = WM.el('preview-binds-empty');
    if (empty) { empty.style.display = list.length ? 'none' : ''; }
  }

  function send(next) {
    WM.send('set_preview_binds', next).then(function (ok) {
      if (!ok) {
        // WM.send resolves to null on a bridge error, and Python returns
        // false on a rejected chord. Either way the page must not keep
        // showing a binding the backend never accepted.
        refresh();
        return;
      }
      state.hotkeys = next;
      render();
    });
  }

  function setBind(key, gesture) {
    endCapture();
    var next = JSON.parse(JSON.stringify(state.hotkeys));
    next[key] = gesture;
    send(next);
  }

  function setCharacterBind(name, gesture) {
    endCapture();
    var next = JSON.parse(JSON.stringify(state.hotkeys));
    next.characters = next.characters || {};
    if (gesture) { next.characters[name] = gesture; }
    else { delete next.characters[name]; }
    send(next);
  }

  function refresh() {
    WM.send('get_preview_hotkey_state').then(function (payload) {
      if (!payload) { return; }
      state = payload;
      state.hotkeys = state.hotkeys || {characters: {}, cycle_next: '',
                                        cycle_prev: ''};
      render();
    });
  }

  document.addEventListener('keydown', function (event) {
    if (!capturing) { return; }
    event.preventDefault();
    event.stopPropagation();
    if (event.key === 'Escape') { endCapture(); return; }
    // Held synchronously: by the time the bridge resolves the user may have
    // pressed Escape or clicked another row.
    var session = capturing;
    WM.send('capture_preview_bind', {
      ctrl: event.ctrlKey, alt: event.altKey,
      shift: event.shiftKey, meta: event.metaKey, code: event.code
    }).then(function (result) {
      if (!result || result.error === 'modifier-only') { return; }
      if (capturing !== session) { return; }
      if (result.error) {
        endCapture();
        WM.send('alert_bookmarks',
                result.error === 'no-modifier'
                  ? 'A preview hotkey needs at least one of Ctrl, Alt, ' +
                    'Shift or Win, or it would fire in every application.'
                  : 'That key cannot be used as a hotkey.');
        return;
      }
      var apply = session.onSet;
      endCapture();
      apply(result.gesture);
    });
  });

  // Python volunteers this when registration or the client set changes.
  window.onPreviewHotkeys = function (payload) {
    if (!payload) { return; }
    state = payload;
    state.hotkeys = state.hotkeys || {characters: {}, cycle_next: '',
                                      cycle_prev: ''};
    render();
  };

  document.addEventListener('wm:settings', refresh);
  refresh();
}());
```

- [ ] **Step 3: Check the file ships**

Run: `python -m pytest tests/test_packaging_completeness.py -v`
Expected: PASS. If that test enumerates web assets by hand, add `previews.js`
to its list — a missing entry installs cleanly and fails only in the frozen
build.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/web/previews.js obs_youtube_uploader/web/index.html \
        tests/test_packaging_completeness.py
git commit -m "web: bind list for preview hotkeys"
```

---

### Task 13: Smoke checks for the half CI cannot reach

**Files:**
- Modify: `docs/smoke-checklist.md`

- [ ] **Step 1: Add the section**

Append to `docs/smoke-checklist.md`, following the file's existing
`- [ ]` style and its convention of marking load-bearing items in bold:

```markdown
## EVE preview hotkeys

- [ ] **LOAD-BEARING: `WM_HOTKEY` reaches the message-only host window.**
  Bind any chord and press it. If nothing happens while the log shows a
  successful registration, `HWND_MESSAGE` is not receiving the message and
  registration must move to `hWnd=NULL` with dispatch in the pump loop —
  see risk 4 in `eve-preview-hotkeys-design.md`.
- [ ] A per-character chord switches to that client from another application
  (try it from a browser, not just from Wingman).
- [ ] Cycle forward and back walk every running client in name order and wrap.
- [ ] **Holding a chord fires once, not at the key-repeat rate.** Hold it for
  three seconds; the client must not flicker through repeated activations.
- [ ] **A chord another application already owns is visible on the Previews
  tab**, not only in the log. Bind something a running app claims, restart
  Wingman, and check the tab BEFORE touching anything — this is the startup
  case where the push has no window to reach.
- [ ] Switching previews off releases the chords: they do nothing, and the
  application that owns them gets them back. Switching previews on reclaims
  them.
- [ ] A binding made for a character survives a restart while that character
  is logged off, and still appears in the list.
- [ ] With EVE bookmarks enabled and a window enabled, binding a preview chord
  that matches a bookmark bind shows the collision warning. With bookmarks
  disabled, it does not warn.
- [ ] Quitting Wingman with chords bound leaves them released: the owning
  application gets them back without a reboot.
```

- [ ] **Step 2: Commit**

```bash
git add docs/smoke-checklist.md
git commit -m "docs: smoke checks for preview hotkeys"
```

---

## Verification before claiming completion

- [ ] `python -m pytest -q` — full suite green.
- [ ] `git diff main --stat` — nothing outside the files this plan names.
- [ ] `grep -rn "hwnd:" obs_youtube_uploader/preview/roster.py obs_youtube_uploader/ui/api.py`
      — every persistence path still filters character-select clients.
- [ ] No `settings.save()` call remains inside a `settings.update()` block
      (it would deadlock — the lock is not reentrant).
- [ ] `python -c "import obs_youtube_uploader.preview.gestures, obs_youtube_uploader.preview.cycle, obs_youtube_uploader.preview.roster"`
      on Linux — the new modules import with no Windows.
- [ ] The Windows-only half is **unverified by the suite**. Say so plainly, and
      walk `docs/smoke-checklist.md`'s new section before calling this done.
