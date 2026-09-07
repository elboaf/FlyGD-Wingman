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

Four rules S1 settled that belong in `DESIGN.md`, which S1 does not own.

**1. Column headers share the inset of the rows they label.** (Walkthrough
Skills 7, same defect as Uploader 3.) The walkthrough records `PLANS` ~22px
left of its column, `READY` ~14px right of its own, and the Uploader's
headers ~16px right of their data. **Treat all three as unverified and
re-measure in CSS px before sizing anything to them.**

S2 checked several walkthrough figures against the stylesheet and found two
distinct problems, which is why this says "unverified" rather than giving a
correction factor. Some figures are physical pixels read off 200% captures
and halve cleanly: Settings 12's "~255px" is 128 CSS, which is the 118px
`.lab` plus a 10px gap exactly, and Settings 3's "about 48px" is 24 CSS,
which is `.check`'s 15px box plus a 9px gap exactly. But F3's "11 CSS px"
is not a unit slip at all — the walkthrough gave that one in physical units
already (568 → 590) and converted it correctly. It is simply wrong, which
is a different failure and needs a different response.

**F3 measures 6 CSS px, and this is settled rather than open.** Rendered
from merged `main` in the `?dev=1` harness at an 840 CSS viewport: the h1,
both paragraphs, the field, *and the skip button's border box* all begin at
x=169. Only the button's ink begins at 175 — text-range origin and
border-box-plus-padding agree on that to the hundredth. So the displacement
is 6.0 CSS px and it is entirely `.linkbtn`'s `padding-left: 6px`; nothing
about the button's box is out of line. At 200% that is 12 physical, which
is what S2 measured directly and independently. The walkthrough's 22
physical does not reproduce, and R5 should build to 6 CSS.

The rule rests on the direction, not the figure: headers and rows do not
share padding. The Skills instance has no scrollbar, which
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
colour did not change — 7.13:1 on a card's tinted top stop, 7.19:1 on flat
`--panel`, 7.72:1 on `--bg`, all over the 4.5:1 floor. (Re-measured after
the purple retheme in #52, which landed between S1's base and its merge.) `DESIGN.md`'s "tokens are the only place a colour is decided"
is now true of it. Worth a sentence in `DESIGN.md` saying that an outbound
link keeps link-blue *because* it leaves the app, so a future contributor
does not "unify" it into the palette.

**3. The idle status word is `Idle`.** (F6, and the strip's half of Skills
3.) `docs/smoke-checklist.md` is yours — if any check item names the
status strip's resting text, the wording is now `Idle`. `Ready` stays with
Skills, which owns it in Python (`eveskills/evaluator.py:19`) and in the
payload; the strip only ever meant "the app is doing nothing" and now says
so. This removes Skills 3's roster half from R4 entirely.

**4. Accent marks what is selected and what will happen.** (Uploader 16.)
Approved by the maintainer. `DESIGN.md`'s existing rule — "`.btn.acc` is
the single brand-accent control" — is written about controls, so the
`UPLOAD` and `PUBLISH` heading bars never breached its letter; they were
simply a third and fourth claim on a signal that carries two meanings. The
rule to add is:

> Accent marks **what is selected** and **what will happen**. A card
> heading is neither.

On the Uploader that is five accent uses down to three: the checked row's
checkbox and its left-edge marker (what is selected) and the `Upload`
button (what will happen). The two `.card > h2` bars lose it. **R1
executes**; the heading-bar treatment is not confined to that screen, so
whichever lane owns a card heading elsewhere inherits the same rule.

## To S4 and S3 — the floor claim, and the two out-of-lane instances

S4 is correcting `DESIGN.md:56-58` and `PRODUCT.md:137`. The same wrong
claim sat in two more places, both outside every lane's ownership:

- `wingman/ui/window.py`, in a comment that ended "do not
  'correct' this to logical" — nominally S3's file, and in none of S3's
  findings.
- `CLAUDE.md`, in no lane at all.

**The maintainer has authorised S1 to fix both, and this branch does.**
`window.py`'s comment now states the logical-unit result and the
839x621-at-200% measurement; correcting it also repaired a mangled
sentence, since the physical-pixel paragraph had been inserted into the
middle of the one about the two provisional estimates and left its second
half orphaned. `CLAUDE.md`'s line now reads **logical**, with the
consequence spelled out. Neither is a behaviour change: `MIN_WIDTH` and
`MIN_HEIGHT` are untouched at 840 and 625.

**S3 should know** that `ui/window.py` is touched by this branch, so a
rebase may be needed — the change is comment-only and in no method.

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

## To R5 — F3's mechanism, specified by S2

S1 measured F3 (above); **S2 owns `.linkbtn`'s box model and has specified
how to act on it.** Recorded here because R5 reads this file and a bare
"6 CSS px" gets the second half wrong:

- **`padding-left: 0` on the first-run skip is wrong**, even though it
  would move the ink to 0. `.linkbtn:hover` paints `background: #22252c`,
  so zeroing the left padding leaves the hover rectangle hugging the
  glyphs on one side and 6px clear on the other. The one button that got
  the fix would look broken on hover while eighteen bind rows stayed
  correct.
- **`margin-left: -6px`, scoped to the first-run action row**, is the
  right shape: padding and hover rect stay symmetric, the ink lands at 0,
  and the box overhangs the content edge into the card's own padding.
  Standard optical alignment for a padded text button — align the text,
  let the transient chrome overhang. (S1's render corroborates the room
  for it: the card's box is at 140 and its content edge at 169.)
- **Either way the padding stays on the class.** That was the boundary the
  lanes doc warned must not silently become "remove the padding" — bind
  rows, Skills' link buttons and Profiles' `Change…` are untouched.

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

## Nothing left open in S1

Both decisions S1 was asked to settle before starting — the idle status
word and whether the terms link gets a token or an exemption — were
answered by the maintainer, and Uploader 16's accent rule was approved
afterwards. S1 holds no open question. What remains are the items above,
each owned by a named lane.
