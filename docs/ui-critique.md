# UI critique — FlyGD Wingman, screen by screen

`DESIGN.md` closes by listing what it cannot judge: whether a screen is
worth adding, whether a control belongs where it is, whether the words are
right, whether the thing is any good. That list is this document's brief.
It reviews the five screens against `PRODUCT.md`'s statement of what the
app is and who it is for.

Scope note: this is a review. Nothing here has been implemented, and
nothing in the repository executes the page, so every finding marked
`needs the running app` is reasoning from source that a hand pass against
`docs/smoke-checklist.md` would settle in seconds.

**Deliberately not re-reported:** contrast and focus rings, the
`.check`/`.radio` wrapper rule, native dialogs, the destination count, the
Save-button removal and per-field commit model, "keybind" vocabulary, the
EVE visibility gate, the status strip appearing on every route, the
`gesture` / `alert_bookmarks` identifiers, the README screenshot, and
anything `tests/test_page_conventions.py` enforces mechanically.

**Relationship to `ui-layout-observations.md`:** that round's findings 1
(no outer margins), 3 (centred headers over left data), 4 (column widths),
5 (light dialog title bar), 6 (no typographic hierarchy) and 8 (bare status
string) are addressed. Finding 2 — "the least-used control dominates" — is
**partly** addressed and reappears below in a different form: the
Description box no longer takes the top 170px, but the panel that holds it
is a hard 320px that never yields, which is a bigger problem at the real
window floor than it was at the 100%-scaling screenshot that round was
written from. Finding 7 (row density) is unaddressed and is not worth
re-raising: `--row-h: 30px` reads fine at three type sizes.

**The measurement everything below is checked against.** `MIN_WIDTH` is
840 **physical** pixels and the app is system-DPI-aware, so the CSS
viewport floor is 672px at 125% scaling and **560px at 150%**
(`DESIGN.md`, and `style.css:554-558` does this arithmetic correctly for
one media query). Several of the findings below are simply that the rest
of the page was laid out against 840.

> ## ⚠ CORRECTION — the paragraph directly above is wrong
>
> Added by round-2 lane S4. **The floor is 840x625 CSS pixels at every
> display scaling.** `MIN_WIDTH` / `MIN_HEIGHT` resolve in *logical*
> units, so there is no `840 / scale`, and the 672px and 560px viewports
> this document reasons from **cannot occur**. Measured: the floor capture
> is 1678x1242 physical on a 3840x2160 display at 200% — 839x621 CSS,
> against `MIN_WIDTH` 840 and `MIN_HEIGHT` 625. `DESIGN.md` carries the
> full correction; `docs/ui-walkthrough.md` carries the evidence as C1.
>
> The original text is left in place because the reasoning that produced
> the wrong version is the useful part, and because this file is a record
> of a completed pass rather than a live specification. But **do not
> re-derive anything from it.** Three findings below are struck out
> entirely, each marked where it stands. Three more survive their
> conclusions while their arithmetic fails, also marked.
>
> A note on the parenthetical above: `style.css:554-558` was credited with
> doing the scaling arithmetic "correctly". That credit was earned against
> the wrong model. The query in question — `max-width: 839px` — happens to
> be the only one of the stylesheet's eight width queries that can fire at
> the real floor, and it does so by a single pixel, for reasons unrelated
> to the reasoning that praised it.
>
> `#47` and round-1 lane 0 did useful work. The emergency they were sized
> against was not real.

---

## 1. Uploader — `#route-main`

**Verdict.** The layout says the right thing: the list takes `flex: 1` and
the upload form is a fixed sidebar, which is the correct answer to the last
round's "least-used control dominates". But the sidebar's width is a
constant and the list's minimum is a sum of six constants, and at the
window's actual floor the second exceeds what is left of the first — so the
screen that is right at 840 CSS px silently loses half its data columns at
the two scalings most laptops ship with. Everything else here is smaller:
a combat-log checkbox that promises something it will not do on a fresh
install, a permanently-disabled button holding half a row, and an empty
state that names neither the folder nor the way to change it.

1. ~~**The recording list loses Size, Length and Link at the documented
   window floor, with no scrollbar to say so**~~
   > **DISCARDED — S4, round 2.** Arithmetic against a viewport that
   > cannot occur. The whole finding is computed from "at 150% scaling the
   > viewport is 560 CSS px"; the viewport is 840 CSS px at every scaling,
   > where this finding's own numbers give a 484px pane holding a 472px
   > grid — it fits, with room to spare, as the text below concedes.
   > `folder-narrow.png` at ~835 CSS is direct counter-evidence: both
   > fields wide, both trailing buttons intact, nothing starved. The
   > `max-width: 767px` and `max-width: 607px` blocks that drop those
   > columns cannot be reached by resizing the window at any scaling.
   > Note that the two Uploader findings raised against the *same* floor
   > in `docs/ui-walkthrough.md` — the primary button below the fold, and
   > filename truncation — survive, because they were measured at 840x625
   > CSS rather than derived from 560.
   - **Where** — `style.css:310` (grid template), `style.css:452-455`
     (`.panel { width: 320px }`), `style.css:450` (`#panel-slot { flex:
     none }`), `style.css:279` (route padding and gap), `style.css:284`
     (`.list-pane { overflow: hidden }`), `style.css:287`
     (`.list-scroll { overflow-x: hidden }`); `docs/smoke-checklist.md:241-245`
     is the check that would have caught it and tests the wrong width.
   - **What the user notices** — At 150% scaling the viewport is 560 CSS
     px. The route spends 24px on padding and 12px on the gap, the panel
     takes a fixed 320px, and the list pane is left with 204px. Inside it
     the grid's minimum is `34 + 120 + 92 + 84 + 76 + 46 = 452px` plus
     20px of row padding — 472px of column in 204px of pane. `Modified`
     is cut in half at the pane edge and `Size`, `Length` and `Link` are
     not on screen at all. At 125% (672px viewport, 316px pane) `Size` is
     the one cut in half and `Length` and `Link` are gone. Both `overflow`
     rules are `hidden`, so there is no horizontal scrollbar and nothing
     indicates the columns exist. The smoke item that guards this reads
     "Drag the window to its floor (840 logical). Every column still
     present … NO horizontal scrollbar" — at 840 CSS px the pane is 484px
     and the grid fits with 12px to spare, so the check passes on the one
     width where the layout is fine. The checklist already knows the CSS
     floor is 560px; it says so at `docs/smoke-checklist.md:1020-1022`.
   - **Confidence** — `sure` (arithmetic from the stylesheet; the exact
     button and glyph widths do not enter into it, only the six declared
     column tracks and the declared panel width).
   - **Blast radius** — `screen-local`. The lever is `.panel`'s width and
     the grid template, both in this screen's own CSS sections. A media
     query that drops the panel below the list, or lets it shrink, or
     sheds columns deliberately rather than by clipping, is a decision
     about this screen only.

2. **The combat-log checkbox is on by default, and on a fresh install the
   confirmation promises a Discord post that will never happen**
   - **Where** — `index.html:83-86` (`checked`, with no gating anywhere),
     `panel.js:54` (read straight into `start_upload`),
     `ui/copy.py:96-97` (`logs_line` is composed from the checkbox alone),
     `ui/api.py:925-927` (no webhook ⇒ `_skip_logs`).
   - **What the user notices** — First install, no webhook configured.
     They select a recording and press Upload. The confirm says
     `Logs:     combat logs posted to Discord afterwards`. They confirm.
     The video uploads, and the status strip turns WARNING:
     "Upload complete — combat logs skipped: … Set it up in Settings."
     This happens on **every** upload until they either configure a
     webhook or notice the checkbox — and the checkbox looks like a
     feature they have, so the warning reads as a recurring failure rather
     than as an unconfigured option. `PRODUCT.md`'s tone rule is "state
     cost before an irreversible action": the confirm is stating a cost
     that is not real. Nothing on the panel says a webhook is required,
     and the panel has no idea whether one is configured — `onSettings`
     already reaches `panel.js:109-114`, so it could.
   - **Confidence** — `sure`.
   - **Blast radius** — `shared`. The default state is markup, but making
     the checkbox honest means either `ui/copy.py` learning whether a
     webhook exists (so the confirm line is conditional) or the panel
     reading `discord_webhook` off the `onSettings` payload it already
     receives. Either touches Python-side copy or `panel.js`.

3. **Retry holds half a row permanently and is disabled on every visit
   except the one after a failure**
   - **Where** — `index.html:96-99` (`.secondary-row`), `panel.js:97-99`
     (`onRetryAvailable`), `style.css:493-494` (`flex: 1` each).
   - **What the user notices** — Below the accent Upload button sits a row
     of two equal buttons: `Retry`, greyed, and `Delete selected`, live.
     Retry is available only after an upload has failed in this session,
     which for most users is never. So the permanent arrangement is a dead
     control given the same weight as the only button on the screen that
     removes files from disk, and it puts a destructive action one row
     below the primary one at equal width. Hiding Retry until
     `onRetryAvailable` says otherwise gives Delete its own row and
     removes the dead half.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local` (this panel's markup, its CSS
     section, and one line in `panel.js`).

4. **The empty state names neither the folder it watched nor the way to
   change it**
   - **Where** — `index.html:55-57`, `list.js:151`.
   - **What the user notices** — "No recordings found in the watched
     folder." The user cannot see which folder that is without opening
     Settings › Folders, and cannot act from here. This is the exact
     shape `PRODUCT.md` rules out — "Say what happened and what to do.
     'That folder does not exist.' — not 'An error occurred.'" It is also
     the most likely screen a first-run user lands on immediately after
     nominating a folder, so it is where a wrong pick surfaces. Naming the
     path and offering the folder is one sentence and one button.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local` for the markup; note this string is
     composed in HTML rather than `ui/copy.py`, unlike almost every other
     user-facing sentence in the app, so naming the path in it means either
     moving it to Python or pushing the path to the page.

5. **There is no way to reach the watched folder from the screen that is
   about its contents**
   - **Where** — `index.html:60-64` (`.list-foot`), by absence.
   - **What the user notices** — A recording is missing, or one is
     mid-write, or they want to check what OBS actually produced. The only
     file affordances are double-click on a row (opens the video) and the
     context menu (both entries act on the YouTube link,
     `list.js:284-288`). "Open the recordings folder" is the reflex, and
     the footer — which holds Select all, Select none and a count — has
     the room for it. `Api.open_path` exists but is keyed to a row.
   - **Confidence** — `needs the running app` (whether this is felt as a
     gap depends on how often a recording is inspected outside Wingman;
     the absence itself is certain).
   - **Blast radius** — `shared` (a new bridge method on `ui/api.py`).

---

## 2. Profiles — `#route-evesettings`

**Verdict.** The screen is for copying one character's EVE settings onto
others, and the card that does it is the second of three, below a card of
setup that is correct after the first visit and inert forever after. The
copy card itself is well built — the filter, the visible-only target rule
at `evesettings.js:187-194`, the three-state pill — but its mode switch is
the one unlabelled control on the screen, and the confirmation that guards
the irreversible action counts "file(s)" at a user who was choosing
characters. The Backups card is the weakest thing here: two destructive
buttons at ragged x positions after an undelimited run of text.

1. **The once-ever setup card sits above the task the screen exists for**
   - **Where** — `index.html:358-372` (Settings folder) versus
     `index.html:374-406` (Copy settings); `style.css:675`
     (`#route-evesettings` scrolls as one column).
   - **What the user notices** — Every visit begins with a folder path, a
     Choose button, an EVE-running pill, a Server dropdown and a Profile
     dropdown. Two of those five are set once; the other three change
     rarely. The card the user came for begins below them, and on a 560px
     viewport with `.settings`' 620px max-width the first card is roughly
     a third of the visible height before the copy card starts. This is
     the same shape as the last round's finding 2 in a new place: the
     thing you came to do starts below the thing you configured once.
     Collapsing the folder card to a one-line summary with an edit
     affordance — the root, the server and the profile are three short
     strings — puts the target list on screen at open.
   - **Confidence** — `sure` for the ordering; `needs the running app` for
     exactly how much of the copy card is pushed below the fold.
   - **Blast radius** — `screen-local`.

2. **The Characters / Accounts switch is the only unlabelled control on
   the screen, and it changes what three other controls mean**
   - **Where** — `index.html:381-391` (the `<span class="lab"></span>` is
     deliberately empty, per the comment at `index.html:376-380`),
     `evesettings.js:20-28` (`kind()` drives `rows()`),
     `evesettings.js:241-248`.
   - **What the user notices** — A pair of radios floating in the label
     column's shadow with no word in front of them. They switch the source
     dropdown, the target list and the filter between per-character and
     per-account settings files — three controls, none of which announce
     the change. On a first visit there is nothing saying whether this is
     a filter, a mode, or what an "account" settings file even is. The
     empty `.lab` was added to hold the alignment, which is right; it just
     needs a word in it. "Copy" reads correctly against both options.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local` (one text node).

3. **The copy confirmation counts files at a user who selected characters,
   and does not mention the running-client hazard the screen already
   tracks**
   - **Where** — `ui/api.py:2119-2123`, against `index.html:363` and
     `evesettings.js:68-78` (the EVE-running pill).
   - **What the user notices** — "Copy these settings onto 3 other
     file(s)? Each one is backed up first. This cannot be undone except by
     restoring a backup." They ticked three character names; the dialog
     talks about files, and the "(s)" is exactly the padding
     `PRODUCT.md`'s tone rule rules out ("Name things the way the user
     does"). More consequentially: the screen renders a warn-toned pill
     saying "EVE running" precisely because copying into a profile while a
     client is open is the hazard — EVE rewrites its own settings on exit
     — and the confirmation, which is the last thing before the
     irreversible act, does not repeat it. The pill is advisory and the
     dialog is modal; the warning is on the wrong one.
   - **Confidence** — `sure` for the wording; `needs the running app` only
     to confirm the pill is genuinely up in the case being described.
   - **Blast radius** — `shared` (`ui/api.py`, and the string belongs in
     `ui/copy.py` where the rest of the tested copy lives).

4. **The Backups list is an undelimited text run with two destructive
   buttons wherever it happens to end**
   - **Where** — `index.html:408-414`, `evesettings.js:162-175`,
     `style.css:681` (`max-height: 38vh`), `style.css:1004-1007` (the
     `.danger` treatment that exists and is not used here).
   - **What the user notices** — Each row is `2026-08-21 14:03 · profile ·
     Tranquility_abc (auto)` as a single text node, then `Restore`, then
     `Delete`. Nothing is column-aligned, so ten backups produce ten
     different button positions and the eye cannot scan the dates. Both
     buttons are plain `.btn`, so permanently deleting a backup looks
     identical to restoring one — while Skills, on the same app, already
     marks its irreversible action with `.linkbtn.danger` and
     `.btn.danger`. Both are confirmed in Python
     (`ui/api.py:2214-2218` for delete), so this is about what the row
     looks like before the click, not about the guard.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local`.

5. **"(auto)" is never explained, and nothing says backups are pruned**
   - **Where** — `evesettings.js:167` (the `(auto)` suffix),
     `ui/api.py:2127-2128` (`auto_keep`, default 10, pruned after every
     copy).
   - **What the user notices** — Half the backup list carries a suffix
     with no key anywhere. Worse, the list silently loses its oldest
     entries as copies accumulate, and the card that offers "Back up this
     profile" gives no hint that what it creates is subject to that.
     `PRODUCT.md` says assume EVE fluency and explain Wingman; automatic
     pre-copy backups and a keep-10 window are Wingman, not EVE.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local` for the hint; the count would have
     to come off the payload rather than be typed into the page — this is
     exactly the class `DESIGN.md`'s "State that must not be retyped"
     covers.

6. **The settings-folder path is a bare `<span>` with no label column, no
   monospace, and nothing to stop it pushing the row apart**
   - **Where** — `index.html:361`, against `style.css:739-742` (the
     screen-wide 118px label column), `style.css:195-198` (`.mono`, and
     `span.field`'s ellipsis), `docs/smoke-checklist.md:185-186`
     ("Machine text is monospace. Paths, the webhook field and the webhook
     summary render in the monospace face").
   - **What the user notices** — The one path on this screen renders in the
     proportional face while every other path in the app is monospace, it
     is the only row whose first element is not on the shared label
     column, and it has no truncation. A Windows path offers few line-break
     opportunities, so a long root is liable to push "Choose folder…" and
     the EVE pill toward or past the right edge of the 620px card — and at
     a 560px viewport the card is narrower than that. `span.field` at
     `style.css:198` already provides exactly the ellipsis this needs.
   - **Confidence** — `sure` for the convention breaches (label column,
     monospace); `needs the running app` for whether the row actually
     pushes the pill off, since that depends on Chromium's break
     behaviour around backslashes.
   - **Blast radius** — `screen-local` (markup classes only).

---

## 3. Skills — `#route-skills`

**Verdict.** This screen answers its question well — the grouped roster,
the lockout guard at `skills.js:278-305`, the two-step forget, filtering
outstanding requirements only — and its problems are all in the rail and
the words. The rail is 214px, which is 38% of the window at 150% scaling,
and its top and bottom blocks are both file management; the plan list, the
one thing you come here to change, is sandwiched between them.
[**S4:** "38% of the window at 150%" is wrong — the floor is 840 CSS at
every scaling, so the rail is 25%. The sandwiching is unaffected.] And the
plan rail's ratio and the plan header's count are two different quantities
printed as similar numbers, side by side, with neither one labelled.

1. **`3/12` in the rail and `12 requirements` in the header are different
   quantities and read as the same one**
   - **Where** — `skills.js:126-127` (`plan.ready_count + '/' + total`,
     where `total = characters().length`), `skills.js:208-209`
     (`count + ' requirements'`, where count is `requirement_count`),
     `index.html:430` and `index.html:440-441`.
   - **What the user notices** — The rail shows `Armour Rolling  3/12`.
     The header shows `Armour Rolling` and `12 requirements`. The 12 in
     the rail is the number of characters; the 12 in the header is the
     number of skills in the plan. They are adjacent, they are both
     unlabelled, and on any roster whose size happens to be near a plan's
     length they are indistinguishable. A first visitor reads `3/12` as
     "three of twelve requirements met", which is a plausible and wrong
     reading of a screen whose entire purpose is readiness. The rail is
     the app's densest information and it has no key.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local` (a `title`, a `.rail-head`
     sub-label, or a suffix on the ratio).

2. ~~**The rail is 214px wide and only its middle third is what the user
   came for**~~
   > **DISCARDED — S4, round 2.** "At 150% scaling the viewport is 560px"
   > is false; it is 840px. The rail is 214px of 840, which is 25%, not
   > 38%, and the roster keeps ~590px rather than 310px. The complaint
   > about *what occupies* the rail — two of three blocks being file
   > management, with the plan list sandwiched between them — is a real
   > observation that does not depend on the arithmetic, and round 2 picks
   > it up separately. What is discarded is the width emergency. The smoke
   > item this finding faults for "measuring the rail against 626px of
   > roster, which is the 100%-scaling case" was measuring the only case
   > there is; S4 has corrected that item for the opposite reason.
   - **Where** — `index.html:422-436`, `style.css:845-867`
     (`grid-template-columns: 214px minmax(0, 1fr)`),
     `docs/smoke-checklist.md:1383-1385` (checks the layout at "840×625 —
     626px beside the 214px rail", again in logical rather than physical
     pixels).
   - **What the user notices** — At 150% scaling the viewport is 560px, so
     the roster gets `560 − 24 − 12 − 214 = 310px` and the rail takes 38%
     of the window. What is in that 38%: a count line, `Add character`
     (used once per account, ever), `Refresh characters`, the plan list,
     then `Open plans folder` and `Reload plans` — both of which exist to
     support editing plan files in a text editor, which is a thing you do
     rarely and not while reading a roster. Two of the three rail blocks
     are setup, permanently occupying the width the character names need.
     The smoke item that would catch this measures the rail against 626px
     of roster, which is the 100%-scaling case.
   - **Confidence** — `sure` for the arithmetic; `needs the running app`
     for whether 310px actually truncates real character names — EVE names
     run long and `.skills-name` ellipsises at `style.css:965-968`.
   - **Blast radius** — `screen-local`.

3. **"Not yet refreshed" is the wrong label for the most common way to
   land in that group**
   - **Where** — `skills.js:275` (`Unscored: 'Not yet refreshed'`),
     against `skills.js:415-422`, which documents that an empty or broken
     plans folder makes **every** character Unscored.
   - **What the user notices** — With no plans in the folder, the whole
     roster collapses into a group headed "Not yet refreshed" — which is
     false, and which points the user at the Refresh button rather than at
     the plans folder. The code already knows the distinction: the hint
     beside the roster says "No local plans yet." The group heading
     contradicts it two lines below. The comment at `skills.js:415-422`
     was written about the lockout risk and is right about that; the label
     is the part that did not follow.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local`.

4. **The empty state names a location instead of a control**
   - **Where** — `skills.js:405-408`.
   - **What the user notices** — "No characters yet. Add one from the
     actions on the left." `PRODUCT.md`: "Name things the way the user
     does." The control is called `Add character`; the sentence should
     say so. On the narrowest window the rail is also the thing most
     likely to be scanned past.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local`.

5. **Nothing on the screen says what a plan is or how to write one until
   there are none**
   - **Where** — `skills.js:420-422` (the hint fires only when
     `!plans().length`), `index.html:428-431`.
   - **What the user notices** — With one plan present, a user who wants a
     second has `Open plans folder` and no statement anywhere that a plan
     is a `.txt` file of skill names and roman numerals. The one sentence
     that says it is shown only to users who have zero plans — that is,
     only before they have any reason to care. `PRODUCT.md` says the app
     may assume EVE fluency but must explain Wingman, and the plan file
     format is Wingman's.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local`.

---

## 4. Settings — `#route-settings`

**Verdict.** The rail is the right structure for eight groups and it
solved the long-scroll problem. Two things are wrong with what it holds.
First, the section it lands on is General, whose entire content is one
checkbox for turning the app's EVE half off — so the first thing every
user sees on opening Settings is a switch for removing most of the
product. Second, the shared 118px label column plus two or three trailing
buttons is a layout for an 840px window: at 560px the Folders and Discord
rows leave a path field and a credential field roughly 30–50px wide. The
Bookmarks section is worse, because it has three trailing controls and
eighteen rows of them.
[**S4:** an 840px window is the only window there is, so the second half
of this verdict is void — see the discard note on finding 1 below. The
first half, General as the landing section, stands.]

1. ~~**Folders, Discord and the Bookmarks binds starve their fields at the
   window floor**~~
   > **DISCARDED — S4, round 2.** "At 560px the Folders and Discord rows
   > leave a path field and a credential field roughly 30-50px wide" is
   > computed from a viewport that cannot occur. At the real floor of 840
   > CSS px those rows are not starved: `folder-narrow.png`, captured at
   > ~835 CSS, shows both fields wide with `Browse…` and `Detect` intact.
   > The `max-width: 720px` block this finding relies on to rescue the
   > rows by stacking each label above its field cannot fire through the
   > window at any scaling — which means the collapse it describes is
   > unreachable, not that the rows need it.
   > Round 2 raises a *different*, confirmed problem in the same rows
   > (`docs/ui-walkthrough.md`, Settings 11 and 12): not starved fields
   > but ~600px of dead space between a keybind's action name and its
   > binding, and control rows starting at three different left edges.
   > Those are S2's and R2's, and they are not this finding.
   - **Where** — `style.css:739-742` (`.lab` fixed 118px, `flex: none`),
     `style.css:746` (`.field { flex: 1; min-width: 0 }`),
     `style.css:617` (`168px` rail), `style.css:178` (`.row` gap 10px);
     the rows themselves at `index.html:213-224` (Folders),
     `index.html:238-249` (Discord, with `style.css:799` pinning the
     toggle at 62px), and `index.html:293-299` with
     `bookmarks.js:150-200` (eighteen bind rows, `style.css:707` pinning
     `.bindbtn` at 150px, `style.css:699-701` giving the action name the
     rest).
   - **What the user notices** — At a 560px viewport the settings pane is
     `560 − 24 − 12 − 168 = 356px`, less 32px of card padding = 324px of
     row. The Folders row spends 118px on the label, ~78px on "Browse…",
     ~66px on "Detect" and 30px on three gaps, leaving roughly 30px for a
     monospace Windows path — a field showing about three characters, with
     `min-width: 0` ensuring it shrinks rather than pushing anything out.
     Discord is the same shape: 118 + 62 (Show) + ~72 (Remove) + 30 leaves
     about 40px for a masked webhook that the user is expected to verify
     by eye. The bind rows have no fixed label but three trailing controls
     — a 150px `.bindbtn`, `Clear` and `Type…` — so "Convert EvE-Scout
     Bookmarks" gets roughly 60px and wraps or ellipsises to nothing,
     eighteen times.
   - **Confidence** — `sure` for the label, gap and `min-width` maths;
     `needs the running app` for the exact button widths, which depend on
     rendered text.
   - **Blast radius** — `shared`. `.settings` is also the Profiles route's
     wrapper (`index.html:357`), so any change to `.settings .row`'s
     behaviour — wrapping the buttons below the field under a width
     threshold, or letting the label column collapse — lands on two
     screens at once. Worth saying explicitly because the rule reads as
     Settings-only from its name.

2. **Settings opens on a section whose whole content is a switch for
   turning off most of the app**
   - **Where** — `index.html:120` and `index.html:132-146` (General is
     marked active in markup and holds one checkbox, one hint and one
     message slot), `app.js:143` (`WM.current_section = 'account'`).
   - **What the user notices** — Press the gear. The first pane is
     headed "EVE ONLINE TOOLS" with a single checkbox reading "Show the
     EVE Online tools" and a paragraph explaining that unticking it makes
     Wingman just the uploader. That is a legitimate control and a poor
     landing: it is the least-used switch on the screen (visited once,
     probably never), it takes the most prominent pane in the app's
     configuration surface, and it frames the first impression of Settings
     as "here is how to remove things". Uploads, Folders or Account are
     all better landings, and General would be a fine last rail item.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local` for reordering the rail; `shared`
     if the landing section changes, because `app.js:143` and the two
     `active` classes in markup have to move together — see finding 6.

3. **"Category ID" and "(20 = Gaming)" ask for a YouTube API magic
   number**
   - **Where** — `index.html:180-185`, `ui/api.py:1234`
     (`set_category` takes the raw string).
   - **What the user notices** — A numeric text field labelled "Category
     ID" with the hint "(20 = Gaming)". `PRODUCT.md`'s rule is "assume
     fluency in EVE, explain Wingman" — this assumes fluency in the
     YouTube Data API instead, from an audience defined by wormhole
     multiboxing. The hint discloses exactly one value, which also implies
     the others are undiscoverable from here; they are, and the user is
     sent to Google's documentation for a field they will set once. The
     categories that plausibly matter to this audience number about three,
     and the same `<select class="field">` pattern the Privacy row above
     it uses would remove the concept entirely.
   - **Confidence** — `sure`.
   - **Blast radius** — `shared` if it becomes a select, because
     `set_category` currently validates a free string
     (`ui/api.py:1234`); `screen-local` if only the words change.

4. **Two rail items repeat themselves as their own card heading, and two
   different sections both head a card "Keybinds"**
   - **Where** — `index.html:124` versus `index.html:212` ("Folders" /
     "Folders"), `index.html:125` versus `index.html:236` ("Discord" /
     "Discord (combat logs)"); `index.html:294` and `index.html:337` (two
     cards headed "Keybinds", in Bookmarks and in Previews).
   - **What the user notices** — `DESIGN.md` states the first rule
     directly: "A screen may not repeat its own tab name as its first card
     heading." The rail item is the tab here, and Folders repeats it
     exactly. The second half matters more: Bookmarks and Previews each
     hold a card headed "Keybinds", they configure two independent keybind
     systems, and those systems can collide — `previews.js:22-31` exists
     entirely to detect and mark that collision. A user reading "Keybinds"
     in Previews has nothing on screen telling them a second, differently
     scoped set exists one rail item away. "EVE-focused keybinds" and
     "Global keybinds" would carry the distinction the collision code
     already knows about; the copy at `index.html:339-341` states the
     global-ness in prose but only under the heading that does not.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local`.

5. **Notifications offers two options and no way to have neither**
   - **Where** — `index.html:194-203`, `ui/api.py:1228`
     (`set_notify_mode`).
   - **What the user notices** — "Show a tray notification" or "Open the
     uploader window immediately", with the first pre-selected as
     recommended and no third choice. `PRODUCT.md` describes this as a
     utility used "beside a game, often mid-fleet, on a second monitor" —
     a fleet in a wormhole is precisely the context in which a user wants
     Wingman to record the file and say nothing at all until they come
     looking. Two radios with no off state is a missing option, not a
     preference; the radio group cannot even be cleared once set.
   - **Confidence** — `sure` that no third option exists; `needs the
     running app` only for whether users want it.
   - **Blast radius** — `shared` (`ui/api.py`'s `set_notify_mode` accepts
     a fixed set, and the watcher's announcement path reads it).

6. **`WM.current_section` and the visibly active section disagree until
   the user clicks the rail**
   - **Where** — `app.js:143` (`WM.current_section = 'account'`),
     `app.js:125` (entering Settings dispatches `wm:section` with
     `WM.current_section`), against `index.html:120` and `index.html:132`
     (General carries `active` in markup).
   - **What the user notices** — Nothing, today. This is a latent
     inconsistency rather than a live defect: opening Settings paints
     General and announces "account", and no current listener acts on a
     section name other than its own (`bookmarks.js:386-406`,
     `previews.js`, and `settings.js:306-308`, which only tests
     `!== 'discord'`). It is worth recording because `DESIGN.md` makes
     section entry the fetching contract — "Route and section entry is how
     screens **fetch**" — so the first section that fetches on entry and
     is not Bookmarks or Previews will fetch for a pane the user is not
     looking at, or fail to fetch for the one they are. The initial value
     and the two `active` classes are one fact written in three places.
   - **Confidence** — `sure` (read from source; the "nothing happens
     today" half depends on the current listener set, which is small
     enough to enumerate).
   - **Blast radius** — `shared` (`app.js`).

---

## 5. First run — `#route-firstrun`

**Verdict.** This is the only screen in the app the user cannot leave, and
it asks for the one thing `PRODUCT.md` says the EVE half must not require.
A wormhole multiboxer who installed Wingman for previews and bookmark
keybinds is stopped at a mandatory OBS-recordings folder with no skip, and
the screen never says what the application is. Separately, its Detect
button fails silently — the same button in Settings, twenty lines away in
a sibling module, says so.

1. **A recording folder is mandatory, which contradicts a stated product
   constraint**
   - **Where** — `index.html:481-483` (`disabled` Continue),
     `firstrun.js:15-19` and `firstrun.js:33-36` (enabled only when
     `chosen` is non-empty), `firstrun.js:48-58` (the only exit is a
     successful `set_folder`), `app.js:110-111` (the gear and the whole
     destination nav are hidden on this route).
   - **What the user notices** — There is no Skip, no Later, and no way to
     reach Settings, Profiles or Skills. `PRODUCT.md` states the
     constraint plainly: "It must not require the EVE tools to upload a
     video, or a Google account to use the EVE tools. The two halves must
     stay independent." The recordings folder is the uploader half's
     configuration, and it is currently a gate on the EVE half. The
     document also ranks previews and bookmark keybinds as co-primary with
     uploading, so this is not a corner case — it is the front door for a
     third of the stated audience. A "Set this up later" link that routes
     to `main` with an empty list (which already renders an empty state)
     is the smallest form of the fix.
   - **Confidence** — `sure`.
   - **Blast radius** — `shared`. Skipping means `main` has to tolerate no
     configured folder, and `_push_first_run_when_ready`
     (`ui/api.py:1621`) decides when this screen appears at all — so
     "skipped" has to be a state Python knows about, or the screen returns
     on every launch.

2. **The screen never says what the application is**
   - **Where** — `index.html:466-471`.
   - **What the user notices** — The first and only thing Wingman says to
     a new user is "Choose your recording folder — Wingman watches one
     folder for new OBS recordings." Nothing mentions client previews,
     bookmark keybinds, profiles or skills. `PRODUCT.md` opens by saying
     the README's framing — an uploader with EVE extras — "is out of date
     and should not be used to decide anything", and this screen is that
     framing, presented before the user has seen anything else. One
     sentence naming the other half would also make the skip in finding 1
     legible rather than arbitrary.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local`.

3. **Detect does nothing, visibly, when it finds nothing**
   - **Where** — `firstrun.js:25-29` (`if (path) setChosen(path)` — no
     else), against `settings.js:132-137`, which rewrites its note to
     "Detect found neither folder automatically — use Browse to pick them
     yourself."
   - **What the user notices** — OBS is not installed, or its config is
     elsewhere. They press Detect. Nothing moves: the field stays empty,
     the note still reads "Detect reads the folder from OBS's own
     configuration", Continue stays disabled. There is no way to tell a
     failed detection from a dead button, on the one screen with no way
     out. The correct behaviour already exists in the sibling module and
     the note element (`firstrun-note`) is already used as a message slot
     by the error path at `firstrun.js:54`.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local`.

4. **The `firstrun-note` element carries three different jobs and one of
   them is permanent**
   - **Where** — `index.html:478-480`, `firstrun.js:54`.
   - **What the user notices** — The note explains Detect. On a refused
     folder it is overwritten with `res.error` and never restored, so a
     user who mistypes a path, reads the error, and then wants the Detect
     explanation back has lost it for the session. Combined with finding 3
     this element would be carrying the Detect explanation, a detection
     failure and a commit refusal with no rule about precedence. The
     comment at `firstrun.js:51-53` reasons the precedence out for two of
     the three; a third slot, or restoring the note on the next input
     event, settles it.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local`.

5. **The placeholder reports status instead of suggesting input**
   - **Where** — `index.html:473-475` (`placeholder="No folder chosen
     yet"`).
   - **What the user notices** — The field is typeable
     (`firstrun.js:33-36`), and its placeholder — the one piece of text
     inside it — tells the user something they can already see rather than
     what a valid value looks like. An example path is the conventional
     content, and "no folder chosen yet" is already implied by the
     disabled Continue button below it.
   - **Confidence** — `sure`.
   - **Blast radius** — `screen-local`.

---

## If I could make one change per screen

- **Uploader** — Finding 1. Make the list survive 560 CSS px. Every other
  finding on this screen is about a control; this one is about whether the
  screen's primary content is on screen at the two display scalings most
  Windows laptops ship with, and it is currently guarded by a smoke item
  that measures the wrong width.
- **Profiles** — Finding 1. Collapse the Settings-folder card to a summary
  line so the target list — the reason the screen exists — is visible when
  the screen opens.
- **Skills** — Finding 1. Label the rail's ratio, or make it unambiguous
  against the header's requirement count. It is the densest number in the
  app and it currently invites the wrong reading of the one question the
  screen exists to answer.
- **Settings** — Finding 1. Fix the row layout at the window floor. A
  30px path field and a 40px credential field are not a polish issue, and
  the Bookmarks section multiplies the same problem by eighteen.
- **First run** — Finding 1. Let the user skip. It is the only screen with
  no exit, and requiring it contradicts a constraint `PRODUCT.md` states
  as a hard rule.
