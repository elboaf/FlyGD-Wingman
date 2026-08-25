# R1 handoffs — `ui/r1`

Round-2 screen lane R1 (the Uploader). Everything below is something R1
**decided**, **found** or **could not close**, that another lane owns or
that the next contributor would otherwise have to rediscover.

R1's edits are in `web/index.html` (`#route-main` only), `web/list.js`,
`web/panel.js:1-101`, `web/style.css` (the recording-list and upload-panel
regions), `web/dev.js`, and — by explicit authorisation, because the
owning lanes had merged — `style.css`'s `.card > h2::before`,
`ui/api.py`, `ui/copy.py`, `ui/rows.py`, `library.py`, `durations.py` and
`docs/smoke-checklist.md`.

---

## Two `sure` findings did not survive measurement

Both were re-measured in the `?dev=1` harness at 1280x800 with 30 rows,
comparing **text ranges** rather than boxes, exactly as S1's handoff asked
("treat all three as unverified and re-measure in CSS px before sizing
anything to them").

**Uploader 4 — `Modified` is a right-aligned header over a left-aligned
column — does NOT reproduce. Closed, not fixed.** Measured, the header's
ink begins at x=477 and the data's at x=479, and `justify-content` on the
header computes to the flex default while the cell's `text-align` is
`start`. Both are left-aligned and have been since the replatform
(`16c0414` added the header-anchoring rules). Nothing was changed for it.
The 2px is `.list-row`'s own `border-left: 2px solid transparent`, which
the header does not carry; matching it would mean giving the header a fake
border, so it stays.

**Uploader 3 is real but is not the scrollbar gutter.** The walkthrough
blamed the gutter and reported ~16px on every column. Unsorted, every
header agrees with its column to within that same 2px — and the gutter
could not move anything regardless, because `.grid-row` declares no `1fr`,
so the tracks are left-packed and a narrower body only eats slack at the
right edge. What moves is the **sort arrow**: on a `flex-end` header the
`::after` takes the right end of the column and pushes the label off it,
measured at 14px the moment that column is sorted and back in line the
moment another is. One column at a time, changing under the pointer, which
is how it read as "every column, on every visit".

Fixed by ordering the arrow *before* the label on right-aligned headers
and reserving its width on all of them. **Reserving the width alone was
not enough and the first attempt shipped that mistake** — an `::after` at
the right end of a flex-end header still owns the column's right edge, so
the label sat 12px inboard whether or not the arrow was drawn:
consistently misaligned instead of intermittently. Only a render caught
it.

**To R4, who executes the same rule on Skills:** the walkthrough's figures
for `PLANS` (~22px left) and `READY` (~14px right) are from the same pass
and deserve the same scepticism. Skills' header row has no scrollbar
either. Measure the arrow before measuring anything else — `READY`'s
"~14px right" is the same number this lane measured for `Size`, and it may
be the same cause.

## To S4 — `DESIGN.md`'s header rule needs one more sentence

The rule as written ("a header row is laid out by the same padding as the
rows beneath it, with no separate inset") is correct and was not the whole
of either instance. Padding was never the difference on the Uploader. The
sentence worth adding is about what a header row may put *in* its own box:

> A sort indicator is laid out so that it cannot move the label. On a
> right-aligned column that means ordering it before the label, not after.

S4's files are otherwise current with this lane; `docs/smoke-checklist.md`
was updated here directly (the maintainer authorised it after S4 merged).

## To R2 — a `?dev=1` gap on your screen, and one measurement habit

`dev.js` has never stubbed `get_preview_hotkey_state`, so every harness
load logs `bridge: no such method: get_preview_hotkey_state` three times.
It is pre-existing (confirmed against `origin/main`) and harmless in the
app, but it is noise in exactly the place a Previews change gets verified,
and it looks like a real bridge failure until you check. R1 added
`inert_notes` to `dev.js`'s settings payload while wiring Uploader 8's
sentence — **you need that key too** for Settings 1's `previews_off`, and
it is already there.

The measurement habit, because it cost this lane two wrong fixes: the
absolutely-positioned `[data-tip]::after` reports an overflow on every
element carrying a tooltip, at every width. A **constant** figure across
widths is that; a figure that grows as the window narrows is real. R1
briefly chased a `list-scroll +46` that was purely the new `—` cells'
tooltips.

## To R4 — a third Length glyph exists now

`library.VideoInfo` gained an `answered` field and `duration_str` a third
return value, `—`. Nothing on Skills reads durations, so this is FYI: if
you add a `CELL_HELP`-style table, `tests/test_tooltip.py`'s cross-check
between `ui/copy.py` and `web/list.js` is the pattern, and it is what
caught the copy staying in step here.

## Findings this lane declined, with the reason

**Uploader 17 — reveal `Stitch` only above one selection. Declined.** The
walkthrough proposed it as one lever resolving three findings, and by the
time it could be built its own justification had gone: Uploader 8's
removal of the combat-log checkbox resolved 15 outright (two confusable
checkboxes minus one is one), and 9 and 13 are answered structurally. What
remained was a control that appears and disappears under the pointer, on
the one screen with a recorded mis-click. `Stitch` is **disabled** below
two selected instead — S1's `setEnabled` rule exactly, no layout change,
and the box is force-unchecked so a stale tick cannot reach `start_upload`.

**Uploader 7 — superseded by 15 in the walkthrough itself**, and 15 by
Uploader 8. No separate work.

## What is still open

**Uploader 9's exact symptom was not reproduced, only its mechanism.** The
walkthrough describes `Upload` clipped to "about 15px of accent and no
label". Measured on `main` at the floor with no webhook and everything
selected, the panel overflowed its pane by 5px at 840 and 38px at 839 —
real, and enough to put `Delete selected` below the fold, but ~40px short
of clipping `Upload` itself. The most likely missing 40px is the
`#destination` line wrapping once a channel is known, which the harness
cannot produce because `dev.js` has no post-upload state. The restructure
returns ~97px, so the panel now has 0 overflow in every state the harness
can build — but if anyone sees `Upload` clipped again, that wrap is where
to look first.

**The filename floor is 212px and covers this group's template, not every
template.** "Fight 2026-08-24 17-57-37.mkv" measures 205px; 212 is what
the window floor affords once `Modified` gives way. A scene name much
longer than `Fight ` will still ellipsise, and because the ellipsis takes
the tail, it will reach the timestamp again. Not designed around, because
OBS's default template is what the finding was confirmed against — but a
middle-ellipsis is the fix if it ever comes back.

**`test_the_widest_layout_needs_exactly_the_measured_window_floor` was
renamed and its premise moved one tier down.** It asserted that the
six-column layout needs exactly `MIN_WIDTH`, which was true and was the
defect: it meant the layout rendering at the floor was the one whose name
track sat on an arbitrary 120px. It now asserts that whichever tier
renders **at** the floor needs exactly `MIN_WIDTH`, which is the same
check on the same arithmetic and survives a tier being inserted above it.
The agreement between the stylesheet and `ui/window.py` is intact and is
still the thing that makes that file trustworthy.
