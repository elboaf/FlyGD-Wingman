# Previews: the character table, rebuilt

Settings › Previews ends in a list with one row per known character. This
document is the design for turning that list into a table, and for moving
two of its columns to the toggles they are exceptions to.

The prompt was a screenshot and one sentence: "functionality works fine,
but it's just really ugly". It is worth recording that the diagnosis was
not a taste call. The list renders every character name on a full-width
line of its own and its seven controls on the line beneath, so thirteen
characters read as thirteen headings rather than as one table, and the
column headers are off screen by the sixth row.

Round 3's B1 is why. Each bind list's first track was `max-content` over
its OWN labels, so the bind button sat at 189.6px in Bookmarks and 86.2px
in Previews: 103.4 CSS px apart in two sections of one screen, and
Previews' half moved between sessions because the track followed whoever
was logged in. The fix chosen was to delete the column in both lists and
stack the name above its controls. That fixed the offset. It also gave the
Previews list a shape sized for Bookmarks' content.


## Decisions

Four, all taken with the maintainer in the loop, recorded here so the
reasoning is not rediscovered from the result.

1. **Previews diverges from Bookmarks; Bookmarks keeps stacking.** B1's
   shared-shape rule is retired, not violated. Bookmarks' longest label is
   "Convert EvE-Scout Bookmarks" at 189.6px and genuinely needs its own
   line; character names are uniform and short. The two lists differ in
   content, and only four ungrouped Bookmarks rows were ever in the shared
   grid anyway (round 5's C8 moved the other fourteen into `.bind-dense`,
   a flex block with no shared tracks).
2. **Lock and Never minimize leave the row.** This is not a preference. The
   seven tracks and six gaps measure 502.16px of the 586px card interior,
   so 83.84px is free and a name column costs about 126. Freeing those two
   columns returns about 136px including their gaps.
3. **They become disclosures under the toggles they except**, in the first
   card, not blocks under the table in the second. Round 5's C4 moved the
   minimize toggle into the first card precisely because it "governs every
   per-character Never-minimize box" (`index.html:600`). Putting the
   exception beside the rule finishes that move and deletes the sentence
   at `index.html:628` whose only job is to point at the other card.
4. **A disclosure summary is a door when there is nothing to state, and a
   fact otherwise.** Both patterns already exist here: `.rail-about` uses a
   question as a door, `.skills-issues` uses a fact.


## The row

Five tracks and a trailing flexible one, down from seven:

```
Character          Preview  Keybind         Size
Amelio Pellion       [x]    [Ctrl+Alt+F1]   Clear Edit…   Size…
Guarzo Togenada      [x]    [Not set    ]         Edit…   Size…
Astrella Esubria     [x]    [Not set    ]         Edit…
  offline
```

```css
grid-template-columns: 150px repeat(4, max-content) minmax(0, 1fr);
```

**The name track is fixed, not `max-content`.** `max-content` over
character names is B1's original bug: the track follows whoever is logged
in and is unstable between sessions. Fixed keeps that property while
dropping the cross-list half of the old rule. Names wider than the track
ellipsize and carry a `title`.

**`Clear` and `Edit…` share one cell.** Two adjacent link buttons in two
tracks forced two blank header cells, which is what produces the wide
ragged gap between "Keybind" and "Size" today.

**`Clear` renders only where it can do something**, with a filler cell
holding the track open. Today it is `:disabled` on every row of a fresh
install, and `.linkbtn:disabled` is `opacity: .45` over `--text-faint`,
which computes to **1.94:1** against the card. That is a control nobody
can read occupying a track on every row. Rendering it conditionally is
D6's own rule (`previews.js:270`), already applied to `Size…`; this
applies it to the one remaining control that breaks it.

**`.no-nm` disappears.** With Never minimize off the row there is no
conditional cell, so `makeRow` and `makeHeadRow` stop varying their cell
count, one grid template replaces two, and the hand-maintained difference
between them stops existing.

**The unbound state stops shouting.** Measured against the card,
`--control` (the bind button's fill) is 1.09:1 and `--control-border` is
1.32:1, so the box is very nearly invisible and what carries "Not set"
thirteen times is `--text` at 13.71:1. `.bindbtn.unset` drops the label to
`--text-dim`, which is 6.43:1 on `--control`. A bound chord keeps `--text`
and becomes the thing that stands out, which is the right way round for
what the reader is scanning for.

`.unset` cannot collide with the three existing bind-button states:
`clashes()` returns `null` for an empty gesture (`previews.js:91`) and no
bookmark chord list contains `""`, so an unset button is never also
`.clash`, `.unknown` or `.dim`.

**No border is raised, deliberately.** No border token in the app clears
3:1 against the card (`--control-border` 1.32, `--field-border` 1.18,
`--panel-border` 1.11). Fixing that is a decision about every control in
the app and does not belong to this change.


## The exception blocks

Two `<details>`, each directly beneath its own toggle in the first card,
indented to the toggle's label text. The roster inside uses `.es-roster`'s
column treatment (`columns: 170px`), which already solved "a list of
character names in a narrow card" on Profiles.

```
[x] Minimize a client's window while it is not the one you switched to
      Applies the next time a client is switched away from, not this one.
    ▸ Exempt individual characters

[ ] Lock previews in place by default
      Applies to every character whose own Lock box you have not changed.
    ▾ Locked: Guarzo Togenada
        [ ] Amelio Pellion   [ ] Umochi Tawate    [ ] Guarzo Opper
        [x] Guarzo Togenada  [ ] Astrella Esubria
        [ ] Gustav Oswaldo   [ ] Suartad Arsten
```

"Exempt" rather than a new phrase: the toggle's own hint already calls it
that (`index.html:628`).

### The summary sentence, and the polarity trap

`preview.locked` does **not** hold the locked characters. It holds the
ones that DIFFER from `lock_default`, and `isLocked()` resolves the pair
with an XOR (`previews.js:429`). The checkboxes are safe because they go
through that function. The summary is new text and has to resolve the pair
itself, or it states the opposite of the truth the moment the default is
on.

| `lock_default` | exceptions | resolved | line |
|---|---|---|---|
| off | none | nobody locked | **door**: `Lock individual characters` |
| off | some | those are locked | `Locked: Guarzo Togenada` |
| on | none | **everyone** locked | `Locked: every character` |
| on | some | all but those | `Locked: every character except Guarzo Opper` |

**The door is keyed on the resolved state being nobody, not on the list
being empty.** An earlier draft of this design had it keyed on the list,
which is wrong in row three: with the default on and no exceptions every
character is already locked, and a door inviting you to lock one would be
offering something already done. The door therefore appears in exactly one
of the four states, and it is the fresh-install one, which is where
discoverability matters.

**Never minimize is not the same underneath, and the two blocks will look
identical.** `isNeverMinimize()` is a plain membership test
(`previews.js:433`) with no default toggle of this kind, so that block has
two states, not four: door when the list is empty, fact when it is not.

Names, not counts, and truncate long lists the way `alerts.js:463-471`
already argues for the same problem on the same kind of sentence.

### Accessible naming

The row checkboxes carry an `aria-label` naming their character
(`previews.js:462`, `:475`, `:648`) because the visible label has no text
at all: that is `DESIGN.md:194`'s rule, and it is a rule about a checkbox
in a table column.

**Do not carry those labels over.** In the blocks the character name IS
visible text inside the `<label>`, so an accessible name exists already
and a retained `aria-label` would override the visible one, which is the
failure WCAG 2.5.3 names.

What is genuinely missing is what the tick MEANS. "Amelio Pellion,
checkbox, checked" does not say whether that is about locking or about
minimizing, and the only thing that supplies it is the summary, which is
not programmatically associated with anything. Associate the group: give
each roster container an `aria-labelledby` pointing at its own `<summary>`
so the block's purpose reaches the accessible name computation once,
rather than being restated on every row.

### Where the code lives

`previews.js` renders both blocks, even though their markup sits in the
first card. It already holds `locked`, `lock_default`, `never_minimize`,
`excluded`, `characters` and `roster` off the hotkey-state payload, and it
already listens for `wm:preview-lock-default` and
`wm:preview-minimize-inactive` (`previews.js:1103`, `:1115`), the events
`settings.js` dispatches when those toggles flip. Rendering them from
`settings.js` would mean holding the same payload in two files.

**No Python changes.** The blocks call `set_preview_locked`
(`api.py:2913`) and `set_never_minimize` (`:2934`), which are the same
endpoints the row checkboxes call today, and read fields the payload
already carries (`:2489`). The write path is unchanged; only where the
checkbox lives changes.

### Keeping the summary live, which nothing currently does

**This is the one thing in this design that today's code actively does not
support**, and it was missed until an independent review of this document
went looking for it.

Both per-character handlers patch `state` and return without rendering:
`set_preview_locked`'s at `previews.js:504` and `set_never_minimize`'s at
`:660`. That is correct today and deliberate. The box the user clicked
already shows its own new value, so a repaint would be waste, and the
endpoints do not push either (`api.py:2929`, `:2938`).
`makeExcludedCheck` is the only one that calls `requestRender()`, and only
because opting out changes OTHER controls on its row.

A summary sentence derived from `state.locked` turns that deliberate
non-render into a stale-summary bug: tick a box inside the block and the
line above it still says "nobody" until something else happens to repaint.
So both handlers must repaint their block on success. This design
introduces the first read of that state that is not the control the user
just clicked, which is why the gap did not exist before it.

**Repaint through the existing guards, not around them.** Two are already
there and both are load-bearing:

- The `pushes` generation guard, which drops a patch when a newer hotkey
  table landed mid-flight.
- The lock handler's `defaultAtSend` guard (`previews.js:503-516`), which
  calls `refresh()` when `lock_default` changed while the write was in
  flight. Its comment records that bumping `pushes` there instead was
  tried and made `send()` drop a keybind save Python had accepted. Do not
  re-try that.

Repaint the block only, not the whole table: a full `render()` while a
keybind capture is armed is the trap `requestRender()` and `pendingRender`
exist for.


## What must not change

- **Never minimize stays live for an opted-out character.** Unlike every
  other per-character control, opting out of previews does not stop it:
  `_activate_client` still consults it for a character with no preview.
  Guarded by `test_never_minimize_stays_live_on_an_opted_out_row`.
- **Lock is inert for an opted-out character.** With no window there is
  nothing to lock. The asymmetry with the line above is the point.

  **The styling that says so does not travel with the control.** Both
  inert rules are scoped to the host the checkbox is leaving:
  `#preview-binds .check.inert` (`style.css:1480`) and
  `#preview-binds .check.inert input:not(:checked) + .box` (`:1502`).
  `makeLockCheck` returns through `inert()` (`previews.js:530`), which
  sets the class and calls `WM.setEnabled` on the INPUT; the input is
  `opacity: 0` and positioned out of flow, so the class is the entire
  visible treatment. Relocated without those selectors, an opted-out
  character's Lock box looks live and clicking it does nothing.

  The second rule is the one that is easy to drop as decoration and is
  not. Its comment (`style.css:1484-1493`) records that it is qualified
  with `input:not(:checked)` specifically so a character who is BOTH
  locked and opted out keeps the checked gradient under the dimming
  instead of being repainted as unticked. That state is exactly the one
  the block makes easier to reach.
- **The Never-minimize block exists only while the global toggle is on**
  (D6), the same rule that governs the column today.
- **`Size…` renders only where `set_preview_size` can succeed**, with a
  filler where it cannot.
- **The opt-out box is never gated on previews being enabled.**
- **Unticking the lock default is not an undo.** A box changed while it
  was on means the opposite thing once it goes off. `api.py:2669` carries
  the worked example. The UI must not promise reversibility.


## Two hazards this change creates

Both were found by building the mockup against the real stylesheet, and
both would otherwise have shipped looking like a correct table.

1. **Rows scramble without a definite column start.** With the name
   inline, each row contributes 5 cells to a 6-track grid, so the trailing
   `minmax(0, 1fr)` swallows the NEXT row's first cell and every row after
   it walks one track left. The current design never hits this because the
   spanning `.lab` forces a fresh row for free. The cure is
   `#preview-binds .row > :first-child { grid-column-start: 1 }`, the same
   mechanism `test_page_conventions.py:1382` already relies on.
2. **`Edit…` sits at two x positions** depending on whether `Clear`
   rendered beside it, because they now share a cell. Fixed by
   right-aligning inside that cell, so `Edit…` pins to one edge and a
   missing `Clear` reads as an empty slot rather than a shift.


## Measurements

Taken in headless Brave over CDP at the 840x625 floor with
`--force-device-scale-factor=1`, against the real `style.css`.

| | now | proposed |
|---|---|---|
| card interior | 586 | 586 |
| control line used | 502.16 | **519** |
| free | 83.84 | **68** |
| overflow / clipped | none | **none** |
| per character | ~62px | **~30px** |
| grid height | 370px for 3 characters | 366px for 7 |

Header-to-column alignment, proposed: `Character` 0.00, `Preview` 0.00,
`Keybind` 0.00, `Size` 0.00.

The 502.16 came out of the browser to the pixel against the figure already
recorded at `previews.js:573`, which is why the rest of the table is
trusted. Two figures produced by hand during design were wrong and are
recorded here so they are not re-derived: the free space was estimated at
158px (it is 83.84, because the "Never minimize" header sets its track to
about 90px, not the checkbox's 15px), and the proposed control line was
estimated at 536 (it is 519).


## Blast radius

Ten tests in `test_page_conventions.py`. Three change shape:

- `:222 test_the_two_keybind_lists_render_the_same_row` is the retired
  invariant. Rewritten around the new relationship rather than deleted, so
  what replaces it still forbids a list drifting into an accidental track
  kind.
- `:1282 test_the_previews_grid_drops_exactly_one_track_with_never_minimize`
  retires with `.no-nm`.
- `:1468 test_the_size_control_is_not_drawn_where_it_could_only_refuse`
  extends to `Clear`.

The rest follow the new cell list: `:1321`, `:1353`, `:1419`, `:1509`,
`:1534`, and `:122 test_generated_controls_use_the_wrapper_too` reaching
the new checkboxes in the blocks. `:327
test_every_hidden_element_can_actually_hide` covers the new disclosures.

One guard survives unchanged and still binds: `:180
test_an_id_override_of_the_label_column_still_collapses_at_the_floor`
finds every `#id .row > .lab` override and requires a matching restore in
a `max-width: 720px` block. Previews keeps its override, so it keeps its
restore.

`DESIGN.md` needs three passages re-argued rather than appended to: the
label-column override rule (`:266`, which cites `#preview-binds` as an
example of long labels), the checkbox-in-a-column paragraph (`:194`, whose
"three words × thirteen rows" evidence is this exact list), and a record of
why B1's shared shape was retired so nobody restores it from the old
reasoning.

Also in the blast radius: the bind button's opted-out tooltip says "comes
back when you untick **Off**" (`previews.js:207`), and there has been no
box named `Off` since it became the inverted `Preview` box at `:548`.

**CSS.** Ten rules are scoped to `#preview-binds` (`style.css:1480`,
`:1502`, `:1965`, `:2026`, `:2069`, `:2072`, `:2076`, `:2077`, `:2093`,
`:2106`). Eight describe the grid and travel with it. The first two are
the inert-checkbox treatment and must move or widen with the control, for
the reason under "What must not change" above. `:2069` is `.no-nm` and
goes.


## Out of scope

No sticky header: the inline name makes it far less load-bearing, and it
risks a stacking context inside `.settings-pane`'s scroller. No card
widening, which was already tried and rejected with measurements
(`style.css:2736-2755`: a widened section cannot stay centred with the
other four, measured at 103px of horizontal jump at 1040 and 543px at
1920). No new colour tokens. No bulk bind, sort or filter. No change to
`BIND_LABELS`. And not the two items `DESIGN.md` says to leave alone: the
`--brand-text` control-surface AA gap, and the two stacked-label
treatments sitting 1px apart.


## Verification

Nothing in the suite renders the page, so the lexical guards are the floor
and not the ceiling.

1. `uv run --no-sync python -m pytest tests/`, plus `ruff check` and
   `ruff format --check`.
2. Both grid states in the CDP harness at 840x625: the global minimize
   toggle off and on. The `" No preview"` overflow recorded at
   `previews.js:561-570` only appeared with that toggle ON, so a single-state measurement would pass and ship the bug.
3. Header-to-column deltas for all four columns, and no element with
   `scrollWidth > clientWidth`.
4. All four summary states from the polarity table, by flipping
   `lock_default` and the exception list.
5. **Tick a box inside each block and watch its own summary**, which is
   the failure mode "Keeping the summary live" describes and the one no
   lexical guard can see. Do it with a keybind capture armed as well, to
   prove the repaint does not detach the armed button.
6. **An opted-out character's Lock box in the block must read inert**, and
   a character who is both locked and opted out must still show a ticked
   box under the dimming.
7. The accessible name of a roster checkbox, which should be the character
   name with the block's purpose reaching it through the group, and must
   not be a doubled or overridden label.
8. A hand pass against `docs/smoke-checklist.md`, which needs updating for
   the moved controls.

## Open items, measured and closed

- **The disclosure's vertical grouping.** Measured collapsed (the state a
  reader normally sees) in the CDP harness at the 840x625 floor, on both
  blocks: the gap above and the gap below each render at **10.00px**, not
  the intended 2px above / 10px below. `.pv-exc`'s own
  `margin: 2px 0 10px 24px` does carry that asymmetry on paper, but it
  never reaches the page. Its neighbour on both sides is a `.row`, and
  `.row { margin-bottom: 10px }` (`style.css:597`) sits directly above and
  below every `.pv-exc` in the DOM; adjacent block margins collapse to
  their larger value rather than summing, so the row's own 10px wins over
  `.pv-exc`'s 2px top margin every time, and its 10px bottom margin simply
  matches the row's 10px on the way out. The two gaps are not merely
  close — they are the same rendered value on both `preview-nm-exceptions`
  and `preview-lock-exceptions` — so the "closer to the toggle above"
  relationship this design specified does not exist in the rendered page.
  Recorded here rather than fixed: changing `.pv-exc` or `.row` margins is
  a style change outside this task, left for the controller to rule on.
- **Truncation width for the summary.** `previews.js`'s `EXC_NAMES_MAX = 3`
  (`:895`) was chosen against the maintainer's own roster — thirteen
  characters, the size the rest of this document and
  `docs/smoke-checklist.md` already measure the table against — for the
  same reason `alerts.js` records against `HEALTH_NAMES_MAX`: a list of
  names is what the reader can act on, and a bare count is not, so the
  cap exists to keep the sentence readable rather than to fit a
  measurement. At 3 of 13, a summary naming exceptions spells out fewer
  than a quarter of the roster before falling back to "and N more".
