# UI layout and information design — design

**Status:** approved in brainstorming, ready for an implementation plan
**Branch base:** `worktree-ui-layout`, off `origin/main` (`97f189f`), which
contains the PR #5 theming refresh (`80087c4`) and the rebrand (`#4`).
**Input:** `ui-layout-observations.md` (repo root).

## Intended outcome

The main window stops reading as a re-skinned script. Layout, spacing, column
sizing, and information hierarchy are addressed; the theming from PR #5 is
reused untouched. No new features, and no capability is removed — in
particular the "Upload combat logs" button and the Discord settings frame
both survive.

## Repository evidence that shaped this

Findings established by reading the code, not assumed from the observations
doc:

1. **`title` / `description` are per-batch, not per-video.** One `UploadJob`
   carries one title (`app.py`), and `uploader.build_body` substitutes
   `"Untitled"` when it is empty and appends `(n/total)` for multi-item
   uploads. They are properties of the *upload action*, not of the list.
2. **The `link` column is empty in the common case.** `refresh()` clears
   `self.links` on every rebuild, so a value exists only for rows uploaded
   during the current session. It occupied ~35% of the width regardless.
3. **`_sort_by` keys the date column off `info.mtime`, not the rendered
   string.** The displayed date format is therefore free to change without
   touching sort behaviour.
4. **A `has_link` tag already colours uploaded rows.** The link column is not
   the only signal that a row has been uploaded.
5. **`PAD_TIGHT/NORMAL/LOOSE/FRAME_PADDING` have exactly two consumers** —
   `app.py` and `settingsui.py` — and **no test references them.** Replacing
   them carries no compatibility burden.
6. **`app.dpi_scale(widget)` already returns exact quarter steps**, so scaled
   spacing needs no new DPI machinery.

## Correction to the observations doc

`ui-layout-observations.md` finding #2 calls Title/Description "the least-used
control". The user's actual flow is "recording just finished → open → the new
recording is preselected → title it → upload". In that flow these are the
*primary input* of the session.

The defect is therefore not that they are prominent. It is that they are
**mis-proportioned** (a 3-line always-empty Description box billed equally with
a one-line Title), **unmargined**, and **separated from the Upload button that
consumes them by the entire window**. The design fixes proportion and adjacency
rather than hiding them behind a disclosure.

Every other finding in that doc is upheld.

## Observable behaviour and UX

Two-pane main window: recording list on the left, upload panel on the right,
full-width status strip beneath both.

```
┌──────────────────────────────────┬──────────────┐
│ ☑ Filename        Date  Size  Len│ Upload       │
│ ☐ Fight 2026-08…  17:43 388MB 61:58─────────────│
│ ☑ 2026-08-20 17…  17:43 7.5MB  1:59 Title       │
│ ☐ Replay 2026-0…  17:43 381MB 59:58 [_________] │
│ …                                │ Description  │
│                                  │ ┌──────────┐ │
│                                  │ │          │ │
│                                  │ │          │ │
│                                  │ └──────────┘ │
│                                  │ ☐ Stitch     │
│                                  │ 3 sel·1.2 GB │
│ [Select All][None][Delete]       │ [Combat logs]│
│                                  │ [Rty][Upload]│
├──────────────────────────────────┴──────────────┤
│ [Settings]  ▓▓▓▓▓▓░░░░         Uploading 2 of 3…│
└─────────────────────────────────────────────────┘
```

Validated by a throwaway Tk mockup driven at 96 and 144 DPI on a real display
(WSLg), with scaling set the way `__main__.main()` sets it
(`root.tk.call("tk","scaling", tk_scaling_for(dpi))`), not by monkeypatching
`dpi_scale`. The mockup is not kept.

### What moves

| Control | From | To |
|---|---|---|
| Title, Description | "Video details" frame, top | Upload panel, right |
| Stitch checkbox | bottom action bar | Upload panel |
| "(ffmpeg not found — stitching unavailable)" label | beside Stitch, bottom bar | Upload panel, directly under Stitch |
| Upload Selected, Retry, Upload combat logs | bottom action bar | Upload panel, under the fields they consume |
| Select All / None / Delete Selected | bottom action bar | under the list |
| Settings | bottom action bar | status strip, far left |
| Status message, progress bar | bottom | status strip (unchanged in kind) |

The `ttk.LabelFrame` titled "Video details" is dissolved; the panel's own
"Upload" heading plus a separator replaces it.

The conditional ffmpeg warning moves **with** the checkbox it explains. It is
created only when `state.ffmpeg_bin` is falsy (`app.py:254-263`) and is an
explicit smoke-test expectation (`docs/smoke-checklist.md:37-41`), so it is
called out here rather than left to be inferred from "the Stitch checkbox
moves". Wrapping is enabled on it — the panel is narrower than the bottom bar
it came from, and the string is long enough to need two lines there.

### Selection summary

The status label keeps its existing roles (progress, errors, "Found N
video(s)"). A **new muted label in the panel** shows
`3 selected · 1.2 GB · 2:04:35`, built from `info.size` and `info.duration`,
both already held.

**It is recomputed on two triggers, not one.** Selection changes are the
obvious one. The second is probe completion: `_apply_duration` writes a
resolved duration straight into the Treeview cell by iid and deliberately
touches nothing else (`app.py:744-767`), so a summary wired only to selection
would sit stale behind every probe that lands. `_apply_duration` gains a call
to the same recompute.

**A partial total is labelled as partial.** A recording whose probe is still
outstanding contributes nothing to the duration sum, so the sum would otherwise
read as complete while being short. When any selected recording has
`probed == False`, the duration is rendered `2:04:35+` — mirroring the `…`
placeholder convention the duration column already uses rather than inventing a
second vocabulary for the same state. Size is never partial: `info.size` comes
from `stat`, not from a probe.

## Architecture and boundaries

No module boundaries move. `library.py`, `durations.py`, `uploader.py`,
`stitch.py`, `combatlog.py`, `discord.py` are untouched. Changes are confined
to `app.py` (layout), `settingsui.py` (spacing + title bar), and `theme.py`
(title bar).

`_build` is currently one long method building four unrelated regions. It is
split into `_build_list_pane`, `_build_upload_panel`, and `_build_status_strip`,
called from `_build`. This is a direct consequence of the restructure, not
opportunistic refactoring: the method's regions no longer sit in visual order.

## Interfaces

### Scaled spacing

`PAD_TIGHT/PAD_NORMAL/PAD_LOOSE/FRAME_PADDING` are removed and replaced by:

```python
@dataclass(frozen=True)
class Spacing:
    """DPI-scaled spacing steps. Built from dpi_scale(), so gaps grow with
    everything else — the unscaled constants this replaces were the reason
    high-DPI layouts grew while the space between things did not."""
    tight: int    # 4 @100% — within one control group
    normal: int   # 8 @100% — between controls in a section
    loose: int    # 12 @100% — between sections
    margin: int   # 16 @100% — window edge; new step, no unscaled equivalent
    frame: int    # 8 @100% — internal padding of a bordered frame


def spacing(widget: tk.Misc) -> Spacing: ...
```

Both windows call `spacing()` once during construction and use the result.
`margin` is new: the old scale had no window-edge step, which is why finding
#1 (no outer margins) had no constant to reach for.

### Dark title bar

Explicitly requested scope, not an extension of PR #5: that PR descoped the
call as an accepted limitation, and the light Settings title bar beside the
dark main window is visible in the screenshot the observations doc was built
from. Nothing else about the theming changes.

In `theme.py`, alongside the existing `detect_mode(reader=...)` convention:

```python
def apply_titlebar(window, mode, setter=None) -> None:
    """DWMWA_USE_IMMERSIVE_DARK_MODE (20), falling back to 19 on pre-20H1.
    No-op off Windows. `setter` is injectable so this is testable on Linux."""
```

**Lifecycle — three requirements, none of which registration alone satisfies:**

1. **The initial application must be explicit.** `__main__.main()` calls
   `theme.apply(root, ...)` at `__main__.py:198`, *before* `UploaderWindow` is
   constructed at line 209. A consumer registered in a window's constructor is
   therefore never invoked until the *next* theme switch, leaving the title bar
   light until the user changes their OS theme. Each window calls
   `apply_titlebar` directly during construction, then registers for
   subsequent switches.
2. **Extend the existing consumer; do not add a second one.** Both windows
   already register exactly one callback (`_on_theme_changed`), and
   `SettingsWindow` already unregisters it on `<Destroy>`
   (`settingsui.py:418-423`). Calling `apply_titlebar` from inside those
   existing callbacks inherits that teardown for free. Registering a separate
   consumer would silently reintroduce the leak `theme.unregister` was written
   to fix — see its docstring.
3. **The Settings window must be mapped first.** `wm_frame()` returns a usable
   HWND only after the toplevel exists on screen, so the call happens after the
   window is realised rather than mid-construction.

## Column specification

| Column | Width @100% | Min | Stretch | Anchor | Notes |
|---|---|---|---|---|---|
| `#0` checkbox | 34 | 34 | no | center | unchanged |
| `filename` | 260 | 120 | **yes** | W | the only stretching column |
| `date` | 120 | 90 | no | W | reformatted, see below |
| `size` | 84 | 64 | no | **E** | numeric |
| `duration` | 76 | 56 | no | **E** | header renamed `Length` |
| `link` | 46 | 46 | no | center | `↗` when a link exists, else empty |

Every `heading()` gets an `anchor` matching its column, fixing centered headers
over left-aligned data (finding #3).

**Narrow windows — accepted degradation.** The preferred widths sum to 620px.
At the existing 750px minimum window width the list pane gets roughly 380–420px
once the margin, the 300px panel, the pane gap and the scrollbar are taken out,
so the preferred widths do not fit. The `Min` column above is what makes this
safe: the minimums sum to 420px, which does fit, and `ttk.Treeview` compresses
toward them.

No horizontal scrollbar is added, and the window minimum is **not** raised.
Both were considered and rejected: a horizontal scrollbar on a list whose only
elastic column is the filename trades a rare annoyance for a permanent one, and
raising the minimum cannot help on a screen where `__main__` already clamps the
geometry to the display size (`app.py:159-169`). A window dragged to its
minimum shows cramped columns; that is accepted, not a defect to design around.

**Date format:** `Aug 20  17:43`, prefixed with the year (`2025 Nov 02  22:11`)
only when the recording is not from the current year. Safe because sorting uses
`mtime` (evidence #3).

**Link column:** narrows from ~35% of the width to 46px, showing `↗` on rows
uploaded this session. No capability is lost — double-click-to-open and the
right-click Copy link / Open menu items are unchanged, and the raw URL was
never selectable inside a Treeview. The existing `has_link` row colour remains
as a secondary cue.

**Row density:** `_apply_row_height` currently takes
`max(checkbox_height + 4, linespace + 3)`. A third term, `int(28 * scale)`, is
added inside that same `max()`, giving rows breathing room over 132 entries
while preserving both existing guarantees — the checkbox is never clipped, and
sv-ttk's own larger rowheight is never shrunk.

## Typographic hierarchy

Deliberately restrained, because ttk offers little per-cell control:

- Treeview headings: bold, via a named style.
- Panel section heading ("Upload"): bold, followed by a separator.
- Selection summary and hint labels: `MUTED` token, already defined in
  `theme.py` for both modes.
- Row text: unchanged. Per-column fonts are not available in `ttk.Treeview`,
  and per-row tags are already spent on zebra striping, preselection, and
  `has_link`.

## Compatibility and migration

No persisted data changes. `settings.json` and the duration cache are
untouched. No public interface has external consumers — this is a single
desktop application.

## Failure handling

Unchanged. The layout carries no new failure modes; the one new computation
(selection summary) reads values already in memory and treats an unprobed
duration as unknown rather than zero.

## Testing and verification

- The suite runs on Linux and contains no UI tests. Layout is therefore
  verified by driving real Tk windows on the WSLg display, with `tk scaling`
  set as `__main__.main()` sets it, and `root.update()` called before reading
  any geometry.
- New unit tests: `spacing()` scaling at 1.0/1.25/1.5, the date formatter
  (same year vs other year), the selection summary formatter — including a
  selection containing an unprobed recording, which must render the `+`
  partial marker — and `apply_titlebar` via an injected setter (asserting the
  no-op off Windows and the 20→19 fallback).
- One regression test for the staleness path: a summary computed over a
  selection with an outstanding probe, then `_apply_duration` delivering that
  probe, must leave the summary updated and the `+` marker gone. This is the
  bug the two-trigger rule exists to prevent, so it is tested rather than
  assumed.
- `docs/smoke-checklist.md` gains entries for what cannot be verified off
  Windows: both title bars dark and matching, both at startup and after a live
  OS theme switch; the panel at 100%/150%/200%; the ffmpeg-missing warning
  still visible and readable in its new position (extending the existing item
  at `docs/smoke-checklist.md:37-41` rather than duplicating it); and column
  behaviour at the minimum window size.

## Assumptions that may change

- A 300px panel at 100% is comfortable at the default 1350px width. It is
  fixed, so it costs proportionally more the narrower the window gets; see
  "Narrow windows — accepted degradation" for what that means at the floor. An
  earlier draft of this design claimed the list would still get ~420px of
  *comfortable* room at the minimum width, which was arithmetic that had not
  been done: the preferred column widths sum to 620px and do not fit. The
  minimums are what make the narrow case work, and the result there is cramped
  by design.
- `wm_frame()` returns the HWND `DwmSetWindowAttribute` expects. Unverifiable
  on Linux; the smoke checklist covers it, and a failure is cosmetic and
  caught rather than fatal.

## Explicitly out of scope

- Any change to theming, sv-ttk usage, DPI awareness, the Treeview choice, or
  the app icon — all delivered by PR #5.
- New features of any kind, including per-video titles, a resizable pane
  divider, tooltips, and relative ("2 hours ago") dates.
- Restructuring the Settings dialog beyond spacing and its title bar.
