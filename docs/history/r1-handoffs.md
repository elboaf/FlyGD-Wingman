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

**R1 guessed that Skills 7 had the same cause. That guess was wrong, and
R4 disproved it.** Recorded here rather than quietly deleted, because the
way it was wrong is the same trap this section is about.

The guess was that `READY`'s reported "~14px right" was the same defect,
because it was the same number R1 measured for `Size`. R4 checked and
found: the Skills block contains **zero** `::after`, `::before` and
`content:` declarations, `READY` is a static span, and nothing on that rail
is sortable — so there is no arrow to be the mechanism. The real cause is
arithmetic and closes exactly: `.rail-plan` carries
`border-left: 2px solid transparent` plus `padding: 6px 8px` and
`.rail-head-row` carried neither, predicting 10px left and 8px right.
Measured: `PLANS` −10.00, `READY` +8.00, both to 0.00 after one padding
declaration. A sort arrow acts on **one** edge of one column; this was two
opposite edges fixed by one line.

**And the numbers never matched.** R1's `14` is CSS px measured in the
harness; the walkthrough's `~14` for `READY` is physical off a 200%
capture, so it is 7 CSS — against R4's measured 8. Likewise `~22` for
`PLANS` is 11 halved, against a measured 10. The match that made the guess
look plausible was a unit coincidence, in a figure R1 was simultaneously
warning R4 not to trust. Two screens, two causes, one rule.

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

## To R4 — `.linkbtn`'s padding now has two compensators, not one

Relayed from R5, who found it building F3 and asked that it not stay in a
chat thread. `.linkbtn`'s `padding: 4px 6px` is load-bearing in two
directions, and there are now **two** scoped `margin-left: -6px` rules
correcting for it:

- `.rail-plan-actions > .linkbtn` — Skills, pre-existing, **yours**
- `.firstrun-actions > .linkbtn` — R5's, PR #62

Change the padding on the class and both silently become wrong offsets,
and nothing in the suite catches it. `docs/ui-work-lanes-2.md` already
scopes R4 to `.linkbtn.danger`'s **colour only**; this is the concrete
reason, and it is now stronger than when that scope was written, because
the second compensator did not exist yet.

## The walkthrough's bad figures are bad in one particular way

Worth stating once, because there are now three instances across three
lanes and they are the same failure, not three unrelated errors:

| Finding | Reported | Actual |
|---|---|---|
| Uploader 3 | ~16px, "the scrollbar gutter" | 14px CSS, the sort arrow, sorted column only |
| Uploader 4 | right-aligned over left-aligned | left over left; does not reproduce |
| Skills 7 (R4) | ~22px / ~14px, "no shared inset" | 10 / 8 CSS; one missing padding declaration |
| F3 (R5) | 11 CSS px | 6px, entirely `.linkbtn`'s `padding-left` |
| Profiles 2 (R3) | ~1180px card, ~250px column | halved; the card is capped at 620 CSS |

In every case **the box was fine and something inside it moved** — padding
on the control, an `::after` on the header, a missing padding declaration
on a header row, ink versus border box. So the figure was measuring
something that was not the defect, which is why correcting the *units*
does not rescue these: the mechanism was misidentified first.

**Both failure modes are present and they are not the same.** Some figures
are physical off 200% captures and halve cleanly (Skills 7, Profiles 2);
some are wrong outright (F3, Uploader 4). Halving is not a general fix, and
a figure that halves to something plausible is not thereby verified.

**The trap R1 fell into is worth naming, because it is the subtle one.**
R1 warned R4 that the walkthrough's figures were unreliable and in the same
message inferred a shared cause from one of them matching a number R1 had
measured. It matched because R1's was CSS and the walkthrough's was
physical — a coincidence between a real measurement and an untrusted one.
**A number you do not trust cannot become evidence by agreeing with one you
do.** `DESIGN.md` carries the standing instruction; the practical form is
**find the mechanism before you trust the number, and measure text ranges
rather than boxes.**


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

## A `dev.js` conflict to expect, from outside round 2

The **preview-alerts** lane (`worktree-preview-alerts`, unmerged — a
feature branch rather than a round-2 lane) also edits `web/dev.js`: a
`preview` key with an `alerts` subtree in `settingsPayload`, and a
`get_alert_state` stub. R1 added `inert_notes` to the same object literal.

The two keys are additive and merge cleanly in meaning, but
`settingsPayload` will conflict **textually**. Whoever merges second should
expect that rather than discover it.

That branch also adds a third `<section class="card">` inside
`#section-previews`, which is **R2's markup** — worth R2 knowing before it
lands, since `docs/ui-work-lanes-2.md` puts the Previews alert
functionality explicitly out of round 2's scope but does not say another
branch is editing the same block concurrently.

Neither branch touches `get_preview_hotkey_state`; both looked at it and
both left it as out of scope, so the harness warning above is still
unowned by anyone.

## `dev.js` is unowned, and four lanes have now written to it

Reported independently by R3 and R4, and worth acting on rather than
noting. `docs/ui-work-lanes-2.md`'s region-ownership table does not name an
owner for `web/dev.js`, and by the end of wave 2 four sessions had edited
it on the honour system: S1 (the version fake), R1 (`inert_notes`), R3 (the
whole `eve_settings_*` family — the route had **no** stub at all, so
`?dev=1` rendered Profiles inert, which is why the screen with the most
findings was the one nobody could eyeball), and R4 (the skills fixtures).
The preview-alerts branch makes five.

It merged clean this round. That is luck, not design, and the file is the
one thing every lane verifies through.

**It also merged clean and WRONG, which is the sharper version.** R2 added
`inert_notes` to `settingsPayload` independently of R1, for Settings 1's
`previews_off`. Git merges the two without a conflict, and the result is
one object literal with **two `inert_notes` keys five lines apart** — legal
JS, last one wins, nothing warns, and R2's existing test asserting the
strings against `ui/copy.py` still passes, because both copies are correct.
Whichever of #60 and #64 lands second silently drops its own copy.

Nothing is broken either way here (same two sentences, both derived from
`copy.py`), but the *class* of failure is the one this file exists for.
R2's `test_the_dev_harness_declares_each_payload_key_once` on `ui/r2`
(`8e9787a`) is what makes it loud:

    dev.js declares these settings-payload keys more than once, so the
    harness renders whichever came last: ['inert_notes']

**On rebase, drop the duplicate rather than merging around it.** And note
what this means for the unowned-file problem generally: a shared file with
no owner does not fail at merge time, it fails at render time, on whichever
route lost the coin toss.

**The concrete consequence, which nobody currently owns:** R3 test-merged
all four wave-2 PRs with `git merge-tree --write-tree` and found no
conflicts — but a clean textual merge is not a rendered page, and each of
us has only vouched for our own route. Whoever lands last produces a
combination nobody has opened, which is exactly the failure the top of
`DESIGN.md` describes: a broken screen looks like an empty screen and the
suite stays green through it.

**Someone should do one `?dev=1` pass over all five routes after the final
merge**, in addition to the per-lane hand passes. It is one browser load
and it is the only check that sees the combination.
