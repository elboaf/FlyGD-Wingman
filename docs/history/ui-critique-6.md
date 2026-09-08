# UI critique, round 6 — from the nine-screen capture of 2026-08-26

Every screen of the running app, shot by `/screenshots` in one pass:
`tmp/screens/20260826T235157Z/`, nine PNGs plus `manifest.json`. Baseline
is `main` at **4.0.0** (`e2172cd`), tree dirty with the round-5 docs only.
Viewport **1015x633 CSS** — the real default window, not the 840x625 floor.

Unlike rounds 3 and 5, this review worked from captures of the **real app
against real state**: 16 recordings, 37 characters, 10 plans, a connected
Google account, and a bookmark engine that was genuinely stopped. Several
findings below exist only because the state was real — the alert collision
in particular is user configuration, not a default, and no synthetic
fixture would have produced it.

## Method, and one thing that went wrong

Two assessments were run in isolation, neither able to see the other:

- **A — design review.** Read all nine captures plus `PRODUCT.md`,
  `DESIGN.md` and `wingman/web/`. Scored 26/40 on Nielsen.
- **B — deterministic detection.** `npx impeccable --json wingman/web`
  (17 findings, exit 2) plus a hand-written grep scan for the patterns the
  CLI does not cover.

**Both reports were lost on their first delivery** and arrived only after
being asked for a second time — after the combined report had already been
written from a third, inline pass. The scores and several findings below
are therefore *corrections* to a report that had already been published.
That is recorded here because the failure mode is not rare: a subagent can
report idle with no findings, and the synthesis will quietly proceed
without it.

## The diagnosis

Round 5's diagnosis was *internal values reach the page unformatted*.
Round 6's is narrower and worse:

**Three subsystems mint a vocabulary for a hazard, then do not use it at
the moment the hazard occurs.**

| Subsystem | Vocabulary it minted | Where it is not used |
|---|---|---|
| Dialogs | `.btn.danger`, "the app's one destructive treatment" (`style.css:650`) | `panel.js:371` — every confirm's OK is `.btn acc` |
| Alerts | five well-separated colours, chosen *because* "nothing ever told you" (`alerts.js:62`) | no check that two events share one |
| Keybinds | `.bindbtn.clash` marks two binds on one key | the higher-stakes surface has no equivalent |

Each of the three has the reasoning written into the source. Each stops one
step short of applying it. This is not three copy problems and it is not
taste; it is the same omission three times.

## Findings

Severity is P0 (ship-blocking for trust) to P3 (polish). **Verified** means
the claim was checked against source or measured from the capture, not
taken from an assessment's word.

### P0-1 — the destructive confirm is styled as the encouraged action

`panel.js:371`:

```js
// Upload is the app's only irreversible action, so the accent stays on
// the affirming button of a confirm and on nothing else in the dialog.
btnOk.className = isConfirm ? 'btn acc' : 'btn';
```

The premise is false. Deleting a recording and overwriting 34 characters'
EVE settings are both irreversible, and `PRODUCT.md` calls the settings
hazard a hard line after a test once destroyed three characters' settings.

`.btn.danger` exists and is used at `index.html:112, 449, 667` and
`skills.js:1139, 1151` — never in the dialog layer. So `09-dialog.png`
shows a red `Delete selected` trigger opening a dialog whose `Confirm` is
brand-purple *and* auto-focused (`panel.js:374`), carrying the lilac focus
ring on top. The colour system inverts at the exact moment stakes peak.

**Verified.** The comment is the reason the bug exists and must be
corrected with it.

### P1-1 — two alerts can share a colour and a sound, silently

`05-settings-alerts.png`: Combat and Decloak are both `#4dd2ff` and both
`Notify`. Indistinguishable on the only two channels an alert has.

Defaults ship distinct (`#ff4d4d` / `#ffd24d` / `#4dd2ff`), so this is a
configuration the app accepted without comment. `alerts.js:62-68` narrowed
16.7M colours to five *specifically* because:

> Two similar purples silently destroy the one thing that makes three
> alerts distinguishable, and nothing ever told you.

Two *identical* colours are still reachable in five clicks, and it still
never tells you. `PRODUCT.md` makes trust the feature's load-bearing
property: a wrong alert costs more than a missing one.

**Verified.** Fix uses the existing per-row message element
(`alerts.js:234, 287, 306`) — no new component.

### P1-2 — the window does not use itself

Measured from the captures at 1015 CSS:

| Screen | Content ends | Window | Empty |
|---|---|---|---|
| Skills roster | **593** | 1015 | 42% |
| Settings (all five) | nav card `12→180`, content card starts **287.5** | 1015 | 107.5px gutter + ~380px empty column |

Skills has **two right edges**: `Filter characters` and `Copy plan` run to
the pane edge while every roster row and separator stops at 593.
`style.css:3237` makes `.skills-roster` `width: max-content` on purpose
("honest margin") and the reasoning is sound — but the filter field above
it was not brought along, so the result reads as a truncated table rather
than as a margin.

Skills is a comparison screen (37 characters against a plan) whose spare
pane shows nothing, while the per-character requirement detail it could
show is behind a row expand.

### P1-3 — the copy flow surfaces its safety only after commitment

`copy.py:565-571` names the source character, prints up to six target
names, states the overflow count explicitly, states the backup policy and
repeats the EVE-running hazard. **It is the best writing in the app.**

None of it appears before the modal. On `07-profiles.png` the user sees 37
checkboxes, a dimmed button, and an amber `EVE running` pill that never
says why it is amber. "Every copy backs up what it is about to overwrite"
(`evesettings.js:296`) lives in the **Backups** card, the third `<h2>` on
the route (`index.html:1165`) — below the fold at 633px.

*An earlier draft of this review claimed the safety story was absent
entirely. It is not; it is late.*

### P2-1 — the opacity slider is an unstyled native control

`04-settings-previews.png`. Measured: the unfilled track is
**rgb(239,239,239)** on a **rgb(23,20,31)** card — the single brightest
object across all nine captures, brighter than any text, ~1070px wide, on a
secondary setting.

`style.css:2734-2739` sets only `accent-color` and argues:

> `color-scheme: dark` above already gets a dark-themed native track and
> thumb from WebView2's Chromium, so the only thing left off-brand is the
> thumb's default blue.

`color-scheme: dark` *is* set (`style.css:44`). The capture refutes the
conclusion: setting `accent-color` returns the remainder track to the light
default. This is the failure `DESIGN.md`'s `.check`/`.radio` rule exists to
prevent, applied to two form controls and not the third.

**Verified by pixel sample.** Correct the comment with the fix.

### P2-2 — sorting is invisible until you have already sorted

`style.css:1113-1117` sets `visibility: hidden` on the sort glyph until a
column carries `.sorted`. The list opens in delivery order with nothing
sorted, so all four headers in `01-uploader.png` carry zero affordance.
16 recordings differing only in a timestamp make Size and Length the fast
route to "which one was the good fight", and the mechanism is fully built
and hidden behind knowing it is there. **Verified.**

### P2-3 — the status strip fails the project's own contrast floor

`SIG / ROOT / NEXT` peak at **2.73:1** (brightest antialiased pixel;
effective contrast is worse). Cause is `.evestat.degraded { opacity: .5 }`
(`style.css:1628`) compounding `--text-dim` at 11px. `DESIGN.md`'s stated
floor is 4.5:1.

The strip is degraded exactly when the bookmark engine is not live
(`bookmarks.js:535`) — which is the state in these captures. The failure
makes its own indicator harder to see. **Verified by measurement.**

Dimming a 4.5:1 label by half always lands under 3:1. Express degraded as a
token step, not as `opacity` over an already-dim token.

### P2-4 — the alert tuning knobs are UI-unreachable

`cooldown_s`, `duration_ms` and `pulses` are accepted, ranged and clamped
at `api.py:97`. Across `wingman/web/` they appear **only in `dev.js`**, the
fake-data harness. `PRODUCT.md` says the per-event cooldowns "exist because
the feature is worthless the moment it cries wolf."

Either the doc overstates them, or the Alerts card is missing the control
that makes the feature trustworthy. **Verified.**

### P2-5 — recall burden on Alerts

Fifteen unlabelled swatches, five per row, no legend tying a swatch to what
it looks like on a preview border. `alerts.js:181-182` gives each swatch a
`title` and `aria-label` of the **raw hex** — honest, as its comment says,
but `#4dd2ff` is not a name and it does not say Decloak already has it.

### P3 — minor

- **The `Link` column labels nothing.** Header renders, all 16 rows empty,
  and it advertises "Sort by uploaded" on a column with no data
  (`index.html:64`). It could hide itself the way `.evestat[hidden]` and
  `#eve-blockers-row` already do.
- **29 em dashes in user-facing JS strings.** `settings.js` x12,
  `alerts.js` x8, `firstrun.js` x3, `skills.js` x3, `bookmarks.js` x2,
  `previews.js` x1. Two templates account for 10. The three in
  `index.html` are empty-value placeholders and are legitimate.
- **Six zero-offset coloured glows**: `style.css:482` (`.mark`), `1598`
  (`.bar`), `1674`, `1675`, `1678` (dialog ticks), `2842` (radio ring). On
  the LEDs this is a legitimate indicator idiom; on the logo and progress
  bar it is decoration.
- **`--fs-mono` and `--fs-muted` are both 12px**, which `style.css:386`
  already flags.
- **The watermark's dose, not its presence.** `#route-settings::after` is
  fixed at 640x550 regardless of section length, and General is the
  thinnest section in the app — the mark covers roughly 45% of visible
  area beneath two checkboxes and a version string.
- **The Bookmarks card runs at two densities.** Four action binds one per
  full-width row (295px field in a ~1150px row), then FINISHERS switches to
  two columns, on one card.
- **"Format Enforcer"** (`bookmarks.py:146`) is Wingman's own coinage, not
  EVE's, sitting unglossed between `Set Root` and `Convert EvE-Scout
  Bookmarks`. `PRODUCT.md`: do not explain EVE, **do** explain Wingman.
- **`Rename` / `Delete` on Skills** are unbordered dim text whose vertical
  position is ambiguous between the two lists they sit between.
- **`.list-scroll` focused with zero rows has no focus indicator.**
  `style.css:829, 1172` set `outline: none`; the replacement is the focused
  *row*'s ring, which does not exist when there are no rows.

## Rejected findings

Recorded so they are not re-raised.

| Claim | Source | Why rejected |
|---|---|---|
| Flat type hierarchy (11/12/13/15/17) | impeccable | Contradicts `DESIGN.md`'s reasoned scale, pinned by `test_page_conventions.py:641`. Hierarchy is carried by luminance instead — measured 15.07:1 label vs 4.83:1 hint on one card, which survives CVD. **Do not act on this.** |
| Overused font (Inter) | impeccable | Self-hosted, WebView2-only, no network path. The product register permits it. |
| Marquee (`.track.indeterminate .bar`) | impeccable | Indeterminate progress for an ffmpeg stitch that reports no percentage. Reasoned at `style.css:1601`, stopped under `prefers-reduced-motion`. |
| Layout animation (`transition: width`) | impeccable | One element, 120ms, on a progress bar; `scaleX` would distort the gradient. |
| Broken image (`style.css:476`) | impeccable | Matched a code comment. The only `<img>` is `assets/emblem.png`, which exists, with correct `alt=""`. |
| Skipped heading h1 to h3 | impeccable | Document-order artifact: all nine routes live in one `index.html`, so the modal's `<h3>` trails the first-run `<h1>` in source and never on screen. |
| "Nothing selected" contradiction | assessment A | Not established. The Uploader hid a *count summary* duplicating a greyed button; Profiles renders "34 characters will be overwritten" and dims to "Nothing selected" only when empty, with a written reason. Different messages, different jobs. |
| Side-stripe borders | — | The two `border-left: 2px` sites are transparent selection indicators; `style.css:1152` records that the brand-coloured marker was deliberately removed and the width kept for header alignment. |

## Guard blind spots

`test_page_conventions.py` is unusually strong for a lexical suite. Four
gaps are load-bearing:

- The **colour guard reads `style.css` only.** `alerts.js:80`'s five hex
  literals are invisible to it, as would be any future inline
  `style="color:…"`.
- The colour guard **matches on token value**, so a literal that is not any
  token's value passes — `style.css:1655`'s `rgba(6,7,9,.62)` does.
- The **`hidden` guard sees only the static attribute** and only
  single-token selectors. 40 JS sites set `.hidden` at runtime.
- **There is no type-scale guard at all.** Six hard-coded `font-size`
  values exist against 61 `--fs-*` token uses.

## Score

| # | Heuristic | Score |
|---|---|---|
| 1 | Visibility of System Status | 3 |
| 2 | Match System / Real World | 3 |
| 3 | User Control and Freedom | 3 |
| 4 | Consistency and Standards | 2 |
| 5 | Error Prevention | 3 |
| 6 | Recognition Rather Than Recall | 2 |
| 7 | Flexibility and Efficiency | 2 |
| 8 | Aesthetic and Minimalist Design | 3 |
| 9 | Error Recovery | 3 |
| 10 | Help and Documentation | 2 |
| **Total** | | **26/40** |

Cognitive load: **5 of 8** checklist items fail — choice count, progressive
disclosure, visual noise, memory burden, decision points. Scan-ability
passes on type contrast and fails on Skills' two right edges; counted once.

**Not AI slop.** Zero gradient text, zero `backdrop-filter`, no hero-metric
block, no identical card grid, two modals in the entire app and both guard
irreversible writes, every `window.confirm` hit in the tree is a comment
explaining its avoidance. The interface evokes composure, which is the
correct register for a tool that lives on a second monitor beside a
wormhole you are rolling. The problems are dose and follow-through, not
taste.

## Lanes

`style.css` is the contention point as always; a lane owns files, not
findings.

| Lane | Owns | Findings |
|---|---|---|
| **L1 dialogs** | `panel.js`, `style.css` dialog block | P0-1 |
| **L2 layout** | `style.css` skills + settings blocks, `skills.js`, `api.py` skills payload | P1-2 |
| **L3 alerts** | `alerts.js`, `style.css` alert block | P1-1, P2-4, P2-5 |
| **L4 profiles** | `evesettings.js`, `copy.py`, Profiles markup | P1-3 |
| **L5 chrome** | `style.css` strip + list-head blocks, `list.js` | P2-2, P2-3, `Link` column |
| **L6 copy** | `settings.js`, `firstrun.js`, `bookmarks.py` strings | em dashes, Format Enforcer |

L1 is independent of everything and is the smallest change in the round.
**Run it first.**

L2 needs a bridge payload change (per-character requirement names do not
cross today), so it needs a `WM.HANDLERS` entry and clears
`test_bridge_contract.py`. Before touching the Bookmarks two-density split,
grep `tests/` for `#eve-binds`: `DESIGN.md` records that a
`max-width: 720px` override and its restore must move together or not at
all.


## What shipped, and what did not

The lane table above is how the round was planned. This is what the first
PR actually carries, so the two do not have to be reconciled by reading
git log.

| Finding | Commit | Verified by |
|---|---|---|
| P0-1 destructive confirm | `602f33d` | 4 mutations |
| P1-2 Skills roster names what is missing | `390633f` | CDP: roster edge 1003 = filter edge 1003 |
| P1-2 Settings beside their rail | `1b8c009` | CDP: gap 107.5px -> 12px |
| P1-1 alert colour collision | `ec89616` | CDP, four states |
| P2-5 alert colour names | `5af4d83` | CDP |
| P1-3 backup promise above the button | `67b657c` | CDP with three selected |
| P2-2 sort arrows, P2-3 degraded strip | `559e626` | 2.73:1 -> 5.07:1 |

**Three defects were found by the browser and could not have been found
by the suite**, which is this repo's standing hazard rather than a
surprise:

- The collision note kept warning on a **disabled** event. A disabled
  event is absent from the colour map, but its enabled partner still puts
  that colour in it, so the disabled row found a peer and warned about an
  alert it cannot raise.
- Deleting the backup note's `<p>` from `index.html` left every JS
  assertion green: `WM.el` returns null and the `if (commitNote)` guard
  swallows it.
- The first version of the P0-1 guard used a regex, matched 3 of the 4
  confirm call sites, and passed while `Confirm Copy` sat outside it.

All three are now mutation-tested.

**Two existing tests pinned a MECHANISM rather than an intent** and broke
on correct changes. `test_the_sort_arrow_has_a_reserved_slot_on_every_header`
asserted `visibility` when its own docstring says it is about the
reserved slot; `test_the_backup_note_takes_its_number_off_the_payload`
asserted the assignment's shape. Both were rewritten to their stated
intent and strengthened. Worth knowing that this file has more of them.

### Left open, deliberately

- **P2-4, the alert tuning knobs.** Exposing `cooldown_s`,
  `duration_ms` and `pulses` means nine new controls on the card this
  same round flagged for cognitive load (~27 options already). PRODUCT.md
  says they are why the feature is not worthless when it cries wolf.
  Those two facts have to be reconciled by a decision, not by building
  the controls.
- **The 29 em dashes.** Both assessments and this document agree it is
  house voice, not a defect. Not a change to make on one reading.
- **The `Link` column hiding itself.** `test_uploader_page.py` derives
  every breakpoint from the declared grid tracks, and its header warns
  that losing a column off an `overflow: hidden` pane is invisible -- no
  scrollbar, nothing logged. A dynamic 5-to-4 column change means the
  whole tier system follows, which is disproportionate for a P3.
- **The minors**: watermark dose on General, `--fs-mono` and
  `--fs-muted` both 12px, the Bookmarks two-density split (whose
  `#eve-binds` breakpoint carries the move-together-or-not-at-all rule),
  Rename/Delete on Skills, the six glow sites.
