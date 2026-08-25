# R2 handoffs — `ui/r2-settings`

Round-2 lane R2 (Settings: `settings.js`, `bookmarks.js`, `previews.js`,
`index.html #route-settings`, `style.css`'s settings-route and bind-row
blocks). Everything below is something R2 **decided**, **found** or
**declined**, and is either owned by another lane or worth stating once so
nobody re-derives it.

R2's own edits are in `web/index.html` (`#route-settings` only),
`web/settings.js`, `web/bookmarks.js`, `web/previews.js`, `web/dev.js`
(two payload keys, by permission), `web/style.css`'s `#preview-binds`,
`#preview-binds-off`, `#about-version` and `#eve-binds` rules, and
`tests/test_settings_page.py`.

---

## To R4 — the rule for a full-width row, decided for both lanes

Walkthrough Settings 11 and Skills 6 are one question in two places: *what
should a full-width row do with its width?* The maintainer asked R2 to
settle it for both, so this is the answer R4 inherits.

> **A full-width row does not stretch its label to fill. The value column
> sits at the widest label plus one gap, and the width left over stays
> unused at the right rather than becoming a gap in the middle.**

**The walkthrough's figure does not survive measurement, and R4 should
expect the same of Skills 6's.** It reports "~600px between `Grab Sig ID`
and `Not set`", which cannot happen inside a `.settings` capped at
`max-width: 620px`. Measured in the `?dev=1` harness at the 840 CSS floor,
with the real eighteen `BIND_LABELS`:

| | before | after |
|---|---|---|
| row width | 586px | 586px |
| label box | 316px | 190px |
| widest label ink | 190px | 190px |
| gap, name to binding | 137–274px | 10–148px |

The surplus was the whole defect: `flex: 1` gave every label a 316px box
when the longest name needed 190, and the 126px difference became a void on
every row that was not the longest. Skills 6's "~1000px" is the same shape
and is very probably the same arithmetic — S1's handoff already warns that
several walkthrough figures are physical pixels read off 200% captures.
**Re-measure before sizing anything to it.**

**Mechanism, because the obvious one does not work.** Grid on the
*container* with `display: contents` on the rows:

```css
#eve-binds {
  display: grid; gap: 10px; align-items: center; justify-content: start;
  grid-template-columns: minmax(0, max-content) repeat(3, max-content);
}
#eve-binds .row { display: contents; }
#eve-binds .row[hidden] { display: none; }
```

Three things that cost time and will cost R4 the same:

- **Grid on each `.row` sizes each row separately.** `max-content` then
  resolves per row and the values stop aligning — eighteen buttons at
  eighteen x-positions, which is worse than the void it replaced. The grid
  has to be on the element that holds every row.
- **`display: contents` out-specifies `.row[hidden]`**, so a hidden row
  keeps rendering its children with the row itself gone. That is the
  `[hidden]` trap `DESIGN.md` names and `.row` itself already carries a
  note about; the guard above is required, not defensive.
- **`.row`'s box disappears**, taking its `gap: 10px` and
  `margin-bottom: 10px` with it. The grid's own `gap` restates both.

`minmax(0, max-content)` rather than bare `max-content` on the name column:
a pathologically long character name has to be able to shrink rather than
push the controls out of the card, which is what `min-width: 0` did under
flex.

## To whoever next owns `ui/copy.py` — Settings 15, which R2 could not take

`not configured` is the only lower-case, unpunctuated status string in the
app, against `Not running`, `Nothing selected`, `No backups yet.` and
`Not connected`. It exists in three places:

- `ui/copy.py:244` — **S3's file, merged.** The tested source, and the one
  the payload actually carries.
- `web/settings.js` — the fallback when the payload has no
  `webhook_status`.
- `web/index.html` — the pre-hydration default.

R2 owns the last two and not the first. Changing only those two produces a
page that reads `Not configured` until the payload lands and then flips to
`not configured` in front of the user, which is worse than the finding.
**One change, in `copy.py`, and the other two follow it.** Left untouched
on purpose.

## To R1 — the card-heading accent bar is not scopeable from a screen lane

S1's approved accent rule ("accent marks what is selected and what will
happen; a card heading is neither") assigns the `.card > h2` bars to R1 to
remove, and adds that "whichever lane owns a card heading elsewhere
inherits the same rule".

There is nothing for R2 to inherit, because the bar is not per-screen:
`.card > h2::before` is at `style.css:238`, inside S1's shared primitives
region. Every card on Settings, Profiles and Skills draws it from that one
rule. So R1 cannot confine the change to the Uploader without editing a
region no wave-2 lane owns, and when the rule changes, **all four routes
change appearance in the same commit**. Worth knowing before it looks like
a regression on a screen nobody edited.

## Declined, with reasons

**Settings 7's heading half.** The finding is that on Bookmarks every card
heading opens with the word every heading shares — `EVE BOOKMARKS`,
`EVE WINDOWS`, `EVE-FOCUSED KEYBINDS`. R2 took the list half (below) and
declined the headings, because both available edits undo merged work:

- Dropping the prefix gives `Bookmarks` and `Windows`. `Bookmarks` is the
  rail item verbatim, which is what round 1 (#44, "headings that stop
  echoing the rail") removed and `test_settings_page.py` now forbids.
  `Windows` collides with the operating system on a Windows-only app.
- Renaming `EVE-FOCUSED KEYBINDS` blurs its pairing with Previews'
  `GLOBAL KEYBINDS` — the distinction the walkthrough calls "the best
  writing in the app" and explicitly asks not to undo.

The list half had neither problem and is done: every EVE client titles its
window `EVE - <character>`, so the checkbox list repeated the prefix on
every row. It is stripped for display only; `title` remains the identity
(it is the key in `settings.windows` and what the engine matches on) and
the full title is on the row's tooltip.

**Settings 2's colour half — superseded.** The observation reproduces
exactly: with previews off, the checked `Position` box is the only
brand-painted element on the section. But desaturating it contradicts S1's
approved rule that accent marks what is *selected*, and the rule lives in
S1's region; and disabling the control contradicts S3's handoff, which is
explicit that Previews controls stay live because recording a preference
for later is an action that *can* be carried out. What was actually wrong
is that a dependent option was rendered as a peer of the switch it depends
on. The row now says so, in INERT_NOTES' voice, and only while it is true.

## Closed by S2 before R2 started — verified, not edited

Both re-measured in the harness at 840 and 1280 CSS, from each card's
content-box left edge:

- **Settings 12** — "three left edges, a ~255px jump". Every section's
  first control now begins at 1 (that 1 is the card's own border).
- **Settings 4** — "prose hangs ~250px right of the rows". Prose and
  controls both at 1.

**Settings 16 is half closed.** The walkthrough's own path,
`C:\Users\tng\Documents\EVE\logs\Gamelogs` (40 chars), no longer clips:
S2's stacking widened the field from 604−118 to 422px and the value needs
exactly 422. It still clips silently from about **59 characters**, which is
what a OneDrive-redirected Documents folder produces, and an `<input>`
cannot ellipsize or wrap. Both folder fields now carry their full value as
a `title`; the field's own box belongs to S1 and S2.

## Left standing, and why

**`Api.import_bookmarks` has no caller.** Settings 19 removed the
`Import from an existing helper…` button. The bridge method, its
`alert_import` counterpart, `tests/test_bookmarks_import.py` and
`tests/test_api_bookmarks.py` are all untouched: removing a bridge method
is `ui/api.py`, which is another lane's file, and the import logic itself
is correct — only its entry point was unused.

**Settings 10 is partly resolved and the rest is inherent.** The complaint
is that `EVE BOOKMARKS` spends ~280px on three sparse rows while the
keybind card below runs dense and repeats eighteen times. Two of those
three rows were the import button (gone, finding 19) and the engine-state
line (now withheld under an unticked switch, finding 8). Measured at 840
CSS the sparse card went 167px → 136px against the keybind card's 831px.
The remaining difference is a card with one switch beside a card with
eighteen rows, which is what the section is; no further edit was made.

## Two new lexical guards, in `tests/test_settings_page.py`

Nothing in the suite renders the page, so both are source reads:

- **`test_the_page_never_types_a_version_number`** — M2's whole point. The
  markup may not carry a version-shaped literal at all; `__version__`
  reaches the page on the payload and JS writes it into the titlebar and
  into `ABOUT`.
- **`test_the_dev_harness_quotes_copy_pys_inert_notes_verbatim`** — the
  Previews sentence is now `ui/copy.py`'s and index.html carries no copy of
  it, which left `dev.js` as the only remaining duplicate. It is a
  deliberate one (dev.js is the file that fabricates data), so it is
  asserted against `copy_mod.INERT_NOTES` rather than trusted.
