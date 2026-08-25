# UI layout observations — input for the next piece of work

**Source:** user screenshot (`obs.png`, repo root), taken from the built
Windows installer of branch `worktree-ui-refresh` at 100% display scaling,
dark mode, 132 videos listed, Settings dialog open.

**User's verdict: "dark mode is working — but the app is still pretty ugly."**

## What the theming refresh did deliver

Confirmed working in the screenshot: dark theming throughout; native Win11
widget chrome; the status dot beside "Connected"; right-aligned labels in
Settings ("Privacy:", "Category ID:", "Webhook URL:", "Gamelogs:"); the accent
Save button; the Discord (combat logs) frame intact with both Detect buttons;
the combat-log button present and unaccented in the action bar; nothing
clipped. The refresh succeeded at what it scoped.

## Why it still looks bad — the scoping mistake

The spec deliberately excluded layout and information design, treating
"look and feel" as theming + spacing + widget nativeness. That was the wrong
reading of the request. The result is a re-skinned version of the original
script's arrangement. Everything below is a layout problem that no amount of
theming can fix.

## Specific findings

1. **No outer margins anywhere.** "Video details" starts at x=0; the list
   touches both window edges; "Found 132 video(s)" is jammed into the
   bottom-left corner. The window content is flush to all four edges, so it
   reads as crammed regardless of widget quality. Highest impact-to-effort
   fix in the list.

2. **The least-used control dominates.** Title + the large empty Description
   box take the top ~170px — the most prominent space — and are only relevant
   at the moment of upload. The user's actual content (the video list) is what
   they opened the window to see. Candidates: collapse into one row, move into
   an expander, or relocate beside the upload action.

3. **Column headers are centered over left-aligned data.** Filename, Date,
   Size, Duration all centered; their values flush left. Reads as sloppy even
   when a viewer cannot name why.

4. **Column widths do not match content.** "YouTube Link" occupies ~35% of
   width and is empty for all 132 rows. Date is wide for `2026-08-20 17:45`
   (redundant year; consider relative dates). Size and Duration are wide for
   4-6 characters AND are numeric — they should be right-aligned.

5. **Settings dialog title bar is LIGHT while the main window's is DARK.**
   This is the `DwmSetWindowAttribute` call the spec descoped as an accepted
   limitation. Side by side in a single screenshot it reads as a bug, not a
   limitation. Reconsider descoping it — it is a ctypes one-liner.

6. **No typographic hierarchy.** Column headers, filenames, dates, and the
   status line are all the same weight and size. Nothing guides the eye.

7. **Row density.** Rows are tight; a little vertical padding would help
   scanning a 132-row list.

8. **Status bar is a bare string in the corner.** "Found 132 video(s)" could
   carry useful state (selected count, total size) and needs padding.

## Sequencing decision

User chose: finish the theming branch (the font-scaling regression must land
first — it is a real regression at 125%+ and does NOT show at the 100% of this
screenshot), then start layout as a SEPARATE piece with its own brainstorm and
spec.

Note layout changes alter how the app is operated, which the current spec
forbids — so this genuinely cannot be an extension of the existing plan.
