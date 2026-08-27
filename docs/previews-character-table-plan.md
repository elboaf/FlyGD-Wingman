# Previews Character Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Settings › Previews character list into a real table with the character name inline, and move its `Lock` and `Never minimize` columns to disclosures under the global toggles they are exceptions to.

**Architecture:** Five sequential tasks, each leaving the screen coherent. `Lock` leaves the row, then `Never minimize` leaves (taking `.no-nm` and the conditional-cell machinery with it), which frees the width for the name to come inline, after which `Clear` and `Edit…` merge into one cell and the unbound bind button stops shouting. No Python changes: the blocks call the endpoints the row checkboxes already call.

**Tech Stack:** Plain ES5 in `wingman/web/*.js`, plain CSS in `wingman/web/style.css`, no framework and no build step. Tests are lexical guards in `tests/test_page_conventions.py` plus a headless-Brave CDP pass.

**Spec:** `docs/previews-character-table-design.md`

## Global Constraints

- **Nothing in the test suite renders the page.** pytest reads the web sources lexically. A guard passing is not the feature working; every task ends with a CDP pass as well.
- ES5 only. No `let`, `const`, arrow functions, template literals, or `Array.prototype.find`.
- Colours come only from `:root` tokens in `style.css`. No literals.
- Checkboxes must use the `.check` wrapper, built immediately after `input.type = 'checkbox'` and before any listener (`test_page_conventions.py` looks for `'box'` within 600 characters of that assignment).
- Never `window.confirm/prompt/alert`. Use `WM.confirm` / `WM.prompt`.
- `hidden` needs an explicit `[hidden]` override on any selector that sets a `display`.
- The CSS viewport floor is **840x625 logical pixels at every display scaling**.
- The `#preview-binds` card interior is **586px at every window width**. Grid tracks do not wrap: exceeding it clips a control at every width.
- `ruff check` and `ruff format --check` must pass. Line length 88. Note that ruff does not lint `.js` or `.css`, so comment width in those files is on you.
- **Prose that describes moved machinery is a defect, and this lane creates it constantly.** Comments here carry the *why*, often naming the incident that caused the rule, so a comment must never be deleted because its rule looks arbitrary. But a comment left stating something the code no longer does is a defect this repo treats seriously. Tasks 1 and 2 each spent a fix round on exactly this and nothing else. Before you commit, re-read every comment within about forty lines of anything you moved, and every comment that points at a thing by its location ("see the comment on its append below", "the column header carries it once"). Keep the history and change the tense and the subject: say what was true then, what this task retired, and what is true now.
- Run the whole suite: `uv run --no-sync python -m pytest tests/`.

## The CDP verification harness

Every task's verification step uses a real-app CDP probe: headless Brave over the debugging port, driven by the **Windows** interpreter at `/mnt/c/Users/tng/AppData/Local/Programs/Python/Python312/python.exe` so the port stays on `127.0.0.1`.

Task 1 built one at `/mnt/c/dev/wingman-testrun/lock-disclosure-probe.py`. Copy it and adapt its assertions per task. It already carries the parts that are easy to get wrong: the stdlib WebSocket client, `--force-device-scale-factor=1`, `Network.setCacheDisabled` plus a hard reload (the profile persists between runs, so a stale `style.css` out of the disk cache is the kind of "verified" that verifies nothing), and `Emulation.setDeviceMetricsOverride` at the 840x625 floor.

**Do not use `/mnt/c/dev/wingman-testrun/mockup-shot.py`.** It targets the design mockup, whose element ids (`#pv-new`) do not exist in the app. Repointing its `URL` is not enough; its measurement function is mockup-shaped.

Run from that directory, not from the worktree:

```bash
cd /mnt/c/dev/wingman-testrun && \
  "/mnt/c/Users/tng/AppData/Local/Programs/Python/Python312/python.exe" <probe>.py
```

**Measure both minimize-toggle states, every time.** The last overflow bug on this row only appeared with `minimize_inactive_clients` ON, which is not the default; a single-state measurement passed and shipped it (`previews.js:561-570`).

---

### Task 1: Lock moves to a disclosure under its toggle

**Files:**
- Modify: `wingman/web/index.html` (after the `preview-lock-default` row, ~line 694)
- Modify: `wingman/web/previews.js` (`makeRow`, `makeHeadRow`, `makeLockCheck`, `render`)
- Modify: `wingman/web/style.css` (`#preview-binds` templates; `.check.inert` scoping; new `.pv-exc` rules)
- Test: `tests/test_page_conventions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `renderLockBlock()` in `previews.js`, called by `render()` and by `makeLockCheck`'s own change handler; the DOM ids `preview-lock-exceptions` (the `<details>`), `preview-lock-exceptions-summary` (its `<summary>`), `preview-lock-exceptions-list` (the roster container). Task 2 builds `renderNeverMinimizeBlock()` against the same shape.

- [ ] **Step 1: Widen the two inert rules so the treatment travels with the control**

The class is the entire visible treatment: `inert()` sets `WM.setEnabled` on the input, and the input is `opacity: 0` and out of flow, so without these rules an opted-out character's Lock box looks live. In `style.css`, change the two selectors at `:1480` and `:1502` from host-scoped to class-scoped, keeping both comment blocks intact above them:

```css
.check.inert { opacity: .45; cursor: default; }
.check.inert input:not(:checked) + .box { background: var(--sunken); }
```

Add one sentence to the comment above the first, recording why they are no longer scoped: the control they describe now renders in two places, and scoping it to `#preview-binds` would silently drop the treatment in the second.

- [ ] **Step 2: Update the three guards that name Lock**

`makeRow` will append **six** cells per character row instead of seven, and `#preview-binds` will declare `repeat(6, ...)` with `.no-nm` at `repeat(5, ...)`. The two count guards derive rather than restate, so they need no edit. Three guards name `Lock` literally and do need one.

In `test_the_previews_headings_are_in_the_order_makeRow_builds` (`:1419`), delete the `Lock` entry from `owners`:

```python
    owners = (
        ("Preview", "makeExcludedCheck"),
        ("Keybind", "'bindbtn'"),
        ("Size", "makeSizeButton"),
        ("Never minimize", "makeNeverMinimizeCheck"),
    )
```

`test_an_opted_out_character_row_disables_its_own_controls` (`:1509`) asserts `makeLockCheck(character, ... off)` inside `makeRow`. The call is leaving, but the invariant is not: the spec keeps "Lock is inert for an opted-out character". Move the assertion to the block's call site. Replace the second loop with:

```python
    for builder in ("makeSizeButton",):
        assert re.search(rf"{builder}\(character,[^)]*\boff\b", body), (
            f"makeRow does not pass the row's opted-out state to {builder}"
        )
    # Lock left the row for its own disclosure, and took this invariant with
    # it: with no window there is nothing to lock, so the block must pass
    # each character's opted-out state the way the row used to. Asserted on
    # the CALL, not inside the builder, because the call site is what
    # decides -- the same reasoning the never-minimize guard below gives.
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    assert re.search(r"makeLockCheck\(name,[^)]*isExcluded\(name\)", src), (
        "the Lock block does not pass each character's opted-out state, so "
        "an opted-out character gets a live control over a window that is "
        "not there"
    )
```

`test_never_minimize_stays_live_on_an_opted_out_row` (`:1534`) asserts both builders against `makeRow`. Only its Lock half moves in this task; its never-minimize half still holds until Task 2. Replace its Lock assertion with the same `src`-scoped one:

```python
    assert re.search(r"makeLockCheck\(name,[^)]*isExcluded\(name\)", src), (
        "Lock SHOULD be gated -- with no window there is nothing to lock"
    )
```

reading `src` the same way, and leave the `makeNeverMinimizeCheck(character)` assertion alone.

- [ ] **Step 3: Run the suite to watch it fail**

Run: `uv run --no-sync python -m pytest tests/test_page_conventions.py -q`
Expected: FAIL. `test_the_previews_headings_are_in_the_order_makeRow_builds` reports that `makeHeadRow` still names a `Lock` column, and the two count guards now disagree with the templates.

- [ ] **Step 4: Take the Lock cell off the row**

In `previews.js`'s `makeRow`, delete the `row.appendChild(makeLockCheck(character, off));` line and, in the `else` branch, one of the filler `document.createElement('span')` appends, so both branches still contribute the same count. In `makeHeadRow`, drop `'Lock'` from the `cells` array:

```javascript
    var cells = ['Preview', 'Keybind', '', '', 'Size'];
```

In `style.css`, drop one track from each template:

```css
  grid-template-columns: repeat(6, max-content) minmax(0, 1fr);
```

```css
#preview-binds.no-nm {
  grid-template-columns: repeat(5, max-content) minmax(0, 1fr);
}
```

- [ ] **Step 5: Add the disclosure markup**

In `index.html`, immediately after the `preview-lock-default` row's closing `</div>`, add the block. It is empty in the markup on purpose, for the reason `preview-binds-off` already carries: the words are computed from state the page holds, and a copy here would be a second place to keep in step.

```html
        <details class="pv-exc" id="preview-lock-exceptions">
          <summary id="preview-lock-exceptions-summary"></summary>
          <div class="pv-exc-list" id="preview-lock-exceptions-list"
               aria-labelledby="preview-lock-exceptions-summary"></div>
        </details>
```

- [ ] **Step 6: Add the disclosure CSS**

```css
/* The per-character exceptions to a global preview default. Sits directly
   under the toggle it excepts, indented to that toggle's label text (the
   .check wrapper's 15px box plus its 9px gap), so the exception reads as
   belonging to the rule above it rather than to the control below.

   The gap above is deliberately smaller than the gap below: the collapsed
   summary is one line, and equal gaps let it read as a heading for the
   NEXT toggle. */
.pv-exc { margin: 2px 0 10px 24px; font-size: var(--fs-muted); }
.pv-exc summary { cursor: pointer; color: var(--text-dim); }
.pv-exc summary:hover { color: var(--text); }
/* Same column treatment .es-roster uses on Profiles, and for the same
   reason: a list of character names in a card too narrow for one column
   leaves most of its width empty. */
.pv-exc-list { columns: 170px; column-gap: 16px; margin: 8px 0 0 16px; }
.pv-exc-list > .check { break-inside: avoid; padding: 2px 0; }
```

- [ ] **Step 7: Render the block**

Add to `previews.js`, above `render()`. `isLocked()` already resolves the `lock_default` XOR, so the checkboxes inherit it; only the sentence is new.

```javascript
  // How many names a summary spells out before it counts the rest. Same
  // number and same reason as alerts.js's HEALTH_NAMES_MAX: a list of
  // names is what the reader can act on, and a bare count is not.
  var EXC_NAMES_MAX = 3;

  function nameList(names) {
    var shown = names.slice(0, EXC_NAMES_MAX);
    var rest = names.length - shown.length;
    return rest > 0 ? shown.join(', ') + ' and ' + rest + ' more'
                    : shown.join(', ');
  }

  // The summary is keyed on the RESOLVED state, not on the exception list
  // being empty. With lock_default on and no exceptions every character is
  // already locked, so a door inviting the reader to lock one would offer
  // something already done.
  function lockSummary(names, all) {
    if (!names.length) { return 'Lock individual characters'; }
    if (names.length === all.length) { return 'Locked: every character'; }
    var unlocked = all.filter(function (n) {
      return names.indexOf(n) === -1;
    });
    // Past halfway the exception is shorter than the rule, and naming the
    // shorter side is what makes the sentence readable at 13 characters.
    if (unlocked.length < names.length) {
      return 'Locked: every character except ' + nameList(unlocked);
    }
    return 'Locked: ' + nameList(names);
  }
```

- [ ] **Step 8: Give the checkbox its name back, as visible text**

`makeLockCheck` builds `WM.make('label', 'check', '')` — an empty label
holding nothing but the box — and puts the accessible name on the input
instead. That is right under a column header and wrong in a list, where
the header does not exist and the block would render as a column of
anonymous boxes.

After Step 4 the block is `makeLockCheck`'s only caller, so change it
rather than adding a variant. Replace the `aria-label` line and the empty
label with:

```javascript
    // The name is VISIBLE text here, not an aria-label. Under a column
    // header the word beside the box is the header repeated once per row,
    // which is why it used to be dropped and the accessible name moved
    // onto the input (DESIGN.md). In a list there is no header to carry
    // it, so the word comes back and the aria-label goes: a label with
    // text AND an aria-label would override the visible one, which is the
    // failure WCAG 2.5.3 names. What the tick MEANS reaches the reader
    // through the group's aria-labelledby, once, not per row.
    var label = WM.make('label', 'check', name);
```

Delete the `box.setAttribute('aria-label', ...)` line. Keep the
`label.prepend` pair exactly where it is: the wrapper must still be built
within 600 characters of `input.type = 'checkbox'`.

- [ ] **Step 9: Build the roster and wire the commit**

```javascript
  function renderLockBlock() {
    var box = WM.el('preview-lock-exceptions');
    var summary = WM.el('preview-lock-exceptions-summary');
    var list = WM.el('preview-lock-exceptions-list');
    if (!box || !summary || !list) { return; }
    var all = rows().map(function (entry) { return entry.name; });
    var locked = all.filter(isLocked);
    summary.textContent = lockSummary(locked, all);
    list.textContent = '';
    all.forEach(function (name) {
      list.appendChild(makeLockCheck(name, isExcluded(name)));
    });
    box.hidden = !all.length;
  }
```

`makeLockCheck` keeps its signature and its `inert()` return, so an
opted-out character stays inert here exactly as it was on the row. Call
`renderLockBlock()` at the end of `render()`.

- [ ] **Step 10: Repaint the summary when its own box changes**

This is the spec's Blocking finding. The existing handler patches `state.locked` and returns, which is correct while the only reader is the box the user clicked. Inside `makeLockCheck`'s `change` handler, after the line that assigns `state.locked`, add:

```javascript
        // The block's summary reads this list, so patching it without a
        // repaint leaves the sentence above the box stating the state
        // before the click. Only this block, not render(): a full render
        // while a keybind capture is armed detaches the armed button.
        renderLockBlock();
```

Do **not** add it before the `pushes` guard or the `defaultAtSend` branch. That branch already calls `refresh()`, which re-renders everything; bumping `pushes` there instead was tried and made `send()` drop an accepted keybind save (`previews.js:503-516`).

- [ ] **Step 11: Run the suite**

Run: `uv run --no-sync python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 12: Verify in the browser**

Run the CDP probe with the toggle off and on. Confirm: the row has no Lock cell; the block appears under the toggle; ticking a name changes the summary immediately; an opted-out character's box in the block is dimmed and does not respond; a character both locked and opted out still shows a ticked box under the dimming; nothing has `scrollWidth > clientWidth`.

- [ ] **Step 13: Commit**

```bash
git add wingman/web/index.html wingman/web/previews.js wingman/web/style.css tests/test_page_conventions.py
git commit -m "Previews: move Lock to a disclosure under its own toggle"
```

---

### Task 2: Never minimize moves, and `.no-nm` dies

**Files:**
- Modify: `wingman/web/index.html` (after the `preview-minimize-inactive-status` row, ~line 629)
- Modify: `wingman/web/previews.js` (`makeRow`, `makeHeadRow`, `render`)
- Modify: `wingman/web/style.css` (`#preview-binds`, delete `#preview-binds.no-nm`)
- Test: `tests/test_page_conventions.py`

**Interfaces:**
- Consumes: `renderExceptionBlock` shape and the `.pv-exc` CSS from Task 1.
- Produces: `#preview-binds` with a single unconditional template; `renderNeverMinimizeBlock()`.

- [ ] **Step 1: Retire the delta guard and update the ordering guard**

Delete `test_the_previews_grid_drops_exactly_one_track_with_never_minimize` (`:1282`) entirely. Its subject is the difference between two templates, and after this task there is one. Replace it with a guard that the second template has not crept back:

```python
def test_the_previews_grid_declares_exactly_one_template():
    """`.no-nm` existed because the Never-minimize cell rendered only while
    the global minimize toggle was on, so makeRow appended a different
    number of cells in each state and the stylesheet needed two templates
    whose difference was maintained by hand.

    That control now lives in its own disclosure under the toggle, so the
    row's cell count no longer varies and the second template is gone. A
    reintroduced conditional cell must bring back a guard for its own
    difference rather than reusing this one.
    """
    assert ".no-nm" not in CSS, (
        "#preview-binds.no-nm is back -- a conditional cell needs a guard "
        "on the difference between the two templates, not just a template"
    )
    body = _makerow_body()
    assert "minimizeInactive" not in body, (
        "makeRow appends a conditional cell again, so its cell count "
        "varies with a setting and one template cannot describe both"
    )
```

In `test_the_previews_headings_are_in_the_order_makeRow_builds` (`:1419`), delete the `Never minimize` entry from `owners`, leaving `Preview`, `Keybind`, `Size`.

`test_the_previews_header_row_names_one_column_per_track` (`:1353`) loops over two selectors and asserts each has a rule block. The second stops existing in this task. Reduce the loop to one selector and drop the now-meaningless `conditional` term:

```python
    m = re.search(r"#preview-binds \{(.*?)\}", CSS, re.DOTALL)
    assert m, "#preview-binds has no rule block"
    tracks = re.search(r"grid-template-columns:\s*repeat\((\d+),", m.group(1))
    assert tracks, "#preview-binds no longer declares repeat(N, ...) tracks"
    assert base == int(tracks.group(1)), (
        f"makeHeadRow names {base} columns but #preview-binds declares "
        f"{tracks.group(1)} tracks -- the headings sit over the wrong "
        f"controls, and a heading falling into a narrower shared track "
        f"widens it for every row below"
    )
```

Keep `base` derived from the array literal. Delete the `conditional = body.count("cells.push(")` line and add an assertion that no conditional heading has crept back, so the two-state hazard cannot return unguarded:

```python
    assert "cells.push(" not in body, (
        "makeHeadRow names a conditional column again, so the header's cell "
        "count varies with a setting and one template cannot describe both"
    )
```

`test_never_minimize_stays_live_on_an_opted_out_row` (`:1534`) still asserts `makeNeverMinimizeCheck(character)` against `makeRow`, and that call is leaving. The invariant is not: the spec keeps never-minimize live for an opted-out character. Move it to the block's call site:

```python
    src = _strip_js_comments((WEB / "previews.js").read_text(encoding="utf-8"))
    assert re.search(r"makeNeverMinimizeCheck\(name\)", src), (
        "makeNeverMinimizeCheck is being passed an opted-out state, which "
        "would grey a checkbox whose setting is still enforced"
    )
```

- [ ] **Step 2: Run to watch it fail**

Run: `uv run --no-sync python -m pytest tests/test_page_conventions.py -q`
Expected: FAIL on both the new `.no-nm` assertion and the ordering guard.

- [ ] **Step 3: Take the cell and the conditional off the row**

In `makeRow`, delete the `if (minimizeInactive) { row.appendChild(makeNeverMinimizeCheck(character)); }` block and, in the `else` branch, the matching conditional filler, so both branches append a fixed count. In `makeHeadRow`, delete the `if (minimizeInactive) { cells.push('Never minimize'); }` line:

```javascript
    var cells = ['Preview', 'Keybind', '', '', 'Size'];
```

In `render()`, delete the `host.classList.toggle('no-nm', !minimizeInactive);` line. In `style.css`, delete the whole `#preview-binds.no-nm` block and its comment, and set the one remaining template:

```css
  grid-template-columns: repeat(5, max-content) minmax(0, 1fr);
```

- [ ] **Step 4: Add the second disclosure**

In `index.html`, immediately after the `preview-minimize-inactive-status` row:

```html
        <details class="pv-exc" id="preview-nm-exceptions">
          <summary id="preview-nm-exceptions-summary"></summary>
          <div class="pv-exc-list" id="preview-nm-exceptions-list"
               aria-labelledby="preview-nm-exceptions-summary"></div>
        </details>
```

Then shorten the toggle's own hint at `:626`, whose second sentence exists only to point at the other card:

```html
          <span class="hint" id="preview-minimize-inactive-status">Applies
            the next time a client is switched away from, not this
            one.</span>
```

- [ ] **Step 5: Give this checkbox its name back too**

`makeNeverMinimizeCheck` has the same empty label and input-side
accessible name as `makeLockCheck` did (`var label = WM.make('label',
'check nm', '');` plus `box.setAttribute('aria-label', 'Never minimize ' +
name + "'s EVE window")`). Same change, same reason: after Step 3 the
block is its only caller, and in a list there is no column header to carry
the word.

```javascript
    // Visible text, not an aria-label -- see makeLockCheck for the full
    // reasoning. `.nm` stays in the class list: it is how the smoke pass
    // and the layout probes tell this checkbox from Lock.
    var label = WM.make('label', 'check nm', name);
```

Delete the `box.setAttribute('aria-label', ...)` line, and keep the
`label.prepend` pair adjacent to `input.type = 'checkbox'`.

- [ ] **Step 6: Render it**

`never_minimize` is a plain membership list with no default toggle, so this block has two states rather than the lock block's four.

```javascript
  function nmSummary(names) {
    return names.length ? 'Never minimized: ' + nameList(names)
                        : 'Exempt individual characters';
  }

  function renderNeverMinimizeBlock() {
    var box = WM.el('preview-nm-exceptions');
    var summary = WM.el('preview-nm-exceptions-summary');
    var list = WM.el('preview-nm-exceptions-list');
    if (!box || !summary || !list) { return; }
    var all = rows().map(function (entry) { return entry.name; });
    // D6: the whole block is absent while the global toggle is off, not
    // present and dead. Nothing here can do anything in that state.
    box.hidden = !minimizeInactive || !all.length;
    if (box.hidden) { return; }
    summary.textContent = nmSummary(all.filter(isNeverMinimize));
    list.textContent = '';
    all.forEach(function (name) {
      // NOT gated on isExcluded, unlike the Lock block. Opting a character
      // out stops their preview; _activate_client still consults this for
      // the real EVE window, so a dimmed box here would leave a setting in
      // force with no control to change it.
      list.appendChild(makeNeverMinimizeCheck(name));
    });
  }
```

Call it at the end of `render()`.

- [ ] **Step 7: Repaint on change**

In `makeNeverMinimizeCheck`'s `change` handler, after the `state.never_minimize` assignment:

```javascript
        renderNeverMinimizeBlock();
```

- [ ] **Step 8: Confirm `[hidden]` actually hides**

`.pv-exc` sets no `display`, so `[hidden]`'s UA rule applies and no override is needed. Confirm by running `test_every_hidden_element_can_actually_hide`:

Run: `uv run --no-sync python -m pytest tests/test_page_conventions.py::test_every_hidden_element_can_actually_hide -q`
Expected: PASS.

- [ ] **Step 9: Run the suite**

Run: `uv run --no-sync python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 10: Verify in the browser**

Both toggle states. With the global minimize toggle off the block must not render at all. With it on, ticking a name must change the summary immediately, and an opted-out character's box must stay live.

- [ ] **Step 11: Commit**

```bash
git add wingman/web/index.html wingman/web/previews.js wingman/web/style.css tests/test_page_conventions.py
git commit -m "Previews: move Never minimize out of the row, retiring .no-nm"
```

---

### Task 3: The character name comes inline

**Files:**
- Modify: `wingman/web/style.css` (`#preview-binds` and its `.lab` rules)
- Modify: `wingman/web/previews.js` (`makeHeadRow`, `makeRow`'s label)
- Modify: `DESIGN.md`
- Test: `tests/test_page_conventions.py`

**Interfaces:**
- Consumes: the five-track grid from Task 2.
- Produces: a six-track grid whose first track is a fixed 150px name column.

- [ ] **Step 1: Rewrite the two guards that assume a spanning label**

`test_the_previews_grid_has_one_track_per_cell_makeRow_appends` (`:1321`) excludes the label because it spans, and reads the track count with `repeat\((\d+),`, which will now match only the repeated half. Replace its body's last three statements:

```python
    body = _makerow_body()
    halves = body.split("} else {", 1)
    assert len(halves) == 2, "makeRow no longer has the cycle-row filler branch"
    # The label is COUNTED now: it sits in track 1 rather than spanning the
    # row, so it is a cell like any other. That is the whole change, and it
    # is why the -1 that used to discount it is gone.
    cells = body.count("row.appendChild(") - halves[1].count("row.appendChild(")

    m = re.search(r"#preview-binds \{(.*?)\}", CSS, re.DOTALL)
    assert m, "#preview-binds has no rule block"
    fixed = re.search(r"grid-template-columns:\s*(\d+)px\s+repeat\((\d+),",
                      m.group(1))
    assert fixed, (
        "#preview-binds no longer declares a fixed first track followed by "
        "repeat(N, ...) -- a max-content name column is round 3's B1 bug, "
        "where the track followed whoever was logged in"
    )
    tracks = 1 + int(fixed.group(2))

    assert cells == tracks, (
        f"makeRow appends {cells} cells per character row but #preview-binds "
        f"declares {tracks} tracks -- every row after the first is "
        f"pulled into the previous row's leftover columns"
    )
```

**While you are in this test, decide the shape of `makeRow`'s branch.** Task 2 left `if (character) { <comments only> } else { <one filler append> }` — an empty `if` whose prose records what used to be built there. The obvious cleanup is `if (!character)`, and it is blocked by this very test: the body is split on the literal string `"} else {"` and the split is asserted to find two halves, so collapsing the branch fails the guard with "makeRow no longer has the cycle-row filler branch". You are rewriting the guard, so you may collapse the branch and change the split with it, or leave both. If you collapse it, keep the prose — move it above the `if` — and replace the split-based count with one that does not depend on a brace-and-keyword string. If you leave it, say nothing; Task 2 already documented why it is empty.

Then fix the header guard, which reads its track count with a regex anchored to `repeat(` and will not match a fixed first track. In `test_the_previews_header_row_names_one_column_per_track`, replace the `tracks` search and its assertion:

```python
    fixed = re.search(r"grid-template-columns:\s*(\d+)px\s+repeat\((\d+),",
                      m.group(1))
    assert fixed, (
        "#preview-binds no longer declares a fixed first track followed by "
        "repeat(N, ...)"
    )
    tracks = 1 + int(fixed.group(2))
    assert base == tracks, (
        f"makeHeadRow names {base} columns but #preview-binds declares "
        f"{tracks} tracks -- the headings sit over the wrong controls, and "
        f"a heading falling into a narrower shared track widens it for "
        f"every row below"
    )
```

Then guard the new column in `test_the_previews_headings_are_in_the_order_makeRow_builds`, so it is ordered against its own cell like every other heading:

```python
    owners = (
        ("Character", "'lab'"),
        ("Preview", "makeExcludedCheck"),
        ("Keybind", "'bindbtn'"),
        ("Size", "makeSizeButton"),
    )
```

While you are in that test, its docstring opens by illustrating the hazard with "moving `makeLockCheck` ahead of the Size cell is an entirely plausible edit". `makeLockCheck` left `makeRow` in Task 1, so the example names an edit nobody can make. Keep the point and change the example to one that is now plausible: moving `makeExcludedCheck` ahead of the name cell.

Then add the guard for the hazard this change creates:

```python
def test_every_previews_row_starts_a_fresh_grid_line():
    """With the name inline each row contributes fewer cells than the grid
    has tracks, because the trailing minmax(0, 1fr) holds no control. Grid
    auto-placement then puts the NEXT row's first cell in that leftover
    track, and every row after it walks one column left -- measured in the
    harness as the second character's name landing in the far-right column
    while its own controls slid under the wrong headings.

    A definite column-start resets auto-placement to a fresh row. The
    spanning label used to do this for free, which is why the hazard is
    new: it arrived with the inline name, not with the grid.
    """
    assert re.search(r"#preview-binds \.row > :first-child \{[^}]*"
                     r"grid-column-start:\s*1", CSS, re.DOTALL), (
        "#preview-binds rows no longer pin their first cell to column 1, so "
        "the trailing flexible track swallows the next row's first cell"
    )
```

- [ ] **Step 2: Rewrite the retired cross-list invariant**

`test_the_two_keybind_lists_render_the_same_row` (`:222`) requires both lists to put the name on its own line. Replace the whole test:

```python
def test_each_keybind_list_declares_a_deliberate_first_track():
    """Round 3's B1 made both bind lists stack the name above its controls,
    because each list's first track was `max-content` over ITS OWN labels
    and the bind button sat 103.4 CSS px apart in two sections of one
    screen -- Previews' half moving between sessions, because the track
    followed whoever was logged in.

    THAT RULE IS RETIRED, deliberately, and this is what replaced it. The
    two lists differ in content: Bookmarks' longest label is "Convert
    EvE-Scout Bookmarks" at 189.6px and needs its own line, while character
    names are uniform and short enough for a column. Only four ungrouped
    Bookmarks rows were ever in the shared grid anyway -- round 5's C8 moved
    the other fourteen into .bind-dense, which is flex and shares no tracks.

    What still has to hold is that neither list gets there by accident. A
    `max-content` first track is the original bug; each list must declare
    either a fixed track or a spanning label, and say which.
    """
    for host, expected in (("#eve-binds", "span"), ("#preview-binds", "fixed")):
        m = re.search(re.escape(host) + r" \{(.*?)\}", CSS, re.DOTALL)
        assert m, f"{host} has no rule block"
        template = re.search(r"grid-template-columns:([^;]*);", m.group(1))
        assert template, f"{host} declares no grid-template-columns"
        first = template.group(1).strip().split()[0]
        assert not first.startswith("max-content"), (
            f"{host}'s first track is max-content over its own labels, "
            f"which is round 3's B1 -- the bind button moves with the "
            f"content and, in Previews, between sessions"
        )
        lab = re.search(re.escape(host) + r" \.row > \.lab \{(.*?)\}",
                        CSS, re.DOTALL)
        assert lab, f"{host} no longer overrides the shared label column"
        spans = "grid-column: 1 / -1" in lab.group(1)
        assert spans == (expected == "span"), (
            f"{host}'s label {'spans' if spans else 'sits in a track'}, "
            f"which is not what this list decided: Bookmarks spans for its "
            f"189.6px labels, Previews takes a fixed column for its names"
        )
```

- [ ] **Step 3: Run to watch both fail**

Run: `uv run --no-sync python -m pytest tests/test_page_conventions.py -q`
Expected: FAIL on the fixed-first-track search, the `:first-child` search, and the Previews half of the first-track test.

- [ ] **Step 4: Reshape the grid**

In `style.css`, replace the `#preview-binds` template and rewrite the comment above it to describe six tracks with a fixed first:

```css
  grid-template-columns: 150px repeat(5, max-content) minmax(0, 1fr);
```

Replace the two `.lab` rules. The name is a cell now, so it no longer spans and no longer needs the margin that separated stacked blocks:

```css
#preview-binds .row > .lab {
  width: auto; min-width: 0; text-align: left; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* Each row contributes fewer cells than the grid has tracks, because the
   trailing flexible one holds no control. Without a definite start, grid
   auto-placement puts the NEXT row's first cell there and every row after
   it walks one column left. The spanning label used to prevent this for
   free; the inline name is what makes it necessary. */
#preview-binds .row > :first-child { grid-column-start: 1; }
```

Keep the `@media (max-width: 720px)` restore: `test_an_id_override_of_the_label_column_still_collapses_at_the_floor` requires every id override of the label column to carry one, and this is still an override.

- [ ] **Step 5: Name the column, and give a long name its full text**

In `makeHeadRow`:

```javascript
    var cells = ['Character', 'Preview', 'Keybind', '', '', 'Size'];
```

In `makeRow`, after `var lab = WM.make('span', 'lab', label);`, add the title so a truncated name is still readable:

```javascript
    // The track is a fixed 150px, so a long name ellipsizes. The title is
    // the only place the whole of it can be read.
    lab.title = label;
```

- [ ] **Step 6: Run the suite**

Run: `uv run --no-sync python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 7: Correct the measurement that this task's mechanism supersedes**

The same seven-column experiment is recorded twice: as a comment above `makeHeadRow` (`previews.js:800-831`) and in `test_the_previews_header_row_names_one_column_per_track`'s docstring. Both close on the same sentence, and it is the one this task falsifies:

> every row leads with `.lab { grid-column: 1 / -1 }` and a definite column-start of 1 resets the auto-placement cursor to a fresh row

The label stops spanning in this task, so the reset now comes from the explicit `:first-child` rule instead. Left alone, the only prose in the repo that explains the auto-placement hazard would credit the wrong mechanism — directly above the rule that took over the job.

**Keep the measurement tables.** They are a record of an experiment that was run, and this repo leaves those as taken (`DESIGN.md`: "the measurement that decided this and is left as it was taken"). Do not delete or renumber them. In both places:

- Add one line above each table saying it was measured against the seven-column layout, before Lock and Never minimize moved to their own disclosures.
- Rewrite the closing paragraph so the fresh-row reset is credited to `#preview-binds .row > :first-child { grid-column-start: 1 }`, and say that the spanning label used to do this for free — which is why the hazard arrived with the inline name rather than with the grid.

- [ ] **Step 8: Verify in the browser, and measure**

Both toggle states. Confirm `used` is about 526 of the 586 interior, `overflows` is false, nothing is clipped, and every header's delta from its column is 0.00. Confirm no row's controls sit under the wrong heading, which is the failure mode Step 1's new guard describes.

- [ ] **Step 9: Re-argue the three `DESIGN.md` passages**

Do not append. Rewrite in place:

- `:266` ("If you out-specify the label column, restore its collapse yourself") cites `#preview-binds` as an example of a list with long labels. Keep the rule and the requirement, and change the example: Previews now takes the column away to give the name a fixed track of its own, not because its labels are long.
- `:194` ("A checkbox in a table column carries no word, and still carries a name") uses "three words × thirteen rows" on this list as its evidence. Two of those three columns have left the table. Keep the rule, and mark the evidence as the state that produced it.
- Add a short passage recording that B1's shared shape is retired and why, so nobody restores it from the old reasoning. Name the replacement guard by its new test name.

- [ ] **Step 10: Commit**

```bash
git add wingman/web/previews.js wingman/web/style.css tests/test_page_conventions.py DESIGN.md
git commit -m "Previews: put the character name in a column of its own"
```

---

### Task 4: `Clear` earns its place, and the unbound state stops shouting

**Files:**
- Modify: `wingman/web/previews.js` (`makeRow`)
- Modify: `wingman/web/style.css` (`.bindbtn.unset`, `.rowacts`, `#preview-binds` template)
- Test: `tests/test_page_conventions.py`

**Interfaces:**
- Consumes: the six-track grid from Task 3.
- Produces: the final five-track grid; `.rowacts` as the shared actions cell.

- [ ] **Step 1: Extend the do-not-draw-a-dead-control guard to `Clear`**

`test_the_size_control_is_not_drawn_where_it_could_only_refuse` (`:1468`) states D6's rule for one control. Add its sibling:

```python
def test_clear_is_not_drawn_where_it_could_only_refuse():
    """Same rule as the Size test above, applied to the control that broke
    it worst. `Clear` was rendered on every row and disabled wherever there
    was no chord to clear -- which, on a fresh install, is every row. It is
    a .linkbtn, so :disabled is opacity .45 over --text-faint: 1.94:1
    against the card, a control nobody can read holding a grid track on
    thirteen rows.

    Its function is not lost. Edit... with an empty submission clears, and
    that path predates this change.
    """
    body = _makerow_body()
    assert "if (gesture) {" in body, (
        "makeRow no longer chooses whether to build Clear -- it is back to "
        "rendering a control that can only refuse on every unbound row"
    )
    assert re.search(r"WM\.setEnabled\(clear,[^)]*\boff\b", body), (
        "Clear is no longer gated on the row's opted-out state. Only the "
        "GESTURE half of the old `!off && !!gesture` gate moved out here, "
        "into whether the control is built at all; the opted-out half "
        "stays, or an inert row's one live control is the destructive one"
    )
```

- [ ] **Step 2: Run to watch it fail**

Run: `uv run --no-sync python -m pytest tests/test_page_conventions.py::test_clear_is_not_drawn_where_it_could_only_refuse -q`
Expected: FAIL on the `WM.setEnabled(clear` assertion.

- [ ] **Step 3: Merge the two link buttons into one cell**

In `makeRow`, replace the separate `Clear` and `Edit…` appends with a single wrapper. Build `Clear` only when there is something to clear:

```javascript
    // One cell, not two tracks. Two adjacent link buttons in their own
    // tracks forced two blank header cells, which is the ragged gap
    // between "Keybind" and "Size" the table used to have.
    var acts = WM.make('span', 'rowacts');
    if (gesture) {
      var clear = WM.make('button', 'linkbtn', 'Clear');
      clear.addEventListener('click', function () { endCapture(); onSet(''); });
      WM.setEnabled(clear, !off);
      acts.appendChild(clear);
    }
```

Append the existing `Edit…` button to `acts` instead of to `row`, then `row.appendChild(acts);` in its place. Drop one filler from the `else` branch to match.

- [ ] **Step 4: Pin `Edit…` to one x, and quiet the unbound button**

```css
/* Right-aligned inside its own cell so Edit... holds one x whether or not
   Clear is beside it. The track is max-content over the rows that have
   both, so a row without Clear reads as an empty slot rather than as a
   shifted control. */
.rowacts { display: flex; gap: 2px; justify-content: flex-end; }

/* An unbound chord. Measured against the card, --control (this button's
   fill) is 1.09:1 and --control-border 1.32:1, so the box is very nearly
   invisible and what carried "Not set" thirteen times was --text at
   13.71:1 -- the loudest thing on a screen whose subject is the roster.
   --text-dim is 6.43:1 on --control, well over AA, and leaves a BOUND
   chord as the thing that stands out.

   Cannot collide with the three states below: clashes() returns null for
   an empty gesture and no bookmark chord list contains "", so an unset
   button is never also .clash, .unknown or .dim. */
.bindbtn.unset { color: var(--text-dim); }
```

In `makeRow`, add the class where the button is built:

```javascript
    if (!gesture) { button.classList.add('unset'); }
```

Drop the template to its final width:

```css
  grid-template-columns: 150px repeat(4, max-content) minmax(0, 1fr);
```

and the header's second blank:

```javascript
    var cells = ['Character', 'Preview', 'Keybind', '', 'Size'];
```

- [ ] **Step 5: Fix the tooltip that names a control that no longer exists**

At `previews.js:207` the opted-out bind tooltip ends "comes back when you untick **Off**". There has been no box named `Off` since it became the inverted `Preview` box:

```javascript
      button.title = 'Previews are off for this character, so this keybind '
                   + 'is not registered. It is still saved, and comes back '
                   + 'when you tick Preview again.';
```

- [ ] **Step 6: Run the suite**

Run: `uv run --no-sync python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 7: Verify in the browser**

Both toggle states. Confirm `used` is 519 of 586 and `free` 68; all four header deltas are 0.00; `Edit…` sits at the same x on rows with and without `Clear`; a bound chord reads brighter than "Not set".

- [ ] **Step 8: Commit**

```bash
git add wingman/web/previews.js wingman/web/style.css tests/test_page_conventions.py
git commit -m "Previews: draw Clear only where it can act, and quiet Not set"
```

---

### Task 5: The smoke pass, and the spec's open items

**Files:**
- Modify: `docs/smoke-checklist.md`
- Modify: `docs/previews-character-table-design.md`

- [ ] **Step 1: Re-point the smoke checklist**

Two items describe the controls this lane moved, and both are now false.

`docs/smoke-checklist.md:1471` ("No dead Never-minimize checkboxes in the
default state") tests that ticking the global toggle adds a checkbox to
every character row, and that the header gains a column in the same
toggle. Neither happens any more. Rewrite it against the disclosure: with
the toggle off the block must not render at all; with it on the block
appears, live, without a reload; ticking a name changes the summary
immediately; an opted-out character stays live here, unlike in the Lock
block. Keep its alignment paragraph, which still applies to the grid.

`docs/smoke-checklist.md:1490` ("The columns are named once, above the
rows") lists the headings as `Preview`, `Keybind`, `Size`, `Lock`, `Never
minimize`. Change the list to `Character`, `Preview`, `Keybind`, `Size`,
and say that the three checkbox columns are now one. Keep the sentence
about `Clear`, `Edit…` and `Size…` carrying their own words, and add that
`Clear` is absent rather than disabled on an unbound row.

Add one new item for the Lock block: the four summary states from the
spec's polarity table, reached by flipping the global toggle and the
exception list.

- [ ] **Step 2: Close the spec's first open item, or record the measurement**

The spec records that the disclosure's vertical grouping is eyeballed: the collapsed summary sits nearer the toggle above than the one below, at 2px and 10px, and whether 10 is enough was never checked. Measure both gaps in the harness. If the gap below is not visibly larger, raise it and say by how much. Replace the open item with the measured numbers either way.

- [ ] **Step 3: Close the second open item**

The spec leaves the summary truncation width unchosen. Task 1 shipped `EXC_NAMES_MAX = 3`. Record that number and the roster size it was chosen against, the way `alerts.js` records its own.

- [ ] **Step 4: Run everything**

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

- [ ] **Step 5: Commit**

```bash
git add docs/smoke-checklist.md docs/previews-character-table-design.md
git commit -m "Docs: re-point the smoke pass, and close the design's open items"
```
