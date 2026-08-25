# EVE Preview Subsystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Live, click-to-focus previews of running EVE Online clients, floating over the desktop, with layouts that survive a restart.

**Architecture:** A dedicated thread owns a Win32 message pump and every preview HWND. Each preview is one small layered top-level window whose chrome (border, label band) is rendered by Pillow and pushed via `UpdateLayeredWindow`; the live client image is a DWM thumbnail composited over that chrome. The majority of the logic — geometry, chrome rendering, layout persistence, client identity — is pure Python, tested on Linux in CI.

**Tech Stack:** Python 3.11+, ctypes (user32/gdi32/dwmapi), Pillow, pywebview 6.2.1, pytest.

**Spec:** `eve-preview-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **Licence: Wingman is GPL-3.0-only on this branch**, which is what makes deriving from TriffView (GPL-3.0-only) lawful. The relicense is part of this change, not a prerequisite to it — `LICENSE`, `README.md`, `THIRD-PARTY-NOTICES.md`, and `pyproject.toml`'s `license` field all carry it, and it ships in the same PR. Keep TriffView attributions in the modules that derive from it: the GPL requires the derivation be visible, and it is also just accurate.
- **The process DPI mode is frozen.** `__main__.set_dpi_awareness()` selects `PROCESS_SYSTEM_DPI_AWARE` deliberately (`__main__.py:99-114`), and `ui/chrome.py:177-186` depends on that choice. **Never modify it.** The preview thread sets its own awareness thread-locally.
- **`evewindows.list_eve_windows()`'s signature is frozen.** It returns `list[str]` of sorted, de-duplicated titles (`evewindows.py:80-89`) and `ui/api.py:1288-1303` passes that straight to the page. Do not change its return type.
- **Every ctypes function gets `argtypes` and `restype` declared before use.** Undeclared, ctypes marshals pointer-sized values as 32-bit ints; the failure is a truncated handle or a late `OverflowError` inside a callback, not a clean error. This is documented at `evewindows.py:36-44` and `ui/chrome.py:123-131`, and was hit twice during design probing.
- **Every HWND touch happens on the preview thread.** Violations hang rather than raise.
- **`settings.save()` already has two writers and must be serialized.** It rewrites the complete projected document (`settings.py:145-149`), and `ui/api.py:722-739` writes from an upload worker thread by design. Task 13 adds a lock. No writer may save from a stale snapshot, and no writer may replace a subtree wholesale.
- **New subpackages must be added to `packages` in `pyproject.toml:49`.** A missing entry installs cleanly and fails at import time in the frozen build only.
- **No new runtime dependencies.** Pillow, pystray, pywebview are already present. pywebview is pinned `==6.2.1`; do not upgrade it.
- **Every module must import cleanly on Linux**, guarding Windows calls behind `sys.platform`, following `evewindows.py:1-14`.
- **CI runs `ubuntu-latest`** (`ci.yml:10`). Pure-logic tasks must pass there.

---

### Task 1: Verify thread-local DPI awareness

The design's DPI strategy is unverified and everything downstream assumes it. This is a **throwaway probe**, not shipped code: its deliverable is a recorded answer.

**Files:**
- Create (throwaway): `C:\dev\_probe\probe_thread_dpi.py`
- Modify: `eve-preview-design.md` — record the result in the Risks section

- [x] **Step 1: Write the probe**

```python
"""THROWAWAY. Does thread-local PMv2 hold while the process stays System-aware?"""
import ctypes, threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shcore = ctypes.WinDLL("shcore", use_last_error=True)
user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
user32.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int
user32.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]

# Reproduce production order: the process is System-aware FIRST.
shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
print("process set System-aware")

result = {}

def preview_thread():
    prev = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # PMv2
    ctx = user32.GetThreadDpiAwarenessContext()
    result["prev_nonzero"] = bool(prev)
    result["awareness"] = user32.GetAwarenessFromDpiAwarenessContext(ctypes.c_void_p(ctx))

t = threading.Thread(target=preview_thread)
t.start(); t.join()

# DPI_AWARENESS_PER_MONITOR_AWARE == 2
print(f"call accepted: {result['prev_nonzero']}")
print(f"thread awareness: {result['awareness']} (2 == per-monitor)")
print("VERDICT:", "OK" if result["awareness"] == 2 else "THREAD-LOCAL DPI DOES NOT HOLD")
```

- [x] **Step 2: Run it on Windows**

Run: `C:\dev\flygd-wingman\.venv\Scripts\python.exe C:\dev\_probe\probe_thread_dpi.py`
Expected: `VERDICT: OK`

- [x] **Step 3: Extend the probe to check thumbnail rects**

Add to the thread, after setting PMv2: create a layered `WS_POPUP` window, register a DWM thumbnail of any visible window, and set `rcDestination` to a known rect. Screenshot and confirm the thumbnail lands where the rect says — not offset or scaled. This is the half that thread-local awareness could plausibly break.

- [x] **Step 4: Record the outcome in the design**

If `VERDICT: OK` and rects land correctly, replace risk item 1 in `eve-preview-design.md` with the measured result and the Windows build tested.

**If the verdict is not OK: STOP and escalate.** The fallback stated in the design is to keep the preview thread System-aware and accept TriffView-equivalent mixed-DPI behaviour — **not** to change the process-wide setting. That is a design change and needs review before any further task starts.

- [x] **Step 5: Commit the design update**

```bash
git add eve-preview-design.md
git commit -m "docs: record thread-local DPI probe result"
```

---

### Task 2: Package scaffold, with a guard against the packaging trap

**Files:**
- Create: `obs_youtube_uploader/preview/__init__.py`
- Modify: `pyproject.toml:49`
- Test: `tests/test_packaging_completeness.py`

**Interfaces:**
- Produces: the `obs_youtube_uploader.preview` package that every later task imports.

- [x] **Step 1: Write the failing test**

```python
"""Every importable subpackage must be listed in pyproject's `packages`.

pyproject.toml:38-49 records why this is not paranoia: discovery is
enumerated by hand, subpackages are NOT implied by their parent, and a
missing entry "installs cleanly and fails at import time in the built
artifact, not in the checkout where the source tree makes it work anyway."
A source checkout passes every test while the frozen release dies on
launch, so only a test that reads the manifest can catch it here.
"""
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_every_subpackage_is_declared():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        declared = set(tomllib.load(fh)["tool"]["setuptools"]["packages"])
    on_disk = {
        ".".join(p.parent.relative_to(ROOT).parts)
        for p in (ROOT / "obs_youtube_uploader").rglob("__init__.py")
    }
    assert on_disk <= declared, f"undeclared packages: {sorted(on_disk - declared)}"
```

- [x] **Step 2: Run it — it must pass first, proving the guard is honest**

Run: `python -m pytest tests/test_packaging_completeness.py -v`
Expected: PASS (only `obs_youtube_uploader` and `.ui` exist so far)

- [x] **Step 3: Create the package, and watch the guard fail**

```bash
mkdir -p obs_youtube_uploader/preview
printf '"""EVE client preview windows. Windows-only at runtime."""\n' \
  > obs_youtube_uploader/preview/__init__.py
python -m pytest tests/test_packaging_completeness.py -v
```

Expected: FAIL with `undeclared packages: ['obs_youtube_uploader.preview']`

- [x] **Step 4: Declare the package**

In `pyproject.toml`, change line 49 to:

```toml
packages = [
    "obs_youtube_uploader",
    "obs_youtube_uploader.ui",
    "obs_youtube_uploader.preview",
]
```

- [x] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_packaging_completeness.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add pyproject.toml obs_youtube_uploader/preview/__init__.py tests/test_packaging_completeness.py
git commit -m "feat(preview): add package scaffold, guard subpackage declaration"
```

---

### Task 3: `geometry.py` — rects, placement, snapping, hit-testing

Pure integer arithmetic. No Windows, no framework, runs in CI.

**Files:**
- Create: `obs_youtube_uploader/preview/geometry.py`
- Test: `tests/test_preview_geometry.py`

**Interfaces:**
- Produces:
  - `Rect(NamedTuple)` with `x, y, w, h` and properties `right`, `bottom`
  - `default_stack(index: int, screen: Rect, size: tuple[int, int]) -> Rect`
  - `snap(rect: Rect, others: list[Rect], screen: Rect, threshold: int = 12) -> Rect`
  - `hit_resize_handle(rect: Rect, px: int, py: int, handle: int = 16) -> bool`
  - `thumbnail_rect(rect: Rect, border: int, label_h: int) -> Rect`

- [x] **Step 1: Write the failing tests**

```python
"""Pure geometry: no Windows, no Pillow, runs in CI on Linux."""
import pytest

from obs_youtube_uploader.preview import geometry as g

SCREEN = g.Rect(0, 0, 1920, 1080)


def test_default_stack_starts_at_the_right_edge():
    r = g.default_stack(0, SCREEN, (320, 210))
    assert r.right <= SCREEN.right
    assert r.x == SCREEN.right - 320 - g.EDGE_MARGIN


def test_default_stack_descends_without_overlapping():
    a = g.default_stack(0, SCREEN, (320, 210))
    b = g.default_stack(1, SCREEN, (320, 210))
    assert b.y >= a.bottom


def test_default_stack_wraps_into_a_new_column_when_it_runs_out_of_height():
    """Twenty clients is an ordinary multiboxing setup; the column must not
    walk off the bottom of the screen and leave previews unreachable."""
    last = g.default_stack(19, SCREEN, (320, 210))
    assert last.bottom <= SCREEN.bottom
    assert last.x < g.default_stack(0, SCREEN, (320, 210)).x


def test_snap_aligns_to_a_nearby_edge():
    moving = g.Rect(100, 103, 320, 210)
    other = g.Rect(100, 300, 320, 210)   # left edges 0 apart, y within threshold
    assert g.snap(moving, [other], SCREEN).x == 100


def test_snap_ignores_edges_beyond_the_threshold():
    moving = g.Rect(100, 100, 320, 210)
    other = g.Rect(400, 100, 320, 210)
    assert g.snap(moving, [other], SCREEN, threshold=12) == moving


def test_snap_pulls_to_the_screen_edge():
    moving = g.Rect(5, 400, 320, 210)
    assert g.snap(moving, [], SCREEN).x == 0


def test_snap_never_moves_a_rect_further_than_the_threshold():
    """A snap that teleports a preview across the desktop is a bug that
    reads as 'the drag broke', so bound the correction explicitly."""
    moving = g.Rect(500, 500, 320, 210)
    out = g.snap(moving, [g.Rect(508, 500, 320, 210)], SCREEN, threshold=12)
    assert abs(out.x - moving.x) <= 12


def test_hit_resize_handle_is_the_bottom_right_corner():
    r = g.Rect(100, 100, 320, 210)
    assert g.hit_resize_handle(r, r.right - 4, r.bottom - 4)
    assert not g.hit_resize_handle(r, r.x + 4, r.y + 4)


def test_thumbnail_rect_insets_by_border_and_label():
    r = g.Rect(0, 0, 320, 210)
    t = g.thumbnail_rect(r, border=5, label_h=30)
    assert t == g.Rect(5, 35, 310, 170)


@pytest.mark.parametrize("w,h", [(0, 0), (4, 4)])
def test_thumbnail_rect_never_goes_negative(w, h):
    """A preview dragged smaller than its own chrome must clamp, not hand
    DwmUpdateThumbnailProperties an inverted rect."""
    t = g.thumbnail_rect(g.Rect(0, 0, w, h), border=5, label_h=30)
    assert t.w >= 0 and t.h >= 0
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: obs_youtube_uploader.preview.geometry`

- [x] **Step 3: Write the implementation**

```python
"""Preview geometry. Pure integer arithmetic -- no Windows, no Pillow.

All rects are absolute virtual-desktop pixels. Conversion to a window's
own client coordinates happens at the Win32 boundary, not here, so this
module stays testable on any platform.
"""
from typing import NamedTuple

EDGE_MARGIN = 18   # gap from the screen edge for the default stack
STACK_GAP = 10     # vertical gap between stacked previews
RESIZE_HANDLE = 16


class Rect(NamedTuple):
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


def default_stack(index: int, screen: Rect, size: tuple[int, int]) -> Rect:
    """Place preview *index* down the right edge, wrapping into columns.

    Wrapping is not decoration: twenty clients at 210px tall overflow a
    1080p screen after four, and a preview placed off-screen cannot be
    dragged back.
    """
    w, h = size
    per_column = max(1, (screen.h - EDGE_MARGIN) // (h + STACK_GAP))
    column, row = divmod(index, per_column)
    x = screen.right - w - EDGE_MARGIN - column * (w + STACK_GAP)
    y = screen.y + EDGE_MARGIN + row * (h + STACK_GAP)
    return Rect(x, y, w, h)


def _snap_axis(value: int, targets: list[int], threshold: int) -> int:
    best, best_delta = value, threshold + 1
    for t in targets:
        delta = abs(t - value)
        if delta < best_delta:
            best, best_delta = t, delta
    return best if best_delta <= threshold else value


def snap(rect: Rect, others: list[Rect], screen: Rect,
         threshold: int = 12) -> Rect:
    """Pull *rect* onto nearby preview edges and screen edges."""
    xs = [screen.x, screen.right - rect.w]
    ys = [screen.y, screen.bottom - rect.h]
    for o in others:
        xs += [o.x, o.right, o.right - rect.w, o.x - rect.w]
        ys += [o.y, o.bottom, o.bottom - rect.h, o.y - rect.h]
    return Rect(_snap_axis(rect.x, xs, threshold),
                _snap_axis(rect.y, ys, threshold), rect.w, rect.h)


def hit_resize_handle(rect: Rect, px: int, py: int,
                      handle: int = RESIZE_HANDLE) -> bool:
    return (rect.right - handle <= px <= rect.right
            and rect.bottom - handle <= py <= rect.bottom)


def thumbnail_rect(rect: Rect, border: int, label_h: int) -> Rect:
    """The client-coordinate rect the DWM thumbnail is drawn into.

    Clamped at zero: a preview dragged smaller than its own chrome would
    otherwise produce an inverted rect, which DWM rejects.
    """
    return Rect(border, border + label_h,
                max(0, rect.w - border * 2),
                max(0, rect.h - border - border - label_h))
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preview_geometry.py -v`
Expected: PASS (11 tests)

- [x] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/geometry.py tests/test_preview_geometry.py
git commit -m "feat(preview): geometry -- placement, snapping, hit-testing"
```

---

### Task 4: `chrome.py` — Pillow-rendered preview chrome

Replaces TriffView's GDI+ layer. Pure: takes numbers, returns an image.

**Files:**
- Create: `obs_youtube_uploader/preview/chrome.py`
- Create: `obs_youtube_uploader/assets/fonts/Inter-Regular.ttf` (bundled)
- Modify: `THIRD-PARTY-NOTICES.md`
- Modify: `packaging/uploader.spec:24-58` (add the font to `datas`) and its post-build assertion
- Test: `tests/test_preview_chrome.py`

**Interfaces:**
- Consumes: `geometry.Rect`
- Produces: `render(size, label, *, border_color, border=5, label_h=30, selected=False) -> PIL.Image.Image` (mode `RGBA`)

- [x] **Step 1: Bundle a TTF**

`web/fonts/` holds `.woff2`, which Pillow cannot load. Download the Inter **TTF** matching the bundled `InterVariable.woff2` release, place it at `obs_youtube_uploader/assets/fonts/Inter-Regular.ttf`, and add to `THIRD-PARTY-NOTICES.md` under a new `## Inter (font)` section naming the SIL Open Font License and the release URL. `web/fonts/Inter-LICENSE.txt` already carries the licence text.

Bundling rather than using `C:\Windows\Fonts\segoeui.ttf` is deliberate: it makes label rendering byte-identical on Linux, which is what lets the tests below run in CI.

**The font must also be added to `packaging/uploader.spec`'s `datas`.** That
list is enumerated by hand and collects only what it names — web assets, the
icon, the notices, the engine (`uploader.spec:24-58`). Package data is not
picked up automatically, and the spec's own comments record why that matters:
PyInstaller exits 0 when a `datas` entry fails to collect, so a missing font
produces a green build. Add:

```python
        # modulegraph does not follow data files, and Pillow loads this by
        # path at render time. Without it the frozen build renders every
        # preview label in Pillow's bitmap default font.
        (str(ROOT / "obs_youtube_uploader" / "assets" / "fonts"), "assets/fonts"),
```

and extend the post-build assertion in `build.yml`/`release.yml` to check the
collected font exists, exactly as it already checks the engine and `web/`.

- [x] **Step 2: Write the failing tests**

```python
"""Chrome rendering is pure: numbers in, RGBA image out.

Testing pixels directly is the point of moving off GDI+ -- these run in
CI on Linux, where no Windows drawing API exists.
"""
from obs_youtube_uploader.preview import chrome

CYAN = (0, 200, 220, 255)


def test_border_is_drawn_in_the_requested_colour():
    img = chrome.render((320, 210), "Pilot", border_color=CYAN)
    assert img.getpixel((0, 0)) == CYAN
    assert img.getpixel((319, 209)) == CYAN


def test_interior_below_the_label_is_transparent_for_the_thumbnail():
    """The DWM thumbnail composites over this area. Leaving it opaque is
    harmless today but hides mistakes if the thumbnail fails to register --
    a transparent hole makes that failure visible instead of silent."""
    img = chrome.render((320, 210), "Pilot", border_color=CYAN)
    assert img.getpixel((160, 120))[3] == 0


def test_label_band_is_opaque_and_the_right_height():
    img = chrome.render((320, 210), "Pilot", border_color=CYAN,
                        border=5, label_h=30)
    assert img.getpixel((160, 6))[3] > 200      # inside the band
    assert img.getpixel((160, 40))[3] == 0      # below it


def test_label_text_is_actually_drawn():
    blank = chrome.render((320, 210), "", border_color=CYAN)
    named = chrome.render((320, 210), "Pilot", border_color=CYAN)
    assert blank.tobytes() != named.tobytes()


def test_long_labels_do_not_overflow_the_band():
    """A 40-character character name must not paint over the thumbnail."""
    img = chrome.render((320, 210), "X" * 60, border_color=CYAN,
                        border=5, label_h=30)
    assert img.getpixel((160, 40))[3] == 0


def test_selected_draws_a_thicker_border():
    plain = chrome.render((320, 210), "P", border_color=CYAN, border=5)
    picked = chrome.render((320, 210), "P", border_color=CYAN, border=5,
                           selected=True)
    assert plain.tobytes() != picked.tobytes()


def test_degenerate_size_does_not_raise():
    """Resize can transiently produce a rect smaller than the chrome."""
    chrome.render((4, 4), "P", border_color=CYAN)
```

- [x] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_chrome.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 4: Write the implementation**

```python
"""Preview chrome, rendered with Pillow.

Pure by construction: it takes sizes and colours and returns an RGBA
image. Nothing here knows about HWNDs, which is what lets the whole
drawing layer be tested on Linux -- the reason this replaces TriffView's
GDI+ path rather than porting it.
"""
import logging
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Inter-Regular.ttf"
LABEL_BG = (10, 14, 20, 235)
LABEL_FG = (235, 240, 245, 255)


@lru_cache(maxsize=8)
def _font(size: int) -> ImageFont.FreeTypeFont:
    """Cached: a drag re-renders chrome on every move, and reopening the
    face each time shows up as stutter."""
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        # Degrade rather than take the subsystem down -- but LOUDLY. The
        # realistic cause is a frozen build that did not collect the font
        # (uploader.spec's datas is enumerated by hand and PyInstaller exits
        # 0 when an entry misses), and a silent fallback there ships
        # unlabelled previews with nothing in the log to explain them.
        logger.warning("Bundled font missing at %s; labels will use Pillow's "
                       "default face. In a frozen build this means "
                       "uploader.spec did not collect assets/fonts.",
                       FONT_PATH)
        return ImageFont.load_default()


def _ellipsize(draw, text, font, max_w):
    if not text or draw.textlength(text, font=font) <= max_w:
        return text
    ell = "\u2026"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell


def render(size, label, *, border_color, border=5, label_h=30,
           selected=False, font_size=17):
    """Render one preview's chrome. Interior is left transparent."""
    w, h = max(1, size[0]), max(1, size[1])
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    width = border * 2 if selected else border
    d.rectangle([0, 0, w - 1, h - 1], outline=border_color, width=width)

    band_bottom = min(h - 1, border + label_h)
    if band_bottom > border:
        d.rectangle([border, border, w - border - 1, band_bottom], fill=LABEL_BG)
        font = _font(font_size)
        text = _ellipsize(d, label, font, max_w=w - border * 2 - 12)
        if text:
            d.text((border + 6, border + 4), text, font=font, fill=LABEL_FG)
    return img
```

- [x] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_preview_chrome.py -v`
Expected: PASS (7 tests)

- [x] **Step 6: Commit**

```bash
git add obs_youtube_uploader/preview/chrome.py obs_youtube_uploader/assets/fonts/ \
        THIRD-PARTY-NOTICES.md packaging/uploader.spec .github/workflows/ \
        tests/test_preview_chrome.py
git commit -m "feat(preview): Pillow-rendered chrome, bundled Inter TTF"
```

---

### Task 5: `layout.py` — persisted preview layouts

**Files:**
- Create: `obs_youtube_uploader/preview/layout.py`
- Test: `tests/test_preview_layout.py`

**Interfaces:**
- Consumes: `geometry.Rect`
- Produces:
  - `Entry(NamedTuple)` with `rect: Rect`, `locked: bool`
  - `serialize(entries: dict[str, Entry]) -> dict`
  - `deserialize(raw) -> dict[str, Entry]`

- [x] **Step 1: Write the failing tests**

```python
"""Layout persistence, pure. Mirrors settings.py's posture: a malformed
stored value must fall back, never raise -- a corrupt layout key should
cost you one preview's position, not the app's launch."""
from obs_youtube_uploader.preview import layout
from obs_youtube_uploader.preview.geometry import Rect


def test_round_trips():
    entries = {"Pilot One": layout.Entry(Rect(10, 20, 320, 210), locked=False)}
    assert layout.deserialize(layout.serialize(entries)) == entries


def test_deserialize_ignores_a_malformed_entry_but_keeps_the_others():
    raw = {
        "Good": {"x": 1, "y": 2, "w": 3, "h": 4, "locked": False},
        "Bad": {"x": "not-a-number", "y": 2, "w": 3, "h": 4},
    }
    out = layout.deserialize(raw)
    assert set(out) == {"Good"}


def test_deserialize_of_a_wrong_type_returns_empty():
    for raw in (None, [], "nope", 3):
        assert layout.deserialize(raw) == {}


def test_locked_defaults_to_false_when_absent():
    out = layout.deserialize({"P": {"x": 1, "y": 2, "w": 3, "h": 4}})
    assert out["P"].locked is False


def test_non_positive_sizes_are_rejected():
    """A zero-width stored rect would produce an invisible, undraggable
    preview that looks like the feature is broken."""
    assert layout.deserialize({"P": {"x": 1, "y": 2, "w": 0, "h": 4}}) == {}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_layout.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Write the implementation**

```python
"""Preview layout persistence.

Pure: dict in, dict out. The caller owns the file, because settings.save()
is single-writer on the UI thread (settings.py:145-149) and the preview
thread must never reach it.
"""
from typing import NamedTuple

from .geometry import Rect


class Entry(NamedTuple):
    rect: Rect
    locked: bool = False


def serialize(entries: dict) -> dict:
    return {
        key: {"x": e.rect.x, "y": e.rect.y, "w": e.rect.w, "h": e.rect.h,
              "locked": bool(e.locked)}
        for key, e in entries.items()
    }


def deserialize(raw) -> dict:
    """Rebuild entries, dropping anything malformed.

    Deliberately forgiving, matching settings.py's validation posture: a
    hand-edited or partially-written settings file should cost one
    preview's position, not the launch.
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        try:
            x, y, w, h = (int(value["x"]), int(value["y"]),
                          int(value["w"]), int(value["h"]))
        except (KeyError, TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        out[key] = Entry(Rect(x, y, w, h), bool(value.get("locked", False)))
    return out
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preview_layout.py -v`
Expected: PASS (5 tests)

- [x] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/layout.py tests/test_preview_layout.py
git commit -m "feat(preview): layout serialisation with forgiving validation"
```

---

### Task 6: Expose window handles from `evewindows.py` without breaking its API

**Files:**
- Modify: `obs_youtube_uploader/evewindows.py:36-89`
- Test: `tests/test_evewindows.py` (add cases; all existing must stay green)

**Interfaces:**
- Produces: `_enumerate_windows() -> list[tuple[int, str]]` — `(hwnd, title)` for every visible titled window.
- Unchanged: `list_eve_windows(enumerator=None) -> list[str]`

- [x] **Step 1: Write the failing test**

```python
def test_enumerate_titles_is_derived_from_the_handle_enumerator(monkeypatch):
    """One enumeration path, two views of it. If these drift, the preview
    subsystem and the bookmarks checkbox disagree about which clients
    exist, and only one of them is visible to the user."""
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    monkeypatch.setattr(evewindows, "_enumerate_windows",
                        lambda: [(0x10, "EVE - Pilot"), (0x20, "Notepad")])
    assert evewindows._enumerate_titles() == ["EVE - Pilot", "Notepad"]


def test_list_eve_windows_still_returns_plain_sorted_titles(monkeypatch):
    """ui/api.py:1288-1303 hands this list straight to the page. The
    return type is frozen; adding handles here would break it silently."""
    monkeypatch.setattr(evewindows.sys, "platform", "win32")
    monkeypatch.setattr(evewindows, "_enumerate_windows",
                        lambda: [(0x20, "EVE - B"), (0x10, "EVE - A")])
    assert evewindows.list_eve_windows() == ["EVE - A", "EVE - B"]
```

- [x] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_evewindows.py -v`
Expected: FAIL — `_enumerate_windows` does not exist

- [x] **Step 3: Refactor — rename the collector, add a titles wrapper**

In `evewindows.py`, rename `_enumerate_titles` to `_enumerate_windows` and change its `callback` to append `(hwnd, buffer.value)` instead of `buffer.value`. Keep every `argtypes`/`restype` declaration and the broad `except` in the callback exactly as they are — the comments at `evewindows.py:36-44` and `:59-63` explain why both are load-bearing.

Then add:

```python
def _enumerate_titles() -> list:
    """Titles only, for `list_eve_windows`'s frozen string-list contract."""
    return [title for _hwnd, title in _enumerate_windows()]
```

- [x] **Step 4: Run the whole file's tests**

Run: `python -m pytest tests/test_evewindows.py -v`
Expected: PASS — the new cases and every pre-existing one

- [x] **Step 5: Commit**

```bash
git add obs_youtube_uploader/evewindows.py tests/test_evewindows.py
git commit -m "refactor(evewindows): expose handles, keep the title API frozen"
```

---

### Task 7: `discovery.py` — EVE clients with stable identity

**Files:**
- Create: `obs_youtube_uploader/preview/discovery.py`
- Test: `tests/test_preview_discovery.py`

**Interfaces:**
- Consumes: `evewindows._enumerate_windows`
- Produces:
  - `Client(NamedTuple)` with `hwnd: int`, `title: str`, `pid: int`, `character: str | None`, `stable_key: str`
  - `list_clients(*, enumerator=None, pids=None, image_name=None) -> list[Client]`

- [x] **Step 1: Write the failing tests**

```python
"""Client discovery. Every collaborator is injected so identity and
filtering logic is testable off Windows."""
from obs_youtube_uploader.preview import discovery

WINDOWS = [(0x10, "EVE - Pilot One"), (0x20, "Firefox"),
           (0x30, "EVE - Pilot Two")]
PIDS = {0x10: 100, 0x20: 200, 0x30: 300}
IMAGES = {100: "exefile.exe", 200: "firefox.exe", 300: "exefile.exe"}


def _list(**kw):
    kw.setdefault("enumerator", lambda: WINDOWS)
    kw.setdefault("pids", PIDS.get)
    kw.setdefault("image_name", IMAGES.get)
    return discovery.list_clients(**kw)


def test_finds_eve_clients():
    assert [c.character for c in _list()] == ["Pilot One", "Pilot Two"]


def test_rejects_a_non_eve_process_with_an_eve_title():
    """A browser tab titled 'EVE - something' must not become a preview.
    Title alone is user-controlled; the process name is not."""
    windows = [(0x40, "EVE - Not A Client")]
    out = discovery.list_clients(enumerator=lambda: windows,
                                 pids={0x40: 400}.get,
                                 image_name={400: "chrome.exe"}.get)
    assert out == []


def test_does_not_apply_the_engine_ini_rule():
    """bookmarks.is_engine_window_title also rejects '=' because the AHK
    INI format cannot carry it (bookmarks.py:308-309). That is a storage
    constraint of a different feature, not a property of EVE clients, and
    reusing it here would silently drop a previewable window."""
    windows = [(0x50, "EVE - Odd=Name")]
    out = discovery.list_clients(enumerator=lambda: windows,
                                 pids={0x50: 500}.get,
                                 image_name={500: "exefile.exe"}.get)
    assert len(out) == 1


def test_stable_key_is_the_character_name():
    assert _list()[0].stable_key == "Pilot One"


def test_character_select_has_no_character_and_falls_back_to_the_handle():
    """A client at character select has no name. It must still preview,
    but must never have a layout persisted against it -- the next client
    to sit at that screen would inherit the position."""
    windows = [(0x60, "EVE")]
    out = discovery.list_clients(enumerator=lambda: windows,
                                 pids={0x60: 600}.get,
                                 image_name={600: "exefile.exe"}.get)
    assert out[0].character is None
    assert out[0].stable_key == "hwnd:0x60"


def test_access_denied_on_image_name_drops_the_window():
    """OpenProcess fails for another user's or a higher-integrity process.
    That is expected, not an error, and must not raise."""
    out = _list(image_name=lambda pid: None)
    assert out == []


def test_enumerator_failure_is_survivable():
    def boom():
        raise OSError("no window station")
    assert _list(enumerator=boom) == []
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_discovery.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Write the implementation**

```python
"""Discover running EVE clients, with a stable identity per client.

Separate from `evewindows.list_eve_windows` on purpose: that function's
string-list return type is consumed by ui/api.py:1288-1303 and is frozen.
Both share `_enumerate_windows` so the argtypes discipline lives in one
place.
"""
import logging
import sys
from typing import NamedTuple

from .. import evewindows

logger = logging.getLogger(__name__)

TITLE_PREFIX = "EVE - "
CLIENT_IMAGE = "exefile.exe"


class Client(NamedTuple):
    hwnd: int
    title: str
    pid: int
    character: str | None
    stable_key: str


def _character(title: str) -> str | None:
    if title.startswith(TITLE_PREFIX):
        name = title[len(TITLE_PREFIX):].strip()
        return name or None
    return None


def list_clients(*, enumerator=None, pids=None, image_name=None) -> list:
    """Every visible EVE client window, as Client records.

    Collaborators are injected for testing, following evewindows.py's
    pattern. `image_name` returns None when the process cannot be opened,
    which is routine for processes owned by another user -- treated as
    "not a client", never as an error.
    """
    if sys.platform != "win32" and enumerator is None:
        return []
    enumerator = enumerator or evewindows._enumerate_windows
    pids = pids or _pid_for_window
    image_name = image_name or _image_name_for_pid
    try:
        windows = enumerator()
    except Exception:
        logger.exception("Could not enumerate windows")
        return []

    out = []
    for hwnd, title in windows:
        if not title.startswith("EVE"):
            continue
        try:
            pid = pids(hwnd)
            if not pid or image_name(pid) != CLIENT_IMAGE:
                continue
        except Exception:
            logger.exception("Skipped window 0x%x during discovery", hwnd)
            continue
        character = _character(title)
        out.append(Client(hwnd, title, pid, character,
                          character or f"hwnd:0x{hwnd:x}"))
    return out
```

- [x] **Step 4: Add the Windows-side resolvers**

Append to the same module. `procid.describe()` is **not** usable here: it spawns PowerShell per PID with a ten-second timeout (`procid.py:21-37`), justified in its own docstring as "one call on one code path". At a 700ms sweep across 20 clients that is catastrophic.

```python
_IMAGE_CACHE: dict = {}
_CACHE_SWEEPS = 0
_CACHE_FLUSH_EVERY = 512   # TriffViewSubsystem.cs:4732 uses the same bound


def _pid_for_window(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


def _image_name_for_pid(pid: int):
    """Executable basename for *pid*, or None if it cannot be opened.

    QueryFullProcessImageNameW under PROCESS_QUERY_LIMITED_INFORMATION --
    the limited right exists precisely so this works without elevation.
    """
    global _CACHE_SWEEPS
    if pid in _IMAGE_CACHE:
        return _IMAGE_CACHE[pid]
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD)]
    k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    handle = k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        _IMAGE_CACHE[pid] = None
        return None
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            _IMAGE_CACHE[pid] = None
            return None
        name = buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        k32.CloseHandle(handle)
    _IMAGE_CACHE[pid] = name
    return name


def flush_image_cache_periodically() -> None:
    """PIDs are reused. Called once per sweep by the host."""
    global _CACHE_SWEEPS
    _CACHE_SWEEPS += 1
    if _CACHE_SWEEPS >= _CACHE_FLUSH_EVERY:
        _CACHE_SWEEPS = 0
        _IMAGE_CACHE.clear()
```

- [x] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_preview_discovery.py -v`
Expected: PASS (7 tests)

- [x] **Step 6: Commit**

```bash
git add obs_youtube_uploader/preview/discovery.py tests/test_preview_discovery.py
git commit -m "feat(preview): client discovery with process-name filtering"
```

---

### Task 8: `win32.py` — the declaration surface, with a guard

**Files:**
- Create: `obs_youtube_uploader/preview/win32.py`
- Test: `tests/test_preview_win32.py`

**Interfaces:**
- Produces: structs (`RECT`, `POINT`, `SIZE`, `BLENDFUNCTION`, `BITMAPINFO`, `DWM_THUMBNAIL_PROPERTIES`, `WNDCLASSW`, `MSG`), constants (`WS_POPUP`, `WS_EX_*`, `WM_*`, `ULW_ALPHA`, `DWM_TNP_*`), and `bind() -> Libs` returning declared `user32`/`gdi32`/`dwmapi`/`kernel32` handles.

- [x] **Step 1: Write the failing test**

```python
"""The declaration guard.

Undeclared ctypes functions marshal pointer-sized values as 32-bit ints.
The failure is a truncated handle or an OverflowError raised *inside* a
callback, where it is reported via sys.unraisablehook and lost. Both
evewindows.py:36-44 and ui/chrome.py:123-131 document this; design
probing hit it twice, on DefWindowProcW and on SelectObject. A test that
enumerates the declarations is cheaper than finding it again.

Skipped on platform, NOT via importorskip. The module imports fine on
Linux by design (it declares types and constants at import time and only
touches DLLs inside bind()), so importorskip would not skip -- the test
would run and fail in CI on the bind() call.
"""
import sys

import pytest

from obs_youtube_uploader.preview import win32

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="binds user32/gdi32/dwmapi")

# Every function the subsystem calls, by library.
REQUIRED = {
    "user32": ["CreateWindowExW", "DestroyWindow", "DefWindowProcW",
               "RegisterClassW", "ShowWindow", "SetWindowPos",
               "UpdateLayeredWindow", "SetLayeredWindowAttributes",
               "GetMessageW", "DispatchMessageW", "TranslateMessage",
               "PostMessageW", "PostQuitMessage", "GetDC", "ReleaseDC",
               "GetClientRect", "InvalidateRect", "LoadCursorW",
               "SetCapture", "ReleaseCapture", "GetCursorPos",
               "SetForegroundWindow", "GetForegroundWindow",
               "AttachThreadInput", "IsIconic", "ShowWindowAsync",
               "GetWindowThreadProcessId",
               # Host thread: the hook, the hotkeys, the DPI override.
               # Omitting these was the gap that made Task 12 unbuildable.
               "SetWinEventHook", "UnhookWinEvent",
               "RegisterHotKey", "UnregisterHotKey",
               "SetThreadDpiAwarenessContext"],
    "gdi32": ["CreateDIBSection", "CreateCompatibleDC", "SelectObject",
              "DeleteObject", "DeleteDC"],
    "dwmapi": ["DwmRegisterThumbnail", "DwmUnregisterThumbnail",
               "DwmUpdateThumbnailProperties", "DwmIsCompositionEnabled"],
}


def test_every_used_function_is_declared():
    libs = win32.bind()
    missing = []
    for lib_name, funcs in REQUIRED.items():
        lib = getattr(libs, lib_name)
        for fn in funcs:
            f = getattr(lib, fn, None)
            if f is None:
                missing.append(f"{lib_name}.{fn} absent")
            elif f.argtypes is None:
                missing.append(f"{lib_name}.{fn} has no argtypes")
    assert not missing, "\n".join(missing)
```

- [x] **Step 2: Run to verify it fails**

On Windows: `.venv\Scripts\python.exe -m pytest tests/test_preview_win32.py -v`
Expected: FAIL with `ModuleNotFoundError`
On Linux the test **skips on platform**, and the import at module scope still has to succeed — which is the global constraint that every module imports cleanly off Windows. Declare structs and constants at import time; touch DLLs only inside `bind()`.

- [x] **Step 3: Write the module**

Create `win32.py` declaring every struct and constant listed in the Interfaces block, and a `bind()` returning a `Libs` NamedTuple of `user32, gdi32, dwmapi, kernel32` with `argtypes`/`restype` set on every function in `REQUIRED`. Use the declarations proven in the design probes verbatim, in particular:

```python
LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)

# These four are the ones that actually bit during probing.
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
```

Keep a module-level `_KEEPALIVE = []` for `WNDPROC` objects, with the comment from `ui/chrome.py:117-121`: a ctypes callback collected while Windows still holds its address takes the process down at the next message.

- [x] **Step 4: Run the test on Windows to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_preview_win32.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/win32.py tests/test_preview_win32.py
git commit -m "feat(preview): win32 declarations with a completeness guard"
```

---

### Task 9: `layered.py` — Pillow image onto a layered window

**Files:**
- Create: `obs_youtube_uploader/preview/layered.py`
- Test: `tests/test_preview_layered.py`

**Interfaces:**
- Consumes: `win32.bind`, a `PIL.Image.Image`
- Produces:
  - `to_premultiplied_bgra(img) -> bytes` (**pure — CI-tested**)
  - `push(libs, hwnd, img, x, y) -> bool` (Windows)

- [x] **Step 1: Write the failing tests**

```python
"""The premultiply step is pure and gets real tests; the ULW call is a
thin wrapper around it and is covered by the smoke checklist.

ULW_ALPHA requires PREMULTIPLIED BGRA. Getting this wrong makes
translucent pixels glow -- which looks correct on a dark background and
wrong everywhere else, so it is exactly the bug that ships.
"""
from PIL import Image

from obs_youtube_uploader.preview import layered


def test_opaque_pixel_is_bgra_ordered():
    img = Image.new("RGBA", (1, 1), (10, 20, 30, 255))
    assert layered.to_premultiplied_bgra(img) == bytes([30, 20, 10, 255])


def test_half_alpha_is_premultiplied():
    img = Image.new("RGBA", (1, 1), (200, 100, 50, 128))
    b, g, r, a = layered.to_premultiplied_bgra(img)
    assert a == 128
    assert (b, g, r) == (50 * 128 // 255, 100 * 128 // 255, 200 * 128 // 255)


def test_transparent_pixel_is_fully_zeroed():
    """A transparent pixel that keeps its colour shows as a coloured halo
    around the preview's rounded corners."""
    img = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    assert layered.to_premultiplied_bgra(img) == bytes([0, 0, 0, 0])


def test_length_is_four_bytes_per_pixel():
    img = Image.new("RGBA", (7, 5), (1, 2, 3, 4))
    assert len(layered.to_premultiplied_bgra(img)) == 7 * 5 * 4
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_layered.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement the pure half**

```python
"""Push a Pillow image onto a layered window.

Split deliberately: the byte conversion is pure and tested in CI, the
UpdateLayeredWindow call is thin enough to leave to the smoke checklist.
"""
from PIL import Image


def to_premultiplied_bgra(img: Image.Image) -> bytes:
    """Premultiplied BGRA bytes, top-down, as ULW_ALPHA requires.

    Pillow's raw encoder mode "BGRa" (lowercase a) emits premultiplied
    output directly, which avoids a per-pixel Python loop over ~67k
    pixels per repaint. The tests pin the exact byte values, so if a
    Pillow release changes that encoder they fail here rather than
    producing subtly glowing previews at runtime.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.tobytes("raw", "BGRa")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preview_layered.py -v`
Expected: PASS (4 tests)

**Verified on Pillow 12.3.0** (the version this repo resolves): `tobytes("raw",
"BGRa")` on RGBA `(200, 100, 50, 128)` returns `[25, 50, 100, 128]`, which is
exactly premultiplied BGRA. The tests above pin those bytes, so a future Pillow
that changes the encoder fails here rather than shipping glowing previews.

**If `test_half_alpha_is_premultiplied` ever fails**, swap the body for this
explicit conversion and leave the tests untouched — it produces identical bytes,
confirmed against the same cases:

```python
def to_premultiplied_bgra(img: Image.Image) -> bytes:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    raw = img.tobytes("raw", "RGBA")
    out = bytearray(len(raw))
    for i in range(0, len(raw), 4):
        r, g, b, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
        out[i] = b * a // 255
        out[i + 1] = g * a // 255
        out[i + 2] = r * a // 255
        out[i + 3] = a
    return bytes(out)
```

Prefer the encoder while it passes: this loop runs per pixel in Python, roughly
67k iterations per repaint at 320x210, and a drag repaints continuously.

- [x] **Step 5: Add the Windows push**

```python
def push(libs, hwnd, img, x, y) -> bool:
    """Blit *img* onto the layered window at absolute (x, y)."""
    import ctypes
    from . import win32

    w, h = img.size
    data = to_premultiplied_bgra(img)
    bmi = win32.BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(win32.BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h        # negative == top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0    # BI_RGB

    screen_dc = libs.user32.GetDC(None)
    mem_dc = libs.gdi32.CreateCompatibleDC(screen_dc)
    bits = ctypes.c_void_p()
    dib = libs.gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0,
                                      ctypes.byref(bits), None, 0)
    old = libs.gdi32.SelectObject(mem_dc, dib)
    try:
        ctypes.memmove(bits, data, len(data))
        blend = win32.BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        return bool(libs.user32.UpdateLayeredWindow(
            hwnd, screen_dc, ctypes.byref(win32.POINT(x, y)),
            ctypes.byref(win32.SIZE(w, h)), mem_dc,
            ctypes.byref(win32.POINT(0, 0)), 0,
            ctypes.byref(blend), win32.ULW_ALPHA))
    finally:
        # Ordered: restore the DC's original object before deleting ours,
        # or the DIB leaks for the life of the process.
        libs.gdi32.SelectObject(mem_dc, old)
        libs.gdi32.DeleteObject(dib)
        libs.gdi32.DeleteDC(mem_dc)
        libs.user32.ReleaseDC(None, screen_dc)
```

- [x] **Step 6: Commit**

```bash
git add obs_youtube_uploader/preview/layered.py tests/test_preview_layered.py
git commit -m "feat(preview): layered-window blit with premultiplied BGRA"
```

---

### Task 10: `thumbnail.py` — DWM thumbnail lifecycle

**Files:**
- Create: `obs_youtube_uploader/preview/thumbnail.py`
- Test: `tests/test_preview_thumbnail.py`

**Interfaces:**
- Consumes: `win32.bind`, `geometry.Rect`
- Produces: `Thumbnail` class with `register(libs, dest_hwnd, src_hwnd) -> Thumbnail | None`, `update(rect, opacity=255, visible=True)`, `close()`

- [x] **Step 1: Write the failing tests**

```python
"""Lifecycle only -- the DWM calls are faked. What matters here is that a
failed registration degrades instead of raising, and that close() is
idempotent: a double-unregister is a use-after-free in DWM's handle
table, and the crash lands nowhere near this file."""
from obs_youtube_uploader.preview import thumbnail
from obs_youtube_uploader.preview.geometry import Rect


class FakeDwm:
    def __init__(self, hr=0):
        self.hr, self.unregistered, self.updates = hr, [], []

    def DwmRegisterThumbnail(self, dest, src, out):
        out._obj.value = 0xABC
        return self.hr

    def DwmUnregisterThumbnail(self, handle):
        self.unregistered.append(handle)
        return 0

    def DwmUpdateThumbnailProperties(self, handle, props):
        self.updates.append(handle)
        return 0


class FakeLibs:
    def __init__(self, dwm):
        self.dwmapi = dwm


def test_registration_failure_returns_none_not_an_exception():
    libs = FakeLibs(FakeDwm(hr=0x80004005))
    assert thumbnail.Thumbnail.register(libs, 1, 2) is None


def test_close_is_idempotent():
    dwm = FakeDwm()
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 1, 2)
    t.close()
    t.close()
    assert len(dwm.unregistered) == 1


def test_update_after_close_is_a_no_op():
    """The sweep can race a client closing; an update against a freed
    handle must not reach DWM."""
    dwm = FakeDwm()
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 1, 2)
    t.close()
    t.update(Rect(0, 0, 10, 10))
    assert dwm.updates == []
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_thumbnail.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Write the implementation**

```python
"""One DWM thumbnail: register, position, release."""
import ctypes
import logging
from ctypes import wintypes

from . import win32

logger = logging.getLogger(__name__)


class Thumbnail:
    def __init__(self, libs, handle):
        self._libs, self._handle = libs, handle

    @classmethod
    def register(cls, libs, dest_hwnd, src_hwnd):
        """Returns None on failure -- a client that vanished between the
        sweep and this call is routine, not exceptional."""
        handle = wintypes.HANDLE()
        hr = libs.dwmapi.DwmRegisterThumbnail(dest_hwnd, src_hwnd,
                                              ctypes.byref(handle))
        if hr != 0:
            logger.warning("DwmRegisterThumbnail failed: hr=0x%08x src=0x%x",
                           hr & 0xFFFFFFFF, src_hwnd)
            return None
        return cls(libs, handle)

    def update(self, rect, opacity: int = 255, visible: bool = True) -> None:
        if self._handle is None:
            return
        props = win32.DWM_THUMBNAIL_PROPERTIES()
        props.dwFlags = (win32.DWM_TNP_RECTDESTINATION | win32.DWM_TNP_VISIBLE
                         | win32.DWM_TNP_OPACITY
                         | win32.DWM_TNP_SOURCECLIENTAREAONLY)
        props.rcDestination = win32.RECT(rect.x, rect.y, rect.right, rect.bottom)
        props.opacity = opacity
        props.fVisible = visible
        props.fSourceClientAreaOnly = True
        self._libs.dwmapi.DwmUpdateThumbnailProperties(self._handle,
                                                       ctypes.byref(props))

    def close(self) -> None:
        """Idempotent: a second unregister is a use-after-free in DWM's
        handle table, and it does not crash here."""
        if self._handle is None:
            return
        self._libs.dwmapi.DwmUnregisterThumbnail(self._handle)
        self._handle = None
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preview_thumbnail.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/thumbnail.py tests/test_preview_thumbnail.py
git commit -m "feat(preview): DWM thumbnail lifecycle wrapper"
```

---

### Task 11: `window.py` — one preview window

**Files:**
- Create: `obs_youtube_uploader/preview/window.py`
- Test: `tests/test_preview_window.py`

**Interfaces:**
- Consumes: `win32`, `geometry`, `chrome`, `layered`, `thumbnail`
- Produces: `PreviewWindow` with `create(libs, client, rect, on_activate)`, `move(rect)`, `set_label(text)`, `redraw()`, `close()`; and the pure helper `drag_result(start, current, rect, locked, drag_min) -> tuple[str, Rect]`

- [x] **Step 1: Write the failing tests for the pure gesture helper**

```python
"""Only the gesture arithmetic is tested here -- window creation needs a
desktop and lives in the smoke checklist.

Click-versus-drag is where this goes subtly wrong: a click that moves one
pixel must still focus the client, and a locked preview must never move
but must still activate on release."""
from obs_youtube_uploader.preview import window
from obs_youtube_uploader.preview.geometry import Rect

R = Rect(100, 100, 320, 210)


def test_a_still_press_is_a_click():
    action, rect = window.drag_result((10, 10), (10, 10), R, locked=False,
                                      drag_min=4)
    assert action == "activate" and rect == R


def test_movement_within_the_drag_threshold_is_still_a_click():
    action, _ = window.drag_result((10, 10), (12, 11), R, locked=False,
                                   drag_min=4)
    assert action == "activate"


def test_movement_past_the_threshold_is_a_drag():
    action, rect = window.drag_result((10, 10), (60, 40), R, locked=False,
                                      drag_min=4)
    assert action == "move"
    assert rect == Rect(150, 130, 320, 210)


def test_a_locked_preview_never_moves_but_still_activates():
    """Locking exists so a carefully placed layout survives a stray drag.
    It must not also break click-to-focus."""
    action, rect = window.drag_result((10, 10), (200, 200), R, locked=True,
                                      drag_min=4)
    assert action == "activate" and rect == R
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_window.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement the pure helper**

```python
def drag_result(start, current, rect, locked: bool, drag_min: int):
    """Classify a completed pointer gesture.

    Returns ("activate", unchanged_rect) or ("move", new_rect). A locked
    preview always reports "activate": the lock stops movement, not
    focus switching.
    """
    dx, dy = current[0] - start[0], current[1] - start[1]
    if locked or (abs(dx) <= drag_min and abs(dy) <= drag_min):
        return "activate", rect
    return "move", rect._replace(x=rect.x + dx, y=rect.y + dy)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preview_window.py -v`
Expected: PASS (4 tests)

- [x] **Step 5: Implement `PreviewWindow`**

Add the Windows half in the same module.

**Creation.** Register the window class once per process, then
`CreateWindowExW(WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST, ..., WS_POPUP, ...)`,
show with `SW_SHOWNOACTIVATE`, `redraw()`, then register a `Thumbnail`. Append
the `WNDPROC` object to `win32._KEEPALIVE`.

**Message handling.** There is no `WM_SIZING` here: the window is `WS_POPUP` with
no frame, so Windows never negotiates a resize. Both moving and resizing are
driven entirely by mouse messages, and which one you are doing is decided at
button-down by `geometry.hit_resize_handle`:

| Message | Action |
|---|---|
| `WM_LBUTTONDOWN` | `SetCapture`; record start point and current rect; set mode to `resize` if `hit_resize_handle(rect, x, y)` else `drag` |
| `WM_MOUSEMOVE` (captured, `drag`) | new rect = start rect offset by the delta, then `geometry.snap(rect, other_rects, screen)`; `SetWindowPos` + `redraw()` |
| `WM_MOUSEMOVE` (captured, `resize`) | new rect = start rect with `w`/`h` grown by the delta, floored at `MIN_SIZE`; `SetWindowPos` + `redraw()` |
| `WM_LBUTTONUP` | `ReleaseCapture`; feed `drag_result`; on `"activate"` call `on_activate(client.hwnd)`; on `"move"`/resize report the final rect to the host so it can persist |
| `WM_RBUTTONDOWN`/`UP` | same as left-button drag, but never activates — right-drag moves a locked preview |
| `WM_DESTROY` | release the thumbnail if still held |

Everything else goes to `DefWindowProcW`.

**`other_rects` for snapping** is supplied by the host, which is the only thing
that knows about sibling previews — `PreviewWindow.create()` takes a
`neighbours: Callable[[], list[Rect]]` returning every *other* preview's rect.
Without that callback `geometry.snap` only ever sees screen edges, and
preview-to-preview snapping silently does nothing.

**`redraw()`** calls `chrome.render(...)`, then `layered.push(...)`, then
`thumbnail.update(geometry.thumbnail_rect(...))`.

**`close()`** closes the thumbnail **before** `DestroyWindow` — the thumbnail's
destination is this window.

- [x] **Step 6: Implement the focus sequence**

Click-to-focus is the feature, and `SetForegroundWindow` alone does not work:
Windows refuses it from a process that does not own the foreground. The
two-stage `AttachThreadInput` dance is required.

```python
def activate(libs, hwnd) -> bool:
    """Bring *hwnd* to the foreground. Returns whether it actually worked.

    The verdict is read from GetForegroundWindow, never from
    SetForegroundWindow's return value -- it reports that the request was
    accepted, not that the window came forward.

    Every attach MUST be balanced by a detach, including on the failure
    path: a leaked attachment welds two threads' input queues together for
    the life of the process, and the symptom is EVE's keyboard input
    arriving in the wrong client.
    """
    if libs.user32.IsIconic(hwnd):
        libs.user32.ShowWindowAsync(hwnd, 9)  # SW_RESTORE

    current = libs.user32.GetForegroundWindow()
    if current == hwnd:
        return True

    our_tid = libs.kernel32.GetCurrentThreadId()
    fg_tid = libs.user32.GetWindowThreadProcessId(current, None)
    target_tid = libs.user32.GetWindowThreadProcessId(hwnd, None)

    attached = []
    try:
        for tid in (fg_tid, target_tid):
            if tid and tid != our_tid and libs.user32.AttachThreadInput(our_tid, tid, True):
                attached.append(tid)
        libs.user32.SetForegroundWindow(hwnd)
    finally:
        for tid in attached:
            libs.user32.AttachThreadInput(our_tid, tid, False)

    return libs.user32.GetForegroundWindow() == hwnd
```

Log at debug when it returns False — a client that refuses to come forward is
the single most likely field complaint, and without this line there is nothing
to go on.

- [x] **Step 7: Commit**

```bash
git add obs_youtube_uploader/preview/window.py tests/test_preview_window.py
git commit -m "feat(preview): per-client layered preview window"
```

---

### Task 12: `host.py` — the thread, the pump, the lifecycle

**Files:**
- Create: `obs_youtube_uploader/preview/host.py`
- Test: `tests/test_preview_host.py`

**Interfaces:**
- Consumes: `discovery`, `window`, `win32`, `geometry`, `layout`
- Produces: `PreviewHost(on_layout_changed)` with `start()`, `stop(timeout=5.0)`, `is_running` property, and the pure helper `reconcile(current, desired) -> tuple[list, list, list]` returning `(added, removed, kept)` stable keys.

- [x] **Step 1: Write the failing tests**

```python
"""Reconciliation and lifecycle. The pump itself is smoke-tested.

reconcile() is where a leak would live: a client that disappears without
being removed leaves a thumbnail registered against a dead source and a
window that never closes."""
from obs_youtube_uploader.preview import host


def test_reconcile_reports_additions_and_removals():
    added, removed, kept = host.reconcile({"A", "B"}, {"B", "C"})
    assert set(added) == {"C"}
    assert set(removed) == {"A"}
    assert set(kept) == {"B"}


def test_reconcile_of_an_empty_desired_set_removes_everything():
    """EVE closing entirely must tear every preview down, not leave them
    showing the last frame of a dead client."""
    added, removed, kept = host.reconcile({"A", "B"}, set())
    assert set(removed) == {"A", "B"} and not added and not kept


def test_stop_before_start_is_a_no_op():
    h = host.PreviewHost(on_layout_changed=lambda _: None)
    h.stop()
    assert not h.is_running


def test_stop_is_idempotent(monkeypatch):
    h = host.PreviewHost(on_layout_changed=lambda _: None)
    monkeypatch.setattr(h, "_run", lambda: None)
    h.start()
    h.stop()
    h.stop()
    assert not h.is_running
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_host.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `reconcile` and the lifecycle shell**

```python
def reconcile(current: set, desired: set):
    """(added, removed, kept) stable keys between two sweeps."""
    return sorted(desired - current), sorted(current - desired), sorted(current & desired)
```

`PreviewHost.start()` spawns a daemon thread running `_run()`. `_run()` must, in order:

1. `SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)`, logging the result (Task 1 verified this).
2. **Create the host's message-only window** (see below).
3. Create the previews for the current sweep.
4. Install `SetWinEventHook` for `EVENT_SYSTEM_FOREGROUND`.
5. `SetTimer(host_hwnd, SWEEP_TIMER_ID, 700, None)` — the discovery sweep.
6. Run `GetMessageW` / `TranslateMessage` / `DispatchMessageW` until `WM_QUIT`.

**The host owns a message-only window, and this is not optional.** `PostMessageW`
needs an HWND, and there is no preview window to post to when zero clients are
running — which is the state at startup and after the last client quits. Without
it, `stop()` has nothing to signal and hangs until its timeout on exactly the
paths that matter most. Create it first, before any preview:

```python
# HWND_MESSAGE parent: never visible, never in the taskbar, exists purely
# to own this thread's timer and command queue. It outlives every preview,
# so shutdown and the sweep always have a target.
self._hwnd = libs.user32.CreateWindowExW(
    0, HOST_CLASS, "wingman-preview-host", 0, 0, 0, 0, 0,
    win32.HWND_MESSAGE, None, hinst, None)
```

**The sweep** is a `WM_TIMER` on that window, not a `threading.Timer`: it must run
on the preview thread, because it creates and destroys HWNDs. Each tick:

1. `discovery.list_clients()`, then `discovery.flush_image_cache_periodically()`.
2. `added, removed, kept = reconcile(current_keys, desired_keys)`.
3. For `removed`: `PreviewWindow.close()` and drop from the registry.
4. For `added`: resolve a rect — saved layout for that `stable_key`, else
   `geometry.default_stack(len(registry), screen, size)` — and create a window.
5. For `kept`: nothing. Do **not** rebuild a live preview; re-registering its
   thumbnail every 700ms is a visible flicker.

`EVENT_SYSTEM_FOREGROUND` posts a message asking for an immediate sweep rather
than sweeping inline — the hook callback arrives on an arbitrary thread, and
touching HWNDs from it is the thread-affinity violation that hangs.

`stop(timeout=5.0)` posts `WM_APP_SHUTDOWN` to the host window and joins. On the
preview thread, shutdown runs in this exact order — the design's Lifecycle section:

1. `UnregisterHotKey` (no-op in the first slice; the call site exists so Task 7-deferred hotkeys have somewhere to land).
2. `UnhookWinEvent`.
3. `Thumbnail.close()` for every preview.
4. `DestroyWindow` for every preview.
5. `KillTimer`, then `DestroyWindow(host_hwnd)`.
6. `PostQuitMessage(0)`.

Then the joiner logs if the thread does not exit inside `timeout` — a `stop()` that returns while the thread still owns HWNDs produces a Wingman that vanishes from the tray but lingers in Task Manager.

`stop()` must also `flush()` the layout store (Task 13) *before* destroying
windows, or the last drag before quitting is lost to the debounce.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preview_host.py -v`
Expected: PASS (4 tests)

- [x] **Step 5: Commit**

```bash
git add obs_youtube_uploader/preview/host.py tests/test_preview_host.py
git commit -m "feat(preview): host thread, pump, and ordered teardown"
```

---

### Task 13: Settings integration, single-writer

**Files:**
- Modify: `obs_youtube_uploader/settings.py` — `DEFAULTS`, `_preview_defaults()`, `_fresh_defaults()` (`settings.py:64-68`), `validated_preview()`, and a module-level save lock
- Modify: `tests/test_settings.py:6-28` — the exact-DEFAULTS assertion
- Create: `obs_youtube_uploader/preview/store.py`
- Test: `tests/test_preview_store.py`, `tests/test_settings_preview.py`

**Interfaces:**
- Consumes: `layout.serialize`, `layout.deserialize`
- Produces: `LayoutStore(save_settings, read_settings, debounce_s=1.0, timer=threading.Timer)` with `record(stable_key, entry)` and `flush()`

- [x] **Step 1: Write the failing tests**

```python
"""The preview thread must never call settings.save(): it rewrites the
whole projected document (settings.py:145-149), so two writers lose each
other's keys entirely. This store is the single-writer boundary."""
from obs_youtube_uploader.preview.store import LayoutStore
from obs_youtube_uploader.preview.layout import Entry
from obs_youtube_uploader.preview.geometry import Rect


class FakeTimer:
    """Runs nothing until fire() is called, so debouncing is testable
    without sleeping -- the scheduler.py injection pattern."""
    def __init__(self, interval, fn):
        self.fn, self.cancelled = fn, False
    def start(self): pass
    def cancel(self): self.cancelled = True
    def fire(self): self.fn()


def _store(saves):
    timers = []
    def timer(interval, fn):
        t = FakeTimer(interval, fn); timers.append(t); return t
    s = LayoutStore(save_settings=saves.append,
                    read_settings=lambda: {"preview": {"layouts": {}}},
                    timer=timer)
    return s, timers


def test_a_drag_does_not_write_once_per_pixel():
    """Dragging emits a rect per mouse-move. Writing each one would
    rewrite the settings file dozens of times a second."""
    saves = []
    s, timers = _store(saves)
    for x in range(20):
        s.record("Pilot", Entry(Rect(x, 0, 320, 210)))
    assert saves == []
    timers[-1].fire()
    assert len(saves) == 1


def test_the_last_position_is_the_one_written():
    saves = []
    s, timers = _store(saves)
    s.record("Pilot", Entry(Rect(1, 0, 320, 210)))
    s.record("Pilot", Entry(Rect(9, 0, 320, 210)))
    timers[-1].fire()
    assert saves[0]["preview"]["layouts"]["Pilot"]["x"] == 9


def test_flush_writes_immediately_for_shutdown():
    saves = []
    s, _ = _store(saves)
    s.record("Pilot", Entry(Rect(1, 2, 320, 210)))
    s.flush()
    assert len(saves) == 1


def test_layouts_for_clients_not_running_are_preserved():
    """THE bug this store exists to avoid. You multibox thirty characters and
    log in two. If the write replaces `layouts` with only what was seen this
    session, the other twenty-eight lose their saved positions -- and the user
    finds out weeks later, once, with no way to get them back."""
    saves = []
    stored = {"preview": {"layouts": {
        "Absent Pilot": {"x": 7, "y": 7, "w": 320, "h": 210, "locked": False}}}}
    timers = []
    def timer(interval, fn):
        t = FakeTimer(interval, fn); timers.append(t); return t
    s = LayoutStore(save_settings=saves.append,
                    read_settings=lambda: stored, timer=timer)
    s.record("Present Pilot", Entry(Rect(1, 2, 320, 210)))
    timers[-1].fire()
    written = saves[0]["preview"]["layouts"]
    assert set(written) == {"Absent Pilot", "Present Pilot"}
    assert written["Absent Pilot"]["x"] == 7


def test_reads_settings_at_write_time_not_at_construction():
    """settings.save() projects the WHOLE document (settings.py:145-149), so
    saving from a snapshot taken earlier writes back stale values for every
    unrelated key -- including ones another thread changed in between."""
    saves, live = [], {"preview": {"layouts": {}}, "channel_title": "before"}
    timers = []
    def timer(interval, fn):
        t = FakeTimer(interval, fn); timers.append(t); return t
    s = LayoutStore(save_settings=saves.append,
                    read_settings=lambda: live, timer=timer)
    s.record("Pilot", Entry(Rect(1, 2, 320, 210)))
    live["channel_title"] = "changed by another thread"
    timers[-1].fire()
    assert saves[0]["channel_title"] == "changed by another thread"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `store.py`**

`LayoutStore` accumulates pending entries and restarts its debounce timer on each
`record()`. On fire it must **merge, not replace**:

```python
def _write(self) -> None:
    with self._lock:
        pending, self._pending = dict(self._pending), {}
    if not pending:
        return
    live = self._read_settings()          # read at write time, never cached
    layouts = dict(live.setdefault("preview", {}).setdefault("layouts", {}))
    layouts.update(layout.serialize(pending))   # per-key merge
    live["preview"]["layouts"] = layouts
    self._save_settings(live)
```

Two properties the tests above pin, both of which a wholesale replace would break:
layouts for clients that were not running are preserved, and the document handed
to `save()` is the live dict, not a snapshot.

`flush()` cancels the timer and calls `_write()` now — the host calls it during
shutdown, before destroying windows.

`record()` is safe to call from the preview thread. Serialization is the
**lock's** job, not the calling thread's: see Step 4.

- [x] **Step 4: Add the settings schema, and serialize `save()`**

Three changes in `settings.py`, all required together:

**(a) The nested default.** Add to `DEFAULTS`:

```python
"preview": {"enabled": False, "width": 320, "height": 210,
            "opacity": 235, "layouts": {}},
```

and add a `_preview_defaults()` returning a fresh copy, then extend
`_fresh_defaults()` (`settings.py:64-68`) to rebuild it:

```python
def _fresh_defaults() -> dict:
    """dict(DEFAULTS) is shallow, so the nested section is rebuilt."""
    data = dict(DEFAULTS)
    data["eve_bookmarks"] = _eve_defaults()
    data["preview"] = _preview_defaults()      # same reason
    return data
```

Skipping this hands every caller the *same* nested dict — one window's layout
edit would silently mutate the defaults for the whole process.

**(b) `tests/test_settings.py:6-28` asserts `DEFAULTS` exactly** and will fail
the moment the key is added. Update it in this task; it is not a follow-up.

**(c) Serialize `save()`.** Add a module-level lock held across the whole
function:

```python
_SAVE_LOCK = threading.Lock()


def save(data: dict, path: Path | None = None) -> None:
    # Two writers already exist without previews: ui/api.py:722-739 persists
    # the channel from an upload worker thread, deliberately. save() projects
    # the complete document, so an interleaved pair loses one side entirely.
    # The preview store makes it three.
    with _SAVE_LOCK:
        ...existing body...
```

Then `validated_preview(raw)` following `validated_eve`'s shape
(`settings.py:141`): clamp `opacity` to 20-255, `width`/`height` to a floor,
and pass `layouts` through `layout.deserialize` then `serialize` so a corrupt
entry is dropped at load rather than at draw time.

- [x] **Step 5: Write and run the settings tests**

Mirror `tests/test_settings_eve.py`'s cases: a whole section of the wrong type
falls back, an out-of-range opacity clamps, an unknown key is dropped. Add one
for the shallow-copy hazard:

```python
def test_each_caller_gets_its_own_preview_section():
    """dict(DEFAULTS) is shallow. Without _fresh_defaults rebuilding it,
    two callers share one dict and one caller's layout edit rewrites the
    other's -- including the module-level DEFAULTS itself."""
    a, b = settings._fresh_defaults(), settings._fresh_defaults()
    a["preview"]["layouts"]["X"] = {"x": 1, "y": 1, "w": 2, "h": 2}
    assert b["preview"]["layouts"] == {}
    assert settings.DEFAULTS["preview"]["layouts"] == {}
```

Run: `python -m pytest tests/test_preview_store.py tests/test_settings_preview.py tests/test_settings.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add obs_youtube_uploader/preview/store.py obs_youtube_uploader/settings.py \
        tests/test_preview_store.py tests/test_settings_preview.py tests/test_settings.py
git commit -m "feat(preview): debounced layout persistence, serialised saves"
```

---

### Task 14: Wire into the app — enable, disable, shut down

**Files:**
- Modify: `obs_youtube_uploader/__main__.py:410-416` (shutdown)
- Modify: `obs_youtube_uploader/ui/api.py` (enable/disable endpoint)
- Modify: `obs_youtube_uploader/web/settings.js`, `obs_youtube_uploader/web/index.html`
- Test: `tests/test_preview_wiring.py`

- [x] **Step 1: Write the failing tests**

```python
"""Wiring, with the host faked. What must hold: the subsystem is lazy,
and shutdown always tears it down.

`make_api` is the existing helper at tests/test_api.py:56 -- imported, not
redefined. It takes tmp_path positionally and forwards **kwargs to Api(),
so the preview host arrives the same way every other collaborator does.
"""
from tests.test_api import make_api


class FakeHost:
    def __init__(self):
        self.started = self.stopped = 0

    def start(self):
        self.started += 1

    def stop(self, timeout=5.0):
        self.stopped += 1


def test_disabled_at_startup_never_starts_the_thread(tmp_path):
    """A user who never touches EVE previews must not pay a thread and a
    700ms sweep for a feature they have off."""
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": False}
    api.startup()
    assert host.started == 0


def test_enabling_starts_it_and_disabling_stops_it(tmp_path):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": False}
    api.set_preview_enabled(True)
    assert host.started == 1
    api.set_preview_enabled(False)
    assert host.stopped == 1


def test_enabling_twice_does_not_start_two_threads(tmp_path):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": False}
    api.set_preview_enabled(True)
    api.set_preview_enabled(True)
    assert host.started == 1


def test_shutdown_stops_the_host_even_when_enabled(tmp_path):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": True}
    api.startup()
    api.shutdown()
    assert host.stopped == 1
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview_wiring.py -v`
Expected: FAIL

- [x] **Step 3: Implement the wiring**

Add a `preview_host=None` keyword to `Api.__init__`, and `set_preview_enabled(bool)`
to `ui/api.py`, persisting through the normal settings path and starting/stopping
the host. Add `PreviewHost.stop()` to the shutdown sequence at
`__main__.py:410-416`, alongside the scheduler and bookmark engine. Add an enable
checkbox to the settings pane, following the existing bookmarks controls' markup
and classes.

`from tests.test_api import make_api` **resolves** under this project's pytest
invocation — verified by running it, despite there being no `tests/__init__.py`
and no `conftest.py`; pytest puts the rootdir on `sys.path`. No fixture
extraction is needed. It does mean the import breaks if anyone ever runs pytest
from inside `tests/`, so if that becomes a habit, move `make_api`/`make_state`
into a `tests/conftest.py` then.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preview_wiring.py -v`
Expected: PASS (4 tests)

- [x] **Step 5: Run the whole suite**

Run: `python -m pytest -q`
Expected: **`869 passed`, zero failures**, plus the tests added by this plan.

This baseline is measured on `bump-3.2.0`, not estimated. The suite is
**fully green** — there are no known-failing tests to write off. Any failure
you see is either yours or a genuine regression; do not normalize one.

(An earlier draft of this plan claimed ~107 pre-existing failures. That was a
stale measurement taken in a different checkout, where the bookmarks work was
still untracked and unfinished before it merged as `70c1655`. Following it
would have masked real regressions.)

- [x] **Step 6: Commit**

```bash
git add obs_youtube_uploader/__main__.py obs_youtube_uploader/ui/api.py \
        obs_youtube_uploader/web/ tests/test_preview_wiring.py
git commit -m "feat(preview): enable/disable from the UI, teardown on shutdown"
```

---

### Task 15: Smoke checklist

The Windows half is deliberately thin and untested by CI. This is what stands in for that.

**Files:**
- Modify: `docs/smoke-checklist.md` — append a `## EVE client previews` section

- [x] **Step 1: Write the checklist**

The repo has one smoke-check document, not several. Append a section alongside
the existing `## EVE bookmark hotkeys` block (`docs/smoke-checklist.md:773-850`)
and match its style: each item states what to do, what to observe, and what a
failure looks like. Cover at minimum:

1. Two clients running → two previews appear, showing live video.
2. Click a preview → that client comes to the foreground.
3. Drag a preview → it moves; release near another → it snaps.
4. Resize from the bottom-right → the thumbnail follows the frame.
5. Restart Wingman → previews return to their saved positions.
6. Close one EVE client → its preview disappears; the others keep rendering.
7. Close every EVE client → no previews, no crash, thread still healthy.
8. Disable in settings → previews vanish and the thread exits (check Task Manager for a lingering process).
9. Quit Wingman with previews enabled → the process fully exits.
10. Two monitors at different scales → previews land correctly on both (this is Task 1's DPI work paying off, and the one item most likely to fail).
11. Check the log for `SetThreadDpiAwarenessContext` result, DWM registration failures, and thread death.

- [x] **Step 2: Run it on Windows and record the results**

- [x] **Step 3: Commit**

```bash
git add docs/smoke-checklist.md
git commit -m "docs: preview subsystem smoke checks"
```

---

## Self-Review

**Spec coverage.** Each first-slice item maps to a task: discovery → 6, 7; layered window + Pillow chrome + thumbnail → 2, 4, 8, 9, 10, 11; click-to-focus → 11 (`drag_result`) and the `AttachThreadInput` sequence in Task 11 Step 5; drag/resize/snapping → 3, 11; persistence → 5, 13; enable/disable → 14. Cross-cutting spec sections: DPI → 1 and Task 12 Step 3; lifecycle → 12; observability → the logging called for in 7, 10, 12; packaging → 2; single-writer settings → 13; frozen `list_eve_windows` → 6.

**Deferred, deliberately:** hotkeys, cycle groups, labels beyond the character name, alerts, minimize-inactive, client-layout save/restore, profiles, EVE-O import. Task 12's teardown reserves the `UnregisterHotKey` call site so hotkeys have somewhere to land without restructuring.

**Type consistency.** `Rect` is defined once in `geometry.py` and used unchanged by `layout`, `window`, `thumbnail`, and `host`. `Client.stable_key` is the identity used by `layout.Entry` keys, `host.reconcile`, and `store.record`. `Thumbnail.close()` and `PreviewHost.stop()` are the two idempotent teardown methods; neither is spelled `dispose` anywhere.

**Known gap.** Task 11's window body and Task 12's sweep are specified as
message-by-message tables and ordered sequences rather than complete listings.
That is a judgement, not an omission: both are long, mechanical Win32 bodies
where a listing written now would be wrong on contact with a real desktop, and
the constraints that actually matter — message routing, ordering, which thread
owns what — are pinned exactly. The focus sequence in Task 11 Step 6 and the
merge in Task 13 Step 3 *are* given as code, because both are places where a
plausible-looking implementation is silently wrong: a leaked
`AttachThreadInput` welds two input queues together, and a wholesale layout
replace deletes saved positions the user cannot recover.

**Sequencing.** Every task is startable — the licence gate that previously
held tasks 10-15 is gone, since the relicense lands in this same change. Task 1
(the DPI probe) still comes first: it is the one result that can invalidate the
architecture, and finding that out after tasks 8-12 are written is the expensive
order.

**Revision note.** This plan was revised after an independent review found eight
defects, four blocking. The corrections worth carrying forward: the suite is
**fully green** on this branch (869 passed — an earlier draft's "107 known
failures" was a stale measurement from a different checkout and would have masked
regressions); `settings.save()` already has two writers, so previews make three
and the fix is a lock rather than a thread rule; the bundled font must reach
`uploader.spec`'s `datas` or the frozen build silently falls back; and
`_fresh_defaults` must rebuild the nested `preview` section or every caller
shares one mutable dict.

---

## Execution notes

All fifteen tasks executed. Suite: **956 passed, 2 skipped** on Linux.
On Windows, 2 pre-existing failures remain, both confirmed against the
untouched checkout and neither caused by this work — `test_discord.py`'s
`chmod` test (Windows ignores the permission change) and
`test_hotkeys_commands.py`'s BOM test (`write_text` without an encoding
picks cp1252, which cannot encode `\ufeff`). CI never saw either because
it runs `ubuntu-latest`.

Deviations from the plan as written, and why:

- **Task 8**: `ctypes.wintypes` and `Structure` definitions *do* work on
  Linux; `WINFUNCTYPE`, `WinDLL` and `windll` do not. So structs and
  constants stayed module-level as planned, and only the callback types
  and `bind()` became lazy.
- **Task 11**: added `resize_result` and signed `_lparam_point` decoding,
  neither in the plan. Unsigned lParam decoding sends a preview to the far
  edge of the desktop the moment a drag goes above or left of its origin.
- **Task 13**: `save()` became a lock wrapper around `_save_locked` rather
  than growing a `with` inside the existing body.
- **Task 14**: the JS bridge helpers are `WM.send`/`WM.handle`, not the
  `WM.api`/`WM.on`/`WM.toast` the plan guessed. `set_preview_enabled`
  returns `True` because `WM.send` resolves to `null` on failure and
  cannot otherwise tell that from a method returning `None`.
- **Post-plan fix**: placement and snapping used a hardcoded
  `Rect(0, 0, 1920, 1080)`. The real virtual desktop on the dev machine is
  `Rect(x=-2560, y=0, w=8960, h=1746)`. Replaced with the four
  `SM_*VIRTUALSCREEN` metrics behind a pure, testable helper.

One test carries a known limit worth remembering:
`test_build_preview_host_body_is_exercised` only catches names resolved
**eagerly**. It went green against a real bug (`lambda data:
settings.save(data)` — wrong module alias) because a lambda body is not
executed at build time. Callbacks constructed there should be bound
method references, not lambdas wrapping them.

Not yet done, and the only thing standing between this and a usable
feature: **nobody has run it**. The smoke checklist in
`docs/smoke-checklist.md` has never been executed, so no preview has been
seen on screen from this code — only from the throwaway probes. The
multi-monitor item is the one most likely to fail.
