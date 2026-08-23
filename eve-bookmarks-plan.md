# EVE Bookmark Helper Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Absorb the standalone EVE wormhole bookmark AutoHotkey script into FlyGD Wingman as a second feature area, configured natively and driven by a supervised background engine.

**Architecture:** `settings.json` is the single source of truth. Wingman generates the INI the engine reads, publishes commands through a sequence-numbered file, and reads status back — every cross-process file has exactly one writer and is published atomically. AutoHotkey is hidden behind a `HotkeyEngine` interface so it can be swapped for a native implementation later without touching the UI or config model.

**Tech Stack:** Python 3.11+, pywebview 6.2.1 / WebView2, vanilla JS (no build step, no framework), pytest, PyInstaller, Inno Setup, AutoHotkey v1.1.

**Spec:** `eve-bookmarks-design.md`

## Global Constraints

- **Windows-only runtime, Linux-testable code.** Every new module must import cleanly on Linux. Platform work sits behind a guard that is "a no-op returning False off Windows", mirroring `ui/chrome.py` (`window-resize-plan.md:130-140`). `tests/test_window.py` and `tests/test_chrome.py` are the precedent.
- **No JavaScript logic that needs testing.** A browser test toolchain is out of scope (`webview-replatform-design.md:545`). JS captures and renders; every judgement happens in Python.
- **Bridge discipline.** Python pushes semantic events via `_push(handler, payload)`; the page calls Python only through `WM.send()`. New handler names MUST be added to `WM.HANDLERS` in `web/app.js:53` or registration throws.
- **`settings.save()` projects onto `DEFAULTS` keys.** Anything undeclared is dropped on every write (`settings.py:31`).
- **19 binds, no global scope.** Every bind requires an active, enabled EVE window.
- **Canonical modifier order is `^` `!` `+` `#`** (Ctrl, Alt, Shift, Win). AHK ignores order; collision detection does not.
- **Subprocess calls use `_NO_WINDOW_KWARGS`** (`stitch.py:27`) and take an injected runner/spawner for testability (`stitch.py:87`).
- **No PATH fallback for the AutoHotkey binary.** A user's AutoHotkey v2 would be handed a v1 script.
- **Home-mode bookmarks number from `.0`**, matching the shipped default `HomeZeroIs0 := 1` (`111unified.ahk:32`). See OPEN QUESTION below.

## Open questions carried from the spec

- **`.0` vs `.1` for home-mode numbering.** The plan hardcodes `.0` (today's shipped default). If the maintainer wants `.1`, Task 11 is the only place that changes.
- **AutoHotkey Authenticode signing is unconfirmed.** Task 21 verifies it; if v1.1 binaries are unsigned, Task 22's signature check cannot mirror the WebView2 one and that becomes a conscious omission.

## The 19 binds

These IDs are the INI keys under `[Keybinds]` and the `settings.json` keys. They are fixed by the existing script (`111unified.ahk:120-140`) minus `Copy` and `Paste`.

```
GrabSig  SetRoot  FormatEnf  ConvertScout
FinH  FinL  FinN  Fin13  Fin1  Fin2  Fin3  Fin4  Fin5  Fin6
FinETag  FinSlash  FinM  FinS  FinC
```

Only `ConvertScout` has a non-blank default: `^+s` (`111unified.ahk:57,140`).

## File Structure

**New Python modules**

| File | Responsibility |
|---|---|
| `obs_youtube_uploader/bookmarks.py` | Pure: keybind notation, validation, collision detection, INI generation, legacy INI import. No I/O, no platform code. |
| `obs_youtube_uploader/hotkeys.py` | Supervisor: spawn/stop/liveness, orphan recovery, command publication, status reading. AutoHotkey confined here. |
| `obs_youtube_uploader/evewindows.py` | Windows-only EVE window enumeration behind a Linux-safe guard. |
| `obs_youtube_uploader/atomicio.py` | `write_atomic(path, text)` — temp-plus-rename. Used by every cross-process writer. |

**New non-Python files**

| File | Responsibility |
|---|---|
| `obs_youtube_uploader/engine/eve_bookmarks.ahk` | The vendored, stripped engine. |
| `packaging/fetch_autohotkey.py` | Pinned fetch of the interpreter. |
| `THIRD-PARTY-NOTICES.md` | GPL written offer against pinned versions. |

**Modified**

| File | Change |
|---|---|
| `obs_youtube_uploader/settings.py` | `eve_bookmarks` key, nested validation, deep-copy fix. |
| `obs_youtube_uploader/paths.py` | `engine_script()`, `engine_exe()`, command/status/pid paths. |
| `obs_youtube_uploader/ui/api.py` | Bookmarks bridge methods. |
| `obs_youtube_uploader/__main__.py` | Engine lifecycle at startup and shutdown. |
| `obs_youtube_uploader/web/index.html` | Nav, `route-bookmarks`, status-bar segment. |
| `obs_youtube_uploader/web/app.js` | Route map, handler names, nav wiring. |
| `obs_youtube_uploader/web/bookmarks.js` | New: the Bookmarks route's rendering and capture. |
| `obs_youtube_uploader/web/style.css` | Nav, route, status segment styling. |
| `packaging/uploader.spec` | Bundle interpreter and script. |
| `.github/workflows/build.yml`, `release.yml` | Collection assertion, signature check. |
| `docs/smoke-checklist.md` | Manual checks for the untestable engine. |

---

## Phase A — Pure logic (Tasks 1-5)

Nothing in this phase touches a process, a file the engine reads, or the UI. All of it runs on Linux.

### Task 1: Keybind notation mapping

**Files:**
- Create: `obs_youtube_uploader/bookmarks.py`
- Test: `tests/test_bookmarks_keys.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `to_ahk(parts: dict) -> dict` returning `{"ahk": str, "display": str, "error": str | None}`. `parts` has keys `ctrl`, `alt`, `shift`, `meta` (bool) and `code` (str, a DOM `KeyboardEvent.code`). On error, `ahk` and `display` are `""`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bookmarks_keys.py
"""The mapping lives in Python because the repo has no way to test JS
(webview-replatform-design.md:545). These tests are what stands in for the
browser tests we deliberately do not have."""
import pytest
from obs_youtube_uploader import bookmarks

NONE = {"ctrl": False, "alt": False, "shift": False, "meta": False}


def parts(code, **mods):
    return {**NONE, **mods, "code": code}


def test_plain_letter():
    assert bookmarks.to_ahk(parts("KeyS")) == {
        "ahk": "s", "display": "S", "error": None}


def test_modifiers_use_canonical_order():
    """AHK ignores modifier order, collision detection does not: ^+s and +^s
    must produce the same string or a duplicate bind goes undetected."""
    got = bookmarks.to_ahk(parts("KeyS", ctrl=True, shift=True))
    assert got["ahk"] == "^+s"
    assert got["display"] == "Ctrl+Shift+S"


def test_all_four_modifiers():
    got = bookmarks.to_ahk(parts("KeyA", ctrl=True, alt=True, shift=True,
                                 meta=True))
    assert got["ahk"] == "^!+#a"
    assert got["display"] == "Ctrl+Alt+Shift+Win+A"


@pytest.mark.parametrize("code,ahk", [
    ("Comma", ","), ("Period", "."), ("Slash", "/"), ("Quote", "'"),
    ("Semicolon", ";"), ("Backquote", "`"), ("Minus", "-"), ("Equal", "="),
    ("BracketLeft", "["), ("BracketRight", "]"), ("Backslash", "\\"),
])
def test_punctuation(code, ahk):
    """The finishers are historically punctuation-bound -- the handler names
    still read DoComma, DoDot, DoQuote, DoSemi -- so these are the common
    case here, not an edge case."""
    assert bookmarks.to_ahk(parts(code))["ahk"] == ahk


@pytest.mark.parametrize("code,ahk", [
    ("Space", "Space"), ("Enter", "Enter"), ("Tab", "Tab"),
    ("Escape", "Esc"), ("Backspace", "Backspace"), ("Delete", "Delete"),
    ("Home", "Home"), ("End", "End"), ("PageUp", "PgUp"),
    ("PageDown", "PgDn"), ("ArrowUp", "Up"), ("ArrowDown", "Down"),
    ("ArrowLeft", "Left"), ("ArrowRight", "Right"), ("F5", "F5"),
    ("Numpad7", "Numpad7"), ("Digit4", "4"),
])
def test_named_keys(code, ahk):
    assert bookmarks.to_ahk(parts(code))["ahk"] == ahk


@pytest.mark.parametrize("code", [
    "ControlLeft", "ControlRight", "AltLeft", "AltRight",
    "ShiftLeft", "ShiftRight", "MetaLeft", "MetaRight",
])
def test_modifier_only_is_rejected(code):
    """Holding Ctrl to reach a combo must not bind Ctrl."""
    got = bookmarks.to_ahk(parts(code, ctrl=True))
    assert got["error"] == "modifier-only"
    assert got["ahk"] == ""


def test_unknown_code_is_rejected():
    """Better a refusal than a string AHK cannot parse in a file it re-reads
    every ten seconds."""
    got = bookmarks.to_ahk(parts("Fn"))
    assert got["error"] == "unmappable"
    assert got["ahk"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bookmarks_keys.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'obs_youtube_uploader.bookmarks'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/bookmarks.py
"""Pure logic for the EVE bookmark helper: keybind notation, validation,
INI generation, and legacy import.

Nothing here does I/O or touches a platform API, which is what lets the
whole module be tested on Linux. The engine that consumes its output cannot
be tested at all, so this is where the coverage has to come from.
"""

# Ctrl, Alt, Shift, Win. AHK accepts any order; a fixed one is what makes
# two spellings of the same combo compare equal in collision detection.
_MODIFIERS = (("ctrl", "^", "Ctrl"), ("alt", "!", "Alt"),
              ("shift", "+", "Shift"), ("meta", "#", "Win"))

_MODIFIER_CODES = frozenset({
    "ControlLeft", "ControlRight", "AltLeft", "AltRight",
    "ShiftLeft", "ShiftRight", "MetaLeft", "MetaRight",
})

# event.code -> AHK key name. event.code is used rather than event.key
# because event.key reports the *produced* character: Shift+Comma arrives as
# "<" and the shifting would have to be reversed to recover the "," AHK
# wants. The cost is a US-layout assumption, mitigated by manual entry.
_NAMED = {
    "Space": "Space", "Enter": "Enter", "Tab": "Tab", "Escape": "Esc",
    "Backspace": "Backspace", "Delete": "Delete", "Insert": "Insert",
    "Home": "Home", "End": "End", "PageUp": "PgUp", "PageDown": "PgDn",
    "ArrowUp": "Up", "ArrowDown": "Down", "ArrowLeft": "Left",
    "ArrowRight": "Right",
    "Comma": ",", "Period": ".", "Slash": "/", "Semicolon": ";",
    "Quote": "'", "Backquote": "`", "Minus": "-", "Equal": "=",
    "BracketLeft": "[", "BracketRight": "]", "Backslash": "\\",
}


def _base_key(code: str) -> str | None:
    if code in _NAMED:
        return _NAMED[code]
    if len(code) == 4 and code.startswith("Key"):
        return code[3].lower()
    if len(code) == 6 and code.startswith("Digit"):
        return code[5]
    if code.startswith("Numpad") and code[6:].isdigit():
        return code
    if code.startswith("F") and code[1:].isdigit() and 1 <= int(code[1:]) <= 24:
        return code
    return None


def to_ahk(parts: dict) -> dict:
    """Translate a captured DOM key event into AHK hotkey notation.

    Returns both the AHK string and a human label, so the page holds no
    mapping table of its own and cannot drift from this one.
    """
    code = parts.get("code") or ""
    if code in _MODIFIER_CODES:
        return {"ahk": "", "display": "", "error": "modifier-only"}
    base = _base_key(code)
    if base is None:
        return {"ahk": "", "display": "", "error": "unmappable"}

    prefix = "".join(sym for key, sym, _ in _MODIFIERS if parts.get(key))
    labels = [label for key, _, label in _MODIFIERS if parts.get(key)]
    display_key = base.upper() if len(base) == 1 and base.isalpha() else base
    return {
        "ahk": prefix + base,
        "display": "+".join(labels + [display_key]),
        "error": None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bookmarks_keys.py -q`
Expected: PASS (all parametrised cases)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/bookmarks.py tests/test_bookmarks_keys.py
git commit -m "feat(bookmarks): map captured key events to AHK notation"
```

---

### Task 2: Bind validation and collision detection

**Files:**
- Modify: `obs_youtube_uploader/bookmarks.py`
- Test: `tests/test_bookmarks_validate.py`

**Interfaces:**
- Consumes: `to_ahk` from Task 1.
- Produces:
  - `BIND_IDS: tuple[str, ...]` — the 19 ids, in display order.
  - `DEFAULT_BINDS: dict[str, str]` — every id mapped to `""` except `ConvertScout` mapped to `"^+s"`.
  - `collisions(binds: dict[str, str]) -> dict[str, list[str]]` — AHK string to the list of bind ids sharing it, for strings bound more than once. Blank binds are never collisions.
  - `parse_ahk(text: str) -> dict` — same return shape as `to_ahk`, for the manual-entry escape hatch.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bookmarks_validate.py
import pytest
from obs_youtube_uploader import bookmarks


def test_there_are_nineteen_binds():
    """21 in the standalone script, minus Copy and Paste which were dropped
    as personal Dvorak conveniences (eve-bookmarks-design.md)."""
    assert len(bookmarks.BIND_IDS) == 19
    assert "Copy" not in bookmarks.BIND_IDS
    assert "Paste" not in bookmarks.BIND_IDS
    assert len(set(bookmarks.BIND_IDS)) == 19


def test_only_convertscout_has_a_default():
    """111unified.ahk:57,140 ships ^+s. Blanking it would silently take a
    working binding away from every existing user."""
    assert bookmarks.DEFAULT_BINDS["ConvertScout"] == "^+s"
    others = {k: v for k, v in bookmarks.DEFAULT_BINDS.items()
              if k != "ConvertScout"}
    assert set(others.values()) == {""}
    assert set(bookmarks.DEFAULT_BINDS) == set(bookmarks.BIND_IDS)


def test_no_collision_when_all_distinct():
    binds = dict(bookmarks.DEFAULT_BINDS, FinH="^h", FinL="^l")
    assert bookmarks.collisions(binds) == {}


def test_collision_is_reported_with_every_owner():
    """RefreshHotkeys registers with UseErrorLevel and silently lets one
    win (111unified.ahk:707-828); catching it here is the improvement."""
    binds = dict(bookmarks.DEFAULT_BINDS, FinH="^h", FinL="^h", FinN="^h")
    assert bookmarks.collisions(binds) == {"^h": ["FinH", "FinL", "FinN"]}


def test_blank_binds_never_collide():
    """Eighteen of nineteen ship blank; treating that as a 17-way collision
    would make the screen unusable on first run."""
    assert bookmarks.collisions(dict(bookmarks.DEFAULT_BINDS)) == {}


def test_parse_ahk_accepts_a_typed_string():
    """The manual escape hatch for non-US layouts, validated by the same
    rules as capture."""
    assert bookmarks.parse_ahk("^+s") == {
        "ahk": "^+s", "display": "Ctrl+Shift+S", "error": None}


def test_parse_ahk_normalises_modifier_order():
    assert bookmarks.parse_ahk("+^s")["ahk"] == "^+s"


@pytest.mark.parametrize("text", ["", "^", "^!+#", "   "])
def test_parse_ahk_rejects_modifier_only(text):
    assert bookmarks.parse_ahk(text)["error"] == "modifier-only"


def test_parse_ahk_rejects_unknown_key():
    assert bookmarks.parse_ahk("^Nope")["error"] == "unmappable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bookmarks_validate.py -q`
Expected: FAIL — `AttributeError: module 'obs_youtube_uploader.bookmarks' has no attribute 'BIND_IDS'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/bookmarks.py`:

```python
# Order is display order in the Bookmarks route, grouped the way the
# standalone GUI grouped them (111unified.ahk:285-305): actions, then
# class finishers, then tag finishers.
BIND_IDS = (
    "GrabSig", "SetRoot", "FormatEnf", "ConvertScout",
    "FinH", "FinL", "FinN", "Fin13",
    "Fin1", "Fin2", "Fin3", "Fin4", "Fin5", "Fin6",
    "FinETag", "FinSlash", "FinM", "FinS", "FinC",
)

# Human labels for the route. Kept beside the ids so the two cannot drift.
BIND_LABELS = {
    "GrabSig": "Grab Sig ID",
    "SetRoot": "Set Root",
    "FormatEnf": "Format Enforcer",
    "ConvertScout": "Convert EvE-Scout Bookmarks",
    "FinH": "Finisher: HS (highsec)",
    "FinL": "Finisher: LS (lowsec)",
    "FinN": "Finisher: NS (nullsec)",
    "Fin13": "Finisher: C13 (shattered)",
    "Fin1": "Finisher: C1", "Fin2": "Finisher: C2",
    "Fin3": "Finisher: C3", "Fin4": "Finisher: C4",
    "Fin5": "Finisher: C5", "Fin6": "Finisher: C6",
    "FinETag": "E Tag (end of life)",
    "FinSlash": "/ Tag (half mass)",
    "FinM": "M Tag (medium hole)",
    "FinS": "S Tag (frig hole)",
    "FinC": "C Tag (critical)",
}

# Only ConvertScout ships bound (111unified.ahk:57,140). The other
# eighteen are blank on purpose: no default global bind means no surprise
# collision on first run.
DEFAULT_BINDS = {bid: ("^+s" if bid == "ConvertScout" else "")
                 for bid in BIND_IDS}

_SYMBOL_TO_KEY = {sym: key for key, sym, _ in _MODIFIERS}


def collisions(binds: dict) -> dict:
    """Map each doubly-bound AHK string to every bind id claiming it.

    Blank means "do not register" to RefreshHotkeys, so blanks are skipped
    rather than treated as a shared value.
    """
    seen: dict[str, list[str]] = {}
    for bid in BIND_IDS:
        value = (binds.get(bid) or "").strip()
        if not value:
            continue
        seen.setdefault(value, []).append(bid)
    return {k: v for k, v in seen.items() if len(v) > 1}


def parse_ahk(text: str) -> dict:
    """Validate a hand-typed AHK hotkey string.

    The escape hatch for non-US layouts, where the event.code table maps to
    the wrong character. Routed through the same rules as capture so the
    two cannot disagree.
    """
    raw = (text or "").strip()
    parts = dict.fromkeys(("ctrl", "alt", "shift", "meta"), False)
    index = 0
    while index < len(raw) and raw[index] in _SYMBOL_TO_KEY:
        parts[_SYMBOL_TO_KEY[raw[index]]] = True
        index += 1
    base = raw[index:]
    if not base:
        return {"ahk": "", "display": "", "error": "modifier-only"}

    # Reverse the mapping table so a typed "," and a captured Comma agree.
    code = None
    for candidate, mapped in _NAMED.items():
        if mapped.lower() == base.lower():
            code = candidate
            break
    if code is None:
        if len(base) == 1 and base.isalpha():
            code = "Key" + base.upper()
        elif len(base) == 1 and base.isdigit():
            code = "Digit" + base
        elif base.lower().startswith("numpad") or (
                base[:1].upper() == "F" and base[1:].isdigit()):
            code = base
        else:
            return {"ahk": "", "display": "", "error": "unmappable"}
    return to_ahk({**parts, "code": code})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bookmarks_validate.py tests/test_bookmarks_keys.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/bookmarks.py tests/test_bookmarks_validate.py
git commit -m "feat(bookmarks): bind ids, defaults, collisions, manual entry"
```

---

### Task 3: Settings schema and the nested-default aliasing fix

**Files:**
- Modify: `obs_youtube_uploader/settings.py`
- Test: `tests/test_settings_eve.py`
- Modify: `tests/test_settings.py` (the DEFAULTS equality assertion)

**Interfaces:**
- Consumes: `BIND_IDS`, `DEFAULT_BINDS` from Task 2.
- Produces: `settings.DEFAULTS["eve_bookmarks"]` with keys `enabled` (bool), `keybinds` (dict), `windows` (dict). Validation guarantees those three keys exist with those types after `load()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings_eve.py
"""The eve_bookmarks values drive a file that registers keyboard hooks, so
load() has to be defensive about them in a way a title string never needed.
"""
import json
import pytest
from obs_youtube_uploader import bookmarks, settings


def test_defaults_carry_every_bind(tmp_path):
    data = settings.load(tmp_path / "missing.json")
    assert data["eve_bookmarks"]["enabled"] is False
    assert data["eve_bookmarks"]["keybinds"] == bookmarks.DEFAULT_BINDS
    assert data["eve_bookmarks"]["windows"] == {}


def test_nested_defaults_are_not_shared_with_the_module_global(tmp_path):
    """load() starts from dict(DEFAULTS) (settings.py:38), a SHALLOW copy.
    Fine while every default is a scalar; with a nested dict the returned
    settings would alias DEFAULTS and the first in-place edit would corrupt
    it for the rest of the process -- silently, and for every later load().
    """
    first = settings.load(tmp_path / "missing.json")
    first["eve_bookmarks"]["keybinds"]["FinH"] = "^h"
    first["eve_bookmarks"]["windows"]["EVE - Pilot"] = True

    second = settings.load(tmp_path / "missing.json")
    assert second["eve_bookmarks"]["keybinds"]["FinH"] == ""
    assert second["eve_bookmarks"]["windows"] == {}
    assert bookmarks.DEFAULT_BINDS["FinH"] == ""


def test_roundtrip(tmp_path):
    path = tmp_path / "s.json"
    data = settings.load(path)
    data["eve_bookmarks"]["enabled"] = True
    data["eve_bookmarks"]["keybinds"]["FinH"] = "^h"
    data["eve_bookmarks"]["windows"]["EVE - Pilot"] = True
    settings.save(data, path)

    loaded = settings.load(path)
    assert loaded["eve_bookmarks"]["enabled"] is True
    assert loaded["eve_bookmarks"]["keybinds"]["FinH"] == "^h"
    assert loaded["eve_bookmarks"]["windows"] == {"EVE - Pilot": True}


@pytest.mark.parametrize("bad", [7, "yes", None, [], {"a": 1}])
def test_bad_enabled_falls_back_to_off(tmp_path, bad):
    """Failing closed matters here: the wrong answer starts a keyboard
    hook the user did not ask for."""
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": {"enabled": bad}}))
    assert settings.load(path)["eve_bookmarks"]["enabled"] is False


def test_unknown_bind_ids_are_dropped_and_missing_ones_defaulted(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": {
        "keybinds": {"FinH": "^h", "Copy": "^c", "Nonsense": "^x"}}}))
    binds = settings.load(path)["eve_bookmarks"]["keybinds"]
    assert binds["FinH"] == "^h"
    assert "Copy" not in binds
    assert "Nonsense" not in binds
    assert binds["ConvertScout"] == "^+s"
    assert set(binds) == set(bookmarks.BIND_IDS)


@pytest.mark.parametrize("bad", [7, None, [], {"x": 1}])
def test_non_string_bind_value_falls_back(tmp_path, bad):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": {"keybinds": {"FinH": bad}}}))
    assert settings.load(path)["eve_bookmarks"]["keybinds"]["FinH"] == ""


def test_window_map_coerces_to_bool_and_drops_non_string_keys(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": {
        "windows": {"EVE - Pilot": 1, "EVE - Alt": 0}}}))
    assert settings.load(path)["eve_bookmarks"]["windows"] == {
        "EVE - Pilot": True, "EVE - Alt": False}


@pytest.mark.parametrize("bad", [7, "x", None, []])
def test_whole_section_of_wrong_type_falls_back(tmp_path, bad):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": bad}))
    section = settings.load(path)["eve_bookmarks"]
    assert section["enabled"] is False
    assert section["keybinds"] == bookmarks.DEFAULT_BINDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_eve.py -q`
Expected: FAIL — `KeyError: 'eve_bookmarks'`

- [ ] **Step 3: Write minimal implementation**

In `obs_youtube_uploader/settings.py`, add the import and the default:

```python
from . import bookmarks, paths
```

Add to `DEFAULTS`, after `channel_title`:

```python
    # Nested, unlike every other key. save() projects onto DEFAULTS keys, so
    # this whole section travels as one value; load() rebuilds the inner
    # dicts rather than copying them, because dict(DEFAULTS) below is
    # shallow and would otherwise hand callers the module globals.
    "eve_bookmarks": {
        # Off by default: enabling installs a global keyboard hook, so an
        # upgrading user has to ask for it rather than be given it.
        "enabled": False,
        "keybinds": dict(bookmarks.DEFAULT_BINDS),
        "windows": {},
    },
```

Add the validator, and call it from `load()` just before `return data`:

```python
def _eve_defaults() -> dict:
    """Fresh nested structure every call. Never return the module global."""
    return {"enabled": False,
            "keybinds": dict(bookmarks.DEFAULT_BINDS),
            "windows": {}}


def validated_eve(raw) -> dict:
    section = _eve_defaults()
    if not isinstance(raw, dict):
        return section

    # `is True` rather than truthiness: a stray 1 or "yes" from a
    # hand-edited file must not start a keyboard hook.
    section["enabled"] = raw.get("enabled") is True

    binds = raw.get("keybinds")
    if isinstance(binds, dict):
        for bid in bookmarks.BIND_IDS:
            value = binds.get(bid)
            if isinstance(value, str):
                section["keybinds"][bid] = value.strip()
    # Ids not in BIND_IDS are dropped by construction: the loop is over the
    # known ids, so a stale "Copy" from a pre-integration file cannot
    # survive into the generated INI.

    windows = raw.get("windows")
    if isinstance(windows, dict):
        section["windows"] = {k: bool(v) for k, v in windows.items()
                              if isinstance(k, str)}
    return section
```

In `load()`, immediately before `return data`:

```python
    data["eve_bookmarks"] = validated_eve(raw.get("eve_bookmarks"))
    return data
```

There is one more edit: `load()` returns early when the file is missing or unreadable, and that path must also get a fresh nested section. Change the two early `return data` statements near the top of `load()` to go through a helper:

```python
def _fresh_defaults() -> dict:
    """dict(DEFAULTS) is shallow, so the nested section is rebuilt."""
    data = dict(DEFAULTS)
    data["eve_bookmarks"] = _eve_defaults()
    return data
```

and replace every `data = dict(DEFAULTS)` / bare `return data` early exit in `load()` with `_fresh_defaults()`.

- [ ] **Step 4: Update the existing DEFAULTS assertion**

`tests/test_settings.py::test_defaults_are_the_documented_values` asserts an exact dict and will now fail. Add the new key to it:

```python
        "channel_title": "",
        "eve_bookmarks": {
            "enabled": False,
            "keybinds": bookmarks.DEFAULT_BINDS,
            "windows": {},
        },
    }
```

with `from obs_youtube_uploader import bookmarks, settings` at the top.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS, 607 existing plus the new cases

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/settings.py tests/test_settings_eve.py tests/test_settings.py
git commit -m "feat(settings): eve_bookmarks section with non-aliasing defaults"
```

---

### Task 4: INI generation

**Files:**
- Modify: `obs_youtube_uploader/bookmarks.py`
- Test: `tests/test_bookmarks_ini.py`

**Interfaces:**
- Consumes: `BIND_IDS` (Task 2), the `eve_bookmarks` section shape (Task 3).
- Produces: `generate_ini(section: dict) -> str` — the complete INI text the engine reads, with a trailing newline and CRLF line endings.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bookmarks_ini.py
"""The INI is a generated artifact: Wingman writes it, the engine only ever
reads it. These tests pin the exact bytes because the consumer is an AHK
script we cannot test."""
from obs_youtube_uploader import bookmarks


def section(**over):
    base = {"enabled": True, "keybinds": dict(bookmarks.DEFAULT_BINDS),
            "windows": {}}
    base.update(over)
    return base


def test_uses_crlf_and_ends_with_a_newline():
    """GetPrivateProfileString is a Windows API reading a Windows file."""
    text = bookmarks.generate_ini(section())
    assert "\r\n" in text
    assert text.endswith("\r\n")
    assert "\n" not in text.replace("\r\n", "")


def test_every_bind_is_written_even_when_blank():
    """Blank means "do not register" to RefreshHotkeys (111unified.ahk:719).
    Omitting the key entirely would leave IniRead returning its default
    instead, which for ConvertScout is ^+s -- so a deliberately cleared
    bind would come back."""
    text = bookmarks.generate_ini(section())
    for bid in bookmarks.BIND_IDS:
        assert f"{bid}=" in text
    assert "ConvertScout=^+s\r\n" in text
    assert "FinH=\r\n" in text


def test_enabled_windows_are_written_as_one_and_zero():
    text = bookmarks.generate_ini(section(
        windows={"EVE - Pilot": True, "EVE - Alt": False}))
    assert "[Enabled]\r\n" in text
    assert "EVE - Pilot=1\r\n" in text
    assert "EVE - Alt=0\r\n" in text


def test_semicolon_bind_survives():
    """Windows INI treats ; as a comment only at line start, and the value
    reaches AHK through IniRead into a variable so it is never parsed as
    script text. Pinned by a test rather than by confidence."""
    text = bookmarks.generate_ini(section(
        keybinds=dict(bookmarks.DEFAULT_BINDS, FinH="^;")))
    assert "FinH=^;\r\n" in text


def test_newline_in_a_window_title_cannot_forge_a_line():
    """Window titles come from the OS, but a hostile or malformed one must
    not be able to inject an extra INI entry. Asserted line-anchored: the
    sanitised title becomes "EVE - BadFinH=1", which *contains* "FinH=1"
    as a substring without being a forged line."""
    text = bookmarks.generate_ini(section(
        windows={"EVE - Bad\r\nFinH": True}))
    lines = text.split("\r\n")
    assert "FinH=1" not in lines
    assert "EVE - BadFinH=1" in lines


def test_no_mode_or_preface_settings():
    """Protean/v21, HomeZeroIs0 and the return preface are gone; the engine
    hardcodes their surviving behaviour."""
    text = bookmarks.generate_ini(section())
    for gone in ("Mode", "HomeZeroIs0", "PrefaceReturn", "ReturnPreface"):
        assert gone not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bookmarks_ini.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'generate_ini'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/bookmarks.py`:

```python
_CRLF = "\r\n"


def generate_ini(section: dict) -> str:
    """Render the engine's INI from a validated eve_bookmarks section.

    Pure: the caller writes it, atomically. Every known bind is emitted even
    when blank, because a missing key makes IniRead fall back to its
    compiled-in default -- which would resurrect ConvertScout's ^+s after a
    user deliberately cleared it.
    """
    binds = section.get("keybinds") or {}
    windows = section.get("windows") or {}

    lines = ["[Keybinds]"]
    for bid in BIND_IDS:
        value = binds.get(bid) or ""
        lines.append(f"{bid}={sanitise(value)}")

    lines.append("")
    lines.append("[Enabled]")
    for title, on in windows.items():
        clean = sanitise(title)
        if not clean:
            continue
        lines.append(f"{clean}={1 if on else 0}")

    return _CRLF.join(lines) + _CRLF


def sanitise(value: str) -> str:
    """Strip anything that could forge an INI line.

    Public because hotkeys.send_command needs it too: the Set Root argument
    is free text the user typed and lands in a file the engine parses.
    Window titles come from the OS and bind values from user input; neither
    is trusted to contain a line break.
    """
    return "".join(ch for ch in str(value) if ch not in "\r\n").strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bookmarks_ini.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/bookmarks.py tests/test_bookmarks_ini.py
git commit -m "feat(bookmarks): generate the engine INI from settings"
```

---

### Task 5: Legacy INI import

**Files:**
- Modify: `obs_youtube_uploader/bookmarks.py`
- Test: `tests/test_bookmarks_import.py`

**Interfaces:**
- Consumes: `BIND_IDS`, `DEFAULT_BINDS`.
- Produces: `import_legacy_ini(text: str) -> dict` returning `{"section": dict, "discarded": list[str], "notes": list[str]}`. `section` is a valid `eve_bookmarks` section; `discarded` names settings that no longer exist; `notes` holds user-facing sentences about behaviour changes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bookmarks_import.py
"""Retiring the standalone script without importing its INI would discard
every existing user's configuration, which -- since Wingman is meant to
REPLACE the script -- is everyone, not an edge case."""
from obs_youtube_uploader import bookmarks

LEGACY = (
    "[Settings]\r\n"
    "HomeZeroIs0=1\r\n"
    "Mode=2\r\n"
    "PrefaceReturn=1\r\n"
    "ReturnPreface=!\r\n"
    "[Keybinds]\r\n"
    "Copy=^c\r\n"
    "Paste=^v\r\n"
    "GrabSig=q\r\n"
    "SetRoot=`;\r\n"
    "FinH=y\r\n"
    "ConvertScout=^+s\r\n"
    "[Enabled]\r\n"
    "EVE - Pilot=1\r\n"
    "EVE - Alt=0\r\n"
)


def test_binds_that_still_exist_are_carried_over():
    got = bookmarks.import_legacy_ini(LEGACY)
    assert got["section"]["keybinds"]["GrabSig"] == "q"
    assert got["section"]["keybinds"]["FinH"] == "y"
    assert got["section"]["keybinds"]["ConvertScout"] == "^+s"


def test_window_enablement_is_carried_over():
    got = bookmarks.import_legacy_ini(LEGACY)
    assert got["section"]["windows"] == {"EVE - Pilot": True,
                                         "EVE - Alt": False}


def test_removed_binds_are_reported_not_silently_dropped():
    """A user who loses a working key should learn it here rather than by
    pressing it and getting nothing."""
    got = bookmarks.import_legacy_ini(LEGACY)
    assert "Copy" not in got["section"]["keybinds"]
    assert "Paste" not in got["section"]["keybinds"]
    assert any("Copy" in d for d in got["discarded"])
    assert any("Paste" in d for d in got["discarded"])


def test_removed_settings_are_reported():
    got = bookmarks.import_legacy_ini(LEGACY)
    joined = " ".join(got["discarded"])
    assert "Mode" in joined
    assert "ReturnPreface" in joined


def test_home_numbering_change_is_described_in_user_terms():
    """HomeZeroIs0 is NOT Protean-specific: FireRootFinisher applies it with
    no reference to CurrentMode (111unified.ahk:870,886,893). A user who had
    it off gets renumbered bookmarks, so this cannot read as "no longer
    applies"."""
    off = LEGACY.replace("HomeZeroIs0=1", "HomeZeroIs0=0")
    got = bookmarks.import_legacy_ini(off)
    note = " ".join(got["notes"])
    assert ".0" in note and ".1" in note


def test_no_note_when_home_numbering_already_matched():
    got = bookmarks.import_legacy_ini(LEGACY)
    assert not any(".0" in n and ".1" in n for n in got["notes"])


def test_import_never_enables_the_engine():
    """Importing settings is not consent to start a keyboard hook."""
    assert bookmarks.import_legacy_ini(LEGACY)["section"]["enabled"] is False


def test_garbage_yields_defaults_rather_than_raising():
    got = bookmarks.import_legacy_ini("not an ini at all\x00\x01")
    assert got["section"]["keybinds"] == bookmarks.DEFAULT_BINDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bookmarks_import.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'import_legacy_ini'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/bookmarks.py`:

```python
# Settings the standalone script carried that the engine no longer has.
# Named individually so import can tell the user what it dropped.
_REMOVED_SETTINGS = ("Mode", "PrefaceReturn", "ReturnPreface")
_REMOVED_BINDS = ("Copy", "Paste")


def _parse_ini(text: str) -> dict:
    """Minimal INI reader. configparser is not used: the legacy file has
    section keys (window titles) containing '=' and characters configparser
    mangles, and we only need two flat sections."""
    out: dict[str, dict[str, str]] = {}
    current = None
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            out.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[current][key.strip()] = value.strip()
    return out


def import_legacy_ini(text: str) -> dict:
    """Translate a standalone eve_bookmark_helper.ini into a settings section.

    Returns what was imported, what was dropped, and any behaviour change
    the user needs to be told about in their own terms.
    """
    parsed = _parse_ini(text)
    legacy_binds = parsed.get("Keybinds", {})
    legacy_settings = parsed.get("Settings", {})
    legacy_windows = parsed.get("Enabled", {})

    section = {"enabled": False,
               "keybinds": dict(DEFAULT_BINDS),
               "windows": {}}
    for bid in BIND_IDS:
        if bid in legacy_binds:
            section["keybinds"][bid] = sanitise(legacy_binds[bid])
    section["windows"] = {title: value.strip() == "1"
                          for title, value in legacy_windows.items()
                          if sanitise(title)}

    discarded = [f"{name} (setting)" for name in _REMOVED_SETTINGS
                 if name in legacy_settings]
    discarded += [f"{name} (keybind)" for name in _REMOVED_BINDS
                  if legacy_binds.get(name)]

    notes = []
    # HomeZeroIs0 defaults to 1 (111unified.ahk:32) and the engine now
    # hardcodes that. Only a user who turned it OFF sees a change.
    if legacy_settings.get("HomeZeroIs0", "1").strip() == "0":
        notes.append(
            "Your home-mode bookmarks used to start at .1; they will now "
            "start at .0. That option no longer exists.")
    return {"section": section, "discarded": discarded, "notes": notes}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bookmarks_import.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite and commit**

```bash
pytest -q
git add obs_youtube_uploader/bookmarks.py tests/test_bookmarks_import.py
git commit -m "feat(bookmarks): import a standalone helper INI"
```

---

## Phase B — Supervisor (Tasks 6-11)

Everything here is Windows-only at runtime and Linux-testable by construction: no module imports a Windows API at module scope, and the process is reached only through an injected spawner.

### Task 6: Atomic publication helper

**Files:**
- Create: `obs_youtube_uploader/atomicio.py`
- Test: `tests/test_atomicio.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `write_atomic(path: Path, text: str, encoding: str = "utf-8") -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atomicio.py
"""One writer per file prevents conflicting WRITES. It does nothing about a
reader observing a half-written file, and every one of these files is polled
by another process on a 2s or 10s timer."""
from pathlib import Path
import pytest
from obs_youtube_uploader import atomicio


def test_writes_the_content(tmp_path):
    target = tmp_path / "out.json"
    atomicio.write_atomic(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'


def test_overwrites_existing(tmp_path):
    target = tmp_path / "out.json"
    target.write_text("old")
    atomicio.write_atomic(target, "new")
    assert target.read_text() == "new"


def test_creates_parent_directories(tmp_path):
    target = tmp_path / "nested" / "deep" / "out.json"
    atomicio.write_atomic(target, "x")
    assert target.read_text() == "x"


def test_no_temp_files_are_left_behind(tmp_path):
    target = tmp_path / "out.json"
    atomicio.write_atomic(target, "x")
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_a_failed_write_leaves_the_old_content_intact(tmp_path, monkeypatch):
    """The point of temp-plus-rename: a reader either sees the whole old
    file or the whole new one, never a truncated file."""
    target = tmp_path / "out.json"
    target.write_text("good")

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(atomicio.os, "replace", boom)
    with pytest.raises(OSError):
        atomicio.write_atomic(target, "partial")
    assert target.read_text() == "good"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_temp_file_is_on_the_same_directory(tmp_path, monkeypatch):
    """os.replace is only atomic within a filesystem. A temp in /tmp would
    silently degrade to a copy across a volume boundary."""
    seen = {}
    real = atomicio.tempfile.mkstemp

    def spy(**kwargs):
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(atomicio.tempfile, "mkstemp", spy)
    atomicio.write_atomic(tmp_path / "out.json", "x")
    assert Path(seen["dir"]) == tmp_path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_atomicio.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'obs_youtube_uploader.atomicio'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/atomicio.py
"""Publish a file so a concurrent reader never sees it half-written.

Every file crossing the Wingman/engine boundary goes through here. Single
writer ownership settles who may write; it says nothing about what a reader
polling on a timer observes mid-write, and both sides poll.
"""
import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write *text* to *path* by rename, leaving the old file intact on error.

    The temporary file is created in the destination directory on purpose:
    os.replace is only atomic within one filesystem, so a temp elsewhere
    would degrade to a non-atomic copy across a volume boundary.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent),
                                        prefix=path.name + ".",
                                        suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding=encoding, newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Leave no debris: a stray .tmp beside the real file is confusing
        # and, in state_dir, indistinguishable from state that matters.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
```

Note `newline=""` — `generate_ini` already emits CRLF and Python must not translate it again.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_atomicio.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/atomicio.py tests/test_atomicio.py
git commit -m "feat(atomicio): publish files by temp-plus-rename"
```

---

### Task 7: Engine paths

**Files:**
- Modify: `obs_youtube_uploader/paths.py`
- Test: `tests/test_paths_engine.py`

**Interfaces:**
- Consumes: existing `state_dir()`, `bundle_dir()`.
- Produces: `engine_ini_file()`, `engine_status_file()`, `engine_command_file()`, `engine_pid_file()` (all `-> Path` under `state_dir()`), `engine_script() -> Path | None`, `engine_exe() -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paths_engine.py
"""resolve_binary() falls back to PATH, which is right for ffmpeg and wrong
here: a user with AutoHotkey v2 installed would have their v2 interpreter
handed a v1 script and fail with parse errors that look like our bug."""
from pathlib import Path
from obs_youtube_uploader import paths


def test_state_files_live_together(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)
    assert paths.engine_ini_file() == tmp_path / "eve_bookmark_helper.ini"
    assert paths.engine_status_file() == tmp_path / "eve_status.json"
    assert paths.engine_command_file() == tmp_path / "eve_command.ini"
    assert paths.engine_pid_file() == tmp_path / "eve_engine.pid"


def test_engine_exe_never_falls_back_to_path(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(paths.shutil, "which",
                        lambda _n: "C:/Program Files/AutoHotkey/v2/AutoHotkey.exe")
    assert paths.engine_exe() is None


def test_engine_exe_finds_the_bundled_binary(monkeypatch, tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "AutoHotkeyU64.exe").write_text("")
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    assert paths.engine_exe() == str(tmp_path / "bin" / "AutoHotkeyU64.exe")


def test_engine_exe_finds_the_source_checkout_copy(monkeypatch, tmp_path):
    """packaging/fetch_autohotkey.py writes into packaging/bin, not <repo>/bin,
    exactly as fetch_ffmpeg.py does (paths.py:63-79)."""
    target = tmp_path / "packaging" / "bin"
    target.mkdir(parents=True)
    (target / "AutoHotkeyU64.exe").write_text("")
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    monkeypatch.delattr(paths.sys, "_MEIPASS", raising=False)
    assert paths.engine_exe() == str(target / "AutoHotkeyU64.exe")


def test_engine_script_prefers_the_frozen_location(monkeypatch, tmp_path):
    engine = tmp_path / "engine"
    engine.mkdir()
    (engine / "eve_bookmarks.ahk").write_text("")
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    assert paths.engine_script() == engine / "eve_bookmarks.ahk"


def test_engine_script_returns_none_when_absent(monkeypatch, tmp_path):
    """Callers treat a missing engine as "reinstall", the same policy
    resolve_binary() and icon_file() use."""
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "_package_dir", lambda: tmp_path / "nope")
    assert paths.engine_script() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_paths_engine.py -q`
Expected: FAIL — `AttributeError: module 'obs_youtube_uploader.paths' has no attribute 'engine_ini_file'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/paths.py`:

```python
def engine_ini_file() -> Path:
    """Config the engine reads. Generated by Wingman, never hand-edited.

    The name matches the standalone script's IniFile (111unified.ahk:71),
    which is relative -- so spawning the engine with cwd=state_dir() is what
    makes it resolve here with no edit to the script.
    """
    return state_dir() / "eve_bookmark_helper.ini"


def engine_status_file() -> Path:
    """Runtime state the engine publishes. Wingman never writes this."""
    return state_dir() / "eve_status.json"


def engine_command_file() -> Path:
    """Operations Wingman publishes. The engine never writes this.

    INI rather than JSON, unlike the status file, because the direction of
    travel decides the format: AHK reads INI natively via IniRead and has no
    JSON parser, while it only ever *writes* the status file, which string
    concatenation handles fine. Each side does its easy direction.
    """
    return state_dir() / "eve_command.ini"


def engine_pid_file() -> Path:
    """PID plus run token of the last spawned engine, for orphan recovery."""
    return state_dir() / "eve_engine.pid"


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def engine_script() -> Path | None:
    """Locate the vendored .ahk, or None if it is not present.

    Mirrors icon_file()'s two-case handling of bundle_dir(): a frozen build
    collects the script via uploader.spec's datas entry, a source checkout
    has it inside the package.
    """
    frozen = bundle_dir() / "engine" / "eve_bookmarks.ahk"
    if frozen.exists():
        return frozen
    source = _package_dir() / "engine" / "eve_bookmarks.ahk"
    if source.exists():
        return source
    return None


def engine_exe() -> str | None:
    """Locate the bundled AutoHotkey interpreter. Bundled only.

    Deliberately NOT resolve_binary(): its shutil.which() fallback is
    correct for ffmpeg and dangerous here. AutoHotkey v2 is a different,
    incompatible language, and a v2 interpreter on PATH handed our v1
    script fails with parse errors that read like a bug in the script.
    Better to report a missing engine and have the user reinstall.
    """
    name = "AutoHotkeyU64.exe"
    candidate = bundle_dir() / "bin" / name
    if candidate.exists():
        return str(candidate)
    if not hasattr(sys, "_MEIPASS"):
        candidate = bundle_dir() / "packaging" / "bin" / name
        if candidate.exists():
            return str(candidate)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_paths_engine.py tests/test_paths.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/paths.py tests/test_paths_engine.py
git commit -m "feat(paths): locate the engine binary, script and state files"
```

---

### Task 8: HotkeyEngine start, stop and liveness

**Files:**
- Create: `obs_youtube_uploader/hotkeys.py`
- Test: `tests/test_hotkeys_lifecycle.py`

**Interfaces:**
- Consumes: `bookmarks.generate_ini` (Task 4), `atomicio.write_atomic` (Task 6), `paths.engine_*` (Task 7).
- Produces:
  - `class HotkeyEngine(exe, script, state_dir, *, spawner=subprocess.Popen, token_factory=...)`
  - `.apply(section: dict) -> None` — regenerate the INI.
  - `.start() -> bool`, `.stop(timeout: float = 5.0) -> None`, `.is_running() -> bool`
  - `.last_error: str | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkeys_lifecycle.py
"""The supervisor is Windows-only at runtime but must import and be tested
on Linux, the same way ui/chrome.py is (window-resize-plan.md:130-140)."""
import subprocess
import pytest
from obs_youtube_uploader import bookmarks, hotkeys


class FakeProc:
    def __init__(self, pid=4321):
        self.pid = pid
        self._alive = True
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        self._alive = False

    def kill(self):
        self.killed = True
        self._alive = False

    def wait(self, timeout=None):
        if self._alive:
            raise subprocess.TimeoutExpired("ahk", timeout)
        return 0


class FakeSpawner:
    def __init__(self):
        self.calls = []
        self.proc = FakeProc()

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.proc


def section(**over):
    base = {"enabled": True, "keybinds": dict(bookmarks.DEFAULT_BINDS),
            "windows": {}}
    base.update(over)
    return base


def engine(tmp_path, spawner):
    (tmp_path / "ahk.exe").write_text("")
    (tmp_path / "e.ahk").write_text("")
    return hotkeys.HotkeyEngine(str(tmp_path / "ahk.exe"),
                                tmp_path / "e.ahk", tmp_path,
                                spawner=spawner,
                                token_factory=lambda: "TOKEN123")


def test_apply_writes_the_ini(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section(keybinds=dict(bookmarks.DEFAULT_BINDS, FinH="^h")))
    text = (tmp_path / "eve_bookmark_helper.ini").read_text()
    assert "FinH=^h" in text


def test_start_spawns_interpreter_script_and_token(tmp_path):
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    assert eng.start() is True
    argv, kwargs = spawner.calls[0]
    assert argv[0] == str(tmp_path / "ahk.exe")
    assert argv[1] == str(tmp_path / "e.ahk")
    assert "TOKEN123" in argv


def test_start_runs_in_state_dir(tmp_path):
    """The script's IniFile is relative (111unified.ahk:71); cwd is what
    makes it resolve to our generated file rather than beside the exe."""
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    assert spawner.calls[0][1]["cwd"] == str(tmp_path)


def test_start_suppresses_a_console_window_on_windows(tmp_path, monkeypatch):
    """console=False build: without this a console flashes on every spawn
    (stitch.py:22-27)."""
    monkeypatch.setattr(hotkeys.sys, "platform", "win32")
    monkeypatch.setattr(hotkeys, "_NO_WINDOW_KWARGS", {"creationflags": 8})
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    assert spawner.calls[0][1]["creationflags"] == 8


def test_start_records_pid_and_token(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    import json
    record = json.loads((tmp_path / "eve_engine.pid").read_text())
    assert record == {"pid": 4321, "token": "TOKEN123"}


def test_start_fails_cleanly_when_the_binary_is_missing(tmp_path):
    eng = hotkeys.HotkeyEngine(None, tmp_path / "e.ahk", tmp_path,
                               spawner=FakeSpawner())
    assert eng.start() is False
    assert eng.is_running() is False
    assert "engine" in (eng.last_error or "").lower()


def test_start_fails_cleanly_when_the_script_is_missing(tmp_path):
    (tmp_path / "ahk.exe").write_text("")
    eng = hotkeys.HotkeyEngine(str(tmp_path / "ahk.exe"), None, tmp_path,
                               spawner=FakeSpawner())
    assert eng.start() is False
    assert "engine" in (eng.last_error or "").lower()


def test_start_is_idempotent(tmp_path):
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    eng.start()
    assert len(spawner.calls) == 1


def test_stop_terminates_and_clears_the_pid_record(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    eng.stop()
    assert eng.is_running() is False
    assert not (tmp_path / "eve_engine.pid").exists()


def test_stop_escalates_to_kill_when_terminate_is_ignored(tmp_path):
    """A hung engine still holds a keyboard hook; leaving it is worse than
    killing it."""
    spawner = FakeSpawner()

    class Stubborn(FakeProc):
        def terminate(self):
            self.terminated = True   # ignores it

    spawner.proc = Stubborn()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    eng.stop(timeout=0.01)
    assert spawner.proc.killed is True


def test_stop_is_safe_when_never_started(tmp_path):
    engine(tmp_path, FakeSpawner()).stop()


def test_is_running_reflects_process_death(tmp_path):
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    assert eng.is_running() is True
    spawner.proc._alive = False
    assert eng.is_running() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hotkeys_lifecycle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'obs_youtube_uploader.hotkeys'`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/hotkeys.py
"""Supervise the EVE bookmark hotkey engine.

AutoHotkey is confined to this module: nothing in its public interface
names it. That is deliberate -- the naming logic may later be reimplemented
in Python, and this boundary is what makes that a swap rather than a
rewrite of the integration.

Windows-only at runtime, importable and testable everywhere: the process is
reached only through an injected spawner.
"""
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path

from . import atomicio, bookmarks, paths

logger = logging.getLogger(__name__)

# CREATE_NO_WINDOW doesn't exist off Windows, and the tests inject a fake
# spawner -- same shape as stitch.py:27 and library.py:19.
_NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if sys.platform == "win32" else {}
)

_MISSING = ("The bookmark engine is missing from this installation. "
            "Reinstall FlyGD Wingman to restore it.")


class HotkeyEngine:
    """Own the engine process and the files it reads."""

    def __init__(self, exe, script, state_dir, *,
                 spawner=subprocess.Popen,
                 token_factory=lambda: uuid.uuid4().hex):
        self._exe = exe
        self._script = Path(script) if script else None
        self._state_dir = Path(state_dir)
        self._spawner = spawner
        self._token_factory = token_factory
        self._proc = None
        self._token = None
        self.last_error: str | None = None

    # -- config ------------------------------------------------------
    def apply(self, section: dict) -> None:
        """Regenerate the INI the engine reads.

        The engine picks this up on its own 10s timer, so there is no need
        to restart it and lose in-flight state (root system, used slots).
        """
        atomicio.write_atomic(self._ini_path(),
                              bookmarks.generate_ini(section))

    # -- lifecycle ---------------------------------------------------
    def start(self) -> bool:
        if self.is_running():
            return True
        if not self._exe or not self._script or not self._script.exists():
            self.last_error = _MISSING
            logger.error("Engine not started: exe=%r script=%r",
                         self._exe, self._script)
            return False

        self._token = self._token_factory()
        argv = [str(self._exe), str(self._script), "/token", self._token]
        try:
            self._proc = self._spawner(
                argv, cwd=str(self._state_dir), **_NO_WINDOW_KWARGS)
        except OSError as exc:
            self.last_error = f"The bookmark engine could not start: {exc}"
            logger.exception("Engine spawn failed")
            self._proc = None
            return False

        atomicio.write_atomic(
            self._pid_path(),
            json.dumps({"pid": self._proc.pid, "token": self._token}))
        self.last_error = None
        return True

    def stop(self, timeout: float = 5.0) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # A hung engine still holds a keyboard hook. Killing it is
                # the lesser harm.
                logger.warning("Engine ignored terminate; killing it.")
                proc.kill()
        self._clear_pid_record()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -- paths -------------------------------------------------------
    def _ini_path(self) -> Path:
        return self._state_dir / paths.engine_ini_file().name

    def _pid_path(self) -> Path:
        return self._state_dir / paths.engine_pid_file().name

    def _clear_pid_record(self) -> None:
        try:
            self._pid_path().unlink()
        except OSError:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hotkeys_lifecycle.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/hotkeys.py tests/test_hotkeys_lifecycle.py
git commit -m "feat(hotkeys): supervise the engine process"
```

---

### Task 9: Orphan recovery with identity verification

**Files:**
- Modify: `obs_youtube_uploader/hotkeys.py`
- Create: `obs_youtube_uploader/procid.py`
- Test: `tests/test_hotkeys_orphan.py`

**Interfaces:**
- Consumes: the pid record written by Task 8.
- Produces:
  - `procid.describe(pid: int) -> dict | None` — `{"image": str, "cmdline": str}` or `None` if no such process. Returns `None` off Windows.
  - `HotkeyEngine.recover_orphan() -> bool` — True if something was terminated. Called from `start()` before spawning.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkeys_orphan.py
"""If Wingman crashes, the engine survives holding a global keyboard hook
with no UI left to disable it. Recovery is the backstop -- but it kills a
process, so identity has to be right."""
import json
from obs_youtube_uploader import hotkeys
from tests.test_hotkeys_lifecycle import FakeSpawner, engine, section


def write_record(tmp_path, pid=999, token="TOKEN123"):
    (tmp_path / "eve_engine.pid").write_text(
        json.dumps({"pid": pid, "token": token}))


def test_kills_a_matching_orphan(tmp_path, monkeypatch):
    write_record(tmp_path)
    killed = []
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"C:\app\bin\AutoHotkeyU64.exe",
        "cmdline": r'AutoHotkeyU64.exe eve_bookmarks.ahk /token TOKEN123'})
    monkeypatch.setattr(hotkeys.procid, "terminate", lambda pid: killed.append(pid))
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is True
    assert killed == [999]


def test_does_not_kill_a_reused_pid(tmp_path, monkeypatch):
    """Windows reuses PIDs, and this path runs precisely after an unclean
    shutdown -- the recorded PID may since belong to anything."""
    write_record(tmp_path)
    killed = []
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"C:\Windows\explorer.exe", "cmdline": "explorer.exe"})
    monkeypatch.setattr(hotkeys.procid, "terminate", lambda pid: killed.append(pid))
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False
    assert killed == []


def test_does_not_kill_the_interpreter_running_another_script(tmp_path, monkeypatch):
    """The image path alone is not identity: AutoHotkey is a general
    interpreter and the user may be running their own scripts."""
    write_record(tmp_path)
    killed = []
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"C:\app\bin\AutoHotkeyU64.exe",
        "cmdline": r"AutoHotkeyU64.exe someone-elses.ahk"})
    monkeypatch.setattr(hotkeys.procid, "terminate", lambda pid: killed.append(pid))
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False
    assert killed == []


def test_stale_record_for_a_dead_pid_is_discarded(tmp_path, monkeypatch):
    write_record(tmp_path)
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: None)
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False
    assert not (tmp_path / "eve_engine.pid").exists()


def test_corrupt_record_is_survivable(tmp_path, monkeypatch):
    (tmp_path / "eve_engine.pid").write_text("{ not json")
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: None)
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False


def test_no_record_is_not_an_error(tmp_path):
    assert engine(tmp_path, FakeSpawner()).recover_orphan() is False


def test_start_recovers_before_spawning(tmp_path, monkeypatch):
    write_record(tmp_path)
    order = []
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"bin\AutoHotkeyU64.exe",
        "cmdline": "AutoHotkeyU64.exe eve_bookmarks.ahk /token TOKEN123"})
    monkeypatch.setattr(hotkeys.procid, "terminate",
                        lambda pid: order.append("kill"))
    spawner = FakeSpawner()

    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    order.append("spawn")
    assert order == ["kill", "spawn"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hotkeys_orphan.py -q`
Expected: FAIL — `AttributeError: module 'obs_youtube_uploader.hotkeys' has no attribute 'procid'`

- [ ] **Step 3: Write the process-identity module**

```python
# obs_youtube_uploader/procid.py
"""Identify and terminate a process by PID, on Windows.

Split out of hotkeys.py for the reason ui/chrome.py is split out of
ui/window.py (window-resize-plan.md:130-140): this is the only module that
touches Win32, so hotkeys.py stays importable and testable on Linux.

Every function is a no-op returning None/False off Windows.
"""
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

_NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if sys.platform == "win32" else {}
)


def describe(pid: int, runner=subprocess.run) -> dict | None:
    """Return {"image", "cmdline"} for *pid*, or None if it is not running.

    Uses WMIC-style query via PowerShell rather than adding psutil: the
    dependency list is deliberately short, and this is one call on one
    code path.
    """
    if sys.platform != "win32":
        return None
    script = (
        f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}';"
        "if ($p) { $p.ExecutablePath; $p.CommandLine }"
    )
    try:
        done = runner(["powershell", "-NoProfile", "-Command", script],
                      capture_output=True, text=True, timeout=10,
                      **_NO_WINDOW_KWARGS)
    except (OSError, subprocess.SubprocessError):
        logger.exception("Could not query process %s", pid)
        return None
    lines = [ln.strip() for ln in (done.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return None
    return {"image": lines[0], "cmdline": lines[-1]}


def terminate(pid: int, runner=subprocess.run) -> bool:
    if sys.platform != "win32":
        return False
    try:
        runner(["taskkill", "/PID", str(int(pid)), "/F"],
               capture_output=True, text=True, timeout=10,
               **_NO_WINDOW_KWARGS)
        return True
    except (OSError, subprocess.SubprocessError):
        logger.exception("Could not terminate process %s", pid)
        return False
```

- [ ] **Step 4: Wire recovery into the engine**

Add `from . import atomicio, bookmarks, paths, procid` to `hotkeys.py`, then:

```python
    def recover_orphan(self) -> bool:
        """Terminate an engine left behind by a crashed Wingman.

        Identity is the image name AND the run token from the command line.
        The PID alone is not identity -- Windows reuses PIDs and this runs
        after an unclean shutdown -- and the image alone is not either,
        because the bundled interpreter could be running someone else's
        script. Anything that fails either check is treated as a stale
        record and discarded rather than killed.

        Note this only ever runs at the next start. Neither this nor
        #SingleInstance Force helps a user who closes Wingman and never
        reopens it; clean shutdown is what covers the common case.
        """
        try:
            record = json.loads(self._pid_path().read_text())
            pid = int(record["pid"])
            token = str(record["token"])
        except (OSError, ValueError, KeyError, TypeError):
            self._clear_pid_record()
            return False

        info = procid.describe(pid)
        if not info:
            self._clear_pid_record()
            return False

        image_ok = "autohotkey" in (info.get("image") or "").lower()
        token_ok = token and token in (info.get("cmdline") or "")
        if not (image_ok and token_ok):
            logger.info("PID %s is not our engine; leaving it alone.", pid)
            self._clear_pid_record()
            return False

        logger.warning("Terminating orphaned engine %s", pid)
        procid.terminate(pid)
        self._clear_pid_record()
        return True
```

and call it as the first statement inside `start()` after the idempotence check:

```python
        if self.is_running():
            return True
        self.recover_orphan()
```

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_hotkeys_orphan.py tests/test_hotkeys_lifecycle.py -q
git add obs_youtube_uploader/procid.py obs_youtube_uploader/hotkeys.py tests/test_hotkeys_orphan.py
git commit -m "feat(hotkeys): recover orphaned engines with verified identity"
```

---

### Task 10: Status reading and staleness

**Files:**
- Modify: `obs_youtube_uploader/hotkeys.py`
- Test: `tests/test_hotkeys_status.py`

**Interfaces:**
- Consumes: `eve_status.json` written by the engine (Task 15).
- Produces:
  - `EngineStatus` dataclass: `state` (`"off" | "stopped" | "stale" | "running"`), `sig`, `root`, `next_num`, `next_alpha` (all `str | None`), `failed_binds: list[str]`, `consumed_seq: int`.
  - `HotkeyEngine.status(enabled: bool, now: float | None = None) -> EngineStatus`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkeys_status.py
"""A stale readout is worse than none: a plausible-looking dead root system
would be acted on. Liveness is the authority; the file only supplies values
once liveness is established."""
import json
from obs_youtube_uploader import hotkeys
from tests.test_hotkeys_lifecycle import FakeSpawner, engine, section

VALUES = {"sig": "-ABC", "root": "J1234", "next_num": "J12345",
          "next_alpha": "J1234A", "failed_binds": [], "seq": 0,
          "written": 1000.0}


def write_status(tmp_path, **over):
    (tmp_path / "eve_status.json").write_text(json.dumps({**VALUES, **over}))


def test_off_when_not_enabled(tmp_path):
    write_status(tmp_path)
    got = engine(tmp_path, FakeSpawner()).status(enabled=False, now=1000.0)
    assert got.state == "off"
    assert got.root is None


def test_stopped_clears_values_rather_than_freezing_them(tmp_path):
    """The engine died but its last status file is still on disk. Showing
    J1234 as the current root would be a lie the user acts on."""
    write_status(tmp_path)
    got = engine(tmp_path, FakeSpawner()).status(enabled=True, now=1000.0)
    assert got.state == "stopped"
    assert got.root is None
    assert got.sig is None


def test_running_reports_the_values(tmp_path):
    write_status(tmp_path)
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    got = eng.status(enabled=True, now=1002.0)
    assert got.state == "running"
    assert got.root == "J1234"
    assert got.next_alpha == "J1234A"


def test_stale_when_the_file_stops_updating(tmp_path):
    """The engine writes every 2s; several missed ticks means it is alive
    but not working."""
    write_status(tmp_path, written=1000.0)
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    got = eng.status(enabled=True, now=1000.0 + hotkeys.STALE_AFTER_S + 1)
    assert got.state == "stale"
    assert got.root is None


def test_failed_binds_are_surfaced(tmp_path):
    """Registration errors are swallowed by UseErrorLevel in the script
    (111unified.ahk:767-823); a process can look healthy with dead keys."""
    write_status(tmp_path, failed_binds=["FinH", "FinL"])
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    assert eng.status(enabled=True, now=1001.0).failed_binds == ["FinH", "FinL"]


def test_missing_status_file_while_running_is_stale_not_a_crash(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    assert eng.status(enabled=True, now=1000.0).state == "stale"


def test_corrupt_status_file_is_stale_not_a_crash(tmp_path):
    """A torn read is exactly what atomic publication is meant to prevent,
    but a truncated file from an older build must not take the UI down."""
    (tmp_path / "eve_status.json").write_text('{"sig": "-AB')
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    assert eng.status(enabled=True, now=1000.0).state == "stale"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hotkeys_status.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'STALE_AFTER_S'`

- [ ] **Step 3: Write minimal implementation**

Add to `hotkeys.py`:

```python
from dataclasses import dataclass, field

# The engine republishes every 2s (111unified.ahk:77). Three missed ticks
# is a deliberate margin: one missed write on a busy machine is normal, a
# sustained gap means it is alive but not working.
STALE_AFTER_S = 6.0


@dataclass
class EngineStatus:
    """What the UI renders. `state` is authoritative; the values are only
    populated when state == "running"."""
    state: str = "off"
    sig: str | None = None
    root: str | None = None
    next_num: str | None = None
    next_alpha: str | None = None
    failed_binds: list = field(default_factory=list)
    consumed_seq: int = 0
```

and the method:

```python
    def status(self, enabled: bool, now: float | None = None) -> EngineStatus:
        """Report engine state, driven by liveness rather than file contents.

        The status file outlives the process that wrote it. Reading values
        from it without first establishing that the engine is alive is how
        a dead root system gets displayed as the current one.
        """
        if not enabled:
            return EngineStatus(state="off")
        if not self.is_running():
            return EngineStatus(state="stopped")

        now = time.time() if now is None else now
        try:
            raw = json.loads(self._status_path().read_text())
            written = float(raw["written"])
        except (OSError, ValueError, KeyError, TypeError):
            return EngineStatus(state="stale")
        if now - written > STALE_AFTER_S:
            return EngineStatus(state="stale")

        failed = raw.get("failed_binds")
        return EngineStatus(
            state="running",
            sig=raw.get("sig") or None,
            root=raw.get("root") or None,
            next_num=raw.get("next_num") or None,
            next_alpha=raw.get("next_alpha") or None,
            failed_binds=[str(b) for b in failed] if isinstance(failed, list) else [],
            consumed_seq=int(raw.get("seq") or 0),
        )

    def _status_path(self) -> Path:
        return self._state_dir / paths.engine_status_file().name
```

with `import time` at the top.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hotkeys_status.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/hotkeys.py tests/test_hotkeys_status.py
git commit -m "feat(hotkeys): liveness-driven status with staleness detection"
```

---

### Task 11: The command channel

**Files:**
- Modify: `obs_youtube_uploader/hotkeys.py`
- Test: `tests/test_hotkeys_commands.py`

**Interfaces:**
- Consumes: `status()` (Task 10) for acknowledgement.
- Produces:
  - `HotkeyEngine.send_command(name: str, argument: str = "") -> bool` — `name` is `"set_root"` or `"clear_root"`. Returns False if a previous command is unacknowledged.
  - `HotkeyEngine.pending_command() -> int | None` — the unacknowledged sequence, or None.
  - `HotkeyEngine.sync_sequence() -> None` — called on start; initialises the counter from the file on disk.
  - The file format is INI with a single `[Command]` section holding `Seq`, `Name`, `Argument`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkeys_commands.py
"""Set Root and Clear Root are operations, not settings, so they cannot
travel through the config file. One slot, a monotonic sequence, and an
acknowledgement is the whole protocol -- but each of those three pieces has
a failure mode worth a test."""
import json
from obs_youtube_uploader import hotkeys
from tests.test_hotkeys_lifecycle import FakeSpawner, engine, section


def started(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    return eng


def command(tmp_path):
    """Parse the INI the engine will read with IniRead."""
    out = {}
    for line in (tmp_path / "eve_command.ini").read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def ack(tmp_path, seq, now=1000.0):
    (tmp_path / "eve_status.json").write_text(json.dumps(
        {"seq": seq, "written": now, "failed_binds": []}))


def test_first_command_is_sequence_one(tmp_path):
    eng = started(tmp_path)
    assert eng.send_command("clear_root") is True
    got = command(tmp_path)
    assert got["Seq"] == "1"
    assert got["Name"] == "clear_root"
    assert got["Argument"] == ""


def test_file_has_the_section_header_iniread_needs(tmp_path):
    eng = started(tmp_path)
    eng.send_command("clear_root")
    assert (tmp_path / "eve_command.ini").read_text().startswith("[Command]")


def test_argument_is_carried(tmp_path):
    eng = started(tmp_path)
    eng.send_command("set_root", "J123456")
    assert command(tmp_path)["Argument"] == "J123456"


def test_argument_cannot_forge_an_ini_line(tmp_path):
    """The argument is free text typed by the user and lands in a file the
    engine parses; a newline must not be able to add a key."""
    eng = started(tmp_path)
    eng.send_command("set_root", "J1\r\nName=clear_root")
    assert command(tmp_path)["Name"] == "set_root"


def test_unacknowledged_command_is_never_overwritten(tmp_path):
    """One slot and a 2s poll: a second action taken quickly would destroy
    the first, and the user would see one of their two clicks vanish."""
    eng = started(tmp_path)
    eng.send_command("set_root", "J111")
    assert eng.send_command("clear_root") is False
    assert command(tmp_path)["Argument"] == "J111"


def test_a_new_command_is_allowed_once_acknowledged(tmp_path):
    eng = started(tmp_path)
    eng.send_command("set_root", "J111")
    ack(tmp_path, 1)
    assert eng.send_command("clear_root", now=1000.0) is True
    assert command(tmp_path)["Seq"] == "2"


def test_pending_command_reports_the_waiting_sequence(tmp_path):
    eng = started(tmp_path)
    eng.send_command("clear_root")
    assert eng.pending_command(now=1000.0) == 1
    ack(tmp_path, 1)
    assert eng.pending_command(now=1000.0) is None


def test_sequence_survives_a_wingman_restart(tmp_path):
    """If Wingman resumed from zero while a higher-numbered command sat on
    disk, the engine would ignore every command until it caught up."""
    eng = started(tmp_path)
    eng.send_command("clear_root")
    ack(tmp_path, 1)
    eng.send_command("set_root", "J1")
    ack(tmp_path, 2)

    fresh = started(tmp_path)
    fresh.sync_sequence()
    fresh.send_command("clear_root", now=1000.0)
    assert command(tmp_path)["Seq"] == "3"


def test_sync_ignores_a_corrupt_command_file(tmp_path):
    (tmp_path / "eve_command.ini").write_text("nonsense without a section")
    eng = started(tmp_path)
    eng.sync_sequence()
    eng.send_command("clear_root")
    assert command(tmp_path)["Seq"] == "1"


def test_command_is_refused_when_the_engine_is_not_running(tmp_path):
    """Writing a command nothing will read would leave the buttons stuck
    waiting for an acknowledgement that cannot arrive."""
    eng = engine(tmp_path, FakeSpawner())
    assert eng.send_command("clear_root") is False
    assert not (tmp_path / "eve_command.ini").exists()


def test_unknown_command_names_are_refused(tmp_path):
    eng = started(tmp_path)
    assert eng.send_command("rm_rf") is False
    assert not (tmp_path / "eve_command.ini").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hotkeys_commands.py -q`
Expected: FAIL — `AttributeError: 'HotkeyEngine' object has no attribute 'send_command'`

- [ ] **Step 3: Write minimal implementation**

Add to `hotkeys.py`:

```python
# The only operations the channel carries. Adding to this list should be a
# deliberate decision: the channel exists because two GUI buttons had no
# other route, not as a general RPC mechanism.
COMMANDS = frozenset({"set_root", "clear_root"})
```

and the methods:

```python
    def sync_sequence(self) -> None:
        """Adopt the sequence already on disk.

        Called after start(). Without it a restarted Wingman would resume
        from zero while a higher-numbered command file remained, and every
        command would be ignored as already-consumed until the counter
        caught up.
        """
        self._seq = 0
        try:
            for line in self._command_path().read_text().splitlines():
                key, _, value = line.partition("=")
                if key.strip() == "Seq":
                    self._seq = int(value.strip())
                    return
        except (OSError, ValueError):
            self._seq = 0

    def pending_command(self, now: float | None = None) -> int | None:
        """The sequence awaiting acknowledgement, or None."""
        if not self._seq:
            return None
        consumed = self.status(enabled=True, now=now).consumed_seq
        return None if consumed >= self._seq else self._seq

    def send_command(self, name: str, argument: str = "",
                     now: float | None = None) -> bool:
        """Publish one operation for the engine to execute.

        Refuses while a previous command is unacknowledged: the file holds
        one slot and the engine polls every 2s, so overwriting would
        silently discard the earlier action.
        """
        if name not in COMMANDS:
            logger.error("Refusing unknown engine command %r", name)
            return False
        if not self.is_running():
            return False
        if self.pending_command(now=now) is not None:
            return False

        self._seq += 1
        # INI, and sanitised: the argument is free text the user typed and
        # a newline in it would otherwise add a key to the section.
        body = ("[Command]\r\n"
                f"Seq={self._seq}\r\n"
                f"Name={name}\r\n"
                f"Argument={bookmarks.sanitise(argument)}\r\n")
        atomicio.write_atomic(self._command_path(), body)
        return True

    def _command_path(self) -> Path:
        return self._state_dir / paths.engine_command_file().name
```

and initialise `self._seq = 0` in `__init__`.

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/hotkeys.py tests/test_hotkeys_commands.py
git commit -m "feat(hotkeys): sequence-numbered command channel"
```

---

## Phase C — The vendored engine (Tasks 12-16)

**Read this before starting Phase C.** None of the AutoHotkey in this phase can be exercised by pytest. The only automated check is the invariant guard in Task 16; everything else is review plus the smoke checklist. Work in small commits so the diff stays readable, and do not batch these tasks.

Source of truth for the original is `111unified.ahk` at the repository root (untracked; copy it in if absent).

### Task 12: Vendor and strip

**Files:**
- Create: `obs_youtube_uploader/engine/eve_bookmarks.ahk` (from `111unified.ahk`)
- Test: none (see Task 16)

**Interfaces:**
- Produces: a script that reads `eve_bookmark_helper.ini` from its working directory and registers hotkeys. No GUI, no tray, no config writing.

- [ ] **Step 1: Copy the script verbatim and commit that alone**

```bash
mkdir -p obs_youtube_uploader/engine
cp 111unified.ahk obs_youtube_uploader/engine/eve_bookmarks.ahk
git add obs_youtube_uploader/engine/eve_bookmarks.ahk
git commit -m "chore(engine): vendor 111unified.ahk verbatim"
```

Committing the unmodified copy first is what makes every later commit in this phase a reviewable diff against the original rather than a 2000-line blob.

- [ ] **Step 2: Delete the GUI, tray and config-writing blocks**

Remove entirely:
- `Menu, Tray, *` block (`:63-68`) and the `ReloadScript:` / `ExitScript:` labels those menu items targeted
- `GoSub, ShowMainGui` at `:93`
- `SaveAllSettings:` and `SaveWindowSettings:` labels in full
- `ShowMainGui:`, `BuildMainGui:`, `RefreshWinList:`, `MainGuiClose:` labels in full
- The GUI event handlers: `OnWinCheck:`, `OnModeChange:`, `OnHomeZeroToggle:`, `OnPrefaceToggle:`, `OnPrefaceChange:`, `KBChange:`, `ResetKeybinds:`
- The `IfNotExist, %IniFile%` / `GoSub, SaveAllSettings` branch at the top of `LoadAllSettings` — replace with a bare `Return`, because Wingman now owns creating that file and the engine must never write it

Keep `SetManualRoot:` and `ClearRoot:` — they are operations, restored in Task 15.

- [ ] **Step 3: Remove the Copy and Paste binds**

Delete the `KB_Copy` / `KB_Paste` declarations (`:36-37`), their `IniRead` lines (`:120-121`), their `HotkeyLabelMap` entries, their registration in the global block, and the `DoCopy:` / `DoPaste:` labels.

- [ ] **Step 4: Pin single-instance behaviour**

Change line 5 from `#SingleInstance` to:

```ahk
; Force, explicitly: a duplicate spawn must replace the previous copy, not
; raise a prompt for a user who no longer has a GUI to answer it in.
#SingleInstance Force
```

- [ ] **Step 5: Accept the token argument**

After the `#SingleInstance` line, add:

```ahk
; Wingman passes /token <value> at spawn and records the same value beside
; the PID. Orphan recovery matches on it before terminating anything, so
; the interpreter running someone else's script is never killed.
RunToken := ""
Loop %0%
{
    Arg := %A_Index%
    if (Arg = "/token" && A_Index < %0%)
    {
        Next := A_Index + 1
        RunToken := %Next%
    }
}
```

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/engine/eve_bookmarks.ahk
git commit -m "refactor(engine): strip GUI, tray, config writes and Copy/Paste"
```

---

### Task 13: Remove Protean mode and pin home numbering

**Files:**
- Modify: `obs_youtube_uploader/engine/eve_bookmarks.ahk`

**This is the largest and least safe deletion in the plan.** `CurrentMode` is not localised: it branches inside every finisher, the parser and the status text. Removing it is threading logic out, not deleting a block.

- [ ] **Step 1: Delete the mode state**

Remove `CurrentMode := 1` (`:13`), its `IniRead` (`:115`), and the `global ... CurrentMode` entries in every function signature that lists it.

- [ ] **Step 2: Collapse every mode branch to the Flygd/ABH arm**

For each `if (CurrentMode = 1) { ... } else { ... }`, keep the `else` body and delete the rest. The finishers at `DoY:`, `DoO:`, `Do1:`–`Do6:`, `DoP:`, `DoDot:` each carry one. For example `DoY:` becomes:

```ahk
DoY:
if (RootModeActive) {
    FireRootFinisher("H", True)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "H"
    NewE := 0
    NewSlash := 0
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
}
Return
```

Also delete `FormatProteanClipAndPaste:` in full, and in `DoQ:` keep only the `StringUpper` arm.

- [ ] **Step 3: Pin home numbering to `.0`**

`HomeZeroIs0` is **not** Protean-specific — its GUI label said "v21/null static mode" but `FireRootFinisher` reads it with no reference to `CurrentMode` (`:870`, `:886`, `:893`). It decides whether home-mode bookmarks number from 0 or 1 under both schemes, and the shipped default is on (`:32`).

Delete the variable, its `IniRead`, and every `&& HomeZeroIs0` guard, keeping the **zero-based arm** so behaviour is unchanged for anyone who never touched the checkbox. In `FireRootFinisher` that means:

```ahk
    } else {
        if (ReadyToIncrement) {
            ; Home mode numbers from .0. This was the HomeZeroIs0 option,
            ; whose default was on (:32); it is now fixed behaviour. It is
            ; NOT tied to the removed Protean mode -- the original condition
            ; never mentioned CurrentMode.
            if (RootKey = "") {
                Num := NextNum - 1
            } else {
                Num := NextNum
            }
            UsedNums[NextNum] := True
            LastUsedNum := NextNum
            FindNextNum()
        } else {
            ; Preserve the original structure exactly. The home-mode first
            ; correction is .0, which the original produced by seeding
            ; LastUsedNum with 1 and subtracting below -- NOT by seeding it
            ; with NextNum, which diverges as soon as NextNum > 1.
            if (LastUsedNum = "") {
                LastUsedNum := (RootKey = "") ? 1 : NextNum
            }
            Num := (RootKey = "") ? LastUsedNum - 1 : LastUsedNum
        }
        SysKey := BuildSystemKey(RootKey, Num, False)
```

- [ ] **Step 4: Remove the return preface**

Delete `PrefaceReturn` and `ReturnPreface` (`:33-34`), their `IniRead` lines, and every use. Where a preface was prepended to a return bookmark, emit the bookmark unprefixed.

- [ ] **Step 5: Simplify the status text**

`RefreshStatusTab` and `ShowRootTooltip` both branch on mode to print `"N/A (Protean mode)"`. Both now always compute the alpha value:

```ahk
NextAlphaText := BuildSystemKey(RootKey, NextAlpha, True)
```

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/engine/eve_bookmarks.ahk
git commit -m "refactor(engine): single naming scheme, home numbering fixed at .0"
```

---

### Task 14: Repair the hotkey teardown and capture registration errors

**Files:**
- Modify: `obs_youtube_uploader/engine/eve_bookmarks.ahk`

**The bug this fixes.** `RefreshHotkeys` Step 1 resets to the global context with `Hotkey, IfWinActive` (`:705-713`) and disables bindings *there*. The eighteen window-scoped binds are registered under `Hotkey, IfWinActive, %WinTitle%` (`:786`), a different criterion, and AHK v1 disables only the variant matching the current one. Those variants are therefore never torn down. It is latent today because rebinding is rare; routing every config change through this path makes it routine, leaving hotkeys live against windows the user just disabled.

- [ ] **Step 1: Track the contexts registered on the previous pass**

Near the other globals:

```ahk
; Window titles whose hotkey variants were registered on the last pass.
; Required for teardown: a variant registered under IfWinActive <title> can
; only be disabled from inside that same criterion.
RegisteredWindows := []
```

- [ ] **Step 2: Replace Step 1 of RefreshHotkeys**

```ahk
RefreshHotkeys:
GoSub, LoadAllSettings          ; hot reload: keybinds and settings, not just [Enabled]

; Disable the global-context variants.
Hotkey, IfWinActive
For hk, lbl in HotkeyLabelMap
{
    if (hk != "")
        Hotkey, %hk%, Off, UseErrorLevel
}

; Disable the window-scoped variants IN THEIR OWN CONTEXT. Turning them off
; from the global context above does nothing at all -- that is the bug this
; loop exists to fix. Without it, changing a bind or disabling a window
; leaves the previous hotkey live.
For idx, OldTitle in RegisteredWindows
{
    Hotkey, IfWinActive, %OldTitle%
    For hk, lbl in HotkeyLabelMap
    {
        if (hk != "")
            Hotkey, %hk%, Off, UseErrorLevel
    }
}
Hotkey, IfWinActive
RegisteredWindows := []
FailedBinds := ""
```

- [ ] **Step 3: Add a registration helper that records failures**

```ahk
; Every Hotkey ... On UseErrorLevel in the original discarded its result,
; so a bind Windows refused -- one already claimed by another application --
; failed silently and the key simply did nothing.
RegisterBind(id, key, label) {
    global FailedBinds
    if (key = "")
        return
    Hotkey, %key%, %label%, On UseErrorLevel
    if (ErrorLevel)
        FailedBinds .= (FailedBinds = "" ? "" : ",") . id
}
```

- [ ] **Step 4: Route every registration through it**

Replace each `if (KB_X != "") \n Hotkey, %KB_X%, Label, On UseErrorLevel` pair with `RegisterBind("X", KB_X, "Label")`. Set Root moves from the global block into the per-window block, since it is no longer globally scoped:

```ahk
Loop, Parse, EnabledSection, `n, `r
{
    ...
    if (Val = "1") {
        Hotkey, IfWinActive, %WinTitle%
        RegisteredWindows.Push(WinTitle)
        RegisterBind("GrabSig",      KB_GrabSig,      "DoQ")
        RegisterBind("SetRoot",      KB_SetRoot,      "DoSemi")
        RegisterBind("FormatEnf",    KB_FormatEnf,    "DoE")
        RegisterBind("ConvertScout", KB_ConvertScout, "DoConvertScout")
        RegisterBind("FinH",  KB_FinH,  "DoY")
        RegisterBind("FinL",  KB_FinL,  "DoP")
        RegisterBind("FinN",  KB_FinN,  "DoDot")
        RegisterBind("Fin13", KB_Fin13, "DoO")
        RegisterBind("Fin1",  KB_Fin1,  "Do1")
        RegisterBind("Fin2",  KB_Fin2,  "Do2")
        RegisterBind("Fin3",  KB_Fin3,  "Do3")
        RegisterBind("Fin4",  KB_Fin4,  "Do4")
        RegisterBind("Fin5",  KB_Fin5,  "Do5")
        RegisterBind("Fin6",  KB_Fin6,  "Do6")
        RegisterBind("FinETag",  KB_FinETag,  "DoQuote")
        RegisterBind("FinSlash", KB_FinSlash, "DoComma")
        RegisterBind("FinM", KB_FinM, "DoM")
        RegisterBind("FinS", KB_FinS, "DoS")
        RegisterBind("FinC", KB_FinC, "DoC")
    }
}
```

The global registration block disappears entirely — no bind is global any more.

- [ ] **Step 5: Simplify DoSemi**

`DoSemi` opened by checking whether the active window was an enabled EVE window and, if not, pasting the raw root (`:1024-1043`). That branch existed only for Protean dual-use. Since the bind is now window-scoped, it can only fire inside an enabled window; delete the check and the non-EVE branch, keeping the copy/parse/set-root flow.

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/engine/eve_bookmarks.ahk
git commit -m "fix(engine): tear down window-scoped hotkeys in their own context"
```

---

### Task 15: Publish status, consume commands

**Files:**
- Modify: `obs_youtube_uploader/engine/eve_bookmarks.ahk`

**Interfaces:**
- Produces: `eve_status.json` matching what `HotkeyEngine.status()` reads (Task 10) — keys `sig`, `root`, `next_num`, `next_alpha`, `failed_binds`, `seq`, `written`.
- Consumes: `eve_command.ini` written by `send_command()` (Task 11).

- [ ] **Step 1: Replace RefreshStatusTab's sink**

The function already computes all five values on a 2s timer; only where they go changes. Replace the five `GuiControl, Main:, ...` calls with:

```ahk
RefreshStatusTab:
if (RootModeActive) {
    RootText     := RootKey = "" ? "(home)" : RootKey
    NextNumText  := BuildSystemKey(RootKey, NextNum,   False)
    NextAlphaText := BuildSystemKey(RootKey, NextAlpha, True)
} else {
    RootText := "", NextNumText := "", NextAlphaText := ""
}
SigText := LastSigId

; Written to a temp name and moved over the target: Wingman polls this at
; ~1Hz and must never read a half-written file.
StatusBody := "{"
    . """sig"":""" . JsonEsc(SigText) . ""","
    . """root"":""" . JsonEsc(RootText) . ""","
    . """next_num"":""" . JsonEsc(NextNumText) . ""","
    . """next_alpha"":""" . JsonEsc(NextAlphaText) . ""","
    . """failed_binds"":[" . JsonList(FailedBinds) . "],"
    . """seq"":" . (ConsumedSeq + 0) . ","
    . """written"":" . A_NowUTC_Epoch
    . "}"
FileDelete, eve_status.json.tmp
FileAppend, %StatusBody%, eve_status.json.tmp
FileMove, eve_status.json.tmp, eve_status.json, 1
Return
```

`A_NowUTC_Epoch` is not built in; add near the top:

```ahk
; Unix seconds, to compare against Python's time.time() for staleness.
EpochNow() {
    diff := A_NowUTC
    EnvSub, diff, 19700101000000, Seconds
    return diff
}
```

and use `EpochNow()` in place of `A_NowUTC_Epoch`.

- [ ] **Step 2: Add the JSON helpers**

```ahk
; Minimal escaping: these values are system names, sig ids and bind ids --
; no control characters -- but a stray quote or backslash would still
; produce a file Python cannot parse, and the UI would read "stale".
JsonEsc(text) {
    StringReplace, text, text, \, \\, All
    StringReplace, text, text, ", \", All
    return text
}

JsonList(csv) {
    if (csv = "")
        return ""
    out := ""
    Loop, Parse, csv, `,
        out .= (out = "" ? "" : ",") . """" . JsonEsc(A_LoopField) . """"
    return out
}
```

- [ ] **Step 3: Consume commands on the same timer**

Add `ConsumedSeq := 0` to the globals, and at the top of `RefreshStatusTab`:

```ahk
GoSub, ReadCommand
```

then:

```ahk
ReadCommand:
IfNotExist, eve_command.ini
    Return
IniRead, CmdSeq,  eve_command.ini, Command, Seq, 0
IniRead, CmdName, eve_command.ini, Command, Name, %A_Space%
IniRead, CmdArg,  eve_command.ini, Command, Argument, %A_Space%
CmdSeq += 0
; Strictly greater: the file is never deleted, so re-running anything at or
; below the last consumed sequence would replay it on every tick.
if (CmdSeq <= ConsumedSeq)
    Return
ConsumedSeq := CmdSeq
if (CmdName = "clear_root")
    GoSub, ClearRoot
else if (CmdName = "set_root")
{
    ManualRoot := Trim(CmdArg)
    GoSub, SetManualRoot
}
Return
```

- [ ] **Step 4: Detach SetManualRoot from the GUI**

`SetManualRoot` began with `GuiControlGet, ManualRoot, Main:, ManualRoot` (`:578`). Delete that line — `ManualRoot` is now set by `ReadCommand` before the `GoSub`. The rest of the label is unchanged.

- [ ] **Step 5: Initialise ConsumedSeq at startup**

Immediately before the main `Return` at the end of the auto-execute section:

```ahk
; Adopt whatever sequence is already on disk, so a command left by a
; previous session is not replayed on this one's first tick.
IniRead, StartSeq, eve_command.ini, Command, Seq, 0
ConsumedSeq := StartSeq + 0
```

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/engine/eve_bookmarks.ahk
git commit -m "feat(engine): publish status atomically and consume commands"
```

---

### Task 16: Invariant guard

**Files:**
- Test: `tests/test_engine_invariants.py`

This is the only automated check on the engine. It pins the two properties the whole design rests on, so a later re-sync from the standalone script cannot quietly undo them.

- [ ] **Step 1: Write the test**

```python
# tests/test_engine_invariants.py
"""The engine cannot be exercised by pytest, so these are the only
automated checks on it. Modelled on test_no_tk.py, which exists for exactly
this reason: to stop something that was removed on purpose creeping back.
"""
import re
import pytest
from obs_youtube_uploader import paths


@pytest.fixture
def source():
    script = paths.engine_script()
    assert script is not None, "vendored engine script is missing"
    return script.read_text(encoding="utf-8", errors="replace")


def test_no_gui(source):
    """The GUI is Wingman's job now. A returning Gui command means a second
    config surface, and with it the two-writer problem the design removed."""
    assert not re.search(r"^\s*Gui[,\s]", source, re.MULTILINE)
    assert not re.search(r"^\s*GuiControl", source, re.MULTILINE)


def test_engine_never_writes_config(source):
    """settings.json is the single source of truth and the INI is derived
    from it. An IniWrite here would make the engine a second writer."""
    assert "IniWrite" not in source


def test_no_tray_menu(source):
    assert not re.search(r"^\s*Menu,\s*Tray", source, re.MULTILINE)


def test_single_instance_is_pinned(source):
    """Unparameterised #SingleInstance prompts, and there is no GUI left to
    answer the prompt in."""
    assert "#SingleInstance Force" in source


def test_protean_mode_is_gone(source):
    assert "CurrentMode" not in source
    assert "FormatProteanClipAndPaste" not in source


def test_removed_settings_are_gone(source):
    for name in ("HomeZeroIs0", "PrefaceReturn", "ReturnPreface"):
        assert name not in source


def test_copy_and_paste_binds_are_gone(source):
    assert "KB_Copy" not in source
    assert "KB_Paste" not in source


def test_every_registration_records_failures(source):
    """Registration must go through RegisterBind, which checks ErrorLevel.
    A bare Hotkey ... On UseErrorLevel would swallow the failure again."""
    bare = re.findall(r"Hotkey,\s*%KB_\w+%.*On\s+UseErrorLevel", source)
    assert bare == []
    assert "RegisterBind(" in source


def test_window_scoped_teardown_exists(source):
    """The teardown bug: variants registered under IfWinActive <title> can
    only be disabled from inside that criterion."""
    assert "RegisteredWindows" in source


def test_status_is_published_atomically(source):
    assert "eve_status.json.tmp" in source
    assert re.search(r"FileMove,\s*eve_status\.json\.tmp,\s*eve_status\.json,\s*1",
                     source)
```

- [ ] **Step 2: Run it**

Run: `pytest tests/test_engine_invariants.py -q`
Expected: PASS (Tasks 12-15 already satisfy every assertion)

- [ ] **Step 3: Commit**

```bash
git add tests/test_engine_invariants.py
git commit -m "test(engine): pin the invariants the design depends on"
```

---

## Phase D — Wiring and UI (Tasks 17-22)

### Task 17: EVE window enumeration

**Files:**
- Create: `obs_youtube_uploader/evewindows.py`
- Test: `tests/test_evewindows.py`

**Interfaces:**
- Produces: `list_eve_windows() -> list[str]` — sorted, de-duplicated titles starting `EVE - `. Returns `[]` off Windows.
- Produces: `TITLE_PREFIX = "EVE - "`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_evewindows.py
"""Windows-only at runtime, importable on Linux -- the ui/chrome.py pattern
(window-resize-plan.md:130-140). The enumerator is injected so the matching
and de-duplication logic is testable off-platform."""
from obs_youtube_uploader import evewindows


def test_returns_empty_off_windows(monkeypatch):
    monkeypatch.setattr(evewindows.sys, "platform", "linux")
    assert evewindows.list_eve_windows() == []


def test_keeps_only_eve_titles(monkeypatch):
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    titles = ["EVE - Pilot One", "Notepad", "EVE - Alt Two", "eve online"]
    assert evewindows.list_eve_windows(enumerator=lambda: titles) == [
        "EVE - Alt Two", "EVE - Pilot One"]


def test_deduplicates(monkeypatch):
    """Multiboxing routinely produces two handles reporting one title."""
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    titles = ["EVE - Pilot", "EVE - Pilot"]
    assert evewindows.list_eve_windows(enumerator=lambda: titles) == ["EVE - Pilot"]


def test_prefix_match_is_case_sensitive_like_the_script(monkeypatch):
    """The engine matches ^EVE -  (111unified.ahk:248). If Wingman offered a
    window the engine will never match, the checkbox would do nothing."""
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    assert evewindows.list_eve_windows(enumerator=lambda: ["Eve - Pilot"]) == []


def test_enumerator_failure_is_survivable(monkeypatch):
    monkeypatch.setattr(evewindows.sys, "platform", "win32")

    def boom():
        raise OSError("no window station")

    assert evewindows.list_eve_windows(enumerator=boom) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_evewindows.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/evewindows.py
"""Enumerate running EVE client windows by title.

Windows-only at runtime; imports and tests cleanly on Linux, following the
ui/chrome.py precedent. ctypes is imported lazily inside the enumerator so
the module itself has no platform dependency at import time.
"""
import logging
import sys

logger = logging.getLogger(__name__)

# The engine matches ^EVE -  (111unified.ahk:248). Offering the user a
# window the engine will never match would give them a checkbox that
# silently does nothing, so the two must agree exactly.
TITLE_PREFIX = "EVE - "


def _enumerate_titles() -> list:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titles = []

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            titles.append(buffer.value)
        return True

    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(proto(callback), 0)
    return titles


def list_eve_windows(enumerator=None) -> list:
    """Sorted, de-duplicated EVE window titles. Empty off Windows."""
    if sys.platform != "win32":
        return []
    try:
        titles = (enumerator or _enumerate_titles)()
    except Exception:
        logger.exception("Could not enumerate windows")
        return []
    return sorted({t for t in titles if t.startswith(TITLE_PREFIX)})
```

- [ ] **Step 4: Run test and commit**

```bash
pytest tests/test_evewindows.py -q
git add obs_youtube_uploader/evewindows.py tests/test_evewindows.py
git commit -m "feat(evewindows): enumerate EVE client windows"
```

---

### Task 18: Bridge methods

**Files:**
- Modify: `obs_youtube_uploader/ui/api.py`
- Test: `tests/test_api_bookmarks.py`

**Interfaces:**
- Consumes: `HotkeyEngine` (Tasks 8-11), `evewindows` (Task 17), `bookmarks` (Tasks 1-5).
- Produces on `Api` — all JS-callable, so public:
  - `get_bookmarks() -> dict` — `{"settings": section, "labels": dict, "order": list, "windows": list, "collisions": dict}`
  - `save_bookmarks(section: dict) -> dict` — persists, regenerates INI, starts/stops the engine, returns the same shape as `get_bookmarks`
  - `capture_bind(parts: dict) -> dict` — `to_ahk` passthrough
  - `parse_bind(text: str) -> dict` — `parse_ahk` passthrough
  - `eve_command(name: str, argument: str = "") -> bool`
  - `import_bookmarks() -> dict` — opens a file dialog, returns `{"ok": bool, "discarded": list, "notes": list}`
- Produces on `AppState`: `engine: HotkeyEngine | None = None`
- New bridge handler name: `onEveStatus`, `onBookmarks`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_bookmarks.py
"""The bridge is tested headless through FakeWindow, as every other Api
method is (tests/fakes.py)."""
import json
import pytest
from obs_youtube_uploader import bookmarks, hotkeys, settings
from tests.fakes import FakeWindow


class FakeEngine:
    def __init__(self):
        self.applied = []
        self.started = 0
        self.stopped = 0
        self.commands = []
        self.running = False

    def apply(self, section):
        self.applied.append(section)

    def start(self):
        self.started += 1
        self.running = True
        return True

    def stop(self, timeout=5.0):
        self.stopped += 1
        self.running = False

    def is_running(self):
        return self.running

    def sync_sequence(self):
        pass

    def send_command(self, name, argument=""):
        self.commands.append((name, argument))
        return True

    def status(self, enabled, now=None):
        return hotkeys.EngineStatus(
            state="running" if self.running else "off", root="J1234")


@pytest.fixture
def api(tmp_path, monkeypatch):
    from obs_youtube_uploader.ui import api as api_mod
    monkeypatch.setattr(api_mod.paths, "settings_file",
                        lambda: tmp_path / "s.json")
    state = api_mod.AppState(recording_dir=tmp_path,
                             settings=settings.load(tmp_path / "s.json"))
    state.engine = FakeEngine()
    built = api_mod.Api(state)
    built._window = FakeWindow()
    return built


def test_get_returns_settings_labels_and_order(api):
    got = api.get_bookmarks()
    assert got["settings"]["enabled"] is False
    assert got["order"] == list(bookmarks.BIND_IDS)
    assert got["labels"]["FinH"] == "Finisher: HS (highsec)"


def test_get_returns_human_labels_for_bound_keys(api):
    """The page must never translate a hotkey string itself -- that is why
    to_ahk returns a display value. Unbound ids are absent rather than
    empty so the page's `|| 'Not set'` fallback fires."""
    got = api.get_bookmarks()
    assert got["displays"]["ConvertScout"] == "Ctrl+Shift+S"
    assert "FinH" not in got["displays"]


def test_get_lists_live_eve_windows(api, monkeypatch):
    from obs_youtube_uploader.ui import api as api_mod
    monkeypatch.setattr(api_mod.evewindows, "list_eve_windows",
                        lambda: ["EVE - Pilot"])
    assert api.get_bookmarks()["windows"] == ["EVE - Pilot"]


def test_save_persists_and_regenerates_the_ini(api, tmp_path):
    section = dict(api.get_bookmarks()["settings"])
    section["keybinds"] = dict(bookmarks.DEFAULT_BINDS, FinH="^h")
    api.save_bookmarks(section)
    assert api._state.engine.applied[-1]["keybinds"]["FinH"] == "^h"
    on_disk = json.loads((tmp_path / "s.json").read_text())
    assert on_disk["eve_bookmarks"]["keybinds"]["FinH"] == "^h"


def test_enabling_starts_the_engine_and_disabling_stops_it(api):
    section = dict(api.get_bookmarks()["settings"], enabled=True)
    api.save_bookmarks(section)
    assert api._state.engine.started == 1
    api.save_bookmarks(dict(section, enabled=False))
    assert api._state.engine.stopped == 1


def test_save_reports_collisions_rather_than_silently_accepting(api):
    """RefreshHotkeys would let one bind win silently."""
    section = dict(api.get_bookmarks()["settings"])
    section["keybinds"] = dict(bookmarks.DEFAULT_BINDS, FinH="^h", FinL="^h")
    got = api.save_bookmarks(section)
    assert got["collisions"] == {"^h": ["FinH", "FinL"]}


def test_save_rejects_a_non_dict_payload(api):
    """Everything from the page is untrusted input to a file that drives a
    keyboard hook."""
    before = api.get_bookmarks()["settings"]
    api.save_bookmarks("nonsense")
    assert api.get_bookmarks()["settings"] == before


def test_capture_and_parse_delegate_to_bookmarks(api):
    assert api.capture_bind({"ctrl": True, "alt": False, "shift": True,
                             "meta": False, "code": "KeyS"})["ahk"] == "^+s"
    assert api.parse_bind("+^s")["ahk"] == "^+s"


def test_eve_command_is_forwarded(api):
    api.eve_command("set_root", "J1234")
    assert api._state.engine.commands == [("set_root", "J1234")]


def test_import_applies_and_reports(api, tmp_path, monkeypatch):
    legacy = tmp_path / "eve_bookmark_helper.ini"
    legacy.write_text("[Keybinds]\r\nFinH=y\r\nCopy=^c\r\n")
    api._window.dialog_result = (str(legacy),)
    got = api.import_bookmarks()
    assert got["ok"] is True
    assert api.get_bookmarks()["settings"]["keybinds"]["FinH"] == "y"
    assert any("Copy" in d for d in got["discarded"])


def test_import_cancelled_changes_nothing(api):
    api._window.dialog_result = None
    assert api.import_bookmarks()["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_bookmarks.py -q`
Expected: FAIL — `AttributeError: 'Api' object has no attribute 'get_bookmarks'`

- [ ] **Step 3: Write the implementation**

Add `evewindows` and `bookmarks` to the imports in `api.py`, add `engine: object | None = None` to `AppState`, and add the methods:

```python
    # ---- EVE bookmarks ------------------------------------------------
    def get_bookmarks(self) -> dict:
        """Everything the Bookmarks route renders, in one call."""
        section = self._state.settings["eve_bookmarks"]
        return {
            "settings": section,
            "labels": bookmarks.BIND_LABELS,
            "order": list(bookmarks.BIND_IDS),
            "windows": evewindows.list_eve_windows(),
            "collisions": bookmarks.collisions(section["keybinds"]),
            # Human labels for the bound keys. Computed here rather than in
            # the page, which is the entire reason to_ahk returns a display
            # string: the page holds no mapping table and cannot drift from
            # this one. Without this the UI would show raw "^+s".
            "displays": {bid: bookmarks.parse_ahk(value)["display"]
                         for bid, value in section["keybinds"].items()
                         if value},
        }

    def save_bookmarks(self, section) -> dict:
        """Persist the section, regenerate the INI, and match the engine to
        the enabled flag.

        The payload arrives from the page and lands in a file that registers
        keyboard hooks, so it is re-validated here rather than trusted.
        """
        if not isinstance(section, dict):
            logger.error("Refusing a non-dict bookmarks payload")
            return self.get_bookmarks()

        merged = dict(self._state.settings)
        merged["eve_bookmarks"] = settings.validated_eve(section)
        settings.save(merged)
        self._state.settings = settings.load()
        clean = self._state.settings["eve_bookmarks"]

        engine = self._state.engine
        if engine is not None:
            engine.apply(clean)
            if clean["enabled"] and not engine.is_running():
                engine.start()
                engine.sync_sequence()
            elif not clean["enabled"] and engine.is_running():
                engine.stop()
        return self.get_bookmarks()

    def capture_bind(self, parts) -> dict:
        return bookmarks.to_ahk(parts if isinstance(parts, dict) else {})

    def parse_bind(self, text) -> dict:
        return bookmarks.parse_ahk(text if isinstance(text, str) else "")

    def eve_command(self, name, argument="") -> bool:
        engine = self._state.engine
        if engine is None:
            return False
        return bool(engine.send_command(str(name), str(argument or "")))

    def import_bookmarks(self) -> dict:
        """Import a standalone helper INI chosen by the user.

        The standalone script wrote its INI relative to its working
        directory, so there is no path worth probing -- the user points at
        it.
        """
        import webview
        chosen = self._window.create_file_dialog(
            webview.FileDialog.OPEN, directory="")
        if not chosen:
            return {"ok": False, "discarded": [], "notes": []}
        try:
            # utf-8-sig, not utf-8: the legacy file is routinely hand-edited
            # in Notepad, which prepends a BOM. import_legacy_ini strips one
            # too, but handling it at the I/O boundary as well means the
            # parser never sees it -- and a BOM reaching the parser silently
            # discarded the whole first section, which is every keybind.
            text = Path(chosen[0]).read_text(encoding="utf-8-sig",
                                             errors="replace")
        except OSError as exc:
            return {"ok": False, "discarded": [],
                    "notes": [f"Could not read that file: {exc}"]}

        result = bookmarks.import_legacy_ini(text)
        # Import never enables the engine: reading someone's old settings is
        # not consent to start a keyboard hook.
        result["section"]["enabled"] = \
            self._state.settings["eve_bookmarks"]["enabled"]
        self.save_bookmarks(result["section"])
        return {"ok": True, "discarded": result["discarded"],
                "notes": result["notes"]}
```

- [ ] **Step 4: Register the handler names**

In `web/app.js:53`, extend `WM.HANDLERS`:

```javascript
  WM.HANDLERS = ['onRows', 'onDuration', 'onProgress', 'onStatus',
                 'onRetryAvailable', 'onLink', 'onSettings', 'onChannel',
                 'onAuthState', 'onDialog', 'onFirstRun',
                 'onBookmarks', 'onEveStatus'];
```

- [ ] **Step 5: Run tests and commit**

```bash
pytest -q
git add obs_youtube_uploader/ui/api.py obs_youtube_uploader/web/app.js tests/test_api_bookmarks.py
git commit -m "feat(api): bookmarks bridge methods"
```

---

### Task 19: Engine lifecycle and status polling

**Files:**
- Modify: `obs_youtube_uploader/__main__.py`
- Modify: `obs_youtube_uploader/ui/api.py`
- Test: `tests/test_main_engine.py`

**Interfaces:**
- Consumes: `HotkeyEngine`, `Api.get_bookmarks`.
- Produces: `Api._push_eve_status()` called on the existing scheduler tick.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_engine.py
"""A surviving engine holds a global keyboard hook with no UI to disable it,
so shutdown must stop it on every exit path."""
from obs_youtube_uploader import __main__ as main_mod


class Recorder:
    def __init__(self, enabled):
        self.enabled = enabled
        self.started = 0
        self.stopped = 0
        self.synced = 0

    def start(self):
        self.started += 1
        return True

    def stop(self, timeout=5.0):
        self.stopped += 1

    def sync_sequence(self):
        self.synced += 1

    def apply(self, section):
        pass

    def is_running(self):
        return self.started > self.stopped


def test_engine_is_not_started_when_disabled():
    engine = Recorder(enabled=False)
    main_mod.start_engine_if_enabled(engine, {"enabled": False})
    assert engine.started == 0


def test_engine_starts_and_syncs_when_enabled():
    engine = Recorder(enabled=True)
    main_mod.start_engine_if_enabled(engine, {"enabled": True})
    assert engine.started == 1
    assert engine.synced == 1


def test_shutdown_stops_a_running_engine():
    engine = Recorder(enabled=True)
    main_mod.start_engine_if_enabled(engine, {"enabled": True})
    main_mod.shutdown_engine(engine)
    assert engine.stopped == 1


def test_shutdown_is_safe_with_no_engine():
    main_mod.shutdown_engine(None)


def test_shutdown_survives_an_engine_that_raises():
    """Shutdown must not be blocked by the thing it is cleaning up."""
    class Angry(Recorder):
        def stop(self, timeout=5.0):
            raise OSError("nope")

    main_mod.shutdown_engine(Angry(enabled=True))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_engine.py -q`
Expected: FAIL — `AttributeError: module has no attribute 'start_engine_if_enabled'`

- [ ] **Step 3: Write the implementation**

In `__main__.py`:

```python
def start_engine_if_enabled(engine, section) -> None:
    """Start the hotkey engine only when the user has turned it on.

    Opt-in is the whole point: enabling installs a global keyboard hook, and
    an upgrading user must not acquire one by upgrading.
    """
    if engine is None or not section.get("enabled"):
        return
    if engine.start():
        engine.sync_sequence()


def shutdown_engine(engine) -> None:
    """Stop the engine on the way out, whatever else has gone wrong.

    An engine that outlives Wingman keeps a keyboard hook alive with nothing
    left to disable it, so this must never be the thing that raises.
    """
    if engine is None:
        return
    try:
        engine.stop()
    except Exception:
        logger.exception("Engine did not stop cleanly")
```

In `main()`, after `AppState` is built:

```python
    engine = hotkeys.HotkeyEngine(paths.engine_exe(), paths.engine_script(),
                                  paths.state_dir())
    state.engine = engine
    engine.apply(state.settings["eve_bookmarks"])
    start_engine_if_enabled(engine, state.settings["eve_bookmarks"])
```

and beside the existing `icon.stop()` / `scheduler.stop()` calls at the end:

```python
    shutdown_engine(engine)
```

In `api.py`, add the push and call it from the same place the scheduler already ticks:

```python
    def _push_eve_status(self) -> None:
        """Publish engine status to the page.

        Pushed regardless of which route is showing: the status bar is
        global chrome, and app.js deliberately never tells Python which
        route is active.
        """
        engine = self._state.engine
        if engine is None:
            return
        enabled = self._state.settings["eve_bookmarks"]["enabled"]
        status = engine.status(enabled=enabled)
        self._push("onEveStatus", {
            "state": status.state, "sig": status.sig, "root": status.root,
            "next_num": status.next_num, "next_alpha": status.next_alpha,
            "failed_binds": status.failed_binds,
        })
```

- [ ] **Step 4: Run tests and commit**

```bash
pytest -q
git add obs_youtube_uploader/__main__.py obs_youtube_uploader/ui/api.py tests/test_main_engine.py
git commit -m "feat: engine lifecycle at startup and shutdown"
```

---

### Task 20: Navigation and route scaffolding

**Files:**
- Modify: `obs_youtube_uploader/web/index.html`, `web/app.js`, `web/style.css`

No test: this is markup and CSS, and the repo has no browser test toolchain by policy. Verified in the smoke pass.

- [ ] **Step 1: Replace the passive label with nav**

In `index.html`, the title bar becomes:

```html
  <div class="titlebar">
    <div class="pywebview-drag-region">
      <span class="mark">&#9654;</span>
      <span class="name">WINGMAN</span>
    </div>
    <!-- Sibling of the drag region, never a child: style.css:100-102 says
         only that element drags and buttons must stay clickable. A
         clickable child of it yields dead buttons or an immovable window. -->
    <nav class="routenav" id="routenav">
      <button class="navbtn active" id="nav-main" data-route="main">Uploader</button>
      <button class="navbtn" id="nav-bookmarks" data-route="bookmarks">Bookmarks</button>
    </nav>
    <button class="winbtn gear" id="btn-settings" title="Settings">&#9881;</button>
    <button class="winbtn" id="btn-minimize" title="Minimize">&#8211;</button>
    <button class="winbtn close" id="btn-close" title="Close">&#10005;</button>
  </div>
```

- [ ] **Step 2: Add the route container**

After `route-settings`, before `route-firstrun`:

```html
  <div class="route" id="route-bookmarks">
    <div class="settings">
      <section class="card">
        <h2>EVE bookmark hotkeys</h2>
        <div class="row">
          <span class="lab">Enable</span>
          <label><input type="checkbox" id="eve-enabled"> Register hotkeys in EVE</label>
        </div>
        <div class="row"><span class="lab"></span>
          <span class="hint" id="eve-engine-state">Not running</span></div>
        <div class="row"><span class="lab"></span>
          <button id="eve-import">Import from an existing helper…</button></div>
      </section>

      <section class="card">
        <h2>Root</h2>
        <div class="row">
          <span class="lab">Set root</span>
          <input type="text" id="eve-root-input" placeholder="J123456">
          <button id="eve-set-root">Set</button>
          <button id="eve-clear-root">Clear</button>
        </div>
      </section>

      <section class="card">
        <h2>EVE windows</h2>
        <p class="hint">Hotkeys only fire while one of these windows is active.</p>
        <div id="eve-windows"></div>
      </section>

      <section class="card">
        <h2>Keybinds</h2>
        <p class="hint" id="eve-bind-warning" hidden></p>
        <div id="eve-binds"></div>
      </section>
    </div>
  </div>
```

- [ ] **Step 3: Extend the router**

In `app.js`, `WM.route` gains the entry and the nav toggles:

```javascript
  WM.route = function (name) {
    var routes = { main: 'route-main', settings: 'route-settings',
                   firstrun: 'route-firstrun',
                   bookmarks: 'route-bookmarks' };
    Object.keys(routes).forEach(function (key) {
      WM.el(routes[key]).classList.toggle('active', key === name);
    });
    Array.prototype.forEach.call(
      document.querySelectorAll('.navbtn'), function (btn) {
        btn.classList.toggle('active', btn.dataset.route === name);
      });
    WM.el('btn-settings').classList.toggle('active', name === 'settings');
    // First run is not dismissable, so neither the gear nor the
    // destinations are offered: there is nowhere else to go yet.
    WM.el('btn-settings').hidden = (name === 'firstrun');
    WM.el('routenav').hidden = (name === 'firstrun');
    WM.current_route = name;
    document.dispatchEvent(new CustomEvent('wm:route', { detail: name }));
  };
```

and the wiring, replacing the `route-label` reference:

```javascript
  Array.prototype.forEach.call(
    document.querySelectorAll('.navbtn'), function (btn) {
      btn.addEventListener('click', function () {
        WM.route(btn.dataset.route);
      });
    });
```

Note the settings toggle keeps returning to `main` only when it is showing settings; change it to return to the last non-settings route:

```javascript
  WM.el('btn-settings').addEventListener('click', function () {
    WM.route(WM.current_route === 'settings'
             ? (WM.last_destination || 'main') : 'settings');
  });
```

recording `WM.last_destination = name` inside `WM.route` when `name` is `main` or `bookmarks`.

- [ ] **Step 4: Style it**

In `style.css`, beside the existing `.winbtn` rules:

```css
/* Peer destinations, visually distinct from the window actions on the
   right. Every pixel here is drag surface given up, so this stays tight;
   past about four destinations the 44px bar needs rethinking. */
.routenav { display: flex; gap: 2px; align-items: center; flex: none; }
.navbtn {
  background: none; border: 0; color: var(--fg-dim);
  font: inherit; font-size: 12px; letter-spacing: .04em;
  padding: 5px 10px; border-radius: 5px; cursor: pointer;
}
.navbtn:hover { color: var(--fg); background: var(--bg-hover); }
.navbtn.active { color: var(--fg); background: var(--bg-active); }
```

Use whatever the existing token names are; do not introduce new colour literals.

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/web/index.html obs_youtube_uploader/web/app.js obs_youtube_uploader/web/style.css
git commit -m "feat(ui): Bookmarks destination and title-bar navigation"
```

---

### Task 21: The Bookmarks route

**Files:**
- Create: `obs_youtube_uploader/web/bookmarks.js`
- Modify: `obs_youtube_uploader/web/index.html` (script tag)

The page holds no mapping table and makes no judgements — it captures, sends, and renders what Python returns.

- [ ] **Step 1: Write the module**

```javascript
/* FlyGD Wingman — the Bookmarks route.
 *
 * Deliberately dumb. Every decision about a key -- what it means, whether
 * it is legal, whether it collides -- happens in Python, because this repo
 * has no way to test JavaScript (webview-replatform-design.md:545). This
 * file captures events, sends them, and renders the answer.
 */
(function () {
  'use strict';

  var state = null;
  var capturing = null;

  function send(section) {
    WM.send('save_bookmarks', section).then(render);
  }

  function render(payload) {
    if (!payload) return;
    state = payload;
    WM.el('eve-enabled').checked = !!payload.settings.enabled;
    renderWindows();
    renderBinds();
  }

  function renderWindows() {
    var host = WM.el('eve-windows');
    host.textContent = '';
    var live = state.windows || [];
    var known = state.settings.windows || {};
    // Titles that are enabled but not currently running still matter: the
    // client may simply not be open yet, and dropping them would silently
    // disable a character's hotkeys.
    var titles = live.slice();
    Object.keys(known).forEach(function (t) {
      if (titles.indexOf(t) === -1) titles.push(t);
    });
    if (!titles.length) {
      host.appendChild(WM.make('p', 'hint', 'No EVE windows found.'));
      return;
    }
    titles.sort().forEach(function (title) {
      var row = WM.make('div', 'row');
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = !!known[title];
      box.addEventListener('change', function () {
        var next = JSON.parse(JSON.stringify(state.settings));
        next.windows[title] = box.checked;
        send(next);
      });
      var label = WM.make('label', null, ' ' + title);
      label.prepend(box);
      if (live.indexOf(title) === -1) {
        label.appendChild(WM.make('span', 'hint', ' (not running)'));
      }
      row.appendChild(label);
      host.appendChild(row);
    });
  }

  function renderBinds() {
    var host = WM.el('eve-binds');
    host.textContent = '';
    var collisions = state.collisions || {};
    var clashing = {};
    Object.keys(collisions).forEach(function (combo) {
      collisions[combo].forEach(function (id) { clashing[id] = combo; });
    });

    var warn = WM.el('eve-bind-warning');
    var names = Object.keys(collisions);
    warn.hidden = names.length === 0;
    if (names.length) {
      warn.textContent = 'Two actions share the same key: ' +
        names.join(', ') + '. Only one of them will work.';
    }

    state.order.forEach(function (id) {
      var row = WM.make('div', 'row');
      row.appendChild(WM.make('span', 'lab', state.labels[id]));

      var button = WM.make('button', 'bindbtn',
                           state.displays[id] || 'Not set');
      if (clashing[id]) button.classList.add('clash');
      button.addEventListener('click', function () { beginCapture(id, button); });
      row.appendChild(button);

      var clear = WM.make('button', 'linkbtn', 'Clear');
      clear.addEventListener('click', function () { setBind(id, ''); });
      row.appendChild(clear);

      // Manual entry: the escape hatch for non-US layouts, where the
      // event.code table maps a physical key to the wrong character. The
      // typed string is validated by the same Python rules as capture, so
      // the two cannot disagree.
      var typed = WM.make('button', 'linkbtn', 'Type…');
      typed.addEventListener('click', function () {
        var text = window.prompt(
          'AutoHotkey hotkey for "' + state.labels[id] + '"\n' +
          '^ = Ctrl, ! = Alt, + = Shift, # = Win. Example: ^+s',
          state.settings.keybinds[id] || '');
        if (text === null) return;
        WM.send('parse_bind', text).then(function (result) {
          if (!result) return;
          if (result.error) {
            WM.send('alert_import',
                    'That is not a hotkey AutoHotkey can register.');
            return;
          }
          setBind(id, result.ahk);
        });
      });
      row.appendChild(typed);

      host.appendChild(row);
    });
  }

  function beginCapture(id, button) {
    capturing = { id: id, button: button };
    button.textContent = 'Press a key…';
    button.classList.add('capturing');
  }

  function endCapture() {
    if (!capturing) return;
    capturing.button.classList.remove('capturing');
    capturing = null;
    renderBinds();
  }

  function setBind(id, ahk) {
    var next = JSON.parse(JSON.stringify(state.settings));
    next.keybinds[id] = ahk;
    send(next);
  }

  document.addEventListener('keydown', function (event) {
    if (!capturing) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.key === 'Escape') { endCapture(); return; }
    WM.send('capture_bind', {
      ctrl: event.ctrlKey, alt: event.altKey,
      shift: event.shiftKey, meta: event.metaKey, code: event.code
    }).then(function (result) {
      // A modifier-only press is not an error the user needs told about --
      // they are still reaching for the combination.
      if (!result || result.error === 'modifier-only') return;
      var id = capturing.id;
      endCapture();
      if (result.error) return;
      setBind(id, result.ahk);
    });
  }, true);

  WM.el('eve-enabled').addEventListener('change', function () {
    var next = JSON.parse(JSON.stringify(state.settings));
    next.enabled = WM.el('eve-enabled').checked;
    send(next);
  });

  WM.el('eve-set-root').addEventListener('click', function () {
    var value = WM.el('eve-root-input').value.trim();
    if (!value) return;
    WM.send('eve_command', 'set_root', value);
  });

  WM.el('eve-clear-root').addEventListener('click', function () {
    WM.send('eve_command', 'clear_root');
  });

  WM.el('eve-import').addEventListener('click', function () {
    WM.send('import_bookmarks').then(function (result) {
      if (!result || !result.ok) return;
      var lines = [];
      if (result.discarded.length) {
        lines.push('These no longer exist and were not imported: ' +
                   result.discarded.join(', ') + '.');
      }
      result.notes.forEach(function (note) { lines.push(note); });
      if (lines.length) WM.send('alert_import', lines.join('\n\n'));
      WM.send('get_bookmarks').then(render);
    });
  });

  WM.handle('onBookmarks', render);

  document.addEventListener('wm:route', function (event) {
    // Refreshed on entry rather than polled: the EVE window list changes
    // when clients open and close, which is not something worth a timer.
    if (event.detail === 'bookmarks') {
      WM.send('get_bookmarks').then(render);
    }
  });
}());
```

- [ ] **Step 2: Add the alert helper to `api.py`**

```python
    def alert_import(self, body: str) -> None:
        """Report what an import changed. Uses the existing dialog layer."""
        self._alert("info", "Import complete", str(body))
```

- [ ] **Step 3: Add the script tag**

In `index.html`, beside the other module scripts, after `app.js`:

```html
  <script src="bookmarks.js"></script>
```

- [ ] **Step 4: Commit**

```bash
git add obs_youtube_uploader/web/bookmarks.js obs_youtube_uploader/web/index.html obs_youtube_uploader/ui/api.py
git commit -m "feat(ui): the Bookmarks configuration route"
```

---

### Task 22: Status bar segment

**Files:**
- Modify: `obs_youtube_uploader/web/index.html`, `web/style.css`
- Create: the handler inside `web/bookmarks.js`

- [ ] **Step 1: Add the segment**

`index.html`, inside `.statusbar`, before `#status`:

```html
      <span class="evestat" id="evestat" hidden>
        <span class="evelabel">SIG</span><span id="eve-sig">—</span>
        <span class="evelabel">ROOT</span><span id="eve-root">—</span>
        <span class="evelabel">NEXT</span><span id="eve-next">—</span>
        <span class="evewarn" id="eve-warn" hidden>⚠</span>
      </span>
```

- [ ] **Step 2: Render it**

Append to `bookmarks.js`:

```javascript
  WM.handle('onEveStatus', function (payload) {
    var host = WM.el('evestat');
    // Hidden entirely when off, so nothing changes for users who never
    // turn the feature on.
    host.hidden = (payload.state === 'off');
    if (payload.state === 'off') return;

    var live = payload.state === 'running';
    // Values are shown ONLY while running. A stopped or stale engine
    // leaves its last status file on disk, and a plausible-looking dead
    // root system is worse than no readout -- it gets acted on.
    WM.el('eve-sig').textContent = live && payload.sig ? payload.sig : '—';
    WM.el('eve-root').textContent = live && payload.root ? payload.root : '—';
    WM.el('eve-next').textContent = live && payload.next_num
      ? payload.next_num + ' / ' + (payload.next_alpha || '—') : '—';

    var warn = WM.el('eve-warn');
    var failed = payload.failed_binds || [];
    warn.hidden = failed.length === 0;
    warn.title = failed.length
      ? failed.length + ' hotkey(s) failed to register — see Bookmarks'
      : '';

    var label = { stopped: 'Stopped', stale: 'Not responding',
                  running: 'Running' }[payload.state] || '';
    var stateEl = WM.el('eve-engine-state');
    if (stateEl) stateEl.textContent = label;
    host.classList.toggle('degraded', !live);
  });
```

- [ ] **Step 3: Style it**

```css
/* Second segment in the status bar. Yields to upload progress at narrow
   widths: an upload in flight is the more urgent of the two. */
.evestat { display: flex; gap: 6px; align-items: baseline; flex: 0 1 auto;
           min-width: 0; overflow: hidden; white-space: nowrap; }
.evelabel { color: var(--fg-dim); font-size: 10px; letter-spacing: .08em; }
.evestat.degraded { opacity: .5; }
@media (max-width: 720px) { .evestat { display: none; } }
```

- [ ] **Step 4: Commit**

```bash
git add obs_youtube_uploader/web/index.html obs_youtube_uploader/web/style.css obs_youtube_uploader/web/bookmarks.js
git commit -m "feat(ui): EVE status segment in the global status bar"
```

---

## Phase E — Packaging (Tasks 23-26)

### Task 23: Fetch the interpreter

**Files:**
- Create: `packaging/fetch_autohotkey.py`
- Test: `tests/test_fetch_autohotkey.py`

- [ ] **Step 1: Write the module**

Mirror `fetch_ffmpeg.py` exactly — pinned URL, pinned SHA256, `.autohotkey-version` sidecar so a bumped pin cannot silently keep shipping the old binary:

```python
# packaging/fetch_autohotkey.py
"""Download and verify the AutoHotkey v1.1 interpreter at build time.

Mirrors fetch_ffmpeg.py. v1.1 specifically: the vendored engine is v1
syntax, and v2 is a different, incompatible language.
"""
import hashlib
import io
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# Update URL and SHA256 together, never separately.
AHK_URL = ("https://github.com/AutoHotkey/AutoHotkey/releases/download/"
           "v1.1.37.02/AutoHotkey_1.1.37.02.zip")
AHK_SHA256 = "REPLACE_WITH_MEASURED_DIGEST"
OUT_DIR = Path(__file__).parent / "bin"
WANTED = ("AutoHotkeyU64.exe",)
VERSION_FILE = OUT_DIR / ".autohotkey-version"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if (
        all((OUT_DIR / name).exists() for name in WANTED)
        and VERSION_FILE.exists()
        and VERSION_FILE.read_text().strip() == AHK_SHA256
    ):
        print(f"AutoHotkey already present and matches pin {AHK_SHA256}; skipping")
        return 0

    print(f"Downloading {AHK_URL}")
    try:
        with urllib.request.urlopen(AHK_URL) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError) as exc:
        print(f"ERROR: download failed: {exc}")
        return 1

    digest = hashlib.sha256(payload).hexdigest()
    if AHK_SHA256 == "REPLACE_WITH_MEASURED_DIGEST":
        print(f"ERROR: pin the checksum first. Downloaded archive is sha256={digest}")
        return 1
    if digest != AHK_SHA256:
        print(f"ERROR: checksum mismatch\n  expected {AHK_SHA256}\n  got      {digest}")
        return 1

    extracted = 0
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for member in archive.namelist():
                # Basename only: a malicious member path such as
                # "../../evil/AutoHotkeyU64.exe" cannot escape OUT_DIR
                # because Path(member).name discards every directory
                # component before the join.
                name = Path(member).name
                if name in WANTED:
                    (OUT_DIR / name).write_bytes(archive.read(member))
                    print(f"  extracted {name}")
                    extracted += 1
    except zipfile.BadZipFile as exc:
        print(f"ERROR: downloaded archive is not a valid zip file: {exc}")
        return 1

    if extracted != len(WANTED):
        print(f"ERROR: expected {len(WANTED)} binaries, extracted {extracted}")
        return 1
    VERSION_FILE.write_text(AHK_SHA256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The `REPLACE_WITH_MEASURED_DIGEST` guard is deliberate and matches `fetch_ffmpeg.py:47`: the script refuses to run until the digest is pinned, and Step 4's test fails while the placeholder remains.

- [ ] **Step 2: Measure and pin the digest**

```bash
curl -sL "$AHK_URL" -o /tmp/ahk.zip && sha256sum /tmp/ahk.zip
```

Paste the result into `AHK_SHA256`. **Do not leave the placeholder** — a build with an unverified download is the thing this file exists to prevent.

- [ ] **Step 3: Check whether the binary is Authenticode-signed**

```bash
cd /tmp && unzip -o ahk.zip AutoHotkeyU64.exe && osslsigncode verify AutoHotkeyU64.exe 2>&1 | head -20
```

Record the answer in the commit message. If it is signed, Task 24 adds the CI check; if not, Task 24 records the omission as deliberate. This is the open question the spec flagged.

- [ ] **Step 4: Test and commit**

```python
# tests/test_fetch_autohotkey.py
"""The pin is the security boundary for a binary that installs a keyboard
hook. A placeholder digest shipping to CI would defeat it entirely."""
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "packaging" / "fetch_autohotkey.py"


def test_digest_is_a_real_sha256():
    text = SOURCE.read_text()
    match = re.search(r'AHK_SHA256 = "([^"]+)"', text)
    assert match, "AHK_SHA256 not found"
    assert re.fullmatch(r"[0-9a-f]{64}", match.group(1)), \
        "AHK_SHA256 is not a measured digest"


def test_url_and_wanted_agree_on_v1():
    text = SOURCE.read_text()
    assert "v1.1" in text
    assert "AutoHotkeyU64.exe" in text
```

```bash
pytest tests/test_fetch_autohotkey.py -q
git add packaging/fetch_autohotkey.py tests/test_fetch_autohotkey.py
git commit -m "build: fetch and pin the AutoHotkey v1.1 interpreter"
```

---

### Task 24: Bundle and assert

**Files:**
- Modify: `packaging/uploader.spec`, `.github/workflows/build.yml`, `.github/workflows/release.yml`

- [ ] **Step 1: Add both artifacts to the spec**

```python
    binaries=[
        (str(BIN / "ffmpeg.exe"), "bin"),
        (str(BIN / "ffprobe.exe"), "bin"),
        # v1.1 interpreter. Bundled-only by design: paths.engine_exe()
        # deliberately does not fall back to PATH, because a user's
        # AutoHotkey v2 handed a v1 script fails with parse errors that
        # read like a bug in the script.
        (str(BIN / "AutoHotkeyU64.exe"), "bin"),
    ],
```

and in `datas`, beside the `web/` entry:

```python
        # The engine is data, not code -- modulegraph cannot see it, and
        # PyInstaller exits 0 when a datas entry fails to collect. Without
        # the post-build assertion below, a missing script produces a green
        # build and an engine that never starts.
        (str(ROOT / "obs_youtube_uploader" / "engine"), "engine"),
```

- [ ] **Step 2: Add the collection assertion**

In both workflows, beside the existing `web/` assertion:

```yaml
      - name: Verify the bookmark engine was collected
        shell: pwsh
        run: |
          $script = "dist/OBSYouTubeUploader/_internal/engine/eve_bookmarks.ahk"
          if (-not (Test-Path $script)) {
            throw "engine script missing from the bundle - PyInstaller exits 0 when datas fail to collect"
          }
          $exe = "dist/OBSYouTubeUploader/_internal/bin/AutoHotkeyU64.exe"
          if (-not (Test-Path $exe)) { throw "AutoHotkey interpreter missing from the bundle" }
```

- [ ] **Step 3: Add the signature check, or record its absence**

If Task 23 found the binary signed, mirror `build.yml:155-177`:

```yaml
      - name: Verify AutoHotkey is signed by the AutoHotkey Foundation
        shell: pwsh
        run: |
          $exe = "packaging/bin/AutoHotkeyU64.exe"
          $sig = Get-AuthenticodeSignature $exe
          Write-Host "Subject: $($sig.SignerCertificate.Subject)"
          if ($sig.Status -ne "Valid") { throw "AutoHotkey signature is $($sig.Status), not Valid - do NOT ship this" }
          if ($sig.SignerCertificate.Subject -notmatch "AutoHotkey") {
            throw "AutoHotkey is signed by $($sig.SignerCertificate.Subject), which is not upstream"
          }
```

If it is **not** signed, add this comment instead of a check, so the omission is a decision on the record rather than an oversight:

```yaml
      # No signature check for AutoHotkeyU64.exe: upstream v1.1 releases are
      # not Authenticode-signed (verified <date>). The SHA256 pin in
      # packaging/fetch_autohotkey.py is the only integrity guarantee for
      # this binary. Revisit if upstream starts signing.
```

- [ ] **Step 4: Commit**

```bash
git add packaging/uploader.spec .github/workflows/build.yml .github/workflows/release.yml
git commit -m "build: bundle the engine and assert it was collected"
```

---

### Task 25: GPL notices

**Files:**
- Create: `THIRD-PARTY-NOTICES.md`
- Modify: `packaging/uploader.spec`, `README.md`

A README line is not a written offer. Both bundled binaries are GPL and neither ships with source today.

- [ ] **Step 1: Write the notice**

```markdown
# Third-party software in FlyGD Wingman

FlyGD Wingman itself is MIT (see LICENSE). It bundles the following
programs, which are licensed separately.

## FFmpeg

Version: 7.1 (`ffmpeg-7.1-essentials_build`)
Licence: GNU General Public License v2 or later
Source: https://github.com/GyanD/codexffmpeg/releases/tag/7.1

## AutoHotkey

Version: 1.1.37.02
Licence: GNU General Public License v2
Source: https://github.com/AutoHotkey/AutoHotkey/releases/tag/v1.1.37.02

## Written offer

For either program, we will provide the complete corresponding source code
for the exact version distributed with this application, on request, for a
period of three years from the date you received it. Contact
technical@zoolanders.vip.

The versions above are the exact versions shipped. Pinning matters: an offer
of "the latest upstream release" would not correspond to what you received.
```

- [ ] **Step 2: Ship it in the installed tree**

In `uploader.spec` `datas`:

```python
        # Must reach the installed tree, not just the repository: the offer
        # has to travel with the binaries it covers.
        (str(ROOT / "THIRD-PARTY-NOTICES.md"), "."),
```

- [ ] **Step 3: Point at it from the README**

Under "License and affiliations":

```markdown
Released under the [MIT License](LICENSE).

FFmpeg and AutoHotkey are bundled and are licensed under the GPL. See
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for versions, sources, and
a written offer of source.
```

- [ ] **Step 4: Commit**

```bash
git add THIRD-PARTY-NOTICES.md packaging/uploader.spec README.md
git commit -m "docs: written offer of source for the bundled GPL binaries"
```

---

### Task 26: Smoke checklist

**Files:**
- Modify: `docs/smoke-checklist.md`

The engine cannot be tested. This is the whole verification story for it.

- [ ] **Step 1: Append the section**

```markdown
## EVE bookmark hotkeys

Requires a Windows machine with EVE running. None of this is covered by
pytest — the engine is AutoHotkey.

- [ ] Bookmarks appears in the title bar; the window still drags by the
      wordmark area
- [ ] With the feature off, the status bar shows no EVE segment
- [ ] Enabling starts the engine; the status bar segment appears
- [ ] Hotkeys fire in an enabled EVE window and do nothing in an unenabled one
- [ ] **A bound key does nothing when a non-EVE window is focused** — no bind is
      global any more, and registration happens inside a function called while
      an `IfWinActive` criterion is active. If that criterion does not carry
      into the function, every bind registers globally and fires everywhere.
      Nothing in the repository can test this; confirm it by hand.
- [ ] **Rebinding a window-scoped hotkey stops the old key firing** — the
      direct test of the teardown repair, and the bug that shipped for years
- [ ] Disabling a window stops its hotkeys firing, within ~10s
- [ ] Every finisher produces the correct Flygd/ABH name (Protean removal)
- [ ] Home-mode bookmarks number from `.0`
- [ ] Deliberately binding two actions to one key shows the collision warning
- [ ] Binding a key another application owns shows a registration failure,
      not a silently dead key
- [ ] Set Root and Clear Root from the route change the status bar values
- [ ] A second action taken immediately is not lost
- [ ] Importing an existing `eve_bookmark_helper.ini` reproduces that setup
      and reports what it discarded
- [ ] Config changes apply within 10s without losing root or used slots
- [ ] No console window flashes when the engine starts
- [ ] Killing Wingman via Task Manager leaves the engine running; restarting
      Wingman terminates it
- [ ] With the pid file pointing at an unrelated live process, starting
      Wingman does **not** kill it
```

- [ ] **Step 2: Run the full suite and commit**

```bash
pytest -q
git add docs/smoke-checklist.md
git commit -m "docs: smoke checks for the bookmark engine"
```

---

## Verification

After Task 26:

1. `pytest -q` — the 607 existing tests plus roughly 90 new ones
2. Read the full diff of `obs_youtube_uploader/engine/eve_bookmarks.ahk` against `111unified.ahk`. This is the part no test covers; it deserves the most reviewer attention in the whole change.
3. Work the smoke checklist on Windows with EVE running.
4. Confirm `THIRD-PARTY-NOTICES.md` reached `dist/OBSYouTubeUploader/`.



