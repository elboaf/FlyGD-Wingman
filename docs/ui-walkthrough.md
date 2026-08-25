# UI walkthrough — FlyGD Wingman, live, one route at a time

A conversation held over screenshots of the real WebView2 window, after
PRs #38, #39 and lanes 0-5 landed. `docs/ui-critique.md` was a
source-level pass; this one exists because reading CSS cannot tell you
where the eye lands, whether 320px beside a list feels right, or whether
a screen full of real data looks like the same app as its empty state.

Register is `product` (`PRODUCT.md`). `PRODUCT.md` and `DESIGN.md` outrank
generic design law wherever they disagree.

**Not re-reported:** everything closed in `docs/ui-critique.md`, PRs #38
and #39, lanes 0-5, anything `tests/test_page_conventions.py` enforces,
the status strip's SIG/ROOT/NEXT on every route, and the `gesture` /
`alert_bookmarks` identifiers.

Each finding is marked `sure` or `worth trying`, and tagged `screen-local`
or `shared`. **Shared** means `style.css` above the "recording list"
banner, `app.js`, `panel.js`'s status-strip and dialog halves, the
titlebar, `#statusbar-slot`, `#dialog-slot`, or `ui/api.py` — the tag is
what lets follow-up work split across parallel sessions.

---

## Uploader — `#route-main`

**Looked at:** a real watched folder, 25 recordings, no webhook configured,
nothing selected, normal window width. (Still to see: the window floor,
the empty folder, and a live upload.)

**How the maintainer actually uses it:** one clip per fleet, with logs. A
title and description typed every time; the file is never renamed. This is
the destination visited regularly — previews and bookmarks are configured
once and left. So the panel, not the list, is the half touched on every
visit, and the list's job is to pick exactly one row.

### 1. The loudest element on the screen is the one that cannot act — `sure`, `screen-local`

`Upload` is full-strength accent with a glow, and it is the first thing
the eye lands on. With nothing selected it has nothing to do. The state
that blocks it is stated as dim body text at the foot of the card *above*
it ("Nothing selected"), 200px away and in the weakest type on the panel.

The blocked action shouts and the blocker whispers. Either the button
takes a disabled treatment when the selection is empty, or the selection
count moves next to it. `DESIGN.md` spends the screen's one accent here;
spending it on an inoperable control is the part that is wrong, not the
choice of control.

*Open:* does the button no-op or raise something when pressed empty? Not
answerable from a still.

### 2. The card headed UPLOAD does not contain the Upload button — `sure`, `screen-local`

Two cards: `UPLOAD` (title, description, two checkboxes, selection count)
and `PUBLISH` (the `Upload` button, `Delete selected`). One concept, two
names, on one screen — `DESIGN.md`, "One name per concept, across every
screen."

Two further seams in the same place:

- The route is `Uploader` and its first card heading is `UPLOAD`.
  `DESIGN.md`: "A screen may not repeat its own tab name as its first card
  heading." Lane 2 fixed this for Settings; the Uploader still does it.
- `Delete selected` is a local file deletion filed under `PUBLISH`.

### 3. Column headers sit ~16px right of their data — `sure`, `screen-local`

The header row is outside the scroll container, so it is not offset by the
scrollbar gutter. Confirmed by crop: `Size` is right-aligned and
`108.8 MB` is right-aligned, and the header hangs ~16px right of the
number. It reads as a mistake rather than as a style, on every column, on
every visit.

### 4. `Modified` is a right-aligned header over a left-aligned column — `sure`, `screen-local`

"Modified" floats above the right end of "yesterday". Every other
header/data pair in the table shares an alignment. This one does not.
Separate defect from 3 and separately fixable.

### 5. `Length` and `Link` are empty on all 25 rows — `sure` that they are empty, cause open, `screen-local`

`Link` empty is expected before an upload. `Length` blank for every row is
not obviously expected, and two of six columns carrying nothing is
expensive in a pane that a whole PR (#47) was spent keeping columns inside.

*Needs an answer:* does `Length` ever populate?

### 6. `Filename` and `Modified` are the same fact printed twice — `worth trying`, `screen-local`

`Fight 2026-08-24 17-57-37.mkv` beside `5h ago`. The widest column in the
app and a dedicated column carry one timestamp. Worse for scanning: the
distinguishing characters sit mid-string between a constant prefix and a
constant extension, so 25 rows read as one repeated string and the eye has
to parse into the middle of each.

*Needs an answer:* is the date-in-filename OBS's default template? If so
this is true for every user, and the lever is what the Filename column
renders, not what OBS writes.

### 7. Two checkboxes sit in the approach corridor to the primary button — `sure`, `screen-local`

`Stitch selected into one video` and `Also post combat logs to Discord`
are between the panel's content and `Upload`. The maintainer reports
hitting one of them while reaching for `Upload`. `Stitch` is the larger
and higher target and mis-firing it changes *what gets uploaded*, not just
what gets posted afterwards.

### 8. The combat-log checkbox has no true second state, for this user — `sure` as a use report, `shared`

> "I think the checkbox is not needed, there is no scenario where I don't
> want to upload logs also." — and, on probing, only fights are ever
> uploaded.

Lane 1's fix has landed and is visible: the box is disabled and carries
"No Discord webhook is configured, so logs would be skipped. Set one in
Settings › Discord." The maintainer asked for exactly that behaviour
*while looking at a build that has it*, which suggests the sentence is not
being read — it currently reads as a footnote to a control rather than as
a fact about the install.

That argues for the sentence outliving the checkbox: post logs whenever a
webhook exists, and state the no-webhook case as a fact on the panel.

`PRODUCT.md` supports an opinionated default — "The bookmark workflow
encodes one group's conventions and does not have to be neutral about
them" — and a fork's "logs off" belongs in `settings.py`, not one click
from `Upload`. `shared` because the confirm line lives in `ui/copy.py` and
the gate is `ui/api.py`.

**Disagreement to record:** none yet. The nearest thing is that removing a
control is the one edit a fork cannot undo without re-adding it, which is
why the default's home matters more than the checkbox's fate.

### 9. At the documented minimum height the primary button is below the fold — `sure`, `screen-local`

Seen in two separate captures: the right column takes its own scrollbar
and `Upload` is clipped by the bottom of the pane, showing about 15px of
accent and no label. It was fully visible in a taller window, so this is
**height**, not width — and the documented floor is 840x**625** physical.

The fixed vertical cost stacked above it: Title, a ~170px Description box,
two checkboxes that wrap to two lines each at narrow widths, a three-line
webhook explanation, a selection summary, then a second card with a
heading and a line of prose. The most-pressed control in the app is last
in that stack.

`#47` was scoped to width. Nothing was wrong with that; the height case
simply was not in it.

### 10. `Length` is not blank, it is zero — `sure`, likely a regression, `screen-local`

With one row selected the summary reads
`1 selected · 108.8 MB · 0:00:00`. The duration is not missing, it is
computed as zero and stated with confidence about a 108.8 MB recording. A
blank cell says "unknown"; `0:00:00` says "zero seconds". Maintainer
recalls it working previously — treat as regression, not as an
unimplemented column. Supersedes finding 5's "empty".

### 11. The Filename column truncates away the only part that identifies the row — `sure`, `screen-local`

Upgrades finding 6 from `worth trying`. At the narrow width rows render as
`Fight 2026-08-24 17-57-…` and `Fight 2026-08-21 18-35-1…`: the ellipsis
eats the seconds, inconsistently, and one row keeps a stray digit. So the
column that is truncated is the one carrying the identity, while
`Modified` — carrying the same timestamp in a friendlier form — is intact
beside it. Confirmed with the maintainer that the date-in-filename is
OBS's default template, so this holds for every user, not just this one.

`#47` kept all six columns at the floor, which was its job and which it
did. This is what became visible once they all fitted.

### 12. The empty state names the wrong folder — `sure` as an observation, cause unconfirmed, `shared`

`No recordings in D:\Videos`, where `D:\Videos` is the folder that *does*
have the recordings; the configured-and-empty folder is elsewhere. The
critique asked the empty state to name the folder (Uploader 4) and it now
names *a* folder, confidently and wrongly. The next line — "Open folder
below to check it" — would open the wrong one.

Working hypothesis, not verified: the list renders a stale `wm:settings`
payload and nothing re-pushes when the folder changes. Tagged `shared`
because if that is the cause the lever is the push, not the sentence.

### 13. The panel does not know the list is empty — `sure`, `screen-local`

With zero recordings the right column is unchanged: live Title field,
Description box, both checkboxes, full-strength accent `Upload`. So the
empty and full states read as the *same* product in the wrong direction —
nothing on the right acknowledges there is nothing to act on. Combined
with finding 1, the accent button is inoperable in two different states
and dressed identically in both.

### 14. The empty pane is half-centred — `worth trying`, `screen-local`

The message is centred horizontally and top-aligned vertically, leaving
roughly 750px of empty pane beneath it, with the column headers still up
labelling nothing. It reads as neither deliberate placement nor natural
flow. Also: `0 recordings`, `Nothing selected` and `No recordings in …`
are three statements of the same emptiness in one view.

### 15. Two adjacent checkboxes are too close to distinguish by aim — `sure`, `screen-local`

Revises finding 7. The maintainer's mis-click was **not** a control caught
on the way to `Upload`:

> "I hit logs, but meant to hit stitch."

So it is two similar targets adjacent to each other, and at narrow widths
both labels wrap to two lines, which brings the rows closer together
rather than further apart. `Stitch selected into one video` and `Also post
combat logs to Discord` are unrelated concerns sharing a visual treatment
and a neighbourhood.

This also revises the framing of the whole screen: **stitching is a
control the maintainer uses**, so multi-select is doing real work and the
list is not merely a one-of-25 picker. Finding 8's "no scenario without
logs" stands; "this is a one-clip workflow" does not.

### 16. Accent is spent in five places, two of them decorative — `worth trying`, `shared`

In the selected-row capture the brand accent appears on: the checked row's
checkbox, that row's left edge marker, the `UPLOAD` card heading bar, the
`PUBLISH` card heading bar, and the `Upload` button. `DESIGN.md`'s rule is
written about controls (".btn.acc is the single brand-accent control"), so
the heading bars do not breach its letter.

They do compete with the two places accent is load-bearing — *what is
selected* and *what will happen* — and they mark cards rather than
actions. Tagged `shared` because the heading-bar treatment is not confined
to this screen.

### 17. The panel's vertical order does not match its frequency of use — `worth trying`, `screen-local`

Confirmed with the maintainer: stitching is **occasional**, one clip is
the norm. So the fixed stack above `Upload` reads, top to bottom:

| | used |
|---|---|
| Title | every upload |
| Description | every upload |
| Stitch selected into one video | occasionally |
| Also post combat logs to Discord | never varies (finding 8) |
| webhook explanation (3 lines) | never acted on from here |
| selection summary | read, not touched |
| `PUBLISH` heading + "Channel confirmed…" | never acted on |
| **Upload** | **every upload** |

The two always-used fields are correctly at the top. Everything between
them and the button is occasional, invariant, or prose — and it is exactly
that block which pushes `Upload` off-screen at the documented minimum
height.

`Stitch` has a natural disclosure condition already on the screen: it is
meaningless with 0 or 1 rows selected, and the panel already knows the
count (it prints it). Revealing it only when the selection is greater than
one would, in one change, reclaim height for finding 9, remove one of the
two confusable targets in finding 15, and stop the empty state offering a
batch operation over an empty list (finding 13).

Noted as one change rather than three because whoever takes it should know
they are the same lever.

---

## Profiles — `#route-evesettings`

**Looked at:** no folder chosen; a real EVE root with ~35 characters, top
of list; the same scrolled to the button and the Backups card.

**How the maintainer actually uses it:** "almost always it's that I want
to resync my accounts with a change I've made on one." `Characters` mode
nearly always, `Accounts` rarely but genuinely needed. **`Select all`
almost every time.** Backups have been restored, but very rarely.

Lane 3 delivered: the folder card is collapsed to one summary line
(critique Profiles 1), the mode switch is labelled `Copy` (Profiles 2),
and the Backups card now states the keep-10 policy in prose (Profiles 5).

### 1. At the moment of the irreversible action, the hazard warning is off-screen — `sure`, `screen-local`

The `EVE running` pill lives in the folder card at the top of the page.
`Copy to selected` sits at the bottom of the second card, past a nested
scroller. In the scrolled capture the button is on screen and the pill is
**not** — the folder card has left the viewport entirely.

The critique raised this (Profiles 3) as "the pill is advisory and the
dialog is modal; the warning is on the wrong one", marked `needs the
running app`. Confirmed, and stronger than stated: it is not merely the
wrong element, it is an element that is not visible at the moment of
commit.

### 2. The list is a picking surface used as a verification surface — `sure`, `screen-local`

The maintainer selects all almost every time. So the tallest element on
the screen, with its own scrollbar, exists to serve the interaction it
almost never receives. What is actually wanted at that moment is to *see
who is about to be overwritten* — which needs everything visible at once,
and currently needs scrolling instead.

Consequences visible in the captures:

- ~35 names in a ~250px column inside a ~1180px card. Roughly 900px of
  dead card to the right of every row. Three columns would show the whole
  roster with no inner scroll.
- Two nested scrollbars — the list's own and the page's.
- The inner list clips mid-row at **both** edges: `Suartad Arsten` cut in
  half at the top, `Yas Kalkoken` cut at the bottom with `Copy to
  selected` immediately beneath the cut. A half-legible name against a
  full-strength accent button reads as a collision even where it is only a
  scroll boundary.

### 3. The number of characters about to be overwritten appears nowhere before the modal — `sure`, `shared`

There is no selection count on the screen. The Uploader prints
`1 selected · 108.8 MB · 0:00:00`; this screen prints nothing. Combined
with `Select all` being the normal path, the user's only quantity is the
one in the confirmation — which the critique records (Profiles 3) as
counting "file(s)" at a user who ticked character names. `shared` because
the count belongs beside the button on the page *and* the dialog string
lives in `ui/copy.py`.

### 4. No `Detect` for the EVE settings folder, in an app that detects OBS's twice — `sure`, `shared`

Maintainer's own finding, and it holds. `Detect` exists in Settings ›
Folders **and** on the first-run screen, for a folder that is shallower
and better known than this one. The EVE settings root gets `Choose
folder…` only.

`PRODUCT.md` settles it rather than leaving it to taste: *"assume fluency.
Do not explain EVE. Do explain Wingman — where a folder is."* Where a
folder is, is named as Wingman's job. And the app already derives
`Tranquility · Default` from the chosen root, so it understands the
structure well enough to find it.

`shared` — a new bridge method on `ui/api.py`, alongside the existing OBS
detector.

### 5. The empty state answers a question that cannot be asked yet — `sure`, `screen-local`

With no folder chosen the target list reads *"No other characters in this
profile."* There is no profile. It reports a downstream condition rather
than the blocking one, which is the same shape as the Uploader's empty
state (finding 12) and worth fixing with the same instinct: name the thing
that is actually stopping you.

### 6. Two empty dropdowns render identically to working ones — `worth trying`, `screen-local`

`Server` and `Profile` are blank, un-placeholdered and undimmed before a
folder exists. They read as broken rather than as not-yet-applicable.

### 7. `Change…` is the only control on its row and the quietest thing on it — `worth trying`, `screen-local`

The row reads: a mono boxed path that looks interactive and is not, dim
plain text (`Tranquility · Default`), then `Change…` — link-styled,
borderless, and no more prominent than the static text beside it. The one
control is the least control-like element present.

### 8. The screen is named Profiles; its cards are named Settings — `worth trying`, `screen-local`

`SETTINGS FOLDER` and `COPY SETTINGS`. `DESIGN.md` renamed the tab away
from "EVE Settings" because *"a tab named 'EVE Settings' beside a gear
named 'Settings' describes the implementation and confuses the reader"*.
The tab moved and the cards kept the word, so the gear's name still
appears twice inside the screen that was renamed to avoid it.

### 9. `.btn.acc` has no disabled state, on two screens — `sure`, `shared`

`Copy to selected` is full-strength accent with nothing ticked, no folder
chosen, and "No other characters in this profile" printed above it. This
is the same behaviour as the Uploader's `Upload` (finding 1) in the same
release, which promotes it from screen-local to shared: either the accent
button has no disabled treatment, or it is not being applied at either
site.

Both instances guard consequential actions — one uploads, one overwrites
irreversibly — so the cost of the missing state is not cosmetic.

### Decision needed, not a finding — profile management

> "The thing that I would like to do, but we don't have functionality for,
> is create a new profile folder and copy all existing settings — or
> select which profile folder to use, and do the same copy to alts."

The screen already **reads** the profile dimension (`Profile` dropdown,
and everything is scoped to "this profile") and offers no way to **write**
it: no create, no clone, no copy-between-profiles. The dropdown implies a
management surface that does not exist.

Recorded as unmade rather than as a defect. When it is taken up:
Profiles is already a destination under `PRODUCT.md`'s test, so this grows
an existing destination rather than adding a peer — the cheap direction,
and the title bar does not have to be re-argued.

---

## Skills — `#route-skills`

**Looked at:** one character, one plan, everything ready; then two
characters, eight plans, a not-ready character expanded over 36
requirements.

**How the maintainer actually uses it:** "trying to see which characters
can fly a given ship, or to see what I need to train next on a given set
of characters." **Has never used the `Filter characters` box.**

Lane 4 delivered: the rail's ratio now sits under a `READY` column header
so it no longer reads as the header's requirement count (critique Skills
1), and `What is a plan?` is present as a disclosure (Skills 5).

### 1. `Unknown skill` reads as an app failure and means a fact about the character — `sure`, `screen-local`

> **Corrected after the maintainer's answer. See Corrections, C2.** The
> original entry treated the string as an unresolved-lookup error. It is
> not. What follows is the rewritten finding.

Of 24 visible rows, ~17 read `Unknown skill` and 6 read `Missing`. Neither
of the maintainer's two questions can be answered in that state: not *who
can fly this*, not *what do I train next*.

Cause is not determinable from a capture — unresolved plan-file names, a
lookup that is not finding its data, or an unauthenticated character are
all consistent with it. The UI finding stands regardless: **the string
appears 17 times and nothing on the screen says what it means or what
would fix it.** `PRODUCT.md` names this obligation directly — explain
Wingman, "why a keybind did not register" being its own example.

*Needs an answer:* is this normal on a real install, or an artefact of the
sandboxed instance?

### 2. `Unknown` means two different things in one glance — `sure`, `screen-local`

Group header: `Unknown skills 2` — two **characters** of unknown status.
Rows: `Unknown skill` — a **skill name** that could not be resolved. One
directly above the other.

With finding 3 below, this screen's problem is vocabulary rather than
layout.

### 3. `Ready` carries four meanings, one of which is the app's idle state — `sure`, `shared`

In a single view: the rail column header `READY`; the group header
`Ready 1`; the per-character pill `Ready`; and the status bar's `Ready`,
which is the application being idle and has nothing to do with skills.

`PRODUCT.md`: one name per concept. This is one name over four concepts,
two of them visible simultaneously. `shared` because the status strip is
lane 0 territory and the collision is only visible from this route.

### 4. `2 characters · 0 ready` is contradicted four rows below it — `sure`, `screen-local`

The rail's top line is scoped to the **selected plan**; the rail's ratios
are per plan. Both are true and the top line does not say so. It sits
above `Add character`, detached from the plan list, where it reads as a
roster statement — and `Core Ship Skills 2/2`, four rows down, makes the
naive reading visibly wrong.

Lane 4 fixed the two-numbers problem at the rail and the header. This is a
third number with the original disease.

### 5. Outstanding requirements are not ordered by state — `sure`, `screen-local`

> **Corrected. See Corrections, C3.** The original entry claimed the list
> mixed met and unmet requirements. It does not; met ones are already
> filtered out.

Not alphabetical, not grouped by status, not by anything visible. The
`Missing` rows — the only actionable ones — fall at positions 5, 12, 15,
17, 23 and 24. Answering "what do I train next" means scanning the whole
list picking red out of grey.

Sorting outstanding to the top answers the maintainer's stated question
without adding a control.

*Needs an answer:* the critique credited this screen with "filtering
outstanding requirements only". No such control is visible here — removed,
below the fold, or state-dependent?

### 6. A ~1000px void between each row's subject and its answer — `sure`, `screen-local`

Skill name ends around x=870; its status is right-aligned near x=1900.
Repeated for all 36 rows, and for the character rows above them. The
screen exists to associate a name with a state, and it places them at
opposite ends of a very wide line with nothing between.

Visible with one character; the dominant texture of the screen with a real
plan.

### 7. Column header rows do not share the inset of the rows they label — `sure`, `shared`

`PLANS` sits ~22px left of `Babaroga`; `READY` sits ~14px right of `0/2`.
Confirmed by crop.

This is the same defect as Uploader finding 3, and this instance has **no
scrollbar**, which rules out the gutter explanation there too: header rows
and data rows simply do not share padding. Two screens, one cause —
`shared`.

### 8. Two time vocabularies in one app — `worth trying`, `shared`

Skills renders `Last fetched 8/25/2026, 12:12:28 AM`; the Uploader renders
`5h ago`. Same class of fact, two formats, and the Skills one carries
seconds precision on a value where seconds cannot matter.

### 9. The never-used control is the second most prominent thing on the screen — `worth trying`, `screen-local`

`Filter characters` is full-width, directly beneath the heading, above the
data. The maintainer has never used it. Same disclosure question as the
Uploader's `Stitch` (finding 17): it has a natural condition — a roster
large enough to need filtering — and the screen already knows the count.

### Not reported, deliberately

The `impeccable` skill bans em dashes in UI copy ("Nothing outstanding —
every requirement is trained and active."). `PRODUCT.md`'s tone section
does not, the repository uses them throughout, and override 1 puts the
project's documents above the skill's generic laws. Recording the
non-finding so the next pass does not raise it as new.

---

## Settings — `#route-settings`

**Looked at:** the `Bookmarks` and `Previews` sections at a wide window.
(Still to see: `Account`, `Uploads`, `Notifications`, `Folders`,
`Discord`, `General`, and any section at the window floor.)

**What is working, and should not be undone.** Lane 2's fix for critique
Settings 4 is the best writing in the app. `EVE-FOCUSED KEYBINDS` and
`GLOBAL KEYBINDS` are now distinct headings, and *each card names the
other and gives its path* — "Previews have a second set, registered
globally rather than only in EVE — Settings > Previews" and "Bookmarks
have a second set that fires only in EVE — Settings > Bookmarks. A keybind
the two share is marked below." The collision that `previews.js:22-31`
detects is now legible from either side. The rail order also changed:
`General` is last, so critique Settings 2's landing complaint is addressed.

### 1. "Precondition not met" is rendered two opposite ways in one release — `sure`, `shared`

- **Uploader**: no webhook, so `Also post combat logs to Discord` is
  **disabled and greyed**, with a sentence explaining why.
- **Settings › Previews**: previews are off, so every keybind below is
  inert — and `Cycle forward`, `Cycle back`, `Clear`, `Type…` and the
  `Position` checkbox are all **fully live**, with a sentence explaining
  why ("Previews are off, so every keybind below is unregistered until you
  turn them back on").

Same situation, same release, opposite answers. One of the two is wrong
and it does not matter much which — what matters is that a user cannot
learn the rule. `shared` because the answer belongs in the control
vocabulary, not in either screen.

### 2. The only accent on the Previews section marks a sub-option of a switched-off feature — `sure`, `screen-local`

`Enable — Show live previews of running EVE clients` is **unchecked**.
`Position — Reopen previews where you last put them` is **checked**, and
its checked box is the sole accent-coloured element on the screen.

So the one thing the eye is pulled to is a preference that currently does
nothing, sitting below the switch that turned it off. `DESIGN.md` reserves
the accent for the one thing claiming primacy; here it claims it for the
least consequential control present.

### 3. Hint text aligns to the checkbox, not to the sentence it explains — `sure`, `shared`

Confirmed by crop. Under `Show live previews of running EVE clients`, the
hint's left edge sits on the **checkbox's** left edge — about 48px left of
the label text it belongs to. It is technically aligned to a real element
and reads as a mis-indent, because the thing it explains is the sentence,
not the box.

This is the `.settings` hint rule rather than one screen's markup, so it
recurs wherever a hint follows a checkbox.

### 4. Inside one card, the prose and the control rows have different left edges — `sure`, `screen-local`

In `GLOBAL KEYBINDS` the explanatory paragraphs start at roughly x=848
while `Cycle forward` and `Cycle back` start at roughly x=597 — the prose
hangs about 250px right of the rows beneath it, with nothing in the gap.

### 5. Durable explanation and current state share one undifferentiated block — `worth trying`, `screen-local`

`GLOBAL KEYBINDS` opens with two paragraphs in identical type: the first
is permanent (what global keybinds are, where the other set lives), the
second is a live state message ("Previews are off, so every keybind below
is unregistered"). The one that changes looks exactly like the one that
never does.

### 6. The label column plus the checkbox label reads as a broken sentence — `worth trying`, `shared`

`Enable` + `Register keybinds in EVE`. `Position` + `Reopen previews where
you last put them`. `Enable` + `Show live previews of running EVE
clients`. The shared 118px label column is right for fields; against a
checkbox whose own label already carries the verb, it produces a stutter.

### 7. On the Bookmarks section the distinguishing word is never first — `worth trying`, `screen-local`

Card headings scan as `EVE BOOKMARKS`, `EVE WINDOWS`, `EVE-FOCUSED
KEYBINDS`. The client list scans as `EVE - Aiga Otsolen`, `EVE - Guarzo
Opper`, `EVE - Gustav Oswaldo`… Every line begins with the word shared by
every line, and the part that distinguishes it is downstream of the eye's
landing point.

Same shape as Uploader finding 11 (`Fight ` prefixing every filename).
Noted together because the instinct is one instinct.

### 8. `Not running` restates the unchecked box above it — `worth trying`, `screen-local`

`Register keybinds in EVE` is unchecked and, below it, `Not running`. Two
renderings of one fact, the second unlabelled and dim.

### 9. `Import from an existing helper…` does not say what a helper is — `sure`, `screen-local`

The button assumes knowledge of some other application. `PRODUCT.md`
draws the line precisely here: assume fluency in EVE, explain Wingman. A
prior third-party tool whose binds can be imported is Wingman's context,
not EVE's.

### 10. Card density disagrees within one section — `worth trying`, `screen-local`

`EVE BOOKMARKS` spends roughly 280px on three sparse rows; the keybind
rows below run dense and repeat eighteen times. The page moves from airy
to tabular with no transition.

### 11. ~600px between a keybind's action name and its binding, eighteen times — `sure`, `shared`

`Grab Sig ID` sits at x=593; `Not set` sits at x=1230. The same void as
Skills finding 6, and for the same reason: a row associates a name with a
value and places them at opposite ends of a very wide line.

`shared` with Skills because the two screens are now two instances of one
unaddressed question — what a full-width row should do with its width.

---

### Settings, remaining sections — `Account`, `Uploads`, `Notifications`, `Folders`, `Discord`, `General`

All at a wide window. The narrow case is still unseen and is where critique
Settings 1 lives.

**More that is working.** `Uploads` now reads `YouTube category` with a
hint that explains rather than dropping a magic number (critique Settings
3). `Folders` and `Discord` have headings that say what the section does
(`WHERE YOUR RECORDINGS AND GAMELOGS LIVE`, `WHERE COMBAT LOGS ARE
POSTED`) rather than echoing the rail (critique Settings 4). `General` is
last in the rail and its prose names all four EVE features.

### 12. Control rows start at three different left edges depending on the section — `sure`, `shared`

Flipping through the rail moves the content sideways:

| section | first control begins |
|---|---|
| `Folders`, `Discord`, `Uploads`, `Account` | ~x=860 (after the label column) |
| `Bookmarks`, `Previews` | ~x=860 (label column word + checkbox) |
| `Notifications`, `General` | ~x=600 (card's left padding, no label column) |

A ~255px jump, triggered by clicking a rail item. Each section is
internally consistent, which is why this is invisible from any single
capture and obvious when switching.

### 13. The `YouTube category` hint is doing a control's job — `worth trying`, `shared`

The new copy is good: "YouTube files every video under one of its own
numbered categories. 20 is Gaming, which is where fight footage belongs —
leave it unless you know you want a different one."

It is three lines instructing the user **not to use the control**, on a
field whose correct value the app already knows and prints. The critique's
Settings 3 had two halves — the words and the `<select>` — and lane 2 took
the words. A field whose best documentation is "leave it" is a candidate
for not being a field.

`shared` — `set_category` validates a free string in `ui/api.py`.

### 14. `Show` and `Remove` are live on an unconfigured webhook — `sure`, `shared`

Third instance of finding 9 / Settings 1: `Discord` has an empty field,
`not configured` beneath it, and both buttons at full strength. `Show`
reveals nothing; `Remove` removes nothing.

Three screens now (Uploader, Profiles, Settings › Discord) with the same
gap, across primary and secondary buttons, which settles it as a control
vocabulary problem rather than three oversights.

### 15. `not configured` is the only lower-case status string in the app — `worth trying`, `screen-local`

Against `Not running` (Bookmarks), `Nothing selected` (Uploader), `No
backups yet.` (Profiles), `Not connected` (Account). One of the five is
lower-case and unpunctuated.

### 16. The `EVE gamelogs` path is silently cut mid-word at a comfortable width — `sure`, `screen-local`

`C:\Users\tng\Documents\EVE\logs\Gamelo` — no ellipsis, no wrap, and this
is a wide window, not the floor. The value cannot be verified by eye at
any width the app offers, which matters for a field whose whole purpose is
naming a location the user must confirm.

### 17. Status indicators use three different shapes — `worth trying`, `shared`

Pill with a dot (`● Not connected`, Account), plain pill (`EVE running`,
Profiles), square swatch (green/grey group markers, Skills). Three
vocabularies for one concept.

### 18. The YouTube terms link is the only blue in the application — `worth trying`, `shared`

`https://www.youtube.com/t/terms` renders in a link blue that appears
nowhere else in a palette otherwise built from near-black, red, amber and
green. It is also the only raw URL shown as its own text.

`DESIGN.md`: "Tokens live in `:root` and are the only place a colour is
decided." Worth checking whether this blue is a token at all.

### 19. `Import from an existing helper…` is a dead control in a primary position — upgraded to `sure`, `screen-local`

> "No one uses import from an existing helper."

Supersedes finding 9 above. It is not only unexplained, it is unused —
and it holds the only button position in the first card of the `Bookmarks`
section, directly under the feature's enable switch. Removal or demotion
is a smaller change than explaining it.

### Still open, already deferred — `Notifications` has no third option

Two radios, no way to have neither, exactly as `docs/ui-work-lanes.md`
recorded when it deferred this pending a product decision. Not re-reported
as new; recorded because the decision is still unmade and
`PRODUCT.md`'s "beside a game, often mid-fleet, on a second monitor"
argues for it more strongly than the critique did.

### Corroboration for Uploader finding 12

`Folders` shows `Recordings: D:\Videos` — the same path the Uploader's
empty state named while claiming it held no recordings. The maintainer
reports that at capture time the *configured* folder was a different,
empty one. That is consistent with the stale-payload hypothesis and
inconsistent with the string being merely wrong.

**Repro that would settle it:** change the recordings folder in Settings,
switch to the Uploader without restarting, and read the empty state.

### Strengthens Profiles finding 4

`Folders` carries **two** `Detect` buttons, and the second one detects an
**EVE-owned** folder — "the gamelogs folder from your EVE Online documents
folder". So the objection "EVE's folders are not detectable" is already
disproved inside the app. One EVE folder is detected automatically; the
other requires the user to navigate to it by hand.

---

## First run — `#route-firstrun`

**Reviewed on the second capture.** The first one was of stale code; the
launcher has since been corrected and `tmp/first-run-again.png` is main.
F1 below is kept because the tooling fault outlives the capture.

`C:\dev\wingman-testrun\run-first-run.bat` ends with

```
cd /d "C:\dev\flygd-wingman\.claude\worktrees\nav-restructure"
```

That worktree is at `2f60c8f` ("README: describe the app that ships"),
roughly #39 and six commits before lane 5. Verified directly: its
`index.html` still contains `No folder chosen yet` and has **no**
`firstrun-skip` element.

So the captured screen shows the pre-`be43305` first run, and the three
things it appears to lack — a skip, a sentence saying what Wingman is, and
an example placeholder — are exactly the three things `#49` added. Main's
markup has all of them.

### F1. The first-run launcher runs a stale worktree — `sure`, tooling, not UI

One line to fix. The consequence is larger than the line: **the first-run
smoke pass has been running against old code**, so any hand verification
of `#49` through this launcher verified the screen it replaced.
`run-test-build.bat` points at `C:\dev\flygd-wingman` and is unaffected —
every other capture in this document is current.

Worth a note in `docs/smoke-checklist.md` beside the first-run items:
the launcher's target tree is part of what the check depends on.

**Fixed 2026-08-25.** `run-first-run.bat` now runs `C:\dev\flygd-wingman`;
the old line is preserved in `run-first-run.bat.bak` and the reason is in a
comment above the replacement.

Re-checked after a second paste of the same capture (`tmp/first-run.png`,
byte-identical, unchanged mtime): still the stale tree. Three strings
settle it independently — the screen shows `No folder chosen yet`, one
OBS-only paragraph, and no skip; main has `placeholder="C:\Users\you\Videos"`,
two paragraphs opening "Wingman is an EVE multiboxing toolkit", and
`id="btn-firstrun-skip"`.

**The tell, for whoever runs it next:** if the card has a `Set this up
later` link beside `Continue`, it is main. If it does not, the launcher is
still pointed at `.claude/worktrees/nav-restructure` and nothing rendered
on that screen is worth reviewing.

### The screen, on main

`tmp/first-run-again.png`, 2026x1262 physical at 200% = 1013x631 CSS, so
close to the 840x625 floor in height and comfortable in width. All four
tells present: the skip link, two paragraphs, the toolkit sentence, and
the `C:\Users\you\Videos` placeholder. `Continue` renders muted maroon
with the field empty, which is the disabled accent style working exactly
as X1 says it does.

The title bar carries no destinations here, the card is vertically
centred, and the field is mono. The screen is in good shape; the findings
below are small except the first.

### F2. The heading is narrower than the screen it heads — `sure`, `screen-local`

`Choose your recording folder` is uploader-scoped. The paragraph directly
under it is product-scoped: "Wingman is an EVE multiboxing toolkit."

The eye lands on the largest text first, so the sequence a new user
actually experiences is *this is a folder chooser* and then, at body
weight, *actually it is a toolkit*. The first paragraph is doing the
heading's job in the heading's absence, one size down.

This is the one finding on the screen with product weight behind it.
PRODUCT.md opens by saying the uploader-first framing "is out of date and
should not be used to decide anything", and this is the first sentence of
the application at its largest type size. The prose was fixed in `#49`;
the heading was not.

The fix is not to make the heading long. `Wingman` as the heading, with
the folder ask carried by the field and the button, would put the two
sentences in the order the doc asks for. Whether the heading should name
the product or the task is a judgement call worth making deliberately
rather than inheriting.

### F3. `Set this up later` sits ~11 CSS px right of everything else in the card — `sure`, `shared`

Measured on the crop: the h1, both paragraphs and the field's border box
all begin at 568 physical px. The `Set this up later` text begins at 590.
Eleven CSS pixels is small enough to read as a mistake rather than a
choice, and the card has an otherwise unbroken left edge for it to break.

Same family as Settings 4 and Settings 12 — a control's own horizontal
padding pushing its text off a column the rest of the card holds. Likely
the `.linkbtn` padding, which would make it shared rather than local; the
finding is the measurement, the mechanism is a lead.

### F4. The Detect hint is aligned under the field but explains the third control — `worth trying`, `shared`

"Detect reads the folder from OBS's own configuration." sits at the
field's left edge. `Detect` is roughly 660 px to the right, past
`Browse...`. The sentence names its subject in the first word, which
carries it, but the eye still has to travel the width of the row to
connect them.

The same shape as Settings 3, which is already recorded as `shared`: hint
text inherits the row's left edge rather than sitting under the thing it
describes.

### F5. Two paragraphs, one voice, two different jobs — `worth trying`, `screen-local`

Both are `.firstrun-body` at the same size, weight and colour. The first
answers *what is this*; the second answers *what do I do and what happens
if I skip*. On a screen with one heading and no other structure, the only
thing separating them is a blank line.

Not obviously wrong — this is a product register and PRODUCT.md asks for
plain and short, which both are. But if the heading changes under F2, the
"what is this" paragraph may not need to exist at body length, and the
two-paragraph block becomes one.

Line length is 78ch at this window width, over the 65-75ch guidance,
though the card is centred and fixed so it does not grow further.

### F6. The status bar says `Ready` before anything is configured — `worth trying`, `shared`

Nothing is set up, the folder field is empty, `Continue` is disabled, and
the strip reads `Ready`. Same word-collision family as Skills 3: a status
word that means "the process is idle" read on a screen where it will be
taken to mean "you are ready".

The strip is shared, so this is a question about what it should say
during first run rather than about this card.

### Corroboration: `Detect` exists here, for a folder OBS owns

Third instance. First run has a `Detect` for the OBS recording folder;
Folders carries two more, one of them for an EVE-owned path. Profiles
still asks the user to type a path to an EVE-owned directory by hand.
That is now three places where the app detects a foreign application's
folder and one place where it does not, and the one place is the EVE
directory this product is named for.

### Corroboration: the card is vertically centred here

Uploader 14 said the app does not centre its empty state. It plainly can;
this screen does it. So the Uploader's empty state is a per-screen
omission and not a capability the layout lacks.

### Noted, not a finding: the quiet skip

`Set this up later` is the least prominent control on a screen whose own
prose tells the EVE-only user to use it. That is a documented deliberate
decision — the markup carries the comment "skipping is the quiet way out
of the screen, and Continue is the one accent per screen", and it follows
DESIGN.md's one-accent rule.

Recording the tension without calling it a fault: for a user who came for
previews and keybinds, the recommended action and the visually
recommended action are different controls. If first-run drop-off ever
becomes a question, this is the place to look. It should not be changed
on aesthetic grounds alone, because the reason it looks this way is
written down.

---

## Cross-cutting

### X1. The disabled accent style exists, works, and three screens do not use it — `sure`, `shared`

Supersedes Uploader 1, Profiles 9 and Settings 14, and shrinks all three.

`style.css:229`:

```css
button.btn.acc:disabled { box-shadow: none; filter: grayscale(.5); }
```

It is correct and visibly working — first run's `Continue` renders as a
muted maroon. So the problem is not a missing treatment. It is that
`Upload` (nothing selected), `Copy to selected` (no folder, no targets)
and `Show` / `Remove` (no webhook) never receive the `disabled`
**attribute**.

That also settles a question left open at Uploader 1: those buttons are
genuinely live in impossible states, not merely dressed as live.

Per-site attribute wiring rather than a design decision — but `shared`,
because the rule that decides *when* a control is inert is the thing three
screens currently answer differently (see Settings 1).

### X2. The floor is 840 CSS px at every scaling, and `DESIGN.md` says otherwise — `sure`, confirmed, `shared`

> **Resolved. See Corrections, C1.**

Every floor-related finding inherited from `docs/ui-critique.md` is checked
against a 560 CSS px viewport (840 physical at 150% scaling). The captures
are in physical pixels and the display scaling is not recorded, so none of
them can be confirmed or dismissed from this session's evidence.

`folder-narrow.png` looks healthy — both fields wide, `Browse…` and
`Detect` intact, nothing starved — but that is only meaningful if it is
the floor.

If the maintainer's standing note is right that the app cannot be resized
to the CSS floors, then those findings are **unverifiable through the
window by design**, and `docs/smoke-checklist.md`'s "drag the window to its
floor (840 logical)" item cannot be performed as written. That is a
finding about the checklist regardless of how the layout measures.

**Blocked on:** the display scaling percentage. It retroactively settles
whether `upload-floor.png` is the real floor, and therefore whether
Uploader findings 9 and 11 sit at the minimum or well above it.

### X3. ~~`EVE gamelogs` blank between captures~~ — **withdrawn**, sandbox artefact

`folders.png`: `C:\Users\tng\Documents\EVE\logs\Gamelo`.
`folder-narrow.png`, minutes later: empty.

If the field was not cleared by hand between captures, this is the failure
`DESIGN.md` names directly — "Nothing commits before the first payload has
rendered … a commit fired in that window writes blanks over a configured
install. There is a test recording that this once happened."

**Awaiting the maintainer's answer.** If it was cleared by hand, discard
this entry.

---

## Corrections

Answers from the maintainer that changed findings already written above.
Recorded here rather than by silently editing them, because the reasoning
that produced the wrong version is the useful part.

### C1. The CSS viewport floor is 840px at every scaling — supersedes X2, and corrects `DESIGN.md`

**Display scaling is 200%.** `upload-floor.png` is 1678x1242 physical =
**839x621 CSS**, against `MIN_WIDTH = 840` and `MIN_HEIGHT = 625`
(`ui/window.py:54-55`, passed as `min_size` at `:207`). The window was at
its minimum, and the minimum resolves in **CSS pixels**.

`DESIGN.md` states the opposite in bold: "`MIN_WIDTH` is **840 physical
pixels**, not logical … the CSS viewport floor is `840 / scale`: 672px at
125%, 560px at 150%." If that held, 200% would allow a 420px viewport. It
does not. `ui/chrome.py:10-22` notes the value lands in WinForms
`MinimumSize` / `ptMinTrackSize`, both of which are DPI-scaled.

The maintainer's standing note — "the app cannot be resized to the CSS
floors" — is this fact, observed previously and not explained.

**What this keeps:**

- **Uploader 9** (the `Upload` button below the fold) — `upload-floor.png`
  *is* 840x625 CSS. Confirmed at the documented minimum, not near it.
- **Uploader 11** (filename truncation eating the identifying characters)
  — same capture, same standing.

**What this discards**, in `docs/ui-critique.md`, as arithmetic against a
viewport that cannot occur:

- Uploader 1 — "the list loses Size, Length and Link at 560 CSS px".
- Settings 1 — "roughly 30px for a path, ~40px for a webhook".
  `folder-narrow.png` at ~835 CSS is direct counter-evidence: both fields
  are wide and both trailing buttons intact.
- Skills 2 — "the rail is 38% of the window at 150%".

`#47` and lane 0 did useful work; the emergency they were sized against
was not real.

**Confirmed.** Monitor is 3840x2160 at 200%, so the captures are native
and nothing is downscaled. Two independent matches:

| | physical | ÷2 = CSS | configured |
|---|---|---|---|
| width | 1678 | **839** | `MIN_WIDTH` 840 |
| height | 1242 | **621** | `MIN_HEIGHT` 625 |

Were the minimum 840 *physical*, that capture would be ~840px across. It
is twice that. `MIN_WIDTH` / `MIN_HEIGHT` resolve in logical units.

### X2b. The measurement contradicts the observation `#38` acted on — `unresolved`, needs a person

`DESIGN.md` does not only state the arithmetic; it reports an observation
resting on it:

> Five destinations needed 686px and clipped the close button off the
> right edge at 125%.

If the floor is 840 CSS at every scaling, 686px of unshrinkable content
fits inside it with room to spare and nothing should have clipped. Both
statements cannot be true as written.

**This is not a claim that `#38` was wrong.** Three destinations stand on
`PRODUCT.md`'s destination-vs-configuration test alone, which needs no
pixel argument, and something was evidently observed. What is now suspect
is the *recorded reason* — and that reason is the constraint the title bar
is governed by. The next person who wants to add a destination will do the
arithmetic in `DESIGN.md` and get an answer that appears wrong by the
scale factor.

Needs someone to reproduce the clip or establish that it cannot be
reproduced. Not answerable from screenshots.

### C2. `Unknown skill` is a fact about the character, not a lookup failure — rewrites Skills 1

> "I think Unknown skills is valid — it literally means the character
> doesn't know 2 skills."

The original entry read the string as an unresolved plan-file name or a
failed lookup, and built a finding on it. That was wrong.

**The misreading is the finding, and it is stronger than what it
replaced.** The reader who made it had the source, `PRODUCT.md`, and every
capture. In English "unknown" attaches to the speaker, not the subject —
*unknown to us*. The state meant is "not trained", or "not injected".
`PRODUCT.md`: "Say what happened and what to do." `Not trained` does both;
`Unknown skill` does neither.

Compounded by the treatment: `Missing` renders red, `Unknown skill`
renders dim. If the semantics are as `skills.js` suggests — `Missing` =
present but below the required level, `Unknown` = never injected — then
the **dimmer** label marks the **worse** state.

**Confirmed by the maintainer.** `Missing` = the skill is present but
below the required level. `Unknown` = it was never injected. So the
dimmer, greyer label is the more severe state, and the red one is the
milder. The colours are the wrong way round on top of the wrong word.

Finding 2 above (the same word labelling a character group and a
requirement state) is unaffected and still stands.

### C3. The outstanding-requirements filter exists and is not a control — corrects Skills 5

`skills.js:607-615` drops every requirement in the `Active` state before
rendering, with a comment giving the reason. So this **is** the
"filtering outstanding requirements only" the critique credited, and the
question asked of the maintainer was malformed — there was no missing
control to look for.

It also means all 36 rows in `skills-not-ready.png` are outstanding. The
original entry's "the actionable rows are scattered among the met ones" is
wrong; there are no met ones.

What survives: the outstanding set is rendered in plan order, so `Missing`
and `Unknown skill` interleave down 36 rows with no grouping by state.
Sorting by state answers "what do I train next" without adding a control.

### C4. X3 withdrawn

The blank `EVE gamelogs` field between the two `Folders` captures is a
sandbox artefact, not a blanked commit. No finding.

---

## Raised by the maintainer, outside the screenshots

Three gaps named from use rather than seen in a capture. None is a
critique finding; all three are about the app describing itself.

### M1. The tray menu says "Open uploader" — `sure`, `shared`

`obs_youtube_uploader/__main__.py:200`:

```python
pystray.MenuItem("Open uploader", lambda *_: on_open(), default=True),
```

Two lines below, the icon is named `"FlyGD Wingman"`; eleven lines below,
notifications are titled `"FlyGD Wingman"`. The same function uses the
right name twice and the wrong one once.

`PRODUCT.md` decides it without appeal to taste: the README's
"OBS-to-YouTube uploader with EVE extras" framing "is out of date and
should not be used to decide anything", and the tray menu is that framing
in the one place a user reads **before** the window exists. It is also
literally wrong since `#38`: `Uploader` now names one of three
destinations, and the item opens the window.

`Open Wingman`. Two words.

### M2. The version is not shown anywhere — `sure`, `shared`

`obs_youtube_uploader/__init__.py:1` already defines
`__version__ = "3.2.1"`, and `discord.py:20`, `evesettings/names.py:18`
and `eveskills/application.py:18` all import it. The value is plumbed; the
UI is the only consumer that never reads it.

`DESIGN.md`'s "State that must not be retyped" governs, and is already
half-broken: `pyproject.toml:15` and `__init__.py:1` both carry `3.2.1` by
hand. **Push it from `__version__`.** A third hand-typed copy in the page
is precisely the drift that section exists to prevent, and the copy a user
reads is the one that matters when they report a bug.

**Decision needed — where.** `General` is one checkbox and last in the
rail, so it has room. But `THIRD-PARTY-NOTICES.md` exists in the
repository with no UI surface at all, and GPL-3.0 attribution usually
wants one. So: a line in `General`, or `General` widened into an
About-shaped section, or a ninth rail item.

Note that `DESIGN.md`'s destination arithmetic does **not** apply here —
that constraint is about the title bar's 105px drag-region floor, not the
Settings rail. A ninth rail item is cheap.

### M3. No start-on-login setting — `worth trying`, `shared`

Best argued from `PRODUCT.md` rather than from convenience. The product
describes itself as "A tray app that starts hidden", and names bookmark
keybinds as "the only feature that runs continuously in the background".
Keybinds fire only while Wingman is running, so start-on-login serves a
**co-primary** feature. On that framing it reads as an omission rather
than an addition.

Nothing in `What it must not become` is touched: no telemetry, no account,
no gameplay automation, no EVE window handling.

Implementation note for whoever takes it: writing a Run key or a Startup
shortcut can fail on permissions, so this is a real instance of
`DESIGN.md`'s three-outcome commit model — refused, applied-but-not-
persisted, done — not a checkbox that assumes success.

**Decision needed — the default.** On after install is defensible for a
tray app; adding yourself to a user's startup unasked is the kind of thing
people resent discovering later. `PRODUCT.md` does not settle it. Noted as
unmade because it is expensive to reverse once shipped.

> **M2 decided.** Version and licence go in `General` as a second card
> headed `ABOUT`, alongside start-on-login; version rendered as selectable
> text, pushed from `__version__`, never typed into the page. A ninth rail
> item is deferred until `THIRD-PARTY-NOTICES.md` has a real surface to
> justify one.
>
> **M3 decided.** Start-on-login approved. Default recorded as **opt-in**,
> the reversible direction, unless the maintainer says otherwise.
