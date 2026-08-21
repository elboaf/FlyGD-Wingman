# UI Layout and Information Design Implementation Plan

> **HISTORICAL RECORD — delivered. Do not implement from this file.**
> `ui-layout-design.md` is the current authority; where the two disagree the
> design doc wins. Two figures here were superseded by measurement during
> implementation and are deliberately left as written: the window floor is
> **860px**, not the 750px this plan assumes throughout (only `filename`'s
> minimum is reachable, so the columns need 490px of viewport), and
> `format_selection_summary([])` returns `"Nothing selected"`, which the
> empty-selection assertion in Task 6 did not expect.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the main window into a two-pane layout — recording list beside an upload panel — with margins, DPI-scaled spacing, correctly sized and aligned columns, and a dark title bar on both windows.

**Architecture:** No module boundaries move. `library.py`, `durations.py`, `uploader.py`, `stitch.py`, `combatlog.py` and `discord.py` are untouched. Work is confined to `app.py` (layout), `settingsui.py` (spacing, title bar) and `theme.py` (title bar), plus two new pure formatter functions that carry the only non-trivial logic and are therefore unit-testable without a display.

**Tech Stack:** Python 3, Tkinter/ttk, sv-ttk (already integrated by PR #5), Pillow (checkbox images), pytest.

**Spec:** `ui-layout-design.md` — read it first; this plan argues from it and the two travel together.

## Global Constraints

- **Theming is DONE and out of scope.** sv-ttk, OS dark/light following, DPI awareness, the `ttk.Treeview` list and the app icon all landed in PR #5 (`80087c4`). Do not redo, restyle, or "improve" any of it. The one exception is the dark title bar, which is explicitly requested scope (Task 7).
- **No new features, and no capability may be removed.** The "Upload combat logs" button and the Discord settings frame must both survive. So must the conditional "(ffmpeg not found — stitching unavailable)" label, which is an explicit smoke-test item (`docs/smoke-checklist.md:37-41`).
- **The app is Windows-only; the test suite runs on Linux and has no UI tests.** `docs/smoke-checklist.md` is the only thing that tests UI behaviour on the target platform. Anything unverifiable off Windows goes there as a checklist entry rather than being claimed as done.
- **A real display IS available (WSLg, `DISPLAY=:0`).** Prefer constructing real widgets over reasoning about layout. Two traps where a wrong check looks identical to a right one:
  - Call `root.update()` before reading geometry — every `winfo_*` is zero until you do.
  - Drive DPI the way `__main__.main()` does — `root.tk.call("tk", "scaling", dpi / 72.0)` — **never** by monkeypatching `dpi_scale`.
- **This host's Tk has no Xft**, so `tkfont.families()` returns only `"fixed"`, a bitmap font. Font linespace and metrics measurements are meaningless here. Never assert on font metrics in a test; put those checks in the smoke checklist.
- **The editable install points at a DIFFERENT worktree.** Run throwaway scripts with `PYTHONPATH=$PWD` or from the repo root, or you will silently import the wrong code. `pytest` is unaffected.
- **Spacing:** every pixel constant is multiplied by the DPI scale via the `Spacing` helper from Task 1. A raw pixel literal in layout code is a bug — it is the exact defect this work exists to fix.
- **Commit after every task**, and keep the suite green at every commit. The baseline is 335 passing.

---

## Task Order and Dependencies

Tasks are ordered so each one consumes only what earlier tasks have already
produced. Two orderings were rejected: putting the restructure (Task 5) before
the column spec (Task 3) would have it copy the old column code forward and
silently revert it, and putting typography (Task 4) after the panel would leave
the panel's heading with a hand-rolled font instead of the shared style.

| # | Task | Depends on |
|---|---|---|
| 1 | Scaled spacing | — |
| 2 | Pure formatters | — |
| 3 | Treeview columns | 1 (insertion point only) |
| 4 | Typographic hierarchy | 3 |
| 5 | Two-pane main window | 1, 3, 4 |
| 6 | Selection summary | 2, 5 |
| 7 | Dark title bar | — |

---

### Task 1: Scaled spacing

**Files:**
- Modify: `obs_youtube_uploader/app.py` (lines 74-82, the `PAD_*`/`FRAME_PADDING` block; `_build`'s padding call sites, 182-284)
- Modify: `obs_youtube_uploader/settingsui.py` (`_build`, lines 106-231)
- Create: `tests/test_app.py`

**Interfaces:**
- Consumes: `app.dpi_scale(widget: tk.Misc) -> float` (existing, unchanged)
- Produces:
  - `app.Spacing` — frozen dataclass with `tight: int`, `normal: int`, `loose: int`, `margin: int`, `frame: int`, declared in that order
  - `app.spacing(widget: tk.Misc) -> Spacing`
  - Removes `app.PAD_TIGHT`, `app.PAD_NORMAL`, `app.PAD_LOOSE`, `app.FRAME_PADDING`

- [ ] **Step 1: Write the failing test**

Create `tests/test_app.py`. It deliberately does **not** create a real `tk.Tk()`: no existing test does, and `tests/test_main.py:213-244` already drives `dpi_scale` through a `SimpleNamespace` whose `tk.call` returns the scaling value. The value fed in is the one `__main__.main()` really writes (`tk_scaling_for(dpi)`), so this exercises the real arithmetic rather than stubbing it.

```python
from types import SimpleNamespace

import pytest

from obs_youtube_uploader import app as app_mod
from obs_youtube_uploader.__main__ import tk_scaling_for


def _widget_at(dpi: int):
    """A widget whose `tk scaling` is what __main__.main() would have set for
    this DPI. Monkeypatching dpi_scale instead would prove only that the
    multiplication happens, not that it is fed the value the app really
    installs -- the two halves of that contract have drifted before
    (test_main.test_tk_scaling_and_dpi_scale_round_trip)."""
    return SimpleNamespace(tk=SimpleNamespace(
        call=lambda *args, _v=tk_scaling_for(dpi): _v))


def test_spacing_base_values_at_100_percent():
    pad = app_mod.spacing(_widget_at(96))
    assert (pad.tight, pad.normal, pad.loose, pad.margin, pad.frame) == (
        4, 8, 12, 16, 8)


@pytest.mark.parametrize("dpi, expected", [
    (96, (4, 8, 12, 16, 8)),
    (120, (5, 10, 15, 20, 10)),
    (144, (6, 12, 18, 24, 12)),
])
def test_spacing_scales_with_tk_scaling(dpi, expected):
    pad = app_mod.spacing(_widget_at(dpi))
    assert (pad.tight, pad.normal, pad.loose, pad.margin, pad.frame) == expected


def test_spacing_never_collapses_to_zero():
    """A pathological scale must still leave a visible gap: 0 padding reads as
    a layout bug, not as small spacing."""
    widget = SimpleNamespace(tk=SimpleNamespace(call=lambda *args: 0.01))
    pad = app_mod.spacing(widget)
    assert min(pad.tight, pad.normal, pad.loose, pad.margin, pad.frame) >= 1


def test_spacing_is_immutable():
    pad = app_mod.spacing(_widget_at(96))
    with pytest.raises(Exception):
        pad.tight = 99


def test_old_unscaled_pad_constants_are_gone():
    """They are removed, not deprecated: leaving them importable invites a new
    call site that silently ignores DPI."""
    for name in ("PAD_TIGHT", "PAD_NORMAL", "PAD_LOOSE", "FRAME_PADDING"):
        assert not hasattr(app_mod, name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_app.py -q`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.app' has no attribute 'spacing'`

- [ ] **Step 3: Write the implementation**

Replace `app.py` lines 74-82 (the comment block plus the four constants) with:

```python
@dataclass(frozen=True)
class Spacing:
    """DPI-scaled spacing steps.

    Derived from dpi_scale() rather than kept as fixed pixels, because the
    unscaled constants this replaces were the reason high-DPI layouts grew
    while the space between things did not: at 150% every control was half
    again as tall inside gaps still measured for 96 DPI.

    Frozen so a window cannot mutate the steps for one section and leave the
    rest of the app disagreeing about what "loose" means.
    """
    tight: int    # within one control group (e.g. buttons in one row)
    normal: int   # between controls in a section
    loose: int    # between sections
    margin: int   # window edge; new step, no unscaled equivalent existed
    frame: int    # internal padding of a bordered frame


def spacing(widget: tk.Misc) -> Spacing:
    """Scale the 100% base steps for *widget*'s display.

    max(1, ...) rather than a plain round: a scale small enough to round a
    step to 0 would read as a layout bug (controls touching), not as tight
    spacing. Callers take this once per build and reuse the result, so the
    Tcl round-trip in dpi_scale() is paid once per window, not per widget.
    """
    scale = dpi_scale(widget)
    return Spacing(
        tight=max(1, int(round(4 * scale))),
        normal=max(1, int(round(8 * scale))),
        loose=max(1, int(round(12 * scale))),
        margin=max(1, int(round(16 * scale))),
        frame=max(1, int(round(8 * scale))),
    )
```

`dataclass` is already imported at `app.py:10`; no import change is needed.

- [ ] **Step 4: Swap `app.py`'s call sites — swap only, do not restructure**

Task 5 restructures `_build`. Here every `PAD_*`/`FRAME_PADDING` reference becomes the scaled equivalent and nothing moves, so the tree stays green and the restructure lands as a reviewable diff of its own.

At the top of `_build`, before the `meta` LabelFrame:

```python
        # One lookup for the whole build, mirroring settingsui._build: the
        # Tcl scaling round-trip is per-window state, not per-widget.
        pad = spacing(self.root)
```

Then substitute throughout `_build`, leaving surrounding structure and comments untouched:

| Old | New |
|---|---|
| `padding=FRAME_PADDING` | `padding=pad.frame` |
| `padx=PAD_NORMAL` | `padx=pad.normal` |
| `pady=PAD_TIGHT` | `pady=pad.tight` |
| `pady=PAD_NORMAL` | `pady=pad.normal` |
| `padx=PAD_TIGHT` | `padx=pad.tight` |
| `padx=(0, PAD_LOOSE)` | `padx=(0, pad.loose)` |
| `padx=(PAD_LOOSE, PAD_TIGHT)` | `padx=(pad.loose, pad.tight)` |
| `pady=(0, PAD_NORMAL)` | `pady=(0, pad.normal)` |
| `pady=(PAD_TIGHT, 0)` | `pady=(pad.tight, 0)` |

- [ ] **Step 5: Give the Settings dialog an outer margin**

`settingsui._build` packs six frames straight onto `self.win` with `padx=PAD_NORMAL` and no top/bottom margin at all, so the first frame sits flush against the title bar. Introduce one `body` frame that owns the margin and re-parent the six frames to it.

Replace the `scale` preamble (lines 107-111) with:

```python
        # One lookup for the whole build. Every raw pixel constant below is
        # multiplied by this, the same factor app.dpi_scale() gives the main
        # window - character widths (Entry/Combobox `width=`) are NOT pixels
        # and are deliberately left alone.
        scale = app_mod.dpi_scale(self.win)
        pad = app_mod.spacing(self.win)

        # The margin lives on one container rather than on each frame's padx.
        # Per-frame padding gives horizontal breathing room only, which is why
        # the dialog had no gap above the first frame or below Save/Cancel;
        # and it is measured after this runs (winfo_reqwidth, __init__) so the
        # margin has to be inside the geometry request, not outside it.
        body = ttk.Frame(self.win, padding=pad.margin)
        body.pack(fill=tk.BOTH, expand=True)
```

For each of the six top-level frames — `acct`, `up`, `beh`, `disc`, `folder`, and the trailing `row` — change the parent from `self.win` to `body`, drop the now-redundant `padx`, and scale the `pady`:

```python
        acct = ttk.LabelFrame(body, text="Google account",
                              padding=pad.frame)
        acct.pack(fill=tk.X, pady=pad.tight)
```

and the last one:

```python
        row = ttk.Frame(body)
        row.pack(fill=tk.X, pady=pad.tight)
        ttk.Button(row, text="Save", command=self._save,
                   style="Accent.TButton").pack(side=tk.RIGHT)
        ttk.Button(row, text="Cancel", command=self.win.destroy).pack(
            side=tk.RIGHT, padx=pad.tight)
```

Every remaining `app_mod.PAD_TIGHT` inside those frames becomes `pad.tight`, and every `padding=app_mod.FRAME_PADDING` becomes `padding=pad.frame`. No other value changes.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS (335 existing plus the new cases; no test referenced the removed constants)

- [ ] **Step 7: Verify no stale references remain**

Run: `grep -rn "PAD_TIGHT\|PAD_NORMAL\|PAD_LOOSE\|FRAME_PADDING" obs_youtube_uploader tests`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/app.py obs_youtube_uploader/settingsui.py tests/test_app.py
git commit -m "Replace the unscaled PAD_* constants with a DPI-scaled Spacing scale

The four module constants were fixed pixels, so at 125%/150% every control
grew while the gaps between them did not. spacing() derives all five steps
from the existing dpi_scale(), and adds the window-edge 'margin' step the old
scale lacked -- which is why the Settings dialog had no outer margin to reach
for. app.py's layout is otherwise untouched here; the restructure is separate."
```

---
### Task 2: Pure formatters: date and selection summary

**Files:**
- Modify/Test: `tests/test_app.py` (append; the file and its module docstring are created by Task 1)
- Modify/Test: `tests/test_library.py` (replace `test_date_str_matches_mtime`, lines 193-196; append new date tests)
- Modify: `obs_youtube_uploader/library.py` (insert `format_date` after `format_size`, line 27; rewrite `VideoInfo.date_str`, lines 43-45)
- Modify: `obs_youtube_uploader/app.py` (insert `format_selection_summary` after `dpi_scale`, before the `Spacing` dataclass introduced by Task 1)

**Interfaces:**
- Consumes: `library.format_size(size_bytes: float) -> str` (unchanged); `library.VideoInfo` fields `mtime: float`, `size: int`, `duration: float | None`, `probed: bool`
- Produces:
  - `library.format_date(mtime: float, now: datetime.datetime | None = None) -> str`
  - `library.VideoInfo.date_str` (property, `-> str`) — now delegates to `format_date`
  - `app.format_selection_summary(infos: list[library.VideoInfo]) -> str`

Both are module-level pure functions with no Tk involvement. `app.py` imports cleanly with no display (verified: `python3 -c "from obs_youtube_uploader import app"` succeeds headless), so `tests/test_app.py` can import it directly; only constructing `UploaderWindow` needs a display, and nothing here does.

- [ ] **Step 1: Write the failing test for `library.format_date`**

Append to `tests/test_library.py`, and replace the existing `test_date_str_matches_mtime` (lines 193-196), which asserts the old `"%Y-%m-%d %H:%M"` format and would otherwise fail for the wrong reason:

```python
def test_format_date_omits_the_year_in_the_current_year():
    mtime = datetime.datetime(2026, 8, 20, 17, 43).timestamp()
    now = datetime.datetime(2026, 12, 1, 9, 0)
    assert library.format_date(mtime, now=now) == "Aug 20  17:43"


def test_format_date_prefixes_the_year_for_an_older_recording():
    mtime = datetime.datetime(2025, 11, 2, 22, 11).timestamp()
    now = datetime.datetime(2026, 12, 1, 9, 0)
    assert library.format_date(mtime, now=now) == "2025 Nov 02  22:11"


def test_format_date_compares_calendar_years_not_elapsed_time():
    """December 31 and the next January 1 are 24 hours apart and must still
    take opposite branches -- the rule is the calendar year, not "recent"."""
    mtime = datetime.datetime(2025, 12, 31, 23, 59).timestamp()
    now = datetime.datetime(2026, 1, 1, 0, 1)
    assert library.format_date(mtime, now=now) == "2025 Dec 31  23:59"


def test_format_date_defaults_now_to_the_clock():
    """The default path is exercised for real; only the injected `now`
    branches above pin literal strings, so this cannot become a time bomb."""
    mtime = datetime.datetime.now().timestamp()
    assert library.format_date(mtime) == library.format_date(
        mtime, now=datetime.datetime.now())


def test_date_str_delegates_to_format_date(tmp_path):
    f = _touch(tmp_path / "a.mkv", mtime=1000)
    info = library.build_info(f, None)
    assert info.date_str == library.format_date(1000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_library.py -q`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.library' has no attribute 'format_date'`

- [ ] **Step 3: Write the minimal implementation in `library.py`**

Insert after `format_size` (after line 27):

```python
def format_date(mtime: float, now: datetime.datetime | None = None) -> str:
    """Recording timestamp, with the year suppressed for the current year.

    The year is the least informative part of the string for a recording
    made this year, and `date` is the tightest non-elastic column in the
    list, so dropping it buys width without costing the user anything they
    cannot infer. The double space before the time is a poor man's column
    split: ttk.Treeview offers no alignment control *within* a cell, so the
    wider gap is what keeps the times legible as their own field.

    Changing this display format is safe only because app._sort_by keys the
    date column off info.mtime (app.py:422), never off the rendered string.
    A future sort that reads the cell text would silently start sorting
    "Aug" before "Dec".

    `now` is injectable so the year branch is testable without waiting for
    January -- the same convention as discover()'s runner= and
    theme.detect_mode's reader=.
    """
    when = datetime.datetime.fromtimestamp(mtime)
    if now is None:
        now = datetime.datetime.now()
    if when.year == now.year:
        return when.strftime("%b %d  %H:%M")
    return when.strftime("%Y %b %d  %H:%M")
```

Replace the `date_str` property (lines 43-45):

```python
    @property
    def date_str(self) -> str:
        # Delegates rather than formatting inline so the format has exactly
        # one definition and can be tested without constructing a VideoInfo
        # (and therefore without touching the filesystem).
        return format_date(self.mtime)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_library.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing test for `app.format_selection_summary`**

`tests/test_app.py` already exists — Task 1 created it, with this module docstring at the top, which stays as it is:

```python
"""Pure formatters that live in app.py.

app.py imports without a display -- only constructing UploaderWindow needs
one -- so its module-level pure functions are testable here. The Tk wiring
that consumes them has no harness in this repo (see library.py's docstring),
which is exactly why the formatting lives in a function and not inline in a
label update.
"""
```

Append the following below Task 1's existing tests. `library` may already be imported at the top of the file from Task 1; add it to the existing import line rather than duplicating it:

```python
from pathlib import Path

from obs_youtube_uploader import app, library


def _info(name="a.mkv", size=10, duration=60.0, probed=True):
    return library.VideoInfo(path=Path(name), mtime=100.0, size=size,
                             duration=duration, probed=probed)


def test_summary_of_an_empty_selection():
    assert app.format_selection_summary([]) == "Nothing selected"


def test_summary_of_one_recording_is_not_pluralised():
    """"1 selected", not "1 selecteds": the noun is elided entirely, so the
    count needs no agreement at any value."""
    summary = app.format_selection_summary([_info(size=1024, duration=5.0)])
    assert summary == "1 selected · 1.0 KB · 0:00:05"


def test_summary_totals_size_and_duration_across_recordings():
    infos = [_info(size=1024, duration=3600.0),
             _info(size=1024, duration=2700.0),
             _info(size=2048, duration=1535.0)]
    assert app.format_selection_summary(infos) == "3 selected · 4.0 KB · 2:04:35"


def test_summary_marks_the_duration_partial_when_a_probe_is_outstanding():
    infos = [_info(size=1024, duration=3600.0),
             _info(size=1024, duration=None, probed=False)]
    assert app.format_selection_summary(infos) == "2 selected · 2.0 KB · 1:00:00+"


def test_summary_size_is_never_marked_partial():
    """Size comes from stat, not from a probe, so an outstanding probe says
    nothing about it -- the "+" belongs to the duration alone."""
    infos = [_info(size=1024, duration=None, probed=False)]
    assert app.format_selection_summary(infos) == "1 selected · 1.0 KB · 0:00:00+"


def test_summary_of_a_probed_recording_with_no_duration_is_not_partial():
    """probed=True with duration=None is a finished verdict (ffprobe ran and
    could not read the file). It contributes 0 and the total stays exact --
    the row's own "?" already reports the failure."""
    infos = [_info(size=1024, duration=3600.0),
             _info(size=1024, duration=None, probed=True)]
    assert app.format_selection_summary(infos) == "2 selected · 2.0 KB · 1:00:00"


def test_summary_uses_a_middle_dot_separator():
    summary = app.format_selection_summary([_info()])
    assert " · " in summary and "|" not in summary
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python3 -m pytest tests/test_app.py -q`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.app' has no attribute 'format_selection_summary'`

- [ ] **Step 7: Write the minimal implementation in `app.py`**

Insert after `dpi_scale` (after line 72), before the `PAD_*` block:

```python
def format_selection_summary(infos: list[library.VideoInfo]) -> str:
    """The panel's "3 selected · 1.2 GB · 2:04:35" line.

    Pure, and kept out of the window class, because the label it feeds is in
    the one layer this repo has no test harness for. Everything decidable
    about the string is decided here.

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
```

- [ ] **Step 8: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS (335 existing tests, plus Task 1's and the new ones; no existing test references `date_str`'s old format apart from the one replaced in Step 1)

- [ ] **Step 9: Commit**

```bash
git add obs_youtube_uploader/library.py obs_youtube_uploader/app.py \
        tests/test_library.py tests/test_app.py
git commit -m "Add pure date and selection-summary formatters

library.format_date renders the list's date column year-first only when
the recording is not from the current year, freeing width in the tightest
non-elastic column. Safe because app._sort_by keys that column off
info.mtime (app.py:422), not the rendered string. VideoInfo.date_str
delegates to it.

app.format_selection_summary builds the upload panel's summary line.
Duration gets a trailing + when any selected recording is still
unprobed, so a partial total is never presented as complete; size never
does, since it comes from stat.

Both are pure and tested directly -- the widgets that will consume them
in a later task are in the layer with no harness."
```
### Task 3: Treeview columns: widths, alignment, density, link glyph

**Files:**
- Modify: `obs_youtube_uploader/app.py` (add module-level block after the `spacing()` helper; replace `_build` lines 204–224; replace `_apply_row_height` lines 328–376; `refresh()` line 626; `_set_link` line 858)
- Create: `tests/test_treeview_columns.py`
- Modify: `docs/smoke-checklist.md` (append to `### The list`, ~line 154; amend the Upload item at ~line 447)

**Interfaces:**
- Consumes: nothing from earlier tasks. Existing in-repo: `app.dpi_scale(widget: tk.Misc) -> float`, `UploaderWindow._sort_by(column: str) -> None`, `UploaderWindow._apply_zebra_tags() -> None`, `theme.token(name: str, mode: Mode | None = None) -> str`.
- Produces, for later tasks:
  - `app.COLUMN_SPEC: tuple[tuple[str, str, str, int, int, bool, str], ...]` — `(column_key, heading_text, sort_key, width_at_100, minwidth_at_100, stretch, anchor)`
  - `app.configure_tree_columns(tree: ttk.Treeview, scale: float, on_sort: Callable[[str], None]) -> None`
  - `app.LINK_GLYPH: str` (`"↗"`) and `app.link_cell(url: str | None) -> str`
  - `app.row_height(checkbox_height: int, linespace: int, scale: float) -> int`
  - Unchanged and depended on by the panel task: the Treeview column keys stay `("filename", "date", "size", "duration", "link")`, and `_sort_by` still dispatches on `"duration"`.

**Width arithmetic:** the preferred widths sum to 620px; the minimums sum to 410px. The list pane gets roughly 380–420px at the 750px minimum window width, so the minimums are what make that case fit.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_treeview_columns.py
"""Column geometry, header alignment, and the link glyph.

These drive a REAL Tk widget: ttk.Treeview normalises and clamps what
column()/heading() are given, so asserting on the spec tuple alone would
test the tuple rather than the widget. The suite otherwise has no UI
tests, so the fixture skips rather than fails where no display exists
(CI runs ubuntu-latest with no X server); locally WSLg provides one.

Nothing here measures font metrics: this host's Tk has no Xft, so
tkfont.families() returns only "fixed" and linespace is meaningless.
Row height is therefore tested through the pure helper, and the visual
result is a smoke-checklist item.
"""
import tkinter as tk
from tkinter import ttk

import pytest

from obs_youtube_uploader import app


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - no display (CI)
        pytest.skip(f"Tk needs a display: {exc}")
    yield r
    r.destroy()


def _tree(root, dpi):
    """Build a configured Treeview at *dpi*, driving scaling the way
    __main__.main() does rather than monkeypatching dpi_scale."""
    root.tk.call("tk", "scaling", dpi / 72.0)
    scale = app.dpi_scale(root)
    tree = ttk.Treeview(
        root,
        columns=("filename", "date", "size", "duration", "link"),
        show="tree headings",
    )
    sorted_keys = []
    app.configure_tree_columns(tree, scale, sorted_keys.append)
    tree.pack(fill=tk.BOTH, expand=True)
    # winfo_*/column readback is zeros until the widget is realised.
    root.update()
    return tree, scale, sorted_keys


@pytest.mark.parametrize("dpi,expected_scale", [(96, 1.0), (144, 1.5)])
def test_columns_match_the_spec_at_every_scale(root, dpi, expected_scale):
    tree, scale, _ = _tree(root, dpi)
    assert scale == expected_scale
    for key, text, _sort_key, width, minwidth, stretch, anchor in app.COLUMN_SPEC:
        assert tree.column(key, "width") == int(width * scale), key
        assert tree.column(key, "minwidth") == int(minwidth * scale), key
        assert bool(tree.column(key, "stretch")) is stretch, key
        assert str(tree.column(key, "anchor")) == anchor, key


def test_every_heading_is_anchored_like_its_column(root):
    # The defect being fixed: centred headers over left/right-aligned data.
    tree, _, _ = _tree(root, 96)
    for key, _text, _sort_key, _w, _m, _s, anchor in app.COLUMN_SPEC:
        assert str(tree.heading(key, "anchor")) == anchor, key


def test_filename_is_the_only_stretching_column():
    stretching = [c[0] for c in app.COLUMN_SPEC if c[5]]
    assert stretching == ["filename"]


def test_minimums_fit_the_pane_at_the_window_floor():
    # The preferred widths do not fit at the 750px minimum window width;
    # the minimums are what make that case survive.
    assert sum(c[3] for c in app.COLUMN_SPEC) == 620
    assert sum(c[4] for c in app.COLUMN_SPEC) == 410


def test_duration_header_reads_length_but_keeps_its_sort_key(root):
    # _sort_by dispatches on the column KEY, so renaming the header must
    # not rename the key.
    tree, _, sorted_keys = _tree(root, 96)
    assert str(tree.heading("duration", "text")) == "Length"
    root.tk.call(tree.heading("duration", "command"))
    assert sorted_keys == ["duration"]


def test_checkbox_header_still_sorts_by_checked(root):
    tree, _, sorted_keys = _tree(root, 96)
    root.tk.call(tree.heading("#0", "command"))
    assert sorted_keys == ["checked"]


def test_link_cell_is_a_glyph_not_a_url():
    assert app.link_cell("https://www.youtube.com/watch?v=abc") == app.LINK_GLYPH
    assert app.link_cell("") == ""
    assert app.link_cell(None) == ""


def test_link_cell_round_trips_through_a_real_row(root):
    tree, _, _ = _tree(root, 96)
    iid = tree.insert("", tk.END, values=("a.mkv", "Aug 20", "1 MB", "1:00",
                                          app.link_cell(None)))
    assert tree.set(iid, "link") == ""
    tree.set(iid, "link", app.link_cell("https://youtu.be/abc"))
    assert tree.set(iid, "link") == app.LINK_GLYPH


@pytest.mark.parametrize("checkbox,linespace,scale,expected", [
    (20, 10, 1.0, 28),   # the new comfort floor wins
    (40, 10, 1.0, 44),   # the checkbox guarantee still wins
    (10, 40, 1.0, 43),   # the line-box guarantee still wins
    (20, 10, 1.5, 42),   # the comfort floor scales with DPI
])
def test_row_height_keeps_both_old_guarantees_and_adds_a_floor(
        checkbox, linespace, scale, expected):
    assert app.row_height(checkbox, linespace, scale) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_treeview_columns.py -q`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.app' has no attribute 'COLUMN_SPEC'`

- [ ] **Step 3: Write minimal implementation — the module-level spec and helpers**

Insert after the `spacing()` helper:

```python
# Treeview column geometry in pixels at 100%; every value is multiplied by
# dpi_scale() when the columns are configured.
#
# The MINIMUMS are the load-bearing half. The preferred widths sum to 620px,
# but at the 750px minimum window width the list pane gets roughly 380-420px
# once the window margin, the 300px upload panel, the pane gap and the
# scrollbar are taken out, so the preferred widths do not fit. The minimums
# sum to 410px, which does, and ttk.Treeview compresses toward them.
#
# No horizontal scrollbar is added and the window minimum is not raised.
# Both were considered and rejected: on a list whose only elastic column is
# the filename, a horizontal scrollbar trades a rare annoyance for a
# permanent one, and raising the minimum cannot help on a screen where
# __main__ already clamps the geometry to the display size. A window dragged
# to its floor shows cramped columns; that is accepted, not a defect.
COLUMN_SPEC = (
    # column key, heading text, sort key, width, minwidth, stretch, anchor
    ("#0", "☑", "checked", 34, 34, False, tk.CENTER),
    ("filename", "Filename", "filename", 260, 120, True, tk.W),
    ("date", "Date", "date", 120, 90, False, tk.W),
    ("size", "Size", "size", 84, 64, False, tk.E),
    # Header text only. The KEY stays "duration" because _sort_by dispatches
    # on it, and self.infos exposes info.duration under that name.
    ("duration", "Length", "duration", 76, 56, False, tk.E),
    ("link", "Link", "link", 46, 46, False, tk.CENTER),
)

# The link column shows a glyph rather than the URL it used to render across
# ~35% of the list. Nothing is lost: the URL was never selectable inside a
# Treeview, and every consumer of a link (double-click, the context menu,
# the has_link row colour) reads self.links, not the cell.
LINK_GLYPH = "↗"


def link_cell(url: str | None) -> str:
    return LINK_GLYPH if url else ""


def configure_tree_columns(tree: "ttk.Treeview", scale: float,
                           on_sort) -> None:
    """Apply COLUMN_SPEC to *tree*, scaled by *scale*.

    Module-level rather than a method so the geometry can be verified
    against a real widget without standing up a whole UploaderWindow.
    Each heading is anchored like its column: headers were centred over
    left- and right-aligned data, which read as misalignment rather than
    as a deliberate choice.
    """
    for key, text, sort_key, width, minwidth, stretch, anchor in COLUMN_SPEC:
        tree.heading(key, text=text, anchor=anchor,
                     command=lambda k=sort_key: on_sort(k))
        tree.column(key, width=int(width * scale),
                    minwidth=int(minwidth * scale),
                    stretch=stretch, anchor=anchor)


def row_height(checkbox_height: int, linespace: int, scale: float) -> int:
    """Row height in pixels — see _apply_row_height for why each term exists.

    Split out as a pure function because the two font-derived inputs cannot
    be measured meaningfully on the Linux test host (no Xft), while the
    arithmetic that combines them is exactly what regresses.
    """
    return max(checkbox_height + 4, linespace + 3, int(28 * scale))
```

- [ ] **Step 4: Write minimal implementation — wire the Treeview**

Replace `app.py:214-224` (the `heading("#0", ...)`/`column("#0", ...)` pair and the `for key, text, chars` loop) with:

```python
        configure_tree_columns(self.tree, self._dpi_scale, self._sort_by)
```

Replace the tail of `_apply_row_height` (`app.py:369`):

```python
        needed = row_height(self._checkbox_images[True].height(), linespace,
                            self._dpi_scale)
```

and add this paragraph to that method's docstring, immediately before the
existing `Re-applied from _on_theme_changed…` paragraph, leaving every other
paragraph untouched:

```python
        A third term, int(28 * scale), is a comfort floor rather than a
        correctness one: over a hundred rows, a height that merely avoids
        clipping reads as a dense spreadsheet. It sits inside the SAME
        max() as the other two, so neither existing guarantee is weakened
        - the checkbox is still never clipped, and the measured line box
        is still never cropped. It scales because a 28px row at 200% is
        the cramped row it exists to prevent.
```

Replace the `values=` line in `refresh()` (`app.py:626`):

```python
                # link_cell rather than a literal "": refresh() has just
                # cleared self.links, so this is always empty today, but a
                # lookup states the rule instead of encoding today's answer.
                values=(info.path.name, info.date_str, info.size_str,
                        info.duration_str, link_cell(self.links.get(info.path))),
```

Replace the cell write in `_set_link` (`app.py:858`):

```python
        self.tree.set(iid, "link", link_cell(url))
```

**Verification by reading, required before Step 5:** confirm in the source that
no link consumer reads the cell. `_on_row_double_click` (`app.py:529-537`)
resolves `Path(iid)` and calls `self._open`, which reads `self.links.get(path)`
(`app.py:836-839`). `_show_context_menu` (`app.py:503-519`) enables/disables the
two entries from `self.links.get(path)`, and `_context_copy`/`_context_open`
route through `self._copy`/`self._open`, both keyed on `self.links`. `_row_tags`
(`app.py:386-395`) also reads `self.links`. `_sort_by`'s `"link"` branch sorts on
`self.links.get(path, "")`, so sorting still orders by URL, not by glyph.
Double-click, Copy link and Open in browser are therefore unaffected by the
cell contents — state this explicitly in the commit body.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_treeview_columns.py -q`
Expected: PASS

- [ ] **Step 6: Run the whole suite for regressions**

Run: `python3 -m pytest -q`
Expected: PASS (335 existing + the new tests)

- [ ] **Step 7: Add the smoke-checklist entries**

Append to `docs/smoke-checklist.md` under `### The list`:

```markdown
- [ ] **Column headers line up with their data.** Filename and Date read
      left-aligned with left-aligned headers; Size and Length read
      right-aligned with right-aligned headers; the checkbox and Link
      headers are centred. Confirm the fourth column's header reads
      **Length**, and that clicking it still sorts by duration (a short
      recording and a long one swap places) — the header text changed but
      the sort key deliberately did not.
- [ ] **Only the Filename column grows.** Widen the window from its minimum
      to full screen: Filename takes all the new space; Date, Size, Length
      and Link stay put.
- [ ] **LOAD-BEARING: the list at the minimum window width.** Drag the
      window to its floor (750px at 100%). Expected: every column is still
      present and readable, Filename truncates rather than pushing the
      others off, and NO horizontal scrollbar appears. Cramped is the
      accepted outcome here — a column that vanishes, overlaps, or
      collapses to nothing is not. The preferred widths (620px total) do
      not fit in the pane at that size; the per-column minimums (410px
      total) are what hold it together, so this is the only place that
      arithmetic is exercised.
- [ ] **The Link column shows ↗, not a URL.** After an upload completes, the
      row's Link cell shows a single arrow glyph in the link colour. Then
      confirm the URL is still reachable three ways on that row:
      double-click opens the video, right-click → Copy link pastes a working
      URL, right-click → Open in browser opens the same page. These read the
      in-memory link map rather than the cell, so a regression here means
      the wiring changed, not the glyph.
- [ ] **Rows have breathing room.** Compare against a pre-change build if
      one is handy: rows should look noticeably less cramped over a long
      list. At 100%, 125%, 150% and 200% confirm the extra height did not
      cost anything — descenders and the checkbox are still fully visible,
      and still are after a light↔dark switch.
```

Amend the existing Upload item (`docs/smoke-checklist.md:447`):

```markdown
- [ ] Single upload completes and the link column fills in with ↗
```

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/app.py tests/test_treeview_columns.py docs/smoke-checklist.md
git commit -m "$(cat <<'EOF'
List columns: real widths, matching header anchors, link glyph, roomier rows

Columns move to an explicit DPI-scaled spec: filename is the only
stretching column, size and duration are right-aligned, and every
heading is anchored like its column (headers were centred over
left-aligned data). The duration header reads "Length"; its column key
is unchanged because _sort_by dispatches on it.

The link column drops from ~35% of the width to 46px and shows "↗"
instead of the raw URL. Verified by reading the code that no capability
is lost: _on_row_double_click, _show_context_menu, _context_copy,
_context_open, _row_tags and _sort_by all read self.links, never the
cell.

_apply_row_height gains a third term, int(28 * scale), inside its
existing max(), so both prior guarantees hold.

The minimums, not the preferred widths, are what make the 750px floor
survive; that arithmetic is a comment, a test, and a checklist item.
EOF
)"
```
### Task 4: Typographic hierarchy

**Files:**
- Modify: `obs_youtube_uploader/app.py` (add module-level block after Task 3's helpers; Treeview construction ~line 204–213; `_build`; `_on_theme_changed` ~line 549–551)
- Create: `tests/test_typography.py`
- Modify: `docs/smoke-checklist.md` (new `### Typography` subsection under `## Look and feel`, after `### Display scaling`)

**Interfaces:**
- Consumes (Task 3): `app.configure_tree_columns(tree, scale, on_sort)` — unchanged by this task. Existing in-repo: `theme.token(name)`, `theme.register(consumer)`, `theme.apply(root, mode)`, `UploaderWindow._on_theme_changed(mode)`.
- Produces, for the upload-panel task and any later task that needs emphasis:
  - `app.apply_typography(root: tk.Misc) -> None` — idempotent; must be called once during construction and re-called from `_on_theme_changed`.
  - `app.TREE_STYLE: str` = `"Wingman.Treeview"` — the Treeview widget's `style=`; its `.Heading` substyle carries the bold.
  - `app.SECTION_HEADING_STYLE: str` = `"Section.TLabel"` — **this is the exact name the upload panel's "Upload" heading must pass as `style=` to `ttk.Label`.** The panel task creates no style of its own.
  - `app.MUTED_STYLE: str` = `"Muted.TLabel"` — **this is the exact name Task 6's selection-summary label passes as `style=` to `ttk.Label`, and the same one any hint label uses.** A label wearing it needs NO manual `foreground=` and NO per-mode recolour of its own: the style's foreground is `theme.token("MUTED")`, and `apply_typography` re-asserts it on every theme change, so the label follows light/dark for free. Setting `foreground=` on such a label would override the style and reintroduce exactly the bug the token exists to prevent.
  - `app.HEADING_FONT: str` = `"WingmanHeadingFont"` — the named Tk font both heading styles point at.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_typography.py
"""Bold headings, the muted style, and surviving a live theme switch.

No assertion here touches font metrics: this host's Tk has no Xft, so
linespace and measure() are meaningless. What IS checkable is the font's
CONFIGURATION (weight, size) and which style points at it, which is
exactly where this can regress.

The switch test is the point of the file. ttk stores style options per
THEME, and sv_ttk.set_theme() swaps the whole theme, so anything
configured before a switch is gone after it -- the same hazard
_apply_row_height's docstring describes.
"""
import tkinter as tk
from tkinter import ttk

import pytest

from obs_youtube_uploader import app, theme


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - no display (CI)
        pytest.skip(f"Tk needs a display: {exc}")
    yield r
    r.destroy()


@pytest.fixture(autouse=True)
def _clear_consumers():
    """theme._consumers is module-level; mirrors tests/test_theme.py."""
    saved = list(theme._consumers)
    theme._consumers.clear()
    yield
    theme._consumers.clear()
    theme._consumers.extend(saved)


def _font_option(root, name, option):
    return str(root.tk.call("font", "configure", name, option))


def test_heading_font_is_bold(root):
    app.apply_typography(root)
    assert _font_option(root, app.HEADING_FONT, "-weight") == "bold"


def test_both_heading_styles_use_that_font(root):
    app.apply_typography(root)
    style = ttk.Style(root)
    assert style.lookup(f"{app.TREE_STYLE}.Heading", "font") == app.HEADING_FONT
    assert style.lookup(app.SECTION_HEADING_STYLE, "font") == app.HEADING_FONT


def test_muted_style_follows_the_active_mode(root, monkeypatch):
    for mode in ("light", "dark"):
        monkeypatch.setattr(theme, "_current_mode", mode)
        app.apply_typography(root)
        assert ttk.Style(root).lookup(app.MUTED_STYLE, "foreground") == \
            theme.TOKENS[mode]["MUTED"]


def test_a_treeview_can_actually_wear_the_named_style(root):
    """The named style has no layout of its own; ttk must fall back to
    Treeview's. If that fallback ever stopped working the widget would
    fail to render rather than merely look wrong."""
    app.apply_typography(root)
    tree = ttk.Treeview(root, columns=("filename",), show="tree headings",
                        style=app.TREE_STYLE)
    tree.heading("filename", text="Filename")
    tree.pack(fill=tk.BOTH, expand=True)
    root.update()  # geometry is zeros until realised
    assert tree.winfo_width() > 1


def test_a_theme_switch_wipes_the_styles_without_a_re_assert(root):
    # Documents the hazard the wiring exists for. If this ever stops
    # failing, the re-assert below is no longer load-bearing.
    app.apply_typography(root)
    theme.apply(root, "dark")
    assert ttk.Style(root).lookup(f"{app.TREE_STYLE}.Heading", "font") \
        != app.HEADING_FONT


def test_registered_consumer_restores_the_styles_after_a_switch(root):
    # How UploaderWindow wires it: apply_typography runs from the ONE
    # registered consumer, so it lands after sv_ttk.set_theme has
    # rewritten the theme's styles.
    theme.register(lambda mode: app.apply_typography(root))
    for mode in ("dark", "light"):
        theme.apply(root, mode)
        style = ttk.Style(root)
        assert style.lookup(f"{app.TREE_STYLE}.Heading", "font") == app.HEADING_FONT
        assert style.lookup(app.SECTION_HEADING_STYLE, "font") == app.HEADING_FONT
        assert style.lookup(app.MUTED_STYLE, "foreground") == \
            theme.TOKENS[mode]["MUTED"]


def test_heading_font_tracks_the_dpi_rescaled_sv_font(root):
    """theme.apply rescales sv-ttk's fonts BEFORE consumers run, so the
    copy taken here is the corrected size -- not the 96-DPI one sv.tcl
    declared. Compared against the source font rather than an absolute
    number, so this says nothing about metrics."""
    root.tk.call("tk", "scaling", 144 / 72.0)
    theme.register(lambda mode: app.apply_typography(root))
    theme.apply(root, "dark")
    strong = _font_option(root, "SunValleyBodyStrongFont", "-size")
    assert _font_option(root, app.HEADING_FONT, "-size") == strong


def test_apply_typography_is_idempotent(root):
    root.tk.call("tk", "scaling", 144 / 72.0)
    theme.register(lambda mode: app.apply_typography(root))
    theme.apply(root, "dark")
    first = _font_option(root, app.HEADING_FONT, "-size")
    for _ in range(3):
        theme.apply(root, "dark")
    assert _font_option(root, app.HEADING_FONT, "-size") == first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_typography.py -q`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.app' has no attribute 'apply_typography'`

- [ ] **Step 3: Write minimal implementation**

Add after Task 3's `row_height` in `app.py`:

```python
# Named styles, so emphasis is declared in one place and every consumer
# spells it the same way. TREE_STYLE is the Treeview's own style: ttk
# derives a heading's style by appending ".Heading" to it, and a style with
# no layout of its own falls back to its parent's, so "Wingman.Treeview"
# inherits sv-ttk's Treeview appearance (and the rowheight
# _apply_row_height sets on "Treeview") while giving the headings a name of
# their own to hang a font on.
TREE_STYLE = "Wingman.Treeview"
SECTION_HEADING_STYLE = "Section.TLabel"   # panel section headings ("Upload")
MUTED_STYLE = "Muted.TLabel"               # selection summary, hint labels
HEADING_FONT = "WingmanHeadingFont"

# Preference order for what the heading font is derived from. The sv-ttk
# fonts come first because theme._rescale_sv_fonts has already corrected
# them for `tk scaling`; the Tk defaults are a fallback for a build with no
# sv-ttk, not the intended source.
_HEADING_FONT_BASES = ("SunValleyBodyStrongFont", "SunValleyBodyFont",
                       "TkHeadingFont", "TkDefaultFont")


def apply_typography(root: tk.Misc) -> None:
    """Declare the app's emphasis styles. Idempotent; safe to re-run.

    MUST be re-run on every theme change. ttk stores style options per
    theme and sv_ttk.set_theme swaps the theme wholesale, so a style
    configured once is silently gone after the first light/dark switch --
    the same hazard _apply_row_height's docstring describes, and the
    reason both are re-asserted from _on_theme_changed rather than set up
    once in _build.

    The font is re-derived from sv-ttk's own font on every call rather
    than remembered, because theme.apply rescales those fonts (for `tk
    scaling`) immediately before the consumers run: copying here is how
    bold headings inherit the corrected size instead of freezing a
    96-DPI one. Only -weight is overridden, so family and size stay
    sv-ttk's.

    Row text is deliberately NOT touched. ttk.Treeview has no per-column
    fonts, and per-row tags -- the only other channel -- are already
    fully spent on zebra striping, preselection and has_link (see
    _row_tags), where the tag listed first wins. There is nothing left to
    carry emphasis with, so the hierarchy stops at the headings.
    """
    names = {str(n) for n in root.tk.splitlist(root.tk.call("font", "names"))}
    if HEADING_FONT not in names:
        root.tk.call("font", "create", HEADING_FONT)
    base = next((n for n in _HEADING_FONT_BASES if n in names), None)
    if base is not None:
        root.tk.call("font", "configure", HEADING_FONT,
                     *root.tk.splitlist(root.tk.call("font", "configure", base)))
    root.tk.call("font", "configure", HEADING_FONT, "-weight", "bold")

    style = ttk.Style(root)
    style.configure(f"{TREE_STYLE}.Heading", font=HEADING_FONT)
    style.configure(SECTION_HEADING_STYLE, font=HEADING_FONT)
    # The one secondary-text colour, read live from the token table so a
    # switch recolours it rather than baking in the mode that was active
    # when the widget was built.
    style.configure(MUTED_STYLE, foreground=theme.token("MUTED"))
```

- [ ] **Step 4: Write minimal implementation — wire it into the window**

In `_build`, immediately after `self._dpi_scale = dpi_scale(self.root)` (`app.py:202`):

```python
        # Before the Treeview, so the style it names already exists.
        apply_typography(self.root)
```

In the same method, give the Treeview the named style (`app.py:204-213`):

```python
        self.tree = ttk.Treeview(
            self.list_frame,
            columns=("filename", "date", "size", "duration", "link"),
            show="tree headings",
            style=TREE_STYLE,
            # The checkbox is the selection model. A competing
            # highlight-selection would give the user two contradictory
            # notions of "selected", and a stray click would wipe out the
            # watcher's preselection.
            selectmode="none",
        )
```

In `_on_theme_changed`, beside the existing re-asserts (`app.py:549-551`):

```python
        self._build_checkbox_images()
        # Beside _apply_row_height for the same reason: set_theme swaps the
        # ttk theme, taking every style option configured against the old
        # one with it.
        apply_typography(self.root)
        self._apply_row_height()
        self._configure_tree_tags()
```

Note for whoever executes Task 5: that task moves this Treeview construction out of `_build` and into `_build_list_pane`, and MUST carry both the `apply_typography(self.root)` call and the `style=TREE_STYLE` argument across unchanged — dropping either silently returns the headings to the theme's default weight.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_typography.py -q`
Expected: PASS

- [ ] **Step 6: Run the whole suite for regressions**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 7: Add the smoke-checklist entries**

Insert a new subsection in `docs/smoke-checklist.md` under `## Look and feel`, directly after the `### Display scaling` block:

```markdown
### Typography
- [ ] **Column headers are bold and the rows are not.** Filename, Date,
      Size, Length and Link read heavier than the row text beneath them.
      Row text is intentionally uniform — `ttk.Treeview` has no per-column
      fonts and the row tags are already spent on striping, preselection
      and the link colour — so uneven-looking rows are a bug, not the
      hierarchy.
- [ ] **The panel's "Upload" heading is bold**, and heavier than the
      "Title"/"Description" field labels under it.
- [ ] **Secondary text is muted, not black-on-black.** The selection
      summary and any hint labels read visibly lighter than the primary
      text in BOTH light and dark — the muted colour is a theme token, so
      an unreadable one means the style was not re-applied for that mode.
- [ ] **LOAD-BEARING: bold survives a live OS theme switch.** With the main
      window open, flip `Choose your mode`. After the switch, the column
      headers and the "Upload" heading must still be bold, still the right
      size, and the muted text must have taken the new mode's colour. ttk
      stores style options per theme and `sv_ttk.set_theme` replaces the
      theme, so everything configured here is wiped on every switch and
      re-asserted from the window's single theme consumer. A switch that
      leaves plain headings behind means that re-assert is not running, or
      is running before `set_theme` rather than after.
- [ ] **Heading size follows display scaling.** At 150% and 200%, the bold
      headers grow with the rest of the UI rather than staying at their
      100% size — they are derived from sv-ttk's own font *after* it has
      been rescaled, so a frozen-looking header means that ordering broke.
```

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/app.py tests/test_typography.py docs/smoke-checklist.md
git commit -m "$(cat <<'EOF'
Typographic hierarchy: bold headings via named styles, muted secondary text

apply_typography() declares three named styles -- Wingman.Treeview
(whose .Heading carries the bold), Section.TLabel for the upload
panel's "Upload" heading, and Muted.TLabel for secondary text off
theme.token("MUTED"). The upload panel task consumes these names; it
defines no styles of its own.

Called from _build and re-called from the existing _on_theme_changed,
never registered as a second consumer: ttk stores style options per
theme, so sv_ttk.set_theme wipes them on every light/dark switch -- the
hazard _apply_row_height already documents.

The heading font is re-derived from sv-ttk's font on each call rather
than cached, so it inherits the DPI rescale theme.apply performs just
before consumers run. Only -weight is overridden.

Row text is unchanged, and stays that way: ttk.Treeview has no
per-column fonts, and per-row tags are already fully spent on zebra
striping, preselection and has_link.
EOF
)"
```
### Task 5: Two-pane main window

**Files:**
- Modify: `obs_youtube_uploader/app.py` (`_build` 182–290 → rewritten; `_on_theme_changed` 539–581 → extended; new `_build_list_pane` / `_build_upload_panel` / `_build_status_strip` / `_apply_desc_colors`)
- Create: `tests/conftest.py` (new — shared real-Tk fixture, reused by Task 6)
- Create: `tests/test_app_layout.py` (new)
- Modify: `docs/smoke-checklist.md` (extend the ffmpeg item at 37–41; new `### Layout` subsection under `## Look and feel`)

**Interfaces:**
- Consumes:
  - `app.spacing(widget: tk.Misc) -> Spacing` with fields `tight/normal/loose/margin/frame: int` (Task 1)
  - `app.configure_tree_columns(tree: ttk.Treeview, scale: float, on_sort) -> None` (Task 3 — owns the whole column spec: widths, minwidths, anchors, stretch, heading text and their sort commands)
  - `app.TREE_STYLE: str`, `app.SECTION_HEADING_STYLE: str`, `app.MUTED_STYLE: str`, `app.apply_typography(root: tk.Misc) -> None` (Task 4)
  - `app.dpi_scale(widget: tk.Misc) -> float` (existing); `theme.token(name, mode=None) -> str`, `theme.register(consumer)` (existing)
- Produces:
  - `UploaderWindow._build_list_pane(self, parent: tk.Misc) -> None`
  - `UploaderWindow._build_upload_panel(self, parent: tk.Misc) -> None`
  - `UploaderWindow._build_status_strip(self, parent: tk.Misc) -> None`
  - `UploaderWindow._apply_desc_colors(self, mode: str | None = None) -> None`
  - Attributes later tasks rely on: `self._pad: Spacing`, `self._dpi_scale: float`, `self._panel_width: int`, `self.upload_panel: ttk.Frame` (Task 6 grids the selection-summary label into it at **row 8**), `self.list_frame`, `self.tree`, `self.title_var`, `self.desc_txt`, `self.stitch_var`, `self.stitch_chk`, `self.ffmpeg_warn_label`, `self.retry_btn`, `self.progress`, `self.status` — every name that existed before still exists, with the same type.
  - Panel row map (fixed here, consumed by Task 6): `0` heading, `1` separator, `2` Title label, `3` Title entry, `4` Description label, `5` Description text (**weighted row**), `6` Stitch checkbox, `7` ffmpeg warning (conditional), `8` **reserved for the selection summary**, `9` Upload combat logs, `10` Retry + Upload Selected row.

---

- [ ] **Step 1: Replace `_build` with a shell that calls three region builders**

Replace `app.py:182-290` (the whole current `_build`) with the following. Note what is deliberately preserved: `self._dpi_scale` is still computed from the shared `dpi_scale()` helper, `theme.register` is still the last statement, and the `stitch_var` / `retry_btn` / `progress` / `status` attribute names are unchanged so no other method needs touching.

```python
    def _build(self) -> None:
        """Assemble the window: a two-pane body over a full-width status strip.

        Everything hangs off ONE padded frame instead of each section
        packing itself against the root with its own padx/pady. That single
        wrapper is what gives the window outer margins at all — the previous
        layout could only ever put space *between* sections, never around
        them, which is why no amount of tuning the old PAD_* constants
        produced a margin.

        The four regions are built by three helpers rather than inline. Not
        opportunistic tidying: the regions no longer appear in the order a
        reader walks the window (the panel's contents come from what used to
        be three separate places), so a single 110-line method would no
        longer describe anything.
        """
        self._pad = spacing(self.root)
        # Shared helper, not an independent computation: checkbox images,
        # window geometry and panel width must all agree on the scale.
        self._dpi_scale = dpi_scale(self.root)
        # Before any widget is created: the builders below NAME styles
        # (TREE_STYLE, SECTION_HEADING_STYLE, MUTED_STYLE) rather than
        # configuring fonts inline, and a widget naming a style that does
        # not exist yet renders with the theme default and no error.
        apply_typography(self.root)

        outer = ttk.Frame(self.root, padding=self._pad.margin)
        outer.pack(fill=tk.BOTH, expand=True)
        # The body takes every pixel a resize adds; the status strip keeps
        # its natural height, so a taller window grows the list, not the
        # progress bar.
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        body = ttk.Frame(outer)
        body.grid(row=0, column=0, sticky=tk.NSEW)
        body.rowconfigure(0, weight=1)
        # Only the list column stretches. The panel is a fixed width (see
        # _build_upload_panel), so all the slack a wider window brings goes
        # to the filename column — the one thing that benefits from it.
        body.columnconfigure(0, weight=1)

        self._build_list_pane(body)
        # A rule between the panes rather than whitespace alone: at the
        # minimum window width the gap compresses to almost nothing, and
        # two unseparated button groups read as one.
        ttk.Separator(body, orient=tk.VERTICAL).grid(
            row=0, column=1, sticky=tk.NS, padx=(self._pad.loose, 0))
        self._build_upload_panel(body)
        self._build_status_strip(outer)

        # Registered last, deliberately: _on_theme_changed dereferences
        # self.ffmpeg_warn_label, self.status and self.desc_txt, all created
        # above. A consumer registered earlier would be fine only for as
        # long as _build stays synchronous.
        theme.register(self._on_theme_changed)
```

- [ ] **Step 2: Add `_build_list_pane` — the list and the three commands that act on it**

Insert directly after `_build`. The column spec is NOT restated here: Task 3 owns it, and re-inlining widths, heading text or anchors would revert that task.

```python
    def _build_list_pane(self, parent: tk.Misc) -> None:
        """The recording list, its scrollbar, and the commands that act on
        the list itself.

        Select All / Select None / Delete Selected sit UNDER the list rather
        than in a shared bottom bar. They operate on rows; the old bar mixed
        them with upload actions and a checkbox, so eight controls of three
        different kinds read as one undifferentiated strip.

        grid rather than pack (the tree used pack before): the button row
        below has to span both the tree and its scrollbar, which pack cannot
        express without a second nesting frame.
        """
        self.list_frame = ttk.Frame(parent)
        self.list_frame.grid(row=0, column=0, sticky=tk.NSEW)
        self.list_frame.rowconfigure(0, weight=1)
        self.list_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self.list_frame,
            columns=("filename", "date", "size", "duration", "link"),
            show="tree headings",
            style=TREE_STYLE,
            # The checkbox is the selection model. A competing
            # highlight-selection would give the user two contradictory
            # notions of "selected", and a stray click would wipe out the
            # watcher's preselection.
            selectmode="none",
        )
        # Task 3 owns the whole column spec — widths, minwidths, anchors,
        # stretch, heading text and their sort commands. Configuring any of
        # it here would silently revert that task.
        configure_tree_columns(self.tree, self._dpi_scale, self._sort_by)

        scroll = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        scroll.grid(row=0, column=1, sticky=tk.NS)

        self._build_checkbox_images()
        self._apply_row_height()
        self._configure_tree_tags()
        self._build_context_menu()
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-Button-1>", self._on_row_double_click)
        self.tree.bind("<space>", self._on_tree_space)
        self.tree.bind("<FocusIn>", self._on_tree_focus_in)

        list_actions = ttk.Frame(self.list_frame)
        list_actions.grid(row=1, column=0, columnspan=2, sticky=tk.EW,
                          pady=(self._pad.normal, 0))
        # Delete last and separated: it is the only irreversible action in
        # the group, and it used to sit second from the left, between two
        # harmless ones.
        ttk.Button(list_actions, text="Select All",
                   command=lambda: self._set_all(True)).pack(
            side=tk.LEFT, padx=(0, self._pad.tight))
        ttk.Button(list_actions, text="Select None",
                   command=lambda: self._set_all(False)).pack(
            side=tk.LEFT, padx=(0, self._pad.loose))
        ttk.Button(list_actions, text="Delete Selected",
                   command=self._delete_selected).pack(side=tk.LEFT)
```

- [ ] **Step 3: Add `_build_upload_panel` — the fixed-width right pane**

This is where every moved control lands. The `ttk.LabelFrame` titled "Video details" is gone: a bold heading plus a separator carries the same grouping without the frame's own inset, which was competing with the new window margin.

```python
    def _build_upload_panel(self, parent: tk.Misc) -> None:
        """The upload panel: the two fields, the stitch option, and the three
        buttons that consume them.

        Title and Description are the primary input of the common session
        ("fight ended → open → the new recording is preselected → title it →
        upload"), and they used to sit at the top of the window while the
        button that reads them sat at the bottom. They are grouped with that
        button here instead.

        FIXED width, with grid_propagate off: without it the panel would
        size to its widest child (the ffmpeg warning, when present) and the
        window's proportions would depend on whether ffmpeg happens to be
        installed. Fixed also means the panel costs proportionally more the
        narrower the window is — accepted, and covered by the column
        minimums; see "Narrow windows" in ui-layout-design.md.

        Row map, since Task 6 grids into it: 0 heading, 1 separator, 2-3
        Title, 4-5 Description, 6 Stitch, 7 ffmpeg warning, 8 selection
        summary, 9 combat logs, 10 Retry + Upload.
        """
        self._panel_width = int(300 * self._dpi_scale)
        self.upload_panel = ttk.Frame(parent, width=self._panel_width)
        self.upload_panel.grid(row=0, column=2, sticky=tk.NSEW,
                               padx=(self._pad.loose, 0))
        self.upload_panel.grid_propagate(False)
        self.upload_panel.columnconfigure(0, weight=1)
        # The Description box absorbs the panel's vertical slack. Verified
        # on a real display: a bordered box that grows with the window reads
        # as a field, while the same slack left as empty space between
        # groups reads as a hole in the layout.
        self.upload_panel.rowconfigure(5, weight=1)

        # Bold comes from Task 4's shared named style, never from a font
        # pinned on this widget: ttk stores style options per theme, so a
        # font configured here would be wiped by the first light/dark
        # switch. apply_typography re-asserts the style after every switch.
        heading = ttk.Label(self.upload_panel, text="Upload",
                            style=SECTION_HEADING_STYLE)
        heading.grid(row=0, column=0, sticky=tk.W)
        ttk.Separator(self.upload_panel, orient=tk.HORIZONTAL).grid(
            row=1, column=0, sticky=tk.EW, pady=(self._pad.tight, self._pad.normal))

        ttk.Label(self.upload_panel, text="Title").grid(
            row=2, column=0, sticky=tk.W, pady=(0, self._pad.tight))
        self.title_var = tk.StringVar(value="")
        ttk.Entry(self.upload_panel, textvariable=self.title_var).grid(
            row=3, column=0, sticky=tk.EW)

        ttk.Label(self.upload_panel, text="Description").grid(
            row=4, column=0, sticky=tk.W, pady=(self._pad.normal, self._pad.tight))
        # height=3 is a FLOOR, not the rendered height: row 5 carries the
        # weight, so the box grows to whatever the panel has spare. Given a
        # visible border because it is now the panel's largest element —
        # unbordered, a box that big reads as a gap rather than a field.
        self.desc_txt = tk.Text(self.upload_panel, height=3, wrap=tk.WORD,
                                relief=tk.SOLID, bd=1, highlightthickness=0)
        self.desc_txt.grid(row=5, column=0, sticky=tk.NSEW)
        self._apply_desc_colors()

        self.stitch_var = tk.BooleanVar(value=False)
        self.stitch_chk = ttk.Checkbutton(self.upload_panel,
                                          text="Stitch selected videos",
                                          variable=self.stitch_var)
        self.stitch_chk.grid(row=6, column=0, sticky=tk.W,
                             pady=(self._pad.normal, 0))
        self.ffmpeg_warn_label = None
        if not self.state.ffmpeg_bin:
            self.stitch_chk.state(["disabled"])
            # Directly under the checkbox it explains, and WRAPPED: this
            # label came from a full-width bottom bar and does not fit on
            # one line in a 300px panel. Without wraplength Tk would size
            # the label to its full natural width and the fixed panel would
            # simply clip the tail of the sentence.
            self.ffmpeg_warn_label = ttk.Label(
                self.upload_panel, text="(ffmpeg not found — stitching unavailable)",
                foreground=theme.token("WARNING"), justify=tk.LEFT,
                wraplength=self._panel_width - self._pad.normal)
            self.ffmpeg_warn_label.grid(row=7, column=0, sticky=tk.EW,
                                        pady=(self._pad.tight, 0))

        # Row 8 is left free for Task 6's selection summary.

        # Upload combat logs is a peer upload action, NOT accented, so the
        # primary action stays unambiguous — the same reasoning the old
        # bottom bar carried, preserved here. Full width because it is the
        # only control on its row.
        ttk.Button(self.upload_panel, text="Upload combat logs",
                   command=self._start_combat_log_upload).grid(
            row=9, column=0, sticky=tk.EW, pady=(self._pad.normal, 0))

        actions = ttk.Frame(self.upload_panel)
        actions.grid(row=10, column=0, sticky=tk.EW, pady=(self._pad.tight, 0))
        # Only Upload Selected stretches: Retry keeps its natural width so
        # the accent button is visibly the larger target, and the pair still
        # fills the panel at every scale.
        actions.columnconfigure(1, weight=1)
        self.retry_btn = ttk.Button(actions, text="Retry", command=self._manual_retry)
        self.retry_btn.grid(row=0, column=0, sticky=tk.W, padx=(0, self._pad.tight))
        self.retry_btn.state(["disabled"])
        ttk.Button(actions, text="Upload Selected", style="Accent.TButton",
                   command=self._start_upload).grid(row=0, column=1, sticky=tk.EW)
```

- [ ] **Step 4: Add `_build_status_strip` and `_apply_desc_colors`**

```python
    def _build_status_strip(self, parent: tk.Misc) -> None:
        """The full-width strip under both panes: Settings, progress, status.

        Settings moves here because it configures the app rather than acting
        on the list or on an upload, and it was the leftmost item of the old
        action bar — first in reading order, ahead of the two buttons the
        user actually came for.

        No fixed height any more (the old status_bar pinned 48px with
        pack_propagate off). The strip is a single row of three widgets, so
        its natural height is already correct, and a pinned one would clip
        the progress bar at 200%.
        """
        strip = ttk.Frame(parent)
        strip.grid(row=1, column=0, sticky=tk.EW, pady=(self._pad.loose, 0))
        # The bar takes the slack; the message keeps its natural width and
        # stays pinned to the right edge instead of drifting with it.
        strip.columnconfigure(1, weight=1)
        ttk.Button(strip, text="Settings", command=self._open_settings).grid(
            row=0, column=0, sticky=tk.W, padx=(0, self._pad.loose))
        self.progress = ttk.Progressbar(strip, mode="determinate")
        self.progress.grid(row=0, column=1, sticky=tk.EW)
        self.status = ttk.Label(strip, text="")
        self.status.grid(row=0, column=2, sticky=tk.E, padx=(self._pad.loose, 0))

    def _apply_desc_colors(self, mode: str | None = None) -> None:
        """Paint the Description box from theme tokens.

        This box used to be left deliberately unstyled, riding on sv-ttk's
        tk_setPalette side effect. That stops being enough once it has a
        border and is the panel's dominant element: tk_setPalette gives it
        the window background, so a bordered box painted the same colour as
        everything around it reads as a rectangle drawn on nothing.

        ROW_EVEN is reused rather than a new token invented: it is the
        app's existing "surface slightly off the window background" colour
        in both modes, and this box wants exactly that.
        """
        self.desc_txt.config(background=theme.token("ROW_EVEN", mode),
                             foreground=theme.token("FG", mode),
                             insertbackground=theme.token("FG", mode))
```

- [ ] **Step 5: Re-apply the Description colours on a live theme switch**

Extend the existing `_on_theme_changed` (`app.py:539-581`) — do **not** register a second consumer. Add the block below beside the existing `ffmpeg_warn_label` / `status` deferrals, inside the same `after_idle` reasoning the surrounding comment already explains.

Verified on a real display at `DISPLAY=:0`: after `theme.apply(root, "light")` the box's background reads back as the dark value immediately and is stomped to `#fafafa` on the next `update()`; scheduling the repaint with `after_idle` leaves it at the token value. The existing comment above these lines is the explanation — it now covers three widgets rather than two.

```python
        # Same after_idle reasoning as the two labels above: tk_setPalette
        # runs on the next tick and resets this classic widget's colours.
        # Measured, not assumed — without the deferral the box reverts one
        # tick after the switch. (ttk widgets need nothing here: their
        # colours come from named styles, which apply_typography re-asserts.)
        self.root.after_idle(lambda m=mode: self._apply_desc_colors(m))
```

- [ ] **Step 6: Confirm every `command=` binding survived**

No code; this is the checklist the diff must satisfy. All eight commands and all five tree bindings are re-created, none dropped:

| Control | Old home | New home | Command |
|---|---|---|---|
| Settings | bottom bar | `_build_status_strip` | `self._open_settings` |
| Select All | bottom bar | `_build_list_pane` | `lambda: self._set_all(True)` |
| Select None | bottom bar | `_build_list_pane` | `lambda: self._set_all(False)` |
| Delete Selected | bottom bar | `_build_list_pane` | `self._delete_selected` |
| Upload combat logs | bottom bar (right) | `_build_upload_panel` row 9 | `self._start_combat_log_upload` |
| Retry | bottom bar (right) | `_build_upload_panel` row 10 | `self._manual_retry`, still `state(["disabled"])` at build |
| Upload Selected | bottom bar (right) | `_build_upload_panel` row 10 | `self._start_upload`, still `style="Accent.TButton"` |
| `#0` heading | list | `configure_tree_columns(..., self._sort_by)` | `self._sort_by("checked")` |
| 5 data headings | list | `configure_tree_columns(..., self._sort_by)` | `self._sort_by(key)` per column |
| `<Button-1>` `<Button-3>` `<Double-Button-1>` `<space>` `<FocusIn>` | list | `_build_list_pane` | unchanged |

Non-command state that must also survive: `stitch_var` still drives `stitch_chk`; `stitch_chk.state(["disabled"])` still fires when `state.ffmpeg_bin` is falsy; `ffmpeg_warn_label` is still `None` otherwise (`_on_theme_changed` tests it for `None`).

One thing NOT changed here, deliberately: `_set_all` leaves row images stale — a pre-existing defect visible when Select All is clicked, out of scope for a layout task and not to be silently folded in.

- [ ] **Step 7: Shared real-Tk fixture for widget tests**

Create `tests/conftest.py`. This is the first test in the suite to construct a window, so the display guard and the DPI convention live here once.

```python
"""Fixtures for the tests that drive a real Tk window.

The suite runs on Linux with no UI tests, but a display is usually
available (WSLg). These tests build real widgets rather than reasoning
about layout, and skip cleanly where there is no display — a headless CI
box must not turn a missing X server into a red suite.

Two traps that make a wrong check look identical to a right one:
  * every winfo_* is 0 until root.update() has run;
  * DPI is driven the way __main__.main() drives it, `tk scaling` = dpi/72,
    NOT by monkeypatching app.dpi_scale — patching the helper leaves Tk
    itself at 100%, so widget geometry would not move and the test would
    pass for the wrong reason.

Font metrics are meaningless here: this host's Tk has no Xft, so
tkfont.families() offers only a bitmap font. Never assert on text extents
or line heights; those checks belong in docs/smoke-checklist.md.
"""
import tkinter as tk

import pytest


@pytest.fixture
def make_window(tmp_path):
    """Build a real UploaderWindow at a given DPI over a temp recording dir."""
    windows = []

    def _make(dpi=96, ffmpeg_bin="/usr/bin/ffmpeg", files=("a.mkv", "b.mkv")):
        from obs_youtube_uploader import app as app_mod, theme

        try:
            root = tk.Tk()
        except tk.TclError:
            pytest.skip("no display available")
        root.tk.call("tk", "scaling", dpi / 72.0)
        theme.apply(root, "dark")
        for name in files:
            (tmp_path / name).write_bytes(b"\0" * 1024)
        state = app_mod.AppState(
            recording_dir=tmp_path,
            settings={"privacy": "unlisted", "category": "20"},
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=None,
        )
        window = app_mod.UploaderWindow(root, state)
        # Invalidate the probe refresh() just started: these tests set
        # duration state by hand, and a straggling probe result landing
        # mid-test would overwrite it.
        window._refresh_generation += 1
        root.update()
        windows.append(window)
        return window

    yield _make

    for window in windows:
        from obs_youtube_uploader import theme

        theme.unregister(window._on_theme_changed)
        window.root.destroy()
```

- [ ] **Step 8: Layout regression test**

Create `tests/test_app_layout.py`.

```python
"""Structural checks on the two-pane layout, against real widgets.

These assert the things a refactor of _build can silently break — a
control that stopped being created, a panel that stopped being fixed
width, content pushed past the bottom edge — and nothing that depends on
font rendering.
"""
import tkinter as tk

import pytest


def _labelled(widget):
    """Every text label in the widget subtree, flattened."""
    found = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except tk.TclError:
            text = ""
        if text:
            found.append(str(text))
        found.extend(_labelled(child))
    return found


def test_every_moved_control_still_exists(make_window):
    window = make_window()
    texts = _labelled(window.root)
    for label in ("Upload", "Title", "Description", "Stitch selected videos",
                  "Upload combat logs", "Retry", "Upload Selected",
                  "Select All", "Select None", "Delete Selected", "Settings"):
        assert label in texts, f"{label} disappeared in the restructure"


def test_upload_controls_live_in_the_panel(make_window):
    # Adjacency is the point of the redesign: the button that consumes the
    # fields must be in the same pane as the fields.
    window = make_window()
    panel_texts = _labelled(window.upload_panel)
    assert "Upload Selected" in panel_texts
    assert "Upload combat logs" in panel_texts
    assert "Retry" in panel_texts
    assert window.desc_txt.winfo_parent() == str(window.upload_panel)
    assert window.stitch_chk.winfo_parent() == str(window.upload_panel)
    # ...and the list commands must NOT have followed them there.
    assert "Delete Selected" not in panel_texts


def test_every_command_is_bound(make_window):
    window = make_window()

    def commands(widget):
        out = []
        for child in widget.winfo_children():
            try:
                out.append((str(child.cget("text")), str(child.cget("command"))))
            except tk.TclError:
                pass
            out.extend(commands(child))
        return out

    bound = {text: cmd for text, cmd in commands(window.root) if text}
    for label in ("Settings", "Select All", "Select None", "Delete Selected",
                  "Upload combat logs", "Retry", "Upload Selected"):
        assert bound.get(label), f"{label} lost its command binding"


@pytest.mark.parametrize("dpi,scale", [(96, 1.0), (144, 1.5), (192, 2.0)])
def test_panel_width_is_fixed_and_scales(make_window, dpi, scale):
    window = make_window(dpi=dpi)
    assert window.upload_panel.winfo_width() == int(300 * scale)
    # The list gets everything else, so it must still be the larger pane at
    # the default geometry.
    assert window.tree.winfo_width() > window.upload_panel.winfo_width()


def test_description_absorbs_panel_slack(make_window):
    window = make_window()
    # height=3 is a floor; the weighted row makes the real box much taller.
    assert window.desc_txt.winfo_height() > 3 * 20


def test_nothing_is_clipped_at_the_minimum_window_size(make_window):
    """The action row must still fit inside the panel at the window floor.

    grid shrinks the weighted Description row first; only once that is gone
    does fixed content start falling off the bottom, which is what this
    catches.
    """
    window = make_window()
    root = window.root
    root.update()
    min_w, min_h = root.wm_minsize()
    root.geometry(f"{int(min_w)}x{int(min_h)}")
    root.update()
    actions = window.retry_btn.master
    bottom = actions.winfo_rooty() + actions.winfo_height()
    assert bottom <= window.upload_panel.winfo_rooty() + window.upload_panel.winfo_height()
    assert window.tree.winfo_width() > 0


def test_ffmpeg_warning_sits_under_stitch_and_wraps(make_window):
    window = make_window(ffmpeg_bin=None)
    assert window.ffmpeg_warn_label is not None
    assert window.stitch_chk.instate(["disabled"])
    assert window.ffmpeg_warn_label.winfo_parent() == str(window.upload_panel)
    # Below the checkbox it explains, and constrained to the panel — an
    # unwrapped label would be silently clipped by grid_propagate(False).
    assert window.ffmpeg_warn_label.grid_info()["row"] > window.stitch_chk.grid_info()["row"]
    assert 0 < window.ffmpeg_warn_label.cget("wraplength") <= window._panel_width


def test_no_ffmpeg_warning_when_ffmpeg_is_present(make_window):
    window = make_window(ffmpeg_bin="/usr/bin/ffmpeg")
    assert window.ffmpeg_warn_label is None
    assert not window.stitch_chk.instate(["disabled"])


def test_description_box_is_painted_from_tokens(make_window):
    from obs_youtube_uploader import theme

    window = make_window()
    assert window.desc_txt.cget("background") == theme.token("ROW_EVEN")
    assert window.desc_txt.cget("relief") == "solid"
```

- [ ] **Step 9: Smoke-checklist entries**

Extend the existing ffmpeg item rather than duplicating it (`docs/smoke-checklist.md:37-41`), appending to its final line:

```markdown
      Restore the binary afterward. **The warning now lives in the upload
      panel, directly under the Stitch checkbox, not in a full-width bar** —
      check the whole sentence is readable there and wraps rather than being
      cut off at the panel edge, at 100% and again at 150%.
```

Then add a new subsection immediately after the `## Look and feel` heading, before `### Theming`:

```markdown
### Layout
- [ ] **The upload panel is intact at 100%, 150% and 200%.** Set
      `Settings > System > Display > Scale`, restart the app at each. The
      panel keeps its proportion to the window, and Title, Description,
      Stitch, the selection summary, Upload combat logs, Retry and Upload
      Selected are all fully visible with no clipped text and no button
      running past the panel edge.
- [ ] **Nothing is clipped at the minimum window size.** Drag the window as
      small as it goes at 150%. Expected: the Description box shrinks first
      and the Retry/Upload Selected row is still fully visible; list columns
      are cramped but present (accepted degradation — see
      ui-layout-design.md, "Narrow windows"). A missing Upload button is a
      defect; a narrow filename column is not.
- [ ] **The window has visible margins on all four edges,** and the
      Description box reads as a bordered field in both light and dark mode
      rather than blending into the panel background.
```

- [ ] **Step 10: Verify**

```bash
python3 -m pytest -q
DISPLAY=:0 python3 -m pytest -q tests/test_app_layout.py -v
```

Expect the pre-existing suite to stay green plus the new layout tests. If `test_app_layout.py` skips, `DISPLAY` is unset — re-run against `:0` rather than accepting the skip, since this task's whole risk is geometric.

- [ ] **Step 11: Commit**

```bash
git add obs_youtube_uploader/app.py tests/conftest.py tests/test_app_layout.py docs/smoke-checklist.md
git commit -m "Split _build into list pane, upload panel and status strip

Two-pane layout: the recording list beside a fixed-width upload panel,
with a full-width status strip beneath both. One padded wrapper frame
gives the window the outer margins it never had.

Title, Description, Stitch (with its ffmpeg warning, now wrapped),
Upload Selected, Retry and Upload combat logs move into the panel beside
the fields they consume; Select All/None/Delete move under the list;
Settings moves to the status strip. The 'Video details' LabelFrame is
dissolved in favour of a bold heading and a separator. Every command
binding is preserved; the column spec stays in configure_tree_columns and
the heading font in its named style rather than being restated here.

The Description box now carries a border and theme-token colours,
repainted from the existing theme consumer via after_idle - tk_setPalette
otherwise resets it one tick after a live switch."
```
### Task 6: Selection summary, updated on both triggers

**Files:**
- Modify: `obs_youtube_uploader/app.py` (`_build_upload_panel` — grid the label into reserved row 8; new `_update_selection_summary`; call sites in `_toggle_row` 438–448, `_set_all` 820–822, `refresh()` 582–650, `_apply_duration` 744–767)
- Create: `tests/test_app_selection_summary.py` (new)
- Test: `tests/conftest.py` (reused unchanged, from Task 5)

**Interfaces:**
- Consumes:
  - `app.format_selection_summary(infos: list[library.VideoInfo]) -> str` (Task 2 — pure; returns e.g. `"3 selected · 1.2 GB · 2:04:35"`, with a trailing `+` on the duration when any selected info has `probed is False`, and a no-selection string)
  - `app.MUTED_STYLE: str` and `app.apply_typography(root)` (Task 4)
  - `UploaderWindow.upload_panel`, `_pad`, `_panel_width`, and the reserved panel **row 8** (Task 5)
  - `UploaderWindow._chosen() -> list[library.VideoInfo]` (existing)
- Produces: `UploaderWindow.selection_summary: ttk.Label`; `UploaderWindow._update_selection_summary(self) -> None`.

---

- [ ] **Step 1: Add the label to the panel**

Insert into `_build_upload_panel` at the reserved row 8, between the ffmpeg warning block and the "Upload combat logs" button.

```python
        # Row 8. Muted via Task 4's shared named style rather than a
        # foreground set here: apply_typography re-asserts MUTED_STYLE on
        # every theme change, so this label needs no entry in
        # _on_theme_changed — a manual recolour would be redundant with the
        # style and would drift from it the moment the token changes.
        #
        # A readout, not a control, and placed immediately above the upload
        # buttons: it exists to answer "am I about to upload what I think I
        # am?" at the moment the user is reaching for Upload Selected.
        #
        # Deliberately NOT folded into self.status: that line is owned by
        # progress, errors and "Found N video(s)", all of which overwrite
        # each other. A summary sharing it would be destroyed by the first
        # progress tick of the upload it describes.
        self.selection_summary = ttk.Label(self.upload_panel, text="",
                                           style=MUTED_STYLE, justify=tk.LEFT,
                                           wraplength=self._panel_width - self._pad.normal)
        self.selection_summary.grid(row=8, column=0, sticky=tk.W,
                                    pady=(self._pad.normal, 0))
```

`_on_theme_changed` is **not** touched by this task.

- [ ] **Step 2: Add `_update_selection_summary`**

Place it beside `_chosen`, the only thing it reads.

```python
    def _update_selection_summary(self) -> None:
        """Repaint the panel's selection readout.

        TWO triggers feed this, not one. Selection changes are the obvious
        one — _toggle_row, _set_all, and refresh() (which rebuilds
        self.selected from scratch and re-applies the watcher's preselect).
        The second is probe completion: _apply_duration writes a resolved
        duration into one Treeview cell by iid and deliberately touches
        nothing else, so a summary wired only to selection changes would sit
        stale behind every probe that lands — showing a partial total, with
        its "+" marker, long after the probe that completed it.

        Cheap enough to call unconditionally: _chosen() is a list
        comprehension over infos already in memory, and the formatter reads
        only info.size and info.duration.
        """
        self.selection_summary.config(text=format_selection_summary(self._chosen()))
```

- [ ] **Step 3: Wire trigger one — every path that mutates the selection**

Enumerated by grepping `self.selected` in `app.py`; the mutation sites are lines 444 (`_toggle_row`), 601/621 (`refresh`) and 821 (`_set_all`), and nothing outside `app.py` touches `self.selected` (`__main__.py` and `settingsui.py` both come up empty). `_delete_selected`, `_settings_saved` and `show()` all mutate the selection only by calling `refresh()`, so they are covered by the `refresh()` call and must not get a second one.

`_toggle_row` — append after the image update:

```python
        var.set(not var.get())
        self.tree.item(iid, image=self._checkbox_image(var.get()))
        self._update_selection_summary()
```

`_set_all` — after the loop, once, not per var:

```python
    def _set_all(self, value: bool) -> None:
        for var in self.selected.values():
            var.set(value)
        # Once, after the loop: the label is recomputed from the whole
        # selection, so doing it per row would be N identical repaints of
        # intermediate states.
        self._update_selection_summary()
```

`refresh()` — immediately after the status line is set, i.e. after the rows and `self.selected` have been rebuilt and the preselect applied, and before the cache prune:

```python
        self._status_kind = "FG"
        self.status.config(text=f"Found {len(self.infos)} video(s)",
                           foreground=theme.token("FG"))
        # After the rebuild, not before: self.selected was cleared and
        # repopulated above, and the watcher's preselect means a refresh can
        # arrive with rows already checked.
        self._update_selection_summary()
```

- [ ] **Step 4: Wire trigger two — probe completion**

`_apply_duration`, appended after the cell write. This is the trigger the whole two-trigger rule exists for.

```python
        iid = str(info.path)
        if self.tree.exists(iid):
            self.tree.set(iid, "duration", info.duration_str)
        # The summary's duration total is only as complete as the probes
        # behind it. This method is the ONLY place a duration becomes known
        # after the list is drawn, so without this call the "+" partial
        # marker would still be showing on a selection that is now fully
        # measured. Unconditional rather than guarded on "is this info
        # selected": the check costs a dict lookup either way, and a guard
        # that gets the membership test subtly wrong fails silently.
        self._update_selection_summary()
```

- [ ] **Step 5: Regression test for the staleness path**

Create `tests/test_app_selection_summary.py`. The first test is the regression: it is the bug the two-trigger rule prevents, so it is tested rather than assumed.

```python
"""The selection summary, and the probe-completion path that keeps it fresh."""


def test_summary_is_refreshed_when_a_probe_lands(make_window):
    """REGRESSION: a summary wired only to selection changes goes stale.

    _apply_duration writes one Treeview cell and touches nothing else, so
    the partial-total "+" survives the very probe that completes the total
    unless _apply_duration recomputes the summary too.
    """
    window = make_window()
    probed, outstanding = window.infos[0], window.infos[1]
    probed.duration, probed.probed = 60.0, True
    outstanding.duration, outstanding.probed = None, False

    window._set_all(True)
    partial = window.selection_summary.cget("text")
    assert "+" in partial, "an outstanding probe must be marked partial"

    # The probe lands. Nothing else happens — no refresh, no click.
    window._apply_duration(outstanding, 45.0, True)

    complete = window.selection_summary.cget("text")
    assert "+" not in complete, "summary went stale behind the probe"
    assert complete != partial


def test_toggling_one_row_updates_the_summary(make_window):
    window = make_window()
    window._set_all(False)
    empty = window.selection_summary.cget("text")
    window._toggle_row(str(window.infos[0].path))
    assert window.selection_summary.cget("text") != empty
    assert "1" in window.selection_summary.cget("text")


def test_select_all_and_none_update_the_summary(make_window):
    window = make_window()
    window._set_all(True)
    all_text = window.selection_summary.cget("text")
    assert str(len(window.infos)) in all_text
    window._set_all(False)
    assert window.selection_summary.cget("text") != all_text


def test_refresh_rebuilds_the_summary_from_the_preselect(make_window):
    # The watcher's preselect arrives through refresh(), which rebuilds
    # self.selected wholesale — the summary must follow that rebuild, not
    # the selection it had before it.
    window = make_window()
    window._set_all(True)
    window.refresh(preselect={window.infos[0].path})
    window._refresh_generation += 1  # stop the probe this refresh started
    text = window.selection_summary.cget("text")
    assert text.startswith("1 ")


def test_deleting_through_refresh_leaves_no_stale_count(make_window):
    window = make_window()
    window._set_all(True)
    for info in window.infos:
        info.path.unlink()
    window.refresh()
    window._refresh_generation += 1
    assert "0" in window.selection_summary.cget("text") or \
        window.selection_summary.cget("text") == ""
```

- [ ] **Step 6: Verify**

```bash
python3 -m pytest -q
DISPLAY=:0 python3 -m pytest -q tests/test_app_selection_summary.py -v
```

The staleness test must fail if the `_apply_duration` call from Step 4 is removed — confirm that by deleting the line, re-running, and putting it back. A regression test that passes either way is not one.

- [ ] **Step 7: Commit**

```bash
git add obs_youtube_uploader/app.py tests/test_app_selection_summary.py
git commit -m "Show a selection summary, refreshed on selection AND on probe

A muted label in the upload panel reports how many recordings are
selected, their total size, and their total length, from values already
held in memory. It uses the shared muted style, so apply_typography keeps
it correct across theme switches with no manual recolour.

Recomputed from two triggers. Selection changes (_toggle_row, _set_all,
and refresh(), which rebuilds the selection and applies the watcher's
preselect) are the obvious one. The second is _apply_duration: it writes
a resolved duration into one Treeview cell by iid and touches nothing
else, so a summary wired only to selection would keep showing the '+'
partial marker behind every probe that completed it. Covered by a
regression test."
```
### Task 7: Dark title bar

**Files:**
- Modify: `obs_youtube_uploader/theme.py` (append `apply_titlebar` and its default setter after `unregister`, ~line 120)
- Modify: `obs_youtube_uploader/app.py` (tail of `_build`; `_on_theme_changed`)
- Modify: `obs_youtube_uploader/settingsui.py` (`__init__` tail, ~line 93-104; `_on_theme_changed`, ~line 390-403)
- Test: `tests/test_theme.py` (append)

**Interfaces:**
- Consumes: theme.register / theme.unregister / theme.apply / theme.current_mode (all existing)
- Produces:
  - `theme.apply_titlebar(window, mode: Mode, setter: Callable[[int, int, int], int] | None = None) -> None`
  - `theme.DWMWA_USE_IMMERSIVE_DARK_MODE: int = 20`
  - `theme.DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1: int = 19`
  - `theme._dwm_set_window_attribute(hwnd: int, attr: int, value: int) -> int` (the default setter; returns the HRESULT, 0 on success)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme.py`. The `setter` seam mirrors `detect_mode(reader=...)` exactly, so the Windows-only DWM call is exercised on Linux without a real HWND.

```python
class _FakeWindow:
    """Stand-in for a Toplevel. wm_frame() returns the hex window id string
    Tk really hands back, so the test covers the parse too."""

    def __init__(self, frame="0x1a2b3c"):
        self._frame = frame
        self.frame_calls = 0

    def wm_frame(self):
        self.frame_calls += 1
        if self._frame is None:
            raise RuntimeError("window is not realised")
        return self._frame


def _recording_setter(results):
    """results: HRESULT to return per call, consumed in order."""
    calls = []

    def setter(hwnd, attr, value):
        calls.append((hwnd, attr, value))
        return results[len(calls) - 1] if len(calls) <= len(results) else 0

    return calls, setter


def test_apply_titlebar_sets_attribute_20_when_it_succeeds():
    calls, setter = _recording_setter([0])
    win = _FakeWindow("0x1a2b3c")

    theme.apply_titlebar(win, "dark", setter=setter)

    assert calls == [(0x1a2b3c, theme.DWMWA_USE_IMMERSIVE_DARK_MODE, 1)]


def test_apply_titlebar_falls_back_to_attribute_19_when_20_fails():
    """Attribute 20 is only recognised from Windows 10 20H1 on; on earlier
    builds DwmSetWindowAttribute returns a failing HRESULT rather than
    raising, so a caller that ignored the return value would leave the title
    bar light on exactly the hosts that need the fallback."""
    calls, setter = _recording_setter([-2147024809, 0])  # E_INVALIDARG, then OK
    win = _FakeWindow("0x1a2b3c")

    theme.apply_titlebar(win, "dark", setter=setter)

    assert calls == [
        (0x1a2b3c, theme.DWMWA_USE_IMMERSIVE_DARK_MODE, 1),
        (0x1a2b3c, theme.DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1, 1),
    ]


def test_apply_titlebar_clears_the_flag_in_light_mode():
    calls, setter = _recording_setter([0])

    theme.apply_titlebar(_FakeWindow(), "light", setter=setter)

    assert calls == [(0x1a2b3c, theme.DWMWA_USE_IMMERSIVE_DARK_MODE, 0)]


def test_apply_titlebar_is_a_noop_off_windows(monkeypatch):
    """No setter injected means the real DWM path, which does not exist off
    Windows. It must return before even touching the window - wm_frame() on a
    non-Windows Tk returns an X11 id that is meaningless to DWM."""
    monkeypatch.setattr(theme.sys, "platform", "linux")
    win = _FakeWindow()

    theme.apply_titlebar(win, "dark")

    assert win.frame_calls == 0


def test_apply_titlebar_swallows_an_unrealised_window(caplog):
    """wm_frame() has no usable HWND until the toplevel is on screen. Ordering
    is the caller's job, but this must degrade rather than take a window
    constructor down - the same policy as apply()."""
    calls, setter = _recording_setter([0])

    with caplog.at_level(logging.WARNING):
        theme.apply_titlebar(_FakeWindow(frame=None), "dark", setter=setter)

    assert calls == []


def test_apply_titlebar_swallows_a_raising_setter(caplog):
    def boom(hwnd, attr, value):
        raise OSError("dwmapi.dll missing")

    with caplog.at_level(logging.WARNING):
        theme.apply_titlebar(_FakeWindow(), "dark", setter=boom)  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_theme.py -q`

Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.theme' has no attribute 'apply_titlebar'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/theme.py`, after `unregister` (before the `_SV_FONT_NAMES` block):

```python
# DWMWA_USE_IMMERSIVE_DARK_MODE. The attribute was renumbered in Windows 10
# 20H1: 20 on 20H1 and later, 19 on 1809-1909. Both are tried because the
# older value is silently REJECTED on new builds and vice versa - there is no
# version query cheaper or more reliable than asking DWM itself.
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1 = 19


def _dwm_set_window_attribute(hwnd: int, attr: int, value: int) -> int:
    """Returns the raw HRESULT rather than a bool: apply_titlebar keys its
    fallback off a FAILING result, and DwmSetWindowAttribute reports an
    unrecognised attribute by returning E_INVALIDARG, not by raising."""
    import ctypes

    val = ctypes.c_int(value)
    return int(ctypes.windll.dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd), ctypes.c_uint(attr),
        ctypes.byref(val), ctypes.sizeof(val)))


def apply_titlebar(window, mode: Mode, setter=None) -> None:
    """Paint *window*'s OS title bar to match *mode*.

    sv-ttk restyles the client area only, so a dark window kept a light title
    bar - visibly wrong beside the themed content, and worst on the Settings
    dialog sitting over the dark main window.

    `setter` is injectable for the same reason detect_mode takes `reader=`:
    the real call is Windows-only, and the suite runs on Linux. When it is
    omitted the platform guard fires FIRST, before `window` is touched at all
    - wm_frame() off Windows returns an X11 id that means nothing to DWM.

    Never raises, for the same reason apply() never does: this is an optional
    presentation capability, and it is called from window constructors and
    from theme consumers, neither of which can absorb a failure.
    """
    if setter is None:
        if sys.platform != "win32":
            return
        setter = _dwm_set_window_attribute

    try:
        # wm_frame() returns the id of the window's OS-level frame, and only
        # once the toplevel has actually been realised - before that there is
        # no HWND to hand DWM. Callers must map the window first.
        hwnd = int(window.wm_frame(), 16)
        enabled = 1 if mode == "dark" else 0
        if setter(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, enabled) != 0:
            setter(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1, enabled)
    except Exception:
        log.warning("applying the %r title bar failed", mode, exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_theme.py -q`

Expected: PASS

- [ ] **Step 5: Wire it into `UploaderWindow`**

Two edits in `obs_youtube_uploader/app.py`.

First, insert the initial application immediately before the `theme.register(self._on_theme_changed)` call at the end of `_build`. After Task 5's split, that call is the last statement of the new, much shorter `_build`, which now delegates the actual widget construction to `_build_list_pane` / `_build_upload_panel` / `_build_status_strip`:

```python
        # The initial application is explicit, not left to registration:
        # __main__.main() calls theme.apply() at __main__.py:198, BEFORE this
        # window is constructed at line 209, so a consumer registered here is
        # not invoked until the NEXT theme switch. Registration alone would
        # leave the title bar light until the user changed their OS theme.
        theme.apply_titlebar(self.root, theme.current_mode())

        # Registered last, deliberately: _on_theme_changed dereferences
        # self.ffmpeg_warn_label and self.status, both created above. A
        # consumer registered earlier would be fine only for as long as
        # _build stays synchronous.
        theme.register(self._on_theme_changed)
```

Second, at the end of the EXISTING `_on_theme_changed` — extending the one consumer rather than registering a second, which is what its own docstring already demands. By the time this task runs, that method has already grown to re-assert typography (Task 4) and repaint the Description box (Task 5) on top of the checkbox images, row height, tree tags, ffmpeg warning, and status colour it started with, so this is one more line in an established method, not a new consumer:

```python
        # Extends this window's single consumer rather than registering
        # another: two consumers against one window means two half-updates on
        # a live switch, and this one is not unregistered anywhere.
        theme.apply_titlebar(self.root, mode)
```

- [ ] **Step 6: Wire it into `SettingsWindow`**

Two edits in `obs_youtube_uploader/settingsui.py`.

First, at the very end of `__init__` (after `self.win.resizable(True, True)`, ~line 104):

```python
        # After geometry/minsize, and after the update_idletasks above: the
        # toplevel must be realised before wm_frame() has an HWND to give.
        # Explicit here for the same reason as the main window - theme.apply()
        # ran back in main() long before this dialog existed, so the consumer
        # registered above will not fire until the next switch, and the
        # dialog would otherwise open with a light title bar over a dark
        # parent (the exact mismatch this change exists to fix).
        theme.apply_titlebar(self.win, theme.current_mode())
```

Second, in the EXISTING `_on_theme_changed` (~line 403), alongside the deferred repaint:

```python
        self.win.after_idle(lambda: self._repaint_tokens(mode))
        # Folded into the existing consumer, NOT registered separately: this
        # method is the one callback _on_destroy unregisters, so the title bar
        # inherits that teardown for free. A second consumer would leak a
        # destroyed Toplevel on every dialog open - the leak theme.unregister
        # was written to fix.
        theme.apply_titlebar(self.win, mode)
```

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest -q`

Expected: PASS (all pre-existing tests plus the six new `apply_titlebar` cases). The two windows are not constructed by any test, so the wiring is covered by the smoke checklist on Windows, not by pytest — noted rather than hidden.

- [ ] **Step 8: Add the smoke-checklist entries**

This task is the one change in the plan with **no** automated coverage of its real behaviour: the DWM call is a no-op off Windows, so pytest proves only that the fallback logic branches correctly, never that a title bar actually turned dark. The checklist is the only real verification, which makes these entries load-bearing rather than a formality.

Insert under `## Look and feel`, after the `### Theming` block:

```markdown
### Title bars
- [ ] **Both title bars are dark at startup** in dark mode. Open the main
      window, then open Settings and put the two side by side: the dialog's
      title bar must match the main window's, not be light. This mismatch,
      visible in a single screenshot, is the whole reason this exists.
- [ ] **Both title bars are light in light mode.** Switch
      `Settings > Personalization > Colors` to Light, restart the app, and
      confirm neither window has a dark title bar stuck on.
- [ ] **LOAD-BEARING: both follow a LIVE OS theme switch.** With BOTH windows
      open, flip `Choose your mode`. Both title bars must change together,
      with no restart. A window that changes only after reopening means the
      call is wired to construction but not to the theme consumer; a window
      that never changes means the consumer is not firing at all.
- [ ] **Older Windows builds still work.** On Windows 10 1809-1909 the
      attribute is 19, not 20, and DWM reports the wrong one by returning a
      failing HRESULT rather than raising — so a build where the title bars
      stay light but the app is otherwise fine points at the fallback, not at
      the wiring. If no such machine is available, note it as untested rather
      than ticking it.
```

- [ ] **Step 9: Commit**

```bash
git add obs_youtube_uploader/theme.py obs_youtube_uploader/app.py \
        obs_youtube_uploader/settingsui.py tests/test_theme.py \
        docs/smoke-checklist.md
git commit -m "Paint both title bars to match the theme

sv-ttk styles the client area only, so a dark window kept a light title bar --
most visible on the Settings dialog floating over the dark main window. PR #5
descoped this call; it is in scope now.

theme.apply_titlebar sets DWMWA_USE_IMMERSIVE_DARK_MODE (20), falling back to
19 on pre-20H1 builds where 20 is rejected with a failing HRESULT rather than
an exception. setter= is injectable so the Windows-only call is tested on
Linux, mirroring detect_mode(reader=...).

Both windows apply it directly during construction -- theme.apply() runs
before either exists, so registration alone would never apply the initial
state -- and then extend their single existing _on_theme_changed callback
rather than registering a second consumer, which would reintroduce the
Toplevel leak theme.unregister exists to prevent."
```
