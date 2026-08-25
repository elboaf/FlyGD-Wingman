# UI work lanes, round 2 — decomposing `docs/ui-walkthrough.md`

`docs/ui-walkthrough.md` raises 62 findings across five routes, plus three
items the maintainer raised outside the screenshots. This document sorts
them into **four shared lanes that run in parallel**, then **five screen
lanes that run in parallel once the shared ones merge**.

Nothing here is implemented. This is a routing document, the successor to
`docs/ui-work-lanes.md` (round 1, lanes 0–5, merged).

**What changed since round 1.** Round 1 had a single lane 0 that blocked
everything else. That was the right call when every shared finding landed
in one region of `style.css`. This round's shared findings fall into four
groups that do not share a file region at all — CSS primitives, Settings
row machinery, Python, and documentation — so they can run at the same
time. The serialization is between *waves*, not inside them.

**Paths.** Everything below uses real paths: `obs_youtube_uploader/web/*`
and `obs_youtube_uploader/ui/*`.

**Line numbers** are against `main` at `be43305` and will drift. Treat them
as "the region beginning at this banner comment", not as absolute.

---

## The rule that decides the split

Unchanged from round 1: a file region is **shared** if two lanes could be
editing it in the same week. Shared regions belong to a wave-1 lane alone,
and every screen lane gets a hard "must not touch" on them.

The one refinement round 1 taught: **a shared *root cause* does not make
the whole finding shared.** X1 is the example. The disabled accent style
exists and works; three screens fail to set the `disabled` attribute. The
policy is shared, the twelve call sites are not. So those findings appear
twice below — once in a wave-1 lane as a decision plus a helper, once in
each screen lane as execution.

### Region ownership

| Region | Owner |
|---|---|
| `style.css:1-100` — fonts, tokens | S1 |
| `style.css:101-161` — titlebar, `.routenav`, `.route` | S1 |
| `style.css:162-276` — `.card`, `.row`, `.field`, `.btn`, `.btn.acc`, `.check`, `.radio`, focus, scrollbar | S1 |
| `style.css:588-651` — status strip | S1 |
| `style.css:652-698` — modal dialog layer | S1 |
| `style.css:1301-1317` — `prefers-reduced-motion` | S1 |
| **`style.css:884-889`** — `.linkbtn` | **S2 — rendered on bind rows *and* first run** |
| **`style.css:891-978`** — `.settings` wrapper, the 118px `.settings .row > .lab`, `.pill`, `.led`, `.radio`/`.ring`, `#f-webhook`, `.settings .toggle`, `.field-msg` | **S2 — rendered on Settings *and* Profiles** |
| `style.css:979-1025` — the settings row at the window floor | S2 |
| `web/app.js` — routing, sections, bridge registration, EVE gate | S1 |
| `web/panel.js:102-262` — status strip + dialog layer | S1 |
| `index.html` titlebar, `#statusbar-slot`, `#dialog-slot` | S1 |
| `ui/api.py`, `ui/copy.py`, `__main__.py`, `__init__.py`, `ui/window.py`, `pyproject.toml` | S3 |
| `DESIGN.md`, `PRODUCT.md`, `docs/smoke-checklist.md`, `docs/ui-critique.md` | S4 |
| `style.css:277-587`, `list.js`, `panel.js:1-101`, `index.html #route-main` | R1 |
| `style.css:699-766`, `style.css:832-883`, `settings.js`, `bookmarks.js`, `previews.js`, `index.html #route-settings` | R2 |
| `style.css:767-831`, `evesettings.js`, `index.html #route-evesettings` | R3 |
| `style.css:1062-1300`, `skills.js`, `index.html #route-skills` | R4 |
| `style.css:1026-1061`, `firstrun.js`, `index.html #route-firstrun` | R5 |

### Two boundaries worth naming

**`.linkbtn` is shared and does not look it.** It is the Clear / Type…
affordance on eighteen bind rows (R2) and the `Set this up later` control
on first run (R5). F3 says its 4px 6px padding pushes the first-run skip
11 CSS px off the card's left edge. Removing the padding globally would
change eighteen bind rows nobody complained about. S2 owns the class; the
fix has to be scoped to the first-run action row, and R5 executes it.

**`style.css:832-883` looks like Profiles and is Settings.** The
`#eve-bind-warning` / `#eve-binds .row > .lab` / `.bindbtn` block sits
directly after the EVE Settings route block (which ends at `831`), but Bookmarks and Previews
are Settings sections. It is R2's. It also carries an id-specificity
override of `.settings .row > .lab`, which is S2's — round 1 already got
caught by exactly this pair, and the comment at `style.css:875` records
it. R2 must re-check that override after S2 merges.

**`.linkbtn` is scattered across three lanes.** The class body is at
`884-889` (S2), its `:focus-visible` rule shares the shared focus selector
at `244` (S1), and `.linkbtn.danger` sits inside the Skills block at
`1276-1277` (R4). Three lanes can touch this one class. S2 owns any change
to its box model; S1 owns the focus treatment; R4 may change only the
`.danger` colour. Anyone widening the scope of a `.linkbtn` edit past
those bounds has left their lane.

---

# Wave 1 — four shared lanes, all parallel

None of these four touch a file region another one owns. They can start on
the same day. **No screen lane starts until all four have merged.**

## S1 — primitives, chrome, status strip, dialog

**Branch:** `ui/s1-primitives`

**Findings:** Uploader 16, Skills 3 (decision half), Skills 7 (decision
half), Settings 18, F6, X1 / Profiles 9 (policy half), M2 (page half).

**Owns:** `style.css:1-276`, `588-651`, `652-698`, `1301-1317`; `app.js`;
`panel.js:102-262`; `index.html` titlebar, `#statusbar-slot`,
`#dialog-slot`.

**Must not touch:** any `#route-*` markup block, `style.css:277-587`,
`699-1300`, `panel.js:1-101`, any screen JS file, anything in `ui/`.

**What each finding costs here:**

- **F6** is one line. `index.html:630` hard-codes `Ready` as `#status`'s
  initial content, which is what an unconfigured first run displays. It
  needs a word that means "the app is idle" without also reading as "you
  are set up". Cheapest item in the whole round.
- **Skills 3** is the same word at larger scale: `Ready` is a skill-plan
  readiness value, a roster count, a group label, *and* the status strip's
  idle state. S1 owns the strip's vocabulary and settles which meaning
  keeps the word. R4 renames the other side.
- **Uploader 16** is an accent-budget decision, not an edit. DESIGN.md
  allows one accent per screen; the Uploader spends it in five places, two
  decoratively. S1 writes down what `.btn.acc` and the brand rule are for;
  R1 removes the two decorative uses.
- **X1 / Profiles 9** — the disabled style at `style.css:228-229` already
  works, proven by first run's muted `Continue`. What is missing is the
  `disabled` attribute at roughly twelve call sites on three screens. S1
  adds one helper to `app.js` (`WM.setEnabled(el, bool)` or equivalent) so
  the screen lanes have one thing to call instead of three hand-rolled
  variants. **Do not** change `style.css:228-229` — it is correct.
- **Skills 7** is the same shape as Uploader 3: a column header row that
  does not share the inset of the rows it labels. It shows on two screens
  with two different offsets, so the decision — headers align to their
  columns, full stop — is S1's and the edits are R1's and R4's.
- **M2 (page half)** — render the version in the titlebar, dimmed, after
  the `WINGMAN` wordmark. Recommended over the status strip because the
  strip's right side is already `#track` and `#pct` and yields to upload
  progress at narrow widths. S3 supplies the value.
- **Settings 18** — the YouTube terms link is the only blue in the app.
  It needs either a token or a reason to stay an exception.

**Decisions needed before starting:** what the idle status word becomes
(F6 / Skills 3), and whether the terms link gets a token or an exemption.

## S2 — the shared Settings and Profiles row machinery

**Branch:** `ui/s2-settings-rows`

**Findings:** Settings 3, Settings 6, Settings 12, Settings 17, F3
(class half), F4.

**Owns:** `style.css:884-889` (`.linkbtn`), `891-1025`.

**Must not touch:** anything else in `style.css`, any JS, any markup, any
Python. This lane is CSS only, in one contiguous block.

**Why it is one lane and not two:** `index.html:407` puts
`class="settings"` on the Profiles route as well, so every rule in
`891-978` renders on two screens. Round 1 hit this exact trap — Settings 1
and Profiles 6 both wanted `style.css:739-746` and would have shipped
incompatible answers.

**What each finding costs here:**

- **Settings 12** is the anchor. Control rows begin at three different
  left edges depending on the section, because some rows have a `.lab`,
  some have a `.check` wrapper, and some have neither. One answer for all
  three, applied once.
- **Settings 3 and F4** are the same rule: hint text inherits the row's
  left edge rather than sitting under the control it explains. Settings 3
  is the checkbox case, F4 the field-plus-two-buttons case. Fix them
  together or the second one re-opens the first.
- **Settings 6** — the 118px right-aligned `.lab` column followed by a
  checkbox label reads as one broken sentence. Interacts with Settings 12;
  same lane by design.
- **Settings 17** — `.pill`, `.led` and a bare dot are three shapes for
  one concept. Pick one, or give each a stated job.
- **F3 (class half)** — `.linkbtn`'s `padding: 4px 6px`. S2 decides
  whether the padding stays and first run compensates, or the padding goes
  and bind rows compensate. **It must not silently become "remove the
  padding"** — see "Two boundaries worth naming" above.

**Handoffs out:** R2 re-checks `#eve-binds .row > .lab` and its
`max-width: 720px` block after this merges (Settings 11). R3 re-checks the
Profiles cards, which inherit every rule here. R5 executes F3.

## S3 — Python, bridge, copy, tray, version, startup

**Branch:** `ui/s3-backend`

**Findings:** M1, M2 (source half), M3 (backend half), Profiles 3,
Profiles 4 (bridge half), Uploader 8 (payload half), Uploader 12,
Settings 1, Settings 13, Settings 14 (guard half), Skills 8.

**Owns:** `ui/api.py`, `ui/copy.py`, `__main__.py`, `__init__.py`,
`ui/window.py`, `pyproject.toml`, and `tests/` wherever those are
asserted.

**Must not touch:** anything under `web/`. Every UI-visible consequence of
this lane is picked up by a screen lane in wave 2.

**What each finding costs here:**

- **M1** is one string. `__main__.py:200` reads `"Open uploader"`; lines
  202 and 213 already say `FlyGD Wingman`. Right name twice, wrong name
  once, in the only menu most users ever see.
- **M2 (source half)** — `__version__ = "3.2.1"` at `__init__.py:1`, and
  `pyproject.toml:15` carries the same string by hand. Expose the value to
  the page through the existing bridge, and single-source the two while
  you are there or they will drift.
- **M3 (backend half)** is the largest item in this lane and the only one
  that writes outside the app's own config. Start-on-login on Windows is
  either a `.lnk` in the Startup folder or an `HKCU\...\Run` value; both
  need a get, a set, and a "what if the user removed it by hand" answer.
  It must also start hidden — the app is a tray app and a login that
  raises a window every boot is worse than no setting.
- **Profiles 4 (bridge half)** — the walkthrough's most-corroborated
  finding, now at three instances. First run detects OBS's folder, Folders
  detects two more, and Profiles asks the user to type the path to the EVE
  directory the product is named for. This lane adds the detection; R3
  adds the button.
- **Uploader 12** — the empty state names a folder that is not the
  configured one. Cause was never confirmed from the screenshots; this
  lane confirms or disproves it in `api.py` before anyone edits the page.
- **Uploader 8** — the combat-log checkbox has no true second state for
  this user, and the maintainer has decided it goes. This lane makes logs
  unconditional in the payload; R1 removes the control.
- **Settings 1** — "precondition not met" is rendered two opposite ways in
  one release. One answer, in `copy.py`.
- **Settings 13** needs a decision before it can start: making YouTube
  category a `<select>` changes `set_category`, which currently validates
  a free string.
- **Settings 14 (guard half)** — `Show` and `Remove` act on a webhook that
  is not configured. Backend refuses; R2 disables the buttons.
- **Skills 8** — two time vocabularies in one app. Copy-level, cheap.

**Decisions needed before starting:** Settings 13 (`<select>` or not), and
M3's mechanism (Startup shortcut vs `Run` key).

## S4 — documentation corrections

**Branch:** `ui/s4-docs`

**Findings:** C1 / X2, X2b, F1's follow-up, and the three discarded
round-1 findings.

**Owns:** `DESIGN.md`, `PRODUCT.md`, `docs/smoke-checklist.md`,
`docs/ui-critique.md`.

**Must not touch:** any code.

Smallest lane, and the only one that can be done in an hour. It exists as
its own lane because it conflicts with nothing.

- **C1 / X2** — `DESIGN.md` states that `MIN_WIDTH` is "**840 physical
  pixels**, not logical". Measured at 200% scaling, the floor capture is
  839×621 CSS, which matches `MIN_WIDTH = 840` / `MIN_HEIGHT = 625`
  exactly. The minimum resolves in **logical** units and the CSS floor is
  840×625 at every scaling. `PRODUCT.md:137` repeats the same error
  ("Minimum 840x625 **physical** pixels — 560 CSS px at 150% scaling")
  and needs the same correction.
- **Consequence for round 1:** critique findings Uploader 1, Settings 1
  and Skills 2 were arithmetic against a viewport that cannot exist. Mark
  them discarded in `docs/ui-critique.md` with the reason, so nobody
  re-derives them. `folder-narrow.png` is the counter-evidence.
- **X2b — leave unresolved, deliberately.** `DESIGN.md` reports that five
  destinations "needed 686px and clipped the close button off the right
  edge at 125%", which is impossible if the floor is 840 CSS. This is not
  a claim that `#38` was wrong; PRODUCT.md's destination test stands on
  its own. But the recorded *reason* is the tool future contributors will
  reach for, and it does not add up. Record it as an open question with
  both measurements beside each other. The maintainer has agreed this
  stays unresolved rather than being guessed at.
- **F1 follow-up** — note in `docs/smoke-checklist.md`, beside the
  first-run items, that the launcher's target tree is part of what the
  check depends on. The launcher itself was fixed on 2026-08-25;
  `run-first-run.bat` had been running a worktree six commits behind main,
  so every hand verification of `#49` through it verified the screen `#49`
  replaced.

---

# Wave 2 — five screen lanes, all parallel

Start only after S1, S2, S3 and S4 have all merged. Each lane owns one
route's markup, JS and CSS block and touches nothing else.

Every screen lane inherits the same three standing items:

1. **X1 execution** — set the `disabled` attribute on this route's accent
   buttons, using S1's helper. Do not restyle.
2. **Re-check against S2** — this route's rows may have moved.
3. **Hand pass** against `docs/smoke-checklist.md`. Nothing in the
   repository executes the page.

## R1 — Uploader

**Branch:** `ui/r1-uploader` · **Owns:** `style.css:277-587`, `list.js`,
`panel.js:1-101`, `index.html #route-main`

**Findings:** 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17.

Largest screen lane, and the route the maintainer uses constantly. Order
it by what a real session hits:

- **15** first. Two adjacent checkboxes are too close to distinguish by
  aim, and the maintainer has actually hit the wrong one — meant Stitch,
  hit logs. **8's removal (from S3) deletes one of the two**, which may
  resolve 15 outright. Check before doing separate work.
- **9 and 11** are the two round-1 findings that survived the floor
  correction and are now confirmed at the genuine 840×625 minimum: the
  primary button falls below the fold, and the Filename column truncates
  away the only part that identifies the row.
- **2** — the card headed UPLOAD does not contain the Upload button.
- **1, 16's execution** — the loudest element on the screen cannot act,
  and two of five accent uses are decorative.
- **3, 4** — headers 16px right of their data, and `Modified`
  right-aligned over a left-aligned column. S1 settled the rule.
- **5, 10** — `Length` and `Link` empty on all 25 rows, and `Length` is
  not blank but zero. 10 is probably a regression; confirm before
  designing around it.
- **13, 14** — the panel does not know the list is empty, and the empty
  pane is half-centred. First run proves the app can centre a card, so 14
  is an omission and not a layout limit.
- **6, 7, 17** — `worth trying`: duplicate fact in two columns, checkboxes
  in the button's approach corridor, and panel order that does not match
  frequency of use.

**Depends on S3 for:** 8 (payload), 12 (folder). Do not start either until
S3's answer is in.

## R2 — Settings

**Branch:** `ui/r2-settings` · **Owns:** `style.css:699-766`, `832-883`,
`settings.js`, `bookmarks.js`, `previews.js`, `index.html #route-settings`

**Findings:** 2, 4, 5, 7, 8, 9, 10, 11, 15, 16, 19, plus Settings 14's UI
half and M3's UI half.

- **11** first, and re-check `#eve-binds .row > .lab` against S2 before
  touching it. ~600px between a keybind's action name and its binding,
  eighteen times over.
- **19 and 9** are the same control: `Import from an existing helper…` is
  a dead control in a primary position that also never says what a helper
  is. The maintainer's use report is unambiguous — nobody uses it. The
  cheapest fix is removal, not clarification.
- **M3 (UI half)** — one row in the General section, wired to S3's
  get/set. Decide where it sits relative to the existing General rows.
- **14 (UI half)** — disable `Show` and `Remove` when no webhook is set.
- **2** — the only accent on Previews marks a sub-option of a feature that
  is switched off.
- **4, 16** — different left edges inside one card; the `EVE gamelogs`
  path cut mid-word at a comfortable width.
- **5, 7, 8, 10, 15** — `worth trying`: durable explanation mixed with
  current state, the distinguishing word never coming first, `Not running`
  restating the box above it, density disagreeing within a section, and
  the app's only lower-case status string.

**Depends on S3 for:** 13 (category control), 14 (guard), M3 (backend).

**Explicitly out of scope:** the Previews alert functionality gap. The
maintainer has flagged it as a future feature branch, not a fix.

## R3 — Profiles

**Branch:** `ui/r3-profiles` · **Owns:** `style.css:767-831`,
`evesettings.js`, `index.html #route-evesettings`

**Findings:** 1, 2, 5, 6, 7, 8, plus Profiles 4's button.

- **4's button** is the headline. S3 supplies detection; this lane adds
  the control and removes the requirement to know an EVE path by hand.
- **1 and 2** are the safety pair, and should be designed together. At the
  moment of the irreversible action the hazard warning is off-screen, and
  the list is a picking surface being used as a verification surface.
  Profiles 3 (from S3) puts the character count in the confirm line, which
  is half of 1's answer; this lane owns the other half.
- **5** — the empty state answers a question that cannot be asked yet.
- **6, 7, 8** — `worth trying`: empty dropdowns rendering identically to
  working ones, `Change…` as the quietest thing on its own row, and a
  screen named Profiles whose cards are named Settings.

**Re-check against S2 carefully.** Profiles renders `.settings`; more of
this route's appearance comes from S2's block than from its own.

**Explicitly out of scope:** creating a new profile folder and copying
settings into it. That is a feature the maintainer wants and this round
does not design. Recorded in the walkthrough under "Decision needed".

## R4 — Skills

**Branch:** `ui/r4-skills` · **Owns:** `style.css:1062-1300`, `skills.js`,
`index.html #route-skills`

**Findings:** 1, 2, 4, 5, 6, 9, plus Skills 3's roster half and Skills 7's
execution.

- **1 and 2 together, and read C2 first.** `Unknown skill` is correct —
  it means the character has never injected the skill — but "unknown"
  attaches to the speaker, not the subject, so it reads as an app failure.
  Worse, the semantics are inverted in colour: `Missing` (trained but
  below the required level) is red, `Unknown` (never injected, the more
  severe state) is dim grey. Renaming to `Not trained` fixes the reading;
  the colour inversion is the separate half and the more important one.
- **4** — `2 characters · 0 ready` is contradicted four rows below it.
- **6** — a ~1000px void between each row's subject and its answer.
- **5, and read C3 first.** The outstanding-requirements filter already
  exists at `skills.js:607-615` and is not a control. The surviving
  finding is only that outstanding requirements are not ordered by state.
- **9** — `worth trying`: the filter-character box is the second most
  prominent thing on the screen and the maintainer has never used it.
- **3's roster half** — whichever side of `Ready` S1 did not keep.

## R5 — First run

**Branch:** `ui/r5-firstrun` · **Owns:** `style.css:1026-1061`,
`firstrun.js`, `index.html #route-firstrun`

**Findings:** F2, F5, plus F3's execution.

Smallest lane, with the round's most interesting single question in it.

- **F2** is the one finding on this screen with product weight behind it.
  `Choose your recording folder` is uploader-scoped; the paragraph under
  it is product-scoped. The eye lands on the largest text first, so the
  experienced sequence is *this is a folder chooser*, then *actually it is
  a toolkit* — which is the framing PRODUCT.md says is out of date and
  should not be used to decide anything, sitting in the application's
  first sentence at its largest type size. `#49` fixed the prose and left
  the heading. **This needs the maintainer's answer before implementation:
  should the h1 name the product or the task?**
- **F5** follows from F2. If the heading changes, the "what is this"
  paragraph may not need body length and the two-paragraph block becomes
  one.
- **F3's execution** — scoped to the first-run action row, per S2's
  decision. Eleven CSS px.

**Do not change** the prominence of `Set this up later`. It is the
quietest control on a screen whose prose recommends it, and that is a
recorded deliberate decision — the markup carries the comment "skipping is
the quiet way out of the screen, and Continue is the one accent per
screen", and it follows DESIGN.md's one-accent rule. The walkthrough
records the tension without calling it a fault. It should not be changed
on aesthetic grounds alone, because the reason it looks that way is
written down.

---

## Deferred, with reasons

| Item | Why it is not in a lane |
|---|---|
| Previews alert functionality | A feature branch, not a fix. Maintainer's call. |
| Create a profile folder and copy settings into it | Same. Wanted, not designed. |
| `Notifications` has no third option | Carried over from round 1, still open, still deferred. |
| The live-upload capture | Never taken; the sandbox lacks credentials. |
| X2b, the `#38` reconciliation | Needs a person to reproduce or rule out. S4 records it as open. |
| Internal identifiers still say `gesture` and `alert_bookmarks` | Known and tracked outside this round. |
| The status strip shows SIG/ROOT/NEXT on every route | Known and tracked outside this round. |

## Counts

| Lane | Findings | Files | Blocking |
|---|---|---|---|
| S1 | 7 | 4 + markup | all of wave 2 |
| S2 | 6 | 1 | all of wave 2 |
| S3 | 11 | 6 | all of wave 2 |
| S4 | 4 | 4 docs | all of wave 2 |
| R1 | 14 + 1 standing | 4 | — |
| R2 | 13 + 1 standing | 6 | — |
| R3 | 7 + 1 standing | 3 | — |
| R4 | 8 | 3 | — |
| R5 | 3 | 3 | — |

Wave 1 is 28 findings across four non-overlapping lanes. Wave 2 is 45
across five. The overlap in the totals is the findings that appear in both
waves — a decision in wave 1, execution in wave 2.
