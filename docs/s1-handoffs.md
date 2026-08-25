# S1 handoffs — `ui/s1-primitives`

Round-2 lane S1 (primitives, chrome, status strip, dialog). Everything
below is something S1 **decided** or **found** but is not permitted to
edit, because the file belongs to another lane. Nothing here is a request
to change scope; each item names the lane that owns the edit.

S1's own edits are in `web/style.css` (tokens, titlebar, `.linkish`, the
status-strip comment), `web/app.js`, `web/index.html` (titlebar and
`#statusbar-slot` only) and `web/dev.js`.

---

## To S4 — `DESIGN.md`

Three rules S1 settled that belong in `DESIGN.md`, which S1 does not own.

**1. Column headers share the inset of the rows they label.** (Walkthrough
Skills 7, same defect as Uploader 3.) `PLANS` sits ~22px left of its
column and `READY` ~14px right of its own; on the Uploader the headers sit
~16px right of their data. The Skills instance has no scrollbar, which
rules out the gutter explanation for the Uploader one too — header rows
and data rows simply do not share padding. The rule is: **a header row is
laid out by the same padding as the rows beneath it, with no separate
inset.** R1 and R4 execute; there is nothing for S1 to edit, because
neither header row lives in an S1 region.

This does not license changing header *size*. `--fs-muted` on column
headers is a recorded deliberate decision and `DESIGN.md` already says not
to "fix" it.

**2. The one blue is a declared exemption, not a stray hex.** (Settings
18.) `.linkish` was `#7aa2f7` written inline; it is now `--link`, defined
in `:root` beside the severity tokens with the reasoning attached. The
colour did not change — 7.4:1 on `--panel`, 7.7:1 on `--bg`, both over the
4.5:1 floor. `DESIGN.md`'s "tokens are the only place a colour is decided"
is now true of it. Worth a sentence in `DESIGN.md` saying that an outbound
link keeps link-blue *because* it leaves the app, so a future contributor
does not "unify" it into the palette.

**3. The idle status word is `Idle`.** (F6, and the strip's half of Skills
3.) `docs/smoke-checklist.md` is yours — if any check item names the
status strip's resting text, the wording is now `Idle`. `Ready` stays with
Skills, which owns it in Python (`eveskills/evaluator.py:19`) and in the
payload; the strip only ever meant "the app is doing nothing" and now says
so. This removes Skills 3's roster half from R4 entirely.

**4. Accent budget (Uploader 16) — see the open question at the bottom.**

## To S4 and S3 — the floor claim survives in two more places

S4 is correcting `DESIGN.md:56-58` and `PRODUCT.md:137`. The same wrong
claim also sits in:

- `obs_youtube_uploader/ui/window.py:40-46`, in a comment that ends "do
  not 'correct' this to logical" — **S3's file**, and not in any S3
  finding, so it needs the maintainer's word before anyone edits it.
- `CLAUDE.md:128-130` — in no lane at all.

S1 has corrected the one instance inside its own region:
`style.css`, above `@media (max-width: 720px) { .evestat { display: none; } }`.
The rule is kept, not deleted — it is the only record of what the strip
does when it runs out of room (the EVE segment yields, upload progress
does not) — but the comment now says plainly that the query cannot fire at
a floor of 840 CSS px, and that nothing new should be sized against a
560px or 672px viewport.

**Consequence for wave 2, worth stating once:** `style.css` carries four
more `@media (max-width: 720px)` blocks, at roughly lines 743, 858, 1008
and 1297, in R2's, R2's, S2's and R4's regions respectively. By C1 none of
them can fire either. S1 has not touched them. Each owning lane should
decide for itself whether its block is a decision worth keeping or dead
weight — but no lane should assume those blocks are load-bearing.

## To R1, R2, R3 — X1 execution

`WM.setEnabled(elementOrId, boolean)` now exists in `app.js`. Use it
rather than hand-rolling a third variant.

```js
WM.setEnabled('btn-upload', selectedCount > 0);
WM.setEnabled(node, false);
```

It takes an element or an id, sets the `disabled` property, returns the
element, and `console.warn`s and returns `null` for an id that resolves to
nothing — a silent no-op there would leave a button live in exactly the
state the helper exists to cover.

**Do not restyle anything.** `button.btn.acc:disabled` already works and
is untouched; the twelve sites were missing the attribute, not a
treatment.

The rule for *when* to call it, since the three screens answered it three
ways: **a control is disabled when the app already knows the action cannot
be carried out from the state it is holding** — nothing selected, no
folder chosen, no webhook configured. Not for an action that might fail
once attempted; that is the status strip's and the dialog layer's job. And
nothing may disable the only route back out of the state that disabled it.

## To R2 — the other half of Settings 18

The finding has two halves. S1 took the colour. The other half —
`index.html:184` renders `https://www.youtube.com/t/terms` as raw URL text
rather than as a labelled link — is inside `#route-settings` and therefore
R2's. S1 has not touched that markup.

## To R4 — Skills 3 has no roster half left

See item 3 above. The strip changed; `Ready` stays where it is on Skills.
R4's list still holds Skills 1, 2, 4, 5, 6, 9 and Skills 7's execution.

## To S3 — settled, no action

The version reaches the page as a `version` key on the settings payload,
confirmed with S3 directly. `app.js` reads it from the `wm:settings` event
and writes it into `#app-version`; a payload without the key leaves the
titlebar as it was rather than printing `undefined`, so merge order does
not matter. S3 also established that `get_settings` is a return and never
a push, which is why the titlebar is populated at the page's startup read
and not by a later event.

---

## Open question for the maintainer — Uploader 16

S1 owns the *decision* half and R1 the execution. The proposed rule, not
yet approved:

> Accent marks **what is selected** and **what will happen**. A card
> heading is neither, so `.card > h2`'s accent bar loses it.

`DESIGN.md`'s existing rule is written about controls, so the two heading
bars on the Uploader (`UPLOAD`, `PUBLISH`) do not breach its letter — they
compete with the two places accent is load-bearing. If the rule is
approved it belongs in `DESIGN.md` (S4) and the edit belongs to R1; if it
is not, R1's finding 16 closes with no change. Nothing in S1's branch
depends on the answer.
