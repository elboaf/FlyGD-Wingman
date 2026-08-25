# R4 handoffs — `ui/r4-skills`

Round-2 screen lane R4 (Skills). Findings owned: Skills 1, 2, 4, 5, 6, 9,
plus Skills 3's roster half and Skills 7's execution. Files owned:
`style.css`'s skills block, `web/skills.js`, `index.html #route-skills`.

Everything below is something R4 decided, found, or had to touch outside
its own region. Nothing here is a request to widen scope.

---

## Disclosure — one file edited outside R4's ownership

`tests/test_skills_page.py`, and the reason is the deletion the maintainer
approved.

The `@media (max-width: 720px)` block at the foot of the skills stylesheet
was **enforced by a test**. `test_the_rail_is_not_sized_only_against_100_
percent_scaling` asserted the block existed, and its docstring was the
disproven arithmetic verbatim: "MIN_WIDTH is 840 PHYSICAL pixels … the CSS
viewport floor is 672px at 125% scaling and 560px at 150%. A 214px rail is
38% of the window at 560."

**`DESIGN.md` does not know this.** Its table of unreachable queries names
exactly two as test-required — the `#eve-binds` and `#preview-binds` label
column restores in `test_page_conventions.py` — and then says "beyond
those two, each owning lane decides whether its block is a decision worth
keeping". Skills' block was a third test-required one. Deleting it turned
the suite red, and the test could not be left standing, because what it
pins is the error `#55` corrected everywhere else.

The test is kept and narrowed rather than removed: its first assertion —
the rail is 214px — was always a real invariant and still passes. The
second assertion and the docstring's arithmetic are gone, replaced by the
correction and the number that matters now (the rail leaves the roster
590px at the real 840 floor).

**To S4, or whoever next edits `DESIGN.md`:** the "beyond those two" line
is wrong by one. Worth checking the remaining three dead 720px blocks for
the same trap before another lane deletes one and is surprised.

## To S1, or whoever owns `:root` — a colour with no token

`#7aa2f7` is a literal, written three times inside the skills block:
`.key-Training`, `.status-Training` and `.state-Queued`. The comment above
them claimed "every value is an existing token; this route introduces no
new colour literals", which was untrue when written and is now corrected
in place.

Since the purple retheme it is **exactly** `--link`'s value. R4 did not
point them at `--link`: that token is the declared exemption for a link
*out of the app*, and a training state does not leave the application.
Reusing it would launder a collision into a false statement about meaning.

A token of its own — an informational/in-progress blue, distinct from the
outbound-link blue that happens to share its hex — belongs in `:root`,
which R4 does not own. Recorded, not fixed.

## To R1 — the `READY` header is not the sort-arrow cause

R1's handoff notes that Skills' `READY` header "may have the same
sort-arrow cause" as Uploader 3, where the offset turned out to be the
sort arrow on the sorted column rather than a scrollbar gutter.

It is not. There is no sort control anywhere on the Skills rail, and the
whole offset is accounted for without one: `.rail-plan` is
`border-left: 2px` plus `padding: 6px 8px`, and `.rail-head-row` had
neither, which is 10px on the left and 8px on the right — exactly the two
measured deltas, in opposite directions, from one missing declaration.
Restating that inset puts both at 0.00 at 840 and at 1600. Two screens,
two different causes, one rule.

The half of R1's note that DOES carry over is the one S1 wrote first: the
walkthrough's pixel figures are unverified. Skills 7's `~22px` and `~14px`
are physical off a 200% capture and measure 10 and 8 in CSS.

## To S4 — `docs/smoke-checklist.md`, if it names any of these strings

Four user-visible strings on Skills changed:

| was | is | why |
|---|---|---|
| `Unknown skill` (requirement state) | `Not trained` | C2 |
| `Unknown skills` (group header) | `Untrained requirements` | Skills 2 |
| `Unknown` (character status) | `Not trained` | C2 |
| `2 characters · 0 ready` (rail) | `2 characters` | Skills 4 |

The last one is a **deletion**, not a rewording: the ready count was
plan-scoped, presented as roster-scoped, and was the third copy of a
number the plan list and the group headers already carry with their scope
attached.

## Skills 3 — confirmed closed, no edit

S1 kept `Ready` on this screen and moved the status strip to `Idle`, and
its handoff said R4 had nothing left to rename. Verified against the
rendered page: the strip reads `Idle` while the roster shows the `READY`
column header, a `Ready 1` group header and a `Ready` character status.
Three uses, one concept, no collision with the application's idle state.
Nothing done.

## Skills 9 — proposed, NOT built

`worth trying`, so it is a proposal per the lane's rules.

`Filter characters` is a full-width field directly under the heading and
above the data, and the maintainer has never used it. It has a natural
condition and the screen already holds the count.

**Proposal:** render the filter bar only when the roster is large enough
to need it — hidden below a threshold, shown at or above it, with the
`Clear filter` affordance behaving as it does now. The threshold should be
a named constant in `skills.js` beside `GROUPS`, not a number inline.

**Not proposed:** removing it. Unlike `Import from an existing helper…`
(Settings 19) this control works and answers a real question on a large
roster; the finding is about its prominence at nine characters, not its
existence.

Two things to settle before building it, which is why this is a proposal:

- **The threshold.** A roster of nine — the current dev fixture — reads as
  scrollable but scannable. Somewhere between 8 and 12 is defensible and
  none of it is measured.
- **The disappearing-control problem.** A filter that vanishes as
  characters are forgotten, and reappears as they are added, is a control
  that moves the rest of the screen up and down under the reader. The
  Uploader has the same question open at finding 17 (`Stitch`), and the
  two screens should answer it the same way rather than each inventing
  one.
