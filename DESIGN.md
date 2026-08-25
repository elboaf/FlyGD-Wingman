# DESIGN.md

How the Wingman window is built, and why. Written after a review found the
same conventions broken in four places, in a codebase that documented every
one of them — in comments, inside the modules that already got them right.

This file is the reference a new screen is checked against.
`tests/test_page_conventions.py` enforces the mechanical half; everything
here that a regex cannot see is the reason this file exists as well.

The stack is plain HTML, CSS and ES5-flavoured JavaScript in a WebView2
window (pywebview), Windows only, dark only. No framework, no build step,
no bundler. Nothing in the test suite executes any of it.


## The one rule that explains most of the others

**Nothing renders this page except a real Windows machine.** There is no
JS test harness, no snapshot, no headless run. `pytest` proves the Python
side and reads the page's *source*; it never sees the result.

The failure mode that follows is specific and quiet. Handlers register at
the top of each module's IIFE, so one bad name throws mid-module and every
registration below it never runs. The screen loads as an inert copy of
itself — no data, no working buttons, and no error anywhere a user or a
test would look. `ui/api.py`'s `_push` renders as
`window.<handler> && window.<handler>(...)`, so the push is a no-op rather
than an error.

So: a broken screen looks like an empty screen. Assume any new screen is
broken until it has been opened by hand, and treat `docs/smoke-checklist.md`
as part of the change rather than as paperwork after it.


## Destinations vs. configuration

The title bar holds **destinations** — places you go to accomplish
something and stay. Settings holds **configuration** — screens you visit
twice ever, to switch a feature on and set it up.

The test is not how important a feature is. It is whether the screen
produces anything of its own. Bookmarks and Previews were top-level tabs
for four releases; neither shows anything on its own screen, because both
configure things that happen elsewhere — global keybinds that fire in EVE,
floating windows that appear on the desktop. They are Settings sections.

This matters because title-bar space is the scarcest thing in the app.

    unshrinkable content = nav + 3 window buttons + gaps + padding + 105px

That 105px is the drag region's floor: it is the only flexible child of
`.titlebar`, and with no `min-width` its automatic minimum resolves to the
wordmark's own width. Nothing else in the bar can compress at all — the nav
and the window buttons are both `flex: none`.

`MIN_WIDTH` is **840 logical pixels**, and the CSS viewport floor is
**840x625 at every display scaling**. `MIN_WIDTH` / `MIN_HEIGHT`
(`ui/window.py`) land in WinForms `MinimumSize` and `ptMinTrackSize`, both
of which Windows DPI-scales for a system-DPI-aware process, so the number
is already in the same units the page sees.

Measured, not derived: the floor capture is 1678x1242 physical on a
3840x2160 display at 200%, which is **839x621 CSS** against `MIN_WIDTH`
840 and `MIN_HEIGHT` 625. Were the floor 840 *physical*, that capture
would be ~840px across; it is twice that. The maintainer's standing
observation that the app cannot be resized to the CSS floors is this fact,
observed before it was explained.

> **This corrects a bold claim that stood here through four releases.**
> This file previously said `MIN_WIDTH` is "**840 physical pixels**, not
> logical … the CSS viewport floor is `840 / scale`: 672px at 125%, 560px
> at 150%". That arithmetic is wrong, and `docs/ui-critique.md` and
> `docs/smoke-checklist.md` were both written against it. **Do not size
> anything against a 560px or 672px viewport. Neither can occur.**

**Unresolved — the observation that produced the rule above.** This file
also reported that "five destinations needed 686px and clipped the close
button off the right edge at 125%". Both statements cannot be true as
written: at a floor of 840 CSS, 686px of unshrinkable content fits with
154px to spare and nothing should have clipped.

| | claimed | measured |
|---|---|---|
| viewport at 125% | 672px | 840px |
| unshrinkable content | 686px | unchanged |
| result | close button clipped | fits, with 154px spare |

This is **not** a claim that `#38` was wrong. Three destinations stand on
`PRODUCT.md`'s destination-vs-configuration test, which needs no pixel
argument, and something was evidently observed. What is suspect is the
recorded *reason* — and the reason is the tool the next contributor will
reach for. Reproduce the clip or establish that it cannot be reproduced
before relying on either number. Deliberately left open rather than
guessed at.

**What this means for `style.css`.** Every width media query below the
floor is unreachable through the window. As of the merge that carried this
correction there were eight, of which seven could never fire — but lanes
are deleting their own dead blocks and adding reachable ones, so treat the
*rule* as the durable part and re-grep before quoting a count:

| Query | Fires at the floor |
|---|---|
| `max-width: 931px`, `max-width: 840px` (the list's column tiers, added by R1) | **yes** — both are above the floor |
| `max-width: 839px` (the `.panel` 248px step) | **only at some scalings** — see below |
| `max-width: 767px` (the list's narrowest tier) | no |
| `max-width: 720px` x5 (status strip, two Settings blocks, the settings row, Skills) | no |

**`max-width: 839px` fires at 200% scaling and not at 100%.** At 100% the
floor viewport is 840 CSS and the query does not match. At 200% the floor
measures 839 CSS — the 840 logical minimum lands a client area of 1678
physical, and 1678 / 2 is 839 — so it matches, at the floor and nowhere
else. The Uploader's panel is therefore 248px wide on one machine and
320px on another, at the same window size, with nothing in the stylesheet
that predicts which.

**R1 settled this, and the answer was not to delete it.** It is a real
viewport — it is what the floor measures at 200% — so it is now the
narrower of two known floors and the panel is what gives there. What R1
did delete was the assumption underneath: the list's column tiers used to
sit at 767px and 607px, *below* a floor the window can never reach, so the
six-column layout was the only one that ever rendered. That is what made
`docs/ui-walkthrough.md`'s Uploader 11 possible — at 840 the Filename
track sat on a 120px floor while an OBS filename measures 205px, so the
column carrying the row's identity truncated away the seconds while
`Modified` sat intact beside it carrying the same timestamp.

**The lesson generalises past that screen: 839 is the floor at 200% only.**
A query written against it leaves 100% — the ordinary machine — unchanged.
R1 shipped exactly that mistake once and only a render caught it. If a tier
must fire *at* the floor, it is `max-width: 840px`.

**And a tier's floor is a measurement, not a round number.** The name track
is 212px now because that is what the window floor affords once `Modified`
gives way, and it clears the 205px a filename actually needs. 120px
measured nothing. The check that the whole chain still hangs together is
that the tier rendering **at** the floor needs exactly `MIN_WIDTH` —
`tests/test_uploader_page.py` asserts it, and it used to be the six-column
tier that held that position.

A rule the window cannot currently reach is not thereby wrong, and
unreachable is not the same as removable. Two of these blocks are
**required by a test**: `test_page_conventions.py` brace-matches every
`max-width: 720px` body and demands that each id override of the shared
label column — `#eve-binds` and `#preview-binds` — restore its collapse
inside one. They are unreachable through the window *and* mandatory, which
is not a contradiction: the override they correct is real at every width,
and the restore is the record of what happens if the floor ever moves.
Delete an override and its restore together, or neither. Beyond those two,
each owning lane decides whether its block is a decision worth keeping. Note that
`docs/ui-critique.md` credited one of these queries with doing the
scaling arithmetic "correctly": it is the `839px` one, and the credit was
earned against the wrong model, and the credit was misplaced.

**Before adding a destination, do the arithmetic.** `style.css` warned at
four; four features added one each without revisiting it, the last
describing the change as "seven edits, all mechanical". If it is mechanical
you are not deciding anything, which is the problem.


## Controls

**Checkboxes and radios must use the wrapper.** Nothing in `style.css`
targets `input[type=checkbox]` or `input[type=radio]`; the dark appearance
comes entirely from `.check > input + .box` and `.radio > input + .ring` —
the input is `opacity: 0` and the styled span beside it is what you see. A
bare input is a white Win32 widget on a dark card. This applies to controls
built in JavaScript too, which is where the worst instance shipped: one per
character, forty of them.

**Field labels go through `.lab`, and `.lab` sits above its control.**
`.settings .row > .lab` is full-width, left-aligned and `--text-dim`
across Settings *and* Profiles — both render `class="settings"`. The row
is `flex-wrap: wrap` with a 4px `row-gap`, so every label stacks above the
thing it labels and every control starts at the card's own left edge.

This did not invent a pattern. The Uploader's panel has always stacked its
labels above their controls, through a separate `.panel .lab` rule that is
not a `.settings` descendant and was never part of the column. Settings
now agrees with the one screen that was already doing it. A label outside `.lab` renders brighter than
every other label and at its own width — that is still the failure being
prevented, and it is still why three labels on one screen once sat at
47px, 84px and 71px. Prefer `<label class="lab" for="...">` over a
`<span>`: it keeps the control association a bare span throws away. An
empty `.lab` is hidden (`:empty { display: none }`) rather than left to
occupy a blank line.

**This replaced a 118px right-aligned column, and not because the column
was a mistake.** The column did its job: it made labels align with each
other across cards instead of per-card. What it could not do was reach the
sections that have no `.lab` at all — Notifications and General hold their
controls as direct card children. Measured at the floor from each card's
content edge, the first control sat at three different left edges:

| Section | First control |
|---|---|
| Account, Uploads, Folders, Discord | 128px |
| Bookmarks, Previews | 128px, with text at 152px |
| Notifications, General | 0, with text at 24px |

Each was internally consistent, which is why no single capture showed it
and switching rail items did. Stacking is the only answer available in CSS
alone: the two sections without a column cannot grow one without markup.
The column's original job is still done — labels still share one edge —
they now share it with everything else on the card.

**If you out-specify the label column, restore its collapse yourself.**
`#eve-binds` and `#preview-binds` take the column away from their rows on
purpose, because their labels are long action and character names. ID
specificity also beats the `max-width: 720px` block written against
`.settings .row > .lab`, so the collapse silently skipped exactly the rows
that needed it most. `tests/test_page_conventions.py` enforces the general
rule. See "What this means for `style.css`" above: those two restores are
unreachable through the window and mandatory, which is not a
contradiction.

**Open, not decided — the two stacked treatments are 1.5px apart.**
`.settings .row > .lab` is `--fs-body` (13px) with a 4px `row-gap`;
`.panel .lab` is `--fs-muted` (11.5px) with a 5px `margin-bottom`. While
one was a right-aligned column and the other a stacked block, nobody could
confuse them. Now they read as one pattern implemented twice, a pixel and
a half apart, and neither difference is recorded as deliberate. Whether
they should converge — and on which — belongs to whoever owns both blocks,
and it is in no lane's findings. Recorded here so it is not rediscovered;
do not fix it in passing.

*Note for anyone reading the tests:* the docstrings of
`test_settings_rows_label_through_the_shared_column` and
`test_an_id_override_of_the_label_column_still_collapses_at_the_floor`
still describe the 118px right-aligned column. **The assertions are
current and passing** — they forbid a bare `<label>` in a settings row and
require a restore per override, both of which still hold. Only the prose
is stale. Nothing is broken; do not go hunting.

**One accent per screen, or none.** `.btn.acc` is the single brand-accent
control. Zero is fine — a screen that applies immediately has no commit
action to accent. Two is two things claiming to be primary. Its label is
near-black on the brand, not white: white measures 3.08:1 on the gradient's
top stop.

**Accent marks what is selected and what will happen. A card heading is
neither.** The rule above is written about *controls*, so the Uploader's
`UPLOAD` and `PUBLISH` heading bars never breached its letter — they were
a third and fourth claim on a signal that carries exactly two meanings.
The signal is diluted by every use that is neither. On the Uploader that
is five accent uses down to three: the checked row's checkbox and its
left-edge marker (what is selected), and the `Upload` button (what will
happen); the two `.card > h2` bars lose it. This is about `.card > h2`
generally and not about one screen — the heading-bar treatment is not
confined to the Uploader, and whichever screen owns a card heading
inherits the rule.

**Never use `window.confirm`, `window.prompt` or `window.alert`.** WebView2
renders them as browser chrome captioned with the page origin — a grey box
mentioning localhost, in a frameless dark app. Use `WM.confirm` /
`WM.prompt`, which raise the app's own overlay. Python's `_confirm` cannot
serve a page-initiated dialog: it blocks the calling thread until
`dialog_response` arrives, so calling it from a bridge method deadlocks the
thread that has to deliver the answer.

**`hidden` needs an author rule.** An author rule beats the UA
stylesheet's `[hidden] { display: none }` regardless of specificity, so any
selector that sets a display needs its own `[hidden]` override or the
element stays visible. Six rules in `style.css` carry a note about this and
one shipped without it anyway.


## Saving

Settings has no Save button. Every field commits on its own through a
per-field endpoint returning `{applied, persisted, error}`.

Three outcomes, not two, because the page says something different for
each: **refused** (revert the control, explain inline), **applied but not
persisted** (leave the control, warn it will not survive a restart),
**done**.

**A refusal reverts the control. A failed write does not.** The setting
really did take effect for the session; snapping the control back would
misreport it.

**Discrete controls commit on change. Free text does not commit on blur.**
Folders and the webhook commit on Enter, or via an explicit affordance
(Browse, Detect, Remove). This is not fussiness:

- Committing a half-typed path that happens to name a real directory
  rebinds the watcher, and `Watcher.rebind` marks every file already in
  that folder as seen — silently suppressing the announcement for every
  recording that arrived this session, then doing it again to the right
  folder on the corrective commit. Not undoable from the UI.
- An empty webhook used to mean "clear it", so select-all, Delete and look
  away destroyed a credential. There is no Cancel and no pre-edit snapshot
  anywhere on the page.

**Nothing commits before the first payload has rendered.** `get_settings`
resolves asynchronously and every field is blank until it does; a commit
fired in that window writes blanks over a configured install. There is a
test recording that this once happened.

**An endpoint whose effect reaches outside its own control must apply that
effect locally.** There is no whole-document push to ride on any more —
that push is exactly what used to rewrite the field you were still typing
in. The EVE gate learned this twice: once by persisting without repainting,
once by clearing the current route but not the route the gear returns to.
**Hiding a screen means cutting every route into it, not just the one the
user is standing on.**


## Routes and sections

`WM.route` switches destinations; `WM.section` switches groups inside
Settings. Both dispatch an event, and both provide the same **enter and
leave** contract. Leaving Settings dispatches a section change too, so a
module folded into Settings learns about both.

Route and section entry is how screens **fetch**. There is no polling and
nothing is pushed at boot; a subsystem that costs nothing until you open it
must not push state at launch.

Leaving is load-bearing, not bookkeeping. `bookmarks.js` and `previews.js`
each install a document-level `keydown` listener while capturing a keybind,
and each disarms it on being left. `stopPropagation()` does not stop a
sibling listener already attached to the same node, so an armed capture
consumes the next keystroke typed anywhere and persists it into the wrong
bind, off-screen. The capture handler `preventDefault()`s every key
including Tab — an escaped capture inside Settings would swallow a folder
path or a webhook mid-type.


## Words

One name per concept, across every screen.

A key combination is a **keybind**. It was a keybind, a hotkey and a chord
on two adjacent screens that build the same widget. Identifiers may keep
older spellings where they cross the Python bridge — consistency with the
API outranks consistency with the label — but user-visible text may not.

A screen may not repeat its own tab name as its first card heading.

Say what a control does, not what it configures. A tab named "EVE
Settings" beside a gear named "Settings" describes the implementation and
confuses the reader; "Profiles" is what the thing is called.


## State that must not be retyped

Four places carried a count of the bookmark keybinds. `bookmarks.py`
defines eighteen; a confirmation said twenty-one, two comments said
nineteen, and the smoke checklist said twenty-one. The user-visible one
guarded the only irreversible action on that screen.

`tests/fakes.py` hand-listed the settings keys, so every new setting was
absent from the fake until someone remembered.

Derive it, or assert it in a test. A number that has to be kept in step by
hand will drift, and the copy that drifts is usually the one a user reads.


## Colour and type

Tokens live in `:root` and are the only place a colour is decided. Reducing
a token fixes every rule that uses it: `--text-faint` was below AA against
every surface it appeared on, and one edit fixed twenty-two rules.

Contrast floors: **4.5:1** for text (everything here is under 18px, so
nothing qualifies as large), **3:1** for a focus ring or a state border.

`color-scheme: dark` is declared, or WebView2 resolves UA-drawn chrome for
a light scheme against a near-black page.

Every interactive element needs a visible `:focus-visible`. One rule covers
them all. `:focus-visible` and not `:focus`, so a mouse click does not
leave a ring behind.

Column headers sit *below* body size deliberately: they label the data and
are not the data. Do not "fix" this.

**A header row is laid out by the same padding as the rows beneath it,
with no separate inset.** A header that does not share its column's inset
is not labelling that column. This licenses no change to header *size* —
see the paragraph above.

**And a sort indicator is laid out so that it cannot move the label. On a
right-aligned column that means ordering it before the label, not after.**
This is the second half of the same rule and it is the half that was
actually broken on the Uploader, which is worth recording because the
first half was written from a wrong diagnosis.

`docs/ui-walkthrough.md` reported the Uploader's headers ~16px right of
their data and blamed the scroll container's gutter, and reported `PLANS`
~22px left of its column and `READY` ~14px right of its own on Skills.
R1 re-measured its instance in the `?dev=1` harness at 1280x800 with 30
rows, comparing text ranges rather than boxes:

- **Padding was never the difference.** Unsorted, every Uploader header
  agrees with its column to within 2px — and that 2px is `.list-row`'s own
  `border-left: 2px solid transparent`, which the header does not carry.
  Matching it would mean giving the header a fake border, so it stays.
- **The gutter could not have been the cause anywhere.** `.grid-row`
  declares no `1fr`, so the tracks are left-packed and a narrower body only
  eats slack at the right edge. It cannot shift a column.
- **What moved was the arrow.** `.list-head > span.sorted::after` on a
  `flex-end` header takes the right end of the column and pushes the label
  off it — measured at 14px the moment that column was sorted, and back in
  line the moment another was. One column at a time, changing under the
  pointer, which is how it read as "every column, on every visit".

**Skills' instance is not yet re-measured, and R4 owns it.** `READY`'s
"~14px right" is the same figure R1 measured for `Size`, from the same
pass, on a header row that also has no scrollbar. Measure the arrow before
measuring anything else there.

Reserving the arrow's width is **not** the fix on its own, and shipping
that was R1's first attempt: an `::after` at the right end still owns the
column's right edge, so the label sits inboard whether or not the arrow is
drawn — consistently misaligned instead of intermittently. Order it before
the label and reserve the width on every header, so the label holds the
edge and nothing moves when the sort changes. Centred headers need the
reservation mirrored with a `::before` or it decentres them by half its box.

**Uploader 4 — `Modified` right-aligned over a left-aligned column — does
not reproduce and is not a rule here.** Measured, the header's ink begins
at x=477 and the data's at x=479; `justify-content` computes to the flex
default and the cell's `text-align` is `start`. Both left, since the
replatform. Recorded so it is not re-derived from the walkthrough.

**Treat that file's pixel figures as unverified until re-measured in CSS
px.** Some are physical pixels read off 200% captures and halve cleanly;
some are simply wrong. Both kinds are in it, and the two above are the
second kind.

**The one blue is a declared exemption.** `--link` is the single colour in
the app outside the palette, and it stays that way on purpose: an outbound
link keeps link-blue *because* it leaves the app, and a link recoloured
into the palette stops reading as a link. It is a token like any other —
7.4:1 on `--panel`, 7.7:1 on `--bg` — so "tokens are the only place a
colour is decided" holds. Do not unify it into the brand.

Both infinite animations are stopped under `prefers-reduced-motion`. An
indeterminate bar still has to say "working" without claiming a percentage.


## What this file cannot tell you

Whether a screen is worth adding. Whether a control belongs where you put
it. Whether the words are right. Whether the thing is any good.

The conventions here are floors, not a design. Clearing them is what stops
a screen being obviously wrong; it is not what makes it right.
