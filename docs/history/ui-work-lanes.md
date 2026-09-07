# UI work lanes — decomposing `docs/ui-critique.md`

`docs/ui-critique.md` raises 25 findings across five screens. This document
sorts them into one shared lane and five screen lanes so that, after the
shared lane merges, the five can run in parallel sessions without touching
the same lines.

Nothing here is implemented. This is a routing document.

**Paths.** The critique uses shorthand (`index.html`, `panel.js`,
`ui/api.py`). The real paths are `wingman/web/*` and
`wingman/ui/*`, and every ownership list below uses them.

## The rule that decides the split

A file section is **shared** if two screens can be editing it in the same
week. Shared sections are lane 0's alone; screen lanes get a hard "must not
touch" on them, because a `.card` tweak and a `.row` tweak from two
branches conflict on adjacent lines and merge into a layout neither branch
tested.

| Region | Owner |
|---|---|
| `style.css:1-276` — tokens, titlebar, `.route`, `.card`, `.row`, `.field`, `.btn`, `.check`, `.radio`, focus, scrollbar | lane 0 |
| `style.css:496-606` — status strip, dialog layer | lane 0 |
| **`style.css:725-819`** — `.linkbtn`, `.settings`, `.settings .row > .lab/.field/.radio`, `.pill`, `.led`, `.radio`/`.ring`, `#f-webhook`, `.settings .toggle`, `.field-msg` | **lane 0 — see "The mis-drawn boundary" below** |
| `style.css:1009-1025` — `prefers-reduced-motion` block | lane 0 |
| `web/app.js` — routing, sections, bridge registration, EVE gate | lane 0 |
| `web/panel.js:66-226` — status strip + dialog layer (below the `// ---- status strip` banner at `panel.js:66`) | lane 0 |
| `ui/api.py`, `ui/copy.py` | lane 0 |
| `index.html` titlebar, `#statusbar-slot`, `#dialog-slot` | lane 0 |
| `style.css:277-495`, `list.js`, `panel.js:1-65`, `index.html #route-main` | lane 1 |
| `style.css:607-668`, `style.css:691-724` (`#eve-bind-warning`, `#eve-binds`, `.bindbtn`), `settings.js`, `bookmarks.js`, `previews.js`, `index.html #route-settings` | lane 2 |
| `style.css:669-690` (`#route-evesettings`, `#es-*`), `evesettings.js`, `index.html #route-evesettings` | lane 3 |
| `style.css:837-1008`, `skills.js`, `index.html #route-skills` | lane 4 |
| `style.css:820-836`, `firstrun.js`, `index.html #route-firstrun` | lane 5 |

### The mis-drawn boundary

The prompt's map gives Profiles `style.css:669-819` and Settings
`style.css:607-668`. That is wrong in a way that would have produced silent
conflicts, so it is corrected above and called out here.

Only `style.css:675-690` is Profiles-local (`#route-evesettings`,
`#es-targets`, `#es-backups`, `#es-warning`). From `style.css:691` the block
turns into Settings machinery and then into cross-screen machinery:

- `691-724` — `#eve-bind-warning`, `#eve-binds .row > .lab`, `.bindbtn`.
  Bookmarks and Previews only. This belongs to **lane 2**, not lane 3.
- `725-819` — `.linkbtn`, `.settings` (the 620px wrapper), the 118px
  `.settings .row > .lab` column, `.settings .row > .field`, `.pill`,
  `.led`, `.radio`/`.ring`, `#f-webhook`, `.settings .toggle`,
  `.field-msg`. `index.html:357` puts `class="settings"` on the Profiles
  route too, so **every one of these rules is rendered on two screens.**
  This is **lane 0**.

Settings finding 1 and Profiles finding 6 both want to change
`style.css:739-746`. Lane 2 and lane 3 would have shipped incompatible
answers to the same question. Lane 0 answers it once.

---

## Lane 0 — shared. Runs alone, first. Nothing else starts until it merges.

**Branch:** `ui/lane0-shared`

**Findings:** Uploader 2 (Python half), Uploader 5, Profiles 3, Profiles 5
(payload half), Settings 1, Settings 2 (landing half), Settings 3, Settings 6,
First run 1. Settings 5 is deferred — see Deferred.

**Owns:**

```
wingman/web/style.css      1-276, 496-606, 725-819, 1009-1025
wingman/web/app.js         all
wingman/web/panel.js       66-226 (status strip + dialog layer)
wingman/ui/api.py          all
wingman/ui/copy.py         all
wingman/web/index.html     titlebar, #statusbar-slot, #dialog-slot,
                                        the `active` classes on the Settings rail
                                        and its panes (index.html:120, :132)
tests/                                  wherever copy.py or api.py behaviour is asserted
docs/smoke-checklist.md                 :241-245 and :1383-1385 (both measure logical
                                        px where the finding is about CSS px)
```

**Must not touch:** `list.js`, `settings.js`, `bookmarks.js`, `previews.js`,
`evesettings.js`, `skills.js`, `firstrun.js`, `panel.js:1-65`, any
`#route-*` markup block, `style.css:277-495`, `607-724`, `669-690`,
`820-1008`.

**What each finding costs here:**

- **Settings 1** (rows starve at 560px) is the anchor. It is a change to
  `.settings .row`'s wrap behaviour or the 118px label column, and it lands
  on Settings *and* Profiles at once. Everything else in lane 0 is smaller.
- **Settings 2 + 6** move together: `app.js:143`'s `current_section` and the
  two `active` classes in markup are one fact written in three places. Fixing
  the landing section without fixing the initial value re-creates finding 6
  as a live defect instead of a latent one.
- **Uploader 2** — the *page* half is lane 1 (the payload already carries
  `discord_webhook`; `get_settings` returns `settings` wholesale at
  `ui/api.py:1068-1087` and `panel.js:112` already re-dispatches it as
  `wm:settings`). Lane 0 owns only the **confirm line** in `ui/copy.py:96-97`,
  which must stop promising a Discord post when no webhook is configured.
- **Uploader 5** — one new bridge method for "open the recordings folder"
  (`Api.open_path` exists but is keyed to a row). Lane 1 adds the button.
- **Profiles 3** — copy confirmation moves from `ui/api.py:2119-2123` into
  `ui/copy.py`, counts characters not `file(s)`, and repeats the EVE-running
  hazard the pill already shows.
- **Profiles 5** — put `auto_keep` on the backups payload so lane 3 can say
  "the last 10 are kept" without typing the number into the page.
- **Settings 3** — only if it becomes a `<select>`; `set_category`
  (`ui/api.py:1234`) currently validates a free string. Needs a decision.
- **First run 1** — the largest single item. "Skipped" has to be a state
  Python persists, or `_push_first_run_when_ready` (`ui/api.py:1621`) shows
  the screen again next launch. Needs a decision.

**Decisions needed before starting:**

1. **First run 1 — what does "skip" persist?** A new settings key
   (`first_run_skipped`)? A sentinel `recording_dir`? This is persisted data
   and a migration surface; it is the one item in lane 0 that should not be
   guessed at. Blocks: the skip link, `main`'s tolerance of no folder, and
   `_push_first_run_when_ready`.
2. **Settings 3 — select or wording?** A select removes the YouTube API
   concept entirely but changes `set_category`'s contract and what is stored
   in `settings.json` for existing installs. Wording-only is zero risk and
   leaves the magic number. If the answer is "wording only", this finding
   drops out of lane 0 and into lane 2.
3. **Settings 1 — which lever?** Wrapping trailing buttons below the field
   under a width threshold, or letting the 118px label column collapse. Both
   change Profiles' appearance as a side effect. Worth showing the maintainer
   two screenshots at 560px before committing, since this is the rule the two
   screens share.

**Smoke items before PR** (`docs/smoke-checklist.md`):

- `:187-191` Display scaling at 100 / 125 / 150 / 200%.
- `:192-198` Nothing clipped at the minimum window size at 150%.
- `:185-186` Machine text is monospace (the `.settings` rules move).
- `:750-782` Dialogs and confirmations, whole section — lane 0 owns the
  dialog layer and two confirm strings.
- `:640-660` Upload confirms before publishing anything — the Logs line
  changes.
- `:823-858` The Settings rail, whole section — the landing section moves.
- `:80-109` First run, whole section, plus the LOAD-BEARING first-run item
  under Settings › Folder dialogs (`:397-446`).
- `:1214-1256` Profiles — the copy confirmation is re-worded.

**Size:** Large. Nine findings, four files, two persisted-state questions,
and the widest smoke surface in the document. This is the lane most likely
to want splitting into two PRs (`api.py`/`copy.py` first, then the CSS
primitives) — but both halves still merge before any screen lane starts.

---

## Lane 1 — Uploader (`#route-main`)

**Branch:** `ui/lane1-uploader`

**Findings:** Uploader 1, 2 (page half), 3, 4, 5 (button only).

**Owns:**

```
wingman/web/style.css      277-495
wingman/web/list.js        all
wingman/web/panel.js       1-65 ONLY (above the status-strip banner)
wingman/web/index.html     #route-main block (list, footer, #panel-slot)
docs/smoke-checklist.md                 :241-245 if lane 0 did not already fix the width
```

**Must not touch:** `panel.js:66-226`, `style.css` outside 277-495,
`app.js`, `ui/`, any other `#route-*`.

**Notes:**

- Finding 1 is the one that matters: a 472px grid in a 204px pane at 150%
  scaling. The levers — `.panel { width: 320px }` at `style.css:452-455` and
  the grid template at `style.css:310` — are both inside this lane's range.
- Finding 2's page half: gate the checkbox on `discord_webhook` from the
  `wm:settings` event. No Python change needed; lane 0 handles the confirm
  string. **This finding is split across two lanes — lane 1 must land after
  lane 0 or the checkbox and the dialog will disagree.**
- Finding 4: the payload already carries `settings.recording_dir`, so naming
  the folder in the empty state is page-side. Do **not** move the string into
  `ui/copy.py` — see Deferred.

**Decisions needed:** None, if lane 0 has landed. Finding 1 has several valid
answers (media query stacking the panel below the list, a shrinkable panel, or
deliberate column shedding) and all are local; pick one and say which in the PR.

**Smoke items before PR:** `:199-263` The list, whole section (rows, sort,
keyboard, context menu, double-click) — the grid template changes.
`:241-245` at 100 / 125 / 150%, not just 840 logical. `:187-198` scaling and
minimum size. `:100-109` the ffmpeg / Stitch label wraps in the panel.
`:640-660` upload confirm, for the combat-log checkbox half.

**Size:** Medium-large. Finding 1 is a real layout decision; 3, 4, 5 are each
a few lines.

---

## Lane 2 — Settings (`#route-settings`)

**Branch:** `ui/lane2-settings`

**Findings:** Settings 4. Settings 3 as well, if the decision is
"wording only". Settings 2's rail *ordering* is here; its landing-section
half is lane 0's.

**Owns:**

```
wingman/web/style.css      607-668, 691-724
wingman/web/settings.js    all
wingman/web/bookmarks.js   all
wingman/web/previews.js    all
wingman/web/index.html     #route-settings block, rail item ORDER
                                        (not the `active` classes — lane 0)
```

**Must not touch:** `style.css:725-819` (the `.settings .row` family — lane 0,
and shared with Profiles), `app.js:143`, `ui/api.py`.

**Notes:** This is the thinnest lane after lane 0 takes finding 1 and the
landing section. Finding 4 is heading text: stop repeating the rail name, and
distinguish the two cards both headed "Keybinds" ("EVE-focused keybinds" /
"Global keybinds") — `previews.js:22-31` already computes the collision those
headings should be naming.

**Decisions needed:** Whether the rail *order* changes at all, given lane 0
already moves the landing section. Reordering and re-landing are two answers
to the same complaint; doing both may be one too many.

**Smoke items before PR:** `:823-858` The Settings rail, whole section
(the eight-entry count line included). `:860-1026` EVE bookmark hotkeys, if
`#eve-binds` CSS moved. `:1136-1213` EVE preview hotkeys. `:305-396` Settings,
whole section.

**Size:** Small.

---

## Lane 3 — Profiles (`#route-evesettings`)

**Branch:** `ui/lane3-profiles`

**Findings:** Profiles 1, 2, 4, 5 (page half), 6.

**Owns:**

```
wingman/web/style.css      669-690 ONLY
wingman/web/evesettings.js all
wingman/web/index.html     #route-evesettings block
```

**Must not touch:** `style.css:691-819` — **this is the trap.** The 118px
label column, `.pill`, `.field`, `.linkbtn` and `.field-msg` all render on
this screen but are lane 0's. Finding 6 wants `.mono` and `span.field` on
the path — applying the *existing* classes is fine and is this lane's; *changing
what those classes do* is not.

**Notes:**

- Finding 1 (collapse the setup card to a summary line) is the largest item
  and is genuinely local — it is markup order plus a collapsed/expanded state
  in `evesettings.js`.
- Finding 2 is one text node in the empty `<span class="lab">` at
  `index.html:381-391`.
- Finding 4 needs `.danger` on Delete — the treatment already exists at
  `style.css:1004-1007`, inside **lane 4's** range. Reference it; do not edit
  it. If it needs generalising, that is a lane 0 change.
- Finding 5's page half reads `auto_keep` off the payload lane 0 adds.

**Decisions needed:** Finding 1 — does the collapsed folder card stay
collapsed across visits, or re-expand when the root is unset? Local and
reversible; decide in the PR unless the maintainer has a view.

**Smoke items before PR:** `:1214-1256` Profiles, whole section — especially
the eleven-copies `auto_keep` item at `:1252-1254` (finding 5) and the
EVE-running copy refusal at `:1236-1238` (finding 3's pill, lane 0's dialog).
`:185-186` monospace (finding 6). `:187-198` scaling and minimum size
(finding 6's overflow claim is `needs the running app`).

**Size:** Medium.

---

## Lane 4 — Skills (`#route-skills`)

**Branch:** `ui/lane4-skills`

**Findings:** Skills 1, 2, 3, 4, 5.

**Owns:**

```
wingman/web/style.css      837-1008
wingman/web/skills.js      all
wingman/web/index.html     #route-skills block
docs/smoke-checklist.md                 :1383-1385 (measures 840 logical, not 560 CSS)
```

**Must not touch:** `style.css:1009-1025` (reduced motion — lane 0; it sits
directly below this lane's range, so a careless append lands in it),
`app.js`, `ui/api.py`.

**Notes:** The cleanest lane. Every finding is inside `skills.js` or this
screen's CSS, and no other screen imports `.skills-*` or `.rail-plan`. Finding
2 (the 214px rail at 38% of a 560px window) is the one with a real layout
decision; 1, 3, 4, 5 are labels and strings.

**Decisions needed:** None.

**Smoke items before PR:** `:1363-1440` The Skills page itself, whole
section — particularly `:1383-1385` (the floor measurement finding 2 says is
taken at the wrong width; fix the item as part of the lane) and the counts-line
item at `:1374-1378` (finding 1). `:1441-1453` frozen build if the rail
structure changes.

**Size:** Medium.

---

## Lane 5 — First run (`#route-firstrun`)

**Branch:** `ui/lane5-firstrun`

**Findings:** First run 2, 3, 4, 5. Finding 1 is lane 0's.

**Owns:**

```
wingman/web/style.css      820-836
wingman/web/firstrun.js    all
wingman/web/index.html     #route-firstrun block
```

**Must not touch:** `app.js:110-111` (the route's nav gating — lane 0),
`ui/api.py:1621`.

**Notes:** Findings 3 and 4 are one piece of work: `firstrun.js:25-29` needs
an else branch, and `firstrun-note` needs a precedence rule once it is
carrying three messages instead of two. `settings.js:132-137` already has the
sentence to copy. Finding 2's one-sentence framing should mention the EVE half
— it is what makes lane 0's skip link legible rather than arbitrary, so write
the two to agree even though they ship in different lanes.

**Decisions needed:** None. Finding 2's exact sentence is worth showing the
maintainer, since it is the first thing the app ever says, but it does not
block starting.

**Smoke items before PR:** `:80-109` First run, whole section — including
the "how to actually get here" recipe at `:84-93`, which is the only way to
reach this screen on a machine with OBS installed. `:397-446` Settings ›
Folder dialogs, for the LOAD-BEARING first-run item. `:187-191` scaling.

**Size:** Small.

---

## Deferred

- **Settings 5 — Notifications has no "neither" option.** Blocked on a
  product decision, and the change is not confined to a radio: `set_notify_mode`
  (`ui/api.py:1228`) accepts a fixed set and the watcher's announcement path
  reads it, so "silent" is a third behaviour in the watcher, not a third value
  in the page. The critique's own confidence is `needs the running app` for
  whether users want it. Holding lane 0 — which everything else depends on —
  for a preference question is the wrong trade. Split it out as its own
  post-lane-0 shared PR if the maintainer wants it.
- **Uploader 4's copy migration.** The critique notes the empty-state string
  lives in HTML rather than `ui/copy.py`, unlike the rest of the app's prose.
  Moving it is a defensible consistency fix and an entirely separate concern
  from naming the folder. Naming the folder is possible page-side today.
  Migrating the string means a new push or a new payload key for a sentence
  that is currently static — do the finding, defer the migration.
- **Profiles 1's fold measurement** and **Skills 2's truncation claim** are
  not deferred, but both carry `needs the running app`. Run the relevant smoke
  item at 150% *before* choosing a fix, not after — the critique's arithmetic
  says the problem exists; only the running app says how much of it the user
  sees.
- **Uploader 1's smoke item.** `docs/smoke-checklist.md:241-245` tests 840
  logical px, which is the one width where the layout is fine. Whoever fixes
  the finding must fix the item, or the next round re-passes a check that
  never caught it. The same is true of `:1383-1385` for Skills. Neither is
  optional; both are named in their lanes above.

---

## Dependency line

```
lane 0 (shared)  ──merge──┬── lane 1  Uploader
                          ├── lane 2  Settings
                          ├── lane 3  Profiles
                          ├── lane 4  Skills
                          └── lane 5  First run
```

Lanes 1-5 have no dependency on each other and may run in any order or all at
once. Lane 0 has no dependency on any of them.

## Findings that look screen-local and are not

These are the ones that turn into merge conflicts if a lane takes them at
face value.

1. **Settings 1 and Profiles 6 are the same finding.** Settings 1 wants
   `.settings .row`'s label column to stop starving the field; Profiles 6
   wants a path to join that label column and take `span.field`'s ellipsis.
   Both edit `style.css:739-746`. The critique marks Settings 1 `shared` and
   Profiles 6 `screen-local`, which is right per-finding and wrong per-file:
   the *lever* is shared even though Profiles' use of it is not. Lane 0 sets
   the rule; lane 3 applies the classes.
2. **Settings 2 is two findings wearing one number.** Reordering the rail is
   markup. Changing which section Settings *lands* on is `app.js:143` plus
   two `active` classes, and doing only the markup half creates finding 6 as a
   live defect. Split at the lane boundary, and note in both PRs.
3. **Uploader 2 splits down the middle.** The checkbox default is markup, the
   gate is a payload read the page can already do, and the confirm line is
   `ui/copy.py`. Lane 1 doing its half alone produces a checkbox that greys out
   and a dialog that still promises the post. Sequence matters.
4. **Uploader 4 needs a path the page has but does not read.** `get_settings`
   returns `settings.recording_dir` and `panel.js:112` re-dispatches it as
   `wm:settings`, so `list.js` can subscribe. That is lane 1's work, but only
   because lane 0's payload happens to already carry it — verify before
   starting rather than discovering it mid-PR.
5. **Profiles 4 references a `.danger` treatment inside lane 4's CSS range**
   (`style.css:1004-1007`, the Skills block). Using the class is free; editing
   or generalising it crosses into lane 4 and should be escalated to lane 0
   instead of done in either screen lane.
6. **Skills 2 and Uploader 1 are the same class of bug** — a fixed-width
   sidebar measured at 100% scaling — and both have a smoke item that
   measures logical rather than CSS pixels. The fixes are independent; the
   *lesson* is shared, and whichever lane lands second should check the other
   used the same floor (560 CSS px, per `docs/smoke-checklist.md:1020-1022`).
