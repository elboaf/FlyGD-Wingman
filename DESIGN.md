# DESIGN.md

How the Wingman window is built, and why. Written after a review found the
same conventions broken in four places, in a codebase that documented every
one of them — in comments, inside the modules that already got them right.

This file is the reference a new screen is checked against.
`tests/test_page_conventions.py` enforces the mechanical half; everything
here that a regex cannot see is the reason this file exists as well.

The stack is plain HTML, CSS and ES5-flavoured JavaScript in a WebView2
window (pywebview), Windows only, dark only. No framework, no build step,
no bundler. Focused Node harnesses execute selected production modules against
DOM/bridge doubles, including setup sharing's owner and route wiring. They do not
render CSS or exercise Windows/WebView2.


## The one rule that explains most of the others

**Only a real Windows/WebView2 run proves the shipped window.** The Node
smoke runner loads every page module; focused runtime harnesses also execute
production handlers with controlled DOM/bridge doubles and delayed replies,
including Settings, Skills and setup sharing. They catch registration and
response-ordering failures, not layout, focus behavior in WebView2, or native
lifecycle behavior. `pytest` proves Python and selected JavaScript lifecycle
behavior, with most web conventions still checked lexically; it does not render
the page.

**A rendered browser check is not Windows/WebView2 acceptance.** Browser geometry
and interaction checks must be recorded separately from installed Windows smoke
results. The historical floor measurements below retain that distinction.

The failure mode that follows is specific and quiet. Handlers register at
the top of each module's IIFE, so one bad name throws mid-module and every
registration below it never runs. The screen loads as an inert copy of
itself — no data, no working buttons, and no error anywhere a user or a
test would look. `ui/api.py`'s `_push` renders as
`window.<handler> && window.<handler>(...)`, so the push is a no-op rather
than an error.

So: a broken screen looks like an empty screen. Assume any new screen is
broken until it has been opened by hand, and treat `docs/smoke-checklist.md`
as part of the change rather than as paperwork after it. **Crossing the
bridge**, below, has the whole of that contract — the allowlist, both ways
it can be broken, and what the test that guards it cannot see.


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

This is **not** a claim that `#38` was wrong. Four destinations stand on
`PRODUCT.md`'s destination-vs-configuration test, which needs no pixel
argument, and something was evidently observed. What is suspect is the
recorded *reason* — and the reason is the tool the next contributor will
reach for. Reproduce the clip or establish that it cannot be reproduced
before relying on either number. Deliberately left open rather than
guessed at.

**Fourth destination, measured (SDD task 6, `2026-09-03-character-
fittings`).** Adding Fittings brought the bar to four destinations, which
is the one arithmetic this file warns against skipping two paragraphs
above ("four features added one each without revisiting it"). Measured in
headless Chromium (`google-chrome`, driven over CDP with `puppeteer-core`,
loading `wingman/web/index.html?dev=1` so the fake API answers without a
Python process) at the two CSS viewport widths this file already
identifies as the floor — 840 (100% and every scaling below 200%) and 839
(the 200%-only floor) — with `deviceScaleFactor: 1`:

| | 840px | 839px |
|---|---|---|
| titlebar client width (`.titlebar` rect) | 840px | 839px |
| `document.scrollWidth == clientWidth` | 840 == 840 | 839 == 839 |
| drag region width, left/right edge (105px floor) | 379.9px, 16–395.9 | 378.9px, 16–394.9 |
| nav (`#routenav`) left/right edge | 405.9 / 672 | 404.9 / 671 |
| gear (`#btn-settings`) left/right edge | 682 / 726 | 681 / 725 |
| minimize (`#btn-minimize`) left/right edge | 736 / 780 | 735 / 779 |
| close (`#btn-close`) left/right edge | 790 / 834 | 789 / 833 |
| destination labels visible | 4 (Uploader, Profiles, Skills, Fittings) | 4 |

All four of Task 6's acceptance conditions hold at both widths: nothing
overflows (every edge above sits inside the 840/839 titlebar client
width), the close button's right edge (834/833) stays inside it, and the
drag region is still more than 3.5x its 105px floor.

**Task 12 release-integration recheck.** After the full Fittings route, dev
fixtures and screenshot staging were present, the exact dev page was loaded
again from a cleared browser cache and exercised over CDP. The same 840/839
measurements held: `scrollWidth == clientWidth`, drag widths 379.86/378.86,
nav edges 405.86–672/404.86–671, and close edges 790–834/789–833. All four
labels remained visible. This settles the browser-side route/chrome behavior
for the completed screen, not only the Task 6 shell. It still does not turn a
Chromium measurement into Windows/WebView2 evidence; the scaling pass below
remains open.

**This does not resolve the "Unresolved" question directly above, and is
not offered as a substitute for it.** This file's own opening rule is that
only a real Windows/WebView2 run proves the shipped window; headless
Chromium is not WebView2 and cannot reproduce Windows' DPI rounding — the
fact that makes an 840 logical minimum measure as 839 CSS px at 200% is a
WinForms/Windows behaviour (`ui/window.py`'s `MinimumSize` /
`ptMinTrackSize`), not a browser one, and no headless run can exercise it.
What this measurement DOES confirm is the CSS layout arithmetic itself:
that four destinations' worth of nav buttons, at these two exact pixel
widths, do not overflow the titlebar — which is the "do the arithmetic"
check Task 6 asked for before building the rest of Fittings. **The actual
100%/125%/150%/200% Windows display-scaling smoke pass
(`docs/smoke-checklist.md`) is still required and remains UNVERIFIED as of
this task** — no real Windows/WebView2 environment was available to this
change, and this measurement must not be read as having produced that
evidence. Treat the smoke item as open until it is actually run.

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

**A six-column layout exists again, and the distinction is the whole
reason it is allowed to.** The `Age` column was restored above the floor,
so five columns is now the *floor* layout rather than the widest one. The
old six-column tier sat ON the floor with a 120px name track, which is why
it truncated the filename; this one needs 924 and sheds at 923, so the
layout that renders at 840 is still the five-column one that fits there
exactly. "The tier at the floor needs exactly `MIN_WIDTH`" is unchanged —
what changed is that the tier at the floor is no longer also the base, and
the test was updated to assert that separation rather than their
equality.

A rule the window cannot currently reach is not thereby wrong, and
unreachable is not the same as removable. Some of these blocks are
**required by a test**, and this file has already undercounted them once,
so: **grep `tests/` for the selector before deleting any media query.**

`test_page_conventions.py` brace-matches every `max-width: 720px` body and
demands that each id override of the shared label column — `#eve-binds` and
`#preview-binds` — restore its collapse inside one. Those two are
unreachable through the window *and* mandatory, which is not a
contradiction: the override they correct is real at every width, and the
restore is the record of what happens if the floor ever moves. Delete an
override and its restore together, or neither.

**They were not the only two.** This file previously said "two", and
`tests/test_skills_page.py` was separately asserting a `max-width: 720px`
block containing `#route-skills` — a third, named nowhere. R4 found it by
turning the suite red while deleting a block this file had implied was
theirs to judge. The count is not the durable part; the grep is. Beyond
what a test requires, each owning lane decides whether its block is a
decision worth keeping. Note that
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

**A checkbox in a table column carries no word, and still carries a name.**
Under a column header the word beside the box is the header repeated once
per row — on the Previews character list that was three words × thirteen
rows, and because the tracks are `max-content` the longest of them set a
width every row paid for. That is the state the rule was argued from, and
it has since been acted on twice over: two of those three columns, `Lock`
and `Never minimize`, have left the table for disclosures under the global
toggles they are exceptions to, and only the `Preview` box is still a
checkbox in a column here. The rule is unchanged — it is about any
checkbox under any column header — but its worked example is now one
column, not three. The `.check` wrapper stays (it is what makes the
box dark), the label's text goes, and the accessible name moves onto the
input as an `aria-label` naming the row: an empty `<label>` is what a
screen reader would otherwise read. `.check input` is `position: absolute`,
so it is not a flex item and the wrapper's 9px gap reserves nothing beside
a box with no text.

Build the wrapper **immediately after** `input.type = 'checkbox'`, before
any listener. `test_page_conventions.py` looks for `'box'` within 600
characters of that assignment, and a commit handler in between is easily
long enough to push it out — the guard is right and the fix is the
ordering, not a wider window.

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

The table above is the measurement that decided this and is left as it was
taken. Three things have moved under it since, none of which changes the
argument: `Notifications` is no longer a rail entry — its one radio pair is
the second card under `Uploads` — and five labels that only restated the
control beside them have been deleted, because stacking changed what a
label costs from 118px of gutter to a whole line. A label now earns its
line by naming a GROUP the controls do not name themselves (`Status` over
a pill and a button, `Copy` over a radio pair) or by labelling a text input,
which has no self-describing text.

The third is round 5's E1, and it renames most of the first column: the
rail merged `Account`, `Uploads`, `Folders` and `Discord` into one entry,
`Uploading`; `Characters` and `Alerts` became entries of their own. Fleet telemetry
now has a separate entry too. The rail order is Uploading, Companion previews,
Character access, Bookmarks, Previews, Fleet telemetry, Alerts, General, asserted
in `test_settings_page.py`. Companion previews is independent of the EVE-tools gate.
The rows above still describe the same cards, which is why the measurement
stands — the first control's left edge is a property of the card, not of
the rail entry it is reached through. With the EVE gate off the rail is
three entries, `Uploading`, `Companion previews` and `General`.

**If you out-specify the label column, restore its collapse yourself.**
`#eve-binds` and `#preview-binds` both take the column away from their
rows, for two different reasons that make the same hole. `#eve-binds` does
it because its labels are long action names and it gives them a whole line
instead. `#preview-binds` does it to give the character name a
length-bounded `minmax(150px, 260px)` track of its own — an inline column,
not a line — so the name is a cell in the table rather than a heading above
it. Either way ID specificity beats
the `max-width: 720px` block written against `.settings .row > .lab`, so
the collapse silently skipped exactly the rows that needed it most.
`tests/test_page_conventions.py` enforces the general rule. See "What this
means for `style.css`" above: those two restores are unreachable through
the window and mandatory, which is not a contradiction.

**Round 3's B1 shared shape is retired, and the half that is not.** B1
found the two bind lists rendering one row at two geometries: each list's
first track was `max-content` over ITS OWN labels, so the bind button sat
189.6px into Bookmarks and 86.2px into Previews — 103.4 CSS px apart in
two sections of one screen, and Previews' half moved between sessions
because the track followed whoever was logged in. The fix was to delete
the column in both and stack the name above its controls. That cured the
offset, and it also gave the Previews list a shape sized for Bookmarks'
content: thirteen characters read as thirteen headings, with the column
headers off screen by the sixth row.

So the two lists no longer share a shape, deliberately. They differ in
content — "Convert EvE-Scout Bookmarks" is 189.6px and genuinely needs its
own line, while character names are uniform and short — and only four
ungrouped Bookmarks rows were ever in the shared grid anyway, round 5's C8
having moved the other fourteen into `.bind-dense`, which is flex and
shares no tracks at all.

**What did NOT retire is the ban on a `max-content` first track**, which
was the actual bug. Each list must reach its shape on purpose: Bookmarks
by spanning its label, Previews by a column whose every part is a length.
Neither may arrive at one by letting the track follow its own content.
`test_each_keybind_list_declares_a_deliberate_first_track` is the guard,
and it is what replaced the old cross-list equality test. Do not restore
that test from B1's reasoning — the reasoning is recorded here precisely
so the conclusion is not re-derived from it.

Round 6 widened Previews' column from a flat `150px` to
`minmax(150px, 260px)` and the ban was unaffected, which is the point worth
recording: B1 forbids a track sized *by the roster*, not a track that
varies with the WINDOW. Both ends are lengths, so the column still cannot
move between sessions with whoever is logged in — it simply stops
ellipsizing a name to 106px on a window that has 191px of unused gutter
beside it. `_preview_binds_cell_tracks` in `test_page_conventions.py`
checks the rule rather than the spelling, and rejects `max-content`
anywhere in the track including inside a `minmax()`, which the regex it
replaced could not see.

The current Preview table uses `minmax(200px, 260px)`. Step 4's rendered floor
check found the intervening 210px minimum needed 596px in a 592px pane; 200px
removes overflow without shrinking action hit areas. The 260px ceiling brings
controls closer on wider panes. Clear/Edit keep their shared, right-aligned cell.

**Open, not decided — the two stacked treatments are 1px apart.**
`.settings .row > .lab` is `--fs-body` (13px) with a 4px `row-gap`;
`.panel .lab` is `--fs-muted` (12px) with a 5px `margin-bottom`. (It was
1.5px and 11.5px when this was written; round 5's G3 moved `--fs-muted`
to 12px, which narrows the gap and does not close it.) While
one was a right-aligned column and the other a stacked block, nobody could
confuse them. Now they read as one pattern implemented twice, a pixel
apart, and neither difference is recorded as deliberate. Whether
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

**Four treatments, and this is the whole list.** Round 3 counted five
vocabularies for "clickable" — accent button, neutral button, red-outlined
button, red text, dim text — with no rule about which meant what, so three
screens each invented an answer for the same destructive verb. What a
control looks like is decided by what it *means*:

| treatment | means |
|---|---|
| `.btn.acc` | the one action the screen exists to perform — one per screen or none, per the rule below |
| `.btn` | every other action; the default, and reaching past it needs a reason from this table |
| `.btn.danger` | the action destroys something the user cannot get back by clicking again |
| `.linkbtn` | the quiet tier, which takes a stated reason — see below |

`.linkbtn` is not a volume knob. Two reasons are admissible, and both are
already load-bearing in the app:

1. The action is **subordinate** to the control or field it trails and as
   a `.btn` would compete with it — `Clear` and `Edit…` belong to the
   `.bindbtn`, `Clear filter` to the filter field, `Set this up later` to
   `Continue`.
2. A full-width `.btn` would put **its own label into a rail's width
   floor**. Skills' `Open plans folder` and `Reload plans` are `.linkbtn`
   for this reason and `index.html:774-781` reasons it out.

Neither reason and it is a `.btn`, however minor it feels: `Change…` on
Profiles is one because nothing else on its row acts, so link-styling made
the only control the least control-like element present
(`index.html:632-638`).

The four cover actions **on a surface**. Three other clickable families sit
outside the table and are not exceptions to it: **chrome** (`.navbtn`,
`.winbtn`, `.rail-item`, `.rail-plan`) navigates rather than acts; **value
controls** (`.bindbtn`, `input.field`, `.check`/`.radio`) hold a value
rather than performing one; and **menu items and outbound links**
(`.ctxmenu button`, `.linkish`, `.glyph-link`) take their shape from the
menu they sit in or from `--link`'s own rule about leaving the application.
A menu item is still an action control for the disabled rule below — that
exclusion is about shape, not behaviour.

"Red text with no button" is not a treatment; `.linkbtn.danger` survives at
one site pending its conversion and must not gain a second.

**The rule was ahead of its sites, deliberately.** Round 3 landed the
primitive in its own lane so that three screen lanes would convert to one
thing rather than invent a third answer between them. At that point,
`Delete selected` on the Uploader and `Remove` were plain `.btn`s that
destroy something. `Remove` now removes the webhook from Settings › Uploading
and uses `.btn.danger`. The current EVE credential
cleanup lives under Settings › Character access rather than on the Skills page,
so this rule must not drift back toward a second inline destructive style.

**Destructive treatment, confirmation, and mechanism are three questions,
not one.** Conflating them is how `Restore` nearly got red-outlined:

- **`.btn.danger` when** the action destroys something unrecoverable — a
  recording, a backup, a stored credential, a refresh token. Not "this is
  important", and not "this is tedious to undo".
- **A destructive action confirms, but a confirmation does not imply the
  treatment.** `Restore` overwrites a live profile and confirms, yet stays
  a plain `.btn`, because it backs the profile up first and the dialog says
  so — nothing is destroyed. (The dialog text is in `ui/api.py`'s
  `eve_settings_restore`; `evesettings.js` reasons out the *treatment* at
  the site, not the backup.) Removing the webhook from Settings › Uploading
  destroys the webhook credential. It now confirms through `WM.confirm`
  in `settings.js`; the old single-click removal did not meet this rule.
- **Which confirmation** is decided by the thread the action runs on, and
  that is the table under *Which confirmation, and why* below.

**One disabled state.** A control whose object is absent is disabled —
`WM.setEnabled` in `app.js` carries the rule for *when*, including the
constraint that nothing may disable the only route out of the state that
disabled it. What disabled *looks* like is one declaration in `style.css`
covering `.btn`, `.linkbtn`, `.bindbtn` and context-menu items, and every
one of their `:hover` rules excludes `:disabled`. Among those four it had
been two answers and two omissions: `.linkbtn` and `.bindbtn` had no
disabled state at all, so a dead control still lit up under the pointer. A
few controls outside the four keep scoped rules of their own for stated
reasons — `#lab-stitch`, the three `#es-*` dropdowns — and the accent
button adds `grayscale` on top of the shared one rather than replacing it.

**One accent per screen, or none.** `.btn.acc` is the single brand-accent
control. Zero is fine — a screen that applies immediately has no commit
action to accent. Two is two things claiming to be primary. Its label is
white on the brand: `#fff` on `--acc-fill`'s stops measures 5.26:1 at the
top and 7.35:1 at the bottom. The near-black label this file asked for
until 3.3.0 was measured against the retired vermilion brand, where white
managed only 3.08:1; the purple retheme inverted that, and the button has
shipped white-on-purple since. Re-measure from `style.css`, not from a
screenshot — a capture of this button samples the top stop as `#9034E3`
and the label as `(244,236,251)`, which is antialiasing and the accent
glow, not what the sheet declares.

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

**`hidden` needs an author rule.** An author rule beats the UA
stylesheet's `[hidden] { display: none }` regardless of specificity, so any
selector that sets a display needs its own `[hidden]` override or the
element stays visible. Six rules in `style.css` carry a note about this and
one shipped without it anyway.


## Crossing the bridge

Two mechanics here are enforced — or punished — somewhere other than where
you would look for them. Both were derivable only by reading four or five
call sites, and both have been stated wrongly in planning documents written
by people who had read this file — which is why they are in it now.

**A handler name is a three-way contract.** `web/app.js` keeps the
`WM.HANDLERS` allowlist, `ui/api.py` pushes into it, and each screen module
registers out of it with `WM.handle()`. All three have to agree, and the two
ways they can disagree do not fail alike:

| mismatch | what happens |
|---|---|
| `_push("x")` where `x` is not in `WM.HANDLERS` | **Silent no-op.** The push renders as `window.x && window.x(…)`, and `_push` swallows `evaluate_js` failures at debug level. Nothing happens and nothing says so. |
| `WM.handle('x')` where `x` is not in `WM.HANDLERS` | **Throws at registration** — and every handler declared below it in the same file never registers. |

The second row is the mechanism behind this file's opening rule: it is *why*
a broken screen looks like an empty screen. It has happened —
`onEveSettingsRunning` was pushed from `ui/api.py` and registered in
`evesettings.js` without being added to `WM.HANDLERS`, and the whole EVE
Settings route broke while every test still passed.

`tests/test_bridge_contract.py` now asserts both directions, and it is
purely lexical, so know where it stops looking before trusting it: it reads
only `self._push("literal", …)` calls (and `_push_cb("literal", …)` in
`eveskills/controller.py`) and only the `WM.HANDLERS = [...]` array
literal, so a name built or appended at runtime is invisible to it; and an
allowlist entry that nothing registers is deliberately not an error,
because it may be pushed from somewhere other than `ui/api.py`.

`scripts/js_smoke.js` is the executable half of the same guard: it loads
every page's modules under node and fails on anything an IIFE throws,
which is how the second row of the table above actually fails. Its header
says what it cannot see — a handler body on a real payload, a missing
element id, anything painted.

**Which confirmation, and why.** Never `window.confirm`, `window.prompt` or
`window.alert`: WebView2 renders them as browser chrome captioned with the
page origin — a grey box mentioning localhost, in a frameless dark app. Four
mechanisms ship in their place, and the thread the action runs on picks
between them:

| the action runs… | use | why |
|---|---|---|
| page-side, page-owned | `WM.confirm`, `WM.prompt`, or `WM.choose` (`panel.js`) | the app's own overlay, and the only one safe on the bridge thread |
| on a Python worker | `Api._confirm` (`api.py:412`) | blocks the calling thread until `dialog_response` arrives — from a bridge method that deadlocks the very thread that has to deliver the answer |
| on a worker **holding the mutation lock** | `Api._eve_confirm` (`api.py:2851`) | `_confirm` bounded by `EVE_CONFIRM_TIMEOUT_S`, with a missing answer read as **no** |
| where the row is the only surface for the action | inline two-step (`skills.js:717`) | a dialog would cover the thing being acted on |

`WM.choose` is the compact source-picker variant, not a reason to turn every
selection into a modal. It is for a bounded choice whose inline form would
break the surface it belongs to, such as the Previews table's shared grid.
Options are built with DOM text properties, grouped in words rather than by
colour, and its `<select>` participates in the same focus trap, Escape-is-
Cancel behavior, queue, and focus restoration as the other page-owned
requests. The scrim is also Cancel, but only when both press and release land
on it: a text-selection drag that starts inside the dialog must not discard a
prompt value when it overshoots the edge. A keybind-capture screen disarms
capture before opening any of the three: its document listener consumes Tab as
well as printable keys. A delayed dialog answer must recheck the page interaction
that admitted it before sending a mutation; leaving, staging or newer capture can
revoke that interaction without cancelling an already-sent operation's receipt.
The shared dialog queue restores its original invoker (or visible fallback) only
while it still owns return focus. Focus outside the visible overlay revokes that
ownership until the queue drains; blur or re-entry into the dialog cannot revive
it. An old Saved/Size/Copy answer must not steal a newer capture's actual focus.

The third row's bound is not caution. `_push` swallows every `evaluate_js`
failure, so a confirmation whose push never reached the page would park its
worker forever *holding the lock* — permanently refusing every later copy,
backup, restore and delete.

**Selection can be a bridge method, not just client state.** Selection that
changes only what the page draws stays on the page. Selection that changes
what Python computes crosses, because the computation is here — for
example `skills_select_plan`, `skills_select_group`, and
`eve_settings_select`, each rescoping what a later read returns, not a
closed list. The rule itself lives in `CLAUDE.md`; this is the pointer, not
a second copy of it.


## Saving

Fittings separates reading a fit from editing its metadata. The native
**Edit metadata…** disclosure starts closed; opening or closing it never saves
or discards a draft. Edited/pending/refused values survive list refreshes, with
focus and text selection restored only when that editor still owns focus.
A newer route, row or dialog must never have focus taken back by a refresh.
Save remains explicit, and disclosure state is session-only.

Fittings' neutral **Import from clipboard…** opens an inline EFT draft and
attempts a read only when text, review and result are all absent. Reopening a
retained draft or result preserves it; **Read clipboard** explicitly replaces
text, and clipboard refusal leaves manual paste available. Route entry never
reads the clipboard. **Review** shows normalized items and all line-specific
bay, loaded-ammo and offline-state warnings before the separate, local-only
**Add to library** action. Type-name lookup through ESI is disclosed beside
the draft. Editing text invalidates its review; list refreshes do not discard it.
A failed save retains the same review for Add retry while current and unexpired;
**Review again** also permits explicit recovery without editing the text.
Success keeps warnings visible and offers **Show fitting**, not automatic
selection or character copying. Per-detail EFT export uses saved metadata,
never an unsaved editor draft, and refuses unrepresentable saved content before
clipboard delivery. Clipboard controls stay neutral; **Copy selected** remains
the sole accent action.

Fittings' **Select page** selects only the currently displayed filtered page, not
hidden pages or the whole library. **Clear selection** and individual checkboxes
share that page-owned selection; existing filter/page/route pruning remains in
force. Selection-only changes repaint checkboxes and the Copy count, never the
metadata editor or a bridge read/write. Clearing from the focused helper returns
focus locally to Select page without scrolling; programmatic changes never take
focus from an editor. Copy selected remains the sole accent action.

Formation import separates parsing source text from validating edited candidates.
After successful Review, unchanged source cannot be parsed again and discard name
corrections. Changing the pasted text enables Review; a failed parse stays
retryable. Add formations validates the corrected names and changes the draft,
not the file. The creation preset is labelled and precedes New formation.

Settings has no page-wide Save button. Every field commits on its own through a
per-field endpoint returning `{applied, persisted, error}`.

**Saved layouts are explicit snapshot commands, not a Settings Save.** In
Previews → Windows → Placement, Save current as… and Update saved… capture primary
positions, sizes and Preview choices only. Ordinary edits save the working
arrangement, never the selected name. Selection is page-local, not an active
layout, and does not fetch or write. Apply confirms its recorded membership;
absent characters stay unchanged, and a null rectangle preserves geometry, not
the old Preview choice. Apply does not change global preferences, including the
reopen rule for later openings. Management remains usable with Previews Off;
Apply then saves for later without enabling previews.

**Wanderer's connection is a scoped grouped exception.** Its full map URL and
token form one bound credential, saved explicitly by **Test connection** or Enter
in either field; the nearby note states that Test saves. Python extracts the
server address and map identifier; the page never asks users for a slug. Existing
saved bindings render as one map URL without migrating settings on entry. It has no separate
Apply/Replace actions and no blur commit. The enable toggle remains independent.
A grouped acknowledgement still owns each field separately, so it cannot erase
a newer draft in another field. Configuration persistence and asynchronous Test
admission/result are separate facts. Remove confirms and clears the connection,
not the enabled preference.

Three outcomes, not two, because the page says something different for
each: **refused** (revert the control, explain inline), **applied but not
persisted** (leave the control, warn it will not survive a restart),
**done**.

**A rolled-back write is a refusal, not a session-only success.**
`settings.update()` restores the previous settings when persistence fails;
those endpoints must return `applied: false, persisted: false` and must not
run their dependent runtime effects. Reserve **applied but not persisted**
for an operation whose effect really remains active after the failed write.

**Revert to the last acknowledged submission, not a stale hydration value.**
Each field serializes its writes and tracks its accepted baseline separately
from newer drafts. A refusal restores that baseline only if the request
still owns the control; an older reply must not erase newer typing or a
queued submission. A successful retry retires its obsolete refusal without
erasing another field's error or replacing a newer draft warning.

**Discrete controls commit on change. Free text does not commit on blur.**
Folders and the webhook commit on Enter, or via an explicit affordance
(Browse, Detect, Remove). This is not fussiness:

- Committing a half-typed path that happens to name a real directory
  rebinds the watcher, and `Watcher.rebind` marks every file already in
  that folder as seen. The cost is specific, and smaller than this file
  used to claim: those recordings are not *announced* and arrive unticked,
  but they are still listed — `list_rows` rebuilds from the folder and only
  the watcher's poll result is preselected (`__main__.py:249-266`). A
  corrective commit does it again only for a genuinely different folder;
  `api.py:1743-1748` returns early when the path is unchanged, so
  re-committing the same path is a no-op, added for exactly this reason.
- An empty webhook used to mean "clear it", so select-all, Delete and look
  away destroyed a credential. **That hazard is retired, and the rule
  outlived it:** `api.py:1644-1648` refuses an empty value outright, so
  even a blur commit could not clear one, and removing a webhook is its own
  explicit action. The rule stands because the reasoning does — there is
  still no Cancel and no pre-edit snapshot anywhere on the page, so a free
  text field that commits on blur has no way back.

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

**A precondition is stated once, by the control that owns it — not by
every control it governs.** A master switch that gates a block of settings
gets ONE line saying what the block is waiting for, and the block is drawn
as subordinate to it: Alerts' labelled preferences region under
`#alert-enabled`, and `#preview-depends` for the nine under
`#preview-enabled` (`.pv-master` in `style.css` is the rule under the
switch that says so structurally).

Previews is the worked example because it got there the other way first.
Saying it per-control put the same sentence in seven blocks, each with its
own copy of the machinery to place it; round 3's R4 caught three of them
colliding in one view and shortened one, which fixed the view it was
looking at and left six. Turning the switch off then filled the card with
its own footnote. **The cost of a per-control note is not the note, it is
that nothing counts them.**

Two rules follow from that, and both are load-bearing:

- **Do not disable the block.** Recording a preference for later is an
  action that can be carried out, and disabling the only route to a
  control's own precondition is a dead end the reader cannot see the exit
  from (`ui/copy.py`). The line says it; the controls stay live.
- **Only one sentence may open with the state.** `ui/copy.py`'s
  `INERT_NOTES["previews_off"]` is that sentence for Previews. A second
  note in the same view says the consequence and the way out, and does not
  restate what the unticked box already shows.

**An empty hint costs no line.** A continuation row that exists only to
carry a `.hint` collapses while that hint contributes nothing — either
`:empty` (a status slot with no default text, blank until a write fails)
or `[hidden]` (a note the page raises only while its condition holds).
Both states matter: with `[hidden]` uncovered, the row stayed a 0-height
flex item and still spent its parent's gap, so a block's height moved with
the state of a switch inside it. Eleven rows across Bookmarks, Previews and
Alerts are governed by this.

**A live region is the exception.** `#alerts-health` and `#alerts-status`
are `role="status"` and keep their line, because a live region that is
`display: none` when its text lands may never be announced. The exclusion
is keyed on the role, not on the two ids, so a third live region is covered
without anyone remembering the rule exists.


**Readiness is not a preference.** Companion availability, Wanderer connection
and coverage, and custom-alert watching state use a stronger text role than
static help. Keep current readiness near its owning switch or heading, with
recovery beside it; enabled settings alone do not establish live operation.
Move the existing status node rather than creating a second live-region owner.
Expected Off or Waiting states are not errors merely because work is inactive.
Bookmarks puts its existing engine status beside Register keybinds in EVE;
only Running gets a pill. Both getter/save and push paths retain full error text
in that same polite live region, including an Off error. Quiet Off leaves that
owner exposed but empty; unchanged polls do not rewrite live text. Registration blockers
remain separate facts: a running engine does not prove keys are registered.
Fleet eligibility stays beside sharing status, outside its roster disclosure;
settled history hides obsolete Stop controls but retains their keyed identity if
pending work makes an attempt current again. Advanced alert Flashes and Speed
have separate local feedback and ordered per-field writes. Their replies and
hydration cannot replace newer choices or another field's refusal. Keep their
live regions mounted, including when empty.

Preview Copy sources describe geometry from the same current layout snapshot
that enumerates the source names, including undebounced retained host geometry
even while Off. Size-dialog defaults use committed layouts/configured defaults
and must not be presented as current Copy geometry. One `geometry_revision`
high-water mark accepts `onPreviewGeometry`, full getters and final layout
receipts; full hydration overlays the newest accepted geometry. Each fresh sample
advances the revision even when values match. It is ordered observation, not an
atomic settings/native snapshot. Named-operation receipts sample after native or
retained settlement and before releasing admission. Ordinary Size queue ACKs
never install requested dimensions: a delayed ACK cannot undo a later Apply, and
later settled Size/Copy/Reset can supersede Apply. Geometry-only delivery does not
replace keybind state or increment its push counter. Preserve drafts, scroll,
capture, owned focus and detached screenshot/live state. Older payloads without
geometry still identify the source without invented coordinates. This is read
evidence, not a guarantee that a user cannot move the source before pressing Copy.

Preview Copy alone opts into hiding a redundant selected-detail line when the
complete caption fits the closed selector. Truncated, clipped, unmeasurable and
legacy/null-geometry source details stay readable. Other compact choosers retain
their full-detail default. Observed placement in Configure uses that same current
geometry source, not Size defaults; geometry/actions and crop occupy a full-width
local grid, stacking at the floor without creating another scroll owner.

Bookmark overlap warnings show “Conflicts with a Bookmark keybind” and the
underlined Open Bookmarks action. Their same description node retains the full
owner/chord/consequence/recovery for accessibility. This warning treatment does
not replace local conflict precedence or genuine registration-error information.


## Routes and sections

**Task subpages are presentation, not a new section lifecycle.** Uploading has
YouTube, Recording and Combat logs tabs; Previews has Windows, Characters & cycling
and Wanderer names. Their static tab panels retain drafts, disclosure state and
scroll position while hidden. `WM.settingsTab(section, tab)` changes the selected
panel and dispatches `wm:settings-tab`, never `wm:section` or a settings read.
`WM.openSettingsSection(section, tab)` can target a subpage explicitly; ordinary
section entry retains the previous selection. Both obey the EVE-tools gate.

Tab lists use selected-state underlines, `aria-selected`, linked tab/panel IDs and
roving tabindex. Left/Right wrap; Home/End select the first/last tab. A tab change
moves focus out of the hidden panel, cancels Preview keybind capture and pending
detail-focus restoration, and masks a revealed webhook when leaving Combat logs.
It must not reset a draft or submit a field. The section header and preview master
switch stay outside the subpage scroller. Inside it, the character table and
Offline heading retain their stack, without the old scroll-jump navigation
offset. Wanderer's compact Map connection heading and name-availability status
stay visible while its form scrolls; the enable switch stays with its refusal
message in normal flow. Availability counts fresh projected names, not proof
that labels are visibly painted. Long recovery and Test outcomes stay with the
connection controls, outside the retained context visually. Both compact status
owners retain full detail as visually hidden content in their original live
regions; moving visual feedback must not reduce an announcement to just “Error”.
Expanded Companion rows retain their existing name and operational status on the
Settings scroller, releasing at that row's boundary. Enabled stays nearby with
its refusal; source details and full operation errors remain in normal flow.
Only Live and Waiting for source use pills. Add owns the accent until its form
opens, when Choose source takes it; both yield while source selection is active.
Expanded Fittings rows retain their existing identity above the detail and
release at that fitting's boundary. Keyboard reveal clears these local headers.

Windows uses native disclosures: Appearance and Placement start open; Size and
shape and When you switch away start closed. Each exception list stays with its
controlling preference. Related control units use two columns above 960px and
stack below; helpers stay beneath their owning controls, not at the far edge.
Cycle-group headings retain local identity within their panel boundary, after
the character table's separate opaque header/Offline stack. The group manager
never sticks; bounded name tracks keep Rename/Delete and member actions nearby.
Forward/Back share a row above 960px and stack below, preserving DOM tab order.
All group controls clear the measured local heading when focused, including
unconflicted binds and member actions. Pointer-down targets do not move before
activation; full heading height is reserved even while it releases at the panel end. The tabs and flat subpage treatment are scoped to these
two sections; other Settings screens keep their existing layout.

`WM.route` switches destinations; `WM.section` switches groups inside
Settings. Both dispatch an event, and both provide the same **enter and
leave** contract. Leaving Settings dispatches a section change too, so a
module folded into Settings learns about both.

Route and section entry is how screens **fetch**. There is no polling and
nothing is pushed at boot; a subsystem that costs nothing until you open it
must not push state at launch.

Update availability is application chrome, not General-section content.
Wingman therefore starts one background GitHub check after the page is ready
so the Settings gear can show availability before General opens. It does not
run inside `get_settings()`, block hydration, poll, download, or push before
readiness; General reads the cached state and offers an explicit retry.

**Fleet telemetry is configuration, not a destination.** Its compact overview
precedes Local display and External sharing. Each existing module paints only its
own accepted facts: local display preference, sharing preference/inhibition,
setup and last-observed authGD participation, and verification/eligibility.
Unknown is not Off, and a saved binding is not completed pairing: browser approval
can still be pending after its key is saved. No summary claims actual transmission
or native visibility. The original consent live region retains local/server facts
as visually hidden text; only their repeated standing sentence leaves visual flow.
Eligibility and actionable connection/recovery details remain beside sharing controls,
outside the eligible-character disclosure. Refresh belongs to the Connection header;
it does not add a local-roster read. Opaque, flat subsections keep shell artwork out
from behind operational text without making every fact another pill or card.

Section entry/exit changes only view watching, never sharing or source intent.
Deep links and remembered sections obey the EVE-tools gate and use the same
section notifications as the rail.

Account sources keep Current verification and Pending / local operation in
separate worklists above the new-attempt controls. All three lists share the
existing keyed row reconciliation; moving to Pending must retain its Stop control
and keyboard focus. A Start without a returned UUID stays character-specific
feedback in the original exposed action region. Only settled ended records enter
the quieter native Previous attempts disclosure; its count comes from rendered
history and its open state survives updates. Failed or stopped-only
setups still show reported reasons and a next action outside collapsed history.
There is no reliable terminal chronology: UUIDs and array order cannot identify
a latest attempt. Retained same-connection observations are labelled last-known
while current state is unknown, and discarded when the binding changes.

Leaving is load-bearing, not bookkeeping. `bookmarks.js` and `previews.js`
each install a document-level `keydown` listener while capturing a keybind,
and each disarms it on being left. `stopPropagation()` does not stop a
sibling listener already attached to the same node, so an armed capture
consumes the next keystroke typed anywhere and persists it into the wrong
bind, off-screen. The capture handler `preventDefault()`s every key
including Tab — an escaped capture inside Settings would swallow a folder
path or a webhook mid-type.


## Alerts operational hierarchy

The original mounted `alerts-health` owns the one standing operational sentence;
`alerts-status` still owns independent master/modifier write outcomes. Event Test,
volume, collision, pulse-field and custom-alert messages retain their own owners.
Health reads cannot erase those receipts. Preferences remain readable and editable
while Off inside “Preferences used when Alerts are on”, never visually disabled.
The no-events warning is configuration, not a second reader state; it accounts for
custom rules as well as built-ins. Advanced keeps a concise lead plus the distinction
between timed/Test/foreground pulses and persistent pulses on other clients.

Alerts reports Off, prerequisite waiting, Watching with the reported monitored names,
Watching gamelogs when a running reader has no names, or Not watching with its error.
These names identify selected log sources, **not the running-client roster**. Explicit
partial/complete coverage is unavailable and deliberately deferred: no X-of-Y, “all”
or “missing” character claims, and no backend or cross-subsystem roster join in this
presentation program. Custom-matcher degradation remains a separate fact.

## Character access and Profiles row actions

Character access presents four aligned columns: Character, Skills, Fittings and
Actions. Ready is the visible label for the existing authorized capability; Access
needed and Access expired remain separate facts. The authentication timestamp is
not a displayed column, but stays in the model and existing date searches. Both
Ready and legacy Authorized name/status/date searches remain supported. Header and
row tracks share padding; status and action centers align without compressing the
complete access phrases. Long names retain their full text and title.

The Character roster retains its internal scroller and opaque sticky header. Its
existing fixed menu clears the actual status strip rather than a guessed height.
Tab rejoins native traversal from the owning row; scroll or resize dismisses stale
geometry and returns only owned menu focus without scrolling or taking outside focus.
Authorization waiting, cancellation, read-failure retention and partial-cleanup
announcements are independent of these presentation changes.

Profiles retains one work scroller and its nonshrinking, normal-flow copy bar.
The existing selected-target count and source share a wrapping summary line, with
profile/server and scope context beneath; Copy settings follows that summary, with
the EVE advisory beside the action. At the floor the action row follows the summary.
The count still means selected, shown, non-source targets, exactly what Copy uses;
hidden selections remain retained. No second live summary is introduced. Long server
identities wrap within the existing folder row rather than widening the scroller.

Backup row actions reuse native details/summary, not a second ARIA menu system.
The visible ellipsis has a row-specific accessible identity and timestamp; native
expanded state and Tab behavior remain intact. Delete stays inside the disclosure,
Restore stays neutral, and both retain their existing worker confirmations. A
measured route/status-strip boundary chooses the popup side for any visible row,
not only the final DOM row. Escape returns focus; geometry dismissal returns it
only if that disclosure still owns it, without undoing scroll or stealing focus.
Backup ordering, filtering, retention and filesystem behavior are unchanged.

## Formation and setup import stages

Probe selection is transient page state, not formation data or EVE's selected
formation ID. No probe is initially selected. Row/field interaction selects its
original ordinal, which still labels the depth-sorted diagram marker. A dashed
row boundary and outlined, bold-numbered marker distinguish selection from the
field's solid keyboard focus ring. Rows are labelled groups, not an ARIA grid;
the diagram remains a noninteractive image and keeps its rotation behavior.
Selection survives ordinary repaint, but never moves to a replacement probe or
another formation, import candidate, account document or route lifetime.

Save and Balance explain their actual local disabled predicates. Clean drafts,
loading, saving and missing read revisions are not errors. Existing validation
and operation errors retain their complete text and original status owners.
Launches as drawn is neutral guidance beside Balance; closing every EVE client
is a standing Save prerequisite, not inferred live readiness. Save, Balance and
Add hand self-disabling keyboard focus to their mounted outcome/note owner without
scrolling, whether the browser blurs immediately or at its next rendering update.
Only still-owned completion focus may advance to the added formation; a newer
control, candidate, formation, route or dialog takes precedence. Selected-probe
system colors are decided by narrow forced-mode tokens at `:root`, never component literals.

Formation import separates source parsing (Review), candidate diagram selection
(Preview), local draft addition (Add formations), and the later explicit Save.
Successful Review subordinates retained source text and removes the competing
parse action. Actual source edits invalidate that review; merely reopening source
does not discard corrected names. Candidate conflicts remain associated with
name fields, and Add validates the corrected candidates rather than reparsing
unchanged source. Its destination names the acknowledged account's local draft,
never a profile identity the editor does not receive.

Setup import keeps source entry and completed review visually distinct. A valid
review collapses the retained source/recipient controls, including an eligible
ship-label correction and its instruction. Edit reveals the retained policy only
for the source that required it, without changing review validity until actual
input changes. Review hands self-disabling focus to the existing status while
pending and advances to reviewed context only while focus is still owned.
A summary without an accepted
review ID is not authorization and must keep corrections reachable. The final
action context names the proposed new profile and recipient character/account/base.
Non-overwrite and cancellation safety remain visible, with the original complete
review announcement retained in its existing live owner. After Create is sent,
Back is not cancellation; its detached receipt still owns completion. Source and
review stay private to the existing route lifetime. Setup sharing is independent
and retains its accepted presentation and snapshot semantics.

Both tools retain their existing work scrollers and normal-flow action siblings.
Responsive wrapping must not turn previous-stage fields into clipped fragments,
strand hidden focus, or cover controls with a second fixed or sticky surface.

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

Same rule pointed the other way: name a control for its effect, not for
the user's next move. `Clear`, `Restore`, `Detect`, `Refresh`, `Edit…`.
`Type…` was the one control *name* in the app that was an instruction, and
it sat beside `Clear` in the same treatment, so the pair read as two
options rather than as a value-clearer and an editor.

A trailing `…` on a control name means *this opens something* — `Browse…`,
`Change…`, `Choose folder…`, `Edit…`. It is not decoration, and a control
that opens nothing may not wear one.

Both rules are about the name a control *rests* at. A transient state
label may be an instruction and may trail an ellipsis, because that is what
it is for: an armed `.bindbtn` reads `Press a key…` for as long as the
capture is live, and the ellipsis there means *waiting*, not *opens*.


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
Enabled empty checkbox/radio outlines are selection affordances, not decorative
panel borders: their `--control-edge` must also clear 3:1 against adjacent
surfaces. `test_ui_contrast.py` checks field, panel, row and control fills.
Disabled/inert controls retain their separate dimmed treatment.

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

That column's successor, `Age`, *is* right-aligned — in the cell and in
the header together, sharing `.c-size`'s rule and its `order: -1` arrow
treatment. That is the finding's actual rule being followed (a header is
anchored like its column), not the finding reproducing: what Uploader 4
alleged was a header anchored *opposite* its data.

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
