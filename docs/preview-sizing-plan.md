# Preview Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A preview can be made to match its client's shape exactly (drag),
sized to an exact number (type), placed without magnetism (toggle), or put
back (reset).

**Architecture:** All the arithmetic goes into pure functions in
`preview/geometry.py` that CI runs on Linux; the Win32 half stays on the
preview thread behind posted messages, following `set_hotkeys`' existing
shape. The page gains one row control and two card controls, all committing
through per-field bridge endpoints.

**Tech Stack:** Python 3.11+ / ctypes / pywebview 6.2.1 (pinned), plain
HTML/CSS/ES5 with no build step, pytest, ruff.

**Spec:** `docs/preview-sizing-design.md`

## Global Constraints

- **Wingman must never move or resize a real EVE client window.** Previews
  only. This outranks every requirement below.
- **Every non-method attribute on `Api` must be underscore-prefixed.**
  pywebview walks public attributes; a public one holding a window recurses
  until `RecursionError` kills the process ~8s after launch.
- **Nothing in the test suite renders the page.** A handler that throws takes
  every registration below it down silently. Assume a touched screen is
  broken until opened by hand.
- **Checkboxes must use the `.check`/`.box` wrapper.** A bare input is a
  white Win32 widget on a dark card.
- **Never `window.confirm/prompt/alert`.** Use `WM.confirm` / `WM.prompt`.
- **Colours come only from `:root` tokens.**
- **Derived values (counts, key lists) must be derived or asserted in a
  test, never retyped.**
- **`ruff format` and `ruff check` gate CI.** Line length is 88; `E501` is
  off because the formatter owns it.
- Run tests with `uv run --no-sync python -m pytest tests/`.

---

## File Structure

**Created:**
- None. Every change lands in an existing module.

**Modified:**
- `obs_youtube_uploader/preview/geometry.py` — gains `parse_size` and
  `lock_to_aspect`. Both pure; this is where the testable arithmetic lives.
- `obs_youtube_uploader/preview/window.py` — `resize_result` gains an
  aspect; `PreviewWindow` gains `_source_aspect()`, a `snap` attribute, and
  captures aspect + chrome at drag start.
- `obs_youtube_uploader/preview/store.py` — gains `clear()`, the one
  wholesale write this class allows.
- `obs_youtube_uploader/preview/host.py` — gains `resize_preview()`,
  `reset_layouts()`, `client_sizes()`, two message handlers, and a snap
  push in `_restyle`.
- `obs_youtube_uploader/preview/win32.py` — two new `WM_APP_*` constants.
- `obs_youtube_uploader/settings.py` — the `preview.snap` key and its
  validation.
- `obs_youtube_uploader/__main__.py` — passes the `snap` callable and
  `clear_layouts=store.clear` into `PreviewHost`.
- `obs_youtube_uploader/ui/api.py` — four endpoints and a widened payload.
- `obs_youtube_uploader/web/{index.html,style.css,previews.js,settings.js,dev.js}`
- `docs/smoke-checklist.md`, `docs/preview-roadmap.md`

**Tests:**
- `tests/test_preview_geometry.py`, `tests/test_preview_window.py`,
  `tests/test_preview_store.py`, `tests/test_settings_preview.py`,
  `tests/test_api_settings_fields.py`

---

### Task 1: `geometry.parse_size`

**Files:**
- Modify: `obs_youtube_uploader/preview/geometry.py`
- Test: `tests/test_preview_geometry.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_size(text) -> tuple[int, int] | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preview_geometry.py`:

```python
def test_parse_size_accepts_the_obvious_spelling():
    assert g.parse_size("1280x720") == (1280, 720)


def test_parse_size_tolerates_spacing_and_capital_x():
    assert g.parse_size("  640 X 360 ") == (640, 360)
    assert g.parse_size("640×360") == (640, 360)


def test_parse_size_rejects_junk_rather_than_raising():
    """Same contract as gestures.parse: the caller gets None, never an
    exception, because this runs on typed input."""
    for text in ("", "x", "640", "640x", "axb", "640x720x480", None, 640):
        assert g.parse_size(text) is None


def test_parse_size_rejects_zero_and_negative():
    assert g.parse_size("0x720") is None
    assert g.parse_size("-640x360") is None


def test_parse_size_does_not_clamp():
    """The floor belongs to the caller, which knows the chrome. A parser
    that silently repaired a typo would hand back a size nobody typed."""
    assert g.parse_size("1x1") == (1, 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-sync python -m pytest tests/test_preview_geometry.py -k parse_size -v`
Expected: FAIL, `AttributeError: module ... has no attribute 'parse_size'`

- [ ] **Step 3: Implement**

Add `import re` to the top of `geometry.py`, then append:

```python
_SIZE_RE = re.compile(r"^\s*(\d{1,5})\s*[xX×]\s*(\d{1,5})\s*$")


def parse_size(text):
    """Parse "1280x720" into a (w, h) pair, or None.

    Same contract as gestures.parse: None for anything not accepted, never
    an exception. Deliberately does NOT clamp -- the floor belongs to the
    caller, which knows the chrome, and a parser that silently repaired a
    typo would hand back a size the user never typed.
    """
    if not isinstance(text, str):
        return None
    match = _SIZE_RE.match(text)
    if not match:
        return None
    w, h = int(match.group(1)), int(match.group(2))
    if w <= 0 or h <= 0:
        return None
    return w, h
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-sync python -m pytest tests/test_preview_geometry.py -k parse_size -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/geometry.py tests/test_preview_geometry.py
git commit -m "Parse a typed preview size"
```

---

### Task 2: `geometry.lock_to_aspect`

The spec's central arithmetic, and the piece an earlier draft got wrong by
treating the chrome as a constant.

**Files:**
- Modify: `obs_youtube_uploader/preview/geometry.py`
- Test: `tests/test_preview_geometry.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `lock_to_aspect(w, h, aspect, chrome, min_size) -> tuple[int, int]`,
  taking and returning **window** sizes; `chrome` is `(dw, dh)`.

- [ ] **Step 1: Write the failing tests**

```python
LABELS_ON = (4, 34)  # BORDER * 2, BORDER * 2 + LABEL_H
LABELS_OFF = (4, 4)  # the same window with show_labels off
FLOOR = (120, 90)


def _picture(size, chrome):
    return size[0] - chrome[0], size[1] - chrome[1]


def test_lock_to_aspect_matches_the_picture_not_the_window():
    """The label band is not part of the picture. Locking the WINDOW to
    16:9 leaves the picture stretched by exactly the band's height."""
    w, h = g.lock_to_aspect(640, 999, 16 / 9, LABELS_ON, FLOOR)
    pw, ph = _picture((w, h), LABELS_ON)
    assert abs(pw / ph - 16 / 9) < 0.01


def test_lock_to_aspect_uses_the_chrome_it_is_given():
    """Labels off removes 30px of band, so the same window width needs a
    different window height for the same picture shape. A fixed chrome
    distorts the picture for everyone who turned labels off -- silently,
    while the control reports success."""
    on = g.lock_to_aspect(640, 999, 16 / 9, LABELS_ON, FLOOR)
    off = g.lock_to_aspect(640, 999, 16 / 9, LABELS_OFF, FLOOR)
    assert on != off
    assert on[1] - off[1] == 30


def test_lock_to_aspect_lets_a_vertical_drag_do_something():
    """Driving from width alone would make a downward drag inert."""
    grown = g.lock_to_aspect(640, 900, 16 / 9, LABELS_ON, FLOOR)
    assert grown[0] > 640


def test_lock_to_aspect_applies_the_floor_without_distorting():
    """The clamp must not be the thing that breaks the ratio."""
    w, h = g.lock_to_aspect(1, 1, 16 / 9, LABELS_ON, FLOOR)
    assert w >= FLOOR[0] and h >= FLOOR[1]
    pw, ph = _picture((w, h), LABELS_ON)
    assert abs(pw / ph - 16 / 9) < 0.01


def test_lock_to_aspect_without_an_aspect_only_floors():
    """None is the character-select and client-gone fallback: today's
    freeform behaviour, unchanged."""
    assert g.lock_to_aspect(500, 400, None, LABELS_ON, FLOOR) == (500, 400)
    assert g.lock_to_aspect(10, 10, None, LABELS_ON, FLOOR) == (120, 90)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-sync python -m pytest tests/test_preview_geometry.py -k lock_to_aspect -v`
Expected: FAIL, `AttributeError: ... has no attribute 'lock_to_aspect'`

- [ ] **Step 3: Implement**

Append to `geometry.py`:

```python
def lock_to_aspect(w, h, aspect, chrome, min_size):
    """The nearest window size whose PICTURE is *aspect* wide per unit tall.

    *chrome* is (dw, dh): the pixels the window spends on border and label
    band. It is a parameter and not a constant because the band is
    LABEL_H tall or zero depending on a live setting -- a fixed value
    distorts the picture for everyone who turned labels off, silently,
    while the control reports success.

    Both drag axes stay live: driving from width alone would make a
    mostly-vertical drag do nothing, so the picture width is the larger of
    the one implied by w and the one implied by h.

    The floor is applied in PICTURE space and the height re-derived from
    it, so clamping cannot itself distort the result.
    """
    dw, dh = chrome
    if not aspect or aspect <= 0:
        return max(min_size[0], w), max(min_size[1], h)
    pw = max(1, w - dw)
    ph = max(1, h - dh)
    pw = max(pw, ph * aspect)
    pw = max(pw, min_size[0] - dw, 1)
    floor_h = max(1, min_size[1] - dh)
    if pw / aspect < floor_h:
        pw = floor_h * aspect
    return int(round(pw + dw)), int(round(pw / aspect + dh))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-sync python -m pytest tests/test_preview_geometry.py -v`
Expected: PASS (all, including the pre-existing geometry tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/geometry.py tests/test_preview_geometry.py
git commit -m "Lock a window size to its picture's aspect ratio"
```

---

### Task 3: The drag handle keeps the client's shape

**Files:**
- Modify: `obs_youtube_uploader/preview/window.py`
- Test: `tests/test_preview_window.py`

**Interfaces:**
- Consumes: `geometry.lock_to_aspect` (Task 2).
- Produces: `resize_result(start, current, rect, min_size=MIN_SIZE,
  aspect=None, chrome=(0, 0))`; `PreviewWindow._source_aspect() -> float | None`;
  `PreviewWindow._start_aspect` / `_start_chrome`, set at `WM_LBUTTONDOWN`.

- [ ] **Step 1: Write the failing tests**

```python
def test_resize_result_without_an_aspect_is_unchanged():
    """The existing signature must keep working: this is the fallback for
    a client at character select or one that quit mid-drag."""
    out = window.resize_result((100, 100), (150, 130), R, min_size=(80, 60))
    assert out.w == R.w + 50 and out.h == R.h + 30


def test_resize_result_with_an_aspect_locks_the_picture():
    out = window.resize_result(
        (0, 0), (200, 0), R, min_size=(80, 60), aspect=16 / 9, chrome=(4, 34)
    )
    assert abs((out.w - 4) / (out.h - 34) - 16 / 9) < 0.01


def test_resize_result_respects_the_label_band_being_off():
    """Same drag, labels off: the window is 30px shorter for the same
    picture. window.py reads _label_h() live at every other call site."""
    on = window.resize_result(
        (0, 0), (200, 0), R, min_size=(80, 60), aspect=16 / 9, chrome=(4, 34)
    )
    off = window.resize_result(
        (0, 0), (200, 0), R, min_size=(80, 60), aspect=16 / 9, chrome=(4, 4)
    )
    assert on.h - off.h == 30
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-sync python -m pytest tests/test_preview_window.py -k resize_result -v`
Expected: FAIL, `TypeError: resize_result() got an unexpected keyword argument 'aspect'`

- [ ] **Step 3: Replace `resize_result`**

In `window.py`, replace the existing `resize_result` with:

```python
def resize_result(start, current, rect, min_size=MIN_SIZE, aspect=None, chrome=(0, 0)):
    """New rect for a resize drag. Top-left is the anchor and never moves.

    With *aspect* set, the PICTURE keeps that shape and *chrome* says how
    many pixels of the window are not picture. With aspect None the result
    is what it has always been -- which is also the fallback when the
    client's rect cannot be read.
    """
    dx, dy = current[0] - start[0], current[1] - start[1]
    w, h = rect.w + dx, rect.h + dy
    if aspect:
        w, h = geometry.lock_to_aspect(w, h, aspect, chrome, min_size)
        return rect._replace(w=w, h=h)
    return rect._replace(w=max(min_size[0], w), h=max(min_size[1], h))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-sync python -m pytest tests/test_preview_window.py -v`
Expected: PASS

- [ ] **Step 5: Add `_source_aspect` to `PreviewWindow`**

Add as a method on `PreviewWindow`, next to `_label_h`:

```python
    def _source_aspect(self):
        """The client area's width/height, or None if it cannot be read.

        None is routine rather than exceptional: a client sitting at character
        select, or one that quit mid-drag, has a degenerate rect. The handle
        falls back to a freeform resize rather than freezing.
        """
        import ctypes

        rect = win32.RECT()
        if not self._libs.user32.GetClientRect(self.client.hwnd, ctypes.byref(rect)):
            return None
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None
        return w / h
```

The local `import ctypes` matches this file's existing habit (`_cursor_pos`
does the same).

- [ ] **Step 6: Capture aspect and chrome at button-down**

In `_on_message`, in the `WM_LBUTTONDOWN`/`WM_RBUTTONDOWN` branch, directly
after `self._start = _cursor_pos(self._libs)`:

```python
            # Sampled once per drag, never per WM_MOUSEMOVE: that handler
            # has a documented stutter history and a WINGMAN_PREVIEW_PERF
            # harness built to measure it, and a syscall per mouse move is
            # the cost that harness exists to catch.
            self._start_aspect = self._source_aspect()
            self._start_chrome = (BORDER * 2, BORDER * 2 + self._label_h())
```

Initialise both to `None` and `(0, 0)` in `__init__` beside `_start_rect`.

- [ ] **Step 7: Use them in the resize branch**

In the `WM_MOUSEMOVE` handler, replace the resize line with:

```python
            if self._mode == "resize":
                self.move(
                    resize_result(
                        self._start,
                        cur,
                        self._start_rect,
                        aspect=self._start_aspect,
                        chrome=self._start_chrome,
                    )
                )
```

- [ ] **Step 8: Run the full suite and the formatter**

Run: `uv run --no-sync python -m pytest tests/ -q`
Run: `uv run --extra dev ruff format --check . && uv run --extra dev ruff check .`
Expected: PASS, clean

- [ ] **Step 9: Commit**

```bash
git add obs_youtube_uploader/preview/window.py tests/test_preview_window.py
git commit -m "The resize handle keeps a preview at its client's shape"
```

---

### Task 4: The snap toggle

**Files:**
- Modify: `obs_youtube_uploader/settings.py`, `obs_youtube_uploader/preview/window.py`,
  `obs_youtube_uploader/preview/host.py`, `obs_youtube_uploader/__main__.py`
- Test: `tests/test_settings_preview.py`, `tests/test_preview_window.py`

**Interfaces:**
- Consumes: nothing.
- Produces: settings key `preview.snap` (bool, default `True`);
  `PreviewWindow.snap` attribute; `PreviewHost(snap=<callable>)`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_settings_preview.py`:

```python
def test_snap_defaults_to_on():
    """On by default because it is what shipped; turning it off would
    silently change how every existing install's previews drag."""
    assert settings._preview_defaults()["snap"] is True


def test_snap_survives_a_round_trip():
    assert settings.validated_preview({"snap": False})["snap"] is False


def test_snap_falls_back_when_it_is_not_a_bool():
    assert settings.validated_preview({"snap": "yes"})["snap"] is True


def test_the_preview_defaults_are_a_fixed_point_of_their_own_validator():
    """Normalising runs on every save, so a default its own validator
    rewrites would drift the file on the first write. Named as unguarded
    in docs/preview-roadmap.md; this slice makes it cheap to add."""
    defaults = settings._preview_defaults()
    assert settings.validated_preview(defaults) == defaults
```

In `tests/test_preview_window.py`:

```python
def test_a_preview_defaults_to_snapping():
    """The attribute exists before any restyle lands, so a preview created
    between launch and the first settings push still snaps."""
    assert window.PreviewWindow.snap is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --no-sync python -m pytest tests/test_settings_preview.py -k snap tests/test_preview_window.py -k snap -v`
Expected: FAIL, `KeyError: 'snap'`

- [ ] **Step 3: Add the settings key**

In `settings.py`, inside `_preview_defaults()`, beside `show_labels`:

```python
        # On by default -- it is what shipped, and turning it off would
        # silently change how every existing install's previews drag.
        # A new key whose default matches current behaviour needs no
        # defaults_version bump: the migration exists for defaults that
        # CHANGE, and this one has no previous value to protect.
        "snap": True,
```

In `validated_preview`, beside the `restore_preview_positions` branch:

```python
    if isinstance(raw.get("snap"), bool):
        section["snap"] = raw["snap"]
```

- [ ] **Step 4: Add the window attribute and use it**

In `window.py`, as a class attribute on `PreviewWindow` beside the others:

```python
    # Class-level so a preview created before the first restyle still has
    # it. Pushed live by PreviewHost._restyle, like show_labels and locked.
    snap = True
```

In `_on_message`'s `WM_MOUSEMOVE` handler, replace the move branch:

```python
            else:
                moved = drag_target(self._start, cur, self._start_rect)
                if self.snap:
                    moved = geometry.snap(moved, self._neighbours(), self._screen())
                self.move(moved)
```

- [ ] **Step 5: Wire the host**

In `host.py`, add a `snap=None` parameter to `PreviewHost.__init__`, store it
as `self._snap`, and add:

```python
    def _snapping(self) -> bool:
        """Whether a dragged preview snaps, read live.

        Same posture as _restoring(): this runs on the preview thread
        inside the pump, so a callable that raises must not be the thing
        that kills it. Falls back to snapping -- the behaviour that
        predates the toggle.
        """
        if self._snap is None:
            return True
        try:
            return bool(self._snap())
        except Exception:
            logger.exception("Could not read preview.snap; leaving snapping on")
            return True
```

In `_restyle`, inside the loop, beside `win.locked = ...`:

```python
            win.snap = self._snapping()
```

In the `PreviewWindow.create(...)` call inside `_sweep`, pass `snap=self._snapping()`,
and add `snap=True` to `PreviewWindow.create`'s signature and to `__init__`,
assigning `self.snap = snap`.

- [ ] **Step 6: Wire `__main__`**

In `__main__.py`, beside the existing `show_labels`/`opacity`/`locked`
callables, matching `locked()`'s shape:

```python
        def snap():
            # Read live for the same reason as restore_positions: the
            # setting is changed while previews are running.
            return state.settings.get("preview", {}).get("snap", True) is not False
```

Then pass `snap=snap` to `PreviewHost(...)`.

- [ ] **Step 7: Run tests and formatter**

Run: `uv run --no-sync python -m pytest tests/ -q`
Run: `uv run --extra dev ruff format --check . && uv run --extra dev ruff check .`
Expected: PASS, clean

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/ tests/
git commit -m "preview.snap: a dragged preview can stop snapping"
```

---

### Task 5: `LayoutStore.clear()`

**Files:**
- Modify: `obs_youtube_uploader/preview/store.py`
- Test: `tests/test_preview_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `LayoutStore.clear() -> None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_clear_empties_every_saved_layout():
    live = {"preview": {"layouts": {"Alice": {"x": 1, "y": 2, "w": 3, "h": 4}}}}
    store = LayoutStore(_updater(live), timer=FakeTimer)
    store.clear()
    assert live["preview"]["layouts"] == {}


def test_clear_drops_a_pending_layout_write():
    """A drag that ended under a second ago has an unwritten entry. If the
    debounce fires after the clear it resurrects exactly one preview's old
    position -- intermittently, which is the worst way for this to fail."""
    live = {"preview": {"layouts": {}}}
    store = LayoutStore(_updater(live), timer=FakeTimer)
    store.record("Alice", Entry(Rect(1, 2, 3, 4)))
    timer = store._timer
    store.clear()
    assert timer.cancelled
    assert live["preview"]["layouts"] == {}


def test_clear_keeps_a_pending_roster_name():
    """record_character shares this one timer deliberately, so cancelling
    without draining it silently loses a character discovered moments
    before the reset -- and any binding whose row it is the reason for."""
    live = {"preview": {"layouts": {}, "seen": []}}
    store = LayoutStore(_updater(live), timer=FakeTimer)
    store.record_character("Bob")
    store.clear()
    assert live["preview"]["seen"] == ["Bob"]
```

Reuse whatever `_updater`-style context-manager helper the file already
defines for `update_settings`; do not add a second one.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --no-sync python -m pytest tests/test_preview_store.py -k clear -v`
Expected: FAIL, `AttributeError: 'LayoutStore' object has no attribute 'clear'`

- [ ] **Step 3: Implement**

Add to `LayoutStore`:

```python
    def clear(self) -> None:
        """Discard every saved layout. The one wholesale write this class allows.

        Pending LAYOUT deltas are dropped: they describe positions being
        erased anyway, and a debounce firing after the clear would resurrect
        exactly one preview's old position, intermittently.

        Pending NAMES are kept and written here. record_character shares this
        single timer deliberately (see its docstring), so cancelling without
        draining them would silently lose a character discovered moments
        before the reset -- and with it any binding whose row that character
        is the only reason to show.
        """
        with self._lock:
            self._pending = {}
            names, self._pending_names = list(self._pending_names), []
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        try:
            with self._update_settings() as live:
                section = live.setdefault("preview", {})
                section["layouts"] = {}
                for name in names:
                    bound = set(section.get("hotkeys", {}).get("characters", {}))
                    section["seen"] = roster.touch(
                        section.get("seen", []), name, protected=bound
                    )
        except OSError:
            logger.exception("Could not clear preview layouts")
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --no-sync python -m pytest tests/test_preview_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/store.py tests/test_preview_store.py
git commit -m "LayoutStore.clear: forget every saved position, keep pending names"
```

---

### Task 6: The host resizes one preview and resets them all

**Files:**
- Modify: `obs_youtube_uploader/preview/win32.py`,
  `obs_youtube_uploader/preview/host.py`, `obs_youtube_uploader/__main__.py`
- Test: `tests/test_preview_host.py`

**Interfaces:**
- Consumes: `LayoutStore.clear` (Task 5).
- Produces: `PreviewHost.resize_preview(stable_key, (w, h))`,
  `PreviewHost.reset_layouts()`, `PreviewHost.client_sizes() -> dict`,
  constructor kwarg `clear_layouts=<callable>`.

- [ ] **Step 1: Add the message constants**

In `win32.py`, beside `WM_APP_ALERT`:

```python
WM_APP_RESET_LAYOUTS = WM_APP + 5
WM_APP_RESIZE_ONE = WM_APP + 6
```

- [ ] **Step 2: Write the failing tests**

Follow the fake-libs conventions already in `tests/test_preview_host.py`.

```python
def test_resize_preview_stashes_the_payload_and_posts_only_a_signal():
    """PostMessageW carries integers only, so the size travels in a field
    under the lock -- set_hotkeys' shape."""
    host = _host()
    host.resize_preview("Alice", (640, 392))
    assert host._pending_resize == {"Alice": (640, 392)}


def test_reset_layouts_clears_saved_and_calls_the_injected_clear():
    cleared = []
    host = _host(clear_layouts=lambda: cleared.append(True))
    host._saved["Alice"] = Entry(Rect(1, 2, 3, 4))
    host._reset_layouts()
    assert cleared == [True]
    assert host._saved == {}


def test_reset_does_not_record_the_defaults_it_just_placed():
    """Writing them back would repopulate the table the reset just
    emptied -- a reset leaving the file exactly as full as it found it."""
    recorded = []
    host = _host(on_layout_changed=lambda *a: recorded.append(a))
    host._reset_layouts()
    assert recorded == []
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run --no-sync python -m pytest tests/test_preview_host.py -k "resize_preview or reset" -v`
Expected: FAIL, `AttributeError`

- [ ] **Step 4: Implement the host methods**

Add `clear_layouts=None` to `__init__`, store as `self._clear_layouts`, and
initialise `self._pending_resize = {}` and `self._client_sizes = {}` beside
`self._pending_alerts`. Then add:

```python
    def resize_preview(self, stable_key: str, size) -> None:
        """Set one preview's size on demand. Safe from any thread.

        Same shape as set_hotkeys: PostMessageW carries integers only, so the
        payload travels in a field under the lock and only the signal is
        posted.
        """
        with self._lock:
            self._pending_resize[stable_key] = (int(size[0]), int(size[1]))
        self._post(win32.WM_APP_RESIZE_ONE)

    def reset_layouts(self) -> None:
        """Forget every saved position and re-place. Safe from any thread."""
        self._post(win32.WM_APP_RESET_LAYOUTS)

    def client_sizes(self) -> dict:
        """Last sampled client-area size per character. Safe from any thread."""
        with self._lock:
            return dict(self._client_sizes)

    def _apply_resizes(self) -> None:
        with self._lock:
            pending, self._pending_resize = dict(self._pending_resize), {}
        for key, (w, h) in pending.items():
            win = self._windows.get(key)
            if win is None:
                continue
            win.move(win.rect._replace(w=w, h=h))
            # Recorded like a drag: a typed size is the user's choice and
            # must survive a restart exactly as a dragged position does.
            self._layout_changed(key, win.rect, win.locked)

    def _reset_layouts(self) -> None:
        """Clear saved layouts and re-place every open preview.

        Deliberately does NOT record the new rects. They are defaults, and
        writing them back would repopulate the very table this just cleared --
        a reset that leaves the file exactly as full as it found it.
        """
        if self._clear_layouts is not None:
            self._clear_layouts()
        self._saved.clear()
        monitors = self._monitors()
        for index, (key, win) in enumerate(self._windows.items()):
            win.move(self._resolve_rect(key, index, monitors, None))

    def _record_client_sizes(self, libs, clients) -> None:
        """Sample each client's client-area size, on the preview thread.

        Readable from the UI thread afterwards, like hotkey_status(): the page
        needs a client's shape to tell the user which size would not distort
        it, and calling GetClientRect from the bridge thread is the
        thread-affinity violation this module is organised to avoid.
        """
        import ctypes

        sizes = {}
        rect = win32.RECT()
        for key, client in clients.items():
            if libs.user32.GetClientRect(client.hwnd, ctypes.byref(rect)):
                w, h = rect.right - rect.left, rect.bottom - rect.top
                if w > 0 and h > 0:
                    sizes[key] = (w, h)
        with self._lock:
            self._client_sizes = sizes
```

- [ ] **Step 5: Handle the two messages**

In `_on_message`, beside the `WM_APP_RESTYLE` branch:

```python
        if msg == win32.WM_APP_RESIZE_ONE:
            self._apply_resizes()
            return 0
        if msg == win32.WM_APP_RESET_LAYOUTS:
            self._reset_layouts()
            return 0
```

In `_sweep`, after `clients = {...}` is built, add:

```python
        self._record_client_sizes(libs, clients)
```

- [ ] **Step 6: Wire `__main__`**

Pass `clear_layouts=store.clear` to `PreviewHost(...)`, beside the existing
`flush_layouts=store.flush`. Use the bound method, never a lambda wrapping
it — `tests/test_preview_wiring.py` records what a lazily-resolved name in a
lambda cost last time.

- [ ] **Step 7: Run tests and formatter**

Run: `uv run --no-sync python -m pytest tests/ -q`
Run: `uv run --extra dev ruff format --check . && uv run --extra dev ruff check .`
Expected: PASS, clean

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/ tests/
git commit -m "The preview host can resize one preview and reset them all"
```

---

### Task 7: The four bridge endpoints

**Files:**
- Modify: `obs_youtube_uploader/ui/api.py`
- Test: `tests/test_api_settings_fields.py`

**Interfaces:**
- Consumes: Tasks 1, 2, 5, 6.
- Produces: `parse_preview_size(text) -> {w, h, error}`;
  `set_preview_snap(bool) -> {applied, persisted, error}`;
  `set_preview_size(name, w, h) -> {applied, persisted, error}`;
  `reset_preview_layouts() -> {applied, persisted, error}`;
  `get_preview_hotkey_state()` payload gains `sizes` and `client_sizes`.

- [ ] **Step 1: Write the failing tests**

Follow the fake-host conventions already in `tests/test_api_settings_fields.py`.

```python
def test_parse_preview_size_reports_an_error_rather_than_raising():
    api = _api()
    assert api.parse_preview_size("nonsense")["error"]
    assert api.parse_preview_size("1280x720") == {"w": 1280, "h": 720, "error": None}


def test_set_preview_size_refuses_below_the_floor():
    api = _api()
    result = api.set_preview_size("Alice", 10, 10)
    assert result["applied"] is False
    assert "120x90" in result["error"]


def test_set_preview_size_refuses_a_character_with_no_saved_rect():
    """There is no x/y to write, and layout.deserialize drops any entry
    missing a full rect -- so a w/h written alone vanishes at the next
    load, after the page has reported it accepted."""
    api = _api()
    result = api.set_preview_size("Nobody", 640, 392)
    assert result["applied"] is False


def test_set_preview_size_rewrites_an_offline_entry_in_place():
    api = _api(layouts={"Alice": {"x": 5, "y": 6, "w": 320, "h": 210}})
    result = api.set_preview_size("Alice", 640, 392)
    assert result["applied"] is True
    saved = api._state.settings["preview"]["layouts"]["Alice"]
    assert (saved["w"], saved["h"], saved["x"]) == (640, 392, 5)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --no-sync python -m pytest tests/test_api_settings_fields.py -k preview_size -v`
Expected: FAIL, `AttributeError`

- [ ] **Step 3: Implement the endpoints**

Add beside `set_preview_show_labels`:

```python
    def parse_preview_size(self, text) -> dict:
        """Validate a typed "1280x720", mirroring parse_preview_bind.

        The page sends the raw string rather than parsing it, so the one
        definition of what a size looks like stays in a pure module CI can
        test -- web/*.js is never executed by anything in the suite.
        """
        parsed = preview_geometry.parse_size(text)
        if parsed is None:
            return {"w": 0, "h": 0, "error": "Sizes look like 1280x720."}
        return {"w": parsed[0], "h": parsed[1], "error": None}

    def set_preview_snap(self, enabled) -> dict:
        """Persist whether a dragged preview snaps to its neighbours and the
        screen edges, then push it live via PreviewHost.restyle() -- snap is
        read per mouse-move, so the live PreviewWindow.snap has to be
        refreshed or the checkbox would do nothing until restart."""
        result = self._write_preview_setting(("snap",), bool(enabled))
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def set_preview_size(self, name, w, h) -> dict:
        """Persist one preview's size, and apply it live if that client is running.

        Three cases, and the third is the awkward one:

          running        -> resized now; the host records the new rect
          saved, offline -> the stored entry's w/h are rewritten in place
          neither        -> refused, because there is no x/y to write

        The third cannot be repaired by inventing coordinates.
        layout.deserialize drops any entry missing a full rect
        (preview/layout.py), so a w/h written without an x/y is discarded at
        the next load -- silently, after the page has already reported the
        size as accepted.
        """
        try:
            width, height = int(w), int(h)
        except (TypeError, ValueError):
            return self._field_refused("Sizes look like 1280x720.")
        floor_w, floor_h = window_mod.MIN_SIZE
        if width < floor_w or height < floor_h:
            return self._field_refused(f"The smallest preview is {floor_w}x{floor_h}.")
        host = self._preview_host
        if host is not None and host.is_running and name in host.characters():
            host.resize_preview(name, (width, height))
            return self._field_ok()
        layouts = self._state.settings.get("preview", {}).get("layouts") or {}
        if name not in layouts:
            return self._field_refused(
                "Start this client once, or drag its preview, before setting a size."
            )
        entry = dict(layouts[name])
        entry["w"], entry["h"] = width, height
        return self._write_preview_setting(("layouts", name), entry)

    def reset_preview_layouts(self) -> dict:
        """Forget every saved preview position and size.

        Goes through the host when one is running so the open windows move
        too; falls back to clearing settings directly so a reset with
        previews switched off still takes effect at the next launch.
        """
        if self._preview_host is not None and self._preview_host.is_running:
            self._preview_host.reset_layouts()
            return self._field_ok()
        try:
            with settings_mod.update(self._state.settings) as doc:
                doc.setdefault("preview", {})["layouts"] = {}
        except OSError:
            logger.exception("Could not clear preview layouts")
            return self._field_refused("Could not save this to settings.")
        return self._field_ok()

    def _preview_sizes(self) -> dict:
        """Saved window size per character, for the Size... dialog's default.

        Read from settings rather than from the host so an offline character
        still reports the size it will open at.
        """
        out = {}
        layouts = self._state.settings.get("preview", {}).get("layouts") or {}
        for name, entry in layouts.items():
            try:
                out[name] = [int(entry["w"]), int(entry["h"])]
            except (KeyError, TypeError, ValueError):
                continue
        return out
```

Import `geometry as preview_geometry` and `window as window_mod` from
`..preview` alongside the existing preview imports at the top of `api.py`.

- [ ] **Step 4: Widen the payload**

In `get_preview_hotkey_state`'s returned dict, add:

```python
            # Sizes for the Size... dialog: what the preview is now, and
            # what its client's shape is, so the page can name the size
            # that would not distort it. client_sizes is sampled on the
            # preview thread (host._record_client_sizes) precisely so the
            # bridge thread never touches an HWND.
            "sizes": self._preview_sizes(),
            "client_sizes": host.client_sizes() if live else {},
```

- [ ] **Step 5: Run tests and formatter**

Run: `uv run --no-sync python -m pytest tests/ -q`
Run: `uv run --extra dev ruff format --check . && uv run --extra dev ruff check .`
Expected: PASS, clean. `tests/test_api.py`'s underscore-attribute assertion
must still pass — `_preview_sizes` is a method, and the two new state dicts
live on the host, not on `Api`.

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/ui/api.py tests/
git commit -m "Bridge endpoints for preview size, snap and reset"
```

---

### Task 8: The `Size…` row control

**Files:**
- Modify: `obs_youtube_uploader/web/previews.js`,
  `obs_youtube_uploader/web/style.css`, `obs_youtube_uploader/web/dev.js`
- Test: `tests/test_page_conventions.py` (existing rules; no new test file)

**Interfaces:**
- Consumes: Task 7's `parse_preview_size` / `set_preview_size`, and the
  `sizes` / `client_sizes` payload fields.
- Produces: a sixth per-row control.

- [ ] **Step 1: Widen the grid**

In `style.css`, change `#preview-binds`'s template to
`repeat(6, max-content) minmax(0, 1fr)` and update the comment above it: it
currently names the five children `makeRow` appends and says the number
changes with them. It must now name six, ending `Size…`. That comment is the
only place the count is explained.

- [ ] **Step 2: Add the button in `makeRow`**

In `previews.js`, after the `Edit…` button is appended and **before** the
Lock/Never-minimize block, append for character rows only:

```javascript
    if (character) { row.appendChild(makeSizeButton(character)); }
```

Then change the cycle-row `else` branch from two filler spans to **three**.
`.row { display: contents }` means the grid cannot tell one row from the
next, so a row short by one cell pulls the following row's children into
the gap.

- [ ] **Step 3: Implement the button**

```javascript
  // Mirrors the Edit… path step for step: disarm, prompt, send the raw
  // text to Python to parse, then commit. The page never parses the
  // string itself -- nothing in the suite executes this file, so the one
  // definition of what a size looks like belongs in geometry.py.
  function makeSizeButton(name) {
    var btn = WM.make('button', 'linkbtn', 'Size…');
    btn.addEventListener('click', function () {
      // Same trap bookmarks.js documents: an armed capture's document
      // keydown handler preventDefault()s every key, so a prompt opened
      // while one is live cannot be typed into.
      endCapture();
      var size = (state.sizes || {})[name];
      WM.prompt('Size for "' + name + '"', sizeHint(name),
                size ? size[0] + 'x' + size[1] : '')
        .then(function (text) {
          if (text === null || text === '') { return; }
          WM.send('parse_preview_size', text).then(function (parsed) {
            if (!parsed) { return; }
            if (parsed.error) {
              WM.send('alert_bookmarks', parsed.error);
              return;
            }
            var before = pushes;
            WM.send('set_preview_size', name, parsed.w, parsed.h)
              .then(function (res) {
                if (!res || !res.applied) {
                  if (res && res.error) { WM.send('alert_bookmarks', res.error); }
                  return;
                }
                if (pushes !== before) { return; }
                state.sizes = state.sizes || {};
                state.sizes[name] = [parsed.w, parsed.h];
              });
          });
        });
    });
    return btn;
  }

  // Plain prose: panel.js sets the dialog body with textContent, so no
  // markup survives here.
  function sizeHint(name) {
    var client = (state.client_sizes || {})[name];
    if (!client) {
      return 'Width x height in pixels, for example 1280x720. This client is '
           + 'not running, so the size applies next time it is.';
    }
    var size = (state.sizes || {})[name];
    var width = size ? size[0] : 640;
    // Chrome: BORDER*2 across, BORDER*2 + the label band down. The band is
    // 30px or 0 depending on the labels setting, which is why the number
    // is computed rather than baked in. showLabels comes off the SETTINGS
    // payload, not the hotkey-state one -- same route and same reason as
    // minimizeInactive above: it lives in Settings' own Previews card.
    var dw = 4, dh = 4 + (showLabels ? 30 : 0);
    var tall = Math.round((width - dw) * client[1] / client[0]) + dh;
    return 'Your client is ' + client[0] + 'x' + client[1] + '. At this width '
         + 'an undistorted preview is ' + width + 'x' + tall
         + '; a different shape will stretch the picture.';
  }
```

- [ ] **Step 4: Carry the new state**

Two different routes, and mixing them up is the bug this step exists to
prevent:

- `sizes` and `client_sizes` ride the **preview-hotkey-state** payload. Add
  them to the initial `state` literal as `{}` each; they are replaced
  wholesale with the rest of `state` on every push and refresh.
- `showLabels` rides the **settings** payload. Declare it beside
  `minimizeInactive` as `var showLabels = true;` and set it in the same
  `wm:settings` listener that already reads `minimizeInactive`, from
  `s.preview && s.preview.show_labels !== false`. It is not on the hotkey
  payload and must not be added to it — Settings owns that field.

- [ ] **Step 5: Update `dev.js`**

Add `sizes`, `client_sizes` to the fake preview-hotkey-state payload and
`show_labels` to the fake settings payload's `preview` section. Give at
least one character a saved size and a client size, and one neither — the
harness is how the width gets measured, and a fixture missing these renders
a page without the control being measured.

- [ ] **Step 6: Verify the tests and the width**

Run: `uv run --no-sync python -m pytest tests/test_page_conventions.py tests/test_bridge_contract.py -v`
Expected: PASS. In particular `test_opening_a_dialog_disarms_an_armed_keybind_capture`
asserts `endCapture()` within 400 characters above every `WM.prompt(` in this
file, and `test_the_two_keybind_lists_render_the_same_row` asserts the track
kind and trailing `minmax(0, 1fr)` are unchanged.

Then measure the width in the `?dev=1` harness at **840x625** — six
`max-content` tracks on the tightest screen in the app is the real risk here,
and it cannot be reasoned about. Serve `obs_youtube_uploader/web/` and load
`index.html?dev=1`.

- [ ] **Step 7: Commit**

```bash
git add obs_youtube_uploader/web/
git commit -m "Size…: type a preview's dimensions"
```

---

### Task 9: The Previews card gains snapping and reset

**Files:**
- Modify: `obs_youtube_uploader/web/index.html`,
  `obs_youtube_uploader/web/settings.js`, `obs_youtube_uploader/web/dev.js`

**Interfaces:**
- Consumes: Task 7's `set_preview_snap` / `reset_preview_layouts`.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Add the markup**

In `index.html`, inside `#section-previews`, after the opacity row:

```html
        <div class="row"><label class="check">
            <input type="checkbox" id="preview-snap"><span class="box"></span>
            Snap previews to each other and the screen edges
          </label>
          <span class="hint" id="preview-snap-status">Off places a dragged
            preview exactly where you drop it.</span></div>
        <div class="row">
          <button class="btn danger" id="preview-reset">Reset previews</button>
          <span class="hint" id="preview-reset-status">Puts every preview
            back to its default size and place.</span></div>
```

`.btn.danger` is the only destructive treatment in this app, and
`test_page_conventions.py` asserts `linkbtn danger` has zero users — a red
link fails the suite. `#section-previews` has no accent button, so the
one-primary-action rule is satisfied.

- [ ] **Step 2: Wire the checkbox**

In `settings.js`, add a block in the same shape as
`restore-preview-positions`. Written out rather than referred to, because
the engineer may be reading this task on its own:

```javascript
// Same shape as preview-show-labels above: a per-field endpoint that
// reports {applied, persisted, error}, a box that goes back if the write
// is refused, and the previews-off note when the setting is inert.
(function () {
  var box = WM.el('preview-snap');
  var status = WM.el('preview-snap-status');
  if (!box || !status) { return; }

  var DEPENDS = 'Applies when you turn previews back on.';
  function say(text) { status.textContent = text; }
  function previewsOn() {
    var enable = WM.el('preview-enabled');
    return !!(enable && enable.checked);
  }
  function sayDependence() { if (!previewsOn()) { say(DEPENDS); } }

  box.addEventListener('change', function () {
    var wanted = box.checked;
    WM.send('set_preview_snap', wanted).then(function (res) {
      if (!res || !res.applied) {
        box.checked = !wanted;
        say((res && res.error) || 'Could not save this.');
        return;
      }
      say('Snapping is ' + (wanted ? 'on' : 'off') + '.');
      sayDependence();
    });
  });

  document.addEventListener('wm:settings', function (ev) {
    var s = (ev && ev.detail) || {};
    box.checked = !(s.preview && s.preview.snap === false);
    sayDependence();
  });

  var enableBox = WM.el('preview-enabled');
  if (enableBox) {
    document.addEventListener('wm:preview-enabled-changed', function () {
      sayDependence();
      if (previewsOn() && status.textContent === DEPENDS) { say(''); }
    });
  }
}());
```

Match the surrounding file for how it reads the settings payload — if the
neighbouring blocks use a different event name or accessor than
`wm:settings`/`ev.detail`, use theirs. The endpoint call, the revert on
refusal, and the dependence note are the parts that must not change.

- [ ] **Step 3: Wire the reset button**

```javascript
    btn.addEventListener('click', function () {
      WM.confirm('Reset previews',
                 'Every preview goes back to its default size and place. The '
               + 'positions you have dragged are discarded, and Wingman '
               + 'cannot get them back.')
        .then(function (ok) {
          if (!ok) { return; }
          WM.send('reset_preview_layouts').then(function (res) {
            say(res && res.applied
                ? 'Previews are back at their defaults.'
                : ((res && res.error) || 'Could not reset previews.'));
          });
        });
    });
```

Title is a short verb phrase and the body names the irreversibility, matching
`bookmarks.js:391` and `settings.js:401`. It quotes no count: derived numbers
must be derived or test-asserted, never retyped.

- [ ] **Step 4: Update `dev.js`**

Add `snap` to the fake settings payload's `preview` section.

- [ ] **Step 5: Verify**

Run: `uv run --no-sync python -m pytest tests/test_page_conventions.py -v`
Expected: PASS — specifically `test_no_container_offers_two_primary_actions`,
`test_the_destructive_treatment_is_a_button_and_restates_its_hover`,
`test_no_checkbox_or_radio_renders_as_a_native_control`, and
`test_every_hidden_element_can_actually_hide`.

Then open the Previews card in `?dev=1` at 840x625 and confirm both controls
render and neither overflows.

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/web/
git commit -m "Previews card: snapping toggle and reset"
```

---

### Task 10: Documentation

**Files:**
- Modify: `docs/smoke-checklist.md`, `docs/preview-roadmap.md`

- [ ] **Step 1: Add the smoke steps**

Add a "Preview sizing" section to `docs/smoke-checklist.md` covering, each as
a checkbox:

1. Drag a preview's resize handle; the picture stays undistorted against the
   client's shape, and both a mostly-horizontal and a mostly-vertical drag
   change the size.
2. Turn labels off in the Previews card, then drag the handle again. The
   picture is still undistorted — this is the case the first draft of the
   design got wrong.
3. `Size…` on a running client: type `640x392`, confirm the preview resizes
   and the hint named the undistorted size before you typed.
4. `Size…` on an offline character with a saved position: the size is
   accepted and applies when that client next runs.
5. `Size…` on a character with no saved position: refused, with the sentence
   telling you to start the client once.
6. Turn snapping off, drag a preview next to another: no magnetism. Turn it
   back on: magnetism returns, without restarting.
7. Reset previews: confirm dialog appears, previews return to the default
   stack, and locks and keybinds survive.
8. Reset with previews switched off, then turn them on: they open at
   defaults.

- [ ] **Step 2: Record the DWM correction**

Add to `docs/preview-roadmap.md`'s "Corrections to the record" section:

> **A DWM thumbnail stretches to fill `rcDestination`; it does not preserve
> the source aspect ratio.** Measured with two solid-colour windows, a 2:1
> and a 4:1 source into a 1:1 destination, with a `fVisible=False` control:
> the picture filled the destination in every case. So a preview whose shape
> does not match its client has never letterboxed — it has been showing the
> game **distorted**. This is the third claim about this API to have read
> plausibly, gone unverified, and been followed; see the
> `SetLayeredWindowAttributes` and thumbnail-alpha entries above.

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "Smoke steps for preview sizing, and the DWM stretch correction"
```

---

## Verification Before Completion

- [ ] `uv run --no-sync python -m pytest tests/` — full suite
- [ ] `uv run --extra dev ruff check .`
- [ ] `uv run --extra dev ruff format --check .`
- [ ] The `?dev=1` harness at 840x625: the six-track row does not overflow
- [ ] `docs/smoke-checklist.md`'s new section, by hand, against real clients
      on Windows — including the labels-off case
